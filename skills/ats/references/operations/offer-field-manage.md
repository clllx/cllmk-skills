---
route: offer-field-manage
---

# Offer 字段与模块管理

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

覆盖 Moka ATS「设置 → Offer 自定义字段」（`/settings/offer_custom_field`）下的
Offer 字段查询、创建、更新、隐藏/显示，Offer 模块（分组）的查询、创建、改名，
以及字段选项级联动关系的查询与写入。

## 目录

- 第 1 步：前置鉴权与 hireMode 探测
- 第 2 步：判断操作类型
- 第 3 步：模块归属
- 第 4 步：字段类型与参数
- 第 5 步：接口调用
- 第 6 步：联动关系
- 第 7 步：调用前确认
- 第 8 步：响应处理
- 附录 A：端点清单
- 附录 B：查询接口能力对比
- 附录 C：未覆盖形态

---

## 第 1 步：前置鉴权与 hireMode 探测

执行前须已通过 `<skill-dir>/SKILL.md` 的「业务公共前置」，确认
`data.system === "ats"`。会话异常时按
`<skill-dir>/references/foundation/auth.md` 的对应分支处理。

**Offer 字段按 hireMode 分身**，且社招/校招各有独立的模块与字段。操作前必须探测：

```bash
cllmk curl --url "/api/v2/org/info" --method GET --filter currentUserInfo
```

读 `data.currentUserInfo.currentHireMode`（1=社招 / 2=校招）与
`availableHireModes`，向用户明示。与目标不一致时**停止，不得自动切换**——
hireMode 是服务端会话状态，只能由用户在 Web 端切换。

> 🚨 **两个 list 接口按会话 hireMode 过滤**（实测）：某租户
> `availableHireModes:[1,2]`、`currentHireMode:1` 时，
> `customFieldGroup/listCustomFieldGroupByOrgId` 只返回 2 个社招模块，
> 而 `searchField/org/get` 露出 4 个（社招 + 校招各 2 个，两两同名）。
>
> 所以**社招会话下拿不到校招的 `groupId`**。用户要求在校招下建字段时，
> 必须先让用户把 Web 端切到校招，不要试图从 `searchField` 反推校招 `groupId`
> 后在社招会话里下发——payload 的 `hireMode` 与会话是否能不一致**未实测**，
> 属于附录 C 的禁止写入项。

---

## 第 2 步：判断操作类型

| 触发关键词 | 操作 |
|----------|------|
| 查询 / 看看 / 列出 / 导出 | **查询** → 第 5 步 §5.1 |
| 创建 / 新增 / 新建 / 添加 | **创建字段** → 第 3 步 |
| 更新 / 修改 / 改名 / 改选项 / 改提示语 / 改权限 | **更新字段** → 第 5 步 §5.5 |
| 隐藏 / 关闭 / 不显示 | **隐藏字段** → 第 5 步 §5.5 |
| 显示 / 打开 / 恢复 | **显示字段** → 第 5 步 §5.5 |
| 新建模块 / 新建分组 | **创建模块** → 第 5 步 §5.2 |
| 模块改名 / 分组改名 | **模块改名** → 第 5 步 §5.3 |
| 联动 / 级联 / 选了 A 就显示 B | **联动** → 第 6 步 |

**「删除字段」「停用字段」不存在**：Offer 字段只能隐藏（`isVisible:false`），
没有 delete 端点，也没有候选人侧那样的 `/status` 停用端点。用户说「删除 Offer 字段」
时，说明只能隐藏，并让用户确认是否接受。

---

## 第 3 步：模块归属

### 3.1 查询现有模块

```bash
cllmk curl \
  --url "/api/outer/ats-offer/customFieldGroup/listCustomFieldGroupByOrgId" \
  --method POST --payload '{}'
```

响应 `data.data[]` 每项：

| 键 | 说明 |
|---|---|
| `id` | 模块 ID，即字段的 `groupId` |
| `nameZh` / `nameEn` | 中英文名称 |
| `hireMode` | 1=社招 / 2=校招（只会返回当前会话对应的那一批） |
| `isBuiltin` | 是否系统内置 |
| `isDefault` | 是否默认模块 |
| `isCheckInTable` | 是否为「offer 阶段信息采集」类模块 |
| `version` | 固定 `"1.0"` |

