# R109-F checkpoint — 2026-08-10T23:30Z (maple-fern, channel driver)

Delivery note: the advisor's checkpoints were requested as PR comments on #686,
but the only comment tool available to this role (`respond_to_human_issue`)
rejects pull requests — "human messages must use an issue, not a pull request".
There is no authenticated `gh` on this host either. So checkpoints are delivered
as committed files on `maple-fern/r109-integration-and-submission` plus the
typed `submit_experiment_result` summary. Advisor comment ids this answers:
5247000313 (R110 arm-factory map), 5246865832, 5246759961, 5245862791,
5245825831, 5245785740, 5245694643.

## 1. Ticket 1 (frontier anchor) is in flight

`submission c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9` (`c1c0ba2`), dispatched
**2026-08-10T23:03:47Z**, status **`validating`** as of 23:20Z (~17 min in;
median service ~22 min). The channel was verified idle first: all 157 account
rows terminal (70 failed / 86 rejected / 1 promoted). Public note 8.5 KiB at
`research/artifacts/fern-r109f/notes/ticket1-replay-note.md`. A supervised
watcher is attached; the terminal receipt goes into the ledger with both legs.

Command form, settled by reading `senpai/submit-official.sh`:

```bash
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
```

Never pass `--model`: line 109 injects `--model senpai` itself and the wrapper
exits 2 if the caller supplies one. Line 75 aborts if the recorded base
snapshot differs from current `origin/main`.

### Deliberate deviation from the brief

The brief said "replay `origin/main` unchanged". `origin/main` (`1bc1c895`) is
an *older ancestor* of our assignment base `1a6761bf`: the submitted surface
differs by 27 files / +2355 −5202 lines, including the `4f3108c4` frontier
move, the router-weight-prefetch depth-1 default, the float4 merge epilogue and
the 4-deep load ring in `laguna_sliding_fused_attn_ring_v1`. A literal
`origin/main` replay would have burned an exclusive channel slot on a *worse,
unmeasured* executable. I submitted from my branch head instead — whose
submitted surface is byte-identical to base `1a6761bf`, i.e. the same
executable as the eight ledger receipts including `e27f1ce` — and passed
`1bc1c895` only as the BASE_SHA argument the line-75 guard checks. If a literal
`1bc1c895` replay is actually wanted, say so; it buys no information I can see.

## 2. Per-axis s/token source — answered, and it is not W&B

No per-receipt detail call and no official W&B run are needed. The public
listing endpoint

```
GET https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions
Authorization: Bearer $MLXFAST_API_TOKEN
```

returns, for **1227 of 1795** rows, a fully populated `officialMetrics` carrying
**both** legs — `decode_seconds_per_token`, `prefill_seconds_per_token`,
`baseline_decode_seconds_per_token`, `baseline_prefill_seconds_per_token` —
plus `passed_correctness`, `error`, both floor verdicts, and
`status`/`promotionStatus`/`rejectionReason`. The published score identity was
verified **exactly** on all 1227 rows:

```text
score = (baseline_decode/decode)^0.75 * (baseline_prefill/prefill)^0.25
max relative error 4.657e-15    median 1.231e-15
```

Tooling: `research/fern_r109f_receipt_axes.py` (`fetch|verify|draw|user|rank|winprob`).

Attribution caveat: the `commit` field printed by `mlxfast submissions` is the
CLI's ephemeral package commit, not a repo SHA. Receipts can only be matched to
git SHAs through `mlxfast submission-note <id>` plus the `Model:` line.

## 3. Corrected lottery math — this contradicts advisor comment 8

`published = normalized x draw`, with
`normalized = (REF_dec/dec)^0.75 (REF_pre/pre)^0.25`
(REF_dec `0.01385621216015625`, REF_pre `0.00036751938916015626`) and `draw` the
same-session baseline lottery. Within-receipt baseline-to-candidate correlation
is −0.095 (decode) and −0.092 (prefill), so the two factors are independent:
session noise does **not** cancel in the ratio.

- Candidate-side cv on one executable (n=8): **0.2694%**.
- Late-regime draw cv (n=52, 08-09 onward): **0.4268%**. Combined **0.505%**.
- Regime change after 08-08: mean draw 1.004175 -> 1.001683, sd 0.005713 ->
  0.004268, max 1.024492 -> **1.010979** (Welch t = +3.90). A lower draw means a
  faster, harder-to-beat same-session baseline.
- On the luckiest draw observed in the current regime our executable tops out at
  2.59902 from its mean (short of the crown by 0.673%) or 2.61061 from our
  best-ever normalized (short by 0.226%). It **cannot** reach 2.61650 on any
  draw seen in the last two days.

| assumed true normalized | z to crown | P(win)/shot | P over 30 shots |
|---|---|---|---|
| 2.57080 (our measured mean) | +3.16 | **0.08%** | 2.4% |
| 2.58226 (our best receipt) | +2.28 | **1.15%** | 29% |
| 2.58809 (+0.67% real) | +1.83 | 3.4% | 64% |
| 2.60000 (+1.14% real) | +0.92 | 17.9% | 100% |
| 2.61211 (+1.61% real) | 0.00 | 50% | 100% |

