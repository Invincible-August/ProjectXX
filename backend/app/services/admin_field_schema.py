"""
运营后台「字段中文说明 + 双写模式」契约（强制）。

规则（与开发计划 §0.0 / 后台计划同步）：
1. 每个可编辑字段必须有 ``label_zh`` / ``help_zh``；
2. 每个内容域须同时支持 **表格** 与 **JSON** 两种写入（运营非编码 / 编码人员）；
3. 表格写入由后端 format 成域 JSON，再进入草稿 → 校验 → 发布管线。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldMeta:
    """单个配置字段的运维说明。"""

    key: str
    label_zh: str
    help_zh: str
    value_type: str = "string"  # string | int | float | bool | json | null_str

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 字典。"""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SheetMeta:
    """一张运营表格（可对应嵌套 JSON 的某一段）。"""

    sheet_id: str
    title_zh: str
    description_zh: str
    columns: tuple[FieldMeta, ...]
    primary_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 字典。"""
        return {
            "sheet_id": self.sheet_id,
            "title_zh": self.title_zh,
            "description_zh": self.description_zh,
            "columns": [col.to_dict() for col in self.columns],
            "primary_keys": list(self.primary_keys),
        }


@dataclass(frozen=True, slots=True)
class DomainEditSchema:
    """域级编辑契约：双写模式 + 字段说明 + 表格定义。"""

    domain_id: str
    title_zh: str
    description_zh: str
    edit_modes: tuple[str, ...]  # table | json | entries
    fields: tuple[FieldMeta, ...]
    sheets: tuple[SheetMeta, ...] = ()
    entry_path: tuple[str, ...] | None = None
    entry_fields: tuple[FieldMeta, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 字典。"""
        return {
            "domain_id": self.domain_id,
            "title_zh": self.title_zh,
            "description_zh": self.description_zh,
            "edit_modes": list(self.edit_modes),
            "fields": [field.to_dict() for field in self.fields],
            "sheets": [sheet.to_dict() for sheet in self.sheets],
            "entry_path": list(self.entry_path) if self.entry_path else None,
            "entry_fields": [field.to_dict() for field in self.entry_fields],
            "dual_write_rule": (
                "须同时提供表格与 JSON；表格由后端 format 为域 JSON；"
                "每个字段须有中文 label/help，方便非编码运营人员。"
            ),
        }


def _f(
    key: str,
    label_zh: str,
    help_zh: str,
    value_type: str = "string",
) -> FieldMeta:
    """缩短 FieldMeta 构造。"""
    return FieldMeta(key=key, label_zh=label_zh, help_zh=help_zh, value_type=value_type)


# ---------------------------------------------------------------------------
# realms / idle / dice（嵌套矩阵：专用表格）
# ---------------------------------------------------------------------------