常见内置模块：`offer详情`（`isDefault:true`）、`offer阶段信息采集`。

### 3.2 归属判断

按名称 trim + 大小写不敏感匹配 `nameZh` / `nameEn`：

| 匹配结果 | 处理 |
|---|---|
| 1 条 | 取其 `id` 作为 `groupId`，继续第 4 步 |
| 多条 | 列出候选（`nameZh` + `id`）让用户选择 |
| 0 条 | 询问「未找到模块【x】，是否新建？」→ §5.2 |

用户未指定模块时，按字段语义推断最可能的模块并向用户确认，不要默认丢进
`isDefault` 模块。

---

## 第 4 步：字段类型与参数

### 4.1 类型枚举（`customFields` 侧）

| type | 自定义字段含义 | 附加参数 | 已实测的 builtin 复用 |
|---|---|---|---|
| 1 | 单行文本 | — | ⚠️ `salary`（薪资待遇）、`job`（offer职位） |
| 2 | 多行文本 | — | 未见 |
| 3 | 是否 | — | 未见 |
| 4 | 时间选择（年/月） | — | 未见 |
| 5 | **未见自定义入口** | — | `internal_attachment`、`addition`（offer 附件）→ 附录 C |
| 6 | 选择题（单选） | `detail` + `codes` | ⚠️ `location`（入职地点）、`hcm_job_department`（入职部门）、`rank`（职位级别） |
| 7 | 时间段（年月 — 年月） | — | 未见 |
| 8 | **未见自定义入口** | — | `hc`（招聘需求）→ 附录 C |
| 9 | 时间选择（年/月/日） | — | ⚠️ `time`（预计入职时间） |
| 10 | 数字 | `attributeRule` | 未见 |
| 11 | 附件 | — | 未见 |
| 12 | 人员单选 | — | 未见 |

> ⚠️ **4 是「年/月」，9 是「年/月/日」**，数值大小与精度无关，注意别写反。
>
> ⚠️ **Offer 字段不支持多选自定义字段。** UI 类型下拉里只有「选择题」（= 单选，
> type 6）。用户要多选时告知不支持，不要猜一个 type。

> 🚨 **`type` 单独不足以判断字段形态，必须 `type` + `isBuiltin` + `builtinType` 三者结合。**
>
> 实测 builtin 字段横跨 **type 1 / 5 / 6 / 8 / 9** 五种，与同 type 的自定义字段混在同一个
> 列表里。例如 `type 1` 既有普通单行文本，也有 `builtinType:"salary"` 的「薪资待遇」和
> `builtinType:"job"` 的「offer职位」；`type 6` 既有普通选择题，也有选项来自其它数据源的
> 引用型字段（入职地点 / 入职部门 / 职位级别）。
>
> 上表「未见」只代表**实测样本里没出现**，不代表该 type 一定没有 builtin。判定必须按实际值
> 走，不能查表：
>
> 1. `isBuiltin:true` → **builtin 字段，禁止写操作**（`update` / 隐藏 / 联动一律停止）。
>    向用户说明该字段由系统维护、可配置项与自定义字段不同，需用户提供对应的 UI curl 才能覆盖。
> 2. `isBuiltin:false` → 按上表「自定义字段含义」处理。
> 3. `isBuiltin` 键缺失 → **按 builtin 保守处理**，不要默认 `false`（§5.1 已说明空值会被省略
>    整个键，缺失不能解释为 `false`）。
>
> builtin 字段的多语言也不可靠：实测其 `supplementaryLocales` 只带
> `{"en-US":{"group":"Offer details"}}` 这类**分组名**而非字段名，照抄回传会写坏数据。

### 4.2 通用参数

