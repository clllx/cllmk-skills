---
route: job-rank-manage
---

# Moka ATS 职位级别（职级）管理 — 仅单 ATS 系统

本路由通过 `cllmk curl` 管理 Moka ATS 的职位级别（UI 位置：`/settings/job_rank`），覆盖四个接口：

| 动作 | Method | URL |
|---|---|---|
| 查询 | `POST` | `/api/outer/ats-jc/job/jobRank/listForManage` |
| 创建 | `POST` | `/api/outer/ats-jc/job/jobRank/create` |
| 修改 | `POST` | `/api/outer/ats-jc/job/jobRank/update` |
| 合并（唯一的删除手段） | `POST` | `/api/outer/ats-jc/job/jobRank/merge` |

## 目录

- 适用范围硬边界（先读这一节）
- 前置鉴权与租户防串
- 数据模型与通用响应结构
- 错误码字典
- 查询职级
- 创建职级
- 修改职级
- 合并（删除）职级
- 安全约束
- 不在本路由覆盖范围

---

## 适用范围硬边界（先读这一节）

> **本文的接口只适用于「单 ATS 系统」的职级管理。**

| 租户形态 | 职级由谁管 | 本路由是否适用 |
|---|---|---|
| 单独的 Moka ATS 招聘系统（`app.mokahr.com` / `hire-r1.mokahr.com` / `staging-3.mokahr.com`） | ATS 自己的 `ats-jc` 接口 | ✅ **唯一覆盖范围** |
| Moka People 人事系统里的「职位级别 / 职级」（`core.mokahr.com`） | People 侧另一套接口与数据模型 | ❌ 使用 `people` skill，**不得**套用本文 endpoint 或 payload |
| ATS + People 一体化，职级作为人事主数据下发到招聘侧 | People 侧主数据 | ❌ 停止写入，见下方判定 |

**执行写操作前必须确认租户形态。** 本文的四个接口**无法**判断当前租户属于哪种形态（`listForManage` 不返回数据来源标识，实测未见相关字段）。因此：

- 用户未说明时，向用户确认「这个租户的职级是在招聘系统里维护，还是从人事系统同步过来的」。
- 若职级来自 People 侧主数据，用 ATS 接口写入可能与人事侧不一致或被同步覆盖 —— **停止写入**，改用 `people` skill 或让用户在 People 页面操作。
- 只读的 `listForManage` 在任何形态下都可以跑。

**另一处命名撞车**：`protection-period-country` 路由里的「职位级别的保护期方案配置」指的是渠道保护期的**配置维度**，和本文的职级管理毫无关系。用户提到「职位级别」时先分清是**职级本体的增删改查**（本路由）还是**保护期方案**（`protection-period-country`）。

---

## 前置鉴权与租户防串

执行任何操作前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `CLLMK_PROFILE` 为空 → 需要时按 `tenant-switch.md` 切换 current → 裸 `cllmk auth status`，确认 `data.system === "ats"` 且 `orgId` / `orgName` / `env` 与目标一致。

向用户展示 env / orgName 并确认目标租户后再继续。

### 每条写请求前重新断言 orgId（强制）

本组接口对「id 不存在」和「id 属于别的租户」返回**同一个错误码 `1919401 无权限`**，无法区分。也就是说 **接口报错兜不住租户串号**：拿 A 租户的 id 去 B 租户跑，只会得到一句「无权限」；反过来如果两个租户都有同名职级，写入会静默落到错误的租户。

因此：**不要只在流程开头查一次 status**。每条 `create` / `update` / `merge` 之前重新确认一次 orgId，status 不匹配就不发请求。用 `&&` 短路，不要用 `;` 串联（`;` 会在 status 失败后照样执行写入）：

```bash
EXPECT_ORG="<目标 orgId>"

guard() {
  local org
  org=$(cllmk auth status 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d['data']['orgId'] if d.get('code')==0 else '')
except Exception:
    print('')
")
  if [ "$org" != "$EXPECT_ORG" ]; then
    echo "!!! 护栏拦截：当前 orgId='${org:-<无/失败>}'，期望 '$EXPECT_ORG'。已阻止写入。" >&2
    return 1
  fi
}

guard && cllmk curl --url /api/outer/ats-jc/job/jobRank/create --method POST --payload '<payload>'
```

`create` 的成功响应里带 `data.data.orgId`，可作为写入后的二次断言：与目标不一致时立即停止并向用户报告已写入错误租户。

### 样例 id 一律运行时获取

