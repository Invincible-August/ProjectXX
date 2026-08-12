# Changelog

## [Unreleased]

- **玩家在线状态（Presence）**：统一 `PresenceService`（WS 鉴权连接 + 可配 `grace_sec`）；组队/道友/面交/助战/赛会改接 `is_online_for`；上线/离线推送 `presence.changed`（道友+队友）；设计见 [`玩家在线状态设计.md`](./玩家在线状态设计.md)；多 worker → **PRESENCE-R01**（2026-08-12）

- **修复前端 `npm run build` 类型错误**：`GmSetCharacterPayload` 补 `open_dao_contest_now`；WS RSVP 超时结果改用对象承载避免 TS2367；去掉 `contestBattleReport` 未使用变量 `flipped`（2026-08-12）

- **独立队伍页 `/party`**：建队 / 队长邀请与踢人 / 离队 / 队友公开摘要（境界·状态·在线·攻防·功法·体质装备）；ChatDock 去掉建队/邀请/离队，待邀仅角标与「去队伍页」；道友「组队」跳转 `/party?invite=`；大厅入口与规则文案同步；`party_action` 增 `kick`、邀请仅队长；单测 `test_party_kick_and_leader_only_invite`（2026-08-12）

- **聊天在线全频道收信**：世界频向所有在线连接直推正文；前端订齐可进聊天房且切页不退订；进玩法壳即 `startSessionListening`（坞未开也收）；打开窗口可见本会话在线期间各频缓存（2026-08-12）

- **修复未领机缘盖住聊天**：消息流机缘按当前频道过滤；切到私聊/队伍/师承清空可见机缘；消息区加高，避免红包挤没正文（2026-08-12）

- **聊天坞：私聊同步 + 机缘限频 + 私聊按人头角标**：WS 对频道成员直推正文（未进房也能同步）；机缘仅世界/宗门可发；聊天按钮角标为有未读私聊的**人数**；组队/交易/道友规则提示挪到大厅主界面（2026-08-12）

- **独立道友页 `/friends`**：列表展示修为/境界/在线/助战可用；行内私聊、赠礼入邮、组队邀请、化身助战、面交；解除道友；大厅入口；助战开关与待处理邀请（2026-08-11）

- **道友化身助战竖切**：`AvatarAssistSession`；`assist_friends_enabled`；`friend_assist` 功能（化神）+ `assist_battle` 体力；API `/avatar/assist/*`；离线自动 accept / 在线须确认；bench 客串 `avatar_guest_{owner}_{avatar}`；PVE 扣主人体力、奖励归借入人；PVP/赛会拒客串；WS `avatar.assist.invite`；单测 `test_avatar_friend_assist_pve`（2026-08-11）

- **组队邀请/接受/拒绝**：`party_invites` 表；`party_action` 支持 create（空队）/invite/accept/reject/leave；双方在线门闸（`party_dev_assume_online`）；`party_me` 返回 `pending_invites`；WS `party.invite`/`party.update`；ChatDock 邀请流；单测 `test_party_invite_accept`（2026-08-11）

- **面交草稿/锁定/确认**：`pending_invite`→接受`browsing`→`set_offer`仅写草稿→`lock`托管→双方确认成交；新增 accept/reject/lock API；`face_dev_assume_online` 等 trade.yaml 开关；前端双栏面交面板（2026-08-11）

- **修复连续发机缘误判「已开过这份缘」**：SQLite 默认关外键导致 purge 包后 `heritage_claims` 残留，id 复用后同人无法再开；现连接启用 `PRAGMA foreign_keys=ON`、purge 显式删领取行、列表/发包清理孤儿 claim；单测 `test_heritage_sequential_packets_claimable`（2026-08-11）

- **机缘落库审计单测**：`test_heritage_db_audit` 覆盖发机缘扣灵石/道具、`heritage_packets`/`currency_ledger`/`heritage_claims` 写入，以及灵石不足/道具不足/绑定物拒发（2026-08-11）

- **聊天坞整体可滚**：矮视口下面板增加纵向滚动条，可滑到下方发机缘/发送等功能按钮（2026-08-11）

- **修复机缘发出即「已领完」**：SQLite purge 后 id 复用 + 会话已领完脏缓存；发出/推送时强制按进行中归一，open 时清同 id 已领完缓存；claimed 推送带 `packet_created_at` 防迟到覆盖；表启用 `sqlite_autoincrement`（2026-08-11）

- **聊天/机缘会话清空**：`session_ephemeral`——退出/关浏览器清空本端聊天且不拉历史；已抢完机缘本会话仍可见，默认保留 **20** 条（`session_finished_keep`），退出/关浏览器后清空；未抢完始终从服务端拉取（2026-08-11）

- **聊天机缘（原传承红包）**：玩家称谓改为「机缘」；发机缘可选灵石或从背包点选非绑定/非唯一/可交易物品（禁手填 id）；`GET /inventory` 增 `tradable`/`bound`/`unique`/`max_stack`；目录支持 `unique`；摘要展示物品中文名（2026-08-11）

- **聊天坞体验**：打开默认进入世界频道；不展示「进入频道」类提示；发言正文黑色；道号按大境界着色；聊天按钮加深；频道页签（宗门/师承/队伍等）与组队按钮加深色高对比（2026-08-11）

- **凝练权威闸下沉后端**：`GET /avatar/features` 增 `condense`（`can_condense`/`realm_ok`/`stones_ok`/`block_*`，与 POST 同源）；前端 `AvatarCondensePanel` 改读该字段，删除本地境界硬编码；真仙单测覆盖；POST 失败文案细分（2026-08-11）

- **修复真仙无法凝练化身（前端）**：`AvatarCondensePanel` 门槛误写死为金丹/元婴/化神，GM「一键真仙」后按钮禁用；改为 `realmMeetsUnlock` 按大境界序判定（金丹及以上含真仙）；新增 `utils/realmOrder.ts`（2026-08-11）

- **M7 L8 商业化壳竖切（前后端）**：`commerce.yaml` / `currencies.yaml`；角色 `tiandao_points` / `membership_expires_at`；`CommerceService`（开通会员 18/24 帽、过期回落 12h、天道商店、禁售本命道文案、沙盒加点）；账本扩 `tiandao_point`；API `/commerce/*`；前端 `/shop`；`COMMERCE_SYSTEM_ENABLED` / `COMMERCE_SANDBOX_ENABLED`；单测 `test_commerce_membership_sandbox`；`scripts/smoke_m7.py`（2026-08-11）

- **M7 L7 双修+四榜竖切（前后端）**：`dual_cultivation.yaml`；表 dual_cultivation_sessions / dual_rank_scores；`DualCultivationService`（邀约→确认→掷骰 `purpose=dual_cultivation`→结算双增/传修为；四榜）；角色 `gender` + 创角/补选；API `/dual/*`；前端 `/dual-cultivation` + 创角性别；`DUAL_CULTIVATION_ENABLED`；单测 `test_dual_cultivation_dice_ranks`；消化 **DICE-R03**（2026-08-11）

- **M7 L6 师徒+真引渡竖切（前后端）**：`mentor.yaml`；表 mentor_bonds/quest_progress/pass_daily；`MentorService`（拜师/传功/出师/解除、师承频成员）；API `/mentor/*`；`reincarnation.yaml` `social_rescue` + `POST /ferry/rescue`（道友/同门，救援者支付，`SAME_REGION_STUB`）；前端 `/social?mode=mentor|ferry`、待引渡「去求援」、ChatDock 师承解锁；`MENTOR_SYSTEM_ENABLED`；单测 `test_mentor_flow`；消化 **M5-D03**（同图真判定仍 → M9）（2026-08-11）

- **M7 L5 传承竖切（前后端）**：`chat_heritage.yaml`；`heritage_rules` 预拆份；表 heritage_packets/claims/daily；`HeritageService`（random/fixed、成员校验 `40140`、绑定拒 `40111`、过期退邮件）；API `GET/POST /heritage` · `POST /heritage/{id}/claim`；WS `heritage.created|claimed|expired`；ChatDock `HeritageCard`；`HERITAGE_SYSTEM_ENABLED` / `HERITAGE_EXPIRE_SEC`；单测 `test_heritage_random_fixed`（2026-08-11）

- **M7 L4 五频道聊天+ChatDock（前后端）**：`chat.yaml`；`ChannelMembership`；表 chat_messages/mutes/unreads + party_*；`ChatService`（world/sect/dm/mentor锁/party、限速 40131、禁言 40132、敏感词占位）；API `/chat/*` `/party`；WS `chat.message`/`chat.unread` + 进房成员校验；前端 `ChatDock` 横切挂 `App.vue`；`CHAT_SYSTEM_ENABLED` / `CHAT_WS_PUSH_ENABLED`；单测 `test_chat_channels_auth`（2026-08-11）

- **M7 L3 邮件+赠送竖切（前后端）**：`mail.yaml`；表 `mail_messages` / `gift_daily_counters`；`MailService`（领取幂等 `40120`、过期退回、赠送日限/道友校验）；拍卖流拍默认退系统邮件；API `GET/POST /mail` · `POST /mail/{id}/claim|read` · `POST /gifts`；前端 `/social?mode=mail|gift`；`social_badges.mail_unread`；单测 `test_mail_gift`；`MAIL_SYSTEM_ENABLED`（2026-08-11）

- **M7 L2 道友+交易竖切（前后端）**：`friends.yaml` / `trade.yaml`；表 friendship / trade_listings / auction_* / face_trade / currency_ledger；`FriendService` + `TradeService`；物品 `tradable`/`bound`；一口价手续费入回收；面交版本锁成交；API `/friends` `/trade/*`；前端 `/market` `/social`；单测 `test_trade_listing_face`；`FRIENDS_SYSTEM_ENABLED` / `TRADE_SYSTEM_ENABLED`（2026-08-11）

- **M7 L2 前端**：`/market`（交易行/拍卖/面交）+ `/social`（道友；邮件/赠送/师徒/引渡 L3+ 占位）；`types/api/stores` friends·trade；`CharacterPublic.friend_count` / `social_badges`；`HallSocialGate` 文案改为坊市/社交已开放 L2（2026-08-11）

- **M7 L1 宗门竖切（前后端）**：扩展 `sects.yaml`（NPC 拜入/建宗/任务/商店/兑宠）；表 `sects`/`sect_members`/`sect_contribution_ledger`/`sect_quest_progress`；`SectService` + `/api/v1/sect/*`；`CharacterPublic.sect`；轮回贡献归零；前端 `/sect` + `HallSocialGate`；单测 `test_sect_join_create`；`SECT_SYSTEM_ENABLED`；消化 **M4-D06**（化身宗门任务接交）（2026-08-11）

- **M7 L1 前端**：`/sect` 宗门页（拜入/建宗、任务、商店、魂灯、兑宠）+ `HallSocialGate`；`types/api/stores/components/sect`；`CharacterPublic.sect`；`/market` `/social` `/dual-cultivation` `/shop` L2+ 占位；`safeRedirect` 白名单扩展（2026-08-11）

- **ATTR 占位设计（仅文档）**：[`ATTR战斗属性占位设计.md`](./ATTR战斗属性占位设计.md) **v1.0**——锁 `CombatAttrBlock` / 叠层 / 面板 `breakdown`；澄清 **M13=填正式曲线、不重设计字段**；**ATTR-D01 → 设计中**；开发计划 §0.6.2 同步（2026-08-11）

- **开 M7 设计（仅文档）**：[`M7宗门社交与经济设计.md`](./M7宗门社交与经济设计.md) / [`M7前端目录与路由设计.md`](./M7前端目录与路由设计.md) **v1.0**——五路由（`/sect` `/market` `/social` `/dual-cultivation` `/shop`）+ ChatDock 横切；竖切 L1～L8；锁双修 D-WD1～4；CHAT/HERITAGE 细则并入核心设计；登记 **M7-D02～D05**；本轮无业务代码（2026-08-11）

- **M6 收尾包**：世界事件骨架补 `room_id` + Hub 建房（在场=WS 成员）；`smoke_m6` 覆盖赛会报名/立刻开赛；设计 §11 验收勾选；`?mode=spectate` 深链到赛会；旧单挑遗留清理命名（2026-08-11）

- **移除旧单挑**：删除 `POST/GET /dao-lord/challenges*` 与玩家端旧即时单挑 UI/store；有主更替仅走道主之争赛会。`DaoChallengeSession` 表保留作遗留数据清理（剔除道主时强制 abort）（2026-08-11）

- **战报先攻日志**：先攻不再回合开头批量刷三条；服务端按行动序在「该单位行动前」写出【先攻】再接移动/攻击，播放器逐步跟这条流水（2026-08-11）

- **战报播控解耦**：后端 `battle_kind` + `playback_policy` 驱动播放器控件（`domain.battle_presentation`）；日常探索 / 道主直播 / 道主回放矩阵写死；前端 `BattleReportPlayer` 只消费策略，不再靠路由拼 `liveMode`/`allowSkip`（2026-08-11）

- **战报播放器**：拆分 `/battle` 自由回放与道主之争直播策略——自由回放不再沿用「同战报保持终局」；单步/跳过不再因播完而禁用（终局点单步=回到开局）；`BattleView` 显式 `allow-skip`/`live-mode=false`（2026-08-11）

- **战报播放器**：修复切到「详细」后单步/跳过无效（简易档不再后台播完游标）；简易档不显示棋盘，仅结果摘要+完整日志（2026-08-11）

