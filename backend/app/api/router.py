"""在 API_PREFIX 下汇总各业务路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    allocate,
    auth,
    avatar,
    battle,
    breakthrough,
    character,
    constitution,
    craft,
    dao,
    dao_lord,
    facilities,
    ferry,
    formation,
    gm,
    idle,
    inventory,
    pets,
    quench,
    reincarnation,
    server,
    snapshot,
    techniques,
    tribulation,
    verification,
    world,
    world_events,
    ws,
    sect,
    friends,
    trade,
    mail,
    chat,
    heritage,
    mentor,
    dual,
    commerce,
)

api_router = APIRouter()
api_router.include_router(server.router)
api_router.include_router(auth.router)
api_router.include_router(verification.router)
api_router.include_router(character.router)
api_router.include_router(idle.router)
api_router.include_router(breakthrough.router)
api_router.include_router(quench.router)
api_router.include_router(battle.router)
api_router.include_router(gm.router)
# M2 成长深度
api_router.include_router(allocate.router)
api_router.include_router(techniques.router)
api_router.include_router(constitution.router)
# M3 战斗成型
api_router.include_router(formation.router)
api_router.include_router(snapshot.router)
# M4 双线程成长
api_router.include_router(avatar.router)
api_router.include_router(craft.router)
api_router.include_router(inventory.router)
api_router.include_router(pets.router)
# M5 环境与轮回
api_router.include_router(world.router)
api_router.include_router(tribulation.router)
api_router.include_router(ferry.router)
api_router.include_router(reincarnation.router)
# M6 大道 / 道主 / 世界事件 / WS
api_router.include_router(dao.router)
api_router.include_router(dao_lord.router)
api_router.include_router(world_events.router)
api_router.include_router(ws.router)
# M7 宗门 / 道友 / 交易 / 邮件 / 聊天
api_router.include_router(sect.router)
api_router.include_router(friends.router)
api_router.include_router(trade.router)
api_router.include_router(mail.router)
api_router.include_router(chat.router)
api_router.include_router(heritage.router)
api_router.include_router(mentor.router)
api_router.include_router(dual.router)
api_router.include_router(commerce.router)
# ADM 设施/地图/活动只读投影
api_router.include_router(facilities.router)
