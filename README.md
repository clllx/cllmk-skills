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
│   ├── SKILL.md            # 只决策路由，不解释业务
│   ├── references/
│   │   ├── _glossary.md    # 术语表，全仓库单一事实来源
│   │   ├── foundation/     # 安装 / 鉴权 / 租户切换 单一事实来源
│   │   └── operations/     # ATS 业务路由主文档（frontmatter 统一 route:）
│   └── scripts/            # 业务脚本，默认 dry-run
├── people/                 # People 主技能：复用 ats 的 foundation
│   ├── SKILL.md
│   └── references/operations/
├── cllmk-auth/             # 兼容入口：→ ats/references/foundation/auth.md
├── cllmk-install/          # 兼容入口：→ ats/references/foundation/install.md
└── cllmk-tenant-switch/    # 兼容入口：→ ats/references/foundation/tenant-switch.md
```

> **必须整套安装**：`people` 与三个 `cllmk-*` 兼容入口通过相对路径（`../ats/...`）引用 `ats` 的规则文档。漏装 `ats` 时这些入口会主动停止并报告「套件安装不完整」。

工程约定细节见 [AGENT.md](./AGENT.md)；对模型助手的工作守则见 [CLAUDE.md](./CLAUDE.md)。

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

- **安装 / 鉴权 / 租户切换** 这三项基础能力由 `ats/references/foundation/` 提供单一事实来源；`cllmk-auth` `cllmk-install` `cllmk-tenant-switch` 只是兼容入口，不重复存放规则。
- **ATS vs People 的边界**：候选人字段、登记表、职位与 HC 字段等走 `ats`；员工字段、档案分类、人事字段走 `people`；用户只说「字段」而未指明系统时，技能会停下询问。
- **写操作默认 dry-run**：删除、阶段移动、保护期修改等写操作脚本默认只预览，必须显式传入 `--confirm --expected-org-id <orgId>` 且实时 current orgId 匹配才会真正写入。
- **current 指针全局共享**：跨租户/跨系统任务按 `switch → status → 完成本任务 → switch` 串行执行；任务收尾时向用户明示 current 停在哪个租户。

## 使用示例

> "帮我在 Moka 招聘系统里给候选人 X 移动到「Offer」阶段"

> "为 People 人事库的员工档案新增一个自定义字段，类型是单选"

> "列出我当前已登录的所有公司，把 current 切到 X 公司"

> "cllmk 还没装好，帮我在 mac 上装一下"

技能会自动按路由表选择对应的 `ats` 或 `people` 主文档，先执行公共的前置检查（CLI 是否存在、current 是否指向目标租户、会话是否有效），再进入具体业务流程。

## 维护约定

详细的工程原则、文档格式约定、评审流程见 [AGENT.md](./AGENT.md)。核心要点速查：

- 新增 ATS 业务：在 `skills/ats/references/operations/` 下新增主文档，frontmatter 只用 `route:`，H1 下方必须有 `⚠️ 执行前必读` callout；在 `skills/ats/SKILL.md` 路由表登记意图信号与文档路径。
- 新增 People 业务：同上，但目标路径改为 `skills/people/references/operations/`。
- **不要**在 `cllmk-auth` `cllmk-install` `cllmk-tenant-switch` 内重复存放规则；规则更新请改 `skills/ats/references/foundation/`。
- **不要**在 SKILL.md 的「容易混淆的边界」表里展开业务细节；那里只能放指针型短条目（「X → 路由到 Y」）。
- 新增术语先登记到 `skills/ats/references/_glossary.md`。

### Lint 与 pre-commit hook

每次提交 `skills/` 下变更前必跑：

```bash
python3 scripts/lint_skill_routes.py
```

通过后才能提交。要让 hook 自动拦截，安装一次：

```bash
git config core.hooksPath .githooks
# 或：ln -sf ../../.githooks/pre-commit .git/hooks/pre-commit
```

### git 提交规范

- 提交信息使用 `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` 前缀。
- 涉及 `foundation/` 的改动**必须**在 commit body 中显式说明影响面（例如 `ats/SKILL.md` 的「基础能力路由」是否同步更新，三个 cllmk-* 兼容入口 description 是否需要改）。
- 仓库主线不允许 force-push，提交历史是合规审计源。
