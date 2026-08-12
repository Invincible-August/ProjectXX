"""
道友应用服务（M7 L2）：申请 / 确认 / 列表 / 解除；列表附修为与在线。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models import Character, User
from app.db.models.avatar import Avatar
from app.db.models.social_trade import Friendship
from app.domain.trade_rules import friendship_pair_key
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm

logger = logging.getLogger(__name__)


def require_friends_enabled() -> None:
    """道友总闸（与交易开关独立，默认随 TRADE/SECT 开）。"""
    settings = get_settings()
    if not bool(getattr(settings, "friends_system_enabled", True)):
        raise AppError(code=40000, message="道友系统未开放", http_status=403)


class FriendService:
    """道友用例。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)

    def _cfg(self):
        return get_game_config().friends

    async def list_friends(self, user: User) -> dict[str, Any]:
        """道友与待处理申请（含修为 / 在线 / 助战可用）。"""
        require_friends_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale_requests()
        rows = (
            await self._session.execute(
                select(Friendship).where(
                    or_(
                        Friendship.character_low_id == character.id,
                        Friendship.character_high_id == character.id,
                    ),
                ),
            )
        ).scalars().all()
        active: list[dict[str, Any]] = []
        incoming: list[dict[str, Any]] = []
        outgoing: list[dict[str, Any]] = []
        for row in rows:
            peer_id = (
                row.character_high_id
                if row.character_low_id == character.id
                else row.character_low_id
            )
            peer = await self._session.get(Character, peer_id)
            item = await self._friend_item(row, character.id, peer)
            if row.status == "active":
                active.append(item)
            elif row.status == "pending":
                if row.requester_id == character.id:
                    outgoing.append(item)
                else:
                    incoming.append(item)
        return {
            "friends": active,
            "incoming": incoming,
            "outgoing": outgoing,
            "friend_count": len(active),
            "max_friends": int(self._cfg().max_friends),
        }

    async def apply(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
    ) -> dict[str, Any]:
        """发起道友申请。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        target = await self._resolve_target(target_character_id, target_name)
        if target.id == character.id:
            raise AppError(code=40000, message="不可加自己为道友", http_status=400)
        await self._expire_stale_requests()
        low, high = friendship_pair_key(character.id, target.id)
        existing = (
            await self._session.execute(
                select(Friendship).where(
                    Friendship.character_low_id == low,
                    Friendship.character_high_id == high,
                ),
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "active":
                raise AppError(code=40000, message="已是道友", http_status=400)
            if existing.status == "pending":
                raise AppError(code=40000, message="申请已存在，请等待确认", http_status=400)
            # rejected/cancelled → 允许重开
            existing.status = "pending"
            existing.requester_id = character.id
            existing.accepted_at = None
            await self._session.flush()
            return {"message": "已重新发送道友申请", "friendship_id": existing.id}

        my_count = await self._active_count(character.id)
        if my_count >= int(self._cfg().max_friends):
            raise AppError(code=40000, message="己方道友已达上限", http_status=400)
        their_count = await self._active_count(target.id)
        if their_count >= int(self._cfg().max_friends):
            raise AppError(code=40000, message="对方道友已达上限", http_status=400)

        row = Friendship(
            character_low_id=low,
            character_high_id=high,
            requester_id=character.id,
            status="pending",
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "friend apply from=%s to=%s id=%s",
            character.id,
            target.id,
            row.id,
        )
        return {
            "message": f"已向「{target.name}」发送道友申请",
            "friendship_id": row.id,
        }

    async def accept(self, user: User, friendship_id: int) -> dict[str, Any]:
        """确认道友申请。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(Friendship, friendship_id)
        if row is None or row.status != "pending":
            raise AppError(code=40000, message="申请不存在或已处理", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权处理该申请", http_status=403)
        if row.requester_id == character.id:
            raise AppError(code=40000, message="不可确认自己发出的申请", http_status=400)
        if await self._active_count(character.id) >= int(self._cfg().max_friends):
            raise AppError(code=40000, message="己方道友已达上限", http_status=400)
        peer_id = (
            row.character_high_id
            if row.character_low_id == character.id
            else row.character_low_id
        )
        if await self._active_count(peer_id) >= int(self._cfg().max_friends):
            raise AppError(code=40000, message="对方道友已达上限", http_status=400)
        row.status = "active"
        row.accepted_at = now_utc()
        await self._session.flush()
        peer = await self._session.get(Character, peer_id)
        return {
            "message": f"已与「{peer.name if peer else peer_id}」结为道友",
            "friendship_id": row.id,
            "friend_count": await self._active_count(character.id),
        }

    async def reject(self, user: User, friendship_id: int) -> dict[str, Any]:
        """拒绝申请。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(Friendship, friendship_id)
        if row is None or row.status != "pending":
            raise AppError(code=40000, message="申请不存在或已处理", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权处理该申请", http_status=403)
        if row.requester_id == character.id:
            raise AppError(code=40000, message="请使用取消，而非拒绝自己的申请", http_status=400)
        row.status = "rejected"
        await self._session.flush()
        return {"message": "已拒绝道友申请", "friendship_id": row.id}

    async def remove(self, user: User, friendship_id: int) -> dict[str, Any]:
        """解除已结交道友。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(Friendship, friendship_id)
        if row is None or row.status != "active":
            raise AppError(code=40000, message="道友关系不存在", http_status=400)
        if character.id not in (row.character_low_id, row.character_high_id):
            raise AppError(code=40000, message="无权解除该关系", http_status=403)
        peer_id = (
            row.character_high_id
            if row.character_low_id == character.id
            else row.character_low_id
        )
        peer = await self._session.get(Character, peer_id)
        row.status = "cancelled"
        await self._session.flush()
        return {
            "message": f"已与「{peer.name if peer else peer_id}」解除道友",
            "friendship_id": row.id,
            "friend_count": await self._active_count(character.id),
        }

    async def are_friends(self, a: int, b: int) -> bool:
        """两角色是否为 active 道友。"""
        low, high = friendship_pair_key(a, b)
        row = (
            await self._session.execute(
                select(Friendship).where(
                    Friendship.character_low_id == low,
                    Friendship.character_high_id == high,
                    Friendship.status == "active",
                ),
            )
        ).scalar_one_or_none()
        return row is not None

    async def friend_count(self, character_id: int) -> int:
        """活跃道友数。"""
        return await self._active_count(character_id)

    async def _friend_item(
        self,
        row: Friendship,
        viewer_id: int,
        peer: Character | None,
    ) -> dict[str, Any]:
        """组装列表条目（修为 / 在线 / 助战）。"""
        peer_id = (
            row.character_high_id
            if row.character_low_id == viewer_id
            else row.character_low_id
        )
        major_key = str(peer.major_realm) if peer is not None else ""
        major = get_major_realm(major_key) if major_key else None
        online = False
        assist_available = False
        if peer is not None and row.status == "active":
            online = self._is_peer_online(int(peer.id))
            assist_available = await self._assist_available(peer)
        return {
            "friendship_id": row.id,
            "peer_character_id": peer_id,
            "peer_name": peer.name if peer else str(peer_id),
            "status": row.status,
            "is_requester": row.requester_id == viewer_id,
            "peer_major_realm": major_key or None,
            "peer_major_realm_name": major.name if major else (major_key or None),
            "peer_cultivation_points": int(peer.cultivation_points) if peer else 0,
            "online": online,
            "assist_available": assist_available,
        }

    def _is_peer_online(self, character_id: int) -> bool:
        """在线判定：配置关则恒 false；经 Presence 门面（含 DEV 假定）。"""
        cfg = self._cfg()
        if not bool(getattr(cfg, "include_online", False)) and not bool(
            getattr(cfg, "include_online_stub", False),
        ):
            return False
        from app.services.presence_service import PresencePurpose, get_presence

        return get_presence().is_online_for(PresencePurpose.FRIENDS, int(character_id))

    async def _assist_available(self, peer: Character) -> bool:
        """对方化身是否可供助战（已凝练 + 开关 + 非 disabled + 无忙碌会话）。"""
        avatar = (
            await self._session.execute(
                select(Avatar).where(Avatar.character_id == peer.id),
            )
        ).scalar_one_or_none()
        if avatar is None:
            return False
        if str(avatar.status) == "disabled":
            return False
        if not bool(getattr(avatar, "assist_friends_enabled", 0)):
            return False
        # 已有 invited/active 会话则不可再借
        from app.db.models.avatar_assist import AvatarAssistSession
        from app.services.avatar_assist_service import BUSY_STATUSES

        busy = (
            await self._session.execute(
                select(AvatarAssistSession.id).where(
                    AvatarAssistSession.avatar_id == avatar.id,
                    AvatarAssistSession.status.in_(tuple(BUSY_STATUSES)),
                ).limit(1),
            )
        ).scalar_one_or_none()
        if busy is not None:
            return False
        return True

    async def _active_count(self, character_id: int) -> int:
        rows = (
            await self._session.execute(
                select(Friendship).where(
                    Friendship.status == "active",
                    or_(
                        Friendship.character_low_id == character_id,
                        Friendship.character_high_id == character_id,
                    ),
                ),
            )
        ).scalars().all()
        return len(list(rows))

    async def _resolve_target(
        self,
        target_character_id: int | None,
        target_name: str | None,
    ) -> Character:
        if target_character_id is not None:
            ch = await self._session.get(Character, int(target_character_id))
            if ch is None:
                raise AppError(code=40000, message="目标角色不存在", http_status=404)
            return ch
        name = (target_name or "").strip()
        if not name:
            raise AppError(code=40000, message="请提供目标角色 id 或道号", http_status=400)
        ch = (
            await self._session.execute(select(Character).where(Character.name == name))
        ).scalar_one_or_none()
        if ch is None:
            raise AppError(code=40000, message=f"找不到道号「{name}」", http_status=404)
        return ch

    async def _expire_stale_requests(self) -> None:
        expire_sec = int(self._cfg().request_expire_sec or 0)
        if expire_sec <= 0:
            return
        cutoff = now_utc() - timedelta(seconds=expire_sec)
        rows = (
            await self._session.execute(
                select(Friendship).where(
                    Friendship.status == "pending",
                    Friendship.created_at < cutoff,
                ),
            )
        ).scalars().all()
        for row in rows:
            row.status = "cancelled"
        if rows:
            await self._session.flush()
