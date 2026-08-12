"""
聊天与最小队伍应用服务（M7 L4）。

发送权威走 HTTP；落库后可选 WS ``chat.message`` 推送。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.chat import (
    ChatMessage,
    ChatMute,
    ChatUnread,
    PartyInvite,
    PartyMember,
    PartySession,
)
from app.domain.channel_membership import (
    ACTIVE_CHANNEL_TYPES,
    ChannelMembership,
    apply_sensitive_filter,
    build_dm_ref,
    build_mentor_ref,
    build_party_ref,
    build_sect_ref,
    build_world_ref,
    parse_channel_ref,
    room_id_for,
)
from app.domain.ws_protocol import (
    TYPE_CHAT_MESSAGE,
    TYPE_CHAT_UNREAD,
    TYPE_PARTY_INVITE,
    TYPE_PARTY_UPDATE,
)
from app.schemas.common import AppError
from app.services.friend_service import FriendService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)

# 进程内滑动窗口限速：character_id → 发送时间戳队列
_RATE_BUCKETS: dict[int, deque[float]] = defaultdict(deque)


def require_chat_enabled() -> None:
    """聊天总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "chat_system_enabled", True)):
        raise AppError(code=40000, message="聊天系统未开放", http_status=403)


def reset_chat_rate_buckets_for_tests() -> None:
    """测试清空限速桶。"""
    _RATE_BUCKETS.clear()


