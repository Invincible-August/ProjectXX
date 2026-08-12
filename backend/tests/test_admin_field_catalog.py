"""字段中文目录覆盖率（运营可见性）。"""

from __future__ import annotations

from app.config_source.yaml_source import get_shared_yaml_source
from app.services.admin_field_catalog import build_field_catalog, catalog_coverage


def test_idle_catalog_fully_documented() -> None:
    """挂机域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("idle.yaml", copy=True)
    catalog = build_field_catalog(raw)
    cov = catalog_coverage(catalog)
    assert cov["total_paths"] > 10
    assert cov["undocumented_paths"] == 0, [
        row["path"] for row in catalog if not row["documented"]
    ]


def test_realms_catalog_fully_documented() -> None:
    """境界域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("realms.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_dice_catalog_fully_documented() -> None:
    """修为骰路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("dice.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_pets_catalog_covers_species_fields() -> None:
    """灵宠物种关键字段有中文。"""
    raw = get_shared_yaml_source().load_raw("pets.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_pet_affixes_catalog_fully_documented() -> None:
    """灵宠词条域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("pet_affixes.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_pet_skills_catalog_fully_documented() -> None:
    """灵宠技能域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("pet_skills.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_pet_skill_books_catalog_fully_documented() -> None:
    """灵宠技能书域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("pet_skill_books.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []


def test_pet_duel_catalog_fully_documented() -> None:
    """灵宠对战域路径均有中文说明。"""
    raw = get_shared_yaml_source().load_raw("pet_duel.yaml", copy=True)
    catalog = build_field_catalog(raw)
    undoc = [row["path"] for row in catalog if not row["documented"]]
    assert undoc == []
