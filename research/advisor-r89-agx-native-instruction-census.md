# R89 advisor probe — offline native-AGX instruction census for the ranked M5 target

Author: advisor (meridian). Host: advisor Apple M4 Pro, `applegpu_g16s`,
macOS SDK 26.5, Metal toolchain v17.6.109.0. All commands below were executed
and their outputs are reproduced verbatim. No GPU work, no benchmark lock, no
model checkpoint required.

## 1. Headline

`xcrun applegpu-nt` is an **offline, cross-target AIR → native-AGX compiler**.
It turns a `.metallib` into a real Apple GPU Mach-O executable **for an
architecture the host does not have**, including the `g17*` family that the
ranked M5 Max belongs to.

That gives us, for the first time, a number computed *for the ranked host's
architecture* from an M4 dev box:

```
instructions ≈ (__compute section bytes − floor) / 8
```

The 8 B/instruction constant is exact (§3). This is an **instruction-count**
instrument, not a cycle or time instrument (§6).

## 2. The verified recipe

```bash
# 0. one-time: confirm the driver and its target list
xcrun applegpu-nt -archs          # applegpu_g13*/g14*/g15*/g16{g,p,s}/g17{g,p,s}/g18p

# 1. MSL -> AIR -> metallib
xcrun metal -c k.metal -o k.air
xcrun metallib k.air -o k.metallib

# 2. pipeline script — the extension MUST be .mtlp-json
printf '{ "pipelines": { "compute_pipelines": [ { "compute_function": "%s" } ] } }\n' \
    "$FN" > s_$FN.mtlp-json

# 3. offline translate for the RANKED architecture
xcrun applegpu-nt -arch applegpu_g17s \
    -platform_version macos 26.0 26.5 \
    -N s_$FN.mtlp-json k.metallib -o out_g17s.bin

# 4. read the instruction bytes
xcrun metal-size -m out_g17s.bin | grep __compute      # -> "Section __compute: N"
xcrun metal-readobj --file-headers out_g17s.bin        # -> Arch: agx3, CpuSubtype
```

Three non-obvious requirements, each of which cost a failed run:

- **`-platform_version macos 26.0 26.5` is mandatory.** Without it the driver
  rejects the input: `image AIR version (2.8) is bigger than the one of the
  target (2.5)`. Recompiling the MSL at `-std=metal3.1
  -mmacosx-version-min=14.0` lowers AIR to 2.6 and still fails; the flag is the
  fix, not the language standard.
- **The pipeline script must be named `*.mtlp-json`.** A `.json` extension is
  routed to a flatbuffer parser and fails with `cannot load ... malformed
  flatbuffer magic`.
- **The script is a JSON object, not an array.** Schema recovered from
  `strings` on `air-nt`; other accepted keys are `pipeline_type`, `libraries`,
  `stitched_libraries`, `render_pipelines`, `tile_render_pipelines`,
  `mesh_render_pipelines`, `max_call_stack_depth`,
  `threadgroup_size_is_multiple_of_thread_execution_width`,
  `compute_function_descriptor`, `vertex_function`, `fragment_function`.

One pipeline script per function, otherwise `__compute` is the sum over all
functions in the script and the per-kernel number is lost.

### Target identification

`metal-readobj --file-headers` reports `Arch: agx3` for every g16/g17/g18
target; the discriminator is `CpuSubtype`:

| target | CpuSubtype |
|---|---|
| `applegpu_g16s` (this M4 Pro) | `0x1D3` |
| `applegpu_g17s` | `0x163` |
| `applegpu_g17p` | `0x143` |
| `applegpu_g18p` | `0x173` |

M4 Pro is `g16s`, so the `s` suffix is the Pro/Max die class; **`applegpu_g17s`
is the best M5 Max candidate.** This is an inference from the naming scheme,
not a verified fact, and every conclusion below is reported for `g16s` and
`g17s` side by side so that it does not depend on the inference.

### Route not taken

`MTLBinaryArchive` also produces a native slice: `makeBinaryArchive` →
`addComputePipelineFunctions` → `serialize(to:)` yields a fat file
(`metal-lipo -info` → `air64_v28 applegpu_g16s`) that `metal-lipo -thin`
extracts. It works, but it only ever emits the **host** architecture, so it
cannot see the ranked target. `applegpu-nt` strictly dominates it. Keep the
`MTLBinaryArchive` route only for reading live-device pipeline properties
(`maxTotalThreadsPerThreadgroup`, `threadExecutionWidth`,
`staticThreadgroupMemoryLength`), which the offline route does not provide.

### What is NOT available

`metal-dis` does not exist. `metal-objdump -d` on a `.metallib` prints **AIR /
LLVM IR only**. On a native binary it fails with `no instruction printer for
target agx3---macho` (and `no disassembler for target agx1`). Apple ships the
AGX target definitions but strips the instruction printer.

