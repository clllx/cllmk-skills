# cllmk Skills 工程原则

本文件约定 cllmk skill 仓库（`ats` / `people` / `cllmk-*`）在新增、修改、评审业务文档时**必须遵循**的工程原则。
所有 Agent / 协作者在编辑 `skills/` 任何文件前都应该完整读取本文件。

## 1. 目录结构约定

```
skills/
├── ats/                          # ATS 招聘系统主 skill（含 references + scripts）
│   ├── SKILL.md                  # 主入口，只决策路由，不解释业务
│   ├── references/
│   │   ├── _glossary.md          # 术语表，全仓库单一事实来源
│   │   ├── foundation/           # 安装 / 鉴权 / 租户切换，正文只含 ATS 分支
│   │   │   ├── install.md
│   │   │   ├── auth.md
│   │   │   └── tenant-switch.md
│   │   └── operations/           # ATS 业务路由对应的主文档
│   │       ├── <route>.md        # 顶层主文档（frontmatter 必须有 route:）
│   │       └── <sub>/            # 复杂业务的二级目录
│   │           ├── index.md      # 二级目录的主文档（必须有 route:）
│   │           └── <other>.md    # 被主文档引用的子文档（不强制 route:）
│   ├── scripts/
│   │   ├── <route>/              # 每个主路由一个目录
│   │   └── _test/                # 跨路由的测试脚本
│   └── ...
├── people/                       # People 人事系统主 skill
│   └── references/foundation/    # 同名三份文档，正文只含 People 分支
└── scripts/lint_skill_routes.py  # 仓库级 lint（根目录 scripts/）

doc/                              # 仅供人类阅读的背景说明，不随技能分发
└── <topic>.md                    # 与 skills 内同名文档一一对应（如 doc/install.md ↔ foundation/install.md）
```

**`doc/` 与 `skills/` 的分工**：`skills/` 下的文档只写模型执行时需要的内容 —— 步骤、payload、
硬约束、路由边界；「为什么这么设计」「链路原理」「历史踩坑」写进 `doc/`。
安装器只平铺 `skills/<name>/`，`doc/` 不会出现在用户机器上，所以**模型执行必需的规则一律不许下放到 `doc/`**。
反过来，`skills/` 内**不允许出现任何指向 `doc/` 的引用**（相对路径会失效，仓库 URL 则是让模型去读一份它不需要的文档）：
两侧靠同名对应（`doc/install.md` ↔ `foundation/install.md`）关联，由人在改动时自行同步。

## 2. 核心架构原则

### 2.1 单一事实来源（SSOT）

- **鉴权 / 安装 / 租户切换**的规则**只允许手写在** `ats/references/foundation/` 下。
- 这三项**都没有独立 skill 入口**：意图由各主 skill 的 description 与「基础能力路由」表直接接住。
  历史上曾有 `cllmk-auth` / `cllmk-install` / `cllmk-tenant-switch` 三个瘦入口，正文只有三行指针，
  不提供任何路由价值，却让每次 foundation 改动都多三处需要同步 —— 已全部删除。**不要再建瘦入口**。

**每个主 skill 各自维护一份 foundation。**

安装器只平铺 `skills/<name>/`。用户单独安装 `people` 时 `skills/ats/` 根本不存在，
跨 skill 的相对引用会全部断链，SKILL.md 只能报「套件安装不完整」并停止 —— people 因此无法独立分发。
所以 `ats` 和 `people` 各有一套 `references/foundation/{install,auth,tenant-switch}.md`，
**都是手工维护的最终文档**，正文只写自己那套系统的分支：

| 内容 | ats 侧 | people 侧 |
|---|---|---|
| login 命令 | `cllmk ats <env> auth login` | `cllmk people <env> auth login` |
| profile 命名 | `ats-<orgId>` | `people-<tenantId>` |
| 身份字段 | `orgId` / `orgName` | `tenantId` / `buId` / `corpName` / `realname` |
| env 表 | `cn` / `intl` / `s3` | `pp`（`dingding` / `test` 尚未配置 URL） |
| login 失败分支 | 账号角色不正确（未进 `/dashboard`） | env URL not configured |

