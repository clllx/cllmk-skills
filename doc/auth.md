# cllmk 鉴权：背景说明

本文是 `skills/ats/references/foundation/auth.md` 与 `skills/people/references/foundation/auth.md` 的人类阅读版补充：记录「为什么这么设计」。
`skills/` 只写模型执行时需要的步骤与硬约束；本文不随技能分发，模型不会读到，**因此任何执行必需的规则都不允许只写在这里**。

## 1. 为什么是 profile 而不是单会话

早期 CLI 只保存一份 `auth.json`，登录第二家公司会直接覆盖第一家 —— 跨租户任务（从 A 公司导出、写入 B 公司）每切一次就要重新走一遍浏览器登录。
v3.0 改成一个 profile 对应一份独立凭证文件，再用一个 current 指针表示「现在对谁操作」。带来的三个后果都写进了 skill：

- 可以同时保持多家公司登录，切换只是改指针，不动 Cookie。
- 指针是**全局共享状态**，所以跨租户任务必须串行，且收尾要向用户明示指针停在哪。
- 凭证文件里的身份字段只是登录时刻的快照，用于离线定位；会话是否还活着必须实时问 `auth status`。

profile 名带 `<system>-` 前缀（`ats-<orgId>` / `people-<tenantId>`），是因为两套系统的租户标识各自独立编号、存在重合可能。没有前缀时，一次 People 登录可能覆盖同号 ATS 会话，而两者的 Cookie 域和接口完全不通用，排查起来看不出任何异常。

## 2. 为什么 login 可以由 Agent 代跑

`login` 从终端看是完全非交互的：它启动一个**独立的临时 Chrome**（不复用用户日常浏览器配置，避免读到用户其他站点的 Cookie），轮询目标域的 Cookie 直到认证完成，最长等 180 秒，然后打印 JSON 退出。全程不读 stdin、不需要 TTY，所以 Agent 可以直接执行，用户只需要在弹出的窗口里点几下。

这也解释了 skill 里那条「禁止用 `&` / `nohup` / `disown` / `setsid` 自行后台化」：这条命令最长挂 180 秒，Agent 必然要放后台等它。用工具管理的后台任务，进程退出会回调 Agent、也能显式终止；用 shell 自行脱离后，一旦登录失败或用户放弃，临时 Chrome 进程和 `cllmk-chrome-*` 临时目录就没人回收，用户下次登录还可能撞上残留端口。

180 秒超时是**用户没来得及操作**，不是故障 —— 这个区分很重要，否则模型会把它报成 CLI 错误，然后开始「排查」，甚至去动 current 或已有会话。

## 3. 为什么沙箱里的 ENOTFOUND 不能当本机故障

Codex、Claude Code 等执行环境会把工具进程放进网络沙箱。此时 `getaddrinfo ENOTFOUND` 只说明**这个进程**没有联网权限，用户本机的 DNS 和网络可能完全正常。把它当成本机故障，结论就会是「请检查你的网络」，而用户那边一切正常。

反过来，也不能因此就无条件重试 —— 重试的风险不对称：

- 读请求（GET / HEAD、只读的 status）重复执行没有副作用。
- 写请求要看错误发生在连接建立**之前**还是**之后**。`ENOTFOUND` / `EAI_AGAIN` 是 DNS 阶段失败，请求根本没出去，可以重试；`ECONNRESET` / `ETIMEDOUT` / `socket hang up` 无法证明服务端没收到，重试就可能重复创建或重复删除。

所以 skill 里的白名单不是保守，是按「能否证明请求未送达」划的线。无法证明时的正确动作是回读确认，而不是重试或猜。

## 4. 为什么 status 从不删凭证

`auth status` 是纯查询。HTTP 401 时它只返回 `Session expired. Credentials preserved.` 和 `data.expired`，凭证和 current 指针都保持原样；403 / 429 / 5xx 同样保留。

这是刻意的：非 401 的失败**不能证明**凭证失效（可能是权限、限流或服务端故障），此时删掉凭证等于让用户白重新登录一次。清除凭证只有一个入口 —— 显式 `auth logout`。

同理，`logout` 从不改 current 指针。如果它顺手把指针挪走，用户登出 A 公司后，下一条裸命令会静默落到 B 公司 —— 这类「指针被副作用悄悄改掉」的问题在业务上非常危险，所以三个动作的磁盘副作用被严格划开：只有 `login` 和 `switch` 写指针，只有 `logout` 删会话，`status` 什么都不写。

## 5. 为什么 CLI 返回里有 email

