# R107-J′ — Characterising and certifying the paired `--local-submit` decode instrument

**Student** maple-nezuko · **PR** #657 · **assignment** `maple-r107-j-qkv-lane-major-packing-replication`
· **revision** `r107-j-rev1` · **base** `fc66172b73a1ffa3bf2d9a4431267c0b922b7b7f`
· **branch** `maple-nezuko/r107-qkv-packing-replication`

Host **Apple M4 Pro**, 20 GPU cores, 48 GiB, MLX cache capped 6 GiB, 40 °C thermal gate.
Epoch **R107**. Unless a line says otherwise, every quantity below is
**host = M4-Pro · epoch = R107 · MARGINAL** (a local paired difference of two arms of
one binary). No number here is a census number and no number here came from a receipt.

---

## 0. What this round is, and what it is not

The original R107-J brief (build `_sg8`, flip QKV `num_simdgroups` 2→8, sweep) is **void**.
maple-fern already ran exactly that flip as a preregistered 10-block ABBA
(`research/maple-fern-r106j-integration-tree.md` §5.3.6, branch head `234c5542`):

| channel | estimate | CI95 |
| --- | --- | --- |
| `d(ln score)` | +0.0328 % | [−0.2338, +0.2994] |
| `d(ln decode)` | −0.0686 % | [−0.3921, +0.2550] |

42 usable runs, 10 blocks, 0 correctness failures, one `golden_hash b9509697c08a2cf3`.
L3 is settled and is not revisited here. **No `_sg8` kernel is built in this round.**

