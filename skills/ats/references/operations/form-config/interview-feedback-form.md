---
route: interview-feedback-form
---

# ATS 面试评价表配置

通过 `cllmk curl` 管理 Moka ATS 的**面试评价表模板**：导出、比对、创建、更新、删除。

> URL 前缀：`/api/outer/ats-interview/interview/feedbackTemplates/*`
>
> 设置页：`https://<host>/settings/interview_feedback_form`
>
> 鉴权：先执行 `<skill-dir>/SKILL.md` 的「业务公共前置」

## 目录

- 第 0 步：作用域确认（必做）
- 第 1 步：鉴权与 hireMode 场景探测（必做）
- 第 2 步：接口清单
- 第 3 步：读写不对称（核心陷阱）
- 第 4 步：数据结构
- 第 5 步：枚举与校验
- 第 6 步：四个操作原语（export / plan / create / update）
- 第 7 步：跨租户搬运规则
- 未覆盖项与停止规则
- 失败处理

---

## 第 0 步：作用域确认（必做）

Moka 后台有多种「评价表」，本路由**只覆盖面试评价表**。触发后第一步必须确认作用域：

| 设置页 | 本路由是否覆盖 |
|---|---|
| 面试管理 → **面试评价表**（`/settings/interview_feedback_form`） | ✅ **唯一覆盖范围** |
| 候选人满意度管理 → 候选人满意度评价表 | ❌ 接口不同（`interviewSatisfactionTemplate` 系列），未覆盖 |
| 招聘分类信息 → 人才评价表 | ❌ 未覆盖 |
| 招聘流程管理 → 简历筛选评价表设置 | ❌ 未覆盖 |
| 试工管理 → 试工反馈 | ❌ 独立表 `shigong_feedback_templates`，未覆盖 |
| 面试管理 → 面试评价选项管理 / 面试结果规则 | ❌ 本路由只**读取**它们做映射，不创建不修改 |

### 本路由明确不做的事

- **不绑定职位与面试轮次**。评价表通过 `job_round_feedback_connections`（职位 → 面试轮次 → 评价表）
  才真正对面试官生效。本路由只管模板本体，创建完成后必须向用户明示：

  ```
  ⚠️ 评价表已创建，但尚未绑定到任何职位/面试轮次，面试官目前看不到它。
  请到「设置 → 面试管理 → 面试轮次设置」手工绑定，或告知我这部分需求（当前未覆盖）。
  ```

- **不创建面试结果规则**。`ruleConfig` 依赖租户本地的规则引擎对象，见第 7 步。
- **不切换社招/校招场景**。只探测，见第 1 步。

---

## 第 1 步：鉴权与 hireMode 场景探测（必做）

### 1.1 鉴权

按 `<skill-dir>/SKILL.md` 的业务公共前置完成：`command -v cllmk` → 确认 `CLLMK_PROFILE` 为空 →
必要时按 `<skill-dir>/references/foundation/tenant-switch.md` 切换 current →
裸 `cllmk auth status` 且 `code:0`、`data.system == "ats"`。

### 1.2 🚨 hireMode 是隐藏的服务端会话状态

社招/校招**既不看 payload 的 `hireMode`，也不看请求头**，而是一个**服务端按用户存储的会话状态**，
由 Web 端左上角的场景切换器修改。实测：payload 传 `hireMode:1` 与 `hireMode:2` 返回**完全相同**的结果；
用户在浏览器里切到校招后，同一个裸请求返回的就是校招数据。

这是一个和 `current` 租户指针**同性质的隐藏全局状态**，且用户可能在浏览器里随时改动它。因此：

```bash
# 每次操作前必做：探测当前场景
cllmk curl --url /api/v2/org/info --method GET --filter data.currentUserInfo.currentHireMode
```

| 值 | 场景 |
|---|---|
| `1` | 社招 |
| `2` | 校招 |

> ⚠️ 字段在 **`data.currentUserInfo.currentHireMode`**，顶层 `data.currentHireMode` 不存在。
> 用错路径时 `cllmk` 返回 `{"code":1,"data":null,"msg":"Response filter path not found: 'data'"}`
> —— 报错里的 `'data'` 是误导，实际是整条路径没命中，不是没登录也不是接口异常。
> 该端点上 `--filter` 曾出现命中失败，必要时改为不带 `--filter` 拉全量再本地取该路径。

