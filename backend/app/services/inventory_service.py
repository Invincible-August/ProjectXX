"""
M4 背包应用服务：列表、增减堆叠、使用消耗品。
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.domain.inventory_rules import apply_remove, can_add_to_stack, max_stack_for
from app.schemas.common import AppError
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


class InventoryService:
    """
    最小背包用例。

    属性:
        _session: 异步数据库会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    async def list_items(self, character_id: int) -> list[dict[str, Any]]:
        """列出角色全部背包行（含 bag_kind）。"""
        result = await self._session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character_id)
            .order_by(InventoryItem.bag_kind, InventoryItem.item_id),
        )
        items = []
        inv_cfg = get_game_config().inventory
        for row in result.scalars().all():
            defn = inv_cfg.items.get(row.item_id)
            items.append(
                {
                    "id": row.id,
                    "item_uid": row.item_uid,
                    "item_type": row.item_type,
                    "item_id": row.item_id,
                    "name": defn.name if defn else row.item_id,
                    "quantity": int(row.quantity),
                    "bag_kind": str(getattr(row, "bag_kind", None) or "normal"),
                    "meta": json.loads(row.meta_json) if row.meta_json else None,
                    # 机缘/交易筛选用（目录权威）
                    "tradable": bool(defn.tradable) if defn is not None else False,
                    "bound": bool(defn.bound) if defn is not None else True,
                    "unique": bool(getattr(defn, "unique", False)) if defn is not None else True,
                    "max_stack": int(defn.max_stack) if defn is not None else 1,
                },
            )
        return items

    async def list_bags(self, character: Character) -> dict[str, Any]:
        """
        分袋列表 + 轮回袋容量摘要。

        Args:
            character: 角色实体。

        Returns:
            dict: normal_items / reincarnation_items / capacities.
        """
        from app.domain.reincarnation_rules import compute_reincarnation_bag_slots

        items = await self.list_items(character.id)
        normal = [x for x in items if x.get("bag_kind") == "normal"]
        rein = [x for x in items if x.get("bag_kind") == "reincarnation"]
        bags_cfg = get_game_config().reincarnation.bags or {}
        cap = compute_reincarnation_bag_slots(
            int(character.reincarnation_count),
            bags_cfg,
        )
        return {
            "normal_items": normal,
            "reincarnation_items": rein,
            "items": items,
            "reincarnation_bag_capacity": cap,
            "reincarnation_bag_used": len(rein),
        }

    async def move_bag(
        self,
        character: Character,
        *,
        item_uid: str,
        target_bag: str,
    ) -> dict[str, Any]:
        """
        在普通袋与轮回袋之间移动一行物品。

        Args:
            character: 角色。
            item_uid: 物品 uid。
            target_bag: ``normal`` 或 ``reincarnation``。

        Returns:
            dict: 移动结果 + 分袋摘要。

        Raises:
            AppError: 物品不存在 / 袋不允许 / 容量不足。
        """
        from app.domain.reincarnation_rules import (
            ERR_BAG_MOVE,
            compute_reincarnation_bag_slots,
        )

        target = (target_bag or "").strip().lower()
        if target not in ("normal", "reincarnation"):
            raise AppError(code=ERR_BAG_MOVE, message="目标袋须为 normal 或 reincarnation", http_status=400)

        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character.id,
                InventoryItem.item_uid == item_uid,
            )
            .limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(code=40000, message="背包物品不存在", http_status=404)

        current = str(getattr(row, "bag_kind", None) or "normal")
        if current == target:
            return {
                "moved": False,
                "message": "已在目标袋中",
                **(await self.list_bags(character)),
            }

        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(row.item_id)
        allowed = defn.bag_allowed if defn is not None else ("normal",)
        if target not in allowed:
            raise AppError(
                code=ERR_BAG_MOVE,
                message=f"「{defn.name if defn else row.item_id}」不可放入{target}袋",
                http_status=400,
            )

        if target == "reincarnation":
            bags_cfg = get_game_config().reincarnation.bags or {}
            cap = compute_reincarnation_bag_slots(
                int(character.reincarnation_count),
                bags_cfg,
            )
            used = await self._session.execute(
                select(InventoryItem.id).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.bag_kind == "reincarnation",
                ),
            )
            if len(used.all()) >= cap:
                raise AppError(
                    code=ERR_BAG_MOVE,
                    message=f"轮回袋已满（容量 {cap}）",
                    http_status=400,
                )

        row.bag_kind = target
        await self._session.flush()
        logger.info(
            "inventory move_bag character_id=%s uid=%s -> %s",
            character.id,
            item_uid,
            target,
        )
        return {
            "moved": True,
            "item_uid": item_uid,
            "bag_kind": target,
            "message": f"已移入{'轮回袋' if target == 'reincarnation' else '普通袋'}",
            **(await self.list_bags(character)),
        }

    async def count_items(self, character_id: int) -> int:
        """背包行数（非堆叠总数）。"""
        result = await self._session.execute(
            select(InventoryItem.id).where(InventoryItem.character_id == character_id),
        )
        return len(result.all())

    async def material_counts(self, character_id: int) -> dict[str, int]:
        """材料 item_id → 数量映射（含 material/consumable 等）。"""
        result = await self._session.execute(
            select(InventoryItem).where(InventoryItem.character_id == character_id),
        )
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            counts[row.item_id] = counts.get(row.item_id, 0) + int(row.quantity)
        return counts

    async def add_item(
        self,
        character_id: int,
        *,
        item_type: str,
        item_id: str,
        quantity: int,
        meta: dict[str, Any] | None = None,
        bag_kind: str = "normal",
    ) -> None:
        """
        增加物品（自动堆叠或新建行；仅同袋内堆叠）。

        参数:
            character_id: 角色 id。
            item_type: 物品类型。
            item_id: 物品 id。
            quantity: 增加数量。
            meta: 可选元数据（傀儡等）。
            bag_kind: ``normal`` 或 ``reincarnation``。
        """
        if quantity <= 0:
            return
        bag = (bag_kind or "normal").strip().lower()
        if bag not in ("normal", "reincarnation"):
            bag = "normal"
        inv_cfg = get_game_config().inventory
        max_stack = max_stack_for(item_id, item_type, inv_cfg)
        remaining = quantity
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_id == item_id,
                InventoryItem.item_type == item_type,
                InventoryItem.bag_kind == bag,
            )
            .order_by(InventoryItem.id),
        )
        rows = list(result.scalars().all())
        for row in rows:
            if remaining <= 0:
                break
            add = can_add_to_stack(int(row.quantity), remaining, max_stack)
            if add > 0:
                row.quantity = int(row.quantity) + add
                remaining -= add
        while remaining > 0:
            add = min(remaining, max_stack)
            uid = f"{item_id}_{secrets.token_hex(4)}"
            self._session.add(
                InventoryItem(
                    character_id=character_id,
                    item_uid=uid,
                    item_type=item_type,
                    item_id=item_id,
                    quantity=add,
                    bag_kind=bag,
                    meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
                ),
            )
            remaining -= add
        await self._session.flush()

    async def remove_materials(
        self,
        character_id: int,
        materials: list[dict[str, Any]],
    ) -> None:
        """
        扣减配方材料。

        异常:
            AppError: 40055 材料不足。
        """
        counts = await self.material_counts(character_id)
        for mat in materials:
            item_id = str(mat["item_id"])
            need = int(mat["quantity"])
            if counts.get(item_id, 0) < need:
                raise AppError(code=40055, message=f"材料不足：{item_id}", http_status=400)
        for mat in materials:
            await self._remove_item_id(character_id, str(mat["item_id"]), int(mat["quantity"]))

    async def _remove_item_id(self, character_id: int, item_id: str, quantity: int) -> None:
        """按 item_id 扣减数量（跨行）。"""
        remaining = quantity
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character_id,
                InventoryItem.item_id == item_id,
            )
            .order_by(InventoryItem.id),
        )
        for row in result.scalars().all():
            if remaining <= 0:
                break
            new_qty, removed = apply_remove(int(row.quantity), remaining)
            remaining -= removed
            if new_qty <= 0:
                await self._session.delete(row)
            else:
                row.quantity = new_qty
        await self._session.flush()

    async def use_item(
        self,
        character: Character,
        *,
        item_uid: str,
        quantity: int = 1,
    ) -> dict[str, Any]:
        """
        使用背包物品（M4：体力丹等）。

        异常:
            AppError: 40000 不存在；40055 数量不足。
        """
        result = await self._session.execute(
            select(InventoryItem)
            .where(
                InventoryItem.character_id == character.id,
                InventoryItem.item_uid == item_uid,
            )
            .limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(code=40000, message="背包物品不存在", http_status=404)
        if int(row.quantity) < quantity:
            raise AppError(code=40055, message="物品数量不足", http_status=400)

        inv_cfg = get_game_config().inventory
        defn = inv_cfg.items.get(row.item_id)
        effect: dict[str, Any] | None = defn.use_effect if defn else None
        applied: dict[str, Any] = {"item_id": row.item_id, "quantity": quantity}

        if effect and effect.get("kind") == "stamina":
            from app.services.stamina_service import StaminaService

            stamina_svc = StaminaService(self._session)
            amount = int(effect.get("amount", 0)) * quantity
            stamina_svc.add_stamina(character, amount)
            applied["stamina_gained"] = amount

        new_qty, _ = apply_remove(int(row.quantity), quantity)
        if new_qty <= 0:
            await self._session.delete(row)
        else:
            row.quantity = new_qty
        await self._session.flush()
        logger.info(
            "inventory use character_id=%s item=%s qty=%s",
            character.id,
            row.item_id,
            quantity,
        )
        return applied
