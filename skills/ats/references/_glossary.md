# cllmk 业务技能术语表

本文件是 cllmk skill 套件（`ats` / `people` / `cllmk-*`）的术语单一事实来源。
所有 SKILL.md 与 references 文档**必须使用本表的标准说法**，不要同义改写。

## 系统与账号

| 术语 | 标准说法 | 备注 |
|---|---|---|
| Moka ATS | **ATS 招聘系统** / **ATS** | 禁用「招聘后台」「HR 招聘」等同义词 |
| Moka People | **People 人事系统** / **People** | 禁用「人事后台」「HR 人事」等同义词 |
| profile | **profile** | 一个 profile = 一份独立会话（system + env + 一家公司） |
| current | **current 指针** / **current** | 全局共享状态，只允许 `login` 和 `auth switch` 写 |
| profile 名 | **profile** / **profile 名** | 形如 `ats-<orgId>` / `people-<tenantId>` |
| 租户 ID | ATS 用 **orgId**，People 用 **tenantId** | 不混用 |
| 公司名 | ATS 用 **orgName**，People 用 **corpName** | 不混用 |
| 登录环境 | **env** | ATS：`cn` / `intl` / `s3`；People：`pp` |

## 业务概念

| 术语 | 标准说法 | 备注 |
|---|---|---|
| 候选人档案 | **候选人主档** | 关联 N 份申请 |
| 应聘申请 | **申请** / **application** | 单独可删 |
| 硬删除 | **不可逆硬删除** / **硬删除** | 不用「彻底删除」「永久删除」 |
| 人才库移除 | **人才库移除** | ≠ 候选人主档删除 |
| 应聘阶段 | **应聘阶段** / **stage** | 推进 = **移动阶段**，不是「新增 stage」 |
| 职位级别 | **职级** / **职位级别** / **jobRank** | 单 ATS 系统内有效 |
| 招聘需求 | **HC** / **Headcount** / **招聘需求** | 不是「职位」 |
| Offer 字段 | **Offer 字段** / **Offer 自定义字段** | 与候选人字段是两套独立接口 |
| Offer 模块 | **Offer 模块** / **Offer 分组** | 字段的容器 |
| Offer 附件模板 | **Offer 附件模板** / **录用通知函模板** | ≠ 邮件模板、≠ 审批模板、≠ 字段模块 |
| 校招 / 社招 | **hireMode**（1=社招，2=校招） | 服务端会话状态，不可 payload 传 |
| 面试评价表 | **面试评价表模板** / **feedbackTemplate** | 分 hireMode（社招/校招）；正文可简称「面试评价表」 |
| 面试题库 | **面试题库** | 社招/校招共用一套 |
| 渠道保护期 | **渠道保护期** / **protection period** | 分全局 / 职位级 / 国家维度 |
| 简历 / 数据保留期限 | **保留期限** / **retention** | 由独立 `ats-resume-retention` skill 处理 |
| 登记表 | **登记表** / **apply form** / **applyForm** | 候选人投递时填写的表单 |
| 标准字段 | **标准字段** / **standard field** | Moka 预置的字段池 |
| 自定义字段 | **自定义字段** / **custom field** | 租户自己加的字段 |
| 字段模块 | **字段模块** / **字段分组** / **customBlock** / **model** | 字段的容器，候选侧叫 customBlock，People 侧叫 model |
| 字段类型 | **字段类型** / **type** | ATS 候选人字段是字符串（`select_info`），Offer 字段是数字（`6`），People 是 code |
| 占位符 | **占位符** / **placeholder** | Offer 附件模板里 `[字段id]` 形式的占位标记 |
| 电子签 | **电子签** / **e-sign** | 模板上的电子签名区块 |
| hireMode 探测 | **hireMode 探测** | 用 `GET /api/v2/org/info` 读 `data.currentUserInfo.currentHireMode` |
| 主数据下发 | **主数据下发**（People → ATS） | 比如 People 下发职级到 ATS，**只读侧** |
| 唯一申请 | **唯一申请** / **UNIQUE_APPLICATION** | 错误码 400059，候选人只有这一份申请时不能直接删申请 |
| 业务成功码 | ATS 是 `data.success:true`；People 是响应体 `code:200` | **完全不同的两套**，不可混用 |

## Skill 套件术语

| 术语 | 标准说法 | 备注 |
|---|---|---|
| 业务公共前置 | **业务公共前置**（Step 1–6 / Step 1–8） | 所有 operation 文档首行 callout 引用同一说法 |
| 路由 | **route** | frontmatter 字段名，全仓库统一用 `route:`，不用 `name:` |
| 单一事实来源 | **单一事实来源** / **SSOT** | 描述 foundation 目录的职责 |
| 主路由 / 子场景 | **主路由** / **子场景** | 主路由由 SKILL.md 路由表派发，子场景在主路由文档内 |
| 超出范围 | **不在本 skill 覆盖范围** | 不用「不支持」「不处理」「待建」等口语 |
| 安全硬约束 | **不允许 / 禁止 + 动作** | 「禁止猜 type」「一律不允许创建」；**不可**用「不在本 skill 覆盖范围」替代 |

## 表述约束

- 所有「超出范围」的表达统一为「**不在本 skill 覆盖范围**」或「**不在本路由覆盖范围**」，不再使用「当前不覆盖」「待建」「待扩展」。
- 所有「鉴权前置」的引用统一为 callout：
  ```
  > ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–N），
  >   确认 `data.system === "<ats|people>"`。
  ```
- 「本路由」/「本 skill」后面不跟空格再跟动词；避免「本路由 通过」「本路由 覆盖」这类带空格的写法。
- 用户表达统一用中文引号「」包裹，不用英文双引号 `""`（本文件与 AGENT.md、README 同样受此约束）。
- **范围边界与安全硬约束是两类表述，不可互换**：
  - 范围边界（「本 skill 没做这件事」）→「不在本 skill 覆盖范围」+ 给出替代路径。
  - 安全硬约束（「做了就是事故」）→ 保留「一律不允许」「禁止」「停止写入」等禁止语气，
    可以在括号里附带范围说明，但**不能只留范围说明**。误把硬约束改写成范围声明会让模型
    以为「只是本 skill 没覆盖，自己猜一个也行」，这正是 §5 红线 3（不猜 payload）要防的事。
