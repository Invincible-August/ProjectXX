"""
后台运营动作：道主席位等运行时干预（与配置发布分离，须审计）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAuditLog, AdminUser
from app.schemas.common import AppError
from app.services.admin_rbac import can_publish, can_view, parse_roles
from app.services.dao_lord_service import DaoLordService

logger = logging.getLogger(__name__)


class AdminOpsService:
    """运营干预用例（剔除道主等）。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话。
        """
        self._session = session

    def assert_can_view(self, admin: AdminUser) -> None:
        """只读运营面板。"""
        if not can_view(parse_roles(admin.roles)):
            raise AppError(code=40300, message="无后台只读权限", http_status=403)

    def assert_can_ops(self, admin: AdminUser) -> None:
        """
        运行时干预（剔除道主等）。

        与发布同级：须 ``publisher`` 或 ``admin``。
        """
        if not can_publish(parse_roles(admin.roles)):
            raise AppError(code=40300, message="无运营干预权限（须 publisher/admin）", http_status=403)

    async def list_dao_lords(self, admin: AdminUser) -> dict[str, Any]:
        """道主榜只读。"""
        self.assert_can_view(admin)
        seats = await DaoLordService(self._session).list_lordships_board()
        return {"seats": seats}

    async def get_dao_contest(self, admin: AdminUser) -> dict[str, Any]:
        """当前道主之争赛会摘要。"""
        self.assert_can_view(admin)
        from app.services.dao_contest_service import DaoContestService

        svc = DaoContestService(self._session)
        contest = await svc.ensure_current()
        return await svc._public_payload(contest, character=None)

    async def force_start_dao_contest(
        self,
        admin: AdminUser,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """立刻开赛。"""
        self.assert_can_ops(admin)
        from app.services.dao_contest_service import DaoContestService

        data = await DaoContestService(self._session).force_start(note=note)
        await self._write_audit(
            admin,
            action="ops.dao_contest.force_start",
            domain_id="dao_lord",
            summary="立刻开赛：关闭道主之争报名",
            detail={"note": (note or "")[:500], "result": data},
        )
        return data

    async def reopen_dao_contest(
        self,
        admin: AdminUser,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """重新开放报名（联调重置本场）。"""
        self.assert_can_ops(admin)
        from app.services.dao_contest_service import DaoContestService

        data = await DaoContestService(self._session).reopen_for_ops(note=note)
        await self._write_audit(
            admin,
            action="ops.dao_contest.reopen",
            domain_id="dao_lord",
            summary="重新开放道主之争报名（清空报名/对阵）",
            detail={"note": (note or "")[:500], "result": data},
        )
        return data

    async def advance_dao_contest_arena(
        self,
        admin: AdminUser,
        *,
        note: str | None = None,
        until_playing: bool = True,
    ) -> dict[str, Any]:
        """跳过整备/等待等，推进擂台至开战或下一阶段。"""
        self.assert_can_ops(admin)
        from app.services.dao_contest_service import DaoContestService

        data = await DaoContestService(self._session).advance_arena_for_ops(
            note=note,
            until_playing=until_playing,
        )
        await self._write_audit(
            admin,
            action="ops.dao_contest.advance_arena",
            domain_id="dao_lord",
            summary="跳过道主之争等待并推进赛程",
            detail={
                "note": (note or "")[:500],
                "until_playing": until_playing,
                "ops_advance": data.get("ops_advance"),
                "status": (data.get("contest") or {}).get("status"),
                "phase": (data.get("contest") or {}).get("phase"),
            },
        )
        return data

    async def remove_dao_lord(
        self,
        admin: AdminUser,
        *,
        dao_id: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        剔除指定道现任道主 → 空位。

        Args:
            admin: 操作者。
            dao_id: 大道 id。
            note: 可选运营备注。

        Returns:
            剔除结果摘要。
        """
        self.assert_can_ops(admin)
        data = await DaoLordService(self._session).clear_lordship_for_dao(
            dao_id.strip(),
            reason="admin_remove",
        )
        summary = data.get("message") or f"剔除道主 {dao_id}"
        await self._write_audit(
            admin,
            action="ops.dao_lord.remove",
            domain_id="dao_lord",
            summary=str(summary)[:1024],
            detail={
                "dao_id": dao_id,
                "note": (note or "")[:500],
                "result": data,
            },
        )
        logger.info(
            "admin ops remove dao lord admin=%s dao=%s removed=%s",
            admin.username,
            dao_id,
            data.get("removed"),
        )
        return data

    async def _write_audit(
        self,
        admin: AdminUser,
        *,
        action: str,
        domain_id: str | None,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                username=admin.username,
                action=action,
                domain_id=domain_id,
                summary=summary[:1024],
                detail_json=json.dumps(detail or {}, ensure_ascii=False),
            ),
        )
