"""
道主特权投影（S1-5）：布尔旗标 ↔ privilege Ability grants 双写兼容。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.constants.character import GRANT_SOURCE_DAO_LORD
from app.constants.dao_lord import (
    PRIVILEGE_ABILITY_TO_FLAG,
    PRIVILEGE_FLAG_TO_ABILITY,
    PRIVILEGE_GRANTS_KEY,
)
from app.game.ability import SimpleGrantSource


def normalize_privileges_payload(
    raw: dict[str, Any] | None,
    *,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    归一化特权 JSON：保证布尔旗标与 grants 列表一致（互为投影）。

    Args:
        raw: 席位上已存 privileges_json 解析结果。
        defaults: dao_lord.privileges_default。

    Returns:
        dict[str, Any]: 可写回 privileges_json 的完整载荷。
    """
    base = deepcopy(defaults or {})
    data = deepcopy(raw or {})
    merged: dict[str, Any] = {**base, **data}

    grants_from_list: list[str] = []
    raw_grants = merged.get(PRIVILEGE_GRANTS_KEY)
    if isinstance(raw_grants, list):
        grants_from_list = [str(x) for x in raw_grants if x]

    grants_from_flags: list[str] = []
    for flag, ability_id in PRIVILEGE_FLAG_TO_ABILITY.items():
        if bool(merged.get(flag)):
            grants_from_flags.append(ability_id)

    grant_set = list(dict.fromkeys([*grants_from_list, *grants_from_flags]))
    for ability_id, flag in PRIVILEGE_ABILITY_TO_FLAG.items():
        merged[flag] = ability_id in grant_set
    merged[PRIVILEGE_GRANTS_KEY] = grant_set
    return merged


def privilege_grant_sources(
    privileges: dict[str, Any],
    *,
    dao_id: str,
) -> list[SimpleGrantSource]:
    """
    将归一化特权转为 GrantSource 列表。

    Args:
        privileges: 已 normalize 的特权 dict。
        dao_id: 大道 id（作 source_id 后缀）。

    Returns:
        list[SimpleGrantSource]: 无授予时为空列表。
    """
    grants = privileges.get(PRIVILEGE_GRANTS_KEY) or []
    if not isinstance(grants, list) or not grants:
        return []
    return [
        SimpleGrantSource(
            source_type=GRANT_SOURCE_DAO_LORD,
            source_id=f"dao_lord:{dao_id}",
            ability_ids=[str(x) for x in grants],
        ),
    ]


def has_privilege(privileges: dict[str, Any], flag: str) -> bool:
    """查询布尔特权（兼容仅 grants 或仅 flag 的旧数据）。"""
    norm = normalize_privileges_payload(privileges)
    return bool(norm.get(flag))
