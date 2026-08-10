# R106-B Stage B — preregistration (written and committed BEFORE any timing arm is run)

Student: maple-nezuko · PR #616 · assignment `maple-r106-b-revert-residual-forensics`
revision `r106-b-rev3` · host: Apple M4 Pro, 20 GPU cores, 1 GPU.

This file is committed before the first timed arm so that the design, the
outcome labels and the stopping rule cannot be chosen after seeing the numbers.
Rules honoured: Rule 40 (named contrast + declared dof), Rule 68
(interleaved contemporaneous control **and** a preregistered revert),
Rule 72 (no post-hoc arm relabelling), Rule 77 (dispatch geometry recorded for
both arms), Rule 86 (`--local-iterate` is never evidence).

---

## 1. Mechanism under test — "H4" head packing of the sliding decode attention kernel

Shipped kernel `laguna_sliding_fused_attn_ring_v1` packs **2 query heads that
share one KV head** into one threadgroup and dispatches
`grid = ((heads/2) * 1024, 1, 1)` = 32 threadgroups of 1024 threads for
`heads = 64`, `kvHeads = 8`, `gqa = 8`.

Each threadgroup streams the whole 512-row sliding window of its KV head:
`512 rows x 128 dims x 2 B x 2 tensors (K,V) = 256 KiB` per threadgroup, so a
call *requests* `32 x 256 KiB = 8.0 MiB` while the *unique* footprint is only
`8 KV heads x 256 KiB = 2.0 MiB`. Request amplification is therefore
`gqa / heads_per_tg = 8 / 2 = 4x`.

The candidate kernel `laguna_sliding_fused_attn_ring_h4_v1` packs **4 query
heads per threadgroup** (`grid = ((heads/4) * 1024, 1, 1)` = 16 threadgroups),
halving request amplification to `2x` (8.0 MiB -> 4.0 MiB requested per call;
unique footprint unchanged at 2.0 MiB).

