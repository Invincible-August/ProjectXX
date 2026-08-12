"""
M4 工坊应用服务：配方列表、开工、惰性 settle、领取。
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.craft_job import CraftJob
from app.db.models.user import User
from app.domain.craft_rules import (
    compute_efficiency,
    compute_finish_at,
    count_active_jobs,
    roll_fail,
)
from app.domain.m4_constants import CraftActor, CraftJobStatus
from app.schemas.common import AppError
from app.services.avatar_service import AvatarService
from app.services.inventory_service import InventoryService
from app.services.m4_features import require_craft_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.stamina_service import StaminaService

logger = logging.getLogger(__name__)


class CraftService:
    """
    制造业工坊用例。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._gate = PlayGate(session)
        self._inventory = InventoryService(session)
        self._avatar = AvatarService(session)
        self._stamina = StaminaService(session)

    def list_recipes(self, character: Character) -> list[dict[str, Any]]:
        """
        配方列表（含锁定原因占位）。

        参数:
            character: 当前角色（预留境界/熟练锁；M4 出口暂不使用）。
        """
        _ = character  # 预留：后续按境界/熟练度标记 locked
        cfg = get_game_config().craft_recipes
        out: list[dict[str, Any]] = []
        for recipe in cfg.recipes.values():
            out.append(
                {
                    "recipe_id": recipe.recipe_id,
                    "branch": recipe.branch,
                    "name": recipe.name,
                    "duration_seconds": recipe.duration_seconds,
                    "fail_chance": recipe.fail_chance,
                    "spirit_stone_cost": recipe.spirit_stone_cost,
                    "stamina_cost": recipe.stamina_cost,
                    "materials": [
                        {"item_id": m.item_id, "quantity": m.quantity}
                        for m in recipe.materials
                    ],
                    "locked": False,
                    "lock_reason": None,
                    # 供前端展示「制造业挂机效率」文案，避免写死 1.25
                    "main_crafting_bonus": cfg.main_crafting_bonus,
                },
            )
        return out

    async def list_jobs(
        self,
        character: Character,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """我的工坊队列（先惰性 settle，再返回，避免 finish_at 已到仍显示 running）。"""
        await self.settle_jobs_async(character, now=now)
        result = await self._session.execute(
            select(CraftJob)
            .where(CraftJob.character_id == character.id)
            .order_by(CraftJob.id.desc()),
        )
        return [self._job_to_dict(j) for j in result.scalars().all()]

    @staticmethod
    def _job_to_dict(job: CraftJob) -> dict[str, Any]:
        """工坊任务 ORM → 响应字典。"""
        return {
            "id": job.id,
            "actor": job.actor,
            "recipe_id": job.recipe_id,
            "status": job.status,
            "started_at": to_utc_iso(job.started_at),
            "finish_at": to_utc_iso(job.finish_at),
            "result": json.loads(job.result_json) if job.result_json else None,
        }

    async def jobs_summary(self, character_id: int) -> dict[str, int]:
        """进行中 / 可领取条数摘要。"""
        result = await self._session.execute(
            select(CraftJob).where(CraftJob.character_id == character_id),
        )
        running = ready = 0
        for job in result.scalars().all():
            if job.status == CraftJobStatus.RUNNING:
                running += 1
            elif job.status == CraftJobStatus.READY:
                ready += 1
        return {"running": running, "ready": ready}

    async def start(
        self,
        user: User,
        *,
        recipe_id: str,
        actor: str = CraftActor.MAIN,
        use_dao: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        开工：扣材料/灵石/体力，创建 running 任务。

        异常:
            AppError: 40053 队列满；40055 材料不足；40049 体力不足；40084 道值不足。
        """
        require_craft_enabled()
        # 一站式：角色 + 清 pending + 双线程 settle + 须先停止修炼
        from app.domain.activity_mutex import Activity

        character, _ = await self._gate.prepare_for_play(
            user,
            now=now,
            require=Activity.START_CRAFT,
        )

        cfg = get_game_config().craft_recipes
        recipe = cfg.recipes.get(recipe_id)
        if recipe is None:
            raise AppError(code=40000, message=f"未知配方：{recipe_id}", http_status=404)

        if actor not in (CraftActor.MAIN, CraftActor.AVATAR):
            raise AppError(code=40000, message="actor 须为 main 或 avatar", http_status=400)

        avatar_row = await self._avatar.get_avatar_row(character.id)
        if actor == CraftActor.AVATAR and avatar_row is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        # AVATAR-D01：化身工坊须元婴起 workshop_actor
        if actor == CraftActor.AVATAR:
            from app.domain.m4_constants import AvatarFeature

            cap_idx = get_game_config().avatar.capability
            if cap_idx is None:
                from app.domain.avatar_capability import AvatarCapabilityIndex

                cap_idx = AvatarCapabilityIndex.from_config(
                    get_game_config().avatar,
                    get_game_config().realms,
                )
            ok, code, msg = cap_idx.check_feature(
                character.major_realm,
                AvatarFeature.WORKSHOP_ACTOR,
            )
            if not ok:
                raise AppError(code=code or 40090, message=msg, http_status=400)

        result = await self._session.execute(
            select(CraftJob).where(
                CraftJob.character_id == character.id,
                CraftJob.status.in_(
                    (CraftJobStatus.RUNNING, CraftJobStatus.READY),
                ),
            ),
        )
        active_jobs = list(result.scalars().all())
        if count_active_jobs(active_jobs, actor, cfg.max_jobs_per_actor):
            raise AppError(code=40053, message="工坊队列已满", http_status=400)

        mats = [{"item_id": m.item_id, "quantity": m.quantity} for m in recipe.materials]
        # remove_materials 内会再次校验并扣减，避免双次手写校验
        if int(character.spirit_stones) < recipe.spirit_stone_cost:
            raise AppError(code=40000, message="灵石不足以开工", http_status=400)

        # M6：开工前扣道值（成功运用占位；失败率/词条在 claim 加深）
        dao_usage_info: dict[str, Any] | None = None
        if use_dao:
            from app.services.dao_service import DaoService

            dao_usage_info = await DaoService(self._session).consume_usage(
                character,
                kind="craft",
                success=True,
            )

        self._stamina.spend(character, "craft", now=now)
        await self._inventory.remove_materials(character.id, mats)
        character.spirit_stones = int(character.spirit_stones) - recipe.spirit_stone_cost

        eff = compute_efficiency(
            actor=actor,
            character_idle_direction=character.idle_direction,
            avatar_idle_direction=avatar_row.idle_direction if avatar_row else None,
            main_crafting_bonus=cfg.main_crafting_bonus,
        )
        # M5：开工锁定世界环境，并乘天气分支效率
        from app.domain.env_modifiers import resolve_craft_branch_mult
        from app.domain.weather_rules import build_env_lock
        from app.services.calendar_service import CalendarService
        from app.services.weather_service import WeatherService

        started = now_utc(now)
        cal = CalendarService().get_snapshot(now=started)
        weather_id = WeatherService().get_underlying_weather_id(now=started)
        env_lock = build_env_lock(str(cal["shichen_id"]), weather_id)
        weather_cfg = get_game_config().weather
        branch = str(recipe.branch or "alchemy")
        craft_tables = weather_cfg.modifiers.get("craft") or {}
        if isinstance(craft_tables, dict):
            weather_eff = resolve_craft_branch_mult(
                weather_id=weather_id,
                branch=branch,
                craft_tables=craft_tables,
                clamp_min=weather_cfg.clamp_min,
                clamp_max=weather_cfg.clamp_max,
            )
            eff = float(eff) * float(weather_eff)

        finish = compute_finish_at(started, recipe.duration_seconds, eff)

        job = CraftJob(
            character_id=character.id,
            actor=actor,
            recipe_id=recipe_id,
            started_at=started,
            finish_at=finish,
            status=CraftJobStatus.RUNNING,
            env_lock_json=json.dumps(env_lock.to_dict(), ensure_ascii=False),
        )
        self._session.add(job)
        await self._session.flush()
        await self._session.refresh(job)
        logger.info(
            "craft started character_id=%s job_id=%s recipe=%s actor=%s eff=%s use_dao=%s",
            character.id,
            job.id,
            recipe_id,
            actor,
            eff,
            use_dao,
        )
        payload = self._job_to_dict(job)
        if dao_usage_info is not None:
            payload["dao_usage"] = dao_usage_info
            # 显性：失败率占位说明
            delta = float(dao_usage_info.get("fail_rate_delta") or 0)
            payload["dao_usage_hint"] = (
                f"已运用{dao_usage_info.get('fate_dao_label')}："
                f"耗道值 {dao_usage_info.get('qi_cost')}，失败率修正 {delta:+.0%}"
            )
        return payload

    async def settle_jobs_async(
        self,
        character: Character,
        now: datetime | None = None,
    ) -> list[int]:
        """
        惰性推进 running → ready（now >= finish_at）。

        返回:
            本次变为 ready 的 job id 列表。
        """
        now_aware = now_utc(now)
        result = await self._session.execute(
            select(CraftJob).where(
                CraftJob.character_id == character.id,
                CraftJob.status == CraftJobStatus.RUNNING,
            ),
        )
        ready_ids: list[int] = []
        for job in result.scalars().all():
            if now_aware >= job.finish_at:
                job.status = CraftJobStatus.READY
                ready_ids.append(job.id)
        if ready_ids:
            await self._session.flush()
            logger.info("craft jobs ready character_id=%s ids=%s", character.id, ready_ids)
        return ready_ids

    async def claim(
        self,
        user: User,
        job_id: int,
        *,
        rng: random.Random | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        领取完成品：入背包或 array_craft_level++。

        领取前先 settle，避免 finish_at 已到但 status 仍为 running。

        异常:
            AppError: 任务不存在或不可领取。
        """
        character = await self._gate.require_character(user)
        await self.settle_jobs_async(character, now=now)

        result = await self._session.execute(
            select(CraftJob)
            .where(CraftJob.id == job_id, CraftJob.character_id == character.id)
            .limit(1),
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AppError(code=40000, message="工坊任务不存在", http_status=404)
        if job.status == CraftJobStatus.CLAIMED:
            raise AppError(code=40000, message="任务已领取", http_status=400)
        if job.status == CraftJobStatus.RUNNING:
            raise AppError(code=40000, message="任务尚未完成", http_status=400)

        cfg = get_game_config().craft_recipes
        recipe = cfg.recipes.get(job.recipe_id)
        if recipe is None:
            raise AppError(code=40000, message="配方配置缺失", http_status=500)

        # 已标记 failed 的任务直接按失败结算；否则按 fail_chance 掷骰
        failed = True if job.status == CraftJobStatus.FAILED else roll_fail(
            recipe.fail_chance,
            rng=rng,
        )
        claim_result: dict[str, Any] = {"job_id": job.id, "failed": failed}

        if failed:
            job.status = CraftJobStatus.FAILED
            job.result_json = json.dumps({"failed": True}, ensure_ascii=False)
        else:
            job.status = CraftJobStatus.CLAIMED
            outputs: list[dict[str, Any]] = []
            for out in recipe.outputs:
                if out.grant_array_craft_level > 0:
                    character.array_craft_level = (
                        int(character.array_craft_level) + out.grant_array_craft_level
                    )
                    outputs.append({"grant_array_craft_level": out.grant_array_craft_level})
                elif out.item_id:
                    await self._inventory.add_item(
                        character.id,
                        item_type=str(out.item_type or "material"),
                        item_id=str(out.item_id),
                        quantity=int(out.quantity),
                    )
                    outputs.append(
                        {
                            "item_type": out.item_type,
                            "item_id": out.item_id,
                            "quantity": out.quantity,
                        },
                    )
            job.result_json = json.dumps(
                {"failed": False, "outputs": outputs},
                ensure_ascii=False,
            )
            claim_result["outputs"] = outputs

        await self._session.flush()
        logger.info(
            "craft claimed character_id=%s job_id=%s failed=%s",
            character.id,
            job.id,
            failed,
        )
        return claim_result