规则：

1. 读取结果必须向用户明示「当前处于 **社招 / 校招**」，再继续。
2. 用户指定的目标场景与探测结果不一致时**停止**。**不要自动切换** ——
   切换接口是 `POST /api/users/update_currenthiremode_fields`，它会改变用户 Web 端的全局状态，
   且本 skill 未采集其 payload。请用户自己在 Web 端切换后重新触发任务。
3. 列表接口返回的就是「当前场景」下的表。不要把「校招下只看到 1 张表」误报成租户配置缺失。
4. **评价表分场景，但它引用的面试题库不分场景**（两场景共用同一组题目，见 §4.4.5）。
   不要因为要处理校招表就去找「校招题库」——没有这个东西。

---

## 第 2 步：接口清单

全部为 POST，payload 为 JSON。

| 用途 | 路径（前缀 `/api/outer/ats-interview/interview/feedbackTemplates/`） | payload |
|---|---|---|
| 列表 | `getFeedbackTemplateList` | `{}` |
| 详情 | `getFeedbackTemplateByIdPermission` | `{"id":"<id>"}` ← **字符串** |
| 创建 | `saveFeedbackTemplate` | 见 §4.1；返回 `data` = 新 id（数字） |
| 更新 | `updateFeedbackTemplate` | §4.1 + `id` ← **数字** |
| 删除 | `removeFeedbackTemplate` | `{"id":"<id>"}` ← **字符串** |

```bash
# 列表（返回当前场景下全部表，且已含每张表完整的 items）
cllmk curl --url /api/outer/ats-interview/interview/feedbackTemplates/getFeedbackTemplateList \
  --method POST --payload '{}'

# 详情（比列表多返回 ruleConfig）
cllmk curl --url /api/outer/ats-interview/interview/feedbackTemplates/getFeedbackTemplateByIdPermission \
  --method POST --payload '{"id":"<template-id>"}'
```

> `getFeedbackTemplateList` 已经返回每张表完整的 `items`，**导出不需要逐个调详情**；
> 只有需要 `ruleConfig` 时才逐个调 `getFeedbackTemplateByIdPermission`。

### 2.1 🚨 删除不受场景限制

`removeFeedbackTemplate` 按 id 删除，**不校验当前 hireMode**（实测在校招会话下成功删除了社招创建的表）。
删除前必须先调详情确认 `name` 与 `hireMode` 都是用户要删的那张，并让用户显式确认。

### 2.2 未采集的同族端点

`getFeedbackTemplateById`、`getFeedbackTemplateListPermission`、`getFeedbackTemplateListPermission20`、
`getFeedbackTemplateOfJobById`、`hm/getFeedbackTemplateByJob`、`hm/getFeedbackTemplateByRound`、
`addFeedbackCache`、`getFeedbackCache`、`isOptional`、`resultRuleWarmUp`。

Inner API（`/api/inner/.../feedback-templates` 的 `saveFeedbackTemplates` 批量、`mergeToOtherMigrate` 迁移合并）
是**服务间调用，Cookie 鉴权到不了**，`cllmk` 不可用，不要基于它设计任何流程。

---

## 第 3 步：读写不对称（核心陷阱）

读接口把这些字段返回成 **JSON 字符串**，写接口要求它们是**真数组**：

```
items  ruleConfig  departmentIds  feedbackQuestion  linkageRelationship
```

导出后回填必须先 `fromjson`。其余不对称：

| 项 | 读 | 写 |
|---|---|---|
| `id` | 字符串（detail / remove） | **数字**（update） |
| `linkageLevel` | 不返回 | 写入时 UI 会带（可省略） |
| `ruleConfig` | 无规则时**字段缺失**（不是 `[]`），`enableRule` 是 `true` 还是 `false` 都一样，list 与 detail 都缺 | 传 `[]` |
| `linkageRelationship` | 创建时未下发该字段的表，读回来**字段缺失**（不是 `[]`）；下发过 `[]` 的读回是 `"[]"` | 传 `[]` |
| 模块 `calcScoreType` | 可能是 **`null`**（不只是 `""`） | 归一成 `""` 下发，见 §4.2 |
| `feedbackQuestion.questions[]` | **list 与 detail 形态不同**：list 只有 `{id}`；**detail 富化成 `{id, title, description, type}`** | 只传 `{id}`，富化字段不要回填 |
| `subjects[].relatedQuestion` | 只有 `true` 会返回；未关联时**字段缺失**（不是 `false`） | 关联时必须显式传 `true`，见 §4.4.1 |
| `departmentInfos` | detail 独有的派生字段 | 不下发 |
| `version` | detail 返回 | 不下发 |

