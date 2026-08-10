#!/usr/bin/env python3
"""R106-G Stage 3: legality and editability triage of the nominated fusions.

For every write->read family pair found in Stage 2, print the Rule 77 geometry
of both sides, the dispatches that sit between them (the blocking DAG edges a
fusion would have to absorb), and the Rule 90 editability of the file that
would have to change.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
from roundtrip_census import load_step, B_STEP, BW_M5, DECODE_PCT_PER_US  # noqa: E402

GATE_PCT_B = 1.2


def editable_paths():
    with open(os.path.join(REPO, "benchmark.json")) as f:
        return set(json.load(f)["editablePaths"])


def main():
    step = load_step(os.path.join(REPO, "research", "artifacts", "fern-r106g",
                                  "dispatch_raw.tsv"))
    with open(os.path.join(REPO, "research", "artifacts", "fern-r106g",
                           "roundtrip_census.json")) as f:
        rt = json.load(f)

    by_pair = collections.defaultdict(list)
    for p in rt["stage2_pairs"]:
        by_pair[(p["writer_family"], p["reader_family"])].append(p)

    rows = []
    for x in rt["stage2_table"]:
        key = (x["writer_family"], x["reader_family"])
        ex = by_pair[key][0]
        between = collections.Counter()
        for p in by_pair[key]:
            for j in range(p["writer_i"] + 1, p["reader_i"]):
                between[step[j]["family"]] += 1
        rows.append({**x,
                     "example_writer_i": ex["writer_i"],
                     "example_reader_i": ex["reader_i"],
                     "writer_tgs": ex["writer_tgs"], "reader_tgs": ex["reader_tgs"],
                     "intervening_families": dict(between),
                     "geometry_match": ex["same_geometry"]})

    total = sum(r["bytes_saved_if_fused"] for r in rows)
    print(f"Stage-2 total if EVERY pair fused: {total} B = "
          f"{100*total/B_STEP:.4f}% of B = {total/BW_M5*1e6:.2f} us/step = "
          f"{(total/BW_M5*1e6)*DECODE_PCT_PER_US:.4f}% of cs")
    print(f"Gate: {GATE_PCT_B}% of B = {int(GATE_PCT_B/100*B_STEP)} B. "
          f"Shortfall factor: {GATE_PCT_B/(100*total/B_STEP):.2f}x\n")

    print("--- Stage 3 ranked fusion candidates (Rule 77 geometry) ---")
    for r in rows[:12]:
        print(f"\n[{r['pct_of_B']:.4f}% B | {r['us_per_step']:.2f} us | "
              f"{r['pct_of_cs']:.4f}% cs | n={r['n_pairs']}] "
              f"{r['writer_family']} -> {r['reader_family']}")
        g = r["geometries"][0]
        print(f"    writer grid={g['writer_grid']:>14} group={g['writer_group']:>12} "
              f"tgs={r['writer_tgs']}")
        print(f"    reader grid={g['reader_grid']:>14} group={g['reader_group']:>12} "
              f"tgs={r['reader_tgs']}")
        print(f"    geometry_match={r['geometry_match']}  gap={r['gap_dispatches']}  "
              f"same_encoder={r['same_encoder_pairs']}/{r['n_pairs']}  "
              f"n_geometries={len(r['geometries'])}")
        if r["intervening_families"]:
            print(f"    blocking dispatches between write and read: "
                  f"{r['intervening_families']}")

    with open(os.path.join(REPO, "research", "artifacts", "fern-r106g",
                           "stage3_triage.json"), "w") as f:
        json.dump({"gate_pct_B": GATE_PCT_B, "total_bytes_if_all_fused": total,
                   "total_pct_of_B": 100 * total / B_STEP,
                   "shortfall_factor": GATE_PCT_B / (100 * total / B_STEP),
                   "n_editable_paths": len(editable_paths()),
                   "rows": rows}, f, indent=2)


if __name__ == "__main__":
    main()
