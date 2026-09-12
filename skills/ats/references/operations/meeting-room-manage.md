---
route: meeting-room-manage
---

# Moka ATS 会议室管理（Meeting Room）

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

本路由通过 `cllmk curl` 管理 Moka ATS 的公司会议室（UI 位置：`/settings/meeting_rooms`），只做两件事：
**查询会议室列表**、**开启或关闭单个会议室的「面试是否可用」**。

统一前缀 `/api/outer/ats-common/room/meeting-rooms/`，全部 `POST`：

| 动作 | 端点 | payload | 读/写 |
|---|---|---|---|
| 查询会议室列表 | `search` | `{"type":"ALL","displayInvisible":true}` | 读 |
| 开启 / 关闭「面试是否可用」 | `updateVisible` | `{"id":"<会议室 id>","visible":true}` | **写** |
| 读「使用会议室」总开关 | `feature/enabled` | `{}` | 读 |
| 读当前生效的会议室来源 | `vendors/setting` | `{}` | 读 |
| 读可用的会议室来源清单 | `vendors/available` | `{}` | 读 |
| 读多组织（应用）会议室状态 | `vendors/multi-app/status` | `{}` | 读 |
| 读会议室来源的展示元信息 | `listLocationVendor` | `{}` | 读 |

**本路由只有 `updateVisible` 一个写接口。** 其余六个都是只读，用于写之前的前置确认。

## 目录

- 覆盖范围与边界
- 前置鉴权与租户护栏
- 上位开关：改 visible 之前必须先读的两个状态
- 数据模型
- 三个必须先知道的陷阱
- 查询会议室
- 开启 / 关闭「面试是否可用」
- 错误码
- 安全约束
- 不在本路由覆盖范围
- 验证说明

---

## 覆盖范围与边界

| 项 | 结论 |
|---|---|
| 「面试是否可用」的字段 | 会议室对象上的 `visible`（布尔）。UI 列名叫「面试是否可用」，值展示为「是 / 否」 |
| 社招 / 校招是否隔离 | **不隔离**。页面标题旁挂「全局」标签，会议室是组织级配置。本路由**不需要**按 `currentHireMode` 分流，也不必在操作前读 `org/info` 判场景（未在校招会话下比对过，见「验证说明」） |
| 会议室来源（vendor） | 租户同一时刻**只有一个**来源生效，由 `vendors/setting` 决定，**不由请求参数决定**。`search` 只返回当前生效来源下的会议室 |
| 分页 | **没有分页**。`search` 一次返回全部会议室 |
| People 人事系统 | 无对应概念，不涉及 |

### 会议室来源（vendor）是租户级状态，不是请求参数

`search` 的 `type` 参数**不做过滤**（见「三个必须先知道的陷阱」第 1 条）。返回哪家来源的会议室，
完全由 `vendors/setting` 返回的 `vendor` 决定。要确认当前生效的是哪家：

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/vendors/setting \
  --method POST --payload '{}'
```

`vendors/available` 会返回租户可选的全部来源及其可用性（布尔 map），`listLocationVendor` 返回这些来源在
UI 上的展示名与描述（带 i18n）。这两个接口只用于**向用户解释「当前在操作哪家来源的会议室」**，
本路由不改它们。

---

## 前置鉴权与租户护栏

执行任何操作前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `CLLMK_PROFILE` 为空 → 需要时按 `foundation/tenant-switch.md` 切换 current → 裸 `cllmk auth status`，
确认 `data.system === "ats"` 且 `orgId` / `orgName` / `env` 与目标一致。

向用户展示 env / orgName 并确认目标租户后再继续。

### 每条写请求前重新断言 orgId（强制）

会议室 `id` 是租户内分配的，跨租户复用只会落到别人的数据上或报错。**不要只在流程开头查一次 status**，
每条 `updateVisible` 之前重新确认 orgId，并用 `&&` 短路 —— 用 `;` 串联会在 status 失败后照样发出写请求：

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

guard && cllmk curl --url /api/outer/ats-common/room/meeting-rooms/updateVisible \
  --method POST --payload '{"id":"<会议室 id>","visible":false}'
```

