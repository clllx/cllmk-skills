---
version: 1.0.3
description: "cllmk CLI 的安装与安装确认流程。只要用户提到安装、升级、找不到 cllmk，或其他 skill 检测到 cllmk 未安装，就使用本 skill。不要改用 npm 公共仓库或本地 npm link。"
---

# cllmk 安装

本文档只处理 `cllmk` CLI 的检测、安装和版本确认。按第 1–4 节顺序执行，任一节的检查不通过就停在该节（失败分支见第 5 节），不进入 `cllmk auth status` 或业务 API 调用。

## 1. 检测是否已安装

macOS / Linux：

```bash
command -v cllmk
cllmk --version
```

Windows PowerShell：

```powershell
Get-Command cllmk -ErrorAction SilentlyContinue
cllmk --version
```

两条都成功 → 报告已安装版本，结束流程，不重复安装。任一条失败 → 进入第 2 节。

## 2. 检查前置条件

```bash
node --version
npm --version
```

| 检查项 | 要求 | 不满足时的动作 |
|---|---|---|
| Node.js | 20 或更高版本 | 提示用户升级，**不执行安装器** |
| npm | 存在即可 | 提示先安装 Node.js 20+（含 npm），**不执行安装器** |
| 网络 | 可访问 `https://cdn.five5.life/cllmk` | 报告网络或代理问题，**不执行安装器** |

安装器内部用 npm 落地 tarball 并生成全局 `cllmk` 命令，**不允许**换成 pnpm 或 yarn。

## 3. 给出安装命令

macOS / Linux：

```bash
curl -fsSL https://cdn.five5.life/cllmk/install.sh | sh
```

Windows PowerShell：

```powershell
irm https://cdn.five5.life/cllmk/install.ps1 | iex
```

执行规则：

- 本文档被 `auth.md` 因「CLI 未安装」间接触发时，**只展示适合当前平台的安装命令并停止**；等用户完成安装后再重新执行原任务。
- 只有用户明确要求执行安装时，才在得到确认后代跑安装命令。
- 一律使用上面的 CDN 安装器。**禁止**要求用户发布 npm 包，**禁止**改走 `npm install cllmk`，**禁止**先执行本地 `npm link`。

## 4. 安装后确认

macOS / Linux：

```bash
command -v cllmk
cllmk --version
```

Windows 用 `Get-Command cllmk`。两项都成功才报告安装完成；否则按第 5 节报告失败原因和下一步。

## 5. 失败处置

| 症状 | 动作 |
|---|---|
| 找不到 `node` 或 `npm` | 先安装 Node.js 20+，再重跑安装器 |
| npm 全局目录无写权限 | 修复 npm 全局目录权限；**不允许**用 root 强行覆盖用户环境 |
| CDN 下载失败 | 检查网络与代理，确认 `latest.json` 可访问 |
| 安装完成但找不到 `cllmk` | 重新打开终端；或检查 npm 全局 bin 是否在 `PATH` 中 |
