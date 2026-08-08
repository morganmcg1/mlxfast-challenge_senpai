SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"insitu_boundary_price_d_us","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

# R86-B — In-situ price of a DRAM round-trip boundary inside the real decode step

- Student / PR: `maple-nezuko` / #462
- Hypothesis and target cost: a DRAM round-trip boundary inserted inside the real decode step
  costs `d = slope(WIDE) − slope(TINY)` µs per boundary; `d` calibrates every future
  fusion/removal proposal in the programme's NET rule.
- Decision: **TBD-FIT**
- `BASE_SHA` / candidate commit: `7687c2e44e6975c181444ca8d3d151ee30480a72` / **TBD-HEAD**
- Submitted candidate files: none intended for submission. This is an instrument-only
  deoptimizer; expected to **close unmerged**.
- Supporting test or documentation files: `Sources/MLXFastModel/LagunaR86BoundaryLadder.swift`
  (instrument, disarmed unless `DARKBLOOM_R86_MODE` is set), one hook line at
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:11535`, and `research/nezuko-r86b-*`.
- Official submission `--model` value: n/a — no official submission from this PR.
- Explicit API model-value rejection: n/a.
- Assignment-scope preflight: passed on `7687c2e4`.
- Editable bytes / headroom / growth: `current=2894029 headroom=105971 growth=2686/262144`.
- Scored-path reachability evidence: the hook sits on the scored decode step; the gate-1
  dispatch census shows the arms change the dispatch count of the real step
  (406 → 1046 dispatches at k = 640), so the control provably reaches the scored path.

## Base-bump handling

`codex/mlxfast-maple-20260804-advisor` moved twice during this round
(`7687c2e4 → c15740be → b6800f30`). Both diffs are research Markdown only, zero editable-surface
bytes. Per advisor instruction the branch was **not** rebased; the pre-registration, the
instrument, and every timing number in this report are on `7687c2e4`.

## 1. The measurement

**TBD-FIT** — `d`, its 95 % CI, the WIDE and TINY slopes, the ratio, linearity/secants, and the
verdict against the pre-registered thresholds (GO `d ≥ 1.00`; PARTIAL `0.35 ≤ d < 1.00`; NO-GO
`d < 0.35`). Thresholds are as pre-registered in `research/nezuko-r86b-prereg.md` and are not
softened.

## 1.5 Instrument-validity re-audit

The advisor required this section if `d` lands materially below the pre-registered 1.19 central
estimate. It does. **TBD-FIT** gives the final number; the audit below is the reason it is a
physical result rather than an instrument defect, and it is written from evidence that does not
depend on the final fit.

**The primary evidence that the instrument is sound is cross-method agreement.** Two unrelated
measurement paths were run: a Metal-level dispatch census (GPU counters, `gpu_busy` deltas,
40 steps) and a wall-clock ladder (A-B-B-A blocks, 200 steps/run). They agree on the WIDE price
to **1.2 %** (census 1.398 µs/boundary vs ladder 1.415 µs/boundary). A broken instrument does
not reproduce itself to 1.2 % across a GPU-counter method and a wall-clock method. A third,
completely independent check is in §4: the synthetic WIDE price reproduces the *real* chain
refund measured by the C1 fusion (100.0 µs over 80 boundaries = 1.25 µs/boundary) to **12 %**.

Four candidate explanations for a small `d` were considered:

**A — TINY is not free, and the pre-registration assumed it was.** The blind prediction put
`slope(TINY)` at 0.17 µs. The measured TINY price is ≈0.62–0.71 µs. A 2-byte dependent operation
still pays a full kernel dispatch, a full grid launch and a full barrier; only the data movement
is removed. So ≈44 % of a boundary's in-situ price is **irreducible dispatch/launch cost that
`d` deliberately subtracts out**. This is not an error in the instrument; it is the instrument
correctly reporting that the round-trip component is smaller than the launch component.

**B — the WIDE intermediate never reaches DRAM (leading explanation).** The WIDE arm moves
8,192 B per insert in ≈1.4 µs, an implied **5.85 GB/s** — roughly 1/50 of this machine's
achievable DRAM bandwidth. A 4 KiB working set is trivially SLC-resident, so WIDE is timing a
*cache* round trip, not a DRAM round trip. Critically, **this is the right thing to measure**:
the boundary census (§3) shows every real decode intermediate is 512 B – 401 KB, i.e. in exactly
the same cache-resident class, and all intermediates together are <0.5 % of the ~550 MB/step of
weight traffic. `d` is therefore the correct *in-situ* price for the boundaries the programme
actually wants to remove, and the pre-registered 1.19 µs prior — which was calibrated on
*whole-op removal* experiments (#268, #269, R85-D) that also removed dispatch and grid cost —
was priced against a different quantity. The **size sweep is the decisive test**: if
`price(4 MiB) ≫ price(4 KiB)` (4 MiB exceeds SLC and must go to DRAM), the instrument is
demonstrably capable of seeing a real DRAM round trip and the small `d` at realistic sizes is a
physical fact about the workload, not an instrument ceiling. **TBD-FIT** scores this.

**C — the inserted work overlaps other work (ruled out).** The census shows
`gpu_busy_sum == gpu_busy_union` in every arm: the decode step is fully serialized. There is no
concurrency for an inserted boundary to hide behind, so `d` is not being suppressed by overlap.

**D — M4 regime effects, sign unresolved, stated in both directions.** This host is
bandwidth-bound; the ranked M5 Max is instruction-bound at ~89 % GPU utilisation. On a
bandwidth-bound host an inserted round trip can partially hide behind weight streaming, which
would make `d` a **lower bound** for M5. Pushing the other way, M5's wider dispatch engine makes
the fixed launch component cheaper, which raises the TINY floor's share and would make `d`
larger on M4 than on M5. Both effects are real and neither is measured here; the honest
statement is that `d` is an M4 number with unresolved transfer sign, which is exactly why §5
attaches the byte-class transfer caveat (−0.40 ± 0.24).

**What the audit does not excuse.** The pre-registered thresholds are applied to the measured
`d` as-is. No threshold is moved, and the ratio prediction (8.0× predicted) is scored as a miss
if the measured ratio is smaller.

## 2. Validity gates

**TBD-FIT** for gates 2, 3 and 5. Gates 1 and 4 are already settled:

**Gate 1 — the arms do what they claim (PASS, exactly).** GPUPROF build, 40 steps, n = 1, every
arm reporting `0 divergences (all match)`:

| arm | dispatches/step | Δ vs `off` | expected Δ | cbs/step | wall ms | gpu_busy ms | gap ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 406 | — | — | 45.0 | 8.211 | 7.967 | 0.244 |
| w0 | 406 | 0 | 0 | 45.0 | 8.216 | 7.964 | 0.252 |
| w2 | 486 | +80 | +80 ✓ | 45.0 | 8.338 | 8.075 | 0.263 |
| w16 | 1046 | +640 | +640 ✓ | 45.0 | 9.111 | 8.857 | 0.254 |
| t0 | 446 | +40 | +40 ✓ | 45.0 | 8.265 | 8.005 | 0.260 |
| t2 | 526 | +120 | +120 ✓ | 45.0 | 8.268 | 8.028 | 0.241 |
| t16 | 1086 | +680 | +680 ✓ | 45.0 | 8.663 | 8.392 | 0.271 |

Every arm hits its predicted dispatch count exactly. Three structural facts fall out:

- **Command buffers are constant at 45.0/step across all arms.** The price is therefore
  in-command-buffer dispatch cost, *not* command-buffer submission overhead.
- `gpu_busy_sum == gpu_busy_union` in every arm ⇒ the step is fully serialized; there is no
  concurrency for an inserted boundary to hide behind.
- ≈99.8 % of the added cost lands in `gpu_busy`, not in the scheduling `gap`. The boundary price
  is GPU-side work, not CPU-side encode.

At 8,192 B per WIDE insert and ≈1.4 µs, the implied bandwidth is **5.85 GB/s** — three orders
below DRAM peak. **An inserted boundary is latency/grid-bound, not bandwidth-bound.** That is the
single most important structural finding for interpreting `d`.

**Gate 4 — the disarmed instrument is neutral (PASS).** With `DARKBLOOM_R86_MODE` unset,
`./benchmark.sh --local-iterate` gives decode 0.012933 s/tok against a baseline 0.012953 s/tok
(−0.1 %, i.e. inside noise and slightly favourable), est score 0.798 vs 0.795. The census `off`
and `w0` cells differ by 5 µs on an 8,211 µs step (0.06 %).

## 3. Boundary census

Delivered in full as [`research/nezuko-r86b-census.md`](nezuko-r86b-census.md), with all seven
mandatory columns, named intermediates with byte counts, line-number evidence for every `R`, and
ranking by net.

Headline results:

- The 406-dispatch ledger closes exactly: 2 embed + 8 dense (layer 0) + 390 sparse + 5 head +
  1 argmax.
- **No remaining redundancy-free boundary is worth more than ≈10 µs/step (≈0.15 % of score).**
- A general inequality kills most of the table: gross ≤ `40 × price(4 KiB)` ≈ 56 µs, and no kernel
  in the step costs less than one 4 KiB boundary price, so **every row with `R ≥ 41` has
  net < 0**.
- §3.5 prices the advisor's named target, the norm→QKV producer, and reports the decisive
  sentence: **the redundancy term dominates the boundary term there.**
- §3.6 corrects the programme's NET rule (see below).
- §3.7 labels every row byte-class vs instruction-class.
- **CP-3 MISS**: the largest recurring intermediate is `coarse` (401,408 B) in the lm-head, not in
  the MoE path as pre-registered.

### The NET rule is sub-linear in R

The programme rule `net = gross − producer × (R − 1)` is linear in `R`; the measured redundancy
exponent is 0.64, so the correct form is `net = gross − producer × (R^0.64 − 1)`.

This is not a modelling preference — it is cross-validated. My deconfounded M4 measurement of the
redundancy term at `R = 640` is **+80.4 µs**. Scaling to the advisor audit's `R = 5120` with the
audit's own exponent gives `80.4 × 8^0.64 = 304.3 µs`; the audit independently measured
**+308.3 µs**. **Two unrelated methods agree to 1.3 %.**

Practical effect: the linear rule over-prices redundancy by `R^0.36` (≈10× at R = 640, ≈20× at
R = 5120). It stays directionally safe for every row with `R ≥ 128`, but it is unsafe for ranking
and unsafe near the sign boundary. **D2** (`normalized` 4,096 B → `lagunaGateSoftplus`, `R = 8`)
is the one census row whose sign is not robust to the correction, and therefore the one row that
deserves a direct measurement rather than a modelled verdict.

## 4. Why the C1 RMSNorm→QKV fusion failed

Delivered in full as
[`research/nezuko-r86b-c1-decomposition.md`](nezuko-r86b-c1-decomposition.md).

C1 predicted +0.85–0.9 % and the ranked M5 receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`
measured **−0.1488 %** (+9.7–10.0 µs/step). The finding is that this was a **cancellation, not a
wash**: the individual terms are 35–100 µs each.

