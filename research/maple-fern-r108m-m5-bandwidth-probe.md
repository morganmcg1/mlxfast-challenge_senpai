# R108-M Part 1 — N-DEGENERATE resolved: `alpha` is bracketed, and the two pools disagree for a reason that is not `alpha`

**Student**: maple-fern · **PR**: #664 · **Assignment**: `maple-r108-m-bandwidth-probe-and-freeze-custody` (`r108-m-rev1`)
**Base**: `705484b9e120d60a973d660fdbdd1ccc7cdfa124` · **Reconciled by**: branch created directly at the assignment commit `4aab2f34` (Rule 97.0: *neither* merge nor rebase was needed — the assignment branch is a fast-forward pointer at the advisor base; my one carried file is described in §10.1)
**Receipts consumed**: **ZERO**. **Scored surface touched**: **NONE** (§10.2).

---

## §0 Verdict

**`V-ALPHA-BRACKETED`**, plus one correction the campaign should adopt tonight.

| # | finding | number |
|---|---|---|
| 1 | **Measured M4 Pro DRAM read ceiling on this host** | **263.29 GB/s**, range [262.37, 263.49] over 6 independent working sets ≥192 MiB |
| 2 | **Rule 55's denominator `bytes/266.3` is 1.14 % optimistic** | 266.3 is 101.14 % of the measured ceiling |
| 3 | **`alpha` is bracketed, and the campaign's 0.4369 SURVIVES** | **`alpha` ∈ [0.4227, 0.4409]**; 0.4369 sits inside, in the upper part |
| 4 | My upper bound is **tighter than tanjiro's** | 0.44095 vs his alpha-free 0.4454 (1.00 % tighter), and derived independently |
| 5 | **The gather hypothesis is dead** | block-shuffled 64 KiB reads reach **100.0 % of sequential** at every DRAM-resident working set (9 points, 99.8–100.7 %) |
| 6 | **The real cause of N-DEGENERATE is byte-census composition, not `alpha`** | the `qkvo` pool implies an M4 achieved rate of **295.82 GB/s = 112.4 % of the measured DRAM ceiling** — physically impossible. **≥11.0 % of its counted bytes are cache-served, not DRAM.** |
| 7 | **No verdict anywhere in the campaign moves** | worst-case re-price is −3.24 % on a byte-regime price; nothing crosses a bar |

**One line for frieren and tanjiro, who are both blocked on this right now:** *keep using `alpha = 0.4369`; it is inside the measured bracket [0.4227, 0.4409]. The worst case is that byte-regime prices are 3.2 % optimistic. Do not re-derive anything. But stop using the `qkvo` pool to constrain `alpha` — its byte census counts cache-resident traffic and it is the reason the two pools disagree.*

---

## §1 Part 1 as written could not be executed, and why

The brief says:

> The resolving experiment already exists and is free: `research/fern_r101_bw_probe.swift`, your own tool, run on the official M5, **~7 seconds, zero receipts**.

**There is no zero-receipt path to the official M5, and there is no path at all for this probe.** I verified both halves before substituting anything:

1. `research/fern_r101_bw_probe.swift:1` declares itself *"Research-only host probe (not part of the submission surface)."* It is a standalone Swift executable, built with `xcrun swiftc -O … -o /tmp/fernbw` and run as a host binary.
2. It appears nowhere in the submitted surface. `grep -rn fern_r101_bw_probe Sources Package.swift benchmark.json senpai` returns **no hits**. It is not in `harnessHash()`'s coverage either (`Package.swift`, `Sources`, `Tests`, `benchmark.json`, `benchmark.sh`, `setup.sh`, `tools`, `README.md`, `TASK.md`).
3. The only channel to the official M5 is `senpai/submit-official.sh`, whose final line is `exec mlxfast submit --model senpai "$@"`. That submits **the benchmark harness**, not an arbitrary binary, and it **consumes a receipt**. There is no `--dry-run`, no probe mode, no non-scoring path — the script's only flags are the `--model` guard and the twelve surface predicates.

So "run this probe on the official M5" is not a thing that can happen: **not for zero receipts, and not for any number of receipts.** The 610 GB/s M5 constant we all quote was obtained by tanjiro from a *harness-embedded* instrument in PR #27, which is a different and much more expensive thing than running this file.

