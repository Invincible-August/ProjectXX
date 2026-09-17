---
name: admin-content-domain
description: Add or deepen an admin content domain with dual-write tables, Chinese field schema, validators, and registry. Use when creating admin CRUD, 后台域, OverlayStore, admin_field_schema, or making YAML operable from /management.
---

# 新后台内容域

权威：`设计文档/开发计划.md` **§0.0 / §0.0.1** · `设计文档/后台管理系统开发计划.md`。

## 步骤

1. 在后台计划 **内容域清单** 登记域 id 与职责，再写玩法代码。
2. 配置进注册表 + 校验器；玩家服只读 Bundle / Overlay，禁止发版改代码才能加一条内容。
3. **双写**：表格编辑 + JSON 覆盖；表格提交由 **后端 format** 成该域 JSON。
4. 每个可编辑字段：`label_zh` + `help_zh`。
5. 境界 / 挂机 / 骰子等矩阵拆成运营表格，不要只给 textarea。
6. 协议常量进 `app.constants`；写操作审计 + RBAC。
7. 运营可见文案中文；文档英文键双语备注。
8. 禁止对运营暴露旧「保存 JSON 草稿 / 发布 / 回滚 YAML」文案。

## 结束前自检

见后台计划 **§9**：中文字段、常量、中文文案、审计、RBAC。
