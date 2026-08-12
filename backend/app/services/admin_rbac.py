"""后台 RBAC 角色常量与权限判定。"""

from __future__ import annotations

from typing import Iterable

# 与《后台管理系统开发计划》§6 对齐
ROLE_VIEWER = "viewer"
ROLE_EDITOR_CONTENT = "editor_content"
ROLE_EDITOR_BALANCE = "editor_balance"
ROLE_PUBLISHER = "publisher"
ROLE_ADMIN = "admin"

ALL_ROLES: frozenset[str] = frozenset(
    {
        ROLE_VIEWER,
        ROLE_EDITOR_CONTENT,
        ROLE_EDITOR_BALANCE,
        ROLE_PUBLISHER,
        ROLE_ADMIN,
    },
)


def parse_roles(raw: str | Iterable[str] | None) -> list[str]:
    """
    将逗号串或列表规范为去重角色列表。

    Args:
        raw: ``\"viewer,publisher\"`` 或 list。

    Returns:
        list[str]: 合法角色；非法项丢弃。
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        parts = [str(item).strip() for item in raw if str(item).strip()]
    seen: set[str] = set()
    result: list[str] = []
    for role in parts:
        if role in ALL_ROLES and role not in seen:
            seen.add(role)
            result.append(role)
    return result


def roles_to_storage(roles: list[str]) -> str:
    """角色列表 → 落库逗号串。"""
    return ",".join(parse_roles(roles))


def has_role(roles: Iterable[str], *needed: str) -> bool:
    """
    是否具备任一所需角色；``admin`` 视为超权。

    Args:
        roles: 当前用户角色。
        *needed: 任一即可放行的角色。

    Returns:
        bool: 有权限则为 True。
    """
    role_set = set(roles)
    if ROLE_ADMIN in role_set:
        return True
    return bool(role_set.intersection(needed))


def can_view(roles: Iterable[str]) -> bool:
    """只读各域。"""
    return has_role(
        roles,
        ROLE_VIEWER,
        ROLE_EDITOR_CONTENT,
        ROLE_EDITOR_BALANCE,
        ROLE_PUBLISHER,
        ROLE_ADMIN,
    )


def can_edit_domain(roles: Iterable[str], *, risk: str) -> bool:
    """
    是否可改草稿。

    Args:
        roles: 当前角色。
        risk: ``content`` / ``balance`` / ``facility``（facility 暂同 content）。
    """
    if risk == "balance":
        return has_role(roles, ROLE_EDITOR_BALANCE, ROLE_ADMIN)
    return has_role(roles, ROLE_EDITOR_CONTENT, ROLE_EDITOR_BALANCE, ROLE_ADMIN)


def can_publish(roles: Iterable[str]) -> bool:
    """发布 / 回滚。"""
    return has_role(roles, ROLE_PUBLISHER, ROLE_ADMIN)
