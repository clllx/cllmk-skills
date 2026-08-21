---
name: cllmk-auth
metadata:
  version: "3.5.0"
description: "cllmk 登录、查询与登出的兼容入口：用户表达意图、Agent 执行 cllmk、用户只在浏览器完成认证。检查实时会话状态，代为执行 login 与 logout（含 --all），处理未登录/过期/HTTP 401/403/网络错误，并为 `cllmk curl` 提供安全前置与失败分支。其他 skill 调用 Moka API 前，或用户要求登录、退出登录、查看会话是否有效、排查鉴权及接口错误时使用。纯粹列出或切换 current 租户应使用 `cllmk-tenant-switch`；ATS 字段、候选人、职位等业务操作应使用 `ats`。"
---

# cllmk 鉴权兼容入口

读取 `../ats/references/foundation/auth.md` 全文并严格执行。该文件是鉴权、登录、登出与 curl 失败分支的单一事实来源；需要查询或改变 current 时再按文档指引加载 `../ats/references/foundation/tenant-switch.md`，进入具体 ATS 业务时回到 `../ats/SKILL.md` 选择业务路由。任一相对路径不存在时报告 cllmk skill 套件安装不完整并停止。
