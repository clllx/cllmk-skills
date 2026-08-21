# 候选人登记表模板创建

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

## 目录

- 前置鉴权与系统上下文
- 输入解析与类型推断
- 字段匹配、模块归属与首次确认
- 缺失字段创建
- 联动识别、限制与最终确认
- setting/payload 拼装与两段式接口调用
- 响应处理、完整示例与边界用例

## 第 1 步：前置鉴权

执行前须已通过 `<skill-dir>/SKILL.md` 的「业务公共前置」，确认当前会话
`data.system === "ats"`。若会话状态异常，按
`<skill-dir>/references/foundation/auth.md` 的对应分支完成鉴权后继续。

---

## 第 2 步：加载系统上下文

本步骤的全部输入在**本轮会话内仅加载一次并缓存**，避免后续步骤重复请求。

| 输入 | 来源 | 用途 |
|------|------|------|
| `orgId` / `env` / `orgName` | `cllmk auth status` | 接口路径拼接、入口 URL、日志展示 |
| 自定义字段 `customFields[]` | `GET /api/v2/org/info` 的 `data.customFields[]` | 与原文字段做匹配 |
| 自定义模块 `customBlocks[]` | `GET /api/v2/org/info` 的 `data.customBlocks[]` | 模块归属判断、categoryOrder 写入 |
| 模板克隆基底 | `GET /api/apply_form_info/<orgId>?hireMode=1` 的 `applyForm[0]`（含回退） | 取 `id` 作为创建接口的 `applyFormId`；取 `setting` 作为 categoryOrder + 各模块 fieldOrder 的克隆基底。**回退规则**：若 `applyForm[0].setting` 各模块 fieldOrder 全部为空（某些租户可能存在 Headhunter 表占位、`fo=0` 的情况，对克隆无意义），改用首个"有非空 fieldOrder"的 `applyForm[i]`（通常是租户的"标准简历"），并向用户展示选择依据。|
| 标准字段池 | `https://cdn.five5.life/cllmk/public/candidate_standard_fields.json` | 80 字段 / 10 标准模块，含 `synonyms`，作为匹配主依据；每轮任务从 CDN 加载一次 |
| **现有联动（仅更新场景）** | `POST /api/outer/ats-candidate/apply-form/extend-info/query/config`，payload `{"ids":[<表ID>],"type":1}` | **必须在 save 前读取**：取 `applyFormExtendInfoList[0].fieldLinkedList` 作为旧联动基线，与本次新增联动合并后整体下发（save 是 REPLACE 语义，见 §9.5.2） |

**调用示例：**

```bash
cllmk curl --url "/api/v2/org/info" --method GET
cllmk curl --url "/api/apply_form_info/<orgId>?hireMode=1" --method GET

# 仅更新现有表时必跑
cllmk curl --url "/api/outer/ats-candidate/apply-form/extend-info/query/config" \
  --method POST --payload '{"ids":[<表ID>],"type":1}'
```

> ⚠️ `apply_form_info` 路径不带 `/api/outer/...` 前缀，按抓包路径直传。
>
> ⚠️ **更新表时不要根据 `apply_form_info.applyForm[].fieldLinkageMode` 判断"是否有联动"**：
> 实际观察到该字段为 `None` 但 `extend-info/query/config` 里仍有有效的 `fieldLinkedList` 记录。
> 唯一权威的现有联动来源是 `extend-info/query/config` 的返回值。
> 另一线索：`setting.<blockId>.fieldOrder` 中若同一字段 ID 重复出现 N 次，
> 通常代表 `fieldLinkedList` 中有 N 条记录指向它，可作旁证但**不能替代实际查询**。

### 标准字段池加载

每轮任务从固定 CDN 地址下载一次标准字段池，并在本轮内缓存使用：

```bash
STANDARD_FIELDS_FILE="$(mktemp /tmp/cllmk-candidate-standard-fields.XXXXXX)"
curl -fsSL "https://cdn.five5.life/cllmk/public/candidate_standard_fields.json" \
  -o "$STANDARD_FIELDS_FILE"
jq -e 'type == "array" and length > 0' "$STANDARD_FIELDS_FILE" >/dev/null
```

下载失败或 JSON 校验失败时立即停止字段匹配并报告错误。不要回退到本地副本，
也不要凭模型记忆补全标准字段。任务结束后可删除该临时文件。

### 2.1 登记表 type 枚举与单例语义

`apply_form_info.applyForm[].type` 是**登记表种类标识**，且 1 / 2 / 3 各为**租户内单例**：

| type | 种类 | 单例 |
|------|------|------|
| 1 | 标准简历 | ✅ 每租户一张 |
| 2 | 面试登记表 / 候选人信息登记表 | ✅ 每租户一张（同一个槽位） |
| 3 | 猎头更新简历登记表 | ✅ 每租户一张 |
| 0 | 用户自建的自定义登记表 | ❌ 可多张 |

> ⚠️ 不要与 §7.4 的 `fieldLinkedType` 混淆——那是联动类型，与本表无关。

**表名不能作为识别依据。** 同一个 type 在不同租户可能叫不同名字（例如某些租户
type=2 叫「面试登记表」，另一租户 type=2 叫「候选人信息登记表」）。按 `type` 定位槽位，
不要按名称匹配。

因此，用户要求"新增某张系统表"时先判断意图：

| 情形 | 处理 |
|------|------|
| 目标是 type=1/2/3 的某张系统表 | 该槽位已存在，是**更新（PUT）**而非创建。向用户确认是更新现有表（可选是否同时改名），还是另建一张 type=0 自定义表 |
| 目标是一张新的业务表 | 走创建（POST），`type` 传 `0` |

