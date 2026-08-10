#!/usr/bin/env python3
"""R108-K barrier-region price probe — the analysis fixed by prereg amendment 1 sec 4.

Reads the TSV appended by research/maple-frieren-r108k-barrier-region-price.sh and
emits, per rung, the block-paired difference against that block's own control anchor,
Student-t CI95 (no normal approximation at B <= 6), the per-dispatch slope, and the
paired barrier separation dS-dF / dJ-dH.

Nothing here is chosen after seeing numbers: arms, rungs, estimands, the t
interval, the no-outlier-rejection rule and the verdict table are all from the
amendment, which was committed before the first timing run.

Usage: python3 research/maple-frieren-r108k-barrier-price-analyze.py [TSV]
"""
import math
import statistics
import sys
from collections import defaultdict

# amendment sec 3: r93-A's K=2400 chained rung measured +3121 us/step; the guard is
# deliberately far below it so that it tests channel liveness, not reproduction.
GAUGE_MIN_US = 500.0
# amendment sec 5: the advisor's decision band from PR #660 comment 6.
FREE_BAND_HI = 0.3
TAX_BAND_LO = 0.8
# amendment sec 4: rungs are (arm_free, arm_serial, N).
RUNGS = [("F", "S", 160), ("H", "J", 1200)]

# Student t, two-sided 0.975, df 1..30 then the normal limit.
T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
}


def t975(df):
    if df <= 0:
        return float("nan")
    return T975.get(df, 1.960)


def ci95(xs):
    """mean and Student-t CI95 half-width of a sample. Half-width is nan at n=1."""
    n = len(xs)
    if n == 0:
        return float("nan"), float("nan"), 0
    m = statistics.fmean(xs)
    if n == 1:
        return m, float("nan"), 1
    hw = t975(n - 1) * statistics.stdev(xs) / math.sqrt(n)
    return m, hw, n


def fmt(m, hw, unit=""):
    if math.isnan(m):
        return "n/a"
    if math.isnan(hw):
        return f"{m:+.4g}{unit} (n=1, no CI)"
    return f"{m:+.4g} [{m - hw:+.4g}, {m + hw:+.4g}]{unit}"


