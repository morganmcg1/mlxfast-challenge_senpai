# R122-B — porting the o_proj `rps` residency parameterization to the decode QKV lane-major kernel

Student: maple-nezuko. Assignment `maple-r122-b-qkv-residency-ladder`, revision
`r122-b-rev1`, PR #719. BASE `fa2a81b7624f6afa807830eb9ad7eb6d38c3d11d`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU generation 16.

---

## §0. Headline

**The hypothesis is refuted. No rung of the `results_per_simdgroup` ladder
beats the shipped `rps = 1` QKV kernel, and the far rung loses decisively.**

| arm | `rps` | µs/token (mean of 3 blocks) | Δ vs Q1 | CI95 on Δ | verdict |
| --- | --- | --- | --- | --- | --- |
| **Q1** (shipped) | 1 | **8918.96** | — | — | reference |
| Q2 | 2 | 8950.29 | **+31.33** | [−36.06, +98.72] | no win; interval covers 0 |
| Q4 | 4 | 8975.75 | **+56.79** | [−13.93, +127.51] | no win; interval covers 0 |
| Q8 | 8 | 9124.84 | **+205.88** | [+151.67, +260.08] | **significant regression**, +2.31 % decode wall |

- **All 12 runs `passed=true` with one identical golden hash**, so the
  parameterization is bit-identical at every rung: the mechanism was
  implemented correctly and simply does not pay (§4.2).
- **No landing branch is prepared**, per the assignment's rule: an arm must be
  bit-identical *and* beat Q1 on an interval excluding zero. None does.
- **The null was predictable from a number in my own earlier report.**
  `decode_nvfp4_qkv_h64` already runs at **94.3 % of this host's measured
  streaming peak** (§5.2). The most valuable output of R122-B is therefore a
  *selection* rule for the campaign: gate geometry experiments on achieved
  bandwidth, and never assign a bandwidth-shaped change to a kernel above
  ~90 % of peak (§8 item 3).
- W&B run: `3x2cwlll` —
  <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/3x2cwlll>.
  Raw per-run TSVs for both campaigns are committed under
  `research/r122b-runs/`.

Prefill speedup fails its 0.95 floor on **every arm including untouched
controls** on this host: an M4 Pro reports Apple GPU generation 16 and does
not select the `_nax` prefill kernels the ranked M5 uses, so
`prefill_speedup ≈ 0.33` here is structural and is not an effect of this
change (§4.3, §7.3).

§1 below is the pre-registration, committed at `8355c24a` before any data
existed. It is not edited after the first data commit; corrections to it are
appended to §7 with a timestamp instead.

---

## §1. Pre-registration (committed before data)

### 1.1 The geometry facts I am predicting from

Read off the merged tree (`Sources/MLXFastModel/LagunaRuntimeModel.swift`
`:4938-4995` for the body, `:5023-5083` for dispatch, `:5094-5108` for the
grid-appended qkv+gate variant):

- `num_simdgroups = 2`, `values_per_thread = 16`, `threadGroup = (64,1,1)`,
  `grid = ((rows / 2) * 64, 1, 1)`, `out_row = tile * num_simdgroups + simd_gid`
  ⇒ `results_per_simdgroup = 1`, hardcoded and implicit.
- h64: `rows = (64 + 16) * 128 = 10240` ⇒ 5120 TGs, **10240 simdgroups,
  512.0 per core at C=20**, 256.0 at C=40.
- h48: `rows = (48 + 16) * 128 = 8192` ⇒ 4096 TGs, **8192 simdgroups,
  409.6 per core at C=20**, 204.8 at C=40.

Against my own R117-C interior optimum (**51.2 simdgroups/core**) and tanjiro's
grantable-occupancy ceiling (**96/core**), K2 is 10× above the former and 5.3×
above the latter.

| arm | rps | ns | TGs (h64) | simdgroups (h64) | /core C=20 | /core C=40 | TGs (h48) | simdgroups (h48) | /core C=20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Q1** (shipped, A/A control) | 1 | 2 | 5120 | 10240 | 512.0 | 256.0 | 4096 | 8192 | 409.6 |
| Q2 | 2 | 2 | 2560 | 5120 | 256.0 | 128.0 | 2048 | 4096 | 204.8 |
| Q4 | 4 | 2 | 1280 | 2560 | 128.0 | 64.0 | 1024 | 2048 | 102.4 |
| **Q8** (primary candidate) | 8 | 2 | 640 | 1280 | 64.0 | 32.0 | 512 | 1024 | **51.2** |
| Q16 | 16 | 2 | 320 | 640 | 32.0 | 16.0 | 256 | 512 | 25.6 |

Note a fact the brief's table does not make explicit and which I will lean on
in §5: **the two head counts are one arm apart.** At Q8, h48 sits at exactly
51.2/core — my measured o_proj optimum — while h64 sits at 64.0/core. At Q16,
h48 is at 25.6/core, i.e. exactly the *pre-*R117-C o_proj residency that I
measured to be worse. So a single ladder point carries two different per-core
residencies, and the h64/h48 split is itself a within-arm probe.

### 1.2 Predicted signs and magnitudes (falsifiable, stated before data)

Deltas are candidate − Q1, decode µs/token, SPLIT=0 wall, block-paired median
with a bootstrap CI95. Decode wall reference ≈ 8,970 µs/token.

| arm | predicted sign | predicted magnitude (µs/token) | confidence |
|---|---|---|---|
| **Q8** | **negative (wins)** | **−60 to −200**, point ≈ **−120** | moderate |
| Q4 | negative, intermediate between Q1 and Q8 | −40 to −140 | low-moderate |
| Q2 | negative, small | −10 to −70 | low |
| Q16 | negative but **worse than Q8** | −20 to −140 | low |
| Q1 vs Q1 (A/A) | interval covers zero | \|Δ\| < 25 | high |

The advisor's stated expectation is Q8 ∈ [−40, −250] and Q16 worse than Q8. My
Q8 interval is narrower and my point estimate is inside his. I am not
copying his number: mine is anchored on relative kernel size. R117-C took
−80 µs/token out of an o_proj family of ~1,385 µs/step busy (K3 1,082–1,115 +
h48 ~303), i.e. **5.7 % of the family**. K2's family is **1,705.6 µs/step**
(1,342.1 h64 + 363.5 h48). At the same relative efficiency the port is worth
−98 µs/token. I widen downward because the two changes are in *opposite
regimes*: R117-C moved 25.6 → 51.2/core, i.e. **upward toward** the optimum from
below, whereas Q8 moves 512 → 64/core, i.e. **downward toward** it from 8×
above. Nothing in my R117-C data measures the descending limb, so the transfer
of magnitude is an extrapolation and I am pricing it as one.

### 1.3 The collinearity I cannot break by geometry — and the shape test that partly survives it

I accept the advisor's §4 point in full and restate it as my own: in this
parameterization **total simdgroup count and activation re-read volume are
perfectly collinear.** The activation row is `hidden = 2048` × 2 B = 4,096 B and
every simdgroup reads all of it, so re-reads/call = 4,096 B × simdgroups:

| arm | simdgroups (h64) | re-reads/call (h64) | h64/step (30 calls) | h48/step (10 calls) | family/step |
|---|---:|---:|---:|---:|---:|
| Q1 | 10240 | 41.9 MB | 1.258 GB | 0.336 GB | **1.594 GB** |
| Q8 | 1280 | 5.24 MB | 0.157 GB | 0.042 GB | **0.199 GB** |

Every arm that cuts simdgroups cuts re-reads by the identical factor, and
changing `ns` at fixed `rps` changes neither. **This experiment cannot separate
"residency/wave count" from "activation re-read volume" by geometry alone, and
I am not going to claim it can.**

