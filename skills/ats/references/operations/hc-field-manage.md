---
route: hc-field-manage
---

# 招聘需求自定义字段管理（ATS-JC HC 接口）

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

本路由通过自然语言在 Moka ATS 中**创建**或**更新**招聘需求（Headcount/HC）自定义字段，使用 `cllmk curl` 调用 `/api/outer/ats-jc/headcount/hc_custom_fields/create` 与 `/update` 接口。

## 目录

- 前置鉴权与环境确认
- 创建/更新路由判定
- 文件选项与 ID 处理
- 创建流程：参数、类型、payload、调用与响应
- 更新流程：定位、类型校验、optionId 合并、payload 与响应
- 安全约束与交互示例

> **与其他字段 skill 的区别**：
> - `cllmk` 的 `job-field-manage` 路由处理**职位**自定义字段（`/job/jobCustomFields/create`），结构含 14 语种 locale 和 cascade 类型
> - 本路由处理**招聘需求（HC）**字段，结构更简单：`supplementaryLocales: null`、`multiDetail` 仅 zh-CN、无 cascade 类型、含 number_info 和 person_select_info
> - 两个 skill 对应的是前端不同页面的不同接口，**不可替代**

---

## 第 1 步：前置鉴权检查

**必须**先按 `<skill-dir>/SKILL.md` 的「业务公共前置」执行：

1. **Step 0** — 确认 `cllmk` 已安装（`command -v cllmk`）；未安装则展示安装指引，**终止流程**
2. **Step 1** — 执行 `cllmk auth status`
3. **Step 2/3** — 解析输出并分支处理：

| 输出 | 处理 |
|------|------|
| `code:0` 且 `data.system === "ats"` | 继续第 2 步 |
| `code:0` 且 `data.system === "people"` | 提示当前登录 People 系统，询问是否切换到 ATS，确认后执行 `cllmk ats <env> auth login` |
| `code:1, msg: "Not logged in"` | 确认目标 env 后执行 `cllmk ats <env> auth login`，完成后回到 Step 1 |
| `code:1, msg: "Session expired. Credentials preserved..."` | 同上；**凭证未被清除**，重新 login 会覆盖过期会话，不要跑 logout 去「清理」 |
| `code:1, msg: "Request failed..."` | 按 `references/foundation/auth.md` 的「受限执行环境的网络重试」处理；不得触发登录 |

login 由 Agent 按 `references/foundation/auth.md` 的「登录流程」在受工具管理的长运行会话中执行（禁止 `&` / `nohup` 自行后台化），用户只在弹出的 Chrome 里完成认证；只有该文档列出的四种回退情况才把命令交还用户在自己的终端运行。

---

## 第 2 步：确认 auth status 和环境

在收集参数之前，**先向用户展示当前登录状态**（来自 `cllmk auth status` 的 `data`，仅包含 system / env / orgId / orgName，不展示 email），并询问是否在此环境下执行操作，确认后继续。

---

## 第 3 步：判断操作类型（创建 or 更新）

根据用户输入判断操作分支：

| 触发关键词 | 操作 |
|----------|------|
| 创建 / 新增 / 新建 / 加 / 添加一个字段 | **创建** → 第 4 步 |
| 更新 / 修改 / 改名 / 改为 / 变更 / 停用 / 启用 / 禁用 / 启停 | **更新** → 第 5 步 |

若用户意图模糊，主动询问："是要新建字段还是修改已有字段？"

---

## 第 3.5 步：文件输入处理（选项来源于 xlsx / csv / txt 等文件，**创建与更新通用**）

当用户通过文件提供选项列表时（无论创建还是更新），**在构造 payload 前**按以下流程处理；不得直接只取名称列就跳过 ID 检测。

### A. 检测选项 ID 列

读取文件首行作为表头，扫描所有列名（**trim + 大小写不敏感**），凡命中以下任一关键词的列**视为候选 ID 列**：

- `id` / `ID` / `optionId` / `OptionID` / `option_id`
- `referenceId` / `ReferenceID` / `reference_id` / `ref_id`
- `code` / `Code` / `external_code` / `externalCode` / `externalId`
- 任意以 `id` / `Id` / `ID` / `code` / `Code` 结尾的列名

### B. 处理规则

