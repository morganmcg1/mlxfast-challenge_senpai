# NAX routing verification (which classes actually reach the guard)

The guard sits inside `steel_matmul_regular_axpby_nax`, so only shapes that
survive the NAX split-K admission at `matmul.cpp:1019-1021` can ever see it:

```cpp
if (use_nax && batch_size_out == 1 &&
    (K >= 3 * std::max(M, N) ||
     (std::max(M, N) <= 1024 && K > 2 * std::max(M, N)))) {  // -> split-K
```

| class | M | N | K | max(M,N) | `K >= 3*max` | `max<=1024 && K > 2*max` | route |
|---|---|---|---|---|---|---|---|
| wq slide + dense gate/up | 512 | 8192 | 2048 | 8192 | 2048>=24576 F | max>1024 F | **regular-NAX** |
| wq full | 512 | 6144 | 2048 | 6144 | F | F | **regular-NAX** |
| wk + wv (TARGET) | 512 | 1024 | 2048 | 1024 | 2048>=3072 F | 2048>2048 **F** | **regular-NAX** |
| L39 [K;V] bank | 512 | 2048 | 2048 | 2048 | 2048>=6144 F | max>1024 F | **regular-NAX** |
| wo slide / dense down | 512 | 2048 | 8192 | 2048 | 8192>=6144 **T** | - | split-K |
| wo full | 512 | 2048 | 6144 | 2048 | 6144>=6144 **T** | - | split-K |
| router | 512 | 256 | 2048 | 512 | 2048>=1536 **T** | - | split-K |
| g_proj | 512 | 128 | 2048 | 512 | 2048>=1536 **T** | - | split-K |
| decode wq/gate/up | 1 | 8192 | 2048 | 8192 | F | F | **regular-NAX** |
| decode wk+wv | 1 | 1024 | 2048 | 1024 | F | 2048>2048 **F** | **regular-NAX** |
| decode L39 bank | 1 | 2048 | 2048 | 2048 | F | F | **regular-NAX** |

Two consequences.

1. The `router` and `g_proj` rows printed as `ADMIT` by `/tmp/guardcheck.cpp`
   are harness artifacts. That replay models only the tile-selection block, not
   the split-K early return above it, so it evaluates the guard on shapes that
   never reach it. Real behaviour for those two classes is unchanged.

2. **The `tiles_m >= 4` term is load-bearing, not cosmetic.** All three M=1
   decode classes reach the regular-NAX function. Under the tile ceiling alone
   (`tiles <= 96 && N % 64 == 0`, as originally drafted) every one of them would
   have been admitted:

   | decode class | tiles_m | tiles_n | tiles | ceiling alone | with `tiles_m>=4` |
   |---|---|---|---|---|---|
   | wq/gate/up (1,8192,2048) | 1 | 64 | 64 | ADMIT | exclude |
   | wk+wv (1,1024,2048) | 1 | 8 | 8 | ADMIT | exclude |
   | L39 bank (1,2048,2048) | 1 | 16 | 16 | ADMIT | exclude |

   That would have silently retiled the entire decode QKV/gate/up projection
   path, which carries 75% of the score weight, making any prefill result
   unattributable. With `tiles_m >= 4` the arm is a clean prefill-only change
   and the decode axis is a genuine negative control.
