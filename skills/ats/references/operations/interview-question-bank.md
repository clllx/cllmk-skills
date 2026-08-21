---
route: interview-question-bank
---

# Moka ATS 面试题库管理（Interview Question Bank）

本路由通过 `cllmk curl` 管理 Moka ATS 的面试题库（UI 位置：`/settings/interview_question`），覆盖四个接口：

| 动作 | Method | URL（前缀 `/api/outer/ats-interview/interview/interviewQuestion/`） | payload |
|---|---|---|---|
| 查询 | `POST` | `getInterviewQuestionList` | `{"currentPage":1,"pageSize":30,"title":"","count":true}` |
| 创建 | `POST` | `save` | `{"title":"...","description":"..."}` |
| 更新 | `POST` | `update` | `{"id":<数字>,"title":"...","description":"..."}` |
| 删除 | `POST` | `delete` | `{"id":<数字>}` |

## 目录

- 覆盖范围与边界
- 前置鉴权与租户护栏
- 数据模型
- 四个写接口的共同陷阱（先读这一节）
- 错误码字典
- 查询题目
- 创建题目
- 更新题目
- 删除题目
- 安全约束
- 不在本路由覆盖范围

---

## 覆盖范围与边界

| 项 | 结论 |
|---|---|
| 社招 / 校招是否隔离 | **不隔离，两个场景共用同一组面试题库**（用户确认，非实测）。因此本路由**不需要**按 `currentHireMode` 分流，也不必在操作前读 `org/info` 判场景 |
| 与面试评价表的关系 | 题库是被引用方。评价表模板通过 `feedbackQuestion.questions[].id` 引用题库题目，见 `form-config/interview-feedback-form.md`。**改题/删题会影响引用它的模板** |
| People 人事系统 | 无对应概念，不涉及 |

> **社招/校招通用这一条是用户口头确认的，没有实测。** 实测时会话 `currentUserInfo.currentHireMode` 为 `1`（社招），未在校招场景下比对过题目列表。若后续发现两场景列表不同，以实测为准并更新本节。

### 与面试评价表的场景差异（容易搞反）

| 对象 | 是否区分社招/校招 |
|---|---|
| **面试题库**（本路由） | ❌ **不区分**，两个场景共用同一组题目 |
| **面试评价表模板**（`interview-feedback-form` 路由） | ✅ **区分**。每张表带 `hireMode`，列表只返回当前会话场景下的表 |

含义：同一道题可以同时被社招表和校招表引用，**不存在「校招题库」**，也不需要为两个场景各备一份题目。
但操作评价表时仍必须按那边的 §1.2 探测 `currentHireMode`。

---

## 前置鉴权与租户护栏

执行任何操作前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `CLLMK_PROFILE` 为空 → 需要时按 `foundation/tenant-switch.md` 切换 current → 裸 `cllmk auth status`，确认 `data.system === "ats"` 且 `orgId` / `orgName` / `env` 与目标一致。

向用户展示 env / orgName 并确认目标租户后再继续。

### 每条写请求前重新断言 orgId（强制）

本组接口对「id 不存在」和「id 属于别的租户」都返回 `222141 数据不存在`，**无法区分**。接口报错兜不住租户串号，只能靠写前断言。

**不要只在流程开头查一次 status**，每条 `save` / `update` / `delete` 之前重新确认 orgId，并用 `&&` 短路 —— 用 `;` 串联会在 status 失败后照样发出写请求：

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

