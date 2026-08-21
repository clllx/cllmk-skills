---
route: offer-template-manage
---

# Offer 附件模板管理

覆盖 Moka ATS「设置 → Offer 附件模板设置」（`/settings/offer_template`）下**上传型**
Offer 附件模板的查询、创建与编辑：生成带占位符的 docx、上传解析、保存模板、回读对账，
以及电子签开关与附件标题变量。

> ⚠️ **本文所有字段 ID、模板 ID、`ossKey` 均为示例。** 它们都是租户内标识，必须在目标
> 租户现查现用，禁止跨租户复用或从本文照抄。

## 目录

- 第 1 步：前置检查（鉴权、hireMode、cllmk 版本）
- 第 2 步：判断操作类型
- 第 3 步：模板形态识别
- 第 4 步：占位符规则
- 第 5 步：生成模板文件
- 第 6 步：接口调用
- 第 7 步：附件标题
- 第 8 步：电子签
- 第 9 步：调用前确认
- 第 10 步：响应处理与回读对账
- 安全约束
- 附录 A：端点清单
- 附录 B：标准变量枚举表
- 附录 C：未覆盖形态（禁止写入）

---

## 第 1 步：前置检查（鉴权、hireMode、cllmk 版本）

执行前须已通过 `<skill-dir>/SKILL.md` 的「业务公共前置」，确认
`data.system === "ats"`。会话异常时按
`<skill-dir>/references/foundation/auth.md` 的对应分支处理。

### 1.1 cllmk 版本硬门槛

**本文的创建流程要求 `cllmk >= 0.4.0`**，原因有两条，缺一不可：

```bash
cllmk --version
```

| 依赖 | 为什么必须 |
|---|---|
| `curl --form` | `office_template/offer/upload` 是 `multipart/form-data`，`--payload` 只能发 JSON，低版本**根本发不出上传请求** |
| 响应 UTF-8 修复 | ≤0.3.0 逐 chunk 解码，多字节字符跨 chunk 边界会变 U+FFFD。占位符校验要比对**中文字段名**，读坏了会误判成「字段名不符」并诱导改错占位符 |

版本低于 0.4.0 时**停止创建流程**，按 `<skill-dir>/references/foundation/install.md`
引导升级。只做查询（第 6 步 §6.1）时 0.3.0 可用，但仍要向用户提示中文可能损坏。

### 1.2 hireMode 探测

**Offer 附件模板按 hireMode 分身**，社招/校招各有独立的模板列表：

```bash
cllmk curl --url "/api/v2/org/info" --method GET --filter currentUserInfo
```

读 `data.currentUserInfo.currentHireMode`（1=社招 / 2=校招）与 `availableHireModes`，
向用户明示。与目标不一致时**停止，不得自动切换**——hireMode 是服务端会话状态，只能由
用户在 Web 端切换。`save` payload 顶层的 `hireMode` 必须与会话一致；不一致时下发**未实测**，
属附录 C 禁止项。

**hireMode 影响三处，必须一起对齐**：

| 位置 | 社招 | 校招 |
|---|---|---|
| `save` payload 顶层 `hireMode` | `1` | `2` |
| `upload` 表单 `type` / `officeTemplate.type` | `1` | `2` |
| 模板列表 | 只返回社招模板 | 只返回校招模板 |

**校招的 Offer 附件模板是完全独立的一套**，社招会话下既看不到也建不了校招模板。用户
要配校招模板时先确认会话已切到校招，否则会把模板建到社招下（服务端不会拦，见 §6.2）。

> `cllmk curl` 不发送浏览器那个 `moka-tracing` 头（其中含 `scenario: social|campus`）。
> 实测不带该头也能正常读写——**hireMode 完全由服务端会话决定**，不要试图靠请求头切换场景。

> 🚨 **hireMode 是共享的服务端状态，会在任务执行途中被外部改变。** 用户在 Web 端切一次
> 招聘场景，同一账号的 cllmk 会话**立即**跟着变，不需要重新登录、也不换租户。
>
> 实测到的后果：任务开始时 `currentHireMode:1` 读到 128 个 Offer 字段，用户在浏览器切到
> 校招后，同一条命令只读到 24 个字段且 **ID 集合与之前几乎不相交**，模板列表也整个换了一批。
> 此时若拿着先前社招的字段 ID 去生成占位符，校验会报「字段 ID 不存在」——真实原因是
> 场景变了，不是 ID 错了。
>
> 因此：**每个写请求前重新断言 `currentHireMode`**，不要复用任务开头那次探测结果；
> 中途发现与预期不符时停止并告知用户，不要自动适配到新场景。跨越多次交互的长任务
> （生成 → 校验 → 上传 → 保存）尤其要在 `save` 前再确认一次。
>
> 这与 `cllmk` current 指针被并发改动是同类问题，但更隐蔽——current 是本地状态，
> hireMode 是服务端状态，连切租户都不需要。

---

## 第 2 步：判断操作类型

| 触发关键词 | 操作 |
|----------|------|
| 查询 / 看看 / 列出 / 有哪些模板 | **查询** → 第 6 步 §6.1 |
| 新建 / 添加 / 创建 / 上传模板 | **新建** → 第 3 步 |
| **只改名字**（不动文件、标题、部门、电子签） | **改名** → 第 6 步 §6.5（用 `updateName`，**不换 ID**） |
| 换文件 / 改标题 / 改部门 / 开关电子签 | **编辑** → 第 6 步 §6.4（先读 §6.3 的换 ID 警告） |
| 生成模板文件 / 做一份 offer 附件 | **只生成 docx** → 第 5 步，生成后交用户上传或继续第 6 步 |
| 删除模板 | **删除** → 第 6 步 §6.6（不可逆，逐条确认） |
| 设为默认 / 换默认模板 | **设默认** → 第 6 步 §6.7（单选，自动取消旧默认） |

