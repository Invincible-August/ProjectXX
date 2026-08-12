"""
后台导入/导出与条目级草稿合并工具（ADM-8 加深）。

支持 JSON / YAML 全文；扁平域支持 CSV（id + 若干标量列）。
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import yaml

from app.schemas.common import AppError

# 域 → 条目字典所在路径（用于结构化表编辑 / CSV）
# 值为从域根到「id→定义」dict 的键路径
ENTRY_TABLE_PATHS: dict[str, tuple[str, ...]] = {
    "pets": ("species",),
    "items": ("items",),
    "techniques": ("techniques",),
    "monsters": ("monsters",),
    "formations": ("formations",),
    "sects": ("facilities",),
    "map": ("regions",),
    "activity": ("activities",),
}


def dump_export(payload: dict[str, Any], *, fmt: str) -> tuple[str, str]:
    """
    将配置 dict 序列化为文本。

    Args:
        payload: 待导出对象。
        fmt: ``json`` / ``yaml``。

    Returns:
        tuple[str, str]: (media 子类型提示, 文本正文)。
    """
    normalized = (fmt or "json").strip().lower()
    if normalized == "yaml":
        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        return "yaml", text
    if normalized == "json":
        return "json", json.dumps(payload, ensure_ascii=False, indent=2)
    raise AppError(code=40000, message="format 仅支持 json / yaml", http_status=400)


def parse_import_text(raw_text: str, *, fmt: str) -> dict[str, Any]:
    """
    解析导入正文为 dict。

    Args:
        raw_text: 文件或粘贴正文。
        fmt: ``json`` / ``yaml``。

    Returns:
        dict[str, Any]: 根 mapping。
    """
    normalized = (fmt or "json").strip().lower()
    try:
        if normalized == "yaml":
            data = yaml.safe_load(raw_text)
        elif normalized == "json":
            data = json.loads(raw_text)
        else:
            raise AppError(code=40000, message="format 仅支持 json / yaml", http_status=400)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(code=40055, message=f"导入解析失败: {exc}", http_status=400) from exc
    if not isinstance(data, dict):
        raise AppError(code=40055, message="导入根须为 object/mapping", http_status=400)
    return data


def get_entry_table(root: dict[str, Any], domain_id: str) -> dict[str, Any]:
    """
    取出域内「条目表」dict；不存在则空表。

    Args:
        root: 域配置根。
        domain_id: 域 ID。
    """
    path = ENTRY_TABLE_PATHS.get(domain_id)
    if not path:
        raise AppError(code=40056, message=f"域 {domain_id} 不支持条目表编辑", http_status=400)
    cursor: Any = root
    for key in path[:-1]:
        nxt = cursor.get(key) if isinstance(cursor, dict) else None
        if not isinstance(nxt, dict):
            return {}
        cursor = nxt
    leaf = cursor.get(path[-1]) if isinstance(cursor, dict) else None
    if leaf is None:
        return {}
    if not isinstance(leaf, dict):
        raise AppError(code=40056, message="条目表须为 object", http_status=400)
    return leaf


def set_entry_table(root: dict[str, Any], domain_id: str, table: dict[str, Any]) -> dict[str, Any]:
    """
    写入条目表，返回修改后的 root（原地改）。

    Args:
        root: 域配置根（通常为草稿 overlay 或 effective 拷贝）。
        domain_id: 域 ID。
        table: id → 定义。
    """
    path = ENTRY_TABLE_PATHS.get(domain_id)
    if not path:
        raise AppError(code=40056, message=f"域 {domain_id} 不支持条目表编辑", http_status=400)
    cursor = root
    for key in path[:-1]:
        nxt = cursor.setdefault(key, {})
        if not isinstance(nxt, dict):
            raise AppError(code=40056, message=f"路径 {key} 不是 object", http_status=400)
        cursor = nxt
    cursor[path[-1]] = table
    return root


def entries_to_csv(domain_id: str, table: dict[str, Any]) -> str:
    """
    将条目表导出为简易 CSV（标量列；嵌套字段 JSON 字符串）。

    Args:
        domain_id: 域 ID（写入首列 meta 注释行外的 id）。
        table: 条目表。
    """
    rows: list[dict[str, str]] = []
    fieldnames: list[str] = ["id"]
    extra_keys: set[str] = set()
    for entry_id, body in table.items():
        if not isinstance(body, dict):
            body = {"_value": body}
        flat: dict[str, str] = {"id": str(entry_id)}
        for key, value in body.items():
            extra_keys.add(str(key))
            if isinstance(value, (dict, list)):
                flat[str(key)] = json.dumps(value, ensure_ascii=False)
            else:
                flat[str(key)] = "" if value is None else str(value)
        rows.append(flat)
    fieldnames.extend(sorted(extra_keys))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    # 域标记方便人工识别
    return f"# domain={domain_id}\n{buffer.getvalue()}"


def csv_to_entries(raw_text: str) -> dict[str, Any]:
    """
    解析简易 CSV 为条目表。

    Args:
        raw_text: CSV 正文（可含 ``#`` 注释行）。
    """
    lines = [line for line in raw_text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return {}
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if not reader.fieldnames or "id" not in reader.fieldnames:
        raise AppError(code=40055, message="CSV 须含 id 列", http_status=400)
    table: dict[str, Any] = {}
    for row in reader:
        entry_id = (row.get("id") or "").strip()
        if not entry_id:
            continue
        body: dict[str, Any] = {}
        for key, raw_value in row.items():
            if key is None or key == "id":
                continue
            text = (raw_value or "").strip()
            if text == "":
                continue
            # 尝试还原 JSON 嵌套
            if text.startswith("{") or text.startswith("["):
                try:
                    body[key] = json.loads(text)
                    continue
                except json.JSONDecodeError:
                    pass
            # 数字 / 布尔
            if text.lower() in {"true", "false"}:
                body[key] = text.lower() == "true"
                continue
            try:
                if "." in text:
                    body[key] = float(text)
                else:
                    body[key] = int(text)
                continue
            except ValueError:
                body[key] = text
        table[entry_id] = body
    return table
