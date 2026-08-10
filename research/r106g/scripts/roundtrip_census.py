#!/usr/bin/env python3
"""R106-G Stage 1b + Stage 2: intra-dispatch broadcast and intermediate round trips.

Stage 1b closes the one hole in the per-range reader map built by read_census.py:
a range read twice *inside a single dispatch* has exactly one reader and is
therefore invisible to that map. Every MLX decode GEMV broadcasts its small
operands to all threadgroups, so the issue-level multiplicity is large; the
question is whether any of those operands is big enough to miss the SLC.

Stage 2 lists, per intermediate tensor, the dispatch that writes it, the
dispatch that reads it, their separation, and -- Rule 77 -- the grid and
threadgroup geometry of both sides of every nominated pair.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "research", "r106c", "scripts"))
import dag_ledger as D  # noqa: E402

B_STEP = 1_671_402_432
BW_M5 = 602.7e9
DECODE_PCT_PER_US = 0.015228
SLC_BYTES = 24 * 1024 * 1024
SMALL = 65536


def threadgroups(r):
    g = [int(x) for x in r["grid"].split("x")]
    t = [int(x) for x in r["group"].split("x")]
    n = 1
    for a, b in zip(g, t):
        n *= -(-a // b)
    return n


def load_step(trace):
    rows = D.load(trace)
    period = D.find_period([r["kernel"] for r in rows])
    step = rows[-period:]
    fams = D.load_families(D.FAMILY_CSV)
    for i, r in enumerate(step):
        r["i"] = i
        r["family"] = D.family_of(r["kernel"], fams) or r["kernel"]
        r["tgs"] = threadgroups(r)
    return step


def stage1b(step):
    """Issue-level multiplicity of broadcast operands, and its SLC exposure."""
    issue = 0
    distinct = set()
    per_family = collections.Counter()
    for r in step:
        outs = set(r["outs"])
        for k in r["ins"]:
            if k in outs or k[2] > SMALL:
                continue
            issue += r["tgs"] * k[2]
            per_family[r["family"]] += r["tgs"] * k[2]
            distinct.add(k)
    dist_bytes = sum(k[2] for k in distinct)
    return {
        "issue_level_read_bytes": issue,
        "issue_level_multiple_of_B": issue / B_STEP,
        "distinct_broadcast_operand_bytes": dist_bytes,
        "distinct_pct_of_B": 100.0 * dist_bytes / B_STEP,
        "largest_broadcast_operand_bytes": max(k[2] for k in distinct),
        "all_broadcast_operands_sub_slc":
            max(k[2] for k in distinct) < SLC_BYTES,
        "resident_working_set_bytes": dist_bytes,
        "by_family": dict(per_family.most_common()),
    }


def stage2(step):
    """Write -> read round trips inside one decode step, with Rule 77 geometry."""
    writes = collections.defaultdict(list)
    reads = collections.defaultdict(list)
    for r in step:
        ins, outs = set(r["ins"]), set(r["outs"])
        for k in outs:
            writes[k].append(r["i"])
        for k in ins - outs:
            reads[k].append(r["i"])

    pairs = []
    for k, ws in writes.items():
        for w in ws:
            nxt = [x for x in reads.get(k, []) if x > w]
            if not nxt:
                continue
            rd = nxt[0]
            a, b = step[w], step[rd]
            pairs.append({
                "bytes": k[2],
                "writer_i": w, "writer_family": a["family"],
                "writer_grid": a["grid"], "writer_group": a["group"],
                "writer_tgs": a["tgs"], "writer_enc": a["enc"],
                "reader_i": rd, "reader_family": b["family"],
                "reader_grid": b["grid"], "reader_group": b["group"],
                "reader_tgs": b["tgs"], "reader_enc": b["enc"],
                "gap_dispatches": rd - w,
                "same_encoder": a["enc"] == b["enc"],
                "same_geometry": a["grid"] == b["grid"] and a["group"] == b["group"],
            })

    roll = collections.defaultdict(lambda: {"n": 0, "bytes": 0, "gaps": set(),
                                            "geom": set(), "same_enc": 0})
    for p in pairs:
        key = (p["writer_family"], p["reader_family"])
        e = roll[key]
        e["n"] += 1
        e["bytes"] += p["bytes"]
        e["gaps"].add(p["gap_dispatches"])
        e["geom"].add((p["writer_grid"], p["writer_group"],
                       p["reader_grid"], p["reader_group"]))
        e["same_enc"] += int(p["same_encoder"])

    table = []
    for (wf, rf), e in roll.items():
        # A fused pair removes both the store and the reload of the tensor.
        saved = 2 * e["bytes"]
        table.append({
            "writer_family": wf, "reader_family": rf,
            "n_pairs": e["n"], "roundtrip_bytes": e["bytes"],
            "bytes_saved_if_fused": saved,
            "pct_of_B": 100.0 * saved / B_STEP,
            "us_per_step": saved / BW_M5 * 1e6,
            "pct_of_cs": (saved / BW_M5 * 1e6) * DECODE_PCT_PER_US,
            "gap_dispatches": sorted(e["gaps"]),
            "same_encoder_pairs": e["same_enc"],
            "geometries": [{"writer_grid": g[0], "writer_group": g[1],
                            "reader_grid": g[2], "reader_group": g[3]}
                           for g in sorted(e["geom"])],
        })
    table.sort(key=lambda x: -x["bytes_saved_if_fused"])
    return pairs, table


def main():
    trace = os.path.join(REPO, "research", "artifacts", "fern-r106g",
                         "dispatch_raw.tsv")
    outdir = os.path.join(REPO, "research", "artifacts", "fern-r106g")
    step = load_step(trace)
    s1b = stage1b(step)
    pairs, table = stage2(step)

    tot = sum(x["bytes_saved_if_fused"] for x in table)
    out = {
        "stage1b_broadcast": s1b,
        "stage2_roundtrip_total_bytes_saved_if_all_fused": tot,
        "stage2_pct_of_B": 100.0 * tot / B_STEP,
        "stage2_us_per_step": tot / BW_M5 * 1e6,
        "stage2_pct_of_cs": (tot / BW_M5 * 1e6) * DECODE_PCT_PER_US,
        "stage2_n_pairs": len(pairs),
        "stage2_table": table,
    }
    with open(os.path.join(outdir, "roundtrip_census.json"), "w") as f:
        json.dump({**out, "stage2_pairs": pairs}, f, indent=2)

    print(json.dumps({k: v for k, v in out.items() if k != "stage2_table"},
                     indent=2))
    print("\n--- Stage 2: write->read round trips, by family pair ---")
    hdr = (f"{'saved B':>10} {'%B':>7} {'us':>6} {'%cs':>7} {'n':>4} {'gap':>10} "
           f"{'enc=':>5}  writer -> reader")
    print(hdr)
    for x in table:
        print(f"{x['bytes_saved_if_fused']:>10} {x['pct_of_B']:>7.4f} "
              f"{x['us_per_step']:>6.2f} {x['pct_of_cs']:>7.4f} {x['n_pairs']:>4} "
              f"{str(x['gap_dispatches'])[:10]:>10} {x['same_encoder_pairs']:>5}  "
              f"{x['writer_family']} -> {x['reader_family']}")


if __name__ == "__main__":
    main()
