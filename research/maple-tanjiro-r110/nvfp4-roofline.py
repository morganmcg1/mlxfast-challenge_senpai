#!/usr/bin/env python3
"""Static byte accounting for the NVFP4 QMV family, and its roofline position.

Everything here is read out of the scored checkpoint's safetensors headers, not
assumed: `weights/model-*.safetensors` already hold the NVFP4 representation, so
the packed-code and scale tensors give exact bytes per decode step.

Pairs with nibble-split-verdict.md 6.1.  The point is to answer, independently
of any wall-clock A/B, whether the family has room to go faster at all -- ALU
reduction can only matter in a kernel that is not already at the memory
roofline.

    research/maple-tanjiro-r110/nvfp4-roofline.py [weights_dir]
"""
import json
import struct
import sys
from glob import glob
from pathlib import Path

# SPLIT=1 per-kernel census, 200 steps, this M4 Pro.  Face value: the hook's
# +19.6 % wall inflation is command-buffer overhead that lands mostly in the
# gaps between dispatches, so using these unadjusted UNDERSTATES achieved GB/s.
CENSUS_US = {
    "routed gate+up": 1502.1,   # routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2
    "routed+shared down": 862.0,  # routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6
    "shared gate+up": 288.7,    # laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1
}
M4_PRO_PEAK_GBS = 273.0  # Mac16,11 LPDDR5X-8533, 256-bit


def headers(wdir):
    out = {}
    for f in sorted(glob(str(Path(wdir) / "*.safetensors"))):
        with open(f, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            h = json.loads(fh.read(n))
        for k, v in h.items():
            if k != "__metadata__":
                out[k] = v
    return out


def nbytes(spec):
    w = {"F32": 4, "BF16": 2, "F16": 2, "U8": 1, "I8": 1, "U32": 4, "I32": 4}
    n = 1
    for d in spec["shape"]:
        n *= d
    return n * w[spec["dtype"]]


def main():
    wdir = sys.argv[1] if len(sys.argv) > 1 else "weights"
    h = headers(wdir)
    cfg = json.loads((Path(wdir) / "config.json").read_text())
    topk, n_exp = cfg["num_experts_per_tok"], cfg["num_experts"]
    moe = sorted({int(k.split(".")[2]) for k in h if ".mlp.switch_mlp." in k})
    L = len(moe)
    ref = moe[0]
    print(f"{cfg['num_hidden_layers']} layers, {L} MoE "
          f"(dense: {sorted(set(range(cfg['num_hidden_layers'])) - set(moe))}), "
          f"top-{topk} of {n_exp}")

    def per_expert(kind, proj):
        w = h[f"model.layers.{ref}.mlp.{kind}.{proj}.weight"]
        s = h[f"model.layers.{ref}.mlp.{kind}.{proj}.scales"]
        # switch_mlp tensors carry a leading expert axis; price ONE expert.
        div = n_exp if kind == "switch_mlp" else 1
        return nbytes(w) // div, nbytes(s) // div

    wb, sb = per_expert("switch_mlp", "gate_proj")
    codes = wb * 2  # 4-bit codes: two per byte
    group = codes // sb
    print(f"NVFP4: {wb} code bytes + {sb} scale bytes per expert gate_proj "
          f"=> group size {group}, {8 * wb / codes:.1f} bit/code, "
          f"{(wb + sb) / codes:.4f} byte/weight all-in")

    fam = {
        "routed gate+up": topk * sum(sum(per_expert("switch_mlp", p))
                                     for p in ("gate_proj", "up_proj")),
        "routed+shared down": (topk * sum(per_expert("switch_mlp", "down_proj"))
                               + sum(per_expert("shared_expert", "down_proj"))),
        "shared gate+up": sum(sum(per_expert("shared_expert", p))
                              for p in ("gate_proj", "up_proj")),
    }

    print(f"\n{'MB/step':>9} {'us/step':>9} {'GB/s':>8} {'% peak':>7}  kernel group")
    tb = tt = 0
    for k, per_layer in fam.items():
        mb = per_layer * L / 1e6
        us = CENSUS_US[k]
        gbs = mb / us * 1e3
        tb += mb
        tt += us
        print(f"{mb:9.1f} {us:9.1f} {gbs:8.1f} {gbs / M4_PRO_PEAK_GBS * 100:6.1f}%  {k}")
    print(f"{tb:9.1f} {tt:9.1f} {tb / tt * 1e3:8.1f} "
          f"{tb / tt * 1e3 / M4_PRO_PEAK_GBS * 100:6.1f}%  FAMILY")

    sib = max(fam, key=lambda k: fam[k] * L / CENSUS_US[k])
    sib_gbs = fam[sib] * L / 1e6 / CENSUS_US[sib] * 1e3
    lag = "shared gate+up"
    ideal = fam[lag] * L / 1e6 / sib_gbs * 1e3
    gain = CENSUS_US[lag] - ideal
    print(f"\nif '{lag}' reached its sibling's {sib_gbs:.1f} GB/s it would take "
          f"{ideal:.1f} us/step instead of {CENSUS_US[lag]:.1f} "
          f"=> {gain:.1f} us/step on this M4 "
          f"= {0.75 * 1.06 * gain * 0.4367 / 8972 * 100:.3f} % of score "
          f"(bar 0.27 %)")


if __name__ == "__main__":
    main()
