#!/usr/bin/env python3
"""Reduce an Arm G split-profile block to one machine-readable JSON summary.

Parses the `.prof` files written by `research/nezuko_armg_split_profile.sh` so
that the W&B run, `research/nezuko-r109-armg-result.md` and
`research/nezuko-r109-terminal-result.md` cannot disagree about the numbers.

Pass 1 (`split1-<arm>.prof`) carries the de-nested per-kernel busy attribution
and the per-step wall/gap. Pass 2 (`split0-<arm>.prof`) carries the shipped-shape
wall, and its sibling `split0-<arm>.err.gz` carries the GPUBARRIER census that
`research/nezuko_r109_barrier_period.py` reduces to a per-step barrier count.

Usage: nezuko_r109_profile_summary.py RUN_DIR [--barriers ARM=N ...] [-o OUT]
"""
import argparse
import json
import pathlib
import re

STEP_RE = re.compile(
    r"per steady step: wall=(?P<wall>[\d.]+) ms "
    r"gpu_busy_sum=(?P<sum>[\d.]+) ms "
    r"gpu_busy_union=(?P<union>[\d.]+) ms "
    r"gap=(?P<gap>[\d.]+) ms \((?P<gap_pct>[\d.]+)% of wall\) "
    r"cbs=(?P<cbs>[\d.]+) dispatches=(?P<disp>[\d.]+)"
)
KERNEL_RE = re.compile(
    r"^\s*(?P<us>[\d.]+)\s+(?P<share>[\d.]+)%\s+"
    r"(?P<n>[\d.]+)\s+(?P<per>[\d.]+)\s+(?P<kernel>\S+)\s*$"
)
DECODE_RE = re.compile(
    r"decode steps=(?P<steps>\d+) mean=(?P<mean>[\d.]+) ms "
    r"median=(?P<median>[\d.]+) ms"
)
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (?P<n>\d+) divergences")

# Kernel families whose totals are the object of the arm.
FAMILIES = {
    "rmsbfloat16": lambda k: k == "rmsbfloat16",
    "gate_sp": lambda k: k.startswith("gate_sp_") or "gate_sp_rms_" in k,
    "qkv": lambda k: k.startswith("decode_nvfp4_qkv_"),
    "oproj": lambda k: k.startswith("oproj_act_h"),
}


def parse_prof(path):
    text = path.read_text(errors="replace")
    out = {"path": path.name, "kernels": {}}
    m = STEP_RE.search(text)
    if m:
        out["wall_us"] = float(m["wall"]) * 1000.0
        out["busy_sum_us"] = float(m["sum"]) * 1000.0
        out["busy_union_us"] = float(m["union"]) * 1000.0
        out["gap_us"] = float(m["gap"]) * 1000.0
        out["gap_pct"] = float(m["gap_pct"])
        out["cbs_per_step"] = float(m["cbs"])
        out["dispatches_per_step"] = float(m["disp"])
        out["sum_over_union"] = out["busy_sum_us"] / out["busy_union_us"]
    m = DECODE_RE.search(text)
    if m:
        out["probe_steps"] = int(m["steps"])
        out["probe_median_ms"] = float(m["median"])
    m = DIVERGE_RE.search(text)
    if m:
        out["divergences"] = int(m["n"])
    for line in text.splitlines():
        km = KERNEL_RE.match(line)
        if not km:
            continue
        out["kernels"][km["kernel"]] = {
            "us_per_step": float(km["us"]),
            "n_per_step": float(km["n"]),
            "us_per_call": float(km["per"]),
        }
    fam = {}
    for name, pred in FAMILIES.items():
        hits = {k: v for k, v in out["kernels"].items() if pred(k)}
        if hits:
            fam[name] = {
                "us_per_step": round(sum(v["us_per_step"] for v in hits.values()), 2),
                "n_per_step": round(sum(v["n_per_step"] for v in hits.values()), 2),
                "kernels": sorted(hits),
            }
    out["families"] = fam
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument(
        "--barriers",
        action="append",
        default=[],
        metavar="ARM=N",
        help="per-step barrier count from nezuko_r109_barrier_period.py",
    )
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    run_dir = pathlib.Path(args.run_dir)
    barriers = {}
    for tok in args.barriers:
        arm, _, n = tok.partition("=")
        barriers[arm] = int(n)

    arms = sorted({p.name.split("-", 1)[1].split(".")[0] for p in run_dir.glob("split*-*.prof")})
    out = {"run_dir": str(run_dir), "arms": {}}
    for arm in arms:
        rec = {}
        for tag, prefix in (("split1", "split1"), ("split0", "split0")):
            p = run_dir / f"{prefix}-{arm}.prof"
            if p.exists():
                rec[tag] = parse_prof(p)
        if arm in barriers:
            rec["barriers_per_step"] = barriers[arm]
        out["arms"][arm] = rec

    # Derived contrasts against the shipped control, arm A.
    if "A" in out["arms"]:
        a = out["arms"]["A"]
        for arm, rec in out["arms"].items():
            if arm == "A" or "split1" not in rec or "split1" not in a:
                continue
            def fam_us(r, name):
                return r["split1"]["families"].get(name, {}).get("us_per_step", 0.0)

            # The arm only touches these two families; every other kernel is
            # untouched, so the *targeted* saving is the honest attribution and
            # the whole-step busy_sum delta is dominated by run-to-run drift.
            targeted_a = fam_us(a, "rmsbfloat16") + fam_us(a, "gate_sp")
            targeted_x = fam_us(rec, "rmsbfloat16") + fam_us(rec, "gate_sp")
            rec["vs_A"] = {
                "targeted_busy_saved_us": round(targeted_a - targeted_x, 1),
                "targeted_busy_us_A": round(targeted_a, 1),
                "targeted_busy_us_arm": round(targeted_x, 1),
                "busy_sum_delta_us": round(
                    a["split1"]["busy_sum_us"] - rec["split1"]["busy_sum_us"], 1
                ),
                "dispatch_delta": rec["split1"]["dispatches_per_step"]
                - a["split1"]["dispatches_per_step"],
                "barrier_delta": (
                    rec.get("barriers_per_step", 0) - a.get("barriers_per_step", 0)
                    if "barriers_per_step" in rec and "barriers_per_step" in a
                    else None
                ),
                "split0_wall_delta_us": (
                    round(a["split0"]["wall_us"] - rec["split0"]["wall_us"], 1)
                    if "split0" in a and "split0" in rec
                    else None
                ),
            }

    blob = json.dumps(out, indent=2, sort_keys=True)
    if args.out:
        pathlib.Path(args.out).write_text(blob + "\n")
        print(f"wrote {args.out}")
    else:
        print(blob)


if __name__ == "__main__":
    main()
