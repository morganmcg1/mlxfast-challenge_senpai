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

They run at 237–248 GB/s net of the SPLIT=1 dispatch tax, which is 90–95 % of
this host's best measured sequential rate (262.5 GB/s) and 99–105 % of the
access-pattern ceilings measured for their own patterns. Inserting float
arithmetic into their inner loops costs 3.5 % (qkv), 15.4 % (oproj) and 16.5 %
(routed) of its issue-limited price — they have idle issue slots. Inserting
*bytes* costs the **full** streaming rate, 227–240 GB/s marginal: that is the
measurement that excludes memory-latency-bound, because a latency-starved
kernel would absorb extra independent loads at *below* full rate. Separately, at
equal bytes, doubling the number of load *instructions* changes cost by only
−2.6 % to +0.5 %, which excludes memory-issue-bound.

**Consequence for the programme:** the 54 % of the busy pool these kernels hold
is *not* 54 % of addressable time. At fixed bytes the in-trio serialized
per-dispatch pool is ≈ 472 µs/step gross and realistically ≲ 240 µs/step
recoverable; the most optimistic possible byte reduction adds ≤ 180 µs/step.
The honest optimistic in-trio ceiling is therefore **≈ 420 µs/step, ≈ 9 % of the
trio and ≈ 4.9 % of the local busy pool** (§8). Any future proposal for these
kernels that does not reduce **bytes moved**, reduce **dispatch count**, or
overlap the **wall−busy gap** has a ceiling near zero — including unrolling,
register tuning, instruction selection, and cheaper dequantization math. The
wall−busy gap is itself smaller than it looks: 1261 µs/step under SPLIT=1 but
only **302 µs/step** in the `off@nosplit` control (§8).

**Not measured:** a controlled grid-scaling sweep (probe 2) could not be run —
no env knob reaches these kernels' geometry and geometry is forbidden to ship —
so occupancy-limited is excluded by inference rather than by a dedicated probe
(§4, §10). Everything here was timed under `DARKBLOOM_GPU_PROFILE_SPLIT=1`,
which serializes dispatches; production runs unsplit at 7940 µs/step busy versus
8582 µs/step split, so the per-dispatch overhead figures are **serialized-mode
quantities and are an upper bound on what fusion could recover in production**
(§8, §10). The single most valuable follow-up is therefore an unsplit
dispatch-overhead A/B rather than another kernel-internal probe.

---

## 1. Question

Three decode kernels hold 54.2 % of the 8528 µs/step GPU-busy pool:

| kernel label | µs/step (assignment) | µs/step (this rig, rep 1) | µs/step (this rig, mean) | share |
|---|---|---|---|---|
| `decode_nvfp4_qkv_h64/h48_...` | 1702.9 | 1704.0 | 1715.6 | 20.0 % |
| `oproj_act_h64/h48_...` | 1419.5 | 1421.2 | 1428.9 | 16.6 % |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 1497.7 | 1498.6 | 1508.2 | 17.6 % |

The **first** `off` census reproduces the assignment's per-kernel times to within
0.12 %, well inside the 3.34 µs/step per-label σ, so the census target is the
same population the assignment measured. The **second** `off` census, run 48
minutes later at the end of the arm list, is 1.0 % slower pool-wide (busy 8.627
vs 8.538 ms/step; qkv 1727.2 vs 1704.0). That drift is larger than σ and is
exactly why the replicate order is reversed: every slope in this report is an OLS
fit over both replicates, so a monotone drift enters as noise on the intercept
rather than as a spurious slope. All absolute µs/step quoted below are
two-replicate means, which is why they sit ≈ 0.7 % above the assignment's.

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

| arm | busy_sum ms/step (mean of 2) | boundaries/step |
|---|---|---|
| `off` (SPLIT=1) | 8.582 | 406 dispatches |
| `off@nosplit` | 7.940 | 45 command buffers |

Δ = **642 µs/step over 361 extra boundaries = 1.78 µs per boundary.**

The pinned 1.4064 µs is the *conservative* choice here: a smaller correction
removes less time, which yields a lower computed achieved bandwidth. Every
number below uses 1.4064 µs, so the bandwidth-bound conclusion is not an
artefact of an inflated tax — the measured correction is ≈ 27 % larger and would
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
248.4 GB/s cannot exceed the 262.5 GB/s sequential ceiling, so *f* ≤ 0.62 even
with no knowledge of the packer. The exact per-bank counts are printed by
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1` (`LagunaRuntimeWeights.swift:939-940`); the
measured value is reported in §3.1c. Either way this term is far too small to
change the classification.

### 3.1c Measured escape counts

`research/maple_r93_escape_audit.py` runs the timed build with
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1` and parses every bank's escape line:

| bank | escaped rows | total rows | escape rate | packed B/row | escaped B/row | Δ bytes/row weighted |
|---|---|---|---|---|---|---|
| qkv (lane-major pairwise) | 2 543 | 389 120 | **0.654 %** | 1057 | 1152 | +0.62 (+0.06 %) |
| oproj (lane-major pairwise) | 1 563 | 81 920 | **1.908 %** | 4225 (h64) | 4608 | +7.3 (+0.17 %) |

An escaped row swaps its 32 B nibble plane + 1 B base for the 128 B (qkv) /
512 B (oproj h64) stock `weight_scales` row, so the byte penalty is +95 B/row
(qkv) and +383 B/row (oproj h64). Weighted by the measured escape rates that is
**+0.24 MB/step on qkv and +0.56 MB/step on oproj — +0.07 % on the trio's
1085.5 MB/step**, which moves the achieved rates from 248.4 → 248.5 GB/s (qkv)
and 236.9 → 237.3 GB/s (oproj). Every table below uses the packed-only byte
counts; this is the size of the error that introduces.

**The code derivation in §3.1b was too optimistic, and this is the honest
correction.** The `:706-717` header comment bounds only the *pairwise-halves
disagree* escape cause (≤ 3 QKV and ≤ 1 oproj row per layer). The measured rates
are ≈ 64 QKV and ≈ 39 oproj rows per layer, i.e. 20–40× that bound, so the
*scale-span > 15* cause at `:886-933` dominates and was not bounded by the
comment. The independent measurement-side cap (*f* ≤ 0.62) still holds with
enormous margin, and the classification is unaffected — but a future round that
wants to *exploit* the packed representation should size it against 0.65 % / 1.9 %
escapes, not 0.03 %.

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
| qkv | 1715.6 | 1659.3 | 412.2 | 240.3 | **248.4** | 236.6 | 105.0 % | 94.6 % |
| oproj | 1428.9 | 1372.6 | 325.2 | 227.6 | **236.9** | 236.6 | 100.1 % | 90.3 % |
| routed | 1508.2 | 1453.4 | 348.1 | 230.8 | **239.5** | 243.0 | 98.6 % | 91.2 % |

All three sit at 99 – 105 % of their own measured pattern ceiling and at
90 – 95 % of the best bandwidth *any* access pattern reached on this host. The
trio aggregate is 1085.5 MB in 4485.3 µs net = **242.0 GB/s**.

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
| qkv h64 | 10.82 | 44.61 | 45.02 | 43.61 | 0.977 | −1.00 µs |
| qkv h48 | 8.66 | 36.48 | 36.52 | 35.11 | 0.962 | −1.38 µs |
| oproj h64 | 8.65 | 36.46 | 37.53 | 36.12 | 0.991 | −0.34 µs |
| oproj h48 | 6.49 | 28.34 | 30.30 | 28.89 | 1.020 | +0.55 µs |
| routed | 8.91 | 37.44 | 38.67 | 37.27 | 0.995 | −0.17 µs |

**All five dispatch shapes land within 4 % of a pure-DRAM model that contains
no compute term at all**, and the aggregate non-DRAM residual across the whole
trio is **−55 µs/step** — i.e. the three kernels are, within measurement error,
*entirely* explained by bytes moved plus a fixed per-dispatch cost.

The fixed term is not free: 3.97 µs × 119 dispatches/step = **472 µs/step**,
i.e. 5.5 % of the 8582 µs/step busy pool and 4.8 % of the 9843 µs/step local
decode wall. But an empty serialized dispatch on this host costs only 0.87 µs
(1×32 grid) to 2.46 µs (160×256 grid), so at most roughly half of the 472 µs
is launch overhead that could be recovered by issuing fewer, larger dispatches;
the remainder is DRAM ramp-up/drain that follows the bytes wherever they are
dispatched from.

**This intercept is a SPLIT=1 quantity.** It was fitted on a serialized replay
ladder and applied to serialized kernel dispatches, and production runs unsplit
(§2.3: 7940 vs 8582 µs/step busy). Some of the 3.97 µs is per-dispatch cost that
the unsplit scheduler already overlaps with neighbouring work. **Every
overhead-recovery figure derived from it in §8 is therefore an upper bound on
what a fusion or batching change could recover in production**, not a prediction
of it. The measurement that would replace this bound with a fact is an unsplit
dispatch-count A/B (§10).

*Unit caveat, applied to every ceiling in §8.* The assignment's calibration
(1.00 % decode = 48.94 µs/step) implies a 4894 µs/step decode base, which is
**smaller than this rig's own 8582 µs/step busy pool**. The two are therefore
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
| qkv | 1715.6 | 1693.2 | 1693.8 | 1694.3 | 1.1 µs |
| oproj | 1428.9 | 1424.5 | 1425.5 | 1416.1 | 9.4 µs |
| routed | 1508.2 | 1504.7 | 1504.6 | 1506.7 | 2.1 µs |

