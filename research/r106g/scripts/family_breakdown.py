#!/usr/bin/env python3
"""R106-G Stage 1 family breakdown: read multiplicity of the weight payload.

Splits each family's accepted DRAM traversal (fern-r105d) into the part that
lands on buffers with exactly one reading dispatch in the step -- provably read
once, because a byte read twice must be bound twice -- and the part that lands
on buffers some other dispatch also binds.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
from roundtrip_census import load_step, B_STEP, BW_M5, DECODE_PCT_PER_US  # noqa: E402

SLC = 24 * 1024 * 1024


def main():
    step = load_step(os.path.join(REPO, "research", "artifacts", "fern-r106g",
                                  "dispatch_raw.tsv"))
    with open(os.path.join(REPO, "research", "artifacts", "fern-r105d",
                           "decode-byte-census.json")) as f:
        cen = json.load(f)
    fam_bytes = {x["family"]: x["bytes_per_step"] for x in cen["families"]}

    readers = collections.defaultdict(set)
    for r in step:
        outs = set(r["outs"])
        for k in set(r["ins"]) - outs:
            readers[k].add(r["i"])

    # Per family: split the bound read extent into single-reader and shared.
    fam_single = collections.Counter()
    fam_shared = collections.Counter()
    for r in step:
        outs = set(r["outs"])
        for k in set(r["ins"]) - outs:
            if len(readers[k]) == 1:
                fam_single[r["family"]] += k[2]
            else:
                fam_shared[r["family"]] += k[2]

    print(f"{'traversal B':>12} {'%B':>7} {'excl':>7} {'shared bind B':>14} "
          f"{'>SLC?':>6}  family")
    tot_excl = 0
    rows = []
    for fam, tb in sorted(fam_bytes.items(), key=lambda kv: -kv[1]):
        s, sh = fam_single[fam], fam_shared[fam]
        frac = s / (s + sh) if (s + sh) else 1.0
        excl = tb * frac
        tot_excl += excl
        above = any(k[2] > SLC for k, w in readers.items()
                    if any(step[i]["family"] == fam for i in w))
        rows.append({"family": fam, "traversal_bytes": tb,
                     "pct_of_B": 100 * tb / B_STEP,
                     "single_reader_bind_bytes": s, "shared_bind_bytes": sh,
                     "exclusive_fraction": frac,
                     "traversal_provably_read_once": excl,
                     "touches_above_slc_buffer": above})
        print(f"{tb:>12} {100*tb/B_STEP:>7.3f} {100*frac:>6.2f}% {sh:>14} "
              f"{str(above):>6}  {fam}")

    print(f"\nTraversal provably read exactly once: {tot_excl:,.0f} B = "
          f"{100*tot_excl/B_STEP:.4f}% of B")
    rem = B_STEP - tot_excl
    print(f"Remainder (shares a buffer with another reader): {rem:,.0f} B = "
          f"{100*rem/B_STEP:.4f}% of B = {rem/BW_M5*1e6:.2f} us/step upper bound")

    with open(os.path.join(REPO, "research", "artifacts", "fern-r106g",
                           "family_breakdown.json"), "w") as f:
        json.dump({"B_step": B_STEP,
                   "traversal_provably_read_once": tot_excl,
                   "pct_provably_read_once": 100 * tot_excl / B_STEP,
                   "rows": rows}, f, indent=2)


if __name__ == "__main__":
    main()
