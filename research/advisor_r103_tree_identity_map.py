#!/usr/bin/env python3
"""Fetch every Maple submission commit from origin and build a tree-identity map.

Why this matters
----------------
Each receipt publishes `submissionCommitSha`. Those commits are NOT reachable
from any local branch, but `git fetch origin <FULL-40-CHAR-SHA>` succeeds. So
the exact tree that produced every one of our measured receipts can be
materialised locally.

Two payoffs:
  1. Provenance: we can prove which local commit a receipt actually measured
     instead of inferring it from PR bodies.
  2. Calibration: receipts whose `Sources/` trees are byte-identical are
     same-code replicates. Their spread is a direct, model-free estimate of
     the run-to-run reproducibility of the official scorer ACROSS sessions and
     days -- the number every power calculation in this campaign depends on.

Usage:
    python3 research/advisor_r103_tree_identity_map.py
"""
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(REPO, "research", "artifacts", "advisor-r103")
PROV = os.path.join(ART, "our-receipts-provenance.json")
OUT = os.path.join(ART, "tree-identity-map.json")

BATCH = 12


def sh(args, check=True):
    p = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {p.returncode}\n{p.stderr[:400]}")
    return p


def have(sha):
    p = sh(["git", "cat-file", "-e", sha + "^{commit}"], check=False)
    return p.returncode == 0


def fetch_batch(shas):
    if not shas:
        return
    sh(["git", "fetch", "--quiet", "origin"] + list(shas), check=False)


