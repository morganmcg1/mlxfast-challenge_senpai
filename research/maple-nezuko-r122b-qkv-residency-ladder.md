# R122-B — porting the o_proj `rps` residency parameterization to the decode QKV lane-major kernel

Student: maple-nezuko. Assignment `maple-r122-b-qkv-residency-ladder`, revision
`r122-b-rev1`, PR #719. BASE `fa2a81b7624f6afa807830eb9ad7eb6d38c3d11d`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, Apple GPU generation 16.

> **This commit contains §1 only — the pre-registration — and is committed
> before any data exists.** Everything below §1 is a placeholder at this commit.
> §1 is not edited after the first data commit; corrections to it are appended
> to §7 with a timestamp instead.

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

_Placeholder at the pre-registration commit._

## §5. Mechanism

_Placeholder at the pre-registration commit._

## §6. C=40 extrapolation

_Placeholder at the pre-registration commit._

## §7. Deviations and corrections log

### 7.1 Deviations from the brief

| # | Deviation | Reason |
| --- | --- | --- |
| D1 | The `num_simdgroups` (`ns`) axis, offered by the brief as D44, is **not** in this experiment. `ns` is a pinned `constexpr 2`. | It is the sole source of hazard (b). Designing the hazard out beat guarding it under a 10:30Z deadline. §3.1, §8 item 5. |
| D2 | The ladder was **not** run as a single 5-arm campaign. | Arm count multiplies wall clock directly at ~183 s/run and the deadline admits roughly 12 runs. §4.1 records the arms actually run and why that subset. |
| D3 | Added a pre-data addendum (§1.7) that the brief did not ask for. | It reconciles my own R117-C constant with tanjiro's independently measured grantable ceiling and turns a loose "interior optimum" prior into a rung-level prediction. Committed before any run finished (`b02f7965`) so it is falsifiable rather than retrofitted. |
| D4 | Added the shape test and the null-work discriminator proposal (§1.3, §8 item 2), which the brief did not request. | The brief's ladder cannot distinguish residency from activation re-read volume. Saying so explicitly is worth more than reporting a ladder as if it were clean. |

### 7.2 Corrections to my own earlier claims

- **The "optimum at 51.2 simdgroups/core" framing from R117-C was wrong,
  or at least badly under-determined.** I reported a constant where the
  data supported a *threshold*. §1.7 reframes it as "the largest residency
  that still fits inside one grantable wave", which fits the same R117-C
  points, additionally explains why `R1` at 102.4/core needed two waves,
  and — unlike a bare constant — makes a rung-level prediction for a kernel
  I had not yet touched. Note the direction of this correction: it makes my
  previous result *less* special, not more.
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
  confound (§2.4, §1.3) remains open rather than excluded.
- I fired no official submission, per the assignment's explicit
  reservation of that channel to the advisor.

## §8. What I would do with two more hours

Ordered by expected value per hour, and written so the advisor can hand any
one of them to another student without reading the rest of this report.

1. **Close the C=40 question directly instead of extrapolating.** §6 is the
   weakest part of this report and it is weak for a structural reason: the
   wave model's prediction changes *rung* between 20 and 40 cores, so the
   local argmax is not the ranked argmax under the model's own logic. The
   cheap resolution is not more M4 data — it is one paired ranked draw of
   the two candidate rungs. Whoever owns the ranked channel can settle in
   two draws what I cannot settle in two hours here.
2. **Break the simdgroup/re-read collinearity with a null-work arm.** §1.3
   concedes that every rung changes residency and activation re-read volume
   together. The clean discriminator is an arm that keeps the shipped
   geometry but reads the activation tile `rps` times into a discarded
   accumulator — same bytes, same residency, no useful work removed. If
   that arm reproduces the ladder's shape, the mechanism is bytes; if it is
   flat, the mechanism is residency. This is the R117-C `N42` move
   transplanted to the byte axis, and it is the single experiment that
   would most improve the causal claim.
3. **Apply the same parameterization to the remaining decode QMV kernels
   and rank them by residency, not by time.** The §1.7 wave model makes a
   sharp prediction that is testable without any new kernel: kernels whose
   current residency already sits at or below one grantable wave should
   show no gain from an `rps` ladder, and kernels far above it should. The
   advisor's own decision to decline `F8 sliding_fused_attn_ring_v1` on the
   grounds that it already sits at 51.2 sgs/core is exactly this prediction
   used as a filter. Turning that filter into a table over every decode
   kernel would let the campaign spend its remaining draws on the kernels
   the model says are still mispriced, and would falsify the model quickly
   if a low-residency kernel *did* respond.
4. **Test the register-pressure confound at the top of the ladder
   deliberately.** §1.3's shape test is limited because a Q16 regression is
   ambiguous between "past the residency optimum" and "spilling". Dumping
   the compiled ISA per rung (the `r100c-dump-msl` path already exists) and
   reading off register counts and spill traffic would disambiguate it for
   the cost of a build, no timing runs at all. If Q16 spills and Q8 does
   not, the interior-optimum reading of the ladder is safe; if neither
   spills, a Q16 regression is real evidence about residency.
5. **Re-examine whether `ns` is genuinely unavailable or only awkward.** I
   designed hazard (b) out rather than solving it (§3.1), which was right
   under this deadline but leaves a real axis unexplored. The hazard is
   that gate and QKV share a threadgroup size. Splitting the fused
   dispatch back into two dispatches would free `ns` at the cost of one
   extra command; whether that trade is net-positive is measurable, and the
   R122-A busy-vs-gap decomposition alphonse is running is exactly the
   instrument that would price the extra command. That sequencing matters:
   this item is worth much more *after* R122-A reports than before.
