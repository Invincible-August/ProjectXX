"""后台玩家账号管理：列表检索、封号、重置密码、改联系方式、派发仙缘、打赏/广告流水。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.admin_player import (
    AUDIT_DOMAIN_PLAYER_ACCOUNTS,
    DEFAULT_RESET_PASSWORD,
    PLAYER_DEFAULT_PAGE_SIZE,
    PLAYER_PAGE_SIZES,
    build_player_ops_schema,
)
from app.core.security import hash_password
from app.core.time_utils import ensure_aware_utc, now_utc
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    Character,
    FateLuckGrantRecord,
    PlayerAdWatchRecord,
    PlayerTipRecord,
    User,
)
from app.schemas.common import AppError
from app.services.admin_rbac import can_publish, can_view, parse_roles

logger = logging.getLogger(__name__)

# 邮箱格式（运营改联系方式）
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# 大陆手机号 11 位
_PHONE_RE = re.compile(r"^1\d{10}$")

# 兼容旧测试：``from … import DEFAULT_RESET_PASSWORD``
__all__ = ["AdminPlayerService", "DEFAULT_RESET_PASSWORD"]


class AdminPlayerService:
    """玩家账号运营用例。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 DB 会话。
        """
        self._session = session

    def assert_can_view(self, admin: AdminUser) -> None:
        """只读账号列表。"""
        if not can_view(parse_roles(admin.roles)):
            raise AppError(code=40300, message="无后台只读权限", http_status=403)

    def assert_can_ops(self, admin: AdminUser) -> None:
        """
        账号干预（封号 / 重置密码 / 改联系方式 / 派发仙缘 / 记录打赏）。

        与运营干预同级：须 ``publisher`` 或 ``admin``。
        """
        if not can_publish(parse_roles(admin.roles)):
            raise AppError(
                code=40300,
                message="无账号运营权限（须 publisher/admin）",
                http_status=403,
            )

    def get_ops_schema(self, admin: AdminUser) -> dict[str, Any]:
        """返回玩家运营中文字段契约（§0.0.1）。"""
        self.assert_can_view(admin)
        return build_player_ops_schema()

    async def list_accounts(
        self,
        admin: AdminUser,
        *,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        分页列出玩家账号（左联角色取仙缘）。

        Args:
            admin: 当前管理员。
            q: 可选关键字；匹配 email / phone / public_uid / username / 数据库 id。
            page: 页码（从 1 起）。
            page_size: 每页条数（10/20/50/100）。

        Returns:
            dict: items / total / page / page_size。
        """
        self.assert_can_view(admin)
        page = max(1, int(page))
        page_size = int(page_size) if page_size else PLAYER_DEFAULT_PAGE_SIZE
        if page_size not in PLAYER_PAGE_SIZES:
            raise AppError(
                code=40000,
                message=f"page_size 仅支持 {'/'.join(str(n) for n in PLAYER_PAGE_SIZES)}",
                http_status=400,
            )

        filters: list[Any] = []
        keyword = (q or "").strip()
        if keyword:
            # SQLite / PostgreSQL 共用：lower(col) LIKE lower(%kw%)，避免方言 ILIKE 分叉
            like = f"%{keyword.lower()}%"
            or_parts: list[Any] = [
                func.lower(User.email).like(like),
                func.lower(User.phone).like(like),
                func.lower(User.username).like(like),
                func.lower(User.public_uid).like(like),
            ]
            if keyword.isdigit():
                uid = int(keyword)
                or_parts.append(User.id == uid)
            filters.append(or_(*or_parts))

        count_stmt = select(func.count()).select_from(User)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        stmt = (
            select(User, Character)
            .outerjoin(Character, Character.user_id == User.id)
            .order_by(User.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            stmt = stmt.where(*filters)

        rows = (await self._session.execute(stmt)).all()
        items = [self._row_to_item(user, character) for user, character in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def ban_account(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        banned: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        """封号或解封（``users.is_active``）。"""
        self.assert_can_ops(admin)
        user = await self._get_user(user_id)
        user.is_active = not banned
        await self._session.flush()
        action = "ops.player.ban" if banned else "ops.player.unban"
        summary = f"{'封号' if banned else '解封'} user_id={user_id}"
        await self._write_audit(
            admin,
            action=action,
            summary=summary,
            detail={"user_id": user_id, "banned": banned, "note": (note or "")[:500]},
        )
        character = await self._get_character_optional(user_id)
        return self._row_to_item(user, character)

    async def soft_delete_account(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        软删账号：``is_active=False``（非物理删除）。

        登录时提示「无效用户名」。与封号共用 ``is_active`` 字段。
        """
        self.assert_can_ops(admin)
        user = await self._get_user(user_id)
        user.is_active = False
        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.soft_delete",
            summary=f"删除账号（软删） user_id={user_id}",
            detail={"user_id": user_id, "note": (note or "")[:500]},
        )
        character = await self._get_character_optional(user_id)
        return self._row_to_item(user, character)

    async def set_gm(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        is_gm: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        设为 / 取消 GM（功能暂未开放；仅改标记与 public_uid 前缀）。
        """
        self.assert_can_ops(admin)
        from app.services.public_uid import rewrite_public_uid_for_gm

        user = await self._get_user(user_id)
        user.is_gm = bool(is_gm)
        new_uid = await rewrite_public_uid_for_gm(
            self._session,
            user,
            is_gm=bool(is_gm),
        )
        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.set_gm" if is_gm else "ops.player.unset_gm",
            summary=f"{'设为' if is_gm else '取消'}GM user_id={user_id} public_uid={new_uid}",
            detail={
                "user_id": user_id,
                "is_gm": bool(is_gm),
                "public_uid": new_uid,
                "note": (note or "")[:500],
            },
        )
        character = await self._get_character_optional(user_id)
        return self._row_to_item(user, character)

    async def reset_password(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        """将密码重置为 ``12345678``。"""
        self.assert_can_ops(admin)
        user = await self._get_user(user_id)
        user.password_hash = hash_password(DEFAULT_RESET_PASSWORD)
        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.reset_password",
            summary=f"重置密码 user_id={user_id}",
            detail={
                "user_id": user_id,
                "password_set_to": DEFAULT_RESET_PASSWORD,
                "note": (note or "")[:500],
            },
        )
        character = await self._get_character_optional(user_id)
        return {
            **self._row_to_item(user, character),
            "message": f"密码已重置为 {DEFAULT_RESET_PASSWORD}",
        }

    async def update_contacts(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        email: str | None = None,
        phone: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """修改邮箱与/或手机号；空字符串表示清空该字段。"""
        self.assert_can_ops(admin)
        if email is None and phone is None:
            raise AppError(code=40000, message="请至少提供 email 或 phone", http_status=400)

        user = await self._get_user(user_id)
        before = {"email": user.email, "phone": user.phone}

        if email is not None:
            normalized_email = email.strip().lower() if email.strip() else None
            if normalized_email is not None:
                if not _EMAIL_RE.match(normalized_email):
                    raise AppError(code=40000, message="邮箱格式无效", http_status=400)
                clash = await self._session.scalar(
                    select(User).where(User.email == normalized_email, User.id != user_id),
                )
                if clash is not None:
                    raise AppError(code=40000, message="邮箱已被其他账号占用", http_status=400)
            user.email = normalized_email
            if normalized_email is None:
                user.email_verified = False

        if phone is not None:
            normalized_phone = phone.strip() if phone.strip() else None
            if normalized_phone is not None:
                if not _PHONE_RE.match(normalized_phone):
                    raise AppError(code=40000, message="手机号须为11位大陆号", http_status=400)
                clash = await self._session.scalar(
                    select(User).where(User.phone == normalized_phone, User.id != user_id),
                )
                if clash is not None:
                    raise AppError(code=40000, message="手机号已被其他账号占用", http_status=400)
            user.phone = normalized_phone
            if normalized_phone is None:
                user.phone_verified = False

        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.update_contacts",
            summary=f"修改联系方式 user_id={user_id}",
            detail={
                "user_id": user_id,
                "before": before,
                "after": {"email": user.email, "phone": user.phone},
                "note": (note or "")[:500],
            },
        )
        character = await self._get_character_optional(user_id)
        return self._row_to_item(user, character)

    async def grant_fate_luck(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        amount: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        """向角色派发仙缘，并写入 ``fate_luck_grant_records`` 流水。"""
        self.assert_can_ops(admin)
        amount = int(amount)
        if amount < 1:
            raise AppError(code=40000, message="派发仙缘数量须 ≥ 1", http_status=400)

        user = await self._get_user(user_id)
        character = await self._get_character_optional(user_id)
        if character is None:
            raise AppError(code=40000, message="该账号尚未创角，无法派发仙缘", http_status=400)

        before = int(character.fate_luck or 0)
        after = before + amount
        character.fate_luck = after
        granted_at = now_utc()
        self._session.add(
            FateLuckGrantRecord(
                user_id=user_id,
                character_id=character.id,
                granted_at=granted_at,
                amount=amount,
                before_amount=before,
                after_amount=after,
                note=(note or None),
                created_by_admin_id=admin.id,
                created_by_admin_name=admin.username,
            ),
        )
        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.grant_fate_luck",
            summary=f"派发仙缘 user_id={user_id} +{amount}",
            detail={
                "user_id": user_id,
                "character_id": character.id,
                "amount": amount,
                "before": before,
                "after": after,
                "note": (note or "")[:500],
            },
        )
        return self._row_to_item(user, character)

    async def create_tip_record(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        paid_at: str | datetime,
        channel: str,
        order_no: str,
        amount: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        """手工记录打赏，并累加 ``users.total_recharge_amount``。"""
        self.assert_can_ops(admin)
        user = await self._get_user(user_id)
        amount_i = int(amount)
        if amount_i < 1:
            raise AppError(code=40000, message="打赏金额须 ≥ 1", http_status=400)

        channel_norm = (channel or "").strip()
        if not channel_norm:
            raise AppError(code=40000, message="请填写打赏路径", http_status=400)
        if len(channel_norm) > 64:
            raise AppError(code=40000, message="打赏路径过长", http_status=400)

        order_norm = (order_no or "").strip()
        if not order_norm:
            raise AppError(code=40000, message="请填写订单号", http_status=400)
        if len(order_norm) > 128:
            raise AppError(code=40000, message="订单号过长", http_status=400)

        paid_dt = self._parse_ops_datetime(paid_at, field_zh="打赏时间")

        clash = await self._session.scalar(
            select(PlayerTipRecord)
            .where(
                PlayerTipRecord.user_id == user_id,
                PlayerTipRecord.order_no == order_norm,
            )
            .limit(1),
        )
        if clash is not None:
            raise AppError(code=40000, message="该账号已存在相同订单号的打赏记录", http_status=400)

        record = PlayerTipRecord(
            user_id=user_id,
            paid_at=paid_dt,
            channel=channel_norm,
            order_no=order_norm,
            amount=amount_i,
            note=(note or None),
            created_by_admin_id=admin.id,
            created_by_admin_name=admin.username,
        )
        self._session.add(record)
        user.total_recharge_amount = int(user.total_recharge_amount or 0) + amount_i
        await self._session.flush()
        await self._write_audit(
            admin,
            action="ops.player.create_tip",
            summary=f"记录打赏 user_id={user_id} +{amount_i}",
            detail={
                "user_id": user_id,
                "tip_id": record.id,
                "paid_at": paid_dt.isoformat(),
                "channel": channel_norm,
                "order_no": order_norm,
                "amount": amount_i,
                "total_recharge_amount": int(user.total_recharge_amount),
                "note": (note or "")[:500],
            },
        )
        character = await self._get_character_optional(user_id)
        return {
            "account": self._row_to_item(user, character),
            "tip": self._tip_to_item(record),
        }

    async def list_tip_records(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查看某账号打赏流水。"""
        self.assert_can_view(admin)
        await self._get_user(user_id)
        return await self._paginate_records(
            PlayerTipRecord,
            user_id=user_id,
            page=page,
            page_size=page_size,
            order_col=PlayerTipRecord.paid_at,
            to_item=self._tip_to_item,
        )

    async def list_fate_luck_grants(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查看某账号仙缘派发流水。"""
        self.assert_can_view(admin)
        await self._get_user(user_id)
        return await self._paginate_records(
            FateLuckGrantRecord,
            user_id=user_id,
            page=page,
            page_size=page_size,
            order_col=FateLuckGrantRecord.granted_at,
            to_item=self._grant_to_item,
        )

    async def list_ad_watch_records(
        self,
        admin: AdminUser,
        *,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查看广告观看流水（广告未接入前通常为空）。"""
        self.assert_can_view(admin)
        await self._get_user(user_id)
        result = await self._paginate_records(
            PlayerAdWatchRecord,
            user_id=user_id,
            page=page,
            page_size=page_size,
            order_col=PlayerAdWatchRecord.watched_at,
            to_item=self._ad_to_item,
        )
        result["watch_count"] = result["total"]
        return result

    async def _paginate_records(
        self,
        model: type[Any],
        *,
        user_id: int,
        page: int,
        page_size: int,
        order_col: Any,
        to_item: Any,
    ) -> dict[str, Any]:
        """通用：按 user_id 分页流水。"""
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
                    select(func.count()).select_from(model).where(model.user_id == user_id),
                )
            ).scalar_one(),
        )
        rows = (
            await self._session.execute(
                select(model)
                .where(model.user_id == user_id)
                .order_by(order_col.desc(), model.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size),
            )
        ).scalars().all()
        return {
            "items": [to_item(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "user_id": user_id,
        }

    def _parse_ops_datetime(self, value: str | datetime, *, field_zh: str) -> datetime:
        """解析运营填写的年月日时分秒。"""
        if isinstance(value, datetime):
            return ensure_aware_utc(value)
        raw = str(value or "").strip()
        if not raw:
            raise AppError(code=40000, message=f"请填写{field_zh}", http_status=400)
        normalized = raw.replace("T", " ").replace("Z", "")
        if "+" in normalized[10:]:
            normalized = normalized.split("+", 1)[0].strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return ensure_aware_utc(datetime.strptime(normalized[:19], fmt))
            except ValueError:
                continue
        try:
            return ensure_aware_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError as exc:
            raise AppError(
                code=40000,
                message=f"{field_zh}格式无效，请用 YYYY-MM-DD HH:MM:SS",
                http_status=400,
            ) from exc

    def _tip_to_item(self, row: PlayerTipRecord) -> dict[str, Any]:
        """打赏行 → DTO。"""
        return {
            "id": int(row.id),
            "user_id": int(row.user_id),
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "channel": row.channel,
            "order_no": row.order_no,
            "amount": int(row.amount),
            "note": row.note,
            "created_by_admin_name": row.created_by_admin_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _grant_to_item(self, row: FateLuckGrantRecord) -> dict[str, Any]:
        """仙缘派发行 → DTO。"""
        return {
            "id": int(row.id),
            "user_id": int(row.user_id),
            "character_id": int(row.character_id) if row.character_id else None,
            "granted_at": row.granted_at.isoformat() if row.granted_at else None,
            "amount": int(row.amount),
            "before_amount": int(row.before_amount or 0),
            "after_amount": int(row.after_amount or 0),
            "note": row.note,
            "created_by_admin_name": row.created_by_admin_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _ad_to_item(self, row: PlayerAdWatchRecord) -> dict[str, Any]:
        """广告观看行 → DTO。"""
        return {
            "id": int(row.id),
            "user_id": int(row.user_id),
            "watched_at": row.watched_at.isoformat() if row.watched_at else None,
            "platform": row.platform,
            "ad_unit": row.ad_unit,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _row_to_item(self, user: User, character: Character | None) -> dict[str, Any]:
        """ORM 行 → 列表/详情 DTO。"""
        return {
            "id": int(user.id),
            # 对外账号号（字符串）；API 路径仍用数据库 id
            "user_id": user.public_uid or "",
            "email": user.email,
            "phone": user.phone,
            "is_active": bool(user.is_active),
            "is_banned": not bool(user.is_active),
            "is_gm": bool(getattr(user, "is_gm", False)),
            "fate_luck": int(character.fate_luck or 0) if character else 0,
            "total_recharge_amount": int(user.total_recharge_amount or 0),
            "character_id": int(character.id) if character else None,
            "character_name": character.name if character else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    async def _get_user(self, user_id: int) -> User:
        """按 id 取账号；不存在则 404。"""
        user = await self._session.get(User, int(user_id))
        if user is None:
            raise AppError(code=40000, message="账号不存在", http_status=404)
        return user

    async def _get_character_optional(self, user_id: int) -> Character | None:
        """取账号绑定角色（一账号一角色）。"""
        return await self._session.scalar(
            select(Character).where(Character.user_id == int(user_id)).limit(1),
        )

    async def _write_audit(
        self,
        admin: AdminUser,
        *,
        action: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """写后台审计日志。"""
        self._session.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                username=admin.username,
                action=action,
                domain_id=AUDIT_DOMAIN_PLAYER_ACCOUNTS,
                summary=summary[:1024],
                detail_json=json.dumps(detail or {}, ensure_ascii=False),
            ),
        )
