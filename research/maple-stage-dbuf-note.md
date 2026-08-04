# Software-pipelining the expert gather-GEMM weight stage without spending a single byte of threadgroup memory

**Model / effort:** Claude Opus 5, high reasoning effort, driven by OpenHands as
the coding agent inside a multi-agent Senpai research harness (an advisor agent
writes assignments, student agents implement and measure them, results are
reviewed and promoted through pull requests).

**What this submission is:** a screening receipt for one structural change to the
routed-expert NVFP4 gather-GEMM used by the 512-token prefill. It converts the
weight-staging step of the k-loop from a fused `load -> decode -> store` into a
split **register prefetch** (device loads for tile `k+1`) and **commit**
(decode + threadgroup store for tile `k`), and issues the prefetch *after* the
RAW barrier so the device read for the next tile is in flight across the current
tile's MMA. It is intended to be bit-exact, and every local gate says it is.

I do not know whether it is faster. My host is an M4 Pro and the kernel this
change targets is compiled only when `metal::is_nax_available()` is true, which
on my machine it is not. The most useful thing in this note is probably not the
mechanism at all — it is section 6, where I measured my own local instrument's
noise floor with a compile-identical control and found it 5x too coarse to
resolve the effect I was trying to measure. I am reporting that plainly because
it is the part that transfers.

---

## 1. Goal and the arithmetic that motivated it

Score on this track is `decode_speedup^0.75 * prefill_speedup^0.25`, so prefill
carries 25% of the exponent weight. On our official receipts the 512-token
prefill costs `S = 98.153 ms`, i.e. 191.70 us/token. Dividing the seed forward's
work by that time gives roughly 28.8 TFLOP/s and roughly 271.8 GB/s.

Against plausible M5 Max ceilings (about 60 TFLOP/s of matrix throughput and
about 485-530 GB/s of achievable DRAM bandwidth) that is approximately **half of
the compute ceiling and half of the bandwidth ceiling at the same time**. A
kernel at 50% of both is not limited by either resource; it is limited by doing
them one after the other.

A per-block roofline of the forward pass makes the target specific. Splitting the
seed forward into blocks and pricing each one at 60 TFLOP/s and 500 GB/s:

```
block                 GFLOP        MB   FLOP/B  cmp ms  dram ms  binds
attn_proj_qkvo       1460.3    2852.1    512.0   24.34     5.70    cmp
routed_experts       1005.0   14087.2     71.3   16.75    28.17   dram   <- target
attn_core             161.1       0.0      inf    2.68     0.00    cmp
shared_expert         125.6      69.0   1820.4    2.09     0.14    cmp
dense_mlp_layer0       51.5     100.7    512.0    0.86     0.20    cmp
router                 20.9      40.9    512.0    0.35     0.08    cmp
```

`routed_experts` is the only DRAM-bound block in the entire forward. That framing
matters, and it corrected my own initial description of the mechanism:

**Staging is not overhead to be removed. Staging *is* the DRAM read of the weight
bank.** Those ~14.09 GB have to cross the bus once no matter what the pipeline
looks like. What pipelining can do is change

```
serial:   cmp + dram  = 16.75 + 28.17 = 44.92 ms
overlap:  max(cmp, dram)              = 28.17 ms
```

So the prize is **the MMA time hidden behind an unavoidable DRAM stream**, and
the floor is hard at roughly 28.17 ms (26.6 ms at 530 GB/s, 29.0 ms at 485). No
pipeline beats that floor. If measurement ever puts this block near 28 ms, the
kernel is finished and further effort on it is waste.

Two honest error bars on that prize. The 60 TFLOP/s figure is a vendor number,
not something we measured. Our own receipt bounds matrix throughput only from
below: the compute floor is at most `98.153 - 34.32 = 63.8 ms`, so M5 Max matrix
throughput is **>= 44.3 TFLOP/s**. If the true figure is 44.3 rather than 60, the
hideable MMA is 22.69 ms rather than 16.75 ms. So the prize is a range,
**16.75-22.69 ms**, and I deliberately did not set a stop rule against any single
point inside it.

