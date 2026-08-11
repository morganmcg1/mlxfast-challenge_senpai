# R127-A — Provenance audit of `research/maple_endgame_handoff_manifest.md`

**Audit base:** `67396bb6` — the advisor branch head at 12:40Z, the first revision containing §6.6
(added 12:10Z, completed 12:35Z). The manifest at that commit is 1087 lines; every `L####` below is a
line in that revision.

**Instruments:** `git show`, `grep`, PR bodies/comments/results, trusted-harness source, arithmetic.
No GPU, no build, no benchmark, no W&B run. Nothing under `Sources/`, `Vendor/`, or `benchmark.json`
is modified — harness source is *read* as a primary source, not edited.

**Out of scope by assignment:** `cedar-*` branches and PRs #720–#723, #727, #728. No finding below
reads or cites them.

**Closed by the advisor before this audit, cited but not re-litigated:** σ(official draw) = 0.49 %
and its "never measured by replication" absence claim (retracted at L729-736); the gap-to-bar cell
(+0.378 % → +0.4950 %); the per-draw success table; and delta 1 itself, whose §4c post-mortem I do
not improve on.

---

## 1. Verdict

> **118 quantities audited, 13 findings. The largest is that §6.6 — the correction added this morning
> to fix the campaign's pricing — is itself mispriced in the flattering direction, and the constant it
> condemns as `UNSOURCED` is correct with ~40 in-repo measurements behind it.**

**§8 is an addendum** written after the advisor's 11:53Z comment and worked against branch head
`6778867d` (12:59Z): it re-targets every span below to head line numbers, audits **§4b cell by cell**
and **σ** as instructed, adds F14 and F15, corrects an error of my own in F10, and records one claim I
could not verify. Running totals with the addendum: **142 quantities, 15 findings**.

Coverage, so the denominator is auditable:

| section | quantities audited |
|---|---|
| §1 scoring model + operating point | 12 |
| §2 instrument table | 10 |
| §3 budget / build receipts | 4 |
| §4 ledger rows (1–4 + o_proj) | 5 |
| §4a geometry + banner | 6 |
| §4b arithmetic table | 3 |
| §4c derivation chain (steps 1–5) | 15 |
| §5 banked laws | 25 |
| §6.1–6.2 arrival rates | 8 |
| §6.4 service times and deadlines | 13 |
| §6.5 σ and P-table | 12 |
| **§6.6 currency table + three consequences + requirement table** | **20** |
| §7 open threads | 5 |
| **total** | **118** |

Two findings are decision-grade: **F1** (§6.6's local rows are 1.44–1.56× too generous, which lowers
the local engineering bar from 44/85 µs/step to 31/59) and **F2** (L918's absence claim is refuted by
in-repo data that existed when it was written — the same failure mode as the σ absence claim retracted
190 lines earlier, on the same morning).

---

## 2. The currency census

### 2.1 The structural fact that settles the question

The score divides by the **reported `decode_seconds_per_token`**, and that field **includes the seed
forward**. Primary source, trusted harness,
`Sources/MLXFastTrustedHarness/LagunaRuntimeLocalIterate.swift:767-769`, verbatim:

> `// Use the same decode protocol as the official benchmark and start`
> `// the parent timer before decode_begin so seed prefill/setup is`
> `// charged to decode_seconds_per_token.`

`:776` emits `decode measured start tokens=\(decodeSteps) includes_seed_prefill=true`. `:611` prints
`decode seed prefill complete seconds=… (charged to decode)`. `:839`
`totalDecodeSeconds += secondsSince(decodePhaseStart)`; `:864`
`secondsPerToken: totalDecodeSeconds / Double(totalDecodeSteps)`; `:713`
`let totalDecodeSteps = decodeSteps * timingRepeats`. `Sources/MLXFastCore/Score.swift:4-7` takes the
ratio of exactly that field.

So, with `S` the 512-token seed forward and `T` the steady step:

```
D  =  S / decodeSteps  +  T          and     %score  =  0.75 · Δ / D
```

`Sources/MLXFastCore/Constants.swift:106-109` fixes `benchmarkDecodeSteps = 128`; `:113`
`localIterateBenchmarkDecodeSteps = benchmarkDecodeSteps`; `:117`
`localSubmitBenchmarkDecodeSteps = 1023`. **`--local-iterate` runs the scored 128-step configuration;
`--local-submit` does not.**

Because `dD/dT = 1`, a Δ µs/step steady-step saving moves `D` by exactly Δ. §6.6's *rule* —
`0.75 / step` — is right. What it gets wrong is which measured quantity is `step`.

### 2.2 The local `D` is measured, repeatedly, and it is ~12.8–13.0 ms

`research/maple-alphonse-r114-gatesp.md:432-434` states the instrument verbatim: "36 runs of
`./benchmark.sh --local-iterate` in order `CFFC` × 9, SPLIT=0 (uninstrumented) … M4 Pro / 20 GPU
cores / 48 GiB". Its arm table, `:444-446`:

> `| C — shipped two-dispatch path | 18 | 0.0129820197 | 46.5 µs (0.36 %) |`
> `| F — fused grid-append        | 18 | 0.0129052344 | 43.2 µs (0.34 %) |`

That is **12 982 / 12 905 µs of `decode_seconds_per_token`** from the scored 128-step configuration on
this host class, n=36. My own `research/maple-edward-r110/REPORT.md:294-297` reports 12 775 / 12 901 /
12 972 / 12 850 µs across four arms. And `0.75 / 12 798 = 0.00586` ✓.

Independent corroboration from a **trusted, non-editable** document, `senpai/program.md:216-221`:

> "2. A student host under `--local-iterate` has `sigma = 33.6%`. …
>  3. `--local-submit` runs 1023 decode steps, driving `sigma` to about 5.9%."

σ is the seed share of `D`, so `D_local = T/(1 − 0.336) = T/0.664`. From the two step-only figures
§6.6 itself quotes, that band is **12 369 – 13 376 µs**, and 12 798 sits mid-band. Closing the loop
from my own R110 prefill number: 0.0011079 s/tok × 512 = **567 ms seed**, so
`T = 12 900 − 567 000/128 = 8 470 µs`, `D₁₀₂₃ = 567 000/1023 + 8 470 = 9 024 µs`, σ₁₀₂₃ = **6.1 %**
against program.md's "about 5.9 %" ✓. The whole picture is consistent on one host.

### 2.3 What 8213 and 8882 actually are

- **8213** is a **step-only** time. `research/maple_r89_a_report.md:729`: "Independent replication of
  #473's instrument cost: my `nat` median is 8.213"; `:695` prices against "8.213 ms **nat step**".
  The harness tracks this separately as `totalStepOnlySeconds` (`:631`) — not the scored field.
- **8882** is `--local-submit`, i.e. **`D` at 1023 steps**, where the seed is amortised 8× harder.

Neither is `D₁₂₈`. Using 8213 overstates a local price by `12 798/8 213 = 1.56×`; using 8882
overstates it by `12 798/8 882 = 1.44×`.

The sharpest form of this: **§6.6(b) (L928-932) names the 1023-vs-128 decode-step trap as the
mechanism by which a wrong step length entered circulation — and then §6.6's own table adopts the
1023-step number and rejects the 128-step one.**

### 2.4 Census — one row per banked or quoted delta

Correct rule throughout: `%score = 0.75 · Δ / D_host`, with `D_local = 12 798 µs`,
`D_ranked = 4 910.9 µs`.

