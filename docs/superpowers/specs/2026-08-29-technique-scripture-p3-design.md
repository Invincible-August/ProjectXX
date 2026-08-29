# 功法自研 P3 · 藏经阁（秘籍上缴与条目学习）

| 项 | 内容 |
| --- | --- |
| **日期** | 2026-08-29 |
| **状态** | **已实现**（2026-08-29）；实现计划见 [`docs/superpowers/plans/2026-08-29-technique-scripture-p3.md`](../plans/2026-08-29-technique-scripture-p3.md) |
| **父规格** | [`2026-08-27-technique-research-design.md`](./2026-08-27-technique-research-design.md) §8.3、§10 P3 |
| **依赖** | P1 创造培养、P2 秘籍印制与学习已落地 |
| **范围** | 自研秘籍上缴宗门藏经阁、审核、永久条目、本门扣贡献学习。不包含 P4 师徒。 |
| **架构选型** | 扩展现有 `SectScriptureEntry` + `SectDonationReview`（方案 1），不新建平行表。 |

---

## 1. 目标与验收

创作者印出的 `tech_manual` 可上缴本宗藏经阁；管理人员审核通过后变成门派永久条目（快照 + 署名），上缴者获得贡献；本门弟子支付贡献后按条目学会定格副本（`source=sect`），不消耗秘籍。YAML 目录兑换与自研条目并存、不互相替换。

**验收路径：** 印书 → 上缴扣书 → 拒绝退同快照书 / 通过入库并发贡献 → 同门扣贡献学会只读副本 → 同 `origin` 再上缴经审核替换快照。

---

## 2. 与现行藏经阁的关系

| 现有（M7） | P3 |
| --- | --- |
| `sects.yaml` `scripture.catalog` + 贡献兑换 | **保留**；兑换仍可只扣贡献并「占位授予」，本期不把目录改成真授予系统功法 |
| `SectScriptureEntry` 仅 `technique_id` / `label` | **扩展**快照与署名字段；自研上缴写入 `source=self_research` |
| `scripture_donate(technique_id, …)` / 前端未接上缴 | **改为**按 `item_uid` 上缴秘籍；前端 `SectScripturePanel` 接上缴 / 学习 / 待审 |
| `POST /sect/donations/{id}/review` 已有；无待审列表 API | **补**待审列表；通过时写条目 + 发贡献；拒绝退书 |

---

## 3. 规则（已确认）

1. **必须经秘籍**：自研功法不能只凭 `technique_id` 入库；须持有 `tech_manual` 上缴。
2. **仅创作者可上缴**：`meta.author_character_id == 当前角色`；须为本门弟子且藏经阁设施闸通过。
3. **提交即扣书**；审核**拒绝**则退回**同快照**一本 `tech_manual`（`add_item` meta 原样）；通过不退书。
4. **通过才发贡献**：数额读 YAML `donate_reward_contrib`；专精匹配另加 `specialty_match_bonus_contrib`（已有键可复用）。
5. **学习扣贡献**：数额为条目上的 `cost_contribution`（写入时用 YAML `learn_cost_contrib` 默认）。
6. **同 origin 替换**：已有同 `origin_technique_id` 的条目时仍可再缴（新快照）；再审通过后**覆盖**旧条目。已有同 origin 的**待审单**则拒绝新提交。
7. **学会规则**（对齐 P2）：境界 ≥ 条目 `major_rank`；原值不打折；新 `PrivateTechnique` + `CharacterTechnique(source=sect)`；不可培养、不可再印秘籍；已有同 origin 已学 → 拒绝且不扣贡献。
8. **目录兑换**：与自研并存；本期行为不变（占位）。

---

## 4. 数据

### 4.1 `SectScriptureEntry` 扩展

| 字段 | 说明 |
| --- | --- |
| `origin_technique_id` | 原创功法 id；替换键（可空：旧目录行） |
| `author_character_id` | 创作者（可空：目录） |
| `major_rank` | 快照功法阶 |
| `payload_json` / `stats_json` / `affix_ids_json` | 定格快照（与秘籍 meta 同形子集） |
| `cost_contribution` | 学习学费 |
| `source` | `catalog` / `donated` / `self_research` |
| 已有 | `sect_id`, `technique_id`, `label_zh`, `specialty_tag` |

唯一约束：保留 `(sect_id, technique_id)`。自研行约定 **`technique_id = origin_technique_id`**，从而一宗一门原创至多一行；替换 = 更新该行快照与学费字段。目录行 `technique_id` 仍为 YAML catalog id（与自研 origin 命名空间不冲突：自研 id 形如 `custom:technique:…`）。

### 4.2 审核单

`SectDonationReview.kind=scripture` 的 `payload_json` 至少含：完整秘籍快照、`origin_technique_id`、`label_zh`、`major_rank`、`author_character_id`、可选 `specialty_tag`。提交时已扣书，payload 须足以拒绝时重发。

---

## 5. API

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/sect/scripture` | 目录 + `entries`（署名、阶、学费、是否已学）+ 贡献 |
| GET | `/sect/donations` | 本宗 `pending` 审核单（仅管理职；他人 403） |
| POST | `/sect/scripture/donate` | body `{ item_uid }`；校验创作者与秘籍 → 扣书 → pending |
| POST | `/sect/donations/{id}/review` | `{ approve }`；通过入库/替换+发贡献；拒绝退书 |
| POST | `/sect/scripture/exchange` | 自研有快照：扣学费 → 真学会；目录：保持占位 |

错误码：优先复用现有宗门/功法码；缺则在计划中分配 `4022x` 段邻近码，文案中文。

---

## 6. 配置（`sects.yaml` → `scripture`）

```yaml
scripture:
  donate_reward_contrib: 40
  specialty_match_bonus_contrib: 30   # 已有
  learn_cost_contrib: 60
  catalog: { ... }                    # 不变
```

禁止把奖励/学费写死在 `if` 分支。

---

## 7. 前端

`SectScripturePanel`：

- 展示目录占位与已收录自研条目（署名、阶、学费、已学标记）。
- 上缴：列出自己持有且自己为创作者的 `tech_manual`，提交 `item_uid`。
- 学习：对有快照条目点学习/兑换。
- 审核：管理职待审列表，通过/拒绝。

研究室印书入口不改（P2）。

---

## 8. 明确不做（本期）

- YAML 目录真授予系统功法
- 每日学习次数、贡献以外货币
- 非创作者代缴
- P4 师徒传授
- 条目指针制（指向创作者当前 PrivateTechnique）— 必须定格快照

---

## 9. 修订

| 日期 | 说明 |
| --- | --- |
| 2026-08-29 | 初稿：问答确认流程、贡献学费、扣书/退书、仅创作者、同 origin 替换、方案 1 |
