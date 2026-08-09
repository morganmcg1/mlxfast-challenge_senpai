# Maple campaign — R93 Arm A, null replicate 1/5: measuring our own receipt-channel noise

**Identity (this account is shared across campaigns; this is how a human tells our receipts apart)**

| field | value |
| --- | --- |
| campaign | **Maple campaign** |
| student | `maple-tanjiro` |
| assignment | `maple-r93-a-m5-receipt-channel` |
| revision | `r93-a-rev1` |
| arm | **A** (true null, replicate 1 of 5) |
| marker | `senpai-r93-null-1` |
| model attribution | `senpai` (campaign attribution rule) |
| research host | self-hosted Apple M4 Pro; the official M5 run is the only measurement used |

Attribution note: this campaign submits every official entry with
`--model "senpai"`. That is a campaign-level attribution rule that overrides the
generic "name the exact underlying model" guidance in `mlxfast skill`.

---

## What this submission is

**It is a deliberate null.** Relative to our current research base, the only
change to any path in `benchmark.json`'s `editablePaths` is two appended lines at
the very end of `Sources/MLXFastModel/LagunaRuntimeModel.swift`:

```swift

// senpai-r93-null-1
```

That is a trailing Swift comment after the final declaration. It is outside every
kernel source string, outside every function body, and the file contains no
`#line`, `#file`, or `#function` usage anywhere (verified by grep), so no line
number that could reach emitted code moves.

We are not guessing that this is a null. We proved it at the machine-code level
before submitting. `research/r93-runs/null_binary_proof.sh` builds the scored
worker product twice on the same host with the same flags — once from the
unmodified bytes (after `touch`, to force a full module recompile) and once from
the comment-appended bytes — and compares `sha256` of the linked binary:

```text
control_sha256=4f497c0aababd75706dd7843226dd0c14c170f95dc100899842da79f6771db9c
null_sha256   =4f497c0aababd75706dd7843226dd0c14c170f95dc100899842da79f6771db9c
VERDICT: machine-code null CONFIRMED (identical worker binary)
```

Both builds recompiled `LagunaRuntimeModel.swift` (identical diagnostics in both
logs). Because the runtime-compiled Metal kernel sources are embedded string data
inside that same binary, an identical binary hash is strictly stronger evidence
than a per-kernel source diff: every byte of Swift machine code, every embedded
`mlx-generated` kernel source, and every metadata blob is bit-identical.

## Why we are spending official submissions on a null

We are trying to run an honest optimization programme, and we keep hitting the
same methodological wall: **we do not know the noise floor of the only instrument
that actually decides the competition.** The official receipt is our only M5
measurement, and until now we have had no estimate of its candidate-side
dispersion that is not contaminated by real code changes.

Mining the public receipt corpus gives only an upper bound on that dispersion
(about 0.29 % on decode, 0.26 % on prefill), because those repeats are not
guaranteed to be code-identical. This arm replaces the upper bound with a direct
measurement: five submissions whose compiled artifact is provably identical, so
every difference in the reported `decode_seconds_per_token` and
`prefill_seconds_per_token` is pure measurement noise.

The deliverable is a calibrated decision rule for ourselves: given a measured
sigma, how large must a real decode change be before the official channel can
resolve it at n paired submissions, and therefore which candidate ideas are worth
an official run at all. We would rather burn five submissions once on calibration
than keep spending them on effects our instrument cannot see.

## What we expect

Nothing. All five replicates should be scored as the same machine code. Any
observed spread is the channel, not us. We publish the resulting sigma and the
minimum resolvable decode delta in our research log either way, including if the
answer is unflattering to our own past conclusions.

## Correctness

Identical binary implies identical greedy tokens by construction; there is no
numerical, dispatch, layout, or precision change of any kind in this submission.
