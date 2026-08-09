#!/usr/bin/env python3
"""R103-B rung 2: compare Metal dispatch traces captured for two arms.

dispatch.tsv columns: seq, kernel, kind, gridWxHxD, groupWxHxD, args
"""
import collections
import difflib
import pathlib
import sys

US_PER_DISPATCH = 0.3  # rule 53/68 pricing


def load(arm):
    p = pathlib.Path("/tmp/r103b/dump") / arm / "dispatch.tsv"
    rows = []
    for line in p.read_text().splitlines():
        if line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 5:
            continue
        rows.append(
            {
                "seq": int(f[0]),
                "kernel": f[1],
                "kind": f[2],
                "grid": f[3],
                "group": f[4],
                "args": f[5] if len(f) > 5 else "",
            }
        )
    return rows


STEP_MARKER = "custom_kernel_laguna_decode_embedding_rope_atlas"


def decode_steps(rows):
    """Split the trace into [prefill, step0, step1, ...] on the decode-step marker.

    The trace file is flushed line-by-line and its final line is truncated when
    the worker exits, so the last segment is always incomplete.
    """
    starts = [i for i, r in enumerate(rows) if r["kernel"].startswith(STEP_MARKER)]
    segs = []
    prev = 0
    for s in starts:
        segs.append(rows[prev:s])
        prev = s
    segs.append(rows[prev:])
    return segs


def last_complete_step(rows):
    segs = decode_steps(rows)
    return segs[-2] if len(segs) >= 3 else None


def main():
    a_arm, b_arm = sys.argv[1], sys.argv[2]
    a, b = load(a_arm), load(b_arm)
    print(f"# dispatch trace {a_arm} vs {b_arm}")
    print(f"total dispatches: {a_arm}={len(a)} {b_arm}={len(b)} delta={len(b)-len(a)}")

    sa = last_complete_step(a)
    sb = last_complete_step(b)
    pa, pb = len(sa), len(sb)
    print(f"last complete decode-step block length: {a_arm}={pa} {b_arm}={pb}")
    d = pb - pa
    print(
        f"per-decode-step dispatch delta = {d} "
        f"-> priced {d * US_PER_DISPATCH:+.2f} us/step at {US_PER_DISPATCH} us/dispatch"
    )
    print()

    ca = collections.Counter(r["kernel"] for r in a)
    cb = collections.Counter(r["kernel"] for r in b)
    keys = sorted(set(ca) | set(cb))
    print("## per-kernel dispatch counts (whole trace)")
    print(f"{'kernel':<70} {a_arm:>8} {b_arm:>8} {'delta':>7}")
    for k in keys:
        if ca[k] != cb[k] or True:
            print(f"{k:<70} {ca[k]:>8} {cb[k]:>8} {cb[k]-ca[k]:>+7}")
    print()

    print("## kernels with different counts")
    any_diff = False
    for k in keys:
        if ca[k] != cb[k]:
            any_diff = True
            print(f"  {k}: {ca[k]} -> {cb[k]} ({cb[k]-ca[k]:+d})")
    if not any_diff:
        print("  (none)")
    print()

    # Per-decode-step slice comparison (last complete block of each arm).
    if True:
        print("## last decode-step block, ordered sequence diff")
        la = [f"{r['kernel']}\t{r['kind']}\t{r['grid']}\t{r['group']}\t{r['args']}" for r in sa]
        lb = [f"{r['kernel']}\t{r['kind']}\t{r['grid']}\t{r['group']}\t{r['args']}" for r in sb]
        pos = [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]
        if len(la) == len(lb) and not pos:
            print("  (identical)")
        elif len(la) == len(lb):
            print(f"  positionally aligned; {len(pos)} of {len(la)} rows differ")
            for i in pos[:2]:
                print(f"  row {i}\n    - {la[i]}\n    + {lb[i]}")
            if len(pos) > 2:
                print(f"  ... {len(pos) - 2} further differing rows suppressed")
        else:
            for line in difflib.unified_diff(
                la, lb, fromfile=a_arm, tofile=b_arm, lineterm="", n=2
            ):
                print(line)
        print()

        print("## last decode-step block, geometry differences for shared kernel names")
        ga = collections.defaultdict(set)
        gb = collections.defaultdict(set)
        for r in sa:
            ga[r["kernel"]].add((r["kind"], r["grid"], r["group"]))
        for r in sb:
            gb[r["kernel"]].add((r["kind"], r["grid"], r["group"]))
        shown = False
        for k in sorted(set(ga) & set(gb)):
            if ga[k] != gb[k]:
                shown = True
                print(f"  {k}")
                print(f"    {a_arm}: {sorted(ga[k])}")
                print(f"    {b_arm}: {sorted(gb[k])}")
        if not shown:
            print("  (none)")


if __name__ == "__main__":
    main()
