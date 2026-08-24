"""玩家角色领域门面（包装 ORM Character，无 Session）。"""

from __future__ import annotations

from typing import Any, Iterable

from app.constants.character import (
    CHARACTER_STATUS_DEAD,
    CHARACTER_STATUS_PENDING_FERRY,
)
from app.game.ability.grant import GrantSource
from app.game.battle.seed import BattleUnitSeed
from app.game.character.sapient import PlayerNpcCharacter
from app.domain.env_preview import parse_spirit_root_tags_json


class PlayerCharacter(PlayerNpcCharacter):
    """
    玩家本体行动体。

    Attributes:
        row: ORM ``Character``（仅作数据载体；禁止在此开事务）。
        _attr_cache: 可选预计算 ATTR 块。
    """

    kind = "player"

    def __init__(
        self,
        row: Any,
        *,
        attr_block: dict[str, Any] | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_capacity: int = 0,
        divine_sense_load: int = 0,
    ) -> None:
        """
        Args:
            row: ``app.db.models.character.Character``。
            attr_block: 预组装的 combat/life 块；缺省时 ``build_base_attrs`` 返回最小 stats。
            grant_sources: 已展开的授予源（过渡期可空）。
            divine_sense_capacity: 自身神识总量。
            divine_sense_load: 已使用神识（上阵随从合计）。
        """
        self.row = row
        self._attr_cache = attr_block
        self._grant_sources = list(grant_sources or [])
        self._init_sense(
            divine_sense_capacity=divine_sense_capacity,
            divine_sense_load=divine_sense_load,
        )

    @classmethod
    def from_orm(
        cls,
        row: Any,
        *,
        attr_block: dict[str, Any] | None = None,
        grant_sources: list[GrantSource] | None = None,
        divine_sense_capacity: int = 0,
        divine_sense_load: int = 0,
    ) -> PlayerCharacter:
        """自 ORM 行构建门面。"""
        inst = cls(
            row,
            attr_block=attr_block,
            grant_sources=grant_sources,
            divine_sense_capacity=divine_sense_capacity,
            divine_sense_load=divine_sense_load,
        )
        inst.set_spirit_root_tags(
            parse_spirit_root_tags_json(getattr(row, "spirit_root_tags_json", None)),
        )
        return inst

    def get_entity_kind(self) -> str:
        return "player"

    def get_piece_kind(self) -> str:
        return "main"

    def get_major_realm(self) -> str:
        return str(getattr(self.row, "major_realm", "") or "")

    def get_realm_stage(self) -> int:
        return int(getattr(self.row, "realm_stage", 1) or 1)

    def get_realm_progress(self) -> int:
        return int(getattr(self.row, "realm_progress", 0) or 0)

    def can_enter_dao_lordship(self) -> bool:
        """玩家本体可以就任道主（门槛另由大道系统判定）。"""
        return True

    def can_enter_reincarnation_realm(self) -> bool:
        """玩家本体是轮回外环主体。"""
        return True

    def build_base_attrs(self) -> dict[str, Any]:
        if self._attr_cache is not None:
            return self._attr_cache
        # 无缓存时给出引擎兼容最小块（完整 ATTR 由 CharacterService 注入）
        return {
            "combat": {
                "final": {
                    "hp": 1,
                    "phys_atk": 0,
                    "speed": 10,
                    "mp": 0,
                },
            },
        }

    def iter_grant_sources(self) -> Iterable[GrantSource]:
        return list(self._grant_sources)

    def set_attr_cache(self, attr_block: dict[str, Any]) -> None:
        """由服务层在 ``build_combat_attrs`` 后注入。"""
        self._attr_cache = attr_block

    def can_be_deployed(self) -> bool:
        status = getattr(self.row, "status", "idle")
        return status not in {CHARACTER_STATUS_PENDING_FERRY, CHARACTER_STATUS_DEAD}

    @property
    def display_name(self) -> str:
        return str(getattr(self.row, "name", "player"))

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
            ref_id=int(getattr(self.row, "id", 0) or 0),
            stats=self.battle_core_stats(),
            meta={"entity_kind": self.get_entity_kind(), "name": self.display_name},
        )
