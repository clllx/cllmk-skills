from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


# 本文件位于 skills/ats/scripts/_test/，被测业务脚本在上一级 scripts/ 的各路由目录下。
# 注意：这三个常量必须跟着文件位置一起改，否则所有 subprocess 调用都会 FileNotFoundError。
TEST_DIR = Path(__file__).resolve().parent          # skills/ats/scripts/_test
SCRIPTS_DIR = TEST_DIR.parent                        # skills/ats/scripts
SKILL_DIR = SCRIPTS_DIR.parent                       # skills/ats
SCRIPTS = {
    "application-delete": SCRIPTS_DIR / "application-delete" / "bulk_delete.py",
    "application-move-stage": SCRIPTS_DIR / "application-move-stage" / "bulk_move.py",
    "talent-pool-candidate-delete": (
        SCRIPTS_DIR / "talent-pool-candidate-delete" / "bulk_remove.py"
    ),
    "job-delete": SCRIPTS_DIR / "job-delete" / "bulk_delete.py",
    "protection-period-create": (
        SCRIPTS_DIR / "protection-period-country" / "create_batch.py"
    ),
    "protection-period-reorder": (
        SCRIPTS_DIR / "protection-period-country" / "reorder_to_top.py"
    ),
}
WRITE_URLS = (
    "/application/delete",
    "/application/bulk/delete",
    "/move-stage/v2",
    "/talent-pool-candidates/bulk/delete",
    "/jobs/deleteJob",
    "/protectionPeriod/create",
    "/protectionPeriod/changePriority",
)


class SafetyGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="cllmk-safety-")
        self.root = Path(self.temp_dir.name)
        self.call_log = self.root / "cllmk-calls.log"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_cllmk = bin_dir / "cllmk"
        fake_cllmk.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ["CLLMK_TEST_LOG"]).open("a").write(" ".join(sys.argv[1:]) + "\\n")
args = " ".join(sys.argv[1:])
if "/api/v2/org/info" in args:
    data = {
        "orgInfo": {"orgId": "org-test"},
        "stages": [
            {"id": 1, "name": "From", "disabled": False, "orgId": "org-test"},
            {"id": 2, "name": "To", "disabled": False, "orgId": "org-test"},
        ],
    }
elif os.environ.get("CLLMK_TEST_BULK_UNIQUE") == "1" and "/application/bulk/delete" in args:
    print(json.dumps({"code": 0, "data": {"success": False, "msg": "400059"}}))
    raise SystemExit(0)
elif os.environ.get("CLLMK_TEST_BULK_UNIQUE") == "1" and '"applicationId": 2' in args:
    print(json.dumps({"code": 0, "data": {"success": False, "msg": "400059"}}))
    raise SystemExit(0)
elif os.environ.get("CLLMK_TEST_NETWORK_FAIL") == "1":
    print("Client network socket disconnected", file=sys.stderr)
    raise SystemExit(1)
else:
    data = {"success": True}