**更新系统表时 `type` 回传原值**（type=2 就传 2）已实测可正常工作。§9.2 顶层字段表里的
`type: 0` 是按新建场景写的；下发 `0` 去更新已有系统表**未实测**，不要假定它安全。

初始态的系统表（租户从未配置过）特征：`setting.categoryOrder` 为 `null`，各模块只有
`show` / `isSelected` 而 `fieldOrder` 全空。**这种表不适合当克隆基底**，选基底时按 §2
的回退规则跳过它。

### 2.2 兜底：模板基底为空

若 `apply_form_info.applyForm[]` 为空（极少出现，租户从未创建过任何登记表），
告知用户：

```
当前租户未检测到任何已有登记表，本流程依赖一份默认模板作为创建基底。
请先在 Moka 后台「设置 → 申请表」创建一份默认表，再回来重试。
```

终止本次流程。

### 2.3 缓存策略

本轮会话内：
- `org/info`、`apply_form_info`、CDN 标准字段池各自只调用/读取 1 次。
- 若中途新建了自定义字段/模块（第 6 步），需要把新增项**追加**到缓存，
  避免重新请求 `org/info`。

---

## 第 3 步：解析输入

### 3.1 输入形式

接受的输入形式：

| 形式 | 处理方式 |
|------|---------|
| **本地文件路径**（`.md` / `.docx` / `.xlsx`） | 调用 `<skill-dir>/scripts/candidate/parse_form_file.py` 拿到标准化 JSON 后进入 §3.2 |
| **自然语言描述** | 直接进入 §3.2 |
| **md 片段** | 直接进入 §3.2 |

#### 3.1.1 调用解析脚本

收到文件路径时执行：

```bash
uv run --with python-docx --with openpyxl \
  python3 <skill-dir>/scripts/candidate/parse_form_file.py <path>
```

脚本输出结构：

```json
{
  "ok": true,
  "format": "docx" | "xlsx" | "md",
  "form_name": "...",
  "blocks": [
    {
      "title": "...",
      "title_en": "..." | null,
      "repeatable": false,
      "fields": [
        {
          "name": "...",
          "name_en": "..." | null,
          "type_hint": "string|text|select|multi_select|bool|day|date|date_group|number|file|confirm|signature",
          "required": true,
          "options": [],
          "trigger_condition": null,
          "note": null
        }
      ],
      "unnamed_lines": []
    }
  ]
}
```

字段对照与 §3.2-3.4 的关系：

| 脚本输出 | 用法 |
|---------|------|
| `blocks[].title` / `title_en` | §3.2 模块归属 |
| `fields[].name` / `name_en` | §4 智能匹配（中英文双语） |
| `fields[].type_hint` | §3.3 类型推断的**优先依据**；为空时退回原文文本规则 |
| `fields[].required` | §3.4.3 必填默认（脚本已处理 `*` 标记和 `必填` 关键词） |
| `fields[].options` | §3.4.1 选项补全的初值 |
| `fields[].trigger_condition` | §7 联动识别的输入（含"当 X = Y 时显示" 这类描述） |
| `fields[].note` / `unnamed_lines` | 智能匹配时附加上下文，特殊备注列展示 |
| `repeatable: true` | 对应 Moka 多段模块（experienceInfo / educationInfo 等） |

#### 3.1.2 解析失败的降级

| 输出 | 处理 |
|------|------|
| `ok: false` + `fallback_text`（xlsx 布局表单） | 把 `fallback_text` 当 md 片段处理，走 §3.2-3.4 文本解析路径 |
| `ok: false` + `reason: "unsupported extension"`（PDF / 图片） | 提示用户先转 Word / Excel，或用自然语言描述字段 |
| `ok: false` + `reason: "file not found"` | 让用户确认路径 |

> ⚠️ 暂不支持 PDF / 图片直接解析。如用户提供这类文件，
> 请用户先转换为 docx / xlsx / md，或用自然语言描述字段。

### 3.2 字段属性识别

对输入内容自动识别每个字段的：

| 识别项 | 说明 | 默认值 |
|-------|------|-------|
| 所属模块 | 原文中的分组标题 / 章节标题 | — |
| 字段名称 | 字段标签文字 | — |
| 字段类型 | 按下方推断规则 | — |
| 是否必填 | `*` 标记或文本"必填"则为是；其余按必填处理 | **必填** |
| 下拉选项 | 单选 / 多选题的所有选项 | — |
| 排序 | 按原文顺序编号 | 按原文顺序 |

### 3.3 类型推断规则

| 表单形式 | 推断类型（API type） |
|---------|----------------|
| 单行输入框 | 单行文本（string_info） |
| 多行输入框 / 文本域 | 多行文本（text_info） |
| 单选按钮组 / 下拉单选 | 单选题（select_info） |
| 复选框组 | 多选题（multi_select_info） |
| 日期选择器（年月日） | 时间选择 - 年月日（day_info） |
| 日期选择器（仅年月） | 时间选择 - 年月（date_info） |
| 开始时间 + 结束时间 | 时间段（date_group_info） |
| 是 / 否 二选一 | 是否题（bool_info） |
| 文件上传 | 文件（file_info / custom_file_upload） |
| 数字输入框 | 数字（number_info） |
| 声明 / 同意 / 协议确认 | 确认题（confirm_info） |
| 签名区域 | 手写签名（signature_info） |

