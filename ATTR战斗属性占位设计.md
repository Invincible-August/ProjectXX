# 战斗属性 Schema 占位设计（ATTR）

> 依据：`开发计划.md` **§0.6.2** · `project修仙.md` §4 / §7 / §23（GDD **不写公式**，本文件写 **字段与叠层契约**）· 现行 `build_combat_stats` / 自走棋引擎 / 灵宠面板  
> 目标：锁死 **统一属性 schema**（战斗 + 非战斗）、**承载实体清单**、**人物面板派生层**、**来源拆解与叠乘顺序**；数值用占位曲线即可跑通；**正式曲线与满表 → M13 填数，不再重设计字段**  
> 对应延后项：**ATTR-D01**（本文消化设计）；喂入装备/傀儡 → **ATTR-D02（M8）**；野怪满模板 → **ATTR-D03（M9）**；满曲线 → **M13**  
> 版本：v1.2 · 2026-08-12  
> **不单开属性里程碑**：ATTR-D01 已作为 P2 竖切落地（大厅嵌入，无独立路由）

---

## 0. 与 M13 的边界（必读）

| 阶段 | 做什么 | 不做什么 |
| --- | --- | --- |
| **现在（ATTR-D01）** | **已落地**：字段名、中文 label、实体适用面、叠层、面板拆解；YAML/ADM；`build_combat_attrs` + `CharacterPublic` | 追求平衡的正式曲线 |
| **M8（ATTR-D02）** | 装备/丹药/符箓/傀儡 **写入同一 schema**；打开 IDLE-R01 / DICE-R01 通道开关 | 把装备数值调到终局 |
| **M9（ATTR-D03）** | 野怪/NPC/Boss **挂同一 schema 的模板行** | AI 行为 |
| **M13** | 替换 `realms.yaml` / 成长表 / 词条系数等为 **正式曲线与全量表** | **重新发明属性字段或另起第二套面板** |

> GDD §23 写「数值框架 — 不设计」= **不在 GDD 写公式与概率表**。  
> **工程侧必须提前设计 schema 占位**，否则 M8/M9/M13 会各写一套 `atk2`/`power`/`damage`。

---

## 1. 设计目标与原则

### 1.1 一句话

以自走棋棋子为中心，定义 **一份** `CombatAttrBlock` + **一份** `LifeAttrBlock`（非战斗）：玩家本体 / 化身 / 灵宠 / 傀儡 / NPC / 怪物 / Boss / 宗门大阵 **同源字段、按实体裁剪适用面**；人物大厅面板是其上的 **派生展示 + 来源拆解**；结算只认服务端 `build_combat_attrs`（取代/扩展现行 `build_combat_stats`）。

### 1.2 原则

| 原则 | 落地 |
| --- | --- |
| **一套字段** | 禁止宠用 `base_atk`、人用 `attack`、怪用 `damage` 三套语义；物攻/法攻拆键后旧 `atk` 仅作别名 |
| **实体裁剪** | 全量键在注册表；各 `entity_kind` 声明 `uses` / `ignores`，缺省填默认，不当作「另一套 schema」 |
| **引擎子集** | 棋盘当前只消费已接线的键；未接线键 **仍出现在 schema**，默认 0 / 1.0，战报可不打印 |
| **显性拆解** | 面板必须能答：基础值、有效值、来自境界/品阶/功法/体质/轮回/…（§0.7） |
| **战斗 / 生活分栏** | 战斗键进 `CombatAttrBlock`；悟性/体力/吐纳等进 `LifeAttrBlock`；主键可 **映射贡献** 战斗，但面板分栏展示 |
| **配置中文** | 每个属性键有 `label_zh` / `help_zh`（ADM `combat_attrs` 或并入 realms/items） |
| **占位可跑** | 今日仍可用「境界 base_* + 品阶倍 + 功法/体质加算」填满核心键；物/法未拆开的旧数据经别名映射 |
| **填数不改键** | M13 只改 YAML 数字与曲线函数参数，不改机读键名（除非版本迁移文档） |

### 1.3 成功标准（设计验收 · 本文）

