---
route: employee-field-manage
---

# 员工信息设置字段管理

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–8），确认 `data.system === "people"`。

对应页面：设置 → 人事设置 → 员工信息设置（`/setting/staff/staffInfo/*`）

## 目录

- 第 1 步：前置鉴权
- 第 2 步：判断操作类型
- 第 3 步：定位目标（Tab → 分组 → 字段）
- 第 4 步：收集字段参数
- 第 5 步：接口调用
- 第 6 步：调用前确认
- 第 7 步：处理响应
- 不覆盖清单
- 附录 A：字段类型全表
- 附录 B：moduleId 全表
- 附录 C：状态位速查

---

## 第 1 步：前置鉴权

执行前须已通过 `<skill-dir>/SKILL.md` 的「业务公共前置」，确认当前会话 **`data.system === "people"`**。会话是 ATS 时停止，按 `SKILL.md` 业务公共前置第 5 条执行 `cllmk people pp auth login`，用户只在弹出的 Chrome 里完成认证。

> ⚠️ 全文所有接口的成功码是响应体内层 **`code == 200`**，不是 ATS 的 `code == 0`。`cllmk curl` 外层的 `code == 0` 只代表 HTTP 通了。

---

## 第 2 步：判断操作类型

| 触发关键词 | 操作 | 去向 |
|---|---|---|
| 查看 / 查询 / 列出 / 有哪些 / 导出 | **查询** | §5.1 |
| 创建 / 新增 / 新建 / 添加 / 加一个 | **创建** | 第 3 步 → §5.3 |
| 修改 / 更新 / 改名 / 改为 / 变更 / 移动到 | **编辑** | 第 3 步 → §5.4 |
| 停用 / 禁用 / 关闭 / 下线 | **停用** | 第 3 步 → §5.5 |
| 启用 / 开启 / 恢复 / 重新启用 | **启用** | 第 3 步 → §5.6 |
| 删除 / 移除 | **不覆盖** —— 见「不覆盖清单」，提示用户改用停用 | — |

无法判断时询问：「是要新建字段、修改已有字段，还是停用/启用？」

---

## 第 3 步：定位目标

数据是三层结构：**Tab（moduleId）→ 分组（modelId）→ 字段（attrId）**。

### 3.1 确定 Tab → moduleId

用户说的 Tab 名对应固定的 moduleId（**视图键**，见附录 B）：

| Tab | moduleId |
|---|---|
| 个人信息 | 1 |
| 任职信息 | 2 |
| 履历信息 | 3 |
| 合同信息 | 8 |
| 招聘信息 | 9 |
| 兼岗信息 | 14 |
| 其他信息 | 15 |
| 所属成本中心 | 18 |
| 所属项目组 | 68 |

**用户未指定 Tab 时**：不要猜。按字段语义给出建议并确认，例如「建议放在【个人信息 → 基本信息】，确认吗？」用户修正后按修正结果执行。

**用户提到上表之外的模块**（如「绩效字段」「社保字段」「部门字段」）：这些 moduleId 同样能被本接口访问（附录 B 第二部分），但**不属于员工信息设置页**。停下告知用户该模块归属其他设置页，确认是否仍要操作。

### 3.2 查询该 Tab 下的分组与字段

```bash
cllmk curl \
  --url "/api/organization/hr/setting/model/list?bus=20" \
  --method POST \
  --payload '{"loginType":"10","moduleId":<moduleId>}'
```

响应 `data[]` 是分组数组，每个分组含 `id`（= 写接口的 `modelId`）、`title`、`status`、`biz`、`attrs[]`。

> ⚠️ 响应可能很大（绩效模块单次 284 KB / 500 字段）。用 `--filter` 或结构化解析裁剪，不要把整个响应展开给用户。

### 3.3 定位分组（modelId）

在 `data[]` 中按 `title` 匹配（trim + 大小写不敏感）：

| 命中数 | 处理 |
|---|---|
| 0 | 告知「未找到分组【xxx】」，列出该 Tab 下所有**启用**分组供选择 |
| 1 | targetModel = 该分组 |
| 多个 | 列出候选（title + id + status）让用户确认 |

分组 `status`：`0`=系统内置、`1`=启用、`2`=已停用（见附录 C）。**目标分组 `status==2` 时停下**，告知该分组已停用，在其下新建字段不会显示在页面上，确认是否继续。

### 3.4 定位字段（attrId）

