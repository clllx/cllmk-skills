---
route: application-delete
---

# Moka ATS 删除候选人 / 申请

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–6），确认 `data.system === "ats"`。

## 拒信硬约束（务必先读）

本路由 **永久禁用拒信**：`refuseMail.send` 硬编码为 `false`，CLI 不提供任何
开启入口。如需发拒信请在 UI 操作，绝不通过本路由。

## 接口元信息

### 单删

| 项 | 值 |
|---|---|
| Method | `PUT` |
| URL | `/api/outer/ats-candidate/application/delete` |
| Body | `{"type":"application\|candidate","applicationId":<int>,"refuseMail":{...send:false}}` |

### 批删

| 项 | 值 |
|---|---|
| Method | `POST` |
| URL | `/api/outer/ats-candidate/application/bulk/delete` |
| Body | `{"applicationIdList":[<int>,...],"type":"application\|candidate","refuseMail":{...send:false}}` |

### type 语义

| type | 效果 |
|---|---|
| `application` | 只删这份申请，候选人主档保留 |
| `candidate` | 连同候选人主档一起删除（**该候选人所有申请一并消失**，不可逆） |

### 响应分类

| 类别 | 判定 | 处置 |
|---|---|---|
| ✅ 成功 | `code=0 AND data.success=true` | — |
| 🌐 网络失败 | `cllmk` 退出码 ≠ 0，或响应含 socket 断开字样 | **结果未知，不自动重试；先回读业务状态** |
| 🚫 UNIQUE_APPLICATION | code=400059 或 msg 含 "不能删除候选人唯一的申请" | 运行时拦截，见下 |
| 🚫 BIZ_FAIL | 其它业务失败 | 写日志，不重试 |

## 子场景路由

| 用户意图 | 执行 |
|---|---|
| 单个 applicationId | `--type <t> --ids <id>`（自动走单删 PUT） |
| < 30 条 ID，随手删 | `--type <t> --ids id1,id2,...` |
| xlsx / csv 大批量 | `--type <t> --input <path>` |
| 事后救场（曾选 S 的想再删） | `--rescue --workdir <之前目录>` |

## CLI 契约

入口脚本：`<skill-dir>/scripts/application-delete/bulk_delete.py`

### 必需参数

- `--type application` 或 `--type candidate` —— **无默认**，缺参数直接报错退出
- `--ids` 或 `--input` 二选一

### 可选参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--id-column` | 第 1 列 | xlsx / csv 的 ID 列名或列号 |
| `--batch-size` | `30` | 每批条数 |
| `--interval` | `2.0` | 批间隔秒 |
| `--workdir` | 输入同目录或 `/tmp/ats-app-del-<ts>` | 日志输出目录 |
| `--no-bulk` | off | 禁用 bulk 端点，逐条 PUT |
| `--dry-run` | off | 显式预览；未提供 `--confirm` 时同样只预览 |
| `--confirm` | off | 允许不可逆删除 |
| `--expected-org-id` | — | 与 `--confirm` 同时提供，必须与实时 current orgId 完全一致 |
| `--rescue` | off | 事后救场：重跑 skip.log 里的 ID（需 TTY 确认，type 强制 candidate） |

## 执行前 5 项确认（缺一不可）

跑批前逐条与用户对齐：

1. **环境与 org** —— `cllmk auth status` 显示的 env / org 是不是目标？
2. **type 与破坏范围** —— 本轮是删申请还是删候选人？覆盖多少行？
3. **数据规模** —— `ceil(N/30) × 3.3s` 估算耗时
4. **不可逆确认** —— 删除不可逆
5. **日志目录可写确认**

真实删除命令必须同时包含 `--confirm --expected-org-id <已确认的orgId>`；缺少任一项都只预览或终止。

## 400059 运行时拦截

bulk 请求返回 400059 时，脚本先把该批 ID 逐条以 `type=application` 重扫：

- 单条成功：完成用户原本授权的申请删除，不进入升级池
- 单条仍返回 400059：确认为唯一申请，进入待确认清单
- 单条网络失败：结果未知，不重试且不进入升级池
- 其它业务失败：记录后停止，不进入升级池

主轮结束后，仅对逐条重扫确认的 UNIQUE_APPLICATION 展示：

```
⚠️  检测到 UNIQUE_APPLICATION（400059）
   本轮 --type=application，有 N 个 applicationId 是候选人唯一申请，无法删除。
   请选择本轮所有 400059 的处置：
     [E] 升级到 type=candidate 删除（把候选人整体删掉，破坏范围放大）
     [S] 全部跳过并记录（保守）
     [A] 立刻终止
```

**无 TTY 环境**（后台 / 无标准输入）：默认 **S**（跳过），绝不静默升级。

E 分支会在 `<workdir>/escalate.authorization` 落盘授权审计，然后用
`type=candidate` 通过 bulk 端点删除，日志到 `escalate.log`。

## 长时间运行

大批量（>1000 条）耗时约 `ceil(N/30) × 3.3s`。建议：
- `python3 ... &` 后台跑，或用 Claude Code 的 `run_in_background`
- `tail -F <workdir>/run.log | grep -E "FAIL|ESCALATE|DONE"` 只监控异常和里程碑
- 不要每批汇报给用户，只在异常率或重大节点汇报

## 输出文件

```
<workdir>/
├── state.json           # {"next_batch": N, "type": "...", "input_hash": "...", "orgId": "..."}
├── delete.log           # 主轮 jsonl
├── escalate.log         # 400059 → E 分支 jsonl
├── skip.log             # 400059 → S 分支 jsonl
├── run.log              # 人可读进度日志
├── unique_application.pending  # 400059 收集清单
├── escalate.authorization      # E 分支审计
├── rescue.authorization        # --rescue 审计
└── summary.json         # 最终战报
```

## 租户防串保护（org guard）

- 启动时脚本拒绝非空 `CLLMK_PROFILE`，再调 `/api/v2/org/info` 取 current 会话的 orgId 并打印；取不到 orgId 直接中止，不发任何删除请求
- orgId 写入 state.json；续跑时若当前会话租户与 state.json 不一致，立即拒绝
- `--rescue` 同样校验：skip.log 来自哪个租户，就只能在那个租户的会话下救场
- 第一次 live 运行也要求 `--expected-org-id` 与实时 current orgId 完全一致，不只依赖续跑 state
- DELETE/PUT/POST 网络失败不自动重试；结果可能已经生效，必须先回读确认
- 跨租户任务必须串行执行 `cllmk auth switch → cllmk auth status → 本租户删除任务`；同一配置目录不得并行跑不同租户，且不同租户的 workdir 必须分开

## 不在本路由覆盖范围

| 需求 | 应使用 |
|---|---|
| 从人才库移除候选人 | `cllmk` 的 `talent-pool-candidate-delete` 路由 |
| 候选人字段 / 登记表 | `cllmk` 的 `candidate` 路由 |
| 招聘需求字段 | `cllmk` 的 `hc-field-manage` 路由 |
| 职位字段 | `cllmk` 的 `job-field-manage` 路由 |
| 简历保留期限 | `ats-resume-retention` |
| 通过 UI 发拒信删除 | 不覆盖（拒信永久禁用） |