1. 属性键表（战斗核心 / 抗性 / 主键 / 扩展 / 非战斗 / 元数据）写死，含中文名。  
2. 承载实体清单与适用面矩阵写死。  
3. 叠乘/加算顺序写死（一句话公式）。  
4. `CharacterPublic.combat` + `life`（或等价）示意 JSON 含 `final` + `breakdown`。  
5. 与现行 `atk/hp/speed/mp` 引擎字段对齐说明；物攻/法攻迁移路径清晰。  
6. ATTR-D02/D03/M13 边界无歧义。

### 1.4 明确不做（本设计）

- 正式境界成长曲线、装备词条满库、命中/暴击/抗性真实战斗公式（可占位键，**公式关闭**）。  
- 前端本地重算战力。  
- 为 ATTR 单开玩法里程碑或独立路由（大厅/开战面板嵌入即可）。

---

## 2. 承载实体（谁用这套字段）

> 所有可参战或可被战斗修正的对象，**只认一套键名**；差异只在「哪些键有意义」与「贡献源从哪读」。

### 2.1 `entity_kind` 清单

| `entity_kind` | 中文 | 典型场景 | 说明 |
| --- | --- | --- | --- |
| `player` | 玩家本体 | 大厅面板、上阵 `main` | 战斗 + 生活全量；养成源最完整 |
| `avatar` | 化身 | 金丹化身上阵 | 战斗子集；生活键默认不读或按比例投影 |
| `pet` | 灵宠 | 上阵宠、灵宠面板 | 战斗为主；部分生活键（如悟性）可作成长 |
| `puppet` | 傀儡 | 工坊成品上阵 | 战斗 + `precision` 养成相关；无心魔/天劫等 |
| `npc` | NPC | 对话战、驻地快照战 | 战斗模板；生活键按需（店主可无） |
| `monster` | 怪物 | 野怪、副本小怪 | 战斗模板行；抗性常用 |
| `boss` | Boss | 精英/首领 | 同怪物 schema；可多填抗性/护盾扩展键与旗标 |
| `sect_formation` | 宗门大阵 | 守山大阵、攻防阵眼 | **战斗实例侧**属性块：耐久/攻防/抗性/阵法乘区；不进人物常驻面板 |

棋盘 `piece_kind` 与上表对齐：`main`←`player`，其余同名；大阵以侧车/目标单位或 `side_mod` 快照挂载，不冒充玩家。

### 2.2 适用面矩阵（✅ 常用 · △ 可选/映射 · — 默认忽略）

| 属性族 | 玩家 | 化身 | 灵宠 | 傀儡 | NPC | 怪 | Boss | 宗门大阵 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 生命 / 物攻物防 / 法攻法防 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅（阵眼耐久≈hp） |
| 速度 / 命中 / 闪避 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | △（阵速/锁定） |
| 法力 `mp` | ✅ | ✅ | △ | △ | △ | △ | ✅ | △（阵灵） |
| 元素抗性七维 | ✅ | ✅ | ✅ | ✅ | △ | ✅ | ✅ | ✅ |
| 主键（力敏智悟根） | ✅ | △ | △ | — | — | — | — | — |
| 生活：体力/吐纳/心魔天劫 | ✅ | — | — | — | — | — | — | — |
| 生活：耐力/灵巧/精密/心性 | ✅ | — | — | △ 精密 | — | — | — | — |
| 阵法侧乘区 `formation_*` | — | — | — | — | — | — | — | ✅ |

忽略键：**仍在 JSON 默认位**，ADM/校验器可见；面板按 `entity_kind` 隐藏。

---

## 3. 分层模型

```text
┌─────────────────────────────────────────────────────────┐
│ Layer C · 开战快照（权威）                                 │
│   CombatAttrBlock.final + flags + breakdown               │
│   （大阵 / 天气等 → battle_preview 或 side_mod，不写回角色） │
└──────────────────────────▲──────────────────────────────┘
                           │ build_combat_attrs()
┌──────────────────────────┴──────────────────────────────┐
│ Layer B · 养成贡献源（可开关）                             │
│   realm / grade / technique / constitution / reincarnation│
│   equipment* / pill_buff* / dao_usage* / pet_talent*     │
│   puppet_craft* / formation_level*  （* = 通道可关）       │
│   primary→combat 映射（力量→物攻 等，系数 YAML）           │
└──────────────────────────▲──────────────────────────────┐
                           │ 读配置 + 角色/模板状态
┌──────────────────────────┴──────────────────────────────┐
│ Layer A · 身份与进度                                       │
│   境界、品阶、功法、体质、轮回、神识池、LifeAttrBlock        │
└─────────────────────────────────────────────────────────┘
```

