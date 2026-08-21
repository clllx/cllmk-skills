---
route: candidate-field-manage
---

# 候选人信息字段管理

## 目录

- 前置鉴权与操作类型
- 模块归属与标准字段匹配
- 字段参数、类型、语言与选项 ID
- 创建、更新、停用与启用接口
- 调用前确认与响应处理
- 字段查询接口附录

## 第 1 步：前置鉴权

执行前须已通过 `<skill-dir>/SKILL.md` 的「业务公共前置」，确认当前会话
`data.system === "ats"`。若会话状态异常，按
`<skill-dir>/references/foundation/auth.md` 的对应分支完成鉴权后继续。

---

## 第 2 步：判断操作类型

| 触发关键词 | 操作 |
|----------|------|
| 创建 / 新增 / 新建 / 加 / 添加 | **创建** → 第 3 步 |
| 更新 / 修改 / 改名 / 改为 / 变更 | **更新** → 第 6 步 §6.2 |
| 停用 / 禁用 / 关闭 | **停用** → 第 6 步 §6.3 |
| 启用 / 开启 / 重新启用 | **启用** → 第 6 步 §6.4 |

若无法判断操作类型，询问：「是要新建字段还是修改已有字段？」

---

## 第 3 步：模块归属判断

### 3.1 系统标准模块

| 模块名称 | relatedTo | 支持多段 | 典型字段举例 |
|---------|----------|---------|------------|
| 个人信息 | basicInfo | 否 | 姓名、手机号、邮箱、现居住城市 |
| 求职意向 | jobIntention | 否 | 期望职位、期望城市、期望薪资 |
| 自我描述 | selfDescription | 否 | 自我评价 |
| 上传 | uploadInfo | 否 | 文件上传（仅 custom_file_upload 类型） |
| 工作经历 | experienceInfo | 是 | 公司名称、职位、在职时间、薪资 |
| 教育经历 | educationInfo | 是 | 学校名称、专业、学历 |
| 实习经历 | practiceInfo | 是 | 实习公司、岗位 |
| 项目经历 | projectInfo | 是 | 项目名称、项目描述 |
| 语言能力 | languageInfo | 是 | 语言种类、熟练程度 |
| 获奖经历 | awardInfo | 是 | 奖项名称、获奖时间 |

### 3.2 自定义模块查询

若用户指定的模块不在 3.1 表格中，则为自定义模块。调用 org/info 查询：

```bash
cllmk curl --url "/api/v2/org/info" --method GET --filter customBlocks
```

本文所有 `org/info --filter ...` 调用若返回明确的 filter 路径错误，按
`references/foundation/auth.md` 检查最小父路径；这属于本地筛选失败，不能直接解释为租户无配置。

从响应 `data.customBlocks[]` 中按名称模糊匹配（trim + 大小写不敏感）：

| 匹配结果 | 处理 |
|---------|------|
| 找到 1 条 | 使用 `customBlocks[].id`（数字）作为 relatedTo，继续第 4 步 |
| 找到多条 | 列出候选模块（title + id）让用户选择 |
| 未找到 | 询问：「未找到模块【{名称}】，是否新建该自定义模块？」→ 见 §3.3 |

### 3.3 新建自定义模块

收集以下参数：

| 参数 | 说明 | 默认值 |
|------|------|-------|
| 模块名称 | 显示名称 | 必填 |
| 是否支持多段 | 候选人是否可添加多条记录（如多段工作经历） | 否 |

调用前确认（展示参数 + 获得用户确认），然后执行：

```bash
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-blocks" \
  --method POST \
  --payload '{"title":"<模块名称>","multi":<true/false>,"supplementaryLocales":"{\"zh-CN\":{\"title\":\"<模块名称>\"}}"}'
```

> 🚨 **响应是全量模块列表，不是刚创建的那一条**（实测）：`data` 返回该租户下**所有**
> 自定义模块的数组。连续创建两个模块时，第一次返回 1 条，第二次返回 2 条（含第一次的）。
>
> 取新模块 ID 必须**按 `title` 在返回数组里匹配**，不要取 `data[0]` 或 `data[-1]`，
> 否则后续字段会挂到错误的模块下。

成功后按 title 匹配取出该模块的 `id` 作为 relatedTo，继续第 4 步。

### 3.4 归属判断规则