> ⚠️ `day_info` = 年月日精度，`date_info` = 年月精度，命名与直觉相反。

### 3.4 启发式规则

#### 3.4.1 选项补全

字段语义为**离散集合**但原文未列选项时，建议作为选项题并给出常见选项：

| 字段 | 建议类型 | 建议选项 |
|------|---------|---------|
| 性别 | 单选 | 男 / 女 |
| 政治面貌 | 单选 | 群众 / 团员 / 党员 / 民主党派 / 无党派人士 |
| 学历 / 最高学历 | 单选 | 高中 / 中专 / 专科 / 本科 / 硕士 / 博士 |
| 学位 | 单选 | 学士 / 硕士 / 博士 |
| 籍贯 / 城市 / 地点 | 单选（地点选择类型） | — |
| 婚姻状况 | 单选 | 未婚 / 已婚 / 离异 / 丧偶 |

特殊备注列写：「建议改为选项题（原文为文本框）」。

#### 3.4.2 字段拆分

字段名称为「X 及 Y」、「X / Y」组合形式时，建议拆分为两个字段：

| 原字段 | 拆分后 |
|------|------|
| 紧急联系人及电话 | 紧急联系人 + 紧急联系人电话 |
| 起止日期 / 在职时间 | 开始时间 + 结束时间 |
| 学校及专业 | 学校 + 专业 |
| 部门及职位 | 部门 + 职位 |

特殊备注列写：「拆分自原表 X」。

#### 3.4.3 必填默认

原文未标注 `*` 或「必填」时，**默认必填**。在第 5 步会显式提醒用户。

---

## 第 4 步：智能匹配

对解析出的每个字段（含拆分后的子字段），按以下顺序匹配：

### 4.1 匹配优先级

| 顺序 | 判定 | 分类 |
|------|------|------|
| 1 | 标准字段池中**精确名称命中**（`labelZh` 或 `synonyms` 中含完全相等项） | 完全匹配 |
| 2 | 标准字段池中 **synonyms 模糊命中**（含义相近） | 智能匹配 |
| 3 | `customFields[]` 中**精确名称命中**（`name` 完全相等） | 完全匹配 |
| 4 | `customFields[]` 中**含义相近**（同义词、缩写、上下位词等） | 智能匹配 |
| 5 | 全部失败 | 待创建 |

> 智能匹配时（顺序 2 / 4），特殊备注列必须写出**匹配依据**，例如
> 「原表『政治背景』→ 系统标准字段『政治面貌』，含义一致」。

### 4.2 冲突处理规则

| 冲突类型 | 处理 | 特殊备注写法 |
|---------|------|------------|
| 字段名命中但**类型不一致** | 优先采用系统已有字段类型 | 「已采用系统类型 <type>」 |
| 原文模块名 ≠ 系统标准模块名，但字段命中 | 按系统标准模块归属 | 「按系统模块归属（原表归在 X，系统归在 Y）」 |
| 字段含离散集合语义但原文未列选项 | 建议作为选项题 | 「建议改为选项题（原文为文本框）」 |
| 字段名是组合形式 | 建议拆分（见 §3.4.2） | 「拆分自原表 X」 |
| 字段间存在条件依赖（如「是否 X」→「X 详情」） | 建议联动（见第 7 步） | 「触发联动 / 被联动」 |

### 4.3 三类分类标签

| 分类 | 判定 |
|------|------|
| **完全匹配** | 字段名 + 类型 + 选项均与系统已有字段一致 |
| **智能匹配** | 字段含义一致但名称、类型或选项有差异（已按系统为准） |
| **待创建** | 系统中无任何匹配，需要新建自定义字段 |

### 4.4 模块归属

- 标准模块：按系统的 10 个标准模块（basicInfo、jobIntention、experienceInfo、
  educationInfo、practiceInfo、projectInfo、languageInfo、selfDescription、
  awardInfo、uploadInfo）归属。
- 自定义模块：在 `customBlocks[]` 中按名称匹配。
- **未匹配自定义模块**：原文出现的模块（如「家庭情况」「应急联系人」）在标准模块和
  customBlocks 中都未命中时，询问用户：

  ```
  原表中存在模块「{模块名}」，系统中未找到对应模块。是否新建该自定义模块？
  - 新建：将按 candidate-field-manage §3.3 创建后继续
  - 不新建：将该模块下的字段合并到 basicInfo 模块
  ```

  用户确认新建后，调用同目录 `candidate-field-manage.md` §3.3，
  并把新模块 ID 追加到 categoryOrder 末尾（缓存层面）。

---

## 第 5 步：输出对照表 + 第 1 次确认

### 5.1 对照表（9 列）

在对话框直接展示以下 markdown 表格，**同时**写入日志（见 §5.4）：

| 模块 | 字段名称 | 字段ID | 字段类型 | 字段性质 | 选项详情 | 是否必填 | 分类 | 特殊备注 |
|------|---------|-------|---------|---------|---------|---------|------|---------|

各列规则：

| 列 | 内容规则 |
|----|---------|
| 模块 | 标准模块用中文（个人信息/教育经历/...）；自定义模块用 `customBlocks[].title` |
| 字段名称 | 最终采用的字段名（智能匹配时用系统名；待创建时用原文名） |
| 字段ID | 完全/智能匹配 → 使用系统字段的 `key`（标准）或数字 `id`（自定义）；**待创建 → 留空** |
| 字段类型 | 中文为主、附 API 名，如「单选题(select_info)」 |
| 字段性质 | `标准字段` / `自定义字段` |
| 选项详情 | 已有字段：展示**系统选项**；待创建字段：展示**原文选项**；非选项题：`—` |
| 是否必填 | `是` / `否` |
| 分类 | `完全匹配` / `智能匹配` / `待创建` |
| 特殊备注 | 智能匹配依据、类型/模块冲突说明、拆分说明、联动说明等；无 → `—` |

