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
    eta = (absx @ np.abs(what).T).astype(np.float64) * 2.0 ** -18

    err = np.minimum(e1, e2) + eta
    rho = bf16_ulp(np.abs(lhat) + err) * 0.5
    eps = err + rho

    b = bias.astype(np.float64)[None, :]
    lo = sigmoid(lhat - eps) + b
    hi = sigmoid(lhat + eps) + b
    tau = np.partition(lo, -8, axis=1)[:, -8]
    ncand = (hi >= tau[:, None]).sum(axis=1)
    return ncand, err, rho, eps


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
    configs = [(s, b, g) for s in ("pot", "affine")
               for b in (8, 6, 5, 4, 3) for g in groups]

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

    for tag, L in layers.items():
        x = L["x"]
        L["absx"] = np.abs(x)
        L["xnorm"] = np.sqrt((x.astype(np.float64) ** 2).sum(axis=1))
        L["absx_g"] = {g: L["absx"].reshape(-1, HID // g, g).sum(axis=2)
                       for g in groups}

    rows = []
    for scheme, bits, group in configs:
        ncands, errs, rhos, epss = [], [], [], []
        nets = []
        for tag, L in layers.items():
            what, halfcell, scale_bytes, escaped = quantize(
                L["weight"], scheme, bits, group)
            nc, err, rho, eps = evaluate(
                L["x"], L["absx"], L["xnorm"], L["absx_g"],
                L["weight"], what, halfcell, L["bias"], group)
            ncands.append(nc)
            errs.append(err.ravel()[::97])
            rhos.append(rho.ravel()[::97])
            epss.append(eps.ravel()[::97])
            n_esc = int(escaped.sum())
            plane = (EXPERTS - n_esc) * (HID * bits // 8 + scale_bytes) \
                + n_esc * HID * 2
            nets.append(plane + 2 * EXPERTS + 4 * HID * nc.astype(np.float64))
        nc = np.concatenate(ncands)
        net = np.concatenate(nets)
        a = nc - 8
        err = np.concatenate(errs)
        rho = np.concatenate(rhos)
        rows.append(dict(
            scheme=scheme, bits=bits, group=group,
            net_mean=float(net.mean()),
            net_frac=float(net.mean() / BASELINE_BYTES),
            saving_mb_step=float((BASELINE_BYTES - net.mean()) * 39 / 1e6),
            a_mean=float(a.mean()), a_p99=float(np.percentile(a, 99)),
            a_max=float(a.max()),
            rho_share=float((rho / (err + rho)).mean()),
        ))
        r = rows[-1]
        print(f"{scheme:6s} b={bits} G={group:4d} "
              f"net={r['net_frac']*100:6.1f}%  save={r['saving_mb_step']:6.2f} MB/step "
              f"A: mean={r['a_mean']:7.2f} p99={r['a_p99']:6.1f} max={r['a_max']:6.0f} "
              f"rho_share={r['rho_share']:.3f}")

    # ------------------------------------------------------- pre-registered bar
    bar_net = 629146.0
    ok = [r for r in rows
          if r["net_mean"] <= bar_net and r["a_p99"] <= 16 and r["a_max"] <= 64]
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
                       validation_exact_frac=frac, rows=rows), fh, indent=2)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
