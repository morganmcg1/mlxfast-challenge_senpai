#!/usr/bin/env python3
"""r2 predictor: turn command-buffer count deltas into a predicted ns delta.

Uses the per-boundary M5 costs measured by the PR #44 r1 ranked receipt
(200 MB -> 50 MB, submission 3e6fdcba) and the score conversion fixed by
tanjiro's PR #34 M5 dispatch law.

  python3 research/nezuko_mbcap_predict.py --dec-cb 19 --pre-cb 41
  python3 research/nezuko_mbcap_predict.py --receipt 195.502521 5.1195537
"""
import argparse
import math

# Control c3ce66e, the fixed comparison point for every r2 verdict.
CTRL_PRE_US = 191.308        # candidate prefill seconds/token, in us
CTRL_DEC_MS = 5.04644        # candidate decode seconds/token, in ms
NORM_DEC = 0.013890          # ns normalisers (programme constants)
NORM_PRE = 0.0003845

# r1 measured M5 per-added-command-buffer costs.
DEC_US_PER_CB = 56.33 / 51.0     # +1.1045 us per added decode cb
PRE_US_PER_CB = 2147.0 / 79.0    # +27.18 us per added prefill cb

# r1 measured M4 == M5 boundary counts at the shipped cap.
BASE_DEC_CB = 34
BASE_PRE_CB = 81


def ns(pre_us: float, dec_ms: float) -> float:
    nd = NORM_DEC / (dec_ms * 1e-3)
    npf = NORM_PRE / (pre_us * 1e-6)
    return nd ** 0.75 * npf ** 0.25


def decompose(pre_us: float, dec_ms: float):
    s_ms = 512.0 * pre_us * 1e-3
    t_ms = dec_ms - s_ms / 128.0
    return s_ms, t_ms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dec-cb", type=float, help="candidate decode cbs/step")
    ap.add_argument("--pre-cb", type=float, help="candidate prefill cbs")
    ap.add_argument("--receipt", nargs=2, type=float,
                    metavar=("PRE_US", "DEC_MS"),
                    help="score an actual receipt instead of predicting")
    args = ap.parse_args()

    ctrl_ns = ns(CTRL_PRE_US, CTRL_DEC_MS)
    ctrl_s, ctrl_t = decompose(CTRL_PRE_US, CTRL_DEC_MS)
    sigma = (ctrl_s / 128.0) / CTRL_DEC_MS
    d_lnscore_dt = -0.75 * (1.0 - sigma) / ctrl_t          # per ms of T
    d_lnscore_ds = -(0.25 + 0.75 * sigma) / ctrl_s          # per ms of S
    print(f"control  ns={ctrl_ns:.6f}  S={ctrl_s:.4f} ms  T={ctrl_t:.6f} ms  "
          f"sigma={sigma:.5f}")
    print(f"conversion  dlnscore/dT = {d_lnscore_dt*100:+.5f} %/ms   "
          f"dlnscore/dS = {d_lnscore_ds*100:+.5f} %/ms")
    print(f"per removed decode cb  {-d_lnscore_dt*DEC_US_PER_CB*1e-3*100:+.6f} % "
          f"({DEC_US_PER_CB:.4f} us/cb)")
    print(f"per removed prefill cb {-d_lnscore_ds*PRE_US_PER_CB*1e-3*100:+.6f} % "
          f"({PRE_US_PER_CB:.3f} us/cb)")

    if args.receipt:
        pre_us, dec_ms = args.receipt
        cand_ns = ns(pre_us, dec_ms)
        s_ms, t_ms = decompose(pre_us, dec_ms)
        print()
        print(f"receipt  cand_pre={pre_us:.6f} us  cand_dec={dec_ms:.7f} ms")
        print(f"         ns={cand_ns:.6f}  d_ns={100*(cand_ns/ctrl_ns-1):+.4f}%")
        print(f"         S={s_ms:.4f} ms ({100*(s_ms/ctrl_s-1):+.3f}%)  "
              f"T={t_ms:.6f} ms ({100*(t_ms/ctrl_t-1):+.3f}%)")
        print(f"         dS={s_ms-ctrl_s:+.4f} ms -> "
              f"{100*d_lnscore_ds*(s_ms-ctrl_s):+.4f}% ; "
              f"dT={t_ms-ctrl_t:+.6f} ms -> "
              f"{100*d_lnscore_dt*(t_ms-ctrl_t):+.4f}%")
        print(f"         decode ratio {CTRL_DEC_MS/dec_ms:.4f}  "
              f"prefill ratio {CTRL_PRE_US/pre_us:.4f}  (band gate)")

    if args.dec_cb is not None and args.pre_cb is not None:
        d_dec = BASE_DEC_CB - args.dec_cb        # buffers removed
        d_pre = BASE_PRE_CB - args.pre_cb
        dt_ms = -d_dec * DEC_US_PER_CB * 1e-3
        ds_ms = -d_pre * PRE_US_PER_CB * 1e-3
        pct_t = 100.0 * d_lnscore_dt * dt_ms
        pct_s = 100.0 * d_lnscore_ds * ds_ms
        pred_pre = CTRL_PRE_US + ds_ms * 1e3 / 512.0
        pred_dec = CTRL_DEC_MS + dt_ms + ds_ms / 128.0
        print()
        print(f"prediction  decode cb {BASE_DEC_CB} -> {args.dec_cb:g} "
              f"({-d_dec:+g}), prefill cb {BASE_PRE_CB} -> {args.pre_cb:g} "
              f"({-d_pre:+g})")
        print(f"  dT = {dt_ms*1e3:+.2f} us -> {pct_t:+.4f}% of score")
        print(f"  dS = {ds_ms:+.4f} ms -> {pct_s:+.4f}% of score")
        print(f"  TOTAL predicted d_ns = {pct_t+pct_s:+.4f}%")
        print(f"  implies cand_pre {pred_pre:.4f} us, cand_dec {pred_dec:.6f} ms, "
              f"ns {ns(pred_pre, pred_dec):.6f}")
        print(f"  acceptance band: decode ratio "
              f"{CTRL_DEC_MS/pred_dec:.4f} in [0.980,1.053]; prefill ratio "
              f"{CTRL_PRE_US/pred_pre:.4f} in [0.952,1.053]")


if __name__ == "__main__":
    main()