**样例 id 一律运行时获取。** 本文所有 `id` 都是占位符，禁止照抄历史 curl 或文档里的数字。

---

## 上位开关：改 visible 之前必须先读的两个状态

单个会议室的 `visible` 是**最底层**的开关，它上面还压着两层租户级开关。上位开关关着的时候，
`updateVisible` **照样返回成功**，但安排面试时页面上一个会议室都看不到 —— 用户会以为是这次改动把功能改坏了。

> **强制**：执行 `updateVisible` 之前，先读这两个状态并向用户明示。

**1. 「使用会议室」总开关**

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/feature/enabled \
  --method POST --payload '{}'
```

`data.data` 为 `true` 表示总开关开启。为 `false` 时**停止写入**，告诉用户「公司会议室功能整体处于关闭状态，
改单个会议室的可用性不会产生任何效果，请先在 `/settings/meeting_rooms` 打开『使用会议室』」。
**本路由不覆盖该开关的写接口，不要尝试构造。**

**2. 当前生效的会议室来源**

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/vendors/setting \
  --method POST --payload '{}'
```

把返回的 `vendor` 与目标会议室对象上的 `vendor` 字段比对。两者不一致说明用户说的会议室不在当前生效来源下，
**停止写入**并向用户说明，不要自行切换来源。

「开启多组织（应用）会议室」是第三个开关（`vendors/multi-app/status`，返回
`{"enabled":<bool>,"status":"<状态>","statusUpdatedAt":<毫秒时间戳>,"version":"1.0"}`）。
它影响的是多组织场景下会议室的归属范围，与单个会议室的 `visible` 不构成上下位关系，
**按需读取即可，不作为写入门禁**。

---

## 数据模型

`search` 返回的数组里每一项（实测 13 个字段，全部会议室上都存在，无缺键）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | **字符串** | 会议室 ID。⚠️ 是 9 位数字组成的**字符串**，`updateVisible` 必须原样回传字符串，**不要转成数字** |
| `name` | 字符串 | 会议室名称，UI 列「会议室名称」 |
| `visible` | 布尔 | **「面试是否可用」**。`true` = UI 显示「是」，操作列是「关闭」；`false` = 显示「否」，操作列是「开启」 |
| `building` | 字符串 | ⚠️ **UI 列「会议室层级」对应的就是这个字段**，形如 `<洲> <国家> <地区> <城市>`。不是 `location.address` |
| `vendor` | 字符串 | 会议室来源。与 `vendors/setting` 的 `vendor` 比对，见「上位开关」 |
| `orgId` | 字符串 | 所属租户，用于核对是否串号 |
| `locationId` | **数字** | 地点 ID |
| `location` | 对象 | 地点详情，含 `id` / `address` / `type` / `visible` / `isTemp` / `orgId` / `thirdPartyUniqueId` / `userId` / `version` |
| `size` | 数字 | 容纳人数 |
| `devices` | 字符串 | 设备清单，**逗号分隔的单个字符串**（如 `电视,白板`），不是数组；无设备时是空串 |
| `thirdPartyId` | 字符串 | 第三方系统里的会议室 ID（36 位 UUID 形态） |
| `meetingRoomGroupId` | 数字 | 会议室分组 ID |
| `version` | 字符串 | 实测恒为 `"1.0"` |

### `locationId` 与 `location.id` 类型不同

两者数值相同，但 `locationId` 是**数字**、`location.id` 是**字符串**。做等值比较时必须先统一类型，
直接 `==` 会得到 false。

### 不要用 `name` 作为操作依据

`name` 在实测样本里恰好无重名，但**接口没有暴露任何唯一性约束**，也没有按名称查询的端点。
**禁止**仅凭会议室名称执行 `updateVisible` —— 必须先 `search` 回读拿到 `id`，并由用户确认对象。

---

## 三个必须先知道的陷阱

### 1. `type` 是必填参数，但完全不做校验、也不做过滤

这是本接口最反直觉的地方。实测：

