"""
实体可选根：统一 id / 定义引用 / 展示名约定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntityRef:
    """轻量引用：跨域指向某定义或实例。"""

    domain_root: str
    kind: str
    def_id: str | None = None
    instance_id: int | str | None = None
    label_zh: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """序列化为可进战报/日志的原始 dict。"""
        return {
            "domain_root": self.domain_root,
            "kind": self.kind,
            "def_id": self.def_id,
            "instance_id": self.instance_id,
            "label_zh": self.label_zh,
        }
