# Agent Skills

可复用的 Agent Skills 集合。每个技能位于 `skills/<name>/`，并包含符合 Agent Skills 规范的 `SKILL.md`。

## 使用 npx skills 安装

列出仓库中的技能：

```bash
npx skills add clllx/skills --list
```

交互式选择并安装：

```bash
npx skills add clllx/skills
```

安装个人计划与复盘相关技能：

```bash
npx skills add clllx/skills \
  --skill planning-center \
  --skill daily-capture \
  --skill review-align
```

安装到 OpenClaw：

```bash
npx skills add https://github.com/clllx/skills \
  --skill planning-center \
  --skill daily-capture \
  --skill review-align \
  --agent openclaw
```

增加 `--global` 可安装到 `~/.openclaw/skills/`，供本机 OpenClaw Agent 共享使用。

## OpenClaw 原生安装

OpenClaw 原生 Git 安装要求安装源根目录直接包含一个 `SKILL.md`，适合单技能仓库：

```bash
openclaw skills install git:owner/single-skill-repo@main
```

本仓库包含多个技能。推荐使用上方的 `npx skills add ... --agent openclaw` 安装，或将单个技能发布到 ClawHub 后执行：

```bash
openclaw skills install <skill-slug>
```

## 计划与复盘技能

| Skill | 用途 |
| --- | --- |
| `planning-center` | 创建、修改、删除和归档个人计划 |
| `daily-capture` | 通过 `/daily` 采集并保存每日原始记录 |
| `review-align` | 通过 `/review` 生成日、周、月复盘与罗盘 |

默认数据目录为 `/opt/daily/user/`。多用户 OpenClaw 部署需要改成用户级目录，并配置会话隔离，避免不同用户共用文件。
