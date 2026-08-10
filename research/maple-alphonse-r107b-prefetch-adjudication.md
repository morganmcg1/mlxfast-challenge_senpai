# r107-B — Adjudicating PR #454's routed gate/up depth-1 preload

**Verdict: GATE CLOSED. Killed at gate 1 (kernel-local). Zero-byte submitted diff.**

Student `maple-alphonse`, PR #630, branch
`maple-alphonse/r107-routed-prefetch-adjudication`, base
`ca39d2163255a4fdda39609447328b76acd7f0a9`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s`, DRAM peak 266.3 GB/s.
W&B: https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/1nlxutje

---

## 1. The assignment had to be reframed: the mechanism is already shipped

The assignment asked me to *reconstruct* PR #454's depth-1 four-K-block preload
and measure whether it pays. It cannot be reconstructed, because **it is already
in the tree and default-ON**.

`lagunaRoutedSwiGLUQMVPackedTop8R1Kernel`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:7915–8027`, Metal name
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`) is selected whenever
`lagunaRoutedGateUpR1Enabled` is true, and that flag is
`ProcessInfo…["DARKBLOOM_ROUTED_GATEUP_R1"] != "0"` — **on unless explicitly
disabled**. The kernel body is a textbook depth-1 software pipeline:

| stage | lines | what it does |
|---|---|---|
| prologue peel | `:7956–7970` | loads K-block 0 codes + scales before the loop |
| latch + guarded next fetch | `:7984–8001` | `cur_*` registers, then `const uint next_block = block + block_width; if (next_block < input_width) { … }` |
| FMA on latched registers | `:8003–8008` | `laguna_nvfp4_qdot_codes_16` |

`input_width = 2048`, `block_width = 512` ⇒ **4 K-blocks**, i.e. exactly #454's
"four-K-block depth-1 preload". The sibling non-R1 kernel at `:7892` is dead by
default.

So the only honest one-axis experiment is the **revert direction**: delete the
preload, change nothing else, and ask whether the shipped default earns its
keep. That is what I measured.

PR #454's patch itself does not apply to this base (`git apply --3way` conflicts;
15,978 diff lines of drift on that file since its timed commit
`7f35354247dbd79b5c9c2276f0814d56387668a5`), which is a second, independent
reason reconstruction-by-patch was not available.

## 2. Prior art (Rule 83)

Grepped `research/`, `notes/`, `docs/`, `senpai/` for `454`, the kernel name, and
`prefetch`/`preload`/`pipeline` in this family.

- **PR #454 is nowhere in the archive by number**, so no newer experiment
  adjudicated it and the arm was not pre-empted.
- **But the archive had already reached my §1 conclusion qualitatively.**
  `research/RESEARCH_ARCHIVE_through-round-91.md` states: "⛔ **L2 (routed-twin
  K-block prefetch) is RETIRED as moot** — `next_block` k-loop staging already
  ships in the adopted frontier." I missed this on the first pass because the
  archive names the lever `L2 (routed-twin K-block prefetch)` and never cites
  #454. **Anyone re-greping this family should search the mechanism words, not
  the PR number.** What the archive did *not* have, and what this round adds, is
  the quantitative adjudication: the shipped staging is not merely present, it is
  worth 0.00 % ± 0.07 % kernel-local in the production regime, so retiring the
  lever as "moot" was right for a reason stronger than "already there".
- The relevant instrument already existed: `research/fern_r99_qmv_probe.swift`
  plus `research/fern_r99_qmv_variants.py` and the `fern-r99` / `fern-r100`
  artifacts. Rule 58 says reuse, don't re-author — I reused the probe verbatim
  and only added arm generation and analysis.
- **fern r99/r100 already measured this direction but could not attribute it.**
  At the faithful TG=2048 rung, cache-defeated, four template arms came out
  *faster than shipped*: `tmpl_s1` +1.824 %, `tmpl_s2` +1.977 %, `tmpl_s4`
  +1.776 %, `stage4_cand` +1.723 %, 21/21 rounds, |t| > 13 — and **flat in
  staging depth**. Every one of those arms changed preload depth *and* loop
  spelling together, so the contrast could not say which axis paid.
- PR #543 shipped `stage4_cand` in situ and got **−25.5 µs/tok (−0.196 %)**
  against a 137.2 µs/tok same-arm spread: a non-transferring null.

My job was therefore to split the axis that r99 confounded.

## 3. Instrument

`research/maple-alphonse-r107b-prefetch-adjudication.py` re-emits the arms
directly from the working tree and `…-prefetch-adjudication.sh` runs them
through fern's probe. Four arms:

| arm | bytes | role |
|---|---|---|
| `depth1_shipped` | 9,561 | reference, re-emitted from the live source |
| `noop_control` | 9,561 | **byte-identical** copy, distinct pipeline — Rule 79 in-run slot null |
| `depth0_oneaxis` | 8,872 | **candidate: preload deleted, one axis only** |
| `fault_control` | 8,858 | deliberately wrong up-scale index, proves the bitwise gate can fail |

Fidelity evidence:

- **Reference drift vs fern's r99 artifact: NONE (byte-identical).** fern's
  r99/r100 ladder is therefore directly comparable to mine.
- Rule 77 rung: TG=2048 with 64 threads/TG and 2 rows/simdgroup reproduces the
  shipped dispatch geometry exactly (grid `8*256*64 = 131072` ⇒ 2048
  threadgroups ⇒ 4096 logical rows = 8 experts × (256 gate + 256 up)).
- Rule 75: `Sources/` + `Vendor/` digest
  `b196bafa2d7738636837efa895fe2cc293a0633321b5c2845e708426656cf544` recorded
  before and after timing, hard abort on mismatch. Unchanged.
- **The fault control tripped the bitwise gate first**, before any timing arm
  ran; the script `exit 2`s if it does not. The candidate passed the same gate.
- Occupancy control: all three timing arms report identical
  `maxTotalThreadsPerThreadgroup = 1024`, `threadgroupMemory = 0 B`,
  `execWidth = 32`. The revert does **not** change occupancy, so nothing here is
  an occupancy artifact — the control that #540's "lost codegen quality" story
  required.
- The one-axis diff is bitwise-equivalent by construction: for `block == 0` the
  inline addressing collapses to the shipped prologue peel, and for `block > 0`
  to the shipped `next_block` fetch.
- Arithmetic, reduction, output layout, 64-thread geometry and the prefill path
  are untouched.

Two regimes, because the answer depends entirely on which one you believe:
`resident` (`FERN_DEFEAT_SLOTS=1`, everything in SLC) and `defeat`
(`FERN_DEFEAT_SLOTS=64`, cache-cold). **The defeated regime is the decisive
one**: the scored decode step streams 1,671.40 MB and cannot be served from
cache.

## 4. Results — faithful TG=2048 rung, two independent sessions

`gain% > 0` means **removing** the shipped preload is faster. 32 alternating
control/candidate rounds per session, 500 reps per round, order reversed every
round; **64 alternating rounds total** (assignment asked for ≥30).

| session | regime | gain % | CI95 | even-order | odd-order | rounds faster | noop control | same-session null |
|---|---|---|---|---|---|---|---|---|
| s1 10:23:29Z | **defeat** | **−0.038** | [−0.104, +0.028] | −0.029 | −0.046 | 13/32 | −0.010 | +0.025 |
| s2 10:32:59Z | **defeat** | **−0.037** | [−0.163, +0.089] | −0.108 | +0.034 | 17/32 | −0.048 | +0.173 |
| s1 | resident | +1.224 | [+1.166, +1.282] | +1.233 | +1.214 | 32/32 | +0.157 | +0.306 |
| s2 | resident | +1.207 | [+1.113, +1.302] | +1.114 | +1.301 | 32/32 | +0.242 | +0.274 |

Reference cost 39.03 µs/dispatch (defeat), 36.65 µs/dispatch (resident).

**The defeated-regime null replicates to 0.001 %** across two independent
sessions. Rounds-faster is a coin flip (13/32, 17/32) and the sign is not stable
across dispatch order in s2. Against the assignment's 0.5 % kill threshold the
measurement is ~7× tighter than it needs to be, so this is a **powered** null,
not an underpowered one. Null-subtracting the same-session null makes it
*worse* for the candidate (−0.063 %), so the conclusion is robust to the
instrument-bias correction the archive warns about.

Gate checks at TG=2048, defeat: `gain ≥ 0.5 %` **FAIL**; `CI excludes 0`
**FAIL**; sign stable across order **FAIL** (s2); sign stable across rounds
**FAIL**; noop control within ±0.5 % PASS.

## 5. What actually explains fern r99's +1.8 %

This is the useful part. Two facts sit side by side:

- **resident: removing the preload is +1.2 % faster** (32/32 rounds both
  sessions, t = −42, ~5–8× the local null floor). With no memory latency to
  hide, the pipeline's extra instructions and live registers are pure cost, and
  deleting them buys 0.45 µs/dispatch of issue time. So the revert **is** a real
  codegen improvement.
- **defeat: the same deletion is worth 0.00 %.** Cold, the 0.45 µs of issue time
  the pipeline costs is almost exactly the 0.45 µs of DRAM latency it hides.

**The depth-1 preload is a wash. It buys back precisely what it costs.** That is
the textbook outcome for a kernel that is issue-bound at ~90 % of its issue-rate
floor, and it lands exactly on Frieren r98's calibrated prior for this class of
change (≈0 ± 10 µs/step on M5, P(≥40 µs/step) ≈ 12 %).

It follows that **essentially none of fern r99's +1.8 % is the depth axis**: I
price that axis at −0.038 % ± 0.07 % in the very same rung and regime where
r99 measured +1.824 %, i.e. **−2 % of r99's effect**. The residual therefore
belongs to the other axis r99 changed at the same time — loop spelling, and
specifically rolled-vs-unrolled codegen (the archived #543 AIR diff shows 8 phi,
2 br, 5 gep and 4 dead loads dropped with identical math). That axis was
already shipped by PR #543 and already measured non-transferring in situ. r99's
"flat in staging depth" is now explained: s1/s2/s4 all unroll identically, so
they all collect the same spelling win and none of them collects a depth win,
because there is no depth win to collect.

## 6. Ceiling arithmetic — why no model-level timing was justified

39 sparse layers × 1 routed gate/up dispatch = 39 dispatches per decode token
(4,993 charged-window launches).

```
depth axis  = −0.038 % × 39.03 µs × 39  =  −0.58 µs/token
CI upper    = +0.089 % × 39.03 µs × 39  =  +1.35 µs/token
promotion bar                            =  68.7 µs/step
```

The depth axis is worth **−0.6 µs/token, 95 % upper bound +1.4 µs/token = 2.0 %
of the promotion bar**. Even the *resident* effect, which the scored workload
never sees, is only 17.5 µs/token = 25 % of the bar. Spending a cooled ABBA
whole-model campaign — the assignment's gate-2 — on a lever with a certified
ceiling of 2 % of the bar would have been waste, and the assignment's own kill
rule (`<0.5 %` kernel-local ⇒ kill) says so. **I stopped, and I did not run the
20 GB weight transform or any model-level timing.**

Rule 71/80 footprint: the probe moves 4,456,448 B per dispatch
(4096 rows × 2048 × 0.53125 B) in 39.03 µs = **114.2 GB/s = 42.9 % of the M4 Pro's
266.3 GB/s peak**. The rung is not bandwidth-saturated, which is consistent with
the issue-bound reading and with the family being 10.4 % of the step's
1,671.40 MB.

## 7. What this says about PR #454's whole-model sign flip

#454 reported decode 1.008149 (r1 AB), 1.003309 (r2 AB) and **0.997818 (r2 BA)**
— the sign flipped with run order. The natural reading was "real but fragile
mechanism". The kernel-local instrument says something simpler and stronger:
**there is no mechanism-sized effect to be fragile about.** In the regime the
scored step actually runs in, the mechanism is 0.00 % ± 0.07 % kernel-local.
#454's ±0.3 % whole-model spread is the paired-channel noise floor doing what
it does (my own host's `--local-iterate` MDE is ±0.73 %, single-run decode σ is
48–49 µs/step), not a mechanism appearing and disappearing.

This also matches the standing `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` precedent from
the other direction: there a clean −6.39 µs/step kernel-local win became
+34.58 µs/step *slower* end to end. Kernel-local and whole-model are weakly
coupled in this family; here both are zero, which is the consistent case.

## 8. Recommendation

**Leave `Sources/MLXFastModel/LagunaRuntimeModel.swift` exactly as it is.**

- Do **not** revert the shipped preload. It is not a pessimization: the revert is
  a null cold, and the only regime where it wins is one the scored workload never
  enters.
- Do **not** re-open #454. Its mechanism is shipped, default-ON, and worth zero.
- Mark the depth axis of the routed gate/up QMV family **closed by measurement**,
  alongside the already-closed depth ladder and the already-closed sliding-window
  prefetch arm (#540).

Submitted-surface diff: **0 bytes** (budget allowed 4,096). All work landed in
`research/`, which is not part of the submitted surface.

## 9. Follow-ups I did **not** implement

1. **Unroll axis, isolated.** A one-line `#pragma clang loop unroll(full)` arm on
   the shipped kernel would isolate rolled-vs-unrolled from the pipeline and
   would finish the r99 attribution completely. I did not run it because (a) it
   is outside this assignment's one axis, (b) #543 already shipped that spelling
   and measured it non-transferring, and (c) its honest ceiling is +0.08–0.22 %
   score — below the bar. **Rule 70 (no sixth MoE-QMV codegen arm) also points
   away from it.** Advisor's call.