REALMS_SCHEMA = DomainEditSchema(
    domain_id="realms",
    title_zh="境界",
    description_zh="大境界链、小层/阶段；炼体大境（层/期）与淬体规则。高危域，发布须二次确认。",
    edit_modes=("table", "json"),
    fields=(
        _f("major_realms", "大境界表", "键=大境界 id，值含 name/stage_mode/next_major/stages", "json"),
        _f(
            "body_temper_unlock_majors",
            "炼体对照主修序",
            "锻体→大乘（可含未开放主修，扩境预留）",
            "json",
        ),
        _f(
            "body_temper_majors",
            "炼体大境表",
            "炼皮→道体；含 stage_mode/unlock_major/next_major/stages",
            "json",
        ),
        _f(
            "body_temper_quench",
            "淬体规则",
            "layer_advance/major_advance 成功率与失败保留比；无渡劫",
            "json",
        ),
    ),
    sheets=(
        SheetMeta(
            sheet_id="majors",
            title_zh="大境界",
            description_zh="每行一个大境界；小层请在「小层/阶段」表编辑。",
            primary_keys=("id",),
            columns=(
                _f("id", "大境界 ID", "英文键，如 body_tempering；发布后勿随意改名", "string"),
                _f("name", "展示名", "玩家可见境界名，如「锻体」", "string"),
                _f(
                    "stage_mode",
                    "阶段模式",
                    "layers=1～9层+圆满；phases=早中晚+圆满",
                    "string",
                ),
                _f(
                    "next_major",
                    "下一大境 ID",
                    "链上下一境；终点填空（null）",
                    "null_str",
                ),
            ),
        ),
        SheetMeta(
            sheet_id="stages",
            title_zh="小层 / 阶段",
            description_zh="每行=某大境界下的一层；后端会按 major_id 组装进 stages 列表。",
            primary_keys=("major_id", "stage"),
            columns=(
                _f("major_id", "大境界 ID", "必须对应「大境界」表中的 id", "string"),
                _f("stage", "层编号", "整数；layers 通常 1～10，phases 通常 1～4", "int"),
                _f("label", "层标签", "如 layer_1 / early / perfection", "string"),
                _f(
                    "cultivation_required",
                    "修为门槛",
                    "升到本层所需累计修为（占位可调）",
                    "int",
                ),
                _f("base_atk", "基础攻击", "战力面板占位 atk", "int"),
                _f("base_hp", "基础生命", "战力面板占位 hp", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="body_temper_order",
            title_zh="炼体对照主修序",
            description_zh="从上到下=锻体→大乘；可追加未开放主修作扩境预留。",
            primary_keys=("order",),
            columns=(
                _f("order", "序", "从 1 起", "int"),
                _f("major_id", "主修大境界 ID", "如 body_tempering / dacheng", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="body_temper_majors",
            title_zh="炼体大境",
            description_zh="炼皮→道体；小层见「炼体层/期」表；末境 next_major 空=当前链终点。",
            primary_keys=("id",),
            columns=(
                _f("id", "炼体境 ID", "英文键，如 refine_skin", "string"),
                _f("name", "展示名", "如「炼皮」", "string"),
                _f("stage_mode", "阶段模式", "layers 或 phases", "string"),
                _f("unlock_major", "对照主修", "须在对照主修序中", "string"),
                _f("next_major", "下一炼体境", "扩境口；终点空", "null_str"),
            ),
        ),
        SheetMeta(
            sheet_id="body_temper_layers",
            title_zh="炼体层 / 期",
            description_zh="前两境 1～10 层；其后初中后圆满。",
            primary_keys=("major_id", "stage"),
            columns=(
                _f("major_id", "炼体境 ID", "对应炼体大境 id", "string"),
                _f("stage", "层编号", "layers 1～10；phases 1～4", "int"),
                _f("label", "层标签", "layer_N / early / middle / late / perfection", "string"),
                _f("progress_required", "淬体进度门槛", "当前档满方可淬体", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="body_temper_quench",
            title_zh="淬体规则",
            description_zh="层进阶 / 跨境成功率与失败保留比（无渡劫）。",
            primary_keys=("rule_id",),
            columns=(
                _f("rule_id", "规则", "layer_advance / major_advance / clamp", "string"),
                _f("success_rate", "成功率", "clamp 行可空", "float"),
                _f("fail_progress_keep_ratio", "失败保留比", "clamp 行可空", "float"),
                _f("clamp_min", "成功率下限", "仅 clamp 行", "float"),
                _f("clamp_max", "成功率上限", "仅 clamp 行", "float"),
            ),
        ),
    ),
)

IDLE_SCHEMA = DomainEditSchema(
    domain_id="idle",
    title_zh="挂机速率",
    description_zh="三向挂机 tick、境界基础产出、加成通道与灵石消耗。高危域。",
    edit_modes=("table", "json"),
    fields=(
        _f("tick_seconds", "Tick 秒数", "每次挂机结算墙钟秒；可被环境变量覆盖", "int"),
        _f("clamp_min", "加成下限", "bonus_channels 乘积下限", "float"),
        _f("clamp_max", "加成上限", "bonus_channels 乘积上限", "float"),
        _f("spirit_stone_cost_by_realm", "灵石消耗表", "大境界→每 tick 灵石", "json"),
        _f("directions", "三向定义", "spirit/body/crafting 开关与回落速率", "json"),
        _f("gain_per_tick_by_realm", "境界基础产出", "方向×大境界→每 tick 产出", "json"),
        _f("bonus_channels", "加成通道", "各通道 enabled/default_mult", "json"),
    ),
    sheets=(
        SheetMeta(
            sheet_id="globals",
            title_zh="全局标量",
            description_zh="tick 与加成钳制；一行一个键。",
            primary_keys=("key",),
            columns=(
                _f("key", "键名", "tick_seconds / clamp_min / clamp_max", "string"),
                _f("label_zh", "中文名", "只读说明列，保存时忽略", "string"),
                _f("value", "数值", "对应键的取值", "float"),
                _f("help_zh", "说明", "只读说明列，保存时忽略", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="spirit_stone_cost",
            title_zh="灵石消耗（按境界）",
            description_zh="筑基前可为 0；0=不因灵石卡 tick。",
            primary_keys=("major_realm",),
            columns=(
                _f("major_realm", "大境界 ID", "如 foundation", "string"),
                _f("cost", "每 tick 灵石", "整数消耗", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="directions",
            title_zh="挂机三向",
            description_zh="互斥方向；未在境界产出表列出时回落本表 per_tick。",
            primary_keys=("direction",),
            columns=(
                _f("direction", "方向 ID", "spirit / body / crafting", "string"),
                _f("enabled", "是否开放", "关闭后玩家不可选该向", "bool"),
                _f(
                    "rate_key",
                    "回落字段名",
                    "写入 YAML 的 *_per_tick 键名",
                    "string",
                ),
                _f("rate_value", "回落每 tick", "未命中境界表时的基础产出", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="gain_per_tick",
            title_zh="境界基础产出",
            description_zh="核心挂机速率表：方向 × 大境界 → 每 tick 产出。",
            primary_keys=("direction", "major_realm"),
            columns=(
                _f("direction", "方向", "spirit / body / crafting", "string"),
                _f("major_realm", "大境界 ID", "如 qi_refining", "string"),
                _f("gain", "每 tick 产出", "整数基础速率（再乘通道与环境）", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="bonus_channels",
            title_zh="加成通道",
            description_zh="内部/外部乘区；未启用则视为 1.0。",
            primary_keys=("channel",),
            columns=(
                _f("channel", "通道 ID", "如 constitution_idle", "string"),
                _f("enabled", "是否启用", "false 时不参与乘积", "bool"),
                _f("default_mult", "默认倍率", "无实例修正时的倍率", "float"),
            ),
        ),
    ),
)

DICE_SCHEMA = DomainEditSchema(
    domain_id="dice",
    title_zh="修为骰",
    description_zh="修为检定上下限、气运分档、体修加成与通道开关。高危域。",
    edit_modes=("table", "json"),
    fields=(
        _f("fallback_bounds", "回落上下限", "无境界上下文时使用", "json"),
        _f("monster_default", "怪物默认区间", "PVE 防守侧默认", "json"),
        _f("clamp", "全局钳制", "absolute_min / absolute_max", "json"),
        _f("breakthrough", "突破选项", "是否沿用 breakthrough 成功率表", "json"),
        _f("combat", "战斗选项", "是否用中点正态化伤害", "json"),
        _f("purposes", "用途清单", "文档/校验用字符串列表", "json"),
        _f("bonus_channels", "修正通道", "technique/body_track/…", "json"),
        _f("fate_luck_tiers", "气运分档", "列表：luck 区间 → bonus", "json"),
        _f("body_realm_bonus", "体修境界加成", "大境×小境 → min/max_bonus", "json"),
        _f("realm_bounds", "境界默认上下限", "权威检定表；调数值优先改这里", "json"),
    ),
    sheets=(
        SheetMeta(
            sheet_id="scalar_groups",
            title_zh="区间与开关标量",
            description_zh="fallback/monster/clamp/breakthrough/combat 扁平行。",
            primary_keys=("group", "field"),
            columns=(
                _f("group", "分组", "fallback_bounds / monster_default / clamp / …", "string"),
                _f("field", "字段", "如 min、absolute_max、use_legacy_success_rate", "string"),
                _f("label_zh", "中文名", "只读说明，保存忽略", "string"),
                _f("value", "取值", "数字或 true/false", "string"),
                _f("help_zh", "说明", "只读说明，保存忽略", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="realm_bounds",
            title_zh="境界默认上下限",
            description_zh="权威表：大境锁 max 波段，小境抬 min。",
            primary_keys=("major_realm", "stage"),
            columns=(
                _f("major_realm", "大境界 ID", "如 body_tempering", "string"),
                _f("stage", "小境界编号", "整数层号", "int"),
                _f("min", "下限", "检定骰最小值", "int"),
                _f("max", "上限", "检定骰最大值", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="body_realm_bonus",
            title_zh="体修境界加成",
            description_zh="体修道相关检定额外加减（可全 0）。",
            primary_keys=("major_realm", "stage"),
            columns=(
                _f("major_realm", "大境界 ID", "通常为 body_tempering 等", "string"),
                _f("stage", "小境界编号", "整数层号", "int"),
                _f("min_bonus", "下限加成", "加到骰子 min", "int"),
                _f("max_bonus", "上限加成", "加到骰子 max", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="fate_luck_tiers",
            title_zh="气运分档",
            description_zh="角色 fate_luck 落入区间时的 min/max_bonus。",
            primary_keys=("row_index",),
            columns=(
                _f("row_index", "行号", "从 0 起；决定列表顺序", "int"),
                _f("min_luck", "气运下限", "含", "int"),
                _f("max_luck", "气运上限", "含", "int"),
                _f("min_bonus", "下限加成", "整数", "int"),
                _f("max_bonus", "上限加成", "整数", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="bonus_channels",
            title_zh="修正通道开关",
            description_zh="无实例则修正为 0；关闭通道即不生效。",
            primary_keys=("channel",),
            columns=(
                _f("channel", "通道 ID", "technique / body_track / fate_luck 等", "string"),
                _f("enabled", "是否启用", "布尔", "bool"),
            ),
        ),
        SheetMeta(
            sheet_id="purposes",
            title_zh="用途清单",
            description_zh="文档与校验用；一行一个用途 id。",
            primary_keys=("purpose",),
            columns=(
                _f("purpose", "用途 ID", "如 breakthrough / combat_damage", "string"),
            ),
        ),
    ),
)


BREAKTHROUGH_SCHEMA = DomainEditSchema(
    domain_id="breakthrough",
    title_zh="突破",
    description_zh="层/跨境成功率、灵石、失败惩罚与异步真读条时长。高危域。",
    edit_modes=("table", "json"),
    fields=(
        _f("layer_advance", "层进阶规则", "同境内层/期成功率与代价", "json"),
        _f("major_advance", "跨境规则", "跨大境界成功率与代价", "json"),
        _f(
            "pre_foundation_free",
            "筑基前突破免费",
            "true=锻体/炼气突破不扣石；仅炼气→筑基扣 major 费用",
            "bool",
        ),
        _f("success_rate_clamp", "成功率钳制", "min/max，含轮回加成后", "json"),
        _f("async_channel", "异步真读条（可选·默认关）", "开关、时长、中文提示；默认同步出结果", "json"),
    ),
    sheets=(
        SheetMeta(
            sheet_id="rules",
            title_zh="进阶规则",
            description_zh="layer_advance / major_advance 各一行。",
            primary_keys=("rule_id",),
            columns=(
                _f("rule_id", "规则 ID", "layer_advance 或 major_advance", "string"),
                _f("success_rate", "成功率", "0～1", "float"),
                _f("spirit_stone_cost", "灵石消耗", "每次尝试", "int"),
                _f("fail_cultivation_keep_ratio", "失败保留修为比", "0～1", "float"),
                _f("fail_still_charge_stones", "失败仍扣灵石", "布尔", "bool"),
            ),
        ),
        SheetMeta(
            sheet_id="clamp",
            title_zh="成功率钳制",
            description_zh="一行一个键。",
            primary_keys=("key",),
            columns=(
                _f("key", "键名", "min / max", "string"),
                _f("label_zh", "中文名", "只读说明，保存忽略", "string"),
                _f("value", "数值", "0～1", "float"),
                _f("help_zh", "说明", "只读说明，保存忽略", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="async_channel",
            title_zh="异步真读条",
            description_zh="闭关占用时长与开关；一行一个键。",
            primary_keys=("key",),
            columns=(
                _f(
                    "key",
                    "键名",
                    "enabled / label_zh / hint_zh / client_poll_ms / "
                    "duration_seconds.layer_advance / duration_seconds.major_advance",
                    "string",
                ),
                _f("label_zh", "中文名", "只读说明，保存忽略", "string"),
                _f("value", "取值", "布尔/字符串/整数", "string"),
                _f("help_zh", "说明", "只读说明，保存忽略", "string"),
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# 扁平条目域：条目字段中文说明（表格=条目表，JSON=覆盖层）
# ---------------------------------------------------------------------------

_ENTRY_COMMON_NAME = _f("name", "名称", "玩家可见展示名", "string")

PETS_SCHEMA = DomainEditSchema(
    domain_id="pets",
    title_zh="灵宠",
    description_zh="物种/种族/品阶注册表；可用条目表或 JSON 覆盖。加物种后玩家图鉴自动同步。",
    edit_modes=("entries", "json"),
    fields=(
        _f("hold_cap", "持有上限", "同时可持有灵宠数", "int"),
        _f("level_stat_bonus", "每级加成", "相对基础面板比例", "float"),
        _f("races", "种族表", "race_id→定义", "json"),
        _f("grades", "品阶表", "grade→槽位与乘区", "json"),
        _f("species", "物种表", "id→物种定义", "json"),
        _f("capture_test_weights", "测试捕获稀有度权重", "rarity→权重", "json"),
        _f("capture_test_grade_weights", "测试捕获品阶权重", "grade→权重", "json"),
        _f("grade_up", "升阶费用", "spirit_stones_base/grow/max_grade", "json"),
        _f("sect_reroll", "灵兽宗改类型费用", "enabled/base_1/grow；玩法闸读 sects", "json"),
    ),
    entry_path=("species",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("race", "种族 ID", "须存在于 races 表", "string"),
        _f("rarity", "稀有度", "common/rare/epic/legendary", "string"),
        _f("roles", "定位", "dps/tank/control/support 列表", "json"),
        _f("acquire_tags", "获取途径白名单", "如 capture_test/gm_grant", "json"),
        _f("skill_pool_id", "技能池 ID", "对战技能池占位", "string"),
        _f("passive_pool_id", "被动池 ID", "独立被动抽取；可空", "string"),
        _f("base_hp", "基础生命", "品阶 1 时基础 HP", "int"),
        _f("base_atk", "基础攻击", "品阶 1 时基础攻击", "int"),
        _f("base_speed", "基础速度", "比速/先攻相关", "int"),
        _f("growth", "成长系数", "atk/hp/speed", "json"),
        _f("upgrade_cost", "升级消耗", "灵石/材料对象", "json"),
        _f("divine_sense_cost", "神识占用覆盖", "空则用默认宠占用", "int"),
    ),
)

PET_AFFIXES_SCHEMA = DomainEditSchema(
    domain_id="pet_affixes",
    title_zh="灵宠词条",
    description_zh="词条类型库与数值洗炼费用；与体质词条分表。加类型只改本域。",
    edit_modes=("entries", "json"),
    fields=(
        _f("types", "词条类型表", "affix_type_id→定义", "json"),
        _f("type_weights", "类型抽取权重", "type_id→权重", "json"),
        _f("tier_weights", "品级抽取权重", "tier→权重", "json"),
        _f("value_reroll", "数值洗炼费用", "spirit_stones_base/grow", "json"),
    ),
    entry_path=("types",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("kind", "效果种类", "flat_atk/pct_hp/passive_ref 等", "string"),
        _f("tier_ranges", "品级数值区间", "tier→{min,max}", "json"),
        _f("passive_id", "被动引用", "kind=passive_ref 时必填", "string"),
    ),
)

PET_SKILLS_SCHEMA = DomainEditSchema(
    domain_id="pet_skills",
    title_zh="灵宠技能",
    description_zh="主动技能与物种技能池；装备栏最多 4。加技能只改本域。",
    edit_modes=("entries", "json"),
    fields=(
        _f("equip_slots", "装备栏位数", "固定 1～4", "int"),
        _f("skills", "技能表", "skill_id→定义", "json"),
        _f("pools", "技能池表", "pool_id→技能列表", "json"),
    ),
    entry_path=("skills",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("power", "威力", "整数；状态技可为 0", "int"),
        _f("accuracy", "命中", "0～100", "int"),
        _f("category", "类别", "physical/special/status", "string"),
        _f("priority", "先制档", "整数", "int"),
        _f("pp", "使用次数", "PP 占位", "int"),
        _f("mutex_tags", "互斥标签", "字符串列表", "json"),
    ),
)

PET_SKILL_BOOKS_SCHEMA = DomainEditSchema(
    domain_id="pet_skill_books",
    title_zh="灵宠技能书",
    description_zh="技能书与 scope 约束。",
    edit_modes=("entries", "json"),
    fields=(_f("books", "技能书表", "book_id→定义", "json"),),
    entry_path=("books",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("skill_id", "技能 ID", "须存在于 pet_skills.skills", "string"),
        _f("scope", "适用范围", "universal/race/species", "string"),
        _f("race_id", "种族 ID", "scope=race 时必填", "string"),
        _f("species_id", "物种 ID", "scope=species 时必填", "string"),
    ),
)

PET_DUEL_SCHEMA = DomainEditSchema(
    domain_id="pet_duel",
    title_zh="灵宠对战",
    description_zh="回合制对战规则与 NPC；禁止依赖自走棋 board。",
    edit_modes=("entries", "json"),
    fields=(
        _f("max_rounds", "最大回合", "超时按剩余 HP 判胜", "int"),
        _f("damage_divisor", "伤害分母", "atk*power/divisor", "float"),
        _f("damage_roll_min", "伤害随机下限", "如 0.85", "float"),
        _f("damage_roll_max", "伤害随机上限", "如 1.0", "float"),
        _f("accuracy_enabled", "启用命中检定", "bool", "bool"),
        _f("speed_tie_break", "同速决胜", "seed_parity 等", "string"),
        _f("default_struggle", "默认挣扎", "无技能时指令", "json"),
        _f("npc_templates", "NPC 模板", "npc_id→定义", "json"),
    ),
    entry_path=("npc_templates",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("species_id", "物种 ID", "须存在于 pets.species", "string"),
        _f("grade", "品阶", "整数", "int"),
        _f("level", "等级", "整数", "int"),
        _f("skill_ids", "技能列表", "须存在于 pet_skills", "json"),
    ),
)

PET_EGGS_SCHEMA = DomainEditSchema(
    domain_id="pet_eggs",
    title_zh="灵兽蛋",
    description_zh="孵化蛋表；egg_id 须与道具 catalog 对齐；物种须含 egg_hatch。",
    edit_modes=("entries", "json"),
    fields=(
        _f("max_concurrent", "并发孵化上限", "0=不限", "int"),
        _f("eggs", "蛋表", "egg_id→定义", "json"),
    ),
    entry_path=("eggs",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("species_id", "物种 ID", "须存在于 pets 且 acquire_tags 含 egg_hatch", "string"),
        _f("hatch_seconds", "孵化秒数", "0=可立刻领取", "int"),
        _f("spirit_stones", "开工灵石", "开工额外扣费", "int"),
        _f("grade_weights", "品阶权重", "grade→权重；空则用 capture_test", "json"),
    ),
)

PET_PASSIVES_SCHEMA = DomainEditSchema(
    domain_id="pet_passives",
    title_zh="灵宠被动",
    description_zh="种族天赋与独立被动；combat 进面板，life/cultivation 仅展示。",
    edit_modes=("entries", "json"),
    fields=(
        _f("passives", "被动表", "passive_id→定义", "json"),
        _f("pools", "被动池", "pool_id→权重/空权", "json"),
    ),
    entry_path=("passives",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("kind", "种类", "racial_talent/independent", "string"),
        _f("effect_domain", "效果域", "combat/life/cultivation", "string"),
        _f("effects", "数值效果", "flat_atk/pct_hp 等", "json"),
        _f("summary", "摘要", "玩家可见说明", "string"),
    ),
)

PET_FEED_SCHEMA = DomainEditSchema(
    domain_id="pet_feed",
    title_zh="灵宠喂养",
    description_zh="兽丹效果与单药/总量上限；item_id 须存在于道具表。",
    edit_modes=("entries", "json"),
    fields=(
        _f("total_feed_cap", "默认总量上限", "0=不限总量", "int"),
        _f("total_feed_cap_by_grade", "品阶总量上限", "grade→上限", "json"),
        _f("total_feed_cap_by_species", "物种总量上限", "species_id→上限", "json"),
        _f("items", "兽丹表", "item_id→定义", "json"),
    ),
    entry_path=("items",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("per_item_cap", "单药上限", "该丹最多喂几次；0=不限", "int"),
        _f("effects", "单次效果", "flat_atk/pct_hp 等", "json"),
        _f("summary", "摘要", "玩家可见说明", "string"),
    ),
)

PET_ENCOUNTER_SCHEMA = DomainEditSchema(
    domain_id="pet_encounter",
    title_zh="灵宠遭遇",
    description_zh="区域×时辰×天气遭遇表；可捕类型须含 wild_capture 物种。",
    edit_modes=("json",),
    fields=(
        _f("capturable_types", "可捕类型", "如 spirit_beast", "json"),
        _f("skip_battle", "跳过战斗", "占位区直接可捕", "bool"),
        _f("tables", "遭遇表", "region×shichen×weather 列表", "json"),
    ),
)

PET_CAPTURE_SCHEMA = DomainEditSchema(
    domain_id="pet_capture",
    title_zh="灵宠捕获",
    description_zh="捕获成功率因子、诱灵草/灵兽袋与自动捕开关。",
    edit_modes=("json",),
    fields=(
        _f("lure_item_id", "诱灵草道具", "inventory item_id", "string"),
        _f("bag_item_id", "灵兽袋道具", "inventory item_id", "string"),
        _f("require_bag", "必须持袋", "无袋拒绝捕获", "bool"),
        _f("daily_attempt_cap", "日尝试上限", "0=不限", "int"),
        _f("special_affix_min_tier", "特殊词条门槛", "默认 rare", "string"),
        _f("pen_affix", "词条惩罚", "每条减成", "float"),
        _f("pen_grade", "品阶惩罚", "grade→减成", "json"),
        _f("realm_diff", "修为差", "per_stage/clamp", "json"),
        _f("root_affinity", "灵根亲和", "tag→race→加成", "json"),
        _f("taming_tech_bonus", "御兽功法加成", "technique→加成", "json"),
        _f("species_capture_override", "物种捕获率覆盖", "species→p", "json"),
        _f("auto_capture", "自动捕", "enabled/max_rolls", "json"),
        _f("estimate_special_affixes", "估计特殊词条", "遭遇时抽样", "bool"),
    ),
)

ITEMS_SCHEMA = DomainEditSchema(
    domain_id="items",
    title_zh="道具",
    description_zh="道具注册表。",
    edit_modes=("entries", "json"),
    fields=(_f("items", "道具表", "id→道具定义", "json"),),
    entry_path=("items",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("kind", "类型", "道具分类键", "string"),
        _f("stackable", "可堆叠", "是否可堆叠", "bool"),
        _f("max_stack", "堆叠上限", "整数", "int"),
        _f("description", "说明", "运营/玩家说明", "string"),
    ),
)

TECHNIQUES_SCHEMA = DomainEditSchema(
    domain_id="techniques",
    title_zh="功法",
    description_zh="功法注册表。",
    edit_modes=("entries", "json"),
    fields=(_f("techniques", "功法表", "id→功法定义", "json"),),
    entry_path=("techniques",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("track", "轨道", "spirit / body / crafting 等", "string"),
        _f("dice_mods", "骰子修正", "挂接修为骰通道", "json"),
        _f("effects", "效果", "挂机/战斗效果对象", "json"),
    ),
)

MONSTERS_SCHEMA = DomainEditSchema(
    domain_id="monsters",
    title_zh="怪物",
    description_zh="PVE 怪物表。",
    edit_modes=("entries", "json"),
    fields=(_f("monsters", "怪物表", "id→怪物定义", "json"),),
    entry_path=("monsters",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("hp", "生命", "整数", "int"),
        _f("atk", "攻击", "整数", "int"),
        _f("realm_hint", "境界提示", "展示用境界描述", "string"),
    ),
)

FORMATIONS_SCHEMA = DomainEditSchema(
    domain_id="formations",
    title_zh="阵法",
    description_zh="阵法表：四象 + 部署契约 + 强制移位 + 环境/天气/效果目录（M3-D07）。",
    edit_modes=("entries", "json"),
    fields=(
        _f("formations", "阵法表", "id→阵法定义", "json"),
        _f("environment_catalog", "环境目录", "id→label_zh/combat", "json"),
        _f("weather_catalog", "天气目录", "阵法天气层目录（≠世界天气）", "json"),
        _f("effect_catalog", "效果目录", "id→label_zh", "json"),
        _f("environment_counters", "环境克制表", "对抗系数", "json"),
        _f("weather_counters", "天气克制表", "对抗系数", "json"),
        _f("effect_counters", "效果克制表", "对抗系数", "json"),
    ),
    entry_path=("formations",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("level", "等级", "阵法等级", "int"),
        _f("unlocked_by_default", "默认解锁", "创角是否已解锁", "bool"),
        _f("required_array_level", "所需阵法钻研", "整数门槛", "int"),
        _f("deploy", "部署契约", "mode/cells/max_units JSON", "json"),
        _f("terrain_layout", "地形布局", "none/fixed/brush JSON", "json"),
        _f("terrain", "地形列表", "障碍/深渊/禁制等", "json"),
        _f("force_shifts", "强制移位", "from/to 列表", "json"),
        _f("environment", "环境层", "可为 null", "json"),
        _f("weather", "天气层", "可为 null", "json"),
        _f("effect", "效果层", "可为 null", "json"),
    ),
)

SECTS_SCHEMA = DomainEditSchema(
    domain_id="sects",
    title_zh="宗门与设施",
    description_zh="设施开关 + 等级/职位/专精/十设施（M7-V+）。表格改设施闸；完整玩法表可用 JSON。",
    edit_modes=("entries", "json"),
    fields=(
        _f("facilities", "设施表", "id→设施定义（enabled/note）", "json"),
        _f("create_cost_spirit_stones", "建宗灵石", "自建宗门费用（有钱即可）", "int"),
        _f("idle_bonus_vs_wanderer", "入宗挂机乘区", "相对散修的占位乘区（显性）", "float"),
        _f(
            "contribution_zero_on_reincarnation",
            "轮回归零贡献",
            "入轮回时是否清本宗贡献",
            "bool",
        ),
        _f("max_announcement_len", "公告字数上限", "议事厅公告", "int"),
        _f(
            "promotion_auto_approve_after_game_days",
            "自申自动通过游戏日",
            "贡献/自荐申请隔几游戏日自动通过",
            "int",
        ),
        _f("facility_upgrade_cost_base", "设施升级基础贡献", "升到 2 级起算", "int"),
        _f("facility_upgrade_cost_per_level", "设施升级贡献递增", "每级额外贡献", "int"),
        _f("grade_upgrade_spirit_stones_base", "升宗门等级基础灵石", "扣宗门库", "int"),
        _f("sect_grades", "宗门等级表", "草庐→道庭：人数/设施门槛/buff", "json"),
        _f("disciple_ranks", "弟子职位表", "杂役→创派：任命/贡献/藏宝阁页", "json"),
        _f("specialties", "专精表", "建宗必选；藏经阁匹配", "json"),
        _f("facility_defs", "玩法设施定义", "任务殿等十设施", "json"),
        _f("sect_buffs", "宗门增益", "可开启 buff 与费用", "json"),
        _f("treasury", "藏宝阁规则", "禁止类型/目录/页数", "json"),
        _f("scripture", "藏经阁规则", "功法目录与专精加成", "json"),
        _f("craftsmen", "工匠表", "代工分支/品阶/贡献费", "json"),
        _f("workshop_blueprints", "工坊图纸目录", "branch→在售 recipe", "json"),
        _f("formations", "宗门阵法表", "兑换/启停/加点费用", "json"),
        _f("formation_attr_keys", "阵法属性键", "攻击/防御/抗性等中文", "json"),
        _f("mine_yield", "矿脉产出", "被动入库+采矿名额/体力", "json"),
        _f("herb_garden", "灵药园", "兑换/托管种植/灵植师", "json"),
        _f("npc_sects", "NPC 宗门表", "template_id→拜入条件与中文名", "json"),
        _f("features_by_founder_realm", "祖师境界功能", "大境界→功能键列表", "json"),
        _f("sect_exchange", "兑宠规则", "白名单物种与贡献费用", "json"),
        _f("shop_items", "贡献商店", "条目→费用与奖励", "json"),
        _f("quests", "宗门任务", "任务→接取方与贡献奖励", "json"),
        _f("sects", "旧模板占位", "兼容设施预览", "json"),
    ),
    entry_path=("facilities",),
    entry_fields=(
        _f("enabled", "是否开放", "玩家 facilities / 宗门大厅读取", "bool"),
        _f("note", "备注", "玩家可见说明（§0.7）", "string"),
    ),
)

FRIENDS_SCHEMA = DomainEditSchema(
    domain_id="friends",
    title_zh="道友",
    description_zh="道友/道侣/炉鼎上限与面交炉鼎时长（M7 L2）。",
    edit_modes=("json",),
    fields=(
        _f("max_friends", "道友上限", "每角色最多活跃道友数", "int"),
        _f("max_companions", "道侣上限", "", "int"),
        _f("max_vessels", "炉鼎上限", "主人侧可拥有炉鼎数", "int"),
        _f("vessel_min_hours", "炉鼎最短小时", "面交要约下限（现实小时）", "int"),
        _f("vessel_max_hours", "炉鼎最长小时", "面交要约上限（现实小时）", "int"),
        _f("request_expire_sec", "申请过期秒", "0=不过期", "int"),
        _f("keep_on_reincarnation", "轮回保留", "轮回是否保留道友关系", "bool"),
        _f("include_online_stub", "在线摘要(旧)", "兼容旧键", "bool"),
        _f("include_online", "在线摘要", "列表是否附带 WS 在线", "bool"),
        _f("dev_assume_online", "DEV假定在线", "仅 development", "bool"),
    ),
)

TRADE_SCHEMA = DomainEditSchema(
    domain_id="trade",
    title_zh="交易行与拍卖 / 坊市",
    description_zh="手续费、拍卖时长、面交超时、NPC 坊市货架（M7 L2）。",
    edit_modes=("json",),
    fields=(
        _f("listing_fee_pct", "一口价手续费比例", "0~1，从卖方所得扣除", "float"),
        _f("barter_fee_by_realm", "易物手续费表", "大境界→固定灵石", "json"),
        _f("barter_fee_default", "易物缺省手续费", "境界未命中时", "int"),
        _f("auction_duration_sec", "拍卖默认时长秒", "上架未指定时", "int"),
        _f("auction_min_increment_pct", "最低加价比例", "相对当前价", "float"),
        _f("auction_fee_pct", "拍卖手续费比例", "成交后从卖方所得扣", "float"),
        _f(
            "auction_unsold_refund",
            "流拍退回方式",
            "inventory|mail",
            "string",
        ),
        _f("face_timeout_sec", "面交超时秒", "可被环境变量覆盖", "int"),
        _f("face_max_item_lines", "面交物品行上限", "单侧", "int"),
        _f("face_require_friend", "面交须道友", "发起时校验", "bool"),
        _f("face_require_online", "面交须双方在线", "WsHub 判定", "bool"),
        _f(
            "face_dev_assume_online",
            "开发假定在线",
            "仅 development 跳过 WS 在线检查",
            "bool",
        ),
        _f("recycle_label_zh", "回收池中文名", "玩家可见", "string"),
        _f("bazaar", "NPC坊市", "固定货架买价/卖价与提示文案", "json"),
    ),
)

MAIL_SCHEMA = DomainEditSchema(
    domain_id="mail",
    title_zh="邮件",
    description_zh="保留天数、附件种类上限、群发权限、附物日限（原赠送并入邮件）。",
    edit_modes=("json",),
    fields=(
        _f("retain_days", "保留天数", "附件未领过期基准", "int"),
        _f("expire_unclaimed", "未领过期策略", "return_sender|destroy", "string"),
        _f("max_attachment_lines", "附件物品种类上限", "单封默认6", "int"),
        _f("max_attachment_spirit_stones", "附件灵石上限", "0=不限", "int"),
        _f("max_body_len", "正文最大字数", "玩家信/附言", "int"),
        _f("list_limit", "列表条数", "收件箱默认", "int"),
        _f("sect_broadcast_min_rank_order", "宗门群发最低职位order", "掌门=9", "int"),
        _f("broadcast_max_recipients", "群发人数上限", "默认100", "int"),
        _f("gift", "附物发信日限", "日限/道友要求/回执", "json"),
    ),
)

COMBAT_ATTRS_SCHEMA = DomainEditSchema(
    domain_id="combat_attrs",
    title_zh="战斗属性注册表",
    description_zh="统一战斗/生活属性键、别名、主键映射与通道开关（ATTR-D01）；M13 只改数字不改键名。",
    edit_modes=("json",),
    fields=(
        _f("schema_version", "Schema 版本", "战报/快照携带", "int"),
        _f("defaults", "默认值", "speed/mp/攻防等", "json"),
        _f("aliases", "旧键别名", "atk→phys_atk 等", "json"),
        _f("primary_map", "主键映射", "力量→物攻等系数", "json"),
        _f("attrs", "属性注册表", "label_zh/help_zh/category", "json"),
        _f("entity_profiles", "实体适用面", "player/pet/monster…", "json"),
        _f("channels", "养成通道开关", "equipment/puppet…", "json"),
    ),
)

CHAT_SCHEMA = DomainEditSchema(
    domain_id="chat",
    title_zh="聊天频道",
    description_zh="五频道限速、敏感词、历史条数（M7 L4）；私聊持久条数单独可配。",
    edit_modes=("json",),
    fields=(
        _f("history_limit", "历史条数", "非私聊拉历史封顶", "int"),
        _f("dm_history_limit", "私聊每会话保留条数", "超限裁剪最旧；默认 100", "int"),
        _f("session_ephemeral", "会话级清空", "非私聊：关浏览器不拉历史", "bool"),
        _f("max_body_len", "正文最大字数", "单条", "int"),
        _f("rate_window_sec", "限速窗口秒", "滑动窗口", "int"),
        _f("rate_max_messages", "窗口内最大条数", "超限 40131", "int"),
        _f("sensitive_words", "敏感词表", "占位过滤", "json"),
        _f("sensitive_filter_enabled", "启用敏感词过滤", "开关", "bool"),
        _f("world_line_id", "世界分线键", "default 时引用为 world", "string"),
        _f("dm_require_friend", "私聊须道友", "true 时非道友拒聊", "bool"),
        _f("labels_zh", "频道中文名", "world/sect/dm…", "json"),
    ),
)

CHAT_HERITAGE_SCHEMA = DomainEditSchema(
    domain_id="chat_heritage",
    title_zh="聊天机缘",
    description_zh="份数、过期、日限、拆分策略（M7 L5）。",
    edit_modes=("json",),
    fields=(
        _f("expire_sec", "默认过期秒", "可被 HERITAGE_EXPIRE_SEC 覆盖", "int"),
        _f("min_shares", "最少份数", "", "int"),
        _f("max_shares", "最多份数", "", "int"),
        _f("max_spirit_stones", "单包灵石上限", "0=不限", "int"),
        _f("max_item_lines", "物品行上限", "", "int"),
        _f("claims_per_character", "同人限领", "默认 1", "int"),
        _f("daily_send_cap", "日发送次数", "", "int"),
        _f("daily_spirit_cap", "日发送灵石额", "", "int"),
        _f("fixed_remainder", "定额余数", "last_share|recycle", "string"),
        _f("expire_refund", "过期退回", "mail|inventory", "string"),
        _f("claim_broadcast_hide_amount", "领取广播隐藏数额", "", "bool"),
        _f("active_list_limit", "进行中列表上限", "", "int"),
        _f("allowed_channel_types", "允许频道", "world/sect/dm/party", "json"),
    ),
)

MENTOR_SCHEMA = DomainEditSchema(
    domain_id="mentor",
    title_zh="师徒",
    description_zh="境界差、名额、任务、传功、出师（M7 L6）。",
    edit_modes=("json",),
    fields=(
        _f("max_apprentices", "收徒上限", "师傅同时活跃徒弟数", "int"),
        _f("max_masters_per_apprentice", "拜师上限", "徒弟同时师傅数", "int"),
        _f("min_realm_gap", "最小境界差", "大境界档", "int"),
        _f("request_expire_sec", "申请过期秒", "0=不过期", "int"),
        _f("dissolve_cooldown_sec", "解除冷却秒", "", "int"),
        _f("keep_on_reincarnation", "轮回保留", "", "bool"),
        _f("history_after_dissolve", "解除后历史", "readonly|deny", "string"),
        _f("pass_cultivation", "传功规则", "费用/加成/日帽（兼容旧）", "json"),
        _f("daily_lesson", "日课三选一", "传道/授业/解惑比例", "json"),
        _f("teach", "传授规则", "日帽/阶梯天数", "json"),
        _f("study", "徒弟请学", "日帽/进度加成", "json"),
        _f("direct_disciple", "亲传弟子", "名额/授业解惑加成", "json"),
        _f("quests", "任务表", "quest_id→定义", "json"),
        _f("graduate", "出师奖励", "", "json"),
    ),
)

DUAL_CULTIVATION_SCHEMA = DomainEditSchema(
    domain_id="dual_cultivation",
    title_zh="双修",
    description_zh="功法（双增/传功/蛇蝎索取）、体力消耗、高潮循环、时长榜；初始设定均可后台改。",
    edit_modes=("json",),
    fields=(
        _f("invite_expire_sec", "邀约过期秒", "道侣超时取消；炉鼎超时自动接受", "int"),
        _f("undress_expire_sec", "宽衣过期秒", "道侣超时取消；炉鼎自动宽衣", "int"),
        _f("max_rerolls", "可重掷次数", "不含首次（旧掷骰兼容）", "int"),
        _f("spirit_stone_cost", "开局灵石", "邀请方支付", "int"),
        _f("cultivation_gap_scale", "修为差距尺度", "传功/双增/索取归一化", "int"),
        _f(
            "stamina_costs",
            "体力消耗",
            "mutual_gain 双方相同；transfer 传方>受方；extract 索取>被索取",
            "json",
        ),
        _f("climax", "高潮循环", "base_chance/growth/jitter 等", "json"),
        _f("rank_min_scores", "上榜门槛", "duration_total 等", "json"),
        _f("rank_labels", "榜中文名", "", "json"),
        _f("dice_tiers", "掷骰档表", "出目→倍率/时长（兼容）", "json"),
        _f("techniques", "双修功法表", "含蛇蝎索取 mode=extract", "json"),
    ),
)

CURRENCIES_SCHEMA = DomainEditSchema(
    domain_id="currencies",
    title_zh="币种目录",
    description_zh="六币种展示与是否可玩家直转（M7 L8）。",
    edit_modes=("json",),
    fields=(_f("currencies", "币种表", "id→定义", "json"),),
)

COMMERCE_SCHEMA = DomainEditSchema(
    domain_id="commerce",
    title_zh="商业化",
    description_zh="会员档、天道商店、沙盒（M7 L8）。",
    edit_modes=("json",),
    fields=(
        _f("keep_membership_on_reincarnation", "轮回保留会员", "", "bool"),
        _f("membership_tiers", "会员档表", "free/tier1/tier2", "json"),
        _f("shop", "天道商店", "货架/禁售/边界文案", "json"),
        _f("sandbox", "沙盒加点", "单次/日上限", "json"),
    ),
)

MAP_SCHEMA = DomainEditSchema(
    domain_id="map",
    title_zh="地图区域",
    description_zh="区域注册表。",
    edit_modes=("entries", "json"),
    fields=(_f("regions", "区域表", "id→区域定义", "json"),),
    entry_path=("regions",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("enabled", "是否开放", "布尔", "bool"),
        _f("note", "备注", "运营备注", "string"),
    ),
)

ACTIVITY_SCHEMA = DomainEditSchema(
    domain_id="activity",
    title_zh="活动开关",
    description_zh="活动占位开关。",
    edit_modes=("entries", "json"),
    fields=(_f("activities", "活动表", "id→活动定义", "json"),),
    entry_path=("activities",),
    entry_fields=(
        _ENTRY_COMMON_NAME,
        _f("enabled", "是否开放", "布尔", "bool"),
        _f("note", "备注", "运营备注", "string"),
    ),
)

TAUNT_AURAS_SCHEMA = DomainEditSchema(
    domain_id="taunt_auras",
    title_zh="嘲讽光环",
    description_zh="自走棋嘲讽光环形状与展示；单位用 taunt_aura_id 引用本表。",
    edit_modes=("entries", "json"),
    fields=(
        _f("schema_version", "结构版本", "整数；当前为 1", "int"),
        _f("auras", "光环表", "id→光环定义", "json"),
    ),
    entry_path=("auras",),
    entry_fields=(
        _f("label_zh", "中文名", "面板与战报展示", "string"),
        _f("help_zh", "运营说明", "后台编辑提示", "string"),
        _f("summary", "玩家摘要", "短描述范围", "string"),
        _f(
            "shape",
            "形状",
            "ortho_adjacent / chebyshev / offsets",
            "string",
        ),
        _f("radius", "半径", "仅 chebyshev；≥1", "int"),
        _f("cells", "偏移表", "仅 offsets；[{dx,dy}]", "json"),
        _f("include_self_cell", "含自身格", "默认否", "bool"),
        _f("duration_rounds", "持续回合", "空=直到死亡；Phase B 生效", "null_str"),
    ),
)

WEATHER_SCHEMA = DomainEditSchema(
    domain_id="weather",
    title_zh="天气",
    description_zh="区域天气配置；当前以 JSON 覆盖为主，表格可后续加深。",
    edit_modes=("json", "table"),
    fields=(
        _f("regions", "区域天气", "区域→天气定义", "json"),
        _f("labels", "展示文案", "天气 id→中文", "json"),
    ),
    sheets=(),
)

CALENDAR_SCHEMA = DomainEditSchema(
    domain_id="calendar",
    title_zh="历法时辰",
    description_zh="六时历法；当前以 JSON 覆盖为主。",
    edit_modes=("json", "table"),
    fields=(
        _f("shichen_order", "时辰顺序", "字符串列表", "json"),
        _f("slot_seconds", "每时秒数", "现实秒", "int"),
        _f("labels", "展示文案", "时辰 id→中文", "json"),
    ),
    sheets=(),
)

AVATAR_SCHEMA = DomainEditSchema(
    domain_id="avatar",
    title_zh="化身",
    description_zh=(
        "永久单化身；境界功能解锁矩阵、互传保留率、体力/日行动、挂机速率。"
        "max_avatars 必须为 1。"
    ),
    edit_modes=("table", "json"),
    fields=(
        _f("unlock_major_realm", "凝练门槛大境界", "如 jindan", "string"),
        _f("max_avatars", "化身上限", "定案必须为 1", "int"),
        _f("initial_stat_ratio", "初始属性比例", "凝练时相对本体", "float"),
        _f("material_mod_placeholder", "材料修正占位", "乘区占位", "float"),
        _f("condense_spirit_stone_cost", "凝练灵石", "整数", "int"),
        _f("spirit_stone_cost_per_tick_ratio", "化身耗石比例", "相对本体同境", "float"),
        _f("feature_unlocks", "功能解锁表", "feature_id→min_major/label/summary", "json"),
        _f("transfer", "互传规则", "allow/deny/retention", "json"),
        _f("stamina", "体力与日行动", "cap/recovery/action_costs", "json"),
        _f("friend_assist", "道友助战", "invite_expire_sec / assist_dev_assume_online", "json"),
        _f("idle", "化身挂机速率", "spirit/body/crafting", "json"),
    ),
    sheets=(
        SheetMeta(
            sheet_id="globals",
            title_zh="全局标量",
            description_zh="凝练门槛、单化身上限、属性比例等；一行一个键。",
            primary_keys=("key",),
            columns=(
                _f("key", "键名", "如 max_avatars / unlock_major_realm", "string"),
                _f("label_zh", "中文名", "只读说明列", "string"),
                _f("value", "数值", "字符串或数字", "string"),
                _f("help_zh", "说明", "只读说明列", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="feature_unlocks",
            title_zh="功能解锁",
            description_zh="本体大境界 ≥ min_major 则解锁；禁止业务写死境界。",
            primary_keys=("feature_id",),
            columns=(
                _f("feature_id", "功能 ID", "如 idle_spirit / solo_battle", "string"),
                _f("min_major", "最低大境界", "须存在于 realms", "string"),
                _f("label_zh", "中文名", "玩家可见", "string"),
                _f("summary", "说明", "玩家可见摘要", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="transfer",
            title_zh="互传折扣",
            description_zh="保留率与白名单；一行一个键。",
            primary_keys=("key",),
            columns=(
                _f("key", "键名", "retention_ratio / summary / min_amount 等", "string"),
                _f("label_zh", "中文名", "只读说明列", "string"),
                _f("value", "数值", "字符串或数字；列表用逗号分隔", "string"),
                _f("help_zh", "说明", "只读说明列", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="stamina",
            title_zh="体力全局",
            description_zh="体力上限与日行动；一行一个键。",
            primary_keys=("key",),
            columns=(
                _f("key", "键名", "base_cap / daily_action_cap / recovery.per_hour 等", "string"),
                _f("label_zh", "中文名", "只读说明列", "string"),
                _f("value", "数值", "字符串或数字", "string"),
                _f("help_zh", "说明", "只读说明列", "string"),
            ),
        ),
        SheetMeta(
            sheet_id="action_costs",
            title_zh="行动耗体",
            description_zh="独战/探索/接任务等行动的体力消耗。",
            primary_keys=("action_id",),
            columns=(
                _f("action_id", "行动 ID", "solo_battle / assist_battle / explore_step", "string"),
                _f("cost", "体力消耗", "整数", "int"),
            ),
        ),
        SheetMeta(
            sheet_id="idle_rates",
            title_zh="化身挂机速率",
            description_zh="三向每 tick 产出；方向可选另看功能解锁。",
            primary_keys=("direction",),
            columns=(
                _f("direction", "方向", "spirit / body / crafting", "string"),
                _f("enabled", "速率表启用", "body 可关", "bool"),
                _f("gain_per_tick", "每 tick 产出", "整数", "int"),
            ),
        ),
    ),
)


DAO_SCHEMA = DomainEditSchema(
    domain_id="dao",
    title_zh="大道",
    description_zh="道目录样本、开道门槛、道值曲线与运用占位（M6）。",
    edit_modes=("table", "json"),
    fields=(
        _f("open", "开道规则", "min_major_realm / picks / deny_reroll", "json"),
        _f("pool", "道池规则", "endgame 开关等", "json"),
        _f("resources", "道资源", "初始道值与等级曲线", "json"),
        _f("usage", "运用占位", "battle/craft 消耗与乘区", "json"),
        _f("restraint_enabled", "启用克制", "是否读 dao_restraint", "bool"),
        _f("entries", "道目录", "dao_id → 定义", "json"),
        _f("labels", "中文标签", "dao_id → 中文名", "json"),
    ),
    sheets=(
        SheetMeta(
            sheet_id="entries",
            title_zh="道目录",
            description_zh="样本道条目。",
            primary_keys=("dao_id",),
            columns=(
                _f("dao_id", "大道 ID", "如 dao_flame", "string"),
                _f("label_zh", "中文名", "玩家可见", "string"),
                _f("category", "大类键", "elemental/special/…", "string"),
                _f("rarity", "稀有度键", "common/…", "string"),
                _f("weight", "开道权重", "正数", "float"),
                _f("description", "说明", "图鉴文案", "string"),
            ),
        ),
    ),
)


DAO_RESTRAINT_SCHEMA = DomainEditSchema(
    domain_id="dao_restraint",
    title_zh="大道克制",
    description_zh="上位克制样本矩阵。",
    edit_modes=("table", "json"),
    fields=(_f("edges", "克制边列表", "attacker/defender/damage_mul/label_zh", "json"),),
    sheets=(
        SheetMeta(
            sheet_id="edges",
            title_zh="克制边",
            description_zh="攻方道克制守方道。",
            primary_keys=("attacker", "defender"),
            columns=(
                _f("attacker", "攻方道 ID", "如 dao_flame_apex", "string"),
                _f("defender", "守方道 ID", "如 dao_flame", "string"),
                _f("damage_mul", "伤害乘区", "如 1.15", "float"),
                _f("label_zh", "中文标签", "战报用，如 上位克制", "string"),
            ),
        ),
    ),
)


DAO_LORD_SCHEMA = DomainEditSchema(
    domain_id="dao_lord",
    title_zh="道主",
    description_zh="道主门槛、挑战时段、冷却、特权占位与道主之争赛会日程。",
    edit_modes=("table", "json"),
    fields=(
        _f("claim_min_level", "夺位最低道等级", "整数", "int"),
        _f("challenge_min_level", "挑战最低道等级", "整数", "int"),
        _f("cooldown", "冷却秒数", "win/lose/abort", "json"),
        _f("windows", "开窗列表（过渡）", "start_hour/end_hour", "json"),
        _f("privileges_default", "特权默认", "布尔占位", "json"),
        _f(
            "contest",
            "道主之争赛会",
            "报名窗/开打时刻/直播轮次等；立刻开赛走运营动作",
            "json",
        ),
        _f("contest.tz", "赛会时区", "如 Asia/Shanghai", "str"),
        _f("contest.registration_start", "报名开始时刻", "每日 HH:MM（配置时区）", "str"),
        _f("contest.registration_end", "报名结束时刻", "每日 HH:MM；勿晚于开打", "str"),
        _f("contest.fight_at", "开打时刻", "每日 HH:MM；到点关闭报名并匹配", "str"),
        _f(
            "contest.live_round_kinds",
            "可直播轮次",
            "如 semi/final/lord",
            "json",
        ),
        _f("contest.live_prep_seconds", "直播准备秒数", "半决起入席倒计时", "int"),
        _f("contest.live_playback_seconds", "对战直播秒数", "准备结束后的节拍窗", "int"),
        _f("contest.live_tick_base_ms", "普通事件间隔毫秒", "直播节拍", "int"),
        _f("contest.live_dramatic_pause_ms", "关键停顿毫秒", "阵亡/结束等", "int"),
        _f(
            "contest.log_retain_until_next_contest",
            "日志保留至下场",
            "true=下场开赛清回溯",
            "bool",
        ),
        _f(
            "contest.both_offline_policy",
            "双离线策略",
            "earlier_entrant_advances | double_eliminate",
            "str",
        ),
        _f(
            "contest.dev_assume_online",
            "DEV 假定在线",
            "生产须 false",
            "bool",
        ),
    ),
)


WORLD_EVENTS_SCHEMA = DomainEditSchema(
    domain_id="world_events",
    title_zh="世界事件",
    description_zh="世界 Boss / 秘境开窗骨架。",
    edit_modes=("json",),
    fields=(
        _f("enabled", "总开关", "亦可被 WORLD_EVENTS_ENABLED 覆盖", "bool"),
        _f("events", "事件表", "event_id → 定义", "json"),
    ),
)


DOMAIN_EDIT_SCHEMAS: dict[str, DomainEditSchema] = {
    schema.domain_id: schema
    for schema in (
        REALMS_SCHEMA,
        IDLE_SCHEMA,
        DICE_SCHEMA,
        COMBAT_ATTRS_SCHEMA,
        BREAKTHROUGH_SCHEMA,
        PETS_SCHEMA,
        PET_AFFIXES_SCHEMA,
        PET_SKILLS_SCHEMA,
        PET_SKILL_BOOKS_SCHEMA,
        PET_DUEL_SCHEMA,
        PET_EGGS_SCHEMA,
        PET_PASSIVES_SCHEMA,
        PET_FEED_SCHEMA,
        PET_ENCOUNTER_SCHEMA,
        PET_CAPTURE_SCHEMA,
        ITEMS_SCHEMA,
        TECHNIQUES_SCHEMA,
        MONSTERS_SCHEMA,
        FORMATIONS_SCHEMA,
        SECTS_SCHEMA,
        FRIENDS_SCHEMA,
        TRADE_SCHEMA,
        MAIL_SCHEMA,
        CHAT_SCHEMA,
        CHAT_HERITAGE_SCHEMA,
        MENTOR_SCHEMA,
        DUAL_CULTIVATION_SCHEMA,
        CURRENCIES_SCHEMA,
        COMMERCE_SCHEMA,
        MAP_SCHEMA,
        ACTIVITY_SCHEMA,
        TAUNT_AURAS_SCHEMA,
        WEATHER_SCHEMA,
        CALENDAR_SCHEMA,
        AVATAR_SCHEMA,
        DAO_SCHEMA,
        DAO_RESTRAINT_SCHEMA,
        DAO_LORD_SCHEMA,
        WORLD_EVENTS_SCHEMA,
    )
}


def get_domain_edit_schema(domain_id: str) -> DomainEditSchema | None:
    """按域 ID 取编辑契约；未知域返回 None。"""
    return DOMAIN_EDIT_SCHEMAS.get(domain_id)
