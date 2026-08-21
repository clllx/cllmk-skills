---
name: cllmk-tenant-switch
metadata:
  version: "1.2.0"
description: "cllmk 租户切换兼容入口：将 current 租户查询与切换意图路由到 `ats/references/foundation/tenant-switch.md`，规则单一事实来源在 `ats` skill，本 skill 不存放逻辑。"
---

# cllmk 租户切换兼容入口

> 🔀 本文件只是**路由指针**，不存放任何租户切换逻辑。规则单一事实来源在 `../ats/references/foundation/tenant-switch.md`。

读取 `../ats/references/foundation/tenant-switch.md` 全文并严格执行。该文件是 current 租户查询与切换规则的单一事实来源；不要加载无关 ATS 业务文档。若该相对路径不存在，报告 cllmk skill 套件安装不完整并停止，不要猜测或复制旧规则。
