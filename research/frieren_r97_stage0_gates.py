#!/usr/bin/env python3
"""r97-d Stage 0: evaluate the two terminal gates and size the Stage 1 ladder.

GATE 0a (prefill-only): the injected work must not reach the single-token
decode steps. Step 0 is excluded because the seed forward's asynchronously
evaluated tail can legitimately drain into it -- and that tail is inside the
decode timer either way, so it cannot manufacture the effect under test.

GATE 0b (output-neutral): zero teacher-forced divergences and an identical
generated-token hash at every rung.

    python3 research/frieren_r97_stage0_gates.py research/r97-runs/stage0
"""
import argparse
import glob
import hashlib
import json
import os
import re
import statistics
import sys

TAG_RE = re.compile(r"^(\d+)_n(\d+)\.log$")


def parse(outdir):
    runs = []
    for path in sorted(glob.glob(os.path.join(outdir, "*.log"))):
        m = TAG_RE.match(os.path.basename(path))
        if not m:
            continue
        idx, rung = int(m.group(1)), int(m.group(2))
        text = open(path, errors="replace").read()
        prefill = re.search(r"prefill 512 tokens: ([0-9.]+) ms", text)
        seed = re.search(r"decode_begin seed forward: ([0-9.]+) ms", text)
        div = re.search(r"greedy tokens: (\d+) divergences", text)
        stem = path[: -len(".log")]
        steps = [float(x) for x in open(stem + ".steps")] if os.path.exists(stem + ".steps") else []
        tokens = open(stem + ".tokens", "rb").read() if os.path.exists(stem + ".tokens") else b""
        runs.append({
            "idx": idx, "rung": rung,
            "prefill_ms": float(prefill.group(1)) if prefill else None,
            "seed_ms": float(seed.group(1)) if seed else None,
            "divergences": int(div.group(1)) if div else None,
            "tokens_sha256": hashlib.sha256(tokens).hexdigest()[:16] if tokens else None,
            "step0_ms": steps[0] if steps else None,
            "steady_mean_ms": statistics.mean(steps[1:]) if len(steps) > 1 else None,
            "steady_sd_ms": statistics.stdev(steps[1:]) if len(steps) > 2 else None,
            "n_steps": len(steps),
        })
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    runs = parse(args.outdir)
    if not runs:
        print(f"no probe logs under {args.outdir}", file=sys.stderr)
        return 2

    print(f"{'idx':>4} {'rung':>5} {'prefill ms':>11} {'seed ms':>9} {'step0 ms':>9} "
          f"{'steady ms':>10} {'sd':>7} {'div':>4} {'tokens sha':>17}")
    for r in sorted(runs, key=lambda x: x["idx"]):
        print(f"{r['idx']:4d} {r['rung']:5d} {r['prefill_ms']:11.2f} {r['seed_ms']:9.2f} "
              f"{r['step0_ms']:9.3f} {r['steady_mean_ms']:10.4f} {r['steady_sd_ms']:7.4f} "
              f"{r['divergences']:4d} {r['tokens_sha256']:>17}")

    rungs = sorted({r["rung"] for r in runs})
    base = [r for r in runs if r["rung"] == 0]
    b_steady = statistics.mean(r["steady_mean_ms"] for r in base)
    b_seed = statistics.mean(r["seed_ms"] for r in base)
    b_prefill = statistics.mean(r["prefill_ms"] for r in base)

    print(f"\n{'rung':>5} {'n':>3} {'d_seed ms':>10} {'d_prefill ms':>13} "
          f"{'ms/matmul(seed)':>16} {'d_steady us':>12} {'leak frac':>10}")
    per_rung, worst_leak = {}, 0.0
    for rung in rungs:
        sel = [r for r in runs if r["rung"] == rung]
        d_seed = statistics.mean(r["seed_ms"] for r in sel) - b_seed
        d_prefill = statistics.mean(r["prefill_ms"] for r in sel) - b_prefill
        d_steady_us = (statistics.mean(r["steady_mean_ms"] for r in sel) - b_steady) * 1e3
        # If the injection reached a single-token step it would add the WHOLE
        # per-forward cost to every step, so that is the correct denominator.
        leak = d_steady_us / (d_seed * 1e3) if rung else 0.0
        worst_leak = max(worst_leak, abs(leak))
        per_rung[rung] = {"n": len(sel), "d_seed_ms": d_seed, "d_prefill_ms": d_prefill,
                          "ms_per_matmul": d_seed / rung if rung else 0.0,
                          "d_steady_us": d_steady_us, "leak_fraction": leak}
        print(f"{rung:5d} {len(sel):3d} {d_seed:10.2f} {d_prefill:13.2f} "
              f"{(d_seed/rung if rung else 0):16.3f} {d_steady_us:12.1f} {leak:10.5f}")

    # The steady-step deltas compare DIFFERENT runs, so the relevant error is
    # the run-to-run scatter of the per-run steady mean, not the within-run SE
    # of 127 steps. Pool the within-rung variance across rungs.
    resid, dof = 0.0, 0
    for rung in rungs:
        sel = [r["steady_mean_ms"] for r in runs if r["rung"] == rung]
        if len(sel) > 1:
            m = statistics.mean(sel)
            resid += sum((x - m) ** 2 for x in sel)
            dof += len(sel) - 1
    between_sd_us = ((resid / dof) ** 0.5) * 1e3 if dof else float("nan")
    worst_z = 0.0
    for rung, v in per_rung.items():
        if not rung:
            continue
        se = between_sd_us * (1 / len(base) + 1 / v["n"]) ** 0.5
        v["steady_se_us"] = se
        v["steady_z"] = v["d_steady_us"] / se if se else float("nan")
        worst_z = max(worst_z, abs(v["steady_z"]))
    gate0a = all(abs(v["leak_fraction"]) < 0.01 and abs(v["steady_z"]) < 3
                 for k, v in per_rung.items() if k)
    hashes = {r["tokens_sha256"] for r in runs}
    gate0b = all(r["divergences"] == 0 for r in runs) and len(hashes) == 1

    print(f"\nGATE 0a prefill-only : {'PASS' if gate0a else 'FAIL'} "
          f"(worst |leak| = {worst_leak:.5f} of injected cost; "
          f"between-run steady sd = {between_sd_us:.1f} us, worst |z| = {worst_z:.2f})")
    print(f"GATE 0b output-neutral: {'PASS' if gate0b else 'FAIL'} "
          f"(divergences {sorted({r['divergences'] for r in runs})}, "
          f"{len(hashes)} distinct token hash(es): {sorted(hashes)})")

    top = max(rungs)
    if top:
        ms = per_rung[top]["d_seed_ms"] / top
        print(f"\nsizing: {ms:.3f} ms per injected matmul (from the seed forward, "
              f"the forward that is inside the decode timer)")
        for n in (8, 16, 32, 40):
            print(f"  rung {n:3d}: injected {n*ms:7.1f} ms -> predicted "
                  f"dD {n*ms*1e3/128:7.1f} us/step, dP {n*ms*1e3/512:6.1f} us/token")

    out = {"gate0a_prefill_only": gate0a, "gate0b_bitexact": gate0b,
           "worst_leak_fraction": worst_leak, "between_run_steady_sd_us": between_sd_us, "worst_steady_z": worst_z,
           "ms_per_matmul": per_rung[top]["d_seed_ms"] / top if top else 0.0,
           "distinct_token_hashes": len(hashes),
           "per_rung": {str(k): v for k, v in per_rung.items()},
           "runs": runs}
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=2)
    return 0 if (gate0a and gate0b) else 1


if __name__ == "__main__":
    sys.exit(main())