- **战报棋盘观感**：播报结束后保持终局站位（不复位）；详细回放中用路径高亮、行动/攻击浮标、攻击连线标出行动者、移动起终点与攻击目标（2026-08-11）

- **运营后台**：道主之争新增「跳过等待 · 进入战斗」——`POST /admin/ops/dao-contests/advance-arena`，可跳过 RSVP/倒计时/整备/轮间/直播等待并推进至对战演出（审计 `ops.dao_contest.advance_arena`）（2026-08-11）

- **道主之争整备离场**：整备中一方离场判负且本阶段场次均已结束后，立刻跳过剩余整备倒计时并推进结算/轮间，避免空等（2026-08-11）

- **道主之争开打编成**：挑战者互殴与道主在线决战改为开打瞬间双方现场读取进攻预设并冻结入局（`live_loadouts` 审计）；道主离线/强制快照仍用防守快照；锁阵文案改为「现场编成已锁定」（2026-08-11）

- **道主之争改阵/空窗/整备卡**：入席确认与开赛倒计时亦可改阵装道具（`can_adjust_loadout`）；无棋盘绝不弹空抽屉（含赛会面板去掉「暂无棋盘战报」empty）；同轮多场 adjusting 时仅本人场标「整备中」，其它为「同轮整备」，并合并顶部提示避免多框堆叠（2026-08-11）

- **安全加固（道主/赛会）**：移除玩家 `force_result` 夺位洞；离场判负改服务端权威（忽略客户端开关）并同步 `alive`/道主席位；道主 RSVP 一次性且 accept 清快照标记；`dev_assume_online` 仅 development 生效；WS 赛会房间 id 校验（2026-08-11）

- **道主之争播报窗**：直播可随时关闭，关后不再强制弹；关窗≠跳过赛程；点对阵表或「回到播报」可再进；无战报场次不再开空抽屉（2026-08-11）

- **道主之争体验**：点击无棋盘数据的场次（轮空/未开打/旧场）不再打开空抽屉，仅 Toast 说明原因（2026-08-11）

- **道主之争直播/对阵打磨**：擂台倒计时按 `phase_ends_at`+`server_now` 本地滴答（消除双端约 1s 差）；直播强制详细棋盘、禁简易/暂停/跳过，游标跟 `battle_event_cursor` 全服同步（中途观战不从头播）；晋级表改 tournament bracket 列序；人数不足跳过空轮（1 人直打道主、2 人决赛）（2026-08-11）

- **道主之争实时审查修复**：RSVP 弹窗限时 60s（超时弃权）、确认提示仅本账号；RSVP 后 30s 开首轮；战报本人视角己方在下、观众标上下方；收口后离场不再误报判负；个人 `rsvp_update` 不再全服 Toast（2026-08-11）

- **修复**：道主之争报名 `TypeError: can't compare offset-naive and offset-aware datetimes`——冷却截止与 `now` 统一经 `_as_utc` 再比较（2026-08-11）

- **道主之争体验**：淘汰赛分组对战表（动态晋级，决赛后保留）；点击场次棋盘直播/回放（复用日常 `BattleReportPlayer`，直播禁跳过）；擂台整备 `/formation?from=dao-arena` 显示「回擂台」，日常布阵不显示（2026-08-10）

- **运营后台**：道主之争「重新开放报名」——收口/取消/进行中均可重置本场（清空报名与对阵、拉长报名窗），便于联调反复开赛；赛会卡片展示收口/再开赛条件说明；`POST /admin/ops/dao-contests/reopen`（2026-08-10）

- **道主之争擂台分阶段（M6-D06b）**：开赛 RSVP 弹框（报名弃权 / 道主快照）、独立 `/dao-lord/arena`、首轮 30s / 轮间 30s、半决起 60s 整备、演出中离场 `leave_forfeit` 覆盖推演胜者；配置见 `dao_lord.yaml` `contest.staging_*`（2026-08-10）

- **修复**：管理员保存「赛会日程」草稿报错（`dao_lord` 等域缺校验探针）→ `AdminConfigService._probe_parse_domain` 补齐；日程表单校验 HH:MM（2026-08-10）
- **修复**：立刻开赛后在线玩家无反应 → 收口前先 `commit` 再广播 `dao_lord.contest.state`；前端全局提示、切赛会 Tab、自动打开本人直播准备/对战窗（2026-08-10）

- **运营后台**：
  - **道主之争赛会日程**表单（`domains/dao_lord` →「赛会日程」：报名开始/结束、开打时刻、时区、直播秒数）
  - 配置域侧栏按**类目折叠**（大道与道主 / 灵宠 / 战斗 / 成长数值…），不再全部平铺
  - 左侧类目区与右侧内容区**独立滚动**
- **道主之争**：未满足报名资格时不展示「去报名 / 道主之争报名」按钮；赛会 `me.eligible` / `me.can_register`（2026-08-10）

- **M6 半决起「实时感」直播**：准备倒计时 → 节拍对战；选手可见布阵锁定，**观众仅见「准备中」倒计时**；`GET …/matches/{id}/live`；配置 `live_prep_seconds` / `live_tick_*`（2026-08-10）

- **M6 打磨包（M6-D06 P2～P4）**：立刻开赛后同道淘汰（轮空/离线判负）→ 冠军决战道主（在线 realtime / 离线快照）→ 半决/决赛/道主战直播窗与单直播槽；`GET bracket` / `matches` / `report` / `spectate`；下场开赛清回溯；玩家对阵树 UI（2026-08-10）
- **排期**：下一主线曾定为 M6 打磨包；**打磨包已收口**，其后开 M7；`后续待完成.md` §0.1 / 开发计划 U6 已同步

- **M6-D06 P1**：道主之争**报名与日程**落地——`contest.*` 配置、`/dao-lord/contests/current` 报名/取消、GM/Admin **立刻开赛**；玩家 `/dao-lord?mode=contest`；有主默认引导赛会（旧单挑降级）（2026-08-10）

- **运营后台**：新增「道主运营」——可查看各道道主并 **剔除道主**（席位变虚位）；`POST /admin/ops/dao-lords/{dao_id}/remove`（须 publisher/admin，写审计）；进行中挑战强制结束（2026-08-10）

- **定案（仅文档）**：道主有主更替 → **道主之争赛会**（报名 / 同道淘汰 / 道主在线双模决战 / 半决决赛直播）；见 [`M6大道与道主设计.md`](./M6大道与道主设计.md) v1.1 §5、[`后续待完成.md`](./后续待完成.md) **M6-D06**（P1～P4）；本轮无业务代码（2026-08-10）

- **规则**：道主空位**无需夺位**——首个本命道达标者自动就任（开道 / 升级 / GM 锁本命与抬级 / 拉榜惰性）；有主后仅挑战更替；前端去掉「夺位」按钮（2026-08-10）

- **修复**：道主夺位 `AttributeError: DefenseSnapshot 无 id`——快照主键为 `character_id`，改用其作 `snapshot_id` 引用（2026-08-10）

- **DEV 调参同步 M6（2026-08-10）**
  - 大厅「调参（DEV）」新增 **M6** 区：一键联调套装 / 真仙 / 锁本命道 / 道值等级 / 灌池 / 任命道主 / 开窗 / 清冷却 / 刷快照 / 推 `world.env`
  - GM API：`m6_quick_kit` · `lock_fate_dao` · `set_dao_qi` · `set_dao_level`；`dao_lord.yaml` 夺位门槛改为 **1**（样本联调）
  - `.env.example`：`DAO_LORD_FORCE_WINDOW=true` · `WORLD_EVENTS_ENABLED=true`（请同步到本地 `backend/.env` 后重启）

- **M6 大道 / 道主 / WS 实现（2026-08-10 · W1～W6）**
  - **境界**：`realms.yaml` 化神 → **真仙**（`true_immortal`）；开道门槛真仙初期
  - **配置**：`dao.yaml` / `dao_restraint.yaml` / `dao_lord.yaml` / `world_events.yaml`；ADM 域登记 + 字段 schema；环境变量见 `.env.example`
  - **后端**：`DaoService` 开道 roll/choose/道池；战斗/工坊 `use_dao` 扣道值；上位克制战报；`WsHub` + `WS /api/v1/ws`；道主 claim/挑战 HTTP 闭环 + 房间广播；世界事件骨架；轮回卸主留池
  - **前端**：`/dao` `/dao-lord`、`src/ws`、大厅门闸、挑战 Feed；见前端设计 §9
  - **测试**：`test_dao_open` / `test_dao_lord_claim`；冒烟 `scripts/smoke_m6.py`
  - **消化**：M4-D05（工坊运用）、M5-D04（`world.env` 可推）；延后仍见 M6-D01～D07

- **M6 前端骨架落地（2026-08-10）**
  - 新路由 `/dao` `/dao-lord`；`src/ws` 客户端（鉴权/心跳/重连）；大厅 `HallDaoGate` + 顶栏 `WsStatusBadge`
  - 类型 / API / Pinia：`dao` · `daoLord` · `worldEvents` · `ws`；组件与视图按 [`M6前端目录与路由设计.md`](./M6前端目录与路由设计.md)
  - 守卫：`PLAY_ROUTE_NAMES` 含 dao；待引渡禁 `dao-lord`；`active_dao_challenge` 优先回挑战区；`safeRedirect` 白名单扩展
  - 战斗/工坊可选 `use_dao` 勾选（`BattleDaoUsageLine` / `CraftDaoUsageLine`）
  - 环境变量：`VITE_WS_URL` / `VITE_WS_ENABLED` / `VITE_WS_RECONNECT_MS` / `VITE_DAO_POLL_MS`
  - **不做**：聊天/传承 UI（→ M7）

- **M6 设计开篇（2026-08-10 · 仅文档）**
  - [`M6大道与道主设计.md`](./M6大道与道主设计.md) **v1.0**：板块 S/T/U；竖切 **W1～W6**；决策 D1～D16；样本开道/道池、WS 协议、道主挑战（实时挑战者×快照道主）、Boss/秘境骨架
  - [`M6前端目录与路由设计.md`](./M6前端目录与路由设计.md) **v1.0**：新增 `/dao` `/dao-lord`；`src/ws` 客户端；大厅 `HallDaoGate`
  - `后续待完成.md`：新增 **§1.11 M6-D01～D07**；**M4-D05 / M5-D04 / M1-D33 → 设计中**；§0.1 指向 M6 实现
  - **明确不做**：完整 37 道、聊天/传承（→ M7）、Boss 成型（→ M11）、修炼真推送完整（M6-D07 不进出口）

- **开发计划 v2.8：属性路线 + 聊天/传承排期（2026-08-10 · 仅文档）**
  - **§0.6.2**：战斗属性不单开里程碑；M3-D03 schema → M8 喂属性 → M9 怪模板 → M13 填数
  - **M7**：WB 扩为世界/私聊/宗门/师承/队伍；新增板块 **WE 传承红包**（拼手气/定额；灵石+可交易道具；频道成员可见）
  - **M9**：AC6 地图频、AD5 势力频（复用 WB/WE）
  - **后续待完成**：登记 **ATTR-D01～D03**、**CHAT-D01～D03**、**HERITAGE-D01**

- **主动入轮回门槛：化神期起（2026-08-10）**
  - **规则**：`reincarnation.yaml` `altar.min_major_realm: huashen`；化神以下祭坛 → `40068`
  - **范围**：仅 **祭坛主动**；待引渡自选 / 超时强制不受此限
  - **前端**：祭坛预览 `can_altar` + 中文原因；大厅提示「化神期起」
  - **测试**：`test_altar_blocked_below_huashen`

- **突破取消读条（2026-08-10）**
  - **体验**：点击「发起突破」→ 同步 `attempt` → **立即**弹结果（无假条/真条）
  - **配置**：`breakthrough.yaml` `async_channel.enabled: false`（ADM 仍可再开）
  - **前端**：`BreakthroughPanel` 精简；旧档卡在 `breaking_through` 时懒结算一次
  - **文档**：[`异步真读条突破设计.md`](./异步真读条突破设计.md) **v1.2**

- **M5 横切打磨：中文信条落地 · 解耦 · 算力 · 索引（2026-08-10）**
  - **§0.0.2**：渡劫 `locked_weather_label` 不再塞英文 id；探索/离线/角色化身方向/PVP 阵法/战报击杀与阶段均中文出口；`domain/display_labels.py`；挂机 `segments` 带 `*_label`
  - **解耦**：突破对挂机改为 lazy import；展示映射下沉 domain
  - **算力**：settle 切段用时辰公式+天气一次冻结+`memoize_env_resolve`，避免每 tick 打 Calendar/Weather 快照
  - **索引**：`breakthrough_sessions` / `craft_jobs` / `pet_hatch_jobs` / `tribulation_sessions` / `inventory_items` / 体质槽 FK 复合或单列索引；`bootstrap._ensure_performance_indexes`
  - **文档**：开发计划 **v2.7** §0.6.1；M5 设计 **v1.5**；README / 各 M 修订记录同步
  - **测试**：`test_memoize_env_resolve_buckets` + 切段/战报/突破回归

- **筑基前挂机停滞误判 + 突破扣石规则（2026-08-10）**
  - **Bug**：前端 `idlePredict` 把 `idle_stones_per_tick=0`（筑基前免费）误判为「灵石不足停滞」，进度条停、误报文案；服务端挂机仍为 0 消耗未改
  - **修复**：免费挂机按满 tick 预测、不停滞；修炼区显示「不耗灵石」
  - **突破**：`pre_foundation_free`——锻体/炼气突破不扣灵石；**仅炼气圆满→筑基**扣 `major_advance` 费用；与轮回次数无关
  - **测试**：同步/异步突破用例与免费突破用例更新

