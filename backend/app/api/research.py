"""Research desk HTTP routes (mounted at /cave/lab; /research is a compat alias)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_play_gate, get_research_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.research import (
    ResearchCreateRequest,
    ResearchFinalizeRequest,
    ResearchFormationDraftRequest,
)
from app.services.play_gate import PlayGate
from app.services.research_service import ResearchService

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
