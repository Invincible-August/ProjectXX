"""灵宠行动体门面。"""

from __future__ import annotations

from typing import Any, Iterable

from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.minion import SenseMinionCharacter, default_divine_sense_cost


class PetCharacter(SenseMinionCharacter):
    """灵宠（ORM Pet）；上阵消耗宿主神识。"""

    kind = "pet"

    def __init__(
        self,
        row: Any,
        *,
        stats: dict[str, Any] | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_cost: int | None = None,
    ) -> None:
        self.row = row
        self._stats = dict(stats or {})
        self._grant_sources = list(grant_sources or [])
        if divine_sense_cost is not None:
            cost = int(divine_sense_cost)
        else:
            cost = default_divine_sense_cost("pet")
            species_id = str(getattr(row, "species_id", "") or "")
            if species_id:
                from app.services.realm_config import get_game_config

                species = get_game_config().pets.species.get(species_id)
                if species is not None and species.divine_sense_cost is not None:
                    cost = int(species.divine_sense_cost)
        self._init_sense_cost(cost)

    @classmethod
    def from_orm(
        cls,
        row: Any,
        *,
        stats: dict[str, Any] | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_cost: int | None = None,
    ) -> PetCharacter:
        return cls(
            row,
            stats=stats,
            grant_sources=grant_sources,
            divine_sense_cost=divine_sense_cost,
        )

    def get_entity_kind(self) -> str:
        return "pet"

    def get_piece_kind(self) -> str:
        return "pet"

    def build_base_attrs(self) -> dict[str, Any]:
        return {"combat": {"final": dict(self._stats)}}

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return list(self._grant_sources)

    def can_be_deployed(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        nick = getattr(self.row, "nickname", None)
        if nick:
            return str(nick)
        return str(getattr(self.row, "species_id", "pet"))

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
            unit_kind="pet",
            side=side,
            x=x,
            y=y,
            ref_id=int(getattr(self.row, "id", 0) or 0),
            stats=self.battle_core_stats(),
            meta={
                "entity_kind": "pet",
                "species_id": getattr(self.row, "species_id", None),
                "name": self.display_name,
            },
        )
