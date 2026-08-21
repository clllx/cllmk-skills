---
route: protection-period-country
---

# ATS 渠道保护期 — 职位级别方案 / 国家维度

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

本路由通过 `cllmk curl` 在 Moka ATS 中**批量管理渠道保护期规则**：列出现有规则、新建国家维度的规则、调整规则优先级。

> URL 前缀：`/api/outer/ats-jc/channel/protectionPeriod/*`
>
> 设置页：`https://<host>/settings/protection_period_setting`

---

## 0. 作用域确认（必须先做）

保护期在 Moka 系统里有**多种形态**，本路由仅覆盖其中一种。**触发后第一步必须向用户确认作用域**，避免越权操作：

| 形态 | 本路由是否处理 |
|------|-------------------|
| 后台**开启**「职位级别的保护期方案配置」+ 按**国家/地区**分组 | ✅ **本路由唯一覆盖范围** |
| 后台**开启**「职位级别的保护期方案配置」+ 按**部门**分组 | ❌ 字段组合不同，未覆盖 |
| 后台**未开启**职位级别方案，使用标准全局保护期 | ❌ 接口路径不同，未覆盖 |
| 候选人简历/人才库数据保留时长 | ❌ 走 `ats-resume-retention` skill |

**话术示例**：
> 这套接口仅覆盖「后台开启了职位级别保护期方案 + 按国家/地区分组」的场景。你的租户是这种配置吗？如果是按部门或者没开职位级别方案，本路由不适用，我需要你给一份 UI 操作的 curl 才能反推接口。

确认后再进入下一步。

---

## 1. 鉴权检查

调用前按 `<skill-dir>/SKILL.md` 的业务公共前置完成：`command -v cllmk` →
必要时切换 current → `cllmk auth status` → `code:0` 且 `system=="ats"`。

若是登录到 People 或未登录，按 `references/foundation/auth.md` 的「登录流程」执行 `cllmk ats <env> auth login`（一般 `intl` 是 hire-r1），用户只在弹出的 Chrome 里完成认证。

---

## 2. 三个接口

所有接口都是 POST，payload 是 JSON。

### 2.1 List — 查所有规则

```bash
cllmk curl --url /api/outer/ats-jc/channel/protectionPeriod/list --method POST --payload '{}'
```

返回 `data.data` 是一个数组，每条结构：

| 字段 | 含义 |
|------|------|
| `id` | 规则自身 id（**用于 changePriority**） |
| `ruleId` | 规则引擎内部 id（不是同一个东西，不用） |
| `name` | 规则名（一般等于国家名） |
| `priority` | 优先级数值，**越大越靠前**；系统维护连续 1..N |
| `enabled` | 是否启用 |
| `lastModifyTime` / `lastModifyUserName` | 最后修改信息 |

⚠️ 响应数据较大，必要时 jq 投影 `.data.data | map({id,name,priority})` 输出。

### 2.2 Create — 新建国家维度规则

```bash
cllmk curl \
  --url /api/outer/ats-jc/channel/protectionPeriod/create \
  --method POST \
  --payload '<JSON>'
```

Payload 结构（详见同目录 `api-templates.md`）：
- `name`：规则名 = 国家名
- `ruleConditionData`：JSON 字符串（前端规则引擎结构），内嵌 `orgId` / 国家名 / 3 个随机 UUID
- `content`：保护期具体数值（**由用户提供，不要写死**，见第 3 节）

返回 `{code:0, data.success: true}` 表示成功。响应**不包含**新规则的 id，需要后续 list 才能拿到。

### 2.3 changePriority — 改优先级

```bash
cllmk curl \
  --url /api/outer/ats-jc/channel/protectionPeriod/changePriority \
  --method POST \
  --payload '{"id":<规则id>,"priority":<目标值>}'
```

#### ⚠️ 语义不对称（踩过坑，请认真读）

系统维护**连续 1..N** 的优先级。同一调用，**向上移动**和**向下移动**结果不同：

| 方向 | old_p / new_p 关系 | 规则最终落点 | 区间内其他规则的位移 |
|------|---------------------|---------------|---------------------|
| **UP**（顶到更前） | `priority > old_p` | priority（**精确等于**） | `[old_p+1, priority]` 全部 **-1** |
| **DOWN**（移到更后） | `priority < old_p` | **priority + 1**（off-by-one） | `[priority+1, old_p-1]` 全部 **+1** |

**实用结论：**
- 想「顶到第一位」：发 `priority = 当前 max`（一般是 246 或当前规则总数），规则就到 #1，其他全部下移一格。
- 想「移到指定第 N 位（从顶往下数）」：算出目标 priority 值 = `total - N + 1`，然后看是 UP 还是 DOWN：
  - UP：发 `priority = target`
  - DOWN：发 `priority = target - 1`
- 批量"按指定顺序排序到顶部 K 个国家"：**逆序**遍历期望列表，每个发 `priority = max`。最后调用的会落到 #1，倒数第二的落到 #2，依此类推。

---

## 3. content 字段（保护期数值，由用户提供）

**永远不要写死保护期天数。**`content` 字段值要么用户直接给，要么从 UI 的 create curl 里取出。

字段清单（Moka 渠道保护期所有可配置项）：

