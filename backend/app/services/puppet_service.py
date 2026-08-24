"""
傀儡双切面服务（S1-4）：背包 Item ↔ PuppetActor 一对一。

试炼木傀保持 ephemeral（可无背包行）；真傀炼成/懒加载时确保 Actor 行。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.inventory import ITEM_TYPE_PUPPET
from app.constants.puppet import (
    PUPPET_DEF_TRIAL_WOOD,
    PUPPET_LABEL_GENERIC,
    PUPPET_LABEL_TRIAL_WOOD,
)
from app.db.models.inventory_item import InventoryItem
from app.db.models.puppet_actor import PuppetActor
from app.game.character.puppet import PuppetCharacter
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class PuppetService:
    """傀儡 Actor 创建 / 懒绑定 / 门面构建。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def resolve_actor_def_id(item_id: str) -> str:
        """自 inventory 配置解析 actor_def_id；缺省回退为 item_id。"""
        entry = get_game_config().inventory.items.get(item_id)
        if entry is not None and entry.actor_def_id:
            return str(entry.actor_def_id)
        return item_id

    @staticmethod
    def resolve_label_zh(item_id: str) -> str:
        """物品中文名。"""
        entry = get_game_config().inventory.items.get(item_id)
        if entry is not None and entry.name:
            return str(entry.name)
        return PUPPET_LABEL_GENERIC

    async def get_by_inventory_item_id(self, inventory_item_id: int) -> PuppetActor | None:
        """按背包行查 Actor。"""
        result = await self._session.execute(
            select(PuppetActor).where(PuppetActor.inventory_item_id == inventory_item_id).limit(1),
        )
        return result.scalar_one_or_none()

    async def ensure_for_inventory_item(self, inv: InventoryItem) -> PuppetActor:
        """
        确保背包傀儡行有绑定 Actor（懒创建）。

        Args:
            inv: ``item_type=puppet`` 的背包行。

        Returns:
            PuppetActor: 已有或新建行。
        """
        existing = await self.get_by_inventory_item_id(inv.id)
        if existing is not None:
            return existing
        actor = PuppetActor(
            character_id=int(inv.character_id),
            inventory_item_id=int(inv.id),
            def_id=self.resolve_actor_def_id(str(inv.item_id)),
            ephemeral=False,
            label_zh=self.resolve_label_zh(str(inv.item_id)),
        )
        self._session.add(actor)
        await self._session.flush()
        logger.info(
            "puppet actor created inventory_item_id=%s actor_id=%s def_id=%s",
            inv.id,
            actor.id,
            actor.def_id,
        )
        return actor

    async def ensure_for_character_inventory(self, character_id: int) -> list[PuppetActor]:
        """为角色全部真傀背包行懒绑定 Actor，返回 Actor 列表。"""
        result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_type == ITEM_TYPE_PUPPET,
            ),
        )
        actors: list[PuppetActor] = []
        for inv in result.scalars().all():
            actors.append(await self.ensure_for_inventory_item(inv))
        return actors

    async def on_craft_granted(
        self,
        character_id: int,
        *,
        item_id: str,
        quantity: int = 1,
    ) -> list[PuppetActor]:
        """
        工坊领取傀儡后：确保对应背包行已绑定 Actor。

        注：堆叠行 1:1 Actor（模型 A 建议 puppet max_stack=1）。
        """
        _ = quantity
        result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_type == ITEM_TYPE_PUPPET,
                InventoryItem.item_id == item_id,
            ),
        )
        actors: list[PuppetActor] = []
        for inv in result.scalars().all():
            actors.append(await self.ensure_for_inventory_item(inv))
        return actors

    def build_character_from_actor(
        self,
        actor: PuppetActor,
        *,
        stats: dict[str, Any] | None = None,
    ) -> PuppetCharacter:
        """ORM Actor → PuppetCharacter 门面。"""
        return PuppetCharacter(
            def_id=str(actor.def_id),
            stats=stats,
            ephemeral=bool(actor.ephemeral),
            bound_item_uid=None,
            instance_id=int(actor.id),
            label_zh=actor.label_zh or (PUPPET_LABEL_TRIAL_WOOD if actor.ephemeral else PUPPET_LABEL_GENERIC),
        )

    @staticmethod
    def build_trial_character(
        *,
        trial_index: int,
        stats: dict[str, Any] | None = None,
    ) -> PuppetCharacter:
        """试炼木傀门面（无 DB Actor 亦可）。"""
        return PuppetCharacter(
            def_id=PUPPET_DEF_TRIAL_WOOD,
            stats=stats,
            ephemeral=True,
            instance_id=f"trial:{trial_index}",
            label_zh=PUPPET_LABEL_TRIAL_WOOD,
        )
