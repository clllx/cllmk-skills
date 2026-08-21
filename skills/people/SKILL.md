---
name: people
metadata:
  version: "1.2.0"
description: "Moka People 人事系统的 cllmk 统一操作入口。当前覆盖「人事设置 → 员工信息设置」的字段管理：查询档案分类/分组/字段、创建自定义字段、编辑字段、停用与启用字段。用户提到 Moka People、人事系统、员工信息设置、员工字段、人事字段、档案分类、字段分组、core.mokahr.com，或 `model/list`、`field/add`、`field/edit`、`field/detail`、`field/enable`、`field/disable`、`combinedField/list` 等接口时使用本 skill。ATS 招聘侧的候选人字段、登记表、职位与 HC 字段属于 `ats` skill，不要路由到这里。先按路由表选择唯一业务文档，再按需加载参考，禁止一次性读取全部 references。"
compatibility: "依赖 cllmk CLI 与一个 system=people 的有效会话；鉴权规则复用 cllmk skill 套件。"
---

# Moka People 统一路由

本 skill 是 `cllmk` 对 **Moka People 人事系统**（`https://core.mokahr.com`）操作的统一入口。它负责识别意图、执行公共安全前置检查，并只加载当前任务需要的参考文档。

ATS 招聘系统的业务由同级的 `ats` skill 负责；两者共用一套 CLI、鉴权与租户模型，但**接口路径、成功码与数据模型完全不同**，不可互相套用。

## 路径约定

本文中的 `<skill-dir>` 指本文件所在目录，即 `skills/people/`。安装、鉴权、租户切换的基础文档在 `<skill-dir>/references/foundation/`，本 skill 自带一份，不依赖其他 skill 是否安装。任一相对路径不存在时，报告 cllmk skill 套件安装不完整并停止。

## 加载纪律

1. 先从下方路由表选择一个主路由；意图不明确且不同路由的副作用不同才询问用户。
2. 执行「业务公共前置」，再完整读取对应的一个 `references/operations/*` 主文档。
3. 主文档指向更细的 reference 时，只读取当前分支点名的文件。不要预读其他业务文档。
4. 单个请求确实包含多个独立操作时，按用户期望顺序逐个路由；每次只保持一个业务流程在执行态。

## 基础能力路由

鉴权、安装、租户切换**不在本 skill 内重复定义**，一律读取 cllmk 套件的单一事实来源：

| 用户意图 | 读取 |
|---|---|
| 安装、升级、找不到 `cllmk`、确认版本 | `<skill-dir>/references/foundation/install.md` |
| 登录、退出登录（含全部退出）、登录状态、会话过期、HTTP 401/403、curl 失败分支 | `<skill-dir>/references/foundation/auth.md` |
| 查看已登录公司/current、切换公司/org/profile | `<skill-dir>/references/foundation/tenant-switch.md` |

## People 业务路由

| 意图或接口信号 | route | 读取 |
|---|---|---|
| 员工信息设置、员工字段、人事字段、档案分类/分组、新增或修改员工自定义字段、停用/启用员工字段、组合字段（证件/银行卡）在员工档案中的使用、`model/list`、`field/add`、`field/edit`、`field/detail`、`field/enable`、`field/disable`、`base/combinedField/list` | `employee-field-manage` | `references/operations/employee-field-manage.md` |

> 后续 People 业务（假勤、薪酬、组织、审批等）在此表继续追加，每个业务一份独立主文档。

## 容易混淆的边界

| 用户表达 | 正确路由 |
|---|---|
| 「候选人字段」「登记表/申请表/应聘表」 | **ATS**，使用 `ats` skill 的 `candidate` 路由，不是本 skill |
| 「职位字段」「HC/招聘需求字段」 | **ATS**，使用 `ats` skill；注意 People 也有 moduleId=11「招聘需求」，两者不是一回事 |
| 「员工字段」「人事字段」「员工信息设置」 | 本 skill 的 `employee-field-manage` |
| 「字段」但未说明系统 | **停下询问**是招聘（ATS）还是人事（People）；两系统都有「字段」概念且接口完全不同 |
| 「职级」「职位级别」 | **停下询问是哪套系统**。招聘侧（单 ATS 系统）用 `ats` skill 的 `job-rank-manage` 路由（`ats-jc/job/jobRank/*`）；People 侧职级是另一套接口与数据模型，不在本 skill 覆盖范围，不得套用 ATS 的 jobRank 接口 |
| 「添加分组」「档案结构设置」「联动规则」「字段排序」「删除字段」 | 不在本 skill 覆盖范围，见主文档的「不覆盖清单」 |
| 「组合字段」的定义与增删（基础设置页） | 不在本 skill 覆盖范围；本 skill 只在创建员工字段时**引用**已有组合类型 |
| 简历/数据保留期限 | 使用独立的 `ats-resume-retention` skill |

