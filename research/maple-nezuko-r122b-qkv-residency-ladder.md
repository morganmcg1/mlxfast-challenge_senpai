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

## §2. The code change

_Placeholder at the pre-registration commit._

## §3. The two hazards and how they were handled

_Placeholder at the pre-registration commit._

## §4. The ladder

_Placeholder at the pre-registration commit._

## §5. Mechanism

_Placeholder at the pre-registration commit._

## §6. C=40 extrapolation

_Placeholder at the pre-registration commit._

## §7. Deviations and corrections log

_Placeholder at the pre-registration commit._

## §8. What I would do with two more hours

_Placeholder at the pre-registration commit._
