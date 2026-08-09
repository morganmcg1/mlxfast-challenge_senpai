#!/usr/bin/env python3
"""r96-b Stage 1: certified lossless low-precision screen for the decode router.

Research only. Consumes the dump produced by
`research/frieren-r96b-router-dump.patch` and applies the go/no-go bar fixed in
`research/frieren-r96b-preregistration.md` before any of this data existed.

  python3 research/frieren_r96b_screen.py --dir /tmp/r96b [--records 128]

Dump layout (all payloads FP32; BF16 -> FP32 is exact so the BF16 bit pattern
is the high half of each word):
  w_L<NN>.bin    256*2048 router weights, then 256 correction-bias values
  act_L<NN>.bin  repeated records of 2048 `normalized` then 256 router logits
"""
import argparse
import glob
import json
import os
import re

import numpy as np

HID = 2048
EXPERTS = 256
REC_FLOATS = HID + EXPERTS
BASELINE_BYTES = EXPERTS * HID * 2  # BF16 router plane per layer-step


# ---------------------------------------------------------------- bf16 helpers
def bf16_bits(x: np.ndarray) -> np.ndarray:
    """Round-to-nearest-even FP32 -> BF16, returned as the 16-bit pattern."""
    u = np.ascontiguousarray(x, dtype=np.float32).view(np.uint32)
    lsb = (u >> 16) & 1
    return ((u + 0x7FFF + lsb) >> 16).astype(np.uint16)


def bf16_value(x: np.ndarray) -> np.ndarray:
    return (bf16_bits(x).astype(np.uint32) << 16).view(np.float32)


def bf16_ulp(v: np.ndarray) -> np.ndarray:
    """ULP of the BF16 grid at magnitude `v` (7 stored mantissa bits)."""
    v = np.maximum(np.abs(v), np.float64(1e-30))
    return np.exp2(np.floor(np.log2(v)) - 7)


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


# ------------------------------------------------------------------- dump load
def load_layer(dump_dir: str, tag: str, records: int | None):
    w = np.fromfile(os.path.join(dump_dir, f"w_L{tag}.bin"), dtype=np.float32)
    assert w.size == EXPERTS * HID + EXPERTS, (tag, w.size)
    weight = w[: EXPERTS * HID].reshape(EXPERTS, HID)
    bias = w[EXPERTS * HID:]

    a = np.fromfile(os.path.join(dump_dir, f"act_L{tag}.bin"), dtype=np.float32)
    n = a.size // REC_FLOATS
    a = a[: n * REC_FLOATS].reshape(n, REC_FLOATS)
    if records is not None and n > records:
        a = a[np.linspace(0, n - 1, records).astype(int)]
    return weight, bias, a[:, :HID].copy(), a[:, HID:].copy(), n


# ---------------------------------------------------------------- quantization
def quantize(weight: np.ndarray, scheme: str, bits: int, group: int):
    """Return (what, halfcell, scale_bytes_per_row, escaped_row_mask)."""
    rows, cols = weight.shape
    ng = cols // group
    w = weight.reshape(rows, ng, group).astype(np.float32)

    if scheme == "pot":
        qmax = 2 ** (bits - 1) - 1
        m = np.abs(w).max(axis=2)
        e = np.ceil(np.log2(np.maximum(m, 1e-38) / qmax))
        sd = np.exp2(np.clip(e, -126, 127)).astype(np.float32)
        q = np.rint(w / sd[:, :, None])
        escaped = (np.abs(q).max(axis=(1, 2)) > qmax)
        what = (q * sd[:, :, None]).astype(np.float32)
        scale_bytes = ng * 1
    elif scheme == "affine":
        levels = 2 ** bits - 1
        mn = np.float32(np.float16(w.min(axis=2)))
        mx = w.max(axis=2)
        sc = np.float32(np.float16((mx - mn) / levels))
        sc_safe = np.where(sc == 0, np.float32(1.0), sc)
        q = np.clip(np.rint((w - mn[:, :, None]) / sc_safe[:, :, None]), 0, levels)
        what = (mn[:, :, None] + q * sc[:, :, None]).astype(np.float32)
        escaped = np.zeros(rows, dtype=bool)
        scale_bytes = ng * 4
    else:
        raise ValueError(scheme)

    halfcell = np.abs(w - what).max(axis=2).astype(np.float32)
    return what.reshape(rows, cols), halfcell, scale_bytes, escaped


