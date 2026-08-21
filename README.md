# cllmk Skills

面向 Moka 招聘（ATS）与人事（People）系统的 cllmk 业务技能套件，配合 [`cllmk`](https://cdn.five5.life/cllmk) CLI 使用。

每个技能位于 `skills/<name>/`，并包含符合 Agent Skills 规范的 `SKILL.md`，可被 Claude Code、Codex、CodeBuddy、OpenClaw 等 70+ 种 Agent 直接加载执行（安装见[安装](#安装)）。

## 技能清单

| Skill | 作用 | 说明 |
| --- | --- | --- |
| `ats` | Moka ATS 招聘业务统一入口 | 候选人/申请删除、应聘阶段移动、候选人字段与登记表、职位与 HC 字段、Offer 字段与模块、Offer 附件模板、职位级别（职级）、国家维度渠道保护期、面试评价表与面试题库、职位硬删除等；识别意图后按需加载对应业务文档 |
| `people` | Moka People 人事业务统一入口 | 员工信息设置：档案分类/分组/字段查询、创建/编辑/停用/启用员工自定义字段；引用 `ats` 的鉴权与 CLI 基础规则 |

### 结构说明

```
skills/
├── ats/                    # ATS 主技能：含 references/ 与 scripts/
│   ├── SKILL.md            # 只决策路由，不解释业务
│   ├── references/
│   │   ├── _glossary.md    # 术语表，全仓库单一事实来源
│   │   ├── foundation/     # 安装 / 鉴权 / 租户切换（ATS 分支）
│   │   └── operations/     # ATS 业务路由主文档（frontmatter 统一 route:）
│   └── scripts/            # 业务脚本，默认 dry-run
└── people/                 # People 主技能，自带同名 foundation
    ├── SKILL.md
    └── references/
        ├── foundation/     # 安装 / 鉴权 / 租户切换（People 分支）
        └── operations/

doc/                        # 背景说明（仅供人类阅读，不随技能分发）
├── install.md              # 安装链路与前置条件的设计说明
├── auth.md                 # 鉴权模型的设计取舍
└── tenant-switch.md        # 租户切换的设计取舍
```

> **两个技能都可以单独安装**：安装器只平铺 `skills/<name>/`，所以 `ats` 和 `people` 各自带一份
> `references/foundation/`（安装 / 鉴权 / 租户切换），正文只写自己那套系统的命令、身份字段和环境。
> 代价是这三项规则有两份，改动时必须两侧同步 —— 详见 [AGENT.md](./AGENT.md) §2.1。
> 安装、鉴权、租户切换都没有独立 skill 入口，意图由各主技能的 description 直接接住。

`skills/` 内只写模型执行需要的步骤与约束，「为什么这么设计」放 [`doc/`](./doc) —— 两侧同名对应，`skills/` 内不引用 `doc/`。

工程约定细节见 [AGENT.md](./AGENT.md)；对模型助手的工作守则见 [CLAUDE.md](./CLAUDE.md)。

## 安装

安装器是 [`skills`](https://www.npmjs.com/package/skills) CLI，支持 70+ 种 Agent。下面给出本套件在 **Claude Code**、**Codex**、**CodeBuddy**、**OpenClaw** 上的整套安装命令。

> **必须整套安装，不要只挑一个技能。**
> `people` 用 `<cllmk-dir>` 占位符引用 `ats` 的规则文档，该占位符解析为**同级目录** `ats/`。安装器把技能平铺到同一个 skills 目录，只有两者互为兄弟目录时这个引用才成立。
> 所以下面每条命令都带 `--skill '*'`（装全部 2 个技能）。漏装 `ats` 时 `people` 会主动停止并报告「套件安装不完整」。

> 命令统一用 `npx`（一次性下载执行，不写进 `package.json`）。

### 先看仓库里有哪些技能

```bash
npx skills add clllx/skills --list
```

### Claude Code

```bash
# 项目级 → ./.claude/skills/
npx skills add clllx/skills --skill '*' --agent claude-code -y

# 全局 → ~/.claude/skills/
npx skills add clllx/skills --skill '*' --agent claude-code -y --global
```

### Codex

```bash
# 项目级 → ./.agents/skills/
npx skills add clllx/skills --skill '*' --agent codex -y

# 全局 → ~/.agents/skills/
npx skills add clllx/skills --skill '*' --agent codex -y --global
```

Codex 走通用 `.agents/skills` 目录（Cursor、Cline、Gemini CLI 等也共用它），不是 `.codex/skills`。

### CodeBuddy

```bash
# 项目级 → ./.codebuddy/skills/（要求 ./.codebuddy/ 已存在，见下方注意）
npx skills add clllx/skills --skill '*' --agent codebuddy -y

# 全局 → ~/.codebuddy/skills/
npx skills add clllx/skills --skill '*' --agent codebuddy -y --global
```

> ⚠️ **项目级安装 CodeBuddy 前，项目根目录必须已有 `.codebuddy/`**，否则安装器会**静默跳过** CodeBuddy —— 计划里仍会打印 `symlink → CodeBuddy`，但结果里没有它，且退出码为 0，很容易误判成装好了。先 `mkdir -p .codebuddy` 再执行，或直接用 `--global`。
> （Claude Code 是唯一例外：目录不存在时会自动创建。）

### OpenClaw

```bash
# 项目级 → ./skills/
npx skills add clllx/skills --skill '*' --agent openclaw -y

# 全局 → OpenClaw 全局技能目录（~/.openclaw/skills/）
npx skills add clllx/skills --skill '*' --agent openclaw -y --global
```

OpenClaw 原生 Git 安装要求源仓库根目录直接有 `SKILL.md`，只适合单技能仓库；本仓库是多技能套件，用上面的命令安装。若已把单个技能发布到 ClawHub，也可以：

```bash
openclaw skills install <skill-slug>
```

### 一条命令装到多个 Agent

`--agent` 接受多个值：

```bash
npx skills add clllx/skills --skill '*' --agent claude-code codex codebuddy -y
```

同装多个时，安装器把技能**实体**放在 `.agents/skills/`，再 symlink 到其余 Agent 目录，磁盘上只有一份。加 `--copy` 可改为每个目录各存一份副本。

### 落盘位置一览

| Agent | `--agent` 取值 | 项目级 | 全局（`--global`） |
| --- | --- | --- | --- |
| Claude Code | `claude-code` | `./.claude/skills/` | `~/.claude/skills/` |
| Codex | `codex` | `./.agents/skills/` | `~/.agents/skills/` |
| CodeBuddy | `codebuddy` | `./.codebuddy/skills/` | `~/.codebuddy/skills/` |
| OpenClaw | `openclaw` | `./skills/` | `~/.openclaw/skills/` |

省略 `--agent` 时进入交互式选择；`--list` 只列出不安装。

### 为什么不用 `--all`

`--all` 是 `--skill '*' --agent '*' -y` 的简写，但其中 `--agent '*'` 指的是安装器支持的**全部 70+ 种 Agent**，不是本机已装的那几个——执行后会在机器上凭空建出几十个 skills 目录。要整套安装请用 `--skill '*'` 搭配显式 `--agent`。

### 更新与卸载

```bash
# 更新到最新版
npx skills update

# 卸载本套件（按名字列出，避免 --skill '*' 连带删掉其他来源的技能）
npx skills remove ats people
```

## 路由约定

- **安装 / 鉴权 / 租户切换** 这三项基础能力在 `ats` 与 `people` 的 `references/foundation/` 各有一份（按系统分家），没有独立 skill 入口，意图直接由主技能接住。
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
- **不要**在 SKILL.md 的「容易混淆的边界」表里展开业务细节；那里只能放指针型短条目（「X → 路由到 Y」）。
- 新增术语先登记到 `skills/ats/references/_glossary.md`。

### Lint 与 pre-commit hook

装一次 hook，提交时自动拦截：

```bash
git config core.hooksPath .githooks
# 或：ln -sf ../../.githooks/pre-commit .git/hooks/pre-commit
```

hook 依次跑四道守卫，任一失败即拒绝提交：

| # | 守卫 | 内容 |
| --- | --- | --- |
| 1 | `scripts/lint_skill_routes.py` | 路由表一致性、callout 存在性与 `Step 1–N` 是否匹配 SKILL.md 实际步数、`data.system` 断言、frontmatter 字段、400 行目录、禁用口语、文档引用的脚本是否存在 |
| 2 | `scripts/test_lint_skill_routes.py` | lint 自身的变异测试：每条检查都有「故意写坏必须报」的反向用例 |
| 3 | `skills/ats/scripts/_test/test_safety_guards.py` | 安全红线在脚本层的唯一自动化守卫（默认只预览、组织校验、不自动重试写请求） |
| 4 | `test_offer_template.py` / `test_parse_form_file.py` | 依赖 `python-docx` / `pytest`，缺依赖则跳过，不阻断 |

也可以手动全跑：

```bash
sh .githooks/pre-commit
```

只跑 lint（`--strict` 会把引号、超长等 WARNING 提升为 ERROR）：

```bash
python3 scripts/lint_skill_routes.py
python3 scripts/lint_skill_routes.py --strict
```

**为什么 2 和 3 必须在 hook 里**：hook 曾只跑第 1 项。`test_safety_guards.py` 被移动目录后，44 条安全断言全部 `FileNotFoundError`，而 lint 照样绿，没人察觉。守卫本身不被守卫，等于没有守卫。

### git 提交规范

- 提交信息使用 `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` 前缀。
- 涉及 `foundation/` 的改动**必须**在 commit body 中显式说明影响面，并列出实际改到的两侧文件（`ats` 与 `people` 的同名文档，以及两个 `SKILL.md` 的「基础能力路由」表与 description 是否同步更新）。
- 仓库主线不允许 force-push，提交历史是合规审计源。
