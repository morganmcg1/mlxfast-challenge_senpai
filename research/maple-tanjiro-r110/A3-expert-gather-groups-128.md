# Arm A3 — `darkbloom_expert_gather_groups()` 256 -> 128

Status: **ready to fire**, delivered as a patch
(`A3-expert-gather-groups-128.patch`). Lowest-priority arm of the three;
droppable if the M5 channel is contended.
Owner surface: `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
(tanjiro region `:1222-1250`).
Single knob.

## Diff

One literal, in the existing helper at `quantized.cpp:1222-1231`:

```cpp
 int darkbloom_expert_gather_groups() {
   static const int v = [] {
     auto s = env::get_var("DARKBLOOM_EXPERT_GATHER_GROUPS", "");
     if (s.empty()) {
-      return 256;
+      return 128;
     }
     int n = std::atoi(s.c_str());
     return (n > 0 && (256 % n) == 0) ? n : 256;
   }();
   return v;
 }
```

Only the empty-string default moves. The invalid-value fallback stays at 256,
which mirrors the house pattern already used by `darkbloom_expert_down_bn()`
immediately below it (empty -> 32, invalid -> 64).

`DARKBLOOM_EXPERT_GATHER_GROUPS=256` restores base behaviour exactly, so the
control is available for a follow-up attribution run.

**Important: this arm shares a file with arm A1** (`quantized.cpp`). A1 edits
`darkbloom_expert_down_bn()` at `:1242`; A3 edits
`darkbloom_expert_gather_groups()` at `:1225`. They are different functions but
the same file, so A3 must be fired **on its own branch from the base**, never
stacked on the A1 branch. See `READY.md` for the exact procedure.

## Why this is safe (the question that decided the arm)

The concern worth ruling out was whether `expert_groups` partitions the **M**
(row/token) axis. It does not. It partitions the **expert id space** across
`grid.y`, and every row mapping is recomputed from sorted offsets rather than
from a group index.

Evidence in `fp_quantized_nax.h`:

- `:1716-1717` — `experts = 256`;
- `:1720` — `static_assert(experts % expert_groups == 0)`;
- `:1798` — loop bound `expert_slot < experts / expert_groups`;
- `:1802` — `expert = tid.y * (experts / expert_groups) + expert_slot`;
- `:1645-1661` — row ranges come from `laguna_sorted_lower_bound`;
- `:1808-1809` — per-expert row bounds;
- `:1820` — BM chunk loop over that row interval.

At `expert_groups = 128`, `S = experts / expert_groups` goes 1 -> 2. The map
`expert = tid.y * 2 + expert_slot` over `tid.y in [0,128)`,
`expert_slot in [0,2)` is still a **bijection** onto `[0,256)`: every expert is
visited exactly once, by exactly one threadgroup. Per-expert row intervals and
BM chunking are computed from the sorted offsets and are therefore unchanged.

Output addressing (`:1975-1977`, `:2005-2008`, `:2017-2027`) contains **no**
`expert_groups` term at all, so no output element changes owner and no
reduction is re-associated. `bounds[]` grows from 2 to 3 ints (`:1741`) — a
trivial threadgroup-memory change. The WAR barrier between chunks is already
exercised by the base at `S = 1`, and nothing in the kernel assumes
`M % expert_groups == 0`.

Conclusion: **bit-exact**. The risk in this arm is purely performance.

## Mechanism and predicted direction

Host side: default at `quantized.cpp:1224-1230`, kernel name suffix `_eg_N`
emitted at `:1508`, `grid.y = egroups` at `:1632`.

Going 256 -> 128 **halves `grid.y`** (256 -> 128 threadgroups on that axis) and
makes each threadgroup serialize 2 experts instead of 1.

Predicted direction is genuinely uncertain, which is why this arm ranks third:

- **Upside**: fewer, longer-lived threadgroups amortise per-threadgroup prologue
  (offset lookup, bounds computation, weight-pointer setup) across 2 experts,
  and halve total threadgroup launch overhead.
- **Downside**: halving `grid.y` halves available parallelism on the expert
  axis. If the gather-GEMM is already launch-limited rather than
  overhead-limited, this straightforwardly loses.

Discriminator on the M5 receipt, against the candidate reference
`1.87812e-4 ± 2.607e-7` s/token (n=14, sd 0.103 %):

- **Win** — `prefill_seconds_per_token` below `1.87030e-4` s/token (3 sd).
- **Null** — inside the 3 sd band; prologue amortisation and lost parallelism
  cancel. Do not pursue 64.
- **Loss** — above the band; the path is launch-limited. The interesting
  follow-up then flips to **512** (more groups), not fewer.

Since prefill elasticity is 0.362 and S ≈ 97.9 ms (1 ms = 0.37 % of score), a
>= 0.3 ms reduction in S is worth landing under the withdrawn 0.378 % bar.
Both speedup floors must stay >= 0.95.

## JIT

The kernel is JIT-only, generated from
`mlx-generated/fp_quantized_nax.cpp:1828-1946`, which is identical to the
header body apart from one comment. Since only a host-side integer default
changes and **no kernel body is touched**, the `.cpp` twin and the `.metal`/
header sources stay consistent automatically. No metallib rebuild is required.

## Local gates

See `GATES.md`.

## M4 correctness caveat

Same caveat as A1 and A2, and it applies in full. This host is `Mac16,11` (M4
Pro, Apple GPU generation 16) with `is_nax_available() == false`, so the
`fp_quantized_nax` gather-GEMM this arm retiles is **never dispatched locally**.

The local green `--local-iterate` run therefore proves only **build soundness,
harness health, and that the non-NAX path is unperturbed**. It does not
validate `_nax` numerics or geometry, and **local timing is not evidence for or
against this arm**. Only the official M5 channel can measure it.

`MLX_METAL_GPU_ARCH` was **not** set; forcing `_nax` on M4 is forbidden by the
assignment and was not attempted.

## Suggested follow-ups (not implemented)

1. If A3 **loses**, try `512` — the sign of this arm tells you which direction
   the expert axis wants, and a loss is a positive result pointing upward.
2. If A3 **wins**, `64` is the next step down, but the bijection argument still
   holds only while `256 % expert_groups == 0`; the existing validation clamp
   already enforces that.
