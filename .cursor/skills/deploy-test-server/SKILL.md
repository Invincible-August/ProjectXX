---
name: deploy-test-server
description: Update or restart the Ubuntu test server with conda, screen, and Nginx. Use when the user asks to 更新测试服, 重启后端, deploy to 8080/8100, or follow 测试更新指令.
---

# 测试服更新

**先完整阅读并执行** [`设计文档/测试更新指令.md`](../../../设计文档/测试更新指令.md)，不要凭记忆改端口或跳步。

## 硬约束

- 币安监控占用 **:5000**，全程不要改、不要停
- 本项目后端：本机 `127.0.0.1:8100`（screen 内 uvicorn）
- 对外：Nginx **8080**（玩家静态 + 反代 API/后台）
- 玩家：`http://101.36.105.109:8080/`
- 后台：`http://101.36.105.109:8080/management/`
- 本地 8000 / 5173 与测试服无关

## 做法

1. 按用户改动范围选择文档里的「完整更新」或「按改动范围精简步骤」
2. `git pull` 后按文档重启 uvicorn / 构建 admin 与玩家前端
3. 用文档中的 `curl` / 健康检查验证，不要只报「应该好了」
