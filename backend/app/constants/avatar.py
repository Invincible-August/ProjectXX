"""化身协议常量：凝练配方错误码与破除。"""

from __future__ import annotations

# 未达凝练境界（需 unlock_major_realm 及以上）
ERR_CONDENSE_REALM = 40050
# 已凝练化身（凝练）/ 尚未凝练化身（挂机、破除等）
ERR_AVATAR_EXISTS_OR_MISSING = 40051
# 凝练灵力（修为池）不足
ERR_CONDENSE_CULTIVATION = 40053
# 未选择或未学会化身功法
ERR_CONDENSE_TECHNIQUE = 40054
# 化身正在工坊/助战，不可破除
ERR_AVATAR_BUSY = 40056
# 化身不可进入的身份境界（非常规修为链）
AVATAR_FORBIDDEN_IDENTITY_REALMS: frozenset[str] = frozenset(
    {
        "dao_lord",  # 道主境
        "reincarnation",  # 轮回境
    },
)
# 化身常规修为链默认硬顶（当前 realms 表末境）
AVATAR_DEFAULT_MAX_MAJOR_REALM: str = "true_immortal"
# 化身相对本体默认可超前的大境界数
AVATAR_DEFAULT_LEAD_MAJORS: int = 0
# 化身突破触达硬顶 / 身份禁区
ERR_AVATAR_REALM_CAP: int = 40094
# 装备/功法/神通槽主体：本体
LOADOUT_ACTOR_MAIN: str = "main"
# 装备/功法/神通槽主体：化身
LOADOUT_ACTOR_AVATAR: str = "avatar"
# 凝练后化身起始大境界（金丹初期）
AVATAR_CONDENSE_MAJOR_REALM: str = "jindan"


def normalize_loadout_actor(raw: str | None) -> str:
    """把 API actor 归一成 main / avatar。"""
    value = str(raw or LOADOUT_ACTOR_MAIN).strip().lower()
    if value in {LOADOUT_ACTOR_AVATAR, "av"}:
        return LOADOUT_ACTOR_AVATAR
    return LOADOUT_ACTOR_MAIN
