"""
M3 战斗成型 HTTP 冒烟脚本（对本地后端跑通完整竖切）。

流程：注册两账号 → 创角 → board-meta → 预设保存 → 快照更新 →
教学 PVE（无预设）→ 荒原双狼 PVE（带预设）→ 体力读数 → PVP 攻打。

用法::

    python scripts/smoke_m3.py [base_url]

默认 base_url = http://127.0.0.1:8031/api/v1
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
    except urllib.error.HTTPError as exc:  # 业务错误也带统一信封
        return json.loads(exc.read())


def expect(envelope: dict[str, Any], label: str, code: int = 0) -> dict[str, Any]:
    """断言信封 code；失败即退出。"""
    if envelope.get("code") != code:
        print(f"[FAIL] {label}: {envelope.get('code')} {envelope.get('message')}")
        sys.exit(1)
    print(f"[ OK ] {label}")
    return envelope.get("data") or {}


def register_and_create(email: str, name: str) -> str:
    """注册 + 登录 + 创角，返回 access_token。"""
    call("POST", "/auth/register", {"password": "password123", "email": email})
    login = expect(
        call("POST", "/auth/login", {"account": email, "password": "password123"}),
        f"login {email}",
    )
    token = login["access_token"]
    expect(call("POST", "/characters", {"name": name}, token=token), f"创角 {name}")
    return token


def main() -> None:
    """执行冒烟流程。"""
    token_a = register_and_create("m3smoke_a@example.com", "冒烟攻方")
    token_b = register_and_create("m3smoke_b@example.com", "冒烟守方")

    meta = expect(call("GET", "/formation/board-meta", token=token_a), "board-meta")
    assert meta["size"] == 7, "棋盘尺寸应为 7"

    presets = expect(call("GET", "/formation/presets", token=token_a), "presets 列表")
    assert len(presets["presets"]) == 3, "默认三槽"

    expect(
        call(
            "PUT",
            "/formation/presets/0",
            {
                "name": "冒烟攻阵",
                "role": "attack",
                "formation_id": "none",
                "units": [
                    {"unit_uid": "main", "unit_kind": "main", "x": 0, "y": 3},
                    {"unit_uid": "puppet_1", "unit_kind": "puppet", "x": 1, "y": 2},
                ],
            },
            token=token_a,
        ),
        "保存进攻预设",
    )

    # 非法占位应报 40041
    expect(
        call(
            "PUT",
            "/formation/presets/2",
            {
                "name": "非法",
                "role": "temp",
                "formation_id": "none",
                "units": [{"unit_uid": "main", "unit_kind": "main", "x": 3, "y": 3}],
            },
            token=token_a,
        ),
        "中立列落子被拒（40041）",
        code=40041,
    )

    expect(call("POST", "/snapshot/defense/update", token=token_b), "守方手动更新快照")
    expect(
        call("POST", "/snapshot/defense/update", token=token_b),
        "冷却中再更新被拒（40045）",
        code=40045,
    )

    pve1 = expect(
        call("POST", "/battle/pve", {"monster_id": "tutorial_slime"}, token=token_a),
        "教学 PVE（默认预设）",
    )
    report = pve1["report"]
    assert report["schema_version"] == 1 and report["events"], "战报应含事件"
    assert report["events"][0]["type"] == "battle_start"
    print(f"       PVE 结果: {pve1['result']}，{report['rounds']} 回合，体力剩 {pve1['stamina']['left']}")

    pve2 = expect(
        call(
            "POST",
            "/battle/pve",
            {"monster_id": "wild_wolves", "preset_slot": 0},
            token=token_a,
        ),
        "双狼 PVE（带预设）",
    )
    print(f"       双狼结果: {pve2['result']}，{pve2['report']['rounds']} 回合")

    stamina = expect(call("GET", "/battle/stamina", token=token_a), "体力读数")
    print(f"       体力: {stamina['left']}/{stamina['cap']}")

    opponents = expect(call("GET", "/battle/pvp/opponents", token=token_a), "对手列表")
    target = next(
        o for o in opponents["opponents"] if o["dao_name"] == "冒烟守方"
    )
    expect(
        call("GET", f"/snapshot/defense/{target['character_id']}", token=token_a),
        "攻打前预览快照",
    )
    pvp = expect(
        call(
            "POST",
            "/battle/pvp/attack",
            {"target_character_id": target["character_id"], "preset_slot": 0},
            token=token_a,
        ),
        "PVP 攻打快照",
    )
    print(f"       PVP 结果: {pvp['result']}，{pvp['report']['rounds']} 回合")

    print("[DONE] M3 冒烟全部通过")


if __name__ == "__main__":
    main()