| 参数 | 键 | 必填 | 默认 |
|---|---|---|---|
| 字段类型 | `type` | ✅ | — |
| 字段名称 | `name` | ✅ | — |
| 所属模块 | `groupId` | ✅ | — |
| 招聘场景 | `hireMode` | ✅ | 与会话 `currentHireMode` 一致 |
| 必填项 | `isRequired` | ✅ | `false` |
| 必审项 | `reapprovalRequired` | ✅ | `false` |
| 私密 | `isSensitive` | ✅ | `false` |
| 提示语（中） | `fieldTip` | ✅ | `""` |
| 提示语（英） | `fieldTipEn` | ✅ | `""` |
| 特殊角色权限 | `specialRoleAuthority` | ✅ | `enable:false` + 六角色全 `true/true` |
| 多语言 | `supplementaryLocales` | ✅ | `{"zh-CN":{"name":"<字段名>"}}` |
| 选项 ID | `codes` | ✅ | 非选择题也要显式传 `null` |
| 固定值 | `isBuiltin` / `isVisible` | ✅ | `false` / `true` |

> `fieldTip` / `fieldTipEn` 在 **payload 顶层**，不在 `supplementaryLocales` 里。

### 4.3 `specialRoleAuthority`

六个角色键固定：`offerCreator`（offer 创建人）、`offerSharer`（offer 共享人）、
`offerReportChain`（offer 创建人的汇报链）、`jobManager`（职位负责人）、
`jobAssistant`（职位协作人）、`systemSuperAdmin`（默认超级管理员）。

**创建（`save`）时每个角色只传两个键：**

```json
"specialRoleAuthority": {
  "enable": true,
  "offerCreator":     {"visible": true, "editable": true},
  "offerSharer":      {"visible": true, "editable": false},
  "offerReportChain": {"visible": true, "editable": false},
  "jobManager":       {"visible": true, "editable": true},
  "jobAssistant":     {"visible": true, "editable": false},
  "systemSuperAdmin": {"visible": true, "editable": false}
}
```

硬约束：

- `enable:false` 时**仍须传全部六个角色**（UI 一律传 `true/true`），不能省略。
- `visible:false` 时 `editable` 必须为 `false`。

**`actionValue` 是服务端派生的位掩码**（bit0=visible=1，bit1=editable=2）：

| actionValue | visible | editable |
|---|---|---|
| 3 | true | true |
| 1 | true | false |
| 0 | false | false |

- `save` payload **不传** `actionValue`，服务端自己算出来（实测：创建时只给
  `visible`/`editable`，读回来带完整 `actionValue` 且六角色全部自洽）。
- `update` 的两种 payload 形态都带 `actionValue`。以 `visible`/`editable` 为准，
  `actionValue` 自己按上表算，或直接复用 list 读回来的整个
  `specialRoleAuthority` 对象。
- **实测见过前端下发 `{"actionValue":1,"editable":true,"visible":true}` 的自相矛盾
  状态**，服务端按 `visible`/`editable` 归一化了。生成 payload 时不要照抄可能滞后
  的 `actionValue`；发现读回来的值与 `visible`/`editable` 不自洽时，按后者重算并
  提示用户。

### 4.4 选择题（type 6）的 `detail` / `codes` / 多语言

三处必须协同，**均为原生 JSON 数组，不是 stringified 字符串**（与候选人
`apply-form` 侧相反，不要照搬那边的序列化规范）：

```json
{
  "detail": ["男", "女", "不愿意透露"],
  "codes":  ["001", "002"],
  "supplementaryLocales": {
    "zh-CN": {"name": "性别", "detail": ["男", "女", "不愿意透露"]},
    "en-US": {"name": "",     "detail": ["M",  "F",  ""]}
  }
}
```

规则：

- `detail` 与 `supplementaryLocales["zh-CN"].detail` **必须一致**（顶层是主语言副本）。
- 其他语言的 `detail` **按下标与 zh-CN 对齐**，缺项用空字符串 `""` 占位（UI 就是这么做的）。
- `en-US.name` 允许缺键或空字符串两种写法，服务端都接受。
- `codes` 未启用时传 `null`；启用时按下标与 `detail` 对齐。

> 🚨 **`codes` 允许短于 `detail`，且服务端会持久化这个错位状态**（实测：
> `detail` 3 项 / `codes` 2 项，写入后读回仍是 2 项，第 3 个选项没有 code）。
> UI 新增选项时会给 `en-US.detail` 补 `""` 占位，但**不会给 `codes` 补**。
>
> 所以**不能照搬候选人侧「codes 数量必须 ≡ detail，不等即阻断」的硬约束**。
> 改为：不阻断，但调用前确认时必须展示完整「选项 ↔ code」对照，把无 code 的项
> 显式标出来让用户确认。`codes` 能否传 `""` 占位**未实测**。

