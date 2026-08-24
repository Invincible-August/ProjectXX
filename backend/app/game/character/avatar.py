"""化身行动体门面：修士子类，上阵消耗宿主神识。"""

from __future__ import annotations

from typing import Any, Iterable

from app.constants.battle import PieceKind
from app.constants.m4 import AvatarStatus
from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.cultivator import CultivatorCharacter
from app.game.character.minion import DivineSenseConsumer, default_divine_sense_cost


class AvatarCharacter(CultivatorCharacter, DivineSenseConsumer):
    """
    化身（ORM Avatar）。

    养成走修士契约（境界/分配/突破）；开战仍带 ``divine_sense_cost``。
    禁止道主境与轮回境；无独立神识池。
    """

    kind = "avatar"

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
        cost = (
            int(divine_sense_cost)
            if divine_sense_cost is not None
            else default_divine_sense_cost(PieceKind.AVATAR)
        )
        self._init_sense_cost(cost)

    @classmethod
    def from_orm(
        cls,
        row: Any,
        *,
        stats: dict[str, Any] | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_cost: int | None = None,
    ) -> AvatarCharacter:
        return cls(
            row,
            stats=stats,
            grant_sources=grant_sources,
            divine_sense_cost=divine_sense_cost,
        )

    def get_entity_kind(self) -> str:
        return "avatar"

    def get_piece_kind(self) -> str:
        return PieceKind.AVATAR

    def get_major_realm(self) -> str:
        return str(getattr(self.row, "major_realm", "") or "")

    def get_realm_stage(self) -> int:
        return int(getattr(self.row, "realm_stage", 1) or 1)

    def get_realm_progress(self) -> int:
        return int(getattr(self.row, "realm_progress", 0) or 0)

    def can_enter_dao_lordship(self) -> bool:
        return False

    def can_enter_reincarnation_realm(self) -> bool:
        return False

    def build_base_attrs(self) -> dict[str, Any]:
        return {"combat": {"final": dict(self._stats)}}

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return list(self._grant_sources)

    def can_be_deployed(self) -> bool:
        return str(getattr(self.row, "status", AvatarStatus.IDLE)) != AvatarStatus.DISABLED

    @property
    def display_name(self) -> str:
        return str(getattr(self.row, "name", "avatar"))

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
            unit_kind=PieceKind.AVATAR,
            side=side,
            x=x,
            y=y,
            ref_id=int(getattr(self.row, "id", 0) or 0),
            stats=self.battle_core_stats(),
            meta={"entity_kind": "avatar", "name": self.display_name},
        )
