# PR #35 — pre-registered receipt read rule

Committed **before** any receipt for this arm exists, so the reading cannot be
chosen after the number is known. Student `maple-frieren`, branch
`maple-frieren/scale-code-width`, submission head `b3319dfb`.

## 1. Control

The only comparison used is the permanent ranked control `c3ce66ec`, whose
normalised score is

```
ns(control) = 2.544360
```

`ns` is the harness-independent reconstruction

```
nd  = 0.013890 / decode_s_per_tok
npf = 0.0003845 / prefill_s_per_tok
ns  = nd^0.75 * npf^0.25
```

and it is reported **first**, before `officialScore`, because `officialScore`
carries the session's own baseline and is not comparable across receipts.

The relative effect read from the receipt is

```
delta = ns(candidate) / 2.544360 - 1
```

## 2. Point prediction and its derivation

Deliverable B (4-bit lane-major per-row-base QKV decode scale plane) plus r1
(narrow `o_proj` bank) removes 34–39 MB of scale-plane traffic per decode step.
The r3 haircut converts M4 bytes to M5 time with the measured transfer factor

```
260.2 / 651.8 = 0.399
```

giving 52–60 µs/step, i.e. a **point prediction of +0.58 % to +0.67 %** on `ns`.

The unhaircut M4-rate figure, **+1.46 %**, is carried only as an explicit upper
bracket. It is not the prediction.

Two corrections that must not silently reappear in the reading:

* B alone is **30.1 %** of the M4 byte roofline. The earlier "75.5 %" was a
  unit-mismatch artefact: `0.755 = 0.301 × 651.8/260.2`.
* Single-receipt M5 dispersion is reserved at **±14.2 µs/step, i.e. ±0.278 % on
  `ns`**. The earlier "6.9σ" claim was a category error (it compared a
  within-session paired σ against a cross-session single-receipt spread).

## 3. The table

| `delta` on `ns` vs 2.544360 | Reading, fixed in advance |
| --- | --- |
| **≥ +0.60 %** | Strong confirmation. The byte-transfer mechanism is real at or above the haircut point prediction. |
| **+0.15 % … +0.60 %** | Consistent with the haircut point prediction once the ±0.278 % single-receipt reserve is applied. Positive, mechanism supported, magnitude not resolved to better than the reserve. |
| **−0.28 % … +0.15 %** | Inside single-receipt dispersion. **Not evidence in either direction.** Do not claim a win; do not claim the mechanism is dead. Report as unresolved and state that separating it needs a same-session paired measurement, not another single receipt. |
| **< −0.28 %** | Report immediately and **do not resubmit**. A regression this size cannot come from the byte accounting, so the first hypotheses are an injected-work landmine (§4), a base-acceptance mismatch, or an unintended interaction with the r1 bank — each of which is a diagnosis task, not a retune. |

Additional pre-registered commitments:

* If `delta ≥ +0.60 %` **and** the receipt is otherwise clean, that is one
  positive result from one receipt; it is *not* a licence to spend a second
  ticket confirming it.
* The r1 narrow-`o_proj`-alone anomaly (+69.5 µs/step at **4.1×** its byte
  roofline, 863 vs 210 GB/s) is **not** explained by this receipt whatever it
  says. Its discriminator (zero-byte 256-entry LUT, instruction-issue
  hypothesis) is held until after the receipt and is not folded into the reading
  above.
* Any M4-only claim in the write-up quotes the **measured within-session M4 ABBA
  σ**, never an M5 reserve.

## 4. Correctness and hygiene fields read *before* the score

The score is read only after all of the following are confirmed from the same
receipt:

`passed_correctness`, `checked_steps`, `case_count`, `max_abs_diff` (recorded but
**not** treated as a numerical bound — see
`research/frieren-pr35-r4-gate-blindness.md`), GPQA verdict, TTFT verdict,
`peak_ram_gb`, golden hash, harness hash, and **both** legacy band ratios with
the band formula stated explicitly so a legacy band failure is not mistaken for
the ranked verdict.

Pre-dispatch, and pasted into the submission note:

```
git show <submission commit>:Sources/MLXFastModel/LagunaRuntimeModel.swift \
  | grep -n "DARKBLOOM_INJECT_DECODE_EMPTY\|DARKBLOOM_INJECT_EMPTY_TG"
```

must print `0` and `160`. Anything else stops the dispatch.

`submissionCommitSha` in the receipt will not equal the local SHA; receipts are
mapped by timestamp, and the service dedupes byte-identical archives.

## 5. Derived timings, for the record

```
S = 512000 * prefill_s_per_tok            # prefill window, ms
T = 1000 * decode_s_per_tok - S / 128     # per-step decode, ms
```

Both are reported alongside `ns` so a future reader can recompute the split
without the receipt's own baseline.
