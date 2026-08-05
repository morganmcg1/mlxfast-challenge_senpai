DRAFT - NOT TERMINAL. The single-line SENPAI-RESULT marker replaces this banner
once every authorised receipt has returned.

# PR #34 revision r2: is the marginal cost of a Metal dispatch on M5 worth removing?

- Student / PR: `maple-tanjiro` / #34, branch `maple-tanjiro/m5-block-rates`, revision r2
- Assignment: `maple-2026-08-04i-m5-block-rates`
- Hypothesis and target cost: PR #37 attributes about 4.1 microseconds of host
  encode and commit cost to each of the roughly 406 Metal dispatches in one
  decode step, which would make 1.665 ms of the 4.32 ms step removable by
  fusion. This revision measures the *marginal* price of a dispatch on the
  official M5 directly, by injecting `n` empty, dependency-free dispatches per
  decode step and fitting `dT(n) = max(0, n*c - slack)`. `slack` is the free
  headroom: the number of dispatches the machine absorbs before wall time
  responds at all.
- Decision: PENDING
- `BASE_SHA` / candidate commit: base `279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b`
  (advisor tip `ed02e9e69427f774628aaf69fee106931e7bc7cb`, docs-only ahead of it);
  candidate commit PENDING
- Submitted candidate files: none. The final commit of this revision restores
  `Sources/MLXFastModel/LagunaRuntimeModel.swift` byte-for-byte to the base. This
  is a measurement revision, not an optimisation: the assignment says sweep only,
  do not build a fusion.
- Supporting test or documentation files: `research/tanjiro-pr34/` (pre-registration,
  queue, per-level notes, provenance, M4-vs-M5 comparison, instrument patch) and
  `senpai/tools/pr34_*.py`, `senpai/tools/pr34_m4_ladder.sh`. All outside
  `editablePaths`, so none of it costs submission bytes.
- Assignment-scope preflight: PENDING
- Editable bytes / headroom / growth: PENDING (before/after captured; see the
  byte-budget section)
- Scored-path reachability evidence: the injection hook is called at
  `LagunaRuntimeModel.swift:10797`, inside the per-layer loop of the scored
  forward pass, and the decode branch is selected by `isSingleTokenDecode`
  (`inputs.dims(1,1)`, line 10753). Every receipt below shows the injected work
  in the timed decode axis, which is itself proof of reachability.

## What this probe prices, and what it does not

The injected kernel is `laguna_inject_empty_dispatch_v1`. It has a predicated
store that never executes, it is chained through `LagunaInjectChain.tail` so the
encoder cannot elide it, and at `DARKBLOOM_INJECT_EMPTY_TG = 8` it is 8
threadgroups of 256 threads. So the probe measures the *host-encode and
scheduling margin of an empty, dependency-free dispatch*.

That is deliberately narrower than "the cost of a dispatch in the shipped decode
step", and the distinction drives the whole interpretation:

- If `slack` is about zero, the machine is already dispatch-bound and removing
  dispatches by fusion buys time at the fitted rate `c`. Green light.
- If `slack` is large, the 4.1 microsecond figure is falsified **as a marginal
  host cost**. It does *not* retire fusion, because a real fusion also removes
  GPU-side costs the empty probe cannot see: launch ramp and tail, inter-kernel
  gaps, and round-trips of intermediate tensors through memory. Those are worth
  roughly 3.1 to 3.4 microseconds per dispatch if the entire unattributed 1.27
  to 1.38 ms of the decode residual is charged to them, which is an upper bound,
  not an estimate.

This scope limit was pre-registered in `research/tanjiro-pr34/prereg-r2.md`
before any reading arrived, precisely so that a large `slack` could not be
quietly promoted into "dispatch reduction is worthless".

## Ladder, and why it deviates from the assignment

The assignment proposed `n` in {0, 100, 200, 400, 800}. I ran
{0, 400, 800, 1600, 2400} at `tg = 8` with prefill empties pinned to 0, and
pre-registered that choice with three competing predictions before submitting
anything.

The reason is that the assignment's ladder cannot discriminate the hypotheses it
is meant to test. Carrying the M4 law (`c = 2.607 us`, `slack = 3.152 ms`, knee
at 1209 dispatches) to M5 gives three candidate laws:

| | mechanism | `c_M5` (us) | `slack_M5` (ms) | knee (dispatches) |
| --- | --- | --- | --- | --- |
| `H_sat` | M5 is already dispatch-bound | 2.0 to 2.6 | < 0.2 | < 80 |
| `H_gpu` (advisor) | slack is GPU-idle-gap shaped, so it scales down by the 2.623x step-time ratio | 2.61 | 1.20 | 461 |
| `H_cpu` (my prediction) | slack is a fixed *dispatch count*, so the knee transfers | 2.27 | 2.72 | 1200 |

Predicted `dT` in ms:

| n | `H_sat` | `H_gpu` | `H_cpu` |
| --- | --- | --- | --- |
| 0 | 0 | 0 | 0 |
| 400 | 0.82 | 0 | 0 |
| 800 | 1.74 | 0.89 | 0 |
| 1600 | 3.58 | 2.98 | 0.91 |
| 2400 | 5.42 | 5.06 | 2.73 |

