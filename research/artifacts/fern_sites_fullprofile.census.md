## step windows found: [8796, 9202] (using idx 9202)
## dispatches=406 barriers=258 command_buffers=30

## transformer layers detected: 40 ; tail dispatches=7

### 2.1 barrier sites (one default decode step)

| # | cb | ord | consumer | RAW producers | WAR producers | gap |
|---|----|-----|----------|---------------|---------------|-----|
| 1 | 723 | 9203 | inputNorm | embed+rope | - | 1 |
| 2 | 723 | 9204 | gate_softplus | inputNorm | - | 0 |
| 3 | 724 | 9207 | o_proj | attn(full) | - | 2 |
| 4 | 724 | 9208 | postNorm | o_proj | - | 0 |
| 5 | 724 | 9209 | dense_gate_up | postNorm | - | 0 |
| 6 | 724 | 9210 | dense_down | dense_gate_up | - | 0 |
| 7 | 725 | 9212 | qkv(h64) | inputNorm | - | 1 |
| 8 | 725 | 9213 | attn(sliding) | qkv(h64) | - | 0 |
| 9 | 725 | 9215 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 10 | 725 | 9216 | postNorm+router | o_proj | - | 0 |
| 11 | 725 | 9217 | shared_swiglu | postNorm+router | - | 0 |
| 12 | 725 | 9220 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 13 | 726 | 9222 | qkv(h64) | inputNorm | - | 1 |
| 14 | 726 | 9223 | attn(sliding) | qkv(h64) | - | 0 |
| 15 | 726 | 9225 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 16 | 726 | 9226 | postNorm+router | o_proj | - | 0 |
| 17 | 726 | 9227 | shared_swiglu | postNorm+router | - | 0 |
| 18 | 726 | 9230 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 19 | 726 | 9231 | inputNorm | down+residual | - | 0 |
| 20 | 726 | 9232 | qkv(h64) | inputNorm | - | 0 |
| 21 | 726 | 9233 | attn(sliding) | qkv(h64) | - | 0 |
| 22 | 726 | 9235 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 23 | 726 | 9236 | postNorm+router | o_proj | - | 0 |
| 24 | 726 | 9237 | shared_swiglu | postNorm+router | - | 0 |
| 25 | 727 | 9241 | inputNorm | down+residual | - | 3 |
| 26 | 727 | 9242 | qkv(h48) | inputNorm | - | 0 |
| 27 | 727 | 9243 | attn(full) | qkv(h48) | - | 0 |
| 28 | 727 | 9245 | o_proj | attn(full), gate_softplus | - | 1 |
| 29 | 727 | 9246 | postNorm+router | o_proj | - | 0 |
| 30 | 727 | 9247 | shared_swiglu | postNorm+router | - | 0 |
| 31 | 727 | 9250 | down+residual | routed_swiglu, router_top8, shared_swiglu | - | 2 |
| 32 | 727 | 9251 | inputNorm | down+residual | - | 0 |
| 33 | 727 | 9252 | qkv(h64) | inputNorm | - | 0 |
| 34 | 727 | 9253 | attn(sliding) | qkv(h64) | - | 0 |
| 35 | 727 | 9255 | o_proj | attn(sliding), gate_softplus | - | 1 |
| 36 | 727 | 9256 | postNorm+router | o_proj | - | 0 |
| 37 | 727 | 9257 | shared_swiglu | postNorm+router | - | 0 |
| 38 | 728 | 9261 | inputNorm | down+residual | - | 3 |
| 39 | 728 | 9262 | qkv(h64) | inputNorm | - | 0 |
| 40 | 728 | 9263 | attn(sliding) | qkv(h64) | - | 0 |

(first 40 of 258 shown; full list in the tsv)

### 2.2 per-layer barrier templates

**template x19** (10 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
| | qkv(h64) | BAR |
| | attn(sliding) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | . |

**template x9** (10 dispatches, 7 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
| | qkv(h64) | BAR |
| | attn(sliding) | BAR |
| | gate_softplus | . |
| | o_proj | BAR |
| | postNorm+router | BAR |
| | shared_swiglu | BAR |
| | router_top8 | . |
| | routed_swiglu | . |
| | down+residual | BAR |

**template x5** (10 dispatches, 7 barriers)

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

**template x4** (10 dispatches, 6 barriers)

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

**template x2** (10 dispatches, 6 barriers)

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

**template x1** (8 dispatches, 6 barriers)

| ord | kernel | barrier? |
|-----|--------|----------|
| | inputNorm | BAR |
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
| 754 | inputNorm | . | - |
| 754 | lm:5a coarse | BAR | inputNorm |
| 754 | lm:5b argmax1 | BAR | lm:5a coarse |
| 754 | lm:5c winner | BAR | lm:5b argmax1 |
| 756 | lm:5d refine | . | - |
| 758 | lm:gather | . | - |
| 758 | lm:argmax | BAR | lm:gather |

layer barriers=254 tail barriers=4 pre-layer=0 total=258

### barrier-charged edges, aggregated over the step

| producer role(s) | consumer role | count |
|------------------|---------------|-------|
| o_proj | postNorm+router | 39 |
| postNorm+router | shared_swiglu | 39 |
| down+residual | inputNorm | 33 |
| inputNorm | qkv(h64) | 30 |
| qkv(h64) | attn(sliding) | 30 |
| attn(sliding)+gate_softplus | o_proj | 30 |
| routed_swiglu+router_top8+shared_swiglu | down+residual | 20 |
| inputNorm | qkv(h48) | 9 |
| qkv(h48) | attn(full) | 9 |
| attn(full)+gate_softplus | o_proj | 9 |
| embed+rope | inputNorm | 1 |
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
| C2 attn->o_proj | 40 | 40 | 0 |
| C3 postNorm+router->top8 | 0 | 0 | 0 |
| C4 shared->down / routed->down | 20 | 20 | 0 |
| C5 postNorm+router first consumer | 39 | 39 | 0 |
| layer boundary down->inputNorm | 33 | 33 | 0 |

### refund pricing (M4-measured coefficients)

barrier = 1.3003 us, dispatch = 0.1231 us, score = 0.015280 %/us