编辑 / 停用 / 启用时，在 `targetModel.attrs[]` 中按 `label` 匹配（trim + 大小写不敏感）：

| 命中数 | 处理 |
|---|---|
| 0 | 告知未找到；列出该分组下全部字段（标注启用状态）供选择 |
| 1 | targetAttr = 该字段 |
| 多个 | 列出候选（label + id + type + isLimited）让用户确认 |

> `model/list` **同时返回启用与停用字段**，靠 `isLimited` 区分（附录 C）。不需要额外的筛选参数 —— 实测 `status` / `disabled` / `isEnable` 等 9 个候选参数全部无效。

**跨分组搜索**：用户只给字段名不给分组时，遍历该 Tab 全部分组的 `attrs[]`；仍未命中再遍历其他 Tab（代价较高，先询问用户）。

### 3.5 写前预检（必做）

| 条件 | 处理 |
|---|---|
| `isLimited == 0` 且操作是停用 | **拒绝**，不发请求。提示「【xxx】是系统核心字段，不可停用」 |
| `isLimited == 2` 且操作是停用 | 提示「【xxx】已是停用状态」，不重复发请求 |
| `isLimited == 1` 且操作是启用 | 提示「【xxx】已是启用状态」，不重复发请求 |
| `isRequired == 1` 且操作是停用 | ⚠️ 未完全确认必填字段能否停用。先告知风险并要求用户确认，再发请求；若返回业务错误则按第 7 步处理 |
| `isCanModify == 0` 且操作是编辑 | 提示该字段可能不允许修改，请用户确认后再试 |

---

## 第 4 步：收集字段参数

### 4.1 通用参数

| 参数 | 说明 | 必填 |
|---|---|---|
| 字段名称 | → `label` | ✅ |
| 字段类型 | → `type`，见 §4.2 | ✅（创建时） |
| 所属 Tab / 分组 | → `moduleId` / `modelId`，第 3 步结果 | ✅ |
| 是否必填 | → `isRequired`，0/1，默认 0 | 默认否 |
| 提示文案 | → `tips`，对应列表页「提示」列 | 可选 |
| 是否唯一 | → `isUnique`，0/1，默认 0 | 默认否 |

用户未提及可选项时使用默认值，不要逐项追问。

### 4.2 支持创建的字段类型

| 用户描述 | type | 附加参数 |
|---|---|---|
| 单行文本 / 文本 | `1` | 无 |
| 日期 / 时间 | `2` | 无 |
| 数字 / 数值 | `3` | `options`（单位）+ `unitRequired`，见 §4.3 |
| 是否 / 布尔 / 是非题 | `4` | 无 |
| 单选 / 下拉 | `5` | `values` 选项数组，见 §4.4 |
| 地址 / 省市区 | `6` | 无（服务端生成 `options`） |
| 电话 / 手机号 | `7` | 无（服务端生成 `options`） |
| 附件 / 文件 / 上传 | `8` | 无 |
| 多行文本 / 长文本 | `11` | 无 |
| 证件（组合字段） | `9` | `biz` + `combineInstances`，见 §4.5 |

**上表之外的 type 一律不允许创建**（不在本 skill 覆盖范围）。用户要求建部门选择器、员工选择器、职级、银行卡等类型时，停下说明：这些是系统内置类型或未实证的形态，本 skill 不创建，请在页面手工操作。完整类型清单见附录 A。

> ⚠️ 当前已验证的存量字段样本中未观察到「多选」类型，type 编号未知。用户要求多选时停下确认，不要用 type 5 代替。

### 4.3 数字(3) 的附加参数

```json
"options": "[{\"label\":\"单位\",\"name\":\"unit\",\"value\":\"岁\",\"ref\":\"\"}]",
"unitRequired": 0
```

- `options` 是 **stringified JSON**，必须由客户端构造（与地址/电话相反）。
- `value` 为单位文案；无单位时传空串 `""`。
- `unitRequired` 是数字类型专有的顶层键，默认 0。
- ⚠️ 小数位 / 负数 / 数值范围的键名**未实证**。用户提出这些需求时停下说明，不要猜测键名。

### 4.4 单选(5) 的选项

**创建**时结构极简，`sortNo` 从 1 连续递增：

```json
"options": "",
"values": [
  {"value": "专员", "sortNo": 1},
  {"value": "经理", "sortNo": 2}
]
```

