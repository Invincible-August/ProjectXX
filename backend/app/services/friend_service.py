"""
道友应用服务（M7 L2）：申请 / 确认 / 列表 / 解除；列表附修为与在线。
"""

from __future__ import annotations

import json
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
from app.domain.ws_protocol import TYPE_FRIEND_REQUEST, TYPE_FRIEND_UPDATE
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm
from app.services.ws_hub_service import get_ws_hub

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

    async def _push_to_character(
        self,
        character_id: int,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Push friend WS envelope to a character's live connections."""
        settings = get_settings()
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        try:
            await get_ws_hub().send_to_character(int(character_id), msg_type, payload)
        except Exception:  # noqa: BLE001
            logger.debug(
                "friend ws push skipped character_id=%s type=%s",
                character_id,
                msg_type,
                exc_info=True,
            )

    def _event_payload(
        self,
        *,
        event: str,
        friendship_id: int,
        from_id: int,
        from_name: str,
        to_id: int,
        to_name: str,
        message: str,
    ) -> dict[str, Any]:
        """Build friend.request / friend.update payload."""
        return {
            "event": event,
            "friendship_id": int(friendship_id),
            "from_character_id": int(from_id),
            "from_name": from_name,
            "to_character_id": int(to_id),
            "to_name": to_name,
            "message": message,
        }

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
            tip = f"你有新的道友拜帖：「{character.name}」申请结为道友"
            await self._push_to_character(
                target.id,
                TYPE_FRIEND_REQUEST,
                self._event_payload(
                    event="request",
                    friendship_id=existing.id,
                    from_id=character.id,
                    from_name=character.name,
                    to_id=target.id,
                    to_name=target.name,
                    message=tip,
                ),
            )
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
        tip = f"你有新的道友拜帖：「{character.name}」申请结为道友"
        await self._push_to_character(
            target.id,
            TYPE_FRIEND_REQUEST,
            self._event_payload(
                event="request",
                friendship_id=row.id,
                from_id=character.id,
                from_name=character.name,
                to_id=target.id,
                to_name=target.name,
                message=tip,
            ),
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
        peer_name = peer.name if peer else str(peer_id)
        # 通知发起方：对方已同意
        await self._push_to_character(
            int(row.requester_id),
            TYPE_FRIEND_UPDATE,
            self._event_payload(
                event="accepted",
                friendship_id=row.id,
                from_id=character.id,
                from_name=character.name,
                to_id=int(row.requester_id),
                to_name=peer_name,
                message=f"「{character.name}」已同意与你结为道友",
            ),
        )
        return {
            "message": f"已与「{peer_name}」结为道友",
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
        requester_id = int(row.requester_id)
        row.status = "rejected"
        await self._session.flush()
        await self._push_to_character(
            requester_id,
            TYPE_FRIEND_UPDATE,
            self._event_payload(
                event="rejected",
                friendship_id=row.id,
                from_id=character.id,
                from_name=character.name,
                to_id=requester_id,
                to_name="",
                message=f"「{character.name}」已拒绝你的道友拜帖",
            ),
        )
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
        """
        列表在线：WS Hub 真实在线（含 grace），**不含** DEV 假定。

        为何不用 is_online_for：development 下 friends.dev_assume_online
        曾把所有人标成在线，导致离线门闸无法验证。
        """
        cfg = self._cfg()
        if not bool(getattr(cfg, "include_online", False)) and not bool(
            getattr(cfg, "include_online_stub", False),
        ):
            return False
        from app.services.presence_service import get_presence

        return get_presence().is_online(int(character_id))

    async def get_privacy(self, user: User) -> dict[str, Any]:
        """当前角色的道友资料可见开关。"""
        require_friends_enabled()
        character = await self._gate.require_character(user)
        visible = bool(getattr(character, "friend_profile_visible", True))
        return {
            "friend_profile_visible": visible,
            "snapshot_at": (
                character.friend_profile_snapshot_at.isoformat()
                if getattr(character, "friend_profile_snapshot_at", None)
                else None
            ),
        }

    async def set_privacy(self, user: User, *, friend_profile_visible: bool) -> dict[str, Any]:
        """
        设置是否允许道友查看修为/功法/属性。

        Args:
            user: 当前用户。
            friend_profile_visible: True=允许；False=遮掩天机。

        Returns:
            dict: 更新后的隐私状态。
        """
        require_friends_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        character.friend_profile_visible = bool(friend_profile_visible)
        if character.friend_profile_visible:
            await self.refresh_profile_snapshot(character)
        await self._session.flush()
        return {
            "message": (
                "已允许道友查看天机"
                if character.friend_profile_visible
                else "已遮掩天机，道友将无法查看"
            ),
            "friend_profile_visible": bool(character.friend_profile_visible),
        }

    async def refresh_profile_snapshot(self, character: Character) -> dict[str, Any]:
        """
        刷新角色道友资料快照（离线时供他人查看）。

        Args:
            character: 目标角色 ORM。

        Returns:
            dict: 写入的快照内容。
        """
        card = await self._build_profile_card(character, online=False, source="snapshot")
        # 快照内不重复塞 source/online 语义给存储；查看时再标注
        store = {k: v for k, v in card.items() if k not in ("online", "source", "snapshot_at")}
        character.friend_profile_snapshot_json = json.dumps(
            store,
            ensure_ascii=False,
        )
        character.friend_profile_snapshot_at = now_utc()
        await self._session.flush()
        return store

    async def get_friend_profile(
        self,
        user: User,
        peer_character_id: int,
    ) -> dict[str, Any]:
        """
        查看道友资料：须为道友；对方允许查看；在线读实时，离线读快照。

        Args:
            user: 查看者。
            peer_character_id: 对方角色 id。

        Returns:
            dict: 资料卡。

        Raises:
            AppError: 非道友 / 遮掩天机 / 不存在。
        """
        require_friends_enabled()
        character = await self._gate.require_character(user)
        peer = await self._session.get(Character, int(peer_character_id))
        if peer is None:
            raise AppError(code=40000, message="目标角色不存在", http_status=404)
        if peer.id == character.id:
            raise AppError(code=40000, message="请在角色面板查看自己", http_status=400)
        if not await self.are_friends(character.id, peer.id):
            raise AppError(code=40000, message="仅可查看道友资料", http_status=403)
        if not bool(getattr(peer, "friend_profile_visible", True)):
            raise AppError(code=40130, message="道友已遮掩天机", http_status=403)

        online = self._is_peer_online(peer.id)
        if online:
            card = await self._build_profile_card(peer, online=True, source="live")
            # 顺带刷新快照，便于下次离线
            try:
                await self.refresh_profile_snapshot(peer)
            except Exception:  # noqa: BLE001
                logger.exception("refresh snapshot failed character_id=%s", peer.id)
            return card

        raw = getattr(peer, "friend_profile_snapshot_json", None)
        if raw:
            try:
                stored = json.loads(raw)
            except json.JSONDecodeError:
                stored = {}
            if isinstance(stored, dict) and stored:
                snap_at = getattr(peer, "friend_profile_snapshot_at", None)
                return {
                    **stored,
                    "online": False,
                    "source": "snapshot",
                    "snapshot_at": snap_at.isoformat() if snap_at else None,
                }
        # 无快照：用当前库内基础字段兜底（仍非实时战斗演算）
        card = await self._build_profile_card(peer, online=False, source="fallback")
        return card

    async def _build_profile_card(
        self,
        character: Character,
        *,
        online: bool,
        source: str,
    ) -> dict[str, Any]:
        """组装可公开给道友的资料卡（修为/功法/属性）。"""
        from app.domain.body_temper import build_body_temper_public
        from app.domain.combat import public_combat_final_summary
        from app.services.character_service import CharacterService
        from app.services.realm_config import get_current_stage

        major = get_major_realm(str(character.major_realm))
        stage = get_current_stage(character.major_realm, character.realm_stage)
        packed = await CharacterService(self._session).build_combat_attrs(character)
        combat = packed.get("combat") or {}
        final = combat.get("final") or {}
        body = build_body_temper_public(character)
        snap_at = getattr(character, "friend_profile_snapshot_at", None)
        return {
            "character_id": character.id,
            "name": character.name,
            "major_realm": character.major_realm,
            "major_realm_name": major.name if major else character.major_realm,
            "realm_stage": int(character.realm_stage),
            "realm_stage_label": character.realm_stage_label,
            "realm_progress": int(character.realm_progress or 0),
            "cultivation_required": (
                int(stage.cultivation_required) if stage is not None else None
            ),
            "cultivation_points": int(character.cultivation_points or 0),
            "body_temper": body,
            "technique_summary": list(packed.get("technique_summary") or []),
            # 与 ATTR schema 同源键（magic_atk / magic_def），禁止 mag_* 分叉
            "combat_final": public_combat_final_summary(final),
            "life": packed.get("life"),
            "online": bool(online),
            "source": source,
            "snapshot_at": snap_at.isoformat() if snap_at and source != "live" else None,
        }

    async def _assist_available(self, peer: Character) -> bool:
        """对方化身是否可邀请（开关开 + 助战体力够 + 非忙碌）。"""
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
        from app.db.models.avatar_assist import AvatarAssistSession
        from app.services.avatar_assist_service import (
            BUSY_STATUSES,
            AvatarAssistService,
        )

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
        panel = AvatarAssistService(self._session).refresh_assist_stamina(
            avatar,
            peer,
            persist=True,
        )
        return bool(panel.get("can_assist"))

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
