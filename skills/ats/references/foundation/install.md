---
source-skill: cllmk-install
version: 1.0.0
description: "cllmk CLI 的安装与安装确认流程。只要用户提到安装、升级、找不到 cllmk，或其他 skill 检测到 cllmk 未安装，就使用本 skill。优先使用 https://cdn.five5.life/cllmk 的跨平台安装器，不要改用 npm 公共仓库或本地 npm link。"
---

# cllmk 安装

本 skill 只处理 `cllmk` CLI 的检测、安装和版本确认，不处理登录、租户路由或业务 API 调用。

## 1. 先检查是否已安装

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

如果命令存在且版本可以输出，报告已安装版本，不重复安装。

## 2. 安装前置条件

安装器需要：

- Node.js 20 或更高版本
- npm
- 能访问 `https://cdn.five5.life/cllmk`

先确认 `node --version` 和 `npm --version`。Node.js 不满足最低版本时，先提示升级，不执行安装器。

## 3. 安装命令

macOS / Linux：

```bash
curl -fsSL https://cdn.five5.life/cllmk/install.sh | sh
```

Windows PowerShell：

```powershell
irm https://cdn.five5.life/cllmk/install.ps1 | iex
```

安装器会从 CDN 读取 `latest.json`，下载版本 tarball，校验 SHA-256，然后使用 npm 全局安装。不要要求用户发布 npm，也不要先执行本地 `npm link`。

当本 skill 是被 `cllmk-auth` 因“CLI 未安装”间接触发时，只展示适合当前平台的安装命令并停止；等待用户完成安装后，再重新执行原任务。只有用户明确要求执行安装时，才可以在得到确认后运行安装命令。

## 4. 安装后确认

安装完成后重新执行：

```bash
command -v cllmk
cllmk --version
```

Windows 使用 `Get-Command cllmk`。两项都成功才报告安装完成；否则报告失败原因和下一步，不进入 `cllmk auth status` 或业务 API 调用。

## 常见失败

- 找不到 `node` 或 `npm`：先安装 Node.js 20+。
- npm 全局目录无写权限：修复 npm 全局目录权限，不要用 root 强行覆盖用户环境。
- CDN 下载失败：检查网络、代理和 `latest.json` 是否可访问。
- 安装完成但找不到 `cllmk`：重新打开终端，或检查 npm 全局 bin 是否在 `PATH` 中。
