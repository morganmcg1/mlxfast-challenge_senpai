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


RESULTS = {"rungs": {}, "drift": {}}


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = argv[0] if argv else "/tmp/r108k-barrier-price.tsv"
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
        RESULTS["gauge"] = (g_eff, g_eff / 2400, gauge_ok)

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
        RESULTS["rungs"][n] = {
            "arms": (free, ser), "blocks": used,
            "free": ci95(d_free), "ser": ci95(d_ser), "sep": (m, hw, k),
        }

    # sec 5: the verdict table, applied mechanically to arm F's 160 rung.
    print("\n## verdict (amendment sec 5, applied mechanically)")
    key = "dF (no barrier)"
    if gauge_ok is False:
        verdict = "P-INSTRUMENT-DEAD — gauge failed; no slope is reportable."
    elif key not in slopes:
        verdict = "P-INDETERMINATE-UNDERPOWERED — no complete 160-rung block."
    else:
        sm, shw, k = slopes[key]
        lo, hi = (sm - shw, sm + shw) if not math.isnan(shw) else (sm, sm)
        if k < 4:
            verdict = (f"P-INDETERMINATE-UNDERPOWERED — {k} block(s) < 4 required; "
                       f"arm F slope {fmt(sm, shw, ' M4 us/dispatch')}")
        elif hi <= FREE_BAND_HI:
            verdict = (f"P-FREE-REGION-CONFIRMED — arm F CI95 upper {hi:+.4g} "
                       f"<= {FREE_BAND_HI}: the dispatch-count merge programme is dead.")
        elif lo >= TAX_BAND_LO:
            verdict = (f"P-LAUNCH-TAX-CONFIRMED — arm F CI95 lower {lo:+.4g} "
                       f">= {TAX_BAND_LO}: 105.17 survives, build the merge.")
        else:
            verdict = (f"P-INDETERMINATE — arm F slope {fmt(sm, shw, ' M4 us/dispatch')} "
                       f"straddles the {FREE_BAND_HI}-{TAX_BAND_LO} band.")
        if gauge_ok is None:
            verdict += "  (gauge not yet complete — this verdict is provisional)"
    print(f"  {verdict}")
    RESULTS["verdict"] = verdict

    # sec 6: prefill must not move. DARKBLOOM_INJECT_PREFILL_EMPTY stays 0.
    print("\n## falsification check — prefill must not move (sec 6)")
    pf = defaultdict(list)
    for r in rows:
        pf[r["arm"]].append(r["pre_us"])
    if not pf.get("C"):
        for arm in sorted(pf):
            print(f"  arm {arm}: prefill {statistics.fmean(pf[arm]):.2f} us/token  "
                  f"(no control anchor yet)")
        return rows, voided
    base = statistics.fmean(pf["C"])
    for arm in sorted(pf):
        m = statistics.fmean(pf[arm])
        print(f"  arm {arm}: prefill {m:.2f} us/token  "
              f"delta vs C {m - base:+.3f} ({100 * (m - base) / base:+.3f} %)")

    drift_diagnostic(by_block)
    per_arm = defaultdict(list)
    for r in rows:
        if not r.get("voided"):
            per_arm[r["arm"]].append(r["dec_us"])
    rung_difference(pooled_scatter(per_arm))
    return rows, voided


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
        RESULTS["drift"][(arm, n)] = ci95(xs)


def pooled_scatter(rows):
    """Pooled within-arm run-to-run SD, for intervals the block bootstrap cannot give.

    The high rung has one block, so the block-paired CI is undefined there. Pooling
    residuals within (arm, N) across the whole session recovers a variance estimate
    with usable df. It ASSUMES equal variance across arms and rungs; the high rung
    injects 30 dispatches/layer against the low rung's 4, so if variance grows with
    injected work this understates the interval. Reported as scatter-propagated,
    never as a block bootstrap.
    """
    ss, df = 0.0, 0
    for key, xs in sorted(rows.items()):
        if len(xs) < 2:
            continue
        m = statistics.fmean(xs)
        ss += sum((x - m) ** 2 for x in xs)
        df += len(xs) - 1
    if df == 0:
        return float("nan"), 0
    return math.sqrt(ss / df), df


