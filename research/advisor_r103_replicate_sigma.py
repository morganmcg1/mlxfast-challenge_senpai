#!/usr/bin/env python3
"""Direct, model-free estimate of official-scorer replicate noise.

Method
------
All 139 Maple submission commits are fetchable from origin by full SHA. For
each we build a COMMENT-INSENSITIVE digest of `Sources/`:

    sha256 over every file under Sources/, where for .swift files any line
    whose first non-space characters are `//` is dropped.

Receipts sharing a digest ran functionally identical code (the round-93 null
arms differ only in a marker comment such as `// senpai-r93-null-1`). Their
spread in `cs`, `D`, `P` and `T = D - 4P` is a direct measurement of the
official scorer's run-to-run reproducibility -- no model, no assumption.

Caveat recorded in the output: a `//` line inside an embedded-MSL string
literal is NOT semantically inert (it changes the emitted Metal text and hence
the compiled kernel). Groups are therefore reported with the number of distinct
RAW trees they contain so over-merging is visible and checkable.

Usage:
    python3 research/advisor_r103_replicate_sigma.py
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
OUT = os.path.join(ART, "replicate-sigma.json")


def sh(args, check=True, binary=False):
    p = subprocess.run(args, cwd=REPO, capture_output=True,
                       text=not binary)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {p.returncode}")
    return p


def list_sources(sha):
    p = sh(["git", "ls-tree", "-r", "--name-only", sha, "--", "Sources"])
    return sorted(x for x in p.stdout.splitlines() if x.strip())


def canon_digest(sha):
    files = list_sources(sha)
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode() + b"\0")
        blob = sh(["git", "show", f"{sha}:{f}"], binary=True).stdout
        if f.endswith(".swift"):
            keep = [ln for ln in blob.split(b"\n")
                    if not ln.lstrip().startswith(b"//")]
            blob = b"\n".join(keep)
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest(), len(files)


def stats(vals):
    n = len(vals)
    m = sum(vals) / n
    if n < 2:
        return m, 0.0
    v = sum((x - m) ** 2 for x in vals) / (n - 1)
    return m, math.sqrt(v)


def main():
    rows = [r for r in json.load(open(PROV)) if r.get("sub_sha")]
    shas = sorted({r["sub_sha"] for r in rows})
    print(f"{len(rows)} receipts, {len(shas)} commits")

    dig = {}
    for i, s in enumerate(shas):
        try:
            dig[s] = canon_digest(s)
        except Exception as e:  # noqa: BLE001
            print(f"  {s[:8]}: FAILED {e}")
        if (i + 1) % 25 == 0:
            print(f"  digested {i+1}/{len(shas)}", flush=True)

    raw_tree = {}
    for s in shas:
        p = sh(["git", "rev-parse", f"{s}:Sources"], check=False)
        raw_tree[s] = p.stdout.strip() if p.returncode == 0 else None

    groups = defaultdict(list)
    for r in rows:
        s = r["sub_sha"]
        if s in dig:
            groups[dig[s][0]].append(r)

    report = {"n_receipts": len(rows), "n_commits": len(shas), "groups": []}
    print("\n=== comment-insensitive replicate groups (n>=2 with cs) ===")
    for d, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        wc = [r for r in rs if r.get("cs") and r.get("D") and r.get("P")]
        trees = {raw_tree[r["sub_sha"]] for r in rs}
        e = {
            "digest": d[:16],
            "n": len(rs),
            "n_with_metrics": len(wc),
            "n_distinct_raw_trees": len(trees),
            "receipts": [
                {"id8": r["id8"], "ts": r["ts"], "cs": r.get("cs"),
                 "D": r.get("D"), "P": r.get("P"),
                 "T": (r["D"] - 4 * r["P"]) if r.get("D") and r.get("P") else None,
                 "sub_sha": r["sub_sha"],
                 "raw_tree": raw_tree[r["sub_sha"]]}
                for r in sorted(rs, key=lambda x: x.get("ts") or "")
            ],
        }
        if len(wc) >= 2:
            lcs = [math.log(r["cs"]) for r in wc]
            _, s_lcs = stats(lcs)
            e["sd_ln_cs_pct"] = 100 * s_lcs
            e["range_ln_cs_pct"] = 100 * (max(lcs) - min(lcs))
            mD, sD = stats([r["D"] for r in wc])
            mP, sP = stats([r["P"] for r in wc])
            mT, sT = stats([r["D"] - 4 * r["P"] for r in wc])
            e.update(mean_D=mD, sd_D_us=sD, mean_P=mP, sd_P_us=sP,
                     mean_T=mT, sd_T_us=sT,
                     sd_T_pct=100 * sT / mT, sd_D_pct=100 * sD / mD,
                     sd_P_pct=100 * sP / mP)
            span_h = None
            ts = sorted(r["ts"] for r in wc if r.get("ts"))
            if len(ts) >= 2:
                e["first_ts"], e["last_ts"] = ts[0], ts[-1]
            print(f"digest {d[:12]} n={len(rs)} metrics={len(wc)} "
                  f"rawtrees={len(trees)}  sd(ln cs)={e['sd_ln_cs_pct']:.4f}%  "
                  f"sd(T)={sT:.2f}us  sd(D)={sD:.2f}us  sd(P)={sP:.3f}us")
            for r in sorted(wc, key=lambda x: x.get("ts") or ""):
                print(f"    {r['ts']}  {r['id8']}  cs={r['cs']:.6f}  "
                      f"D={r['D']:.3f}  P={r['P']:.3f}  "
                      f"T={r['D'] - 4*r['P']:.3f}  tree={raw_tree[r['sub_sha']][:8]}")
        report["groups"].append(e)

    def pooled(key, dofkey="n_with_metrics"):
        num = den = 0.0
        for g in report["groups"]:
            if key in g:
                k = g[dofkey]
                num += g[key] ** 2 * (k - 1)
                den += (k - 1)
        return (math.sqrt(num / den), den) if den else (None, 0)

    for key, unit in [("sd_ln_cs_pct", "%"), ("sd_T_us", "us/step"),
                      ("sd_D_us", "us/step"), ("sd_P_us", "us/tok")]:
        v, dof = pooled(key)
        if v is not None:
            report[f"pooled_{key}"] = v
            report[f"pooled_{key}_dof"] = dof
            print(f"\nPOOLED {key} = {v:.4f} {unit}  (dof={dof})")

    # robust variant: drop groups whose sd(ln cs) exceeds 1% (thermal excursions)
    keep = [g for g in report["groups"]
            if "sd_ln_cs_pct" in g and g["sd_ln_cs_pct"] < 1.0]
    for key in ("sd_ln_cs_pct", "sd_T_us", "sd_D_us", "sd_P_us"):
        num = den = 0.0
        for g in keep:
            k = g["n_with_metrics"]
            num += g[key] ** 2 * (k - 1)
            den += (k - 1)
        if den:
            report[f"trimmed_pooled_{key}"] = math.sqrt(num / den)
            report[f"trimmed_pooled_{key}_dof"] = den
    if keep:
        print("\n--- trimmed (groups with sd(ln cs) < 1%) ---")
        for key in ("sd_ln_cs_pct", "sd_T_us", "sd_D_us", "sd_P_us"):
            if f"trimmed_pooled_{key}" in report:
                print(f"  {key} = {report[f'trimmed_pooled_{key}']:.4f} "
                      f"(dof={report[f'trimmed_pooled_{key}_dof']})")

    report["digests"] = {s: dig[s][0] for s in dig}
    report["raw_trees"] = raw_tree
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
