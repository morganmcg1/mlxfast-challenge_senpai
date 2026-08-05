# Pre-registration: M2 Step 1 decision table

Student: maple-fern. PR #63. Assignment `maple-2026-08-05h-lhs-indices-gather-elision`, revision `r1`.
`BASE_SHA = 929b5c439b41675c35d38ede227fd58220c40513`.

**This file is committed before the Step 1 timing run.** Nothing below is
re-tuned after seeing a number. Host: AWS Apple M4 Pro, 20-core GPU, 48 GiB,
`applegpu_g16s` gen 16 (`_nax` unreachable).

---

## 1. What Step 1 measures

Step 1 prices the two halves of M2 separately with a standalone Metal probe at
the shapes Step 0 observed, because the sorted gather-GEMM itself is `_nax` on
M5 and unmeasurable here, while **the row gather is a plain gather kernel and is
measurable** (assignment §5, corollary to 0.9.10).

Probe: `research/maple_fern_m2_gather_probe.swift`, built and run standalone as

```bash
xcrun swiftc -O research/maple_fern_m2_gather_probe.swift \
  -framework Metal -framework Foundation -o /tmp/m2probe
/tmp/m2probe 1 7     # regime A: 1 layer slot,  18 MiB working set
/tmp/m2probe 8 7     # regime B: 8 layer slots, 144 MiB working set
```

Three GPU kernels, all on `bf16`-sized (2 B) elements, all at the Step 0 shapes:

| symbol | kernel | physical traffic |
|---|---|---|
| `t_gather` | `out[i][j] = src[rowOrder[i]][j]`, `src` 512x2048, `out` 4096x2048 | 2 MiB R + 16 MiB W |
| `t_seq` | consume all 4096x2048 logical elements from the contiguous 16 MiB sorted copy | 16 MiB R |
| `t_perm` | consume the same 4096x2048 logical elements from the 512-row 2 MiB source through `rowOrder` | 2 MiB R, 8x reuse |

`rowOrder` model: each of 512 tokens appears exactly 8 times (topK = 8), placed
at deterministic pseudo-random sorted positions (seeded Fisher-Yates). This is
the correct distributional model of `row_order[off] = idx / M` after an
expert-major counting sort, because a token's 8 experts are scattered across
256 buckets.

Every timing is a GPU-only `MTLCommandBuffer` `gpuEndTime - gpuStartTime`, with
**>= 5 matched repetitions** reported as median plus min/max, and the three
kernels **interleaved per repetition** (not run in three blocks) so host thermal
or DVFS drift cannot land preferentially on one arm.

### 1a. Two cache regimes, because residency is the whole question

`half_b` is a cache question, not a DRAM question. In situ the 16 MiB sorted
copy is written and then immediately re-read, but the routed GEMM streams
~453 MB of expert weights per layer through the same hierarchy while doing so.
Neither "fully SLC-resident" nor "fully DRAM-bound" is obviously right, and the
two bracket the answer, so the probe runs both:

| regime | `layers` arg | working set | expected character |
|---|---|---|---|
| A | 1 | 2 MiB src + 16 MiB dst = 18 MiB | both arms cache-warm; smallest absolute gap |
| B | 8 | 16 MiB src + 128 MiB dst = 144 MiB | DRAM traffic forced; largest absolute gap |

Both are reported in full. The decision uses **whichever regime gives the larger
`converted_M5_ms`**, i.e. the bracket end most favourable to the mechanism, so
that a STOP verdict is robust and a GO verdict still requires Step 2 to confirm
it end to end.

---

## 2. Derived quantities (formulas fixed now)

Per-layer savings, 39 routed layers (layers 1-39; layer 0 is dense):

```
half_a_us_per_layer  = t_gather                       # kernel deleted outright
half_b_us_per_layer  = t_seq - t_perm                 # may be <= 0
combined_M4_ms       = 39 * (half_a + half_b) / 1000
converted_M5_ms      = 0.399 * combined_M4_ms
score_delta_pct      = 0.371 * converted_M5_ms
```

The byte-arm factor is **0.399 = 260.2 GB/s (M4 measured DRAM) / 651.8 GB/s
(M5 measured in-situ byte rate)**, per assignment §5. Explicitly **not** 0.501
(wall-clock class) and **not** 0.812 (residual class). Prefill exchange rate
1 ms = 0.371% of score.

### 2a. The multiplier is 39 and that is the generous choice

