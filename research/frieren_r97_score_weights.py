#!/usr/bin/env python3
"""Effective score exponents once the seed prefill is charged to decode.

The harness starts the decode timer BEFORE the 512-token seed forward, so with
S = wall time of a 512-token forward and T_bar = mean single-token step time:

    P = S / 512                       (prefill_seconds_per_token)
    D = (S + T_total) / 128 = 4P + T_bar   (decode_seconds_per_token)

score = (D_base/D)^0.75 * (P_base/P)^0.25, so with f = 4P/D:

    d log(score) / d log(multi-token forward cost) = -(0.25 + 0.75 f)
    d log(score) / d log(single-token step cost)   = -(0.75 (1 - f))

f is read straight off any score JSON as 4 * prefill_seconds_per_token
divided by decode_seconds_per_token; no extra measurement is needed.

    python3 research/frieren_r97_score_weights.py [score.json ...]
"""
import json
import math
import sys

PINNED_BASELINE = ("M5 pinned baseline (score.json constants)",
                   0.00036751938916015626, 0.01385621216015625)


def report(name, p, d):
    f = 4 * p / d
    e_prefill, e_step = 0.25 + 0.75 * f, 0.75 * (1 - f)
    print(f"{name}")
    print(f"  P = {p*1e3:8.4f} ms/token   D = {d*1e3:8.4f} ms/step")
    print(f"  seed term 4P = {4*p*1e3:7.4f} ms/step   T_bar = {(d-4*p)*1e3:8.4f} ms/step")
    print(f"  f = 4P/D = {f:.5f}   ({f:.1%} of the decode metric is the seed prefill)")
    print(f"  effective exponent, 512-token forward cost : {e_prefill:.4f} "
          f"(nominal 0.25, {e_prefill/0.25-1:+.1%})")
    print(f"  effective exponent, single-token step cost : {e_step:.4f} "
          f"(nominal 0.75, {e_step/0.75-1:+.1%})")
    print(f"  exchange rate: one unit of step cost is worth "
          f"{e_step/e_prefill:.2f} units of prefill cost")
    return f


def worked_example(f, forward_factor=1.10, step_factor=0.95):
    lm, ls = math.log(forward_factor), math.log(step_factor)
    correct = -(0.25 + 0.75 * f) * lm - 0.75 * (1 - f) * ls
    naive = -0.25 * lm - 0.75 * ls
    print(f"\n  worked example: 512-token forward x{forward_factor}, "
          f"single-token step x{step_factor}")
    print(f"    correct : d log score = {correct:+.5f} -> {math.exp(correct)-1:+.2%} score")
    print(f"    naive   : d log score = {naive:+.5f} -> {math.exp(naive)-1:+.2%} score")
    if correct:
        print(f"    the naive 0.25/0.75 split misstates the change by {naive/correct:.1f}x")


def main():
    f = report(*PINNED_BASELINE)
    worked_example(f)
    for path in sys.argv[1:]:
        with open(path) as fh:
            m = json.load(fh)["metrics"]
        print()
        report(path, m["prefill_seconds_per_token"], m["decode_seconds_per_token"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