| 情况 | 处理 |
|------|------|
| 文件**仅含名称列**（无候选 ID 列） | 按 §4.3 / §5.4 默认逻辑：创建时不带 `optionId`；更新时走「名称严格相等」的自动合并 |
| 文件**同时含名称列和 1 个候选 ID 列** | 向用户展示检测到的列映射（如：「A=名称、B=ID」），**确认后**将该列值作为 `optionId` 写入 payload |
| 检测到**多个候选 ID 列** | 列出所有候选列，让用户明确指定哪一列作为 `optionId` |
| 列含义不明 / 只有未命名列 | 列出全部列及前几行示例，让用户指定哪一列是名称、哪一列是 ID |

### C. 校验

- **名称列**：去除空行；若存在重复名称需向用户提示并询问处理方式
- **ID 列**：去除空行；ID 在文件内必须唯一；与名称行数一致；否则向用户报告并终止

### D. 与 §5.4 自动合并的冲突解决

当文件携带 ID 且操作为**更新**时，**文件 ID 优先级 > 服务端已有 optionId**：
- skill 不再按 §5.4 的名称严格相等做 optionId 复用
- 直接使用文件 ID 作为 `optionId`
- 在 §5.6 payload 预览中**必须明确告知**用户：

> ⚠️ 本次更新将使用文件中的 ID 列作为 `optionId`，服务端现有的 `optionId` 将被替换（旧 optionId 作废）。若已存在使用旧 optionId 的历史数据，关联可能丢失，请确认。

### E. 选项删除提醒不变

无论使用文件 ID 还是默认自动合并，§5.4 的「选项删除提醒」逻辑仍生效：以**名称**为准，若 targetField 中某旧选项名未出现在文件中，仍需列出并获用户确认。

---

## 第 4 步（创建流程）

### 4.1 收集参数

从用户输入中提取以下参数，缺失的**必填**参数用 AskUserQuestion 逐项询问，不得擅自假设：

| 参数 | 说明 | 必填 | 默认 |
|------|------|------|------|
| `name` | 字段名称 | ✅ | — |
| `type` | 字段类型（见类型表） | ✅ | — |
| `isRequired` | 是否必填 | ✅ | `false` |
| `isApproval` | 是否必审 | 可选 | `false`（用户未明示时直接使用默认值，不再追问）|
| 单选选项 | `select_info` 的选项值 | 条件必填 | — |
| 多选选项 | `multi_select_info` 的选项值 | 条件必填 | — |
| 数字规则 | `number_info` 的小数位数/范围 | 可选 | 不传 |

**固定值：`supplementaryLocales: null`**（所有类型）

> **若选项来源于文件**：先按 §3.5 检测 ID 列。若存在，在 `multiDetail[].optionId` 或对应位置带上文件 ID（创建时也可携带预定义 optionId）。

### 4.2 字段类型映射表

| 用户描述 | `type` 值 | 备注 |
|----------|-----------|------|
| 单行文本 / 文本 / 字符串 | `string_info` | |
| 长文本 / 多行文本 / 富文本 | `text_info` | |
| 单选 / 下拉 | `select_info` | 需 `detail` 选项数组 |
| 多选 | `multi_select_info` | 需 `multiDetail` 选项列表 |
| 是否 / 布尔 / 开关 | `bool_info` | |
| 日期（年月日）/ 日期 | `day_info` | |
| 日期（年月）/ 年月 | `date_info` | |
| 数字 | `number_info` | 可选 `fieldRule` |
| 附件 | `attachment_info` | |
| 人员单选 | `person_select_info` | |

### 4.3 构造请求 Body

#### 组 A — 简单类型（string_info / text_info / bool_info / day_info / date_info / attachment_info / person_select_info）

```json
{
  "type": "<type>",
  "name": "<name>",
  "isRequired": false,
  "isApproval": false,
  "supplementaryLocales": null
}
```

#### 组 B — 单选（select_info）

```json
{
  "type": "select_info",
  "name": "<name>",
  "isRequired": false,
  "isApproval": false,
  "supplementaryLocales": null,
  "detail": ["选项1", "选项2", "选项3"]
}
```

#### 组 C — 多选（multi_select_info）

```json
{
  "type": "multi_select_info",
  "name": "<name>",
  "isRequired": true,
  "isApproval": true,
  "supplementaryLocales": null,
  "multiDetail": [
    { "localeValues": [{ "locale": "zh-CN", "value": "选项1" }] },
    { "localeValues": [{ "locale": "zh-CN", "value": "选项2" }] },
    { "localeValues": [{ "locale": "zh-CN", "value": "选项3" }] }
  ]
}
```

