"""
FastAPI 依赖注入：数据库会话、当前登录用户，以及各应用服务工厂。
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.common import AppError
from app.services import auth_service
from app.services.allocate_service import AllocateService
from app.services.auth_service import AuthService
from app.services.autochess_service import AutochessService
from app.services.avatar_service import AvatarService
from app.services.battle_service import BattleService
from app.services.breakthrough_service import BreakthroughService
from app.services.quench_service import QuenchService
from app.services.character_service import CharacterService
from app.services.constitution_service import ConstitutionService
from app.services.craft_service import CraftService
from app.services.formation_service import FormationService
from app.services.gm_service import GmService
from app.services.idle_service import IdleService
from app.services.inventory_service import InventoryService
from app.services.pet_service import PetService
from app.services.pet_duel_service import PetDuelService
from app.services.pet_explore_service import PetExploreService
from app.services.pet_hatch_service import PetHatchService
from app.services.play_gate import PlayGate
from app.services.reincarnation_service import ReincarnationService
from app.services.snapshot_service import SnapshotService
from app.services.stamina_service import StaminaService
from app.services.technique_service import TechniqueService
from app.services.tribulation_service import TribulationService
from app.services.verification.service import VerificationService
from app.services.ferry_service import FerryService
from app.services.calendar_service import CalendarService
from app.services.weather_service import WeatherService
from app.services.dao_service import DaoService
from app.services.dao_lord_service import DaoLordService
from app.services.dao_contest_service import DaoContestService
from app.services.world_event_service import WorldEventService
from app.services.sect_service import SectService
from app.services.sect_org_service import SectOrgService
from app.services.sect_facility_service import SectFacilityService
from app.services.friend_service import FriendService
from app.services.trade_service import TradeService
from app.services.mail_service import MailService
from app.services.chat_service import ChatService
from app.services.heritage_service import HeritageService
from app.services.mentor_service import MentorService
from app.services.dual_cultivation_service import DualCultivationService
from app.services.commerce_service import CommerceService
from app.services.avatar_assist_service import AvatarAssistService

logger = logging.getLogger(__name__)

# auto_error=False：缺少头时自行抛出统一业务码 40100，而不是 FastAPI 默认 403
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    从 ``Authorization: Bearer <access_token>`` 解析当前用户。

    Args:
        credentials: HTTPBearer 解析出的凭证；缺失则为 None。
        session: 异步数据库会话。

    Returns:
        User: 活跃的当前用户。

    Raises:
        AppError: 缺少令牌、令牌无效/过期、用户不存在或禁用。
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(code=40100, message="未认证或 access_token 无效", http_status=401)

    raw_token = credentials.credentials
    try:
        claims = decode_token(raw_token, expected_type="access")
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        logger.warning("access token rejected reason=%s", type(exc).__name__)
        raise AppError(
            code=40100,
            message="未认证或 access_token 无效",
            http_status=401,
        ) from exc

    return await auth_service.load_user_by_id(session, user_id)


def get_play_gate(session: AsyncSession = Depends(get_db)) -> PlayGate:
    """
    提供请求级 ``PlayGate``（跨玩法前置：加载角色、清理离线 pending）。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        PlayGate: 角色加载与 pending 处理门禁。
    """
    return PlayGate(session)


def get_battle_service(session: AsyncSession = Depends(get_db)) -> BattleService:
    """
    提供请求级 ``BattleService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        BattleService: PVE 战斗应用服务。
    """
    return BattleService(session)


def get_breakthrough_service(session: AsyncSession = Depends(get_db)) -> BreakthroughService:
    """
    提供请求级 ``BreakthroughService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        BreakthroughService: 突破预览与 attempt 服务。
    """
    return BreakthroughService(session)


def get_quench_service(session: AsyncSession = Depends(get_db)) -> QuenchService:
    """
    提供请求级 ``QuenchService``（炼体淬体）。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        QuenchService: 淬体预览与 attempt 服务。
    """
    return QuenchService(session)


def get_allocate_service(session: AsyncSession = Depends(get_db)) -> AllocateService:
    """
    提供请求级 ``AllocateService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        AllocateService: 资源池分配服务。
    """
    return AllocateService(session)


def get_constitution_service(session: AsyncSession = Depends(get_db)) -> ConstitutionService:
    """
    提供请求级 ``ConstitutionService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        ConstitutionService: 体质背包与镶嵌服务。
    """
    return ConstitutionService(session)


def get_technique_service(session: AsyncSession = Depends(get_db)) -> TechniqueService:
    """
    提供请求级 ``TechniqueService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        TechniqueService: 功法列表与默认发放服务。
    """
    return TechniqueService(session)


def get_gm_service(session: AsyncSession = Depends(get_db)) -> GmService:
    """
    提供请求级 ``GmService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        GmService: 仅开发环境可用的 GM 调参服务。
    """
    return GmService(session)


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    """
    提供请求级 ``AuthService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        AuthService: 注册、登录与令牌用例。
    """
    return AuthService(session)


def get_verification_service(session: AsyncSession = Depends(get_db)) -> VerificationService:
    """
    提供请求级 ``VerificationService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        VerificationService: 短信/邮件/身份核验编排服务。
    """
    return VerificationService(session)


def get_character_service(session: AsyncSession = Depends(get_db)) -> CharacterService:
    """
    提供请求级 ``CharacterService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        CharacterService: 创角与角色面板用例。
    """
    return CharacterService(session)


def get_formation_service(session: AsyncSession = Depends(get_db)) -> FormationService:
    """
    提供请求级 ``FormationService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        FormationService: 布阵预设与占位校验服务。
    """
    return FormationService(session)


def get_snapshot_service(session: AsyncSession = Depends(get_db)) -> SnapshotService:
    """
    提供请求级 ``SnapshotService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        SnapshotService: 防守快照构建 / 更新 / 预览服务。
    """
    return SnapshotService(session)


def get_stamina_service(session: AsyncSession = Depends(get_db)) -> StaminaService:
    """
    提供请求级 ``StaminaService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        StaminaService: 体力惰性恢复与扣减服务。
    """
    return StaminaService(session)


def get_autochess_service(session: AsyncSession = Depends(get_db)) -> AutochessService:
    """
    提供请求级 ``AutochessService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        AutochessService: 自走棋 PVE / PVP 战斗编排服务。
    """
    return AutochessService(session)


def get_idle_service(session: AsyncSession = Depends(get_db)) -> IdleService:
    """
    提供请求级 ``IdleService``。

    Args:
        session: 来自 ``get_db`` 的异步数据库会话。

    Returns:
        IdleService: 挂机结算与离线 pending 用例。
    """
    return IdleService(session)


def get_avatar_service(session: AsyncSession = Depends(get_db)) -> AvatarService:
    """提供请求级 ``AvatarService``。"""
    return AvatarService(session)


def get_avatar_assist_service(
    session: AsyncSession = Depends(get_db),
) -> AvatarAssistService:
    """提供请求级 ``AvatarAssistService``（道友化身助战）。"""
    return AvatarAssistService(session)


def get_craft_service(session: AsyncSession = Depends(get_db)) -> CraftService:
    """提供请求级 ``CraftService``。"""
    return CraftService(session)


def get_inventory_service(session: AsyncSession = Depends(get_db)) -> InventoryService:
    """提供请求级 ``InventoryService``。"""
    return InventoryService(session)


def get_pet_service(session: AsyncSession = Depends(get_db)) -> PetService:
    """提供请求级 ``PetService``。"""
    return PetService(session)


def get_pet_duel_service(session: AsyncSession = Depends(get_db)) -> PetDuelService:
    """提供请求级 ``PetDuelService``。"""
    return PetDuelService(session)


def get_pet_hatch_service(session: AsyncSession = Depends(get_db)) -> PetHatchService:
    """提供请求级 ``PetHatchService``（N5）。"""
    return PetHatchService(session)


def get_pet_explore_service(session: AsyncSession = Depends(get_db)) -> PetExploreService:
    """提供请求级 ``PetExploreService``（M4-D04c）。"""
    return PetExploreService(session)


def get_calendar_service() -> CalendarService:
    """提供 ``CalendarService``（无会话依赖）。"""
    return CalendarService()


def get_weather_service() -> WeatherService:
    """提供 ``WeatherService``。"""
    return WeatherService()


def get_tribulation_service(session: AsyncSession = Depends(get_db)) -> TribulationService:
    """提供请求级 ``TribulationService``。"""
    return TribulationService(session)


def get_ferry_service(session: AsyncSession = Depends(get_db)) -> FerryService:
    """提供请求级 ``FerryService``。"""
    return FerryService(session)


def get_reincarnation_service(
    session: AsyncSession = Depends(get_db),
) -> ReincarnationService:
    """提供请求级 ``ReincarnationService``。"""
    return ReincarnationService(session)


def get_dao_service(session: AsyncSession = Depends(get_db)) -> DaoService:
    """提供请求级 ``DaoService``。"""
    return DaoService(session)


def get_dao_lord_service(session: AsyncSession = Depends(get_db)) -> DaoLordService:
    """提供请求级 ``DaoLordService``。"""
    return DaoLordService(session)


def get_dao_contest_service(session: AsyncSession = Depends(get_db)) -> DaoContestService:
    """提供请求级 ``DaoContestService``。"""
    return DaoContestService(session)


def get_world_event_service(
    session: AsyncSession = Depends(get_db),
) -> WorldEventService:
    """提供请求级 ``WorldEventService``。"""
    return WorldEventService(session)


def get_sect_service(session: AsyncSession = Depends(get_db)) -> SectService:
    """提供请求级 ``SectService``（M7 L1 宗门）。"""
    return SectService(session)


def get_sect_org_service(session: AsyncSession = Depends(get_db)) -> SectOrgService:
    """提供请求级 ``SectOrgService``（M7-V+ 组织/人事）。"""
    return SectOrgService(session)


def get_sect_facility_service(
    session: AsyncSession = Depends(get_db),
) -> SectFacilityService:
    """提供请求级 ``SectFacilityService``（M7-V+ 设施）。"""
    return SectFacilityService(session)


def get_friend_service(session: AsyncSession = Depends(get_db)) -> FriendService:
    """提供请求级 ``FriendService``（M7 L2 道友）。"""
    return FriendService(session)


def get_trade_service(session: AsyncSession = Depends(get_db)) -> TradeService:
    """提供请求级 ``TradeService``（M7 L2 交易）。"""
    return TradeService(session)


def get_mail_service(session: AsyncSession = Depends(get_db)) -> MailService:
    """提供请求级 ``MailService``（M7 L3 邮件/赠送）。"""
    return MailService(session)


def get_chat_service(session: AsyncSession = Depends(get_db)) -> ChatService:
    """提供请求级 ``ChatService``（M7 L4 聊天/队伍）。"""
    return ChatService(session)


def get_heritage_service(session: AsyncSession = Depends(get_db)) -> HeritageService:
    """提供请求级 ``HeritageService``（M7 L5 传承）。"""
    return HeritageService(session)


def get_mentor_service(session: AsyncSession = Depends(get_db)) -> MentorService:
    """提供请求级 ``MentorService``（M7 L6 师徒）。"""
    return MentorService(session)


def get_dual_cultivation_service(
    session: AsyncSession = Depends(get_db),
) -> DualCultivationService:
    """提供请求级 ``DualCultivationService``（M7 L7 双修）。"""
    return DualCultivationService(session)


def get_commerce_service(session: AsyncSession = Depends(get_db)) -> CommerceService:
    """提供请求级 ``CommerceService``（M7 L8 商业化）。"""
    return CommerceService(session)


__all__ = [
    "get_db",
    "get_current_user",
    "get_play_gate",
    "get_battle_service",
    "get_breakthrough_service",
    "get_quench_service",
    "get_allocate_service",
    "get_constitution_service",
    "get_technique_service",
    "get_gm_service",
    "get_auth_service",
    "get_verification_service",
    "get_character_service",
    "get_idle_service",
    "get_formation_service",
    "get_snapshot_service",
    "get_stamina_service",
    "get_autochess_service",
    "get_avatar_service",
    "get_avatar_assist_service",
    "get_craft_service",
    "get_inventory_service",
    "get_pet_service",
    "get_pet_duel_service",
    "get_pet_hatch_service",
    "get_pet_explore_service",
    "get_calendar_service",
    "get_weather_service",
    "get_tribulation_service",
    "get_ferry_service",
    "get_reincarnation_service",
    "get_dao_service",
    "get_dao_lord_service",
    "get_dao_contest_service",
    "get_world_event_service",
    "get_sect_service",
    "get_sect_org_service",
    "get_sect_facility_service",
    "get_friend_service",
    "get_trade_service",
    "get_mail_service",
    "get_chat_service",
    "get_heritage_service",
    "get_mentor_service",
    "get_dual_cultivation_service",
    "get_commerce_service",
]
