"""傀儡行动体（战斗面）；背包面见 ``PuppetItem``。"""

from __future__ import annotations

from typing import Any, Iterable

from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.minion import SenseMinionCharacter, default_divine_sense_cost


class PuppetCharacter(SenseMinionCharacter):
    """
    傀儡战斗体。

    Attributes:
        def_id: 模板/物品定义 id。
        ephemeral: True 表示试炼木傀（无背包行，不占神识）。
        bound_item_uid: 模型 A 下绑定的背包 uid。
    """

    kind = "puppet"

    def __init__(
        self,
        *,
        def_id: str,
        stats: dict[str, Any] | None = None,
        ephemeral: bool = False,
        bound_item_uid: str | None = None,
        instance_id: int | str | None = None,
        grant_sources: list[GrantSource] | None = None,
        label_zh: str | None = None,
        divine_sense_cost: int | None = None,
    ) -> None:
        self.def_id = def_id
        self._stats = dict(stats or {})
        self.ephemeral = ephemeral
        self.bound_item_uid = bound_item_uid
        self.instance_id = instance_id
        self._grant_sources = list(grant_sources or [])
        self._label_zh = label_zh or def_id
        cost = (
            int(divine_sense_cost)
            if divine_sense_cost is not None
            else default_divine_sense_cost("puppet", ephemeral=ephemeral)
        )
        self._init_sense_cost(cost)

    def get_entity_kind(self) -> str:
        return "puppet"

    def get_piece_kind(self) -> str:
        return "puppet"

    def build_base_attrs(self) -> dict[str, Any]:
        return {"combat": {"final": dict(self._stats)}}

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return list(self._grant_sources)

    def can_be_deployed(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self._label_zh

    def on_battle_enter(
        self,
        *,
        unit_uid: str,
        side: str,
        x: int,
        y: int,
        ctx: dict[str, Any] | None = None,
    ) -> BattleUnitSeed:
        del ctx
        return BattleUnitSeed(
            unit_uid=unit_uid,
            unit_kind="puppet",
            side=side,
            x=x,
            y=y,
            ref_id=self.instance_id or self.bound_item_uid or self.def_id,
            stats=self.battle_core_stats(),
            meta={
                "entity_kind": "puppet",
                "def_id": self.def_id,
                "ephemeral": self.ephemeral,
                "name": self.display_name,
            },
        )
