"""聊天 / 队伍 ORM（M7 L4）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatMessage(Base):
    """聊天消息短历史。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    channel_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body_zh: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class ChatMute(Base):
    """禁言记录（频道级或全局）。"""

    __tablename__ = "chat_mutes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 空字符串表示全局禁言
    channel_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    reason_zh: Mapped[str] = mapped_column(String(128), nullable=False, default="禁言中")
    until_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ChatUnread(Base):
    """按角色+频道未读计数。"""

    __tablename__ = "chat_unreads"
    __table_args__ = (
        UniqueConstraint("character_id", "channel_ref", name="uq_chat_unread_char_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PartySession(Base):
    """最小队伍会话（仅服务 party 频）。"""

    __tablename__ = "party_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    leader_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # open | disbanded
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    disbanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartyMember(Base):
    """队伍成员。"""

    __tablename__ = "party_members"
    __table_args__ = (
        UniqueConstraint("party_id", "character_id", name="uq_party_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    party_id: Mapped[int] = mapped_column(
        ForeignKey("party_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PartyInvite(Base):
    """
    Party invite row (invite → accept/reject).

    Status lifecycle: pending → accepted | rejected | expired | cancelled.
    ``party_id`` is set when the inviter already has (or creates) an open party
    at invite time; accept joins that party via ``PartyMember``.
    """

    __tablename__ = "party_invites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable until inviter ensures an open party (usually set on invite)
    party_id: Mapped[int | None] = mapped_column(
        ForeignKey("party_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # pending | accepted | rejected | expired | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
