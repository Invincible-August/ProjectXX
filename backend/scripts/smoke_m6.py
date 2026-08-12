"""
M6 冒烟：开道 → 空位就任 → 世界事件骨架房间 → 赛会报名/立刻开赛。

用法（backend 目录、已激活 venv）:
  python scripts/smoke_m6.py

说明：写入本地 ``xiuxian.db``；赛会先经 Admin ``reopen`` 保证处于报名期。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# 保证可 import app
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
) -> dict[str, str]:
    """注册（可忽略已存在）并登录，返回 Authorization headers。"""
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
            json={"name": name},
        )
        r.raise_for_status()
    return headers


async def _admin_reopen_contest(client: AsyncClient) -> None:
    """运营 reopen，确保本场回到报名期（冒烟可重复跑）。"""
    login = await client.post(
        "/admin/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    login.raise_for_status()
    assert login.json()["code"] == 0, login.json()
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    reopen = await client.post(
        "/admin/ops/dao-contests/reopen",
        headers=headers,
        json={"note": "smoke_m6"},
    )
    print(
        "admin reopen:",
        reopen.status_code,
        reopen.json().get("code"),
        reopen.json().get("message"),
    )


async def main() -> None:
    """跑通 M6 出口最小路径（含赛会与世界事件骨架）。"""
    settings = get_settings()
    settings.world_events_enabled = True
    settings.dao_system_enabled = True
    settings.dao_lord_enabled = True
    settings.gm_enabled = True

    suffix = uuid.uuid4().hex[:8]
    password = "SmokePass123"

    # ASGITransport 默认不跑 lifespan；须进入上下文才会 create_all
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _admin_reopen_contest(client)

            headers_a = await _register_and_login(
                client,
                email=f"smoke_m6_a_{suffix}@test.local",
                password=password,
                name=f"冒烟道甲{suffix[:4]}",
            )

            gm = await client.post(
                "/api/v1/gm/character/set",
                headers=headers_a,
                json={
                    "force_true_immortal": True,
                    "lock_fate_dao": "dao_flame",
                    "set_dao_level": 2,
                    "set_dao_lord": "dao_flame",
                    "open_dao_challenge_window": True,
                    "clear_dao_challenge_cooldown": True,
                },
            )
            gm.raise_for_status()
            assert gm.json()["code"] == 0, gm.json()

            catalog = await client.get("/api/v1/dao/catalog", headers=headers_a)
            catalog.raise_for_status()
            print("catalog total:", catalog.json()["data"]["total"])

            board = await client.get("/api/v1/dao-lord/board", headers=headers_a)
            board.raise_for_status()
            board_data = board.json()["data"]
            seat = next(
                (s for s in board_data["seats"] if s["dao_id"] == "dao_flame"),
                None,
            )
            print("flame seat:", seat)
            assert seat and seat.get("is_self_lord"), seat

            # --- 世界事件骨架：房间 id ---
            events = await client.get("/api/v1/world-events/current", headers=headers_a)
            events.raise_for_status()
            ev_body = events.json()["data"]
            assert ev_body.get("enabled") is True, ev_body
            boss = next(
                (e for e in ev_body.get("events") or [] if e.get("id") == "world_boss_sample"),
                None,
            )
            assert boss and boss.get("room_id") == "world_event:world_boss_sample", boss
            reg = await client.post(
                "/api/v1/world-events/world_boss_sample/register",
                headers=headers_a,
            )
            reg.raise_for_status()
            assert reg.json()["data"]["room_id"] == "world_event:world_boss_sample"
            print("world-event room:", reg.json()["data"]["room_id"])

            # --- 赛会：挑战者报名 → GM 立刻开赛 ---
            headers_b = await _register_and_login(
                client,
                email=f"smoke_m6_b_{suffix}@test.local",
                password=password,
                name=f"冒烟道乙{suffix[:4]}",
            )
            gm_b = await client.post(
                "/api/v1/gm/character/set",
                headers=headers_b,
                json={
                    "force_true_immortal": True,
                    "lock_fate_dao": "dao_flame",
                    "set_dao_level": 2,
                    "clear_dao_challenge_cooldown": True,
                },
            )
            gm_b.raise_for_status()

            contest_me = await client.get(
                "/api/v1/dao-lord/contests/current",
                headers=headers_b,
            )
            contest_me.raise_for_status()
            print(
                "contest before:",
                contest_me.json()["data"].get("contest", {}).get("status"),
            )

            register = await client.post(
                "/api/v1/dao-lord/contests/current/register",
                headers=headers_b,
            )
            if register.status_code >= 400:
                print("register failed:", register.json())
            register.raise_for_status()
            assert register.json()["code"] == 0, register.json()
            assert register.json()["data"]["me"]["registered"] is True
            print("registered challenger")

            force = await client.post(
                "/api/v1/gm/character/set",
                headers=headers_a,
                json={"open_dao_contest_now": True},
            )
            force.raise_for_status()
            assert force.json()["code"] == 0, force.json()

            after = await client.get(
                "/api/v1/dao-lord/contests/current",
                headers=headers_b,
            )
            after.raise_for_status()
            status = after.json()["data"]["contest"]["status"]
            print("contest after force-start:", status)
            assert status in ("rsvp", "arena", "settled", "cancelled", "running"), status
            assert after.json()["data"]["contest"]["can_register"] is False

            bracket = await client.get(
                "/api/v1/dao-lord/contests/current/bracket",
                headers=headers_b,
                params={"dao_id": "dao_flame"},
            )
            bracket.raise_for_status()
            print("bracket ok:", bracket.json()["code"] == 0)

    print("smoke_m6 done")


if __name__ == "__main__":
    asyncio.run(main())
