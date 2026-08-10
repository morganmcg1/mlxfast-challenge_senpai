# r105-E — Decode bandwidth efficiency: does the M4→M5 gap name a real surplus?

**Outcome: N-1.** No decode family retains a defensible bandwidth surplus of
≥32.8 µs/step (0.5 % of `cs`) after the measured pattern ceiling is applied. The
largest single-family bandwidth-attributable surplus is **25.2 µs/step
(0.384 % of `cs`)**, and the sum over every roofline-modellable family is
**101.6 µs/step = 1.548 % of `cs`** as a deliberately conservative upper bound,
tightening to **35.8 µs = 0.545 % of `cs`** once a probe-only artifact is removed.

**Primary metric `decode_recoverable_bandwidth_surplus_pct_of_cs` = 1.548**
against a baseline of 10.25. Delta **−8.70**.

The 12.9-point M4→M5 DRAM-efficiency gap is **not** an extraction deficiency.
It decomposes into (i) a busy-versus-wall axis mismatch inside the assignment's
own constants worth 1.92 % of `cs`, and (ii) Amdahl arithmetic on a fixed
non-DRAM component that M5 has already made **25 % smaller** than M4's. A
fourth explanation, absent from the assignment's D/B/P trichotomy, absorbs the
whole residue. Per the stopping rule, A5 was not completed.

Phase A only. Zero official receipts. Zero bytes under `Sources/` or `Vendor/`.

---

## 0. Zero-byte proof

```
$ git diff --numstat 9274c2923e38c9bc3925cb6409fade962ad571de HEAD -- Sources Vendor
$                      # no output
```

