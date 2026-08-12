# 战斗属性 Schema 占位设计（ATTR）

> 依据：`开发计划.md` **§0.6.2** · `project修仙.md` §4 / §7 / §23（GDD **不写公式**，本文件写 **字段与叠层契约**）· 现行 `build_combat_stats` / 自走棋引擎 / 灵宠面板  
> 目标：锁死 **棋子统一战斗属性 schema**、**人物面板派生层**、**来源拆解与叠乘顺序**；数值用占位曲线即可跑通；**正式曲线与满表 → M13 填数，不再重设计字段**  
> 对应延后项：**ATTR-D01**（本文消化设计）；喂入装备/傀儡 → **ATTR-D02（M8）**；野怪满模板 → **ATTR-D03（M9）**；满曲线 → **M13**  
> 版本：v1.0 · 2026-08-11  
> **不单开属性里程碑**：实现可挂 M3-D03 邻近、或与 M7/M8 竖切并行；本轮以文档锁契约为主

---

## 0. 与 M13 的边界（必读）

| 阶段 | 做什么 | 不做什么 |
| --- | --- | --- |
| **现在（ATTR-D01）** | 定 **字段名、中文 label、单位、谁可读、叠层顺序、面板拆解**；YAML/ADM schema；引擎与 `CharacterPublic` 对齐占位 | 追求平衡的正式曲线 |
| **M8（ATTR-D02）** | 装备/丹药/符箓/傀儡 **写入同一 schema**；打开 IDLE-R01 / DICE-R01 通道开关 | 把装备数值调到终局 |
| **M9（ATTR-D03）** | 野怪/NPC **挂同一 schema 的模板行** | AI 行为 |
| **M13** | 替换 `realms.yaml` / 成长表 / 词条系数等为 **正式曲线与全量表** | **重新发明属性字段或另起第二套面板** |

> GDD §23 写「数值框架 — 不设计」= **不在 GDD 写公式与概率表**。  
> **工程侧必须提前设计 schema 占位**，否则 M8/M9/M13 会各写一套 `atk2`/`power`/`damage`。

---

## 1. 设计目标与原则

### 1.1 一句话

以自走棋棋子为中心，定义 **一份** `CombatAttrBlock`：本体 / 化身 / 灵宠 / 傀儡 / 怪物 **同源字段**；人物大厅面板是其上的 **派生展示 + 来源拆解**；结算只认服务端 `build_combat_attrs`（取代/扩展现行 `build_combat_stats`）。

### 1.2 原则

| 原则 | 落地 |
| --- | --- |
| **一套字段** | 禁止宠用 `base_atk`、人用 `attack`、怪用 `damage` 三套语义 |
| **引擎子集** | 棋盘当前只消费已接线的键；未接线键 **仍出现在 schema**，默认 0 / 1.0，战报可不打印 |
| **显性拆解** | 面板必须能答：基础值、有效值、来自境界/品阶/功法/体质/轮回/…（§0.7） |
| **配置中文** | 每个属性键有 `label_zh` / `help_zh`（ADM `combat_attrs` 或并入 realms/items） |
| **占位可跑** | 今日仍可用「境界 base_atk/base_hp + 品阶倍 + 功法/体质加算」填满核心键 |
| **填数不改键** | M13 只改 YAML 数字与曲线函数参数，不改机读键名（除非版本迁移文档） |

### 1.3 成功标准（设计验收 · 本文）

1. 属性键表（核心 / 扩展 / 元数据）写死，含中文名。  
2. 叠乘/加算顺序写死（一句话公式）。  
3. 五类棋子 → schema 映射表。  
4. `CharacterPublic.combat`（或等价）示意 JSON 含 `final` + `breakdown`。  
5. 与现行 `atk/hp/speed/mp` 引擎字段对齐说明；迁移路径清晰。  
6. ATTR-D02/D03/M13 边界无歧义。

### 1.4 明确不做（本设计）

- 正式境界成长曲线、装备词条满库、命中/暴击真实战斗公式（可占位键，**公式关闭**）。  
- 前端本地重算战力。  
- 为 ATTR 单开玩法里程碑或独立路由（大厅/开战面板嵌入即可）。

---

## 2. 分层模型

