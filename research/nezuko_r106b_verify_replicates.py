#!/usr/bin/env python3
"""r106-B Stage 0 support: verify replicate identity on the FULL submitted surface.

The r103 replicate digest covers only `Sources/`, so it can merge receipts that
differ under `Vendor/` -- and `Vendor/mlx-swift*` files are submitted and do
change behaviour. This script recomputes replicate identity over `Sources/` AND
`Vendor/` for the receipts a Stage-0 variance pool would use, and reports, per
group, whether the surviving differences really are inert comments.

Two digests per commit:
  strict : sha256 over raw bytes of every file under Sources/ and Vendor/
  ci     : same, but full-line `//` comments are dropped from .swift files

A `//` line inside an embedded-MSL multiline string literal is NOT inert, so
every ci-equal / strict-unequal pair is additionally checked line by line: each
differing line must be a full-line `//` comment that is not inside a `\"\"\"`
literal. Groups failing that check are reported and excluded.

Read-only with respect to the working tree; only fetches objects into .git.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTIER_SHA = "bd33883eb89209c9714c8c570e399613ecbaa848"
ARM_R_SHA = "ef055b9b1956e8056267972308fd7deddd89649d"

FRESH_PATTERNS = [
    (re.compile(r"r105-A ladder receipt (A\d)-\d", re.I), "r105A/{}"),
    (re.compile(r"r104-A stage 2, leg \d+ of \d+ [\u2014-]+ arm ([A-Z])", re.I), "r104A/arm{}"),
]


def sh(args, binary=False, check=True):
    p = subprocess.run(args, cwd=REPO, capture_output=True, text=not binary)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])}... -> {p.returncode}: "
                           f"{(p.stderr if not binary else p.stderr.decode()) [:200]}")
    return p


def have(sha: str) -> bool:
    return sh(["git", "cat-file", "-e", f"{sha}^{{commit}}"], check=False).returncode == 0


def fetch(shas: list[str]) -> dict[str, bool]:
    missing = [s for s in shas if not have(s)]
    for i in range(0, len(missing), 8):
        batch = missing[i:i + 8]
        sh(["git", "fetch", "--quiet", "origin"] + batch, check=False)
    return {s: have(s) for s in shas}


def surface_tree(sha: str) -> dict[str, str]:
    """path -> git blob sha for every file under Sources/ and Vendor/."""
    p = sh(["git", "ls-tree", "-r", sha, "--", "Sources", "Vendor"])
    out: dict[str, str] = {}
    for line in p.stdout.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        _mode, _typ, blob = meta.split()
        out[path] = blob
    return out


def strip_comment_lines(blob: bytes) -> bytes:
    return b"\n".join(ln for ln in blob.split(b"\n") if not ln.lstrip().startswith(b"//"))


def blob_bytes(blob_sha: str) -> bytes:
    return sh(["git", "cat-file", "blob", blob_sha], binary=True).stdout


def strict_digest(tree: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path in sorted(tree):
        h.update(path.encode() + b"\0" + tree[path].encode() + b"\0")
    return h.hexdigest()


def in_multiline_literal(lines: list[bytes], idx: int) -> bool:
    return sum(ln.count(b'"""') for ln in lines[:idx]) % 2 == 1