### 5.2 第 1 次确认提示

对照表后追加以下提示：

```
⚠️ 以下字段默认必填，需调整为非必填请告知：
{自动列出全部默认必填字段}

如需修正：
- 必填项：「第N条改为非必填」
- 字段映射：「第N条用XX字段」「第N条不要拆分」「第N条按原文模块归属」
- 分类：「第N条强制新建」「第N条用智能匹配的XX字段」

确认无误后回复「确认」继续，修正后将重新展示对照表。
```

用户修正 → 重新生成对照表 → 再次确认。

### 5.3 联动初步建议

如第 4 步识别到联动可能（特殊备注含「触发联动 / 被联动」），在对照表下方
追加联动建议小节，**仅展示不询问**（联动详细确认在第 7 步）：

```
🔗 检测到以下潜在联动关系（第 7 步将逐条确认）：
- {主字段} → {被联动字段}（依据：…）
```

### 5.4 日志路径与内容

每次流程开始即创建日志文件：

```
~/.config/cllmk/logs/ats-candidate/apply-form-{slug}-{YYYYMMDD-HHMMSS}.md
```

**slug 规则**：表名中文保留、空格转 `-`、特殊字符（`/\:*?"<>|`）删除。

> ⚠️ 首次运行时，目录可能不存在，需先 `mkdir -p ~/.config/cllmk/logs/ats-candidate/`。

**日志内容结构**：

```markdown
# 登记表创建日志：{表名}
> 生成时间：{YYYY-MM-DD HH:MM:SS}
> orgId：{orgId} / env：{env}
> 模板克隆自 applyFormId：{applyFormId}

## 1. 原始输入摘要
{首 50 行或全部，二选一}

## 2. 对照表（确认前）
{9 列 markdown 表格}

## 3. 对照表（确认后）
{用户修正后的最终版本}

## 4. 联动关系
{联动表格 / 链路图}

## 5. 最终 Payload
```json
{完整 payload}
```

## 6. 接口响应
```
{cllmk 返回原文}
```

## 7. 结果
- 新表 ID：{id}
- 入口 URL：{settings/apply_form 链接}
```

---

## 第 6 步：创建缺失字段（仅当存在「待创建」分类）

### 6.1 处理顺序

1. **新建自定义模块**（如有）：调用同目录 `candidate-field-manage.md` §3.3，
   每个模块创建成功后获取 `customBlocks[].id`，追加到 categoryOrder 缓存末尾。
2. **逐个创建字段**：对每个「待创建」字段调用同目录 `candidate-field-manage.md` §6.1，
   使用对照表中确认的字段名 / 类型 / 选项 / 必填属性。
3. **更新对照表**：每个字段创建成功后，把返回的字段 ID 回填到对照表「字段ID」列，
   分类列改为 `已创建`。

### 6.2 失败处理

任一字段创建失败时**暂停后续步骤**，向用户展示：

```
字段「{字段名}」创建失败：{错误详情}

请决策：
1. 修改后重试（提供新参数）
2. 跳过此字段，继续创建其他字段（此字段不出现在登记表中）
3. 终止流程
```

依用户选择继续。

---

## 第 7 步：联动识别 + 用户确认

### 7.1 主字段类型限制

| 主字段类型 | 是否支持作为联动主字段 |
|----------|-------------------|
| 单选（select_info） | ✅ |
| 多选（multi_select_info） | ✅ |
| 确认题（confirm_info） | ✅ |
| 单行文本（string_info） | ✅ |
| 多行文本（text_info） | ✅ |
| 数字（number_info） | ✅ |
| 是否题（bool_info） | ✅（按 `"1"`/`"0"` 处理）|
| 时间选择 / 时间段 / 地点选择 | ❌ |

### 7.2 被联动字段类型限制

**所有类型**均可作为被联动字段（含时间选择、时间段、地点选择）。

### 7.3 同模块约束

**主字段与被联动字段必须在同一模块**。如识别到跨模块意图，告知用户：

```
检测到跨模块联动：「{主字段}」(模块 {A}) → 「{被联动字段}」(模块 {B})
系统不支持跨模块联动。建议：
1. 将被联动字段移到模块 {A}
2. 取消该联动（两个字段独立显示）

请选择：
```

### 7.4 fieldLinkedType=1 vs fieldLinkedType=2

> ⚠️ 这里的 1/2 是**联动类型** `fieldLinkedType`，与 §2.1 的登记表 `type` 无关，不要混淆。

| `fieldLinkedType` | 含义 | 何时使用 |
|------------------|------|---------|
| **1** | 普通联动：满足条件 → 联动字段显示，**不限制选项** | 大多数场景 |
| **2** | 联动 + 选项过滤：满足条件 → 联动字段显示，**且只展示 `linkedFieldNameDetailList` 里的选项** | 主字段不同值要求被联动字段展示不同选项子集 |

### 7.5 linkedFieldValue 写法

