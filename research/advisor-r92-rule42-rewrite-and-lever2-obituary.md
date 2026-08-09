# Advisor note, round 92 — Rule 42 rewritten, and the obituary for Frontier Lever 2

Base: `8486638578a283de40369172f68c3a4d2d6a5365`
Author: advisor (maple)
Supersedes: the rule-42 statement published in
`research/advisor-r89-agx-native-instruction-census.md` (commit `c6f7fa6f`).

This note does two things. It replaces a standing rule that my own calibration
got wrong, and it buries a lever family that has been on the assignable queue
for six rounds and is now shown to be almost entirely already-shipped.

---

## Part 1 — Rule 42, rewritten

### Why the old rule had to go

The old rule 42 said, in substance: *we can count real M5 instructions offline
from an M4 by compiling with `applegpu-nt -arch applegpu_g17s` and reading
`(__compute bytes − floor) / 8`.*

Two of those claims are false and one is misleading.

1. **`(bytes − floor) / 8` is retired.** It assumed a uniform 8 bytes per
   instruction. PR #481's §4 encoding table, replicated independently in
   `/tmp/advisor-r91-calib`, shows marginal bytes per operation spanning
   **4.0 to 14.0** depending on opcode class and operand form. A single divisor
   cannot be right for all of them.

2. **The old "memory-only exception" is dead.** The old rule allowed that
   architectural encoding differences might exist for memory operations but
   assumed ALU encoding was architecture-invariant. #481 measured **uint MAD at
   12.0 B/op on g16s and 14.0 B/op on g17s — a +16.7 % M5 penalty on an
   operation that touches no memory at all.** Whatever causes the difference,
   it is not addressing modes.

3. **"Count instructions" oversells it.** The instrument reads *static code
   size of the `__compute` section*. That is not an instruction count, not a
   dynamic instruction count, and not a cycle count.

### Rule 42, current form

> **Rule 42.** `xcrun applegpu-nt` compiles Metal for a chosen Apple GPU
> architecture, including `applegpu_g17s` (the inferred M5 generation), from an
> M4 host, offline, with no GPU and no checkpoint. The quantity it yields is
> **static `__compute` section code size in bytes**. It is admissible as an A/B
> comparator **only** as a matched-null difference between arms that share the
> same opcode class and the same loop structure. It is not an instruction
> count, not a cycle count, and not a performance prediction.

### Binding method constraints

Every one of these is a way the instrument has already produced a wrong answer
in this campaign. They are not stylistic.

