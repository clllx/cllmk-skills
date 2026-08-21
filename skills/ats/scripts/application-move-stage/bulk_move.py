"""Bulk-move Moka ATS applications between pipeline stages via cllmk curl.

Reads (applicationId, fromStage, toStage) triples from xlsx/csv, resolves stage
names → IDs via /api/v2/org/info, then calls
PUT /api/outer/ats-pipeline/stage/application/move-stage/v2 one row at a time
(the endpoint has no bulk variant). Classifies failures without retrying
result-unknown network errors, and supports resume-from-crash via state.json.

⚠️ 中文安全提示（必读）：
  · 本脚本默认**只预览（dry-run）**，不会真正移动任何应聘阶段。
  · 只有同时提供 --confirm 与 --expected-org-id <orgId>，且该 orgId 与实时
    `cllmk auth status` 返回的 current orgId 完全一致时，才会执行移动。
  · stageId 是**租户级**标识，不同 org 的同名 stage 的 stageId 完全不同；
    执行前必须先把 `data.orgId` / `data.env` 明示给用户对齐。
  · 失败不自动重试；结果未知时必须先回读应聘当前阶段，避免重复移动。

Usage:
  python3 bulk_move.py --input <xlsx|csv>
                       [--app-col <name|idx>] [--from-col <name|idx>] [--to-col <name|idx>]
                       [--workdir <dir>] [--interval 1.0]
                       [--dry-run] [--confirm --expected-org-id <orgId>]

Resume: re-running with the same --workdir picks up from state.json.
Different-org guard: state.json records orgId; refuses to resume across orgs.
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

MOVE_URL = "/api/outer/ats-pipeline/stage/application/move-stage/v2"
ORG_INFO_URL = "/api/v2/org/info"

NETWORK_FAIL_PATTERN = re.compile(
    r"Client network socket disconnected|ECONNRESET|ETIMEDOUT|socket hang up|EAI_AGAIN",
    re.I,
)
AUTH_FAIL_PATTERN = re.compile(r"HTTP 401|HTTP 403|Not logged in|Session expired", re.I)


# ---------- cllmk helpers ----------

def cllmk_curl(url: str, method: str, payload: dict | None = None, timeout: int = 60):
    if os.environ.get("CLLMK_PROFILE", "").strip():
        sys.exit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                 "verify with 'cllmk auth status', then retry")
    args = ["cllmk", "curl", "--url", url, "--method", method]
    if payload is not None:
        args += ["--payload", json.dumps(payload)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def fetch_org_context() -> tuple[str, dict[str, int]]:
    """Return (orgId, {stageName: stageId}). Only enabled stages are included.

    stages come from /api/v2/org/info data.stages, which is org-scoped and
    flat — names are unique within an org in practice, so we build a direct
    map. If duplicates ever appear, we surface them as an error so the user
    knows to disambiguate rather than getting silent wrong routing.
    """
    rc, out, err = cllmk_curl(ORG_INFO_URL, "GET")
    if rc != 0 or not out:
        sys.exit(f"error: cllmk curl org/info failed rc={rc} err={err} out={out[:200]}")
    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        sys.exit(f"error: org/info returned non-JSON: {out[:200]}")
    if resp.get("code") != 0:
        sys.exit(f"error: org/info code={resp.get('code')} msg={resp.get('msg')}")

    data = resp.get("data") or {}
    org_id = (data.get("orgInfo") or {}).get("orgId") or (data.get("stages") or [{}])[0].get("orgId") or "unknown"
    stages = data.get("stages") or []

    name_to_ids: dict[str, list[int]] = {}
    for s in stages:
        if s.get("disabled"):
            continue
        name_to_ids.setdefault(s["name"], []).append(s["id"])

    dups = {n: ids for n, ids in name_to_ids.items() if len(ids) > 1}
    if dups:
        lines = [f"  {n!r}: ids={ids}" for n, ids in dups.items()]
        sys.exit(
            "error: duplicate stage names in org.stages (cannot disambiguate by name alone):\n"
            + "\n".join(lines)
        )

    return org_id, {n: ids[0] for n, ids in name_to_ids.items()}


def require_expected_org(org_id: str, expected_org_id: str | None) -> None:
    if not expected_org_id:
        sys.exit("error: --expected-org-id is required with --confirm")
    if org_id != expected_org_id:
        sys.exit(f"error: current cllmk orgId={org_id} does not match "
                 f"--expected-org-id={expected_org_id}; refuse to move applications")


def call_move(app_id: int, from_id: int, to_id: int) -> tuple[int, str, str]:
    return cllmk_curl(
        MOVE_URL,
        "PUT",
        {"applicationId": app_id, "currentStageId": from_id, "stageId": to_id},
    )


def classify(rc: int, out: str, err: str) -> tuple[str, str]:
    """Return (status, msg). Status ∈ {OK, NETWORK_FAIL, AUTH_FAIL, BIZ_FAIL, OTHER_FAIL}."""
    combined = f"{err}\n{out}"
    if AUTH_FAIL_PATTERN.search(combined):
        return "AUTH_FAIL", combined[:300]
    if rc != 0:
        if NETWORK_FAIL_PATTERN.search(combined):
            return "NETWORK_FAIL", combined[:300]
        return "OTHER_FAIL", (err or out)[:300]
    if not out:
        return "OTHER_FAIL", "empty response"
    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        return "OTHER_FAIL", out[:300]

    outer_code = resp.get("code")
    inner = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    inner_success = inner.get("success") if inner else None
    inner_msg = (inner.get("msg") if inner else None) or resp.get("msg") or ""

    if outer_code == 0 and inner_success is True:
        return "OK", inner_msg
    if NETWORK_FAIL_PATTERN.search(inner_msg + " " + (resp.get("msg") or "")):
        return "NETWORK_FAIL", inner_msg or resp.get("msg", "")[:300]
    if AUTH_FAIL_PATTERN.search(inner_msg + " " + (resp.get("msg") or "")):
        return "AUTH_FAIL", inner_msg or resp.get("msg", "")[:300]
    return "BIZ_FAIL", inner_msg or resp.get("msg", "")[:300]


# ---------- input parsing ----------

def _resolve_col(header: list, spec, default_idx: int) -> int:
    if spec is None:
        return default_idx
    s = str(spec)
    if s.isdigit():
        return int(s)
    try:
        return list(header).index(spec)
    except ValueError:
        sys.exit(f"error: column {spec!r} not found in header {header}")


def load_rows(path: Path, app_col, from_col, to_col) -> list[tuple[int, str, str]]:
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
        except ImportError:
            sys.exit("error: openpyxl required to read xlsx. pip install openpyxl")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        raw = list(ws.iter_rows(values_only=True))
    elif path.suffix.lower() == ".csv":
        with path.open(newline="") as f:
            raw = list(csv.reader(f))
    else:
        sys.exit(f"error: unsupported input format {path.suffix}")
    if not raw:
        sys.exit("error: input file is empty")

    header = list(raw[0])
    # Auto-detect header: if any of the first row cells is non-numeric where an id column would sit
    first_val = header[0] if header else None
    looks_like_header = first_val is not None and not str(first_val).strip().lstrip("-").isdigit()
    data_rows = raw[1:] if looks_like_header else raw

    ai = _resolve_col(header, app_col, 0) if looks_like_header else int(app_col or 0)
    fi = _resolve_col(header, from_col, 1) if looks_like_header else int(from_col or 1)
    ti = _resolve_col(header, to_col, 2) if looks_like_header else int(to_col or 2)

    out = []
    for row in data_rows:
        if max(ai, fi, ti) >= len(row):
            continue
        a, f_, t = row[ai], row[fi], row[ti]
        if a is None or str(a).strip() == "":
            continue
        try:
            a_int = int(str(a).strip())
        except ValueError:
            continue
        out.append((a_int, str(f_).strip(), str(t).strip()))
    return out


# ---------- runner ----------

def make_logger(log_path: Path):
    def log(msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")
    return log


def write_state(state_path: Path, org_id: str, label: str, next_row: int) -> None:
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "orgId": org_id,
        "label": label,
        "next_row": next_row,
    }))
    tmp.replace(state_path)


def run_pass(rows, stage_map, log_path, state_path, interval, label,
             org_id, failed_csv_path=None):
    log = make_logger(log_path)
    log(f"{label} START total={len(rows)} interval={interval}s")

    start_idx = 0
    if state_path and state_path.exists():
        try:
            st = json.loads(state_path.read_text())
            if st.get("label") == label:
                start_idx = st.get("next_row", 0)
                if start_idx:
                    log(f"{label} RESUME from row {start_idx}")
        except Exception:
            pass

    counts = {"OK": 0, "NETWORK_FAIL": 0, "BIZ_FAIL": 0, "AUTH_FAIL": 0, "OTHER_FAIL": 0}
    failed_writer = None
    failed_fh = None
    if failed_csv_path:
        already = failed_csv_path.exists()
        failed_fh = failed_csv_path.open("a", newline="")
        failed_writer = csv.writer(failed_fh)
        if not already:
            failed_writer.writerow(["applicationId", "fromStage", "toStage", "status", "msg"])

    aborted = False
    for i in range(start_idx, len(rows)):
        app_id, from_name, to_name = rows[i]
        from_id = stage_map.get(from_name)
        to_id = stage_map.get(to_name)
        if from_id is None or to_id is None:
            counts["OTHER_FAIL"] += 1
            miss = [n for n, v in [("from", from_id), ("to", to_id)] if v is None]
            msg = f"unknown stage name: {miss} row=({from_name!r} -> {to_name!r})"
            log(f"{label} {i+1}/{len(rows)} OTHER_FAIL app={app_id} {msg}")
            if failed_writer:
                failed_writer.writerow([app_id, from_name, to_name, "OTHER_FAIL", msg])
                failed_fh.flush()
            if state_path:
                write_state(state_path, org_id, label, i + 1)
            continue

        try:
            rc, out, err = call_move(app_id, from_id, to_id)
            status, msg = classify(rc, out, err)
        except subprocess.TimeoutExpired:
            status, msg = "NETWORK_FAIL", "timeout"
        except Exception as e:
            status, msg = "OTHER_FAIL", f"EXC {e}"

        counts[status] += 1
        if status == "OK":
            log(f"{label} {i+1}/{len(rows)} OK app={app_id} {from_name!r}->{to_name!r}")
        else:
            log(f"{label} {i+1}/{len(rows)} {status} app={app_id} "
                f"{from_name!r}->{to_name!r} msg={msg[:200]}")
            if failed_writer:
                failed_writer.writerow([app_id, from_name, to_name, status, msg])
                failed_fh.flush()

        if state_path:
            write_state(state_path, org_id, label, i + 1)

        if status == "AUTH_FAIL":
            log(f"{label} ABORT auth failure at row {i+1}: {msg[:200]}")
            aborted = True
            break

        if i < len(rows) - 1:
            time.sleep(interval)

    if failed_fh:
        failed_fh.close()

    log(f"{label} {'ABORTED' if aborted else 'DONE'} " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return counts, aborted


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True, help="xlsx or csv file")
    ap.add_argument("--app-col", default=None, help="applicationId column (name or 0-based idx, default: col 0)")
    ap.add_argument("--from-col", default=None, help="fromStage column (default: col 1)")
    ap.add_argument("--to-col", default=None, help="toStage column (default: col 2)")
    ap.add_argument("--workdir", type=Path, default=None,
                    help="output dir (default: input file's parent)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between calls (default 1.0)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch stage map, resolve every row, print summary, but call no API")
    ap.add_argument("--confirm", action="store_true",
                    help="allow writes; without this flag the script only previews")
    ap.add_argument("--expected-org-id",
                    help="required with --confirm; must exactly match the live current orgId")
    args = ap.parse_args()

    workdir = args.workdir or args.input.parent
    workdir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args.input, args.app_col, args.from_col, args.to_col)
    if not rows:
        sys.exit("error: no valid rows parsed from input")

    org_id, stage_map = fetch_org_context()
    print(f"org={org_id}, stages={len(stage_map)}, rows={len(rows)}")

    # Pre-validate stage names
    ref_names = set()
    for _, f_, t in rows:
        ref_names.update([f_, t])
    unknown = sorted(n for n in ref_names if n not in stage_map)
    if unknown:
        print(f"[warn] {len(unknown)} stage name(s) in input NOT found in org.stages:")
        for n in unknown[:20]:
            print(f"  - {n!r}")
        if len(unknown) > 20:
            print(f"  ... and {len(unknown) - 20} more")
        print(f"[hint] available stages: {sorted(stage_map)}")

    # State guard: refuse to resume across a different org
    state_path = workdir / "state.json"
    saved_state = None
    if state_path.exists():
        try:
            saved_state = json.loads(state_path.read_text())
            if saved_state.get("orgId") and saved_state["orgId"] != org_id:
                sys.exit(
                    f"error: state.json orgId={saved_state['orgId']} but current cllmk org={org_id}; "
                    f"delete {state_path} or run cllmk auth switch and verify current before rerunning"
                )
        except json.JSONDecodeError:
            if args.confirm and not args.dry_run:
                sys.exit(f"error: invalid {state_path}; refuse to resume live writes")

    if args.dry_run or not args.confirm:
        print(f"[dry-run] would move {len(rows) - len(unknown)} rows, "
              f"skip {len(unknown)} unknown-stage row(s)")
        print("[preview] no API called; rerun with --confirm --expected-org-id <orgId>")
        return

    require_expected_org(org_id, args.expected_org_id)

    if saved_state:
        if not saved_state.get("orgId"):
            sys.exit(f"error: {state_path} has no orgId; cannot safely resume. "
                     "Move it aside after verifying the original tenant, then rerun")
        if saved_state.get("label") != "MOVE":
            sys.exit(f"error: {state_path} label={saved_state.get('label')!r}; "
                     "refuse to reuse it for MOVE")
    else:
        write_state(state_path, org_id, "MOVE", 0)

    move_log = workdir / "move.log"
    failed_csv = workdir / "failed.csv"
    counts, aborted = run_pass(rows, stage_map, move_log, state_path, args.interval,
                               "MOVE", org_id, failed_csv)

    if aborted:
        return

    if counts["NETWORK_FAIL"] > 0:
        print("NETWORK_FAIL rows were not retried because a move may already have reached the "
              "server; query current stages before any manual retry")


if __name__ == "__main__":
    main()
