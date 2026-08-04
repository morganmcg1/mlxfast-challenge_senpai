SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

# PR #19 — Cold first-touch cost in the scored 512-token forward

- Student / PR: `maple-fern` / #19 (`maple-2026-08-04c-cold-first-touch-forward`, revision `r1`)
- Hypothesis and target cost: PR #11 recorded a cold 512-token forward at
  584.09 ms against a warm median of 555.15 ms and attributed the ~30.5 ms gap
  (~5.2% of the forward, ~15.8% of the M5 prefill window) to first-touch page
  faults and cold caches paid *inside* the timed window. The arm was to
  localize that cost and move it into the untimed constructor window.
- Decision: **dead hypothesis**. The premise does not reproduce. There is no
  first-touch cost inside the timed window to reclaim, and the one mechanism
  that could have "moved" allocator state across the phase boundary is a
  circumvention of a documented trusted defense, not an optimization.
- `BASE_SHA` / candidate commit: `3e8e43522aeb3222cef45fe8852fb78eed673e10` /
  see final HEAD of `maple-fern/cold-first-touch-forward`
- Submitted candidate files: **none**. `git diff BASE_SHA -- Sources Vendor` is
  empty; the scored surface is byte-identical to the base.
- Supporting test or documentation files: `research/prefill_probe.py` (added a
  `--gap` option for duty-cycle control) and this report. Research-only, not on
  the scored surface.

## Part 0 — Where the timed window starts and ends, and how much untimed headroom exists

| Boundary | Location | Fact |
| --- | --- | --- |
| Prefill timer | `Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:809-811` | Wraps exactly one worker round trip for the 512-token prompt. |
| Prefill repetitions | `Sources/MLXFastModel/Constants.swift:129-130` | 1 timed run, **0 warmup**, not editable and not overridable. |
| Decode timer | `LagunaRuntimeBenchmark.swift:966-1010` | `beginDecode` (charged: the 512-token seed forward) + 128 single-token steps, divided by 128. |
| Process isolation | worker spawn per phase | Prefill, decode, and correctness each run in a **fresh worker process**. Nothing from an earlier phase warms a later one. |
| Allocator reset | `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:180-197` | At every phase start, after the parent timer is already running: `Memory.cacheLimit = 6 GiB; Memory.clearCache(); guard Memory.cacheMemory == 0`. |
| Untimed window | `Sources/MLXFastModel/LagunaRuntimeWeights.swift:470-517` | `warmLibraryModel`: one 512-token prefill, one decode step, argmax PSO warm, fused-attn PSO warm — all before the protocol hello. |
| Untimed window (M5 only) | `LagunaRuntimeWeights.swift:546-580` | `wireResidentWeightsIfEnabled`: `Memory.clearCache()` then wire **1.0 × live bytes + 64 MiB ≈ 31.4 GiB**, gated on `physicalMemory >= 96 GiB`. |
| TTFT budget | trusted stack | There is **no maximum-seconds TTFT threshold constant** anywhere in the trusted stack — only `passed` / `> 0` checks. TTFT is measured in the correctness worker and excludes load and warm. The hello timeout is 15 min. |

So the untimed budget for prewarming is effectively unbounded, and the
hypothesis was not blocked by headroom. It was blocked by there being nothing
left to prewarm:

1. The shipped frontier **already** prewarms the exact thing the hypothesis
   targets, in its strongest available form. On the official ≥96 GiB M5 the
   constructor wires the entire ~31.4 GiB live footprint through
   `set_wired_limit` before the hello. Wiring *is* first-touch elimination:
   after the resize commit the weight pages are resident and non-evictable.
   The dose table in that comment (42 MiB → −4.2% prefill … 1.0× → −28.3%)
   is the already-harvested version of this hypothesis.
2. On this 48 GiB host the ≥96 GiB guard is false, so every local number below
   is the **unwired** path — the worst case for first-touch cost. Even there,
   the cost is zero (next section).

## Part 1 — The premise does not reproduce

`research/prefill_probe.py` issues N back-to-back 512-token forwards through one
fresh worker process on the identical scored prompt
(`correctness_prompts/public_longcopy_gate_english_512_256.json`, golden hash
`b9509697c08a2cf3…`; the probe's greedy token matches
`cases[0].expected_tokens[0] = 5991`).

**Six back-to-back forwards, no idle gap (unchanged BASE_SHA):**

| Forward | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ms | **544.72** | 546.68 | 546.11 | 547.48 | 546.81 | 546.74 |

The first forward is the **fastest of the six**. There is no cold-page penalty,
no first-touch ramp, and no warm-up curve. A hypothesis that predicts
+30.5 ms on forward 1 predicts the opposite of what happens.