I spent ~4 minutes establishing that and then substituted the best zero-receipt experiment that actually bears on the question. **I did not consume a receipt and I did not ask for one.**

### §1.1 What I ran instead, and why it is genuinely resolving

The probe was *designed* for exactly this substitution. Its header, written in round 101, says of its third arm:

> `tanjiro` replicates the instrument geometry behind the 610 GB/s M5 constant (`tanjiro-pr27-interim.md:1044-1105`) … **Running the *same* instrument here is the only way to get a paired M4→M5 instrument ratio rather than a ratio of two different instruments.**

That is the whole trick. I cannot measure M5. But `alpha` is a *ratio*, and I can measure the M4 leg of a **paired** instrument whose M5 leg is already published. Instrument efficiency cancels in the ratio — which is the same pairing logic as my ABBA discipline, applied across hosts instead of across arms.

Cost: **6.027 s wall clock**, one `xcrun swiftc` build, zero receipts.

---

## §2 The measurement

Host: **Apple M4 Pro, 20 GPU cores**, macOS 26.5.2, `applegpu_g16s`. `rounds=15`, median of 15. Full log: `research/artifacts/maple-fern-r108m/m4-bw-probe-default.log`.

### §2.1 Autotune (Rule 77 geometry, printed for every timed configuration)

Swept `tgPerCore ∈ {2,4,8,16} × threadsPerTG ∈ {128,256,512} × ilp ∈ {1,2,4,8}` at a 512 MiB working set. Winner:

```
tgPerCore=2  threadsPerTG=256  ilp=8  ->  tg=40  grid=10240  ->  263.29 GB/s
```

The surface is flat: 44 of 48 configurations land in 250–263 GB/s. Only `threadsPerTG=128, ilp≤8` at `tgPerCore=2` is materially poor (218.7–226.9). **This host is not geometry-sensitive for streaming reads**, which retires a whole class of "maybe we launched it wrong" objections.

### §2.2 The working-set sweep — the ceiling and the cache shelf

| uniq MiB | GB/s | % of DRAM ceiling | regime | slc_fit |
|---:|---:|---:|---|---|
| 2 | 1675.96 | 636.5 | cache | fits |
| 4 | 1444.44 | 548.6 | cache | fits |
| 8 | 590.30 | 224.2 | cache | fits |
| 12 | 499.62 | 189.8 | cache | fits |
| 16 | 312.70 | 118.8 | **mixed** | marginal |
| 20 | 272.18 | 103.4 | dram | marginal |
| 24 | 265.58 | 100.9 | dram | marginal |
| 32–1024 | 262.37–263.69 | 99.7–100.1 | dram | spills |

**`MEASURED dram_read_ceiling = 263.29 GB/s`** (median of the 6 rows ≥192 MiB; full range across those rows 262.37–263.49, i.e. **±0.21 %**). **`MEASURED cache_served_ceiling = 1675.96 GB/s`** = **6.37× the DRAM ceiling**.

That 6.37× factor is the load-bearing number for §6.

### §2.3 The four published M4 denominators, adjudicated

| source | value | % of measured |
|---|---:|---:|
| theoretical 273.0 (r94 census denominator) | 273.0 | **103.69 %** — unreachable |
| **hardcoded 266.3 (Rule 55, `fern_r100_attn_probe.swift:71`)** | 266.3 | **101.14 %** — 1.14 % optimistic |
| roofline fit 260.6 (`decode-marginal-cost-ledger.md:940`) | 260.6 | 98.98 % — good |
| tanjiro pool-differential 237.4 | 237.4 | 90.17 % — 10 % low |

**Correction the campaign should adopt: Rule 55's floor `bytes/266.3 + 3.97` uses a denominator 1.14 % higher than this host can deliver.** The correct denominator is **263.29**. Direction: Rule 55 has been predicting floors that are **1.14 % too fast**, i.e. it has been *understating* how much time bytes cost, i.e. every byte-bound M4 floor is slightly optimistic. It is small and it does not move a verdict, but it is a free correction and it is mine to report since 266.3 is my own hardcoded constant.

The 237.4 figure is the one to retire: tanjiro's pool-differential method reads **10 % low** against a direct measurement on the same host.

---

## §3 The gather hypothesis is dead

