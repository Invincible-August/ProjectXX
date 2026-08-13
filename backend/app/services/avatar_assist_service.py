"""
道友化身助战用例：开关 / 邀请化身 / 结束 / 独立助战体力。

规则：开关开则邀请立即入队；关→闭关；忙→助战中；助战体力独立；
PVE 战后自动离队；秘境整场结束离队。
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
from app.domain.avatar_assist_stamina import (
    assist_resume_threshold,
    assist_stamina_cap,
    tick_assist_stamina,
)
from app.domain.m4_constants import AvatarFeature
from app.schemas.common import AppError
from app.services.avatar_service import AvatarService
from app.services.friend_service import FriendService, require_friends_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)

STATUS_INVITED = "invited"
STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"

BUSY_STATUSES = frozenset({STATUS_INVITED, STATUS_ACTIVE})


def guest_unit_uid(owner_character_id: int, avatar_id: int) -> str:
    """Build guest bench unit_uid."""
    return f"avatar_guest_{int(owner_character_id)}_{int(avatar_id)}"


def parse_guest_unit_uid(unit_uid: str) -> tuple[int, int] | None:
    """Parse guest unit_uid into (owner_character_id, avatar_id)."""
    prefix = "avatar_guest_"
    if not unit_uid.startswith(prefix):
        return None
    rest = unit_uid[len(prefix) :]
    parts = rest.split("_", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def is_guest_avatar_unit(unit: dict[str, Any]) -> bool:
    """True when unit is guest avatar assist."""
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

    def refresh_assist_stamina(
        self,
        avatar: Avatar,
        owner: Character,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Tick 助战体力并返回面板。"""
        cfg = self._assist_cfg()
        cap = assist_stamina_cap(
            character_major=str(owner.major_realm),
            assist_cfg=cfg,
        )
        cur = int(getattr(avatar, "assist_stamina", 0) or 0)
        if getattr(avatar, "assist_stamina_recovered_at", None) is None and cur <= 0:
            cur = cap
        new_val, new_anchor = tick_assist_stamina(
            current=cur,
            cap=cap,
            recovered_at=getattr(avatar, "assist_stamina_recovered_at", None),
            recovery_per_hour=float(cfg.stamina_recovery_per_hour),
        )
        thr = assist_resume_threshold(cap, resume_ratio=float(cfg.resume_ratio))
        locked = bool(getattr(avatar, "assist_stamina_locked", 0))
        if locked and new_val >= thr:
            locked = False
        if persist:
            avatar.assist_stamina = new_val
            avatar.assist_stamina_recovered_at = new_anchor
            avatar.assist_stamina_locked = 1 if locked else 0
        return {
            "assist_stamina": new_val,
            "assist_stamina_cap": cap,
            "assist_stamina_locked": locked,
            "resume_threshold": thr,
            "battle_cost": int(cfg.battle_cost),
            "recovery_per_hour": float(cfg.stamina_recovery_per_hour),
            "can_assist": (not locked) and new_val >= int(cfg.battle_cost),
        }

    def assert_can_lend(self, avatar: Avatar, owner: Character) -> dict[str, Any]:
        """校验可出借。"""
        panel = self.refresh_assist_stamina(avatar, owner, persist=True)
        if panel["assist_stamina_locked"]:
            raise AppError(
                code=40000,
                message=(
                    f"化身助战体力已耗尽，须恢复至 "
                    f"{panel['resume_threshold']} 点后方可再助战"
                ),
                http_status=400,
            )
        if int(panel["assist_stamina"]) < int(panel["battle_cost"]):
            raise AppError(
                code=40000,
                message=(
                    f"化身助战体力不足（需 {panel['battle_cost']}，"
                    f"当前 {panel['assist_stamina']}）"
                ),
                http_status=400,
            )
        return panel

    def spend_assist_battle(self, avatar: Avatar, owner: Character) -> dict[str, Any]:
        """PVE 开战扣助战体力。"""
        panel = self.refresh_assist_stamina(avatar, owner, persist=True)
        cost = int(panel["battle_cost"])
        if panel["assist_stamina_locked"] or int(panel["assist_stamina"]) < cost:
            raise AppError(
                code=40000,
                message="化身助战体力不足，无法继续助战",
                http_status=400,
            )
        avatar.assist_stamina = max(0, int(panel["assist_stamina"]) - cost)
        if avatar.assist_stamina <= 0:
            avatar.assist_stamina = 0
            avatar.assist_stamina_locked = 1
        return self.refresh_assist_stamina(avatar, owner, persist=True)

    async def _expire_stale_invites(self) -> None:
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

    async def set_assist_settings(self, user: User, *, enabled: bool) -> dict[str, Any]:
        """化身页：开启/关闭化身助战。"""
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
        stamina = self.refresh_assist_stamina(avatar, character, persist=True)
        await self._session.flush()
        enabled_flag = bool(avatar.assist_friends_enabled)
        return {
            "enabled": enabled_flag,
            "assist_friends_enabled": enabled_flag,
            "avatar_id": avatar.id,
            "assist_stamina": stamina,
            "message": "已开启化身助战" if enabled else "已关闭化身助战（闭关）",
        }

    async def invite(
        self,
        user: User,
        *,
        target_character_id: int | None,
        target_name: str | None,
    ) -> dict[str, Any]:
        """邀请化身：开则立即入队；关→闭关；忙→助战中。"""
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale_invites()

        owner = await self._friends._resolve_target(target_character_id, target_name)
        if owner.id == character.id:
            raise AppError(code=40000, message="不可邀请自己的化身", http_status=400)
        if not await self._friends.are_friends(character.id, owner.id):
            raise AppError(code=40000, message="仅道友可邀请化身", http_status=400)

        if not self._avatars.capability().is_unlocked(
            owner.major_realm,
            AvatarFeature.FRIEND_ASSIST,
        ):
            raise AppError(code=40093, message="对方尚未解锁化身助战", http_status=400)
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
            raise AppError(code=40000, message="化身正在闭关中", http_status=400)
        if await self._avatar_busy(avatar.id):
            raise AppError(code=40000, message="化身正在助战中", http_status=400)

        self.assert_can_lend(avatar, owner)

        my_busy = (
            await self._session.execute(
                select(AvatarAssistSession.id).where(
                    AvatarAssistSession.borrower_character_id == character.id,
                    AvatarAssistSession.status.in_(tuple(BUSY_STATUSES)),
                ).limit(1),
            )
        ).scalar_one_or_none()
        if my_busy is not None:
            raise AppError(code=40000, message="你已有进行中的化身助战", http_status=400)

        expire_sec = int(self._assist_cfg().invite_expire_sec or 0)
        expires_at = (
            now_utc() + timedelta(seconds=expire_sec) if expire_sec > 0 else None
        )
        row = AvatarAssistSession(
            owner_character_id=owner.id,
            borrower_character_id=character.id,
            avatar_id=avatar.id,
            status=STATUS_ACTIVE,
            expires_at=expires_at,
            accepted_at=now_utc(),
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "avatar assist joined session=%s owner=%s borrower=%s",
            row.id,
            owner.id,
            character.id,
        )
        return {
            "session": await self._enrich(row),
            "auto_accepted": True,
            "message": f"已邀请「{owner.name}」化身加入助战",
        }

    async def accept(self, user: User, session_id: int) -> dict[str, Any]:
        """兼容旧 invited 态。"""
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
        avatar = await self._session.get(Avatar, row.avatar_id)
        if avatar is None:
            raise AppError(code=40051, message="化身不存在", http_status=400)
        self.assert_can_lend(avatar, character)
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
            raise AppError(code=40000, message="化身正在助战中", http_status=400)
        row.status = STATUS_ACTIVE
        row.accepted_at = now_utc()
        await self._session.flush()
        return {"session": await self._enrich(row), "message": "已接受化身助战邀请"}

    async def reject(self, user: User, session_id: int) -> dict[str, Any]:
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
        return {"session": await self._enrich(row), "message": "已拒绝化身助战邀请"}

    async def end(self, user: User, session_id: int) -> dict[str, Any]:
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
        return {"session": await self._enrich(row), "message": "化身已离队"}

    async def end_active_for_borrower(
        self,
        borrower_character_id: int,
        *,
        reason: str = "battle_end",
    ) -> int:
        """借入方战斗结束：客串化身自动离队。"""
        rows = (
            await self._session.execute(
                select(AvatarAssistSession).where(
                    AvatarAssistSession.borrower_character_id == int(borrower_character_id),
                    AvatarAssistSession.status == STATUS_ACTIVE,
                ),
            )
        ).scalars().all()
        now = now_utc()
        n = 0
        for row in rows:
            row.status = STATUS_ENDED
            row.ended_at = now
            n += 1
        if n:
            await self._session.flush()
            logger.info(
                "avatar assist auto-end borrower=%s count=%s reason=%s",
                borrower_character_id,
                n,
                reason,
            )
        return n

    async def end_for_secret_realm(self, borrower_character_id: int) -> int:
        """秘境整场结束后离队。"""
        return await self.end_active_for_borrower(
            borrower_character_id,
            reason="secret_realm_end",
        )

    async def list_me(self, user: User) -> dict[str, Any]:
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
        assist_stamina = None
        if avatar is not None:
            assist_stamina = self.refresh_assist_stamina(avatar, character, persist=True)
            await self._session.flush()
        return {
            "assist_friends_enabled": bool(
                avatar.assist_friends_enabled if avatar is not None else 0,
            ),
            "assist_stamina": assist_stamina,
            "as_owner": as_owner,
            "as_borrower": as_borrower,
        }

    async def list_active_for_borrower(
        self,
        borrower_character_id: int,
    ) -> list[AvatarAssistSession]:
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
