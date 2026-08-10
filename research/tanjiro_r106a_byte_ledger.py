#!/usr/bin/env python3
"""R106-A: decode-step byte ledger split into payload vs quantisation metadata.

Two independent parts.

Part A (`--ledger`) re-derives every one of the 25 families in
`research/artifacts/fern-r105d/decode-byte-census.json` from `weights/config.json`
plus the HEAD runtime representation read out of the Swift sources, and splits
each family's bytes into six buckets:

    routed_payload / routed_metadata / shared / attention_kv /
    embed_lmhead / activations

Every family is reconciled line by line against the accepted census so the
residual is a published number rather than an assumption (Rule 79).

Part B (`--scales`) is a CPU-only census of the shipped uint8 E4M3 NVFP4 scale
planes. It answers whether any of the metadata bytes are removable bit-exactly:
run-of-2 (already exploited at HEAD), run-of-4 (group 64) and run-of-8
(group 128) equality, per-row span and distinct-code counts (the precondition
for the lane-major 4-bit-delta encoding), and the group-32 code entropy that
bounds any fixed-width recode.

Usage:
  python3 research/tanjiro_r106a_byte_ledger.py --ledger
  python3 research/tanjiro_r106a_byte_ledger.py --scales --layers 1,20,39
  python3 research/tanjiro_r106a_byte_ledger.py --scales --all --out artifact.json
"""

import argparse
import json
import struct
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
WEIGHTS = REPO / "weights"
CENSUS = REPO / "research/artifacts/fern-r105d/decode-byte-census.json"

# ---------------------------------------------------------------- geometry
HIDDEN = 2048
LAYERS = 40
SPARSE_LAYERS = 39  # layer 0 is dense
SLIDING_LAYERS, SLIDING_HEADS = 30, 64
FULL_LAYERS, FULL_HEADS = 10, 48
KV_HEADS, HEAD_DIM = 8, 128
SLIDING_WINDOW = 512
FULL_POSITIONS = 576  # 512-token seed + 128 steps, mean occupancy
EXPERTS, TOPK = 256, 8
MOE_INTER, SHARED_INTER = 512, 512
DENSE_INTER = 8192
VOCAB = 100352

# HEAD representation, from the Swift sources rather than from a profiler label.
#   routed + shared NVFP4 scale planes are halved to one uint8 per 32 weights
#     (LagunaRuntimeWeights.swift:1038-1160, LagunaRuntimeModel.swift:8883-9050)
#   attention q/k/v/o are re-quantised to NVFP4 g16 and their scale plane is
#     replaced by a lane-major pairwise nibble bank: groups/4 nibble bytes plus
#     one uint8 row base (LagunaRuntimeWeights.swift:857-943)
#   per-head g_proj is affine INT8 group-32 with bfloat16 scales AND biases
#     (LagunaRuntimeModel.swift:482-497, dispatch guard :4526-4540)
#   lm_head decode reads the int5 coarse base plane: 1024 code bytes plus 64
#     e8m0 scale bytes per row (LagunaLmHeadPrune.swift:816-828, 896-919)
ROUTED_SCALE_GROUP = 32
SHARED_SCALE_GROUP = 32


def nvfp4_row(in_features, group):
    """Payload, metadata bytes for one NVFP4 row at the given scale group."""
    return in_features // 2, in_features // group


def lane_major_row(in_features):
    """Payload, metadata for one attention row: pairwise lane-major nibbles."""
    groups = in_features // 16
    return in_features // 2, groups // 4 + 1


def bf16_row(in_features):
    return in_features * 2, 0