The most natural explanation for "routed demands 597.1, qkvo demands 677.1" is that **the routed pool is a gather** and gathers are slower. The probe's `blk` arm tests exactly this: each threadgroup walks a pseudo-random permutation of contiguous 64 KiB blocks — the access shape of a routed-expert gather.

| uniq MiB | blk GB/s | **% of seq** | slc_fit |
|---:|---:|---:|---|
| 64 | 263.57 | **100.0** | spills |
| 96 | 263.58 | **100.1** | spills |
| 128 | 262.60 | **99.8** | spills |
| 192 | 265.31 | **100.7** | spills |
| 256 | 263.89 | **100.3** | spills |
| 384 | 262.41 | **99.9** | spills |
| 512 | 264.88 | **100.6** | spills |
| 768 | 263.37 | **100.4** | spills |
| 1024 | 264.56 | **100.5** | spills |

**Mean 100.25 %, range 99.8–100.7 %, over 9 independent DRAM-resident working sets.** Block-shuffled reads at 64 KiB granularity are **indistinguishable from sequential** on this host.

**Conclusion: gather access shape costs nothing at DRAM working sets, and therefore cannot explain a 13.4 % gap between the routed and qkvo pools.** One candidate explanation eliminated by measurement. (The sub-SLC rows are noisy — 75.5 % at 4 MiB, 120.3 % at 2 MiB — because at those sizes the permutation changes *which* cache the data is served from, not how fast DRAM is. They are not evidence about gathers and I do not use them.)

---

## §4 `alpha`: two independent constraints, opposite in sign

I can bound `alpha` from **below** with a paired instrument and from **above** with a physical impossibility. The two together bracket it.

### §4.1 Lower bound — the instrument-paired ratio

The `tanjiro` arm reproduces the PR #27 geometry (256 MiB pool, timed at S and S+6 grid-stride sweeps, bandwidth from the 6-sweep differential):

```
sweeps=2  us_med=2047.88      sweeps=8  us_med=8293.63
delta_bytes = 1610.61 MB   delta_us = 6245.75   ->  257.87 GB/s
tanjiro_instrument_pct_of_measured_dram_ceiling = 97.9%
```

The **same instrument** published **610 GB/s** on M5. For byte-bound work `alpha = T_M5/T_M4 = BW_M4/BW_M5`, and the instrument's own 97.9 % efficiency cancels in the ratio:

> **`alpha` ≥ 257.87 / 610.0 = 0.42274**

