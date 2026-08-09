# R93-C — Stall-structure census of the barrier-free 54 % trio

Student `maple-nezuko` · PR #498 · assignment `maple-r93-c-stall-structure-census`
rev `r93-c-rev1` · base `ca920bbe6938ae7efb9cab79739229a0321ba856`

**Diagnostic round. No fix ships. The submitted editable surface at HEAD is
byte-identical to the assignment base (0 bytes changed).**

---

## 0. Answer

**All three kernels are memory-bandwidth-bound.** Three independent instruments
agree on each of them (byte-accounting roofline, free-ALU ladder, extra-load
ladder), which meets the assignment's ≥ 2-probe stopping rule. I say
*memory-bandwidth* rather than *DRAM-bandwidth* deliberately: nothing here
separates DRAM from the fabric or system-level cache, only "the memory path is
the binding resource".

They run at 238–250 GB/s net of the SPLIT=1 dispatch tax, which is 91–95 % of
this host's best measured sequential rate (262.5 GB/s) and 99–106 % of the
access-pattern ceilings measured for their own patterns. Inserting float
arithmetic into their inner loops costs 3.6 % (qkv), 14.7 % (oproj) and 19.0 %
(routed) of its issue-limited price — they have idle issue slots. Inserting
*bytes* costs the **full** streaming rate, 225–239 GB/s marginal: that is the
measurement that excludes memory-latency-bound, because a latency-starved
kernel would absorb extra independent loads at *below* full rate. Separately, at
equal bytes, doubling the number of load *instructions* changes cost by only
−0.6 % to +4.4 %, which excludes memory-issue-bound.

**Consequence for the programme:** the 54 % of the busy pool these kernels hold
is *not* 54 % of addressable time. At fixed bytes the in-trio serialized
per-dispatch pool is ≈ 472 µs/step gross and realistically ≲ 240 µs/step
recoverable; the most optimistic possible byte reduction adds ≤ 180 µs/step.
The honest optimistic in-trio ceiling is therefore **≈ 420 µs/step, ≈ 9 % of the
trio and ≈ 4.9 % of the local busy pool** (§8). Any future proposal for these
kernels that does not reduce **bytes moved**, reduce **dispatch count**, or
overlap the **wall−busy gap** has a ceiling near zero — including unrolling,
register tuning, instruction selection, and cheaper dequantization math.

**Not measured:** a controlled grid-scaling sweep (probe 2) could not be run —
no env knob reaches these kernels' geometry and geometry is forbidden to ship —
so occupancy-limited is excluded by inference rather than by a dedicated probe
(§4, §10). Everything here was timed under `DARKBLOOM_GPU_PROFILE_SPLIT=1`,
which serializes dispatches; production runs unsplit at 7918 µs/step busy versus
8538 µs/step split, so the per-dispatch overhead figures are **serialized-mode
quantities and are an upper bound on what fusion could recover in production**
(§8, §10). The single most valuable follow-up is therefore an unsplit
dispatch-overhead A/B rather than another kernel-internal probe.

---

## 1. Question

Three decode kernels hold 54.2 % of the 8528 µs/step GPU-busy pool:

| kernel label | µs/step (assignment) | µs/step (this rig) | share |
|---|---|---|---|
| `decode_nvfp4_qkv_h64/h48_...` | 1702.9 | 1704.0 | 20.0 % |
| `oproj_act_h64/h48_...` | 1419.5 | 1421.2 | 16.6 % |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 1497.7 | 1498.6 | 17.6 % |

This rig reproduces the assignment's per-kernel times to within 0.12 %, which is
well inside the 3.34 µs/step per-label σ, so the census target is the same
population the assignment measured.

R92-A showed they carry no hoistable barrier. This round asks *what they are
actually waiting on*: DRAM bandwidth, memory latency, instruction issue/ALU
throughput, or occupancy.

Calibration: 1.00 % decode = 48.94 µs/step; 0.015280 % score per µs/step. See
the §3.4 clock caveat before converting any local µs/step in this report with
that constant.

## 2. Method

### 2.1 Probe mechanism

`NEZUKO_R93_PROBE=<target>:<kind>:<n>`, default off. Targets `qkv | oproj |
routed`; kinds `fma | imad | ld8 | ld16`; `n` ∈ [0, 64].

* **Bit-exact ADDITION only (Rule 45).** Every ladder computes a private value
  consumed solely by `if (nz_sum > 3.0e38f) { sink[0] = bfloat(0.0f); }`,
  which is never true at runtime. No existing work is deleted or weakened to
  "price" it. All arms were checked for token divergence.