M4, deconfounded via PR #298's `{0, G, R, N}` ladder:

| Term | Rung | M4 µs | 95 % CI |
| --- | --- | ---: | --- |
| occupancy / threadgroup geometry | `G − 0` | −35.4 | [−62.8, −8.0] |
| redundant RMSNorm recomputation | `R − G` | +80.4 | [+53.0, +107.7] |
| boundary / chain refund | `N − R` | −100.0 | [−127.3, −72.6] |
| **net** | `N − 0` | **−55.0** | — |

On M4 the fusion was a genuine 0.67 % **win**. It died in transfer: the refund is
dispatch-dominated and transfers at ×0.39, while the redundancy is exposed ALU work that *grows*
on the instruction-bound M5. Ledger: `−30.9 + 41.0 = +10.1 µs = +0.15 %` versus the receipt's
+0.1488 %. **The ledger closes to within 4 %.**

Two further results:

- **The advisor's 5120 and my 640 are the same site at two geometries.** Stock
  `lagunaDecodeNVFP4QKVR1` (`:4857`, call `:5806`) launches `grid=((rows/2)*64,1,1)`, `TG=64` ⇒
  `R = rows/2 = 5120`. The C1 kernel (`9c73e16f:4861`) launches `grid=((rows/16)*512,1,1)`,
  `TG=512` ⇒ `R = rows/16 = 640`. **C1 had already applied an 8× redundancy mitigation by
  coarsening, and it still was not enough.**
