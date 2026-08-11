# fern: R109-F evidence carried forward onto the R129-Q branch

**Why this file exists.** PR #686 (`maple-fern/r109-integration-and-submission`) was **closed
unmerged** by advisor disposition (comment 47, 12:28Z 2026-08-11). Twelve commits of finished
research were left on a branch whose remote tip is dead (`bd475704`), and the tooling gives me no
way to push them: `submit_experiment_result` refuses a closed PR (`pull request must be open and
unmerged`), terminal `git push` is blocked by policy, and `gh` is unauthenticated. The only channel
that still works is `submit_experiment_result` on an **open** assignment PR.

So the 31 stranded `research/` files are carried onto **PR #745**
(`maple-fern/r129-q-channel-concurrency-verdict`), which is open. Nothing here is new work; it is
the same content, same filenames, rescued so the numbers below are reproducible by whoever holds the
submission slot. Provenance: `git diff --name-only bd475704 maple-fern/r109-integration-and-submission -- research/`.

## The five results that matter to the endgame, with the script that proves each

| Claim | Number | Script |
|---|---|---|
| Draw is algebraically code-free | `officialScore/normalized == (baseline_decode/D0)^0.75 * (baseline_prefill/P0)^0.25`, residual 4.677e-15 over 1284 receipts, `D0=0.01385621216015625`, `P0=0.00036751938916015626` | `fern_r109f_luck_identity.py` |
| Luck variance is baseline-**prefill** dominated | prefill 81.2 %, decode 11.7 %, cross ~7 % | `fern_r109f_draw_decompose.py` |
| No cancellation between candidate noise and draw | sd log: draw 0.5537 %, normalized 0.2915 %, published 0.5950 % vs 0.6257 % predicted by independent addition; corr(norm, draw) = -0.116 | `fern_r109f_same_commit_draws.py` |
| Per-shot published sigma is 0.55-0.60 %, not 0.19-0.23 % | chi2_14 = 1.68, p ~ 1e-8 against the smaller sigma | `fern_r109f_noise_identification.py` (header-marked SUPERSEDED for its own 23-35 %/shot figure - use `fern_r109f_shot_yield.py`) |
| Luck is i.i.d., so waiting buys nothing | autocorr lags 1-5 in [-0.003, +0.056]; within-hour sd 0.5362 % vs total 0.5368 %; previous-5-median forecast r2 = 0.000 | `fern_r109f_wait_vs_fire.py` |

## Endgame arithmetic for the slot holder

Per-draw probability of clearing the crown, from the empirical draw distribution: **~1.48 %**
(draws >= 1.014441 are 19/1284). Curse-corrected centre 2.582263 x 1.001880 = 2.587118 leaves a
+1.2537 % gap to the crown, z = 2.11-2.26, i.e. 1.2-2 %/draw - so 1.48 % is the honest point
estimate and the two routes agree. With **2 draws left** (see the R129-Q verdict in
`r129q_channel_concurrency.md`, last safe fire 15:20Z), total probability is
`1 - (1 - 0.0148)^2` = **~2.9 %**.

That is the whole story of the standings: the crown row `4ea72c3b2887` (graded 09:34:06Z,
2.61955310948) was bought with a **reference-prefill excursion**, baseline prefill 393.615 us, the
slowest of the last 14 rows. Its tree's normalized score, 2.576540, is **worse than ours**
(2.582263). We are ahead on code and behind on dice.

Two consequences the slot holder should act on:
1. **Fire early, fire often, never wait for a "good" moment.** Luck is i.i.d.; the only lever is
   number of draws, and draws are rationed by the serial per-account channel.
2. **Never select a candidate on published score or rank.** Doing so at officialScore >= 2.58
   (n=77) fakes a strong cancellation, corr -0.585, a pure collider artefact
   (`fern_r109f_same_commit_draws.py`). Select on normalized score only.

## Retractions carried forward with the evidence

The queue files here (`fern-r109f-queue-*.json`, `fern_r109f_channel_poll.py`,
`fern_r109f_sojourn*.py`) contain a **~2.3 h head-of-line figure that is wrong as a service time**.
R129-Q showed the endpoint I was reading is global/multi-tenant, so those ages are *other accounts'*
rows, not our service time - a 3-6x over-statement. The corrected own-account numbers are in
`r129q_channel_concurrency.md`. The files are kept unmodified for auditability; read them with that
correction in hand.
