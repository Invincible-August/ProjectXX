"""
商业化应用服务（M7 L8）：会员开通 / 天道商店 / 沙盒加点 / 过期回落。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import User
from app.db.models.character import Character
from app.domain.commerce_rules import (
    apply_membership_expiry_inplace,
    is_forbidden_shop_kind,
    membership_public,
)
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config, offline_cap_hours_for_tier

logger = logging.getLogger(__name__)


def require_commerce_enabled() -> None:
    """商业化总闸（会员/商店）。"""
    settings = get_settings()
    if not bool(getattr(settings, "commerce_system_enabled", True)):
        raise AppError(code=40000, message="天道商店未开放", http_status=403)


def require_sandbox_enabled() -> None:
    """沙盒加点闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "commerce_sandbox_enabled", True)):
        raise AppError(code=40000, message="天道点沙盒未开放", http_status=403)


class CommerceService:
    """商业化用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """注入会话。"""
        self._session = session
        self._gate = PlayGate(session)
        self._ledger = CurrencyLedgerService(session)

    def _cfg(self):
        return get_game_config().commerce

    def _currencies(self):
        return get_game_config().currencies

    async def ensure_membership_fresh(
        self,
        character: Character,
        *,
        now=None,
    ) -> str:
        """
        惰性过期：付费档到期回落 free，并清 expires。

        Returns:
            有效档位。
        """
        current = now or now_utc()
        effective = apply_membership_expiry_inplace(character, now=current)
        await self._session.flush()
        return effective

    async def me(self, user: User) -> dict[str, Any]:
        """会员与天道点摘要。"""
        require_commerce_enabled()
        character = await self._gate.require_character(user)
        tier = await self.ensure_membership_fresh(character)
        return {
            "membership": self._membership_payload(character, tier),
            "tiandao_points": int(getattr(character, "tiandao_points", 0) or 0),
            "boundary_zh": str((self._cfg().shop or {}).get("boundary_zh") or ""),
            "currencies": self._currency_catalog_public(),
        }

    async def shop(self, user: User) -> dict[str, Any]:
        """天道商店货架。"""
        require_commerce_enabled()
        character = await self._gate.require_character(user)
        tier = await self.ensure_membership_fresh(character)
        shop_cfg = dict(self._cfg().shop or {})
        forbidden = list(shop_cfg.get("forbidden_item_types") or [])
        items_out = []
        for item_id, body in dict(shop_cfg.get("items") or {}).items():
            if not isinstance(body, dict):
                continue
            kind = str(body.get("kind") or "")
            if is_forbidden_shop_kind(kind, forbidden):
                continue
            if not bool(body.get("enabled", True)):
                continue
            item = dict(body)
            item["item_id"] = item_id
            items_out.append(item)
        return {
            "boundary_zh": str(shop_cfg.get("boundary_zh") or ""),
            "forbidden_item_types": forbidden,
            "items": items_out,
            "membership": self._membership_payload(character, tier),
            "tiandao_points": int(getattr(character, "tiandao_points", 0) or 0),
        }

    async def activate_membership(self, user: User, tier: str) -> dict[str, Any]:
        """开通或续费会员（耗天道点）。"""
        require_commerce_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self.ensure_membership_fresh(character)
        target = str(tier or "").strip().lower()
        if target not in ("tier1", "tier2"):
            raise AppError(code=40000, message="会员档须为 tier1 或 tier2", http_status=400)
        tiers = dict(self._cfg().membership_tiers or {})
        spec = dict(tiers.get(target) or {})
        if not spec:
            raise AppError(code=40000, message="会员档未配置", http_status=400)
        cost = int(spec.get("tiandao_cost") or 0)
        days = int(spec.get("duration_days") or 30)
        if cost > 0:
            await self._ledger.adjust_tiandao_points(
                character,
                delta=-cost,
                reason="commerce_membership",
                note_zh=f"开通{spec.get('label_zh') or target}",
                ref_type="commerce",
                ref_id=target,
            )
        current = now_utc()
        base = current
        # 同档未过期则续期
        if (
            str(character.membership_tier) == target
            and character.membership_expires_at is not None
        ):
            exp = ensure_aware_utc(character.membership_expires_at)
            if exp > current:
                base = exp
        character.membership_tier = target
        character.membership_expires_at = base + timedelta(days=days)
        character.updated_at = current
        await self._session.flush()
        logger.info(
            "membership activate character=%s tier=%s expires=%s cost=%s",
            character.id,
            target,
            character.membership_expires_at,
            cost,
        )
        return {
            "membership": self._membership_payload(character, target),
            "tiandao_points": int(character.tiandao_points),
            "message": (
                f"已开通{spec.get('label_zh') or target}，"
                f"挂机帽 {offline_cap_hours_for_tier(target):.0f} 时辰；"
                f"过期后回落十二时辰"
            ),
        }

    async def buy(self, user: User, item_id: str) -> dict[str, Any]:
        """商店购买（会员走 activate；灵石锦囊直发）。"""
        require_commerce_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        await self.ensure_membership_fresh(character)
        shop_cfg = dict(self._cfg().shop or {})
        forbidden = list(shop_cfg.get("forbidden_item_types") or [])
        items = dict(shop_cfg.get("items") or {})
        body = items.get(item_id)
        if not isinstance(body, dict) or not bool(body.get("enabled", True)):
            raise AppError(code=40000, message="商品不存在或已下架", http_status=404)
        kind = str(body.get("kind") or "")
        if is_forbidden_shop_kind(kind, forbidden):
            raise AppError(code=40000, message="禁止售卖指定本命道类商品", http_status=400)
        if kind == "membership":
            return await self.activate_membership(
                user,
                str(body.get("membership_tier") or ""),
            )
        if kind == "spirit_stones":
            cost = int(body.get("tiandao_cost") or 0)
            grant = int(body.get("spirit_stones_grant") or 0)
            if cost > 0:
                await self._ledger.adjust_tiandao_points(
                    character,
                    delta=-cost,
                    reason="commerce_shop",
                    note_zh=str(body.get("label_zh") or item_id),
                    ref_type="commerce",
                    ref_id=item_id,
                )
            if grant > 0:
                await self._ledger.adjust_spirit_stones(
                    character,
                    delta=grant,
                    reason="commerce_shop",
                    note_zh=str(body.get("label_zh") or item_id),
                    ref_type="commerce",
                    ref_id=item_id,
                )
            return {
                "item_id": item_id,
                "spirit_stones_granted": grant,
                "tiandao_points": int(character.tiandao_points),
                "message": f"已兑换「{body.get('label_zh') or item_id}」",
            }
        raise AppError(code=40000, message=f"未知商品类型：{kind}", http_status=400)

    async def sandbox_grant_tiandao(self, user: User, amount: int) -> dict[str, Any]:
        """沙盒发放天道点（仅开关开启时）。"""
        require_commerce_enabled()
        require_sandbox_enabled()
        character = await self._gate.require_character(user)
        sandbox = dict(self._cfg().sandbox or {})
        max_once = int(sandbox.get("max_grant_per_request") or 10000)
        qty = int(amount)
        if qty <= 0 or qty > max_once:
            raise AppError(
                code=40000,
                message=f"单次发放须为 1～{max_once}",
                http_status=400,
            )
        bal = await self._ledger.adjust_tiandao_points(
            character,
            delta=qty,
            reason="commerce_sandbox_grant",
            note_zh="沙盒加点",
            ref_type="commerce",
            ref_id="sandbox",
        )
        logger.info("sandbox tiandao character=%s +%s bal=%s", character.id, qty, bal)
        return {
            "tiandao_points": bal,
            "granted": qty,
            "message": f"沙盒已发放天道点 {qty}",
        }

    def _membership_payload(self, character: Character, tier: str) -> dict[str, Any]:
        tiers = dict(self._cfg().membership_tiers or {})
        spec = dict(tiers.get(tier) or {})
        label = str(spec.get("label_zh") or tier)
        expires = (
            ensure_aware_utc(character.membership_expires_at)
            if character.membership_expires_at is not None and tier != "free"
            else None
        )
        return membership_public(
            tier=tier,
            expires_at=expires,
            idle_cap_hours=float(
                spec.get("idle_cap_hours")
                if spec.get("idle_cap_hours") is not None
                else offline_cap_hours_for_tier(tier),
            ),
            label_zh=label,
        )

    def _currency_catalog_public(self) -> list[dict[str, Any]]:
        out = []
        for cid, body in dict(self._currencies().currencies or {}).items():
            if not isinstance(body, dict):
                continue
            item = dict(body)
            item["currency_id"] = cid
            out.append(item)
        return out


async def refresh_membership_for_idle(session: AsyncSession, character: Character) -> str:
    """挂机结算前刷新会员档（供 IdleService 调用）。"""
    return await CommerceService(session).ensure_membership_fresh(character)
