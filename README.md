# Project修仙

偏挂机的修仙题材 Web 游戏（Vue 3 + Python FastAPI）。玩法见 `project修仙.md`，排期见 `开发计划.md`。

## 文档

| 文档 | 说明 |
| --- | --- |
| [project修仙.md](./project修仙.md) | 游戏设计文档（GDD）**v4.1**（§3.3 雷劫仅跨境；§11 灵宠指针 → 灵宠系统设计） |
| [后台管理系统开发计划.md](./后台管理系统开发计划.md) | **后台细则**（**v1.3.3** 双写表格+JSON · 字段中文 · `/management`）；与主计划 **§0.0.1** 同步 |
| [开发计划.md](./开发计划.md) | 分里程碑开发计划（**v3.2**：§1.2 延后项计划队列 · 下一主线 **M8** · §0.6.2 属性 · M0～M13 · ADM） |
| [后续待完成.md](./后续待完成.md) | **开新设计前必读**：延后项登记册（钩子/笔记）；阶段归属见开发计划 **§1.2** |
| [四象禁制与环境天气载荷设计.md](./四象禁制与环境天气载荷设计.md) | **M3-D07**：禁制子类 / 环境·天气战斗载荷 / 战报中文；**v1.1.1 已落地**（载荷与 LOS 已解耦） |
| [异步真读条突破设计.md](./异步真读条突破设计.md) | **M5-D05 / M1-D20**：可选闭关读条；**v1.2 默认关闭**——点击同步出结果（2026-08-10） |
| [灵宠系统设计.md](./灵宠系统设计.md) | **灵宠细则**（热插拔注册表/品阶/词条/技能/被动/喂养/野外捕获/回合制对战/灵兽宗改类型/蛋孵）；**v2.1**（2026-08-07 · **N4/N5 + PET-D01～D06 + M4-D04c 已落地**） |
| [化身系统设计.md](./化身系统设计.md) | **化身细则**（**单化身** · 境界功能解锁 · 体力/日行动 · 互传折扣 · 独战/探索/任务）；**v1.1**（2026-08-07 · **AVATAR-D01～D06 + ADM 已落地**） |
| [阵法部署与自研设计.md](./阵法部署与自研设计.md) | **阵法部署契约**（`deploy` 四模式 / 地形 brush 定稿 / `force_shifts` / ADM+自研同 schema）；**M3-D08 Phase A 已落地**；M8 自研 UI 待做；**v1.1**（2026-08-10） |
| [嘲讽光环设计.md](./嘲讽光环设计.md) | **嘲讽光环** Phase A 已落地；Phase B=**M3-D06b** 挂 M3-D03；**v1.1.2**（2026-08-10） |
| [M0工程骨架设计.md](./M0工程骨架设计.md) | **M0** 框架与接口字段详细设计 |
| [M0前端目录与路由设计.md](./M0前端目录与路由设计.md) | **M0** 前端 `src` 目录职责与路由对照（2026-07-27） |
| [M1核心循环设计.md](./M1核心循环设计.md) | **M1** 挂机 / 突破 / 极简战斗详细设计（2026-08-03） |
| [M1前端目录与路由设计.md](./M1前端目录与路由设计.md) | **M1** 大厅内面板落点（无新路由）（2026-08-03） |
| [M2成长深度设计.md](./M2成长深度设计.md) | **M2** 三向挂机 / 离线帽 / 分配 / 体质 / 品阶详细设计（2026-08-04） |
| [挂机速率与加成设计.md](./挂机速率与加成设计.md) | **挂机速率**：境界基础表 × 内外部加成；`idle.yaml` / `idle_env` 拆解（2026-08-06） |
| [骰子系统设计.md](./骰子系统设计.md) | **修为检定骰**：YAML 查表上下限 + 动态修正；突破/战斗/双修统一框架（2026-08-06） |
| [M2前端目录与路由设计.md](./M2前端目录与路由设计.md) | **M2** 大厅面板与对话框落点（仍无新玩法路由）（2026-08-04） |
| [M3战斗成型设计.md](./M3战斗成型设计.md) | **M3** 现行已落地设计（S1～S6）；**v1.5**；延后见 `后续待完成` M3-D01～D10（2026-08-05） |
| [M3自动移动攻击算法设计.md](./M3自动移动攻击算法设计.md) | **M3** 默认 AI；**v2.5**：友军软墙绕行 + 让路；现行 vs 延后分界；Tier B/最小 LOS/零保留 |
| [M3前端目录与路由设计.md](./M3前端目录与路由设计.md) | **M3** 新增 `/formation` `/battle`；大厅变枢纽（2026-08-04） |
| [M4双线程成长设计.md](./M4双线程成长设计.md) | **M4** 化身双挂机 / 工坊配方 / 灵宠雏形 / 神识骨架；N4 收窄出口（2026-08-05 / 07） |
| [M4前端目录与路由设计.md](./M4前端目录与路由设计.md) | **M4** 新增 `/avatar` `/workshop` `/pets`；大厅双线程入口（2026-08-05） |
| [M5环境与轮回外环设计.md](./M5环境与轮回外环设计.md) | **M5** 六时/天气/雷劫（**仅跨境**+准备格+劫云）/待引渡与轮回强化；竖切 E1～E6；**v1.5**（2026-08-10 · 切段算力 + 中文出口） |
| [M5前端目录与路由设计.md](./M5前端目录与路由设计.md) | **M5** `/tribulation` `/reincarnation` + 时辰天气顶栏；新生商店/轮回袋；**v1.5**（2026-08-10） |
| [M6大道与道主设计.md](./M6大道与道主设计.md) | **M6** 开道/道池/道值运用、WS 基建、道主空位自动就任、**道主之争赛会定案**（§5 / M6-D06）；竖切 **W1～W6**；**v1.1**（2026-08-10） |
| [M6前端目录与路由设计.md](./M6前端目录与路由设计.md) | **M6** `/dao` `/dao-lord` + `src/ws`；赛会 mode 预告；**v1.1**（2026-08-10） |
| [M7宗门社交与经济设计.md](./M7宗门社交与经济设计.md) | **M7** 宗门/交易/邮件/多频道聊天/传承/师徒/双修/商业化壳；竖切 **L1～L8**；**v1.0**（2026-08-11） |
| [M7前端目录与路由设计.md](./M7前端目录与路由设计.md) | **M7** `/sect` `/market` `/social` `/friends` `/party` `/dual-cultivation` `/shop` + ChatDock；**v1.0**（2026-08-11） |
| [ATTR战斗属性占位设计.md](./ATTR战斗属性占位设计.md) | **ATTR-D01 已落地**：统一战斗+生活属性 schema、实体适用面、叠层与面板拆解；**M13=填数不改键**；**v1.3**（2026-08-13） |
| [玩家在线状态设计.md](./玩家在线状态设计.md) | **Presence**：WS 鉴权在线 / grace / 组队·面交·助战门闸；**v1.0**（2026-08-12） |
| [核验与超级密码设计](./docs/superpowers/specs/2026-07-28-verification-super-password-design.md) | 注册核验 / verification API / 超级密码（**已实现**，2026-07-28） |
| [核验与超级密码实现计划](./docs/superpowers/plans/2026-07-28-verification-super-password.md) | 分任务实现清单 |
| [测试更新指令.md](./测试更新指令.md) | **测试服更新/重启**：conda + screen + Nginx（8080/8100）；完整更新与按改动范围精简步骤 |
| [CHANGELOG.md](./CHANGELOG.md) | 变更记录 |

## 当前进度