> 注意：`multiDetail` 只含 `zh-CN` 一个 locale，不展开14语言（与 `job-field-manage` 路由的处理方式不同）。

#### 组 D — 数字（number_info）

**无 fieldRule 时：**
```json
{
  "type": "number_info",
  "name": "<name>",
  "isRequired": false,
  "isApproval": false,
  "supplementaryLocales": null
}
```

**有 fieldRule 时（小数位数 decimalLength、范围 numberRange.min/max 按需设置，值为字符串）：**
```json
{
  "type": "number_info",
  "name": "<name>",
  "isRequired": false,
  "isApproval": false,
  "supplementaryLocales": null,
  "fieldRule": {
    "decimalLength": "2",
    "numberRange": { "min": "0", "max": "100" }
  }
}
```

### 4.4 展示 payload 并等待确认

在执行前，必须将完整请求展示给用户：

```
即将执行以下请求（创建）：

POST /api/outer/ats-jc/headcount/hc_custom_fields/create
（当前会话：<system> / <env> / <orgName>）

{
  <完整 JSON body，格式化缩进>
}

确认执行？
```

用户说"确认""可以""执行""ok""是"等明确指令后才继续。其他回复视为未确认。

### 4.5 执行 cllmk curl

```bash
cllmk curl \
  --url "/api/outer/ats-jc/headcount/hc_custom_fields/create" \
  --method POST \
  --payload '<完整 JSON 字符串>'
```

### 4.6 处理结果

| cllmk 输出 | 处理方式 |
|-----------|---------|
| `code:0` | 告知创建成功，展示响应中的关键字段（如返回的字段 ID） |
| `code:1, msg: "HTTP 401"` / `"HTTP 403"` | 执行 `cllmk auth status` 重新验证；若 session 失效则引导重新登录 |
| `code:1, msg: "HTTP 4xx"` | 展示错误详情，提示检查参数（字段名重复、类型非法等） |
| `code:1, msg: "HTTP 5xx"` | 提示服务端错误，建议稍后重试 |
| `code:1, msg: "Not logged in"` | 引导重新登录 |

---

## 第 5 步（更新流程）

### 5.0 收集更新参数

**定位参数（至少一项）**：

| 参数 | 说明 |
|------|------|
| `id` | 字段 ID（若提供，按 id 精确匹配） |
| `name` | 字段名称（若只给 name，按 trim + 大小写不敏感匹配） |

**更新参数（至少一项变更）**：

| 参数 | 说明 |
|------|------|
| `name` | 新字段名称（同时作为定位键与改名值时，用户需明确表达改名意图） |
| `isRequired` | 是否必填（输入 true/false/是/否） |
| `isApproval` | 是否必审（输入 true/false/是/否） |
| `isVisible` | 启用(true) / 停用(false) |
| `detail` | 单选新选项数组 |
| `multiDetail` | 多选新选项列表（**无需用户手抄 optionId**，skill 自动合并） |

若 id 和 name **都未提供**，必须询问："请提供要更新的字段 ID 或字段名称"。

### 5.1 字段定位（GET /api/v2/org/info）

**无论用户是否提供 id，都必须先调用以下请求**（既为校验字段存在，也为后续多选 optionId 自动复用取素材）：

```bash
cllmk curl \
  --url "/api/v2/org/info" \
  --method GET --filter hcFields
```

若命令返回 `code:1` 且消息明确指向 filter 路径错误，按 `references/foundation/auth.md`
的 filter 失败规则检查最小父路径；不得直接判定该租户没有 HC 字段配置。

从响应 `data.hcFields[]` 中按以下规则定位 **targetField**：

#### A. 用户提供 id
按 id 精确匹配 `hcFields[]`：
- **找不到** → 终止，告知"未找到 ID 为 `<id>` 的 HC 字段"
- **找到** → `targetField = 该字段`

#### B. 用户只给 name
按名称模糊匹配（**trim + 大小写不敏感**）：
```
field.name.trim().toLowerCase() === userInput.trim().toLowerCase()
```