guard && cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/save --method POST --payload '<payload>'
```

**样例 id 一律运行时获取。** 本文所有 `id` 都是示意值，禁止照抄历史 curl 或文档里的数字；题目 id 是租户内分配的，跨租户复用只会得到 `222141`。

---

## 数据模型

`getInterviewQuestionList` 的 `rows[]` 每一项：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | 数字 | 题目 ID。⚠️ **不反映创建顺序**，见下 |
| `title` | 字符串 | 题目标题。非空时**强制唯一**（重复报 `223200`）；空串不受唯一约束 |
| `description` | 字符串 | 题目内容/描述，可为空串。支持 `\n` 换行 |
| `templateCount` | 数字 | **引用该题的面试评价表模板数量**（去重计数，实时）。改题/删题的影响面判断依据。⚠️ 只统计 `subjectId` 在模板 `items` 中**有效存在**的关联，孤儿条目不计，见下 |
| `operatorId` / `operatorName` | 数字 / 字符串 | 最后操作人，写操作会覆盖为当前会话账号 |
| `updatedAt` | 数字 | 毫秒时间戳。**列表按此字段倒序**返回 |
| `version` | 字符串 | 实测恒为 `"1.0"`，**不可写**（见 update 一节）|

**`id` 不能用来推断新旧**：实测新建的题目拿到 `100056162`，比早已存在的 `100058149` 更小。判断创建/修改顺序只能用 `updatedAt`。

### `templateCount` 的精确语义与它的盲区

实测逐张比对 51 张评价表的 `feedbackQuestion` 后确认：`templateCount` **等于**引用该题目的模板数（去重），
且随评价表侧的改动实时变化。但它有一个盲区：

> **孤儿关联条目不计入 `templateCount`** —— 若某模板的 `feedbackQuestion` 条目里 `subjectId` 已不在该
> 模板的 `items` 中（评价表侧删了 subject 却没同步收拾关联，见 `form-config/interview-feedback-form.md` §4.4.2），
> 该条目引用的题目**不会**被计数。

因此：

- `templateCount > 0` → 一定有模板在有效引用，改/删必须先评估影响面。
- `templateCount == 0` → **不能**据此断定「没有任何模板提到这道题」，可能存在孤儿条目。
- **`templateCount` 不能用来发现悬空或孤儿关联**。要查这类问题只能从评价表侧逐张读详情，按裸
  `{"id":...}`（无 `title`）识别，方法见 `form-config/interview-feedback-form.md` §4.4.4。

---

## 四个写接口的共同陷阱（先读这一节）

### 1. 双层 code

业务失败时 HTTP 仍是 **200**、`cllmk` 外层仍是 **`code:0`**，只有内层 `data.success:false`：

```json
{"code":0,"data":{"code":223200,"codeType":0,"msg":"题目名称不可重复","opNo":"...","source":"ats-interview","success":false},"msg":""}
```

**判定成败只看 `data.success` 与 `data.code`。**

### 2. 三个写接口全都只返回 `data: true`，不回显任何对象

`save` / `update` / `delete` 成功时统一是：

```json
{"code":0,"data":{"code":0,"codeType":0,"data":true,"msg":"成功","success":true},"msg":""}
```

后果：
- `save` **拿不到新建的 id**
- `update` **看不到写入后的实际值**（`version` 就是这么被静默忽略的）
- 任何写操作之后**必须调 `getInterviewQuestionList` 回读确认**，不能拿响应当结论

### 3. 查询响应会「掉键」

`currentPage` 越界或搜索无命中时，`rows` 和 `total` **两个键从响应里整个消失**，只剩 `{currentPage, pageSize}`，且 `success` 仍是 `true`：

```json
{"code":0,"data":{"code":0,"codeType":0,"data":{"currentPage":999,"pageSize":30},"msg":"成功","success":true},"msg":""}
```

**解析时必须用 `.get('rows') or []` / `.get('total')` 防御**，直接下标会 KeyError / NPE。而且「无命中」和「翻过界」的响应形态完全相同，**无法从响应区分**。

### 4. `count` 默认 false，此时 `total = -1`

`-1` 是「未统计」的哨兵值，**不是 0 条**。要真实总数必须显式传 `count: true`。

---

## 错误码字典（实测，`data.source: "ats-interview"`）

| `data.code` | `data.msg` | 触发条件 |
|---|---|---|
| `0` | 成功 | — |
| `-1` | 系统错误 | `update` 显式传 `title: ""`。**这是未处理异常泄漏，不是业务码** |
| `222141` | 数据不存在 | `update` / `delete` 的 `id` 不存在，**或**不属于当前租户，**或**该 id 已被删除（重复删除）—— 三种情况同码 |
| `223200` | 题目名称不可重复 | `save` 的非空 `title` 与现有题目完全同名 |

其他错误码尚未收集，遇到后按实测结果回填，不要猜测含义。

---

## 查询题目

```bash
cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/getInterviewQuestionList \
  --method POST --payload '{"currentPage":1,"pageSize":30,"title":"","count":true}'