- **前端生产构建**：`cd frontend && npm ci && npm run build`（`vue-tsc -b && vite build`）在 2026-08-12 已通过类型检查修复后可完整产出 `dist/`
- **ATTR-D01 已落地（2026-08-13 · v1.3）**：[`ATTR战斗属性占位设计.md`](./ATTR战斗属性占位设计.md)——`combat_attrs.yaml` / `build_combat_attrs` / `AdditiveSource` 叠层封装 / 大厅分栏；道友卡键统一 `magic_atk`；装备喂入 → ATTR-D02（M8）；满曲线 → M13
- **玩家在线状态 Presence 已落地（2026-08-12）**：[`玩家在线状态设计.md`](./玩家在线状态设计.md) **v1.0**——`PresenceService` + Hub 索引/grace；组队/面交/助战/道友/赛会共用；`presence.changed` 推送；多 worker → **PRESENCE-R01**
- **M7 已收口（2026-08-13）**：L1～L8 + V+ + 打磨包（真正坊市、大厅导航、社交交易/双修/师徒等）；`scripts/smoke_m7.py`；设计见 [`M7宗门社交与经济设计.md`](./M7宗门社交与经济设计.md)；延后见 [`后续待完成.md`](./后续待完成.md) **CHAT-D03** / **M7-D***
- **M7 L1～L8 已落地（2026-08-11）**：宗门 + 道友/交易 + 邮件（附物发信，原赠送并入）+ 五频道聊天/ChatDock + **机缘**（原聊天红包）+ 师徒/真引渡 + 双修/四榜 + 会员/天道商店沙盒
- **M7-V+ 宗门深化（2026-08-12）**：九档宗门等级 + 十二档职位/任命 + 十设施可玩骨架；建宗须专精；战入口占位 → M11；矿脉被动入库+采矿挂机；灵药园兑换/托管；大阵兑换上缴与加点
- **M7 前端**：`/sect` `/market` `/friends` `/party` `/social` `/dual-cultivation` `/shop`；创角必选性别；ChatDock（世界等）+ **DmDialog 私聊弹窗**；组队在队伍页；`HallSocialGate`
- **M6 大道 / 道主 / WS + 打磨包已收口（2026-08-11）**：W1～W6 + **M6-D06** + 收尾包；延后见 **M6-D01～D05、D07**
- **M6 前端已接路由（2026-08-10）**：`/dao` `/dao-lord`；`src/ws` + `WsStatusBadge`；大厅 `HallDaoGate`；战斗/工坊 `use_dao`
- **ADM 后台骨架已落地（2026-08-07）+ 深化 v1.3.3**：同端口 `/management`；**境界/挂机/修为骰表格+JSON 双写**与字段中文说明（§0.0.1）；细则 [`后台管理系统开发计划.md`](./后台管理系统开发计划.md) **v1.3.3**
- **M5 前后端均已落地（2026-08-06）+ 强化/优先打磨收口（2026-08-07）+ 横切打磨（2026-08-10）**：竖切 **E1～E6** + 轮回强化 + **D10～D12 / 幂等 / 开战修为×环境**；**§0.0.2 玩家可见中文**、切段 env 缓存、DB 复合索引见开发计划 **§0.6.1**
- **M5 轮回页修复（2026-08-06）**：对齐 ferry/preview/logs 响应契约；回大厅、待引渡倒计时、祭坛预览、流水/阅历可正常使用（详见 CHANGELOG）
- **M4 前后端均已落地（2026-08-05）**：T1～T6——化身/工坊/灵宠/神识；前端 `/avatar` `/workshop` `/pets` + `HallDualThreadGate`
- **灵宠愿景 + N4/N5/PET-D01～D06/M4-D04c 落地（2026-08-07）**：[`灵宠系统设计.md`](./灵宠系统设计.md) **v2.1**；真地图 region → M9
- **化身定案 + 深化落地（2026-08-07）**：取消多化身；[`化身系统设计.md`](./化身系统设计.md) **v1.2**；**AVATAR-D01～D06 + 域 `avatar` ADM** 已落地；**OOP/减负**：CapabilityIndex 预计算、体力脏写、`get_summary` 轻量摘要
- **异步真读条突破已落地后默认关闭（2026-08-10）**：[`异步真读条突破设计.md`](./异步真读条突破设计.md) **v1.2**——玩家点击突破同步出结果；`async_channel` 可运营再开；API `/breakthrough/channel/*` 保留
- **四象加深 M3-D07 Phase A 落地（2026-08-10）**：[`四象禁制与环境天气载荷设计.md`](./四象禁制与环境天气载荷设计.md) **v1.1**——禁制三子类 LOS；迷雾/雷暴 combat 载荷；战报中文；样本金锁障·咒缄幕·万缄障
- **阵法部署 M3-D08 Phase A 落地（2026-08-10）**：[`阵法部署与自研设计.md`](./阵法部署与自研设计.md) **v1.1**——`deploy` 四模式 / `force_shifts` / presets `effective_deploy_cells` / 前端换阵高亮；样本 wide_front·cloud_drift·left_wing_mask·shift_gust
- **嘲讽光环 M3-D06 Phase A 落地（2026-08-10）**：[`嘲讽光环设计.md`](./嘲讽光环设计.md) **v1.1**——静态 `taunt_auras` / 进入触发 / 决策短路 / 死亡解除 / 样本 `taunt_guardian` / ADM 域
- **延后/并行项**：总表见 [`开发计划.md`](./开发计划.md) **§1.2**；细则钩子见 [`后续待完成.md`](./后续待完成.md)（M3 §1.5 · M4 §1.6 · M5 §1.7 · M6 §1.11 · M7 §1.12 · ATTR/CHAT/IDLE/DICE）
- **扩展层已排期（开发计划 v3.2）**：~~M6~~ / ~~M7~~ → **下一主线 M8**（自研 + ATTR-D02）→ M9～M13；新功能须遵循 **§0.7 显性设计**、**§0.0 后台适配**、**§0.0.2 中文信条** 与 **§0.6.2 属性路线**
- **M7 L1～L8 已收口**（含 V+ 与打磨包）；后端测试含 M0～M7 + ADM；冒烟 `smoke_m3` / `smoke_m4` / `smoke_m5` / `smoke_m6` / `smoke_m7` / `smoke_adm`
- **后端 OOP 分层**：见下方「后端架构」

## 后端架构

分层约定（依赖方向单向向下）：

```
api/            # 玩家薄路由：Depends 注入服务类
admin_api/      # 运营后台路由：/admin/*（独立 JWT）
services/       # Application Service（__init__(session)）用例编排
config_source/  # M2-D01：共享 YamlConfigSource（mtime 缓存）+ OverlayStore + RuntimeConfigReloader
admin_spa.py    # AdminSpaHost：同端口 /management；assets immutable 长缓存
domain/         # 无 IO 纯规则与值对象（SettleResult / CombatCalculator 等）
core/           # Settings / JWT（玩家+后台）/ time_utils / deps 工厂
db/             # ORM（含 admin_users / config_*）+ bootstrap
schemas/        # HTTP DTO（Pydantic）
```

| 概念 | 说明 |
| --- | --- |
| 应用服务 | 如 `IdleService` / `AuthService` / `AdminConfigService`（组合 `AdminEntryEditor`）/ `PlayGate`；路由经 deps 注入 |
| 跨玩法门禁 | `PlayGate`：加载角色 + 自动 claim 离线 pending |
| 配置热更 | YAML ∪ 已发布覆盖 → `GameConfigBundle`；发布走 `RuntimeConfigReloader` |
| 后台 SPA | `AdminSpaHost` 托管 `/management`（与 API 同端口） |
| 核验 Provider | `SmsProvider` / `EmailProvider` / `IdentityProvider` |
| 时间工具 | 全站唯一 `app.core.time_utils` |
| 展示中文 | `domain/display_labels.py` + 配置 `label_zh`；战报/UI 禁止裸英文 id（§0.0.2） |
| 切段 settle | `idle_segments.memoize_env_resolve` + `IdleService._make_segment_env_resolver` |
| 索引补齐 | `db/bootstrap._ensure_performance_indexes`（与 ORM `__table_args__` 对齐） |
| DEV GM | `/api/v1/gm/*` **仅联调**；正式改数走 `/admin` |
| 兼容包装 | 各 service 模块底部仍保留同名函数，便于旧测试与脚本 import |

**详情对照**：各 `M*` 设计 §分层 · [`开发计划.md`](./开发计划.md) §0.6 · [`后台管理系统开发计划.md`](./后台管理系统开发计划.md)

## 环境要求

- Node.js 20+（已用 npm）
- Python 3.11+（当前本地可用 3.12；生产目标仍按设计 3.11）

## 本地运行

### 1. 后端（数据库 + 鉴权）

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
# 首次：pip install -r requirements.txt
# 复制环境变量：copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- **CORS**：玩家端 `5173`（见 `backend/.env.example`）；运营后台与 API **同端口**，走 `/management`，一般无需再开 5174
- **ADM 环境变量**（可选）：`ADMIN_JWT_SECRET_KEY`、`ADMIN_BOOTSTRAP_USERNAME`/`PASSWORD`（默认 `admin`/`admin123`）
- 健康检查：`GET http://127.0.0.1:8000/api/v1/server/health`（或兼容路径 `GET /health`）；`data.db` 应为 `ok`
- 后台登录页：`http://127.0.0.1:8000/management/`（须先 `cd admin && npm run build`）
- 后台 API：`POST http://127.0.0.1:8000/admin/auth/login` Body `{"username":"admin","password":"admin123"}`
- **道主运营**：`/management/ops/dao-lords` — **立刻开赛**、**跳过等待·进入战斗**、**重新开放报名**、**剔除道主**（侧栏「大道与道主 → 道主运营」）
  - **收口**：无人报名→`cancelled`；有人报名则 RSVP→擂台各轮结束→`settled`（到点 `fight_at` 或点「立刻开赛」关闭报名）
  - **再开赛**：须 `registration`；自然为下一业务日新开；联调点「重新开放报名」清空本场后再「立刻开赛」
  - 「立刻开赛」进入 RSVP/擂台分阶段；玩家 `/dao-lord/arena`
  - **跳过等待**：RSVP/擂台进行中可点「跳过等待 · 进入战斗」（`POST /admin/ops/dao-contests/advance-arena`），跳过入席确认/倒计时/整备/轮间/直播倒计时并推进至对战演出；可连点跳过本场演出进入下一轮
  - **RSVP**：默认 **60 秒**确认窗（超时报名弃权 / 道主改快照）；弹窗仅对 `needs_rsvp` 本人；确认提示仅本账号；结束后再等 **30 秒**开第一轮
  - **倒计时**：擂台用 `phase_ends_at` + `server_now` 本地滴答，双端对齐
  - **直播棋盘**：播控由后端 `battle_kind`/`playback_policy` 下发（直播=`dao_contest_live`：强制详细、禁简易/暂停/单步/跳过；回放=`dao_contest_replay`：可播/单步/跳过）；按 `battle_event_cursor` 全服同步；结束后可重播
  - **对战表**：tournament bracket 列序（淘汰→半决→决赛→道主）；按人数动态生成（1 人直进道主战、2 人决赛）
  - **整备改阵**：`can_adjust_loadout` 在 **入席确认 / 开赛倒计时 / 轮间 / 半决整备** 为真；擂台点「调整上阵」进 `/formation?from=dao-arena`（仅此时显示「回擂台」）；日常布阵无该按钮
  - **开打编成**：挑战者互殴 / 道主在线时，**开打瞬间双方现场读取进攻预设+实时战力**并冻结入局（不必依赖手动防守快照）；道主离线/强制快照时道主侧仍用库内防守快照
  - **播报窗**：无棋盘数据不开空抽屉；整备中点对阵只 Toast；直播可关窗再进
  - **离场判负**：仅服务端根据 `playing`/`adjusting` 判定；客户端不可关闭判负；收口后离开不判负；**整备中**一方离场且本阶段场次均已结束时，立刻跳过剩余整备倒计时并推进
  - **安全**：挑战结算禁止客户端指定胜负；核心战报/晋级/席位均服务端权威