`ruleConfig` 缺失是**常态**，不是读取不完整或权限不足，不要据此重试或报错。`linkageRelationship` 缺失同理。

模块 `calcScoreType` 为 `null` 的**来源已确认**：UI 创建时根本不下发模块层的该字段。实测显式传 `""`
会落库成 `""`，所以归一成 `""` 是安全路径（§4.2）。

---

## 第 4 步：数据结构

### 4.1 顶层 payload

```jsonc
{
  "id": <template-id>,           // 仅 update
  "name": "表名",                 // 与 hireMode 组成幂等键，见 §6.2
  "description": "",             // 评价表说明，仅 HR 可见
  "hireMode": 1,                 // 1=社招 2=校招；实际落哪个场景由会话决定，见 §1.2
  "items": [ /* §4.2 */ ],
  "linkageRelationship": [ /* §4.3 */ ],
  "feedbackQuestion": [ /* §4.4 */ ],
  "ruleConfig": [ /* §4.5 */ ],
  "enableRule": false,
  "calcScoreType": "",           // "" | "total" | "avg" | "weight"
  "fixedDecimal": 1,             // 保留小数位数
  "isPaddedWithZero": false,     // 小数是否补 0
  "feedbackWriteOrder": 0,       // 0=先评价再结果 1=先结果再评价
  "departmentIds": [],           // 适用部门；[] = 全部部门
  "isOptimizedDeptIds": true     // 部门联动开关
}
```

### 4.2 items（模块 + 题目）

```jsonc
[{
  "id": "<UUID>",                // 模块 UUID，可原样复用
  "title": "模块名",
  "description": "",
  "calcScoreType": "total",      // 模块级：avg | total | "" | null（weight 见 §5.2）
  "subjects": [{
    "id": "<UUID>",              // 题目 UUID，可原样复用
    "title": "题目",
    "description": "",
    "type": 2,                   // §5.1
    "scoreType": 5,              // 分值类型 = N 分制满分值；0 = 自定义分数
    "arrangeType": 0,            // 每行列数
    "isRequired": false,
    "needReason": false,
    "isSelfInputScore": false,
    "isFoldDescription": false,
    "relatedQuestion": false,
    "ratio": 60,                 // 仅权重表，见 §5.2
    "options": [                 // type=2/4 必填，且**至少 2 项**
      { "value": "A: 优", "description": "" },
      { "value": "B: 良" }
    ],
    "customScores": [{ "value": 1.0 }]   // type=1
  }]
}]
```

> ⚠️ `options` 的字段是 **`value` / `description`**。没有 `id`、没有 `text`、没有 `score`。

> ⚠️ 模块 `calcScoreType` 读回来可能是 **`null`**。搬运时归一成 `""` 再下发，原样传 `null` 未验证，不要用。
> 表级 `calcScoreType` 为 `null` 时同样归一成 `""`。

### 4.3 linkageRelationship（题目联动）

```jsonc
[{ "id": "<主题目UUID>", "linkages": [{ "value": "<触发选项值>", "idList": ["<被联动题目UUID>"] }] }]
```

- 每个参与联动的题目一条记录；`linkages: []` = 该题无联动。
- `linkages: [{}]`（内含空对象）是 UI 里**没配完的空联动**，不是有效数据；搬运时应剔除。
- `titleList` 是前端按 `idList` 派生的展示字段，不需要下发。

### 4.4 feedbackQuestion（关联面试题库）

写入形状 —— **只有两个键**：

```jsonc
[{ "subjectId": "<题目UUID>", "questions": [{ "id": <面试题ID> }] }]
```

> ⚠️ **没有 `relatedQuestionChecked` 字段。** 本文早期版本写过该字段，实测传入会被**静默丢弃**：
> 同租户 51 张表的全部 `feedbackQuestion` 条目，键组合永远只有 `{subjectId, questions}`。不要下发它。

