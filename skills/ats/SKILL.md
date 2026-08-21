---
name: ats
metadata:
  version: "1.11.0"
description: "Moka ATS 业务的 cllmk 统一入口，覆盖候选人/申请删除、人才库移除、应聘阶段移动、候选人字段和登记表、职位与 HC 字段、Offer 字段与模块（含选项级联动、隐藏/显示）、Offer 附件模板（生成带占位符的 docx、上传、保存、电子签开关）、单 ATS 系统的职位级别（职级）增删改查与合并、职位硬删除、国家维度渠道保护期、面试评价表配置、面试题库增删改查，并在业务前按需加载安装、鉴权和 current 租户规则。用户提出上述 ATS 业务操作、相关接口路径，或要求在指定公司/org 下执行 ATS 操作时使用；只想安装 CLI 时优先 `cllmk-install`，只问登录/会话错误时优先 `cllmk-auth`，只列出或切换租户时优先 `cllmk-tenant-switch`。职位批量创建、跨租户迁移、简历/数据保留期限（用 `ats-resume-retention`）、Moka People 人事字段与 People 侧职位级别（用 `people`）不在本 skill 覆盖范围。"
compatibility: "Requires the cllmk CLI for live Moka API calls; installation guidance supports macOS, Linux, and Windows PowerShell."
---

# cllmk 统一路由

本 skill 是 `cllmk` 与 Moka ATS 操作的统一入口。它负责识别意图、执行公共安全前置检查，并只加载当前任务需要的参考文档。

## 路径约定

本文中的 `<skill-dir>` 指本文件所在目录，即 `skills/ats/`。运行脚本时使用 `<skill-dir>/scripts/...`，不要猜测其他目录名。

## 加载纪律

1. 先从下方路由表选择一个主路由；意图不明确且不同路由的副作用不同才询问用户。
2. 基础任务只读取对应的一个 `references/foundation/*.md`。
3. ATS 业务任务先执行本文的「业务公共前置」，再完整读取对应的一个 `references/operations/*` 主文档。
4. 主文档指向更细的 reference 时，只读取当前分支点名的文件。不要预读其他业务文档。
5. 单个请求确实包含多个独立操作时，按用户期望顺序逐个路由；每次只保持一个业务流程在执行态。

## 基础能力路由

| 用户意图 | 按需读取 |
|---|---|
| 安装、升级、找不到 `cllmk`、确认版本 | `references/foundation/install.md` |
| 登录、退出登录（含全部退出）、登录状态、会话过期、HTTP 401/403、curl 鉴权与失败分支 | `references/foundation/auth.md` |
| 查看已登录公司/current、切换公司/org/profile | `references/foundation/tenant-switch.md` |

基础能力的完整规则位于本 skill 内；独立的 `cllmk-install`、`cllmk-auth`、`cllmk-tenant-switch` skill 仍保留为兼容入口，并指向同一套文档。

## ATS 业务路由

| 意图或接口信号 | route | 读取 |
|---|---|---|
| 删除候选人主档、删除申请、`application/delete`、`application/bulk/delete` | `application-delete` | `references/operations/application-delete.md` |
| 移动/推进候选人应聘阶段、`move-stage/v2` | `application-move-stage` | `references/operations/application-move-stage.md` |
| 候选人字段、自定义字段、登记表/申请表/应聘表/报名表 | `candidate` | `references/operations/candidate/index.md` |
| 招聘需求字段、HC/Headcount 字段、`hc_custom_fields` | `hc-field-manage` | `references/operations/hc-field-manage.md` |
| 职位字段、职位自定义字段、查询 `jobFields`、`jobCustomFields/create` | `job-field-manage` | `references/operations/job-field-manage.md` |
| 职位级别/职级的增删改查、合并职级、`jobRank/listForManage`、`jobRank/create`、`jobRank/update`、`jobRank/merge` | `job-rank-manage` | `references/operations/job-rank-manage.md` |
| 面试评价表、评价表模板、`feedbackTemplates` | `interview-feedback-form` | `references/operations/form-config/interview-feedback-form.md` |
| 面试题库、面试题的增删改查、`interviewQuestion/getInterviewQuestionList`、`interviewQuestion/save`、`interviewQuestion/update`、`interviewQuestion/delete` | `interview-question-bank` | `references/operations/interview-question-bank.md` |
| 硬删除校招/社招职位、`deleteJob` | `job-delete` | `references/operations/job-delete.md` |
| Offer 字段、Offer 自定义字段、Offer 模块/分组、Offer 字段联动、`ats-offer/customFields`、`ats-offer/customFieldGroup`、`offer-custom-field-link` | `offer-field-manage` | `references/operations/offer-field-manage.md` |
| Offer 附件模板、录用通知函/录用通知书模板、模板里的字段占位符、电子签签署区、`office_template/offer/upload`、`ats-offer/template/save`、`getOfferTemplateById` | `offer-template-manage` | `references/operations/offer-template-manage.md` |
| 职位级保护期方案、按国家配置/排序、`protectionPeriod` | `protection-period-country` | `references/operations/protection-period-country/index.md` |
| 从人才库移除候选人、`talent-pool-candidates/bulk/delete` | `talent-pool-candidate-delete` | `references/operations/talent-pool-candidate-delete.md` |

## 容易混淆的边界（指针型）

下表只做**路由转向**。业务细节（类型映射、参数语义、坑）一律在对应 reference 主文档里，不要在这里展开。