> ⚠️ **「改名」和「编辑」要分开判断。** 只改名字走 §6.5 的 `updateName`（ID 不变）；
> 一旦涉及文件/标题/部门/电子签就得走 §6.4 的全量 `save`，**模板 ID 会变**。
> 用户说「改一下模板」时先问清改哪部分，别默认走 `save`。

业务顺序固定：**先生成模板文件，再上传，最后保存模板**。不要反过来先建模板再补文件。

---

## 第 3 步：模板形态识别

模板有两种形态，混在同一个列表里，靠**独占键**区分：

| 形态 | 独占键 | `screenshot` | 支持电子签 | 本文覆盖 |
|---|---|---|---|---|
| **上传型**（docx） | `officeTemplateId` / `officeTemplate`（内含 `type`：社招 1 / 校招 2） | `/images/file_types/doc.svg` | ✅ | ✅ 全流程 |
| **在线编辑型** | `draftTemplateId` / `draftTemplate`（`content` 是 draft-js JSON） | CDN 截图 png | ❌ | 仅识别与读取 |

判定用键的**存在性**，不要用 `screenshot` 猜——它只是派生展示值。

UI 上「添加模板」第一步就要选「在线编辑」或「上传模板文件」，且弹窗明确写了**只有
「上传模板文件」支持电子签**。用户要电子签时必须走上传型。

在线编辑型的创建流程**未覆盖**（缺 curl，`draftTemplate.content` 是 draft-js 富文本
结构）。用户要求新建在线编辑型模板时停止，说明只支持上传型，或请用户提供 UI curl。

> ⚠️ **详情接口不返回 `templateName`**。模板名在 `officeTemplate.name`
> （或 `draftTemplate.name`），列表接口的 `templateName` 是列表侧自己拼的。
> `save` 时模板名也写在 `officeTemplate.name`，不是顶层。

---

## 第 4 步：占位符规则

### 4.1 判据：是否落在标准变量枚举里

占位符带不带字段 ID，判据是**名称是否在附录 B 的 37 项标准变量枚举里**：

| 情况 | 写法 |
|---|---|
| 在枚举里 | `{名称}` |
| 不在枚举里的任何 Offer 字段 | `{名称[字段id]}` |

> 🚨 **判据不是「标准字段 vs 自定义字段」，也不是 Offer 字段的 `isBuiltin` /
> `builtinType`。** 实测反例：某租户字段「工作地点」`builtinType:"office_address"` 但
> `isBuiltin:false`，占位符是 `{工作地点[<该字段ID>]}`；而「offer职位」`isBuiltin:true`
> 因为在枚举里，写 `{offer职位}`。`builtinType` 非空却 `isBuiltin:false` 的字段（入职日期、
> 员工类型、薪资计划项等）**全都要带 ID**。

同名不冲突：枚举里的「入职地点」写 `{入职地点}`，租户里另一个同名自定义字段写
`{入职地点[<该字段ID>]}`，两者可在同一文档共存。

### 4.2 空格必须编码成 `%20`

> 🚨 **字段名里的空格在占位符里要写 `%20`。** 实测：某字段接口返回
> `name:"转正后基本工资 Q1"`（真实空格），UI「查看字段」给出的占位符是
> `{转正后基本工资%20Q1[<该字段ID>]}`。旁证：前端 bundle 里公司签署人的英文占位符
> 是硬编码常量 `"Company%20Signatory1"`。

规则细节：

- **只有空格被编码**。全角/半角括号、斜杠、连字符、中文标点一律原样——所以**不是**
  `urllib.parse.quote` / `encodeURIComponent`。
- 连续空格逐个转：`A  B` → `A%20%20B`。
- 影响面不小：实测某租户 119 个可用字段里 25 个含空格（21%）。

⏳ 未实测：直接写空格是否也被接受（`occurrences` 不校验所以测不出来，要发真 Offer 才知道）；
全角空格 / tab 如何处理；字段名里字面 `%` 是否需要转义。一律按 `%20` 规则生成，不要赌。

### 4.3 不能作为占位符的字段类型

Offer 字段中 `type` 属于 **5 / 8 / 11 / 12** 的不能作占位符，实测被 UI 从清单里排除：

| type | 含义 |
|---|---|
| 5 | 附件发送开关（发送附件给审批人 / 给候选人） |
| 8 | 招聘需求 |
| 11 | 附件 |
| 12 | 人员选择 |

其余 type（1/2/3/4/6/7/9/10）可用。`isVisible:false` 的隐藏字段**仍可写占位符**
（合法但值可能为空），生成时提示用户。

### 4.4 `occurrences` 不做有效性校验

> 🚨 **`upload` 返回的 `info.occurrences` 只是机械提取文档里所有 `{...}`，不做任何
> 有效性校验。** 实测：漏写 `[id]` 的自定义字段（`{Offer的单行文本}`）和根本不存在的
> 字段名（`{这个字段不存在}`）都照样计入 occurrences。
>
> 所以 **「上传成功 + occurrences 有条目」不等于变量能被替换**。合法性只能本地校验，
> 见第 5 步 §5.2。

`occurrences` 仍有两个正当用途：

1. 反查「文档里实际写了哪些花括号」，与预期清单对账。
2. 发现 `occurrences` 为 `{}` 或缺项 → 说明占位符被 Word/WPS **拆进了多个 run**
   （实测见过上传成功但 `occurrences:{}` 的模板）。

