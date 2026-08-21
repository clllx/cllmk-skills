---
source-skill: cllmk-auth
metadata:
  version: "3.5.0"
description: "cllmk 登录、查询与登出的共享规则：用户表达意图、Agent 执行 cllmk、用户只在浏览器完成认证；检查实时会话状态，处理未登录/过期/HTTP 401/403/网络错误，并为 `cllmk curl` 提供安全前置与失败分支。current 租户的离线查询、选择和切换细节由 tenant-switch.md 负责。"
---

# cllmk 鉴权共享规则

本 skill 定义了如何通过 `cllmk` CLI 对 Moka 系统（ATS 招聘 / People 人事）进行鉴权检查、登录、登出与 API 调用。所有调用 Moka API 的 skill 在发起请求前必须遵守本文档的前置检查流程。

**交互模型**：用户表达意图，Agent 执行 `cllmk` 命令，用户只在浏览器里完成身份认证。登录、查询会话、登出都由 Agent 代跑；只有在本文「必须回退到用户自己在终端跑」列出的情况下才把命令交还用户。

三个动作互不干扰，各自只做一件事：

| 动作 | 命令 | 对磁盘的影响 |
|---|---|---|
| 登录 | `cllmk <ats\|people> <env> auth login` | 写目标 profile 的会话文件；更新 current 指针 |
| 查询 | `cllmk auth status` / `profiles` / 无参 `switch` | 只读，**永不删凭证** |
| 登出 | `cllmk auth logout [--all]` | 只删会话文件，**永不改 current 指针** |

current 指针只由 `login` 和 `auth switch` 写。

## 目录

- 会话模型与 current 规则引用
- 临时会话路由与业务租户标准工作流
- 系统与环境
- 前置鉴权检查
- 登录、登出、切换租户与 API 调用
- 失败场景与安全规则

## 会话模型（v3.0：多租户 profile）

核心概念：**一个 profile = 一份独立的会话凭证**（一个 system + 一个 env + 一家公司）。不同 profile 物理隔离、互不覆盖，因此可以同时保持多家公司的登录状态，再通过 current 指针串行切换业务租户。

三条关键行为：

1. **login 自动建 profile**：登录成功后 CLI 自动探测租户身份，按 `<system>-<租户ID>` 命名保存会话（ATS：`ats-<orgId>`；People：`people-<tenantId>`），并把身份信息写进凭证文件。system 前缀保证两套系统即使租户标识重合也不会互相覆盖；用户在浏览器里登录哪家公司，会话就自动归到哪家公司名下——**不会覆盖其他公司的会话**。
2. **当前指针**：每次 login 或 `cllmk auth switch` 成功都会更新「当前 profile」指针。清除 `CLLMK_PROFILE` 后，业务 skill 不带任何租户路由参数，status / logout / curl 使用持久化 current 租户。
3. **身份快照**：凭证文件里的身份字段是登录时刻的快照，用于离线定位 profile；会话是否仍有效以 `cllmk auth status` 实时结果为准。

### 身份字段按 system 分组

`login` / `auth status` / `auth profiles` / `auth switch` 只返回会话所属 system 的那一组字段：

| system | 身份字段 |
|---|---|
| `ats` | `orgId`、`orgName` |
| `people` | `tenantId`、`buId`、`corpName`、`realname` |

**People 会话没有 `orgId` / `orgName`**（那是 ATS 的组织维度），租户看 `tenantId`，公司/业务单元看 `buId` + `corpName`，登录人看 `realname`。一个 profile 只属于一个 system，因此单次 login 或 status 只反映该系统的身份；要同时使用 ATS 和 People，需分别 login，形成两个 profile 后按 current 串行切换。

### 命令一览

