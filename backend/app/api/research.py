"""Research desk HTTP routes (mounted at /cave/lab; /research is a compat alias)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import (
    get_current_user,
    get_play_gate,
    get_research_service,
    get_technique_craft_service,
)
from app.db.models import User
from app.schemas.common import success
from app.schemas.research import (
    ResearchCreateRequest,
    ResearchFinalizeRequest,
    ResearchFormationDraftRequest,
)
from app.schemas.technique_craft import (
    TechniqueAffixChooseRequest,
    TechniqueAffixSlotRequest,
    TechniqueAffixUpgradeRequest,
    TechniqueBaseUpgradeRequest,
    TechniqueConditionsRequest,
    TechniqueEmbedRequest,
    TechniqueFinalizeRequest,
)
from app.services.play_gate import PlayGate
from app.services.research_service import ResearchService
from app.services.technique_craft_service import TechniqueCraftService

router = APIRouter(tags=["cave"])


async def _prepare_research_write(
    gate: PlayGate,
    current_user: User,
):
    """Character + pending + ferry/tribulation write block."""
    character = await gate.require_character(current_user)
    await gate.resolve_pending_before_play(character)
    gate.assert_lifecycle_write(character, write_zh="研究室")
    return character


@router.get("/catalog", response_model=None)
async def research_catalog(
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Materials, affix pool, and Chinese help."""
    _ = current_user
    return success(service.get_catalog())


