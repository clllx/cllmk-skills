---
route: application-move-stage
---

# Moka ATS 批量移动应聘阶段

## 前置鉴权

执行任何子流程前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `cllmk auth status` → 登录引导，确认 `data.system === "ats"`。
**同时把 `data.orgId` / `data.env` 明示给用户对齐**——这是本路由 的头号坑，
不同 org 的 stageId 完全不同，跑错 org 会 100% BIZ_FAIL 或误伤。

## 接口元信息

### 主接口：移动阶段

| 项 | 值 |
|---|---|
| Method | `PUT` |
| URL | `/api/outer/ats-pipeline/stage/application/move-stage/v2` |
| Body | `{"applicationId": <int>, "currentStageId": <int>, "stageId": <int>}` |
| 鉴权 | Cookie（`cllmk curl` 自动注入） |
| 语义 | **单条**接口，无 bulk 版本，必须逐条串行 |

### 副接口：拉 stage 映射

| 项 | 值 |
|---|---|
| Method | `GET` |
| URL | `/api/v2/org/info` |
| 关注字段 | `data.stages: [{id, name, type, disabled, ...}]`（org 级、扁平） |
| 用途 | 名字→ID 映射；同时用 `data.orgInfo.orgId` 做状态守卫 |

`data.stages` 是 org 级的扁平数组，实测名字在 org 内唯一。若未来某 org 出现重名，
脚本会**主动报错并列出重复项**，让用户手动澄清，绝不静默取第一个。

## 响应分类（实测）

| 类别 | 判定条件 | 是否重试 |
|---|---|---|
| ✅ 成功 | outer `code=0 AND data.success=true` | — |
| 🌐 网络失败 | cllmk rc≠0 或响应 msg 含 `ETIMEDOUT` / `ECONNRESET` / `socket disconnected` / `hang up` | **结果未知，不自动重试；先回读当前阶段** |
| 🚫 业务失败 | outer `code=0 AND data.success=false`（如"阶段已被他人变更"、"应聘不存在"、"stageId 非法"） | **不重试**（是数据本身问题） |
| 🔐 鉴权失败 | 响应含 `HTTP 401` / `HTTP 403` / `Not logged in` / `Session expired` | **立即整体停跑**（继续也白搭） |

业务失败按行独立，**不存在** talent-pool 那种"整批连坐"问题，所以本路由 **不需要 rescue 模式**。

## 子场景路由

| 用户意图 | 执行 |
|---|---|
| 提供 xlsx/csv 路径 → 批量移动 | 进入「脚本模式」 |
| 只有几条 → 直接给 (appId, from, to) 三元组 | 询问是否要走脚本；如不要，直接 cllmk curl 3 条 |

## 脚本模式

### 输入格式

xlsx 或 csv，**三列**（列名任意，脚本会尝试当第一行是表头处理；也可用 `--app-col` / `--from-col` / `--to-col` 显式指定列名或 0-based 索引）：

| applicationId | fromStage | toStage |
|---|---|---|
| &lt;applicationId&gt; | &lt;当前阶段名&gt; | &lt;目标阶段名&gt; |
| &lt;applicationId&gt; | &lt;当前阶段名&gt; | &lt;目标阶段名&gt; |

- `applicationId` 是数字，非数字行会被跳过
- `fromStage` / `toStage` 是 stage **名字**（精确匹配，含大小写和空格）；脚本自动查 org 拿到对应 ID
- 空 applicationId 行自动跳过

### 执行前 5 项确认

逐条与用户对齐后再开跑（缺一不可）：

1. **环境与 org** —— `cllmk auth status` 显示的 env/org/orgId 是不是目标？跑错 org 会一片 BIZ_FAIL
2. **数据规模** —— 读取输入文件得到总条数；耗时估算 `N × (interval + ~0.5s 接口延迟)`，
   默认 `interval=1s`，即约 `N × 1.5s`
3. **未知 stage 名字** —— 脚本会先跑一遍 `--dry-run` 或输入校验，把 xlsx 里
   **不在当前 org.stages 里**的名字全部列出；这一批行不会真的发请求（会记 OTHER_FAIL）
4. **不可逆** —— 移动阶段本身不可逆需要人工再改回来；确认无误再开跑
5. **日志位置** —— 默认 `--workdir` 是输入文件同目录，生成 `move.log` /
   `state.json` / `failed.csv`；确认可写

### 运行

```bash
python3 <skill-dir>/scripts/application-move-stage/bulk_move.py \
  --input <path-to-xlsx-or-csv> \
  [--app-col <名字或索引>] [--from-col ...] [--to-col ...] \
  [--workdir <输出目录>] \
  [--interval 1.0] \
  [--confirm --expected-org-id <orgId>]
```

脚本默认仅拉 stage 映射并全量校验，不发任何写请求。只有显式提供
`--confirm --expected-org-id <已确认的orgId>` 且与实时 current orgId 完全一致才移动。

### 脚本特性

- **Stage 映射自动拉取**：开跑前 `GET /api/v2/org/info`，`data.stages` 建 name→id
- **Org 守卫**：首次 live 运行要求 `--expected-org-id`；`state.json` 记 `orgId`，续跑若 cllmk 已切到别的 org，**拒绝执行**
  并提示"删掉 state.json 或切回原 env 再跑"，防跨 org 误伤
- **重名保护**：若某 org 的 stages 出现同名条目，脚本直接报错列出，不静默取第一个
- **断点续跑**：`state.json` 记录 `next_row`，同 `--workdir` 重跑自动从上次成功位置继续
- **网络结果未知不重试**：`NETWORK_FAIL` 可能发生在服务端完成移动之后；脚本停止自动重试，先查询当前阶段再决定
- **鉴权熔断**：任何一条命中 401/403/Session expired 立即整体停跑（继续也是白干）
- **失败 CSV**：`failed.csv` 追加写，格式 `applicationId,fromStage,toStage,status,msg`，
  方便事后按 status 过滤（`NETWORK_FAIL` 可再手工重试，`BIZ_FAIL` 需业务方核对）

### 长时间运行的监控建议

10k+ 数据耗时约 4 小时（1s/条）。建议：
- Claude Code 的 `run_in_background` 或 shell `nohup ... &`
- `tail -F move.log | grep -E "FAIL|ABORT|DONE"` 只在异常和完成时刷屏
- 不必每条汇报给用户，只在失败率异常（>10% 连续）或里程碑（1k/5k/完成）汇报

## 不在本路由 覆盖范围

| 需求 | 应使用 |
|---|---|
| 归档 / 淘汰应聘（不同接口） | `cllmk` 的 `application-delete` 路由 |
| 招聘流程模板（pipeline）CRUD | 暂未覆盖 |
| 阶段本身的字段配置 / 新增 stage | 暂未覆盖 |
| 候选人字段 / 登记表 | `cllmk` 的 `candidate` 路由 |
| 职位 / HC 字段 | `cllmk` 的 `job-field-manage` / `hc-field-manage` 路由 |
