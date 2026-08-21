"""Bulk-remove candidates from a Moka ATS talent pool via cllmk curl.

Reads candidate IDs from xlsx/csv or --ids flag, batches them, calls
POST /api/outer/ats-candidate/talent-pool-candidates/bulk/delete,
classifies failures without retrying result-unknown network errors, and
runs a "rescue" pass over BIZ_NOT_IN_POOL batches at 1 ID/call to
recover collateral misfires from the server's all-or-nothing batch
semantics.

⚠️ 中文安全提示（必读）：
  · 本脚本默认**只预览（dry-run）**，不会真正从人才库删除任何候选人。
  · 只有同时提供 --confirm 与 --expected-org-id <orgId>，且该 orgId 与实时
    `cllmk auth status` 返回的 current orgId 完全一致时，才会执行移除。
  · rescue 模式从上一轮 skip.log 读 ID，必须在与原工作目录相同租户下复跑。
  · 失败不自动重试；结果未知时必须先回读人才库，避免重复删除。

Usage:
  python3 bulk_remove.py --input <xlsx|csv> [--id-column <name|index>]
                        [--workdir <dir>] [--batch-size 30] [--interval 2.0]
                        [--no-rescue-biz]
  python3 bulk_remove.py --ids 1,2,3 [--workdir <dir>]
  python3 bulk_remove.py --rescue --workdir <dir-with-existing-logs>

Writes require --confirm --expected-org-id <orgId>. Without --confirm the
script only previews and never calls the delete endpoint.

Resume: re-running with the same --workdir picks up from state.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

URL = "/api/outer/ats-candidate/talent-pool-candidates/bulk/delete"
ORG_INFO_URL = "/api/v2/org/info"
NETWORK_FAIL_PATTERN = re.compile(r"Client network socket disconnected|ECONNRESET|ETIMEDOUT|socket hang up", re.I)
BIZ_LINE_PATTERN = re.compile(r"BIZ_NOT_IN_POOL ids=\[([^\]]+)\]")
LEGACY_FAIL_BIZ_PATTERN = re.compile(r"FAIL ids=\[([^\]]+)\].*不在人才库")


def require_current_tenant() -> None:
    if os.environ.get("CLLMK_PROFILE", "").strip():
        sys.exit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                 "verify with 'cllmk auth status', then retry")


def load_ids_from_file(path: Path, id_column) -> list[int]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
        except ImportError:
            sys.exit("error: openpyxl required to read xlsx. pip install openpyxl")
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    elif path.suffix.lower() == ".csv":
        with path.open(newline="") as f:
            rows = list(csv.reader(f))
    else:
        sys.exit(f"error: unsupported input format {path.suffix}")

    if not rows:
        sys.exit("error: input file is empty")

    header = rows[0]
    if isinstance(id_column, str) and not id_column.isdigit():
        try:
            col_idx = list(header).index(id_column)
        except ValueError:
            sys.exit(f"error: column '{id_column}' not found in header {header}")
        data_rows = rows[1:]
    else:
        col_idx = int(id_column) if id_column is not None else 0
        first_val = rows[0][col_idx] if col_idx < len(rows[0]) else None
        looks_like_header = first_val is not None and not str(first_val).strip().lstrip("-").isdigit()
        data_rows = rows[1:] if looks_like_header else rows

    ids = []
    seen: set[int] = set()
    for row in data_rows:
        if col_idx >= len(row):
            continue
        v = row[col_idx]
        if v is None or str(v).strip() == "":
            continue
        try:
            candidate_id = int(str(v).strip())
        except ValueError:
            continue
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        ids.append(candidate_id)
    return ids


def dedupe_ids(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def fetch_org_id() -> str:
    """Return current cllmk session's orgId. Removal is org-scoped, so an
    undeterminable org aborts instead of proceeding."""
    require_current_tenant()
    proc = subprocess.run(
        ["cllmk", "curl", "--url", ORG_INFO_URL, "--method", "GET"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        sys.exit(f"error: cllmk curl org/info failed rc={proc.returncode} "
                 f"err={proc.stderr.strip()[:200]} out={proc.stdout.strip()[:200]}")
    try:
        resp = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"error: org/info returned non-JSON: {proc.stdout.strip()[:200]}")
    if resp.get("code") != 0:
        sys.exit(f"error: org/info code={resp.get('code')} msg={resp.get('msg')}")
    data = resp.get("data") or {}
    org_id = (data.get("orgInfo") or {}).get("orgId")
    if not org_id:
        sys.exit("error: org/info response has no orgInfo.orgId; refuse to delete "
                 "without knowing the target org")
    return str(org_id)


def require_expected_org(org_id: str, expected_org_id: str | None) -> None:
    if not expected_org_id:
        sys.exit("error: --expected-org-id is required with --confirm")
    if org_id != expected_org_id:
        sys.exit(f"error: current cllmk orgId={org_id} does not match "
                 f"--expected-org-id={expected_org_id}; refuse to remove candidates")


def check_state_org(state_path: Path, org_id: str, hint: str):
    """Refuse to touch a workdir whose state.json belongs to another org."""
    if not state_path.exists():
        return
    try:
        st = json.loads(state_path.read_text())
    except Exception:
        return
    if st.get("orgId") and st["orgId"] != org_id:
        sys.exit(f"error: state.json orgId={st['orgId']} but current cllmk org={org_id}; "
                 f"{hint}")


def call_delete(ids: list[int]) -> tuple[int, str, str]:
    require_current_tenant()
    payload = json.dumps({"candidateIds": ids})
    proc = subprocess.run(
        ["cllmk", "curl", "--method", "POST", "--url", URL, "--payload", payload],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def classify(rc: int, out: str, err: str) -> tuple[str, str]:
    """Return (status, msg). status in {OK, NETWORK_FAIL, BIZ_NOT_IN_POOL, OTHER_FAIL}."""
    if rc != 0:
        combined = (err or "") + "\n" + (out or "")
        if NETWORK_FAIL_PATTERN.search(combined):
            return "NETWORK_FAIL", combined[:300]
        return "OTHER_FAIL", (err or out)[:300]

    if not out:
        return "OTHER_FAIL", "empty response"

    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        return "OTHER_FAIL", out[:300]

    inner = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    inner_msg = (inner.get("msg") if inner else None) or resp.get("msg") or ""

    if resp.get("code") == 0 and inner and inner.get("success") is True:
        return "OK", inner_msg

    if NETWORK_FAIL_PATTERN.search(json.dumps(resp, ensure_ascii=False)):
        return "NETWORK_FAIL", inner_msg or resp.get("msg", "")[:300]

    if "不在人才库" in inner_msg or "不在人才库" in resp.get("msg", ""):
        return "BIZ_NOT_IN_POOL", inner_msg

    return "OTHER_FAIL", inner_msg or resp.get("msg", "")[:300]


def make_logger(log_path: Path):
    def log(msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")
    return log


def run_pass(batches: list[list[int]], log_path: Path, state_path: Path | None,
             interval: float, label: str, org_id: str = "") -> dict:
    log = make_logger(log_path)
    log(f"{label} START batches={len(batches)} interval={interval}s")

    start_idx = 0
    if state_path and state_path.exists():
        try:
            st = json.loads(state_path.read_text())
            if st.get("label") == label:
                start_idx = st.get("next_batch", 0)
                log(f"{label} RESUME from batch {start_idx}")
        except Exception:
            pass

    counts = {"OK": 0, "NETWORK_FAIL": 0, "BIZ_NOT_IN_POOL": 0, "OTHER_FAIL": 0}
    for bi in range(start_idx, len(batches)):
        b = batches[bi]
        try:
            rc, out, err = call_delete(b)
            status, msg = classify(rc, out, err)
        except Exception as e:
            status, msg = "NETWORK_FAIL", f"EXC {e}"
            rc = -1

        counts[status] += 1
        if status == "OK":
            log(f"{label} {bi+1}/{len(batches)} OK ids={b[0]}..{b[-1]} count={len(b)}")
        else:
            log(f"{label} {bi+1}/{len(batches)} {status} ids={b} rc={rc} msg={msg}")

        if state_path:
            state_path.write_text(json.dumps({"label": label, "next_batch": bi + 1,
                                              "orgId": org_id}))

        if bi < len(batches) - 1:
            time.sleep(interval)

    log(f"{label} DONE " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def collect_biz_ids(workdir: Path) -> list[int]:
    """Scan all *.log under workdir (recursive) for BIZ_NOT_IN_POOL or legacy FAIL+不在人才库 batches."""
    seen = set()
    ordered = []
    for log_path in sorted(workdir.rglob("*.log")):
        for line in log_path.read_text().splitlines():
            m = BIZ_LINE_PATTERN.search(line) or LEGACY_FAIL_BIZ_PATTERN.search(line)
            if not m:
                continue
            for x in m.group(1).split(","):
                x = x.strip()
                if not x.lstrip("-").isdigit():
                    continue
                n = int(x)
                if n in seen:
                    continue
                seen.add(n)
                ordered.append(n)
    return ordered


def run_rescue(ids: list[int], workdir: Path, interval: float) -> dict:
    """Single-ID rescue pass for collateral BIZ_NOT_IN_POOL misfires."""
    log = make_logger(workdir / "rescue.log")
    log(f"RESCUE START total={len(ids)} interval={interval}s")
    counts = {"RECOVERED": 0, "TRULY_NOT_IN_POOL": 0, "NETWORK_FAIL": 0, "OTHER_FAIL": 0}
    net_failed: list[int] = []
    for i, cid in enumerate(ids):
        try:
            rc, out, err = call_delete([cid])
            status, msg = classify(rc, out, err)
        except Exception as e:
            status, msg = "NETWORK_FAIL", f"EXC {e}"

        if status == "OK":
            counts["RECOVERED"] += 1
        elif status == "BIZ_NOT_IN_POOL":
            counts["TRULY_NOT_IN_POOL"] += 1
        elif status == "NETWORK_FAIL":
            counts["NETWORK_FAIL"] += 1
            net_failed.append(cid)
        else:
            counts["OTHER_FAIL"] += 1

        # log non-RECOVERED + periodic checkpoint
        if status != "OK" or (i + 1) % 100 == 0:
            log(f"RESCUE {i+1}/{len(ids)} id={cid} {status} msg={msg[:80]}")
        if i < len(ids) - 1:
            time.sleep(interval)

    log("RESCUE DONE " + " ".join(f"{k}={v}" for k, v in counts.items()))

    if net_failed:
        log("RESCUE_NETWORK_FAIL results are unknown and were not retried; verify pool "
            "membership before any manual retry")
    return counts


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="xlsx or csv file with candidate IDs")
    src.add_argument("--ids", type=str, help="comma-separated candidate IDs")
    src.add_argument("--rescue", action="store_true",
                     help="rescue-only mode: rescan BIZ_NOT_IN_POOL batches from logs at 1 ID/call")
    ap.add_argument("--id-column", default=None,
                    help="column name or 0-based index (default: first column)")
    ap.add_argument("--workdir", type=Path, default=None,
                    help="output directory (default: input file's parent dir)")
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--rescue-interval", type=float, default=1.0,
                    help="inter-call delay for single-ID rescue pass (default: 1.0s)")
    ap.add_argument("--no-rescue-biz", action="store_true",
                    help="skip the automatic rescue pass over BIZ_NOT_IN_POOL batches")
    ap.add_argument("--confirm", action="store_true",
                    help="allow irreversible writes; without this flag the script only previews")
    ap.add_argument("--expected-org-id",
                    help="required with --confirm; must exactly match the live current orgId")
    args = ap.parse_args()

    # Rescue-only mode: don't run main delete, just scan existing logs and rescue
    if args.rescue:
        if not args.workdir:
            sys.exit("error: --workdir required for --rescue")
        workdir = args.workdir
        if not workdir.exists():
            sys.exit(f"error: workdir {workdir} does not exist")
        ids = collect_biz_ids(workdir)
        if not ids:
            print("no BIZ_NOT_IN_POOL entries found in logs; nothing to rescue")
            return
        if not args.confirm:
            print(f"[preview] would rescue-scan {len(ids)} candidate(s); no API called")
            print("[preview] rerun with --confirm --expected-org-id <orgId>")
            return
        org_id = fetch_org_id()
        require_expected_org(org_id, args.expected_org_id)
        check_state_org(workdir / "state.json", org_id,
                        "run cllmk auth switch and verify current before --rescue")
        print(f"org={org_id} (tenant_source=current)")
        print(f"rescue: {len(ids)} unique IDs from {workdir}/*.log; "
              f"est. {len(ids) * (args.rescue_interval + 1.0):.0f}s")
        run_rescue(ids, workdir, args.rescue_interval)
        return

    # Normal delete mode
    if args.input:
        ids = load_ids_from_file(args.input, args.id_column)
        workdir = args.workdir or args.input.parent
    else:
        ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
        if not args.workdir:
            sys.exit("error: --workdir required when using --ids")
        workdir = args.workdir

    original_count = len(ids)
    ids = dedupe_ids(ids)
    if len(ids) != original_count:
        print(f"note: deduped {original_count} -> {len(ids)} candidate IDs")

    workdir.mkdir(parents=True, exist_ok=True)
    if not ids:
        sys.exit("error: no candidate IDs found")

    if not args.confirm:
        batches = [ids[i:i + args.batch_size] for i in range(0, len(ids), args.batch_size)]
        print(f"[preview] would remove {len(ids)} candidate(s) in {len(batches)} batch(es)")
        print("[preview] no API called; rerun with --confirm --expected-org-id <orgId>")
        return

    org_id = fetch_org_id()
    require_expected_org(org_id, args.expected_org_id)
    check_state_org(workdir / "state.json", org_id,
                    f"delete {workdir / 'state.json'} or run cllmk auth switch and verify current before rerunning")
    print(f"org={org_id} (tenant_source=current)")

    batches = [ids[i:i + args.batch_size] for i in range(0, len(ids), args.batch_size)]
    print(f"Loaded {len(ids)} IDs → {len(batches)} batches × {args.batch_size}; "
          f"est. {len(batches) * (args.interval + 1.3):.0f}s")

    delete_log = workdir / "delete.log"
    state_path = workdir / "state.json"

    main_counts = run_pass(batches, delete_log, state_path, args.interval, "BATCH", org_id)

    if main_counts["NETWORK_FAIL"] > 0:
        print("NETWORK_FAIL batches were not retried because removal may already have reached "
              "the server; verify pool membership before any manual retry")

    # Default: auto-rescue BIZ_NOT_IN_POOL batches
    if not args.no_rescue_biz:
        biz_ids = collect_biz_ids(workdir)
        if biz_ids:
            print(f"auto-rescue: {len(biz_ids)} unique IDs from BIZ_NOT_IN_POOL batches; "
                  f"est. {len(biz_ids) * (args.rescue_interval + 1.0):.0f}s")
            run_rescue(biz_ids, workdir, args.rescue_interval)


if __name__ == "__main__":
    main()
