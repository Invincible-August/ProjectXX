"""运行时 Bundle 重载闸门（发布/回滚后统一入口）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.realm_config import clear_game_config_cache, get_game_config

if TYPE_CHECKING:
    from app.services.realm_config import GameConfigBundle

logger = logging.getLogger(__name__)


class RuntimeConfigReloader:
    """
    封装「清 lru_cache → 重新 load_game_config」。

    发布路径只应调用本类，避免各处散落双行调用、漏掉重载。
    """

    @staticmethod
    def reload(*, reason: str = "") -> GameConfigBundle:
        """
        使玩家服配置热更生效。

        Args:
            reason: 日志原因（publish / rollback / boot）。

        Returns:
            GameConfigBundle: 新快照。
        """
        clear_game_config_cache()
        bundle = get_game_config()
        if reason:
            logger.info("game config reloaded reason=%s", reason)
        return bundle