本文所有 payload 里的 `id` / `mergeToId` / `departmentIds` 都是示意值。**禁止**照抄任何历史 curl 或文档样例里的数字 —— 职级 id 是租户内自增的，跨租户复用必然指向错误对象或报 `1919401`。每次都先跑 `listForManage` 拿当前租户的真实 id。

---

## 数据模型与通用响应结构

`listForManage` 返回的每个职级对象：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | 数字 | 职级 ID，租户内唯一 |
| `name` | 字符串 | 职级名称 |
| `type` | 字符串 / null | 职级类别，**自由文本**，非枚举 |
| `level` | 数字 | 级别数值 |
| `departmentIds` | 数字数组 | 适用部门；`[0]` = 全部部门 |
| `departments` | 对象 | `departmentIds` 的 id→名称映射，如 `{"0":"全部部门"}` |
| `status` | 数字 | 实测全部为 `0`；**语义未验证**，不要据此判断启用/停用 |
| `comment` | 字符串 / null | 备注 |
| `apiCode` | 字符串 | 实测为空串；**语义未验证** |

### 双层 code 陷阱（必须遵守）

业务失败时 HTTP 仍是 **200**、`cllmk` 外层仍是 **`code:0`**，只有内层 `data.success:false`。

```json
{"code":0,"data":{"code":705402,"codeType":0,"msg":"名称和类别与已有职位级别重复","opNo":"...","source":"ats-jc","success":false},"msg":""}
```

**判定成败只看 `data.success` 与 `data.code`**，绝不能把外层 `code:0` 当成业务成功。

| 类别 | 判定条件 | 是否重试 |
|---|---|---|
| ✅ 成功 | `code=0 AND data.success=true AND data.code=0` | — |
| 🚫 业务失败 | `code=0 AND data.success=false`，见错误码字典 | **不重试** |
| 🌐 网络失败 | `cllmk` 非 0 退出，或 `ECONNRESET` / `ETIMEDOUT` / `socket hang up` | **结果未知，不自动重试**；先用 `listForManage` 回读 |

---

## 错误码字典（实测）

| `data.code` | `data.msg` | 触发条件 |
|---|---|---|
| `0` | 成功 | — |
| `100` | 地址错误 | 用 `GET` 调 `listForManage`（伴随 `HTTP 405`） |
| `101` | JSON格式错误 | `level` 传了无法解析为整数的值（如 `"abc"`）；后端按 int 反序列化 |
| `705401` | 无对应职级 | `merge` 时 `id == mergeToId`（自我合并被拒） |
| `705402` | 名称和类别与已有职位级别重复 | `create` / `update` 的 `(name, type)` 组合与现有职级冲突 |
| `1919401` | 无权限 | `id` / `mergeToId` 不存在，**或**不属于当前租户 —— 两种情况同码，无法区分 |

其他错误码尚未收集，遇到后按实测结果回填此表，不要猜测含义。

---

## 查询职级

```bash
cllmk curl --url /api/outer/ats-jc/job/jobRank/listForManage --method POST
```

| 要点 | 实测结果 |
|---|---|
| Method | **必须 `POST`**；`GET` 返回 `HTTP 405` + `data.code:100 地址错误` |
| Body | 可完全省略，也可传 `{}`，两者结果一致（UI 抓包是 `Content-Length: 0`） |
| 分页 | 无分页参数，一次返回全部 |
| 排序 | 非 `id` / `level` 顺序，按服务端返回原序展示即可 |

职级数组在 `data.data`（注意是双层 `data`）。人类可读输出：

```bash
cllmk curl --url /api/outer/ats-jc/job/jobRank/listForManage --method POST | python3 -c "
import json,sys
d=json.load(sys.stdin)['data']['data']
print(f'共 {len(d)} 条')
for r in d:
    print(f\"  id={r['id']} level={r['level']} name={r['name']!r} type={r['type']!r} departments={r.get('departments')} comment={r['comment']!r}\")
"
```

以 Markdown 表格向用户呈现，至少包含：id、name、type、level、适用部门。

---

## 创建职级

```bash
cllmk curl --url /api/outer/ats-jc/job/jobRank/create --method POST --payload '{
  "name": "<职级名称>",
  "type": "<职级类别>",
  "level": 10,
  "departmentIds": [0],
  "comment": ""
}'
```

### 字段规则（实测）

