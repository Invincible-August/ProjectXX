# Project修仙 · Agent 约束

权威细则：`设计文档/开发计划.md` **§0.0～§0.9**。  
排期与延后项 **不要** 写进规则：读开发计划 **§20** 与 `设计文档/后续待完成.md`。  
完整副本与规则正文：`约束/AGENTS.md`、`约束/rules/`、`约束/skills/`。  
Cursor 如何加载：`Cursor约束配置说明.md`。

## 最高优先级

1. **凡可配置必须进后台注册表**（§0.0）：禁止前端/后端写死物种、功法、怪物、道具、天气等本应进注册表的枚举；禁止只改 YAML + 玩家代码的一次性方案。DEV `/gm` 仅联调，正式改数走后台。
2. **机读英文，人读中文**（§0.0.2）：代码键可用英文；玩家 UI、战报、给人读的文档必须中文。英文键首次出现写 `英文（中文）`。会进 UI/战报的内容须有 `label_zh`。
3. **显性设计**（§0.7）：影响收益、风险、偏好、成功率的设定必须对玩家可见（基础→有效、来源或 catalog）。预览与结算同一套服务端公式；前端只渲染。
4. **竖切交付**（§0.1）：每个板块「后端可结算 + 前端可操作 + 联调」。节奏：表结构（可后台）→ 领域逻辑+单测 → API/WS → 前端 → 联调。里程碑结束同步 `README.md` / `CHANGELOG.md`。
5. **协议常量**（§0.6.3）：禁止在 `api/` / `services/` / `domain/` / `game/` 新增未命名魔数或裸协议字面量；放入 `backend/app/constants/`，公开名加中文注释。
6. **新文件即时 `git add`**（§0.0.5）：只暂存，不擅自 `commit` / `push`。
7. **拍板前不开 M9**。当前主线见开发计划 §20。

## 技术栈（写死）

前端 Vue 3 + Vite + TypeScript + Pinia + Vue Router；后端 Python 3.11 FastAPI；**服务端权威**。日常挂机/突破/PVE 走 HTTP；道主/秘境/世界 Boss 等强交互才上 WebSocket。

## 按任务再读

| 场景 | 读 |
| --- | --- |
| 改后端 | `约束/rules/backend-conventions.mdc` |
| 改玩家前端展示 | `约束/rules/frontend-display.mdc` |
| 改运营后台 / 新配置域 | `约束/rules/admin-ops.mdc` · skill `admin-content-domain` |
| 新玩法竖切 | skill `vertical-slice` |
| 更新测试服 | skill `deploy-test-server` |
| 检定 / 随机 | `设计文档/骰子系统设计.md` · 开发计划 §0.9 |
| 新活动互斥 | 开发计划 §0.8 · `backend/app/domain/activity_mutex.py` |