- **道主之争日程**：侧栏「大道与道主 → 道主」→ **赛会日程** Tab（报名开始/结束、开打时刻）；保存草稿后须发布（`dao_lord` 域草稿校验已支持）。节奏键：`contest.rsvp_seconds` / `arena_first_round_countdown_seconds` / `round_gap_seconds` / `live_adjust_seconds`
- 侧栏配置按**类目折叠**（灵宠 / 战斗 / 成长…）；类目区与内容区**独立滚动**
- 冒烟：`python scripts/smoke_adm.py`

### 1b. 运营后台前端（ADM）

**推荐（与后端同端口）**：

```powershell
cd admin
npm install
npm run build
# 然后只开后端 uvicorn → 浏览器打开：
# http://127.0.0.1:8000/management/
```

账号默认：`admin` / `admin123`。

**可选（热更新调试 UI）**：`npm run dev` 仍可用 5174，入口为 `http://127.0.0.1:5174/management/`（已代理 `/admin` 到 8000）。

玩家可读设施投影：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/facilities` | 设施开关 + 活动摘要（读 Bundle） |
| GET | `/api/v1/facilities/map/regions` | 地图区域占位 |
| GET | `/api/v1/pets/sect/affix/type-reroll/preview` | 灵兽宗改类型预览（可带 pet_id/slot 报价） |
| GET | `/api/v1/pets/sect/affix/type-reroll/status` | 各槽改类型次数与费用 |
| POST | `/api/v1/pets/sect/affix/reroll-type` | 改词条类型（扣灵石） |
| GET | `/api/v1/pets/hatch` | 孵化面板（蛋+会话） |
| POST | `/api/v1/pets/hatch/start` | 消耗蛋开工 |
| POST | `/api/v1/pets/hatch/{id}/claim` | 领取灵宠入园 |

### 续：玩家鉴权 API

- 注册：`POST http://127.0.0.1:8000/api/v1/auth/register`  
  Body（默认开关全关，最小）：`{"password":"password123","email":"a@b.com"}`  
  若开启对应 `REGISTER_REQUIRE_*`：另需 `phone`+`sms_ticket` / `email_ticket` / `real_name`+`id_card`+`id_ticket`  
  **不再需要用户名**；成功：`201`，`code=0`；邮箱手机占用：`409`/`40013`；缺开关要求的材料：`400`/`40017`
- 登录：`POST http://127.0.0.1:8000/api/v1/auth/login`  
  - 邮箱/手机 + 密码：`{"login_method":"password","account":"a@b.com","password":"password123","remember_me":true}`（`account` 也可为手机号）  
  - 手机 + 短信验证码：先 `POST /verification/sms/send`，再 `{"login_method":"sms","phone":"13800138000","sms_code":"000000","remember_me":true}`  
  成功：`200`，`data` 含 `access_token` / `refresh_token` / `expires_in` / `has_character` / `user`（`email`/`phone`/`display_name`）  
  密码登录亦可使用 `.env` 中 `SUPER_PASSWORD`；禁用账号返回 `40300`
- 刷新：`POST http://127.0.0.1:8000/api/v1/auth/refresh`  
  Body：`{"refresh_token":"<jwt>"}`（响应同登录，含 `has_character`）
- 当前用户：`GET http://127.0.0.1:8000/api/v1/auth/me`  
  Header：`Authorization: Bearer <access_token>`（返回 `email` / `phone` / `display_name` / `has_character`）
- 修改密码：`POST http://127.0.0.1:8000/api/v1/auth/change-password`  
  Body：`{"old_password":"...","new_password":"..."}`（新密码至少 8 位）
- 创建角色：`POST http://127.0.0.1:8000/api/v1/characters`  
  Header：`Authorization: Bearer <access_token>`  
  Body：`{"name":"青柠散人"}`（道号 2～16，中文/字母/数字）  
  成功：`201`，`data` 为完整角色面板（锻体一层、灵石=`INITIAL_SPIRIT_STONES`）；已有角色 `40004`；道号占用 `40003`
- 我的角色：`GET http://127.0.0.1:8000/api/v1/characters/me`  
  Header：`Authorization: Bearer <access_token>`  
  无角色：`404` / 业务码 `40005`（前端应跳转创角页）；**先 `ensure_offline_pending`（短缺口 settle / 长缺口且 WS 离线写 pending；WS 仍在线则带帽直接入账不写 pending）再返回**，含进度 / `is_stalled` / 修正后 `base_atk`/`base_hp` 等衍生字段
- 领取离线：`POST /api/v1/idle/offline/claim`；无 pending → `40031`；灵石不足以支付 pending 消耗 → `40038`

### M1 核心循环 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/idle/direction` | Body `{"direction":"spirit"\|"body"\|"crafting"\|"none"}`；有 pending → `40030` |
| POST | `/api/v1/idle/sync` | 权威入账；有 pending 时冻结在线累计 |
| GET | `/api/v1/idle/offline/preview` | 离线收益预览（幂等生成 pending） |
| POST | `/api/v1/idle/offline/claim` | 领取离线 pending；无 pending → `40031`；灵石不足 → `40038` |
| GET | `/api/v1/breakthrough/preview` | 门槛读 `realm_progress`；可含进行中 `channel` |
| POST | `/api/v1/breakthrough/attempt` | 兼容入口：`async_channel.enabled` 时=开读条，否则同步掷骰 |
| POST | `/api/v1/breakthrough/channel/start` | 开异步真读条（扣灵石、置 `breaking_through`） |
| GET | `/api/v1/breakthrough/channel` | 读条进度；到期懒结算 |
| POST | `/api/v1/breakthrough/channel/resolve` | 显式结算（未到期 409） |
| GET | `/api/v1/breakthrough/grades/history` | 跨境品阶历史 |
| GET | `/api/v1/quench/preview` | 淬体预览（进度 / 主修门槛） |
| POST | `/api/v1/quench/attempt` | 发起淬体（炼体境晋级） |
| POST | `/api/v1/battle/pve` | Body `{"monster_id":"tutorial_slime"}`；返回战报 |
| POST | `/api/v1/allocate` | Body `{"target_type":"realm"\|"body_temper"\|"technique","target_id":"...","amount":N}`；炼体功法自动扣淬体度池 |
| GET | `/api/v1/techniques/me` | 角色功法等级列表 |
| GET/POST | `/api/v1/constitution/*` | 体质背包 / 镶嵌 / 卸下 / 升品 / 融合（骨架） |
| POST | `/api/v1/gm/character/set` | 仅 development；支持 `realm_progress` / `clear_offline_pending` 等 |

### M3 战斗成型 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/formation/board-meta` | 棋盘只读元数据（尺寸 / 三区 / 默认部署格 / 镜像规则 / 种类闸门） |
| GET | `/api/v1/formation/presets` | 预设三槽 + 已解锁阵法 + 可上阵棋子（Bench）+ 上阵上限 |
| PUT | `/api/v1/formation/presets/{slot}` | 保存预设：`{name, role, formation_id, units}`；非法占位 `40041/40042/40043` |
| POST | `/api/v1/formation/validate` | 干跑校验占位（编辑器即时反馈，不落库） |
| GET | `/api/v1/snapshot/defense/me` | 我的防守快照摘要（触发每日定点**惰性**补刷） |
| POST | `/api/v1/snapshot/defense/update` | 手动更新快照；冷却中 `40045`；状态禁止 `40046` |
| GET | `/api/v1/snapshot/defense/{character_id}` | 攻打前预览目标快照；无快照 `40048` |
| POST | `/api/v1/battle/pve` | `{monster_id, preset_slot?}`；棋盘化演算，**响应即完整战报**；体力不足 `40049` |
| POST | `/api/v1/battle/pvp/attack` | `{target_character_id, preset_slot?}`；攻打对方快照（对方零打扰）；打自己 `40047` |
| GET | `/api/v1/battle/pve/monsters` | 可挑战怪列表（含体力消耗与编成规模） |
| GET | `/api/v1/battle/pvp/opponents` | 可攻打对手列表（M3 占位匹配） |
| GET | `/api/v1/battle/stamina` | 体力读数（惰性恢复后）：`{left, cap, next_point_in_seconds, regen_per_minute}` |

战报结构：响应顶层含 `battle_kind` + `playback_policy`（播控权威）；`data.report` 为 `{schema_version, seed, winner, rounds, board_text, summary, detailed_log, events}`。服务器**零保留**，无任何 `GET /battle/reports*` 端点。种类矩阵见 `backend/app/domain/battle_presentation.py`（`exploration` / `dao_contest_live` / `dao_contest_replay`；`duel`/`raid_boss` 占位同探索）。先攻事件按行动序交错写入（【先攻】→该单位移动/攻击），不在回合开头批量刷屏。

M3 GM 扩展（`POST /gm/character/set` 新增可选字段）：`set_stamina` / `trial_puppet_count` / `reset_snapshot_cooldown` / `force_refresh_snapshot`。