> ⚠️ **顺序错位是高发问题**（实测遇到过 `["男","女"]` 配 `["F","M"]` 和
> `["002","001"]`）。生成 payload 前逐项打印三列对照，让用户核对，不要本地
> 猜测哪个才是对的。

### 4.5 数字（type 10）的 `attributeRule`

```json
"attributeRule": {
  "layout": 0,
  "isSupportNegative": true,
  "decimalLength": "2",
  "numberRange": {"min": "0", "max": "100"}
}
```

| 键 | 说明 |
|---|---|
| `layout` | 格式：`0`=默认 / `1`=百分数 / `2`=千分位（✅ 三值全部实测） |
| `isSupportNegative` | 是否支持负数，布尔，始终传 |
| `decimalLength` | 小数位数，**字符串**。不支持小数时**整个键省略** |
| `numberRange` | `{min, max}`，**字符串**。不限范围时**整个键省略** |

> ⚠️ 关闭 = **省略键**，不是传 `null` 或 `{}`（实测：百分数/千分位两条 payload 的
> `attributeRule` 只有 `layout` + `isSupportNegative` 两个键）。
>
> ⚠️ 生成 payload 时校验语义自洽：`isSupportNegative:true` 配 `numberRange.min:"0"`
> 是矛盾配置（允许负数但下限为 0），发现时提示用户确认。
>
> ⏳ `layout:0` 且三项全关的组合未单独实测，按三者与 `layout` 独立处理。

### 4.6 多语言

- 默认只收集 `zh-CN`。
- 顶层 `name` 与 `supplementaryLocales["zh-CN"].name` 必须一致。
- 用户明确要英文名/英文选项时才写 `en-US`。

---

## 第 5 步：接口调用

### §5.1 查询字段

```bash
cllmk curl \
  --url "/api/outer/ats-offer/customFields/listCustomFieldsByOrgIdPermission" \
  --method POST --payload '{}'
```

响应 `data.data[]`，关键键：

| 键 | 类型 | 说明 |
|---|---|---|
| `id` | number | 字段 ID |
| `name` | string | 字段名（主语言） |
| `type` | number | 见 §4.1 |
| `groupId` / `relatedTo` | number | 模块 ID；`relatedTo` 是 `groupId` 的副本（**int，不是字符串**） |
| `groupNameZh` / `groupNameEn` | string | 模块名 |
| `hireMode` | number | 只返回当前会话对应的那一批 |
| `isBuiltin` / `builtinType` | bool / string | builtin 判定，见 §4.1 |
| `isVisible` | bool | **false = 已隐藏**；隐藏字段仍在此列表中 |
| `isRequired` / `isSensitive` / `reapprovalRequired` | bool | 必填 / 私密 / 必审 |
| `detail` | array | **选项数组**（原生，非 stringified） |
| `codes` | array | 选项 ID，可能短于 `detail` |
| `fieldTip` / `fieldTipEn` | string | 提示语 |
| `specialRoleAuthority` | object | 含 `actionValue` 的完整配置 |
| `attributeRule` | object | 数字规则。非数字字段**实测两种形态都出现过**：返回 `{}`，或整个键缺失（见下方空值规则）。按可选键处理 |
| `supplementaryLocales` | object | 多语言（原生对象） |
| `action` | object | **当前登录人对该字段的权限**，不是配置项，不要与 `specialRoleAuthority` 混用 |
| `fieldDetail` | string | 实测始终为 `""`，用途未知。**选项在 `detail`，不在这里** |
| `localFieldNameList` | array | 各语言名称的集合 |
| `unit` / `defaultValue` / `value` | — | 实测为空 |
| `isPeople` / `isFieldPeople` / `peopleId` / `peopleType` / `peopleBuiltinType` / `isRequiredPeople` | — | People 打通相关，本文不覆盖 |

