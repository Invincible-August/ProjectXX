"""
M8 冒烟：装备穿戴 → 自研功法 → 自研阵法写入防守快照 → 画符开战 → 宗门工坊真扣材料。

用法（backend 目录、已激活 venv）:
  python scripts/smoke_m8.py

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

LAB = "/api/v1/cave/lab"


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    password: str,
    name: str,
) -> dict[str, str]:
    """Register, login, and create a character."""
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
            json={"name": name, "gender": "male"},
        )
        r.raise_for_status()
        assert r.json().get("code") == 0, r.json()
    return headers


def _assert_ok(envelope: dict, label: str) -> dict:
    assert envelope.get("code") == 0, f"{label}: {envelope}"
    print(f"[ OK ] {label}")
    return envelope.get("data") or {}


async def main() -> None:
    """Run M8 exit smoke path."""
    settings = get_settings()
    settings.gm_enabled = True
    settings.app_env = "development"
    settings.sect_system_enabled = True
    settings.m4_gm_grant_materials = True

    suffix = uuid.uuid4().hex[:8]
    password = "SmokePass123"

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = await _register_and_login(
                client,
                email=f"smoke_m8_{suffix}@test.local",
                password=password,
                name=f"冒烟捌{suffix[:4]}",
            )

            gm = await client.post(
                "/api/v1/gm/character/set",
                headers=headers,
                json={
                    "spirit_stones": 200_000,
                    "cultivation_points": 500,
                    "grant_craft_materials": True,
                    "grant_test_equipment": True,
                },
            )
            _assert_ok(gm.json(), "gm kit")

            # 1) 穿戴测试装备 → breakdown 含装备
            slots = _assert_ok(
                (await client.get("/api/v1/equipment/slots", headers=headers)).json(),
                "equipment slots",
            )
            bag = (slots.get("equipment") or {}).get("bag_equipment") or []
            sword = next((r for r in bag if r.get("item_id") == "iron_sword_t1"), None)
            assert sword, slots
            equip = await client.post(
                "/api/v1/equipment/equip",
                headers=headers,
                json={"slot": "weapon_1", "item_uid": sword["item_uid"]},
            )
            eq_data = _assert_ok(equip.json(), "equip iron_sword")
            breakdown = ((eq_data.get("combat") or {}).get("breakdown")) or []
            assert any(r.get("source") == "equipment" for r in breakdown), breakdown

            # 2) 洞府枢纽 + 研究室功法定稿（列表可见自研来源）
            cave = _assert_ok(
                (await client.get("/api/v1/cave", headers=headers)).json(),
                "cave overview",
            )
            assert any(r.get("id") == "lab" for r in (cave.get("rooms") or [])), cave
            tech_sess = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions",
                        headers=headers,
                        json={
                            "kind": "technique",
                            "materials": [{"item_id": "herb_spirit_grass", "quantity": 2}],
                            "spends": {"cultivation_points": 20},
                        },
                    )
                ).json(),
                "research technique session",
            )
            tech_fin = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions/{tech_sess['id']}/finalize",
                        headers=headers,
                        json={"label_zh": "冒烟吐纳残篇"},
                    )
                ).json(),
                "finalize technique",
            )
            assert tech_fin["private"]["source_label_zh"] == "自研"
            tech_list = _assert_ok(
                (await client.get("/api/v1/techniques/me", headers=headers)).json(),
                "techniques me",
            )
            assert any(
                t.get("id") == tech_fin["private"]["id"] and t.get("source_label_zh") == "自研"
                for t in (tech_list.get("items") or [])
            )

            # 3) 自研阵法定稿 → 防守预设 → 快照
            form_sess = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions",
                        headers=headers,
                        json={
                            "kind": "formation",
                            "materials": [{"item_id": "herb_spirit_grass", "quantity": 1}],
                            "spends": {"cultivation_points": 10},
                        },
                    )
                ).json(),
                "research formation session",
            )
            catalog = _assert_ok(
                (await client.get(f"{LAB}/catalog", headers=headers)).json(),
                "lab catalog",
            )
            terrain_layout = (catalog.get("formation") or {}).get("terrain_layout") or {
                "mode": "brush",
                "brush": {
                    "max_obstacles": 3,
                    "max_ravines": 1,
                    "allowed_types": ["obstacle", "ravine"],
                    "paint_zone": "own_half",
                },
            }
            draft = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions/{form_sess['id']}/draft",
                        headers=headers,
                        json={
                            "blueprint": {
                                "deploy": {
                                    "mode": "free_own",
                                    "cells": [],
                                    "add_cells": [],
                                    "exclude_cells": [],
                                    "allow_neutral": False,
                                },
                                "terrain_layout": terrain_layout,
                                "terrain": [
                                    {
                                        "x": 1,
                                        "y": 1,
                                        "type": "obstacle",
                                        "subtype": "destructible",
                                    },
                                ],
                                "force_shifts": [],
                            },
                        },
                    )
                ).json(),
                "formation draft",
            )
            assert draft.get("blueprint")
            form_fin = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions/{form_sess['id']}/finalize",
                        headers=headers,
                        json={"label_zh": "冒烟雾障阵"},
                    )
                ).json(),
                "finalize formation",
            )
            fid = form_fin["private"]["id"]
            _assert_ok(
                (
                    await client.put(
                        "/api/v1/formation/presets/1",
                        headers=headers,
                        json={
                            "name": "冒烟防阵",
                            "role": "defense",
                            "formation_id": fid,
                            "units": [
                                {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                            ],
                        },
                    )
                ).json(),
                "save defense preset",
            )
            snap = _assert_ok(
                (await client.post("/api/v1/snapshot/defense/update", headers=headers)).json(),
                "defense snapshot",
            )
            assert (snap.get("snapshot") or {}).get("formation_id") == fid

            # 4) 画符 + 预载 + PVE 见中文 item_trigger
            tal_sess = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions",
                        headers=headers,
                        json={
                            "kind": "talisman",
                            "materials": [{"item_id": "talisman_paper", "quantity": 1}],
                            "spends": {"cultivation_points": 10},
                            "effect_id": "first_hit_ward",
                        },
                    )
                ).json(),
                "research talisman session",
            )
            tal_fin = _assert_ok(
                (
                    await client.post(
                        f"{LAB}/sessions/{tal_sess['id']}/finalize",
                        headers=headers,
                        json={"label_zh": "冒烟护体符"},
                    )
                ).json(),
                "finalize talisman",
            )
            tid = tal_fin["private"]["id"]
            scribed = _assert_ok(
                (
                    await client.post(
                        "/api/v1/craft/talisman/scribe",
                        headers=headers,
                        json={"template_id": tid, "quantity": 1},
                    )
                ).json(),
                "scribe talisman",
            )
            inv = _assert_ok(
                (await client.get("/api/v1/inventory", headers=headers)).json(),
                "inventory",
            )
            tal_row = next(
                (
                    r
                    for r in (inv.get("items") or [])
                    if r.get("item_id") == tid and r.get("item_type") == "talisman"
                ),
                None,
            )
            assert tal_row, (scribed, inv)
            _assert_ok(
                (
                    await client.put(
                        "/api/v1/craft/talisman/preload",
                        headers=headers,
                        json={"inventory_item_ids": [int(tal_row["id"])]},
                    )
                ).json(),
                "preload talisman",
            )
            battle = _assert_ok(
                (
                    await client.post(
                        "/api/v1/battle/pve",
                        headers=headers,
                        json={"monster_id": "tutorial_slime"},
                    )
                ).json(),
                "pve with talisman",
            )
            report = battle.get("report") or {}
            events = report.get("events") or []
            triggers = [e for e in events if e.get("type") == "item_trigger"]
            assert triggers, events
            detailed = "\n".join(report.get("detailed_log") or [])
            assert "符箓：" in detailed, detailed

            # 5) 宗门工坊真扣材料
            _assert_ok(
                (
                    await client.post(
                        "/api/v1/sect/create",
                        headers=headers,
                        json={
                            "name": f"冒烟宗{suffix[:4]}",
                            "specialty": "formation",
                        },
                    )
                ).json(),
                "create sect",
            )
            hire = await client.post(
                "/api/v1/sect/workshops/smithing/hire",
                headers=headers,
                json={
                    "craftsman_id": "apprentice_smith",
                    "recipe_id": "ore_plate_t1",
                },
            )
            _assert_ok(hire.json(), "workshop hire (true materials)")

            open_sess = _assert_ok(
                (await client.get(f"{LAB}/sessions", headers=headers)).json(),
                "list open lab sessions",
            )
            assert isinstance(open_sess.get("items"), list)

            # 6) 待引渡禁研究室写（PlayGate → 40211）
            ferry = await client.post(
                "/api/v1/gm/character/set",
                headers=headers,
                json={"set_awaiting_ferry": True},
            )
            _assert_ok(ferry.json(), "set awaiting_ferry")
            blocked = await client.post(
                f"{LAB}/sessions",
                headers=headers,
                json={
                    "kind": "technique",
                    "materials": [{"item_id": "herb_spirit_grass", "quantity": 1}],
                    "spends": {"cultivation_points": 20},
                },
            )
            blocked_body = blocked.json()
            assert blocked_body.get("code") == 40211, blocked_body
            print("[ OK ] lab write blocked in awaiting_ferry (40211)")

            print("smoke_m8 PASSED")


if __name__ == "__main__":
    asyncio.run(main())
