#!/usr/bin/env python3
"""Join the SPLIT=1 per-kernel profile table with the analytic byte model.

Usage:
    python3 research/nezuko_family_table.py <split1-sweep-log> [arm]

The SPLIT=1 sweep prints one `us/step share n/step us/call kernel` block per
arm. This reducer takes the first block (or the block after `arm=<arm>`),
subtracts the measured per-command-buffer floor from us/call, and reports the
achieved read bandwidth against a 260.2 GB/s reference ceiling.

MB/call is analytic: quantized weight bytes plus activation and cache traffic
derived from the checkpoint shapes, so it is host-independent. The two
attention families read a growing or windowed KV region; `u` is the unique
footprint and `i` the issued (redundantly fetched) bytes, so both bounds are
printed and neither should be ranked without a separate check.
"""
import re
import sys

CB_FLOOR_US = 1.33  # SPLIT=1 command-buffer submit/complete floor, r1 measured
CEIL_GB_S = 260.2   # M5 reference read ceiling used by the advisor's roofline

MB_PER_CALL = {
    "decode_nvfp4_qkv_h64": 11.80,
    "decode_nvfp4_qkv_h48": 9.44,
    "routed_nvfp4_swiglu_qmv_packed_top8keys": 9.442,
    "oproj_act_h64": 9.45,
    "oproj_act_h48": 7.09,
    "routed_shared_nvfp4_down_residual": 5.311,
    "shared_nvfp4_swiglu_qmv_rows1": 1.184,
    "residual_rms_router": 1.062,
    "gate_sp_h64": 0.033,
    "gate_sp_h48": 0.033,
    "decode_router_top8_ordinal": 0.004,
    "lmhead_int5_base_coarse_delta": 134.9,
    "lmhead_coarse_argmax_stage1": 0.5,
    "lmhead_exact_winner": 0.5,
    "lmhead_exact_fused_int5_sparse_refine": 0.5,
    "lmhead_exact_inline_mask_block": 0.5,
}
MB_RANGE = {  # families whose unique and issued byte counts differ
    "sliding_fused_attn_ring": (2.097, 8.389),
    "full_fused_attn_grow": (2.621, 10.484),
}

ROW = re.compile(r"^\s*([0-9]+\.[0-9])\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s+(\S.*)$")


def bytes_for(name):
    for key, mb in MB_PER_CALL.items():
        if key in name:
            return mb, mb
    for key, (lo, hi) in MB_RANGE.items():
        if key in name:
            return lo, hi
    return None, None


def main():
    path = sys.argv[1]
    want = sys.argv[2] if len(sys.argv) > 2 else None
    rows, active, seen_header = [], want is None, False
    for line in open(path, errors="replace"):
        if line.startswith("================"):
            active = want is None or f"arm={want} " in line
            if rows:
                break
            seen_header = False
            continue
        if not active:
            continue
        if "us/call" in line:
            seen_header = True
            continue
        m = ROW.match(line)
        if seen_header and m:
            us_step, share, n_step, us_call, kernel = m.groups()
            rows.append((float(us_step), float(n_step), float(us_call), kernel.strip()))

    print("| kernel | n/step | us/call | us/step | body us | MB/call | GB/s | % ceil |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    tot_us = tot_mb_lo = tot_mb_hi = 0.0
    for us_step, n_step, us_call, kernel in rows:
        body = us_call - CB_FLOOR_US
        lo, hi = bytes_for(kernel)
        tot_us += us_step
        if lo is None:
            print(f"| {kernel} | {n_step:.2f} | {us_call:.2f} | {us_step:.1f} "
                  f"| {body:.2f} | ? | ? | ? |")
            continue
        tot_mb_lo += lo * n_step
        tot_mb_hi += hi * n_step
        gb_lo, gb_hi = lo / body * 1e3, hi / body * 1e3
        mb = f"{lo:.3f}" if lo == hi else f"{lo:.3f}u/{hi:.3f}i"
        gb = f"{gb_lo:.0f}" if lo == hi else f"{gb_lo:.0f}/{gb_hi:.0f}"
        pc = (f"{gb_lo / CEIL_GB_S * 100:.0f}%" if lo == hi else
              f"{gb_lo / CEIL_GB_S * 100:.0f}/{gb_hi / CEIL_GB_S * 100:.0f}%")
        print(f"| {kernel} | {n_step:.2f} | {us_call:.2f} | {us_step:.1f} "
              f"| {body:.2f} | {mb} | {gb} | {pc} |")
    print(f"\ntotals: {tot_us:.0f} us/step attributed, "
          f"{tot_mb_lo:.0f}-{tot_mb_hi:.0f} MB/step modelled "
          f"({tot_mb_lo / CEIL_GB_S * 1e3:.0f}-{tot_mb_hi / CEIL_GB_S * 1e3:.0f} us "
          f"at {CEIL_GB_S} GB/s)")


if __name__ == "__main__":
    main()