The name-only spread (1.1 – 9.4 µs) is comparable to σ ≈ 4.7 µs for a
difference of two single censuses, so it is consistent with noise — but it is
**not negligible relative to the ALU slopes below**, which is precisely why
every ladder is differenced against *its own* level 0 rather than against
`off`.

The `off`-to-level-0 offset is a separate and larger effect: qkv's level-0 arms
run **22 µs/step faster than `off`** (≈ 5σ, and consistent across all three
kinds), oproj's ≈ 5 µs faster, routed's ≈ 3.5 µs faster. Binding a sixth buffer
and changing the kernel name is not free and is not zero-mean — which is Rule
44's point, empirically confirmed here at 1.3 % of a kernel's time. Any SPLIT=1
delta in this report that were differenced against `off` instead of against its
own level 0 would carry that 22 µs as bias; none are.

### 5.2 Slopes

| kernel | kind | levels (µs/step) | slope µs/n | 95 % CI ± | work/n | issue-limited µs/n | **% of issue-limited** |
|---|---|---|---|---|---|---|---|
| oproj | fma | 0:1425 4:1440 8:1441 16:1454 | 1.7 | 0.5 | 39.3 Mop | 11.0 | **15.4 %** |
| oproj | imad | 0:1425 8:1462 16:1491 | 4.1 | 0.6 | 39.3 Mop | 11.0 | 37.0 % |
| qkv | fma | 0:1693 1:1693 2:1699 4:1700 | 1.9 | 1.4 | 199.2 Mop | 55.7 | **3.5 %** |
| qkv | imad | 0:1694 2:1697 4:1707 | 3.3 | 1.2 | 199.2 Mop | 55.7 | 6.0 % |
| routed | fma | 0:1505 2:1509 4:1509 8:1535 | 3.8 | 1.8 | 81.8 Mop | 22.8 | **16.5 %** |
| routed | imad | 0:1505 4:1536 8:1596 | 11.4 | 3.0 | 81.8 Mop | 22.8 | 50.1 % |

Inserted arithmetic costs **3.5 – 16.5 % of its issue-limited price** on the
float ladder. The kernels have large spare issue capacity: work added *inside
the main loop* is largely absorbed into existing memory stalls. Every float
slope's 95 % interval excludes 100 % of the issue-limited price by a wide
margin — qkv's upper bound is 6.1 %, oproj's 20 %, routed's 24 %.

**Honest caveat on the integer ladder.** `imad` normalizes higher (36 – 50 %)
than `fma`. That is very likely an artefact of the denominator, not less
headroom: the 3.58e12 op/s figure is the *float* FMA peak, and 32-bit integer
multiply is commonly quarter-rate or worse on Apple GPUs. The `imad` rows are
therefore reported but the **float ladder is the load-bearing issue-headroom
evidence**; `imad` is included because it uses a different functional unit and
so guards against the float ladder being absorbed by an idle FP pipe alone.
Both ladders agree on direction (sub-unity), which is the claim being made.

CIs are still wide relative to the slopes — this probe can say "far below
100 %", not "exactly 3.5 %".

**Second caveat: independent chains, not the real dequant dependency graph.**
The ladder deliberately uses four independent chains so that it is throughput-
rather than latency-limited (§2.1). The dequantization arithmetic a future round
would remove is *dependent* — each step feeds the next — so it occupies issue
slots for longer per operation than the ladder does. The measured 3.5 – 16.5 %
therefore bounds the cost of adding *ideally schedulable* ALU work, and the cost
of the real dependent arithmetic could be somewhat higher. The bound is still
useful, because it is the same direction as the conclusion: even ideally
schedulable ALU work is nearly free here, and dependent work being *less* free
does not make the kernel issue-bound.

## 6. Probe 4 — extra-load ladder

### 6.1 Marginal cost of a byte

| kernel | kind | levels (µs/step) | slope µs/n | 95 % CI ± | MB/n | **marginal GB/s** |
|---|---|---|---|---|---|---|
| qkv | ld8 | 0:1694 1:2174 2:2566 | 435.8 | 37.0 | 99.6 | 228.6 |
| qkv | ld16 | 0:1694 1:2570 | 876.3 | 2.0 | 199.2 | 227.3 |
| oproj | ld8 | 0:1416 4:1518 8:1597 | 22.7 | 2.4 | 5.2 | 231.3 |
| oproj | ld16 | 0:1422 4:1596 | 43.6 | 2.3 | 10.5 | 240.4 |
| routed | ld8 | 0:1507 1:1707 2:1852 | 172.8 | 23.3 | 40.9 | 236.7 |
| routed | ld16 | 0:1505 1:1862 | 356.4 | 12.9 | 81.8 | 229.5 |

