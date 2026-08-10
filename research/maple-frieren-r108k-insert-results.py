#!/usr/bin/env python3
"""Regenerate every sink-derived figure in the R108-K report, idempotently.

Five regions of the report are machine-written from the probe sink, because each
landing probe block moves the fitted values and hand-copied restatements go stale
silently:

  RESULTS     the whole of §3.3, straight from the analyzer's --markdown output
  HEADLINE    the "Both stages, in one screen" Stage 1 table
  PRIZETABLE  §3.5's prize ladder and the fold-reduction sentence under it
  REPRICE     §3.5.1's rule-105.23 critical test between the two decode-pool models
  LADDER      §3.4.1's two-ladder k/c comparison

Prose outside these regions is deliberately qualitative ("roughly four-fold",
"more than fifteen standard errors") so that it cannot go stale within rounding.

Rerunnable: each region is replaced between its BEGIN/END pair.
"""
import json
import math
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / "maple-frieren-r108k-decode-dispatch-merge.md"
ANALYZER = HERE / "maple-frieren-r108k-barrier-price-analyze.py"
FIGURES = HERE / "artifacts" / "maple-frieren-r108k" / "figures.json"
SINK = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r108k-barrier-price.tsv"
DISPATCHES_PER_STEP = 40  # family E, advisor's corrected n (comment 6)
DECODE_WEIGHT = 0.75
ASSUMED_K = 1.890

# Campaign constants for the 105.23 critical test, taken verbatim from the advisor's
# comments 2 and 3 so this script's arithmetic can be checked against their own tables.
RECORD_GAP = 1.6359          # rule 101 unbiased gap to the record, % of cs
RESUBMIT_SIGMA = 0.3016      # fixed-tree resubmission noise, % of cs
DRAW_BAR = 0.400             # one draw bar, % of cs
SLACK_BARS = {"D": 0.71, "A": 0.45, "C": 0.03, "B": 0.00, "E": 1.89}  # 105.16
PROGRAMME_DISPATCHES = 168   # 105.17 per-layer dispatches in the whole programme
PROGRAMME_M5_US = 2.3403     # rule 65 price per dispatch, M5 µs
PCT_PER_M5_US = 0.015228     # 105.17's µs/step -> % of cs constant


def run(*args):
    return subprocess.run(
        [sys.executable, str(ANALYZER), SINK, *args],
        capture_output=True, text=True, check=True,
    ).stdout


def grab(pattern, text, what):
    m = re.search(pattern, text, flags=re.S)
    if not m:
        sys.exit(f"analyzer output does not expose {what}; refusing to write stale figures")
    return m.groups()


plain = run()
control = float(grab(r"mean\(C\)=([\d.]+)", plain, "the control mean")[0])
k, k_lo, k_hi, b_low, b_high, sd, df, c_layer, c_step = grab(
    r"unchained / concurrent \(F -> H\): k = ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]"
    r".*?\(B=(\d+),(\d+)\).*?pooled sd ([\d.]+) us, df (\d+)\]"
    r".*?c = ([+-][\d.]+) us per layer \(([+-][\d.]+) us/step",
    plain, "the unchained rung-difference fit")
ck, ck_lo, ck_hi, cc_layer, cc_step = grab(
    r"chained / serialized \(S -> J\): k = ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]"
    r".*?c = ([+-][\d.]+) us per layer \(([+-][\d.]+) us/step",
    plain, "the chained rung-difference fit")
bar_b, bar, bar_lo, bar_hi = grab(
    r"dS - dF \(paired\).*?B=(\d+).*?-> barrier price\s+"
    r"([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]", plain, "the N=160 barrier price")
bar_hi_rung, = grab(
    r"dJ - dH \(paired\).*?-> barrier price\s+([+-][\d.]+) M4 us/barrier", plain,
    "the N=1200 barrier price")
f_slope, f_lo, f_hi = grab(
    r"dF \(no barrier\).*?-> slope\s+([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]", plain,
    "the single-rung arm-F slope")
mechanical, = grab(r"## verdict.*?\n\s+(P-[A-Z-]+)", plain, "the mechanical §5 verdict")


def prize(value):
    us = float(value) * DISPATCHES_PER_STEP
    pct = 100.0 * us / control
    return us, pct, pct * DECODE_WEIGHT


def num(value, digits=3, sign=False):
    """Format with the U+2212 minus the rest of the report uses, not ASCII hyphen."""
    spec = f"{'+' if sign else ''}.{digits}f"
    return format(float(value), spec).replace("-", "\u2212")


