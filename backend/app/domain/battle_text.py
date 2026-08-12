"""
战报渲染器（M3自动移动攻击算法设计.md §11 · 非热路径纯函数）。

引擎只记结构化事件；本模块把事件渲染成：
    - 开局棋盘字符画（simple / detailed 两档通用）；
    - 结果摘要 dict（simple 档）；
    - 逐回合 DND 式中文日志（detailed 档）。

渲染不回查任何战斗状态——事件字段已带齐骰点与全部中间量。
玩家可见文案一律中文（开发计划 §0.0.2）。
"""

from __future__ import annotations

from typing import Any

from app.domain.board_tables import BOARD_SIZE

# 地形大类 → 棋盘字符画标记（不泄露障/渊子类；禁制用「禁」）
_TERRAIN_MARKS = {"obstacle": "障", "ravine": "渊", "seal": "禁"}

# 四象层名回落表（优先读事件 layer_label_zh，与 layer_payloads.LAYER_LABEL_ZH 对齐）
_LAYER_NAMES = {"environment": "环境", "weather": "天气", "effect": "场上效果"}

# 攻击类别 → 中文
_ATTACK_KIND_NAMES = {
    "melee_physical": "近战物理",
    "melee_magic": "近战法术",
    "ranged_physical": "远程物理",
    "ranged_magic": "远程法术",
}


def _pad_cell(text: str, width: int = 4) -> str:
    """按显示宽度补齐格内文本（中文按 2 列估宽）。"""
    display = sum(2 if ord(ch) > 0x7F else 1 for ch in text)
    return text + " " * max(0, width - display)