## 业务公共前置

所有 People 业务路由在发起读取租户数据或写请求前执行：

1. 运行 `command -v cllmk`，再运行 `cllmk --version`。未安装时停止业务流程，按 `<skill-dir>/references/foundation/install.md` 引导安装。
2. 检查 `CLLMK_PROFILE`。非空时停止，要求用户清除后重试；业务流程只允许使用 current。
3. 若用户指定公司、tenantId 或 profile，先按 `<skill-dir>/references/foundation/tenant-switch.md` 切换 current；不要在业务命令上附加 `--org`、`--profile` 或临时环境变量。
4. 运行裸 `cllmk auth status`。仅当 `code == 0`、**`data.system == "people"`** 且 `tenantId/buId/corpName/env` 与目标一致时继续。People 会话不返回 `orgId` / `orgName`，不要拿这两个字段做校验。
5. 会话是 ATS（`data.system == "ats"`）时**停止**，不要用 ATS 会话调用 People 接口。改为登录 People：
   > 当前会话是 ATS 招聘系统，本操作需要 People 人事系统。我来执行 `cllmk people pp auth login`，本机会弹出一个 Chrome 窗口，请用目标公司的账号完成登录，我接着往下做。

   随后在受工具管理的长运行会话中执行该命令；ATS 会话不会被覆盖（仍保存在原 profile 下），但 **current 指针会移到新的 People 会话**。
   **在自动登录前必须先记录当前 ATS profile 名**（用无参数 `cllmk auth switch` 查看 current），
   任务完成后**默认主动 `cllmk auth switch --profile <原 ATS profile>` 切回**，
   并向用户明示 current 的最终位置。

6. **任务收尾强制规则**：只要本 skill 触发过 ATS→People 的自动登录切换，任务结束时必须：
   - 显式切回任务开始时的 ATS profile（除非用户明确说"留在 People"）。
   - 向用户报告「current 已从 `<原 ATS profile>` 切到 `<新 People profile>`，已切回/保留在 `<最终 profile>`」，
     下一条命令会落在那里。
   - 不允许无声保留 current 在 People。

7. 未登录、过期、网络错误或 HTTP 401/403 时，按 `<skill-dir>/references/foundation/auth.md` 对应分支处理。需要登录时由 Agent 按该文档「登录流程」执行 login，用户只在浏览器里完成认证；仅在该文档列出的四种回退情况下才把命令交还用户。

8. 向用户展示不含凭证的目标环境与租户。写操作执行前按业务文档完成范围、影响面与确认项检查。

### People 环境

| env | Web URL | 状态 |
|---|---|---|
| `pp` | https://core.mokahr.com | 已实现 |
| `dingding` | — | URL 待配置（TODO），不能登录不能调用 |
| `test` | — | URL 待配置（TODO），不能登录不能调用 |

`cllmk auth switch` 的 current 指针是 ATS 与 People 共享的全局状态。跨系统或跨租户任务按 `switch → status → 完成本任务 → switch` 串行执行，不并行运行不同会话的业务脚本。

## 全局安全规则

- 不输出 Cookie、认证头或凭证文件内容，不手动编辑 cllmk 的 auth/profile/current 文件。
- **People 接口的成功码是 `code == 200`，不是 ATS 的 `code == 0`。** 不要把 cllmk 外层 `code == 0` 等同于业务成功；必须检查响应体内层的 `code`。
- 创建、编辑、停用、启用等写操作，执行前必须向用户展示完整 payload 并获得明确确认。
- `field/edit` 是**全量覆盖**语义，漏传的键会被重置。任何编辑前必须先用 `field/detail` 读回原值。
- 遇到未覆盖的接口形态、字段类型或数据结构时停止写入，说明缺少的 UI curl 或业务信息，不猜测 payload。
- **语义未确认的参数不得使用默认值静默提交。** 必须在确认环节单独列出并由用户明示取值。（当前无此类参数：`applyTargetLibrary` 已于 2026-07-30 确认语义，见业务文档 §5.3.1。）
- 员工档案字段是全租户共享配置，一次改动影响所有员工。批量操作前明确告知影响范围。
