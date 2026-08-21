"""Delete Moka ATS applications or candidates via cllmk curl.

Reads applicationIds from xlsx/csv or --ids, batches them, calls
  - PUT  /api/outer/ats-candidate/application/delete            (single, when N==1 or --no-bulk)
  - POST /api/outer/ats-candidate/application/bulk/delete       (batched)

--type is required (application | candidate); no default, refuses to run without it.
refuseMail.send is hardcoded false and cannot be overridden via CLI.

⚠️ 中文安全提示（必读）：
  · 本脚本默认**只预览（dry-run）**，不会真正删除任何数据。
  · 只有同时提供 --confirm 与 --expected-org-id <orgId>，且该 orgId 与实时
    `cllmk auth status` 返回的 current orgId 完全一致时，才会执行删除。
  · 删除不可逆；refuseMail.send 硬编码为 false，本通道绝不发送拒信。
  · 写在脚本里的所有「客户默认」都不存在；任何参数都必须来自用户 / 业务文档。

Usage:
  python3 bulk_delete.py --type application --ids 810211925
  python3 bulk_delete.py --type application --input <xlsx|csv> [--id-column A]
  python3 bulk_delete.py --type candidate  --input <xlsx|csv>
  python3 bulk_delete.py --rescue --workdir <dir-with-existing-logs>
  python3 bulk_delete.py --type application --ids 1,2,3 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SINGLE_URL = "/api/outer/ats-candidate/application/delete"
BULK_URL = "/api/outer/ats-candidate/application/bulk/delete"
ORG_INFO_URL = "/api/v2/org/info"

# Hardcoded: this skill NEVER sends refuse mails.
# Do not accept overrides. Do not add a CLI flag.
_REFUSE_MAIL_OFF = {
    "contentList": [],
    "delayTime": 0,
    "send": False,
    "checkApplication": False,
    "whatsAppTemplateId": "",
}

NETWORK_FAIL_PATTERN = re.compile(
    r"Client network socket disconnected|ECONNRESET|ETIMEDOUT|socket hang up", re.I
)
UNIQUE_APP_PATTERN = re.compile(r"不能删除候选人唯一的申请|400059")


def require_current_tenant() -> None:
    if os.environ.get("CLLMK_PROFILE", "").strip():
        sys.exit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                 "verify with 'cllmk auth status', then retry")


def build_single_payload(app_id: int, type_: str) -> dict:
    return {
        "type": type_,
        "applicationId": app_id,
        "refuseMail": dict(_REFUSE_MAIL_OFF),
    }


def build_bulk_payload(app_ids: list[int], type_: str) -> dict:
    return {
        "applicationIdList": list(app_ids),
        "type": type_,
        "refuseMail": dict(_REFUSE_MAIL_OFF),
    }


def load_ids_from_file(path: Path, id_column) -> list[int]:
    """Load applicationIds from xlsx/csv. Ignores blanks and non-numeric cells."""
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

    ids: list[int] = []
    seen: set[int] = set()
    for row in data_rows:
        if col_idx >= len(row):
            continue
        v = row[col_idx]
        if v is None or str(v).strip() == "":
            continue
        try:
            n = int(str(v).strip())
        except ValueError:
            continue
        if n in seen:
            continue
        seen.add(n)
        ids.append(n)
    return ids


def parse_ids_csv(s: str) -> list[int]:
    """Parse '1,2,3' -> [1,2,3]; dedupes preserving first occurrence."""
    seen: set[int] = set()
    out: list[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            continue
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def compute_input_hash(*, input_path: Path | None, ids: list[int]) -> str:
    """Hash used to detect input drift on resume."""
    h = hashlib.sha1()
    if input_path is not None:
        h.update(input_path.read_bytes())
    else:
        h.update(",".join(str(i) for i in sorted(ids)).encode())
    return h.hexdigest()


def fetch_org_id() -> str:
    """Return current cllmk session's orgId. Deletion is org-scoped and
    irreversible, so an undeterminable org aborts instead of proceeding."""
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
                 f"--expected-org-id={expected_org_id}; refuse to delete")


def call_single(app_id: int, type_: str) -> tuple[int, str, str]:
    require_current_tenant()
    payload = json.dumps(build_single_payload(app_id, type_), ensure_ascii=False)
    proc = subprocess.run(
        ["cllmk", "curl", "--method", "PUT", "--url", SINGLE_URL, "--payload", payload],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def call_bulk(app_ids: list[int], type_: str) -> tuple[int, str, str]:
    require_current_tenant()
    payload = json.dumps(build_bulk_payload(app_ids, type_), ensure_ascii=False)
    proc = subprocess.run(
        ["cllmk", "curl", "--method", "POST", "--url", BULK_URL, "--payload", payload],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def classify(rc: int, out: str, err: str) -> tuple[str, str]:
    """Return (status, msg). status in {OK, NETWORK_FAIL, UNIQUE_APPLICATION, BIZ_FAIL}."""
    if rc != 0:
        combined = (err or "") + "\n" + (out or "")
        if NETWORK_FAIL_PATTERN.search(combined):
            return "NETWORK_FAIL", combined[:300]
        if UNIQUE_APP_PATTERN.search(combined):
            return "UNIQUE_APPLICATION", combined[:300]
        return "BIZ_FAIL", (err or out)[:300]

    if not out:
        return "BIZ_FAIL", "empty response"

    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        return "BIZ_FAIL", out[:300]

    inner = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    inner_msg = (inner.get("msg") if inner else None) or resp.get("msg") or ""
    resp_dump = json.dumps(resp, ensure_ascii=False)

    if resp.get("code") == 0 and inner and inner.get("success") is True:
        return "OK", inner_msg

    if NETWORK_FAIL_PATTERN.search(resp_dump):
        return "NETWORK_FAIL", inner_msg[:300]

    if UNIQUE_APP_PATTERN.search(resp_dump):
        return "UNIQUE_APPLICATION", inner_msg[:300] or resp.get("msg", "")[:300]

    return "BIZ_FAIL", inner_msg[:300] or resp.get("msg", "")[:300]


def make_logger(log_path: Path):
    def log(msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        with log_path.open("a") as f:
            f.write(line + "\n")
    return log


def write_state(state_path: Path, next_batch: int, type_: str, input_hash: str,
                org_id: str):
    """Atomic state write."""
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "next_batch": next_batch,
        "type": type_,
        "input_hash": input_hash,
        "orgId": org_id,
    }))
    tmp.replace(state_path)


def load_state(state_path: Path) -> dict | None:
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text())
    except json.JSONDecodeError:
        return None


def log_jsonl(log_path: Path, record: dict):
    """Append one jsonl record."""
    record.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    with log_path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def rescan_bulk_unique_applications(app_ids: list[int], batch_no: int,
                                    delete_log: Path, interval: float,
                                    log) -> tuple[dict, list[int]]:
    """Identify the actual 400059 IDs without widening deletion to candidates.

    Successful single calls complete the originally authorized application deletion.
    Network failures remain result-unknown and are never added to the escalation pool.
    """
    counts = {"OK": 0, "NETWORK_FAIL": 0, "UNIQUE_APPLICATION": 0, "BIZ_FAIL": 0}
    confirmed_unique: list[int] = []
    log(f"BATCH {batch_no} UNIQUE_APPLICATION; re-scan {len(app_ids)} id(s) as application")

    for index, app_id in enumerate(app_ids):
        try:
            rc, out, err = call_single(app_id, "application")
            status, msg = classify(rc, out, err)
        except Exception as exc:
            status, msg, rc = "NETWORK_FAIL", f"EXC {exc}", -1

        counts[status] += 1
        if status == "UNIQUE_APPLICATION":
            confirmed_unique.append(app_id)
        log_jsonl(delete_log, {
            "batch": batch_no,
            "ids": [app_id],
            "type": "application",
            "result": status,
            "msg": msg,
            "rc": rc,
            "mode": "bulk-400059-single-rescan",
        })
        log(f"RESCAN {index + 1}/{len(app_ids)} app={app_id} {status}")
        if index < len(app_ids) - 1:
            time.sleep(interval)

    return counts, confirmed_unique


def run_main_pass(batches: list[list[int]], type_: str, workdir: Path,
                  input_hash: str, interval: float, use_bulk: bool,
                  org_id: str) -> dict:
    """Run main deletion pass. Returns counts dict."""
    delete_log = workdir / "delete.log"
    state_path = workdir / "state.json"
    log = make_logger(workdir / "run.log")

    start_idx = 0
    st = load_state(state_path)
    if st:
        if st.get("orgId") and st["orgId"] != org_id:
            sys.exit(f"error: state.json orgId={st['orgId']} but current cllmk org={org_id}; "
                     f"delete {state_path} or switch cllmk profile/env before rerunning")
        if st.get("input_hash") != input_hash:
            sys.exit(f"error: state.json input_hash mismatch (saved={st.get('input_hash')[:8]}, "
                     f"current={input_hash[:8]}); refuse to resume across different inputs")
        if st.get("type") != type_:
            sys.exit(f"error: state.json type mismatch (saved={st.get('type')}, current={type_}); "
                     "refuse to resume across different --type")
        start_idx = st.get("next_batch", 0)
        log(f"RESUME from batch {start_idx}/{len(batches)}")

    counts = {"OK": 0, "NETWORK_FAIL": 0, "UNIQUE_APPLICATION": 0, "BIZ_FAIL": 0}
    unique_ids: list[int] = []  # collected across the pass for Task 6

    log(f"MAIN START batches={len(batches)} type={type_} interval={interval}s use_bulk={use_bulk}")

    for bi in range(start_idx, len(batches)):
        b = batches[bi]
        if not use_bulk or len(b) == 1:
            # Fall back to single PUT per id
            for app_id in b:
                try:
                    rc, out, err = call_single(app_id, type_)
                    status, msg = classify(rc, out, err)
                except Exception as e:
                    status, msg, rc = "NETWORK_FAIL", f"EXC {e}", -1
                counts[status] += 1
                if status == "UNIQUE_APPLICATION":
                    unique_ids.append(app_id)
                log_jsonl(delete_log, {
                    "batch": bi + 1, "ids": [app_id], "type": type_,
                    "result": status, "msg": msg, "rc": rc, "mode": "single",
                })
        else:
            try:
                rc, out, err = call_bulk(b, type_)
                status, msg = classify(rc, out, err)
            except Exception as e:
                status, msg, rc = "NETWORK_FAIL", f"EXC {e}", -1
            if status == "UNIQUE_APPLICATION" and type_ == "application":
                log_jsonl(delete_log, {
                    "batch": bi + 1, "ids": b, "type": type_,
                    "result": "BULK_400059_RESCAN", "msg": msg, "rc": rc,
                    "mode": "bulk",
                })
                rescan_counts, confirmed_unique = rescan_bulk_unique_applications(
                    b, bi + 1, delete_log, interval, log,
                )
                for key, value in rescan_counts.items():
                    counts[key] += value
                unique_ids.extend(confirmed_unique)
                status = "BULK_400059_RESCANNED"
                msg = f"confirmed_unique={confirmed_unique}"
            else:
                counts[status] += 1
                if status == "UNIQUE_APPLICATION":
                    unique_ids.extend(b)
                log_jsonl(delete_log, {
                    "batch": bi + 1, "ids": b, "type": type_,
                    "result": status, "msg": msg, "rc": rc, "mode": "bulk",
                })

        if status == "OK":
            log(f"BATCH {bi+1}/{len(batches)} OK count={len(b)}")
        else:
            log(f"BATCH {bi+1}/{len(batches)} {status} ids={b} msg={msg}")

        write_state(state_path, bi + 1, type_, input_hash, org_id)

        if bi < len(batches) - 1:
            time.sleep(interval)

    log("MAIN DONE " + " ".join(f"{k}={v}" for k, v in counts.items()))
    # Persist unique_ids for Task 6 (400059 flow) & Task 8 (summary)
    (workdir / "unique_application.pending").write_text(
        "\n".join(str(i) for i in unique_ids) + ("\n" if unique_ids else "")
    )
    return counts


def prompt_unique_application_action(count: int) -> str:
    """Return one of 'E', 'S', 'A'. Falls back to 'S' when no TTY."""
    if not sys.stdin.isatty():
        print(f"AUTO_SKIP_UNIQUE_APPLICATION: no TTY, defaulting to SKIP for {count} ids")
        return "S"

    print()
    print("⚠️  检测到 UNIQUE_APPLICATION（400059）")
    print(f"   本轮 --type=application，有 {count} 个 applicationId 是候选人唯一申请，无法删除。")
    print("   请选择本轮所有 400059 的处置：")
    print("     [E] 升级到 type=candidate 删除（把候选人整体删掉，破坏范围放大）")
    print("     [S] 全部跳过并记录（保守）")
    print("     [A] 立刻终止")
    while True:
        choice = input("   选择 [E/S/A]: ").strip().upper()
        if choice in {"E", "S", "A"}:
            return choice
        print("   请输入 E / S / A")


def read_unique_pending(workdir: Path) -> list[int]:
    pending = workdir / "unique_application.pending"
    if not pending.exists():
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for line in pending.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            n = int(line)
        except ValueError:
            continue
        if n in seen:
            continue
        seen.add(n)
        ids.append(n)
    return ids


def write_skip_log(workdir: Path, ids: list[int]):
    with (workdir / "skip.log").open("a") as f:
        for i in ids:
            f.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "applicationId": i,
                "reason": "UNIQUE_APPLICATION",
                "action": "SKIP",
            }, ensure_ascii=False) + "\n")


def run_escalate_pass(ids: list[int], workdir: Path, batch_size: int,
                      interval: float, use_bulk: bool) -> dict:
    """Delete the given applicationIds with type=candidate, logging to escalate.log."""
    escalate_log = workdir / "escalate.log"
    log = make_logger(workdir / "run.log")
    log(f"ESCALATE START total={len(ids)} type=candidate")

    counts = {"OK": 0, "NETWORK_FAIL": 0, "UNIQUE_APPLICATION": 0, "BIZ_FAIL": 0}
    batches = [ids[i:i + batch_size] for i in range(0, len(ids), batch_size)]
    for bi, b in enumerate(batches):
        if not use_bulk or len(b) == 1:
            for app_id in b:
                try:
                    rc, out, err = call_single(app_id, "candidate")
                    status, msg = classify(rc, out, err)
                except Exception as e:
                    status, msg, rc = "NETWORK_FAIL", f"EXC {e}", -1
                counts[status] += 1
                log_jsonl(escalate_log, {"batch": bi + 1, "ids": [app_id], "type": "candidate",
                                         "result": status, "msg": msg, "rc": rc, "mode": "single"})
        else:
            try:
                rc, out, err = call_bulk(b, "candidate")
                status, msg = classify(rc, out, err)
            except Exception as e:
                status, msg, rc = "NETWORK_FAIL", f"EXC {e}", -1
            counts[status] += 1
            log_jsonl(escalate_log, {"batch": bi + 1, "ids": b, "type": "candidate",
                                     "result": status, "msg": msg, "rc": rc, "mode": "bulk"})

        log(f"ESCALATE {bi+1}/{len(batches)} {status} ids={b}")
        if bi < len(batches) - 1:
            time.sleep(interval)

    log("ESCALATE DONE " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def count_results(log_path: Path) -> dict:
    """Count OK / NETWORK_FAIL / UNIQUE_APPLICATION / BIZ_FAIL rows in a jsonl log."""
    counts = {"OK": 0, "NETWORK_FAIL": 0, "UNIQUE_APPLICATION": 0, "BIZ_FAIL": 0}
    if not log_path.exists():
        return counts
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        r = rec.get("result")
        # tally by IDs, not by batch rows (a bulk BIZ_FAIL affects len(ids) items)
        n = len(rec.get("ids", []) or [1])
        if r in counts:
            counts[r] += n
    return counts


def emit_summary(workdir: Path, total: int, type_: str,
                 escalate_action: str | None,
                 unique_ids: list[int],
                 elapsed_s: float):
    """Write summary.json and print human report."""
    main_counts = count_results(workdir / "delete.log")
    escalate_counts = count_results(workdir / "escalate.log")
    skip_lines = 0
    skip_log = workdir / "skip.log"
    if skip_log.exists():
        skip_lines = sum(1 for _ in skip_log.read_text().splitlines() if _.strip())

    summary = {
        "input_total": total,
        "type": type_,
        "elapsed_s": round(elapsed_s, 1),
        "main": main_counts,
        "escalate": escalate_counts,
        "escalate_action": escalate_action,
        "unique_application_hit": len(unique_ids),
        "skip_recorded": skip_lines,
    }
    (workdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    print()
    print("=== cllmk application-delete 战报 ===")
    print(f"input:  {total} 条")
    print(f"type:   {type_}")
    print(f"耗时:   {elapsed_s:.1f}s")
    print()
    print(f"主轮成功:                  {main_counts['OK']}")
    print(f"主轮网络失败:              {main_counts['NETWORK_FAIL']}  (delete.log)")
    print(f"主轮 UNIQUE_APPLICATION:   {main_counts['UNIQUE_APPLICATION']}")
    print(f"主轮其它业务失败:          {main_counts['BIZ_FAIL']}  (delete.log grep BIZ_FAIL)")
    if escalate_action == "E":
        print(f"升级 candidate 已删:       {escalate_counts['OK']}  (escalate.log)")
        print(f"升级 candidate 失败:       {sum(v for k,v in escalate_counts.items() if k!='OK')}  (escalate.log)")
    elif escalate_action == "S":
        print(f"唯一申请→跳过:             {skip_lines}  (skip.log)")
    elif escalate_action is None and len(unique_ids) > 0 and type_ == "candidate":
        # UNIQUE_APPLICATION 不应出现在 candidate 模式，但兜底提示
        print(f"⚠ UNIQUE_APPLICATION 在 candidate 模式出现: {len(unique_ids)}")


def load_skip_ids(workdir: Path) -> list[int]:
    skip_log = workdir / "skip.log"
    if not skip_log.exists():
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for line in skip_log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        i = rec.get("applicationId")
        if isinstance(i, int) and i not in seen:
            seen.add(i)
            ids.append(i)
    return ids


def run_rescue(workdir: Path, batch_size: int, interval: float, use_bulk: bool,
               expected_org_id: str):
    if not workdir.exists():
        sys.exit(f"error: workdir {workdir} does not exist")
    ids = load_skip_ids(workdir)
    if not ids:
        print("no skip.log entries; nothing to rescue")
        return

    # skip.log came from a specific org's run; refuse to escalate its ids
    # against whichever org the current cllmk profile happens to point at
    org_id = fetch_org_id()
    require_expected_org(org_id, expected_org_id)
    st = load_state(workdir / "state.json")
    if st and st.get("orgId") and st["orgId"] != org_id:
        sys.exit(f"error: workdir state.json orgId={st['orgId']} but current cllmk "
                 f"org={org_id}; run cllmk auth switch and verify current before --rescue")
    print(f"org={org_id} (tenant_source=current)")

    if sys.stdin.isatty():
        print()
        print(f"⚠️  RESCUE: 将把 skip.log 里 {len(ids)} 条 applicationId 以 type=candidate 重新删除。")
        print("   这会把这些候选人整体删掉（不可逆）。确认继续？[y/N]")
        confirm = input("   ").strip().lower()
        if confirm != "y":
            print("aborted.")
            return
    else:
        sys.exit("error: RESCUE refuses to run without TTY confirmation "
                 "(would escalate SKIP to candidate delete without user consent)")

    # audit
    (workdir / "rescue.authorization").write_text(json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "authorized_ids": ids,
        "reason": "user confirmed --rescue at prompt",
    }, ensure_ascii=False, indent=2))

    counts = run_escalate_pass(ids, workdir, batch_size, interval, use_bulk)
    print("RESCUE counts:", counts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["application", "candidate"], default=None,
                    help="REQUIRED (except --rescue): 'application' deletes only the application; "
                         "'candidate' deletes the candidate and ALL their applications")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="xlsx or csv with applicationIds")
    src.add_argument("--ids", type=str, help="comma-separated applicationIds")
    src.add_argument("--rescue", action="store_true",
                     help="rescue-only mode: reprocess skip.log entries from a prior --workdir as type=candidate")
    ap.add_argument("--id-column", default=None,
                    help="column name or 0-based index (default: first column)")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--no-bulk", action="store_true",
                    help="disable bulk endpoint; use single PUT per applicationId")
    ap.add_argument("--dry-run", action="store_true",
                    help="print payloads but do not call cllmk")
    ap.add_argument("--confirm", action="store_true",
                    help="allow irreversible writes; without this flag the script only previews")
    ap.add_argument("--expected-org-id",
                    help="required with --confirm; must exactly match the live current orgId")
    args = ap.parse_args()
    t0 = time.time()

    if not args.rescue and args.type is None:
        sys.exit("error: --type is required (application | candidate); no default is provided")

    if args.rescue:
        if not args.workdir:
            sys.exit("error: --workdir required for --rescue")
        if not args.confirm or args.dry_run:
            ids = load_skip_ids(args.workdir)
            print(f"[preview] would rescue-delete {len(ids)} candidate(s)")
            print("[preview] no API called; rerun with --confirm --expected-org-id <orgId>")
            return
        run_rescue(args.workdir, args.batch_size, args.interval, not args.no_bulk,
                   args.expected_org_id)
        return

    # Resolve ids + workdir
    if args.input:
        ids = load_ids_from_file(args.input, args.id_column)
        workdir = args.workdir or args.input.parent
    else:
        ids = parse_ids_csv(args.ids)
        if not args.workdir:
            workdir = Path(f"/tmp/ats-app-del-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        else:
            workdir = args.workdir

    workdir.mkdir(parents=True, exist_ok=True)
    if not ids:
        sys.exit("error: no applicationIds found in input")

    input_hash = compute_input_hash(input_path=args.input, ids=ids)
    print(f"Loaded {len(ids)} applicationIds; workdir={workdir}; input_hash={input_hash[:8]}")

    if args.dry_run or not args.confirm:
        if len(ids) == 1 or args.no_bulk:
            for i in ids:
                print(json.dumps(build_single_payload(i, args.type), ensure_ascii=False))
        else:
            batches = [ids[i:i + args.batch_size] for i in range(0, len(ids), args.batch_size)]
            for b in batches:
                print(json.dumps(build_bulk_payload(b, args.type), ensure_ascii=False))
        print("[preview] no API called; rerun with --confirm --expected-org-id <orgId>")
        return

    org_id = fetch_org_id()
    require_expected_org(org_id, args.expected_org_id)
    print(f"org={org_id} (tenant_source=current)")

    batches = [ids[i:i + args.batch_size] for i in range(0, len(ids), args.batch_size)]
    est = len(batches) * (args.interval + 1.3)
    print(f"→ {len(batches)} batches × {args.batch_size}; est. {est:.0f}s")

    main_counts = run_main_pass(
        batches=batches, type_=args.type, workdir=workdir,
        input_hash=input_hash, interval=args.interval, use_bulk=not args.no_bulk,
        org_id=org_id,
    )
    print("MAIN counts:", main_counts)
    if main_counts["NETWORK_FAIL"] > 0:
        print("NETWORK_FAIL batches were not retried because deletion may already have reached "
              "the server; verify each result before any manual retry")

    unique_ids = read_unique_pending(workdir)
    escalate_action: str | None = None
    if unique_ids and args.type == "application":
        escalate_action = prompt_unique_application_action(len(unique_ids))
        if escalate_action == "A":
            print("→ 用户选择 ABORT；state.json 已保留，可续跑或改数据后重跑")
            sys.exit(1)
        elif escalate_action == "S":
            write_skip_log(workdir, unique_ids)
            print(f"→ 已跳过 {len(unique_ids)} 条唯一申请，写入 skip.log")
        elif escalate_action == "E":
            print(f"→ 用户授权升级：将 {len(unique_ids)} 条唯一申请以 type=candidate 删除")
            # persist authorization audit trail before running
            (workdir / "escalate.authorization").write_text(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "authorized_ids": unique_ids,
                "reason": "user chose [E] at UNIQUE_APPLICATION prompt",
            }, ensure_ascii=False, indent=2))
            escalate_counts = run_escalate_pass(
                unique_ids, workdir, args.batch_size, args.interval, not args.no_bulk,
            )
            print("ESCALATE counts:", escalate_counts)

    unique_ids_final = read_unique_pending(workdir)
    emit_summary(
        workdir=workdir, total=len(ids), type_=args.type,
        escalate_action=escalate_action, unique_ids=unique_ids_final,
        elapsed_s=time.time() - t0,
    )


if __name__ == "__main__":
    main()
