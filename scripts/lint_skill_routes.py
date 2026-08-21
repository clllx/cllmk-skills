#!/usr/bin/env python3
"""校验 cllmk skill 仓库的路由一致性与文档格式约定（AGENT.md §3 / §4 的机器可查部分）。

设计意图：AGENT.md §6 原本把「callout 是否存在」「术语是否一致」「边界表述是否标准」
全部列为人工检查项。人工检查会漏（例如 people 侧插入新 Step 后，下游 callout 的
`Step 0–7` 没人跟着改）。凡是能机器判定的约定都搬到这里，人工评审只留真正需要判断力的部分。

分两档输出：
  ERROR   —— 阻断提交（退出码 1）
  WARNING —— 只提示，不阻断；加 --strict 时提升为 ERROR

用法：
  python3 scripts/lint_skill_routes.py [--strict]
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# 默认校验本仓库；CLLMK_LINT_ROOT 用于让自测脚本在临时副本上跑同一套规则
REPO_ROOT = Path(os.environ.get("CLLMK_LINT_ROOT") or Path(__file__).resolve().parent.parent)
SKILLS_DIR = REPO_ROOT / "skills"

# 主 skill（含业务路由表与「业务公共前置」）；新增主 skill 时在此追加
MAIN_SKILLS = ["ats", "people"]

# 「本路由 X」的合法例外：X 以 `**`（加粗）或版本号开头
_PERMITTED_ROUTE_SUFFIX = re.compile(r"^本路由 (\*\*|\d|v\d)")

# §3.4 / §4.1 禁用的口语化范围表述。规范文件自身要引用这些词做反例，故豁免
_FORBIDDEN_PHRASES = ["当前不覆盖", "待建", "待扩展", "当前不支持"]
_SPEC_FILES = {"_glossary.md"}

CJK = r"一-鿿"
_CJK_DOUBLE_QUOTE = re.compile(rf'"[^"\n]*[{CJK}][^"\n]*"')
_SCRIPT_REF = re.compile(r"<skill-dir>/(scripts/[A-Za-z0-9_\-/]+\.py)")


class Report:
    """收集 ERROR / WARNING 两档结果。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def strip_code(text: str) -> list[str]:
    """按行剥离 fenced code block 与 inline code。

    payload 示例、JSON、curl 里的英文双引号是合法的，不能当排版违规，
    所以做引号类检查前必须先把代码段清空（保留行号，行内容置空）。
    """
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else re.sub(r"`[^`]*`", "", line))
    return out


