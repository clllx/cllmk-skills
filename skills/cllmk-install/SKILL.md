---
name: cllmk-install
metadata:
  version: "1.0.0"
description: "cllmk CLI 的安装与安装确认流程。只要用户提到安装、升级、找不到 cllmk，或其他 skill 检测到 cllmk 未安装，就使用本 skill。优先使用 https://cdn.five5.life/cllmk 的跨平台安装器，不要改用 npm 公共仓库或本地 npm link。"
---

# cllmk 安装兼容入口

读取 `../ats/references/foundation/install.md` 全文并严格执行。该文件是安装规则的单一事实来源；不要只停留在本入口，也不要加载其他业务路由。若该相对路径不存在，报告 cllmk skill 套件安装不完整并停止，不要猜测或复制旧规则。
