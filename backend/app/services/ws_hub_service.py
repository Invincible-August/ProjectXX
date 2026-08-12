"""
进程内 WebSocket Hub：连接、心跳、房间广播、角色在线索引。

多 worker 时可通过 WS_REDIS_URL 扩展（本阶段单进程默认；见 PRESENCE-R01）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

PresenceListener = Callable[[int, bool], Awaitable[None]]


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
        # 角色 → 已鉴权连接 id 集合（O(1) 在线判定）
        self._char_conns: dict[int, set[str]] = {}
        # 最后连接断开后的宽限截止时间
        self._grace_until: dict[int, datetime] = {}
        self._grace_tasks: dict[int, asyncio.Task[None]] = {}
        self._presence_listener: PresenceListener | None = None

    def enabled(self) -> bool:
        return bool(get_settings().ws_enabled)

    def set_presence_listener(self, listener: PresenceListener | None) -> None:
        """
        Register async callback for presence transitions (character_id, online).

        Args:
            listener: Awaitable callback or None to clear.
        """
        self._presence_listener = listener

    def _grace_sec(self) -> int:
        """Read grace_sec from presence config; default 30 on load failure."""
        try:
            from app.services.realm_config import get_game_config

            return max(0, int(get_game_config().presence.grace_sec))
        except Exception:  # noqa: BLE001
            return 30

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _compute_online(self, character_id: int) -> bool:
        """Live connection or unexpired grace."""
        cid = int(character_id)
        if self._char_conns.get(cid):
            return True
        until = self._grace_until.get(cid)
        if until is not None and until > self._now():
            return True
        return False

    def has_live_connection(self, character_id: int) -> bool:
        """
        True if character has at least one authenticated WS (no grace).

        Args:
            character_id: Character primary key.

        Returns:
            Whether a live connection exists.
        """
        return bool(self._char_conns.get(int(character_id)))

    async def _emit_presence(self, character_id: int, online: bool) -> None:
        """Fire presence listener if registered."""
        listener = self._presence_listener
        if listener is None:
            return
        try:
            await listener(int(character_id), bool(online))
        except Exception:  # noqa: BLE001
            logger.exception(
                "presence listener failed character_id=%s online=%s",
                character_id,
                online,
            )

    def _cancel_grace_task(self, character_id: int) -> None:
        task = self._grace_tasks.pop(int(character_id), None)
        if task is not None and not task.done():
            task.cancel()

    def _schedule_grace_expiry(self, character_id: int, grace_sec: int) -> None:
        """After grace, if still no live conn, clear grace and emit offline."""
        cid = int(character_id)
        self._cancel_grace_task(cid)

        async def _expire() -> None:
            try:
                await asyncio.sleep(grace_sec)
            except asyncio.CancelledError:
                return
            was = self._compute_online(cid)
            self._grace_until.pop(cid, None)
            self._grace_tasks.pop(cid, None)
            now = self._compute_online(cid)
            if was and not now:
                await self._emit_presence(cid, False)

        self._grace_tasks[cid] = asyncio.create_task(_expire())

    async def register(self, conn_id: str, websocket: WebSocket) -> WsConnection:
        """登记新连接。"""
        conn = WsConnection(conn_id=conn_id, websocket=websocket)
        async with self._lock:
            self._connections[conn_id] = conn
        logger.info("ws register conn_id=%s", conn_id)
        return conn

    async def unregister(self, conn_id: str) -> None:
        """断开并离开所有房间；维护角色在线索引与宽限。"""
        transition: tuple[int, bool] | None = None
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
            cid = conn.character_id if conn.authenticated else None
            if cid is not None:
                cid_i = int(cid)
                was = self._compute_online(cid_i)
                bucket = self._char_conns.get(cid_i)
                if bucket is not None:
                    bucket.discard(conn_id)
                    if not bucket:
                        self._char_conns.pop(cid_i, None)
                        grace = self._grace_sec()
                        if grace > 0:
                            self._grace_until[cid_i] = self._now() + timedelta(seconds=grace)
                            self._schedule_grace_expiry(cid_i, grace)
                        else:
                            self._grace_until.pop(cid_i, None)
                            self._cancel_grace_task(cid_i)
                now = self._compute_online(cid_i)
                if was != now:
                    transition = (cid_i, now)
        logger.info("ws unregister conn_id=%s", conn_id)
        if transition is not None:
            await self._emit_presence(transition[0], transition[1])

    async def authenticate(
        self,
        conn_id: str,
        *,
        user_id: int,
        character_id: int | None,
    ) -> None:
        """标记已鉴权并更新角色连接索引。"""
        transitions: list[tuple[int, bool]] = []
        async with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                return
            prev_cid = conn.character_id if conn.authenticated else None
            # 换绑角色时先从旧索引移除
            if prev_cid is not None and (
                character_id is None or int(prev_cid) != int(character_id)
            ):
                old = int(prev_cid)
                was_old = self._compute_online(old)
                bucket = self._char_conns.get(old)
                if bucket is not None:
                    bucket.discard(conn_id)
                    if not bucket:
                        self._char_conns.pop(old, None)
                now_old = self._compute_online(old)
                if was_old != now_old:
                    transitions.append((old, now_old))

            conn.user_id = user_id
            conn.character_id = character_id
            conn.authenticated = True

            if character_id is not None:
                cid = int(character_id)
                was = self._compute_online(cid)
                self._char_conns.setdefault(cid, set()).add(conn_id)
                self._grace_until.pop(cid, None)
                self._cancel_grace_task(cid)
                now = self._compute_online(cid)
                if was != now:
                    transitions.append((cid, now))

        for cid_t, online_t in transitions:
            await self._emit_presence(cid_t, online_t)

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

    async def send_to_character(
        self,
        character_id: int,
        msg_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """
        Send to all authenticated connections of a character.

        Args:
            character_id: Target character id.
            msg_type: Envelope type.
            payload: Optional payload.
        """
        cid = int(character_id)
        for conn_id in list(self._char_conns.get(cid, ())):
            await self.send(conn_id, msg_type, payload)

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
        角色是否在线（含断线宽限；不含 DEV 假定）。

        Args:
            character_id: 角色主键。

        Returns:
            True 表示在线。
        """
        return self._compute_online(int(character_id))

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


def reset_ws_hub_for_tests() -> None:
    """Test helper: drop process Hub singleton."""
    global _hub
    _hub = None