def rung_difference(scatter=(float("nan"), 0)):
    """POST-HOC, added after seeing that both injected arms ran FASTER than control.

    Not in the amendment, and it does not override the sec 5 verdict. It exists
    because the pre-registered per-rung estimator is degenerate.

    An injected arm differs from its control in two ways, not one: N extra
    dispatches, and one extra `asyncEval` per layer (`:12143`), which arm C never
    reaches because of the `guard !pending.isEmpty` at `:12142`. So
        d(N) = N*k + 40*c
    with k the per-dispatch cost and c the per-layer eval-boundary cost. One
    equation, two unknowns — a null d(N) can equally mean k=0 or a positive k
    masked by a negative c.

    `lagunaInjectShare` (`:12105-12107`) spreads the total over all 40 layers for
    every rung, so the 40*c term is IDENTICAL at N=160 and N=1200 and cancels:
        k = (d(1200) - d(160)) / 1040
    That is the only estimator here that isolates a true per-dispatch price.
    """
    r = RESULTS["rungs"]
    print("\n## POST-HOC rung-difference estimator (cancels the eval-boundary term)")
    if 160 not in r or 1200 not in r:
        print("  (needs both rungs)")
        return
    for key, what in (("free", "unchained / concurrent (F -> H)"),
                      ("ser", "chained / serialized (S -> J)")):
        m1, h1, k1 = r[160][key]
        m2, h2, k2 = r[1200][key]
        if not k1 or not k2:
            print(f"  {what}: incomplete (B={k1} at 160, B={k2} at 1200)")
            continue
        dn = 1200 - 160
        k = (m2 - m1) / dn
        hw = (math.sqrt(h1 ** 2 + h2 ** 2) / dn
              if not (math.isnan(h1) or math.isnan(h2)) else float("nan"))
        c = (m1 - 160 * k) / 40
        note = ""
        if math.isnan(hw):
            sd, df = scatter
            if df:
                # each block-paired difference is treat-minus-control, var 2*sd^2;
                # a B-block mean divides that by B.
                hw = t975(df) * math.sqrt(2 * sd ** 2 / k2 + 2 * sd ** 2 / k1) / dn
                note = f"  [scatter-propagated, pooled sd {sd:.1f} us, df {df}]"
        print(f"  {what}: k = {fmt(k, hw, ' M4 us/dispatch')}  (B={k1},{k2}){note}")
        print(f"    implied eval-boundary term c = {c:+.2f} us per layer "
              f"({40 * c:+.0f} us/step over 40 layers)")
        RESULTS.setdefault("rungdiff", {})[key] = (k, hw, c, min(k1, k2))
    # Coarser cross-check on the chained ladder using the gauge as a third rung.
    # The gauge effect is measured against POOLED controls, not block-paired, so
    # this is weaker evidence than the S->J difference above.
    if "gauge" in RESULTS and r[160]["ser"][2]:
        g_eff = RESULTS["gauge"][0]
        m1 = r[160]["ser"][0]
        k_ch = (g_eff - m1) / (2400 - 160)
        print(f"  chained cross-check via gauge (S -> G): k = {k_ch:+.4f} M4 us/dispatch"
              f"   implied c = {(m1 - 160 * k_ch) / 40:+.2f} us per layer")
        RESULTS["gauge_xcheck"] = (k_ch, (m1 - 160 * k_ch) / 40)