`install.md` 没有 system 差异，两侧内容一致。

**两条维护约定**：

1. **规则类改动必须两侧同步落地**。鉴权规则只改一侧的后果不是排版不一致，
   而是一侧写着「凭证仍在盘上」另一侧写着「已登出」，模型据此做出相反的动作。
   改 `foundation/` 时把两份文档一起打开、一起改、一起提交。
2. **双系统对照内容两侧都保留，不许按 system 拆掉**：身份字段对照表、
   「一个 profile 只属于一个 system」、「system 选错」的兜底、「不在本 skill 覆盖范围时改用另一个 skill」。
   这些是模型识别「自己拿错了会话」的唯一依据，拆掉等于把安全兜底删了。

### 2.2 主入口职责最小化

`SKILL.md` 的职责只有两个：**识别意图 → 路由到唯一主文档**。它**不应该**：

- ❌ 解释业务实现细节（type 映射、字段语义、接口陷阱等）
- ❌ 列举操作步骤
- ❌ 存放接口元信息

如果某条「容易混淆的边界」需要超过一行解释，那说明这段细节**写错地方了**，应该下沉到对应 reference 的「前置确认 / 适用范围」小节。

### 2.3 路由决策与业务实现严格分层

| 层级 | 文件位置 | 内容 |
|---|---|---|
| 路由层 | `SKILL.md` 路由表 | 意图关键词 → route → 主文档路径 |
| 业务层 | `references/operations/<route>.md` | 接口元信息、业务流程、payload、错误处理 |
| 通用层 | `references/foundation/*.md` | 鉴权、安装、租户共享规则 |
| 术语层 | `references/_glossary.md` | 业务术语标准说法 |

**任何文档不允许跨层扩写**。

## 3. 文档格式约定

### 3.1 frontmatter 字段

所有 **主文档**（顶层 `operations/<route>.md` 或 `<sub>/index.md`）必须使用：

```yaml
---
route: <route-name>
---
```

- 不允许使用 `name:` / `description:` 代替 `route:`。
- 路由名必须与上级 SKILL.md 路由表中登记的值**完全一致**（由 `lint_skill_routes.py` 强制校验）。
- 二级目录内的子文档（如 `api-templates.md`）**不需要** frontmatter。

### 3.2 首行 callout

每个业务主文档（`references/operations/**`）的 H1 下方必须紧跟：

```markdown
# <业务标题>

> ⚠️ 执行前必读：`<skill-dir>/SKILL.md` 的「业务公共前置」（Step 1–N），
>   确认 `data.system === "<ats|people>"`。
```

**这是强约束**，模型扫描长文档时这是最稳定的锚点。不允许散布在大写段落、第 1 步小节、或者完全不写。

### 3.3 超长文档必须有目录

- 超过 **400 行**的文档必须在 H1 之后紧跟 `## 目录`，列出与实际 `## H2` 完全对应的锚点。
- 超过 **700 行** 的文档，应该考虑按「操作原语」拆分为子目录 + 索引文件（参考 `protection-period-country/` 的做法）。

### 3.4 「不在本路由覆盖范围」

- 每个业务主文档可以**选择性**包含这一节，列出与该业务**相关但路由不覆盖**的边界。
- 统一用 `## 不在本路由覆盖范围`，不再使用「当前不覆盖」「待建」「不支持」等口语。
- 条目应提供替代路径（哪个 skill / 哪个路由 / 是否需要用户给 UI curl）。

## 4. 文字与术语规范

### 4.1 术语一致性

所有文档**必须**使用 `skills/ats/references/_glossary.md` 中的术语标准说法，不允许自由同义改写。
例如：

