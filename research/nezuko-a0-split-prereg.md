# Pre-registration: SPLIT localization of the dispatch-concurrency benefit

Written and committed **before** the `PHASES='1:2 1:1'` runs existed. Anchored on
PR #158 §4.5 replicated values and the A0 smoke serial-dispatch delta.

## Inputs (all pre-existing)

| quantity | value | source |
|---|---|---|
| `busy(SPLIT=1)` | 8572.8 µs/step | PR #158 §4.5, 4 replicates |
| `busy(SPLIT=0)` | 7999.4 µs/step | PR #158 §4.5, 4 replicates |
| `busy(SPLIT=2)` | 8058.0 µs/step | PR #158 §1.1.d |
| dispatches/step | 406 | invariant across all arms |
| CBs/step at SPLIT ∈ {1,2,0} | 406 / 204 / 45 | invariant |
| serial−concurrent busy at SPLIT=0 | +498.0 µs/step | A0 smoke, CB count fixed at 45 |

## Derived constants

Serializing dispatch *within unchanged command buffers* removes all intra-buffer
dispatch concurrency while holding the buffer count at 45. SPLIT=1 removes the
same concurrency **and** adds 361 command buffers. The difference isolates the
genuine per-buffer cost:

```
c = (573.4 - 498.0) / 361 = 0.209 µs/CB
W = busy(SPLIT=1) - 406c  = 8487.9 µs/step      (zero-overlap kernel work)
```

`c = 0.209 µs/CB` replaces PR #158's `c = 1.588 µs/CB`, which was **7.6× too
large** because it charged the whole SPLIT=1 inflation to buffer count when
~87 % of that inflation is loss of dispatch concurrency. Note 7.6× is
numerically the same factor as the PR #101 vs PR #158 headline gap
(0.456 / 0.06 = 7.6): it is the same conflation seen from two directions.

## Competing predictions for serial − concurrent busy

Seams are intra-buffer dispatch boundaries: `406 − CBs`. SPLIT=0 has 361,
SPLIT=2 has 202 (56 % retained), SPLIT=1 has 0.

| arm | **R-B** sibling shadowing | **R-A** uniform seam pipelining | control |
|---|---|---|---|
| SPLIT=1 (1 dispatch/CB) | ≈ 0 µs | ≈ 0 µs | must be ≈ 0 or the probe is invalid |
| SPLIT=2 (2 dispatches/CB) | **+473 µs** (95 % of SPLIT=0) | **+279 µs** (56 %, ∝ seam count) | — |
| SPLIT=0 (shipped, ~9/CB) | +498 µs | +498 µs | already measured |

The two hypotheses are separated by **194 µs**, which is 2.8× the ±70 µs
between-session arm scatter. This is a clean discrimination.

**R-B rationale.** If the benefit comes from a small latency-bound kernel hiding
underneath a bandwidth-bound neighbour, then *one* hazard-free neighbour is
enough. Pairwise splitting still gives every such kernel a partner, so almost
the whole benefit survives. **R-A rationale.** If the benefit is a fixed
tail/head overlap paid once per seam, removing 44 % of seams removes 44 % of it.

## Falsification

- `Δ(SPLIT=1)` materially above ~50 µs ⇒ the serial probe is charging a
  per-dispatch cost unrelated to concurrency, and **the whole A0 conclusion is
  withdrawn**, including the `c = 0.209` correction.
- `Δ(SPLIT=2)` near 279 µs ⇒ R-A, and the per-seam de-inflation unit is
  rehabilitated (though at 1.38 µs/seam, not 1.588 µs/CB).
- `Δ(SPLIT=2)` near 473 µs ⇒ R-B, and per-kernel exposure `E` is the only
  correct pricing unit; no constant per-dispatch or per-buffer subtraction is
  admissible.
- Anything between 330 and 420 µs ⇒ genuinely mixed; report the mixture weight
  rather than declaring a winner.

## Independent prior evidence already consistent with R-B

At SPLIT=2 concurrent, measured inflation over SPLIT=0 is only +58.6 µs, of
which `159 × 0.209 = 33.2 µs` is added buffer commit. The residual concurrency
loss is **25.4 µs against a uniform-R-A prediction of 219 µs** — an 8.6× miss.
The SPLIT=2 serial arm is the direct, same-currency confirmation of that
inference.