**若用户指定了模块：**
- 在该模块下按「字段名称 + 字段类型」匹配已有字段
- 若已有匹配字段 → 提示「该模块下已有字段【xxx】（类型：xxx），无需重复创建」，终止流程
- 若无匹配字段 → 进入第 4 步

**若用户未指定模块：**
1. 根据字段名称语义推断最可能的模块（参考 3.1 表格）
2. 向用户确认：「建议将【{字段名}】放在【{模块名}】模块，确认吗？」
3. 用户确认后进入第 4 步；用户修正后按修正后的模块操作

---

## 第 4 步：标准字段匹配

在进入自定义字段创建前，先尝试匹配系统标准字段：

**模糊匹配规则（不区分大小写，允许同义词）：**
- 若字段名与标准字段**完全一致** → 提示「系统已有标准字段【xxx】，建议使用标准字段而非自定义」，**终止自定义创建流程**
- 若字段含义与标准字段**一致但名称不同**（如用户说「GPA」，标准字段叫「绩点」）→ 提示「系统有含义相近的标准字段【{标准字段名}】，是否使用标准字段？」，等待用户确认：
  - 用户选择使用标准字段 → 终止自定义创建流程
  - 用户选择新建自定义字段 → 进入第 5 步
- 若无任何匹配 → 直接进入第 5 步

每轮任务从固定 CDN 加载一次标准字段池并缓存：

```bash
STANDARD_FIELDS_FILE="$(mktemp /tmp/cllmk-candidate-standard-fields.XXXXXX)"
curl -fsSL "https://cdn.five5.life/cllmk/public/candidate_standard_fields.json" \
  -o "$STANDARD_FIELDS_FILE"
jq -e 'type == "array" and length > 0' "$STANDARD_FIELDS_FILE" >/dev/null
```

使用 `labelZh` 和 `synonyms` 完成精确及同义词匹配。下载或 JSON 校验失败时停止，
不得回退到本地副本、模型记忆或让用户代替系统字段池做判断。

---

## 第 5 步：收集字段参数

### 5.1 通用必填参数

| 参数 | 说明 | 必填 |
|------|------|------|
| 字段名称 | 字段显示名 | ✅ |
| 字段类型 | 见 5.2 类型表 | ✅ |
| 是否必填 | 是/否，默认否 | ✅ |
| 所属模块 | 来自第 3 步确认结果 | ✅ |

### 5.2 字段类型与 API type 对应

| 用户描述 | API type | 附加参数 |
|---------|---------|---------|
| 单行文本 / 文本 / 字符串 | `string_info` | 无 |
| 多行文本 / 长文本 | `text_info` | 无 |
| 确认题 / 声明 / 同意 | `confirm_info` | 见 5.3 |
| 是否 / 布尔 / 是否题 | `bool_info` | 无 |
| 单选 / 下拉选择 | `select_info` | 选项列表（至少 1 项） + 可选选项 ID（见 §5.7） |
| 多选 | `multi_select_info` | 选项列表（至少 1 项） + 可选选项 ID（见 §5.7） |
| 时间段 / 开始结束时间 | `date_group_info` | 无 |
| 时间（年月日）/ 具体日期 | `day_info` | 无 |
| 时间（年月）/ 年月 | `date_info` | 无 |
| 数字 / 数值 | `number_info` | 见 5.4 |
| 手写签名 / 签名 | `signature_info` | 无（仅字段名称） |
| 文件 / 附件 / 上传 | 见 5.5 | 见 5.5 |

> ⚠️ `day_info` 对应「年月日」精度，`date_info` 对应「年月」精度，命名与直觉相反，注意区分。

### 5.3 确认题附加参数

确认题包含三个子字段，需逐一收集：

| 子字段 | API 字段名 | 说明 | 示例 |
|-------|----------|------|------|
| 字段名称 | name | 确认题的标题 | 个人声明 |
| 确认内容 | describe | 需要候选人确认的正文内容 | 本人声明以上填写内容真实有效…… |
| 确认声明 | statement | 底部确认按钮文字（数组，通常 1 条） | 本人已确认并同意上述内容 |

适用场景提示：适用于表单中需要候选人表示同意或确认的内容，例如隐私协议、诚信声明等。

### 5.4 数字附加参数（均为可选）

| 规则 | API 字段 | 说明 |
|-----|---------|------|
| 小数位数 | supportDecimal + decimalPlaces | 是否支持小数？支持几位？ |
| 支持负数 | supportNegative | 是/否 |
| 数字范围 | supportLimits + min + max | 最小值 / 最大值（字符串形式） |