| 字段 | 规则 |
|---|---|
| `name` | 必填。**可以与现有职级重名**，只要 `type` 不同 |
| `type` | **自由文本，不是枚举**。实测同一租户内并存 `"管理"` / `"副"` / `"正"` / `"特级"` / `"工程师"` / `""` 等任意字符串；空串合法 |
| `level` | 数字。传数字字符串 `"10"` 也会被接受并落库为数字 `10`；传 `"abc"` 报 `101 JSON格式错误`。**不要求唯一，也不要求连续** —— 实测同租户有 10 条 `level=1`，并存 17 / 20 / 30 |
| `departmentIds` | `[0]` = 全部部门；也可传具体部门 id 数组。⚠️ 见下方「不校验部门存在性」 |
| `comment` | 备注，可传空串 |

**唯一约束是 `(name, type)` 组合**，不是 `name`。冲突时返回：

```json
{"code":705402,"msg":"名称和类别与已有职位级别重复","success":false}
```

创建前先跑 `listForManage`，按 `(name, type)` 判重并把结论告诉用户，不要靠撞错误码试探。

### ⚠️ `departmentIds` 不校验部门存在性

示例中传入一个根本不存在的部门 id：**创建可能成功，野 id 原样入库**，但 `listForManage` 返回的 `departments` 映射可能回落成 `{"0":"全部部门"}`。结果是**数据与展示不一致**：库里存着无意义的部门 id，UI 上却显示「全部部门」。

因此创建/修改前必须核实部门 id 真实存在（让用户提供，或从 UI / 部门接口确认），**不能指望接口报错兜底**。

### 成功响应

```json
{"code":0,"data":{"code":0,"codeType":0,"data":{"comment":"<comment>","departmentIds":[<department-id>],"id":<rank-id>,"level":10,"name":"<rank-name>","orgId":"<org-id>","status":0,"type":"<rank-type>"},"msg":"成功","success":true},"msg":""}
```

`data.data.id` 是新建职级的 id；`data.data.orgId` 用于二次确认写入落在目标租户。

---

## 修改职级

```bash
cllmk curl --url /api/outer/ats-jc/job/jobRank/update --method POST --payload '{
  "id": <运行时从 listForManage 获取>,
  "name": "<新名称>",
  "type": "<新类别>",
  "level": 10,
  "departmentIds": [0],
  "comment": "<新备注>"
}'
```

### ⚠️ 三个反直觉的行为（本节是本文最重要的部分）

**1. 省略字段 = 不修改（MERGE 语义）。**

这与本 skill 里 `job-field-manage` 的职位 `customFields`、候选人登记表联动的 **REPLACE** 语义**正好相反**。只传 `{"id":<rank-id>,"name":"<new-name>"}` 时，回读后其他字段保持原值，只有 `name` 变更。所以做局部修改时可以只传要改的字段，不需要先读全量再整体下发。

**2. 响应体是入参回显，不是写入结果 —— 必须回读。**

上面那次只传 `id` + `name` 的请求，响应是：

```json
{"code":0,"data":{"code":0,"data":{"comment":null,"departmentIds":[0],"level":null,"name":"新名字","type":null,...},"msg":"成功","success":true}}
```

`comment` / `level` / `type` 显示为 `null`，但库里这三个字段**完好无损**。响应只是把你没传的字段回显成空值。

> **强制要求**：任何 `update` 之后必须跑 `listForManage` 回读目标 id，用回读结果向用户汇报。**禁止**把 update 的响应体当作写入结论 —— 它会让你误判成「字段被清空了」。

**3. 显式传 `departmentIds: []` ≠ 省略它。**

把某职级的 `departmentIds` 从一个具体部门改传 `[]`，落库结果可能是 `[0]`，即**适用范围被放开成「全部部门」**，原来的部门限制被无声抹掉。

所以：
- 不想动部门范围 → **省略 `departmentIds` 字段**
- 想改成全部部门 → 显式传 `[0]`（语义清晰）或 `[]`（等效，但不推荐）
- 想限定部门 → 传核实过的具体部门 id 数组

从 UI 抓来的 curl 里如果带着 `"departmentIds":[]`，套用到一个原本限定了部门的职级上就是一次无声的范围放开 —— 执行前必须先回读该职级当前的部门范围并向用户明示。

### 其他实测结果

| 情况 | 结果 |
|---|---|
| `id` 不存在 | `1919401 无权限`（**不是**「不存在」，报错有误导性） |
| 改后 `(name, type)` 与其他职级冲突 | `705402 名称和类别与已有职位级别重复` |
| `level` 传 `"abc"` | `101 JSON格式错误` |
| `departmentIds` 传不存在的部门 id | 与 create 相同：静默接受，`departments` 映射回落成全部部门 |

### 执行流程

