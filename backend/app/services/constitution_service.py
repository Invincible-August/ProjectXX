"""
体质背包、镶嵌槽与创角样本发放（M2 骨架）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.character import Character
from app.db.models.constitution import ConstitutionItem, ConstitutionSlot
from app.schemas.common import AppError
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)

# 创角发放：1 凡体 + 1 主词条 + 2 副词条样本
_STARTER_ITEM_DEFS = (
    "sample_body_root",
    "sample_main_affix_iron",
    "sample_sub_affix_swift",
    "sample_sub_affix_swift",
)


class ConstitutionService:
    """
    Application service for constitution inventory, slots, and equip flows (M2 skeleton).

    Manages starter kit grants, slot initialization, equip/unequip, and placeholder
    upgrade/fuse operations.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize constitution service with a database session.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session

    async def ensure_default_slots(
        self,
        character_id: int,
    ) -> None:
        """
        Initialize main/sub constitution slots (empty) on character creation.

        Args:
            character_id: Character primary key.
        """
        cfg = get_game_config().constitution
        existing = await self._session.execute(
            select(ConstitutionSlot.id)
            .where(ConstitutionSlot.character_id == character_id)
            .limit(1),
        )
        if existing.scalar_one_or_none() is not None:
            return
        for index in range(cfg.main_slots):
            self._session.add(
                ConstitutionSlot(
                    character_id=character_id,
                    slot_type="main",
                    slot_index=index,
                ),
            )
        for index in range(cfg.sub_slots):
            self._session.add(
                ConstitutionSlot(
                    character_id=character_id,
                    slot_type="sub",
                    slot_index=index,
                ),
            )
        await self._session.flush()

    async def grant_starter_constitution_kit(
        self,
        character_id: int,
    ) -> None:
        """
        Grant starter constitution sample items and empty slots on character creation.

        Args:
            character_id: Character primary key.
        """
        await self.ensure_default_slots(character_id)
        cfg = get_game_config().constitution
        for def_id in _STARTER_ITEM_DEFS:
            item_def = cfg.items.get(def_id)
            if item_def is None:
                continue
            self._session.add(
                ConstitutionItem(
                    character_id=character_id,
                    def_id=def_id,
                    quality=item_def.quality,
                    grade=item_def.grade,
                    kind=item_def.kind,
                    is_equipped=False,
                ),
            )
        await self._session.flush()
        logger.info("constitution starter kit granted character_id=%s", character_id)

    async def grant_acceptance_constitution_kit(
        self,
        character: Character,
        *,
        auto_equip: bool = True,
    ) -> dict:
        """
        发放验收用临时主/副词条，并可选自动镶嵌（轮回保留验收）。

        Args:
            character: 角色。
            auto_equip: 是否装入空闲主/副格。

        Returns:
            dict: 最新体质 state。
        """
        await self.ensure_default_slots(character.id)
        cfg = get_game_config().constitution
        granted_ids: list[int] = []
        for def_id in ("accept_main_affix_keep", "accept_sub_affix_keep"):
            item_def = cfg.items.get(def_id)
            if item_def is None:
                continue
            item = ConstitutionItem(
                character_id=character.id,
                def_id=def_id,
                quality=item_def.quality,
                grade=item_def.grade,
                kind=item_def.kind,
                is_equipped=False,
            )
            self._session.add(item)
            await self._session.flush()
            await self._session.refresh(item)
            granted_ids.append(int(item.id))

            if not auto_equip:
                continue
            slot_type = "main" if item_def.kind == "main" else "sub"
            # 找第一个空槽
            slots = await self._session.execute(
                select(ConstitutionSlot).where(
                    ConstitutionSlot.character_id == character.id,
                    ConstitutionSlot.slot_type == slot_type,
                ).order_by(ConstitutionSlot.slot_index.asc()),
            )
            for slot in slots.scalars().all():
                if slot.item_instance_id is None:
                    slot.item_instance_id = item.id
                    item.is_equipped = True
                    break
        await self._session.flush()
        logger.info(
            "acceptance constitution granted character_id=%s items=%s auto_equip=%s",
            character.id,
            granted_ids,
            auto_equip,
        )
        return await self.get_constitution_state(character)

    async def _get_slot(
        self,
        character_id: int,
        slot_type: str,
        slot_index: int,
    ) -> ConstitutionSlot | None:
        """
        Look up a constitution slot row by type and index.

        Args:
            character_id: Character primary key.
            slot_type: ``main`` or ``sub``.
            slot_index: Zero-based slot index.

        Returns:
            ConstitutionSlot | None: Matching slot or None.
        """
        result = await self._session.execute(
            select(ConstitutionSlot).where(
                ConstitutionSlot.character_id == character_id,
                ConstitutionSlot.slot_type == slot_type,
                ConstitutionSlot.slot_index == slot_index,
            ),
        )
        return result.scalar_one_or_none()

    async def get_constitution_state(
        self,
        character: Character,
    ) -> dict:
        """
        Return backpack, slot grid, and equipped summary for a character.

        Args:
            character: Character entity.

        Returns:
            dict: backpack, slots, equipped_summary.
        """
        await self.ensure_default_slots(character.id)
        cfg = get_game_config().constitution

        items_result = await self._session.execute(
            select(ConstitutionItem).where(ConstitutionItem.character_id == character.id),
        )
        items = items_result.scalars().all()
        backpack = []
        for item in items:
            item_def = cfg.items.get(item.def_id)
            backpack.append(
                {
                    "id": item.id,
                    "def_id": item.def_id,
                    "name": item_def.name if item_def else item.def_id,
                    "quality": item.quality,
                    "grade": item.grade,
                    "kind": item.kind,
                    "is_equipped": item.is_equipped,
                },
            )

        slots_result = await self._session.execute(
            select(ConstitutionSlot).where(ConstitutionSlot.character_id == character.id),
        )
        slots_rows = slots_result.scalars().all()
        slots = []
        equipped_summary: list[dict] = []
        item_by_id = {item.id: item for item in items}
        for slot in slots_rows:
            equipped_item = item_by_id.get(slot.item_instance_id) if slot.item_instance_id else None
            slot_info = {
                "slot_type": slot.slot_type,
                "slot_index": slot.slot_index,
                "item_id": slot.item_instance_id,
            }
            slots.append(slot_info)
            if equipped_item is not None:
                item_def = cfg.items.get(equipped_item.def_id)
                equipped_summary.append(
                    {
                        "slot_type": slot.slot_type,
                        "slot_index": slot.slot_index,
                        "def_id": equipped_item.def_id,
                        "name": item_def.name if item_def else equipped_item.def_id,
                    },
                )

        return {
            "backpack": backpack,
            "slots": slots,
            "equipped_summary": equipped_summary,
        }

    @staticmethod
    def constitution_summary_from_state(state: dict) -> dict:
        """
        Build compact constitution summary for CharacterPublic.

        Args:
            state: Full constitution state dict.

        Returns:
            dict: equipped summary only.
        """
        return {"equipped": state.get("equipped_summary", [])}

    async def equip_constitution_item(
        self,
        character: Character,
        *,
        item_id: int,
        slot_type: str,
        slot_index: int,
    ) -> dict:
        """
        Equip a constitution item into a main or sub slot.

        Args:
            character: Character entity.
            item_id: Backpack item instance id.
            slot_type: ``main`` or ``sub``.
            slot_index: Target slot index.

        Returns:
            dict: Latest constitution state after equip.

        Raises:
            AppError: ``40034`` / ``40035`` validation failures.
        """
        if slot_type not in {"main", "sub"}:
            raise AppError(code=40000, message="无效槽类型", http_status=400)

        item_result = await self._session.execute(
            select(ConstitutionItem).where(
                ConstitutionItem.id == item_id,
                ConstitutionItem.character_id == character.id,
            ),
        )
        item = item_result.scalar_one_or_none()
        if item is None or item.is_equipped:
            raise AppError(code=40035, message="体质物品不存在或不可用", http_status=400)

        cfg = get_game_config().constitution
        item_def = cfg.items.get(item.def_id)
        if item_def is None:
            raise AppError(code=40035, message="体质物品配置缺失", http_status=400)

        # 本体类（凡体）仅占位，不可装入主/副词条格
        if item_def.kind == "body":
            raise AppError(
                code=40034,
                message="本体类体质暂不支持镶嵌主副格（骨架预留）",
                http_status=400,
            )

        if slot_type == "main" and item_def.kind != "main":
            raise AppError(code=40034, message="主格仅可镶嵌主词条", http_status=400)
        if slot_type == "sub" and item_def.kind != "sub":
            raise AppError(code=40034, message="副格仅可镶嵌副词条", http_status=400)

        # 同 def_id 不可重复镶嵌（创角可发多件同名副词条样本）
        dup = await self._session.execute(
            select(ConstitutionItem.id).where(
                ConstitutionItem.character_id == character.id,
                ConstitutionItem.def_id == item.def_id,
                ConstitutionItem.is_equipped.is_(True),
                ConstitutionItem.id != item.id,
            ).limit(1),
        )
        if dup.scalar_one_or_none() is not None:
            raise AppError(code=40034, message="同名体质不可重复镶嵌", http_status=400)

        slot = await self._get_slot(character.id, slot_type, slot_index)
        if slot is None:
            raise AppError(code=40034, message="镶嵌格不存在", http_status=400)
        if slot.item_instance_id is not None:
            raise AppError(code=40034, message="该格已满", http_status=400)

        slot.item_instance_id = item.id
        item.is_equipped = True
        await self._session.flush()
        logger.info(
            "constitution equip character_id=%s item_id=%s slot=%s/%s",
            character.id,
            item_id,
            slot_type,
            slot_index,
        )
        return await self.get_constitution_state(character)

    async def unequip_constitution_item(
        self,
        character: Character,
        *,
        slot_type: str,
        slot_index: int,
    ) -> dict:
        """
        Unequip a constitution item from a slot.

        Args:
            character: Character entity.
            slot_type: ``main`` or ``sub``.
            slot_index: Source slot index.

        Returns:
            dict: Latest constitution state after unequip.

        Raises:
            AppError: ``40034`` / ``40037`` validation failures.
        """
        cooldown = get_settings().constitution_unequip_cooldown_seconds
        if cooldown > 0:
            raise AppError(code=40037, message="卸下冷却中", http_status=400)

        slot = await self._get_slot(character.id, slot_type, slot_index)
        if slot is None or slot.item_instance_id is None:
            raise AppError(code=40034, message="该格无镶嵌物品", http_status=400)

        item_result = await self._session.execute(
            select(ConstitutionItem).where(ConstitutionItem.id == slot.item_instance_id),
        )
        item = item_result.scalar_one_or_none()
        if item is not None:
            item.is_equipped = False
        slot.item_instance_id = None
        await self._session.flush()
        logger.info(
            "constitution unequip character_id=%s slot=%s/%s",
            character.id,
            slot_type,
            slot_index,
        )
        return await self.get_constitution_state(character)

    async def upgrade_constitution_item(
        self,
        character: Character,
        *,
        item_id: int,
    ) -> dict:
        """
        Placeholder upgrade: spend fixed spirit stones for quality text bump.

        Args:
            character: Character entity.
            item_id: Item instance id.

        Returns:
            dict: message and latest constitution state.

        Raises:
            AppError: ``40035`` / ``40036`` validation failures.
        """
        placeholder_cost = 100
        if int(character.spirit_stones) < placeholder_cost:
            raise AppError(code=40036, message="升品材料不足（灵石）", http_status=400)

        item_result = await self._session.execute(
            select(ConstitutionItem).where(
                ConstitutionItem.id == item_id,
                ConstitutionItem.character_id == character.id,
            ),
        )
        item = item_result.scalar_one_or_none()
        if item is None:
            raise AppError(code=40035, message="体质物品不存在", http_status=400)

        character.spirit_stones = int(character.spirit_stones) - placeholder_cost
        await self._session.flush()
        state = await self.get_constitution_state(character)
        logger.info("constitution upgrade placeholder character_id=%s item_id=%s", character.id, item_id)
        return {
            "message": "升品占位成功（M2 骨架）",
            "constitution": state,
        }

    async def fuse_constitution_items(
        self,
        character: Character,
        *,
        item_ids: list[int],
    ) -> dict:
        """
        Placeholder fuse: validate items exist and return stub result.

        Args:
            character: Character entity.
            item_ids: Instance ids to fuse (minimum 2).

        Returns:
            dict: Placeholder fuse outcome with constitution state.

        Raises:
            AppError: ``40035`` / ``40036`` validation failures.
        """
        if len(item_ids) < 2:
            raise AppError(code=40036, message="融合至少需要 2 个物品", http_status=400)

        for item_id in item_ids:
            item_result = await self._session.execute(
                select(ConstitutionItem).where(
                    ConstitutionItem.id == item_id,
                    ConstitutionItem.character_id == character.id,
                    ConstitutionItem.is_equipped.is_(False),
                ),
            )
            if item_result.scalar_one_or_none() is None:
                raise AppError(code=40035, message="融合物品不存在或已镶嵌", http_status=400)

        state = await self.get_constitution_state(character)
        logger.info("constitution fuse placeholder character_id=%s items=%s", character.id, item_ids)
        return {
            "message": "融合占位成功（M2 骨架）",
            "result_item_id": None,
            "constitution": state,
        }

    async def compute_constitution_combat_bonuses(
        self,
        character_id: int,
    ) -> tuple[int, int]:
        """
        Aggregate equipped constitution atk/hp combat bonuses.

        Args:
            character_id: Character primary key.

        Returns:
            tuple[int, int]: (atk_bonus, hp_bonus).
        """
        from app.services.grade_service import GradeService

        bonus = await GradeService(self._session).aggregate_constitution_bonuses(character_id)
        return int(bonus.get("atk_bonus", 0)), int(bonus.get("hp_bonus", 0))


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