**编辑**时读写结构不对称，规则见 §5.4.2。没有 ATS 那种选项 ID（`codes`）的概念。

### 4.5 证件组合字段(9)

创建前**必须**先读组合类型清单：

```bash
cllmk curl \
  --url "/api/organization/hr/setting/base/combinedField/list?bus=20" \
  --method POST \
  --payload '{"loginType":"10","enabled":true}'
```

从 `combineTypeId == 1939`（certificate/证件）的 `subAttributeList` 取全部启用子属性，按下表映射成 `combineInstances`：

| 清单响应 | payload |
|---|---|
| `subAttributeId` | `combineSubAttributeId` |
| `required` | `required` |
| — | `needFill`（传 `true`） |
| `values[].id` | `values[].valueId` |
| `values[].idx` | `values[].enumId` |
| `values[].value` | `values[].enumValue` |
| `values[].isCanModify`（0/1） | `values[].canModify`（bool） |
| `values[].sortNo` | `values[].sortNo` |
| `values[].valueInitials`（null） | `values[].valueInitials`（`""`） |
| `values[].hot`（null） | `values[].hot`（`false`） |
| — | `values[].enabled`（传 `true`） |

无 `values` 的子属性传 `"values": []`，`"options": ""`。

**银行卡组合字段(40) 不允许创建**（不在本 skill 覆盖范围）：其子属性数量很大，全量 payload 可能达到数百 KB，且创建 body 尚未验证。用户要求时停下说明，请在页面手工操作。

---

## 第 5 步：接口调用

所有接口均为 **POST**，路径带 `?bus=20`，body 均含 `"loginType":"10"`。

> ⚠️ 两套前缀并存，且**不按读写划分**：
> - `/api/organization/hr/setting/*` —— 查询、详情、创建、编辑、组合类型清单
> - `/api/core/v1/field/*` —— 停用、启用

### §5.1 查询

见 §3.2。常见输出形态：

- 「某 Tab 有哪些分组」→ 列 `title` + 启用状态 + 字段数
- 「某分组有哪些字段」→ 列 `label` + 类型名 + 必填 + 启用状态
- 「哪些字段被停用了」→ 过滤 `isLimited == 2`
- 导出报表 → 解析后生成文件，不要把原始 JSON 倒给用户

### §5.2 查询单个字段详情

```bash
cllmk curl \
  --url "/api/organization/hr/setting/field/detail?bus=20" \
  --method POST \
  --payload '{"loginType":"10","attrId":<字段id>}'
```

返回单个 attr 对象，与 `model/list` 的 `attrs[]` 同构，**但补齐了两项列表接口缺失的内容**：

| 键 | model/list | field/detail |
|---|---|---|
| `values`（单选选项） | 恒为 `null` | ✅ 完整选项数组 |
| `combineInstances` | 有 | ✅ 有 |

**编辑前必须调用它**（见 §5.4）。

### §5.3 创建字段

```bash
cllmk curl \
  --url "/api/organization/hr/setting/field/add?bus=20" \
  --method POST \
  --payload '<完整 JSON>'
```

基础 payload（文本 1/11、日期 2、是否 4、地址 6、电话 7、附件 8）：

```json
{
  "loginType": "10",
  "label": "<字段名称>",
  "tips": "<提示文案>",
  "type": <type>,
  "moduleId": <moduleId>,
  "modelId": <modelId>,
  "attrId": null,
  "isRequired": 0,
  "isUnique": 0,
  "options": "",
  "isGroupTitle": 0,
  "applyTargetLibrary": true
}
```

#### 5.3.1 `applyTargetLibrary` —— 固定传 `true` ✅ 语义已确认

**在员工信息字段设置场景下该参数不适用，页面已将其隐藏；接口层面以默认值 `true` 提交，不影响普通字段的行为。**

因此：

- 非组合类型固定传 `true`，无需询问用户，也不必在确认信息中特别说明。
- 组合字段（证件/银行卡）不传该键，与 UI 行为一致。
- 用户主动问起时可如实解释：该参数服务于其他场景，在员工字段设置中被隐藏且无实际作用。

> 确认时间 2026-07-30，来源：Les。此前版本曾要求用户逐次明示取值，语义确认后已放宽。

**各 type 的键集合不同，必须分支构造：**

