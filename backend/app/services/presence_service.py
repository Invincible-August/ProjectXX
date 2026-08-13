"""
角色在线状态（Presence）门面：统一组队 / 道友 / 面交 / 助战 / 赛会判定与推送。

权威：WsHub 鉴权连接 + grace；DEV 假定仅 development 且按用途读取。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.db.models import Friendship, PartyMember, PartySession
from app.db.session import AsyncSessionLocal
from app.domain.ws_protocol import TYPE_PRESENCE_CHANGED, utc_now_iso
from app.services.realm_config import get_game_config
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)


class PresencePurpose(str, Enum):
    """门闸用途：决定 DEV 假定回落哪条遗留配置。"""

    FRIENDS = "friends"
    PARTY = "party"
    FACE = "face"
    ASSIST = "assist"
    CONTEST = "contest"


class PresenceService:
    """
    Presence facade.

    ``is_online`` includes Hub grace but never DEV assume.
    ``is_online_for`` may force True in development per purpose.
    """

    def is_online(self, character_id: int) -> bool:
        """
        Whether the character is online (live WS or grace).

        Args:
            character_id: Character primary key.

        Returns:
            True if online.
        """
        try:
            return get_ws_hub().is_character_online(int(character_id))
        except Exception:  # noqa: BLE001
            return False

    def is_online_for(self, purpose: PresencePurpose | str, character_id: int) -> bool:
        """
        Online gate for a feature purpose (may apply DEV assume).

        Args:
            purpose: friends | party | face | assist | contest.
            character_id: Character primary key.

        Returns:
            True if considered online for that purpose.
        """
        key = purpose.value if isinstance(purpose, PresencePurpose) else str(purpose)
        if self._dev_assume(key):
            return True
        return self.is_online(int(character_id))

    def _dev_assume(self, purpose: str) -> bool:
        """DEV-only assume online; production always False."""
        settings = get_settings()
        if str(getattr(settings, "app_env", "") or "") != "development":
            return False
        try:
            cfg = get_game_config()
            pcfg = cfg.presence
        except Exception:  # noqa: BLE001
            return False
        if bool(pcfg.dev_assume_online):
            return True
        overrides = pcfg.dev_assume_by_purpose or {}
        if purpose in overrides:
            return bool(overrides[purpose])
        # 遗留业务 YAML 回落
        if purpose == PresencePurpose.PARTY.value:
            return bool(cfg.chat.party_dev_assume_online)
        if purpose == PresencePurpose.FACE.value:
            return bool(cfg.trade.face_dev_assume_online)
        if purpose == PresencePurpose.FRIENDS.value:
            return bool(cfg.friends.dev_assume_online)
        if purpose == PresencePurpose.ASSIST.value:
            override = cfg.friends.assist_dev_assume_online
            if override is not None:
                return bool(override)
            return bool(cfg.avatar.friend_assist.assist_dev_assume_online)
        if purpose == PresencePurpose.CONTEST.value:
            return bool(cfg.dao_lord.contest.dev_assume_online)
        return False

    async def on_presence_transition(self, character_id: int, online: bool) -> None:
        """
        Hub hook: push ``presence.changed`` to friends and party mates.

        Args:
            character_id: Character whose presence changed.
            online: New online flag.
        """
        cid = int(character_id)
        payload: dict[str, Any] = {
            "character_id": cid,
            "online": bool(online),
            "at": utc_now_iso(),
        }
        try:
            watchers = await self._watcher_character_ids(cid)
        except Exception:  # noqa: BLE001
            logger.exception("presence watchers failed character_id=%s", cid)
            return
        # 下线时刷新道友资料快照，供离线查阅
        if not online:
            try:
                await self._persist_friend_profile_snapshot(cid)
            except Exception:  # noqa: BLE001
                logger.exception("friend profile snapshot failed character_id=%s", cid)
        hub = get_ws_hub()
        for wid in watchers:
            if int(wid) == cid:
                continue
            await hub.send_to_character(int(wid), TYPE_PRESENCE_CHANGED, payload)
        logger.info(
            "presence.changed character_id=%s online=%s watchers=%s",
            cid,
            online,
            len(watchers),
        )

    async def _persist_friend_profile_snapshot(self, character_id: int) -> None:
        """Persist friend-visible profile snapshot when going offline."""
        from app.db.models import Character
        from app.services.friend_service import FriendService

        async with AsyncSessionLocal() as session:
            ch = await session.get(Character, int(character_id))
            if ch is None:
                return
            await FriendService(session).refresh_profile_snapshot(ch)
            await session.commit()

    async def _watcher_character_ids(self, character_id: int) -> set[int]:
        """Friends (active) + open party mates."""
        cid = int(character_id)
        out: set[int] = set()
        async with AsyncSessionLocal() as session:
            friend_rows = (
                await session.execute(
                    select(Friendship).where(
                        Friendship.status == "active",
                        or_(
                            Friendship.character_low_id == cid,
                            Friendship.character_high_id == cid,
                        ),
                    ),
                )
            ).scalars().all()
            for row in friend_rows:
                other = (
                    row.character_high_id
                    if int(row.character_low_id) == cid
                    else row.character_low_id
                )
                out.add(int(other))

            member = (
                await session.execute(
                    select(PartyMember).where(PartyMember.character_id == cid).limit(1),
                )
            ).scalar_one_or_none()
            if member is not None:
                party = await session.get(PartySession, member.party_id)
                if party is not None and str(party.status) == "open":
                    mates = (
                        await session.execute(
                            select(PartyMember.character_id).where(
                                PartyMember.party_id == party.id,
                            ),
                        )
                    ).scalars().all()
                    for mid in mates:
                        out.add(int(mid))
        return out


_presence: PresenceService | None = None
_hub_hooked = False


def get_presence() -> PresenceService:
    """
    Process singleton PresenceService; wire Hub listener once.

    Returns:
        Shared PresenceService instance.
    """
    global _presence, _hub_hooked
    if _presence is None:
        _presence = PresenceService()
    if not _hub_hooked:
        get_ws_hub().set_presence_listener(_presence.on_presence_transition)
        _hub_hooked = True
    return _presence


def ensure_presence_hub_hook() -> None:
    """Idempotent: ensure Hub → Presence listener is registered (app startup)."""
    get_presence()


def reset_presence_for_tests() -> None:
    """Test helper: clear Presence singleton and Hub listener flag."""
    global _presence, _hub_hooked
    from app.services.ws_hub_service import get_ws_hub

    try:
        get_ws_hub().set_presence_listener(None)
    except Exception:  # noqa: BLE001
        pass
    _presence = None
    _hub_hooked = False
