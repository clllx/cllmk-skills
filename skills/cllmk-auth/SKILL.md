---
name: cllmk-auth
metadata:
  version: "3.5.0"
description: "cllmk 鉴权兼容入口：将登录、登出、会话状态检查、HTTP 401/403 处理意图路由到 `ats/references/foundation/auth.md`，规则单一事实来源在 `ats` skill，本 skill 不存放逻辑。"
---

# cllmk 鉴权兼容入口

> 🔀 本文件只是**路由指针**，不存放任何鉴权逻辑。规则单一事实来源在 `../ats/references/foundation/auth.md`。

读取 `../ats/references/foundation/auth.md` 全文并严格执行。该文件是鉴权、登录、登出与 curl 失败分支的单一事实来源；需要查询或改变 current 时再按文档指引加载 `../ats/references/foundation/tenant-switch.md`，进入具体 ATS 业务时回到 `../ats/SKILL.md` 选择业务路由。任一相对路径不存在时报告 cllmk skill 套件安装不完整并停止。