print(json.dumps({"code": 0, "data": data, "msg": ""}))
""",
            encoding="utf-8",
        )
        fake_cllmk.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "CLLMK_TEST_LOG": str(self.call_log),
            "CLLMK_PROFILE": "",
        }

        (self.root / "move.csv").write_text(
            "applicationId,fromStage,toStage\n1,From,To\n", encoding="utf-8"
        )
        (self.root / "content.json").write_text("{}\n", encoding="utf-8")
        (self.root / "countries.txt").write_text("法国\n", encoding="utf-8")
        (self.root / "order.txt").write_text("法国\n", encoding="utf-8")
        (self.root / "ids.json").write_text('{"法国": 1}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS[name]), *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def calls(self) -> list[str]:
        if not self.call_log.exists():
            return []
        return self.call_log.read_text(encoding="utf-8").splitlines()

    def assert_no_write_calls(self) -> None:
        calls = self.calls()
        for call in calls:
            self.assertFalse(
                any(url in call for url in WRITE_URLS),
                f"unexpected write call: {call}",
            )

    def write_calls(self) -> list[str]:
        return [
            call for call in self.calls()
            if any(url in call for url in WRITE_URLS)
        ]

    def clear_calls(self) -> None:
        self.call_log.unlink(missing_ok=True)

    def base_commands(self) -> dict[str, list[str]]:
        return {
            "application-delete": [
                "--type", "application", "--ids", "1", "--workdir", str(self.root / "app"),
            ],
            "application-move-stage": [
                "--input", str(self.root / "move.csv"), "--workdir", str(self.root / "move"),
            ],
            "talent-pool-candidate-delete": [
                "--ids", "1", "--workdir", str(self.root / "talent"),
            ],
            "job-delete": [
                "--job-id", "1caca481-a244-4bab-a13c-719b7b52f399",
                "--workdir", str(self.root / "jobs"),
            ],
            "protection-period-create": [
                "--content-file", str(self.root / "content.json"),
                "--countries", str(self.root / "countries.txt"),
                "--log", str(self.root / "create.log"),
            ],
            "protection-period-reorder": [
                "--order", str(self.root / "order.txt"),
                "--top-priority", "1", "--id-map", str(self.root / "ids.json"),
            ],
        }

    def test_job_batch_create_is_absent_from_cllmk(self) -> None:
        script_dir = SCRIPTS_DIR / "job-batch-create"
        reference_dir = SKILL_DIR / "references" / "operations" / "job-batch-create"
        self.assertFalse(script_dir.exists() and any(script_dir.iterdir()))
        self.assertFalse(reference_dir.exists() and any(reference_dir.iterdir()))
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("| `job-batch-create` |", skill_text)

    def test_help_has_no_cllmk_or_business_side_effects(self) -> None:
        for name in SCRIPTS:
            with self.subTest(name=name):
                result = self.run_script(name, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])

    def test_default_execution_only_previews(self) -> None:
        for name, args in self.base_commands().items():
            with self.subTest(name=name):
                result = self.run_script(name, *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("preview", result.stdout.lower())
        self.assert_no_write_calls()

    def test_confirm_rejects_mismatched_expected_org_before_writing(self) -> None:
        for name, args in self.base_commands().items():
            with self.subTest(name=name):
                result = self.run_script(
                    name, *args, "--confirm", "--expected-org-id", "org-other"
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("does not match", result.stderr + result.stdout)
        self.assert_no_write_calls()

    def test_confirm_requires_expected_org_before_writing(self) -> None:
        for name, args in self.base_commands().items():
            with self.subTest(name=name):
                result = self.run_script(name, *args, "--confirm")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--expected-org-id is required", result.stderr + result.stdout)
        self.assert_no_write_calls()

    def test_matching_expected_org_allows_one_write_call(self) -> None:
        for name, args in self.base_commands().items():
            with self.subTest(name=name):
                self.clear_calls()
                self.run_script(
                    name, *args, "--confirm", "--expected-org-id", "org-test"
                )
                self.assertEqual(len(self.write_calls()), 1, self.calls())

    def test_network_failure_is_not_automatically_retried(self) -> None:
        self.env["CLLMK_TEST_NETWORK_FAIL"] = "1"
        try:
            for name, args in self.base_commands().items():
                with self.subTest(name=name):
                    self.clear_calls()
                    self.run_script(
                        name, *args, "--confirm", "--expected-org-id", "org-test"
                    )
                    self.assertEqual(len(self.write_calls()), 1, self.calls())
        finally:
            self.env.pop("CLLMK_TEST_NETWORK_FAIL", None)

    def test_job_delete_preview_does_not_advance_live_state(self) -> None:
        args = self.base_commands()["job-delete"]
        workdir = self.root / "jobs"

        preview = self.run_script("job-delete", *args)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse((workdir / "state.json").exists())
        self.assertEqual(self.write_calls(), [])

        live = self.run_script(
            "job-delete", *args, "--confirm", "--expected-org-id", "org-test"
        )
        self.assertEqual(live.returncode, 0, live.stderr)
        self.assertEqual(len(self.write_calls()), 1, self.calls())
        state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["next_index"], 1)

    def test_move_stage_resumes_without_resetting_state_or_org(self) -> None:
        workdir = self.root / "move-resume"
        workdir.mkdir()
        (self.root / "move.csv").write_text(
            "applicationId,fromStage,toStage\n1,From,To\n2,From,To\n3,From,To\n",
            encoding="utf-8",
        )
        (workdir / "state.json").write_text(json.dumps({
            "orgId": "org-test", "label": "MOVE", "next_row": 1,
        }))

        result = self.run_script(
            "application-move-stage",
            "--input", str(self.root / "move.csv"),
            "--workdir", str(workdir),
            "--confirm", "--expected-org-id", "org-test",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.write_calls()), 2, self.calls())
        state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state, {"orgId": "org-test", "label": "MOVE", "next_row": 3})

    def test_move_stage_rejects_cross_org_resume_before_writing(self) -> None:
        workdir = self.root / "move-cross-org"
        workdir.mkdir()
        (workdir / "state.json").write_text(json.dumps({
            "orgId": "org-other", "label": "MOVE", "next_row": 1,
        }))

        result = self.run_script(
            "application-move-stage",
            "--input", str(self.root / "move.csv"),
            "--workdir", str(workdir),
            "--confirm", "--expected-org-id", "org-test",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("state.json orgId=org-other", result.stderr + result.stdout)
        self.assert_no_write_calls()

    def test_bulk_400059_only_escalates_confirmed_unique_id(self) -> None:
        self.env["CLLMK_TEST_BULK_UNIQUE"] = "1"
        try:
            workdir = self.root / "app-unique"
            result = self.run_script(
                "application-delete",
                "--type", "application", "--ids", "1,2,3",
                "--workdir", str(workdir),
                "--confirm", "--expected-org-id", "org-test",
                "--interval", "0",
            )
        finally:
            self.env.pop("CLLMK_TEST_BULK_UNIQUE", None)

        self.assertEqual(result.returncode, 0, result.stderr)
        pending = (workdir / "unique_application.pending").read_text().splitlines()
        self.assertEqual(pending, ["2"])
        write_calls = self.write_calls()
        self.assertEqual(len(write_calls), 4, write_calls)
        self.assertFalse(any('"type": "candidate"' in call for call in write_calls))

    def test_talent_pool_preview_dedupes_ids(self) -> None:
        result = self.run_script(
            "talent-pool-candidate-delete",
            "--ids", "101,101,102",
            "--workdir", str(self.root / "talent-dedupe"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would remove 2 candidate(s)", result.stdout)
        self.assert_no_write_calls()

    def test_job_delete_preview_does_not_touch_live_report_or_log(self) -> None:
        workdir = self.root / "job-preview-artifacts"
        workdir.mkdir()
        live_report = workdir / "report.xlsx"
        live_log = workdir / "delete.log"
        live_report.write_text("live-report", encoding="utf-8")
        live_log.write_text("live-log", encoding="utf-8")

        result = self.run_script(
            "job-delete",
            "--job-id", "1caca481-a244-4bab-a13c-719b7b52f399",
            "--workdir", str(workdir),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(live_report.read_text(encoding="utf-8"), "live-report")
        self.assertEqual(live_log.read_text(encoding="utf-8"), "live-log")
        self.assertTrue((workdir / "preview.log").exists())

    def test_protection_create_rejects_legacy_org_id(self) -> None:
        result = self.run_script(
            "protection-period-create",
            *self.base_commands()["protection-period-create"],
            "--org-id", "org-wrong",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--org-id is no longer supported", result.stderr + result.stdout)
        self.assert_no_write_calls()

    def test_reorder_rejects_profile_override_even_with_local_map(self) -> None:
        self.env["CLLMK_PROFILE"] = "other-profile"
        try:
            result = self.run_script(
                "protection-period-reorder",
                *self.base_commands()["protection-period-reorder"],
            )
        finally:
            self.env["CLLMK_PROFILE"] = ""
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLLMK_PROFILE is set", result.stderr + result.stdout)
        self.assert_no_write_calls()


if __name__ == "__main__":
    unittest.main()