def subtree(sha, path):
    p = sh(["git", "rev-parse", f"{sha}:{path}"], check=False)
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def blob_sha(sha, path):
    p = sh(["git", "rev-parse", f"{sha}:{path}"], check=False)
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def main():
    rows = json.load(open(PROV))
    rows = [r for r in rows if r.get("sub_sha")]
    shas = sorted({r["sub_sha"] for r in rows})
    print(f"{len(rows)} receipts with a submission sha; {len(shas)} distinct commits")

    missing = [s for s in shas if not have(s)]
    print(f"{len(missing)} not present locally; fetching in batches of {BATCH}")
    for i in range(0, len(missing), BATCH):
        chunk = missing[i:i + BATCH]
        fetch_batch(chunk)
        got = sum(1 for s in chunk if have(s))
        print(f"  batch {i//BATCH + 1}: {got}/{len(chunk)} present after fetch",
              flush=True)

    ok = [s for s in shas if have(s)]
    print(f"{len(ok)}/{len(shas)} commits materialised")

    info = {}
    for s in ok:
        info[s] = {
            "sources_tree": subtree(s, "Sources"),
            "lrm_blob": blob_sha(s, "Sources/MLXFastModel/LagunaRuntimeModel.swift"),
            "model_tree": subtree(s, "Sources/MLXFastModel"),
        }

    # group receipts by Sources tree
    groups = defaultdict(list)
    for r in rows:
        s = r["sub_sha"]
        if s not in info or not info[s]["sources_tree"]:
            continue
        groups[info[s]["sources_tree"]].append(r)

    report = {
        "n_receipts": len(rows),
        "n_distinct_commits": len(shas),
        "n_materialised": len(ok),
        "unfetchable": [s for s in shas if not have(s)],
        "groups": [],
    }

    print("\n=== same-Sources-tree replicate groups (size >= 2, with cs) ===")
    for tree, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        with_cs = [r for r in rs if r.get("cs")]
        entry = {
            "sources_tree": tree,
            "n": len(rs),
            "n_with_cs": len(with_cs),
            "receipts": [
                {"id8": r["id8"], "ts": r["ts"], "cs": r.get("cs"),
                 "D": r.get("D"), "P": r.get("P"), "sub_sha": r["sub_sha"]}
                for r in sorted(rs, key=lambda x: x.get("ts") or "")
            ],
        }
        if len(with_cs) >= 2:
            xs = [math.log(r["cs"]) for r in with_cs]
            m = sum(xs) / len(xs)
            var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
            entry["sd_ln_cs_pct"] = 100.0 * math.sqrt(var)
            entry["range_cs_pct"] = 100.0 * (max(xs) - min(xs))
            ds = [r["D"] for r in with_cs if r.get("D")]
            if len(ds) >= 2:
                md = sum(ds) / len(ds)
                vd = sum((d - md) ** 2 for d in ds) / (len(ds) - 1)
                entry["mean_D"] = md
                entry["sd_D_us"] = math.sqrt(vd)
                entry["sd_D_pct"] = 100.0 * math.sqrt(vd) / md
            ps = [r["P"] for r in with_cs if r.get("P")]
            if len(ps) >= 2:
                mp = sum(ps) / len(ps)
                vp = sum((p - mp) ** 2 for p in ps) / (len(ps) - 1)
                entry["mean_P"] = mp
                entry["sd_P_us"] = math.sqrt(vp)
                entry["sd_P_pct"] = 100.0 * math.sqrt(vp) / mp
            ts_ = [r["D"] - 4.0 * r["P"] for r in with_cs
                   if r.get("D") and r.get("P")]
            if len(ts_) >= 2:
                mt = sum(ts_) / len(ts_)
                vt = sum((t - mt) ** 2 for t in ts_) / (len(ts_) - 1)
                entry["mean_T"] = mt
                entry["sd_T_us"] = math.sqrt(vt)
                entry["sd_T_pct"] = 100.0 * math.sqrt(vt) / mt
            print(f"tree {tree[:12]}  n={len(rs)} n_cs={len(with_cs)}  "
                  f"sd(ln cs)={entry['sd_ln_cs_pct']:.4f}%  "
                  f"range={entry['range_cs_pct']:.4f}%  "
                  f"sd(D)={entry.get('sd_D_us', float('nan')):.2f}us  "
                  f"sd(T)={entry.get('sd_T_us', float('nan')):.2f}us")
            for r in sorted(with_cs, key=lambda x: x.get("ts") or ""):
                print(f"    {r['ts']}  {r['id8']}  cs={r['cs']:.6f}  "
                      f"D={r.get('D')}  P={r.get('P')}")
        report["groups"].append(entry)

    # pooled within-tree estimate
    num, den = 0.0, 0
    for g in report["groups"]:
        if "sd_ln_cs_pct" in g:
            k = g["n_with_cs"]
            num += (g["sd_ln_cs_pct"] ** 2) * (k - 1)
            den += (k - 1)
    if den:
        report["pooled_sd_ln_cs_pct"] = math.sqrt(num / den)
        report["pooled_dof"] = den
        print(f"\nPOOLED within-tree sd(ln cs) = "
              f"{report['pooled_sd_ln_cs_pct']:.4f}%  (dof={den})")

    numT, denT = 0.0, 0
    for g in report["groups"]:
        if "sd_T_us" in g:
            k = g["n_with_cs"]
            numT += (g["sd_T_us"] ** 2) * (k - 1)
            denT += (k - 1)
    if denT:
        report["pooled_sd_T_us"] = math.sqrt(numT / denT)
        print(f"POOLED within-tree sd(T) = {report['pooled_sd_T_us']:.3f} us/step "
              f"(dof={denT})")

    numD, denD = 0.0, 0
    for g in report["groups"]:
        if "sd_D_us" in g:
            k = g["n_with_cs"]
            numD += (g["sd_D_us"] ** 2) * (k - 1)
            denD += (k - 1)
    if denD:
        report["pooled_sd_D_us"] = math.sqrt(numD / denD)
        print(f"POOLED within-tree sd(D) = {report['pooled_sd_D_us']:.3f} us/step "
              f"(dof={denD})")

    numP, denP = 0.0, 0
    for g in report["groups"]:
        if "sd_P_us" in g:
            k = g["n_with_cs"]
            numP += (g["sd_P_us"] ** 2) * (k - 1)
            denP += (k - 1)
    if denP:
        report["pooled_sd_P_us"] = math.sqrt(numP / denP)
        print(f"POOLED within-tree sd(P) = {report['pooled_sd_P_us']:.4f} us/tok "
              f"(dof={denP})")

    report["commit_info"] = info
    os.makedirs(ART, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