| 命令 | 说明 |
|------|------|
| `cllmk ats <env> auth login` | 登录 ATS。登录后自动按公司建 profile 并更新指针 |
| `cllmk people <env> auth login` | 登录 People。同上 |
| `cllmk auth switch ...` | 列出或切换持久化 current；完整参数和失败行为见 `tenant-switch.md` |
| `cllmk auth status` | 实时验证目标会话；确认 `profile` / `system` / `env` 和该 system 的身份字段，不向用户展示 email |
| `cllmk auth profiles` | **离线**列出所有有会话的 profile，并标记持久化 current；不向用户展示 email |
| `cllmk auth logout` | 清除 current profile 的会话（幂等）；不改 current 指针 |
| `cllmk auth logout --all` | 清除全部会话；忽略路由参数，不改 current 指针 |
| `cllmk curl --url <url> [--method] [--payload] [--filter]` | 用当前会话发 HTTP 请求，并按需筛选响应字段 |

只有 login 需要 domain + env；其余命令都不需要。

## current 租户规则

需要列出、选择或切换 current 时，按需完整读取同目录的 `tenant-switch.md`。该文件是以下行为的单一事实来源：

- 无参数 `cllmk auth switch` 的离线列表与持久化 current 语义
- `CLLMK_PROFILE` 对纯查询、切换验证和业务命令的不同影响
- 按 profile、租户 ID（ATS orgId / People tenantId）、公司名选择目标及参数冲突处理
- 切换后裸 `cllmk auth status` 的实时验证
- status 失败时 current 已改变、保留新 current 且不自动回滚的规则

本文不重复这些命令和失败表。实时 status、登录、HTTP 与网络错误处理继续按本文后续章节执行。

## 临时会话路由（仅鉴权诊断使用）

所有命令都按同一优先级解析目标 profile：

```
--profile / --org 命令行参数  >  CLLMK_PROFILE 环境变量  >  current 指针（最后一次 login / switch）  >  default
```

三种指定方式（`--profile` 与 `--org` 互斥，参数可放在命令任意位置）：

```bash
# 方式 A：--org，按租户 ID（ATS orgId / People tenantId）或公司名精确匹配自动反查 profile
cllmk --org <org-id-or-company-name> curl --url /api/...
cllmk --org "<company-name>" auth status

# 方式 B：--profile，直接指定 profile 名（auth profiles 可查）
cllmk --profile <profile-name> curl --url /api/...

# 方式 C：环境变量，兼容旧的终端级临时路由
export CLLMK_PROFILE=<profile-name>
python3 xxx_bulk_script.py ...    # 脚本内的 cllmk 子进程自动继承
```

这些方式只临时影响单条命令或当前终端，不更新 current 指针。**业务 skill 不得使用这些方式选择租户**；应先按 `tenant-switch.md` 更新并验证 current，之后业务 skill 只调用裸 `cllmk auth status` / `cllmk curl`。

唯一例外是 `cllmk auth logout`：它的 `--org` / `--profile` 指的是「删哪份凭证」而不是业务请求的路由，也不会改变 current，规则见「登出流程」。`logout --all` 不接受任何路由参数。

`--org`、`--profile` 和位置参数的未匹配、多匹配、非法名称及参数冲突统一按 `tenant-switch.md` 处理；本文只承接“目标没有已保存会话”之后的登录流程。

### Agent 处理「用 XX 公司操作」的标准工作流

1. 按 `tenant-switch.md` 离线定位并切换目标 current；目标没有已保存会话时进入本文的登录流程。
2. 按 `tenant-switch.md` 使用裸 `cllmk auth status` 验证目标身份；失败时保留已切换的 current、停止业务，并按本文的 status 失败分支处理。
3. 进入业务 skill 后，所有 `status` / `curl` / 批处理脚本都不再携带 `--org`、`--profile` 或 `CLLMK_PROFILE`。

current 指针是共享状态，因此同一配置目录下不要并行跑不同租户的业务任务。需要跨租户处理时按租户串行执行：`switch → status → 完成本租户任务 → switch`。

## 系统与环境

### ATS（招聘系统）

