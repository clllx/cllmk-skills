---
metadata:
  version: "6.0.0"
description: "Moka ATS 侧 cllmk 登录、查询与登出的共享规则：用户表达意图、Agent 执行 cllmk、用户只在浏览器完成认证；检查实时会话状态，处理未登录、过期、网络错误，以及 `cllmk curl` 返回 HTTP 401/403 时的复验分支。current 租户的查询与切换见 tenant-switch.md。"
---

# cllmk 鉴权共享规则

本文档定义如何通过 `cllmk` CLI 对 Moka ATS（招聘系统）做鉴权检查、登录与登出。所有调用 Moka API 的 skill 在发起请求前必须完成本文的「前置鉴权检查」。

**交互模型**：用户表达意图，Agent 执行 `cllmk` 命令，用户只在浏览器里完成身份认证。登录、查询、登出三个动作都由 Agent 代跑，只有「必须回退到用户自己在终端跑」列出的四种情况才把命令交还用户。

| 动作 | 命令 | 对磁盘的影响 |
|---|---|---|
| 登录 | `cllmk ats <env> auth login` | 写目标 profile 的会话文件；更新 current 指针 |
| 查询 | `cllmk auth status` / `profiles` / 无参 `switch` | 只读，**永不删凭证** |
| 登出 | `cllmk auth logout [--all]` | 只删会话文件，**永不改 current 指针** |

**current 指针只由 `login` 和 `auth switch` 写。** 一个 profile = 一个 system + 一个 env + 一家公司的独立会话，可同时保持多家公司登录、再按 current 串行切换；一个 profile 只属于一个 system，同时使用 ATS 和 People 需要分别 login。

## 命令一览

| 命令 | 说明 |
|------|------|
| `cllmk ats <env> auth login` | 登录 ATS。登录后自动按 `ats-<orgId>` 建 profile 并更新指针 |
| `cllmk auth switch ...` | 列出或切换持久化 current；完整参数和失败行为见 `tenant-switch.md` |
| `cllmk auth status` | 实时验证目标会话；确认 `profile` / `system` / `env` 和该 system 的身份字段，不向用户展示 email |
| `cllmk auth profiles` | **离线**列出所有有会话的 profile，并标记持久化 current；不向用户展示 email |
| `cllmk auth logout` | 清除 current profile 的会话（幂等）；不改 current 指针 |
| `cllmk auth logout --all` | 清除全部会话；忽略路由参数，不改 current 指针 |
| `cllmk curl --url <url> [--method] [--payload] [--filter]` | 用当前会话发 HTTP 请求，并按需筛选响应字段；本身不做鉴权，具体接口与 payload 见对应业务文档 |

只有 login 需要 domain + env（合法 env 见「登录流程」），其余命令都不需要。

**业务命令一律只用 current**：不得携带 `--org` / `--profile`，也不得靠 `CLLMK_PROFILE` 路由 —— 这三种方式只临时影响单条命令或当前终端、**不更新 current 指针**，会让「验证通过的租户」和「实际操作的租户」错位。唯一例外是 `cllmk auth logout`（见「登出流程」）。需要列出、选择或切换 current 时按需完整读取同目录的 `tenant-switch.md`，那些行为一律以该文件为准；current 指针是共享状态，同一配置目录下不要并行跑不同租户的业务任务，跨租户按 `switch → status → 完成本租户任务 → switch` 串行执行。

## 前置鉴权检查（调用方 skill 必做）

**在执行任何 `cllmk` 命令前**，必须先完成 Step 1；未安装时不得执行 `switch`、`profiles`、`status`、`login` 或 `curl`。

### Step 1 — 确认 `cllmk` 已安装

```bash
command -v cllmk
```

- **成功**（输出可执行路径）：继续执行 `cllmk --version`，再进入 Step 2。
- **失败**：**立即停止后续所有步骤**。按 `install.md` 提供当前平台的安装指引，结束流程；不要执行 switch、status、profiles、login 或 curl。安装完成后用户需要重新触发原任务，届时再次从 Step 1 开始。

### Step 2 — 排除 `CLLMK_PROFILE` 覆盖

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