- **M5-D05 / M1-D20 异步真读条突破 Phase A 落地（2026-08-10）**
  - **配置**：`breakthrough.yaml` `async_channel`（开关/时长/中文提示）；ADM 域 `breakthrough`
  - **后端**：`breakthrough_sessions`；`POST /channel/start` · `GET /channel` · `POST /channel/resolve`；开读条扣灵石；到期懒结算掷骰；PlayGate/角色拉取钩子；`attempt` 兼容 Flag
  - **前端**：`BreakthroughPanel` 真进度条（按 `ends_at`）+ 重连续条；大厅活动条闭关提示
  - **测试**：`tests/test_breakthrough_async_channel.py`
  - **文档**：设计 **v1.1**；`后续待完成` **M5-D05 / M1-D20 已消化**

- **M5-D05 / M1-D20 异步真读条突破设计定案（2026-08-10 · 仅文档）**
  - **新建**：[`异步真读条突破设计.md`](./异步真读条突破设计.md) **v1.0**——假读条→服务端跨请求 `breaking_through`；开读条/进度/懒结算；与渡劫会话分离；配置 `async_channel` + ADM；Feature Flag 可回退同步 attempt
  - **同步**：`后续待完成` **M5-D05 / M1-D20 → 设计中**；M1 §5 / M5 外环 D05 指针；README 文档表

- **M3-D07 封装解耦（2026-08-10）**
  - **新建** `domain/layer_payloads.py`：catalog / combat 乘区 / 命中伤害钩子 / 事件 enrichment（含 `layer_label_zh`）
  - **新建** `domain/line_of_sight.py`：统一最小 LOS mask 与 `block_source`（决策层与执行层同源）
  - **收窄** `formation_rules.py`：只保留对抗骰点与效果面板乘区
  - **引擎** `autochess`：经载荷/LOS 钩子调用，不再内联 mask 与乘区公式
  - **前端** 播放器四象行读 enrichment；「平局分区」与后端对齐
  - **命名** `FormationsConfig.to_engine_catalogs`（对齐嘲讽 snapshot）
  - **文档**：设计 **v1.1.1**

- **M3-D07 四象禁制 / 环境·天气载荷 Phase A 落地（2026-08-10）**
  - **配置**：`environment_catalog` / `weather_catalog` / `effect_catalog`；样本 `seal_phys_curtain`（金锁障）/ `seal_spell_curtain`（咒缄幕）/ `seal_all_curtain`（万缄障）；迷雾 `ranged_hit_mul=0.85`、雷暴 `magic_damage_mul=1.10`
  - **后端**：禁制子类按 `attack_kind` 过滤 LOS；禁制格计入通行墙；环境/天气 combat 乘区进命中/伤害；四象事件补 `*_label_zh` / `combat_notes`；`battle_text` 只播中文
  - **前端**：棋盘「禁」；播放器四象行优先中文名
  - **ADM**：formations 域加深 catalog 字段中文说明
  - **测试**：`tests/test_m3_d07_four_aspects.py`
  - **文档**：设计 **v1.1**；`后续待完成` **M3-D07 已消化**

- **§0.0.2 中文信条 + M3-D07 设计定案（2026-08-10 · 仅文档）**
  - **开发计划**：新增 **§0.0.2 玩家可见文案 · 中文信条（法律级）**——机读英文、人读中文；文档双语备注；战报/UI 禁止裸英文 id；配置须有 `label_zh`；违反=竖切未完成
  - **新建**：[`四象禁制与环境天气载荷设计.md`](./四象禁制与环境天气载荷设计.md) **v1.0**——禁制三子类（禁远程物理/法术/全部远程）、环境·天气 `combat` catalog 载荷、与世界天气边界、战报中文渲染、样本阵与验收单测表
  - **同步**：`后续待完成` **M3-D07 → 设计中**；成型设计 §5.2.3 / 延后表指针；README 文档表；计划版本 **v2.6**

- **嘲讽光环封装 + 挂账标注（2026-08-10）**
  - **封装**：`TauntAuraDef.to_engine_snapshot` / `to_public_summary`；`TauntAurasConfig.resolve_snapshot` / `public_summaries_for_units`；`AutochessService.list_pve_monsters_public`；API 变薄；`clear_taunt` Phase B 钩子
  - **文档**：[`开发计划.md`](./开发计划.md) §5 增 M3 打磨对照表；[`后续待完成.md`](./后续待完成.md) 新增 **M3-D06b**（Phase B → 挂 **M3-D03**）；设计 **v1.1.2**

- **M3-D06 显性收口（2026-08-10）**
  - **前端**：战报播放器 `ONE_LINE_TYPES` 补 `taunt`/`ai_retarget`（日志与棋盘游标同步）；PVE 选怪选项与提示展示嘲讽光环中文名
  - **API**：`GET /battle/pve/monsters` 增 `taunt_auras[{aura_id,label_zh,summary}]`
  - **测试**：`test_monster_list_exposes_taunt_labels`
  - **文档**：嘲讽光环设计 **v1.1.1**

- **M3-D06 嘲讽光环 Phase A 落地（2026-08-10）**
  - **配置**：`taunt_auras.yaml`（`ortho_guard` / `chebyshev_guard`）；PVE 样本 `taunt_guardian`；怪物 `units[].taunt_aura_id` 外键
  - **后端**：`domain/taunt_aura.py`；`BattleState` 光环运行态；`_execute_move` 进入触发；`decide_action` 嘲讽短路；死亡清除；`battle_text` 中文行
  - **ADM**：域 `taunt_auras`（entries+JSON / catalog / schema / probe）
  - **前端**：`BattleEvent` 增 `taunt` / `ai_retarget`
  - **测试**：`tests/test_taunt_aura.py`（7 例）+ 战斗回归绿
  - **文档**：设计 v1.1；`后续待完成` **M3-D06 已消化**

- **嘲讽光环设计定案（2026-08-10 · 仅文档）**
  - **新建**：[`嘲讽光环设计.md`](./嘲讽光环设计.md) **v1.0**——静态 YAML 光环注册表、按侧 `taunt_aura_mask`、进入触发 `STOP_TAUNT`、决策层嘲讽短路、死亡解除、战报 `taunt`/`ai_retarget`、ADM 域 `taunt_auras`；技能时长/驱散 → Phase B（M3-D03）
  - **定案要点**：不必等完整技能树；光环随嘲讽者移动更新；多光环重叠按 `(切比雪夫, uid)` 确定性归属；开战站位不自动嘲讽（只认移动进入）
  - **同步**：`后续待完成` **M3-D06 → 设计中**；算法文档 §8 / 成型延后表指针；README 文档表

- **战斗友军占位协调（2026-08-10）**
  - **根因**：§5.4 原「单位不算墙 + 撞人重规划≈绕行」在友军占住最短路时失效，后排反复 `blocked_unit` 空耗 AP
  - **修复**：`combat_ai` 局部软墙 BFS 改道；窄廊前排 `pick_yield_cell` 侧移让路；`_execute_move` 与决策共用 `next_step_toward_goal`
  - **测试**：`test_ally_repath_around_friendly_blocker` / `test_ally_yield_opens_chokepoint_corridor`
  - **文档**：`M3自动移动攻击算法设计.md` **v2.5** §5.4 修订

- **M3-D08 阵法部署 / force_shift Phase A 落地（2026-08-10）**
  - **配置**：`formations.yaml` 增 `deploy` / `terrain_layout` / `force_shifts`；样本 `wide_front`（add_cells）、`cloud_drift`（free_own）、`left_wing_mask`（mask）、`shift_gust`（移位）
  - **后端**：`domain/formation_blueprint.py`（resolve/校验/移位）；`validate_placement` 接 `deploy_zone`；presets 下发 `effective_deploy_cells`；开战套用 `force_shifts` 战报事件；启动与 ADM 发布硬校验
  - **封装优化**：`FormationDeploySnapshot` 一次解析；`validate_formation_def`；`ShiftBoardState` Protocol；禁停与 `terrain.py` 常量同源；API 增 `max_units_effective`
  - **前端**：布阵页随阵法切换高亮与上限；换阵自动清洗非法格；部署模式/移位预览提示
  - **ADM**：formations 域字段 catalog/schema 加深
  - **测试**：`tests/test_formation_deploy.py` + 相关回归绿
  - **文档**：设计 v1.2；`后续待完成` **M3-D08 已消化**

- **阵法部署与自研设计定案（2026-08-07 · 仅文档）**
  - **新建**：[`阵法部署与自研设计.md`](./阵法部署与自研设计.md) **v1.0**——部署四模式（`default`/`fixed`/`free_own`/`mask`）、地形 `brush` 仅定稿时落笔、`force_shifts`、ADM/自研同 schema、Phase A（M3-D08）/ Phase B（M8）竖切
  - **定案要点**：自由度在阵法定稿时写死；出战只摆棋子不改地形；`free_own`=己方半区只限数量；中立列默认关闭
  - **同步**：`后续待完成` **M3-D08** 指针与验收钩子；README 文档表

- **化身系统 OOP / 减负优化（2026-08-07）**
  - **封装**：`AvatarCapabilityIndex`（配置加载时预计算境界序与功能闸）；`AvatarStaminaLedger`（体力账本）；`avatar_repo.fetch_avatar_row` 轻量仓储
  - **减负**：`enrich_public` 改走 `get_summary`（不建功能表、不脏写体力）；体力仅 `dirty` 时写 ORM；预览/探索只读免 settle；前端 `/me` 回填 features，未解锁不拉探索桩
  - **调用方**：idle / snapshot / autochess / formation / craft 改用索引或轻量查询，避免为读一行构造完整 `AvatarService`
  - **测试**：`test_avatar_capability.py` + 原有化身测回归通过

- **化身系统深化 AVATAR-D01～D06 + ADM 落地（2026-08-07）**
  - **配置**：`avatar.yaml` 扩展 `feature_unlocks` / `transfer.retention_ratio` / `stamina`；`max_avatars=1` 硬校验
  - **后端**：功能闸（金丹仅 spirit；元婴工坊/炼体）；互传预览与折扣实扣；体力/日行动；独战编成闸；探索/任务桩；错误码 `40090～40093`
  - **API**：`GET /avatar/features` · `POST /avatar/transfer/preview` · `GET /avatar/explore/status` · `POST /avatar/quests/accept`；`/me` 扩 features/stamina
  - **ADM**：域 `avatar` 登记；表格+JSON 双写；中文 schema / field catalog
  - **前端**：`/avatar` 功能看板、挂机方向锁定、互传预览、体力条、独战/任务桩入口
  - **测试**：`tests/test_avatar_features.py`（9 例）
  - **文档**：`化身系统设计` / `后续待完成` AVATAR-D* **已消化**；后台计划域状态更新

- **化身定案：取消多化身 + 细则文档（2026-08-07 · 仅文档）**
  - **新建**：[`化身系统设计.md`](./化身系统设计.md) **v1.0**——永久单化身；境界功能矩阵；体力/日行动；互传保留率；独战/探索/任务竖切；对齐 §0.0 / §0.7
  - **取消**：原 **M4-D01 多化身**；`max_avatars` 必须为 `1`
  - **拆项**：`AVATAR-D01～D06` 登记于 `后续待完成.md`；§0.1 P1 改为 AVATAR-D01
  - **同步**：GDD §10 指针；M4 设计 D1；开发计划 / README；`avatar.yaml` 注释

- **M4-D03 神识完整公式落地（2026-08-07）**
  - **配置**：`divine_sense.yaml` 阶梯 `overload_bands` + `backlash_table`；青羽鹤 `divine_sense_cost: 4` 覆盖样例
  - **后端**：表驱动超载乘区；硬顶反噬档；快照/开战同公式；`DIVINE_SENSE_STRICT` 仅 DEV 门控是否套战斗衰减
  - **前端**：神识条展示 zone / 乘区 / 反噬摘要（去「占位」文案）
  - **测试**：舒适 / 超载 / 硬顶；物种占用覆盖
  - **文档**：`后续待完成` **M4-D03 已消化**；M4 设计 §6 同步

- **M4-D04c 野外遭遇与捕获落地（2026-08-07）**
  - **配置**：`pet_encounter.yaml`（区×时×天）；`pet_capture.yaml`（全因子/诱灵草/袋/自动捕）；物种 `wild_capture`；道具诱灵草/灵兽袋
  - **后端**：`PetExploreService`；`GET/POST /pets/explore/*`；骰审计 `p/factors/roll/seed`；成功 `spawn_owned_pet(..., wild_capture)`；非 `capture_test`
  - **前端**：灵兽园「野外」Tab；遭遇/捕获/自动捕 + 审计 JSON
  - **测试**：配置外键；捕获审计；缺草 40082
  - **文档**：`灵宠系统设计` v2.1；`后续待完成` **M4-D04c 已消化**

- **PET-D04 丹药喂养落地（2026-08-07）**
  - **配置**：`pet_feed.yaml`；inventory 兽丹 `pet_pill_*`；ADM 域 `pet_feed`
  - **后端**：`feed_counts_json`；单药/总量上限；`POST /pets/{id}/feed`；效果叠面板；超限 `40066` / 缺药 `40055`
  - **前端**：详情「丹药喂养」列表与喂 1 颗
  - **测试**：涨 atk；超单药上限拒绝；背包不足拒绝
  - **文档**：`灵宠系统设计` v2.0；`后续待完成` **PET-D04 已消化**

