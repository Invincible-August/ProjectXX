"""角色待领取事件日志（离线缓冲 / 在线 WS 推送）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models import Character

logger = logging.getLogger(__name__)

# 环形缓冲上限，防止离线堆积撑爆 JSON
_MAX_PENDING_EVENT_LOGS = 50


def parse_pending_event_logs(character: Character) -> list[dict[str, Any]]:
    """
    解析 ``pending_event_logs_json``。

    Args:
        character: 角色。

    Returns:
        list: 日志条目列表。
    """
    raw = getattr(character, "pending_event_logs_json", None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and item.get("message"):
            out.append(item)
    return out


def append_pending_event_log(
    character: Character,
    *,
    message: str,
    level: str = "info",
    source: str = "mentor",
) -> None:
    """
    追加一条待领取事件日志。

    Args:
        character: 角色。
        message: 正文。
        level: info|success|warning|system。
        source: 来源键。
    """
    text = str(message or "").strip()
    if not text:
        return
    logs = parse_pending_event_logs(character)
    logs.append(
        {
            "message": text,
            "level": str(level or "info"),
            "source": str(source or "system"),
            "at": to_utc_iso(now_utc()),
        },
    )
    if len(logs) > _MAX_PENDING_EVENT_LOGS:
        logs = logs[-_MAX_PENDING_EVENT_LOGS:]
    character.pending_event_logs_json = json.dumps(logs, ensure_ascii=False)


def take_pending_event_logs(character: Character) -> list[dict[str, Any]]:
    """
    取出并清空待领取事件日志。

    Args:
        character: 角色。

    Returns:
        list: 原有日志条目。
    """
    logs = parse_pending_event_logs(character)
    character.pending_event_logs_json = None
    return logs
