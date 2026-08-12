"""聊天频道成员可见性门面（M7 L4 · D11）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Character
from app.db.models.chat import PartyMember, PartySession
from app.db.models.sect import SectMember
from app.domain.trade_rules import friendship_pair_key
from app.services.friend_service import FriendService


# M7 落地五频；region/faction 预留 M9
ACTIVE_CHANNEL_TYPES = ("world", "sect", "dm", "mentor", "party")
RESERVED_CHANNEL_TYPES = ("region", "faction")


@dataclass(frozen=True)
class ChannelRef:
    """解析后的频道引用。"""

    channel_type: str
    channel_ref: str
    room_id: str
    # 可选载荷
    sect_id: int | None = None
    low_id: int | None = None
    high_id: int | None = None
    party_id: int | None = None
    mentor_bond_id: int | None = None


def room_id_for(channel_ref: str) -> str:
    """WS 房间 id：``chat:{channel_ref}``。"""
    ref = str(channel_ref or "").strip()
    if ref.startswith("chat:"):
        return ref
    return f"chat:{ref}"


def build_world_ref(*, line_id: str = "default") -> ChannelRef:
    """世界频道引用。"""
    line = (line_id or "default").strip() or "default"
    # 单线时简化为 world；多线 world:{line}
    cref = "world" if line == "default" else f"world:{line}"
    return ChannelRef(
        channel_type="world",
        channel_ref=cref,
        room_id=room_id_for(cref),
    )


def build_sect_ref(sect_id: int) -> ChannelRef:
    """宗门频道。"""
    cref = f"sect:{int(sect_id)}"
    return ChannelRef(
        channel_type="sect",
        channel_ref=cref,
        room_id=room_id_for(cref),
        sect_id=int(sect_id),
    )


def build_dm_ref(a: int, b: int) -> ChannelRef:
    """私聊双方会话（有序键）。"""
    low, high = friendship_pair_key(a, b)
    cref = f"dm:{low}:{high}"
    return ChannelRef(
        channel_type="dm",
        channel_ref=cref,
        room_id=room_id_for(cref),
        low_id=low,
        high_id=high,
    )


def build_party_ref(party_id: int) -> ChannelRef:
    """队伍频道。"""
    cref = f"party:{int(party_id)}"
    return ChannelRef(
        channel_type="party",
        channel_ref=cref,
        room_id=room_id_for(cref),
        party_id=int(party_id),
    )


def build_mentor_ref(bond_id: int) -> ChannelRef:
    """师承频道（L6 结缘后可用）。"""
    cref = f"mentor:{int(bond_id)}"
    return ChannelRef(
        channel_type="mentor",
        channel_ref=cref,
        room_id=room_id_for(cref),
        mentor_bond_id=int(bond_id),
    )


def parse_channel_ref(raw: str) -> ChannelRef | None:
    """
    解析 ``channel_ref`` 字符串。

    Args:
        raw: 如 ``world`` / ``sect:3`` / ``dm:1:2``。

    Returns:
        ChannelRef | None: 无法解析则 None。
    """
    text = str(raw or "").strip()
    if text.startswith("chat:"):
        text = text[5:]
    if not text:
        return None
    if text == "world" or text.startswith("world:"):
        return ChannelRef(channel_type="world", channel_ref=text, room_id=room_id_for(text))
    if text.startswith("sect:"):
        try:
            sid = int(text.split(":", 1)[1])
        except (TypeError, ValueError):
            return None
        return build_sect_ref(sid)
    if text.startswith("dm:"):
        parts = text.split(":")
        if len(parts) != 3:
            return None
        try:
            low, high = int(parts[1]), int(parts[2])
        except (TypeError, ValueError):
            return None
        if low > high:
            low, high = high, low
        return ChannelRef(
            channel_type="dm",
            channel_ref=f"dm:{low}:{high}",
            room_id=room_id_for(f"dm:{low}:{high}"),
            low_id=low,
            high_id=high,
        )
    if text.startswith("party:"):
        try:
            pid = int(text.split(":", 1)[1])
        except (TypeError, ValueError):
            return None
        return build_party_ref(pid)
    if text.startswith("mentor:"):
        try:
            bid = int(text.split(":", 1)[1])
        except (TypeError, ValueError):
            return None
        return build_mentor_ref(bid)
    if text in RESERVED_CHANNEL_TYPES or text.startswith(("region:", "faction:")):
        return ChannelRef(channel_type=text.split(":", 1)[0], channel_ref=text, room_id=room_id_for(text))
    return None


def apply_sensitive_filter(body: str, words: list[str], *, enabled: bool) -> str:
    """敏感词占位：命中替换为等长 *。"""
    if not enabled:
        return body
    out = body
    for word in words:
        w = str(word or "").strip()
        if not w:
            continue
        if w in out:
            out = out.replace(w, "*" * len(w))
    return out


class ChannelMembership:
    """
    频道准入与成员列举（供聊天 / 传承共用）。

    无 IO 纯函数见模块级；本类持会话做查询。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def can_access(self, character: Character, channel_ref: str | ChannelRef) -> tuple[bool, str | None]:
        """
        是否可进频道（读/发）。

        Args:
            character: 角色。
            channel_ref: 引用或字符串。

        Returns:
            tuple: (允许, 中文拒绝原因)。
        """
        cref = (
            channel_ref
            if isinstance(channel_ref, ChannelRef)
            else parse_channel_ref(str(channel_ref))
        )
        if cref is None:
            return False, "频道不存在"
        ctype = cref.channel_type
        if ctype in RESERVED_CHANNEL_TYPES:
            return False, "该频道尚未开放"
        if ctype == "world":
            return True, None
        if ctype == "sect":
            if character.sect_id is None:
                return False, "未入宗不可进宗门频"
            if cref.sect_id is not None and int(character.sect_id) != int(cref.sect_id):
                return False, "非本宗频道"
            member = (
                await self._session.execute(
                    select(SectMember).where(SectMember.character_id == character.id),
                )
            ).scalar_one_or_none()
            if member is None:
                return False, "非宗门成员"
            return True, None
        if ctype == "dm":
            if cref.low_id is None or cref.high_id is None:
                return False, "私聊频道无效"
            cid = int(character.id)
            if cid not in (int(cref.low_id), int(cref.high_id)):
                return False, "非会话双方"
            return True, None
        if ctype == "party":
            if cref.party_id is None:
                return False, "队伍频道无效"
            row = (
                await self._session.execute(
                    select(PartyMember).where(
                        PartyMember.party_id == int(cref.party_id),
                        PartyMember.character_id == character.id,
                    ),
                )
            ).scalar_one_or_none()
            if row is None:
                return False, "非队伍成员"
            party = await self._session.get(PartySession, int(cref.party_id))
            if party is None or party.status != "open":
                return False, "队伍已解散"
            return True, None
        if ctype == "mentor":
            if cref.mentor_bond_id is None:
                return False, "师承频道无效"
            from app.db.models.mentor import MentorBond

            bond = await self._session.get(MentorBond, int(cref.mentor_bond_id))
            if bond is None or bond.status != "active":
                # 解除后：只读策略由调用方决定；默认不可发=无权限
                return False, "尚未结成师徒或已解除"
            cid = int(character.id)
            if cid not in (int(bond.master_character_id), int(bond.apprentice_character_id)):
                return False, "非本对师徒"
            return True, None
        return False, "未知频道"

    async def list_member_ids(self, channel_ref: str | ChannelRef) -> list[int]:
        """
        列举频道成员 id（传承广播用）。

        Args:
            channel_ref: 频道引用。

        Returns:
            list[int]: 成员角色 id；世界频返回空（由调用方改走在线广播）。
        """
        cref = (
            channel_ref
            if isinstance(channel_ref, ChannelRef)
            else parse_channel_ref(str(channel_ref))
        )
        if cref is None:
            return []
        if cref.channel_type == "world":
            return []
        if cref.channel_type == "sect" and cref.sect_id is not None:
            rows = (
                await self._session.execute(
                    select(SectMember.character_id).where(
                        SectMember.sect_id == int(cref.sect_id),
                    ),
                )
            ).scalars().all()
            return [int(x) for x in rows]
        if cref.channel_type == "dm" and cref.low_id is not None and cref.high_id is not None:
            return [int(cref.low_id), int(cref.high_id)]
        if cref.channel_type == "party" and cref.party_id is not None:
            rows = (
                await self._session.execute(
                    select(PartyMember.character_id).where(
                        PartyMember.party_id == int(cref.party_id),
                    ),
                )
            ).scalars().all()
            return [int(x) for x in rows]
        if cref.channel_type == "mentor" and cref.mentor_bond_id is not None:
            from app.db.models.mentor import MentorBond

            bond = await self._session.get(MentorBond, int(cref.mentor_bond_id))
            if bond is None or bond.status != "active":
                return []
            return [int(bond.master_character_id), int(bond.apprentice_character_id)]
        return []

    async def assert_dm_policy(
        self,
        a: Character,
        b: Character,
        *,
        require_friend: bool,
    ) -> None:
        """私聊建会话策略（可选道友）。"""
        from app.schemas.common import AppError

        if a.id == b.id:
            raise AppError(code=40000, message="不可与自己私聊", http_status=400)
        if require_friend:
            ok = await FriendService(self._session).are_friends(a.id, b.id)
            if not ok:
                raise AppError(code=40130, message="仅可与道友私聊", http_status=403)
