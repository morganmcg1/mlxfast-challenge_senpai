#!/usr/bin/env python3
"""r101-A: rebuild the decode pool model on measured quantities only.

Consumes the byte model in `fern_r101_byte_audit.py` (single source of truth for
per-step bytes) plus this host's measured streaming ceiling, and emits:

  P0  the impossibility replication of the assignment's section 1
  P3  regime classification, the two-parameter M4->M5 map, and its residual
  P4  the re-ranked M5 pool table with headroom in us/step and % score
  P5  the families that clear the follow-on bar

Artifacts land under `research/artifacts/fern-r101/`.

Every timing input is a prior measurement with its source named inline; nothing
here is fitted to the validation target.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib

from fern_r101_byte_audit import (
    CENSUS_EPOCH,
    HEAD_EPOCH,
    HIDDEN,
    MOE_INTER,
    R94,
    SPARSE_LAYERS,
    TOPK,
    family_bytes,
    nvfp4_row_bytes,
)

# The M5 routed receipt differential ablates the routed experts only, so it
# carries the routed down projection but not T2d's shared-expert down or
# residual traffic.
ROUTED_DOWN = SPARSE_LAYERS * TOPK * HIDDEN * nvfp4_row_bytes(
    MOE_INTER, HEAD_EPOCH["routed_scale_group"]
)

# --- measured host ceilings ----------------------------------------------
# `research/artifacts/fern-r101/bw-ladder.tsv`, job 4f4ee576, M4 Pro Mac16,11,
# 20 GPU cores, applegpu_g16s. Autotuned geometry: 40 TGs (2/core), 256
# threads/TG, ilp=8, 163,840 B written per command buffer (rule 77).
MEAS_M4 = 266.80  # 64 KiB block-shuffled asymptote: the achievable read ceiling
SEQ_M4 = 262.98  # grid-stride sequential asymptote
THEOR_M4 = 273.0  # LPDDR5X-8533 273 GB/s spec sheet
# Session-normalised streaming-sweep rate from official M5 receipts
# (`RESEARCH_STATE_ARCHIVE_through-round-21.md:4564-4578`): raw 620.3.
M5_PUB = 610.6
# Same sweep corrected by this host's measured fixed-geometry under-read
# (266.80 / 237.4 = 1.1238): a sensitivity, not a measurement.
M5_GEOM = M5_PUB * MEAS_M4 / 237.4

# Measured cache curve, sequential grid-stride, MiB of unique footprint -> GB/s.
CACHE_CURVE = [
    (1, 2583.19),
    (2, 1674.21),
    (3, 1510.90),
    (4, 1445.48),
    (6, 873.82),
    (8, 590.29),
    (10, 538.17),
    (12, 510.10),
    (14, 441.34),
    (16, 313.17),
    (20, 268.38),
    (24, 265.05),
]

# --- prior timing measurements -------------------------------------------
# r94 per-kernel GPU-timer census (`maple-frieren-r94-decode-residue-ledger.md`).
SPLIT1_TOTAL = 8528.3  # all 24 rows, SPLIT=1 raw GPU timer
NAT_TOTAL = 7993.4  # all 24 rows, dispatch-deflated estimate
# Marginal-cost ledger (`maple-fern-decode-marginal-cost-ledger.md:434-436`):
# census denominator and duplicate-injection marginal, us/step.
INJECTION = {
    "T2c": (1569.8, 1183.81),
    "T2d": (898.8, 554.89),
    "T0b": (1722.3, 1276.01),
}
# Official M5 receipt differentials (`research/tanjiro-pr34-result.md:599,602`).
M5_RECEIPT = {"routed": 1010.67, "qkvo": 1230.70}
# Steady-state M5 decode: 4893.7 ranked wall - 752.2 amortised seed prefill
# (rule 58). This is the single hard M5 constraint.
M5_TARGET = 4141.5
SCORE_PER_US = 0.015228  # % score per us/step of decode

# Marginal-ledger E column (marginal / census), with T0a as the near-zero-byte
# floor and T1c_lmhead as the uncacheable control.
E_COLUMN = {
    "T0a": -0.045,
    "T1a residual rms router": 0.349,
    "T2a shared gate+up qmv": 0.311,
    "T2d routed+shared down+residual": 0.617,
    "T2c routed gate+up qmv": 0.754,
    "T0b": 0.741,
    "T1c lmhead int5 base coarse delta": 1.111,
}

BW_THRESHOLD_PCT = 70.0  # achieved >= 70 % of measured peak => bytes-bound


def b_eff(mib: float) -> float:
    """Measured achievable read rate for a unique footprint of `mib` MiB."""
    if mib <= CACHE_CURVE[0][0]:
        return CACHE_CURVE[0][1]
    if mib >= CACHE_CURVE[-1][0]:
        return SEQ_M4
    for (x0, y0), (x1, y1) in zip(CACHE_CURVE, CACHE_CURVE[1:]):
        if x0 <= mib <= x1:
            t = (math.log(mib) - math.log(x0)) / (math.log(x1) - math.log(x0))
            return y0 + t * (y1 - y0)
    return SEQ_M4


def spearman(xs, ys) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


def p0(head, census, out: pathlib.Path):
    """Replicate the assignment's section-1 impossibility table."""
    qkv = head["T0b(a) qkv h64"][0] + head["T0b(b) qkv h48"][0]
    oproj = head["T3b oproj h64"][0] + head["T3c oproj h48"][0]
    rows = [
        # label, source, advisor_MB, head_bytes, us, host peak
        ("M4 census T2c gate+up", "gpu-timer", 368.1, head["T2c routed gate+up qmv"][0],
         INJECTION["T2c"][0], MEAS_M4),
        ("M4 injection T2c gate+up", "duplicate-inject", 368.1,
         head["T2c routed gate+up qmv"][0], INJECTION["T2c"][1], MEAS_M4),
        ("M4 census T2d down+shared", "gpu-timer", 184.0,
         head["T2d routed+shared down+residual"][0], INJECTION["T2d"][0], MEAS_M4),
        ("M4 injection T2d", "duplicate-inject", 184.0,
         head["T2d routed+shared down+residual"][0], INJECTION["T2d"][1], MEAS_M4),
        ("M4 census T0b QKV", "gpu-timer", 411.3, qkv, INJECTION["T0b"][0], MEAS_M4),
        ("M4 injection T0b QKV", "duplicate-inject", 411.3, qkv, INJECTION["T0b"][1],
         MEAS_M4),
        ("M5 receipt R3-R2 routed", "receipt-diff", 552.1,
         head["T2c routed gate+up qmv"][0] + ROUTED_DOWN,
         M5_RECEIPT["routed"], M5_PUB),
        ("M5 receipt R2-R1 qkvo", "receipt-diff", 802.2, qkv + oproj,
         M5_RECEIPT["qkvo"], M5_PUB),
    ]
    lines = ["row\tsource\tadvisor_MB\thead_MB\tus\tadvisor_GBs\thead_GBs\t"
             "advisor_pct_peak\thead_pct_peak\tverdict"]
    n_impossible = 0
    print("\n## P0 impossibility replication (head bytes, measured peaks)")
    for label, src, amb, hb, us, peak in rows:
        hmb = hb / 1e6
        agbs = amb / (us * 1e-3)
        hgbs = hmb / (us * 1e-3)
        apct = agbs / peak * 100
        hpct = hgbs / peak * 100
        verdict = "IMPOSSIBLE" if hpct > 100 else "possible"
        n_impossible += hpct > 100
        lines.append(
            f"{label}\t{src}\t{amb:.1f}\t{hmb:.2f}\t{us:.2f}\t{agbs:.1f}\t{hgbs:.1f}\t"
            f"{apct:.1f}\t{hpct:.1f}\t{verdict}"
        )
        print(f"  {label:32s} {src:16s} {amb:7.1f} -> {hmb:7.2f} MB  "
              f"{hgbs:6.1f} GB/s  {apct:5.1f}% -> {hpct:5.1f}%  {verdict}")
    print(f"  => {n_impossible} of {len(rows)} rows exceed host peak "
          f"(registered prediction: at least 3)")
    (out / "p0-impossibility.tsv").write_text("\n".join(lines) + "\n")

    # P0-3: the same T2d row at the census layout epoch it was published in.
    c2d = census["T2d routed+shared down+residual"][0] / 1e6
    print(f"  P0-3 T2d at census epoch: {c2d:.2f} MB -> census "
          f"{c2d/(INJECTION['T2d'][0]*1e-3):.1f} GB/s, injection "
          f"{c2d/(INJECTION['T2d'][1]*1e-3):.1f} GB/s")
    return n_impossible


