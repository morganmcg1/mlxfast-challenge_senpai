#!/usr/bin/env python3
"""Offline replay of a saved prefill_probe GPUPROF trace (no GPU needed).

`prefill_probe.py --profile` prints three attribution bases: the raw
command-buffer bracket sum (over-counts, because buffers overlap), the
overlap-corrected fair share (sums exactly to union busy), and the exclusive
time each family owned the GPU alone.

Fair share still mis-credits a *fully covered* buffer: a kernel that binds
almost no bytes but whose bracket sits inside a multi-millisecond GEMM gets
half of the shared span even though it cannot be doing that much work. This
tool re-runs the same sweep with such dispatches removed so their span is
returned to the kernels that actually executed during it.

Usage:
  python3 research/prefill_census_adjudicate.py \
      --stderr research/pr270-logs-r106f/split1.worker.err \
      --cbs 1066 --walls-ms 548.25,548.53,548.10,548.06,548.81,548.52,548.43 \
      --drop arangeuint32
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prefill_probe import analyze, parse_gpuprof, shorten  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stderr", required=True)
    ap.add_argument("--cbs", type=int, required=True,
                    help="command buffers per request (from the probe output)")
    ap.add_argument("--walls-ms", required=True,
                    help="comma-separated per-request wall times, warm reps only")
    ap.add_argument("--drop", action="append", default=[],
                    help="dispatch short-name to treat as fully covered")
    ap.add_argument("--profile-top", type=int, default=400)
    ap.add_argument("--ceiling-gbs", type=float, default=260.2)
    args = ap.parse_args()

    walls = [float(x) / 1e3 for x in args.walls_ms.split(",")]
    records = parse_gpuprof(pathlib.Path(args.stderr).read_text(errors="replace"))
    need = len(walls) * args.cbs
    if len(records) < need:
        sys.exit(f"trace has {len(records)} records, need >= {need}")
    warm = records[-need:]
    batches = [(walls[i], warm[i * args.cbs:(i + 1) * args.cbs])
               for i in range(len(walls))]
    analyze("replay: all buffers", batches, args.ceiling_gbs, args.profile_top)

    if not args.drop:
        return
    drop = set(args.drop)

    def covered(rec):
        return len(rec[4]) == 1 and shorten(rec[4][0]) in drop

    kept = [(w, [r for r in recs if not covered(r)]) for w, recs in batches]
    removed = sum(len(r) for _, r in batches) - sum(len(r) for _, r in kept)
    print(f"\n\n=== adjudicated: dropped {removed} fully-covered buffers "
          f"({', '.join(sorted(drop))}) ===")
    analyze("replay: adjudicated", kept, args.ceiling_gbs, args.profile_top)


if __name__ == "__main__":
    main()
