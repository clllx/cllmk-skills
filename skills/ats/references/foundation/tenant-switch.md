---
metadata:
  version: "1.5.0"
description: "cllmk current 租户查询与切换规则。无参数 `cllmk auth switch` 离线列出已保存租户和持久化 current；带公司名、租户 ID 或 profile 时切换，并用裸 `cllmk auth status` 验证。不存在或匹配多个 profile 时停止，不猜测。"
---

# cllmk 租户切换

本文只管理 `cllmk` 的 current 租户：离线查询已保存租户和持久化 current 指针、选择目标 profile、切换 current，并衔接切换后的实时验证。登录、登出、过期处理和 API 鉴权规则位于 `auth.md`；CLI 未安装时读取 `install.md`。

## 边界

- 只使用 `cllmk auth switch` 改变 current，不手动编辑任何 auth、profile 或 current 文件。
- **只有 `login` 和 `auth switch` 会写 current 指针**。`auth status` 只读，`auth logout` 只删会话文件，两者都不改指针。
- 不执行 Moka 业务 API。进入业务 skill 后只使用 current，命令不得携带 `--org`、`--profile` 或 `CLLMK_PROFILE`。
- 不输出 Cookie、认证头或凭证文件内容。
- current 是同一配置目录的共享状态，不并行执行不同租户的业务任务。

## 1. 确认 CLI 已安装

按 `auth.md` 的 Step 1 确认 `cllmk` 可执行。未安装时立即停止，不运行 `auth switch` 或 `auth status`，改按 `install.md` 引导安装。

## 2. 检查环境变量覆盖

运行租户命令前检查 `CLLMK_PROFILE` 是否为非空值：

```bash
if [ -n "${CLLMK_PROFILE:-}" ]; then
  printf '%s\n' "$CLLMK_PROFILE"
fi
```

Windows PowerShell：

```powershell
$env:CLLMK_PROFILE
```

先检查非空值是否符合 profile 名语法：只能包含字母、数字、`-`、`_`，最长 64 个字符，且必须以字母或数字开头。

- **值不合法**：所有命令都会在执行前返回 `Invalid profile name`，包括无参数列表。停止并要求用户先清除或修正环境变量，不要声称列表查询已经执行。
- **值合法，且只做无参数列表查询**：允许继续。`cllmk auth switch` 的无参数结果读取持久化 current 指针，不受 `CLLMK_PROFILE` 影响；同时提示该环境变量存在，后续裸 `auth status` 和业务命令会被它覆盖，因此列表结果不能证明实时会话正在使用哪一个 profile。
- **值合法，但要切换 current 或进入业务**：停止并要求用户先清除该环境变量 —— 它的优先级高于 current，会让验证通过的 profile 和实际执行的 profile 错位。

## 3. 查询租户列表

用户未给出目标、询问有哪些租户、或询问当前租户时运行：

```bash
cllmk auth switch
```

**无参数 `auth switch` 就是列表命令。不存在 `cllmk auth list` 子命令** —— 执行它只会得到 `error: unknown command 'list'`，不要因此以为 CLI 版本过旧或需要升级。

这是离线查询，只列出已有会话的 profile，并标记**持久化 current 指针**；不会修改 current，也不验证 Cookie 是否仍然有效。向用户只展示 `profile`、`system`、`env`、current 标记和该 system 的身份字段，不展示 email、createdAt、Cookie、认证头或其他凭证信息。

身份字段按 system 不同，列表和 status 都只返回对应那一组：

| system | 身份字段 |
|---|---|
| `ats` | `orgId`、`orgName` |
| `people` | `tenantId`、`buId`、`corpName`、`realname` |

**不要在 People 会话里找 `orgId` / `orgName`** —— 那是 ATS 专用字段，People 侧不返回；反之 ATS 也不返回 tenantId / buId / corpName。

按下表处理列表的四种异常形态：

