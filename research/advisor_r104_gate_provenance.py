#!/usr/bin/env python3
"""Advisor r104: date every env gate, and rank the default-ON kill switches by
how likely each is to have rotted.

SS10 of research/advisor-r104-the-receipt-is-the-instrument.md found 76
default-ON gates on the executed path -- 76 shipped optimisations, each of which
won a measurement at the moment it was added and none of which has been
re-measured since.  That is an unaudited ablation ledger, and 76 arms is
unaffordable.  This script narrows it.

The ranking signal is provenance, and it is unusually sharp here because the
repository contains a MODEL SWAP:

    4799830b  2026-07-21  Migrate serial track:
              Gemma 4 31B -> Poolside Laguna XS 2.1

A gate introduced BEFORE that commit was tuned against a different model, with
different shapes, a different expert count and a different attention geometry.
Its "on" decision was correct for Gemma.  Nobody has re-derived it for Laguna.
Those are the prime suspects for having silently become pessimisations.

The secondary signal is churn: how many commits have touched the guarded file
since the gate appeared.  A gate whose surroundings were rewritten many times is
more likely to be stale than one whose surroundings are untouched.

Reads only git history and the SS10 artifact.  Writes one artifact.

usage:
    python3 research/advisor_r104_gate_provenance.py
env:
    MLXFAST_ROOT   repository root (defaults to this file's parent's parent)
"""

import json
import os
import subprocess
import sys
from collections import defaultdict

MIGRATION_SHA = "4799830b"
MIGRATION_DATE = "2026-07-21"

ROOT = os.environ.get("MLXFAST_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
INVENTORY = os.path.join(
    ROOT, "research", "artifacts", "advisor-r104-gate-inventory.json"
)
DEST = os.path.join(
    ROOT, "research", "artifacts", "advisor-r104-gate-provenance.json"
)


def git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=ROOT, capture_output=True, text=True
    ).stdout


def introduced(gate, path):
    """Oldest commit whose diff on `path` changes the number of occurrences of
    `gate`.  -S is a pickaxe: --reverse then gives first appearance."""
    out = git("log", "--reverse", "--format=%H|%ad|%s", "--date=short",
              "-S", gate, "--", path)
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        # gate may have arrived with the file under a different path
        out = git("log", "--reverse", "--format=%H|%ad|%s", "--date=short",
                  "-S", gate)
        lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        return None
    sha, date, subj = lines[0].split("|", 2)
    return dict(sha=sha[:12], date=date, subject=subj[:90], n_touch=len(lines))


def churn_since(path, sha):
    if not sha:
        return None
    out = git("rev-list", "--count", f"{sha}..HEAD", "--", path)
    try:
        return int(out.strip())
    except ValueError:
        return None


def main():
    inv = json.load(open(INVENTORY))
    print(f"loaded {len(inv)} executed-path gates from the SS10 inventory")

    # cache per (gate, file) because several gates repeat across sites
    seen = {}
    rows = []
    for rec in inv:
        gate = rec["gate"]
        path = rec["site"].rsplit(":", 1)[0]
        key = (gate, path)
        if key not in seen:
            intro = introduced(gate, path)
            seen[key] = dict(
                intro=intro,
                churn=churn_since(path, intro["sha"]) if intro else None,
            )
        info = seen[key]
        rows.append(dict(rec, path=path, **info))

    # de-duplicate to one row per gate, keeping the earliest introduction
    by_gate = {}
    for r in rows:
        g = r["gate"]
        cur = by_gate.get(g)
        if cur is None:
            by_gate[g] = r
            continue
        a = (r["intro"] or {}).get("date") or "9999"
        b = (cur["intro"] or {}).get("date") or "9999"
        if a < b:
            by_gate[g] = r
    gates = list(by_gate.values())
    print(f"{len(gates)} distinct gates after de-duplication\n")

    def era(r):
        d = (r["intro"] or {}).get("date")
        if not d:
            return "unknown"
        return "pre-Laguna" if d <= MIGRATION_DATE else "post-Laguna"

    counts = defaultdict(lambda: defaultdict(int))
    for r in gates:
        counts[r["polarity"]][era(r)] += 1
    print(f"introduction era, split by default polarity "
          f"(migration {MIGRATION_SHA} {MIGRATION_DATE})")
    print(f"{'polarity':<10}{'pre-Laguna':>12}{'post-Laguna':>13}{'unknown':>10}")
    for pol in sorted(counts, key=lambda x: str(x)):
        c = counts[pol]
        print(f"{str(pol):<10}{c['pre-Laguna']:>12}{c['post-Laguna']:>13}"
              f"{c['unknown']:>10}")
    print()

    on = [r for r in gates if r["polarity"] == "ON"]
    print(f"===== the {len(on)} default-ON kill switches, ranked =====")
    print("rank key: pre-Laguna first (tuned on a model we no longer run),")
    print("then by churn in the guarded file since the gate appeared,")
    print("then by how little research/ has to say about it.\n")

    def sort_key(r):
        return (
            0 if era(r) == "pre-Laguna" else (1 if era(r) == "post-Laguna" else 2),
            -(r["churn"] or 0),
            r["research_docs"],
            r["gate"],
        )

    on.sort(key=sort_key)
    print(f"{'#':>3} {'gate':<48}{'era':<13}{'added':<12}"
          f"{'churn':>6}{'docs':>6}")
    for i, r in enumerate(on, 1):
        intro = r["intro"] or {}
        print(f"{i:>3} {r['gate']:<48}{era(r):<13}"
              f"{intro.get('date','?'):<12}{str(r['churn'] or 0):>6}"
              f"{r['research_docs']:>6}")

    pre_on = [r for r in on if era(r) == "pre-Laguna"]
    silent = [r for r in on if r["research_docs"] == 0]
    both = [r for r in pre_on if r["research_docs"] == 0]
    print()
    print(f"default-ON and PRE-Laguna              : {len(pre_on)}")
    print(f"default-ON and unmentioned in research/: {len(silent)}")
    print(f"default-ON, PRE-Laguna AND unmentioned : {len(both)}")
    if both:
        print("  ^ this is the shortlist worth spending calibrated arms on:")
        for r in both:
            print(f"    {r['gate']:<46} {r['site']}")

    out = dict(
        migration=dict(sha=MIGRATION_SHA, date=MIGRATION_DATE),
        n_gates=len(gates),
        era_by_polarity={str(k): dict(v) for k, v in counts.items()},
        default_on_ranked=[
            dict(
                gate=r["gate"],
                site=r["site"],
                era=era(r),
                added=(r["intro"] or {}).get("date"),
                added_sha=(r["intro"] or {}).get("sha"),
                added_subject=(r["intro"] or {}).get("subject"),
                churn_since=r["churn"],
                research_docs=r["research_docs"],
            )
            for r in on
        ],
        shortlist=[r["gate"] for r in both],
    )
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    print(f"\nwrote {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
