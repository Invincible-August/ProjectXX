"""
自走棋战斗编排服务（M3战斗成型设计.md §7～§9 · S3/S6）。

职责（服务层只编排、不演算）：
    P0 门禁：角色态 / 修炼互斥 / pending 清算 / 体力扣减（单角色事务内）；
    P1 组装：进攻阵（预设 + 权威战力）+ 防守阵（怪配置 / 对方快照）→ 纯数据 setup；
    P2 演算：调用 ``domain.autochess.simulate_battle``（纯 CPU，可复现）；
    P3 结算：奖励入账 + 战报渲染（零持久化，整包随响应返回）。
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc
from app.db.models.avatar import Avatar
from app.db.models.character import Character
from app.db.models.user import User
from app.domain.autochess import simulate_battle
from app.domain.battle_presentation import BattleKind, BattlePlaybackPolicy
from app.domain.battle_text import render_board, render_detailed, render_summary
from app.domain.env_modifiers import combine_env_multipliers, lookup_modifier
from app.schemas.common import AppError
from app.domain.divine_sense import apply_overload_mult
from app.services.pet_service import PetService
from app.services.avatar_service import AvatarService
from app.services.character_service import CharacterService
from app.services.formation_service import FormationService
from app.services.idle_service import settle_idle
from app.services.play_gate import PlayGate
from app.services.realm_config import BoardConfig, MonsterConfig, get_game_config
from app.services.snapshot_service import SnapshotService
from app.services.stamina_service import StaminaService

logger = logging.getLogger(__name__)


class AutochessService:
    """
    自走棋战斗用例：PVE 讨伐与 PVP 攻打快照。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session
        self._gate = PlayGate(session)
        self._characters = CharacterService(session)
        self._formations = FormationService(session)
        self._snapshots = SnapshotService(session)
        self._stamina = StaminaService(session)

    # ------------------------------------------------------------------
    # 公开查询（只读配置派生，无 DB）
    # ------------------------------------------------------------------

    @staticmethod
    def list_pve_monsters_public() -> list[dict[str, Any]]:
        """
        组装 PVE 选怪列表（体力、编成规模、嘲讽光环摘要）。

        Returns:
            可供 ``GET /battle/pve/monsters`` 直接下发的 dict 列表。
        """
        cfg = get_game_config()
        default_cost = int(cfg.stamina.costs.get("battle_pve", 0))
        catalog = cfg.taunt_auras
        rows: list[dict[str, Any]] = []
        for monster in cfg.monsters.values():
            cost = (
                monster.stamina_cost
                if monster.stamina_cost is not None
                else default_cost
            )
            rows.append(
                {
                    "monster_id": monster.monster_id,
                    "name": monster.name,
                    "stamina_cost": cost,
                    "unit_count": len(monster.units) or 1,
                    "rewards_on_win": {
                        "cultivation_points": monster.rewards_on_win.cultivation_points,
                        "spirit_stones": monster.rewards_on_win.spirit_stones,
                    },
                    # §0.7：编成内嘲讽光环中文摘要（无则空列表）
                    "taunt_auras": catalog.public_summaries_for_units(monster.units),
                },
            )
        return rows

    # ------------------------------------------------------------------
    # setup 组装（全部转为纯数据，维持引擎零依赖纪律）
    # ------------------------------------------------------------------

    @staticmethod
    def _board_plain(board: BoardConfig) -> dict[str, Any]:
        """``BoardConfig`` → 引擎入参 dict（含 env 回合上限覆盖）。"""
        settings = get_settings()
        max_rounds = (
            settings.battle_max_rounds
            if settings.battle_max_rounds > 0
            else board.max_rounds
        )
        return {
            "size": board.size,
            "max_rounds": max_rounds,
            "timeout_winner": board.timeout_winner,
            "dice_sides": board.dice_sides,
            "ap_per_turn": board.ap_per_turn,
            "land_move_points": board.land_move_points,
            "fly_move_points": board.fly_move_points,
            "hit_rates": dict(board.hit_rates),
            "damage_floor": board.damage_floor,
            "damage_dice_normalizer": board.damage_dice_normalizer,
            # 修为骰：伤害用中点归一（dice.yaml）
            "use_midpoint_normalizer": get_game_config().dice.use_midpoint_normalizer,
        }

    @staticmethod
    def _counters_plain() -> dict[str, Any]:
        """四象克制表 → 纯 dict（引擎按层查倍率）。"""
        cfg = get_game_config().formations
        return {
            "environment": cfg.environment_counters,
            "weather": cfg.weather_counters,
            "effect": cfg.effect_counters,
        }

    @staticmethod
    def _layer_catalogs_plain() -> dict[str, Any]:
        """四象内容目录快照（中文名 + combat）→ 引擎 setup。"""
        return get_game_config().formations.to_engine_catalogs()

    async def _attacker_units(
        self,
        character: Character,
        preset_units: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        用预设占位 + 权威战力组装进攻方（side=0）棋子列表。

        S1-2：经 Character 门面 ``on_battle_enter`` → ``seed_to_engine_unit``；
        数值口径与改前等价（品阶/功法/体质、傀儡比例、客串化身）。
        """
        from app.constants.battle import (
            BATTLE_SIDE_ATTACKER,
            DICE_PURPOSE_COMBAT_DAMAGE,
            PIECE_KIND_AVATAR,
            PIECE_KIND_MAIN,
            PIECE_KIND_PET,
            PIECE_KIND_PUPPET,
        )
        from app.game.battle.assemble import (
            build_scaled_puppet_seed,
            is_trial_puppet_uid,
            seed_to_engine_unit,
        )
        from app.game.character import AvatarCharacter, PetCharacter
        from app.services.avatar_repo import fetch_avatar_row

        board = get_game_config().board
        main_atk, main_hp, _, _ = await self._characters.build_combat_stats(character)
        player = await self._characters.build_player_character(character)

        pet_svc = PetService(self._session)
        avatar_row = await fetch_avatar_row(self._session, character.id)

        from app.services.dice_service import DiceService

        dice_svc = DiceService(self._session)
        char_bounds = await dice_svc.resolve_for_character(
            character,
            purpose=DICE_PURPOSE_COMBAT_DAMAGE,
        )
        dice_payload = DiceService.unit_dice_payload(char_bounds)

        units: list[dict[str, Any]] = []
        for unit in preset_units:
            kind = str(unit.get("unit_kind", PIECE_KIND_MAIN))
            defaults = board.unit_defaults.get(kind) or board.unit_defaults[PIECE_KIND_MAIN]
            x, y = int(unit["x"]), int(unit["y"])
            unit_uid = str(unit["unit_uid"])
            seed = None
            display_name: str | None = None

            if kind == PIECE_KIND_MAIN:
                seed = player.on_battle_enter(
                    unit_uid=unit_uid,
                    side="attacker",
                    x=x,
                    y=y,
                )
                display_name = character.name
            elif kind == PIECE_KIND_AVATAR:
                from app.services.avatar_assist_service import parse_guest_unit_uid

                guest_ids = parse_guest_unit_uid(unit_uid)
                if guest_ids is not None:
                    _owner_id, guest_avatar_id = guest_ids
                    guest_row = await self._session.get(Avatar, int(guest_avatar_id))
                    if guest_row is None:
                        raise AppError(code=40057, message="客串化身不存在", http_status=400)
                    owner_ch = await self._session.get(Character, int(_owner_id))
                    avatar_svc = AvatarService(self._session)
                    if owner_ch is not None:
                        stats = await avatar_svc.live_combat_stats(owner_ch, guest_row)
                    else:
                        stats = AvatarService.avatar_combat_stats(guest_row)
                    facade = AvatarCharacter.from_orm(
                        guest_row,
                        stats={
                            "hp": stats["hp"],
                            "phys_atk": stats["atk"],
                            "speed": defaults.speed,
                            "mp": 0,
                        },
                    )
                    seed = facade.on_battle_enter(
                        unit_uid=unit_uid,
                        side="attacker",
                        x=x,
                        y=y,
                    )
                    owner_label = owner_ch.name if owner_ch else str(_owner_id)
                    display_name = f"{owner_label}·{guest_row.name}"
                elif avatar_row is not None:
                    stats = await AvatarService(self._session).live_combat_stats(
                        character,
                        avatar_row,
                    )
                    facade = AvatarCharacter.from_orm(
                        avatar_row,
                        stats={
                            "hp": stats["hp"],
                            "phys_atk": stats["atk"],
                            "speed": defaults.speed,
                            "mp": 0,
                        },
                    )
                    seed = facade.on_battle_enter(
                        unit_uid=unit_uid,
                        side="attacker",
                        x=x,
                        y=y,
                    )
                    display_name = avatar_row.name
                else:
                    seed = build_scaled_puppet_seed(
                        unit_uid=unit_uid,
                        side="attacker",
                        x=x,
                        y=y,
                        main_atk=main_atk,
                        main_hp=main_hp,
                        atk_ratio=float(defaults.atk_ratio),
                        hp_ratio=float(defaults.hp_ratio),
                        speed=int(defaults.speed),
                        label_zh=kind,
                        ephemeral=False,
                    )
                    # 无化身时回退比例：kind 仍标 avatar（与旧行为一致）
                    seed.unit_kind = PIECE_KIND_AVATAR
                    display_name = kind
            elif kind == PIECE_KIND_PET and unit.get("ref_id") is not None:
                ref_id = int(unit["ref_id"])
                stats = await pet_svc.get_pet_stats(ref_id, character.id)
                from types import SimpleNamespace

                from app.db.models.pet import Pet

                pet_row = await self._session.get(Pet, ref_id)
                pet_obj = pet_row or SimpleNamespace(
                    id=ref_id,
                    species_id="pet",
                    nickname=None,
                )
                facade = PetCharacter.from_orm(
                    pet_obj,
                    stats={
                        "hp": stats["hp"],
                        "phys_atk": stats["atk"],
                        "speed": stats["speed"],
                        "mp": 0,
                    },
                )
                seed = facade.on_battle_enter(
                    unit_uid=unit_uid,
                    side="attacker",
                    x=x,
                    y=y,
                )
                display_name = f"pet_{ref_id}"
            elif kind == PIECE_KIND_PUPPET:
                ephemeral = is_trial_puppet_uid(unit_uid)
                if ephemeral:
                    label = "试炼木傀"
                    seed = build_scaled_puppet_seed(
                        unit_uid=unit_uid,
                        side="attacker",
                        x=x,
                        y=y,
                        main_atk=main_atk,
                        main_hp=main_hp,
                        atk_ratio=float(defaults.atk_ratio),
                        hp_ratio=float(defaults.hp_ratio),
                        speed=int(defaults.speed),
                        label_zh=label,
                        ephemeral=True,
                    )
                    display_name = label
                else:
                    from app.db.models.puppet_actor import PuppetActor
                    from app.game.battle.assemble import scale_atk_hp
                    from app.services.puppet_service import PuppetService

                    atk, hp = scale_atk_hp(
                        main_atk,
                        main_hp,
                        atk_ratio=float(defaults.atk_ratio),
                        hp_ratio=float(defaults.hp_ratio),
                    )
                    stats = {
                        "hp": hp,
                        "phys_atk": atk,
                        "speed": int(defaults.speed),
                        "mp": 0,
                    }
                    puppet_svc = PuppetService(self._session)
                    actor = None
                    ref_id = unit.get("ref_id")
                    if ref_id is not None:
                        actor = await self._session.get(PuppetActor, int(ref_id))
                    if actor is None:
                        # 兼容旧预设：unit_uid = item_uid
                        from app.constants.inventory import ITEM_TYPE_PUPPET
                        from app.db.models.inventory_item import InventoryItem

                        inv_row = (
                            await self._session.execute(
                                select(InventoryItem).where(
                                    InventoryItem.character_id == character.id,
                                    InventoryItem.item_uid == unit_uid,
                                    InventoryItem.item_type == ITEM_TYPE_PUPPET,
                                ),
                            )
                        ).scalar_one_or_none()
                        if inv_row is not None:
                            actor = await puppet_svc.ensure_for_inventory_item(inv_row)
                    if actor is not None:
                        facade = puppet_svc.build_character_from_actor(actor, stats=stats)
                        seed = facade.on_battle_enter(
                            unit_uid=unit_uid,
                            side="attacker",
                            x=x,
                            y=y,
                        )
                        display_name = facade.display_name
                    else:
                        seed = build_scaled_puppet_seed(
                            unit_uid=unit_uid,
                            side="attacker",
                            x=x,
                            y=y,
                            main_atk=main_atk,
                            main_hp=main_hp,
                            atk_ratio=float(defaults.atk_ratio),
                            hp_ratio=float(defaults.hp_ratio),
                            speed=int(defaults.speed),
                            label_zh="傀儡",
                            ephemeral=False,
                        )
                        display_name = "傀儡"
            else:
                seed = build_scaled_puppet_seed(
                    unit_uid=unit_uid,
                    side="attacker",
                    x=x,
                    y=y,
                    main_atk=main_atk,
                    main_hp=main_hp,
                    atk_ratio=float(defaults.atk_ratio),
                    hp_ratio=float(defaults.hp_ratio),
                    speed=int(defaults.speed),
                    label_zh=kind,
                    ephemeral=False,
                )
                seed.unit_kind = kind
                display_name = kind

            units.append(
                seed_to_engine_unit(
                    seed,
                    defaults=defaults,
                    dice_payload=dice_payload,
                    name=display_name,
                    side=BATTLE_SIDE_ATTACKER,
                ),
            )

        # 神识超载按装备栏（化身开关+灵宠槽+傀儡编成），与棋盘落子无关
        sense = await AvatarService(self._session).get_sense(character)
        settings = get_settings()
        if sense["load"] > sense["soft_cap"]:
            if settings.divine_sense_strict:
                mult = sense["overload_mult"]
                for idx, u in enumerate(units):
                    units[idx] = apply_overload_mult(u, mult)
                logger.info(
                    "divine sense overload applied character_id=%s load=%s mult=%s zone=%s",
                    character.id,
                    sense["load"],
                    mult,
                    sense.get("zone"),
                )
            else:
                logger.info(
                    "divine sense overload skipped (DIVINE_SENSE_STRICT=false) "
                    "character_id=%s load=%s",
                    character.id,
                    sense["load"],
                )
        return units

    @staticmethod
    def _monster_units(monster: MonsterConfig, board: BoardConfig) -> list[dict[str, Any]]:
        """
        怪侧（side=1）棋子列表。

        - 配置了 ``units``：坐标即绝对棋盘坐标（配置约定敌对半区）；
        - 旧式单体怪：回退为单棋子落防守锚点（默认锚 x 镜像 → (6,3)）。
        S1-2：经 MonsterCharacter.on_battle_enter 再转引擎 dict。
        """
        from app.constants.battle import (
            BATTLE_SIDE_DEFENDER,
            DICE_PURPOSE_COMBAT_DAMAGE,
            PIECE_KIND_MAIN,
            PIECE_KIND_MONSTER,
        )
        from app.game.battle.assemble import seed_to_engine_unit
        from app.game.character import MonsterCharacter
        from app.services.dice_service import DiceService

        monster_bounds = DiceService().monster_bounds(purpose=DICE_PURPOSE_COMBAT_DAMAGE)
        dice_payload = DiceService.unit_dice_payload(monster_bounds)
        if monster.units:
            catalog = get_game_config().taunt_auras
            result: list[dict[str, Any]] = []
            for u in monster.units:
                facade = MonsterCharacter.from_template(
                    u.unit_uid,
                    {
                        "label_zh": u.name,
                        "stats": {
                            "hp": u.hp,
                            "phys_atk": u.atk,
                            "speed": u.speed,
                            "mp": 0,
                        },
                    },
                )
                seed = facade.on_battle_enter(
                    unit_uid=u.unit_uid,
                    side="defender",
                    x=u.x,
                    y=u.y,
                )
                # 怪物 defaults：用配置行覆盖 attack_* / can_fly
                defaults = type(
                    "MonsterDefaults",
                    (),
                    {
                        "speed": u.speed,
                        "attack_range": u.attack_range,
                        "attack_kind": u.attack_kind,
                        "can_fly": u.can_fly,
                    },
                )()
                row = seed_to_engine_unit(
                    seed,
                    defaults=defaults,
                    dice_payload=dice_payload,
                    name=u.name,
                    side=BATTLE_SIDE_DEFENDER,
                )
                snap = catalog.resolve_snapshot(u.taunt_aura_id)
                if snap is not None:
                    row["taunt_aura"] = snap
                    row["taunt_aura_id"] = u.taunt_aura_id
                result.append(row)
            return result
        anchor_x, anchor_y = board.default_anchor
        # 防守锚点 = 进攻锚点 x 镜像（与改前口径一致）
        defender_x = (board.size - 1) - anchor_x
        defaults = board.unit_defaults[PIECE_KIND_MAIN]
        facade = MonsterCharacter.from_template(
            "monster",
            {
                "label_zh": monster.name,
                "stats": {
                    "hp": monster.hp,
                    "phys_atk": monster.atk,
                    "speed": defaults.speed,
                    "mp": 0,
                },
            },
        )
        seed = facade.on_battle_enter(
            unit_uid="monster",
            side="defender",
            x=defender_x,
            y=anchor_y,
        )
        return [
            seed_to_engine_unit(
                seed,
                defaults=defaults,
                dice_payload=dice_payload,
                name=monster.name,
                side=BATTLE_SIDE_DEFENDER,
                uid="d_monster",
            ),
        ]

    @staticmethod
    def _snapshot_defender_units(payload: dict[str, Any], board: BoardConfig) -> list[dict[str, Any]]:
        """
        对方快照 → 防守方（side=1）棋子列表。

        快照坐标存的是对方自己的「进攻方视角」→ 落位需 x 镜像到敌对半区。
        """
        from app.services.dice_service import DiceService

        # 快照若未带 dice，用怪物默认回落
        fallback = DiceService.unit_dice_payload(
            DiceService().monster_bounds(purpose="combat_damage"),
        )
        units: list[dict[str, Any]] = []
        for u in payload.get("units") or []:
            units.append(
                {
                    "uid": f"d_{u['unit_uid']}",
                    "kind": str(u.get("unit_kind", "main")),
                    "name": str(u.get("name", u["unit_uid"])),
                    "side": 1,
                    "x": (board.size - 1) - int(u["x"]),
                    "y": int(u["y"]),
                    "atk": int(u["atk"]),
                    "hp": int(u["hp"]),
                    "speed": int(u.get("speed", 5)),
                    "attack_range": int(u.get("attack_range", 1)),
                    "attack_kind": str(u.get("attack_kind", "melee_physical")),
                    "can_fly": bool(u.get("can_fly", False)),
                    "dice_lo": int(u.get("dice_lo", fallback["dice_lo"])),
                    "dice_hi": int(u.get("dice_hi", fallback["dice_hi"])),
                },
            )
        return units

    @staticmethod
    def mirror_attack_units_to_defender_side(
        attack_units: list[dict[str, Any]],
        board: BoardConfig,
    ) -> list[dict[str, Any]]:
        """
        将 side=0 进攻编成镜像为 side=1（赛会对称现场编成）。

        预设坐标均为「自己进攻视角」；乙方落位与防守快照相同：x → size-1-x。
        """
        mirrored: list[dict[str, Any]] = []
        for unit in attack_units:
            next_unit = dict(unit)
            raw_uid = str(unit.get("uid") or "unit")
            if raw_uid.startswith("a_"):
                raw_uid = raw_uid[2:]
            next_unit["uid"] = f"d_{raw_uid}"
            next_unit["side"] = 1
            next_unit["x"] = (board.size - 1) - int(unit["x"])
            mirrored.append(next_unit)
        return mirrored

    async def load_contest_live_attack_setup(
        self,
        character: Character,
        *,
        preset_slot: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
        """
        赛会开打瞬间：现场读取进攻预设 + 实时战力（不扣体力/化身行动）。

        Returns:
            (side0 棋子列表, 阵法 plain 或 None, 审计摘要)
        """
        board = get_game_config().board
        settings = get_settings()
        preset = await self._formations.get_attack_preset(character, slot=preset_slot)
        preset_units = json.loads(preset.units_json or "[]")
        if not preset_units:
            if settings.pve_require_preset:
                raise AppError(code=40040, message="进攻预设为空，请先布阵", http_status=400)
            anchor_x, anchor_y = board.default_anchor
            preset_units = [
                {"unit_uid": "main", "unit_kind": "main", "x": anchor_x, "y": anchor_y},
            ]
        await self._formations.validate_units(character, preset_units, preset.formation_id)
        # 赛会/PVP 路径：禁止道友客串化身
        self._reject_guest_units(preset_units, mode="赛会")
        formation = await self._formations.resolve_formation_def(preset.formation_id, character)
        units = await self._attacker_units(character, preset_units)
        formation_plain = (
            None
            if formation.formation_id == "none"
            else FormationService.formation_to_plain(formation)
        )
        audit = {
            "character_id": character.id,
            "formation_id": str(preset.formation_id or "none"),
            "unit_count": len(units),
            "source": "attack_preset_live",
            "preset_slot": int(preset.slot),
            "preset_role": str(preset.role),
        }
        return units, formation_plain, audit

    # ------------------------------------------------------------------
    # 门禁与公共步骤
    # ------------------------------------------------------------------

    async def _prepare_character(
        self,
        user: User,
        now: datetime,
    ) -> Character:
        """P0 门禁：加载角色 → 清 pending → settle → 活动互斥。"""
        from app.domain.activity_mutex import Activity

        character = await self._gate.require_character(user)
        await self._gate.resolve_pending_before_play(character, now=now)
        settle_idle(character, now=now)
        await self._gate.assert_activity(character, Activity.START_BATTLE)
        return character

    async def _load_attack_setup(
        self,
        character: Character,
        preset_slot: int | None,
        *,
        inject_assist: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        加载进攻预设 → (棋子列表, 阵法 plain)。

        ``PVE_REQUIRE_PRESET=false`` 且预设为空时回退「本体锚点临时阵」。
        """
        settings = get_settings()
        board = get_game_config().board
        preset = await self._formations.get_attack_preset(character, slot=preset_slot)
        preset_units = json.loads(preset.units_json or "[]")
        if not preset_units:
            if settings.pve_require_preset:
                raise AppError(code=40040, message="进攻预设为空，请先布阵", http_status=400)
            anchor_x, anchor_y = board.default_anchor
            preset_units = [
                {"unit_uid": "main", "unit_kind": "main", "x": anchor_x, "y": anchor_y},
            ]
        from app.services.avatar_assist_service import parse_guest_unit_uid
        from app.services.formation_service import parse_assist_anchor

        preset_units = [
            unit
            for unit in preset_units
            if parse_guest_unit_uid(str(unit.get("unit_uid", ""))) is None
        ]
        if inject_assist:
            preset_units = await self._formations.inject_assist_guest(
                character,
                preset_units,
                parse_assist_anchor(getattr(preset, "assist_anchor_json", None)),
                formation_id=preset.formation_id,
            )
        # 开战前重校验（防配置变更后旧预设越界）
        await self._formations.validate_units(
            character,
            preset_units,
            preset.formation_id,
            allow_guest=inject_assist,
        )
        # 道友助战客串：开战扣主人「助战专用体力」（与探索 stamina 隔离）
        await self._spend_guest_assist_actions(character, preset_units)
        formation = await self._formations.resolve_formation_def(preset.formation_id, character)
        units = await self._attacker_units(character, preset_units)
        formation_plain = (
            None
            if formation.formation_id == "none"
            else FormationService.formation_to_plain(formation)
        )
        return units, formation_plain

    async def _spend_guest_assist_actions(
        self,
        character: Character,
        preset_units: list[dict[str, Any]],
    ) -> None:
        """
        PVE 开战：对编成中客串化身扣主人「助战专用体力」。
        """
        from app.services.avatar_assist_service import (
            AvatarAssistService,
            parse_guest_unit_uid,
        )

        assist_svc = AvatarAssistService(self._session)
        seen_avatar_ids: set[int] = set()
        for unit in preset_units:
            guest_ids = parse_guest_unit_uid(str(unit.get("unit_uid", "")))
            if guest_ids is None:
                continue
            owner_id, guest_avatar_id = guest_ids
            if guest_avatar_id in seen_avatar_ids:
                continue
            seen_avatar_ids.add(guest_avatar_id)
            guest_row = await self._session.get(Avatar, int(guest_avatar_id))
            owner_ch = await self._session.get(Character, int(owner_id))
            if guest_row is None or owner_ch is None:
                raise AppError(code=40057, message="客串化身或主人不存在", http_status=400)
            assist_svc.spend_assist_battle(guest_row, owner_ch)

    @staticmethod
    def _reject_guest_units(preset_units: list[dict[str, Any]], *, mode: str) -> None:
        """PVP / 赛会：编成含道友客串化身则拒绝。"""
        from app.services.avatar_assist_service import parse_guest_unit_uid

        for unit in preset_units:
            if parse_guest_unit_uid(str(unit.get("unit_uid", ""))) is not None:
                raise AppError(
                    code=40041,
                    message=f"{mode}不可使用道友化身助战",
                    http_status=400,
                )

    async def _apply_talisman_triggers(
        self,
        character: Character,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Inject item_trigger rows from preloaded talismans; consume if enabled."""
        from app.constants.battle import BATTLE_SIDE_ATTACKER
        from app.domain.talisman_battle import inject_item_triggers
        from app.services.craft_service import CraftService

        cfg = get_game_config().research.talisman
        craft = CraftService(self._session)
        talismans = await craft.peek_preloaded_talismans(character)
        attacker_uids: set[str] = set()
        for event in events:
            if event.get("type") != "battle_start":
                continue
            for unit in event.get("units") or []:
                if int(unit.get("side") or 0) == BATTLE_SIDE_ATTACKER:
                    attacker_uids.add(str(unit.get("uid") or ""))
        new_events = inject_item_triggers(
            events,
            talismans,
            enabled=bool(cfg.battle_enabled),
            attacker_uids=attacker_uids,
        )
        if cfg.battle_enabled and talismans:
            await craft.consume_preloaded_talismans(character)
        return new_events

    @staticmethod
    def _resolve_seed() -> int:
        """演算种子：env 注入（测试复现）优先，否则取 64 位随机数。"""
        settings = get_settings()
        if settings.autochess_rng_seed is not None:
            return int(settings.autochess_rng_seed)
        return secrets.randbits(63)

    @staticmethod
    def _render_report(outcome: dict[str, Any]) -> dict[str, Any]:
        """引擎结果 → 战报包（结构化事件 + 三种渲染档全给，前端选用）。"""
        events = outcome["events"]
        return {
            "schema_version": outcome["schema_version"],
            "seed": outcome["seed"],
            "winner": outcome["winner"],
            "rounds": outcome["rounds"],
            "board_text": render_board(events),
            "summary": render_summary(events),
            "detailed_log": render_detailed(events),
            "events": events,
        }

    @staticmethod
    def _apply_battle_cultivation_env(
        base_cultivation: int,
        *,
        shichen_id: str,
        weather_id: str,
    ) -> tuple[int, float]:
        """
        Scale battle cultivation rewards by locked world env (M5 polish).

        Args:
            base_cultivation: Raw reward from monster/snapshot table.
            shichen_id: Locked shichen at battle start.
            weather_id: Locked weather at battle start.

        Returns:
            tuple: (scaled_points, env_mult) for explicit UI breakdown.
        """
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.calendar_enabled and not settings.weather_enabled:
            return int(base_cultivation), 1.0

        bundle = get_game_config()
        shichen_table = bundle.calendar.modifiers.get("battle_cultivation") or {}
        weather_table = bundle.weather.modifiers.get("battle_cultivation") or {}
        shichen_mult = (
            lookup_modifier(shichen_table, shichen_id)
            if settings.calendar_enabled
            else 1.0
        )
        weather_mult = (
            lookup_modifier(weather_table, weather_id)
            if settings.weather_enabled
            else 1.0
        )
        env_mult = combine_env_multipliers(
            base=1.0,
            shichen_mult=shichen_mult,
            weather_mult=weather_mult,
            clamp_min=min(bundle.calendar.clamp_min, bundle.weather.clamp_min),
            clamp_max=max(bundle.calendar.clamp_max, bundle.weather.clamp_max),
        )
        return int(base_cultivation * env_mult), float(env_mult)

    # ------------------------------------------------------------------
    # PVE
    # ------------------------------------------------------------------

    async def start_pve(
        self,
        user: User,
        monster_id: str,
        preset_slot: int | None = None,
        now: datetime | None = None,
        *,
        use_dao: bool = False,
    ) -> dict[str, Any]:
        """
        发起一场棋盘化 PVE 讨伐。

        参数:
            user: 当前用户。
            monster_id: 怪物配置键。
            preset_slot: 指定进攻预设槽；None 时取 role=attack 预设。
            now: 可选冻结时间（测试）。
            use_dao: 是否运用本命道（M6）。

        返回:
            dict: ``{result, seed, monster_id, monster_name, report, rewards, stamina, character}``。

        异常:
            AppError: ``40022`` 状态互斥；``40025`` 怪物不存在；``40049`` 体力不足。
        """
        current_time = now_utc(now)
        character = await self._prepare_character(user, current_time)

        monster = get_game_config().monsters.get(monster_id)
        if monster is None:
            raise AppError(code=40025, message="怪物不存在或未开放", http_status=404)

        # 先组装（校验可能失败），后扣体力：避免非法请求白扣
        attacker_units, attacker_formation = await self._load_attack_setup(
            character,
            preset_slot,
        )

        dao_usage_info: dict[str, Any] | None = None
        dao_restraint_event: dict[str, Any] | None = None
        if use_dao:
            from app.services.dao_service import DaoService

            dao_svc = DaoService(self._session)
            # 开战前预检道值；真正扣减在结算后按胜负
            preview = await dao_svc.preview_usage(
                user,
                kind="battle",
            )
            if not preview.get("can_afford"):
                raise AppError(code=40084, message="道值不足", http_status=400)
            dmg_mul = float(preview.get("damage_mul") or 1.0)
            for unit in attacker_units:
                if "atk" in unit:
                    unit["atk"] = int(max(1, round(float(unit["atk"]) * dmg_mul)))
                if "attack" in unit:
                    unit["attack"] = int(max(1, round(float(unit["attack"]) * dmg_mul)))

        stamina_state = self._stamina.spend_for_monster(
            character,
            monster.stamina_cost,
            now=current_time,
        )

        board = get_game_config().board
        # M5：开战锁定世界时辰/天气
        from app.services.calendar_service import CalendarService
        from app.services.weather_service import WeatherService

        cal = CalendarService().get_snapshot(now=current_time)
        weather_id = WeatherService().get_underlying_weather_id(now=current_time)
        # 阵法对抗骰：攻方取单位区间；守方怪物默认
        atk_unit = attacker_units[0] if attacker_units else {}
        from app.services.dice_service import DiceService

        mon_b = DiceService().monster_bounds(purpose="formation")
        setup: dict[str, Any] = {
            "board": self._board_plain(board),
            "units": attacker_units + self._monster_units(monster, board),
            "attacker_formation": attacker_formation,
            "defender_formation": None,  # PVE 怪物暂无阵法（后续可配）
            "counters": self._counters_plain(),
            "layer_catalogs": self._layer_catalogs_plain(),
            "locked_shichen": cal["shichen_id"],
            "locked_world_weather": weather_id,
            "formation_dice": {
                "attacker_lo": int(atk_unit.get("dice_lo", 1)),
                "attacker_hi": int(atk_unit.get("dice_hi", board.dice_sides)),
                "defender_lo": mon_b.lo,
                "defender_hi": mon_b.hi,
            },
        }
        seed = self._resolve_seed()
        outcome = simulate_battle(setup, seed)
        outcome["events"] = await self._apply_talisman_triggers(character, outcome["events"])

        # P3 结算：奖励入账；修为乘开战锁定环境（日历/天气 battle_cultivation）
        result = outcome["result"]
        rewards_src = monster.rewards_on_win if result == "win" else monster.rewards_on_lose
        scaled_cultivation, env_mult = self._apply_battle_cultivation_env(
            int(rewards_src.cultivation_points),
            shichen_id=str(cal["shichen_id"]),
            weather_id=str(weather_id),
        )
        rewards = {
            "cultivation_points": scaled_cultivation,
            "spirit_stones": rewards_src.spirit_stones,
            "cultivation_base": int(rewards_src.cultivation_points),
            "env_mult": env_mult,
            "locked_shichen": cal["shichen_id"],
            "locked_weather": weather_id,
        }
        character.cultivation_points = int(character.cultivation_points) + rewards["cultivation_points"]
        character.spirit_stones = int(character.spirit_stones) + rewards["spirit_stones"]

        if use_dao:
            from app.services.dao_service import DaoService

            dao_svc = DaoService(self._session)
            dao_usage_info = await dao_svc.consume_usage(
                character,
                kind="battle",
                success=(result == "win"),
            )
            # PVE 无守方本命道；克制事件仅当配置有边且未来怪物挂道时

        character.updated_at = current_time
        await self._session.flush()
        # 普通 PVE：战斗结束后客串化身自动离队（秘境整场结束另调 end_for_secret_realm）
        from app.services.avatar_assist_service import AvatarAssistService

        await AvatarAssistService(self._session).end_active_for_borrower(
            character.id,
            reason="pve_battle_end",
        )
        await self._session.refresh(character)

        logger.info(
            "autochess pve character_id=%s monster=%s result=%s rounds=%s seed=%s env=%s use_dao=%s",
            character.id,
            monster_id,
            result,
            outcome["rounds"],
            seed,
            env_mult,
            use_dao,
        )
        public = await self._characters.enrich_public(character)
        report = self._render_report(outcome)
        if dao_usage_info is not None and isinstance(report, dict):
            events = list(report.get("events") or [])
            events.insert(
                0,
                {
                    "type": "dao_usage",
                    "battle_text": (
                        f"运用本命道「{dao_usage_info.get('fate_dao_label')}」"
                        f"（耗道值 {dao_usage_info.get('qi_cost')}）"
                    ),
                    "summary": f"运用{dao_usage_info.get('fate_dao_label')}",
                },
            )
            if dao_restraint_event:
                events.insert(1, dao_restraint_event)
            report["events"] = events
            report["dao_usage"] = dao_usage_info
        # 探索遭遇：播控策略由后端种类矩阵下发，前端不得按路由猜测
        presentation = BattlePlaybackPolicy.envelope(BattleKind.EXPLORATION)
        return {
            "mode": "pve",
            "result": result,
            "seed": seed,
            "monster_id": monster_id,
            "monster_name": monster.name,
            "report": report,
            "rewards": rewards,
            "stamina": stamina_state,
            "dao_usage": dao_usage_info,
            "character": CharacterService.public_to_dict(public),
            **presentation,
        }

    # ------------------------------------------------------------------
    # PVP（攻打快照，异步非对称）
    # ------------------------------------------------------------------

    async def start_pvp(
        self,
        user: User,
        target_character_id: int,
        preset_slot: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        攻打其他玩家的防守快照（对方零打扰，只演算不通知）。

        返回:
            dict: 同 PVE 结构，另含 ``target`` 摘要。

        异常:
            AppError: ``40047`` 不能攻打自己；``40048`` 目标无快照；``40049`` 体力不足。
        """
        current_time = now_utc(now)
        character = await self._prepare_character(user, current_time)
        if target_character_id == character.id:
            raise AppError(code=40047, message="不能攻打自己的快照", http_status=400)

        payload = await self._snapshots.load_payload_for_battle(target_character_id)

        # 先读预设以拒绝客串，再走 _load_attack_setup（避免误扣助战体力）
        preset = await self._formations.get_attack_preset(character, slot=preset_slot)
        preset_units = json.loads(preset.units_json or "[]")
        self._reject_guest_units(preset_units, mode="PVP")

        attacker_units, attacker_formation = await self._load_attack_setup(
            character,
            preset_slot,
            inject_assist=False,
        )
        stamina_state = self._stamina.spend(character, "battle_pvp", now=current_time)

        board = get_game_config().board
        defender_formation = None
        formation_id = str(payload.get("formation_id") or "none")
        if formation_id != "none":
            inline = payload.get("formation_blueprint")
            if isinstance(inline, dict):
                custom = FormationService.def_from_blueprint(
                    formation_id=formation_id,
                    name=str(payload.get("formation_name") or formation_id),
                    blueprint=inline,
                )
                defender_formation = FormationService.formation_to_plain(custom)
            else:
                formations = get_game_config().formations.formations
                formation = formations.get(formation_id)
                if formation is not None:
                    defender_formation = FormationService.formation_to_plain(formation)

        defender_units = self._snapshot_defender_units(payload, board)
        atk_unit = attacker_units[0] if attacker_units else {}
        def_unit = defender_units[0] if defender_units else {}
        setup: dict[str, Any] = {
            "board": self._board_plain(board),
            "units": attacker_units + defender_units,
            "attacker_formation": attacker_formation,
            "defender_formation": defender_formation,
            "counters": self._counters_plain(),
            "layer_catalogs": self._layer_catalogs_plain(),
            "formation_dice": {
                "attacker_lo": int(atk_unit.get("dice_lo", 1)),
                "attacker_hi": int(atk_unit.get("dice_hi", board.dice_sides)),
                "defender_lo": int(def_unit.get("dice_lo", 1)),
                "defender_hi": int(def_unit.get("dice_hi", board.dice_sides)),
            },
        }
        seed = self._resolve_seed()
        outcome = simulate_battle(setup, seed)
        outcome["events"] = await self._apply_talisman_triggers(character, outcome["events"])

        # PVP 占位奖励：只加攻方；修为同样乘开战环境（开战时锁定）
        from app.services.calendar_service import CalendarService
        from app.services.weather_service import WeatherService

        cal = CalendarService().get_snapshot(now=current_time)
        weather_id = WeatherService().get_underlying_weather_id(now=current_time)
        result = outcome["result"]
        cfg = get_game_config().snapshots
        rewards_src = cfg.attacker_win if result == "win" else cfg.attacker_lose
        scaled_cultivation, env_mult = self._apply_battle_cultivation_env(
            int(rewards_src.cultivation_points),
            shichen_id=str(cal["shichen_id"]),
            weather_id=str(weather_id),
        )
        rewards = {
            "cultivation_points": scaled_cultivation,
            "spirit_stones": rewards_src.spirit_stones,
            "cultivation_base": int(rewards_src.cultivation_points),
            "env_mult": env_mult,
            "locked_shichen": cal["shichen_id"],
            "locked_weather": weather_id,
        }
        character.cultivation_points = int(character.cultivation_points) + rewards["cultivation_points"]
        character.spirit_stones = int(character.spirit_stones) + rewards["spirit_stones"]
        character.updated_at = current_time
        await self._session.flush()
        await self._session.refresh(character)

        logger.info(
            "autochess pvp character_id=%s target=%s result=%s rounds=%s seed=%s",
            character.id,
            target_character_id,
            result,
            outcome["rounds"],
            seed,
        )
        public = await self._characters.enrich_public(character)
        presentation = BattlePlaybackPolicy.envelope(BattleKind.EXPLORATION)
        return {
            "mode": "pvp",
            "result": result,
            "seed": seed,
            "target": {
                "character_id": payload.get("character_id"),
                "dao_name": payload.get("dao_name"),
                "realm": payload.get("realm"),
            },
            "report": self._render_report(outcome),
            "rewards": rewards,
            "stamina": stamina_state,
            "character": CharacterService.public_to_dict(public),
            **presentation,
        }

    # ------------------------------------------------------------------
    # 对手列表（PVP 入口）
    # ------------------------------------------------------------------

    async def list_opponents(
        self,
        character: Character,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        可攻打对手列表（M3 占位：除自己外按 id 升序取前 N 个角色）。

        匹配 / 段位系统后置；此处只为打通 PVP 竖切。
        """
        result = await self._session.execute(
            select(Character)
            .where(Character.id != character.id)
            .order_by(Character.id)
            .limit(limit),
        )
        opponents: list[dict[str, Any]] = []
        for target in result.scalars().all():
            row = await self._snapshots.get_row(target.id)
            opponents.append(
                {
                    "character_id": target.id,
                    "dao_name": target.name,
                    "major_realm": target.major_realm,
                    "realm_stage": target.realm_stage,
                    "has_snapshot": row is not None,
                },
            )
        return opponents