| 传值 | 结果 |
|---|---|
| 省略 `type` | `code: -1`、`msg: "系统错误"`、`success: false`。**这是未处理异常泄漏，不是业务码** |
| `"type": null` | 同上，`-1 系统错误` |
| `"type": ""` | **成功**，返回全量 |
| `"type": 123` | **成功**，返回全量 |
| `"type": "ALL"` / `"MOKA"` / `"DINGTALK"` / 任意不存在的字符串 | **成功，返回结果完全一致** |

含义：

- `type` 这个键**必须存在且非 `null`**，否则接口抛异常。
- 它的**值不起任何作用** —— 既不过滤来源，也不校验合法性。返回哪家来源的会议室由租户级
  `vendors/setting` 决定（见「上位开关」）。
- **禁止把 `type` 当成来源筛选参数使用**，也禁止因为「传了 `MOKA` 也返回数据」就得出「该租户有 Moka 会议室」的结论。

本路由一律固定传 `"type":"ALL"`。

### 2. `displayInvisible` 决定能不能看见被关掉的会议室

| 传值 | 返回 |
|---|---|
| `"displayInvisible": true` | 全部会议室，**含 `visible:false` 的** |
| `"displayInvisible": false` | 只含 `visible:true` 的 |
| 省略 | 同 `false`，**只含 `visible:true` 的** |

实测同一租户：省略时 102 条、全部 `visible:true`；传 `true` 时 104 条、其中 2 条 `visible:false`。

> **强制**：本路由的所有查询一律显式传 `"displayInvisible":true`。
> 漏传会让已关闭的会议室**整条消失**，模型会据此报告「不存在这个会议室」，而实际上它只是被关了。

### 3. `updateVisible` 的成功响应里**没有 `data` 键**

```json
{"code":0,"codeType":0,"msg":"成功","success":true}
```

没有 `data`，也就没有任何字段回显。后果：

- 拿不到写入后的实际值。
- 解析时**禁止**访问 `data.data`，会 KeyError / NPE。
- **写操作之后必须调 `search` 回读确认**，不能拿响应当结论。

---

## 查询会议室

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/search \
  --method POST --payload '{"type":"ALL","displayInvisible":true}'
```

会议室数组在 `data.data`（注意双层 `data`：外层是 `cllmk` 包络，内层是服务端响应体）。

### 响应体积大，禁止直接打到终端

实测单租户 104 个会议室约 **49 KB**，且**没有分页参数可用**（`pageSize` 之类的键会被忽略）。
按 `<skill-dir>/SKILL.md` 的全局安全规则，必须先解析再输出：

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/search \
  --method POST --payload '{"type":"ALL","displayInvisible":true}' | python3 -c "
import json,sys
r=json.load(sys.stdin)
d=r.get('data') or {}
if not d.get('success'):
    print('业务失败:', d.get('code'), d.get('msg')); sys.exit(1)
rooms=d.get('data') or []
on=[x for x in rooms if x['visible']]
print(f'共 {len(rooms)} 个会议室：可用 {len(on)} / 不可用 {len(rooms)-len(on)}')
for x in rooms:
    print(f\"  id={x['id']} name={x['name']!r} visible={x['visible']} building={x['building']!r}\")
"
```

**不要**用 `--filter data.data` 来「裁剪」—— 会议室数组就是响应的主体，过滤后体积不变。
确实需要按下标取单条时，注意 `--filter` 的数组下标语法只在 CLI `>= 0.2.0` 上可用；
`0.1.1` 不能进入数组且**静默返回 `null`**，会被误判成「租户没有会议室」。优先用上面的 Python 解析。

### 按名称定位某个会议室

接口**没有**按名称查询的端点，只能全量拉回后本地筛：

```bash
cllmk curl --url /api/outer/ats-common/room/meeting-rooms/search \
  --method POST --payload '{"type":"ALL","displayInvisible":true}' | python3 -c "
import json,sys
kw=sys.argv[1]
rooms=(json.load(sys.stdin).get('data') or {}).get('data') or []
hits=[x for x in rooms if kw.lower() in x['name'].lower()]
print(f'命中 {len(hits)} 条')
for x in hits:
    print(f\"  id={x['id']} name={x['name']!r} visible={x['visible']} vendor={x['vendor']}\")
" "<会议室名称关键词>"
```