@router.get("/mine", response_model=None)
async def research_mine(
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Finalized private content owned by the character."""
    character = await gate.require_character(current_user)
    items = await service.list_mine(character)
    return success({"items": items})


@router.get("/sessions", response_model=None)
async def research_list_open_sessions(
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """In-progress drafts for the hall 「继续草案」 button."""
    character = await gate.require_character(current_user)
    items = await service.list_open_sessions(character)
    return success({"items": items})


@router.post("/sessions", response_model=None)
async def research_create_session(
    payload: ResearchCreateRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a research session (PlayGate)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.create_session(
        character,
        kind=payload.kind,
        materials=payload.materials,
        spends=payload.spends,
        effect_id=payload.effect_id,
    )
    return success(data)


@router.get("/sessions/{session_id}", response_model=None)
async def research_get_session(
    session_id: int,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Session status + preview."""
    character = await gate.require_character(current_user)
    data = await service.get_session(character, session_id)
    return success(data)


@router.post("/sessions/{session_id}/reroll", response_model=None)
async def research_reroll(
    session_id: int,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reroll affixes (extra materials)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.reroll_session(character, session_id)
    return success(data)


@router.post("/sessions/{session_id}/draft", response_model=None)
async def research_save_draft(
    session_id: int,
    payload: ResearchFormationDraftRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Save formation or talisman draft (PlayGate)."""
    character = await _prepare_research_write(gate, current_user)
    if payload.effect_id:
        data = await service.save_talisman_draft(
            character,
            session_id,
            payload.effect_id,
        )
    else:
        data = await service.save_formation_draft(
            character,
            session_id,
            payload.blueprint,
        )
    return success(data)


@router.post("/sessions/{session_id}/finalize", response_model=None)
async def research_finalize(
    session_id: int,
    payload: ResearchFinalizeRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Name and freeze the draft."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.finalize_session(
        character,
        session_id=session_id,
        label_zh=payload.label_zh,
    )
    return success(data)


@router.post("/sessions/{session_id}/submit-review", response_model=None)
async def research_submit_review(
    session_id: int,
    gate: PlayGate = Depends(get_play_gate),
    service: ResearchService = Depends(get_research_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Review pool placeholder (40210)."""
    character = await _prepare_research_write(gate, current_user)
    await service.submit_review(character, session_id=session_id)
    return success({})


@router.get("/technique/drafts", response_model=None)
async def technique_list_drafts(
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Active technique-craft drafts (abandoned omitted)."""
    character = await gate.require_character(current_user)
    items = await service.list_drafts(character)
    return success({"items": items})


@router.post("/technique/drafts", response_model=None)
async def technique_create_draft(
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Open an empty technique draft. Does not consume cards."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.create_draft(character)
    return success(data)


@router.post("/technique/drafts/{draft_id}/abandon", response_model=None)
async def technique_abandon_draft(
    draft_id: int,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Abandon a draft (phase=abandoned). Embedded cards are not refunded."""
    character = await _prepare_research_write(gate, current_user)
    await service.abandon_draft(character, draft_id)
    return success({})


@router.post("/technique/drafts/{draft_id}/embed", response_model=None)
async def technique_embed_card(
    draft_id: int,
    payload: TechniqueEmbedRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Embed a formal element or efficacy card (may fail; card is always consumed)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.embed_card(character, draft_id, payload.item_uid)
    return success(data)


@router.post("/technique/drafts/{draft_id}/conditions", response_model=None)
async def technique_set_conditions(
    draft_id: int,
    payload: TechniqueConditionsRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Confirm launch conditions. Both boxes may be empty."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.set_conditions(
        character,
        draft_id,
        element_limit=payload.element_limit,
        weapon_limit=payload.weapon_limit,
    )
    return success(data)


@router.post("/technique/drafts/{draft_id}/affix/roll", response_model=None)
async def technique_roll_affix(
    draft_id: int,
    payload: TechniqueAffixSlotRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate three affix options for one slot (no resource cost)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.roll_affix(character, draft_id, payload.slot)
    return success(data)


@router.post("/technique/drafts/{draft_id}/affix/choose", response_model=None)
async def technique_choose_affix(
    draft_id: int,
    payload: TechniqueAffixChooseRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lock one of the three rolled affix options."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.choose_affix(
        character,
        draft_id,
        payload.slot,
        payload.affix_id,
    )
    return success(data)


@router.post("/technique/drafts/{draft_id}/affix/reroll", response_model=None)
async def technique_reroll_affix(
    draft_id: int,
    payload: TechniqueAffixSlotRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pay reroll cost, clear levels, and draw three new affix options."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.reroll_affix(character, draft_id, payload.slot)
    return success(data)


@router.post("/technique/drafts/{draft_id}/finalize", response_model=None)
async def technique_finalize_draft(
    draft_id: int,
    payload: TechniqueFinalizeRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Name and freeze a ready draft onto the learned list."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.finalize_draft(character, draft_id, payload.label_zh)
    return success(data)


@router.post("/technique/techniques/{technique_id}/base-upgrade", response_model=None)
async def technique_upgrade_base(
    technique_id: str,
    payload: TechniqueBaseUpgradeRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Spend one base-upgrade click (attack / defense / speed) on an original technique."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.upgrade_base(character, technique_id, payload.stat)
    return success(data)


@router.post("/technique/techniques/{technique_id}/affix-upgrade", response_model=None)
async def technique_upgrade_affix(
    technique_id: str,
    payload: TechniqueAffixUpgradeRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pay and roll an affix upgrade; failure still charges."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.upgrade_affix(character, technique_id, payload.slot)
    return success(data)


@router.post("/technique/techniques/{technique_id}/affix/roll", response_model=None)
async def technique_cultivate_roll_affix(
    technique_id: str,
    payload: TechniqueAffixSlotRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Roll three options for an empty cultivate affix slot (breakthrough pad)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.roll_cultivate_affix(character, technique_id, payload.slot)
    return success(data)


@router.post("/technique/techniques/{technique_id}/affix/choose", response_model=None)
async def technique_cultivate_choose_affix(
    technique_id: str,
    payload: TechniqueAffixChooseRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Lock one rolled option onto an empty cultivate affix slot."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.choose_cultivate_affix(
        character,
        technique_id,
        payload.slot,
        payload.affix_id,
    )
    return success(data)


@router.post("/technique/techniques/{technique_id}/affix/reroll", response_model=None)
async def technique_cultivate_reroll_affix(
    technique_id: str,
    payload: TechniqueAffixSlotRequest,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pay and redraw options on an empty cultivate affix slot."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.reroll_cultivate_affix(character, technique_id, payload.slot)
    return success(data)


@router.post("/technique/techniques/{technique_id}/breakthrough", response_model=None)
async def technique_breakthrough(
    technique_id: str,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Spend breakthrough resources and roll rank-up; points are never deducted."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.breakthrough(character, technique_id)
    return success(data)


@router.post("/technique/techniques/{technique_id}/print-manual", response_model=None)
async def technique_print_manual(
    technique_id: str,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Print the current original-technique snapshot as an unstacked inventory manual."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.print_manual(character, technique_id)
    return success(data)


@router.post("/technique/techniques/{technique_id}/abolish", response_model=None)
async def technique_abolish(
    technique_id: str,
    gate: PlayGate = Depends(get_play_gate),
    service: TechniqueCraftService = Depends(get_technique_craft_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Abolish an original technique (must unequip first; copies remain)."""
    character = await _prepare_research_write(gate, current_user)
    data = await service.abolish_technique(character, technique_id)
    return success(data)