### M4 双线程成长 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/avatar/me` | 化身面板；含 `features`/`stamina`/`unlock_preview`；未凝练 `data=null` |
| GET | `/api/v1/avatar/features` | 功能解锁看板 + 下一档预告 + **`condense` 权威闸**（`can_condense`/`realm_ok`/`stones_ok`/`block_*`；与 POST 同源） |
| POST | `/api/v1/avatar/condense` | 凝练化身（金丹**及以上**门槛 `40050`，含真仙；已有化身 `40051`；灵石不足 `40000`；UI 闸读 `/features.condense`） |
| POST | `/api/v1/avatar/idle` | Body `{"direction":"spirit"\|"body"\|"crafting"\|"sect_mining"\|"none"}`；采矿需入宗且计入矿脉名额；未解锁方向 `40090` |
| POST | `/api/v1/avatar/transfer/preview` | 互传预览（gross/net/retention；不扣池） |
| POST | `/api/v1/avatar/transfer` | 互传实扣；回包含 gross/net/fee |
| GET | `/api/v1/avatar/sense` | 神识读数（capacity/load/soft/hard/zone/overload_mult/backlash） |
| GET | `/api/v1/avatar/explore/status` | 探索代理桩（化神+） |
| POST | `/api/v1/avatar/quests/accept` | Body `{"quest_kind":"npc"\|"sect"}`；未解锁 `40090`；解锁后桩 `50110` |
| POST | `/api/v1/avatar/assist/settings` | Body `{"enabled":bool}`；**化身页**开关「化身助战」（关=闭关）；化神 `friend_assist` |
| POST | `/api/v1/avatar/assist/invite` | Body `target_character_id` 或 `target_name`；**邀请化身**：开则立即入队；关→「闭关中」；忙→「助战中」 |
| POST | `/api/v1/avatar/assist/{id}/accept\|reject\|end` | 兼容旧 invited / 手动结束；PVE 战后自动离队 |
| GET | `/api/v1/avatar/assist/me` | 助战会话 + 开关 + **助战专用体力**（独立槽，仅随境界变容） |
| GET | `/api/v1/craft/recipes` | 配方列表（五分支） |
| GET | `/api/v1/craft/jobs` | 工坊队列 |
| POST | `/api/v1/craft/start` | Body `{"recipe_id":"...","actor":"main"\|"avatar"}` |
| POST | `/api/v1/craft/claim` | Body `{"job_id":N}` |
| GET | `/api/v1/inventory` | 背包列表 |
| POST | `/api/v1/inventory/use` | 使用消耗品（如体力丹） |
| GET | `/api/v1/pets` | 灵宠列表（含种族/稀有度/品阶/词条） |
| GET | `/api/v1/pets/catalog` | 图鉴（注册表投影 + seen/caught） |
| POST | `/api/v1/pets/capture_test` | 测试捕获（加权物种+品阶+填槽词条；可选 `species_id`） |
| POST | `/api/v1/pets/{id}/upgrade` | 升级占位 |
| POST | `/api/v1/pets/{id}/grade-up` | 升阶（扣灵石；+1 槽随机词条） |
| POST | `/api/v1/pets/{id}/affix/reroll-value` | 数值-only 洗炼（Body `slot_index`） |
| POST | `/api/v1/pets/{id}/feed` | 丹药喂养（Body `item_id`/`quantity`；超限 40066） |
| GET | `/api/v1/pets/explore/preview` | 野外遭遇池预览（区×时×天） |
| POST | `/api/v1/pets/explore/encounter` | 掷遭遇（Body `region_id`/`seed?`） |
| POST | `/api/v1/pets/explore/capture` | 野外捕获（诱灵草；审计 `p/factors/roll/seed`） |
| POST | `/api/v1/pets/explore/auto` | 自动探索捕 |
| POST | `/api/v1/pets/{id}/skills/equip` | 装备最多 4 技能（Body `equipped`） |
| POST | `/api/v1/pets/{id}/skills/learn` | 物种池领悟（Body `skill_id`） |
| POST | `/api/v1/pets/{id}/skills/learn_book` | 消耗技能书（Body `book_id`） |
| POST | `/api/v1/pets/duel/npc/start` | vs NPC 开战（Body `pet_id`/`seed?`） |
| POST | `/api/v1/pets/duel/npc/auto` | vs NPC 自动打完（seed 可复现） |
| POST | `/api/v1/pets/duel/{id}/turn` | 提交选招结算一回合 |
| GET | `/api/v1/pets/duel/{id}` | 对战快照 |
| PATCH | `/api/v1/pets/{id}` | 昵称 / 偏好上阵 |
| GET | `/api/v1/formation/bench` | 可上阵棋子源（本体/化身/灵宠/傀儡/道友客串化身） |

M4 GM 扩展：`force_jindan` / `grant_craft_materials` / `grant_test_pet` / `clear_craft_jobs` / `divine_sense_capacity_bonus` / `clear_divine_sense_backlash` / `array_craft_level`。

M3 冒烟：`python scripts/smoke_m3.py http://127.0.0.1:8000/api/v1`（注册→布阵→快照→PVE→PVP）。  
M4 冒烟：`python scripts/smoke_m4.py http://127.0.0.1:8000/api/v1`（金丹→凝练→双挂机→传修为→炼丹→发宠→Bench 快照）。

### M6 大道 / 道主 / WS API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/dao/catalog` `/dao/me` `/dao/pool` | 图鉴 / 本命资源 / 道池 |
| POST | `/dao/open/roll` `/dao/open/choose` | 开道三选一 |
| POST | `/dao/usage/preview` | 运用预览 |
| GET | `/dao-lord/board` `/dao-lord/windows` | 道主榜 / 开窗 |
| POST | `/dao-lord/claim` | 空位自动就任（兼容） |
| GET | `/dao-lord/contests/current` | 本场道主之争状态 |
| POST/DELETE | `/dao-lord/contests/current/register` | 报名 / 取消报名 |
| POST | `/dao-lord/contests/current/rsvp` | 开赛入席确认 |
| GET/POST | `/dao-lord/contests/current/arena*` | 擂台状态 / 进入 / 离开 |
| GET | `/dao-lord/contests/current/bracket` | 对阵树（可选 `dao_id`） |
| GET | `/dao-lord/contests/matches/{id}` | 单场摘要 |
| GET | `/dao-lord/contests/matches/{id}/report` | 战报回放（观众脱敏布阵） |
| GET | `/dao-lord/contests/matches/{id}/live` | 直播时钟：准备倒计时 / 对战节拍 |
| POST | `/dao-lord/contests/matches/{id}/spectate` | 单直播槽观战 |
| GET | `/world-events/current` | Boss/秘境骨架（含 `room_id`） |
| POST | `/world-events/{id}/register` | 骨架报名；进房须 WS `room.join` |
| WS | `/ws` | 鉴权首帧 `auth` / 心跳 `ping` / `room.join`；可收 `world.env` |

M6 GM：`force_true_immortal` / `lock_fate_dao` / `grant_dao_pool` / `set_dao_qi` / `set_dao_level` / `set_dao_lord` / `open_dao_challenge_window` / `clear_dao_challenge_cooldown` / `push_world_env` / **`m6_quick_kit`（一键联调）**。

本地 DEV：将 `backend/.env.example` 中 M6 段（尤其 `DAO_LORD_FORCE_WINDOW=true`、`WORLD_EVENTS_ENABLED=true`）同步进 `backend/.env` 后重启 uvicorn；大厅展开「调参（DEV）」→ **M6 一键联调套装**。

M6 冒烟：`python scripts/smoke_m6.py`（backend 目录、已激活 venv）。

### M7 宗门 API（需 Bearer · L1 + M7-V+）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/sect/me` `/sect/npc` | 我的宗门 / NPC 目录 |
| POST | `/sect/join` `/sect/create` | 拜入 NPC / 自建（`specialty` 必填） |
| GET | `/sect/overview` `/sect/members` | 组织总览 / 门众 |
| POST | `/sect/ranks/apply` `/sect/ranks/appoint` | 晋升申请 / 任命 |
| POST | `/sect/council/salary` `/sect/council/announce` | 日俸 / 公告 |
| POST | `/sect/council/war/start` | 战事占位（→M11） |
| POST | `/sect/grade/upgrade` `/sect/facilities/{id}/upgrade` `/sect/buffs/toggle` | 升等 / 升设施 / buff |
| GET/POST | `/sect/treasury*` `/sect/scripture*` `/sect/workshops/*` | 藏宝阁/藏经阁/工坊 |
| GET/POST | `/sect/formation` · `…/select` · `…/active` · `…/allocate` · `…/exchange` · `…/donate` | 宗门大阵（无管理权仅兑换/上缴；有权可选阵/启停/加点） |
| GET/POST | `/sect/mine` · `…/start` · `…/stop` | 矿脉（被动入库；采矿挂机） |
| GET/POST | `/sect/herbs` · `…/exchange` · `…/plant` · `…/{id}/harvest` | 灵药园（兑换/托管种植/收获） |
| GET/POST | `/sect/quests` · `…/accept` · `…/complete` | 任务殿 |
| GET/POST | `/sect/shop` · `/sect/shop/buy` | 贡献商店（兼容） |
| GET | `/sect/soul-lamps` | 魂灯 |
| GET/POST | `/sect/exchange/catalog` · `/sect/exchange/pet` | 兑宠 |

前端：`/sect`（`mode=join|overview|council|quests|treasure|scripture|forge|alchemy|talisman|formation|mine|herbs|shop|lamps|exchange`）；大厅顶栏「宗门」。

