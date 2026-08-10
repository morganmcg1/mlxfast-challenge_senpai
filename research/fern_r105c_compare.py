#!/usr/bin/env python3
"""R105-C A2/A6: compare two dispatch traces produced by fern_r105c_trace_arm.sh.

Prints the per-kernel dispatch-count delta and, for every kernel whose count
changed, the grid/threadgroup geometry actually recorded by the tracer. The
tracer output is truncated by its byte quota, so both arms are compared over the
same recorded prefix only.

Usage: fern_r105c_compare.py <arm_a> <arm_b> [--root /tmp/r105c/dump]
"""
import argparse
import collections
import hashlib
import pathlib
import sys

DECODE_MARKER = "custom_kernel_laguna_decode_embedding_rope_atlas"


def load(path):
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        rows.append({"name": parts[1], "grid": parts[3], "tg": parts[4]})
    return rows


def phase_counts(rows):
    starts = [i for i, r in enumerate(rows) if DECODE_MARKER in r["name"]]
    cut = starts[0] if starts else len(rows)
    pre = collections.Counter(r["name"] for r in rows[:cut])
    dec = collections.Counter(r["name"] for r in rows[cut:])
    return pre, dec, cut, len(starts)


def geometry(rows, name):
    return sorted({(r["grid"], r["tg"]) for r in rows if r["name"] == name})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arm_a")
    ap.add_argument("arm_b")
    ap.add_argument("--root", default="/tmp/r105c/dump")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    pa, pb = root / args.arm_a / "dispatch.tsv", root / args.arm_b / "dispatch.tsv"
    for p in (pa, pb):
        if not p.exists():
            sys.exit(f"missing {p}")

    ra, rb = load(pa), load(pb)
    ha = hashlib.md5(pa.read_bytes()).hexdigest()
    hb = hashlib.md5(pb.read_bytes()).hexdigest()
    print(f"{args.arm_a}: rows={len(ra)} bytes={pa.stat().st_size} md5={ha}")
    print(f"{args.arm_b}: rows={len(rb)} bytes={pb.stat().st_size} md5={hb}")
    print(f"byte-identical: {ha == hb}")

    prea, deca, cuta, nda = phase_counts(ra)
    preb, decb, cutb, ndb = phase_counts(rb)
    print(f"{args.arm_a}: prefill_prefix_rows={cuta} decode_steps_seen={nda}")
    print(f"{args.arm_b}: prefill_prefix_rows={cutb} decode_steps_seen={ndb}")

    names = sorted(set(prea) | set(preb) | set(deca) | set(decb))
    changed = [
        n for n in names
        if (prea[n], deca[n]) != (preb[n], decb[n])
    ]
    if not changed:
        print("\nNo per-kernel dispatch-count difference in either phase.")
        return
    print(f"\n{len(changed)} kernels differ (prefill_a/decode_a -> prefill_b/decode_b):")
    changed.sort(
        key=lambda n: -abs((prea[n] + deca[n]) - (preb[n] + decb[n]))
    )
    for n in changed[: args.top]:
        print(f"  {prea[n]:>5}/{deca[n]:<5} -> {preb[n]:>5}/{decb[n]:<5}  {n}")
        ga, gb = geometry(ra, n), geometry(rb, n)
        if ga:
            print(f"        {args.arm_a} geom: {ga}")
        if gb:
            print(f"        {args.arm_b} geom: {gb}")


if __name__ == "__main__":
    main()