```

题目数组在 `data.data.rows`（注意双层 `data`），总数在 `data.data.total`。

### 参数行为矩阵（实测）

| 参数 | 行为 |
|---|---|
| 空 payload `{}` | 成功。默认 `currentPage=1`、`pageSize=10`、`count=false`（→ `total=-1`）|
| `count: true` | 返回真实 `total` |
| `count: false` / 省略 | `total = -1`（哨兵值，**不是 0**），`rows` 照常返回 |
| `currentPage: 0` | 等同第 1 页 |
| `currentPage` 越界 | `rows` / `total` 键消失，`success:true`（见共同陷阱 3）|
| `pageSize: 0` | **忽略分页，返回全部**（`pageSize` 原样回显 0）|
| `pageSize: -1` | `rows` 键消失，0 条 |
| `pageSize: 9999` | 正常返回 |
| `title: ""` / `null` / 省略 | 不筛选 |
| `title` 匹配方式 | 模糊匹配，**大小写不敏感**（`top100` 命中 `TOP100`）|
| `title` 空格 | ⚠️ **不做 trim**：`"TOP100 "` 命中 0 条。用户输入必须先自行 `strip()` |
| `title` 搜索范围 | ⚠️ **只搜 `title`，不搜 `description`** |

### 人类可读输出

```bash
cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/getInterviewQuestionList \
  --method POST --payload '{"currentPage":1,"pageSize":50,"title":"","count":true}' | python3 -c "
