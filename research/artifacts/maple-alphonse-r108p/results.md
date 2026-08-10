### 5.1 Arm means (µs/step, decode)

| arm | Δn | n | mean | sd | rows |
|---|---|---|---|---|---|
| `d0` | 0 | 2 | 12874.27 | 36.6 | 12900, 12848 |
| `d4` | 158 | 2 | 13189.30 | 30.3 | 13211, 13168 |
| `dQ` | 40 | 1 | 12908.37 | — | 12908 |
| `e1600` | 1600 | 1 | 13967.95 | — | 13968 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (8 runs, 8 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 5 | 2.0483 | [1.3442, 2.7524] | 35.8 |
| E — addition, K ≤ 480 (free region) | 4 | 0.1517 | [-0.5386, 0.8420] | 44.3 |
| E — addition, secant from K=480 upward (past knee) | 3 | 0.7944 | [0.1970, 1.3918] | 50.8 |
| E — addition, all K (secant, do not quote) | 5 | 0.7089 | [0.4764, 0.9415] | 97.7 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 2.0483 | [1.3442, 2.7524] |
| removal price, µs/dispatch (d4/d0 matched pair) | 1.9939 | n/a |
| addition price at operating point, µs/dispatch | 0.1517 | n/a |
| **ratio removal / addition(operating point)** | 13.5016 | [-25.3417, 99.0993] |
| **ratio removal / M4 saturated addition (2.17, regime-matched)** | 0.9439 | [0.8679, 1.0345] |
| ratio removal / rule 65 M5 addition (2.3403) | 0.8752 | n/a |
| ratio removal / rule 57 quoted M4 (1.2382, chord — void) | 1.6543 | [1.0738, 2.2493] |
| k_dispatch regime-matched = rule65 / M4 saturated addition | 1.0785 | [0.9917, 1.1820] |
| M5 removal projected at k_dispatch=1.890 | 3.8713 | n/a |
| M5 removal projected at k_residue=1.4998 | 3.0720 | n/a |
| **k_removal = rule65 / M4 removal** | 1.1426 | [0.8503, 1.7411] |
