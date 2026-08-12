"""
进程内 WebSocket Hub：连接、心跳、房间广播。

多 worker 时可通过 WS_REDIS_URL 扩展（本阶段单进程默认）。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.core.config import get_settings
from app.domain.ws_protocol import (
    TYPE_PONG,
    TYPE_SYS_ERROR,
    TYPE_SYS_HELLO,
    make_envelope,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


@dataclass
class WsConnection:
    """单条 WebSocket 连接状态。"""

    conn_id: str
    websocket: WebSocket
    user_id: int | None = None
    character_id: int | None = None
    authenticated: bool = False
    seq: int = 0
    last_ping_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rooms: set[str] = field(default_factory=set)

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


@dataclass
class WsRoom:
    """房间：成员 conn_id 集合。"""

    room_id: str
    kind: str
    members: set[str] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=dict)


class WsHubService:
    """进程内房间中枢（单例）。"""

    def __init__(self) -> None:
        self._connections: dict[str, WsConnection] = {}
        self._rooms: dict[str, WsRoom] = {}
        self._lock = asyncio.Lock()

    def enabled(self) -> bool:
        return bool(get_settings().ws_enabled)

    async def register(self, conn_id: str, websocket: WebSocket) -> WsConnection:
        """登记新连接。"""
        conn = WsConnection(conn_id=conn_id, websocket=websocket)
        async with self._lock:
            self._connections[conn_id] = conn
        logger.info("ws register conn_id=%s", conn_id)
        return conn

    async def unregister(self, conn_id: str) -> None:
        """断开并离开所有房间。"""
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn is None:
                return
            for room_id in list(conn.rooms):
                room = self._rooms.get(room_id)
                if room:
                    room.members.discard(conn_id)
                    if not room.members:
                        self._rooms.pop(room_id, None)
        logger.info("ws unregister conn_id=%s", conn_id)

    async def authenticate(
        self,
        conn_id: str,
        *,
        user_id: int,
        character_id: int | None,
    ) -> None:
        """标记已鉴权。"""
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                return
            conn.user_id = user_id
            conn.character_id = character_id
            conn.authenticated = True

    async def send(self, conn_id: str, msg_type: str, payload: dict[str, Any] | None = None) -> None:
        """向单连接发送信封。"""
        conn = self._connections.get(conn_id)
        if conn is None:
            return
        envelope = make_envelope(msg_type, payload, seq=conn.next_seq())
        try:
            await conn.websocket.send_json(envelope)
        except Exception:  # noqa: BLE001
            logger.warning("ws send failed conn_id=%s type=%s", conn_id, msg_type)

    async def send_hello(self, conn_id: str) -> None:
        """连接成功问候。"""
        await self.send(
            conn_id,
            TYPE_SYS_HELLO,
            {"server_time": utc_now_iso(), "heartbeat_seconds": get_settings().ws_heartbeat_seconds},
        )

    async def send_error(self, conn_id: str, message: str, *, code: int = 40092) -> None:
        """可展示中文错误。"""
        await self.send(conn_id, TYPE_SYS_ERROR, {"code": code, "message": message})

    async def handle_ping(self, conn_id: str, payload: dict[str, Any]) -> None:
        """心跳：更新时间并回 pong。"""
        conn = self._connections.get(conn_id)
        if conn is None:
            return
        conn.last_ping_at = datetime.now(timezone.utc)
        await self.send(conn_id, TYPE_PONG, {"echo": payload.get("echo")})

    async def join_room(
        self,
        conn_id: str,
        room_id: str,
        *,
        kind: str = "generic",
    ) -> WsRoom | None:
        """加入房间。"""
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None or not conn.authenticated:
                return None
            room = self._rooms.get(room_id)
            if room is None:
                room = WsRoom(room_id=room_id, kind=kind)
                self._rooms[room_id] = room
            room.members.add(conn_id)
            conn.rooms.add(room_id)
        await self.broadcast_room(
            room_id,
            "room.state",
            {"room_id": room_id, "kind": kind, "member_count": len(self._rooms[room_id].members)},
        )
        return self._rooms.get(room_id)

    async def leave_room(self, conn_id: str, room_id: str) -> None:
        """离开房间。"""
        async with self._lock:
            conn = self._connections.get(conn_id)
            room = self._rooms.get(room_id)
            if conn:
                conn.rooms.discard(room_id)
            if room:
                room.members.discard(conn_id)
                if not room.members:
                    self._rooms.pop(room_id, None)

    async def broadcast_room(
        self,
        room_id: str,
        msg_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """房间广播。"""
        room = self._rooms.get(room_id)
        if room is None:
            return
        for member_id in list(room.members):
            await self.send(member_id, msg_type, payload)

    async def broadcast_world(self, msg_type: str, payload: dict[str, Any] | None = None) -> None:
        """向所有已鉴权连接广播（环境等）。"""
        for conn_id, conn in list(self._connections.items()):
            if conn.authenticated:
                await self.send(conn_id, msg_type, payload)

    def ensure_room(self, room_id: str, *, kind: str = "generic") -> WsRoom:
        """
        确保房间存在（可无成员；供世界事件等 HTTP 先开房）。

        Args:
            room_id: 房间 id。
            kind: 房间类型标签。

        Returns:
            已有或新建的 ``WsRoom``。
        """
        room = self._rooms.get(room_id)
        if room is None:
            room = WsRoom(room_id=room_id, kind=kind)
            self._rooms[room_id] = room
        return room

    def room_member_count(self, room_id: str) -> int:
        """
        房间当前成员数（WS 在场）。

        Args:
            room_id: 房间 id。

        Returns:
            成员数；房间不存在则为 0。
        """
        room = self._rooms.get(room_id)
        return len(room.members) if room else 0

    def is_character_online(self, character_id: int) -> bool:
        """
        角色是否有至少一条已鉴权 WS 连接（心跳未踢）。

        Args:
            character_id: 角色主键。

        Returns:
            True 表示在线。
        """
        for conn in self._connections.values():
            if conn.authenticated and conn.character_id == character_id:
                return True
        return False

    async def sweep_idle(self) -> None:
        """踢掉心跳超时连接。"""
        timeout = get_settings().ws_idle_timeout_seconds
        now = datetime.now(timezone.utc)
        stale = []
        for conn_id, conn in list(self._connections.items()):
            age = (now - conn.last_ping_at).total_seconds()
            if age > timeout:
                stale.append(conn_id)
        for conn_id in stale:
            conn = self._connections.get(conn_id)
            if conn:
                try:
                    await conn.websocket.close(code=4000, reason="heartbeat timeout")
                except Exception:  # noqa: BLE001
                    pass
            await self.unregister(conn_id)
            logger.warning("ws idle kick conn_id=%s", conn_id)


# 进程级单例
_hub: WsHubService | None = None


def get_ws_hub() -> WsHubService:
    """获取全局 Hub。"""
    global _hub
    if _hub is None:
        _hub = WsHubService()
    return _hub