import json,sys
d=json.load(sys.stdin)['data']['data']
print('total', d.get('total'))
for r in (d.get('rows') or []):
    print(f\"  id={r['id']} title={r['title']!r} tmplCount={r['templateCount']} operator={r['operatorName']!r}\")
"
```

以 Markdown 表格向用户呈现，至少包含：id、title、templateCount、最后操作人。**`templateCount` 必须展示** —— 它是后续改/删操作的影响面依据。

---

## 创建题目

```bash
cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/save \
  --method POST --payload '{"title":"<题目标题>","description":"<题目内容>"}'
```

### ⚠️ 服务端校验缺失，调用方必须自己补三道校验

**1. 服务端不做必填校验 —— 必须在本地拦住空 title。**

实测 `{"title":"","description":"x"}` 和 `{"description":"x"}`（完全省略 title）**都返回成功**，落库 `title: ''`，UI 上出现无标题题目，而且空 title 不受唯一约束，可以无限重复创建。

> **强制**：构造 payload 前校验 `title` 非空（先 `strip()`）。空 title 直接停止并要求用户补齐，**不要**依赖服务端拦截。

**2. 服务端不返回新建 id —— 创建后按 title 回读。**

响应只有 `data: true`。因为非空 `title` 强制唯一（`223200`），创建成功后用精确 title 查一次即可可靠定位新 id：

```bash
guard && cllmk curl --url .../save --method POST --payload '{"title":"面试题标题","description":"..."}'
# 成功后回读拿 id
cllmk curl --url .../getInterviewQuestionList --method POST \
  --payload '{"currentPage":1,"pageSize":50,"title":"面试题标题","count":true}'
```

回读时 `title` 不要带首尾空格（接口不 trim）。这个办法**只对非空 title 有效** —— 又一个必须本地拦住空 title 的理由。

**3. `save` 传 `id` 会被静默忽略，永远是 INSERT。**

实测 `{"id":<已存在的 id>,"title":"新标题","description":"..."}` 的结果是**新建了一条记录**，目标 id 原封不动，且不报任何错。

> **`save` 不是 upsert。** 修改已有题目**只能**用 `update`。把 `save` 当 upsert 用会静默堆出重复数据。

### 查重

创建前先按 title 查一次并把结论告给用户，不要靠撞错误码试探。非空 title 重复时返回：

```json
{"code":223200,"msg":"题目名称不可重复","success":false}
```

### 执行流程

1. 本地校验 `title` 非空（`strip()` 后）。
2. `getInterviewQuestionList` 按精确 title 查重，向用户报告结论。
3. 展示完整 payload，等用户确认。
4. `guard && cllmk curl ...` 执行。
5. **按 title 回读**拿到新 id，用回读结果向用户汇报（不要说「已创建但拿不到 id」就收工）。

---

## 更新题目

```bash
cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/update \
  --method POST --payload '{"id":<运行时获取>,"title":"<新标题>","description":"<新内容>"}'
```

### 字段语义（实测）

| 情况 | 结果 |
|---|---|
| **省略字段** | **不修改（MERGE 语义）**。只传 `{"id":...,"title":"新标题"}`，`description` 保持原值；只传 `{"id":...}` 也成功且什么都不改 |
| 显式 `description: ""` | 成功，描述被清空 |
| **显式 `title: ""`** | ⚠️ **`code:-1 系统错误`**，写入不生效 |
| `version` | ⚠️ **不可写**。传 `"2.0"` 返回成功，回读仍是 `"1.0"` |
| `id` 不存在 | `222141 数据不存在` |
| 改后 title 与其他题重名 | 按 `223200` 处理 |

**MERGE 语义与本 skill 里 `job-field-manage` 的职位 `customFields`、候选人登记表联动的 REPLACE 正好相反** —— 局部修改只传要改的字段即可，不需要先读全量再整体下发。这一点与 `job-rank-manage` 一致。

**`title` 的校验在两个端点不一致**：`save` 放行空 title，`update` 却抛未处理异常（`-1 系统错误`）。清空标题这个操作在本接口上做不到，遇到该需求停止并说明。

### 修改前必须看 `templateCount`

题库是被评价表模板引用的共享数据。改一道 `templateCount > 0` 的题，会同步影响那些模板里呈现的题目内容。

> **强制**：`update` 前先回读该题的 `templateCount`。`> 0` 时向用户明示「这道题被 N 个面试评价表模板引用，修改会同时影响它们」，取得确认后才执行。

### 执行流程

1. `getInterviewQuestionList` 回读目标题目的全量字段与 `templateCount`，展示「改前」状态。
2. `templateCount > 0` 时明示影响面并取得确认。
3. 只构造要改的字段（外加 `id`），告知用户哪些字段不动。
4. 展示完整 payload，等确认。
5. `guard && cllmk curl ...` 执行。
6. **再次回读**，用回读结果展示「改后」状态。响应里的 `data:true` 不能作为字段生效的证据（`version` 就是这么被静默忽略的）。

---

## 删除题目

```bash
cllmk curl --url /api/outer/ats-interview/interview/interviewQuestion/delete \
  --method POST --payload '{"id":<运行时获取>}'
```

| 项 | 实测结果 |
|---|---|
| 语义 | **硬删除**，列表立即消失，无软删标记，不可逆 |
| 成功响应 | `{"code":0,"data":true,"msg":"成功","success":true}` |
| `id` 不存在 | `222141 数据不存在` |
| **幂等性** | ⚠️ **不幂等**。重复删同一 id 返回 `222141`，不是成功 |

### `222141` 在批量删除时的判定规则

因为不幂等，网络超时后重试同一条会得到 `222141`。**这时 `222141` 表示「已删成功」，不是失败**；但首次调用就返回 `222141` 则表示 id 本身有问题（不存在，或不属于当前租户）。

> **强制**：批量删除必须记录每个 id 是否已被本次任务成功删过。
> - 已成功删过 + 重试得到 `222141` → 判定 `OK`（幂等补偿）
> - 首次调用即 `222141` → 判定 `BUSINESS_FAIL`，不重试
>
> 不做这个区分会在报告里产出假失败或假成功。

### 删除门禁（缺一不可）

1. `getInterviewQuestionList` 回读目标题目的 `title` 与 `templateCount`。
2. 向用户逐字明示：**「`<title>`（id=X）将被硬删除且不可恢复」**，等待显式确认。
3. **`templateCount > 0` 时停止**，明示「该题被 N 个面试评价表模板引用，删除后这些模板会留下悬空引用且不会自动清理」，由用户确认后才继续 —— 见下方实证说明。
4. `guard` 确认 orgId 后才执行。
5. 执行后回读，确认目标已消失再向用户汇报。

**禁止**仅凭题目标题执行删除 —— 必须先回读拿到 id 并由用户确认对象。

### 🚨 删除被模板引用的题目：不拦截，也不清理引用（已实证）

实测结论（此前标注为「未验证」，现已确认）：

1. **删除不做引用检查**。一道 `templateCount == 1` 的题目被删除时**没有被拦截**。
2. **评价表侧的引用不会被清理**。删除后，引用它的评价表模板里**仍保留该题目 id**，变成
   **悬空引用** —— 详情接口里表现为裸 `{"id": <数字>}`，没有 `title` / `description` / `type`
   （正常题目会被富化返回这些字段）。
3. 悬空引用**不会**从 `templateCount` 上体现出来（题目已不存在，自然查不到计数）。

> 示例：某题目（删除前 `templateCount=1`）被删除后，评价表的
> `feedbackQuestion` 仍可能保留 `{"id": <deleted-question-id>}`，同条目内其他题目均带完整内容。
>
> 该次删除动作发生在 UI 侧，本路由的 API 删除只在无引用题目上实测过；但**「删除不清理引用」这一后果
> 是直接观测到的**，与删除走哪个入口无关。

因此 `templateCount > 0` 时**必须停下**：删除是可以成功的，代价是留下一条谁也不会主动发现的悬空引用。
向用户明示被影响的模板数量，让其决定是先改模板还是接受悬空引用，**不要**自行决定继续。

清理悬空引用只能从评价表侧做（重建题目并重映射，或把该题从模板的 `feedbackQuestion` 中移除），
见 `form-config/interview-feedback-form.md` §4.4.2 / §4.4.4。

---

## 安全约束

- **禁止**把 `cllmk` 外层 `code:0` 当成业务成功；只认 `data.success` / `data.code`。
- **禁止**把写接口的 `data:true` 当作字段生效的证据；`save` / `update` / `delete` 之后一律回读。
- **禁止**解析查询响应时直接下标 `rows` / `total`；必须 `.get(...) or []` 防御掉键。
- **禁止**依赖服务端校验空 `title`；本地拦住。
- **禁止**用 `save` 做更新（传 id 会被忽略并新建重复数据）。
- **禁止**照抄历史 curl 或文档样例里的 `id`；一律运行时获取。
- **禁止**用 `;` 串联 status 与写请求；必须 `&&` 短路。
- **禁止**在未回读 `templateCount` 的情况下执行 `update` / `delete`。
- **禁止**展示或记录 Cookie 明文（`moka-jwt` / `moka-uid` 等）。用户贴带 `-b` 的 curl 时提醒去掉 Cookie 段，改用 `cllmk curl` 复现。

---

## 不在本路由覆盖范围

| 需求 | 说明 |
|---|---|
| `interview/interviewQuestion/getAll` | `form-config/interview-feedback-form.md` 引用了该端点做题库 ID 映射，**本轮未验证**其 payload 与响应；不要假设它与 `getInterviewQuestionList` 同构 |
| 面试评价表模板本体的增改 | `form-config/interview-feedback-form.md` 路由 |
| 把题目绑定到评价表模板（`feedbackQuestion`） | `form-config/interview-feedback-form.md` 路由（§4.4）。本路由只管题库本体，**不写**任何模板侧字段 |
| 绑定到面试轮次 / 职位 | 当前不覆盖，两个路由都不做 |
| 清理悬空 / 孤儿关联引用 | 只能从评价表侧做，见 `form-config/interview-feedback-form.md` §4.4.2 / §4.4.4 |
| 题目分类、标签、题型、答案与评分标准 | 实测响应中无对应字段，接口未见支持 |
| 批量导入 / 批量删除的专用端点 | 未见；批量只能串行循环单条接口，并按上方 `222141` 规则记账 |
| 题目版本管理（`version` 字段） | `version` 恒为 `"1.0"` 且不可写，语义未验证，不要尝试写入 |
| 社招 / 校招分场景的题库差异 | 用户确认两场景通用；未实测，见「覆盖范围与边界」 |

---

## 验证说明

本文的行为结论来自接口与页面交叉验证；标注「用户确认」的条目来自用户口述，未经接口验证。

**补充验证（从面试评价表侧交叉验证）**：逐张比对多张评价表的 `feedbackQuestion` 后，
确认了 `templateCount` 的精确语义与它对孤儿条目的盲区，并把「删除被引用题目」由未验证改为已实证
（不拦截、不清理引用、留下裸 id 悬空引用）。同时确认题库不分社招/校招，而评价表分场景。
交叉验证的细节在 `form-config/interview-feedback-form.md` 的「契约来源」一节里。