- ✅ 「候选人主档」 ❌ 「候选人档案」「候选人记录」「候选人实体」
- ✅ 「不在本 skill 覆盖范围」 ❌ 「当前不支持」「待扩展」

**但要区分两类表述**：「不在本 skill 覆盖范围」描述的是**路由边界**；「一律不允许创建」「禁止猜 type」「停止写入」描述的是**安全硬约束**。
规范化文字时**不允许**把后者改写成前者 —— 边界声明听起来像「本 skill 没做，你自己想办法」，
硬约束要的是「做了就是事故，停下来问用户」。两者语气不同，后果也不同。

新增业务概念时，**先**在 `_glossary.md` 里登记术语，**再**在业务文档里使用。

### 4.2 中文表达

- 「本路由」 / 「本 skill」后面**不跟空格再跟动词**。
  - ❌ 「本路由 处理」  ✅ 「本路由处理」
  - ❌ 「本路由 覆盖」  ✅ 「本路由覆盖」
  - 例外：「本路由 **加粗**」「本路由 1.0.0+」这种 Markdown 或版本号语义后面可以跟空格。
- 用户表达统一用中文引号「」包裹，不用双引号 `""`。
- 标点遵循 GB/T 15834：中文句内用中文标点（。，；：），代码段、英文术语、CLI 命令保留英文标点。

### 4.3 中英混排

- 中文与英文 / 数字之间加一个空格（盘古之白）。
  - ❌ 「在Moka ATS中」 ✅ 「在 Moka ATS 中」
  - ❌ 「运行cllmk curl」 ✅ 「运行 `cllmk curl`」
- CLI 命令、API 路径、字段名、错误码用 `code` 包裹；界面按钮、模块名用「」包裹。

## 5. 业务安全红线

下列原则**不可妥协**，写入即事故：

1. **默认只预览**：所有删除、阶段移动、保护期修改、字段停用等写操作，脚本默认 dry-run；
   只有 `--confirm` + `--expected-org-id <orgId>` 同时到位且与实时 current orgId 一致时才允许写入。
2. **不输出凭证**：Cookie、token、登录态、认证头**永远不出现在终端输出、日志、Agent 回复中**；
   identity 展示仅限 `orgId`/`orgName`/`tenantId`/`buId`/`corpName`/`realname`，禁止展示 email。
3. **不猜 payload**：遇到当前 skill 未覆盖的接口形态、字段类型、参数语义时，
   **停止写入**并要求用户提供 UI curl 反推，不允许猜 type 枚举或字段默认值。
4. **current 指针全局共享**：切换 / 登录 / 登出的副作用必须在业务文档中显式说明；
   跨租户任务串行执行（`switch → status → 完成本任务 → switch`），不允许并行；
   任务收尾时必须向用户明示 current 最终停在哪个租户。
5. **网络重试白名单**：仅对幂等 GET/HEAD 以及 DNS 解析失败（`ENOTFOUND`/`EAI_AGAIN`）且
   **未建立连接**的写请求允许重试；`ECONNRESET`/`ETIMEDOUT`/`socket hang up` 一律先回读再决定是否重复。

## 6. 评审流程

### 6.1 一次装好本地守卫

```bash
git config core.hooksPath .githooks     # 或：ln -sf ../../.githooks/pre-commit .git/hooks/pre-commit
```

hook 依次跑四道守卫，任一失败即拒绝提交：

| # | 守卫 | 内容 |
|---|---|---|
| 1 | `scripts/lint_skill_routes.py` | 路由与文档约定（见 6.2） |
| 2 | `scripts/test_lint_skill_routes.py` | lint 自身的变异测试 —— 每条检查都有「故意写坏必须报」的反向用例 |
| 3 | `skills/ats/scripts/_test/test_safety_guards.py` | §5 红线在脚本层的唯一自动化守卫 |
| 4 | `test_offer_template.py` / `test_parse_form_file.py` | 依赖 `python-docx` / `pytest`，缺依赖则跳过不阻断 |