```text
┌─────────────────────────────────────────────────────────┐
│ Layer C · CombatAttrBlock（棋子开战快照 · 权威）           │
│   final: { hp, atk, speed, mp, defense, … }             │
│   flags: { attack_range, attack_kind, can_fly, … }      │
│   breakdown: [ { source, label_zh, deltas… } ]          │
└──────────────────────────▲──────────────────────────────┘
                           │ build_combat_attrs()
┌──────────────────────────┴──────────────────────────────┐
│ Layer B · 养成贡献源（可开关）                             │
│   realm / grade / technique / constitution / reincarnation│
│   equipment* / pill_buff* / dao_usage* / pet_talent*     │
│   puppet_craft*   （* = M8+ 或通道关闭时贡献 0）           │
└──────────────────────────▲──────────────────────────────┘
                           │ 读配置 + 角色状态
┌──────────────────────────┴──────────────────────────────┐
│ Layer A · 身份与进度                                       │
│   境界层、品阶、功法列表、体质、轮回加成、神识池（非战斗伤）   │
└─────────────────────────────────────────────────────────┘
```

- **神识**：约束上阵强度，**不是** `CombatAttrBlock` 的伤害键；面板另栏展示（已有 `divine_sense`）。  
- **修灵/炼体/制造业三池**：养成资源，**不**直接等于 atk/hp；炼体可经体质/体魄通道间接贡献（配置映射）。

---

## 3. 统一 Schema（`CombatAttrBlock`）

### 3.1 核心战斗键（引擎 / 面板必有）

| 机读键 | 中文 | 类型 | 现行接线 | 说明 |
| --- | --- | --- | --- | --- |
| `hp` | 生命 | int ≥ 1 | ✅ 引擎 `hp`/`max_hp` | 开战快照为当前/最大同源；人物面板展示最大生命 |
| `atk` | 攻击 | int ≥ 1 | ✅ | 普攻威力底 |
| `speed` | 身法 | int ≥ 1 | ✅ 引擎先攻 | 人物占位：可由境界表补 `base_speed`，缺省用配置默认 |
| `mp` | 法力 | int ≥ 0 | ✅ 字段在；消耗链浅 | 技能耗蓝预留；无技能时可为 0 |
| `defense` | 防御 | int ≥ 0 | ❌ 公式未吃 | **占位键**：减伤公式关闭时战报不展示；面板可显示「占位」 |

> 兼容：旧代码 `base_atk`/`base_hp` 仅表示 **境界层贡献源**，不是棋子最终键。最终一律 `atk`/`hp`。

### 3.2 扩展键（schema 有、默认关闭）

| 机读键 | 中文 | 默认 | 何时启用 |
| --- | --- | --- | --- |
| `hit` | 命中 | 0 | M3-D03 / 命中公式开 |
| `dodge` | 闪避 | 0 | 同上 |
| `crit_rate` | 暴击率 | 0.0 | 同上 |
| `crit_damage` | 暴击伤害 | 0.0 | 同上 |
| `penetrate` | 穿透 | 0 | 减防公式开时 |
| `block_rate` | 格挡率 | 0.0 | 可选 |
| `heal_power` | 治疗强度 | 0 | 治疗技能 |
| `shield_power` | 护盾强度 | 0 | 护盾技能 |
| `toughness` | 韧性 | 0 | 控制抗性占位 |

未启用键：**参与 schema 校验与 ADM**，`build` 填默认；引擎忽略。

### 3.3 元数据 / 旗标（非数值成长）

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `attack_range` | 攻击距离 | 已有 |
| `attack_kind` | 攻击类别 | 已有（近战/远程等） |
| `can_fly` | 可飞行 | 已有 |
| `piece_kind` | 棋子类型 | `main` / `avatar` / `pet` / `puppet` / `monster` / `npc` |
| `label_zh` | 显示名 | 战报用 |
| `schema_version` | schema 版本 | 自增；战报/快照携带 |

### 3.4 人物「成长属性」栏（非棋子键，面板并陈）