- **Byte count is `$NF` of the `Section __compute:` line** from
  `xcrun metal-size -m`, not `$2`. (#481 §2 correction.)
- **Entry-point names come from `xcrun metal-objdump --syms FUNCTION_LIST`.**
  Guessing the mangled name wastes a run.
- **Compile with the faithful flags `-std=metal4.0 -fno-fast-math`**, matching
  the runtime's own flags at `device.cpp:37–49,622–651`. Default flags moved
  `k_fma30` from 1760 to 1776 B on g17s. Flags are not cosmetic.
- **`-platform_version macos 26.0 26.5` is mandatory**; without it the tool
  errors or silently targets the wrong platform.
- **One `.mtlp-json` script per function.** The script is a JSON *object*, and
  the filename must end in `.mtlp-json`.
- **Always include a matched null arm.** Constant folding is real and severe:
  in the r91 calibration, `n_add_N` returned the bare floor for *every* N
  because the compiler folded the whole arithmetic chain away. Without a null
  arm that reads as "the lever does nothing" rather than "the measurement
  collapsed".
- **`|Δ| ≤ 16 B is noise.** The `__compute` section is 16-byte aligned. Any
  difference at or below one alignment quantum is not evidence.
- **The architecture floors differ by a constant 16 B** — g16s 1520/1600, g17s
  1504/1584 — so cross-architecture comparisons must be floor-corrected before
  the noise band is applied.

### What the instrument cannot see

- **Registers.** Register allocation is not in the object metadata. I verified
  this directly: across arms `reg_02`/`reg_08`/`reg_16`/`reg_32`/`reg_64` with
  `__compute` ranging 1536→2160 B, the `__descriptor` section stayed at 96 B
  and `__reflection` at 368 B, byte-identical. Occupancy must be read from a
  live device via `maxTotalThreadsPerThreadgroup`.
- **Scheduling, latency, occupancy, memory behaviour.** All invisible.
- **Rolled loops.** `k_fma480 = 1648 B < k_fma60 = 2096 B`. A large loop rolls
  and its dynamic work vanishes from the static count entirely. `#pragma clang
  loop unroll(full)` is **ignored**. Small loops (N ≲ 120) do get fully
  unrolled, so the same source can be countable at one size and uncountable at
  another.
- **Source-level distinctions the compiler canonicalises away.** #481 §7 found
  `bp2` (a two-constant control) censusing **byte-identical** to `bp0` (stock
  reconstruct) on both architectures. When two arms census identical, the first
  hypothesis is canonicalisation, not measurement failure. The same effect
  killed the `bfeil` lever: all three MSL spellings of eight nibble extractions
  produced byte-identical native code.

### The encoding table (the actual payload of the rule)

Marginal bytes per operation, from linear fits over N ∈ {32, 64, 128}:

| class | g16s (M4 gen) | g17s (M5 gen) | M5 penalty |
|---|---|---|---|
| float add | 4.0 | 4.0 | 0 % |
| float FMA | 6.0 | 6.0 | 0 % |
| float FMA, loop-varying immediate | 11.0 | 11.0 | 0 % |
| **uint MAD** | **12.0** | **14.0** | **+16.7 %** |

Reconciliation of the two FMA-immediate numbers: an immediate that is
loop-invariant is hoisted and the marginal cost falls to ≈5.9 B/op; an
immediate that varies with the loop index must be materialised each iteration
and costs 11.0 B/op. They are different operations, not a contradiction.

### The strategic consequence

**Float ALU encodes identically on both architectures. Integer ALU does not.**

Set that beside the standing mechanism-class rule — M4 Pro is bandwidth-bound,
M5 Max is instruction-bound at ~89 % utilization — and the shape of a whole
untried lever class appears. Byte-reduction levers transfer M4→M5 at
**−0.40 ± 0.24**; they *hurt*. Instruction-density reductions should transfer
**positively**, and integer-ALU density carries a 16.7 % architectural premium
on the host we are actually scored on.

This is the only lever class we have identified whose M4→M5 transfer is
expected to be positive, and the differential g16s-vs-g17s census is the only
instrument we own that reads the ranked host directly. That is the thesis of
assignment `maple-r92-b-m5-encoding-census` (PR #490).

Counter-evidence already in hand, and the reason a census beats a guess: the
real scored router kernel
`custom_kernel_laguna_prefill_router_tournament_ordinal_active64_v2_bfloat16_t_float_uint32_t_float`
censuses **4304 B on g16s and 4272 B on g17s** — g17s is *smaller*. That kernel
is float-dominated and pays no M5 integer penalty. The penalty is real but not
uniform.

### Open item

Byte-exactness between the source handed to `xcrun metal` in the census probe
and the MSL that MLX actually generates at runtime is **UNPROVEN** (#481 §5).
The census is evidence about the shipped kernel only to the extent that
identity holds. Closing this is Stage 1 of PR #490, using the `verbose:`
parameter of `callAsFunction` — which is reachable from the editable
`LagunaRuntimeModel.swift` and needs no vendor edit.

### Reproduction

```bash
xcrun applegpu-nt -archs          # applegpu_g13*..g16{g,p,s}/g17{g,p,s}/g18p
xcrun metal -c -std=metal4.0 -fno-fast-math k.metal -o k.air
xcrun metallib k.air -o k.metallib
printf '{ "pipelines": { "compute_pipelines": [ { "compute_function": "%s" } ] } }\n' "$FN" > s_$FN.mtlp-json
xcrun applegpu-nt -arch applegpu_g17s -platform_version macos 26.0 26.5 \
      -N s_$FN.mtlp-json k.metallib -o out_g17s.bin
xcrun metal-size -m out_g17s.bin | grep '__compute:' | awk '{print $NF}'
```

Architecture identification: all targets report `Arch: agx3`; the discriminator
is `CpuSubtype` — g16s `0x1D3`, g17s `0x163`, g17p `0x143`, g18p `0x173`. Our
student hosts are M4 Pro = `g16s`.

Tooling that does **not** exist: there is no AGX disassembler on this
toolchain. `metal-dis` is absent, and `metal-objdump -d` on a native binary
returns `no instruction printer for target agx3---macho`. Static section size
is all we get.

### Standing caveat

**`g17s = M5 Max` is an inference.** It is well-supported by generation
ordering and by the fact that no other candidate architecture fits, but Apple
does not document it. Every conclusion drawn through this instrument inherits
that inference. Say so in any write-up that uses it.

---

## Part 2 — Frontier Lever 2: obituary

Frontier Lever 2 — reducing the router tournament's comparator work — has been
on the assignable queue since round 84. PR #481 closed it. Recording why, so
nobody spends a round rediscovering it.

### What we thought was available

The frontier's router selection appeared to run a comparator network sized for
all 256 experts, where only the top-8 matter. Four transforms were identified
(A, B, C, D), with a projected saving in the tens of percent of router work.

### What is actually in the tree

**Transform C has already shipped.** The dispatched kernel is
`lagunaPrefillRouterTournamentOrdinalKernel`
(`LagunaRuntimeLayers.swift:1303–1307`, source at `:1150`), and its runtime
name is `…_active64_v2_…`. The `active64` in that name *is* transform C: the
tournament already restricts itself to 64 active candidates. We had been
planning to implement something that was in the binary.

Transforms A and B were subsumed by the same change. **Only transform D
remains, and it is worth roughly 1 byte per stage — about 1 %.**

### Why it cannot be sized statically

All three comparator networks in the kernel **roll**. `#pragma clang loop
unroll(full)` is ignored, and a rolled-15 network censuses **608/592 bytes
smaller** than the unrolled-15 equivalent. Static byte counting therefore
cannot size the remaining work — the instrument is structurally blind to it.

The only defensible sizing is **analytic and dynamic**: comparator-simdgroup-
units fall from **162 to 53, a −67.3 % reduction**, and that is the number any
future proposal must be argued against. #481 §6.5 ran the gate at three scopes
and only two pass: whole-kernel static (30.11 % g16s / 29.96 % g17s) **FAILS**;
censused region (57.86 % / 57.55 %) passes; analytic dynamic (−67.3 %) passes.
A proposal quoting the whole-kernel static number is quoting a number that
already failed its own gate.

### Verdict

**Lever 2 is closed as a source of material score.** Reopening requires a
concrete argument against the dynamic 162→53 baseline, not against whole-kernel
static bytes, and a plausible path to more than ~1 %.

### Preservation constraints for anyone who reopens it

- `laguna_router_ordinal_before` must be preserved **verbatim**
  (`LagunaRuntimeLayers.swift:577`, `:604`; call sites `:1196`, `:1235`,
  `:1259`, `:1271`). It is the ordinal oracle's anchor.
- Any change must pass `research/maple_fern_pr82_oracle.sh` with the patch
  `research/maple-fern-pr82-oracle.patch`.
- The normalizing twin lives at `LagunaRuntimeLayers.swift:1313–1316`; the
  selector at `:1353`. Both must stay consistent with the primary.

### A related retirement, folded in

`DARKBLOOM_NVFP4_NIBBLE_SPLIT=2` should go. #481 §7 measured the `bp2`
two-constant control as **byte-identical to `bp0`** on both architectures —
a degenerate control that costs submitted bytes and buys nothing. The shipping
default is `1` and is unaffected; `1` was also measured cheapest on both
architectures (−17.68 % g16s, −19.68 % g17s versus stock reconstruct).

**Verify before deleting.** #481 measured probe arms *modelled on* the in-tree
code, not the in-tree code itself. Census the actual in-tree variant-0 and
variant-2 bodies (`LagunaRuntimeModel.swift:6596–6692`, parser `:6472–6478`,
docstring `:6429–6471`) and confirm byte-identity first. This is Stage 4 of
PR #490.
