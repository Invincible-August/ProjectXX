"""
角色本命道与道资源 ORM（M6）。

一道角色一行；周目锁定后 fate_dao_id 不可改，直至轮回清空。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CharacterDao(Base):
    """角色大道状态：本命道、道值、经验、开道会话。"""

    __tablename__ = "character_dao"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_character_dao_character"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 本命道 id；未开道为 null
    fate_dao_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dao_qi: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dao_exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dao_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 开道会话：JSON 字符串存 options / expires
    opening_session_json: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    # 挑战冷却截止
    challenge_cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
