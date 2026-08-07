#!/usr/bin/env python3
"""Research-only (PR #158): rank decode kernels by exposed serial time.

The SPLIT=1 arm times every dispatch in its own command buffer, so its
`us/call` column is inflated by the per-command-buffer GPU cost that the
shipped ~9-dispatch batching amortises. That inflation is measurable rather
than assumed: SPLIT=1 reports gpu_busy_sum = 8583 us/step over 406 dispatches
while SPLIT=0 reports 8001-8013 us/step over the same 406 dispatches, so the
per-dispatch inflation is (8583 - 8007) / 406 us.

Subtracting it reconstructs the shipped per-call cost. The corrected total
returning to the SPLIT=0 busy sum is arithmetic, not evidence; it only checks
that the per-kernel n/step column sums to 406. The real cross-check is the
floor: the marginal cost of an added dispatch in the unfuse sweep (1.9 us)
must agree with the absolute cost of the step's cheapest dispatches, which is
an independent quantity.

Usage: python3 research/nezuko_pr158_exposed_time.py
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(REPO, "research/nezuko-pr158-split1-kernels.txt")

SPLIT0_BUSY_US = 8007.0  # mean of the two SPLIT=0 replicates, 8013 and 8001
DISPATCHES = 406.0

# Smallest marginal GPU cost per dispatch observed when a fused kernel is
# ablated into a longer chain computing the same result (unfuse sweep):
#   rsdr +39 dispatches / +73 us, ssq +195 / +373, rsq +195 / +473.
FLOOR_US = 1.9


def short(name):
    name = re.sub(r"^custom_kernel_laguna_", "", name)
    name = re.sub(r"_(bfloat16_t|uint\d+_t|uint8_t|float|c_float|tc_float).*$", "", name)
    return name[:52]


def main():
    rows = []
    with open(TABLE) as fh:
        header = fh.readline()
        busy_split1 = float(re.search(r"gpu_busy_sum=([\d.]+)", header).group(1))
        fh.readline()
        for line in fh:
            f = line.split()
            if len(f) < 7:
                continue
            rows.append(
                {
                    "us_step": float(f[0]),
                    "n": float(f[2]),
                    "us_call": float(f[3]),
                    "name": short(f[6]),
                }
            )

    inflation = (busy_split1 - SPLIT0_BUSY_US) / DISPATCHES
    n_total = sum(r["n"] for r in rows)
    print(f"SPLIT=1 busy_sum        {busy_split1:8.1f} us/step over {n_total:.0f} dispatches")
    print(f"SPLIT=0 busy_sum        {SPLIT0_BUSY_US:8.1f} us/step (independent measurement)")
    print(f"per-dispatch inflation  {inflation:8.3f} us/dispatch")
    print(f"per-dispatch floor      {FLOOR_US:8.3f} us/dispatch (unfuse-sweep marginal cost)")
    print()

    for r in rows:
        r["exposed_call"] = r["us_call"] - inflation
        r["exposed"] = r["exposed_call"] * r["n"]
        r["floor"] = FLOOR_US * r["n"]
        r["work"] = max(r["exposed"] - r["floor"], 0.0)

    rows.sort(key=lambda r: -r["exposed"])
    total = sum(r["exposed"] for r in rows)
    floor_total = sum(r["floor"] for r in rows)

    print(f"{'exposed':>9} {'share':>7} {'n':>5} {'us/call':>8} "
          f"{'floor':>7} {'work':>8}  kernel")
    for r in rows:
        print(f"{r['exposed']:9.1f} {r['exposed']/total*100:6.2f}% {r['n']:5.0f} "
              f"{r['exposed_call']:8.2f} {r['floor']:7.1f} {r['work']:8.1f}  {r['name']}")
    print()
    print(f"corrected total    {total:8.1f} us/step  "
          f"(target {SPLIT0_BUSY_US:.1f}, error {total - SPLIT0_BUSY_US:+.1f} us "
          f"= {(total - SPLIT0_BUSY_US)/SPLIT0_BUSY_US*100:+.2f}%)")
    print(f"per-dispatch floor {floor_total:8.1f} us/step "
          f"= {floor_total/total*100:.1f}% of GPU busy time")
    print(f"work-proportional  {total - floor_total:8.1f} us/step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
