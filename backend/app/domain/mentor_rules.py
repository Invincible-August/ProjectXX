"""师徒领域纯规则（M7 L6 · 无 IO）。"""

from __future__ import annotations


def realm_index(major_realm: str, realm_order: list[str]) -> int:
    """
    大境界在链上的下标；未知视为 -1。

    Args:
        major_realm: 境界键。
        realm_order: 有序大境界键。

    Returns:
        int: 下标。
    """
    key = str(major_realm or "")
    try:
        return realm_order.index(key)
    except ValueError:
        return -1


def master_realm_ok(
    *,
    master_major: str,
    apprentice_major: str,
    realm_order: list[str],
    min_gap: int,
) -> tuple[bool, str | None]:
    """
    校验师傅境界是否高于徒弟足够档位。

    Args:
        master_major: 师傅大境界。
        apprentice_major: 徒弟大境界。
        realm_order: 境界链。
        min_gap: 最小档差。

    Returns:
        tuple: (允许, 中文原因)。
    """
    if int(min_gap) <= 0:
        return True, None
    mi = realm_index(master_major, realm_order)
    ai = realm_index(apprentice_major, realm_order)
    if mi < 0 or ai < 0:
        return False, "境界配置异常"
    if mi - ai < int(min_gap):
        return False, f"师傅须至少高出徒弟 {min_gap} 个大境界"
    return True, None


def same_region_stub(*, stub_enabled: bool) -> bool:
    """
    M7 同图判定桩：开启则一律视为同区。

    Args:
        stub_enabled: SAME_REGION_STUB / YAML。

    Returns:
        bool: 是否同区。
    """
    return bool(stub_enabled)