The Step 0 census counted **38** `lagunaFusedSortedRoutedGateUp` calls per
forward, not the 39 the config implies (`num_hidden_layers = 40`,
`mlp_only_layers = [0]`). Whether the 39th routed layer also materialises a
sorted copy through `SwitchGLU`/`gatherSort` is being resolved separately. The
formulas keep **39** because that is the larger multiplier and therefore the
choice most favourable to the mechanism; if the true count is 38 every number
above scales by 38/39 = 0.974, which cannot flip D1 or D2 and can only make D3
fire more readily. Reported alongside the result either way.

---

## 3. Decision table (binding)

| # | Condition, evaluated in this order | Action |
|---|---|---|
| D1 | max/min spread of any of the three medians > 1.20 | **STOP.** Not an instrument at this resolution; report inconclusive, do not proceed on noise. |
| D2 | `half_b < 0` and `half_a + half_b <= 0` | **STOP.** The scatter penalty eats the whole gather saving; M2 is retired with a measurement. |
| D3 | `converted_M5_ms < 1.0` | **STOP.** Below the assignment's floor (+0.371% of score) for a 3-file kernel change across the correctness surface. Report the negative; this is a merge, not a failure. |
| D4 | `converted_M5_ms >= 1.0` | Proceed to Step 2 (kernel surgery), then mandatory two-part certification. |

D1 is evaluated on **every** regime (any arm too noisy kills the measurement).
D2, D3 and D4 are evaluated on the regime whose `converted_M5_ms` is **larger**
(§1a), and both regimes' full numbers are reported.

No other outcome authorises Step 2. If D3 fires I do **not** re-run with a
different probe shape hoping to clear the bar. The two regimes and two reps
counts written above are the entire authorised search.

---

## 4. Interpretation limits, stated before the numbers exist

These are recorded now so they cannot be selected post hoc:

1. **`half_a` transfers; `half_b` is an upper bound.** Deleting the gather
   deletes its wall time, so `half_a` is a real removal. `half_b` measured
   standalone is an **upper bound on `half_b` in situ**, because in the real
   pipeline the x read happens inside the routed gather-GEMM, which on M4 reads
   ~453 MB of expert weights per layer against ~16 MiB of x (x is ~3.6% of its
   read traffic) and runs at **266.65 ms against a 74.8 ms DRAM floor**
   (`research/maple-fern-prefill-roofline.md`), i.e. ~28% DRAM utilisation and
   therefore not DRAM-bound. A kernel that is not bandwidth-bound does not
   return the full price of bytes removed from it.
2. **The indirection is not free.** Step 2 adds `rowOrder[i]` to the x load of a
   kernel whose loader is already the LSU bottleneck (`quantized.cpp:~1283`
   prior art: ~50 LSU ops vs ~40 compute ops per thread per k-iteration). The
   probe's `t_perm` includes the index load, so this cost is inside the measured
   number rather than assumed away.
3. **0.9.18 (%-of-ceiling logical-byte law) applies to `half_b`, not `half_a`.**
   The 16 MiB sorted copy is written and immediately re-read, so on a Max part
   it may already be substantially SLC-resident. `t_seq` vs `t_perm` is exactly
   the measurement of that residency, which is why the probe reads both patterns
   rather than assuming DRAM for either.
4. **M2 and gather-GEMM "mechanism #3" (x re-read, HELD) are the same bytes**
   (`research/CURRENT_RESEARCH_STATE.md:1108-1112`). Whatever Step 1 returns
   must never be summed with #3.
5. The probe emulates the *access pattern*, not MLX's exact `Gather` kernel, so
   `t_gather` is a **lower bound** on the real kernel's time (my kernel is a
   pure copy with no general strides, offsets, or bounds machinery). A lower
   bound on the saving is the conservative direction for a go/no-go.
6. **`t_perm` uses the most favourable possible permuted geometry.** One
   threadgroup reads one whole 4 kB row contiguously. The real sorted-rhs kernel
   loads `bm x bk` tiles (16 rows x 32 elements = 16 scattered 64 B loads on the
   non-`_nax` path, 64 rows x 64 elements on `_nax`), which is strictly worse
   for a permuted read and no worse for a sequential one. So the real `half_b`
   is **smaller** than the probe's. Together with limit 1 this makes the whole
   Step 1 estimate an upper bound on the achievable saving: a STOP is safe, a GO
   is only permission to try.

---

## 5. Standing checks

Pre-measurement inject check (0.5) must show defaults `0` and `160` before any
timing run, pasted into the result. Byte budget cap for this assignment is
<= +8,000 B net; the probe is `research/`-only and therefore outside the
submitted surface.
