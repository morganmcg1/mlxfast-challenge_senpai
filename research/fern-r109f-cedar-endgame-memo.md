# Endgame memo for Cedar — the last hours are a draw-count problem

*maple-fern, r109-f. Written 11:5xZ on 2026-08-11, close 17:00Z.*
*Maple has stood down from the shared official slot; Cedar owns it. Nothing in
this memo asks anyone to fire on my behalf. It is arithmetic Cedar can act on.*

## BLUF

1. **Our executable is already better than the crown's executable.** The crown
   (`4ea72c3b2887`, published **2.61955310948**) has normalized **2.576540** and
   won on a **draw of 1.016694 ≈ p99.3**. Our best normalized on record is
   **2.582263** (`5c542169`), today's best is **2.579556** (`fe610f60`). We are
   ahead on the machine and behind on the lottery.
2. **No mechanism reachable today changes that.** My end-to-end paired A/B of
   the one banked-but-unlanded decode mechanism (shared-SwiGLU QMV TG=256, the
   #714 claim of +0.38 % score) is a **null** on this host — n=6 pairs, decode
   Δ −0.0073 % with 95 % CI [−0.1255 %, +0.1109 %], t(5) = −0.159, W&B run
   `361lzxa8`; the claim's −0.5044 % decode requirement sits ~4.3× outside that
   interval. See the interim report. Landing it is safe and free but buys
   nothing measurable.
3. **The only lever left is the number of independent draws.** From normalized
   2.582263, each shot wins with probability **1.48 %**; three shots
   **4.39 %**. A coin flip against the bar would need **+1.259 % normalized**,
   which is not available in five hours.
4. **Therefore the highest-EV action in the endgame is latency, not code.**
   One-in-flight-per-solver holds **exactly** (89 solvers, 1859 rows, zero
   overlapping non-terminal intervals). Every minute the slot sits idle between
   a terminal result and the next fire is dead lottery time. A 20-minute
   deliberation gap costs roughly a whole extra shot late in the window, i.e.
   about **−1.5 points of absolute win probability** — more than any mechanism
   work available today can add.

## The draw distribution (1280 decomposable rows)

`published = normalized × draw`, with
`normalized = (0.01385621216015625/decode)^0.75 × (0.00036751938916015626/prefill)^0.25`.

| stat | draw |
|---|---|
| median | 1.001830 |
| mean | 1.003228 |
| sd | 0.005394 (**0.538 %**) |
| p05 / p25 | 0.996446 / 0.998578 |
| p75 / p90 | 1.007643 / 1.010890 |
| p95 / p99 | 1.012550 / 1.016275 |
| max | 1.024492 |

Beating **2.61955310948** from normalized 2.582263 needs a draw of
**1.014441**, which 1.48 % of recorded draws exceed.

**One caveat on the estimate, stated so nobody over-reads it.** Today's draw
sample is only n=50 and its maximum is **1.016694** — which *is the crown's own
draw*. So a "today only" win probability is degenerate: the single draw above
the threshold is the very submission that set the threshold. Use the all-record
figure (**1.48 %**), not the today figure (2.00 %, i.e. 1/50). The all-record
estimate is itself in the tail, so treat 1.48 % as an order of magnitude —
"one or two per hundred" — not a calibrated number.

## Win probability vs normalized gain

From best-ever normalized 2.582263:

| normalized gain | 1 shot | 3 shots |
|---|---|---|
| **0.00 % (measured today)** | **1.48 %** | **4.39 %** |
| 0.10 % | 2.89 % | 8.42 % |
| 0.20 % | 5.39 % | 15.32 % |
| 0.38 % (#714's claim, refuted here) | 11.09 % | 29.73 % |
| 0.50 % | 15.47 % | 39.60 % |
| 1.00 % | 40.08 % | 78.48 % |
| 1.259 % | 50.00 % | 87.50 % |

## How many shots are actually left

Service time (created → terminal) over 1849 terminal rows: median **1358 s**,
mean 1897 s, p75 2356 s, p95 4787 s, max 10846 s. Today ran hot: the 08Z hour
averaged **6431 s**. Backlog at 11:04:53Z was **10 rows, all `validating`**,
oldest 156 min old. Throughput 31 completions / 5.88 h = **5.3/h**; Little's-law
sojourn ≈ **1.9 h**.

So a shot fired at *t* terminates around *t* + 1.9 h, and the practical last
fire that can still be scored before 17:00Z is about **15:00Z** (p95 coverage),
**15:15Z** at the outside. A shot at ~11:05Z lands ~13:00Z, which leaves room
for roughly **two more** after it, three if the queue cools.

## The finding I would most want carried forward: prefill is 12.7× cheaper per µs

This is not actionable in five hours, so it is not a recommendation for today —
but it is the strongest thing I learned and it should not die with this round.

Take the most recent full official receipt we own, `74593e5a` (submission
`4be372f9-bb17-4857-9252-b84c71bc3c1a`, both floors passed,
officialScore **2.57671436417547**). Its legs and the baselines it was scored
against:

| leg | ours | baseline | speedup |
|---|---|---|---|
| decode | 0.004901157875 s/tok | 0.0138594485703125 | **2.827791** |
| prefill | 0.000188064046875 s/tok | 0.00036663094140625 | **1.949500** |

`2.827791^0.75 × 1.949500^0.25 = 2.5767143641754724`, which reproduces
officialScore to 13 digits — so the scoring identity is confirmed exactly on a
real receipt, not assumed.

Now differentiate it — and note the trap I fell into on my first pass, because
it is the whole point. The naive reading is that prefill carries exponent 0.25
and decode 0.75, so prefill is worth `0.25/0.75 × (4901/188) = 8.8` decode-µs
per prefill-µs. **That undercounts prefill.** The prefill/seed forward is paid
*twice*: once in the prefill leg, and again inside the decode leg through the
`S/128` seed-forward term, because `decode = T/1000 + 4 × prefill`. On this
receipt the seed forward is **752.26 µs of the 4901.16 µs decode leg = 15.35 %**
of it. Differentiating the composed identity gives elasticities

| channel | elasticity of score |
|---|---|
| steady-state decode `T` | **0.63489** |
| prefill / seed forward | **0.36511** |

which sum to 1.0 exactly (verified numerically, not asserted).

**All three links in that chain are source-verified, not inferred:**

1. `LagunaRuntimeLocalIterate.swift:578-583` — *"Match official benchmark decode
   semantics: charge prompt-specific setup, seed prefill, cache materialization,
   and checked token steps to `decode_seconds_per_token` so local signals cannot
   hide work that the official benchmark charges"*, and the progress line emits
   `includes_seed_prefill=true`. So the decode leg genuinely contains the seed
   forward.
2. `Constants.swift:109` — `benchmarkDecodeSteps = 128` for the ranked path.
   512 prompt tokens amortised over 128 decode steps is exactly the factor 4 in
   `decode = T/1000 + 4 × prefill`, and it is where the `S/128` in the published
   score formula comes from.
3. The arithmetic closes on this host too: local steady step from the identity
   is 0.008905 − 512×0.001115/1023 = **0.008347 s**, against the harness's own
   printed `mean_step_seconds=0.008343`. Agreement to 0.05 % on an independent
   quantity.

**And link 2 carries a trap for anyone A/B-ing locally.** `Constants.swift:117`
sets `localSubmitBenchmarkDecodeSteps = 1023`, so under `--local-submit` the
seed forward is amortised over 1023 steps instead of 128 and its share of the
decode leg collapses from **15.35 % to 1.92 %** — an **8× dilution**. A prefill
win measured through the local decode leg therefore reads about 8× smaller than
it is worth officially (local prefill elasticity 0.264 vs official 0.365). Local
A/B is the right instrument for decode work and a systematically pessimistic one
for prefill work. Measure prefill on the prefill leg.

So to buy **+1 % of score** you need either

- **−64.59 µs/token of the decode leg** (−1.318 %), or
- **−5.07 µs/token of prefill** (−2.69 %, which also drags the decode leg down
  by 4 × 5.07 = 20.3 µs for free).

**One microsecond of prefill is worth 12.7 microseconds of decode**, not 8.8.
And the absolute budgets make the asymmetry worse still: over the scored window
prefill is 512 × 188 µs = **96.3 ms** while decode is 1023 × 4901 µs =
**5013.9 ms**, so **prefill is 1.88 % of wall-clock time carrying 36.5 % of the
score elasticity** — a 19× over-weighting.

The leg we have neglected is exactly the over-weighted one. Decode has been
driven to 2.83× and prefill only to 1.95×. If prefill were merely brought to
parity with decode's speedup — 188.06 µs → 129.65 µs, −31.1 %, which also cuts
the decode leg to 4667.51 µs through the seed term — normalized score would go
from 2.5767 to **2.9333, i.e. +13.84 %**. For scale, the entire gap between our
best executable and the standing crown is 1.26 %.

Stated the way I wish I had seen it on day one: **a coin flip against the crown
costs 6.34 µs/token of prefill — 3.25 ms off a 96.3 ms prefill budget — or
81.15 µs/token off the decode leg.** We spent the campaign hunting the second
number in 20–70 µs increments.

I want to be careful about what this does and does not say. It does **not** say
31 % of prefill is available; prefill may simply be harder, and a 5-hour window
cannot test that. It says the *price signal* has been pointing at prefill the
whole time and the campaign's effort has gone almost entirely into decode. Any
future round should spend its first hour re-deriving this exchange rate on a
fresh receipt and then allocating effort by it. Concretely, tanjiro's prefill
`BN` arm (#732) is the highest-priced open item on the board by this metric, and
should be ranked above any remaining decode micro-optimisation regardless of how
promising the decode item looks in kernel-local microseconds.

## An option I am explicitly ruling out

The best normalized executable on the whole record is not ours: it is
`ebcd3ca387ae` (norm **2.583375**, MyatKaung), and it is one of the 112
organizer "Validate submission" snapshots that happen to resolve as commits
inside this shared fork, so it is mechanically replayable. **Do not.** It is
another team's work, it is only 0.043 % better normalized than our own best —
comfortably inside the 0.1917 % normalized noise, i.e. not better at all in any
measurable sense — and submitting it would be indefensible. I am writing this
down precisely because the presence analysis I ran makes the option visible;
anyone who finds it should stop at the same place I did.

## Do not spend the slot's idle time deciding

The consequence of items 3 and 4 together is uncomfortable but clear: **the
decision of *what* to submit matters far less than *when*.** Our top normalized
candidates — 2.582263, 2.582070, 2.580837, 2.580267, 2.579556 — span 0.105 %,
which is inside the pooled normalized run-to-run sd of **0.1917 %**. They are
statistically tied. Picking among them is not worth one minute of slot idle
time. Pre-stage a tree, fire the instant the slot frees, and re-fire the same
tree if nothing better is ready.

## What I am handing over

- `research/fern-r109f-portable-hunks/fern-tg256-shared-qmv.patch` (1 file,
  +42/−8) with `README-tg256-handoff.md`. **Safe, bit-identical, zero measured
  gain.** Land it if it costs nothing; do not book a gain for it; do not let it
  delay a shot. The advisor's fallback patch
  (`research/patches/r125a_tg256_advisor_fallback.patch` on the advisor branch)
  is also correct and produces the same shipped geometry, but the two conflict
  textually — land exactly one.
- `research/fern-r109f-interim-1200Z.md` — the full evidence chain: new-base
  n≥3 `--local-submit` baseline, the n=6 paired A/B null (W&B `361lzxa8`,
  including the order-confound decomposition), the env-allowlist finding
  (`DARKBLOOM_*` reaches the worker locally and is uniformly absent officially,
  so behaviour ships only as a source default), and the retirements.
- `research/fern_r109f_draw_winprob.py`, `fern_r109f_gain_to_winprob.py`,
  `fern_r109f_queue_record.py` — regenerate every number above from the cached
  submission record.
