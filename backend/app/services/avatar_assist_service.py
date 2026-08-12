"""
道友化身助战用例：开关 / 邀请 / 接受·拒绝·结束 / 列表。

产品规则摘要：
- 主人开 ``assist_friends_enabled`` 后，好友可邀请借入化身；
- 主人在线须手动 accept；离线且开关开 → 自动 active；
- 每化身同时最多一条 active；奖励归借用人；体力扣主人化身。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models import Character, User
from app.db.models.avatar import Avatar
from app.db.models.avatar_assist import AvatarAssistSession
from app.domain.m4_constants import AvatarFeature
from app.schemas.common import AppError
from app.services.avatar_service import AvatarService
from app.services.friend_service import FriendService, require_friends_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)

# 会话状态常量（与 ORM status 对齐）
STATUS_INVITED = "invited"
STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"

# 占用中的状态：不可再开新助战
BUSY_STATUSES = frozenset({STATUS_INVITED, STATUS_ACTIVE})


def guest_unit_uid(owner_character_id: int, avatar_id: int) -> str:
    """Build guest bench unit_uid: ``avatar_guest_{ownerId}_{avatarId}``."""
    return f"avatar_guest_{int(owner_character_id)}_{int(avatar_id)}"


def parse_guest_unit_uid(unit_uid: str) -> tuple[int, int] | None:
    """
    Parse guest unit_uid into (owner_character_id, avatar_id).

    Returns:
        Tuple or None if not a guest uid.
    """
    prefix = "avatar_guest_"
    if not unit_uid.startswith(prefix):
        return None
    rest = unit_uid[len(prefix) :]
    parts = rest.split("_", 1)
    if len(parts) != 2:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def is_guest_avatar_unit(unit: dict[str, Any]) -> bool:
    """True when unit_kind=avatar and unit_uid is a guest assist uid."""
    if str(unit.get("unit_kind", "")) != "avatar":
        return False
    return parse_guest_unit_uid(str(unit.get("unit_uid", ""))) is not None


class AvatarAssistService:
    """Friend-avatar assist use-cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._avatars = AvatarService(session)
        self._friends = FriendService(session)

    def _assist_cfg(self):
        return get_game_config().avatar.friend_assist

    def _is_owner_online(self, owner_character_id: int) -> bool:
        """
        Owner online gate for assist invites.

        ``assist_dev_assume_online`` (friends.yaml override or avatar.yaml) only
        applies in development — forces online so accept must be manual.
        """
        settings = get_settings()
        friends_cfg = get_game_config().friends
        assume = self._assist_cfg().assist_dev_assume_online
        override = getattr(friends_cfg, "assist_dev_assume_online", None)
        if override is not None:
            assume = bool(override)
        if assume and settings.app_env == "development":
            return True
        return get_ws_hub().is_character_online(int(owner_character_id))

    async def _expire_stale_invites(self) -> None:
        """Lazily mark overdue invited rows as expired."""
        expire_sec = int(self._assist_cfg().invite_expire_sec or 0)
        if expire_sec <= 0:
            return
        cutoff = now_utc() - timedelta(seconds=expire_sec)
        rows = (
            await self._session.execute(
                select(AvatarAssistSession).where(
                    AvatarAssistSession.status == STATUS_INVITED,
                    AvatarAssistSession.expires_at.is_not(None),
                    AvatarAssistSession.expires_at < now_utc(),
                ),
            )
        ).scalars().all()
        # Also catch rows whose expires_at drifted past cutoff via created_at
        if not rows:
            rows = (
                await self._session.execute(
                    select(AvatarAssistSession).where(
                        AvatarAssistSession.status == STATUS_INVITED,
                        AvatarAssistSession.created_at < cutoff,
                        AvatarAssistSession.expires_at.is_(None),
                    ),
                )
            ).scalars().all()
        for row in rows:
            row.status = STATUS_EXPIRED
            row.ended_at = now_utc()
        if rows:
            await self._session.flush()

    async def _avatar_busy(self, avatar_id: int) -> bool:
        """True if avatar already has invited/active assist session."""
        row = (
            await self._session.execute(
                select(AvatarAssistSession.id).where(
                    AvatarAssistSession.avatar_id == int(avatar_id),
                    AvatarAssistSession.status.in_(tuple(BUSY_STATUSES)),
                ).limit(1),
            )
        ).scalar_one_or_none()
        return row is not None

    def _session_public(
        self,
        row: AvatarAssistSession,
        *,
        owner_name: str | None = None,
        borrower_name: str | None = None,
        avatar_name: str | None = None,
    ) -> dict[str, Any]:
        """Serialize session for API."""
        return {
            "id": row.id,
            "owner_character_id": row.owner_character_id,
            "owner_name": owner_name,
            "borrower_character_id": row.borrower_character_id,
            "borrower_name": borrower_name,
            "avatar_id": row.avatar_id,
            "avatar_name": avatar_name,
            "status": row.status,
            "guest_unit_uid": guest_unit_uid(row.owner_character_id, row.avatar_id),
            "expires_at": to_utc_iso(row.expires_at) if row.expires_at else None,
            "created_at": to_utc_iso(row.created_at) if row.created_at else None,
            "accepted_at": to_utc_iso(row.accepted_at) if row.accepted_at else None,
            "ended_at": to_utc_iso(row.ended_at) if row.ended_at else None,
        }

    async def _enrich(self, row: AvatarAssistSession) -> dict[str, Any]:
        owner = await self._session.get(Character, row.owner_character_id)
        borrower = await self._session.get(Character, row.borrower_character_id)
        avatar = await self._session.get(Avatar, row.avatar_id)
        return self._session_public(
            row,
            owner_name=owner.name if owner else None,
            borrower_name=borrower.name if borrower else None,
            avatar_name=avatar.name if avatar else None,
        )

    async def _push_invite(self, owner_character_id: int, payload: dict[str, Any]) -> None:
        """Optional WS push ``avatar.assist.invite`` to owner connections."""
        settings = get_settings()
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        from app.domain.ws_protocol import TYPE_AVATAR_ASSIST_INVITE

        hub = get_ws_hub()
        for conn in list(hub._connections.values()):
            if conn.authenticated and conn.character_id == int(owner_character_id):
                await hub.send(conn.conn_id, TYPE_AVATAR_ASSIST_INVITE, payload)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def set_assist_settings(self, user: User, *, enabled: bool) -> dict[str, Any]:
        """
        Owner toggles ``assist_friends_enabled`` on their avatar.

        Raises:
            AppError: no avatar / feature locked.
        """
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._avatars._require_feature(character, AvatarFeature.FRIEND_ASSIST)
        avatar = (
            await self._session.execute(
                select(Avatar).where(Avatar.character_id == character.id).limit(1),
            )
        ).scalar_one_or_none()
        if avatar is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        avatar.assist_friends_enabled = 1 if enabled else 0
        await self._session.flush()
        logger.info(
            "avatar assist settings character_id=%s enabled=%s",
            character.id,
            enabled,
        )
        return {
            "assist_friends_enabled": bool(avatar.assist_friends_enabled),
            "avatar_id": avatar.id,
        }

    async def invite(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
    ) -> dict[str, Any]:
        """
        Borrower invites owner's avatar to assist.

        Auto-accepts to ``active`` when owner is offline and switch is on.
        """
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale_invites()

        owner = await self._friends._resolve_target(target_character_id, target_name)
        if owner.id == character.id:
            raise AppError(code=40000, message="不可邀请自己的化身助战", http_status=400)
        if not await self._friends.are_friends(character.id, owner.id):
            raise AppError(code=40000, message="仅道友可邀请化身助战", http_status=400)

        # 主人须已解锁功能 + 凝练化身 + 开关开
        if not self._avatars.capability().is_unlocked(
            owner.major_realm,
            AvatarFeature.FRIEND_ASSIST,
        ):
            raise AppError(code=40093, message="对方尚未解锁道友助战", http_status=400)
        avatar = (
            await self._session.execute(
                select(Avatar).where(Avatar.character_id == owner.id).limit(1),
            )
        ).scalar_one_or_none()
        if avatar is None:
            raise AppError(code=40051, message="对方尚未凝练化身", http_status=400)
        if str(avatar.status) == "disabled":
            raise AppError(code=40051, message="对方化身不可用", http_status=400)
        if not bool(avatar.assist_friends_enabled):
            raise AppError(code=40000, message="对方未开启道友助战", http_status=400)
        if await self._avatar_busy(avatar.id):
            raise AppError(code=40000, message="对方化身正在助战中", http_status=400)

        # 借用人侧：同时只允许一条 invited/active（避免多客串）
        my_busy = (
            await self._session.execute(
                select(AvatarAssistSession.id).where(
                    AvatarAssistSession.borrower_character_id == character.id,
                    AvatarAssistSession.status.in_(tuple(BUSY_STATUSES)),
                ).limit(1),
            )
        ).scalar_one_or_none()
        if my_busy is not None:
            raise AppError(code=40000, message="已有进行中的助战会话", http_status=400)

        expire_sec = int(self._assist_cfg().invite_expire_sec or 0)
        expires_at = (
            now_utc() + timedelta(seconds=expire_sec) if expire_sec > 0 else None
        )
        row = AvatarAssistSession(
            owner_character_id=owner.id,
            borrower_character_id=character.id,
            avatar_id=avatar.id,
            status=STATUS_INVITED,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()

        # 离线 → 自动接受；在线 → 等主人确认
        auto_accepted = False
        if not self._is_owner_online(owner.id):
            row.status = STATUS_ACTIVE
            row.accepted_at = now_utc()
            auto_accepted = True
            await self._session.flush()
            logger.info(
                "avatar assist auto-accept session=%s owner=%s borrower=%s",
                row.id,
                owner.id,
                character.id,
            )
        else:
            public = await self._enrich(row)
            await self._push_invite(owner.id, public)
            logger.info(
                "avatar assist invite session=%s owner=%s borrower=%s",
                row.id,
                owner.id,
                character.id,
            )

        return {
            "session": await self._enrich(row),
            "auto_accepted": auto_accepted,
            "message": (
                "对方离线，已自动借入化身助战"
                if auto_accepted
                else f"已邀请「{owner.name}」化身助战，等待对方确认"
            ),
        }

    async def accept(self, user: User, session_id: int) -> dict[str, Any]:
        """Owner accepts an invited assist session."""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale_invites()
        row = await self._session.get(AvatarAssistSession, int(session_id))
        if row is None:
            raise AppError(code=40000, message="助战会话不存在", http_status=404)
        if row.owner_character_id != character.id:
            raise AppError(code=40000, message="仅化身主人可接受助战", http_status=403)
        if row.status != STATUS_INVITED:
            raise AppError(code=40000, message=f"会话状态不可接受：{row.status}", http_status=400)
        # 再次确认化身未被其它会话占用（防竞态）
        other = (
            await self._session.execute(
                select(AvatarAssistSession.id).where(
                    AvatarAssistSession.avatar_id == row.avatar_id,
                    AvatarAssistSession.status == STATUS_ACTIVE,
                    AvatarAssistSession.id != row.id,
                ).limit(1),
            )
        ).scalar_one_or_none()
        if other is not None:
            row.status = STATUS_REJECTED
            row.ended_at = now_utc()
            await self._session.flush()
            raise AppError(code=40000, message="化身已在其它助战中", http_status=400)
        row.status = STATUS_ACTIVE
        row.accepted_at = now_utc()
        await self._session.flush()
        logger.info("avatar assist accept session=%s owner=%s", row.id, character.id)
        return {"session": await self._enrich(row), "message": "已接受道友助战邀请"}

    async def reject(self, user: User, session_id: int) -> dict[str, Any]:
        """Owner rejects an invited assist session."""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale_invites()
        row = await self._session.get(AvatarAssistSession, int(session_id))
        if row is None:
            raise AppError(code=40000, message="助战会话不存在", http_status=404)
        if row.owner_character_id != character.id:
            raise AppError(code=40000, message="仅化身主人可拒绝助战", http_status=403)
        if row.status != STATUS_INVITED:
            raise AppError(code=40000, message=f"会话状态不可拒绝：{row.status}", http_status=400)
        row.status = STATUS_REJECTED
        row.ended_at = now_utc()
        await self._session.flush()
        logger.info("avatar assist reject session=%s owner=%s", row.id, character.id)
        return {"session": await self._enrich(row), "message": "已拒绝道友助战邀请"}

    async def end(self, user: User, session_id: int) -> dict[str, Any]:
        """Owner or borrower ends an active (or invited) assist session."""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(AvatarAssistSession, int(session_id))
        if row is None:
            raise AppError(code=40000, message="助战会话不存在", http_status=404)
        if character.id not in (row.owner_character_id, row.borrower_character_id):
            raise AppError(code=40000, message="无权结束此助战会话", http_status=403)
        if row.status not in (STATUS_INVITED, STATUS_ACTIVE):
            raise AppError(code=40000, message=f"会话状态不可结束：{row.status}", http_status=400)
        row.status = STATUS_ENDED
        row.ended_at = now_utc()
        await self._session.flush()
        logger.info(
            "avatar assist end session=%s by=%s",
            row.id,
            character.id,
        )
        return {"session": await self._enrich(row), "message": "助战已结束"}

    async def list_me(self, user: User) -> dict[str, Any]:
        """List assist sessions involving the current character."""
        require_friends_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale_invites()
        rows = (
            await self._session.execute(
                select(AvatarAssistSession)
                .where(
                    or_(
                        AvatarAssistSession.owner_character_id == character.id,
                        AvatarAssistSession.borrower_character_id == character.id,
                    ),
                )
                .order_by(AvatarAssistSession.id.desc()),
            )
        ).scalars().all()
        as_owner: list[dict[str, Any]] = []
        as_borrower: list[dict[str, Any]] = []
        for row in rows:
            item = await self._enrich(row)
            if row.owner_character_id == character.id:
                as_owner.append(item)
            if row.borrower_character_id == character.id:
                as_borrower.append(item)
        avatar = (
            await self._session.execute(
                select(Avatar).where(Avatar.character_id == character.id).limit(1),
            )
        ).scalar_one_or_none()
        return {
            "assist_friends_enabled": bool(
                avatar.assist_friends_enabled if avatar is not None else 0,
            ),
            "as_owner": as_owner,
            "as_borrower": as_borrower,
        }

    async def list_active_for_borrower(
        self,
        borrower_character_id: int,
    ) -> list[AvatarAssistSession]:
        """Active assist sessions where character is the borrower (for bench)."""
        await self._expire_stale_invites()
        rows = (
            await self._session.execute(
                select(AvatarAssistSession).where(
                    AvatarAssistSession.borrower_character_id == int(borrower_character_id),
                    AvatarAssistSession.status == STATUS_ACTIVE,
                ),
            )
        ).scalars().all()
        return list(rows)

    async def get_active_guest_session(
        self,
        *,
        borrower_character_id: int,
        owner_character_id: int,
        avatar_id: int,
    ) -> AvatarAssistSession | None:
        """Lookup active guest session matching owner+avatar for borrower."""
        await self._expire_stale_invites()
        return (
            await self._session.execute(
                select(AvatarAssistSession).where(
                    AvatarAssistSession.borrower_character_id == int(borrower_character_id),
                    AvatarAssistSession.owner_character_id == int(owner_character_id),
                    AvatarAssistSession.avatar_id == int(avatar_id),
                    AvatarAssistSession.status == STATUS_ACTIVE,
                ).limit(1),
            )
        ).scalar_one_or_none()