Every marginal rate lands in **227.3 – 240.4 GB/s**, i.e. essentially the same
rate the kernels already achieve (§3.3: 236.9 – 248.4 GB/s) and 87 – 92 % of the
sequential peak. An added byte costs full DRAM time in all three kernels:
**there is no spare bandwidth anywhere in the trio.**

**This is the measurement that excludes memory-latency-bound.** A kernel limited
by memory *latency* — too few outstanding requests to cover the round trip — is
by construction *not* saturating the pipe. Extra independent loads issued into
that slack would be partly free, so the marginal rate would come out
*above* the machine's streaming rate (in the limit, infinite: added bytes cost
nothing). What is observed instead is that added bytes cost the **full**
streaming rate, in all three kernels, on both load widths, with tight intervals
on four of the six fits. That is only possible if the memory pipe was already
full before the extra loads arrived.

*Placement caveat.* The load ladder is a post-epilogue tail (§2.1), so it reads
its own 128 MiB pool at a point where the main loop's loads have drained. The
number it produces is the marginal rate of a *clean* stream at the end of the
kernel, not the marginal rate of one more load interleaved into the main loop.
If anything that biases the measured rate *upward* (less contention), which
makes the "no spare bandwidth" reading conservative: an in-loop byte would cost
at least as much.

### 6.2 The decisive discriminator: bytes, not loads

This is the sharpest result of the round. `ld8:2k` and `ld16:k` move **exactly
the same bytes** from the same region: at each rung lanes 0–31 read consecutive
elements, so an `ld8` rung covers 256 contiguous B per simdgroup and an `ld16`
rung 512 B, and rung *j* sits at element offset *32j*. `ld8:2` and `ld16:1`
therefore touch the same 512 contiguous bytes and the same fully-covered cache
lines, and differ **only** in issuing twice as many load instructions to do it.

If the kernels were limited by memory-instruction *issue* or by
outstanding-request slots, doubling the request count at constant bytes and
constant footprint would cost substantially more. If they are limited by
*bandwidth*, it should cost the same.

| kernel | 2× loads, same bytes | 1× loads, same bytes | ratio (1×/2×) |
|---|---|---|---|
| qkv | `ld8:2` +871.7 µs/step | `ld16:1` +875.8 µs/step | **1.005** |
| oproj | `ld8:8` +181.3 µs/step | `ld16:4` +180.4 µs/step | **0.995** |
| routed | `ld8:2` +345.6 µs/step | `ld16:1` +355.0 µs/step | **1.027** |

Doubling the load count at constant bytes changes cost by **−2.6 % to +0.5 %**.
**Cost tracks bytes moved and is indifferent to the number of memory
instructions that move them.** That excludes **memory-issue-bound** and
**outstanding-request-slot-bound** as the binding constraint.

Note carefully what this probe does *not* do: because both variants touch the
same footprint, it holds latency exposure essentially constant and so cannot by
itself exclude latency-bound. The latency exclusion is §6.1's full-rate marginal
bytes, not this table. The two probes are complementary and neither substitutes
for the other.

## 7. Classification

| kernel | classification | probe 1 roofline | probe 3 free-ALU | probe 4 marginal byte | probe 4 byte-vs-load | agreeing instruments |
|---|---|---|---|---|---|---|
| **qkv** | **memory-bandwidth-bound** | 248.4 GB/s = 94.6 % of seq peak; per-dispatch model ratio 0.977 / 0.962 | ALU at 3.5 % of issue price | 228.6 / 227.3 GB/s marginal | ratio 1.005 | **3** |
| **oproj** | **memory-bandwidth-bound** | 236.9 GB/s = 90.3 % of seq peak; model ratio 0.991 / 1.020 | ALU at 15.4 % | 231.3 / 240.4 GB/s | ratio 0.995 | **3** |
| **routed** | **memory-bandwidth-bound** | 239.5 GB/s = 91.2 % of seq peak; model ratio 0.995 | ALU at 16.5 % | 236.7 / 229.5 GB/s | ratio 1.027 | **3** |

The assignment's stopping rule asked for ≥ 2 independent probes agreeing per
kernel. Each kernel has **three independent instruments** agreeing: probe 1
(byte-accounting roofline), probe 3 (free-ALU ladder), probe 4 (extra-load
ladder). §6.1 and §6.2 are two *analyses of the same probe-4 arms*, not two
independent probes, so they are listed separately above but counted once. Probe
2 (grid scaling) contributes nothing — it was not run as a controlled sweep (§4).

I say **memory-bandwidth-bound** rather than *DRAM-bandwidth-bound* throughout:
nothing here distinguishes DRAM from the fabric or the system-level cache. The
claim is that the memory path is the binding resource, not which level of it.

