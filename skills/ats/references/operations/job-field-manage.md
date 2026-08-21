---
route: job-field-manage
---

# 职位自定义字段管理（ATS-JC 接口）

本路由 通过自然语言在 Moka ATS 中**创建**或**查询**职位自定义字段，使用 `cllmk curl`：
- **创建**：`POST /api/outer/ats-jc/job/jobCustomFields/create`
- **查询**：`GET /api/v2/org/info`，从 `data.jobFields` 数组中筛选

## 目录

- 查询/创建路由判定
- 查询字段：鉴权、接口、筛选与选项明细
- 创建字段：鉴权、参数与类型映射
- 各字段类型 payload
- 确认、执行与响应处理
- 安全约束与交互示例

> 当前只覆盖查询和创建。修改、停用或删除职位字段的真实接口尚未确认，遇到这些意图时停止写入并说明当前不覆盖，不得猜测 endpoint 或 payload。

---

## 路由判定（首先做这一步）

根据用户意图决定走哪个流程：

| 用户意图 | 关键词示例 | 走哪个流程 |
|----------|-----------|------------|
| 查询/查看/列出现有字段 | "有哪些"、"列出"、"查一下"、"查看"、"看看" | → 跳到「查询职位自定义字段」 |
| 新增/创建字段 | "创建"、"新增"、"加一个"、"添加" | → 跳到「创建职位自定义字段」（第 1 步起）|
| 同时包含两者 | "查一下有没有 X，没有的话创建" | 先查询，再根据结果询问是否创建 |
| 修改/停用/删除字段 | "修改"、"改名"、"停用"、"删除字段" | 当前不覆盖；停止写入 |

---

## 查询职位自定义字段

### Q1. 鉴权检查

与创建流程一致：先执行 `cllmk auth status`，确认 `data.system === "ats"`。若未登录或登录到 People 系统，参照下方「第 1 步」处理。

向用户展示当前 env / orgName 并请求确认后再继续。

### Q2. 调用 org/info 接口

```bash
cllmk curl --url "/api/v2/org/info" --method GET --filter jobFields
```

> **注意**：该接口完整响应体积较大且可能包含与当前任务无关的业务配置。必须使用 `--filter jobFields` 只保留职位字段，再通过 `jq` 做必要筛选；不要直接展开完整响应。
>
> 若返回 `code:1` 且消息明确指向 filter 路径错误，按 `references/foundation/auth.md`
> 的 filter 失败规则检查最小父路径；不得直接判定该租户没有职位字段配置。

### Q3. 字段列表所在路径与字段结构

字段数组位于 `.data.jobFields`，每个元素包含：

| 字段 | 说明 |
|------|------|
| `id` | 字段 ID（数字） |
| `name` | 字段名称（zh-CN） |
| `type` | 字段类型，值同创建时的 type（如 `multi_select_info`） |
| `isVisible` | 是否可见（0/1） |
| `isRequired` | 是否必填（字符串："必填" / "选填"） |
| `isApproval` | 是否必审（0/1） |
| `isBuiltin` | 是否系统内置（0=自定义，1=系统内置） |
| `isCandidateSearch` | 是否参与候选人搜索（0/1） |
| `isSyncedUp` | 是否同步（0/1） |
| `detail` | **选项/层级明细**，结构随 type 而变（见下） |
| `multiDetail` | **多选选项明细**（仅 `multi_select_info` 类型有此字段） |
| `supplementaryLocales` | 多语言名称及（部分类型的）多语言选项 |
| `fieldAttribute` / `hireMode` / `orgId` / `createdAt` / `updatedAt` | 其他元数据 |

#### `detail` / `multiDetail` 按 type 的形态差异

| type | 选项数据所在字段 | 数据形态 |
|------|------------------|---------|
| `select_info`（单选） | `detail` | 字符串数组（zh-CN 选项）。其他语种在 `supplementaryLocales.<locale>.detail` 同序数组 |
| `multi_select_info`（多选） | `multiDetail` | 对象数组，每项含 `optionId` 和 `localeValues`（14 locale 数组）。`detail` 字段为 `null` |
| `cascade_info`（级联） | `detail` | **字符串数组，每个元素是 JSON 字符串**，需 `JSON.parse` 解析为树。每棵树根含 `id`、`keyword`、`children` |
| 其他简单类型（string_info / text_info / bool_info / day_info / date_info / attachment_info） | — | `detail` 为 `null` |
| 系统内置字段（`isBuiltin==1`） | — | 即使 type 是 select/multi_select/cascade，`detail`/`multiDetail` 也可能为 `null`（前端用预置数据源渲染） |

### Q4. 按 type 筛选

根据用户意图过滤。`type` 取值与创建时一致：

