# STEP 0 — ranked dispatch record (submission `58e28b8d`)

Posted as a committed branch artefact because `send_assignment_feedback` is an
advisor-owned transition; a student cannot comment through it. This file is the
durable student-side record of the one official dispatch I was handed.

**Channel state: HELD.** It is released only by the release note appended to the
bottom of this file once the receipt resolves.

## Dispatch record

| field | value |
|---|---|
| submission id | `58e28b8d-d677-499e-a0cf-03bf2e767e8a` |
| status at dispatch | `validating` |
| dispatched (UTC) | 2026-08-06T04:42Z |
| commit submitted | `f2fedd584e6514569758d79e581402210306e77b` |
| benchmark | `eigenlabs/mlxfast-challenge` |
| model attribution | `--model "senpai"` — **accepted on the first attempt, no fallback used** |
| public note | 11.7 KiB (within the 5 KiB–100 KiB window) |
| receipt log | `/tmp/nezuko85/submit-receipt.log` (host-local, not committed) |

## What this receipt measures

The submitted commit `f2fedd58` carries exactly two merged experiments on top of
the prior frontier.

### #72 — group-32 effective scale granularity

Bit-identical halving of the routed-expert NVFP4 scale planes
(`lagunaHalvedGroup32ScalePlane`, `preparePackedRoutedGateUpBank`,
`lagunaPackedRoutedGateUpScaleBytes`, `lagunaRoutedDownScaleBytes` in
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`).

A census over 985,300,992 scale pairs found 985,300,824 identical and 168
exceptions, every one of which is the first pair of a tensor; those are carried
in a 128-byte patch header. An init-time refusal gate returns `nil` unless the
halving is provably lossless.

- expected decode effect: **+0.834 %** predicted
- Campaign B same-host paired measurement: **+0.726 % ± 0.457 %**
- prior estimate of promotion odds: **~41 %**
- diffstat vs previous frontier: `LagunaRuntimeModel.swift` +
  `LagunaRuntimeWeights.swift`, +216 / −98

This is the only mechanism in the submission that can move the number.

### #81 — Metal-literal byte reclamation

T1 dedent 29,360 B plus T2 comment strip; 42,757 B total.
`LagunaRuntimeModel.swift` 521,768 → 479,011 B.

The certificate compared 109 emitted kernel source strings: 77 byte-identical,
32 differ, **32 explained, 0 unexplained**. The change is **inert by
construction** — zero semantic effect, pure per-file byte headroom.

- diffstat vs previous frontier: `LagunaRuntimeModel.swift` +3881 / −4092

### Reading the receipt

A `rejected` receipt would be an ordinary outcome meaning "did not beat the
current best", **not** a correctness or floor failure. When the receipt resolves
I will report six independent lines: receipt id, `correctness`, `error`, the
decode floor verdict, the prefill floor verdict, and ranking status **last**.

## Pre-dispatch checks (all green)

- Worktree clean at `f2fedd58`; no local modifications.
- All `DARKBLOOM_INJECT_*` knobs verified at neutral defaults:
  `DECODE_SWEEPS=0`, `SWEEP_PASSES=1`, `PREFILL_MATMULS=0`, `DECODE_EMPTY=0`,
  `PREFILL_EMPTY=0`, `EMPTY_SPREAD=1`, `EMPTY_TG=160`, `EMPTY_CHAIN=1`.
- Editable budget: `current=2930084/3000000  headroom=69916  growth=0/262144
  files=142`.
- `editablePaths` resolves to 97 entries (93 files totalling 1,896,386 B plus 4
  directory entries).
- `LagunaRuntimeModel.swift` = 478,533 B against the 524,288 B per-file cap
  (45,755 B margin).

## `./benchmark.sh --local-submit` immediately before dispatch

```
passed:                    true
passed_correctness:        true
max_abs_diff:              0
checked_steps:             1025
num_layers:                40
error:                     ""
partial_result:            false
peak_ram_gb:               21
decode_seconds_per_token:  0.00910558
decode_speedup:            1.5217      (floor pass)
prefill_seconds_per_token: 0.0011239
prefill_speedup:           0.3270      (floor FALSE — see below)
golden_hash:   f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2
harness_hash:  69baac098b6dbf12feb5340ff2a9167caf741e3b3eadfdbded15ca48d87aaf33
weights_hash:  aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
weight files:  9  (21,568,891,382 B)
timestamp:     2026-08-06T04:17:55Z
```

### Prefill-floor disclaimer

The `prefill_speedup 0.327 / floor=false` line is the known M4 Pro host
artefact, not a property of the candidate. This box reports Apple GPU generation
16 and therefore never selects the `_nax` prefill kernels the ranked M5 uses;
the **unchanged base reproduces the identical number on the same host**. It is
not evidence about the ranked prefill floor in either direction. The M5 decides.

## PR #85 status at time of dispatch

The dense-MLP lossless repack work is unaffected by the dispatch and continued
in parallel:

- Census complete; firing gate is **GO-12e** (p99 outliers/row at window 14 =
  2 ≤ 8). Chosen scheme d=4: 12.0063 bits/weight = 75.04 % of BF16.
- Implementation complete and building:
  `Sources/MLXFastModel/LagunaDensePacked.swift` (18,462 B) plus three minimal
  hooks in `LagunaRuntimeModel.swift`.
- **Static-equivalence certificate discharged** (the programme's fourth):
  `lagunaDensePackedReproduces` true on all three planes ⇒ 0 mismatching BF16
  bit patterns over 50,331,648 weights. Bytes moved per step
  100,663,296 → 75,522,048, i.e. **25.14 MB saved/step**. Escape rates
  0.014836 % (gate/up) and 0.014955 % (down). End-to-end
  `passed_correctness: true`, `max_abs_diff: 0`, `checked_steps: 130`, golden
  hash matched, `peak_ram_gb: 21`.
- Timing campaign A (12 paired within-binary runs with an A/A null control) was
  launched at dispatch time.

I will **not** dispatch the dense-MLP arm to the ranked M5 without an explicit
advisor go-ahead. When it is ready I will post `READY FOR CHANNEL` plus the head
SHA and stop.

---

## Channel release

<!-- appended once the receipt for 58e28b8d resolves -->

_status: PENDING — channel still HELD._
