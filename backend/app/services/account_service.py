"""
玩家端账号摘要与打赏账单（只读；写入仍走后台运营）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.admin_player import PLAYER_DEFAULT_PAGE_SIZE, PLAYER_PAGE_SIZES
from app.db.models import Character, PlayerAdWatchRecord, PlayerTipRecord, User
from app.schemas.common import AppError


class AccountService:
    """当前登录玩家的仙缘/打赏/广告计数与打赏流水。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 请求级异步会话。
        """
        self._session = session

    async def get_summary(self, user: User) -> dict[str, Any]:
        """
        账号页摘要：仙缘余额、累计打赏、累计观看广告次数。

        Args:
            user: 当前登录用户。

        Returns:
            dict: fate_luck / total_recharge_amount / ad_watch_count。
        """
        character = await self._session.scalar(
            select(Character).where(Character.user_id == user.id),
        )
        ad_watch_count = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(PlayerAdWatchRecord)
                    .where(PlayerAdWatchRecord.user_id == user.id),
                )
            ).scalar_one(),
        )
        return {
            "fate_luck": int(character.fate_luck or 0) if character else 0,
            "total_recharge_amount": int(user.total_recharge_amount or 0),
            "ad_watch_count": ad_watch_count,
        }

    async def list_tips(
        self,
        user: User,
        *,
        page: int = 1,
        page_size: int = PLAYER_DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """
        当前账号打赏账单（时间 / 金额 / 单号 / 途径原文）。

        Args:
            user: 当前登录用户。
            page: 页码，从 1 起。
            page_size: 每页条数，须为运营分页白名单之一。

        Returns:
            dict: items / total / page / page_size。

        Raises:
            AppError: page_size 非法。
        """
        page = max(1, int(page))
        page_size = int(page_size) if page_size else PLAYER_DEFAULT_PAGE_SIZE
        if page_size not in PLAYER_PAGE_SIZES:
            raise AppError(
                code=40000,
                message=f"page_size 仅支持 {'/'.join(str(n) for n in PLAYER_PAGE_SIZES)}",
                http_status=400,
            )
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(PlayerTipRecord)
                    .where(PlayerTipRecord.user_id == user.id),
                )
            ).scalar_one(),
        )
        rows = (
            (
                await self._session.execute(
                    select(PlayerTipRecord)
                    .where(PlayerTipRecord.user_id == user.id)
                    .order_by(PlayerTipRecord.paid_at.desc(), PlayerTipRecord.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size),
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "id": int(row.id),
                    "paid_at": row.paid_at.isoformat() if row.paid_at else None,
                    "amount": int(row.amount),
                    "order_no": row.order_no,
                    "channel": row.channel,
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
