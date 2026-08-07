## step windows found: [8796, 9202, 9608, 10014, 10420] (using idx 10420)
## dispatches=406 barriers=247 command_buffers=45

## transformer layers detected: 40 ; tail dispatches=7

### 2.1 barrier sites (one default decode step)

| # | cb | ord | consumer | RAW producers | WAR producers | gap |
|---|----|-----|----------|---------------|---------------|-----|
| 1 | 1104 | 10422 | gate_softplus | inputNorm | - | 2 |
| 2 | 1105 | 10425 | o_proj | attn(full) | - | 2 |
| 3 | 1105 | 10426 | postNorm | o_proj | - | 0 |
| 4 | 1105 | 10427 | dense_gate_up | postNorm | - | 0 |
| 5 | 1105 | 10428 | dense_down | dense_gate_up | - | 0 |
| 6 | 1106 | 10430 | qkv(h64) | inputNorm | - | 1 |
| 7 | 1106 | 10431 | attn(sliding) | qkv(h64) | - | 0 |
| 8 | 1106 | 10433 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 9 | 1106 | 10434 | postNorm+router | o_proj | - | 0 |
| 10 | 1106 | 10435 | shared_swiglu | postNorm+router | - | 0 |
| 11 | 1106 | 10438 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 12 | 1108 | 10440 | qkv(h64) | inputNorm | - | 1 |
| 13 | 1108 | 10441 | attn(sliding) | qkv(h64) | - | 0 |
| 14 | 1108 | 10443 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 15 | 1108 | 10444 | postNorm+router | o_proj | - | 0 |
| 16 | 1108 | 10445 | shared_swiglu | postNorm+router | - | 0 |
| 17 | 1108 | 10448 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 18 | 1109 | 10450 | qkv(h64) | inputNorm | - | 1 |
| 19 | 1109 | 10451 | attn(sliding) | qkv(h64) | - | 0 |
| 20 | 1109 | 10453 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 21 | 1109 | 10454 | postNorm+router | o_proj | - | 0 |
| 22 | 1109 | 10455 | shared_swiglu | postNorm+router | - | 0 |
| 23 | 1109 | 10458 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 24 | 1110 | 10460 | qkv(h48) | inputNorm | - | 1 |
| 25 | 1110 | 10461 | attn(full) | qkv(h48) | - | 0 |
| 26 | 1110 | 10463 | o_proj | attn(full), gate_softplus | - | 1 |
| 27 | 1110 | 10464 | postNorm+router | o_proj | - | 0 |
| 28 | 1110 | 10465 | shared_swiglu | postNorm+router | - | 0 |
| 29 | 1110 | 10468 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 30 | 1110 | 10469 | inputNorm | down+residual | - | 0 |
| 31 | 1110 | 10470 | qkv(h64) | inputNorm | - | 0 |
| 32 | 1111 | 10473 | o_proj | attn(sliding), gate_softplus | - | 2 |
| 33 | 1111 | 10474 | postNorm+router | o_proj | - | 0 |
| 34 | 1111 | 10475 | shared_swiglu | postNorm+router | - | 0 |
| 35 | 1111 | 10478 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 36 | 1111 | 10479 | inputNorm | down+residual | - | 0 |
| 37 | 1111 | 10480 | qkv(h64) | inputNorm | - | 0 |
| 38 | 1112 | 10483 | o_proj | attn(sliding), gate_softplus | - | 2 |
| 39 | 1112 | 10484 | postNorm+router | o_proj | - | 0 |
| 40 | 1112 | 10485 | shared_swiglu | postNorm+router | - | 0 |

(first 40 of 247 shown; full list in the tsv)

### 2.2 per-layer barrier templates

**template x15** (10 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
| | qkv(h64) | BAR |
| | attn(sliding) | . |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x12** (10 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
| | qkv(h64) | BAR |
| | attn(sliding) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | . |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x5** (10 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | . |
| | qkv(h48) | BAR |
| | attn(full) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x4** (10 dispatches, 7 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
| | qkv(h48) | BAR |
| | attn(full) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x3** (10 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | . |
| | qkv(h64) | BAR |
| | attn(sliding) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x1** (8 dispatches, 5 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | . |
| | gate_softplus | BAR |
| | qkv(h48) | . |
| | attn(full) | . |
| | o_proj | BAR |
| | postNorm | BAR |
| | dense_gate_up | BAR |
| | dense_down | BAR |

**tail** (7 dispatches, 4 barriers)

| cb | kernel | barrier? | RAW |
|----|--------|----------|-----|
| 1165 | inputNorm | . | - |
| 1165 | lm:5a coarse | BAR | inputNorm |
| 1165 | lm:5b argmax1 | BAR | lm:5a coarse |
| 1165 | lm:5c winner | BAR | lm:5b argmax1 |
| 1167 | lm:5d refine | . | - |
| 1169 | lm:gather | . | - |
| 1169 | lm:argmax | BAR | lm:gather |

layer barriers=243 tail barriers=4 pre-layer=0 total=247

### barrier-charged edges, aggregated over the step

| producer role(s) | consumer role | count |
|------------------|---------------|-------|
| postNorm+router | shared_swiglu | 39 |
| routed_swiglu+router_top8+shared_swiglu | down+residual | 39 |
| down+residual | inputNorm | 31 |
| inputNorm | qkv(h64) | 30 |
| attn(sliding)+gate_softplus | o_proj | 30 |
| o_proj | postNorm+router | 27 |
| qkv(h64) | attn(sliding) | 15 |
| inputNorm | qkv(h48) | 9 |
| qkv(h48) | attn(full) | 9 |
| attn(full)+gate_softplus | o_proj | 5 |
| gate_softplus | o_proj | 4 |
| inputNorm | gate_softplus | 1 |
| attn(full) | o_proj | 1 |
| o_proj | postNorm | 1 |
| postNorm | dense_gate_up | 1 |
| dense_gate_up | dense_down | 1 |
| inputNorm | lm:5a coarse | 1 |
| lm:5a coarse | lm:5b argmax1 | 1 |
| lm:5b argmax1 | lm:5c winner | 1 |
| lm:gather | lm:argmax | 1 |

### candidate-edge charge rate (per step)

| candidate edge | edge present | barrier charged | free (cb split / collapsed) |
|----------------|--------------|-----------------|------------------------------|
| C1 inputNorm->qkv | 39 | 39 | 0 |
| C2 attn->o_proj | 36 | 36 | 0 |
| C3 postNorm+router->top8 | 0 | 0 | 0 |
| C4 shared->down / routed->down | 39 | 39 | 0 |
| C5 postNorm+router first consumer | 39 | 39 | 0 |
| layer boundary down->inputNorm | 31 | 31 | 0 |

### refund pricing (M4-measured coefficients)

barrier = 1.3003 us, dispatch = 0.1231 us, score = 0.015280 %/us
