"""
双修应用服务（M7 L7）：邀约→接受→宽衣→开始（高潮循环）→结算 / 时长榜。

权威：修为变动与榜分只在服务端；高潮循环走 ``simulate_climax_loop`` + DiceService RNG。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc, to_utc_iso
from app.db.models import Character, User
from app.db.models.bond import BOND_KIND_COMPANION, BOND_KIND_VESSEL
from app.db.models.dual_cultivation import DualCultivationSession, DualRankScore
from app.db.models.social_trade import FaceTradeSession
from app.domain.activity_mutex import is_productive_idle
from app.domain.dual_cultivation_rules import (
    ACTIVE_SESSION_STATUSES,
    BOARD_DURATION_TOTAL,
    BOARD_KEYS,
    board_key_for,
    gender_label_zh,
    normalize_gender,
    normalize_role,
    opposite_role,
    resolve_dice_tier,
    resolve_extract_settlement,
    resolve_mutual_gain,
    resolve_transfer_settlement,
    simulate_climax_loop,
    status_label_zh,
    technique_allows_pair,
)
from app.domain.ws_protocol import TYPE_DUAL_INVITE, TYPE_DUAL_UPDATE
from app.schemas.common import AppError
from app.services.bond_service import BondService
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.dice_service import DiceService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm
from app.services.stamina_service import StaminaService
from app.services.ws_hub_service import get_ws_hub

logger = logging.getLogger(__name__)


def require_dual_enabled() -> None:
    """双修总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "dual_cultivation_enabled", True)):
        raise AppError(code=40000, message="双修系统未开放", http_status=403)


