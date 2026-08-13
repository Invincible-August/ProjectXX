"""
道侣 / 炉鼎关系服务。

道侣：申请 / 接受 / 拒绝 / 解除（同道友流程，含 WS 提示）。
炉鼎：面交成交建立/延长；一炉一主；主人可随时解除；到期惰性解除。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.bond import (
    BOND_KIND_COMPANION,
    BOND_KIND_VESSEL,
    VALID_BOND_KINDS,
    CharacterBond,
)
from app.domain.trade_rules import friendship_pair_key
from app.domain.ws_protocol import TYPE_BOND_REQUEST, TYPE_BOND_UPDATE
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)


def require_friends_enabled() -> None:
    """复用道友总闸（道侣/炉鼎挂在社交关系下）。"""
    settings = get_settings()
    if not bool(getattr(settings, "friends_system_enabled", True)):
        raise AppError(code=40000, message="道友系统未开放", http_status=403)


class BondService:
    """道侣 / 炉鼎用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """注入 DB 会话。"""
        self._session = session
        self._gate = PlayGate(session)

    def _cfg(self):
        return get_game_config().friends

    def _max_for(self, bond_kind: str) -> int:
        cfg = self._cfg()
        if bond_kind == BOND_KIND_COMPANION:
            return int(getattr(cfg, "max_companions", None) or cfg.max_friends)
        return int(getattr(cfg, "max_vessels", None) or 10)

    async def _push_to_character(
        self,
        character_id: int,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Push bond WS envelope to a character's live connections."""
        settings = get_settings()
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        try:
            await get_ws_hub().send_to_character(int(character_id), msg_type, payload)
        except Exception:  # noqa: BLE001
            logger.debug(
                "bond ws push skipped character_id=%s type=%s",
                character_id,
                msg_type,
                exc_info=True,
            )

    def _event_payload(
        self,
        *,
        event: str,
        bond_id: int,
        bond_kind: str,
        from_id: int,
        from_name: str,
        to_id: int,
        to_name: str,
        message: str,
    ) -> dict[str, Any]:
        """Build bond.request / bond.update payload."""
        return {
            "event": event,
            "bond_id": int(bond_id),
            "bond_kind": bond_kind,
            "from_character_id": int(from_id),
            "from_name": from_name,
            "to_character_id": int(to_id),
            "to_name": to_name,
            "message": message,
        }

    def _vessel_owner_id(self, row: CharacterBond) -> int:
        """Resolve vessel master id (owner column, else requester fallback)."""
        owner = getattr(row, "owner_character_id", None)
        if owner is not None:
            return int(owner)
        return int(row.requester_id)

    async def list_bonds(self, user: User) -> dict[str, Any]:
        """
        道侣 / 炉鼎 / 主人列表与待处理申请。

        Returns:
            companions / vessels（我为主人）/ my_master（我为炉鼎，唯一或 null）等。
        """
        require_friends_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        rows = (
            await self._session.execute(
                select(CharacterBond).where(
                    or_(
                        CharacterBond.character_low_id == character.id,
                        CharacterBond.character_high_id == character.id,
                    ),
                ),
            )
        ).scalars().all()
        companions: list[dict[str, Any]] = []
        vessels: list[dict[str, Any]] = []
        companion_incoming: list[dict[str, Any]] = []
        companion_outgoing: list[dict[str, Any]] = []
        my_master: dict[str, Any] | None = None
        for row in rows:
            peer_id = (
                row.character_high_id
                if row.character_low_id == character.id
                else row.character_low_id
            )
            peer = await self._session.get(Character, peer_id)
            item = await self._bond_item(row, character.id, peer)
            if row.bond_kind == BOND_KIND_COMPANION:
                if row.status == "active":
                    companions.append(item)
                elif row.status == "pending":
                    if row.requester_id == character.id:
                        companion_outgoing.append(item)
                    else:
                        companion_incoming.append(item)
            elif row.bond_kind == BOND_KIND_VESSEL and row.status == "active":
                owner_id = self._vessel_owner_id(row)
                if int(owner_id) == int(character.id):
                    vessels.append(item)
                elif my_master is None:
                    # 我是炉鼎：对方即主人（唯一）
                    my_master = item
        return {
            "companions": companions,
            "vessels": vessels,
            "my_master": my_master,
            "companion_incoming": companion_incoming,
            "companion_outgoing": companion_outgoing,
            "companion_count": len(companions),
            "vessel_count": len(vessels),
            "max_companions": self._max_for(BOND_KIND_COMPANION),
            "max_vessels": self._max_for(BOND_KIND_VESSEL),
            "vessel_min_hours": int(self._cfg().vessel_min_hours),
            "vessel_max_hours": int(self._cfg().vessel_max_hours),
            "vessel_invite_enabled": False,
            "vessel_hint_zh": "炉鼎经由面交要约建立/延长；不可直接邀请添加",
        }

    async def apply_companion(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
    ) -> dict[str, Any]:
        """发起道侣申请（可接受/拒绝）。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        target = await self._resolve_target(target_character_id, target_name)
        if target.id == character.id:
            raise AppError(code=40000, message="不可与自己结为道侣", http_status=400)
        await self._expire_stale()
        return await self._apply_bond(
            character,
            target,
            bond_kind=BOND_KIND_COMPANION,
            label_zh="道侣",
        )

    async def apply_vessel(
        self,
        user: User,
        *,
        target_character_id: int | None = None,
        target_name: str | None = None,
    ) -> dict[str, Any]:
        """炉鼎申请口子：当前一律拒绝（后续玩法开放）。"""
        require_friends_enabled()
        await self._gate.require_character(user)
        raise AppError(
            code=40000,
            message="炉鼎不可直接邀请添加，请在面交中要约成为对方炉鼎",
            http_status=400,
        )

    async def accept(self, user: User, bond_id: int) -> dict[str, Any]:
        """确认道侣申请。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(CharacterBond, bond_id)
        if row is None or row.status != "pending":
            raise AppError(code=40000, message="申请不存在或已处理", http_status=400)
        if row.bond_kind != BOND_KIND_COMPANION:
            raise AppError(code=40000, message="仅道侣申请可确认", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权处理该申请", http_status=403)
        if row.requester_id == character.id:
            raise AppError(code=40000, message="不可确认自己发出的申请", http_status=400)
        if await self._active_count(character.id, BOND_KIND_COMPANION) >= self._max_for(
            BOND_KIND_COMPANION,
        ):
            raise AppError(code=40000, message="己方道侣已达上限", http_status=400)
        peer_id = (
            row.character_high_id
            if row.character_low_id == character.id
            else row.character_low_id
        )
        if await self._active_count(peer_id, BOND_KIND_COMPANION) >= self._max_for(
            BOND_KIND_COMPANION,
        ):
            raise AppError(code=40000, message="对方道侣已达上限", http_status=400)
        if await self.get_active_vessel_between(character.id, peer_id) is not None:
            raise AppError(
                code=40000,
                message="双方已是主从炉鼎，不可再结为道侣",
                http_status=400,
            )
        row.status = "active"
        row.accepted_at = now_utc()
        await self._session.flush()
        peer = await self._session.get(Character, peer_id)
        peer_name = peer.name if peer else str(peer_id)
        await self._push_to_character(
            int(row.requester_id),
            TYPE_BOND_UPDATE,
            self._event_payload(
                event="accepted",
                bond_id=row.id,
                bond_kind=row.bond_kind,
                from_id=character.id,
                from_name=character.name,
                to_id=int(row.requester_id),
                to_name=peer_name,
                message=f"「{character.name}」已同意与你结为道侣",
            ),
        )
        return {
            "message": f"已与「{peer_name}」结为道侣",
            "bond_id": row.id,
            "bond_kind": row.bond_kind,
            "companion_count": await self._active_count(character.id, BOND_KIND_COMPANION),
        }

    async def reject(self, user: User, bond_id: int) -> dict[str, Any]:
        """拒绝道侣申请。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(CharacterBond, bond_id)
        if row is None or row.status != "pending":
            raise AppError(code=40000, message="申请不存在或已处理", http_status=400)
        if row.bond_kind != BOND_KIND_COMPANION:
            raise AppError(code=40000, message="仅道侣申请可拒绝", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权处理该申请", http_status=403)
        if row.requester_id == character.id:
            raise AppError(code=40000, message="请解除或取消，而非拒绝自己的申请", http_status=400)
        requester_id = int(row.requester_id)
        row.status = "rejected"
        await self._session.flush()
        await self._push_to_character(
            requester_id,
            TYPE_BOND_UPDATE,
            self._event_payload(
                event="rejected",
                bond_id=row.id,
                bond_kind=row.bond_kind,
                from_id=character.id,
                from_name=character.name,
                to_id=requester_id,
                to_name="",
                message=f"「{character.name}」已拒绝你的道侣申请",
            ),
        )
        return {"message": "已拒绝道侣申请", "bond_id": row.id}

    async def remove(self, user: User, bond_id: int) -> dict[str, Any]:
        """解除道侣（双方可）或炉鼎（仅主人可随时解除）。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._session.get(CharacterBond, bond_id)
        if row is None or row.status != "active":
            raise AppError(code=40000, message="关系不存在", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权解除", http_status=403)
        kind = row.bond_kind
        if kind == BOND_KIND_VESSEL:
            owner_id = self._vessel_owner_id(row)
            if int(character.id) != int(owner_id):
                raise AppError(
                    code=40000,
                    message="仅主人可解除炉鼎关系",
                    http_status=403,
                )
            label = "炉鼎"
        else:
            label = "道侣"
        row.status = "cancelled"
        row.expires_at = None
        await self._session.flush()
        return {"message": f"已解除{label}关系", "bond_id": row.id, "bond_kind": kind}

    async def require_active_bond(
        self,
        character_id: int,
        peer_id: int,
        bond_kind: str,
    ) -> CharacterBond:
        """
        校验双方存在指定 active 关系。

        Args:
            character_id: 甲方。
            peer_id: 乙方。
            bond_kind: companion|vessel。

        Returns:
            关系行。

        Raises:
            AppError: 无关系。
        """
        if bond_kind not in VALID_BOND_KINDS:
            raise AppError(code=40161, message="双修对象须为道侣或炉鼎", http_status=400)
        await self._expire_stale()
        low, high = friendship_pair_key(character_id, peer_id)
        row = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.character_low_id == low,
                    CharacterBond.character_high_id == high,
                    CharacterBond.bond_kind == bond_kind,
                    CharacterBond.status == "active",
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            label = "道侣" if bond_kind == BOND_KIND_COMPANION else "炉鼎"
            raise AppError(
                code=40161,
                message=f"仅可与已结交的{label}发起双修",
                http_status=400,
            )
        return row

    async def list_active_peers(
        self,
        character_id: int,
        bond_kind: str,
    ) -> list[dict[str, Any]]:
        """列出某类 active 关系对方（供双修选人；炉鼎含主人侧与炉鼎侧）。"""
        await self._expire_stale()
        rows = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.bond_kind == bond_kind,
                    CharacterBond.status == "active",
                    or_(
                        CharacterBond.character_low_id == character_id,
                        CharacterBond.character_high_id == character_id,
                    ),
                ),
            )
        ).scalars().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            peer_id = (
                row.character_high_id
                if row.character_low_id == character_id
                else row.character_low_id
            )
            peer = await self._session.get(Character, peer_id)
            out.append(await self._bond_item(row, character_id, peer))
        return out

    async def _apply_bond(
        self,
        character: Character,
        target: Character,
        *,
        bond_kind: str,
        label_zh: str,
    ) -> dict[str, Any]:
        if bond_kind == BOND_KIND_COMPANION:
            if await self.get_active_vessel_between(character.id, target.id) is not None:
                raise AppError(
                    code=40000,
                    message="双方已是主从炉鼎，不可再申请道侣",
                    http_status=400,
                )
        low, high = friendship_pair_key(character.id, target.id)
        existing = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.character_low_id == low,
                    CharacterBond.character_high_id == high,
                    CharacterBond.bond_kind == bond_kind,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "active":
                raise AppError(code=40000, message=f"已是{label_zh}", http_status=400)
            if existing.status == "pending":
                raise AppError(code=40000, message="申请已存在，请等待确认", http_status=400)
            existing.status = "pending"
            existing.requester_id = character.id
            existing.accepted_at = None
            await self._session.flush()
            tip = f"你有新的道侣申请：「{character.name}」申请结为道侣"
            await self._push_to_character(
                target.id,
                TYPE_BOND_REQUEST,
                self._event_payload(
                    event="request",
                    bond_id=existing.id,
                    bond_kind=bond_kind,
                    from_id=character.id,
                    from_name=character.name,
                    to_id=target.id,
                    to_name=target.name,
                    message=tip,
                ),
            )
            return {
                "message": f"已重新发送{label_zh}申请",
                "bond_id": existing.id,
                "bond_kind": bond_kind,
            }

        if await self._active_count(character.id, bond_kind) >= self._max_for(bond_kind):
            raise AppError(code=40000, message=f"己方{label_zh}已达上限", http_status=400)
        if await self._active_count(target.id, bond_kind) >= self._max_for(bond_kind):
            raise AppError(code=40000, message=f"对方{label_zh}已达上限", http_status=400)

        row = CharacterBond(
            character_low_id=low,
            character_high_id=high,
            bond_kind=bond_kind,
            requester_id=character.id,
            owner_character_id=None,
            status="pending",
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "bond apply kind=%s from=%s to=%s id=%s",
            bond_kind,
            character.id,
            target.id,
            row.id,
        )
        tip = f"你有新的道侣申请：「{character.name}」申请结为道侣"
        await self._push_to_character(
            target.id,
            TYPE_BOND_REQUEST,
            self._event_payload(
                event="request",
                bond_id=row.id,
                bond_kind=bond_kind,
                from_id=character.id,
                from_name=character.name,
                to_id=target.id,
                to_name=target.name,
                message=tip,
            ),
        )
        return {
            "message": f"已向「{target.name}」发送{label_zh}申请",
            "bond_id": row.id,
            "bond_kind": bond_kind,
        }

    async def _active_count(self, character_id: int, bond_kind: str) -> int:
        rows = (
            await self._session.execute(
                select(CharacterBond.id).where(
                    CharacterBond.bond_kind == bond_kind,
                    CharacterBond.status == "active",
                    or_(
                        CharacterBond.character_low_id == character_id,
                        CharacterBond.character_high_id == character_id,
                    ),
                ),
            )
        ).scalars().all()
        return len(rows)

    async def _resolve_target(
        self,
        target_character_id: int | None,
        target_name: str | None,
    ) -> Character:
        if target_character_id is not None:
            ch = await self._session.get(Character, int(target_character_id))
        elif target_name:
            ch = (
                await self._session.execute(
                    select(Character).where(Character.name == target_name.strip()).limit(1),
                )
            ).scalar_one_or_none()
        else:
            raise AppError(code=40000, message="请指定对方道号或角色 id", http_status=400)
        if ch is None:
            raise AppError(code=40005, message="目标角色不存在", http_status=404)
        return ch

    async def _bond_item(
        self,
        row: CharacterBond,
        self_id: int,
        peer: Character | None,
    ) -> dict[str, Any]:
        peer_id = (
            row.character_high_id if row.character_low_id == self_id else row.character_low_id
        )
        major = None
        major_name = None
        cultivation = 0
        if peer is not None:
            major = str(peer.major_realm or "")
            mr = get_major_realm(major) if major else None
            major_name = mr.name if mr else major
            cultivation = int(peer.cultivation_points or 0)
        from app.services.presence_service import PresencePurpose, get_presence

        online = get_presence().is_online_for(PresencePurpose.FRIENDS, int(peer_id))
        owner_id = None
        if row.bond_kind == BOND_KIND_VESSEL:
            owner_id = self._vessel_owner_id(row)
        return {
            "bond_id": row.id,
            "bond_kind": row.bond_kind,
            "peer_character_id": peer_id,
            "peer_name": peer.name if peer else str(peer_id),
            "status": row.status,
            "is_requester": int(row.requester_id) == int(self_id),
            "owner_character_id": owner_id,
            "expires_at": (
                ensure_aware_utc(row.expires_at).isoformat()
                if getattr(row, "expires_at", None) is not None
                else None
            ),
            "peer_major_realm": major,
            "peer_major_realm_name": major_name,
            "peer_cultivation_points": cultivation,
            "online": online,
        }

    async def _expire_stale(self) -> None:
        """惰性清理：过期 pending 申请 + 到期炉鼎。"""
        current = now_utc()
        dirty = False
        expire_sec = int(self._cfg().request_expire_sec or 0)
        if expire_sec > 0:
            cutoff = current - timedelta(seconds=expire_sec)
            pending_rows = (
                await self._session.execute(
                    select(CharacterBond).where(
                        CharacterBond.status == "pending",
                        CharacterBond.created_at < cutoff,
                    ),
                )
            ).scalars().all()
            for row in pending_rows:
                row.status = "cancelled"
                dirty = True
        vessel_rows = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.bond_kind == BOND_KIND_VESSEL,
                    CharacterBond.status == "active",
                    CharacterBond.expires_at.is_not(None),
                    CharacterBond.expires_at < current,
                ),
            )
        ).scalars().all()
        for row in vessel_rows:
            row.status = "cancelled"
            dirty = True
            logger.info("vessel expired bond=%s", row.id)
        if dirty:
            await self._session.flush()

    async def get_active_vessel_between(
        self,
        character_a: int,
        character_b: int,
    ) -> CharacterBond | None:
        """双方之间的 active 炉鼎关系（若有）。"""
        await self._expire_stale()
        low, high = friendship_pair_key(int(character_a), int(character_b))
        return (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.character_low_id == low,
                    CharacterBond.character_high_id == high,
                    CharacterBond.bond_kind == BOND_KIND_VESSEL,
                    CharacterBond.status == "active",
                ),
            )
        ).scalar_one_or_none()

    async def get_active_companion_between(
        self,
        character_a: int,
        character_b: int,
    ) -> CharacterBond | None:
        """双方之间的 active 道侣关系（若有）。"""
        await self._expire_stale()
        low, high = friendship_pair_key(int(character_a), int(character_b))
        return (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.character_low_id == low,
                    CharacterBond.character_high_id == high,
                    CharacterBond.bond_kind == BOND_KIND_COMPANION,
                    CharacterBond.status == "active",
                ),
            )
        ).scalar_one_or_none()

    async def get_vessel_as_servant(
        self,
        character_id: int,
    ) -> CharacterBond | None:
        """角色作为炉鼎的唯一 active 关系（一炉一主）。"""
        await self._expire_stale()
        rows = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.bond_kind == BOND_KIND_VESSEL,
                    CharacterBond.status == "active",
                    or_(
                        CharacterBond.character_low_id == character_id,
                        CharacterBond.character_high_id == character_id,
                    ),
                ),
            )
        ).scalars().all()
        for row in rows:
            if int(self._vessel_owner_id(row)) != int(character_id):
                return row
        return None

    async def face_vessel_context(
        self,
        viewer_id: int,
        peer_id: int,
    ) -> dict[str, Any]:
        """面交炉鼎要约上下文。"""
        await self._expire_stale()
        cfg = self._cfg()
        between = await self.get_active_vessel_between(viewer_id, peer_id)
        relation = "none"
        can_become = True
        can_extend = False
        if between is not None:
            owner_id = self._vessel_owner_id(between)
            if int(owner_id) == int(viewer_id):
                relation = "i_am_master"
                can_become = False
            else:
                relation = "i_am_vessel"
                can_become = False
                can_extend = True
        else:
            as_servant = await self.get_vessel_as_servant(viewer_id)
            if as_servant is not None:
                can_become = False
            # 互为道侣不可再互为炉鼎；道侣仍可为他人炉鼎
            if await self.get_active_companion_between(viewer_id, peer_id) is not None:
                can_become = False
        return {
            "relation": relation,
            "can_offer_become": can_become,
            "can_offer_extend": can_extend,
            "are_companions": (
                await self.get_active_companion_between(viewer_id, peer_id) is not None
            ),
            "vessel_min_hours": int(cfg.vessel_min_hours),
            "vessel_max_hours": int(cfg.vessel_max_hours),
            "expires_at": (
                ensure_aware_utc(between.expires_at).isoformat()
                if between is not None and between.expires_at is not None
                else None
            ),
        }

    async def validate_face_vessel_offer(
        self,
        *,
        offerer_id: int,
        peer_id: int,
        hours: int,
    ) -> None:
        """面交草稿校验炉鼎要约（互斥由交易服务负责）。"""
        from app.domain.int_money import coerce_non_negative_int_or_app_error

        ctx = await self.face_vessel_context(offerer_id, peer_id)
        cfg = self._cfg()
        min_h = int(cfg.vessel_min_hours)
        max_h = int(cfg.vessel_max_hours)
        hours_i = coerce_non_negative_int_or_app_error(hours, field_zh="炉鼎时限")
        if hours_i < min_h or hours_i > max_h:
            raise AppError(
                code=40000,
                message=f"炉鼎时限须为 {min_h}～{max_h} 现实小时",
                http_status=400,
            )
        # 延长现有炉鼎：允许（即便数据异常同时存在道侣也不挡延时）
        if ctx["can_offer_extend"]:
            return
        if await self.get_active_companion_between(offerer_id, peer_id) is not None:
            raise AppError(
                code=40000,
                message="互为道侣不可成为对方炉鼎（道侣可为他人炉鼎）",
                http_status=400,
            )
        if ctx["can_offer_become"]:
            return
        if ctx["relation"] == "i_am_master":
            raise AppError(
                code=40000,
                message="你已是对方主人，不可再成为其炉鼎",
                http_status=400,
            )
        raise AppError(
            code=40000,
            message="当前不可要约炉鼎（已是他人炉鼎或不可延长）",
            http_status=400,
        )

    async def create_or_extend_vessel_from_face(
        self,
        *,
        vessel_character_id: int,
        owner_character_id: int,
        hours: int,
    ) -> dict[str, Any]:
        """
        面交成交：新建或延长炉鼎关系。

        Args:
            vessel_character_id: 愿为炉鼎的一方。
            owner_character_id: 主人。
            hours: 现实小时。
        """
        await self._expire_stale()
        from app.domain.int_money import coerce_non_negative_int_or_app_error

        cfg = self._cfg()
        min_h = int(cfg.vessel_min_hours)
        max_h = int(cfg.vessel_max_hours)
        hours_i = coerce_non_negative_int_or_app_error(hours, field_zh="炉鼎时限")
        if hours_i < min_h or hours_i > max_h:
            raise AppError(
                code=40000,
                message=f"炉鼎时限须为 {min_h}～{max_h} 现实小时",
                http_status=400,
            )
        if int(vessel_character_id) == int(owner_character_id):
            raise AppError(code=40000, message="不可成为自己的炉鼎", http_status=400)

        existing = await self.get_active_vessel_between(
            vessel_character_id,
            owner_character_id,
        )
        current = now_utc()
        delta = timedelta(hours=hours_i)

        if existing is not None:
            owner_id = self._vessel_owner_id(existing)
            if int(owner_id) != int(owner_character_id):
                raise AppError(
                    code=40000,
                    message="主从方向与现有炉鼎关系不符",
                    http_status=400,
                )
            base = current
            if existing.expires_at is not None:
                exp = ensure_aware_utc(existing.expires_at)
                if exp > base:
                    base = exp
            existing.expires_at = base + delta
            existing.updated_at = current
            await self._session.flush()
            logger.info(
                "vessel extend bond=%s vessel=%s owner=%s hours=%s",
                existing.id,
                vessel_character_id,
                owner_character_id,
                hours_i,
            )
            return {
                "bond_id": existing.id,
                "extended": True,
                "hours": hours_i,
                "expires_at": ensure_aware_utc(existing.expires_at).isoformat(),
            }

        if await self.get_active_companion_between(
            vessel_character_id,
            owner_character_id,
        ) is not None:
            raise AppError(
                code=40000,
                message="互为道侣不可成为对方炉鼎（道侣可为他人炉鼎）",
                http_status=400,
            )

        as_servant = await self.get_vessel_as_servant(vessel_character_id)
        if as_servant is not None:
            raise AppError(
                code=40000,
                message="已是他人炉鼎，不可再结",
                http_status=400,
            )
        if await self._owner_vessel_count(owner_character_id) >= self._max_for(
            BOND_KIND_VESSEL,
        ):
            raise AppError(code=40000, message="主人炉鼎已达上限", http_status=400)

        low, high = friendship_pair_key(vessel_character_id, owner_character_id)
        stale = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.character_low_id == low,
                    CharacterBond.character_high_id == high,
                    CharacterBond.bond_kind == BOND_KIND_VESSEL,
                ),
            )
        ).scalar_one_or_none()
        expires = current + delta
        if stale is not None:
            stale.status = "active"
            stale.requester_id = int(vessel_character_id)
            stale.owner_character_id = int(owner_character_id)
            stale.accepted_at = current
            stale.expires_at = expires
            stale.updated_at = current
            row = stale
        else:
            row = CharacterBond(
                character_low_id=low,
                character_high_id=high,
                bond_kind=BOND_KIND_VESSEL,
                requester_id=int(vessel_character_id),
                owner_character_id=int(owner_character_id),
                status="active",
                accepted_at=current,
                expires_at=expires,
            )
            self._session.add(row)
        await self._session.flush()
        logger.info(
            "vessel create bond=%s vessel=%s owner=%s hours=%s",
            row.id,
            vessel_character_id,
            owner_character_id,
            hours_i,
        )
        return {
            "bond_id": row.id,
            "extended": False,
            "hours": hours_i,
            "expires_at": ensure_aware_utc(expires).isoformat(),
        }

    async def _owner_vessel_count(self, owner_id: int) -> int:
        """主人侧 active 炉鼎数。"""
        rows = (
            await self._session.execute(
                select(CharacterBond).where(
                    CharacterBond.bond_kind == BOND_KIND_VESSEL,
                    CharacterBond.status == "active",
                    or_(
                        CharacterBond.character_low_id == owner_id,
                        CharacterBond.character_high_id == owner_id,
                    ),
                ),
            )
        ).scalars().all()
        return sum(1 for r in rows if int(self._vessel_owner_id(r)) == int(owner_id))
