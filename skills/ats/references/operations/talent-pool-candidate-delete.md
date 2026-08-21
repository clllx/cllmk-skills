---
route: talent-pool-candidate-delete
---

# Moka ATS 人才库批量移除候选人

## 前置鉴权

执行任何子流程前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成
安装确认 → `cllmk auth status` → 登录引导，确认 `data.system === "ats"`。

## 接口元信息

| 项 | 值 |
|---|---|
| Method | `POST` |
| URL | `/api/outer/ats-candidate/talent-pool-candidates/bulk/delete` |
| Body | `{"candidateIds": [<int>, ...]}` |
| 鉴权 | Cookie（`cllmk curl` 自动注入） |

### 响应分类（实测）

| 类别 | 判定条件 | 是否重试 |
|---|---|---|
| ✅ 成功 | `code=0 AND data.success=true AND data.msg="成功"` | — |
| 🌐 网络失败 | `cllmk` 退出码 ≠ 0，或响应含 `"Client network socket disconnected"` | **结果未知，不自动重试；先回读人才库成员状态** |
| 🚫 业务失败 | `code=0 AND data.success=false AND data.msg` 含 `"不在人才库"` | **不重试** |

业务失败是**整批连坐语义**（这是高优先级的坑）：批内只要存在 1 个 ID 不在目标人才库，
整批请求都会被服务端拒绝，而不是只跳过那个异常 ID。批量任务中该情况可能造成较大误伤，
因此不能把整批失败直接当作“全部不在人才库”。

所以业务失败 **不能默认归档**，必须执行救场扫描（除非用户明确说"漏删少量可接受"）。
本路由 1.1.0+ 内置 `--rescue` 模式，从上一轮日志读出 BIZ_NOT_IN_POOL 批次的全部 ID，
去重后**单条/次**重扫，把误伤的 ID 找回来；真实"不在人才库"的会单独标记 TRULY_NOT_IN_POOL。

### 语义注记（未完全求证）

接口 path 含 `talent-pool-candidates`、但 body **不带** `talentPoolId`，
referer 仅在浏览器调用时出现。`cllmk curl` 调用时无 referer 也能成功，
推测服务端根据候选人当前所在人才库做反查并移除。这意味着：

- 同一候选人若同时在多个人才库，此调用是否会一并清除尚未求证
- 用户若关心"只从某个人才库移除"，应该先在浏览器进入目标人才库再用 cllmk
  （以建立 session/referer 上下文），或要求扩展接口字段

执行前**主动向用户提示这一点**，让其确认风险后再开跑。

## 子场景路由

| 用户意图 | 执行 |
|---|---|
| 提供 xlsx / csv 路径 → 大批量移除 | 进入「批量脚本模式」 |
| 直接给 < 30 条 ID → 一次性删 | 直接调一次 `cllmk curl`，不走脚本 |
| 给 30 ~ 几百条 ID（嫌写脚本麻烦） | 仍走脚本模式，把 ID 写到临时 csv 给脚本读 |

## 批量脚本模式

### 执行前 5 项确认

逐条与用户对齐后再开跑（缺一不可）：

1. **环境与人才库** —— 当前 `cllmk auth status` 显示的 env / org 是不是目标？
   人才库语义注记是否接受？
2. **数据规模** —— 读取输入文件第一列得到总条数，估算批次数与耗时
   （`ceil(N/30) × 2s` + 接口延迟，经验值约 1.3s/批，所以总耗时 ≈ `ceil(N/30) × 3.3s`）
3. **失败策略** —— 网络失败不自动重试；业务失败（"不在人才库"）由于连坐
   误伤率高，**默认在主轮结束后自动触发 `--rescue` 单条扫描**。
   若用户明确说"漏删少量可接受、不要 rescue"，再用 `--no-rescue-biz` 跳过
4. **不可逆** —— 删除不可逆，明确询问确认
5. **日志位置** —— 默认与输入文件同目录下生成 `delete.log` /
   `rescue.log` / `state.json`，确认是否可写

### 运行

调用脚本 `<skill-dir>/scripts/talent-pool-candidate-delete/bulk_remove.py`：

```bash
python3 <skill-dir>/scripts/talent-pool-candidate-delete/bulk_remove.py \
  --input <path-to-xlsx-or-csv> \
  --id-column <列名或列号，默认第 1 列> \
  --workdir <输出目录，默认输入文件同目录> \
  --batch-size 30 \
  --interval 2.0 \
  [--confirm --expected-org-id <orgId>]
```

或直接给 ID 列表（中等量级）：

```bash
python3 <skill-dir>/scripts/talent-pool-candidate-delete/bulk_remove.py \
  --ids <candidateId>,<candidateId>,<candidateId> \
  --workdir /tmp/del-xxx \
  [--confirm --expected-org-id <orgId>]
```

脚本特性：
- 默认只预览；live 必须显式提供 `--confirm --expected-org-id <已确认的orgId>`
- 输入 ID 保持原顺序去重后再分批；重复 ID 不会扩大请求规模或重复移除
- 自动批量 + 间隔；支持断点续跑（依赖 `state.json` 记录 `next_batch`）
- 租户防串（org guard）：启动（含 `--rescue`）时拒绝非空 `CLLMK_PROFILE`，再经 `/api/v2/org/info` 取 current 会话 orgId 并打印，取不到即中止；orgId 写入 `state.json`，续跑时租户不一致立即拒绝。跨租户任务按 `switch → status → 本租户任务` 串行执行
- 网络失败不自动重试；删除结果可能已经生效，必须先查询人才库成员状态
- 业务失败（"不在人才库"）整批标记 `BIZ_NOT_IN_POOL`
- 主轮结束后**自动 rescue**：从所有日志收集 BIZ_NOT_IN_POOL 批次 ID，
  去重后单条/次重扫，rescue 日志写到 `rescue.log`
- `--no-rescue-biz` 跳过 rescue 步骤（仅当用户明确接受连坐误伤）
- 输出最终战报：OK / NETWORK_FAIL / BIZ_NOT_IN_POOL / RECOVERED / TRULY_NOT_IN_POOL

### 救场模式（单独触发）

如果是事后想给已经跑完的目录补救：

```bash
python3 <skill-dir>/scripts/talent-pool-candidate-delete/bulk_remove.py \
  --rescue --workdir <已跑过的目录> \
  --confirm --expected-org-id <orgId>
```

读取目录下所有 `*.log`（含子目录）的 BIZ_NOT_IN_POOL 行，单条/次重扫。耗时 ≈ `N_unique × 2s`。

### 长时间运行的监控建议

21k+ 数据耗时 ~25 分钟。建议：
- 在 shell 中以 `python3 ... &` 后台运行；或使用 Claude Code 的 `run_in_background`
- 配合 `tail -F delete.log | grep -E "FAIL|EXC|DONE"` 仅在异常和完成时输出
- 不要每批都汇报给用户，否则刷屏；只汇报失败率明显异常或重大里程碑

## 不在本路由 覆盖范围

| 需求 | 应使用 |
|---|---|
| 候选人字段 / 登记表 | `cllmk` 的 `candidate` 路由 |
| 招聘需求字段 | `cllmk` 的 `hc-field-manage` 路由 |
| 职位字段 | `cllmk` 的 `job-field-manage` 路由 |
| 人才库 CRUD / 权限 | 暂未覆盖 |
| 向人才库**加入**候选人 | 暂未覆盖 |