`questions[].id` 是**租户本地的面试题库 ID**，跨租户必须重映射（见第 7 步）。

> 题库本体的查询与增删改（`interviewQuestion/getInterviewQuestionList` / `save` / `update` / `delete`）属于
> `interview-question-bank` 路由，见 `../interview-question-bank.md`。需要新建题目再绑进模板时分两步走，
> 先在该路由建题并回读拿 id。注意第 7 步引用的 `getAll` 与那边验证过的
> `getInterviewQuestionList` 是**两个不同端点**，`getAll` 的 payload 与响应尚未实测。

#### 4.4.1 关联的载体是 feedbackQuestion，不是 relatedQuestion

题目层的 `relatedQuestion`（§4.2）只是 **UI 勾选标记**，关联数据本体存在 `feedbackQuestion` 数组里。实测
subject **不带** `relatedQuestion` 但 `feedbackQuestion` 里有对应条目时，**关联照样入库**。

这会产出「数据里有关联、UI 开关没打开」的不一致状态。因此：

> **强制**：为某个 subject 关联题库时，**必须同时**写 `subjects[].relatedQuestion: true` 和
> `feedbackQuestion` 里对应的条目。取消关联时两处一起去掉。

`relatedQuestion` 只在为 `true` 时写入；未关联的 subject 读回来该字段是**缺失**，不是 `false`。

#### 4.4.2 🚨 update 对 feedbackQuestion 不是整体覆盖

同一个 `updateFeedbackTemplate` 请求里**两种语义并存**（实测）：

| 字段 | payload 省略该字段时 |
|---|---|
| `items` | **整体覆盖**：实测传入少 2 个 subject 的版本，落库就只剩传入的那些 |
| `feedbackQuestion` | ⚠️ **不覆盖，原关联完整保留** |

后果：删掉一个 subject 而没有同步收拾 `feedbackQuestion`，它的关联条目会**残留成孤儿**（`subjectId`
指向已不存在的题目）。

要真正清空关联，必须**显式传 `feedbackQuestion: []`**（实测有效）。省略它做不到清空。

> **强制**：改动 `items` 里的 subject 时，必须同时显式下发一份与新 `items` 对齐的
> `feedbackQuestion`（哪怕是 `[]`），不能省略该字段。

#### 4.4.3 🚨 两个校验完全缺失

| 构造 | 实测结果 |
|---|---|
| `questions:[{id: <本租户不存在的题目 id>}]` | **静默接受入库**，不报错 |
| `subjectId` 不在 `items` 的任何 subject 里（孤儿条目） | **静默接受入库**，且详情接口还会富化返回题目内容 |

**跨租户搬运时忘记重映射题目 id 不会报任何错**，直接产出悬空引用。校验只能靠调用方自己做：下发前
用 `interview-question-bank` 路由的查询确认每个 `questions[].id` 在目标租户真实存在，且每个
`subjectId` 都能在本次 `items` 里找到。

#### 4.4.4 悬空引用的检测方法

`getFeedbackTemplateByIdPermission` 会把 `questions[]` **富化**成 `{id, title, description, type}`。
因此：

> **详情里某个 question 只有裸 `{"id": <数字>}`、没有 `title`/`description`/`type` → 该题目已从题库删除，
> 这是一条悬空引用。**

示例：某张表引用的题目已被删除，详情里该条可能是裸 `{"id": <deleted-question-id>}`，同表其他题目均带完整内容。

**`templateCount` 不能用来发现这类问题**：它是题库侧的计数，只统计 `subjectId` 在 `items` 中**有效存在**
的关联，孤儿条目不计入（实测一条孤儿条目引用的题目，`templateCount` 未计它）。详见
`../interview-question-bank.md`。

#### 4.4.5 场景差异：评价表分社招/校招，题库不分

| 对象 | 是否区分社招/校招 |
|---|---|
| **面试评价表模板** | ✅ **区分**。每张表带 `hireMode`，列表只返回当前会话场景下的表（§1.2）|
| **面试题库** | ❌ **不区分**，两个场景共用同一组题目 |

所以同一道题库题目可以被社招表和校招表同时引用，不需要按场景准备两份题库；但**评价表本身必须在目标
场景下操作**，仍按 §1.2 探测 `currentHireMode` 并与用户目标核对。