def _find_events(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    """按类型过滤事件。"""
    return [item for item in events if item.get("type") == event_type]


def _layer_cn(item: dict[str, Any]) -> str:
    """层中文名：优先 enrichment 字段；未知层不得裸出英文 id。"""
    if item.get("layer_label_zh"):
        return str(item["layer_label_zh"])
    layer = str(item.get("layer") or "")
    if layer in _LAYER_NAMES:
        return _LAYER_NAMES[layer]
    return _zh_or_none(None, layer or None)


def _zh_or_none(label: Any, fallback_id: Any) -> str:
    """
    优先中文名；无中文名时不得把英文 id 当正文（§0.0.2）。

    缺 label 时用「未知」占位并附 id 仅作括号机读提示（验收测应保证有 label）。
    """
    if label:
        return str(label)
    if fallback_id:
        return f"未知({fallback_id})"
    return "无"


def _resolved_zh(item: dict[str, Any]) -> str:
    """四象 resolved 展示串（中文）。"""
    if item.get("coverage") == "split":
        return (
            f"己方 {_zh_or_none(item.get('resolved_attacker_half_label_zh'), item.get('resolved_attacker_half'))} / "
            f"敌方 {_zh_or_none(item.get('resolved_defender_half_label_zh'), item.get('resolved_defender_half'))} / "
            f"中立 {_zh_or_none(item.get('resolved_neutral_label_zh'), item.get('resolved_neutral'))}"
        )
    return _zh_or_none(item.get("resolved_full_label_zh"), item.get("resolved_full"))


def render_board(events: list[dict[str, Any]]) -> str:
    """
    渲染开局棋盘字符画（两档通用）。

    - 棋子名直接写在格内；地形写「障 / 渊 / 禁」；
    - y 大在上（左下锚点 (0,0) 在左下）；
    - 天气 / 环境 / 效果用文字行说明（来自四象结算事件）。
    """
    start = _find_events(events, "battle_start")
    if not start:
        return ""
    start_ev = start[0]

    # 格内容表：优先棋子名（棋子不会与禁停地形同格）
    grid: dict[tuple[int, int], str] = {}
    for cell in start_ev.get("terrain") or []:
        grid[(int(cell["x"]), int(cell["y"]))] = _TERRAIN_MARKS.get(
            str(cell["kind"]),
            "?",
        )
    attacker_units: list[str] = []
    defender_units: list[str] = []
    for unit in start_ev.get("units") or []:
        x, y = int(unit["x"]), int(unit["y"])
        name = str(unit["name"])
        grid[(x, y)] = name
        label = f"{name}({x},{y})"
        if int(unit["side"]) == 0:
            attacker_units.append(label)
        else:
            defender_units.append(label)

    # 四象结算行（中文）
    layer_line_parts: list[str] = []
    for item in _find_events(events, "battlefield_layer"):
        cn = _layer_cn(item)
        if item.get("coverage") in (None, "none"):
            resolved = "无"
        elif item.get("coverage") == "cancelled":
            resolved = "互抵为无"
        else:
            resolved = _resolved_zh(item)
            notes = item.get("combat_notes") or []
            if notes:
                resolved = f"{resolved}（{'；'.join(str(n) for n in notes)}）"
        layer_line_parts.append(f"{cn}：{resolved}")

    lines: list[str] = []
    lines.append("   ".join(layer_line_parts))
    header = "y\\x │" + "│".join(_pad_cell(f" {x}", 5) for x in range(BOARD_SIZE)) + "│"
    lines.append(header)
    for y in range(BOARD_SIZE - 1, -1, -1):
        cells = "│".join(_pad_cell(grid.get((x, y), ""), 5) for x in range(BOARD_SIZE))
        lines.append(f" {y}  │{cells}│")
    lines.append("图例：障=障碍（能否破坏未知） 渊=深渊（能否飞越未知） 禁=禁制（挡对应远程）")
    lines.append(
        f"进攻方：{' '.join(attacker_units) or '无'}   "
        f"防守方：{' '.join(defender_units) or '无'}",
    )
    return "\n".join(lines)


def render_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    渲染结果摘要（simple 档）。

    返回:
        dict: 胜负 / 回合数 / 双方存活与剩余 HP / 击杀列表（中文名）。
    """
    end = _find_events(events, "battle_end")
    end_ev = end[0] if end else {}
    # uid → 名称（开局单位表）；摘要击杀必须中文名，禁止裸 uid（§0.0.2）
    names: dict[str, str] = {}
    for start_ev in _find_events(events, "battle_start"):
        for unit in start_ev.get("units") or []:
            names[str(unit["uid"])] = str(unit["name"])
    kills = [
        names.get(str(item["uid"]), f"未知({item['uid']})")
        for item in _find_events(events, "death")
    ]
    return {
        "winner": end_ev.get("winner"),
        "rounds": end_ev.get("rounds", 0),
        "survivors": end_ev.get("survivors", []),
        "kills": kills,
    }


def render_detailed(events: list[dict[str, Any]]) -> list[str]:
    """
    渲染逐回合 DND 式中文日志（detailed 档）。

    按事件类型查模板逐条生成；引擎零改动即可调整文案。
    """
    # uid → 名称映射（来自 battle_start）
    names: dict[str, str] = {}
    for start_ev in _find_events(events, "battle_start"):
        for unit in start_ev.get("units") or []:
            names[str(unit["uid"])] = str(unit["name"])

    def _n(uid: Any) -> str:
        """uid 转显示名；缺名时用未知占位，不裸出 uid。"""
        key = str(uid) if uid is not None else ""
        if key in names:
            return names[key]
        return _zh_or_none(None, key or None)

    lines: list[str] = []
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "battlefield_layer":
            if ev.get("coverage") in (None, "none"):
                continue
            cn = _layer_cn(ev)
            notes = ev.get("combat_notes") or []
            notes_txt = f"（{'；'.join(str(n) for n in notes)}）" if notes else ""
            if ev.get("coverage") == "cancelled":
                lines.append(f"【四象】{cn}：双方强制生效互抵，该层为无")
            elif ev.get("attacker_score") is not None:
                atk_zh = _zh_or_none(ev.get("attacker_label_zh"), ev.get("attacker_id"))
                def_zh = _zh_or_none(ev.get("defender_label_zh"), ev.get("defender_id"))
                outcome = (
                    "平局分区"
                    if ev["coverage"] == "split"
                    else _resolved_zh(ev)
                )
                lines.append(
                    f"【四象】{cn}对抗：进攻方 {atk_zh}"
                    f"（骰 {ev['attacker_dice']} → {ev['attacker_score']:.1f}） vs "
                    f"防守方 {def_zh}"
                    f"（骰 {ev['defender_dice']} → {ev['defender_score']:.1f}） → "
                    f"{outcome}{notes_txt}",
                )
            else:
                lines.append(
                    f"【四象】{cn}：{_resolved_zh(ev)} 覆盖全场{notes_txt}",
                )
        elif ev_type == "round_start":
            lines.append(f"—— 第 {ev['round']} 回合 ——")
        elif ev_type == "initiative":
            # 先攻事件已按「该单位行动前」交错写入；日志紧挨其移动/攻击行
            lines.append(
                f"【先攻】{_n(ev['uid'])}：速度 {ev['speed']} × d20={ev['dice']}"
                f" → 先攻 {ev['initiative']}",
            )
        elif ev_type == "move":
            path = ev.get("path") or []
            path_text = "→".join(f"({p['x']},{p['y']})" for p in path)
            reason_map = {
                "arrived": "到达",
                "budget": "步数用尽",
                "blocked_unit": "撞上单位中断",
                "blocked_terrain": "被地形阻挡",
                "abyss_bounce": "深渊弹回",
                "taunt": "进入嘲讽中断",
            }
            stop = str(ev.get("stop_reason") or "")
            stop_cn = reason_map.get(stop, _zh_or_none(None, stop or None))
            lines.append(
                f"【移动】{_n(ev['uid'])}：{path_text}"
                f"（{stop_cn}）",
            )
        elif ev_type == "taunt":
            cell = ev.get("cell") or {}
            lines.append(
                f"【嘲讽】{_n(ev['taunter'])} 强制 {_n(ev['victim'])} 以自己为目标"
                f"（格 ({cell.get('x')},{cell.get('y')})）",
            )
        elif ev_type == "ai_retarget":
            reason = str(ev.get("reason", ""))
            reason_cn = {
                "taunt": "嘲讽",
                "obstacle_indestructible": "障碍不可破",
                "abyss_nofly": "深渊禁飞",
                "cheaper": "更近目标",
            }.get(reason) or _zh_or_none(None, reason or None)
            from_uid = ev.get("from_uid")
            from_txt = _n(from_uid) if from_uid else "无"
            lines.append(
                f"【换目标】原因={reason_cn}：{from_txt} → {_n(ev.get('to_uid'))}",
            )
        elif ev_type == "hit_check":
            kind_raw = str(ev.get("attack_kind") or "")
            kind_cn = _ATTACK_KIND_NAMES.get(kind_raw) or _zh_or_none(None, kind_raw or None)
            lines.append(
                f"【攻击】{_n(ev['attacker'])} → {_n(ev['target'])}（{kind_cn}）："
                f"命中率 {round(ev['chance'] * 100)}%"
                f"（基础 {round(ev['base_rate'] * 100)}%"
                f" + 额外 {round(ev['extra_rate'] * 100)}%"
                f" − 闪避 {round(ev['dodge_rate'] * 100)}%），"
                f"掷 d100={ev['dice']} → {'命中' if ev['hit'] else '未命中'}",
            )
        elif ev_type == "damage":
            mul = ev.get("damage_mul", 1.0)
            mul_txt = f" × 载荷 {mul}" if abs(float(mul) - 1.0) > 1e-9 else ""
            lines.append(
                f"【伤害】威力 {ev['power']} × 克制 {ev['c_atk']}"
                f" × 骰 {ev['dice']}{mul_txt} − 防御 {ev['defense']} × 克制 {ev['c_def']}"
                f" = {ev['final']} → {_n(ev['target'])}"
                f" HP {ev['hp_before']}→{ev['hp_after']}",
            )
        elif ev_type == "obstacle_hit":
            cell = ev["cell"]
            result_cn = "击破" if ev["result"] == "break" else "揭晓【无法破坏】"
            lines.append(
                f"【破障】{_n(ev['uid'])} 攻击障碍 ({cell['x']},{cell['y']})：{result_cn}",
            )
        elif ev_type == "abyss_pass":
            cell = ev["cell"]
            lines.append(
                f"【探路】{_n(ev['uid'])} 飞越深渊 ({cell['x']},{cell['y']})：可通过",
            )
        elif ev_type == "abyss_bounce":
            cell = ev["cell"]
            back = ev["back_to"]
            lines.append(
                f"【探路】{_n(ev['uid'])} 尝试进入深渊 ({cell['x']},{cell['y']})："
                f"揭晓【禁飞】→ 弹回 ({back['x']},{back['y']})",
            )
        elif ev_type == "blocked":
            reason = ev.get("reason")
            if reason == "los_blocked":
                src = ev.get("block_source")
                if src == "seal":
                    reason_cn = "远程攻击被禁制挡住"
                elif src == "obstacle":
                    reason_cn = "远程攻击被障碍挡住"
                else:
                    reason_cn = "视线被遮挡"
            else:
                reason_cn = "无可达目标"
            lines.append(f"【受阻】{_n(ev['uid'])}：{reason_cn}")
        elif ev_type == "death":
            lines.append(f"【阵亡】{_n(ev['uid'])}")
        elif ev_type == "battle_end":
            winner_cn = "进攻方胜" if ev["winner"] == "attacker" else "防守方胜"
            lines.append(f"—— 战斗结束：{winner_cn}（共 {ev['rounds']} 回合） ——")
    return lines