**两侧 foundation 是否同步，机器查不到**：两份都是手写的最终文档，正文按 system 不同，
diff 天然不相等，没有可自动比对的基线。这一条只能靠 §6.3 的人工复查兜住。

**为什么 2 和 3 必须在 hook 里**：本 hook 曾只跑 lint。`test_safety_guards.py` 被移动目录后，
44 条安全断言全部 `FileNotFoundError` 而 lint 照样绿，没人察觉。守卫本身不被守卫，等于没有守卫。

### 6.2 lint 已经机器化的检查（不必人工复查）

**ERROR 级（阻断提交）**：

- frontmatter 必须用 `route:`，不得用 `name:` / `description:`。
- 路由表登记的 route → 文件存在，且文件内 `route:` 完全一致。
- 双向归属：有 `route:` 必须被某个 SKILL.md 登记；结构上像主文档却没 `route:` 也报错。
  （**主文档的权威定义是「出现在路由表里」**，目录形状只是弱信号 —— `form-config/` 没有
  `index.md`，其唯一文档直接登记在顶层路由表，这也是合法的。）
- 被登记的主文档必须有首行 callout。
- **所有**带 callout 的文档（含二级子文档）：callout 里的 `Step 1–N` 必须等于所属
  SKILL.md「业务公共前置」的实际步数，`data.system` 断言必须匹配所属 skill。
  这条专治真实发生过的事故：people 侧插入一步后，下游 callout 的 N 集体过期。
- 超过 400 行的文档必须有 `## 目录`。
- 禁用口语：`当前不覆盖` / `待建` / `待扩展` / `当前不支持`。
- 「本路由 」后跟空格再跟动词（加粗与版本号例外）。
- 文档里写的 `<skill-dir>/scripts/**.py` 必须真实存在。

**WARNING 级（提示不阻断，`--strict` 可提升为 ERROR）**：

- 中文内容用了英文双引号 `""`。历史存量较多，且服务端返回的字面量（如报错文案）
  更应该用 `` `code` `` 包裹而不是「」，属于需要判断的灰区，故不硬拦。
- 文档超过 700 行，建议按操作原语拆子目录。
- 二级目录有多个文档却没有 `index.md`（缺派发入口）。

### 6.3 仍然需要人工判断的部分

lint 只能查形式，查不了语义。提交前请自己回答：

- **术语是否符合 `_glossary.md`**：同义改写（「候选人档案」vs「候选人主档」）机器认不出来。
- **范围边界 vs 安全硬约束有没有被写反**（见 §4.1）：两者句式都合规，但语义相反，
  错一个字就会让模型从「停下来问用户」变成「自己猜一个」。
- **SKILL.md 新增的边界表行是否仍是「指针型」短条目**，没有偷偷展开业务细节（§2.2）。
- **改动 `foundation/` 时（最高敏感级别，且 lint 查不到）**：
  `ats` 和 `people` 两侧的同名文档都改了吗？还是只改了一侧？
  新增的规则在两侧的措辞是否等价（只有系统专属的命令、字段、env 允许不同）？
  是否需要同步两个 `SKILL.md` 的「基础能力路由」表与 description？是否影响已实现业务的鉴权与租户切换流程？
- **双系统对照内容有没有被误删**：身份字段对照表、「system 选错」的兜底两侧都必须在。
  只留自己那一半，模型就无法判断自己是不是拿错了会话 —— 这属于把安全兜底删了。
- **是否给新写的业务脚本补了安全断言**：脚本层的红线只有 `test_safety_guards.py` 在守。
  新增写操作脚本却不在那里加用例，等于这个脚本没有守卫。

## 7. 新增业务的 SOP

### 新增 ATS 业务路由

