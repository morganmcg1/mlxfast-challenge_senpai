# R127-A — Provenance audit of `research/maple_endgame_handoff_manifest.md`

**Audit base:** `67396bb6` — the advisor branch head at 12:40Z, the first revision containing §6.6
(added 12:10Z, completed 12:35Z). The manifest at that commit is 1087 lines; every `L####` below is a
line in that revision.

**Addenda:** §8 re-targets every finding to branch head `6778867d` (manifest 1198 lines) against the
advisor's 11:53Z feedback; §9 answers the 12:29Z and 12:44Z feedback and adds F16-F18; **§10 takes the
widening in the assignment's own stopping rule** and audits `research/CURRENT_RESEARCH_STATE.md` and the
two live tools that feed it, adding F19 and F20 plus corrections to my own F18 and §9.5; **§11 takes
the other half of that same widening** — the three round archives — adding F21, which strengthens F19
from an independent 12-program corpus. **§12 adds no findings**: it is the applier's work order,
collapsing every recommended edit from §6, §8.3, §9.3, §10.4 and §11.4 into one ordered table of 25
rows, each target verified still present at its cited line at head by
`research/tools/r127a_s12_edit_target_check.py` (25/25 PASS). **§13** ships that work order as an
executable, guard-checked applier and found three more copies of the F19 bracket while doing so.
**§14 adds F22**: `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md` — the one-page handover, outside every
earlier section's scope — carries F1 as a *prescription* ("never price a delta with 0.00586 %/µs",
`:181-183`), which sets local screening bars ≈30 % too low; rows B1–B6 take the applier to 34 rows.
**§15 adds F23**, found by following the brief's own reading list: `brief:60` says of
`research/tools/account_draw_record.py` "(run it)", and that fifth artefact — also outside every
earlier section's scope — still prints the superseded 0.95 %/1.48 % pair as the per-fire price and
reads a rule-of-three *ceiling* as corroboration of it; rows C1–C2 take the applier to 36 rows over
five files. Line references inside §8-§15 are
head lines (`CRS:####` = `research/CURRENT_RESEARCH_STATE.md` at that head); §1-§7 line references are
`67396bb6` lines, with the head equivalents tabulated in §8.1.

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

---

## 9. Second addendum — advisor feedback of 12:29Z and 12:44Z

### 9.0 Timing, and what this addendum adds

Both comments were **created at 12:29Z and 12:44Z and delivered to me at 13:24Z**, i.e. after I had
already published the terminal result at commit `494b6df3`. There is still no channel by which I could
have known earlier (§8 preamble: `gh` unauthenticated, `respond_to_human_issue` rejects PR targets,
`git push` blocked outside `submit_experiment_result`). This section is therefore a **second terminal
submission on the same branch**, not an interim.

Three of the four asks were already answered in the body of this audit and I have not rewritten them:

| ask | where it already is |
|---|---|
| the µs/step currency census, with `correct % / as banked / discrepancy factor` | **§2.4**, 13 rows, exactly the requested column layout; verdict in §2.5 |
| the census's disposition consequence | §2.5 and §3 (F1-F3); re-stated and extended in **§9.4** |
| do not audit delta 1 itself | §7 bullet 1: delta 1 appears only as a *price* row, never as a post-mortem |

What is new below: the currency identity is now **proved from the ranked host's own receipt fields**
(§9.1), Rule 14 violations are **named, including mine** (§9.2), claims of absence are **tested by
grepping for the thing they say does not exist** (§9.3), every decline is **re-priced** (§9.4), and
§7 item 6 is **answered from our own receipts, with a mechanism that was not on the board** (§9.5).

Everything below is read-only: `git show`, `git grep`, `git ls-tree`, `git cat-file -t` against
`6778867d` and five in-tree receipt JSONs. No build, no benchmark, no draw, no W&B run.

### 9.1 The currency census, closed from the ranked host's own receipts

§2 derived the currency identity `rate = 0.75 / D` from our source (`Score.swift:4-7`,
`LagunaRuntimeLocalIterate.swift:767-769,776,864`). That was the *local* side. The **official** side is
now closed too, from five receipts that have been sitting in the tree since round 93
(`research/r93-runs/receipts/null-{1..5}.json`):

```
officialScore  = decode_speedup^0.75 * prefill_speedup^0.25      exact, 0 ppm residual, all 5
decode_speedup = baseline_decode_seconds_per_token / decode_seconds_per_token     exact, all 5
```

So `d ln(officialScore) / d D_candidate = -0.75 / D_candidate` **identically**, on the ranked host, for
whatever `D_candidate` that harness reports. Every row of §6.6 is an instance of one identity, and the
only live question is which `D` each quoted µs/step figure actually is. Provenance test of all four:

| §6.6 row | D | §6.6's label | what the tree says | verdict |
|---|---|---|---|---|
| ranked official | 4910.9 | measured | = mean candidate decode of the five receipts above (4894.114, 4931.226, 4900.524, 4916.141, 4912.621 ⇒ mean 4910.9253); also `research/r93-runs/log_wandb.py:24` `NULL_DECODE_US = 4910.9253`, `research/r93-runs/RESULTS.md:1123,242` | **safe.** `0.75/4910.9 = 0.015272 %/µs` is *exact*, not approximate |
| `--local-submit` | 8882 | "measured, nezuko #730" | **8882 as a µs/step figure occurs nowhere in the tree.** Boundary-aware grep over `research/ senpai/ Sources/` at head returns 7 hits, all coincidental (a dispatch row index, a UUID fragment, an LRM line-range heading, a stripped-comment line number, a receipt-corpus digest) plus `MAPLE_TO_SLOT_HOLDER_BRIEF.md:183,215`, which cite "§6.6". I read #730 in full: its decode figures are 8918.96 / 8950.29 / 8975.75 / 9124.84 µs/step and it prices against "the 8,567 µs decode busy budget" | **attribution unsupported.** Nearest #730 number is 8918.96 ⇒ `0.75/8918.96 = 0.008409`, 0.4 % off the printed 0.00845 |
| bench control | 8213 | "measured, frieren #733" | in-tree, exactly one real hit: **one single token step out of 765** in `research/frieren_r116_raw_steps.csv:357` (`confirm,C7,ABBA,ctl,26,8213.0`). The ctl-arm *medians* are **8189.0** (confirm, n=105) and **8192.0** (screen, n=45). In #733's typed result 8.213-8.217 ms is named explicitly as the **slow mode of a bimodal control**, against 8.148-8.152 ms | **mislabelled in kind.** It is a wall-clock step time, the slow mode, not a median and not a decode denominator. At the median: `0.75/8189 = 0.009158` (+0.3 %) |
| manifest inherited | 12798 implied | "**UNSOURCED — I cannot establish it. Do not reuse.**" | `0.00586` has **two hits outside the manifest and outside advisor-authored files**: `research/frieren_r116_router_top8_number.md:154` derives it from a *realized ranked outcome* — "alphonse's merged #700 turned −76.8 µs/step into +0.45 % score, i.e. 0.00586 % score per µs/step" (0.45/76.8 = 0.005859) — and `research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_e27_generation.patch:40` applies it (64.8 µs/step ⇒ +0.38 %; 0.38/64.8 = 0.005864). Add §2.2's ~40 in-repo local D measurements, 12 775-12 972 µs | **the row branded unsourced is the best-sourced of the four**, and it is the only one with an *outcome* anchor rather than a harness-internal one |

**F16 (new, decision-grade).** Of the four §6.6 currencies, one is safe (4910.9), one is unsupported in
its attribution (8882), one is mislabelled (8213), and the one branded UNSOURCED has two independent
in-tree derivations, one of which is a realized ranked promotion. The labels are, in provenance terms,
close to inverted. The three *rates* `0.01527`, `0.00845`, `0.00913` have **zero** in-tree occurrences
outside `MAPLE_TO_SLOT_HOLDER_BRIEF.md`, which cites "§6.6" — they are new to §6.6, derived, not
measured, which is fine, but they should not be labelled "measured currencies" (`BRIEF:182`).

One trap for whoever fixes this: the ranked host's **baseline** decode is 13 819-13 871 µs/step (the
five receipts). That is ~8 % from 12 798 and it is *not* a source for it. 12 798 is a candidate-side
local D; 13 845 is the reference model on the ranked host. Do not join them.

### 9.2 Rule 14 violations, named

Rule 14: *when you correct a reference point, recompute every row that shares it, in a script, in one
pass.* Five violations, in descending consequence. Two are the manifest's, two are inherited, one is
mine.

1. **§6.6 itself, twice — the largest.** §6.6 replaced the local currency with rates 1.44-1.56× larger
   and did not recompute two rows that share that reference point: **§7 item 2** (banked "~2 % of
   score" for ~350 µs/step; §6.6 restates it as 2.94 %; correct at 0.00586 is **2.05 %**, factor
   **1.44×**) and **FUSED** (banked −0.504 %; #733 measured +55.2 µs/step ⇒ **−0.323 %**, factor
   **1.56×**). The second is live: the advisor's disposition comment on #733 *instructed* frieren to
   reprice 1.56× larger. §2.4, §6.1-6.5.
2. **§6.6's own requirement column.** 31 / 59 / 149 µs/step replaced 44 / 85; the replacement is
   `0.75/8882`-consistent but the *question* is a local-harness question, so the correct column is
   **44 / 85** and the printed one is ~30 % lenient. §6.6 then asserts at L1035-1036 that the retired
   column was "~40 % too high … conservative rather than flattering", which is backwards. F1/F2.
3. **§5 o_proj (L456-457)** still carries **−82 µs/step** where the cited source measures **−35**
   (factor **2.34×**). §4c corrected this reference point; §5 was not recomputed. F5.
4. **§4 row 4 (L230) and §5 (L470) on my own #731.** Both print **−0.282 %**, which is the *fractional
   decode slowdown* 23.12/8199.68 misread as a score delta; §4c L405 prices the same delta correctly at
   **−0.14 %**. Factor **2.09×**, two rows sharing one reference, only one recomputed. Related: §4c
   L399 (64.8) against L414 (41.4) is **1.57×** inside a single paragraph. F4, F8.
5. **Mine.** Two, and I will name both. (a) **F10** — my first-pass σ note took the wrong reference
   population; corrected in §8.3, and the correction is mine, not prompted. (b) §2.4's discrepancy
   factors were computed against the `095499f4` text and then re-targeted to head **by hand** in §8.1
   rather than by one scripted pass, which is exactly the shape Rule 14 forbids. §9.1 repairs it: the
   identity is now re-derived from receipts, and **no factor in §2.4 moved**.