My R117-C escape — separating bytes from residency by *sign*, because the
winning arms *added* 314.6 MB/step — does not exist here. Both accounts predict
the same sign for every arm on this ladder.

**However, they do not predict the same *shape*, and that is a discriminator the
brief does not name:**

- A **residency / latency-hiding** account has an **interior optimum**: too many
  simdgroups means serialized waves, too few means insufficient memory-level
  parallelism to cover latency. It predicts a **reversal** — Q16 strictly worse
  than Q8 — and my R117-C `R1` arm is direct evidence that this reversal is real
  at this site's sister kernel.
- A **re-read-volume / L2-traffic** account is **monotone**: less traffic is
  never worse, with diminishing returns. It predicts Q16 ≤ Q8, never a
  reversal.

So: **Q16 worse than Q8 on a paired interval excluding zero ⇒ residency, with
volume relegated to at most a co-factor. Q16 ≤ Q8 ⇒ the volume account is
sufficient and the interior-optimum story is not needed at this site.** I
pre-commit to reading the ladder that way.

🔴 **Confound that limits the shape test, stated up front:** high `rps` costs
registers. Each simdgroup holds `rps` FP32 accumulators plus `rps × 4` bytes of
`sb` scale bytes (Q8: 8 accumulators + 32 B; Q16: 16 + 64 B). A Q16 regression
is therefore **not** cleanly attributable to residency — it may be register
pressure or spilling. I will report the Q16 regression, if any, as
**residency-or-register-pressure** and will not claim the shape test is clean
unless Q8 → Q16 degrades by more than the Q4 → Q8 improvement (which would be
hard to explain by a monotone register cost alone). This is a real limitation of
the ladder and it is why I am not promising a decisive mechanism verdict.

### 1.4 What would refute the residency account outright

