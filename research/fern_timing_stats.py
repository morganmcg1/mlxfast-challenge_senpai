#!/usr/bin/env python3
"""Paired-timing statistics for the R85-B split arm (research-only).

Reads the *.row.json emitted by research/paired-timing-r85b-split.sh and reports
the paired decode/prefill difference, the arm-order effect, and the
order-balanced estimate that cancels linear session drift.
"""
import glob
import json
import math
import statistics as st
import sys

T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
       8: 2.365, 9: 2.306, 10: 2.262, 11: 2.228, 12: 2.201}
T95_1S = {2: 4.303, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895,
          8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782}


def load(pattern):
    pairs = {}
    for path in glob.glob(pattern):
        row = json.load(open(path))
        pairs.setdefault((row["session"], row["round"]), {})[row["arm"]] = row
    out = []
    for key, arms in sorted(pairs.items()):
        if len(arms) != 2:
            continue
        out.append({
            "first": arms["baseline"].get("first", "baseline"),
            "dd": (arms["candidate"]["decode"] - arms["baseline"]["decode"]) * 1e6,
            "dp": (arms["candidate"]["prefill"] - arms["baseline"]["prefill"]) * 1e6,
            "bd": arms["baseline"]["decode"] * 1e6,
        })
    return out


def summarize(xs):
    n = len(xs)
    m = st.mean(xs)
    if n < 2:
        return m, float("nan"), float("nan"), float("nan")
    s = st.stdev(xs)
    sem = s / math.sqrt(n)
    return m, s, sem, T95.get(n - 1, 1.96) * sem


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "../mlxfast-r85b-split-timing/*.row.json"
    pairs = load(pattern)
    if not pairs:
        sys.exit(f"no complete pairs matched {pattern}")

    dd = [p["dd"] for p in pairs]
    dp = [p["dp"] for p in pairs]
    base = st.mean([p["bd"] for p in pairs])

    m, s, sem, half = summarize(dd)
    print(f"n = {len(pairs)} pairs   baseline decode {base:.1f} us/step")
    print(f"decode  diff mean {m:+.2f}  sd {s:.2f}  sem {sem:.2f}  "
          f"95% CI [{m - half:+.2f}, {m + half:+.2f}] us/step  ({m / base * 100:+.4f} %)")
    mp, sp, semp, halfp = summarize(dp)
    print(f"prefill diff mean {mp:+.3f}  sd {sp:.3f}  "
          f"95% CI [{mp - halfp:+.3f}, {mp + halfp:+.3f}] us/token")

    bf = [p["dd"] for p in pairs if p["first"] == "baseline"]
    cf = [p["dd"] for p in pairs if p["first"] == "candidate"]
    print()
    print(f"baseline-first  n={len(bf)}  mean {st.mean(bf):+.2f}  sd {st.stdev(bf):.2f}")
    print(f"candidate-first n={len(cf)}  mean {st.mean(cf):+.2f}  sd {st.stdev(cf):.2f}")
    print(f"arm-order effect (BF - CF) {st.mean(bf) - st.mean(cf):+.2f} us/step "
          "<- position-in-session drift, not code")

    bal = (st.mean(bf) + st.mean(cf)) / 2
    se_bal = math.sqrt(0.25 * (st.variance(bf) / len(bf) + st.variance(cf) / len(cf)))
    print(f"order-balanced mean {bal:+.2f}  se {se_bal:.2f}  "
          f"~95% CI [{bal - 1.96 * se_bal:+.2f}, {bal + 1.96 * se_bal:+.2f}] us/step "
          f"({bal / base * 100:+.4f} %)")

    ub_pooled = m + T95_1S.get(len(dd) - 1, 1.645) * sem
    ub_bal = bal + 1.645 * se_bal
    print()
    print(f"one-sided 95% upper bound on a real decode regression:")
    print(f"  pooled         {ub_pooled:+.1f} us/step  ({ub_pooled / base * 100:.3f} %)")
    print(f"  order-balanced {ub_bal:+.1f} us/step  ({ub_bal / base * 100:.3f} %)")

    need = (1.96 * s / 5.0) ** 2
    print(f"\npairs needed to resolve the 5 us/step threshold at sd={s:.0f}: {need:.0f} "
          f"(~{need * 2 * 170 / 3600:.1f} h of arms) -- wall clock cannot answer this")


if __name__ == "__main__":
    main()