### 4.5 正文变量 ≠ 附件标题变量

两处可选变量不同，不要互相套用：

| | 文档正文（「查看字段」弹窗） | 附件标题（`attachmentTitle`） |
|---|---|---|
| 实测项数 | 163 | 161 |
| 前端注入变量 | 10 项（含**职位描述**） | 9 项（**不含**职位描述） |
| 派生变量 | 入职部门路径 | 入职部门路径 |
| Offer 字段 | 排除 type 5/8/11/12 | 同样排除 |
| 同名字段 | **不去重**（`{入职地点}` 与 `{入职地点[id]}` 并存） | **按名称去重**，被去掉的那个无法用作标题变量 |
| 签署类变量 | 不在列表里但**可用**（见 §8） | 不适用 |

> ⚠️ **「查看字段」弹窗不是可用变量的完备清单。** 6 个签署区变量不在其中，但实测确实
> 可用（电子签模板的 occurrences 里有并已落库）。所以「某变量不在弹窗里」推不出
> 「不可用」——附录 B 的 3 个学历类变量就属于「枚举里有、UI 列表里没有、可用性未知」。

---

## 第 5 步：生成模板文件

### 5.1 生成 docx

> 🚨 **占位符必须整体落在同一个 Word run 里**，否则服务端提取不到。手写或从
> Word/WPS 另存的文档常因拼写检查、格式残留把 `{候选人姓名}` 拆成多个 run，表现是上传
> 成功但 `occurrences` 缺项甚至为 `{}`。

用脚本生成可规避该问题，并自动完成 §4.2 的空格编码：

```bash
uv run --with python-docx python3 \
  <skill-dir>/scripts/offer-template/build_offer_docx.py \
  --spec body.md --out offer.docx
```

`body.md` 用最小 Markdown 子集（`#`/`##`/`###` 标题、`-` 列表、普通段落）。占位符按
自然名称写即可，脚本负责编码：

```markdown
# 录用通知书

尊敬的 {候选人姓名}：

我们诚挚邀请您加入 {公司名称}，担任 {offer职位} 一职。

- 入职部门：{入职部门}
- 薪资待遇：{薪资待遇}

年假天数：{Annual Leave[123456]}
```

脚本输出改写后的占位符清单（如 `Annual%20Leave[123456]`），用于人工核对。

**需要页眉页脚、图片、复杂排版、盖章位的正式文书时脚本不够用**——`build_offer_docx.py`
只做纯文本段落。此时让用户提供已排版的 docx，生成步骤跳过，但 §5.2 的校验**不能跳过**。

### 5.2 校验占位符（不可跳过）

```bash
uv run --with python-docx python3 \
  <skill-dir>/scripts/offer-template/validate_placeholders.py \
  --docx offer.docx --template-type 0
```

脚本按附录 B 枚举表 + 实时字段清单逐个判定，输出 JSON；有非法项时 `ok:false` 且退出码 1。
它能识别并给出修正建议的问题：

| 判定 `kind` | 含义 |
|---|---|
| `standard` | 合法标准变量（学历类 / 签署类会带 `note` 提示） |
| `custom` | 合法自定义字段占位符 |
| `missing_field_id` | 名称匹配到字段但漏了 `[id]`，note 里给出正确写法 |
| `custom` + `valid:false` | 空格未编码 / ID 与名称不符 / ID 不存在 / type 不可用 |
| `unknown` | 既不是标准变量也不匹配任何字段名——**服务端不会拒绝，但不会被替换** |

离线校验（复现问题、或不想实时打接口）可先存字段清单再 `--fields-json` 传入。

**校验不通过时不要上传。** 上传本身会成功，问题会推迟到发 Offer 时才暴露。

---

## 第 6 步：接口调用

三段式，注意**跨两个服务层**，成功判定方式不同：

| 步 | 端点 | 层 | 成功判定 |
|---|---|---|---|
| 1 | `POST /api/office_template/offer/upload` | node | HTTP 状态码；cllmk 外层 `code:0` |
| 2 | `POST /api/outer/ats-offer/template/save` | java（`use-http-status:0`） | 外层 `code:0` **且**内层 `data.success:true` |
| 3 | `POST /api/outer/ats-offer/template/getOfferTemplateById` | java | 同上 |

### 6.1 查询现有模板

```bash
cllmk curl \
  --url "/api/outer/ats-offer/template/listOfferTemplatesPermission" \
  --method POST --payload '{}'
```

> 端点名里的 `Permission` 是前端拼接的 scene 后缀（`"listOfferTemplates".concat(scene)`）。
> 不带后缀的 `listOfferTemplates` 返回**完全一致**。同理，Offer 字段接口在前端被调用为
> `listCustomFieldsByOrgIdPermission77`，那个 `77` 是调用方硬编码的垃圾，实测带与不带
> 返回一致——**本文一律用不带多余后缀的规范名**。`{"scene":"Permission"}` 可传可不传。

列表项键：`id`、`templateName`、`creatorName`、`templateType`、`isDefault`、
`isOptimizedDeptIds`、`label`、`screenshot`、`version`，加上形态独占的
`officeTemplateId` 或 `draftTemplateId`。

单条详情：

```bash
cllmk curl \
  --url "/api/outer/ats-offer/template/getOfferTemplateById" \
  --method POST --payload '{"id":"<模板ID>"}'
```

`id` 传**字符串**。详情键见 §6.5。

### 6.2 上传模板文件

```bash
cllmk curl \
  --url "/api/office_template/offer/upload" \
  --form "template=@<docx路径>;filename=<上报的文件名>.docx" \
  --form 'type=1' \
  --form 'requireNoRevisions=true'
```

