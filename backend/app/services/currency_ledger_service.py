"""
货币流水助手（M7 L2）：统一改灵石并记 currency_ledger。

系统回收池：character_id=None。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character
from app.db.models.social_trade import CurrencyLedger
from app.schemas.common import AppError

logger = logging.getLogger(__name__)

# 进程内回收池余额（审计累加；非角色字段）
_SYSTEM_RECYCLE_BALANCE: dict[str, int] = {"spirit_stones": 0, "tiandao_point": 0}


def system_recycle_balance(currency: str = "spirit_stones") -> int:
    """读取进程内回收池余额（测试/展示用）。"""
    return int(_SYSTEM_RECYCLE_BALANCE.get(currency, 0))


def reset_system_recycle_balance_for_tests() -> None:
    """单测重置回收池。"""
    _SYSTEM_RECYCLE_BALANCE.clear()
    _SYSTEM_RECYCLE_BALANCE["spirit_stones"] = 0
    _SYSTEM_RECYCLE_BALANCE["tiandao_point"] = 0


class CurrencyLedgerService:
    """多币种入账/扣款 + 流水（灵石 / 天道点）。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步会话。
        """
        self._session = session

    def _balance_of(self, character: Character, currency: str) -> int:
        """读取角色某币种余额。"""
        if currency == "spirit_stones":
            return int(character.spirit_stones)
        if currency == "tiandao_point":
            return int(getattr(character, "tiandao_points", 0) or 0)
        if currency == "reincarnation_point":
            return int(getattr(character, "reincarnation_points", 0) or 0)
        raise AppError(code=40000, message=f"暂不支持币种：{currency}", http_status=400)

    def _set_balance(self, character: Character, currency: str, value: int) -> None:
        """写回角色某币种余额。"""
        if currency == "spirit_stones":
            character.spirit_stones = int(value)
        elif currency == "tiandao_point":
            character.tiandao_points = int(value)
        elif currency == "reincarnation_point":
            character.reincarnation_points = int(value)
        else:
            raise AppError(code=40000, message=f"暂不支持币种：{currency}", http_status=400)

    async def adjust_currency(
        self,
        character: Character | None,
        *,
        currency: str,
        delta: int,
        reason: str,
        note_zh: str | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        allow_negative: bool = False,
    ) -> int:
        """
        调整币种余额并记流水。

        Raises:
            AppError: 余额不足；天道点不足 ``40170``。
        """
        cur = str(currency or "spirit_stones").strip()
        if character is None:
            bal = int(_SYSTEM_RECYCLE_BALANCE.get(cur, 0)) + int(delta)
            if bal < 0 and not allow_negative:
                raise AppError(code=40000, message="回收池余额异常", http_status=400)
            _SYSTEM_RECYCLE_BALANCE[cur] = bal
            self._session.add(
                CurrencyLedger(
                    character_id=None,
                    currency=cur,
                    delta=int(delta),
                    balance_after=bal,
                    reason=reason,
                    note_zh=note_zh,
                    ref_type=ref_type,
                    ref_id=str(ref_id) if ref_id is not None else None,
                ),
            )
            await self._session.flush()
            return bal

        new_bal = self._balance_of(character, cur) + int(delta)
        if new_bal < 0 and not allow_negative:
            if cur == "tiandao_point":
                raise AppError(code=40170, message="天道点不足", http_status=400)
            raise AppError(code=40000, message="余额不足", http_status=400)
        self._set_balance(character, cur, new_bal)
        self._session.add(
            CurrencyLedger(
                character_id=character.id,
                currency=cur,
                delta=int(delta),
                balance_after=new_bal,
                reason=reason,
                note_zh=note_zh,
                ref_type=ref_type,
                ref_id=str(ref_id) if ref_id is not None else None,
            ),
        )
        await self._session.flush()
        logger.info(
            "currency character_id=%s currency=%s delta=%s reason=%s bal=%s",
            character.id,
            cur,
            delta,
            reason,
            new_bal,
        )
        return new_bal

    async def adjust_spirit_stones(
        self,
        character: Character | None,
        *,
        delta: int,
        reason: str,
        note_zh: str | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        allow_negative: bool = False,
    ) -> int:
        """
        调整角色灵石或系统回收池。

        Args:
            character: 角色；None 表示系统回收池。
            delta: 增量（可负）。
            reason: 机读原因。
            note_zh: 中文备注。
            ref_type: 关联类型。
            ref_id: 关联 id。
            allow_negative: 是否允许余额为负（一般禁止）。

        Returns:
            int: 调整后余额。

        Raises:
            AppError: 余额不足。
        """
        return await self.adjust_currency(
            character,
            currency="spirit_stones",
            delta=delta,
            reason=reason,
            note_zh=note_zh,
            ref_type=ref_type,
            ref_id=ref_id,
            allow_negative=allow_negative,
        )

    async def adjust_tiandao_points(
        self,
        character: Character,
        *,
        delta: int,
        reason: str,
        note_zh: str | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> int:
        """调整天道点。"""
        return await self.adjust_currency(
            character,
            currency="tiandao_point",
            delta=delta,
            reason=reason,
            note_zh=note_zh,
            ref_type=ref_type,
            ref_id=ref_id,
        )

    async def recent_for_character(
        self,
        character_id: int,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """最近流水（调试/面板）。"""
        rows = (
            await self._session.execute(
                select(CurrencyLedger)
                .where(CurrencyLedger.character_id == character_id)
                .order_by(CurrencyLedger.id.desc())
                .limit(limit),
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "currency": r.currency,
                "delta": int(r.delta),
                "balance_after": int(r.balance_after),
                "reason": r.reason,
                "note_zh": r.note_zh,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
            }
            for r in rows
        ]
