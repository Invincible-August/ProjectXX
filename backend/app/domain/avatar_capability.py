"""
化身能力索引：预计算境界序与功能解锁，供请求热路径复用。

避免每次 is_feature_unlocked / list_feature_states 重新走 next_major 链。
无 IO；由 load_game_config 在解析 avatar+realms 后构建一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.domain.m4_constants import IDLE_DIRECTION_FEATURE, AvatarFeature, IdleDirection


@dataclass(frozen=True)
class AvatarFeatureEntry:
    """单一功能解锁条目的索引视图。"""

    feature_id: str
    min_major: str
    min_major_index: int
    label_zh: str
    summary: str


@dataclass(frozen=True)
class AvatarCapabilityIndex:
    """
    化身玩法能力门面（只读）。

    属性:
        realm_order: 大境界从低到高。
        realm_index: major → 序号。
        features: feature_id → 条目。
        transfer_retention: 全局互传保留率。
        transfer_by_major: 境界覆盖保留率。
        transfer_min_amount: 最小互传。
        transfer_summary: 玩家可见说明。
        transfer_allow / transfer_deny: 资源白/黑名单。
        stamina_base_cap / stamina_cap_by_major / ...: 体力表快照。
    """

    realm_order: tuple[str, ...]
    realm_index: Mapping[str, int]
    features: Mapping[str, AvatarFeatureEntry]
    transfer_retention: float
    transfer_by_major: Mapping[str, float]
    transfer_min_amount: int
    transfer_summary: str
    transfer_allow: tuple[str, ...]
    transfer_deny: tuple[str, ...]
    stamina_base_cap: int
    stamina_cap_by_major: Mapping[str, int]
    stamina_daily_cap: int
    stamina_recovery_per_hour: float
    stamina_recovery_summary: str
    stamina_action_costs: Mapping[str, int]
    idle_spirit_enabled: bool
    idle_body_enabled: bool
    idle_crafting_enabled: bool

    def major_index(self, major: str) -> int:
        """大境界序号；未知返回 -1。"""
        return int(self.realm_index.get(major, -1))

    def meets_major(self, character_major: str, required_major: str) -> bool:
        """本体境界是否 ≥ 要求境界。"""
        cur = self.major_index(character_major)
        need = self.major_index(required_major)
        if cur < 0 or need < 0:
            return character_major == required_major
        return cur >= need

    def is_unlocked(self, character_major: str, feature_id: str) -> bool:
        """功能是否已解锁。"""
        entry = self.features.get(feature_id)
        if entry is None:
            return False
        cur = self.major_index(character_major)
        if cur < 0:
            return character_major == entry.min_major
        return cur >= entry.min_major_index

    def check_feature(
        self,
        character_major: str,
        feature_id: str,
    ) -> tuple[bool, int | None, str]:
        """
        功能闸。

        返回:
            (ok, error_code, message)；未解锁 code=40090。
        """
        if self.is_unlocked(character_major, feature_id):
            return True, None, ""
        entry = self.features.get(feature_id)
        label = entry.label_zh if entry else feature_id
        min_major = entry.min_major if entry else ""
        reason = f"化身功能未解锁：{feature_id}（{label}）"
        if min_major:
            reason += f"；需本体达 {min_major}"
        return False, 40090, reason

    def feature_for_idle(self, direction: str) -> str | None:
        """挂机方向对应功能 id；none → None。"""
        if direction == IdleDirection.NONE:
            return None
        return IDLE_DIRECTION_FEATURE.get(direction)

    def idle_direction_allowed(self, character_major: str, direction: str) -> tuple[bool, str | None]:
        """
        方向是否可选（功能 + 速率表 enabled）。

        返回:
            (ok, feature_id_if_blocked)。
        """
        feature_id = self.feature_for_idle(direction)
        if feature_id is None:
            return True, None
        if not self.is_unlocked(character_major, feature_id):
            return False, feature_id
        enabled_map = {
            IdleDirection.SPIRIT: self.idle_spirit_enabled,
            IdleDirection.BODY: self.idle_body_enabled,
            IdleDirection.CRAFTING: self.idle_crafting_enabled,
            "sect_mining": self.idle_spirit_enabled,
        }
        if not enabled_map.get(direction, True):
            return False, feature_id
        return True, None

    def retention_ratio(self, character_major: str) -> float:
        """当前本体境界互传保留率。"""
        if character_major in self.transfer_by_major:
            ratio = float(self.transfer_by_major[character_major])
        else:
            ratio = float(self.transfer_retention)
        return max(0.0, min(1.0, ratio))

    def stamina_cap(self, character_major: str) -> int:
        """化身体力上限。"""
        if character_major in self.stamina_cap_by_major:
            return max(0, int(self.stamina_cap_by_major[character_major]))
        return max(0, int(self.stamina_base_cap))

    def action_cost(self, action_key: str) -> int:
        """行动耗体；未知键 → 0。"""
        return max(0, int(self.stamina_action_costs.get(action_key, 0)))

    def list_feature_states(
        self,
        character_major: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        显性功能看板 + 下一档预告（单次遍历，复用预计算序号）。

        返回:
            (features[], unlock_preview | None)。
        """
        cur_idx = self.major_index(character_major)
        features: list[dict[str, Any]] = []
        next_by_major_idx: dict[int, list[dict[str, Any]]] = {}

        for entry in self.features.values():
            unlocked = cur_idx >= 0 and cur_idx >= entry.min_major_index
            if cur_idx < 0:
                unlocked = character_major == entry.min_major
            item = {
                "feature_id": entry.feature_id,
                "min_major": entry.min_major,
                "label_zh": entry.label_zh,
                "summary": entry.summary,
                "unlocked": unlocked,
            }
            features.append(item)
            if not unlocked and entry.min_major_index >= 0:
                next_by_major_idx.setdefault(entry.min_major_index, []).append(
                    {
                        "feature_id": entry.feature_id,
                        "label_zh": entry.label_zh,
                        "summary": entry.summary,
                        "min_major": entry.min_major,
                    },
                )

        unlock_preview: dict[str, Any] | None = None
        if cur_idx >= 0:
            for maj_idx in sorted(next_by_major_idx.keys()):
                if maj_idx > cur_idx:
                    unlock_preview = {
                        "next_major": self.realm_order[maj_idx],
                        "features": next_by_major_idx[maj_idx],
                    }
                    break

        features.sort(
            key=lambda it: (
                0 if it["unlocked"] else 1,
                self.features[str(it["feature_id"])].min_major_index
                if str(it["feature_id"]) in self.features
                else 999,
                str(it["feature_id"]),
            ),
        )
        return features, unlock_preview

    @staticmethod
    def build_realm_order(realms: Mapping[str, Any]) -> tuple[str, ...]:
        """按 next_major 链推导大境界顺序。"""
        pointed: set[str] = set()
        for cfg in realms.values():
            nxt = getattr(cfg, "next_major", None)
            if nxt is None and isinstance(cfg, dict):
                nxt = cfg.get("next_major")
            if nxt:
                pointed.add(str(nxt))
        roots = [k for k in realms if k not in pointed]
        if not roots:
            return tuple(realms.keys())
        order: list[str] = []
        current: str | None = roots[0]
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            order.append(current)
            cfg = realms.get(current)
            nxt = getattr(cfg, "next_major", None) if cfg is not None else None
            if nxt is None and isinstance(cfg, dict):
                nxt = cfg.get("next_major")
            current = str(nxt) if nxt else None
        for key in realms:
            if key not in order:
                order.append(key)
        return tuple(order)

    @classmethod
    def from_config(
        cls,
        avatar_cfg: Any,
        realms: Mapping[str, Any],
    ) -> "AvatarCapabilityIndex":
        """
        从 AvatarConfig + realms 构建索引。

        参数:
            avatar_cfg: ``AvatarConfig``（须含 feature_unlocks / transfer / stamina / rates）。
            realms: 境界表。
        """
        order = cls.build_realm_order(realms)
        realm_index = {name: i for i, name in enumerate(order)}
        features: dict[str, AvatarFeatureEntry] = {}
        for feature_id, body in (avatar_cfg.feature_unlocks or {}).items():
            min_major = str(getattr(body, "min_major", "") or "")
            features[str(feature_id)] = AvatarFeatureEntry(
                feature_id=str(feature_id),
                min_major=min_major,
                min_major_index=int(realm_index.get(min_major, -1)),
                label_zh=str(getattr(body, "label_zh", feature_id) or feature_id),
                summary=str(getattr(body, "summary", "") or ""),
            )
        transfer = avatar_cfg.transfer
        stamina = avatar_cfg.stamina
        return cls(
            realm_order=order,
            realm_index=realm_index,
            features=features,
            transfer_retention=float(transfer.retention_ratio),
            transfer_by_major=dict(transfer.retention_by_major),
            transfer_min_amount=int(transfer.min_amount),
            transfer_summary=str(transfer.summary or ""),
            transfer_allow=tuple(transfer.allow),
            transfer_deny=tuple(transfer.deny),
            stamina_base_cap=int(stamina.base_cap),
            stamina_cap_by_major=dict(stamina.cap_by_major),
            stamina_daily_cap=int(stamina.daily_action_cap),
            stamina_recovery_per_hour=float(stamina.recovery_per_hour),
            stamina_recovery_summary=str(stamina.recovery_summary or ""),
            stamina_action_costs=dict(stamina.action_costs),
            idle_spirit_enabled=bool(avatar_cfg.spirit_rates.enabled),
            idle_body_enabled=bool(avatar_cfg.body_rates.enabled),
            idle_crafting_enabled=bool(avatar_cfg.crafting_rates.enabled),
        )


# 常用功能 id 再导出，便于调用方少写魔法字符串
__all__ = [
    "AvatarCapabilityIndex",
    "AvatarFeatureEntry",
    "AvatarFeature",
]
