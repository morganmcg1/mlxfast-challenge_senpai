#!/usr/bin/env python3
"""Rule 105.14 -- the editable byte budget is a *shared, per-file* resource and
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is the binding constraint.

Provenance of the discovery (advisor error #10, self-reported):
  When I merged maple-nezuko's R106-B (PR #616) I checked base-drift
  (`git diff base_old base_new -- Sources ...`) but did NOT check the PR *head*
  content against the base.  Her report said "RECOMMENDED ADOPTION: ZERO SOURCE
  BYTES", which was true about *behaviour* -- every arm was env-gated OFF -- but
  her branch still carried 26,000 bytes of experimental scaffolding
  (DARKBLOOM_FUSED_SLIDING_ATTN_H4 / _PACKRED / _NOREDUCE) in
  LagunaRuntimeModel.swift.  The squash merge put all of it on the integration
  tree.  Reverted in the commit that carries this file.

  Standing fix (advisor): before merging any experiment, diff the PR HEAD
  against the base over the editable surface, not just base-against-base.
  "Zero source bytes adopted" is a claim about semantics; the byte budget is a
  claim about *text*.  They are different audits.

Limits, read out of `senpai/check-editable-budget.sh` (authoritative):
  MAX_TOTAL_BYTES  = 3_000_000     total over benchmark.json:editablePaths
  MAX_FILE_BYTES   =   524_288     per file -- HARD ABORT, checked file by file
  MAX_GROWTH_BYTES =   262_144     working_total - base_total, vs trusted main

Run:  python3 research/advisor_r105_14_editable_byte_budget.py
"""

from __future__ import annotations

import json
import subprocess
import sys

MAX_TOTAL_BYTES = 3_000_000
MAX_FILE_BYTES = 524_288
MAX_GROWTH_BYTES = 262_144

TRUSTED_MAIN = "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7"

# Size of the scaffolding one student's single decode-kernel experiment added to
# LagunaRuntimeModel.swift in PR #616 (three env-gated arms + macro plumbing).
NEZUKO_UNIT = 26_000


def sh(*args: str) -> str:
    return subprocess.run(
        args, capture_output=True, text=True, check=True
    ).stdout


def editable_files(base_sha: str) -> list[str]:
    contract = json.loads(sh("git", "show", f"{base_sha}:benchmark.json"))
    paths = contract["editablePaths"]
    seen: dict[str, None] = {}
    for p in paths:
        out = sh("git", "ls-tree", "-r", "--name-only", base_sha, "--", p)
        for line in out.splitlines():
            if line:
                seen.setdefault(line, None)
    return list(seen)


def working_size(path: str) -> int:
    try:
        with open(path, "rb") as handle:
            return len(handle.read())
    except FileNotFoundError:
        return 0


def main() -> int:
    base = TRUSTED_MAIN
    files = editable_files(base)

    sizes = {p: working_size(p) for p in files}
    # files present on disk but absent from base are added by us; account them
    total = sum(sizes.values())

    base_total = 0
    for p in files:
        try:
            base_total += int(
                sh("git", "cat-file", "-s", f"{base}:{p}").strip()
            )
        except subprocess.CalledProcessError:
            pass

    growth = total - base_total

    print("=" * 78)
    print("RULE 105.14  editable byte budget -- census")
    print("=" * 78)
    print(f"editable files (from {base[:8]}:benchmark.json): {len(files)}")
    print(
        f"total       {total:>9,} / {MAX_TOTAL_BYTES:>9,}"
        f"   headroom {MAX_TOTAL_BYTES - total:>9,}"
    )
    print(
        f"growth      {growth:>9,} / {MAX_GROWTH_BYTES:>9,}"
        f"   (negative = the campaign has recovered bytes)"
    )
    print()

    print("--- ten largest editable files and their PER-FILE headroom ---")
    print(f"{'bytes':>9}  {'headroom':>9}  {'%full':>6}  path")
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    for path, n in ranked[:10]:
        head = MAX_FILE_BYTES - n
        print(f"{n:>9,}  {head:>9,}  {100.0 * n / MAX_FILE_BYTES:>5.1f}%  {path}")
    print()

    hot = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
    n = sizes.get(hot, 0)
    head = MAX_FILE_BYTES - n
    print("=" * 78)
    print("THE BINDING CONSTRAINT")
    print("=" * 78)
    print(f"{hot}")
    print(f"  size            {n:>9,}")
    print(f"  per-file limit  {MAX_FILE_BYTES:>9,}")
    print(f"  headroom        {head:>9,}   ({100.0 * n / MAX_FILE_BYTES:.1f}% full)")
    print()
    print(
        f"  One student's experimental scaffolding for ONE decode kernel"
        f" (PR #616) = {NEZUKO_UNIT:,} B."
    )
    print(
        f"  Per-file headroom = {head / NEZUKO_UNIT:.1f} such units."
        f"   Total headroom = {(MAX_TOTAL_BYTES - total) / NEZUKO_UNIT:.1f} units."
    )
    print()
    print("  Live arms that all edit THIS file:")
    for who, what in [
        ("maple-edward  #629", "R107-A routed gate_up packing"),
        ("maple-alphonse #644", "R107-E decode oproj amortisation"),
        ("maple-frieren  #597", "R105-B router prefetch adjudication"),
        ("maple-nezuko   (new)", "R107-J qkv lane-major packing replication"),
        ("maple-tanjiro  #648", "R107-G decode family regime census (probes)"),
    ]:
        print(f"    - {who}: {what}")
    print()
    n_arms = 5
    print(
        f"  If all {n_arms} land scaffolding at the #616 rate:"
        f" {n_arms * NEZUKO_UNIT:,} B vs {head:,} B headroom"
        f"  -> {'BREACH' if n_arms * NEZUKO_UNIT > head else 'fits, with'}"
        f" {abs(head - n_arms * NEZUKO_UNIT):,} B to spare."
    )
    print()
    print("=" * 78)
    print("RULINGS")
    print("=" * 78)
    print(
        """
(1) The per-file limit, not the total, is what will kill a draw.  The total has
    ~319 KB of slack and NEGATIVE growth (the campaign's byte-recovery branches
    banked ~303 KB).  LagunaRuntimeModel.swift is at 73% of its own hard cap and
    is the one file every live decode arm edits.  Five arms scaffolded at the
    #616 rate = 130,000 B against 140,043 B of headroom: it fits with 10 KB to
    spare, i.e. ONE extra experiment aborts the run.  This is the tightest
    resource in the campaign and nobody was tracking it.

(2) `check-editable-budget.sh` aborts on the FIRST oversized file and does not
    tell you how close the others are.  A green check today says nothing about
    whether the integrated tree is green.  Integration must re-run it.

(3) Experimental scaffolding is NOT free just because it is env-gated OFF.
    "Zero source bytes adopted" is a semantic claim; the budget is textual.
    Students: when an arm closes negative, DELETE the scaffolding from Sources/
    in the same commit that reports the result, and keep the reproduction in
    research/ (which is outside editablePaths and therefore free).

(4) Advisor standing rule: before merging, diff the PR HEAD against the base
    restricted to editablePaths, and run check-editable-budget.sh on the
    resulting tree.  Base-against-base drift checking is a different audit and
    does not catch this.

(5) Interaction with nezuko's finding E.3: `research/` is NOT in editablePaths.
    That cuts both ways -- research/ costs zero budget, but any branch carrying
    research/ edits is REJECTED by the CI surface gate.  The draw branch must
    therefore be Sources-only, which means the integrator strips research/ and
    re-runs BOTH gates (surface + budget) on the exact submitted tree.
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
