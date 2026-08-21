# cllmk 安装：链路与设计说明

本文是 `skills/ats/references/foundation/install.md` 的背景说明。

**分工**：foundation 里的 `install.md` 只写可执行步骤与硬约束（检测 → 前置条件 → 安装命令 → 确认 → 失败处置）；
「为什么这么做」写在本文。`doc/` **不随技能分发**（安装器只平铺 `skills/<name>/`），
所以本文只承载人类阅读的背景，不允许放模型执行时必须读到的规则。

## 1. 安装链路

一条 `curl … | sh`（Windows 为 `irm … | iex`）背后是四步：

| # | 步骤 | 产物 |
|---|---|---|
| 1 | 拉取安装脚本 `install.sh` / `install.ps1` | 本地临时脚本 |
| 2 | 读 CDN 上的 `latest.json` | 目标版本号与 tarball 地址 |
| 3 | 下载版本 tarball 并校验 SHA-256 | 已验证的本地包 |
| 4 | `npm install -g <本地 tarball>` | 全局 `node_modules` + `PATH` 里的 `cllmk` 可执行文件 |

CDN（`https://cdn.five5.life/cllmk`）是唯一包来源，SHA-256 校验用于拦住传输损坏与被篡改的包。

## 2. 为什么前置条件里要有 npm

npm 只出现在第 4 步，角色是**本地安装执行器**：解包 tarball、写全局 `node_modules`、
创建 `PATH` 上的 `cllmk` 软链。它不是包来源 —— 包在第 3 步就已经从 CDN 下载并校验完了。

由此推出三条结论，它们已经作为硬约束写进 `install.md`：

- **不能用 pnpm / yarn 替代**：第 4 步的命令写死在上游安装脚本里，本地换包管理器改不了它，
  且 pnpm / yarn 的全局安装布局与软链策略不同，装完 `cllmk` 未必落在同一个 bin 目录。
- **不走 `npm install cllmk`**：那会把包来源换成 npm 公共仓库，绕过 CDN 的版本指针与 SHA-256 校验。
- **不用本地 `npm link`**：link 指向的是工作副本而非已校验的发布包，版本号与实际代码会脱节，
  排查问题时 `cllmk --version` 不再可信。

## 3. 为什么失败大多集中在 npm

`install.md` 第 5 节的四类失败里有两类源自第 4 步：

- **npm 全局目录无写权限**：全局安装要写 npm prefix 目录。用 `sudo` 硬装会把 root 拥有的文件
  留在用户目录里，之后普通用户升级又失败一次，所以处置动作是「修复权限」而不是「提权重试」。
- **安装完成但找不到 `cllmk`**：包装好了，但 npm 全局 bin 目录不在 `PATH` 中，
  或当前 shell 的 `PATH` 缓存还没刷新 —— 因此先让用户重开终端，再查 `PATH`。

另外两类分别属于第 1–3 步：CDN / 代理不可达，以及运行时缺失（Node.js 低于 20 或没有 npm）。
Node.js 20 是安装器与 CLI 要求的最低运行时版本，低于它不执行安装器，避免装出一个跑不起来的 `cllmk`。

## 4. 修改本文或 install.md 时

- 新增/变更**执行步骤或硬约束** → 改 `install.md`（foundation 是单一事实来源，属最高敏感级别，
  参见 `AGENT.md` §2.1、§7「新增基础能力」）。
- 新增/变更**原理解释** → 改本文，不要回流到 `install.md`。
- 两者都改时，在 commit message 里显式说明 foundation 影响面（`AGENT.md` §9）。