**What the 584-vs-555 observation in PR #11 actually was.** Request *cadence*,
not page state. Inserting a 3 s idle gap before each request in the same process
moves every forward up by 12–14%:

| Forward (3 s gap) | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ms | 586.77 | 621.48 | 622.26 | 614.67 | 606.71 | 608.56 |

A slower-cadence or profiler-hooked measurement run (PR #11's "cold" sample)
sits higher on this curve than a back-to-back run for reasons that have nothing
to do with the code under test, and the effect persists on forwards 2–6, which a
first-touch explanation cannot produce. (PR #11's base was also `0d980bb`, whose
only `Sources` delta to `3e8e435` is `LagunaLmHeadPrune.swift`, so the absolute
numbers are not directly comparable either.)

**A real, systematic, and irrelevant gap: harness vs in-process probe.** The
harness's charged first forward on the unchanged base is consistently ~4–6%
above the probe's:

| Measurement | first-forward ms |
| --- | ---: |
| probe, back-to-back, unsandboxed (4 samples) | 544.07 / 544.72 / 546.86 / 547.49 |
| probe, one slow sample | 576.37 |
| `--local-iterate` harness run 1 (`aa83b22`) | 576.36 |
| `--local-iterate` harness run 2 (`dda075d`, A/A) | 568.86 |

Two plausible causes: the idle gap between the constructor's warm forward and
the parent's timed request (the cadence effect above, measured at +12–14% for
3 s), and the harness worker running under `sandbox-exec` with
`tools/deny-network.sb` while the probe does not. It is *not* paging — Part 2
prices fresh-buffer cost at zero. It is also **score-neutral**: the official
metric is a same-session paired ratio, so a systematic per-run environment cost
appears in both arms and cancels. Its only consequence is that absolute
in-process probe milliseconds must never be compared against harness
milliseconds.

## Part 2 — Pricing the allocator, so the null result is not just an absence

If first-touch cost existed it would show up as a cost of *fresh* MTLBuffer
allocation inside the window. I measured that directly with two temporary,
env-gated research instrumentations (`DARKBLOOM_TRACE_ALLOC`,
`DARKBLOOM_PROBE_CACHE_LIMIT`), both since reverted (commit `dda075d` restores
the surface to `BASE_SHA`).

Allocator state at timed-forward entry, on the unwired local path:

| Quantity | Value |
| --- | --- |
| live (`active`) MLX buffers | 35.75 GB (≈21.2 GB weights + ≈14 GB fused/packed copies) |
| cache at entry | **0 bytes** (the trusted reset) |
| process peak | 39.07 GB, never exceeded by a timed forward |
| cache after one 512-token seed forward | ≈1.14 GB — i.e. one scored forward creates ≈1.1 GB of fresh buffers |

Forcing essentially every one of those 1.1 GB of allocations to be a fresh
`newBuffer` (cache limit 0) instead of a cache hit:

| Cache limit | Sample 1 | Sample 2 | Sample 3 |
| --- | ---: | ---: | ---: |
| 6 GiB (control) | 547.49 | 547.31 | 546.52 |
| **0** | 544.07 | 547.89 | 546.51 |
| 256 MiB | 576.37 (slow sample) | 546.65 | 550.93 |

Fresh-allocation cost is **indistinguishable from zero** at this measurement
resolution. On a unified-memory device with the pages already faulted by the
constructor's 512-token warm forward, `newBuffer` is cheap and the first-touch
term the hypothesis is built on does not exist. This also means the legal
version of the idea — reducing the ~1.1 GB of transient bytes per forward —
would be optimizing a measured zero.

## Part 3 — Integrity ruling on the only mechanism that would have "worked"

Recording this explicitly so it is not re-derived. The trusted reset clears the
allocator cache but cannot touch *live* buffers. A submission could therefore
hold a pre-touched buffer pool **live** across the phase boundary and release it
in the first line of the scored forward, donating warm buffers to the charged
window. The trusted harness names this exact attack in its own comment:

> The substantive defense is `Memory.clearCache()`, which removes every free
> buffer accumulated during unscored initialization so it cannot subsidize the
> first charged forward.
> — `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:174-177`

The mechanism is a deliberate circumvention of a documented trusted defense and
**must not ship**, independently of whether it would score. (A frontier review
concurred, and per Part 2 its upside is ≈0 anyway.)

The cadence sensitivity in Part 1 has an equally tempting and equally
inadmissible reading: keep the GPU busy across the hello→request boundary so the
SoC is already boosted when the timed request arrives. That does not make
inference faster; it manipulates the measurement environment, and it defeats the
purpose of the harness's own 40 °C thermal gate. Treat Part 1 as a
**measurement-protocol caveat**, not a mechanism. Nothing may be in flight
across a request boundary.

