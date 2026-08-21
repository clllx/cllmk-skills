---
name: cllmk-install
metadata:
  version: "1.0.0"
description: "cllmk 安装兼容入口：将安装、升级、找不到 cllmk 的处理意图路由到 `ats/references/foundation/install.md`，规则单一事实来源在 `ats` skill，本 skill 不存放逻辑。"
---

# cllmk 安装兼容入口

> 🔀 本文件只是**路由指针**，不存放任何安装逻辑。规则单一事实来源在 `../ats/references/foundation/install.md`。

读取 `../ats/references/foundation/install.md` 全文并严格执行。该文件是安装规则的单一事实来源；不要只停留在本入口，也不要加载其他业务路由。若该相对路径不存在，报告 cllmk skill 套件安装不完整并停止，不要猜测或复制旧规则。
