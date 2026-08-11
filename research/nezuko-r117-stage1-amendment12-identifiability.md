# Stage 1 amendment 12 — B_act is not identifiable as promised, and what I will fit instead

*maple-nezuko, R117-C, written 2026-08-11 ~04:57Z.*
*Written AFTER the 4-arm pre-flight (n=1 per arm, unpaired) and BEFORE any paired
ladder observation existed. The 25-run ladder was launched at 04:55Z and the first
block had not finished when this file was committed. Every number below that comes
from data comes from the four unpaired pre-flight singles, which are published in
`research/data/nezuko-r117-stage1-preflight.tsv`.*

---

## 1. The problem with the pre-registered fit

Amendment 11 said I would fit `B_act` by regressing paired Δµs on the activation
dose, using `DOSES="R1=943.72,R2=314.57,R8=-157.29"`.

That fit is **not identifiable**, and I want that on the record before I see the
paired numbers rather than after.

Activation traffic in this kernel is

```
act_bytes = num_simdgroups x in_vec_size x 2 bytes x calls
num_simdgroups = outVec / rows_per_simdgroup      (independent of ns)
```

so **activation bytes are an exact linear function of the simdgroup count**. Along the
`ns = 2` ladder (`R8, C, R2, R1`) the byte dose and the parallelism knob move together
with correlation exactly 1.0. A regression of Δ on bytes therefore returns
"bytes + parallelism, bundled", not `B_act` — the identical failure mode I already
had to report for the `OP` rung of the Stage 0b ruler (§2.5 of the final report),
where an arm changed addressing as well as bytes and its apparent τ ran past 1.0.

I will not launder a bundled coefficient as `B_act`.

## 2. What the design *does* identify

The `N4` control breaks the collinearity in one place, because `ns` moves the
threadgroup count at **fixed** simdgroup count and therefore at **fixed bytes**:

| contrast | simdgroups | threadgroups | Δ bytes | isolates |
|---|---|---|--:|---|
| `N4` vs `C` | 512 = 512 | 256 → 128 | **0** | threadgroup packaging, byte-free |
| `R8` vs `N4` | 512 → 256 | 128 = 128 | −157.29 MB | simdgroups + bytes, bundled |
| `R1`/`R2`/`R8` vs `C` | varies | varies | varies | simdgroups + bytes, bundled |

So one factor (packaging) is cleanly identified; the other (simdgroups vs bytes)
is not, by construction.

## 3. The two-form decomposition I will fit, and its pre-registered prediction

Bytes and parallelism are collinear *in the design*, but they are not collinear *in
functional form*: a bandwidth term is linear in bytes, whereas an occupancy term
saturates and is much better described as linear in `log2(simdgroups)`. Two different
shapes through four `ns = 2` design points are identifiable with 3 free contrasts.

Model, fitted on the `ns = 2` arms only:

```
delta_us(sg) = a * log2(sg / 512) + tau_act * 3.8956 * (act_MB(sg) - 314.57)
```

`a` = µs per doubling of the simdgroup count (occupancy), `tau_act` = the byte→time
transfer for activation re-reads, on the same scale as the Stage 0b τ = +0.780.

**Solving this on the pre-flight singles alone** (`R8` +101.03, `C` 0, `R1` −65.17):

| parameter | pre-flight point estimate |
|---|--:|
| `a` (µs per doubling of simdgroups) | **−135.3** |
| `tau_act` | **+0.056** |

**Pre-registered out-of-sample prediction.** `R2` took no part in fitting those two
numbers — it was not in the pre-flight. The model predicts

> **`R2` (rps=2, 1024 simdgroups, +314.57 MB/step) lands at Δ ≈ −66.8 µs/step,**
> i.e. statistically indistinguishable from `R1` (−65.2), because the occupancy gain
> from 1024 → 2048 simdgroups is by then almost exactly cancelled by the byte cost of
> another +629 MB/step. **The ladder should show an interior optimum near rps = 2,
> not a monotone win at rps = 1.**

If the paired ladder puts `R2` near −67 µs/step, the two-form decomposition survives an
honest out-of-sample test and `tau_act ≈ +0.06` is a real, if small, number: activation
re-reads cost about **7 %** of what the Stage 0b scale-plane bytes cost. If `R2` lands
far from −67, the decomposition is wrong and I will report only the bundled coefficient
plus the byte-free `N4` contrast, and say so.

## 4. What is already settled by sign alone

Whatever the decomposition does, the assignment-relevant conclusion is already fixed by
the pre-flight signs and does not depend on any fit:

- a pure byte model at the Stage 0b τ = 0.780 predicts `R1` at **+2868 µs/step** and
  `R8` at **−478 µs/step**;
- observed: `R1` **−65.2**, `R8` **+101.0**. **Both signs are inverted.**

o_proj activation traffic is not a bandwidth lever on this host. The o_proj kernel is
occupancy-limited, not bandwidth-limited, and the 90.9 % / 83.4 % "distance from peak"
figures in the Stage 0 census are therefore **not** headroom that a byte reduction can
collect. That is a correction to my own Stage 0 framing, and I flag it as such.

## 5. Analysis I will run, in order

1. Default paired-difference analyser (`maple-nezuko-r107j-paired-ci.py`) → Δ and CI95
   for `R1`, `R2`, `R8`, `N4` against `C`. This is the primary endpoint.
2. `N4` vs `C` as the byte-free packaging contrast.
3. `R8` vs `N4` as the fixed-threadgroup contrast, reconstructed block-by-block from the
   same rotation (both arms appear in every block, so the pairing is exact).
4. The §3 two-form fit, reported **with** its out-of-sample `R2` test.
5. Bit-exactness: all 25 goldens must equal `f49e4c2cbc0d3ceee9…`, else the arm is void.

Decision rule, unchanged from amendment 11: an arm is reportable as a candidate only if
its paired Δ CI95 excludes the **68.7 µs/step** Rule 105.12 slot floor on the winning
side. `R1` at −65.2 µs/step in the pre-flight sits **just below** that floor, so this is
genuinely undecided and I am not going to pretend otherwise.
