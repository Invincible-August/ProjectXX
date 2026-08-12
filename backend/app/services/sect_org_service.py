"""
宗门组织应用服务（M7-V+）：总览 / 人事 / 等级 / 设施升级 / buff / 公告 / 俸禄。

服务端权威；任命与升级只在本层写库。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import now_utc
from app.db.models import Character, User
from app.db.models.sect import (
    Sect,
    SectContributionLedger,
    SectFacility,
    SectMember,
    SectRankApplication,
)
from app.domain.game_day import game_day_number
from app.domain.sect_org_rules import (
    RANK_TO_LEGACY_ROLE,
    application_is_auto_passable,
    appoint_locked_same_day,
    can_appoint,
    can_self_apply_rank,
    can_toggle_buff,
    can_upgrade_facility,
    can_upgrade_sect_grade,
    council_action_allowed,
    cultivation_above,
    facility_upgrade_cost,
    grade_label_zh,
    normalize_member_rank,
    ordered_grade_ids,
    rank_label_zh,
    specialty_label_zh,
    unique_rank_occupied,
)
from app.domain.sect_rules import role_label_zh
from app.schemas.common import AppError
from app.services.calendar_service import CalendarService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config
from app.services.sect_service import require_sect_system_enabled

logger = logging.getLogger(__name__)


class SectOrgService:
    """宗门组织用例编排。"""

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: 异步 SQLAlchemy 会话。
        """
        self._session = session
        self._gate = PlayGate(session)

    def _cfg(self):
        """当前 SectsConfig 快照。"""
        return get_game_config().sects

    def _current_game_day(self) -> int:
        """历法游戏日号。"""
        snap = CalendarService().get_snapshot(now_utc())
        return game_day_number(
            now_utc(),
            epoch=str(snap.get("epoch_utc") or get_game_config().calendar.epoch_utc),
            slot_seconds=int(snap.get("slot_seconds") or 60),
        )

    async def _require_member(self, user: User) -> tuple[Character, Sect, SectMember]:
        """要求已入宗；返回角色、宗门、成员。"""
        require_sect_system_enabled()
        character = await self._gate.require_character(user)
        if character.sect_id is None:
            raise AppError(code=40101, message="未入宗，不可用宗门组织功能", http_status=400)
        sect = await self._session.get(Sect, int(character.sect_id))
        if sect is None:
            raise AppError(code=40101, message="宗门不存在", http_status=400)
        member = (
            await self._session.execute(
                select(SectMember).where(SectMember.character_id == character.id),
            )
        ).scalar_one_or_none()
        if member is None:
            raise AppError(code=40101, message="宗门成员记录缺失", http_status=400)
        return character, sect, member

    def _member_rank(self, member: SectMember) -> str:
        """规范化成员职位。"""
        return normalize_member_rank(
            getattr(member, "rank", None),
            getattr(member, "role", None),
        )

    def _parse_buffs(self, sect: Sect) -> list[str]:
        """解析已开启 buff 列表。"""
        raw = getattr(sect, "buffs_json", None) or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(x) for x in data]

    def _set_buffs(self, sect: Sect, buffs: list[str]) -> None:
        """写回 buff JSON。"""
        sect.buffs_json = json.dumps(buffs, ensure_ascii=False)

    async def _facility_levels(self, sect_id: int) -> dict[str, int]:
        """读取设施等级表；缺省补 0。"""
        rows = (
            await self._session.execute(
                select(SectFacility).where(SectFacility.sect_id == sect_id),
            )
        ).scalars().all()
        return {str(r.facility_id): int(r.level) for r in rows}

    async def ensure_default_facilities(self, sect: Sect) -> None:
        """为宗门惰性创建 facility_defs 初始等级行。"""
        cfg = self._cfg()
        existing = await self._facility_levels(sect.id)
        for fid, body in cfg.facility_defs.items():
            if fid in existing:
                continue
            self._session.add(
                SectFacility(
                    sect_id=sect.id,
                    facility_id=str(fid),
                    level=int(body.get("initial_level") or 1),
                ),
            )
        await self._session.flush()

    async def ensure_sect_org_fields(self, sect: Sect) -> None:
        """惰性补齐 grade/specialty（NPC 从模板）。"""
        cfg = self._cfg()
        if not getattr(sect, "grade", None):
            sect.grade = "hut"
        if sect.kind == "npc" and sect.template_id:
            npc = cfg.npc_sects.get(str(sect.template_id)) or {}
            if not getattr(sect, "specialty", None):
                sect.specialty = str(npc.get("specialty") or "") or None
            # NPC 固定等级写模板值（若仍为默认 hut 且模板有更高档）
            tpl_grade = str(npc.get("grade") or "")
            if tpl_grade and sect.grade in ("hut", "", None):
                sect.grade = tpl_grade
            elif tpl_grade and sect.kind == "npc":
                # NPC 始终以模板为准
                sect.grade = tpl_grade
        await self.ensure_default_facilities(sect)
        await self._session.flush()

    async def _apply_contribution(
        self,
        member: SectMember,
        *,
        delta: int,
        reason: str,
        note_zh: str | None,
    ) -> None:
        """增减贡献并写流水。"""
        new_bal = int(member.contribution) + int(delta)
        if new_bal < 0:
            raise AppError(code=40102, message="贡献不足", http_status=400)
        member.contribution = new_bal
        self._session.add(
            SectContributionLedger(
                sect_id=member.sect_id,
                character_id=member.character_id,
                delta=int(delta),
                reason=reason,
                note_zh=note_zh,
                balance_after=new_bal,
            ),
        )

    async def _set_member_rank(self, member: SectMember, new_rank: str, *, game_day: int) -> None:
        """写入 rank + 兼容 role，并记录任命日。"""
        member.rank = new_rank
        member.role = RANK_TO_LEGACY_ROLE.get(new_rank, "member")
        member.last_appoint_game_day = int(game_day)

    async def _lazy_resolve_applications(self, sect_id: int) -> int:
        """懒结算：贡献自升申请到日自动通过。返回处理条数。"""
        cfg = self._cfg()
        day = self._current_game_day()
        delay = int(cfg.promotion_auto_approve_after_game_days or 1)
        rows = (
            await self._session.execute(
                select(SectRankApplication).where(
                    SectRankApplication.sect_id == sect_id,
                    SectRankApplication.status == "pending",
                    SectRankApplication.kind == "contrib_self",
                ),
            )
        ).scalars().all()
        resolved = 0
        for app in rows:
            if not application_is_auto_passable(app.target_rank, cfg.disciple_ranks):
                continue
            if int(app.apply_game_day) + delay > day:
                continue
            member = (
                await self._session.execute(
                    select(SectMember).where(
                        SectMember.character_id == app.character_id,
                        SectMember.sect_id == sect_id,
                    ),
                )
            ).scalar_one_or_none()
            if member is None:
                app.status = "cancelled"
                continue
            ok, _ = can_self_apply_rank(
                current_rank=self._member_rank(member),
                target_rank=app.target_rank,
                contribution=int(member.contribution),
                disciple_ranks=cfg.disciple_ranks,
            )
            if not ok:
                app.status = "rejected"
                app.resolve_game_day = day
                continue
            await self._set_member_rank(member, app.target_rank, game_day=day)
            app.status = "auto_passed"
            app.resolve_game_day = day
            resolved += 1
        if resolved:
            await self._session.flush()
        return resolved

    async def overview(self, user: User) -> dict[str, Any]:
        """
        宗门组织总览。

        Args:
            user: 当前用户。

        Returns:
            dict: 等级/人数/设施/buff/权限。
        """
        character, sect, member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        await self._lazy_resolve_applications(sect.id)
        cfg = self._cfg()
        rank = self._member_rank(member)
        levels = await self._facility_levels(sect.id)
        member_count = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(SectMember)
                    .where(SectMember.sect_id == sect.id),
                )
            ).scalar_one(),
        )
        grade = str(sect.grade or "hut")
        grade_body = cfg.sect_grades.get(grade) or {}
        buffs = self._parse_buffs(sect)
        actions = list((cfg.disciple_ranks.get(rank) or {}).get("council_actions") or [])
        nxt = None
        nxt_id = None
        from app.domain.sect_org_rules import next_grade_id

        nxt_id = next_grade_id(grade, cfg.sect_grades)
        if nxt_id:
            nxt = {
                "grade": nxt_id,
                "label_zh": grade_label_zh(nxt_id, cfg.sect_grades),
                "require_facilities": dict(
                    (cfg.sect_grades.get(nxt_id) or {}).get("upgrade_require_facilities")
                    or {},
                ),
            }
        fac_items = []
        for fid, fdef in cfg.facility_defs.items():
            fac_items.append(
                {
                    "facility_id": fid,
                    "label_zh": str(fdef.get("label_zh") or fid),
                    "summary": str(fdef.get("summary") or ""),
                    "level": int(levels.get(fid) or 0),
                    "max_level": min(
                        int(fdef.get("max_level") or 10),
                        int(grade_body.get("facility_level_cap") or 10),
                    ),
                },
            )
        return {
            "sect_id": sect.id,
            "name": sect.name,
            "kind": sect.kind,
            "grade": grade,
            "grade_label_zh": grade_label_zh(grade, cfg.sect_grades),
            "grade_order": int(grade_body.get("order") or 1),
            "next_grade": nxt,
            "specialty": sect.specialty,
            "specialty_label_zh": specialty_label_zh(sect.specialty, cfg.specialties),
            "announcement": sect.announcement,
            "spirit_stone_pool": int(getattr(sect, "spirit_stone_pool", 0) or 0),
            "member_count": member_count,
            "max_members": int(grade_body.get("max_members") or 20),
            "idle_bonus": float(
                grade_body.get("idle_bonus") or cfg.idle_bonus_vs_wanderer,
            ),
            "active_buffs": [
                {
                    "buff_id": bid,
                    "label_zh": str((cfg.sect_buffs.get(bid) or {}).get("label_zh") or bid),
                }
                for bid in buffs
            ],
            "max_active_buffs": int(grade_body.get("max_active_buffs") or 1),
            "buff_catalog": [
                {
                    "buff_id": bid,
                    "label_zh": str(body.get("label_zh") or bid),
                    "summary": str(body.get("summary") or ""),
                    "tier": int(body.get("tier") or 1),
                    "cost_spirit_stones_per_day": int(
                        body.get("cost_spirit_stones_per_day") or 0,
                    ),
                    "active": bid in buffs,
                }
                for bid, body in cfg.sect_buffs.items()
            ],
            "facilities": fac_items,
            "my_rank": rank,
            "my_rank_label_zh": rank_label_zh(rank, cfg.disciple_ranks),
            "my_contrib": int(member.contribution),
            "my_actions": actions,
            "game_day": self._current_game_day(),
            "specialties_catalog": [
                {
                    "specialty_id": sid,
                    "label_zh": str(body.get("label_zh") or sid),
                    "summary": str(body.get("summary") or ""),
                }
                for sid, body in cfg.specialties.items()
            ],
            "grades_catalog": [
                {
                    "grade": gid,
                    "label_zh": grade_label_zh(gid, cfg.sect_grades),
                    "order": int((cfg.sect_grades.get(gid) or {}).get("order") or 0),
                    "max_members": int(
                        (cfg.sect_grades.get(gid) or {}).get("max_members") or 0,
                    ),
                }
                for gid in ordered_grade_ids(cfg.sect_grades)
            ],
        }

    async def list_members(self, user: User) -> dict[str, Any]:
        """门众列表。"""
        _character, sect, _member = await self._require_member(user)
        await self._lazy_resolve_applications(sect.id)
        cfg = self._cfg()
        rows = (
            await self._session.execute(
                select(SectMember, Character)
                .join(Character, Character.id == SectMember.character_id)
                .where(SectMember.sect_id == sect.id)
                .order_by(SectMember.id.asc()),
            )
        ).all()
        items = []
        for m, ch in rows:
            r = self._member_rank(m)
            items.append(
                {
                    "character_id": ch.id,
                    "name": ch.name,
                    "rank": r,
                    "rank_label_zh": rank_label_zh(r, cfg.disciple_ranks),
                    "role": m.role,
                    "role_label_zh": role_label_zh(m.role),
                    "contrib": int(m.contribution),
                    "major_realm": ch.major_realm,
                    "cultivation": int(getattr(ch, "realm_progress", 0) or 0),
                },
            )
        return {"items": items, "count": len(items)}

    async def list_applications(self, user: User) -> dict[str, Any]:
        """待处理/近期申请列表。"""
        _c, sect, member = await self._require_member(user)
        await self._lazy_resolve_applications(sect.id)
        cfg = self._cfg()
        rows = (
            await self._session.execute(
                select(SectRankApplication)
                .where(SectRankApplication.sect_id == sect.id)
                .order_by(SectRankApplication.id.desc())
                .limit(50),
            )
        ).scalars().all()
        items = []
        for app in rows:
            ch = await self._session.get(Character, app.character_id)
            items.append(
                {
                    "id": app.id,
                    "character_id": app.character_id,
                    "name": ch.name if ch else str(app.character_id),
                    "target_rank": app.target_rank,
                    "target_rank_label_zh": rank_label_zh(
                        app.target_rank,
                        cfg.disciple_ranks,
                    ),
                    "kind": app.kind,
                    "status": app.status,
                    "apply_game_day": app.apply_game_day,
                    "resolve_game_day": app.resolve_game_day,
                },
            )
        return {
            "items": items,
            "can_appoint": council_action_allowed(
                rank=self._member_rank(member),
                action="appoint",
                disciple_ranks=cfg.disciple_ranks,
            ),
        }

    async def apply_rank(self, user: User, *, target_rank: str) -> dict[str, Any]:
        """
        议事厅申请晋升（贡献自升或毛遂自荐）。

        Args:
            user: 当前用户。
            target_rank: 目标职位键。

        Returns:
            dict: 申请结果。
        """
        character, sect, member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        day = self._current_game_day()
        current = self._member_rank(member)
        ok, reason = can_self_apply_rank(
            current_rank=current,
            target_rank=target_rank,
            contribution=int(member.contribution),
            disciple_ranks=cfg.disciple_ranks,
        )
        if not ok:
            raise AppError(code=40000, message=reason or "不可申请", http_status=400)
        # 已有 pending 则拒
        pending = (
            await self._session.execute(
                select(SectRankApplication).where(
                    SectRankApplication.sect_id == sect.id,
                    SectRankApplication.character_id == character.id,
                    SectRankApplication.status == "pending",
                ),
            )
        ).scalar_one_or_none()
        if pending is not None:
            raise AppError(code=40000, message="已有待处理申请", http_status=400)
        kind = (
            "self_recommend"
            if list((cfg.disciple_ranks.get(target_rank) or {}).get("appoint_by") or [])
            else "contrib_self"
        )
        app = SectRankApplication(
            sect_id=sect.id,
            character_id=character.id,
            target_rank=target_rank,
            kind=kind,
            status="pending",
            apply_game_day=day,
        )
        self._session.add(app)
        await self._session.flush()
        msg = (
            "已提交毛遂自荐，待有权者任命"
            if kind == "self_recommend"
            else f"已提交晋升申请，将于游戏日 {day + int(cfg.promotion_auto_approve_after_game_days)} 自动通过"
        )
        return {
            "message": msg,
            "application_id": app.id,
            "kind": kind,
            "target_rank": target_rank,
            "target_rank_label_zh": rank_label_zh(target_rank, cfg.disciple_ranks),
            "apply_game_day": day,
        }

    async def appoint_rank(
        self,
        user: User,
        *,
        target_character_id: int,
        target_rank: str,
    ) -> dict[str, Any]:
        """
        任命门众职位。

        Args:
            user: 任命者。
            target_character_id: 被任命角色。
            target_rank: 目标职位。

        Returns:
            dict: 结果。
        """
        character, sect, actor_member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        day = self._current_game_day()
        actor_rank = self._member_rank(actor_member)
        if not council_action_allowed(
            rank=actor_rank,
            action="appoint",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权任命", http_status=403)
        ok, reason = can_appoint(
            actor_rank=actor_rank,
            target_rank=target_rank,
            disciple_ranks=cfg.disciple_ranks,
        )
        if not ok:
            raise AppError(code=40000, message=reason or "不可任命", http_status=400)
        target_member = (
            await self._session.execute(
                select(SectMember).where(
                    SectMember.sect_id == sect.id,
                    SectMember.character_id == int(target_character_id),
                ),
            )
        ).scalar_one_or_none()
        if target_member is None:
            raise AppError(code=40000, message="目标非本宗门众", http_status=400)
        if appoint_locked_same_day(
            last_appoint_game_day=target_member.last_appoint_game_day,
            current_game_day=day,
        ):
            raise AppError(code=40000, message="该弟子今日已被任命，不可再改", http_status=400)
        all_ranks = [
            self._member_rank(m)
            for m in (
                await self._session.execute(
                    select(SectMember).where(SectMember.sect_id == sect.id),
                )
            ).scalars().all()
        ]
        if unique_rank_occupied(
            target_rank=target_rank,
            existing_ranks=all_ranks,
            disciple_ranks=cfg.disciple_ranks,
            exclude_character_rank=self._member_rank(target_member),
        ):
            raise AppError(code=40000, message="该唯一职位已被占用", http_status=400)
        # 大长老须修为高于掌门
        tbody = cfg.disciple_ranks.get(target_rank) or {}
        if bool(tbody.get("require_cultivation_above_leader")):
            target_ch = await self._session.get(Character, int(target_character_id))
            leader_ch = None
            if sect.leader_character_id:
                leader_ch = await self._session.get(Character, int(sect.leader_character_id))
            if target_ch is None or leader_ch is None:
                raise AppError(code=40000, message="无法校验修为（掌门缺失）", http_status=400)
            if not cultivation_above(
                actor_cultivation=int(getattr(target_ch, "realm_progress", 0) or 0),
                leader_cultivation=int(getattr(leader_ch, "realm_progress", 0) or 0),
            ):
                raise AppError(
                    code=40000,
                    message="大长老修为必须高于掌门",
                    http_status=400,
                )
        await self._set_member_rank(target_member, target_rank, game_day=day)
        if target_rank == "leader":
            sect.leader_character_id = int(target_character_id)
        if target_rank == "founder":
            sect.founder_character_id = int(target_character_id)
        # 关闭同角色 pending 自荐
        pending_apps = (
            await self._session.execute(
                select(SectRankApplication).where(
                    SectRankApplication.sect_id == sect.id,
                    SectRankApplication.character_id == int(target_character_id),
                    SectRankApplication.status == "pending",
                ),
            )
        ).scalars().all()
        for app in pending_apps:
            if app.target_rank == target_rank:
                app.status = "appointed"
                app.resolve_game_day = day
            else:
                app.status = "cancelled"
                app.resolve_game_day = day
        await self._session.flush()
        logger.info(
            "sect appoint sect_id=%s by=%s target=%s rank=%s",
            sect.id,
            character.id,
            target_character_id,
            target_rank,
        )
        return {
            "message": f"已任命为「{rank_label_zh(target_rank, cfg.disciple_ranks)}」",
            "target_character_id": int(target_character_id),
            "rank": target_rank,
            "rank_label_zh": rank_label_zh(target_rank, cfg.disciple_ranks),
        }

    async def claim_salary(self, user: User) -> dict[str, Any]:
        """议事厅领取日俸（贡献）。"""
        _c, sect, member = await self._require_member(user)
        cfg = self._cfg()
        day = self._current_game_day()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="salary",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权领取俸禄", http_status=403)
        if member.salary_claimed_game_day is not None and int(
            member.salary_claimed_game_day,
        ) == day:
            raise AppError(code=40000, message="今日俸禄已领取", http_status=400)
        amount = int((cfg.disciple_ranks.get(rank) or {}).get("salary_contribution") or 0)
        if amount <= 0:
            raise AppError(code=40000, message="当前职位无俸禄", http_status=400)
        await self._apply_contribution(
            member,
            delta=amount,
            reason="salary",
            note_zh="议事厅日俸",
        )
        member.salary_claimed_game_day = day
        await self._session.flush()
        return {
            "message": f"已领取俸禄贡献 +{amount}",
            "amount": amount,
            "contrib": int(member.contribution),
            "game_day": day,
        }

    async def set_announcement(self, user: User, *, text_zh: str) -> dict[str, Any]:
        """发布/修改宗门公告。"""
        _c, sect, member = await self._require_member(user)
        cfg = self._cfg()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="announce",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权发布公告", http_status=403)
        cleaned = (text_zh or "").strip()
        if len(cleaned) > int(cfg.max_announcement_len):
            raise AppError(
                code=40000,
                message=f"公告过长（最多 {cfg.max_announcement_len} 字）",
                http_status=400,
            )
        sect.announcement = cleaned or None
        await self._session.flush()
        return {"message": "公告已更新", "announcement": sect.announcement}

    async def upgrade_facility(self, user: User, *, facility_id: str) -> dict[str, Any]:
        """升级宗门设施（扣贡献）。"""
        _c, sect, member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="upgrade_facility",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权升级设施", http_status=403)
        levels = await self._facility_levels(sect.id)
        cur = int(levels.get(facility_id) or 0)
        if cur <= 0:
            # 惰性补行
            await self.ensure_default_facilities(sect)
            levels = await self._facility_levels(sect.id)
            cur = int(levels.get(facility_id) or 1)
        ok, reason, next_lv = can_upgrade_facility(
            facility_id=facility_id,
            current_level=cur,
            sect_grade=str(sect.grade or "hut"),
            facility_defs=cfg.facility_defs,
            sect_grades=cfg.sect_grades,
        )
        if not ok:
            raise AppError(code=40000, message=reason or "不可升级", http_status=400)
        cost = facility_upgrade_cost(
            current_level=cur,
            cost_base=int(cfg.facility_upgrade_cost_base),
            cost_per_level=int(cfg.facility_upgrade_cost_per_level),
        )
        await self._apply_contribution(
            member,
            delta=-cost,
            reason="facility_upgrade",
            note_zh=f"升级设施 {facility_id}→{next_lv}",
        )
        row = (
            await self._session.execute(
                select(SectFacility).where(
                    SectFacility.sect_id == sect.id,
                    SectFacility.facility_id == facility_id,
                ),
            )
        ).scalar_one()
        row.level = next_lv
        await self._session.flush()
        label = str((cfg.facility_defs.get(facility_id) or {}).get("label_zh") or facility_id)
        return {
            "message": f"「{label}」已升至 {next_lv} 级",
            "facility_id": facility_id,
            "level": next_lv,
            "cost_contribution": cost,
            "contrib": int(member.contribution),
        }

    async def upgrade_grade(self, user: User) -> dict[str, Any]:
        """升级宗门等级（扣宗门灵石库）。"""
        _c, sect, member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="upgrade_grade",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权升级宗门等级", http_status=403)
        levels = await self._facility_levels(sect.id)
        ok, reason, nxt = can_upgrade_sect_grade(
            current_grade=str(sect.grade or "hut"),
            facility_levels=levels,
            sect_grades=cfg.sect_grades,
            is_npc=sect.kind == "npc",
        )
        if not ok or not nxt:
            raise AppError(code=40000, message=reason or "不可升级", http_status=400)
        cost = int(cfg.grade_upgrade_spirit_stones_base) * int(
            (cfg.sect_grades.get(nxt) or {}).get("order") or 1,
        )
        pool = int(getattr(sect, "spirit_stone_pool", 0) or 0)
        if pool < cost:
            raise AppError(
                code=40102,
                message=f"宗门灵石库不足：升级需 {cost}",
                http_status=400,
            )
        sect.spirit_stone_pool = pool - cost
        sect.grade = nxt
        await self._session.flush()
        return {
            "message": f"宗门已晋升为「{grade_label_zh(nxt, cfg.sect_grades)}」",
            "grade": nxt,
            "grade_label_zh": grade_label_zh(nxt, cfg.sect_grades),
            "cost_spirit_stones": cost,
            "spirit_stone_pool": int(sect.spirit_stone_pool),
        }

    async def toggle_buff(self, user: User, *, buff_id: str, enable: bool) -> dict[str, Any]:
        """开启/关闭宗门 buff。"""
        _c, sect, member = await self._require_member(user)
        await self.ensure_sect_org_fields(sect)
        cfg = self._cfg()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="toggle_buff",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权管理宗门增益", http_status=403)
        active = self._parse_buffs(sect)
        ok, reason = can_toggle_buff(
            buff_id=buff_id,
            active_buffs=active,
            enable=enable,
            sect_grade=str(sect.grade or "hut"),
            sect_buffs=cfg.sect_buffs,
            sect_grades=cfg.sect_grades,
        )
        if not ok:
            raise AppError(code=40000, message=reason or "不可操作", http_status=400)
        if enable:
            body = cfg.sect_buffs.get(buff_id) or {}
            cost = int(body.get("cost_spirit_stones_per_day") or 0)
            pool = int(getattr(sect, "spirit_stone_pool", 0) or 0)
            if pool < cost:
                raise AppError(
                    code=40102,
                    message=f"宗门灵石库不足：开启需 {cost}",
                    http_status=400,
                )
            sect.spirit_stone_pool = pool - cost
            active.append(buff_id)
        else:
            active = [b for b in active if b != buff_id]
        self._set_buffs(sect, active)
        await self._session.flush()
        label = str((cfg.sect_buffs.get(buff_id) or {}).get("label_zh") or buff_id)
        return {
            "message": f"已{'开启' if enable else '关闭'}「{label}」",
            "active_buffs": active,
            "spirit_stone_pool": int(sect.spirit_stone_pool or 0),
        }

    async def start_war_stub(self, user: User, *, war_kind: str) -> dict[str, Any]:
        """势力战/宗门战入口占位（→M11）。"""
        _c, _sect, member = await self._require_member(user)
        cfg = self._cfg()
        rank = self._member_rank(member)
        if not council_action_allowed(
            rank=rank,
            action="war_start",
            disciple_ranks=cfg.disciple_ranks,
        ):
            raise AppError(code=40000, message="无权发起战事", http_status=403)
        raise AppError(
            code=40110,
            message=f"「{war_kind}」尚未开放，完整势力战/宗门战见里程碑 M11",
            http_status=501,
        )
