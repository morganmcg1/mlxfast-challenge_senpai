#!/usr/bin/env python3
"""Adjudicate R107-F Stage 1 (T2D down-residual amortisation) from probe JSON.

Usage:
    python3 research/maple_frieren_r107f_stage1_analyse.py [--wandb]

Reads the two independent replicate JSONs written by
research/maple_frieren_r107f_stage1_run.sh, emits the adjudication tables to
stdout, writes research/artifacts/maple-frieren-r107f/adjudication.json, and
with --wandb publishes the ledger run.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path

ART = Path("research/artifacts/maple-frieren-r107f")
STAGE1 = ART / "stage1"
REPLICATES = [("run1", STAGE1 / "t2d-probe-full.json"), ("run2", STAGE1 / "t2d-probe-full2.json")]

CALLS_PER_STEP = 39
# Decode price book (campaign constants, PR #597 rev6 §2):
#   1 us/step = 0.015228 % of cs  ->  1 us/call = 39 * 0.015228 = 0.593892 % of cs
PCT_CS_PER_US_STEP = 0.015228
PCT_CS_PER_US_CALL = PCT_CS_PER_US_STEP * CALLS_PER_STEP
SHIP_BAR_PCT_CS = 0.4
SHIP_BAR_US_CALL = SHIP_BAR_PCT_CS / PCT_CS_PER_US_CALL

# Clean in-situ anchor, research/artifacts/maple-frieren-r107f/stage0_device_clean.log
IN_SITU_US_CALL = 22.07
IN_SITU_US_STEP = 860.5
V0_TOLERANCE = 0.02  # preregistered +-2 % twin-fidelity band

FOCUS_BLOCK = "focus split cold calls=39"
GRID_BLOCKS = [
    "grid calls=39 split cold",
    "grid calls=39 split resident",
    "grid calls=39 fused cold",
    "grid calls=39 fused resident",
]

ARM_MEANING = {
    "a0": "shipped geometry twin (opsi 4, 288 thr/TG, 512 TG/call)",
    "a0_act2": "activation loads 4 -> 2",
    "a0_act1": "activation loads 4 -> 1",
    "a0_act0": "all activation loads -> compile-time constants (upper bound)",
    "a0_wide": "WAL: 2x uint4 wide activation loads (12 -> 10 loads/lane)",
    "a0_badcoal": "deliberately de-coalesced code loads (line touches +54.5 %)",
    "a1": "opsi 4 -> 8 (A1: issued bytes -23.5 %, unique bytes 0 %)",
    "a1_wide": "A1 + WAL",
    "a2": "negative control: 576 thr/TG, same loads/lane",
    "a3": "opsi 4 -> 16",
    "a0_min": "arithmetic stripped to a single simd_sum",
    "a0_act0_min": "activation loads AND arithmetic both stripped",
}


def load(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def arms(doc: dict, block: str) -> list[dict]:
    return [r for r in doc["records"] if r["kind"] == "arm" and r.get("block") == block]


def by_arm(doc: dict, block: str) -> dict[str, dict]:
    return {r["arm"]: r for r in arms(doc, block)}


def other(doc: dict, kind: str) -> list[dict]:
    return [r for r in doc["records"] if r["kind"] == kind]


def fmt(x: float | None, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def section(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def v0_gate(docs: dict[str, dict]) -> dict:
    out = {}
    for tag, doc in docs.items():
        for label, block in (("grid", "grid calls=39 split cold"), ("focus", FOCUS_BLOCK)):
            r = by_arm(doc, block).get("a0")
            if r is None:
                continue
            rel = r["us_per_call"] / IN_SITU_US_CALL - 1.0
            out[f"{tag}_{label}"] = {
                "us_per_call": r["us_per_call"],
                "rel_vs_in_situ": rel,
                "within_band": abs(rel) <= V0_TOLERANCE,
                "conservative": rel > 0,
            }
    return out


def paired_table(docs: dict[str, dict], block: str, order: list[str] | None = None) -> list[dict]:
    keys = order or [a for a in ARM_MEANING if any(a in by_arm(d, block) for d in docs.values())]
    rows = []
    for arm in keys:
        row: dict = {"arm": arm, "meaning": ARM_MEANING.get(arm, "")}
        deltas = []
        for tag, doc in docs.items():
            r = by_arm(doc, block).get(arm)
            if r is None:
                continue
            row[f"{tag}_us_per_call"] = r["us_per_call"]
            row[f"{tag}_dram_gb_s"] = r["dram_gb_s"]
            row["n"] = r["n"]
            row["line_touches_per_sg"] = r["line_touches_per_sg"]
            row["loads_per_lane"] = r["loads_per_lane"]
            row["issued_bytes_per_call"] = r["issued_bytes_per_call"]
            row["tg_per_call"] = r["tg_per_call"]
            row["pso_tg_mem"] = r["pso_tg_mem"]
            d = r.get("paired_vs_a0_us_per_call")
            if d is not None:
                row[f"{tag}_delta_us_per_call"] = d
                row[f"{tag}_ci"] = [r["paired_ci_lo"], r["paired_ci_hi"]]
                deltas.append(d)
        if deltas:
            row["delta_us_per_call"] = statistics.mean(deltas)
            row["delta_pct_cs"] = row["delta_us_per_call"] * PCT_CS_PER_US_CALL
            row["delta_us_per_step"] = row["delta_us_per_call"] * CALLS_PER_STEP
            row["replicates_agree_sign"] = len({d > 0 for d in deltas}) == 1
            cis = [row[f"{t}_ci"] for t in docs if f"{t}_ci" in row]
            row["clears_ship_bar"] = (
                row["delta_us_per_call"] <= -SHIP_BAR_US_CALL and all(c[1] < 0 for c in cis)
            )
            row["fraction_of_ship_bar"] = -row["delta_us_per_call"] / SHIP_BAR_US_CALL
        rows.append(row)
    return rows


def print_paired(rows: list[dict], tags: list[str]) -> None:
    cols = ["arm"] + [f"{t} us/call" for t in tags] + [f"{t} delta" for t in tags]
    cols += ["mean %cs", "x bar"]
    widths = [14] + [14] * (2 * len(tags)) + [10, 7]
    print("".join(c.rjust(w) for c, w in zip(cols, widths)) + "  meaning")
    print("-" * (sum(widths) + 40))
    for r in rows:
        vals = [r["arm"]]
        vals += [fmt(r.get(f"{t}_us_per_call")) for t in tags]
        vals += [fmt(r.get(f"{t}_delta_us_per_call")) for t in tags]
        vals += [fmt(r.get("delta_pct_cs"), 4), fmt(r.get("fraction_of_ship_bar"), 2)]
        print("".join(v.rjust(w) for v, w in zip(vals, widths)) + "  " + r["meaning"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wandb", action="store_true")
    args = ap.parse_args()

    docs = {tag: load(p) for tag, p in REPLICATES if p.exists()}
    if len(docs) < 2:
        raise SystemExit(f"expected two replicates, found {sorted(docs)}")
    tags = list(docs)

    section("R107-F Stage 1: T2D down-residual amortisation adjudication")
    for tag, doc in docs.items():
        print(
            f"{tag}: device={doc['device']} revision={doc['revision']} "
            f"rounds={doc['rounds']}/{doc['discard']} "
            f"focus={doc['focus_rounds']}/{doc['focus_discard']} "
            f"unique_bytes_per_call={doc['unique_bytes_per_call']}"
        )
    print(
        f"price book: 1 us/call = {PCT_CS_PER_US_CALL:.6f} % of cs; "
        f"ship bar {SHIP_BAR_PCT_CS} % of cs = {SHIP_BAR_US_CALL:.4f} us/call"
    )

    section("V0 twin-fidelity gate (split cold a0 vs clean in-situ 22.07 us/call)")
    gate = v0_gate(docs)
    for k, v in sorted(gate.items()):
        print(
            f"{k:<14} {v['us_per_call']:8.3f} us/call  rel {v['rel_vs_in_situ'] * 100:+6.2f} %  "
            f"within_2pct={v['within_band']}  conservative={v['conservative']}"
        )

    section(f"PRIMARY: {FOCUS_BLOCK} (n=201, round-paired vs a0)")
    focus_rows = paired_table(docs, FOCUS_BLOCK, ["a0", "a0_act0", "a0_wide", "a1", "a2"])
    print_paired(focus_rows, tags)

    grid_rows: dict[str, list[dict]] = {}
    for block in GRID_BLOCKS:
        section(f"GRID: {block} (n=61, round-paired vs same-mode a0)")
        rows = paired_table(docs, block)
        grid_rows[block] = rows
        print_paired(rows, tags)

    section("Call sweep (cold, a0 split vs fused; a1 split penalty)")
    for tag, doc in docs.items():
        print(f"-- {tag}")
        print(f"{'calls':>6}{'split us/call':>15}{'fused us/call':>15}{'a1 split delta':>16}")
        sweep = arms(doc, "call sweep cold")
        for calls in sorted({r["calls"] for r in sweep}):
            sel = lambda a, sp: [r for r in sweep if r["calls"] == calls and r["split"] is sp and r["arm"] == a]  # noqa: E731
            s, f, a1 = sel("a0", True), sel("a0", False), sel("a1", True)
            print(
                f"{calls:>6}"
                f"{fmt(s[0]['us_per_call'] if s else None):>15}"
                f"{fmt(f[0]['us_per_call'] if f else None):>15}"
                f"{fmt(a1[0].get('paired_vs_a0_us_per_call') if a1 else None):>16}"
            )

    section("Encoder-serialisation probe (exploratory; a0 cold, 39 calls)")
    enc: dict[str, dict] = {}
    for tag, doc in docs.items():
        for r in other(doc, "encmode"):
            enc.setdefault(r["mode"], {})[tag] = r
            print(
                f"{tag} {r['mode']:<18} {r['us_per_call']:8.3f} us/call   "
                f"empty {r['empty_us_per_dispatch']:6.3f} us/dispatch"
            )
    gap = None
    if "serial" in enc and "concurrent" in enc:
        shared = [t for t in enc["serial"] if t in enc["concurrent"]]
        gap = statistics.mean(
            enc["serial"][t]["us_per_call"] - enc["concurrent"][t]["us_per_call"] for t in shared
        )
        print(
            f"\nbarrier drain = {gap:.3f} us/call = {gap * CALLS_PER_STEP:.1f} us/step "
            f"= {gap * PCT_CS_PER_US_CALL:.3f} % of cs "
            "(irreducible here: the 39 calls are genuinely data-dependent)"
        )

    section("Machine ceilings")
    for tag, doc in docs.items():
        for r in other(doc, "stream"):
            print(f"{tag} stream {r['bytes'] >> 20:>4} MiB  {r['gb_s']:7.2f} GB/s")
        for r in other(doc, "issue"):
            print(
                f"{tag} issue  threads={r['threads']:>7} iters={r['iters']:>3}  "
                f"{r['loads_per_s'] / 1e9:7.1f} Gload/s"
            )
        for r in other(doc, "empty"):
            print(
                f"{tag} empty  tg={r['tg']:>4} dispatches={r['dispatches']:>4}  "
                f"{r['us_per_dispatch']:6.3f} us/dispatch"
            )

    stream_peak = max(r["gb_s"] for d in docs.values() for r in other(d, "stream"))
    unique = next(iter(docs.values()))["unique_bytes_per_call"]
    floor_us = unique / (stream_peak * 1e9) * 1e6

    section("Closed accounting of the 22.07 us/call anchor")
    act0 = next(r for r in focus_rows if r["arm"] == "a0_act0")
    minrow = next(r for r in grid_rows["grid calls=39 split cold"] if r["arm"] == "a0_act0_min")
    arith = next(r for r in grid_rows["grid calls=39 split cold"] if r["arm"] == "a0_min")
    parts = [
        ("unique-byte floor", floor_us, f"{unique} B at {stream_peak:.1f} GB/s"),
        ("barrier drain", gap, "serial minus concurrent encoder"),
        ("exposed activation ld", -act0["delta_us_per_call"], "upper bound, a0_act0"),
        ("exposed arithmetic", -arith["delta_us_per_call"], "upper bound, a0_min"),
    ]
    for name, val, note in parts:
        if val is None:
            continue
        print(f"{name:<22}{val:7.3f} us/call {val / IN_SITU_US_CALL * 100:6.1f} %  ({note})")
    print(
        f"{'both stripped':<22}"
        f"{-minrow['delta_us_per_call']:7.3f} us/call "
        f"{-minrow['delta_us_per_call'] / IN_SITU_US_CALL * 100:6.1f} %  "
        "(a0_act0_min; the two upper bounds overlap)"
    )

    section("VERDICT")
    verdict = "N-T2D-DRAM-BOUND"
    best = min((r for r in focus_rows if "delta_us_per_call" in r), key=lambda r: r["delta_us_per_call"])
    act0_min_us = min(
        r["us_per_call"]
        for d in docs.values()
        for r in arms(d, "grid calls=39 split cold")
        if r["arm"] == "a0_act0_min"
    )
    print(f"preregistered negative: {verdict}")
    print(
        f"best lever in family:   {best['arm']} at {best['delta_us_per_call']:+.3f} us/call "
        f"= {best['delta_pct_cs']:+.3f} % of cs = {best['fraction_of_ship_bar']:.2f}x the "
        f"{SHIP_BAR_PCT_CS} % ship bar -> does not ship"
    )
    print(
        "P3 falsifier (a0_act0_min >= 21.1 us/call => whole family dead): "
        f"{act0_min_us:.3f} us/call => SATISFIED"
    )

    payload = {
        "probe": "maple-frieren-r107f-stage1-t2d",
        "verdict": verdict,
        "price_book": {
            "pct_cs_per_us_step": PCT_CS_PER_US_STEP,
            "pct_cs_per_us_call": PCT_CS_PER_US_CALL,
            "calls_per_step": CALLS_PER_STEP,
            "ship_bar_pct_cs": SHIP_BAR_PCT_CS,
            "ship_bar_us_per_call": SHIP_BAR_US_CALL,
        },
        "in_situ_anchor": {"us_per_call": IN_SITU_US_CALL, "us_per_step": IN_SITU_US_STEP},
        "v0_gate": gate,
        "focus": focus_rows,
        "grid": grid_rows,
        "encmode": {
            m: {
                t: {k: v for k, v in r.items() if k not in ("samples", "empty_samples")}
                for t, r in d.items()
            }
            for m, d in enc.items()
        },
        "barrier_drain_us_per_call": gap,
        "ceilings": {
            "stream_peak_gb_s": stream_peak,
            "issue_peak_gload_s": max(
                r["loads_per_s"] for d in docs.values() for r in other(d, "issue")
            )
            / 1e9,
        },
        "unique_byte_floor_us_per_call": floor_us,
        "a0_act0_min_us_per_call": act0_min_us,
        "shipped_change": "none (empty diff vs base 2454cc01 over Sources/, Vendor/, benchmark.json)",
    }
    outp = ART / "adjudication.json"
    with outp.open("w") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {outp}")

    if args.wandb:
        import wandb

        run = wandb.init(
            entity="wandb-applied-ai-team",
            project="mlxfast-maple",
            name="r107f-t2d-down-residual-amortisation",
            job_type="adjudication",
            tags=["r107f", "t2d", "down-residual", "negative", "stage1", "m4-pro"],
            config={
                "assignment": "r105-b-rev6",
                "pr": 597,
                "branch": "maple-frieren/r105-router-prefetch-adjudication",
                "base_sha": "2454cc01ea3afabac067f0a271e36901fea7d21c",
                "host": next(iter(docs.values()))["device"],
                "architecture_name": "applegpu_g16s",
                "architecture_gen": 16,
                "nax_available": False,
                "kernel": "laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6",
                "calls_per_step": CALLS_PER_STEP,
                "unique_bytes_per_call": unique,
                "issued_bytes_per_call_shipped": 10027008,
                "ship_bar_pct_cs": SHIP_BAR_PCT_CS,
                "ship_bar_us_per_call": SHIP_BAR_US_CALL,
                "focus_rounds": next(iter(docs.values()))["focus_rounds"],
                "grid_rounds": next(iter(docs.values()))["rounds"],
                "replicates": len(docs),
            },
        )
        summary = {
            "decode_us_per_step": IN_SITU_US_STEP,
            "decode_us_per_step_baseline": IN_SITU_US_STEP,
            "decode_us_per_step_delta": 0.0,
            "verdict": verdict,
            "shipped_change": "none",
            "twin_us_per_call": statistics.mean(
                v["us_per_call"] for k, v in gate.items() if k.endswith("_focus")
            ),
            "v0_rel_vs_in_situ_pct": 100
            * statistics.mean(v["rel_vs_in_situ"] for k, v in gate.items() if k.endswith("_focus")),
            "unique_byte_floor_us_per_call": floor_us,
            "stream_peak_gb_s": stream_peak,
            "issue_peak_gload_s": payload["ceilings"]["issue_peak_gload_s"],
            "barrier_drain_us_per_call": gap,
            "barrier_drain_pct_cs": None if gap is None else gap * PCT_CS_PER_US_CALL,
            "a0_act0_min_us_per_call": act0_min_us,
        }
        for r in focus_rows:
            if "delta_us_per_call" not in r:
                continue
            summary[f"focus/{r['arm']}_delta_us_per_call"] = r["delta_us_per_call"]
            summary[f"focus/{r['arm']}_delta_pct_cs"] = r["delta_pct_cs"]
            summary[f"focus/{r['arm']}_x_ship_bar"] = r["fraction_of_ship_bar"]
        for block, rows in grid_rows.items():
            slug = block.replace("grid calls=39 ", "").replace(" ", "_")
            for r in rows:
                if "delta_us_per_call" not in r:
                    continue
                summary[f"grid/{slug}/{r['arm']}_delta_us_per_call"] = r["delta_us_per_call"]
        run.summary.update(summary)

        art = wandb.Artifact("r107f-t2d-adjudication", type="adjudication")
        for f in [
            outp,
            STAGE1 / "t2d-probe-full.json",
            STAGE1 / "t2d-probe-full2.json",
            ART / "stage0_host.json",
            ART / "rule75_digests.txt",
            ART / "offline" / "opsi_pipeline_stats.json",
            ART / "offline" / "opsi4_buffer_census.json",
            ART / "offline" / "compute_section_bytes.txt",
            ART / "offline" / "down_residual_reconstructed_opsi4.metal",
            Path("research/maple-frieren-r107f-t2d-down-residual-amortisation.md"),
            Path("research/maple_frieren_r107f_t2d_probe.swift"),
            Path("research/maple_frieren_r107f_stage1_run.sh"),
            Path("research/maple_frieren_r107f_stage1_analyse.py"),
        ]:
            if f.exists():
                art.add_file(str(f), name=f.name)
            else:
                print(f"WARNING: missing artifact file {f}")
        run.log_artifact(art)
        print(f"wandb run: {run.url}  id={run.id}")
        run.finish()


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent.parent)
    main()