若输出非空，**立即停止业务流程**，要求用户先清除该环境变量，再从 Step 2 重新检查。不要静默忽略，也不要继续运行 status 或 curl —— 否则环境变量会覆盖 current，使鉴权检查和业务请求路由到错误租户。

这条检查同样适用于登出：环境变量非空时，裸 `cllmk auth logout` 会去删该变量指向的 profile 而不是 current 的会话。两个例外是纯粹运行无参数 `cllmk auth switch` 查询持久化列表（提示规则见 `tenant-switch.md`），以及 `cllmk auth logout --all`（全量操作，CLI 忽略该变量的路由）。

### Step 3 — 执行 status 命令

任务涉及特定公司时，先按 `tenant-switch.md` 切换 current，再运行裸 `cllmk auth status`。业务 skill 不得通过路由参数绕过 current。

### Step 4 — 解析 JSON 输出的 `code` 字段

所有命令统一输出格式：

```json
{ "code": 0|1, "data": <any|null>, "msg": "<string>" }
```

### Step 5 — 按下表分支处理

| `code` | `msg` 关键字 | 含义 | 下一步 |
|--------|--------------|------|--------|
| `0` | （空） | 已登录 | 读 `data.profile` / `system` / `env` 和 `orgId` / `orgName`，**确认是目标公司/系统**后继续；不向用户展示 email |
| `1` | `Not logged in` | current profile 无会话 | 先运行无参数 `cllmk auth switch` 看目标公司是否已有其他 profile；都没有再进入「登录流程」 |
| `1` | `Session expired. Credentials preserved` | 状态接口明确返回 HTTP 401，`data.expired == true`；**凭证仍保留在盘上** | 进入「登录流程」重新登录（login 会覆盖过期会话）。不要为了「清理」去跑 logout —— status 是纯查询，过期凭证留在盘上不会让任何请求成功 |
| `1` | `Auth status failed: HTTP ... Credentials preserved` | 非 401 响应，不能证明凭证失效 | 保留会话并报告原始状态；**不**进入登录流程 |
| `1` | `Session env '<env>' status endpoint not configured` | 已保存会话的 system/env 没有对应状态接口 | **停止流程**。保留凭证，按 msg 提示用户在受支持的 system/env 重新登录；不得当成过期或清除会话 |
| `1` | `Unknown <system> env: ...` | env 参数非法 | **停止流程**。列出合法 env 让用户选择 |
| `1` | `Request failed: ...` | 网络/DNS 错误，或当前执行环境限制联网 | 按下方「受限执行环境的网络重试」处理；不进入登录流程 |
| `1` | switch 选择或参数错误 | current 查询或切换未完成 | 按 `tenant-switch.md` 的失败处理执行；确认目标没有会话后才进入登录流程 |
| `1` | `Logout failed for profile ...` | 会话文件删除失败，凭证仍在盘上 | 报告失败，不得声称已登出；见「登出流程」 |
| — | `cllmk curl` 返回 HTTP **401 / 403** | 这是 curl 的 HTTP 状态，**不代表凭证已失效，也不会清除会话** | 先跑裸 `cllmk auth status` 复验 current，再按本表分支决定是否重新登录 —— 不要凭 curl 的一次 401 就去 login 或 logout。会话仍有效时的 403 是业务权限问题：报告并停止，不要重新登录 |

`curl` 之前必须走完整段前置鉴权检查（Step 1–5），且目标会话 status 为 `code: 0`；curl 自己不会触发登录，未登录只返回 `Not logged in`。`login` 自己的失败分支（超时、无可用 Chrome、ATS 账号角色不正确）见「登录流程」；误用老语法时 CLI 返回 `Old syntax is no longer supported. Use: ...`，按 msg 给出的新语法重试。

### 身份字段按 system 分组

`login` / `auth status` / `auth profiles` / `auth switch` 只返回会话所属 system 的那一组：

| system | 身份字段 |
|---|---|
| `ats` | `orgId`、`orgName` |
| `people` | `tenantId`、`buId`、`corpName`、`realname` |