### 4.5 ruleConfig（面试结果规则，仅 enableRule=true）

```jsonc
[{ "feedbackTemplateId": <template-id>, "interviewCustomFeedbackResultsId": <result-id>,
   "ruleId": <rule-id>, "version": "1.0" }]
```

编辑器「填写规则」区按**面试评价选项**逐行展开（社招显示 通过/淘汰/待定，校招显示 满意/不满意/待定），
每行后面一个「配置规则」入口，点开是规则引擎式配置器。

| 字段 | 含义 | 来源 |
|---|---|---|
| `interviewCustomFeedbackResultsId` | 该行的面试评价选项 id | `interview/evaluation/option/list` |
| `ruleId` | 在**本租户**创建的面试结果规则对象 id | `interview/conclusions/rules/*` |

两条实测边界：

- 打开 `enableRule` 开关**只写 `enableRule: true`**，`ruleConfig` 仍为 `[]`；必须真正配置规则才会填充。
- 规则条件树的写 payload（`conclusions/rules/addOrUpdate`）**本 skill 未采集**，见「未覆盖项」。

---

## 第 5 步：枚举与校验

### 5.1 题型（来自前端常量 `FEEDBACK_TEMPLATE_ITEM_TYPE`）

| `type` | 题型 | 必需字段 |
|---|---|---|
| `1` | 评分题 | `customScores`（可选）；`scoreType` 决定满分值 |
| `2` | 单选题 | `options` **≥ 2 项** |
| `3` | 文本题（问答） | — |
| `4` | 多选题 | `options` ≥ 2 项（**本 skill 未实际采集过 type=4 的样本**） |

其他常量：

```
FEEDBACK_TEMPLATE_TYPES         = { STANDARD:"standard", WEIGHT:"weight" }
TEMPLATE_MODULE_CALC_SCORE_TYPE = { AVG:"avg", TOTAL:"total", WEIGHT:"weight" }
CUSTOM_SCORE_DEFAULT_VALUE      = 0     // scoreType=0 → 自定义分数
```

### 5.2 权重评价表

**「普通 / 权重」不是独立字段**。写入 payload 里没有 `templateType`；URL 上的
`?templateType=standard|weight` 只是前端路由参数。持久化判别式是顶层 `calcScoreType`。

| 组合 | 结果 |
|---|---|
| 表 `calcScoreType:"weight"` + 模块 `calcScoreType:""` + 题目 `ratio` 求和 = 100 | ✅ 可用，`ratio` 以浮点持久化 |
| 表 `weight` + **模块 `calcScoreType:"weight"`**（带或不带模块 `ratio`） | ❌ `211015 权重总和不是100` |
| 表 `weight` + 模块 `""` + 模块 `ratio:100` | ✅ 成功（模块 `ratio` 被忽略） |

**模块级权重（模块 `calcScoreType:"weight"`）三组对照均构造失败，求和口径不明** → 未覆盖，停止写入。

### 5.3 🚨 `code` 是业务码，不是 0/1

不要沿用其他接口「`code==0` 即成功」之外的任何假设：**必须检查 `success` 字段**。

| `code` | `msg` | 触发条件 |
|---|---|---|
| `0` | 成功 | — |
| `102` | `items subjects options 最小长度2` | 单选/多选题选项少于 2 个 |
| `211015` | `权重总和不是100` | 权重口径不符（§5.2） |

同时注意区分两层：`cllmk` 外层的 `code` 是 CLI 自身的 0/1；接口业务码在 `data` 里。
**不得把 cllmk 外层 `code == 0` 当作业务成功。**

两层信封的实际形状：

```jsonc
{ "code": 0, "data": {                       // ← 外层 = cllmk CLI 自身
    "code": 0, "codeType": 0,                // ← 内层 = 接口业务码
    "success": true, "msg": "成功",
    "data": <业务载荷>                        // ← 列表数组 / 详情对象 / 创建返回的新 id（数字）
  }, "msg": "" }
```

判定成功要求内层 `code == 0` **且** `success == true`；业务载荷一律取 `data.data`
（`getFeedbackTemplateList` 是数组，`saveFeedbackTemplate` 是新 id 数字）。

---

## 第 6 步：四个操作原语