- **PET-D03 被动与种族天赋落地（2026-08-07）**
  - **配置**：`pet_passives.yaml`；物种 `passive_pool_id`；ADM 域 `pet_passives`
  - **后端**：`racial_talent_id` / `passives_json`；捕获必带天赋、独立可空；combat 进面板；词条 `passive_ref` 解析
  - **前端**：详情展示种族天赋与独立被动
  - **测试**：天赋必带；空抽；HP 含厚皮
  - **文档**：`灵宠系统设计` v1.9；`后续待完成` **PET-D03 已消化**

- **N5 / M4-D04b 灵兽蛋孵化落地（2026-08-07）**
  - **配置**：`pet_eggs.yaml`；inventory `pet_egg` + `egg_fox_trial` / `egg_crane_qing`；物种 `acquire_tags` 含 `egg_hatch`
  - **后端**：`PetHatchJob`；`GET|POST /pets/hatch*`；惰性 settle；领取入园；ADM 域 `pet_eggs`
  - **前端**：灵兽园「孵化」Tab
  - **测试**：蛋→开工→领取闭环；配置外键
  - **文档**：`灵宠系统设计` v1.8；`后续待完成` **N5/M4-D04b 已消化**

- **PET-D06 灵兽宗改词条类型落地（2026-08-07）**
  - **配置**：`pet_sect_reroll.yaml` 启用；`sects.facilities.spirit_beast_sect.enabled=true`；费用 `base_1`/`grow`
  - **后端**：`type_reroll_counts_json`；`POST /pets/sect/affix/reroll-type`；preview/status 真报价；分槽递增费用
  - **前端**：详情可改类型槽「改类型」按钮（费用预览）
  - **测试**：费用公式 + 同槽递增 + 超槽 40061
  - **文档**：`灵宠系统设计` v1.7；`后续待完成` **PET-D06 已消化**

- **PET-D05 灵宠回合制对战落地（2026-08-07）**
  - **配置**：`pet_duel.yaml`（伤害/挣扎/NPC）；ADM 域 `pet_duel`
  - **引擎**：`domain/pet_duel.py`（选招→priority/比速→命中伤害→胜负；seed 可复现；零 board）
  - **API**：`POST /pets/duel/npc/start|auto` · `POST /pets/duel/{id}/turn` · `GET /pets/duel/{id}`
  - **前端**：灵兽园「对战」Tab；开战/选招/自动打完
  - **文档**：`灵宠系统设计` v1.6；`后续待完成` **PET-D05 已消化**

- **PET-D02 灵宠技能竖切落地（2026-08-07）**
  - **配置**：`pet_skills.yaml`（技能+池）· `pet_skill_books.yaml`；背包 `skill_book` 道具；ADM 域 `pet_skills` / `pet_skill_books`
  - **后端**：`skills_learned_json` / `skills_equipped_json`；捕获默认装；`POST .../skills/equip|learn|learn_book`
  - **前端**：详情四栏装备、池领悟、技能书输入
  - **测试**：装备/scope/池外键；字段目录覆盖
  - **文档**：`灵宠系统设计` v1.5；`后续待完成` **PET-D02 已消化**

- **PET-D01 灵宠词条竖切落地（2026-08-07）**
  - **配置**：新建 `pet_affixes.yaml`（类型库/品级区间/洗炼费用）；`pets.yaml` 增 `grade_up`；ADM 域 `pet_affixes`
  - **后端**：`affixes_json` / `value_reroll_counts_json`；捕获按品阶填槽；`POST /pets/{id}/grade-up`；`POST /pets/{id}/affix/reroll-value`（数值-only）；面板叠 flat/pct
  - **前端**：详情词条列表、升阶、按槽洗炼（费用预览）
  - **测试**：`test_grade_up_and_value_reroll` 等；字段目录覆盖 pet_affixes
  - **文档**：`灵宠系统设计` v1.4；`后续待完成` **PET-D01 已消化**

- **N4 / M4-D04a 灵宠热插拔骨架落地（2026-08-07）**
  - **配置**：`pets.yaml` 增 `races` / `grades` / ≥3 物种；`pet_sect_reroll.yaml` 占位；解析校验热插拔
  - **后端**：`pets.grade` 列；`PetDexEntry` 图鉴；`GET /pets/catalog`；`capture_test` 加权抽物种+品阶；灵兽宗 `/pets/sect/affix/*` 桩；战斗面板×品阶乘区
  - **前端**：灵兽园「持有 / 图鉴」Tab；列表/详情展示种族·稀有度·品阶；`PetCatalogPanel`
  - **测试**：`test_pets_sense` / admin 相关 16 项通过
  - **文档**：`灵宠系统设计` v1.3；`后续待完成` **M4-D04a 已消化**；开发计划板块 N 状态同步

- **ADM 双写 + 中文字段 v1.3.3（2026-08-07）**
  - 强制规则写入 [`开发计划.md`](./开发计划.md) **§0.0.1** / [`后台管理系统开发计划.md`](./后台管理系统开发计划.md) **§8.2**：**表格 + JSON** 双写；字段须有中文 `label_zh`/`help_zh`；表格由后端 format 为域 JSON
  - 高危域 **境界 / 挂机速率 / 修为骰** 结构化表格：`GET|PUT /admin/config/{domain}/sheets` + `GET .../schema`
  - **全路径字段目录**：`admin_field_catalog` 展开 YAML 全部可配置路径并配中文；UI 固定「字段说明」页；`admin/dist` 已重建
  - 实现：`admin_field_schema.py` · `admin_sheet_codec.py`；Admin UI「表格编辑」与「JSON 覆盖」；单测 `test_admin_sheets.py` / `test_admin_field_catalog.py`

- **ADM 运行时优化 v1.3.2（2026-08-07）**
  - **封装**：`AdminSpaHost` / `ImmutableAssetsStaticFiles`；`AdminEntryEditor` 组合进配置服务；`RuntimeConfigReloader` 统一热更
  - **减负**：共享 `YamlConfigSource`（mtime 缓存）；`OverlayStore.has`/`get_ref`/`versions_map`；`bundle_summary` 不再全量 snapshot；hashed assets 长缓存
  - 单测：`tests/test_admin_config*.py` 通过

- **ADM 深化 v1.3.1（2026-08-07）**
  - 运营后台前端改由后端 **同端口** 托管：入口 **`/management/`**（`admin/dist`）；API 仍为 `/admin/*`
  - 默认 Axios 基址改为同源相对路径 `/admin`；可选 `npm run dev`（5174）仅用于热更新

- **ADM 深化 v1.3（2026-08-07）**
  - **结构化条目表**：`/admin/config/{domain}/entries` CRUD；Admin UI「条目表」页
  - **导入导出**：JSON/YAML 全文；条目 CSV；剪贴板导出
  - **新域 YAML**：`sects.yaml`（设施闸）· `map.yaml`（区域）· `activity.yaml`（活动占位）进 Bundle
  - **玩家 API**：`GET /api/v1/facilities` · `GET /facilities/map/regions`；灵兽宗桩 `/pets/sect/affix/*` 读设施开关
  - 冒烟 `smoke_adm.py` 覆盖 entries + sects 发布；单测 `test_admin_config_v2.py`

- **ADM 后台管理系统骨架落地（2026-08-07）**
  - **定案**：monorepo `admin/`（端口 5174）+ `backend/app/admin_api/` 前缀 `/admin/*`；独立 `admin_users` JWT（`aud=admin`）
  - **M2-D01**：`app/config_source/`（YamlConfigSource + OverlayStore + deep_merge + 域注册表）；`realm_config._load_yaml` 合并已发布覆盖；发布清 Bundle 缓存
  - **域**：pets / items / techniques / weather / calendar / monsters / formations + 高危 realms/idle/dice（须确认）
  - **能力**：草稿 → 校验 → 发布 → 回滚 → 审计；RBAC（viewer/editor_*/publisher/admin）
  - **冒烟**：`backend/scripts/smoke_adm.py`；单测 `tests/test_admin_config.py`
  - **文档**：[`后台管理系统开发计划.md`](./后台管理系统开发计划.md) **v1.3**；[`开发计划.md`](./开发计划.md) **v2.0**；`后续待完成` M2-D01/ADM 骨架已消化；README 启动说明
  - **环境变量**：`ADMIN_JWT_SECRET_KEY` / `ADMIN_BOOTSTRAP_*` / CORS 含 5174（见 `backend/.env.example`）
  - **职责分离**：DEV `/gm` 仍仅联调；正式改数走后台

- **开发计划 v1.9 · ADM 最高优先级（2026-08-07 · 仅文档）**
  - [`开发计划.md`](./开发计划.md) 新增 **§0.0 强制提示词**：凡可配置需求必须适配后台管理系统
  - 里程碑总览 / **§1.1 ADM** / §20 开工顺序第 1 条升为 **P0**
  - [`后台管理系统开发计划.md`](./后台管理系统开发计划.md) **v1.1** 取消后置；与主计划同步
  - `后续待完成` / README 同步

- **后台管理系统立项（2026-08-07 · 仅文档）**
  - 新建 [`后台管理系统开发计划.md`](./后台管理系统开发计划.md) **v1.0**：独立部署；覆盖灵兽/功法/宗门/地图/怪物/道具/天气等全站内容域；竖切 ADM-0～10；挂 M2-D01
  - [`后续待完成.md`](./后续待完成.md) 登记 **ADM**；灵宠设计 §1.4 / 开发计划 §20 / README 指针同步

- **灵宠 v1.2：热插拔 + 并行不冻结（2026-08-07 · 仅文档）**
  - [`灵宠系统设计.md`](./灵宠系统设计.md)：§1.4 热插拔强制；catalog 派生注册表；灵兽宗 **API 先行**（`/pets/sect/affix/*`）；PET/野外 **不绑** M7/M9
  - [`后续待完成.md`](./后续待完成.md) / M4 §7.4.3 / README 同步

- **灵宠对战模式定案（2026-08-07 · 仅文档）**
  - [`灵宠系统设计.md`](./灵宠系统设计.md) **v1.1** §10：PET-D05 = 神奇宝贝式**简易回合制**（选招→比速→结算）；明确**不**复用自走棋棋盘/AP/移动
  - GDD §11.3、[`后续待完成.md`](./后续待完成.md) PET-D05 验收钩子同步

- **灵宠系统愿景与分期（2026-08-07 · 仅文档）**
  - 新建 [`灵宠系统设计.md`](./灵宠系统设计.md) **v1.0**：宝可梦式遭遇/图鉴、个体品阶、暗黑词条（最多 9）、四技能装备、捕获骰、灵兽宗改类型、1v1；与自走棋边界写死
  - GDD §11 改为框架 + 指针；M4 §7.4 **N4 收窄**（`grade`/catalog 骨架；真词条/技能不进 N4）
  - [`后续待完成.md`](./后续待完成.md) 拆 **PET-D01～D06**；M4-D04c 加厚；§0.1 P0 备注同步
  - 开发计划板块 N / §20 / 附录同步；**无运行时代码变更**

- **M5 优先打磨收口 + 下一会话并行包（2026-08-07）**
  - **M5-D12**：突破结果弹窗展示服务端 `dice`（出目/区间/阈值）
  - **M5-D11**：挂机/离线跨时辰切段 settle；`segments` 明细；`domain/idle_segments.py`
  - **M5-D10**：遮天 `fail_effects` 加权表（升档/云倍/重伤等）；响应 `veil_fail_effect`
  - **M1-D30**：`Idempotency-Key`（突破/PVE/PVP）；前端自动带 Key；CORS 放行
  - **开战修为×环境**：`calendar/weather.yaml` `battle_cultivation`；奖励带 `env_mult` 拆解
  - **M3-D09 取消**：承认「响应全量 + 前端切档」
  - **文档**：[`后续待完成.md`](./后续待完成.md) 新增 **§0.1 下一会话开工包**（★ N4 / M4-D01/D03 / M3-D06～D08 / M5-D05）；开发计划 §20 同步

- **M5 完成度核对与计划同步（2026-08-07）**
  - 结论：主路径 E1～E6 / O–R **已收口**；收口后强化（永久加成/轮回袋/新生商店/阵法 reset·prune/筑基前免费挂机）已落地
  - 文档：`开发计划.md` v1.7；外环设计 v1.4；前端目录 v1.3；挂机/骰子设计各 v1.1；`后续待完成.md` 增 **M5-D11**（切段 settle）· **M5-D12**（突破 dice UI）；延后范围 **D01～D12**
  - README 索引版本号同步

- **修复无化身时棋盘残留化身无法下阵（2026-08-07）**
  - **根因**：预设存 `avatar_{id}`，化身删除后 Bench 变为占位 `avatar`，uid 对不上导致「撤下」不出现
  - **后端**：`list_presets` 前 `prune_invalid_units_from_presets` 自动清洗失效化身/灵宠/傀儡
  - **前端**：Bench 增加「失效棋子」撤下区；棋盘再次点击已选中非本体棋子可撤下
  - **测试**：`test_prune_ghost_avatar_when_no_avatar`

- **轮回后阵法重置 + 筑基前免费挂机（2026-08-07）**
  - **阵法**：`carry.formation=reset`；结算删除前世布阵并重种默认三槽（`formation_id=none` + 本体锚点）
  - **灵石**：`idle.yaml` 锻体/炼气每 tick 消耗改为 `0`；`stones_per_tick_for` 允许 0；`IdleGainCalculator` / 化身 settle 在 cost=0 时按时间片满 tick、不停滞
  - **测试**：`test_pre_foundation_idle_free_and_full_ticks`；祭坛用例断言阵法重置

