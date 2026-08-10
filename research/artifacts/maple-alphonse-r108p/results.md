### 5.1 Arm means (µs/step, decode)

| arm | Δn | n | mean | sd | rows |
|---|---|---|---|---|---|
| `d0` | 0 | 4 | 12897.19 | 35.6 | 12900, 12848, 12934, 12906 |
| `d4` | 158 | 4 | 13203.35 | 26.5 | 13211, 13168, 13203, 13232 |
| `dQ` | 40 | 2 | 12926.17 | 25.2 | 12908, 12944 |
| `dR` | 117 | 2 | 13221.04 | 54.1 | 13259, 13183 |
| `e1600` | 1600 | 2 | 14085.06 | 165.6 | 13968, 14202 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (16 runs, 16 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 12 | 2.1379 | [1.6213, 2.6546] | 54.8 |
| E — addition, K ≤ 480 (free region) | 6 | 0.0686 | [-0.2796, 0.4169] | 40.0 |
| E — addition, secant from K=480 upward (past knee) | 4 | 0.8829 | [0.4847, 1.2810] | 122.5 |
| E — addition, all K (secant, do not quote) | 8 | 0.7629 | [0.6082, 0.9176] | 118.5 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 2.1379 | [1.6213, 2.6546] |
| removal price, µs/dispatch (d4/d0 matched pair) | 1.9377 | n/a |
| addition price at operating point, µs/dispatch | 0.0686 | n/a |
| **ratio removal / addition(operating point)** | 31.1439 | [-217.3860, 132.5702] |
| **ratio removal / M4 saturated addition (2.17, regime-matched)** | 0.9852 | [0.9059, 1.0798] |
| ratio removal / rule 65 M5 addition (2.3403) | 0.9135 | n/a |
| ratio removal / rule 57 quoted M4 (1.2382, chord — void) | 1.7266 | [1.2951, 2.1693] |
| k_dispatch regime-matched = rule65 / M4 saturated addition | 1.0785 | [0.9917, 1.1820] |
| M5 removal projected at k_dispatch=1.890 | 4.0407 | n/a |
| M5 removal projected at k_residue=1.4998 | 3.2065 | n/a |
| **k_removal = rule65 / M4 removal** | 1.0947 | [0.8816, 1.4435] |