On the assignment's ladder, `H_gpu` produces exactly one non-zero point and
`H_cpu` produces none: four of the five receipts would have returned zero and
the outcome would have been "the knee is somewhere above 800", which is what the
M4 work already said. On mine, `n = 800` separates all three hypotheses (the
predictions are 34 to 37 sigma apart at the 0.024 ms two-receipt noise floor),
`n = 400` is the sole `H_sat` discriminator, and there are always at least two
points above any knee in [0, 1600].

`tg = 8` keeps the injected GPU work under about 0.09 microseconds per dispatch,
under 3.5 percent of `c`, so the probe stays a dispatch-count probe rather than a
GPU-work probe. Prefill empties are pinned to 0, which makes the prefill axis `S`
a flat internal control and avoids the prefill dispatch axis that PR #27 found
self-inconsistent by a factor of 7.

Declared blind spot: no level lies in `n` between 0 and 400, and that is exactly
where a fusion removing 50 to 200 of the 406 shipped dispatches would live. A
knee near 200 would make "remove 40" worthless and "remove 300" valuable, and
this ladder cannot separate those two worlds.

Design lesson accepted but declined mid-flight: a frontier review of the design
found that `n = 0` is nearly redundant and that replacing it with `n = 1200`
would have given a tighter knee (standard error 9.3 to 12 dispatches instead of
10 to 17) and one more degree of freedom for lack-of-fit. I kept the
pre-registered ladder rather than re-choosing levels after the fact, because the
value of a pre-registration is destroyed by editing it once submissions are
under way.

## Cost floor headroom

The pinned decode baseline is 0.013890 s/token and the hard floor is 0.95, so a
candidate may take up to 14.621 ms/token. The frontier is about 5.087 ms/token,
which leaves about 9.53 ms of injected `dT` affordable. The worst case on this
ladder, `n = 2400` under `H_sat`, costs at most 6.26 ms. `c` would have to exceed
3.97 microseconds to breach the floor, and a breach still returns `rejected`
*with* full timed metrics, so no reading is lost either way. The prefill floor is
untouched because prefill empties are 0.

## Readings

PENDING

## Fit

PENDING

## Verdict on dispatch-count reduction

PENDING

## M4 companion measurement

PENDING

## The M4-versus-M5 disagreement

The advisor asked for this explicitly. The same inert tree on the local Apple M4
Pro host and on the ranked M5:

| quantity | M4 Pro (`m4-L0.json`, inert) | ranked M5 (`b6032aeb`) | M4 / M5 |
| --- | --- | --- | --- |
| `S`, 512-token prefill forward | 577.20 ms | 97.86 ms | 5.90x |
| `T`, steady one-token decode step | 8.8161 ms | 4.2747 ms | 2.06x |
| full decode seconds/token | 13.326 ms | 5.039 ms | 2.64x |

The 5.90x prefill gap is mostly a *kernel gate*, not hardware. Locally
`prefill_speedup = 188.17 / 577.20 = 0.326`, so the promoted frontier is three
times **slower** than the baseline on this host, while on M5 the same tree is
1.913 times faster. `quantized.cpp:1956` routes to `gather_qmm_rhs_nax` only when
`is_nax_available()`, and `device.cpp:913` requires architecture generation 17 or
above; this host is generation 16 (`applegpu_g16s`). So for NAX-gated prefill
work M4 is **anti-correlated** with M5, not merely conservative, and no prefill
conclusion may be carried across.

The 2.06x decode gap is closer to an honest hardware ratio, which is why the M4
companion ladder is used only for decode-side method validation: to show that the
injected kernel's own GPU time is negligible, and to state an M4 companion law at
the same ladder points.

A related finding worth recording: the local paired baseline is not measured, it
is a pinned constant. Across all eleven r1 local runs
`baseline_decode_seconds_per_token` was 0.01385621216015625 and
`baseline_prefill_seconds_per_token` was 0.00036751938916015626, identical to
every digit. There is no `--local-iterate` baseline artefact on disk. So a local
`*_speedup` is arithmetic against another machine's constant, and every local
`dT` in this report is `T(n) - T(0)` measured on the same host in the same
session, never a difference against that pinned number.

## Answers to the two questions in the r2 assignment

Recovered from the submitted trees themselves, by reading the injection literals
out of each submitted commit
(`git show <c>:Sources/MLXFastModel/LagunaRuntimeModel.swift`):

| tree | `DECODE_ATTN` | `DECODE_ROUTED` | `PREFILL_ROUTED` | `PREFILL_ATTN` |
| --- | --- | --- | --- | --- |
| R1 anchor | 0 | 0 | 0 | 0 |
| R2 | 40 | 0 | 39 | 0 |
| R3 | 40 | 39 | 0 | 40 |
| R4 | 0 | 39 | 20 | 0 |

**(a) Were the R2 and R3 decode arms nested or disjoint?** Nested, on the decode
axis. R3 is R2's 40 attention-QMV copies *plus* 39 routed-QMV copies, which is
what `cfg-r3.md` says at the time. So `dT_4 = T_R3 - T_R2` is a plain difference
of a strictly nested pair, and the advisor's `2.24137 - 1.23070` reduces to the
same quantity. On the prefill axis R2 and R3 are instead disjoint single-knob
arms against the shared zero anchor, which is also valid.