- **轮回系统强化·持续变强闭环（2026-08-06）**
  - **永久加成表** `character_reincarnation_bonuses`：初始属性 / 小突破成长 / 大突破成长 / 突破成功率；每次轮回按峰值境界自动叠加；商店可再购升级
  - **轮回点**：`base_per_peak_major × path_multipliers`；主动（祭坛/自选）> 死亡强制（仅基础）
  - **携带**：功法 `traits: [reincarnatable]` 保留等级；体质实例保留但装配槽有上限；普通袋清空、轮回袋可带（容量随轮回次数增大）
  - **商店**：固定货架 + 随机商品池（条件过滤）；`POST /reincarnation/shop/refresh` 耗轮回点或仙缘（`fate_luck`）
  - **战力/突破**：境界底 × (1+初始+本世成长)；成功率 = clamp(base + break_rate_bonus)
  - **配置**：全面扩展 `reincarnation.yaml`（`permanent_bonus_on_settle` / `slots` / `bags` / `shop.fixed_items`+`random`）；`techniques.yaml` traits；`inventory.yaml` `bag_allowed`
  - **API**：`shop/buy` 增 `source`；`shop/refresh`；`GET /inventory` 分袋；`POST /inventory/move-bag`
  - **前端**：商店分区+刷新；新生展示永久加成/槽位；预览主动 vs 死亡点数；背包普通袋/轮回袋
  - **测试**：`tests/test_reincarnation_boost.py`

- **轮回新生选角 + 轮回商店（2026-08-06）**
  - **流程**：祭坛/自选/强制轮回结算后 `status=reincarnating`（不再直接 normal）；须在 `/reincarnation?mode=newborn` 选灵根/传承/体质倾向并确认后回 `normal`
  - **保留**：道号只读；体质词条 ORM 继承（新生页只读展示）；轮回点可花
  - **API**：`GET /reincarnation/newborn` · `POST /reincarnation/complete-newborn` · `GET /reincarnation/shop` · `POST /reincarnation/shop/buy`
  - **配置**：`reincarnation.yaml` 增补 `newborn` / `spirit_roots` / `legacy_catalog` / `shop`
  - **前端**：`NewbornSetupPanel` + `ReincarnationShopPanel`；路由对 `reincarnating` 强引导（不可进厅）
  - **错误码**：`40078`～`40081`；测试与 `smoke_m5.py` 已对齐
  - **修复**：两组件补回缺失的 `<script setup lang="ts">`（Vite 将泛型 `<` 误判为标签）

- **文档对齐修为骰子（2026-08-06）**：`开发计划.md` **v1.6 §0.9**；`M5环境与轮回外环设计.md` **v1.3**；`M5前端目录与路由设计.md` **v1.2**（突破/遮天展示纪律与服务端 `dice` 字段）

- **修为骰子系统（2026-08-06）**：境界 YAML 查表上下限 + 功法/体修/气运修正；突破/战斗先攻·伤害·阵法接入；制造失败/遮天/品阶权重走统一 RNG 门面。设计见 [`骰子系统设计.md`](./骰子系统设计.md)；配置 `dice.yaml`；延后 **DICE-R01～R03**

- **挂机速率按境界 + 内外部加成骨架（2026-08-06）**
  - **公式**：`effective = floor(realm_base × channel_mult × env_mult)`；设计见 [`挂机速率与加成设计.md`](./挂机速率与加成设计.md)
  - **配置**：`idle.yaml` 增补 `gain_per_tick_by_realm` / `bonus_channels` / `clamp_*`；未列境界回落 `directions.*_per_tick`
  - **后端**：`gain_per_tick_for`；settle / `idle_env` 按大境界取 base；breakdown 含 `realm_base`；体质通道读装备词条 `effects.idle_mult` 钩子
  - **延后**：装备 / 丹药符箓 / 灵眼 / 洞府 → `后续待完成` **IDLE-R01～R04**
  - **前端**：`IdleEnvPanel` / `idleRateClient` 识别新 source 文案；本片预计叠乘通道
  - **测试**：`tests/test_idle_realm_rates.py`

- **本片预计前端实时算速（2026-08-06）**：「本回合修炼 → 本片预计」按当前时辰/天气在浏览器重算有效产出（`idleRateClient` + `/world/env.idle_preview`），仅展示、不写库；时辰切换不再为此 `fetchMe`，减轻服务器负担

- **雷劫仅跨境（2026-08-06）**：小境界（同大境内层/期进阶）**不再渡劫**，走普通突破；仅元婴→化神起的**跨大境界**进渡劫，首劫后亦仅跨境再渡。`needs_tribulation_for_advance` / `tribulation.yaml`；设计同步 GDD **v4.1** §3.3 · M5 **v1.2** D5 · 开发计划 Q1

- **渡劫准备格消耗说明 + 成功确认突破（2026-08-06）**
  - **准备格**：醒目告警——放入的道具在**开渡后永久消耗、不可取回**；开渡按钮文案同步提示
  - **后端**：`item_uid` 正确写入准备格；开渡时从背包扣除；会话回传 `item_uid`/`item_name` 供 UI 展示
  - **成功后**：进度 100% / `won` 时页内可点「确认突破」；结果弹窗主按钮改为「确认突破」回大厅

- **修复渡劫结算 MissingGreenlet（2026-08-06）**：`resolve-batch` 在 `flush` 后序列化角色时，`updated_at` 等列已过期，同步懒加载触发 `sqlalchemy.exc.MissingGreenlet`。`tribulation` / `ferry` / `reincarnation` 在 `enrich_public` 前先 `session.refresh(character)`。

- **渡劫 strikes_per_batch 防空转（2026-08-06）**：`strikes_per_batch` / `strikes` 必须为正整数；写成小数会被 `int()` 截成 0，每批结算 0 道雷导致 `auto_resolve` 空转。已恢复 YAML 默认值，解析与 `resolve_batch` 强制 `max(1, …)`。降低单雷伤害请改 `power_tiers.*.base_weight` 或 `realm_scale`，不是 `strikes_per_batch`。

- **关键变量中文注释（2026-08-06）**：对照 GDD / M5 设计，为关键字段补中文说明（无逻辑变更）
  - **后端**：`CharacterPublic` / 历法天气 Schema；`Settings` 环境变量；`TribulationSession` 等 ORM；domain 值对象（`ShichenSnapshot` / `EnvLock` / `TribulationDims` / `ReincarnationPlan` / `SettleResult` 等）与 `m4_constants` / `activity_mutex`
  - **前端**：`types/character.ts`、`types/tribulation.ts` 字段 JSDoc

- **M5 验收辅助（2026-08-06）**：
  - GM：`force_tribulation_outcome=won|failed|fallen`；`grant_acceptance_constitution` 发放可镶嵌主/副词条并自动镶嵌
  - `tribulation.yaml` 注明 `fall_on_hp_zero` 与空准备强制陨落验收法
  - 开战/工坊文案明确：**点开战/开工瞬间锁定**环境，进页不锁；战中/任务中天气再滚不改本场

- **config_data YAML 中文字段注释（2026-08-06）**：`backend/app/config_data/` 下全部 21 个 YAML 补全文件头（用途+加载时机）与字段中文注释；数值与结构不变，便于策划直接改表

- **自救消耗与冷却显性化（2026-08-06）**：自救消耗为**灵石**（配置 `spirit_stone_cost: 500`）；两次自救间隔冷却 `cooldown_seconds: 300`。第二次死亡无法自救多为冷却未满或灵石不足（非静默 bug）。UI 展示「消耗 N 灵石 / 当前持有 / 冷却剩余 / 不可用原因」

- **待引渡 CORS/Network Error + 陨落弹窗（2026-08-06）**：
  - **根因**：`ferry_deadline_at`（SQLite naive）与 aware UTC 相减抛 `TypeError` → 500，浏览器表现为 CORS / Network Error
  - **后端**：`ferry_service` / `ferry_rules` 一律 `ensure_aware_utc`；渡劫结束 outcome 带回 `character`
  - **前端**：`FerryDeathDialog`（任意进入 `awaiting_ferry` 弹「前往轮回与引渡 / 关闭」）；渡劫结果弹窗同步；`envelopeFromAxiosError` 网络失败返回可读信封不再裸抛

- **渡劫 NaN + 活动互斥状态机（2026-08-06）**：
  - **渡劫**：`GET /tribulation/me` 前端 `load()` 误把 `{session}` 整包当会话 → HP/进度 NaN；改为解包 + `normalizeTribulationSession`；后端补 `target_label`/`power_label`/`veil_selected` 等别名；prep 接受 `veil_selected`
  - **互斥**：`domain/activity_mutex.py` + `PlayGate.assert_activity`——修炼中禁战/工坊/突破/渡劫；工坊 RUNNING 禁进入修炼；开渡清 `idle_direction`；`CharacterPublic.activity` 显性快照；大厅横幅与按钮门禁
  - **文档**：开发计划 **v1.5 §0.8**；错误码 `40074`～`40077`

- **开发计划 v1.4 · 显性设计原则（2026-08-06）**：`开发计划.md` 增补 **§0.7**——「研究游戏设计」为本玩法之一，禁止隐性数值/黑盒修正；配置须带 catalog 说明字段；新会话/新板块按显性验收清单交付

- **挂机环境预览（2026-08-06）**：`CharacterPublic.idle_env` 与 `/world/env` 暴露时辰×天气×灵根/功法标签有效速率 + catalog 文案；settle 同步吃 tag 乘区；GM 可设 `spirit_root_tags`；列 `spirit_root_tags_json`
  - **前端**：修炼区 `IdleEnvPanel` 展示「基础→有效」速率、乘区拆解、时辰/天气说明（`idle_note` / `spawn_bias_note` / `craft_notes`）；`EnvModifierHint` 优先读 catalog；DEV GM 可写灵根标签
  - **配置录入**：`calendar.yaml` / `weather.yaml` 的 `catalog.*` 字段见 README「环境说明 catalog」

- **修复顶栏天气显示 `[object Object]`（2026-08-06）**：`/world/env` 曾返回嵌套 `{calendar, weather}`，前端把 weather 对象当字符串渲染；改为扁平 `weather`/`weather_label`/`shichen` 契约，前端 store 兼做解包兜底

- **修复 M5 轮回页契约与交互（2026-08-06）**：
  - **根因**：`/ferry/me` 嵌套 `{ferry}` 未解包 → 倒计时无 deadline 误判过期；preview 返回对象型 keep/lose，流水键为 `logs` 而非 `items`；自救/祭坛/入轮回响应缺 `character` 导致状态不同步
  - **后端**：ferry/reincarnation 响应对齐前端类型（FerryPublic 展开、preview keep/lose 列表、logs.`items`、mutation 带回 `character`）
  - **前端**：ferry store 解包/兜底 `fetchMe`；回大厅用 `name:'hall'`；无 deadline 不触发过期；祭坛/待引渡/流水按 mode 正确拉数；待引渡时禁用祭坛
  - 文档：CHANGELOG 本条

- **M5 后端落地（2026-08-06）**：按 `M5环境与轮回外环设计.md` v1.1 竖切 E1～E5（+ E6 联调）
  - YAML：`calendar.yaml` / `weather.yaml` / `tribulation.yaml` / `reincarnation.yaml`；境界链扩至元婴/化神
  - Domain：历法公式、天气加权锁、env 叠加 clamp、渡劫双维/准备格/法宝/引渡/轮回保留表
  - Services：`calendar` / `weather` / `tribulation` / `ferry` / `reincarnation`；突破分流 `needs_tribulation`；挂机择时乘区；工坊/开战环境锁；PlayGate 惰性引渡超时
  - API：`/world/*` `/tribulation/*` `/ferry/*` `/reincarnation/*`；GM 强制时辰/天气/开渡/待引渡/story 节点
  - ORM：角色轮回字段 + `tribulation_sessions` / `reincarnation_logs` / 天气与劫云表；bootstrap 补列
  - 测试：`test_calendar` / `test_weather_lock` / `test_env_modifiers_idle` / `test_tribulation` / `test_ferry_reincarnation` / `test_story_flags`；冒烟 `scripts/smoke_m5.py`；旧挂机测关闭环境乘区以保证确定性
  - 环境变量：`CALENDAR_*` / `WEATHER_ENABLED` / `TRIBULATION_ENABLED` / `WORLD_STATE_BACKEND` / `FERRY_COUNTDOWN_SECONDS` / `REINCARNATION_PET_CARRY`
  - **M1-D21 → 已消化**；**不含** M5-D01～D10（WS、多区域、道友引渡、完整带宠等）

- **M5 前端落地（2026-08-06）**：按 `M5前端目录与路由设计.md` v1.1 实现环境与轮回外环 UI
  - 新路由 `/tribulation` `/reincarnation`；`App.vue` + `WorldClockBar`（`meta.showWorldBar`）
  - 类型/API/Store：`world` / `tribulation` / `ferry` / `reincarnation`；`CharacterPublic` 扩 ferry/轮回点/story_flags/tribulation 等
  - 突破 `needs_tribulation` → `start-prep` 跳转渡劫；待引渡守卫拦积极玩法；`homePathAfterAuth` 状态分流
  - 大厅 `HallEnvGate`；渡劫准备格+双维+批次；引渡倒计时/自救/祭坛；道友引渡灰置（M7）
  - GM（DEV）：强制时辰/天气、开渡、待引渡、超时轮回、标记 story
  - 环境变量：`VITE_WORLD_POLL_MS` / `VITE_FERRY_TICK_MS`
  - **不含**：剧情播放器、道友真引渡、WS 推时辰