**Ruling out the other three categories, explicitly.**

* **Issue/ALU-bound — excluded.** Probe 3: inserted float arithmetic inside the
  main loop costs 3.5 – 16.5 % of its issue-limited price, with 95 % upper
  bounds of 6.1 / 20 / 24 %. An issue-bound kernel would pay ≈ 100 %.
* **Memory-latency-bound — excluded by §6.1**, not by §6.2. Extra *independent*
  loads are absorbed at 227 – 240 GB/s, i.e. the full streaming rate. A
  latency-starved kernel has idle memory-pipe capacity by definition and would
  absorb them below full price.
* **Memory-issue- / outstanding-request-bound — excluded by §6.2.** At equal
  bytes and equal footprint, doubling the load *instruction* count changes cost
  by −2.6 % to +0.5 %.
* **Occupancy-bound — excluded indirectly.** No direct geometry sweep was run
  (§4), so this rests on an inference rather than a dedicated probe, and is
  labelled as such. The argument: an occupancy-limited kernel has too few
  resident threads to cover its own memory latency, so it *cannot* be running
  at 90 – 95 % of the machine's best measured streaming rate — the two are
  mutually exclusive. Independently, an occupancy-limited kernel would show
  added ALU work as *nearly free* (true here) **and** added bytes as *cheaper
  than full DRAM rate*, because it was not saturating the pipe to begin with.
  The observed combination — nearly-free ALU **together with** full-price bytes
  at 227 – 240 GB/s — is logically incompatible with occupancy-limited and is
  the exact signature of bandwidth-saturated.

## 8. Ranked candidate mechanisms with ceilings

The classification is the ranking: for all three kernels the only lever with a
large ceiling is **moving fewer bytes**. Everything else is bounded by the
−55 µs/step of aggregate non-DRAM residual the trio actually carries (§3.4).

Two framing rules apply to every number in this section.

1. **Units.** Ceilings are quoted as **local µs/step against this rig's
   8582 µs/step busy pool** (see the §3.4 clock caveat — do *not* convert them
   with the assignment's 48.94 µs/step-per-1 % constant, which belongs to a
   4894 µs/step decode clock).
2. **Serialization.** Every dispatch-overhead figure here is derived from the
   SPLIT=1 intercept and is therefore an **upper bound on what is recoverable in
   production**, which runs unsplit at 7940 vs 8582 µs/step busy (§2.3, §3.4).
   Byte-reduction figures (mechanism 1) do not carry this caveat; overhead
   figures (2, 2a, 3, 4) all do.

| # | mechanism | ceiling (local µs/step) | basis | confidence |
|---|---|---|---|---|
| 1 | shave real bytes off the weight stream | **≈ 180** in-trio, if the scale planes could vanish entirely | codes are already 4-bit, so the only removable bytes above a pure-code floor are the scale planes and bases: qkv 1057→1024 B/row (−12.84 MB), oproj 4225→4096 and 3169→3072 (−9.91 MB), routed 1 114 112→1 048 576 B/expert (−20.44 MB) ⇒ 1085.5 → 1042.3 MB/step, −43.2 MB at 240 GB/s = **180 µs/step**. This is an upper bound assuming scales become free, which they cannot; a realistic packing win is a fraction of it | high that the *rate* holds; low that the bytes are removable |
| 2 | fixed per-dispatch cost, pool-wide | **≈ 1612** gross, ≲ 800 recoverable | 3.97 µs model intercept × 406 dispatches/step; an empty serialized dispatch measures 0.87 µs (1×32) to 2.46 µs (160×256), so roughly half the intercept is irreducible launch/teardown that survives any merge — only the part above that floor is addressable by issuing fewer, larger dispatches | medium |
| 2a | — of which inside the trio | **472** gross, ≲ 240 recoverable | 3.97 µs × 119 trio dispatches = 5.5 % of the busy pool | medium |
| 3 | close the achieved→sequential-peak gap | **≈ 350** | trio at 242.0 GB/s aggregate net of the SPLIT tax vs 262.5 GB/s sequential ⇒ 1085.5 MB at 262.5 = 4135 µs vs 4485.3 net measured | low — the pattern ceilings (236.6 / 243.0 GB/s) say most of this gap is the access pattern, not slack; and see the double-counting note below, where it is shown to be a subset of (2a) |
| 4 | the wall−busy gap | **≈ 302** gross | under SPLIT=1 the gap is 1261 µs/step (wall 9843 vs busy 8582), but that is mostly the serialization artefact itself: the **`off@nosplit` control measures wall 8242 vs busy 7940, a gap of only 302 µs/step**. Production has ≈ 302 µs/step of GPU idle to attack, not 1261 | medium — the nosplit number is a direct measurement, but it overlaps (2) and is partly host-side |
| 5 | anything that trades bytes for ALU | **≈ 0**, likely negative | probe 3 says ALU is 83.5–96.5 % free, but probe 4 says every added byte costs full DRAM rate; a transform that spends ALU to *save* bytes is the only version of this with positive expected value, and it is mechanism (1) | high |
| 6 | expert-locality / routing-affinity tricks | **≈ 0** | routed already runs at 98.6 % of its own measured gather pattern ceiling and 91.2 % of sequential peak; there is no locality left to exploit | high |
| 7 | reducing write traffic | **≈ 0** | writes are ≈ 0.5–0.9 MB/step against 1085 MB of reads | high |