| 表单字段 | 值 | 说明 |
|---|---|---|
| `template` | 文件 | `;filename=` 覆盖上报名（会成为模板的 `filename`）；不传则用路径 basename |
| `type` | **`1`=社招 / `2`=校招** | 必须与 §1.2 的 `currentHireMode` 对应，见下方警告 |
| `requireNoRevisions` | `true` | 要求文档无修订痕迹；有修订痕迹的用户文档会被拒 |

> 🚨 **`type` 按 hireMode 取值，不是固定 1**：社招 `hireMode:1` → `type:1`，
> 校招 `hireMode:2` → `type:2`。该值会原样进入 `officeTemplate.type`（§6.3）。
>
> **服务端不校验 `type`，原样回显**（实测：社招会话下传 `type=2` 照样返回 200 且
> `type:2`）。传错不会报错，问题会推迟到模板实际使用时才暴露——和 `occurrences`
> 不校验是同类陷阱。生成 payload 前必须按会话 `currentHireMode` 显式推导 `type`，
> 不要沿用样例里的 `1`。

`--form` 时 method 默认 POST，无需显式 `--method`。

响应 `data`（**下一步 save 要原样带走大部分**）：

```json
{
  "orgId": "<当前租户>",
  "ossKey": "<服务端生成>",
  "filename": "<上报的文件名>.docx",
  "filesize": 37134,
  "type": 1,
  "info": {
    "properties": {"application": "..."},
    "errorCode": 0,
    "errorMessage": "",
    "occurrences": {"候选人姓名": 1, "Annual%20Leave[123456]": 1},
    "schema": 1
  },
  "creatorId": 500123
}
```

拿到响应后**立即对账 `occurrences`** 与第 5 步的预期清单：条数一致、逐项一致。
不一致说明占位符被拆 run（§4.4），修文档重新上传，不要往下走。

同时检查 `info.errorCode`：非 0 时展示 `errorMessage` 并停止。

### 6.3 保存模板

> 🚨 **`save` 带 `id` 不是原地更新，而是版本化替换：服务端建一条新记录并让旧 id 立即
> 失效。** 实测：对 `id=900450` 下发后返回新 id `800120`，再读旧 id 得
> `{"code":300100,"msg":"模版不存在！"}`；`templateVersion` 0 → 1，`officeTemplate.id`
> 也从 610330 换成 620145，只有 `ossKey` 沿用。
>
> **新 id 可能比旧 id 小**（上例 800120 < 900450），所以不能用大小判断新旧。
>
> 后果：`save` 之后如果还要继续操作同一模板，**必须先按 §6.1 用 `templateName`
> 重新查 id**。不要把模板 id 缓存或写进任何交付物。

payload（`id` 缺省 = 新建，带 `id` = 版本化替换）：

```json
{
  "hireMode": 1,
  "officeTemplate": {
    "orgId": "<upload 响应原样>",
    "ossKey": "<upload 响应原样>",
    "filename": "<upload 响应原样>",
    "filesize": 37134,
    "type": 1,
    "info": "<upload 响应的 info 整体原样，含 occurrences>",
    "creatorId": "<upload 响应原样>",
    "name": "<模板名称，由用户给定>"
  },
  "isOptimizedDeptIds": true,
  "departmentIds": [],
  "templateType": 0,
  "attachmentTitle": { "见第 7 步": "" }
}
```

| 键 | 必填 | 说明 |
|---|---|---|
| `hireMode` | ✅ | 与会话 `currentHireMode` 一致（§1.2） |
| `officeTemplate` | ✅ | 上传响应 + `name`。**模板名在这里，不在顶层** |
| `officeTemplate.type` | ✅ | 社招 `1` / 校招 `2`，与顶层 `hireMode` 对齐（§6.2） |
| `officeTemplate.info` | ✅ | upload 返回的 `info` **整体原样回传**，不要重算 occurrences |
| `isOptimizedDeptIds` | ✅ | 实测一律 `true` |
| `departmentIds` | ✅ | `[]` = 不限部门；限定时传部门 ID 数组（§6.9） |
| `templateType` | ✅ | 电子签开关，见第 8 步。不支持电子签也要显式给 `0` |
| `attachmentTitle` | ✅ | 见第 7 步 |
| `id` | 编辑时 | **带上就会换 id**，见上方警告 |

成功响应：

```json
{"code":0,"data":{"code":0,"codeType":0,"data":{"id":"900450","version":"1.0"},"msg":"成功","success":true},"msg":""}
```

新 id 在**内层** `data.data.id`，是**字符串**。

### 6.4 编辑已有模板

1. 按 §6.1 用 `templateName` 查到当前 id，读详情拿到完整对象。
2. 判形态（§3）：`draftTemplateId` 型停止，本文不覆盖其编辑。
3. 在详情基础上构造 §6.3 的 payload，**只改要改的键**，`id` 用刚查到的值。
   - 只换文件：重跑 §6.2 拿新 `ossKey`/`filesize`/`info`，`name` 沿用。
   - 改标题/改部门/开关电子签：`officeTemplate` 整体沿用详情里的值（去掉服务端
     派生键，见 §6.8），只改目标键。
   - **只改名字不要走这里**——用 §6.5 的 `updateName`，模板 ID 不变。
4. 下发后**必须**按 §6.1 重新查 id（§6.3 警告），再回读校验。

`save` 是 REPLACE 还是 PATCH **未实测**——由于它整体重建记录，一律按 REPLACE 处理：
所有必填键都要给全，缺键的后果未知。