### Evidence

- Host, memory profile, toolchain, and thermal policy: AWS Apple **M4 Pro,
  48 GiB** unified memory → low-memory startup profile; `is_nax_available()`
  is false; the ≥96 GiB wired-residency path is **inactive locally and active
  on the official M5**. Standard `benchmark.sh` 40 °C cool-down gate on every
  harness run.
- Exact baseline and candidate commands:
  - `./benchmark.sh --local-iterate` on the unchanged base, run twice (A/A) at
    `aa83b22` and `dda075d`; both have an empty
    `git diff BASE_SHA -- Sources Vendor`.
  - `python3 research/prefill_probe.py --reps 6` and
    `python3 research/prefill_probe.py --reps 6 --gap 3` for the in-process
    series; the probe drives one fresh worker on the scored prompt.
- Tests and risk-based checks run: `passed_correctness: true` on both harness
  runs; probe greedy token equals the golden `expected_tokens[0] = 5991`;
  `git diff BASE_SHA -- Sources Vendor` empty after revert.
- Correctness and serial-protocol verdict: **green / not applicable** — no
  scored-surface change was made, so the serial non-speculative contract is
  untouched. Every probe request supplies its own tokens and advances KV by
  exactly the supplied length.
- Divergent tokens or failure category, if any: none.
- Peak RAM or generated-weight size, if relevant: 39.07 GB process peak during
  a scored phase on the unwired local path; `weights_byte_count`
  21,568,891,382; editable-surface headroom unchanged at 67,056 bytes.

| Metric | Baseline (run 1, `aa83b22`) | Baseline (run 2, `dda075d`) | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.013508382484375 | 0.0135727106171875 | 1.0048x (+0.48%) |
| prefill seconds/token | 0.0011257115078125 | 0.001111057373046875 | 0.9870x (−1.30%) |
| same-host paired estimate | — | — | — |

There is no candidate column: the scored surface is byte-identical to the base,
so the two harness runs above are an **A/A noise-floor measurement**, not a
paired baseline/candidate comparison. `primary_metric.available` is `false` for
that reason, not because a run failed. Both runs reported
`passed_correctness: true`.

Useful campaign number from this A/A pair: a single `--local-iterate` run on
this host reproduces itself to within **≈1.3% on prefill and ≈0.5% on decode**.
Any single-run prefill delta under ~1.5% is noise here; the decode measurement
is the tighter of the two despite its 33% per-step σ, because it averages 128
steps.

Note on local `prefill_speedup`: `--local-iterate` compares against the pinned
official constant `officialBaselinePrefillSecondsPerToken = 0.00036751938916015625`
(`docs/benchmark-window-freeze.md:180`), an M5 number. The resulting local
`prefill_speedup ≈ 0.33` is the M4 Pro / M5 hardware ratio, not a regression;
only same-host prefill *seconds per token* is comparable here.

### Conclusion

- What happened and why: the arm's premise — ~30.5 ms of reclaimable
  first-touch cost inside the timed window — is false on this host. The first
  512-token forward in a fresh worker is the fastest of six, and forcing every
  allocation in the window to be fresh costs nothing measurable. The original
  cold-vs-warm gap is explained by request cadence (+12–14% at a 3 s idle gap,
  and persisting on forwards 2–6, which first-touch cannot do), plus a
  systematic harness-vs-probe environment cost that cancels in the paired
  ratio. Separately, the shipped frontier already performs the strongest form
  of this prewarm on the official host by wiring the whole ~31.4 GiB live set
  before the hello.
- Evidence for or against the mechanism: against, on three independent axes —
  the ordering of the six-forward series, the cache-limit-0 pricing, and the
  existing wired-residency path. No axis supports it.
- Uncertainty or M5 transfer risk: all timing is M4 Pro. The specific
  millisecond values do not transfer. The *structural* conclusions do and, if
  anything, are stronger on M5: the official host wires the entire live set in
  the untimed window, which removes page-fault exposure that this local host
  still carries. The one thing an M5 measurement could change is the magnitude
  of the cadence effect, which would be a measurement-protocol finding, not a
  mechanism.
- Smallest useful next action: none on this hypothesis. For the campaign, adopt
  the two protocol rules this arm produced. (1) **Never compare a first-forward
  sample against a later-forward sample, never compare across request cadences,
  and never compare in-process probe milliseconds against harness
  milliseconds** — each of those axes moves the number by 4–14% with the code
  held constant. (2) On this host a single `--local-iterate` run reproduces to
  ≈1.3% on prefill and ≈0.5% on decode, so a sub-1.5% single-run prefill
  "win" is not evidence.
- Recommendation: **close**. Zero of the three authorized official M5
  submissions were used; there is no candidate worth a ranked slot.
