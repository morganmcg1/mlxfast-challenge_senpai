#!/usr/bin/env python3
"""Exact byte/FLOP accounting for the PR #34 real-kernel injections, and
marginal-rate arithmetic over two receipts.

Research-only tool. `senpai/tools/` is outside `benchmark.json` editablePaths, so
this file is never uploaded with a submission.

Injection schedule mirrors `lagunaInjectShare` / `lagunaInject*BankLayer` in
Sources/MLXFastModel/LagunaRuntimeModel.swift exactly.
"""

from __future__ import annotations

import argparse
import json
import math

LAYERS = 40
HIDDEN = 2048
HEAD_DIM = 128
KV_HEADS = 8
FULL_HEADS = 48
SLIDING_HEADS = 64
EXPERTS = 256
TOPK = 8
MOE_INTER = 512
PREFILL_ROWS = 512
BANK_ROTATION = 20


def injecting_layers(total: int) -> list[int]:
    """Layers where lagunaInjectShare(total, layer) > 0."""
    return [
        i
        for i in range(LAYERS)
        if ((i + 1) * total) // LAYERS - (i * total) // LAYERS > 0
    ]


def attn_bank(layer: int) -> int:
    return (layer + BANK_ROTATION) % LAYERS


def routed_bank(layer: int) -> int:
    return 1 + ((layer + BANK_ROTATION - 1) % (LAYERS - 1))


def heads_of(layer: int) -> int:
    return FULL_HEADS if layer % 4 == 0 else SLIDING_HEADS


# --- per-copy weight bytes and FLOPs ---------------------------------------