| env | Web URL | 状态 |
|-----|---------|------|
| `cn` | https://app.mokahr.com | 已实现 |
| `intl` | https://hire-r1.mokahr.com | 已实现 |
| `s3` | https://staging-3.mokahr.com | 已实现 |

### People（人事系统）

| env | Web URL | 状态 |
|-----|---------|------|
| `pp` | https://core.mokahr.com | 已实现 |
| `dingding` | — | URL 待配置（TODO） |
| `test` | — | URL 待配置（TODO） |

## 前置鉴权检查（调用方 skill 必做）

**在执行任何 `cllmk` 命令前**，必须先完成 Step 0；未安装时不得执行 `switch`、`profiles`、`status`、`login` 或 `curl`。

### Step 0 — 确认 `cllmk` 已安装

```bash
command -v cllmk
```

- **成功**（输出可执行路径）：继续执行 `cllmk --version`，再进入 Step 0.5。
- **失败**：**立即停止后续所有步骤**。按 `cllmk-install` skill 提供当前平台的 CDN 安装指引，结束流程；不要执行 switch、status、profiles、login 或 curl。

安装地址固定为：

```text
https://cdn.five5.life/cllmk/install.sh
https://cdn.five5.life/cllmk/install.ps1
```

安装完成后，用户需要重新触发原任务；重新触发时再次执行 Step 0。

### Step 0.5 — 排除 `CLLMK_PROFILE` 覆盖

业务 skill 只允许使用 current。执行带目标的 switch、status 或 curl 前，先确认环境变量 `CLLMK_PROFILE` 为空：

```bash
if [ -n "${CLLMK_PROFILE:-}" ]; then
  printf '%s\n' "$CLLMK_PROFILE"
fi
```

Windows PowerShell：

```powershell
$env:CLLMK_PROFILE
```

若输出非空，**立即停止业务流程**，要求用户先清除该环境变量，再从 Step 0.5 重新检查。不要静默忽略，也不要继续运行 status 或 curl；否则环境变量会覆盖 current，使鉴权检查和业务请求路由到错误租户。

这条检查同样适用于登出：环境变量非空时，裸 `cllmk auth logout` 会去删该变量指向的 profile 而不是 current 的会话。两个例外是纯粹运行无参数 `cllmk auth switch` 查询持久化列表（提示规则见 `tenant-switch.md`），以及 `cllmk auth logout --all`（全量操作，CLI 忽略该变量的路由）。

### Step 1 — 执行 status 命令

在 CLI 已确认安装后，且在执行任何 `cllmk curl` 或其他需要鉴权的命令前，继续以下步骤：

任务涉及特定公司时，先按 `tenant-switch.md` 切换 current，再运行裸 `cllmk auth status`。业务 skill 不得通过路由参数绕过 current。

### Step 2 — 解析 JSON 输出的 `code` 字段

所有命令统一输出格式：

```json
{ "code": 0|1, "data": <any|null>, "msg": "<string>" }
```

### Step 3 — 按下表分支处理