def inert_only(blob_a: bytes, blob_b: bytes) -> tuple[bool, list[str]]:
    """True when every DIFFERING line is a full-line `//` comment outside a \"\"\" literal."""
    la, lb = blob_a.split(b"\n"), blob_b.split(b"\n")
    bad: list[str] = []
    sm = difflib.SequenceMatcher(a=la, b=lb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for lines, lo, hi, side in ((la, i1, i2, "a"), (lb, j1, j2, "b")):
            for i in range(lo, hi):
                ln = lines[i]
                if not ln.lstrip().startswith(b"//"):
                    bad.append(f"{side}:line {i + 1}: non-comment change")
                elif in_multiline_literal(lines, i):
                    bad.append(f"{side}:line {i + 1}: `//` inside a multiline literal")
    return (not bad), bad


def load_corpus(path: str) -> list[dict]:
    with open(path) as fh:
        blob = json.load(fh)
    out = []
    for r in blob["submissions"]:
        m = r.get("officialMetrics") or {}
        dec, pre = m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token")
        if dec is None or pre is None:
            continue
        out.append({"id": r.get("id"), "sub_sha": r.get("submissionCommitSha") or "",
                    "note": r.get("note") or "", "ts": r.get("createdAt") or "",
                    "D": float(dec) * 1e6, "P": float(pre) * 1e6})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--r103", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    corpus = load_corpus(args.corpus)
    by_sha = {r["sub_sha"]: r for r in corpus if r["sub_sha"]}

    # candidate groups: r103 digest groups with >=2 metric-bearing receipts, plus fresh ladder arms
    with open(args.r103) as fh:
        r103 = json.load(fh)
    cand: dict[str, list[str]] = {}
    for g in r103["groups"]:
        shas = [r["sub_sha"] for r in g["receipts"] if r.get("sub_sha")]
        shas = [s for s in shas if s in by_sha]
        if len(shas) >= 2:
            cand[f"r103:{g['digest']}"] = shas

    fresh: dict[str, list[str]] = defaultdict(list)
    for r in corpus:
        for pat, fmt in FRESH_PATTERNS:
            m = pat.search(r["note"])
            if m:
                fresh[f"fresh:{fmt.format(m.group(1))}"].append(r["sub_sha"])
                break
    for k, v in fresh.items():
        if len(v) >= 2:
            cand[k] = v

    all_shas = sorted({s for v in cand.values() for s in v} | {FRONTIER_SHA, ARM_R_SHA})
    print(f"{len(cand)} candidate groups, {len(all_shas)} commits", flush=True)
    avail = fetch(all_shas)
    print(f"fetched: {sum(avail.values())}/{len(all_shas)} available", flush=True)

    trees: dict[str, dict[str, str]] = {}
    for s in all_shas:
        if avail[s]:
            trees[s] = surface_tree(s)
    print(f"read {len(trees)} surface trees "
          f"({len(next(iter(trees.values()))) if trees else 0} files each)", flush=True)

    bcache: dict[str, bytes] = {}

    def content(blob_sha: str) -> bytes:
        if blob_sha not in bcache:
            bcache[blob_sha] = blob_bytes(blob_sha)
        return bcache[blob_sha]

    groups_out = []
    for name, shas in sorted(cand.items()):
        shas = [s for s in shas if s in trees]
        if len(shas) < 2:
            continue
        strict_set = {strict_digest(trees[s]) for s in shas}
        problems: list[str] = []
        changed_files: dict[str, int] = defaultdict(int)
        ref = shas[0]
        for s in shas[1:]:
            ta, tb = trees[ref], trees[s]
            if set(ta) != set(tb):
                only = sorted(set(ta) ^ set(tb))[:3]
                problems.append(f"{s[:8]}: file set differs ({only})")
                continue
            for f in sorted(ta):
                if ta[f] == tb[f]:
                    continue
                changed_files[f] += 1
                ok, bad = inert_only(content(ta[f]), content(tb[f]))
                if not ok:
                    problems.append(f"{s[:8]}:{f}: " + "; ".join(bad[:2]))
        groups_out.append({
            "group": name,
            "n": len(shas),
            "shas": [s[:12] for s in shas],
            "n_distinct_strict": len(strict_set),
            "changed_files_vs_reference": dict(sorted(changed_files.items())),
            "verified_inert_only": not problems,
            "problems": problems[:6],
            "receipts": sorted(({"sha12": s[:12], "ts": by_sha[s]["ts"],
                                 "D": by_sha[s]["D"], "P": by_sha[s]["P"],
                                 "T": by_sha[s]["D"] - 4.0 * by_sha[s]["P"]} for s in shas),
                               key=lambda x: x["ts"]),
        })

    out = {
        "schema": "maple-nezuko-r106b-replicate-identity/1",
        "identity": ("comment-insensitive sha256 over every file under Sources/ AND Vendor/, "
                     "with every ci-equal pair line-checked so surviving differences are "
                     "full-line `//` comments outside a multiline string literal"),
        "arms": {k: {"sha": v, "available": v in trees,
                     "strict_digest": strict_digest(trees[v]) if v in trees else None,
                     "n_files": len(trees.get(v, {}))}
                 for k, v in (("frontier", FRONTIER_SHA), ("arm_r", ARM_R_SHA))},
        "n_groups": len(groups_out),
        "n_verified_groups": sum(1 for g in groups_out if g["verified_inert_only"]),
        "groups": groups_out,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)

    for g in groups_out:
        flag = "VERIFIED" if g["verified_inert_only"] else "REJECTED"
        print(f"  {flag:8s} {g['group']:24s} n={g['n']} strict={g['n_distinct_strict']} "
              f"{g['problems'][:1]}")
    print(f"{out['n_verified_groups']}/{out['n_groups']} groups verified -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