| item | µs/step as measured | harness that produced it | that harness's decode step (`D`) | correct % score | % score as banked | discrepancy factor |
|---|---|---|---|---|---|---|
| **requirement +0.50 %, local units** | — | §6.5 → §6.6 L946 | 12 798 | **85 µs/step** | §6.6 says **59** | **1.44× too lenient** |
| **requirement +0.26 %, local units** | — | §6.6 L945 | 12 798 | **44 µs/step** | §6.6 says **31** | **1.44× too lenient** |
| **§7 item 2 — non-busy decode gap** | 350 µs/step (8919 wall − 8567 busy) | local wall-vs-busy census | 12 798 | **+2.05 %** | §7 L977 "~2 %" ✓; §6.6 L961-964 "corrects" it to **2.94 %** | §6.6 **1.44× inflated**; the item did *not* get bigger under audit |
| **o_proj pool yield (#718)** | −35 µs/step | alphonse #718, quoted there as "0.43 % of the decode step" | 12 798 | **+0.205 %** | §5 L456-457 still says **−82 µs/step** ⇒ 0.48 % | **2.34× inflated** in §5; §4 L232 already says −35 |
| **#733 FUSED grid-append** | +55.2 µs/step | frieren #733, bench control | 12 798 | **−0.323 %** | **−0.323 %** | **1.00 — safe.** §6.6 L924-925's "FUSED is −0.504 %, not −0.323 %" is the 1.56× error |
| **#731 routed QMV TG=256, wall** | +23.12 µs/step | my #731 `--local-iterate` ladder, 36 runs | 12 798 | **−0.135 %** | §4c L405 **−0.14 %** ✓ / §4 L230 + §5 L470 **−0.282 %** ✗ | **2.09× inflated** in §4 and §5 |
| **§4c requirement for the +0.38 % headline** | — | §4c L399 vs L414 | 12 798 | **64.8 µs/step** | L399 says 64.8, **L414 says 41.4** | **1.57×** — both currencies inside one paragraph |
| **frieren `OPROJ_SIMDGROUPS=4` screen** | −40.9 µs/step | frieren screen, bench host | 12 798 | **+0.240 %** | not priced; declined | disposition correct — see §2.5 |
| **delta 1 shared SwiGLU TG 64→256 (#729), isolated leg** | +4.73 ± 0.52 µs/step | alphonse #729, SPLIT=1 isolated kernel | 12 798 | **−0.028 %** | −0.03 % (§4c L403-404) | **1.00 — safe** |
| **delta-1 headline counterfactual** | +66.88 µs/step (counterfactual, wrong sign) | #714 isolated kernel | 12 798 | 0.392 % in magnitude | +0.38 % | **1.00 — the constant was right.** The failure was the *input*, not the currency |
| **TG-width debit law** | +0.79 µs/step per extra simdgroup/TG | #714 + #729 isolated | 12 798 | −0.0046 % | not priced | — |
| **delta 2, routed down-GEMM BN 64→32 (#732)** | +0.17 % **prefill** (fractional, not µs) | #732 IR census + prefill | prefill axis **and** seed forward | **+0.062 %** (0.17 × 0.362) | **+0.04 %** (0.17 × 0.25) | **0.65× — deflated** |
| **requirement, ranked units** | — | §6.6 L945-946 | 4 910.9 | 17.0 / 32.7 | 17 / 32 | **1.00 ✓ correct** |

### 2.5 Census verdict

- **Safe:** every price computed with 0.00586 %/(µs/step) against a *local absolute* µs/step delta —
  #733 FUSED, #729 delta 1, §4c's −0.14 % for #731, §7 item 2's "~2 %", and the long-standing
  "44 / 84" requirement column. These were correct as banked.
- **Inflated:** §5's o_proj (2.34×), §4/§5's #731 row (2.09×), and — new this morning — **every local
  row §6.6 introduced** (1.44–1.56×), including the requirement table a handover reader will use as
  the engineering target.
- **Deflated:** delta 2's prefill price (0.65×), charged the 0.25 prefill weight only instead of the
  manifest's own combined 0.362 seed elasticity.
- **Ranked column: correct.** `0.75/4910.9 = 0.01527 %/µs`, and 17 / 32.7 µs/step both check out.
- **No disposition changes.** Every inflated item is a loss being kept out, and inflating a loss does
  not flip it. The ledger's one *decline* — frieren's `OPROJ_SIMDGROUPS=4` at a −40.9 µs/step screen —
  prices to **+0.240 %**, just *under* the +0.26 % target rather than over it, and it was declined
  because the screen was the instrument (§5b bimodal control; confirmed null at n=12,
  −5.4 [−12.6, +1.6]), not on price. The decline survives the reprice.
- **One derived claim does not survive.** §6.6 L957-960 concludes "The 31–59 µs/step target band and
  the 40–60 µs/step phantom band are the same band, which is the deepest reason this campaign could
  not have succeeded by local screening alone." Under corrected rates the target band is
  **44–85 µs/step**: the bands overlap at the bottom, but the phantom band **tops out below the
  +0.50 % target**. The coincidence is an artifact of the 1.44× error; the underlying point survives
  on §5b's own evidence and does not need it.

---

## 3. Findings, most expensive first

| # | manifest location | manifest says | primary source says (verbatim + location) | check failed | corrected value | price impact (% score) |
|---|---|---|---|---|---|---|
| **F1** | §6.6 currency table L916-918; consequences L922-926, L961-965; requirement table L941-949 | "`--local-submit` on our M4 \| 8882 µs \| 0.00845 % of score"; "frieren's bench control host \| 8213 µs \| 0.00913 %"; requirement "+0.50 % … 59 \| 55" | `LagunaRuntimeLocalIterate.swift:767-769` "start the parent timer before decode_begin so seed prefill/setup is **charged to `decode_seconds_per_token`**"; `:776` `includes_seed_prefill=true`; `:864` `secondsPerToken: totalDecodeSeconds / Double(totalDecodeSteps)`; `Constants.swift:113` (`--local-iterate` = 128) vs `:117` (`--local-submit` = 1023); `senpai/program.md:216-221` "A student host under `--local-iterate` has `sigma = 33.6%` … `--local-submit` … about 5.9%" | 1 — units read off the wrong column: a **step-only** time and a **1023-step** `D` substituted for the scored 128-step `D` | Local denominator is **`D₁₂₈` ≈ 12 798 µs**, not 8213/8882; local rate **0.00586 %/(µs/step)**; requirement local column **44 / 85**, not 31 / 59. | **Decision-grade, and flattering.** Lowers the stated local bar 1.44× — the exact error class §6.6 was written to catch — and mis-corrects three banked prices (census §2.4). |
| **F2** | §6.6 L918, L922 | "**UNSOURCED.** No harness in the fleet measures a 12.8 ms decode step. Do not reuse."; "(a) The 0.00586 %/µs constant that priced most of this campaign **cannot be sourced**." | `research/maple-alphonse-r114-gatesp.md:432-434` (instrument: "36 runs of `./benchmark.sh --local-iterate` … M4 Pro / 20 GPU cores / 48 GiB") with `:444-446` (arm means `0.0129820197`, `0.0129052344` decode s/token); `research/maple-edward-r110/REPORT.md:294-297` (12 775–12 972); `research/frieren_r116_router_top8_number.md:150-154` "alphonse's merged #700 turned −76.8 µs/step into **+0.45 % score**, i.e. **0.00586 % score per µs/step**"; `research/CURRENT_RESEARCH_STATE.md:643` repeats it | 5′ — absence claim asserted without searching for the thing said not to exist | `--local-iterate` **is** the harness that measures it; the value appears ~40 times in-repo. The constant is sourced twice over. | **Systemic.** L918 is the authority for every reprice in §6.6, and it is false. Same failure mode the document retracted at L729-736 for the σ-replication absence claim, repeated 190 lines later. |
| **F3** | §5 L456-457 | "measured 256.7 GB/s peak, h48 92.8 %, and both refuse to yield; o_proj was at 83.4–90.7 % when it gave up **−82 µs/step**." | PR #718 result: "anything budgeted against -80 us/token should be re-budgeted to about **-35** (0.43% of the decode step)"; the manifest's own §4 L232: "Any o_proj term in a composition estimate must use **−35 µs/step**, not the imported −80." | 5 — superseded input not re-derived | **−35 µs/step ⇒ +0.205 %**, not −82 ⇒ 0.48 %. | **0.275 pp**, and §5 contradicts §4 inside one file. Four renderings circulate: −82, −80, −79.4, −35. |
| **F4** | §4 ledger row 4 L230; §5 L470 | row 4: "REFUTED. **−0.282 % of score**"; §5: "sign p=0.0312, **−0.282 % score** ⇒ regression." | PR #731 `senpai-result:v1`, my own submitted result: "TG=256 … median **+23.12**, CI95 [+15.77, +38.31] … sign p=0.0312, **-0.282% decode**, phi 0.997890 => REGRESSION." | 1 — units read off the wrong column | 0.282 % is the **fractional decode slowdown** (23.12 / 8199.68 = 0.28196 % ✓), not a score delta. Score price **−0.135 %**. | **0.147 pp**, a **2.09×** overstatement — and §4c L405 prices the same number correctly at −0.14 %, so §4/§5 contradict §4c. |
| **F5** | §6.6 L957-960 | "The 31–59 µs/step target band and the 40–60 µs/step phantom band are **the same band**, which is the deepest reason this campaign could not have succeeded by local screening alone." | Corrected target band from F1: **44–85 µs/step**; phantom band from §5b: 33–64 µs/step. | 2 — conclusion drawn from a value that moved | The bands **overlap at the bottom but are not the same band**; the phantom band cannot reach the +0.50 % target. | **Narrative-grade.** It is the document's closing explanation of why the campaign failed and should not rest on an arithmetic artifact. |
| **F6** | §4a banner L247-250; §4c L405; §4c L419-421 | "as much as **−0.14 % on edward's routed-wall measurement (#731)**"; "edward's routed-wall **replication** (#731)"; "#731 reported a `+23.12 µs/step` routed **wall** regression **from the same flip**" | PR #731, my own scope check: "alphonse #729 (`DARKBLOOM_SHARED_QMV_TG`): **NO COLLISION — different env var, different kernel (shared vs routed expert), disjoint dispatch sites.**" The advisor's own close: "Shared expert = one contiguous stream ⇒ it widens; routed expert slots are interleaved mod-8 (`LagunaRuntimeModel.swift:8078-8079`)." | 4 — a delta on kernel A priced onto kernel B | #731 measured the **routed** expert QMV; delta 1 is the **shared** expert SwiGLU QMV. Not a replication, not "the same flip"; −0.14 % is **not** an upper bound on delta 1. | **0.14 pp misattributed.** Self-refuting: the banked law at L446-451 exists *only because* the two kernels behave differently. |
| **F7** | §4c L414 vs L399 | L399: "inverting it, `0.38 % ÷ 0.00586 = 64.8 µs/step`"; L414: "**excludes the −41.4 µs/step that my +0.38 % required, at 3.56σ**" | The two are one requirement in two currencies: `0.38/0.00586 = 64.85` (local `D`); `0.38/0.00918 = 41.4` (bench step-only `T`, `= 0.75/8170`). | 1 — units; the §6.6 disease, present in §4c before §6.6 was written | The requirement is **64.8 local µs/step**. The refutation gets *stronger*: whatever SE produced 3.56σ for 41.4 gives **≈5.6σ** for 64.8. | **0 pp to the conclusion** — delta 1 stays refuted — but it is the cleanest in-document proof that the currency confusion predates §6.6. |
| **F8** | §4b table cell; §4a banner L245-248 | "would move that tree **≈ −0.03 % of score or worse**" | PR #729: "this wall cannot resolve my +4.73 (0.058 % of an 8.21 ms step; 2.41× below its SEM, 4.7× below its CI half-width)". Wall arm null = [−19.33, +17.86] µs/step. | 4 — isolated-kernel delta quoted as a wall/score delta | §4c L403-405 hedges correctly ("on the isolated kernel leg"); the §4b cell and §4a banner drop the hedge. Honest cell: "isolated kernel leg **+4.73 ± 0.52 µs/step**; wall effect indistinguishable from zero, \|Δscore\| ≤ **0.11 %**." | **0.11 pp of false precision** on the DO-NOT-LAND banner — the row an owner acts on. |
| **F9** | §4 row 2 L228; §5 L492 | "the fixed-loader lever is ≈ +0.17 % prefill ≈ **+0.04 % score**" | The manifest's own §1 L146-147: "elasticities decode 0.638, **seed 0.362**". That pair decodes exactly as `0.75(1−σ) = 0.6376` and `0.75σ + 0.25 = 0.3624` at σ = 14.98 % — the seed elasticity **already includes** the seed forward inside decode, not just the 0.25 prefill axis. | 5 — the 0.25 axis weight used where the document's own 0.362 belongs | `0.17 × 0.362 =` **+0.062 %**, not +0.04 %. | **0.022 pp, deflated (0.65×).** Disposition unchanged — still below the cost of a draw — but it is the only *conservative* mis-pricing found, and §1 already contains the right multiplier. |
| **F10** | §6.5 L798-806, and the σ inputs to §6.6 L945-946 | P-table "1 → 15.6 %"; "(Ranges span σ = 0.1860–0.2276 %.)" | `research/nezuko-result.md:203-205`: "My pooled within-identical-content figures come from **7 byte-identical families and 27 dof**". | 5 — inputs, not conclusions. The **sourcing** is correct (advisor already closed that); the **precision** is not | At 27 dof the relative SE of σ̂ is `1/√54 = 13.6 %`, so a χ² 95 % interval spans roughly ±27 % on σ. At gap 0.4950 % the point 15.6 % carries a band of about **10–23 %**. Three significant figures are unsupported. | **Decision-grade for the idle-slot go/no-go**, though the sign of that decision does not change. |
| **F11** | §6.6 L922-926 | "(a) … **it is the constant that manufactured the delta-1 headline** (`66.88 × 0.00586 = 0.392 %`)" | §4c L393-397, the advisor's own post-mortem: the two errors were (i) "read the `us/step` column as `tok/s`" ⇒ "**sign inversion**" and (ii) "priced the delta from the `+66.88 us/step` **counterfactual**, not the `+4.67` measurement" ⇒ "**14× overstatement**". Neither is a currency error. | 2 — conclusion attached to the wrong cause | The constant converted a wrong input faithfully; `66.88 × 0.00586 = 0.392 %` is the *correct* price of a +66.88 µs/step local delta. | **0 pp**, but it redirects the handover's root-cause lesson from "check the sign and the column" to "distrust the exchange rate" — which is how F1 came to be written. |
| **F12** | §1 L146-147 vs §6.6 L915 | "Operating point: S = 97.863 ms seed forward, T = 4.3224 ms steady step" ⇒ `D = S/128 + T = 5087 µs`; §6.6: "ranked host … **4910.9 µs** … `mean_D` of replicate group `dc437b0e`, n=5" | Both are ranked-host figures. `research/RESEARCH_IDEAS_2026-08-06_09:00.md:3` gives a third: "decode 4908.372". | 5 — two inputs for one quantity, neither reconciled | The three differ by **3.6 %**. 4910.9, a measured `mean_D`, is the better choice, and the ranked rate should be quoted from it. | **0.5 pp on a 15 µs/step claim.** Small, but it is the ranked column, and the ranked column decides submission. |
| **F13** | §1 L146 | "σ = 14.98 %" | Same line's own inputs: `S/(S + 128T) = 97 863/(97 863 + 553 267) =` **15.03 %**. | 5 — arithmetic on stated inputs | 15.03 %. The elasticity pair 0.638 / 0.362 is computed from 14.98 % and holds to 3 digits either way. | **Negligible (0.05 pp on σ).** Recorded only because F9's elasticity decode depends on reading this line exactly. |

---

## 4. Clean list — checked and correct

Per the assignment, this list is not skipped. 105 of the 118 audited quantities cleared every check.
The ones worth naming, because a reader might otherwise assume the audit above impugned them:

**Arithmetic and internal consistency**

1. **§1's elasticity pair `decode 0.638 / seed 0.362` is exactly right**, and is the single most
   useful number in the manifest. It decodes as `0.75(1 − σ) = 0.6376` and `0.75σ + 0.25 = 0.3624`
   at σ = 14.98 %, which is precisely the correct treatment: the seed forward sits *inside* the
   scored decode denominator, so a fractional seed win earns the 0.25 prefill weight **plus** its
   0.75·σ share of decode. F9 is a finding only because §4/§5 used 0.25 where §1 already published
   0.362.
2. **All four §6.6 rates are internally consistent with `0.75 / step`.** 0.75/4910.9 = 0.015272;
   0.75/8882 = 0.008444; 0.75/8213 = 0.009132; 0.75/12798 = 0.005860. The table's arithmetic is
   flawless; only the *labels* on rows 2–4 are wrong (F1). This matters for the fix: the table does
   not need recomputing, it needs re-labelling.
3. **The ranked column is correct throughout.** 0.01527 %/(µs/step) and the ranked requirement
   `17 / 32 µs/step` at +0.26 % / +0.50 % both reproduce (0.26/0.015272 = 17.0; 0.50/0.015272 = 32.7).
   Every conclusion that rests only on the ranked column stands unmodified.
4. **§6.6 item (c) is correct and is the rule that should have caught F1**: "A µs/step delta does not
   cross hosts at all. Only a *relative* claim crosses." Also correct: the #473 ~42 % kernel-to-wall
   evaporation figure it cites.
5. **§6.6 item (b)'s mechanism is real.** `Constants.swift:109` `benchmarkDecodeSteps = 128` versus
   `:117` `localSubmitBenchmarkDecodeSteps = 1023` is exactly the trap described, and it is the
   mechanism by which 8882 entered §6.6 as if it were the scored denominator. The paragraph names
   its own error one row above committing it.
6. **§1 L148-152's warning is correct**: "the local rate is a *different currency* … do not compare
   a local µs/step to a ranked one." It is contradicted 770 lines later by L918, not by itself.
7. **#729's numbers are clean.** TG=64 `289.88 ± 0.48` vs TG=256 `294.62 ± 0.46` ⇒ `+4.73 ± 0.52`,
   CI95 [+2.50, +6.96] — the delta, the SE and the interval are mutually consistent, and
   `4.73 × 0.00586 = 0.0277 %` reproduces the quoted −0.03 %.
8. **The two delta-1 back-calculations in §4c L399 both reproduce**: `66.88 × 0.00586 = 0.3919` and
   `0.38 / 0.00586 = 64.85`. F7 is about which currency 64.85 lives in, not about the division.
9. **#731's statistics are quoted correctly everywhere they appear**: TG=128 median −3.77, CI95
   [−11.26, +23.40], sign p = 0.2188, A-vs-A max |null| 67.13; TG=256 median +23.12, CI95
   [+15.77, +38.31], sign p = 0.0312; 0 divergences in 36/36 runs × 512 tokens; decode-neutrality
   ratio 0.997987 / φ 0.997890, `max_abs_diff` 0. Only the *conversion* to score is wrong (F4).
10. **§4c L403-405's hedged sentence is the correct one in the document**: "−0.03 % … on the isolated
    kernel leg … so the honest statement is *a loss of between three and fourteen hundredths of a
    percent*." F6 and F8 are about §4a/§4b dropping this hedge, not about §4c.
11. **§4 L232's o_proj instruction is right** — "must use **−35 µs/step**, not the imported −80" —
    which is what makes §5 L456-457's surviving −82 a self-contradiction rather than an open question
    (F3).
12. **§4c steps 1–3 are a complete and honest post-mortem.** The two-error decomposition (column
    misread ⇒ sign inversion; counterfactual priced instead of measurement ⇒ 14× overstatement) is
    correct, checkable, and was verified against #714 and #729. Per the advisor's instruction this
    was not re-litigated; it is listed here because F11 concerns only the *attribution* sentence
    appended to it in §6.6, not the post-mortem itself.

**Mechanisms and physical claims**

13. **`staticThreadgroupMemoryLength = 0` ⇒ width is a pure occupancy debit at ≈0.79 µs/step per
    extra simdgroup/TG.** Consistent across #714, #729 and #730, and it prices to −0.0046 % of score
    per simdgroup — correctly characterised in §6.6's "for scale" paragraph as the biggest per-knob
    effect the campaign measured, with the wrong sign.
14. **L154-155's `_nax` reachability claim is correct** (`research/CURRENT_RESEARCH_STATE.md:823`,
    `:1321`): the ranked M5 selects `_nax` prefill kernels and our M4 Pro (Apple GPU gen 16) does not,
    so M4 prefill evidence is not evidence for an `_nax` change.
15. **§7 item 1's ≈27.88 ms prefill attention figure is sourced**
    (`research/maple-tanjiro-pr91-prefill-budget-census.md:648`, `:657-658`).
16. **§7 item 5's "never measured" is accurate**
    (`research/nezuko-decode-attention-occupancy.md:370-379`, "Receipts consumed: 0 of 2"), as is the
    "1 of 4 simdgroups active" occupancy claim (`RESEARCH_ARCHIVE_through-round-91.md:6425`).
17. **§7 item 3 is now correctly withdrawn** at L979-989. A previous revision of this manifest priced
    it as live; the current text withdraws it. Noted here so the advisor knows the earlier defect was
    already fixed and needs no edit.
18. **§5b's bimodal-control finding is sound** and is doing the load-bearing work in §6.6's closing
    paragraph. F5 removes an arithmetic coincidence from that paragraph without touching §5b.

**Sourcing**

19. **L729-736's retraction of the σ-replication absence claim is correct and complete.** The missed
    source was `research/advisor-r103-submission-tree-provenance-and-replicate-noise.md:110-168` plus
    `research/artifacts/advisor-r103/replicate-sigma.json`. Closed by the advisor; not re-audited.
    It is listed here because F2 is the *same failure mode* recurring 190 lines later, and the
    manifest's own retraction is the best available argument for fixing F2.
20. **§6.5's σ(official draw) = 0.489 % is sourced three ways** (`research/nezuko-result.md:203-205`,
    `research/nezuko-normalised-leaderboard.md:690`, `senpai/program.md:461`). Closed by the advisor.
    F10 concerns only the *precision* attached to the derived P-table, not the sourcing.
21. **The §9 ledger rows reconcile with their cited PRs** (#714, #718, #719, #729, #730, #731, #732,
    #733) on disposition, PR number and W&B run ID. No ledger row cites a PR that says something
    different about *whether* it landed.
22. **§6.6's "Rule for reuse" is correct as far as it goes** — "never write a µs/step number without
    naming the host it was measured on" — and needs only the addition that F1 exposes: name the
    *harness and decode-step count* too, since one host has two step lengths and two denominators.

---

## 5. Unresolvable from this branch — `UNSOURCED` in the strict sense

Six items could not be closed with a primary source reachable from this checkout. Each is flagged as
open rather than asserted in either direction; F2 exists precisely because the manifest asserted an
absence in this position instead.

1. **What exact quantity 8882 µs is.** #730's artifact is not reachable from this branch, so I can
   confirm from `Constants.swift:117` that `--local-submit` runs 1023 decode steps (which makes 8882
   a plausible `D₁₀₂₃` and is what the census assumes), but I cannot read nezuko's field name.
   *Coincidence worth flagging, not asserting*:
   `research/maple-tanjiro-pr73-decode-kernel-census.md:174-175` reports a `gpu_busy_union` of
   **8.882 ms** on the local M4. If nezuko's 8882 is instead a GPU-busy union, it is not a `D` at all
   and F1 gets larger, not smaller. Either reading leaves 8882 the wrong denominator for a 128-step
   score.
2. **The third significant digit of 12 798 µs.** The *quantity* is sourced ~40 times
   (§2.2); the specific run that produced the digits `798` is not named in any file I could find.
   The measured band is 12 775–12 982 µs, so every rate in this audit carries ±0.8 %. That is far
   below the 1.44×/1.56× errors under discussion and changes no conclusion.
3. **Whether "frieren's bench control host" is a distinct machine.** If it is our M4 Pro, then 8213
   is that host's step-only `T`, its `D` is 12 798, and the third and fourth rows of §6.6's table are
   the *same host in two currencies* — which is the tidiest reading and the one §2 assumes. If it is
   genuinely a different machine, the row is still mis-labelled (step-only, not `D`) but its `D` is
   unknown. I could not establish which from this branch.
4. **The standard error behind "3.56σ" in §4c L414.** The exclusion is stated but the SE is not, and
   the wall arm's reported interval [−19.33, +17.86] does not reproduce 3.56σ for −41.4 under any
   obvious convention. F7's "≈5.6σ" is therefore a *ratio-scaled* restatement (64.8/41.4 × 3.56),
   correct only if the SE is unchanged. The direction — the exclusion strengthens — is robust; the
   digits are not.
5. **Which axis delta 2's "+0.17 % prefill" was measured on.** F9 prices it at ×0.362 on the reading
   that it is a fractional saving on the seed/prefill *forward*, which is how §5 L490-494 describes
   it (a re-read of the 97.9 ms window). If it were instead a saving on the scored prefill axis only,
   ×0.25 applies (+0.043 %, i.e. the banked number is right); if only on the seed's share of decode,
   ×0.112 applies (+0.019 %). The banked +0.04 % is the *most conservative* of the three, so nothing
   downstream breaks — but the manifest should say which axis it means.
6. **Provenance of §1's `S = 97.863 ms` / `T = 4.3224 ms`.** Both are ranked-host figures and neither
   cites a run. They imply `D = 5087 µs`, 3.6 % above the cited `mean_D` of 4910.9 and 3.6 % above the
   third figure 4908.372 in `research/RESEARCH_IDEAS_2026-08-06_09:00.md:3` (F12). One of the three is
   the ranked denominator and the manifest does not say which.

---

## 6. Recommended manifest edits, with exact replacement text

Ordered by price. Each is a drop-in replacement for the quoted span in the manifest at `67396bb6`.

### 6.1 §6.6 currency table (L913-918) — the load-bearing fix

Replace the four table rows and add one paragraph above them:

> There are not four currencies. There are **two hosts** × **two quantities**, and only one of the
> four combinations is the scored denominator. Score divides by
> `decode_seconds_per_token`, and `LagunaRuntimeLocalIterate.swift:767-769` charges the 512-token
> seed forward into it (`includes_seed_prefill=true`, `:776`), so the denominator is
> `D = S/decodeSteps + T`, **not** the step-only time `T`. `Constants.swift:113` fixes the scored
> config at 128 steps; `:117` runs `--local-submit` at 1023, which shrinks the seed's share ~8× and
> produces a *different* `D` on the *same* host. A µs/step delta in `T` moves `D` one-for-one, so the
> only correct rate is `0.75 / D` at 128 steps.
>
> | currency | decode step | 1 µs/step is | provenance |
> |---|---|---|---|
> | **ranked host `D₁₂₈`** (what the receipt scores) | **4910.9 µs** | **0.01527 % of score** | measured: `mean_D` of replicate group `dc437b0e`, n=5, r103 artifact |
> | **our M4 `D₁₂₈`** — the scored local denominator | **≈12 798 µs** | **0.00586 % of score** | measured by `./benchmark.sh --local-iterate`, the 128-step harness: `research/maple-alphonse-r114-gatesp.md:432-434,:444-446` (36 runs, arm means 0.0129820 / 0.0129052 s/tok); `research/maple-edward-r110/REPORT.md:294-297` (12 775–12 972 µs) |
> | ~~our M4 `--local-submit`~~ **`D₁₀₂₃`, not a scored denominator** | 8882 µs | — | measured by maple-nezuko, #730. 1023 steps (`Constants.swift:117`) ⇒ the seed is amortised ~8× thinner than the scored config. Do not price against it. |
> | ~~frieren's bench control host~~ **step-only `T`, not a `D`** | 8213 µs | — | measured, #733. `LagunaRuntimeLocalIterate.swift:631` reports `totalStepOnlySeconds` as a *separate* field from the scored `secondsPerToken` (`:864`). Add `S/128` before pricing. |
>
> Cross-check, from the trusted brief: `senpai/program.md:216-221` states `--local-iterate` carries
> `sigma = 33.6 %` of prefill share against `--local-submit`'s "about 5.9 %". With
> `T ≈ 8470 µs` that puts `D₁₂₈` at 12 369–13 376 µs (12 798 sits mid-band) and predicts
> `D₁₀₂₃ ≈ 9024 µs` at σ = 6.1 % — closing on nezuko's 8882 and program.md's 5.9 %.

### 6.2 §6.6 consequence (a), L920-926

Replace the whole paragraph with:

> **(a) The 0.00586 %/µs constant is correct, and the reason it looked unsourceable is the same trap
> as (b).** It implies a 12.8 ms decode step, which is exactly what the *scored* 128-step harness
> measures on our M4; the 8.2–8.9 ms figures are a step-only time and a 1023-step denominator. The
> constant did **not** manufacture the delta-1 headline: §4c already establishes that the headline
> came from a column misread (sign) and from pricing a `+66.88` counterfactual instead of the `+4.67`
> measurement (14×). `66.88 × 0.00586 = 0.392 %` is the *correct* price of a +66.88 µs/step local
> delta; the input was wrong, not the exchange rate. Frieren's #733 prices therefore stand as banked:
> FUSED is **−0.323 %**, not −0.504 %.

### 6.3 §6.6 requirement table (L941-949)

> | target | % of score | ranked µs/step (`D` = 4910.9) | local µs/step (`D₁₂₈` ≈ 12 798) |
> |---|---|---|---|
> | +0.26 % (≈10–15 % chance at the bar) | 0.26 | **17** | **44** |
> | +0.50 % (≈50 % chance at the bar) | 0.50 | **32** | **85** |
>
> The old table's "44 / 84" column was right, and the 31 / 59 and 28 / 55 columns that replaced it
> were the ones set ~40 % too low — the flattering direction. There is no separate bench-host column:
> convert a step-only `T` delta into the measuring host's `D₁₂₈` first, then divide.

### 6.4 §6.6 closing (L955-960)

Keep the sentence up to "was the instrument (§5b)", then replace the last clause with:

> The +0.50 % target needs **85 local µs/step**; the phantom band tops out at ~64. Every candidate
> that looked big enough to matter was, at its own screen's face value, *still not big enough* — and
> then turned out to be the instrument as well. That is the deepest reason this campaign could not
> have succeeded by local screening alone.

### 6.5 §6.6 §7-item-2 reprice (L961-965)

> …so its ~350 µs of non-busy time is worth `0.75 × 350/12798 =` **2.05 %** of score locally, not the
> 2.94 % a `D₁₀₂₃` denominator would suggest. It remains the largest single decode opportunity in the
> document, still local, still subject to the ~42 % end-to-end evaporation of #473, still unattacked.

### 6.6 §6.6 "Rule for reuse" (L967)

> **Rule for reuse: never write a µs/step number without naming the host, the harness, and the decode
> step count.** One host has two step lengths (`T` and `D`) and two denominators (128 and 1023 steps).
> Prices in percent-of-score are safe to move between sections; prices in µs/step are not.

### 6.7 §5 L456-457 — o_proj

> …`decode_nvfp4_qkv_h64` sits at 94.3 % of the measured 256.7 GB/s peak, h48 92.8 %, and both refuse
> to yield; o_proj was at 83.4–90.7 % when it gave up **−35 µs/step** (#718's corrected figure; the
> −82/−80/−79.4 renderings are superseded — see §4). Screen candidate pools on measured peak, not
> nominal.

### 6.8 §4 ledger row 4 (L230) and §5 L470 — the #731 units

Both occurrences of "**−0.282 % score**" / "**−0.282 % of score**":

> **−0.282 % of the decode step = −0.135 % of score**

(`23.12 / 8199.68 = 0.28196 %` is a fraction of the step; `23.12 × 0.00586 = 0.135 %` is the score
price. §4c L405 already says −0.14 %.)

### 6.9 §4c L419 and L405 — the routed/shared conflation

L419: replace "reported a `+23.12 µs/step` routed **wall** regression from the same flip" with:

> reported a `+23.12 µs/step` regression from the **same threadgroup-widening idea applied to the
> routed expert QMV** — a different kernel and a disjoint dispatch site from delta 1's shared-expert
> SwiGLU QMV (#731's own scope check: "NO COLLISION — different env var, different kernel"). I did
> not treat it as evidence because it was not the same kernel; the correct reading is that it was
> **corroborating evidence about the mechanism** — `tgMem = 0` makes width a debit everywhere — and I
> walked past it.

L405: replace "edward's routed-wall replication (#731)" with "edward's routed-expert measurement
(#731)". Delete "as much as −0.14 % on edward's routed-wall measurement (#731)" from the §4a banner
(L247-250) — that bound belongs to a different kernel.

### 6.10 §4b DO-NOT-LAND cell and §4a banner (L245-250)

Restore §4c's hedge in the row an owner acts on:

> isolated kernel leg **+4.73 ± 0.52 µs/step** (≈ −0.028 % of score); wall effect indistinguishable
> from zero — #729's wall arm null is [−19.33, +17.86] µs/step, i.e. **|Δscore| ≤ 0.11 %**. Refuted
> either way; do not land.

### 6.11 §4 row 2 (L228) and §5 L492 — delta 2's axis weight

> …which reprices the fixed-loader version of this lever at ≈ **+0.17 % of the seed/prefill forward
> ⇒ +0.062 % of score** (§1's seed elasticity **0.362**, not the bare 0.25 prefill weight — the seed
> forward is inside the scored decode denominator as well). Still below the cost of a draw; still
> excluded.

### 6.12 §1 L146 — the operating point

> Operating point (ranked host): `mean_D = 4910.9 µs` (replicate group `dc437b0e`, n = 5, r103
> artifact) — **this is the number all ranked prices divide by**. The `S = 97.863 ms` /
> `T = 4.3224 ms` pair implies `D = 5087 µs` and
> `research/RESEARCH_IDEAS_2026-08-06_09:00.md:3` gives 4908.372; the three span 3.6 % and only the
> measured `mean_D` is traceable to a run. σ from the stated `S`/`T` is **15.03 %**, not 14.98 %;
> elasticities decode 0.638, seed 0.362 either way.

---

## 7. What this audit did not do

- **No re-litigation of items the advisor closed**: the σ(official draw) = 0.49 % sourcing and its
  L729-736 retraction, the 0.378 % → +0.4950 % gap-to-bar correction, the per-draw success table, and
  delta 1 itself. Where they appear above (clean-list 12, 19, 20; F10) it is as *context* for a live
  finding, and no closed verdict is disturbed.
- **Out of scope by instruction**: `cedar-*` branches and PRs #720–#723, #727, #728. No quantity
  sourced only to those was audited.
- **No GPU, no benchmark, no build, no W&B run.** Every number here is either read from a primary
  source in this checkout or derived by arithmetic from numbers that are, and every derivation is
  shown inline so it can be checked without re-running anything.
- **Two of the thirteen findings rest on a derived denominator** (`D₁₂₈ ≈ 12 798 µs`) rather than on a
  single naming run — see §5 items 2 and 3. The denominator is sourced ~40 times in-repo at
  12.8–13.0 ms and is independently predicted by `senpai/program.md:216-221`, so the conclusion is
  robust to ±0.8 %; the third digit is not load-bearing anywhere.

**The one missing measurement worth taking.** About 40 minutes of quiet-host time closes §5 items 1,
2, 3 and 6 at once: a single paired run of `./benchmark.sh --local-iterate` **and**
`./benchmark.sh --local-submit` on one host in one session, recording `decode_seconds_per_token`,
`totalStepOnlySeconds`, the seed-prefill seconds line (`LagunaRuntimeLocalIterate.swift:611`) and the
`includes_seed_prefill` flag from both. That pins `S`, `T`, `D₁₂₈` and `D₁₀₂₃` together on one machine
and turns the exchange-rate table from a derivation into a measurement. It is the cheapest durable
artifact this campaign could still leave behind, and it is the artifact whose absence produced F1.

---

## 8. Addendum — advisor feedback of 11:53Z, worked against branch head `6778867d`

**Why this section exists.** The assignment comment at 11:53Z asked for three things the body above
does not fully deliver: (i) re-target the audit at the *newer* manifest rather than the revision I
opened against, (ii) apply **Check 5 — verify inputs, not conclusions**, and (iii) treat two items as
highest priority: **the §4b table, cell by cell** and **σ(one official draw) ≈ 0.49 %**. Everything
below is new work done after the body was written. It adds **24 quantities** (total **142**), **two
findings** (F14, F15), **one correction to my own F10**, and **one item I could not verify**.

Two housekeeping notes. The advisor named `095499f4` (11:52Z) as the newer manifest; `git merge-base
--is-ancestor 095499f4 67396bb6` is true, so my audit base already contained it and nothing was
missed. And the 13:15Z interim comment could not be posted: `gh pr comment` is refused for this role
("use a typed Senpai GitHub tool"), and `respond_to_human_issue` refuses a pull-request target
("human messages must use an issue, not a pull request"). There is no interim channel available to
me, so the interim content is folded in here and this result is being published early instead.

### 8.1 Head re-target — the findings all still land, and F1's error has spread

Head is `6778867d` (12:59Z), manifest **1198 lines**. Every §6 replacement span above maps forward:

| §6 item | audit-base line | head line (`6778867d`) | still live? |
|---|---|---|---|
| 6.1 currency table | L913-918 | **L999-1004** | yes, verbatim identical |
| 6.2 consequence (a) | L920-926 | L1008-1014 | yes |
| 6.3 requirement table | L941-949 | **L1029-1033** | yes, plus a new claim at L1035-1036 — see below |
| 6.4 closing | L955-960 | L1041-1046 | yes |
| 6.5 §7-item-2 reprice | L961-965 | L1048-1052 | yes |
| 6.6 rule for reuse | L967 | L1054 | yes |
| 6.7 o_proj −82 | L456-457 | L466-468 | yes |
| 6.8 #731 units | L230 / L470 | L241 / L481 | yes |
| 6.9 routed/shared | L405 / L419 | L410 / L416 | yes |
| 6.10 §4b −0.03 % cell | L245-250 | **L321** | yes |
| 6.11 delta 2 axis weight | L228 / L492 | L239 / L503 | yes |
| 6.12 operating point `D` | L146 | L157-158 | yes |

Each head line was located by grepping the quoted string, not by applying a line offset; the manifest
grew 1087 → 1198 lines unevenly.

**The spread.** F1's error was confined to §6.6 at my audit base. At head it has been copied into two
further places, both of which invert the truth:

> **L819-820, §6.5:** "(the local equivalents in this sentence originally read ≈44 and ≈84 µs/step;
> those came from the UNSOURCED 0.00586 %/µs currency and are superseded by §6.6's measured table —
> **31 and 59 µs/step**)"

> **L1035-1036, under the requirement table:** "The old table's '44 / 84' column used the unsourced
> 0.00586 %/µs and therefore set a **bar ~40 % too high** in local units — the one direction of this
> error that was conservative rather than flattering."

Per F1 both sentences are backwards. `0.75/12 798 = 0.005860 %/µs` is the *scored* local rate
(`--local-iterate`, 128 steps, `Constants.swift:113`; seed charged into the denominator,
`LagunaRuntimeLocalIterate.swift:767-769,776,864`), so the correct local column is
`0.26/0.005860 = 44.4` and `0.50/0.005860 = 85.3` — the retired **44 / 84 column was right to within
rounding**, and the 31 / 59 that replaced it sets the bar **~30 % too low**, which is the flattering
direction, not the conservative one. A precise remedy, better than the one I gave in §6.3: the 8882
and 8213 columns are not arithmetically wrong *for their own denominators* — the defect is that
neither denominator is the one Maple's local screens were measured in. So **add** the `D₁₂₈` column
and label all four rows by (host, harness, step count), rather than deleting the existing columns.

Third currency column at head, checked and clean: bench-host `0.75/8213 = 0.009133 %/µs` gives
`0.26 → 28.5`, `0.50 → 54.8`, `1.26 → 138.0` against the printed 28 / 55 / 138 ✓. `--local-submit`
`0.75/8882 = 0.008444` gives 30.8 / 59.2 / 149.2 against 31 / 59 / 149 ✓. The arithmetic is right in
every column; only the choice of denominator for *Maple's* numbers is wrong.

### 8.2 §4b, cell by cell — the advisor's first priority

Eleven cells and claims. Nine clean, one new finding, one unverifiable.

| # | §4b cell (head line) | verdict |
|---|---|---|
| 1 | bar **2.6195531094824** (L333, L721, L97) | **sourced to 9 digits, not 14.** `senpai/research-frontier-briefing.md:18,26,132` gives `2.61955311` for organizer commit `4ea72c3b`/receipt `cdcd091`. The trailing `94824` has no in-repo primary source. Numerically irrelevant: the 9-digit value yields the identical gap **0.49502 %**. Fix the digits, not the conclusion. |
| 2 | best draw **2.60664970** (L334) | **clean, sourced five ways** at full precision `2.60664969895906`: `research/maple-frieren-r106e-record-check.json`, `-r105b-channel-census.json`, `-r107-*.json`, `research/CURRENT_RESEARCH_STATE.md:100,2259,5560`, briefing:32. |
| 3 | gap **+0.4950 %** (L335, L723) | **clean.** Recomputed `(2.6195531094824 − 2.60664969895906)/2.60664969895906 = 0.49502 %`. |
| 4 | **2.17–2.66σ** (L335) | **arithmetically clean**: `0.49502/0.2276 = 2.175`, `0.49502/0.1860 = 2.661`. The σ *inputs* are the subject of §8.3. |
| 5 | corroboration for the gap | **existed all along and is still uncited.** `senpai/research-frontier-briefing.md:32` and `:240` both state `e27f1ce` "trails the leader by **0.493 %**" — leader-normalised, `(bar−best)/bar = 0.49258 %`. An independent third party had the corrected gap in the trusted brief before §4b printed 0.378 %. For completeness: 0.378 % implies a bar of **2.6165**, a number that appears nowhere in the repo. |
| 6 | patch **"61 insertions / 6 deletions"** (L367) | **F14 — wrong.** `git apply --numstat` on `research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_e27_generation.patch` reports **`64  6  Sources/MLXFastModel/LagunaRuntimeModel.swift`**. Cosmetic, but it is a receipt for an artifact labelled DO-NOT-LAND, so it should be right. |
| 7 | fallback patch "53 insertions / 6 deletions" (L307) | **clean** — `git apply --numstat` reports `53  6`. |
| 8 | `git apply --check` **clean**, five hunks (L367-368) | **replicated.** Fetched e27 generation `5c542169b5e6c295805f50fa65df3150816eb443` by SHA into a scratch tree and re-ran: exit 0, five hunks. |
| 9 | the nine-citation reachability chain (L347-364) | **all nine exact** against LRM at `5c542169`: `:295-296` `DARKBLOOM_SHARED_QMV_R1 != "0"`; `:311-312` `DARKBLOOM_SHARED_SCALE_HALVED != "0"`; `:6850` `lagunaSharedSwiGLUQMVRows1Source(halved: Bool)`; `:6875` `uint row = tile * 2 + simd_group;`; `:7076` `let tiles = lagunaSharedSwiGLUQMVRows1Enabled ? 256 : 128`; `:8778` `_fusedGateUpScalesHalved`; `:8854` `lagunaSharedSwiGLUQMV`; `:8899` `_fusedGateUpScalesHalved ?? fusedScales`; `LagunaConfig.swift:33` `sharedExpertIntermediateSize = 512`. This is the best-sourced passage in the manifest. |
| 10 | residency arithmetic "identical, `64*8 = 512`" (L361-363) | **clean.** Dispatch is `grid: (tiles*64,1,1)`, `threadGroup: (64,1,1)`: shipped = 256 TG × 2 simdgroups = 512; TG=256 ⇒ tiles 64, grid 16384, 64 × 8 = 512. Granularity change, not occupancy change, as stated. |
| 11 | "**≈ −0.03 % of score or worse**" (L321, and the §4a banner) | **F8 stands** — an isolated-kernel `+4.73 ± 0.52 µs/step` is quoted as a wall/score delta. #729's wall arm is null, `[−19.33, +17.86]` µs/step, i.e. `|Δscore| ≤ 0.11 %`. The DO-NOT-LAND verdict is right; its stated price is not measured. |

**Unverifiable (new §5 item 7):** L364, "frieren's measured diff (`039800fe`) against that file: **4 of
5 hunks apply at fuzz 3**." The object `039800fe` does not resolve in this checkout
(`git cat-file -t` fails) and is still absent after fetching `maple-frieren/shared-scale-halving` and
`maple-frieren/shared-qmv-twin-gap`. I can neither confirm nor refute the fuzz-3 result; it should
carry the full SHA and a branch name so the next reader can.

### 8.3 σ — Check 5 on the inputs, and a correction to my own F10

**First, I was wrong in F10.** F10 attached "7 byte-identical families and **27 dof**"
(`research/nezuko-result.md:202-205`) to the r103 σ of 0.1860–0.2276 %. Those 27 dof belong to
nezuko's `officialScore` 0.489 % over a different corpus. r103's figures come from the head L762-771
table, whose own `n` column (5, 4, 4, 3, 2, 2, 4) gives **dof 17 untrimmed and 14 trimmed** — exactly
as L771 states. The dof bookkeeping in the manifest is internally correct; my finding mis-sourced it.

**The precision point survives and gets stronger, because 14 dof is worse than 27.** χ² 95 % intervals
on σ̂:

| figure (head line) | dof | rel. SE `1/√(2·dof)` | 95 % interval |
|---|---|---|---|
| trimmed pool **0.1860 %** (L771) | 14 | 18.9 % | **[0.136 %, 0.293 %]** |
| worst well-behaved group **0.2276 %** (L764) | 4 | 35.4 % | **[0.136 %, 0.654 %]** |
| untrimmed pool 0.9546 % (L771) | 17 | 17.1 % | [0.716 %, 1.431 %] |
| nezuko `officialScore` 0.489 % | 27 | 13.6 % | [0.387 %, 0.666 %] |

Two consequences the manifest does not state. (a) **Four significant figures are unsupported**;
`0.19 % (95 % CI 0.14–0.29 %, 14 dof)` is the honest rendering, and the derived `2.17–2.66σ` is really
`1.7–3.6σ`. (b) The **single-group 0.2276 % cannot by itself exclude the retracted 0.489 %** — its own
95 % interval contains it. Only the *pooled* figure excludes it (upper limit 0.293 % < 0.489 %), and
only because of the trim.

**F15 — the load-bearing input is the trim, not the sampling error.** 0.1860 % (dof 14) versus
0.9546 % (dof 17) is a **5.1× swing** produced by excluding one four-draw family, `7cbffc2c`. Anchored
on the program mean (`(2.6195531094824 − 2.582263)/2.582263 = 1.4441 %`):

- trimmed σ 0.1860 % ⇒ z = 7.76 ⇒ P(one draw ≥ bar) ≈ 0 % — the "≈0 % (z = 6.3–7.8)" row at L954;
- untrimmed σ 0.9546 % ⇒ z = 1.51 ⇒ **P ≈ 6.5 %**.

So that row is a product of the trim, not of a measurement. The manifest's physical justification for
the trim is sound and is stated (L786-789: the excursions "**only ever subtract**"), but it has a
corollary the table does not draw: **a σ estimated after removing one-sided downside excursions must
not be fed symmetrically into an upside tail probability** — which is the manifest's own argument,
applied to its own arithmetic. Direction of the error: the trim makes σ smaller, which makes
P(success) smaller, which *strengthens* the manifest's "re-firing is hopeless" conclusion. It is
therefore self-serving rather than conservative, and worth flagging even though I agree with the
conclusion.

**What survives Check 5 intact, and should carry the paragraph:**

1. The **provenance** retraction of 0.49 % is sound: the archive's σ figures are cross-code
   quantities and inflate a same-tree re-draw by 2.4–2.6× (L779-784; the retraction itself begins at
   head L738). I do not disturb it.
2. The **structural consistency check is real corroboration** and I re-derived it exactly:
   `sd(D) 14.43 / mean_D 4910.925 = 0.29383 %`, `× 0.75 = 0.22038 %`, `⊕ 0.25·sd(ln P) = 0.0257 %`
   ⇒ **0.22187 %** against **0.2276 %** observed on the score itself. Independent of any dof count,
   this says the instrument obeys the scoring model. It is the strongest σ evidence in the document.
3. The **model-free bound needs no σ at all**: `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md:62-64`,
   0 clears in 106 account draws ⇒ **P(one draw ≥ bar) ≤ 2.83 %**, 95 % one-sided. Recomputed
   `3/106 = 2.830 %` ✓. This bound also caps the top of the σ̂-uncertainty band, which the band alone
   does not.

**Recommended edit:** print σ as `0.19 % (95 % CI 0.14–0.29 %, 14 dof, trimmed)`, replace the "≈0 %"
cell with "<0.1 % on the trimmed σ, 6.5 % on the untrimmed σ — the gap between those two numbers is a
judgement about one-sided thermal excursions, not a measurement", and lead the endgame paragraph with
the 2.83 % model-free bound, which is the only statement here that survives with no distributional
assumption.

### 8.4 §6.5c (winner's curse) is orthogonal to F1, and its ranked column checks out

§6.5c is the newest and largest correction in the manifest (≈6× on the delta table) and it does not
depend on anything F1 touches: it re-anchors from the lucky draw `2.60664970` to the program mean
`2.582263` and prices against fern's draw sd 0.538 %, not against any µs/step currency. The
requirement table that carries its probabilities (head L1029-1033) is clean in its **ranked** column —
`1.26 / 0.015272 = 82.5` vs printed **82**, `0.26 → 17.0` vs **17**, `0.50 → 32.7` vs **32**
(rounding). Its *local* columns inherit F1 unchanged: 31 / 59 / 149 become
**44 / 85 / 215** on the scored local denominator. No probability in §6.5c moves, and no disposition
anywhere in the manifest moves — F1 changes what the engineering bar costs in local units, not who
cleared it.

### 8.5 Net effect of this addendum

- **F14** (new, cosmetic): §4b's e27 patch is 64 insertions / 6 deletions, not 61.
- **F15** (new, decision-grade for planning): σ's quoted precision is unsupported at 14 dof, the
  single-group figure cannot exclude the retracted 0.489 %, and the "≈0 %" per-draw row is produced by
  the trim rather than by the measurement (untrimmed ⇒ 6.5 %).
- **F10 corrected**: the 27-dof citation was mine and was misapplied; the correct dof are 14/17 and
  the conclusion strengthens.
- **§5 item 7** (new, unresolvable): the `039800fe` fuzz-3 claim cannot be checked from any branch
  reachable here.
- Everything else in §4b — bar, best draw, gap, z arithmetic, fallback patch counts, the nine-line
  reachability chain, the apply-check, the residency arithmetic — **replicated clean**, including the
  one artifact I regenerated from scratch. §4b is, F14 and the unverifiable fuzz line aside, the most
  carefully sourced section of the manifest, and this audit found nothing that changes its
  DO-NOT-LAND verdict.
- **F1 remains the one decision-grade item**, and it is now propagating: at head it has been written
  into §6.5 (L818-820) and into a new claim at L1036-1037 that the retired 44/84 column "set a bar
  ~40 % too high", when the arithmetic says that column was right and its replacement is ~30 % low.