> 🚨 **值为空时服务端省略整个键**（实测：某租户 20 个字段全部不返回
> `detail`/`codes`/`fieldTip`/`specialRoleAuthority`/`attributeRule`，另一租户配了这些的
> 字段则全部返回）。解析时一律按可选键处理，**键缺失只能解释为「未配置」，
> 不能解释为「接口不支持」**。
>
> 省略并不彻底一致：同一个 `attributeRule`，一个租户全部省略键，另一个租户的非数字字段
> 返回 `{}`。所以**「省略」和「空值」两种形态都要兼容**，不能只处理一种。这条同样适用于
> 响应体本身的内层 `data`（第 8 步、§6.1）。
>
> ⚠️ `localFieldNameList` 的**顺序不固定**，且**可能含空字符串**（实测见过
> `["", "性别"]` 和 `["Previous company rank", "上家公司职级"]`）。不要按下标取
> 中/英文名，改用 `name` 与 `supplementaryLocales`。

### §5.2 创建模块

```bash
cllmk curl \
  --url "/api/outer/ats-offer/customFieldGroup/save" \
  --method POST \
  --payload '{"nameZh":"<中文名>","nameEn":"<英文名>"}'
```

### §5.3 模块改名

```bash
cllmk curl \
  --url "/api/outer/ats-offer/customFieldGroup/update" \
  --method POST \
  --payload '{"id":<模块ID>,"nameZh":"<中文名>","nameEn":"<英文名>"}'
```

`nameZh` / `nameEn` 都要给；只想改中文时把原 `nameEn` 一起回传。

### §5.4 创建字段

**endpoint**：`POST /api/outer/ats-offer/customFields/save`

```json
{
  "type": 6,
  "name": "性别",
  "detail": ["男", "女"],
  "codes": ["001", "002"],
  "isRequired": false,
  "reapprovalRequired": true,
  "isSensitive": true,
  "specialRoleAuthority": { "enable": true, "...": "见 §4.3" },
  "isBuiltin": false,
  "isVisible": true,
  "hireMode": 1,
  "supplementaryLocales": {
    "zh-CN": {"name": "性别", "detail": ["男", "女"]},
    "en-US": {"detail": ["M", "F"]}
  },
  "groupId": "<按 §3.1 现查的模块 ID>",
  "fieldTip": "请选择性别",
  "fieldTipEn": "Please choose gender"
}
```

非选择题去掉 `detail`、`codes` 传 `null`；数字加 `attributeRule`（§4.5）。

> ⚠️ 截图提示：**字段类型创建后无法修改**。类型必须在创建前与用户确认。

### §5.5 更新字段 / 隐藏 / 显示

**endpoint**：`POST /api/outer/ats-offer/customFields/update`（不是 `save` 带 id）

实测该端点接受两种 payload 形态：

| 形态 | 来源 | 键数 | 含 `isVisible` |
|---|---|---|---|
| a 表单精简 | UI 编辑弹窗 | ~13 | ❌ 不含 |
| b 全量回传 | UI 列表页开关 | ~30 | ✅ 含 |

**本 skill 一律用形态 b 的「读—改—写」流程**，不用形态 a：

1. 按 §5.1 读 list，按 `id` 或名称定位目标字段，拿到完整对象。
2. **检查 `isBuiltin`**：为 `true` 或键缺失时**停止写入**，按 §4.1 的三条判定规则向用户
   说明；只有 `isBuiltin:false` 才继续。
3. 在这个对象上**只改要改的键**。
4. 全量下发。

原因：`update` 是 REPLACE 还是 PATCH **未实测**。形态 a 不含 `isVisible`，若是
REPLACE 就会把已隐藏的字段重新显示出来；形态 a 也要求 `fieldTip` /
`specialRoleAuthority`，取不到真实值就会清空。走全量回传，两种语义下都安全。

下发时在读回来的对象上做这些调整（对齐 UI 形态 b）：

- 去掉 `builtinType`
- 加 `value: null`
- 保留 `action`、`attributeRule`、`fieldTip`、`fieldTipEn`、`specialRoleAuthority`、
  `orgId`、`version`、`relatedTo`、`localFieldNameList`、`unit`、`defaultValue`、
  `fieldDetail` 以及全部 `isPeople` / `peopleXxx` 键原样
- **改名时顶层 `name` 与 `supplementaryLocales["zh-CN"].name` 两处都要改**
  （形态 b 的 UI payload 不含顶层 `name`，但 list 返回它；两处都给最安全）