| 命中数 | 处理 |
|--------|------|
| **0 命中** | 列出所有 hcFields 的 `name / id / hireMode` 让用户选；若列表超过 20 条，先列出包含用户输入子串的条目 |
| **1 命中** | `targetField = 该字段`，进入下一步 |
| **N 命中** | 列出候选的 `name / id / type / hireMode`，让用户明确选一个再继续 |

### 5.2 字段类型一致性校验

根据用户操作意图推断预期类型，与 `targetField.type` 比对：

| 用户意图关键词 | 预期 type |
|--------------|-----------|
| "加选项" / "改选项" / "删选项" / 涉及 detail / 涉及 multiDetail | `select_info` 或 `multi_select_info` |
| "启用" / "停用" / "改名" / "改必填" / "改必审" | 任意类型 |
| 显式要求改 type（如"把这个字段从单选改成多选"） | **直接拒绝** |

**不匹配处理**：告知用户并终止流程，不发起请求：

> 目标字段类型是 `<targetField.type>`，与操作意图（`<action>`）不一致。字段类型创建后不可更改，请先停用当前字段（将 `isVisible` 设为 false），然后新建一个正确类型的字段。

**显式要求改类型**（原 5.2 规则）合并进本节，使用同一份文案告知用户后终止。

### 5.3 布尔值格式转换

用户输入的 true/false/是/否/启用/停用等自然语言在构造 payload 时按以下规则转换：

- `isRequired`、`isApproval` → **整数 0/1**（创建时是 boolean，但更新时接口要整数）
- `isVisible` → **布尔 true/false**（保持 boolean 形式）

| 用户输入 | isRequired/isApproval | isVisible |
|---------|----------------------|-----------|
| true / 是 / 必填 / 必审 / 启用 | `1` | `true` |
| false / 否 / 不必填 / 不必审 / 停用 | `0` | `false` |

### 5.4 多选 optionId 自动复用 + 选项删除提醒

更新 `multi_select_info` 字段时，skill **自动**基于 `targetField.multiDetail` 合并 optionId。

> **若选项来源于文件**：先按 §3.5 检测 ID 列。**若文件已携带 ID 列，则跳过下文的自动合并**，直接使用文件 ID 作为 `optionId`，并按 §3.5.D 向用户告知"旧 optionId 将被替换"。仅当文件**无 ID 列**时，才走下方"严格相等自动复用"逻辑。

#### 复用规则（选项名严格相等）

对用户新提供的每个选项值 `v_new`：

```
if v_new === targetField.multiDetail[i].localeValues[locale=zh-CN].value
  （严格相等：case-sensitive，无 trim）
→ 新选项带上已有 optionId（复用）
否则
→ 新选项不带 optionId（服务端视为新增）
```

> 选项名匹配采用**严格相等**（与 §5.1 字段名的 trim+不区分大小写**不同**）。因为选项常为大小写敏感缩写（如 EN/HK/JP），宽松匹配可能误判。

**multiDetail 构造示例**（targetField 含 A(optionId:…969)、B(…970)、C(…971)；用户新列表 A/B/D）：

```json
"multiDetail": [
  { "localeValues": [{ "locale": "zh-CN", "value": "A" }], "optionId": "<option-id-a>" },
  { "localeValues": [{ "locale": "zh-CN", "value": "B" }], "optionId": "<option-id-b>" },
  { "localeValues": [{ "locale": "zh-CN", "value": "D" }] }
]
```

#### 选项删除提醒

若 targetField.multiDetail 中某旧选项在用户新列表中未出现（视为删除），skill **必须**列出将被删除的选项名并提示：

> ⚠️ 以下选项将被删除：[C]。历史数据中引用这些选项的记录可能失去关联，确认继续？

获得用户明确确认后才继续。

### 5.5 构造最小化 payload

更新 payload **只包含** `targetField.id` 和用户实际要变更的字段，**不传未变更字段**。

**示例 A — 仅停用字段：**
```json
{ "id": <field-id>, "isVisible": false }
```

**示例 B — 更新单选选项 + 名称 + isRequired：**
```json
{
  "id": <field-id>,
  "name": "Job Group",
  "isRequired": 0,
  "isApproval": 0,
  "supplementaryLocales": null,
  "detail": ["Finance", "Marketing", "Sales"],
  "fieldAttribute": null
}
```