def p0_e_analysis(head, out: pathlib.Path):
    """P0-4/P0-5: is E monotone in per-call unique footprint, and why."""
    per_call = {
        "T0a": 0.001,
        "T1a residual rms router": head["T1a residual rms router"][0] / 39 / 1e6,
        "T2a shared gate+up qmv": head["T2a shared gate+up qmv"][0] / 39 / 1e6,
        "T2d routed+shared down+residual":
            head["T2d routed+shared down+residual"][0] / 39 / 1e6,
        "T2c routed gate+up qmv": head["T2c routed gate+up qmv"][0] / 39 / 1e6,
        "T0b": (head["T0b(a) qkv h64"][0] + head["T0b(b) qkv h48"][0]) / 40 / 1e6,
        "T1c lmhead int5 base coarse delta":
            head["T1c lmhead int5 base coarse delta"][0] / 1e6,
    }
    names = sorted(per_call, key=lambda k: per_call[k])
    xs = [per_call[n] for n in names]
    ys = [E_COLUMN[n] for n in names]
    rho = spearman(xs, ys)
    lines = ["family\tper_call_MB\tE\tE_floor\tin_band\timplied_C_MB"]
    print("\n## P0-4/5 E versus per-call unique footprint")
    for n, x, y in zip(names, xs, ys):
        floor = SEQ_M4 / b_eff(x / 1.048576)  # MB -> MiB
        implied_c = x * (1 - y)
        lines.append(f"{n}\t{x:.4f}\t{y:.3f}\t{floor:.3f}\t"
                     f"{'yes' if floor - 1e-9 <= y <= 1.0 + 1e-9 else 'no'}\t"
                     f"{implied_c:.3f}")
        print(f"  {n:34s} {x:8.3f} MB/call  E={y:+.3f}  E_floor={floor:.3f}  "
              f"C=F(1-E)={implied_c:6.3f} MB")
    print(f"  Spearman rho = {rho:.4f} (registered bar: >= 0.80)")
    (out / "p0-e-column.tsv").write_text("\n".join(lines) + "\n")
    return rho


