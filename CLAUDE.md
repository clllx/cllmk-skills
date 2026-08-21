# CLAUDE.md

本仓库的工作守则收敛在 [AGENT.md](./AGENT.md)。

**在编辑 `skills/` 下任何文件前，必须先完整阅读 AGENT.md**，包括其中定义的：

- 目录结构约定（§1）
- 核心架构原则：SSOT / 路由与业务分层（§2）
- 文档格式约定：frontmatter / 首行 callout / 目录 / 「不在本路由覆盖范围」（§3）
- 文字与术语规范（§4），所有术语以 `skills/ats/references/_glossary.md` 为准
- 业务安全红线（§5）
- 评审流程（§6）
- 新增业务的 SOP（§7）
- 反模式清单（§8）

提交前必跑：

```bash
python3 scripts/lint_skill_routes.py
```

不通过不允许提交。