| 用户描述 | `type` 过滤值 |
|---------|---------------|
| 单行文本 | `string_info` |
| 长文本 | `text_info` |
| 单选 | `select_info` |
| 多选 | `multi_select_info` |
| 是否 / 布尔 | `bool_info` |
| 日期（年月日） | `day_info` |
| 日期（年月） | `date_info` |
| 附件 | `attachment_info` |
| 级联 | `cascade_info` |
| 全部 | 不筛选 |

示例（筛选多选字段）：
```bash
jq '[.data.jobFields[] | select(.type=="multi_select_info") | {id, name, type, isVisible, isRequired, isApproval, isBuiltin}]' <cllmk_output_file>
```

筛选自定义（非内置）字段时追加 `select(.isBuiltin==0)`。

### Q5. 展示结果

以 Markdown 表格呈现基础列表，至少包含：ID、字段名、类型、可见、必填、必审、内置/自定义。

若用户同时要看选项明细，按下面 Q6 的规则提取后追加展示。

### Q6. 提取选项明细

按 type 用不同 jq 表达式提取（注意：jq 选择字段时必须**显式**列出 `detail` 或 `multiDetail`，否则就会像我第一次踩坑那样误以为没有选项数据）：

**单选（select_info）**：
```bash
jq '.data.jobFields[] | select(.id==<ID>) | {id, name, options: .detail}'
```

**多选（multi_select_info）**：
```bash
jq '.data.jobFields[] | select(.id==<ID>) | {id, name, options: [.multiDetail[] | {optionId, zhCN: (.localeValues[] | select(.locale=="zh-CN") | .value)}]}'
```

**级联（cascade_info）**：`detail` 是字符串数组，每项是 JSON 字符串。需要二次解析：
```bash
jq '.data.jobFields[] | select(.id==<ID>) | .detail | map(fromjson) | map({id, keyword, childCount: (.children | length)})'
```
或完整解析整棵树：
```bash
jq '.data.jobFields[] | select(.id==<ID>) | .detail | map(fromjson)'
```

**系统内置字段**（`isBuiltin==1`）：即便 type 是 select/multi_select/cascade，选项也可能为 `null` —— 这类字段前端用预置数据源渲染，本接口不带选项。需告知用户。

---

## 创建职位自定义字段

---

## 第 1 步：前置鉴权检查

**必须**先按 `<skill-dir>/SKILL.md` 的「业务公共前置」执行：

1. **Step 0** — 确认 `cllmk` 已安装（`command -v cllmk`）；未安装则展示安装指引，终止流程
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

## 第 2 步：确认 auth status 和参数

在收集参数之前，**先向用户展示当前登录状态**（来自 `cllmk auth status` 的 `data`，仅包含 system / env / orgId / orgName，不展示 email），并询问是否在此环境下执行操作，确认后继续。

---

## 第 3 步：收集参数

从用户输入中提取以下参数，缺失的**必填**参数用 AskUserQuestion 逐项询问，不得擅自假设：

| 参数 | 说明 | 必填 | 默认 |
|------|------|------|------|
| `name` | 字段名称（zh-CN） | ✅ | — |
| `type` | 字段类型（见类型表） | ✅ | — |
| `isRequired` | 是否必填 | ✅ | `false` |
| `isVisible` | 是否可见/启用 | ✅ | `true` |
| `isApproval` | 是否必审 | ✅ | `false` |
| 选项列表 | select / multi_select 类型的选项值（zh-CN） | 条件必填 | — |
| 级联结构 | cascade 类型的层级数据 | 条件必填 | — |
| `supplementaryLocales` | 其他语种的字段名（及选项） | 可选 | 仅 zh-CN |

**固定值（不询问用户）：**
- `isSyncedUp: true`（所有类型）
- `isCandidateSearch: false`（cascade 以外的类型）

### 字段类型映射表

| 用户描述 | `type` 值 |
|----------|-----------|
| 单行文本 / 文本 / 字符串 | `string_info` |
| 长文本 / 多行文本 / 富文本 | `text_info` |
| 单选 / 下拉 | `select_info` |
| 多选 | `multi_select_info` |
| 是否 / 布尔 / 开关 | `bool_info` |
| 时间（年月日）/ 日期 | `day_info` |
| 时间（年月）/ 年月 | `date_info` |
| 附件 | `attachment_info` |
| 级联 / 多级联动 / 省市区 | `cascade_info` |

---

## 第 4 步：构造请求 Body

根据字段类型，按以下规则构造 JSON body：

### 组 A — 简单类型（string_info / text_info / bool_info / day_info / date_info / attachment_info）