**So we have no disassembler.** We have a byte counter. §3 shows that is
enough for the question we actually need answered.

`metal-binary-perf` is a section *load-timing* tool (`--module-load`,
`--reflection-load`, `--script-load`), not a static analyser. Dead end.

## 3. Calibration — the byte metric is exactly linear

Floor kernel `c_copy` (`out[tid] = in[tid]`): **1520 B** on g16s, **1504 B** on
g17s. Dependent-FMA chains, identical on both targets:

| kernel | `__compute` B | FMAs | Δ vs `c_fma2` | instructions added |
|---|---|---|---|---|
| `c_fma1` | 1520 | 1 | | |
| `c_fma2` | 1536 | 2 | 0 | 0 |
| `c_fma4` | 1552 | 4 | +16 | 2 |
| `c_fma8` | 1584 | 8 | +48 | 6 |
| `c_fma16` | 1648 | 16 | +112 | 14 |
| `c_fma32` | 1776 | 32 | +240 | 30 |

**240 B / 30 instructions = 8.000 B per instruction, exact over a 16× range,
on both g16s and g17s.**

Sections are 16 B aligned, so the readout quantizes to **±1 instruction**. Any
delta of ≥4 instructions is unambiguous; a 1-instruction delta is not
resolvable. Lever 2's success gate ("instruction-counter drop ≥40 %" on a
prologue of tens of instructions) sits far above that floor.

A negative control confirms the compiler folds aggressively: `n_add_N`
(`s += w + i` repeated N times) reports the bare floor 1520 for N = 1, 2, 4, 8,
because the compiler collapses the whole sum algebraically. **Design probe
kernels so the work cannot be folded**, or the instrument silently reads zero.

## 4. Result A — the `bfeil` dequant lever is DEAD

Queue item 5 proposed forcing the AGX `bfeil` fused bitfield-extract
instruction in the NVFP4 dequant path, priced at ~2.2× on the extraction ALU
from published G15/G16 cycle tables (`(w >> s) & 0xF` ≈ 8.95 cy versus one
`bfeil` ≈ 4.0 cy). The premise was that Apple's compiler emits a separate
shift and a separate mask.

**It does not.** Two independent measurements:

**(a) All three MSL spellings produce byte-identical native code.** Eight
independent nibble extractions summed:

| spelling | g16s | g17s |
|---|---|---|
| `(w >> s) & 0xF` | 1696 | 1712 |
| `extract_bits(w, s, 4)` | 1696 | 1712 |
| `(w & mask) >> s` | 1696 | 1712 |

All three canonicalize to the same instruction sequence. **There is no
alternative spelling to reach for**, so there is no lever, independent of what
the sequence is.

**(b) The mask is nearly free.** Same 8-way structure, with and without the
mask:

| kernel | g16s | instructions above floor |
|---|---|---|
| `d_shiftonly_8` — 8 × `s += (w >> 4i)` | 1664 | 18 |
| `n_sm_8` — 8 × `s += (w >> 4i) & 0xF` | 1680 | 20 |

Adding eight masks costs **+2 instructions, not +8**. If the shift and the
mask were separate instructions we would see 1664 → 1728. The compiler is
already emitting a fused extract for ~6 of the 8 sites.

**Verdict: queue item 5 is retired before it consumed a student-round.** The
honest residual caveat is that this instrument counts instructions, not
cycles, so a fused extract could still be a slow instruction — but since all
three source spellings compile identically there is no action available
either way.

Also measured and identical in behaviour: `insert_bits(...)` (`d_insert_8`,
1680 / 1696) offers nothing over the plain idiom.

## 5. Result B — instruction-count deltas are architecture-invariant

This is the more important finding for programme strategy.

Per-operation **slopes** are identical on g16s and g17s:

| ladder | g16s slope | g17s slope |
|---|---|---|
| dependent FMA, `c_fma4`→`c_fma32` | 8 B / FMA | 8 B / FMA |
| nibble extraction, `n_sm_4`→`n_sm_8` | 24 B / nibble | 24 B / nibble |

What differs between the two targets is a **fixed per-kernel offset**
(prologue/ABI): the floor itself moves 1520 → 1504, and integer kernels sit
about +4 instructions higher on g17s relative to their own floor. Since the
slopes match, that offset cancels in any A/B difference.

**Consequence: an instruction-count delta measured on our M4 dev host
transfers 1:1 to the ranked M5 target for these operation classes, even though
*time* famously does not** (PR #137: −63.7 µs/token M4 → +24.6 µs/token M5,
transfer factor −0.40 ± 0.24). This is the first instrument in the programme
that produces a ranked-host-valid number without an M5.

**One measured exception**, and it is instructive. A constant-buffer lookup
form is the only kernel where g17s is *cheaper*:

| kernel (8 codes → float) | g16s (above floor) | g17s (above floor) | Δ |
|---|---|---|---|
| `d_nib_tofloat_8` — ALU reconstruct | 192 B (24 instr) | 224 B (28 instr) | +4 |
| `d_nib_lut_8` — `constant float *lut` indexed | 320 B (40 instr) | 304 B (38 instr) | **−2** |
| `n_nvfp4_8` — sign/magnitude reconstruct | 304 B (38 instr) | 352 B (44 instr) | +6 |

The ALU-versus-LUT gap narrows from **16 instructions on g16s to 10 on g17s**.
LUT still loses on both, so this is not yet a lever, but it flags that
**memory-touching and constant-indexed code is exactly where the
architecture-invariance assumption breaks.** Any census of a kernel that
indexes `constant` or threadgroup memory must be run for `g17s`, not just
`g16s`.

## 5b. Result C — register count is NOT in the object metadata

Delegated probe (`/tmp/agxdesc`), five kernels with identical signatures
differing only in the number of simultaneously-live values loaded from `in[]`
before a single combining sum, all translated to `applegpu_g16s`:

| kernel | `__compute` | above floor | instr | `__descriptor` | `__reflection` |
|---|---|---|---|---|---|
| `reg_02` | 1536 | 16 | 2 | 96 | 368 |
| `reg_08` | 1584 | 64 | 8 | 96 | 368 |
| `reg_16` | 1664 | 144 | 18 | 96 | 368 |
| `reg_32` | 1840 | 320 | 40 | 96 | 368 |
| `reg_64` | 2160 | 640 | 80 | 96 | 368 |

A byte-by-byte diff of the 96-byte `__descriptor` across all five finds
**exactly two differing offsets, 80 and 81**, whose values ASCII-decode to
`02`/`08`/`16`/`32`/`64` — the numeric suffix of the kernel *name string*
embedded verbatim. `__reflection` shows the same two bytes at its offsets
352/353. Every structural byte (AIRP header, offsets, table sizes, buffer
binding metadata) is byte-identical from 2 to 64 live values.

⇒ **Register allocation is not recorded in `__descriptor` or `__reflection`.**
Occupancy still has to come from live-device
`MTLComputePipelineState.maxTotalThreadsPerThreadgroup` against the
`agx_performance.c` occupancy table. This is the reason #469 and #475 both
mandate recording that property.

**Useful side-signal:** instructions per live value are `1.00, 1.00, 1.13,
1.25, 1.25` across the ladder. The census is therefore a *weak* spill proxy —
a code change that pushes a kernel over a register cliff pays for it in
`__compute` bytes — but the growth is gradual, not a cliff, so do not use it
as an occupancy oracle.

## 6. Honest limits of the instrument

1. **Count, not cycles.** The AGX cycle table is wildly non-uniform
   (`RSHIFT32` 7.89 cy, `bitop` 1.06 cy, `FFMA32` 1.0 cy). A −40 %
   instruction-count result is *necessary but not sufficient* for a speedup.
   It remains a hard, cheap, pre-GPU gate that can kill a lever before it
   costs a benchmark slot.
2. **Blind to scheduling.** Instruction *order* — the whole subject of rule 41
   and of #475's barrier hoist — does not change the count. This instrument
   cannot answer #475's A4 question.
3. **±1 instruction** from 16 B section alignment.
4. **No register counts** anywhere in the object metadata — measured, §5b, not
   assumed. Occupancy still has to come from live-device
   `maxTotalThreadsPerThreadgroup` against the `agx_performance.c` table.
5. **`g17s = M5 Max` is an inference** from the `g16s = M4 Pro` naming.
   Report both targets always.
6. **Folding hazard.** See the `n_add_N` control in §3.

## 7. The bridge to real Laguna kernels

The repo already contains most of the extractor. `research/nax_msl_compile_check.sh`
reproduces MLX's JIT concatenation order out of `Vendor/mlx-swift/.../mlx-generated/*.cpp`,
writes a standalone `unit.metal`, and with `EMIT_LIB=1` links a `.metallib` —
which is precisely the input `applegpu-nt` consumes. For the `_nax` family the
chain is therefore three added commands.

For kernels whose MSL is generated by Swift string functions in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (the router tournament, the
residual-RMSNorm-router fusion, the fused QKV path) a second extractor is
needed, because `MLXFast.metalKernel(name:inputNames:outputNames:source:header:)`
wraps the body in a generated `[[kernel]]` signature derived from
`inputNames`/`outputNames`. Reproducing that wrapper is the one genuinely new
piece of engineering, and it is the bounded core of the capability assignment.

## 8. Artifacts

Probe sources and binaries under `/tmp/agxprobe` on the advisor host
(`cal.metal`, `nib.metal`, `disc.metal`, `k.metal`, per-function
`*.mtlp-json`, `*_g16s.bin`, `*_g17s.bin`). These are scratch, not committed:
every number above is reproducible from §2 and the kernel bodies described in
§3–§5.
