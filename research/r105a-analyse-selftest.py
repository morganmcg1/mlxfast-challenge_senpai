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


def rec(arm: str, dec: float, pre: float) -> dict:
    prefill_ms = 512_000.0 * pre
    return {
        "arm": arm,
        "cand_dec": dec,
        "cand_pre": pre,
        "prefill_ms": prefill_ms,
        "step_ms": 1000.0 * dec - prefill_ms / 128.0,
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
        f"CI90=[{a['ci90_ms'][0]:+.3f},{a['ci90_ms'][1]:+.3f}] -> {a['verdict']}"
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
