# Decision rule, fixed BEFORE the receipt lands

Control `c3ce66e` (2026-08-05 09:33): S = 97.949583 ms, cand_pre = 191.30778 us,
cand_dec = 5.0464443 ms, ns = 2.5443596, max_abs_diff = 0, both floors passed.

Noise model: same-day frontier-tight candidate prefill rel sd 0.183%
  => 1 sd on S = 0.00183 * 97.9496 = 0.1793 ms
  (upper bound: that 0.183% still contains real code differences)

Pre-registered v2: point dS = -4.0 ms, 80% interval [-9, +1], point ns 2.5647.

## Gates checked first (any failure overrides everything below)
1. max_abs_diff == 0                     -> else INVALID CANDIDATE, hypothesis untested
2. passed_correctness == True
3. passed_prefill_speedup_floor == True
4. passed_decode_speedup_floor == True

## Primary axis: dS = S_cand - S_ctl  (negative = win)
| band | sigma | verdict |
|---|---|---|
| dS <= -0.54 ms | <= -3 sd | GREEN. Mechanism confirmed: DRAM read latency across the WAR barrier was binding. Compare magnitude to prereg -4.0 and to the 15.4 ms ceiling. Recommend merge + F3 (BN=32) / F2 (staging-free). |
| -0.54 < dS < +0.54 | within 3 sd | NULL. Two live explanations: (a) Metal compiler re-sank the hoisted loads, so no reordering actually happened; (b) load latency is not the binding constraint. Escalate to the **v1 canary** as a powered activation test. |
| dS >= +0.54 ms | >= +3 sd | WRONG SIGN, and this is the pre-registered falsifier: store/dequant throughput, not load latency, is binding. Activation is PROVEN by the significant shift, so no v1 canary needed. Report as an informative negative and close the double-buffer family. |

## Secondary axis: decode
This change touches only the prefill expert gather-QMM. Decode should be flat.
|dT| > 3 sd (decode rel sd 0.517% frontier-tight => ~0.026 ms on T = 4.281) is a
confound to flag, not a result to claim.

## Reporting
Rank by `ns`, never `officialScore` (0.569% vs 0.825% rel sd, n = 302).
A bit-exact within-noise null is a first-class result. Do not hunt a rescue.
