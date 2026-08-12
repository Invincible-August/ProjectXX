"""
化身仓储：仅查 ORM，避免为读一行而构造完整 AvatarService（含 PlayGate/CharacterService）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.avatar import Avatar


async def fetch_avatar_row(session: AsyncSession, character_id: int) -> Avatar | None:
    """
    按 character_id 查化身行（1:1）。

    参数:
        session: 异步会话。
        character_id: 角色主键。

    返回:
        Avatar 或 None。
    """
    result = await session.execute(
        select(Avatar).where(Avatar.character_id == character_id).limit(1),
    )
    return result.scalar_one_or_none()