**Double-counting warning: (3) is contained in (2a), not additive to it.** The
3.97 µs model intercept lives *inside* the busy pool, so it is precisely one of
the things that makes the trio achieve 242.0 GB/s instead of 262.5 GB/s. The
arithmetic closes almost exactly:

| term | µs/step |
|---|---|
| (2a) fixed-cost pool inside the trio, 3.97 × 119 | **472** |
| less the measured aggregate non-DRAM residual (§3.4) | −55 |
| less the model-vs-sequential slope difference (266.3 vs 262.5 GB/s over 1085.5 MB) | −59 |
| = implied achieved→sequential-peak gap | **358** |
| (3) measured achieved→sequential-peak gap | **350** |

358 versus 350 is agreement to 2 %. Mechanism (3) is therefore *the same slack*
as most of mechanism (2a), re-expressed as a rate deficit. **Their union is
472 µs/step gross — not 550, and certainly not 793.** Mechanism (4) is measured
*outside* the busy pool, so it is additive to (2a) within the trio but overlaps
(2) pool-wide, and part of it is host-side rather than GPU-addressable.
Mechanism (1) is the one genuinely orthogonal item: it removes bytes rather than
overhead.

A second, sharper version of the same warning applies to mechanism (4). The
1261 µs/step wall−busy gap that SPLIT=1 shows is **not** an opportunity: the
`off@nosplit` control in the same census measures wall 8242 against busy 7940,
so the real production idle gap is **302 µs/step**, four times smaller. Roughly
960 µs/step of the apparent gap is the serialization the profiler itself
imposes. Any follow-up that sizes an overlap or pipelining change against the
SPLIT=1 number will over-promise by ≈ 4×.

**Honest in-trio ceiling.** At **fixed bytes**, the trio has **≈ 472 µs/step**
of gross addressable time (the union of (2a) and (3)), of which **≲ 240 µs/step
is realistically recoverable** once the empty-dispatch floor is subtracted — and
even that is an *upper* bound on production, because the whole figure is derived
from a SPLIT=1 intercept while production runs unsplit (framing rule 2). Adding
the most optimistic byte reduction (mechanism 1, ≤ 180 µs/step, itself assuming
the scale planes become free) gives an absolute optimistic total of
**≈ 420 µs/step**. Against this rig's own numbers that is **≈ 9 % of the trio's
4652.7 µs/step raw** and **≈ 4.9 % of the 8582 µs/step busy pool**. Those are
the numbers a follow-up should be sized against. The trio's 54 % share of the
busy pool is *not* a 54 % opportunity, and treating it as one has been the
recurring error this census was meant to settle.

**What this rules out for future rounds.** Any proposal for these three kernels
that does not reduce bytes moved, reduce dispatch count, or overlap the
wall−busy gap (only 302 µs/step unsplit) has a ceiling near zero. Unrolling,
register-pressure tuning, instruction selection, math-mode changes, and cheaper
dequantization arithmetic
all fall in that class — probe 3 already measured that the arithmetic they would
remove is 83.5–96.5 % free. This is the round's most reusable negative.

## 9. The bandwidth-vs-issue contradiction

The contradiction the assignment names is: the trio looks *bandwidth-saturated*
by roofline, yet earlier rounds found it *responsive to issue-side changes*.
Probes 3 and 4 resolve it, and the resolution is not that one side was wrong.

**Resolution: spare issue slots and saturated bytes coexist, and they are not
in tension.** A kernel that is DRAM-bound spends most of its wall time waiting on
memory returns. During that wait the SIMD issue pipe is idle, so arithmetic
inserted into the shadow of an outstanding load is genuinely close to free —
measured at 3.5 % (qkv), 15.4 % (oproj), 16.5 % (routed) of its issue-limited
price (§5.2). That is *predicted* by bandwidth saturation, not a contradiction
with it. The two statements "there is idle issue capacity" and "the memory pipe
is full" are simultaneously true, and §6.2 is the measurement that separates
them: at **equal bytes**, doubling the number of load instructions changes cost
by between **−2.6 % and +0.5 %**. Cost tracks bytes and is blind to instruction
count.