(It is a lower bound rather than a point estimate because the instrument's efficiency need not be *identical* on both hosts; 97.9 % on M4 is high enough that the residual slack is small, but I will not claim it is zero.)

### §4.2 Upper bound — the routed pool cannot beat physics

Tanjiro's routed pool demands an M5 ceiling of 597.1 GB/s. Under the `alpha` map that implies an M4 achieved rate of `597.1 × alpha`. That rate cannot exceed the measured M4 DRAM ceiling:

> `597.1 × alpha ≤ 263.29`  ⇒  **`alpha` ≤ 0.44095**

This is **independent** of the instrument pairing and **1.00 % tighter** than tanjiro's alpha-free bound of 0.4454 — and it is tighter for a good reason: his bound came from the pool algebra, mine from a direct measurement of the denominator.

### §4.3 The bracket

> ## **`alpha` ∈ [0.4227, 0.4409]**
>
> **The campaign's `alpha = 0.4369` is INSIDE the bracket**, at the 78th percentile of it.
> Deviation to the ends: **−3.24 %** (low end) / **+0.93 %** (high end).

**Answer to the brief's question 3 — "does the campaign's 0.4369 survive?" — YES.** And the direction matters: 0.4369 sits *near the top* of the bracket, so if it is wrong it is **too high**, meaning `T_M5` is being over-estimated, meaning **byte-regime M4 savings have been priced up to 3.2 % too generously**. Not the other way round. Nothing needs re-opening; a small number of things are very slightly over-valued.

---

## §5 The real cause of N-DEGENERATE

Tanjiro reported honestly that the two pools demand ceilings 13 % apart and concluded `alpha` is unidentified. He is right that they disagree. He is wrong about *what* is unidentified — and the measured ceiling shows it immediately.

At the campaign `alpha = 0.4369`, the two pools imply these **M4** achieved rates:

| pool | demanded M5 ceiling | implied M4 achieved | vs measured c4 = 263.29 |
|---|---:|---:|---:|
| routed | 597.1 | **260.87 GB/s** | **99.1 %** — at the ceiling, entirely consistent |
| qkvo | 677.1 | **295.82 GB/s** | **112.4 %** — **impossible** |

**The `qkvo` pool requires this host to read DRAM 12.36 % faster than it can.** That is not an `alpha` ambiguity. It is a statement that **the `qkvo` pool's byte census counts bytes that were never fetched from DRAM.**

Quantitatively: if a fraction `f` of the counted bytes are cache-served and therefore effectively free at the DRAM rate, then `(1−f) × 295.82 ≤ 263.29`, so

> **at least 11.0 % of the `qkvo` pool's counted bytes are cache-served, not DRAM.**

This is not speculation, and it is independently corroborated *inside the campaign's own documents*:

- The R107-E brief §3 (advisor-verified at `2454cc01`) states for the oproj/qkv kernel family that the activation vector is **16 KB for h64 and is shared by all 256 threadgroups, so after the first touch it is cache-resident, not DRAM**, and that `scale_bases` is **2 KB total and cache-resident**. It concludes **"roughly 75 % of issued loads serve cache-resident data."**
- My own §2.2 measures the cache-served ceiling at **1675.96 GB/s = 6.37× DRAM**. A pool with an 11 % cache-resident byte fraction served at 6.4× DRAM rate produces *exactly* this kind of apparent super-ceiling reading.
- State doc §5e already found sub-SLC re-reads are nearly free (0.010 % of step to replay a 4 KB activation per simdgroup).

So the three facts fit together with no free parameters: the `qkvo` family re-reads a small cache-resident working set many times, the census counts every re-read as a DRAM byte, and the pool consequently appears to run 12 % faster than DRAM allows.

### §5.1 The consequence — and it is a rule, not a footnote

> **The `qkvo` pool must not be used to constrain `alpha`, or to compute a "% of DRAM ceiling", at all.** Its counted bytes are not DRAM bytes. The routed pool, which sits at 99.1 % of the measured ceiling, is the one that identifies `alpha`.

This also puts a caveat on tanjiro's **N-BYTES-EVERYWHERE**: the "85–91 % of measured DRAM ceiling" figures for families whose census includes cache-resident traffic are **overstated**, because the numerator counts bytes that never touched DRAM. The direction is: **those families are further from their true DRAM roofline than the census says, not closer.** I flag this as a caveat and explicitly *not* as a refutation — it does not re-open anything by itself, because tanjiro's independent instruction-side and efficiency-side probes closed those axes on their own evidence. But if anyone proposes re-opening a byte-regime family on the strength of "it is only at 85 % of peak", this is the first thing to check.

---

## §6 Re-pricing the two `alpha`-dependent live numbers (brief item 4)

`alpha` does not move materially — it stays inside its bracket — so by the brief's own conditional ("if alpha moves materially") no re-price is *required*. I give the bracket anyway so nobody has to redo it at 06:00Z.

### §6.1 Tanjiro's byte-axis price — 15.10 MiB/step per 0.4 % of `cs`

| | `alpha` | price | change |
|---|---:|---:|---:|
| bracket low | 0.4227 | **15.61** MiB/step per 0.4 % | +3.35 % (harder) |
| **campaign** | **0.4369** | **15.10** | — |
| bracket high | 0.4409 | **14.96** | −0.92 % (easier) |

Worst case: you need **15.61** MiB/step rather than 15.10 to buy 0.4 %. A 3.4 % tightening of a byte-axis bar. **No family in the census is within 3.4 % of that bar**, so no verdict moves.

### §6.2 Frieren's barrier-drain conversion — 0.799–0.915 % at `k ∈ [alpha, beta]`

The high end is anchored at `beta = 0.5` and is **unchanged**. Only the low end moves:

| | `alpha` | drain range |
|---|---:|---|
| bracket low | 0.4227 | **0.773** – 0.915 % |
| **campaign** | **0.4369** | 0.799 – 0.915 % |
| bracket high | 0.4409 | 0.806 – 0.915 % |

Worst case the low end drops from 0.799 % to **0.773 %** (−3.2 %). Frieren's drain component stays comfortably a **≥1.9 bar** effect at either end. No verdict moves.

### §6.3 Does anything cross a bar? (my §9 draw model, `sigma0 = 0.3016`, gap 1.6359)

Rescaling the live R108-K prices across the full `alpha` bracket — a deliberately *unfair* stress test, since these are **latency-regime** prices carried at `k ≥ 1.0` and are not `alpha`-denominated at all:

| price | headline | `alpha`-bracket band | P(draw) band |
|---|---:|---|---|
| R108-K `k=1.0`, 30 dispatches | 0.5657 % | [0.5474, 0.5709] % | 1.54e-04 → 2.07e-04 |
| R108-K `k=1.0`, 39 dispatches | 0.7354 % | [0.7116, 0.7422] % | 1.09e-03 → 1.52e-03 |
| family E dispatch-only | 1.0690 % | [1.0343, 1.0789] % | 2.31e-02 → 3.24e-02 |
| family E full fusion | 2.4510 % | [2.3715, 2.4737] % | 0.9926 → 0.9973 |

**Nothing crosses a §9.4 band boundary** (0.40 / 0.93 / 1.25 %). The `alpha` uncertainty is an order of magnitude smaller than the `k` uncertainty it sits next to, and two orders smaller than the desk-price risk in my §9.5. **`alpha` is not the thing to worry about tonight.**

---

## §7 What I am handing to whom

**To frieren (#660), due before her 21:00Z Stage-1 gate:**
1. Keep `alpha = 0.4369`. It survives. Do not re-derive.
2. Your barrier-drain low end is 0.773 % rather than 0.799 % in the worst case. Immaterial.
3. Unrelated to `alpha`, and more important: see my R106-J §9.6.2. **At the advisor's own instructed conservative `k = 1.0`, a 30-dispatch merge is worth 0.5657 % (P = 1.9e-04), not the 1.069 % headline. A 39-dispatch pair at `k_residue = 1.4998` is worth 1.1029 % (P = 3.9e-02) — the only entry in the table that reaches my §9.4 "armed" band under a conservative `k`. Prefer a 39-dispatch pair if the ledger offers one.**

**To tanjiro (#663), due before his 18:00Z ledger:**
1. Your N-DEGENERATE is resolved but not the way you framed it: the pools disagree because the **`qkvo` byte census counts cache-resident traffic**, not because `alpha` is free. Your alpha-free bound 0.4454 is correct and I have tightened it to **0.44095** by direct measurement.
2. **Your pool-differential M4 constant 237.4 GB/s reads 10 % low** against a direct sweep on the same host (263.29). If any row of your ledger uses 237.4 as a denominator, it is overstating that family's % of peak by ~11 %.
3. Your byte-axis price 15.10 MiB/step per 0.4 % is good to −3.4 % worst case.
4. Gathers are free on this host at DRAM working sets (100.0 % of sequential). Do not charge a gather penalty in the `byte_delta` column.

**To the advisor:** §1 — Part 1's premise was unexecutable, and I did not spend a receipt discovering that. §5 — the degeneracy has a mechanical cause worth a rule. §2.4 — Rule 55's 266.3 should become 263.29.

---

## §8 Threats to validity

1. **One host, one session.** The M4 ceiling is measured on *this* M4 Pro; the campaign's M5 numbers come from a different machine I cannot touch. Everything here that crosses hosts does so through the paired-instrument ratio, which is the weakest link.
2. **The 610 GB/s M5 constant is taken on faith.** My lower bound on `alpha` is only as good as the claim that 610 came from this instrument geometry (`tanjiro-pr27-interim.md:1044-1105`). If 610 came from a different instrument, §4.1 collapses and only the §4.2 upper bound survives. **The upper bound does not depend on it**, so the "0.4369 survives, and if wrong it is too high" conclusion is robust either way.
3. **`alpha` is a time ratio, not a bandwidth ratio**, and the identity `alpha = BW_M4/BW_M5` holds only for *purely* byte-bound work. Every family has some fixed cost (Rule 55's 3.97 µs intercept). This biases the bracket, and the bias is in the direction of making `alpha` look *smaller* than it is — consistent with 0.4369 sitting high in the bracket.
4. **The 11.0 % cache-served figure is a lower bound**, derived from an inequality, not a measurement of the `qkvo` census. The true fraction could be much larger; R107-E §3's "≈75 % of issued loads serve cache-resident data" suggests it is.
5. **`slc_fit` says `spills` from 64 MiB up**, and the DRAM plateau is measured entirely in that region — so the plateau is genuinely DRAM and not a cache artefact. Good. But the 16 MiB row is classified `mixed` at 118.8 %, so the SLC transition on this host is between 12 and 20 MiB, not at the 24 MiB the probe's default `FERN_SLC_MIB` assumes. I did not chase this; it does not affect any number above.

---

## §9 Reply to advisor

- **Part 1 is complete and cost zero receipts, but not as specified.** The probe cannot run on the official M5 by any route (§1). I substituted the paired-instrument measurement the probe was designed for and got a stronger answer than a bare M5 ceiling would have given: not just a number, but the *mechanism* behind the disagreement (§5).
- **`alpha = 0.4369` survives.** Bracket [0.4227, 0.4409]. Tell frieren and tanjiro to stop worrying about it; the `k` uncertainty next to it is 10× larger.
- **Two corrections I owe the campaign:** Rule 55's 266.3 → **263.29** (1.14 % optimistic), and tanjiro's 237.4 pool-differential constant reads **10 % low**.
- **One new rule I propose:** *a family whose byte census includes cache-resident re-reads may not be assigned a "% of DRAM ceiling", and may not be used to constrain `alpha`.* The `qkvo` pool violates this and is the sole source of N-DEGENERATE.
- I am now on Part 2 (freeze custody). Part 1 finished at ~16:10Z, inside the 16:15Z stopping rule.

---

## §10 Evidence contract

### §10.1 Base reconciliation (Rule 97.0 as amended)

The assignment branch `maple-fern/r108-m-bandwidth-probe-and-freeze-custody` (`4aab2f34`) is a single assignment commit on top of the advisor base `705484b9`. I created my working branch **directly at `4aab2f34`** — so this is **neither a merge nor a rebase**; there was nothing to reconcile. Recorded as instructed.

I carried forward exactly **one** file from my unmerged R106-J work: `research/maple-fern-r106j-integration-tree.md`, at its `d99a117f` revision (3,541 lines vs the 2,766 lines merged into the advisor tip). I verified the carry is safe: `git diff --numstat 234c5542 1eda2174 -- research/maple-fern-r106j-integration-tree.md` is **empty**, i.e. the advisor merged my file verbatim, so my three later commits (§8.7, §8.8+§9, §9.6) apply cleanly as pure additions. Those sections are the freeze decision rule that Part 2 executes against.

### §10.2 Scored surface

```
git diff --numstat 705484b9 HEAD -- Sources Vendor benchmark.json Package.swift senpai
```
→ **empty** (verified; re-verified at every commit, see §10.4).

### §10.3 Artifacts

| path | content |
|---|---|
| `research/artifacts/maple-fern-r108m/m4-bw-probe-default.log` | full 134-line probe transcript, all four arms, Rule 77 geometry on every timed row |
| `research/artifacts/maple-fern-r108m/alpha_resolution.py` | the arithmetic of §4–§6, runnable |
| `research/artifacts/maple-fern-r108m/alpha_resolution.txt` | its output |

Reproduce with:
```
xcrun swiftc -O research/fern_r101_bw_probe.swift -o /tmp/fernbw && /tmp/fernbw
```
6.027 s on this host.

### §10.4 Rule 105.15

Nothing in Part 1 is a correctness claim. No kernel was built, no golden set was run, no `max_abs_diff` is cited. The probe writes one `uint4` per thread per dispatch to defeat dead-code elimination and reads nothing the model uses.

### §10.5 Rule 98.9 (my own rule)

The headline **263.29 GB/s** is the **DRAM-resident** plateau, taken as the median of 6 working sets ≥192 MiB, all classified `spills`. The **1675.96 GB/s** cache-served figure is reported separately and explicitly labelled, and is used only in §5 to explain a super-ceiling artefact — never as a headline. This is exactly the inflation Rule 98.9 exists to prevent, and this probe's two-column `regime`/`slc_fit` output is the instrument I built to make it impossible to smuggle.
