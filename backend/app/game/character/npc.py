"""NPC 战斗模板（与玩家同属神识池子基类，不继承怪物）。"""

from __future__ import annotations

from typing import Any, Iterable

from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.sapient import PlayerNpcCharacter


class NpcCharacter(PlayerNpcCharacter):
    """NPC 行动体：可有神识池；模板数值来自配置行。"""

    kind = "npc"

    def __init__(
        self,
        *,
        def_id: str,
        stats: dict[str, Any] | None = None,
        label_zh: str | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_capacity: int = 0,
        divine_sense_load: int = 0,
    ) -> None:
        """
        Args:
            def_id: NPC 模板 id。
            stats: 扁平战斗数值。
            label_zh: 展示名。
            grant_sources: 授予源。
            divine_sense_capacity: 自身神识总量。
            divine_sense_load: 已使用神识。
        """
        self.def_id = def_id
        self._stats = dict(stats or {})
        self._label_zh = label_zh or def_id
        self._grant_sources = list(grant_sources or [])
        self._init_sense(
            divine_sense_capacity=divine_sense_capacity,
            divine_sense_load=divine_sense_load,
        )
        tags = stats.get("spirit_root_tags") if isinstance(stats, dict) else None
        self.set_spirit_root_tags(list(tags) if isinstance(tags, list) else [])

    @classmethod
    def from_template(
        cls,
        def_id: str,
        raw: dict[str, Any],
    ) -> NpcCharacter:
        """自 NPC 配置行构建。"""
        stats = dict(raw.get("stats") or raw.get("combat") or {})
        tags = raw.get("spirit_root_tags") or raw.get("spirit_roots") or []
        inst = cls(
            def_id=def_id,
            stats=stats,
            label_zh=str(raw.get("label_zh") or def_id),
            divine_sense_capacity=int(raw.get("divine_sense_capacity") or 0),
            divine_sense_load=int(raw.get("divine_sense_load") or 0),
        )
        inst.set_spirit_root_tags(list(tags) if isinstance(tags, list) else [])
        inst._major_realm = str(raw.get("major_realm") or "")
        inst._realm_stage = int(raw.get("realm_stage") or 1)
        inst._realm_progress = int(raw.get("realm_progress") or 0)
        return inst

    def get_entity_kind(self) -> str:
        return "npc"

    def get_piece_kind(self) -> str:
        return "npc"

    def get_major_realm(self) -> str:
        return str(getattr(self, "_major_realm", "") or "")

    def get_realm_stage(self) -> int:
        return int(getattr(self, "_realm_stage", 1) or 1)

    def get_realm_progress(self) -> int:
        return int(getattr(self, "_realm_progress", 0) or 0)

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