So the correct reading of an issue-side win in an earlier round is that it
removed *bytes* or *dispatches*, or that it moved work out of a region where
the memory pipe happened to be starved — not that the kernel was issue-limited.
The falsifiable prediction is: **a change that only removes ALU work from these
three kernels will not measurably speed them up.** The observed free-ALU slopes
put the ceiling for removing *all* the dequantization arithmetic at 3.5–16.5 %
of its nominal cost (95 % upper bounds: 6.1 % qkv, 20 % oproj, 24 % routed).

The residual asymmetry is worth noting: routed's 16.5 % is about five times
qkv's 3.5 %, so routed has the least issue slack of the three and is the one
kernel where an ALU reduction is not entirely futile. Its `imad` ladder (50.1 %)
points the same way, though the integer normalizer is a known artefact (§5.2).

## 10. What remains unmeasured

Listed so a follow-up does not mistake an inference for a measurement.

### 10.1 Gaps that a follow-up should close, in priority order

1. **Dispatch-count reduction was costed but never attempted, and the cost model
   is itself SPLIT=1.** Mechanism (2)'s ≲ 800 µs/step (and (2a)'s ≲ 240) is
   arithmetic from the model intercept and the empty-dispatch floor, not a
   fusion experiment. Two things should be run together and they are the
   highest-value follow-up: **(a) an unsplit-vs-SPLIT=1 A/B on the *same* build**
   to measure how much of the 3.97 µs intercept survives when Metal is allowed
   to batch command buffers normally (this rig shows 7940 vs 8582 µs/step busy,
   so a large fraction plainly does not survive); and **(b) one concrete
   CB-batching or kernel-fusion pilot** inside the trio, sized against the
   ≲ 240 µs/step in-trio figure. Until (a) is run, every overhead ceiling in §8
   is an upper bound of unknown tightness.
2. **No contention co-run.** The sharpest untried test of "bandwidth-saturated"
   is a second concurrent stream of known size *S* on another queue: a truly
   saturated kernel should slow by ≈ *S*/262.5 GB/s (additive), a
   latency-limited one sub-additively. This would upgrade the classification
   from strong-inferential to direct.
