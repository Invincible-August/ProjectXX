"""
N5 灵兽蛋孵化应用服务：开工、惰性 settle、领取入园。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.pet_hatch import PetHatchJob
from app.domain.pet_rules import can_hold_more, pick_capture_test_grade
from app.schemas.common import AppError
from app.services.inventory_service import InventoryService
from app.services.m4_features import require_pets_enabled
from app.services.pet_service import PetService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# 会话状态常量（与工坊类似，独立枚举避免耦 craft）
STATUS_HATCHING = "hatching"
STATUS_READY = "ready"
STATUS_CLAIMED = "claimed"


class PetHatchService:
    """
    灵兽蛋孵化用例（N5）。

    属性:
        _session: 请求级异步会话。
        _pets: 灵宠生成服务。
        _inventory: 背包扣蛋。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._pets = PetService(session)
        self._inventory = InventoryService(session)

    def _settle_job(self, job: PetHatchJob, *, now: Any) -> None:
        """若已到 finish_at，将 hatching 推进为 ready。"""
        if job.status != STATUS_HATCHING:
            return
        finish = job.finish_at
        if finish.tzinfo is None:
            from datetime import timezone

            finish = finish.replace(tzinfo=timezone.utc)
        if now_utc(now) >= finish:
            job.status = STATUS_READY

    def _job_public(self, job: PetHatchJob, *, now: Any) -> dict[str, Any]:
        """孵化会话 → API 字典。"""
        self._settle_job(job, now=now)
        eggs_cfg = get_game_config().pet_eggs.eggs
        egg = eggs_cfg.get(job.egg_item_id)
        pets_cfg = get_game_config().pets
        species = pets_cfg.species.get(job.species_id)
        remaining = 0
        if job.status == STATUS_HATCHING:
            finish = job.finish_at
            if finish.tzinfo is None:
                from datetime import timezone

                finish = finish.replace(tzinfo=timezone.utc)
            remaining = max(0, int((finish - now_utc(now)).total_seconds()))
        return {
            "job_id": job.id,
            "egg_item_id": job.egg_item_id,
            "egg_name": egg.name if egg else job.egg_item_id,
            "species_id": job.species_id,
            "species_name": species.name if species else job.species_id,
            "status": job.status,
            "started_at": to_utc_iso(job.started_at),
            "finish_at": to_utc_iso(job.finish_at),
            "remaining_seconds": remaining,
            "result_pet_id": job.result_pet_id,
        }

    async def _count_active(self, character_id: int) -> int:
        """进行中（含待领）会话数。"""
        result = await self._session.execute(
            select(func.count(PetHatchJob.id)).where(
                PetHatchJob.character_id == character_id,
                PetHatchJob.status.in_((STATUS_HATCHING, STATUS_READY)),
            ),
        )
        return int(result.scalar_one())

    async def list_state(self, character: Character) -> dict[str, Any]:
        """
        孵化面板：蛋目录（含持有量）+ 会话列表（惰性 settle）。

        Returns:
            eggs / jobs / max_concurrent / hold_cap。
        """
        require_pets_enabled()
        now = now_utc()
        eggs_cfg = get_game_config().pet_eggs
        inv_counts = await self._inventory.material_counts(character.id)
        eggs_out: list[dict[str, Any]] = []
        for egg_id, egg in eggs_cfg.eggs.items():
            species = get_game_config().pets.species.get(egg.species_id)
            eggs_out.append(
                {
                    "egg_item_id": egg.egg_id,
                    "name": egg.name,
                    "species_id": egg.species_id,
                    "species_name": species.name if species else egg.species_id,
                    "hatch_seconds": egg.hatch_seconds,
                    "spirit_stones": egg.spirit_stones,
                    "owned": int(inv_counts.get(egg_id, 0)),
                },
            )
        result = await self._session.execute(
            select(PetHatchJob)
            .where(PetHatchJob.character_id == character.id)
            .order_by(PetHatchJob.id.desc()),
        )
        jobs = [self._job_public(j, now=now) for j in result.scalars().all()]
        await self._session.flush()
        return {
            "eggs": eggs_out,
            "jobs": jobs,
            "max_concurrent": eggs_cfg.max_concurrent,
            "hold_cap": get_game_config().pets.hold_cap,
            "active_count": await self._count_active(character.id),
        }

    async def start(
        self,
        character: Character,
        *,
        egg_item_id: str,
    ) -> dict[str, Any]:
        """
        消耗 1 枚蛋（+可选灵石）开启孵化会话。

        Raises:
            AppError: 未知蛋 / 库存不足 / 并发上限 / 灵石不足。
        """
        require_pets_enabled()
        egg_id = (egg_item_id or "").strip()
        eggs_cfg = get_game_config().pet_eggs
        egg = eggs_cfg.eggs.get(egg_id)
        if egg is None:
            raise AppError(code=40062, message=f"未知灵兽蛋：{egg_id}", http_status=400)

        pets_cfg = get_game_config().pets
        species = pets_cfg.species.get(egg.species_id)
        if species is None:
            raise AppError(code=40000, message=f"蛋绑定物种缺失：{egg.species_id}", http_status=400)
        if "egg_hatch" not in species.acquire_tags:
            raise AppError(
                code=40000,
                message=f"物种 {egg.species_id} 未开放 egg_hatch",
                http_status=400,
            )

        # 并发上限（0=不限）
        if eggs_cfg.max_concurrent > 0:
            active = await self._count_active(character.id)
            if active >= eggs_cfg.max_concurrent:
                raise AppError(
                    code=40063,
                    message=f"孵化位已满（最多 {eggs_cfg.max_concurrent}）",
                    http_status=400,
                )

        inv_counts = await self._inventory.material_counts(character.id)
        if int(inv_counts.get(egg_id, 0)) < 1:
            raise AppError(code=40055, message=f"背包中没有 {egg.name}", http_status=400)

        cost = int(egg.spirit_stones)
        stones = int(getattr(character, "spirit_stones", 0) or 0)
        if cost > 0 and stones < cost:
            raise AppError(
                code=40012,
                message=f"灵石不足（需要 {cost}，当前 {stones}）",
                http_status=400,
            )

        await self._inventory._remove_item_id(character.id, egg_id, 1)
        if cost > 0:
            character.spirit_stones = stones - cost

        now = now_utc()
        finish = now + timedelta(seconds=max(0, int(egg.hatch_seconds)))
        job = PetHatchJob(
            character_id=character.id,
            egg_item_id=egg_id,
            species_id=egg.species_id,
            started_at=now,
            finish_at=finish,
            status=STATUS_HATCHING,
        )
        self._session.add(job)
        await self._session.flush()
        await self._session.refresh(job)
        self._settle_job(job, now=now)
        await self._session.flush()
        logger.info(
            "pet hatch start character_id=%s job_id=%s egg=%s species=%s finish=%s",
            character.id,
            job.id,
            egg_id,
            egg.species_id,
            to_utc_iso(finish),
        )
        return {
            "job": self._job_public(job, now=now),
            "spirit_stones_spent": cost,
            "spirit_stones": int(character.spirit_stones),
        }

    async def claim(self, character: Character, job_id: int) -> dict[str, Any]:
        """
        领取已完成的孵化：生成灵宠入园。

        Raises:
            AppError: 会话不存在 / 未完成 / 已领 / 持有上限。
        """
        require_pets_enabled()
        now = now_utc()
        result = await self._session.execute(
            select(PetHatchJob).where(
                PetHatchJob.id == int(job_id),
                PetHatchJob.character_id == character.id,
            ),
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AppError(code=40421, message="孵化会话不存在", http_status=404)
        self._settle_job(job, now=now)
        if job.status == STATUS_CLAIMED:
            raise AppError(code=40064, message="该蛋已领取", http_status=400)
        if job.status != STATUS_READY:
            raise AppError(code=40065, message="孵化尚未完成", http_status=400)

        count = await self._pets.count_pets(character.id)
        ok, code = can_hold_more(count, get_game_config().pets.hold_cap)
        if not ok:
            raise AppError(code=code or 40057, message="灵宠持有已达上限", http_status=400)

        eggs_cfg = get_game_config().pet_eggs
        egg = eggs_cfg.eggs.get(job.egg_item_id)
        grade_weights = dict(egg.grade_weights) if egg and egg.grade_weights else None
        if not grade_weights:
            grade_weights = dict(get_game_config().pets.capture_test_grade_weights)
        grade = pick_capture_test_grade(grade_weights)
        pets_cfg = get_game_config().pets
        if pets_cfg.grades and grade not in pets_cfg.grades:
            grade = min(pets_cfg.grades.keys())

        spawned = await self._pets.spawn_owned_pet(
            character,
            species_id=job.species_id,
            grade=grade,
            acquire_tag="egg_hatch",
        )
        job.status = STATUS_CLAIMED
        job.result_pet_id = int(spawned["id"])
        await self._session.flush()
        logger.info(
            "pet hatch claim character_id=%s job_id=%s pet_id=%s species=%s",
            character.id,
            job.id,
            job.result_pet_id,
            job.species_id,
        )
        return {
            "job": self._job_public(job, now=now),
            "pet": spawned["pet"],
            "id": spawned["id"],
            "species_id": spawned["species_id"],
            "grade": spawned["grade"],
        }