与 GDD「轮回成长属性 / 体魄」对齐，**单独结构** `GrowthAttrPublic`，避免与棋盘键混淆：

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `physique` | 体魄 | 体质品质主贡献；映射进 `hp`/`defense` 的通道系数可配 |
| `reincarnation_growth` | 轮回成长 | 已有 lifetime 加成；面板显性百分比 |
| `fate_luck` | 气运 | M5 占位字段；渡劫读 |
| `demonic_nature` | 魔性 | 同上 |
| `dao_qi` / `dao_level` | 道值 / 道等级 | M6 已有；运用时另扣，不并入普攻 atk 除非配置 |

---

## 4. 叠层顺序（锁死）

### 4.1 一句话公式（占位）

```text
graded = floor( realm_base × reincarnation_mult × grade_mul )
final  = max( floor_min, graded + Σ(additive_sources) )
# 可选外乘（环境/阵法侧已在开战锁层，不进人物常驻面板）：
# displayed_battle = floor( final × side_combat_mul × env_mul … )
```

| 步骤 | 内容 | 现行对应 |
| --- | --- | --- |
| 1 | 读境界 `base_*` | `realms.yaml` stages |
| 2 | × 轮回乘区 | `combat_attr_multiplier` |
| 3 | × 品阶倍 | `GradeService` |
| 4 | + 功法加算 | `TechniqueService` |
| 5 | + 体质加算 | `ConstitutionService` |
| 6 | + 装备/Buff/傀儡/道… | **通道关闭 → 0**（M8 打开） |
| 7 | clamp 下限（如 atk/hp ≥ 1） | 引擎已有 max(1, …) |

- **禁止**前端再乘一套。  
- **阵法四象 / 天气开战锁**：属战斗实例修正，进战报与开战预览，**不写回**人物常驻 `CombatAttrBlock.final`（可另给 `battle_preview`）。

### 4.2 百分比词条 vs 加算

| 类型 | 约定 |
| --- | --- |
| `add_*` | 在步骤 4～6 加算 |
| `pct_*` | **默认作用于 graded 之后、加算之前**（可配置 `pct_apply: after_grade | after_add`）；M13 可调，键名不变 |
| 同 source 多条 | 先加同层再进下一层；同层内顺序按 `source_order` 配置 |

---

## 5. 五类棋子映射

| `piece_kind` | 主来源 | 备注 |
| --- | --- | --- |
| `main` | 境界+品阶+功法+体质+轮回+（装备） | `build_combat_attrs(character)` |
| `avatar` | 化身境界/能力摘要 × 配置比例（如 50% 占位） | 不吃本体装备除非配置 |
| `pet` | 物种 base_* × 品阶 × 词条投影 | 对齐灵宠系统设计；技能不进棋盘直至 PET-D07 |
| `puppet` | 工坊成品模板 + 养成行 | M8 加深 |
| `monster` / `npc` | 怪物/NPC 模板行 | M9 满模板；现样本可只填 hp/atk/speed |

所有类型输出 **同一 JSON 形**；缺的扩展键填默认。

---

## 6. API / 面板契约（示意）

### 6.1 `CharacterPublic.combat`（增量）

```json
{
  "combat": {
    "schema_version": 1,
    "final": {
      "hp": 120,
      "atk": 15,
      "speed": 10,
      "mp": 0,
      "defense": 0
    },
    "labels": {
      "hp": "生命",
      "atk": "攻击",
      "speed": "身法",
      "mp": "法力",
      "defense": "防御"
    },
    "breakdown": [
      {
        "source": "realm",
        "label_zh": "境界根基",
        "atk": 10,
        "hp": 100,
        "speed": 10
      },
      {
        "source": "grade",
        "label_zh": "突破品阶",
        "atk_mul": 1.2,
        "hp_mul": 1.2
      },
      {
        "source": "technique",
        "label_zh": "功法",
        "atk": 2,
        "hp": 0
      },
      {
        "source": "constitution",
        "label_zh": "体质",
        "atk": 0,
        "hp": 5
      },
      {
        "source": "equipment",
        "label_zh": "装备",
        "enabled": false,
        "note_zh": "通道未开启"
      }
    ],
    "growth": {
      "physique": 0,
      "reincarnation_growth": 0.0,
      "fate_luck": 0,
      "demonic_nature": 0
    }
  }
}
```

兼容：保留顶层 `base_atk` / `base_hp` 为 **final.atk / final.hp 别名**（标废弃），直到前端改读 `combat.final`。

### 6.2 开战单位

