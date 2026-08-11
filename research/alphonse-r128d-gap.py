#!/usr/bin/env python3
"""R128-D analyser: wall statistics, KV-growth slope, and gap decomposition.

Reads one or more JSON files written by research/alphonse-r128d-probe.py. When
the matching worker stderr holds GPUPROF records (the hooked build), it also
splits every steady step's non-busy time into leading (encode/commit before the
first GPU record), internal (idle between command buffers), and trailing
(completion plus the driver's response leg), which sum to wall - busy_union by
construction.

  python3 research/alphonse-r128d-gap.py /tmp/r128d-clean.json [--window 128]
"""
import argparse
import json
import statistics
import sys


def parse_gpuprof(path):
    recs = []
    try:
        fh = open(path, errors="replace")
    except OSError:
        return recs
    with fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parts = line.rstrip("\n").split(" ", 5)
            if len(parts) < 5:
                continue
            if len(parts) == 6 and parts[4].isdigit():
                recs.append((float(parts[1]), float(parts[2]), int(parts[3])))
            else:
                p = line.rstrip("\n").split(" ", 4)
                recs.append((float(p[1]), float(p[2]), int(p[3])))
    recs.sort()
    return recs


def union_len(iv):
    if not iv:
        return 0.0
    total = 0.0
    cs, ce = iv[0]
    for s, e in iv[1:]:
        if s > ce:
            total += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    return total + ce - cs


def internal_idle(iv):
    """Idle time strictly between the first GPU start and the last GPU end."""
    if not iv:
        return 0.0
    span = iv[-1][1] - iv[0][0] if iv[-1][1] > iv[0][0] else max(e for _, e in iv) - iv[0][0]
    hi = max(e for _, e in iv)
    return (hi - iv[0][0]) - union_len(iv)


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


def describe(name, vals, unit=1e6):
    v = sorted(vals)
    med = statistics.median(v)
    iqr = q(v, 0.75) - q(v, 0.25)
    sd = statistics.stdev(v) if len(v) > 1 else 0.0
    print(f"{name:<26} n={len(v):<5} median={med*unit:9.1f} "
          f"IQR={iqr*unit:8.1f} sd={sd*unit:8.1f} "
          f"min={v[0]*unit:9.1f} max={v[-1]*unit:9.1f}")
    return med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--window", type=int, default=128,
                    help="also report the median over steps 1..window-1, the "
                         "scored local-iterate decode window")
    args = ap.parse_args()

    for path in args.files:
        blob = json.load(open(path))
        print(f"\n===== {path}  worker={blob['worker']} env={blob.get('env')}")
        run_meds, run_meds_win, seeds, rtts = [], [], [], []
        lead_all, intern_all, trail_all, busy_sum_all, busy_u_all = [], [], [], [], []
        cbs_all, disp_all, wall_prof = [], [], []
        slopes = []
        for r in blob["runs"]:
            spans = [(a, b) for a, b in r["spans"]]
            steady = spans[1:]
            steps = [b - a for a, b in steady]
            run_meds.append(statistics.median(steps))
            run_meds_win.append(statistics.median(steps[:args.window - 1]))
            seeds.append(r["seed_s"])
            rtts += r["rtt_pre"] + r["rtt_post"]
            n = len(steps)
            xs = list(range(n))
            mx, my = statistics.mean(xs), statistics.mean(steps)
            den = sum((x - mx) ** 2 for x in xs)
            slopes.append(sum((x - mx) * (y - my) for x, y in zip(xs, steps)) / den)

            recs = parse_gpuprof(r["stderr"])
            if not recs:
                continue
            j = 0
            for (t0, t1) in steady:
                while j < len(recs) and recs[j][1] < t0:
                    j += 1
                k = j
                iv, nops = [], 0
                while k < len(recs) and recs[k][0] < t1:
                    s, e, ops = recs[k]
                    iv.append((max(s, t0), min(e, t1)))
                    nops += ops
                    k += 1
                if not iv:
                    continue
                bs = sum(e - s for s, e in iv)
                bu = union_len(iv)
                lead = iv[0][0] - t0
                trail = t1 - max(e for _, e in iv)
                lead_all.append(lead)
                trail_all.append(trail)
                intern_all.append(internal_idle(iv))
                busy_sum_all.append(bs)
                busy_u_all.append(bu)
                cbs_all.append(len(iv))
                disp_all.append(nops)
                wall_prof.append(t1 - t0)

        print(f"runs={len(blob['runs'])} steps/run={blob['steps']}")
        describe("seed forward (ms)", seeds, 1e3)
        describe("per-run median step", run_meds)
        describe(f"per-run median step[1:{args.window}]", run_meds_win)
        describe("null-request RTT", rtts)
        print(f"{'KV-growth slope':<26} "
              f"median={statistics.median(slopes)*1e6*1000:9.3f} us per 1000 steps")
        if busy_u_all:
            print("--- profiled steps ---")
            w = describe("wall (profiled steps)", wall_prof)
            bs = describe("gpu_busy_sum", busy_sum_all)
            bu = describe("gpu_busy_union", busy_u_all)
            le = describe("lead (t0->first GPU)", lead_all)
            it = describe("internal idle", intern_all)
            tr = describe("trail (last GPU->t1)", trail_all)
            print(f"{'cbs/step':<26} median={statistics.median(cbs_all):.1f}  "
                  f"dispatches/step median={statistics.median(disp_all):.1f}")
            print(f"check: wall-busy_union={(w-bu)*1e6:.1f} us vs "
                  f"lead+internal+trail={(le+it+tr)*1e6:.1f} us "
                  f"(medians are not additive; means below)")
            mw = statistics.mean(wall_prof)
            print(f"means: wall={mw*1e6:.1f} busy_union={statistics.mean(busy_u_all)*1e6:.1f} "
                  f"busy_sum={statistics.mean(busy_sum_all)*1e6:.1f} "
                  f"lead={statistics.mean(lead_all)*1e6:.1f} "
                  f"internal={statistics.mean(intern_all)*1e6:.1f} "
                  f"trail={statistics.mean(trail_all)*1e6:.1f} "
                  f"residual={(mw-statistics.mean(busy_u_all))*1e6:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