| 主字段类型 | linkedFieldValue 写法 |
|-----------|--------------------|
| 单选（select_info） | 选项文本，如 `"3.0以下"` |
| 多选（multi_select_info） | 每个目标值一条记录（A 一条、B 一条） |
| 确认题（confirm_info） | `"1"` 表示勾选触发 / `"0"` 表示不勾选触发 |
| 是否题（bool_info） | `"1"` / `"0"` |
| 单行文本 / 多行文本 / 数字 | `""`（空字符串，"有值即联动"） |

### 7.6 多层联动

**A → B → C** 链式联动通过多条 fieldLinkedList 记录串联，每跳必须满足同模块约束。

```
ASCII 链路图（向用户展示用）：

  ┌────────────┐    A/B    ┌────────────┐  选项 X   ┌────────────┐
  │ 主字段 A   │──────────▶│ 被联动 B   │──────────▶│ 被联动 C   │
  │ (多选)     │           │ (单选)     │           │ (文本)     │
  └────────────┘           └────────────┘           └────────────┘
                            (同时也是)
                            (下一跳的主字段)
```

### 7.7 联动确认提示

```
🔗 联动关系最终列表：

| # | 模块 | 主字段 | 触发条件 | 被联动字段 | 类型 | 选项过滤 |
|---|------|-------|---------|----------|------|---------|
| 1 | basicInfo | 是否在本公司有亲属 | 勾选 | 亲属姓名及部门 | type=1 | — |
| 2 | 128081 | 等级（多选） | 包含 A | 首次添加人 | type=2 | Mikey, Vivian |
| 3 | 128081 | 等级（多选） | 包含 B | 首次添加人 | type=2 | Eric |
| 4 | 128081 | 首次添加人 | = Mikey | 信息记录 | type=1 | — |

如需修正：
- 取消第N条
- 修改第N条的触发条件 / 类型 / 过滤选项

确认无误后回复「确认」继续。
```

---

## 第 8 步：第 2 次最终确认

在拼装最终 payload 前，复述以下信息：

```
📋 登记表「{表名}」创建预检：

【表名】{用户指定的表名}
【克隆自模板】applyFormId={applyFormId}（{基模板名称}）
【启用模块】{N} 个：{模块名列表}
【字段总数】{N} 个（完全匹配 {a} / 智能匹配 {b} / 新建 {c}）
【必填字段】共 {N} 个：
  - {模块A}.{字段1}
  - {模块A}.{字段2}
  - ...
【联动关系】共 {N} 条（详见第 7 步）
{仅更新场景额外补一行}
【联动合并】保留旧联动 {X} 条 + 本次新增 {Y} 条 = save 将下发 {Z} 条（默认保留全部旧联动；如需清空请显式说明）

请确认上述全部信息无误。回复「确认」/「执行」/「ok」/「是」继续创建。
```

仅当用户回复明确确认指令时进入第 9 步；否则等待用户修正。

---

## 第 9 步：拼装 setting JSON 与调用接口

### 9.1 setting 结构

setting 对象包含：

```
{
  "categoryOrder": [...],           // 模块顺序，复用基模板
  "<blockId>": { ... },             // 每个模块的配置（按三态规则）
  ...
}
```

#### 9.1.1 categoryOrder 来源

直接复用 `apply_form_info.applyForm[0].setting.categoryOrder`，并补齐两类模块：

- 租户已有的**自定义模块**（`customBlocks[].id`，字符串形式）追加到末尾
- 系统的 `offerInfo` 模块若基模板未包含，也补到末尾

> 不在 categoryOrder 中的模块即使 setting 里写了配置也不会展示。

#### 9.1.2 模块对象三态写法

| 状态 | 写法 |
|------|------|
| **启用** | `{show:true, isSelected:[...], isRequired:[...], fieldOrder:[全量]}`，多段模块（experienceInfo/educationInfo/practiceInfo/projectInfo/languageInfo/awardInfo）额外加 `required:true` |
| **不启用 + 标准模块** | `{show:false, isSelected:[], isRequired:[], fieldOrder:[全量]}` |
| **不启用 + 自定义模块** | **省略**（不写入 setting）|

#### 9.1.3 fieldOrder 来源

每个模块的 fieldOrder 复用 `apply_form_info.applyForm[0].setting[blockId].fieldOrder`：

- 本次新建的自定义字段追加到末尾
- **被联动字段在 fieldOrder 末尾按它在 `fieldLinkedList` 中出现的总次数重复写入**（UI 副产品；按此格式写最稳妥，与 §9.4 顺序规则配合）

#### 9.1.4 isSelected / isRequired

- `isSelected`：本登记表实际勾选展示的字段集合（key 字符串 或 数字 id 混排，按基模板的格式照搬）。
- `isRequired`：isSelected 中标必填的子集。

### 9.2 顶层 payload 字段

| 字段 | 值 |
|------|---|
| `name` | 用户指定表名 |
| `setting` | 上述 setting 对象的 `JSON.stringify` 字符串 |
| `displayName` | `""` |
| `displayNameVisible` | `0` |
| `type` | 新建自定义表传 `0`；**更新 type=1/2/3 的系统表时回传原值**（见 §2.1） |
| `departmentId` | `null` |
| `departmentName` | `null` |
| `locales` | `'["default"]'`（字符串） |
| `hireMode` | `1` |
| `isOptimizedDeptIds` | `false` |
| `departmentIds` | `[]` |
| `departmentNameList` | `[]` |
| `enableOffer` | `true` |
| `applyFormId` | `apply_form_info.applyForm[0].id` |
| `fieldLinkageMode` | `0`（默认联动，引用字段自身 linkage）或 `1`（自定义联动，由本表 fieldLinkedList 定义） |
| `fieldDetailList` | 见 §9.3.1 |
| `fieldLinkedList` | 见 §9.3.2；UI 顺序受 §9.4 约束 |
| `id`（仅 PUT） | 当前表 ID |