布阵/开战把 `CombatAttrBlock.final` + flags 写入 unit dict；与现行引擎键一致，无需改伤害主路径即可验收 schema。

### 6.3 预览

`GET /characters/me/combat` 或嵌入 `/characters/me`：与 settle/开战同一 `build_combat_attrs`。

---

## 7. 配置与 ADM

### 7.1 建议文件

| 文件 | 用途 |
| --- | --- |
| `config_data/combat_attrs.yaml` | 键注册表：`label_zh`、`help_zh`、默认、是否进面板、是否进引擎 |
| `realms.yaml` | 继续提供 `base_atk`/`base_hp`；**增** `base_speed`（缺省回退 `combat_attrs.defaults.speed`） |
| `pets.yaml` / 怪物表 | 已用 base_*；校验器对照注册表 |

### 7.2 `combat_attrs.yaml` 示意

```yaml
schema_version: 1
defaults:
  speed: 10
  mp: 0
  defense: 0
attrs:
  hp:
    label_zh: 生命
    help_zh: 棋盘最大生命；归零阵亡
    engine: true
    panel: true
  atk:
    label_zh: 攻击
    help_zh: 普攻威力底
    engine: true
    panel: true
  speed:
    label_zh: 身法
    help_zh: 先攻排序底；与骰子结合
    engine: true
    panel: true
  mp:
    label_zh: 法力
    help_zh: 施法资源；无技能时可显示 0
    engine: true
    panel: true
  defense:
    label_zh: 防御
    help_zh: 减伤基底（公式未开时仅展示占位）
    engine: false
    panel: true
    formula_enabled: false
channels:
  equipment:
    enabled: false
    label_zh: 装备
  pill_buff:
    enabled: false
    label_zh: 丹药时效
  puppet:
    enabled: false
    label_zh: 傀儡养成
```

ADM 域：`combat_attrs`（或并入 `realms` 高危说明）；字段一律 `label_zh`/`help_zh`。

---

## 8. 代码落点（实现时 · 非本轮必码）

| 位置 | 动作 |
| --- | --- |
| `domain/combat.py` | `CombatStats` → `CombatAttrBlock`（或并存适配器） |
| `CharacterService.build_combat_stats` | 升级为 `build_combat_attrs`，返回 final + breakdown |
| `autochess` unit 构建 | 只读 final 核心键 |
| 前端 `CharacterPanel` | 展示 final + 可折叠 breakdown |
| 单测 | 同源字段；通道关闭时 equipment=0；别名兼容 |

**实现优先级建议**：不阻塞 M7 社交主线；可作为 **P2 并行文档落地的小竖切**（先 schema YAML + breakdown 面板，不改伤害）。

---

## 9. 与既有系统

| 系统 | 关系 |
| --- | --- |
| M3 引擎 | 继续消费 atk/hp/speed/mp；defense 等公式关 |
| M3-D03 | 主动/被动可读写扩展键与 Buff；嘲讽 Phase B 挂靠 |
| 灵宠 | 物种 base_* 已对齐命名；词条投影进同一 final |
| 挂机 IDLE-R01 | 装备通道打开后吃同一 equipment 源 |
| 骰子 DICE-R01 | 装备骰子修正进 bonus_channels，不另起属性名 |
| 道值运用 | 战斗临时乘区进战报，不永久改 final（除非道等级常驻加成配置） |
| 轮回 | 乘区留在步骤 2；成长属性进 `growth` |

---

## 10. 延后与分期

| ID | 本文后状态 | 说明 |
| --- | --- | --- |
| **ATTR-D01** | **设计中 → 实现待做** | 契约以本文为准 |
| **ATTR-D02** | 待做 · M8 | 打开 equipment/puppet 通道 |
| **ATTR-D03** | 待做 · M9 | 怪物模板满字段 |
| **M13 AO1** | 填正式曲线 | **禁止**改键名而无迁移说明 |

---

## 11. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-08-11 | **v1.0**：澄清 M13=填数非设计；锁 CombatAttrBlock、叠层、五类映射、面板 breakdown、ADM 注册表占位 |

---

*冲突时：引擎现行键以代码为准做别名兼容；新键以本文注册表为准。排期见 `开发计划.md` §0.6.2；登记见 `后续待完成.md` ATTR-\*。*