k_us, k_pct, k_score = prize(k)
lo_us, lo_pct, lo_score = prize(k_lo)
hi_us, hi_pct, hi_score = prize(k_hi)
fold = ASSUMED_K / float(k)
c_span = sorted((float(c_layer), float(cc_layer)))
step_span = sorted((abs(float(c_step)), abs(float(cc_step))))
pct_span = [100.0 * v / control for v in step_span]

HEADLINE = f"""\
| | Stage 1 answer |
|---|---|
| **Reported verdict** | **`P-INDETERMINATE`** — the identified per-dispatch price lands inside comment 6's undecided 0.3–0.8 band. One verdict only; §3.3 discloses that the mechanical §5 estimator prints `{mechanical}` and §3.2.1 proves why that estimator is degenerate and must not be believed. |
| **Per-dispatch price** | **`k = {num(k)}` M4 µs/dispatch, CI95 `[{num(k_lo)}, {num(k_hi)}]`** from the unchained ladder; `{num(ck)} [{num(ck_lo)}, {num(ck_hi)}]` from the chained ladder, *independently*. Two ladders, one number. |
| **Barrier price** | **≈ 0, at both rungs.** `{num(bar, sign=True)} [{num(bar_lo, sign=True)}, {num(bar_hi, sign=True)}]` µs/barrier at N=160 (B={bar_b}); `{num(bar_hi_rung, 4, sign=True)}` µs/barrier at N=1200 (n=1). Serialising the injected chain costs nothing measurable — the free-region claim survives, but as a *barrier* claim, not a dispatch claim. |
| **Merge prize, repriced** | {DISPATCHES_PER_STEP} dispatches/step × `k` = **{k_us:.1f} M4 µs/step = {k_pct:.2f} % decode = {k_score:.2f} % score** (interval {lo_score:.2f}–{hi_score:.2f} %). At the assumed `k = {ASSUMED_K:.3f}` it would have been {prize(ASSUMED_K)[2]:.2f} %. |
| **Pre-registered predictions** | 1 of 3 **refuted** (P1, by 3.2×), 1 discriminated as intended (P2: `k = 0` dead by more than fifteen standard errors), 1 sign-confirmed and size-wrong (P3). §3.3 scores all three and names the root cause: the pre-registration anchored its fit on a rung that turned out to be off the line. |
| **Accidental finding** | the intercept is **negative and large**: `c ≈ {num(c_span[0], 1)} to {num(c_span[1], 1)}` µs *per layer*, i.e. adding one `asyncEval` commit boundary per layer at zero added dispatches would make decode **≈ {step_span[0]:.0f}–{step_span[1]:.0f} µs/step ({pct_span[0]:.1f}–{pct_span[1]:.1f} %) faster**. That is an order of magnitude more than the merge prize, it contradicts the campaign's ≈ 30–50 µs-*cost*-per-commit folklore, and it is the follow-up I would rank first. It is also an extrapolation to N=0 from rungs at 160 and 1200 with a tape-split confound, so §3.4.1 states it as a lead to test, not a result. |
| **`Sources/` bytes spent** | **zero.** Both stages are measurement and source reading. |
"""

PRIZETABLE = f"""\
| per-dispatch `k` (M4 µs) | source | merge prize, µs/step | % decode | % score at 0.75 weight |
|---|---|---|---|---|
| `{ASSUMED_K:.3f}` | value the merge was budgeted against | `{prize(ASSUMED_K)[0]:.1f}` | `{prize(ASSUMED_K)[1]:.2f} %` | `{prize(ASSUMED_K)[2]:.2f} %` |
| `0.800` | comment 6's *build* bar | `{prize(0.8)[0]:.1f}` | `{prize(0.8)[1]:.2f} %` | `{prize(0.8)[2]:.2f} %` |
| **`{num(k)}`** | **this probe, identified** | **`{k_us:.1f}`** | **`{k_pct:.2f} %`** | **`{k_score:.2f} %`** |
| `{num(k_lo)}`–`{num(k_hi)}` | its interval | `{lo_us:.1f}`–`{hi_us:.1f}` | `{lo_pct:.2f}`–`{hi_pct:.2f} %` | `{lo_score:.2f}`–`{hi_score:.2f} %` |
| `0.300` | comment 6's *dead* floor | `{prize(0.3)[0]:.1f}` | `{prize(0.3)[1]:.2f} %` | `{prize(0.3)[2]:.2f} %` |

So the measurement cuts the expected prize by **{fold:.1f}×** against the assumption the
programme was costed on, and lands it at ≈{k_score:.2f} % of score. The single-rung arm-F read
alone — the estimator amendment §5 pre-registered — would instead have said
`{num(f_slope, sign=True)} [{num(f_lo, sign=True)}, {num(f_hi, sign=True)}]` and killed the programme; §3.2.1 explains why that
estimator is degenerate and §3.3 reports it anyway.
"""