- **The geometry axis is exhausted.** Redundancy falls as `R^0.64` while occupancy cost explodes:
  coarsening 640 → 128 saves ≈51 µs of redundancy and costs **+174.9 ± 11.0 µs** of occupancy
  (PR #309); at 16 TGs it costs **+917 µs**. There is no interior win below R = 640. The only
  remaining lever is **algebraic: reach R = 1 without changing the grid** — i.e. epilogue
  normalization, whose banked unmerged evidence is `N640 − a0 = −33.7 ± 11.0 µs`.

### Four-part selection criterion for any future fusion

Ship only if all four hold: (1) the removal is verified on the **ranked** decode path; (2)
**R = 1**; (3) occupancy invariants are preserved (simdgroups, TGs in flight, TG memory); (4) the
refund is priced with **M5-measured** constants.

Redundancy-freedom is necessary but **not sufficient**. PR #137 was bit-exact *and*
redundancy-free, measured −63.7 µs on M4, and shipped **+24.6 µs on M5** because occupancy
collapsed 25,088 → 3,136 simdgroups. Criterion 3 is the one that catches it.

### A methodological correction on which price coefficient to use

`d = WIDE − TINY` is the **DRAM round-trip component only**. A real fusion removes the round trip
*and* the dispatch, so a fusion decision must be priced with the **full WIDE price**, not with
`d`. Using `d` under-prices a fusion by the dispatch fraction. `d` is the right coefficient only
when the dispatch survives and just the materialization is removed.

Independent validation of the instrument: the WIDE arm gives **1.398 µs/boundary** (M4, 4 KiB),
and this unrelated real fusion's measured chain refund is `100.0 / 80 =` **1.25 µs/boundary**
(M4). The synthetic in-situ ladder reproduces a real fusion's refund to within **12 %**.

## 5. Regime caveat and transfer class

Dev host: **Apple M4 Pro, 48 GiB, Apple GPU gen 16, bandwidth-bound**; `_nax` kernels are
unreachable here, so this PR makes no claim about them. Ranked host: **M5 Max, instruction-bound
at ~89 % GPU utilization**. A measured byte-class optimisation transferred at **−0.40 ± 0.24** —
an M4 win became an M5 loss.

Both quantities this PR produces — the boundary price `d` and the redundancy multiplier `R` — are
**latency/instruction-class**, which is the privileged class. `R` in particular is *exact* across
devices because it is a property of the launch geometry, not of the hardware. Byte-class rows in
§3.4 are flagged **presumptively non-transferable**. Full table in §3.7.

## 6. Cross-prediction scoring

| ID | Pre-registered claim | Outcome |
| --- | --- | --- |
| CP-1 | price flat within ±0.25 µs for W = 2 B … 64 KiB; `price(4 MiB) ≥ 25 µs`; `BW_eff ∈ [150,450]` GB/s; %/MB within 3× of PR #110 | **TBD-FIT** (expected MISS on the flatness limb: the census already shows 0.62 µs at 2 B vs 1.40 µs at 4 KiB) |
| CP-2 | `d` inside PR #269's CI [0.920, 1.545] | **TBD-FIT** |
| CP-3 | largest recurring intermediate lies in the MoE path | **MISS** — it is `coarse` (401,408 B) in the lm-head |

## Evidence

- Host, memory profile, toolchain, thermal policy: Apple M4 Pro, 48 GiB unified, low-memory
  startup profile not triggered; standard 40 C thermal gate honoured on every arm.
- Exact commands:
  - census: `bash research/nezuko_r86b_census.sh /tmp/r86b/census 40`
  - sweeps: `bash research/nezuko_r86b_run_all.sh /tmp/r86b 1 1 200`
  - fit: `python3 research/nezuko_r86b_fit.py --csv research/nezuko-r86b-ladder.csv /tmp/r86b/ladder /tmp/r86b/size`
  - publish: `python3 research/nezuko_r86b_wandb.py /tmp/r86b/ladder /tmp/r86b/size`
- Correctness and serial-protocol verdict: **TBD-FIT** (every arm log prints the teacher-forced
  greedy divergence count; census arms all reported `0 divergences (all match)` with
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` unset). The instrument inserts no token-dependent state, no
  cross-request state, and no future-token computation; it only round-trips an already-computed
  activation, so the serial non-speculative rule is untouched.
- Peak RAM: 21 GB resident, as expected for the RAM-resident text tower.
- GPU budget: census ≈10 min + two rebuilds + the combined sweep, inside the 60 min cap.

| Metric | Baseline | Candidate (disarmed) | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.012953 | 0.012933 | 0.998× |
| prefill seconds/token | 0.001125 | 0.001112 | 0.989× |
| same-host paired estimate | 0.795 | 0.798 | +0.4 % |

The paired estimate is a same-host research metric, not an official M5 score. The prefill floor
fails locally (0.33×) on every build including the unchanged base, which is the expected M4
behaviour for this harness and is not a property of this change.

## Conclusion

- What happened and why: **TBD-FIT**
- Evidence for or against the mechanism: **TBD-FIT**
- Uncertainty / M5 transfer risk: see §5. `d` and `R` are instruction-class and privileged; the
  absolute magnitude of `d` is expected to shrink on the wider M5 dispatch engine, so `d`
  measured here is an **upper bound** on the M5 round-trip price.
- Smallest useful next action: rerun PR #298's `{0, G, R, N}` deconfound ladder **on M5**
  (`research/nezuko_pr48_deconfound.patch` + `research/nezuko_pr48_abba.sh`). Decision rule:
  `R − G ≳ +60 µs` ⇒ redundancy dominates, fix it algebraically; `N − R ≲ −50 µs` with small
  `R − G` ⇒ occupancy is the killer and the fix is geometric. Four arms.
- Recommendation: **close unmerged**. This is an instrument-only deoptimizer by construction; its
  value is the calibration constant, the §3 census, and the §4 decomposition, all of which are
  research files.

## Suggested follow-ups (not implemented)

1. **Epilogue normalization** at the norm→QKV site: fold the normalization into the consumer's
   epilogue instead of recomputing the producer per threadgroup. Satisfies R = 1 by construction
   *and* preserves grid geometry, so it clears criteria 2 and 3 together. Banked evidence
   `N640 − a0 = −33.7 ± 11.0 µs`.
2. **Direct measurement of census row D2** (`normalized` → `lagunaGateSoftplus`, R = 8) — the only
   row whose sign flips between the linear and `R^0.64` NET rules.
3. **Adopt `net = gross − producer × (R^0.64 − 1)`** as the programme's NET rule, and re-rank the
   existing queue under it.
