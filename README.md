# cllmk Skills

面向 Moka 招聘（ATS）与人事（People）系统的 cllmk 业务技能套件，配合 [`cllmk`](https://cdn.five5.life/cllmk) CLI 使用。

每个技能位于 `skills/<name>/`，并包含符合 Agent Skills 规范的 `SKILL.md`，可被 Claude Code、OpenClaw 等 Agent 直接加载执行。

## 技能清单

| Skill | 作用 | 说明 |
| --- | --- | --- |
| `ats` | Moka ATS 招聘业务统一入口 | 候选人/申请删除、应聘阶段移动、候选人字段与登记表、职位与 HC 字段、Offer 字段与模块、Offer 附件模板、职位级别（职级）、国家维度渠道保护期、面试评价表与面试题库、职位硬删除等；识别意图后按需加载对应业务文档 |
| `people` | Moka People 人事业务统一入口 | 员工信息设置：档案分类/分组/字段查询、创建/编辑/停用/启用员工自定义字段；引用 `ats` 的鉴权与 CLI 基础规则 |
| `cllmk-auth` | 登录鉴权兼容入口 | 登录、登出（含 `--all`）、会话状态检查、HTTP 401/403 处理；规则不重复存放，由 `ats/references/foundation/auth.md` 提供 |
| `cllmk-install` | CLI 安装兼容入口 | cllmk 安装、升级与安装确认；规则由 `ats/references/foundation/install.md` 提供 |
| `cllmk-tenant-switch` | 租户切换兼容入口 | 列出/切换 current 租户（ATS orgId / People tenantId）；规则由 `ats/references/foundation/tenant-switch.md` 提供 |

### 结构说明

```
skills/
├── ats/                    # ATS 主技能：含 references/ 与 scripts/
│   ├── SKILL.md
│   ├── references/
│   │   ├── foundation/     # 安装 / 鉴权 / 租户切换 规则单一事实来源
│   │   └── operations/     # ATS 各业务路由对应的主文档与细则
│   └── scripts/            # dry-run + 确认 --confirm 的业务脚本
├── people/                 # People 主技能：复用 ats 的 foundation
│   ├── SKILL.md
│   └── references/operations/
├── cllmk-auth/             # 兼容瘦入口，指向 ats/references/foundation/
├── cllmk-install/          # 兼容瘦入口，指向 ats/references/foundation/
└── cllmk-tenant-switch/    # 兼容瘦入口，指向 ats/references/foundation/
```

> **必须整套安装**：`people` 与三个 `cllmk-*` 瘦入口通过相对路径（`../ats/...`）引用 `ats` 的规则文档。漏装 `ats` 时这些入口会主动停止并报告"套件安装不完整"。

## 安装

### 使用 npx skills 安装

列出本仓库中的所有技能：

```bash
npx skills add clllx/skills --list
```

交互式选择并安装：

```bash
npx skills add clllx/skills
```

完整安装整套 cllmk 技能（推荐）：

```bash
npx skills add clllx/skills \
  --skill ats \
  --skill people \
  --skill cllmk-auth \
  --skill cllmk-install \
  --skill cllmk-tenant-switch
```

安装到 OpenClaw：

```bash
npx skills add https://github.com/clllx/skills \
  --skill ats \
  --skill people \
  --skill cllmk-auth \
  --skill cllmk-install \
  --skill cllmk-tenant-switch \
  --agent openclaw
```

追加 `--global` 可安装到 `~/.openclaw/skills/`，供本机 OpenClaw Agent 共享。

### OpenClaw 原生安装

OpenClaw 原生 Git 安装要求安装源根目录直接包含 `SKILL.md`，适合单技能仓库。本仓库为多技能套件，推荐使用上方 `npx skills add ... --agent openclaw` 一次性整套装，或将单个技能发布到 ClawHub 后执行：

```bash
openclaw skills install <skill-slug>
```

## 路由约定

- **安装 / 鉴权 / 租户切换** 这三项基础能力由 `ats` skill 的 `references/foundation/` 提供单一事实来源；`cllmk-auth` `cllmk-install` `cllmk-tenant-switch` 仅为兼容瘦入口，不重复存放规则。
- **ATS vs People 的边界**：候选人字段、登记表、职位与 HC 字段等走 `ats`；员工字段、档案分类、人事字段走 `people`；用户只说"字段"而未指明系统时，技能会停下询问。
- **写操作默认 dry-run**：删除、阶段移动、保护期修改等写操作脚本默认只预览，必须显式传入 `--confirm --expected-org-id <orgId>` 且实时 current orgId 匹配才会真正写入。
- **current 租户是全局共享状态**：跨租户/跨系统任务按 `switch → status → 完成本任务 → switch` 串行执行；任务收尾时向用户明示 current 停在哪个租户。

## 使用示例

> "帮我在 Moka 招聘系统里给候选人 X 移动到「Offer」阶段"

> "为 People 人事库的员工档案新增一个自定义字段，类型是单选"

> "列出我当前已登录的所有公司，把 current 切到 X 公司"

> "cllmk 还没装好，帮我在 mac 上装一下"

技能会自动按上述路由表选择对应的 `ats` 或 `people` 主文档，先执行公共的前置检查（CLI 是否存在、current 是否指向目标租户、会话是否有效），再进入具体业务流程。

## 维护约定

- 新增 ATS 业务：在 `skills/ats/references/operations/` 下新增主文档，并在 `skills/ats/SKILL.md` 路由表中登记意图信号与主文档路径。
- 新增 People 业务：在 `skills/people/references/operations/` 下新增主文档，并在 `skills/people/SKILL.md` 路由表中登记。
- 不要修改 `cllmk-auth` `cllmk-install` `cllmk-tenant-switch` 内部的瘦入口逻辑；规则更新请改 `skills/ats/references/foundation/`。
