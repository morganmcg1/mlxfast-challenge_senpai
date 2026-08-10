### 5.1 Arm means (µs/step, decode)

| arm | Δn | n | mean | sd | rows |
|---|---|---|---|---|---|
| `d0` | 0 | 4 | 12897.19 | 35.6 | 12900, 12848, 12934, 12906 |
| `d4` | 158 | 3 | 13193.93 | 22.9 | 13211, 13168, 13203 |
| `dQ` | 40 | 1 | 12908.37 | — | 12908 |
| `dR` | 117 | 1 | 13259.29 | — | 13259 |
| `e1600` | 1600 | 1 | 13967.95 | — | 13968 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (12 runs, 12 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 9 | 2.0653 | [1.3810, 2.7496] | 62.0 |
| E — addition, K ≤ 480 (free region) | 6 | 0.0686 | [-0.2796, 0.4169] | 40.0 |
| E — addition, secant from K=480 upward (past knee) | 3 | 0.7944 | [0.1970, 1.3918] | 50.8 |
| E — addition, all K (secant, do not quote) | 7 | 0.6743 | [0.5029, 0.8457] | 95.5 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 2.0653 | [1.3810, 2.7496] |
| removal price, µs/dispatch (d4/d0 matched pair) | 1.8781 | n/a |
| addition price at operating point, µs/dispatch | 0.0686 | n/a |
| **ratio removal / addition(operating point)** | 30.0861 | [-210.0904, 129.0320] |
| **ratio removal / M4 saturated addition (2.17, regime-matched)** | 0.9518 | [0.8751, 1.0431] |
| ratio removal / rule 65 M5 addition (2.3403) | 0.8825 | n/a |
| ratio removal / rule 57 quoted M4 (1.2382, chord — void) | 1.6680 | [1.1032, 2.2469] |
| k_dispatch regime-matched = rule65 / M4 saturated addition | 1.0785 | [0.9917, 1.1820] |
| M5 removal projected at k_dispatch=1.890 | 3.9034 | n/a |
| M5 removal projected at k_residue=1.4998 | 3.0976 | n/a |
| **k_removal = rule65 / M4 removal** | 1.1331 | [0.8511, 1.6946] |
