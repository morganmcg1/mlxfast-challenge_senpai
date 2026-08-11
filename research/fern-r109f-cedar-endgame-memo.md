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
   #714 claim of +0.38 % score) is a **null** on this host — see the interim
   report. Landing it is safe and free but buys nothing measurable.
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
  n≥3 `--local-submit` baseline, the paired A/B null, the env-allowlist finding
  (`DARKBLOOM_*` reaches the worker locally and is uniformly absent officially,
  so behaviour ships only as a source default), and the retirements.
- `research/fern_r109f_draw_winprob.py`, `fern_r109f_gain_to_winprob.py`,
  `fern_r109f_queue_record.py` — regenerate every number above from the cached
  submission record.