def classify(head):
    """Split the census into a bytes-bound pool and a latency-bound pool."""
    bw, lat = [], []
    for name, (byts, calls) in head.items():
        s1, nat, _r94 = R94[name]
        pct = byts / (s1 * 1e-6) / 1e9 / MEAS_M4 * 100
        (bw if pct >= BW_THRESHOLD_PCT else lat).append((name, byts, calls, s1, nat, pct))
    return bw, lat


def p3(head, bw, lat, alpha, beta, label, nat=False):
    col, total = (4, NAT_TOTAL) if nat else (3, SPLIT1_TOTAL)
    bw_us = sum(r[col] for r in bw)
    lat_us = sum(r[col] for r in lat)
    tail = total - bw_us - lat_us
    pred = alpha * bw_us + beta * (lat_us + tail)
    resid = (pred - M5_TARGET) / M5_TARGET * 100
    print(f"\n## P3 map [{label}] alpha={alpha:.4f} beta={beta:.4f}")
    print(f"  bytes-bound pool {bw_us:.1f} us, latency pool {lat_us:.1f} us, "
          f"unaudited tail {tail:.1f} us (SPLIT=1 total {SPLIT1_TOTAL:.1f})")
    print(f"  predicted M5 {pred:.1f} us vs target {M5_TARGET:.1f} "
          f"=> residual {resid:+.2f} %")
    return dict(alpha=alpha, beta=beta, bw_us=bw_us, lat_us=lat_us, tail_us=tail,
                predicted_us=pred, residual_pct=resid)