| 键 | 文本/日期/是否/地址/电话/附件 | 单选(5) | 数字(3) | 证件(9) |
|---|:-:|:-:|:-:|:-:|
| `loginType` `label` `type` `moduleId` `modelId` `attrId` `isRequired` `options` | ✅ | ✅ | ✅ | ✅ |
| `tips` | 可省略 | ✅ | ✅ | ✅ |
| `isUnique` | ✅ | ✅ | ✅ | ❌ **不传** |
| `isGroupTitle` | ✅ | ✅ | ❌ **不传** | ✅ |
| `applyTargetLibrary` | ✅ 固定 `true` | ✅ 固定 `true` | ✅ 固定 `true` | ❌ **不传** |
| `values` | — | ✅ | — | — |
| `unitRequired` | — | — | ✅ | — |
| `biz` | — | — | — | ✅ 目标分组的 `biz` |
| `combineInstances` | — | — | — | ✅ |

其他约定：

- `moduleId` 传 **视图键**（§3.1 的表），与查询用的一致。**不要用响应里 `data[].moduleId` 的值** —— 那是数据归属，两者可能不同（例如「其他信息」Tab 视图键 15，分组数据归属 3）。
- 不传 `sortNo`，新字段追加到分组末尾。
- `options`：地址/电话传 `""`（服务端生成）；数字必须自己构造；其余传 `""`。
- `applyTargetLibrary` 固定传 `true`（组合字段不传），见 §5.3.1。

### §5.4 编辑字段

#### 5.4.1 edit 是全量覆盖

```bash
cllmk curl \
  --url "/api/organization/hr/setting/field/edit?bus=20" \
  --method POST \
  --payload '<完整 JSON，含 attrId>'
```

payload 结构与创建**完全相同**，只是 `attrId` 填字段 ID。

> 🔴 **`field/edit` 会覆盖 payload 中的每一个键，漏传即重置。**
>
> 强制流程：
> 1. `field/detail` 读回字段当前全部值
> 2. 在读回结果上**只改用户要求变更的键**
> 3. 按 §5.3 的类型键集合合成完整 payload 再提交
>
> 绝不允许只传变更字段。

**修改 `modelId` 会把字段移动到另一个分组**。用户只说改名时，`modelId` 必须原样传回，不能省略也不能改动。

#### 5.4.2 编辑单选字段的 `values`

`field/detail` 读回的选项是完整对象：

```json
{"id":<option-id>,"idx":1,"value":"专员","isDelete":1,"isDisable":1,
 "isCanModify":1,"checked":0,"type":0,"sortNo":1,"valueInitials":null,"hot":null}
```

**规则：**

| 变更类型 | 处理 |
|---|---|
| 修改已有选项文案 | **保留其 `id`**，只改 `value` |
| 新增选项 | 不传 `id`（新项由服务端分配） |
| 调整顺序 | 按目标显示顺序重排 `sortNo`；`id` 一律保留 |
| 删除选项 | ⚠️ 未实证。停下询问用户，不要自行省略某项 |

`sortNo` 是显示顺序，`idx` 是创建序号（只读，不用管）。

> 依据：实测把「专员」改名 + 在中间插入新选项后，所有原选项的 `id` 全部保留（包括显示位置后移的那个）。若不传 `id`，服务端无法按位置匹配，必然重建选项并丢失数据关联。
>
> ⚠️ 该结论由 id 保留反推得出，未直接抓到 edit 的 body。**首次执行单选编辑前，先在测试租户跑一次并用 `field/detail` 复核 id 是否保留。**

### §5.5 停用字段

先执行 §3.5 写前预检（`isLimited == 0` 直接拒绝）。

```bash
cllmk curl \
  --url "/api/core/v1/field/disable?bus=20" \
  --method POST \
  --payload '{"attrId":<字段id>,"modelId":<分组id>,"bus":"20","loginType":"10"}'
```

### §5.6 启用字段

```bash
cllmk curl \
  --url "/api/core/v1/field/enable?bus=20" \
  --method POST \
  --payload '{"attrId":<字段id>,"modelId":<分组id>,"bus":"20","loginType":"10"}'
```

> 启停两个接口 payload 完全相同，只有路径不同。注意 `bus` **同时出现在 query 和 body**，body 里是字符串 `"20"`。
>
> 已停用字段仍会出现在 `model/list` 中（`isLimited == 2`），因此按名称定位停用字段不需要特殊接口。

### §5.7 不要调用的噪声接口

页面操作时会伴随下列请求，**skill 一律不调用**：

