#!/usr/bin/env python3
"""Test whether decode_seconds_per_token amortises the 512-token seed prefill.

The r105-A design bar assumes ``dec = T + 4*pre``: the seed prefill wall
(512*pre seconds) is charged across the 128 timed steps, so one millisecond of
prefill is worth ``1/128`` millisecond of decode. That assumption sets the score
price of a prefill saving (f = 0.38 %/ms instead of 0.20 %/ms) and decides
whether the decode channel is a second, quieter measurement of the same effect.

The pinned baseline is the same code in every receipt, so regressing its decode
metric on its prefill metric isolates the echo: the slope is 4 if the seed
prefill is amortised in, and 0 if the decode metric is prefill-free.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("receipts", ROOT / "research" / "r105a-receipts.py")
_receipts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_receipts)


def main() -> None:
    pre, dec = [], []
    for row in _receipts.fetch_rows().values():
        metrics = row.get("officialMetrics")
        if not isinstance(metrics, dict) or not metrics.get("passed_correctness"):
            continue
        try:
            p = float(metrics["baseline_prefill_seconds_per_token"])
            d = float(metrics["baseline_decode_seconds_per_token"])
        except (KeyError, TypeError, ValueError):
            continue
        if p <= 0 or d <= 0:
            continue
        pre.append(p)
        dec.append(d)

    n = len(pre)
    mp, md = sum(pre) / n, sum(dec) / n
    vp = sum((x - mp) ** 2 for x in pre) / (n - 1)
    vd = sum((y - md) ** 2 for y in dec) / (n - 1)
    cov = sum((x - mp) * (y - md) for x, y in zip(pre, dec)) / (n - 1)
    sp, sd = math.sqrt(vp), math.sqrt(vd)
    slope = cov / vp
    corr = cov / (sp * sd)
    residuals = [y - (md + slope * (x - mp)) for x, y in zip(pre, dec)]
    mr = sum(residuals) / n
    sr = math.sqrt(sum((r - mr) ** 2 for r in residuals) / (n - 2))
    se_slope = sr / math.sqrt((n - 1) * vp)

    print(f"n={n}")
    print(f"baseline prefill: mean={mp:.9f} s/token  wall={512_000 * mp:.3f} ms  sd={512_000 * sp:.3f} ms ({100 * sp / mp:.3f} %)")
    print(f"baseline decode:  mean={md:.9f} s/token  {1000 * md:.4f} ms  sd={1000 * sd:.5f} ms ({100 * sd / md:.3f} %)")
    print(f"corr(base_dec, base_pre)={corr:.4f}")
    print(f"OLS slope d(dec)/d(pre)={slope:.3f} +/- {se_slope:.3f}   [4.0 = seed prefill amortised, 0.0 = prefill-free]")
    print(f"z vs 4: {(slope - 4.0) / se_slope:+.2f}   z vs 0: {slope / se_slope:+.2f}")
    print(f"prefill echo explains sd {1000 * 4.0 * sp:.5f} ms of the {1000 * sd:.5f} ms decode sd")
    print(f"decode sd after removing the echo: {1000 * sr:.5f} ms  ({100 * sr / md:.4f} % of dec)")
    pure_step = 1000 * md - 512_000 * mp / 128.0
    print(f"implied pure step: {pure_step:.4f} ms; residual sd is {100 * 1000 * sr / pure_step:.4f} % of it")

    # A heavy right tail (a receipt whose cool gate or machine misbehaved) would
    # inflate the SD without limiting a robust estimator, so the ladder could
    # recover power by pre-registering a median. A Gaussian core shows
    # 1.4826*MAD ~= SD and quantile spreads matching 1.349 and 2.563 sigma.
    for label, values, mean in (("base_pre(ms wall)", [512_000 * v for v in pre], 512_000 * mp),
                                ("base_dec(ms)", [1000 * v for v in dec], 1000 * md)):
        ordered = sorted(values)
        n_v = len(ordered)

        def q(p: float) -> float:
            return ordered[min(n_v - 1, max(0, int(round(p * (n_v - 1)))))]

        median = q(0.5)
        mad = sorted(abs(v - median) for v in values)[n_v // 2]
        sd_v = math.sqrt(sum((v - mean) ** 2 for v in values) / (n_v - 1))
        print(
            f"{label}: median={median:.4f} sd={sd_v:.5f} robust_sd(1.4826*MAD)={1.4826 * mad:.5f} "
            f"iqr/1.349={(q(0.75) - q(0.25)) / 1.349:.5f} p1={q(0.01):.4f} p99={q(0.99):.4f} max={ordered[-1]:.4f}"
        )


if __name__ == "__main__":
    main()