async def ensure_default_slots(
    session: AsyncSession,
    character_id: int,
) -> None:
    """Module wrapper delegating to ``ConstitutionService.ensure_default_slots``."""
    await ConstitutionService(session).ensure_default_slots(character_id)


async def grant_starter_constitution_kit(
    session: AsyncSession,
    character_id: int,
) -> None:
    """Module wrapper delegating to ``ConstitutionService.grant_starter_constitution_kit``."""
    await ConstitutionService(session).grant_starter_constitution_kit(character_id)


async def get_constitution_state(
    session: AsyncSession,
    character: Character,
) -> dict:
    """Module wrapper delegating to ``ConstitutionService.get_constitution_state``."""
    return await ConstitutionService(session).get_constitution_state(character)


def constitution_summary_from_state(state: dict) -> dict:
    """Module wrapper delegating to ``ConstitutionService.constitution_summary_from_state``."""
    return ConstitutionService.constitution_summary_from_state(state)


async def equip_constitution_item(
    session: AsyncSession,
    character: Character,
    *,
    item_id: int,
    slot_type: str,
    slot_index: int,
) -> dict:
    """Module wrapper delegating to ``ConstitutionService.equip_constitution_item``."""
    return await ConstitutionService(session).equip_constitution_item(
        character,
        item_id=item_id,
        slot_type=slot_type,
        slot_index=slot_index,
    )