| 接口 | 性质 |
|---|---|
| `/api/common/v1/formLinkageRule/ruleList` | 联动规则列表 |
| `/api/common/v1/formLinkageRule/getTotalCount` | 联动规则计数 |
| `/api/universal/pushmsg/getUnreadMsgCount` | 消息红点 |
| `/api/gateway/gray`、`/manifest.json` | 基础设施 |
| `*.fc.aliyuncs.com/.../write_log/` | 前端埋点 |

写操作后页面会自动重新拉 `model/list`；skill 可按需自行回读验证，但那是独立决策，不是接口的必需步骤。

---

## 第 6 步：调用前确认

任何写操作（创建 / 编辑 / 停用 / 启用）前，必须展示完整请求并获得确认：

```
即将执行以下操作（创建 / 编辑 / 停用 / 启用）：

接口：POST {接口路径}
当前会话：people / {env} / {corpName}（tenantId {tenantId} / buId {buId}）
位置：{Tab 名} → {分组名}
{字段名}（类型：{类型名}{，已有字段 id}）

请求内容：
{格式化 JSON payload}

影响范围：员工档案字段为全租户共享配置，改动对所有员工生效。

确认执行？
```

**分类型追加：**

- **编辑**：展示「变更前 → 变更后」逐项对照，明确列出**未变更但仍会提交的键**，说明这是全量覆盖接口。
- **编辑单选**：展示选项对照表，标注哪些保留 `id`、哪些是新增。
- **跨分组移动**（`modelId` 变化）：单独一行醒目提示「字段将从【A 分组】移动到【B 分组】」。
- **停用**：说明停用后字段在员工档案中不再显示，已填数据保留。
- **批量操作**：先展示完整清单和总数，逐条执行并汇报进度；任一条失败即停止并报告已完成/未完成。

用户回复「确认」「可以」「执行」「ok」「是」等明确指令后才继续，其他回复视为未确认。

---

## 第 7 步：处理响应

| 响应 | 处理 |
|---|---|
| 内层 `code == 200` | 成功。展示关键结果（新字段 ID、变更摘要）。写操作后可选回读 `model/list` 或 `field/detail` 验证 |
| 内层 `code != 200` | **业务失败**。展示 `msg`，检查参数（字段名重复、类型非法、分组不存在、必填缺失等）。不要因为外层 `code == 0` 就报告成功 |
| HTTP 401 / 403 | 跑裸 `cllmk auth status` 验证；明确失效才引导重新登录，否则报告权限问题 |
| HTTP 4xx 其他 | 展示错误详情，提示检查参数 |
| HTTP 5xx | 服务端错误，建议稍后重试 |
| `Request failed`（网络） | 按 `<cllmk-dir>/references/foundation/auth.md` 的「受限执行环境的网络重试」处理。**写请求不可盲目重试** —— 先用 `model/list` 或 `field/detail` 回读确认是否已生效 |

---

## 不覆盖清单

以下能力**不在本 skill 覆盖范围**，用户提出时停下说明并建议在页面手工操作：

| 能力 | 原因 |
|---|---|
| 删除字段 | 接口未知；且不可逆。建议改用停用 |
| 添加 / 编辑 / 停用分组 | 接口未抓到（分组 `status` 语义已明但改状态接口未知） |
| 字段拖拽排序 | 接口未抓到 |
| 档案结构设置 | 独立功能，未探索 |
| 联动规则（formLinkageRule） | 独立功能，只读噪声，未探索 |
| 组合字段类型本身的增删改 | 属「基础设置 → 组合字段」页；本 skill 只引用不修改 |
| 创建银行卡组合字段(40) | payload 未实证且体积巨大，见 §4.5 |
| 创建多选字段 | type 编号未知，存量数据无样例 |
| 创建系统内置类型（部门/员工/职级/工作地点等选择器） | 非自定义字段形态，见附录 A |
| 修改系统核心字段（`isLimited == 0`） | 平台限制 |

---

## 附录 A：字段类型全表

**可创建**（§4.2 已列）：1 单行文本、2 日期、3 数字、4 是否、5 单选、6 地址、7 电话、8 附件、11 多行文本、9 证件组合。

**只读**（存量数据中存在，但**不允许创建**，不在本 skill 覆盖范围）：