2. **Cheap AIR-level gate for future probes.** Counting phi/br nodes per arm
   before timing is free and would have predicted this result. Worth adding to
   the shared probe rather than to one experiment.
3. **Retire the `resident` rung from headline numbers in this family.** Two
   sessions here show it reports +1.2 % where the production regime reports
   0.0 %. Any future probe in this family that quotes a cache-warm number is
   quoting a 30×-inflated effect.
4. **The r99/r100 headline should be annotated in the archive.** Its +1.8 % is
   real but attributable to an axis that is already shipped; its depth
   interpretation is now falsified.

## 10. Process note (resolved)

An earlier pass hit a real `malformed_assignment` block: #630's body carried no
`<!-- senpai-assignment:v1 … -->` marker, so the typed submission had no route.
The advisor repaired the routing as revision `r107-b-rev1` and re-cut the
assignment commit on the newer advisor base `ca39d216`, which superseded the
commit my work sat on. I rebased all five research commits onto the repaired
assignment commit `71a65009` with no conflicts and no change to any measurement:
this arm's submitted-surface diff is zero bytes, so the base move cannot
invalidate it, and the probe's `Sources/`+`Vendor/` digest
`b196bafa2d7738636837efa895fe2cc293a0633321b5c2845e708426656cf544` is unchanged
across the two bases. All evidence above stands as measured.
