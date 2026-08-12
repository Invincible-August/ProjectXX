"""
M5 环境与轮回 HTTP 冒烟脚本。

流程：注册 → GM 抬元婴圆满 → attempt 分流 → 渡劫准备/开渡/自动结算陨落
→ 自救 → 再置待引渡 → 入轮回 → 断言锻体+体质保留 + calendar/weather 200。

用法::

    python scripts/smoke_m5.py [base_url]

默认 base_url = http://127.0.0.1:8000/api/v1
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"


def call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """发送一次 JSON 请求并返回统一信封 dict。"""
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
    """断言信封 code；失败即退出。"""
    if envelope.get("code") != code:
        print(f"[FAIL] {label}: {envelope.get('code')} {envelope.get('message')}")
        sys.exit(1)
    print(f"[ OK ] {label}")
    return envelope.get("data") or {}


def main() -> None:
    """执行 M5 冒烟流程。"""
    email = "m5smoke@example.com"
    call("POST", "/auth/register", {"password": "password123", "email": email})
    login = expect(
        call("POST", "/auth/login", {"account": email, "password": "password123"}),
        "login",
    )
    token = login["access_token"]
    expect(call("POST", "/characters", {"name": "M5冒烟道友"}, token=token), "创角")

    # 世界环境可读
    expect(call("GET", "/world/calendar", token=token), "calendar")
    expect(call("GET", "/world/weather", token=token), "weather")

    # GM：元婴大圆满 + 满进度 + 灵石
    expect(
        call(
            "POST",
            "/gm/character/set",
            {
                "force_yuanying_peak": True,
                "spirit_stones": 100000,
            },
            token=token,
        ),
        "GM 元婴圆满",
    )

    attempt = expect(
        call("POST", "/breakthrough/attempt", token=token),
        "breakthrough attempt 分流",
    )
    assert attempt.get("needs_tribulation") is True, "应提示需渡劫"

    expect(call("POST", "/tribulation/start-prep", token=token), "start-prep")
    expect(call("POST", "/tribulation/commit-prep", token=token), "commit-prep")
    expect(call("POST", "/tribulation/begin", token=token), "begin")
    resolved = expect(
        call("POST", "/tribulation/auto-resolve", token=token),
        "auto-resolve",
    )
    assert (resolved.get("outcome") or {}).get("result") == "fallen", "应陨落"

    me = expect(call("GET", "/characters/me", token=token), "角色待引渡")
    assert me.get("status") == "awaiting_ferry"

    expect(call("POST", "/ferry/self-rescue", token=token), "自救")
    me2 = expect(call("GET", "/characters/me", token=token), "自救后 normal")
    assert me2.get("status") == "normal"

    # 再次陨落 → 轮回
    expect(
        call(
            "POST",
            "/gm/character/set",
            {"set_awaiting_ferry": True},
            token=token,
        ),
        "GM 再置待引渡",
    )
    reinc = expect(
        call("POST", "/ferry/enter-reincarnation", token=token),
        "入轮回",
    )
    assert reinc.get("to_major") == "body_tempering"

    mid = expect(call("GET", "/characters/me", token=token), "轮回后新生态")
    assert mid.get("status") == "reincarnating"
    assert mid.get("major_realm") == "body_tempering"
    assert mid.get("realm_stage") == 1
    # 永久加成表应对齐角色面板
    assert isinstance(mid.get("permanent_bonus"), dict)

    expect(
        call("GET", "/reincarnation/newborn", token=token),
        "新生目录",
    )
    shop = expect(call("GET", "/reincarnation/shop", token=token), "轮回商店")
    assert "fixed_items" in shop or "items" in shop
    assert "random_items" in shop
    expect(
        call(
            "POST",
            "/reincarnation/complete-newborn",
            {
                "spirit_root_ids": ["thunder_root"],
                "legacy_ids": ["memory_fragment_minor"],
                "constitution_path": "sturdy_body",
            },
            token=token,
        ),
        "确认新生",
    )

    final = expect(call("GET", "/characters/me", token=token), "新生后角色")
    assert final.get("status") == "normal"
    assert final.get("major_realm") == "body_tempering"
    assert final.get("realm_stage") == 1
    assert int(final.get("reincarnation_count") or 0) >= 1
    assert "thunder_root" in (final.get("spirit_root_tags") or [])

    print("[DONE] M5 smoke passed")


if __name__ == "__main__":
    main()
