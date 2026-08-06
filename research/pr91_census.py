#!/usr/bin/env python3
"""PR91 prefill dispatch census: re-derive the family ledger from a raw
GPUPROF worker stderr trace, independently of prefill_probe.py.

The trace is segmented into individual forwards by inter-command-buffer idle
gaps, so the census is computed per forward and reported as a median across
forwards rather than as a mean over an unsegmented pile of records.

Usage:
  python3 research/pr91_census.py research/pr91-logs/step1-split1.worker.err \
      --label SPLIT=1 [--gap-ms 40] [--drop-first 1]
"""
import argparse
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prefill_probe import FAMILIES, family, parse_gpuprof, shorten  # noqa: E402

# Kernels whose GPU intervals are fully hidden behind a following heavy kernel;
# additive (sum) accounting double-counts them, so they are excluded from the
# serial-equivalent basis and reported separately.
OVERLAPPED = re.compile(r"^arange")


def segment(records, per_forward, n_forwards):
    """Cut the trailing n_forwards blocks of exactly per_forward dispatches.

    Idle-gap segmentation does not work on this trace: the worker is fed
    requests back to back and the largest inter-record gap (19.4 ms) is
    smaller than several intra-forward gaps, so there is no separating
    threshold. The trailing requests are the timed prefills, and each is known
    from the worker's own per-request accounting to issue exactly per_forward
    dispatches, so counting dispatches backwards from the end is exact.
    """
    ordered = sorted(records)
    forwards, cur, n = [], [], 0
    for rec in reversed(ordered):
        cur.append(rec)
        n += rec[2]
        if n == per_forward:
            forwards.append(list(reversed(cur)))
            cur, n = [], 0
            if len(forwards) == n_forwards:
                break
        elif n > per_forward:
            raise SystemExit(f"dispatch boundary overshoot at {n}; the trace "
                             f"does not decompose into {per_forward}-dispatch "
                             f"forwards")
    return list(reversed(forwards))


def union_ms(recs):
    merged = []
    for s, e, *_ in sorted(recs):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(e - s for s, e in merged) * 1e3


def census(forward):
    """Return (per-family ms, per-family dispatches, per-family bytes)."""
    fam_ms, fam_n, fam_b, over_ms = {}, {}, {}, 0.0
    for s, e, nops, nbytes, names in forward:
        dur = (e - s) * 1e3
        shorts = [shorten(n) for n in names] or ["<unnamed>"]
        # A command buffer may carry several dispatches; attribute its wall
        # time evenly across them, which is the only division the instrument
        # supports. SPLIT=1 keeps this benign: 910 of 1066 buffers are
        # single-dispatch and the 156 mixed buffers hold 2 each.
        share = dur / len(shorts)
        for sh in shorts:
            f = family(sh)
            fam_ms[f] = fam_ms.get(f, 0.0) + share
            fam_n[f] = fam_n.get(f, 0) + 1
            fam_b[f] = fam_b.get(f, 0) + nbytes / len(shorts)
            if OVERLAPPED.search(sh):
                over_ms += share
    return fam_ms, fam_n, fam_b, over_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=pathlib.Path)
    ap.add_argument("--label", default="trace")
    ap.add_argument("--dispatches-per-forward", type=int, default=1222)
    ap.add_argument("--forwards", type=int, default=6,
                    help="trailing timed requests present in the trace")
    ap.add_argument("--drop-first", type=int, default=1,
                    help="discard leading forwards (cold first rep)")
    args = ap.parse_args()

    records = parse_gpuprof(args.trace.read_text(errors="replace"))
    if not records:
        raise SystemExit(f"{args.trace}: no 6-field GPUPROF records. A hook "
                         f"emitting only 5 fields is silently unparseable.")
    forwards = segment(records, args.dispatches_per_forward, args.forwards)

    print(f"census [{args.label}]  trace={args.trace}")
    print(f"  command-buffer records in trace  {len(records)}")
    print(f"  dispatches in trace              {sum(r[2] for r in records)}")
    print(f"  trailing forwards recovered      {len(forwards)} "
          f"x {args.dispatches_per_forward} dispatches")
    print(f"  command buffers per forward      "
          f"{[len(f) for f in forwards]}")

    clean = forwards[args.drop_first:]
    if not clean:
        raise SystemExit("nothing left after --drop-first")
    print(f"  kept                             {len(clean)} "
          f"(dropped first {args.drop_first} as cold)")

    rows = [census(f) for f in clean]
    fams = sorted({k for r in rows for k in r[0]},
                  key=lambda f: -statistics.median(r[0].get(f, 0.0)
                                                   for r in rows))
    cb = statistics.median(len(f) for f in clean)
    disp = statistics.median(sum(r[2] for r in f) for f in clean)
    busy = statistics.median(sum((e - s) for s, e, *_ in f) * 1e3
                             for f in clean)
    uni = statistics.median(union_ms(f) for f in clean)
    over = statistics.median(r[3] for r in rows)
    serial = busy - over

    print(f"\n  command buffers / forward   {cb:.0f}")
    print(f"  dispatches / forward        {disp:.0f}")
    print(f"  gpu busy (additive sum)     {busy:9.3f} ms")
    print(f"  gpu busy (interval union)   {uni:9.3f} ms")
    print(f"  fully-overlapped (arange)   {over:9.3f} ms")
    print(f"  serial-equivalent basis     {serial:9.3f} ms "
          f"(sum - overlapped; union is {uni:.3f}, "
          f"{abs(serial - uni) / uni * 100:.2f}% apart)")

    tot_b = statistics.median(sum(r[3] for r in f) for f in clean)
    print(f"  bound input bytes / forward {tot_b / 1e9:9.3f} GB "
          f"({tot_b / 2 ** 30:.3f} GiB)")

    print(f"\n  {'family':<22} {'n/fwd':>6} {'ms/fwd':>9} {'%serial':>8} "
          f"{'GB/fwd':>8}")
    for f in fams:
        ms = statistics.median(r[0].get(f, 0.0) for r in rows)
        n = statistics.median(r[1].get(f, 0) for r in rows)
        b = statistics.median(r[2].get(f, 0.0) for r in rows)
        print(f"  {f:<22} {n:6.0f} {ms:9.3f} {ms / serial * 100:7.2f}% "
              f"{b / 1e9:8.3f}")
    ms_sum = sum(statistics.median(r[0].get(f, 0.0) for r in rows)
                 for f in fams)
    n_sum = sum(statistics.median(r[1].get(f, 0) for r in rows) for f in fams)
    print(f"  {'TOTAL':<22} {n_sum:6.0f} {ms_sum:9.3f}")
    print(f"  closure: family dispatch sum {n_sum:.0f} vs profiler "
          f"{disp:.0f} -> {'OK' if abs(n_sum - disp) < 0.5 else 'MISMATCH'}")
    # Per-family medians are taken independently across forwards, so they need
    # not sum to the median of the total; a sub-0.1% residual is that artifact,
    # not a lost dispatch.
    print(f"  closure: family ms sum {ms_sum:.3f} vs additive busy {busy:.3f} "
          f"-> {abs(ms_sum - busy) / busy * 100:.3f}% "
          f"{'OK' if abs(ms_sum - busy) / busy < 1e-3 else 'MISMATCH'}")


if __name__ == "__main__":
    main()
