"""
PET-D05 灵宠回合制对战纯函数引擎（零 board / autochess 依赖）。

选招 → 比速（含 priority）→ 命中/伤害 → 胜负；RNG 由传入 seed 驱动可复现。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class DuelSkill:
    """对战用技能快照。"""

    skill_id: str
    name: str
    power: int
    accuracy: int
    category: str
    priority: int
    pp: int


@dataclass
class DuelFighter:
    """对战一方出战宠快照。"""

    side: str  # player | foe
    name: str
    max_hp: int
    hp: int
    atk: int
    speed: int
    skills: list[DuelSkill] = field(default_factory=list)
    pp_left: dict[str, int] = field(default_factory=dict)
    # status 占位：defend 本回合减伤
    defending: bool = False

    def to_public(self) -> dict[str, Any]:
        """API 展示。"""
        return {
            "side": self.side,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "atk": self.atk,
            "speed": self.speed,
            "defending": self.defending,
            "skills": [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "power": s.power,
                    "accuracy": s.accuracy,
                    "category": s.category,
                    "priority": s.priority,
                    "pp": s.pp,
                    "pp_left": int(self.pp_left.get(s.skill_id, s.pp)),
                }
                for s in self.skills
            ],
        }


@dataclass
class DuelState:
    """整场对战权威状态。"""

    duel_id: str
    seed: int
    round_index: int
    max_rounds: int
    player: DuelFighter
    foe: DuelFighter
    finished: bool = False
    winner: str | None = None  # player | foe | draw
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        """不含内部细节的公共快照。"""
        return {
            "duel_id": self.duel_id,
            "seed": self.seed,
            "round_index": self.round_index,
            "max_rounds": self.max_rounds,
            "finished": self.finished,
            "winner": self.winner,
            "player": self.player.to_public(),
            "foe": self.foe.to_public(),
            "events": list(self.events),
        }


def build_struggle(cfg: Mapping[str, Any]) -> DuelSkill:
    """从 pet_duel.default_struggle 构建挣扎技能。"""
    return DuelSkill(
        skill_id=str(cfg.get("skill_id", "skill_struggle")),
        name=str(cfg.get("name", "挣扎")),
        power=int(cfg.get("power", 25)),
        accuracy=int(cfg.get("accuracy", 100)),
        category=str(cfg.get("category", "physical")),
        priority=int(cfg.get("priority", 0)),
        pp=int(cfg.get("pp", 99)),
    )


def fighter_from_stats(
    *,
    side: str,
    name: str,
    atk: int,
    hp: int,
    speed: int,
    skills: Sequence[DuelSkill],
    struggle: DuelSkill,
) -> DuelFighter:
    """由面板与技能列表组装出战方；无技能则带挣扎。"""
    skill_list = list(skills) if skills else [struggle]
    pp = {s.skill_id: int(s.pp) for s in skill_list}
    return DuelFighter(
        side=side,
        name=name,
        max_hp=max(1, int(hp)),
        hp=max(1, int(hp)),
        atk=max(1, int(atk)),
        speed=max(1, int(speed)),
        skills=skill_list,
        pp_left=pp,
    )


def _skill_by_id(fighter: DuelFighter, skill_id: str | None, struggle: DuelSkill) -> DuelSkill:
    """解析选招；非法/空 PP 回落挣扎。"""
    if skill_id:
        for skill in fighter.skills:
            if skill.skill_id == skill_id:
                left = int(fighter.pp_left.get(skill.skill_id, 0))
                if left > 0:
                    return skill
                break
    # 挣扎：确保在列表中
    for skill in fighter.skills:
        if skill.skill_id == struggle.skill_id:
            return skill
    fighter.skills.append(struggle)
    fighter.pp_left[struggle.skill_id] = struggle.pp
    return struggle


def _order_sides(
    player: DuelFighter,
    foe: DuelFighter,
    player_skill: DuelSkill,
    foe_skill: DuelSkill,
    *,
    seed: int,
    round_index: int,
) -> list[tuple[str, DuelFighter, DuelSkill, DuelFighter]]:
    """
    决定出手顺序：(side, actor, skill, target)。

    先比 priority，再比 speed；同速用 seed+round 奇偶（可复现）。
    """
    p_key = (int(player_skill.priority), int(player.speed))
    f_key = (int(foe_skill.priority), int(foe.speed))
    if p_key > f_key:
        first = ("player", player, player_skill, foe)
        second = ("foe", foe, foe_skill, player)
    elif f_key > p_key:
        first = ("foe", foe, foe_skill, player)
        second = ("player", player, player_skill, foe)
    else:
        # 同速同先制：seed_parity
        player_first = ((int(seed) + int(round_index)) % 2) == 0
        if player_first:
            first = ("player", player, player_skill, foe)
            second = ("foe", foe, foe_skill, player)
        else:
            first = ("foe", foe, foe_skill, player)
            second = ("player", player, player_skill, foe)
    return [first, second]


def _calc_damage(
    actor: DuelFighter,
    target: DuelFighter,
    skill: DuelSkill,
    rng: random.Random,
    *,
    damage_divisor: float,
    roll_min: float,
    roll_max: float,
) -> int:
    """物理/特殊伤害；status 返回 0。"""
    if skill.category == "status":
        return 0
    raw = float(actor.atk) * float(skill.power) / max(1.0, float(damage_divisor))
    roll = rng.uniform(float(roll_min), float(roll_max))
    dmg = max(1, int(math.floor(raw * roll)))
    if target.defending:
        dmg = max(1, dmg // 2)
    return dmg


def resolve_turn(
    state: DuelState,
    *,
    player_skill_id: str | None,
    foe_skill_id: str | None,
    struggle: DuelSkill,
    duel_cfg: Mapping[str, Any],
) -> DuelState:
    """
    结算一整回合；就地更新 state 并追加 events。

    参数:
        state: 当前对战状态。
        player_skill_id: 玩家选招。
        foe_skill_id: 敌方选招（NPC AI 已选）。
        struggle: 默认挣扎。
        duel_cfg: pet_duel.yaml 根配置。
    """
    if state.finished:
        return state

    state.round_index += 1
    # 回合开始清除上回合防御
    state.player.defending = False
    state.foe.defending = False

    turn_seed = int(state.seed) * 1_000_003 + int(state.round_index)
    rng = random.Random(turn_seed)

    p_skill = _skill_by_id(state.player, player_skill_id, struggle)
    f_skill = _skill_by_id(state.foe, foe_skill_id, struggle)

    events: list[dict[str, Any]] = [
        {
            "type": "round_start",
            "round": state.round_index,
            "player_choice": p_skill.skill_id,
            "foe_choice": f_skill.skill_id,
        },
    ]

    order = _order_sides(
        state.player,
        state.foe,
        p_skill,
        f_skill,
        seed=state.seed,
        round_index=state.round_index,
    )

    accuracy_enabled = bool(duel_cfg.get("accuracy_enabled", True))
    divisor = float(duel_cfg.get("damage_divisor", 50))
    roll_min = float(duel_cfg.get("damage_roll_min", 0.85))
    roll_max = float(duel_cfg.get("damage_roll_max", 1.0))

    for side, actor, skill, target in order:
        if state.finished or actor.hp <= 0 or target.hp <= 0:
            break
        # 扣 PP
        left = int(actor.pp_left.get(skill.skill_id, 0))
        actor.pp_left[skill.skill_id] = max(0, left - 1)

        events.append(
            {
                "type": "move",
                "side": side,
                "actor": actor.name,
                "skill_id": skill.skill_id,
                "skill_name": skill.name,
                "priority": skill.priority,
            },
        )

        # 命中
        hit = True
        if accuracy_enabled and int(skill.accuracy) < 100:
            roll = rng.randint(1, 100)
            hit = roll <= int(skill.accuracy)
            if not hit:
                events.append(
                    {
                        "type": "miss",
                        "side": side,
                        "skill_id": skill.skill_id,
                        "roll": roll,
                        "accuracy": skill.accuracy,
                    },
                )
                continue

        if skill.category == "status":
            # 最小 status：护体类 → defending
            actor.defending = True
            events.append(
                {
                    "type": "status",
                    "side": side,
                    "effect": "defend",
                    "skill_id": skill.skill_id,
                },
            )
            continue

        dmg = _calc_damage(
            actor,
            target,
            skill,
            rng,
            damage_divisor=divisor,
            roll_min=roll_min,
            roll_max=roll_max,
        )
        target.hp = max(0, int(target.hp) - dmg)
        events.append(
            {
                "type": "damage",
                "side": side,
                "target_side": target.side,
                "damage": dmg,
                "target_hp": target.hp,
                "skill_id": skill.skill_id,
            },
        )
        if target.hp <= 0:
            state.finished = True
            state.winner = side
            events.append({"type": "faint", "side": target.side, "name": target.name})
            events.append({"type": "battle_end", "winner": side})
            break

    if not state.finished and state.round_index >= int(state.max_rounds):
        state.finished = True
        # 比剩余 HP 比例
        p_ratio = state.player.hp / max(1, state.player.max_hp)
        f_ratio = state.foe.hp / max(1, state.foe.max_hp)
        if p_ratio > f_ratio:
            state.winner = "player"
        elif f_ratio > p_ratio:
            state.winner = "foe"
        else:
            state.winner = "draw"
        events.append(
            {
                "type": "battle_end",
                "winner": state.winner,
                "reason": "max_rounds",
            },
        )

    state.events.extend(events)
    return state


def pick_npc_skill(foe: DuelFighter, rng: random.Random, struggle: DuelSkill) -> str:
    """NPC：在仍有 PP 的技能中均匀抽取；否则挣扎。"""
    usable = [
        s.skill_id
        for s in foe.skills
        if int(foe.pp_left.get(s.skill_id, 0)) > 0
    ]
    if not usable:
        return struggle.skill_id
    return rng.choice(usable)


def auto_resolve_to_end(
    state: DuelState,
    *,
    struggle: DuelSkill,
    duel_cfg: Mapping[str, Any],
    player_policy: str = "first_usable",
) -> DuelState:
    """
    用确定性策略打完（验收 seed 复现）。

    player_policy:
        first_usable — 始终选第一个有 PP 的技能。
    """
    while not state.finished:
        rng = random.Random(int(state.seed) * 17 + state.round_index + 1)
        # 玩家策略
        if player_policy == "first_usable":
            p_choice = None
            for s in state.player.skills:
                if int(state.player.pp_left.get(s.skill_id, 0)) > 0:
                    p_choice = s.skill_id
                    break
        else:
            p_choice = pick_npc_skill(state.player, rng, struggle)
        f_choice = pick_npc_skill(state.foe, rng, struggle)
        resolve_turn(
            state,
            player_skill_id=p_choice,
            foe_skill_id=f_choice,
            struggle=struggle,
            duel_cfg=duel_cfg,
        )
    return state
