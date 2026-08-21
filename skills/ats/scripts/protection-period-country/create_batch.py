#!/usr/bin/env python3
from __future__ import annotations

"""
批量创建 Moka ATS 渠道保护期规则（国家维度）。

用法：
  python3 create_batch.py \
    --content-file content.json \
    --countries countries.txt \
    [--confirm --expected-org-id <orgId>] \
    [--skip 马来西亚,捷克] \
    [--delay 0.4] \
    [--start-from 印度] \
    [--log result.log]

文件格式：
  content.json — 保护期 content 对象（仅 content 字段内容，不要外层包裹）
  countries.txt — 一行一个国家名；或 JSON 数组也接受

content.json 示例（**数值由用户提供，本脚本不做默认**）：
  {
    "headhunterLockProtect": true,
    "headhunterProtectTime": 365,
    ...
  }
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

CREATE_URL = "/api/outer/ats-jc/channel/protectionPeriod/create"
ORG_INFO_URL = "/api/v2/org/info"


def build_rule_condition_data(name: str, org_id: str) -> dict:
    return {
        "orgId": org_id,
        "bus": "ATS",
        "businessType": "protectionPeriod",
        "contextParam": {"buId": 0, "hireMode": 1},
        "templateType": 1,
        "rule": {
            "uniqueKey": str(uuid.uuid4()),
            "label": "ruleFamily",
            "rules": [{
                "uniqueKey": str(uuid.uuid4()),
                "label": "ruleGroup",
                "logic": "and",
                "rules": [{
                    "uniqueKey": str(uuid.uuid4()),
                    "label": "rule",
                    "name": f"【职位 / 国家/地区】 包含任意【{name}】 ",
                    "features": [{
                        "isCommon": True,
                        "id": 100004000,
                        "name": "job",
                        "title": "职位 / 国家/地区",
                        "type": 6,
                        "featureConditions": [],
                        "child": {
                            "id": 100000034,
                            "name": "countryRegion",
                            "operators": ["IS_NULL", "NOT_NULL", "INCLUDE_ANY", "NOT_INCLUDE_ANY"],
                            "title": "国家/地区",
                            "type": 6,
                            "featureConditions": [],
                            "child": None,
                        },
                        "value": {
                            "option": [{
                                "id": 100000034,
                                "name": "countryRegion",
                                "operators": ["IS_NULL", "NOT_NULL", "INCLUDE_ANY", "NOT_INCLUDE_ANY"],
                                "title": "国家/地区",
                                "type": 6,
                                "value": "job.countryRegion",
                                "label": "国家/地区",
                                "defFeatureId": 100000034,
                                "children": [],
                            }],
                            "conditions": {},
                        },
                    }],
                    "value": {"data": [name], "title": name},
                    "operator": "INCLUDE_ANY",
                }],
            }],
        },
    }


def build_payload(name: str, org_id: str, content: dict) -> dict:
    return {
        "name": name,
        "ruleConditionData": json.dumps(
            build_rule_condition_data(name, org_id), ensure_ascii=False
        ),
        "content": content,
    }


def call(name: str, org_id: str, content: dict):
    if os.environ.get("CLLMK_PROFILE", "").strip():
        raise SystemExit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                         "verify with 'cllmk auth status', then retry")
    payload = json.dumps(build_payload(name, org_id, content), ensure_ascii=False)
    r = subprocess.run(
        ["cllmk", "curl", "--url", CREATE_URL, "--method", "POST", "--payload", payload],
        capture_output=True, text=True,
    )
    return r.stdout, r.stderr, r.returncode


def fetch_org_id() -> str:
    if os.environ.get("CLLMK_PROFILE", "").strip():
        raise SystemExit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                         "verify with 'cllmk auth status', then retry")
    r = subprocess.run(
        ["cllmk", "curl", "--url", ORG_INFO_URL, "--method", "GET", "--filter", "orgInfo"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise SystemExit(f"error: org/info failed: {r.stdout.strip()[:200]} {r.stderr.strip()[:200]}")
    try:
        outer = json.loads(r.stdout)
        org_id = ((outer.get("data") or {}).get("orgInfo") or {}).get("orgId")
    except Exception as exc:
        raise SystemExit(f"error: invalid org/info response: {exc}")
    if not org_id:
        raise SystemExit("error: current orgId unavailable; refuse to create rules")
    return str(org_id)


def require_expected_org(org_id: str, expected_org_id: str | None) -> None:
    if not expected_org_id:
        raise SystemExit("error: --expected-org-id is required with --confirm")
    if org_id != expected_org_id:
        raise SystemExit(f"error: current cllmk orgId={org_id} does not match "
                         f"--expected-org-id={expected_org_id}; refuse to create rules")


def load_countries(path: Path) -> list:
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("["):
        data = json.loads(text)
        return [x if isinstance(x, str) else x["name"] for x in data]
    return [line.strip() for line in text.splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content-file", required=True, help="保护期 content 字段 JSON 文件")
    ap.add_argument("--countries", required=True, help="要创建的国家名列表（文本或 JSON 数组）")
    ap.add_argument("--org-id", help=argparse.SUPPRESS)
    ap.add_argument("--confirm", action="store_true",
                    help="允许创建；未提供时只预览，不调用 API")
    ap.add_argument("--expected-org-id",
                    help="与 --confirm 同时提供，必须与实时 current orgId 完全一致")
    ap.add_argument("--skip", default="", help="逗号分隔的跳过国家名")
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--start-from", help="从该国家开始（含）")
    ap.add_argument("--log", default="result.log")
    args = ap.parse_args()

    if args.org_id is not None:
        raise SystemExit("error: --org-id is no longer supported and is never a tenant selector; "
                         "use current plus --confirm --expected-org-id <orgId>")

    content = json.loads(Path(args.content_file).read_text(encoding="utf-8"))
    countries = load_countries(Path(args.countries))
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    log_path = Path(args.log)

    pending = [name for name in countries if name not in skip]
    if not args.confirm:
        print(f"[preview] would create {len(pending)} protection-period rule(s)")
        for name in pending[:20]:
            print(f"  - {name}")
        if len(pending) > 20:
            print(f"  ... and {len(pending) - 20} more")
        print("[preview] no API called; rerun with --confirm --expected-org-id <orgId>")
        return

    current_org_id = fetch_org_id()
    require_expected_org(current_org_id, args.expected_org_id)

    started = args.start_from is None
    ok = bad = skipped = 0
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n===== run at {time.strftime('%Y-%m-%d %H:%M:%S')} org={current_org_id} =====\n")
        for name in countries:
            if not started:
                if name == args.start_from:
                    started = True
                else:
                    continue
            if name in skip:
                f.write(f"SKIP\t{name}\n")
                skipped += 1
                continue
            out, err, rc = call(name, current_org_id, content)
            try:
                response = json.loads(out)
                inner = response.get("data") if isinstance(response.get("data"), dict) else {}
                success = response.get("code") == 0 and inner.get("success") is True
            except Exception:
                success = False
            status = "OK" if success else "FAIL"
            line = f"{status}\t{name}\t{out.strip()}"
            if err:
                line += f"\tSTDERR={err.strip()}"
            f.write(line + "\n")
            f.flush()
            print(f"[{ok+bad+1}] {status} {name}: {out.strip()[:160]}")
            if success:
                ok += 1
            else:
                bad += 1
            time.sleep(args.delay)
    print(f"DONE ok={ok} fail={bad} skip={skipped}")


if __name__ == "__main__":
    main()
