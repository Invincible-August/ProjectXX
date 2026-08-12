"""
WebSocket 路由：鉴权、心跳、房间加入/离开。

URL: WS /api/v1/ws
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.models import Character, User
from app.db.session import AsyncSessionLocal
from app.domain.ws_protocol import (
    TYPE_AUTH,
    TYPE_PING,
    TYPE_ROOM_JOIN,
    TYPE_ROOM_LEAVE,
    TYPE_WORLD_ENV,
    parse_envelope,
)
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


async def _resolve_user_from_token(token: str) -> tuple[User, Character | None] | None:
    """JWT → User + 可选角色。"""
    try:
        claims = decode_token(token, expected_type="access")
        user_id = int(claims["sub"])
    except Exception:  # noqa: BLE001
        return None
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or not getattr(user, "is_active", True):
            return None
        result = await session.execute(select(Character).where(Character.user_id == user_id))
        character = result.scalar_one_or_none()
        # detach-ish：返回 id 即可
        return user, character


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None, description="DEV 可用 query token"),
) -> None:
    """
    长连接入口。

    鉴权：优先首帧 ``auth``；DEV 允许 ``?token=``。
    """
    settings = get_settings()
    hub = get_ws_hub()
    if not settings.ws_enabled:
        await websocket.close(code=4403, reason="WS disabled")
        return

    await websocket.accept()
    conn_id = uuid.uuid4().hex
    await hub.register(conn_id, websocket)
    await hub.send_hello(conn_id)

    # query token（仅开发便利）
    if token:
        resolved = await _resolve_user_from_token(token)
        if resolved is None:
            await hub.send_error(conn_id, "鉴权失败：token 无效", code=40092)
            await websocket.close(code=4401, reason="auth failed")
            await hub.unregister(conn_id)
            return
        user, character = resolved
        await hub.authenticate(
            conn_id,
            user_id=user.id,
            character_id=character.id if character else None,
        )

    try:
        while True:
            raw: Any = await websocket.receive_json()
            envelope = parse_envelope(raw)
            if envelope is None:
                await hub.send_error(conn_id, "非法消息格式", code=40000)
                continue
            msg_type = envelope["type"]
            payload = envelope["payload"]

            if msg_type == TYPE_AUTH:
                tok = str(payload.get("token") or "")
                resolved = await _resolve_user_from_token(tok)
                if resolved is None:
                    await hub.send_error(conn_id, "鉴权失败：token 无效", code=40092)
                    await websocket.close(code=4401, reason="auth failed")
                    break
                user, character = resolved
                await hub.authenticate(
                    conn_id,
                    user_id=user.id,
                    character_id=character.id if character else None,
                )
                await hub.send(conn_id, "sys.hello", {"authenticated": True})
                continue

            conn = hub._connections.get(conn_id)
            if conn is None or not conn.authenticated:
                await hub.send_error(conn_id, "请先鉴权", code=40092)
                continue

            if msg_type == TYPE_PING:
                await hub.handle_ping(conn_id, payload)
                continue

            if msg_type == TYPE_ROOM_JOIN:
                room_id = str(payload.get("room_id") or "")
                kind = str(payload.get("kind") or "generic")
                if not room_id:
                    await hub.send_error(conn_id, "缺少 room_id", code=40000)
                    continue
                # 防注入：道主赛会直播房须为合法格式；状态仍以 HTTP 权威为准
                if room_id.startswith("dao_lord:match:"):
                    suffix = room_id.split("dao_lord:match:", 1)[-1]
                    if not suffix.isdigit():
                        await hub.send_error(conn_id, "非法赛会房间", code=40000)
                        continue
                # 聊天房：校验频道成员（D11）
                if room_id.startswith("chat:"):
                    char_id = conn.character_id
                    if char_id is None:
                        await hub.send_error(conn_id, "无角色不可进聊天房", code=40130)
                        continue
                    async with AsyncSessionLocal() as session:
                        character = await session.get(Character, int(char_id))
                        if character is None:
                            await hub.send_error(conn_id, "角色不存在", code=40130)
                            continue
                        from app.domain.channel_membership import ChannelMembership

                        ok, reason = await ChannelMembership(session).can_access(
                            character,
                            room_id,
                        )
                        if not ok:
                            await hub.send_error(
                                conn_id,
                                reason or "频道无权限",
                                code=40130,
                            )
                            continue
                    kind = "chat"
                room = await hub.join_room(conn_id, room_id, kind=kind)
                if room is None:
                    await hub.send_error(conn_id, "加入房间失败", code=40093)
                continue

            if msg_type == TYPE_ROOM_LEAVE:
                room_id = str(payload.get("room_id") or "")
                if room_id:
                    await hub.leave_room(conn_id, room_id)
                continue

            # 客户端请求推一条环境（DEV）；正式由日历服务调用 hub.broadcast_world
            if msg_type == "world.env.subscribe":
                await hub.join_room(conn_id, "world_broadcast", kind="world_broadcast")
                continue

            if msg_type == TYPE_WORLD_ENV:
                # 客户端不应推 env；忽略
                continue

            await hub.send_error(conn_id, f"未知消息类型：{msg_type}", code=40000)
    except WebSocketDisconnect:
        logger.info("ws disconnect conn_id=%s", conn_id)
    except Exception:  # noqa: BLE001
        logger.exception("ws error conn_id=%s", conn_id)
    finally:
        await hub.unregister(conn_id)