所有写操作**默认只预览**。真实写入前必须完成 §6.4 的确认清单。

### 6.1 export — 导出

```bash
# 1. 探测场景（字段路径见 §1.2）
cllmk curl --url /api/v2/org/info --method GET --filter data.currentUserInfo.currentHireMode
# 2. 拉全量（已含 items）
cllmk curl --url /api/outer/ats-interview/interview/feedbackTemplates/getFeedbackTemplateList \
  --method POST --payload '{}'
# 3. 仅当需要 ruleConfig 时，对目标表逐个调详情
```

导出产物必须记录：来源 `orgId` / `env` / **`hireMode`** / 导出时间 / 每张表的 `id` 与 `name`。
`items` 等字段先 `fromjson` 再存，避免二次转义。

### 6.2 plan — 比对与幂等判定

**幂等键 = `(name, hireMode)`**。用它把「目标租户已有的表」和「要写入的表」做三分类：

| 分类 | 判定 | 动作 |
|---|---|---|
| 新增 | 目标场景下无同名表 | `saveFeedbackTemplate` |
| 更新 | 目标场景下有同名表 | `updateFeedbackTemplate`（带目标表的 `id`） |
| 冲突 | 同名表存在但结构差异大 | **停止**，向用户展示 diff 让其决策 |

plan 阶段必须向用户输出一张对照表：

| # | 表名 | hireMode | 动作 | 模块数 | 题目数 | 联动 | 权重表 | 需重映射项 |
|---|---|---|---|---|---|---|---|---|

「需重映射项」列出该表引用的所有租户本地 ID（见第 7 步），任何一项无法映射就把该表标为**跳过**。

### 6.3 create / update

```bash
cllmk curl --url /api/outer/ats-interview/interview/feedbackTemplates/saveFeedbackTemplate \
  --method POST --payload '<§4.1 完整 payload>'

cllmk curl --url /api/outer/ats-interview/interview/feedbackTemplates/updateFeedbackTemplate \
  --method POST --payload '<§4.1 完整 payload + "id": <数字>>'
```

> ⚠️ **update 对 `items` 是整体覆盖**。目标表已有的模块、题目，凡本次 payload 未携带的都会丢失。
> 更新现有表前必须先调详情读全量，与新内容合并后整体下发。
> （同 `apply-form` 的 REPLACE 语义，是本仓库反复踩过的坑。）
>
> ⚠️ **但 `feedbackQuestion` 是例外：省略它不会清空，原关联会完整保留**（实测，见 §4.4.2）。
> 所以「整体覆盖」这句话不能一概适用 —— 减少 subject 时必须**同时显式下发**对齐后的
> `feedbackQuestion`，否则会残留孤儿关联条目。要清空关联只能显式传 `[]`。

`saveFeedbackTemplate` 返回新表 id（**数字**），`updateFeedbackTemplate` 返回被更新的 id（数字），
`removeFeedbackTemplate` 返回被删除的 id（**字符串**）。业务载荷一律在 `data.data`（§5.3）。

写入后回读校验：再调一次详情，比对 `name` / 模块数 / 题目数 / `calcScoreType` / `enableRule`，
以及 **`feedbackQuestion` 的条目数与每个 `subjectId` 是否都还能在 `items` 里找到**（§4.4.4）。

### 6.4 写入前确认清单

```
📋 面试评价表写入预检：

【租户】{orgName} ({orgId}) / {env}
【场景】{社招 | 校招}（探测值 currentHireMode={1|2}）
【动作】新增 {a} 张 / 更新 {b} 张 / 跳过 {c} 张
【逐表明细】
  - {表名}：新增，{N} 模块 / {M} 题目 / 联动 {L} 条{权重表标记}
  - {表名}：更新（id={id}），旧 {N1} 题 + 本次 {N2} 题 = 下发 {N3} 题
【重映射】{已映射项} / ⚠️ {无法映射项 → 该表跳过}
【关联题库】下发 {K} 条 feedbackQuestion；题目 id 已在本租户核验存在 {是/否}；
            每条 subjectId 都能在本次 items 中找到 {是/否}
【不做的事】不绑定职位/面试轮次；不创建面试结果规则

请确认。回复「确认」/「执行」继续。
```

用户明确确认后才执行。更新场景必须展示「旧 X + 新 Y = 下发 Z」的合并预览。