**示例 C — 更新多选选项（optionId 自动合并）：**
```json
{
  "id": <field-id>,
  "name": "Job Family",
  "isRequired": 1,
  "isApproval": 0,
  "multiDetail": [
    { "localeValues": [{ "locale": "zh-CN", "value": "A" }], "optionId": "<option-id-a>" },
    { "localeValues": [{ "locale": "zh-CN", "value": "B" }], "optionId": "<option-id-b>" },
    { "localeValues": [{ "locale": "zh-CN", "value": "D" }] }
  ]
}
```

> 用户通过 name 定位字段时，payload 中 `id` 取自 `targetField.id`；是否包含 `name` 取决于用户是否要求改名。

### 5.6 展示 payload 并等待确认

```
即将执行以下请求（更新）：

POST /api/outer/ats-jc/headcount/hc_custom_fields/update
（当前会话：<system> / <env> / <orgName>）
（目标字段：<targetField.name> / ID <targetField.id> / 类型 <targetField.type>）

{
  <完整 JSON body>
}

确认执行？
```

用户明确确认后才继续。

### 5.7 执行 cllmk curl

```bash
cllmk curl \
  --url "/api/outer/ats-jc/headcount/hc_custom_fields/update" \
  --method POST \
  --payload '<完整 JSON 字符串>'
```

### 5.8 处理结果

| cllmk 输出 | 处理方式 |
|-----------|---------|
| `code:0` | 告知更新成功，展示响应关键信息 |
| `code:1, msg: "HTTP 401"` / `"HTTP 403"` | 执行 `cllmk auth status` 重新验证；session 失效则引导重新登录 |
| `code:1, msg: "HTTP 4xx"` | 展示错误详情，提示检查字段 ID 或参数 |
| `code:1, msg: "HTTP 5xx"` | 提示服务端错误，建议稍后重试 |
| `code:1, msg: "Not logged in"` | 引导重新登录 |

---

## 安全约束

- **禁止**展示或记录 Cookie 明文（`moka-jwt` 等 token 值）
- **禁止**静默执行，每次调用前必须展示完整 payload 并获得用户显式确认
- `isApproval` 用户未提供时默认 `false`（不必审）；若用户有必审需求请明示
- **禁止**更新时擅自变更字段类型，必须按 §5.2 流程告知用户并终止
- **禁止**跳过 §5.1 字段定位或 §5.2 类型校验直接构造 payload——每次更新都必须先调用 `GET /api/v2/org/info` 并完成 targetField 定位与类型校验
- **禁止**在 §5.4 选项删除提醒未获确认时提交 payload

---

## 交互示例

### 示例 1 — 创建单选字段

> 用户：帮我创建一个招聘需求单选字段"Job Group"，选项 Finance / Marketing，不必填，不必审

1. 鉴权通过，展示当前会话并确认
2. 参数：`name=Job Group, type=select_info, isRequired=false, isApproval=false, detail=["Finance","Marketing"]`
3. body：
   ```json
   {"type":"select_info","name":"Job Group","isRequired":false,"isApproval":false,"supplementaryLocales":null,"detail":["Finance","Marketing"]}
   ```
4. 展示 payload → 确认 → 执行 `cllmk curl ... /hc_custom_fields/create`

---

### 示例 2 — 创建多选字段

> 用户：创建招聘需求字段"Job Family"，多选，选项 A/B/C，必填必审

1. 鉴权通过
2. 参数：`name=Job Family, type=multi_select_info, isRequired=true, isApproval=true`
3. body：
   ```json
   {"type":"multi_select_info","name":"Job Family","isRequired":true,"isApproval":true,"supplementaryLocales":null,"multiDetail":[{"localeValues":[{"locale":"zh-CN","value":"A"}]},{"localeValues":[{"locale":"zh-CN","value":"B"}]},{"localeValues":[{"locale":"zh-CN","value":"C"}]}]}
   ```
4. 展示 → 确认 → 执行

---

### 示例 3 — 创建数字字段（有 fieldRule）

> 用户：创建招聘需求字段"Q1招聘人数"，数字类型，2位小数，范围 0-100，不必填

1. 参数：`name=Q1招聘人数, type=number_info, isRequired=false, isApproval=false, fieldRule={decimalLength:"2", numberRange:{min:"0", max:"100"}}`
2. body：
   ```json
   {"type":"number_info","name":"Q1招聘人数","isRequired":false,"isApproval":false,"supplementaryLocales":null,"fieldRule":{"decimalLength":"2","numberRange":{"min":"0","max":"100"}}}
   ```

