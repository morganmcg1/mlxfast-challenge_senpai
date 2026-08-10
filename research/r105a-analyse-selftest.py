#!/usr/bin/env python3
"""Offline checks on the preregistered decision rule in r105a-receipts.analyse.

Exercises the arithmetic and every verdict branch with synthetic prefill walls
so a real receipt landing mid-ladder cannot be the first time a branch runs.
Uses the two real A0 receipts as the control pair.
"""
from __future__ import annotations

import importlib.util

spec = importlib.util.spec_from_file_location("r105a_receipts", "research/r105a-receipts.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

# Real A0-1 / A0-2 candidate channels (research log section 4.4).
A0 = [
    ("A0-1", 0.00491191178125, 0.000187560791015625),
    ("A0-2", 0.00491467740625, 0.000188084228515625),
]


# Reference operating point for the synthetic score model: a millisecond off the
# shared 512-token prefill is worth PRICE0 percent of score on both axes, so the
# score channel and the prefill channel agree by construction and every branch
# assertion below reads the same on either. Disagreement is then injected
# explicitly rather than arriving by accident from a nonlinearity.
PREFILL0 = sum(512_000.0 * p for _, _, p in A0) / len(A0)
DECODE0 = sum(128_000.0 * d for _, d, _ in A0) / len(A0)
PRICE0 = 100.0 * (0.75 / DECODE0 + 0.25 / PREFILL0)
SCORE0 = 2.5707


def rec(arm: str, dec: float, pre: float, score: float | None = None) -> dict:
    prefill_ms = 512_000.0 * pre
    decode_ms = 128_000.0 * dec
    if score is None:
        score = SCORE0 * (1.0 + (PRICE0 / 100.0) * (PREFILL0 - prefill_ms))
    return {
        "arm": arm,
        "cand_dec": dec,
        "cand_pre": pre,
        "prefill_ms": prefill_ms,
        "step_ms": 1000.0 * dec - prefill_ms / 128.0,
        "official_score": score,
        "decode_speedup": 3.0 / decode_ms * DECODE0,
        "prefill_speedup": 2.0 / prefill_ms * PREFILL0,
        "prefill_price_pct_per_ms": 100.0 * (0.75 / decode_ms + 0.25 / prefill_ms),
    }


def arm_from_prefill(arm: str, prefill_ms: float, dec: float = 0.00491191178125) -> dict:
    return rec(arm, dec, prefill_ms / 512_000.0)


def controls() -> list[dict]:
    return [rec(a, d, p) for a, d, p in A0]


def show(label: str, res: dict, key: str) -> dict:
    a = res[key]
    print(
        f"{label:<34} n={a['n']} nu={a['dof']} t={a['t95']:.3f} "
        f"SE={a['se_ms']:.4f} delta={a['delta_prefill_ms']:+.4f} "
        f"CI90=[{a['ci90_ms'][0]:+.3f},{a['ci90_ms'][1]:+.3f}] "
        f"score={a['delta_score']:+.5f}/{a['bar_score']:.5f} -> {a['verdict']}"
    )
    return a


def main() -> int:
    base = controls()
    sigma_ref = R._sd([r["prefill_ms"] for r in base])
    mean_ref = sum(r["prefill_ms"] for r in base) / 2
    print(f"control mean prefill = {mean_ref:.5f} ms   sigma_p = {sigma_ref:.5f} ms")

    # SE must be built from the prefill channel only, never the decode channel.
    res = R.analyse(base + [arm_from_prefill("A2-1", mean_ref)])
    assert abs(res["sigma_ms"] - sigma_ref) < 1e-12, res["sigma_ms"]
    assert res["sigma_decode_channel_ms"] != res["sigma_ms"]

    # Section 4.4.2's SE column is a PROSPECTIVE planning table computed at a
    # pinned sigma of 0.190 ms. It is not what the code returns once a third A0
    # receipt lands, because sigma is then re-estimated from all controls in
    # hand. Check the two properties separately so neither is mistaken for the
    # other.
    prereg = {(2, 1): 0.2321, (3, 1): 0.2188, (3, 2): 0.1730}
    for (n0, n), want in prereg.items():
        pinned = sigma_ref * (1.0 / n + 1.0 / n0) ** 0.5
        assert abs(pinned - want) < 5e-4, (n0, n, pinned, want)
        print(f"prereg SE(n0={n0},n={n}) = {pinned:.4f} ms at pinned sigma {sigma_ref:.5f}")

    # The code must apply that same formula to its own re-estimated sigma. Use
    # spread-out synthetic controls so the re-estimate is visibly different.
    for n0, n in prereg:
        ctl = base + [arm_from_prefill(f"A0-{i + 3}", mean_ref + 0.4 * (i + 1)) for i in range(n0 - 2)]
        arm = [arm_from_prefill(f"A2-{i + 1}", mean_ref - 0.1 * i) for i in range(n)]
        res = R.analyse(ctl + arm)
        want = res["sigma_ms"] * (1.0 / n + 1.0 / n0) ** 0.5
        got = res["A2"]["se_ms"]
        assert abs(got - want) < 1e-12, (n0, n, got, want)
        assert res["control_n"] == n0 and res["A2"]["dof"] == (n0 - 1) + (n - 1)
        print(
            f"realized SE(n0={n0},n={n}) = {got:.4f} ms at re-estimated "
            f"sigma {res['sigma_ms']:.5f} (nu={res['A2']['dof']})"
        )

    # Verdict branches. Every target delta is derived from the SE and t that the
    # code itself reports for that design, because a hand-picked delta silently
    # lands in the wrong branch as soon as the re-estimated sigma moves.
    ctl3 = base + [arm_from_prefill("A0-3", mean_ref)]
    for n in (1, 2):
        probe = R.analyse(ctl3 + [arm_from_prefill(f"A2-{i + 1}", mean_ref) for i in range(n)])["A2"]
        se, t = probe["se_ms"], probe["t95"]
        win_at = R.BAR_MS + t * se
        print(f"\n-- verdict branches, n0=3 n={n}: SE={se:.4f} t={t:.3f} "
              f"WIN needs delta>{win_at:.3f} ms --")
        cases = [
            ("clears bar", win_at + 0.2, "WIN" if n >= 2 else "WIN-pending-replicate"),
            ("flat", 0.0, "NULL-bar-excluded"),
            ("big regression", -(t * se + 0.5), "REGRESSION"),
            ("at the bar", R.BAR_MS, "PROMISING-needs-replicate"),
        ]
        for label, delta, want in cases:
            # A branch is only reachable if the rule's own inequalities admit it.
            lo, hi = delta - t * se, delta + t * se
            reachable = {
                "WIN": lo > R.BAR_MS,
                "WIN-pending-replicate": lo > R.BAR_MS,
                "REGRESSION": hi < 0.0,
                "NULL-bar-excluded": lo <= R.BAR_MS and hi < R.BAR_MS and hi >= 0.0,
                "PROMISING-needs-replicate": hi >= R.BAR_MS and lo <= R.BAR_MS and delta > 2.0 * se,
            }[want]
            if not reachable:
                print(f"{label:<34} unreachable at this sigma; skipped")
                continue
            arm = [arm_from_prefill(f"A2-{i + 1}", mean_ref - delta) for i in range(n)]
            got = show(label, R.analyse(ctl3 + arm), "A2")["verdict"]
            assert got == want, (n, label, got, want)

    # The score channel is primary (section 4.4.7). A prefill wall that clears the
    # bar cannot ship on its own when the score did not move, and a score win the
    # prefill wall contradicts is downgraded rather than shipped.
    for n in (1, 2):
        flat_score = [
            rec(f"A2-{i + 1}", 0.00491191178125, (mean_ref - 20.0) / 512_000.0, score=SCORE0)
            for i in range(n)
        ]
        a = R.analyse(ctl3 + flat_score)["A2"]
        assert a["delta_prefill_ms"] > R.BAR_MS and a["ci90_ms"][0] > R.BAR_MS, a
        assert a["verdict"] == "NULL-bar-excluded", a["verdict"]
        assert not a["verdict_is_shippable"]
        print(f"prefill-only win n={n}: prefill delta {a['delta_prefill_ms']:+.2f} ms "
              f"but score delta {a['delta_score']:+.5f} -> {a['verdict']}")

        won_score = SCORE0 * (1.0 + (PRICE0 / 100.0) * 20.0)
        disagree = [
            rec(f"A2-{i + 1}", 0.00491191178125, (mean_ref + 5.0) / 512_000.0, score=won_score)
            for i in range(n)
        ]
        a = R.analyse(ctl3 + disagree)["A2"]
        assert a["ci90_score"][0] > a["bar_score"] and a["delta_prefill_ms"] < 0.0, a
        assert a["verdict"] == "PROMISING-channel-disagreement", a["verdict"]
        assert not a["channels_agree"] and not a["verdict_is_shippable"]
        print(f"score win, prefill regression n={n}: score delta {a['delta_score']:+.5f} "
              f"prefill delta {a['delta_prefill_ms']:+.2f} ms -> {a['verdict']}")

    # The two bars must describe the same physical effect: BAR_MS off the prefill
    # wall is exactly the score-channel bar under the linear price model.
    probe = R.analyse(ctl3 + [arm_from_prefill("A2-1", mean_ref - R.BAR_MS)])
    at_bar = probe["A2"]
    assert abs(at_bar["delta_score"] / at_bar["bar_score"] - 1.0) < 2e-3, at_bar
    print(f"\nbar equivalence: {R.BAR_MS} ms == score {probe['bar_score']:.6f} "
          f"({probe['prefill_price_pct_per_ms']:.4f} %/ms), arm at bar scores "
          f"{at_bar['delta_score']:+.6f}")

    # Only a WIN is shippable, and a WIN requires n>=2 however large the effect.
    for n in (1, 2):
        arm = [arm_from_prefill(f"A2-{i + 1}", mean_ref - 50.0) for i in range(n)]
        a = R.analyse(ctl3 + arm)["A2"]
        assert a["verdict_is_shippable"] == (n >= 2), (n, a["verdict"])
        print(f"shippable guard n={n}: {a['verdict']} shippable={a['verdict_is_shippable']}")

    # Fewer than two controls must refuse to produce a contrast at all.
    guard = R.analyse([base[0], arm_from_prefill("A2-1", mean_ref)])
    assert "A2" not in guard and "status" in guard, guard
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
