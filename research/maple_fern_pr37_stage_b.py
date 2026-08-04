#!/usr/bin/env python3
"""PR#37 Part 0 stage B (research-only, not part of the submission).

Answers the four Part-0 questions from the cached stage-A arrays:
  1. concentration of |x| across channels and 128-dim groups, per decode step;
  2. survivor counts for the shipped level-one screen, for a b-bit coarser
     plane, and for the proposed top-K-group level-0 screen;
  3. the resulting byte budget per decode step;
  4. the general delta-tolerance curve that prices ANY coarser screen.

Run: python3 research/maple_fern_pr37_stage_b.py
"""
import os

import numpy as np

CACHE = os.environ.get("PR37_CACHE", "/tmp/pr37")
V, H = 100352, 2048
GAMMA = 2.0 ** -15
ROW_BYTES_L1 = 1088  # nibble plane 1024 B + 64 scale bytes
BLOCK = 4  # rows per simdgroup in the exact pass
NBLOCK = V // BLOCK


def bf16_rne(x):
    u = x.astype(np.float32).view(np.uint32)
    r = (u + np.uint32(0x7FFF) + ((u >> 16) & np.uint32(1))) & np.uint32(0xFFFF_0000)
    return r.view(np.float32)


def bf16_up(x):
    """Round a non-negative float32 UP to bf16, as the kernel's mask-and-bump does."""
    u = x.astype(np.float32).view(np.uint32)
    t = u & np.uint32(0xFFFF_0000)
    t = np.where(t != u, t + np.uint32(0x0001_0000), t)
    return t.view(np.float32)


def threshold(e_r):
    """Exact replica of the step-3 rule: midpoint just below bfloat(e_r)."""
    b = bf16_rne(e_r)
    bits = b.view(np.uint32)
    pred = np.where(bits & np.uint32(0x8000_0000), bits + np.uint32(0x0001_0000),
                    bits - np.uint32(0x0001_0000)).view(np.float32)
    return (pred.astype(np.float64) + b.astype(np.float64)) * 0.5


def counts(coarse, delta, thr):
    """Rows and 4-row blocks surviving `coarse + delta >= thr`, per step."""
    live = (coarse.astype(np.float64) + delta.astype(np.float64)) >= thr[:, None]
    rows = live.sum(axis=1)
    blocks = live.reshape(len(live), NBLOCK, BLOCK).any(axis=2).sum(axis=1)
    return rows, blocks, live


def pct(a):
    a = np.asarray(a, dtype=np.float64)
    return f"{a.mean():8.1f} {a.min():8.0f} {np.median(a):8.0f} {a.max():8.0f}"


