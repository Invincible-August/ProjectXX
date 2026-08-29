### Task 1: 协议常量、YAML、解析、灵根映射

**Files:**
- Create: `backend/app/constants/technique_craft.py`
- Modify: `backend/app/config_data/research.yaml`
- Modify: `backend/app/services/realm_config.py`（`ResearchConfig` / `_parse_research`）
- Modify: `backend/app/config_source/validate_content.py`
- Test: `backend/tests/test_technique_craft.py`

**Produces:**
- `EFFICACY_IDS: tuple[str, ...] = ("spell_attack", "spell_buff", "martial_attack", "martial_buff", "idle_spirit", "idle_body")`
- `element_ids_from_spirit_root_tags(tags: list[str]) -> list[str]`
- `get_game_config().research.technique_craft` 含失败率、各阶表、词条目录

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_technique_craft.py`：

```python
from app.constants.technique_craft import element_ids_from_spirit_root_tags
from app.services.realm_config import clear_game_config_cache, get_game_config


def test_mixed_root_expands_to_five_elements() -> None:
    got = set(element_ids_from_spirit_root_tags(["mixed_root"]))
    assert got == {"metal", "wood", "water", "fire", "earth"}


def test_metal_root_only_metal() -> None:
    assert element_ids_from_spirit_root_tags(["metal_root"]) == ["metal"]


def test_technique_craft_config_loads() -> None:
    clear_game_config_cache()
    craft = get_game_config().research.technique_craft
    assert abs(craft.blank_to_type_p_element - 0.5) < 1e-6
    assert "spell_attack" in craft.efficacy_weights
    assert craft.embed_fail_rate >= 0
    assert "body_tempering" in craft.ranks
    assert len(craft.affixes) >= 6
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_technique_craft_config_loads -v`

Expected: FAIL（模块或属性不存在）

- [ ] **Step 3: 实现常量与映射**

`backend/app/constants/technique_craft.py`：

```python
from __future__ import annotations
from typing import Final
from app.constants.technique import (
    ELEMENT_EARTH, ELEMENT_FIRE, ELEMENT_METAL, ELEMENT_THUNDER,
    ELEMENT_WATER, ELEMENT_WIND, ELEMENT_WOOD,
)

ERR_CRAFT_CARD: Final[int] = 40220
ERR_CRAFT_EMBED: Final[int] = 40221
ERR_CRAFT_FINALIZE: Final[int] = 40222
ERR_CRAFT_CULTIVATE: Final[int] = 40223
ERR_CRAFT_EQUIP_ROLE: Final[int] = 40224

EFFICACY_SPELL_ATTACK: Final[str] = "spell_attack"
EFFICACY_SPELL_BUFF: Final[str] = "spell_buff"
EFFICACY_MARTIAL_ATTACK: Final[str] = "martial_attack"
EFFICACY_MARTIAL_BUFF: Final[str] = "martial_buff"
EFFICACY_IDLE_SPIRIT: Final[str] = "idle_spirit"
EFFICACY_IDLE_BODY: Final[str] = "idle_body"
EFFICACY_IDS: Final[tuple[str, ...]] = (
    EFFICACY_SPELL_ATTACK, EFFICACY_SPELL_BUFF,
    EFFICACY_MARTIAL_ATTACK, EFFICACY_MARTIAL_BUFF,
    EFFICACY_IDLE_SPIRIT, EFFICACY_IDLE_BODY,
)
IDLE_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_IDLE_SPIRIT, EFFICACY_IDLE_BODY})
SPELL_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_SPELL_ATTACK, EFFICACY_SPELL_BUFF, EFFICACY_IDLE_SPIRIT})
MARTIAL_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_MARTIAL_ATTACK, EFFICACY_MARTIAL_BUFF, EFFICACY_IDLE_BODY})
ATTACK_EFFICACIES: Final[frozenset[str]] = frozenset({EFFICACY_SPELL_ATTACK, EFFICACY_MARTIAL_ATTACK})

CARD_BLANK_ID: Final[str] = "tech_card_blank"
CARD_TYPE_ELEMENT_ID: Final[str] = "tech_card_type_element"
CARD_TYPE_EFFICACY_ID: Final[str] = "tech_card_type_efficacy"
CARD_FORMAL_ELEMENT_ID: Final[str] = "tech_card_formal_element"
CARD_FORMAL_EFFICACY_ID: Final[str] = "tech_card_formal_efficacy"

WEAPON_LIMITS: Final[tuple[str, ...]] = (
    "sword", "saber", "spear", "gauntlet", "bow", "puppet", "avatar",
)

