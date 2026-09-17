# 在 Cursor 中使用本仓库的约束与 Skills

本仓库已经按 Cursor 官方目录放好了规则和 Skills，**用 Cursor 打开本仓库根目录即可生效**，一般不用再点设置。下面说明「已经接好了什么」以及「你想改/加的时候怎么配」。

## 1. 目录约定

| 路径 | 谁读 | 作用 |
| --- | --- | --- |
| `AGENTS.md`（仓库根） | Cursor / 兼容 AGENTS.md 的 Agent **自动读** | 每轮对话的总宪章 |
| `约束/` | 人 + Agent 按需打开 | 规则与 Skills 的可读正文（源码整理） |
| `.cursor/rules/*.mdc` | Cursor **自动加载** | 项目 Rules：`alwaysApply` 或按打开的文件 glob 生效 |
| `.cursor/skills/*/SKILL.md` | Cursor **自动发现** | 项目 Skills：匹配到任务描述时再读全文 |
| `设计文档/` | 人与 Agent | GDD、开发计划、各系统设计（不是约束） |

`.cursor` 在资源管理器里可能是隐藏文件夹。可在仓库根打开 `约束/`，内容应与 `.cursor/rules`、`.cursor/skills` **保持一致**。

```
ProjectXX/
├── AGENTS.md                      ← 打开仓库就会进 Agent 上下文
├── Cursor约束配置说明.md          ← 本文
├── 设计文档/                      ← 设计稿
├── 约束/
│   ├── AGENTS.md
│   ├── rules/*.mdc
│   └── skills/<name>/SKILL.md
└── .cursor/
    ├── rules/*.mdc                ← Cursor 真正扫描这里
    └── skills/<name>/SKILL.md
```

## 2. 规则（Rules）—— 通常不必配置

### 已经生效的方式

1. 用 Cursor **打开文件夹 `D:\ProjectXX`**（必须是仓库根，不要只开 `frontend/` 子目录）。
2. 项目规则文件在 `.cursor/rules/`，带 YAML 头：
   - `alwaysApply: true`：每条对话都带上（核心信条、git add）。
   - `globs: frontend/**/*.vue` 这类：只有打开/编辑匹配文件时才带上。

### 在 Cursor 里确认是否加载

1. 打开 **Cursor Settings**（`Ctrl + ,` 或 `File → Preferences → Cursor Settings`）。
2. 搜索 **Rules**（有的版本在 **Agents** / **General → Rules**）。
3. 应能看到 **Project Rules** 列表，包含例如：
   - `core-commandments`
   - `git-stage-new-files`
   - `backend-conventions`
   - `frontend-display`
   - `admin-ops` / `admin-api`
4. 需要临时关掉某条时，在该列表里禁用即可；不要删仓库里的文件，除非你确定要改约定。

对话里也可以 `@` 某个 `.mdc` 规则，强制本轮采用。

### 用户级规则（可选，全项目生效）

若希望「即使用别的仓库也遵守中文沟通」这类个人习惯：

1. Cursor Settings → **Rules** → **User Rules**
2. 写在用户规则框里（存在本机，不进 git）

项目强制玩法约定（后台适配、中文信条等）**请留在本仓库** `.cursor/rules/`，不要只写在 User Rules，否则换机器/协作者会丢。

### 新增一条项目规则

1. 把 `.mdc` 写到 `约束/rules/`（正文）。
2. **同样一份**复制到 `.cursor/rules/`（Cursor 只扫这里）。
3. 文件头必须包含：

```yaml
---
description: 一句话说明何时使用
globs: backend/**/*.py    # 可选；按文件类型生效时填写
alwaysApply: false        # 横切禁令才设 true
---
```

4. 一条规则只管一件事，尽量短。改完无需重启 Cursor，新对话会读到。

## 3. Skills —— 通常不必配置

### 已经生效的方式

项目 Skills 在 `.cursor/skills/<技能名>/SKILL.md`。Cursor 会读 `description` 判断要不要打开该技能。

当前已放：

| Skill | 何时会用到 |
| --- | --- |
| `vertical-slice` | 新玩法/新板块竖切、联调验收 |
| `admin-content-domain` | 新后台内容域、双写、配表 |
| `deploy-test-server` | 更新/重启测试服 |

你也可以在对话里 **点名**：`按 vertical-slice 做这一块` 或 `@vertical-slice`。

### 在 Cursor 里确认 Skills

1. Cursor Settings 搜索 **Skills**（或 **Agents → Skills**）。
2. 应列出本仓库 Project Skills。若某条被关掉，打开开关即可。
3. 个人 Skills 在用户目录 `~/.cursor/skills/`（Windows 一般为 `C:\Users\<你>\.cursor\skills\`），跨仓库可用；**本项目约定请用项目 Skills**，方便进 git。

### 新增一个项目 Skill

1. 建目录 `约束/skills/my-skill/SKILL.md`。
2. 复制到 `.cursor/skills/my-skill/SKILL.md`。
3. 文件头：

```yaml
---
name: my-skill
description: 做什么，以及何时使用（含触发词）。第三人称。
---
```

4. **不要**加 `disable-model-invocation: true`，否则模型不会自动选用，只能你手动 @。
5. 新开一条 Agent 对话后再试（当前对话可能仍用旧的技能列表）。

## 4. `AGENTS.md` —— 不用配路径

仓库根的 `AGENTS.md` 会被 Cursor（以及同样约定的 Codex 等）当作项目说明书自动纳入。

不要删根目录这份去只留 `约束/AGENTS.md`：后者给人浏览，前者才是自动入口。两份内容应保持同义。

## 5. 常见问题

**Q: 我只改了 `约束/rules`，Agent 怎么还不听？**  
A: Cursor 不扫描 `约束/`。请同步复制到 `.cursor/rules/`，并开 **新对话**。

**Q: 规则会不会把上下文撑爆？**  
A: `alwaysApply` 的规则每轮都会带上，所以写得很短。前端/后端细则用 glob，只有改到对应文件才加载。长作业流放 Skills，不要塞进 alwaysApply。

**Q: 能不能把 `.cursor` 改成别的文件夹名？**  
A: 不能。Cursor 只认项目根下的 `.cursor/rules` 与 `.cursor/skills`。`约束/` 只是给人看的镜像。

**Q: 子目录打开项目会丢规则吗？**  
A: 会。请始终打开仓库根 `ProjectXX`。

**Q: 设计文档要不要配进 Cursor Docs？**  
A: 不必为了约束再配一遍。需要某篇设计时在对话里 `@设计文档/xxx.md` 即可。若要做全局语义检索，可在 Cursor Settings → **Indexing & Docs** 确认本仓库已被索引。