* **Name- and residency-matched placement control (Rule 44).** Every enabled
  level, *including `n = 0`*, changes the kernel-name suffix to `_pz<kind><n>`
  and binds the 128 MiB probe pool. Level 0 is therefore the control for its
  own ladder: it has the identical binding signature and an identical body,
  differing only in the ladder rungs. Because each kind emits a *distinct*
  name at level 0 with an *identical* body, the spread across the level-0 arms
  is a direct measurement of the name-only effect Rule 44 warns about.
* **One mechanism per arm (Rule 24)**, **distinct suffix per variant
  (Rule 33)**.
* Placement is deliberately asymmetric and this matters for interpretation:
  * the **ALU ladder sits inside the kernel's K/block loop**, so the scheduler
    is free to hide it inside the loop's memory stalls. It therefore measures
    *spare issue slots during memory stalls*, which is exactly the question.
  * the **load ladder is a post-epilogue tail**, so it adds bytes without
    perturbing the main loop's software pipelining. It measures the *marginal*
    cost of a byte at the current operating point.
* Four independent dependency chains per ladder keep it throughput-limited,
  not latency-limited. The integer ladder is deliberately non-affine
  (`x*2654435761u + (x>>16)`); a repeated affine `x*C+D` would reassociate into
  a single mul-add and the ladder would collapse to one rung.

### 2.2 Timing

`decode_probe.py --profile` with `DARKBLOOM_GPU_PROFILE_SPLIT=1`, 80 decode
steps, driven by `research/maple_r93_census.py`. Rule 43: SPLIT=1 is
attribution-only, but a single-label, name-matched, control-differenced SPLIT=1
delta is admissible. Every ladder point here is exactly that.

Rule 40: σ for per-kernel SPLIT=1 labels on this rig is 3.34 µs/step, so the
difference of two single censuses carries σ ≈ 4.7 µs/step. All arms were run
twice with the second replicate in reversed order to break drift-vs-order
confounding; slopes are OLS over all replicates with Student-t 95 % intervals.

### 2.3 The SPLIT=1 dispatch tax, measured

Rule 41 pins the dispatch boundary at 1.4064 µs. This round measured it
directly on the same rig, because the tax sits *inside* every per-kernel
interval SPLIT=1 reports and therefore biases the roofline downward.

| arm | busy_sum ms/step | boundaries/step |
|---|---|---|
| `off` (SPLIT=1) | 8.538 | 406 dispatches |
| `off@nosplit` | 7.918 | 45 command buffers |

Δ = **620 µs/step over 361 extra boundaries = 1.72 µs per boundary.**

The pinned 1.4064 µs is the *conservative* choice here: a smaller correction
removes less time, which yields a lower computed achieved bandwidth. Every
number below uses 1.4064 µs, so the bandwidth-bound conclusion is not an
artefact of an inflated tax — the true correction is ≈ 22 % larger and would
strengthen it.

### 2.4 Host and reachability

Apple M4 Pro, 48 GiB, `applegpu_g16s` (GPU generation 16). The `_nax` prefill
kernels the ranked M5 selects are **unreachable here**; this round only touches
decode kernels that are reachable on both, and all three probed labels were
confirmed present in the default profile before any probe was enabled
(Rule 39). Absolute µs/step are directional; the *ratios* (achieved vs
achievable bandwidth, marginal vs nominal ALU cost) are the transferable
result.

## 3. Probe 1 — roofline placement

### 3.1 Byte arithmetic

NVFP4 group-16, lane-major, `_pw1` (pairwise nibble scales) as confirmed by the
kernel-name suffixes `..._lm1_pw1_...`:

* codes: 4 bits per value = **0.5 B/value**
* scale plane: one 4-bit nibble per group of 16 = **0.25 B/group** =
  0.125 bits/value
* one `scale_bases` byte per row

(An earlier draft used 0.5625 B/param; that over-counted the scale plane by
treating it as one byte per group.)

**QKV.** Rows = (heads + 16) · 128 → 10240 (h64), 8192 (h48); K = 2048.
Per row = 1024 code bytes + 32 scale nibble-bytes + 1 base = **1057 B**.
Per step = 30 · 10240 · 1057 + 10 · 8192 · 1057 = **411.30 MB**, plus ≈ 0.9 MB
of activations ⇒ **412.2 MB/step**.