命中 0 条或多条时**停止**，把结果报给用户让其指定，不要自行挑一条执行写入。

### 向用户呈现

以 Markdown 表格呈现，至少包含：会议室名称、会议室层级（`building`）、面试是否可用（`visible` → 是 / 否）、
`id`。**`visible` 必须展示** —— 它是后续开关操作的判断依据。

---

## 开启 / 关闭「面试是否可用」

```bash
guard && cllmk curl --url /api/outer/ats-common/room/meeting-rooms/updateVisible \
  --method POST --payload '{"id":"<运行时获取的会议室 id>","visible":false}'
```

| 参数 | 说明 |
|---|---|
| `id` | **字符串**，从 `search` 回读获得。传数字的行为未验证，**一律传字符串** |
| `visible` | `true` = 开启（UI「开启」按钮，面试时可选）；`false` = 关闭（UI「关闭」按钮） |

### 语义

- 这是**可逆**操作，关闭后仍可再开启，会议室本身不会被删除。
- 关闭后该会议室**从默认查询里消失**（`displayInvisible` 省略时看不到），但仍在 `displayInvisible:true` 的结果里。
- 实测写操作后**列表顺序不变**，目标会议室仍在原位置。

### 执行流程

1. 读「使用会议室」总开关与当前生效来源，确认上位开关就绪（见「上位开关」一节）。总开关为 `false` 时停止。
2. `search`（带 `displayInvisible:true`）回读目标会议室，拿到 `id` / `name` / `building` / `visible` / `vendor`，
   展示「改前」状态。
3. 比对目标会议室的 `vendor` 与 `vendors/setting` 的 `vendor`，不一致则停止。
4. 目标 `visible` 已经等于期望值时，**告知用户无需改动并停止**，不要发出空转的写请求
   （重复写同一值的行为**未验证**，见「错误码」）。
5. 向用户展示完整 payload 与将要改动的会议室，等待显式确认。
6. `guard && cllmk curl ...` 执行。
7. **再次 `search` 回读**，用回读结果展示「改后」状态。响应里没有 `data`，**不能**拿 `success:true` 当作字段已生效的证据。

### 批量开关

没有批量端点。批量只能串行循环单条接口，并且：

- 每条写入前都重新跑 `guard`（orgId 可能在任务中途被别的流程切走）。
- 逐条记录「原值 → 目标值 → 实际回读值」，全部执行完后一次性回读 `search` 做总账核对。
- 任何一条返回非 `success` 时**停止整批**，把已改动的条目报给用户，不要继续往下跑。

---

## 错误码

实测到的只有两个分支，**其余错误码尚未收集**：

| `data.code` | `data.msg` | 触发条件 |
|---|---|---|
| `0` | 成功 | — |
| `-1` | 系统错误 | `search` 省略 `type` 或传 `type: null`。**这是未处理异常泄漏，不是业务码** |

### 判定成败只看内层

业务失败时 HTTP 仍是 **200**、`cllmk` 外层仍是 `code:0`，只有内层 `success:false`。
**判定成败只看 `data.success` 与 `data.code`。**

### 以下分支未验证，遇到即停止

- `updateVisible` 传**不存在的 `id`**
- `updateVisible` 传**属于其他租户的 `id`**
- `updateVisible` **省略 `visible`** 字段
- `updateVisible` **重复设置同一个值**（幂等性）

遇到上述任一情况返回的错误码，**禁止猜测其含义**，也**禁止**按「重试一次就好」处理。
停止写入，把原始响应（去掉凭证）报给用户，并说明需要补充实测才能写进本文档。
批量任务中出现未知错误码时，**不得**把它当成「已成功」计入结果。

---

## 安全约束