class ChatService:
    """聊天 / 队伍用例。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._membership = ChannelMembership(session)

    def _cfg(self):
        return get_game_config().chat

    async def total_unread(self, character_id: int) -> int:
        """角标：各频道未读之和。"""
        total = (
            await self._session.execute(
                select(func.coalesce(func.sum(ChatUnread.unread_count), 0)).where(
                    ChatUnread.character_id == character_id,
                ),
            )
        ).scalar_one()
        return int(total or 0)

    async def list_channels(self, user: User) -> dict[str, Any]:
        """可进频道目录（含锁定原因与未读）。"""
        require_chat_enabled()
        character = await self._gate.require_character(user)
        cfg = self._cfg()
        labels = dict(cfg.labels_zh or {})
        items: list[dict[str, Any]] = []

        # 世界
        world = build_world_ref(line_id=str(cfg.world_line_id or "default"))
        items.append(
            await self._channel_public(
                character,
                channel_type="world",
                channel_ref=world.channel_ref,
                label_zh=str(labels.get("world") or "世界"),
            ),
        )

        # 宗门
        if character.sect_id is not None:
            sect = build_sect_ref(int(character.sect_id))
            items.append(
                await self._channel_public(
                    character,
                    channel_type="sect",
                    channel_ref=sect.channel_ref,
                    label_zh=str(labels.get("sect") or "宗门"),
                ),
            )
        else:
            items.append(
                {
                    "channel_type": "sect",
                    "channel_ref": None,
                    "label_zh": str(labels.get("sect") or "宗门"),
                    "can_access": False,
                    "can_send": False,
                    "lock_reason_zh": "未入宗不可进宗门频",
                    "unread": 0,
                    "room_id": None,
                },
            )

        # 私聊：已结交道友各一条会话（可点开）
        from app.services.friend_service import FriendService

        friends = await FriendService(self._session).list_friends(user)
        for fr in friends.get("friends") or []:
            peer_id = int(fr["peer_character_id"])
            dm = build_dm_ref(character.id, peer_id)
            items.append(
                await self._channel_public(
                    character,
                    channel_type="dm",
                    channel_ref=dm.channel_ref,
                    label_zh=f"{labels.get('dm') or '私聊'}·{fr['peer_name']}",
                    peer_character_id=peer_id,
                    peer_name=str(fr["peer_name"]),
                ),
            )

        # 师承：有活跃键则开放
        from app.services.mentor_service import MentorService

        bond = await MentorService(self._session).get_active_bond_for(character.id)
        if bond is not None:
            mref = build_mentor_ref(bond.id)
            items.append(
                await self._channel_public(
                    character,
                    channel_type="mentor",
                    channel_ref=mref.channel_ref,
                    label_zh=str(labels.get("mentor") or "师承"),
                ),
            )
        else:
            items.append(
                {
                    "channel_type": "mentor",
                    "channel_ref": None,
                    "label_zh": str(labels.get("mentor") or "师承"),
                    "can_access": False,
                    "can_send": False,
                    "lock_reason_zh": "尚未结成师徒",
                    "unread": 0,
                    "room_id": None,
                },
            )

        # 队伍
        party = await self._active_party_for(character.id)
        if party is not None:
            pref = build_party_ref(party.id)
            items.append(
                await self._channel_public(
                    character,
                    channel_type="party",
                    channel_ref=pref.channel_ref,
                    label_zh=str(labels.get("party") or "队伍"),
                    party_id=party.id,
                ),
            )
        else:
            items.append(
                {
                    "channel_type": "party",
                    "channel_ref": None,
                    "label_zh": str(labels.get("party") or "队伍"),
                    "can_access": False,
                    "can_send": False,
                    "lock_reason_zh": "尚未组队",
                    "unread": 0,
                    "room_id": None,
                },
            )

        return {
            "items": items,
            "unread_total": await self.total_unread(character.id),
            # 私聊角标按人头：有未读的 DM 频道数
            "dm_unread_peers": await self.count_dm_unread_peers(character.id),
            "channel_types": list(ACTIVE_CHANNEL_TYPES),
            # 前端：退出/关浏览器清空本会话消息；进房不拉历史
            "session_ephemeral": bool(getattr(cfg, "session_ephemeral", True)),
        }

    async def history(
        self,
        user: User,
        *,
        channel_ref: str,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> dict[str, Any]:
        """拉取短历史（鉴权）。"""
        require_chat_enabled()
        character = await self._gate.require_character(user)
        cref = parse_channel_ref(channel_ref)
        if cref is None:
            raise AppError(code=40000, message="频道无效", http_status=400)
        ok, reason = await self._membership.can_access(character, cref)
        if not ok:
            raise AppError(code=40130, message=reason or "频道无权限", http_status=403)
        lim = min(int(limit or self._cfg().history_limit), int(self._cfg().history_limit))
        lim = max(1, lim)
        q = select(ChatMessage).where(ChatMessage.channel_ref == cref.channel_ref)
        if before_id is not None:
            q = q.where(ChatMessage.id < int(before_id))
        q = q.order_by(ChatMessage.id.desc()).limit(lim)
        rows = list((await self._session.execute(q)).scalars().all())
        rows.reverse()
        return {
            "channel_ref": cref.channel_ref,
            "room_id": cref.room_id,
            "items": [await self._message_public(row) for row in rows],
        }

    async def send(
        self,
        user: User,
        *,
        channel_type: str,
        body_zh: str,
        channel_ref: str | None = None,
        peer_character_id: int | None = None,
        peer_name: str | None = None,
    ) -> dict[str, Any]:
        """
        发送消息（权威）。

        Args:
            user: 发送方。
            channel_type: world/sect/dm/mentor/party。
            body_zh: 正文。
            channel_ref: 可选显式引用。
            peer_character_id: 私聊目标。
            peer_name: 私聊道号。

        Returns:
            dict: 含 message 公开体。
        """
        require_chat_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        ctype = str(channel_type or "").strip().lower()
        if ctype not in ACTIVE_CHANNEL_TYPES:
            raise AppError(code=40000, message="不支持的频道类型", http_status=400)
        if ctype in ("region", "faction"):
            raise AppError(code=40130, message="该频道尚未开放", http_status=403)

        body = (body_zh or "").strip()
        if not body:
            raise AppError(code=40000, message="消息不可为空", http_status=400)
        max_len = int(self._cfg().max_body_len or 200)
        if len(body) > max_len:
            raise AppError(code=40000, message="消息过长", http_status=400)

        cref = await self._resolve_send_target(
            character,
            channel_type=ctype,
            channel_ref=channel_ref,
            peer_character_id=peer_character_id,
            peer_name=peer_name,
        )
        ok, reason = await self._membership.can_access(character, cref)
        if not ok:
            raise AppError(code=40130, message=reason or "频道无权限", http_status=403)

        await self._assert_not_muted(character.id, cref.channel_ref)
        self._assert_rate(character.id)

        body = apply_sensitive_filter(
            body,
            list(self._cfg().sensitive_words or []),
            enabled=bool(self._cfg().sensitive_filter_enabled),
        )

        row = ChatMessage(
            channel_type=cref.channel_type,
            channel_ref=cref.channel_ref,
            sender_character_id=character.id,
            body_zh=body,
        )
        self._session.add(row)
        await self._session.flush()

        # 未读：世界不刷全服角标；其它频道给成员（除自己）+1
        if cref.channel_type != "world":
            member_ids = await self._membership.list_member_ids(cref)
            for mid in member_ids:
                if mid == character.id:
                    continue
                await self._bump_unread(mid, cref.channel_ref, delta=1)

        public = await self._message_public(row)
        await self._push_message(cref.room_id, public)
        if cref.channel_type != "world":
            await self._push_unread_to_members(cref, exclude_id=character.id)

        logger.info(
            "chat send character_id=%s channel=%s msg_id=%s",
            character.id,
            cref.channel_ref,
            row.id,
        )
        return {
            "message": public,
            "channel_ref": cref.channel_ref,
            "room_id": cref.room_id,
        }

    async def mark_read(self, user: User, *, channel_ref: str) -> dict[str, Any]:
        """清零某频道未读。"""
        require_chat_enabled()
        character = await self._gate.require_character(user)
        cref = parse_channel_ref(channel_ref)
        if cref is None:
            raise AppError(code=40000, message="频道无效", http_status=400)
        ok, reason = await self._membership.can_access(character, cref)
        if not ok:
            raise AppError(code=40130, message=reason or "频道无权限", http_status=403)
        row = (
            await self._session.execute(
                select(ChatUnread).where(
                    ChatUnread.character_id == character.id,
                    ChatUnread.channel_ref == cref.channel_ref,
                ),
            )
        ).scalar_one_or_none()
        if row is not None:
            row.unread_count = 0
            await self._session.flush()
        total = await self.total_unread(character.id)
        return {
            "channel_ref": cref.channel_ref,
            "unread": 0,
            "unread_total": total,
            "dm_unread_peers": await self.count_dm_unread_peers(character.id),
        }

    # ----- party -----

    async def party_me(self, user: User) -> dict[str, Any]:
        """
        Current party plus incoming pending invites for this character.

        Returns:
            dict: ``party`` (or null) and ``pending_invites`` list.
        """
        require_chat_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale_party_invites()
        party = await self._active_party_for(character.id)
        pending = await self._pending_invites_for(character.id)
        return {
            "party": await self._party_public(party) if party is not None else None,
            "pending_invites": pending,
        }

    async def party_action(
        self,
        user: User,
        *,
        action: str,
        peer_character_id: int | None = None,
        peer_name: str | None = None,
        invite_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Party lifecycle: create (empty) / invite / accept / reject / leave / kick.

        Args:
            user: Current user.
            action: create | invite | accept | reject | leave | kick.
            peer_character_id: Target for invite or kick.
            peer_name: Target dao name for invite or kick.
            invite_id: Invite row id for accept/reject.

        Returns:
            dict: Result payload (party / invite / pending_invites).

        Raises:
            AppError: Validation or gate failures.
        """
        require_chat_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale_party_invites()
        act = str(action or "").strip().lower()
        if act == "create":
            return await self._party_create_empty(character)
        if act == "invite":
            return await self._party_invite(
                character,
                peer_character_id=peer_character_id,
                peer_name=peer_name,
            )
        if act == "accept":
            return await self._party_accept(character, invite_id=invite_id)
        if act == "reject":
            return await self._party_reject(character, invite_id=invite_id)
        if act == "leave":
            return await self._party_leave(character)
        if act == "kick":
            return await self._party_kick(
                character,
                peer_character_id=peer_character_id,
                peer_name=peer_name,
            )
        raise AppError(code=40000, message="未知队伍动作", http_status=400)

    async def _party_create_empty(self, character: Character) -> dict[str, Any]:
        """Create an open party with only the current character (no force-join)."""
        existing = await self._active_party_for(character.id)
        if existing is not None:
            raise AppError(code=40000, message="已在队伍中", http_status=400)
        party = PartySession(leader_character_id=character.id, status="open")
        self._session.add(party)
        await self._session.flush()
        self._session.add(PartyMember(party_id=party.id, character_id=character.id))
        await self._session.flush()
        logger.info("party create id=%s leader=%s", party.id, character.id)
        public = await self._party_public(party)
        await self._push_party_update_to_characters(
            [character.id],
            {"event": "created", "party": public},
        )
        return {
            "message": "已创建队伍",
            "party": public,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    async def _party_invite(
        self,
        character: Character,
        *,
        peer_character_id: int | None,
        peer_name: str | None,
    ) -> dict[str, Any]:
        """
        Invite a peer into the inviter's open party (create party if needed).

        Gates: both online (or DEV assume), optionally friends, invitee not in party.
        """
        peer = await self._resolve_character(peer_character_id, peer_name)
        if peer.id == character.id:
            raise AppError(code=40000, message="不可邀请自己", http_status=400)

        # 双方须在线（开发环境可 party_dev_assume_online）
        if not self.is_character_online_for_party(character.id):
            raise AppError(code=40000, message="你当前不在线，无法发出邀请", http_status=400)
        if not self.is_character_online_for_party(peer.id):
            raise AppError(code=40000, message="对方不在线，无法邀请", http_status=400)

        cfg = self._cfg()
        if bool(getattr(cfg, "party_require_friend", True)):
            friends = FriendService(self._session)
            if not await friends.are_friends(character.id, peer.id):
                raise AppError(code=40000, message="须先结为道友才能组队邀请", http_status=400)

        peer_party = await self._active_party_for(peer.id)
        if peer_party is not None:
            raise AppError(code=40000, message="对方已在其他队伍", http_status=400)

        # 邀请人须有开放队伍且本人为队长（无队则先建空队，建队者即队长）
        party = await self._active_party_for(character.id)
        if party is None:
            party = PartySession(leader_character_id=character.id, status="open")
            self._session.add(party)
            await self._session.flush()
            self._session.add(PartyMember(party_id=party.id, character_id=character.id))
            await self._session.flush()
        elif int(party.leader_character_id) != int(character.id):
            raise AppError(code=40000, message="仅队长可邀请队友", http_status=403)

        # 同人 pending 邀请：刷新过期时间，避免刷屏多条
        existing_invite = (
            await self._session.execute(
                select(PartyInvite).where(
                    PartyInvite.inviter_id == character.id,
                    PartyInvite.invitee_id == peer.id,
                    PartyInvite.status == "pending",
                ),
            )
        ).scalar_one_or_none()
        expire_sec = int(getattr(cfg, "party_invite_expire_sec", 120) or 0)
        expires_at = (
            now_utc() + timedelta(seconds=expire_sec) if expire_sec > 0 else None
        )
        if existing_invite is not None:
            existing_invite.party_id = party.id
            existing_invite.expires_at = expires_at
            invite = existing_invite
        else:
            invite = PartyInvite(
                inviter_id=character.id,
                invitee_id=peer.id,
                party_id=party.id,
                status="pending",
                expires_at=expires_at,
            )
            self._session.add(invite)
        await self._session.flush()

        invite_public = await self._invite_public(invite)
        logger.info(
            "party invite id=%s party=%s inviter=%s invitee=%s",
            invite.id,
            party.id,
            character.id,
            peer.id,
        )
        # 推给被邀请人
        await self._push_to_character(peer.id, TYPE_PARTY_INVITE, invite_public)
        await self._push_party_update_to_characters(
            [character.id, peer.id],
            {"event": "invite", "invite": invite_public, "party": await self._party_public(party)},
        )
        return {
            "message": f"已邀请「{peer.name}」入队，等待对方确认",
            "party": await self._party_public(party),
            "invite": invite_public,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    async def _party_accept(
        self,
        character: Character,
        *,
        invite_id: int | None,
    ) -> dict[str, Any]:
        """Invitee accepts: add PartyMember and mark invite accepted."""
        invite = await self._load_pending_invite_for_invitee(character, invite_id)
        if await self._active_party_for(character.id) is not None:
            raise AppError(code=40000, message="已在队伍中", http_status=400)

        party_id = invite.party_id
        if party_id is None:
            raise AppError(code=40000, message="邀请无效（无队伍）", http_status=400)
        party = await self._session.get(PartySession, int(party_id))
        if party is None or party.status != "open":
            invite.status = "cancelled"
            await self._session.flush()
            raise AppError(code=40000, message="队伍已解散", http_status=400)

        # 防止重复成员
        existing_member = (
            await self._session.execute(
                select(PartyMember).where(
                    PartyMember.party_id == party.id,
                    PartyMember.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if existing_member is None:
            self._session.add(PartyMember(party_id=party.id, character_id=character.id))
        invite.status = "accepted"
        await self._session.flush()

        public = await self._party_public(party)
        logger.info(
            "party accept invite=%s party=%s invitee=%s",
            invite.id,
            party.id,
            character.id,
        )
        member_ids = [m["character_id"] for m in public["members"]]
        await self._push_party_update_to_characters(
            member_ids,
            {"event": "accepted", "invite_id": invite.id, "party": public},
        )
        return {
            "message": "已加入队伍",
            "party": public,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    async def _party_reject(
        self,
        character: Character,
        *,
        invite_id: int | None,
    ) -> dict[str, Any]:
        """Invitee rejects a pending invite."""
        invite = await self._load_pending_invite_for_invitee(character, invite_id)
        invite.status = "rejected"
        await self._session.flush()
        invite_public = await self._invite_public(invite)
        logger.info("party reject invite=%s invitee=%s", invite.id, character.id)
        await self._push_party_update_to_characters(
            [invite.inviter_id, character.id],
            {"event": "rejected", "invite": invite_public, "party": None},
        )
        return {
            "message": "已拒绝组队邀请",
            "party": None,
            "invite": invite_public,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    async def _party_leave(self, character: Character) -> dict[str, Any]:
        """Leave current party; disband or transfer leadership as needed."""
        party = await self._active_party_for(character.id)
        if party is None:
            raise AppError(code=40000, message="不在队伍中", http_status=400)
        member = (
            await self._session.execute(
                select(PartyMember).where(
                    PartyMember.party_id == party.id,
                    PartyMember.character_id == character.id,
                ),
            )
        ).scalar_one_or_none()
        if member is not None:
            await self._session.delete(member)
        await self._session.flush()
        left = (
            await self._session.execute(
                select(PartyMember).where(PartyMember.party_id == party.id),
            )
        ).scalars().all()
        notify_ids = [int(m.character_id) for m in left] + [character.id]
        if not left:
            party.status = "disbanded"
            party.disbanded_at = now_utc()
            # 解散时取消该队未决邀请
            await self._cancel_pending_invites_for_party(party.id)
        elif party.leader_character_id == character.id and left:
            # 队长离队：移交首位成员
            party.leader_character_id = int(left[0].character_id)
        await self._session.flush()
        # 清本角色该队伍未读
        pref = build_party_ref(party.id)
        await self._clear_unread(character.id, pref.channel_ref)
        remaining_public = (
            await self._party_public(party) if party.status == "open" else None
        )
        await self._push_party_update_to_characters(
            notify_ids,
            {
                "event": "left",
                "left_character_id": character.id,
                "party": remaining_public,
            },
        )
        return {
            "message": "已离队",
            "party": None,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    async def _party_kick(
        self,
        character: Character,
        *,
        peer_character_id: int | None,
        peer_name: str | None,
    ) -> dict[str, Any]:
        """Leader kicks a member out of the open party."""
        party = await self._active_party_for(character.id)
        if party is None:
            raise AppError(code=40000, message="不在队伍中", http_status=400)
        if int(party.leader_character_id) != int(character.id):
            raise AppError(code=40000, message="仅队长可踢出队友", http_status=403)
        target = await self._resolve_character(peer_character_id, peer_name)
        if int(target.id) == int(character.id):
            raise AppError(code=40000, message="不可踢出自己，请使用离队", http_status=400)
        member = (
            await self._session.execute(
                select(PartyMember).where(
                    PartyMember.party_id == party.id,
                    PartyMember.character_id == target.id,
                ),
            )
        ).scalar_one_or_none()
        if member is None:
            raise AppError(code=40000, message="对方不在本队", http_status=400)
        await self._session.delete(member)
        await self._session.flush()
        pref = build_party_ref(party.id)
        await self._clear_unread(target.id, pref.channel_ref)
        left = (
            await self._session.execute(
                select(PartyMember).where(PartyMember.party_id == party.id),
            )
        ).scalars().all()
        notify_ids = [int(m.character_id) for m in left] + [int(target.id)]
        public = await self._party_public(party)
        logger.info(
            "party kick party=%s leader=%s target=%s",
            party.id,
            character.id,
            target.id,
        )
        await self._push_party_update_to_characters(
            notify_ids,
            {
                "event": "kicked",
                "kicked_character_id": target.id,
                "party": public,
            },
        )
        return {
            "message": f"已将「{target.name}」移出队伍",
            "party": public,
            "pending_invites": await self._pending_invites_for(character.id),
        }

    # ----- helpers -----

    async def _resolve_send_target(
        self,
        character: Character,
        *,
        channel_type: str,
        channel_ref: str | None,
        peer_character_id: int | None,
        peer_name: str | None,
    ):
        if channel_ref:
            cref = parse_channel_ref(channel_ref)
            if cref is None or cref.channel_type != channel_type:
                raise AppError(code=40000, message="频道引用与类型不符", http_status=400)
            if channel_type == "dm":
                await self._membership.assert_dm_policy(
                    character,
                    await self._peer_from_dm(cref, character.id),
                    require_friend=bool(self._cfg().dm_require_friend),
                )
            return cref
        if channel_type == "world":
            return build_world_ref(line_id=str(self._cfg().world_line_id or "default"))
        if channel_type == "sect":
            if character.sect_id is None:
                raise AppError(code=40130, message="未入宗不可进宗门频", http_status=403)
            return build_sect_ref(int(character.sect_id))
        if channel_type == "dm":
            peer = await self._resolve_character(peer_character_id, peer_name)
            await self._membership.assert_dm_policy(
                character,
                peer,
                require_friend=bool(self._cfg().dm_require_friend),
            )
            return build_dm_ref(character.id, peer.id)
        if channel_type == "party":
            party = await self._active_party_for(character.id)
            if party is None:
                raise AppError(code=40130, message="尚未组队", http_status=403)
            return build_party_ref(party.id)
        if channel_type == "mentor":
            from app.services.mentor_service import MentorService

            bond = await MentorService(self._session).get_active_bond_for(character.id)
            if bond is None:
                raise AppError(code=40130, message="尚未结成师徒", http_status=403)
            return build_mentor_ref(bond.id)
        raise AppError(code=40000, message="不支持的频道类型", http_status=400)

    async def _peer_from_dm(self, cref, self_id: int) -> Character:
        other = cref.high_id if cref.low_id == self_id else cref.low_id
        ch = await self._session.get(Character, int(other))
        if ch is None:
            raise AppError(code=40000, message="私聊对象不存在", http_status=404)
        return ch

    async def _resolve_character(
        self,
        character_id: int | None,
        name: str | None,
    ) -> Character:
        if character_id is not None:
            ch = await self._session.get(Character, int(character_id))
            if ch is None:
                raise AppError(code=40000, message="目标角色不存在", http_status=404)
            return ch
        nm = (name or "").strip()
        if not nm:
            raise AppError(code=40000, message="请提供目标角色 id 或道号", http_status=400)
        ch = (
            await self._session.execute(select(Character).where(Character.name == nm))
        ).scalar_one_or_none()
        if ch is None:
            raise AppError(code=40000, message=f"找不到道号「{nm}」", http_status=404)
        return ch

    def _assert_rate(self, character_id: int) -> None:
        cfg = self._cfg()
        window = float(cfg.rate_window_sec or 10)
        max_n = int(cfg.rate_max_messages or 5)
        now = time.monotonic()
        bucket = _RATE_BUCKETS[character_id]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= max_n:
            raise AppError(code=40131, message="发言过快，请稍后再试", http_status=429)
        bucket.append(now)

    async def _assert_not_muted(self, character_id: int, channel_ref: str) -> None:
        now = now_utc()
        rows = (
            await self._session.execute(
                select(ChatMute).where(ChatMute.character_id == character_id),
            )
        ).scalars().all()
        for row in rows:
            if row.until_at is not None and now >= ensure_aware_utc(row.until_at):
                continue
            ref = str(row.channel_ref or "")
            if ref == "" or ref == channel_ref:
                raise AppError(
                    code=40132,
                    message=row.reason_zh or "禁言中",
                    http_status=403,
                )

    async def _bump_unread(self, character_id: int, channel_ref: str, *, delta: int) -> None:
        row = (
            await self._session.execute(
                select(ChatUnread).where(
                    ChatUnread.character_id == character_id,
                    ChatUnread.channel_ref == channel_ref,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = ChatUnread(
                character_id=character_id,
                channel_ref=channel_ref,
                unread_count=0,
            )
            self._session.add(row)
            await self._session.flush()
        row.unread_count = max(0, int(row.unread_count) + int(delta))
        await self._session.flush()

    async def _clear_unread(self, character_id: int, channel_ref: str) -> None:
        row = (
            await self._session.execute(
                select(ChatUnread).where(
                    ChatUnread.character_id == character_id,
                    ChatUnread.channel_ref == channel_ref,
                ),
            )
        ).scalar_one_or_none()
        if row is not None:
            row.unread_count = 0
            await self._session.flush()

    async def _unread_for(self, character_id: int, channel_ref: str) -> int:
        row = (
            await self._session.execute(
                select(ChatUnread).where(
                    ChatUnread.character_id == character_id,
                    ChatUnread.channel_ref == channel_ref,
                ),
            )
        ).scalar_one_or_none()
        return int(row.unread_count) if row else 0

    async def _active_party_for(self, character_id: int) -> PartySession | None:
        row = (
            await self._session.execute(
                select(PartySession)
                .join(PartyMember, PartyMember.party_id == PartySession.id)
                .where(
                    PartyMember.character_id == character_id,
                    PartySession.status == "open",
                )
                .limit(1),
            )
        ).scalar_one_or_none()
        return row

    def is_character_online_for_party(self, character_id: int) -> bool:
        """
        Online gate for party invite (Presence facade).

        Args:
            character_id: Character primary key.

        Returns:
            True if considered online for invite purposes.
        """
        from app.services.presence_service import PresencePurpose, get_presence

        return get_presence().is_online_for(PresencePurpose.PARTY, int(character_id))

    async def _expire_stale_party_invites(self) -> None:
        """Lazily mark pending invites past expires_at as expired."""
        now = now_utc()
        rows = (
            await self._session.execute(
                select(PartyInvite).where(PartyInvite.status == "pending"),
            )
        ).scalars().all()
        changed = False
        for row in rows:
            if row.expires_at is None:
                continue
            if now >= ensure_aware_utc(row.expires_at):
                row.status = "expired"
                changed = True
        if changed:
            await self._session.flush()

    async def _cancel_pending_invites_for_party(self, party_id: int) -> None:
        """Cancel all pending invites targeting a disbanded party."""
        rows = (
            await self._session.execute(
                select(PartyInvite).where(
                    PartyInvite.party_id == int(party_id),
                    PartyInvite.status == "pending",
                ),
            )
        ).scalars().all()
        for row in rows:
            row.status = "cancelled"
        if rows:
            await self._session.flush()

    async def _load_pending_invite_for_invitee(
        self,
        character: Character,
        invite_id: int | None,
    ) -> PartyInvite:
        """
        Load a pending invite that the current character may accept/reject.

        Args:
            character: Invitee character.
            invite_id: PartyInvite primary key.

        Returns:
            PartyInvite row still in pending status.

        Raises:
            AppError: Missing id, wrong invitee, or not pending.
        """
        if invite_id is None:
            raise AppError(code=40000, message="请提供邀请 id", http_status=400)
        invite = await self._session.get(PartyInvite, int(invite_id))
        if invite is None:
            raise AppError(code=40000, message="邀请不存在", http_status=404)
        if int(invite.invitee_id) != int(character.id):
            raise AppError(code=40000, message="无权处理该邀请", http_status=403)
        if invite.status != "pending":
            raise AppError(code=40000, message="邀请已处理或已失效", http_status=400)
        if invite.expires_at is not None and now_utc() >= ensure_aware_utc(invite.expires_at):
            invite.status = "expired"
            await self._session.flush()
            raise AppError(code=40000, message="邀请已过期", http_status=400)
        return invite

    async def _pending_invites_for(self, character_id: int) -> list[dict[str, Any]]:
        """Incoming pending invites for the character (after lazy expire)."""
        rows = (
            await self._session.execute(
                select(PartyInvite).where(
                    PartyInvite.invitee_id == int(character_id),
                    PartyInvite.status == "pending",
                ),
            )
        ).scalars().all()
        return [await self._invite_public(row) for row in rows]

    async def _invite_public(self, invite: PartyInvite) -> dict[str, Any]:
        """Serialize a party invite for API / WS payloads."""
        inviter = await self._session.get(Character, invite.inviter_id)
        invitee = await self._session.get(Character, invite.invitee_id)
        return {
            "id": invite.id,
            "inviter_id": invite.inviter_id,
            "inviter_name": inviter.name if inviter else str(invite.inviter_id),
            "invitee_id": invite.invitee_id,
            "invitee_name": invitee.name if invitee else str(invite.invitee_id),
            "party_id": invite.party_id,
            "status": invite.status,
            "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
            "created_at": invite.created_at.isoformat() if invite.created_at else None,
        }

    async def _push_to_character(
        self,
        character_id: int,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Push a WS envelope to all authenticated connections of a character."""
        settings = get_settings()
        if not bool(getattr(settings, "chat_ws_push_enabled", True)):
            return
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        hub = get_ws_hub()
        for conn in list(hub._connections.values()):
            if conn.authenticated and conn.character_id == int(character_id):
                await hub.send(conn.conn_id, msg_type, payload)

    async def _push_party_update_to_characters(
        self,
        character_ids: list[int],
        payload: dict[str, Any],
    ) -> None:
        """Broadcast ``party.update`` to distinct character ids."""
        seen: set[int] = set()
        for cid in character_ids:
            if cid in seen:
                continue
            seen.add(int(cid))
            await self._push_to_character(int(cid), TYPE_PARTY_UPDATE, payload)

    async def _channel_public(
        self,
        character: Character,
        *,
        channel_type: str,
        channel_ref: str,
        label_zh: str,
        peer_character_id: int | None = None,
        peer_name: str | None = None,
        party_id: int | None = None,
    ) -> dict[str, Any]:
        ok, reason = await self._membership.can_access(character, channel_ref)
        return {
            "channel_type": channel_type,
            "channel_ref": channel_ref,
            "label_zh": label_zh,
            "can_access": ok,
            "can_send": ok,
            "lock_reason_zh": None if ok else reason,
            "unread": await self._unread_for(character.id, channel_ref) if ok else 0,
            "room_id": room_id_for(channel_ref) if ok else None,
            "peer_character_id": peer_character_id,
            "peer_name": peer_name,
            "party_id": party_id,
        }

    async def _message_public(self, row: ChatMessage) -> dict[str, Any]:
        sender = await self._session.get(Character, row.sender_character_id)
        major_key = str(sender.major_realm) if sender is not None else ""
        major = get_major_realm(major_key) if major_key else None
        return {
            "id": row.id,
            "channel_type": row.channel_type,
            "channel_ref": row.channel_ref,
            "sender_character_id": row.sender_character_id,
            "sender_name": sender.name if sender else str(row.sender_character_id),
            # 前端按大境界给道号上色
            "sender_major_realm": major_key or None,
            "sender_major_realm_name": major.name if major else None,
            "body_zh": row.body_zh,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def _party_public(self, party: PartySession) -> dict[str, Any]:
        """Serialize party with enriched member summaries for teammate inspect."""
        members = (
            await self._session.execute(
                select(PartyMember).where(PartyMember.party_id == party.id),
            )
        ).scalars().all()
        items = []
        for m in members:
            ch = await self._session.get(Character, m.character_id)
            items.append(await self._party_member_public(party, ch, m.character_id))
        pref = build_party_ref(party.id)
        return {
            "id": party.id,
            "status": party.status,
            "leader_character_id": party.leader_character_id,
            "members": items,
            "channel_ref": pref.channel_ref,
            "room_id": pref.room_id,
        }

    async def _party_member_public(
        self,
        party: PartySession,
        ch: Character | None,
        character_id: int,
    ) -> dict[str, Any]:
        """
        Teammate card: realm / status / online / combat / techniques / constitution.

        Args:
            party: Open party session.
            ch: Character row (may be None).
            character_id: Member character id.

        Returns:
            dict: Member summary for party UI.
        """
        from app.services.character_service import CharacterService
        from app.services.realm_config import STATUS_NAMES

        base: dict[str, Any] = {
            "character_id": character_id,
            "name": ch.name if ch else str(character_id),
            "is_leader": int(character_id) == int(party.leader_character_id),
            "major_realm": None,
            "major_realm_name": None,
            "status": None,
            "status_name": None,
            "online": False,
            "cultivation_points": 0,
            "base_atk": 0,
            "base_hp": 0,
            "technique_summary": [],
            "constitution_equipped": [],
        }
        if ch is None:
            return base
        major_key = str(ch.major_realm or "")
        major = get_major_realm(major_key) if major_key else None
        status_key = str(ch.status or "normal")
        base.update(
            {
                "major_realm": major_key or None,
                "major_realm_name": major.name if major else (major_key or None),
                "status": status_key,
                "status_name": STATUS_NAMES.get(status_key, status_key),
                "online": self.is_character_online_for_party(int(ch.id)),
                "cultivation_points": int(ch.cultivation_points or 0),
            },
        )
        try:
            atk, hp, tech_sum, cons_sum = await CharacterService(
                self._session,
            ).build_combat_stats(ch)
            equipped = []
            if isinstance(cons_sum, dict):
                raw_eq = cons_sum.get("equipped") or []
                if isinstance(raw_eq, list):
                    for row in raw_eq:
                        if isinstance(row, dict):
                            name = row.get("name") or row.get("item_name") or row.get("slot")
                            if name:
                                equipped.append(str(name))
                        elif row:
                            equipped.append(str(row))
            base["base_atk"] = int(atk)
            base["base_hp"] = int(hp)
            base["technique_summary"] = list(tech_sum or [])
            base["constitution_equipped"] = equipped
        except Exception:  # noqa: BLE001 — 摘要失败不挡组队
            logger.exception("party member enrich failed character_id=%s", ch.id)
        return base

    async def _push_message(self, room_id: str, public: dict[str, Any]) -> None:
        """房间广播 + 成员/在线直推（不依赖客户端是否订当前房）。"""
        settings = get_settings()
        if not bool(getattr(settings, "chat_ws_push_enabled", True)):
            return
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        hub = get_ws_hub()
        hub.ensure_room(room_id, kind="chat")
        await hub.broadcast_room(room_id, TYPE_CHAT_MESSAGE, public)
        channel_ref = str(public.get("channel_ref") or "")
        if not channel_ref:
            return
        cref = parse_channel_ref(channel_ref)
        if cref is None:
            return
        member_ids = await self._membership.list_member_ids(cref)
        pushed: set[str] = set()
        # 世界频 list_member_ids 为空：改向所有在线鉴权连接直推
        if cref.channel_type == "world" or not member_ids:
            if cref.channel_type == "world":
                for conn in list(hub._connections.values()):
                    if not conn.authenticated:
                        continue
                    if conn.conn_id in pushed:
                        continue
                    await hub.send(conn.conn_id, TYPE_CHAT_MESSAGE, public)
                    pushed.add(conn.conn_id)
                return
        for mid in member_ids:
            for conn in list(hub._connections.values()):
                if not (conn.authenticated and conn.character_id == mid):
                    continue
                if conn.conn_id in pushed:
                    continue
                await hub.send(conn.conn_id, TYPE_CHAT_MESSAGE, public)
                pushed.add(conn.conn_id)

    async def count_dm_unread_peers(self, character_id: int) -> int:
        """有未读私聊的对方人数（按频道计，非消息条数）。"""
        rows = (
            await self._session.execute(
                select(ChatUnread).where(
                    ChatUnread.character_id == character_id,
                    ChatUnread.unread_count > 0,
                    ChatUnread.channel_ref.like("dm:%"),
                ),
            )
        ).scalars().all()
        return len(list(rows))

    async def _push_unread_to_members(self, cref, *, exclude_id: int) -> None:
        settings = get_settings()
        if not bool(getattr(settings, "chat_ws_push_enabled", True)):
            return
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        hub = get_ws_hub()
        member_ids = await self._membership.list_member_ids(cref)
        for mid in member_ids:
            if mid == exclude_id:
                continue
            unread = await self._unread_for(mid, cref.channel_ref)
            total = await self.total_unread(mid)
            dm_peers = await self.count_dm_unread_peers(mid)
            for conn in list(hub._connections.values()):
                if conn.authenticated and conn.character_id == mid:
                    await hub.send(
                        conn.conn_id,
                        TYPE_CHAT_UNREAD,
                        {
                            "channel_ref": cref.channel_ref,
                            "unread": unread,
                            "unread_total": total,
                            "dm_unread_peers": dm_peers,
                        },
                    )
