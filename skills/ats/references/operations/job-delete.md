---
route: job-delete
---

# Moka ATS 职位批量硬删除

## 前置鉴权

执行任何操作前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `cllmk auth status` → 登录引导，确认 `data.system === "ats"`。

向用户展示 env / orgName 并确认目标租户后再继续。

## 接口元信息

| 项 | 值 |
|---|---|
| Method | `POST` |
| URL | `/api/outer/ats-jc/job/jobs/deleteJob` |
| Body | `{"jobId":"<UUID>","clientType":"main"}` |
| 鉴权 | Cookie（`cllmk curl` 自动注入） |
| 批量能力 | **无**，仅接单个 jobId，批量靠串行循环 |
| 语义 | **硬删除**，不可逆 |

### 校招 vs 社招

**同一个端点**。浏览器抓包时校招/社招仅在 `moka-tracing.scenario` 头
（`campus` / `social`）不同。cllmk curl 不主动传该头也能删除成功
（实测校招 + 社招两种职位都跑通），因此本路由 不区分场景。

### 前置条件（后端强制）

**职位下必须没有招聘中候选人**才能删除。此校验由后端拦截，本路由 不做预检。

### 响应分类（实测）

| 类别 | 判定条件 | 是否重试 |
|---|---|---|
| ✅ 成功 | `code=0 AND data.success=true AND data.code=0 AND data.msg="成功"` | — |
| 🌐 网络失败 | `cllmk` 退出码 ≠ 0，或响应含 `"Client network socket disconnected"` / `ECONNRESET` / `ETIMEDOUT` / `socket hang up` | **结果未知，不自动重试；先回读职位状态** |
| 🚫 业务失败 | `code=0 AND data.success=false`，`data.code` 见错误码字典 | **不重试** |

#### 已知业务错误码

| `data.code` | `data.msg` | 说明 |
|---|---|---|
| `704023` | 当前职位下有招聘中候选人， 不能进行删除 | 需先移动候选人再删 |
| `704024` | 有关联职位，不能进行删除 | 需先在 UI 解除职位关联关系再删 |
| `705004` | 职位不存在 | 职位已被删除或从未存在；可视为"已完成" |

其他错误码尚未收集，遇到后按 `OTHER_FAIL` 记录并回填此表。

### 成功/失败样本

成功：
```json
{"code":0,"data":{"code":0,"codeType":0,"msg":"成功","success":true},"msg":""}
```

业务失败（704023）：
```json
{"code":0,"data":{"code":704023,"codeType":0,"msg":"当前职位下有招聘中候选人， 不能进行删除","opNo":"...","source":"ats-jc","success":false},"msg":""}
```

## 子场景路由

| 用户意图 | 执行 |
|---|---|
| 提供 xlsx / csv 路径 → 大批量删 | 走脚本模式 |
| 直接给 < 5 个 jobId → 一次性删 | 走脚本模式（`--job-id`），仍需 `--confirm` |
| 只删 1 个 jobId | 可直接 `cllmk curl` 一发，不必走 skill；但走 skill 有 dry-run 保护更稳 |

## 脚本模式

### 执行前 4 项确认（缺一不可）

1. **环境与租户** —— `cllmk auth status` 显示的 env / orgName 是不是目标？
2. **数据规模** —— 读取输入得到总条数，估算耗时（`N × (interval + 0.5s)`，
   默认 interval=1.5s，所以约 `N × 2s`）
3. **不可逆** —— 硬删除，明示不可逆，请用户确认
4. **产出位置** —— live 模式在输入文件同目录（或 `--workdir`）生成
   `delete.log` / `report.xlsx` / `state.json`；预览使用 `preview.log` /
   `preview-report.xlsx`，不会覆盖 live 结果

### 运行

调用脚本 `<skill-dir>/scripts/job-delete/bulk_delete.py`。**默认 dry-run**，只打印不实际调用；
加 `--confirm` 才真删：

```bash
# xlsx 输入（首列 jobId），dry-run 预览
python3 <skill-dir>/scripts/job-delete/bulk_delete.py \
  --input <path-to-xlsx-or-csv> \
  --id-column jobId

# xlsx 输入，真删
python3 <skill-dir>/scripts/job-delete/bulk_delete.py \
  --input <path-to-xlsx-or-csv> \
  --id-column jobId \
  --confirm \
  --expected-org-id <orgId>
```

命令行直传（少量 UUID）：

```bash
python3 <skill-dir>/scripts/job-delete/bulk_delete.py \
  --job-id 1caca481-a244-4bab-a13c-719b7b52f399 \
  --job-id 3c2325d3-16c5-43dd-93e2-04c35b6b7806 \
  --workdir /tmp/job-del-xxx \
  --confirm \
  --expected-org-id <orgId>
```

主要参数（详见 `--help`）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | — | xlsx / csv 输入路径（与 `--job-id` 二选一） |
| `--job-id` | — | 单个 jobId，可重复 |
| `--id-column` | 首列 | xlsx / csv 列名或 0-based 列号 |
| `--workdir` | 输入文件同目录 | 日志与 report.xlsx 输出目录 |
| `--interval` | `1.5` | 相邻调用间隔（秒） |
| `--confirm` | — | 关闭默认预览，进入真删模式 |
| `--expected-org-id` | — | 与 `--confirm` 同时提供，必须与实时 current orgId 完全一致 |

### 脚本行为

- **UUID 格式校验**：输入非 UUID 的行会被跳过并计入 `SKIPPED_INVALID`
- **去重**：同一 jobId 只删一次
- **断点续跑**：`state.json` 记录 `next_index`，同 workdir 再跑会跳过已处理条目
- **租户防串（org guard）**：live 模式要求 `--expected-org-id` 与实时 current orgId 一致，并拒绝非空 `CLLMK_PROFILE`；orgId 写入 `state.json`，续跑时租户不一致立即拒绝
- **网络结果未知不重试**：单条网络失败时不自动重试，先查询职位是否仍存在
- **业务失败不重试**：直接归档到报告
- **报告**：live 写 `report.xlsx`，预览写 `preview-report.xlsx`；列 `jobId / status / errorCode / detail / opNo / attempts`
  - status ∈ `OK` / `BUSINESS_FAIL` / `NETWORK_FAIL` / `OTHER_FAIL` / `SKIPPED_INVALID`

### 长时间运行建议

大批量（>500 条）时，脚本仍是串行 `N × 2s`，估算耗时后再决定：

- 500 条约 17 分钟；2000 条约 67 分钟
- 后台运行 `python3 ... &` 或用 Claude Code `run_in_background`
- 用 `tail -F <workdir>/delete.log | grep -E "FAIL|EXC|DONE"` 只看异常
- 不要每条都汇报给用户，只报里程碑（每 100 条）与最终战报

## 安全约束

- **禁止**在未提供 `--confirm --expected-org-id <orgId>` 且实时 current 不匹配时执行真删
- **禁止**跳过业务失败重试（704023 等业务码代表前置校验失败，重试无意义且刷限流）
- **禁止**并发调用（后端未验证并发安全，串行更稳）
- **禁止**展示或记录 Cookie 明文

## 不在本路由 覆盖范围

| 需求 | 应使用 |
|---|---|
| 关闭 / 暂停 / 归档职位（软变更） | 暂未覆盖 |
| 职位下候选人移动 / 清理 | `cllmk` 的 `talent-pool-candidate-delete` 或 `application-move-stage` 路由 |
| 职位自定义字段 | `cllmk` 的 `job-field-manage` 路由 |
| 招聘需求（HC）字段 | `cllmk` 的 `hc-field-manage` 路由 |
