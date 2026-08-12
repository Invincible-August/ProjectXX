"""
ADM 冒烟：登录 → 草稿 → 校验 → 发布 pets → Bundle 摘要含新物种 → 回滚。

用法（backend venv）：
  python scripts/smoke_adm.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from httpx import ASGITransport, AsyncClient

from app.main import app


async def main() -> None:
    """跑通 ADM-1～3 最小闭环（显式进入 FastAPI lifespan 建表/灌覆盖）。"""
    # ASGITransport 默认不跑 lifespan；须进入上下文才会 create_all + bootstrap
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login = await client.post(
                "/admin/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
            assert login.status_code == 200, login.text
            body = login.json()
            assert body["code"] == 0, body
            token = body["data"]["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            domains = await client.get("/admin/config/domains", headers=headers)
            assert domains.json()["code"] == 0
            domain_ids = {d["domain_id"] for d in domains.json()["data"]["domains"]}
            for required in (
                "pets",
                "items",
                "techniques",
                "weather",
                "calendar",
                "sects",
                "map",
                "activity",
                "realms",
                "idle",
                "dice",
            ):
                assert required in domain_ids, required

            # 双写：idle 表格读出再写回草稿（后端 format）
            idle_schema = await client.get("/admin/config/idle/schema", headers=headers)
            assert idle_schema.json()["code"] == 0, idle_schema.text
            assert "table" in idle_schema.json()["data"]["edit_modes"]
            idle_sheets = await client.get("/admin/config/idle/sheets", headers=headers)
            assert idle_sheets.json()["code"] == 0, idle_sheets.text
            save_sheets = await client.put(
                "/admin/config/idle/sheets",
                headers=headers,
                json={"sheets": idle_sheets.json()["data"]["sheets"], "replace_draft": True},
            )
            assert save_sheets.json()["code"] == 0, save_sheets.text

            # 条目 upsert
            put_entry = await client.put(
                "/admin/config/pets/entries/smoke_table_pet",
                headers=headers,
                json={
                    "body": {
                        "name": "表冒烟宠",
                        "race": "beast",
                        "rarity": "common",
                        "roles": ["dps"],
                        "acquire_tags": ["gm_grant"],
                        "base_atk": 2,
                        "base_hp": 10,
                        "base_speed": 5,
                        "upgrade_cost": {"spirit_stones": 1, "materials": []},
                    },
                },
            )
            assert put_entry.json()["code"] == 0, put_entry.text

            overlay = {
                "species": {
                    "smoke_adm_fox": {
                        "name": "冒烟灵狐",
                        "race": "beast",
                        "rarity": "common",
                        "roles": ["dps"],
                        "acquire_tags": ["gm_grant", "capture_test"],
                        "base_atk": 4,
                        "base_hp": 22,
                        "base_speed": 9,
                        "upgrade_cost": {"spirit_stones": 1, "materials": []},
                    },
                },
            }
            save = await client.put(
                "/admin/config/pets/draft",
                headers=headers,
                json={"payload": overlay},
            )
            assert save.json()["code"] == 0, save.text

            pub = await client.post(
                "/admin/config/pets/publish",
                headers=headers,
                json={"note": "smoke_adm", "confirm_high_risk": False},
            )
            assert pub.json()["code"] == 0, pub.text

            summary = await client.get("/admin/config/bundle/summary", headers=headers)
            species = summary.json()["data"]["pets_species"]
            assert "smoke_adm_fox" in species, species
            assert "facilities" in summary.json()["data"]

            # 设施开关发布
            fac = await client.put(
                "/admin/config/sects/draft",
                headers=headers,
                json={
                    "payload": {
                        "facilities": {
                            "spirit_beast_sect": {
                                "enabled": True,
                                "note": "smoke open",
                            },
                        },
                    },
                },
            )
            assert fac.json()["code"] == 0, fac.text
            fac_pub = await client.post(
                "/admin/config/sects/publish",
                headers=headers,
                json={"note": "open", "confirm_high_risk": False},
            )
            assert fac_pub.json()["code"] == 0, fac_pub.text
            summary3 = await client.get("/admin/config/bundle/summary", headers=headers)
            assert summary3.json()["data"]["facilities"]["spirit_beast_sect"] is True

            rb = await client.post(
                "/admin/config/pets/rollback",
                headers=headers,
                json={"target_version": 0, "confirm_high_risk": False},
            )
            assert rb.json()["code"] == 0, rb.text

            rb2 = await client.post(
                "/admin/config/sects/rollback",
                headers=headers,
                json={"target_version": 0, "confirm_high_risk": False},
            )
            assert rb2.json()["code"] == 0, rb2.text

            summary2 = await client.get("/admin/config/bundle/summary", headers=headers)
            species2 = summary2.json()["data"]["pets_species"]
            assert "smoke_adm_fox" not in species2

    print("smoke_adm OK: sheets/entries/sects/login/draft/publish/bundle/rollback")


if __name__ == "__main__":
    asyncio.run(main())
