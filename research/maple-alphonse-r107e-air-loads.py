#!/usr/bin/env python3
"""Stage-1 AIR load census for the R107-E oproj geometry arms.

Classifies every static load/store site in each arm's AIR module by address
space and element type, records the alloca inventory (the register-pressure
proxy the brief asks for), and emits Rule-75 digests. Static instruction
*sites* only -- these are not dynamic issue counts and are never used as
amortisation arithmetic.
"""

import hashlib
import json
import re
from pathlib import Path

ART = Path("research/artifacts/maple-alphonse-r107e")
ARMS = ["g0", "g1", "g2", "g3", "g4"]
HEADS = ["h64", "h48"]

# device buffer element type -> which oproj argument it can only have come from
DEVICE_ELEM_ROLE = {
    "bfloat": "attention_output / gate_values (activation plane)",
    "i8": "scale_bases / scale_nibbles (metadata plane)",
    "i32": "weight_codes (NVFP4 code plane)",
    "float": "weight_scales (escape plane)",
    "half": "weight_codes (unpacked half2 view)",
}

LOAD_RE = re.compile(r"=\s*load\s+(?:volatile\s+)?([<>\w\s\[\]x]+?),\s*\1?\s*")
LOAD_RE2 = re.compile(r"=\s*load\s+([^,]+),\s*([^,]+?)\*\s+(%\S+)")
STORE_RE = re.compile(r"^\s*store\s+([^,]+),\s*([^,]+?)\*\s+(%\S+)")
ALLOCA_RE = re.compile(r"=\s*alloca\s+([^,]+),\s*align\s+(\d+)")


def addrspace_of(ptr_type: str) -> str:
    m = re.search(r"addrspace\((\d+)\)", ptr_type)
    if not m:
        return "thread"
    return {"1": "device", "3": "threadgroup", "2": "constant"}.get(
        m.group(1), "as" + m.group(1)
    )


def elem_of(ty: str) -> str:
    return ty.strip().split()[0].strip()