用户未提及时使用默认值（supportDecimal: false, supportNegative: false, supportLimits: false），不追问。

### 5.5 文件字段

文件字段的 API type 取决于所属模块：

| 所属模块 | API type |
|---------|---------|
| uploadInfo（上传模块） | `custom_file_upload` |
| 其他所有模块 | `file_info` |

**fileTypeLimit**（可选，默认 no_limit）：

| 用户描述 | 值 |
|---------|---|
| 不限 / 所有文件 | `no_limit` |
| 文件（PDF/Word 等） | `file` |
| 图片 | `image` |
| 视频 | `video` |

**followingDescription**：上传提示文字，用户未提及时传空字符串 `""`。

### 5.6 supplementaryLocales 语言

- 默认只收集 **zh-CN**
- 若用户明确指定其他语言（如 en-US、fr-FR），按指定语言收集
- 支持同时收集多个语言

**多语言写法规范（生成 payload 时遵循）：**

- `name` 默认仅放主语言 zh-CN；其他语言只承载差异化字段（detail / describe / statement / followingDescription）。
- 若用户明确指定其他语言的 name 与 zh-CN 不同 → 在该语言下显式写入 name。
- 若用户要求所有语言都带 name 即便内容相同 → 系统接受这种写法，不强制移除。

**解析 org/info 返回时的兼容写法（read 侧三种均接受）：**

| 写法 | 示例 |
|------|------|
| (a) 不写 name 键 | `"en-US": {"detail": [...]}` |
| (b) name 为空字符串 | `"en-US": {"name": "", "detail": [...]}` |
| (c) name 与 zh-CN 同 | `"en-US": {"name": "Country", "detail": [...]}` |

### 5.7 选项 ID（codes）采集与确认（仅单选/多选）

> 仅 `select_info` / `multi_select_info` 适用。其他字段类型跳过本节。

#### 5.7.1 分隔符识别

| 优先级 | 分隔符清单 |
|--------|-----------|
| 强分隔符（极少出现在选项内容里） | Tab、连续 ≥2 空格、`": "`（冒号+空格）、`" - "`（空格+短横+空格）、`" \| "`（markdown 表格分隔） |
| 弱分隔符（容易与选项内容混淆） | 单空格、`,`、`-`、`_` |

#### 5.7.2 切分策略

1. 对用户输入按换行拆为多行。
2. 对每一行先尝试用同一种强分隔符切出 2 段；不成功则尝试弱分隔符。
3. 整段输入必须用同一种分隔符成功切出 2 段才算"识别为 (label, code) 列表"。

#### 5.7.3 歧义停下询问

任一行强弱分隔符均无法切出恰好 2 段，或多行使用了不同分隔符 → **停下**，按以下话术询问，**禁止自动猜测**：

```
解析选项列表时遇到歧义：

可解析为「选项 + ID」的行（共 N 行）：
  - <example>

无法解析的行（共 M 行）：
  - <example>

请确认这是「选项 + ID」列表，还是纯选项列表？
```

#### 5.7.4 即便能切也要二次确认

**所有行成功切出 2 段** ≠ 直接启用 codes。继续询问：

```
识别为「选项 + ID」格式，共 N 项。
样例：<前 3 行 label ↔ code 展示>

要把第 2 列作为选项 ID（codes）写入字段吗？

- 是 → 启用 codes（按 §6.1 拼装）
- 否 → 仅保留第 1 列作为选项标签，codes 留空
```

理由：用户给的"两列"可能仅是 zh-CN/en-US 名副本或 markdown 美化，自动启用会误生成 codes。

#### 5.7.5 软警告（不阻断，需用户确认）

| 触发条件 | 话术提示 |
|---------|--------|
| codes 出现重复 | 列出重复项 + 行号，询问"重复 code 是否符合预期？" |
| codes 含全角字符 | 列出问题项，询问"含全角字符的 code 是否符合预期？" |
| codes 内嵌空白 | 列出问题项，询问"含空白的 code 是否符合预期？" |

软警告均不本地阻断，用户确认后允许提交。

#### 5.7.6 硬约束

- **codes 数量必须 ≡ detail 数量**。不等 → 停下，提示用户重新提供，**禁止本地补齐或截断**。
- 字符规则（如 `[A-Z0-9_]+`）不本地校验，由 API 端决定接受或拒绝；API 返回错误时按第 8 步处理。

---

## 第 6 步：接口调用

### §6.1 创建字段