def main():
    x = np.load(f"{CACHE}/x.npy")[1:]  # drop the worker's pre-timing forward
    E = np.load(f"{CACHE}/E.npy")[1:]
    sd = np.load(f"{CACHE}/sd.npy")
    m128 = np.load(f"{CACHE}/m128.npy")
    C = {b: np.load(f"{CACHE}/C{b}.npy")[1:] for b in (4, 3, 2)}
    T = x.shape[0]
    ax = np.abs(x)
    a32 = ax.reshape(T, 64, 32).sum(axis=2)  # per 32-dim int5 group
    a128 = ax.reshape(T, 16, 128).sum(axis=2)  # per 128-dim level-0 group
    print(f"steps={T}\n")

    # ---------------------------------------------------------------- Q1
    print("== Q1  concentration of sum_j |x_j| (share carried by the top-n channels)")
    print("        n:      64     128     256     512    1024")
    srt = np.sort(ax, axis=1)[:, ::-1]
    cum = np.cumsum(srt, axis=1) / ax.sum(axis=1, keepdims=True)
    for name, fn in (("min ", np.min), ("med ", np.median), ("max ", np.max)):
        row = [fn(cum[:, n - 1]) for n in (64, 128, 256, 512, 1024)]
        print("  " + name + "  " + "  ".join(f"{v:6.3f}" for v in row))
    print("        L2 energy share (sum x_j^2):")
    s2 = np.sort(ax * ax, axis=1)[:, ::-1]
    cum2 = np.cumsum(s2, axis=1) / (ax * ax).sum(axis=1, keepdims=True)
    for name, fn in (("min ", np.min), ("med ", np.median), ("max ", np.max)):
        row = [fn(cum2[:, n - 1]) for n in (64, 128, 256, 512, 1024)]
        print("  " + name + "  " + "  ".join(f"{v:6.3f}" for v in row))
    print("\n     group-of-128 granularity (the level-0 selection unit), top-K groups:")
    print("        K:       1       2       4       8      12")
    g = np.sort(a128, axis=1)[:, ::-1]
    cg = np.cumsum(g, axis=1) / a128.sum(axis=1, keepdims=True)
    for name, fn in (("min ", np.min), ("med ", np.median), ("max ", np.max)):
        row = [fn(cg[:, k - 1]) for k in (1, 2, 4, 8, 12)]
        print("  " + name + "  " + "  ".join(f"{v:6.3f}" for v in row))
    print()

    # ------------------------------------------------- shipped level-one screen
    d_base = a32 @ sd.T  # sum_g sd_g * sum_{j in g} |x_j|  (full-cell, b=4)
    delta1 = bf16_up((d_base * np.float32(1.0 + 32.0 * GAMMA)).astype(np.float32))
    r1 = C[4].argmax(axis=1)
    thr1 = threshold(E[np.arange(T), r1])
    rows1, blocks1, live1 = counts(C[4], delta1, thr1)
    print("== shipped level-one screen (nibble plane, 1088 B/row)")
    print("                      mean     min     med     max")
    print(f"  survivor rows   {pct(rows1)}")
    print(f"  live 4-blocks   {pct(blocks1)}   of {NBLOCK}")
    print(f"  block fill      {rows1.mean() / blocks1.mean():.2f} wanted rows per live block")
    exact_mb = blocks1.mean() * BLOCK * (H * 2 + 256 + 64) / 1e6
    print(f"  bytes/step      level1 {V * ROW_BYTES_L1 / 1e6:.1f} MB + exact {exact_mb:.1f} MB"
          f" = {V * ROW_BYTES_L1 / 1e6 + exact_mb:.1f} MB\n")

    # ---------------------------------------------------------------- Q4
    print("== Q4  delta-tolerance curve: how far ANY coarser screen can widen the bound")
    print("   (coarse = shipped level-one coarse, delta = m x level-one delta)")
    print("     m      rows      blocks   block share")
    for m in (0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0):
        rr, bb, _ = counts(C[4], delta1 * m, thr1)
        print(f"  {m:5.2f}  {rr.mean():9.1f}  {bb.mean():9.1f}   {bb.mean() / NBLOCK:7.4f}")
    print()

    # ---------------------------------------------------------------- Q1b/Q4b
    print("== b-bit exhaustive plane alternative (exact coarse for each plane width)")
    print("   b   B/row   MB/step    rows    blocks   share   total MB/step")
    for b in (4, 3, 2):
        db = bf16_up((d_base * np.float32(2.0 ** (4 - b)) * np.float32(1.0 + 32.0 * GAMMA)).astype(np.float32))
        rb = C[b].argmax(axis=1)
        thrb = threshold(E[np.arange(T), rb])
        rr, bb, _ = counts(C[b], db, thrb)
        brow = 256 * b + 64
        l0 = V * brow / 1e6
        second = bb.mean() * BLOCK * (H * 2 + 256 + 64) / 1e6
        print(f"  {b}   {brow:5d}   {l0:7.1f}  {rr.mean():8.1f} {bb.mean():9.1f}  {bb.mean() / NBLOCK:6.4f}"
              f"   {l0 + second:8.1f}")
    print()

    # ---------------------------------------------------------------- Q2/Q3
    print("== Q2/Q3  proposed level-0 screen: top-K 128-dim groups at int4 + certified tail bound")
    # midpoint-dequantized level-one weight, needed for the partial coarse sums
    q0 = np.load(f"{CACHE}/q0.npy", mmap_mode="r")
    print("   K  dims  B/row  level0 MB   rows   blocks  share   L1-refill MB  total MB/step")
    for K in (1, 2, 4, 8, 12):
        sel = np.argsort(-a128, axis=1)[:, :K]
        mask128 = np.zeros((T, 16), dtype=bool)
        np.put_along_axis(mask128, sel, True, axis=1)
        mask32 = np.repeat(mask128, 4, axis=1)
        # certified bound: half/full-cell inside S, per-row group max outside S
        d0 = (a32 * mask32) @ sd.T + (a128 * ~mask128) @ m128.T
        d0 = bf16_up((d0 * np.float32(1.0 + 32.0 * GAMMA)).astype(np.float32))
        # partial coarse over S only, grouped by distinct selected sets
        c0 = np.zeros((T, V), dtype=np.float32)
        keys = {}
        for t in range(T):
            keys.setdefault(tuple(sorted(sel[t].tolist())), []).append(t)
        for key, ts in keys.items():
            cols = np.concatenate([np.arange(gg * 128, (gg + 1) * 128) for gg in key])
            u = np.asarray(q0[:, cols])
            what = ((u >> 1).astype(np.float32) * 2.0 - 15.5) * sd[:, cols // 32]
            c0[ts] = x[np.ix_(ts, cols)] @ what.T
            del u, what
        r0 = c0.argmax(axis=1)
        thr0 = threshold(E[np.arange(T), r0])
        rr, bb, _ = counts(c0, d0, thr0)
        brow = K * 64 + K * 4 + 16  # int4 codes + scale bytes + 1 B/group max plane
        l0 = V * brow / 1e6
        refill = bb.mean() * BLOCK * ROW_BYTES_L1 / 1e6
        print(f"  {K:2d} {K * 128:5d}  {brow:5d}   {l0:8.1f} {rr.mean():8.1f} {bb.mean():8.1f}"
              f" {bb.mean() / NBLOCK:6.3f}   {refill:10.1f}   {l0 + refill + exact_mb:8.1f}")
        print(f"      distinct selected sets across {T} steps: {len(keys)}")
    print()

    # ---------------------------------------------------- bound anatomy
    print("== bound anatomy: the tail term in units of the shipped level-one delta")
    n128 = np.load(f"{CACHE}/n128.npy")
    xl2 = np.sqrt((x.astype(np.float64) ** 2).reshape(T, 16, 128).sum(axis=2))
    d1m = d_base.mean()
    full_tail_max = (a128 @ m128.T).mean() / d1m
    full_tail_cs = (xl2 @ n128.T).mean() / d1m
    print(f"  whole-row tail bound / delta1:  max-form {full_tail_max:6.2f}x   "
          f"Cauchy-Schwarz {full_tail_cs:6.2f}x")
    print("   K   head/d1   tail_max/d1  tail_CS/d1   best delta0/d1   tolerance 1.25x?")
    for K in (1, 2, 4, 8, 12, 15):
        sel = np.argsort(-a128, axis=1)[:, :K]
        mask128 = np.zeros((T, 16), dtype=bool)
        np.put_along_axis(mask128, sel, True, axis=1)
        mask32 = np.repeat(mask128, 4, axis=1)
        head = ((a32 * mask32) @ sd.T).mean() / d1m
        tmax = ((a128 * ~mask128) @ m128.T).mean() / d1m
        tcs = ((xl2 * ~mask128) @ n128.T).mean() / d1m
        best = head + min(tmax, tcs)
        print(f"  {K:2d}   {head:7.3f}   {tmax:10.2f}  {tcs:10.2f}   {best:12.2f}   "
              f"{'PASS' if best <= 1.25 else 'FAIL'}")
    print()
    # ---------------------------------- can a TIGHTER certificate buy headroom?
    print("== tighter certificate: Cauchy-Schwarz on the residual, |r_i . x| <= ||r_i||2 ||x||2")
    print("   (||r_i||2 is one extra init-time scalar per row: 0.1-0.2 MB total, no per-step bytes)")
    xn = np.linalg.norm(x.astype(np.float64), axis=1)
    print("   b   L1 bound/d1   CS bound/d1   min-of-two/d1    rows   blocks   share")
    for b in (4, 3, 2):
        dl1 = d_base * (2.0 ** (4 - b))
        rn = np.load(f"{CACHE}/rnorm{b}.npy")
        dcs = np.outer(xn, rn)
        dmin = bf16_up(np.minimum(dl1, dcs).astype(np.float32) * np.float32(1.0 + 32.0 * GAMMA))
        rb = C[b].argmax(axis=1)
        thrb = threshold(E[np.arange(T), rb])
        rr, bb, _ = counts(C[b], dmin, thrb)
        print(f"  {b}   {dl1.mean() / d1m:11.3f}   {dcs.mean() / d1m:11.3f}   {dmin.mean() / d1m:13.3f}"
              f" {rr.mean():8.1f} {bb.mean():8.1f}  {bb.mean() / NBLOCK:6.4f}")
    print()

    # ------------------------------------- the shipped TWO-STAGE decode cascade
    print("== the shipped decode cascade, both stages, and what a tighter bound buys")
    C5 = np.load(f"{CACHE}/C5.npy")[1:]
    rn4 = np.load(f"{CACHE}/rnorm4.npy")
    rn5 = np.load(f"{CACHE}/rnorm5.npy")
    cs4 = np.outer(xn, rn4)
    cs5 = np.outer(xn, rn5)
    d4 = bf16_up((d_base * np.float32(1.0 + 32.0 * GAMMA)).astype(np.float32))
    d5 = d4 * np.float32(float.fromhex("0x1.005p-1"))  # the kernel's refined-bound factor
    for label, a4, a5 in (
        ("shipped   (L1 bound)", d4, d5),
        ("min(L1, Cauchy-Schwarz)", np.minimum(d4, cs4), np.minimum(d5, cs5)),
    ):
        _, bbA, liveA = counts(C[4], a4, thr1)
        liveblkA = liveA.reshape(T, NBLOCK, BLOCK).any(axis=2)
        rowmaskA = np.repeat(liveblkA, BLOCK, axis=1)
        liveB = rowmaskA & ((C5.astype(np.float64) + a5) >= thr1[:, None])
        rowsB = liveB.sum(axis=1)
        resid_mb = bbA.mean() * BLOCK * 320 / 1e6
        gemv_mb = rowsB.mean() * H * 2 / 1e6
        print(f"  {label:24s} stage-A blocks {bbA.mean():7.1f} (max {bbA.max():6.0f})"
              f"  stage-B rows {rowsB.mean():6.1f} (max {rowsB.max():5.0f})"
              f"  -> residual {resid_mb:5.2f} MB + BF16 GEMV {gemv_mb:5.2f} MB")
    print()

    share = 0.25 / full_tail_max
    print(f"  For the max-form tail to fit the 1.25x tolerance the UNREAD channels may carry at")
    print(f"  most {share * 100:.2f}% of sum_j |x_j|; the flattest available split (top-15 of 16")
    print(f"  groups) leaves {(1 - cg[:, 14]).max() * 100:.2f}% there. Gap: {(1 - cg[:, 14]).max() / share:.0f}x.")


if __name__ == "__main__":
    main()
