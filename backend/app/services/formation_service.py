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
from app.constants.battle import (
    PIECE_KIND_AVATAR,
    PIECE_KIND_MAIN,
    PIECE_KIND_PET,
    PIECE_KIND_PUPPET,
    TRIAL_PUPPET_UID_PREFIX,
)
from app.constants.formation import (
    FORMATION_DEFAULT_PRESET_SLOTS,
    FORMATION_PRESET_ROLES,
    FORMATION_PRESET_SLOT_COUNT,
)
from app.constants.inventory import ITEM_TYPE_PUPPET, Occupancy
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
from app.constants.research import PRIVATE_ID_PREFIX, SOURCE_LABEL_CUSTOM_ZH, SOURCE_LABEL_OFFICIAL_ZH
from app.db.models.research import PrivateFormation
from app.domain.formation_blueprint import (
    FormationDeploySnapshot,
    deploy_config_to_dict,
    force_shifts_to_dict,
    parse_deploy_config,
    parse_force_shifts,
    parse_terrain_layout,
    resolve_formation_deploy,
    validate_blueprint,
)
from app.domain.avatar_rules import ERR_SOLO_FORMATION_INVALID
from app.schemas.common import AppError
from app.services.realm_config import (
    FormationDef,
    FormationLayerConfig,
    FormationTerrainCell,
    get_game_config,
)

logger = logging.getLogger(__name__)