**endpoint**：`POST /api/outer/ats-candidate/apply-form/custom-fields`

**payload 构造**：

所有类型通用字段：

| 字段 | 值 |
|-----|---|
| relatedTo | 标准模块字符串（如 `"basicInfo"`）或自定义模块数字 ID（如 `"100000057"`） |
| type | 见 5.2 |
| name | 字段名称 |
| supplementaryLocales | stringified JSON（见下方结构） |

各类型附加字段：

| type | 附加字段 |
|------|---------|
| `select_info` / `multi_select_info` | `"detail": "[\"选项1\",\"选项2\"]"`（stringified 数组）, `"codes": null \| "[\"code1\",\"code2\",...]"`（未启用为 null；启用时为与 detail 同序的 stringified 字符串数组，见 §5.7） |
| `number_info` | `"detail": "{\"supportDecimal\":false,\"decimalPlaces\":\"2\",\"supportNegative\":false,\"supportLimits\":false,\"min\":\"\",\"max\":\"\"}"` |
| `confirm_info` | `"describe": "<确认内容>"`, `"statement": "[\"<确认声明>\"]"`（stringified 数组） |
| `custom_file_upload` / `file_info` | `"followingDescription": "<说明或空字符串>"`, `"fileTypeLimit": "<值>"` |
| 其余类型 | 无附加字段 |

**supplementaryLocales 结构**（stringify 之前）：

```
// 单行/多行/是否/签名/时间/数字
{ "zh-CN": { "name": "<字段名>" } }

// 单选/多选
{ "zh-CN": { "name": "<字段名>", "detail": ["选项1", "选项2"] } }

// 确认题
{ "zh-CN": { "name": "<字段名>", "describe": "<确认内容>", "statement": ["<确认声明>"] } }

// 文件
{ "zh-CN": { "name": "<字段名>", "followingDescription": "<说明文字>" } }
```

**多语言写法（按 §5.6 规范：name 仅 zh-CN，其他语言只放差异化字段）：**

```
// 单选/多选 + 中英双语（中英文名相同）
{
  "zh-CN": { "name": "Country", "detail": ["Afghanistan","Albania"] },
  "en-US": { "detail": ["Afghanistan","Albania"] }
}

// 单选/多选 + 中英双语（名字不同）
{
  "zh-CN": { "name": "国家", "detail": ["阿富汗","阿尔巴尼亚"] },
  "en-US": { "name": "Country", "detail": ["Afghanistan","Albania"] }
}
```

**cllmk 调用**：

```bash
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-fields" \
  --method POST \
  --payload '<完整 JSON payload>'
```

成功（code:0）后展示返回的字段 ID。

> ℹ️ **codes 字段说明**：仅在用户经 §5.7 二次确认后启用时附带；未启用时传 `null`。服务端会归一化为 `""`，与 `null` 等价语义，不影响客户端发起。

---

### §6.2 更新字段

**第一步：查询字段**

```bash
cllmk curl --url "/api/v2/org/info" --method GET --filter customFields
```

从 `data.customFields[]` 中定位目标字段（trim + 大小写不敏感名称匹配，或按 ID 精确匹配）：

| 命中数 | 处理 |
|--------|------|
| 0 条 | 告知「未找到字段【xxx】」；列出所有 customFields 供用户选择 |
| 1 条 | targetField = 该字段，继续 |
| 多条 | 列出候选字段（name + id + type）让用户确认 |

> ⚠️ 已停用字段不出现在 org/info 响应中。若目标字段已停用，需先启用（§6.4）再更新。
>
> ⚠️ org/info 不返回 `codes` 字段。**更新单选/多选字段时如需保留原 codes（§6.2 第二步 ① / ④ / ⑤ 类变更），必须改用附录 A 的 v2 接口读取原 codes 后再合成 PUT payload**，否则会把已配置的选项 ID 全部丢失。

**第二步：detail 变更类型检测（仅单选/多选）**

对比 org/info 返回的 `detail` 与用户提交的修改，按变更类型分别处理 `codes`：

