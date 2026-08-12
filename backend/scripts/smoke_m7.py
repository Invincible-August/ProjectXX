"""
M7 冒烟：社交最小闭环 + 双修双增 + 沙盒天道点开通会员帽。

用法（backend 目录、已激活 venv）:
  python scripts/smoke_m7.py

说明：写入本地 ``xiuxian.db``；可重复跑（邮箱带随机后缀）。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    password: str,
    name: str,
    gender: str,
) -> dict[str, str]:
    """注册并创角（含性别）。"""
    await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = await client.post(
        "/api/v1/auth/login",
        json={"account": email, "password": password},
    )
    login.raise_for_status()
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/characters/me", headers=headers)
    if me.status_code != 200 or not (me.json().get("data") or {}).get("id"):
        r = await client.post(
            "/api/v1/characters",
            headers=headers,
            json={"name": name, "gender": gender},
        )
        r.raise_for_status()
        assert r.json().get("code") == 0, r.json()
    return headers


async def main() -> None:
    """跑通 M7 出口关键路径。"""
    settings = get_settings()
    settings.gm_enabled = True
    settings.friends_system_enabled = True
    settings.trade_system_enabled = True
    settings.chat_system_enabled = True
    settings.heritage_system_enabled = True
    settings.mentor_system_enabled = True
    settings.dual_cultivation_enabled = True
    settings.commerce_system_enabled = True
    settings.commerce_sandbox_enabled = True

    suffix = uuid.uuid4().hex[:8]
    password = "SmokePass123"

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers_a = await _register_and_login(
                client,
                email=f"smoke_m7_a_{suffix}@test.local",
                password=password,
                name=f"冒烟甲{suffix[:4]}",
                gender="male",
            )
            headers_b = await _register_and_login(
                client,
                email=f"smoke_m7_b_{suffix}@test.local",
                password=password,
                name=f"冒烟乙{suffix[:4]}",
                gender="female",
            )

            # 灌灵石
            for headers in (headers_a, headers_b):
                gm = await client.post(
                    "/api/v1/gm/character/set",
                    headers=headers,
                    json={"spirit_stones": 50_000, "cultivation_points": 500},
                )
                assert gm.json().get("code") == 0, gm.json()

            # 道友
            apply = await client.post(
                "/api/v1/friends",
                headers=headers_a,
                json={"target_name": f"冒烟乙{suffix[:4]}"},
            )
            assert apply.json().get("code") == 0, apply.json()
            friends_b = await client.get("/api/v1/friends", headers=headers_b)
            incoming = (friends_b.json().get("data") or {}).get("incoming") or []
            assert incoming, friends_b.json()
            fid = incoming[0]["friendship_id"]
            accept = await client.post(
                f"/api/v1/friends/{fid}/accept",
                headers=headers_b,
            )
            assert accept.json().get("code") == 0, accept.json()
            print("friends: ok")

            # 世界频道互发
            send_a = await client.post(
                "/api/v1/chat/send",
                headers=headers_a,
                json={"channel_type": "world", "body_zh": "冒烟甲报到"},
            )
            assert send_a.json().get("code") == 0, send_a.json()
            send_b = await client.post(
                "/api/v1/chat/send",
                headers=headers_b,
                json={"channel_type": "world", "body_zh": "冒烟乙报到"},
            )
            assert send_b.json().get("code") == 0, send_b.json()
            print("chat world: ok")

            # 传承发/抢
            heritage = await client.post(
                "/api/v1/heritage",
                headers=headers_a,
                json={
                    "channel_ref": "world",
                    "mode": "fixed",
                    "spirit_stones": 20,
                    "share_count": 2,
                },
            )
            assert heritage.json().get("code") == 0, heritage.json()
            hid = heritage.json()["data"]["packet"]["id"]
            claim = await client.post(
                f"/api/v1/heritage/{hid}/claim",
                headers=headers_b,
            )
            assert claim.json().get("code") == 0, claim.json()
            print("heritage: ok")

            # 双修双增一局
            invite = await client.post(
                "/api/v1/dual/invite",
                headers=headers_a,
                json={
                    "technique_id": "twin_moon_mutual",
                    "target_name": f"冒烟乙{suffix[:4]}",
                    "dice_seed": 42,
                },
            )
            assert invite.json().get("code") == 0, invite.json()
            sid = invite.json()["data"]["session"]["session_id"]
            confirm = await client.post(
                f"/api/v1/dual/{sid}/confirm",
                headers=headers_b,
            )
            assert confirm.json().get("code") == 0, confirm.json()
            roll = await client.post(
                f"/api/v1/dual/{sid}/roll",
                headers=headers_a,
                json={"dice_seed": 42},
            )
            assert roll.json().get("code") == 0, roll.json()
            settle = await client.post(
                f"/api/v1/dual/{sid}/settle",
                headers=headers_a,
            )
            assert settle.json().get("code") == 0, settle.json()
            print("dual mutual: ok")

            # 沙盒天道点 → 会员帽
            grant = await client.post(
                "/api/v1/commerce/sandbox/grant-tiandao",
                headers=headers_a,
                json={"amount": 500},
            )
            assert grant.json().get("code") == 0, grant.json()
            mem = await client.post(
                "/api/v1/commerce/membership",
                headers=headers_a,
                json={"tier": "tier1"},
            )
            assert mem.json().get("code") == 0, mem.json()
            assert mem.json()["data"]["membership"]["idle_cap_hours"] == 18
            shop = await client.get("/api/v1/commerce/shop", headers=headers_a)
            assert shop.json().get("code") == 0, shop.json()
            assert "本命" in (shop.json()["data"].get("boundary_zh") or "")
            print("commerce membership: ok")

            print("smoke_m7 PASSED")


if __name__ == "__main__":
    asyncio.run(main())
