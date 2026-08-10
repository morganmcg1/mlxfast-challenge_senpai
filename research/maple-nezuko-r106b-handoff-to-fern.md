# R106-B Stage C handoff — `maple-nezuko` → `maple-fern` (#625 integration tree)

**Status: FINAL.** The paired A/B in
`research/maple-nezuko-r106b-revert-residual.md` §C is the only admissible
source for the numbers below; this file is the handoff itself, not a summary of
a pending one.

```
VERDICT: DO NOT SEND — recommended adoption is ZERO source bytes.
```

Read that literally. I am not handing you a candidate to integrate. I am handing
you a **closed search direction** plus the harness facts that cost me a day to
learn, so that you do not spend #625 integration budget re-opening it.

## Why this file exists rather than a comment on #625

My role has no GitHub write credential (`gh` is unauthenticated in this
workspace, no `GH_TOKEN`/PAT is provisioned, and `respond_to_human_issue` refuses
#616 because #616 is a pull request rather than an issue). So I cannot post a
comment on #625 and cannot quote a comment id. The three channels that *do*
carry this result are listed in §G.2 of the report: this in-tree file, the
published W&B run
[`7wzz7sno`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7wzz7sno),
and the typed `submit_experiment_result` payload on PR #616. Everything a
comment would have carried is here, in the order your queue rule wants it
(measured % of `cs` first, reproduction command second).

## What was tested

Stage 0 of this assignment closed the r106 revert residual as **N-RESIDUAL**
(D = +19.405 µs/step, dof 10, CI [−18.156, +56.966]; W&B `d942xnno`): the
reverted residual is not measurable at this harness's resolution. Stage B then
asked whether the *named mechanism* behind that residual — cross-lane reduction
traffic in the sliding decode-attention kernel — is worth any bytes at all. I
built three kernels behind three default-off gates and ran one preregistered
6-block × 4-arm paired design (24 whole-model `--local-submit` runs, dof 5,
t = 2.571; positive Δ = slower):

| arm | gate | mean µs/step | Δ vs control | 95 % CI | % of `cs` | label |
|---|---|---|---|---|---|---|
| C | (none) | 8984.501 (sd 16.354) | — | — | — | control |
| K | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1` | 9006.646 | **+22.145** | [−7.669, +51.958] | +0.3372 | **N-RECOVER** (null) |
| H | `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1` | 9020.460 | **+35.959** | [+9.831, +62.087] | +0.5476 | significant **regression** |
| P | `DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1` | 9000.777 | **+16.276** | [−0.395, +32.947] | +0.2479 | bound only; wrong by construction |

Supporting facts for arm K, in the shape your queue rule asks for:

| field | value |
|---|---|
| paired Δ decode (µs/step) | **+22.145** (slower; sd of Δ 28.405) |
| 95 % CI | [−7.669, +51.958] |
| % of `cs` at 0.015228 %/µs/step | **+0.3372 %** (point estimate is a *slowdown*) |
| n pairs / dof | 6 / 5 |
| bit-exact? | **yes** — error exactly 0 on all 8 decode steps, see caveat 4 |
| shuffle instructions per lane per call | 229 → 109 (a real 52 % cut, bought nothing) |
| sha256 + bytes of changed file | `c11c453b…` / 410245 B (`Sources/MLXFastModel/LagunaRuntimeModel.swift`) |
| reproduce with | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 ./benchmark.sh --local-submit` |

## The one number to keep: P's lower bound

Arm P (`NOREDUCE`) deliberately **deletes** the cross-lane reduction and is
therefore numerically wrong — it exists only as a speed-of-light bound on the
whole family "issue fewer cross-lane reduction instructions in this kernel". Its
95 % CI lower bound is **−0.395 µs/step = 0.006 % of `cs`**, about **12× below**
the −5 µs/step gain I preregistered as the smallest worth pursuing. Even the
physically unattainable version of this idea cannot pay. K's mechanism is a
strict subset of P's, so K cannot beat P's bound either.

**Consequence for #625: do not accept any patch in this family, mine or anyone
else's, on a mechanism argument alone.** The bound already says the ceiling is
zero at this harness's resolution. That is the sentence I would most like to
survive into your integration notes.

## Three traps in these results

1. **H4 is a geometry result, not a KV-bytes result.** Arm H halves the
   threadgroup count, which drops it below the 20 GPU cores on this box, so the
   machine is left partly idle. Its +35.959 µs/step regression is
   occupancy, and it says nothing about whether fetching fewer KV bytes would
   help. Do not cite H as evidence about memory traffic.
2. **K's null does not mean "shuffles are free."** It means shuffle *count* in
   this kernel is not the binding constraint at ±28 µs/step resolution. A
   different mechanism (load path, `fast::exp`, see §G.5 of the report) may still
   pay; those remain open and unmeasured.
3. **I missed my own noise forecast.** §C.3 predicted control sd ≈ 7.5 µs/step;
   the realised value was 16.354, a factor of 2.2. So K's null is a null at the
   resolution I actually achieved, not the one I promised. Closing K on its own
   terms (rather than via P's bound) would need n ≈ 124 blocks ≈ 27.6 h of
   wall-clock, which I judged not worth the box time given the bound.

## Three harness facts worth more than the result

1. **Never mix `--local-submit` and `--local-iterate` numbers in one
   comparison.** They differ by ≈ 1.44× on this workload, and the difference is
   a roughly fixed ~0.5766 s/run additive term, not a scale factor. Any table
   that mixes modes will manufacture effects far larger than anything in this
   assignment's search space.
2. **The thermal gate fires on essentially every run.** It fired in all 24 of my
   campaign runs, with waits of 0/10/20 s only. Treat a nonzero wait as normal,
   not as a signal, and record it per run — otherwise you will read the gate's
   own scheduling as a treatment effect.
3. **Budget power off sd ≈ 16 µs/step, not ≈ 7.5.** Half-percent-of-`cs` effects
   (~33 µs/step) are detectable in a handful of paired blocks; tenth-of-a-percent
   effects (~6.6 µs/step) are not, at any block count you can afford before the
   deadline.

## Pre-submission gate warning — this one is for you, because you will submit

You are the one who will spend a receipt, so please read §E.3 of the report
before you do. In short:

- CI applies `senpai/enforce-modifiable-surface.sh` as a **content rule against
  current trusted `main`**, not as a diff against your branch point. `research/`
  is **not** in `editablePaths`, so a branch that only adds documentation is
  still rejected by that gate. My branch fails it with 64 offenders, all 64
  under `research/` and **zero** under `Sources/`.
- `senpai/submit-official.sh` does **not** pre-check that rule. So the failure
  mode is: spend a receipt, then get rejected on paperwork. **Run the gate
  locally first.**
- A trap inside the trap: if your `refs/remotes/origin/main` is stale, the gate
  reports thousands of spurious offenders (mine reported 2231 against a
  2026-08-09 ref). Fetch first, then interpret.

## Verification state of this branch (see §E.4)

`research/maple-nezuko-r106b-verify-handoff.sh` runs six independent checks and
reports each one's own exit status. Results: clean `rm -rf .build && swift build
-c release` **passes**; the editable-byte budget is unchanged and byte-identical
to §E.2's recorded line; the `Sources/` digest is unchanged from §E.1; the
surface gate fails only on `research/` docs as described above; `swift test`
runs 457 tests across 6 suites with **exactly one** issue,
`senpaiOperationalGuidanceMatchesTheDeployedRankedPath`, which shells out to
`senpai/test_submit_official.py` whose `setUp` performs a `git push` in a
scratch repo and is refused by this sandbox's git shim — I touched no file under
`senpai/` or `.github/`, and all nine of that file's tests fail standalone in
about a second, so the failure is environmental. Commits after the attested one
change only `research/` prose, so the digest, build and test verdicts stand.

## Box state at handoff

All my jobs are terminal; I hold no GPU. Total occupancy for this campaign was
about 2.5 h of GPU time. Sinks left in `/tmp` (`r106b-packred-evidence.tsv` and
friends) are reproducible from the scripts in `research/` and are not needed by
you.

## Standing caveats

1. **Rule 98.9**: no kernel-local or cache-resident number appears anywhere in
   this handoff. Every Δ quoted is a whole-model paired `--local-submit` figure.
2. **Standalone this lever could never clear frieren's 0.4 %-of-`cs` bar**
   (≈ 26 µs/step). The entire Stage 0 residual it targets is **0.295 % of `cs`**
   (+19.405 µs/step, itself a null), so even a perfect recovery of the whole
   residual would fall short. Combined with the closed bound above, that makes
   it a non-starter composed as well.
3. **frieren's #597 margin certificate is moot here.** It would have been
   required only if I recommended shipping a non-bit-exact kernel. I recommend
   shipping nothing, and the kernels are bit-exact anyway.
4. **Bit-exactness caveat.** PACKRED and H4 reproduce the baseline exactly
   (error 0 on all 8 decode steps; per-step sequences byte-identical across
   arms, `md5 6671d9cd…`). My exactness oracle's own exit code is nonzero
   because of a **baseline prefill artefact of 0.125 that reproduces with all
   gates off** — caught only by the gates-off negative control. It is a property
   of the baseline, not of my kernels. Since I recommend zero bytes, nothing
   here is load-bearing.
5. **Scope**: this work touches only the sliding attention kernel. It does not
   touch `residual_rms_router` or router prefetch (frieren), the NVFP4 qmv inner
   loop or weight encoding (tanjiro), decode dispatch/encode ordering (fern),
   the QKV projection kernel (edward, #629), or the routed K-loop (alphonse,
   #630). The default-off measurement gates are retained on my branch so that
   §E's source digest matches the binary that produced the numbers; adopt none
   of them.
6. **What is still open** (§G.5): a pre-specified Stage C campaign on the
   sliding kernel's *load path* and on `fast::exp`, described but not
   implemented. If anyone revisits this kernel, that is where to point them —
   not at reduction counts.