| # | 变更类型 | codes 处理 | 说明 |
|---|---------|-----------|------|
| ① | 文案 rename（数量+顺序不变） | codes 保留 | 如 "Afghanistan" → "Afghanistan-updated"，按位置保留原 ZWE...AFG codes |
| ② | 删除某些选项（数量减少，剩余顺序不变） | 按位置同步删除对应 codes | 展示「删除项 ↔ 对应 code」对照表给用户确认；用户确认后才提交 |
| ③ | 新增某些选项（数量增加，原有顺序不变） | 询问用户每个新项的 code | 用户可填空（视为该项无 code），但需明确确认 |
| ④ | 顺序调整（数量不变） | 警告 codes 与 label 错位风险 | 让用户确认「保留旧 codes 顺序」或「整体重新提供 codes」 |
| ⑤ | 字段 rename（不动 detail） | codes 保留 | 仅 name / supplementaryLocales 变化 |
| ⑥ | 用户主动改 codes | 校验新 codes 长度 ≡ 当前 detail 长度 | 不等时停下询问，禁止本地补齐或截断 |

若混合多类变更（如同时新增 + 顺序调整），按各自规则依次处理后再合成最终 codes。

**第三步：构造 payload（按字段类型的最小必传集）**

PUT payload 至少包含下列字段，按字段类型决定附加项：

| 字段类型 | 最小必传字段集 | 实测状态 |
|---------|--------------|---------|
| `string_info`（含推断：`bool_info` / `signature_info` / `text_info` / `date_info` / `day_info` / `date_group_info`） | `id`, `name`, `orgId`, `relatedTo`, `type`, `operate` (true), `version` ("1.0"), `supplementaryLocales` （8 字段） | string_info ✅ 已实测；其余推断同结构 |
| `select_info` / `multi_select_info` | 上述 8 + `detail` (stringified) + `codes` (null \| stringified) （10 字段） | ✅ 已实测 |
| `number_info` | 8 字段 + `detail` (数字配置 stringified JSON) | ⏳ TBD（首次遇到时复测） |
| `confirm_info` | 8 字段 + `describe`, `statement` (stringified) | ⏳ TBD |
| `file_info` / `custom_file_upload` | 8 字段 + `fileTypeLimit`, `followingDescription` | ⏳ TBD |

> ✅ 现行旧版要求的 `disabled` / `isDeleted` / `fileTypeLimit` / `referenceScope` 等附加固定字段**对 select_info / string_info 更新已实测非必传**，PUT 时可省略；服务端不会拒绝。

**序列化要点：**

- `detail`：org/info 返回时是数组/对象，PUT 时必须 `JSON.stringify`。
- `codes`：未启用时传 `null`；启用时传 stringified 字符串数组（与 detail 同序）。服务端归一化为 `""`，不影响发起。
- `supplementaryLocales`：同样需要 stringify。按 §5.6 多语言规范生成。

**第四步：调用**

```bash
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-fields" \
  --method PUT \
  --payload '<完整 JSON payload>'
```

---

### §6.3 停用字段

**第一步**：同 §6.2 第一步查询字段，取 targetField.id。

**第二步：调用**

```bash
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-fields/status" \
  --method POST \
  --payload '{"id":<字段ID>,"disabled":true}'
```

---

### §6.4 启用字段

> 已停用字段不在 org/info 中，无法通过名称查询。
> **若用户只记得字段名而不知道 ID**，使用附录 A 的 v2 接口查询（v2 响应包含 `disabled: true` 的字段，可按名称定位后取 id）。
> 仍无法定位时再请用户提供 ID（可在 Moka 后台候选人字段设置页面查看）。

```bash
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-fields/status" \
  --method POST \
  --payload '{"id":<字段ID>,"disabled":false}'
```

---

## 第 7 步：调用前确认

在执行接口调用前，必须向用户展示完整请求信息并获得确认：

```
即将执行以下操作（{创建/更新/停用/启用}）：

接口：{HTTP方法} {接口路径}
当前会话：{system} / {env} / {orgName}
所属模块：{模块名称}（仅创建时展示）

请求内容：
{完整 JSON payload，格式化缩进}

确认执行？
```

**单选/多选字段额外要求**（创建与更新通用）：

- payload 预览中必须显式展示 `codes` 字段值（null 或 stringified 数组）。
- 若 codes 启用，预览部分加一份「选项 ↔ code」对照行，便于用户核对：
  ```
  选项 / code 对照（前 3 行示例）：
    Afghanistan ↔ AFG
    Albania     ↔ ALB
    Algeria     ↔ DZA
    （共 N 项）
  ```
- 更新场景下若触达 §6.2 第二步的 ② / ③ / ④ 类变更，对照表必须展示完整变更前后差异。

用户说「确认」「可以」「执行」「ok」「是」等明确指令后才继续，其他回复视为未确认。

