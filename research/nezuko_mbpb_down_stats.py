#!/usr/bin/env python3
"""Evaluate research/nezuko-mbpb-down.log against the r3 pre-registered rule.

The rule is fixed in research/nezuko-mbcap-down-prereg.md and was committed
before the sweep ran. This script only applies it.

  statistic  G(cap)  mean per-steady-step gap = wall - gpu_busy_union
  contrast   dG(cap) = G(cap) - G(200), Welch t at n = 4 per level
  validity   W(50) < W(200) on the same profiled binary, |t| >= 3
  CONFIRM    G(200) is the strict minimum, and dG(50) > 0 at t >= 3,
             and dG(400) > 0 at t >= 3
  REFUTE     dG(50) <= 0 or |t(50)| < 3
  AMBIGUOUS  pooled within-level sd of G > 0.05 ms, or all |t| < 3

  python3 research/nezuko_mbpb_down_stats.py research/nezuko-mbpb-down.log
"""
import argparse
import math
import re
import statistics
import sys
from collections import defaultdict

ARM = re.compile(r"^=== cap=(\d+) mode=(\w+) tag=(\S+)")
STEP = re.compile(
    r"^cap=(\d+) (\w+) (\S+) per steady step: wall=([\d.]+) ms "
    r"gpu_busy_sum=([\d.]+) ms gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms "
    r"\(([\d.]+)% of wall\) cbs=([\d.]+) dispatches=([\d.]+)")
PEAK = re.compile(r"^cap=(\d+) (\w+) (\S+) .*mlx_peak_gb[\"']?[:= ]+([\d.]+)")
DIV = re.compile(r"^cap=(\d+) (\w+) (\S+) .*divergence")
TOTAL = re.compile(
    r"^cap=(\d+) (\w+) (\S+) profile: (\d+) command buffers total, "
    r"(\d+) inside (\d+) steady steps")


def welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan")
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    d = statistics.fmean(a) - statistics.fmean(b)
    if se == 0.0:
        return d, float("inf") if d else 0.0
    return d, d / se


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    args = ap.parse_args()

    rows = []
    divergences = []
    peaks = defaultdict(list)
    totals = defaultdict(list)
    with open(args.log, errors="replace") as fh:
        for line in fh:
            m = TOTAL.match(line)
            if m:
                if m[3] != "warmup-discard":
                    totals[(int(m[1]), m[2])].append(int(m[4]))
                continue
            m = STEP.match(line)
            if m:
                rows.append(dict(
                    cap=int(m[1]), mode=m[2], tag=m[3], wall=float(m[4]),
                    bsum=float(m[5]), union=float(m[6]), gap=float(m[7]),
                    cbs=float(m[9]), disp=float(m[10])))
                continue
            m = PEAK.match(line)
            if m:
                peaks[(int(m[1]), m[2])].append(float(m[4]))
                continue
            m = DIV.match(line)
            if m and "divergence" in line:
                divergences.append(line.rstrip())

    dec = [r for r in rows if r["mode"] == "decode" and r["tag"] != "warmup-discard"]
    warm = [r for r in rows if r["tag"] == "warmup-discard"]
    pre = [r for r in rows if r["mode"] == "prefill"]
    if not dec:
        print("no decode arms parsed", file=sys.stderr)
        return 1

    caps = sorted({r["cap"] for r in dec})
    by = {c: [r for r in dec if r["cap"] == c] for c in caps}

    print(f"warm-up arms discarded: {len(warm)}")
    if warm:
        w = warm[0]
        print(f"  cap={w['cap']} wall={w['wall']:.3f} union={w['union']:.3f} "
              f"gap={w['gap']:.3f} cbs={w['cbs']:.1f}")
    print(f"divergence lines: {len(divergences)}")
    for d in divergences[:6]:
        print("  " + d)

    print("\n== per-level decode means (n arms) ==")
    print(f"{'cap':>5} {'n':>2} {'wall':>8} {'sd':>6} {'union':>8} {'sd':>6} "
          f"{'gap G':>8} {'sd':>6} {'cbs':>6} {'disp':>6} {'gap*cbs':>8}")
    for c in caps:
        g = by[c]
        f = lambda k: statistics.fmean([r[k] for r in g])
        s = lambda k: statistics.stdev([r[k] for r in g]) if len(g) > 1 else 0.0
        print(f"{c:5d} {len(g):2d} {f('wall'):8.3f} {s('wall'):6.3f} "
              f"{f('union'):8.3f} {s('union'):6.3f} {f('gap'):8.4f} "
              f"{s('gap'):6.4f} {f('cbs'):6.1f} {f('disp'):6.1f} "
              f"{f('gap') * f('cbs'):8.3f}")

    ref = 200
    if ref not in by:
        print("no cap=200 anchor", file=sys.stderr)
        return 1
    gref = [r["gap"] for r in by[ref]]
    wref = [r["wall"] for r in by[ref]]

    print("\n== contrasts vs cap=200 (Welch t, n=4) ==")
    print(f"{'cap':>5} {'dG ms':>9} {'t(G)':>7} {'dW ms':>9} {'t(W)':>7} "
          f"{'dW %':>7} {'dU ms':>9} {'t(U)':>7}")
    res = {}
    for c in caps:
        if c == ref:
            continue
        dg, tg = welch([r["gap"] for r in by[c]], gref)
        dw, tw = welch([r["wall"] for r in by[c]], wref)
        du, tu = welch([r["union"] for r in by[c]],
                       [r["union"] for r in by[ref]])
        pct = dw / statistics.fmean(wref) * 100
        res[c] = dict(dg=dg, tg=tg, dw=dw, tw=tw, pct=pct, du=du, tu=tu)
        print(f"{c:5d} {dg:+9.4f} {tg:+7.2f} {dw:+9.4f} {tw:+7.2f} "
              f"{pct:+7.3f} {du:+9.4f} {tu:+7.2f}")

    pooled = math.sqrt(statistics.fmean(
        [statistics.variance([r["gap"] for r in by[c]]) for c in caps
         if len(by[c]) > 1]))
    print(f"\npooled within-level sd of G = {pooled:.4f} ms "
          f"(AMBIGUOUS threshold 0.05)")

    print("\n== pass (thermal drift) effect: decode wall by pass, all caps ==")
    tags = sorted({r["tag"] for r in dec})
    print(f"{'tag':>4} {'n':>2} {'mean wall':>10} {'mean-of-level-mean':>20}")
    lvl = {c: statistics.fmean([r["wall"] for r in by[c]]) for c in caps}
    for t in tags:
        g = [r for r in dec if r["tag"] == t]
        centred = statistics.fmean([r["wall"] - lvl[r["cap"]] for r in g])
        print(f"{t:>4} {len(g):2d} {statistics.fmean([r['wall'] for r in g]):10.3f}"
              f" {centred:+20.4f}")
    span = max(statistics.fmean([r["wall"] - lvl[r["cap"]]
                                 for r in dec if r["tag"] == t]) for t in tags)
    span -= min(statistics.fmean([r["wall"] - lvl[r["cap"]]
                                  for r in dec if r["tag"] == t]) for t in tags)
    print(f"pass-effect span = {span:.4f} ms; |dW(50)| = "
          f"{abs(res[50]['dw']):.4f} ms; ratio = {span / abs(res[50]['dw']):.2f}")

    if totals:
        print("\n== command-buffer totals (determinism + prefill by "
              "differencing) ==")
        print(f"{'cap':>5} {'decode totals':>28} {'prefill':>8} "
              f"{'pre cb/512-tok fwd':>19} {'dec cb/step':>12}")
        for c in caps:
            dt = totals.get((c, "decode"), [])
            pt = totals.get((c, "prefill"), [])
            uniq = sorted(set(dt))
            d = f"{uniq[0]} x{len(dt)}" if len(uniq) == 1 else str(uniq)
            pre_cb = (pt[0] - uniq[0]) if (pt and len(uniq) == 1) else float("nan")
            print(f"{c:5d} {d:>28} {(pt[0] if pt else 0):8d} "
                  f"{pre_cb:19.0f} {statistics.fmean([r['cbs'] for r in by[c]]):12.1f}")

    if pre:
        print("\n== prefill arms (wall/union/gap are decode-phase metrics; "
              "the prefill signal is the count above) ==")
        print(f"{'cap':>5} {'wall':>8} {'union':>8} {'gap':>8} {'cbs':>7}")
        for r in sorted(pre, key=lambda r: r["cap"]):
            print(f"{r['cap']:5d} {r['wall']:8.3f} {r['union']:8.3f} "
                  f"{r['gap']:8.4f} {r['cbs']:7.1f}")

    if peaks:
        print("\n== mlx_peak_gb ==")
        for k in sorted(peaks):
            v = peaks[k]
            print(f"  cap={k[0]:5d} {k[1]:>7} n={len(v)} "
                  f"mean={statistics.fmean(v):.3f} max={max(v):.3f}")

    print("\n== pre-registered verdict ==")
    gmeans = {c: statistics.fmean([r["gap"] for r in by[c]]) for c in caps}
    wmeans = {c: statistics.fmean([r["wall"] for r in by[c]]) for c in caps}
    argmin = min(gmeans, key=gmeans.get)
    print(f"argmin G = {argmin} MB  (G: " +
          ", ".join(f"{c}:{gmeans[c]:.4f}" for c in caps) + ")")
    print(f"argmin wall = {min(wmeans, key=wmeans.get)} MB")

    ok_valid = 50 in res and res[50]["dw"] < 0 and abs(res[50]["tw"]) >= 3
    print(f"session validity  W(50) < W(200) at |t|>=3 : {ok_valid} "
          f"(dW={res.get(50, {}).get('dw', float('nan')):+.4f} ms, "
          f"t={res.get(50, {}).get('tw', float('nan')):+.2f})")

    if pooled > 0.05 or all(abs(res[c]["tg"]) < 3 for c in res):
        if pooled > 0.05:
            print("VERDICT: AMBIGUOUS (pooled sd of G above threshold)")
        else:
            print("VERDICT: AMBIGUOUS (no significant G contrast anywhere)")
        return 0

    r50 = res.get(50)
    r400 = res.get(400)
    if r50 and r50["dg"] > 0 and r50["tg"] >= 3 and argmin == ref \
            and r400 and r400["dg"] > 0 and r400["tg"] >= 3:
        print("VERDICT: CONFIRM  gap ranks the caps like ranked M5; "
              "clause 3 stands and the proxy is adopted.")
    else:
        one_sided = bool(r400 and r400["dg"] > 0 and r400["tg"] >= 3)
        print("VERDICT: REFUTE  gap does not reproduce the downward branch.")
        print(f"  ONE-SIDED hazard flag (dG(400) > 0 at t>=3): {one_sided}")
        print("  Pre-registered action: retire clause 3 as a general proxy; "
              "keep it at most as an upward-only hazard screen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
