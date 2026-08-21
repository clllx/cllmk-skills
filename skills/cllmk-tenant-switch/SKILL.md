---
name: cllmk-tenant-switch
metadata:
  version: "1.2.0"
description: "cllmk current 租户查询与切换的兼容入口。用户只想离线列出已保存租户、查看持久化 current 指针，或明确要求用 `cllmk auth switch` 按公司名、租户 ID（ATS orgId / People tenantId）、profile 切换时使用。登录、会话是否有效、HTTP 401/403/网络错误由 `cllmk-auth` 处理；ATS 字段、候选人、职位等业务操作由 `ats` skill 处理。目标不存在或匹配多个 profile 时停止，不猜测。"
---

# cllmk 租户切换兼容入口

读取 `../ats/references/foundation/tenant-switch.md` 全文并严格执行。该文件是 current 租户查询与切换规则的单一事实来源；不要加载无关 ATS 业务文档。若该相对路径不存在，报告 cllmk skill 套件安装不完整并停止，不要猜测或复制旧规则。