def markdown(rows, voided):
    """Emit the report-ready sec 3.3 block from the same estimators printed above."""
    out = ["## §3.3 Results", ""]
    out.append(f"`{len(rows)}` usable runs, `{len(voided)}` voided. "
               "Every run is a full `./benchmark.sh --local-submit`, so every row below "
               "also carries an exact-token-ID correctness pass.")
    out += ["", "### Raw levels", "",
            "| block | arm | injected/step | chain | decode µs/step | prefill µs/token | gate |",
            "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['block']} | `{r['arm']}` | {r['inject']} | {r['chain']} | "
                   f"{r['dec_us']:.1f} | {r['pre_us']:.2f} | "
                   f"{'pass' if r['passed'] else 'FAIL'} |")
    if "gauge" in RESULTS:
        eff, per, ok = RESULTS["gauge"]
        out += ["", "### Gauge (liveness only — amendment §3)", "",
                f"Arm `G` (2400 chained) moves decode `{eff:+.1f}` µs/step "
                f"(`{per:+.4f}` µs/dispatch) against the pooled controls; threshold is "
                f"`≥ +500` µs/step ⇒ **{'PASS' if ok else 'FAIL'}**. "
                "This confirms the channel is live and nothing is elided. It is **not** an "
                "estimate of a per-dispatch tax; see §3.4."]
    out += ["", "### Pre-registered estimators (block-paired, Student-t CI95)", "",
            "| rung | estimator | µs/step | slope, M4 µs/dispatch | blocks |",
            "|---|---|---|---|---|"]
    for n, d in sorted(RESULTS["rungs"].items()):
        free, ser = d["arms"]
        for label, key in ((f"d{free} — concurrent, no barrier", "free"),
                           (f"d{ser} — serialized, barrier per dispatch", "ser")):
            m, hw, k = d[key]
            if not k:
                out.append(f"| {n} | {label} | — | no complete block | 0 |")
                continue
            out.append(f"| {n} | {label} | {fmt(m, hw)} | {fmt(m / n, hw / n)} | {k} |")
        m, hw, k = d["sep"]
        if k:
            out.append(f"| {n} | **d{ser} − d{free}, paired ⇒ barrier price** | "
                       f"{fmt(m, hw)} | {fmt(m / n, hw / n)} /barrier | {k} |")
    if RESULTS["drift"]:
        out += ["", "### Post-hoc drift control (exploratory, not pre-registered)", "",
                "Injection is decode-only, so any prefill move within a block is host "
                "drift that also multiplies decode. Subtracting it removes the "
                "common-mode term.", "",
                "| arm | rung | drift-corrected slope, M4 µs/dispatch | blocks |",
                "|---|---|---|---|"]
        for (arm, n), (m, hw, k) in sorted(RESULTS["drift"].items()):
            out.append(f"| `{arm}` | {n} | {fmt(m, hw)} | {k} |")
    if RESULTS.get("rungdiff") or RESULTS.get("gauge_xcheck"):
        out += ["", "### Post-hoc rung-difference estimator (the decisive one)", "",
                "An injected arm differs from its control by `N` dispatches **and** by one "
                "`asyncEval` per layer (`:12143`), which arm `C` never reaches "
                "(`guard !pending.isEmpty`, `:12142`). So `d(N) = N·k + 40·c`: one equation, "
                "two unknowns, and a null `d(N)` is equally consistent with `k = 0` or with a "
                "positive `k` masked by a negative `c`. `lagunaInjectShare` "
                "(`:12105-12107`) spreads every rung over all 40 layers, so `40·c` is "
                "identical at `N = 160` and `N = 1200` and cancels in the difference.", "",
                "| ladder | k, M4 µs/dispatch | implied eval-boundary c | blocks |",
                "|---|---|---|---|"]
        for key, what in (("free", "unchained / concurrent (F→H)"),
                          ("ser", "chained / serialized (S→J)")):
            if key in RESULTS.get("rungdiff", {}):
                k, hw, c, b = RESULTS["rungdiff"][key]
                out.append(f"| {what} | {fmt(k, hw)} | {c:+.2f} µs/layer "
                           f"({40 * c:+.0f} µs/step) | {b} |")
            else:
                out.append(f"| {what} | rung incomplete | — | — |")
        if "gauge_xcheck" in RESULTS:
            k_ch, c = RESULTS["gauge_xcheck"]
            out.append(f"| chained cross-check via gauge (S→G) | {k_ch:+.4f} | "
                       f"{c:+.2f} µs/layer ({40 * c:+.0f} µs/step) | pooled |")
    out += ["", "### Verdict", "", f"**{RESULTS.get('verdict', 'not computed')}**"]
    print("\n".join(out))


if __name__ == "__main__":
    _rows, _voided = main()
    if "--markdown" in sys.argv:
        print()
        markdown(_rows, _voided)
