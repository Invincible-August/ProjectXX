"""
双修应用服务（M7 L7）：邀约 / 确认 / 掷骰 / 结算 / 四榜。

权威：修为变动与榜分只在服务端；掷骰走 DiceService purpose=dual_cultivation。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import Character, User
from app.db.models.dual_cultivation import DualCultivationSession, DualRankScore
from app.db.models.social_trade import FaceTradeSession
from app.domain.dual_cultivation_rules import (
    ACTIVE_SESSION_STATUSES,
    BOARD_KEYS,
    board_key_for,
    gender_label_zh,
    normalize_gender,
    resolve_dice_tier,
    scaled_yield,
    technique_allows_pair,
)
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.dice_service import DiceService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, get_major_realm

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

    def _cfg(self):
        return get_game_config().dual_cultivation

    def _technique(self, technique_id: str) -> dict[str, Any]:
        tech = self._cfg().techniques.get(technique_id)
        if not tech:
            raise AppError(code=40162, message="双修功法不存在", http_status=400)
        return dict(tech)

    async def me(self, user: User) -> dict[str, Any]:
        """当前会话、功法目录、性别状态。"""
        require_dual_enabled()
        character = await self._gate.require_character(user)
        await self._expire_stale()
        session = await self._active_session_for(character.id)
        gender = normalize_gender(getattr(character, "gender", None))
        return {
            "gender": gender,
            "gender_label_zh": gender_label_zh(gender),
            "needs_gender": gender is None,
            "session": await self._session_public(session) if session else None,
            "techniques": self._techniques_public(),
            "config": {
                "invite_expire_sec": int(self._cfg().invite_expire_sec),
                "max_rerolls": int(self._cfg().max_rerolls),
                "spirit_stone_cost": int(self._cfg().spirit_stone_cost),
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
        target_name: str | None,
        dice_seed: int | None = None,
    ) -> dict[str, Any]:
        """发起邀约。"""
        require_dual_enabled()
        inviter, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._assert_playable(inviter)
        self._require_gender(inviter)
        tech = self._technique(technique_id)
        invitee = await self._resolve_target(
            target_character_id=target_character_id,
            target_name=target_name,
            exclude_id=inviter.id,
        )
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
        if await self._active_session_for(inviter.id) or await self._active_session_for(invitee.id):
            raise AppError(code=40161, message="已有进行中的双修会话", http_status=409)
        if await self._has_active_face(inviter.id) or await self._has_active_face(invitee.id):
            raise AppError(code=40161, message="面交锁定中不可开双修", http_status=409)

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
            status="inviting",
            invite_expire_at=current + timedelta(seconds=expire_sec) if expire_sec > 0 else None,
            dice_seed=dice_seed,
            created_at=current,
        )
        self._session.add(row)
        await self._session.flush()
        logger.info(
            "dual invite id=%s inviter=%s invitee=%s tech=%s",
            row.id,
            inviter.id,
            invitee.id,
            technique_id,
        )
        return {
            "session": await self._session_public(row),
            "message": f"已邀请「{invitee.name}」双修「{tech.get('label') or technique_id}」",
        }

    async def confirm(self, user: User, session_id: int) -> dict[str, Any]:
        """受邀方确认 → confirmed。"""
        require_dual_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self._expire_stale()
        row = await self._get_session(session_id)
        if row.status != "inviting":
            raise AppError(code=40161, message="会话不在邀约态", http_status=400)
        if int(row.invitee_character_id) != int(character.id):
            raise AppError(code=40161, message="仅受邀方可确认", http_status=403)
        await self._assert_playable(character)
        row.status = "confirmed"
        row.confirmed_at = now_utc()
        await self._session.flush()
        return {
            "session": await self._session_public(row),
            "message": "双方已确认，可掷骰开局",
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
            raise AppError(code=40161, message="当前不可掷骰", http_status=400)

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
        """结束领取：按功法 mode 结算修为与榜分。"""
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
            raise AppError(code=40161, message="须先掷骰开局后再结算", http_status=400)
        if row.roll_value is None or row.yield_mult is None:
            raise AppError(code=40161, message="缺少掷骰快照", http_status=400)

        tech = self._technique(row.technique_id)
        inviter = await self._session.get(Character, row.inviter_character_id)
        invitee = await self._session.get(Character, row.invitee_character_id)
        if inviter is None or invitee is None:
            raise AppError(code=40005, message="双修角色缺失", http_status=404)

        mult = float(row.yield_mult)
        base = int(tech.get("base_yield") or 0)
        gained = scaled_yield(base, mult)
        mode = str(tech.get("mode") or "mutual_gain")
        summary: dict[str, Any] = {
            "mode": mode,
            "technique_id": row.technique_id,
            "technique_label": tech.get("label"),
            "yield_mult": mult,
            "effect_tier": row.effect_tier,
            "base_yield": base,
            "scaled_yield": gained,
        }

        if mode == "mutual_gain":
            inviter.cultivation_points = int(inviter.cultivation_points) + gained
            invitee.cultivation_points = int(invitee.cultivation_points) + gained
            summary["inviter_gain"] = gained
            summary["invitee_gain"] = gained
            await self._add_rank(
                inviter,
                number_one=int(tech.get("number_one_score") or 0),
                zero=int(tech.get("zero_score") or 0),
            )
            await self._add_rank(
                invitee,
                number_one=int(tech.get("number_one_score") or 0),
                zero=int(tech.get("zero_score") or 0),
            )
        elif mode == "transfer":
            direction = str(tech.get("transfer_direction") or "inviter_to_invitee")
            if direction == "invitee_to_inviter":
                giver, receiver = invitee, inviter
            else:
                giver, receiver = inviter, invitee
            cost_pool = int(tech.get("transfer_cost_from_giver") or 0)
            if cost_pool > 0 and int(giver.cultivation_points) < cost_pool:
                raise AppError(
                    code=40162,
                    message=f"传方修为池不足（需 {cost_pool}）",
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
            if cost_pool > 0:
                giver.cultivation_points = int(giver.cultivation_points) - cost_pool
            receiver.cultivation_points = int(receiver.cultivation_points) + gained
            summary["giver_id"] = giver.id
            summary["receiver_id"] = receiver.id
            summary["giver_pool_cost"] = cost_pool
            summary["receiver_gain"] = gained
            n1 = int(tech.get("number_one_score") or 0)
            await self._add_rank(giver, number_one=n1, zero=int(tech.get("zero_score_giver") or 0))
            await self._add_rank(
                receiver,
                number_one=n1,
                zero=int(tech.get("zero_score_receiver") or tech.get("zero_score") or 0),
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
        logger.info("dual settle session=%s mode=%s yield=%s", row.id, mode, gained)
        from app.services.character_service import CharacterService, character_public_to_dict

        svc = CharacterService(self._session)
        return {
            "session": await self._session_public(row),
            "summary": summary,
            "message": "双修已结算",
            "character": character_public_to_dict(await svc.enrich_public(character)),
        }

    async def cancel(self, user: User, session_id: int) -> dict[str, Any]:
        """取消邀约或中止未结算会话。"""
        require_dual_enabled()
        character = await self._gate.require_character(user)
        row = await self._get_session(session_id)
        if int(character.id) not in (
            int(row.inviter_character_id),
            int(row.invitee_character_id),
        ):
            raise AppError(code=40161, message="非本场双修成员", http_status=403)
        if row.status not in ("inviting", "confirmed", "running"):
            raise AppError(code=40161, message="会话已结束", http_status=400)
        row.status = "cancelled"
        await self._session.flush()
        return {"session": await self._session_public(row), "message": "双修已取消"}

    async def ranks(
        self,
        user: User,
        *,
        board: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        四榜查询。

        Args:
            user: 当前用户（用于本人名次）。
            board: 榜键；空则返回四榜摘要。
            limit: 每榜条数。
        """
        require_dual_enabled()
        character = await self._gate.require_character(user)
        gender = normalize_gender(getattr(character, "gender", None))
        labels = dict(self._cfg().rank_labels)
        min_scores = dict(self._cfg().rank_min_scores)
        boards = [board] if board else list(BOARD_KEYS)
        result: dict[str, Any] = {"boards": {}, "my_gender": gender}
        for key in boards:
            if key not in BOARD_KEYS:
                raise AppError(code=40160, message=f"未知榜键：{key}", http_status=400)
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
                    .limit(max(1, min(int(limit), 100))),
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
                if ch_g != expected_gender:
                    continue
                entry = {
                    "rank": idx,
                    "character_id": ch.id,
                    "name": ch.name,
                    "score": int(r.score),
                    "gender": ch_g,
                }
                entries.append(entry)
                if ch.id == character.id:
                    my_rank = idx
                    my_score = int(r.score)
            if my_rank is None and gender == expected_gender:
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
            }
        return result

    def _techniques_public(self) -> list[dict[str, Any]]:
        out = []
        for tid, body in self._cfg().techniques.items():
            item = dict(body)
            item["technique_id"] = tid
            out.append(item)
        return out

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

    async def _has_active_face(self, character_id: int) -> bool:
        row = (
            await self._session.execute(
                select(FaceTradeSession.id)
                .where(
                    or_(
                        FaceTradeSession.initiator_id == character_id,
                        FaceTradeSession.peer_id == character_id,
                    ),
                    FaceTradeSession.status.in_(
                        ("pending_invite", "browsing", "locking", "confirming"),
                    ),
                )
                .limit(1),
            )
        ).scalar_one_or_none()
        return row is not None

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

    async def _expire_stale(self) -> None:
        current = now_utc()
        rows = (
            await self._session.execute(
                select(DualCultivationSession).where(
                    DualCultivationSession.status == "inviting",
                    DualCultivationSession.invite_expire_at.is_not(None),
                    DualCultivationSession.invite_expire_at < current,
                ),
            )
        ).scalars().all()
        for row in rows:
            row.status = "timeout"
        if rows:
            await self._session.flush()

    async def _add_rank(
        self,
        character: Character,
        *,
        number_one: int,
        zero: int,
    ) -> None:
        gender = normalize_gender(getattr(character, "gender", None))
        if gender is None:
            return
        if number_one > 0:
            await self._bump_score(
                character.id,
                board_key_for(gender=gender, kind="number_one"),
                number_one,
            )
        if zero > 0:
            await self._bump_score(
                character.id,
                board_key_for(gender=gender, kind="zero"),
                zero,
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

    async def _session_public(self, row: DualCultivationSession) -> dict[str, Any]:
        inviter = await self._session.get(Character, row.inviter_character_id)
        invitee = await self._session.get(Character, row.invitee_character_id)
        tech = self._cfg().techniques.get(row.technique_id) or {}
        summary = None
        if row.settle_summary_json:
            try:
                summary = json.loads(row.settle_summary_json)
            except json.JSONDecodeError:
                summary = None
        return {
            "session_id": row.id,
            "status": row.status,
            "technique_id": row.technique_id,
            "technique_label": tech.get("label") or row.technique_id,
            "mode": tech.get("mode"),
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
                ensure_aware_utc(row.invite_expire_at).isoformat()
                if row.invite_expire_at
                else None
            ),
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