The unifying mechanism is worth stating once: substituting 0.00845/0.00913 for 0.00586 multiplies
**every** price in the document by 1.44-1.56× away from zero. Credit-side rows therefore inflate the
value of marginal work (§7 item 2, o_proj, the requirement column) and debit-side rows inflate the cost
of the things already declined (#731, FUSED). Both directions are wrong by the same factor from the
same cause, which is why one scripted pass fixes all of them.

### 9.3 Check 5 — claims of absence, and rows whose only citation is this document

Method: for each claim of absence, grep the tree for the thing the claim says does not exist; for each
row of §6.6 and §7 (**excluding §7 item 2, `≈8919 µs wall / ≈8567 µs busy`, which is maple-alphonse's
in #744**), grep for any citation outside the manifest family. Boundary-aware: BSD grep has no `-P`, so
`(?<![0-9.])tok(?![0-9])` is enforced in Python after `git grep --fixed-strings`, which is what
separates `8882` from `2.58882784` and `8213` from `dd7b1236a8213ff…`.

| claim of absence | test | result |
|---|---|---|
| §6.6: `0.00586` is "UNSOURCED — I cannot establish it" | grep `0.00586` | **falsified.** Two independent hits outside the manifest family (§9.1) |
| §6.6: "no harness we ran reproduces" the 12 798 step (`BRIEF:182`) | grep `12798`, `12,798` | literally true of the *string* (1 hit, advisor's own brief) but the *quantity* is measured ~40 times in-repo at 12 775-12 972 µs (§2.2), so the claim is true only of the digits, not of the step |
| §6.4: the `queue_probe_1110` JSONL, "if it is still present" | grep `queue_probe_1110` | **absent.** Manifest already hedges; hedge is correct |
| §7 item 5: "never measured" occupancy items | resolve all five source coordinates in `LagunaRuntimeModel.swift` at head | **substance verified, coordinates stale.** `heads/2` dispatch is at **L1978 and L2463** (`grid: ((heads / 2) * 1024, 1, 1)`), not `:1970-1971`/`:2455-2456`; `ROUTED_GATEUP_R1` is at **L8062** (`DARKBLOOM_ROUTED_GATEUP_R1`), not `:8053-8054`; `:1586-1588` lands on rotary math and `:2048-2050` on a `constexpr` block. Off by 8-9 lines in a 12 431-line file. Fix by citing tokens, not lines |
| §7 item 4: re-audit against `N-K3-AT-DRAM-ROOF` | grep the label | **zero hits anywhere in the tree outside the manifest**, and the item names no PR. This is the clean instance of the advisor's own test: *a row whose only citation is another row of this document* |
| §7 item 3: `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`, "≈0.79 µs/step per extra simdgroup" | grep label, grep `0.79 us/step` | label self-cited only (1 hit, advisor's brief), but the **number is independently sourced** — `research/patches/REFUTED_DO_NOT_LAND_r125a_tg256_advisor_fallback.patch:11` and `…_e27_generation.patch:15`. Row stands; relabel to cite the patches |
| §7 item 1: "~27.88 ms of the 97.9 ms prefill seed forward is unattributed" | grep `27.88`, `97.89` | **sourced.** `maple-fern-r106i-prefill-traversal-census.md:635` ("central 27.88 ms [PROJ]"), `maple-tanjiro-nonmoe-prefill-census.md:64`; `S = 97.89475 ms` at `RESEARCH_ARCHIVE_through-round-91.md:1284` |
| §7 item 6: `dc437b0e`, "if that program is still reconstructible" | grep `dc437b0e` | **41 hits / 12 files, and the answer is yes** — §9.5 |
| §6.5b: "Primary source: `research/fern-r109f-interim-1200Z.md` ADDENDUM 2 §L" | `git ls-tree` the path; grep `r109f` | **the named primary source is not in the tree at head, and no file matching `r109f` exists at all** — including the two `maple-fern-r109f-*.md` paths that `CURRENT_RESEARCH_STATE.md:631-632` names |

**F17 (new).** §6.5b's entire numeric core — `2.576540`, `2.582263`, `1.016694`, `1.009444`,
`1.001830`, `1.012550`, `1.024492` — occurs in the tree **only** in `MAPLE_TO_SLOT_HOLDER_BRIEF.md`
(which cites "§6.5b, fern") and `research/tools/slot_holder_arithmetic.py:10-14` (whose comments cite
"6.5b"). `1.012550` and `1.024492` occur **nowhere at all**. `CURRENT_RESEARCH_STATE.md:785` records the
same work as decomposing **1230** official rows where §6.5b says **1280**, and that cannot be
adjudicated from the tree. This is not misconduct — #686 closed unmerged, so the file legitimately
never landed — but it means the manifest's **most load-bearing strategic claim** ("our normalized
2.582263 already exceeds the crown's normalized 2.576540 … we lose on draw variance, not on code",
which is the stated basis for the policy that cutting gates to buy draws is irrational) is, in the
repository a successor will actually receive, **self-cited only**. Recommended edit: mark §6.5b
"primary source not in tree (PR #686, closed unmerged; numbers not independently reproducible)" and
point at §9.5, whose route to the same conclusion is entirely in-tree. The conclusion survives; the
citation does not.

A second class worth flagging: several §7 figures are sourced to **PR comment bodies** rather than to
files — the −40.9 µs/step OPROJ screen and its local null "−5.4 [−12.6, +1.6] at n=12" are in #733's
typed result and nowhere in the tree. For a document whose purpose is handover with the repo, that is a
provenance gap even though the numbers are real.

### 9.4 Was any decline decided against an inflated price?

Yes, twice. Neither flips. Full re-pricing at the corrected local currency (0.00586 %/(µs/step)):

| decision | banked price | correct price | factor | does the disposition change? |
|---|---|---|---|---|
| **#731 routed TG=256 — not indicated** | −0.282 % (§4, L230; §5, L470) | **−0.135 %** (+23.12 µs/step; §4c L405 already says −0.14 %) | 2.09× inflated debit | **No.** Still a debit, and 0.36σ of one official draw (§9.5). Decline stands |
| **FUSED family (#733) — terminal** | −0.504 % | **−0.323 %** (+55.2 µs/step) | 1.56× inflated debit | **No.** Still a debit. But the 1.56× is a *live instruction* to frieren and should be withdrawn |
| **delta 2 prefill — EXCLUDED** | +0.04 % | **+0.062 %** (+0.17 % prefill × 0.25 axis weight ÷ …; §2.4) | 0.65×, i.e. banked *too small* | **No.** 0.062 % is 0.17σ of one draw. Decline stands, and for a better reason than the one recorded |
| **OPROJ_SIMDGROUPS=4 — declined (frieren)** | −40.9 µs/step screen, local null −5.4 [−12.6, +1.6] n=12 | n/a — refusal was on M4→M5 non-transferability, not on price | n/a | **No, and correctly so.** §7 item 5 is right that this refusal is the model. No repricing can touch it |
| **delta 1 — refuted** | +4.73 µs/step ⇒ −0.028 % | same | 1.00× | **No.** Isolated and safe; §4c is a complete post-mortem and I did not re-audit it |

Inflated *credits*, which are the more dangerous direction because they invite spending a draw:
§7 item 2 at 2.94 % where 2.05 % is correct (1.44×); §5 o_proj at −82 µs/step where −35 is measured
(2.34×, i.e. an o_proj win is worth +0.205 %, not +0.48 %); and §6.6's requirement column at 31/59
where 44/85 is correct, which would pass a 40 µs/step delta as clearing the +0.26 % bar when it does
not. **No disposition anywhere in the manifest flips on any of this.** The exposure is prospective: a
successor pricing new work off §6.6 would over-value it by 1.44-2.34× depending on the row.

### 9.5 §7 item 6 — `dc437b0e`: yes, we hold it, and it answers a larger question

**Answer: yes.** From our own account's receipts and our own tree only, no reconstruction of anyone
else's submission.

The group is `senpai-r93-null-1..5`: **maple-tanjiro**, assignment `maple-r93-a-m5-receipt-channel`,
revision `r93-a-rev1`, arm A true null, five replicates whose trees differ by **exactly one comment
line** — `// senpai-r93-null-N` at `LagunaRuntimeModel.swift:9474`
(`research/maple-frieren-r106e-replication.md:1174`; `CURRENT_RESEARCH_STATE.md:7578`; advisor-r103
§5.2). `research/artifacts/maple-nezuko-r106b/replicate-identity-verified.json` group
`r103:dc437b0e0b918c86` records `n = 5`, `n_distinct_strict = 5`, `problems: []`,
`verified_inert_only: true`, `changed_files_vs_reference: {LagunaRuntimeModel.swift: 4}`.

Chain of custody, all in-tree:

| null | commit sha12 | receipt id | account TSV | officialScore | status |
|---|---|---|---|---|---|
| 1 | `4b0e051bf3cd` | `25e1f18e` | 8/9/26 2:56 AM | 2.57537675806293 | rejected |
| 2 | `d6a5f9e7346e` | `d11026c9` | 8/9/26 3:18 AM | **2.59319614607077** | rejected |
| 3 | `e1b6e2be2792` | `05dd8bbf` | 8/9/26 4:06 AM | 2.57423407186536 | rejected |
| 4 | `ca91d86c904c` | `ab6a15a1` | 8/9/26 4:55 AM | 2.56861545123952 | rejected |
| 5 | `5d9060aa0d36` | `4fec8e2d` | 8/9/26 5:44 AM | 2.57166224186903 | rejected |

All five are on `morganmcg1` in `research/receipts/account_submissions_1254Z.tsv`, all rejected with
`rejectionReason: "score did not improve current best"`, and the raw receipts are in-tree at
`research/r93-runs/receipts/null-{1..5}.json`. `research/artifacts/advisor-r103/tree-identity-map.json`
carries `sub_sha 4b0e051bf3cd9777bd6d2be64e172c490705f9a5` and `sources_tree 85ba1a2f4d9a…`.

Two honest qualifications. (a) **Neither the submission commits nor their trees are git objects in our
repository** — `git cat-file -t 4b0e051bf3cd9777bd6d2be64e172c490705f9a5` and the two arm digests
`ef055b9b…` / `bd33883e…` all return `could not get object info`. "Still hold it" is true at the
receipt-and-description level, not at the retrievable-object level. (b) That is sufficient anyway,
because the program is described exactly enough to rebuild, **and it has already been rebuilt once**:
frieren replayed it at r106e by rewriting the marker (`maple-frieren-r106e-amendment3.md:183`,
`senpai-r93-null-1 (= 4b0e051b)` → `senpai-r106e-replay-NN`), and the script that does the rewrite is
in-tree at `research/r106e_draw.sh:46`.

**Correction to §7 item 6's own numbers.** "mean score 2.5831" is the mean **`cs`**, not the mean
official score. I verified that `cs` is *exactly* `K · D^-0.75 · P^-0.25` with `K = 5610.207` constant
to 1.2 × 10⁻⁶ across all five receipts — i.e. `cs` is a deterministic function of the receipt's own
candidate metrics. The mean **official** score of the group is **2.576617**. So "its mean sits above
the crown's normalized 2.576540" compares a candidate-only score to a program-normalized official one,
and on the closest matching quantity the margin is **+0.0030 %, not +0.26 %**. The row's motivation is
weaker than printed — but there is a much better reason to care about this group.

**F18 (new, and the most consequential thing in this addendum).** The receipts carry
`baseline_decode_seconds_per_token` and `baseline_prefill_seconds_per_token`, and **the baseline is
re-measured on every submission**:

| null | candidate D µs/step | baseline D µs/step | candidate P µs/tok | baseline P µs/tok | officialScore |
|---|---|---|---|---|---|
| 1 | 4894.114 | 13819.365 | 187.637 | 366.640 | 2.57537676 |
| 2 | **4931.226** | 13845.108 | 187.734 | **383.584** | **2.59319615** |
| 3 | 4900.524 | 13857.327 | 187.877 | 364.885 | 2.57423407 |
| 4 | 4916.141 | 13864.993 | 188.117 | 365.037 | 2.56861545 |
| 5 | 4912.621 | 13870.722 | 187.994 | 365.293 | 2.57166224 |

Read null-2. It has the group's **slowest** candidate decode (+0.758 % vs null-1) and the group's
**highest** official score (+0.692 % vs null-1). The official score is **not monotone in our own
metrics**, and the reason is in the table: its baseline prefill came in at 383.584 against ~365 µs/tok
for the other four, +4.6 %, which at the 0.25 axis weight is worth +1.13 % of score. Decomposing
`ln(officialScore)` over the five replicates of this one fixed program:

```
sd(ln candidate decode)  = 0.2938 %     sd(ln baseline decode)  = 0.1471 %
sd(ln candidate prefill) = 0.1027 %     sd(ln baseline prefill) = 2.1725 %   <-- dominant term
candidate-only component = 0.2276 %  (== advisor-r103's printed sd(ln cs) = 0.2276 %, exactly)
baseline-only component  = 0.5263 %   corr(candidate, baseline) = -0.79
sd(ln officialScore)     = 0.3728 %   (reconstructed to 4 digits from the four fields)
```

Three consequences, and I am deliberately *not* re-deriving the closed rows:

1. **"Draw luck" has a mechanism, and it is the harness's own baseline measurement, chiefly baseline
   prefill.** fern's cross-program draw σ of **0.538 %** (§6.5b) and this group's baseline-side σ of
   **0.5263 %** agree to two digits. That is a receipt-level corroboration of §6.5b's conclusion by a
   route that does **not** depend on the primary source missing from the tree (§9.3, F17). It also
   suggests fern's 0.538 % is not mainly "between-program leakage" at all.
2. **A Rule-14 flag on §6.5/§6.5c's σ input, for its owner.** 0.186-0.228 % is a **`cs`** σ and
   therefore structurally excludes *all* baseline-side variance; the within-program **official** σ is
   **0.3728 %**, 95 % CI [0.223 %, 1.071 %] (n = 5, χ², dof 4). Substituting it into §6.5c's own z
   takes z from 6.34 to 3.87 and P(one draw clears from the program mean) from ≈0 to **0.005 %** —
   still ≈0, so **the disposition and the no-buy-draws policy do not change**, and the bracket the
   manifest states as `[≈0 %, 1.5 %]` reads `[0.005 %, 0.36 %]` when both ends use the program mean as
   reference. Notably, the advisor's own closed σ(one official draw) of 0.49 % sits *inside* that CI
   and is much closer to 0.373 % than to 0.19-0.23 %, which is independent support for the relabelling.
   The row is its owner's; I am flagging the input, not rewriting the table.
   **[Refined by §10.3(e), F19.]** The `0.005 %` here substitutes the corrected σ into §6.5c's
   *uncentred* numerator (+1.4441 %). Centred on the program's own mean official score
   (`2.582263 × 1.001830 = 2.586989`, required move +1.2588 %) the same σ gives **0.037 %** — my figure
   was low by 6.8× — and §10.3 shows the `[0.005 %, 0.36 %]` restatement above should be a single
   estimate with a σ interval, not a bracket between two σ's.
3. **A free instrument for the successor.** Every receipt carries its own baseline, so any two
   receipts can be compared on candidate metrics alone — that is `cs` — at σ **0.228 %** instead of
   **0.373 %**. Dividing by a re-measured baseline *injects* noise rather than removing it (the
   correlation is −0.79). Never A/B two official scores when both receipts' candidate metrics are in
   hand; and never read a single official score as evidence about a program, because 0.69 % of it can
   be the harness's baseline having a slow morning.

### 9.6 Net effect of this addendum

No previously banked finding is withdrawn. Three new ones: **F16** (the §6.6 provenance labels are
close to inverted), **F17** (§6.5b's numeric core is self-cited only and its named primary source is
absent from the tree), **F18** (the official score's within-program variance is majority baseline-side,
mechanism identified, and it re-labels the σ input of §6.5/§6.5c without changing its disposition).
Rule 14 violations are named in §9.2, including two of mine. Every decline is re-priced in §9.4 and
**none flips**. §7 item 6 is answered **yes** in §9.5, with one correction to the row's own arithmetic.

F1 remains the single decision-grade item and its recommended replacement text is unchanged (§6.1).
The highest-value single edit is still §6.6's currency table; the second is withdrawing the 1.56×
reprice instruction issued to frieren on #733.


---

## 10. Third addendum — extension to `research/CURRENT_RESEARCH_STATE.md`

### 10.0 Why this section exists, and what it audits

The authority for this section is the assignment's own stopping rule, in the PR body, quoted verbatim:

> If you exhaust the scope early, do **not** invent GPU work. Extend the audit to
> `CURRENT_RESEARCH_STATE.md` and the round archives instead, same four checks.

§1-§9 exhausted the manifest's decision-grade rows, so this addendum applies the same four checks to the
**downstream** artefact: the state file the successor will actually read, plus the two live tools that
feed it. It stays inside the same envelope — read-only, `research/` only, no GPU, no build, no benchmark,
no W&B run.

**Sources for §10, all at branch head `6778867d`:**

| artefact | size / anchor | how referenced below |
|---|---|---|
| `research/CURRENT_RESEARCH_STATE.md` | 10,609 lines, md5 `edafefe90de372a23bc59ad16a930b2d` | `CRS:####` |
| `senpai/research-frontier-briefing.md` | snapshot **2026-08-11 10:06 UTC** (L3) | `brief:####` |
| `research/tools/slot_holder_arithmetic.py` | the script §6.5c says to run | `tool:##` |
| `research/advisor-r104-the-receipt-is-the-instrument.md` | origin of the ×1/median-draw bar | `r104:###` |
| my five receipt JSONs | `n1`-`n5`, §9.1 | receipt algebra |

Method unchanged: every number is re-derived from its inputs, and a claim is only "verified" if the
inputs are in the tree. No GPU, no build, no benchmark, no W&B run; nothing outside `research/` read as
anything but a primary source.

### 10.1 Clean bill first — the §6.6 currency exposure did **not** propagate into the state file

F5/F6/F16 concern constants that §6.6 mislabels. The obvious risk is that they were copied into the
successor-facing state file. They were not:

| constant | occurrences in `CRS` (10,609 lines) |
|---|---|
| `0.00586` (the §6.6 currency) | **0** |
| `12798` (decode µs/step anchor) | **0** |
| `4910.9` (prefill anchor) | **0** |
| `2.60664970` | **1**, at `CRS:5560` — the `our best / e27f1ce (Cedar) / 2.60664970` leaderboard row, not a currency |
| `8882` | 3, **all** the unrelated score `2.588828` |

So the §6.6 defect is **manifest-local** (plus the slot-holder brief that quotes it). That bounds the
blast radius of F16 to two documents and is the one piece of good news in this addendum. It is also
why §10 spends its remaining budget on what *is* in the state file.

### 10.2 Correction to my own F18 — the mechanism was already in this repo, and I should have found it

F18 (§9.5) reported that the official score's within-program variance is majority baseline-side, and
presented the mechanism as new to the audit. **It is not new to the repo.** `CRS:3509-3511` states it
outright:

> Corpus `L` (n = 1,204): median 0.998597, sd(ln L) 0.5359 %, p90 1.007519, p95 1.009232, p99 1.012733,
> max 1.021135; **≈96 % of that variance is the `bl_pre` baseline draw.**

and `CRS:3541-3548` gives the same decomposition with the record receipt worked through. This is a
**Rule-14 failure of mine**: I priced a mechanism without first grepping the state file for it, exactly
the failure mode §9.2 names in others. Recorded here rather than quietly edited, per the manifest's own
convention.

What survives as my contribution, and it is narrower than F18 claimed:

1. **An exact algebraic identity, not a statistical finding.** For each of my five receipts,
   `official / cs` equals `(baseline_D^0.75 · baseline_P^0.25) / K` to **0.000 ppm** with a single
   fitted `K = 5610.207`. The draw factor `L` therefore contains **no candidate term at all** — it is a
   pure function of the two baseline legs. `CRS:3509` measures that; the receipts prove it.
2. **An independent reproduction of the ≈96 %**, from n=5 receipts instead of n=1,204:
   sd(ln base_D) = 0.1471 %, sd(ln base_P) = 2.1725 %; `0.75 × 0.1471 = 0.1103 %` and
   `0.25 × 2.1725 = 0.5431 %`; in quadrature **0.5542 %**, of which the prefill leg is
   `0.5431² / 0.5542² =` **96.04 %**. Two independent samples, same 96 %.
3. sd(ln L) from those five receipts is **0.5263 %** against `CRS:3509`'s **0.5359 %** (n=1,204) — 1.8 %
   apart on five points, which is as much agreement as five points can give.

Point 1 is what makes §10.3 a finding rather than an opinion, so the correction costs the audit nothing
except the credit.

### 10.3 F19 — §6.5c's `[≈0 %, 1.5 %]` is not a bracket: **both** rails price the wrong random variable, in opposite directions

**The claim audited.** §6.5c (L948-953) replaces the earlier ~1 %-per-draw price with a two-row bracket:

> | within-program σ 0.1860-0.2276 %, normal | program mean (correct) | **≈0 %** (z = 6.3-7.8) |
> | fern's draw component, sd 0.538 %, normal | program mean (correct) | **0.95 %** (z = 2.344) |

and instructs the successor to **"Plan against `[≈0 %, 1.5 %]` per draw"** (L959-960). Both rows are
labelled as using the same reference point. They do not, and neither σ is the σ of the quantity the
successor actually draws.

**(a) The quantity being priced is a draw factor; the lower rail is the sd of the candidate legs.**
`tool:35-36` computes `need = BAR / OUR_PROGRAM = 2.6195531094824 / 2.582263 = 1.014441`.
`OUR_PROGRAM` is a **program-normalized** mean, i.e. a `cs`; `BAR` is an **official score**. So `need` is
by construction a required value of `official / cs` — that is, of the draw factor `L`. By §10.2 point 1,
`L` is an exact function of the two baseline legs and contains no candidate term. The 0.1860-0.2276 %
σ is, by §9.1 and r103's own definition, the replicate sd of **`cs`** — the candidate legs only. Using it
here discards the ≈96 % of `L`'s variance that `CRS:3509` puts on the baseline draw. That is not a
conservative choice; it is a units error, and it is the whole reason the lower rail reads "≈0 %".

**(b) The two rows also use different centres, visibly, in the same function.** `tool:37`:
`z = (need - DRAW_MEDIAN) / DRAW_SD` with `DRAW_MEDIAN = 1.001830`. `tool:42`: `zz = (need - 1.0) / sd`.
The fern row subtracts the measured median draw factor; the within-program rows subtract 1.0. The
numerator is `need - 1.001830 =` **+0.012611** under the first convention — equivalently **+1.2588 %** of
the program's own mean official score `2.582263 × 1.001830 = 2.586989` — against `need - 1.0 =`
**+0.014441** under the second, while the table's reference-point column says both are "program mean
(correct)". At the σ established in (d) that one difference is worth a factor **6.8×** in the answer, so
it is not second-order.

**(c) But the upper rail is the wrong σ too — it answers the conditional question.** fern's 0.538 %,
`CRS:3509`'s sd(ln L) = 0.5359 % and my 0.5263 % (n=5) all measure the spread of `L` **holding `cs`
fixed**: *given* a program that has already produced this `cs`, how much can a re-fire's baseline move
the official score. That is the right σ for "should I re-fire the submission I already have". It is the
wrong σ for the question §6.5c is actually asking — *"we submit a new program at our program mean, what
is P(record) per draw"* — because a fresh submission re-draws `cs` **and** `L` together, and they are not
independent. Separately, §6.5c's stated reason for discounting fern — *"fern's 0.538 % legitimately
carries between-program leakage that program-hashing removes"* (L957-958) — **cannot hold**: a quantity
with no candidate term in it cannot carry between-program leakage, and program-hashing has nothing to
remove. The corpus value at `CRS:3509`, computed over 1,204 receipts, agrees with fern's to **0.4 %**.

**(d) The predictive σ is directly measurable, and it is neither rail.** From the same five receipts,
sd(ln official) = **0.3728 %**. It is *smaller* than either sd(ln L) or the independence quadrature
`sqrt(0.2276² + 0.5263²) = 0.5822 %` because the two components are **negatively correlated**:
r(ln cs, ln L) = **-0.79** on those five points. The mechanism is mechanical, not statistical — the
official score is a within-session ratio of candidate to baseline timings, so a host that is slow during
one submission slows both legs and the common mode cancels. The check closes:
`sqrt(0.2276² + 0.5263² + 2(-0.79)(0.2276)(0.5263)) = 0.3735 %` against **0.3728 %** measured — the
correlation term is the whole gap. n=5 is thin, so the honest interval is the chi-square one:
**σ ∈ [0.223 %, 1.071 %]** at 95 %, 4 dof.

**(e) Recomputation, correctly centred and with the predictive σ.** Program mean official
`= 2.582263 × 1.001830 = 2.586989`; required move to `BAR` **+1.2588 %**; one-sided normal:

| σ used | what it measures | z | P(one draw ≥ bar) |
|---|---|---|---|
| 0.1860 % | replicate sd of `cs` | 6.77 | 6.5e-10 % ← §6.5c's lower rail |
| 0.2276 % | replicate sd of `cs` | 5.53 | 1.6e-6 % ← §6.5c's lower rail |
| **0.3728 %** | **measured sd(ln official), n=5 — the predictive σ** | **3.38** | **0.037 %** |
| 0.2230 % | its chi-square 95 % lower bound, 4 dof | 5.65 | 8.3e-7 % |
| 1.0710 % | its chi-square 95 % upper bound, 4 dof | 1.18 | **12.0 %** |
| 0.5359 % | sd(ln L), `CRS:3509` — the *conditional* σ | 2.35 | 0.94 % |
| 0.5380 % | fern's draw component (conditional) | 2.34 | 0.96 % ← §6.5c's upper rail |
| 0.5822 % | independence quadrature — rejected by r = -0.79 | 2.16 | 1.53 % |

So the σ defect alone is worth a factor **2.3 × 10⁴** (against the 0.2276 % rail) to **5.6 × 10⁷**
(against 0.1860 %), and the centring defect a further **6.8×**. Rails four to eight orders of magnitude
apart are not a bracket; they are one number and one artefact.

**This also refines my own §9.5.** F18's arithmetic substituted the corrected σ into §6.5c's *uncentred*
numerator (+1.4441 %) and reported z = 3.87, **P = 0.0054 %**. Centring on the program's own mean
official score — which is what "program mean (correct)" was supposed to mean — gives z = 3.38,
**P = 0.037 %**. My published figure was low by 6.8×. Recorded here rather than silently corrected.

**(f) The state file makes the same centring slip, and it is exactly reproducible.** `CRS:3537-3540`:

> **Per-draw record probability at the measured frontier is 0.748 %** (9/1203 empirical, 1 in 134;
> **0.671 % lognormal**), not the 1.2 % predicted at `cs = 2.58506`

That **0.671 %** is reproduced *exactly* by centring `L` on **1.0** rather than on its own measured
median: required `L = 2.616504 / 2.582286 = 1.013251`, `(1.013251 - 1) / 0.005359 = 2.4726 → 0.6705 %`.
Centring on `CRS:3509`'s own median 0.998597 gives `z = 2.7344 → 0.3124 %`. The printed figure is
therefore **2.15× optimistic** in its own convention. Worse, the same table's *"2.6202 → 50 %"* row is
**median**-centred — it is r104's `2.616504 / 0.998572` inverted (**r104:546-549**), and 1.0-centring
would print 60.4 % there, not 50 %. **The table mixes two centrings**, which is why its lognormal column
cannot be compared row-to-row.

**F19.** *§6.5c's `[≈0 %, 1.5 %]` per-draw bracket is not a disagreement between two methods. The lower
rail divides a required **draw factor** by the replicate sd of the **candidate** legs, discarding the
≈96 % of draw variance `CRS:3509` attributes to the baseline; the upper rail uses the **conditional** sd
of `L` at fixed `cs`, which answers "should I re-fire this submission", not "what does a fresh submission
draw". The predictive σ is measurable directly — sd(ln official) = **0.3728 %**, below the independence
quadrature because r(ln cs, ln L) = **-0.79** — and, centred on the program's own mean official score,
prices one draw at **≈0.04 %**, with an honest n=5 interval of **[≈0 %, 12 %]**. §6.5c's `[≈0 %, 1.5 %]`
is roughly the right width by accident and for the wrong reason. The successor must not carry "≈0 %"
forward as a rail: a lower rail of zero makes any draw-buying argument unfalsifiable in the flattering
direction, and it contradicts the ~1.5 % the same section spends at L923-926.*

**Disposition of the §6.5c decision is unchanged.** 0.04 % per draw, or even the 12 % upper bound, is
still not a licence to cut verification gates — the use the number is put to at L922-926 — and the
audit's recommendation there stands. What changes is that the number must be quoted as one estimate with
an interval, sourced to `sd(ln official)`, not as a bracket between two mislabelled σ's.

This is the same shape as F1 and F16: the correction is real, the direction of the correction is
flattering to the corrector, and the input was never re-derived from the receipt.

### 10.4 F20 — the crown moved, and every per-draw price in the state file is still calibrated to the retired one

**(a) Where the orphan `0.378 %` came from.** §4b's superseded cell and the §4c post-mortem attribute it
to narrative contamination, twice — once in §0 (L39-42, *"I had let the gap drift to whatever made the
story close"*) and once in the post-mortem itself (L726-728):

> §4b said **+0.378 %**. The true gap is **+0.4950 %** — 31 % larger. And 0.378 ≈ the 0.38 I had
> attached to delta 1, which is almost certainly where it came from: **I let the gap take the value that
> made the story close.**

That attribution is wrong, and provably so. The **retired** crown is `cc6ddc1` /
`c5b0a13c` = **2.61650354381456**, quoted at that precision in ≥8 places in the tree
(`CRS:203,1044,1331,2113,2266,3412,3541,5260,7099,7535,7781,8688`;
`research/RESEARCH_ARCHIVE_through-round-91.md:20,873,878,1140`;
`research/advisor-r93-corpus-mining/mine2_record_and_cv.py:70` and `mine3/mine4/mine5` likewise). Then:

```
2.60664969895906 × 1.00378 = 2.616502834821125
                  cc6ddc1  = 2.61650354381456      → agreement 0.000027 %
```

`+0.378 %` is the gap from our best-ever draw to the crown **as it stood when the cell was written**.
It was not story-fitted; it was **correct against a reference point that has since been retired**. That
matters for the handover: a self-diagnosis of "I let the number drift to fit the story" prescribes
narrative discipline, while the actual defect — a stale reference point transcribed forward without its
`as-of` — prescribes *dating every leaderboard constant*. The second is fixable by convention; the
first is not. Note also that the σ-multiple invariance L730-732 flags ("a wrong numerator over a wrong
denominator kept giving me the right-looking σ multiple") has the same root: both numerator and
denominator were correct as of different dates.

**(b) The crown that replaced it is 8 hours old, and the state file has not been told.** `brief:132-133`:

> | 1 | ggu77wt | `cdcd091` / `4ea72c3b` | **2.619553** | 203.937 | 5,314.295 |
> | 2 | a-github-name | `cc6ddc1` / `c5b0a13c` | 2.616504 | 202.837 | 5,314.658 |

`2.619553 / 2.61650354381456 - 1 = +0.1165 %`. The manifest **did** re-anchor (`BAR = 2.6195531094824`,
`tool:10`; L333). The state file did **not**: `CRS:3412` still reads *"Record still
**2.61650354381456**"*, and every per-draw price in `CRS:3511-3514` is built on it.

**(c) The state file predicted this exact failure and then filed it as a tail risk.** `CRS:1330-1348`,
round 116, written 02:1xZ today:

> **(1) The crown is a FIXED target, not a moving one.** Every EV table in this campaign (§0P.13) held
> the crown at 2.61650354381456. That assumption was never tested … **It is now tested and it holds** …
> receipts since the crown was set **73** … of those, above the crown **0** … ⇒ **the fixed-crown
> assumption in §0P.13 is sound.**

and `CRS:1362-1365`:

> Field-only draw rate is **0.51 receipts/h** ⇒ ~4.5 field draws remain. Rule of three on 0/33 gives a
> 95 % upper bound of 9.09 % per draw ⇒ **P(new crown) ≤ 34.7 %, point estimate ~0 %.** We plan against
> the fixed crown and treat a new one as a tail risk

The 34.7 % tail **fired**, somewhere between 02:14Z and the 10:06Z briefing snapshot. The same note also
states what a moving crown would cost: a real drift *"would have been a reason to discount every
P(crown) figure"* (`CRS:1351-1352`). Nothing downstream was discounted.

**(d) The whole `CRS` price table is the retired crown divided by the median draw.** `CRS:3511-3514`:

> P(record) per draw as a function of `cs`: 2.575633 → 0.415 %; **2.582286 → 0.748 %** (1-in-134);
> 2.585060 → 1.163 %; 2.588362 → 1.744 %; **2.590559 → 3.239 %**; 2.591868 → 4.153 %; 2.600 → 14.286 %;
> 2.610 → 34.551 %; **2.6202 → 50 %**

The `2.6202 → 50 %` row is not fitted; it is `r104:546-549`, verbatim:

> To beat `score = 2.616504` at the *median* draw `L = 0.998572` you need
> `cs >= 2.616504 / 0.998572 = 2.620246`

i.e. the 50 % column **is** the retired crown over the median draw: `2.616504 / 0.998597 = 2.620180`,
which is the printed `2.6202` to four decimals. Re-anchored on `2.619553` that point moves to
`2.619553 / 0.998597 =` **2.623233** (+0.1165 % of `cs`), and every row below it shifts. Recomputed in
the state file's **own** convention (§10.3(f): `L` centred on 1.0, sd 0.5359 %), which is how each old
column below reproduces its printed value:

| `cs` | old crown, state file's convention | re-anchored to `cdcd091`, same convention | discount |
|---|---|---|---|
| 2.582286 (`CRS:3512` row; our program mean is 2.582263) | 0.6706 % = the printed **0.671 %** | **0.354 %** | ÷1.89× |
| 2.583100 (§7 item 6's mean `cs`) | 0.791 % | **0.423 %** | ÷1.87× |
| 2.590559 (our best-ever `cs`, receipt `n1`) | 3.082 %, against the printed **3.239 %** empirical | **1.838 %** | ÷1.68× |
| 50 %-point | 2.620180 = the printed **2.6202** | **2.623233** | +0.1165 % of `cs` |

**(e) The internal consistency check that makes this airtight.** `CRS:3515` states its own local
elasticity: *"At our operating point **+0.1 % of `cs` multiplies p/draw by 1.56×**."* A crown rise of
+0.1165 % is that same move with the sign flipped, so it must divide p/draw by `1.56^1.165 =` **1.679×**.
Measured on my re-anchoring at that same operating point (`cs = 2.590559`): 3.082 % → 1.838 % =
**÷1.677×**. The elasticity the state file printed and the repricing done from the crown constants agree
to **0.1 %** — two independent routes to the same discount. Deeper in the tail the discount grows
(÷1.87-1.89× at `cs ≈ 2.5823`), and it is **not** an artefact of the centring defect in §10.3(f):
median-centring every row instead gives ÷1.77-2.00×, i.e. the same ≈1.7-2× either way.

**F20.** *The promoted crown rose `cc6ddc1` 2.61650354381456 → `cdcd091` 2.619553 (+0.1165 %) between
02:14Z and 10:06Z. The manifest re-anchored; `CURRENT_RESEARCH_STATE.md` did not, and its P(record)
table (`CRS:3511-3514`) is by construction the retired crown over the median draw (`r104:546-549`), so
**every per-draw and cumulative-EV figure a successor reads from the state file is optimistic by
≈1.7-1.9×** — at our best-ever `cs` it prints 3.239 %/draw where the same method re-anchored gives
≈1.8-1.9 %, and the state file's own elasticity at `CRS:3515` predicts that discount to 0.1 %. The same
file tested and blessed the fixed-crown assumption at 02:1xZ and priced a new crown as a ≤34.7 % tail
risk; that tail has fired. Separately, the orphan `+0.378 %` in the superseded §4b cell is the gap to the retired
crown to **0.000027 %**, so §4c's "I let the gap take the value that made the story close" mis-diagnoses
it: it is a stale-reference-point transcription, which is the defect still live in the state file and in
`mine2/3/4/5_*.py`.*

**Cheapest fix, for whoever holds the slot.** Two edits, no measurement: (i) at `CRS:3412` and
`CRS:3511-3514`, stamp the crown constant with its `as-of` and note the ÷1.7-1.9× discount, or delete
the table; (ii) in `research/tools/slot_holder_arithmetic.py`, replace `WITHIN_SD` in the `need`
comparison with the measured sd(ln official) and centre **both** rows on `DRAW_MEDIAN` (four lines,
`tool:37-44`). Neither
touches `Sources/`, `Vendor/`, or `benchmark.json`. I have **not** made either edit — this branch is
read-only by assignment, and both files are owned by others.

### 10.5 Net effect of the third addendum

Two findings, two self-corrections, one clean bill. **F19**: §6.5c's `[≈0 %, 1.5 %]` is not a bracket —
its lower rail divides a required **draw factor** by the replicate sd of the **candidate** legs, its
upper rail uses the **conditional** sd of `L` at fixed `cs`, and the predictive σ is measurable directly
as sd(ln official) = **0.3728 %** (below the independence quadrature because r(ln cs, ln L) = **-0.79**),
which prices one draw at **≈0.04 %** with an honest n=5 interval of **[≈0 %, 12 %]**; the §6.5c
*decision* is unchanged, the number carried forward must be. That recomputation also **corrects my own
§9.5**, which was low by 6.8× because it inherited §6.5c's uncentred numerator. **F20**: the crown moved
8 hours before the handover, the state file's entire per-draw price table is still calibrated to the
retired crown and is optimistic by ≈1.7-1.9× — a discount the state file's own elasticity at `CRS:3515`
independently predicts to 0.1 % — and the orphan `+0.378 %` is explained exactly, as a stale reference
point rather than narrative drift. **Self-correction to F18**: its mechanism was already at `CRS:3509`;
my contribution reduces to the 0-ppm identity `L = (base_D^0.75 base_P^0.25)/K` and an independent
96.04 % from five receipts — and that identity is what proves F19. **Clean bill**: none of the §6.6
currency constants reached `CURRENT_RESEARCH_STATE.md`, so F16's blast radius is two documents.

Running total as of §10: **20 findings, F1-F20**, of which **three** are
decision-grade for the successor — F1 (the `UNSOURCED` label is inverted), F19 (per-draw price has no
zero rail), F20 (the crown moved and the state file's EV table did not). No finding in §1-§9 is
withdrawn. (§11 adds F21 and carries the final total.)

---

## §11 Fourth addendum, 14:40Z — the round archives, and the draw factor nobody used (F21)

### §11.0 Authority and sources

Same clause of the assignment's stopping rule quoted verbatim in §10.0: *"If you exhaust the scope
early, do **not** invent GPU work. Extend the audit to `CURRENT_RESEARCH_STATE.md` and the round
archives instead, same four checks."* §10 took the state file; this section takes the round archives.
Still reading only: no GPU, no build, no benchmark, no `run_job`, no W&B run.

| tag | file | lines | md5 |
|---|---|---|---|
| `arc21:####` | `research/RESEARCH_STATE_ARCHIVE_through-round-21.md` | 6874 | `915230e2f54592a9bd27afbf7b19803d` |
| `arc28:####` | `research/RESEARCH_STATE_ARCHIVE_rounds-22-28.md` | 896 | `fccb7ec9f6ee136d6e735aa40aa3d875` |
| `arc91:####` | `research/RESEARCH_ARCHIVE_through-round-91.md` | 7601 | `8f65c7275dc30bece6508bccb0b94e9c` |

All three read at advisor head `6778867dc8579eff3302d49d064c2bc0cf60ead2`
(`git show 6778867d:research/<file>`), 15,371 lines in total. Recompute script for everything
numeric below: `research/tools/r127a_f21_draw_factor_from_r21_ledger.py` (committed on this branch), inputs transcribed from `arc21:5684-5695` only.

### §11.1 Clean bill: no §6.6 currency constant, and no retired-crown constant, reached the archives

Census over all 15,371 archive lines (counts are `grep -c` per file, `arc91`/`arc28`/`arc21`):

| string | hits | verdict |
|---|---|---|
| `0.00586` | 0 / 0 / 0 | absent |
| `12798`, `12,798` | 0 / 0 / 0 | absent |
| `4910.9` | 0 / 0 / 0 | absent |
| `8213`, `8,213` | 0 / 0 / 0 | absent |
| `8882` | 5 / 1 / 5 | **all coincidental** — substrings of `officialScore 2.58882784082067` |
| `2.60664970` | 0 / 0 / 0 | absent |
| `2.6195` | 0 / 0 / 0 | absent |
| `0.378` | 0 / 0 / 2 | **coincidental** — substrings of `score2.500378` (`arc21:2618`, `arc21:5694`) |
| `15.6` | 8 / 3 / 7 | none is a per-draw probability (t-statistic `arc91:1363`; a `T0b_qkv` share `arc28:621`; a section heading `R15.6` at `arc21:1324`) |

The `8882` pattern is the same boundary-hit artefact F16 documented in the live tree — e.g.
`arc91:1134` verbatim:

```
| **97a5090** | **morganmcg1 (us)** | **2.58882784082067** | **3e165fa** |
```

That is a score, not a µs/step. So **F16's blast radius remains two documents** (manifest +
slot-holder brief) and **F20's orphan `+0.378 %` never entered the archives** either.

`2.6165` does appear seven times in `arc91`, and every one of them is correct, because the archives
timestamp their claims. `arc91:20` verbatim:

```
Leaderboard re-checked round 88: current best still **2.61650354381456 @
```

and `arc91:1140` marks it `← **live frontier**` — true of round 88. This is the honest form of the
constant F20 flags: the defect in `CRS:3412` is not that it holds `2.61650354381456` but that it
holds it in the present tense ("Record still …") in the file a successor reads as current state. The
archives need no edit.

### §11.2 F21 — the draw factor has been measured twelve times, across twelve different programs, and both rails of §6.5c ignored it

`arc21:5681` heads a ledger of our own account's receipts:

```
### Full `morganmcg1` receipt ledger (18 receipts: 13 on 2026-08-04, 5 since)
```

Twelve of those rows carry full metrics. Verbatim, `arc21:5684-5695`:

```
07:53 27b9c7c6 T4.3530 S 98.153 ns2.51567 draw0.992674 score2.497243
09:30 f8502e12 T4.3704 S 97.622 ns2.51417 draw0.988626 score2.485577  } pre-harvest trio
10:02 71586bcf T4.3828 S 97.513 ns2.51065 draw1.002111 score2.515950  } (our best SCORE)
10:26 f3cda678 T4.3621 S 97.998 ns2.51374 draw0.998094 score2.508953  }
10:49 5d522d6a T4.3475 S 97.841 ns2.52060 draw0.988443 score2.491470  } C0 control, n=4
11:15 5e0e9cd1 T4.3637 S 98.011 ns2.51302 draw0.994854 score2.500092  } pooled mean
11:38 c210d200 T4.3428 S 97.973 ns2.52110 draw0.997477 score2.514743  } ns 2.519365
14:16 0c21dc18 T4.3181 S 98.029 ns2.52973 draw0.985211 score2.492321  } Y = FRONTIER
14:48 2dce5912 T4.3267 S 97.696 ns2.52967 draw0.985388 score2.492708  } mean ns 2.529702
15:10 7a5a1e08 T4.3612 S 98.347 ns2.51083 draw0.998492 score2.507043  fern #24 (closed)
15:34 1feeabc8 T4.3394 S 97.932 ns2.52274 draw0.991135 score2.500378  4th CONTROL (see §E)
16:06 ff29f5c2 T4.8324 S103.568 ns2.30788 draw0.989388 score2.283393  tanjiro instrument A
```

**Column identity first (check 1).** `ns` is the candidate score `cs`, `score` is the official score,
and `draw` is their ratio: `score/ns` reproduces every printed `draw` to **≤ 1.9 ppm** on all twelve
rows (worst `+1.85 ppm`, `ff29f5c2`; the residual is rounding of the 6-digit printed inputs). So this
column *is* the code-free factor `L = official/cs` of my §10.2 identity, measured twelve times, on
twelve different programs, on one day, on the ranked host. Neither rail of §6.5c cites it.

**What it says.** Over all twelve programs, `sd(ln L) = 0.5568 %`, 11 dof, χ² 95 % interval
**[0.3944 %, 0.9453 %]**. Dropping the one deliberately-slowed instrument tree (`ff29f5c2`, `ns`
2.30788): `0.5738 %`, 10 dof, [0.4009 %, 1.0069 %]. Set beside the three values already in
circulation:

| quantity | value | dof |
|---|---|---|
| fern's draw sd (§6.5b, `CRS:3509` prints 0.5359 %) | 0.538 % | — |
| my conditional `sd(ln L)`, five ranked nulls (§10.2) | 0.5263 % | 4 |
| **this ledger, 12 distinct programs** | **0.5568 %** | **11** |
| this ledger, 11 programs (instrument dropped) | 0.5738 % | 10 |
| r103 replicate `sd(ln cs)` — the §6.5c lower rail | 0.2276 % | 4 |

**Consequence for F19, and it is the load-bearing sentence of this section.** §6.5c's stated ground
for discounting fern's 0.538 % is *"between-program leakage that program-hashing removes"*. §10.3
refuted that algebraically — `L` contains no candidate term, so it cannot carry program leakage. This
ledger refutes it *empirically*: it is the most "leaky" corpus available — twelve genuinely different
programs whose `cs` spans 2.30788 to 2.52973, an 8.8 % range, one of them a deliberately slowed
instrument — and its draw-factor dispersion is **0.5568 %**, i.e. the same 0.53-0.57 % band, with the
0.2276 % lower rail nowhere near its 95 % interval. Program identity contributes nothing measurable:
`corr(ln cs, ln L) = +0.106`, `t = 0.34` on 10 dof.

Two honest caveats on that correlation, because it is fragile. It is leverage-dominated by
`ff29f5c2`; over the eleven comparable programs it is **−0.777**. Both signs are hostile to the
§6.5c argument, which needs a *positive* program-linked term in `L` to justify shrinking fern's
number — but the fragility means the algebraic identity, not this correlation, is what carries F19.
The second caveat is the more interesting one: −0.777 on eleven programs independently reproduces the
**−0.79** I measured on the five ranked nulls (F18, §10.3). That is the correlated-quadrature
mechanism — official is a within-session candidate/baseline ratio, so common-mode host slowdown
cancels — showing up in a second corpus, seven rounds older, with no receipt in common.

**What does not change.** The predictive σ for re-firing a *fixed* program is still the directly
measured `sd(ln official) = 0.3728 %` (n=5, §10.3), not 0.5568 %: this ledger corroborates the `L`
rail, not the total. F19's price is therefore unchanged — required move `+1.2588 %` from the program's
own mean official score, `z = 3.38`, `P ≈ 0.037 %` per draw, honest 95 % interval `[≈0 %, 12 %]`. What
changes is the strength of the evidence under it: the rail that F19 argues *is* the right order of
magnitude now has 11 dof of independent support instead of 4.

### §11.3 Caveat with teeth — the draw factor's centre is era-specific, and no per-draw table says so

Mean draw in this ledger (twelve receipts, all on 2026-08-04) is **0.992644**. The median-draw
constant that `CRS`'s P(record) table divides by — and that F20's arithmetic uses to reproduce the
printed `2.6202` — is **0.998597**. The centre has moved

```
0.998597 / 0.992644 = 1.005997  ->  +0.5997 %
```

between the two eras: **1.6× the predictive σ of 0.3728 %**. This is not an arithmetic error in
anyone's table; it is a missing uncertainty. Any per-draw probability computed against a fixed median
draw inherits an era-drift term larger than the dispersion it quotes, and every such table in the
corpus prints the constant undated. Check 3 in spirit: a constant measured in one era is being used
as a property of the instrument.

### §11.4 Recommended edits (I applied none — read-only branch)

1. **`research/maple_endgame_handoff_manifest.md` §6.5c**, the sentence discounting fern's 0.538 % as
   between-program leakage. Replace with: *"fern's 0.538 % is confirmed, not shrunk: the draw factor
   `official/cs` was measured on 12 distinct programs in the 2026-08-04 ledger
   (`RESEARCH_STATE_ARCHIVE_through-round-21.md:5684-5695`) at sd 0.5568 %, 11 dof, 95 % CI
   [0.394 %, 0.945 %]; `cs` spans 8.8 % across those programs and `corr(ln cs, ln L)` is not
   distinguishable from zero. The 0.1860-0.2276 % replicate sd of `cs` is not a rail on the draw
   factor at all."*
2. **Every per-draw table** (manifest §6.5/§6.6, `CRS:3520-3540`): date-stamp the median-draw
   constant — `0.998597 (measured <date>; the 2026-08-04 ledger gives 0.992644, +0.60 % apart)`.
3. **The archives themselves: no edit.** They timestamp their constants correctly (§11.1).

### §11.5 Net effect of §11

One finding (**F21**), one clean bill (currency and orphan-constant propagation into 15,371 archive
lines: none), one dated caveat. Running total for the whole audit: **21 findings, F1-F21**, of which
three remain decision-grade for the successor — F1 (the `UNSOURCED` label is inverted), F19 (the
per-draw price has no zero rail and is centred on the wrong point), F20 (the crown moved and the state
file's EV table did not). **No earlier finding is withdrawn, and F19 is strengthened**: the rail it
depends on is now measured on 12 programs and 11 dof rather than 5 receipts and 4. (§12 adds no
findings and audits nothing new — it is the work order for applying everything above, with all 25 edit
targets re-verified at head.)

**Updated after §14: 22 findings, F1–F22**, and **four** remain decision-grade — F22 is F1 restated as
an instruction ("never price a delta with 0.00586 %/µs") on the one page a successor reads first,
`research/MAPLE_TO_SLOT_HOLDER_BRIEF.md`, which was outside every earlier section's scope. The work
order is 34 rows after §14 (28 A-rows + B1–B6).

**Updated after §15: 23 findings, F1–F23**, and **five** are decision-grade. F23 is the same shape as
F22 one step further out: the brief tells the reader to *run*
`research/tools/account_draw_record.py` (`brief:60`), and that program prints
`model, normal tail 0.95 %` / `model, empirical tail 1.48 %` as the per-fire price of a draw with no
mention of the measured 0.04 %, while asserting that a ≤2.83 % ceiling corroborates it. The work order
is **36 rows** after §15 (28 A-rows + B1–B6 + C1–C2) over **five** files. §15 also closes the scope
question the earlier sections had assumed: the brief's reading list names exactly four artefacts, the
manifest names a fifth tool, all six are now read, and the census of every other file carrying a
retracted constant is archival. One near-miss is recorded there rather than fixed: two independent
tools print `1.48 %` for a bare re-fire from unrelated inputs, which reads as replication and is not.

---

## 12. Applier's work order — every recommended edit in one place, each target verified present at head

### §12.0 What this section is, and what it deliberately is not

The assignment's deliverable item 5 is "**Recommended manifest edits** — exact section, exact
replacement text. I will apply them." Four sittings later those edits are spread over 1,400 lines:
twelve in §6, one in §8.3, one in §9.3, two in §10.4, two in §11.4. Whoever applies them should not
have to reconstruct that list from the prose, and should not have to trust that the line numbers still
resolve. So §12 is a **work order**: one row per edit, in apply order, with the file and the line at
the advisor head this audit read, the finding it comes from, and the section that holds the exact
replacement text.

**No new claims are made here.** Every number, quote and disposition below is already published in
§1-§11; §12 adds only collation, apply order, and one mechanical guarantee:

> Every edit target listed below **still exists, at the line cited, in
> `6778867dc8579eff3302d49d064c2bc0cf60ead2`** — the advisor-branch head at 12:59Z, which is
> still the head at 14:40Z (`git ls-remote origin refs/heads/codex/mlxfast-maple-20260804-advisor`).
> Checked mechanically, not by eye: `research/tools/r127a_s12_edit_target_check.py` reads each file
> with `git show <sha>:<path>` and asserts a verbatim substring on the cited line. Output at 14:41Z:
> **25/25 PASS**, exit 0. If a later head moves a target, that script says which one, in one second,
> and it needs no network beyond the local object store.

I have applied **none** of these edits. This branch is read-only by assignment, and `CURRENT_RESEARCH_STATE.md`
and `research/tools/slot_holder_arithmetic.py` are owned by others.

### §12.1 The work order

Tiers: **D** = decision-grade (a successor who reads the unedited text will price a decision wrongly);
**C** = correctness of a banked number, no disposition change; **P** = provenance label or citation.

| # | target at `6778867d` | tier | edit | replacement text | finding |
|---|---|---|---|---|---|
| A1 | `manifest:999-1004` (§6.6 currency table) | **D** | Replace the four rows; add the two-hosts-×-two-quantities paragraph above them. Per §8.1, prefer **adding** the `D₁₂₈` row and labelling every row `(host, harness, step count)` over deleting the 8882/8213 rows — their arithmetic is right for their own denominators | §6.1 | F1 |
| A2 | `manifest:1008-1014` (§6.6 consequence (a)) | **D** | Replace the paragraph: the `0.00586 %/µs` constant is **sourced and correct** for the scored 128-step local harness; drop `UNSOURCED`/"Do not reuse" | §6.2 | F1 |
| A3 | `manifest:1029-1033` (§6.6 requirement table) | **D** | Restore `44 / 85` as the local column (`0.26/0.005860 = 44.4`, `0.50/0.005860 = 85.3`); keep the ranked column 17/32/82; label the 8882/8213 columns by harness | §6.3 | F1 |
| A4 | `manifest:1035-1036` | **D** | Apply **with A3 or not at all**. The sentence is backwards: the retired 44/84 column was right to within rounding, and the 31/59 that replaced it sets the bar **≈30 % low — the flattering direction** | §8.1 | F1 |
| A5 | `manifest:1041-1046` (§6.6 closing) | C | Replace the last clause: the +0.50 % target needs **85** local µs/step against a phantom band topping out at ≈64 | §6.4 | F1 |
| A6 | `manifest:1048-1052` (§7-item-2 reprice) | C | `0.75 × 350/12798 =` **2.05 %**, not 2.94 % | §6.5 | F1 |
| A7 | `manifest:1054` ("Rule for reuse") | P | Name the **harness and step count**, not only the host: one host carries two step lengths (`T`, `D`) and two denominators (128, 1023) | §6.6 | F1 |
| A8 | `manifest:819-820` (§6.5) | **D** | Same inversion as A4, second copy. Delete the clause superseding 44/84 with 31/59 | §8.1 | F1 |
| A9 | `manifest:466-468` (§5, o_proj) | C | **−35 µs/step** (#718 corrected); the −82/−80/−79.4 renderings are superseded | §6.7 | F5 |
| A10 | `manifest:241` (§4 row 4) | C | `−0.282 % of the decode step = −0.135 % of score` | §6.8 | F6 |
| A11 | `manifest:481` (§5) | C | Same string, second copy — apply both or neither | §6.8 | F6 |
| A12 | `manifest:416` (§4c) | P | "routed-wall replication" → "routed-**expert** measurement": #731 is a different kernel and a disjoint dispatch site from delta 1 | §6.9 | F7 |
| A13 | `manifest:258` (§4a/§4b banner) | P | Delete "as much as −0.14 % on edward's routed-wall measurement (#731)" — that bound belongs to the routed kernel, not to delta 1 | §6.9 | F7 |
| A14 | `manifest:321` (§4b DO-NOT-LAND cell) | C | Restore §4c's hedge in the row an owner acts on: isolated leg **+4.73 ± 0.52 µs/step**, wall arm null `[−19.33, +17.86]` ⇒ `|Δscore| ≤ 0.11 %` | §6.10 | F8 |
| A15 | `manifest:239` (§4 row 2) | C | delta 2 is **+0.062 % of score** (seed elasticity 0.362, not the bare 0.25 prefill weight); still excluded | §6.11 | F9 |
| A16 | `manifest:503` (§5) | C | Same, second copy | §6.11 | F9 |
| A17 | `manifest:157-158` (§1 operating point) | C | Lead with the measured `mean_D = 4910.9 µs`; note the `S`/`T` pair implies 5087 µs and r-ideas gives 4908.372 (3.6 % spread); σ from the stated `S`/`T` is **15.03 %**, not 14.98 % | §6.12 | F10 |
| A18 | `manifest:954` (§6.5c bracket, "≈0 %" row) | **D** | Print σ with its interval and **stop using the replicate sd of `cs` as a rail on a draw factor**; the lower rail is not a rail (F19). Re-price the row from the directly measured `sd(ln official) = 0.3728 %` centred on the program mean: **P ≈ 0.037 %, honest 95 % interval [≈0 %, 12 %]** | §8.3 + §10.3 | F15, **F19** |
| A19 | `manifest:908` (§6.5c, fern discount) | **D** | Replace the between-program-leakage sentence with the 12-program ledger result (`sd(ln L) = 0.5568 %`, 11 dof, CI `[0.394 %, 0.945 %]`; `cs` spans 8.8 %; `corr(ln cs, ln L)` indistinguishable from zero) | §11.4 item 1 | **F21** |
| A20 | `CRS:3412` | **D** | "Record still **2.61650354381456**" is the **retired** crown (superseded by `cdcd091` 2.619553 at ≈02:14Z, `brief:132-133`). Stamp it `as-of`, or delete | §10.4 | **F20** |
| A21 | `CRS:3511-3514` (P(record) table) | **D** | The table is the retired crown over the median draw (`2.616504/0.998597 = 2.620180`), so every per-draw figure is optimistic by **≈1.7-1.9×**. Re-anchor on `BAR = 2.6195531094824` or delete the table | §10.4 | **F20** |
| A22 | `CRS:3509` | C | Date-stamp the median draw: `0.998597 (measured <date>; the 2026-08-04 ledger gives 0.992644, +0.60 % apart — 1.6× the predictive σ)` | §11.4 item 2 | F21 |
| A23 | `tool:35-36` | **D** | Comment that `need = BAR / OUR_PROGRAM` is a **draw factor** (`OUR_PROGRAM` is a `cs`, `BAR` an official score) — that is why a `cs` replicate sd cannot be its σ | §10.4 | **F19** |
| A24 | `tool:37-44` | **D** | Replace `WITHIN_SD` in the `need` comparison with the measured `sd(ln official)`, and centre **both** rows on the program mean. Four lines | §10.4 | **F19** |
| A25 | `manifest:872-874` (§6.5b heading) | P | Mark "primary source not in tree (PR #686, closed unmerged; `research/fern-r109f-interim-1200Z.md` absent at head)" and point at §9.5, whose route to the same conclusion is entirely in-tree. **The conclusion survives; the citation does not** | §9.3 | F17 |

### §12.2 Apply order and the three couplings that matter

1. **A3 with A4, and A10 with A11, and A15 with A16.** Each pair is the same quantity written twice.
   Applying one of a pair leaves the document self-contradicting, which is worse than leaving both.
2. **A1-A8 are one edit in seven places.** They are all F1. If only one thing is applied from this
   whole work order, apply A2 + A3 + A4: they are what stops the next campaign from screening against
   a bar set ≈30 % too low in the flattering direction.
3. **A18, A19, A23, A24 are one edit in four places** — F19 plus F21. Order matters: A19 removes the
   stated reason for discarding fern's number, A23 names the random variable, then A18 and A24 re-price
   with the right σ and the right centre. Doing A18 first leaves the tool disagreeing with the
   document it is supposed to reproduce.
4. **A20 and A21 travel together**, and both belong to a file this branch does not own.

Not in this work order, deliberately: everything the advisor closed before 12:45Z (σ = 0.49 %, the
0.378 % gap, the per-draw success table, delta 1 itself, §6.5/§6.5b/§6.6 probability rows), the
`8919/8567` pair (maple-alphonse, #744), and the archives — §11.1 gives them a clean bill and they
need no edit because they timestamp their constants.

### §12.3 What is left unresolvable, restated in one place

The `UNSOURCED` list a successor should not spend time re-hunting: `research/fern-r109f-interim-1200Z.md`
(named source of §6.5b, absent at head, F17); `N-K3-AT-DRAM-ROOF` (§7 item 4, zero hits outside the
manifest, names no PR, F17); the `1.012550 / 1.024492` pair (appear nowhere, F17); the two `dc437b0e`
tree digests (not local git objects — the tree needs the r106e rebuild, §9.5); and `8882`'s attribution
to a *scored* denominator (the figure is real and nezuko's, the 1023-step denominator is not a scored
one, F16).

---

## §13 The work order as an executable, verified patch

§12 is prose, and prose work orders decay: the next reader has to re-find 34 spans by hand in three
documents plus a script, at line numbers that move the first time anybody edits above them. So §12 is
also shipped as a **data-driven applier** with baked-in content guards.

`research/tools/r127a_s13_apply_work_order.py` — **36 rows**: 28 A-rows, one per §12 edit, six
B-rows (B1–B6) added by §14 for `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md`, and two C-rows (C1–C2) added
by §15 for `research/tools/account_draw_record.py`. Each row carries the tier
(D/C/P), the finding it discharges, the target `file:line`, the exact replacement text, and an **md5 of
the text it expects to find** at advisor head `6778867dc8579eff3302d49d064c2bc0cf60ead2`. Two edit
kinds: `span` (replace whole lines) and `subs` (exact substring replacements on one named line). It is
idempotent — a row whose target already reads as the replacement reports `already applied`, not
`DRIFT` — and it applies per file in descending line order, so line drift between rows cannot happen.

```
python3 research/tools/r127a_s13_apply_work_order.py            # --check: verify all 36 guards
python3 research/tools/r127a_s13_apply_work_order.py --emit-patch > wo.patch
python3 research/tools/r127a_s13_apply_work_order.py --emit-patch --tiers D          # decision-grade only
python3 research/tools/r127a_s13_apply_work_order.py --emit-patch --only A2,A3,A4    # minimum useful set
python3 research/tools/r127a_s13_apply_work_order.py --emit-patch --only B1          # one row, biggest reader
python3 research/tools/r127a_s13_apply_work_order.py --apply --root /path/to/worktree
python3 research/tools/r127a_s13_apply_work_order.py --print-guards                  # re-bake after drift
```

`--apply` refuses to run without an explicit `--root`, because this branch does not own
`maple_endgame_handoff_manifest.md`, `CURRENT_RESEARCH_STATE.md`, `slot_holder_arithmetic.py`,
`MAPLE_TO_SLOT_HOLDER_BRIEF.md` or `account_draw_record.py`. The five pre-emitted patches are committed
instead:

| artifact | rows | lines | what it is |
|---|---|---|---|
| `research/artifacts/r127a/work_order_all.patch` | 36 (17 D, 12 C, 7 P) | 510 | the whole work order |
| `research/artifacts/r127a/work_order_D_tier.patch` | 17 | 321 | decision-grade only (F1, F19, F20, F21, F17) |
| `research/artifacts/r127a/work_order_A2_A3_A4.patch` | 3 | 54 | the minimum useful set: stop screening against a bar ≈30 % too low |
| `research/artifacts/r127a/work_order_B1_brief_trap.patch` | 1 | 22 | if you fix one thing: the brief's trap 4, which is F1 as an instruction (§14) |
| `research/artifacts/r127a/work_order_refire_price_coupled.patch` | 3 (B2, C1, C2) | 58 | the re-fire price in both places that quote it: the brief's §2 table and the program its §2a says to run (§15) |

**Verification performed** (worktree `git worktree add --detach /tmp/r127a_head3 6778867d…`, i.e. a
pristine advisor head, then removed; re-run in full after the B-rows and again after the C-rows):

1. `--check` → **36/36 targets verified** against the baked guards.
2. `git apply --check -p1` → **CLEAN** for all five patches independently.
3. Full patch applied; `git status` showed exactly the five intended files modified.
4. The patched `research/tools/slot_holder_arithmetic.py` **runs** and prints the corrected block:
   `z (measured official sd) 3.383 -> normal p = 0.036 %` beside fern's `z = 2.344 -> 0.95 %` and the
   12-programme `z = 2.265 -> 1.18 %`. Section E's `ratio of odds ours/theirs: 3.3x` still means what
   it meant — the added σ is reported separately and does **not** displace fern's σ in the sections
   that consume it downstream.
5. Patched prose read end-to-end at §0 L62, §1, §4/§4a/§4b/§4c, §5, §6.5/§6.5b/§6.5c, §6.6, §7 and
   `CRS:3505-3525` for self-contradiction.

**Step 5 found three more copies**, now rows A19b/A19c/A19d, which is the point of doing this
mechanically rather than by hand:

- **A19b** (`manifest:958-962`) — a *second* statement of the "between-program leakage" discount and of
  the `[≈0 %, 1.5 %]` bracket, four lines below A18's table. Patching only A18 left §6.5c retracting
  the bracket in a table and re-asserting it in the paragraph underneath.
- **A19c** (`manifest:896-898`) — the §6.5b retraction still told a successor to "plan against
  `[≈0 %, 1.5 %]`".
- **A19d** (`manifest:62`) — §0's executive summary carried a *third* copy, and §0 is the one section a
  successor is guaranteed to read.

That is F19's own lesson turned on itself: a bracket quoted in four places is four edits, and the only
reliable way to find copies two through four is to patch, read the result, and look for the document
contradicting itself. It is also rule 14 (§6.5c: "when you correct a reference point, recompute every
row that shares it, in a script, in one pass") applied to prose rather than to arithmetic.

**Two coherence fixes made while doing this**, both worth naming because they are the kind of thing a
prose work order silently gets wrong:

- A24's first draft replaced fern's σ with the measured one in the module-level constant, which
  silently changed section E's odds ratio and section F's cumulative table. Fixed: `p_norm` still comes
  from `DRAW_SD`, and the measured-σ figure is reported as a separate line.
- A21's first draft cited the elasticity sentence as `CRS:3515`, which is correct at head and **wrong
  the moment the patch lands** (it moves to 3521). Replaced with a content-based reference.

**What this does not do.** It does not touch `Sources/`, `Vendor/` or `benchmark.json`; it runs no
build, no benchmark and no GPU; and it does not write to the five target files from this branch. If
the advisor branch has moved past `6778867d`, `--check` will name every drifted row rather than apply a
stale edit, and `--print-guards` re-bakes the guards in one pass.

## §14 Fifth addendum, 15:20Z — F22: the one page a successor reads first was never audited

Everything above audits the manifest, `CURRENT_RESEARCH_STATE.md`, the archives and
`slot_holder_arithmetic.py`. It does not audit `research/MAPLE_TO_SLOT_HOLDER_BRIEF.md` (219 lines at
head `6778867d`) — and that is the document whose entire purpose is to be read first by whoever holds
the slot. Auditing it now gives **F22**, which is not a new error so much as the worst *form* of two
already-found ones: in the brief, F1 appears as a **prescription**.

**F22 (decision-grade). `MAPLE_TO_SLOT_HOLDER_BRIEF.md:181-183` instructs the reader to price local
measurements ≈30 % too low, in the flattering direction.** Verbatim at head:

```
4. **Never price a delta with 0.00586 %/µs.** That currency is UNSOURCED and implies a 12798 µs step
   that no harness we ran reproduces. Measured currencies: **0.01527 %/µs** ranked (4910.9 µs/step),
   **0.00845 %/µs** local `--local-submit` (8882), **0.00913 %/µs** bench host (8213). §6.6.
```

Every number in that trap is real; the inference is inverted. All four currencies are the *same*
formula — decode's score weight over the scored denominator, `0.75 / D` — evaluated at four different
`D`, which is checkable in one line each: `0.75/4910.9 = 0.01527`, `0.75/12798 = 0.00586`,
`0.75/8882 = 0.00845`, `0.75/8213 = 0.00913`. So the question is only *which `D` the score divides
by*, and §2/F1 answered it from source: `D = S/decodeSteps + T` with `includes_seed_prefill=true`
(`LagunaRuntimeLocalIterate.swift:767-769,776`), at the scored **128**-step setting ⇒
`D₁₂₈ ≈ 12 798 µs` locally. 8882 µs is the same harness at **1023** decode steps — a step count the
score never uses — and 8213 µs is a step-only `T` with the 512-token seed dropped. 0.00586 is
therefore the *correct* local currency and is sourced; "UNSOURCED" is exactly backwards.

The cost of the instruction, not of the belief: a reader who obeys trap 4 screens local µs/step wins
at 0.00845 %/µs and so demands **31 / 59** local µs/step for +0.26 % / +0.50 % of score, where the
truth is **44 / 85** (and 215 for +1.26 %). That is a bar ≈30 % too low on the side that lets a
candidate through — the one direction that costs a draw. This is the same arithmetic as F1/A2–A4 in
the manifest, but the manifest states it as a belief a reader may check, while the brief states it as
a rule a reader is asked to obey without checking. Row **B1** and
`research/artifacts/r127a/work_order_B1_brief_trap.patch` (22 lines, one row) rewrite the trap into
"price a delta in the currency of the harness *and the step count* that produced it", with all four
`0.75/D` values and both requirement columns.

**F22b. The brief's §2 and §3 price draws on the pooled σ (F19/F21 again), and §3 is a screening
table.** `:30-34` is the per-draw table (`≈0 %` from a replicate sd of `cs`, `0.95 %` from fern's
pooled 0.538 %, `1.48 %` "← upper bound, carries between-program leakage") followed at `:36` by
**"Plan against `[≈0 %, 1.5 %]` per draw."** — the **fifth** copy of the bracket that §13/A18–A19d
retired, restated a sixth time at `:151` as "that draw is worth ≤1.5 %", and both of them in the
highest-traffic document in the tree. `:85-91` then prices candidate gains from the same pooled σ:

| real gain | brief `:85-91` (pooled sd 0.538 %) | measured σ 0.3728 %, n = 5 (F19) | optimism |
|---|---|---|---|
| 0 (re-fire) | 0.95 % (emp. 1.48 %) | **0.04 %** | 24× |
| +0.26 % | 3.2 % | **0.38 %** | 8.4× |
| +0.50 % | 8.0 % | **2.1 %** | 3.7× |
| +1.00 % | 31.7 % | **24.6 %** | 1.3× |
| +1.26 % | 50.0 % | **50.1 %** | 1.0× |

(Same formula the patched `slot_holder_arithmetic.py` uses: `z = (need/(1+g) / DRAW_MEDIAN − 1)/σ`,
`need = 2.6195531094824/2.582263 = 1.014441`, `DRAW_MEDIAN = 1.001830`. The re-fire row reproduces the
tool's `p = 0.036 %`.) The two tables agree exactly where a candidate is already big enough to be even
money and diverge by up to 24× where the real decisions are — small gains and bare re-fires. The
brief's own closing line, `Do not let anyone tell you a +0.5 % candidate is a coin flip; it is 8 %`
(`:94`), is right in spirit and 3.7× optimistic in fact: it is 2 %. Rows **B2** (`:30-36`), **B5**
(`:85-94`, which also adds the missing **local** µs/step column 44 / 85 / 171 / 215 so the table can be
used against a local harness at all), **B3** (`:97`) and **B4** (`:65`) discharge it; **B6** (`:151`)
re-prices the last draw's value in the "must not skip the gates" argument. Note what does *not*
change: every conclusion the brief draws from these numbers — gates over draws, handover over
candidates, a draw-count change worth more than anything else on the page — survives, and three of the
six rows only *harden* it, because a draw worth 0.04 % is even less worth gambling than one worth 1.5 %.

**Clean in the brief, checked here** (so a successor does not re-litigate it): `:17`'s bar
`2.6195531094824` is already the re-anchored crown, i.e. F20 landed here before it landed in
`CURRENT_RESEARCH_STATE.md`; §3's ranked-host column **17 / 32 / 65 / 82** is correct
(`1.00/0.01527 = 65.5`); the model-free **0/106 official draws ⇒ P(one draw ≥ bar) ≤ 2.83 %**
(rule of three, `:64`) is assumption-free and F19's 0.04 % sits comfortably inside it; `:74-79`'s
"gate insurance is worth ≤7.5 %" is expressed as a *fraction of one draw's value* and so is invariant
to the per-draw re-pricing above; and `:215`'s note that the 8919 µs figure has no primary source is
alphonse's open item (#744), not mine to close.

**Why this is the last finding rather than the first.** The brief is 219 lines and reads as a summary,
so it was easy to treat as derived from the manifest and therefore already covered. It is not derived:
it is *edited*, independently, and the editing is what converted F1 from a mispriced constant into a
"never do this" rule. The general lesson for the next audit, and it is cheap: **audit the shortest
document first**, because errors are compressed there, stated imperatively, and read by everyone.

## §15 Sixth addendum, 15:45Z — F23: the brief tells a successor to run a program, and the program still quotes the retracted price

§14 ended by saying the shortest document should be audited first. Doing that raised the obvious next
question, which the 34-row work order had assumed rather than checked: **is "four target files" the
whole surface?** The work order's scope was assembled by walking the document tree Maple happens to
have written. A successor does not walk a tree; a successor reads the one page they were handed and
does what it says. So the completeness test is not "which files mention these numbers" but **"which
files does the handover instruct the reader to open"** — and that list is written down, in the brief,
in two passages. Verbatim at head, `MAPLE_TO_SLOT_HOLDER_BRIEF.md:4-6` and `:59-60`:

```
Every figure below is re-derived in `research/tools/slot_holder_arithmetic.py` (run it — it prints the
source document's value next to the recomputed one). Depth, provenance and the five errors I made
getting here are in `research/maple_endgame_handoff_manifest.md`; section pointers are given per line.
```

```
`research/receipts/account_submissions_1254Z.tsv` and reduced by
`research/tools/account_draw_record.py` (run it):
```

Those are the only four artefacts the brief points at (`git grep -nE 'research/|\.py|\.tsv'` over the
brief returns exactly lines 4, 6, 59, 60), and **§1–§14 had read three of them**: the manifest
(§1–§10), `slot_holder_arithmetic.py` (§9, rows A23/A24) and the brief itself (§14). The TSV is data,
not claims, and was read in §9 to recompute the record. The fourth —
`research/tools/account_draw_record.py`, flagged **"(run it)"**, i.e. presented as live guidance and
not as an archive — was in nobody's read set: not in §1–§14, not in the A/B work order, not in the
advisor's own pre-12:45Z closures. It is 130 lines and it carries the retracted price.

**Defect 1 (row C1, D-tier, F19), `research/tools/account_draw_record.py:108` at `6778867d`:**

```
    for p, name in ((0.0095, "model, normal tail"), (0.0148, "model, empirical tail")):
```

The two lines under it multiply each `p` by `(1 − failure rate)` and print the result as "the real
per-fire value". So the program a successor is told to run prints **0.95 % and 1.48 %** as *the* price
of one draw, with no mention of the measured figure at all — F19's `sd(ln official) = 0.3728 %` over
the n = 5 replicate group `dc437b0e` puts a bare re-fire at **0.0367 %**, 26–40× lower. This is the same
defect as B2 (§14) in the brief's §2 table, one hop further out, and it is worse here in one respect:
a table on a page can be read sceptically, whereas a program's output is normally trusted as *computed*.
Nothing in this program computes 0.0095 or 0.0148; they are typed-in constants imported from fern's
pooled draw sd.

C1 is non-destructive, the pattern B4 established: it adds the measured point estimate as the first
row and keeps fern's two as explicitly-labelled rails.

A `subs` row on line 108, guard `48ee6f014a488320b02404eff3970f90`:

```
((0.0095, "model, normal tail"), (0.0148, "model, empirical tail"))
  ->  ((0.000367, "measured sd, F19"), (0.0095, "fern sd, normal tail"), (0.0148, "fern sd, empirical"))
```

Every name is ≤ 24 chars, so the `{name:<24}` column alignment in the line below survives untouched.

**Defect 2 (row C2, P-tier, F19), `:118-119`:**

```
    print("  Brief sec.2's model-based 0.95%-1.48% sits inside that bound, so the model")
    print("  survives a check that assumes no distribution at all. Anything like the")
```

Two problems in one sentence. (a) It cites "Brief sec.2" for figures that **B2 replaces**, so the
moment the work order lands the citation dangles — the coupling between C1/C2 and B2 is exactly the
A18↔A19 coupling, and is now written into `APPLY_ORDER_NOTES` so a partial application cannot leave
the page and the program disagreeing. (b) The inference is invalid in a way worth naming, because it
is the most seductive error on this whole page: **a ceiling cannot corroborate a point estimate.** The
rule-of-three bound is `P(one draw ≥ bar) ≤ 2.83 %`; 0.95 % is inside it, 1.48 % is inside it, and
F19's 0.0367 % is inside it too. A test that every candidate passes discriminates among none of them,
so "the model survives" is true and empty. What the bound *does* do is refute anything above it, which
is precisely the retracted 15.6 % — and that arithmetic (`p = 0.156` ⇒ `1.56e-08`) is genuine, so C2
keeps it verbatim. The advisor's own commit message for this file makes the stronger claim the code
implies — `brief 2a: model-free rule-of-three bound from 106 account draws (<=2.83%) corroborates
0.95-1.48%` — which is why fixing the printed line matters more than it looks: the printed line is
where the reasoning is taught.

**A collision found while checking C2, and now printed as a warning.** The manifest cites a sixth
artefact for its per-draw odds table — `research/tools/recompute_replicate_sigma_and_draw_odds.py`
(`manifest:749`) — so it was read and run too. It is **clean** (its only retracted constant is the
0.49 % σ named *as* retracted in its docstring, correct usage), and it reproduces its artifact exactly
(`recomputed sd(ln cs)% == artifact%` for all seven groups). But its odds table prints

```
  sigma%   gain%       z  P(1 draw)  P(3 draws)
  0.2276    0.00   2.174      1.48%       4.38%
```

i.e. **P(one draw) = 1.48 %** for a bare re-fire. That is the same number as fern's "empirical tail",
from entirely unrelated inputs: this tool uses `sd(ln cs) = 0.2276 %` (worst well-behaved group) with
the `0.4950 %` gap of a *different* program — the account's best-ever draw `e27f1ce = 2.6066497` — and
a **normal** tail at `z = 2.174`; fern's 1.48 % is an **empirical** tail at `z = 2.344` on a pooled
`sd = 0.538 %`. `1 − Φ(2.174) = 1.48 %` is a coincidence, not a replication. A successor who runs both
programs, as the handover tells them to, sees 1.48 % twice and reasonably concludes the price has been
independently confirmed. C2's replacement now says so in the output, naming both derivations. (Note
also that the two tools are answering different questions: re-firing `e27f1ce` from 0.4950 % below the
bar is not the same bet as re-firing the replicate group's program from 1.4441 % below it, which is
what F19 prices. Neither is wrong; they are labelled identically and read as the same row.)

**What is clean in this program** (so a successor does not re-litigate it): the 106-draw count, the
zero clears, the `≤ 2.83 %` rule-of-three bound and the `−0.4926 %` best-ever gap all reproduce from
the TSV at head; the failure-rate machinery is sound; and the program is careful about its *own* σ in a
way it is not careful about fern's imported one — `:124-125`:

```
    print("What this does NOT show: these rows are not one program, so the sd printed")
    print("above mixes code changes with draw noise and must not be quoted as a draw sd.")
```

which is the right caveat, stated by the same file that then quotes somebody else's draw sd without
one.

**Completeness census, stated so the next auditor can stop.** A repo-wide `git grep -lEI` at
`6778867d` for the retracted constants and their neighbours (`0.00586`, `0.0095`, `0.0148`, `0.95 %`,
`1.48 %`, `15.6 %`, `12798`) matches **166 tracked files**: 163 under `research/`, 2 under `senpai/`,
1 under `Vendor/`. The residue is not 161 open findings:

- `Vendor/mlx-swift/Tests/MLXTests/IntegrationTests.swift` is a numeric-tolerance substring, unrelated.
- The two `senpai/competition_notes/*` files are dated (2026-07-29, 2026-08-02) and are campaign
  infrastructure, out of scope; `senpai/research-frontier-briefing.md`'s `0.493 %` was checked
  separately and is the gap expressed against the **leader's** score rather than the bar — a different
  legitimate denominator, not a stale copy.
- Everything else under `research/` is either a dated per-PR or per-round note (the §11.1 clean bill:
  archival records of what was believed at the time, which must not be rewritten) or a substring
  artefact in a JSON/txt receipt.
- The claim-bearing, undated, *instructed-reading* set is exactly the five files the work order now
  covers, plus the sixth tool above, which is clean. **The reading list is exhausted.**

**Rows and verification.** The applier is now **36 rows (17 D / 12 C / 7 P) over five files** —
manifest 23, brief 6, `CURRENT_RESEARCH_STATE.md` 3, `slot_holder_arithmetic.py` 2,
`account_draw_record.py` 2 — and in a pristine worktree at `6778867d`:

1. `--check` → **36/36 targets verified** (both C guards bake against head).
2. All **five** patches `git apply --check -p1` → **CLEAN**.
3. `work_order_all.patch` applies and modifies exactly the five intended files, nothing else.
4. The patched `account_draw_record.py` **runs**, printing `measured sd, F19  0.04%`,
   `fern sd, normal tail  0.95%`, `fern sd, empirical  1.48%`, and the corrected interpretation block
   including the collision warning.
5. The patched brief and the patched program now agree: `:33-34` labels fern's rows "a *pooled* sd, not
   this program's" and B4's line notes the measured ≈0.04 % also clears the model-free bound.

**Lesson, and it is a different one from §14's.** §14 said audit the shortest document first. §15 says
**audit the reading list, not the document tree** — enumerate every artefact the handover tells a
successor to open or run, and treat that closure as the definition of scope. Four rows of this work
order exist only because a number was copied *out* of a document into a place a reader trusts more —
an instruction or a program's stdout: **B1** (F1 as a prescription in the brief), **B2** (F19's price
in the brief's table), **A24** (F19's σ in `slot_holder_arithmetic.py`) and **C1** (F19's price in
`account_draw_record.py`). Two corollaries worth carrying:
**a bound is not a measurement** (a ceiling refutes from above and corroborates nothing), and **the
same number arriving twice is not two witnesses** until you have checked that its inputs differ.