### 6.5 只改名字：用 `updateName`，不要用 `save`

```bash
cllmk curl \
  --url "/api/outer/ats-offer/template/updateName" \
  --method POST --payload '{"id":<模板ID数字>,"name":"<新名称>"}'
```

`id` 是**数字**，不是字符串（与 `getOfferTemplateById` 相反）。

> ✅ **`updateName` 不换 ID，也不递增 `templateVersion`**（实测：改名后 id 不变、
> `templateVersion` 仍为 0、名称已生效）。**这是它与 §6.4 全量 `save` 的关键差别**——
> 只改名字时一律走本端点，不要走 `save`，否则会白白换掉模板 ID。

实测对两种形态都适用（在线编辑型模板改名成功）。改的是模板名，不影响
`attachmentTitle`、部门范围、`templateType` 或模板文件。

### 6.6 删除模板

```bash
cllmk curl \
  --url "/api/outer/ats-offer/template/delete" \
  --method POST --payload '{"id":<模板ID数字>}'
```

`id` 是**数字**。成功响应内层为 `{"value": true, "version": "1.0"}`。

> 🚨 **删除不可逆，且没有 dry-run。** 执行前必须：
> 1. 按 §6.1 现查 id 并向用户展示 `templateName` + `creatorName` + `isDefault`，
>    确认是同一条模板（模板 ID 会因 `save` 变化，缓存的 id 可能指向别的模板）。
> 2. 让用户逐条明确确认。**批量删除必须逐条确认，不接受「全删」这类指令。**
> 3. `isDefault:true` 的默认模板删除后果**未实测**——遇到时停止，要求用户先改默认模板。

删除后该 id 回读返回 `300100 模版不存在！`，列表里消失。

> ⚠️ `ossKey` 指向的 OSS 对象**不随模板删除**（实测：复用已删模板的 `ossKey` 重新
> `save` 仍能成功建出模板）。所以删模板不等于删文件，也没有清理 OSS 的端点；
> 反复上传只会累积孤儿对象。

### 6.7 设为默认模板

```bash
cllmk curl \
  --url "/api/outer/ats-offer/template/updateDefault" \
  --method POST --payload '{"id":<模板ID数字>}'
```

`id` 是**数字**。成功响应内层为 `{"value": true, "version": "1.0"}`。

> ✅ **默认模板是单选，切换即自动取消旧默认**（实测：把默认从 A 切到 B 后，A 的
> `isDefault` 由 `true` 变 `false`，B 变 `true`，全列表始终恰好一个 `isDefault:true`）。
> **不需要先取消旧默认**，也没有「取消默认」的操作——只能把默认转移给另一个模板。

> ✅ **不换模板 ID**（与 §6.5 `updateName` 一致，与 §6.3 `save` 相反）。

默认状态按 hireMode 各自独立：社招和校招各有一个默认模板。切换前按 §6.1 查当前默认并
向用户展示「从 {旧默认} 改为 {新默认}」，默认模板影响发 Offer 时的预选项，属业务可感知变更。

### 6.8 服务端派生键（回传时去掉）

详情里这些键由服务端生成，**构造 save payload 时不要下发**：

| 位置 | 键 |
|---|---|
| 顶层 | `officeTemplateId`、`templateVersion`、`label`、`isLatest`、`isDeleted`、`isDefault`、`otherInfo`、`orgId`、`version` |
| `officeTemplate` | `id`、`screenshot`、`version`、`downloadUrl` |

`label` 是毫秒时间戳字符串，`otherInfo` 实测恒为 `{}`（用途未知，不要往里塞东西）。

### 6.9 部门范围

`departmentIds: []` = 不限部门（实测多个模板如此）。要限定时先查部门树：

```bash
cllmk curl \
  --url "/api/outer/ats-warden-search/departments/detail" \
  --method POST \
  --payload '{"departmentIdList":[0],"orgId":"<current orgId>","valueMode":1,"filterAuthority":false}'
```

`departmentIdList:[0]` 返回根节点，`directChildren` 是直属子部门 ID 数组，
`subTreeCount` 是子树规模。逐层下钻取目标部门 ID。

⏳ 未实测：`departmentIds` 非空时是否需要同时包含父部门；`isOptimizedDeptIds` 为
`false` 时语义如何变化（实测样本全为 `true`）。

---

## 第 7 步：附件标题

`attachmentTitle` 是发 Offer 时**附件的标题**，三个键必须互相自洽：

```json
{
  "text": "的录用通知函",
  "variables": [
    {"name": "候选人姓名", "position": 0},
    {"name": "公司名称",   "position": 1}
  ],
  "editorStateContent": "{\"blocks\":[{\"key\":\"e2e001\",\"text\":\"候选人姓名的公司名称录用通知函\",\"type\":\"unstyled\",\"depth\":0,\"inlineStyleRanges\":[],\"entityRanges\":[{\"offset\":0,\"length\":5,\"key\":0},{\"offset\":6,\"length\":4,\"key\":1}],\"data\":{}}],\"entityMap\":{\"0\":{\"type\":\"VARIABLE\",\"mutability\":\"IMMUTABLE\",\"data\":{\"name\":\"候选人姓名\"}},\"1\":{\"type\":\"VARIABLE\",\"mutability\":\"IMMUTABLE\",\"data\":{\"name\":\"公司名称\"}}}}"
}
```

上例渲染为「{候选人姓名}的{公司名称}录用通知函」。