- **神识**：约束上阵强度，**不是**伤害键；面板另栏（已有 `divine_sense`）。  
- **修灵/炼体/制造业三池**：养成资源，**不**直接等于攻防；经主键/体质/生活键映射。  
- **宗门大阵**：贡献进 Layer C 的开战锁层（`side_mod` / 阵眼单位），**不**写入玩家常驻 `final`。

---

## 4. 统一 Schema

### 4.1 战斗核心键（引擎 / 面板必有 · 物法拆分）

| 机读键 | 中文 | 类型 | 现行接线 | 说明 |
| --- | --- | --- | --- | --- |
| `hp` | 生命 | int ≥ 1 | ✅ | 开战当前/最大同源；面板展示最大生命；大阵=阵眼耐久 |
| `phys_atk` | 物理攻击 | int ≥ 0 | 🔶 经 `atk` 别名 | 普攻/武器物理底 |
| `phys_def` | 物理防御 | int ≥ 0 | ❌ 公式未吃 | 占位；减伤公式关时仅展示 |
| `magic_atk` | 法术攻击 | int ≥ 0 | ❌ | 法术/神通威力底 |
| `magic_def` | 法术防御 | int ≥ 0 | ❌ | 占位 |
| `speed` | 速度 | int ≥ 1 | ✅ 引擎先攻 | 原「身法」展示可仍用中文「速度」；人物可由 `base_speed` 补 |
| `mp` | 法力 | int ≥ 0 | ✅ 字段在；消耗链浅 | 技能耗蓝；无技能可为 0 |
| `hit` | 命中 | int ≥ 0 | ❌ | 命中公式开后启用 |
| `dodge` | 闪避 | int ≥ 0 | ❌ | 同上 |

**兼容别名（迁移期强制）**

| 旧键 | 含义 | 规则 |
| --- | --- | --- |
| `atk` | 攻击 | **读写别名 → `phys_atk`**（占位期引擎只吃物理）；战报可印「攻击」直到物法公式拆开 |
| `defense` | 防御 | **读写别名 → `phys_def`** |

> 旧代码 `base_atk`/`base_hp` 仅表示 **境界层贡献源**，不是最终键。最终一律 `phys_atk`/`hp`（及 `atk` 别名）。

### 4.2 元素抗性（金木水火土风雷）

| 机读键 | 中文 | 默认 | 说明 |
| --- | --- | --- | --- |
| `resist_metal` | 金抗 | 0 | 可为整数抗性点或 0～1 比例；**单位在注册表锁死**，占位用 int 点 |
| `resist_wood` | 木抗 | 0 | 同上 |
| `resist_water` | 水抗 | 0 | 同上 |
| `resist_fire` | 火抗 | 0 | 同上 |
| `resist_earth` | 土抗 | 0 | 同上 |
| `resist_wind` | 风抗 | 0 | 同上 |
| `resist_thunder` | 雷抗 | 0 | 同上 |

公式未开：面板可展示，战报不结算。Boss/大阵优先填满；小怪可只填 0～2 维。

### 4.3 战斗主键（成长向 · 可映射进攻防）

> 面板「资质/根基」栏；**默认不直接进伤害公式**，经 `primary_map` 配置加算进物/法攻防等。

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `strength` | 力量 | 主映射 `phys_atk` / 部分 `phys_def` |
| `agility` | 敏捷 | 主映射 `speed` / `dodge` / `hit` |
| `intelligence` | 智力 | 主映射 `magic_atk` / `mp` |
| `comprehension` | 悟性 | **跨栏**：战斗映射可配；生活栏亦展示（功法领悟等） |
| `bone_root` | 根骨 | 主映射 `hp` / `phys_def` / 炼体通道 |

