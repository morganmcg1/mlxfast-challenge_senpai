#!/usr/bin/env python3
"""R96-C Stage 1: cross-artifact ladder pricing and round-trip certification.

Research-only. Reads the census artifacts written by fern_r96_dense_census.py,
prints the best design for each tensor in each orientation, and then really
encodes/decodes three implementation rungs so the advisor gets a certified
bytes-per-step number for each, not just an analytic one.

Usage: python3 research/fern_r96_summarise.py [weights_dir] [--wandb]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fern_r96_dense_census import BASE_BYTES, TENSORS, load_bf16, roundtrip  # noqa: E402

PRICE = 0.015224  # % score per MB/step removed (PR #110 realised ledger)
M4_BYTES_PER_S = 266.3e9

# rung -> per-tensor (blocked_along_output_axis, block, d, m); m=7 forced by tzm=0
LADDER = {
    "R0_escape_free_natural": {
        "gate_proj": (False, "row", 5, 7),
        "up_proj": (False, "row", 5, 7),
        "down_proj": (False, "row", 6, 7),
    },
    "R1_per_tensor_natural": {
        "gate_proj": (False, "128", 4, 7),
        "up_proj": (False, "128", 4, 7),
        "down_proj": (False, "row", 6, 7),
    },
    "R2_mixed_axis": {
        "gate_proj": (False, "128", 4, 7),
        "up_proj": (False, "128", 4, 7),
        "down_proj": (True, "32", 4, 7),
    },
}


def best(rec, strided):
    """Best (block, d, design) for one orientation of one tensor, m=7."""
    out = []
    unit = 64 if strided else 2
    n, shape = rec["n"], rec["shape"]
    for bk in ("32", "64", "128", "row"):
        key = str(shape[1]) if bk == "row" else bk
        s = rec["spans"][key]
        nb = s["blocks"]
        for d in (2, 3, 4, 5, 6):
            e = s[f"esc_d{d}"]
            core = n * (1 + d + 7) // 8 + nb
            for design, net in (("l", core + e["line_bytes"]),
                                ("b", core + e["rows_with_esc"] * shape[1] * unit)):
                out.append((n * 2 - net, bk, d, design, net, e["blocks"], nb))
    out.sort(reverse=True)
    return out[0]


def price(saved):
    return f"saved={saved/1e6:7.3f} MB  {saved/1e6*PRICE:7.4f}%  {saved/M4_BYTES_PER_S*1e6:6.1f} us"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    weights = Path(args[0]) if args else Path("weights")
    use_wandb = "--wandb" in sys.argv

    mixed = json.loads(Path("research/artifacts/fern_r96_dense_census_mixed.json").read_text())
    red_key, out_key = ("per_tensor", "alt_tensor") if mixed["base_axis"] == "reduction" \
        else ("alt_tensor", "per_tensor")

    print("=" * 100)
    print("A  best design per tensor per orientation (m=7 forced by tzm=0)")
    print("=" * 100)
    red_only = 0
    for name in TENSORS:
        br = best(mixed[red_key][name], False)
        bo = best(mixed[out_key][name], True)
        red_only += br[0]
        print(f"\n{name.split('.')[-2]}:  checkpoint shape {mixed[red_key][name]['shape']}")
        for label, r in (("reduction-axis", br), ("output-axis   ", bo)):
            print(f"  {label} best: {price(r[0])}  B={r[1]:>4} d={r[2]} design={r[3]} "
                  f"net={r[4]} esc={r[5]}/{r[6]} ({r[5]/r[6]*100:.4f}%)")
    print(f"\nreduction-axis-only per-tensor total: {price(red_only)}")

    print("\n" + "=" * 100)
    print("B  round-trip certification of the implementation ladder")
    print("=" * 100)
    cache = {}
    rows = []
    for rung, spec in LADDER.items():
        net = mismatch = 0
        detail = {}
        for name in TENSORS:
            short = name.split(".")[-2]
            axis0, bk, d, m = spec[short]
            if name not in cache:
                cache[name] = load_bf16(weights, name)
            u = np.ascontiguousarray(cache[name].T) if axis0 else cache[name]
            block = u.shape[1] if bk == "row" else int(bk)
            recon, st = roundtrip(u, block, d, m, False, strided=axis0)
            bad = int((recon != u).sum())
            h0 = hashlib.sha256(np.ascontiguousarray(u, dtype="<u2").tobytes()).hexdigest()
            h1 = hashlib.sha256(np.ascontiguousarray(recon, dtype="<u2").tobytes()).hexdigest()
            net += st["plane_bytes_line"]
            mismatch += bad
            detail[short] = dict(axis="output" if axis0 else "reduction", block=bk, d=d, m=m,
                                 bytes=st["plane_bytes_line"], mismatched=bad,
                                 hash_equal=h0 == h1, escaped_blocks=st["escaped_blocks"],
                                 total_blocks=st["total_blocks"])
            print(f"  {rung:24s} {short:9s} axis={detail[short]['axis']:9s} B={bk:>4} d={d} m={m}  "
                  f"bytes={st['plane_bytes_line']:9d}  "
                  f"esc={st['escaped_blocks']:6d}/{st['total_blocks']:<7d}  "
                  f"mismatched={bad}  sha_equal={h0 == h1}")
            del u, recon
        saved = BASE_BYTES - net
        rows.append(dict(rung=rung, net_bytes=net, saved_bytes=saved,
                         saved_MB=round(saved / 1e6, 3),
                         score_pct=round(saved / 1e6 * PRICE, 4),
                         us_M4=round(saved / M4_BYTES_PER_S * 1e6, 1),
                         mismatched=mismatch, bar_pass=saved >= 21_300_000, detail=detail))
        print(f"  {rung:24s} TOTAL net={net}  {price(saved)}  mismatched={mismatch}  "
              f"bar={'PASS' if saved >= 21_300_000 else 'FAIL'}\n")

    dest = Path("research/artifacts/fern_r96_ladder.json")
    dest.write_text(json.dumps(dict(base_bytes=BASE_BYTES, ladder=rows,
                                    reduction_only_saved=int(red_only)), indent=1))
    print(f"wrote {dest}")

    if use_wandb:
        import wandb
        run = wandb.init(project="mlxfast-maple", entity="wandb-applied-ai-team",
                         name="fern-r96c-stage1-ladder-certification", job_type="census",
                         config=dict(assignment="maple-r96-c-bf16-lossless-compaction",
                                     revision="r96-c-rev1", stage=1,
                                     base_sha="43036cd39dd3c795b117b099f0fe52767fbedbca",
                                     host="M4 Pro"))
        table = wandb.Table(columns=["rung", "net_bytes", "saved_MB", "score_pct", "us_M4",
                                     "mismatched", "bar_pass"])
        best_net = min(r["net_bytes"] for r in rows)
        log = {
            "dense_mlp_bytes_per_step": int(best_net),
            "dense_mlp_bytes_per_step_baseline": BASE_BYTES,
            "stage1_net_bytes_saved": int(BASE_BYTES - best_net),
            "stage1_net_score_pct": float((BASE_BYTES - best_net) / 1e6 * PRICE),
            "roundtrip_mismatched_weights": int(sum(r["mismatched"] for r in rows)),
            "stage1_reduction_only_saved_bytes": int(red_only),
        }
        for r in rows:
            table.add_data(r["rung"], r["net_bytes"], r["saved_MB"], r["score_pct"],
                           r["us_M4"], r["mismatched"], r["bar_pass"])
            for k in ("net_bytes", "saved_bytes", "score_pct", "us_M4", "mismatched"):
                log[f"ladder_{r['rung']}_{k}"] = r[k]
            log[f"ladder_{r['rung']}_bar_pass"] = int(r["bar_pass"])
            log[f"ladder_{r['rung']}_escape_block_fraction"] = float(
                sum(v["escaped_blocks"] for v in r["detail"].values())
                / sum(v["total_blocks"] for v in r["detail"].values()))
        log["stage1_escape_block_fraction"] = log["ladder_R2_mixed_axis_escape_block_fraction"]
        log["ladder"] = table
        run.log(log)
        art = wandb.Artifact("fern_r96_ladder", type="census")
        art.add_file(str(dest))
        run.log_artifact(art)
        print(f"W&B run: {run.url}  id={run.id}")
        run.finish()

    return 0 if all(r["mismatched"] == 0 for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