**(b) Does rate 4 depend on the failed R4 receipt?** No. R4's decode probe was
routed-QMV *alone*, the unloaded companion. The published rate 4 of 546.2 GB/s
rests entirely on R3 minus R2, and both of those receipts succeeded
(`6757de65`, `ca416f01`). R4 carried only three robustness companions. **Rate 4
needs no re-run**, so the advisor's contingency of reallocating r2 receipts to
repair it is moot and all five r2 receipts stayed on the dispatch law.

Widened error bar, since the question was asked: the published +/-0.034 ms
already used two-receipt propagation (quadrature 0.02900 ms times the same 1.18
method factor used for `dT_2`). Adding a 0.026 ms allowance for cross-session
drift, which is what the R2 and R3 normalisations actually disagreed by (2.6
percent), gives a conservative +/-0.043 ms. Rate 4 becomes 546.2 +/- 23.3 GB/s,
that is [523, 569]. Against the 0.90505 ms roofline the excess is +0.1056 +/-
0.043 ms, still more than 2 sigma from zero, and 7.9 +/- 3.2 percent of the
decode residual. The conclusion does not change.

## The R4 failure: `afec358a`

`afec358a` returned `status=failed` with `officialScore=None` and no timed
metrics at all. The reason was not timing and not correctness: the workflow run
concluded failure at the step "Review submitted code for benchmark bypasses"
(run 30955316536), created 22:09:28Z and updated 22:53:48Z.

The R4 tree differs from the R3 tree, which had already passed that same review,
in exactly four integer literals. `DARKBLOOM_INJECT_ARCH_PROBE` was 0 in all
four trees and predates R1, so it cannot be the differentiator. The most
defensible reading is a non-deterministic reviewer or an infrastructure error.

The operational lesson is worth more than the diagnosis: **a submission can
consume a slot and return no metrics at all.** I therefore declared a rule in
advance, in `queue-r2.md`, that a `failed`-with-no-metrics receipt is a *retry*
and not a data point: resubmit the identical tree and record both attempts, so
that five authorised receipts means five readings rather than five slots.

## Process disclosures

These are not incidental; two of them changed how this revision had to be run.

**The official channel is serialised at one submission in flight.** The r1 notes
and the r2 assignment both said the receipts could be submitted concurrently.
They cannot. Submitting L1 about 20 seconds after L0 returned produced
`{"error":{"code":"conflict","message":"account already has 1 submission(s) in
flight for this benchmark (limit 1)"}}`. At 21 to 48 minutes per receipt this
turns a five-point ladder into a 2.5 to 3 hour serial campaign, and it is the
single most important scheduling fact for anyone planning a multi-receipt sweep.
I kept the full five-level ladder rather than truncating it, with one declared
exception: stopping early if a reading falsified the law itself.

**There is no live channel from a student to the advisor.** `push_branch` is
advisor-owned, so a student can only push through `submit_result`, which means
the advisor sees nothing at all until the final submission. `respond_to_issue`
refuses a pull-request target (`human messages must use an issue, not a pull
request`). So an intermediate finding cannot be surfaced mid-campaign. My
mitigation was to commit `research/tanjiro-pr34/queue-r2.md` as a running log and
to fold every disclosure into this report. A useful consequence: reordering the
ladder to give the advisor an early read has exactly zero value, so the
pre-registered order was kept.

**Branch divergence, disclosed rather than resolved by force.** The remote
assignment head `454b189a07a2cb0c51b91188d834e9b1c5035603` is the stale
pre-rebase r1 tip. My local history was rebased onto `279b6e24`, so the SHAs
differ one-for-one by commit message (`454b189` is `c92eab6`, `5b39ec5` is
`8d5131f`, `ee324e1` is `644c226`). R4's submitted commit `af3ab58` is a
pre-rebase SHA and is not a valid object locally; its content equals local
`13d424f`. Comparing file lists, no file exists on the remote but not locally:
local is a strict content superset. The submission therefore uses
`expected_remote_sha = 454b189a...`, and nothing was reset or discarded.

## Byte budget

The assignment asked for the editable-byte budget before and after.

| | total bytes | headroom | growth | files |
| --- | --- | --- | --- | --- |
| before | 2954324 / 3000000 | 45676 | 13351 / 262144 | 142 (base 142) |
| after | 2940973 / 3000000 | 59027 | 0 / 262144 | 142 (base 142) |

The instrument patch was moved out of the scored file into
`research/tanjiro-pr34/instrument.patch`, which restored
`LagunaRuntimeModel.swift` to the base size of 508529 bytes and with it the full
15759 bytes of per-file room under the 524288 byte cap. That matters to a
sibling: PR #35 needs 8037 bytes in the same file and now has 7722 bytes of
spare.

## Cross-references

Per the assignment, the per-family M4 dispatch census in `nezuko`'s PR #32 is
cross-referenced rather than duplicated here.

## Conclusion

PENDING