| `code` | `msg` 关键字 | 含义 | 下一步 |
|--------|--------------|------|--------|
| `0` | （空） | 已登录 | 读 `data.profile` / `system` / `env` 和该 system 的身份字段（ATS：`orgId` / `orgName`；People：`tenantId` / `buId` / `corpName` / `realname`），**确认是目标公司/系统**后继续；不向用户展示 email |
| `1` | `Not logged in` | current profile 无会话 | 先运行无参数 `cllmk auth switch` 看目标公司是否已有其他 profile；都没有再进入登录流程 |
| `1` | `Session expired. Credentials preserved` | 状态接口明确返回 HTTP 401，`data.expired == true`；**凭证仍保留在盘上** | 进入登录流程重新登录（login 会覆盖过期会话）。不要为了「清理」去跑 logout —— status 是纯查询，过期凭证留在盘上不会让任何请求成功 |
| `1` | `Auth status failed: HTTP ... Credentials preserved` | 非 401 响应，不能证明凭证失效 | 保留会话并报告原始状态；不进入登录流程 |
| `1` | switch 选择或参数错误 | current 查询或切换未完成 | 按 `tenant-switch.md` 的失败处理执行；确认目标没有会话后才进入登录流程 |
| `1` | `Logout failed for profile ...` | 会话文件删除失败，凭证仍在盘上 | 报告失败，不得声称已登出；见「登出流程」 |
| `1` | `Unknown <system> env: ...` | env 参数非法 | **停止流程**。列出合法 env 让用户选择 |
| `1` | `Session env '<env>' status endpoint not configured` | 已保存会话的 system/env 没有对应状态接口 | **停止流程**。保留凭证，按 msg 提示用户在受支持的 system/env 重新登录；不得当成过期或清除会话 |
| `1` | `Request failed: ...` | 网络/DNS 错误，或当前执行环境限制联网 | 按下方「受限执行环境的网络重试」处理；不进入登录流程 |
| `1` | `Login timeout. Browser closed.` | 180 秒内用户未完成浏览器登录 | 提议再执行一次 login；不是故障，不动 current 和已有会话；这是 login 返回 |
| `1` | `Chrome not found. ...` | 本机没有可用 Chrome | 按「必须回退到用户自己在终端跑」交还用户；这是 login 返回 |
| `1` | `账号角色不正确` | ATS login 后未进入 `/dashboard`，本次 Cookie 未保存 | 请用户换用具有 ATS 招聘权限的账号，再由 Agent 重新执行 login；这是 login 返回 |
| `1` | `People env '<env>' URL not configured yet. TODO.` | People dingding/test 的 login 占位 env | 停止流程并告知该环境尚未配置；这是 login 返回 |
| `1` | `Old syntax is no longer supported. Use: ...` | 误用老语法 | 按 msg 给出的新语法重试 |

### 受限执行环境的网络重试

`cllmk auth status` 是实时网络验证。在 Codex、Claude Code 或其他带网络沙箱的执行环境中，`getaddrinfo ENOTFOUND` 可能只表示当前工具进程没有联网权限，并不能直接证明用户本机 DNS 异常。

遇到 `Request failed: ...` 时先判断命令是否可能产生写入，再决定能否重试：

1. `cllmk auth status` 是只读状态检查，即使 People 环境内部使用 POST，也允许在用户本地同命令成功或工具明确受限联网时，为**原命令**申请受控网络访问并重试一次。
2. `cllmk curl` 的 GET / HEAD 属于幂等读取，可按相同条件对原命令重试一次。
3. POST / PUT / PATCH / DELETE 等写请求只有在错误明确发生于建立连接前（目前仅 `ENOTFOUND` / `EAI_AGAIN` DNS 解析失败）时，才能为原命令申请网络权限并重试一次，因为请求尚未到达服务端。
4. 写请求遇到 `ECONNRESET`、`ETIMEDOUT`、`socket hang up` 或其他无法证明发生在连接前的错误时，不得直接重试。先用业务文档规定的查询接口回读，确认写入是否已经生效；无法确认时停止并向用户报告“结果未知”，避免重复创建、更新或删除。
5. 任何重试都不得修改 profile、租户、HTTP method、URL 或 payload，也不得为了排查而执行 login、logout 或其他会改变鉴权状态的命令。
6. 受控网络重试成功：判定为执行环境网络隔离，按原命令成功结果继续业务流程。后续联网命令仍按工具权限边界逐条执行，不静默扩大授权范围。
7. 无法申请网络权限、用户拒绝授权，或允许重试的原命令仍失败：停止流程，报告原始错误并提示检查代理、VPN、DNS 或目标服务；不要转入登录流程。

若本地终端与受控网络重试都失败，才将其视为本机网络、DNS 或目标服务故障。

## 登录流程

### 职责划分

用户表达意图，**Agent 执行 `cllmk` 命令**，用户只在浏览器里完成身份认证。登录、查询、登出三个动作都由 Agent 执行，用户不需要自己敲命令。