```json
{
  "type": "<type>",
  "name": "<name>",
  "isVisible": true,
  "isRequired": false,
  "isSyncedUp": true,
  "isApproval": false,
  "isCandidateSearch": false,
  "supplementaryLocales": {
    "zh-CN": { "name": "<name>" }
  }
}
```

若用户提供其他语种名称（如 `en-US: "Field Name"`），追加到 `supplementaryLocales`：
```json
"supplementaryLocales": {
  "zh-CN": { "name": "字段名" },
  "en-US": { "name": "Field Name" },
  "fr-FR": { "name": "Nom du champ" }
}
```

---

### 组 B — 单选（select_info）

```json
{
  "type": "select_info",
  "name": "<name>",
  "isVisible": true,
  "isRequired": false,
  "isSyncedUp": true,
  "isApproval": false,
  "isCandidateSearch": false,
  "supplementaryLocales": {
    "zh-CN": { "name": "<name>", "detail": ["选项1", "选项2", "选项3"] }
  },
  "detail": ["选项1", "选项2", "选项3"]
}
```

规则：
- `detail`（顶层）= zh-CN 选项数组
- `supplementaryLocales.zh-CN.detail` = 同上，与顶层 `detail` 保持一致
- 若用户提供其他语种的选项翻译，在对应 locale 下补充 `name` 和 `detail`（顺序与 zh-CN 一致）：
  ```json
  "supplementaryLocales": {
    "zh-CN": { "name": "单选字段", "detail": ["选项1", "选项2"] },
    "en-US": { "name": "Select Field", "detail": ["Option1", "Option2"] }
  }
  ```

---

### 组 C — 多选（multi_select_info）

```json
{
  "type": "multi_select_info",
  "name": "<name>",
  "isVisible": true,
  "isRequired": false,
  "isSyncedUp": true,
  "isApproval": false,
  "isCandidateSearch": false,
  "supplementaryLocales": {
    "zh-CN": { "name": "<name>" }
  },
  "multiDetail": [
    {
      "localeValues": [
        { "locale": "zh-CN", "value": "选项1" },
        { "locale": "en-US", "value": "" },
        { "locale": "ms-MY", "value": "" },
        { "locale": "id-ID", "value": "" },
        { "locale": "ja-JP", "value": "" },
        { "locale": "es-ES", "value": "" },
        { "locale": "ko-KR", "value": "" },
        { "locale": "de-DE", "value": "" },
        { "locale": "zh-HK", "value": "" },
        { "locale": "th-TH", "value": "" },
        { "locale": "zh-TW", "value": "" },
        { "locale": "pt-PT", "value": "" },
        { "locale": "fr-FR", "value": "" },
        { "locale": "vi-VN", "value": "" }
      ]
    },
    {
      "localeValues": [
        { "locale": "zh-CN", "value": "选项2" },
        { "locale": "en-US", "value": "" },
        ...
      ]
    }
  ]
}
```

规则：
- 每个选项对应 `multiDetail` 中一个对象
- 14 个 locale 顺序固定：`zh-CN, en-US, ms-MY, id-ID, ja-JP, es-ES, ko-KR, de-DE, zh-HK, th-TH, zh-TW, pt-PT, fr-FR, vi-VN`
- 用户未提供翻译的 locale，`value` 填 `""`
- 若用户提供某语种翻译（如 `en-US: ["Option1", "Option2"]`），填入对应位置的 `value`
- `supplementaryLocales` 只含 `name`，**不含** `detail`（多选选项语言在 `multiDetail` 里）

---

### 组 D — 级联（cascade_info）

```json
{
  "type": "cascade_info",
  "name": "<name>",
  "isVisible": true,
  "isRequired": false,
  "isSyncedUp": true,
  "isApproval": false,
  "supplementaryLocales": {
    "zh-CN": { "name": "<name>" }
  },
  "detail": [
    {
      "keyword": "中国",
      "id": "<root-id-1>",
      "supplementaryLocales": { "zh-CN": { "keyword": "中国" } },
      "children": [
        {
          "keyword": "北京",
          "id": "<child-id-1>",
          "supplementaryLocales": { "zh-CN": { "keyword": "北京" } },
          "children": []
        },
        {
          "keyword": "上海",
          "id": "<child-id-2>",
          "supplementaryLocales": { "zh-CN": { "keyword": "上海" } },
          "children": []
        }
      ]
    },
    {
      "keyword": "美国",
      "id": "<root-id-2>",
      "supplementaryLocales": { "zh-CN": { "keyword": "美国" } },
      "children": [
        {
          "keyword": "纽约",
          "id": "<child-id-3>",
          "supplementaryLocales": { "zh-CN": { "keyword": "纽约" } },
          "children": []
        }
      ]
    }
  ]
}
```

