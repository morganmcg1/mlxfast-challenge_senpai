#!/usr/bin/env python3
"""Inter-command-buffer GPU idle-interval distribution from GPUPROF records.

PR #44 r3 deliverable C names this the discriminator between two rival
explanations of why raising MLX_MAX_MB_PER_BUFFER above 200 costs wall time
while GPU busy time barely moves:

  H_encode  the GPU cannot start a command buffer until more encoding is done,
            so *every* buffer boundary costs more as buffers grow. Prediction:
            the extra idle is spread across boundaries; mean idle per boundary
            rises and the top-decile share of total idle stays flat.

  H_stall   a few long stalls appear (allocator, residency, or completion
            handler serialization) that are not a property of boundaries.
            Prediction: mean idle per boundary can even fall while the
            top-decile share of total idle rises sharply.

Reads the worker stderr written by research/decode_probe.py --stderr, which
holds one GPUPROF record per command buffer with GPU start/end seconds on the
mach absolute epoch. Only inter-buffer idle is observable at
DARKBLOOM_GPU_PROFILE_SPLIT=0; intra-buffer idle would need SPLIT=1 and a
different, inflated binary.

  python3 research/nezuko_cb_idle.py --steps 99 /tmp/nezuko-up-decode-mb200.err

--steps is the number of steady steps the matching decode_probe run reported,
used only to normalize per step so the idle sum can be checked against that
run's logged gap. Records are read tail-first via --tail-frac to drop the
512-token prefill seed and step 0 without needing the driver's step spans.
"""
import argparse
import statistics


def load(path):
    rec = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("GPUPROF "):
                _, s, e, nops, _names = line.rstrip("\n").split(" ", 4)
                rec.append((float(s), float(e), int(nops)))
    rec.sort()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, default=0,
                    help="steady steps, for per-step normalization only")
    ap.add_argument("--tail-frac", type=float, default=0.95,
                    help="analyze only the last fraction of records")
    args = ap.parse_args()

    hdr = (f"{'file':>34} {'n_cb':>6} {'n_idle':>7} {'busy_ms':>8} "
           f"{'idle_ms':>8} {'mean_us':>8} {'p50_us':>7} {'p90_us':>7} "
           f"{'p99_us':>7} {'max_us':>8} {'top10%':>7} {'top1%':>6}")
    print(hdr)
    print("-" * len(hdr))
    for path in args.paths:
        rec = load(path)
        if not rec:
            print(f"{path.split('/')[-1]:>34}  no GPUPROF records")
            continue
        keep = rec[int(len(rec) * (1.0 - args.tail_frac)):]
        idle = [max(0.0, keep[i + 1][0] - keep[i][1])
                for i in range(len(keep) - 1)]
        busy = sum(e - s for s, e, _ in keep)
        tot = sum(idle)
        srt = sorted(idle, reverse=True)
        n10 = max(1, len(srt) // 10)
        n01 = max(1, len(srt) // 100)
        top10 = sum(srt[:n10]) / tot * 100 if tot else 0.0
        top01 = sum(srt[:n01]) / tot * 100 if tot else 0.0
        print(f"{path.split('/')[-1]:>34} {len(keep):6d} {len(idle):7d} "
              f"{busy * 1e3:8.1f} {tot * 1e3:8.3f} "
              f"{statistics.fmean(idle) * 1e6:8.2f} "
              f"{statistics.median(idle) * 1e6:7.2f} "
              f"{srt[n10 - 1] * 1e6:7.2f} {srt[n01 - 1] * 1e6:7.2f} "
              f"{srt[0] * 1e6:8.1f} {top10:6.1f}% {top01:5.1f}%")
        if args.steps:
            frac = len(keep) / len(rec)
            eff = args.steps * frac
            print(f"{'':>34} per steady step (scaled x{frac:.3f}): "
                  f"idle={tot / eff * 1e3:.3f} ms "
                  f"boundaries={len(idle) / eff:.1f} "
                  f"idle_per_boundary={tot / len(idle) * 1e6:.2f} us")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