| 键 | 构造规则 |
|---|---|
| `text` | 抠掉**所有变量**后剩下的静态文本 |
| `variables[].name` | 变量名，必须是 §4.5 表里附件标题允许的那一组（9 项注入 + 入职部门路径 + 去重后的字段） |
| `variables[].position` | 该变量在 **`text`** 中的插入下标 |
| `editorStateContent` | draft-js 序列化**字符串**（不是对象）。`blocks[0].text` 是变量名**展开后**的完整串，`entityRanges` 按展开串标注每个变量占的 `offset`/`length`，`entityMap` 给出变量名 |

> ✅ **`position` 是 `text` 中的插入下标，不是展开串的下标**（实测确认）。样本：某模板
> `text:"录取通知函_"`（长度 6）配 `[{候选人姓名,position:0},{Offer生成日期,position:6}]`
> —— `position:6` 即插在 `text` 末尾。若按展开串计，第二个变量应是 11 而非 6。
>
> **多个变量可以有相同 `position`**，此时按 `variables` 数组顺序依次插入。样本：某模板
> `text:"录取通知书"`（长度 5）配 10 个变量全部 `position:5`。

> 🚨 **服务端原样回存 `attachmentTitle`，不校验三键是否自洽**（实测：下发即回读一致）。
> 三键算错不会报错，会在发 Offer 时得到错乱的附件名。生成后自行校验：
> 按 `text` + `variables` 重建展开串，必须与 `editorStateContent.blocks[0].text` 相等。

`entityRanges[].length` 用**变量名的字符长度**（如「候选人姓名」= 5）。`key` 是
`entityMap` 的键（字符串数字），从 `"0"` 开始。`blocks[0].key` 可以是任意短串。

---

## 第 8 步：电子签

「是否支持电子签」在 payload 里就是顶层 **`templateType`**，没有独立布尔键，也不在
`otherInfo` 里：

| `templateType` | 枚举名 | 含义 |
|---|---|---|
| 0 | `NORMAL` | 不支持电子签 |
| 1 | `ELECTRON` | 支持（国内电子签） |
| 2 | `AWS_ELECTRON` | 支持（Adobe） |
| 3 | `AWS_ELECTRON_DOCUSIGN` | 支持（Docusign） |

选 1 还是 2/3 由 org 配置 `awsElectronicSignVendor` 决定（为空走 1）；租户是否开通看
`enable_electronic_sign`。**用户未明确说走哪个厂商时不要猜**，问清楚或让用户在 UI 上确认。

硬约束：

- 该项在 UI 上是必填单选、默认「不支持」，所以 `templateType` **始终要显式给**。
- 只有上传型支持电子签（§3）。
- `templateType != 0` 时 payload **没有任何额外键**——实测一条 `templateType:1` 的真实
  请求与 `templateType:0` 的键集合完全一致。签署顺序（`1=企业先签 / 2=候选人先签`）和
  印章属于「电子签设置 / 授权印章管理」全局配置，不在模板 payload 里。

签署位置靠 docx 占位符表达，均在附录 B 枚举内故**不带字段 ID**：

| 用途 | 占位符 |
|---|---|
| 候选人签署 | `{个人签署区}` |
| 企业签署（按需选一或多个） | `{公章签署区}`、`{人事章签署区}`、`{人名章签署区}`、`{合同章签署区}`、`{法人章签署区}` |
| 签署人/时间/文本 | 见附录 B 签署类 |

- 支持电子签时文档里**必须**有 `{个人签署区}`，否则候选人无处签署。
  `validate_placeholders.py --template-type 1` 会检查这一点。
- 企业签署另需在「授权印章管理」配置对应印章，本文不覆盖该配置。
- `templateType:0` 却写了签署类占位符时，这些变量不生效——校验脚本会给出警告。

---

## 第 9 步：调用前确认

写操作执行前展示完整信息并获得用户确认：

```
即将执行（{新建模板 / 编辑模板}）：

接口：POST /api/office_template/offer/upload  →  POST /api/outer/ats-offer/template/save
当前会话：{system} / {env} / {orgName} / hireMode={1社招|2校招}
cllmk 版本：{version}（>=0.4.0）

模板名称：{name}
使用部门：{不限部门 | 部门名(id) 列表}
电子签：{不支持(0) | 国内(1) | Adobe(2) | Docusign(3)}
模板文件：{路径}（{filesize} 字节）
附件标题：{按 text+variables 重建的渲染结果}

占位符清单（{n} 项，校验全部通过）：
  {候选人姓名}                     标准变量
  {Annual%20Leave[123456]}         自定义字段「Annual Leave」
  ...

编辑时额外提示：
  ⚠️ 保存后模板 ID 会从 {旧id} 变成新 ID，旧 ID 立即失效。

确认执行？
```

额外要求：

- **占位符清单必须逐项展示判定结果**，含标准/自定义归属与字段 ID 对应的字段名。
- 含学历类变量（附录 B）时**必须**明示「该变量可用性未经实测」。
- 编辑操作**必须**明示换 id。
- `occurrences` 与预期不一致时不要进入确认环节，先修文档。

用户回复「确认」「可以」「执行」「ok」「是」等明确指令才继续。

---

## 第 10 步：响应处理与回读对账

`save` / 详情响应经 cllmk 后是双层：

```json
{"code":0,"data":{"code":0,"codeType":0,"data":<业务数据>,"msg":"成功","success":true},"msg":""}
```

> 🚨 外层 `code` 是 **cllmk 自己的包装**，不代表业务成功。必须再查内层
> `data.success === true` 且 `data.code == 0`。

