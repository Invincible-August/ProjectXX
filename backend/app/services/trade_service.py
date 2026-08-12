"""
交易行 / 拍卖 / 面交应用服务（M7 L2）。
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
from app.db.models.social_trade import (
    AuctionBid,
    AuctionLot,
    FaceTradeSession,
    TradeListing,
)
from app.domain.trade_rules import (
    auction_min_next_bid,
    barter_fee_for_realm,
    item_may_trade,
    listing_fee_amount,
    parse_item_lines,
)
from app.schemas.common import AppError
from app.services.currency_ledger_service import CurrencyLedgerService
from app.services.friend_service import FriendService
from app.services.inventory_service import InventoryService
from app.services.play_gate import PlayGate
from app.services.realm_config import get_game_config

logger = logging.getLogger(__name__)


def require_trade_enabled() -> None:
    """交易总闸。"""
    settings = get_settings()
    if not bool(getattr(settings, "trade_system_enabled", True)):
        raise AppError(code=40000, message="交易系统未开放", http_status=403)


class TradeService:
    """交易用例编排。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = PlayGate(session)
        self._inv = InventoryService(session)
        self._ledger = CurrencyLedgerService(session)

    def _cfg(self):
        return get_game_config().trade

    # ----- listings -----

    async def list_listings(self, user: User) -> dict[str, Any]:
        """开放中的交易行列表（含惰性无逻辑）。"""
        require_trade_enabled()
        await self._gate.require_character(user)
        rows = (
            await self._session.execute(
                select(TradeListing)
                .where(TradeListing.status == "open")
                .order_by(TradeListing.id.desc())
                .limit(100),
            )
        ).scalars().all()
        return {"items": [await self._listing_public(r) for r in rows]}

    async def create_listing(
        self,
        user: User,
        *,
        mode: str,
        offer_items: list[dict[str, Any]],
        price_spirit_stones: int,
        ask_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """上架一口价或易物。"""
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._reject_if_ferry_or_tribulation(character)
        mode_n = (mode or "fixed_price").strip()
        if mode_n not in ("fixed_price", "barter"):
            raise AppError(code=40000, message="mode 须为 fixed_price 或 barter", http_status=400)
        offer = parse_item_lines(offer_items)
        ask = parse_item_lines(ask_items)
        if not offer:
            raise AppError(code=40000, message="上架物品不可为空", http_status=400)
        await self._assert_items_tradable(offer)
        if mode_n == "fixed_price":
            if int(price_spirit_stones) <= 0:
                raise AppError(code=40000, message="一口价须大于 0 灵石", http_status=400)
            ask = []
            fee = 0
        else:
            if not ask:
                raise AppError(code=40000, message="易物须指定索要物品", http_status=400)
            await self._assert_items_tradable(ask)
            fee = barter_fee_for_realm(
                str(character.major_realm),
                self._cfg().barter_fee_by_realm,
                self._cfg().barter_fee_default,
            )
            if int(character.spirit_stones) < fee:
                raise AppError(
                    code=40000,
                    message=f"易物手续费不足：需 {fee} 灵石",
                    http_status=400,
                )
            await self._ledger.adjust_spirit_stones(
                character,
                delta=-fee,
                reason="barter_list_fee",
                note_zh="以物易物上架手续费",
                ref_type="listing",
            )
            await self._ledger.adjust_spirit_stones(
                None,
                delta=fee,
                reason="recycle_fee",
                note_zh="回收：易物上架费",
                ref_type="listing",
            )

        await self._escrow_take(character, offer)
        row = TradeListing(
            seller_character_id=character.id,
            mode=mode_n,
            offer_json=json.dumps(offer, ensure_ascii=False),
            price_spirit_stones=int(price_spirit_stones) if mode_n == "fixed_price" else 0,
            ask_json=json.dumps(ask, ensure_ascii=False),
            status="open",
            fee_paid=int(fee),
        )
        self._session.add(row)
        await self._session.flush()
        if mode_n == "fixed_price":
            # 将 listing id 写入流水 ref
            pass
        logger.info("listing create id=%s seller=%s mode=%s", row.id, character.id, mode_n)
        return {
            "message": "已上架",
            "listing": await self._listing_public(row),
            "character": await self._character_public(character),
        }

    async def buy_listing(self, user: User, listing_id: int) -> dict[str, Any]:
        """购买 / 成交易物。"""
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._reject_if_ferry_or_tribulation(character)
        row = await self._session.get(TradeListing, listing_id)
        if row is None or row.status != "open":
            raise AppError(code=40000, message="挂单不存在或已关闭", http_status=400)
        if row.seller_character_id == character.id:
            raise AppError(code=40000, message="不可购买自己的挂单", http_status=400)
        seller = await self._session.get(Character, row.seller_character_id)
        if seller is None:
            raise AppError(code=40000, message="卖家不存在", http_status=400)
        offer = json.loads(row.offer_json or "[]")
        ask = json.loads(row.ask_json or "[]")

        if row.mode == "fixed_price":
            price = int(row.price_spirit_stones)
            fee = listing_fee_amount(price, self._cfg().listing_fee_pct)
            seller_gain = price - fee
            await self._ledger.adjust_spirit_stones(
                character,
                delta=-price,
                reason="listing_buy",
                note_zh="交易行购买",
                ref_type="listing",
                ref_id=str(row.id),
            )
            if seller_gain > 0:
                await self._ledger.adjust_spirit_stones(
                    seller,
                    delta=seller_gain,
                    reason="listing_sell",
                    note_zh="交易行售出",
                    ref_type="listing",
                    ref_id=str(row.id),
                )
            if fee > 0:
                await self._ledger.adjust_spirit_stones(
                    None,
                    delta=fee,
                    reason="recycle_fee",
                    note_zh="回收：交易行手续费",
                    ref_type="listing",
                    ref_id=str(row.id),
                )
        else:
            # 易物：买方交出 ask 物品，卖方已托管 offer
            await self._assert_items_tradable(ask)
            await self._escrow_take(character, ask)
            await self._escrow_give(seller, ask)

        await self._escrow_give(character, offer)
        row.status = "sold"
        row.buyer_character_id = character.id
        row.closed_at = now_utc()
        await self._session.flush()
        return {
            "message": "成交成功",
            "listing": await self._listing_public(row),
            "character": await self._character_public(character),
        }

    async def cancel_listing(self, user: User, listing_id: int) -> dict[str, Any]:
        """撤单并退回托管物。"""
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._session.get(TradeListing, listing_id)
        if row is None or row.status != "open":
            raise AppError(code=40000, message="挂单不存在或已关闭", http_status=400)
        if row.seller_character_id != character.id:
            raise AppError(code=40000, message="仅卖家可撤单", http_status=403)
        offer = json.loads(row.offer_json or "[]")
        await self._escrow_give(character, offer)
        row.status = "cancelled"
        row.closed_at = now_utc()
        await self._session.flush()
        return {
            "message": "已撤单，物品已退回",
            "listing": await self._listing_public(row),
            "character": await self._character_public(character),
        }

    # ----- auctions -----

    async def list_auctions(self, user: User) -> dict[str, Any]:
        """拍卖列表（读时惰性结拍）。"""
        require_trade_enabled()
        await self._gate.require_character(user)
        rows = (
            await self._session.execute(
                select(AuctionLot)
                .where(AuctionLot.status == "open")
                .order_by(AuctionLot.ends_at.asc())
                .limit(100),
            )
        ).scalars().all()
        items = []
        for row in rows:
            await self._lazy_settle_auction(row)
            if row.status == "open":
                items.append(await self._auction_public(row))
        return {"items": items}

    async def create_auction(
        self,
        user: User,
        *,
        offer_items: list[dict[str, Any]],
        start_price: int,
        duration_sec: int | None,
    ) -> dict[str, Any]:
        """上架拍卖。"""
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._reject_if_ferry_or_tribulation(character)
        offer = parse_item_lines(offer_items)
        if not offer:
            raise AppError(code=40000, message="拍品不可为空", http_status=400)
        await self._assert_items_tradable(offer)
        dur = int(duration_sec or self._cfg().auction_duration_sec)
        dur = max(60, dur)
        await self._escrow_take(character, offer)
        now = now_utc()
        row = AuctionLot(
            seller_character_id=character.id,
            offer_json=json.dumps(offer, ensure_ascii=False),
            start_price=int(start_price),
            current_price=int(start_price),
            status="open",
            ends_at=now + timedelta(seconds=dur),
        )
        self._session.add(row)
        await self._session.flush()
        return {
            "message": "拍品已上架",
            "lot": await self._auction_public(row),
            "character": await self._character_public(character),
        }

    async def bid_auction(
        self,
        user: User,
        lot_id: int,
        *,
        amount: int,
    ) -> dict[str, Any]:
        """出价（托管出价灵石；退回前一最高价）。"""
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._reject_if_ferry_or_tribulation(character)
        row = await self._session.get(AuctionLot, lot_id)
        if row is None:
            raise AppError(code=40000, message="拍品不存在", http_status=404)
        await self._lazy_settle_auction(row)
        if row.status != "open":
            raise AppError(code=40000, message="拍品已结束", http_status=400)
        if row.seller_character_id == character.id:
            raise AppError(code=40000, message="不可竞拍自己的拍品", http_status=400)
        min_bid = auction_min_next_bid(
            int(row.current_price),
            self._cfg().auction_min_increment_pct,
        )
        # 无人出价时允许等于起拍价
        if row.current_bidder_id is None:
            min_bid = int(row.start_price)
        if int(amount) < min_bid:
            raise AppError(
                code=40000,
                message=f"出价须不低于 {min_bid} 灵石",
                http_status=400,
            )
        # 退回上一出价者托管
        if row.current_bidder_id is not None:
            prev = await self._session.get(Character, row.current_bidder_id)
            if prev is not None:
                await self._ledger.adjust_spirit_stones(
                    prev,
                    delta=int(row.current_price),
                    reason="auction_bid_refund",
                    note_zh="拍卖被超越退回",
                    ref_type="auction",
                    ref_id=str(row.id),
                )
        await self._ledger.adjust_spirit_stones(
            character,
            delta=-int(amount),
            reason="auction_bid_hold",
            note_zh="拍卖出价托管",
            ref_type="auction",
            ref_id=str(row.id),
        )
        row.current_price = int(amount)
        row.current_bidder_id = character.id
        self._session.add(
            AuctionBid(
                lot_id=row.id,
                bidder_character_id=character.id,
                amount=int(amount),
            ),
        )
        await self._session.flush()
        return {
            "message": f"出价成功：{amount} 灵石",
            "lot": await self._auction_public(row),
            "character": await self._character_public(character),
        }

    async def _lazy_settle_auction(self, row: AuctionLot) -> None:
        """到期结拍。"""
        if row.status != "open":
            return
        if now_utc() < ensure_aware_utc(row.ends_at):
            return
        offer = json.loads(row.offer_json or "[]")
        seller = await self._session.get(Character, row.seller_character_id)
        if row.current_bidder_id is None:
            # 流拍：按配置退回卖家（L3 默认系统邮件）
            if seller is not None:
                refund_mode = str(self._cfg().auction_unsold_refund or "mail").lower()
                if refund_mode == "mail":
                    from app.services.mail_service import MailService

                    await MailService(self._session).send_system(
                        to_character_id=seller.id,
                        subject_zh="拍卖流拍退回",
                        body_zh=f"你的拍卖（#{row.id}）无人出价，拍品已退回邮箱，请领取附件。",
                        reason="auction_unsold",
                        items=list(offer),
                    )
                else:
                    await self._escrow_give(seller, offer)
            row.status = "unsold"
            row.closed_at = now_utc()
            await self._session.flush()
            return
        winner = await self._session.get(Character, row.current_bidder_id)
        price = int(row.current_price)
        fee = listing_fee_amount(price, self._cfg().auction_fee_pct)
        seller_gain = price - fee
        if seller is not None and seller_gain > 0:
            await self._ledger.adjust_spirit_stones(
                seller,
                delta=seller_gain,
                reason="auction_sold",
                note_zh="拍卖成交",
                ref_type="auction",
                ref_id=str(row.id),
            )
        if fee > 0:
            await self._ledger.adjust_spirit_stones(
                None,
                delta=fee,
                reason="recycle_fee",
                note_zh="回收：拍卖手续费",
                ref_type="auction",
                ref_id=str(row.id),
            )
        if winner is not None:
            await self._escrow_give(winner, offer)
        row.status = "sold"
        row.closed_at = now_utc()
        await self._session.flush()

    # ----- face trade -----

    _FACE_ACTIVE_STATUSES: tuple[str, ...] = (
        "pending_invite",
        "browsing",
        "locking",
        "confirming",
    )

    async def face_invite(
        self,
        user: User,
        *,
        peer_character_id: int | None,
        peer_name: str | None,
    ) -> dict[str, Any]:
        """
        Invite a peer to face trade (status ``pending_invite``).

        Requires friendship and both-online checks when configured.
        Does not escrow anything.

        Args:
            user: Authenticated initiator.
            peer_character_id: Optional peer character primary key.
            peer_name: Optional peer display name (道号).

        Returns:
            Invite message and public session payload.

        Raises:
            AppError: Self-trade, not friends, offline, or active session conflict.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        self._reject_if_ferry_or_tribulation(character)
        peer = await self._resolve_peer(peer_character_id, peer_name)
        if peer.id == character.id:
            raise AppError(code=40000, message="不可与自己面交", http_status=400)
        cfg = self._cfg()
        if bool(cfg.face_require_friend):
            friends = await FriendService(self._session).are_friends(character.id, peer.id)
            if not friends:
                raise AppError(
                    code=40000,
                    message="仅可与道友发起当面交易",
                    http_status=400,
                )
        if bool(cfg.face_require_online):
            if not self._face_is_online(character.id):
                raise AppError(code=40000, message="你当前不在线，无法发起面交", http_status=400)
            if not self._face_is_online(peer.id):
                raise AppError(
                    code=40000,
                    message=f"「{peer.name}」不在线，无法发起面交",
                    http_status=400,
                )
        # 互斥：任一方已有进行中面交
        await self._ensure_no_active_face(character.id)
        await self._ensure_no_active_face(peer.id)
        timeout = int(
            getattr(get_settings(), "face_trade_timeout_sec", 0)
            or cfg.face_timeout_sec
            or 120,
        )
        empty_offer = json.dumps({"items": [], "spirit_stones": 0}, ensure_ascii=False)
        row = FaceTradeSession(
            initiator_id=character.id,
            peer_id=peer.id,
            status="pending_invite",
            version=1,
            initiator_offer_json=empty_offer,
            peer_offer_json=empty_offer,
            initiator_locked=0,
            peer_locked=0,
            expires_at=now_utc() + timedelta(seconds=timeout),
        )
        self._session.add(row)
        await self._session.flush()
        return {
            "message": f"已向「{peer.name}」发起面交",
            "session": await self._face_public(row, character.id),
        }

    async def face_accept(self, user: User, session_id: int) -> dict[str, Any]:
        """
        Peer accepts a pending invite; session enters ``browsing``.

        Args:
            user: Authenticated peer user.
            session_id: Face trade session id.

        Returns:
            Accept message and public session.

        Raises:
            AppError: Not peer, wrong status, or ended session.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        if row.status != "pending_invite":
            raise AppError(code=40112, message="面交不在待接受状态", http_status=400)
        if character.id != row.peer_id:
            raise AppError(code=40000, message="仅受邀方可接受面交", http_status=403)
        row.status = "browsing"
        await self._session.flush()
        return {
            "message": "已接受面交，可开始挑选报价",
            "session": await self._face_public(row, character.id),
        }

    async def face_reject(self, user: User, session_id: int) -> dict[str, Any]:
        """
        Peer rejects a pending invite; session becomes ``cancelled``.

        No escrow exists at invite stage, so nothing is refunded.

        Args:
            user: Authenticated peer user.
            session_id: Face trade session id.

        Returns:
            Reject message and public session.

        Raises:
            AppError: Not peer or wrong status.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        if row.status != "pending_invite":
            raise AppError(code=40112, message="面交不在待接受状态", http_status=400)
        if character.id != row.peer_id:
            raise AppError(code=40000, message="仅受邀方可拒绝面交", http_status=403)
        row.status = "cancelled"
        row.closed_at = now_utc()
        await self._session.flush()
        return {
            "message": "已拒绝面交",
            "session": await self._face_public(row, character.id),
        }

    async def face_get(self, user: User, session_id: int) -> dict[str, Any]:
        """
        Fetch face-trade session (lazy timeout).

        Args:
            user: Authenticated participant.
            session_id: Session primary key.

        Returns:
            Public session dict under ``session``.
        """
        require_trade_enabled()
        character = await self._gate.require_character(user)
        row = await self._session.get(FaceTradeSession, session_id)
        if row is None:
            raise AppError(code=40000, message="面交会话不存在", http_status=404)
        if character.id not in (row.initiator_id, row.peer_id):
            raise AppError(code=40000, message="无权查看该面交", http_status=403)
        await self._lazy_expire_face(row)
        return {"session": await self._face_public(row, character.id)}

    async def face_set_offer(
        self,
        user: User,
        session_id: int,
        *,
        items: list[dict[str, Any]],
        spirit_stones: int,
        version: int,
    ) -> dict[str, Any]:
        """
        Write draft offer JSON only (no escrow).

        Allowed in ``browsing``, or ``locking`` while the caller's side is not
        yet locked. Clears both lock flags (refunding any already-escrowed
        side), both confirms, bumps version, and returns to ``browsing``.

        Args:
            user: Authenticated participant.
            session_id: Session id.
            items: Draft item lines.
            spirit_stones: Draft spirit stones (not deducted yet).
            version: Client-held optimistic version.

        Returns:
            Updated session (and character snapshot unchanged for stones/items).

        Raises:
            AppError: Wrong status, already locked on own side, or version mismatch.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        is_initiator = character.id == row.initiator_id
        my_locked = int(row.initiator_locked if is_initiator else row.peer_locked)
        if row.status == "browsing":
            pass
        elif row.status == "locking" and my_locked == 0:
            # 对方已锁、我方未锁：改草稿会清空双方锁定并退还对方托管
            pass
        else:
            raise AppError(code=40112, message="面交状态不可改报价", http_status=400)
        if my_locked == 1:
            raise AppError(
                code=40112,
                message="已锁定，不可再改报价（请取消后重开）",
                http_status=400,
            )
        if int(version) != int(row.version):
            raise AppError(code=40112, message="会话版本过期，请刷新", http_status=409)
        lines = parse_item_lines(items)
        if len(lines) > int(self._cfg().face_max_item_lines):
            raise AppError(code=40000, message="物品行数超限", http_status=400)
        await self._assert_items_tradable(lines)
        # 若任一侧已托管（锁定），改草稿前先退还托管并清除锁定标志
        await self._face_refund_locked_sides(row)
        row.initiator_locked = 0
        row.peer_locked = 0
        payload = {"items": lines, "spirit_stones": int(spirit_stones)}
        if is_initiator:
            row.initiator_offer_json = json.dumps(payload, ensure_ascii=False)
        else:
            row.peer_offer_json = json.dumps(payload, ensure_ascii=False)
        row.initiator_confirmed = 0
        row.peer_confirmed = 0
        row.status = "browsing"
        row.version = int(row.version) + 1
        await self._session.flush()
        await self._session.refresh(character)
        return {
            "message": "草稿报价已更新（尚未托管）",
            "session": await self._face_public(row, character.id),
            "character": await self._character_public(character),
        }

    async def face_lock(
        self,
        user: User,
        session_id: int,
        *,
        version: int,
    ) -> dict[str, Any]:
        """
        Escrow the caller's current draft offer and set their locked flag.

        Each side may lock at most once until cancel/timeout. When both sides
        are locked, status becomes ``locking`` and offers are immutable.

        Args:
            user: Authenticated participant.
            session_id: Session id.
            version: Client-held optimistic version.

        Returns:
            Lock message, session, and refreshed character (after escrow).

        Raises:
            AppError: Wrong status, already locked, empty/invalid offer, or
                insufficient inventory/stones.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        if row.status not in ("browsing", "locking"):
            raise AppError(code=40112, message="面交状态不可锁定", http_status=400)
        if int(version) != int(row.version):
            raise AppError(code=40112, message="会话版本过期，请刷新", http_status=409)
        is_initiator = character.id == row.initiator_id
        my_locked = int(row.initiator_locked if is_initiator else row.peer_locked)
        if my_locked == 1:
            raise AppError(code=40112, message="本侧已锁定，不可重复锁定", http_status=400)
        offer = self._face_offer_dict(row, character.id)
        lines = offer.get("items") or []
        stones = int(offer.get("spirit_stones") or 0)
        await self._assert_items_tradable(lines)
        # 先校验灵石，再托管，避免「物品已扣、灵石失败」半状态
        if stones > 0 and int(character.spirit_stones) < stones:
            raise AppError(
                code=40000,
                message=f"灵石不足：需 {stones}",
                http_status=400,
            )
        await self._face_apply_hold(character, offer, ref_id=str(row.id))
        if is_initiator:
            row.initiator_locked = 1
        else:
            row.peer_locked = 1
        row.initiator_confirmed = 0
        row.peer_confirmed = 0
        if int(row.initiator_locked) == 1 and int(row.peer_locked) == 1:
            row.status = "locking"
        else:
            row.status = "browsing"
        row.version = int(row.version) + 1
        await self._session.flush()
        await self._session.refresh(character)
        both = int(row.initiator_locked) == 1 and int(row.peer_locked) == 1
        return {
            "message": "双方已锁定，可确认成交" if both else "已锁定本侧报价（已托管）",
            "session": await self._face_public(row, character.id),
            "character": await self._character_public(character),
        }

    async def face_confirm(
        self,
        user: User,
        session_id: int,
        *,
        version: int,
    ) -> dict[str, Any]:
        """
        Confirm face trade after both sides have locked.

        Both confirms atomically commit the escrowed exchange.

        Args:
            user: Authenticated participant.
            session_id: Session id.
            version: Client-held optimistic version.

        Returns:
            Confirm or commit payload with session (and character on commit).

        Raises:
            AppError: Not both locked, wrong status, or version mismatch.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        if row.status not in ("locking", "confirming"):
            raise AppError(code=40112, message="面交状态不可确认", http_status=400)
        if int(row.initiator_locked) != 1 or int(row.peer_locked) != 1:
            raise AppError(code=40112, message="双方锁定后方可确认", http_status=400)
        if int(version) != int(row.version):
            raise AppError(code=40112, message="会话版本过期，请刷新", http_status=409)
        if character.id == row.initiator_id:
            row.initiator_confirmed = 1
        else:
            row.peer_confirmed = 1
        row.status = "confirming"
        await self._session.flush()
        if int(row.initiator_confirmed) == 1 and int(row.peer_confirmed) == 1:
            await self._face_commit(row)
            await self._session.refresh(character)
            return {
                "message": "面交成交",
                "session": await self._face_public(row, character.id),
                "character": await self._character_public(character),
            }
        return {
            "message": "已确认，等待对方",
            "session": await self._face_public(row, character.id),
        }

    async def face_cancel(self, user: User, session_id: int) -> dict[str, Any]:
        """
        Cancel face trade and refund any escrowed (locked) offers.

        Args:
            user: Authenticated participant.
            session_id: Session id.

        Returns:
            Cancel message, session, and character after refunds.
        """
        require_trade_enabled()
        character, _ = await self._gate.prepare_for_play(user, settle=True)
        row = await self._require_face_participant(character, session_id)
        await self._lazy_expire_face(row)
        if row.status in ("committed", "cancelled", "expired"):
            raise AppError(code=40112, message="面交已结束", http_status=400)
        await self._face_unlock_both(row)
        row.status = "cancelled"
        row.closed_at = now_utc()
        await self._session.flush()
        await self._session.refresh(character)
        return {
            "message": "面交已取消",
            "session": await self._face_public(row, character.id),
            "character": await self._character_public(character),
        }

    # ----- helpers -----

    def _reject_if_ferry_or_tribulation(self, character: Character) -> None:
        if character.status in ("awaiting_ferry", "tribulation", "reincarnating"):
            raise AppError(
                code=40000,
                message="当前状态不可交易（待引渡/渡劫/轮回中）",
                http_status=400,
            )

    async def _assert_items_tradable(self, lines: list[dict[str, Any]]) -> None:
        inv = get_game_config().inventory
        for line in lines:
            defn = inv.items.get(str(line["item_id"]))
            if defn is None:
                raise AppError(
                    code=40000,
                    message=f"未知物品：{line['item_id']}",
                    http_status=400,
                )
            ok, reason = item_may_trade(tradable=bool(defn.tradable), bound=bool(defn.bound))
            if not ok:
                raise AppError(
                    code=40111,
                    message=f"「{defn.name}」{reason}",
                    http_status=400,
                )

    async def _escrow_take(self, character: Character, lines: list[dict[str, Any]]) -> None:
        """从背包扣入托管。"""
        counts = await self._inv.material_counts(character.id)
        for line in lines:
            item_id = str(line["item_id"])
            need = int(line["quantity"])
            if int(counts.get(item_id, 0)) < need:
                defn = get_game_config().inventory.items.get(item_id)
                name = defn.name if defn else item_id
                raise AppError(
                    code=40055,
                    message=f"物品不足：{name} ×{need}",
                    http_status=400,
                )
        for line in lines:
            await self._inv._remove_item_id(
                character.id,
                str(line["item_id"]),
                int(line["quantity"]),
            )

    async def _escrow_give(self, character: Character, lines: list[dict[str, Any]]) -> None:
        """托管发还/转入背包。"""
        inv = get_game_config().inventory
        for line in lines:
            item_id = str(line["item_id"])
            defn = inv.items.get(item_id)
            item_type = defn.item_type if defn else "material"
            await self._inv.add_item(
                character.id,
                item_type=item_type,
                item_id=item_id,
                quantity=int(line["quantity"]),
                bag_kind="normal",
            )

    async def _listing_public(self, row: TradeListing) -> dict[str, Any]:
        seller = await self._session.get(Character, row.seller_character_id)
        return {
            "id": row.id,
            "mode": row.mode,
            "mode_label_zh": "一口价" if row.mode == "fixed_price" else "以物易物",
            "seller_character_id": row.seller_character_id,
            "seller_name": seller.name if seller else str(row.seller_character_id),
            "offer_items": json.loads(row.offer_json or "[]"),
            "price_spirit_stones": int(row.price_spirit_stones),
            "ask_items": json.loads(row.ask_json or "[]"),
            "status": row.status,
            "fee_paid": int(row.fee_paid),
        }

    async def _auction_public(self, row: AuctionLot) -> dict[str, Any]:
        seller = await self._session.get(Character, row.seller_character_id)
        return {
            "id": row.id,
            "seller_character_id": row.seller_character_id,
            "seller_name": seller.name if seller else str(row.seller_character_id),
            "offer_items": json.loads(row.offer_json or "[]"),
            "start_price": int(row.start_price),
            "current_price": int(row.current_price),
            "current_bidder_id": row.current_bidder_id,
            "status": row.status,
            "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        }

    async def _face_public(self, row: FaceTradeSession, viewer_id: int) -> dict[str, Any]:
        """
        Build public face-trade session payload for a viewer.

        Args:
            row: Session ORM row.
            viewer_id: Viewing character id (sets ``you_are`` / peer_online).

        Returns:
            JSON-serializable session dict including lock flags and offers.
        """
        init = await self._session.get(Character, row.initiator_id)
        peer = await self._session.get(Character, row.peer_id)
        peer_character_id = (
            row.peer_id if viewer_id == row.initiator_id else row.initiator_id
        )
        return {
            "id": row.id,
            "status": row.status,
            "status_label_zh": _face_status_zh(row.status),
            "version": int(row.version),
            "initiator_id": row.initiator_id,
            "initiator_name": init.name if init else str(row.initiator_id),
            "peer_id": row.peer_id,
            "peer_name": peer.name if peer else str(row.peer_id),
            "initiator_offer": json.loads(row.initiator_offer_json or "{}"),
            "peer_offer": json.loads(row.peer_offer_json or "{}"),
            "initiator_locked": bool(int(getattr(row, "initiator_locked", 0) or 0)),
            "peer_locked": bool(int(getattr(row, "peer_locked", 0) or 0)),
            "initiator_confirmed": bool(row.initiator_confirmed),
            "peer_confirmed": bool(row.peer_confirmed),
            "you_are": "initiator" if viewer_id == row.initiator_id else "peer",
            "peer_online": self._face_is_online(peer_character_id),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    def _face_offer_dict(self, row: FaceTradeSession, character_id: int) -> dict[str, Any]:
        raw = (
            row.initiator_offer_json
            if character_id == row.initiator_id
            else row.peer_offer_json
        )
        data = json.loads(raw or "{}")
        return {
            "items": parse_item_lines(data.get("items") or []),
            "spirit_stones": int(data.get("spirit_stones") or 0),
        }

    async def _face_refund_offer(
        self,
        character: Character,
        offer: dict[str, Any],
    ) -> None:
        """Return escrowed items/stones from a locked offer to the character."""
        await self._escrow_give(character, offer.get("items") or [])
        stones = int(offer.get("spirit_stones") or 0)
        if stones > 0:
            await self._ledger.adjust_spirit_stones(
                character,
                delta=stones,
                reason="face_unlock",
                note_zh="面交退回托管灵石",
                ref_type="face",
            )

    async def _face_apply_hold(
        self,
        character: Character,
        offer: dict[str, Any],
        *,
        ref_id: str | None = None,
    ) -> None:
        """
        Escrow items and spirit stones for a face-trade lock.

        Args:
            character: Owner to debit.
            offer: ``{items, spirit_stones}`` from draft JSON.
            ref_id: Optional ledger ``ref_id`` (session id).

        Raises:
            AppError: Insufficient inventory or spirit stones.
        """
        items = offer.get("items") or []
        if items:
            await self._escrow_take(character, items)
        stones = int(offer.get("spirit_stones") or 0)
        if stones > 0:
            await self._ledger.adjust_spirit_stones(
                character,
                delta=-stones,
                reason="face_hold",
                note_zh="面交灵石托管",
                ref_type="face",
                ref_id=ref_id,
            )

    async def _face_refund_locked_sides(self, row: FaceTradeSession) -> None:
        """
        Refund escrow only for sides that have already locked.

        Draft-only offers must not be refunded (items were never taken).

        Args:
            row: Face trade session.
        """
        if int(getattr(row, "initiator_locked", 0) or 0) == 1:
            init = await self._session.get(Character, row.initiator_id)
            if init is not None:
                await self._face_refund_offer(init, self._face_offer_dict(row, init.id))
        if int(getattr(row, "peer_locked", 0) or 0) == 1:
            peer = await self._session.get(Character, row.peer_id)
            if peer is not None:
                await self._face_refund_offer(peer, self._face_offer_dict(row, peer.id))

    async def _face_unlock_both(self, row: FaceTradeSession) -> None:
        """
        Cancel/timeout cleanup: refund locked escrows and clear offers/locks.

        Args:
            row: Session to unlock.
        """
        await self._face_refund_locked_sides(row)
        empty = json.dumps({"items": [], "spirit_stones": 0}, ensure_ascii=False)
        row.initiator_offer_json = empty
        row.peer_offer_json = empty
        row.initiator_locked = 0
        row.peer_locked = 0
        row.initiator_confirmed = 0
        row.peer_confirmed = 0

    async def _face_commit(self, row: FaceTradeSession) -> None:
        """
        Atomically exchange already-escrowed offers and mark committed.

        Args:
            row: Session with both sides locked and confirmed.

        Raises:
            AppError: Missing participant characters.
        """
        init = await self._session.get(Character, row.initiator_id)
        peer = await self._session.get(Character, row.peer_id)
        if init is None or peer is None:
            raise AppError(code=40112, message="面交参与者缺失", http_status=400)
        a = self._face_offer_dict(row, init.id)
        b = self._face_offer_dict(row, peer.id)
        # 托管已在双方账户外：直接把对方物品/灵石发给自己
        await self._escrow_give(peer, a.get("items") or [])
        await self._escrow_give(init, b.get("items") or [])
        if int(a.get("spirit_stones") or 0) > 0:
            await self._ledger.adjust_spirit_stones(
                peer,
                delta=int(a["spirit_stones"]),
                reason="face_receive",
                note_zh="面交收到灵石",
                ref_type="face",
                ref_id=str(row.id),
            )
        if int(b.get("spirit_stones") or 0) > 0:
            await self._ledger.adjust_spirit_stones(
                init,
                delta=int(b["spirit_stones"]),
                reason="face_receive",
                note_zh="面交收到灵石",
                ref_type="face",
                ref_id=str(row.id),
            )
        empty = json.dumps({"items": [], "spirit_stones": 0}, ensure_ascii=False)
        row.initiator_offer_json = empty
        row.peer_offer_json = empty
        row.initiator_locked = 0
        row.peer_locked = 0
        row.status = "committed"
        row.closed_at = now_utc()
        await self._session.flush()
        logger.info("face commit session=%s", row.id)

    async def _require_face_participant(
        self,
        character: Character,
        session_id: int,
    ) -> FaceTradeSession:
        row = await self._session.get(FaceTradeSession, session_id)
        if row is None:
            raise AppError(code=40000, message="面交会话不存在", http_status=404)
        if character.id not in (row.initiator_id, row.peer_id):
            raise AppError(code=40000, message="无权操作该面交", http_status=403)
        return row

    async def _ensure_no_active_face(self, character_id: int) -> None:
        active = (
            await self._session.execute(
                select(FaceTradeSession).where(
                    or_(
                        FaceTradeSession.initiator_id == character_id,
                        FaceTradeSession.peer_id == character_id,
                    ),
                    FaceTradeSession.status.in_(self._FACE_ACTIVE_STATUSES),
                ),
            )
        ).scalars().all()
        for row in active:
            await self._lazy_expire_face(row)
        still = [r for r in active if r.status in self._FACE_ACTIVE_STATUSES]
        if still:
            raise AppError(code=40112, message="已有进行中的面交会话", http_status=400)

    async def _lazy_expire_face(self, row: FaceTradeSession) -> None:
        if row.status in ("committed", "cancelled", "expired"):
            return
        if now_utc() < ensure_aware_utc(row.expires_at):
            return
        await self._face_unlock_both(row)
        row.status = "expired"
        row.closed_at = now_utc()
        await self._session.flush()

    def _face_is_online(self, character_id: int) -> bool:
        """
        Whether a character counts as online for face trade.

        Args:
            character_id: Character primary key.

        Returns:
            True if online (or assumed online in development).
        """
        from app.services.presence_service import PresencePurpose, get_presence

        return get_presence().is_online_for(PresencePurpose.FACE, int(character_id))

    async def _resolve_peer(
        self,
        peer_character_id: int | None,
        peer_name: str | None,
    ) -> Character:
        if peer_character_id is not None:
            ch = await self._session.get(Character, int(peer_character_id))
            if ch is None:
                raise AppError(code=40000, message="对方角色不存在", http_status=404)
            return ch
        name = (peer_name or "").strip()
        if not name:
            raise AppError(code=40000, message="请提供对方角色 id 或道号", http_status=400)
        ch = (
            await self._session.execute(select(Character).where(Character.name == name))
        ).scalar_one_or_none()
        if ch is None:
            raise AppError(code=40000, message=f"找不到道号「{name}」", http_status=404)
        return ch

    async def _character_public(self, character: Character) -> dict[str, Any]:
        from app.services.character_service import CharacterService

        await self._session.refresh(character)
        return (
            await CharacterService(self._session).enrich_public(character)
        ).model_dump(mode="json")


def _face_status_zh(status: str) -> str:
    return {
        "pending_invite": "待接受",
        "browsing": "挑选报价中",
        "locking": "双方已锁定",
        "confirming": "确认中",
        "committed": "已成交",
        "cancelled": "已取消",
        "expired": "已超时",
        # 兼容旧状态文案
        "invited": "已邀约",
    }.get(status, status)