| 列表形态 | 含义 | 动作 |
|---|---|---|
| 某项身份字段为空 | 老版本 CLI 未写入或探测失败 | 显示为「未知（旧会话缺少身份快照）」，只允许用户按明确 profile 名选择；不按 system/env 或相似名称猜公司 |
| 列表为空 | 没有任何已保存的有效会话文件 | 报告「没有可用会话」，再按 `auth.md`「登录流程」执行 login。此时 `data.current` 仍可能是 `"default"`，那只是没有持久化指针时的 fallback 名称，**不代表存在 default 会话或已登录** |
| 列表非空，但没有任何一项带 current 标记 | `data.current` 指向的 profile 已无有效会话文件（通常是刚被 `auth logout` 清除，logout 从不改指针；也可能是会话文件损坏） | 如实报告「current 指向 `<profile>` 但已无会话」，让用户选择重新登录该租户或切到列表中仍有会话的租户。不当成已登录，不自动改指针，不改用 `default`，不自动选列表里的其他 profile |
| 用户问 current 是否有效 / 实际登录的是哪家 | 离线列表不足以回答 | 查完持久化指针后转到 `auth.md` 执行裸 `cllmk auth status` 实时验证 |

## 4. 选择切换命令

每次只传一种目标：

| 用户提供的目标 | 命令 |
|---|---|
| 公司名 / 自然语言租户名 | `cllmk auth switch "<公司名>"` |
| 明确的租户 ID | `cllmk auth switch --org <orgId>` |
| 明确要求按公司名 | `cllmk auth switch --org "<orgName>"` |
| 明确的 profile 名 | `cllmk auth switch --profile <profile>` |

`--org` 和位置参数按会话所属 system 匹配身份，ATS 会话匹配 `orgId` / `orgName`。租户 ID 和公司名**合并判重** —— 命中多个 profile 时一律返回 `matches multiple profiles` 并保持 current 不变，不会因为「ID 比公司名先匹配」就替用户选一个。

位置参数额外先匹配 profile 名：**profile 名优先，再匹配租户 ID / 公司名**。已知目标类型时用对应的显式参数，不要依赖这个隐式优先级，也不要同时传位置参数、`--org` 和 `--profile`。

profile 名由 login 按 `ats-<orgId>` 自动生成，因此 profile 名本身就能看出 system。

切换只接受已存在会话文件的 profile。成功时 current 指针立即更新，响应中的 `previous` 和 `current` 用于向用户说明状态变化；Cookie 不会被修改、复制或删除。**不要把 previous 用于自动回滚。**

## 5. 切换后验证

切换成功后必须立即运行不带任何租户路由参数的命令：

```bash
cllmk auth status
```

只有返回 `code: 0`，且 `data.profile`、`data.system`、`data.env` 和 `data.orgId` / `data.orgName` 与目标一致，才报告「current 已切换且实时验证通过」。之后的业务 skill 继续使用裸 `cllmk auth status` 和裸 `cllmk curl`。email 不属于租户确认所需字段，不向用户展示。

如果 status 显示过期、未登录、网络错误或在线身份与目标不一致：

1. 明确报告「持久化 current 已切到 `<current>`，但实时身份验证失败」，不要误报为 current 未改变，也不要报告切换完成。
2. 保留已切换的 current，**不自动恢复 previous** —— current 是共享状态，回滚会二次改动它。
3. 停止所有业务操作，转到 `auth.md` 的对应失败分支（status 是纯查询，任何状态码都不会删除会话文件，判定规则以该文档为准）。


## 完成标准

查询任务以无参数列表结果为准，并明确它是离线快照而非实时登录验证。切换任务必须同时满足：

1. `cllmk auth switch ...` 返回 `code: 0`。
2. 裸 `cllmk auth status` 返回 `code: 0`。
3. status 中的租户身份与用户目标一致。

跨租户任务（导出 A → 写入 B）额外要求：**收尾时向用户明示 current 指针最终停在哪个租户**，并说明它是共享状态。切换过 current 的任务结束时指针停在最后一个目标租户（通常是写入侧），用户下一条命令会落在那里；不要默默留下与任务开始时不同的指针。不自动切回，由用户决定。
