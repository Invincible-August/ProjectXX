"""
M4 工坊应用服务：配方列表、开工、惰性 settle、领取。
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import ensure_aware_utc, now_utc, to_utc_iso
from app.db.models.character import Character
from app.db.models.craft_job import CraftJob
from app.db.models.user import User
from app.domain.craft_rules import (
    bump_craft_level,
    compute_efficiency,
    compute_finish_at,
    read_craft_levels,
    roll_fail,
)
from app.domain.craft_quality import roll_craft_quality
from app.domain.reincarnation_rules import parse_growth_attrs
from app.constants.character import CRAFT_BRANCH_LEVEL_LABEL_ZH, CRAFT_WORKSHOP_BRANCHES
from app.constants.craft import (
    CRAFT_EQUIP_SLOT_GROUP_LABELS_ZH,
    CRAFT_QUALITY_LABEL_ZH,
    ERR_CRAFT_LEVEL,
    ERR_CRAFT_LEVEL_ZH,
    ERR_CRAFT_NOT_WORKSHOP,
    ERR_CRAFT_NOT_WORKSHOP_ZH,
    craft_equip_slot_group,
)
from app.constants.research import TALISMAN_KIND_LABELS_ZH
from app.constants.inventory import (
    INSPECT_REALM_NONE_ZH,
    USE_EFFECT_KIND_LABEL_ZH,
    UseEffectKind,
    inspect_element_view,
)
from app.constants.m4 import CraftActor, CraftJobStatus
from app.schemas.common import AppError
from app.services.avatar_service import AvatarService
from app.services.inventory_service import InventoryService
from app.services.m4_features import require_craft_enabled
from app.services.play_gate import PlayGate
from app.services.realm_config import (
    CraftRecipe,
    CraftRecipeOutput,
    ItemInspectDef,
    get_game_config,
)
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

    @staticmethod
    def _item_label_zh(item_id: str) -> str:
        """背包物品中文名；缺配置时回落 id。"""
        item = get_game_config().inventory.items.get(item_id)
        return item.name if item is not None else item_id

    @staticmethod
    def _output_effect_zh(out: CraftRecipeOutput) -> str:
        """单条产出的玩家可见基础效果。"""
        grant_array = int(out.grant_array_craft_level or 0)
        if grant_array:
            return f"阵法等级 +{grant_array}"
        if not out.item_id:
            return ""
        qty = int(out.quantity or 1)
        item = get_game_config().inventory.items.get(str(out.item_id))
        name = item.name if item is not None else str(out.item_id)
        effect = item.use_effect if item is not None else None
        if isinstance(effect, dict):
            kind = str(effect.get("kind") or "")
            amount = effect.get("amount")
            kind_zh = USE_EFFECT_KIND_LABEL_ZH.get(kind, "")
            if kind == UseEffectKind.STAMINA and amount is not None:
                return f"使用后{kind_zh} {int(amount)}"
            if kind_zh:
                return f"使用后{kind_zh}"
        item_type = str(out.item_type or (item.item_type if item else ""))
        if item_type == "talisman":
            return f"产出符箓「{name}」×{qty}"
        if item_type == "puppet":
            return f"产出傀儡「{name}」可上阵"
        return f"产出{name}×{qty}"

    def _recipe_inspect(self, recipe: CraftRecipe, first_out: CraftRecipeOutput | None) -> dict[str, Any]:
        """Hover condition card from the first output item (or a stable empty frame)."""
        items = get_game_config().inventory.items
        item = items.get(str(first_out.item_id)) if first_out and first_out.item_id else None
        inspect: ItemInspectDef | None = item.inspect if item is not None else None
        effects = list(inspect.effects) if inspect is not None else []
        if not effects and first_out is not None:
            derived = self._output_effect_zh(first_out)
            if derived:
                effects = [derived]
        help_zh = (inspect.help_zh if inspect is not None else "") or (
            self._output_effect_zh(first_out) if first_out is not None else ""
        )
        realm_req = inspect.realm_req_zh if inspect is not None else INSPECT_REALM_NONE_ZH
        element = inspect_element_view(inspect.element if inspect is not None else None)
        branch_lv_zh = CRAFT_BRANCH_LEVEL_LABEL_ZH.get(recipe.branch, "制作等级")
        return {
            "craft_level_label_zh": branch_lv_zh,
            "required_craft_level": int(recipe.required_craft_level or 0),
            "realm_req_zh": realm_req or INSPECT_REALM_NONE_ZH,
            "help_zh": help_zh,
            "effects": [
                {"id": f"e{idx}", "label_zh": tag} for idx, tag in enumerate(effects)
            ],
            "element": element,
        }

    @staticmethod
    def _output_filter_fields(first_out: CraftRecipeOutput | None) -> dict[str, Any]:
        """Resolve workshop filters from the first output item.

        炼器部位读 equipment.yaml slot；符箓功能读道具 talisman_effect_id → 效果表 kind。
        矿板等非装备产出部位为空，筛选「武器」时会被隐藏。
        """
        slot_group: str | None = None
        slot_zh: str | None = None
        talisman_kind: str | None = None
        talisman_kind_zh: str | None = None
        if first_out is not None and first_out.item_id:
            item_id = str(first_out.item_id)
            cfg = get_game_config()
            equipment = cfg.equipment.items.get(item_id)
            if equipment is not None:
                slot_group = craft_equip_slot_group(equipment.slot)
                if slot_group:
                    slot_zh = CRAFT_EQUIP_SLOT_GROUP_LABELS_ZH.get(slot_group)
            item = cfg.inventory.items.get(item_id)
            effect_id = getattr(item, "talisman_effect_id", None) if item is not None else None
            if effect_id:
                effect = cfg.talisman_effects.get(effect_id)
                if effect is not None:
                    talisman_kind = str(effect.kind or "") or None
                    if talisman_kind:
                        talisman_kind_zh = TALISMAN_KIND_LABELS_ZH.get(talisman_kind)
        return {
            "equip_slot_group": slot_group,
            "equip_slot_group_zh": slot_zh,
            "talisman_kind": talisman_kind,
            "talisman_kind_zh": talisman_kind_zh,
        }

    def list_recipes(self, character: Character) -> list[dict[str, Any]]:
        """配方列表：制作等级不足则 locked；悬停读成品单一属性与功效。"""
        cfg = get_game_config().craft_recipes
        levels = read_craft_levels(
            growth_attrs=parse_growth_attrs(getattr(character, "growth_attrs_json", None)),
            array_craft_level=int(getattr(character, "array_craft_level", 0) or 0),
        )
        out: list[dict[str, Any]] = []
        for recipe in cfg.recipes.values():
            if recipe.branch not in CRAFT_WORKSHOP_BRANCHES:
                continue
            required = int(recipe.required_craft_level or 0)
            current = int(levels.get(recipe.branch, 0) or 0)
            locked = current < required
            branch_lv_zh = CRAFT_BRANCH_LEVEL_LABEL_ZH.get(recipe.branch, "制作等级")
            effects = [self._output_effect_zh(o) for o in recipe.outputs]
            effect_zh = "；".join(part for part in effects if part)
            first_out = recipe.outputs[0] if recipe.outputs else None
            out.append(
                {
                    "recipe_id": recipe.recipe_id,
                    "branch": recipe.branch,
                    "name": recipe.name,
                    "duration_seconds": recipe.duration_seconds,
                    "fail_chance": recipe.fail_chance,
                    "spirit_stone_cost": recipe.spirit_stone_cost,
                    "stamina_cost": recipe.stamina_cost,
                    "required_craft_level": required,
                    "recipe_tier": int(recipe.recipe_tier or 1),
                    "craft_level": current,
                    "effect_zh": effect_zh,
                    "inspect": self._recipe_inspect(recipe, first_out),
                    **self._output_filter_fields(first_out),
                    "materials": [
                        {
                            "item_id": m.item_id,
                            "quantity": m.quantity,
                            "label_zh": self._item_label_zh(m.item_id),
                        }
                        for m in recipe.materials
                    ],
                    "locked": locked,
                    "lock_reason": (
                        f"需要{branch_lv_zh} {required}（当前 {current}）"
                        if locked
                        else None
                    ),
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
            "quantity": int(getattr(job, "quantity", 1) or 1),
            "status": job.status,
            "started_at": to_utc_iso(job.started_at),
            "finish_at": to_utc_iso(job.finish_at),
            "total_finish_at": to_utc_iso(CraftService._job_total_finish_at(job)),
            "result": json.loads(job.result_json) if job.result_json else None,
        }

    async def jobs_summary(self, character_id: int) -> dict[str, int]:
        """进行中条数摘要（ready 仅兼容旧数据）。"""
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

    @staticmethod
    def _unit_duration_seconds(job: CraftJob, recipe: CraftRecipe | None) -> float:
        """当前件单次有效耗时（秒）；优先用 started/finish 差以保留效率。"""
        started = ensure_aware_utc(job.started_at)
        finish = ensure_aware_utc(job.finish_at)
        delta = (finish - started).total_seconds()
        if delta > 0.01:
            return delta
        return float(recipe.duration_seconds if recipe else 60)

    @staticmethod
    def _job_total_finish_at(job: CraftJob, recipe: CraftRecipe | None = None) -> datetime:
        """整单预估结束：下一件完成时刻 + 剩余 (qty-1) 件。"""
        qty = max(1, int(getattr(job, "quantity", 1) or 1))
        unit = CraftService._unit_duration_seconds(job, recipe)
        return ensure_aware_utc(job.finish_at) + timedelta(seconds=unit * max(0, qty - 1))

    async def _queue_anchor_at(
        self,
        character_id: int,
        actor: str,
        *,
        now: datetime,
    ) -> datetime:
        """
        同 actor 队尾锚点：取各 running 整单结束时刻的最大值（若晚于 now），否则 now。
        """
        result = await self._session.execute(
            select(CraftJob).where(
                CraftJob.character_id == character_id,
                CraftJob.actor == actor,
                CraftJob.status == CraftJobStatus.RUNNING,
            ),
        )
        cfg = get_game_config().craft_recipes
        anchor = now
        for job in result.scalars().all():
            recipe = cfg.recipes.get(job.recipe_id)
            total_end = self._job_total_finish_at(job, recipe)
            if total_end > anchor:
                anchor = total_end
        return anchor

    async def start(
        self,
        user: User,
        *,
        recipe_id: str,
        actor: str = CraftActor.MAIN,
        use_dao: bool = False,
        quantity: int = 1,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        开工入队：立即冻材料/灵石/体力；挂到同 actor 队尾。
        quantity 为剩余件数；逐件完成后入包并递减。
        """
        require_craft_enabled()
        from app.domain.activity_mutex import Activity

        character, _ = await self._gate.prepare_for_play(
            user,
            now=now,
            require=Activity.START_CRAFT,
        )
        await self.settle_jobs_async(character, now=now)

        qty = int(quantity)
        if qty < 1 or qty > 99:
            raise AppError(code=40000, message="制造数量须在 1～99", http_status=400)

        cfg = get_game_config().craft_recipes
        recipe = cfg.recipes.get(recipe_id)
        if recipe is None:
            raise AppError(code=40000, message=f"未知配方：{recipe_id}", http_status=404)
        if recipe.branch not in CRAFT_WORKSHOP_BRANCHES:
            raise AppError(
                code=ERR_CRAFT_NOT_WORKSHOP,
                message=ERR_CRAFT_NOT_WORKSHOP_ZH,
                http_status=400,
            )

        levels = read_craft_levels(
            growth_attrs=parse_growth_attrs(getattr(character, "growth_attrs_json", None)),
            array_craft_level=int(getattr(character, "array_craft_level", 0) or 0),
        )
        if int(levels.get(recipe.branch, 0) or 0) < int(recipe.required_craft_level or 0):
            raise AppError(code=ERR_CRAFT_LEVEL, message=ERR_CRAFT_LEVEL_ZH, http_status=400)

        if actor not in (CraftActor.MAIN, CraftActor.AVATAR):
            raise AppError(code=40000, message="actor 须为 main 或 avatar", http_status=400)

        avatar_row = await self._avatar.get_avatar_row(character.id)
        if actor == CraftActor.AVATAR and avatar_row is None:
            raise AppError(code=40051, message="尚未凝练化身", http_status=400)
        if actor == CraftActor.AVATAR:
            from app.constants.m4 import AvatarFeature

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

        mats = [
            {"item_id": m.item_id, "quantity": int(m.quantity) * qty}
            for m in recipe.materials
        ]
        stone_cost = int(recipe.spirit_stone_cost) * qty
        stamina_cost = int(recipe.stamina_cost) * qty
        if int(character.spirit_stones) < stone_cost:
            raise AppError(code=40000, message="灵石不足以开工", http_status=400)

        dao_usage_info: dict[str, Any] | None = None
        if use_dao:
            from app.services.dao_service import DaoService

            dao_usage_info = await DaoService(self._session).consume_usage(
                character,
                kind="craft",
                success=True,
                actor=actor,
            )

        if stamina_cost > 0:
            self._stamina.spend_amount(
                character,
                stamina_cost,
                reason="craft",
                now=now,
            )
        await self._inventory.remove_materials(character.id, mats)
        character.spirit_stones = int(character.spirit_stones) - stone_cost

        cost_snapshot = {
            "materials": mats,
            "spirit_stones": stone_cost,
            "stamina": stamina_cost,
            "quantity_total": qty,
        }

        eff = compute_efficiency(
            actor=actor,
            character_idle_direction=character.idle_direction,
            avatar_idle_direction=avatar_row.idle_direction if avatar_row else None,
            main_crafting_bonus=cfg.main_crafting_bonus,
        )
        from app.domain.env_modifiers import resolve_craft_branch_mult
        from app.domain.weather_rules import build_env_lock
        from app.services.calendar_service import CalendarService
        from app.services.weather_service import WeatherService

        now_aware = now_utc(now)
        started = await self._queue_anchor_at(character.id, actor, now=now_aware)
        cal = CalendarService().get_snapshot(now=now_aware)
        weather_id = WeatherService().get_underlying_weather_id(now=now_aware)
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

        # finish_at = 当前这一件完成时刻；整单时长由 quantity 件累加
        finish = compute_finish_at(started, int(recipe.duration_seconds), eff)

        job = CraftJob(
            character_id=character.id,
            actor=actor,
            recipe_id=recipe_id,
            quantity=qty,
            started_at=started,
            finish_at=finish,
            status=CraftJobStatus.RUNNING,
            cost_snapshot_json=json.dumps(cost_snapshot, ensure_ascii=False),
            env_lock_json=json.dumps(env_lock.to_dict(), ensure_ascii=False),
        )
        self._session.add(job)
        await self._session.flush()
        await self._session.refresh(job)
        logger.info(
            "craft started character_id=%s job_id=%s recipe=%s qty=%s actor=%s eff=%s",
            character.id,
            job.id,
            recipe_id,
            qty,
            actor,
            eff,
        )
        payload = self._job_to_dict(job)
        if dao_usage_info is not None:
            payload["dao_usage"] = dao_usage_info
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
        *,
        rng: random.Random | None = None,
    ) -> list[int]:
        """
        惰性结算：到期则逐件入包；quantity 递减，归零才完结。
        """
        now_aware = now_utc(now)
        result = await self._session.execute(
            select(CraftJob)
            .where(
                CraftJob.character_id == character.id,
                CraftJob.status.in_((CraftJobStatus.RUNNING, CraftJobStatus.READY)),
            )
            .order_by(CraftJob.id.asc()),
        )
        touched_ids: list[int] = []
        for job in result.scalars().all():
            if job.status == CraftJobStatus.READY:
                await self._resolve_finished_job(character, job, rng=rng, now=now_aware)
                touched_ids.append(job.id)
                continue
            if now_aware < ensure_aware_utc(job.finish_at):
                continue
            await self._resolve_finished_job(character, job, rng=rng, now=now_aware)
            touched_ids.append(job.id)
        if touched_ids:
            await self._session.flush()
            logger.info(
                "craft jobs settled character_id=%s ids=%s",
                character.id,
                touched_ids,
            )
        return touched_ids

    async def _grant_one_unit(
        self,
        character: Character,
        job: CraftJob,
        recipe: CraftRecipe,
        *,
        rng: random.Random | None = None,
        grant_craft_level: bool = False,
    ) -> dict[str, Any]:
        """结算单件：失败不入包；成功入包一件。"""
        failed = roll_fail(recipe.fail_chance, rng=rng)
        unit_result: dict[str, Any] = {"failed": failed}
        if failed:
            return unit_result

        outputs: list[dict[str, Any]] = []
        growth = parse_growth_attrs(getattr(character, "growth_attrs_json", None))
        crafter_level = int(
            read_craft_levels(
                growth_attrs=growth,
                array_craft_level=int(getattr(character, "array_craft_level", 0) or 0),
            ).get(recipe.branch, 0)
            or 0
        )
        level_delta = crafter_level - int(recipe.required_craft_level or 0)
        cfg = get_game_config().craft_recipes
        quality = roll_craft_quality(
            level_delta,
            cfg.quality_by_level_delta,
            rng=rng,
        )
        unit_result["quality"] = quality
        grant_lv = int(recipe.grant_craft_level or 0) if grant_craft_level else 0
        for out in recipe.outputs:
            if grant_craft_level:
                grant_lv += int(getattr(out, "grant_craft_level", 0) or 0)
            if out.grant_array_craft_level > 0:
                character.array_craft_level = (
                    int(character.array_craft_level) + int(out.grant_array_craft_level)
                )
                outputs.append(
                    {"grant_array_craft_level": int(out.grant_array_craft_level)},
                )
            elif out.item_id:
                item_type = str(out.item_type or "material")
                out_qty = int(out.quantity)
                claim_meta: dict[str, Any] = {"quality": quality}
                item_def = get_game_config().inventory.items.get(str(out.item_id))
                effect_id = (
                    getattr(item_def, "talisman_effect_id", None)
                    if item_def is not None
                    else None
                )
                if effect_id:
                    claim_meta["effect_id"] = effect_id
                await self._inventory.add_item(
                    character.id,
                    item_type=item_type,
                    item_id=str(out.item_id),
                    quantity=out_qty,
                    meta=claim_meta,
                )
                from app.constants.inventory import ITEM_TYPE_PUPPET
                from app.services.puppet_service import PuppetService

                if item_type == ITEM_TYPE_PUPPET:
                    await PuppetService(self._session).on_craft_granted(
                        character.id,
                        item_id=str(out.item_id),
                        quantity=out_qty,
                    )
                outputs.append(
                    {
                        "item_type": out.item_type,
                        "item_id": out.item_id,
                        "quantity": out_qty,
                        "quality": quality,
                        "quality_label_zh": CRAFT_QUALITY_LABEL_ZH.get(quality, quality),
                    },
                )
        if grant_lv > 0:
            growth, new_lv = bump_craft_level(
                growth,
                branch=recipe.branch,
                amount=grant_lv,
                array_craft_level=int(character.array_craft_level or 0),
            )
            character.growth_attrs_json = json.dumps(growth, ensure_ascii=False)
            outputs.append({"grant_craft_level": grant_lv, "craft_level": new_lv})
        unit_result["outputs"] = outputs
        return unit_result

    async def _resolve_finished_job(
        self,
        character: Character,
        job: CraftJob,
        *,
        rng: random.Random | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        推进到期件数：每件单独判定并入包；quantity 递减。
        离线追上时可能一次结算多件。
        """
        if job.status in (
            CraftJobStatus.CLAIMED,
            CraftJobStatus.FAILED,
            CraftJobStatus.CANCELLED,
        ):
            return json.loads(job.result_json) if job.result_json else {"job_id": job.id}

        cfg = get_game_config().craft_recipes
        recipe = cfg.recipes.get(job.recipe_id)
        if recipe is None:
            raise AppError(code=40000, message="配方配置缺失", http_status=500)

        now_aware = now_utc(now)
        units_done: list[dict[str, Any]] = []
        # 遗留 ready：整单一次性（兼容）
        if job.status == CraftJobStatus.READY:
            qty = max(1, int(getattr(job, "quantity", 1) or 1))
            for i in range(qty):
                is_last = i == qty - 1
                units_done.append(
                    await self._grant_one_unit(
                        character,
                        job,
                        recipe,
                        rng=rng,
                        grant_craft_level=is_last,
                    ),
                )
            job.quantity = 0
            job.status = CraftJobStatus.CLAIMED
            job.result_json = json.dumps(
                {"failed": False, "units": units_done, "quantity": 0},
                ensure_ascii=False,
            )
            await self._session.flush()
            return {"job_id": job.id, "failed": False, "units": units_done}

        while (
            job.status == CraftJobStatus.RUNNING
            and int(job.quantity or 0) > 0
            and now_aware >= ensure_aware_utc(job.finish_at)
        ):
            remaining_before = int(job.quantity)
            is_last = remaining_before <= 1
            unit = await self._grant_one_unit(
                character,
                job,
                recipe,
                rng=rng,
                grant_craft_level=is_last,
            )
            units_done.append(unit)
            job.quantity = remaining_before - 1
            if job.quantity <= 0:
                job.status = CraftJobStatus.CLAIMED
                job.result_json = json.dumps(
                    {"failed": False, "units": units_done, "quantity": 0},
                    ensure_ascii=False,
                )
                break
            # 推进下一件窗口，不改动已消耗时间
            unit_secs = self._unit_duration_seconds(job, recipe)
            next_start = ensure_aware_utc(job.finish_at)
            job.started_at = next_start
            job.finish_at = next_start + timedelta(seconds=unit_secs)

        if units_done:
            prev = {}
            if job.result_json:
                try:
                    prev = json.loads(job.result_json)
                except json.JSONDecodeError:
                    prev = {}
            merged = list(prev.get("units") or []) + units_done
            job.result_json = json.dumps(
                {
                    "failed": False,
                    "units": merged,
                    "quantity": int(job.quantity or 0),
                },
                ensure_ascii=False,
            )
            await self._session.flush()
            logger.info(
                "craft unit(s) resolved character_id=%s job_id=%s done=%s left=%s",
                character.id,
                job.id,
                len(units_done),
                job.quantity,
            )
        return {
            "job_id": job.id,
            "failed": False,
            "units": units_done,
            "quantity": int(job.quantity or 0),
        }

    async def claim(
        self,
        user: User,
        job_id: int,
        *,
        rng: random.Random | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """兼容旧领取：先 settle；已自动入包则返回结果摘要。"""
        character = await self._gate.require_character(user)
        await self.settle_jobs_async(character, now=now, rng=rng)

        result = await self._session.execute(
            select(CraftJob)
            .where(CraftJob.id == job_id, CraftJob.character_id == character.id)
            .limit(1),
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AppError(code=40000, message="工坊任务不存在", http_status=404)
        if job.status == CraftJobStatus.RUNNING:
            raise AppError(code=40000, message="任务尚未完成", http_status=400)
        if job.status == CraftJobStatus.READY:
            return await self._resolve_finished_job(character, job, rng=rng, now=now)
        if job.status in (CraftJobStatus.CLAIMED, CraftJobStatus.FAILED):
            body = json.loads(job.result_json) if job.result_json else {}
            body.setdefault("job_id", job.id)
            body.setdefault("failed", job.status == CraftJobStatus.FAILED)
            return body
        raise AppError(code=40000, message="任务不可领取", http_status=400)

    async def cancel(
        self,
        user: User,
        job_id: int,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        取消任务：按剩余件数比例退冻；重排后续排队项，不触碰正在制造中的进度。
        """
        require_craft_enabled()
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
        if job.status != CraftJobStatus.RUNNING:
            raise AppError(code=40000, message="仅可取消排队中的任务", http_status=400)

        snapshot: dict[str, Any] = {}
        if job.cost_snapshot_json:
            try:
                snapshot = json.loads(job.cost_snapshot_json)
            except json.JSONDecodeError:
                snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}

        remaining = max(0, int(getattr(job, "quantity", 1) or 1))
        total = max(remaining, int(snapshot.get("quantity_total") or remaining or 1))
        # 已完成件数不退；只退剩余占比
        ratio = remaining / total if total > 0 else 0.0

        refunded_mats: list[dict[str, Any]] = []
        mats = snapshot.get("materials") or []
        if isinstance(mats, list) and ratio > 0:
            inv_cfg = get_game_config().inventory
            for mat in mats:
                if not isinstance(mat, dict):
                    continue
                item_id = str(mat.get("item_id") or "")
                need = int(round(int(mat.get("quantity") or 0) * ratio))
                if not item_id or need <= 0:
                    continue
                item_def = inv_cfg.items.get(item_id)
                item_type = str(item_def.item_type) if item_def is not None else "material"
                await self._inventory.add_item(
                    character.id,
                    item_type=item_type,
                    item_id=item_id,
                    quantity=need,
                )
                refunded_mats.append({"item_id": item_id, "quantity": need})

        stones = int(round(int(snapshot.get("spirit_stones") or 0) * ratio))
        if stones > 0:
            character.spirit_stones = int(character.spirit_stones) + stones

        stamina = int(round(int(snapshot.get("stamina") or 0) * ratio))
        if stamina > 0:
            self._stamina.add_stamina(character, stamina, now=now)

        actor = str(job.actor)
        job.status = CraftJobStatus.CANCELLED
        job.result_json = json.dumps(
            {
                "cancelled": True,
                "refunded": {
                    "spirit_stones": stones,
                    "stamina": stamina,
                    "materials": refunded_mats,
                    "remaining": remaining,
                    "quantity_total": total,
                },
            },
            ensure_ascii=False,
        )
        await self._session.flush()
        await self._rechain_running_jobs(character.id, actor, now=now_utc(now))
        await self._session.flush()
        logger.info(
            "craft cancelled character_id=%s job_id=%s refund_stones=%s refund_stamina=%s rem=%s/%s",
            character.id,
            job_id,
            stones,
            stamina,
            remaining,
            total,
        )
        return {
            "job_id": job_id,
            "cancelled": True,
            "refunded": {
                "spirit_stones": stones,
                "stamina": stamina,
                "materials": refunded_mats,
            },
        }

    async def _rechain_running_jobs(
        self,
        character_id: int,
        actor: str,
        *,
        now: datetime,
    ) -> None:
        """
        重排尚未开始的排队任务；正在制造中的（started_at <= now）进度不动。
        """
        result = await self._session.execute(
            select(CraftJob)
            .where(
                CraftJob.character_id == character_id,
                CraftJob.actor == actor,
                CraftJob.status == CraftJobStatus.RUNNING,
            )
            .order_by(CraftJob.id.asc()),
        )
        jobs = list(result.scalars().all())
        if not jobs:
            return
        cfg = get_game_config().craft_recipes
        cursor = now
        for job in jobs:
            recipe = cfg.recipes.get(job.recipe_id)
            started = ensure_aware_utc(job.started_at)
            # 已开工（含正在做当前件）：保留进度，仅用整单结束时刻推进 cursor
            if started <= now:
                cursor = max(cursor, self._job_total_finish_at(job, recipe))
                continue
            # 排队未开始：接到 cursor 后
            qty = max(1, int(getattr(job, "quantity", 1) or 1))
            unit = int(recipe.duration_seconds if recipe else 60)
            job.started_at = cursor
            job.finish_at = compute_finish_at(cursor, unit, 1.0)
            cursor = self._job_total_finish_at(job, recipe)

    async def scribe_talisman(
        self,
        character: Character,
        *,
        template_id: str,
        quantity: int,
    ) -> dict[str, Any]:
        """Paint copies of a private talisman template into the bag."""
        from app.constants.inventory import ItemType
        from app.constants.research import ERR_RESEARCH_OWNER, SOURCE_LABEL_CUSTOM_ZH
        from app.db.models.research import PrivateTalisman

        tal = get_game_config().research.talisman
        qty = int(quantity)
        if qty < 1 or qty > int(tal.max_batch):
            raise AppError(code=40000, message="画符数量不合法", http_status=400)
        result = await self._session.execute(
            select(PrivateTalisman).where(PrivateTalisman.template_id == template_id).limit(1),
        )
        private = result.scalar_one_or_none()
        if private is None or int(private.character_id) != int(character.id):
            raise AppError(ERR_RESEARCH_OWNER, "符箓图纸不属于当前角色", http_status=403)
        paper_need = int(tal.paper_per_copy) * qty
        try:
            await self._inventory.remove_materials(
                character.id,
                [{"item_id": tal.paper_item_id, "quantity": paper_need}],
            )
        except AppError as exc:
            if exc.code == 40055:
                raise AppError(code=40055, message="符纸不足", http_status=400) from exc
            raise
        await self._inventory.add_item(
            character.id,
            item_type=ItemType.TALISMAN,
            item_id=template_id,
            quantity=qty,
            meta={
                "template_id": template_id,
                "effect_id": private.effect_id,
                "label_zh": private.label_zh,
                "source": private.source,
                "source_label_zh": SOURCE_LABEL_CUSTOM_ZH,
            },
        )
        logger.info(
            "talisman scribed character_id=%s template_id=%s quantity=%s",
            character.id,
            template_id,
            qty,
        )
        return {"template_id": template_id, "quantity": qty, "label_zh": private.label_zh}

    async def _loadout_row(self, character: Character):
        from app.db.models.research import CharacterTalismanLoadout

        result = await self._session.execute(
            select(CharacterTalismanLoadout).where(
                CharacterTalismanLoadout.character_id == character.id,
            ).limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = CharacterTalismanLoadout(character_id=character.id, slots_json="[]")
            self._session.add(row)
            await self._session.flush()
        return row

    async def list_talisman_preload(self, character: Character) -> dict[str, Any]:
        """Return preloaded talisman slots for the workshop bar."""
        from app.db.models.inventory_item import InventoryItem

        tal = get_game_config().research.talisman
        row = await self._loadout_row(character)
        raw_ids = [int(x) for x in json.loads(row.slots_json or "[]") if str(x).isdigit() or isinstance(x, int)]
        slots: list[dict[str, Any]] = []
        for inv_id in raw_ids:
            inv = await self._session.get(InventoryItem, inv_id)
            if inv is None or int(inv.character_id) != int(character.id):
                continue
            meta = json.loads(inv.meta_json or "{}")
            slots.append(
                {
                    "inventory_item_id": inv.id,
                    "item_id": inv.item_id,
                    "quantity": int(inv.quantity),
                    "label_zh": meta.get("label_zh") or inv.item_id,
                    "effect_id": meta.get("effect_id"),
                },
            )
        return {"slots": slots, "max_slots": int(tal.preload_slots)}

    async def set_talisman_preload(
        self,
        character: Character,
        inventory_item_ids: list[int],
    ) -> dict[str, Any]:
        """Replace the preload bar; mark selected rows occupancy=deployed."""
        from app.constants.inventory import ItemType, Occupancy
        from app.db.models.inventory_item import InventoryItem

        tal = get_game_config().research.talisman
        ids = [int(x) for x in inventory_item_ids]
        max_slots = int(tal.preload_slots)
        if max_slots > 0 and len(ids) > max_slots:
            raise AppError(code=40000, message="预载栏已满", http_status=400)
        previous = await self.list_talisman_preload(character)
        for slot in previous["slots"]:
            prev = await self._session.get(InventoryItem, int(slot["inventory_item_id"]))
            if prev is not None:
                await self._inventory.set_occupancy(prev, Occupancy.NONE)
        seen: set[int] = set()
        clean: list[int] = []
        for inv_id in ids:
            if inv_id in seen:
                continue
            seen.add(inv_id)
            inv = await self._session.get(InventoryItem, inv_id)
            if inv is None or int(inv.character_id) != int(character.id):
                raise AppError(code=40055, message="预载符箓不存在", http_status=400)
            if str(inv.item_type) != ItemType.TALISMAN:
                raise AppError(code=40000, message="只能预载符箓", http_status=400)
            if int(inv.quantity) < 1:
                raise AppError(code=40055, message="预载符箓数量不足", http_status=400)
            await self._inventory.set_occupancy(inv, Occupancy.DEPLOYED)
            clean.append(inv_id)
        row = await self._loadout_row(character)
        row.slots_json = json.dumps(clean, ensure_ascii=False)
        await self._session.flush()
        return await self.list_talisman_preload(character)

    async def peek_preloaded_talismans(self, character: Character) -> list[dict[str, Any]]:
        """Battle payload for inject_item_triggers (does not consume)."""
        from app.constants.research import SOURCE_LABEL_CUSTOM_ZH
        from app.db.models.inventory_item import InventoryItem

        listed = await self.list_talisman_preload(character)
        out: list[dict[str, Any]] = []
        for slot in listed["slots"]:
            inv = await self._session.get(InventoryItem, int(slot["inventory_item_id"]))
            if inv is None:
                continue
            meta = json.loads(inv.meta_json or "{}")
            effect_id = str(meta.get("effect_id") or "")
            effect = get_game_config().talisman_effects.get(effect_id)
            out.append(
                {
                    "inventory_item_id": inv.id,
                    "label_zh": str(meta.get("label_zh") or (effect.label_zh if effect else inv.item_id)),
                    "source_label_zh": str(meta.get("source_label_zh") or SOURCE_LABEL_CUSTOM_ZH),
                    "effect_id": effect_id,
                    "trigger": effect.trigger if effect else "first_hit",
                    "kind": effect.kind if effect else "buff",
                    "stack_group": effect.stack_group if effect else effect_id,
                    "magnitude": float(effect.magnitude) if effect else 0.0,
                    "duration_kind": effect.duration_kind if effect else "global",
                    "duration": int(effect.duration) if effect else 0,
                    "attr": effect.attr if effect else "phys_atk",
                    "use_chance": float(effect.use_chance) if effect else 0.0,
                    "hit_chance": float(effect.hit_chance) if effect else 1.0,
                },
            )
        return out

    async def consume_preloaded_talismans(self, character: Character) -> None:
        """Deduct one copy per preloaded slot after a battle trigger."""
        from app.constants.inventory import Occupancy
        from app.db.models.inventory_item import InventoryItem

        listed = await self.list_talisman_preload(character)
        kept: list[int] = []
        for slot in listed["slots"]:
            inv = await self._session.get(InventoryItem, int(slot["inventory_item_id"]))
            if inv is None:
                continue
            qty = int(inv.quantity) - 1
            if qty <= 0:
                await self._session.delete(inv)
                continue
            inv.quantity = qty
            await self._inventory.set_occupancy(inv, Occupancy.DEPLOYED)
            kept.append(int(inv.id))
        row = await self._loadout_row(character)
        row.slots_json = json.dumps(kept, ensure_ascii=False)
        await self._session.flush()
