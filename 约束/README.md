# 约束（规则 + Skills）

本目录是 **给人看的正文**。Cursor 实际自动加载的是隐藏目录：

| 本目录 | Cursor 加载路径 | 作用 |
| --- | --- | --- |
| [`AGENTS.md`](./AGENTS.md) | 仓库根 [`../AGENTS.md`](../AGENTS.md) | 每轮对话都会读到的总宪章 |
| [`rules/`](./rules/) | [`.cursor/rules/`](../.cursor/rules/) | 项目 Rules（`alwaysApply` / glob） |
| [`skills/`](./skills/) | [`.cursor/skills/`](../.cursor/skills/) | 项目 Skills（按任务触发） |

**改约束时两处一起改**（或改完本目录后复制到 `.cursor/`）。只改 `约束/`、不改 `.cursor/`，Cursor 不会自动生效。

配置步骤见仓库根 [`Cursor约束配置说明.md`](../Cursor约束配置说明.md)。
