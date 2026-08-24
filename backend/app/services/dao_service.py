"""
大道服务：开道 roll/choose、道池、道资源摘要、运用预览与扣值。

服务端权威；随机经 DiceService；禁止裸 random。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.avatar import (
    ERR_AVATAR_EXISTS_OR_MISSING,
    LOADOUT_ACTOR_AVATAR,
    LOADOUT_ACTOR_MAIN,
    normalize_loadout_actor,
)
from app.constants.dao import (
    DAO_OPEN_MIN_MAJOR_DEFAULT,
    ERR_DAO_BAD_CHOICE,
    ERR_DAO_CANDIDATES,
    ERR_DAO_DISABLED,
    ERR_DAO_LOCKED,
    ERR_DAO_NOT_OPEN,
    ERR_DAO_QI,
    ERR_DAO_REALM,
    ERR_DAO_REROLL,
    ERR_DAO_SESSION,
)
from app.core.config import get_settings
from app.db.models import (
    Avatar,
    AvatarDao,
    AvatarDaoPoolEntry,
    Character,
    CharacterDao,
    DaoPoolEntry,
    User,
)
from app.domain.dao_restraint import DaoRestraintEdge, find_restraint, restraint_battle_event
from app.domain.dao_rules import (
    DaoEntryDef,
    DaoOpenRules,
    DaoResourceRules,
    DaoUsageBranch,
    backfill_candidates_if_short,
    build_candidate_weights,
    catalog_entry_public,
    is_valid_open_choice,
    pick_unique_weighted,
    resolve_dao_level,
)
from app.domain.dao_usage import apply_usage
from app.domain.reincarnation_rules import meets_min_major_realm
from app.schemas.common import AppError
from app.services.dice_service import DiceService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class DaoService:
    """大道用例服务。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话。
        """
        self._session = session
        self._gate = PlayGate(session)
        self._dice = DiceService()

    def _require_enabled(self) -> None:
        """大道总开关。"""
        if not get_settings().dao_system_enabled:
            raise AppError(code=ERR_DAO_DISABLED, message="大道系统未开启", http_status=403)

    def _cfg(self):
        return get_game_config().dao

    def _open_rules(self) -> DaoOpenRules:
        open_cfg = self._cfg().open
        return DaoOpenRules(
            min_major_realm=str(open_cfg.get("min_major_realm") or DAO_OPEN_MIN_MAJOR_DEFAULT),
            picks=int(open_cfg.get("picks") or 3),
            lock_per_run=bool(open_cfg.get("lock_per_run", True)),
            deny_reroll=bool(open_cfg.get("deny_reroll", True)),
            session_ttl_seconds=int(open_cfg.get("session_ttl_seconds") or 600),
        )

    def _resources(self) -> DaoResourceRules:
        res = self._cfg().resources
        curve = tuple(int(x) for x in list(res.get("level_curve") or [0, 100, 250, 500]))
        return DaoResourceRules(
            initial_dao_qi=int(res.get("initial_dao_qi") or 100),
            level_curve=curve,
        )

    def _entries(self) -> dict[str, DaoEntryDef]:
        result: dict[str, DaoEntryDef] = {}
        for dao_id, body in self._cfg().entries.items():
            result[dao_id] = DaoEntryDef(
                dao_id=dao_id,
                label_zh=str(body.get("label_zh") or dao_id),
                category=str(body.get("category") or ""),
                category_label=str(body.get("category_label") or ""),
                rarity=str(body.get("rarity") or ""),
                rarity_label=str(body.get("rarity_label") or ""),
                weight=float(body.get("weight") or 0),
                description=str(body.get("description") or ""),
            )
        return result

    def label_of(self, dao_id: str | None) -> str | None:
        """道 id → 中文名。"""
        if not dao_id:
            return None
        entry = self._cfg().entries.get(dao_id)
        if entry:
            return str(entry.get("label_zh") or self._cfg().labels.get(dao_id) or dao_id)
        return self._cfg().labels.get(dao_id) or dao_id

    def usage_branch(self, kind: str) -> DaoUsageBranch:
        """战斗/工坊运用分支。"""
        usage = dict(self._cfg().usage.get(kind) or {})
        return DaoUsageBranch(
            qi_cost=int(usage.get("qi_cost") or 0),
            dao_exp=int(usage.get("dao_exp") or 0),
            fail_exp_half=bool(usage.get("fail_exp_half", True)),
            damage_mul=float(usage.get("damage_mul") or 1.0),
            mitigation_mul=float(usage.get("mitigation_mul") or 1.0),
            fail_rate_delta=float(usage.get("fail_rate_delta") or 0.0),
            bonus_affix_chance=float(usage.get("bonus_affix_chance") or 0.0),
        )

    async def _load_subject(
        self,
        user: User,
        actor: str | None,
        *,
        settle: bool,
        require_open_realm: bool,
    ) -> tuple[Character, Avatar | None, str]:
        """解析本体/化身主体；化身须已凝练。"""
        actor_n = normalize_loadout_actor(actor)
        if settle:
            character, _ = await self._gate.prepare_for_play(user, settle=True)
        else:
            character = await self._gate.require_character(user)
        avatar: Avatar | None = None
        if actor_n == LOADOUT_ACTOR_AVATAR:
            from app.services.avatar_service import AvatarService

            avatar = await AvatarService(self._session).get_avatar_row(character.id)
            if avatar is None:
                raise AppError(
                    code=ERR_AVATAR_EXISTS_OR_MISSING,
                    message="尚未凝练化身",
                    http_status=400,
                )
        if require_open_realm:
            self._require_open_realm(self._subject_major(character, avatar))
        return character, avatar, actor_n

    def _subject_major(self, character: Character, avatar: Avatar | None) -> str:
        """开道门闸读该主体自己的大境界。"""
        if avatar is not None:
            return str(getattr(avatar, "major_realm", "") or "")
        return str(character.major_realm or "")

    def _require_open_realm(self, major_realm: str) -> None:
        """未达真仙不可进悟道页 / 开道。"""
        rules = self._open_rules()
        if not meets_min_major_realm(major_realm, rules.min_major_realm):
            raise AppError(code=ERR_DAO_REALM, message="未达真仙不可悟道", http_status=400)

    async def _get_or_create_row(
        self,
        character: Character | int,
        avatar: Avatar | None = None,
    ) -> CharacterDao | AvatarDao:
        """获取或创建该主体大道行。可传 Character 或 character_id。"""
        if isinstance(character, int):
            result = await self._session.execute(
                select(Character).where(Character.id == character),
            )
            character = result.scalar_one()
        resources = self._resources()
        if avatar is not None:
            result = await self._session.execute(
                select(AvatarDao).where(AvatarDao.avatar_id == avatar.id),
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return row
            row = AvatarDao(
                avatar_id=avatar.id,
                fate_dao_id=None,
                locked=False,
                dao_qi=resources.initial_dao_qi,
                dao_exp=0,
                dao_level=1,
                opening_session_json=None,
            )
            self._session.add(row)
            await self._session.flush()
            return row
        result = await self._session.execute(
            select(CharacterDao).where(CharacterDao.character_id == character.id),
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = CharacterDao(
            character_id=character.id,
            fate_dao_id=None,
            locked=False,
            dao_qi=resources.initial_dao_qi,
            dao_exp=0,
            dao_level=1,
            opening_session_json=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def _pool_ids(
        self,
        character: Character,
        avatar: Avatar | None = None,
    ) -> set[str]:
        if avatar is not None:
            result = await self._session.execute(
                select(AvatarDaoPoolEntry.dao_id).where(
                    AvatarDaoPoolEntry.avatar_id == avatar.id,
                ),
            )
            return {str(x) for x in result.scalars().all()}
        result = await self._session.execute(
            select(DaoPoolEntry.dao_id).where(DaoPoolEntry.character_id == character.id),
        )
        return {str(x) for x in result.scalars().all()}

    async def _pool_count(
        self,
        character: Character,
        avatar: Avatar | None = None,
    ) -> int:
        return len(await self._pool_ids(character, avatar))

    async def _add_pool_ids(
        self,
        character: Character,
        avatar: Avatar | None,
        dao_ids: list[str],
        owned: set[str],
    ) -> None:
        """把尚未入池的道写入该主体道池。"""
        for oid in dao_ids:
            if oid in owned:
                continue
            if avatar is not None:
                self._session.add(AvatarDaoPoolEntry(avatar_id=avatar.id, dao_id=oid))
            else:
                self._session.add(DaoPoolEntry(character_id=character.id, dao_id=oid))
            owned.add(oid)

    def _can_open(self, major_realm: str, row: CharacterDao | AvatarDao) -> bool:
        rules = self._open_rules()
        if row.locked and row.fate_dao_id:
            return False
        return meets_min_major_realm(major_realm, rules.min_major_realm)

    def build_me_payload(
        self,
        major_realm: str,
        row: CharacterDao | AvatarDao,
        pool_count: int,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """构造 /dao/me 与 CharacterPublic.dao / AvatarPublic.dao。"""
        resources = self._resources()
        level, exp_into, exp_to_next = resolve_dao_level(int(row.dao_exp), resources.level_curve)
        fate_id = row.fate_dao_id
        return {
            "actor": actor,
            "fate_dao_id": fate_id,
            "fate_dao_label": self.label_of(fate_id),
            "qi": int(row.dao_qi),
            "level": int(level),
            "exp": int(row.dao_exp),
            "exp_into_level": int(exp_into),
            "exp_to_next": exp_to_next,
            "pool_count": int(pool_count),
            "can_open": self._can_open(major_realm, row),
            "locked": bool(row.locked and fate_id),
        }

    async def enrich_dao_summary(self, character: Character) -> dict[str, Any] | None:
        """嵌入 CharacterPublic；系统关闭仍返回只读摘要。"""
        if not get_settings().dao_system_enabled:
            return None
        row = await self._get_or_create_row(character)
        count = await self._pool_count(character)
        return self.build_me_payload(
            str(character.major_realm or ""),
            row,
            count,
            actor=LOADOUT_ACTOR_MAIN,
        )

    async def enrich_avatar_dao_summary(
        self,
        character: Character,
        avatar: Avatar,
    ) -> dict[str, Any] | None:
        """嵌入化身面板；系统关闭返回 None。"""
        if not get_settings().dao_system_enabled:
            return None
        row = await self._get_or_create_row(character, avatar)
        count = await self._pool_count(character, avatar)
        return self.build_me_payload(
            str(getattr(avatar, "major_realm", "") or ""),
            row,
            count,
            actor=LOADOUT_ACTOR_AVATAR,
        )

    async def get_catalog(self, user: User, *, actor: str = LOADOUT_ACTOR_MAIN) -> dict[str, Any]:
        """图鉴（须该主体已达真仙，否则悟道页不可见）。"""
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=False,
            require_open_realm=True,
        )
        owned = await self._pool_ids(character, avatar)
        entries = self._entries()
        items = [
            catalog_entry_public(entry, owned=entry.dao_id in owned)
            for entry in entries.values()
        ]
        return {
            "actor": actor_n,
            "items": items,
            "entries": items,
            "total": len(items),
            "count": len(items),
        }

    async def get_me(self, user: User, *, actor: str = LOADOUT_ACTOR_MAIN) -> dict[str, Any]:
        """本命与道资源（须该主体真仙）。"""
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=False,
            require_open_realm=True,
        )
        row = await self._get_or_create_row(character, avatar)
        count = await self._pool_count(character, avatar)
        return self.build_me_payload(
            self._subject_major(character, avatar),
            row,
            count,
            actor=actor_n,
        )

    async def get_pool(self, user: User, *, actor: str = LOADOUT_ACTOR_MAIN) -> dict[str, Any]:
        """道池列表（须该主体真仙）。"""
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=False,
            require_open_realm=True,
        )
        if avatar is not None:
            result = await self._session.execute(
                select(AvatarDaoPoolEntry)
                .where(AvatarDaoPoolEntry.avatar_id == avatar.id)
                .order_by(AvatarDaoPoolEntry.acquired_at.asc()),
            )
        else:
            result = await self._session.execute(
                select(DaoPoolEntry)
                .where(DaoPoolEntry.character_id == character.id)
                .order_by(DaoPoolEntry.acquired_at.asc()),
            )
        rows = list(result.scalars().all())
        entries = self._entries()
        items = []
        for r in rows:
            entry = entries.get(r.dao_id)
            if entry:
                items.append(catalog_entry_public(entry, owned=True))
            else:
                items.append(
                    {
                        "dao_id": r.dao_id,
                        "label": self.label_of(r.dao_id) or r.dao_id,
                        "category": "",
                        "category_label": "未知",
                        "rarity": "",
                        "rarity_label": "未知",
                        "owned": True,
                        "description": "",
                    },
                )
        return {
            "actor": actor_n,
            "items": items,
            "entries": items,
            "total": len(items),
            "count": len(items),
        }

    def _parse_opening(self, row: CharacterDao | AvatarDao) -> dict[str, Any] | None:
        if not row.opening_session_json:
            return None
        try:
            data = json.loads(row.opening_session_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return data

    async def roll_open(
        self,
        user: User,
        *,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """
        生成开道三选项会话。

        Raises:
            AppError: 40080/40081/40095/40096 等。
        """
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=True,
            require_open_realm=True,
        )
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可开道", http_status=409)
        rules = self._open_rules()
        row = await self._get_or_create_row(character, avatar)
        if row.locked and row.fate_dao_id:
            raise AppError(code=ERR_DAO_LOCKED, message="本周目已锁定本命道", http_status=400)
        existing = self._parse_opening(row)
        if existing and rules.deny_reroll:
            expires = existing.get("expires_at")
            still_valid = True
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                    still_valid = datetime.now(timezone.utc) < exp_dt
                except ValueError:
                    still_valid = True
            if still_valid:
                raise AppError(
                    code=ERR_DAO_REROLL,
                    message="已有开道会话，禁止重复抽取；请先确认或等待会话过期",
                    http_status=400,
                )

        owned = await self._pool_ids(character, avatar)
        entries = self._entries()
        weights = build_candidate_weights(entries, owned_dao_ids=owned)
        weights = backfill_candidates_if_short(
            weights,
            entries,
            owned_dao_ids=owned,
            need=rules.picks,
        )
        if len(weights) < rules.picks:
            raise AppError(code=ERR_DAO_CANDIDATES, message="候选道不足三次抽取", http_status=400)

        picked = pick_unique_weighted(
            weights,
            count=rules.picks,
            weighted_pick=self._dice.weighted_pick,
        )
        if len(picked) < rules.picks:
            raise AppError(code=ERR_DAO_CANDIDATES, message="候选道不足三次抽取", http_status=400)

        session_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=rules.session_ttl_seconds)
        allow_pool_pick = bool(owned)
        session_payload = {
            "session_id": session_id,
            "options": picked,
            "allow_pool_pick": allow_pool_pick,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }
        row.opening_session_json = json.dumps(session_payload, ensure_ascii=False)
        await self._session.flush()
        logger.info(
            "dao open roll character_id=%s actor=%s session=%s options=%s",
            character.id,
            actor_n,
            session_id,
            picked,
        )
        options_public = [
            catalog_entry_public(entries[dao_id], owned=dao_id in owned)
            for dao_id in picked
            if dao_id in entries
        ]
        return {
            "actor": actor_n,
            "session_id": session_id,
            "options": options_public,
            "allow_pool_pick": allow_pool_pick,
            "expires_at": session_payload["expires_at"],
            "hint": "抽出的三道将全部录入道池，跨轮回保留；本周目本命道选定后不可更改",
        }

    async def choose_open(
        self,
        user: User,
        *,
        dao_id: str,
        session_id: str | None = None,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """
        确认本命道并入池。

        Args:
            user: 当前用户。
            dao_id: 选定道。
            session_id: 可选校验会话 id。
            actor: main 本体 / avatar 化身。
        """
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=True,
            require_open_realm=True,
        )
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可开道", http_status=409)
        row = await self._get_or_create_row(character, avatar)
        if row.locked and row.fate_dao_id:
            raise AppError(code=ERR_DAO_LOCKED, message="本周目已锁定本命道", http_status=400)
        opening = self._parse_opening(row)
        if not opening:
            raise AppError(code=ERR_DAO_SESSION, message="开道会话不存在或已过期", http_status=400)
        if session_id and str(opening.get("session_id")) != str(session_id):
            raise AppError(code=ERR_DAO_SESSION, message="开道会话不存在或已过期", http_status=400)
        expires = opening.get("expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= exp_dt:
                    row.opening_session_json = None
                    await self._session.flush()
                    raise AppError(code=ERR_DAO_SESSION, message="开道会话不存在或已过期", http_status=400)
            except ValueError:
                pass

        offer_ids = [str(x) for x in list(opening.get("options") or [])]
        allow_pool = bool(opening.get("allow_pool_pick"))
        owned = await self._pool_ids(character, avatar)
        if not is_valid_open_choice(
            chosen_dao_id=dao_id,
            offer_ids=offer_ids,
            allow_pool_pick=allow_pool,
            pool_ids=owned,
        ):
            raise AppError(code=ERR_DAO_BAD_CHOICE, message="非法选择：非本次三选项且非合法道池自选", http_status=400)
        if dao_id not in self._cfg().entries and dao_id not in owned:
            raise AppError(code=ERR_DAO_BAD_CHOICE, message="非法选择：未知大道", http_status=400)

        resources = self._resources()
        row.fate_dao_id = dao_id
        row.locked = True
        row.opening_session_json = None
        if int(row.dao_qi) <= 0 and int(row.dao_exp) == 0:
            row.dao_qi = resources.initial_dao_qi
            row.dao_exp = 0
            row.dao_level = 1
        level, _, _ = resolve_dao_level(int(row.dao_exp), resources.level_curve)
        row.dao_level = level

        await self._add_pool_ids(character, avatar, offer_ids, owned)
        if dao_id not in owned:
            await self._add_pool_ids(character, avatar, [dao_id], owned)

        await self._session.flush()
        logger.info(
            "dao open choose character_id=%s actor=%s fate=%s pool_added=%s",
            character.id,
            actor_n,
            dao_id,
            offer_ids,
        )
        if avatar is None:
            try:
                from app.services.dao_lord_service import DaoLordService

                await DaoLordService(self._session).try_auto_inaugurate(character)
            except Exception:  # noqa: BLE001
                logger.exception("auto inaugurate after open failed character_id=%s", character.id)

        from app.services.character_service import CharacterService

        public = await CharacterService(self._session).enrich_public(character)
        payload: dict[str, Any] = {
            "actor": actor_n,
            "dao": self.build_me_payload(
                self._subject_major(character, avatar),
                row,
                len(owned),
                actor=actor_n,
            ),
            "character": CharacterService.public_to_dict(public),
            "message": f"开道成功：{self.label_of(dao_id)}",
        }
        if avatar is not None:
            from app.services.avatar_service import AvatarService

            payload["avatar"] = await AvatarService(self._session).get_me(character)
        return payload

    async def preview_usage(
        self,
        user: User,
        *,
        kind: str,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """预览战斗/工坊运用消耗与效果。"""
        self._require_enabled()
        character, avatar, actor_n = await self._load_subject(
            user,
            actor,
            settle=False,
            require_open_realm=False,
        )
        row = await self._get_or_create_row(character, avatar)
        if not row.fate_dao_id:
            raise AppError(code=ERR_DAO_NOT_OPEN, message="尚未开辟本命道，不可运用", http_status=400)
        if kind not in ("battle", "craft"):
            raise AppError(code=40000, message="kind 须为 battle 或 craft", http_status=400)
        branch = self.usage_branch(kind)
        return {
            "actor": actor_n,
            "kind": kind,
            "fate_dao_id": row.fate_dao_id,
            "fate_dao_label": self.label_of(row.fate_dao_id),
            "qi_cost": branch.qi_cost,
            "qi_current": int(row.dao_qi),
            "can_afford": int(row.dao_qi) >= branch.qi_cost,
            "can_use": int(row.dao_qi) >= branch.qi_cost,
            "damage_mul": branch.damage_mul,
            "mitigation_mul": branch.mitigation_mul,
            "fail_rate_delta": branch.fail_rate_delta,
            "bonus_affix_chance": branch.bonus_affix_chance,
            "dao_exp": branch.dao_exp,
            "summary": (
                f"运用{self.label_of(row.fate_dao_id)}：耗道值 {branch.qi_cost}，"
                f"成功经验 +{branch.dao_exp}"
            ),
            "effect_label": (
                f"运用{self.label_of(row.fate_dao_id)}：耗道值 {branch.qi_cost}，"
                f"成功经验 +{branch.dao_exp}"
            ),
        }

    async def consume_usage(
        self,
        character: Character,
        *,
        kind: str,
        success: bool,
        actor: str = LOADOUT_ACTOR_MAIN,
    ) -> dict[str, Any]:
        """
        战斗/工坊成功路径扣道值涨经验（内部调用）。

        Raises:
            AppError: 40084/40085。
        """
        self._require_enabled()
        actor_n = normalize_loadout_actor(actor)
        avatar: Avatar | None = None
        if actor_n == LOADOUT_ACTOR_AVATAR:
            from app.services.avatar_service import AvatarService

            avatar = await AvatarService(self._session).get_avatar_row(character.id)
            if avatar is None:
                raise AppError(
                    code=ERR_AVATAR_EXISTS_OR_MISSING,
                    message="尚未凝练化身",
                    http_status=400,
                )
        row = await self._get_or_create_row(character, avatar)
        if not row.fate_dao_id:
            raise AppError(code=ERR_DAO_NOT_OPEN, message="尚未开辟本命道，不可运用", http_status=400)
        branch = self.usage_branch(kind)
        resources = self._resources()
        try:
            result = apply_usage(
                qi=int(row.dao_qi),
                total_exp=int(row.dao_exp),
                resources=resources,
                branch=branch,
                success=success,
            )
        except ValueError as exc:
            raise AppError(code=ERR_DAO_QI, message="道值不足", http_status=400) from exc
        row.dao_qi = result.qi_after
        row.dao_exp = result.exp_after
        row.dao_level = result.level_after
        await self._session.flush()
        logger.info(
            "dao usage character_id=%s actor=%s kind=%s cost=%s exp=%s level=%s→%s",
            character.id,
            actor_n,
            kind,
            result.qi_cost,
            result.exp_gain,
            result.level_before,
            result.level_after,
        )
        if result.leveled_up and avatar is None:
            try:
                from app.services.dao_lord_service import DaoLordService

                await DaoLordService(self._session).try_auto_inaugurate(character)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "auto inaugurate after usage failed character_id=%s",
                    character.id,
                )
        return {
            "actor": actor_n,
            "qi_cost": result.qi_cost,
            "qi_after": result.qi_after,
            "exp_gain": result.exp_gain,
            "level": result.level_after,
            "leveled_up": result.leveled_up,
            "damage_mul": result.damage_mul,
            "mitigation_mul": result.mitigation_mul,
            "fail_rate_delta": result.fail_rate_delta,
            "bonus_affix_chance": result.bonus_affix_chance,
            "fate_dao_id": row.fate_dao_id,
            "fate_dao_label": self.label_of(row.fate_dao_id),
        }

    def restraint_edges(self) -> list[DaoRestraintEdge]:
        """加载克制边。"""
        if not get_game_config().dao.restraint_enabled:
            return []
        edges = []
        for item in get_game_config().dao_restraint.edges:
            edges.append(
                DaoRestraintEdge(
                    attacker=str(item.get("attacker") or ""),
                    defender=str(item.get("defender") or ""),
                    damage_mul=float(item.get("damage_mul") or 1.0),
                    label_zh=str(item.get("label_zh") or "上位克制"),
                ),
            )
        return edges

    def build_restraint_event(
        self,
        *,
        attacker_dao_id: str | None,
        defender_dao_id: str | None,
    ) -> dict[str, Any] | None:
        """若有克制则返回战报事件。"""
        edge = find_restraint(
            self.restraint_edges(),
            attacker_dao_id=attacker_dao_id,
            defender_dao_id=defender_dao_id,
        )
        if edge is None:
            return None
        return restraint_battle_event(
            edge,
            attacker_label=self.label_of(edge.attacker) or edge.attacker,
            defender_label=self.label_of(edge.defender) or edge.defender,
        )

    async def reset_for_reincarnation(self, character_id: int) -> None:
        """
        轮回：清本命/道值/等级；保留道池；清开道会话与冷却。

        道主卸任由 DaoLordService 同事务处理。化身行若解散则 CASCADE 清化身道。
        """
        result = await self._session.execute(
            select(Character).where(Character.id == character_id),
        )
        character = result.scalar_one_or_none()
        if character is None:
            return
        row = await self._get_or_create_row(character)
        resources = self._resources()
        row.fate_dao_id = None
        row.locked = False
        row.dao_qi = resources.initial_dao_qi
        row.dao_exp = 0
        row.dao_level = 1
        row.opening_session_json = None
        row.challenge_cooldown_until = None
        await self._session.flush()
        logger.info("dao reset for reincarnation character_id=%s", character_id)

    async def gm_force_true_immortal(self, character: Character) -> None:
        """GM：抬至真仙初期。"""
        character.major_realm = "true_immortal"
        character.realm_stage = 1
        character.realm_stage_label = "early"
        if hasattr(character, "peak_major_realm"):
            # peak 取更高：真仙
            character.peak_major_realm = "true_immortal"
        await self._session.flush()

    async def gm_grant_pool(self, character: Character, dao_ids: list[str]) -> dict[str, Any]:
        """GM：灌入道池。"""
        owned = await self._pool_ids(character)
        before = set(owned)
        await self._add_pool_ids(
            character,
            None,
            [d for d in dao_ids if d in self._cfg().entries],
            owned,
        )
        await self._session.flush()
        return {"added": [d for d in dao_ids if d in owned and d not in before], "pool_count": len(owned)}

    async def gm_set_resources(
        self,
        character: Character,
        *,
        dao_qi: int | None = None,
        dao_level: int | None = None,
    ) -> dict[str, Any]:
        """
        GM：直接设道值 / 道等级（按曲线回填累计经验）。

        Args:
            character: 角色。
            dao_qi: 道值；None 不改。
            dao_level: 道等级；None 不改。

        Returns:
            当前道资源摘要。
        """
        row = await self._get_or_create_row(character)
        resources = self._resources()
        if dao_qi is not None:
            row.dao_qi = max(0, int(dao_qi))
        if dao_level is not None:
            level = max(1, int(dao_level))
            curve = list(resources.level_curve) or [0]
            # 升到该级：累计经验至少为 curve[level-1]
            idx = min(level - 1, len(curve) - 1)
            row.dao_exp = int(curve[idx])
            row.dao_level = level
        await self._session.flush()
        # 抬级后空位可自动就任
        try:
            from app.services.dao_lord_service import DaoLordService

            await DaoLordService(self._session).try_auto_inaugurate(character)
        except Exception:  # noqa: BLE001
            logger.exception(
                "auto inaugurate after gm_set_resources failed character_id=%s",
                character.id,
            )
        return {
            "qi": int(row.dao_qi),
            "level": int(row.dao_level),
            "exp": int(row.dao_exp),
        }

    async def gm_lock_fate_dao(
        self,
        character: Character,
        dao_id: str,
        *,
        also_grant_offers: bool = True,
    ) -> dict[str, Any]:
        """
        GM：跳过 roll，直接锁定本命道并入池（联调加速）。

        Args:
            character: 角色。
            dao_id: 本命道。
            also_grant_offers: 为 True 时额外灌入炎/霜/雷三样本，便于池展示。

        Returns:
            道摘要。
        """
        if dao_id not in self._cfg().entries:
            raise AppError(code=40000, message=f"未知大道：{dao_id}", http_status=400)
        row = await self._get_or_create_row(character)
        resources = self._resources()
        row.fate_dao_id = dao_id
        row.locked = True
        row.opening_session_json = None
        if int(row.dao_qi) <= 0:
            row.dao_qi = resources.initial_dao_qi
        owned = await self._pool_ids(character)
        to_add = [dao_id]
        if also_grant_offers:
            for sample in ("dao_flame", "dao_frost", "dao_thunder", dao_id):
                if sample not in to_add:
                    to_add.append(sample)
        await self._add_pool_ids(
            character,
            None,
            [oid for oid in to_add if oid in self._cfg().entries],
            owned,
        )
        await self._session.flush()
        logger.info("gm lock fate dao character_id=%s fate=%s", character.id, dao_id)
        # 空位且等级已达标则自动就任（无需夺位）
        try:
            from app.services.dao_lord_service import DaoLordService

            await DaoLordService(self._session).try_auto_inaugurate(character)
        except Exception:  # noqa: BLE001
            logger.exception(
                "auto inaugurate after gm_lock_fate failed character_id=%s",
                character.id,
            )
        return self.build_me_payload(
            str(character.major_realm or ""),
            row,
            len(owned),
            actor=LOADOUT_ACTOR_MAIN,
        )