Every file added by this experiment is under `research/`, which appears zero
times in `benchmark.json` and is therefore outside the submission surface.
Nothing was built, timed against the harness, or submitted. No dial owned by
frieren (#597 router family), nezuko (#584 fused-attention families) or tanjiro
(#592 prefill `_nax` gather-GEMM) was touched.

## 1. Host and the M4/M5 caveat

Apple **M4 Pro**, 14 CPU / **20 GPU cores**, 48 GB unified, `applegpu_g16s`,
Apple GPU generation 16. The ranked host is an **M5 Max with 40 GPU cores**.
Everything measured here is M4. Per `AGENTS.md`, threadgroup geometry can change
sign across core counts, so every M5 quantity in this report is an explicitly
labelled projection, never a measurement.

## 2. What the assignment asked and what came back

| axis | hypothesis H-105E | verdict |
|---|---|---|
| **(D) DENOMINATOR** | the 266.3 / 610 GB/s constants, or the access pattern, make the ceilings unreachable | **≈ 0 on the pattern axis** (A3: 98.0 % of 266.3 reached by a faithful replica); the M5 constant is unprobed |
| **(B) BYTE MODEL** | the 1,671,402,432 B/step census is wrong, so the achieved bandwidth is misstated | **≈ 0** — byte-exact against the compiled MSL for every family ≥1 % of bytes |
| **(P) PARALLELISM** | M5's extra cores leave fixed-geometry dispatches under-occupied | **the only non-zero term: ≤1.548 % of `cs`, no family ≥0.5 %** |
| **(L) fixed non-DRAM time** — *not in the assignment's trichotomy* | `T = B/BW + L`; efficiency falls when `B/BW` shrinks and `L` does not | **absorbs the entire remaining gap** |

---

## 3. A3 — standalone pattern-bandwidth probe (ran first; it is the ceiling)

Source `research/fern_r105e_bw_probe.swift`, artifact
`research/artifacts/fern-r105e/pattern-bandwidth.json`.

```
xcrun swiftc -O research/fern_r105e_bw_probe.swift -o /tmp/fern105e && /tmp/fern105e
```

The probe allocates a 1024-slab synthetic expert bank (1 GiB codes + 64 MiB
scales) and issues 128 calls per timed dispatch, so **1.141 GB of unique bytes
per window against a ~24 MiB SLC** — no window can be cache-warm. Slab order is
a deterministic permutation, so unique bytes equal issued DRAM bytes by
construction.

### 3.1 Bandwidth is a function of total grid threads

| grid threads | best GB/s | % of 266.3 |
|---:|---:|---:|
| 1 280 | 65.99 | 24.8 |
| 2 560 | 125.05 | 47.0 |
| 5 120 | 225.14 | 84.5 |
| **10 240** | **263.12** | **98.8** |
| 20 480 | 260.44 | 97.8 |
| 40 960 | 257.69 | 96.8 |
| 81 920 | 255.98 | 96.1 |
| 163 840 | 251.35 | 94.4 |

Saturation is at ~10 240 threads = **512 threads per core** on 20 cores. Below
that the relationship is near-linear. `stream_peak = 263.12 GB/s` at
(512 threads/TG, 1 TG/core, 2 loads in flight) — 98.8 % of the Rule-80 constant,
and within 0.06 % of r101's independent 262.98.

### 3.2 The pattern penalty is zero

The `nvfp4_qmv` replica reproduces the real routed-expert read shape: 64-thread
threadgroups, 2 simdgroups, `uint2` lane loads striding `row*1024 + lane*8`,
per-row 1 B base + 32 B nibble scales.

| sgPerTG | threads/TG | TGs | replay activation | µs (median) | DRAM GB/s | issued GB/s | % of 266.3 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 64 | 262 144 | yes | 4371.62 | **260.97** | 752.20 | 98.0 |
| 2 | 64 | 262 144 | no | 4371.17 | 260.99 | 260.99 | 98.0 |
| 8 | 256 | 65 536 | yes | 4380.00 | 260.47 | 750.76 | 97.8 |
| 16 | 512 | 32 768 | yes | 4370.46 | 261.04 | 752.40 | 98.0 |

**260.97 GB/s = 98.0 % of 266.3 = 99.2 % of stream peak.** The faithful
routed-expert pattern is not penalised. `gather_slab` (8 × 1 MiB slabs per call)
ran 251.37–260.79 GB/s, so slab selection costs ≤4 %. 64-thread threadgroups are
not a handicap: `stream_tg64` peaked at 260.76 GB/s = 99.1 % of stream peak.
Loads-in-flight (1→8) is a lever only under starved occupancy (+5.9 % at 1280
threads, 0 % at saturation).

**⇒ (D) is ≈ 0 on the pattern axis. The pattern ceiling used throughout this
report is 260.97 GB/s.**

### 3.3 Issued-versus-unique amplification is measured to be free

The `replay activation` arm re-reads the shared activation vector once per
simdgroup, driving **issued** bandwidth to 752 GB/s (2.88× amplification) on a
4 KB buffer. Cost: **0.45 µs out of 4371 µs = 0.010 %.** This is a direct
measurement of the N-2 condition, not an inference.

---

## 4. A1 — per-family achieved-bandwidth ledger

`research/artifacts/fern-r105e/family-bandwidth-ledger.csv`, produced by
`python3 research/fern_r105e_ledger.py`. 25 families, ranked by `surplus_us_m4`.

Three independent sources are joined:

* **bytes** — `research/artifacts/fern-r105d/decode-byte-census.json`, 1,671,402,432 B/step.
* **labels** — M4 Pro `DARKBLOOM_GPU_PROFILE_SPLIT=1` per-step sums from PR #488
  (`research/maple-nezuko-r92-barrier-hoist-generalization.md:70-100`,
  `research/fern_r105d_bytes.py:142-155`), 79-step steady window, 406
  dispatches/step. `vn_copy` is absent from that census and is null here.
* **geometry** — grid and threadgroup sizes in threads, from
  `/tmp/r105c/dump/a_base/dispatch.tsv`.

### 4.1 The three required reconciliations

| # | check | result |
|---|---|---|
| 1 | `Σ bytes_unique` vs census step total | 1,671,402,432 B — **exact by construction** |
| 2 | `Σ label_us_m4` vs the same session's `gpu_busy_sum` | 8528.3 µs vs **8528.0 µs** — closes to **0.3 µs** |
| 3 | `Σbytes / Σlabel` vs the assignment's 210.5 GB/s | **195.98 GB/s (73.59 %)** vs 210.5 GB/s (79.05 %) — a **7.4 % mixed-session artifact**, see §4.2 |

Reconciliation 2 is the important one. `Σ labels = 8528.3 µs` reproduces the
busy sum recorded in that same run (`…r92…:72-73`, cross-checked in
`research/maple-frieren-r94-decode-residue-ledger.md:19-20,134`) to three parts
in 10⁵. The label table and the byte census describe the same 25 families of the
same step.

### 4.2 The assignment's 210.5 GB/s is a mixed-session number

The assignment computes M4 achieved bandwidth as `1671.4 MB / 7940 µs`. That
7940 µs busy figure comes from a **different, non-SPLIT** session
(`research/maple-nezuko-r93-c-stall-structure-census.md:136`,
`research/nezuko-pr158-decode-dead-time.md:1401,1606`), while the byte census
and every per-family label come from the SPLIT=1 PR #488 session whose busy sum
is 8528 µs. `SPLIT=1` inflates busy by **8528/7940 = 1.074**.

More consequentially, the comparison itself changes axis:

| M4 quantity | µs | GB/s | % of 266.3 |
|---|---:|---:|---:|
| busy, non-SPLIT session | 7940 | 210.5 | **79.05** ← used by the assignment |
| **wall, same axis as the M5 step** | **8233** | **203.0** | **76.23** |
| SPLIT=1 label sum | 8528.3 | 195.98 | 73.59 |

The M5 figure, 4141.5 µs, is a **step** time: it is wall-equivalent and includes
inter-dispatch gaps. Comparing M4 *busy* with M5 *step* is a category error.
On the matched wall axis the gap is **10.07 points, not 12.9**, and naive parity
extrapolation gives **+8.33 % of `cs`**, exactly the assignment's own stated
lower bound.

**⇒ 10.25 − 8.33 = 1.92 % of `cs` (18.7 % of the headline claim) is a
measurement-axis artifact, not a physical surplus.**

### 4.3 Two regimes, and why the ledger says so

A DRAM roofline only describes a dispatch that moves enough bytes to amortise
memory latency. The ledger marks a family `BANDWIDTH` when it moves ≥1 MiB per
dispatch **and** launches ≥5120 threads, and `LATENCY` otherwise. The 13
`LATENCY` families hold **0.705 % of step bytes** but 21.6 % of the SPLIT=1
label; their cost is dispatch and serialisation, and their apparent "surplus"
must not be booked as bandwidth.

### 4.4 Top 8 by `surplus_us_m4` (M4 µs, distance to the occupancy-derated 260.97 GB/s ceiling)

| # | family | regime | label µs | achieved GB/s | % of 266.3 | % of pattern ceiling | surplus µs | cum % |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `sliding_fused_attn_ring` | BANDWIDTH | 636.0 | 98.9 | 37.1 | 38.6 | 390.7 | 24.1 |
| 2 | `prefill_router_tournament` | LATENCY | 185.5 | 0.34 | 0.13 | 2.6 | 180.7 | 35.2 |
| 3 | `residual_rms_router` | BANDWIDTH | 312.8 | 130.7 | 49.1 | 50.4 | 155.0 | 44.8 |
| 4 | `full_fused_attn_grow` | BANDWIDTH | 229.7 | 102.7 | 38.6 | 39.9 | 138.1 | 53.3 |
| 5 | `rmsbfloat16` | LATENCY | 141.9 | 3.6 | 1.3 | 13.6 | 122.7 | 60.9 |
| 6 | `shared_nvfp4_swiglu_qmv_rows1_halved` | BANDWIDTH | 287.1 | 151.3 | 56.8 | 58.4 | 119.4 | 68.2 |
| 7 | `oproj_act_h64` | BANDWIDTH | 1117.7 | 232.2 | 87.2 | 89.6 | 116.1 | 75.4 |
| 8 | `routed_nvfp4_swiglu_qmv_packed_top8keys` | BANDWIDTH | 1497.7 | 232.1 | 87.2 | 92.6 | 111.6 | 82.3 |

Total positive surplus 1622.1 µs over 20 families; the top 8 hold 82.3 %.

**None of this is bandwidth surplus.** Rows 1 and 4 are fused attention: an
online-softmax loop with a sequential dependency over K blocks, not a streaming
kernel. Row 3 is a cross-threadgroup reduction. Rows 2 and 5 are `LATENCY`
regime: 39 and 41 single-threadgroup dispatches whose whole cost is launch and
serialisation. Rows 6–8 are already at 89–93 % of their derated ceiling.

The families that carry the bytes are already close to the roofline:

| family | % of step bytes | % of 266.3 |
|---|---:|---:|
| `lmhead_int5_base_coarse_delta` | 6.53 | **97.5** |
| `dense_down_residual` | 2.01 | 94.2 |
| `dense_gate_up_swiglu` | 4.02 | 93.5 |
| `nvfp4_qkv_h64` | 19.43 | 91.0 |
| `nvfp4_qkv_h48` | 5.18 | 89.6 |
| `oproj_act_h64` | 15.53 | 87.2 |
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | 20.80 | 87.2 |
| `routed_shared_nvfp4_down_residual` | 11.70 | 85.5 |

Those eight families are **85.2 % of all step bytes at 89.7 % of the Rule-80
constant.** There is no large pool of badly-streamed bytes to reclaim.

### 4.5 Known ledger caveats

* `gather_front` (0.024 % of bytes) has an internally inconsistent
  (bytes, geometry) pair: 401,408 B in a 3.4 µs label at a grid of 1 thread
  implies 118 GB/s single-threaded. Its `pct_of_pattern_ceiling` of 230 879 % is
  the ledger correctly refusing to model it. It changes no conclusion.
* Geometry for `rmsbfloat16`, `residual_rms_bf16_2048_v1`, `gather_front` and
  `argmax` was ambiguous in the trace; each was resolved to the reading
  consistent with r105-D's `SINGLE_TG` classification.
* `vn_copy` has no label in the PR #488 census and is emitted with null timing
  columns.

---

## 5. A2 — issued versus unique for every family ≥1 % of step bytes

Derived from the dumped compiled MSL under `/tmp/r105c/dump/a_base/`. "Issued"
is the pessimistic per-thread sum of source-level load widths; hardware fetches
at cache-line granularity, so the true figure is lower.

| family | unique B/dispatch | issued B/dispatch | amp | dominant re-read buffer | buffer B | DRAM-visible? |
|---|---:|---:|---:|---|---:|---|
| `nvfp4_qkv_h64` | 10,827,776 | 53,411,840 | 4.93 | `normalized` | 4,096 | no — L1 |
| `nvfp4_qkv_h48` | 8,663,040 | 42,729,472 | 4.93 | `normalized` | 4,096 | no — L1 |
| `oproj_act_h64` | 8,669,312 | 19,398,656 | 2.24 | `attention_output` | 16,384 | no |
| `oproj_act_h48` | 6,502,496 | 14,548,992 | 2.24 | `attention_output` | 12,288 | no |
| `routed_shared_nvfp4_down_residual` | 5,026,880 | 10,620,928 | 2.11 | `routed_activated` | 8,192 | no |
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | 8,912,896 | 25,690,112 | 2.88 | shared hidden row | 4,096 | no |
| `shared_nvfp4_swiglu_qmv_rows1_halved` | 1,118,208 | 3,276,800 | 2.93 | `input` | 4,096 | no |
| `residual_rms_router` | 1,061,888 | 1,442,816 | 1.36 | `residual`/`branch`/`weight` | 4,096 ea | no |
| `sliding_fused_attn_ring` | 2,118,664 | 8,503,296 | 4.01 | `k_cache`+`v_cache` | 1,048,576 ea | no — L2/SLC |
| `full_fused_attn_grow` | 2,376,464 | 7,147,520 | 3.01 | `k_cache`+`v_cache` | ~1.18 MiB live | no — L2/SLC |
| `dense_gate_up_swiglu` | 67,112,960 | 75,497,472 | 1.13 | `input` | 4,096 | no |
| `dense_down_residual` | 33,574,912 | 41,947,136 | 1.25 | `activated` | 16,384 | no |
| `lmhead_int5_base_coarse_delta` | 109,187,072 | 520,224,768 | 4.77 | `x` | 4,096 | no — L1 |

**Every buffer above the ~24 MiB SLC has amplification exactly 1.00**:
`fused_weight` 64 MiB, `down_weight` 32 MiB, `codes_base` 98 MiB,
`routed_down_weight` 128 MiB. Their row partitions are disjoint by construction
(`row_base = tile*rows_per_group + simd_group*rows_per_thread`). Every
amplification above 1.05× sits on a 4 KiB–1.5 MiB buffer. §3.3 measured that
exact situation at 0.010 % cost.

**⇒ the N-2 condition holds in substance: there is no redundant DRAM weight
traffic to remove in any of these thirteen kernels.**

### 5.1 (B) BYTE MODEL is verified, not assumed

I confirmed the attention byte model directly against the compiled kernel
(`lib_0095_…nvfp4_qkv_h64….msl:1150-1215`):

```
in_vec_size_w = axis_size/2  = 1024 B codes per row
row_base      = scale_bases[out_row]                    →   1 B per row
nb            = scale_nibbles + out_row*(in_vec_size_g/4) →  32 B per row
                                                          ------
                                                          1057 B per row
```

Cross-check: `nvfp4_qkv_h64` = 10,823,680 B/call ÷ 1057 = **10 240 rows =
8192 (q) + 1024 (k) + 1024 (v)** ✓. `oproj_act_h64` = 8,652,800 ÷ 2048 rows =
**4225 = 8192/2 + 8192/64 + 1** ✓. The routed qmv reconciles exactly to
8 × (1,048,576 + 65,536) = **8,912,896 B/call** ✓.

An interim analysis claimed attention loads as INT8-g32 affine (2176 B/row),
which would raise the step by 46.4 %. That is **refuted**: it rested on a
checkpoint-footprint comparison, and attention ships BF16 on disk and is
re-quantised to NVFP4 lane-major by the offline transform, so a disk-footprint
reconciliation is invalid for any re-quantised tensor.

Bounded unpriced items, all together well under 1 % of the step: the
`scale_bases[row]==0xFF` escape path (would cost 1153 B/row, +9.1 %, but only on
escaped rows; the model assumes an escape rate of 0), indexed-affine LUTs
(≤256 KB/bank), scale-patch headers (~15 KB/step), router top-8 index buffers,
KV **writes** (163,840 B/step) and output writes (~1 MB/step).
`lmhead_int5_base_coarse_delta`'s 109,182,976 B is a hardcoded measurement
(`research/fern_r101_byte_audit.py:234`), not shape-auditable — but it achieves
97.5 % of 266.3, so any error there would have to make the model *better*.

**⇒ (B) ≈ 0, with a bounded residual uncertainty of ≲1 % of step bytes that
would, if anything, raise the floor and shrink the recoverable surplus.**

---

## 6. A4 — apportionment of the 12.9-point gap

### 6.1 The fourth explanation

Write `T = B/BW_peak + L`, with `L` all time not spent moving DRAM bytes.
Using the A3-measured pattern ceiling (260.97 GB/s on M4; 610 × 0.98807 =
602.7 GB/s projected for M5 using the M4-measured extraction fraction):

| host | step T µs | DRAM term µs | **L** µs | efficiency |
|---|---:|---:|---:|---:|
| M4, wall | 8233.0 | 6404.6 | **1828.4** | 77.79 % |
| M4, busy (non-SPLIT) | 7940.0 | 6404.6 | 1535.4 | 80.66 % |
| M4, SPLIT=1 labels | 8528.3 | 6404.6 | 2123.7 | 75.10 % |
| **M5, step** | **4141.5** | **2773.1** | **1368.4** | **66.96 %** |

`L5 / L4(wall) = 0.748`. **M5's non-DRAM time is 25 % smaller than M4's in
absolute microseconds.** The efficiency ratio nevertheless falls, because the
DRAM term shrank by 2.31× while `L` shrank by only 1.34×. This is Amdahl's law
on a non-scaling component; it is arithmetic, not a deficiency.

The decisive counterfactual: if M5 carried M4's own `L`, its step would be
2773.1 + 1828.4 = **4601.5 µs** at **60.27 %** efficiency. M5 is observed at
4141.5 µs and 66.96 %. **M5 is 6.7 efficiency points *better* than transferring
M4's behaviour predicts, not 12.9 points worse.**

`L5 = 1368.4 µs` is, to within 33 µs, r105-D's already-published
`m5_headroom_above_dram_floor_us = 1401.5`, which that ledger explicitly records
as a subtraction residual and not a lever.

### 6.2 The apportionment

| bucket | µs/step (M5) | % of `cs` | share of the 10.25 claim | basis |
|---|---:|---:|---:|---|
| **(D) DENOMINATOR — pattern** | 0 | 0.000 | 0 % | A3: faithful replica reaches 98.0 % of 266.3, 99.2 % of stream peak |
| **(D) DENOMINATOR — measurement axis** | 126.4 | **1.925** | 18.8 % | M4 *busy* compared against M5 *step*; matched wall axis gives 8.33 % not 10.25 % |
| **(B) BYTE MODEL** | 0 | 0.000 | 0 % | MSL-exact for 85 % of bytes; amplification measured to cost 0.010 % |
| **(P) PARALLELISM** | ≤101.6 | **≤1.548** | ≤15.1 % | occupancy derating of every `BANDWIDTH` family, M4 curve projected to 40 cores |
| **(L) fixed non-DRAM time** *(not in the trichotomy)* | 445.5 | **6.784** | 66.2 % | residual; equals the part of `L5` that M4-parity would have to erase |
| **total** | 673.5 | 10.257 | 100 % | |

Residual after D, B and P: **6.784 % of `cs`**, and it is named — it is `L`, the
1368.4 µs of M5 step time that is not DRAM traffic. It is a dispatch-count,
launch-latency and dependency-chain quantity, addressable (if at all) by the
work already assigned elsewhere, and it is categorically not "bandwidth
efficiency".

### 6.3 The (P) bucket in detail, and why it does not clear the bar

`m5_occupancy_frac` derates each family by evaluating the A3 curve at
`grid × 20/40` — the M4-equivalent threads-per-core of that dispatch on 40
cores.

| family | grid threads | M5 occupancy | penalty µs | % of `cs` |
|---|---:|---:|---:|---:|
| `nvfp4_qkv_h64` | 327 680 | 0.955 | 25.2 | 0.384 |
| `oproj_act_h64` | 16 384 | 0.954 | 21.0 | 0.320 |
| `routed_nvfp4_swiglu_qmv_packed_top8keys` | 131 072 | 0.975 | 14.8 | 0.226 |
| `routed_shared_nvfp4_down_residual` | 147 456 | 0.974 | 8.7 | 0.133 |
| `lmhead_int5_base_coarse_delta` | 3 211 264 | 0.955 | 8.5 | 0.129 |
| `nvfp4_qkv_h48` | 262 144 | 0.961 | 5.8 | 0.089 |
| all `BANDWIDTH` families | | | **101.6** | **1.548** |

**The maximum is 0.384 % of `cs`, against an effort bar of 0.5 %. N-1 fires.**

The 1.548 % aggregate is a deliberately loose upper bound, and the ledger itself
refutes part of it. Most of the penalty for the huge-grid families comes from
the probe's measured decline above 10 240 threads (263.12 → 251.35 GB/s at
163 840). But the real `lmhead_int5_base_coarse_delta` dispatches **3,211,264
threads and achieves 259.8 GB/s = 97.5 % of 266.3 = 104.2 % of the derated
ceiling** — the decline does not reproduce in a real kernel and is a
partitioning artifact of the probe (fewer, longer per-thread walks stream
better). Removing the large-grid derating entirely leaves only the five families
launching 16 384 threads:

| tightened (P) | µs | % of `cs` |
|---|---:|---:|
| `oproj_act_h64` | 21.0 | 0.320 |
| `oproj_act_h48` | 5.3 | 0.081 |
| `shared_nvfp4_swiglu_qmv_rows1_halved` | 3.5 | 0.054 |
| `residual_rms_router` | 3.3 | 0.050 |
| `dense_down_residual` | 2.7 | 0.041 |
| **total** | **35.8** | **0.545** |

I report **1.548** as the primary number because the assignment asked for a
*defensible upper bound*, and 0.545 is the best estimate.

### 6.4 The one number

> **A defensible upper bound on decode time recoverable by improving DRAM
> bandwidth efficiency, holding the byte stream fixed, is 1.548 % of `cs`
> (101.6 µs/step). The best estimate is 0.545 % (35.8 µs/step). No single
> family reaches the 0.5 % effort bar; the record bar of 1.438 % is out of
> reach for this axis entirely.**

Against the assignment's baseline of 10.25, the delta is **−8.70**.

---

## 7. A5 — not completed, per the stopping rule

The assignment's stopping rule: *"no family ≥32.8 µs/step defensible surplus
after the A3 ceiling → fire **N-1** immediately and do not complete A5."* The
largest is 25.2 µs/step. A5 was therefore not performed and no kill-check table
is offered.

One consistency observation, explicitly **not** the A5 deliverable: an
`L`-dominated step is exactly the regime in which #558 (router weight prefetch)
could shave 6.39 µs/step of kernel label while running **34.58 µs/step slower
end to end** at p = 2⁻²⁰. Under a bandwidth-limited model that sign flip is
inexplicable; under `T = B/BW + L` it is ordinary. The same holds for #215's
BK=64 pipeline (+0.684 ms slower) and #40's null result.

---

## 8. Rule 82b — explicit admissibility verdict

**Verdict: A1 is admissible for the question it is used to answer, and would be
inadmissible for pricing a lever.**

Rule 82b exists because r93-C showed `SPLIT=1` inflates the **inter-dispatch
gap** by roughly 4.2× (302 → 1261 µs/step)
(`research/maple-fern-r105d-decode-dispatch-census.md:92-96`). That distortion
attacks *overlap between dispatches*. A1 asks a strictly within-kernel question:
bytes moved divided by time spent running. Three things support admitting it
here:

1. `Σ labels = 8528.3 µs` reproduces that session's own `gpu_busy_sum` of
   8528.0 µs to 0.3 µs. The labels are internally consistent as a partition of
   busy time.
2. Every A1 conclusion is a *ratio between families measured in the same
   session*. A uniform 7.4 % inflation cancels in the ranking and shifts each
   `pct_of_266_3` by the same factor.
3. The load-bearing numbers in §6 — `L4`, `L5`, the apportionment — use **wall
   and step times, not labels**. A1 supplies the per-family attribution; it does
   not supply the verdict.

Where a level (not a ratio) is quoted, I state the axis: §4.2 tabulates all
three M4 axes and uses the matched wall axis for every M4↔M5 comparison.

**If a reviewer rejects A1 anyway**, the admissible substitute is a same-session
non-SPLIT per-family attribution — either Metal counter sampling, or A/B
dispatch-elision timing per family under `--local-iterate` with a paired
unchanged baseline. That is Phase B work and outside this assignment. It would
not change the verdict: §6.1 rests entirely on wall/step times and the A3 probe,
neither of which involves a `SPLIT=1` label.

---

## 9. Outcome, restated

**N-1.** The 12.9-point M4→M5 DRAM-efficiency gap does not name a bounded
recoverable surplus.

* 18.8 % of the headline 10.25 % claim is a busy-versus-wall axis mismatch
  inside the assignment's own constants.
* 0 % is denominator or byte-model error: A3 measured the faithful access
  pattern at 98.0 % of the reference constant, and the byte census is exact
  against the compiled MSL for 85 % of step bytes.
* ≤15.1 % is genuine parallelism/occupancy headroom, capped at 1.548 % of `cs`
  and best-estimated at 0.545 %, with no single family clearing the 0.5 %
  effort bar.
* The remaining 66.2 % is `L`, a fixed non-DRAM component that **M5 has already
  reduced by 25 % relative to M4**. Transferring M4's `L` to M5 would make the
  ranked step 460 µs *slower*.

There is also an **N-3**-flavoured contradiction to record. The framing that M5
"extracts less of its peak" and therefore has recoverable bandwidth is
backwards: normalising for its own DRAM term, M5 is 6.7 efficiency points ahead
of what M4's behaviour predicts. Any future assignment that reasons from a
cross-generation *efficiency ratio* should first subtract the non-DRAM term on
both sides.

## 10. Suggested follow-ups (not implemented)

1. **The only bandwidth-shaped lever this audit found** is the five families
   that launch exactly 16 384 threads, worth ≤0.545 % of `cs` combined and
   dominated by `oproj_act_h64` at 0.320 %. On 40 cores that is 410 threads per
   core against a measured saturation point of 512. Widening the grid — or
   fusing the h64 and h48 variants into one dispatch — is a cheap, bounded,
   correctness-neutral test. It is below the effort bar individually and would
   need to be bundled.
2. **Probe M5 directly.** Every M5 number here is a projection from a 20-core
   curve. `research/fern_r105e_bw_probe.swift` runs in 5.7 s and needs no model
   weights; one M5 execution would replace the whole extrapolation and settle
   whether 610 GB/s is 98.8 %-reachable there too.
3. **Re-scope the residual.** `L5 = 1368.4 µs = 20.8 % of cs` is the real
   target, and it is a dispatch-count and dependency-chain quantity. The A1
   ledger already localises it: 13 `LATENCY`-regime families hold 0.705 % of
   bytes but 21.6 % of the label, and `prefill_router_tournament`,
   `gate_sp_h64`, `rmsbfloat16` and `residual_rms_router` alone are 888 µs of
   M4 label at 0.5–2.5 % of step bytes.
4. **Check the escape rate.** If `scale_bases[row]==0xFF` fires materially in
   the qkv and oproj families, the byte model under-counts scales by up to
   9.1 % on those rows. The transform metadata should be able to answer this
   offline without touching the runtime.

---

## Reproduce

```bash
xcrun swiftc -O research/fern_r105e_bw_probe.swift -o /tmp/fern105e && /tmp/fern105e
python3 research/fern_r105e_ledger.py
python3 research/fern_r105e_wandb_log.py
git diff --numstat 9274c2923e38c9bc3925cb6409fade962ad571de HEAD -- Sources Vendor   # empty
```

## Artifacts

| path | contents |
|---|---|
| `research/artifacts/fern-r105e/family-bandwidth-ledger.csv` | A1, 25 families, 19 columns |
| `research/artifacts/fern-r105e/pattern-bandwidth.json` | A3, 92 measurements |
| `research/fern_r105e_bw_probe.swift` | A3 probe source |
| `research/fern_r105e_ledger.py` | A1 ledger builder |
| `research/fern_r105e_wandb_log.py` | W&B publication |