`login` 从终端看是完全非交互的：它启动一个独立的临时 Chrome（不复用用户日常浏览器配置），轮询 Cookie 直到认证完成，最长等待 **180 秒**，然后打印 JSON 并退出。它不读 stdin，也不需要 TTY，因此可以由 Agent 执行。

### Agent 执行 login 的方式

必须放进**受工具管理的长运行会话**执行 —— 也就是由执行环境跟踪、进程退出时回调 Agent、并且能被显式终止的那种运行方式（Claude Code 里是 Bash 工具的后台任务）。

**禁止用 shell 自行后台化**：不得使用 `&`、`nohup`、`disown`、`setsid` 或写 PID 文件。这些方式脱离工具跟踪，登录失败或用户放弃时会留下无法回收的 Chrome 进程和 `cllmk-chrome-*` 临时目录。

发起命令后**立即**告知用户去浏览器操作，不要轮询、不要反复查 status 刷屏：

> 已为你执行 `cllmk <ats|people> <env> auth login`，本机会弹出一个 Chrome 窗口。请用 **<目标公司>** 的账号完成登录（登录哪家公司，会话就自动归档到哪家公司名下，不会影响其他公司的会话）。登录成功后浏览器自动关闭，我会接着往下做。

**先确定目标 system 和 env**，不要默认 ATS：招聘业务用 `ats`（env `cn` / `intl` / `s3`），人事业务用 `people`（env `pp`）。用户已指明环境时按用户的；只说了公司没说环境时，ATS 默认 `cn`、People 默认 `pp`，并在告知里把环境明示出来。两个常用实例：`cllmk ats cn auth login`、`cllmk people pp auth login`。

不需要带 `--profile` —— CLI 自动按公司命名。只有用户明确要求自定义 profile 名时才加。

### 必须回退到「用户自己在终端跑」的四种情况

以下情况 Agent 无法代跑，改为把命令给用户，让他在自己的终端执行后回来告知：

1. **宿主没有 GUI**：远程容器、CI、cron、无桌面会话的服务器。Chrome 必须和 `cllmk` 进程在同一台有图形界面的机器上。
2. **`Chrome not found. Install Google Chrome or set CLLMK_CHROME_PATH.`**：本机没装 Chrome/Chromium，或 `CLLMK_CHROME_PATH` 指向的路径不可执行。
3. **权限被拒**：用户拒绝执行该命令，或沙箱拦住了 Chrome 启动 / 本地 CDP 端口 / 外网访问。此时按「受限执行环境的网络重试」判断，仍不通就交还用户。
4. **超时或中途取消**：`Login timeout. Browser closed.`（180 秒内未完成）或用户中断了任务。

回退话术：

> 我这边没法代你打开浏览器（<具体原因>）。请在你自己的终端运行 `cllmk <ats|people> <env> auth login`，用 **<目标公司>** 的账号完成登录后告诉我，我接着往下做。

超时是**用户没来得及操作**，不是会话损坏或环境故障：直接提议重跑一次登录，不要报告成 CLI 错误，也不要去动 current 或已有会话。

### 其它 login 失败分支

system 选错的后果是登录成功但会话不可用于目标业务：ATS 会话不能调 People 接口，反之亦然。已有会话属于另一套系统时，不要切 current（switch 只能在已保存会话之间切），而是登录目标 system。

ATS 登录后必须进入 `/dashboard`。如果已认证但跳到其他系统路径，CLI 返回账号角色不正确、关闭临时浏览器且**不保存本次 Cookie**；请用户换一个具有 ATS 招聘权限的账号，再由 Agent 重新执行登录。People 的 `dingding` / `test` 尚未配置 URL，不能登录，按 Step 3 对应分支停止。

### 登录后的验证