def split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """拆出 frontmatter 行与正文行；无 frontmatter 时前者为空。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return [], lines
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:i], lines[i + 1 :]
    return [], lines


def parse_frontmatter_route(md_path: Path) -> str | None:
    """抽取 frontmatter 的 `route:` 值。

    返回 None 表示没有 frontmatter 或没有 route；
    返回 `__wrong_field__:<字段名>` 表示用了 §3.1 禁止的 `name:` / `description:`。
    """
    fm, _ = split_frontmatter(md_path.read_text(encoding="utf-8", errors="replace"))
    if not fm:
        return None
    for line in fm:
        s = line.strip()
        if s.startswith("route:"):
            return s.split(":", 1)[1].strip()
        if s.startswith("name:") or s.startswith("description:"):
            return f"__wrong_field__:{s.split(':', 1)[0]}"
    return None


def extract_routes_from_skill_md(skill_md: Path) -> dict[str, str]:
    """解析 SKILL.md 业务路由表，返回 {route: reference 相对路径}。"""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"\|\s*[^|]*\|\s*`([a-z0-9\-_]+)`\s*\|\s*`(references/operations/[^`]+)`\s*\|"
    )
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}


def count_prelude_steps(skill_md: Path) -> int | None:
    """统计 SKILL.md「业务公共前置」小节里的顶层编号步骤数。

    下游所有主文档的 callout 会写「（Step 1–N）」，N 必须等于这里的实际步数。
    这是历史上真实踩过的坑：people 侧插入一步后，下游 callout 的 N 集体过期。
    """
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^## 业务公共前置\s*$", text, re.M)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = re.search(r"^## ", rest, re.M)
    section = rest[: nxt.start()] if nxt else rest
    numbers = [int(x) for x in re.findall(r"^(\d+)\.\s", section, re.M)]
    return max(numbers) if numbers else None


def check_callout_content(doc: Path, skill: str, steps: int | None, report: Report) -> bool:
    """校验文档开头 callout 的 Step 区间与 system 断言；返回是否找到 callout。

    这一项对**所有**带 callout 的文档生效，不只主文档 —— 二级子文档动辄五六百行，
    模型会直接读它，Step 区间写错的后果和主文档一样：跳过鉴权前置直接调接口。
    """
    text = doc.read_text(encoding="utf-8", errors="replace")
    _, body = split_frontmatter(text)
    head = "\n".join(body[:8])
    if "执行前必读" not in head:
        return False

    if steps is not None and f"Step 1–{steps}" not in head:
        found = re.search(r"Step [0-9]+[–\-][0-9]+", head)
        report.error(
            f"[callout Step 区间过期] {rel(doc)}：写的是 "
            f"{found.group(0) if found else '（未写区间）'}，"
            f"{skill}/SKILL.md 实际是 Step 1–{steps}"
        )
    if f'data.system === "{skill}"' not in head:
        report.error(f'[callout system 断言错误] {rel(doc)}：应断言 data.system === "{skill}"')
    return True


def check_doc_length(doc: Path, report: Report) -> None:
    """§3.3：超长文档必须可跳读。400 行要目录，700 行提示拆分。"""
    line_count = len(doc.read_text(encoding="utf-8", errors="replace").split("\n"))
    if line_count > 400 and not re.search(r"^## 目录\s*$", doc.read_text(encoding="utf-8"), re.M):
        report.error(f"[超长文档缺目录] {rel(doc)}：{line_count} 行 > 400 行，需在 H1 后加「## 目录」")
    if line_count > 700:
        report.warn(f"[文档过长] {rel(doc)}：{line_count} 行 > 700 行，考虑按操作原语拆子目录（§3.3）")


def looks_like_main_doc(p: Path) -> bool:
    """结构上「应该被登记为主路由」的启发式：operations 顶层 .md，或二级目录的 index.md。

    注意这只是启发式，不是权威判据 —— 权威判据是「有没有出现在 SKILL.md 路由表里」。
    反例：`form-config/` 没有 index.md，其唯一文档直接登记在顶层路由表，
    结构上不像主文档但确实是。所以这个函数只用来兜「结构上该登记却漏登记」，
    不用来反推「不像主文档的就是子文档」。
    """
    if p.name.startswith("_"):
        return False
    if p.parent.name == "operations":
        return p.name != "index.md"
    return p.name == "index.md"


def main() -> int:
    strict = "--strict" in sys.argv
    report = Report()

    ref_files = sorted(SKILLS_DIR.glob("*/references/**/*.md"))
    op_files = sorted(SKILLS_DIR.glob("*/references/operations/**/*.md"))

    # ---------- 各主 skill 的路由表与前置步数 ----------
    skill_routes: dict[str, dict[str, str]] = {}
    skill_steps: dict[str, int | None] = {}
    for skill in MAIN_SKILLS:
        skill_md = SKILLS_DIR / skill / "SKILL.md"
        if not skill_md.exists():
            report.error(f"[缺失主入口] skills/{skill}/SKILL.md")
            continue
        skill_routes[skill] = extract_routes_from_skill_md(skill_md)
        steps = count_prelude_steps(skill_md)
        if steps is None:
            report.error(f"[无法解析业务公共前置] {rel(skill_md)}：未找到「## 业务公共前置」或编号步骤")
        skill_steps[skill] = steps

    # ---------- 校验 1：frontmatter 字段名 + 主文档必须有 route ----------
    for doc in op_files:
        if doc.name.startswith("_"):
            continue
        route = parse_frontmatter_route(doc)
        if route and route.startswith("__wrong_field__:"):
            bad = route.split(":", 1)[1]
            report.error(f"[frontmatter 字段名错误] {rel(doc)}：用了 `{bad}:`，本仓库统一 `route:`")
            continue
        # 「缺 route:」由校验 3 统一判定（那里能结合是否登记给出更准的建议）

    # ---------- 校验 2：SKILL.md 登记的 route 必须落到实际文件 ----------
    for skill, routes in skill_routes.items():
        skill_dir = SKILLS_DIR / skill
        for route, ref in routes.items():
            ref_path = skill_dir / ref
            if not ref_path.exists():
                report.error(f"[路由指向不存在文件] skills/{skill}/SKILL.md route={route} → {ref}")
                continue
            fm_route = parse_frontmatter_route(ref_path)
            if fm_route != route:
                report.error(
                    f"[route 不一致] {rel(ref_path)} frontmatter route={fm_route!r}，"
                    f"SKILL.md 登记 {route!r}"
                )

    # ---------- 校验 3：以路由表登记为权威，双向校验 route: 的归属 ----------
    # 主文档的权威定义 = 出现在某个 SKILL.md 路由表里。由此推出两条：
    #   有 route: 却没登记 → 要么漏登记（死文档，永远路由不到），要么给子文档误加了 route:
    #   结构上像主文档却没有 route: → 漏写 frontmatter
    registered: dict[str, set[Path]] = {}
    for skill, routes in skill_routes.items():
        registered[skill] = {(SKILLS_DIR / skill / ref).resolve() for ref in routes.values()}

    for doc in op_files:
        if doc.name.startswith("_"):
            continue
        skill = doc.relative_to(SKILLS_DIR).parts[0]
        route = parse_frontmatter_route(doc)
        is_registered = doc.resolve() in registered.get(skill, set())

        if route and not route.startswith("__wrong_field__:") and not is_registered:
            report.error(
                f"[route: 未被登记] {rel(doc)}：route={route} 不在 skills/{skill}/SKILL.md 路由表。"
                f"若它是主文档 → 去路由表登记；若它是子文档 → 删掉 route:，"
                f"改由同目录 index.md 按路径派发（§8）"
            )
        elif route is None and looks_like_main_doc(doc) and not is_registered:
            report.error(f"[缺少 route: 且未登记] {rel(doc)}：结构上是主文档，需补 route: 并在路由表登记")

    # ---------- 校验 5：callout 与文档长度 ----------
    for doc in op_files:
        if doc.name.startswith("_"):
            continue
        skill = doc.relative_to(SKILLS_DIR).parts[0]
        has_callout = check_callout_content(doc, skill, skill_steps.get(skill), report)
        # callout 的「存在性」只对被登记的主文档强制：
        # 子文档可能是纯参考资料（如 api-templates.md），没有独立执行入口，不需要 callout
        if doc.resolve() in registered.get(skill, set()) and not has_callout:
            report.error(
                f"[缺少首行 callout] {rel(doc)}：H1 下方需紧跟「⚠️ 执行前必读」（AGENT.md §3.2）"
            )
        check_doc_length(doc, report)

    # ---------- 校验 6（WARNING）：二级目录缺 index.md ----------
    for skill in skill_routes:
        ops = SKILLS_DIR / skill / "references" / "operations"
        for sub in sorted(d for d in ops.glob("*") if d.is_dir()):
            docs = [f for f in sub.glob("*.md") if not f.name.startswith("_")]
            if len(docs) > 1 and not (sub / "index.md").exists():
                report.warn(
                    f"[二级目录缺 index.md] {rel(sub)}：目录内有 {len(docs)} 个文档却没有派发入口，"
                    f"顶层路由表会被迫登记多条同目录路由（§1 / §2.3）"
                )

    # ---------- 校验 7：「本路由 + 动词」多余空格（§4.2） ----------
    for doc in ref_files:
        for i, line in enumerate(doc.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            if _PERMITTED_ROUTE_SUFFIX.search(line) or doc.name in _SPEC_FILES:
                continue
            if "本路由 " in line:
                report.error(f"[多余空格] {rel(doc)}:{i} 「本路由」后直接接动词，不加空格：{line.strip()[:50]}")

    # ---------- 校验 8：禁用的口语化范围表述（§3.4 / §4.1） ----------
    for doc in ref_files + sorted(SKILLS_DIR.glob("*/SKILL.md")):
        if doc.name in _SPEC_FILES:
            continue
        for i, line in enumerate(strip_code(doc.read_text(encoding="utf-8", errors="replace")), 1):
            for phrase in _FORBIDDEN_PHRASES:
                if phrase in line:
                    report.error(
                        f"[禁用表述] {rel(doc)}:{i} 出现「{phrase}」，"
                        f"改为「不在本 skill 覆盖范围」并给出替代路径：{line.strip()[:50]}"
                    )

    # ---------- 校验 9：文档引用的脚本必须真实存在 ----------
    # 文档写 <skill-dir>/scripts/... 却没有这个文件时，模型会照着跑然后失败
    for doc in ref_files + sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_dir = SKILLS_DIR / doc.relative_to(SKILLS_DIR).parts[0]
        for m in _SCRIPT_REF.finditer(doc.read_text(encoding="utf-8", errors="replace")):
            if not (skill_dir / m.group(1)).exists():
                report.error(f"[引用脚本不存在] {rel(doc)} → {m.group(1)}")

    # ---------- 校验 10（WARNING）：中文内容用了英文双引号（§4.2） ----------
    # 历史债较多且服务端返回字面量属于灰区（更应该用 `code` 包裹），故不阻断提交
    for doc in ref_files + sorted(SKILLS_DIR.glob("*/SKILL.md")):
        if doc.name in _SPEC_FILES:
            continue
        _, body = split_frontmatter(doc.read_text(encoding="utf-8", errors="replace"))
        for i, line in enumerate(strip_code("\n".join(body)), 1):
            for m in _CJK_DOUBLE_QUOTE.finditer(line):
                report.warn(
                    f"[英文双引号] {rel(doc)}: {m.group(0)[:40]} —— "
                    f"用户表达/界面文案用「」，服务端字面量用 `code` 包裹"
                )

    # ---------- 输出 ----------
    if report.warnings:
        print(f"⚠️  WARNING（{len(report.warnings)} 项，不阻断提交）：")
        for w in report.warnings[:20]:
            print(f"  - {w}")
        if len(report.warnings) > 20:
            print(f"  … 另有 {len(report.warnings) - 20} 项同类，加 --strict 可全部提升为 ERROR")
        print()

    errors = report.errors + (report.warnings if strict else [])
    if errors:
        print(f"❌ Lint 失败（{len(errors)} 项 ERROR）：")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"✅ Lint 通过：{len(op_files)} 个 operations 文档、"
        f"{len(skill_routes)} 个主 skill 路由表一致"
        + (f"（{len(report.warnings)} 项 WARNING 未阻断）" if report.warnings else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