### M7 L2 道友与坊市 / 拍卖行 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/friends` · `…/{id}/accept` · `…/reject` · `DELETE …/{id}` | 道友列表（修为/真实在线/可邀化身）/ 申请 / 确认 / 拒绝 / 解除；WS `friend.request`（拜帖）· `friend.update`（同意/拒绝） |
| GET/PUT | `/friends/privacy` | 本人是否允许道友查看资料 |
| GET | `/friends/profile/{character_id}` | 查看道友资料（在线实时 / 离线快照；遮掩 `40130`） |
| GET | `/trade/bazaar` | **真正坊市**：NPC 固定货架 + 可回收摘要 |
| POST | `/trade/bazaar/buy` · `/trade/bazaar/sell` | 灵石购买 / 按收购价出售（仅普通袋；绑定物拒绝） |
| GET/POST | `/trade/listings` · `…/{id}/buy` · `…/cancel` | 拍卖行·一口价 |
| GET/POST | `/trade/auctions` · `…/{id}/bid` | 拍卖行·竞拍 |
| POST/GET | `/trade/face` · `GET …/pending` · `GET …/invite-options` · `…/{id}` · `…/accept` · `…/reject` · `…/offer` · `…/lock` · `…/confirm` · `…/cancel` | 社交交易（邀约提交后推送；页内待接受列表即时出现→锁定→确认；点通知先拉会话再进页手动接受）；道具格同邮件 72px；报价自动同步；改草稿不拆对方锁定；WS `session` 为接收方视角；`vessel_offer.hours`；单侧最多 16 种；WS `face.invite`/`face.update` |

前端：大厅顶栏 **社交**（`/social`：道友关系/队伍/双修/**交易**/邮件/师徒/引渡）· **商店**（`/shop`：`mode=bazaar|auction|tiandao`）；另有 **化身**（`/avatar`，挂机含采矿）· **账号**（`/account`：资料/改密/退出）；修炼区标题行「资源分配/进阶」入口弹窗；`/market` 为拍卖行独立入口（`mode=listings|auction`，旧 `face` 深链重定向社交交易）；`/friends` `/party` `/dual-cultivation` 深链保留。道友页为单页分区：我的道友/道侣/炉鼎；若自身为他人炉鼎则显示「我的主人」（含到期时间）。交易可要约「愿为对方炉鼎」并设现实小时；双方至多一侧；**互为道侣不可互为炉鼎**（道侣仍可为他人炉鼎）；主人可随时解除，到期自动解除。大厅日志下方有**邀请列表**；社交页操作日志同步进大厅事件日志；右上角 WS 邀请提示可点击跳转对应社交子页（交易/组队/双修/道友/道侣）。

### M7 L3 邮件 API（需 Bearer；原赠送已并入发信）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/mail` | 收件箱（含 `limits`：附件种类上限等） |
| GET | `/mail/compose-options` | 道友/同门/弟子快捷名单与群发权限 |
| POST | `/mail` | 发信；可附灵石/道具；`broadcast=sect\|disciples` 群发 |
| POST | `/mail/read-all` · `/mail/claim-all` · `/mail/delete-all` | 一键已读 / 领取（后标已读）/ 删除（须已读且附件已领） |
| POST | `/mail/{id}/read` · `/claim` · `/delete` | 单封已读 / 领取 / 删除 |
| POST | `/gifts` | **已弃用**，兼容转发到附物发信 |

配置（`mail.yaml` / ADM 域 `mail`）：`max_attachment_lines`（默认 **6**）、`sect_broadcast_min_rank_order`（掌门=9）、`broadcast_max_recipients`；单种道具数量不得超过最大堆叠。附物单发默认须道友；宗门群发仅掌门及以上；弟子群发仅师傅。

前端写信台：右侧 **道友/宗门/弟子** 弹窗选人、**背包** 点选入固定附件栏；可堆叠物品弹出数量窗（魔兽发信交互）。

环境变量：`SECT_SYSTEM_ENABLED` / `FRIENDS_SYSTEM_ENABLED` / `TRADE_SYSTEM_ENABLED` / `MAIL_SYSTEM_ENABLED`（后端；默认开）。

### M7 L4 聊天与队伍 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/chat/channels` | 可进频道（含锁定原因/未读；`dm_persistent` / `dm_history_limit`） |
| GET | `/chat/history` | 短历史（`channel_ref`；私聊上限 `dm_history_limit`） |
| POST | `/chat/send` | 发送（鉴权/限速/敏感词；私聊发送后裁剪最旧） |
| POST | `/chat/read` | 清零频道未读 |
| POST | `/chat/dm/clear` | 清空某私聊会话全部历史（双方） |
| GET/POST | `/party/me` · `/party/invite-options` · `/party` | 当前队伍/团队（`kind`·人数上限·`pending_invites`·`outgoing_invites`）/ 快捷邀请名单 / create·invite·accept·reject·leave·kick·**convert_to_team**·**convert_to_party**（邀请 60s 超时；队伍≤5，团队≤40；≤5 人可转回队伍） |

WS：订阅 `chat:{channel_ref}`，推送 `chat.message` / `chat.unread` / `chat.dm.cleared`；组队另推 `party.invite` / `party.update`。关 `CHAT_WS_PUSH_ENABLED` 时前端轮询 history。

前端：玩法壳横切 `ChatDock`（世界/宗门/师承/队伍；组队管理在 `/party`）；**私聊独立 `DmDialog`**（道友入口 / 坞未读角标）；私聊服务端持久最近 N 条；非私聊仍会话级缓存；世界/宗门可发机缘；大厅提示道友/组队/面交规则。玩法壳内 WS 为长连接（切页保活，登出/离开玩法壳才断）；大厅「正在连接仙界…」仅本会话首进一次。

`chat.yaml`：`dm_history_limit` / `session_ephemeral` / `party_require_friend` / `party_invite_expire_sec` / `party_dev_assume_online`（仅 development）。

环境变量另加：`CHAT_SYSTEM_ENABLED` / `CHAT_WS_PUSH_ENABLED`。

### M7 L5 机缘 API（需 Bearer；机读路径仍为 `/heritage`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/heritage?channel_ref=` | 频道内进行中机缘包 |
| POST | `/heritage` | 发机缘（`mode=random\|fixed`；灵石或非绑定非唯一可交易物品） |
| POST | `/heritage/{id}/claim` | 开缘领取（非成员/领完/过期 → 40140） |

WS：`heritage.created` / `heritage.claimed` / `heritage.expired`（随聊天房广播）。过期未领默认退系统邮件。前端 ChatDock「机缘」从背包点选物品，禁止手填 id。**已抢完**本会话仍可见（默认保留 20 条，`session_finished_keep`）；退出/关浏览器清空；未抢完重进仍拉回。purge 已结束包时同步删除领取行（并启用 SQLite 外键），避免 id 复用后误报「你已开过这份缘」。

环境变量：`HERITAGE_SYSTEM_ENABLED`；`HERITAGE_EXPIRE_SEC`（0=读 YAML）。

### M7 L6 师徒与真引渡 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/mentor/me` | 师徒键 / 任务 / 日课与传授状态 / 可授选项 / 师承频 |
| POST | `/mentor/apply` | 拜师或收徒（师傅须至少高徒 1 个大境界） |
| POST | `/mentor/{id}/accept` · `/reject` | 确认 / 拒绝 |
| POST | `/mentor/quests/{quest_id}/progress` | 推进师徒任务 |
| POST | `/mentor/lesson` | 日课三选一：传道 `dao` / 授业 `craft` / 解惑 `technique`（每日一次） |
| POST | `/mentor/teach` | 传授功法或配方图纸（每日一次，按阶梯累计多日） |
| POST | `/mentor/study` | 徒弟请学师傅功法（每日一次；可叠加未学完的同种传授进度） |
| POST | `/mentor/direct` | 师傅设置亲传弟子（最多 3 人；可含已出师） |
| POST | `/mentor/pass` | 兼容旧传功（等价传道·修为） |
| POST | `/mentor/graduate` · `/dissolve` | 出师 / 解除（弟子追上师傅大境界会自动出师） |
| POST | `/ferry/rescue` | 普渡/同门/亲友引渡（救援者支付；`mode=friend\|sect\|kin`） |
| GET | `/ferry/rescue-targets` | 救援名单（`category=universal\|sect\|kin`：普渡众生道友 / 同门 / 亲友） |

日课数值：`min(弟子当前档突破需求×100%, 师傅对应资源池×10%)`。传授天数见 `mentor.yaml` `teach.sessions_by_tier`（低阶约 1 日，高阶 7～10 日）。徒弟请学见 `mentor.yaml` `study`（默认每日 1 次、进度 +1）。亲传见 `direct_disciple`：授业/解惑日课 +1，传授不变；指定后隔日可解除、解除当日不可再指定；出师自动解除亲传。`GET /mentor/me` 含 `lineage` 师承单（大/二/三弟子，已出师标注）。师傅传授时徒弟在线收 WS `game.log`，离线写入 `pending_event_logs`，领取离线收益时可见；无离线 pending 时用 `POST /characters/me/event-logs/ack` 确认清空。

`GET /ferry/me` 含 `social_rescue` 成本对照（非待引渡也可读）。同图判定默认 `SAME_REGION_STUB=true`（真地图 → M9）。