- **M5 渡劫玩法加厚 v1.1（2026-08-06，设计-only）**：
  - 雷劫 **威力四档**（天道怜悯/普通/天妒/灭世）× **次数四档**（九/百/千/万劫）；由跨境预估突破品阶映射
  - 渡劫前 **准备格**（按序消耗）；减劫分轴 A（阵法/气运/魔性/遮天降档）与轴 B（功法/护劫道具/普通法宝）
  - 法宝耐久归零永毁 + 基础一击破坏率；**灵宝护主**（毁宝、回 20% HP、威力降档或怜悯档伤害×1%）
  - **锁前天气算数、开渡变劫云**；云内开渡基础值×2；半径 0～4（真邻区 → M5-D08/M9）
  - 千/万劫 **批次自动结算**（禁止逐雷微操）；前端准备/结算分相 UI
  - `后续待完成.md` 增 **M5-D08～D10**；文档：`M5环境与轮回外环设计.md` / `M5前端目录与路由设计.md`

- **M5 设计开篇（2026-08-06）**：
  - [`M5环境与轮回外环设计.md`](./M5环境与轮回外环设计.md)：六时权威时钟、区域天气池与三锁点、环境修正切片、雷劫/渡劫会话、待引渡与轮回保留表、剧情「已历可跳」flag；竖切 **E1～E6**；决策 D1～D12
  - [`M5前端目录与路由设计.md`](./M5前端目录与路由设计.md)：新增 `/tribulation` `/reincarnation`；全局 `WorldClockBar`；大厅 `HallEnvGate`；待引渡路由守卫
  - `后续待完成.md`：新增 **§1.7 M5-D01～D07**；**M1-D21 → 设计中**；M1-D20 挂 M5-D05
  - `开发计划.md` §7 / README：挂上 M5 设计索引；近期开工顺序改为按 E1～E6 实现
  - **实现未开**；不重开 M4 出口

- **开发计划 v1.3（2026-08-05）**：M7 增补 **双修**（板块 WD）——双修功法决定「双人同增」或「单向传修为」；会话内掷骰定效果档与时长；男修/女修各自维护 **一号榜** 与 **零号榜**；创角性别字段（WD0）；化身双修延后为 **M7-D01**；M7 日历约扩至第 21～26 周；`后续待完成.md` / README 同步

- **M4 全面优化（2026-08-05）**：
  - **P0 修复**：离线帽 D10 分列 `avatar_gains` 并入账；`GET /craft/jobs` / `claim` 前惰性 settle；拉角色 / PlayGate 短路径走双线程 settle
  - **封装**：`domain/m4_constants.py`（方向/工坊状态枚举）、`services/m4_features.py`（功能开关）；`PlayGate.prepare_for_play` 统一写路径；灵宠战斗面板 `_stats_for_pet` 单入口
  - **注释**：M4 domain/service 文档字符串统一中文章节（参数/返回/异常/属性）
  - **前端**：`DualIdlePreview` 等类型单源化；`idleLabels` / `petDisplay` 工具；工坊效率文案读配置；删除未使用的 `craftIsDue`
  - 测试：`test_offline_pending_splits_avatar_gains`、`test_claim_auto_settles_running_job`；全量后端通过；前端 `vue-tsc` + `vite build` 通过

- **灵宠物种与获取途径正式规划（2026-08-05）**：文档-only——`M4双线程成长设计.md` §7.4 种族/物种、§7.5 途径矩阵与 N4/N5；`开发计划.md` 增 N4/N5 及 M5 轮回带宠 / M7 宗门兑宠 / M9 野外捕获指针；`后续待完成.md` **M4-D04 拆 a/b/c**；前端目录灵兽园 IA 与进度表同步；**实现未开**，不重开 M4 T1～T6 出口

- **修复灵宠布阵保存失败（2026-08-05）**：前端落子携带 `ref_id`；后端 `UnitPlacement` Schema 增加 `ref_id`（此前被 Pydantic 丢弃导致 `40057 灵宠须指定 ref_id`）；校验层兼容从 `pet_{id}` / `avatar_{id}` 推导

- **修炼区展示化身进度（2026-08-05）**：大厅 `IdlePanel` 分本体/化身两栏，化身线程显示方向、速率、片内进度条与池推算（只读；切方向仍走 `/avatar`）；`dual_idle_preview` 补全化身三向速率/耗石/锚点；`predictAvatarIdleDisplay` + `avatarDisplay`

- **M4 前端落地（2026-08-05）**：
  - 新路由 `/avatar` `/workshop` `/pets`；大厅 `HallDualThreadGate` + `DualIdleSummary` + 顶栏快捷入口
  - 化身：凝练 / 挂机 / 传修为 / `DivineSenseBar`；工坊：五分支配方 / 队列进度 / 领取 / 背包侧栏
  - 灵兽园：列表 / 详情 / 偏好上阵 / 测试捕获（DEV）
  - 布阵：`UnitBench` 分组与灰置原因；`FormationPicker` 阵法等级锁提示
  - Pinia：`avatar` / `craft` / `pets` / `inventory`；API 与 `CharacterPublic` M4 字段对齐
  - GM（DEV）：一键金丹 / 发材料 / 发测试宠 / 清工坊队列
  - 环境变量：`VITE_AVATAR_POLL_MS` / `VITE_CRAFT_TICK_MS`；redirect 白名单扩展

- **M4 双线程成长后端落地（2026-08-05）**：
  - 化身：凝练（金丹门槛 `40050`）、双线程挂机 `settle_dual`、修为互传、神识读数
  - 工坊：五类配方、惰性队列、`craft` 体力消耗、背包入库、阵法等级 `array_craft_level`
  - 灵宠：测试捕获、升级占位、布阵 Bench
  - 布阵/战斗/快照：avatar/pet/真傀儡解禁；神识超载衰减；渡劫禁化身上阵
  - 配置：`avatar.yaml` / `craft_recipes.yaml` / `pets.yaml` / `divine_sense.yaml` / `inventory.yaml`；`realms.yaml` 增金丹占位
  - API：`/avatar/*` `/craft/*` `/inventory/*` `/pets/*` `/formation/bench`
  - 环境变量：`AVATAR_ENABLED` `CRAFT_ENABLED` `PETS_ENABLED` `DIVINE_SENSE_STRICT` `M4_GM_GRANT_MATERIALS`
  - 测试：`test_avatar.py` `test_dual_idle.py` `test_craft.py` `test_pets_sense.py` `test_formation_m4_units.py`
  - 冒烟：`backend/scripts/smoke_m4.py`

- **开发计划 v1.2（2026-08-05）**：M7 社交经济补全——**聊天室**（世界/宗门/私聊+WS）、**邮件与赠送**、**师徒**、**面对面交易**；交易行/拍卖原 W2 保留；出口标准与日历（约第 21～25 周）同步；`后续待完成.md` §3 更新

- **开发计划 v1.1（2026-08-05）**：将「之后」拆为 **M8～M13** 并写入步骤表——自研功法/阵法/符箓（M8）、地图·势力·静态 NPC（M9）、奇遇·任务·剧情管线（M10）、世界 Boss/宗门战/势力战/抢地盘（M11）、AI NPC + AI 天道化身第三方 API（M12）、内容填充与数值案（M13）；原则补充剧情/AI 后置；`后续待完成.md` §3 同步；GDD 仍不写细案（工程排系统）

- **M4 设计开篇（2026-08-05）**：
  - [`M4双线程成长设计.md`](./M4双线程成长设计.md)：化身双挂机、工坊配方、灵宠雏形、神识占位；竖切 **T1～T6**；决策 D1～D10
  - [`M4前端目录与路由设计.md`](./M4前端目录与路由设计.md)：新增 `/avatar` `/workshop` `/pets`；大厅 `HallDualThreadGate`；Bench/阵法锁扩展
  - `后续待完成.md`：新增 **M4-D01～D06**；M3 打磨项标明不阻塞 M4 出口
  - `开发计划.md` §6 / README：挂上 M4 设计索引；前端分步表标「设计中」

- **M3 延后项文档整理（2026-08-05）**：`后续待完成.md` 校正 M3-D03 目标阶段，新增 **M3-D06～D10**（嘲讽/四象加深/部署扩展/report_mode/算法打磨）；`M3战斗成型设计.md` **v1.5**、算法文档 **v2.4** 只保留现行已落地内容，未做细则迁入登记册

### Changed

- **M3 战斗界面优化（2026-08-05）**：图形化棋盘 + 日志框自适应
  - **通用棋盘组件** `components/board/BoardGrid.vue`：7×7 格子层作为固定 UI 恒定渲染（不随棋子变化重建），棋子为绝对定位「加载层」叠加，`left/top` 过渡实现平滑移动动画、TransitionGroup 处理落子/阵亡出入场；深色战棋主题（敌方半区在上暗红、可部署格青绿高亮）、圆形棋子按种类配色（本=青 / 傀=灰 / 化=紫 / 宠=金 / 敌=红）+ 血条
  - **战报播放器图形化**：`BattleReportPlayer` 弃用 `board_text` 字符画，改由 `events` 重放驱动棋盘（`battle_start` 加载站位；`move`/`damage`/`death`/`obstacle_hit`/`abyss_bounce` 逐步演变）；播放游标改为事件粒度，按后端 `render_detailed` 同款规则换算可见日志行，保证画面与日志逐行同步；新增当前回合角标、四象结算行
  - **日志框视口自适应**：详细档日志框高度 `max(240px, calc(100vh - 340px))`——网页全屏（视口更高）时日志框更长；新行自动滚动到底；播放器改为「棋盘左 / 日志右」双栏布局（窄屏堆叠）
  - **布阵编辑器复用**：`FormationBoard` 改基于 `BoardGrid`（外部接口不变），与战报棋盘观感统一；本方在下、敌方在上
  - **修复（后端）**：CORS `allow_methods` 缺 `PUT` 导致浏览器保存布阵预设（`PUT /formation/presets/{slot}`）预检 400 被拦——补入 `PUT`（此前 HTTP 冒烟为同源脚本未暴露）；`tests/test_board_placement.py` 补设计 §12.7 指定的切比雪夫 `(0,0)`→`(5,5)`=5 断言
  - 验证：后端 91 测试通过；`vue-tsc -b && vite build` 通过；浏览器实测注册→布阵（落子/保存/PUT 200）→双狼 PVE→图形化回放（移动动画/血条/阵亡消失/日志同步滚动）全绿

### Added