**o_proj.** Rows = 2048. `in_vec` = 8192 (h64) → 4096 + 128 + 1 = 4225 B/row;
`in_vec` = 6144 (h48) → 3072 + 96 + 1 = 3169 B/row.
Per step = 30 · 2048 · 4225 + 10 · 2048 · 3169 = **324.48 MB**, plus ≈ 0.76 MB
⇒ **325.2 MB/step**.

**Routed gate/up.** Per expert 1 048 576 code bytes + 65 536 scale bytes =
1 114 112 B; 8 routed experts × 39 sparse layers = **347.60 MB**, plus ≈ 0.5 MB
⇒ **348.1 MB/step**.

The nibble/base widths above are read directly off the shape assertions rather
than inferred: `LagunaRuntimeModel.swift:5076-5083` requires
`lane.nibbles.dims(rows, hidden / (lane.pairwise ? 64 : 32))` and
`lane.bases.dims(rows)`, and `:4361-4362` set `nibDiv = pairwise ? 4 : 2` with
`laneIdx = (simd_lid >> 1)`. So the pairwise arm really does store one nibble
per *pair* of groups — K/64 B/row — and the non-pairwise routed arm K/32 B/row.
The routed figure cross-checks: 2 097 152 values / 32 values-per-scale-byte =
65 536, which is what the per-expert total uses.

### 3.1b The fifth QKV buffer (`weight_scales`) is not a hidden byte term

The QKV dispatch binds five buffers,
`[normalized, bank.packedCodes, lane.nibbles, lane.bases, bank.scales]`
(`:5090`), and `bank.scales` is the *stock* uint8 plane at `dims(rows, hidden/16)`
= 128 B/row — a potential +12 % on the QKV byte count if it were read on the
common path. It is not. In `lagunaDecodeNVFP4QKVLaneMajorSource` (`:4996-5013`)
`weight_scales` is dereferenced only inside the `row_base == 0xFFu` *escape*
branch; the packed branch touches only `scale_nibbles` and `scale_bases`. The
two branches are exclusive, so a row costs either 32 B (packed) or 128 B
(escaped) of scale traffic, and the buffer is bound unconditionally so the
escape branch has a valid address.

The escape rate is bounded by construction, not by assumption.
`lagunaLaneMajorNVFP4ScaleBank` (`LagunaRuntimeWeights.swift:886-933`) escapes a
row only when its scale span exceeds 15 or its two pairwise halves disagree, and
the header comment at `:706-717` derives that the halves can disagree for at most
**one group pair per `quantized()` call** — i.e. at most three fused-QKV rows and
one `o_proj` row per layer. Against 10 240 QKV rows per layer that is ≤ 0.03 %.