| 情况 | 处理 |
|---|---|
| 外层 `code:0` + 内层 `success:true` | 成功，取内层 `data.data.id`（字符串） |
| 外层 `code:0` + 内层 `success:false` | **业务失败**，展示内层 `msg`，不要报告成功 |
| 内层 `code:300100` / `msg:"模版不存在！"` | **两种原因同码**：① 模板 ID 因 `save` 换掉了（§6.3）；② 模板已被删除（§6.6）。按 §6.1 查列表区分——`templateName` 还在就是换了 ID，不在就是被删了。**不要**默认是前者就去重查重试 |
| `upload` 返回 HTTP 500 | 检查是否真的用了 `--form`；JSON body 打这个端点必 500 |
| HTTP 401 / 403 | 跑 `cllmk auth status` 复验；失效则按 `foundation/auth.md` 重新登录 |
| 其他 4xx | 展示错误详情，检查 `hireMode` 与会话是否一致、`departmentIds` 是否合法 |
| 5xx | 服务端错误，建议稍后重试，**不要自动重试写操作**（重试会再建一条新记录） |

创建/编辑成功后按 §6.1 + 详情回读，逐项对账：

| 对账项 | 期望 |
|---|---|
| `officeTemplate.name` | 等于下发的模板名 |
| `templateType` | 等于下发值 |
| `hireMode` | 等于下发值 |
| `departmentIds` | 等于下发值 |
| `officeTemplate.ossKey` / `filesize` / `filename` | 等于 upload 响应 |
| `officeTemplate.info.occurrences` | 与 upload 响应逐项一致 |
| `attachmentTitle` | 三键与下发一致 |
| `templateVersion` | 新建为 `0`；编辑后递增 |
| `isLatest` | `true` |

回读时**数字/字符串差异属正常**（`save` 返回的 id 是字符串 `"900450"`，详情里是数字
`900450`）。报不一致前先怀疑比对代码。

---

## 安全约束

- **禁止**把 `cllmk` 外层 `code:0` 当成业务成功；只认内层 `data.success` / `data.code`。
- **禁止**把 `save` 的响应体当写入结论；必须按 §6.1 重查 id 再 `getOfferTemplateById` 回读。
- **禁止**把 `occurrences` 有条目当成占位符生效；必须先跑 `validate_placeholders.py`（§4.4、§5.2）。
- **禁止**在 `cllmk < 0.4.0` 时执行创建流程（§1.1）。
- **禁止**照抄历史 curl 或本文样例里的模板 ID、`officeTemplateId`、`ossKey`、字段 ID、
  `creatorId`；一律运行时获取。模板 ID 还会因 `save` 而变（§6.3）。
- **禁止**在 `hireMode` 与会话 `currentHireMode` 不一致时下发（§1.2）。
- **禁止**复用任务开头那次 `currentHireMode` 探测结果；每个写请求前重新断言——用户在
  Web 端切场景会立即改变同一会话的 hireMode（§1.2）。
- **禁止**沿用样例里的 `type:1`；`upload` 表单与 `officeTemplate.type` 必须按会话
  hireMode 推导（社招 1 / 校招 2）。**服务端不校验该值**，传错不报错（§6.2）。
- **禁止**用 `save` 实现「只改名字」——那会换掉模板 ID；改名一律走 `updateName`（§6.5）。
- **禁止**批量或无逐条确认地执行 `delete`；删除不可逆且无 dry-run（§6.6）。
- **禁止**静默切换默认模板；`updateDefault` 会自动取消旧默认，切换前必须展示
  「从 {旧默认} 改为 {新默认}」并获确认（§6.7）。
- **禁止**把 `300100 模版不存在！` 直接当成「ID 变了」——它也可能是模板已被删除（第 10 步）。
- **禁止**在未核实部门 ID 存在性时写 `departmentIds`（§6.9）。
- **禁止**对 5xx 自动重试写操作——`save` 每次调用都可能新建一条记录，重试会产生重复模板。
- **禁止**在未向用户明示「模板 ID 将失效」时执行编辑（§6.3、第 9 步）。
- **禁止**把学历类 3 项变量当已验证能力使用（附录 B.3）。
- **禁止**展示或记录 Cookie 明文（`moka-jwt` / `moka-uid` 等）。用户贴带 `-b` 的 curl 时
  提醒其去掉 Cookie 段，并改用 `cllmk curl` 复现。

---

## 附录 A：端点清单

| 操作 | 端点 | payload | 状态 |
|---|---|---|---|
| 上传 docx | `POST /api/office_template/offer/upload` | multipart：`template` / `type=1` / `requireNoRevisions=true` | ✅ 实测 |
| 保存模板 | `POST /api/outer/ats-offer/template/save` | 见 §6.3 | ✅ 实测（新建与带 id 均验证） |
| 查详情 | `POST /api/outer/ats-offer/template/getOfferTemplateById` | `{"id":"<字符串>"}` | ✅ 实测 |
| 查列表 | `POST /api/outer/ats-offer/template/listOfferTemplates[scene]` | `{}` 或 `{"scene":"Permission"}` | ✅ 实测 |
| 查 Offer 字段 | `POST /api/outer/ats-offer/customFields/listCustomFieldsByOrgIdPermission` | `{}` | ✅ 实测（详见 `offer-field-manage.md`） |
| 查部门树 | `POST /api/outer/ats-warden-search/departments/detail` | 见 §6.9 | ✅ 实测 |
| 删除模板 | `POST /api/outer/ats-offer/template/delete` | `{"id":<数字>}` | ✅ 实测（§6.6，不可逆） |
| 单独改名 | `POST /api/outer/ats-offer/template/updateName` | `{"id":<数字>,"name":"..."}` | ✅ 实测（§6.5，**不换 ID**） |
| 设为默认 | `POST /api/outer/ats-offer/template/updateDefault` | `{"id":<数字>}` | ✅ 实测（§6.7，单选、**不换 ID**） |
| 更新截图 | `POST /api/outer/ats-offer/template/updateScreenshot` | 未知 | ⛔ 附录 C |
| 模板预览 | `POST /api/outer/ats-offer/template/preview` | `{id, outputType}` | ⛔ 附录 C |
| 法人公司列表 | `POST /api/outer/ats-common/flow/electronic/setting/list` | `{applicableDepartmentId}` | ⛔ 附录 C |
| 检查印章 | `POST /api/outer/ats-common/flow/corporation/seal/checkSeal` | 未知 | ⛔ 附录 C |
| 校验用户绑定电子签 | `POST /api/outer/pa-sign/electronicSign/check` | `{}` | ⛔ 附录 C |