`login` 成功后不要直接把它的返回值当作结论展示 —— `data` 里带 `email`。执行裸 `cllmk auth status`（登录已把指针移到新会话，无需路由参数），确认 `code: 0` **且公司名（ATS `orgName` / People `corpName`）是目标公司**再继续，向用户只报 profile / 公司名 / system / env。

登错公司 → `cllmk auth switch` 切回正确公司；正确公司尚无会话 → 重新执行 login。

## 登出流程

用户表达登出意图，Agent 执行 `cllmk auth logout`。**logout 只删会话文件，绝不改写 current 指针**（指针只由 login 和 switch 更新），因此登出任何 profile 都不会把后续命令静默路由到别的租户。

| 用户意图 | 命令 | 行为 |
|---|---|---|
| 「退出登录」（未指明公司） | `cllmk auth logout` | 清除 current 的会话。current 无会话时幂等返回 `Already logged out` |
| 「退出 XX 公司」 | 先核对，再 `cllmk --org "<公司名>" auth logout` | 只清该租户；目标无会话时返回 `No logged-in profile '...'`，**不是**成功 |
| 「全部退出」 | `cllmk auth logout --all` | 清除所有会话。忽略 `CLLMK_PROFILE` 路由，与 `--profile` / `--org` 互斥 |

指定公司时的核对规则：先读无参数 `cllmk auth switch` 或 `cllmk auth profiles` 定位目标，**目标与持久化 current 一致就直接执行；不一致就停下**，向用户说明 current 是哪家、要登出的是哪家，让用户确认后再执行。这是登出唯一需要停下来的情况 —— 清掉的会话必须重新走浏览器登录才能恢复。

`logout` 是这里唯一允许在业务流程中使用 `--org` / `--profile` 的场合：它的目标是**要删哪份凭证**，不是业务请求的路由，不会改变 current，因此不违反「业务只用 current」。`--all` 不接受任何路由参数。

### 登出后必须报告剩余会话

响应自带这些字段，不需要再调一次 `auth profiles`：

| 字段 | 含义 |
|---|---|
| `cleared` | 被清除的会话身份快照（删除前采样） |
| `remaining` | 仍有会话的 profile（删除后重新读取） |
| `current` | 持久化 current 指针，**logout 从不修改它** |
| `currentHasSession` | current 指向的 profile 是否仍有会话 |

按 `remaining` 告诉用户还有哪些租户在登录中（只报 profile / system / env / 公司名与租户 ID，不报 email）。`remaining` 为空就明确说「已无任何已保存会话」。

`currentHasSession: false` 时必须提示：current 仍指向 `<current>`，但该会话已清除，下一步必须重新 login 或 `auth switch` 到一个仍有会话的租户，否则裸命令会返回 `Not logged in`。

`code: 1` 且 msg 为 `Logout failed for profile '...'` 表示会话文件删不掉（如权限问题）：**凭证仍在盘上**，不得报告成功；`--all` 的部分失败会在 `data.cleared` 里给出已清除的部分。

## 切换租户 / 系统 / 环境

- **目标租户已登录过**：完整读取 `tenant-switch.md`，按其规则选择、切换并验证。
- **目标租户没登录过或要换 system/env**：按本文「登录流程」执行 login。旧会话不会被覆盖，login 后 current 指向新会话。
- **切换后的 status 失败**：current 已指向新目标；不自动回滚，停止业务并按本文对应分支处理。

## API 调用（curl）

### 命令签名

```bash
cllmk curl --url <url> [--method <method>] [--payload <json>] [--filter <path>]
```

- `--url`：必填，相对路径（自动拼当前会话 baseUrl）或完整 URL
- `--method`：可选，默认 `GET`
- `--payload`：可选，JSON 字符串作为请求 body
- `--filter`：可选，只在输出中保留指定响应路径；具体能力取决于 CLI 版本，按下方规则选择语法
- CLI 自动注入 current 会话的 Cookie 和 `Content-Type: application/json`

### `--filter` 版本规则

使用数组路径前先读取 Step 0 已取得的 `cllmk --version`：