Why this is not one of the closed families: it is neither a split-K /
flash-decoding / KV-split of the kernel (#196, #566 — those *increase* the
dispatch count and split the reduction), nor a threadgroup-boundary split for
TG-count starvation (#528 / rule 67 — that *raises* the TG count), nor a
barrier/encoder/command-buffer scheduling change (Rule 92), nor a byte
reduction by fusion or redundant-read elimination inside a single threadgroup
(#619) — the *unique* byte count is untouched. It changes only how many query
heads share one threadgroup's KV stream, i.e. the request-side amplification
factor. Dispatch count per decode step is unchanged (Rule 65 has no term).

### Cost model that motivates it (pre-measurement, on the record)

From the R106 dispatch census the sliding attention kernel costs
`22.34 us/call x 30 calls = 670 us/step`. `8.0 MiB / 22.34 us = 375 GB/s`
of *requested* bandwidth, which is above M4 Pro DRAM bandwidth and consistent
with an L2-served request-bandwidth limit; the DRAM-side cost of the 2.0 MiB
unique footprint is only `~8.1 us/call` at 260 GB/s, and the ALU estimate is
`~8.4 us/call`. If the kernel is request-bandwidth-bound, halving requested
bytes should take the call toward the `~11-13 us` ALU/DRAM floor, i.e.
`~300 us/step ~ +4.6 %` of `cs`.

**Named risks, declared before measuring:** (a) register pressure — the
candidate holds 4 head accumulator sets instead of 2 (40 vs 20 live floats on
top of 4 pipeline slots x 8 = 32), so spilling could dominate; (b) 8 epilogue
barriers per call instead of 4; (c) 16 threadgroups on 20 cores leaves 4 cores
idle in the single wave (80 % occupancy — the same 80 % the shipped 32-TG
two-wave schedule achieves, so this is a wash, not a loss).

### Bit-exactness claim (checked, not assumed)

The candidate keeps v1's row->simdgroup mapping, v1's per-head arithmetic order
(scores for the packed heads are interleaved element-by-element in v1's order),
v1's `LAGUNA_RESCALE` sequence, and v1's `outputs4` transpose reduction shape.
Only the *number of heads resident in a threadgroup* changes. The prediction is
therefore **bit-exact equality** with the shipped path, which removes any need
for frieren's #597 margin certificate. This is a falsifiable prediction and is
tested by outcome label **N-CORRECT** below.

## 2. Arms — one binary, gate-selected, interleaved

A single build serves both arms; the gate defaults **OFF**, so the shipped path
is the preregistered revert required by Rule 68.

| arm | env | kernel | grid | threadGroup | dispatches/step |
|---|---|---|---|---|---|
| `C` (control = preregistered revert) | `DARKBLOOM_FUSED_SLIDING_ATTN_H4` unset | `laguna_sliding_fused_attn_ring_v1` | `(32*1024, 1, 1)` | `(1024, 1, 1)` | 30 |
| `H` (candidate) | `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1` | `laguna_sliding_fused_attn_ring_h4_v1` | `(16*1024, 1, 1)` | `(1024, 1, 1)` | 30 |

Rule 33: the candidate kernel name carries the distinct `_h4_v1` suffix, so the
MLX kernel cache cannot alias the two arms inside one process.

## 3. Measurement protocol

* Evidence path: **`./benchmark.sh --local-submit` only** (1023 decode steps).
  `--local-iterate` is used only for (i) a Metal-JIT compile check and (ii) a
  sign triage that selects between the two candidate spellings in §5; it is
  never quoted as evidence (Rule 86), and `research/maple-nezuko-r106b-h4-triage.sh`
  is labelled non-evidence in its own header.
* Order: strictly alternating, starting with `C`, `n >= 3` per arm
  (`C H C H C H`), all runs in one uninterrupted session on an otherwise idle
  host, no other Maple student run and no advisor run concurrent.
* Primary metric: `metrics.decode_seconds_per_token`.
* Contrast: `D_H4 = mean(decode_H) - mean(decode_C)`, converted to us/step and
  to % of `cs` using the campaign constant **1 us/step = 0.015228 % of `cs`**.
* Statistic: paired-by-position differences `d_j = H_j - C_j`, `j = 1..n`;
  reported as `mean(d) +/- t_{0.975, n-1} * sd(d)/sqrt(n)`. **Declared dof = n-1
  with n = 3, i.e. dof = 2** (raised only by adding whole `C H` pairs, never by
  dropping a run).
* Secondary: `metrics.prefill_seconds_per_token` (expected null — the kernel is
  decode-only), `metrics.passed_correctness` must be `true` in every run.
* Stopping rule: fixed at 3 pairs. One extra pair is permitted **only** if the
  `sd(d)`-based CI half-width exceeds 30 us/step, and that extension must be
  recorded in the report.

## 4. Outcome labels (fixed now; Rule 72 forbids relabelling later)

* **V-RECOVER** — `D_H4 <= -5 us/step` and the 95 % CI excludes zero, and the
  candidate is bit-exact: mechanism confirmed, ship to fern's #625.
* **V-ATTRIB** — `D_H4 <= -5 us/step` with CI excluding zero, but the candidate
  is *not* bit-exact: report as a numerics-changing candidate that must go
  through frieren's #597 margin-certificate instrument before any integration.
* **N-RECOVER** — CI includes zero, or `D_H4 > -5 us/step`: the request-side
  amplification is not the binding constraint at this operating point; report as
  a negative result and hand the cost model correction to #625 rather than the
  patch.
* **N-CORRECT** — `metrics.passed_correctness` false in any candidate run, or
  the bit-exactness check fails in a way that is not a pure reduction-order
  difference: candidate withdrawn, no timing claim made.
* **N-RESIDUAL** — already fired in Stage 0 (the frontier-vs-Arm-R residual is
  `+19.405 us/step`, 95 % CI `[-18.156, +56.966]`, covering zero); it is
  recorded here only so the Stage 0 and Stage B labels live in one place.

## 5. Preregistered fallback ladder (each step keeps bit-exactness)

If the triage sign is unfavourable the candidate spelling — not the mechanism —
is changed once, in this fixed order, and only the surviving spelling is taken
into the paired `--local-submit` campaign:

1. **H4/d4** (as written): 4 heads/TG, pipeline depth 4.
2. **H4/d2**: 4 heads/TG, pipeline depth 2 (`i += 2*BN`, 2 slots). Halves the
   live K/V slot registers from 32 to 16 floats, directly targeting risk (a).
   Row->simdgroup order and per-head arithmetic order are preserved, so
   bit-exactness is preserved.

No third spelling will be attempted in this stage. If neither beats the control
the label is **N-RECOVER** and the mechanism is reported closed at this
operating point.

## 6. Verification checklist required before any claim leaves this branch

1. force-clean build from a clean checkout,
2. `swift test --force-resolved-versions`,
3. `research/run_upstream_equivalence.sh` (oracle report marker present),
4. full golden correctness set green in the candidate arm,
5. bit-exactness diff of decode logits, gate ON vs OFF,
6. `senpai/check-editable-budget.sh "$BASE_SHA"` (Rule 75: 3,000,000 B total /
   524,288 B per file),
7. `BASE_SHA=... HEAD_SHA=... .github/scripts/enforce-modifiable-surface.sh`.

No official submission is made from this branch under any outcome
(`senpai/submit-official.sh` is not invoked).
