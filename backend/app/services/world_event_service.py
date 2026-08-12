"""
世界事件骨架：开窗查询、报名占位、Hub 房间与在场人数。

成型波次/掉落 → M6-D05 / M11；本阶段仅 D15 下限。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.domain.dao_lord_rules import DaoLordWindowDef, is_window_open
from app.schemas.common import AppError
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)

# 进程内报名名单：event_id → set(character_id)
_REGISTRATIONS: dict[str, set[int]] = {}


class WorldEventService:
    """Boss/秘境房间骨架。"""

    ROOM_KIND: ClassVar[str] = "world_event"

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话（角色闸用）。
        """
        self._session = session
        self._gate = PlayGate(session)

    def _enabled(self) -> bool:
        """总闸：环境变量或 YAML enabled。"""
        settings = get_settings()
        cfg = get_game_config().world_events
        return bool(settings.world_events_enabled or cfg.enabled)

    @staticmethod
    def room_id_for(event_id: str) -> str:
        """
        稳定房间 id（WS ``room.join`` 用）。

        Args:
            event_id: 配置事件键。

        Returns:
            ``world_event:{event_id}``。
        """
        return f"world_event:{event_id}"

    def _windows_for(self, event_id: str, body: dict[str, Any]) -> list[DaoLordWindowDef]:
        """解析事件开窗定义。"""
        windows: list[DaoLordWindowDef] = []
        for w in list(body.get("windows") or []):
            if not isinstance(w, dict):
                continue
            windows.append(
                DaoLordWindowDef(
                    start_hour=int(w.get("start_hour") or 0),
                    end_hour=int(w.get("end_hour") or 24),
                    tz=str(w.get("tz") or "UTC"),
                    label_zh=str(body.get("label_zh") or event_id),
                    weekday=w.get("weekday"),
                ),
            )
        return windows

    def _ensure_hub_room(self, room_id: str) -> None:
        """确保 Hub 中存在空房间（无成员亦可 join）。"""
        get_ws_hub().ensure_room(room_id, kind=self.ROOM_KIND)

    def _presence_count(self, room_id: str | None) -> int:
        """WS 在场人数（须 join 才计入）。"""
        if not room_id:
            return 0
        return get_ws_hub().room_member_count(room_id)

    def _event_public(
        self,
        *,
        event_id: str,
        body: dict[str, Any],
        character_id: int,
        now: datetime,
    ) -> dict[str, Any]:
        """单条事件公开摘要。"""
        windows = self._windows_for(event_id, body)
        open_now, _ = is_window_open(windows, now=now) if windows else (True, "")
        # 骨架：无窗配置则视为常开，便于联调
        room_id = self.room_id_for(event_id) if open_now else None
        if room_id:
            self._ensure_hub_room(room_id)
        regs = _REGISTRATIONS.get(event_id, set())
        summary = str(body.get("summary") or "骨架占位")
        return {
            "id": event_id,
            "kind": body.get("kind"),
            "label": body.get("label_zh") or event_id,
            "summary": summary,
            "description": summary,
            "open": open_now,
            "room_id": room_id,
            "presence_count": self._presence_count(room_id),
            "registered_count": len(regs),
            "registered": character_id in regs,
            "placeholder": True,
            "skeleton": True,
        }

    async def list_current(self, user: User) -> dict[str, Any]:
        """
        当前事件摘要。

        Args:
            user: 当前用户。

        Returns:
            enabled / events / hint（及 note 别名）。
        """
        character = await self._gate.require_character(user)
        if not self._enabled():
            return {
                "enabled": False,
                "events": [],
                "hint": "世界事件骨架未开启；不参加不挡主线",
                "note": "世界事件骨架未开启；不参加不挡主线",
            }
        now = datetime.now(timezone.utc)
        events_out = [
            self._event_public(
                event_id=event_id,
                body=body,
                character_id=character.id,
                now=now,
            )
            for event_id, body in get_game_config().world_events.events.items()
        ]
        hint = "定时秘境/世界 Boss（骨架）：进房须 WS join；成型玩法见后续版本"
        return {
            "enabled": True,
            "events": events_out,
            "hint": hint,
            "note": hint,
        }

    async def register(self, user: User, event_id: str) -> dict[str, Any]:
        """
        报名占位，并确保房间已创建。

        Args:
            user: 当前用户。
            event_id: 事件配置键。

        Returns:
            报名结果（含 room_id / event 摘要）。

        Raises:
            AppError: 未开启 / 状态不可 / 未知事件 / 非开放窗。
        """
        if not self._enabled():
            raise AppError(code=40094, message="世界事件未开启", http_status=403)
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        if character.status != "normal":
            raise AppError(code=40060, message="当前状态不可报名世界事件", http_status=409)
        cfg = get_game_config().world_events.events.get(event_id)
        if cfg is None:
            raise AppError(code=40000, message="未知世界事件", http_status=404)
        now = datetime.now(timezone.utc)
        public = self._event_public(
            event_id=event_id,
            body=cfg,
            character_id=character.id,
            now=now,
        )
        if not public["open"]:
            raise AppError(code=40086, message="事件未开放", http_status=400)
        room_id = str(public["room_id"])
        self._ensure_hub_room(room_id)
        regs = _REGISTRATIONS.setdefault(event_id, set())
        regs.add(character.id)
        public["registered"] = True
        public["registered_count"] = len(regs)
        public["presence_count"] = self._presence_count(room_id)
        logger.info(
            "world event register event=%s character_id=%s room=%s",
            event_id,
            character.id,
            room_id,
        )
        return {
            "event_id": event_id,
            "registered": True,
            "room_id": room_id,
            "presence_count": public["presence_count"],
            "registered_count": len(regs),
            "event": public,
            "message": "已报名（骨架）；请 WS 进入房间计入在场",
        }
