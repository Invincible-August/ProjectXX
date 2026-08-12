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

from app.core.config import get_settings
from app.db.models import Character, CharacterDao, DaoPoolEntry, User
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
            raise AppError(code=40094, message="大道系统未开启", http_status=403)

    def _cfg(self):
        return get_game_config().dao

    def _open_rules(self) -> DaoOpenRules:
        open_cfg = self._cfg().open
        return DaoOpenRules(
            min_major_realm=str(open_cfg.get("min_major_realm") or "true_immortal"),
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

    async def _get_or_create_row(self, character_id: int) -> CharacterDao:
        """获取或创建角色大道行。"""
        result = await self._session.execute(
            select(CharacterDao).where(CharacterDao.character_id == character_id),
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        resources = self._resources()
        row = CharacterDao(
            character_id=character_id,
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

    async def _pool_ids(self, character_id: int) -> set[str]:
        result = await self._session.execute(
            select(DaoPoolEntry.dao_id).where(DaoPoolEntry.character_id == character_id),
        )
        return {str(x) for x in result.scalars().all()}

    async def _pool_count(self, character_id: int) -> int:
        return len(await self._pool_ids(character_id))

    def _can_open(self, character: Character, row: CharacterDao) -> bool:
        rules = self._open_rules()
        if row.locked and row.fate_dao_id:
            return False
        return meets_min_major_realm(str(character.major_realm or ""), rules.min_major_realm)

    def build_me_payload(self, character: Character, row: CharacterDao, pool_count: int) -> dict[str, Any]:
        """构造 /dao/me 与 CharacterPublic.dao。"""
        resources = self._resources()
        level, exp_into, exp_to_next = resolve_dao_level(int(row.dao_exp), resources.level_curve)
        # 以解析等级为准（防脏数据）
        fate_id = row.fate_dao_id
        return {
            "fate_dao_id": fate_id,
            "fate_dao_label": self.label_of(fate_id),
            "qi": int(row.dao_qi),
            "level": int(level),
            "exp": int(row.dao_exp),
            "exp_into_level": int(exp_into),
            "exp_to_next": exp_to_next,
            "pool_count": int(pool_count),
            "can_open": self._can_open(character, row),
            "locked": bool(row.locked and fate_id),
        }

    async def enrich_dao_summary(self, character: Character) -> dict[str, Any] | None:
        """嵌入 CharacterPublic；系统关闭仍返回只读摘要。"""
        if not get_settings().dao_system_enabled:
            return None
        row = await self._get_or_create_row(character.id)
        count = await self._pool_count(character.id)
        return self.build_me_payload(character, row, count)

    async def get_catalog(self, user: User) -> dict[str, Any]:
        """图鉴（未真仙也可只读）。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        owned = await self._pool_ids(character.id)
        entries = self._entries()
        items = [
            catalog_entry_public(entry, owned=entry.dao_id in owned)
            for entry in entries.values()
        ]
        return {"items": items, "entries": items, "total": len(items), "count": len(items)}

    async def get_me(self, user: User) -> dict[str, Any]:
        """本命与道资源。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        row = await self._get_or_create_row(character.id)
        count = await self._pool_count(character.id)
        return self.build_me_payload(character, row, count)

    async def get_pool(self, user: User) -> dict[str, Any]:
        """道池列表。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
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
        return {"items": items, "entries": items, "total": len(items), "count": len(items)}

    def _parse_opening(self, row: CharacterDao) -> dict[str, Any] | None:
        if not row.opening_session_json:
            return None
        try:
            data = json.loads(row.opening_session_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return data

    async def roll_open(self, user: User) -> dict[str, Any]:
        """
        生成开道三选项会话。

        Raises:
            AppError: 40080/40081/40095/40096 等。
        """
        self._require_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        # 渡劫/引渡等已由 prepare 拦截；额外禁挑战中由 lord 服务处理
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可开道", http_status=409)
        rules = self._open_rules()
        if not meets_min_major_realm(str(character.major_realm or ""), rules.min_major_realm):
            raise AppError(code=40080, message="未达真仙不可开道", http_status=400)
        row = await self._get_or_create_row(character.id)
        if row.locked and row.fate_dao_id:
            raise AppError(code=40081, message="本周目已锁定本命道", http_status=400)
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
                    code=40096,
                    message="已有开道会话，禁止重复抽取；请先确认或等待会话过期",
                    http_status=400,
                )

        owned = await self._pool_ids(character.id)
        entries = self._entries()
        weights = build_candidate_weights(entries, owned_dao_ids=owned)
        weights = backfill_candidates_if_short(
            weights,
            entries,
            owned_dao_ids=owned,
            need=rules.picks,
        )
        if len(weights) < rules.picks:
            raise AppError(code=40095, message="候选道不足三次抽取", http_status=400)

        picked = pick_unique_weighted(
            weights,
            count=rules.picks,
            weighted_pick=self._dice.weighted_pick,
        )
        if len(picked) < rules.picks:
            raise AppError(code=40095, message="候选道不足三次抽取", http_status=400)

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
            "dao open roll character_id=%s session=%s options=%s",
            character.id,
            session_id,
            picked,
        )
        options_public = [
            catalog_entry_public(entries[dao_id], owned=dao_id in owned)
            for dao_id in picked
            if dao_id in entries
        ]
        return {
            "session_id": session_id,
            "options": options_public,
            "allow_pool_pick": allow_pool_pick,
            "expires_at": session_payload["expires_at"],
            "hint": "抽出的三道将全部录入道池，跨轮回保留；本周目本命道选定后不可更改",
        }

    async def choose_open(self, user: User, *, dao_id: str, session_id: str | None = None) -> dict[str, Any]:
        """
        确认本命道并入池。

        Args:
            user: 当前用户。
            dao_id: 选定道。
            session_id: 可选校验会话 id。
        """
        self._require_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可开道", http_status=409)
        row = await self._get_or_create_row(character.id)
        if row.locked and row.fate_dao_id:
            raise AppError(code=40081, message="本周目已锁定本命道", http_status=400)
        opening = self._parse_opening(row)
        if not opening:
            raise AppError(code=40082, message="开道会话不存在或已过期", http_status=400)
        if session_id and str(opening.get("session_id")) != str(session_id):
            raise AppError(code=40082, message="开道会话不存在或已过期", http_status=400)
        expires = opening.get("expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= exp_dt:
                    row.opening_session_json = None
                    await self._session.flush()
                    raise AppError(code=40082, message="开道会话不存在或已过期", http_status=400)
            except ValueError:
                pass

        offer_ids = [str(x) for x in list(opening.get("options") or [])]
        allow_pool = bool(opening.get("allow_pool_pick"))
        owned = await self._pool_ids(character.id)
        if not is_valid_open_choice(
            chosen_dao_id=dao_id,
            offer_ids=offer_ids,
            allow_pool_pick=allow_pool,
            pool_ids=owned,
        ):
            raise AppError(code=40083, message="非法选择：非本次三选项且非合法道池自选", http_status=400)
        if dao_id not in self._cfg().entries and dao_id not in owned:
            raise AppError(code=40083, message="非法选择：未知大道", http_status=400)

        resources = self._resources()
        # 事务：锁定本命；三抽入池；初始化资源（若首次）
        row.fate_dao_id = dao_id
        row.locked = True
        row.opening_session_json = None
        if int(row.dao_qi) <= 0 and int(row.dao_exp) == 0:
            row.dao_qi = resources.initial_dao_qi
            row.dao_exp = 0
            row.dao_level = 1
        level, _, _ = resolve_dao_level(int(row.dao_exp), resources.level_curve)
        row.dao_level = level

        # 本次三抽全部入池（upsert）
        for oid in offer_ids:
            if oid in owned:
                continue
            self._session.add(DaoPoolEntry(character_id=character.id, dao_id=oid))
            owned.add(oid)
        # 若选自旧藏，本命已在池中；仍确保存在
        if dao_id not in owned:
            self._session.add(DaoPoolEntry(character_id=character.id, dao_id=dao_id))
            owned.add(dao_id)

        await self._session.flush()
        logger.info(
            "dao open choose character_id=%s fate=%s pool_added=%s",
            character.id,
            dao_id,
            offer_ids,
        )
        # 空位且达标则自动就任道主（无需夺位）
        try:
            from app.services.dao_lord_service import DaoLordService

            await DaoLordService(self._session).try_auto_inaugurate(character)
        except Exception:  # noqa: BLE001
            logger.exception("auto inaugurate after open failed character_id=%s", character.id)

        from app.services.character_service import CharacterService

        public = await CharacterService(self._session).enrich_public(character)
        return {
            "dao": self.build_me_payload(character, row, len(owned)),
            "character": CharacterService.public_to_dict(public),
            "message": f"开道成功：{self.label_of(dao_id)}",
        }

    async def preview_usage(self, user: User, *, kind: str) -> dict[str, Any]:
        """预览战斗/工坊运用消耗与效果。"""
        self._require_enabled()
        character = await self._gate.require_character(user)
        row = await self._get_or_create_row(character.id)
        if not row.fate_dao_id:
            raise AppError(code=40085, message="尚未开辟本命道，不可运用", http_status=400)
        if kind not in ("battle", "craft"):
            raise AppError(code=40000, message="kind 须为 battle 或 craft", http_status=400)
        branch = self.usage_branch(kind)
        return {
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
    ) -> dict[str, Any]:
        """
        战斗/工坊成功路径扣道值涨经验（内部调用）。

        Raises:
            AppError: 40084/40085。
        """
        self._require_enabled()
        row = await self._get_or_create_row(character.id)
        if not row.fate_dao_id:
            raise AppError(code=40085, message="尚未开辟本命道，不可运用", http_status=400)
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
            raise AppError(code=40084, message="道值不足", http_status=400) from exc
        row.dao_qi = result.qi_after
        row.dao_exp = result.exp_after
        row.dao_level = result.level_after
        await self._session.flush()
        logger.info(
            "dao usage character_id=%s kind=%s cost=%s exp=%s level=%s→%s",
            character.id,
            kind,
            result.qi_cost,
            result.exp_gain,
            result.level_before,
            result.level_after,
        )
        if result.leveled_up:
            try:
                from app.services.dao_lord_service import DaoLordService

                await DaoLordService(self._session).try_auto_inaugurate(character)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "auto inaugurate after usage failed character_id=%s",
                    character.id,
                )
        return {
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

        道主卸任由 DaoLordService 同事务处理。
        """
        row = await self._get_or_create_row(character_id)
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
        owned = await self._pool_ids(character.id)
        added = []
        for dao_id in dao_ids:
            if dao_id not in self._cfg().entries:
                continue
            if dao_id in owned:
                continue
            self._session.add(DaoPoolEntry(character_id=character.id, dao_id=dao_id))
            owned.add(dao_id)
            added.append(dao_id)
        await self._session.flush()
        return {"added": added, "pool_count": len(owned)}

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
        row = await self._get_or_create_row(character.id)
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
        row = await self._get_or_create_row(character.id)
        resources = self._resources()
        row.fate_dao_id = dao_id
        row.locked = True
        row.opening_session_json = None
        if int(row.dao_qi) <= 0:
            row.dao_qi = resources.initial_dao_qi
        owned = await self._pool_ids(character.id)
        to_add = [dao_id]
        if also_grant_offers:
            for sample in ("dao_flame", "dao_frost", "dao_thunder", dao_id):
                if sample not in to_add:
                    to_add.append(sample)
        for oid in to_add:
            if oid in owned or oid not in self._cfg().entries:
                continue
            self._session.add(DaoPoolEntry(character_id=character.id, dao_id=oid))
            owned.add(oid)
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
        return self.build_me_payload(character, row, len(owned))