---

### 示例 4 — 创建数字字段（无 fieldRule）

> 用户：创建招聘需求字段"Q1招聘人数"，数字类型，不必填

1. 参数：`name=Q1招聘人数, type=number_info, isRequired=false, isApproval=false`（fieldRule 不设置）
2. body（不含 fieldRule 字段）：
   ```json
   {"type":"number_info","name":"Q1招聘人数","isRequired":false,"isApproval":false,"supplementaryLocales":null}
   ```

---

### 示例 5 — 创建人员单选字段

> 用户：创建招聘需求字段"替补人员"，人员单选，不必填

1. 参数：`name=替补人员, type=person_select_info, isRequired=false, isApproval=false`
2. body：
   ```json
   {"type":"person_select_info","name":"替补人员","isRequired":false,"isApproval":false,"supplementaryLocales":null}
   ```

---

### 示例 6 — 更新单选选项（提供 ID）

> 用户：把 ID 为 `<field-id>` 的字段增加选项 Sales，改为非必填非必审

1. 鉴权通过
2. 参数：`id=<field-id>, isRequired=0, isApproval=0, detail=["Finance","Marketing","Sales"]`
3. **字段定位（§5.1）**：调用 `cllmk curl --url "/api/v2/org/info" --method GET --filter hcFields`，在 `data.hcFields[]` 中按 id 找到目标 `select_info` 字段
4. **类型校验（§5.2）**：用户意图"加选项"，预期 `select_info | multi_select_info`，实际 `select_info` → 通过
5. body：
   ```json
   {"id":<field-id>,"name":"<field-name>","isRequired":0,"isApproval":0,"supplementaryLocales":null,"detail":["Finance","Marketing","Sales"],"fieldAttribute":null}
   ```
6. 展示 → 确认 → 执行 `cllmk curl ... /hc_custom_fields/update`

---

### 示例 7 — 更新多选字段（optionId 自动合并）

> 用户：更新 ID `<field-id>` 的字段，选项改为 A/B/D，必填非必审

1. **字段定位（§5.1）**：调用 org/info，按 id 找到目标 `multi_select_info` 字段及其 `multiDetail`
2. **类型校验**：意图"改选项"，预期 select/multi_select，实际 `multi_select_info` → 通过
3. **optionId 合并（§5.4）**：
   - A 严格相等目标字段中的 A → 复用对应的 `optionId`
   - B 严格相等目标字段中的 B → 复用对应的 `optionId`
   - D 未找到 → 不带 optionId
4. **选项删除提醒**：targetField 中 C 未出现在新列表 → 提示：
   > ⚠️ 以下选项将被删除：[C]。历史数据中引用这些选项的记录可能失去关联，确认继续？
5. 用户确认后 body：
   ```json
   {"id":<field-id>,"isRequired":1,"isApproval":0,"multiDetail":[{"localeValues":[{"locale":"zh-CN","value":"A"}],"optionId":"<option-id-a>"},{"localeValues":[{"locale":"zh-CN","value":"B"}],"optionId":"<option-id-b>"},{"localeValues":[{"locale":"zh-CN","value":"D"}]}]}
   ```
6. 展示 → 确认 → 执行

---

### 示例 8 — 只给字段名（按名称查找 + optionId 自动复用）

> 用户：把 Job Family 字段的选项改成 A/B/D

1. 鉴权通过
2. 参数：`name=Job Family, multiDetail=[A, B, D]`；用户未提供 id
3. **字段定位（§5.1）**：调用 org/info，按规范化后的字段名在 hcFields[] 中恰好命中 1 条，并读取该字段的 `multiDetail`
4. **类型校验**：通过
5. **optionId 合并**：A/B 复用已有 optionId，D 新增
6. **选项删除提醒**：C 将被删除 → 用户确认
7. body（同示例 7）
8. 展示 → 确认 → 执行

---

### 示例 9 — 字段名匹配多个候选

> 用户：更新 Language 字段，必填

1. 参数：`name=Language, isRequired=1`
2. **字段定位**：org/info 返回两条命中：
   ```
   候选：
   1. name=Language, id=<field-id-1>, type=multi_select_info, hireMode=1（社招）
   2. name=Language, id=<field-id-2>, type=multi_select_info, hireMode=2（校招）
   ```