1. `listForManage` 回读目标职级当前全量字段，向用户展示「改前」状态。
2. 只构造要修改的字段（外加 `id`）；明确告知用户哪些字段不动。
3. 展示完整 payload，等用户确认。
4. `guard && cllmk curl ...` 执行。
5. **再次 `listForManage` 回读**，用回读结果展示「改后」状态。不要引用响应体里的 null。

---

## 合并（删除）职级

> **`merge` 是本组接口唯一的下线手段，且不可逆。没有找到 `delete` 端点。**

```bash
cllmk curl --url /api/outer/ats-jc/job/jobRank/merge --method POST --payload '{
  "id": <将被删除的职级 id>,
  "mergeToId": <合并去向的职级 id>
}'
```

语义：`id` 指向的职级**消失**，其引用被并入 `mergeToId`。实测 `mergeToId` 那条职级的自身属性（`name` / `type` / `level` / `departmentIds` / `comment`）**零改动**，它只是接收方。

### 实测结果

| 情况 | 结果 |
|---|---|
| 正常合并 | `{"code":0,"msg":"成功","success":true}` —— **响应无 `data` 字段**，不返回任何对象 |
| 合并后 | `id` 从 `listForManage` 消失；`mergeToId` 属性不变 |
| `id == mergeToId`（自我合并） | 拒绝：`705401 无对应职级` |
| `mergeToId` 不存在 | 拒绝：`1919401 无权限` |
| `id` 不存在 | 同上：`1919401 无权限` |

### ⚠️ 未验证：源职级被职位引用时的行为

「原本挂在源职级上的职位会改挂到 `mergeToId`」是**根据接口名和 UI 文案的推断，尚未实证** —— 实测用的是新建的、没有任何职位引用的职级。**不要向用户断言职位会被安全改挂。**

因此执行前必须额外做一步：让用户确认源职级上挂了多少职位、这些职位改挂到目标职级是否可接受。用户无法确认影响范围时**停止**，请其先在 UI 上核对。

### 执行门禁（缺一不可）

1. `listForManage` 回读 `id` 与 `mergeToId` 两条职级的完整信息。
2. 向用户逐字明示：**「`<源 name>/<源 type>`（id=X）将被删除且不可恢复，其职位引用并入 `<目标 name>/<目标 type>`（id=Y）」**，等待用户显式确认。
3. 提醒职位改挂行为未经实证（见上）。
4. `guard` 确认 orgId 后才执行。
5. 执行后 `listForManage` 回读，确认源已消失、目标属性未变，再向用户汇报。

**禁止**在用户只说了职级名称、没有确认 id 的情况下执行合并 —— 同名不同 `type` 的职级可以并存，仅凭名称会删错对象。

---

## 安全约束

- **禁止**把 `cllmk` 外层 `code:0` 当成业务成功；只认 `data.success` / `data.code`。
- **禁止**把 `update` 的响应体当写入结论；必须 `listForManage` 回读。
- **禁止**照抄历史 curl 或文档样例里的 `id` / `mergeToId` / `departmentIds`；一律运行时获取。
- **禁止**用 `;` 串联 status 与写请求；必须 `&&` 短路，status 不匹配即不发写请求。
- **禁止**在未核实部门 id 存在性时写 `departmentIds`（接口不校验，会产生脏数据）。
- **禁止**静默执行 `merge`；必须完成上方五步门禁。
- **禁止**在租户形态未确认（可能是 People 主数据下发）时写入。
- **禁止**展示或记录 Cookie 明文（`moka-jwt` / `moka-uid` 等）。用户贴带 `-b` 的 curl 时提醒其去掉 Cookie 段，并改用 `cllmk curl` 复现。

---

## 不在本路由覆盖范围

| 需求 | 应使用 |
|---|---|
| People 人事系统的职位级别 / 职级 | `people` skill；接口与数据模型完全不同 |
| 渠道保护期的「职位级别方案」配置 | `protection-period-country` 路由 |
| 职级的启用 / 停用（`status` 字段语义未验证） | 当前不覆盖；不要猜测 `status` 取值去写入 |
| `apiCode` 的用途与写入 | 当前不覆盖，语义未验证 |
| 职级与职位的绑定关系查询 / 批量改挂 | 当前不覆盖；需要用户提供 UI 操作的 curl 才能反推 |
| 职级排序 / 层级树 | 当前未见相关接口；`level` 只是数值标签，不构成排序契约 |
| 职位自定义字段 / HC 字段 | `job-field-manage` / `hc-field-manage` 路由 |

---

## 验证说明

本文结论按接口行为记录；示例中的 ID、名称和租户标识均为占位符，禁止照抄。
