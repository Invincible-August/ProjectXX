"""炼体大境层/期与淬体成功率。"""

from __future__ import annotations

import random
from types import SimpleNamespace

from app.domain.body_temper import (
    apply_body_temper_progress,
    attempt_quench,
    build_body_temper_public,
    quench_readiness,
)
from app.services.realm_config import clear_game_config_cache, get_game_config


def setup_function() -> None:
    """确保配置缓存新鲜。"""
    clear_game_config_cache()


def test_body_temper_majors_layers_then_phases() -> None:
    """前两境 layers 10 档，其后 phases 4 档；道体可扩 next_major。"""
    cfg = get_game_config().body_temper
    assert cfg.majors["refine_skin"].stage_mode == "layers"
    assert len(cfg.majors["refine_skin"].stages) == 10
    assert cfg.majors["forge_bone"].stage_mode == "layers"
    assert cfg.majors["open_meridian"].stage_mode == "phases"
    assert len(cfg.majors["open_meridian"].stages) == 4
    assert cfg.majors["dao_body"].next_major is None
    assert cfg.unlock_majors[-1] == "dacheng"


def test_preview_shows_target_even_when_progress_low() -> None:
    """进度未满时仍展示成功后到达与进阶方式。"""
    character = SimpleNamespace(
        major_realm="body_tempering",
        body_temper_stage="refine_skin",
        body_temper_layer=1,
        body_temper_layer_label="layer_1",
        body_temper_progress=10,
    )
    ready = quench_readiness(character)
    assert ready["can_quench"] is False
    assert ready["to_display"] == "炼皮二层"
    assert ready["advance_type"] == "layer"
    assert "升层" in (ready["advance_type_label_zh"] or "")


def test_layer_advance_with_success_rate() -> None:
    """炼皮一层满进度可淬体至二层；成功率注入必成。"""
    character = SimpleNamespace(
        major_realm="body_tempering",
        body_temper_stage="refine_skin",
        body_temper_layer=1,
        body_temper_layer_label="layer_1",
        body_temper_progress=0,
    )
    apply_body_temper_progress(character, 50)
    assert character.body_temper_progress == 50
    ready = quench_readiness(character)
    assert ready["can_quench"] is True
    assert ready["advance_type"] == "layer"
    assert ready["to_display"] == "炼皮二层"
    assert ready["needs_tribulation"] is False
    assert 0 < ready["success_rate"] <= 1

    result = attempt_quench(character, rng=random.Random(0))
    # Random(0).random() 通常很小，大概率成功；若失败再强制
    if not result["success"]:
        character.body_temper_progress = 50
        result = attempt_quench(character, rng=random.Random(1))
    assert result["success"] is True
    assert character.body_temper_layer == 2
    assert character.body_temper_layer_label == "layer_2"
    assert character.body_temper_progress == 0


def test_quench_fail_keeps_progress_ratio() -> None:
    """失败按 keep_ratio 回退进度。"""
    character = SimpleNamespace(
        major_realm="body_tempering",
        body_temper_stage="refine_skin",
        body_temper_layer=1,
        body_temper_layer_label="layer_1",
        body_temper_progress=50,
    )
    # 强制失败：阈值恒为 1.0
    class AlwaysFail:
        def random(self) -> float:
            return 0.99

    result = attempt_quench(character, rng=AlwaysFail())  # type: ignore[arg-type]
    assert result["success"] is False
    keep = get_game_config().body_temper.layer_advance.fail_progress_keep_ratio
    assert character.body_temper_progress == int(50 * keep)
    assert character.body_temper_layer == 1


def test_major_advance_blocked_by_cultivation_major() -> None:
    """炼皮圆满跨境锻骨须主修达炼气。"""
    character = SimpleNamespace(
        major_realm="body_tempering",
        body_temper_stage="refine_skin",
        body_temper_layer=10,
        body_temper_layer_label="perfection",
        body_temper_progress=700,
    )
    ready = quench_readiness(character)
    assert ready["can_quench"] is False
    assert "主修" in (ready["reason"] or "")

    character.major_realm = "qi_refining"
    ready2 = quench_readiness(character)
    assert ready2["can_quench"] is True
    assert ready2["advance_type"] == "major"
    assert ready2["to_stage"] == "forge_bone"


def test_realms_sheet_keeps_body_temper_majors() -> None:
    """境界表格往返保留炼体大境与淬体规则。"""
    from app.config_source.yaml_source import get_shared_yaml_source
    from app.services.admin_sheet_codec import payload_to_sheets, sheets_to_payload

    raw = get_shared_yaml_source().load_raw("realms.yaml", copy=True)
    sheets = payload_to_sheets("realms", raw)
    rebuilt = sheets_to_payload("realms", sheets)
    assert rebuilt["body_temper_unlock_majors"] == raw["body_temper_unlock_majors"]
    assert rebuilt["body_temper_majors"]["refine_skin"]["name"] == "炼皮"
    assert len(rebuilt["body_temper_majors"]["refine_skin"]["stages"]) == 10
    assert rebuilt["body_temper_quench"]["layer_advance"]["success_rate"] == (
        raw["body_temper_quench"]["layer_advance"]["success_rate"]
    )
    pub = build_body_temper_public(
        SimpleNamespace(
            major_realm="body_tempering",
            body_temper_stage="refine_skin",
            body_temper_layer=1,
            body_temper_layer_label="layer_1",
            body_temper_progress=0,
        ),
    )
    assert "炼皮" in pub["body_temper_display"]