**People 会话没有 `orgId` / `orgName`**（那是 ATS 的组织维度）：租户看 `tenantId`，公司/业务单元看 `buId` + `corpName`，登录人看 `realname`；反过来 ATS 会话也不返回这三个字段。**拿不到本 system 的身份字段就说明会话不属于本 system**，停止并按「其它 login 失败分支」的「system 选错」处理，不要改用另一组字段校验。

凭证文件里的身份字段是**登录时刻的快照**，只用于离线定位 profile；会话是否仍有效一律以实时 `cllmk auth status` 为准。

### 受限执行环境的网络重试

`Request failed: ...` 在带网络沙箱的执行环境（Codex、Claude Code 等）里可能只表示当前工具进程没有联网权限，`getaddrinfo ENOTFOUND` **不能**直接判定为用户本机 DNS 异常。能否重试按「这条命令是否可能产生写入」判断：

1. **只读命令可对原命令重试一次**：`cllmk auth status` 与 `cllmk curl` 的 GET / HEAD。条件是用户本地同命令成功，或工具明确受限联网。
2. **写请求（POST / PUT / PATCH / DELETE）只有 `ENOTFOUND` / `EAI_AGAIN` 可重试一次** —— DNS 解析失败说明请求还没到服务端。`ECONNRESET`、`ETIMEDOUT`、`socket hang up` 以及其他无法证明发生在建立连接前的错误**一律不得重试**：先用业务文档规定的查询接口回读，确认写入是否已生效；无法确认时停止并向用户报告「结果未知」，避免重复创建、更新或删除。
3. **重试不得改变任何参数**（profile、租户、HTTP method、URL、payload），也不得为了排查去执行 login、logout 或其他改变鉴权状态的命令；后续联网命令仍按工具权限边界逐条执行，不静默扩大授权范围。
4. **重试成功**就按原命令结果继续业务；**无法申请网络权限、用户拒绝授权或允许重试的原命令仍失败**则停止流程，报告原始错误并提示检查代理、VPN、DNS 或目标服务，不要转入登录流程。

只有本地终端与受控网络重试都失败，才视为本机网络、DNS 或目标服务故障。

## 登录流程

### Agent 执行 login 的方式

`login` 非交互（弹出临时 Chrome、轮询 Cookie、最长等 **180 秒**后打印 JSON 退出，不读 stdin、不需要 TTY），因此由 Agent 代跑。

必须放进**受工具管理的长运行会话**执行（由执行环境跟踪、进程退出时回调 Agent、可被显式终止；Claude Code 里是 Bash 工具的后台任务）。**禁止用 `&`、`nohup`、`disown`、`setsid` 或 PID 文件自行后台化** —— 脱离工具跟踪后，登录失败或用户放弃时会留下无法回收的 Chrome 进程和 `cllmk-chrome-*` 临时目录。

发起命令后**立即**告知用户去浏览器操作，不要轮询、不要反复查 status 刷屏：

> 已为你执行 `cllmk ats <env> auth login`，本机会弹出一个 Chrome 窗口。请用 **<目标公司>** 的账号完成登录（登录哪家公司，会话就自动归档到哪家公司名下，不会影响其他公司的会话）。登录成功后浏览器自动关闭，我会接着往下做。

**先确定目标 env**，不要默认 `cn`：招聘业务的 system 固定为 `ats`，env 是 `cn` / `intl` / `s3`（分别对应 app / hire-r1 / staging-3）。用户已指明环境时按用户的；只说了公司没说环境时默认 `cn`，并在告知里把环境明示出来。常用实例：`cllmk ats cn auth login`。人事业务不在本 skill 覆盖范围，需要 People 会话时改用 `people` skill。

不需要带 `--profile` —— CLI 自动按公司命名。只有用户明确要求自定义 profile 名时才加。

### 必须回退到「用户自己在终端跑」的四种情况

以下情况 Agent 无法代跑，改为把命令给用户，让他在自己的终端执行后回来告知：

1. **宿主没有 GUI**：远程容器、CI、cron、无桌面会话的服务器。Chrome 必须和 `cllmk` 进程在同一台有图形界面的机器上。
2. **`Chrome not found. Install Google Chrome or set CLLMK_CHROME_PATH.`**：本机没装 Chrome/Chromium，或 `CLLMK_CHROME_PATH` 指向的路径不可执行。
3. **权限被拒**：用户拒绝执行该命令，或沙箱拦住了 Chrome 启动 / 本地 CDP 端口 / 外网访问。此时先按「受限执行环境的网络重试」判断，仍不通就交还用户。
4. **超时或中途取消**：`Login timeout. Browser closed.`（180 秒内未完成）或用户中断了任务。

