"""
布阵应用服务（M3战斗成型设计.md §4 · S2/S5）。

职责：预设 CRUD、占位校验、可上阵棋子清单（Bench）、
开战用进攻阵组装（本体面板走 ``CharacterService.build_combat_stats`` 权威源）。

坐标口径（写死）：预设一律存 **进攻方视角** 坐标；防守侧开战再镜像。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import now_utc, to_utc_iso
from app.db.models.avatar import Avatar
from app.db.models.character import Character
from app.db.models.inventory_item import InventoryItem
from app.db.models.formation_preset import FormationPreset
from app.db.models.pet import Pet
from app.domain.board import (
    PlacementError,
    board_meta_payload,
    max_units_for_realm,
    validate_placement,
)
from app.domain.formation_blueprint import (
    FormationDeploySnapshot,
    deploy_config_to_dict,
    force_shifts_to_dict,
    resolve_formation_deploy,
)
from app.schemas.common import AppError
from app.services.realm_config import FormationDef, get_game_config

logger = logging.getLogger(__name__)

# 默认三槽：槽位 → (名称, 角色定位)
_DEFAULT_SLOTS: tuple[tuple[int, str, str], ...] = (
    (0, "进攻", "attack"),
    (1, "防守", "defense"),
    (2, "临时", "temp"),
)

# 合法角色定位枚举
_VALID_ROLES = {"attack", "defense", "temp"}


class FormationService:
    """
    布阵用例：预设管理与占位校验。

    属性:
        _session: 请求级异步会话。
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        参数:
            session: SQLAlchemy 异步会话。
        """
        self._session = session

    # ------------------------------------------------------------------
    # 配置辅助
    # ------------------------------------------------------------------

    def get_formation_def(self, formation_id: str, character: Character | None = None) -> FormationDef:
        """
        查阵法定义；不存在或未解锁 → ``40044`` / ``40054``。

        M4：``unlocked_by_default`` 或 ``array_craft_level >= required_array_level``。
        """
        formations = get_game_config().formations.formations
        formation = formations.get(formation_id)
        if formation is None:
            raise AppError(code=40044, message=f"阵法不存在：{formation_id}", http_status=404)
        if formation.formation_id == "none":
            return formation
        unlocked = formation.unlocked_by_default
        if character is not None and not unlocked:
            unlocked = int(character.array_craft_level) >= int(formation.required_array_level)
        if not unlocked:
            if character is not None and formation.required_array_level > 0:
                raise AppError(
                    code=40054,
                    message=f"阵法等级不足，需要 {formation.required_array_level}",
                    http_status=403,
                )
            raise AppError(code=40044, message=f"阵法未解锁：{formation.name}", http_status=403)
        return formation

    @staticmethod
    def get_formation_def_static(formation_id: str) -> FormationDef:
        """兼容旧调用：仅查存在性，不校验 array 等级。"""
        formations = get_game_config().formations.formations
        formation = formations.get(formation_id)
        if formation is None:
            raise AppError(code=40044, message=f"阵法不存在：{formation_id}", http_status=404)
        return formation

    @staticmethod
    def deploy_snapshot(formation: FormationDef) -> FormationDeploySnapshot:
        """
        一次解析阵法部署运行时视图（禁停 + 有效格）。

        校验 / 高亮 / 上限必须共用此结果，避免重复 resolve。
        """
        return resolve_formation_deploy(
            get_game_config().board,
            formation.deploy,
            formation.terrain,
        )

    @staticmethod
    def terrain_blocked_cells(formation: FormationDef) -> frozenset[tuple[int, int]]:
        """阵法地形禁停格（进攻方视角）；薄封装，优先用 ``deploy_snapshot``。"""
        return FormationService.deploy_snapshot(formation).blocked_cells

    @staticmethod
    def resolve_effective_deploy(formation: FormationDef) -> frozenset[tuple[int, int]]:
        """有效可部署格（进攻方视角）；薄封装，优先用 ``deploy_snapshot``。"""
        return FormationService.deploy_snapshot(formation).deploy_cells

    @staticmethod
    def effective_max_units_for(character: Character, formation: FormationDef) -> int:
        """境界上限 ∩ 合法格数 ∩ 阵法 max_units。"""
        board = get_game_config().board
        snap = FormationService.deploy_snapshot(formation)
        return snap.max_units_for(
            board,
            character.major_realm,
            formation_max_units=formation.deploy.max_units,
        )

    @staticmethod
    def formation_public_dict(
        formation: FormationDef,
        *,
        unlocked: bool,
        major_realm: str | None = None,
    ) -> dict[str, Any]:
        """
        阵法列表项（含部署契约与有效格，供前端高亮）。

        若传入 ``major_realm``，附带 ``max_units_effective``（权威上限）。
        """
        board = get_game_config().board
        snap = FormationService.deploy_snapshot(formation)
        payload: dict[str, Any] = {
            "formation_id": formation.formation_id,
            "name": formation.name,
            "level": formation.level,
            "unlocked": unlocked,
            "required_array_level": formation.required_array_level,
            "terrain": [
                {"x": c.x, "y": c.y, "type": c.terrain_type, "subtype": c.subtype}
                for c in formation.terrain
            ],
            "deploy": deploy_config_to_dict(formation.deploy),
            "effective_deploy_cells": sorted(snap.deploy_cells),
            "force_shifts": force_shifts_to_dict(formation.force_shifts),
            "max_units_formation": formation.deploy.max_units,
        }
        if major_realm is not None:
            payload["max_units_effective"] = snap.max_units_for(
                board,
                major_realm,
                formation_max_units=formation.deploy.max_units,
            )
        return payload

    @staticmethod
    def formation_to_plain(formation: FormationDef) -> dict[str, Any]:
        """把阵法定义转成引擎可用的纯数据 dict（引擎零依赖纪律）。"""

        def _layer(layer: Any) -> dict[str, Any] | None:
            """层配置 → 纯 dict。"""
            if layer is None:
                return None
            return {
                "id": layer.layer_id,
                "force_apply": layer.force_apply,
                "counter_group": layer.counter_group,
                "atk_mul": layer.atk_mul,
                "hp_mul": layer.hp_mul,
            }

        return {
            "id": formation.formation_id,
            "name": formation.name,
            "level": formation.level,
            "terrain": [
                {"x": c.x, "y": c.y, "type": c.terrain_type, "subtype": c.subtype}
                for c in formation.terrain
            ],
            "environment": _layer(formation.environment),
            "weather": _layer(formation.weather),
            "effect": _layer(formation.effect),
            # 开战强制移位（进攻方视角；守方由引擎镜像）
            "force_shifts": force_shifts_to_dict(formation.force_shifts),
        }

    # ------------------------------------------------------------------
    # Bench（可上阵棋子清单）
    # ------------------------------------------------------------------

    async def bench_units(self, character: Character) -> list[dict[str, Any]]:
        """
        角色当前可上阵棋子（本体 + 化身 + 灵宠 + 傀儡库存 + 试炼木傀）。

        Returns:
            list[dict]: ``[{unit_uid, unit_kind, name, enabled, ref_id?}, ...]``。
        """
        board = get_game_config().board
        settings = get_settings()
        bench: list[dict[str, Any]] = [
            {"unit_uid": "main", "unit_kind": "main", "name": "本体", "enabled": True},
        ]

        # 化身：已凝练且非 disabled / 渡劫禁上阵
        avatar_gate = board.unit_kinds.get("avatar")
        avatar_enabled = bool(avatar_gate and avatar_gate.enabled and settings.avatar_enabled)
        result = await self._session.execute(
            select(Avatar).where(Avatar.character_id == character.id).limit(1),
        )
        avatar_row = result.scalar_one_or_none()
        if avatar_row is not None:
            tribulation_block = character.status == "tribulation"
            av_ok = avatar_row.status != "disabled" and not tribulation_block
            bench.append(
                {
                    "unit_uid": f"avatar_{avatar_row.id}",
                    "unit_kind": "avatar",
                    "name": avatar_row.name,
                    "enabled": avatar_enabled and av_ok,
                    "ref_id": avatar_row.id,
                },
            )
        elif avatar_enabled:
            bench.append(
                {
                    "unit_uid": "avatar",
                    "unit_kind": "avatar",
                    "name": "化身",
                    "enabled": False,
                },
            )

        # 灵宠
        pet_gate = board.unit_kinds.get("pet")
        pet_enabled = bool(pet_gate and pet_gate.enabled and settings.pets_enabled)
        pet_result = await self._session.execute(
            select(Pet).where(Pet.character_id == character.id).order_by(Pet.id),
        )
        pets = list(pet_result.scalars().all())
        if pets:
            for pet in pets:
                bench.append(
                    {
                        "unit_uid": f"pet_{pet.id}",
                        "unit_kind": "pet",
                        "name": pet.nickname or pet.species_id,
                        "enabled": pet_enabled,
                        "ref_id": pet.id,
                    },
                )
        else:
            bench.append(
                {"unit_uid": "pet", "unit_kind": "pet", "name": "灵宠", "enabled": False},
            )

        # 背包傀儡 + 试炼木傀
        puppet_gate = board.unit_kinds.get("puppet")
        puppet_enabled = bool(puppet_gate and puppet_gate.enabled)
        inv_result = await self._session.execute(
            select(InventoryItem).where(
                InventoryItem.character_id == character.id,
                InventoryItem.item_type == "puppet",
            ),
        )
        for inv in inv_result.scalars().all():
            bench.append(
                {
                    "unit_uid": inv.item_uid,
                    "unit_kind": "puppet",
                    "name": inv.item_id,
                    "enabled": puppet_enabled,
                    "ref_id": inv.id,
                },
            )
        for index in range(int(character.trial_puppet_count)):
            bench.append(
                {
                    "unit_uid": f"puppet_{index + 1}",
                    "unit_kind": "puppet",
                    "name": "试炼木傀",
                    "enabled": puppet_enabled,
                },
            )

        # 道友化身助战：借入中的客串化身出现在借用人 bench（仅 PVE 可用）
        from app.services.avatar_assist_service import (
            AvatarAssistService,
            guest_unit_uid,
        )

        assist_svc = AvatarAssistService(self._session)
        guest_sessions = await assist_svc.list_active_for_borrower(character.id)
        for sess in guest_sessions:
            owner = await self._session.get(Character, sess.owner_character_id)
            avatar_guest = await self._session.get(Avatar, sess.avatar_id)
            if avatar_guest is None or str(avatar_guest.status) == "disabled":
                continue
            owner_label = owner.name if owner else str(sess.owner_character_id)
            bench.append(
                {
                    "unit_uid": guest_unit_uid(sess.owner_character_id, sess.avatar_id),
                    "unit_kind": "avatar",
                    "name": f"{owner_label}·{avatar_guest.name}",
                    "enabled": avatar_enabled,
                    "ref_id": avatar_guest.id,
                    "owner_character_id": sess.owner_character_id,
                    "assist_session_id": sess.id,
                    "is_guest": True,
                },
            )
        return bench

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    async def validate_units(
        self,
        character: Character,
        units: list[dict[str, Any]],
        formation_id: str,
    ) -> None:
        """
        校验一份布阵（占位 + 编成归属 + M4 持有物 + 化身独战闸）。

        异常:
            AppError: 40041/40042/40043/40044/40054/40057/40090/40093。
        """
        from app.domain.avatar_rules import (
            ERR_SOLO_FORMATION_INVALID,
        )
        from app.domain.m4_constants import AvatarFeature

        board = get_game_config().board
        formation = self.get_formation_def(formation_id, character)
        # 一次解析：禁停 + 有效区 + 上限
        snap = self.deploy_snapshot(formation)
        max_units = snap.max_units_for(
            board,
            character.major_realm,
            formation_max_units=formation.deploy.max_units,
        )

        has_main = any(str(u.get("unit_kind")) == "main" for u in units)
        has_avatar = any(str(u.get("unit_kind")) == "avatar" for u in units)
        solo_mode = not has_main
        # 走预计算能力索引，避免每次布阵重扫境界链
        cap_idx = get_game_config().avatar.capability
        if cap_idx is None:
            from app.domain.avatar_capability import AvatarCapabilityIndex

            cap_idx = AvatarCapabilityIndex.from_config(
                get_game_config().avatar,
                get_game_config().realms,
            )
        solo_unlocked = cap_idx.is_unlocked(
            character.major_realm,
            AvatarFeature.SOLO_BATTLE,
        )
        if solo_mode:
            if not solo_unlocked:
                raise AppError(
                    code=ERR_SOLO_FORMATION_INVALID,
                    message="化神后方可化身独战（编成须含本体）",
                    http_status=400,
                )
            if not has_avatar:
                raise AppError(
                    code=ERR_SOLO_FORMATION_INVALID,
                    message="独战编成须至少含化身",
                    http_status=400,
                )

        try:
            validate_placement(
                units,
                board,
                max_units=max_units,
                blocked_cells=snap.blocked_cells,
                deploy_zone=snap.deploy_cells,
                require_main=not solo_mode,
                allow_solo_avatar=solo_mode,
            )
        except PlacementError as exc:
            raise AppError(code=exc.code, message=exc.message, http_status=400) from exc

        bench = await self.bench_units(character)
        bench_index = {
            (str(b["unit_kind"]), str(b["unit_uid"])): b for b in bench
        }

        seen_uids: set[str] = set()
        trial_puppet_used = 0
        guest_count = 0
        from app.services.avatar_assist_service import (
            AvatarAssistService,
            parse_guest_unit_uid,
        )

        assist_svc = AvatarAssistService(self._session)

        for unit in units:
            uid = str(unit.get("unit_uid", ""))
            kind = str(unit.get("unit_kind", ""))
            if uid in seen_uids:
                raise AppError(code=40041, message=f"棋子重复上阵：{uid}", http_status=400)
            seen_uids.add(uid)

            if kind == "avatar":
                if character.status == "tribulation":
                    raise AppError(code=40042, message="渡劫中禁止化身上阵", http_status=400)
                guest_ids = parse_guest_unit_uid(uid)
                if guest_ids is not None:
                    # 客串化身：须有 active 助战会话，且归属正确
                    guest_count += 1
                    if guest_count > 1:
                        raise AppError(
                            code=40041,
                            message="编成最多 1 名道友化身助战",
                            http_status=400,
                        )
                    owner_id, guest_avatar_id = guest_ids
                    sess = await assist_svc.get_active_guest_session(
                        borrower_character_id=character.id,
                        owner_character_id=owner_id,
                        avatar_id=guest_avatar_id,
                    )
                    if sess is None:
                        raise AppError(
                            code=40057,
                            message="道友助战会话无效或已结束",
                            http_status=400,
                        )
                    guest_av = await self._session.get(Avatar, guest_avatar_id)
                    if guest_av is None or guest_av.character_id != owner_id:
                        raise AppError(code=40057, message="客串化身归属非法", http_status=400)
                    if str(guest_av.status) == "disabled":
                        raise AppError(code=40051, message="客串化身不可用", http_status=400)
                    unit["ref_id"] = guest_av.id
                    unit["owner_character_id"] = owner_id
                    unit["is_guest"] = True
                else:
                    # 兼容旧客户端：未传 ref_id 时从 unit_uid「avatar_{id}」推导
                    ref = unit.get("ref_id")
                    if ref is None and uid.startswith("avatar_"):
                        suffix = uid[7:]
                        if suffix.isdigit():
                            ref = int(suffix)
                            unit["ref_id"] = ref
                    av_result = await self._session.execute(
                        select(Avatar).where(Avatar.character_id == character.id).limit(1),
                    )
                    av = av_result.scalar_one_or_none()
                    if av is None or av.status == "disabled":
                        raise AppError(code=40051, message="化身不可用", http_status=400)
                    if ref is not None and int(ref) != av.id:
                        raise AppError(code=40057, message="化身 ref_id 非法", http_status=400)
            elif kind == "pet":
                ref_id = unit.get("ref_id")
                # 兼容：unit_uid=pet_{id} 且未传 ref_id 时回填
                if ref_id is None and uid.startswith("pet_"):
                    suffix = uid[4:]
                    if suffix.isdigit():
                        ref_id = int(suffix)
                        unit["ref_id"] = ref_id
                if ref_id is None:
                    raise AppError(code=40057, message="灵宠须指定 ref_id", http_status=400)
                pet_result = await self._session.execute(
                    select(Pet.id).where(
                        Pet.id == int(ref_id),
                        Pet.character_id == character.id,
                    ).limit(1),
                )
                if pet_result.scalar_one_or_none() is None:
                    raise AppError(code=40057, message="灵宠不存在或不属于当前角色", http_status=400)
            elif kind == "puppet":
                if uid.startswith("puppet_") and uid[7:].isdigit():
                    trial_puppet_used += 1
                else:
                    inv_result = await self._session.execute(
                        select(InventoryItem.id).where(
                            InventoryItem.character_id == character.id,
                            InventoryItem.item_uid == uid,
                            InventoryItem.item_type == "puppet",
                        ).limit(1),
                    )
                    if inv_result.scalar_one_or_none() is None:
                        raise AppError(code=40041, message=f"傀儡未持有：{uid}", http_status=400)

            key = (kind, uid)
            if key in bench_index and not bench_index[key].get("enabled", False):
                raise AppError(code=40043, message=f"棋子类型未开放或未持有：{kind}", http_status=400)

        if trial_puppet_used > int(character.trial_puppet_count):
            raise AppError(
                code=40041,
                message=f"试炼木傀数量不足（持有 {character.trial_puppet_count} 个）",
                http_status=400,
            )

    # ------------------------------------------------------------------
    # 预设 CRUD
    # ------------------------------------------------------------------

    def _default_units_json(self) -> str:
        """
        默认阵 JSON：本体落锚点（进攻方视角）。

        Returns:
            str: units_json 文本。
        """
        board = get_game_config().board
        anchor_x, anchor_y = board.default_anchor
        return json.dumps(
            [
                {
                    "unit_uid": "main",
                    "unit_kind": "main",
                    "x": anchor_x,
                    "y": anchor_y,
                },
            ],
            ensure_ascii=False,
        )

    async def ensure_default_presets(self, character: Character) -> None:
        """确保角色拥有默认三槽预设（惰性种子，兼容 M3 前旧号）。"""
        result = await self._session.execute(
            select(FormationPreset.slot).where(
                FormationPreset.character_id == character.id,
            ),
        )
        existing_slots = {row[0] for row in result.all()}
        created = False
        default_units = self._default_units_json()
        for slot, name, role in _DEFAULT_SLOTS:
            if slot in existing_slots:
                continue
            self._session.add(
                FormationPreset(
                    character_id=character.id,
                    slot=slot,
                    name=name,
                    role=role,
                    formation_id="none",
                    units_json=default_units,
                    updated_at=now_utc(),
                ),
            )
            created = True
        if created:
            await self._session.flush()

    async def reset_presets_to_default(self, character: Character) -> int:
        """
        清空并重种默认阵法预设（轮回结算用）。

        删除该角色全部布阵行后，按默认三槽（进攻/防守/临时）重新插入：
        ``formation_id=none``、仅本体锚点单位。

        Args:
            character: 角色实体。

        Returns:
            int: 重种后的预设槽位数。
        """
        await self._session.execute(
            delete(FormationPreset).where(
                FormationPreset.character_id == character.id,
            ),
        )
        await self._session.flush()
        await self.ensure_default_presets(character)
        logger.info(
            "formation presets reset character_id=%s slots=%s",
            character.id,
            len(_DEFAULT_SLOTS),
        )
        return len(_DEFAULT_SLOTS)

    @staticmethod
    def preset_to_dict(preset: FormationPreset) -> dict[str, Any]:
        """预设实体 → 响应 dict。"""
        return {
            "slot": preset.slot,
            "name": preset.name,
            "role": preset.role,
            "formation_id": preset.formation_id,
            "units": json.loads(preset.units_json or "[]"),
            "updated_at": to_utc_iso(preset.updated_at),
        }

    async def prune_invalid_units_from_presets(
        self,
        character: Character,
    ) -> int:
        """
        清洗预设中已失效的棋子（无化身仍占格、灵宠已删等）。

        化身解散 / 轮回后常见：``units_json`` 仍留 ``avatar_{id}``，
        Bench 只剩占位 ``avatar``，前端按 uid 对不上无法「撤下」。

        Args:
            character: 角色实体。

        Returns:
            int: 共移除的棋子数量。
        """
        await self.ensure_default_presets(character)
        result = await self._session.execute(
            select(FormationPreset).where(
                FormationPreset.character_id == character.id,
            ),
        )
        presets = list(result.scalars().all())
        if not presets:
            return 0

        avatar_row = (
            await self._session.execute(
                select(Avatar).where(Avatar.character_id == character.id).limit(1),
            )
        ).scalar_one_or_none()
        avatar_ok = (
            avatar_row is not None and str(avatar_row.status) != "disabled"
        )
        avatar_id = int(avatar_row.id) if avatar_row is not None else None

        pet_rows = (
            await self._session.execute(
                select(Pet.id).where(Pet.character_id == character.id),
            )
        ).all()
        pet_ids = {int(row[0]) for row in pet_rows}

        inv_rows = (
            await self._session.execute(
                select(InventoryItem.item_uid).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_type == "puppet",
                ),
            )
        ).all()
        puppet_uids = {str(row[0]) for row in inv_rows}
        trial_count = int(character.trial_puppet_count)

        removed_total = 0
        for preset in presets:
            try:
                units = json.loads(preset.units_json or "[]")
            except json.JSONDecodeError:
                units = []
            if not isinstance(units, list):
                units = []

            kept: list[dict[str, Any]] = []
            changed = False
            for raw in units:
                if not isinstance(raw, dict):
                    changed = True
                    removed_total += 1
                    continue
                kind = str(raw.get("unit_kind", ""))
                uid = str(raw.get("unit_uid", ""))
                ref = raw.get("ref_id")

                drop = False
                if kind == "avatar":
                    if not avatar_ok:
                        drop = True
                    else:
                        # ref / uid 与当前化身不一致也视为失效
                        if ref is not None and int(ref) != avatar_id:
                            drop = True
                        elif uid.startswith("avatar_") and uid[7:].isdigit():
                            if int(uid[7:]) != avatar_id:
                                drop = True
                elif kind == "pet":
                    pet_ref = ref
                    if pet_ref is None and uid.startswith("pet_") and uid[4:].isdigit():
                        pet_ref = int(uid[4:])
                    if pet_ref is None or int(pet_ref) not in pet_ids:
                        drop = True
                elif kind == "puppet":
                    if uid.startswith("puppet_") and uid[7:].isdigit():
                        idx = int(uid[7:])
                        if idx < 1 or idx > trial_count:
                            drop = True
                    elif uid not in puppet_uids:
                        drop = True
                # main 与其它 kind 保留（占位校验另走）

                if drop:
                    changed = True
                    removed_total += 1
                    continue
                kept.append(raw)

            if changed:
                preset.units_json = json.dumps(kept, ensure_ascii=False)
                preset.updated_at = now_utc()

        if removed_total:
            await self._session.flush()
            logger.info(
                "formation prune invalid units character_id=%s removed=%s",
                character.id,
                removed_total,
            )
        return removed_total

    async def list_presets(self, character: Character) -> dict[str, Any]:
        """
        列出全部预设 + 已解锁阵法 + Bench + 上阵上限。

        返回:
            dict: ``{presets, formations, bench, max_units}``。
        """
        await self.ensure_default_presets(character)
        # 读取前清洗失效棋子，避免「无化身仍占格且无法下阵」
        await self.prune_invalid_units_from_presets(character)
        result = await self._session.execute(
            select(FormationPreset)
            .where(FormationPreset.character_id == character.id)
            .order_by(FormationPreset.slot),
        )
        presets = [self.preset_to_dict(p) for p in result.scalars().all()]

        formations_cfg = get_game_config().formations
        formations = [
            self.formation_public_dict(
                f,
                unlocked=(
                    f.unlocked_by_default
                    or f.formation_id == "none"
                    or int(character.array_craft_level) >= int(f.required_array_level)
                ),
                major_realm=character.major_realm,
            )
            for f in formations_cfg.formations.values()
        ]
        board = get_game_config().board
        # 列表级 max_units 仍按默认部署区；单预设以当前阵法 effective 为准（前端另读）
        return {
            "presets": presets,
            "formations": formations,
            "bench": await self.bench_units(character),
            "max_units": max_units_for_realm(board, character.major_realm),
        }

    async def get_preset(self, character: Character, slot: int) -> FormationPreset:
        """按槽位取预设；不存在 → ``40040``。"""
        result = await self._session.execute(
            select(FormationPreset)
            .where(
                FormationPreset.character_id == character.id,
                FormationPreset.slot == slot,
            )
            .limit(1),
        )
        preset = result.scalar_one_or_none()
        if preset is None:
            raise AppError(code=40040, message="布阵预设不存在", http_status=404)
        return preset

    async def save_preset(
        self,
        character: Character,
        slot: int,
        *,
        name: str,
        role: str,
        formation_id: str,
        units: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        保存一个预设槽（校验占位后写库；**不**自动更新防守快照）。

        异常:
            AppError: ``40040`` 槽位非法；占位类错误见 ``validate_units``。
        """
        if slot < 0 or slot >= len(_DEFAULT_SLOTS):
            raise AppError(code=40040, message=f"预设槽位非法：{slot}", http_status=400)
        if role not in _VALID_ROLES:
            raise AppError(code=40000, message=f"无效预设定位：{role}", http_status=400)

        await self.validate_units(character, units, formation_id)

        await self.ensure_default_presets(character)
        preset = await self.get_preset(character, slot)
        preset.name = name.strip() or preset.name
        preset.role = role
        preset.formation_id = formation_id
        preset.units_json = json.dumps(units, ensure_ascii=False)
        preset.updated_at = now_utc()
        await self._session.flush()
        logger.info(
            "formation preset saved character_id=%s slot=%s formation=%s units=%s",
            character.id,
            slot,
            formation_id,
            len(units),
        )
        return self.preset_to_dict(preset)

    async def _get_role_preset(
        self,
        character: Character,
        role: str,
        fallback_slot: int,
    ) -> FormationPreset:
        """取某定位的首个预设；无则回退到指定槽位。"""
        await self.ensure_default_presets(character)
        result = await self._session.execute(
            select(FormationPreset)
            .where(
                FormationPreset.character_id == character.id,
                FormationPreset.role == role,
            )
            .order_by(FormationPreset.slot)
            .limit(1),
        )
        preset = result.scalar_one_or_none()
        if preset is not None:
            return preset
        return await self.get_preset(character, fallback_slot)

    async def get_attack_preset(
        self,
        character: Character,
        slot: int | None = None,
    ) -> FormationPreset:
        """
        取开战用进攻预设：显式槽位优先，否则首个 ``role=attack``（回退 slot=0）。
        """
        if slot is not None:
            await self.ensure_default_presets(character)
            return await self.get_preset(character, slot)
        return await self._get_role_preset(character, "attack", 0)

    async def get_defense_preset(self, character: Character) -> FormationPreset:
        """
        取防守预设：优先 ``role=defense``，无则回退 slot=1。

        用于快照序列化（设计 §4.2）。
        """
        return await self._get_role_preset(character, "defense", 1)

    def board_meta(self) -> dict[str, Any]:
        """``GET /formation/board-meta`` 的只读元数据。"""
        return board_meta_payload(get_game_config().board)