- **禁止**把 `cllmk` 外层 `code:0` 当成业务成功；只认 `data.success` / `data.code`。
- **禁止**访问 `updateVisible` 响应的 `data` 键 —— 成功响应里没有这个键。
- **禁止**把 `updateVisible` 的 `success:true` 当作字段生效的证据；写后一律 `search` 回读。
- **禁止**在查询时省略 `displayInvisible:true`，也禁止据此报告「会议室不存在」。
- **禁止**省略 `type` 或传 `null`（接口抛 `-1 系统错误`）；一律固定传 `"type":"ALL"`。
- **禁止**把 `type` 当来源筛选参数，或据其取值推断租户有哪些来源的会议室。
- **禁止**把 `id` 转成数字下发；一律原样传字符串。
- **禁止**仅凭会议室名称执行写入；必须先回读 `id` 并由用户确认对象。
- **禁止**在未确认「使用会议室」总开关为 `true` 的情况下执行 `updateVisible`。
- **禁止**猜测未验证分支的错误码含义或构造未覆盖端点的 payload（§5 红线 3）。
- **禁止**用 `;` 串联 status 与写请求；必须 `&&` 短路。
- **禁止**把整份 `search` 响应打到终端或读进上下文；必须先解析。
- **禁止**展示或记录 Cookie 明文。用户贴带 `-b` 的 curl 时提醒去掉 Cookie 段，改用 `cllmk curl` 复现。

---

## 不在本路由覆盖范围

| 需求 | 说明 |
|---|---|
| 开启 / 关闭「使用会议室」总开关 | 只覆盖读（`feature/enabled`）。写接口未捕获，**不要构造**；请用户在 `/settings/meeting_rooms` 手工操作，或提供 UI curl 后再扩展本路由的覆盖范围 |
| 停用 / 启用某个会议室来源（卡片上的「停用」「开启使用」） | 写接口未捕获。这类操作影响全租户的面试安排，**一律不允许猜 payload**；需要用户提供 UI curl |
| 切换会议室来源（如从飞书切到钉钉） | 同上，写接口未捕获 |
| 开启 / 关闭「多组织（应用）会议室」 | 只覆盖读（`vendors/multi-app/status`）。写接口未捕获 |
| 新增 / 删除 / 改名会议室 | 未见对应端点。UI 上「Moka 会议室」支持自行添加，但该入口的接口未捕获 |
| 修改会议室的容量、设备、地点、分组 | `search` 返回 `size` / `devices` / `locationId` / `meetingRoomGroupId`，但**没有**对应的写端点 |
| 会议室分组管理 | `meetingRoomGroupId` 只在响应里出现，分组本身的增删改查未覆盖 |
| 地点（location）管理 | `location` 只作为会议室的只读附属信息返回；地点本身的管理不在本 skill 覆盖范围 |
| 把会议室绑定到具体面试 / 面试轮次 | 不在本 skill 覆盖范围。本路由只管会议室在面试安排里**是否可选**，不管实际占用 |
| 会议室占用情况、空闲查询、预定记录 | 未见端点，不在本 skill 覆盖范围 |
| 第三方系统（飞书 / 钉钉）侧的会议室本体 | 会议室数据由第三方同步而来（`thirdPartyId`）。在第三方后台增删会议室不在本 skill 覆盖范围 |
| People 人事系统的会议室 | 无此概念 |

---

## 验证说明

本文的行为结论来自在浏览器上对真实租户的接口实测（读接口直接调用，写接口通过界面操作抓包复现），
样本为单一租户、单一会议室来源。以下几点**未经验证**，使用时按「错误码」一节的规定停止并回报：

- `updateVisible` 的错误分支：不存在的 `id`、跨租户 `id`、省略 `visible`、重复设置同一值的幂等性。
- `updateVisible` 的 `id` 传数字类型的行为。
- 校招会话下 `search` 的返回是否与社招一致（页面标记为「全局」，推断不分场景，但未在校招会话下比对）。
- 多个会议室来源同时可用时 `search` 的返回形态（实测租户只有一个来源生效）。
- `cllmk curl` 的外层包络形态按本仓库既有约定书写（外层 `code` + `data` 承载服务端响应体），
  本轮实测走的是浏览器直连，**未经 `cllmk curl` 实跑验证**。首次执行时若外层结构与本文不符，
  以实跑为准并回填本文档。
