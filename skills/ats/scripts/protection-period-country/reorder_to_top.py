#!/usr/bin/env python3
from __future__ import annotations

"""
按指定顺序把 K 个国家顶到优先级 #1..#K。

逆序遍历 order，每个发 priority = top（一般等于当前规则总数）。
- 最后调用 order[0]，落到 #1
- 倒数第二调用 order[1]，落到 #2
- ...
- 第一个调用 order[K-1]，落到 #K

中间被挤掉的旧 #1..#K 会顺延到 #K+1 之后。

用法：
  # 一般推荐：先 list，自动算出 top 值与每个国家的 id
  python3 reorder_to_top.py --order order.txt

  # 也可以显式给 top 和 id 映射
  python3 reorder_to_top.py --order order.txt --top-priority 246 --id-map ids.json

order.txt：一行一个国家名，期望的位次从 #1 到 #K
ids.json：{ "爱尔兰": 100000104, "匈牙利": 100000105, ... }
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LIST_URL = "/api/outer/ats-jc/channel/protectionPeriod/list"
CHANGE_URL = "/api/outer/ats-jc/channel/protectionPeriod/changePriority"
ORG_INFO_URL = "/api/v2/org/info"


def require_current_tenant() -> None:
    if os.environ.get("CLLMK_PROFILE", "").strip():
        raise SystemExit("error: CLLMK_PROFILE is set; unset it, run 'cllmk auth switch', "
                         "verify with 'cllmk auth status', then retry")


def cllmk(url, method="POST", payload="{}"):
    require_current_tenant()
    r = subprocess.run(
        ["cllmk", "curl", "--url", url, "--method", method, "--payload", payload],
        capture_output=True, text=True,
    )
    return r.stdout


def fetch_list():
    out = cllmk(LIST_URL, "POST", "{}")
    data = json.loads(out)
    if data.get("code") != 0:
        raise SystemExit(f"list failed: {out[:200]}")
    return data["data"]["data"]


def fetch_org_id() -> str:
    require_current_tenant()
    r = subprocess.run(
        ["cllmk", "curl", "--url", ORG_INFO_URL, "--method", "GET", "--filter", "orgInfo"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise SystemExit(f"org/info failed: {r.stdout.strip()[:200]} {r.stderr.strip()[:200]}")
    data = json.loads(r.stdout)
    org_id = ((data.get("data") or {}).get("orgInfo") or {}).get("orgId")
    if not org_id:
        raise SystemExit("current orgId unavailable; refuse to reorder")
    return str(org_id)


def require_expected_org(org_id: str, expected_org_id: str | None) -> None:
    if not expected_org_id:
        raise SystemExit("--expected-org-id is required with --confirm")
    if org_id != expected_org_id:
        raise SystemExit(f"current cllmk orgId={org_id} does not match "
                         f"--expected-org-id={expected_org_id}; refuse to reorder")


def load_order(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("["):
        return json.loads(text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", required=True, help="期望顺序的国家名清单（#1..#K）")
    ap.add_argument("--top-priority", type=int, help="当前最大 priority；省略则自动 list")
    ap.add_argument("--id-map", help="国家名→id 的 JSON；省略则自动 list 取")
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 API")
    ap.add_argument("--confirm", action="store_true",
                    help="允许修改优先级；未提供时默认只预览")
    ap.add_argument("--expected-org-id",
                    help="与 --confirm 同时提供，必须与实时 current orgId 完全一致")
    args = ap.parse_args()
    require_current_tenant()

    order = load_order(Path(args.order))

    if args.top_priority is None or args.id_map is None:
        rows = fetch_list()
        max_p = max(r["priority"] for r in rows)
        name2id = {r["name"]: r["id"] for r in rows}
        top = args.top_priority if args.top_priority is not None else max_p
        if args.id_map:
            name2id = json.loads(Path(args.id_map).read_text(encoding="utf-8"))
    else:
        top = args.top_priority
        name2id = json.loads(Path(args.id_map).read_text(encoding="utf-8"))

    missing = [n for n in order if n not in name2id]
    if missing:
        raise SystemExit(f"缺少 id 映射：{missing}")

    print(f"plan: 逆序 {len(order)} 个国家，每个发 priority={top}")
    for n in reversed(order):
        print(f"  -> {n} (id={name2id[n]})")

    if args.dry_run or not args.confirm:
        print("[preview] no changePriority API called; rerun with --confirm "
              "--expected-org-id <orgId>")
        return

    current_org_id = fetch_org_id()
    require_expected_org(current_org_id, args.expected_org_id)

    for name in reversed(order):
        payload = json.dumps({"id": name2id[name], "priority": top})
        out = cllmk(CHANGE_URL, "POST", payload)
        print(f"MOVE {name} -> top: {out.strip()[:120]}")
        time.sleep(args.delay)

    print("DONE")


if __name__ == "__main__":
    main()
