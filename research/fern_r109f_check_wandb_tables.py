#!/usr/bin/env python3
"""Offline check of the section-7.4 W&B table wiring in the campaign script.

WHY THIS EXISTS.  `fern_r109f_wandb_campaign.py --dry-run` exits 0 without ever
reaching the `run.log({...})` block, so a clean dry-run does NOT prove the
tables are well formed.  Two failure modes have actually bitten this campaign:

  1. a `wandb.Table` column is typed by its FIRST row, so feeding None first
     types the column as None and silently discards every number after it;
  2. add_data() arity drifting away from the declared column list.

Both are invisible until a real W&B run, which costs a network round trip and
pollutes the run history.  This script reproduces the two loops against a fake
Table that asserts on both, and additionally recomputes the CHANNEL_EXACT
summary scalars from the EXACT_BRACKETS rows so the prose numbers and the
machine-readable numbers cannot drift apart.

Exit 0 = wiring is sound.  Usage: python3 research/fern_r109f_check_wandb_tables.py
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.join(HERE, "fern_r109f_wandb_campaign.py")


def load_campaign():
    spec = importlib.util.spec_from_file_location("camp", CAMPAIGN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["camp"] = module
    spec.loader.exec_module(module)
    return module


class FakeTable:
    """A wandb.Table stand-in that enforces the two rules that matter."""

    def __init__(self, columns: list[str]) -> None:
        self.columns = columns
        self.rows: list[tuple] = []
        self.types: tuple[str, ...] | None = None

    def add_data(self, *vals) -> None:
        if len(vals) != len(self.columns):
            raise AssertionError(
                "arity %d != %d columns %s"
                % (len(vals), len(self.columns), self.columns)
            )
        kinds = tuple(type(v).__name__ for v in vals)
        if self.types is None:
            self.types = kinds
            if "NoneType" in kinds:
                bad = [
                    self.columns[i]
                    for i, k in enumerate(kinds)
                    if k == "NoneType"
                ]
                raise AssertionError(
                    "first row types these columns as None: %s" % bad
                )
        else:
            for i, (first, now) in enumerate(zip(self.types, kinds)):
                if first != now and now != "NoneType":
                    raise AssertionError(
                        "col %s: first row %s, later row %s"
                        % (self.columns[i], first, now)
                    )
        self.rows.append(vals)


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def main() -> int:
    camp = load_campaign()
    failures = 0

    # --- table 1: the CHANNEL_EXACT quantity dump ---------------------------
    xt = FakeTable(["quantity", "value_num", "value_text"])
    num = [(k, v) for k, v in camp.CHANNEL_EXACT.items() if is_num(v)]
    txt = [(k, v) for k, v in camp.CHANNEL_EXACT.items() if not is_num(v)]
    for k, v in num:
        xt.add_data(k, float(v), "")
    for k, v in txt:
        xt.add_data(k, None, str(v))
    print(
        "channel_exact_service: rows=%d numeric=%d text=%d"
        % (len(xt.rows), len(num), len(txt))
    )

    # --- table 2: the four exact brackets -----------------------------------
    xb = FakeTable(
        [
            "submission_prefix",
            "service_min",
            "half_width_min",
            "poll_gap_s",
            "age_over_total",
            "owner",
        ]
    )
    for row in camp.EXACT_BRACKETS:
        xb.add_data(*row)
    print("channel_exact_brackets: rows=%d" % len(xb.rows))

    # --- scalars must be rederivable from the rows --------------------------
    # EXACT_BRACKETS carries the tool's 3-decimal DISPLAY values while the
    # CHANNEL_EXACT scalars were computed from full-precision timestamps, so a
    # rounding-scale tolerance is expected and is stated per check rather than
    # hidden in one global epsilon.
    svc = sorted(r[1] for r in camp.EXACT_BRACKETS)
    cluster = [s for s in svc if s < 40.0]
    mean = sum(cluster) / len(cluster)
    sd = (sum((s - mean) ** 2 for s in cluster) / (len(cluster) - 1)) ** 0.5
    ratios = [r[4] for r in camp.EXACT_BRACKETS]
    ce = camp.CHANNEL_EXACT
    checks = [
        ("n_exact", float(len(camp.EXACT_BRACKETS)), ce["n_exact"], 0.0),
        ("n_in_cluster", float(len(cluster)), ce["n_exact_in_run_cluster"], 0.0),
        ("cluster_mean_min", mean, ce["run_cluster_mean_min"], 0.001),
        # sd of three 3-dp values: each input carries +/-0.0005, so the sd can
        # legitimately differ from the full-precision value at the 5e-4 scale.
        ("cluster_sd_min", sd, ce["run_cluster_sd_min"], 0.001),
        ("cluster_cv_pct", 100.0 * sd / mean, ce["run_cluster_cv_pct"], 0.005),
        ("fastest_min", svc[0], ce["fastest_observed_min"], 0.0),
        ("slowest_min", svc[-1], ce["slowest_observed_min"], 0.0),
        (
            "implied_queue_max_min",
            svc[-1] - svc[0],
            ce["implied_queue_wait_max_min"],
            0.001,
        ),
        (
            "length_bias_ratio_mean",
            sum(ratios) / len(ratios),
            ce["length_bias_ratio_mean"],
            0.001,
        ),
        (
            "given_instant_slot_hi",
            svc[-1],
            ce["given_instant_slot_service_min_hi"],
            0.0,
        ),
        (
            "two_estimator_gap_min",
            abs(ce["mtime_estimator_median_min"] - ce["given_instant_slot_median_min"]),
            ce["two_estimator_gap_min"],
            0.005,
        ),
    ]
    print("scalars rederived from EXACT_BRACKETS rows:")
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol
        failures += 0 if ok else 1
        print(
            "  %s %-24s rows->%.4f  dict->%.4f  tol %.4f"
            % ("OK " if ok else "BAD", name, got, want, tol)
        )

    # --- guards that caught real bugs, kept as regressions ------------------
    # The run cluster must not silently absorb the slow member.
    if any(s >= 40.0 for s in cluster):
        print("  BAD run cluster contains a slow member")
        failures += 1
    # A length-bias z below 2 is the whole basis for NOT claiming length bias;
    # if new brackets push it over 2 the write-up must change, so fail loudly.
    if ce["length_bias_significant"] == 0 and ce["length_bias_z"] >= 2.0:
        print("  BAD length_bias_z >= 2 but marked not significant")
        failures += 1
    # 7.4f's headline is that the naive floor test had ZERO power; if a future
    # edit gives it violations without giving it power, that is incoherent.
    if ce["floor_test_naive_power"] == 0 and ce["floor_test_naive_violations"]:
        print("  BAD naive floor test reports violations at zero power")
        failures += 1
    # The powered test must stay a test: n>0 and the strongest proven bound
    # must not exceed the floor it is supposed to be consistent with.
    if ce["floor_test_powered_n"] <= 0:
        print("  BAD powered floor test has no observations")
        failures += 1
    if ce["floor_test_strongest_lower_bound_min"] > ce["fastest_observed_min"]:
        print("  BAD proven lower bound exceeds the fastest observed service")
        failures += 1

    # The retraction count is quoted in three places -- the campaign docstring,
    # the retraction table (whose length becomes the summary scalar
    # retractions/count), and the write-up. They have already disagreed once,
    # which is why the scalar exists at all; this makes the disagreement fail a
    # test instead of shipping. Counted from source text because rtab is built
    # inside publish(), which needs a live wandb run.
    src = open(CAMPAIGN, encoding="utf-8").read()
    n_rtab = src.count("rtab.add_data(")
    doc = os.path.join(HERE, "maple-fern-r109f-instrument-collapse.md")
    n_doc = 0
    if os.path.exists(doc):
        dtext = open(doc, encoding="utf-8").read()
        # Retraction banners are numbered "RETRACTION n" / "CORRECTION n" in the
        # section they retract; the roll-up in the closing section is the count
        # this must agree with.
        n_doc = max(
            [
                int(m)
                for m in re.findall(
                    r"(?:RETRACTION|CORRECTION)\s+(\d+)", dtext
                )
            ]
            or [0]
        )
    print("retraction count: rtab rows=%d  doc highest banner=%d" % (n_rtab, n_doc))
    if n_doc and n_rtab != n_doc:
        print(
            "  BAD retraction table has %d rows but the document numbers up to %d"
            % (n_rtab, n_doc)
        )
        failures += 1
    if "the nine self-retractions" not in src:
        print("  BAD campaign docstring does not say 'nine self-retractions'")
        failures += 1

    print("FAILURES: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