| type | 语义 | type | 语义 |
|---|---|---|---|
| 12 | 部门选择器 | 25 | 招聘模式 |
| 13 | 职务选择器 | 26 | 方案选择器（薪资/社保/公积金） |
| 15 | 职级选择器 | 27 | 薪资异动原因 |
| 16 | 工作地点 | 31 | 适用部门 |
| 17 | 员工选择器 | 40 | 银行卡（组合） |
| 18 | 成本中心 | 41 | 参保地 / 缴存地 |
| 19 / 20 | 事件类型 / 事件原因 | 50 | 员工头像 |
| 21 | 法人公司 | 60 | 发薪组织 |
| 22 / 23 / 24 | 职位族 / 类 / 小类 | -20 / -30 | 出发城市 / 目的城市 |

解析已有字段时按本表翻译 `type` 为中文名展示给用户。

## 附录 B：moduleId 全表

**请求参数 `moduleId` 是视图键**（Tab 标识），与响应里 `data[].moduleId`（数据归属）语义不同。所有请求一律使用视图键。

### B.1 员工信息设置页的 9 个 Tab

| Tab | moduleId | 前端路由 |
|---|---|---|
| 个人信息 | 1 | `staffInfoManage` |
| 任职信息 | 2 | `officeManage` |
| 履历信息 | 3 | `experienceManage` |
| 合同信息 | 8 | — |
| 招聘信息 | 9 | — |
| 兼岗信息 | 14 | `partTimeManage` |
| 其他信息 | 15 | `otherManage` |
| 所属成本中心 | 18 | — |
| 所属项目组 | 68 | `projectTeam` |

### B.2 其他设置页的模块（同接口可访问，不属本页）

| moduleId | 内容 |
|---|---|
| 4 / 5 / 6 / 7 | 职务 / 职级 / 部门 / 部门职责 |
| 11 | 招聘需求（HC，≠ ATS 的 hc 字段） |
| 12 | 出差行程 |
| 13 | 薪资档案 |
| 17 | 社保 / 公积金 |
| 19 / 20 | 成本中心基础信息 / 职责 |
| 21 | 绩效信息（500 字段，响应约 284 KB） |
| 22 / 23 | 发薪组织基础信息 / 职责 |
| 24 | 编制信息 |
| 25 | 批量调整 |
| 66 / 67 | 项目组信息 / 项目组职责 |
| 77 | 学习项目 / 课程 / 考试 |
| 88 | 历史任职信息（也出现在 Tab「任职信息」下） |

已扫描 1–400，上述之外均返回空数组。不存在的 moduleId 不报错，返回 `data: []`。

### B.3 视图键与数据归属不一致的已知情形

| 请求 moduleId | 响应 `data[].moduleId` | 说明 |
|---|---|---|
| 15（其他信息） | 全部为 3 | 虚拟聚合视图：服务端按 `moduleId=3 且 biz=extend` 聚合 39 个自定义分组 |
| 2（任职信息） | 4 个为 2，1 个为 88 | 「历史任职信息」是外来分组，也可用 moduleId=88 单独取到 |
| 3（履历信息） | 全部为 3 | 与视图键一致；但注意数据层 moduleId=3 同时承载「其他信息」的 extend 分组，两个视图靠 `biz` 区分 |

## 附录 C：状态位速查

People 全系统统一约定：**0 = 系统锁定 / 1 = 启用 / 2 = 停用**。

| 对象 | 键 | 0 | 1 | 2 |
|---|---|---|---|---|
| 字段 | `isLimited` | 系统核心字段，不可停用 | 启用中 | 已停用 |
| 分组 | `status` | 系统内置分组，常驻 | 启用中 | 已停用（页面锚点不可见） |

**不要用这些键判断状态**（实测在整个模块内恒为 0，无区分度）：`isShow`、`isUnique`、`sensitivity`、`isCanApprove`。

其他常用键：

| 键 | 说明 |
|---|---|
| `fieldName` | `DF_` 前缀 = 租户自建字段；其余为系统预置（`realname` / `birthday` / `id_no`…） |
| `isRequired` | 0/1，对应列表页字段名后的 `*` |
| `isCanModify` | 0/1，是否允许修改 |
| `isCanModifyRequired` | 0/1，是否允许改必填 |
| `biz` | 分组业务标识；系统分组为具名值（`baseInfo` / `contact` / `work`…），租户自建分组统一为 `extend` |
| `combined` / `combineTypeId` | 组合字段标识（证件 1939 / 银行卡 1940） |
