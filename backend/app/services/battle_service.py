"""
极简 PVE：境界战力 vs 怪物数值对撞 + 文字战报（M1）。

玩家先手；无暴击；超 max_rounds 判怪物胜。
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc
from app.db.models.user import User
from app.schemas.common import AppError
from app.services import character_service
from app.services.idle_service import settle_idle
from app.services.play_gate import PlayGate
from app.services.realm_config import get_current_stage, get_game_config

logger = logging.getLogger(__name__)


class BattleService:
    """
    Application service for player-vs-environment combat (M1 tutorial PVE).

    Orchestrates play-gate settlement, combat stat resolution, round simulation,
    reward application, and character envelope serialization.

    Attributes:
        _session: Request-scoped async SQLAlchemy session.
        _gate: Cross-play precondition gate (character load + pending claim).
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize the battle service with a database session.

        Args:
            session: Async SQLAlchemy session bound to the current request.
        """
        self._session = session
        self._gate = PlayGate(session)

    async def start_pve_battle(
        self,
        user: User,
        monster_id: str = "tutorial_slime",
        now: datetime | None = None,
    ) -> dict:
        """
        Start a tutorial PVE encounter: settle → validate → round combat → rewards.

        Args:
            user: Authenticated user owning the character.
            monster_id: Monster configuration key; defaults to ``tutorial_slime``.
            now: Optional frozen UTC timestamp for deterministic tests.

        Returns:
            dict: Battle response payload with result, rounds, rewards, and character.

        Raises:
            AppError: ``40022`` state mutex; ``40025`` unknown monster; ``40026`` missing stage config.
        """
        character = await self._gate.require_character(user)
        current_time = now_utc(now)
        await self._gate.resolve_pending_before_play(character, now=current_time)
        settle_idle(character, now=current_time)

        if character.status != "normal":
            raise AppError(code=40022, message="进阶中不可开战", http_status=409)

        # 修炼中（方向非 none）禁止开战，需先停止修炼
        if character.idle_direction != "none":
            raise AppError(
                code=40022,
                message="修炼中不可开战，请先停止修炼",
                http_status=409,
            )

        monsters = get_game_config().monsters
        monster = monsters.get(monster_id)
        if monster is None:
            raise AppError(code=40025, message="怪物不存在或未开放", http_status=404)

        stage = get_current_stage(character.major_realm, character.realm_stage)
        if stage is None:
            raise AppError(code=40026, message="当前境界配置缺失，无法开战", http_status=400)

        # 与角色面板一致：品阶 × 境界底 + 功法/体质加算
        player_atk, player_hp, _, _ = await character_service.build_combat_stats(
            self._session,
            character,
        )
        monster_atk = monster.atk
        monster_hp = monster.hp
        # 回合内可变血量副本（战力底数不变）
        current_player_hp = player_hp
        current_monster_hp = monster_hp

        rounds: list[dict] = []
        result = "lose"
        # 玩家先手
        for round_index in range(1, monster.max_rounds + 1):
            # 玩家攻击
            current_monster_hp = max(0, current_monster_hp - player_atk)
            rounds.append(
                {
                    "round": round_index,
                    "actor": "player",
                    "action": "attack",
                    "damage": player_atk,
                    "attacker_hp_after": current_player_hp,
                    "defender_hp_after": current_monster_hp,
                    "text": f"你对{monster.name}造成 {player_atk} 点伤害",
                }
            )
            if current_monster_hp <= 0:
                result = "win"
                break

            # 怪物攻击
            current_player_hp = max(0, current_player_hp - monster_atk)
            rounds.append(
                {
                    "round": round_index,
                    "actor": "monster",
                    "action": "attack",
                    "damage": monster_atk,
                    "attacker_hp_after": current_monster_hp,
                    "defender_hp_after": current_player_hp,
                    "text": f"{monster.name}对你造成 {monster_atk} 点伤害",
                }
            )
            if current_player_hp <= 0:
                result = "lose"
                break
        else:
            # 超过 max_rounds 且双方都活着：判怪物胜
            result = "lose"

        rewards_src = monster.rewards_on_win if result == "win" else monster.rewards_on_lose
        rewards = {
            "cultivation_points": rewards_src.cultivation_points,
            "spirit_stones": rewards_src.spirit_stones,
        }
        character.cultivation_points = int(character.cultivation_points) + rewards["cultivation_points"]
        character.spirit_stones = int(character.spirit_stones) + rewards["spirit_stones"]
        character.updated_at = current_time
        await self._session.flush()
        await self._session.refresh(character)

        logger.info(
            "pve battle character_id=%s monster=%s result=%s rounds=%s atk=%s",
            character.id,
            monster_id,
            result,
            len(rounds),
            player_atk,
        )

        public = await character_service.enrich_character_public(self._session, character)
        return {
            "result": result,
            "monster_id": monster_id,
            "monster_name": monster.name,
            "rounds": rounds,
            "rewards": rewards,
            "character": character_service.character_public_to_dict(public),
        }


# ---------------------------------------------------------------------------
# Module-level wrappers (backward-compatible for tests and legacy imports)
# ---------------------------------------------------------------------------


async def start_pve_battle(
    session: AsyncSession,
    user: User,
    monster_id: str = "tutorial_slime",
    now: datetime | None = None,
) -> dict:
    """
    Module wrapper delegating to ``BattleService.start_pve_battle``.

    Args:
        session: DB session.
        user: Current user.
        monster_id: Monster key; default ``tutorial_slime``.
        now: Optional frozen UTC time.

    Returns:
        dict: Battle response data.
    """
    return await BattleService(session).start_pve_battle(
        user,
        monster_id=monster_id,
        now=now,
    )
