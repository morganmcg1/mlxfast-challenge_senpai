#!/usr/bin/env python3
"""R96-C Stage 1: exponent-span census of layer-0's dense BF16 MLP.

Research-only. Reads the transformed `weights/` tree that the runtime loads and
answers the pre-registered questions in
research/fern-r96-stage1-preregistration.md (D1-D5).

Usage: python3 research/fern_r96_dense_census.py [weights_dir] [--wandb]
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

BASE_BYTES = 100_663_296
BYTE_PRICE_PCT_PER_MB = 0.015224  # PR #110 realised ledger
M4_BYTES_PER_S = 266.3e9  # #498 DRAM model marginal term
TENSORS = [
    "model.layers.0.mlp.gate_proj.weight",
    "model.layers.0.mlp.up_proj.weight",
    "model.layers.0.mlp.down_proj.weight",
]


def load_bf16(weights: Path, name: str) -> np.ndarray:
    idx = json.loads((weights / "model.safetensors.index.json").read_text())["weight_map"]
    path = weights / idx[name]
    with open(path, "rb") as f:
        hlen = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(hlen))
        meta = header[name]
        assert meta["dtype"] == "BF16", meta["dtype"]
        start, end = meta["data_offsets"]
        f.seek(8 + hlen + start)
        raw = f.read(end - start)
    return np.frombuffer(raw, dtype="<u2").reshape(meta["shape"])


def fields(u: np.ndarray):
    exp = ((u >> 7) & 0xFF).astype(np.int16)
    mant = (u & 0x7F).astype(np.uint8)
    sign = (u >> 15).astype(np.uint8)
    return exp, mant, sign


def block_spans(exp: np.ndarray, live: np.ndarray, block: int):
    """Per-block (max_exp - min_exp) over live (normal, non-zero) weights.

    Returns (span, has_live, n_blocks_per_row). Blocks with no live weight get
    span 0 and has_live False.
    """
    rows, cols = exp.shape
    assert cols % block == 0
    g_exp = exp.reshape(rows, cols // block, block)
    g_live = live.reshape(rows, cols // block, block)
    hi = np.where(g_live, g_exp, np.int16(-1)).max(axis=2)
    lo = np.where(g_live, g_exp, np.int16(512)).min(axis=2)
    has = g_live.any(axis=2)
    span = np.where(has, hi - lo, 0).astype(np.int32)
    return span, has, cols // block


def pack_groups(vals: np.ndarray, width: int) -> np.ndarray:
    """Pack `width`-bit values, 8 per group, into `width` bytes per group.

    Little-endian within the group: value i occupies bits [width*i, width*i+width).
    """
    assert vals.size % 8 == 0
    g = vals.reshape(-1, 8).astype(np.uint64)
    acc = np.zeros(g.shape[0], dtype=np.uint64)
    for i in range(8):
        acc |= g[:, i] << np.uint64(width * i)
    out = np.empty((g.shape[0], width), dtype=np.uint8)
    for b in range(width):
        out[:, b] = ((acc >> np.uint64(8 * b)) & np.uint64(0xFF)).astype(np.uint8)
    return out.reshape(-1)


def unpack_groups(buf: np.ndarray, width: int, count: int) -> np.ndarray:
    g = buf.reshape(-1, width)
    acc = np.zeros(g.shape[0], dtype=np.uint64)
    for b in range(width):
        acc |= g[:, b].astype(np.uint64) << np.uint64(8 * b)
    mask = np.uint64((1 << width) - 1)
    out = np.empty((g.shape[0], 8), dtype=np.uint64)
    for i in range(8):
        out[:, i] = (acc >> np.uint64(width * i)) & mask
    return out.reshape(-1)[:count]


def escape_line_bytes(esc: np.ndarray, block: int, strided: bool) -> int:
    """Bytes really moved to re-read escaped weights from the resident original.

    With reduction-axis blocking an escaped block is `block` contiguous ushorts,
    so 2 B/weight is line-accurate. With output-axis blocking the same block is
    `block` weights one row apart in the original tensor, so each one pulls its
    own 64 B line; lines are shared by the 32 neighbouring reduction indices.
    """
    if not strided:
        return int(esc.sum()) * block * 2
    rows, bpr = esc.shape
    assert rows % 32 == 0
    return int(esc.reshape(rows // 32, 32, bpr).any(axis=1).sum()) * block * 64


def roundtrip(u: np.ndarray, block: int, d: int, m: int, zero_code: bool, strided: bool = False):
    """Real bit-packed encode/decode of one tensor. Returns (recon, stats)."""
    rows, cols = u.shape
    exp, mant, sign = fields(u)
    is_zero = (u & 0x7FFF) == 0
    live = ~is_zero & (exp != 0)
    span, has, bpr = block_spans(exp, live, block)
    usable = (1 << d) - 1 - (1 if zero_code else 0)
    subnormal = (exp == 0) & (mant != 0)
    g_sub = subnormal.reshape(rows, bpr, block).any(axis=2)
    g_inf = (exp == 255).reshape(rows, bpr, block).any(axis=2)
    esc = (span > usable) | g_sub | g_inf
    base = np.where(has & ~esc, np.where(live, exp, np.int16(512)).reshape(rows, bpr, block).min(axis=2), 0)
    base = np.where(esc, 0xFF, base).astype(np.uint8)

    # planes
    delta = np.where(live.reshape(rows, bpr, block), exp.reshape(rows, bpr, block) - base[:, :, None].astype(np.int16), 0)
    if zero_code:
        delta = np.where(is_zero.reshape(rows, bpr, block), usable + 1, delta)
    delta = np.clip(delta, 0, (1 << d) - 1).astype(np.uint64).reshape(-1)
    payload = ((sign.astype(np.uint64) << np.uint64(m)) | (mant.astype(np.uint64) >> np.uint64(7 - m))).reshape(-1)

    dplane = pack_groups(delta, d)
    pplane = pack_groups(payload, 1 + m)
    raw_rows, raw_cols = np.nonzero(esc)
    rawplane = u.reshape(rows, bpr, block)[raw_rows, raw_cols].copy()

    # decode
    dd = unpack_groups(dplane, d, u.size).reshape(rows, bpr, block)
    pp = unpack_groups(pplane, 1 + m, u.size).reshape(rows, bpr, block)
    s = (pp >> np.uint64(m)).astype(np.uint16)
    mt = ((pp & np.uint64((1 << m) - 1)) << np.uint64(7 - m)).astype(np.uint16)
    e = (base[:, :, None].astype(np.uint16) + dd.astype(np.uint16)) & 0xFF
    recon = (s.astype(np.uint16) << 15) | (e << 7) | mt
    if zero_code:
        recon = np.where(dd == usable + 1, s.astype(np.uint16) << 15, recon)
    recon = np.where(esc[:, :, None], u.reshape(rows, bpr, block), recon)
    recon = recon.reshape(rows, cols).astype(np.uint16)
    core = int(dplane.size + pplane.size + base.size)
    stats = dict(
        escaped_blocks=int(esc.sum()),
        total_blocks=int(esc.size),
        core_bytes=core,
        plane_bytes=core + int(rawplane.size) * 2,
        plane_bytes_row=core + int(esc.any(axis=1).sum()) * cols * (64 if strided else 2),
        plane_bytes_line=core + escape_line_bytes(esc, block, strided),
    )
    return recon, stats


def census_tensor(u: np.ndarray, strided: bool, pooled_hist: dict | None) -> dict:
    exp, mant, sign = fields(u)
    is_zero = (u & 0x7FFF) == 0
    subnormal = (exp == 0) & (mant != 0)
    infnan = exp == 255
    live = ~is_zero & (exp != 0)
    or_mant = int(np.bitwise_or.reduce(mant[live]))
    tz = 7 if or_mant == 0 else int((or_mant & -or_mant).bit_length() - 1)
    cnt16 = np.bincount(u.ravel(), minlength=65536)
    p = cnt16[cnt16 > 0] / u.size
    expc = np.bincount(exp[live].ravel().astype(np.int64), minlength=256)
    pe = expc[expc > 0] / expc.sum()
    rec = dict(
        shape=list(u.shape),
        n=int(u.size),
        zeros=int(is_zero.sum()),
        subnormals=int(subnormal.sum()),
        infnan=int(infnan.sum()),
        distinct16=int((cnt16 > 0).sum()),
        entropy16_bits=round(float(-(p * np.log2(p)).sum()), 4),
        exp_entropy_bits=round(float(-(pe * np.log2(pe)).sum()), 4),
        exp_distinct=int((expc > 0).sum()),
        exp_span_global=int(exp[live].max() - exp[live].min()),
        trailing_zero_mantissa_bits=tz,
        spans={},
    )
    for block in (32, 64, 128, u.shape[1]):
        span, has, bpr = block_spans(exp, live, block)
        hist = np.bincount(np.clip(span.ravel(), 0, 255), minlength=256)
        rec["spans"][str(block)] = dict(
            blocks=int(span.size),
            blocks_per_row=int(bpr),
            hist=[int(x) for x in hist[:33]],
            hist_full=[int(x) for x in hist],
            over32=int(hist[33:].sum()),
            max=int(span.max()),
            mean=round(float(span.mean()), 3),
            subnormal_blocks=int(subnormal.reshape(u.shape[0], bpr, block).any(axis=2).sum()),
        )
        key = str(block)
        if pooled_hist is not None:
            pooled_hist.setdefault(key, np.zeros(256, dtype=np.int64))
            pooled_hist[key] += hist
        # D3: per-row escaped-block count distribution, for each d
        for d in (2, 3, 4, 5, 6):
            usable = (1 << d) - 1 - (1 if int(is_zero.sum()) > 0 else 0)
            esc = (span > usable) | subnormal.reshape(u.shape[0], bpr, block).any(axis=2)
            per_row = esc.sum(axis=1)
            rec["spans"][key][f"esc_d{d}"] = dict(
                blocks=int(esc.sum()),
                frac=round(float(esc.mean()), 6),
                line_bytes=escape_line_bytes(esc, block, strided),
                rows_with_esc=int((per_row > 0).sum()),
                rows=int(esc.shape[0]),
                row_p50=int(np.percentile(per_row, 50)),
                row_p90=int(np.percentile(per_row, 90)),
                row_p99=int(np.percentile(per_row, 99)),
                row_max=int(per_row.max()),
            )
    return rec


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    weights = Path(args[0]) if args else Path("weights")
    use_wandb = "--wandb" in sys.argv
    axis0 = "--axis0" in sys.argv
    mixed = "--mixed" in sys.argv
    tag = "mixed" if mixed else ("axis0" if axis0 else "axis1")

    per_tensor = {}
    alt_tensor = {}
    pooled_hist = {}
    for name in TENSORS:
        raw = load_bf16(weights, name)
        u = np.ascontiguousarray(raw.T) if axis0 else raw
        per_tensor[name] = census_tensor(u, axis0, pooled_hist)
        if mixed:
            v = raw if axis0 else np.ascontiguousarray(raw.T)
            alt_tensor[name] = census_tensor(v, not axis0, None)
            del v
        del raw, u

    # D2 net-bytes grid
    any_zero = any(per_tensor[n]["zeros"] > 0 for n in TENSORS)
    min_tz = min(per_tensor[n]["trailing_zero_mantissa_bits"] for n in TENSORS)
    # a row-granular fallback re-reads one row of the blocking orientation; with
    # output-axis blocking that row is strided in the resident tensor, so every
    # element costs its own line.
    esc_unit = 64 if axis0 else 2
    grid = []
    for block_key in ("32", "64", "128", "row"):
        for d in (2, 3, 4, 5, 6):
            for m in sorted({7, 7 - min_tz}):
                if m < 1:
                    continue
                p_bits = 1 + d + m
                net_a = net_b = net_c = net_l = 0
                esc_blocks = tot_blocks = esc_rows = tot_rows = 0
                for name in TENSORS:
                    t = per_tensor[name]
                    bk = str(t["shape"][1]) if block_key == "row" else block_key
                    s = t["spans"][bk]
                    e = s[f"esc_d{d}"]
                    b = int(bk)
                    n = t["n"]
                    nb = s["blocks"]
                    core = n * p_bits // 8 + nb
                    net_a += core + e["blocks"] * b * 2
                    net_b += core + e["rows_with_esc"] * t["shape"][1] * esc_unit
                    net_c += core + nb * 4 + e["blocks"] * b * 2 - e["blocks"] * b * p_bits // 8
                    net_l += core + e["line_bytes"]
                    esc_blocks += e["blocks"]
                    tot_blocks += nb
                    esc_rows += e["rows_with_esc"]
                    tot_rows += e["rows"]
                row = dict(block=block_key, d=d, m=m, bits=p_bits)
                for design, net in (("a", net_a), ("b", net_b), ("c", net_c), ("l", net_l)):
                    saved = BASE_BYTES - net
                    row[f"net_{design}"] = int(net)
                    row[f"saved_MB_{design}"] = round(saved / 1e6, 3)
                    row[f"score_pct_{design}"] = round(saved / 1e6 * BYTE_PRICE_PCT_PER_MB, 4)
                    row[f"us_M4_{design}"] = round(saved / M4_BYTES_PER_S * 1e6, 1)
                row["esc_block_frac"] = round(esc_blocks / tot_blocks, 6)
                row["esc_row_frac"] = round(esc_rows / tot_rows, 6)
                row["admissible_m"] = m == 7 or min_tz >= 7 - m
                grid.append(row)

    print("=" * 100)
    print("D1  per-tensor census")
    print("=" * 100)
    for name, t in per_tensor.items():
        print(f"\n{name}  shape={t['shape']}  n={t['n']}")
        for k in ("zeros", "subnormals", "infnan", "distinct16", "entropy16_bits",
                  "exp_entropy_bits", "exp_distinct", "exp_span_global",
                  "trailing_zero_mantissa_bits"):
            print(f"  {k:32s} {t[k]}")
        for bk, s in t["spans"].items():
            print(f"  block={bk:5s} blocks={s['blocks']:9d} span max={s['max']:3d} mean={s['mean']:6.3f} "
                  f"subnorm_blocks={s['subnormal_blocks']}")
            print(f"      hist[0..16]={s['hist'][:17]} over32={s['over32']}")
            for d in (2, 3, 4, 5, 6):
                e = s[f"esc_d{d}"]
                print(f"      d={d}: esc_blocks={e['blocks']:9d} ({e['frac']*100:7.4f}%)  "
                      f"line_bytes={e['line_bytes']:10d}  rows_with_esc={e['rows_with_esc']}/{e['rows']}  "
                      f"row p50/p90/p99/max={e['row_p50']}/{e['row_p90']}/{e['row_p99']}/{e['row_max']}")

    print("\n" + "=" * 100)
    print("D1 pooled span histogram (all three tensors)")
    print("=" * 100)
    for bk, h in pooled_hist.items():
        tot = int(h.sum())
        print(f"block={bk}: total={tot}")
        cum = 0
        for span in range(0, 20):
            cum += int(h[span])
            print(f"   span={span:2d}  count={int(h[span]):10d}  frac={h[span]/tot:9.6f}  cum={cum/tot:9.6f}")
        print(f"   span>=20 count={int(h[20:].sum())} frac={h[20:].sum()/tot:.6f}")

    print("\n" + "=" * 100)
    print(f"D2 net-bytes grid   base={BASE_BYTES} B   any_zero={any_zero}  min_trailing_zero_mantissa={min_tz}")
    print("=" * 100)
    hdr = (f"{'blk':>5} {'d':>2} {'m':>2} {'bits':>4} | {'escblk%':>9} {'escrow%':>8} | "
           f"{'savedMB(l)':>10} {'%score':>7} {'usM4':>7} | {'savedMB(b)':>10} {'%score':>7} | "
           f"{'savedMB(a)':>10} {'savedMB(c)':>10}")
    print(hdr)
    for r in grid:
        if not r["admissible_m"]:
            continue
        print(f"{r['block']:>5} {r['d']:>2} {r['m']:>2} {r['bits']:>4} | "
              f"{r['esc_block_frac']*100:9.4f} {r['esc_row_frac']*100:8.4f} | "
              f"{r['saved_MB_l']:10.3f} {r['score_pct_l']:7.4f} {r['us_M4_l']:7.1f} | "
              f"{r['saved_MB_b']:10.3f} {r['score_pct_b']:7.4f} | "
              f"{r['saved_MB_a']:10.3f} {r['saved_MB_c']:10.3f}")

    # pre-registered selection: maximise saved bytes under designs (b) and the
    # line-accurate form of (a). Design (a)'s nominal 2 B/weight escape price is
    # only reachable when escaped weights are contiguous in the resident tensor.
    cands = []
    for r in grid:
        if not r["admissible_m"]:
            continue
        for design in ("l", "b"):
            cands.append((r[f"saved_MB_{design}"], design, r))
    cands.sort(key=lambda x: -x[0])
    best_saved, best_design, best = cands[0]
    print(f"\nBEST (designs l/b): block={best['block']} d={best['d']} m={best['m']} "
          f"design={best_design} saved={best_saved} MB  score={best[f'score_pct_{best_design}']}%  "
          f"escblk={best['esc_block_frac']*100:.4f}%")
    bar_pass = (BASE_BYTES - best[f"net_{best_design}"]) >= 21_300_000
    print(f"PRE-REGISTERED BAR (>= 21.3 MB saved): {'PASS' if bar_pass else 'FAIL'}")

    # E2: per-tensor (B,d,m,design) chosen independently, addendum A
    print("\n" + "=" * 100)
    print("E2 per-tensor optimum (each tensor picks its own B, d, design)")
    print("=" * 100)
    pick = {}
    for name in TENSORS:
        variants = [(per_tensor[name], axis0)]
        if mixed:
            variants.append((alt_tensor[name], not axis0))
        opts = []
        for t, t_axis0 in variants:
            row_unit = 64 if t_axis0 else 2
            for block_key in ("32", "64", "128", "row"):
                bk = str(t["shape"][1]) if block_key == "row" else block_key
                s = t["spans"][bk]
                b, n, nb = int(bk), t["n"], s["blocks"]
                for d in (2, 3, 4, 5, 6):
                    e = s[f"esc_d{d}"]
                    for m in sorted({7, 7 - min_tz}):
                        if m < 1 or not (m == 7 or min_tz >= 7 - m):
                            continue
                        p_bits = 1 + d + m
                        core = n * p_bits // 8 + nb
                        for design, net in (("l", core + e["line_bytes"]),
                                            ("b", core + e["rows_with_esc"] * t["shape"][1] * row_unit)):
                            opts.append(dict(block=block_key, B=b, d=d, m=m, bits=p_bits, design=design,
                                             axis0=bool(t_axis0), shape=list(t["shape"]),
                                             net=int(net), saved=int(n * 2 - net),
                                             esc_blocks=int(e["blocks"]),
                                             esc_frac=round(e["blocks"] / nb, 6)))
        opts.sort(key=lambda o: -o["saved"])
        pick[name] = opts[0]
        print(f"\n{name}:")
        for o in opts[:6]:
            print(f"   axis={'output' if o['axis0'] else 'reduction'} shape={o['shape']} "
                  f"B={o['block']:>4} d={o['d']} m={o['m']} bits={o['bits']:2d} design={o['design']} "
                  f"esc={o['esc_frac']*100:8.4f}%  net={o['net']:9d}  saved={o['saved']/1e6:7.3f} MB")
    e2_net = sum(pick[n]["net"] for n in TENSORS)
    e2_saved = BASE_BYTES - e2_net
    print(f"\nE2 TOTAL net={e2_net}  saved={e2_saved/1e6:.3f} MB  "
          f"score={e2_saved/1e6*BYTE_PRICE_PCT_PER_MB:.4f}%  us_M4={e2_saved/M4_BYTES_PER_S*1e6:.1f}")
    e2_bar = e2_saved >= 21_300_000
    print(f"ADDENDUM-A BAR (>= 21.3 MB saved): {'PASS' if e2_bar else 'FAIL'}")

    # D4 round-trip for the per-tensor selection (E2), which dominates the
    # single global variant by construction.
    print("\n" + "=" * 100)
    print(f"D4 round-trip identity for the selected per-tensor variant ({tag})")
    print("=" * 100)
    mismatch_total = 0
    rt = {}
    for name in TENSORS:
        u = load_bf16(weights, name)
        p = pick[name]
        if p["axis0"]:
            u = np.ascontiguousarray(u.T)
        block = u.shape[1] if p["block"] == "row" else int(p["block"])
        recon, st = roundtrip(u, block, p["d"], p["m"], any_zero, strided=p["axis0"])
        bad = int((recon != u).sum())
        mismatch_total += bad
        h0 = hashlib.sha256(np.ascontiguousarray(u, dtype="<u2").tobytes()).hexdigest()
        h1 = hashlib.sha256(np.ascontiguousarray(recon, dtype="<u2").tobytes()).hexdigest()
        measured = st["plane_bytes_line"] if p["design"] == "l" else st["plane_bytes_row"]
        rt[name] = dict(mismatched=bad, sha_orig=h0, sha_recon=h1, hash_equal=h0 == h1,
                        picked=p, measured_bytes=measured, **st)
        print(f"  {name}: axis={'output' if p['axis0'] else 'reduction'} B={p['block']} d={p['d']} "
              f"m={p['m']} design={p['design']}  mismatched={bad}  "
              f"hash_equal={h0 == h1}  measured_bytes={measured}  (analytic {p['net']})  "
              f"escaped_blocks={st['escaped_blocks']}/{st['total_blocks']}")
        del u, recon
    measured_net = sum(v["measured_bytes"] for v in rt.values())
    print(f"  TOTAL mismatched weights = {mismatch_total} (must be 0)")
    print(f"  measured packed bytes    = {measured_net}  (analytic E2 net = {e2_net})")
    print(f"  measured saved           = {(BASE_BYTES - measured_net)/1e6:.3f} MB  "
          f"= {(BASE_BYTES - measured_net)/1e6*BYTE_PRICE_PCT_PER_MB:.4f}% score")

    out = dict(
        base_axis="output" if axis0 else "reduction", tag=tag, mixed=mixed,
        base_bytes=BASE_BYTES, any_zero=any_zero, min_trailing_zero_mantissa=min_tz,
        per_tensor=per_tensor, alt_tensor=alt_tensor, grid=grid,
        best=dict(best, design=best_design),
        bar_pass=bool(bar_pass), per_tensor_pick=pick,
        e2_net_bytes=int(e2_net), e2_saved_bytes=int(e2_saved), e2_bar_pass=bool(e2_bar),
        roundtrip=rt, measured_net_bytes=int(measured_net),
        measured_saved_bytes=int(BASE_BYTES - measured_net),
        pooled_hist={k: [int(x) for x in v] for k, v in pooled_hist.items()},
    )
    dest = Path(f"research/artifacts/fern_r96_dense_census_{tag}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")

    if use_wandb:
        import wandb
        run = wandb.init(project="mlxfast-maple", entity="wandb-applied-ai-team",
                         name=f"fern-r96c-stage1-dense-census-{tag}",
                         job_type="census",
                         config=dict(assignment="maple-r96-c-bf16-lossless-compaction",
                                     revision="r96-c-rev1", stage=1,
                                     base_axis="output" if axis0 else "reduction",
                                     mixed_axis=mixed,
                                     base_sha="43036cd39dd3c795b117b099f0fe52767fbedbca",
                                     prereg_sha="4aaed2e", host="M4 Pro"))
        run.log({
            "dense_mlp_bytes_per_step": int(measured_net),
            "dense_mlp_bytes_per_step_baseline": BASE_BYTES,
            "stage1_escape_block_fraction": float(sum(rt[n]["escaped_blocks"] for n in TENSORS)
                                                  / sum(rt[n]["total_blocks"] for n in TENSORS)),
            "stage1_net_bytes_saved": int(BASE_BYTES - measured_net),
            "stage1_net_score_pct": float((BASE_BYTES - measured_net) / 1e6 * BYTE_PRICE_PCT_PER_MB),
            "stage1_predicted_us_per_step_M4": float((BASE_BYTES - measured_net) / M4_BYTES_PER_S * 1e6),
            "roundtrip_mismatched_weights": int(mismatch_total),
            "stage1_bar_pass": int(e2_bar),
            "stage1_e2_net_bytes": int(e2_net),
            "stage1_e2_saved_bytes": int(e2_saved),
            "stage1_global_bar_pass": int(bar_pass),
            "stage1_global_saved_bytes": int(BASE_BYTES - best[f"net_{best_design}"]),
            "stage1_global_block": best["block"], "stage1_global_delta_bits": best["d"],
            "stage1_global_mantissa_bits": best["m"], "stage1_global_escape_design": best_design,
            **{f"stage1_pick_{n.split('.')[-2]}_{k}": pick[n][k]
               for n in TENSORS for k in ("block", "d", "m", "design", "saved")},
            **{f"stage1_pick_{n.split('.')[-2]}_axis":
               "output" if pick[n]["axis0"] else "reduction" for n in TENSORS},
        })
        art = wandb.Artifact(f"fern_r96_dense_census_{tag}", type="census")
        art.add_file(str(dest))
        run.log_artifact(art)
        print(f"W&B run: {run.url}  id={run.id}")
        run.finish()
    return 0 if mismatch_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
