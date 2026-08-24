"""怪物模板行动体（无神识池）。"""

from __future__ import annotations

from typing import Any, Iterable

from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.base import Character


class MonsterCharacter(Character):
    """PVE 怪物模板。"""

    kind = "monster"

    def __init__(
        self,
        *,
        def_id: str,
        stats: dict[str, Any] | None = None,
        label_zh: str | None = None,
        grant_sources: list[GrantSource] | None = None,
        is_boss: bool = False,
    ) -> None:
        self.def_id = def_id
        self._stats = dict(stats or {})
        self._label_zh = label_zh or def_id
        self._grant_sources = list(grant_sources or [])
        self.is_boss = is_boss

    @classmethod
    def from_template(
        cls,
        def_id: str,
        raw: dict[str, Any],
        *,
        is_boss: bool = False,
    ) -> MonsterCharacter:
        """自 pve_monsters 等配置行构建。"""
        stats = dict(raw.get("stats") or raw.get("combat") or {})
        return cls(
            def_id=def_id,
            stats=stats,
            label_zh=str(raw.get("label_zh") or def_id),
            is_boss=is_boss or bool(raw.get("is_boss")),
        )

    def get_entity_kind(self) -> str:
        return "boss" if self.is_boss else "monster"

    def get_piece_kind(self) -> str:
        return "boss" if self.is_boss else "monster"

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
            unit_kind=self.get_piece_kind(),
            side=side,
            x=x,
            y=y,
            ref_id=self.def_id,
            stats=self.battle_core_stats(),
            meta={"entity_kind": self.get_entity_kind(), "name": self.display_name},
        )