def parse_assist_anchor(raw: str | None) -> dict[str, int] | None:
    """Parse ``{"x":int,"y":int}`` JSON; invalid/empty → None."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        x_coord = int(data["x"])
        y_coord = int(data["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x_coord <= 6 and 0 <= y_coord <= 6):
        return None
    return {"x": x_coord, "y": y_coord}


def dump_assist_anchor(anchor: dict[str, Any] | None) -> str | None:
    """Serialize assist anchor or None."""
    if not anchor:
        return None
    try:
        x_coord = int(anchor["x"])
        y_coord = int(anchor["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return json.dumps({"x": x_coord, "y": y_coord}, ensure_ascii=False)


def _parse_optional_layer(raw: Any) -> FormationLayerConfig | None:
    """Parse an optional four-symbol layer from a blueprint dict."""
    if not raw or not isinstance(raw, dict):
        return None
    layer_id = raw.get("id") or raw.get("layer_id")
    if not layer_id:
        return None
    return FormationLayerConfig(
        layer_id=str(layer_id),
        force_apply=bool(raw.get("force_apply", False)),
        counter_group=str(raw["counter_group"]) if raw.get("counter_group") else None,
        atk_mul=float(raw.get("atk_mul", 1.0)),
        hp_mul=float(raw.get("hp_mul", 1.0)),
    )


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
        查官方阵法定义；不存在或未解锁 → ``40044`` / ``40054``。

        自研阵请用 ``resolve_formation_def``（读私有表）。
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
    def is_custom_formation_id(formation_id: str) -> bool:
        """True when id uses the private custom prefix."""
        return str(formation_id).startswith(f"{PRIVATE_ID_PREFIX}:formation:")

    @staticmethod
    def def_from_blueprint(
        *,
        formation_id: str,
        name: str,
        blueprint: dict[str, Any],
        required_array_level: int = 0,
    ) -> FormationDef:
        """Build a FormationDef from a frozen/draft blueprint dict."""
        terrain_raw = blueprint.get("terrain") or []
        terrain_cells = tuple(
            FormationTerrainCell(
                x=int(item["x"]),
                y=int(item["y"]),
                terrain_type=str(item.get("type") or item.get("terrain_type") or ""),
                subtype=str(item.get("subtype") or ""),
            )
            for item in terrain_raw
        )
        deploy = parse_deploy_config(blueprint.get("deploy"))
        terrain_layout = parse_terrain_layout(
            blueprint.get("terrain_layout"),
            has_terrain=bool(terrain_cells),
        )
        force_shifts = parse_force_shifts(blueprint.get("force_shifts"))
        return FormationDef(
            formation_id=formation_id,
            name=name,
            level=int(blueprint.get("level") or 1),
            unlocked_by_default=True,
            required_array_level=required_array_level,
            terrain=terrain_cells,
            environment=_parse_optional_layer(blueprint.get("environment")),
            weather=_parse_optional_layer(blueprint.get("weather")),
            effect=_parse_optional_layer(blueprint.get("effect")),
            deploy=deploy,
            terrain_layout=terrain_layout,
            force_shifts=force_shifts,
        )

    async def resolve_formation_def(
        self,
        formation_id: str,
        character: Character | None = None,
    ) -> FormationDef:
        """Official YAML or the character's private frozen blueprint."""
        if not self.is_custom_formation_id(formation_id):
            return self.get_formation_def(formation_id, character)
        result = await self._session.execute(
            select(PrivateFormation).where(PrivateFormation.formation_id == formation_id).limit(1),
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(code=40044, message=f"阵法不存在：{formation_id}", http_status=404)
        if character is not None and int(row.character_id) != int(character.id):
            raise AppError(code=40044, message=f"阵法不存在：{formation_id}", http_status=404)
        blueprint = json.loads(row.blueprint_json or "{}")
        return self.def_from_blueprint(
            formation_id=row.formation_id,
            name=row.label_zh,
            blueprint=blueprint,
        )

    async def list_private_formation_public(self, character: Character) -> list[dict[str, Any]]:
        """Custom formations owned by the character, for the picker."""
        result = await self._session.execute(
            select(PrivateFormation)
            .where(PrivateFormation.character_id == character.id)
            .order_by(PrivateFormation.id),
        )
        items: list[dict[str, Any]] = []
        for row in result.scalars().all():
            blueprint = json.loads(row.blueprint_json or "{}")
            formation = self.def_from_blueprint(
                formation_id=row.formation_id,
                name=row.label_zh,
                blueprint=blueprint,
            )
            payload = self.formation_public_dict(
                formation,
                unlocked=True,
                major_realm=character.major_realm,
            )
            payload["source"] = row.source
            payload["source_label_zh"] = SOURCE_LABEL_CUSTOM_ZH
            payload["revision"] = int(row.revision)
            items.append(payload)
        return items

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
            "source": "official",
            "source_label_zh": SOURCE_LABEL_OFFICIAL_ZH,
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
        角色当前可上阵棋子（本体 + 装备栏已上阵化身/灵宠/傀儡）。

        化身须装备栏开关打开；灵宠须穿在灵宠槽；傀儡须编成板 occupancy=deployed。
        试炼木傀不再进 Bench（未编成视为未装备）。阵法页不再计算神识。

        Returns:
            list[dict]: ``[{unit_uid, unit_kind, name, enabled, ref_id?}, ...]``。
        """
        board = get_game_config().board
        settings = get_settings()
        bench: list[dict[str, Any]] = [
            {"unit_uid": "main", "unit_kind": PIECE_KIND_MAIN, "name": "本体", "enabled": True},
        ]

        # 化身：装备栏开关打开且已凝练
        avatar_gate = board.unit_kinds.get("avatar")
        avatar_enabled = bool(avatar_gate and avatar_gate.enabled and settings.avatar_enabled)
        result = await self._session.execute(
            select(Avatar).where(Avatar.character_id == character.id).limit(1),
        )
        avatar_row = result.scalar_one_or_none()
        if (
            avatar_row is not None
            and int(getattr(avatar_row, "is_deployed", 0) or 0) == 1
        ):
            tribulation_block = character.status == "tribulation"
            av_ok = avatar_row.status != "disabled" and not tribulation_block
            bench.append(
                {
                    "unit_uid": f"avatar_{avatar_row.id}",
                    "unit_kind": PIECE_KIND_AVATAR,
                    "name": avatar_row.name,
                    "enabled": avatar_enabled and av_ok,
                    "ref_id": avatar_row.id,
                },
            )

        # 灵宠：仅装备栏灵宠槽
        pet_gate = board.unit_kinds.get("pet")
        pet_enabled = bool(pet_gate and pet_gate.enabled and settings.pets_enabled)
        from app.constants.equipment import EQUIPMENT_SLOT_PET
        from app.db.models.character_equipment import CharacterEquipmentSlot
        from app.db.models.inventory_item import InventoryItem
        from app.services.pet_service import PetService

        await PetService(self._session).ensure_all_inventory_faces(character.id)
        pet_slot = (
            await self._session.execute(
                select(CharacterEquipmentSlot).where(
                    CharacterEquipmentSlot.character_id == character.id,
                    CharacterEquipmentSlot.slot == EQUIPMENT_SLOT_PET,
                ),
            )
        ).scalar_one_or_none()
        if pet_slot is not None and pet_slot.inventory_item_id is not None:
            inv_pet = await self._session.get(InventoryItem, int(pet_slot.inventory_item_id))
            pet_id = None
            nickname = None
            if inv_pet is not None:
                try:
                    meta = json.loads(inv_pet.meta_json or "{}")
                except json.JSONDecodeError:
                    meta = {}
                if meta.get("pet_id"):
                    pet_id = int(meta["pet_id"])
                nickname = meta.get("nickname")
            pet_row = None
            if pet_id is not None:
                pet_row = await self._session.get(Pet, pet_id)
            if pet_row is not None:
                bench.append(
                    {
                        "unit_uid": f"pet_{pet_row.id}",
                        "unit_kind": PIECE_KIND_PET,
                        "name": pet_row.nickname or nickname or pet_row.species_id,
                        "enabled": pet_enabled,
                        "ref_id": pet_row.id,
                    },
                )

        # 编成板已上阵真傀（与角色页「上阵傀儡」同一数据源；不含试炼木傀）
        puppet_gate = board.unit_kinds.get("puppet")
        puppet_enabled = bool(puppet_gate and puppet_gate.enabled)
        from app.services.equipment_service import EquipmentService
        from app.services.puppet_service import PuppetService

        eq_svc = EquipmentService(self._session)
        puppet_svc = PuppetService(self._session)
        loadout, _bag = await eq_svc.list_puppet_loadout(character.id)
        for entry in loadout:
            uid = str(entry["item_uid"])
            inv = await eq_svc._inventory_by_uid(character.id, uid)
            if inv is None:
                continue
            actor = await puppet_svc.ensure_for_inventory_item(inv)
            bench.append(
                {
                    "unit_uid": uid,
                    "unit_kind": PIECE_KIND_PUPPET,
                    "name": str(entry.get("label_zh") or actor.label_zh or inv.item_id or "傀儡"),
                    "enabled": puppet_enabled,
                    "ref_id": int(actor.id),
                },
            )

        # 客串化身不进棋子栏（AVATAR-D09：开战注入 assist_anchor）
        return bench

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    async def validate_units(
        self,
        character: Character,
        units: list[dict[str, Any]],
        formation_id: str,
        *,
        allow_guest: bool = False,
    ) -> None:
        """
        校验一份布阵（占位 + 编成归属 + M4 持有物）。

        异常:
            AppError: 40041/40042/40043/40044/40054/40057/40090。
        """
        board = get_game_config().board
        formation = await self.resolve_formation_def(formation_id, character)
        # 一次解析：禁停 + 有效区 + 上限
        snap = self.deploy_snapshot(formation)
        max_units = snap.max_units_for(
            board,
            character.major_realm,
            formation_max_units=formation.deploy.max_units,
        )

        try:
            validate_placement(
                units,
                board,
                max_units=max_units,
                blocked_cells=snap.blocked_cells,
                deploy_zone=snap.deploy_cells,
                require_main=True,
                allow_solo_avatar=False,
            )
        except PlacementError as exc:
            raise AppError(code=exc.code, message=exc.message, http_status=400) from exc

        bench = await self.bench_units(character)
        bench_index = {
            (str(b["unit_kind"]), str(b["unit_uid"])): b for b in bench
        }

        seen_uids: set[str] = set()
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

            if kind == PIECE_KIND_AVATAR:
                if character.status == "tribulation":
                    raise AppError(code=40042, message="渡劫中禁止化身上阵", http_status=400)
                guest_ids = parse_guest_unit_uid(uid)
                if guest_ids is not None:
                    if not allow_guest:
                        raise AppError(
                            code=40041,
                            message="道友助战请布置助战位置，不要把客串化身存进棋子栏",
                            http_status=400,
                        )
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
            elif kind == PIECE_KIND_PET:
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
            elif kind == PIECE_KIND_PUPPET:
                if uid.startswith(TRIAL_PUPPET_UID_PREFIX) and uid[len(TRIAL_PUPPET_UID_PREFIX) :].isdigit():
                    raise AppError(
                        code=40041,
                        message="傀儡未编成，不可上阵",
                        http_status=400,
                    )
                inv_result = await self._session.execute(
                    select(InventoryItem).where(
                        InventoryItem.character_id == character.id,
                        InventoryItem.item_uid == uid,
                        InventoryItem.item_type == ITEM_TYPE_PUPPET,
                    ).limit(1),
                )
                inv = inv_result.scalar_one_or_none()
                if inv is None:
                    raise AppError(code=40041, message=f"傀儡未持有：{uid}", http_status=400)
                from app.services.inventory_service import InventoryService
                from app.services.puppet_service import PuppetService

                if InventoryService(self._session).read_meta_occupancy(inv) != Occupancy.DEPLOYED:
                    raise AppError(
                        code=40041,
                        message=f"傀儡未编成，不可上阵：{uid}",
                        http_status=400,
                    )
                actor = await PuppetService(self._session).ensure_for_inventory_item(inv)
                if unit.get("ref_id") is not None and int(unit["ref_id"]) != int(actor.id):
                    raise AppError(code=40057, message="傀儡 ref_id 非法", http_status=400)
                unit["ref_id"] = int(actor.id)

            key = (kind, uid)
            if key in bench_index and not bench_index[key].get("enabled", False):
                raise AppError(code=40043, message=f"棋子类型未开放或未持有：{kind}", http_status=400)

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
                    "unit_kind": PIECE_KIND_MAIN,
                    "x": anchor_x,
                    "y": anchor_y,
                },
            ],
            ensure_ascii=False,
        )

    async def ensure_default_presets(self, character: Character) -> None:
        """确保角色拥有默认五槽预设（惰性种子，兼容旧号缺槽）。"""
        result = await self._session.execute(
            select(FormationPreset.slot).where(
                FormationPreset.character_id == character.id,
            ),
        )
        existing_slots = {row[0] for row in result.all()}
        created = False
        default_units = self._default_units_json()
        for slot, name, role in FORMATION_DEFAULT_PRESET_SLOTS:
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

        删除该角色全部布阵行后，按默认五槽重新插入：
        ``formation_id=none``、仅本体锚点单位。内部 role 仍区分攻/守回退。

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
            FORMATION_PRESET_SLOT_COUNT,
        )
        return FORMATION_PRESET_SLOT_COUNT

    @staticmethod
    def preset_to_dict(preset: FormationPreset) -> dict[str, Any]:
        """预设实体 → 响应 dict。"""
        return {
            "slot": preset.slot,
            "name": preset.name,
            "role": preset.role,
            "formation_id": preset.formation_id,
            "units": json.loads(preset.units_json or "[]"),
            "assist_anchor": parse_assist_anchor(
                getattr(preset, "assist_anchor_json", None),
            ),
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
            avatar_row is not None
            and str(avatar_row.status) != "disabled"
            and int(getattr(avatar_row, "is_deployed", 0) or 0) == 1
        )
        avatar_id = int(avatar_row.id) if avatar_row is not None else None

        pet_ids: set[int] = set()
        from app.constants.equipment import EQUIPMENT_SLOT_PET
        from app.db.models.character_equipment import CharacterEquipmentSlot

        pet_slot = (
            await self._session.execute(
                select(CharacterEquipmentSlot).where(
                    CharacterEquipmentSlot.character_id == character.id,
                    CharacterEquipmentSlot.slot == EQUIPMENT_SLOT_PET,
                ),
            )
        ).scalar_one_or_none()
        if pet_slot is not None and pet_slot.inventory_item_id is not None:
            inv_pet = await self._session.get(InventoryItem, int(pet_slot.inventory_item_id))
            if inv_pet is not None:
                try:
                    meta = json.loads(inv_pet.meta_json or "{}")
                except json.JSONDecodeError:
                    meta = {}
                if meta.get("pet_id"):
                    pet_ids.add(int(meta["pet_id"]))

        inv_rows = (
            await self._session.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == character.id,
                    InventoryItem.item_type == ITEM_TYPE_PUPPET,
                ),
            )
        ).scalars().all()
        from app.services.inventory_service import InventoryService

        inv_svc = InventoryService(self._session)
        puppet_uids = {
            str(row.item_uid)
            for row in inv_rows
            if inv_svc.read_meta_occupancy(row) == Occupancy.DEPLOYED
        }

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
                from app.services.avatar_assist_service import parse_guest_unit_uid

                guest_ids = parse_guest_unit_uid(uid)
                if guest_ids is not None:
                    # 旧预设把客串当棋子：迁到助战锚点后撤下
                    if parse_assist_anchor(getattr(preset, "assist_anchor_json", None)) is None:
                        try:
                            preset.assist_anchor_json = dump_assist_anchor(
                                {"x": int(raw.get("x")), "y": int(raw.get("y"))},
                            )
                        except (TypeError, ValueError):
                            pass
                    drop = True
                elif kind == PIECE_KIND_AVATAR:
                    if not avatar_ok:
                        drop = True
                    else:
                        # ref / uid 与当前化身不一致也视为失效
                        if ref is not None and int(ref) != avatar_id:
                            drop = True
                        elif uid.startswith("avatar_") and uid[7:].isdigit():
                            if int(uid[7:]) != avatar_id:
                                drop = True
                elif kind == PIECE_KIND_PET:
                    pet_ref = ref
                    if pet_ref is None and uid.startswith("pet_") and uid[4:].isdigit():
                        pet_ref = int(uid[4:])
                    if pet_ref is None or int(pet_ref) not in pet_ids:
                        drop = True
                elif kind == PIECE_KIND_PUPPET:
                    is_trial = uid.startswith(TRIAL_PUPPET_UID_PREFIX) and uid[
                        len(TRIAL_PUPPET_UID_PREFIX) :
                    ].isdigit()
                    if is_trial or uid not in puppet_uids:
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
        formations.extend(await self.list_private_formation_public(character))
        board = get_game_config().board
        # 列表级 max_units 仍按默认部署区；单预设以当前阵法 effective 为准（前端另读）
        return {
            "presets": presets,
            "formations": formations,
            "bench": await self.bench_units(character),
            "max_units": max_units_for_realm(board, character.major_realm),
            "assist_guest": await self._assist_guest_summary(character),
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
        assist_anchor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        保存一个预设槽（校验占位后写库；**不**自动更新防守快照）。

        异常:
            AppError: ``40040`` 槽位非法；占位类错误见 ``validate_units``。
        """
        if slot < 0 or slot >= FORMATION_PRESET_SLOT_COUNT:
            raise AppError(code=40040, message=f"预设槽位非法：{slot}", http_status=400)
        if role not in FORMATION_PRESET_ROLES:
            raise AppError(code=40000, message=f"无效预设定位：{role}", http_status=400)

        from app.services.avatar_assist_service import parse_guest_unit_uid

        units = [
            unit
            for unit in units
            if parse_guest_unit_uid(str(unit.get("unit_uid", ""))) is None
        ]
        await self.validate_units(character, units, formation_id)
        await self._validate_assist_anchor(character, units, formation_id, assist_anchor)

        await self.ensure_default_presets(character)
        preset = await self.get_preset(character, slot)
        preset.name = name.strip() or preset.name
        preset.role = role
        preset.formation_id = formation_id
        preset.units_json = json.dumps(units, ensure_ascii=False)
        preset.assist_anchor_json = dump_assist_anchor(assist_anchor)
        preset.updated_at = now_utc()
        await self._session.flush()
        logger.info(
            "formation preset saved character_id=%s slot=%s formation=%s units=%s anchor=%s",
            character.id,
            slot,
            formation_id,
            len(units),
            bool(assist_anchor),
        )
        return self.preset_to_dict(preset)

    async def _validate_assist_anchor(
        self,
        character: Character,
        units: list[dict[str, Any]],
        formation_id: str,
        assist_anchor: dict[str, Any] | None,
    ) -> None:
        """助战锚点须在可部署区、不与棋子重叠，并预留一格上阵上限。"""
        parsed = parse_assist_anchor(dump_assist_anchor(assist_anchor)) if assist_anchor else None
        if parsed is None:
            if assist_anchor:
                raise AppError(code=40041, message="助战位置坐标非法", http_status=400)
            return
        board = get_game_config().board
        formation = await self.resolve_formation_def(formation_id, character)
        snap = self.deploy_snapshot(formation)
        max_units = snap.max_units_for(
            board,
            character.major_realm,
            formation_max_units=formation.deploy.max_units,
        )
        cell = (int(parsed["x"]), int(parsed["y"]))
        if cell in snap.blocked_cells:
            raise AppError(code=40041, message="助战位置被阵法地形占用", http_status=400)
        if cell not in snap.deploy_cells:
            raise AppError(code=40041, message="助战位置不在可部署区", http_status=400)
        if any(int(unit.get("x", -1)) == cell[0] and int(unit.get("y", -1)) == cell[1] for unit in units):
            raise AppError(code=40041, message="助战位置不可与已有棋子重叠", http_status=400)
        if len(units) + 1 > max_units:
            raise AppError(
                code=40041,
                message="助战位置计入上阵上限，请先撤下一枚棋子",
                http_status=400,
            )

    async def _assist_guest_summary(self, character: Character) -> dict[str, Any] | None:
        """当前借入的道友化身摘要（阵法页助战栏展示；无会话为 None）。"""
        from app.services.avatar_assist_service import AvatarAssistService, guest_unit_uid

        assist_svc = AvatarAssistService(self._session)
        sessions = await assist_svc.list_active_for_borrower(character.id)
        if not sessions:
            return None
        sess = sessions[0]
        owner = await self._session.get(Character, sess.owner_character_id)
        avatar_guest = await self._session.get(Avatar, sess.avatar_id)
        if avatar_guest is None or str(avatar_guest.status) == "disabled":
            return None
        owner_label = owner.name if owner else str(sess.owner_character_id)
        return {
            "session_id": sess.id,
            "unit_uid": guest_unit_uid(sess.owner_character_id, sess.avatar_id),
            "name": f"{owner_label}·{avatar_guest.name}",
            "owner_character_id": sess.owner_character_id,
            "ref_id": avatar_guest.id,
        }

    async def inject_assist_guest(
        self,
        character: Character,
        units: list[dict[str, Any]],
        assist_anchor: dict[str, int] | None,
        *,
        formation_id: str,
    ) -> list[dict[str, Any]]:
        """
        PVE 开战：有活跃助战会话则把客串化身注入锚点。

        无会话：原样返回。有会话无锚点 → 40093。
        """
        summary = await self._assist_guest_summary(character)
        if summary is None:
            return units
        if assist_anchor is None:
            raise AppError(
                code=ERR_SOLO_FORMATION_INVALID,
                message="请先在阵法页布置助战位置",
                http_status=400,
            )
        x_coord = int(assist_anchor["x"])
        y_coord = int(assist_anchor["y"])
        if any(int(unit.get("x", -1)) == x_coord and int(unit.get("y", -1)) == y_coord for unit in units):
            raise AppError(
                code=ERR_SOLO_FORMATION_INVALID,
                message="助战位置与已有棋子重叠",
                http_status=400,
            )
        board = get_game_config().board
        formation = await self.resolve_formation_def(formation_id, character)
        snap = self.deploy_snapshot(formation)
        max_units = snap.max_units_for(
            board,
            character.major_realm,
            formation_max_units=formation.deploy.max_units,
        )
        if len(units) + 1 > max_units:
            raise AppError(
                code=40041,
                message="上阵数量已达上限，请先给助战留一格",
                http_status=400,
            )
        injected = [dict(unit) for unit in units]
        injected.append(
            {
                "unit_uid": summary["unit_uid"],
                "unit_kind": PIECE_KIND_AVATAR,
                "x": x_coord,
                "y": y_coord,
                "ref_id": summary["ref_id"],
                "owner_character_id": summary["owner_character_id"],
                "is_guest": True,
            },
        )
        return injected

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
