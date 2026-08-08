# R86-A rev2 pre-registration: prediction before any measurement

Assignment `maple-r86-a-base-decode-regression`, revision `r86-a-rev2`, PR #460.
Required base `7687c2e44e6975c181444ca8d3d151ee30480a72` (advisor branch tip
`c15740be`, doc-only above it). Old base `f64456dd2dc503af080dca65bddfb922164c7bc5`.
Host: Apple M4 Pro, 20 cores, Apple GPU generation 16.

Written and committed **before** the first timing run of this revision. Nothing
below is informed by a rev2 measurement.

## Bar re-verified (evidence contract item, done first)

`mlxfast benchmark` at the time of writing:

```
current best   2.61650354381456
source         https://github.com/Layr-Labs/mlxfast-challenge @ c5b0a13
```

So `cc6ddc1` @ 2.6165035 is still the bar, unchanged. Our best-ever promoted
content `97a5090c` @ 2.58882784082067 and our old base's own ranked control
`25b0b722` @ 2.55158458026643 remain the other two reference numbers.

## What the adoption actually changed

`git diff f64456dd..7687c2e4` touches 8 editable paths:

| path | ins/del | reachable on this M4 host? |
| --- | --- | --- |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 1435 | yes — scored forward pass |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 117 | yes |
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 5 | yes |
| `Vendor/mlx-swift-lm/.../RoPEApplication.swift` | 1 | yes |
| `Vendor/.../mlx-generated/fp_quantized_nax.cpp` | 304 | **no** — `_nax` never selected on gen 16 |
| `Vendor/.../metal/kernels/fp_quantized_nax.h` | 314 | **no** |
| `Vendor/.../metal/matmul.cpp` | 33 | yes — host-side dispatch |
| `Vendor/.../metal/quantized.cpp` | 210 | yes — host-side dispatch |

Two of the eight, and the two largest kernel-source deltas, cannot execute on
this host. That is the dominant source of prediction uncertainty and it caps
how much of the ranked gain an M4 pair can possibly see.

## Prediction

**Score frame.** 2.61650354 / 2.55158458 = **1.02544**, i.e. the frontier is
+2.544 % of score over our old base's measured control. If the whole of that
gain sat on the decode axis, then since `score = decode_sp^0.75 * prefill_sp^0.25`,
the decode speedup ratio would be 1.02544^(1/0.75) = 1.03400, and against the
M5 base decode of 4933.57 µs/step that is

    4933.57 x (1 - 1/1.03400) = 162.2 us/step on M5.

That is the **upper** end: it assigns nothing to prefill. Our old base was
already 3.98 % behind `97a5090c` on prefill alone, and the two unreachable
`_nax` files are prefill kernels, so I expect a real split with a substantial
prefill share.

**M5 point prediction (not measurable here, recorded for the record):**
decode −80 µs/step, 90 % interval [−20, −162]; prefill −12 µs/token,
90 % interval [−2, −25].

**M4 prediction — this is the falsifiable one.**

Old-base M4 anchors measured in rev1 on this same host, same harness, same
thermal gate: decode 12914.0 µs/step (SD 44.5, n=3), prefill 1113 µs/token.

I predict the new base is faster in decode, and by a fraction similar to the
reachable part of the M5 gain:

- **Δdecode = old − new = +200 µs/step (new base faster), 90 % interval
  [+30, +450]**, i.e. −1.5 % [−0.2 %, −3.5 %].
- **Δprefill = old − new = +5 µs/token, 90 % interval [−55, +65]**, i.e.
  essentially no change. The prefill work that the frontier improves is
  concentrated in `_nax`, which this host never selects, so I expect the M4
  prefill axis to be near-silent even if M5 prefill moves a lot.

**Resolution caveat, stated in advance.** My rev1 ABBA pair on this host with
3 reps/arm resolved ±117.7 µs/step at 95 %. So the lower half of my own decode
interval is below my instrument's floor. If the true M4 decode gain is under
~120 µs/step I will measure "no detection", and that must not be read as
"the adoption did not land". I will report the interval and say so explicitly.

**Confidence:** ~70 % that Δdecode is positive (new base faster) as a point
estimate; ~45 % that the pair resolves it as a statistically significant
positive at 3 reps/arm. I will raise reps if the first block lands inside the
noise band and time allows.

## Falsifiers

- Δdecode significantly **negative** (old base faster) ⇒ the advisor's reclaim
  broke something, or the adoption is a regression on non-`_nax` hardware.
- Any correctness gate failing on the new base while `f64456dd` passes the same
  gate ⇒ Null: an audit decision changed behaviour. Stop immediately.
- `AffineMetadataCoding` / `TiedHeadMetadataCoding` omission breaking the
  laguna transform arm ⇒ Null, and a build-only verification was insufficient.

## Nezuko cross-prediction, recorded as unresolvable-by-design

At `632e2c4`, before any of my data existed, nezuko registered ~80 % confidence
that the base regression was **not** dispatch-count-related and guessed
KV-cache bytes as the mechanism (`research/nezuko-r85-460-crossprediction.md`).
The bisect that would have scored that prediction was retired by rev2, and the
tree it referred to no longer exists. **The prediction can never be scored.**
Recording it here so it is not silently forgotten.