未启用映射时：主键只展示，贡献 0。

### 4.4 扩展战斗键（schema 有、默认关闭）

| 机读键 | 中文 | 默认 | 何时启用 |
| --- | --- | --- | --- |
| `crit_rate` | 暴击率 | 0.0 | 暴击公式开 |
| `crit_damage` | 暴击伤害 | 0.0 | 同上 |
| `penetrate` | 穿透 | 0 | 减防公式开 |
| `block_rate` | 格挡率 | 0.0 | 可选 |
| `heal_power` | 治疗强度 | 0 | 治疗技能 |
| `shield_power` | 护盾强度 | 0 | 护盾技能 |
| `toughness` | 韧性 | 0 | 控制抗性占位 |

### 4.5 非战斗 / 生活键（`LifeAttrBlock`）

| 机读键 | 中文 | 说明 | 主要消费者 |
| --- | --- | --- | --- |
| `comprehension` | 悟性 | 与 §4.3 **同键**；生活侧：功法领悟、读经、自研成功率权重 | 玩家（宠可选） |
| `stamina` | 体力 | **行动次数 / 体力槽**相关；耗尽限制大动作（非棋盘 HP） | 玩家 |
| `resist_heart_demon` | 心魔抗性 | 心魔事件、走火检定 | 玩家 |
| `resist_tribulation` | 天劫抗性 | 渡劫检定侧 | 玩家 |
| `breath_efficiency` | 吐纳效率 | 修炼/吐纳收益乘区权重 | 玩家 |
| `endurance` | 耐力 | **体修**向；炼体转化、体修挂机 | 玩家 |
| `craft_dexterity` | 灵巧 | **炼器**向成功率/品质权重 | 玩家 |
| `precision` | 精密 | **符箓 / 傀儡**向 | 玩家、傀儡养成 |
| `temperament` | 心性 | **炼丹**向 | 玩家 |

约定：

- `LifeAttrBlock` **不进**自走棋伤害主路径。  
- 渡劫/心魔/工坊/吐纳读生活键；需要时经骰子通道（见 `骰子系统设计.md`），不另起属性名。  
- 既有 `GrowthAttrPublic`（体魄/轮回成长/气运/魔性/道值）**保留并陈**，不与上表抢键：

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `physique` | 体魄 | 体质品质主贡献；可映射 `hp`/`phys_def` |
| `reincarnation_growth` | 轮回成长 | lifetime 加成百分比 |
| `fate_luck` | 气运 | M5 占位；渡劫读 |
| `demonic_nature` | 魔性 | 同上 |
| `dao_qi` / `dao_level` | 道值 / 道等级 | M6；运用另扣，不默认并入普攻 |

### 4.6 元数据 / 旗标（非数值成长）

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `attack_range` | 攻击距离 | 已有 |
| `attack_kind` | 攻击类别 | 近战/远程；与物/法伤害类型可分列 |
| `damage_school` | 伤害流派 | 占位：`physical` / `magic` / `hybrid`（决定吃哪路攻防） |
| `can_fly` | 可飞行 | 已有 |
| `entity_kind` | 实体类型 | 见 §2.1 |
| `piece_kind` | 棋子类型 | `main` / `avatar` / `pet` / `puppet` / `monster` / `npc` / `boss` / `formation` |
| `label_zh` | 显示名 | 战报用 |
| `schema_version` | schema 版本 | 自增；战报/快照携带 |

### 4.7 宗门大阵专用扩展（仍挂同一注册表）

| 机读键 | 中文 | 说明 |
| --- | --- | --- |
| `formation_power` | 阵威 | 对敌伤害/压制底（可映射进物/法攻展示） |
| `formation_stability` | 阵稳 | 抗破阵；可映射 `phys_def`/`magic_def` |
| `formation_cover` | 护宗覆盖 | 友方侧乘区（进 `side_mod`，不写回成员 final） |

大阵模板行可同时填 `hp`、抗性七维与上表；开战锁进守方 `battle_preview`。

---