- **Q8 interval covers zero** while the geometry readback and pipeline name
  confirm rps=8 actually ran. An 8× cut in both simdgroup count and re-read
  volume producing no wall movement refutes both the residency and the volume
  account at this site, and localizes K2's 44.73 µs/call to something else
  (weight-stream DRAM, as the atlas's 95.4 %-of-peak claims).
- **Q8 loses** (positive interval excluding zero). Then more simdgroups is
  better at this site, the 512/core figure is not oversubscription, and my
  R117-C mechanism does not generalize beyond o_proj. I would report that as a
  clean refutation of the port hypothesis and it is a perfectly good terminal
  result.
- **Q4 not intermediate** between Q1 and Q8 (per the advisor's own falsifier):
  the smooth-residency picture is wrong and something discrete happens at the
  96-slot boundary.

### 1.5 The 77 %-of-traffic argument that the re-reads must be cache-served

Total decode DRAM traffic ≈ 230.6 GB/s × 8.97 ms/step ≈ **2.07 GB/step**. The
QKV activation re-reads at the shipped Q1 geometry are **1.594 GB/step**
(§1.3) = **77.0 %** of that budget — while the atlas simultaneously attributes
K2's 44.73 µs/call to 11.8 MB of *weight* bytes at 95.4 % of DRAM peak. Both
cannot be true: the weights alone already claim the roof. **Therefore the
activation re-reads are provably cache-served, not DRAM traffic**, and any
byte-priced prediction for this arm would be wrong by an order of magnitude. I
am not making one. The operative resource, if the arm wins, is L2/issue
bandwidth and scheduling waves.

A consequence worth recording separately, because it survives whatever the
ladder does: **the byte model used across this campaign counts activation
re-reads as DRAM traffic in at least one place where they demonstrably are
not.** That is the same failure mode alphonse's R122-A is testing from the
other side.

### 1.6 Instrument, pre-committed

One binary at BASE, env-switched, paired, interleaved, mirrored orders reported
separately, warmed isolated full 39-layer chain, steady tail over tokens ≥ 16,
SPLIT=0 wall as the ranking statistic, bootstrap CI on the median block-paired
delta, bimodality screen (elevated Sarle **and** ≥2 smoothed-histogram modes ⇒
instrument failure ⇒ stop). Raw per-run TSV committed under `research/`.
Correctness gate: `max_abs_diff == 0` and a single unchanged golden hash in
every arm proposed for shipping.

### 1.7 Pre-data addendum (committed 09:17Z, before any run had finished)

Written while the Q1/Q8 campaign was in flight and **before any TSV row
existed** — the git history is the proof of order. I am adding it rather than
editing §1.2 because it makes a *sharper and differently-shaped* prediction than
I first wrote, and burying that would defeat the point of pre-registering.

Working through the arithmetic against tanjiro's independently measured
grantable ceiling of **96 simdgroups/core**
(`research/tanjiro-pr-gathergemm-coresidency.md:445-452`), the residency account
has a **discrete** form I did not state in §1.2. Per-core residency is
`512/rps` for h64 and `409.6/rps` for h48, so the number of sequential grantable
waves is `ceil(residency / 96)`:

| arm | h64 /core | h64 waves | h48 /core | h48 waves | both fit one wave? |
|---|---:|---:|---:|---:|---|
| Q1 | 512.0 | **6** | 409.6 | **5** | no |
| Q2 | 256.0 | 3 | 204.8 | 3 | no |
| Q4 | 128.0 | 2 | 102.4 | **2** (only just — 102.4 vs 96) | no |
| Q8 | 64.0 | **1** | 51.2 | **1** | **yes** |
| Q16 | 32.0 | 1 | 25.6 | 1 | yes |

This reframes my own R117-C result. I reported an "interior optimum near
51.2/core". The wave arithmetic says something more specific: my `R1` arm sat at
**102.4/core, i.e. just above 96**, so it needed two waves where `R2` at 51.2
needed one. **The better description of my R117-C finding is therefore not "an
optimum at 51.2" but "the largest residency that still fits inside a single
grantable wave", and 51.2 is simply where the o_proj ladder happened to land.**
That unifies my constant with tanjiro's instead of leaving two unexplained
numbers, and it is falsifiable here.

Three consequences I pre-commit to:

1. **The Q4 → Q8 step should be the largest single step on the ladder**, because
   it is the only step that crosses from two waves to one for both head counts.
   The Q1 → Q2 → Q4 steps should each be smaller and roughly consistent with
   halving a wave count (6 → 3 → 2).
2. **Q16 ≈ Q8, not worse.** Q16 has the *same* wave count as Q8, so a pure
   wave-count model predicts no further gain and no reversal — only whatever
   register-pressure cost the extra 8 accumulators carry. This is a **third
   shape**, distinct from both shapes in §1.3: interior optimum (Q16 worse),
   monotone volume (Q16 better), wave-count (Q16 flat).
3. **What refutes the wave-count account:** a large, clean Q1 → Q4 gain with
   little left for Q4 → Q8, or a Q16 that is substantially *better* than Q8.
   Either would say the mechanism is smooth in simdgroup count (or in re-read
   volume) and not stepped at 96.

This addendum makes my prediction strictly harder to satisfy than §1.2 did,
which is the direction a pre-registration should be revised in.

---

### 1.8 Amendment 1 (09:23Z — after block 1 only, before any further data)

Block 1 has landed, both runs. It is one paired block, so it does not settle
anything, but it is enough to change what the remaining wall clock should be
spent on, and the honest way to do that is to write the amendment down before
the new runs execute rather than to present a re-planned campaign as the
original one.

**What block 1 says.** Q1 8926.7 µs/token, Q8 9113.0 µs/token — Q8 **slower by
+186.3 µs/token** (+2.09 %). Golden digest identical
(`f49e4c2cbc0d3cee…`), `passed=true` on both. So:

- the rps=8 kernel is **bit-identical** to the shipped kernel over the full
  1023-step decode, which validates the §2.4 identity argument including the
  register-pressure caveat at the compiler level;
- the timing moved by 2 %, which by itself proves the arm **did** dispatch a
  different pipeline — a silent fallback would have reproduced Q1's time, not
  differed from it by 21× the effect size I was hunting. Hazard (a) is
  therefore already excluded for Q8 by the data, independently of the trace
  readback;
- the sign is **opposite** to my pre-registered −60 to −200 µs and to the
  advisor's −40 to −250 µs.

**What that refutes, stated now.** This is §1.4 refuter #2, which I wrote
before any run: *"Q8 loses ⇒ more simdgroups is better at this site, the
512/core figure is not oversubscription, and my R117-C mechanism does not
generalize beyond o_proj."* It also refutes §1.7's single-wave model, which
picked Q8 as the argmax for both head counts precisely because it is the only
rung reaching one grantable wave. Both of those were mine. I am recording the
refutation at the point of first contact rather than letting the final write-up
decide how much of the model to keep.

**Why the arm plan changes.** The pre-registered campaign was Q1 vs Q8 × 6
blocks. Five more blocks of a 2 % regression buys a tight interval on a number
nobody will act on. The live question after block 1 is no longer "does Q8 win"
but "does *any* rung win, or is K2 monotone in parallelism". That is a question
about the *shape* between Q1 and Q8, and it needs the intermediate rungs.

Remaining budget is ~9 runs before the 10:30Z deadline. New plan: finish block
2 of the Q1/Q8 pair (so the headline regression has two paired blocks and a
replication check on its sign), then run **Q1 / Q2 / Q4 × 3 blocks**.

**Predictions for the amended arms, before they run.**

1. Q8's sign replicates in block 2. If it does not, block 1 was noise and the
   refutation above is withdrawn.
2. If K2 is monotone in parallelism, then `0 < Δ(Q2) < Δ(Q4) < Δ(Q8) ≈ +186`,
   i.e. every rung loses and losses grow with `rps`.
3. The one outcome that would rescue a weakened form of the residency
   account: Q2 (256 sgs/core) or Q4 (128 sgs/core) **beating** Q1 on an
   interval excluding zero. That would put K2's optimum somewhere in
   128–256 sgs/core — far above o_proj's 51.2 — so the optimum would be
   real but *per-kernel*, not a transportable constant. I would report that
   as "the port hypothesis fails but the mechanism survives, rescaled".
4. The residual possibility I cannot exclude with 3 blocks: a rung whose true
   effect is a genuine but small win, say −20 µs, will not separate from zero
   here. §4 will state the achieved resolution rather than call such a cell a
   null.

I am not adding Q16. Under prediction 2 it is the least informative rung, and
under prediction 3 it is on the wrong side of the interesting region. The §1.3
shape test therefore loses its Q16 arm; what replaces it is the Q2/Q4/Q8
ordering, which tests the same monotone-versus-interior question from below.

---

## §2. The code change

One submitted file: `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(+82 / −28). Commit `a5746c6f`.

### 2.1 The three new symbols

| Symbol | Line | Role |
| --- | --- | --- |
| `lagunaDecodeQKVRowsPerSimdgroup` | 4947 | env `DARKBLOOM_QKV_ROWS_PER_SIMDGROUP`, accepted set `{1,2,4,8,16}`, **default 1** |
| `lagunaDecodeQKVGeometrySuffix` | 4959 | `""` at rps=1, else `_qrps<N>` |
| `lagunaDecodeQKVTilesDivisor` | 4966 | `2 * rps` — simdgroups per threadgroup stays 2 |

The suffix is empty at rps=1 by construction, so the shipped default
compiles to the byte-identical pipeline name it has today
(`laguna_decode_nvfp4_qkv_h64_r1_v1_lm1…`). A default-path Q1 binary is
therefore not merely numerically equal to the pre-change binary, it is the
same pipeline object; nothing in the certified default path is renamed,
recompiled, or re-cached. That is the property that makes Q1 a legitimate
paired reference rather than a second candidate.

### 2.2 What varies and what deliberately does not

Only `results_per_simdgroup` varies. `num_simdgroups` stays pinned at 2
(line 4979), so the threadgroup stays 64 threads on every rung. This is a
deviation from the brief, which offered the `ns` axis too, and it is the
single most consequential design decision in this experiment — see §3.1.

### 2.3 The Metal body

Ladder-relevant edits, all inside `lagunaDecodeNVFP4QKVLaneMajorSource`
(4968–5046):

- `out_row = tile * (num_simdgroups * results_per_simdgroup) + simd_gid *
  results_per_simdgroup` (4991). At rps=1 this reduces to the shipped
  `tile*2 + simd_gid`.
- scale prefetch becomes `sb[results_per_simdgroup][blocks_per_row]`
  (4995–5015), an outer `r` loop over `out_row + r`. Both scale
  representations (packed-nibble bank via `scale_bases`/`scale_nibbles`,
  and the plain `weight_scales` fallback) are inside the `r` loop, so a
  ladder rung never silently changes representation for some rows.
- one shared `x_thread[16]` load per K-block (5020–5024), reused across
  all `rps` rows. This is the whole point of the transform: the activation
  tile is loaded once and amortized over `rps` weight rows instead of once
  per row.
- `result[results_per_simdgroup]` accumulators (5018), zero-initialized
  from a generated literal list (`resultInit`, 4974).
- inner accumulate `ws + r * in_vec_size_w` (5027–5031) against the
  existing single `ws += block_size / 2` advance (5032) — `ws` remains the
  row-`out_row` cursor and the per-row offset is a pure read displacement.
- per-row epilogue `simd_sum(result[r])` then `projected[out_row + r]`
  (5035–5040), preserving the existing deferred-row-scale suffix.

### 2.4 Why this is bit-identical, argued and not assumed

The output element `projected[j]` is produced by exactly one simdgroup on
every rung. Within that simdgroup the 32 lanes each accumulate
`values_per_thread = 16` products per K-block through the unchanged
`laguna_tail_nvfp4_qdot`, over the same four K-blocks visited in the same
ascending order, with the same `laguna_tail_nvfp4_scale(sb[r][blk])`
factor, and the partial sums are closed by the same `simd_sum` tree. What
changes across rungs is only *which* simdgroup owns row `j` and how many
other rows that simdgroup also owns. Neither appears in the arithmetic.
Float addition is not associative, so this argument has to be about
identity of the reduction tree rather than about "same maths"; it is, and
that is why I claim bit-identity rather than tolerance-equality.

The one thing this argument does **not** cover is the compiler. At rps=16
the live set (`sb[16][4]`, `result[16]`, `x_thread[16]`) is large enough
that the Metal compiler may reassociate or spill; reassociation inside
`qdot` would break bit-identity. That is why identity is *checked* per arm
by golden hash (§1.6) and not asserted from this argument alone.

### 2.5 Dispatch guards

Both call sites gained a divisibility guard before the fast path is taken:

- standalone registry `lagunaDecodeNVFP4QKVLaneMajorKernels` (5049–5053,
  suffix applied at 5053); dispatch guard `rows % lagunaDecodeQKVTilesDivisor
  == 0` at 5091, grid `((rows / divisor) * 64, 1, 1)` at 5101.
- fused gate-appended registry `lagunaDecodeNVFP4QKVGateKernels` (suffix at
  5168); guard at 5215, grid `((heads / 8 + rows / divisor) * 64, 1, 1)` at
  5229.

A failing guard returns `nil` and the runtime takes its real pre-existing
fallback; it is not a trap or a crash. Divisibility in fact always holds on
this model: `rows` is 10240 (h64) or 8192 (h48), both divisible by 32, and
the largest divisor on the ladder is `2*16 = 32`. The guard exists so that a
future head configuration cannot silently produce a truncated or
out-of-bounds grid, which is the failure mode a bare grid-arithmetic change
would have introduced.

Trace strings at 5096–5097 and 5220–5222 print `rps=` and the tile count, so
the readback requirement in §1.6 is satisfied from the binary rather than
from the environment I *believe* I set.

## §3. The two hazards and how they were handled

### 3.1 Hazard (b) — `ns ≠ 2` versus the `gate_sp` grid append — designed out

The fused QKV kernel shares one grid with the gate projection: the gate
occupies threadgroups `[0, heads/8)` and QKV occupies the remainder, with
the QKV tile index recovered as `threadgroup_position_in_grid.x -
tileOffset` (4971–4973). The two halves therefore must agree on
threadgroup *size*, because a Metal dispatch has one threadgroup size for
the whole grid. Changing `num_simdgroups` would have changed the QKV
threadgroup from 64 threads to 32 or 128 while the gate half still assumed
64 — a correctness hazard that would have shown up as wrong logits, not as
a compile error.

I did not guard this hazard, mitigate it, or test around it. I removed the
axis that creates it: `num_simdgroups` is a pinned `constexpr 2`, so the
threadgroup is 64 threads on every rung of the ladder and the gate half is
untouched by construction. The cost is that D44 (the `ns` sweep the brief
offered as an option) is not in this experiment at all. I judged that a
ladder over one clean axis, with the hazard structurally absent, is worth
more to the advisor at a 10:30Z deadline than a two-axis grid whose null
cells I would have to argue were not silent-fallback artifacts. §7 records
this as the primary deviation.

Note that pinning `ns` also pins the *threadgroup count* story: as `rps`
rises the number of threadgroups falls by exactly `rps` and each
threadgroup does `rps`× the work, so total simdgroups fall by `rps` while
threadgroup size is constant. That is precisely the N42 discriminator's
axis from R117-C — residency, with threadgroup size held fixed — rather
than the confounded "smaller grid" axis.

### 3.2 Hazard (a) — silent fallback masquerading as a null

The real risk in any geometry ladder is that a rung fails to select the
fast path and reports the *fallback* time as if it were the geometry's
time. A null then means "I did not run your kernel", which is
indistinguishable from "your kernel does not matter" unless you check.

Three defences, all pre-committed in §1.6:

1. the trace readback (`DARKBLOOM_TRACE_FUSION=1`) prints the pipeline name
   including `_qrps<N>` and the tile count, so arm identity is read from
   the dispatch and not from my shell;
2. the golden hash is recorded per run by the certify harness, so an arm
   that quietly changed numerics cannot be reported as a timing result;
3. the divisibility guard is the only way to reach the fallback, and §2.5
   shows it cannot fire on this model's shapes — so on this host a null is
   a real null.

Evidence collected for (1) is in §4.3.

## §4. The ladder

### 4.1 The arms actually run, and the two campaigns

All timing is this host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU
generation 16. Instrument is `research/maple-nezuko-r107j-certify.sh`,
which drives `./benchmark.sh --local-submit` (1023 scored decode steps,
end-to-end wall), rotates the within-block arm order every block, and
writes its TSV incrementally so a truncated campaign still yields whole
blocks. Every arm reaches the kernel through the same env-var route, so
the cost of the route itself cancels in every paired difference. `Q1` is
the reference arm and is the **shipped default**: `rps = 1` produces the
empty geometry suffix (§2.1), so `Q1` is byte-identical to the base
pipeline, not merely numerically equal to it.

| campaign | session | arms | blocks | status |
| --- | --- | --- | --- | --- |
| 1 | `20260811T091536Z` | `Q1`, `Q8` | 1 of 3 | cancelled at 09:23:40Z after block 1, deliberately |
| 2 | `20260811T092338Z` | `Q1`, `Q2`, `Q4`, `Q8` | 3 | full |

Campaign 1 was a two-arm bracket: check the far rung first, on the theory
that if `Q8` did not win there was no interior optimum worth resolving. It
did not win, by a wide margin, so the bracket had done its job after one
block and the remaining wall clock was worth more spent on the shape
between `Q1` and `Q8`. That decision and its reasoning were committed as
§1.8 at 09:23Z, before campaign 2 produced any data. `Q16` was declined;
§8 item 6 re-argues why.

Two bookkeeping reconciliations, both mine to own:

- §1.8 logged the pivot as a **3-arm, 9-run** plan (`Q1`, `Q2`, `Q4`).
  What actually launched was **4-arm, 12-run**: I kept `Q8` in campaign 2
  rather than trusting campaign 1's single block for the one rung that had
  already moved, because a one-block effect is not an effect. So the
  executed design is a superset of the logged one, and `Q8` ends with 4
  blocks total (1 from campaign 1, 3 from campaign 2) while `Q2` and `Q4`
  have 3. Every interval in §4.4 is computed **within campaign 2 only**, on
  3 blocks per arm, so the arms are compared on equal footing; the pooled
  4-block `Q8` level appears only in the W&B log.
- Campaign 1's cancel (09:23:40Z) and campaign 2's session stamp
  (09:23:38Z) are 2 s apart because I staged the second launch while the
  first was still draining its final run; the two sessions share no run.

Raw TSVs for both campaigns are committed under `research/r122b-runs/`.
The `head` column changes between blocks of campaign 2 because
documentation commits landed while it ran. The check that no *code* moved
under the campaign is `git diff a5746c6f..HEAD -- Sources/` being empty,
which it is. The constant golden hash of §4.2 is **not** that check: it
shows every arm computed the same tokens, which is exactly what a
successful residency change is supposed to do, so it cannot distinguish a
frozen `Sources/` from a changed-but-still-bit-identical one.

### 4.2 Bit-identity: measured, not argued

Every run of every arm in both campaigns reports `passed=true` and the
**same** golden hash over its 1023 decode steps:

```
f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
```

One hash, every rung, every block. This is the §2.4 identity argument
discharged empirically, including its compiler caveat: the reassociation
concern in §2.4 was that a compiler might contract or reorder the
per-row accumulation differently once the accumulator became an array, and
a single differing token anywhere in 1023 steps would have shown up as a
different hash. None did.

So the ladder is a pure timing result. Nothing below trades accuracy for
speed, and no rung would have needed a correctness argument to ship.

### 4.3 Hazard (a) — silent fallback — is excluded by the timings themselves

§3.2 pre-committed to proving that a null was not just the dispatch guard
rejecting the new geometry and quietly running the old kernel. The plan was
a trace run. It turned out not to be needed, because the data exclude the
hazard more directly than a trace would:

- Bit-identity alone cannot exclude it — a silent fallback would also be
  bit-identical, which is exactly why §3.2 flagged it.
- But a silent fallback would also be **time-identical**, and the arms are
  not time-identical. `Q2`, `Q4` and `Q8` each differ from `Q1` by an
  interval that excludes zero, and `Q8` differs from `Q2` and `Q4` by far
  more than the block-to-block spread (§4.4). A fallback path cannot
  produce a large `Q8`-specific regression from a parameter it ignored.
  (`Q2` and `Q4` are close to each other — that is the finding of §5.4, not
  a fallback signature, because both are still clearly separated from
  `Q1`.)

This argument only reaches as far as the resolved arm. `Q8`'s regression is
resolved at 3 blocks (§4.4) and cannot come from a code path that ignored
the parameter. `Q2` and `Q4` are **not** individually resolved, so for those
two rungs the timing does not exclude a fallback and the exclusion rests
entirely on §2.5's divisibility argument — `2·rps` divides both 10240 and
8192 exactly for every rung run, so the guard cannot fire. I did not run
the trace, and the honest statement is that hazard (a) is excluded by
construction for all rungs and additionally by measurement for `Q8` only.

### 4.4 The measured ladder

Levels are whole-model end-to-end decode rates over 1023 scored steps
(CENSUS, host M4 Pro). Deltas are paired on the block (MARGINAL). `n = 3`
blocks for every arm in campaign 2.

| arm | rps | level µs/token | sd | cv% | Δ vs `Q1` (mean) | t-CI95 on the mean | covers 0? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Q1` | 1 | 8918.96 | 21.45 | 0.24 | — (reference) | — | — |
| `Q2` | 2 | 8950.29 | 7.58 | 0.09 | **+31.33** | [−36.06, +98.72] | yes |
| `Q4` | 4 | 8975.75 | 15.73 | 0.18 | **+56.79** | [−13.93, +127.51] | yes |
| `Q8` | 8 | 9124.84 | 8.32 | 0.09 | **+205.88** | [+151.67, +260.08] | **no** |

Campaign 1's independent `Q8` block agrees: +186.3 µs/token, inside the
`Q8` interval above.

Every one of the nine paired block differences is positive:

| arm | block 1 | block 2 | block 3 |
| --- | --- | --- | --- |
| `Q2` − `Q1` | +48.09 | +0.04 | +45.87 |
| `Q4` − `Q1` | +49.58 | +32.62 | +88.17 |
| `Q8` − `Q1` | +205.12 | +184.45 | +228.06 |

**What is and is not resolved.**

- **`Q8` is resolved and large**: +205.9 µs/token, +2.31 % of decode wall,
  interval excluding zero by a wide margin, and reproduced in a second
  independent session.
- **`Q2` and `Q4` are directionally positive but not individually
  resolved.** Their t-intervals cover zero, because `n = 3` blocks gives
  `t(0.975, 2) = 4.303` and a paired sd of ~27–28 µs/token, i.e. a
  ±68–71 µs half-width against effects of +31 and +57 µs. This
  instrument needs roughly 8–10 blocks to resolve a +30 µs effect, and the
  deadline bought 3.
- The **joint** claim is much better supported than any single small rung:
  6 of 6 `Q2`/`Q4` block differences are positive, exact two-sided sign
  test `p = 0.031` on the null that neither rung is slower. Caveat: those
  six differences share their `Q1` term within a block, so they are not
  fully independent and 0.031 is optimistic. With `Q8` included, 9 of 9 are
  positive.
- **The ladder is monotone in the point estimate** — +31.3, +56.8, +205.9
  — but `Q4 − Q2` is +25.5 µs against a spread that cannot resolve it, so
  "monotone" is a property of the point estimates, not an established
  ordering between the two small rungs.

**One honest note about the two interval methods.** The pre-registered
decision rule uses a percentile block bootstrap on the median, and that
method reports "excludes zero" for `Q2` and `Q4` as well. At `n = 3` its
95 % percentile interval is exactly `[min, max]` of the three observed
differences, so it **cannot** cover zero whenever all three share a sign.
That is an artifact of the resample size, not evidence. The t-interval is
the honest one at this block count and the table above reports it. The
disagreement is recorded rather than resolved by picking the friendlier
method.

**Diagnostics.** No correctness failures in 12 runs. Prefill differences
are neutral for every arm (all intervals cover zero) and are in any case
not interpretable on this host (§7.2). The position OLS flags an ordering
confound for `Q2` only (slope +11.7 µs/slot, CI [+5.6, +17.9]); the
position-adjusted `Q2` intercept is +35.2 µs/token, slightly *worse* than
the unadjusted +31.3, so the confound is not hiding a `Q2` win. `Q4` and
`Q8` show no ordering confound.

**Verdict.** No rung of the ladder is faster than the shipped `rps = 1`
default. `Q8` is decisively slower. Nothing here is a candidate to land,
and per the assignment's landing rule no branch was prepared.

## §5. Mechanism

### 5.1 The port walks the axis in the wrong direction, and I should have seen that first

R117-C's win was `results_per_simdgroup` **4 → 2** on the o_proj NVFP4 QMV:
fewer rows per simdgroup, therefore *more* simdgroups for the same output,
therefore more concurrent requests in flight. The win was "move toward the
`rps = 1` end of the axis".

The decode QKV lane-major kernel **already sits at `rps = 1`**. It is
already at the most-simdgroups end of the same axis. So the brief's ladder
`Q2 → Q4 → Q8 → Q16` does not port R117-C's move; it explores the only
direction R117-C's own result says is worse. The ladder is a
one-sided walk away from the incumbent, and a one-sided walk away from the
incumbent has one likely outcome.

This is not hindsight from the numbers. It is derivable from the
parameterization in §2 plus the R117-C direction, both of which existed
before the first run. Stating it as the headline is the honest reading:
the experiment was mis-specified as a "port", and the corrected statement
of what it measured is *how steeply the QKV kernel degrades as residency
is removed*. That is a real measurement — §5.4 gets a mechanism constraint
out of it — but it was never going to be a win.

The faithful port of R117-C to QKV would have to go **below** `rps = 1`,
i.e. split one output row across more than one simdgroup. That is not
expressible in this parameterization at all; it is the `ns`/split-K axis
that §3.1 deliberately designed out (D1) and that §8 item 4 proposes.

### 5.2 The null was predictable from a number in my own file

`decode_nvfp4_qkv_h64` moves 1342.1 µs/step at **242.1 GB/s = 94.3 % of
this host's 256.7 GB/s measured streaming peak**
(`research/nezuko-r117-stage0-attn-byte-floor.md:110-116`, re-derived in
`research/nezuko-r117-c-final-report.md:87-90`). `qkv_h48` is at 92.8 %.

Two consequences, both available pre-registration:

1. The entire remaining inefficiency is ≤ 5.7 % of `qkv_h64`'s own time
   (≤ 76.5 µs/token) plus ≤ 7.2 % of `qkv_h48`'s (≤ 26.2 µs/token) — a
   **family cap of ≈ 103 µs/token** even if a change captured *all* of the
   gap to measured peak on both halves. The earlier "≤ 77 µs" figure in my
   notes was the `h64` half only and understated the ceiling by a quarter;
   the honest number is 103, and the brief's `-60 … -200 µs` band still has
   half its range outside it. I signed that band in §1.2 anyway.
2. `rps` cannot reduce weight bytes — the weight stream is read exactly
   once per row regardless of rung (§1.5). It can only reduce **activation
   re-reads**, and §1.5 argues those are ~77 % cache-served. So the
   mechanism available to `rps` acts on a fraction of a fraction.

The correct prior was therefore ≈ 0 expected gain with real downside, and
the correct recommendation was to not spend twelve runs on it. The number
that says so was in a file I wrote myself, three experiments earlier. This
is the single most useful thing in this report and it is a criticism of my
own selection, not of the brief.

The contrast with o_proj is the whole story: `oproj_act_h48` sits at
**83.4 %** of peak and `oproj_act_h64` at **90.7 %**. o_proj had
headroom to recover; QKV does not. "Same kernel family, same
parameterization, therefore same opportunity" is exactly the inference
that achieved-bandwidth accounting exists to block.

### 5.3 Why o_proj had that headroom — the in-flight-bytes floor

Sustaining ~230 GB/s per part against a 400–600 ns loaded LPDDR latency
requires roughly **4.6–7 KB in flight per core** (Little's law on the
measured rate and latency). At `rps = 4` the o_proj QMV offered about
25.6 simdgroups/core, which at ~0.86 load duty and 256 B per outstanding
request is ≈ 5.6 KB/core.

I have to be honest about what that arithmetic does and does not say. 5.6 KB
is **122 % of the low end** of the 4.6–7 KB band, not "80 % of it" as an
earlier draft of this section claimed — it sits *inside* the band, in its
lower third. So the strongest available statement is that o_proj at
`rps = 4` was **marginal** on in-flight bytes and that doubling the offered
simdgroups moved it comfortably clear, not that it was starved. Predicted
recovery on that reading is ≈ 65 µs/token against a measured
−82.4 µs/token: same order, right sign, but a marginal-to-clear transition
is a weaker premise than a starved-to-fed one. **R117-C's −82 µs is
therefore not fully explained by this model**, and I am recording that as an
open item rather than papering over it. The prediction the model does make
cleanly — that a kernel already at 94 % of peak has nothing for `rps` to
recover — is the one R122-B tested, and it held.

So the "optimum at 51.2 simdgroups/core" I reported in R117-C was a
**floor, not an optimum**: 51.2/core was the first rung that cleared the
in-flight requirement, and rungs further along would have cleared it too.
§7.2 already recorded that correction; the R122-B data sharpen it, because
QKV's `rps = 1` offers 512 simdgroups/core — ten times the R117-C constant
— and is nonetheless the best rung on the ladder.

### 5.4 What the ladder's *shape* falsifies, including my own replacement model

Offered simdgroups per core, this host (20 GPU cores, `h64` grid of
10240 rows, 2 simdgroups per threadgroup, `2·rps` rows per threadgroup):

| rung | threadgroups | TGs/core | simdgroups/core offered | resident, cap 96/core |
| --- | --- | --- | --- | --- |
| Q1 | 5120 | 256 | 512 | 96 |
| Q2 | 2560 | 128 | 256 | 96 |
| Q4 | 1280 | 64 | 128 | 96 |
| Q8 | 640 | 32 | 64 | **64** |
| Q16 | 320 | 16 | 32 | **32** |

The grantable ceiling of ≈ 96 simdgroups/core is tanjiro's independently
measured constant (`research/tanjiro-pr-gathergemm-coresidency.md:443-452`).

**Offered is not resident.** Q1, Q2 and Q4 all saturate the same 96/core
ceiling. Any model in which time is a function of *resident* simdgroups
therefore predicts **Q1 = Q2 = Q4, flat**, with the first regression at
Q8. My §1.7 single-wave model is exactly such a model, and it is worse
than that: its constant was 51.2/core, which Q8's 64/core still clears, so
it predicted **no regression anywhere on the ladder**.

The data (mean Δ vs Q1, µs/token): **Q2 +31.3, Q4 +56.8, Q8 +205.9**.

The shape is **monotone and super-linear in `rps`** — every rung is slower
than the last, and the last step is 3.6× the sum of the first two. It is not
the "flat then cliff" a residency-only account predicts, and it is not the
"step then plateau then cliff" an earlier draft of this section called it. I
have to be careful about how much of that shape is real:

- **Q8 is real.** +205.9 µs/token, CI95 [+151.7, +260.1], t = 16.3, all four
  blocks positive. The 51.2/core model is refuted; the 96/core ceiling
  correctly locates *where* the cliff falls — Q8 is the first rung whose
  offered simdgroups drop below the ceiling.
- **Q2 and Q4 are point-estimate positive with intervals covering zero**
  (+31.3 [−36.1, +98.7]; +56.8 [−13.9, +127.5]). All six per-block
  differences are positive, which is suggestive, but at three blocks the
  paired interval is wide and I will not upgrade "monotone in the point
  estimates" to "significantly non-flat". The one thing these two rungs
  establish at ranked strength is that **neither is a win**, which is all
  the ladder needed to decide.

#### The request-count account of the Q8 cliff is refuted by my own arithmetic

The tempting story is that Q8 starves the memory system: 64 simdgroups/core
instead of 96, so fewer outstanding loads, so less latency hiding. Run the
same Little's-law arithmetic §5.3 used and it collapses. At Q8, 64
simdgroups/core × ~0.86 load duty × 256 B per outstanding request is
≈ **14.1 KB/core in flight** — two to three times the 4.6–7 KB the measured
230 GB/s actually requires. Q8 is not request-starved on this model. Nor
should it be: the kernel measures 94.3 % of peak at Q1, and dropping to 64/core
leaves it with more than double the in-flight bytes needed to hold that rate.

So an in-flight-bytes shortfall cannot be the mechanism, and I am stating the
objection rather than leaving the two sections quietly inconsistent.

What survives is not a request-count argument but a **duty-cycle one**. The
0.86 figure is not a constant of nature; it is what a core achieves when
several independent waves of work are resident and one can issue while
another stalls. At Q1–Q4 the core holds 96 grantable simdgroups, i.e. 2–6
waves of concurrently-schedulable work, and any stall is backfilled. At Q8
the core holds exactly **one** wave of 64: when it stalls on a scale/bias
load or a dependent FMA chain, **there is nothing else to run**. The
in-flight bytes at the instant of issue are ample; the fraction of time
spent issuing is not. Oversubscription, not request count, is what Q1 buys.

#### My §1.7 model got the ordering right and every sign wrong

§1.7 predicted, before any data, that `Q4 → Q8` would be the **largest**
step and `Q1 → Q2 → Q4` the smaller ones. That ordering is exactly what
happened (+31.3, +56.8, +205.9). What inverted is the **sign of every
step**: I predicted the ladder climbed toward an optimum at Q8, and it
descends from an optimum at Q1. Calling §1.7 simply "refuted" in §1.8 was
too coarse; the structure it identified is right and its direction is
backwards.

The repair is to read the wave count as a proxy for oversubscription rather
than for coalescing. Waves of 96 grantable simdgroups per core:
`W = 6, 3, 2, 1` for Q1, Q2, Q4, Q8. A latency-hiding tail of the form

```
Δ(rps) = c · (1/W(rps) − 1/6)
```

fits each rung with `c = 144, 171, 247 µs/token` for Q2, Q4, Q8. The shape
is right — a `1/W` tail is monotone and super-linear in `rps`, which is what
the data are — and the drift in `c` is informative: the model
**under-predicts the Q8 cliff by ~1.7×** relative to a constant fitted on
Q2. That residual is the part of the cliff that oversubscription does not
explain, and it is the room left for a second, rung-specific mechanism at
`rps = 8`.

#### The leading candidate for the residual, with its arithmetic corrected

At `rps = 8` per-thread state is `result[8]` plus `sb[8][4]`, an estimated
55–75 registers against 25–35 at `rps = 1`. That is the range in which an
Apple GPU crosses an occupancy tier or begins spilling.

The spill arithmetic in my earlier draft did not add up, so here it is
correctly. Spill traffic on the order of 2.6 MB/call against a 10.5 MB
weight stream is up to **+25 %** of kernel time if every spilled byte
reaches DRAM — not the "+10–15 %" I wrote. And the observed cliff beyond the
Q4 step is ≈ +149 µs on the family's 1705 µs/step, i.e. **8.7 %**, not the
11 % I wrote. The comparison therefore runs the other way from how I first
framed it: **the observed cliff is well under what full spill-to-DRAM would
cost**, which is consistent with either a partial spill that mostly hits
cache, or with a single occupancy-tier drop and no spill at all. Both remain
open; the arithmetic no longer pretends to choose between them.

My best current reading, offered as a hypothesis and not a finding: the Q8
cliff is a **register-file occupancy-tier crossing** between `rps = 4` and
`rps = 8`, compounding the `1/W` oversubscription tail, with i-cache
pressure from the ×8 unroll as the runner-up. I did not run the ISA dump
that would separate these, and I am not going to claim one from a monotone
curve. §8 item 1 is that experiment and it costs **zero timing runs**.

### 5.5 What this hands the campaign

- **A negative constraint with a threshold, not just a null.** Do not
  spend draws on `rps` ladders for decode kernels already above ~90 % of
  measured streaming peak; the achievable band is smaller than the
  code-shape penalty the parameterization itself introduces. The two QKV
  kernels (94.3 %, 92.8 %) are in that class. The advisor's decision to
  decline `F8 sliding_fused_attn_ring_v1` because it already sits at
  51.2 sgs/core reached the right answer, but 51.2 is a floor and not the
  right test; achieved bandwidth is.
- **A corrected reading of R117-C.** The o_proj win was recovery of an
  in-flight-bytes deficit on a kernel with 9–17 % of headroom, not the
  discovery of a residency sweet spot that generalizes. Kernels with no
  headroom have nothing to recover.
- **The axis for QKV, if anyone wants one, is split-K, not `rps`.** It is
  the only direction on this axis that R117-C's result actually endorses,
  and it is blocked today only by the shared gate/QKV threadgroup size
  (§3.1).

## §6. C=40 extrapolation

The ranked host is an M5 Max. I did not measure it and I did not measure
its GPU core count; the extrapolation below is model-based and is the
weakest claim in this report.

Offered simdgroups per core scale as `512 / (rps · C/20)`. Holding the
96/core grantable ceiling as a per-core property:

| rung | offered/core at C=20 | offered/core at C=40 | resident at C=40 |
| --- | --- | --- | --- |
| Q1 | 512 | 256 | 96 |
| Q2 | 256 | 128 | 96 |
| Q4 | 128 | 64 | **64** |
| Q8 | 64 | 32 | **32** |

The cliff **moves one rung earlier**, from Q8 to Q4. Combined with the
rung-insensitive `rps > 1` step of §5.4, which is core-count independent, the
falsifiable prediction for a 40-core part is:

1. Every rung still loses. There is no `rps > 1` rung that wins on a wider
   part, because wider parts underfill sooner.
2. Q2 loses by approximately the same ~+50 µs/token step as here, since
   both Q1 and Q2 remain ceiling-saturated at C=40.
3. Q4 crosses from "step" to "cliff" and should regress markedly more than
   the ~+50 µs/token measured here — the Q4/Q2 gap is the sharp test.
4. Q8 is worse than here.

Two honest caveats. First, prediction 3 is the only one that discriminates
this model from "any `rps > 1` is just worse", and it needs ranked-host
data to test. Second, if the Q8 cliff is register spill rather than
underfill (§5.4, unresolved), the extrapolation is wrong in its
interesting part: spill is core-count independent, so Q4 would stay at the
step and only the constants would move.

The actionable consequence does not depend on which is true: **no ranked
draw should be spent on this ladder.** Every rung loses on the measured
host, and both surviving mechanisms predict the ranked host is no kinder.

## §7. Deviations and corrections log

### 7.1 Deviations from the brief

| # | Deviation | Reason |
| --- | --- | --- |
| D1 | The `num_simdgroups` (`ns`) axis, offered by the brief as D44, is **not** in this experiment. `ns` is a pinned `constexpr 2`. | It is the sole source of hazard (b). Designing the hazard out beat guarding it under a 10:30Z deadline. §3.1, §8 item 4. |
| D2 | The ladder was **not** run as a single 5-arm campaign. | Arm count multiplies wall clock directly at ~183 s/run and the deadline admits roughly 12 runs. §4.1 records the arms actually run and why that subset. |
| D3 | Added a pre-data addendum (§1.7) that the brief did not ask for. | It reconciles my own R117-C constant with tanjiro's independently measured grantable ceiling and turns a loose "interior optimum" prior into a rung-level prediction. Committed before any run finished (`b02f7965`) so it is falsifiable rather than retrofitted. |
| D4 | Added the shape test and the null-work discriminator proposal (§1.3, §8 item 5), which the brief did not request. | The brief's ladder cannot distinguish residency from activation re-read volume. Saying so explicitly is worth more than reporting a ladder as if it were clean. |
| D5 | The arm set changed **mid-campaign**, at 09:23Z after block 1 of campaign 1, from `Q1/Q8` bracket-first to the full `Q1/Q2/Q4/Q8` ladder; `Q16` was dropped. | Block 1 showed Q8 losing by +186 µs, which refuted my own §1.4 refuter #2 and made the bracket's purpose (find the interior optimum between Q1 and Q8) moot. The interesting question became the *shape* between Q1 and Q8, so the runs went there. Logged in §1.8 before any further data. Q16's decline is re-argued in §8 item 6. |
| D6 | §8's pre-registration item 1 — "settle C=40 with one paired ranked draw" — was **withdrawn**, and §8 now opens with an explicit instruction not to spend a ranked draw on this ladder. | A ranked draw is worth spending to choose between rungs that might win. Once every rung lost locally, and once both surviving mechanisms predicted the ranked host is no kinder (§6), the draw buys nothing. Recording the withdrawal rather than quietly deleting the item. |

### 7.2 Corrections to my own earlier claims

Five corrections were made to *this document* after a critical re-read of my
own arithmetic, all after the data were final and none of them changing a
measured number:

- **"≤ 77 µs/token" understated the family cap.** That was `qkv_h64`'s 5.7 %
  gap alone; adding `qkv_h48`'s 7.2 % gives ≈ **103 µs/token** for the QKV
  family. §5.2 now carries the corrected figure, and §8 item 4 inherits it as
  the bound on split-K.
- **"≈ 80 % of the low end" was a mislabel of my own division.** o_proj at
  `rps = 4` had ≈ 5.6 KB/core in flight, which is **122 %** of the 4.6 KB low
  end — inside the required band, not below it. §5.3 is downgraded from
  "starved" to "marginal", and R117-C's −82 µs is now explicitly recorded as
  *not fully explained* by the in-flight-bytes model.
- **A request-count account of the Q8 cliff is refuted by that same
  arithmetic**, and I nearly shipped it. 64 simdgroups/core × 0.86 duty ×
  256 B ≈ 14.1 KB/core, 2–3× the requirement. §5.4 now states the objection
  and replaces the account with a duty-cycle/oversubscription one.
- **The spill arithmetic did not add up.** 2.6 MB spill against a 10.5 MB
  weight stream is up to **+25 %**, not +10–15 %; the cliff beyond the Q4
  step is +149 µs on 1705 µs = **8.7 %**, not 11 %. Corrected, and the
  conclusion inverts: the cliff is *smaller* than full spill would cost, so
  partial spill or a single occupancy-tier drop both remain live.
- **Calling §1.7 "refuted" in §1.8 was too coarse.** §1.7 predicted `Q4→Q8`
  as the largest step and `Q1→Q2→Q4` as smaller ones, which is exactly the
  observed ordering; what it got wrong is the **sign of every step**. §5.4
  now reports the salvaged `Δ = c·(1/W − 1/6)` form, its fitted `c` values,
  and the ~1.7× residual it leaves at Q8.
- **The "optimum at 51.2 simdgroups/core" framing from R117-C was wrong,
  or at least badly under-determined.** I reported a constant where the
  data supported a *threshold*. §1.7 reframes it as "the largest residency
  that still fits inside one grantable wave", which fits the same R117-C
  points, additionally explains why `R1` at 102.4/core needed two waves,
  and — unlike a bare constant — makes a rung-level prediction for a kernel
  I had not yet touched. Note the direction of this correction: it makes my
  previous result *less* special, not more.
- **My §1.7 replacement model is refuted too, and by its own arithmetic.**
  §1.7 predicted an argmax at Q8 from a single-wave `ceil(residency/96)`
  story built on the R117-C constant of 51.2 simdgroups/core. Two errors.
  (i) I wrote residency where I meant *offered* simdgroups: `rps = 1`
  offers 512/core on this host, and with a 96/core grantable ceiling the
  resident count is 96 at Q1, Q2 **and** Q4 alike. Offered is not resident,
  and confusing them is what made a flat region look like a ramp. (ii) With
  51.2/core as the threshold, Q8's 64/core still clears it, so the model
  predicted no regression at any rung — while Q8 loses ~190 µs/token. §5.4
  works through both. The salvageable part is that the 96/core ceiling
  correctly locates *where* the cliff falls; the constant I contributed
  myself does not.
- **Prefill on this host is not evidence for anything on the ranked host.**
  Recorded again rather than assumed: this is an Apple GPU generation 16
  part, it does not select the `_nax` prefill kernels the ranked M5 uses,
  and every arm here — including untouched controls — fails the prefill
  floor at `prefill_speedup ≈ 0.33`. That is a property of the host, not an
  effect of the change, and no prefill number in §4 should be read as a
  ladder result.

### 7.3 What I did not verify

- No ranked-host measurement of any kind. Every number in §4 is M4 Pro,
  20 GPU cores.
- No `ns` variation, hence no coverage of the threadgroup-size axis.
- No ISA/register-pressure inspection, so the top-of-ladder register
  confound (§2.4, §1.3) remains open rather than excluded. This is the one
  omission that materially weakens the report: it leaves the Q8 cliff
  attributable to either underfill or spill (§5.4), and those two accounts
  disagree about the ranked host (§6). §8 item 1 is the fix.
- No row-sequential control at `rps = 8` geometry, which is the cheap
  experiment that would have partly separated them (§8 item 2). It was identified
  too late in the window to build and time.
- No null-work arm, so the residency/re-read collinearity of §1.3 stands
  as conceded rather than broken.
- I fired no official submission, per the assignment's explicit
  reservation of that channel to the advisor.


## §8. What I would do with two more hours

Ordered by expected value per hour, and written so the advisor can hand any
one of them to another student without reading the rest of this report. The
ordering rule I applied: **anything that costs zero timing runs goes first**,
because the campaign's scarce resource is quiet-host wall clock, not ideas.

Item 0, stated first because it is a *don't*: **do not spend a ranked draw
on any rung of this ladder.** §6 gives the reasoning. An earlier draft of
this section proposed exactly that draw; the completed ladder makes it a
waste, since every rung loses locally and both surviving mechanisms predict
the ranked host is no kinder.

1. **Read the register and occupancy facts straight off the toolchain —
   zero timing runs.** Two static measurements settle most of §5.4's
   ambiguity without a single benchmark:
   - Dump the generated ISA per rung with
     `research/maple-nezuko-r100c-dump-msl.sh` and read off spill/reload
     ops, load batching, and code size at `rps = 1, 2, 4, 8`. A spill at
     `rps = 8` and none at `rps = 4` is the cliff, found in minutes.
   - Query `MTLComputePipelineState.maxTotalThreadsPerThreadgroup` for each
     rung's compiled pipeline. That number is the driver telling you the
     occupancy tier it assigned given the kernel's register footprint. If it
     drops between `rps = 4` and `rps = 8`, the occupancy-tier account of
     §5.4 is confirmed directly, and the `1/W` residual has its explanation.

   I did not do this inside the window and it is the omission I most regret,
   because it is the cheapest evidence in the whole report.
2. **Then, if item 1 is ambiguous, run a row-sequential control at `rps = 8`
   geometry.** Keep the `rps = 8` dispatch exactly — 640 threadgroups, 64
   threads, 8 consecutive rows per simdgroup — but process those 8 rows *one
   at a time* with the verbatim `rps = 1` inner loop: reload the activation
   tile per row, one accumulator, one `simd_sum` per row. It is structurally
   bit-identical for the reason §2.4 gives.

   Be precise about what it holds fixed: it fixes **dispatch geometry**
   (threadgroup count, wave count, and hence the `1/W` oversubscription
   term), while *lowering* register pressure back toward `rps = 1`. It does
   **not** hold achieved occupancy fixed — if the driver re-tiers the
   pipeline because the register footprint fell, occupancy moves too, which
   is exactly why item 1's `maxTotalThreadsPerThreadgroup` query should be
   read first for the same variant. With that caveat:
   - `t(seq-8) ≈ t(rps = 1)` points at the fused inner loop's register
     footprint rather than the dispatch shape.
   - `t(seq-8) ≈ t(rps = 8)` points at the dispatch shape — the `1/W` tail —
     rather than registers.
   - Anything in between is the more likely outcome given §5.4's two-term
     fit, and should be read as an apportionment between the two terms, not
     as a verdict for either.
3. **Replace residency with achieved bandwidth as the campaign's
   kernel-selection filter, and publish the table.** §5.2 is a
   selection-process failure, not a measurement failure: the number that
   predicted this null was already written down in my own earlier report.
   The fix is one table over every decode kernel — bytes/step, µs/step,
   GB/s, and percent of the 256.7 GB/s measured streaming peak — used as a
   gate before any geometry experiment is assigned. Kernels above ~90 % are
   off the list for bandwidth-shaped changes; the headroom is not there.
   The census rows for the four attention QMVs already exist
   (`research/nezuko-r117-stage0-attn-byte-floor.md:110-116`); extending
   them across MoE and MLP is mechanical and would reprice the remaining
   draw budget. Note the ledger hazard while doing it: a superseded,
   roughly 9 %-high variant of these numbers exists at
   `research/maple-frieren-r94-decode-residue-ledger.md:177-180`.

   This is the highest-value item in the report for the campaign as a whole,
   and it is the one I would hand out first if the goal is score rather than
   understanding this kernel.
4. **Take the QKV kernel down the axis instead of up it — split-K.** §5.1:
   `rps = 1` is already the most-simdgroups end, so the only direction
   R117-C's result endorses is splitting one output row across several
   simdgroups. That is the `ns` axis this experiment designed out (D1,
   §3.1), blocked today only because the fused gate and QKV dispatches
   share a threadgroup size. Splitting the fused dispatch into two
   dispatches frees `ns` at the cost of one extra command-buffer entry.
   Whether that trade is net-positive is measurable, and the R122-A
   busy-vs-gap decomposition alphonse is running is precisely the
   instrument that prices the extra command — so this item is worth much
   more *after* R122-A reports than before.

   Two temperings, and they are severe. First, split-K is bounded by the
   **same ≈ 103 µs/token family cap** as everything else in §5.2: at 94.3 %
   of measured peak there is no more bandwidth to find, and a perfect
   split-K result cannot exceed a few tens of µs/token. Second, split-K
   requires a **cross-simdgroup reduction** — threadgroup-memory partials
   plus a barrier — which is new work on the critical path, and the `1/W`
   model of §5.4 says Q1 already has ample oversubscription, so there is no
   latency-hiding win waiting to pay for that barrier. Both of this report's
   surviving models therefore predict little from split-K. I list it because
   it is the only direction the R117-C evidence actually endorses, not
   because I expect it to win.
5. **Break the simdgroup/re-read collinearity with a null-work arm.** §1.3
   concedes that every rung changes residency and activation re-read volume
   together. The clean discriminator keeps the shipped geometry but reads
   the activation tile `rps` times into a discarded accumulator — same
   bytes, same residency, no useful work removed. Demoted from its
   pre-registration priority because items 1 and 2 are more informative
   about the cliff and cheaper.

   **Implementation hazard, and it would silently void the arm:** a
   *discarded* accumulator is dead code, and the Metal compiler will delete
   the loads that feed it. The arm must consume the dummy result in a way
   the compiler cannot fold away — e.g. accumulate it and add
   `0.0f * dummy` into the real output, or gate a store on a runtime-uniform
   comparison that is always false but not provably so — and the ISA dump of
   item 1 must then confirm the loads actually survived. An arm that
   measures "no difference" because the compiler removed the extra reads
   looks exactly like an arm that measures "re-reads are free".
6. **Re-examine whether a Q16 rung would have added anything.** I declined
   it in §1.8 on clock, and I still think that was right: with Q2, Q4 and
   Q8 all losing, a fourth losing rung buys one more point on a curve whose
   sign is already settled, and its interpretation is confounded between
   "further past the ceiling" and "spilling harder". If items 1–2 resolve
   the cliff's mechanism, Q16 becomes a clean test of that mechanism's
   extrapolation and is worth 3 runs then — not now.

