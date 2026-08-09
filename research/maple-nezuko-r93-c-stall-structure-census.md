# R93-C — Stall-structure census of the barrier-free 54 % trio

Student `maple-nezuko` · PR #498 · assignment `maple-r93-c-stall-structure-census`
rev `r93-c-rev1` · base `ca920bbe6938ae7efb9cab79739229a0321ba856`

**Diagnostic round. No fix ships. The submitted editable surface at HEAD is
byte-identical to the assignment base (0 bytes changed).**

---

## 1. Question

Three decode kernels hold 54.2 % of the 8528 µs/step GPU-busy pool:

| kernel label | µs/step (assignment) | µs/step (this rig) | share |
|---|---|---|---|
| `decode_nvfp4_qkv_h64/h48_...` | 1702.9 | TBD | 20.0 % |
| `oproj_act_h64/h48_...` | 1419.5 | TBD | 16.6 % |
| `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 1497.7 | TBD | 17.6 % |

R92-A showed they carry no hoistable barrier. This round asks *what they are
actually waiting on*: DRAM bandwidth, memory latency, instruction issue/ALU
throughput, or occupancy.

Calibration: 1.00 % decode = 48.94 µs/step; 0.015280 % score per µs/step.

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

TBD

## 6. Probe 4 — extra-load ladder

TBD

## 7. Classification

TBD

## 8. Ranked candidate mechanisms with ceilings

TBD

## 9. The bandwidth-vs-issue contradiction

TBD

## 10. What remains unmeasured

TBD

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
