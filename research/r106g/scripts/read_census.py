#!/usr/bin/env python3
"""R106-G redundant-read census.

Extends the R106-C byte-range DAG (research/r106c/scripts/dag_ledger.py, imported
as a module per Rule 58/83) to answer: which bytes does one decode step read more
than once, by which dispatch pairs, and which of those pairs could legally fuse?

Two granularities are reported and MUST NOT be conflated:

  * BINDING extent  -- what the tracer records. `note_in_buf` stores
    `a.data_size() * a.itemsize()`, the whole array, not the bytes the kernel
    touches. A routed MoE dispatch binds all 256 experts (268 MB) and reads 8.
  * TRAVERSAL bytes -- what DRAM actually moves. Taken from the accepted
    per-family census (fern-r105d / tanjiro-r106a), B = 1,671,402,432 B/step.

The headline ratio is only meaningful at traversal granularity.

Usage: read_census.py [trace.tsv] [out-dir]
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "r106c",
        "scripts",
    ),
)
import dag_ledger as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

# Accepted decode-step byte total (fern-r105d decode-byte-census.json:step_bytes).
B_STEP = 1_671_402_432
# M5 projected pattern ceiling used by 105-E; names the floor we price against.
BW_M5 = 602.7e9
US_PER_PCT_B = (0.01 * B_STEP / BW_M5) * 1e6  # us/step per 1 % of B
DECODE_PCT_PER_US = 0.015228                   # % of cs per us/step
# 105-E rule (k): buffers above the ~24 MiB SLC show amplification exactly 1.00;
# re-reads of sub-SLC buffers are cache hits, not DRAM traversals.
SLC_BYTES = 24 * 1024 * 1024
# Stage-3 gate from the assignment.
GATE_PCT_B = 1.2


def per_call_traversal():
    """Accepted DRAM traversal per dispatch, by family (fern-r105d census)."""
    path = os.path.join(REPO, "research", "artifacts", "fern-r105d",
                        "decode-byte-census.json")
    with open(path) as f:
        cen = json.load(f)
    assert cen["step_bytes"] == B_STEP, cen["step_bytes"]
    return {x["family"]: x["bytes_per_step"] / x["calls"] for x in cen["families"]}


def reads_writes(r):
    """Split a dispatch's bound ranges into true reads, writes and RMW.

    device.cpp:330-336 -- set_output_array() calls set_input_array() first, so
    every output also appears in the `ins` column. A range appearing on both
    sides is a read-modify-write (e.g. residual accumulate), not a pure read.
    """
    ins, outs = set(r["ins"]), set(r["outs"])
    return ins - outs, outs, ins & outs


def main():
    trace = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, "research", "artifacts", "fern-r106g", "dispatch_raw.tsv"
    )
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        REPO, "research", "artifacts", "fern-r106g"
    )
    os.makedirs(outdir, exist_ok=True)

    rows = D.load(trace)
    period = D.find_period([r["kernel"] for r in rows])
    step = rows[-period:]

    fams = D.load_families(D.FAMILY_CSV)
    for i, r in enumerate(step):
        r["i"] = i
        r["family"] = D.family_of(r["kernel"], fams) or r["kernel"]

    # ---- Stage 1: per-range reader map ------------------------------------
    readers = defaultdict(list)   # range -> [dispatch idx]
    writers = defaultdict(list)
    rmw = defaultdict(list)
    for r in step:
        rd, wr, both = reads_writes(r)
        for x in rd:
            readers[x].append(r["i"])
        for x in wr:
            writers[x].append(r["i"])
        for x in both:
            rmw[x].append(r["i"])

    # Per-buffer (pointer) rollup: a buffer is the allocation MLX tracks.
    buf_size = {}
    buf_readers = defaultdict(set)
    buf_writers = defaultdict(set)
    buf_read_fams = defaultdict(set)
    for (p, o, s), who in readers.items():
        buf_size[p] = max(buf_size.get(p, 0), o + s)
        buf_readers[p].update(who)
        for i in who:
            buf_read_fams[p].add(step[i]["family"])
    for (p, o, s), who in writers.items():
        buf_size[p] = max(buf_size.get(p, 0), o + s)
        buf_writers[p].update(who)

    total_bound_read = sum(s * len(who) for (p, o, s), who in readers.items())
    distinct_bound = sum(s for (p, o, s) in readers)

    buffers = []
    for p in sorted(buf_size, key=lambda q: -buf_size[q]):
        nread = len(buf_readers[p])
        if nread == 0:
            continue
        buffers.append({
            "ptr": p,
            "bytes": buf_size[p],
            "n_reading_dispatches": nread,
            "n_writing_dispatches": len(buf_writers[p]),
            "families": sorted(buf_read_fams[p]),
            "immutable": len(buf_writers[p]) == 0,
            "above_slc": buf_size[p] > SLC_BYTES,
        })

    # ---- Stage 2: intermediates (written then read inside the step) --------
    inter = [b for b in buffers if not b["immutable"]]
    intermediates = []
    for b in inter:
        p = b["ptr"]
        w = sorted(buf_writers[p])
        rd = sorted(buf_readers[p])
        pairs = []
        for wi in w:
            nxt = [x for x in rd if x > wi]
            if nxt:
                ri = nxt[0]
                pairs.append({
                    "writer": wi, "writer_family": step[wi]["family"],
                    "writer_grid": step[wi]["grid"], "writer_group": step[wi]["group"],
                    "reader": ri, "reader_family": step[ri]["family"],
                    "reader_grid": step[ri]["grid"], "reader_group": step[ri]["group"],
                    "gap_dispatches": ri - wi,
                    "same_geometry": (step[wi]["grid"] == step[ri]["grid"]
                                      and step[wi]["group"] == step[ri]["group"]),
                })
        intermediates.append({**b, "pairs": pairs})

    # ---- Stage 1 headline: traversal-granularity redundancy bound ---------
    # A byte can be read twice only if it is BOUND twice, so binding-level
    # single-reader buffers have traversal multiplicity exactly 1. For a buffer
    # with readers R, the redundant traversal is at most the sum of every
    # reader's contribution except the largest, and each contribution is capped
    # both by the buffer extent and by that dispatch's whole per-call traversal
    # budget from the accepted per-family census.
    percall = per_call_traversal()
    redundant_bound = 0
    red_rows = []
    for (p, o, s), who in readers.items():
        if len(who) < 2:
            continue
        caps = sorted((min(s, percall.get(step[i]["family"], s)), i) for i in who)
        extra = sum(c for c, _ in caps[:-1])
        redundant_bound += extra
        red_rows.append({
            "ptr": p, "offset": o, "bytes": s,
            "readers": [{"i": i, "family": step[i]["family"],
                         "grid": step[i]["grid"], "group": step[i]["group"],
                         "per_call_traversal_cap": c} for c, i in caps],
            "redundant_bound_bytes": extra,
            "above_slc": s > SLC_BYTES,
        })
    red_rows.sort(key=lambda x: -x["redundant_bound_bytes"])
    red_above = sum(x["redundant_bound_bytes"] for x in red_rows if x["above_slc"])

    # ---- redundancy classification ----------------------------------------
    multi = [b for b in buffers if b["n_reading_dispatches"] > 1]
    multi_above = [b for b in multi if b["above_slc"]]
    multi_below = [b for b in multi if not b["above_slc"]]

    summary = {
        "period_dispatches": period,
        "command_buffers": len(set(r["enc"] for r in step)),
        "observed_barriers": sum(r["barrier"] for r in step),
        "B_step": B_STEP,
        "us_per_pct_B": US_PER_PCT_B,
        "pct_cs_per_pct_B": US_PER_PCT_B * DECODE_PCT_PER_US,
        "gate_pct_B": GATE_PCT_B,
        "gate_bytes": GATE_PCT_B / 100.0 * B_STEP,
        "binding": {
            "total_bytes_read_with_multiplicity": total_bound_read,
            "distinct_bytes_touched": distinct_bound,
            "ratio": total_bound_read / distinct_bound if distinct_bound else 0.0,
            "n_distinct_ranges": len(readers),
            "n_ranges_read_more_than_once": sum(1 for v in readers.values() if len(v) > 1),
            "n_buffers": len(buffers),
        },
        "traversal": {
            "distinct_bytes_traversed": B_STEP,
            "redundant_bytes_upper_bound": redundant_bound,
            "redundant_upper_bound_above_slc": red_above,
            "ratio_upper_bound": (B_STEP + redundant_bound) / B_STEP,
            "ratio_upper_bound_dram_only": (B_STEP + red_above) / B_STEP,
            "redundant_pct_of_B": 100.0 * redundant_bound / B_STEP,
            "redundant_us_per_step": redundant_bound / BW_M5 * 1e6,
            "redundant_pct_of_cs": (redundant_bound / BW_M5 * 1e6) * DECODE_PCT_PER_US,
            "clears_gate": 100.0 * redundant_bound / B_STEP >= GATE_PCT_B,
        },
        "buffers_multi_read": {
            "n": len(multi),
            "n_above_slc": len(multi_above),
            "n_below_slc": len(multi_below),
            "bytes_above_slc": sum(b["bytes"] for b in multi_above),
            "bytes_below_slc": sum(b["bytes"] for b in multi_below),
        },
        "intermediates": {
            "n_buffers": len(inter),
            "bytes": sum(b["bytes"] for b in inter),
            "n_above_slc": sum(1 for b in inter if b["above_slc"]),
            "bytes_above_slc": sum(b["bytes"] for b in inter if b["above_slc"]),
        },
        "slc_bytes": SLC_BYTES,
    }

    with open(os.path.join(outdir, "read_census.json"), "w") as f:
        json.dump({"summary": summary, "buffers": buffers,
                   "intermediates": intermediates,
                   "redundant_ranges": red_rows}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print("\n--- top redundant ranges (traversal upper bound) ---")
    for x in red_rows[:15]:
        who = " + ".join(f"{r['family']}[{r['i']}]" for r in x["readers"])
        print(f"{x['redundant_bound_bytes']:>10} B  ({100*x['redundant_bound_bytes']/B_STEP:6.4f}% B)"
              f"  extent={x['bytes']:>10}  {who[:95]}")


if __name__ == "__main__":
    main()
