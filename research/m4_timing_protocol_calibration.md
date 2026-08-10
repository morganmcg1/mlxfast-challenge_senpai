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

Pending collection and frozen analysis.