3. **A controlled grid-scaling sweep (probe 2) was not run.** §4 explains why:
   no env knob reaches the trio's geometry and geometry is forbidden to ship
   (#48, receipt `285f79fa`, −0.1488 %). The observational h64/h48 substitute is
   confounded — it varies head count and `in_vec` together, and oproj's implied
   298.8 GB/s exceeds the sequential peak, which proves the confound rather than
   a result. **Occupancy-limited is therefore excluded by inference (§7), not by
   a dedicated probe.**
4. **The two-parameter DRAM refit (§3.4) is a same-host model, not a
   first-principles one.** It dissolves the 105.0 % qkv anomaly, but it was
   fitted on the *replay* size ladder and applied to *kernel* dispatches. It has
   not been checked by (a) refitting the replay ladder with the intercept free
   and reporting its CI, (b) testing the slope directly on a kernel at 2× and 4×
   K, (c) inserting an SLC-busting stream between dispatches to see whether the
   intercept is really fixed cost or partly cache residency, or (d) auditing
   physical buffer lengths for padding. Until then the sub-100 % ratios in §3.4
   should be read as "consistent with", not "proven".
5. **The in-flight-bytes-per-lane table (§3.2) is size-confounded.** It was run
   at 5.06 MB per pattern, where the 3.97 µs fixed term alone caps achievable
   rate near 218 GB/s. Its absolute numbers therefore understate wide-access
   rates; only its *shape* (8 B → 32 B is the big jump) is safe to use.
6. **The escaped rows are now counted, but not traced to DRAM.** §3.1c replaces
   the earlier derivation with direct counts: **0.654 % of QKV rows and 1.908 %
   of oproj rows escape the pairwise fast path**, i.e. ≈ 64 QKV and ≈ 39 oproj
   rows per layer. That is **20–40× more than the `:706-717` header comment's
   bound** (≤ 3 QKV, ≤ 1 oproj per layer), because the comment bounds only the
   pairwise-disagreement cause and not the scale-span > 15 cause; the derivation
   in §3.1b was correspondingly too optimistic and should not be reused. The
   byte impact is still small (+0.24 and +0.56 MB/step, +0.07 % on the trio,
   rates 248.4→248.5 and 236.9→237.3 GB/s) so no classification moves. What is
   still not done is a byte-level trace confirming the escape branch's
   128 B/row actually reaches DRAM rather than hitting cache.
7. **Everything here is M4 Pro (`applegpu_g16s`, gen 16).** The `_nax` kernel
   family the ranked M5 selects is unreachable locally. The *classification*
   (bandwidth-bound) should transfer, since it rests on byte counts and a
   memory-system ceiling rather than on issue width; the *numbers* (µs/step,
   GB/s, and especially the 3.97 µs intercept) should not be assumed to.

### 10.2 Caveats that qualify the probes themselves

These do not change the classification but bound how far each number may be
pushed.

- **Every per-kernel number in this report is a SPLIT=1 quantity.** Per-kernel
  attribution requires one dispatch per command buffer, which costs this rig
  642 µs/step (§2.3). Production runs unsplit. Rates and *ratios* survive the
  translation; absolute overhead figures do not (§8 framing rule 2).
- **The probe pool is not the weight stream.** The 128 MiB uint32 probe buffer
  is read with a small, dense, highly regular stride, so its TLB and
  cache-residency regime differs from the trio's real weight traffic. The
  marginal-byte rates in §6.1 (227–240 GB/s) landing on top of the roofline
  rates (237–248 GB/s) is reassuring, but it is not proof that a marginal byte
  *of weight* costs exactly the same as a marginal byte *of probe pool*.
- **The load ladder sits after the epilogue, once per thread; the ALU ladder
  sits inside the K-loop.** The two probes therefore stress different points of
  the kernel's lifetime. A tail-placed load cannot be hidden by loop software
  pipelining, so §6.1's marginal cost is, if anything, an *over*-estimate of
  what an equivalent in-loop load would cost — which makes the
  bandwidth-bound conclusion conservative in the right direction.
- **The ALU ladder uses four independent chains; real dequantization arithmetic
  is dependency-chained.** Independent chains measure *issue* slack, which is
  the right quantity for "is this kernel issue-limited". They do not measure
  latency slack, so §5.2's slopes are a lower bound on the cost of *dependent*
  arithmetic. The gap matters only if a future proposal adds serially dependent
  math, which the §8 ranking already rates ≈ 0.
- **Attribution under SPLIT=1 is not the unsplit execution path.** §2.3's
  1.78 µs/boundary is a measured tax on *this* configuration; Rule 41's more
  conservative 1.4064 µs is used throughout the report, so the corrections
  applied are smaller than the measured tax would justify.
- **A +1.0 % drift was observed across the 48-minute census** (`off` rep1 8538
  vs rep2 8627 µs/step). Every ladder is fitted across both reps with the arm
  order reversed in rep 2, so drift enters the residual rather than the slope;
  it is nevertheless the largest single source of the ladder CIs.

## 11. Reproduction

```bash
git checkout ca920bbe6938ae7efb9cab79739229a0321ba856
git apply research/nezuko-r93-probes.patch          # probe wiring, never shipped
git apply research/nezuko-pr158-gpuprof-hook.patch  # per-kernel GPU timing
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
python3 research/maple_r93_census.py /tmp/r93/main research/maple_r93_main.arms 80
python3 research/maple_r93_escape_audit.py /tmp/r93/main   # writes escape.json
python3 research/maple_r93_analyze.py /tmp/r93/main
python3 research/maple_r93_wandb.py /tmp/r93/main
```

The census takes ≈ 49 min for 70 arms (worker model load dominates at ≈ 44 s per
arm); the escape audit takes ≈ 40 s and needs no GPU.

## 12. W&B

**Run `mhhosz20`** — <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/mhhosz20>
(`r93-c-stall-structure-census`, `job_type=diagnostic`, state `finished`).

Tables logged:

| key | rows | contents |
|---|---|---|
| `census/arms` | 70 | every arm × rep: busy, wall, per-kernel µs/step, divergence count |
| `roofline/table` | 3 | probe 1: raw/net µs, MB/step, raw/net GB/s, % pattern ceiling, % sequential peak |
| `dispatch/dram_model` | 5 | per-dispatch two-parameter DRAM model, net/model ratio, residual |
| `controls/level0_placement` | 3 | Rule 44 name- and residency-matched level-0 controls with spread |
| `ladders/fits` | 12 | probes 3 and 4: OLS slope, 95 % CI half-width, work per rung, normalized value |
| `escape/pairwise_fast_path` | 2 | measured escaped-row counts and rates per weight bank |

Key summary scalars: `roofline/trio/net_GB_s` **242.01**,
`roofline/trio/net_us_per_step` 4485.3, `roofline/trio/MB_per_step` 1085.5,
`roofline/trio/pct_sequential_peak` 92.2,
`dispatch/fixed_pool_us_per_step` 472.2,
`dispatch/non_dram_residual_us_per_step` −55.1,
`split/off/busy_sum_ms` 8.5825, `split/off_nosplit/busy_sum_ms` 7.9395,
`probe/arms_total` 70, `probe/non_bit_exact_arms` **0**.

A partial 24-arm dry run from the same code is retained as `604khm00`
(`r93-c-census-DRYRUN-partial-24arms`, tagged `dryrun`); it is superseded by
`mhhosz20` and should not be used for any number in this report.
