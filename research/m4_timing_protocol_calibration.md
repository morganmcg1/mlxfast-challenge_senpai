# M4 timing protocol calibration

## Status and scope

Pre-data design frozen on branch `cedar-thorfinn/m4-timing-protocol-calibration` before any retained timing sample. This is an unchanged A/A calibration of `./benchmark.sh --local-iterate`; it does not modify or submit production, vendor, generated, weight, or harness files. The exact public workload is one validated 512-token prefill plus a 512-token seed and 128 teacher-forced one-token decode steps per invocation. M4 results are diagnostic; official M5 measurements remain authoritative.

## Frozen collection design

- Two independent sessions, each containing three complete mirrored cycles (48 invocations total).
- One cycle is `A B B A | B A A B`: an ABBA block followed immediately by reverse-order BAAB. A and B are labels for the identical commit, payload, worker, metallib, weights, and workload.
- Every invocation starts from the strict 40 C gate with `MLXFAST_LOCAL_FAN_PROMPT=0` and `MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1`. Distinct score and integrity paths are retained. No direct worker invocation or fan-setting change is allowed.
- Session 2 begins only after session 1 has ended and a later independent launch is made. The benchmark's process isolation and thermal gate apply to every sample.
- Before collection, run `./setup.sh`, record host/toolchain/fan-auto state, ensure no resident model worker, and hash the unchanged submitted payload, release worker, metallib, weights manifest, and golden fixture. Recheck hashes and fan-auto state afterward.
- Raw rows include session/cycle/block/position/label, UTC start/end, score and integrity paths, prefill s/token and us/pass, decode s/token and us/token, timed seconds, peak RAM, correctness and acceptance flags, commit/harness/weights/golden/transform hashes, worker/metallib/payload hashes, exit status, and rejection reason. Per-invocation logs remain local with published checksums.

No latency outlier is removed. A complete mirrored cycle is rejected only for an objective protocol failure: nonzero exit, correctness failure, missing score/integrity record, strict telemetry failure, non-auto fan state, overlapping model process, or any commit/payload/worker/metallib/weights/golden hash change. The raw row and reason remain in the table. At most one predeclared replacement cycle per session is allowed; otherwise the result is inconclusive. An interrupted pre-data build is not a timing sample.

## Frozen estimands and inference

Analysis uses log latency. Positive `g = mean(log A) - mean(log B)` favors nominal candidate B. For each metric, each ABBA and BAAB half-block produces one label contrast; a mirrored-cycle contrast is their equal-weight mean. The weighted projection is `0.25*g_prefill + 0.75*g_decode`, corresponding to the challenge score in log space.

Report geometric speedup `exp(g)`, percent effect, and two-sided 95% Student-t confidence intervals over the six complete mirrored-cycle contrasts. Also report ABBA-only and BAAB-only estimates/CIs, each session estimate, the ABBA-minus-BAAB order interaction, within-session linear position slope, and lag-1 residual autocorrelation. Cycle contrasts, not individual invocations, are the inferential units.

For a practical threshold `tau`, a promotion occurs only if all hold:

1. pooled point speedup is at least `1 + tau`;
2. the one-sided 95% t lower confidence bound is above parity; and
3. both session estimates favor B.

Apply this unchanged rule to prefill, decode, and weighted projection for `tau` = 0.1%, 0.15%, 0.2%, and 0.5%. This directly audits prior 1.001x/1.0015x, sign-agreement, and CI-above-parity gates. Compare ABBA-only against the full mirrored rule.

The A/A false-positive rate is the fraction of all 64 complete-cycle sign-flip assignments that pass the exact gate, flipping all three correlated metric contrasts together. Report actual A/A promotions separately. The analysis-only positive control divides every B-labeled latency by 1.002, preserves the observed noise/order structure, and reruns the same frozen gate; it never changes measured raw data.

Observed mirrored-cycle standard deviations parameterize deterministic Monte Carlo power (`seed=20260810`, 20,000 trials per point, Gaussian cycle effects, cycles split evenly across two sessions). Find the smallest injected effect giving 80% and 95% power by 0.001 percentage-point bisection. For true 0.1%, 0.2%, and 0.5% effects, find the smallest even cycle count reaching 80% and 95% power; convert cycles to runtime using observed median complete-cycle wall time. Repeat for prefill, decode, weighted projection, and ABBA-only versus mirrored.

The protocol is useful only if the real A/A data produces zero promotions, the 0.2% synthetic control is recovered, and a design of at most two hours has conservative MDE <=0.2% for at least one scored component. Otherwise the conclusion is **NO-GO** for sub-0.2% local promotion gates.

## Results

**Terminal decision: NO-GO for sub-0.2% local promotion gates; acquisition is inconclusive.** The strict physical protocol could not produce one valid latency, and its observed launch-time lower bound already violates the frozen two-hour usefulness condition. No production, vendor, generated, weight, or harness file changed.

### Acquisition outcome

`./setup.sh` completed successfully in 80.543 s (Senpai job `449ce758-2188-4f28-ae9b-bc41c32ac95b`). The first frozen A/A invocation ran through Senpai job `a6393b15-616c-4162-8ef3-72bd12cf8f03` with:

