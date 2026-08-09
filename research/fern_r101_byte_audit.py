#!/usr/bin/env python3
"""Research-only byte audit (not part of the submission surface).

Round-101 arm A, part P1: recompute the decode-step byte footprint of every
family in the r94 census from first principles, at the *current* layout epoch,
and re-price each family against the bandwidth ceiling measured on this host
by `research/fern_r101_bw_probe.swift` rather than against a theoretical peak.

Two independent sources are reconciled:

  * checkpoint ground truth -- the safetensors headers under `weights/`, read
    directly, giving every tensor's shape and dtype;
  * runtime representation -- what the scored decode kernels actually bind,
    which for QKV/o_proj/routed/shared is a group-16 NVFP4 bank at
    `in/2` code bytes plus `in/16` scale bytes per output row
    (`Sources/MLXFastModel/LagunaRuntimeModel.swift:4667-4672`).

The audit is what makes the round-101 P0 question answerable: a row that
exceeds the measured ceiling is either mis-byted (fault F1), mis-timed
(fault F2), or cache-served (fault F3), and only an exact byte model can
tell those apart.

Usage:
  python3 research/fern_r101_byte_audit.py [--weights weights] [--tsv OUT.tsv]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

# --- frozen geometry (Sources/MLXFastModel/LagunaConfig.swift:14-45) ---
VOCAB = 100_352
HIDDEN = 2_048
DENSE_INTER = 8_192
LAYERS = 40
KV_HEADS = 8
HEAD_DIM = 128
FULL_HEADS = 48
SLIDING_HEADS = 64
FULL_LAYERS = 10  # indices 0, 4, 8, ..., 36
SLIDING_LAYERS = 30
SLIDING_WINDOW = 512
# Full-attention layers keep every position. The timed decode pass seeds 512
# tokens then takes 128 one-token steps, so the mid-pass average context a full
# layer reads is 512 + 64. r94's census used this same 576.
FULL_POSITIONS = SLIDING_WINDOW + 64
EXPERTS = 256
TOPK = 8
MOE_INTER = 512
SHARED_INTER = 512
SPARSE_LAYERS = 39  # layers 1..39
NVFP4_GROUP = 16

DTYPE_BYTES = {"BF16": 2, "F16": 2, "F32": 4, "U8": 1, "U32": 4, "I32": 4, "I8": 1}


def nvfp4_row_bytes(in_dim: int, scale_group: int = NVFP4_GROUP) -> int:
    """Bytes one output row of a group-`scale_group` NVFP4 bank costs.

    4 bits per weight plus one uint8 E4M3 scale per group. `scale_group=32`
    is the post-#72 halved plane.
    """
    assert in_dim % scale_group == 0
    return in_dim // 2 + in_dim // scale_group


def lane_major_row_bytes(in_dim: int, escape_rate: float = 0.0) -> int:
    """Bytes one output row costs from `LagunaLaneMajorScaleBank`, pairwise arm.

    `LagunaRuntimeWeights.swift:866-887` packs the group-16 uint8 scale plane
    into `groups / 4` nibble bytes plus one base byte per row. A row whose
    32-element halves disagree, or whose span exceeds 15 codes, carries base
    `0xFF` and re-reads the stock `groups`-byte plane instead.
    """
    groups = in_dim // NVFP4_GROUP
    assert groups % 64 == 0
    narrow = groups // 4 + 1
    return round(in_dim // 2 + narrow + escape_rate * groups)


def bf16_row_bytes(in_dim: int) -> int:
    return in_dim * 2


# --- part 1: checkpoint ground truth -------------------------------------


def read_safetensors_headers(weights: pathlib.Path):
    tensors = {}
    for shard in sorted(weights.glob("model-*-of-*.safetensors")):
        with shard.open("rb") as fh:
            (hlen,) = struct.unpack("<Q", fh.read(8))
            head = json.loads(fh.read(hlen))
        for name, meta in head.items():
            if name == "__metadata__":
                continue
            tensors[name] = (meta["dtype"], tuple(meta["shape"]))
    return tensors


def checkpoint_summary(tensors):
    total = 0
    by_dtype = {}
    for _name, (dtype, shape) in tensors.items():
        n = 1
        for d in shape:
            n *= d
        b = n * DTYPE_BYTES[dtype]
        total += b
        by_dtype[dtype] = by_dtype.get(dtype, 0) + b
    return total, by_dtype


# --- part 2: decode-step footprint at the live representation ------------


def families(
    routed_scale_group: int,
    shared_scale_group: int,
    lmhead_mb: float,
    attn_lane_major: bool = True,
    escape_rate: float = 0.0,
):
    """Per-decode-step bytes for every r94 census family.

    `routed_scale_group` / `shared_scale_group` are 16 for the stock plane and
    32 for the halved plane; `lmhead_mb` is the screening cluster's actual
    traffic, which is not derivable from the nominal plane size.
    `attn_lane_major` selects the pairwise lane-major scale bank the QKV and
    o_proj decode kernels actually dispatch against at HEAD.
    """
    q_full = FULL_HEADS * HEAD_DIM
    q_slid = SLIDING_HEADS * HEAD_DIM
    kv = KV_HEADS * HEAD_DIM

    def attn_row(in_dim: int) -> int:
        if attn_lane_major:
            return lane_major_row_bytes(in_dim, escape_rate)
        return nvfp4_row_bytes(in_dim)

    # QKV: one NVFP4 bank whose output rows are q rows + k rows + v rows.
    qkv_h64 = SLIDING_LAYERS * (q_slid + 2 * kv) * attn_row(HIDDEN)
    qkv_h48 = FULL_LAYERS * (q_full + 2 * kv) * attn_row(HIDDEN)
    # o_proj: HIDDEN output rows, input = concatenated heads.
    op_h64 = SLIDING_LAYERS * HIDDEN * attn_row(q_slid)
    op_h48 = FULL_LAYERS * HIDDEN * attn_row(q_full)

    rgu = (
        SPARSE_LAYERS
        * TOPK
        * 2
        * MOE_INTER
        * nvfp4_row_bytes(HIDDEN, routed_scale_group)
    )
    rdown = (
        SPARSE_LAYERS * TOPK * HIDDEN * nvfp4_row_bytes(MOE_INTER, routed_scale_group)
    )
    sdown = SPARSE_LAYERS * HIDDEN * nvfp4_row_bytes(SHARED_INTER, shared_scale_group)
    sgu = (
        SPARSE_LAYERS
        * 2
        * SHARED_INTER
        * nvfp4_row_bytes(HIDDEN, shared_scale_group)
    )
    router = SPARSE_LAYERS * EXPERTS * bf16_row_bytes(HIDDEN)
    dense_gu = 2 * DENSE_INTER * bf16_row_bytes(HIDDEN)
    dense_dn = HIDDEN * bf16_row_bytes(DENSE_INTER)
    # Per-head g_proj: one gate row per query head. BF16 at HEAD -- the kernel
    # preconditions it (`LagunaRuntimeModel.swift:3383, 5734`), so the INT8
    # group-32 form the accepted envelope permits is not what actually loads.
    gate_h64 = SLIDING_LAYERS * SLIDING_HEADS * bf16_row_bytes(HIDDEN)
    gate_h48 = FULL_LAYERS * FULL_HEADS * bf16_row_bytes(HIDDEN)
    # Sliding attention reads at most `window` KV positions; full attention
    # reads every position so far. Both K and V, BF16, 8 KV heads.
    kv_row = KV_HEADS * HEAD_DIM * 2 * 2
    attn_slid = SLIDING_LAYERS * SLIDING_WINDOW * kv_row
    attn_full = FULL_LAYERS * FULL_POSITIONS * kv_row

    return [
        ("T2c routed gate+up qmv", rgu, 39),
        ("T0b(a) qkv h64", qkv_h64, 30),
        ("T3b oproj h64", op_h64, 30),
        ("T2d routed+shared down+residual", rdown + sdown, 39),
        ("T3a sliding fused attn", attn_slid, 30),
        ("T1c lmhead int5 base coarse delta", int(lmhead_mb * 1e6), 1),
        ("T0b(b) qkv h48", qkv_h48, 10),
        ("T1a residual rms router", router, 39),
        ("T3c oproj h48", op_h48, 10),
        ("T2a shared gate+up qmv", sgu, 39),
        ("dense gate_up (layer 0)", dense_gu, 1),
        ("T2b gate_sp h64", gate_h64, 30),
        ("T3a' full fused attn", attn_full, 10),
        ("dense_down (layer 0)", dense_dn, 1),
        ("T2b' gate_sp h48", gate_h48, 10),
    ]


# r94 census, `research/maple-frieren-r94-decode-residue-ledger.md:109-135` and
# the per-row rate table at `:173-194`.
R94 = {
    "T2c routed gate+up qmv": (1497.7, 1446.3, 368.1),
    "T0b(a) qkv h64": (1340.1, 1300.6, 353.9),
    "T3b oproj h64": (1117.7, 1078.2, 283.1),
    "T2d routed+shared down+residual": (858.9, 807.5, 207.0),
    "T3a sliding fused attn": (636.0, 596.5, 62.9),
    "T1c lmhead int5 base coarse delta": (420.3, 419.0, 128.5),
    "T0b(b) qkv h48": (362.8, 349.6, 94.4),
    "T1a residual rms router": (312.8, 261.4, 40.9),
    "T3c oproj h48": (301.8, 288.6, 70.8),
    "T2a shared gate+up qmv": (287.1, 235.7, 46.0),
    "dense gate_up (layer 0)": (269.4, 268.1, 67.1),
    "T2b gate_sp h64": (248.0, 208.5, 4.4),
    "T3a' full fused attn": (229.7, 216.5, 23.6),
    "dense_down (layer 0)": (133.8, 132.5, 33.6),
    "T2b' gate_sp h48": (80.2, 67.0, 1.1),
}


# The two layout epochs. `census` is the representation the r94 ledger priced:
# stock group-16 NVFP4 scale planes, stock (non lane-major) attention banks, and
# a codes-only lmhead estimate. `head` is what the frontier actually dispatches:
# halved group-32 planes (#72), the pairwise lane-major attention scale bank, and
# the fused-refinement lmhead nibble plane.
CENSUS_EPOCH = dict(
    routed_scale_group=16,
    shared_scale_group=16,
    lmhead_mb=128.5,
    attn_lane_major=False,
)
HEAD_EPOCH = dict(
    routed_scale_group=32,
    shared_scale_group=32,
    lmhead_mb=109.182976,
    attn_lane_major=True,
)


def family_bytes(**epoch):
    return {name: (byts, calls) for name, byts, calls in families(**epoch)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="weights")
    ap.add_argument("--tsv", default=None)
    ap.add_argument(
        "--ceiling-measured",
        type=float,
        default=266.80,
        help="GB/s; best measured streaming read ceiling on this host",
    )
    ap.add_argument(
        "--ceiling-seq",
        type=float,
        default=262.98,
        help="GB/s; grid-stride streaming ceiling on this host",
    )
    ap.add_argument("--ceiling-theoretical", type=float, default=273.0)
    args = ap.parse_args()

    wp = pathlib.Path(args.weights)
    if wp.is_dir():
        tensors = read_safetensors_headers(wp)
        total, by_dtype = checkpoint_summary(tensors)
        print(f"# checkpoint: {len(tensors)} tensors, {total} bytes")
        for d in sorted(by_dtype):
            print(f"#   {d}: {by_dtype[d]} B")
    else:
        print(f"# checkpoint: {wp} absent, skipping ground-truth cross-check")

    census = family_bytes(**CENSUS_EPOCH)
    head = family_bytes(**HEAD_EPOCH)
    print(f"# census epoch: {CENSUS_EPOCH}")
    print(f"# head epoch:   {HEAD_EPOCH}")
    print(
        "\t".join(
            [
                "family",
                "calls",
                "census_MB",
                "r94_MB",
                "repro_d%",
                "head_MB",
                "epoch_d%",
                "us_split1",
                "us_nat",
                "head_GBs_split1",
                "pct_meas_split1",
                "pct_meas_nat",
                "verdict_split1",
            ]
        )
    )
    tot = {"census": 0, "head": 0}
    tot_s1 = tot_nat = 0.0
    for name, _b, calls in families(**HEAD_EPOCH):
        s1, nat, r94mb = R94[name]
        cmb = census[name][0] / 1e6
        hmb = head[name][0] / 1e6
        repro = (cmb - r94mb) / r94mb * 100
        epoch_d = (hmb - cmb) / cmb * 100
        g1 = head[name][0] / (s1 * 1e-6) / 1e9
        gn = head[name][0] / (nat * 1e-6) / 1e9
        p1 = g1 / args.ceiling_measured * 100
        pn = gn / args.ceiling_measured * 100
        verdict = (
            "IMPOSSIBLE"
            if p1 > 100.0
            else ("bytes-bound" if p1 >= 70 else ("mid" if p1 >= 40 else "latency"))
        )
        tot["census"] += census[name][0]
        tot["head"] += head[name][0]
        tot_s1 += s1
        tot_nat += nat
        print(
            f"{name}\t{calls}\t{cmb:.1f}\t{r94mb:.1f}\t{repro:+.2f}\t{hmb:.1f}\t"
            f"{epoch_d:+.2f}\t{s1:.1f}\t{nat:.1f}\t{g1:.1f}\t{p1:.1f}\t{pn:.1f}\t{verdict}"
        )
    for epoch in ("census", "head"):
        for base, us in (("split1", tot_s1), ("nat", tot_nat)):
            gbs = tot[epoch] / (us * 1e-6) / 1e9
            print(
                f"# {epoch}-epoch bytes over {base} time: {tot[epoch]/1e6:.1f} MB/step "
                f"/ {us:.1f} us/step -> {gbs:.1f} GB/s "
                f"({gbs/args.ceiling_measured*100:.1f}% of measured ceiling)"
            )

    if args.tsv:
        with open(args.tsv, "w") as fh:
            fh.write(
                "family\tcalls\tcensus_bytes\thead_bytes\tr94_MB\tus_split1\tus_nat\n"
            )
            for name, _b, calls in families(**HEAD_EPOCH):
                s1, nat, r94mb = R94[name]
                fh.write(
                    f"{name}\t{calls}\t{census[name][0]}\t{head[name][0]}\t"
                    f"{r94mb}\t{s1}\t{nat}\n"
                )
        print(f"# wrote {args.tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