### 9.3 联动数据结构（fieldDetailList + fieldLinkedList）

#### 9.3.1 fieldDetailList — 主字段元信息

每个**主字段一条**记录（即 `fieldLinkedList[].fieldNameId` 去重后），不包含被联动字段：

```json
{
  "blockId": "<主字段所在模块ID>",
  "fieldNameId": <主字段ID>,
  "detail": "",
  "formDimensionType": 2,
  "supplementaryLocales": {}
}
```

无联动时传 `[]`，且**不需要** `formDimensionType`。

#### 9.3.2 fieldLinkedList — 联动规则

每条联动一条记录：

```json
{
  "blockId": "<模块ID>",
  "fieldLinkedType": 1,
  "fieldNameId": <主字段ID 数字>,
  "linkedBlockId": "<同 blockId>",
  "linkedFieldNameId": <被联动字段ID 数字>,
  "linkedFieldValue": "<主字段的某个具体值>",
  "linkedFieldNameDetailList": ["..."]
}
```

- `fieldLinkedType`：1 = 普通联动（默认，可省略）；2 = 联动 + 选项过滤，仅 type=2 才传 `linkedFieldNameDetailList`
- `linkedFieldValue` 写法见 §7.5（按主字段类型）
- **多值场景**：一个 "主→被联动" 对若有 N 个触发值，拆为 N 条记录，每条一个 `linkedFieldValue`

### 9.4 联动顺序规则（控制 UI 显示）

被联动字段在 UI 中的渲染顺序由 **`fieldLinkedList` 中相关条目的相对顺序**决定。

排序原则：

1. **按目标显示顺序分组**：同一被联动字段（`linkedFieldNameId` 相同）的多条记录视为一组，**组之间的相对顺序**决定 UI 上字段的显示顺序。
2. **同组内多条值记录的顺序**不影响显示（同一字段只渲染一个控件，仅触发条件不同）。
3. **`setting.<blockId>.fieldOrder` 末尾**：被联动字段按它在 `fieldLinkedList` 中出现的总次数重复写入，相对顺序与 `fieldLinkedList` 中组的顺序一致。

> 当主字段被某个具体值命中时，会同时触发多组联动，**这些被联动字段按 fieldLinkedList 中各组首次出现的位置先后渲染**。

### 9.5 调用流程（两段式 + 校验）

联动数据**和字段级说明（fieldDetailList）必须通过 `extend-info/save` 接口持久化**，仅靠 `apply-form` 接口不会生效。

> ⚠️ **fieldDetailList 也必须独立调 save**（实测）：即使本次没有任何联动（`fieldLinkedList=[]`），只要存在字段说明（如 educationInfo.Country 的 "Choose the country..." 描述），仍必须调一次 `extend-info/save`，否则 `query/config` 回读 fieldDetailList 为空。
> 触发 save 的判定：`len(fieldLinkedList) > 0 OR len(fieldDetailList) > 0`。

| # | 接口 | 用途 |
|---|------|------|
| 1 | `POST /api/outer/ats-candidate/apply-form/apply-form`（更新时 `PUT`） | 创建/更新表本体（setting / fieldLinkageMode） |
| 2 | `POST /api/outer/ats-candidate/apply-form/extend-info/save` | **持久化联动数据**（必做） |
| 3 | `POST /api/outer/ats-candidate/apply-form/extend-info/query/config` | 回读校验（可选） |

#### 9.5.1 apply-form payload（POST 创建 / PUT 更新）

按 §9.2 顶层字段表传：
- `setting`（JSON.stringify 字符串，含 §9.1 的 categoryOrder + 三态模块对象）
- `applyFormId`：创建时 = 基模板 ID；更新时 = 当前表 ID
- `fieldLinkageMode`：`0` = 默认联动（引用字段自身 linkage 配置）；`1` = 自定义联动
- `fieldDetailList` / `fieldLinkedList`：按 §9.3 结构带上（与 save 接口同构，作为 UI 状态冗余）

更新时 payload 顶层多一个 `id` 字段（= 当前表 ID）。

#### 9.5.2 extend-info/save payload

```json
{
  "applyFormId": <表ID>,
  "type": 1,
  "fieldLinkageMode": 1,
  "fieldLinkedList": [/* §9.3.2 结构，按 §9.4 排序 */],
  "fieldDetailList": [
    {
      "blockId": "<主字段所在模块ID>",
      "fieldNameId": "<主字段ID 字符串>",
      "detail": "",
      "formDimensionType": 2,
      "supplementaryLocales": "{}"
    }
  ]
}
```

**关键字段差异**（save 相对 apply-form）：

| 字段 | apply-form | save |
|------|-----------|------|
| `fieldDetailList[].fieldNameId` | 数字或字符串均可 | **字符串** |
| `fieldDetailList[].supplementaryLocales` | 对象 `{}` | **字符串** `"{}"` |
| 顶层 `type` | 不传 | **必传 `1`** |
| 顶层 `id` / `name` / `setting` 等表元信息 | 必传 | 不传 |