def decode_attn_copy(heads: int) -> tuple[int, int]:
    rows = heads * HEAD_DIM + 2 * KV_HEADS * HEAD_DIM
    # NVFP4 group-16: uint32 codes (hidden/8 words) + uint8 E4M3 scales (hidden/16)
    qkv_bytes = rows * (HIDDEN // 8) * 4 + rows * (HIDDEN // 16)
    in_vec = heads * HEAD_DIM
    o_bytes = HIDDEN * (in_vec // 8) * 4 + HIDDEN * (in_vec // 16)
    flops = 2 * rows * HIDDEN + 2 * HIDDEN * in_vec
    return qkv_bytes + o_bytes, flops


def decode_routed_copy() -> tuple[int, int]:
    gate_up = TOPK * (2 * MOE_INTER) * (HIDDEN // 8) * 4 + TOPK * (
        2 * MOE_INTER * 4
    ) * (HIDDEN // 64)
    down = TOPK * HIDDEN * (MOE_INTER // 8) * 4 + TOPK * HIDDEN * (MOE_INTER // 16)
    flops = 2 * TOPK * (2 * MOE_INTER) * HIDDEN + 2 * TOPK * HIDDEN * MOE_INTER
    return gate_up + down, flops


def prefill_routed_copy() -> tuple[int, int]:
    # 512 rows x top-8 with the injected uniform pattern touches every expert,
    # so the whole layer bank is streamed once (gate/up fused bank + stock down).
    gate_up = EXPERTS * (2 * MOE_INTER) * (HIDDEN // 8) * 4 + EXPERTS * (
        2 * MOE_INTER
    ) * (HIDDEN // 16)
    down = EXPERTS * HIDDEN * (MOE_INTER // 8) * 4 + EXPERTS * HIDDEN * (
        MOE_INTER // 16
    )
    flops = PREFILL_ROWS * TOPK * (2 * (2 * MOE_INTER) * HIDDEN + 2 * HIDDEN * MOE_INTER)
    return gate_up + down, flops


def prefill_attn_copy(heads: int) -> tuple[int, int]:
    q = heads * HEAD_DIM * HIDDEN * 2
    kv = 2 * (KV_HEADS * HEAD_DIM * HIDDEN * 2)
    o = HIDDEN * heads * HEAD_DIM * 2
    flops = (
        2 * PREFILL_ROWS * HIDDEN * (heads * HEAD_DIM)  # q
        + 2 * 2 * PREFILL_ROWS * HIDDEN * (KV_HEADS * HEAD_DIM)  # k, v
        + 2 * PREFILL_ROWS * (heads * HEAD_DIM) * HIDDEN  # o
    )
    return q + kv + o, flops


# --- totals for one configuration ------------------------------------------


def totals(
    decode_attn: int = 0,
    decode_routed: int = 0,
    prefill_routed: int = 0,
    prefill_attn: int = 0,
) -> dict:
    out = {}
    b = f = 0
    for i in injecting_layers(min(decode_attn, LAYERS)):
        cb, cf = decode_attn_copy(heads_of(attn_bank(i)))
        b += cb
        f += cf
    out["decode_attn"] = dict(copies=min(decode_attn, LAYERS), bytes=b, flops=f)

    b = f = 0
    n = 0
    for i in injecting_layers(min(decode_routed, LAYERS - 1)):
        cb, cf = decode_routed_copy()
        b += cb
        f += cf
        n += 1
    out["decode_routed"] = dict(copies=n, bytes=b, flops=f)

    b = f = 0
    n = 0
    for i in injecting_layers(min(prefill_routed, LAYERS - 1)):
        cb, cf = prefill_routed_copy()
        b += cb
        f += cf
        n += 1
    out["prefill_routed"] = dict(copies=n, bytes=b, flops=f)

    b = f = 0
    for i in injecting_layers(min(prefill_attn, LAYERS)):
        cb, cf = prefill_attn_copy(heads_of(attn_bank(i)))
        b += cb
        f += cf
    out["prefill_attn"] = dict(copies=min(prefill_attn, LAYERS), bytes=b, flops=f)
    return out


# --- receipt arithmetic -----------------------------------------------------

SD_S = 0.0193  # relative sd of the prefill axis over 929 pinned baselines
SD_T = 0.0034  # relative sd of the decode axis


def axes(metrics: dict) -> tuple[float, float]:
    """(S, T) in ms: S = one 512-token prefill, T = one steady 1-token step."""
    s = 512000.0 * metrics["prefill_seconds_per_token"]
    t = 1000.0 * metrics["decode_seconds_per_token"] - s / 128.0
    return s, t


def load(path: str) -> dict:
    """Local `score.*.json` (key `metrics`) or one official feed receipt.

    An official receipt is addressed as `<subs.json>:<id-prefix>` and read from
    `officialMetrics`, which carries the same field names.
    """
    if ":" in path:
        path, prefix = path.rsplit(":", 1)
        with open(path) as fh:
            subs = json.load(fh)["submissions"]
        hits = [s for s in subs if (s.get("id") or "").startswith(prefix)]
        if len(hits) != 1:
            raise SystemExit(f"{prefix}: matched {len(hits)} receipts")
        return hits[0]["officialMetrics"]
    with open(path) as fh:
        return json.load(fh)["metrics"]


def rate(delta_ms: float, sd_ms: float, byts: int, flops: int) -> str:
    if delta_ms <= 0:
        return f"delta {delta_ms:+.3f} ms <= 0: no rate"
    gbs = byts / 1e9 / (delta_ms / 1e3)
    tflops = flops / 1e12 / (delta_ms / 1e3)
    rel = sd_ms / delta_ms
    return (
        f"delta {delta_ms:.3f} +/- {sd_ms:.3f} ms ({100*rel:.1f}%)  "
        f"{gbs:.1f} GB/s  {tflops:.2f} TFLOP/s  "
        f"[{gbs*(1-rel):.1f}-{gbs*(1+rel):.1f} GB/s, "
        f"{tflops*(1-rel):.2f}-{tflops*(1+rel):.2f} TFLOP/s]"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--low", help="score JSON at the lower injection level")
    ap.add_argument("--high", help="score JSON at the higher injection level")
    ap.add_argument("--low-config", default="0,0,0,0", help="da,dr,pr,pa")
    ap.add_argument("--high-config", default="0,0,0,0", help="da,dr,pr,pa")
    ap.add_argument("--normalize", action="store_true",
                    help="scale the high receipt by the ratio of pinned baselines")
    ap.add_argument("--sd-s", type=float, default=SD_S,
                    help="relative sd of the prefill axis (default: pinned-baseline sd)")
    ap.add_argument("--sd-t", type=float, default=SD_T,
                    help="relative sd of the decode axis")
    args = ap.parse_args()

    lo_cfg = [int(x) for x in args.low_config.split(",")]
    hi_cfg = [int(x) for x in args.high_config.split(",")]
    lo_tot = totals(*lo_cfg)
    hi_tot = totals(*hi_cfg)

    print("configuration deltas (high - low)")
    for key in ("decode_attn", "decode_routed", "prefill_routed", "prefill_attn"):
        db = hi_tot[key]["bytes"] - lo_tot[key]["bytes"]
        df = hi_tot[key]["flops"] - lo_tot[key]["flops"]
        dc = hi_tot[key]["copies"] - lo_tot[key]["copies"]
        if dc or db:
            print(
                f"  {key:16s} copies {dc:+3d}  bytes {db/1e6:10.2f} MB  "
                f"flops {df/1e9:8.2f} GFLOP"
            )
    if not (args.low and args.high):
        return

    lo, hi = load(args.low), load(args.high)
    s_lo, t_lo = axes(lo)
    s_hi, t_hi = axes(hi)
    scale = 1.0
    if args.normalize:
        # Same-session pinned baseline ratio: removes host/session drift.
        b_lo = 512000.0 * lo["baseline_prefill_seconds_per_token"]
        b_hi = 512000.0 * hi["baseline_prefill_seconds_per_token"]
        scale = b_lo / b_hi
        print(f"\nsession normalisation (prefill pinned baseline ratio): {scale:.4f}")
        s_hi *= scale
        # Baseline decode axis carries the same amortised seed prefill as the
        # candidate axis, so correct it before taking the ratio.
        d_lo = 1000.0 * lo["baseline_decode_seconds_per_token"] - b_lo / 128.0
        d_hi = 1000.0 * hi["baseline_decode_seconds_per_token"] - b_hi / 128.0
        t_scale = d_lo / d_hi
        print(f"session normalisation (decode pinned baseline ratio): {t_scale:.4f}")
        t_hi *= t_scale

    print(f"\nS low {s_lo:8.3f} ms   S high {s_hi:8.3f} ms")
    print(f"T low {t_lo:8.3f} ms   T high {t_hi:8.3f} ms")

    sd_s = math.hypot(args.sd_s * s_lo, args.sd_s * s_hi)
    sd_t = math.hypot(args.sd_t * t_lo, args.sd_t * t_hi)

    for name, keys, delta, sd in (
        ("prefill", ("prefill_routed", "prefill_attn"), s_hi - s_lo, sd_s),
        ("decode", ("decode_attn", "decode_routed"), t_hi - t_lo, sd_t),
    ):
        db = sum(hi_tot[k]["bytes"] - lo_tot[k]["bytes"] for k in keys)
        df = sum(hi_tot[k]["flops"] - lo_tot[k]["flops"] for k in keys)
        print(f"\n{name} axis: {rate(delta, sd, db, df)}")


if __name__ == "__main__":
    main()