`upload` 之外全部走 `/api/outer/`，全部为 `POST`。

---

## 附录 B：标准变量枚举表

37 项。**在这张表里的写 `{名称}`，不在的 Offer 字段写 `{名称[字段id]}`**（§4.1）。
机器可读副本在 `<skill-dir>/scripts/offer-template/placeholder_spec.py`，两处必须同步。

### B.1 业务常用（17 项，已确认可用）

| 变量 | 变量 | 变量 |
|---|---|---|
| 候选人姓名 | 创建人姓名 | 预计入职时间 |
| 候选人身份证 | 创建人手机号 | offer职位 |
| 候选人手机号 | 创建人邮箱 | 薪资待遇 |
| 候选人邮箱 | Offer生成日期 | 入职地点 |
| 职位描述 | 公司名称 | 职位级别 |
| | | 入职部门 |
| | | 入职部门路径 |

### B.2 电子签签署类（17 项）

个人签署区、公章签署区、人事章签署区、人名章签署区、合同章签署区、法人章签署区、
公司签署人1/2/3、公司签署时间_1/2/3、人选签署时间、个人签署文本字段、
公司签署1/2/3文本字段。

只在 `templateType != 0` 时有意义（第 8 步）。**不出现在 UI「查看字段」列表里，但实测可用。**

### B.3 可用性未知（3 项）

候选人最高学历毕业院校、候选人专业（最高学历）、候选人最高学历。

> ⚠️ 这 3 项在前端枚举表里，但**不在** UI「查看字段」列表中，替换效果**未经实测**。
> `occurrences` 会收录它们，但那不构成证据（§4.4）。使用前必须向用户明示可用性未验证；
> 用户要求确定性时，让用户在 UI 上发一封测试 Offer 验证。

### B.4 表过期时如何重新提取

该表来自前端 bundle，**随前端版本变化**。怀疑过期时：

1. 在已登录的 Moka 页面查 `performance.getEntriesByType('resource')`，找
   `static-ats.mokahr.com/hr-web/javascripts/hrWeb-<ver>-release.js`。
2. 在其中检索 `个人签署区`，命中处即枚举表，形如
   `de.CANDIDATE_NAME,{name:"候选人姓名",translation:"Candidate name"}`。
3. 用 `\b\w{1,3}\.([A-Z][A-Z0-9_]+),\{name:"([^"]*)",translation:"([^"]*)"\}` 抽全表。

不要凭记忆增删这张表。

---

## 附录 C：未覆盖形态（禁止写入）

遇到下列情况时**停止**，说明缺少的 UI curl 或业务信息，不猜测 payload：

| 形态 | 状态 |
|---|---|
| 删除 `isDefault:true` 的默认模板 | 未实测后果（§6.6）；遇到时停止，要求用户先改默认模板 |
| 更新截图（`template/updateScreenshot`） | 端点存在，payload 未实测；上传型模板的 screenshot 是固定图标，用途不明 |
| **模板预览**（`template/preview`） | 实测传 `{id:"<模板ID>", outputType:"pdf"}` 返回 `300639 Template不存在`；正确参数未知 |
| **新建在线编辑型模板** | 缺 curl；`draftTemplate.content` 是 draft-js 富文本结构 |
| **编辑在线编辑型模板** | 同上，本文只覆盖上传型 |
| 电子签的法人公司 / 印章配置 | 端点已知（附录 A）但 payload 与业务规则未实测；属「电子签设置 / 授权印章管理」范围 |
| `templateType` 2 / 3（Adobe / Docusign） | 枚举已知，但无实测样本；下发前让用户确认租户厂商配置 |
| payload `hireMode` 与会话 `currentHireMode` 不一致时下发 | 未实测，禁止；要求用户先在 Web 端切换场景 |
| `save` 是 REPLACE 还是 PATCH | 未实测；按 REPLACE 处理（§6.4） |
| `departmentIds` 非空是否需含父部门 / `isOptimizedDeptIds:false` 的语义 | 未实测（§6.9） |
| 占位符里直接写空格是否也被接受 / 全角空格 / tab / 字面 `%` | 未实测（§4.2）；一律按 `%20` 生成 |
| 学历类 3 项变量的替换效果 | 未实测（附录 B.3） |
| `otherInfo` 的语义 | 实测恒为 `{}`，用途未知，原样保留不解读 |
| Offer 邮件模板 / Offer 审批模板 / Offer 字段与模块 | 不在本文范围；字段与模块见 `offer-field-manage.md` |

> ⚠️ **模板 ID、`officeTemplateId`、`ossKey`、字段 ID 全部是租户内标识，禁止跨租户复用。**
> 每次操作前按 §6.1 / §5.2 现查现用。模板 ID 还会因 `save` 而变（§6.3），连同租户内
> 也不能缓存。
