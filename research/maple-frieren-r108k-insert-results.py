#!/usr/bin/env python3
"""Regenerate every sink-derived figure in the R108-K report, idempotently.

Four regions of the report are machine-written from the probe sink, because each
landing probe block moves the fitted values and hand-copied restatements go stale
silently:

  RESULTS     the whole of §3.3, straight from the analyzer's --markdown output
  HEADLINE    the "Both stages, in one screen" Stage 1 table
  PRIZETABLE  §3.5's prize ladder and the fold-reduction sentence under it

Prose outside these regions is deliberately qualitative ("roughly four-fold",
"more than fifteen standard errors") so that it cannot go stale within rounding.

Rerunnable: each region is replaced between its BEGIN/END pair.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / "maple-frieren-r108k-decode-dispatch-merge.md"
ANALYZER = HERE / "maple-frieren-r108k-barrier-price-analyze.py"
SINK = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r108k-barrier-price.tsv"
DISPATCHES_PER_STEP = 40  # family E, advisor's corrected n (comment 6)
DECODE_WEIGHT = 0.75
ASSUMED_K = 1.890


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
print(f"regenerated {', '.join(REGIONS)} from {rows} usable rows "
      f"(control {control:.1f} us/step, pooled sd {sd} us df {df}, B={b_low},{b_high})")
print(f"k unchained = {k} [{k_lo}, {k_hi}] -> {k_us:.1f} us/step, "
      f"{k_score:.2f} % score, {fold:.1f}x fold")
print(f"mechanical verdict: {verdict}")