Independent corroboration that the block really is serialised rather than
overlapped: the expert block is 45-50% of `S` on our profile, which is 44.2-49.1
ms, and the *serial* prediction is 44.92 ms. The measured share brackets the
serial sum, not the overlapped one.

---

## 2. Environment and base

- Host: Apple M4 Pro, 20 GPU cores, 48 GB unified memory, macOS 26.5.2, Metal
  language version 4.0.
- Ranked host: M5 Max, 128 GB.
- Toolchain per the repository's `setup.sh`; all `swift build` / `swift test`
  invocations passed `--force-resolved-versions` and `Package.resolved` was
  restored afterwards.
- Local harness: `./benchmark.sh --local-iterate` (about 204 s) and
  `--local-submit` (about 160 s), both behind the repository's 40 C thermal gate.
- The submitted change is ON by default. The ranked runner sets no
  `DARKBLOOM_*` environment variables, so a kill-switch read as `!= "0"` means
  unset is the shipped path.

---

## 3. The change

The inner loop of the expert-aligned NAX gather-GEMM
(`fp_quantized_nax.h`) is, in the shipped tree:

```
for k in 0..K_it:
    Atile load                  # already hoisted above the barriers
    threadgroup_barrier         # WAR: waits for iteration k-1's MMA
    loader_w.load_unsafe_wide() # stage Ws: device load -> decode -> tgmem store
    threadgroup_barrier         # RAW: MMA waits for the stage
    MMA over kk1                # reads Ws
    loader_w.next()
```

The A-operand read was already software-pipelined by a predecessor. The weight
read was not, and it is the expensive side: it is the 14.09 GB stream.

The naive fix is to double-buffer `Ws` in threadgroup memory. I did not do that,
for reasons in section 4. Instead I split the single staging call into two:

- **`prefetch<wide_store, wide_load>(StageRegs& r, tiles_ahead)`** — performs
  only the *device* reads for the tile `tiles_ahead` ahead, into a per-thread
  register struct `StageRegs { uint8_t sb[kSrcBytes]; uint8_t sc[kScaleRegs]; bool staged; }`.
- **`commit<wide_store, wide_load>(StageRegs& r)`** — performs only the NVFP4
  decode and the threadgroup store, from those registers.

and rewired the loop so the next tile's device read is issued after the RAW
barrier and therefore overlaps the current tile's MMA:

```
prefetch(stage_regs, 0)             # before the loop: tile 0
for k in 0..K_it:
    Atile load
    threadgroup_barrier             # WAR
    commit(stage_regs)              # decode + store tile k from registers
    threadgroup_barrier             # RAW
    if (k + 1 < K_it) prefetch(stage_regs, 1)   # tile k+1 device read, in flight across MMA
    MMA over kk1
    loader_w.next()
```

`prefetch`'s address arithmetic is lifted verbatim from the loader's own `next()`:
`src + tiles_ahead * tile_stride` and
`scales + tiles_ahead * (reduction_dim == 1 ? n_groups : n_groups * group_stride)`.
That is safe to do positionally because the NAX loader is **stateless** — unlike
the non-NAX loader it carries no `group_step_cnt`, so "one tile ahead" is pure
pointer arithmetic with no hidden counter to keep in sync.

**Why this is bit-exact by construction.** It changes only *when* bytes are read,
never which bytes, which addresses, which decode arithmetic, or the accumulation
order. The register round-trip is byte-preserving: the pre-existing
`fp4nv_pack4(const thread uint8_t*)` overload is little-endian and is the same
packing the fused path used, so `read into registers -> decode from registers`
produces the same operands as `read and decode in one expression`. The MMA reads
the same `Ws` contents in the same order in the same iteration.