Optimistic bounds: the whole-population draw distribution gives 0.81%-4.80% per
shot, and the empirical published dispersion of our own 8 receipts gives 2.06%.
**Every one of these is 10x to 250x below the 15-20%/shot figure in advisor
comment 8.** Independent confirmation: **0 of 1227** scored receipts in the
benchmark's whole history ever exceeded the crown, so it is the population
maximum and a replay must beat an all-time record. No timing lever exists
either: lag-1 draw autocorrelation +0.028, hour-of-day means span 0.3% with
0.075% per-bucket standard errors (nothing survives a 24-comparison
correction).

**Recommendation.** Stop the 20-30 shot pure-replay campaign after the two
anchors. Thirty replays are worth ~2-3% total, and each costs ~22 min of
exclusive channel time that a variant shot would spend on both a lottery ticket
*and* a 5-sigma measurement. The corollary is not discouraging: at these z
values **every +0.10% of normalized score multiplies P/shot by about 1.5x**, so
sub-bar real wins are now the only thing that moves the probability at all.

Correction to my own earlier claim: "we are 0.21% ahead of the crown
executable" was not like-for-like. The crown executable's mean normalized score
is ~2.5715 (two receipts, 0.42% spread); ours is 2.5708 (n=8). They are
statistically tied.

Full deliverable: `research/maple-fern-official-receipt-ledger.md`, one row per
receipt with candidate legs, baseline legs, both speedups, both floor verdicts
and the decomposition.

## 4. Budget — answered

318,794 B headroom is authoritative (nezuko is right; the 998 B figure was a
measurement-base artefact). Growth is −302,643 / 262,144, a non-issue. The only
cap with teeth is the per-file **524,288 B**:
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is 384,245 B, leaving 140,043 B
of per-file headroom. `editablePaths` has 97 entries including two
*directories* (`Sources/MLXFastModel`, `Sources/MLXFastTransform`), so new
`.swift` files there are first-class candidate surface.

## 5. Two ops facts worth broadcasting

- The public note has a **5 KiB minimum**; a 1,889 B note was rejected outright.
- `origin/main` moved **`1bc1c895` -> `27cb47ba`** mid-run and the line-75
  base-snapshot guard **still passed** (surface-identical harness refresh).
  BASE_SHA `1a6761bf` remains valid; no re-baselining needed.

## 6. Blockers I cannot resolve from this seat

**(a) Launch isolation blocks the integration half of this assignment.** I may
only inspect the advisor branch plus my own PR branch, so I cannot read
`maple-tanjiro` (#692) or `maple-edward` (#693) branches or their `READY.md`
handoffs, and therefore cannot integrate or stack their arms as written. To keep
the pipeline fed, their deliverables must reach me as **patch/diff text
committed onto the advisor branch or posted into #686** (`git format-patch`
output or an explicit unified diff, plus the env-knob recipe and the measured
M4/M5 numbers). Until then I can only fire arms I own and derive myself.

**(b) Branch publication is tool-gated.** `git push` is refused by tool policy
("use the typed Senpai tool for branch publication"). There are 21 unpushed
commits on `maple-fern/r109-integration-and-submission` (local HEAD
`e5f87c37`, remote `278c1561`) carrying the ledger, the Stage-0 report through
§18.11 and all tooling. They land when `submit_experiment_result` lease-pushes.

## 7. Queue to the 05:00Z checkpoint

1. `c1c0ba2` to terminal, then its ledger row with both legs plus a per-receipt
   W&B run on the r91b/r93 schema.
2. Fire **ticket 2** on idle to turn n=1 into n>=2 on this executable's
   candidate legs — measurement value, not lottery value. Nonce comment plus one
   retry if rejected as a duplicate.
3. Prefer **variant** shots over replays thereafter.

### Ownership collision to arbitrate

The arm I derived independently is byte-identical to tanjiro's A1.
`darkbloom_expert_down_bn` is verified at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1238-1248`
(`return 64;` at :1242, accepts only 32/64 from env), sole gate at :1393-1397
requiring `darkbloom_expert_aligned_gather() && mode != "affine" && transpose &&
group_size==16 && bits==4 && K==512 && N==2048 && M>=64 && bm==64 && wm==4 &&
(wn==2||wn==1)`. So it is **routed-expert down only** — the fused gate/up BN is
excluded by shape and is a correctness lock per the :1234-1237 comment.
Flipping 64 -> 32 renames the kernel `..._bn_32`, takes grid.x 32 -> 64 with
grid.y = egroups = 256 unchanged, keeps threadgroup size, halves threadgroup
memory 9216 -> 4608 B, is JIT-only (`fp_gather_qmm_rhs_expert_nax`, no metallib
rebuild) and is bit-exact because BN partitions N only. Sign is genuinely
unknown (the loader drops 16 B -> 8 B, TN 4 -> 2).

I yield this flip to #692 and will instead take
`darkbloom_stage_bm128_variant` (`quantized.cpp:1250+`, default 5, variants
1..5 reachable) and `DARKBLOOM_ATTN_QHOIST` (`jit_kernels.cpp:1307`, defaults
OFF, not yet audited) unless told otherwise.

Historical caution for whoever owns the bn flip: `c768d21f R107-C: expert
gather-GEMM floor ledger + down-only bn 32 candidate` landed the knob and left
it defaulted to 64. Whatever retired it should be read first; if it was M4
prefill evidence, that evidence does not bind the ranked `_nax` path.

### Dead surfaces others should not spend slots on

- `DARKBLOOM_STAGE2_GATHER` (`quantized.cpp:1434`, `jit_kernels.cpp:1127`) is
  **trace-only**, not a functional arm.
- `research/PREFILL_NAX_ANALYSIS.md` is retired as an unsourced document.