def p3b(head, alpha):
    """Second, independent validation against the two M5 receipt differentials."""
    qkv = head["T0b(a) qkv h64"][0] + head["T0b(b) qkv h48"][0]
    oproj = head["T3b oproj h64"][0] + head["T3c oproj h48"][0]
    rdown = head["T2d routed+shared down+residual"][0]
    # T2d also carries the shared-expert down projection and the residual add,
    # which the routed receipt block does not; scale by the routed-down share.
    routed_down_share = ROUTED_DOWN / rdown
    m4_routed = R94["T2c routed gate+up qmv"][0] + R94[
        "T2d routed+shared down+residual"][0] * routed_down_share
    m4_qkvo = sum(R94[k][0] for k in ("T0b(a) qkv h64", "T0b(b) qkv h48",
                                      "T3b oproj h64", "T3c oproj h48"))
    out = {}
    print("\n## P3b receipt-differential validation")
    for name, m4_us, meas_us, byts in (
        ("routed", m4_routed, M5_RECEIPT["routed"],
         head["T2c routed gate+up qmv"][0] + ROUTED_DOWN),
        ("qkvo", m4_qkvo, M5_RECEIPT["qkvo"], qkv + oproj),
    ):
        pred = alpha * m4_us
        resid = (pred - meas_us) / meas_us * 100
        achieved = byts / (meas_us * 1e-6) / 1e9
        out[name] = dict(m4_us=m4_us, predicted_m5_us=pred, measured_m5_us=meas_us,
                         residual_pct=resid, achieved_gbs=achieved,
                         pct_m5_peak=achieved / M5_PUB * 100)
        print(f"  {name:6s} M4 {m4_us:7.1f} us -> predicted {pred:7.1f} us vs "
              f"measured {meas_us:7.2f} us  residual {resid:+6.2f} %  "
              f"(M5 achieved {achieved:.1f} GB/s = {achieved/M5_PUB*100:.1f} % of peak)")
    return out


def p4(head, bw, lat, alpha, beta, out: pathlib.Path):
    rows = []
    for pool, scale in ((bw, alpha), (lat, beta)):
        for name, byts, calls, s1, _nat, pct in pool:
            m5_us = scale * s1
            gbs = byts / (m5_us * 1e-6) / 1e9
            pct5 = gbs / M5_PUB * 100
            head_us = m5_us * (1 - min(pct5, 100.0) / 100)
            rows.append(dict(family=name, calls=calls, head_bytes=byts,
                             m4_us_split1=s1, regime="bytes" if scale == alpha
                             else "latency", m5_us=m5_us, m5_gbs=gbs,
                             pct_m5_peak=pct5, headroom_us=head_us,
                             headroom_score_pct=head_us * SCORE_PER_US))
    rows.sort(key=lambda r: -r["m5_us"])
    # Headroom against peak is an upper bound nobody has ever reached. The
    # defensible reference is the best rate any family on this host actually
    # achieves, which is the lmhead streaming read.
    best_pct = max(r["pct_m5_peak"] for r in rows)
    for r in rows:
        r["pct_of_best_achieved"] = r["pct_m5_peak"] / best_pct * 100
        r["headroom_vs_best_us"] = r["m5_us"] * (1 - min(r["pct_of_best_achieved"], 100)
                                                 / 100)
        r["headroom_vs_best_score_pct"] = r["headroom_vs_best_us"] * SCORE_PER_US
    print("\n## P4 re-ranked modelled M5 decode pool")
    print(f"  reference best achieved rate on this host: {best_pct:.1f} % of peak")
    print(f"  {'family':34s} {'regime':8s} {'M5 us':>8s} {'GB/s':>7s} {'%peak':>6s} "
          f"{'head us':>8s} {'%score':>7s} {'vs best':>8s} {'%score':>7s}")
    for r in rows:
        print(f"  {r['family']:34s} {r['regime']:8s} {r['m5_us']:8.1f} "
              f"{r['m5_gbs']:7.1f} {r['pct_m5_peak']:6.1f} {r['headroom_us']:8.1f} "
              f"{r['headroom_score_pct']:7.2f} {r['headroom_vs_best_us']:8.1f} "
              f"{r['headroom_vs_best_score_pct']:7.2f}")
    print(f"  modelled audited total {sum(r['m5_us'] for r in rows):.1f} us "
          f"(+ unaudited tail) vs steady-state target {M5_TARGET:.1f} us")
    with open(out / "m5-pool-table.csv", "w") as fh:
        cols = list(rows[0])
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join(str(r[c]) for c in cols) + "\n")
    return rows