前端：`/social?mode=mentor|ferry`（师徒面板含师承单/亲传/日课/传授/徒弟请学；引渡页三类：普渡众生 / 同门引渡 / 亲友引渡）；社交操作日志同步写入大厅事件日志；待引渡页「去求援」跳转社交引渡；ChatDock 师承解锁。

环境变量：`MENTOR_SYSTEM_ENABLED`；`SAME_REGION_STUB`。

### M7 L7 双修与时长榜 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/dual/me` | 会话 / 功法 / 性别 / 道侣·炉鼎选人列表 |
| POST | `/dual/set-gender` | 存量一次性补选 `male\|female` |
| POST | `/dual/invite` | 邀约（`technique_id` + `target_character_id` + `bond_kind`；禁止手填道号；WS `dual.invite`） |
| POST | `/dual/{id}/confirm` | 接受邀约 → `accepted`（启动宽衣 60s；道侣可拒，炉鼎不可拒） |
| POST | `/dual/{id}/undress` | 受邀方「宽衣解带」→ `undressed` |
| POST | `/dual/{id}/start` | 邀请方「开始」：扣双方战斗体力 → 高潮循环结算 → `settled` |
| POST | `/dual/{id}/cancel` | 取消（终态）；炉鼎邀约态受邀方不可取消 |
| GET | `/dual/ranks` | 时长榜（默认前 100；主榜 `duration_total`） |
| GET | `/bonds` | 道侣 / 炉鼎列表 |
| POST | `/bonds/companions` | 申请道侣 |
| POST | `/bonds/vessels` | 炉鼎直邀口子（拒绝；请走面交要约） |
| POST | `/bonds/{id}/accept` · `/reject` · DELETE | 道侣确认/拒绝；解除（炉鼎仅主人可解） |

流程：`inviting` → `accepted` → `undressed` → `start` 自动结算。道侣邀约/宽衣 60s 超时取消；炉鼎邀约 60s 自动接受、宽衣 60s 自动宽衣。
功法模式：`mutual_gain` 双增 · `transfer` 传功 · `extract` 索取（蛇蝎：被索取过低初始转化率 0，索取方过低初始为负）。
体力：`stamina_costs`（双增双方相同；传功传方>受方；索取索取方>被索取）；管理后台域 `dual_cultivation` 可改初始设定。
高潮循环由 `climax` 驱动（每轮≈1s±20%）。WS：`dual.invite` / `dual.update`（弹窗点进 `/social?mode=dual`）。
角色摘要/角色页展示战斗体力（`battle_stamina.left/cap`）。

前端：社交双修台「双修台 / 时长榜」；右侧道侣·炉鼎选人；接受 / 宽衣解带 / 开始。

环境变量：`DUAL_CULTIVATION_ENABLED`。

### M7 L8 商业化 API（需 Bearer）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/commerce/me` | 会员摘要 + 天道点 + 币种目录 |
| GET | `/commerce/shop` | 天道商店货架（含禁售本命道边界文案） |
| POST | `/commerce/membership` | 开通/续费 `tier1\|tier2`（耗天道点） |
| POST | `/commerce/shop/buy` | 货架兑换 |
| POST | `/commerce/sandbox/grant-tiandao` | 沙盒加点（`COMMERCE_SANDBOX_ENABLED`） |

会员过期惰性回落 12h 帽；挂机离线结算读有效档。角色字段：`tiandao_points` / `membership_expires_at`。

前端：`/shop?mode=member|tiandao`。

环境变量：`COMMERCE_SYSTEM_ENABLED` / `COMMERCE_SANDBOX_ENABLED`。

冒烟：`python scripts/smoke_m7.py`（道友→世界频→传承→双修双增→会员帽）。

### M5 环境与轮回 API（需 Bearer）


| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/world/calendar` | 当前六时、下一时 ETA |
| GET | `/world/weather` | 默认区天气、下次滚动 |
| GET | `/world/env` | calendar+weather+提示键；含 `catalog`（当前时辰/天气说明）与 `idle_preview`（无角色标签的基础有效速率） |
| GET/POST… | `/tribulation/*` | me / start-prep / prep / commit-prep / veil-check / begin / resolve-batch / auto-resolve |
| GET/POST | `/ferry/*` | me / self-rescue / **rescue** / enter-reincarnation |
| POST/GET | `/reincarnation/*` | preview / altar / logs / newborn / complete-newborn / **shop** / **shop/buy** / **shop/refresh** |
| GET/POST | `/inventory` · `/inventory/move-bag` | 普通袋+轮回袋分栏；移入轮回袋以便来世携带 |

突破默认走**异步真读条**（`async_channel.enabled`）：`POST /breakthrough/channel/start` 扣灵石并置 `breaking_through`，到期懒结算掷骰；`POST /attempt` 为兼容入口。达雷劫门槛时返回 `needs_tribulation: true`（不建读条）。**仅跨大境界**（自元婴→化神起）会分流渡劫；同境内小境界层/期进阶直接升档。

渡劫准备格：放入的道具在 **开渡** 时从背包永久扣除（未开渡可清空格子取回）；进度 100% / 成功后页内可点「确认突破」回大厅。

M5 GM 扩展：`force_shichen` / `force_weather` / `start_tribulation` / `force_tribulation_outcome`（won|failed|fallen）/ `grant_acceptance_constitution` / `set_awaiting_ferry` / `force_ferry_timeout` / `mark_story_node` / `fate_luck` / `demonic_nature` / `force_yuanying_peak` / `spirit_root_tags`。

**环境锁定**：开战、工坊开工在**点击确认那一刻**写入时辰/天气快照；进页面时的预览只是当前世界态，不锁定。任务/战斗进行中世界天气再滚动，不影响本场已锁环境。

角色面板 `CharacterPublic.idle_env`：spirit/body/crafting 有效挂机速率 = **大境界基础表** × 加成通道（体质钩子等）× 时辰×天气×灵根/功法 `env_tags`；`breakdown` 可拆解（含 `realm_base` / `constitution` 等）。细则见 [`挂机速率与加成设计.md`](./挂机速率与加成设计.md)。大厅修炼区默认只显示「基础→有效」与总乘区，乘区拆解与时辰/天气说明悬停旁侧 **i** 查看。

「本周天预计」由前端用 `/world/env.idle_preview` + 角色基础速率与通道拆解在浏览器实时重算（仅展示，权威结算仍在服务端）；时辰/天气切换不再为此单独 `fetchMe`。

`CharacterPublic.activity`：活动互斥快照（`mode` / `can_enter_idle` / `can_start_craft` / … / `blockers`）。规则见开发计划 **§0.8**：修炼中须先停止才能开战/炼丹炼器/突破/渡劫；工坊进行中不可再修炼。

陨落进入 `awaiting_ferry` 时全局弹窗引导「前往轮回与引渡」（可关闭不跳转）。若 `/ferry/me` 报 Network/CORS，先确认后端已重启（naive 截止时间戳已修复）。

**自救**：消耗 **灵石**（默认 500，见 `reincarnation.yaml` `self_rescue.spirit_stone_cost`）；另有冷却（默认 300 秒）。冷却中或灵石不足时按钮禁用并显示原因——第二次快速再死无法自救通常是冷却/灵石，不是接口坏了。

**轮回新生**：入轮回后进入 `reincarnating`，打开 `/reincarnation?mode=newborn`——道号保留；选择灵根 / 免费传承 / 体质倾向；可花轮回点逛商店（固定+随机，可耗点/仙缘刷新）；`POST /reincarnation/complete-newborn` 后回 `normal`。确认前不可进大厅与积极玩法。

**轮回持续变强（数值主配置 `reincarnation.yaml`）**：
- 每次轮回按**历史峰值大境界**叠加永久加成（初始属性 / 小·大突破成长 / 突破成功率），并存入独立表 `character_reincarnation_bonuses`
- **主动祭坛**：须达 **化神期**（`altar.min_major_realm`）；化神以下不可主动入轮回；待引渡自选/超时强制不受此限
- 轮回点 = 境界基础点 × 路径倍率（祭坛/自选 > 死亡强制）
- 功法带 `reincarnatable` 特性可带入；体质全保留但装配槽有上限（初始/轮回次数免费/商店购买，总上限可配）
- 储物袋分**普通袋**（入轮回清空）与**轮回袋**（可带入，容量随轮回次数增大）；平时可用 `POST /inventory/move-bag` 整理
- 轮回商店可买永久属性升级、槽位扩容等；随机商品池可配出现条件

#### 环境说明 catalog（录入新天气/时辰时填写）

在 `backend/app/config_data/calendar.yaml` / `weather.yaml` 的 `catalog.<id>` 下维护玩家可见文案（数值仍走 `modifiers` / `tag_modifiers`）：

| 字段 | 用途 |
| --- | --- |
| `summary` | 一句话总述 |
| `idle_note` | **基础修炼速度**说明（修炼区/大厅提示） |
| `spawn_bias_note` | **妖兽出没喜好**说明（占位，后续刷怪权重可对齐） |
| `craft_notes.<branch>` | **炼丹/炼器/制符/傀儡/阵法**等分支加成说明（`alchemy` / `smithing` / `talisman` / `puppet` / `array`） |
| `breakthrough_note` | 突破相关说明（可选） |
| `tribulation_note` | 渡劫相关说明（天气侧常用） |

灵根写在角色 `spirit_root_tags`（GM 可改）；功法在 `techniques.yaml` 配 `env_tags`。额外乘区写在同文件 `tag_modifiers.<tag>.shichen|weather.<id>.idle_cultivation` 等键下。

M5 冒烟：`python scripts/smoke_m5.py http://127.0.0.1:8000/api/v1`。

玩法数值在 `backend/app/config_data/`（含 M5：`calendar.yaml` / `weather.yaml` / `tribulation.yaml` / `reincarnation.yaml`；挂机 `idle.yaml`；**修为骰 `dice.yaml`**），改 YAML 无需改结算逻辑。各表已带中文字段注释（文件头说明用途与加载时机）。联调可把 `IDLE_TICK_SECONDS=5` 加速挂机。

**挂机灵石**：筑基前（锻体/炼气）每 tick 消耗为 `0`（见 `idle.yaml` `spirit_stone_cost_by_realm`）；筑基起按境界递增。**突破灵石**：筑基前层进阶/锻体→炼气免费；**仅炼气圆满→筑基**扣费（`breakthrough.yaml` `pre_foundation_free`）。**炼体九境**（`realms.yaml` `body_temper_majors`）：炼皮/锻骨为 **1～10 层**，通脉→道体为 **初/中/后/圆满**；对照主修锻体→大乘解锁跨境；挂机涨淬体度池，分配「投入淬体」写入进度，**淬体**（`POST /quench/attempt`）有成功率、失败回退、**不渡劫**；道体 `next_major: null` 为扩境口。与修为突破同栏切换。**轮回结算**会重置阵法预设为默认空阵（`reincarnation.yaml` `carry.formation=reset`），并重置炼体境为炼皮；不保留前世布阵。

检定/先攻/伤害骰一律按 [`骰子系统设计.md`](./骰子系统设计.md)：大境界+小境界查表得默认上下限，再叠功法/体修/气运等修正；`board.dice_sides` 仅作兼容回落。

**M2 环境变量**（见 `backend/.env.example`）：`OFFLINE_CAP_HOURS_FREE` / `OFFLINE_PREVIEW_THRESHOLD_SECONDS` / `ALLOCATE_MIN_UNIT` / `GRADE_RNG_SEED`（仅测试）/ `GM_ALLOWED_USER_IDS`（可选白名单）等。

**M3 环境变量**（见 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `STAMINA_ENABLED` | `true` | 体力门禁开关；`false` 时开战不校验不扣减（联调用），读数仍可用 |
| `BATTLE_MAX_ROUNDS` | `0` | `>0` 时覆盖 `board.yaml` 的回合上限 |
| `SNAPSHOT_MANUAL_COOLDOWN_SECONDS` | `0` | `>0` 时覆盖 `snapshots.yaml` 的手动更新冷却 |
| `SNAPSHOT_LAZY_DAILY_ENABLED` | `true` | 请求路径惰性执行每日定点快照补刷 |
| `AUTOCHESS_RNG_SEED` | 空 | 演算种子；仅测试注入（写入战报便于复现），生产勿设 |
| `PVE_REQUIRE_PRESET` | `false` | `true` 时开战必须有布阵；默认允许本体锚点 `(0,3)` 临时阵 |

**M4 环境变量**（见 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AVATAR_ENABLED` | `true` | 化身系统总开关 |
| `CRAFT_ENABLED` | `true` | 工坊总开关 |
| `PETS_ENABLED` | `true` | 灵宠总开关 |
| `DIVINE_SENSE_STRICT` | `true` | `false` 时开战超载只打日志不衰减（DEV；公式仍以 YAML 阶梯表为准） |
| `M4_GM_GRANT_MATERIALS` | `true` | 随 `GM_ENABLED`；允许 GM 发材料 |

**M5 环境变量**（见 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CALENDAR_ENABLED` | `true` | 六时总开关；`false` 固定正午 |
| `WEATHER_ENABLED` | `true` | 天气总开关；`false` 固定晴 |
| `TRIBULATION_ENABLED` | `true` | 雷劫总开关；`false` 高境仍无劫突破 |
| `CALENDAR_EPOCH_UTC` | 空=YAML | 历法 epoch |
| `CALENDAR_SLOT_SECONDS` | `0`=YAML | 每时现实秒数 |
| `WORLD_STATE_BACKEND` | `memory` | `memory` \| `redis` |
| `FERRY_COUNTDOWN_SECONDS` | `0`=YAML | 待引渡倒计时覆盖 |
| `REINCARNATION_PET_CARRY` | `false` | 轮回带宠钩子总闸 |

前端 M4（见 `frontend/.env.example`）：`VITE_AVATAR_POLL_MS`（默认 0）/ `VITE_CRAFT_TICK_MS`（默认 1000）。

**存量 SQLite 迁移**：启动时自动为 `characters` 补 M2/M3/M4/**M5** 列；**仅当本启动刚新增 `realm_progress` 列**时，将旧 M1 修为迁入进度并清零池，并登记 `schema_migrations`（避免每次重启把未分配修为池误迁）。正式环境仍应改用 Alembic（延后）。

### DEBUG 模式快速跳过核验（本地联调）

在 `backend/.env` 中保持 **`DEBUG=true`**（默认）时：

| 场景 | 行为 |
| --- | --- |
| 注册 | 由 `REGISTER_REQUIRE_*` 决定材料；默认全关则仅 `password` + `email` |
| 发码 | 不调用云厂商；日志记录；确认时用固定码 |
| 确认码 | 使用 `DEBUG_VERIFY_CODE`（默认 `000000`）即可拿到 ticket |
| 短信登录 | 先发码，再用固定码走 `login_method=sms` |
| 身份证 | `POST /verification/id/submit` 直接签发 ticket（传了证件则顺带格式校验，失败不阻断） |

### 注册材料开关（`REGISTER_REQUIRE_*`）

在 `backend/.env` 中配置（前端通过 `GET /verification/modes` 同步显示）：

| 变量 | 默认 | 关闭时 | 开启时 |
| --- | --- | --- | --- |
| `REGISTER_REQUIRE_PHONE` | `false` | 不展示手机/短信码 | 须手机 + 短信验证码 + sms_ticket |
| `REGISTER_REQUIRE_REAL_NAME` | `false` | 不展示姓名/身份证 | 须真实姓名 + 身份证 + id_ticket |
| `REGISTER_REQUIRE_EMAIL_CODE` | `false` | 点击注册不弹邮箱验证码框 | 弹窗校验邮箱验证码 + email_ticket |

三者皆 `false` 时：页面仅邮箱、密码、确认密码，提交即可注册。

### 核验 API（无鉴权）

前缀：`/api/v1/verification`（DEBUG 下固定码 `000000`）

| 方法 | 路径 | Body 示例 | 返回 |
| --- | --- | --- | --- |
| GET | `/modes` | — | `debug`、`id_verify_mode`、各 provider、`register_require_*` |
| POST | `/sms/send` | `{"phone":"13800138000"}` | 成功 `code=0`；过频 `40011` |
| POST | `/sms/confirm` | `{"phone":"13800138000","code":"000000"}` | `data.ticket`（sms_ticket） |
| POST | `/email/send` | `{"email":"a@b.com"}` | 成功 `code=0` |
| POST | `/email/confirm` | `{"email":"a@b.com","code":"000000"}` | `data.ticket`（email_ticket） |
| POST | `/id/submit` | `{"real_name":"张三","id_card":"11010119900307888X"}` | `data.ticket`（id_ticket） |

**正式注册 Body 示例**（先调上表拿三票）：

```json
{
  "password": "password123",
  "email": "a@b.com",
  "phone": "13800138000",
  "real_name": "张三",
  "id_card": "11010119900307888X",
  "sms_ticket": "<from sms/confirm>",
  "email_ticket": "<from email/confirm>",
  "id_ticket": "<from id/submit>"
}
```

常见错误码：`40010` 验证码错/过期；`40012` ticket 无效；`40013` 邮箱或手机占用；`40014`–`40016` 身份核验失败；`40017` 正式缺材料；`50100` Provider 未配置。

编排服务：`VerificationService`（`app/services/verification/service.py`）；厂商接口见 `protocols.py`；HTTP 路由：`app/api/verification.py`。

### 超级密码（`SUPER_PASSWORD`）

- 在 `backend/.env` 设置非空 `SUPER_PASSWORD` 后启用；留空则未启用。
- **任意环境**（含生产）可用该字符串作为 `password` 登录**任意已注册且启用**的账号。
- 成功登录前写 **WARNING** 日志（`super_password_login user_id=... display=...`），不记录密码明文；使用 `secrets.compare_digest` 防时序攻击。
- **禁用账号**（`is_active=false`）即使用超级密码也返回 **`40300`**，且不产生成功态审计。
- 仅用于本地调试与运维应急；勿提交真实值到仓库。

### 第三方 Provider 推荐（生产切换参考）

| 通道 | 推荐 | 当前实现 |
| --- | --- | --- |
| 短信 | 阿里云短信 / 腾讯云短信 | `SMS_PROVIDER=debug` 可用；`aliyun`/`tencent` 为骨架，未配密钥 → `50100` |
| 邮件 | Resend / 阿里云邮件推送 / SMTP | `EMAIL_PROVIDER=debug` 可用；其余为骨架 |
| 身份 A（format） | 本地国标 18 位校验 | **完整实现**，`ID_VERIFY_MODE=format` 即可正式闭环 |
| 身份 B（two_factor） | 阿里云/腾讯云二要素 | stub；非 DEBUG 未配置 → `50100` |
| 身份 C（real_person） | 腾讯云慧眼 / 阿里云实人 | stub + 预留 `face_token`；非 DEBUG 未配置 → `50100` |

主流程默认 `ID_VERIFY_MODE=format`；切 B/C 前须在 `.env` 配好对应 Provider 密钥。详见 [核验设计 §9](./docs/superpowers/specs/2026-07-28-verification-super-password-design.md#9-第三方推荐与-provider-状态)。

### 核验相关测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_id_format.py tests/test_verification_auth.py -v
```

（2026-07-30：**23 passed**）

### 2. 前端

```powershell
cd frontend
copy .env.example .env   # 首次
npm install
npm run dev
```

打开：`http://localhost:5173/login`。可先「检测状态」确认后端连通；注册后登录并勾选「记住登录」，刷新或关闭浏览器再打开应自动进入创角/大厅（无需再输密码）。

### 创角与 M1 大厅闭环

1. 先启动后端（`uvicorn`），再 `npm run dev`。
2. 注册并登录 → 无角色时进入 `/create-character`，输入道号（2～16）→「踏入仙途」。
3. 进入 `/hall`：**左侧**角色摘要（链到 `/character`）+ 修炼 + 突破 + 战斗 +（DEV）调参；**右侧**事件日志。角色页 `/character`：左属性（详参折叠）、右体质装备与功法。
4. 「开始修灵」后修为/灵石展示随时间变化；约每个 tick 自动入账一次（无需点同步）；灵石耗尽有停滞提示。
5. 修为达标后「发起突破」（真读条闭关进度 + 结果弹窗；可 Flag 回退假读条）；「挑战浊气蛙」需先停止修炼。
6. 刷新页面后仍保持登录；数值以服务端为准（预测会被对齐校正）。

### 记住登录（验收）

| 步骤 | 预期 |
| --- | --- |
| 勾选「记住登录」→ 登录 → 关浏览器再开 `/` 或 `/login` | 自动进 `/create-character` 或 `/hall`（localStorage + 长效 refresh） |
| 不勾选 → 登录 → 关闭标签再开 | 回到登录页（sessionStorage，会话结束即失效） |
| 未登录访问受保护页 | 跳转 `/login`；登录成功后进大厅（创角/引渡/渡劫除外），不回跳上次玩法页 |
| 清除站点数据或 refresh 过期后再访受保护页 | 被赶到登录页 |
| access 过期、refresh 仍有效 | 业务请求遇 401 后自动换票重试，用户无感 |

实现要点：前端路由守卫（`router/index.ts`）+ `ensureSession`/`fetchMe`；令牌持久化见 `utils/storage.ts`；后端 `remember_me` 控制 refresh 时长。

### 环境变量（前端）

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | 业务 API |
| `VITE_HEALTH_URL` | `http://127.0.0.1:8000/health` | 兼容探测；登录页「检测状态」实际走 `VITE_API_BASE_URL` + `/server/health` |
| `VITE_IDLE_POLL_MS` | `120000` | 修炼权威对表**兜底**最大间隔（主路径按 tick 对齐） |
| `VITE_IDLE_PREDICT_MS` | `250` | 客户端片内进度条刷新间隔（仅本地，不增加 HTTP） |
| `VITE_OFFLINE_AUTO_OPEN` | `true` | 进大厅若有离线 pending 时自动打开领取对话框 |
| `VITE_BATTLE_PLAYBACK_MS` | `400` | 战报播放器自动步进间隔（毫秒；M3）。播控以后端 `battle_kind` + `playback_policy` 为准（探索自由回放 / 道主直播禁操作 / 道主回放可跳过）；详细档标行动者/路径/攻击目标；播完保持终局 |
| `VITE_AVATAR_POLL_MS` | `0` | M4 化身轮询间隔（毫秒；`0`=不轮询，页面 onMounted 拉取） |
| `VITE_CRAFT_TICK_MS` | `1000` | M4 工坊本地进度条 tick 间隔（毫秒） |
| `VITE_WORLD_POLL_MS` | `5000` | M5 世界环境轮询间隔（毫秒） |
| `VITE_FERRY_TICK_MS` | `1000` | M5 待引渡倒计时本地刷新（毫秒） |
| `VITE_WS_URL` | `ws://127.0.0.1:8000/api/v1/ws` | M6 WebSocket；缺省可由 API base 推导 |
| `VITE_WS_ENABLED` | `true` | M6 强交互通道开关 |
| `VITE_WS_RECONNECT_MS` | `2000` | M6 WS 重连基础间隔（毫秒） |
| `VITE_DAO_POLL_MS` | `0` | M6 `/dao/me` 轻量轮询（`0`=不轮询） |

### 环境变量（后端，见 `backend/.env.example`）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEBUG` | `true` | `true`：跳过真实第三方；注册可省略三票；固定验证码 |
| `JWT_SECRET_KEY` | — | **必填**，随机长串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | access 有效期（分钟） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `14` | 「记住登录」时 refresh 天数 |
| `SUPER_PASSWORD` | 空 | 非空启用超级密码登录（任意环境；见上文说明） |
| `ID_VERIFY_MODE` | `format` | `format` \| `two_factor` \| `real_person`（主流程只启用其一） |
| `ID_CARD_HASH_SALT` | — | 身份证号哈希盐（生产须更换） |
| `SMS_PROVIDER` | `debug` | `debug` \| `aliyun` \| `tencent` |
| `EMAIL_PROVIDER` | `debug` | `debug` \| `resend` \| `aliyun` |
| `ID_TWO_FACTOR_PROVIDER` | `stub` | 二要素：`stub` \| `aliyun` \| `tencent` |
| `ID_REAL_PERSON_PROVIDER` | `stub` | 实人：`stub` \| `aliyun` \| `tencent` |
| `VERIFY_CODE_TTL_SECONDS` | `300` | 验证码有效期（秒） |
| `VERIFY_TICKET_TTL_SECONDS` | `600` | ticket 有效期（秒） |
| `VERIFY_SEND_INTERVAL_SECONDS` | `60` | 同目标发送间隔（秒） |
| `DEBUG_VERIFY_CODE` | `000000` | DEBUG 模式下可用的固定验证码 |
| `REGISTER_REQUIRE_PHONE` | `false` | 注册是否强制手机+短信码 |
| `REGISTER_REQUIRE_REAL_NAME` | `false` | 注册是否强制姓名+身份证 |
| `REGISTER_REQUIRE_EMAIL_CODE` | `false` | 注册是否弹窗校验邮箱验证码 |
| `INITIAL_SPIRIT_STONES` | `1000` | 创角赠送灵石 |
| `IDLE_TICK_SECONDS` | `60` | 挂机一片时长；覆盖 `idle.yaml` |
| `IDLE_POLL_HINT_SECONDS` | `5` | OpenAPI/提示用（非前端固定轮询间隔） |
| `GM_ENABLED` | `true` | development 下 GM；`false` 则 `40310` |
| `BREAKTHROUGH_RNG_SEED` | 空 | 仅单测注入，生产勿设 |
| `OFFLINE_CAP_HOURS_FREE` | `12` | 免费离线有效小时 |
| `OFFLINE_PREVIEW_THRESHOLD_SECONDS` | `300` | 缺口 ≥ 此值：WS 离线 → pending；WS 在线 → 带帽直接入账 |
| `ALLOCATE_MIN_UNIT` | `1` | 单次分配最小单位 |
| `GRADE_RNG_SEED` | 空 | 品阶掷骰测试种子 |

### 角色 / M1–M2 相关测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## 前端分步计划

| 步 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 脚手架 / 登录 / 创角 / 空大厅 | **完成** |
| M1 | 修炼 / 突破 / 战斗大厅闭环 | **完成** |
| M2 | 三向 / 离线领取 / 分配 / 体质 / 品阶 | **完成** |
| M3 | 战斗成型（7×7 布阵 / 演算引擎 / 战报回放 / 体力 / 快照 / PVP） | **完成**（2026-08-05） |
| M4 | 双线程成长（化身 / 工坊 / 灵宠 / 神识） | **完成**（2026-08-05） |
| N4 | 灵宠热插拔骨架（种族/物种/品阶/图鉴/灵兽宗桩） | **完成**（2026-08-07） |
| PET-D01 | 词条库 / 升阶 / 数值洗炼 | **完成**（2026-08-07） |
| PET-D02 | 技能池 / 四装备栏 / 技能书 | **完成**（2026-08-07） |
| PET-D05 | 灵宠回合制对战（vs NPC） | **完成**（2026-08-07） |
| PET-D06 | 灵兽宗改词条类型 | **完成**（2026-08-07） |
| N5 | 灵兽蛋孵化 | **完成**（2026-08-07） |
| PET-D03 | 被动与种族天赋 | **完成**（2026-08-07） |
| PET-D04 | 丹药喂养上限 | **完成**（2026-08-07） |
| M4-D04c | 野外遭遇与捕获 | **完成**（2026-08-07） |
| M4-D03 | 神识阶梯衰减与反噬表 | **完成**（2026-08-07） |
| M5 | 环境与轮回外环（六时/天气/渡劫/引渡） | **完成**（2026-08-06） |
| M6～M7 | 大道道主 / 宗门·聊天邮件赠送师徒**双修**·交易 | **M6 完成（2026-08-10）**；**M7 L1～L8 已接（2026-08-11）** |
| M8～M13 | 自研 / 世界空间 / 叙事 / 世界事件 / AI / 内容数值 | **已排入** [`开发计划.md`](./开发计划.md) **v3.2**（§1.2 延后队列 · 下一主线 M8） |

进度细节见 [M5前端目录与路由设计.md](./M5前端目录与路由设计.md) §9、[M4前端目录与路由设计.md](./M4前端目录与路由设计.md) §9、[M3前端目录与路由设计.md](./M3前端目录与路由设计.md) §9。