What is left is the instrument problem. fern's ABBA resolves the score channel to a
±0.27 % half-width. The candidates now in flight are individually far below that bar —
edward (#629) ≈ 0.43× and alphonse (#644) ≈ 0.45× of the 0.4 % bar *each* — so under
rule 105.5 the only way either becomes bankable is a **summed** 0.25–0.35 % effect
certified with a CI that excludes zero. Nothing in the campaign can do that today. My
`--local-submit` paired instrument is ~2.25× tighter than fern's `--local-iterate` ABBA on
the score channel, which puts it in the right range — but its noise floor has only ever
been **inferred** (24.8 µs/step, back-derived from a within-arm sd of 16.354 on 24 runs),
never **measured**, and it has never been shown to return zero when nothing changed.

So the deliverable is the instrument, in this order:

1. an **A/A null** — is the paired interval centred on zero, and what is the *measured* paired sd;
2. a **power curve** — blocks → resolvable effect, in µs/step, relative decode %, and % of `cs`;
3. a **turnkey script** fern can run without reading my code;
4. **guard rails** written inside that script, not just in a report nobody re-reads.

Then, and only then, Part 2 spends the instrument on somebody's real candidate.

---

## 1. Preregistration of the A/A null

*Written and committed before any timing was collected in this round. Commit of this
section is the timestamp; the campaign is launched afterwards.*

### 1.1 Design

- **Binary**: one release build of the pristine base tree at head `40ade278`
  (parent `fc66172b`). **No source edit at all.** `Sources/MLXFastModel/LagunaRuntimeModel.swift`
  is 384245 B with 0 hits for `PACKRED|_H4|NOREDUCE`, i.e. the advisor's `fc66172b` revert of my
  R106-B scaffolding is intact and this is the untouched base. An A/A null needs no code:
  it needs two labels on the same thing.
- **Arms**: `A` and `Ap` (A′). **Identical gate sets: both empty.** Same binary, same
  process invocation, same 1023-step `--local-submit` workload. The only difference between
  the arms is the label the harness writes into the row sink, and the position in the block.
- **Blocks**: 12 blocks × 2 arms = **24 runs**. Requirement was ≥10 blocks; 12 gives dof = 11
  and two blocks of slack for a failed run without dropping under the floor.
- **Interleaving and position balance**: within-block order rotates by `(block−1) mod 2`, so
  blocks run `A A′ / A′ A / A A′ / A′ A …` — every arm occupies each of the two positions
  exactly 6 times. This is the same layout a real experiment gets, which is the point: the
  null must be measured through the *same* machinery, not a friendlier one.
- **Mode**: `./benchmark.sh --local-submit` only, 1023 decode steps. `--local-iterate` is
  never invoked (guard rail 1 below).
- **Cost**: 198 s/run measured in R106-B (24 runs = 4750 s) ⇒ ≈ 79 min.

### 1.2 Estimand

Per block *b*, the paired difference in the submit-level decode figure

    D_b = 1e6 × ( decode_seconds_per_token[A′,b] − decode_seconds_per_token[A,b] )   µs/token

and the reported statistic is the ordinary paired-t interval on `D`:
`mean(D) ± t(0.975, n−1) · sd(D)/√n`, n = 12, dof = 11, t = 2.201.
Per rule 105.7 **the interval is the deliverable**; the point estimate is not.

### 1.3 Predictions, registered in advance

- **P1 (the null).** `mean(D)` CI95 **covers zero**. This is the pass condition.
- **P2 (the noise floor).** The measured `sd(D)` lands near the inferred 24.8 µs/token.
  I register a tolerance band of **15–35 µs/token**. Landing *below* 15 would mean my
  R106-B power claims were pessimistic; landing *above* 35 would mean they were optimistic
  and every R106-B interval I published is too narrow.
- **P3 (prefill neutrality, rule 105.4).** The paired difference in
  `prefill_seconds_per_token` covers zero. The submit level carries a constant
  +563.6 µs/token of amortised prefill (`K/N`, K ≈ 0.5766 s, N = 1023); in an A/A it must
  cancel exactly, and if it does not, the decode channel is contaminated and the
  instrument does not measure decode.
- **P4 (no ordering confound).** OLS of `D` on the within-block position offset has a slope
  whose CI95 covers zero. The thermal gate fires on essentially every run, so a real
  position effect would alias drift onto every future contrast.
- **P5 (identity of the arms).** Both arms report the same kernel set and the same
  `golden_hash`, and `passed_correctness` is `true` for all 24 runs.

### 1.4 Falsification, stated in advance

**If P1 fails — if the A/A interval excludes zero — the instrument is broken and that is
this round's most important finding**, outranking any candidate certification. I will
report it as such, will not certify anything with it, and Part 2 becomes a repair job
rather than a measurement job. I am registering this before I look, so that a
zero-excluding A/A cannot later be re-described as "drift we can correct for".

A failure of P3 or P4 is a narrower fault: it does not void the instrument but it does void
the *unadjusted* interval, and the position-adjusted intercept becomes the reported estimand.

### 1.5 Stopping rule

Fixed at 12 blocks, declared before launch. There is no look-and-extend: the row sink is
appended as the campaign runs, but the interval is computed once, at n = 12. If a run
fails hard (no `score.json`, or a kernel set that changes mid-session) the script aborts
and I report the interval on the **complete** blocks only, with the incomplete block
dropped whole — never half a block, because half a block is not a pair. The floor is 10
complete blocks; below that I report the failure, not an interval.

---

## 2. Channel translation, fixed in advance

Three channels, because a µs/step number that nobody can convert is not evidence.

| channel | definition |
| --- | --- |
| (a) **M4 µs/token** | the raw measured paired difference on this host |
| (b) **relative decode %** | (a) ÷ reference arm level × 100 |
| (c) **% of `cs`** | (a) × k × 0.015228 |

`k` is the M4→M5 transfer factor and it is carried at **both** priced values per rule 105.12:
**α = 0.4369** (bytes-priced) and **β = 0.5000** (latency-priced). Anchor supplied by the
advisor: **0.4 % of `cs` = 26.27 M5 µs/step = 60.1 M4 µs/step at α = 52.5 M4 µs/step at β.**
Check: 60.1 × 0.4369 × 0.015228 = 0.3999 ✓.

`k` is **not** a ratio of two measured levels — see guard rail 2. It comes from a
fixed-term fit across matched workloads (rule 105.13, credited to my R106-B §C.3:
`k_steady = 8448/4141.5 = 0.4902`, `k_dispatch = 2.3403/1.2382 = 1.890 > 1`).

---

## 3. Guard rails (also written inside the script)

1. **`--local-submit` only; never mixed with `--local-iterate`.** iterate runs 128 decode
   steps, submit runs 1023, and the harness reports
   `decode_seconds_per_token = mean_step_seconds + K/N` with fixed `K ≈ 0.5766 s`. The same
   binary therefore reads 8984.5 µs/token at N = 1023 and ≈ 12926 µs/token at N = 128 — a
   **1.44× scale gap that is pure prefill amortisation, not speed.** Independent
   cross-check from a second operator: fern's `--local-iterate` decode mean
   0.012955773 s/token ÷ my `--local-submit` 0.008984501 s/step = **1.442**. iterate is also
   ≈ 3.7× noisier per run, which is the whole reason this instrument exists. The script
   hardcodes `--local-submit`, rejects any arm spec mentioning iterate, and aborts if
   `score.local-iterate.json` ever appears (submit writes `score.json`;
   iterate writes `score.local-iterate.json`, `benchmark.sh:138-141`).
2. **Never divide a local level by a receipt level and call the ratio `k`.** The official
   receipt amortises the seed prefill over 128 tokens, so `4925.255 / 8984.50 = 0.5482`
   is a prefill-amortisation artefact of two different N — **it is not `k`**. The script
   computes no `k` at all; the analyser takes it as an explicit constant and prints it
   beside every %-of-`cs` figure it derives.
3. **Prefill is charged neutral (rule 105.4).** The +563.6 µs/token amortised prefill
   cancels in a paired difference between arms that do not touch prefill. The script
   records `prefill_seconds_per_token` for every run and the analyser reports its paired
   CI as a contamination diagnostic.
4. **Blocked, interleaved, position-rotated — never two back-to-back batches.** The
   analyser additionally regresses the paired difference on within-block position.

Standing prohibitions honoured: **no receipts**, **`senpai/submit-official.sh` is never
invoked** (the script fails closed on the name), **`DARKBLOOM_EXPERT_DOWN_BN` is never set**
(the script rejects that gate name).

---

## 4. Deliverable files

| file | role |
| --- | --- |
| `research/maple-nezuko-r107j-certify.sh` | turnkey campaign runner: `--blocks N LABEL:GATES …` |
| `research/maple-nezuko-r107j-paired-ci.py` | paired CI + power curve + position/prefill diagnostics |
| `research/maple-nezuko-r107j-certification-instrument.md` | this report |

Invocation, for maple-fern, no knowledge of my code required:

    # A/A null (what §1 registers): 12 blocks, 24 runs, ~79 min
    research/maple-nezuko-r107j-certify.sh --blocks 12 A: Ap:

    # certify one candidate against the shipped default: 8 blocks, 16 runs
    research/maple-nezuko-r107j-certify.sh --blocks 8 C: E:DARKBLOOM_SOME_GATE=1

    # certify two candidates and their SUM on the combined tree: 6 blocks, 24 runs
    research/maple-nezuko-r107j-certify.sh --blocks 6 \
        C: E:DARKBLOOM_E=1 A:DARKBLOOM_A=1 S:DARKBLOOM_E=1,DARKBLOOM_A=1

The first arm listed is the reference; every later arm is differenced against it block by
block. `LABEL:` with an empty gate list means "set no gates at all". Rows land in
`$OUT` (default `/tmp/r107j-certify-<session>.tsv`), deliberately **outside** the worktree so
a campaign never dirties the assignment checkout.

---

## 5. Results

*(populated after the campaign; §1 was committed before launch)*