回退话术：

> 我这边没法代你打开浏览器（<具体原因>）。请在你自己的终端运行 `cllmk ats <env> auth login`，用 **<目标公司>** 的账号完成登录后告诉我，我接着往下做。

超时是**用户没来得及操作**，不是会话损坏或环境故障：直接提议重跑一次登录，不要报告成 CLI 错误，也不要去动 current 或已有会话。

### 其它 login 失败分支

- **system 选错**：登录成功但会话不可用于目标业务 —— ATS 会话不能调 People 接口，反之亦然。已有会话属于另一套系统时，不要切 current（switch 只能在已保存会话之间切），而是登录目标 system。
- **ATS 账号角色不正确**：ATS 登录后必须进入 `/dashboard`。若已认证但跳到其他系统路径，CLI 返回 `账号角色不正确`、关闭临时浏览器且**不保存本次 Cookie**；请用户换一个具有 ATS 招聘权限的账号，再由 Agent 重新执行登录。

### 登录后的验证

`login` 成功后不要直接把它的返回值当作结论展示 —— `data` 里带 `email`。执行裸 `cllmk auth status`（登录已把指针移到新会话，无需路由参数），确认 `code: 0` **且 `orgName` 是目标公司**再继续，向用户只报 profile / 公司名 / system / env。

登错公司 → `cllmk auth switch` 切回正确公司；正确公司尚无会话 → 重新执行 login。

## 登出流程

用户表达登出意图，Agent 执行 `cllmk auth logout`。**logout 只删会话文件，绝不改写 current 指针**（指针只由 login 和 switch 更新），因此登出任何 profile 都不会把后续命令静默路由到别的租户。

| 用户意图 | 命令 | 行为 |
|---|---|---|
| 「退出登录」（未指明公司） | `cllmk auth logout` | 清除 current 的会话。current 无会话时幂等返回 `Already logged out` |
| 「退出 XX 公司」 | 先核对，再 `cllmk --org "<公司名>" auth logout` | 只清该租户；目标无会话时返回 `No logged-in profile '...'`，**不是**成功 |
| 「全部退出」 | `cllmk auth logout --all` | 清除所有会话。忽略 `CLLMK_PROFILE` 路由，与 `--profile` / `--org` 互斥 |

指定公司时的核对规则：先读无参数 `cllmk auth switch` 或 `cllmk auth profiles` 定位目标，**目标与持久化 current 一致就直接执行；不一致就停下**，向用户说明 current 是哪家、要登出的是哪家，让用户确认后再执行。这是登出唯一需要停下来的情况 —— 清掉的会话必须重新走浏览器登录才能恢复。

`logout` 是唯一允许在业务流程中使用 `--org` / `--profile` 的场合：它的目标是**要删哪份凭证**，不是业务请求的路由，不会改变 current，因此不违反「业务只用 current」。`--all` 不接受任何路由参数。

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

## 安全规则

- **禁止输出 cookies 明文**（如 `moka-jwt`、`moka-uid` 的 value）到终端、日志或任何可见位置。
- **禁止手动编辑** `~/.config/cllmk/auth.json`、`~/.config/cllmk/profiles/**/auth.json` 及 `~/.config/cllmk/current-profile`，必须通过 login / switch / logout 管理。
- `status` / `profiles` / `logout` 只展示确认目标租户所需的 profile、system、env 和 `orgId`、`orgName`。
- **email 出现在 CLI 返回里是设计如此**（`login` / `status` / `profiles` 的 `data`，以及 `logout` 的 `cleared` / `remaining`），不是缺陷，也不需要改命令。约束的对象是 Agent 的转述：不得把 email 写进回复、日志或摘要，确认租户一律用公司名与租户 ID。
- Agent 代跑 `login` 只能用受工具管理的长运行会话，不得用 `&` / `nohup` / `disown` / `setsid` 自行后台化。
