#!/usr/bin/env python3
"""Advisor r103 rung-0 probe: does a receipt carry a commit SHA that exists in
OUR fork?

The submissions endpoint exposes THREE commit-shaped fields that our tooling
had never dumped:

  * `submissionCommitSha`      (top level, 1678/1771 records)
  * `officialMetrics.commit`   (1205 records)  <- the only one we ever used
  * `promotedSourceRef`        (146 records)

`officialMetrics.commit` values (`ef055b9b`, `bd33883e`, ...) are NOT present in
our fork, which is why reference-tree provenance has always been inherited
belief. If `submissionCommitSha` is instead the SHA of the branch commit we
submitted, provenance becomes directly verifiable with `git cat-file`.

READ-ONLY. Never submits. Never prints the token.

usage: advisor_r103_provenance_probe.py
"""

import json
import os
import pathlib
import subprocess
import sys
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
US = "morganmcg1"
MB_D = 0.013855009542
MB_P = 0.000372473193

# receipts the round leans on: id8 -> label
OF_INTEREST = {
    "25e1f18e": "rank1 best-ever",
    "7ce1262d": "rank2 ARM R  (believed tree 30f752df)",
    "83fd2642": "rank3 Arm F",
    "05dd8bbf": "rank4",
    "e08d759f": "rank6 MERGED FRONTIER (believed tree = base)",
    "59bd72a3": "rank10 post-revert control c6c66344",
}

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]
if not token:
    sys.exit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")
SECRET = token


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {SECRET}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def cs_of(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def local_kind(sha):
    """Does this object exist in our fork, and what is it?"""
    if not sha:
        return "-"
    r = subprocess.run(["git", "cat-file", "-t", sha],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "ABSENT"
    kind = r.stdout.strip()
    d = subprocess.run(["git", "log", "-1", "--format=%h %ad %s", "--date=short", sha],
                       capture_output=True, text=True)
    return f"{kind}: {d.stdout.strip()[:70]}" if d.returncode == 0 else kind


def main():
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")["benchmark"]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]

    ours = []
    for r in rows:
        if r.get("solverUsername") != US:
            continue
        m = r.get("officialMetrics") or {}
        if not isinstance(m, dict):
            m = {}
        d, p = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        ours.append(dict(
            id8=r["id"][:8],
            ts=(m.get("timestamp") or r.get("createdAt") or "")[:19],
            status=r.get("status"),
            sub_sha=(r.get("submissionCommitSha") or ""),
            met_commit=(m.get("commit") or ""),
            promoted=(r.get("promotedSourceRef") or ""),
            cs=cs_of(d, p) if (d and p) else None,
            D=d * 1e6 if d else None,
            P=p * 1e6 if p else None,
        ))
    ours.sort(key=lambda x: x["ts"])
    print(f"our receipts: {len(ours)}")

    same = sum(1 for r in ours if r["sub_sha"] and r["sub_sha"] == r["met_commit"])
    diff = sum(1 for r in ours if r["sub_sha"] and r["met_commit"] and r["sub_sha"] != r["met_commit"])
    print(f"submissionCommitSha == officialMetrics.commit : {same}")
    print(f"submissionCommitSha != officialMetrics.commit : {diff}")

    print("\n===== the six receipts the round leans on =====")
    for r in ours:
        if r["id8"] not in OF_INTEREST:
            continue
        print(f"\n--- {r['id8']}  {OF_INTEREST[r['id8']]}")
        print(f"    ts={r['ts']}  status={r['status']}  cs={r['cs']}")
        print(f"    submissionCommitSha = {r['sub_sha']}")
        print(f"        local: {local_kind(r['sub_sha'])}")
        print(f"    officialMetrics.commit = {r['met_commit']}")
        print(f"        local: {local_kind(r['met_commit'])}")
        if r["promoted"]:
            print(f"    promotedSourceRef = {r['promoted']}")
            print(f"        local: {local_kind(r['promoted'])}")

    print("\n===== how many of OUR submissionCommitSha values exist locally? =====")
    present = absent = 0
    for r in ours:
        if not r["sub_sha"]:
            continue
        if local_kind(r["sub_sha"]).startswith("ABSENT"):
            absent += 1
        else:
            present += 1
    print(f"  present locally: {present}   absent: {absent}")

    pathlib.Path("research/artifacts/advisor-r103").mkdir(parents=True, exist_ok=True)
    pathlib.Path("research/artifacts/advisor-r103/our-receipts-provenance.json").write_text(
        json.dumps(ours, indent=1, sort_keys=True))
    print("\nwrote research/artifacts/advisor-r103/our-receipts-provenance.json")


if __name__ == "__main__":
    main()
