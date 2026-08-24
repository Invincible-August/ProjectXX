"""
Equipment HTTP schemas (M8 R0 · 17-zone).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EquipmentEquipRequest(BaseModel):
    """Wear an inventory equipment / pet instance into a pointer slot."""

    slot: str = Field(
        description="指针槽：weapon_1/2、armor_*、accessory_*/ring_*、fabao_*、natal_fabao、fubao、pet",
    )
    item_uid: str = Field(min_length=1, max_length=64)
    actor: str = Field(default="main", description="main=本体，avatar=化身")


class EquipmentUnequipRequest(BaseModel):
    """Remove item from a slot back to bag."""

    slot: str = Field(min_length=1, max_length=32)
    actor: str = Field(default="main", description="main=本体，avatar=化身")


class PuppetLoadoutRequest(BaseModel):
    """Add or remove a puppet inventory instance on the loadout board."""

    item_uid: str = Field(min_length=1, max_length=64)


class PuppetLoadoutReplaceRequest(BaseModel):
    """Replace the whole deployed puppet set (empty list clears)."""

    item_uids: list[str] = Field(default_factory=list, max_length=256)


class AvatarDeployRequest(BaseModel):
    """Toggle whether the condensed avatar is marked as deployed."""

    deployed: bool


class TalismanLoadoutReplaceRequest(BaseModel):
    """Replace equipped talismans; empty list clears. Count uncapped when preload_slots=0."""

    inventory_item_ids: list[int] = Field(default_factory=list, max_length=512)
    item_uids: list[str] = Field(default_factory=list, max_length=512)