规则：
- **不含** `isCandidateSearch` 字段
- 节点的多语言 key 是 `keyword`（不是 `name`）
- 叶子节点的 `children` 为 `[]`
- **ID 生成规则**：
  - 用户提供了节点 ID → 使用用户提供的（字符串）
  - 用户未提供 → 按 13 位近似 epoch 毫秒风格自动生成：
    - 每棵根节点基值间隔 1000（具体值由运行时生成）
    - 同根节点下子节点递增（`...000`, `...001`, `...002`, ...）
    - 确保同一请求内所有节点 ID 唯一

---

## 第 5 步：展示完整 payload，等待用户确认

在执行前，必须将完整请求展示给用户，等待明确确认后才发起请求：

```
即将执行以下请求：

POST /api/outer/ats-jc/job/jobCustomFields/create
（当前会话：<system> / <env> / <orgName>）

{
  <完整 JSON body，格式化缩进>
}

确认执行？
```

用户说"确认""可以""执行""ok""是"等明确指令后才继续。其他回复视为未确认。

---

## 第 6 步：执行 cllmk curl

```bash
cllmk curl \
  --url "/api/outer/ats-jc/job/jobCustomFields/create" \
  --method POST \
  --payload '<完整 JSON 字符串>'
```

---

## 第 7 步：处理结果

| cllmk 输出 | 处理方式 |
|-----------|---------|
| `code:0` | 告知创建成功，展示响应中的关键字段（如返回的字段 ID） |
| `code:1, msg: "HTTP 401"` / `"HTTP 403"` | 执行 `cllmk auth status` 重新验证；若 session 失效则引导重新登录 |
| `code:1, msg: "HTTP 4xx"` | 展示错误详情，提示检查参数（字段名重复、类型非法等） |
| `code:1, msg: "HTTP 5xx"` | 提示服务端错误，建议稍后重试 |
| `code:1, msg: "Not logged in"` | 引导重新登录 |

---

## 安全约束

- **禁止**展示或记录 Cookie 明文（`moka-jwt` 等 token 值）
- **禁止**静默执行，每次调用前必须展示完整 payload 并获得用户显式确认
- **禁止**在 `isApproval` 缺失时擅自默认为 `true`，必须明确询问用户

---

## 交互示例

### 示例 1 — 创建单行文本字段

> 用户：帮我创建一个叫"备注"的单行文本职位字段，必填，可见，不必审

1. 执行鉴权检查，确认当前 ATS 会话
2. 展示 auth status（env / orgName）并请用户确认环境
3. 收集参数：`name=备注, type=string_info, isRequired=true, isVisible=true, isApproval=false`
4. 构造 body（组 A），展示完整 payload
5. 用户确认后执行 `cllmk curl`

---

### 示例 2 — 创建单选字段（多语言）

> 用户：创建职位字段"招聘优先级"，单选，选项：高/中/低，不必填，英文名 Recruitment Priority，英文选项 High/Medium/Low

1. 鉴权通过
2. 参数：`name=招聘优先级, type=select_info, isRequired=false, isVisible=true, isApproval=false`
3. 构造 body（组 B）：
   - `detail: ["高", "中", "低"]`
   - `supplementaryLocales.zh-CN.detail: ["高", "中", "低"]`
   - `supplementaryLocales.en-US: { name: "Recruitment Priority", detail: ["High", "Medium", "Low"] }`
4. 展示 payload → 确认 → 执行

---

### 示例 3 — 创建多选字段

> 用户：创建职位字段"技能要求"，多选，选项：Java / Python / Go，非必填

1. 鉴权通过
2. 参数：`name=技能要求, type=multi_select_info, isRequired=false, isVisible=true, isApproval=false`
3. 构造 body（组 C）：3 个选项，每个选项 14 locale，zh-CN 填值，其余填 `""`
4. 展示 payload → 确认 → 执行

---

### 示例 4 — 创建级联字段

> 用户：创建职位字段"工作城市"，级联，结构：中国-北京/上海，美国-纽约，非必填

1. 鉴权通过
2. 参数：`name=工作城市, type=cascade_info, isRequired=false, isVisible=true, isApproval=false`
3. 构造 body（组 D）：
   - 自动生成 ID：按根节点和子节点顺序生成，具体值由运行时确定
4. 展示 payload → 确认 → 执行

---

### 示例 5 — 未登录场景

> 用户：帮我创建职位字段

1. `cllmk auth status` 返回 `code:1, msg: "Not logged in"`
2. 询问用户目标 env（如 intl / cn / s3）
3. 在受工具管理的长运行会话中执行 `cllmk ats intl auth login`，并立即告知用户去弹出的 Chrome 里完成登录
4. 命令返回后跑裸 `cllmk auth status` 确认 `code:0` 且 `orgName` 是目标公司，回到 Step 1 重新检查