> ⚠️ 即便 apply-form 已经带了 `fieldLinkedList`，**也必须再调一次 save** 接口联动数据才会生效；这是后端的实际行为。
>
> 🚨 **save 是 REPLACE 语义，不是 MERGE**（更新场景的高危陷阱）：
>
> - 服务端会**整体替换** `fieldLinkedList`。本次未带的旧联动**全部丢失**，且无法从 `apply_form_info` 反查恢复。
> - `fieldDetailList` 服务端会做一定保留（实测覆盖后仍能看到旧主字段残留），**不可依赖**作为旧联动还在的证据。
> - **正确做法**：更新现有表时，按 §2 在 save 前先 `extend-info/query/config` 拿 `oldFieldLinkedList`，与新构造的 `newFieldLinkedList` 合并后整体下发：
>
>   ```
>   merged = preserve_old(oldFieldLinkedList) ⊕ new_to_add
>   ```
>
>   合并时按 §9.4 顺序约束排（同被联动字段记录连续；组的先后顺序决定 UI 渲染顺序）。
> - **第 8 步最终确认**中，必须明确告知用户：「本次 save 将携带 X 条旧联动 + Y 条新联动 = Z 条」，避免无声丢失。
> - 如果**就是要清空全部旧联动**（少见），需要用户在第 8 步显式声明「不保留旧联动」，否则**默认保留**。

#### 9.5.3 query/config 回读校验

```bash
cllmk curl --url "/api/outer/ats-candidate/apply-form/extend-info/query/config" \
  --method POST --payload '{"ids":[<表ID>],"type":1}'
```

返回 `data.applyFormExtendInfoList[]`，含本表的 `fieldLinkageMode` / `fieldDetailList` / `fieldLinkedList`。

#### 9.5.4 调用示例

```bash
# 1. 创建/更新表
cllmk curl --url "/api/outer/ats-candidate/apply-form/apply-form" \
  --method POST --payload '<apply-form 完整 payload>'

# 2. 写入联动（关键）
cllmk curl --url "/api/outer/ats-candidate/apply-form/extend-info/save" \
  --method POST --payload '<save 完整 payload>'

# 3. 校验（可选）
cllmk curl --url "/api/outer/ats-candidate/apply-form/extend-info/query/config" \
  --method POST --payload '{"ids":[<表ID>],"type":1}'
```

### 9.6 调用前最后展示

把两段 payload（格式化缩进）展示给用户，重申当前会话信息：

```
即将执行（两段）：
  1. POST /api/outer/ats-candidate/apply-form/apply-form
  2. POST /api/outer/ats-candidate/apply-form/extend-info/save
当前会话：{system} / {env} / {orgName}
表名：{name}

请求 Payload [apply-form]：
{完整 JSON，缩进 2 空格}

请求 Payload [save]：
{完整 JSON，缩进 2 空格}

确认执行？
```

确认后按 §9.5.4 顺序调用，每一步成功后再进入下一步；失败则停在该步报错。

---

## 第 10 步：响应处理

### 10.1 分步处理规则

| 步骤 | 失败时 |
|------|-------|
| apply-form 失败 | 不调用 save；展示错误，让用户决定回退或修正后重试 |
| apply-form 成功、save 失败 | 表已创建/更新但联动未生效；明确告知用户当前状态，并提供「重试 save」或「保留无联动版本」两个选项 |
| save 成功 | 可调用 §9.5.3 query/config 回读校验；展示入口 URL；补齐日志 |

### 10.2 通用错误码

| 响应 | 处理 |
|------|------|
| 成功（code:0） | 展示新表 ID 与入口 URL（`{env URL}/settings/apply_form`），把日志 §7 节补齐 |
| HTTP 401 / 403 | 执行 `cllmk auth status` 重新验证；session 失效则引导重新登录；写入日志 |
| HTTP 4xx 其他 | 展示错误详情，提示检查参数（字段名重复、模块 ID 非法、setting JSON 错误等）；写入日志 |
| HTTP 5xx | 提示服务端错误，建议稍后重试；写入日志 |
| `Not logged in` | 引导用户重新登录 |

入口 URL 按 env 选择：

| env | URL |
|-----|-----|
| cn | https://app.mokahr.com/settings/apply_form |
| intl | https://hire-r1.mokahr.com/settings/apply_form |
| s3 | https://staging-3.mokahr.com/settings/apply_form |

---

## 完整交互示例

**场景：用户提供 md 描述的入职登记表，自动生成系统登记表**

