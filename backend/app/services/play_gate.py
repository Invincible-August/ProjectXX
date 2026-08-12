"""
跨玩法前置门禁：加载角色、自动领取离线 pending、活动互斥状态机。

突破 / 战斗 / 分配 / 体质 / 工坊 / GM 等用例统一经此入口，避免路由与各 service 重复编排。
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.db.models.craft_job import CraftJob
from app.db.models.user import User
from app.domain.activity_mutex import Activity, assert_can_perform, build_activity_snapshot
from app.domain.m4_constants import CraftJobStatus
from app.schemas.common import AppError
from app.services.character_service import CharacterService
from app.services.idle_service import IdleService

logger = logging.getLogger(__name__)


class PlayGate:
    """
    跨玩法前置：有角色、清 pending、活动互斥。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._characters = CharacterService(session)
        self._idle = IdleService(session)

    async def require_character(self, user: User) -> Character:
        """
        加载当前用户角色；无角色 → ``40005``。

        参数:
            user: 当前用户。

        返回:
            角色 ORM 实体。

        异常:
            AppError: ``40005``。
        """
        character = await self._characters.get_by_user_id(user.id)
        if character is None:
            raise AppError(code=40005, message="尚未创建角色", http_status=404)
        return character

    async def resolve_pending_before_play(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> dict | None:
        """
        突破/战斗/分配前自动 claim pending。

        参数:
            character: 角色。
            now: 当前 UTC。

        返回:
            若自动 claim 则返回 applied 明细，否则 None。
        """
        # M5-D05：玩法入口先懒结算到期的闭关突破，避免带着 breaking_through 开战
        from app.services.breakthrough_service import lazy_resolve_breakthrough_channel

        await lazy_resolve_breakthrough_channel(
            self._session,
            character,
            now=now,
        )
        return await self._idle.resolve_pending_before_play(character, now=now)

    async def count_craft_running(self, character_id: int) -> int:
        """
        统计工坊 RUNNING 任务数（用于进入修炼互斥）。

        参数:
            character_id: 角色 id。

        返回:
            running 数量。
        """
        result = await self._session.execute(
            select(CraftJob).where(
                CraftJob.character_id == character_id,
                CraftJob.status == CraftJobStatus.RUNNING,
            ),
        )
        return len(list(result.scalars().all()))

    async def assert_activity(
        self,
        character: Character,
        activity: Activity,
        *,
        craft_running: int | None = None,
        in_secret_realm: bool = False,
    ) -> None:
        """
        校验活动互斥；失败抛 AppError。

        参数:
            character: 角色。
            activity: 目标活动。
            craft_running: 若已知可传入，否则现场统计。
            in_secret_realm: 秘境占位（未落地恒 False）。
        """
        running = (
            craft_running
            if craft_running is not None
            else await self.count_craft_running(character.id)
        )
        assert_can_perform(
            status=str(character.status or "normal"),
            idle_direction=str(character.idle_direction or "none"),
            activity=activity,
            craft_running=running,
            in_secret_realm=in_secret_realm,
        )

    async def activity_snapshot(self, character: Character) -> dict:
        """
        玩家可见活动态摘要。

        参数:
            character: 角色。

        返回:
            build_activity_snapshot 结果。
        """
        running = await self.count_craft_running(character.id)
        return build_activity_snapshot(
            status=str(character.status or "normal"),
            idle_direction=str(character.idle_direction or "none"),
            craft_running=running,
            in_secret_realm=False,
        )

    async def prepare_for_play(
        self,
        user: User,
        now: datetime | None = None,
        *,
        settle: bool = True,
        require: Activity | None = None,
    ) -> tuple[Character, dict | None]:
        """
        一站式：取角色 → 清 pending → 可选双线程 settle → 可选活动互斥。

        参数:
            user: 当前用户。
            now: 可选冻结时间。
            settle: 是否在清 pending 后执行权威 settle_dual。
            require: 若给定则在 settle 后校验活动互斥。

        返回:
            (character, 自动领取的离线明细或 None)。
        """
        character = await self.require_character(user)
        auto_claimed = await self.resolve_pending_before_play(character, now=now)
        # M5：惰性检测待引渡超时 → 强制轮回
        from app.services.ferry_service import FerryService

        await FerryService(self._session).check_timeout_and_force(character, now=now)
        if settle:
            await self._idle.settle_dual_async(character, now=now)
        if require is not None:
            # 开工前先推进到期任务，避免假 running 挡互斥判断
            if require in (Activity.START_CRAFT, Activity.ENTER_IDLE):
                from app.services.craft_service import CraftService

                await CraftService(self._session).settle_jobs_async(character, now=now)
            await self.assert_activity(character, require)
        return character, auto_claimed


# ---------------------------------------------------------------------------
# 兼容包装：供尚未切到 PlayGate 依赖的旧调用方使用
# ---------------------------------------------------------------------------


async def require_character_for_user(session: AsyncSession, user: User) -> Character:
    """兼容包装：委托 ``PlayGate.require_character``。"""
    return await PlayGate(session).require_character(user)


async def resolve_pending_before_play(
    session: AsyncSession,
    character: Character,
    now: datetime | None = None,
) -> dict | None:
    """兼容包装：委托 ``PlayGate.resolve_pending_before_play``。"""
    return await PlayGate(session).resolve_pending_before_play(character, now=now)