**隐藏 / 显示**：同一端点，只切 `isVisible`。

| 操作 | `isVisible` |
|---|---|
| 隐藏 | `false` |
| 显示 | `true` |

隐藏后字段**仍留在 §5.1 的列表里**（`isVisible:false`），可按名称查到再打开。
这与候选人侧「停用即从 `org/info` 消失」相反。

---

## 第 6 步：联动关系

联动定义在**选项级**：某字段取某个选项值时，联动显示另外一个或多个字段，并可
进一步限定被联动字段的可选项。

### §6.1 读联动

```bash
cllmk curl \
  --url "/api/outer/ats-offer/approval/offer-custom-field-link/listPermission" \
  --method POST
```

无 body（UI 发的是 `Content-Length: 0`）。

> 🚨 **无联动时内层 `data` 键会被整个省略**（实测：响应原文为
> `{"code":0,"data":{"code":0,"codeType":0,"msg":"成功","success":true},"msg":""}`，
> 内层**没有 `data` 键**）。也可能返回 `null`。
>
> 解析必须同时兼容「键缺失」「值为 null」「空数组」三种形态，一律归一为空列表
> （如 `(resp.get("data") or {}).get("data") or []`）。**不要**用「取到 None」推断
> 「值为 null」——这两者在本接口族里是不同的服务端行为，见 §5.1 的空值省略规则。

每条记录：

| 键 | 说明 |
|---|---|
| `id` | 联动记录 ID（= 子项里的 `offerCustomFieldLinkId`） |
| `offerCustomFieldId` | 源字段 ID |
| `offerCustomFieldValue` | 源字段的**选项文案**（不是 code、不是下标） |
| `links[]` | 被联动的目标，见下 |
| `hireMode` / `orgId` / `version` | 归属信息 |

`links[]` 每项：

| 键 | 说明 |
|---|---|
| `linkedId` | 被联动的字段 ID |
| `linkedValues` | 限定的选项文案数组；**`[]` = 只联动字段、不限定选项**（对应 UI 的「设置联动选项」开关关闭） |
| `id` / `createdAt` / `offerCustomFieldLinkId` / `orgId` | 已存在记录才有 |

### §6.2 写联动

```bash
cllmk curl \
  --url "/api/outer/ats-offer/approval/offer-custom-field-link/upsert" \
  --method POST \
  --payload '[{...}, {...}]'
```

payload **顶层是数组**，每个元素是一条「(源字段, 选项值) → links」记录。

- 已存在的记录：把 §6.1 读到的对象原样回传（含 `id` / `hireMode` / `orgId` /
  `version`，`links[]` 里含 `id` / `createdAt` / `offerCustomFieldLinkId`）。
- 新增的记录：只给 `offerCustomFieldId`、`offerCustomFieldValue`、`links`
  （`links[]` 只给 `linkedId` + `linkedValues`）。`orgId` 可省。

> 🚨 **按全量 REPLACE 约束**：UI 每次保存都把该字段**所有选项**的联动一次性下发，
> 包括本次没改动的选项。「缺项是否即删除」**未直接实测**，因此：
>
> - 写入前**必须**先按 §6.1 读全量，在读回来的数组上做增删改，再整体下发。
> - 读不到旧联动（接口报错、返回 `null` 但用户说本来有）时**停止写入**。
>
> 这与仓库里 `apply-form save` 和 `job update customFields` 的 REPLACE 教训同类。

> ⚠️ **`links` 子行会被删除重建**（实测：同一 `(源字段, 选项值, linkedId)` 组合在
> 两次 upsert 前后 `id` 和 `createdAt` 都变了，父记录 `id` 不变）。不要把子行
> `id` 当稳定标识缓存。

> 🚨 **联动以选项文案为 key。改选项文案会打断联动**——`offerCustomFieldValue`
> 和 `linkedValues` 存的都是文案字符串。修改选择题的 `detail` 前必须检查该字段是否
> 有联动，有则同步更新联动记录里的文案，并向用户明示这一风险。多语言租户下用哪个
> 语言的文案**未实测**（样本全是 zh-CN）。

> ⚠️ 一个选项可挂多条 `links`（实测见过同一选项同时联动两个字段，其中一个
> `linkedValues:[]`）。