`login` / `status` / `profiles` 的 `data`，以及 `logout` 的 `cleared` / `remaining` 里都带 `email`，这是 CLI 的设计而非缺陷 —— 用户在终端里自己看，需要知道当前登录的是哪个账号。

约束的对象是 **Agent 的转述**：不得把 email 写进回复、日志或摘要，确认租户一律用公司名与租户 ID。写清这一点是为了避免模型看到 email 后误判「CLI 泄露了敏感信息」，转而去改命令或加参数。

## 6. 其他 skill 如何声明依赖

新 skill 的作者在自己的 SKILL.md 里这样声明（不需要复制 auth.md 的内容）：

```markdown
本 skill 依赖 `<cllmk-dir>/references/foundation/auth.md`。在执行任何 `cllmk curl` 前，请按其前置检查工作流
（确认 `cllmk` 已安装且 `CLLMK_PROFILE` 为空 → 需要切换时按 `tenant-switch.md` 更新 current →
用裸 `cllmk auth status` 确认公司与系统正确 → 按 `auth.md` 分支处理，需要登录时由 Agent
按 `auth.md`「登录流程」代为执行 login）完成鉴权。`cllmk curl` 的具体接口与 payload 写在自己的业务文档里。
```

注意这段示例里**没有** curl 手册的引用。`cllmk curl` 的命令签名与 `--filter` 语法不在 `skills/` 内的任何文件里，
它是写文档时的规范（`doc/curl.md`），由作者在业务文档里直接写出可执行的完整命令 —— 见 §9。

## 7. 为什么删掉了「失败场景处理（完整清单）」

auth.md 曾在末尾附一份 12 条的失败清单，每条都是前文 Step 5 分支表、curl 失败表、登录/登出小节的复述。
两处描述同一个分支，改动时必然漏掉一处 —— 而鉴权失败分支写错的后果是模型跳过登录直接调接口，或把「凭证仍在盘上」报成「已登出」。
现在每个失败分支只在它所属的操作小节出现一次。新增分支时**不要**再建汇总清单，直接加到对应小节的表里。

## 8. 修改 auth.md 时

- 鉴权规则只手写在 `references/foundation/auth.md`，但 **`ats` 与 `people` 各有一份、不共用一个文件**（安装器只平铺 `skills/<name>/`，跨 skill 相对引用会断链，见 AGENT.md §2.1）。
  两份都是最终文档，规则类改动**必须两侧同步落地**：只改一侧的后果不是排版不一致，而是一侧写着「凭证仍在盘上」、另一侧写着「已登出」。
  改完按 AGENT.md §9 在 commit message 里显式说明影响面并列出两侧文件 —— 只列一侧通常意味着漏改。
- `cllmk curl` 的命令用法与 `--filter` 语法**不在 `skills/` 的任何文件里**（见 §9）。auth.md 只保留 curl 与鉴权耦合的三条约束，
  且都已并进正文而不再单独成节：curl 前必须过前置鉴权检查、401/403 必须先跑裸 `auth status` 复验（Step 5 表最后一行）、
  `Request failed` 走「受限执行环境的网络重试」。不要因为「curl 也要鉴权」就把手册内容写回来，也不要新建 `foundation/curl.md`。
- **current 租户的细节不在 auth.md**，在同目录 `tenant-switch.md`（背景见 `doc/tenant-switch.md`，本文 §10、§12 记录了两轮移出经过）。
  auth.md 只在「命令一览」末尾留一段：业务只用 current、logout 是唯一例外、跨租户串行、其余以 `tenant-switch.md` 为准。
- 外部文档按**章节名**引用它：「登录流程」和「受限执行环境的网络重试」被多个 operations 文档直接点名，改名会让引用悬空。
- 「前置鉴权检查」的 **Step 编号也是被外部按名引用的**：`tenant-switch.md`（两侧）指向 Step 1，`doc/curl.md` 指向 Step 5。
  编号原本是 Step 0 / 0.5 / 1 / 2 / 3（0.5 是后来插进去的），已在 6.0.0 一并改为连续的 Step 1–5，
  同时把 `hc-field-manage.md` / `job-field-manage.md` 里镜像的那份编号改成序号 + 章节名引用 —— 那两处本是 AGENT.md §8
  「在 operations 里复制鉴权步骤」的残留，挂着 SKILL.md「业务公共前置」的名却用 auth.md 的编号，会随 auth.md 每次调整一起漂移。
  **再动编号时必须同步这几处**，或者干脆改用章节名引用。
- 安全红线（AGENT.md §5）在本文件里必须保持禁止语气（「禁止」「一律不允许」「停止写入」）。改写成「不在本 skill 覆盖范围」这类边界表述会让模型从「停下来问用户」变成「自己猜一个」。

