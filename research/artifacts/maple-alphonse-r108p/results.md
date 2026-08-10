### 5.1 Arm means (µs/step, decode)

| arm | Δn | n | mean | sd | rows |
|---|---|---|---|---|---|
| `d0` | 0 | 2 | 12874.27 | 36.6 | 12900, 12848 |
| `d4` | 158 | 2 | 13189.30 | 30.3 | 13211, 13168 |
| `e1600` | 1600 | 1 | 13967.95 | — | 13968 |
| `e276` | 276 | 2 | 12916.14 | 50.8 | 12952, 12880 |

Correctness: every run passed (7 runs, 7 with a censused Δn).

### 5.2 Slopes (µs/step per dispatch)

| ladder | rungs | slope | 95 % CI | resid sd |
|---|---|---|---|---|
| D — removal (de-fusion) | 4 | 1.9939 | [1.0792, 2.9086] | 33.6 |
| E — addition, K ≤ 480 (free region) | 4 | 0.1517 | [-0.5386, 0.8420] | 44.3 |
| E — addition, secant from K=480 upward (past knee) | 3 | 0.7944 | [0.1970, 1.3918] | 50.8 |
| E — addition, all K (secant, do not quote) | 5 | 0.7089 | [0.4764, 0.9415] | 97.7 |

### 5.3 Headline ratios

| quantity | value | 95 % CI |
|---|---|---|
| removal price, µs/dispatch (slope) | 1.9939 | [1.0792, 2.9086] |
| removal price, µs/dispatch (matched pair) | 1.9939 | n/a |
| addition price at operating point, µs/dispatch | 0.1517 | n/a |
| **ratio removal / addition(operating point)** | 13.1429 | [-25.3417, 99.0993] |
| ratio removal / rule 57 saturated M4 | 1.6103 | [0.8621, 2.3769] |
| M5 removal projected at k_dispatch=1.890 | 3.7685 | n/a |
| M5 removal projected at k_residue=1.4998 | 2.9904 | n/a |
| **k_removal = rule65 / M4 removal** | 1.1737 | [0.8046, 2.1685] |
