"""
WebSocket 信封协议：type 常量与校验。

命名空间：sys.* / world.* / dao_lord.* / event.*
（chat.* 已于 M7 L4 落地；heritage.* 于 M7 L5 落地）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# —— 系统 ——
TYPE_SYS_HELLO = "sys.hello"
TYPE_SYS_ERROR = "sys.error"
TYPE_PING = "ping"
TYPE_PONG = "pong"
TYPE_AUTH = "auth"

# —— 房间 ——
TYPE_ROOM_JOIN = "room.join"
TYPE_ROOM_LEAVE = "room.leave"
TYPE_ROOM_STATE = "room.state"

# —— 世界 ——
TYPE_WORLD_ENV = "world.env"

# —— 道主 ——
TYPE_DAO_LORD_BATTLE_EVENT = "dao_lord.battle.event"
TYPE_DAO_LORD_ROOM_STATE = "dao_lord.room.state"
TYPE_DAO_LORD_FINISHED = "dao_lord.finished"
TYPE_DAO_LORD_CONTEST_STATE = "dao_lord.contest.state"
TYPE_DAO_LORD_LIVE_TICK = "dao_lord.live.tick"
TYPE_DAO_LORD_LIVE_ENDED = "dao_lord.live.ended"
TYPE_DAO_LORD_MATCH_FINISHED = "dao_lord.match.finished"

# —— 世界事件骨架 ——
TYPE_EVENT_STATE = "event.state"

# —— 聊天（M7 L4）——
TYPE_CHAT_MESSAGE = "chat.message"
TYPE_CHAT_UNREAD = "chat.unread"
TYPE_CHAT_RECALL = "chat.recall"
TYPE_CHAT_DM_CLEARED = "chat.dm.cleared"

# —— 队伍邀请 / 状态（party invite flow）——
TYPE_PARTY_INVITE = "party.invite"
TYPE_PARTY_UPDATE = "party.update"

# —— 传承（M7 L5）——
TYPE_HERITAGE_CREATED = "heritage.created"
TYPE_HERITAGE_CLAIMED = "heritage.claimed"
TYPE_HERITAGE_EXPIRED = "heritage.expired"

# —— 道友化身助战 ——
TYPE_AVATAR_ASSIST_INVITE = "avatar.assist.invite"

# —— 角色在线状态 ——
TYPE_PRESENCE_CHANGED = "presence.changed"


def utc_now_iso() -> str:
    """UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_envelope(
    msg_type: str,
    payload: dict[str, Any] | None,
    *,
    seq: int,
    ts: str | None = None,
) -> dict[str, Any]:
    """
    构造标准信封。

    Args:
        msg_type: 点分 type。
        payload: 对象载荷；None 转 {}。
        seq: 连接级序号。
        ts: 可选时间戳。

    Returns:
        信封 dict。
    """
    body = payload if isinstance(payload, dict) else {}
    return {
        "type": str(msg_type),
        "seq": int(seq),
        "ts": ts or utc_now_iso(),
        "payload": body,
    }


def parse_envelope(raw: Any) -> dict[str, Any] | None:
    """
    校验客户端入站 JSON 是否为合法信封。

    Returns:
        规范化信封或 None。
    """
    if not isinstance(raw, dict):
        return None
    msg_type = raw.get("type")
    if not isinstance(msg_type, str) or not msg_type.strip():
        return None
    payload = raw.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return None
    seq_raw = raw.get("seq", 0)
    try:
        seq = int(seq_raw)
    except (TypeError, ValueError):
        seq = 0
    return {
        "type": msg_type.strip(),
        "seq": seq,
        "ts": str(raw.get("ts") or utc_now_iso()),
        "payload": payload,
        "client_action_id": raw.get("client_action_id"),
    }