```jsonc
{
  "headhunterLockInProcess": false,        // 猎头-在流程中锁定
  "rpoLockInProcess": false,                // RPO-在流程中锁定
  "recommenderLockInProcess": false,        // 内推-在流程中锁定
  "campusAmbassadorLockInProcess": false,   // 校园大使-在流程中锁定
  "nonInterestChannelLockInProcess": false, // 非感兴趣渠道-在流程中锁定

  "headhunterLockProtect": true,           // 猎头-锁定保护开关
  "headhunterProtectTime": <int>,          // 猎头保护天数（用户给）

  "rpoLockProtect": true,                   // RPO-锁定保护开关
  "rpoProtectTime": <int>,                  // RPO 保护天数（用户给）

  "recommenderProtect": { "enabled": <bool>, "time": <int|null> },        // 内推
  "campusAmbassadorProtect": { "enabled": <bool>, "time": <int|null> },   // 校园大使

  "ownProtect": {
    "enabled": true,
    "time": <int|-1>,            // 自有保护天数；-1 表示永久
    "headhunterTime": <int>,     // 自有-猎头分支
    "campusAmbassador": <int|-1>,// 自有-校园大使分支
    "rpo": <int>                 // 自有-RPO 分支
  },

  "nonInductionTalentPoolLockProtect": false,
  "nonInductionTalentPoolLockProtectTime": null
}
```

**获取规则数值的标准话术：**
> 保护期具体配置（猎头多少天、RPO 多少天、内推/校园大使开不开、自有保护是否永久……）我不能写死。请你给我一份从 UI 上手动建一条规则的 curl（任意一个国家都行），我从 `content` 字段直接复用。

---

## 4. 国家列表（已记忆）

参见同目录 `countries.json`，共 246 个国家名（语言：zh-CN，与 `referer: settings/protection_period_setting` 页面下拉一致）。

> **注意**：`countries.json` 只存**名字**。规则 id 是创建后才有的，需要 `list` 接口实时获取，不要把 id 缓存到 skill 内（不同租户 id 不同）。

---

## 5. 常见任务流程

### 5.1 批量创建国家保护期规则

1. 作用域确认（第 0 节）
2. 鉴权检查
3. 让用户给一份 UI create curl → 提取 `content` 字段
4. 调用 list 接口，得到已存在国家集合 S
5. 用户期望国家集合 = `countries.json` 全集 ∪ 用户指定子集
6. 待创建 = 期望 - S（去重）
7. 用 `<skill-dir>/scripts/protection-period-country/create_batch.py`，传入：
   - `--content-file <path>`：JSON 文件，仅含 `content` 字段内容
   - `--countries <path>`：要创建的国家名清单（一行一个 / 或 JSON 数组）
   - `--skip <names>`：可选，逗号分隔的跳过列表
   - `--delay 0.4`：默认每次 0.4s 间隔
   - `--log <path>`：默认 `result.log`
   - 默认只预览；真实创建必须加 `--confirm --expected-org-id <已确认的orgId>`
8. 跑完核对日志，FAIL 行按错误码诊断

### 5.2 批量调整优先级到指定顺序

1. 作用域确认（同上）+ 鉴权
2. list 拿到所有规则的 `id` + `priority` + `name`
3. 与用户确认期望顺序（前 N 位的精确列表 + 其余是否动）
4. 决策算法：
   - **「把这 N 个国家按这个顺序顶到最前」** → 用 `<skill-dir>/scripts/protection-period-country/reorder_to_top.py`，传：
     - `--order <names>`：期望顺序的国家名（一行一个）
     - `--top-priority <int>`：当前最大 priority 值（一般 = 规则总数）
     - 默认只预览；真实排序必须加 `--confirm --expected-org-id <已确认的orgId>`
     - 脚本内部 **逆序遍历**，每个国家发 `priority=<top-priority>`
   - **复杂自定义**：自己写一次性脚本，注意 UP/DOWN 不对称（见第 2.3 节）

### 5.3 单个/少量规则的优先级微调

直接手写 `cllmk curl` 调用 changePriority。注意发出去之前先 list 确认 id + 当前 priority，**算清楚是 UP 还是 DOWN**。

---

## 6. 失败处理

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `code:1, msg:"HTTP 401"` | 会话失效 | 先跑裸 `cllmk auth status` 确认；确实过期则按 `auth.md`「登录流程」重新执行 `cllmk ats <env> auth login`（status 不会清除凭证，login 会覆盖） |
| `code:1, msg:"HTTP 405"` | list 用了 GET | 改 POST `{}` |
| create 返回 success 但 list 看不到 | 国家名拼写不在 ruleConditionData 里 | 检查 `value.data` 和 `value.title` 是否匹配 |
| changePriority 落点不对 | 没区分 UP/DOWN | 重新计算（第 2.3 节） |
| 批量创建中途 cookie 过期 | 长时间无活动 | 重登后用脚本的 `--start-from <name>` 续跑 |

---

## 7. 文件索引

- `<skill-dir>/scripts/protection-period-country/create_batch.py` — 批量 create，UUID 每条重新生成
- `<skill-dir>/scripts/protection-period-country/reorder_to_top.py` — 按列表逆序顶到 top
- 同目录 `countries.json` — 246 国家名（zh-CN）
- 同目录 `api-templates.md` — create / list / changePriority 的完整 curl + payload 模板