## 9. curl 手册为什么不在 skill 内

`auth.md` 曾经装着 `cllmk curl` 的完整用法（命令签名、`--filter` 语法、失败全表）。
中途它被拆成过 `foundation/curl.md`（两侧各一份），随后又整体移到 `doc/curl.md`。两次调整的判据不同，都记在 `doc/curl.md` §6，这里只说结论：

**手册不在 `skills/` 内，因为它不会被读到。** 加载纪律下一次业务任务只读「业务公共前置 + 一个 operations 主文档」。
一份通用手册要么永远没人打开，要么得在每份业务文档里加一句跳转 —— 后者等于把维护成本乘以业务数量，换一个本来可以内联两行解决的问题。

现在的落点是三处，缺一不可：

| 内容 | 落点 |
|---|---|
| 命令怎么写、payload、业务成功码 | 各 `operations/` 主文档，直接写出完整可执行的 `cllmk curl ...` |
| `--filter` 的数组下标陷阱 | 用到数组下标的**那一份**业务文档，内联 2–3 行 |
| 响应不得无关展开、大响应先 `--filter` | 两个 `SKILL.md` 的「全局安全规则」（对所有业务路由成立） |
| curl 的鉴权前置与 401/403 复验 | `foundation/auth.md` 的 Step 5 分支表（最后一行）与该表表尾一句 |

写业务文档时的自检在 `doc/curl.md` §5：**这条 curl 命令如果只有它自己被读到，模型能不能正确执行并正确判读失败？**

## 10. 从 auth.md 移出的两节

**「临时会话路由（仅鉴权诊断使用）」** —— 曾经写着「诊断时可以临时用 `--org` / `--profile` / `CLLMK_PROFILE` 指定目标」。
它和同一份文档里的「业务只用 current」是同一件事的两种口径，而模型没有可靠办法判断自己此刻算不算「在诊断」。
实际后果是给了一个绕过 current 验证的合法借口：用 `--org` 查通了，业务命令仍然落在 current 上，两者不是同一个租户时完全无感。
诊断本来也不需要它 —— `switch → status` 两步就能验证任意一个已保存会话，且不留下错位状态。这一节已删除，不要以任何形式恢复。

**「Agent 处理「用 XX 公司操作」的标准工作流」** —— 三步：离线定位并切换 current、裸 status 验证、进业务后不带路由参数。
三步分别是 `tenant-switch.md` §3–§4、§5、「边界」第 3 条，逐条重复了一遍。
「用 XX 公司操作」是一个**路由信号**，处理它的正确位置是 SKILL.md 路由表（「查看已登录公司/current、切换公司/org/profile」那一行指向 `tenant-switch.md`），
而不是在 `auth.md` 里再抄一份流程。同理，原「切换租户 / 系统 / 环境」一节也已合并进「current 租户规则」，只留业务侧真正需要的三条判断。

## 11. People 侧曾经串到 ATS 的接口

people 侧 auth.md 的 curl 示例长期是 `cllmk curl --url /api/v2/org/info --method GET --filter jobFields`，
连注释「只读取职位字段」都照抄了 ATS —— 那是 ATS 的组织信息接口，People 里根本没有「职位字段」这个概念
（People 的 moduleId=11「招聘需求」是另一回事，people/SKILL.md 的边界表专门警告过）。模型照抄必得 404。

这是两侧各存一份带来的固有风险：diff 天然不相等，机器查不出「哪一处是该差异化的、哪一处是漏改的」。
所以 AGENT.md §6.3 把 foundation 的两侧复查列为最高敏感级别的人工项。示例已改成真实的 `POST /api/organization/hr/setting/model/list?bus=20`（`moduleId` 保留占位符，AGENT.md §5.3 不猜 payload），
并在 `code: 0` 那一行补了「外层 `code: 0` 只代表 HTTP 通了，业务成败看内层 `code == 200`」—— 这是 People 与 ATS 最容易互相套错的一处语义。
这个示例现在只剩 `doc/curl.md` §1 一份（作为写文档时的参考），People 的业务成功码则落在 `people/SKILL.md` 的全局安全规则里。

## 12. 第二轮瘦身：又移出的四节

`auth.md` 5.0.0 有 235 行、19 个章节；6.0.0 是 202 行、18 个章节。移出的四节与它们的去处如下 ——
**每一条执行必需的约束都在 `skills/` 内留了落点，没有一条随文件离开分发范围**（AGENT.md §1）。

### 「会话模型」