class DualCultivationService:
    """双修用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """注入会话。"""
        self._session = session
        self._gate = PlayGate(session)
        self._ledger = CurrencyLedgerService(session)
        self._dice = DiceService(session)
        self._bonds = BondService(session)
        self._stamina = StaminaService(session)

    def _cfg(self):
        return get_game_config().dual_cultivation

    def _technique(self, technique_id: str) -> dict[str, Any]:
        tech = self._cfg().techniques.get(technique_id)
        if not tech:
            raise AppError(code=40162, message="双修功法不存在", http_status=400)
        return dict(tech)

    async def me(self, user: User) -> dict[str, Any]:
        """当前会话、功法目录、性别状态、道侣/炉鼎选人列表。"""
        require_dual_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        session = await self._active_session_for(character.id)
        gender = normalize_gender(getattr(character, "gender", None))
        companions = await self._bonds.list_active_peers(character.id, BOND_KIND_COMPANION)
        vessels = await self._bonds.list_active_peers(character.id, BOND_KIND_VESSEL)
        return {
            "gender": gender,
            "gender_label_zh": gender_label_zh(gender),
            "needs_gender": gender is None,
            "session": (
                await self._session_public(session, viewer_character_id=character.id)
                if session
                else None
            ),
            "techniques": self._techniques_public(),
            "invite_targets": {
                "companions": companions,
                "vessels": vessels,
                "vessel_invite_enabled": False,
                "hint_zh": "仅可从道侣或炉鼎中选择双修对象",
            },
            "config": {
                "invite_expire_sec": int(self._cfg().invite_expire_sec),
                "undress_expire_sec": int(self._cfg().undress_expire_sec),
                "max_rerolls": int(self._cfg().max_rerolls),
                "spirit_stone_cost": int(self._cfg().spirit_stone_cost),
                "cultivation_gap_scale": int(self._cfg().cultivation_gap_scale),
                "stamina_costs": dict(self._cfg().stamina_costs or {}),
            },
        }

    async def set_gender(self, user: User, gender: str) -> dict[str, Any]:
        """
        存量角色一次性补选性别；已设定则拒绝。

        Args:
            user: 当前用户。
            gender: male|female。

        Returns:
            更新后的 me 摘要。
        """
        require_dual_enabled()
        character = await self._gate.require_character(user)
        normalized = normalize_gender(gender)
        if normalized is None:
            raise AppError(code=40160, message="性别须为 male 或 female", http_status=400)
        existing = normalize_gender(getattr(character, "gender", None))
        if existing is not None:
            raise AppError(code=40160, message="道途阴阳已定，不可自行更改", http_status=400)
        character.gender = normalized
        character.updated_at = now_utc()
        await self._session.flush()
        logger.info("dual set_gender character=%s gender=%s", character.id, normalized)
        return await self.me(user)

    async def invite(
        self,
        user: User,
        *,
        technique_id: str,
        target_character_id: int | None,
        bond_kind: str,
        inviter_role: str | None = None,
        dice_seed: int | None = None,
        target_name: str | None = None,
    ) -> dict[str, Any]:
        """
        发起邀约：仅可从道侣或炉鼎中按角色 id 选择。

        道侣：对方可接受/拒绝；超时取消。
        炉鼎：对方不可拒绝；超时自动接受进入宽衣阶段。
        """
        require_dual_enabled()
        if target_name:
            raise AppError(
                code=40161,
                message="不可手填道号，请从道侣或炉鼎中选择",
                http_status=400,
            )
        if target_character_id is None:
            raise AppError(code=40161, message="请选择双修对象", http_status=400)
        kind = str(bond_kind or "").strip().lower()
        if kind not in (BOND_KIND_COMPANION, BOND_KIND_VESSEL):
            raise AppError(code=40161, message="双修对象须为道侣或炉鼎", http_status=400)

        inviter, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._assert_playable(inviter)
        self._require_gender(inviter)
        tech = self._technique(technique_id)
        invitee = await self._resolve_target(
            target_character_id=int(target_character_id),
            target_name=None,
            exclude_id=inviter.id,
        )
        await self._bonds.require_active_bond(inviter.id, invitee.id, kind)
        await self._assert_playable(invitee)
        self._require_gender(invitee)
        ok, reason = technique_allows_pair(
            tech,
            gender_a=normalize_gender(inviter.gender),
            gender_b=normalize_gender(invitee.gender),
        )
        if not ok:
            raise AppError(code=40160, message=reason, http_status=400)
        self._assert_realm_min(inviter, tech)
        self._assert_realm_min(invitee, tech)
        # 终态（已取消/成交/结算等）不挡；进行中面交/双修/队伍·团队/秘境视为正忙
        await self._assert_available_for_dual(inviter, who_zh="你")
        await self._assert_available_for_dual(invitee, who_zh="对方")

        role = normalize_role(inviter_role)
        status = "inviting"
        cost = int(self._cfg().spirit_stone_cost)
        if cost > 0:
            await self._ledger.adjust_spirit_stones(
                inviter,
                delta=-cost,
                reason="dual_invite",
                note_zh=f"双修邀约·{tech.get('label') or technique_id}",
                ref_type="dual",
                ref_id=technique_id,
            )

        expire_sec = int(self._cfg().invite_expire_sec)
        current = now_utc()
        row = DualCultivationSession(
            inviter_character_id=inviter.id,
            invitee_character_id=invitee.id,
            technique_id=technique_id,
            bond_kind=kind,
            inviter_role=role,
            auto_forced=False,
            status=status,
            invite_expire_at=(
                current + timedelta(seconds=expire_sec) if expire_sec > 0 else None
            ),
            dice_seed=dice_seed,
            created_at=current,
        )
        self._session.add(row)
        await self._session.flush()
        tech_label = tech.get("label") or technique_id
        logger.info(
            "dual invite id=%s inviter=%s invitee=%s tech=%s bond=%s",
            row.id,
            inviter.id,
            invitee.id,
            technique_id,
            kind,
        )
        if kind == BOND_KIND_VESSEL:
            msg = f"已邀请炉鼎「{invitee.name}」双修「{tech_label}」（60 秒未接受将自动接受）"
            invite_tip = (
                f"「{inviter.name}」邀你双修「{tech_label}」；"
                "可接受不可拒绝，60 秒后自动接受"
            )
        else:
            msg = f"已邀请道侣「{invitee.name}」双修「{tech_label}」（60 秒未接受将取消）"
            invite_tip = (
                f"「{inviter.name}」邀你双修「{tech_label}」；"
                "60 秒未接受将取消"
            )
        await self._push_dual(
            int(row.invitee_character_id),
            TYPE_DUAL_INVITE,
            {
                "session_id": row.id,
                "event": "invite",
                "bond_kind": kind,
                "from_character_id": inviter.id,
                "from_name": inviter.name,
                "technique_id": technique_id,
                "technique_label": tech_label,
                "message": invite_tip,
            },
        )
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=inviter.id,
            ),
            "message": msg,
        }

    async def confirm(self, user: User, session_id: int) -> dict[str, Any]:
        """受邀方确认 → accepted（启动宽衣倒计时）；若在修炼则自动停止。"""
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if row.status != "inviting":
            raise AppError(code=40161, message="会话不在邀约态", http_status=400)
        if int(row.invitee_character_id) != int(character.id):
            raise AppError(code=40161, message="仅受邀方可确认", http_status=403)
        await self._assert_playable(character)
        await self._assert_available_for_dual(
            character,
            who_zh="你",
            skip_dual_session=True,
            skip_idle=True,
        )
        await self._stop_cultivation_if_needed(character)
        await self._accept_session(row, auto=False)
        tech = self._technique(row.technique_id)
        tech_label = tech.get("label") or row.technique_id
        await self._push_dual(
            int(row.inviter_character_id),
            TYPE_DUAL_UPDATE,
            {
                "session_id": row.id,
                "event": "accepted",
                "bond_kind": getattr(row, "bond_kind", None),
                "message": f"「{character.name}」已接受双修「{tech_label}」",
            },
        )
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=character.id,
            ),
            "message": "已接受邀约，请宽衣解带",
        }

    async def undress(self, user: User, session_id: int) -> dict[str, Any]:
        """受邀方宽衣 → undressed。"""
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        effective = self._effective_status(row.status)
        if effective != "accepted":
            raise AppError(code=40161, message="当前不可宽衣", http_status=400)
        if int(row.invitee_character_id) != int(character.id):
            raise AppError(code=40161, message="仅受邀方可宽衣", http_status=403)
        await self._mark_undressed(row, auto=False)
        await self._push_dual(
            int(row.inviter_character_id),
            TYPE_DUAL_UPDATE,
            {
                "session_id": row.id,
                "event": "undressed",
                "bond_kind": getattr(row, "bond_kind", None),
                "message": f"「{character.name}」已宽衣，可开始双修",
            },
        )
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=character.id,
            ),
            "message": "已宽衣，等待对方开始",
        }

    async def start(self, user: User, session_id: int) -> dict[str, Any]:
        """邀请方开始：高潮循环 → 结算 → settled。"""
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if row.status != "undressed":
            raise AppError(code=40161, message="须双方就绪后再开始", http_status=400)
        if int(row.inviter_character_id) != int(character.id):
            raise AppError(code=40161, message="仅邀请方可开始", http_status=403)

        tech = self._technique(row.technique_id)
        inviter = character
        invitee = await self._session.get(Character, row.invitee_character_id)
        if invitee is None:
            raise AppError(code=40005, message="受邀方角色不存在", http_status=404)
        stamina_meta = await self._spend_dual_stamina(
            tech=tech,
            inviter=inviter,
            invitee=invitee,
        )

        row.status = "running"
        row.started_at = now_utc()
        await self._session.flush()

        climax_cfg = dict(self._cfg().climax or {})
        technique_mod = float(tech.get("climax_mod") or 0.0)
        rng = DiceService.make_rng(row.dice_seed)
        climax_meta = simulate_climax_loop(
            rng,
            base_chance=float(climax_cfg.get("base_chance") or 0.03),
            growth_per_tick=float(climax_cfg.get("growth_per_tick") or 0.012),
            chance_cap=float(climax_cfg.get("chance_cap") or 0.85),
            max_ticks=int(climax_cfg.get("max_ticks") or 400),
            tick_jitter=float(climax_cfg.get("tick_jitter") or 0.2),
            technique_mod=technique_mod,
            partner_mod=technique_mod,
            env_mod=float(climax_cfg.get("env_mod") or 0.0),
        )
        duration_sec = int(climax_meta["duration_sec"])
        row.duration_sec = duration_sec
        row.yield_mult = 1.0
        await self._session.flush()
        logger.info(
            "dual climax session=%s %s",
            row.id,
            climax_meta.get("log_zh"),
        )

        summary = await self._settle_session(
            row,
            duration_sec=duration_sec,
            climax_meta=climax_meta,
        )
        summary["stamina"] = stamina_meta
        row.settle_summary_json = json.dumps(summary, ensure_ascii=False)
        await self._session.flush()
        tech_label = tech.get("label") or row.technique_id
        settle_msg = str(climax_meta.get("log_zh") or "双修已结算")
        if int(duration_sec) > 0:
            settle_msg = f"{settle_msg}；已按秒计入时长榜"
        payload = {
            "session_id": row.id,
            "event": "settled",
            "bond_kind": getattr(row, "bond_kind", None),
            "message": f"双修「{tech_label}」已结束：{settle_msg}",
            "summary": summary,
        }
        await self._push_dual(int(row.inviter_character_id), TYPE_DUAL_UPDATE, payload)
        await self._push_dual(int(row.invitee_character_id), TYPE_DUAL_UPDATE, payload)

        from app.services.character_service import CharacterService, character_public_to_dict

        svc = CharacterService(self._session)
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=character.id,
            ),
            "summary": summary,
            "message": settle_msg,
            "character": character_public_to_dict(await svc.enrich_public(character)),
        }

    async def roll(
        self,
        user: User,
        session_id: int,
        *,
        dice_seed: int | None = None,
    ) -> dict[str, Any]:
        """
        掷骰：首次 confirmed→running；可重掷次数由 YAML。

        Args:
            user: 任一方均可掷。
            session_id: 会话 id。
            dice_seed: 可选复现种子。
        """
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if int(character.id) not in (
            int(row.inviter_character_id),
            int(row.invitee_character_id),
        ):
            raise AppError(code=40161, message="非本场双修成员", http_status=403)
        if row.status not in ("confirmed", "running"):
            raise AppError(code=40161, message="当前不可掷骰（请使用开始流程）", http_status=400)

        max_rerolls = int(self._cfg().max_rerolls)
        if row.status == "running":
            if int(row.rerolls_used) >= max_rerolls:
                raise AppError(code=40161, message="重掷次数已用尽", http_status=400)
            row.rerolls_used = int(row.rerolls_used) + 1
        elif row.status == "confirmed":
            row.status = "running"

        inviter = await self._session.get(Character, row.inviter_character_id)
        if inviter is None:
            raise AppError(code=40005, message="邀请方角色不存在", http_status=404)
        seed = dice_seed if dice_seed is not None else row.dice_seed
        rng = DiceService.make_rng(seed)
        roll_value, bounds = await self._dice.roll_for_character(
            inviter,
            purpose="dual_cultivation",
            rng=rng,
        )
        tier = resolve_dice_tier(list(self._cfg().dice_tiers), int(roll_value))
        row.roll_value = int(roll_value)
        row.roll_lo = int(bounds.lo)
        row.roll_hi = int(bounds.hi)
        row.effect_tier = str(tier.get("effect_tier") or "mid")
        row.yield_mult = float(tier.get("yield_mult") or 1.0)
        row.duration_sec = int(tier.get("duration_sec") or 40)
        row.dice_label_zh = str(tier.get("label_zh") or "")
        if seed is not None:
            row.dice_seed = int(seed)
        await self._session.flush()
        logger.info(
            "dual roll session=%s roll=%s tier=%s mult=%s",
            row.id,
            roll_value,
            row.effect_tier,
            row.yield_mult,
        )
        return {
            "session": await self._session_public(row),
            "dice": {
                "purpose": "dual_cultivation",
                "roll": int(roll_value),
                "lo": int(bounds.lo),
                "hi": int(bounds.hi),
                "effect_tier": row.effect_tier,
                "yield_mult": row.yield_mult,
                "duration_sec": row.duration_sec,
                "label_zh": row.dice_label_zh,
                "rerolls_used": int(row.rerolls_used),
                "max_rerolls": max_rerolls,
            },
            "message": f"掷得{row.dice_label_zh or row.effect_tier}（{roll_value}）",
        }

    async def settle(self, user: User, session_id: int) -> dict[str, Any]:
        """结束领取（兼容旧掷骰流程；主流程由 start 自动结算）。"""
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if int(character.id) not in (
            int(row.inviter_character_id),
            int(row.invitee_character_id),
        ):
            raise AppError(code=40161, message="非本场双修成员", http_status=403)
        if row.status != "running":
            raise AppError(code=40161, message="须先开始双修后再结算", http_status=400)
        if row.roll_value is None and row.duration_sec is None:
            raise AppError(code=40161, message="缺少时长快照", http_status=400)

        duration_sec = int(row.duration_sec or 0)
        summary = await self._settle_session(row, duration_sec=duration_sec, climax_meta=None)

        from app.services.character_service import CharacterService, character_public_to_dict

        svc = CharacterService(self._session)
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=character.id,
            ),
            "summary": summary,
            "message": "双修已结算",
            "character": character_public_to_dict(await svc.enrich_public(character)),
        }

    async def _settle_session(
        self,
        row: DualCultivationSession,
        *,
        duration_sec: int,
        climax_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        内部结算：按功法 mode 发放修为与榜分。

        Args:
            row: 双修会话（须 running）。
            duration_sec: 本场秒数（高潮循环或掷骰）。
            climax_meta: 高潮循环摘要；可为空（旧掷骰路径）。

        Returns:
            结算摘要 dict。
        """
        tech = self._technique(row.technique_id)
        inviter = await self._session.get(Character, row.inviter_character_id)
        invitee = await self._session.get(Character, row.invitee_character_id)
        if inviter is None or invitee is None:
            raise AppError(code=40005, message="双修角色缺失", http_status=404)

        mult = float(row.yield_mult if row.yield_mult is not None else 1.0)
        base = int(tech.get("base_yield") or 0)
        gap_scale = int(self._cfg().cultivation_gap_scale)
        mode = str(tech.get("mode") or "mutual_gain")
        inviter_role = normalize_role(getattr(row, "inviter_role", None))
        invitee_role = opposite_role(inviter_role)
        summary: dict[str, Any] = {
            "mode": mode,
            "technique_id": row.technique_id,
            "technique_label": tech.get("label"),
            "yield_mult": mult,
            "effect_tier": row.effect_tier,
            "duration_sec": int(duration_sec),
            "base_yield": base,
            "inviter_role": inviter_role,
            "invitee_role": invitee_role,
            "bond_kind": getattr(row, "bond_kind", None),
        }
        if climax_meta:
            summary["insert_count"] = int(climax_meta.get("insert_count") or 0)
            summary["climax_tick"] = int(climax_meta.get("climax_tick") or 0)
            summary["log_zh"] = str(climax_meta.get("log_zh") or "")

        if mode == "mutual_gain":
            mutual = resolve_mutual_gain(
                base_yield=base,
                duration_sec=int(duration_sec),
                yield_mult=mult,
                cultivation_a=int(inviter.cultivation_points),
                cultivation_b=int(invitee.cultivation_points),
                gap_scale=gap_scale,
            )
            gained = int(mutual["gain_each"])
            inviter.cultivation_points = int(inviter.cultivation_points) + gained
            invitee.cultivation_points = int(invitee.cultivation_points) + gained
            summary["scaled_yield"] = gained
            summary["inviter_gain"] = gained
            summary["invitee_gain"] = gained
            summary["mutual"] = mutual
            await self._add_duration_ranks(
                inviter,
                role=inviter_role,
                duration_sec=int(duration_sec),
            )
            await self._add_duration_ranks(
                invitee,
                role=invitee_role,
                duration_sec=int(duration_sec),
            )
        elif mode == "transfer":
            direction = str(tech.get("transfer_direction") or "inviter_to_invitee")
            if direction == "invitee_to_inviter":
                giver, receiver = invitee, inviter
                giver_role, receiver_role = invitee_role, inviter_role
            else:
                giver, receiver = inviter, invitee
                giver_role, receiver_role = inviter_role, invitee_role
            cost_pool = int(tech.get("transfer_cost_from_giver") or base or 0)
            transfer = resolve_transfer_settlement(
                base_transfer=cost_pool,
                duration_sec=int(duration_sec),
                yield_mult=mult,
                giver_cultivation=int(giver.cultivation_points),
                receiver_cultivation=int(receiver.cultivation_points),
                gap_scale=gap_scale,
            )
            giver_cost = int(transfer["giver_cost"])
            receiver_delta = int(transfer["receiver_delta"])
            if giver_cost > 0 and int(giver.cultivation_points) < giver_cost:
                raise AppError(
                    code=40162,
                    message=f"传方修为池不足（需 {giver_cost}）",
                    http_status=400,
                )
            stone_cost = int(tech.get("giver_spirit_stone_cost") or 0)
            if stone_cost > 0:
                await self._ledger.adjust_spirit_stones(
                    giver,
                    delta=-stone_cost,
                    reason="dual_transfer",
                    note_zh=f"双修传修为·{tech.get('label')}",
                    ref_type="dual",
                    ref_id=str(row.id),
                )
            if giver_cost > 0:
                giver.cultivation_points = int(giver.cultivation_points) - giver_cost
            receiver.cultivation_points = int(receiver.cultivation_points) + receiver_delta
            summary["giver_id"] = giver.id
            summary["receiver_id"] = receiver.id
            summary["giver_pool_cost"] = giver_cost
            summary["receiver_gain"] = receiver_delta
            summary["scaled_yield"] = receiver_delta
            summary["transfer"] = transfer
            await self._add_duration_ranks(giver, role=giver_role, duration_sec=int(duration_sec))
            await self._add_duration_ranks(
                receiver,
                role=receiver_role,
                duration_sec=int(duration_sec),
            )
        elif mode == "extract":
            direction = str(tech.get("extract_direction") or "inviter_from_invitee")
            if direction == "invitee_from_inviter":
                extractor, target = invitee, inviter
                extractor_role, target_role = invitee_role, inviter_role
            else:
                extractor, target = inviter, invitee
                extractor_role, target_role = inviter_role, invitee_role
            cost_pool = int(tech.get("extract_cost_from_target") or base or 0)
            extract = resolve_extract_settlement(
                base_extract=cost_pool,
                duration_sec=int(duration_sec),
                yield_mult=mult,
                extractor_cultivation=int(extractor.cultivation_points),
                target_cultivation=int(target.cultivation_points),
                gap_scale=gap_scale,
            )
            target_cost = int(extract["target_cost"])
            extractor_delta = int(extract["extractor_delta"])
            if target_cost > 0 and int(target.cultivation_points) < target_cost:
                raise AppError(
                    code=40162,
                    message=f"被索取方修为池不足（需 {target_cost}）",
                    http_status=400,
                )
            if target_cost > 0:
                target.cultivation_points = int(target.cultivation_points) - target_cost
            # 索取方可正可负（初始转化率为负时反噬）
            extractor.cultivation_points = int(extractor.cultivation_points) + extractor_delta
            if int(extractor.cultivation_points) < 0:
                extractor.cultivation_points = 0
            summary["extractor_id"] = extractor.id
            summary["target_id"] = target.id
            summary["target_pool_cost"] = target_cost
            summary["extractor_gain"] = extractor_delta
            summary["scaled_yield"] = extractor_delta
            summary["extract"] = extract
            await self._add_duration_ranks(
                extractor,
                role=extractor_role,
                duration_sec=int(duration_sec),
            )
            await self._add_duration_ranks(
                target,
                role=target_role,
                duration_sec=int(duration_sec),
            )
        else:
            raise AppError(code=40162, message="未知双修功法模式", http_status=400)

        current = now_utc()
        inviter.updated_at = current
        invitee.updated_at = current
        row.status = "settled"
        row.settled_at = current
        row.settle_summary_json = json.dumps(summary, ensure_ascii=False)
        await self._session.flush()
        logger.info(
            "dual settle session=%s mode=%s duration=%s summary_keys=%s",
            row.id,
            mode,
            duration_sec,
            list(summary.keys()),
        )
        return summary

    async def cancel(self, user: User, session_id: int) -> dict[str, Any]:
        """取消邀约或中止未结算会话（炉鼎受邀方不可在邀约态取消）。"""
        require_dual_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if int(character.id) not in (
            int(row.inviter_character_id),
            int(row.invitee_character_id),
        ):
            raise AppError(code=40161, message="非本场双修成员", http_status=403)
        allowed = ("inviting", "accepted", "undressed", "confirmed")
        if row.status not in allowed:
            raise AppError(code=40161, message="会话已结束", http_status=400)
        if (
            row.status == "inviting"
            and int(row.invitee_character_id) == int(character.id)
            and str(getattr(row, "bond_kind", "") or "").lower() == BOND_KIND_VESSEL
        ):
            raise AppError(code=40161, message="炉鼎不可拒绝双修邀约", http_status=403)
        row.status = "cancelled"
        await self._session.flush()
        other_id = (
            int(row.invitee_character_id)
            if int(character.id) == int(row.inviter_character_id)
            else int(row.inviter_character_id)
        )
        await self._push_dual(
            other_id,
            TYPE_DUAL_UPDATE,
            {
                "session_id": row.id,
                "event": "cancelled",
                "bond_kind": getattr(row, "bond_kind", None),
                "message": "双修已取消",
            },
        )
        return {
            "session": await self._session_public(
                row,
                viewer_character_id=character.id,
            ),
            "message": "双修已取消",
        }

    async def ranks(
        self,
        user: User,
        *,
        board: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        时长榜查询：默认双修时长总榜前 100；亦可查角色位分榜。

        Args:
            user: 当前用户（用于本人名次）。
            board: 榜键；空则返回全部榜。
            limit: 每榜条数（封顶 100）。
        """
        require_dual_enabled()
        character = await self._gate.require_character(user)
        gender = normalize_gender(getattr(character, "gender", None))
        labels = dict(self._cfg().rank_labels)
        min_scores = dict(self._cfg().rank_min_scores)
        boards = [board] if board else list(BOARD_KEYS)
        result: dict[str, Any] = {
            "boards": {},
            "my_gender": gender,
            "primary_board": BOARD_DURATION_TOTAL,
        }
        cap = max(1, min(int(limit), 100))
        for key in boards:
            if key not in BOARD_KEYS:
                raise AppError(code=40160, message=f"未知榜键：{key}", http_status=400)
            if key == BOARD_DURATION_TOTAL:
                min_score = int(min_scores.get("duration_total", 1))
                expected_gender = None
            else:
                expected_gender = key.split("_", 1)[0]
                kind = "number_one" if key.endswith("number_one") else "zero"
                min_score = int(min_scores.get(kind, 1))
            rows = (
                await self._session.execute(
                    select(DualRankScore)
                    .where(
                        DualRankScore.board_key == key,
                        DualRankScore.score >= min_score,
                    )
                    .order_by(DualRankScore.score.desc(), DualRankScore.character_id.asc())
                    .limit(cap),
                )
            ).scalars().all()
            entries = []
            my_rank = None
            my_score = 0
            for idx, r in enumerate(rows, start=1):
                ch = await self._session.get(Character, r.character_id)
                if ch is None:
                    continue
                ch_g = normalize_gender(getattr(ch, "gender", None))
                if expected_gender is not None and ch_g != expected_gender:
                    continue
                entry = {
                    "rank": idx,
                    "character_id": ch.id,
                    "name": ch.name,
                    "score": int(r.score),
                    "gender": ch_g,
                    "score_unit_zh": "秒",
                }
                entries.append(entry)
                if ch.id == character.id:
                    my_rank = idx
                    my_score = int(r.score)
            if my_rank is None and (expected_gender is None or gender == expected_gender):
                mine = (
                    await self._session.execute(
                        select(DualRankScore).where(
                            DualRankScore.character_id == character.id,
                            DualRankScore.board_key == key,
                        ),
                    )
                ).scalar_one_or_none()
                if mine is not None:
                    my_score = int(mine.score)
            result["boards"][key] = {
                "board_key": key,
                "label_zh": labels.get(key) or key,
                "min_score": min_score,
                "entries": entries,
                "my_rank": my_rank,
                "my_score": my_score,
                "score_unit_zh": "秒",
            }
        return result

    def _techniques_public(self) -> list[dict[str, Any]]:
        out = []
        for tid, body in self._cfg().techniques.items():
            item = dict(body)
            item["technique_id"] = tid
            mode = str(body.get("mode") or "")
            item["mode_label_zh"] = {
                "mutual_gain": "双增",
                "transfer": "传功",
                "extract": "索取",
            }.get(mode, mode)
            out.append(item)
        return out

    async def _spend_dual_stamina(
        self,
        *,
        tech: dict[str, Any],
        inviter: Character,
        invitee: Character,
    ) -> dict[str, Any]:
        """
        按功法模式扣双方战斗体力。

        双增：双方相同；传功：传方>受方；索取：索取方>被索取方。
        """
        mode = str(tech.get("mode") or "mutual_gain")
        costs_root = dict(self._cfg().stamina_costs or {})
        mode_costs = dict(costs_root.get(mode) or {})

        if mode == "mutual_gain":
            inviter_cost = int(mode_costs.get("inviter") or mode_costs.get("invitee") or 10)
            invitee_cost = int(mode_costs.get("invitee") or inviter_cost)
            roles = {"inviter": inviter_cost, "invitee": invitee_cost}
            spend_map = [(inviter, inviter_cost, "dual_mutual_inviter"), (invitee, invitee_cost, "dual_mutual_invitee")]
        elif mode == "transfer":
            direction = str(tech.get("transfer_direction") or "inviter_to_invitee")
            giver_cost = int(mode_costs.get("giver") or 15)
            receiver_cost = int(mode_costs.get("receiver") or 8)
            if direction == "invitee_to_inviter":
                spend_map = [
                    (invitee, giver_cost, "dual_transfer_giver"),
                    (inviter, receiver_cost, "dual_transfer_receiver"),
                ]
                roles = {"giver": giver_cost, "receiver": receiver_cost, "giver_is": "invitee"}
            else:
                spend_map = [
                    (inviter, giver_cost, "dual_transfer_giver"),
                    (invitee, receiver_cost, "dual_transfer_receiver"),
                ]
                roles = {"giver": giver_cost, "receiver": receiver_cost, "giver_is": "inviter"}
        elif mode == "extract":
            direction = str(tech.get("extract_direction") or "inviter_from_invitee")
            extractor_cost = int(mode_costs.get("extractor") or 15)
            target_cost = int(mode_costs.get("target") or 8)
            if direction == "invitee_from_inviter":
                spend_map = [
                    (invitee, extractor_cost, "dual_extract_extractor"),
                    (inviter, target_cost, "dual_extract_target"),
                ]
                roles = {
                    "extractor": extractor_cost,
                    "target": target_cost,
                    "extractor_is": "invitee",
                }
            else:
                spend_map = [
                    (inviter, extractor_cost, "dual_extract_extractor"),
                    (invitee, target_cost, "dual_extract_target"),
                ]
                roles = {
                    "extractor": extractor_cost,
                    "target": target_cost,
                    "extractor_is": "inviter",
                }
        else:
            raise AppError(code=40162, message="未知双修功法模式", http_status=400)

        readings: dict[str, Any] = {"mode": mode, "costs": roles}
        for character, amount, reason in spend_map:
            who = "邀请方" if int(character.id) == int(inviter.id) else "受邀方"
            try:
                reading = self._stamina.spend_amount(
                    character,
                    int(amount),
                    reason=reason,
                )
            except AppError as err:
                if err.code == 40049:
                    raise AppError(
                        code=40049,
                        message=f"{who}{err.message}",
                        http_status=409,
                    ) from err
                raise
            key = "inviter" if int(character.id) == int(inviter.id) else "invitee"
            readings[key] = {"cost": int(amount), **reading}
        return readings

    def _require_gender(self, character: Character) -> None:
        if normalize_gender(getattr(character, "gender", None)) is None:
            raise AppError(
                code=40160,
                message="请先补全道途阴阳（性别）再双修或上榜",
                http_status=400,
            )

    def _assert_realm_min(self, character: Character, tech: dict[str, Any]) -> None:
        realm_min = str(tech.get("realm_min") or "body_tempering")
        order = list(get_game_config().realms.keys())
        try:
            need = order.index(realm_min)
            have = order.index(str(character.major_realm))
        except ValueError:
            return
        if have < need:
            major = get_major_realm(realm_min)
            label = major.name if major else realm_min
            raise AppError(
                code=40162,
                message=f"境界不足：须达{label}",
                http_status=400,
            )

    async def _assert_playable(self, character: Character) -> None:
        status = str(character.status or "normal")
        if status in ("tribulation", "awaiting_ferry", "reincarnating", "breaking_through"):
            raise AppError(
                code=40161,
                message=f"当前状态「{status}」不可双修",
                http_status=409,
            )

    async def _assert_available_for_dual(
        self,
        character: Character,
        *,
        who_zh: str,
        skip_dual_session: bool = False,
        skip_idle: bool = False,
    ) -> None:
        """
        双修可用性：终态可发起/接纳；正忙则拒。

        正忙：进行中面交、进行中双修、队伍/团队、秘境。
        修炼中默认不挡发起；接纳侧 ``skip_idle=True`` 后由停修处理。

        Args:
            character: 角色。
            who_zh: 文案主语（你/对方/炉鼎）。
            skip_dual_session: 确认本场邀约时跳过「已有双修」检查。
            skip_idle: 不因修炼判忙。
        """
        if not skip_dual_session and await self._active_session_for(character.id):
            raise AppError(
                code=40161,
                message=f"{who_zh}已有进行中的双修",
                http_status=409,
            )
        if await self._has_active_face(character.id):
            raise AppError(
                code=40161,
                message=f"{who_zh}正忙，暂不可双修",
                http_status=409,
            )
        if await self._in_open_party(character.id):
            raise AppError(
                code=40161,
                message=f"{who_zh}正在队伍/团队中，暂不可双修",
                http_status=409,
            )
        if self._in_secret_realm(character):
            raise AppError(
                code=40161,
                message=f"{who_zh}正在秘境中，暂不可双修",
                http_status=409,
            )
        if not skip_idle and is_productive_idle(getattr(character, "idle_direction", None)):
            # 发起侧：修炼中仍允许发出邀约；受邀接纳会停修。炉鼎强制走 skip_idle。
            pass

    async def _stop_cultivation_if_needed(self, character: Character) -> None:
        """接受双修时：若在修炼/挂机则先结算并停到 none。"""
        if not is_productive_idle(getattr(character, "idle_direction", None)):
            return
        from app.services.idle_service import IdleService

        idle = IdleService(self._session)
        await idle.settle_dual_async(character, now=now_utc())
        direction = str(character.idle_direction or "none")
        if direction == "sect_mining":
            from app.services.sect_facility_service import SectFacilityService

            fac = SectFacilityService(self._session)
            await fac.settle_mining_character(character, now=now_utc())
            await fac.release_miner_slot(character)
        character.idle_direction = "none"
        character.updated_at = now_utc()
        await self._session.flush()
        logger.info(
            "dual auto-stop idle character=%s was=%s",
            character.id,
            direction,
        )

    async def _in_open_party(self, character_id: int) -> bool:
        from app.db.models.chat import PartyMember, PartySession

        row = (
            await self._session.execute(
                select(PartySession.id)
                .join(PartyMember, PartyMember.party_id == PartySession.id)
                .where(
                    PartyMember.character_id == int(character_id),
                    PartySession.status == "open",
                )
                .limit(1),
            )
        ).scalar_one_or_none()
        return row is not None

    def _in_secret_realm(self, character: Character) -> bool:
        """秘境占位：落地后接真实占用；当前恒 False。"""
        _ = character
        return False

    async def _has_active_face(self, character_id: int) -> bool:
        """
        是否有进行中的面交。

        终态 ``committed`` / ``cancelled`` / ``expired`` 不计入；
        检查前惰性过期，避免超时会话误挡双修。
        """
        from app.core.time_utils import ensure_aware_utc

        rows = (
            await self._session.execute(
                select(FaceTradeSession).where(
                    or_(
                        FaceTradeSession.initiator_id == character_id,
                        FaceTradeSession.peer_id == character_id,
                    ),
                    FaceTradeSession.status.in_(
                        ("pending_invite", "browsing", "locking", "confirming"),
                    ),
                ),
            )
        ).scalars().all()
        still_active = False
        for row in rows:
            # 惰性过期 → 终态 expired，不再挡双修
            if row.expires_at is not None and now_utc() >= ensure_aware_utc(row.expires_at):
                if row.status not in ("committed", "cancelled", "expired"):
                    row.status = "expired"
                    row.closed_at = now_utc()
                continue
            if row.status in ("pending_invite", "browsing", "locking", "confirming"):
                still_active = True
        if rows:
            await self._session.flush()
        return still_active

    async def _resolve_target(
        self,
        *,
        target_character_id: int | None,
        target_name: str | None,
        exclude_id: int,
    ) -> Character:
        if target_character_id is not None:
            ch = await self._session.get(Character, int(target_character_id))
        elif target_name:
            ch = (
                await self._session.execute(
                    select(Character).where(Character.name == target_name.strip()).limit(1),
                )
            ).scalar_one_or_none()
        else:
            raise AppError(code=40161, message="请指定对方道号或角色 id", http_status=400)
        if ch is None:
            raise AppError(code=40005, message="目标角色不存在", http_status=404)
        if int(ch.id) == int(exclude_id):
            raise AppError(code=40161, message="不可与自己双修", http_status=400)
        return ch

    async def _active_session_for(self, character_id: int) -> DualCultivationSession | None:
        return (
            await self._session.execute(
                select(DualCultivationSession)
                .where(
                    DualCultivationSession.status.in_(tuple(ACTIVE_SESSION_STATUSES)),
                    or_(
                        DualCultivationSession.inviter_character_id == character_id,
                        DualCultivationSession.invitee_character_id == character_id,
                    ),
                )
                .order_by(DualCultivationSession.id.desc())
                .limit(1),
            )
        ).scalar_one_or_none()

    async def _get_session(self, session_id: int) -> DualCultivationSession:
        row = await self._session.get(DualCultivationSession, int(session_id))
        if row is None:
            raise AppError(code=40161, message="双修会话不存在", http_status=404)
        return row

    async def _push_dual(
        self,
        character_id: int,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Push dual WS envelope to a character's live connections."""
        settings = get_settings()
        if not bool(getattr(settings, "ws_enabled", True)):
            return
        try:
            await get_ws_hub().send_to_character(int(character_id), msg_type, payload)
        except Exception:  # noqa: BLE001
            logger.debug(
                "dual ws push skipped character_id=%s type=%s",
                character_id,
                msg_type,
            )

    @staticmethod
    def _effective_status(status: str | None) -> str:
        """Map legacy ``confirmed`` to ``accepted`` for宽衣/过期逻辑。"""
        value = str(status or "")
        return "accepted" if value == "confirmed" else value

    async def _accept_session(
        self,
        row: DualCultivationSession,
        *,
        auto: bool,
    ) -> None:
        """进入 accepted 并启动宽衣倒计时。"""
        current = now_utc()
        undress_sec = int(self._cfg().undress_expire_sec)
        row.status = "accepted"
        row.confirmed_at = current
        row.invite_expire_at = None
        row.undress_expire_at = (
            current + timedelta(seconds=undress_sec) if undress_sec > 0 else None
        )
        if auto:
            row.auto_forced = True
        await self._session.flush()

    async def _mark_undressed(
        self,
        row: DualCultivationSession,
        *,
        auto: bool,
    ) -> None:
        """进入 undressed。"""
        current = now_utc()
        row.status = "undressed"
        row.undress_expire_at = None
        row.invitee_undressed_at = current
        if auto:
            row.auto_forced = True
        await self._session.flush()

    async def _expire_stale(self) -> None:
        """惰性过期：邀约超时 / 宽衣超时。"""
        current = now_utc()
        invite_rows = (
            await self._session.execute(
                select(DualCultivationSession).where(
                    DualCultivationSession.status == "inviting",
                    DualCultivationSession.invite_expire_at.is_not(None),
                    DualCultivationSession.invite_expire_at < current,
                ),
            )
        ).scalars().all()
        for row in invite_rows:
            kind = str(getattr(row, "bond_kind", "") or "").lower()
            if kind == BOND_KIND_VESSEL:
                invitee_ch = await self._session.get(Character, row.invitee_character_id)
                if invitee_ch is not None:
                    await self._stop_cultivation_if_needed(invitee_ch)
                await self._accept_session(row, auto=True)
                tech = self._cfg().techniques.get(row.technique_id) or {}
                tech_label = tech.get("label") or row.technique_id
                msg = f"炉鼎邀约超时，已自动接受双修「{tech_label}」"
                for cid in (row.inviter_character_id, row.invitee_character_id):
                    await self._push_dual(
                        int(cid),
                        TYPE_DUAL_UPDATE,
                        {
                            "session_id": row.id,
                            "event": "accepted",
                            "bond_kind": BOND_KIND_VESSEL,
                            "message": msg,
                            "auto": True,
                        },
                    )
            else:
                row.status = "timeout"
                for cid in (row.inviter_character_id, row.invitee_character_id):
                    await self._push_dual(
                        int(cid),
                        TYPE_DUAL_UPDATE,
                        {
                            "session_id": row.id,
                            "event": "timeout",
                            "bond_kind": BOND_KIND_COMPANION,
                            "message": "双修邀约已超时取消",
                        },
                    )

        undress_rows = (
            await self._session.execute(
                select(DualCultivationSession).where(
                    DualCultivationSession.status.in_(("accepted", "confirmed")),
                    DualCultivationSession.undress_expire_at.is_not(None),
                    DualCultivationSession.undress_expire_at < current,
                ),
            )
        ).scalars().all()
        for row in undress_rows:
            kind = str(getattr(row, "bond_kind", "") or "").lower()
            if kind == BOND_KIND_VESSEL:
                await self._mark_undressed(row, auto=True)
                msg = "炉鼎宽衣超时，已自动宽衣"
                for cid in (row.inviter_character_id, row.invitee_character_id):
                    await self._push_dual(
                        int(cid),
                        TYPE_DUAL_UPDATE,
                        {
                            "session_id": row.id,
                            "event": "undressed",
                            "bond_kind": BOND_KIND_VESSEL,
                            "message": msg,
                            "auto": True,
                        },
                    )
            else:
                row.status = "timeout"
                for cid in (row.inviter_character_id, row.invitee_character_id):
                    await self._push_dual(
                        int(cid),
                        TYPE_DUAL_UPDATE,
                        {
                            "session_id": row.id,
                            "event": "timeout",
                            "bond_kind": BOND_KIND_COMPANION,
                            "message": "宽衣已超时，双修取消",
                        },
                    )

        if invite_rows or undress_rows:
            await self._session.flush()

    async def _add_duration_ranks(
        self,
        character: Character,
        *,
        role: str,
        duration_sec: int,
    ) -> None:
        """
        按本场秒数累加总时长榜 + 角色位时长榜。

        Args:
            character: 角色。
            role: number_one|zero。
            duration_sec: 本场秒数。
        """
        seconds = max(0, int(duration_sec))
        if seconds <= 0:
            return
        gender = normalize_gender(getattr(character, "gender", None))
        if gender is None:
            return
        await self._bump_score(character.id, BOARD_DURATION_TOTAL, seconds)
        await self._bump_score(
            character.id,
            board_key_for(gender=gender, kind=normalize_role(role)),
            seconds,
        )

    async def _bump_score(self, character_id: int, board_key: str, delta: int) -> None:
        row = (
            await self._session.execute(
                select(DualRankScore).where(
                    DualRankScore.character_id == character_id,
                    DualRankScore.board_key == board_key,
                ),
            )
        ).scalar_one_or_none()
        if row is None:
            row = DualRankScore(
                character_id=character_id,
                board_key=board_key,
                score=int(delta),
            )
            self._session.add(row)
        else:
            row.score = int(row.score) + int(delta)
            row.updated_at = now_utc()
        await self._session.flush()

    async def _session_public(
        self,
        row: DualCultivationSession,
        *,
        viewer_character_id: int | None = None,
    ) -> dict[str, Any]:
        inviter = await self._session.get(Character, row.inviter_character_id)
        invitee = await self._session.get(Character, row.invitee_character_id)
        tech = self._cfg().techniques.get(row.technique_id) or {}
        summary = None
        if row.settle_summary_json:
            try:
                summary = json.loads(row.settle_summary_json)
            except json.JSONDecodeError:
                summary = None
        effective = self._effective_status(row.status)
        invitee_undressed = row.invitee_undressed_at is not None
        can_undress = (
            viewer_character_id is not None
            and int(viewer_character_id) == int(row.invitee_character_id)
            and effective == "accepted"
        )
        can_start = (
            viewer_character_id is not None
            and int(viewer_character_id) == int(row.inviter_character_id)
            and row.status == "undressed"
        )
        return {
            "session_id": row.id,
            "status": row.status,
            "status_label_zh": status_label_zh(row.status),
            "technique_id": row.technique_id,
            "technique_label": tech.get("label") or row.technique_id,
            "mode": tech.get("mode"),
            "bond_kind": getattr(row, "bond_kind", None),
            "inviter_role": normalize_role(getattr(row, "inviter_role", None)),
            "auto_forced": bool(getattr(row, "auto_forced", False)),
            "inviter": {
                "character_id": row.inviter_character_id,
                "name": inviter.name if inviter else "",
                "gender": normalize_gender(getattr(inviter, "gender", None)) if inviter else None,
            },
            "invitee": {
                "character_id": row.invitee_character_id,
                "name": invitee.name if invitee else "",
                "gender": normalize_gender(getattr(invitee, "gender", None)) if invitee else None,
            },
            "invite_expire_at": (
                to_utc_iso(row.invite_expire_at) if row.invite_expire_at else None
            ),
            "undress_expire_at": (
                to_utc_iso(row.undress_expire_at) if row.undress_expire_at else None
            ),
            "invitee_undressed": invitee_undressed,
            "can_undress": can_undress,
            "can_start": can_start,
            "dice": {
                "roll": row.roll_value,
                "lo": row.roll_lo,
                "hi": row.roll_hi,
                "effect_tier": row.effect_tier,
                "yield_mult": row.yield_mult,
                "duration_sec": row.duration_sec,
                "label_zh": row.dice_label_zh,
                "rerolls_used": int(row.rerolls_used),
            }
            if row.roll_value is not None
            else None,
            "settle_summary": summary,
        }
