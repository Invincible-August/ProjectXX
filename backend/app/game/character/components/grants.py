"""存量 GrantSource 门面（S1-3）：功法 / 体质。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.constants.character import GRANT_SOURCE_CONSTITUTION, GRANT_SOURCE_TECHNIQUE


@dataclass
class TechniqueGrantSource:
    """
    功法授予源。

    一期 ``ability_ids`` 可空：数值仍走 ATTR AdditiveSource；
    本对象用于统一 ``iter_grant_sources`` 与后续 Ability 化。
    """

    source_id: str  # 功法定义或角色功法行 id
    ability_ids: list[str] = field(default_factory=list)  # 已绑定的 ability
    label_zh: str = ""  # 中文名（面板拆解）

    @property
    def source_type(self) -> str:
        """来源类型：technique。"""
        return GRANT_SOURCE_TECHNIQUE

    def list_ability_ids(self) -> list[str]:
        """返回授予的 ability id 列表。"""
        return list(self.ability_ids)


@dataclass
class ConstitutionGrantSource:
    """体质词条授予源（同 Technique：一期可空 ability，占位统一管道）。"""

    source_id: str  # 体质条目 id
    ability_ids: list[str] = field(default_factory=list)
    label_zh: str = ""

    @property
    def source_type(self) -> str:
        """来源类型：constitution。"""
        return GRANT_SOURCE_CONSTITUTION

    def list_ability_ids(self) -> list[str]:
        """返回授予的 ability id 列表。"""
        return list(self.ability_ids)
