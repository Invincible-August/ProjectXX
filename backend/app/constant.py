"""
常量入口别名（开发计划 §0.6.3 · 长期入口，非临时 shim）。

推荐：``from app.constants import ...`` 或 ``from app.constants.battle import ...``。
本模块再导出常用名，便于 ``from app.constant import PIECE_KIND_MAIN``。
"""

from __future__ import annotations

from app.constants import *  # noqa: F403
from app.constants import __all__ as __all__  # noqa: F401