## 5. 叠层顺序（锁死）

### 5.1 一句话公式（占位）

```text
graded = floor( realm_base × reincarnation_mult × grade_mul )
after_primary = graded + map_primary(strength, agility, …)   # 系数来自 primary_map
final  = max( floor_min, after_primary + Σ(additive_sources) )
# 可选外乘（环境/宗门大阵/天气 · 开战锁层，不进人物常驻面板）：
# displayed_battle = floor( final × side_combat_mul × formation_mul × env_mul … )
```

| 步骤 | 内容 | 现行对应 |
| --- | --- | --- |
| 1 | 读境界/模板 `base_*`（含 `base_phys_atk` 等；旧 `base_atk`→物攻） | `realms.yaml` / 怪表 |
| 2 | × 轮回乘区 | `combat_attr_multiplier` |
| 3 | × 品阶倍 | `GradeService` |
| 4 | + 主键映射 | `primary_map`（可全 0） |
| 5 | + 功法加算 | `TechniqueService` |
| 6 | + 体质加算 | `ConstitutionService` |
| 7 | + 装备/Buff/傀儡/道… | **通道关闭 → 0**（M8 打开） |
| 8 | clamp 下限（如 hp ≥ 1；攻防 ≥ 0） | 引擎已有 max(1, …) 对 hp/atk |

- **禁止**前端再乘一套。  
- **阵法四象 / 宗门大阵 / 天气开战锁**：属战斗实例修正，进战报与开战预览，**不写回**人物常驻 `CombatAttrBlock.final`。

### 5.2 百分比词条 vs 加算

| 类型 | 约定 |
| --- | --- |
| `add_*` | 在步骤 4～7 加算 |
| `pct_*` | **默认作用于 graded 之后、加算之前**（可配置 `pct_apply: after_grade | after_add`）；M13 可调，键名不变 |
| 同 source 多条 | 先加同层再进下一层；同层内顺序按 `source_order` 配置 |

### 5.3 `primary_map` 占位（示意 · 系数可全 0）

```yaml
primary_map:
  strength:
    phys_atk: 0.5
    phys_def: 0.2
  agility:
    speed: 0.3
    dodge: 0.4
    hit: 0.2
  intelligence:
    magic_atk: 0.5
    mp: 1.0
  comprehension:
    # 默认不映射战斗；生活侧单独消费
  bone_root:
    hp: 2.0
    phys_def: 0.3
```

---

## 6. 实体 → schema 映射

| `entity_kind` / `piece_kind` | 主来源 | 备注 |
| --- | --- | --- |
| `player` / `main` | 境界+品阶+功法+体质+轮回+主键映射+（装备）+生活键 | `build_combat_attrs` + `build_life_attrs` |
| `avatar` | 化身境界/能力摘要 × 配置比例 | 不吃本体装备除非配置；生活键默认省略 |
| `pet` | 物种 base_* × 品阶 × 词条投影 | 抗性按物种；技能不进棋盘直至 PET-D07 |
| `puppet` | 工坊成品模板 + 养成行；可读 `precision` | M8 加深 |
| `npc` | NPC 模板行 | M9；可无生活键 |
| `monster` | 怪物模板行 | M9 满模板；现样本可只填 hp/phys_atk/speed |
| `boss` | Boss 模板（可继承 monster 行 + 覆盖） | 抗性/护盾扩展优先填满 |
| `sect_formation` / `formation` | 宗门设施等级 + 阵法配置 | 开战 `side_mod` + 可选阵眼单位；不进成员常驻 final |

所有类型输出 **同一 JSON 形**；不适用键填默认。

---

## 7. API / 面板契约（示意）

### 7.1 `CharacterPublic.combat` + `life`（增量）