```text
MLXFAST_LOCAL_FAN_PROMPT=0 \
MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1 \
MLXFAST_SCORE_PATH=<unique score path> \
MLXFAST_INTEGRITY_PATH=<unique integrity path> \
./benchmark.sh --local-iterate
```

It began at `2026-08-10T15:18:44Z` and failed at `15:22:56Z`, exit 1, before timing. After model startup the strict prefill gate observed 44.1 C, cooled for 180 s, then failed at 40.2 C with minimum 40.1 C against the required `<=40 C` threshold. The score records `timed_benchmark_seconds=0`, zero checked steps, zero measured prefill/decode latency, and `error="local GPU cool-down gate failed for prefill with status 1"`.

No overlapping benchmark/model process was present afterward; fan mode remained `auto`. A quiet post-run snapshot at `15:24:28Z` showed GPU 40.015 C, CPU 40.042 C, GPU scaled load 1.2%, GPU power about 0.008 W, and fan 1004 RPM. This makes another unchanged launch unlikely to pass: idle equilibrium is approximately the strict threshold and startup adds heat. Raising fan speed or weakening the gate would violate the frozen protocol, so no replacement cycle was launched.

The rejected launch consumed 252 s. Even treating that failed pre-timing duration as an optimistic per-invocation floor, the frozen 48-invocation design requires at least `48*252/60 = 201.6` minutes. A valid invocation necessarily adds actual correctness/timing work, so the design cannot satisfy the two-hour usefulness cap on this host.

### Statistical result

| Required result | Outcome |
|---|---|
| Valid invocations / cycles / sessions | 0 / 0 / 0 |
| Pooled, ABBA, BAAB, session, order-interaction CIs | Not estimable |
| Position slope and lag-1 autocorrelation | Not estimable |
| A/A eligible promotions | 0 of 0 decisions |
| 64-sign-flip false-positive rate | Not estimable |
| Analysis-only 0.2% synthetic recovery | Not estimable; no observed noise structure |
| Observed 80%/95% MDE, power, required cycles | Not estimable; no cycle SD |
| Two-hour conservative MDE <=0.2% | Not demonstrated |

The machine-readable records are `research/m4_timing_protocol_calibration_raw.csv` and `research/m4_timing_protocol_calibration_summary.csv`. Missing values are `NA`, not zeros. An independent feasibility review also found the requested sub-0.2% false-positive, MDE, and power claims cannot be jointly supported by two sessions; synthetic injection would validate analysis plumbing only, not the physical noise claim. Therefore no favorable inference is made from this failed acquisition.

### Prior-experiment audit

The six frozen external examples reinforce why this calibration was needed, but were not fit as A/A data. PR #610 changed sign dramatically between fresh-worker/order blocks (sliding 1.070844x versus 0.691164x). PR #623 isolated TG512 measured 1.080204x in ABBA but 0.997265x in BAAB. PR #632 full-model prefill was 0.996257x in ABBA and 1.000434x in BAAB. PR #637 used 484 isolated observations to resolve a small negative effect (0.999452x), illustrating that high repetition can be informative for a short isolated harness but not this full-model launch budget. PR #639 reported 1.0659x ABBA versus 0.96948x BAAB with a lower 95% bound of 0.90006. PR #643 reported 1.012585x ABBA versus 0.996736x reverse order. These are evidence against trusting one favorable ordering, not substitutes for the missing unchanged-baseline calibration.

### Provenance and retained evidence

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2 (`25F84`), Darwin 25.5.0, Swift 6.3.3, macmon 0.8.2. Branch HEAD during acquisition was the pre-data commit `104099fb29b58fcc37aab14ac304eaa942d0278a`; worktree and submitted payload were unchanged.

- submitted payload SHA-256: `47121275b6239f422e8167b03c150409ee5af04e9eb508b015a8d8999ecb76ff`
- release worker: `da213603d93346a48ded636ef87e52550e00df5c9e78440c2cb089bdf2f348e8`
- metallib: `8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec`
- harness: `25fafafc593dc655f2cecd3550de1e428fb577de56df900955136a533bc9202e`
- weights: `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` (9 files, 21,568,891,382 bytes)
- golden: `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`
- transform source: `5929dfd16cedf35645e5a2bab62baa06ae4908382eae16917f1594bafb3715ec`
- runner: `86466a4754f021af4759d3dcc8386dc55b53e1fdb6adf2b7b736050ac151ef39`
- score / integrity / log: `701978aa767ab84439501357716f701cfd975839699fd9b1619d96a736471a46` / `beaa053de9ccaeb0e49eedd06f1f68a3ef0b4bb4ab0ffc57f642394103ea036e` / `1b43e318c61d58d7d8f76ce2a697ccadc2819aa85d7819ff3bc980307538ab70`
- raw manifest: `3f9cfba04c0b3123f34fe4f1fc990db3c2c5ce5d5fa639be80b8b1a12dc9c371`

Full logs, score, integrity record, manifest, and before-run provenance remain under the role workspace at `m4-aa-calibration-raw/session-01/cycle-01/`; only checksums and compact tables are committed. W&B is N/A because this local Swift/Metal inference harness does not emit W&B runs. No official submission was made.