def p_draw(x):
    """P(one draw beats the record) under rule 101's normal model."""
    return 0.5 * math.erfc(((RECORD_GAP - x) / RESUBMIT_SIGMA) / math.sqrt(2))


def p_two(x):
    return 1.0 - (1.0 - p_draw(x)) ** 2


def check(name, got, want, tol):
    if abs(got - want) > tol:
        sys.exit(f"self-check failed: {name} = {got!r}, expected ~{want!r}")


slack_pct = sum(SLACK_BARS.values()) * DRAW_BAR
dispatch_pct = PROGRAMME_DISPATCHES * PROGRAMME_M5_US * PCT_PER_M5_US
check("105.16 slack", slack_pct, 1.232, 5e-4)
check("105.17 dispatch accounting", dispatch_pct, 5.987, 5e-4)
check("campaign z", RECORD_GAP / RESUBMIT_SIGMA, 5.42, 5e-3)
check("P(>=1 of 2) at 105.16", p_two(slack_pct), 0.172, 5e-4)
check("P(1 draw) at route A", p_draw(1.069), 0.030, 5e-4)

# The reprice is a ratio applied to 105.17's own figure, so it is independent of the
# µs -> % constant. It does assume the M4/M5 dispatch-price ratio implied by the
# campaign's 1.890 M4 <-> 2.3403 M5 conversion carries over unchanged.
repriced = [dispatch_pct * float(v) / ASSUMED_K for v in (k, k_lo, k_hi)]
merge_via_105_17 = dispatch_pct * (DISPATCHES_PER_STEP / PROGRAMME_DISPATCHES) * float(k) / ASSUMED_K
denominator_gap = merge_via_105_17 / k_score

REPRICE = f"""\
| model of the decode pool | whole-programme gain, % of `cs` | P(1 draw) | P(≥1 of 2 draws) |
|---|---|---|---|
| 105.16 measured non-byte slack ({sum(SLACK_BARS.values()):.2f} bars) | `{slack_pct:.3f}` | `{p_draw(slack_pct):.3f}` | `{p_two(slack_pct):.3f}` |
| 105.17 dispatch accounting at the **assumed** `{ASSUMED_K:.3f}` M4 µs | `{dispatch_pct:.3f}` | `{p_draw(dispatch_pct):.3f}` | `{p_two(dispatch_pct):.3f}` |
| **105.17 repriced at this probe's `k`** | **`{repriced[0]:.3f}`** `[{repriced[1]:.3f}, {repriced[2]:.3f}]` | `{p_draw(repriced[0]):.3f}` | `{p_two(repriced[0]):.3f}` |
| this one merge alone ({DISPATCHES_PER_STEP} of {PROGRAMME_DISPATCHES} dispatches) | `{k_score:.3f}` (§3.5) or `{merge_via_105_17:.3f}` via 105.17's constant | `{p_draw(k_score):.1e}`–`{p_draw(merge_via_105_17):.1e}` | `{p_two(k_score):.1e}`–`{p_two(merge_via_105_17):.1e}` |

**The {dispatch_pct / slack_pct:.2f}× disagreement collapses to {repriced[0] / slack_pct:.2f}×.** Comment 3 set the two models
{dispatch_pct / slack_pct:.2f}× apart and asked which was wrong. The answer is that almost the whole gap was the
*assumed price of a dispatch*, not the dispatch count: substituting the measured `k` moves
105.17 from `{dispatch_pct:.3f} %` to `{repriced[0]:.3f} %`, which is within {100 * (repriced[0] / slack_pct - 1):.0f} % of 105.16's `{slack_pct:.3f} %`. Neither
model is falsified; they now agree, and they agree on a **small** number.
"""

LADDER = f"""\
| ladder | rungs used | `k`, M4 µs/dispatch | `c`, µs/layer | `40·c`, µs/step |
|---|---|---|---|---|
| unchained (`F`→`H`) | 160, 1200 | `{num(k, sign=True)} [{num(k_lo)}, {num(k_hi)}]` | `{num(c_layer, 2)}` | `{num(c_step, 0)}` |
| chained (`S`→`J`) | 160, 1200 | `{num(ck, sign=True)} [{num(ck_lo)}, {num(ck_hi)}]` | `{num(cc_layer, 2)}` | `{num(cc_step, 0)}` |
"""