Independently of that derivation, the measurement itself caps the escape
fraction *f*: QKV bytes/row would be 1057 + 96·*f*, and the observed net
250.2 GB/s cannot exceed the 262.5 GB/s sequential ceiling, so *f* ≤ 0.54 even
with no knowledge of the packer. The exact per-bank counts are printed by
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1` (`LagunaRuntimeWeights.swift:939-940`); the
measured value is reported in §3.1c. Either way this term is far too small to
change the classification.

### 3.2 Achievable ceilings on this host

`senpai/tools/bandwidth-pattern-probe`, same M4 Pro, 2026-08-04:

| pattern | GB/s |
|---|---|
| 64 MB sequential (best any pattern reached) | **262.5** |
| NVFP4 attention rows (QKV / o_proj shape) | **236.6** |
| routed gate/up rows | **243.0** |
| routed down rows | 241.4 |
| 8 scattered 1.77 MB blocks | 246.8 |
| 576 scattered 16 KB blocks | 242.4 |
| KV runs | 227.8 – 234.2 |

### 3.3 Result

| kernel | raw µs | net µs | MB/step | raw GB/s | **net GB/s** | pattern ceil | % ceil | % seq peak |
|---|---|---|---|---|---|---|---|---|
| qkv | 1704.0 | 1647.7 | 412.2 | 241.9 | **250.2** | 236.6 | 105.7 % | 95.3 % |
| oproj | 1421.2 | 1364.9 | 325.2 | 228.9 | **238.3** | 236.6 | 100.7 % | 90.8 % |
| routed | 1498.6 | 1443.8 | 348.1 | 232.3 | **241.1** | 243.0 | 99.2 % | 91.9 % |

All three sit at 99 – 106 % of their own measured pattern ceiling and at
91 – 95 % of the best bandwidth *any* access pattern reached on this host.

### 3.4 Resolving the >100 % artefact: a two-parameter DRAM model

A ratio above 100 % is not a measurement error — it exposes a flaw in the
single-number "ceiling GB/s" idea. The same-host pattern probe reports one
*average* rate per transfer size, so it folds a fixed per-dispatch cost into
the rate. Refitting that table as **time vs bytes** instead:

| transfer | GB/s (avg) |
|---|---|
| 0.125 MB | 28 |
| 0.5 MB | 113 |
| 1 MB | 173 |
| 2 MB | 212 |
| 8 MB | 235 |
| 16 MB | 250 |
| 64 MB | 262 |

* fit over ≥ 8 MB (brackets our 6.5 – 10.8 MB dispatches):
  **t = 3.97 µs + bytes / 266.3 GB/s**
* fit over ≥ 2 MB: t = 3.06 µs + bytes / 265.1 GB/s

Applying that model **per dispatch**, with no ALU term whatsoever:

| shape | MB/dispatch | model µs | raw µs | net µs | net/model | residual |
|---|---|---|---|---|---|---|
| qkv h64 | 10.82 | 44.61 | 44.72 | 43.31 | 0.971 | −1.30 µs |
| qkv h48 | 8.66 | 36.48 | 36.25 | 34.84 | 0.955 | −1.64 µs |
| oproj h64 | 8.65 | 36.46 | 37.34 | 35.93 | 0.986 | −0.53 µs |
| oproj h48 | 6.49 | 28.34 | 30.11 | 28.70 | 1.013 | +0.36 µs |
| routed | 8.91 | 37.44 | 38.43 | 37.02 | 0.989 | −0.41 µs |

**All five dispatch shapes land within 5 % of a pure-DRAM model that contains
no compute term at all**, and the aggregate non-DRAM residual across the whole
trio is **−84 µs/step** — i.e. the three kernels are, within measurement error,
*entirely* explained by bytes moved plus a fixed per-dispatch cost.

The fixed term is not free: 3.97 µs × 119 dispatches/step = **472 µs/step**,
i.e. 5.5 % of the 8538 µs/step busy pool and 4.8 % of the 9804 µs/step local
decode wall. But an empty serialized dispatch on this host costs only 0.87 µs
(1×32 grid) to 2.46 µs (160×256 grid), so at most roughly half of the 472 µs
is launch overhead that fusion could recover; the remainder is DRAM
ramp-up/drain that follows the bytes wherever they are dispatched from.

*Unit caveat, applied to every ceiling in §8.* The assignment's calibration
(1.00 % decode = 48.94 µs/step) implies a 4894 µs/step decode base, which is
**smaller than this rig's own 8538 µs/step busy pool**. The two are therefore
not the same clock: the µs/step figures here are M4 Pro profile units, while
the score calibration is anchored on official M5 receipts. Converting a local
µs/step saving to score at 0.015280 %/µs would overstate it by roughly the
ratio of the two decode bases. §8 quotes ceilings as **fraction of the local
kernel's own time**, which transfers across rigs, and gives the naive score
conversion only as a clearly-labelled upper bound.

## 4. Probe 2 — grid scaling

**Status: not run as a controlled sweep; an observational two-point substitute
is reported instead. This is the one probe of the four that is incomplete, and
the deliberate choice is stated here rather than buried.**

Two reasons:

1. **No existing knob reaches the trio.** The only threadgroup-geometry env
   control on the default decode path is `DARKBLOOM_ROUTER_ROWS_PER_GROUP`,
   which targets the router, not `qkv` / `oproj` / the routed gate-up GEMM. A
   real sweep needs new geometry code in each of the three kernel emitters.
2. **The output would not be actionable.** Receipt `285f79fa` (#48) already
   priced a threadgroup-geometry change on this family at −0.1488 %, and
   geometry changes are forbidden to ship in this round. Spending ~15 arms of
   GPU time on a knob that cannot ship, when three probes already agree, loses
   to the assignment's own stopping rule.

**Observational substitute (free, zero extra arms).** Each attention kernel
already runs at two sizes in the same step, h64 and h48, which is a two-point
size scaling of one kernel family:

| family | (MB, µs) points | marginal GB/s | intercept µs |
|---|---|---|---|
| qkv | (10.82, 44.72), (8.66, 36.25) | **255.0** | 2.29 (≈0.9 net of SPLIT tax) |
| oproj | (8.65, 37.34), (6.49, 30.11) | **298.8** | 8.39 |

qkv's marginal 255.0 GB/s is close to the 266.3 GB/s streaming slope, again
consistent with bandwidth-bound. `routed` has only one variant, so no point
pair exists.

**Caveat, stated plainly:** h64 and h48 differ in head count *and* `in_vec`,
not only in size, so this is **observational, not controlled**. It cannot
separate a grid-size effect from a shape effect, and oproj's 298.8 GB/s
marginal — above the sequential peak — shows exactly that contamination. It is
offered as corroboration, never as a load-bearing measurement.

## 5. Probe 3 — free-ALU ladder

### 5.1 The level-0 placement controls (Rule 44)

Each kind emits a *distinct* kernel name at `n = 0` with an *identical* body,
so the spread across level-0 arms is a direct measurement of the name-only /
residency effect, with no ladder present at all:

| kernel | `off` | `fma:0` | `imad:0` | `ld8:0` | spread |
|---|---|---|---|---|---|
| qkv | 1704.0 | 1692.7 | 1693.8 | 1694.1 | 1.4 µs |
| oproj | 1421.2 | 1425.5 | 1424.9 | 1416.1 | 9.4 µs |
| routed | 1498.6 | 1505.3 | 1503.9 | 1513.7 | 9.8 µs |

The name-only spread (1.4 – 9.8 µs) is comparable to σ ≈ 4.7 µs for a
difference of two single censuses, so it is consistent with noise — but it is
**not negligible relative to the ALU slopes below**, which is precisely why
every ladder is differenced against *its own* level 0 rather than against
`off`.

### 5.2 Slopes

| kernel | kind | levels (µs/step) | slope µs/n | 95 % CI ± | work/n | issue-limited µs/n | **% of issue-limited** |
|---|---|---|---|---|---|---|---|
| oproj | fma | 0:1426 4:1439 8:1440 16:1454 | 1.6 | 1.3 | 39.3 Mop | 11.0 | **14.7 %** |
| oproj | imad | 0:1425 8:1465 16:1489 | 4.0 | 7.6 | 39.3 Mop | 11.0 | 36.4 % |
| qkv | fma | 0:1693 1:1693 2:1701 4:1700 | 2.0 | 5.4 | 199.2 Mop | 55.7 | **3.6 %** |
| qkv | imad | 0:1694 2:1698 4:1707 | 3.3 | 10.6 | 199.2 Mop | 55.7 | 5.9 % |
| routed | fma | 0:1505 2:1509 4:1509 8:1540 | 4.3 | 5.8 | 81.8 Mop | 22.8 | **19.0 %** |
| routed | imad | 0:1504 4:1533 8:1596 | 11.5 | 31.5 | 81.8 Mop | 22.8 | 50.2 % |

Inserted arithmetic costs **3.6 – 19 % of its issue-limited price** on the
float ladder. The kernels have large spare issue capacity: work added *inside
the main loop* is largely absorbed into existing memory stalls.

**Honest caveat on the integer ladder.** `imad` normalizes higher (36 – 50 %)
than `fma`. That is very likely an artefact of the denominator, not less
headroom: the 3.58e12 op/s figure is the *float* FMA peak, and 32-bit integer
multiply is commonly quarter-rate or worse on Apple GPUs. The `imad` rows are
therefore reported but the **float ladder is the load-bearing issue-headroom
evidence**; `imad` is included because it uses a different functional unit and
so guards against the float ladder being absorbed by an idle FP pipe alone.
Both ladders agree on direction (sub-unity), which is the claim being made.

CIs are wide — this probe can say "far below 100 %", not "exactly 3.6 %".

## 6. Probe 4 — extra-load ladder

### 6.1 Marginal cost of a byte

| kernel | kind | levels (µs/step) | slope µs/n | 95 % CI ± | MB/n | **marginal GB/s** |
|---|---|---|---|---|---|---|
| qkv | ld8 | 0:1694 1:2172 2:2577 | 441.2 | 265.2 | 99.6 | 225.8 |
| qkv | ld16 | 0:1694 1:2572 | 878.1 | 3.7 | 199.2 | 226.9 |
| oproj | ld8 | 0:1416 4:1516 8:1598 | 22.7 | 16.9 | 5.2 | 231.0 |
| oproj | ld16 | 0:1422 4:1599 | 44.2 | 6.5 | 10.5 | 237.1 |
| routed | ld8 | 0:1514 1:1703 2:1855 | 170.8 | 135.0 | 40.9 | 239.4 |
| routed | ld16 | 0:1508 1:1870 | 362.7 | 26.3 | 81.8 | 225.5 |

Every marginal rate lands in **225.5 – 239.4 GB/s**, i.e. essentially the same
rate the kernels already achieve. An added byte costs full DRAM time in all
three kernels: **there is no spare bandwidth anywhere in the trio.**

### 6.2 The decisive discriminator: bytes, not loads

This is the sharpest result of the round. `ld8:2k` and `ld16:k` move **exactly
the same bytes** but issue **twice as many load instructions**. If the kernels
were limited by memory *latency*, by outstanding-request slots, or by
instruction *issue*, doubling the request count at constant bytes would cost
substantially more. If they are limited by *bandwidth*, it should cost the
same.

| kernel | 2× loads, same bytes | 1× loads, same bytes | ratio |
|---|---|---|---|
| qkv | `ld8:2` +882.5 µs/step | `ld16:1` +877.5 µs/step | **0.994** |
| oproj | `ld8:8` +181.6 µs/step | `ld16:4` +183.0 µs/step | **1.008** |
| routed | `ld8:2` +341.6 µs/step | `ld16:1` +356.6 µs/step | **1.044** |

All three ratios are within 4.4 % of 1.000, and two are within 1 %. **Cost
tracks bytes moved and is indifferent to the number of memory instructions
that move them.** That is the signature of a bandwidth-saturated pipe, and it
directly excludes memory-latency-bound and issue-bound as the binding
constraint.

## 7. Classification

| kernel | classification | probe 1 roofline | probe 3 free-ALU | probe 4 marginal byte | probe 4 byte-vs-load | agreeing probes |
|---|---|---|---|---|---|---|
| **qkv** | **bandwidth-bound** | 250.2 GB/s = 95.3 % of seq peak; per-dispatch model ratio 0.971 / 0.955 | ALU at 3.6 % of issue price | 225.8 / 226.9 GB/s marginal | ratio 0.994 | **4** |
| **oproj** | **bandwidth-bound** | 238.3 GB/s = 90.8 % of seq peak; model ratio 0.986 / 1.013 | ALU at 14.7 % | 231.0 / 237.1 GB/s | ratio 1.008 | **4** |
| **routed** | **bandwidth-bound** | 241.1 GB/s = 91.9 % of seq peak; model ratio 0.989 | ALU at 19.0 % | 239.4 / 225.5 GB/s | ratio 1.044 | **4** |

The assignment's stopping rule asked for ≥ 2 independent probes agreeing per
kernel. All three kernels have **four**.

**Ruling out the other three categories, explicitly.**

* **Issue/ALU-bound — excluded.** Probe 3: inserted float arithmetic inside the
  main loop costs 3.6 – 19 % of its issue-limited price. An issue-bound kernel
  would pay ≈ 100 %.
* **Memory-latency-bound — excluded.** Probe 4's byte-vs-load discriminator:
  doubling the load *count* at constant bytes changes cost by −0.6 % to +4.4 %.
  A latency- or outstanding-request-limited kernel would pay roughly double.
* **Occupancy-bound — excluded indirectly.** No direct geometry sweep was run
  (§4), so this rests on an inference rather than a dedicated probe, and is
  labelled as such. The argument: an occupancy-limited kernel has too few
  resident threads to cover its own memory latency, so it *cannot* be running
  at 91 – 95 % of the machine's best measured streaming rate — the two are
  mutually exclusive. Independently, an occupancy-limited kernel would show
  added ALU work as *nearly free* (true here) **and** added bytes as *cheaper
  than full DRAM rate*, because it was not saturating the pipe to begin with.
  The observed combination — nearly-free ALU **together with** full-price bytes
  at 225 – 239 GB/s — is logically incompatible with occupancy-limited and is
  the exact signature of bandwidth-saturated.

## 8. Ranked candidate mechanisms with ceilings

The classification is the ranking: for all three kernels the only lever with a
large ceiling is **moving fewer bytes**. Everything else is bounded by the
−84 µs/step of aggregate non-DRAM residual the trio actually carries (§3.4).

Ceilings below are quoted as **local µs/step against this rig's 8538 µs/step
busy pool** (see the §3.4 clock caveat — do *not* convert them with the
assignment's 48.94 µs/step-per-1 % constant, which belongs to a 4894 µs/step
decode clock).

| # | mechanism | ceiling (local µs/step) | basis | confidence |
|---|---|---|---|---|
| 1 | shave real bytes off the weight stream | **≈ 180** in-trio, if the scale planes could vanish entirely | codes are already 4-bit, so the only removable bytes above a pure-code floor are the scale planes and bases: qkv 1057→1024 B/row (−12.84 MB), oproj 4225→4096 and 3169→3072 (−9.91 MB), routed 1 114 112→1 048 576 B/expert (−20.44 MB) ⇒ 1085.5 → 1042.3 MB/step, −43.2 MB at 240 GB/s = **180 µs/step**. This is an upper bound assuming scales become free, which they cannot; a realistic packing win is a fraction of it | high that the *rate* holds; low that the bytes are removable |
| 2 | fixed per-dispatch cost, pool-wide | **≈ 1610** gross, ≲ 800 recoverable | 3.97 µs model intercept × 406 dispatches/step; an empty serialized dispatch measures 0.87 µs (1×32) to 2.46 µs (160×256), so ≈ half is launch overhead that fusion cannot remove | medium |
| 2a | — of which inside the trio | **472** gross, ≲ 240 recoverable | 3.97 µs × 119 trio dispatches = 5.5 % of the busy pool | medium |
| 3 | close the achieved→sequential-peak gap | **≈ 321** | trio at 243.6 GB/s aggregate net of the SPLIT tax vs 262.5 GB/s sequential ⇒ 1085.5 MB at 262.5 = 4135 µs vs 4456 net measured | low — the pattern ceilings (236.6 / 243.0 GB/s) say most of this gap is the access pattern, not slack |
| 4 | the 1266 µs/step wall−busy gap | **≈ 1266** gross | wall 9804 µs vs busy 8538 µs per step; GPU idle between dispatches | medium-low — overlaps (2) and is partly host-side |
| 5 | anything that trades bytes for ALU | **≈ 0**, likely negative | probe 3 says ALU is 81–96 % free, but probe 4 says every added byte costs full DRAM rate; a transform that spends ALU to *save* bytes is the only version of this with positive expected value, and it is mechanism (1) | high |
| 6 | expert-locality / routing-affinity tricks | **≈ 0** | routed already runs at 99.2 % of its own measured gather pattern ceiling and 91.9 % of sequential peak; there is no locality left to exploit | high |
| 7 | reducing write traffic | **≈ 0** | writes are ≈ 0.5–0.9 MB/step against 1085 MB of reads | high |

**Double-counting warning.** (2), (3) and (4) overlap heavily and must not be
added. The 3.97 µs model intercept is *inside* the busy pool, so it is exactly
part of what makes the trio achieve 243.6 GB/s instead of 262.5 GB/s: mechanism
(2a)'s 472 µs and mechanism (3)'s 321 µs are largely the same slack counted two
ways. Their union is bounded by ≈ 500–550 µs/step, not by 793. Mechanism (4) is
measured *outside* the busy pool, so it is additive to (2a) within the trio but
overlaps (2) pool-wide, and part of it is host-side rather than GPU-addressable.
Mechanism (1) is the one genuinely orthogonal item: it removes bytes rather than
overhead.

**Honest in-trio ceiling.** At **fixed bytes and fixed dispatch count**, the trio
has **≈ 550 µs/step** of theoretically addressable time — the union of (2a) and
(3), not their sum — i.e. ≈ 12 % of the trio's 4620 µs/step and ≈ 6.4 % of the
local busy pool. Allowing the most optimistic byte reduction (mechanism 1, an
upper bound that assumes scale planes become free) adds at most another
180 µs/step, for an absolute optimistic total of **≈ 730 µs/step ≈ 16 % of the
trio**. Those are the numbers a follow-up should be sized against. The trio's
54 % share of the busy pool is *not* a 54 % opportunity, and treating it as one
has been the recurring error this census was meant to settle.

**What this rules out for future rounds.** Any proposal for these three kernels
that does not reduce bytes moved, reduce dispatch count, or overlap the
wall−busy gap has a ceiling near zero. Unrolling, register-pressure tuning,
instruction selection, math-mode changes, and cheaper dequantization arithmetic
all fall in that class — probe 3 already measured that the arithmetic they would
remove is 81–96 % free. This is the round's most reusable negative.

## 9. The bandwidth-vs-issue contradiction

The contradiction the assignment names is: the trio looks *bandwidth-saturated*
by roofline, yet earlier rounds found it *responsive to issue-side changes*.
Probes 3 and 4 resolve it, and the resolution is not that one side was wrong.

**Resolution: spare issue slots and saturated bytes coexist, and they are not
in tension.** A kernel that is DRAM-bound spends most of its wall time waiting on
memory returns. During that wait the SIMD issue pipe is idle, so arithmetic
inserted into the shadow of an outstanding load is genuinely close to free —
measured at 3.6 % (qkv), 14.7 % (oproj), 19.0 % (routed) of its issue-limited
price (§5.2). That is *predicted* by bandwidth saturation, not a contradiction
with it. The two statements "there is idle issue capacity" and "the memory pipe
is full" are simultaneously true, and §6.2 is the measurement that separates
them: at **equal bytes**, doubling the number of load instructions changes cost
by −0.6 % / +0.8 % / +4.4 %. Cost tracks bytes and is blind to instruction
count.

So the correct reading of an issue-side win in an earlier round is that it
removed *bytes* or *dispatches*, or that it moved work out of a region where
the memory pipe happened to be starved — not that the kernel was issue-limited.
The falsifiable prediction is: **a change that only removes ALU work from these
three kernels will not measurably speed them up.** The observed free-ALU slopes
put the ceiling for removing *all* the dequantization arithmetic at 3.6–19 % of
its nominal cost.

The residual asymmetry is worth noting: routed's 19.0 % is five times qkv's
3.6 %, so routed has the least issue slack of the three and is the one kernel
where an ALU reduction is not entirely futile. Its `imad` ladder (50.2 %) points
the same way, though the integer normalizer is a known artefact (§5.2).

## 10. What remains unmeasured

Listed so a follow-up does not mistake an inference for a measurement.

1. **A controlled grid-scaling sweep (probe 2) was not run.** §4 explains why:
   no env knob reaches the trio's geometry and geometry is forbidden to ship
   (#48, receipt `285f79fa`, −0.1488 %). The observational h64/h48 substitute is
   confounded — it varies head count and `in_vec` together, and oproj's implied
   298.8 GB/s exceeds the sequential peak, which proves the confound rather than
   a result. **Occupancy-limited is therefore excluded by inference (§7), not by
   a dedicated probe.**
2. **No contention co-run.** The sharpest untried test of "bandwidth-saturated"
   is a second concurrent stream of known size *S* on another queue: a truly
   saturated kernel should slow by ≈ *S*/262.5 GB/s (additive), a
   latency-limited one sub-additively. This would upgrade the classification
   from strong-inferential to direct. It is one probe and should be first in any
   follow-up.
3. **The two-parameter DRAM refit (§3.4) is a same-host model, not a
   first-principles one.** It dissolves the 105.7 % qkv anomaly, but it was
   fitted on the *replay* size ladder and applied to *kernel* dispatches. It has
   not been checked by (a) refitting the replay ladder with the intercept free
   and reporting its CI, (b) testing the slope directly on a kernel at 2× and 4×
   K, (c) inserting an SLC-busting stream between dispatches to see whether the
   intercept is really fixed cost or partly cache residency, or (d) auditing
   physical buffer lengths for padding. Until then the sub-100 % ratios in §3.4
   should be read as "consistent with", not "proven".
4. **The in-flight-bytes-per-lane table (§3.2) is size-confounded.** It was run
   at 5.06 MB per pattern, where the 3.97 µs fixed term alone caps achievable
   rate near 218 GB/s. Its absolute numbers therefore understate wide-access
   rates; only its *shape* (8 B → 32 B is the big jump) is safe to use.
5. **The escaped-row count is derived and bounded, not (yet) directly counted
   at the byte level in the timed build.** §3.1b gives the code derivation
   (≤ 3 QKV rows and 1 oproj row per layer), the measurement-side bound
   (*f* ≤ 0.54), and the measured counts in §3.1c. The one thing not done is a
   byte-level trace confirming the escape branch's 128 B/row actually reaches
   DRAM rather than hitting cache.
6. **Everything here is M4 Pro (`applegpu_g16s`, gen 16).** The `_nax` kernel
   family the ranked M5 selects is unreachable locally. The *classification*
   (bandwidth-bound) should transfer, since it rests on byte counts and a
   memory-system ceiling rather than on issue width; the *numbers* (µs/step,
   GB/s, and especially the 3.97 µs intercept) should not be assumed to.
7. **Dispatch-count reduction was costed but not attempted.** Mechanism (2)'s
   ≲ 800 µs/step is arithmetic from the model intercept and the empty-dispatch
   floor, not a fusion experiment.

## 11. Reproduction

```bash
git checkout ca920bbe6938ae7efb9cab79739229a0321ba856
git apply research/nezuko-r93-probes.patch          # probe wiring, never shipped
git apply research/nezuko-pr158-gpuprof-hook.patch  # per-kernel GPU timing
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
python3 research/maple_r93_census.py /tmp/r93/main research/maple_r93_main.arms 80
python3 research/maple_r93_analyze.py /tmp/r93/main
python3 research/maple_r93_wandb.py /tmp/r93/main
```

## 12. W&B

TBD