- **`cllmk >= 0.2.0`**：点号分隔对象键，纯数字段表示数组下标。例如 `data.list.0.name`。输出保留所选对象和数组路径。
- **`cllmk >= 0.2.0` 的失败行为**：对象键不存在、数组段不是数字或数组下标越界时返回 `code: 1` 和明确的 filter 错误，不再静默返回 `null`。如果字段真实存在且值就是 JSON `null`，仍返回 `code: 0`；因此以 `code` 区分“路径错误”和“真实空值”。
- **filter 失败不是接口业务结论**：`code: 1` 且消息明确指向 filter 路径时，只能说明本地筛选没有成功。先改为读取不含敏感数据的最小父路径，必要时将响应保存到权限受控的临时文件后只检查顶层键；只有确认原始业务响应确实缺少该字段后，才能报告“当前租户未返回此配置”。不得把 filter 错误直接表述成租户无配置或接口失败。
- **非 0 数组下标**：为保留原下标，`data.list.1.name` 会序列化为类似 `{"data":{"list":[null,{"name":"李四"}]}}`。前面的 `null` 是未选择位置的 JSON 占位，不是接口为目标项返回的值；调用方必须读取请求的原下标，不得改读 `list[0]` 或把占位判定为字段空值。
- **`cllmk 0.1.1`**：只支持穿过普通对象，不能进入数组，也不支持数组下标。数组场景先过滤到完整数组（如 `data.list`），再按实际输出结构使用 `jq`、Python 或业务脚本解析。旧版缺失路径会静默返回 `null`，不得据此判断接口没有返回字段。
- 任务确实需要数组下标而版本低于 `0.2.0` 时，优先使用上述整段数组 fallback；只有用户要求升级时才按 `install.md` 安装最新版。不要在旧版上试跑新语法。

### 前置依赖

**调用 curl 前必须完成"前置鉴权检查"**（Step 0 已安装 + 目标会话 status code:0）。curl 本身只报错 "Not logged in"，不会主动触发登录流程。

### 示例

```bash
# current 租户，只读取职位字段
cllmk curl --url /api/v2/org/info --method GET --filter jobFields
```

**提醒**：业务 curl 始终使用 current。发起请求前用裸 `auth status` 确认 `system` 和公司名（ATS `orgName` / People `corpName`）都符合预期。

### curl 的失败行为

与 status 不同，**curl 遇到非 2xx 响应不会自动清除会话**：

| curl 输出 | 含义 | skill 应对 |
|-----------|------|-----------|
| `code: 0` | 成功 | `data` 含响应体，继续流程 |
| `code: 1, msg: "HTTP 401"` | 可能凭证失效 | 跑裸 `cllmk auth status` 验证 current；明确失效才重新登录 |
| `code: 1, msg: "HTTP 403"` | 业务权限不足或接口拒绝 | 跑裸 `cllmk auth status`；会话有效则报告权限问题，会话检查仍为 403 时保留凭证并停止 |
| `code: 1, msg: "HTTP 404"` | 接口路径不存在 | 确认 URL；不同 system 接口不同 |
| `code: 1, msg: "HTTP 4xx"` 其他 | 业务错误 | 报告给用户，由业务 skill 决定重试或终止 |
| `code: 1, msg: "HTTP 5xx"` | 服务器错误 | 提示稍后重试 |
| `code: 1, msg: "Not logged in ..."` | 该 profile 未登录 | 按 Step 3 的 `Not logged in` 分支处理 |
| `code: 1, msg: "No logged-in profile for org ..."` | `--org` 未匹配 | 同上 |
| `code: 1, msg: "--url is required"` / `"--payload must be valid JSON"` | 参数错误 | 修正后重试 |
| `code: 1, msg: "Request failed: ..."` | 网络或执行环境限制 | 按「受限执行环境的网络重试」根据方法幂等性处理 |

## 失败场景处理（完整清单）