async def unequip_constitution_item(
    session: AsyncSession,
    character: Character,
    *,
    slot_type: str,
    slot_index: int,
) -> dict:
    """Module wrapper delegating to ``ConstitutionService.unequip_constitution_item``."""
    return await ConstitutionService(session).unequip_constitution_item(
        character,
        slot_type=slot_type,
        slot_index=slot_index,
    )


async def upgrade_constitution_item(
    session: AsyncSession,
    character: Character,
    *,
    item_id: int,
) -> dict:
    """Module wrapper delegating to ``ConstitutionService.upgrade_constitution_item``."""
    return await ConstitutionService(session).upgrade_constitution_item(
        character,
        item_id=item_id,
    )


async def fuse_constitution_items(
    session: AsyncSession,
    character: Character,
    *,
    item_ids: list[int],
) -> dict:
    """Module wrapper delegating to ``ConstitutionService.fuse_constitution_items``."""
    return await ConstitutionService(session).fuse_constitution_items(
        character,
        item_ids=item_ids,
    )


async def compute_constitution_combat_bonuses(
    session: AsyncSession,
    character_id: int,
) -> tuple[int, int]:
    """Module wrapper delegating to ``ConstitutionService.compute_constitution_combat_bonuses``."""
    return await ConstitutionService(session).compute_constitution_combat_bonuses(character_id)
