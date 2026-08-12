"""
体力应用服务（M3战斗成型设计.md §12.9 · D10）。

体力是战斗（后续含制作）的权威限流器：
    - 读数：任何读取路径先惰性结算（同挂机 lazy 模式，无定时器）；
    - 扣减：开战 P0 在单角色事务内结算后扣 ``battle_cost``；
      不足 → ``40049``，引擎不被调用；
    - ``STAMINA_ENABLED=false`` 时门禁放行（联调用），读数仍可用。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models.character import Character
from app.domain.stamina import StaminaReading, settle_stamina
from app.schemas.common import AppError
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class StaminaService:
    """
    体力用例：惰性恢复读数 + 行为扣减。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    @staticmethod
    def _settle(character: Character, now: datetime) -> StaminaReading:
        """对角色执行一次惰性体力结算（不落库，仅计算）。"""
        cfg = get_game_config().stamina
        # 旧号（M3 前创建）无结算锚点：视为「此刻起算、当前值即存量」
        stored_at = character.stamina_updated_at or now
        # SQLite 可能回读 naive datetime → 统一按 UTC 处理
        if stored_at.tzinfo is None:
            stored_at = stored_at.replace(tzinfo=timezone.utc)
        return settle_stamina(
            int(character.stamina),
            stored_at,
            now,
            cap=cfg.cap,
            regen_per_minute=cfg.regen_per_minute,
        )

    def read(self, character: Character, now: datetime | None = None) -> dict:
        """
        读取当前体力（惰性恢复后），并把结算值回写到实体（懒回写）。

        返回:
            dict: ``{left, cap, next_point_in_seconds, regen_per_minute}``。
        """
        current_time = now_utc(now)
        reading = self._settle(character, current_time)
        # 懒回写：读也推进锚点，避免下次重复结算长区间
        character.stamina = reading.stored_value
        character.stamina_updated_at = current_time
        cfg = get_game_config().stamina
        return {
            "left": reading.current,
            "cap": reading.cap,
            "next_point_in_seconds": reading.next_point_in_seconds,
            "regen_per_minute": cfg.regen_per_minute,
        }

    def spend(
        self,
        character: Character,
        kind: str,
        now: datetime | None = None,
    ) -> dict:
        """
        为一次行为扣减体力（开战 P0 调用）。

        参数:
            character: 角色实体（应处于单角色事务内）。
            kind: 消耗类型键（``battle_pve`` / ``battle_pvp`` / ``craft``）。
            now: 可选冻结时间。

        返回:
            dict: 扣减后的体力读数（结构同 ``read``）。

        异常:
            AppError: ``40049`` 体力不足（附恢复倒计时提示）。
        """
        settings = get_settings()
        current_time = now_utc(now)
        cfg = get_game_config().stamina
        cost = int(cfg.costs.get(kind, 0))

        # 门禁关闭（联调）：不扣减，直接返回读数
        if not settings.stamina_enabled:
            return self.read(character, now=current_time)

        reading = self._settle(character, current_time)
        if reading.current < cost:
            logger.info(
                "stamina insufficient character_id=%s kind=%s left=%s cost=%s",
                character.id,
                kind,
                reading.current,
                cost,
            )
            raise AppError(
                code=40049,
                message=(
                    f"体力不足（当前 {reading.current}/{reading.cap}，"
                    f"本次需 {cost}；{reading.next_point_in_seconds} 秒后恢复 1 点）"
                ),
                http_status=409,
            )

        character.stamina = reading.current - cost
        character.stamina_updated_at = current_time
        logger.info(
            "stamina spend character_id=%s kind=%s cost=%s left=%s",
            character.id,
            kind,
            cost,
            character.stamina,
        )
        return {
            "left": int(character.stamina),
            "cap": reading.cap,
            "next_point_in_seconds": reading.next_point_in_seconds,
            "regen_per_minute": cfg.regen_per_minute,
        }

    def add_stamina(self, character: Character, amount: int, now: datetime | None = None) -> dict:
        """
        道具等方式增加体力（M4 体力丹）；受 cap 限制除非 item_overflow。

        Args:
            character: 角色实体。
            amount: 增加点数。
            now: 可选冻结时间。

        Returns:
            dict: 更新后的体力读数。
        """
        current_time = now_utc(now)
        cfg = get_game_config().stamina
        reading = self._settle(character, current_time)
        new_val = reading.current + max(0, amount)
        if not cfg.item_overflow:
            new_val = min(new_val, reading.cap)
        character.stamina = new_val
        character.stamina_updated_at = current_time
        return {
            "left": int(character.stamina),
            "cap": reading.cap,
            "next_point_in_seconds": reading.next_point_in_seconds,
            "regen_per_minute": cfg.regen_per_minute,
        }

    def spend_for_monster(
        self,
        character: Character,
        monster_stamina_cost: int | None,
        now: datetime | None = None,
    ) -> dict:
        """
        按怪物配置扣体力（怪物可覆盖默认 ``battle_pve`` 消耗）。

        参数:
            monster_stamina_cost: 怪物专属消耗；None 走默认键。
        """
        if monster_stamina_cost is None:
            return self.spend(character, "battle_pve", now=now)

        settings = get_settings()
        current_time = now_utc(now)
        if not settings.stamina_enabled:
            return self.read(character, now=current_time)

        cfg = get_game_config().stamina
        reading = self._settle(character, current_time)
        cost = int(monster_stamina_cost)
        if reading.current < cost:
            raise AppError(
                code=40049,
                message=(
                    f"体力不足（当前 {reading.current}/{reading.cap}，"
                    f"本次需 {cost}；{reading.next_point_in_seconds} 秒后恢复 1 点）"
                ),
                http_status=409,
            )
        character.stamina = reading.current - cost
        character.stamina_updated_at = current_time
        return {
            "left": int(character.stamina),
            "cap": reading.cap,
            "next_point_in_seconds": reading.next_point_in_seconds,
            "regen_per_minute": cfg.regen_per_minute,
        }
