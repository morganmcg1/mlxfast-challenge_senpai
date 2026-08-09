# r96-a — decode attention: occupancy census (Stage 0), R1 no-go, R2 4-deep pipeline

Assignment `maple-r96-a-decode-attention-pipeline`, revision `r96-a-rev1`, PR #511.
Base `codex/mlxfast-maple-20260804-advisor` @ `43036cd39dd3c795b117b099f0fe52767fbedbca`.

Measurement host is Apple **M4 Pro, 20 GPU cores**, 48 GiB, `applegpu_g16s` gen 16.
The ranked host is **M5 Max, 40 GPU cores**. The core-count difference is not a
footnote here — it is the result. See [§4](#4-r2-4-deep-software-pipeline).

Submitted surface: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only
(`LagunaRuntimeLayers.swift` declared, untouched). Everything under `research/`
is research-only.

---

## 1. Stage 0 — pipeline properties and the occupancy census

Probe: `research/nezuko_occupancy_probe.swift` (+ `research/host_device_arch.swift`).

### 1.1 Device

| property | value |
|---|---|
| device | Apple M4 Pro, `applegpu_g16s`, GPU generation 16 |
| GPU cores | 20 |
| `maxThreadgroupMemoryLength` | 32768 B |
| `recommendedMaxWorkingSetSize` | 40200896512 B |

`_nax` prefill kernels are **not** selected on generation 16, so nothing in this
report is evidence about `_nax` code paths.

### 1.2 Pipeline properties of the two scored attention kernels

Both kernels are launched at a fixed 1024 threads/threadgroup.

| kernel | `staticThreadgroupMemoryLength` | `maxTotalThreadsPerThreadgroup` | `threadExecutionWidth` |
|---|---|---|---|
| `laguna_sliding_fused_attn_ring_v1` | 18432 B | 1024 | 32 |
| `laguna_full_fused_attn_grow_v1`    | 18432 B | 1024 | 32 |

18432 B = `outputs4[BN*BDP]` 16896 B + `max_scores[2*BN]` 256 B +
`sum_exp_scores[2*BN]` 256 B + four `[head_dim]` staging arrays at 256 B each.
1024 threads / 32 = **32 simdgroups per threadgroup**.

> Not covered: the "cheap rider" trio kernels (`decode_nvfp4_qkv_*`,
> `oproj_act_*`, `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`). The
> probe's extractor is keyed to the two attention kernels' MSL signature and did
> not generalise for free. Left outstanding rather than half-reported.

### 1.3 Q1 — what is the simdgroup slot budget, and is tgmem the binding constraint?

Three independent measurements, all agreeing.

**Phase B — synthetic residency vs threadgroup memory.** Max co-resident
threadgroups K, sweeping declared tgmem from 16 B to 32768 B:

| threads/TG | co-resident TGs | simdgroups/core | tgmem dependence |
|---|---|---|---|
| 1024 | 60 (3/core) | **96** | **flat, 16 B → 32768 B** |
| 512  | 120 | 96 | flat |
| 256  | 240 | 96 | flat except 32768 B → 130 TGs (52 sg/core) |
| 128  | 480 | 96 | flat except 32768 B → 317 TGs (63.4 sg/core) |

**Phase C — the real sliding kernel body**, with the epilogue plane halved as a
counterfactual:

| arm | tgmem | co-resident TGs | TG/core | sg/core | `maxTotalThreads` |
|---|---|---|---|---|---|
| real plane (shipped) | 18448 B | 60 | 3 | 96 | 1024 |
| real plane / 2       | 10000 B | **60** | **3** | **96** | 1024 |

**Phase D — oversubscribed cross-check** at K=240 requested, 1024 threads:
47 slots pass identically for 16 B, 18432 B, 32768 B, real plane, and real
plane/2.

**Answer.** The budget is exactly **96 simdgroup slots per core** (3072 threads
per core), and at 1024 threads/TG it is **independent of threadgroup memory over
the entire legal range** and independent of this kernel's register pressure.
The shipped geometry already sits at **3 TG/core = full simdgroup occupancy**:
there is no occupancy headroom to buy. Threadgroup memory only becomes binding
below 256 threads/TG at ≥18 kB, which our launches never reach.

Consequently **halving the epilogue plane buys exactly zero residency.** Any
proposal justified by "this frees threadgroup memory, so more threadgroups fit"
is dead on arrival at this geometry.

(Caveat, reported rather than smoothed: the two tgmem-binding rows are mutually
inconsistent as a single per-core pool — 256t@32768 implies ~213 kB/core,
128t@32768 implies ~519 kB/core. The robust, thrice-replicated finding is the
96 sg/core slot budget; the tgmem rows are not load-bearing for any conclusion
here.)

### 1.4 Q2 — read amplification and the bandwidth wall

Each threadgroup reads the whole 512-position window for K and V:
`512 × 128 × 2 B × 2 = 262144 B`. With `gqa = 8` and 2 query heads per
threadgroup, **4 consecutive threadgroups share one KV head**.

| config | heads/TG | TGs sharing a KV head | requested | unique | amplification |
|---|---|---|---|---|---|
| shipped | 2 | 4 | 8.389 MB | 2.097 MB | **4×** |
| R1 (1 head/TG) | 1 | 8 | 16.78 MB | 2.097 MB | **8×** |

Phase E measured real-body cost and requested bandwidth against K:

| K | µs/call | requested GB/s | unique GB/s | vs K=32 |
|---|---|---|---|---|
| 1 | 8.70 | 30.1 | 30.1 | |
| 20 | 8.90 | 589.4 | 147.3 | |
| 24 | 17.60 | 357.5 | 89.4 | |
| **32 (shipped)** | **18.01** | 465.7 | 116.4 | 1.000 |
| 40 | 18.45 | 568.3 | 142.1 | 1.024 |
| 48 | 25.02 | | | 1.389 |
| 60 | 25.52 | 616.4 | 154.1 | 1.417 |
| **64 (R1)** | **32.65** | 513.8 | 128.5 | **1.813** |
| 120 | 48.28 | 651.6 | 162.9 | 2.680 |
| 240 | 95.72 | 657.3 | 164.3 | 5.314 |

**Answer.** The requested-bandwidth asymptote is **~650–660 GB/s** (K=120 →
651.6, K=240 → 657.3). The shipped configuration already runs at
466 / 657 = **71 % of that ceiling**. R1 doubles requested traffic without
changing unique traffic, so its floor is
`16.78e6 / 657e9 = 25.5 µs` against a shipped 18.01 µs — **≥ +42 %**, before any
wave-count effect.

### 1.5 The cost staircase steps at the core count, not at the residency limit

The most useful thing Phase E says is not about bandwidth. Cost is flat from
K=1 (8.70 µs) to K=20 (8.90 µs) — twenty threadgroups, one per core, cost
essentially what one costs — and then **doubles by K=40** (18.45 µs). It steps
at **20 = the core count**, not at 60 = the residency limit.

Fitting `t(K) = a + b·ceil(K/20)` gives `a = 1.413`, `b = 7.849`, so the
marginal wave costs `b / t(1) = 7.849 / 8.716 = 90 %` of a lone wave. Adding a
second threadgroup to a core buys back only ~10 %.

**Therefore 32 co-resident simdgroups already saturate a core: the kernel is
throughput/issue-bound at the shipped geometry, not latency-bound.** This single
fact drives both remaining verdicts. (A prior fit in PR #196 gave `a = 1.661`,
`b = 7.408`, i.e. 83 % — same conclusion, different day.)

---

## 2. R1 (one query head per threadgroup) — pre-registered **NO-GO**

R1 would take sliding from 32 → 64 threadgroups and full from 24 → 48. Stage 0
was the pre-registered gate for R1, and it fails on three independent measured
grounds:

1. **Residency.** R1's stated benefit was freeing threadgroup memory so more
   threadgroups co-reside. §1.3 shows the 18.4 → 9.9 kB reduction buys *exactly
   zero* extra co-residency, in a synthetic sweep, in the real kernel body, and
   under oversubscription. The premise is false.
2. **Wave count.** Cost steps at the core count (§1.5). Shipped K=32 is 2 waves;
   R1 K=64 is 4 waves. Even granting the maximally optimistic pure-compute-bound
   case where halving per-threadgroup work halves the per-wave slope,
   `a + 4·(b/2) = a + 2·b` — **exact break-even**. Any load-bound component makes
   it a strict loss, and under R1 the loads do *not* halve (§1.4).
3. **Bandwidth.** R1 doubles requested traffic against a configuration already at
   71 % of the measured requested ceiling: floor **≥ +42 %** (§1.4).

Direct measurement agrees: Phase E's K=64 row is **1.813× the K=32 cost**.

Supporting prior: PR #48 ran the threadgroup *collapse* (the opposite direction)
ranked as mode 2, receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`, and earned
**−0.1488 %**.

R1 was not implemented. No source change, no timing session spent.

---

## 3. What R2 changes

`Sources/MLXFastModel/LagunaRuntimeModel.swift`, sliding kernel only:
the main accumulation loop goes from a **2-deep to a 4-deep software pipeline**.

```
2-deep:  for (; i + 1*BN < N; i += 2*BN)   slots at i, i+32
4-deep:  for (; i + 3*BN < N; i += 4*BN)   slots at i, i+32, i+64, i+96
```

**Row coverage is provably identical and no tail appears at either depth.**
With `i0 = sg ∈ [0,31]`, `N = 512`, `BN = 32`:

* 2-deep: 8 trips × 2 slots, last trip `i = sg + 448`, visiting `sg+448, sg+480`.
* 4-deep: 4 trips × 4 slots, trip starts `sg, sg+128, sg+256, sg+384`; the guard
  `i + 96 < 512` admits `sg+384` because `sg+384 < 416`.

Both enumerate exactly `{sg, sg+32, …, sg+480}` — 16 rows, same ascending order,
hence the same online-softmax rescale order. Threadgroup memory is unchanged
(no new arrays); there are no barriers inside or adjacent to the loop
(sliding barriers live at L1590/L1740/L1761/L1764), so the rewrite is purely
SIMD-local: no sync change, no tgmem change.

### 3.1 Construction proof

The change is generated, not hand-edited: `research/nezuko_r96_gen4deep.py`
emits every slot block from one template and splices the loop.

**Running the generator at `depth 2` reproduces the shipped source
byte-for-byte** (`diff -q` clean). That is the construction proof that depth 4
alters pipeline depth and nothing else.

### 3.2 Register legality

The assignment required checking `maxTotalThreadsPerThreadgroup` before timing,
because a value below 1024 makes the fixed 1024-thread launch illegal.

| arm | body lines | MSL bytes | tgmem | `maxTotalThreadsPerThreadgroup` |
|---|---|---|---|---|
| base (2-deep) | 268 | 13333 | 18432 B | 1024 |
| **cand (4-deep)** | 356 | 17419 | **18432 B** | **1024** |

**Not register-illegal.** The 3-deep fallback was not needed.

---

## 4. R2 — 4-deep software pipeline: results

Instrument `research/nezuko_pipeline_latency.swift`. ABBA-matched pairs
(A,B,B,A so monotone drift cancels to first order), best-of-3 command buffers.

### 4.1 Correctness: bit-exact

20 configurations — `widx ∈ {0,1,15,31,32,33,255,288,480,511} × K ∈ {1,32}` —
**every checked lane bitwise-equal, `maxUlpDiff = 0`, `maxAbsDiff = 0`**.
This is exact bit-equality, not a tolerance, as the same-slot-order claim
requires.

### 4.2 The calibrated null comes first

Base-vs-base through the identical harness, so the instrument's own bias is
priced before the candidate is read:

| regime | null B/A | candidate B/A |
|---|---|---|
| staircase K=1…20 | 0.9986, 1.0004, 0.9980, 1.0023, 0.9971, 1.0025 | 0.9698, 0.9738, 0.9684, 0.9700, 0.9697, 0.9693 |
| ABBA K=1 median | 0.9997 | **0.9711** |
| ABBA K=32 median / mean | 0.9942 / 0.9948 ± 0.0038 | 1.0091 / 1.0034 ± 0.0047 |
| staircase K=32 | 1.0142 | 1.0157 |
| refit `a` (base → cand) | 1.518 → 1.511 (−0.5 %) | 1.413 → 1.266 (**−10.4 %**) |
| refit `b` (base → cand) | 7.819 → 7.814 (−0.06 %) | 7.849 → 7.745 (**−1.3 %**) |

The null carries a systematic **≈ −0.5 % bias favouring the B slot** at K=32 and
a K=32-specific artifact (+1.4 % in *both* runs). Pair 1 is always a cold-start
outlier; medians are used and pair 1 is dropped.

### 4.3 The result is regime-dependent, and that is the finding

Null-corrected:

| regime on M4 (20 cores) | TG/core | candidate effect |
|---|---|---|
| K = 1…20 | ≤ 1 | **−3.0 %**, six consecutive points, null scatter ±0.25 % |
| K = 24…60 | 1.2–3 | ~0 % (0.998–1.016) |
| K = 64…128 | 3.2–6.4 | −1 to −4 %, noisier |

The low-K effect is **−3.0 % against a ±0.25 % null: a ~12σ separation**, and it
reproduces across six independent K values.

**Mechanism.** A 4-deep pipeline hides memory latency with instruction-level
parallelism *within* a threadgroup. When a core holds **one** threadgroup, that
ILP is the only latency-hiding available and it is worth −3 %. When a core holds
**two or more**, thread-level parallelism between them already hides the same
latency, the ILP is redundant, and the gain nets to zero. This is exactly the
throughput/issue-bound picture of §1.5 seen from the other side.

### 4.4 Why M4 at K=32 cannot see the effect the ranked M5 will

The sliding kernel launches **32 threadgroups** (`heads/2`); full attention
launches 24.

| host | cores | sliding TG/core | regime | M4 proxy |
|---|---|---|---|---|
| M4 Pro (this box) | 20 | 32/20 = **1.6** | 12 cores hold 2 TGs — critical path has TLP | K=32, measures ~0 % |
| **M5 Max (ranked)** | 40 | 32/40 = **0.8** | every TG alone on a core, 8 cores idle | K=20, measures **0.9693** |

M4 structurally cannot reproduce M5's shipped geometry at K=32, because the
critical path on M4 runs through cores holding two threadgroups. The faithful M4
proxy for M5's shipped occupancy is **K=20 — one threadgroup per core with full
20-way bandwidth contention — and it measures B/A = 0.9693.** The gain therefore
survives realistic contention; it is not a single-threadgroup idle-machine
artifact.

This is a textbook instance of the AGENTS.md warning that *"threadgroup geometry
can also change sign across core counts."* Here it changes *magnitude*, in our
favour, and the direction of the extrapolation is the one the warning predicts.

### 4.5 Predicted score impact, and why no end-to-end M4 receipt was run

Using −2.9 % on an estimated ≈290 µs/step of sliding attention:

| shipped scope | Δ µs/step | Δ score @ 0.015280 %/µs |
|---|---|---|
| sliding only (this candidate) | ≈ −8.4 | ≈ **+0.13 %** |
| sliding + full (see §5) | ≈ −11.3 | ≈ +0.17 % |

The **M4 single-receipt detection bar is ≈80 µs/step**. The expected effect is
~7× below it, so an end-to-end `./benchmark.sh --local-iterate` receipt on this
host would be underpowered by construction. **It was deliberately not run**, and
in particular no M4 null result should be recorded as evidence against this
candidate. The kernel-level ABBA instrument with its calibrated null is the
powered measurement; the M5 ranked run is the arbiter.

Current deficit to the frontier is 1.0498 % (best raw candidate
`cs = 2.589321`, receipt `7ce1262d`, record `2.61650354381456`), so a sliding-only
ship is ~13 % of the gap.

---

## 5. Full-attention drain — designed, order-preserving, not shipped here

`laguna_full_fused_attn_grow_v1` has a character-identical main loop plus a tail
(`if (i < N)`, one leftover row) because its `N` is dynamic. The 4-deep drain is:

```
for (; i + 3*BN < N; i += 4*BN) { 4 slots }
if (i        < N) { slot @ +0 }
if (i +   BN < N) { slot @ +1·stride }
if (i + 2*BN < N) { slot @ +2·stride }
```

Ascending order plus `< N` guards give the same reduction order as 2-deep. Worth
roughly −2.9 µs/step (≈ +0.04 % score). Left out of this submission to keep one
mechanism at one call site under measurement; it is a clean follow-up.

---

## 6. Scope discipline

Out-of-scope items named in the assignment were not touched: second `float4`
plane, cross-threadgroup dedup of phase-1 K RMSNorm+RoPE, standalone prefetch
arm, deleting the two `.none` masks, full-attention params memoisation as its own
arm, RoPE restructuring. The merged float4 AoS epilogue
(`research/maple-r85-c-epilogue-result.md`, −20.98 µs/step) is preserved intact —
§1.3 in fact shows why halving that plane would have bought nothing.

## 7. Reproduction

```bash
# Stage 0 census
swiftc -O research/nezuko_occupancy_probe.swift -o /tmp/nezocc && \
  /usr/bin/script -q /tmp/nez_occ_out.txt /tmp/nezocc

# construction proof: depth 2 reproduces the shipped source byte-for-byte
git show 43036cd:Sources/MLXFastModel/LagunaRuntimeModel.swift > /tmp/nez_base_model.swift
python3 research/nezuko_r96_gen4deep.py --depth 2 --in /tmp/nez_base_model.swift --out /tmp/d2.swift
diff -q /tmp/nez_base_model.swift /tmp/d2.swift

# candidate screen (bit-exactness + ABBA + staircase)
swiftc -O research/nezuko_pipeline_latency.swift -o /tmp/nezlat && \
  /usr/bin/script -q /tmp/nez_lat_r2.txt \
  /tmp/nezlat /tmp/nez_base_model.swift Sources/MLXFastModel/LagunaRuntimeModel.swift

# calibrated null
/tmp/nezlat /tmp/nez_base_model.swift /tmp/nez_base_model.swift
```

Stdout from these probes is block-buffered; wrap in `/usr/bin/script` or a trap
loses everything.
