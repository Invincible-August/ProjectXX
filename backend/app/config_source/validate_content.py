"""
Sample-table validator shared by boot, admin publish probes, and CI (M8 R6 / AB1).

Call ``validate_loaded_bundle`` at the end of ``load_game_config``.
Run as ``python -m app.config_source.validate_content`` in CI.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Mapping

from app.constants.combat_attrs import (
    CONSTITUTION_BASE_ATTR_KEYS,
    CONSTITUTION_LEGACY_EFFECT_KEYS,
)
from app.constants.research import TALISMAN_KINDS, TALISMAN_TRIGGERS
from app.constants.technique_craft import AFFIX_ROLES, EFFICACY_IDS

logger = logging.getLogger(__name__)


class ContentValidationError(ValueError):
    """Raised when an official YAML sample table fails ATTR / schema checks."""


def registered_attr_keys(combat_attrs: Any) -> set[str]:
    """ATTR keys plus aliases that sample stats may use."""
    attrs = getattr(combat_attrs, "attrs", {}) or {}
    aliases = getattr(combat_attrs, "aliases", {}) or {}
    return {str(k) for k in attrs} | {str(k) for k in aliases}


def assert_attr_stats(
    path: str,
    stats: Mapping[str, Any] | None,
    allowed: set[str],
) -> None:
    """
    Reject unknown combat-attr keys in a stats mapping.

    Args:
        path: Error prefix (e.g. ``equipment.iron_sword_t1.stats``).
        stats: Mapping of attr key → number.
        allowed: Registered ATTR keys ∪ aliases.

    Raises:
        ContentValidationError: A key is not in the ATTR registry.
    """
    for key in stats or {}:
        sk = str(key)
        if sk not in allowed:
            raise ContentValidationError(f"{path}.{sk}: unknown combat attr key")


def validate_talisman_effects_raw(raw: Mapping[str, Any] | None) -> None:
    """
    Require each whitelist row to be a mapping with Chinese label and known trigger.

    Args:
        raw: talisman_effects.yaml root (effect_id → body).

    Raises:
        ContentValidationError: Missing label_zh or illegal trigger.
    """
    for effect_id, body in (raw or {}).items():
        prefix = f"talisman_effects.{effect_id}"
        if not isinstance(body, dict):
            raise ContentValidationError(f"{prefix} 须为 mapping")
        label = str(body.get("label_zh") or "").strip()
        if not label:
            raise ContentValidationError(f"{prefix} 缺少 label_zh")
        trigger = str(body.get("trigger") or "").strip()
        if trigger not in TALISMAN_TRIGGERS:
            raise ContentValidationError(
                f"{prefix}.trigger={trigger!r} 不在白名单 {sorted(TALISMAN_TRIGGERS)}",
            )
        kind = str(body.get("kind") or "buff").strip()
        if kind not in TALISMAN_KINDS:
            raise ContentValidationError(
                f"{prefix}.kind={kind!r} 须为 {sorted(TALISMAN_KINDS)}",
            )


def validate_technique_craft(
    craft: Any,
    *,
    major_realm_ids: set[str],
    attr_keys: set[str],
) -> None:
    """
    Technique-craft affixes must use known efficacies/roles; ranks must be major ids.

    Args:
        craft: Parsed TechniqueCraftConfig (or mock).
        major_realm_ids: Keys of realms.yaml ``major_realms``.
        attr_keys: Registered ATTR keys ∪ aliases.

    Raises:
        ContentValidationError: Illegal efficacy_allow, role, rank id, or stats key.
    """
    if craft is None:
        return
    for affix_id, affix in (getattr(craft, "affixes", None) or {}).items():
        prefix = f"research.technique_craft.affixes.{affix_id}"
        allow = [str(x) for x in (getattr(affix, "efficacy_allow", ()) or ())]
        unknown = [x for x in allow if x not in EFFICACY_IDS]
        if unknown:
            raise ContentValidationError(
                f"{prefix}.efficacy_allow={unknown!r} 须 ⊆ {list(EFFICACY_IDS)}",
            )
        role = str(getattr(affix, "role", "") or "")
        if role not in AFFIX_ROLES:
            raise ContentValidationError(
                f"{prefix}.role={role!r} 须为 {sorted(AFFIX_ROLES)}",
            )
        assert_attr_stats(f"{prefix}.stats", getattr(affix, "stats", None), attr_keys)
    for rank_id in getattr(craft, "ranks", None) or {}:
        rid = str(rank_id)
        if rid not in major_realm_ids:
            raise ContentValidationError(
                f"research.technique_craft.ranks.{rid}: 须为 realms.yaml 大境界 id",
            )
    for weapon_id, bonus in (getattr(craft, "weapon_bonus", None) or {}).items():
        assert_attr_stats(
            f"research.technique_craft.weapon_bonus.{weapon_id}",
            bonus,
            attr_keys,
        )


def validate_constitution_tables(
    constitution: Any,
    *,
    attr_keys: set[str],
) -> None:
    """
    Constitution affix effect keys must be ATTR, alias, or a frozen legacy set.

    Args:
        constitution: Parsed ConstitutionConfig.
        attr_keys: Registered ATTR keys ∪ aliases.

    Raises:
        ContentValidationError: Unknown base_attrs / effects key.
    """
    items = getattr(constitution, "items", {}) or {}
    allowed_effects = attr_keys | set(CONSTITUTION_LEGACY_EFFECT_KEYS)
    for def_id, item in items.items():
        prefix = f"constitution.items.{def_id}"
        for key in getattr(item, "base_attrs", {}) or {}:
            sk = str(key)
            if sk not in CONSTITUTION_BASE_ATTR_KEYS:
                raise ContentValidationError(f"{prefix}.base_attrs.{sk}: unknown constitution base attr")
        for attr_name in ("effects", "main_effects", "sub_effects"):
            mapping = getattr(item, attr_name, None)
            if not isinstance(mapping, dict):
                continue
            for key in mapping:
                sk = str(key)
                if sk not in allowed_effects:
                    raise ContentValidationError(
                        f"{prefix}.{attr_name}.{sk}: unknown combat attr key",
                    )


def validate_loaded_bundle(bundle: Any) -> None:
    """
    Extra ATTR / schema checks after YAML parsers succeed.

    Equipment stats and research affixes are already rejected in their parsers;
    this pass covers constitution words and re-asserts talisman triggers.

    Args:
        bundle: GameConfigBundle.

    Raises:
        ContentValidationError: Sample table is illegal.
    """
    attr_keys = registered_attr_keys(bundle.combat_attrs)
    for item_id, item in (bundle.equipment.items or {}).items():
        assert_attr_stats(f"equipment.{item_id}.stats", item.stats, attr_keys)
    for affix_id, affix in (bundle.research.affixes or {}).items():
        assert_attr_stats(f"research.affixes.{affix_id}.stats", affix.stats, attr_keys)
    validate_technique_craft(
        getattr(bundle.research, "technique_craft", None),
        major_realm_ids={str(k) for k in (getattr(bundle, "realms", None) or {})},
        attr_keys=attr_keys,
    )
    validate_constitution_tables(bundle.constitution, attr_keys=attr_keys)
    for effect_id, effect in (bundle.talisman_effects or {}).items():
        if not str(getattr(effect, "label_zh", "") or "").strip():
            raise ContentValidationError(f"talisman_effects.{effect_id} 缺少 label_zh")
        trigger = str(getattr(effect, "trigger", "") or "")
        if trigger not in TALISMAN_TRIGGERS:
            raise ContentValidationError(
                f"talisman_effects.{effect_id}.trigger={trigger!r} 不在白名单",
            )
        kind = str(getattr(effect, "kind", "") or "buff")
        if kind not in TALISMAN_KINDS:
            raise ContentValidationError(
                f"talisman_effects.{effect_id}.kind={kind!r} 须为 {sorted(TALISMAN_KINDS)}",
            )
    logger.debug("content sample tables validated")


def validate_startup() -> Any:
    """
    Load the play bundle (same path as FastAPI boot) and return it.

    Returns:
        GameConfigBundle: Validated snapshot.

    Raises:
        Exception: YAML parse or sample validation failure.
    """
    from app.services.realm_config import get_game_config

    return get_game_config()


def main() -> int:
    """CLI: exit 0 if official YAML samples load; non-zero on bad tables."""
    try:
        bundle = validate_startup()
    except Exception as exc:  # noqa: BLE001 — CI wants the message on stderr
        print(f"content validation failed: {exc}", file=sys.stderr)
        return 1
    n_eq = len(getattr(bundle.equipment, "items", {}) or {})
    n_fx = len(bundle.talisman_effects or {})
    print(f"content tables ok equipment={n_eq} talisman_effects={n_fx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