### §6.3 与字段更新的关系

UI 的顺序是 **先 `customFields/update`（或 `save`）改字段本体，再
`offer-custom-field-link/upsert` 写联动**，两个请求独立。本 skill 沿用该顺序，
并在两步之间向用户报告第一步结果——第一步成功、第二步失败时字段会处于
「选项已改、联动未同步」的中间态，必须显式告知。

---

## 第 7 步：调用前确认

写操作执行前展示完整信息并获得用户确认：

```
即将执行（{创建字段/更新字段/隐藏字段/显示字段/创建模块/模块改名/写联动}）：

接口：POST {接口路径}
当前会话：{system} / {env} / {orgName} / hireMode={1社招|2校招}
所属模块：{nameZh}（id={groupId}）

请求内容：
{完整 JSON payload，格式化缩进}

确认执行？
```

**选择题额外要求**：展示三列对照，无 code 的项显式标出。

```
选项 / code / en-US 对照：
  男          ↔ 001 ↔ M
  女          ↔ 002 ↔ F
  不愿意透露   ↔ （无 code） ↔ （无英文）
  （共 3 项，codes 2 项）
```

**更新字段额外要求**：展示「读回来的值 → 下发的值」差异，只列出真正变化的键。

**写联动额外要求**：展示读回来的全量联动与即将下发的全量联动的完整对比，标出
新增 / 修改 / 消失的记录。**有记录「消失」时必须让用户逐条确认**。

用户回复「确认」「可以」「执行」「ok」「是」等明确指令才继续。

---

## 第 8 步：响应处理

**响应是双层嵌套**：

```json
{"code":0,"data":{"code":0,"codeType":0,"data":<业务数据>,"msg":"成功","success":true},"msg":""}
```

> 🚨 UI 带 `use-http-status: 0`，HTTP 200 也可能是业务失败。**外层 `code == 0`
> 不代表成功**，必须再检查内层 `data.success === true` 且 `data.code == 0`。

> ⚠️ **内层 `data` 键在无数据时会被整个省略**（实测见 §6.1）。判断成功只看
> `success` / `code`，**不要用「内层 `data` 取不到」推断失败**；反过来也不要把
> 「键缺失」写成「值为 null」。

| 情况 | 处理 |
|---|---|
| 外层 `code:0` + 内层 `success:true` | 成功，展示关键结果 |
| 外层 `code:0` + 内层 `success:false` | **业务失败**，展示内层 `msg`，不要报告成功 |
| HTTP 401 / 403 | 跑 `cllmk auth status` 复验；失效则按 `foundation/auth.md` 重新登录 |
| 其他 4xx | 展示错误详情，检查字段名重复、`groupId` 不属于当前 hireMode、类型非法 |
| 5xx | 服务端错误，建议稍后重试，不要自动重试写操作 |

创建成功后按 §5.1 回读校验，**回读时数字/字符串差异属正常**（如 `groupId` 下发
数字、回读数字，但 `decimalLength` 下发字符串），报不一致前先怀疑比对代码。

---

## 附录 A：端点清单

| 操作 | 端点（`/api/outer/ats-offer/` 之后） | payload |
|---|---|---|
| 查字段（含全部配置） | `customFields/listCustomFieldsByOrgIdPermission` | `{}` |
| 查搜索/筛选项 | `searchField/org/get` | 无 body |
| 查模块 | `customFieldGroup/listCustomFieldGroupByOrgId` | `{}` |
| 建模块 | `customFieldGroup/save` | `{nameZh,nameEn}` |
| 模块改名 | `customFieldGroup/update` | `{id,nameZh,nameEn}` |
| 建字段 | `customFields/save` | 见 §5.4 |
| 改字段 / 隐藏 / 显示 | `customFields/update` | 见 §5.5 |
| 查联动 | `approval/offer-custom-field-link/listPermission` | 无 body |
| 写联动 | `approval/offer-custom-field-link/upsert` | 数组，见 §6.2 |

全部为 `POST`。

---

## 附录 B：查询接口能力对比

