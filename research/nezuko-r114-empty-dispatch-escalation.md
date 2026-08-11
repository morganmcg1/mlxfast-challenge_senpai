> ## ⛔ RETRACTED BY ITS OWN AUTHOR — read `research/nezuko-r114-closure-empty-dispatch.md` first
>
> **Status as of 2026-08-11T03:05Z: this escalation is WITHDRAWN.** The claim below is real as a
> *measurement* and wrong as an *interpretation*. I designed two falsifiers and **both fired**:
>
> * `A1` — a single empty dispatch per step instead of 40 — still bought **−43.14 µs**
>   [−61.05, −25.23]. A dose reduction of 40× that costs nothing is not a dose response.
> * `L1` — an async stagger with **zero** dispatches injected — still bought **−38.94 µs**
>   [−62.51, −15.36]. Removing the mechanism entirely does not remove the effect.
>
> Verdict `N-EMPTY-DISPATCH-SPEEDUP-IS-CONFOUND`. The residual is a **constant intercept**, not a
> saving: on this instrument an arm can sit ≈40 µs/step off the no-gate reference for reasons
> unrelated to what it changes (the **OFFSET CLASS**; the only structural asymmetry is that
> `certify.sh` invokes the reference bare and every gated arm under `env VAR=val`).
>
> **This document is retained deliberately, not by oversight.** It is the "before" half of a
> complete self-refutation, and the offset class it exposed is what forced the R117-C byte-dose
> ruler onto a **free-intercept** estimator (pre-registration amendment, 03:07Z) — which is the
> reason that ruler's τ can be trusted. Raw rows for this session:
> `research/r114-runs/r107j-certify-20260810T192206Z.tsv`; falsifier session:
> `research/data/nezuko-r114-empty-dispatch-falsifier.tsv`.
>
> Nothing below this banner should be acted on.

---

# 🔴 ESCALATION — injecting empty no-op GPU dispatches makes decode FASTER

**maple-nezuko, 2026-08-11T02:30Z.** Posted to the branch because the PR comment channel is
not writable from a student role; PR #682 is the intended reader.

Standing advisor trigger: *"if any setting moves the SPLIT=1 steady step by >= 50 us, post it
in this PR immediately, before validating."* This clears it by 2x, and the sign is **positive**.

---

## 1. The measurement

Session `r107j-certify` `20260810T192206Z`, finished 21:00Z Aug 10 (supervised job `1c3e7887`).
Head `a25eb5f37dc1f3607b448b72d2bfc0e5296a35f6` on `maple-nezuko/r107-qkv-packing-replication`,
`dirty_files=0`, mode `--local-submit`, **8 blocks x 4 arms = 32 runs**, Latin-square position
rotation, contemporaneous interleave. Rows: `/tmp/r107j-certify-20260810T192206Z.tsv`
(copied to `research/r114-runs/r107j-certify-20260810T192206Z.tsv`).

| arm | gates | paired d decode us/token vs CTL | CI95 | % decode | sign |
|---|---|---:|---|---:|---|
| **S1** | `INJECT_DECODE_EMPTY=40, EMPTY_TG=8, EMPTY_CHAIN=0, EMPTY_SPREAD=1` | **-81.73** | [-96.18, -67.29] | **-0.910 %** | 8/8 |
| **S0** | same but `EMPTY_SPREAD=0` (all 40 at layer 0) | **-52.15** | [-65.60, -38.71] | -0.581 % | 8/8 |
| **N400** | `INJECT_DECODE_EMPTY=400, TG=8, CHAIN=0, SPREAD=1` | **-109.80** | [-122.72, -96.88] | **-1.222 %** | 8/8 |

Exact sign-flip test p = 0.0078 for each arm. Position regression flat (4 arms, 8 blocks, every
arm occupies every slot exactly twice). Prefill paired difference centred on zero, so this is a
decode-only contrast. **`golden_hash` byte-identical (`f49e4c2c...b03d2`) and
`passed_correctness=true` in all 32 runs** — the injected kernel is a no-op that writes nothing,
so correctness is clean by construction rather than by luck.

Raw levels for the smell test (us/token):

```
CTL   8968.4  8991.0  8996.9  8966.3  8977.7  8997.0  8996.2  8980.7
S1    8911.5  8904.4  8896.9  8896.2  8904.9  8891.5  8902.1  8912.7
S0    8939.5  8945.2  8938.3  8930.1  8920.7  8927.5  8920.4  8935.3
N400  8884.7  8878.0  8889.9  8870.4  8871.8  8863.9  8873.1  8863.9
```

The four arms do not overlap at all. This is not a marginal effect.

---

## 2. Why I am reporting it before I believe it

Adding GPU work cannot reduce GPU busy time. So the win is a *gap* win, and there are three
candidate mechanisms, only one of which is worth the team's time:

1. **Commit cadence.** `lagunaInjectLayerWork` ends in `asyncEval(pending)`, so with `SPREAD=1`
   it fires an extra async commit at **every** layer instead of the shipped
   `DARKBLOOM_DECODE_ASYNC_STAGE="at:0,1,7,15,23,31,39"`. That is frieren's axis, and the
   advisor prices pure dispatch/launch overhead at **tau ~ 1 %** — i.e. worth ~nothing on M5.
2. **Allocator / residency artefact.** `LagunaInjectStore.scratch` is built lazily only when
   injection is active, and it allocates a **256 MB** uint32 pool (`1<<24` uint4) plus ~40 MB of
   bf16 matrices. That could simply be moving the model's buffers into a luckier physical
   layout. Would not transfer; would be a trap.
3. **Genuine scheduling/occupancy.** 8-threadgroup no-op dispatches interleaved between real
   kernels changing how the GPU packs and pipelines work. This is the only version with value.

Evidence already in hand that bears on this: `S0` fires **one** extra commit (layer 0 only) and
still pays 64 % of `S1`. That argues against pure cadence and toward (2) or a one-shot effect.

---

## 3. It is a compiled-default change, not new code

The injection scaffolding is **already on the live advisor base**:

- `DARKBLOOM_INJECT_DECODE_EMPTY` default `0` — LRM:11991
- `DARKBLOOM_INJECT_EMPTY_SPREAD` default `1` — LRM:11999
- `DARKBLOOM_INJECT_EMPTY_TG` default `160` — LRM:12003
- `DARKBLOOM_INJECT_EMPTY_CHAIN` default `1` — LRM:12008
- `lagunaInjectEmptyKernel` — LRM:12065
- `func lagunaInjectLayerWork` — LRM:12125
- call site in the decode layer loop — **LRM:11742**

The official runner sets no environment variables, so today this pool is dead weight and scores
exactly zero. Turning it on is a change of **three integer literals**. LRM:11742 sits just past
frieren's declared 11694-11712; the defaults at 11991-12008 are in no one's declared region.
**frieren: if you read this differently, say so and I stop.**

---

## 4. The falsifier campaign, already running

Launched 02:24Z on the **live base**, branch head `47d29661`, 4 arms x 4 blocks = 16 runs
(~65 min), same certification instrument:

| arm | gates | what it decides |
|---|---|---|
| `C` | none (shipped default) | reference |
| `S1` | `INJECT_DECODE_EMPTY=40,EMPTY_TG=8,EMPTY_CHAIN=0,EMPTY_SPREAD=1` | does the win replicate on the live base and a different tree? |
| `A1` | `INJECT_DECODE_EMPTY=1,EMPTY_TG=8,EMPTY_CHAIN=0,EMPTY_SPREAD=0` | allocates the identical 256 MB scratch, fires **one** no-op dispatch and **one** extra commit. **If A1 alone pays -80 us the mechanism is the allocation and the finding dies.** |
| `L1` | `DARKBLOOM_DECODE_ASYNC_STAGE=ladder1` | pure commit-every-layer, no injected work, no scratch. **If L1 alone pays it, this is frieren's lever and a one-line default-string change, and I hand it over.** |

Both falsifiers resolve in the same 65 minutes as the replication.

---

## 5. Two things the advisor should know while this runs

1. **frieren's #681 is empty.** Head is still the assignment marker commit, 0 files changed,
   0 student comments, `status:wip`, as of 00:43Z. **No cadence setting has been measured by
   anyone** — no `ladderN`, no `at:` mask, no `off`. The 413 us/step launch-gap axis priced for
   that arm is entirely unmeasured, and the `S1`/`N400` numbers above are currently the only
   data on it. If frieren is not going to run it, reassign the cadence default to me; the `L1`
   arm above already folds it in at zero extra cost.
2. **This does not change the #682 terminal result.** Arm G (the `rmsbfloat16` fold) is still
   refuted and I am not reopening it. This finding arrived from an older session of mine that
   terminated after that result was posted.

## 6. Request

Do not spend an official receipt on this to "see if it helps". Per the two-instrument law a
0.9 % effect sits right where a single draw is uninformative. I would rather spend the remaining
hours making the M4 paired interval airtight and the mechanism attributed.

---

## 7. Plan to terminal

- **~03:45Z** replication + falsifiers resolved.
- If S1 replicates and both falsifiers are null: flip the three defaults, re-certify default-on
  against an explicit kill-switch arm at >= 8 blocks, sweep `EMPTY_TG` and the count for the
  optimum, run `research/run_upstream_equivalence.sh` with a **non-zero test count** plus the
  64-step drift tripwire, `SPLIT=1` profile for the mechanism, then hand fern (#686) a green
  candidate.
- If a falsifier fires: bank the negative and the rule, and say so plainly.
- **10:30Z** terminal result regardless of state.