ROOT_TAG_TO_ELEMENTS: Final[dict[str, tuple[str, ...]]] = {
    "metal_root": (ELEMENT_METAL,),
    "wood_root": (ELEMENT_WOOD,),
    "water_root": (ELEMENT_WATER,),
    "fire_root": (ELEMENT_FIRE,),
    "earth_root": (ELEMENT_EARTH,),
    "thunder_root": (ELEMENT_THUNDER,),
    "wind_root": (ELEMENT_WIND,),
    "mixed_root": (ELEMENT_METAL, ELEMENT_WOOD, ELEMENT_WATER, ELEMENT_FIRE, ELEMENT_EARTH),
}

def element_ids_from_spirit_root_tags(tags: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        for el in ROOT_TAG_TO_ELEMENTS.get(str(tag), ()):
            if el not in seen:
                seen.add(el)
                ordered.append(el)
    return ordered
```

- [ ] **Step 4: 追加 `research.yaml` 的 `technique_craft`**

挂在文件根上（与现有 `technique:` 并列）。占位如下（可微调数字，键名必须一致）：

```yaml
technique_craft:
  help_zh: 用空白卡生成属性/效能正式卡，镶入草稿后选发动条件与词条，定稿后可培养。
  blank_to_type_p_element: 0.5
  efficacy_weights:
    spell_attack: 1
    spell_buff: 1
    martial_attack: 1
    martial_buff: 1
    idle_spirit: 1
    idle_body: 1
  embed_fail_rate: 0.2
  affix_upgrade_fail_rate: 0.2
  breakthrough_fail_rate: 0.3
  base_bonus_points: [5, 10, 20]
  affix_upgrade_points: [5, 10, 20]
  spirit_upgrade_cost: [20, 40, 80, 160]
  body_upgrade_cost: [20, 40, 80, 160]
  affix_upgrade_cost: [15, 30, 60, 120]
  affix_reroll_cost: [10, 20, 40, 80]
  breakthrough_cost_cultivation: 50
  breakthrough_cost_body: 50
  ranks:
    body_tempering:
      affix_slots: 1
      base_upgrade_cap: 3
      upgrade_points_required: 10
    qi_refining:
      affix_slots: 2
      base_upgrade_cap: 6
      upgrade_points_required: 100
  weapon_bonus:
    sword: { phys_atk: 2 }
    saber: { phys_atk: 2 }
    spear: { phys_atk: 2 }
    gauntlet: { phys_atk: 2 }
    bow: { phys_atk: 2 }
    puppet: { phys_atk: 2 }
    avatar: { magic_atk: 2 }
  affixes:
    sa_edge:
      label_zh: 法锋
      efficacy_allow: [spell_attack]
      role: attack
      stats: { magic_atk: 3 }
    sb_ward:
      label_zh: 法盾
      efficacy_allow: [spell_buff]
      role: buff
      stats: { magic_def: 3 }
    ma_edge:
      label_zh: 武锋
      efficacy_allow: [martial_attack]
      role: attack
      stats: { phys_atk: 3 }
    mb_ward:
      label_zh: 武御
      efficacy_allow: [martial_buff]
      role: buff
      stats: { phys_def: 3 }
    is_flow:
      label_zh: 周天
      efficacy_allow: [idle_spirit]
      role: idle
      stats: { magic_atk: 1 }
    ib_bone:
      label_zh: 锻骨
      efficacy_allow: [idle_body]
      role: idle
      stats: { phys_atk: 1 }
```

现有 `technique:` 材料会话块保留给兼容，但功法 HTTP 不再使用它创建会话。

- [ ] **Step 5: 解析进 `ResearchConfig.technique_craft`**

在 `realm_config.py` 增加 frozen dataclass `TechniqueCraftConfig`（字段与 YAML 键对应：`blank_to_type_p_element: float`、`efficacy_weights: dict[str, float]`、`ranks: dict[str, TechniqueCraftRankConfig]`、`affixes: dict[str, TechniqueCraftAffixDef]` 等）。`_parse_research` 末尾解析 `raw.get("technique_craft") or {}`，缺省时用与 YAML 相同的占位，避免旧测试环境空段崩掉。

词条 `stats` 必须走现有 `assert_attr_stats`。

- [ ] **Step 6: 校验器**

`validate_content.py`：每个 affix 的 `efficacy_allow` ⊆ `EFFICACY_IDS`；`role` ∈ `{attack, buff, idle, defense}`；`ranks` 的键须为 `realms.yaml` 大境界 id。

- [ ] **Step 7: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py::test_mixed_root_expands_to_five_elements tests/test_technique_craft.py::test_metal_root_only_metal tests/test_technique_craft.py::test_technique_craft_config_loads tests/test_content_validator.py -q`

Expected: PASS

---