def int8_affine_row(in_features, group=32):
    """INT8 code byte per weight, bfloat16 scale AND bias per group."""
    return in_features, 2 * 2 * (in_features // group)


# bucket, calls, (payload, metadata) per call, provenance
def families():
    rgu_p, rgu_m = nvfp4_row(HIDDEN, ROUTED_SCALE_GROUP)
    n = TOPK * 2 * MOE_INTER
    rows = [
        ("routed_nvfp4_swiglu_qmv_packed_top8keys", "routed", SPARSE_LAYERS,
         n * rgu_p, n * rgu_m,
         "top-8 experts x {gate,up} x 512 rows x 2048-wide NVFP4 g32"),
    ]

    rdn_p, rdn_m = nvfp4_row(MOE_INTER, ROUTED_SCALE_GROUP)
    sdn_p, sdn_m = nvfp4_row(SHARED_INTER, SHARED_SCALE_GROUP)
    rows.append(
        ("routed_shared_nvfp4_down_residual", "routed+shared", SPARSE_LAYERS,
         TOPK * HIDDEN * rdn_p + HIDDEN * sdn_p,
         TOPK * HIDDEN * rdn_m + HIDDEN * sdn_m,
         "routed: 8 x 2048 rows x 512-wide; shared: 2048 rows x 512-wide"))

    sgu_p, sgu_m = nvfp4_row(HIDDEN, SHARED_SCALE_GROUP)
    rows.append(
        ("shared_nvfp4_swiglu_qmv_rows1_halved", "shared", SPARSE_LAYERS,
         2 * SHARED_INTER * sgu_p, 2 * SHARED_INTER * sgu_m,
         "shared {gate,up} x 512 rows x 2048-wide NVFP4 g32"))

    for name, layers, heads in (("nvfp4_qkv_h64", SLIDING_LAYERS, SLIDING_HEADS),
                                ("nvfp4_qkv_h48", FULL_LAYERS, FULL_HEADS)):
        qkv_rows = heads * HEAD_DIM + 2 * KV_HEADS * HEAD_DIM
        p, m = lane_major_row(HIDDEN)
        rows.append((name, "attention", layers, qkv_rows * p, qkv_rows * m,
                     f"{qkv_rows} fused q/k/v rows x 2048-wide NVFP4 g16 lane-major"))

    for name, layers, heads in (("oproj_act_h64", SLIDING_LAYERS, SLIDING_HEADS),
                                ("oproj_act_h48", FULL_LAYERS, FULL_HEADS)):
        p, m = lane_major_row(heads * HEAD_DIM)
        rows.append((name, "attention", layers, HIDDEN * p, HIDDEN * m,
                     f"2048 rows x {heads * HEAD_DIM}-wide NVFP4 g16 lane-major"))

    for name, layers, heads in (("gate_sp_h64", SLIDING_LAYERS, SLIDING_HEADS),
                                ("gate_sp_h48", FULL_LAYERS, FULL_HEADS)):
        p, m = int8_affine_row(HIDDEN)
        rows.append((name, "attention", layers, heads * p, heads * m,
                     f"{heads} per-head g_proj rows, affine INT8 g32 + bf16 scale/bias"))

    kv_row = KV_HEADS * HEAD_DIM * 2 * 2
    rows.append(("sliding_fused_attn_ring", "attention_kv", SLIDING_LAYERS,
                 SLIDING_WINDOW * kv_row, 0, "512-position ring, K+V bf16, 8 kv heads"))
    rows.append(("full_fused_attn_grow", "attention_kv", FULL_LAYERS,
                 FULL_POSITIONS * kv_row, 0,
                 f"{FULL_POSITIONS} mean positions, K+V bf16, 8 kv heads"))

    rows.append(("residual_rms_router", "routed", SPARSE_LAYERS,
                 EXPERTS * bf16_row(HIDDEN)[0], 0, "router 256x2048 bf16, unquantised"))
    rows.append(("dense_gate_up_swiglu", "dense", 1,
                 2 * DENSE_INTER * bf16_row(HIDDEN)[0], 0,
                 "layer-0 dense MLP gate+up, bf16, unquantised"))
    rows.append(("dense_down_residual", "dense", 1,
                 HIDDEN * bf16_row(DENSE_INTER)[0], 0,
                 "layer-0 dense MLP down, bf16, unquantised"))

    rows.append(("lmhead_int5_base_coarse_delta", "embed_lmhead", 1,
                 VOCAB * 1024, VOCAB * 64,
                 "int5 coarse base plane: 1024 nibble bytes + 64 e8m0 scale bytes per row"))

    # activation-only families (r105-D tail); byte totals adopted from the census
    # because they are activation traffic, not a weight-geometry product.
    tail = {
        "lmhead_exact_fused_int5_sparse_refine": 526848,
        "rmsbfloat16": 503808,
        "gather_front": 401408,
        "lmhead_coarse_argmax_stage1": 229376,
        "vn_copy": 200704,
        "prefill_router_tournament": 62400,
        "residual_rms_bf16_2048_v1": 16384,
        "embedding_rope_atlas": 9216,
        "argmax": 8192,
        "lmhead_exact_winner": 512,
    }
    for name, b in tail.items():
        rows.append((name, "activations", 1, b, 0, "r105-D tail, activation traffic"))
    return rows


# per-call activation operands omitted by the accepted census, from each
# kernel's declared inputNames/outputShapes.
ACTIVATION_OPERANDS = {
    "routed_nvfp4_swiglu_qmv_packed_top8keys": (SPARSE_LAYERS,
        HIDDEN * 2 + TOPK * 4 + TOPK * 2 * MOE_INTER * 2),
    "routed_shared_nvfp4_down_residual": (SPARSE_LAYERS,
        SHARED_INTER * 2 + TOPK * MOE_INTER * 2 + TOPK * 4 + TOPK * 4
        + 2 * HIDDEN * 2),
    "shared_nvfp4_swiglu_qmv_rows1_halved": (SPARSE_LAYERS,
        HIDDEN * 2 + SHARED_INTER * 2),
    "nvfp4_qkv_h64": (SLIDING_LAYERS,
        HIDDEN * 2 + (SLIDING_HEADS * HEAD_DIM + 2 * KV_HEADS * HEAD_DIM) * 2),
    "nvfp4_qkv_h48": (FULL_LAYERS,
        HIDDEN * 2 + (FULL_HEADS * HEAD_DIM + 2 * KV_HEADS * HEAD_DIM) * 2),
    "oproj_act_h64": (SLIDING_LAYERS,
        SLIDING_HEADS * HEAD_DIM * 2 + SLIDING_HEADS * 2 + HIDDEN * 2),
    "oproj_act_h48": (FULL_LAYERS,
        FULL_HEADS * HEAD_DIM * 2 + FULL_HEADS * 2 + HIDDEN * 2),
    "gate_sp_h64": (SLIDING_LAYERS, HIDDEN * 2 + SLIDING_HEADS * 2),
    "gate_sp_h48": (FULL_LAYERS, HIDDEN * 2 + FULL_HEADS * 2),
    "sliding_fused_attn_ring": (SLIDING_LAYERS, 2 * SLIDING_HEADS * HEAD_DIM * 2),
    "full_fused_attn_grow": (FULL_LAYERS, 2 * FULL_HEADS * HEAD_DIM * 2),
    "residual_rms_router": (SPARSE_LAYERS, 4 * HIDDEN * 2 + EXPERTS * 2 * 2),
    "dense_gate_up_swiglu": (1, HIDDEN * 2 + DENSE_INTER * 2),
    "dense_down_residual": (1, DENSE_INTER * 2 + 2 * HIDDEN * 2),
    "lmhead_int5_base_coarse_delta": (1, HIDDEN * 2 + VOCAB * 2),
}


def ledger():
    census = json.loads(CENSUS.read_text())
    accepted = {f["family"]: f["bytes_per_step"] for f in census["families"]}
    B = census["step_bytes"]

    rows, buckets, residual = [], {}, 0
    for name, bucket, calls, p, m, note in families():
        mine = calls * (p + m)
        acc = accepted.pop(name)
        rows.append({
            "family": name, "bucket": bucket, "calls": calls,
            "payload_bytes": calls * p, "metadata_bytes": calls * m,
            "derived_bytes": mine, "accepted_bytes": acc,
            "delta_bytes": mine - acc, "note": note,
        })
        residual += mine - acc
        b = buckets.setdefault(bucket, {"payload": 0, "metadata": 0})
        b["payload"] += calls * p
        b["metadata"] += calls * m

    assert not accepted, f"unmatched census families: {sorted(accepted)}"

    act = sum(c * b for c, b in ACTIVATION_OPERANDS.values())
    derived_total = sum(r["derived_bytes"] for r in rows)

    out = {
        "accepted_step_bytes": B,
        "derived_step_bytes": derived_total,
        "reconciliation_residual_bytes": residual,
        "reconciliation_residual_pct_of_B": 100.0 * residual / B,
        "buckets": buckets,
        "metadata_total_bytes": sum(b["metadata"] for b in buckets.values()),
        "omitted_activation_operand_bytes": act,
        "omitted_activation_operand_pct_of_B": 100.0 * act / B,
        "families": rows,
    }
    meta = out["metadata_total_bytes"]
    out["metadata_pct_of_B"] = 100.0 * meta / B
    # price model: 1 % of B == 27.7 us/step == 0.42 % of the common score
    out["metadata_pct_of_score_if_fully_free"] = out["metadata_pct_of_B"] * 0.42
    return out


# ---------------------------------------------------------------- part B
def load_index():
    idx = {}
    for shard in sorted(WEIGHTS.glob("model-*-of-*.safetensors")):
        with open(shard, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            hdr = json.loads(f.read(n))
        base = 8 + n
        for k, v in hdr.items():
            if k == "__metadata__":
                continue
            idx[k] = (shard, base + v["data_offsets"][0],
                      base + v["data_offsets"][1], v["dtype"], tuple(v["shape"]))
    return idx


def read_u8(idx, name):
    shard, a, b, dtype, shape = idx[name]
    assert dtype == "U8", (name, dtype)
    with open(shard, "rb") as f:
        f.seek(a)
        buf = f.read(b - a)
    return np.frombuffer(buf, dtype=np.uint8).reshape(shape)


def plane_census(arr):
    """arr: (..., G) uint8 group-16 scale codes. Rows are the last axis."""
    rows = arr.reshape(-1, arr.shape[-1])
    nrows, g = rows.shape
    stats = {"rows": nrows, "groups_per_row": g}

    # run-of-k equality: all k consecutive group-16 codes in a row identical.
    for k in (2, 4, 8):
        if g % k:
            stats[f"run{k}_equal_frac"] = None
            continue
        blk = rows.reshape(nrows, g // k, k)
        eq = (blk == blk[:, :, :1]).all(axis=2)
        stats[f"run{k}_equal_frac"] = float(eq.mean())
        stats[f"run{k}_blocks"] = int(eq.size)
        stats[f"run{k}_exceptions"] = int((~eq).sum())

    # group-32 view: the plane HEAD actually reads.
    h = rows.reshape(nrows, g // 2, 2)[:, :, 0]
    stats["g32_distinct_codes_per_tensor_mean"] = float(np.unique(h).size)
    per_row_distinct = np.array(
        [np.unique(h[i]).size for i in range(0, nrows, max(1, nrows // 4096))])
    stats["g32_row_distinct_mean"] = float(per_row_distinct.mean())
    stats["g32_row_distinct_max"] = int(per_row_distinct.max())
    stats["g32_row_distinct_le8_frac"] = float((per_row_distinct <= 8).mean())
    span = h.max(axis=1).astype(np.int32) - h.min(axis=1).astype(np.int32)
    stats["g32_row_span_mean"] = float(span.mean())
    stats["g32_row_span_le15_frac"] = float((span <= 15).mean())
    counts = np.bincount(h.reshape(-1), minlength=256).astype(np.float64)
    p = counts[counts > 0] / counts.sum()
    stats["g32_entropy_bits"] = float(-(p * np.log2(p)).sum())
    return stats


def merge(acc, s):
    for k, v in s.items():
        if v is None:
            acc[k] = None
        elif k.endswith("_frac") or k.endswith("_mean") or k.endswith("_bits"):
            acc.setdefault("_w", 0)
            acc[k] = acc.get(k, 0.0) + v
        elif k.endswith("_max") or k == "groups_per_row":
            acc[k] = max(acc.get(k, 0), v)
        else:
            acc[k] = acc.get(k, 0) + v
    acc["_n"] = acc.get("_n", 0) + 1
    return acc


def finish(acc):
    n = acc.pop("_n")
    acc.pop("_w", None)
    for k in list(acc):
        if acc[k] is not None and (
            k.endswith("_frac") or k.endswith("_mean") or k.endswith("_bits")
        ):
            acc[k] /= n
    acc["tensors"] = n
    return acc


def scales(layers):
    idx = load_index()
    classes = {
        "routed_gate_up": [
            f"model.layers.{l}.mlp.switch_mlp.{p}_proj.scales"
            for l in layers for p in ("gate", "up")],
        "routed_down": [
            f"model.layers.{l}.mlp.switch_mlp.down_proj.scales" for l in layers],
        "shared_gate_up": [
            f"model.layers.{l}.mlp.shared_expert.{p}_proj.scales"
            for l in layers for p in ("gate", "up")],
        "shared_down": [
            f"model.layers.{l}.mlp.shared_expert.down_proj.scales" for l in layers],
    }
    out = {}
    for cls, names in classes.items():
        acc = {}
        for name in names:
            if name not in idx:
                continue
            merge(acc, plane_census(read_u8(idx, name)))
        if acc:
            out[cls] = finish(acc)
            print(f"{cls}: {json.dumps(out[cls])}", flush=True)
    return out


def ceiling(B, scale_stats=None):
    """Ceiling on BIT-EXACT metadata removal, per site, under two encodings.

    `nibble-delta` is the lane-major encoding already shipped for attention:
    `groups / 2` nibble bytes plus one uint8 row base, valid only for rows whose
    code span is <= 15. It keeps a fixed-width, O(1) per-lane scale fetch, which
    is the Rule-66 precondition for a byte cut to be worth its nominal rate.

    `entropy` is the Shannon floor of the measured group-32 code distribution.
    It is a bound on any coder, but reaching it needs variable-length codes, so
    a lane can no longer compute its own scale offset.
    """
    sites = {
        # rows/step, group-32 groups per row
        "routed_gate_up": (SPARSE_LAYERS * TOPK * 2 * MOE_INTER, HIDDEN // 32),
        "routed_down": (SPARSE_LAYERS * TOPK * HIDDEN, MOE_INTER // 32),
        "shared_gate_up": (SPARSE_LAYERS * 2 * SHARED_INTER, HIDDEN // 32),
        "shared_down": (SPARSE_LAYERS * HIDDEN, SHARED_INTER // 32),
        "lmhead_int5_e8m0": (VOCAB, HIDDEN // 32),
    }
    out = {}
    tot_nd = tot_ent = 0
    for site, (rows, g) in sites.items():
        now = rows * g
        nd = rows * (g // 2 + 1)
        h = (scale_stats or {}).get(site, {}).get("g32_entropy_bits")
        ent = int(round(now * h / 8.0)) if h else None
        row = {
            "metadata_bytes_now": now,
            "nibble_delta_bytes": nd,
            "nibble_delta_saving": now - nd,
            "nibble_delta_pct_of_B": 100.0 * (now - nd) / B,
            "measured_g32_entropy_bits": h,
            "entropy_floor_bytes": ent,
            "entropy_saving": None if ent is None else now - ent,
            "entropy_pct_of_B": None if ent is None else 100.0 * (now - ent) / B,
        }
        out[site] = row
        tot_nd += now - nd
        tot_ent += (now - ent) if ent is not None else (now - nd)

    out["_total"] = {
        "nibble_delta_saving": tot_nd,
        "nibble_delta_pct_of_B": 100.0 * tot_nd / B,
        "nibble_delta_pct_of_score": 100.0 * tot_nd / B * 0.42,
        "entropy_saving": tot_ent,
        "entropy_pct_of_B": 100.0 * tot_ent / B,
        "entropy_pct_of_score": 100.0 * tot_ent / B * 0.42,
        "stage3_gate_pct_of_B": 1.2,
        "largest_single_component_pct_of_B": max(
            v["nibble_delta_pct_of_B"] for k, v in out.items() if k != "_total"),
        "addressable_aggregate_clears_gate": 100.0 * tot_nd / B >= 1.2,
        "entropy_aggregate_clears_gate": 100.0 * tot_ent / B >= 1.2,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", action="store_true")
    ap.add_argument("--scales", action="store_true")
    ap.add_argument("--layers", default="1,20,39")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    result = {}
    if a.scales:
        layers = (range(1, LAYERS) if a.all
                  else [int(x) for x in a.layers.split(",")])
        result["scales"] = scales(list(layers))
        result["scales_layers"] = list(layers)
    if a.ledger:
        result["ledger"] = ledger()
        L = result["ledger"]
        print(f"derived {L['derived_step_bytes']} vs accepted "
              f"{L['accepted_step_bytes']}  residual {L['reconciliation_residual_bytes']} "
              f"({L['reconciliation_residual_pct_of_B']:+.4f}% of B)")
        for f in L["families"]:
            if f["delta_bytes"]:
                print(f"  MISMATCH {f['family']}: {f['delta_bytes']:+d} B")
        for b, v in sorted(L["buckets"].items()):
            print(f"  {b:16s} payload {v['payload']:>13d}  metadata {v['metadata']:>11d}")
        print(f"metadata total {L['metadata_total_bytes']} = "
              f"{L['metadata_pct_of_B']:.4f}% of B "
              f"(<= {L['metadata_pct_of_score_if_fully_free']:.4f}% of score)")
        print(f"activation operands omitted by census: "
              f"{L['omitted_activation_operand_bytes']} "
              f"({L['omitted_activation_operand_pct_of_B']:.4f}% of B)")
        result["ceiling"] = ceiling(L["accepted_step_bytes"], result.get("scales"))
        for site, v in result["ceiling"].items():
            if site == "_total":
                print(f"  ceiling TOTAL  addressable {v['nibble_delta_saving']} B "
                      f"({v['nibble_delta_pct_of_B']:.4f}% of B, "
                      f"{v['nibble_delta_pct_of_score']:.4f}% of score); "
                      f"entropy {v['entropy_saving']} B "
                      f"({v['entropy_pct_of_B']:.4f}% of B); gate 1.2%: "
                      f"addressable={v['addressable_aggregate_clears_gate']} "
                      f"entropy={v['entropy_aggregate_clears_gate']}; "
                      f"largest single {v['largest_single_component_pct_of_B']:.4f}%")
            else:
                print(f"  ceiling {site:18s} now {v['metadata_bytes_now']:>9d} "
                      f"nibble-delta -{v['nibble_delta_saving']:>8d} "
                      f"({v['nibble_delta_pct_of_B']:.4f}%)  entropy-floor "
                      f"-{v['entropy_saving']} ({v['entropy_pct_of_B']})")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, indent=1))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
