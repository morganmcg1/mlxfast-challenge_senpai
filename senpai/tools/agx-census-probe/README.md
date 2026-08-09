# agx-census-probe

Offline native-AGX instruction census. Research only — nothing here is
submitted, and nothing here touches an editable path or a GPU.

`applegpu-nt` translates a `.metallib` to a native AGX binary for a chosen
target architecture. `metal-size` then reports that binary's `__compute`
section size. Because the translation is offline, an `applegpu_g17s` (M5-class
Pro/Max) count is obtainable from an M4 host, which is the only ranked-host-valid
instrument this programme has without owning an M5.

Full findings, caveats and gate verdicts: `research/maple-frieren-r90-agx-instruction-census.md`.

## Contents

| file | purpose |
|---|---|
| `census.sh` | driver: `.metal` → `.air` → `.metallib` → native binary → `__compute` bytes, per entry point, per arch |
| `cal.metal` | calibration and the loop-rolling detector |
| `encoding.metal` | instruction-encoding length per source-level op, by opcode class |
| `gen_router_metal.sh` | S3 extractor: reconstructs the MLX-generated translation unit for the scored decode router from committed sources only |
| `router_arms.metal` | S4-a arms for Lever 2 (router-tournament instruction diet); fragment, needs the preamble and header prepended |
| `run_s4a.sh` | runs `gen_router_metal.sh`, assembles `router_arms.metal` into a full translation unit, and censuses both |
| `nvfp4.metal` | S4-b arms: NVFP4 code→float reconstruction at real kernel scale |

## Usage

```bash
bash senpai/tools/agx-census-probe/census.sh senpai/tools/agx-census-probe/nvfp4.metal
bash senpai/tools/agx-census-probe/run_s4a.sh
```

Env overrides: `MTL_STD` (default `-std=metal4.0`), `MTL_FASTMATH` (default
`-fno-fast-math`), `AGX_ARCHS` (default `applegpu_g16s applegpu_g17s`).

The defaults match what MLX's JIT actually uses — `Device::build_library_`
(`backend/metal/device.cpp:622-651`) sets `setFastMathEnabled(false)` and
`get_metal_version()` returns `MTL::LanguageVersion4_0` on macOS ≥ 26. Absolute
byte counts move when the flags move, so never compare arms across flag sets.

## Reading a result

1. **Always pair an arm with a matched null** that has the identical signature
   and keeps the same arguments live. The floor is signature-dependent, and a
   dead-stripped arm can land below the nominal empty-kernel floor.
2. **`__compute` is static code size, not dynamic instruction count.** If the
   compiler rolls a loop, deleting iterations moves the trip count and not the
   byte count. `cal.metal`'s `k_fma480` and `router_arms.metal`'s `r_cmp*`
   ladder both demonstrate this; `#pragma clang loop unroll(full)` does **not**
   reliably repair it.
3. **Do not divide by 8.** Measured encoding length ranges from 4.0 B/op for a
   register-register float add to 14.0 B/op for an integer multiply-add. Compare
   bytes between arms of similar opcode mix, or price a primitive directly with
   an explicitly unrolled ladder.
4. **Report both architectures.** Float slopes agree, but integer and
   memory-touching slopes do not.