def load(path):
    rows, voided = [], []
    with open(path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            r = dict(zip(header, parts))
            # amendment sec 4: rows with passed_correctness != true or a missing
            # score.json are voided and NAMED. No silent drops.
            if r["decode_s_per_token"] == "NA" or r["passed"] != "true":
                voided.append(r)
                continue
            r["dec_us"] = float(r["decode_s_per_token"]) * 1e6
            r["pre_us"] = float(r["prefill_s_per_token"]) * 1e6
            r["block"] = int(r["block"])
            rows.append(r)
    return rows, voided


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r108k-barrier-price.tsv"
    rows, voided = load(path)

    by_block = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_block[r["block"]][r["arm"]].append(r["dec_us"])
        # "<arm>p" holds the same row's prefill, used only by the post-hoc
        # drift control. The pre-registered estimators never read these keys.
        by_block[r["block"]][r["arm"] + "p"].append(r["pre_us"])

    print(f"# R108-K barrier-region price probe — {path}")
    print(f"# usable rows {len(rows)}, voided {len(voided)}")
    for r in voided:
        print(f"#   VOIDED idx={r['idx']} arm={r['arm']} passed={r['passed']} "
              f"err={r.get('error','')}")

    print("\n## raw levels (M4 us/step, decode_seconds_per_token x 1e6)")
    print("block arm  N     chain  decode_us   prefill_us")
    for r in rows:
        print(f"{r['block']:>5} {r['arm']:<3} {r['inject']:<5} {r['chain']:<6} "
              f"{r['dec_us']:>10.1f}  {r['pre_us']:>10.2f}")

    # sec 3: the gauge is the provenance guard. Its comparator is every control row
    # in the campaign, because the gauge is block 0 and carries no anchor of its own.
    controls = [d for b in by_block for d in by_block[b].get("C", [])]
    gauge = by_block.get(0, {}).get("G", [])
    print("\n## gauge (amendment sec 3)")
    if not gauge or not controls:
        print(f"  INDETERMINATE: gauge rows {len(gauge)}, control rows {len(controls)}")
        gauge_ok = None
    else:
        g_eff = statistics.fmean(gauge) - statistics.fmean(controls)
        gauge_ok = g_eff >= GAUGE_MIN_US
        print(f"  mean(G)={statistics.fmean(gauge):.1f}  mean(C)={statistics.fmean(controls):.1f}"
              f"  effect={g_eff:+.1f} us/step  ({g_eff / 2400:+.4f} us/dispatch)")
        print(f"  threshold >= {GAUGE_MIN_US:+.0f} us/step -> "
              f"{'PASS (channel live)' if gauge_ok else 'FAIL -> P-INSTRUMENT-DEAD'}")

    print("\n## rungs — block-paired against that block's own control anchor")
    slopes = {}
    for free, ser, n in RUNGS:
        d_free, d_ser, d_sep, used = [], [], [], []
        for b in sorted(by_block):
            if b == 0:
                continue
            arms = by_block[b]
            if "C" not in arms:
                continue
            c = statistics.fmean(arms["C"])
            has = False
            if free in arms:
                d_free.append(statistics.fmean(arms[free]) - c)
                has = True
            if ser in arms:
                d_ser.append(statistics.fmean(arms[ser]) - c)
                has = True
            if free in arms and ser in arms:
                # sec 4: separation is tested PAIRED WITHIN BLOCK, never by
                # comparing two independent CIs.
                d_sep.append(statistics.fmean(arms[ser]) - statistics.fmean(arms[free]))
            if has:
                used.append(b)
        print(f"\n### rung N={n}  (arm {free} unchained / arm {ser} chained), blocks {used}")
        for label, ds in ((f"d{free} (no barrier)", d_free), (f"d{ser} (barrier/no-op)", d_ser)):
            m, hw, k = ci95(ds)
            if k == 0:
                print(f"  {label:<24} no blocks")
                continue
            print(f"  {label:<24} {fmt(m, hw, ' us/step')}   B={k}")
            sm, shw = m / n, hw / n
            print(f"  {'-> slope':<24} {fmt(sm, shw, ' M4 us/dispatch')}")
            slopes[label] = (sm, shw, k)
        m, hw, k = ci95(d_sep)
        if k:
            print(f"  {'d' + ser + ' - d' + free + ' (paired)':<24} {fmt(m, hw, ' us/step')}   B={k}")
            print(f"  {'-> barrier price':<24} {fmt(m / n, hw / n, ' M4 us/barrier')}")

    # sec 5: the verdict table, applied mechanically to arm F's 160 rung.
    print("\n## verdict (amendment sec 5, applied mechanically)")
    key = "dF (no barrier)"
    if gauge_ok is False:
        print("  P-INSTRUMENT-DEAD — gauge failed; no slope is reportable.")
    elif key not in slopes:
        print("  P-INDETERMINATE-UNDERPOWERED — no complete 160-rung block.")
    else:
        sm, shw, k = slopes[key]
        lo, hi = (sm - shw, sm + shw) if not math.isnan(shw) else (sm, sm)
        n_blocks = k
        if n_blocks < 4:
            print(f"  P-INDETERMINATE-UNDERPOWERED — {n_blocks} block(s) < 4 required; "
                  f"arm F slope {fmt(sm, shw, ' M4 us/dispatch')}")
        elif hi <= FREE_BAND_HI:
            print(f"  P-FREE-REGION-CONFIRMED — arm F CI95 upper {hi:+.4g} "
                  f"<= {FREE_BAND_HI}: the dispatch-count merge programme is dead.")
        elif lo >= TAX_BAND_LO:
            print(f"  P-LAUNCH-TAX-CONFIRMED — arm F CI95 lower {lo:+.4g} "
                  f">= {TAX_BAND_LO}: 105.17 survives, build the merge.")
        else:
            print(f"  P-INDETERMINATE — arm F slope {fmt(sm, shw, ' M4 us/dispatch')} "
                  f"straddles the {FREE_BAND_HI}-{TAX_BAND_LO} band.")
        if gauge_ok is None:
            print("  (gauge not yet complete — this verdict is provisional)")

    # sec 6: prefill must not move. DARKBLOOM_INJECT_PREFILL_EMPTY stays 0.
    print("\n## falsification check — prefill must not move (sec 6)")
    pf = defaultdict(list)
    for r in rows:
        pf[r["arm"]].append(r["pre_us"])
    if not pf.get("C"):
        for arm in sorted(pf):
            print(f"  arm {arm}: prefill {statistics.fmean(pf[arm]):.2f} us/token  "
                  f"(no control anchor yet)")
        return
    base = statistics.fmean(pf["C"])
    for arm in sorted(pf):
        m = statistics.fmean(pf[arm])
        print(f"  arm {arm}: prefill {m:.2f} us/token  "
              f"delta vs C {m - base:+.3f} ({100 * (m - base) / base:+.3f} %)")

    drift_diagnostic(by_block)


def drift_diagnostic(by_block):
    """POST-HOC, NOT PRE-REGISTERED, NOT part of any verdict.

    The injection knob is decode-only, so prefill cannot respond to it. Any prefill
    move inside a block is therefore pure host drift, and to first order the same
    drift multiplies decode. Subtracting the prefill percentage from the decode
    percentage removes that common-mode term. Reported only to show whether a
    pre-registered decode difference is drift or signal; it never overrides sec 5.
    """
    print("\n## POST-HOC drift control (exploratory — prefill as common-mode gauge)")
    print("  arm-vs-own-control, per block: decode %delta, prefill %delta, difference")
    per_rung = defaultdict(list)
    for b in sorted(by_block):
        if b == 0 or "C" not in by_block[b]:
            continue
        cd = statistics.fmean(by_block[b]["C"])
        cp = statistics.fmean(by_block[b]["Cp"]) if "Cp" in by_block[b] else None
        if cp is None:
            continue
        for free, ser, n in RUNGS:
            for arm in (free, ser):
                if arm not in by_block[b] or arm + "p" not in by_block[b]:
                    continue
                dpct = 100 * (statistics.fmean(by_block[b][arm]) - cd) / cd
                ppct = 100 * (statistics.fmean(by_block[b][arm + "p"]) - cp) / cp
                corr_us = (dpct - ppct) / 100 * cd
                per_rung[(arm, n)].append(corr_us / n)
                print(f"  block {b} arm {arm}: decode {dpct:+.3f} %  "
                      f"prefill {ppct:+.3f} %  diff {dpct - ppct:+.3f} %  "
                      f"-> {corr_us / n:+.4f} us/dispatch")
    if not per_rung:
        print("  (no block has both a control and a treatment prefill row yet)")
        return
    print("  drift-corrected slopes:")
    for (arm, n), xs in sorted(per_rung.items()):
        m, hw, k = ci95(xs)
        print(f"    arm {arm} N={n}: {fmt(m, hw, ' us/dispatch')}   B={k}")


if __name__ == "__main__":
    main()
