"""傀儡双切面相关常量（S1-4）。"""

from __future__ import annotations

# 试炼木傀默认模板 id（无背包时的 def_id）
PUPPET_DEF_TRIAL_WOOD: str = "trial_wood_puppet"  # 试炼木傀模板 id

# 试炼木傀默认中文名
PUPPET_LABEL_TRIAL_WOOD: str = "试炼木傀"  # 试炼木傀展示名

# 真傀默认中文名回退
PUPPET_LABEL_GENERIC: str = "傀儡"  # 真傀通用名

# inventory 配置缺省 actor_def_id 时回退用物品自身 id
# （见 PuppetService.resolve_actor_def_id）
