"""交易行 / 拍卖 / 面交 HTTP 路由（M7 L2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user, get_trade_service
from app.db.models import User
from app.schemas.common import success
from app.schemas.social_trade import (
    AuctionBidRequest,
    AuctionCreateRequest,
    BazaarDealRequest,
    FaceTradeConfirmRequest,
    FaceTradeInviteRequest,
    FaceTradeLockRequest,
    FaceTradeOfferRequest,
    TradeListingCreateRequest,
)
from app.services.trade_service import TradeService

router = APIRouter(prefix="/trade", tags=["trade"])


@router.get("/listings", response_model=None)
async def trade_list_listings(
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """交易行列表。"""
    return success(await svc.list_listings(current_user))


@router.post("/listings", response_model=None)
async def trade_create_listing(
    body: TradeListingCreateRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """上架。"""
    return success(
        await svc.create_listing(
            current_user,
            mode=body.mode,
            offer_items=[x.model_dump() for x in body.offer_items],
            price_spirit_stones=body.price_spirit_stones,
            ask_items=[x.model_dump() for x in body.ask_items],
        ),
    )


@router.post("/listings/{listing_id}/buy", response_model=None)
async def trade_buy_listing(
    listing_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """购买。"""
    return success(await svc.buy_listing(current_user, listing_id))


@router.post("/listings/{listing_id}/cancel", response_model=None)
async def trade_cancel_listing(
    listing_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """撤单。"""
    return success(await svc.cancel_listing(current_user, listing_id))


@router.get("/auctions", response_model=None)
async def trade_list_auctions(
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """拍卖列表。"""
    return success(await svc.list_auctions(current_user))


@router.post("/auctions", response_model=None)
async def trade_create_auction(
    body: AuctionCreateRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """上架拍卖。"""
    return success(
        await svc.create_auction(
            current_user,
            offer_items=[x.model_dump() for x in body.offer_items],
            start_price=body.start_price,
            duration_sec=body.duration_sec,
        ),
    )


@router.post("/auctions/{lot_id}/bid", response_model=None)
async def trade_bid_auction(
    lot_id: int,
    body: AuctionBidRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """出价。"""
    return success(await svc.bid_auction(current_user, lot_id, amount=body.amount))


@router.post("/face", response_model=None)
async def trade_face_invite(
    body: FaceTradeInviteRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """发起交易（pending_invite）。"""
    return success(
        await svc.face_invite(
            current_user,
            peer_character_id=body.peer_character_id,
            peer_name=body.peer_name,
        ),
    )


@router.get("/face/pending", response_model=None)
async def trade_face_pending(
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """收到的待接受交易邀请（大厅邀请列表）。"""
    return success(await svc.face_list_pending(current_user))


@router.get("/face/invite-options", response_model=None)
async def trade_face_invite_options(
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """交易快捷选人：道友 / 道侣 / 同门 / 师徒。"""
    return success(await svc.face_invite_options(current_user))


@router.get("/face/{session_id}", response_model=None)
async def trade_face_get(
    session_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """交易会话状态。"""
    return success(await svc.face_get(current_user, session_id))


@router.post("/face/{session_id}/accept", response_model=None)
async def trade_face_accept(
    session_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """受邀方接受交易 → browsing。"""
    return success(await svc.face_accept(current_user, session_id))


@router.post("/face/{session_id}/reject", response_model=None)
async def trade_face_reject(
    session_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """受邀方拒绝交易。"""
    return success(await svc.face_reject(current_user, session_id))


@router.post("/face/{session_id}/offer", response_model=None)
async def trade_face_offer(
    session_id: int,
    body: FaceTradeOfferRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """更新交易草稿报价（不托管）。"""
    return success(
        await svc.face_set_offer(
            current_user,
            session_id,
            items=[x.model_dump() for x in body.items],
            spirit_stones=body.spirit_stones,
            version=body.version,
            vessel_offer=(
                body.vessel_offer.model_dump() if body.vessel_offer is not None else None
            ),
        ),
    )


@router.post("/face/{session_id}/lock", response_model=None)
async def trade_face_lock(
    session_id: int,
    body: FaceTradeLockRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """锁定己方报价并托管。"""
    return success(
        await svc.face_lock(current_user, session_id, version=body.version),
    )


@router.post("/face/{session_id}/confirm", response_model=None)
async def trade_face_confirm(
    session_id: int,
    body: FaceTradeConfirmRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """确认交易（双方已锁定）。"""
    return success(
        await svc.face_confirm(current_user, session_id, version=body.version),
    )


@router.post("/face/{session_id}/cancel", response_model=None)
async def trade_face_cancel(
    session_id: int,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """取消交易并退回已托管侧。"""
    return success(await svc.face_cancel(current_user, session_id))


@router.get("/bazaar", response_model=None)
async def trade_bazaar_catalog(
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """NPC 坊市货架（固定售价）与可回收摘要。"""
    return success(await svc.list_bazaar(current_user))


@router.post("/bazaar/buy", response_model=None)
async def trade_bazaar_buy(
    body: BazaarDealRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """向坊市购买固定货架道具。"""
    return success(
        await svc.bazaar_buy(
            current_user,
            item_id=body.item_id,
            quantity=body.quantity,
        ),
    )


@router.post("/bazaar/sell", response_model=None)
async def trade_bazaar_sell(
    body: BazaarDealRequest,
    svc: TradeService = Depends(get_trade_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """向坊市出售道具换灵石。"""
    return success(
        await svc.bazaar_sell(
            current_user,
            item_id=body.item_id,
            quantity=body.quantity,
        ),
    )