results = run("--markdown")
results_block = results[results.index("## §3.3 Results"):].rstrip() + "\n"

REGIONS = {
    "RESULTS": results_block,
    "HEADLINE": HEADLINE,
    "PRIZETABLE": PRIZETABLE,
    "REPRICE": REPRICE,
    "LADDER": LADDER,
}

text = REPORT.read_text()
for name, payload in REGIONS.items():
    begin, end = f"<!--{name}:BEGIN-->\n", f"<!--{name}:END-->\n"
    if begin not in text or end not in text:
        sys.exit(f"report is missing the {name} BEGIN/END markers; add them first")
    text = re.sub(
        re.escape(begin) + ".*?" + re.escape(end),
        lambda _m, p=payload, b=begin, e=end: b + p + e,
        text, flags=re.S,
    )
REPORT.write_text(text)

rows = results.split("usable rows ")[1].split(",")[0]
verdict = [ln for ln in results.splitlines() if "P-" in ln and ln.startswith("**")][-1]

FIGURES.parent.mkdir(parents=True, exist_ok=True)
FIGURES.write_text(json.dumps({
    "usable_rows": int(rows),
    "control_us_per_step": control,
    "pooled_sd_us": float(sd),
    "pooled_sd_df": int(df),
    "blocks_low_rung": int(b_low),
    "blocks_high_rung": int(b_high),
    "k_unchained": float(k), "k_unchained_lo": float(k_lo), "k_unchained_hi": float(k_hi),
    "k_chained": float(ck), "k_chained_lo": float(ck_lo), "k_chained_hi": float(ck_hi),
    "c_unchained_us_per_layer": float(c_layer), "c_unchained_us_per_step": float(c_step),
    "c_chained_us_per_layer": float(cc_layer), "c_chained_us_per_step": float(cc_step),
    "barrier_160": float(bar), "barrier_160_lo": float(bar_lo),
    "barrier_160_hi": float(bar_hi), "barrier_160_blocks": int(bar_b),
    "barrier_1200": float(bar_hi_rung),
    "single_rung_f_slope": float(f_slope),
    "single_rung_f_slope_lo": float(f_lo), "single_rung_f_slope_hi": float(f_hi),
    "merge_prize_us_per_step": k_us,
    "merge_prize_pct_decode": k_pct,
    "merge_prize_pct_score": k_score,
    "merge_prize_pct_score_lo": lo_score, "merge_prize_pct_score_hi": hi_score,
    "assumed_k": ASSUMED_K,
    "assumed_prize_pct_score": prize(ASSUMED_K)[2],
    "fold_reduction_vs_assumed": fold,
    "dispatches_per_step": DISPATCHES_PER_STEP,
    "reprice_105_16_slack_pct": slack_pct,
    "reprice_105_17_assumed_pct": dispatch_pct,
    "reprice_105_17_measured_pct": repriced[0],
    "reprice_105_17_measured_pct_lo": repriced[1],
    "reprice_105_17_measured_pct_hi": repriced[2],
    "reprice_model_gap_assumed": dispatch_pct / slack_pct,
    "reprice_model_gap_measured": repriced[0] / slack_pct,
    "p_draw_105_16": p_draw(slack_pct),
    "p_draw_105_17_assumed": p_draw(dispatch_pct),
    "p_draw_105_17_measured": p_draw(repriced[0]),
    "p_two_105_17_measured": p_two(repriced[0]),
    "merge_pct_via_105_17": merge_via_105_17,
    "decode_denominator_gap": denominator_gap,
    "mechanical_verdict": mechanical,
    "reported_verdict": "P-INDETERMINATE",
    "analyzer_plain": plain,
}, indent=2) + "\n")
print(f"regenerated {', '.join(REGIONS)} from {rows} usable rows "
      f"(control {control:.1f} us/step, pooled sd {sd} us df {df}, B={b_low},{b_high})")
print(f"k unchained = {k} [{k_lo}, {k_hi}] -> {k_us:.1f} us/step, "
      f"{k_score:.2f} % score, {fold:.1f}x fold")
print(f"reprice: 105.16 = {slack_pct:.3f} %, 105.17 assumed = {dispatch_pct:.3f} % "
      f"({dispatch_pct / slack_pct:.2f}x), 105.17 measured = {repriced[0]:.3f} % "
      f"({repriced[0] / slack_pct:.2f}x); this merge {k_score:.3f} % or "
      f"{merge_via_105_17:.3f} % ({denominator_gap:.2f}x denominator gap)")
print(f"mechanical verdict: {verdict}")