1. **`cllmk` 未安装** → 按 Step 0 话术告知安装，终止流程
2. **未登录 / `No logged-in profile`** → 先用无参数 `auth switch` 排查是否已有其他 profile，再进入登录流程
3. **凭证过期** → status 明确返回 HTTP 401 时报告 `Session expired. Credentials preserved.` 并重新登录；**status 不清除任何凭证**，403/429/5xx 同样保留
4. **switch 选择或参数错误** → 按 `tenant-switch.md` 处理；本文不重复切换失败规则
5. **env 参数错误** → 展示合法 env 列表，不要尝试登录
6. **网络错误（`Request failed`）** → 先按「受限执行环境的网络重试」区分读写方法和请求是否可能已送达；非幂等写请求结果不确定时必须回读，不盲目重试；网络错误不触发登录
7. **ATS 账号角色不正确** → 本次 Cookie 未保存；请用户换用具有 ATS 招聘权限的账号，再由 Agent 重新执行 login
8. **People dingding/test 占位环境** → 不能登录不能调用，告知待配置
9. **curl HTTP 401/403** → 跑裸 `auth status` 验证 current：status 明确返回 401（`data.expired`）时重新登录；status 通过则报告业务权限/路径问题，status 返回其他错误则报告原始状态。无论哪种分支都不动凭证
10. **误用老语法** → 按 CLI 提示的新语法重试
11. **login 无法代跑或超时** → 按「必须回退到用户自己在终端跑」的四种情况处理；超时只提议重跑，不报故障
12. **`Logout failed for profile ...`** → 凭证仍在盘上，不得报告已登出；`--all` 的部分失败按 `data.cleared` 说明清到哪一步

## 安全规则

- **禁止输出 cookies 明文**（如 `moka-jwt`、`moka-uid` 的 value）到终端、日志或任何可见位置
- **禁止手动编辑** `~/.config/cllmk/auth.json`、`~/.config/cllmk/profiles/**/auth.json` 及 `~/.config/cllmk/current-profile`，必须通过 login / switch / logout 管理
- `status` / `profiles` / `logout` 只展示确认目标租户所需的 profile、system、env 和该 system 的身份字段（ATS：orgId、orgName；People：tenantId、buId、corpName、realname）；email 不用于租户确认，不向用户展示
- **email 的约束对象是 Agent 的转述，不是 CLI 的返回值**：`login` / `status` / `profiles` 的 `data`，以及 `logout` 的 `cleared` / `remaining` 里本来就带 `email`，这是设计如此，看到它不代表 CLI 有缺陷、也不需要改命令。Agent 只是不得把它写进回复、日志或摘要；确认租户一律用公司名与租户 ID
- Agent 代跑 `login` 只能用受工具管理的长运行会话，不得用 `&` / `nohup` / `disown` / `setsid` 自行后台化，避免留下无法回收的 Chrome 进程与临时 profile 目录
- `curl` 响应不因“不含凭证明文”就可以完整展示。优先使用 `--filter`、结构化解析或业务脚本，只向用户返回完成任务所需字段；候选人简历、邮箱、电话、证件信息和附件地址等敏感业务数据不得无关展开

## 被其他 skill 引用

其他 skill 在自己的 SKILL.md 中引用本规则的方式：

```markdown
本 skill 依赖 `cllmk-auth`。在执行任何 `cllmk curl` 前，请按其前置检查工作流
（确认 `cllmk` 已安装且 `CLLMK_PROFILE` 为空 → 需要切换时按 `tenant-switch.md` 更新 current →
用裸 `cllmk auth status` 确认公司与系统正确 → 按 `auth.md` 分支处理，需要登录时由 Agent
按 `auth.md`「登录流程」代为执行 login）完成鉴权。
```

调用方 skill 不需要复制本文档内容，只需在触发时机声明依赖即可。业务 skill 自身只能使用 current，不得出现 `--org`、`--profile` 或 `CLLMK_PROFILE` 租户路由。
