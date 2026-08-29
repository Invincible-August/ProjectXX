### Task 7: 原创培养（基础加成、词条升级、突破）

**Files:**
- Modify: `technique_craft_service.py`
- API：`POST .../techniques/{technique_id}/base-upgrade` `{stat: attack|defense|speed}`；`POST .../affix-upgrade` `{slot}`；`POST .../breakthrough`
- Domain：`upgrade_points_for_base_level(n)`、`rank_cap(character.major_realm, ranks.keys())`、`can_breakthrough`
- `technique_service` 列表/战斗 grants：把 `base_json` 的 attack/defense/speed 按效能映射到 `phys_atk`/`magic_atk`/`phys_def`/`magic_def`/`speed`，再加词条 `stats * (1 + 0.2 * chosen_level)`（系数放 YAML `affix_level_mult: 0.2`）
- Test: `backend/tests/test_technique_craft.py`

规则：
- 仅 `author_character_id == character.id` 的 `source=research` 可培养。
- 基础加成：`total_upgrades + 1 <= ranks[major_rank].base_upgrade_cap`；费用取 `spirit_upgrade_cost` 或 `body_upgrade_cost` 下标 `min(total_upgrades, len-1)`；成功则对应 stat +1 段（payload 里存次数即可，展示点数 = 次数，ATTR = 次数 × YAML `base_stat_per_click` 默认 1）。
- `upgrade_points += base_bonus_points[min(new_level-1, len-1)]`。
- 词条升级：失败率 `affix_upgrade_fail_rate`，失败仍扣费；成功 `chosen_level += 1` 并加点。
- 突破：`upgrade_points >= ranks[next].upgrade_points_required` 且 `next` 在角色 `major_realm` 及以下（用 `realms.yaml` 的 `next_major` 链，下一阶 id 的「高度」≤ 角色当前高度）。下一阶不存在或超过人物境界 → 40223。失败只扣 `breakthrough_cost_*`（法术扣修为、武技扣炼体；修炼类按 SPELL/MARTIAL 集）。成功改 `major_rank`，**不扣** upgrade_points；若新阶 `affix_slots` 更大，给新栏空位。

定稿后培养改 `PrivateTechnique.payload_json`，不再写草稿行。

- [ ] **Step 1: 测试** 连续两次加 attack 第二次更贵；突破失败点不变阶不变；突破成功阶升点仍在；词条失败等级不变

- [ ] **Step 2: 实现并跑通**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_technique_craft.py -q`

Expected: PASS

---