| 用户表达 | 正确路由 |
|---|---|
| 「员工字段」「人事字段」「员工信息设置」「档案分类/分组」 | **People**，使用 `people` skill，不在本 skill |
| 「字段」但未说明系统 | 停下询问是招聘（ATS）还是人事（People），两系统字段模型完全不同 |
| 「从人才库拿掉」 | `talent-pool-candidate-delete` |
| 「删除申请」/「删除候选人主档」 | `application-delete`，必须让用户显式确认删除类型 |
| 「关闭/暂停/归档职位」 | 不在本 skill 覆盖范围；`job-delete` 只做不可逆硬删除 |
| 「批量创建/导入/迁移职位」、「create-job」 | 不在本 skill 覆盖范围；不要调用本 skill 内的脚本或猜测客户映射 |
| 「删除/修改职位字段」 | `job-field-manage`（该文档说明不在覆盖范围并**停止写入**，不要猜 endpoint） |
| 「阶段模板 CRUD / 新增 stage」 | 不在本 skill 覆盖范围；`application-move-stage` 只移动应聘 |
| 「满意度/人才/简历筛选/试工反馈 评价表」 | 不在本 skill 覆盖范围；`interview-feedback-form` 只做面试评价表 |
| 「评价表绑定到职位/面试轮次」 | 不在本 skill 覆盖范围；`interview-feedback-form` 只管模板本体，需提示用户手工绑定 |
| 「面试题」「题库」 | `interview-question-bank` |
| 「评价表关联题库」 | 关联字段在 `interview-feedback-form`，题目本体在 `interview-question-bank` |
| 「校招的面试题库」 | 不存在这个概念：题库**不分**社招/校招（`interview-question-bank`）；分场景的是评价表（`interview-feedback-form`，每张表带 `hireMode`） |
| 「面试结果规则」「面试评价选项」增改 | 不在本 skill 覆盖范围；`interview-feedback-form` 只读取它们做 ID 映射 |
| 「简历/数据保留期限」 | 使用独立 `ats-resume-retention` skill |
| 「标准全局保护期」「按部门保护期」 | 不在本 skill 覆盖范围；`protection-period-country` 只处理职位级方案 + 按国家分组 |
| 「职级」「职位级别」未说明系统 | 停下询问是招聘（`job-rank-manage`）还是人事（`people`） |
| 「职位级别」指渠道保护期维度 | `protection-period-country`，不是 `job-rank-manage` |
| 「删除职级」 | `job-rank-manage`（只能 `merge`，见主文档） |
| 「删除/停用 Offer 字段」 | `offer-field-manage`（只能隐藏，见主文档） |
| 「Offer 字段要多选」 | `offer-field-manage`（产品不支持多选，见主文档） |
| 「Offer 模板」 | 停下区分：附件模板 → `offer-template-manage`；字段模块 → `offer-field-manage`；邮件/审批模板 → 不在本 skill 覆盖范围 |
| 「Offer 附件模板」在线编辑型 | 不在本 skill 覆盖范围；`offer-template-manage` 只覆盖上传型（docx） |
| 「占位符不被替换」 | `offer-template-manage`，见主文档 §4 |
| 「改一下 Offer 附件模板」 | `offer-template-manage`，仅改名字 → `template/updateName`；换文件 → `template/save`（版本化，见主文档 §6） |
| 「校招的 Offer 附件模板」 | `offer-template-manage`，见主文档 §1.2 |
| 「字段」未说明候选人还是 Offer | 停下询问；两者 type 枚举与序列化方式完全不同（见各自主文档） |

## 业务公共前置

所有 ATS 业务路由在发起读取租户数据或写请求前执行：

1. 运行 `command -v cllmk`，再运行 `cllmk --version`。未安装时停止业务流程，按 `references/foundation/install.md` 引导安装。
2. 检查 `CLLMK_PROFILE`。非空时停止，要求用户清除后重试；业务流程只允许使用 current。
3. 若用户指定公司、orgId 或 profile，先按 `references/foundation/tenant-switch.md` 切换 current；不要在业务命令上附加 `--org`、`--profile` 或临时环境变量。
4. 运行裸 `cllmk auth status`。仅当 `code == 0`、`data.system == "ats"` 且 `orgId/orgName/env` 与目标一致时继续。
5. 未登录、过期、网络错误或 HTTP 401/403 时，按 `references/foundation/auth.md` 对应分支处理。需要登录时由 Agent 按该文档「登录流程」在受工具管理的长运行会话中执行 login，用户只在弹出的浏览器里完成认证；仅在该文档列出的四种回退情况下才把命令交还用户。
6. 向用户展示不含凭证的目标环境与租户。写操作执行前按业务文档完成范围、不可逆性、dry-run/确认项和日志位置检查。

`cllmk auth switch` 的 current 指针是共享状态。跨租户任务应按 `switch -> status -> 完成本租户任务 -> switch` 串行执行，不并行运行不同租户的业务脚本。任务收尾时向用户明示 current 最终停在哪个租户——它不会自动复原，用户的下一条命令会落在那里。

## 全局安全规则

- 不输出 Cookie、认证头或凭证文件内容，不手动编辑 cllmk 的 auth/profile/current 文件。
- 不把 cllmk 外层 `code == 0` 等同于业务成功；按所选业务文档检查内层 `data.success` 和业务码。
- 删除、阶段移动、保护期修改等写操作默认只预览；只有脚本显式收到 `--confirm --expected-org-id <orgId>` 且实时 current orgId 完全匹配时才允许写入。
- 遇到未覆盖的接口形态、字段结构或保护期模式时停止写入，说明缺少的 UI curl 或业务信息，不猜测 payload。
- **社招/校招是服务端会话状态**，不由 payload 或请求头决定，用户可能在 Web 端随时切换。涉及按
  hireMode 分流的配置（如面试评价表、Offer 字段与模块）时，操作前必须用 `GET /api/v2/org/info` 读
  `data.currentUserInfo.currentHireMode`（1=社招 / 2=校招）并向用户明示；与目标不一致时停止，**不得自动切换**。
