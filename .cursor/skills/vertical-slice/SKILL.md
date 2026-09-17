---
name: vertical-slice
description: Execute a playable frontend+backend vertical slice with config, tests, Chinese UI, and changelog. Use when adding a new gameplay plate, feature slice, or milestone step, or when the user mentions 竖切, 板块, or 联调验收.
---

# 竖切作业流

权威：`设计文档/开发计划.md` **§0.5 / §0.0 / §0.7**。

按顺序做，不要整端堆完再对接：

1. **数据模型 / 配置表**（须可后台，或已在后台计划登记该域）
2. **领域逻辑 + 单测**（`services/` + `domain/`；协议值进 `constants/`）
3. **HTTP 或 WS 接口**
4. **前端页面 / 组件**（中文、稀有度、物品格契约）
5. **联调 + 自检**
6. 通过则更新 `CHANGELOG.md`、`README.md`（若启动/环境变量有变）；消化项同步 `设计文档/后续待完成.md`
7. 本任务新建应跟踪文件：`git add`（不擅自 commit）

## 结束前自检

- 运营加一条同类内容，能否只改数据、玩家端无发版生效？
- 非编码同事能否靠表格+中文列头改？会 coding 的能否走 JSON？
- 关掉英文注释，玩家能看到的字符串是否还有裸英文 id？
- 玩家能否看到有效数值和来源（或 catalog 占位）？预览是否与结算一致？
- 若有检定/随机：是否走 `DiceService`？
- 若有新活动：是否挂 `PlayGate.assert_activity`？
- `git status` 是否还有本任务产生的应跟踪 `??`？