3. skill 请用户明确选一个：「找到 2 个同名字段，请确认要更新哪一个（1 或 2）？」
4. 用户答"1" → `targetField = 候选 1`，继续类型校验与构造 payload

---

### 示例 10 — 字段类型校验失败

> 用户：给字段"是否接受出差"新增选项 Yes/No

1. 参数：`name=是否接受出差, 意图=加选项`
2. **字段定位**：org/info 单一命中一个 `type="bool_info"` 的目标字段
3. **类型校验（§5.2）**：意图"加选项"预期 select/multi_select，实际 `bool_info` → **不匹配**
4. skill 告知：
   > 目标字段类型是 `bool_info`，与操作意图（加选项）不一致。字段类型创建后不可更改，请先停用当前字段（将 `isVisible` 设为 false），然后新建一个正确类型的字段。
5. 终止流程，不发起请求

---

### 示例 11 — 仅停用字段

> 用户：停用 ID 为 `<field-id>` 的字段

1. 参数：`id=<field-id>, isVisible=false`
2. **字段定位**：org/info 按 id 找到 targetField
3. **类型校验**：意图"停用"对任意类型都 OK → 通过
4. body：
   ```json
   {"id":<field-id>,"isVisible":false}
   ```
5. 展示 → 确认 → 执行

---

### 示例 12 — 用户尝试变更字段类型（应阻止）

> 用户：把 ID `<field-id>` 的字段从单选改为多选

1. **类型校验（§5.2）**：用户显式要求改 type → 直接拒绝
2. skill 告知（与 §5.2 统一文案）：
   > 目标字段类型是 `select_info`，与操作意图（改类型为 multi_select_info）不一致。字段类型创建后不可更改，请先停用当前字段（将 `isVisible` 设为 false），然后新建一个正确类型的字段。
3. 终止流程，不发起请求

---

### 示例 13 — 字段 ID 不存在

> 用户：更新 ID 为 999999 的字段，改名为 Foo

1. **字段定位**：org/info 中 hcFields[] 无此 id
2. skill 告知："未找到 ID 为 999999 的 HC 字段"并终止流程

---

### 示例 14 — 从文件读取选项（文件含 ID 列）

> 用户：更新招聘需求多选字段 Job Family，选项见 `Job Family.xlsx`，A 列是选项名称，B 列是选项 ID

1. 鉴权通过，操作类型=更新，字段名=Job Family
2. **§3.5 文件检测**：读取 xlsx 表头 `('JobFamilyName', 'optionID')`，B 列 `optionID` 命中候选 ID 列
3. 向用户展示：「检测到 A=名称（`JobFamilyName`）、B=ID（`optionID`），共 N 行，名称/ID 均唯一」
4. **§5.1 字段定位** + **§5.2 类型校验** → targetField = multi_select_info
5. **§3.5.D**：因文件携带 ID 列，**跳过 §5.4 名称严格相等自动合并**，使用文件 ID 作为 optionId
6. payload 预览：
   ```json
   {
     "id": <field-id>,
     "multiDetail": [
       { "localeValues": [{ "locale": "zh-CN", "value": "Business Development" }], "optionId": "JF_610001" },
       ...
     ]
   }
   ```
   并附带告警：「⚠️ 本次更新将使用文件 ID 列作为 optionId，服务端现有 optionId 将被替换」
7. 用户确认 → 执行

---

### 示例 15 — 从文件读取选项（文件无 ID 列）

> 用户：更新 Language 字段，选项见 `languages.csv`（单列：语言名）

1. **§3.5 文件检测**：表头仅 `language`，无 ID 列
2. 走 §5.4 默认逻辑：按名称严格相等自动复用 targetField 中已有 optionId，未匹配的视为新增
3. 选项删除提醒（§5.4）正常执行
4. payload 预览 → 用户确认 → 执行

---

### 示例 16 — 未登录场景

> 用户：帮我更新招聘需求字段

1. `cllmk auth status` 返回 `code:1, msg: "Not logged in"`
2. 询问目标 env（如 intl / cn / s3）
3. 在受工具管理的长运行会话中执行 `cllmk ats intl auth login`，并立即告知用户去弹出的 Chrome 里完成登录
4. 命令返回后跑裸 `cllmk auth status` 确认 `code:0` 且 `orgName` 是目标公司，回到 Step 1 重新检查