四条 bullet 里前两条是原理（profile 怎么来的、login 为什么不覆盖别人），已在本文 §1；
「一个 profile 只属于一个 system」压成「命令一览」上方那一句，完整表述在「其它 login 失败分支」的「system 选错」；
「身份字段是登录时刻的快照」和**身份字段对照表**则**没有移走**。

对照表留下来是 AGENT.md §2.1/§6.3 的硬要求：它是模型识别「自己拿错了会话」的唯一依据，
删掉或按 system 拆掉等于把安全兜底删了。只是位置从文档开头挪到了 Step 5 之后（新增 `### 身份字段按 system 分组`）——
判读 `auth status` 输出的地方才是它真正被用到的地方，放在开头模型往往在读到 Step 5 时已经滑过去了。
同时补了一句原文没有的推论：**拿不到本 system 的身份字段就说明会话不属于本 system**，不要改用另一组字段校验。

### 「current 租户规则」

整节的每条硬约束在 `skills/` 内本来就有第二个落点，重复的那份删掉：

| 原约束 | 现在住在哪 |
|---|---|
| 业务只用 current，不带 `--org` / `--profile` / `CLLMK_PROFILE` | 两个 `SKILL.md`「业务公共前置」第 2–3 步；auth.md「命令一览」末段 |
| `logout` 是唯一例外 | 同上一句 + 「登出流程」 |
| 目标租户无会话则 login | Step 5 的 `Not logged in` 行 |
| 切换后 status 失败不回滚 | `tenant-switch.md` §5 |
| 跨租户串行、收尾明示 current | 两个 `SKILL.md` + `tenant-switch.md`「边界」与「完成标准」 |

节首那段「以下行为一律以 `tenant-switch.md` 为准」的清单本身就是 `tenant-switch.md` 的目录副本，属于纯冗余。

### 「系统与环境」

一张 system × env × Web URL 表。**模型不需要它** —— URL 由 `cllmk` 自己解析，业务命令只写路径。
表里真正影响行为的两点已经内联：ats 的 `cn` / `intl` / `s3` 在「登录流程」的 env 那段，
People 的 `dingding` / `test` 未配置→停止在「其它 login 失败分支」和 Step 5 的 `Unknown <system> env` 行。
URL 与实现状态对人有用，留在本文与 `people/SKILL.md` 的「People 环境」表即可。

### 「curl 与鉴权的衔接」

三条 bullet：前置检查那条和 `Request failed` 那条分别与 Step 5、「受限执行环境的网络重试」重复，直接删。
**401 / 403 复验那条在 `skills/` 内没有第二份**，所以它不是「移走」而是**换了形态**：
成为 Step 5 分支表的最后一行（`code` 列写 `—`，因为它不是 cllmk 的返回码而是 curl 的 HTTP 状态）。

放进那张表比单独成节更可靠：模型遇到 401 时正在做的事就是「查表判断下一步」，
而独立小节要靠它记得往下翻。语义一字未减 —— 不代表凭证失效、不会清除会话、必须先跑裸 `auth status` 复验、
403 在会话有效时是业务权限问题（报告并停止，不重新登录）。

### 就地精简的三节

- **Step 5 分支表**：14 行（people 13 行）→ 10 行。删掉的是 login / logout 自己的返回（`Login timeout.`、`Chrome not found.`、ats `账号角色不正确`、people `URL not configured`、`Logout failed` 的细节），
  它们在「登录流程」「登出流程」里有完整处置；表尾补一句指回去。`Old syntax` 这类一次性提示压进表尾同一句。
  保留的 10 行是**只有这张表才有**的判断：`0`、`Not logged in`、两种「Credentials preserved」的区别、`status endpoint not configured`、`Unknown env`、`Request failed`、switch 失败、logout 失败、curl 401/403。
- **受限执行环境的网络重试**：7 条 → 4 条。原 1+2 合成「只读命令可重试一次」，3+4 合成「写请求只有 DNS 失败可重试」（AGENT.md §5 红线 5 的语义一字未改），
  原 6 的「不静默扩大授权范围」并进「重试不得改参数」那条。`getaddrinfo ENOTFOUND` 不能判定为本机 DNS 异常仍在节首。
- **登录流程**：只删「180 秒非交互机制」的展开（原理在本文 §2）。**章节名必须保持「登录流程」**——
  `tenant-switch.md`（两侧）和 `operations/protection-period-country/index.md` 三处按名引用它。
  「受工具管理的长运行会话」、`&` / `nohup` / `disown` / `setsid` 禁令、两段面向用户的话术、四种回退情况、
  「超时是用户没来得及操作」、「登录后的验证」全部原样保留 —— 前四项都是别处按名引用或红线约束的对象。