**减少 subject 的更新**额外要展示 `feedbackQuestion` 的前后对比，并说明本次会显式下发对齐后的数组
（省略该字段会残留孤儿关联，§4.4.2）。

---

## 第 7 步：跨租户搬运规则

搬运时字段分两类，**不能一视同仁**：

### 可原样搬运

| 字段 | 依据 |
|---|---|
| `items` 全部内容（含模块与题目 **UUID**） | 实测 UI 复制生成的新表与源表 UUID **完全相同**，说明 UUID 由客户端提供、不要求全局唯一 |
| `linkageRelationship` | 只引用 `items` 内部的 UUID，随 `items` 一起搬即可（剔除空联动） |
| `name` / `description` / `calcScoreType` / `fixedDecimal` / `isPaddedWithZero` / `feedbackWriteOrder` | 纯值（`calcScoreType` 为 `null` 时归一成 `""`，见 §4.2） |
| `isOptimizedDeptIds`（**仅当 `departmentIds` 为 `[]`**） | 已验证 `true` / `false` 均可原样搬运；`departmentIds` 非空仍属未覆盖 |
| `customScores`（`type=1` 评分题的自定义分值） | 纯值数组，实测 `scoreType:5` + `[{value:1.0}…{value:5.0}]` 原样搬运成功 |

### 必须重映射（否则停止）

| 字段 | 引用的租户本地对象 | 映射依据 | 查询接口 |
|---|---|---|---|
| `departmentIds` | 部门 | 部门名称 | `ats-warden-search/departments/*` |
| `feedbackQuestion.questions[].id` | 面试题库题目 | 题目内容（`title`） | `interviewQuestion/getInterviewQuestionList`（见 `../interview-question-bank.md`）|
| `ruleConfig.interviewCustomFeedbackResultsId` | 面试评价选项 | 选项名称 | `interview/evaluation/option/list` |
| `ruleConfig.ruleId` | 面试结果规则对象 | **无法映射** | `interview/conclusions/rules/list` |

> 🚨 **题目 id 的重映射没有任何服务端兜底。** 下发一个目标租户不存在的题目 id
> **静默成功入库**，孤儿 `subjectId` 也一样（§4.4.3）。因此搬运前必须逐条按题目 `title` 在目标租户
> 查到真实 id 并替换；任何一道题在目标租户找不到，就按 §6.2 把该表标为**跳过**，或先用
> `interview-question-bank` 路由在目标租户建题（该路由的 `save` 不返回 id，需按 title 回读）。
> 搬运后必须按 §4.4.4 回读检查有没有裸 `{"id":...}`。
>
> 题库本身**不分社招/校招**（§4.4.5），所以题目映射表在两个场景间可以复用；但评价表要分场景处理。

`ruleId` 指向租户本地的规则引擎对象，且本 skill 未覆盖规则创建 → **凡源表 `enableRule:true` 且带
`ruleConfig` 的，一律降级处理**：

```
⚠️ 表「{表名}」启用了面试结果规则（{N} 条）。规则对象无法跨租户搬运，
本次将以 enableRule=false / ruleConfig=[] 创建，其余结构完整保留。
创建后请到「设置 → 面试管理 → 面试评价表」手工配置填写规则。
是否按此方式继续？
```

用户确认后才继续，并在结果报告里逐条列出被丢弃的规则。

---

## 未覆盖项与停止规则

遇到以下情况**停止写入**，说明缺什么，不要猜 payload：

1. **模块级权重**（模块 `calcScoreType:"weight"`）—— 求和口径不明（§5.2）。
2. **面试结果规则的创建/修改** —— `conclusions/rules/addOrUpdate` 的规则条件树 payload 未采集。
   需要用户提供一份 UI 上「配置规则 → 确认」的 curl 反推。
3. **`type=4` 多选题** —— 常量已确认存在，但未采集过真实样本。
4. **职位/面试轮次绑定** —— 见第 0 步。
5. **社招/校招切换** —— 只探测不切换（§1.2）。
6. **限定部门的表** —— 仅指 `departmentIds` **非空**时，它与 `isOptimizedDeptIds` 的配合语义未采集。
   `departmentIds: []`（全部部门）已验证可搬：`isOptimizedDeptIds` 可为 `true` 或 `false`，
   两个值都原样搬运成功，无需重映射，不必因该字段停止。