# ------------------------------------------------------------------ evaluation
def evaluate(x, absx, xnorm, absx_g, weight, what, halfcell, bias, group):
    """Certified candidate-set size per record for one (layer, config)."""
    lhat = (x @ what.T).astype(np.float64)
    e1 = (absx_g[group] @ halfcell.T).astype(np.float64)
    dw = weight - what
    rnorm = np.sqrt((dw.astype(np.float64) ** 2).sum(axis=1))
    # per-row residual norm ships as BF16; round up so the bound stays valid
    rnorm = bf16_value(rnorm.astype(np.float32)).astype(np.float64)
    rnorm = np.where(rnorm < np.sqrt((dw.astype(np.float64) ** 2).sum(axis=1)),
                     rnorm * (1 + 2 ** -8), rnorm)
    e2 = xnorm[:, None] * rnorm[None, :]
    # covers the FP32 chunked accumulation of both the reference (exact w) and
    # the screen kernel (what); 2^-17 over-bounds 2 * 21 * 2^-24
    wmax = np.maximum(np.abs(weight), np.abs(what))
    eta = (absx @ wmax.T).astype(np.float64) * 2.0 ** -17

    err = np.minimum(e1, e2) + eta
    # BF16 rounding is monotone, so the reference logit lies in the rounded
    # interval; that is strictly tighter than the pre-registered +/- ulp/2 term.
    llo = bf16_value(np.nextafter((lhat - err).astype(np.float32), -np.inf))
    lhi = bf16_value(np.nextafter((lhat + err).astype(np.float32), np.inf))
    eps = (lhi.astype(np.float64) - llo.astype(np.float64)) * 0.5
    rho = np.maximum(eps - err, 0.0)

    b = bias.astype(np.float64)[None, :]
    lo = sigmoid(llo.astype(np.float64)) + b
    hi = sigmoid(lhi.astype(np.float64)) + b
    tau = np.partition(lo, -8, axis=1)[:, -8]
    ncand = (hi >= tau[:, None]).sum(axis=1)
    e1_wins = float((e1 < e2).mean())

    # diagnostic: exact top-8/9 gap in `c` units against the certified halfwidth
    lex = bf16_value((x @ weight.T).astype(np.float32)).astype(np.float64)
    cex = sigmoid(lex) + b
    s = np.sort(cex, axis=1)
    gap = s[:, -8] - s[:, -9]
    order = np.argsort(cex, axis=1)[:, -8:]
    half = np.take_along_axis(hi - lo, order, axis=1).mean(axis=1)
    # how loose the certified bound is versus the error the screen actually makes
    real = np.abs(lhat - lex)
    loose = err / np.maximum(real, 1e-12)
    # what an oracle-tight bound would cost: realized halfwidth in `c` units
    dc = np.abs(sigmoid(lex + real) - sigmoid(lex - real))
    real_half = np.take_along_axis(dc, order, axis=1).mean(axis=1)
    return ncand, err, rho, gap, half, e1_wins, loose, real_half


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/r96b")
    ap.add_argument("--records", type=int, default=128,
                    help="records per layer used by the grid pass")
    ap.add_argument("--full-records", type=int, default=None,
                    help="records per layer used by the confirmation pass")
    ap.add_argument("--out", default="research/frieren-r96b-stage1-results.json")
    args = ap.parse_args()

    tags = sorted(re.search(r"w_L(\d+)\.bin", p).group(1)
                  for p in glob.glob(os.path.join(args.dir, "w_L*.bin")))
    if not tags:
        raise SystemExit(f"no dump in {args.dir}")
    print(f"layers: {len(tags)} -> {tags[0]}..{tags[-1]}")

    groups = [32, 64, 128, 2048]
    prereg_bits = (8, 6, 5, 4, 3)
    diag_bits = (14, 12, 10)  # post-hoc: where certification would become feasible
    configs = [(s, b, g) for s in ("pot", "affine")
               for b in prereg_bits + diag_bits for g in groups]

    # ---------------------------------------------------------- stage 1 checks
    layers = {}
    val_total = val_exact = 0
    val_maxulp = 0.0
    for tag in tags:
        weight, bias, x, logits, nrec = load_layer(args.dir, tag, args.records)
        ref = (x.astype(np.float64) @ weight.astype(np.float64).T)
        got = bf16_bits(logits)
        want = bf16_bits(ref.astype(np.float32))
        val_total += got.size
        val_exact += int((got == want).sum())
        d = np.abs(got.astype(np.int32) - want.astype(np.int32))
        val_maxulp = max(val_maxulp, float(d.max()))
        layers[tag] = dict(weight=weight, bias=bias, x=x, nrec=nrec)
    frac = val_exact / val_total
    print(f"pipeline validation: {val_exact}/{val_total} exact "
          f"({frac*100:.4f}%), max bit-pattern gap {val_maxulp:.0f} ulp")
    if frac < 0.999 or val_maxulp > 1:
        print("VOID: pipeline validation failed the pre-registered gate")
        return 1

    # config-independent property of the routing problem: the top-8/9 decision
    # margin any certified screen has to resolve
    margins = []
    for tag, L in layers.items():
        c = sigmoid(bf16_value((L["x"] @ L["weight"].T).astype(np.float32))
                    .astype(np.float64)) + L["bias"].astype(np.float64)
        s = np.sort(c, axis=1)
        margins.append(s[:, -8] - s[:, -9])
    margin = np.concatenate(margins)
    margin_stats = dict(p01=float(np.percentile(margin, 1)),
                        p10=float(np.percentile(margin, 10)),
                        median=float(np.median(margin)))
    print(f"top-8/9 margin: p01={margin_stats['p01']:.3e} "
          f"p10={margin_stats['p10']:.3e} median={margin_stats['median']:.3e}")

    for tag, L in layers.items():
        x = L["x"]
        L["absx"] = np.abs(x)
        L["xnorm"] = np.sqrt((x.astype(np.float64) ** 2).sum(axis=1))
        L["absx_g"] = {g: L["absx"].reshape(-1, HID // g, g).sum(axis=2)
                       for g in groups}

    rows = []
    for scheme, bits, group in configs:
        ncands, errs, rhos, nets, resids, gaps, halfs, e1w = [], [], [], [], [], [], [], []
        looses, rhalfs = [], []
        for tag, L in layers.items():
            what, halfcell, scale_bytes, escaped = quantize(
                L["weight"], scheme, bits, group)
            nc, err, rho, gap, half, ew, loose, rhalf = evaluate(
                L["x"], L["absx"], L["xnorm"], L["absx_g"],
                L["weight"], what, halfcell, L["bias"], group)
            ncands.append(nc)
            errs.append(err.ravel()[::97])
            rhos.append(rho.ravel()[::97])
            gaps.append(gap)
            halfs.append(half)
            e1w.append(ew)
            looses.append(loose.ravel()[::97])
            rhalfs.append(rhalf)
            n_esc = int(escaped.sum())
            plane = (EXPERTS - n_esc) * (HID * bits // 8 + scale_bytes) \
                + n_esc * HID * 2
            base = plane + 2 * EXPERTS
            nets.append(base + 4 * HID * nc.astype(np.float64))
            # optimistic sensitivity: a candidate refetches only the bits the
            # screen plane does not already carry (assumes an exact bit split)
            resids.append(base + max(16 - bits, 0) * HID // 8 * nc.astype(np.float64))
        nc = np.concatenate(ncands)
        net = np.concatenate(nets)
        netr = np.concatenate(resids)
        a = nc - 8
        err = np.concatenate(errs)
        rho = np.concatenate(rhos)
        gap = np.concatenate(gaps)
        half = np.concatenate(halfs)
        rows.append(dict(
            scheme=scheme, bits=bits, group=group,
            diagnostic=bits not in prereg_bits,
            net_mean=float(net.mean()),
            net_frac=float(net.mean() / BASELINE_BYTES),
            saving_mb_step=float((BASELINE_BYTES - net.mean()) * 39 / 1e6),
            net_resid_frac=float(netr.mean() / BASELINE_BYTES),
            saving_resid_mb_step=float((BASELINE_BYTES - netr.mean()) * 39 / 1e6),
            a_mean=float(a.mean()), a_p99=float(np.percentile(a, 99)),
            a_max=float(a.max()), a_frac_zero=float((a == 0).mean()),
            rho_share=float((rho / np.maximum(err + rho, 1e-30)).mean()),
            e1_wins_frac=float(np.mean(e1w)),
            half_over_gap_median=float(np.median(half / np.maximum(gap, 1e-12))),
            bound_looseness_median=float(np.median(np.concatenate(looses))),
            real_half_over_gap_median=float(np.median(
                np.concatenate(rhalfs) / np.maximum(gap, 1e-12))),
        ))
        r = rows[-1]
        print(f"{'DIAG ' if r['diagnostic'] else '     '}"
              f"{scheme:6s} b={bits:2d} G={group:4d} "
              f"net={r['net_frac']*100:6.1f}%  save={r['saving_mb_step']:7.2f} MB/step "
              f"A: mean={r['a_mean']:8.2f} p99={r['a_p99']:6.1f} max={r['a_max']:5.0f} "
              f"zero={r['a_frac_zero']*100:5.1f}% rho={r['rho_share']:.3f} "
              f"2eps/gap={r['half_over_gap_median']:.2e} "
              f"loose={r['bound_looseness_median']:6.1f} "
              f"real/gap={r['real_half_over_gap_median']:.2e}")

    # ------------------------------------------------------- pre-registered bar
    bar_net = 629146.0
    ok = [r for r in rows if not r["diagnostic"]
          and r["net_mean"] <= bar_net and r["a_p99"] <= 16 and r["a_max"] <= 64]
    ok.sort(key=lambda r: (-r["saving_mb_step"], r["bits"], -r["group"]))
    verdict = "GO" if ok else "NO-GO"
    print(f"\nVERDICT: {verdict}")
    if ok:
        w = ok[0]
        print(f"winner: {w['scheme']} b={w['bits']} G={w['group']} "
              f"save={w['saving_mb_step']:.2f} MB/step "
              f"score={w['saving_mb_step']*0.015224:.3f}%")
    else:
        best = min(rows, key=lambda r: r["net_mean"])
        print(f"closest by bytes: {best}")
        best_a = min(rows, key=lambda r: r["a_p99"])
        print(f"closest by ambiguity: {best_a}")

    with open(args.out, "w") as fh:
        json.dump(dict(verdict=verdict, bar_net_bytes=bar_net,
                       records_per_layer=args.records, layers=len(tags),
                       validation_exact_frac=frac, margin=margin_stats,
                       rows=rows), fh, indent=2)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