```json
{
  "combat": {
    "schema_version": 2,
    "final": {
      "hp": 120,
      "phys_atk": 15,
      "phys_def": 5,
      "magic_atk": 8,
      "magic_def": 4,
      "speed": 10,
      "mp": 20,
      "hit": 0,
      "dodge": 0,
      "resist_fire": 0,
      "resist_thunder": 0,
      "atk": 15,
      "defense": 5
    },
    "primary": {
      "strength": 10,
      "agility": 8,
      "intelligence": 12,
      "comprehension": 15,
      "bone_root": 9
    },
    "labels": {
      "phys_atk": "物理攻击",
      "magic_atk": "法术攻击",
      "speed": "速度",
      "resist_fire": "火抗"
    },
    "breakdown": [
      {
        "source": "realm",
        "label_zh": "境界根基",
        "phys_atk": 10,
        "hp": 100,
        "speed": 10
      },
      {
        "source": "grade",
        "label_zh": "突破品阶",
        "phys_atk_mul": 1.2,
        "hp_mul": 1.2
      },
      {
        "source": "primary_map",
        "label_zh": "根基映射",
        "phys_atk": 5,
        "magic_atk": 6
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
  },
  "life": {
    "schema_version": 2,
    "final": {
      "comprehension": 15,
      "stamina": 100,
      "resist_heart_demon": 0,
      "resist_tribulation": 0,
      "breath_efficiency": 1.0,
      "endurance": 0,
      "craft_dexterity": 0,
      "precision": 0,
      "temperament": 0
    },
    "breakdown": []
  }
}
```

兼容：保留顶层 `base_atk` / `base_hp` 为 **final.phys_atk / final.hp 别名**（标废弃），直到前端改读 `combat.final`。

### 7.2 开战单位

布阵/开战写入 unit dict：`hp` / `speed` / `mp` + **`atk`←`phys_atk`**（引擎未拆物法前）；`magic_*` / 抗性随公式开关决定是否入库。大阵写入守方 `side_mod` 或 `formation` 单位。

### 7.3 预览

`GET /characters/me/combat`（可含 `life`）或嵌入 `/characters/me`：与 settle/开战同一 `build_*`。

---

## 8. 配置与 ADM

### 8.1 建议文件

| 文件 | 用途 |
| --- | --- |
| `config_data/combat_attrs.yaml` | 全量键注册表：`label_zh`、`help_zh`、默认、panel/engine、`entity_uses` |
| `realms.yaml` | `base_hp` / `base_phys_atk`（兼容 `base_atk`）/ `base_speed` / 可选法攻与抗性 |
| `pets.yaml` / 怪物·Boss 表 | base_* + 抗性；校验器对照注册表 |
| 宗门设施/阵法表 | `sect_formation` 模板行与 `formation_*` |

### 8.2 `combat_attrs.yaml` 示意（节选）

```yaml
schema_version: 2
defaults:
  speed: 10
  mp: 0
  phys_atk: 0
  phys_def: 0
  magic_atk: 0
  magic_def: 0
  hit: 0
  dodge: 0
aliases:
  atk: phys_atk
  defense: phys_def
  base_atk: base_phys_atk
attrs:
  hp:
    label_zh: 生命
    help_zh: 棋盘最大生命；归零阵亡；大阵为阵眼耐久
    engine: true
    panel: true
    category: combat_core
  phys_atk:
    label_zh: 物理攻击
    help_zh: 物理普攻/武器威力底
    engine: true
    panel: true
    category: combat_core
  magic_atk:
    label_zh: 法术攻击
    help_zh: 法术/神通威力底（公式未开时仅展示）
    engine: false
    panel: true
    formula_enabled: false
    category: combat_core
  resist_fire:
    label_zh: 火抗
    category: resist
    engine: false
    panel: true
  strength:
    label_zh: 力量
    category: primary
    panel: true
  stamina:
    label_zh: 体力
    help_zh: 行动次数相关资源，非生命
    category: life
    panel: true
  breath_efficiency:
    label_zh: 吐纳效率
    category: life
    panel: true
  craft_dexterity:
    label_zh: 灵巧
    help_zh: 炼器相关
    category: life
    panel: true
  precision:
    label_zh: 精密
    help_zh: 符箓、傀儡相关
    category: life
    panel: true
  temperament:
    label_zh: 心性
    help_zh: 炼丹相关
    category: life
    panel: true
entity_profiles:
  player: { use_categories: [combat_core, resist, primary, life, growth] }
  pet: { use_categories: [combat_core, resist, primary] }
  monster: { use_categories: [combat_core, resist] }
  boss: { use_categories: [combat_core, resist] }
  sect_formation: { use_categories: [combat_core, resist, formation] }
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
  sect_formation:
    enabled: false
    label_zh: 宗门大阵开战修正
```