```
用户：帮我把这份登记表配置到系统里
      [输入：md 片段，含 8 个字段]
      ## 个人信息
      - 姓名 *
      - 联系电话 *
      - 性别（男/女）*
      - 最高学历 *
      - 政治背景
      - 是否有海外留学经历
        - 若有，请填写留学国家/地区
      - 紧急联系人及电话 *

系统：[加载上下文：org/info、apply_form_info、CDN 标准字段池]
      [创建日志文件 <log-path>]

      已识别 8 个字段（含拆分），对照表如下：

| 模块 | 字段名称 | 字段ID | 字段类型 | 字段性质 | 选项详情 | 是否必填 | 分类 | 特殊备注 |
|------|---------|-------|---------|---------|---------|---------|------|---------|
| 个人信息 | 姓名 | name | 单行文本(string_info) | 标准字段 | — | 是 | 完全匹配 | — |
| 个人信息 | 手机号 | phone | 单行文本(string_info) | 标准字段 | — | 是 | 智能匹配 | 原表「联系电话」→ 系统标准字段「手机号」 |
| 个人信息 | 性别 | gender | 单选题(select_info) | 标准字段 | 男/女 | 是 | 完全匹配 | — |
| 个人信息 | 最高学历 | academicDegree | 单选题(select_info) | 标准字段 | 高中/中专/专科/本科/硕士/博士 | 是 | 智能匹配 | 原文未列选项，按系统选项 |
| 个人信息 | 政治面貌 | political | 单选题(select_info) | 标准字段 | 群众/团员/党员/民主党派/无党派人士 | 否 | 智能匹配 | 原表「政治背景」→ 系统「政治面貌」 |
| 个人信息 | 是否有海外留学经历 | — | 是否题(bool_info) | 自定义字段 | — | 否 | 待创建 | 触发联动 |
| 个人信息 | 留学国家/地区 | — | 单行文本(string_info) | 自定义字段 | — | 否 | 待创建 | 被联动（「是否有海外留学经历」=是 时显示） |
| 个人信息 | 紧急联系人 | — | 单行文本(string_info) | 自定义字段 | — | 是 | 待创建 | 拆分自原表「紧急联系人及电话」 |
| 个人信息 | 紧急联系人电话 | — | 单行文本(string_info) | 自定义字段 | — | 是 | 待创建 | 拆分自原表「紧急联系人及电话」 |

      ⚠️ 以下字段默认必填：姓名 / 手机号 / 性别 / 最高学历 / 紧急联系人 / 紧急联系人电话。
      如需修正请告知，确认无误后回复「确认」。

用户：确认

系统：开始创建 4 个待创建字段……
      [按 candidate-field-manage §6.1 逐个创建]
      ✅ 是否有海外留学经历（id=<field-id-1>）
      ✅ 留学国家/地区（id=<field-id-2>）
      ✅ 紧急联系人（id=<field-id-3>）
      ✅ 紧急联系人电话（id=<field-id-4>）

      检测到 1 条联动关系：
      | # | 模块 | 主字段 | 触发条件 | 被联动 | 类型 | 选项过滤 |
      | 1 | basicInfo | 是否有海外留学经历 | =是 | 留学国家/地区 | type=1 | — |

      确认无误？

用户：确认

系统：📋 登记表「入职登记表」创建预检：
      【克隆自模板】applyFormId=<base-form-id>（默认申请表）
      【启用模块】1 个：basicInfo
      【字段总数】9 个（完全匹配 2 / 智能匹配 3 / 新建 4）
      【必填字段】共 6 个：basicInfo.姓名 / basicInfo.手机号 / ...
      【联动】1 条
      确认执行？

用户：确认

系统：[展示两段 payload（apply-form + extend-info/save），再次确认 → 用户确认]
      [1/2] POST /api/outer/ats-candidate/apply-form/apply-form  → ✅ id=<form-id>
      [2/2] POST /api/outer/ats-candidate/apply-form/extend-info/save  → ✅ 1 条联动入库
      [可选] POST /api/outer/ats-candidate/apply-form/extend-info/query/config  → 回读校验通过

      ✅ 登记表「入职登记表」已创建（id=<form-id>）
      入口：<environment-specific-settings-url>
      日志：<log-path>
```

---

## 边界用例

| 用例 | 处理 |
|------|------|
| **模板基底为空** | `apply_form_info.applyForm[]=[]` → 终止流程，提示用户先在后台建默认表（见 §2.2） |
| **所有字段均完全匹配** | 跳过第 6 步（无字段需要创建），直接进入第 7 步 |
| **跨模块联动被识别** | 第 7 步拒绝并提供 2 个备选方案（见 §7.3） |
| **多层联动** | 第 7 步用 ASCII 链路图展示，逐层确认（见 §7.6） |
| **未匹配自定义模块** | 第 4 步询问是否新建（见 §4.4） |
| **字段创建失败** | 第 6 步暂停，3 选 1（见 §6.2） |
| **接口 401/403** | 第 10 步重新鉴权 |
| **更新现有表（含联动）** | 第 2 步**必须**先 `extend-info/query/config` 取旧 `fieldLinkedList`；save 是 REPLACE 语义，未携带的旧联动会**整体丢失**（见 §9.5.2 🚨）；第 8 步要展示「旧 X + 新 Y = Z」的合并预览 |
| **跨租户 JSON 导入（modules 内只有数字 ID）** | 导入用 JSON 的 `modules[].fieldOrder/isSelected/isRequired` 含源租户的 numeric custom field ID 时，本租户对应字段 ID 通常不同，需做名称映射。若 JSON 只把待创建字段挂在 `customFieldsToCreate[]` 而 modules 内未带源 ID↔名称的显式对照，回退到「按 relatedTo 分组 + 按 isSelected 出现顺序与 customFieldsToCreate 顺序对齐」的启发式推断，并在第 5 步对照表的特殊备注列写「跨租户 ID 推断」让用户确认。建议导出脚本未来直接在 modules 内对每个 numeric ID 记录 `{name, relatedTo, type}` 元信息，避免顺序对齐的歧义风险。|

---

## 与 candidate-field-manage 的边界

| 职责 | 归属 |
|------|------|
| 自定义字段创建（API 调用、payload 构造） | **candidate-field-manage §6.1** |
| 自定义模块创建 | **candidate-field-manage §3.3** |
| 字段查询 / 更新 / 停用 / 启用 | **candidate-field-manage §6.2-§6.4** |
| 标准字段匹配 / 智能匹配 / 待创建分类 | **本 reference 第 4 步** |
| 登记表创建（拼装 setting / 调用 apply-form 接口） | **本 reference 第 9 步** |
| 联动关系识别与配置 | **本 reference 第 7、9 步** |
| 对照表与日志输出 | **本 reference 第 5 步** |
