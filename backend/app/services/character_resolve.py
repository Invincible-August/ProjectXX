"""
按角色 id / 道号 / 对外账号号 / 数据库 id 解析 Character。

组队邀请、面交、道友申请等入口共用，避免各服务各自实现分叉。
``name`` 可为道号、``M/P/T/G``+7 位对外 ``user_id``，或纯数字数据库 id。
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.account import PUBLIC_UID_LENGTH, USER_ID_PREFIXES
from app.db.models import Character, User
from app.schemas.common import AppError

# 对外账号号：前缀 + 7 数字
_PUBLIC_UID_RE = re.compile(
    rf"^[{''.join(sorted(USER_ID_PREFIXES))}]\d{{{PUBLIC_UID_LENGTH - 1}}}$",
)


async def resolve_character_ref(
    session: AsyncSession,
    *,
    character_id: int | None = None,
    name: str | None = None,
    user_id: int | None = None,
    not_found_zh: str = "目标",
) -> Character:
    """
    解析目标角色。

    优先级：``character_id`` → ``user_id``（数据库 id）→ ``name``（道号 /
    public_uid / 纯数字数据库 id）。

    Args:
        session: 异步会话。
        character_id: 角色表主键。
        name: 道号；或对外账号号；或纯数字数据库账号 id。
        user_id: 玩家账号数据库 id（``users.id`` / ``characters.user_id``）。
        not_found_zh: 错误文案里的对象称呼（目标/对方）。

    Returns:
        Character: 命中的角色行。

    Raises:
        AppError: 未提供任何标识或查无。
    """
    if character_id is not None:
        ch = await session.get(Character, int(character_id))
        if ch is None:
            raise AppError(
                code=40000,
                message=f"{not_found_zh}角色不存在",
                http_status=404,
            )
        return ch

    if user_id is not None:
        ch = await session.scalar(
            select(Character).where(Character.user_id == int(user_id)).limit(1),
        )
        if ch is None:
            raise AppError(
                code=40000,
                message=f"找不到 user_id={int(user_id)} 对应角色",
                http_status=404,
            )
        return ch

    raw = (name or "").strip()
    if not raw:
        raise AppError(
            code=40000,
            message=f"请提供{not_found_zh}角色 id、道号或 user_id",
            http_status=400,
        )

    ch = await session.scalar(
        select(Character).where(Character.name == raw).limit(1),
    )
    if ch is not None:
        return ch

    # 对外账号号 M/P/T/G + 7 位
    if _PUBLIC_UID_RE.fullmatch(raw.upper()):
        uid_row = await session.scalar(
            select(User).where(User.public_uid == raw.upper()).limit(1),
        )
        if uid_row is not None:
            ch = await session.scalar(
                select(Character).where(Character.user_id == uid_row.id).limit(1),
            )
            if ch is not None:
                return ch
        raise AppError(
            code=40000,
            message=f"找不到道号或 user_id「{raw}」",
            http_status=404,
        )

    # 道号未命中：纯数字视为数据库账号 id
    if raw.isdigit():
        uid = int(raw)
        ch = await session.scalar(
            select(Character).where(Character.user_id == uid).limit(1),
        )
        if ch is not None:
            return ch
        raise AppError(
            code=40000,
            message=f"找不到道号或 user_id「{raw}」",
            http_status=404,
        )

    raise AppError(
        code=40000,
        message=f"找不到道号「{raw}」",
        http_status=404,
    )
