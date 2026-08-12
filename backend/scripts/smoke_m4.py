"""
M4 双线程成长 HTTP 冒烟脚本。

流程：注册 → GM 金丹 → 凝练 → 双挂机 → 传修为 → 炼丹领取 → 发宠 → 布阵 → 快照。

用法::

    python scripts/smoke_m4.py [base_url]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8031/api/v1"


def call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """发送 JSON 请求。"""
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


def expect(envelope: dict[str, Any], label: str, code: int = 0) -> dict[str, Any]:
    """断言信封 code。"""
    if envelope.get("code") != code:
        print(f"[FAIL] {label}: {envelope.get('code')} {envelope.get('message')}")
        sys.exit(1)
    print(f"[ OK ] {label}")
    return envelope.get("data") or {}


def register_and_create(email: str, name: str) -> str:
    """注册 + 创角，返回 token。"""
    call("POST", "/auth/register", {"password": "password123", "email": email})
    login = expect(
        call("POST", "/auth/login", {"account": email, "password": "password123"}),
        f"login {email}",
    )
    token = login["access_token"]
    expect(call("POST", "/characters", {"name": name}, token=token), f"创角 {name}")
    return token


def main() -> None:
    """执行 M4 冒烟。"""
    token = register_and_create("m4smoke@example.com", "M4冒烟")

    expect(
        call(
            "POST",
            "/gm/character/set",
            {
                "force_jindan": True,
                "spirit_stones": 10000,
                "set_stamina": 200,
                "grant_craft_materials": True,
            },
            token=token,
        ),
        "GM 金丹+材料",
    )

    expect(call("POST", "/avatar/condense", {}, token=token), "凝练化身")
    expect(call("POST", "/avatar/idle", {"direction": "spirit"}, token=token), "化身修灵")
    expect(call("POST", "/idle/direction", {"direction": "spirit"}, token=token), "本体修灵")
    expect(call("POST", "/idle/sync", {}, token=token), "双线程 sync")

    expect(
        call(
            "POST",
            "/avatar/transfer",
            {"direction": "main_to_avatar", "resource": "cultivation_points", "amount": 10},
            token=token,
        ),
        "传修为",
    )

    job = expect(
        call(
            "POST",
            "/craft/start",
            {"recipe_id": "pill_stamina_minor", "actor": "main"},
            token=token,
        ),
        "开工炼丹",
    )
    expect(call("GET", "/craft/jobs", token=token), "工坊队列")
    expect(call("POST", "/pets/capture_test", {}, token=token), "测试捕获灵宠")

    bench = expect(call("GET", "/formation/bench", token=token), "布阵 bench")
    assert any(b.get("unit_kind") == "avatar" for b in bench.get("bench", []))

    expect(call("GET", "/avatar/sense", token=token), "神识读数")
    print("M4 smoke completed.")


if __name__ == "__main__":
    main()
