"""
授予源协议：装备 / 功法 / 大道 / 道主 / 宗门 / 环境等均可实现。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GrantSource(Protocol):
    """
    可展开为 Ability 列表的授予源。

    存量整改期允许 ``list_ability_ids`` 返回空（尚未 Ability 化）。
    """

    @property
    def source_type(self) -> str:
        """来源类型键（equipment / technique / constitution / dao / …）。"""
        ...

    @property
    def source_id(self) -> str:
        """来源实例或定义 id（用于去重与面板拆解）。"""
        ...

    def list_ability_ids(self) -> list[str]:
        """本源授予的 ability_id 列表（可空）。"""
        ...