ADM 域：`combat_attrs`（或并入 `realms` 高危说明）；字段一律 `label_zh`/`help_zh`。

---

## 9. 代码落点（实现时 · 非本轮必码）

| 位置 | 动作 |
| --- | --- |
| `domain/combat.py` | `CombatStats` → `CombatAttrBlock`（+ 别名 `atk`/`defense`） |
| `CharacterService.build_combat_stats` | 升级为 `build_combat_attrs` / `build_life_attrs` |
| `autochess` unit 构建 | 读 final 核心键；`atk`←`phys_atk` |
| 前端 `CharacterPanel` | 分栏：战斗 / 抗性 / 根基 / 生活；可折叠 breakdown |
| 怪/Boss/大阵模板 | 同注册表校验 |
| 单测 | 同源字段；别名；通道关闭；entity_profile 裁剪 |

**实现优先级建议**：不阻塞 M7 社交主线；可作为 **P2 并行小竖切**（先 schema YAML + 面板分栏，不改伤害）。

---

## 10. 与既有系统

| 系统 | 关系 |
| --- | --- |
| M3 引擎 | 继续消费 atk/hp/speed/mp；`atk`=物攻别名；法攻/抗性公式关 |
| M3-D03 | 主动/被动可读写扩展键与 Buff；嘲讽 Phase B 挂靠 |
| 灵宠 | 物种 base_* 对齐；抗性按物种；词条投影进同一 final |
| 宗门 / 大阵 | M7 设施等级 → 开战 `sect_formation` 通道（默关） |
| 挂机 IDLE-R01 | 装备通道打开后吃同一 equipment 源；吐纳效率可读 `breath_efficiency` |
| 骰子 DICE-R01 | 装备/检定修正进 bonus_channels；心魔/天劫抗性参与对应检定 |
| 炼器/符箓/傀儡/炼丹 | 分别读 `craft_dexterity` / `precision` / `temperament` |
| 道值运用 | 战斗临时乘区进战报，不永久改 final（除非配置常驻） |
| 轮回 | 乘区留在步骤 2；成长属性进 `growth` |

---

## 11. 延后与分期

| ID | 本文后状态 | 说明 |
| --- | --- | --- |
| **ATTR-D01** | **已消化** | `combat_attrs.yaml` + `build_combat_attrs` + 面板；契约以本文 **v1.2** 为准 |
| **ATTR-D02** | 待做 · M8 | 打开 equipment/puppet 通道 |
| **ATTR-D03** | 待做 · M9 | 怪物/NPC/Boss 模板满字段 |
| **M13 AO1** | 填正式曲线 | **禁止**改键名而无迁移说明 |

---

## 12. 修订记录

| 日期 | 说明 |
| --- | --- |
| 2026-08-11 | **v1.0**：澄清 M13=填数非设计；锁 CombatAttrBlock、叠层、五类映射、面板 breakdown、ADM 注册表占位 |
| 2026-08-12 | **v1.1**：实体扩至玩家/化身/灵宠/傀儡/NPC/怪/Boss/宗门大阵；战斗键拆物法攻防+命中闪避+七维抗性+力敏智悟根；新增 `LifeAttrBlock`（体力/心魔天劫抗/吐纳/耐力/灵巧/精密/心性）；`atk`/`defense` 别名锁定；适用面矩阵与 `primary_map` |
| 2026-08-12 | **v1.2**：ATTR-D01 代码落地——`combat_attrs.yaml`、ADM 域、`build_combat_attrs`/`LifeAttrBlock`、`CharacterPublic.combat`+`life`、`GET /characters/me/combat`、大厅分栏与 breakdown；单测 `test_combat_attrs` |

---

*冲突时：引擎现行键以代码为准做别名兼容；新键以本文注册表为准。排期见 `开发计划.md` §0.6.2；登记见 `后续待完成.md` ATTR-\*。*
