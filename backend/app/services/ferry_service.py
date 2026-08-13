"""
待引渡服务：自救 / 入轮回 / 惰性超时强制轮回（M5 E5）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.user import User
from app.domain.ferry_rules import can_self_rescue, compute_ferry_deadline, is_ferry_timed_out
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class FerryService:
    """
    Application service for awaiting-ferry state machine.

    Attributes:
        _session: Async SQLAlchemy session.
        _gate: Play gate.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: Request-scoped async session.
        """
        self._session = session
        self._gate = PlayGate(session)

    def _countdown_seconds(self) -> int:
        """Resolve ferry countdown from settings-aware config."""
        return int(get_game_config().reincarnation.ferry_countdown_seconds)

    async def enter_awaiting_ferry(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> Character:
        """
        Transition character into awaiting_ferry with deadline.

        Args:
            character: Mutable character.
            now: Fall moment UTC.

        Returns:
            Character: Updated entity.
        """
        current = now_utc(now)
        character.status = "awaiting_ferry"
        character.ferry_deadline_at = compute_ferry_deadline(
            current,
            self._countdown_seconds(),
        )
        character.idle_direction = "none"
        character.updated_at = current
        await self._session.flush()
        logger.info(
            "enter awaiting_ferry character_id=%s deadline=%s",
            character.id,
            character.ferry_deadline_at,
        )
        return character

    async def check_timeout_and_force(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """
        Lazy ferry timeout: if overdue, force reincarnation.

        Args:
            character: Character that may be awaiting ferry.
            now: Current UTC.

        Returns:
            dict: Reincarnation result when forced; else None.
        """
        if character.status != "awaiting_ferry":
            return None
        current = now_utc(now)
        if not is_ferry_timed_out(current, character.ferry_deadline_at):
            return None
        logger.info(
            "ferry timeout force reincarnation character_id=%s",
            character.id,
        )
        from app.services.reincarnation_service import ReincarnationService

        return await ReincarnationService(self._session).apply_reincarnation(
            character,
            path="forced",
            now=current,
        )

    def _ferry_public(
        self,
        character: Character,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Build FerryPublic payload aligned with frontend types.

        Args:
            character: Character in awaiting_ferry.
            now: Optional frozen time.

        Returns:
            dict: ``deadline_at`` / ``can_self_rescue`` / ``self_rescue_cost``.
        """
        cfg = get_game_config().reincarnation
        cost = int(cfg.self_rescue.get("spirit_stone_cost", 500))
        cooldown_total = int(cfg.self_rescue.get("cooldown_seconds", 0))
        current = now_utc(now)
        last_rescue = (
            ensure_aware_utc(character.last_self_rescue_at)
            if character.last_self_rescue_at is not None
            else None
        )
        ok, reason, cooldown_remaining = can_self_rescue(
            status=character.status,
            spirit_stones=int(character.spirit_stones),
            cost=cost,
            last_rescue_at=last_rescue,
            now=current,
            cooldown_seconds=cooldown_total,
        )
        deadline = (
            ensure_aware_utc(character.ferry_deadline_at)
            if character.ferry_deadline_at is not None
            else None
        )
        remaining = None
        if deadline is not None:
            remaining = max(0, int((deadline - current).total_seconds()))
        return {
            "deadline_at": to_utc_iso(deadline) if deadline else None,
            "remaining_seconds": remaining,
            "can_self_rescue": ok,
            "self_rescue_reason": reason or None,
            # 显性：消耗的是灵石，不是抽象点数
            "self_rescue_cost": cost,
            "self_rescue_cost_currency": "spirit_stones",
            "self_rescue_cost_label": "灵石",
            "self_rescue_cooldown_seconds": cooldown_remaining,
            "self_rescue_cooldown_total_seconds": cooldown_total,
            "spirit_stones": int(character.spirit_stones),
            "social_rescue": self._social_rescue_costs_public(),
        }

    def _social_rescue_costs_public(self) -> dict[str, Any]:
        """道友/同门/亲友引渡成本摘要（与自救对比）。"""
        cfg = get_game_config().reincarnation
        social = dict(getattr(cfg, "social_rescue", None) or {})
        friend = dict(social.get("friend") or {})
        kin = dict(social.get("kin") or {})
        sect = dict(social.get("sect") or {})
        self_cost = int(cfg.self_rescue.get("spirit_stone_cost", 500))
        friend_cost = int(friend.get("spirit_stone_cost", 100))
        kin_cost = int(kin.get("spirit_stone_cost", friend_cost))
        sect_cost = int(sect.get("spirit_stone_cost", 150))
        return {
            "same_region_stub": bool(social.get("same_region_stub", True)),
            "friend_cost": friend_cost,
            "kin_cost": kin_cost,
            "sect_cost": sect_cost,
            "self_rescue_cost": self_cost,
            "friend_cheaper_by": max(0, self_cost - friend_cost),
            "kin_cheaper_by": max(0, self_cost - kin_cost),
            "sect_cheaper_by": max(0, self_cost - sect_cost),
            "payer_label_zh": "救援者支付灵石",
        }

    async def list_rescue_targets(
        self,
        user: User,
        *,
        category: str = "universal",
    ) -> dict[str, Any]:
        """
        List awaiting-ferry targets for the rescue panel tabs.

        Categories:
            ``universal`` (普渡众生): friends awaiting ferry.
            ``sect`` (同门引渡): same-sect members awaiting ferry.
            ``kin`` (亲友引渡): friends / companions / mentors / vessels.

        Args:
            user: Authenticated rescuer.
            category: universal | sect | kin.

        Returns:
            ``category``, ``items``, and cost summary.
        """
        from sqlalchemy import or_, select

        from app.db.models.bond import (
            BOND_KIND_COMPANION,
            BOND_KIND_VESSEL,
            CharacterBond,
        )
        from app.db.models.mentor import MentorBond
        from app.services.friend_service import FriendService
        from app.services.realm_config import get_major_realm

        character = await self._gate.require_character(user)
        cat = str(category or "universal").strip().lower()
        if cat in {"pudu", "friend", "friends"}:
            cat = "universal"
        if cat in {"close", "kinfolk", "family"}:
            cat = "kin"
        if cat not in {"universal", "sect", "kin"}:
            raise AppError(
                code=40000,
                message="类别须为普渡众生 / 同门 / 亲友",
                http_status=400,
            )

        peer_meta: dict[int, set[str]] = {}

        def _add(peer_id: int, relation: str) -> None:
            if int(peer_id) == int(character.id):
                return
            peer_meta.setdefault(int(peer_id), set()).add(relation)

        if cat in {"universal", "kin"}:
            friends_payload = await FriendService(self._session).list_friends(user)
            for f in friends_payload.get("friends") or []:
                _add(int(f["peer_character_id"]), "friend")

        if cat == "sect":
            if character.sect_id is not None:
                rows = (
                    await self._session.execute(
                        select(Character).where(
                            Character.sect_id == int(character.sect_id),
                            Character.id != int(character.id),
                            Character.status == "awaiting_ferry",
                        ),
                    )
                ).scalars().all()
                for ch in rows:
                    _add(int(ch.id), "sect")

        if cat == "kin":
            bond_rows = (
                await self._session.execute(
                    select(CharacterBond).where(
                        CharacterBond.status == "active",
                        CharacterBond.bond_kind.in_(
                            (BOND_KIND_COMPANION, BOND_KIND_VESSEL),
                        ),
                        or_(
                            CharacterBond.character_low_id == character.id,
                            CharacterBond.character_high_id == character.id,
                        ),
                    ),
                )
            ).scalars().all()
            for row in bond_rows:
                peer_id = (
                    row.character_high_id
                    if int(row.character_low_id) == int(character.id)
                    else row.character_low_id
                )
                rel = "companion" if row.bond_kind == BOND_KIND_COMPANION else "vessel"
                _add(int(peer_id), rel)

            mentor_rows = (
                await self._session.execute(
                    select(MentorBond).where(
                        MentorBond.status == "active",
                        or_(
                            MentorBond.master_character_id == character.id,
                            MentorBond.apprentice_character_id == character.id,
                        ),
                    ),
                )
            ).scalars().all()
            for bond in mentor_rows:
                peer_id = (
                    bond.apprentice_character_id
                    if int(bond.master_character_id) == int(character.id)
                    else bond.master_character_id
                )
                role = (
                    "disciple"
                    if int(bond.master_character_id) == int(character.id)
                    else "master"
                )
                _add(int(peer_id), role)

        # 普渡/亲友：仅保留 awaiting_ferry
        items: list[dict[str, Any]] = []
        if cat == "sect":
            # already filtered to awaiting_ferry when collecting
            peer_ids = list(peer_meta.keys())
        else:
            peer_ids = list(peer_meta.keys())

        if peer_ids:
            chars = (
                await self._session.execute(
                    select(Character).where(Character.id.in_(peer_ids)),
                )
            ).scalars().all()
            by_id = {int(c.id): c for c in chars}
            for pid in peer_ids:
                ch = by_id.get(int(pid))
                if ch is None:
                    continue
                await self.check_timeout_and_force(ch)
                if ch.status != "awaiting_ferry":
                    continue
                relations = sorted(peer_meta.get(int(pid)) or [])
                mr = get_major_realm(str(ch.major_realm or ""))
                rescue_mode = "sect" if cat == "sect" else ("kin" if cat == "kin" else "friend")
                items.append(
                    {
                        "character_id": ch.id,
                        "name": ch.name,
                        "major_realm": ch.major_realm,
                        "major_realm_name": mr.name if mr else ch.major_realm,
                        "relations": relations,
                        "relation_labels_zh": [
                            _relation_label_zh(r) for r in relations
                        ],
                        "deadline_at": (
                            to_utc_iso(ensure_aware_utc(ch.ferry_deadline_at))
                            if ch.ferry_deadline_at is not None
                            else None
                        ),
                        "rescue_mode": rescue_mode,
                    },
                )

        items.sort(key=lambda x: (x.get("deadline_at") or "", x["name"]))
        label_zh = {
            "universal": "普渡众生",
            "sect": "同门引渡",
            "kin": "亲友引渡",
        }[cat]
        return {
            "category": cat,
            "category_label_zh": label_zh,
            "items": items,
            "costs": self._social_rescue_costs_public(),
        }

    async def social_rescue(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
        mode: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        道友 / 同门 / 亲友引渡（救援者支付较低灵石）。

        Args:
            user: 救援者。
            target_character_id: 待救角色 id。
            target_name: 待救道号。
            mode: friend | sect | kin。
            now: 可选冻结时间。

        Returns:
            dict: 救援结果。
        """
        from sqlalchemy import and_, or_, select

        from app.db.models.bond import (
            BOND_KIND_COMPANION,
            BOND_KIND_VESSEL,
            CharacterBond,
        )
        from app.db.models.mentor import MentorBond
        from app.domain.mentor_rules import realm_index, same_region_stub
        from app.services.currency_ledger_service import CurrencyLedgerService
        from app.services.friend_service import FriendService

        rescuer, _ = await self._gate.prepare_for_play(user, settle=True)
        mode_l = str(mode or "").strip().lower()
        if mode_l not in {"friend", "sect", "kin"}:
            raise AppError(
                code=40000,
                message="引渡方式须为普渡/道友、同门或亲友",
                http_status=400,
            )

        # 解析目标
        if target_character_id is not None:
            victim = await self._session.get(Character, int(target_character_id))
        else:
            nm = (target_name or "").strip()
            if not nm:
                raise AppError(code=40000, message="请提供待救角色 id 或道号", http_status=400)
            victim = (
                await self._session.execute(select(Character).where(Character.name == nm))
            ).scalar_one_or_none()
        if victim is None:
            raise AppError(code=40000, message="待救角色不存在", http_status=404)
        if victim.id == rescuer.id:
            raise AppError(code=40000, message="不可救援自己（请用自救）", http_status=400)

        await self.check_timeout_and_force(victim, now=now)
        if victim.status != "awaiting_ferry":
            raise AppError(code=40067, message="对方非待引渡状态", http_status=400)

        cfg = get_game_config().reincarnation
        social = dict(getattr(cfg, "social_rescue", None) or {})
        settings = get_settings()
        stub = bool(social.get("same_region_stub", True))
        if hasattr(settings, "same_region_stub"):
            stub = bool(settings.same_region_stub)
        if not same_region_stub(stub_enabled=stub):
            raise AppError(code=40180, message="同图判定失败（未同区）", http_status=400)

        mode_label = "道友引渡"
        if mode_l == "friend":
            ok = await FriendService(self._session).are_friends(rescuer.id, victim.id)
            if not ok:
                raise AppError(code=40180, message="仅道友可发起普渡/道友引渡", http_status=403)
            cost = int((social.get("friend") or {}).get("spirit_stone_cost", 100))
            mode_label = "普渡众生"
        elif mode_l == "kin":
            linked = await FriendService(self._session).are_friends(rescuer.id, victim.id)
            if not linked:
                bond = (
                    await self._session.execute(
                        select(CharacterBond.id).where(
                            CharacterBond.status == "active",
                            CharacterBond.bond_kind.in_(
                                (BOND_KIND_COMPANION, BOND_KIND_VESSEL),
                            ),
                            or_(
                                and_(
                                    CharacterBond.character_low_id == rescuer.id,
                                    CharacterBond.character_high_id == victim.id,
                                ),
                                and_(
                                    CharacterBond.character_low_id == victim.id,
                                    CharacterBond.character_high_id == rescuer.id,
                                ),
                            ),
                        ).limit(1),
                    )
                ).scalar_one_or_none()
                linked = bond is not None
            if not linked:
                mentor = (
                    await self._session.execute(
                        select(MentorBond.id).where(
                            MentorBond.status == "active",
                            or_(
                                and_(
                                    MentorBond.master_character_id == rescuer.id,
                                    MentorBond.apprentice_character_id == victim.id,
                                ),
                                and_(
                                    MentorBond.master_character_id == victim.id,
                                    MentorBond.apprentice_character_id == rescuer.id,
                                ),
                            ),
                        ).limit(1),
                    )
                ).scalar_one_or_none()
                linked = mentor is not None
            if not linked:
                raise AppError(
                    code=40180,
                    message="仅道友、道侣、师徒或炉鼎可发起亲友引渡",
                    http_status=403,
                )
            friend_cost = int((social.get("friend") or {}).get("spirit_stone_cost", 100))
            cost = int((social.get("kin") or {}).get("spirit_stone_cost", friend_cost))
            mode_label = "亲友引渡"
        else:
            if rescuer.sect_id is None or victim.sect_id is None:
                raise AppError(code=40180, message="双方须同宗", http_status=403)
            if int(rescuer.sect_id) != int(victim.sect_id):
                raise AppError(code=40180, message="非同门不可宗门引渡", http_status=403)
            sect_cfg = dict(social.get("sect") or {})
            if bool(sect_cfg.get("require_higher_realm", True)):
                order = list(get_game_config().realms.keys())
                if realm_index(str(rescuer.major_realm), order) <= realm_index(
                    str(victim.major_realm),
                    order,
                ):
                    raise AppError(
                        code=40180,
                        message="宗门引渡须由修为更高的同门发起",
                        http_status=403,
                    )
            cost = int(sect_cfg.get("spirit_stone_cost", 150))
            mode_label = "同门引渡"

        current = now_utc(now)
        await CurrencyLedgerService(self._session).adjust_spirit_stones(
            rescuer,
            delta=-cost,
            reason="ferry_social_rescue",
            note_zh=f"{mode_label}·{victim.name}",
            ref_type="ferry",
            ref_id=str(victim.id),
        )
        victim.status = "normal"
        victim.ferry_deadline_at = None
        victim.updated_at = current
        await self._session.flush()
        logger.info(
            "social_rescue mode=%s rescuer=%s victim=%s cost=%s",
            mode_l,
            rescuer.id,
            victim.id,
            cost,
        )
        return {
            "rescued": True,
            "mode": mode_l,
            "mode_label_zh": mode_label,
            "spirit_stones_spent": cost,
            "payer": "rescuer",
            "victim_character_id": victim.id,
            "victim_name": victim.name,
            "message": (
                f"已引渡「{victim.name}」，消耗灵石 {cost}"
                f"（自救需 {int(cfg.self_rescue.get('spirit_stone_cost', 500))}）"
            ),
            "character": await self._character_dict(rescuer),
            "victim_character": await self._character_dict(victim),
        }

    async def _character_dict(self, character: Character) -> dict[str, Any]:
        """Enrich character for mutation responses."""
        from app.services.character_service import CharacterService, character_public_to_dict

        # flush 后 ORM 属性过期；先 refresh 再序列化，避免 MissingGreenlet
        await self._session.refresh(character)
        public = await CharacterService(self._session).enrich_public(character)
        return character_public_to_dict(public)

    async def get_me(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Return ferry status for current character (runs lazy timeout).

        成功路径同时给出顶层 FerryPublic 字段（便于前端直读）与嵌套 ``ferry``。

        Args:
            user: Authenticated user.
            now: Optional frozen time.

        Returns:
            dict: Ferry panel payload.
        """
        character = await self._gate.require_character(user)
        forced = await self.check_timeout_and_force(character, now=now)
        if forced is not None:
            return {
                "status": "reincarnated",
                "forced_reincarnation": forced,
                "ferry": None,
                "character": await self._character_dict(character),
                "message": "引渡超时，已强制轮回，请完成新生选角",
                "needs_newborn_setup": True,
            }

        if character.status != "awaiting_ferry":
            # 非待引渡也返回社交引渡成本摘要，供救援者在 /social?mode=ferry 对照
            return {
                "status": character.status,
                "ferry": None,
                "social_rescue": self._social_rescue_costs_public(),
            }

        ferry_payload = self._ferry_public(character, now=now)
        # 顶层展开 + 嵌套 ferry：兼容直读 deadline_at 与 { ferry: {...} } 两种客户端
        return {
            "status": "awaiting_ferry",
            "ferry": ferry_payload,
            **ferry_payload,
        }

    async def self_rescue(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Spend spirit stones to leave awaiting_ferry → normal.

        Args:
            user: Authenticated user.
            now: Optional frozen time.

        Returns:
            dict: Updated ferry/character summary.

        Raises:
            AppError: ``40066`` / ``40067``.
        """
        character = await self._gate.require_character(user)
        await self.check_timeout_and_force(character, now=now)
        if character.status != "awaiting_ferry":
            raise AppError(code=40067, message="非待引渡不可自救", http_status=400)

        cfg = get_game_config().reincarnation
        cost = int(cfg.self_rescue.get("spirit_stone_cost", 500))
        current = now_utc(now)
        last_rescue = (
            ensure_aware_utc(character.last_self_rescue_at)
            if character.last_self_rescue_at is not None
            else None
        )
        ok, reason, _cooldown_remaining = can_self_rescue(
            status=character.status,
            spirit_stones=int(character.spirit_stones),
            cost=cost,
            last_rescue_at=last_rescue,
            now=current,
            cooldown_seconds=int(cfg.self_rescue.get("cooldown_seconds", 0)),
        )
        if not ok:
            raise AppError(code=40066, message=reason or "自救条件不满足", http_status=400)

        character.spirit_stones = int(character.spirit_stones) - cost
        character.status = "normal"
        character.ferry_deadline_at = None
        character.last_self_rescue_at = current
        character.updated_at = current
        await self._session.flush()
        logger.info("self_rescue character_id=%s cost=%s", character.id, cost)
        return {
            "rescued": True,
            "spirit_stones_spent": cost,
            "status": character.status,
            "ferry": None,
            "message": f"自救成功，消耗灵石 {cost}",
            "character": await self._character_dict(character),
        }

    async def enter_reincarnation(
        self,
        user: User,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Player-chosen reincarnation from awaiting_ferry.

        Args:
            user: Authenticated user.
            now: Optional frozen time.

        Returns:
            dict: Reincarnation result with ``character`` for frontend apply.
        """
        character = await self._gate.require_character(user)
        await self.check_timeout_and_force(character, now=now)
        if character.status != "awaiting_ferry":
            raise AppError(code=40067, message="非待引渡不可入轮回", http_status=400)

        from app.services.reincarnation_service import ReincarnationService

        result = await ReincarnationService(self._session).apply_reincarnation(
            character,
            path="voluntary_ferry",
            now=now,
        )
        result["ferry"] = None
        result["reincarnated"] = True
        result["needs_newborn_setup"] = True
        result["message"] = "自选轮回已结算，请前往新生页选择灵根/传承"
        result["character"] = await self._character_dict(character)
        return result


def _relation_label_zh(relation: str) -> str:
    """Map internal relation key to Chinese label for rescue lists."""
    return {
        "friend": "道友",
        "sect": "同门",
        "companion": "道侣",
        "vessel": "炉鼎",
        "master": "师父",
        "disciple": "弟子",
    }.get(str(relation), str(relation))