| | `customFields/list...Permission` | `searchField/org/get` |
|---|---|---|
| 返回内容 | Offer 字段的**完整配置** | Offer 列表的**搜索/筛选项配置** |
| 按会话 hireMode 过滤 | ✅ 过滤（只给当前场景） | ❌ 不过滤（社招 + 校招全量） |
| `isRequired`/`isSensitive`/`reapprovalRequired`/`isVisible` | ✅ | ❌ |
| `codes` | ✅ | ❌ |
| `fieldTip`/`fieldTipEn` | ✅ | ❌ |
| `specialRoleAuthority` | ✅ | ❌ |
| `attributeRule` | ✅ | ❌ |
| `isBuiltin`/`builtinType` | ✅ | ❌ |
| `detail`（选项） | ✅ | ✅ 自定义选择题有；系统枚举项为空 |
| `supplementaryLocales` | ✅ | ✅ |
| 数据来源 | 仅 Offer 字段 | Offer 字段 + **候选人字段** + 系统筛选项 |

`searchField/org/get` 的条目通过 `businessType` 区分来源：

| `businessType` | `key` 形态 | 来源 |
|---|---|---|
| 0 + `group:"default"` | `candidate` / `job` / `jobManager` | 系统筛选项 |
| 0 | 纯数字（= `fieldId`） | **Offer 字段** |
| 1 | `candidate-custom-<id>` / `candidate-system-<name>` | **候选人字段**，不是 Offer 字段 |

> 🚨 **两个接口的 `type` 枚举不可互认**（实测）：
>
> | 字段 | `customFields.type` | `searchField.type` |
> |---|---|---|
> | 自定义选择题 | **6** | **0** |
> | 招聘需求（builtin `hc`） | **8** | **1** |
> | 引用型选择（入职地点/部门/职级） | 6 | 6 |
> | 文本 / 数字 / 年月 / 年月日 / 多行 | 一致 | 一致 |
>
> **判断字段形态只能用 `customFields`。** `searchField` 只用于两件事：查搜索项的
> `enable` 状态，以及在社招会话下确认校招侧存在哪些模块。

---

## 附录 C：未覆盖形态（禁止写入）

遇到下列情况时**停止写入**，说明缺少的 UI curl 或业务信息，不猜测 payload：

| 形态 | 状态 |
|---|---|
| 删除字段 / 停用字段 | **接口不存在**，只能隐藏（§5.5） |
| 多选自定义字段 | **产品不支持**，UI 只有单选「选择题」 |
| **对 `isBuiltin:true` 字段的任何写操作**（改名 / 改选项 / 改权限 / 隐藏 / 挂联动） | 未实测，禁止。builtin 字段横跨 type 1/5/6/8/9，可配置项与自定义字段不同，且多语言只带分组名（§4.1） |
| `isBuiltin` 键缺失的字段 | 按 builtin 保守处理，禁止写入（§4.1） |
| 创建 `type 5` / `type 8` 字段 | 实测只见到 builtin 实例，未见 UI 创建入口 |
| 删除模块 / 模块排序 / 字段排序 | 缺 curl |
| payload 的 `hireMode` 与会话 `currentHireMode` 不一致时下发 | 未实测，禁止；要求用户先在 Web 端切换场景 |
| `codes` 传 `""` 占位 | 未实测 |
| 联动「缺项即删除」 | 未直接实测，按 REPLACE 保守处理（§6.2） |
| 多语言租户下联动用哪个语言的文案 | 未实测，样本全为 zh-CN |
| `customFields/update` 是 REPLACE 还是 PATCH | 未实测，用 §5.5 的全量回传规避 |
| `fieldDetail` / `unit` / `defaultValue` / `value` 的语义 | 实测均为空，用途未知，原样回传不解读 |
| People 打通相关键（`isPeople` / `peopleId` / `peopleType` / `peopleBuiltinType` / `isFieldPeople` / `isRequiredPeople`） | 不覆盖，原样回传 |
| Offer 邮件模板 / 审批流 / 审批模板 | 不在本文范围 |
| 选项设置的「模板导入」（xlsx 下载/上传） | 缺 curl；本 skill 只走 API 直接下发 `detail`/`codes` |

> ⚠️ **字段 ID、模块 ID、`linkedId` 全部是租户内标识，禁止跨租户复用。**
> 每次操作前按 §5.1 / §3.1 现查现用。
