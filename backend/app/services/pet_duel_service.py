"""
PET-D05 灵宠对战应用服务：NPC 开战 / 回合选招 / 自动结算；内存会话。
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.domain.pet_duel import (
    DuelSkill,
    DuelState,
    auto_resolve_to_end,
    build_struggle,
    fighter_from_stats,
    pick_npc_skill,
    resolve_turn,
)
from app.domain.pet_rules import combat_stats_from_level, species_base_dict
from app.schemas.common import AppError
from app.services.m4_features import require_pets_enabled
from app.services.pet_service import PetService
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


@dataclass
class _DuelSession:
    """内存对战会话。"""

    character_id: int
    pet_id: int
    state: DuelState
    created_at: float = field(default_factory=time.time)


class PetDuelSessionStore:
    """进程内对战会话（个人版足够；多 worker 后置）。"""

    _lock = threading.Lock()
    _sessions: dict[str, _DuelSession] = {}

    @classmethod
    def put(cls, session: _DuelSession) -> None:
        """写入会话。"""
        with cls._lock:
            cls._sessions[session.state.duel_id] = session

    @classmethod
    def get(cls, duel_id: str) -> _DuelSession | None:
        """读取会话。"""
        with cls._lock:
            return cls._sessions.get(duel_id)

    @classmethod
    def remove(cls, duel_id: str) -> None:
        """删除会话。"""
        with cls._lock:
            cls._sessions.pop(duel_id, None)


class PetDuelService:
    """
    灵宠 vs NPC 回合制对战。

    属性:
        _session: DB 会话（读宠面板）。
        _pets: PetService。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定请求级会话。"""
        self._session = session
        self._pets = PetService(session)

    def _struggle(self) -> Any:
        """配置中的挣扎技能。"""
        return build_struggle(get_game_config().pet_duel.default_struggle)

    def _skill_snap(self, skill_id: str) -> DuelSkill | None:
        """配置技能 → DuelSkill。"""
        cfg = get_game_config().pet_skills.skills.get(skill_id)
        if cfg is None:
            return None
        return DuelSkill(
            skill_id=cfg.skill_id,
            name=cfg.name,
            power=cfg.power,
            accuracy=cfg.accuracy,
            category=cfg.category,
            priority=cfg.priority,
            pp=cfg.pp,
        )

    def _skills_from_ids(self, skill_ids: list[str | None]) -> list[DuelSkill]:
        """装备 id 列表 → 技能快照（跳过空/未知）。"""
        out: list[DuelSkill] = []
        for sid in skill_ids:
            if not sid:
                continue
            snap = self._skill_snap(str(sid))
            if snap is not None:
                out.append(snap)
        return out

    def _npc_fighter(self, npc_id: str) -> Any:
        """按模板组装敌方。"""
        bundle = get_game_config()
        duel_cfg = bundle.pet_duel
        npc = duel_cfg.npc_templates.get(npc_id)
        if npc is None:
            raise AppError(code=40063, message=f"未知 NPC：{npc_id}", http_status=400)
        species = bundle.pets.species.get(npc.species_id)
        if species is None:
            raise AppError(code=40000, message="NPC 物种缺失", http_status=400)
        grade_cfg = bundle.pets.grades.get(npc.grade)
        grade_mult = float(grade_cfg.base_mult) if grade_cfg else 1.0
        stats = combat_stats_from_level(
            species_base_dict(species),
            npc.level,
            level_stat_bonus=bundle.pets.level_stat_bonus,
            grade_base_mult=grade_mult,
        )
        skill_ids = list(npc.skill_ids)
        if not skill_ids:
            pool = bundle.pet_skills.pools.get(species.skill_pool_id)
            if pool:
                skill_ids = list(pool.default_equipped)
        skills = self._skills_from_ids(skill_ids)
        return fighter_from_stats(
            side="foe",
            name=npc.name,
            atk=stats["atk"],
            hp=stats["hp"],
            speed=stats["speed"],
            skills=skills,
            struggle=self._struggle(),
        )

    async def _player_fighter(self, character: Character, pet_id: int) -> tuple[Any, int]:
        """读玩家宠组装出战方。"""
        pet = await self._pets._get_owned_pet(character.id, pet_id)
        stats = self._pets._stats_for_pet(pet)
        public = self._pets._pet_to_public(pet)
        skills = self._skills_from_ids(list(public.get("skills", {}).get("equipped_ids") or []))
        name = public.get("nickname") or public.get("species_name") or pet.species_id
        fighter = fighter_from_stats(
            side="player",
            name=str(name),
            atk=stats["atk"],
            hp=stats["hp"],
            speed=stats["speed"],
            skills=skills,
            struggle=self._struggle(),
        )
        return fighter, int(pet.id)

    def _duel_cfg_dict(self) -> dict[str, Any]:
        """引擎所需配置子集。"""
        cfg = get_game_config().pet_duel
        return {
            "max_rounds": cfg.max_rounds,
            "damage_divisor": cfg.damage_divisor,
            "damage_roll_min": cfg.damage_roll_min,
            "damage_roll_max": cfg.damage_roll_max,
            "accuracy_enabled": cfg.accuracy_enabled,
            "speed_tie_break": cfg.speed_tie_break,
            "default_struggle": cfg.default_struggle,
        }

    async def start_npc(
        self,
        character: Character,
        *,
        pet_id: int,
        npc_id: str | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        开启 vs NPC 对战。

        异常:
            AppError: 宠不存在 / NPC 未知。
        """
        require_pets_enabled()
        duel_cfg = get_game_config().pet_duel
        resolved_npc = (npc_id or "").strip() or next(iter(duel_cfg.npc_templates), "")
        if not resolved_npc:
            raise AppError(code=40063, message="无可用 NPC 模板", http_status=400)
        player, owned_pet_id = await self._player_fighter(character, pet_id)
        foe = self._npc_fighter(resolved_npc)
        duel_seed = int(seed) if seed is not None else secrets.randbelow(2**31 - 1)
        duel_id = f"duel_{character.id}_{secrets.token_hex(6)}"
        state = DuelState(
            duel_id=duel_id,
            seed=duel_seed,
            round_index=0,
            max_rounds=int(duel_cfg.max_rounds),
            player=player,
            foe=foe,
            events=[
                {
                    "type": "battle_start",
                    "npc_id": resolved_npc,
                    "seed": duel_seed,
                    "player_pet_id": owned_pet_id,
                },
            ],
        )
        PetDuelSessionStore.put(
            _DuelSession(character_id=character.id, pet_id=owned_pet_id, state=state),
        )
        logger.info(
            "pet duel start character_id=%s duel_id=%s npc=%s seed=%s",
            character.id,
            duel_id,
            resolved_npc,
            duel_seed,
        )
        return {
            "duel_id": duel_id,
            "npc_id": resolved_npc,
            "seed": duel_seed,
            "state": state.to_public(),
        }

    async def get_duel(self, character: Character, duel_id: str) -> dict[str, Any]:
        """读取对战快照。"""
        require_pets_enabled()
        sess = PetDuelSessionStore.get(duel_id)
        if sess is None or sess.character_id != character.id:
            raise AppError(code=40421, message="对战不存在或已结束", http_status=404)
        return {"state": sess.state.to_public()}

    async def turn(
        self,
        character: Character,
        duel_id: str,
        *,
        skill_id: str | None,
    ) -> dict[str, Any]:
        """
        提交玩家选招并结算一回合（NPC 自动选招）。

        异常:
            AppError: 对战不存在 / 已结束。
        """
        require_pets_enabled()
        sess = PetDuelSessionStore.get(duel_id)
        if sess is None or sess.character_id != character.id:
            raise AppError(code=40421, message="对战不存在或已结束", http_status=404)
        if sess.state.finished:
            raise AppError(code=40064, message="对战已结束", http_status=400)

        import random

        struggle = self._struggle()
        cfg = self._duel_cfg_dict()
        rng = random.Random(int(sess.state.seed) * 31 + sess.state.round_index + 7)
        foe_choice = pick_npc_skill(sess.state.foe, rng, struggle)
        before_len = len(sess.state.events)
        resolve_turn(
            sess.state,
            player_skill_id=skill_id,
            foe_skill_id=foe_choice,
            struggle=struggle,
            duel_cfg=cfg,
        )
        new_events = sess.state.events[before_len:]
        if sess.state.finished:
            # 保留会话片刻供 GET；也可立即 remove —— 保留至下次 start 覆盖
            pass
        return {
            "state": sess.state.to_public(),
            "turn_events": new_events,
            "finished": sess.state.finished,
            "winner": sess.state.winner,
        }

    async def auto_npc(
        self,
        character: Character,
        *,
        pet_id: int,
        npc_id: str | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """
        一键自动打完（seed 可复现验收）。

        返回完整战报 events。
        """
        started = await self.start_npc(
            character,
            pet_id=pet_id,
            npc_id=npc_id,
            seed=seed,
        )
        sess = PetDuelSessionStore.get(started["duel_id"])
        assert sess is not None
        auto_resolve_to_end(
            sess.state,
            struggle=self._struggle(),
            duel_cfg=self._duel_cfg_dict(),
            player_policy="first_usable",
        )
        report = {
            "schema_version": 1,
            "mode": "pet_duel_npc",
            "duel_id": sess.state.duel_id,
            "seed": sess.state.seed,
            "winner": sess.state.winner,
            "rounds": sess.state.round_index,
            "events": list(sess.state.events),
            "player": sess.state.player.to_public(),
            "foe": sess.state.foe.to_public(),
        }
        logger.info(
            "pet duel auto character_id=%s duel_id=%s winner=%s rounds=%s",
            character.id,
            sess.state.duel_id,
            sess.state.winner,
            sess.state.round_index,
        )
        return {"report": report, "state": sess.state.to_public()}