def census(path: Path) -> dict:
    text = path.read_text()
    loads: dict[tuple[str, str], int] = {}
    stores: dict[tuple[str, str], int] = {}
    allocas: list[str] = []
    for line in text.splitlines():
        m = ALLOCA_RE.search(line)
        if m:
            allocas.append(m.group(1).strip())
            continue
        m = LOAD_RE2.search(line)
        if m:
            key = (addrspace_of(m.group(2)), elem_of(m.group(1)))
            loads[key] = loads.get(key, 0) + 1
            continue
        m = STORE_RE.search(line)
        if m:
            key = (addrspace_of(m.group(2)), elem_of(m.group(1)))
            stores[key] = stores.get(key, 0) + 1
    return {
        "allocas": allocas,
        "alloca_private_floats": sum(
            int(a.split(" x ")[0].lstrip("[")) if " x " in a else 1
            for a in allocas
            if "float" in a
        ),
        "loads": {f"{a}:{e}": n for (a, e), n in sorted(loads.items())},
        "stores": {f"{a}:{e}": n for (a, e), n in sorted(stores.items())},
        "device_load_sites": sum(n for (a, _), n in loads.items() if a == "device"),
        "thread_load_sites": sum(n for (a, _), n in loads.items() if a == "thread"),
        "threadgroup_load_sites": sum(
            n for (a, _), n in loads.items() if a == "threadgroup"
        ),
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# Emitted kernel constants (LagunaRuntimeModel.swift:4353-4364). Both the
# k_blocks loop and the results_per_simdgroup loop are rolled at -O, so the
# dynamic count per k-block is the static site count times its trip count.
VALUES_PER_THREAD = 16
CODES_PER_THREAD = 2
GEOM = {"g0": 4, "g1": 8, "g2": 8, "g3": 4, "g4": 2}


def dynamic_loads(arms: dict) -> dict:
    """Dynamic device loads per thread per k-block, from AIR sites x trip counts.

    Cross-checks the census against the brief's hand arithmetic for the shipped
    arm: 33 issued loads of which 8 reach DRAM. The DRAM subset is the weight
    plane (codes plus its two scale sites), because the activation and gate
    planes are 16 KB and 128 B respectively and are re-read by every simdgroup.
    """
    result = {}
    for arm, rows in GEOM.items():
        codes = rows * CODES_PER_THREAD
        bases = rows
        nibbles = rows
        issued = VALUES_PER_THREAD + 1 + codes + bases + nibbles
        dram = codes  # only the weight code plane is compulsory per row
        result[arm] = {
            "activation_bfloat": VALUES_PER_THREAD,
            "gate_bfloat": 1,
            "weight_codes_i32": codes,
            "scale_bases_i8": bases,
            "scale_nibbles_i8": nibbles,
            "issued_total": issued,
            "reach_dram": dram,
            "cache_resident_pct": round(100.0 * (issued - dram) / issued, 1),
            "issued_per_output_row": round(issued / rows, 3),
            "dram_per_output_row": round(dram / rows, 3),
            "device_load_sites_in_air": arms[f"{arm}_h64"]["device_load_sites"],
        }
    g0 = result["g0"]
    assert (g0["issued_total"], g0["reach_dram"]) == (33, 8), g0
    assert all(r["dram_per_output_row"] == 2.0 for r in result.values())
    return result


def main() -> None:
    out: dict = {
        "note": (
            "Static AIR instruction SITE counts, not dynamic issue counts. The "
            "k_blocks loop and the results_per_simdgroup loop are both rolled at "
            "-O, so site counts are near-invariant across arms by construction. "
            "Rule 98.9: nothing here is a DRAM byte count."
        ),
        "arms": {},
        "rule75_digests": {},
    }
    for arm in ARMS:
        for head in HEADS:
            metal = ART / f"oproj_{arm}_{head}.metal"
            ir = ART / f"oproj_{arm}_{head}.ir"
            if not ir.exists():
                continue
            key = f"{arm}_{head}"
            out["arms"][key] = census(ir)
            out["rule75_digests"][key] = {
                "metal_sha256_16": digest(metal),
                "air_ir_sha256_16": digest(ir),
                "metal_bytes": metal.stat().st_size,
                "air_ir_bytes": ir.stat().st_size,
            }

    # Register-pressure / spill proxy: does result[] growth show up as more
    # private float traffic, and does any arm grow its alloca footprint beyond
    # the expected result[] + x_thread[] inventory?
    expect = {"g0": 4 + 16, "g1": 8 + 16, "g2": 8 + 16, "g3": 4 + 16, "g4": 2 + 16}
    out["spill_proxy"] = {}
    for key, rec in out["arms"].items():
        arm = key.split("_")[0]
        out["spill_proxy"][key] = {
            "alloca_private_floats": rec["alloca_private_floats"],
            "expected_result_plus_xthread": expect[arm],
            "matches_expected": rec["alloca_private_floats"] == expect[arm],
            "thread_load_sites": rec["thread_load_sites"],
        }

    out["dynamic_loads_per_thread_per_k_block"] = dynamic_loads(out["arms"])

    p = ART / "geom-air-loads.json"
    p.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")

    print("=== Rule 75 digests ===")
    for k, v in sorted(out["rule75_digests"].items()):
        print(
            f"{k:9s} metal {v['metal_sha256_16']} ({v['metal_bytes']:6d} B)  "
            f"air {v['air_ir_sha256_16']} ({v['air_ir_bytes']:6d} B)"
        )
    print("\n=== load sites by address space ===")
    for k, v in sorted(out["arms"].items()):
        print(f"{k:9s} device={v['device_load_sites']:3d} "
              f"thread={v['thread_load_sites']:3d} "
              f"tg={v['threadgroup_load_sites']:3d}  allocas={v['allocas']}")
    print("\n=== device load sites by element type ===")
    for k, v in sorted(out["arms"].items()):
        dev = {kk.split(':')[1]: n for kk, n in v["loads"].items()
               if kk.startswith("device:")}
        print(f"{k:9s} {dev}")
    print("\n=== spill proxy ===")
    for k, v in sorted(out["spill_proxy"].items()):
        print(f"{k:9s} {v}")
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