7. **`scoreType` 合法值全集** —— 语义已确认（N 分制满分值），全集未取到；只使用源表已有的值。

---

## 失败处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `code:102` `options 最小长度2` | 单选/多选题选项不足 2 个 | 补齐选项或改题型 |
| `code:211015` `权重总和不是100` | 权重口径不符 | 按 §5.2 检查；模块级权重直接停止 |
| 列表返回的表数量与预期不符 | 会话处在另一个场景 | 按 §1.2 探测 `currentHireMode`，不要误报成配置缺失 |
| `HTTP 401` | 会话可能失效 | 裸 `cllmk auth status` 确认；确实过期按 `foundation/auth.md` 重新登录 |
| `HTTP 403` | 权限不足（列表有 `FEEDBACK_SETTINGS` 权限版本） | 报告权限问题，不改凭证 |
| update 后题目变少 | `items` 是整体覆盖 | 按 §6.3 先读全量再合并下发；已丢失的需从导出产物恢复 |
| 删了 subject 后仍有 `feedbackQuestion` 条目指向它 | 省略 `feedbackQuestion` 不会清空（§4.4.2） | 显式下发对齐后的数组；要清空传 `[]` |
| UI 上看不到已关联的题库 | 只写了 `feedbackQuestion`，`subjects[].relatedQuestion` 没置 `true`（§4.4.1） | 两处同写后重新下发 |
| 详情里某题只有裸 `{"id":...}` | 该题目已从题库删除，引用悬空（§4.4.4） | 在 `interview-question-bank` 路由确认题目是否存在；重建题目并重映射，或从该 subject 的关联中移除 |

## 入口 URL

| env | URL |
|---|---|
| cn | https://app.mokahr.com/settings/interview_feedback_form |
| intl | https://hire-r1.mokahr.com/settings/interview_feedback_form |
| s3 | https://staging-3.mokahr.com/settings/interview_feedback_form |

## 契约来源

本文档的接口与结构来自页面请求、接口响应和前端常量的交叉验证，枚举不是凭空推测。以下三处以验证结果为准：
`options` 字段名（`value`/`description`，非 `id`/`text`/`score`）、题型共 4 种（含多选题）、
`type:1` 是可配分值类型的评分题（非固定 1–5 星）。

补充验证（跨租户搬运示例并回读校验通过）修正/新增了以下五处：
hireMode 字段路径是 `data.currentUserInfo.currentHireMode`（§1.2）、
模块 `calcScoreType` 可为 `null`（§4.2）、`ruleConfig` 在 `enableRule:false` 时同样缺失（§3）、
两层响应信封形状与业务载荷位置 `data.data`（§5.3）、
`departmentIds: []` 时 `isOptimizedDeptIds` 两个值均可原样搬运（§7、未覆盖项 #6）。

补充验证（围绕**关联面试题库**做的边界验证，验证后清理测试数据）修正/新增以下六处：

1. **删除了 `relatedQuestionChecked`**（§4.4）—— 该字段不存在，传入被静默丢弃。这是本文此前的错误。
2. **`update` 对 `feedbackQuestion` 不是整体覆盖**（§4.4.2、§6.3）—— 省略即保留原值，与同一 payload
   里 `items` 的覆盖语义相反；清空只能显式传 `[]`。此前 §6.3 的「凡未携带的都会丢失」是过度概括。
3. **关联的载体是 `feedbackQuestion` 而非 `relatedQuestion`**（§4.4.1）—— subject 不带
   `relatedQuestion` 时关联照样入库，会产出 UI 与数据不一致，必须两处同写。
4. **题目 id 与 `subjectId` 均无服务端校验**（§4.4.3、§7）—— 不存在的题目 id、孤儿 `subjectId`
   都静默入库，跨租户搬运漏映射不会报错。
5. **`feedbackQuestion` 的 list 与 detail 形态不同**（§3）—— detail 会富化 `questions[]`，
   由此得到悬空引用的检测方法（§4.4.4）；`templateCount` 不计孤儿条目，不能用于该检测。
6. **场景差异**（§1.2 规则 4、§4.4.5）—— 评价表区分社招/校招，面试题库两场景通用。