1. 在 `skills/ats/references/operations/` 下新建 `<route>.md`（或 `<sub>/index.md` + 子文档）。
2. frontmatter 写 `route: <route>`。
3. 业务主文档 H1 后插入首行 callout（见 §3.2）。
4. 超过 400 行的文档加「## 目录」。
5. 在 `skills/ats/SKILL.md` 路由表登记「意图关键词 → route → 文档路径」。
6. 在 `_glossary.md` 登记新增术语。
7. 如产生脚本，放到 `skills/ats/scripts/<route>/` 目录下，脚本开头须有英文 docstring + 中文安全提示。
8. 跑 `python3 scripts/lint_skill_routes.py` 通过后才能提交。

### 新增 People 业务路由

同上，但目标路径改为 `skills/people/references/operations/`，SKILL.md 改为 `skills/people/SKILL.md`。
foundation 引用一律写 `<skill-dir>/references/foundation/`（people 自带一份），
不要跨 skill 指向 `skills/ats/` —— 安装器不会把别的 skill 一起带上。

### 新增基础能力（安装 / 鉴权 / 租户）

**先停下来**：这三项在 `ats` 和 `people` 各有一份，**改动必须两侧同步**。新增/修改前必须回答：
- 这是新规则还是新例外？是否要在原文件里新增章节，而不是新建文件？
- 这段内容对 ATS 和 People 一样吗？一样就两侧写同样的话；不一样就各写自己那套命令、字段和 env。
- 需要同步更新 `ats/SKILL.md` / `people/SKILL.md` 的 description 吗？
  （安装/鉴权/租户切换的触发面全靠它，没有独立入口兜底）
- 需要同步更新两个 SKILL.md 的「基础能力路由」表吗？

改完把两侧文档一起提交，commit message 里写清影响面（§9）。

## 8. 反模式清单（禁止）

| 反模式 | 纠正动作 |
|---|---|
| 在 `SKILL.md` 里展开业务细节 | 下沉到 operations 主文档 |
| 在 operations 里复制鉴权/租户切步 | 用首行 callout 引用 SKILL.md 业务公共前置 |
| 用 `name:`/`description:` 作为 frontmatter 键 | 统一 `route:` |
| 「当前不覆盖」「待建」 | 统一「不在本 skill 覆盖范围」+ 给出替代路径 |
| 「本路由 通过」/「本路由 覆盖」 | 「本路由通过」「本路由覆盖」 |
| 只改一侧的 `foundation/` 就提交 | 两侧同名文档一起改、一起提交（§2.1） |
| 跨 skill 引用 `skills/ats/references/foundation/` | 用本 skill 的 `<skill-dir>/references/foundation/`（安装器不会带上别的 skill） |
| 把双系统对照内容也按 system 拆开 | 身份字段表、「system 选错」兜底两侧都保留，那是模型识别拿错会话的依据 |
| 新增二级目录子文档时也加 `route:` | 只有主文档（顶层 `.md` / `index.md`）需要 `route:` |
| 加新术语但不更新 `_glossary.md` | 先登记术语再使用 |
| 不看 lint 直接提交 | 装 hook：`git config core.hooksPath .githooks` |
| 移动脚本/测试目录后不跑测试 | `__file__` 相对路径会集体失效，移动后必须实跑一遍 |
| 把安全硬约束改写成范围边界 | 保留「一律不允许」「禁止」「停止写入」的禁止语气（§4.1） |
| SKILL.md 加了一步却不改下游 callout 的 `Step 1–N` | lint 会拦；不要手改绕过 |

## 9. 版本与审计

- 每个 skill 的 `metadata.version` 遵循 semver：新增路由 → minor；修改业务规则 → minor；仅 rewording → patch。
- 涉及 foundation 的改动，**必须**在 git commit message 中显式说明影响面，
  并列出实际改到的两侧文件（只列一侧通常意味着漏改）。
- 仓库内的 git commit 历史是合规审计源，不允许 force-push 主线。