---

## 第 8 步：处理接口响应

| 响应 | 处理方式 |
|-----|---------|
| 成功（code:0） | 告知操作成功，展示返回的字段 ID 等关键信息 |
| HTTP 401 / 403 | 执行 `cllmk auth status` 重新验证；session 失效则引导重新登录 |
| HTTP 4xx 其他 | 展示错误详情，提示检查参数（字段名重复、类型非法等） |
| HTTP 5xx | 提示服务端错误，建议稍后重试 |
| Not logged in | 引导用户重新登录 |

---

## 附录 A：字段查询接口（含选项 ID / codes）

候选人自定义字段有两个查询接口，能力差异显著，按需求选择：

### A.1 接口对比

| 接口 | 方法 | 含 `codes` | 含已停用 | 适用场景 |
|------|------|-----------|---------|---------|
| `/api/v2/org/info` | GET | ❌ 无该字段 | ❌ 仅启用 | 仅判断字段是否存在、模块归属推断、命名匹配等轻量查询 |
| `/api/outer/ats-candidate/apply-form/custom-fields/v2?orgId={orgId}` | POST | ✅ 返回 `codes` | ✅ 含停用 | 需要选项 ID、批量导出字段/选项数据、按名称查停用字段 |

> ⚠️ orgId 必须作为 query 参数显式传入，缺失会返回 `"orgId未填写, 请填充。"`。从 `cllmk auth status` 的 `data.orgId` 读取，不要硬编码。

### A.2 何时改用 v2 接口

满足任一即应使用 v2：

- 用户明确提到「选项 ID」「选项 code」「字段编码」「选项编码」
- 批量导出字段或选项数据（如生成 XLSX/CSV 报表）
- 更新单选/多选字段前需读取并保留原 codes（§6.2 第二步对 ① / ④ / ⑤ 的"保留旧 codes"硬性要求）
- 用户只记得名称但目标字段可能已停用（org/info 看不到）

其余场景继续使用 org/info 即可，响应更轻量。

### A.3 v2 调用示例

```bash
# 先取 orgId
ORG_ID=$(cllmk auth status | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['orgId'])")
cllmk curl \
  --url "/api/outer/ats-candidate/apply-form/custom-fields/v2?orgId=${ORG_ID}" \
  --method POST
```

### A.4 响应结构与解析要点

响应 `data` 是字段数组，每项关键字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | number | 字段 ID |
| `name` | string | 字段名称（主语言） |
| `type` | string | 字段类型（同创建/更新接口） |
| `relatedTo` | string | 标准模块字符串或自定义模块数字 ID |
| `disabled` | bool | 是否停用；按需过滤 `not f.disabled` |
| `operate` | bool | 是否可操作（权限标识） |
| `detail` | string | **stringified JSON**：选项列表（select）或数字配置（number_info） |
| `codes` | string \| null \| `""` | **stringified JSON**：选项 ID 数组；未配置时为 `""` / `null` / 缺失 |
| `supplementaryLocales` | string | **stringified JSON**：多语言名称与选项 |
| `fileTypeLimit` | string | 文件类字段适用 |
| `referenceScope` | object | 评分/筛选/标签规则引用范围 |

**解析顺序：**

1. 用 `JSON.parse`（或 `json.loads`）逐项解出 `detail` / `codes` / `supplementaryLocales`。
2. `codes` 视作可选：空字符串 / null / 缺失 → 该字段未配 code，按"无 code"处理；不要本地造一个空数组以外的占位。
3. 按 `disabled` 过滤启用字段；想看停用字段（如查 ID）反向过滤即可。

### A.5 codes ↔ detail 对齐保证（实测）

当 `codes` 非空时：

- **长度严格等于** `detail` 长度（实测 5 个已配 code 的字段全部对齐，0 错位）
- 按数组下标 1-to-1 对齐（detail[i] ↔ codes[i]）

若发现长度不等，视为数据异常：**停下询问用户而非自动补齐/截断**，与 §5.7.6 / §6.2 第二步 ⑥ 的硬约束一致。

### A.6 典型用例：批量导出选项及 code

读取 v2 响应 → 过滤启用 → 对 select_info / multi_select_info 解析 detail+codes → 生成报表（如 XLSX，每个字段一个 sheet，列：序号 / 选项名称 / 选项ID）。注意 CSV 无多 sheet 概念，遇到「一个文件多 sheet」需求时应改用 XLSX 并向用户说明。