- **M3 战斗成型前后端落地（2026-08-05）**：S1～S6 六步竖切全部实现
  - **配置**（`config_data/`）：`board.yaml`（7×7 三区 / 默认部署 / 2AP / 命中表 / 伤害骰归一 / 境界上阵上限 / 棋子种类闸门与默认面板）、`formations.yaml`（阵法样本 ×5 + 地形 + 四象层 + 克制表）、`snapshots.yaml`（手动冷却 / 每日定点 / PVP 占位奖励）、`stamina.yaml`（上限 / 恢复速率 / 各行为消耗）；`pve_monsters.yaml` 扩展怪侧棋子编成（`wild_wolves` 双狼样本）与 `stamina_cost`
  - **domain/（纯规则零 IO）**：`board_tables`（位棋盘 + 导入期静态表：正交邻接 / 切比雪夫射程 / 49×49 距离 / 直线中间格）、`board`（占位校验 `40041/40042/40043` + board-meta）、`terrain`（障碍/深渊/禁制揭晓 + 版本化懒重建全源距离表）、`combat_ai`（零搜索查表决策：贴脸攻击 / 最少 AP 接近 / 挡路破障 / 远程 LOS 过滤）、`formation_rules`（四象对抗：得分骰 / 强制生效互抵 / 平票分区 / 效果乘区）、`autochess`（纯函数 `simulate_battle(setup, seed)`：先攻 × 骰、平票双方交错、2AP 行动、命中 d100、伤害骰、深渊弹回、破障揭晓、全量结构化事件 + seq）、`battle_text`（字符棋盘 / 摘要 / DND 式逐回合中文日志）、`stamina`（惰性恢复纯计算）、`snapshot_hash`（快照内容哈希）
  - **db/**：新表 `formation_presets` / `defense_snapshots`；`characters` 补列 `stamina` / `stamina_updated_at` / `trial_puppet_count`（bootstrap 自动补）
  - **services/**：`FormationService`（默认三槽惰性种子 / 预设 CRUD / Bench / 占位与编成校验）、`SnapshotService`（构建 / 手动更新 1h 冷却 `40045` / 状态禁止 `40046` / 每日定点**惰性**补刷幂等槽位）、`StaminaService`（惰性读数 / 开战扣减 `40049` / `STAMINA_ENABLED` 门禁）、`AutochessService`（P0 门禁 → P1 组装 setup → P2 纯函数演算 → P3 结算奖励 + 三档渲染；PVE 走怪配置、PVP 加载对方快照镜像落位 `40047/40048`）
  - **api/**：`/formation/*`（board-meta / presets / validate）、`/snapshot/defense/*`（me / update / {id}）、`/battle/pve`（**升级为棋盘路径**，响应即战报）、`/battle/pvp/attack`、`/battle/pve/monsters`、`/battle/pvp/opponents`、`/battle/stamina`；GM 扩展 `set_stamina` / `trial_puppet_count` / `reset_snapshot_cooldown` / `force_refresh_snapshot`
  - **环境变量**：`STAMINA_ENABLED` / `BATTLE_MAX_ROUNDS` / `SNAPSHOT_MANUAL_COOLDOWN_SECONDS` / `SNAPSHOT_LAZY_DAILY_ENABLED` / `AUTOCHESS_RNG_SEED` / `PVE_REQUIRE_PRESET`
  - **前端**：新路由 `/formation`（7×7 编辑器 / 预设三槽 / 阵法下拉 / Bench / 快照冷却条 / 脏检查离开确认）与 `/battle`（PVE 选怪 / PVP 目标预览攻打 / 体力条 / 本会话战报列表 + 播放器：字符棋盘 `<pre>` + 简易/详细档 + 自动/单步/跳过）；大厅变枢纽（`HallBattleGate` 入口卡 + `BattlePanel` 降级为一键教学战）；`useFormationStore` / `useBattleStore`（`sessionStorage` 战报，登出清除）；redirect 白名单追加 `/formation` `/battle`；GM API 类型同步
  - **测试**：后端 **91 passed**（新增棋盘占位 / 引擎确定性与地形分支 / 体力 / 布阵-快照-PVE-PVP 集成共 4 文件 24 用例；M0～M2 全量回归通过）；前端 `vue-tsc -b && vite build` 通过；新增 `backend/scripts/smoke_m3.py` HTTP 冒烟脚本（注册→布阵→快照→PVE→PVP 全绿）
  - **修复**：`combat_ai.decide_action` 自身格误入候选导致全场发呆（移除 `pos_mask |= 1 << cur`，远程射击位补 LOS 过滤）；`StaminaService` 兼容 SQLite naive datetime

- **M3 设计开篇（2026-08-04）**：
  - [`M3战斗成型设计.md`](./M3战斗成型设计.md)：7×7、布阵、阵法、快照、战报、PVE/PVP
  - **v1.1**：六步竖切 S1～S6；§12 战斗全流程重点板块
  - **v1.2（2026-08-05）**：**DND+自走棋**棋盘；x 三区；默认 6 格；阵法四象
  - **v1.4（2026-08-05）**：障碍/深渊探路揭晓；每回合 2 AP；[`M3自动移动攻击算法设计.md`](./M3自动移动攻击算法设计.md)；决策 **D9**
  - **算法文档 v2.0（2026-08-05）**：实现方案按 CPython 重写（规则不变）——位棋盘 + 导入期静态表；每目标搜索改为全源距离表/空盘闭式（单次决策零图搜索）；桶队列替代 heapq；`Scratch`+版本戳零分配；纯函数 `simulate_battle` + 惰性事件文案；确定性陷阱清单与 GIL/多进程部署口径；成型设计同步 **v1.4.1**（目录增 `board_tables/terrain/combat_ai`，演算层零框架依赖）
  - **算法文档 v2.1（2026-08-05）**：战斗内动态属性机制——L0 开战快照 / L1 修正栈 / L2 脏标记缓存，FLAT/PCT 顺序无关求值，被动/道具/陷阱走开战构建的触发索引，属性变化零距离表失效；§14.0 万人在线容量估算（1 万活跃演算 CPU 约 0.2～8 核，真瓶颈是战报落库与 setup 读）；成型设计同步 **v1.4.2**
  - **算法文档 v2.2（2026-08-05）**：双档战斗日志——`simple`（棋盘+摘要）/ `detailed`（逐回合 DND 式：先攻/命中/伤害/技能检定含骰点与中间量、深渊通过/弹回、破障/无法破坏等全量渲染）；开局棋盘 7×7 字符画（棋子名与「障/渊/封」写在格内，不泄露未知属性，天气/环境/效果文字说明）；容量口径改 **人均 10～30 s/场**（峰值 1000 场/s），落库定为 `summary+setup+seed`（≈2～5 KB/场），详细日志靠确定性重演再生；新增 `domain/battle_text.py` 渲染器；成型设计同步 **v1.4.3**（§7.7 双档 + §7.8 落库列调整）
  - **算法文档 v2.3 + 成型设计 v1.4.4（2026-08-05）**：**战报零保留**——响应即战报，浏览器 `sessionStorage` 自存（登出/关闭销毁）；服务器不落任何战斗日志（`battle_reports` 表与 `GET /battle/reports*` 端点移除，v2.2 的 summary+setup+seed 落库方案废止；守方过程可见性登记 **M3-D04**）；**体力系统 D10**（成型 §12.9）——`stamina.yaml` + 角色 `stamina`/`stamina_updated_at` 惰性恢复 + P0 开战扣减 + `40049`，日总量天然封顶并兼作权威限流（容量口径见算法文档 §14.0：日志写入 0 字节，DB 只剩结算小事务）；S4 重定义为「战报回放（会话内）+ 体力」；前端目录设计同步（移除 reports 端点、`sessionReports`+`StaminaBar`、留存策略明示文案）；`后续待完成.md` 新增 **M3-D04 / M3-D05**
  - [`M3前端目录与路由设计.md`](./M3前端目录与路由设计.md)：`/formation` `/battle`；进度对齐六步与坐标/演算
  - `后续待完成.md`：D10～D13、D31 设计中；**M3-D01** / **M3-D02**（完整 LOS 延后）

### Changed

- **设计文档同步 OOP（2026-08-04）**：M0/M1/M2 设计与前端目录文档、`开发计划.md` §0.6、`后续待完成.md`（M2-D00 已消化 / M2-D01 仍待做）、README 后端架构对照已更新

- **注释中文化（2026-08-04）**：`backend/app/core/deps.py` 各 `get_*_service` 文档字符串改为中文

- **延后项登记（2026-08-04）**：`后续待完成.md` 新增 **M2-D01**（玩法配置源抽象：现行 YAML 底表；运营化后再考虑 `ConfigSource` + 可选 DB 覆盖；勿过早全量进库）

- **后端面向对象抽象（2026-08-04）**：
  - **基础设施**：`core/time_utils.py`；`db/bootstrap.py`（自 `main` 迁出启动补列/迁移）；`deps.get_*_service` 全覆盖
  - **domain/**：`idle`（SettleResult / IdleGainCalculator / OfflinePending）、`combat`（CombatCalculator）、`breakthrough`（BreakthroughPreview）
  - **应用服务类**：`IdleService` / `PlayGate` / `CharacterService` / `AuthService` / `VerificationService` / `BattleService` / `BreakthroughService` / `AllocateService` / `GradeService` / `TechniqueService` / `ConstitutionService` / `GmService`
  - **核验**：`SmsProvider` / `EmailProvider` / `IdentityProvider` Protocol + Provider 实现类
  - 路由统一 `Depends` 注入；模块级函数保留为兼容包装；API 行为与错误码不变；测试 **63 passed**

### Fixed

- **M2 审查修补（2026-08-04）**：
  - **离线帽入口**：`/characters/me`、`/idle/sync`、切方向改为先 `prepare_offline_or_settle`（长缺口写 pending），禁止先无帽 `settle_idle` 绕过 12h
  - **迁移**：`realm_progress` 仅在本启动刚补列时迁一次，并写入 `schema_migrations`；已是 M2 库不再扫「池>0」误迁未分配修为
  - **战力统一**：`enrich_character_public` / `build_combat_stats`；idle / allocate / battle 与 `/me` 一致；PVE 用修正后 atk/hp
  - **claim**：灵石不足 → `40038`，禁止扣成负；体质同名不可重复镶嵌、本体 `kind=body` 不可装主副格
  - **前端**：pending 停实时/预测；IdlePanel 全方向含停止禁用；战报回合摘要；事件日志环形 200 条；品阶历史可展开；池「推算 / 已入账」标注
  - **GM**：可选 `GM_ALLOWED_USER_IDS` 白名单（`40311`）；OpenAPI `version=0.3.0-m2`
  - 测试全量 **63 passed**；`vue-tsc --noEmit` 通过

### Changed

- **战斗战报改走事件日志（2026-08-04）**：开战不再弹窗；回合文本与胜负奖励写入大厅事件日志；删除 `BattleReportDialog.vue`

- **大厅事件日志半窗自适应（2026-08-04）**：
  - **仅**事件日志：`sticky` + 高度 `50vh`，溢出在日志窗内滚动；本会话日志环形上限 200 条
  - 左侧操作区 / 页面宽度恢复原样（`max-width: 1100px`，左列 `280～380px`）
  - 日志贴底显示、新条目往上顶；始终跟到底部最新一行

### Added

- **M2 成长深度前端（2026-08-04）**：
  - 大厅无新路由：`IdlePanel` 三向；`OfflineClaimDialog` 进厅自动弹；`AllocatePanel` / `ConstitutionPanel`
  - `CharacterPanel`：境界进度 / 三池 / 品阶 / 神通空槽；`idlePredict` 支持三向 + 冻结 pending
  - API：`idle` offline preview/claim、`allocate`、`techniques`、`constitution`；GM 扩展；`VITE_OFFLINE_AUTO_OPEN`
  - `vue-tsc --noEmit` 通过

- **M2 成长深度后端（2026-08-04）**：
  - 配置：`idle.yaml` 三向 + 按境界耗石；`offline.yaml` / `techniques.yaml` / `constitution.yaml` / `grades.yaml`；`breakthrough.yaml` 移除 `fixed_grade`
  - 模型：`realm_progress`、品阶/会员/离线 pending 列；`character_techniques` / 体质表 / `breakthrough_grade_history`
  - 服务：三向 `settle_idle`、离线 preview/claim、`allocate_service` / `technique_service` / `constitution_service` / `grade_service`
  - API：`/idle/offline/*`、`/allocate`、`/techniques/me`、`/constitution/*`、`/breakthrough/grades/history`；GM 扩展 M2 字段
  - 启动迁移：SQLite 补列 + M1 修为 → `realm_progress` 一次性迁移
  - 测试：`test_offline_cap` / `test_allocate` / `test_constitution` / `test_breakthrough_grade`；全量 **56 passed**

### Changed

- **结算模型文档正名（2026-08-04）**：与代码对齐——现行为「客户端预测展示 + 服务端惰性权威入账 + tick 对齐 `/idle/sync`」，废弃「固定 5s 轮询惰性结算」表述。
  - 更新：`M1核心循环设计.md` §4 / `M1前端目录与路由设计.md` §4.3 / `M2成长深度设计.md` §4 / `M2前端目录与路由设计.md` §4.4 / README / `后续待完成.md`
  - `idle_service` 模块注释同步；算法本身未改

### Added

- **M2 设计文档两件套（2026-08-04）**：先定契约与大厅落点，后实现前后端。
  - `M2成长深度设计.md` / `M2前端目录与路由设计.md`
  - `后续待完成.md`：M1-D01～D05、M1-D32 自设计中 → **已消化**（实现完成后）

### Changed

- **M1 里程碑收口（2026-08-04）**：
  - README / 前端设计 §9.3：进度改为「M1 已验收收口」；下一步指向 M2 + `后续待完成.md`
  - 补跨境单测：炼气圆满 → 筑基初期；筑基后再突破 → `40026`
  - 删除无引用 `IdlePanelPlaceholder.vue` / `HelloWorld.vue`
  - 测试基建：`tests/async_db.py` 在 `asyncio.run` 结束前 `dispose` 引擎，消除 aiosqlite 线程告警；全量 **43 passed**

### Added

- **修炼双进度条体感实时（2026-08-04）**：
  - IdlePanel「本回合修炼」片内进度条（0→满，默认 60s），满片闪示并入总进度；CharacterPanel 总修为条继续用预测值
  - `idlePredict` 增加 `tick_progress_ratio` / `seconds_into_tick` / `tick_seconds`；片内条只驱动动画，修为仍按整片累加
  - `VITE_IDLE_PREDICT_MS` 默认改为 `250`（仅本地刷新，不增加 HTTP）；权威仍惰性结算 + tick 对齐 `/idle/sync`
  - 文档：`README` / `M1核心循环设计` / `后续待完成` M1-D33 笔记同步（真 WS 仍 M6）

### Fixed

- **挑战浊气蛙 `__vnode` 报错（2026-08-04）**：`BattleReportDialog.startReveal` 误写 `props.value.length`（props 非 ref），打开战报时抛错导致 Vue patch 失败；改为 `lines.value.length`，并 `nextTick` / `destroy-on-close` / `append-to-body`。

### Changed

- **修炼实时机制（无手动同步，2026-08-03）**：
  - 去掉修炼区「同步」按钮；客户端按 tick 公式预测展示修为/灵石；到点才 `POST /idle/sync` 入账
  - idle 响应增加 `next_tick_at`；无完整 tick 时 sync 不改 `updated_at`
  - 可见页/修灵中才调度；停滞/未修炼不拉；0～2s jitter；`VITE_IDLE_POLL_MS` 改为兜底对表间隔（默认 120s）
  - 突破预览仍只跟权威 `character`，不跟预测每秒刷
  - 真 WS/SSE 推送登记为 `后续待完成.md` M1-D33 → M6

- **大厅体验修正（2026-08-03）**：
  1. 全局页面可纵向滚动（`html/body/#app`），大厅日志区随视口高度自适应滚动
  2. 突破预览去掉「刷新预览」按钮，随角色修为/灵石/境界变化自动同步
  3. 修炼中（`idle_direction != none`）禁止开战：后端 `40022` + 前端按钮禁用
  4. UI 文案「挂机」统一改为「修炼」（含方向展示「未修炼」）

### Added

- **M1 核心循环前后端实现（2026-08-03）**：挂机 → 突破 → 教学 PVE 可本地联调。
  - **后端**：`app/config_data/`（realms / idle / breakthrough / pve_monsters YAML）；`realm_config` / `idle_service`（惰性结算）/ `breakthrough_service` / `battle_service` / `gm_service`；路由 `/idle` `/breakthrough` `/battle` `/gm`；`CharacterPublic` 扩展进度/停滞/攻防；`GET /characters/me` 先 settle；Settings：`IDLE_TICK_SECONDS` / `GM_ENABLED` / `BREAKTHROUGH_RNG_SEED`
  - **前端**：`IdlePanel` 替换占位；`BreakthroughPanel` + 假读条弹窗；`BattlePanel` + 战报；`CharacterPanel` 进度条；大厅轮询 `VITE_IDLE_POLL_MS`；DEV `GmDevPanel`；无新路由
  - **测试**：`test_idle_settle` / `test_breakthrough` / `test_battle_pve`；全量 **39 passed**
  - 延后项仍见 `后续待完成.md`（未提前实现棋盘/三向/离线帽等）

- **M1 设计文档三件套（2026-08-03）**：尚未写玩法代码，先定契约与延后边界。
  - `M1核心循环设计.md`：配置驱动境界；惰性挂机结算；同步突破；数值对撞 PVE；API `/idle` `/breakthrough` `/battle` `/gm`
  - `M1前端目录与路由设计.md`：不新增路由；大厅替换挂机占位并加突破/战斗面板
  - `后续待完成.md`：跨里程碑延后项活文档（棋盘→M3、三向/离线帽→M2 等）；**每次开新设计前必读**
  - `README.md` 文档表与当前进度已指向上述文件

### Fixed

- **登录/refresh 携带 `has_character`（2026-08-03）**：`TokenPayload` 增加字段，登录分流不再依赖额外 `/me`；前端兼容缺字段时回退拉 `/me`。刷新页面仍走 `/auth/me`。
- **登录后总是进创角页（2026-08-03）**：`login()` 未刷新 `has_character`，且 `ensureSession` 在残留 `false` 时短路径跳过 `/me`，导致已有角色仍被送去创角。现登录后强制清缓存并拉 `/me`；401 refresh 失败同步 `logout` 清内存态。（已被「响应带 has_character」取代为更优方案，清缓存/logout 逻辑仍保留）
- **SQLite 相对路径随 cwd 漂移**：`DATABASE_URL=sqlite+aiosqlite:///./xiuxian.db` 现锚定到 `backend/` 绝对路径；已将仓库根目录误生成的库复制到 `backend/xiuxian.db`。

### Added

- **M0 角色创建 + 空大厅正式联调（2026-08-03）**：移除前端 Demo，对接服务端权威角色数据。
  - 后端：`characters` 表、`character_service`、`POST /characters`（201）、`GET /characters/me`；默认锻体一层 / 灵石=`INITIAL_SPIRIT_STONES` / 未挂机；错误码 `40003`/`40004`/`40005`；`/auth/me.has_character` 真实查询
  - 前端：创角页调真实 API；大厅左栏「角色属性」+「挂机区」占位，右栏「事件日志」窗；删除 `characterDemo` / `VITE_CHARACTER_DEMO`
  - 测试：`tests/test_character.py`（6 passed）；与既有核验测试合计 29 passed

### Fixed

- **健康检查路径澄清（2026-07-31）**：正式路径为 `GET /api/v1/server/health`；补回根路径 `GET /health` 别名以对齐 README；前端 ERR_NETWORK 文案改为提示「连不上 :8000」而非「路径错误」。

### Added

- **前端创角 Demo（2026-07-31）**：在后端 `characters` API 未上线前，用 `localStorage` 跑通创角→大厅。（**已于 2026-08-03 由正式 API 取代并移除**）
  - `types/character.ts`、`api/character.ts`、`stores/character.ts`、`utils/characterDemo.ts`
  - `CreateCharacterView`（道号校验 + 踏入仙途）、`CharacterPanel`、`IdlePanelPlaceholder`、`HallView` 绑真实字段
  - 路由守卫：无角色禁入大厅、有角色禁入创角；`auth.setHasCharacter` + demo 水合覆盖 `/me.has_character`
  - 开关 `VITE_CHARACTER_DEMO`（默认 `true`）；`.env.example` / README 已说明

### Changed

- **鉴权去用户名（2026-07-30）**：注册/登录不再使用用户名；账号以邮箱 + 手机号标识。
  - 注册：必填 `password` + `email` + `phone`（DEBUG 下三票仍可省略；正式模式仍须实名+三票）。
  - 登录三种方式：`login_method=password`（`account` 为邮箱或手机 + `password`）、`login_method=sms`（`phone` + `sms_code`）。
  - 响应用户摘要改为 `email` / `phone` / `display_name`（`/auth/me`、登录/刷新同结构）。
  - 前端 `LoginView`：密码登录 / 短信登录切换；注册表单去掉用户名。
  - 测试 `tests/test_verification_auth.py` 更新并新增密码/短信登录用例（**23 passed**）。

### Added

- **退出登录（2026-07-31）**：创角页 / 大厅页顶栏 `AuthSessionBar`；点击「退出登录」调用 `authStore.logout()` 清除令牌与用户态，并 `replace` 到 `/login`。
- **注册表单可配置开关（2026-07-31）**：`REGISTER_REQUIRE_PHONE` / `REGISTER_REQUIRE_REAL_NAME` / `REGISTER_REQUIRE_EMAIL_CODE`（默认全关）；`GET /verification/modes` 下发开关；前端注册顺序为邮箱 → 手机(可选) → 密码 → 实名(可选)；开启邮箱核验时点击注册弹窗填邮箱验证码；全关则仅邮箱+密码可注册。
- **保留登录状态闭环（2026-07-30）**：路由 `meta` + `beforeEach`（受保护页校验令牌、`ensureSession`/`fetchMe`、已登录访问登录/注册自动分流、根路径按会话跳转）；登录成功尊重安全 `redirect`（`utils/safeRedirect.ts`）；auth store 增加 `hasCharacter` / `ensureSession` / `homePathAfterAuth`。令牌层（`remember_me` + local/session Storage + 401 refresh）沿用既有实现。
`LoginView` 增加邮箱/手机/实名/身份证；「发送验证码」对接 `/verification/sms|email/send`；提交前 confirm + `id/submit` 换三票再 `POST /auth/register`；新增 `api/verification.ts`、`types/verification.ts`。
- **核验模块 + 超级密码（Task 3–6 汇总，2026-07-28）**：独立 `/api/v1/verification/*`（modes / sms / email / id）；Provider 层（国标身份证 A、短信/邮件 debug、B/C stub）；编排服务（发码、确认、ticket、注册前 `assert_register_tickets`）；注册扩展 email/phone/实名/三票；`SUPER_PASSWORD` 超级密码登录；集成测试 `tests/test_verification_auth.py`（7 项）+ `tests/test_id_format.py`（13 项），**共 20 passed**。
- 注册改造 + 超级密码登录（Task 6）：`RegisterRequest` 扩展 email/phone/实名/三票；`register_user` 调 `assert_register_tickets`、邮箱手机查重 `40013`、成功后消费 ticket；`login_user` 支持 `SUPER_PASSWORD`（`secrets.compare_digest` + WARNING，禁用号仍 `40300`）；集成测试 `tests/test_verification_auth.py`。
- 核验 HTTP API（Task 5）：`app/api/verification.py` 挂载 `GET /modes`、`POST /sms/send|confirm`、`/email/send|confirm`、`/id/submit`；经 `api_router` 纳入 `{API_PREFIX}/verification`；统一 `success()` / `AppError` 信封；DEBUG 固定码 `000000` 可联调出 ticket。
- 核验编排服务（Task 4）：`app/services/verification/service.py` 实现发码 / 确认 / `submit_id` / `assert_register_tickets` / `get_modes`；`app/schemas/verification.py` 请求响应 Schema；验证码 bcrypt 哈希、发送间隔 `40011`、错码/过期 `40010`、ticket `40012`、正式缺材料 `40017`；DEBUG 固定码 `DEBUG_VERIFY_CODE`。
- 核验 Provider 层（Task 3）：`app/services/verification/` 含国标 18 位身份证校验（GB 11643）、`hash_id_card`/`mask_id_card`、身份核验工厂 `verify_identity`（format / two_factor / real_person）、短信/邮件 debug 发送与 aliyun/tencent/resend 骨架（50100）；单元测试 `tests/test_id_format.py`。
- `Settings` 扩展核验与超级密码项：`SUPER_PASSWORD`、`ID_VERIFY_MODE`、`ID_CARD_HASH_SALT`、SMS/Email/二要素/实人 provider、验证码与票据 TTL、`DEBUG_VERIFY_CODE`；`backend/.env.example` 同步注释说明。
- 设计规格：`docs/superpowers/specs/2026-07-28-verification-super-password-design.md`（注册邮箱/手机/身份证 A·B·C 可插拔核验、独立 verification API、DEBUG 跳过、超级密码）；状态 **已实现**（2026-07-28）。
- 后端登录闭环：`POST /auth/login`（含 `remember_me`）、`POST /auth/refresh`、`GET /auth/me`；JWT access/refresh（PyJWT）；`get_current_user` 依赖。
- 前端保存登录态：`utils/storage` 按记住登录选择 local/session Storage；Pinia `stores/auth`；`main.ts` 启动恢复令牌；`http` 拦截器 401 自动 refresh；`LoginView`「记住登录」勾选。
- `M0前端目录与路由设计.md` §7：开发进度与步骤 3 完成清单、下一步创角建议。

- `LoginView`「检测状态」：调用 `GET /api/v1/health`，将 `app`/`env`/`status`/`db`/`time` 写入 `tipMessage`，由已有 `el-alert` 展示；修正 `api/server.ts` 为无参 GET（原误写 POST `/auth/health`）。

- `Settings` 改为按 `backend/.env` 绝对路径加载，避免 PyCharm 工作目录非 `backend` 时出现 `JWT_SECRET_KEY` Field required。
- 前端 `src/` 备注（模块说明、JSDoc、空壳注释）统一改为中文；标识符与接口字段名保持英文。
- 后端 `app/` 源码备注（模块说明、docstring、行内注释）统一改为中文；标识符与对外 message 英文/中文约定保持不变。
- 后端 M0：`.env`/Settings、异步 SQLAlchemy(SQLite)、`users` 表启动建表、bcrypt 哈希、`POST /api/v1/auth/register`（统一信封；重名 `40001`）、`/health` 探测数据库。
- `M0前端目录与路由设计.md`：标注针对 **M0**、设计日期 **2026-07-27**；约定 `src` 目录职责与 `/login` 等路由对应文件。
- `LoginView.vue`：表单区全面改为 Element Plus（`el-card` / `el-form` / `el-input` / `el-button` / `el-alert` 等），移除自定义 class 与 `<style scoped>`。
- `LoginView.vue`：同页切换登录/注册/忘记密码表单 + 游客登录入口；对接 `api/auth`（注册成功切回登录；登录成功存 JWT 并跳转大厅或创角）。忘记密码与游客登录为占位提示（M0 后端无对应接口）。
- 前端路由挂上 M0 四页：`/login`、`/register`、`/create-character`、`/hall`；`/` 暂重定向登录；保留 `/test`；`App.vue` 改为 `<RouterView />`，`main.ts` 已 `use(router)`。
- 按该设计在 `frontend/src` 创建空壳：`api/auth|character`、`stores/*`、`types/*`、`utils/storage`、`views/*View`、`components/CharacterPanel|IdlePanelPlaceholder`（仅占位注释，未实现逻辑）。
- 前端学习资源：`src/assets/currency/`（coin、spirit-stone）、`src/assets/ui/`（panel-frame、button-bg）；演示页 `src/test/test.vue`（`App.vue` 临时引用以便预览）。
- `frontend/`：Vue 3 + Vite + TypeScript 脚手架（用户可重建模板后继续学习）。
- `frontend` 健康检查页（`/`、`/health`）：浏览器请求 `GET /health`，展示统一响应包字段。
- `frontend/.env.example`：`VITE_API_BASE_URL`、`VITE_HEALTH_URL`。
- 后端 `app/main.py`：CORS（`localhost`/`127.0.0.1:5173`）+ 动态 UTC 时间的 `/health` 信封。

### Changed

- Task 7 文档收尾（2026-07-28）：`README.md` 增补 DEBUG 跳过说明、核验 API 表、超级密码注意事项、第三方 Provider 推荐；`M0前端目录与路由设计.md` §7 步骤 3.5 标 **已完成**；设计规格状态行 → 已实现。

### Fixed

- `LoginView`：底部「游客登录 / 检测状态」改为纵向 `el-space` + `fill`，避免 `el-button` 默认 `inline-flex` 导致未对齐。
- Task 6 评审 Important：`login_user` 先检查 `is_active` 再写 `super_password_login` WARNING（禁用号不产生成功态审计）；正式模式强制 `real_name`（缺则 `40017`，对齐设计 §5）；补测 email/phone `40013`、禁用号+超密 `40300`。

- `src/test/test.vue`：面板/按钮改为「img 底图 + 文字叠加」；SVG 提高对比度；`import ...?url` 明确取资源地址（原先深色底图在暗色主题下几乎看不见，易被误判为背景未生效）。