I applied the same split to the **non-NAX** twin (`fp_quantized.h`,
`quantized_utils.h`), which is what actually executes on my M4, so the mechanism
could be exercised and gated locally at all. There I left the original `stage()`
byte-for-byte untouched and duplicated the decode into the new `prefetch`/`commit`
pair, so any caller that does not opt in generates identical code. The aligned
k-loop got a **separate** `gemm_loop_aligned_stage2` function rather than a flag
inside `gemm_loop_aligned`, because the latter is shared with the affine
(non-NVFP4) path which is out of scope.

Both changes are gated by `DARKBLOOM_STAGE2_GATHER`, read once as a
process-constant `static const bool`. **Never a Metal function constant:** this
tree records a mid-process function-constant flip forcing a second pipeline
compile *inside* a timed prefill, for a reproducible 15-24% regression. The
define is injected at JIT assembly time so each setting compiles exactly one
pipeline for the process lifetime.

Files changed (all inside the benchmark's declared editable surface; I verified
each one against `benchmark.json`'s 97 `editablePaths` entries):

```
kernels/fp_quantized_nax.h        +169/-  (loader split, expert k-loop rewire)
kernels/fp_quantized.h            + 94    (non-NAX loader split)
kernels/quantized_utils.h         + 40    (gemm_loop_aligned_stage2)
kernels/steel/gemm/nax.h          + 10    (static_assert, section 5)
metal/quantized.cpp               + 36    (non-NAX dispatch trace, default flip)
metal/jit_kernels.cpp             + 26    (inject define into gather-QMM kernels)
mlx-generated/{fp_quantized,fp_quantized_nax,gemm_nax,quantized_utils}.cpp
                                        (embedded twins, mirrored hunk-for-hunk)
```

The `mlx-generated/*.cpp` files are the runtime-compiled copies of those headers
and must stay consistent with them; I mirrored every hunk and diffed the results.

---

## 4. The design decision I think is the most valuable part of the diff

There are three ways to pipeline this loop, and the difference between them is
entirely about threadgroup memory.

The shipped kernel's *entire* threadgroup footprint is `Ws`:
`kWsElems = BN * BK_padded = 64 * 72 = 4608` elements at 2 B, stored as 576
16-byte chunks = **9,216 B**, plus an 8 B `bounds[2]` = **9,224 B**. `Atile` is
register-private, not threadgroup, and `gate_up_stage` is an *alias* onto the
same storage rather than a second allocation.

- **Option A, classic threadgroup double buffering:** 9,224 B -> **18,440 B**.
- **Option B, half-tile rotation** at `SK=32`: partial, awkward, kept as fallback.
- **Option C, register prefetch + threadgroup commit** (what I built): the second
  buffer lives in **registers**, so the threadgroup footprint is **unchanged at
  9,224 B**.

Why that matters more than it sounds. A teammate measured **80 threadgroups
co-resident at 17,920 B each on 20 M4 cores** — 4 per core — putting the per-core
threadgroup-memory budget at >= 71,680 B, and fitted a latency-hiding capacity
`f(m) ~= 1 + 0.365(m - 1)` for `m` co-resident threadgroups. Taking threadgroup
memory as the binding limiter:

| `Ws` footprint | TGs/core | latency-hiding capacity |
| --- | ---: | ---: |
| 9,224 B (shipped, and option C) | 7 | `f(7) = 3.56` |
| 18,440 B (option A) | 3 | `f(3) = 2.10` |

Option A buys overlap *inside* each threadgroup by destroying roughly **1.70x**
of the overlap *between* threadgroups — on the one block in the forward pass that
is DRAM-bound and therefore depends most on having many threadgroups in flight to
cover memory latency. That is the single most common way double-buffering
experiments fail, and 18,440 B is essentially the 17,920 B point that was already
characterised, so this is interpolation rather than extrapolation.

Option C gets the pipelining with **zero occupancy cost**, which makes any
measured delta attributable to overlap and nothing else. That is the whole reason
I chose it.

### A cheaper enabling condition that turns out not to be cheap

The obvious way to rescue option A is to pair it with `BN: 64 -> 32`. Since
`BK_padded` depends on `BK` and not `BN`, `kWsElems` halves, so a double-buffered
`BN=32` costs `2 * 4,608 = 9,216 B` — *exactly* the shipped single-buffered
footprint. Same occupancy, full double buffering, and `grid.x = (N + bn - 1)/bn`
doubles, which is the right direction for a 40-core ranked host. It looks free.

I checked it in the source and it is not free, for a reason I have not seen
stated anywhere:

```cpp
constexpr bool kSwigluRegLocal =
    (WN == 1) && (BN == 64) && ((BM / WM) == 16);
```

`BN == 64` is a **hard term in the predicate that enables the shipped
register-local SwiGLU epilogue.** At `BN=32` that constant silently becomes
false, the `if constexpr (kSwigluRegLocal)` fast path is discarded, and the
kernel falls back to the stock epilogue that round-trips the entire `Dtile`
through `gate_up_stage` in threadgroup memory plus an extra barrier per chunk.
So `BN=32` does not merely change a tile size — **it turns off a shipped,
measured optimization**, and any measurement of `BN=32` is confounded by that
loss.

It is worse than confounded, because of what reactivating that path does. On the
shipped geometry (`BN=64`, `WN=1`, `BM/WM=16`), `kSwigluRegLocal` is true, so the
`!kSwigluRegLocal` block is discarded at compile time and **`gate_up_stage` is
dead code** — never written, never read, an alias to storage nobody touches.
There is exactly one live consumer of `Ws_storage`. Drop to `BN=32` and
`gate_up_stage` becomes live again, storing `Dtile` into `Ws_storage` and reading
it back with a single barrier between. Combine *that* with a double-buffered `Ws`
whose next-tile prefetch is in flight and you have a genuine aliasing hazard —
the kind that a single-prompt `max_abs_diff` check can easily fail to catch.

So the conclusion is the reverse of the intuition: **`BN=32` is not the enabling
condition that makes threadgroup double buffering safe; it is the sole cause of
the aliasing hazard that makes it dangerous.** Option C avoids all of it — one
`Ws`, `BN` unchanged, `kSwigluRegLocal` still true, `gate_up_stage` still
compile-time dead, grid and occupancy bit-identical to shipped.

Two smaller notes for anyone walking the same path: `bn` is hard-coded to 64 in
the host dispatch and no tiling variant changes it, so `BN=32` requires a new
host lever rather than an existing knob; and the `expert_aligned` accept gate
does not test `bn`, so the change would stay on the expert path — it fails
silently in the epilogue, not loudly at dispatch.

### The tiling family around it is closed

I also verified, and can confirm, that the tiling axis has nothing left. Running
a real 512-token routing histogram (76 records x 256 experts = 311,296
assignments, 20.26% zero-row experts, mean 20.07 rows among nonzero, median 11)
through the per-expert schedule:

```
config                     MMA rows   x ideal   stagings
BM=64  WM=4  SM=16          453120     1.456      16758   <- SHIPPED
BM=64  WM=2  SM=32          640000     2.056      16758
BM=128 WM=4  SM=32          640000     2.056      15798
BM=128 WM=8  SM=16          453120     1.456      15798
BM=32  WM=2  SM=16          453120     1.456      20000
```

Three strengthenings of that result:

1. It is an **identity, not an empirical finding**. Whenever `BM % SM == 0`,
   `sum_chunks ceil(chunk_rows/SM) * SM = ceil(n/SM) * SM`. MMA row padding
   therefore depends **only on `SM`**; `BM` is decoupled and affects only the
   staging count. `SM=32` is a flat **+41.2%** in MMA rows under real routing
   (`640000` vs `453120`), while `BM=128` buys only 5.7% fewer stagings.
2. `SM=16` attains the hardware floor because `kFragRows = 16`. `SM=8` would give
   `TM = SM/16 = 0` and emit no MMA at all.
3. **Structurally, most of the family was never reachable.** The
   `expert_aligned` gate requires `bm == 64 && wm == 4 && (wn == 2 || wn == 1)`,
   so every `BM=128` variant falls off the expert path entirely and silently
   dispatches the *non-expert* kernel. Those variants could never have measured
   what their names claim.

---

## 5. A silent-wrong-answer trap, found and closed

`tile_matmad_nax` had exactly two branches — `TN == 1 && TM % 2 == 0`, and
`TN % 2 == 0` — and **no `else`**. Any instantiation outside those two shapes
compiled cleanly and performed **no MMA at all**, returning zeros. Every current
instantiation passes (the shipped variant is `TM=1, TN=4`), so nothing is broken
today, but the next person to touch a tile size would have got silently wrong
numerics rather than a compile error. Added:

```cpp
static_assert(TM > 0 && TN > 0 && ((TN == 1 && TM % 2 == 0) || (TN % 2 == 0)),
              "MXU tile matmul: no MMA form exists for this (TM, TN); "
              "need TN == 1 with even TM, or even TN");
```

I confirmed the trap was real rather than theoretical by checking out the
unmodified base in a scratch worktree and compiling a deliberately out-of-shape
instantiation there: it built without a diagnostic. Under the new assert the same
instantiation is rejected.

This also settles the `BN=32` MMA question above: `TN = BN/(WN*16)`, so `BN=32`
with `WN=1` gives `TN=2`, which is even and legal. `BN=32` fails in the epilogue,
not in the MMA.

### A compile gate for kernels this hardware cannot run

Because the NAX family is unreachable on M4, the ported kernel would otherwise
have been submitted having never been compiled anywhere. I built an offline gate
that assembles the same source `jit_kernels.cpp` assembles and runs `xcrun metal`
over it, so NAX instantiations can at least be **compile-verified** on non-M5
hardware. It covers **12 cases**: 8 expert NAX instantiations (stock and stage-2,
across the `gate_up_static`, `down_static`, `dynamic_scalar` and
`gate_up_store_only` specialisations), the non-expert kernel, the stock and
stage-2 non-NAX twins, and one **negative control** — the out-of-shape
instantiation above, which must be rejected. All 12 behave as required.
`-std=metal4.0` is needed; 3.1 fails.

Knowing that NAX arms are otherwise *structurally blind* on M4 changes how a
team should budget official runs, so I am recording the gate as reusable
infrastructure rather than as part of this experiment.

---

## 6. The result I did not expect: my local instrument cannot see this effect

Three `--local-iterate` arms on the same quiet host under the same thermal gate,
using the paired decomposition

```
S = 512000 * prefill_seconds_per_token          (ms)
T = 1000 * decode_seconds_per_token - S/128     (ms)
```

(the `- S/128` term is necessary because the harness's 512-token *seed* prefill
is inside `decode_seconds_per_token`, so anything touching prefill moves both
observables):

| arm | S (ms) | T (ms) | max_abs_diff |
| --- | ---: | ---: | ---: |
| base, feature absent | 575.311 | 8.9866 | 0 |
| candidate, `DARKBLOOM_STAGE2_GATHER=0` | 568.897 | 9.1237 | 0 |
| candidate, stage-2 **ON** | 576.591 | 9.0436 | 0 |

Candidate-ON versus base is `dS = +0.222%`, `dT = +0.634%`.

Now look at the middle row. With `DARKBLOOM_STAGE2_GATHER=0` the guarded blocks
preprocess away, so that arm compiles **the same JIT source as base**. It is a
compile-identical control and its true effect is exactly zero. It measured
`dS = -1.115%`, `dT = +1.525%`.

**So this host's single-receipt noise floor is at least 1.1% on `S` and at least
1.5% on `T` — 5x and 2.4x the effect I was trying to resolve.** My local
measurement of this mechanism is not weak evidence, it is *no* evidence, and any
of the three orderings above could have been produced by chance. Reporting the
candidate-ON row as a result would have been meaningless in one direction or
misleading in the other.

By contrast the official instrument has a measured 1-sigma of **0.497% on `S`**
(from three byte-identical official runs). It is the strictly better instrument
here, which is why this submission exists at all.

I would rather publish this than a tidier story. A compile-identical control is
cheap, it is the only thing that measures an instrument instead of a change, and
in this case it invalidated my own local result.

### Proving the code under test actually runs

This tree has a scar worth knowing about: two earlier optimization flags
(`STAGE_WIDEST`, `WIDELD`) silently measured their own control, because the
function constants they set only ever reached the *non*-expert kernel. So I
verified reachability rather than assuming it. The `=0` arm printed:

```
mlxfast: fusion inactive: stage2_gather (dispatch non-nax mode=nvfp4 align_MNK=111 N=1024 K=2048 M=4096)
mlxfast: fusion inactive: stage2_gather (expert gather-QMM JIT source)
```

The first line is emitted only on the code path taken when
`metal::is_nax_available()` is false, so the op genuinely dispatches the non-NAX
twin on this host; `align_MNK=111` confirms the *aligned* loop — the one I
modified — is the one that runs. It also shows `M = 4096`, because the gather
flattens rows across experts: another concrete way the M4 instrument differs
structurally from the per-expert NAX schedule it is standing in for (128 threads
and 16 B per lane there, 64 threads and 8 B per lane here).

Related finding while wiring this up: **`DARKBLOOM_STAGE2_GATHER` was dead
scaffolding.** The JIT injection and the dispatch trace both already existed, with
**zero consumers in any kernel source**. Flipping it changed the assembled source
string but could not change compiled semantics — so every prior measurement of
that flag was, necessarily, a measurement of its own control. This change gives
it a real consumer for the first time.

---

## 7. Correctness gates

- `swift test --force-resolved-versions`: **453 of 454**. The single failure is a
  harness self-test unrelated to this change; it **passes in isolation**, and the
  script it exercises is byte-identical to base (verified by diff). It is a
  pre-existing parallel-execution flake.
- `./benchmark.sh --local-iterate`: **`max_abs_diff = 0`**, `checked_steps = 130`,
  identical golden hash and weights hash across all three arms.
- Upstream-equivalence oracle against the vendored reference model: prefill
  `max_abs 0.125` / `mean 0.011933609`, **exactly the base profile**; all 8
  decode steps exactly **0**; every runtime token equal to the upstream token.
- `./benchmark.sh --local-submit`: **passed**.
- Editable-surface audit: all 10 changed source files are inside
  `benchmark.json`'s `editablePaths`. One caveat for anyone scripting this check:
  `editablePaths` contains bare **directory** entries without trailing slashes,
  so a naive `startswith` matcher produces false negatives. Match
  `f == p or f.startswith(p.rstrip("/") + "/")`.
- No JIT disk cache exists (the device library map is in-memory only), so there
  is no stale-library confound between arms.

---

## 8. What I got wrong along the way

- **I initially described the mechanism as removing staging cost.** It does not.
  Staging is the DRAM read; it is irreducible. The correct framing is hiding MMA
  behind it, with a hard floor at the DRAM time. This changed what I built and
  what I would accept as success.
- **I priced double buffering before checking the epilogue's constraints.** The
  `BN=32` rescue looked free on a threadgroup-memory spreadsheet and is not free
  in the source. I found that by reading the predicate, not by measuring.
- **I trusted a stale comment.** The motivation I started from described the
  loader as issuing 16 scalar 1-byte device loads and 32 scalar 2-byte
  threadgroup stores, roughly 50 LSU operations. That describes an *older*
  variant. The shipped loader already does four 4-byte device loads (16 B/lane),
  two scale bytes, and four 16 B threadgroup stores — roughly 7 LSU operations.
  The in-tree "staging is 39.5% of prefill" figure is from that older variant
  too. Consequently the "widen the loads" idea I was pointed at is already done;
  the remaining version of it is **prefetch depth** (16 B -> 32 B in flight per
  lane, `tiles_ahead` 1 -> 2, at a cost of about 9 more registers), which is a
  different change and deliberately not bundled here.
- Two prose/code mismatches in the tree, for the record: a helper's comment says
  its default is 128 while the code returns 256, and a tiling case is commented
  "SHIPPED DEFAULT" while the enclosing function defaults to a different case.
  Trust the code.

---

## 9. Caveats — read these before believing any number here

1. **M4 tiling and geometry verdicts have inverted on M5 in this codebase
   before.** A predecessor measured one tiling variant beating another by
   **+17.47%, 4 of 4 paired runs, with zero distributional overlap**, and the
   official M5 receipts then **reversed** it (204.90 -> 201.64 us/token the other
   way). A 19-point sign reversal. My local numbers are evidence that the
   mechanism *exists and is bit-exact*; they are not evidence of its magnitude
   and not evidence of its sign.
2. As section 6 shows, my local numbers do not even establish magnitude on my own
   host.
3. The NAX port is **compile-verified, not execution-verified**. No hardware I
   have can run it. Its bit-exactness rests on the structural argument in
   section 3 plus the compile gate, and its performance is unmeasured.
4. The prize is a **range** (16.75-22.69 ms) because it depends on an unmeasured
   vendor constant. A teammate is currently measuring achievable M5 bandwidth and
   matrix throughput directly on the ranked host by output-neutral work
   injection; those constants should replace the assumed ones.
5. `S` and `T` must be reported separately, since a prefill-only change still
   moves `decode_seconds_per_token` through the seed forward.

---

## 10. Reproduction

```bash
./setup.sh
swift test --force-resolved-versions && git checkout -- Package.resolved

# candidate (stage-2 is the default; no environment variable needed)
./benchmark.sh --local-iterate

# compile-identical control: guarded blocks preprocess away
DARKBLOOM_STAGE2_GATHER=0 ./benchmark.sh --local-iterate

# offline compile gate, including the negative control (12 cases)
python3 research/nax-compile-gate.py

./benchmark.sh --local-submit
```

---

## 11. What I would do next

1. **Judge this submission on measured `S` against the banked compile-identical
   base control**, not against any modelled number. Screen with one receipt; only
   if `S` moves by >= 1.5% is a confirming pair worth paying for.
2. If the mechanism lands, the next increment on the *same edit site* is
   **prefetch depth** `tiles_ahead` 1 -> 2, taking in-flight bytes per lane from
   16 B to 32 B. Roughly 32 B in flight per lane is where a lane saturates, and a
   separate probe measured 22.9 GB/s at 0.125 MB per dispatch rising to 262.5
   GB/s at 64 MB, with access *pattern* contributing nothing. Measure it as its
   own arm — it is a different mechanism that happens to share a code site.
3. Do **not** spend effort quantizing the attention projections for prefill. That
   block is compute-bound at 512 FLOP/byte (24.34 ms compute against 5.70 ms
   DRAM); shaving bytes that are already hidden while adding dequantization work
   to the binding term makes it slower. The tree's choice to keep prefill on the
   original BF16 projections is correct design, not an oversight — the same
   weights want opposite representations in the two phases.
4. Port the compile gate to cover the remaining NAX kernel families, so M5-only
   code stops being submitted unverified from non-M5 hosts.

No hidden artifacts were read, no prompts, tokens, or answers were hardcoded, no
network or filesystem access is relied upon, and no precision was changed
anywhere by this submission.
