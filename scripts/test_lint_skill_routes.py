#!/usr/bin/env python3
"""lint_skill_routes.py 的变异测试。

为什么需要它：lint 是这个仓库唯一的自动化约定守卫。如果 lint 本身有 bug
（正则写错、检查被短路、判定口径反了），它会**安静地通过**，而所有人以为
约定还在被执行 —— 这正是 test_safety_guards.py 被移动目录后 44 条断言
静默失效的同一类故障。所以每条 ERROR 级检查都要有一个「故意写坏 → lint 必须报」
的反向用例。

做法：把 skills/ 复制到临时目录，施加一处变异，用 CLLMK_LINT_ROOT 指向副本跑 lint，
断言退出码非 0 且命中预期的错误标签。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT = REPO_ROOT / "scripts" / "lint_skill_routes.py"


class LintMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="cllmk-lint-")
        self.root = Path(self.tmp.name)
        shutil.copytree(REPO_ROOT / "skills", self.root / "skills")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_lint(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(LINT)],
            env={**os.environ, "CLLMK_LINT_ROOT": str(self.root)},
            capture_output=True, text=True, timeout=60,
        )

    def p(self, rel: str) -> Path:
        return self.root / rel

    def edit(self, rel: str, old: str, new: str) -> None:
        """在副本里做一处定点替换，并断言替换确实发生（防止用例因源文改写而空跑）。"""
        f = self.p(rel)
        text = f.read_text(encoding="utf-8")
        self.assertIn(old, text, f"变异锚点已失效，请更新用例：{rel} 中找不到 {old!r}")
        f.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assert_fails_with(self, label: str) -> None:
        r = self.run_lint()
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1, f"lint 应该失败但通过了：\n{out}")
        self.assertIn(label, out, f"lint 失败了但没报 {label}：\n{out}")

    # ---------- 基线：未变异的副本必须通过 ----------
    def test_pristine_copy_passes(self) -> None:
        r = self.run_lint()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ---------- 每条 ERROR 检查的反向用例 ----------
    def test_detects_stale_callout_step_range(self) -> None:
        # 这是本轮真实踩过的 bug：SKILL.md 加了一步，下游 callout 的 N 没跟着改
        self.edit("skills/ats/references/operations/job-delete.md", "Step 1–6", "Step 1–5")
        self.assert_fails_with("callout Step 区间过期")

    def test_detects_step_drift_when_skill_md_gains_a_step(self) -> None:
        # 反向验证：改 SKILL.md 的步数，所有下游 callout 应集体报错
        text = self.p("skills/ats/SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"^6\. ", text, re.M)
        self.assertIsNotNone(m, "ats/SKILL.md 业务公共前置不再是 6 步，请更新用例")
        self.p("skills/ats/SKILL.md").write_text(
            text[: m.end()] + text[m.end():].replace("\n\n## ", "\n7. 新增的一步\n\n## ", 1),
            encoding="utf-8",
        )
        self.assert_fails_with("callout Step 区间过期")

    def test_detects_wrong_system_assertion(self) -> None:
        self.edit("skills/ats/references/operations/job-delete.md",
                  'data.system === "ats"', 'data.system === "people"')
        self.assert_fails_with("callout system 断言错误")

    def test_detects_missing_callout(self) -> None:
        f = self.p("skills/ats/references/operations/job-delete.md")
        f.write_text(
            "\n".join(l for l in f.read_text(encoding="utf-8").split("\n")
                      if "执行前必读" not in l),
            encoding="utf-8")
        self.assert_fails_with("缺少首行 callout")

    def test_detects_route_mismatch_between_doc_and_skill_md(self) -> None:
        self.edit("skills/ats/references/operations/job-delete.md",
                  "route: job-delete", "route: job-delete-renamed")
        self.assert_fails_with("route 不一致")

    def test_detects_route_pointing_at_missing_file(self) -> None:
        self.p("skills/ats/references/operations/job-delete.md").unlink()
        self.assert_fails_with("路由指向不存在文件")

    def test_detects_subdoc_carrying_route(self) -> None:
        # 子文档误加 route: —— 会让二级派发出现两个事实来源
        f = self.p("skills/ats/references/operations/candidate/candidate-field-manage.md")
        f.write_text("---\nroute: candidate-field-manage\n---\n\n"
                     + f.read_text(encoding="utf-8"), encoding="utf-8")
        self.assert_fails_with("route: 未被登记")

    def test_detects_forbidden_frontmatter_field(self) -> None:
        self.edit("skills/ats/references/operations/job-delete.md",
                  "route: job-delete", "name: job-delete")
        self.assert_fails_with("frontmatter 字段名错误")

    def test_detects_forbidden_scope_phrasing(self) -> None:
        self.edit("skills/ats/references/operations/job-delete.md",
                  "# ", "# 待扩展 ")
        self.assert_fails_with("禁用表述")

    def test_detects_reference_to_nonexistent_script(self) -> None:
        f = self.p("skills/ats/references/operations/job-delete.md")
        f.write_text(f.read_text(encoding="utf-8")
                     + "\n\n运行 `<skill-dir>/scripts/job-delete/does_not_exist.py`。\n",
                     encoding="utf-8")
        self.assert_fails_with("引用脚本不存在")

    def test_detects_missing_toc_in_long_doc(self) -> None:
        self.edit("skills/ats/references/operations/offer-template-manage.md",
                  "## 目录", "## 章节导航")
        self.assert_fails_with("超长文档缺目录")

    def test_detects_spaced_route_phrase(self) -> None:
        f = self.p("skills/ats/references/operations/job-delete.md")
        f.write_text(f.read_text(encoding="utf-8") + "\n本路由 覆盖批量删除。\n",
                     encoding="utf-8")
        self.assert_fails_with("多余空格")

    def test_detects_orphan_main_doc(self) -> None:
        # 新建一个结构上是主文档但没在路由表登记的文件
        self.p("skills/ats/references/operations/brand-new-route.md").write_text(
            "---\nroute: brand-new-route\n---\n\n# 全新业务\n", encoding="utf-8")
        self.assert_fails_with("route: 未被登记")

    def test_detects_main_doc_without_frontmatter(self) -> None:
        self.p("skills/ats/references/operations/no-frontmatter.md").write_text(
            "# 没有 frontmatter 的主文档\n", encoding="utf-8")
        self.assert_fails_with("缺少 route: 且未登记")

    # ---------- WARNING 档：不阻断，但 --strict 下要能提升 ----------
    def test_quote_violation_is_warning_not_error(self) -> None:
        f = self.p("skills/ats/references/operations/job-delete.md")
        f.write_text(f.read_text(encoding="utf-8") + '\n用户说"删掉这个职位"。\n',
                     encoding="utf-8")
        self.assertEqual(self.run_lint().returncode, 0, "引号问题不应阻断提交")
        strict = subprocess.run(
            [sys.executable, str(LINT), "--strict"],
            env={**os.environ, "CLLMK_LINT_ROOT": str(self.root)},
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(strict.returncode, 1, "--strict 下引号问题应提升为 ERROR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