def p5(rows, min_pp=10.0, min_us=30.0):
    picked = [r for r in rows
              if (100 - r["pct_m5_peak"]) >= min_pp and r["headroom_us"] >= min_us]
    strict = [r for r in rows
              if (100 - r["pct_of_best_achieved"]) >= min_pp
              and r["headroom_vs_best_us"] >= min_us]
    print(f"\n## P5 families clearing >={min_pp:.0f} pp headroom and "
          f">={min_us:.0f} us/step")
    print("  [a] bar as written, against peak")
    for r in picked:
        print(f"    {r['family']:34s} {r['pct_m5_peak']:5.1f} % of peak, "
              f"{r['headroom_us']:6.1f} us/step = {r['headroom_score_pct']:.2f} % score")
    print(f"  => {len(picked)} families clear the bar as written "
          f"(registered prediction: at most one)")
    print("  [b] bar restated against the best achieved rate on the same host")
    for r in strict:
        print(f"    {r['family']:34s} {r['pct_of_best_achieved']:5.1f} % of best, "
              f"{r['headroom_vs_best_us']:6.1f} us/step = "
              f"{r['headroom_vs_best_score_pct']:.2f} % score")
    print(f"  => {len(strict)} families clear the restated bar")
    return picked, strict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/artifacts/fern-r101")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    head = family_bytes(**HEAD_EPOCH)
    census = family_bytes(**CENSUS_EPOCH)

    n_impossible = p0(head, census, out)
    rho = p0_e_analysis(head, out)

    bw, lat = classify(head)
    alpha = MEAS_M4 / M5_PUB  # bandwidth ratio
    beta = 20 / 40  # core-count ratio: a latency-bound family halves on M5
    primary = p3(head, bw, lat, alpha, beta, "naive priors, SPLIT=1")
    sens = {
        "geometry_corrected_M5_ceiling": p3(head, bw, lat, MEAS_M4 / M5_GEOM, beta,
                                            "M5 ceiling 686.2"),
        "nat_deflated_census": p3(head, bw, lat, alpha, beta, "nat census", nat=True),
    }
    receipts = p3b(head, alpha)
    rows = p4(head, bw, lat, alpha, beta, out)
    picked, strict = p5(rows)

    model = dict(
        host="M4 Pro Mac16,11, 20 GPU cores, applegpu_g16s",
        measured_ceiling_gbs=MEAS_M4,
        sequential_ceiling_gbs=SEQ_M4,
        theoretical_peak_gbs=THEOR_M4,
        m5_ceiling_published_gbs=M5_PUB,
        m5_ceiling_geometry_corrected_gbs=M5_GEOM,
        bw_threshold_pct=BW_THRESHOLD_PCT,
        p0_rows_exceeding_peak=n_impossible,
        p0_spearman_rho=rho,
        map_primary=primary,
        map_sensitivity=sens,
        receipt_validation=receipts,
        p5_families_vs_peak=[r["family"] for r in picked],
        p5_families_vs_best_achieved=[r["family"] for r in strict],
        pool=rows,
    )
    (out / "pool-model.json").write_text(json.dumps(model, indent=2) + "\n")
    print(f"\n# wrote {out}/p0-impossibility.tsv, p0-e-column.tsv, "
          f"m5-pool-table.csv, pool-model.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
