---
route: candidate
---

# ATS 候选人信息管理

## 前置鉴权

在执行任何子场景前，按 `<skill-dir>/SKILL.md` 的「业务公共前置」完成鉴权
（安装确认 → `cllmk auth status` → 登录引导），
确认 `data.system === "ats"` 后再进入子场景路由。

## 系统入口

根据子场景不同，入口 URL 不同：

### 候选人字段管理

| 环境 | URL |
|------|-----|
| cn   | https://app.mokahr.com/settings/custom_field |
| intl | https://hire-r1.mokahr.com/settings/custom_field |
| s3   | https://staging-3.mokahr.com/settings/custom_field |

### 登记表模板设置

| 环境 | URL |
|------|-----|
| cn   | https://app.mokahr.com/settings/apply_form |
| intl | https://hire-r1.mokahr.com/settings/apply_form |
| s3   | https://staging-3.mokahr.com/settings/apply_form |

## 子场景路由

| 用户意图 | 执行 |
|---------|------|
| 含「登记表」「申请表」「应聘表」「报名表」任一关键词 | `<skill-dir>/references/operations/candidate/form-template.md` |
| 其余情况（含「加个字段」「新增字段」「更新字段」等模糊表达） | `<skill-dir>/references/operations/candidate/candidate-field-manage.md` |

> 默认路由到字段管理，无需询问用户确认子场景。
>
> `form-template.md` 执行过程中若识别出系统缺少的字段，
> 将按需加载同目录的 `candidate-field-manage.md` 完成字段创建后继续。

## 不在本路由 范围内

| 需求 | 应使用 |
|------|-------|
| 招聘需求（HC / Headcount）字段 | `cllmk` 的 `hc-field-manage` 路由 |
| 职位自定义字段 | `cllmk` 的 `job-field-manage` 路由 |
| Offer 字段 | 待建 |
| 候选人字段权限管理 | 待建（未来扩展） |
