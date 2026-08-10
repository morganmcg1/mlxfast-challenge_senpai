Laguna decode-path integration draw — team maple, R108 integration freeze.

(Do not add a `Model:` line here. The CLI prepends `Model: senpai\n\n` itself; a second
one would be duplicated in the stored note.)

STATUS OF THIS FILE: pre-written skeleton, prepared 2026-08-10T16:2xZ, ahead of the
07:00Z integration freeze. Sections marked [[FIXED]] are candidate-independent and are
final. Sections marked [[FILL]] are candidate-dependent and must be completed from the
handoff certificate before this file is passed to `--note-file`. The file as it stands
already clears the 5,105-byte body floor (see BYTE FLOOR below), so completing the
[[FILL]] blocks can only make it longer, never shorter, and cannot push it under.

================================================================================
1. WHAT IS BEING SUBMITTED                                              [[FILL]]
================================================================================

base commit ............ 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7   [[FIXED]]
submitted tree ......... <HEAD sha from handoff certificate>
change class ........... <e.g. decode dispatch-count reduction (R108-K family <X>)>
files touched .......... <from `git diff --numstat BASE HEAD -- Sources Vendor`>
editable-surface bytes .. <total>/3,000,000 ; largest file <n>/524,288
                          growth vs base <n>/262,144
named mechanism ........ <Rule 81 label: the mechanism, not the metric>

The submitted archive is a tar of the 97 `editablePaths` entries taken from the WORKING
TREE, not from the commit. It is only equal to the commit because predicate 12 of
`senpai/submit-official.sh` (`git status --porcelain -uall --ignored=matching` over
`Sources/` and `Vendor/`) was green at submit time; the certificate records that check.
Measured archive size for the unmodified tree is 428,038 bytes over 148 entries, i.e.
1.6 % of the 25 MiB `SUBMISSION_ARCHIVE_MAX_BYTES` cap, so size is not a live risk.

================================================================================
2. EXPECTED EFFECT, AND THE ARITHMETIC BEHIND IT                        [[FILL]]
================================================================================

Predicted delta on composite score .... <g> % of cs
Probability this clears the record gap  <P> (Rule 101 record gap 1.6359 %, z = 5.42)
Decision band (freeze rule §9.4) ...... <HOLD | HOLD-and-say-why | armed | TAKE>

Conversion used (Rule 105): Δ%cs = Δ_M4[µs/step] × k × 0.015228, where 1 % of composite
score is 65.67 M5 µs/step of decode and cs ≈ 6580.8 M5 µs. The multiplier k depends on
the regime the change lives in and is NOT a free parameter:

  k_dispatch = 1.890   dispatch-count reduction (Rule 65: an added dispatch costs
                       2.3403 M5 µs; Rule 57: M4 marginal glue 1.2382 µs; the ratio is
                       a tautology, 2.3403/1.2382 = 1.8901, not an independent finding)
  k_steady   = 0.4902  steady-state kernel-body work
  alpha      = 0.4369  byte-traffic pricing, two-pool map (see §3)
  beta       = 0.5     the other pool of that same map

In M4 µs/step, the 0.4 % reporting bar is therefore 13.90 µs/step under k_dispatch,
53.59 under k_steady, 52.53 under beta, and 60.12 under alpha. The single-receipt M4
detection floor is ≈80 µs/step (Rule 105.7), which is ABOVE every one of those: a single
local receipt cannot see a 0.4 % effect. This is why the draw is justified by a paired
instrument, not by a single before/after run.

================================================================================
3. PROVENANCE OF THE BYTE-PRICING CONSTANT                              [[FIXED]]
================================================================================

Mandatory provenance label, verbatim:

    alpha = 0.4369 / beta = 0.5 two-pool map, residual -6.63 %, #561

As of R108-M this constant is no longer merely inherited. I measured the host DRAM read
ceiling directly on this M4 Pro (20 GPU cores, 48 GiB, applegpu_g16s) with a 48-config
autotuned streaming probe:

    MEASURED dram_read_ceiling = 263.29 GB/s, range [262.37, 263.49], +/- 0.21 %
    cache_served_ceiling       = 1675.96 GB/s = 6.37x the DRAM ceiling
    SLC transition             between 12 and 20 MiB

That ceiling brackets alpha two-sidedly. A measured cross-host arm reproducing the
tanjiro byte census ran at 257.87 GB/s = 97.9 % of ceiling, which forces
alpha >= 257.87/610.0 = 0.42274; the routed-pool byte rate forces
597.1 x alpha <= 263.29, i.e. alpha <= 0.44095. So:

    alpha is bracketed to [0.4227, 0.4409]; the campaign value 0.4369 SURVIVES,
    sitting at the 78th percentile of that interval (-3.24 % / +0.93 % from the ends).

If 0.4369 is wrong it is wrong on the HIGH side, which means byte savings have been
priced at most 3.2 % too generously. Every byte-axis number in this campaign is
therefore an upper bound, not an optimistic guess, and re-pricing at the bracket ends
moves nothing across a decision-band boundary.

The same probe kills two denominators that were in circulation: 273.0 GB/s (r94) is
103.69 % of the measured ceiling and is unreachable; 266.3 GB/s (Rule 55's floor
constant `bytes/266.3 + 3.97`) is 101.14 % and should be restated as 263.29.

================================================================================
4. WHY THE EVIDENCE IS ADMISSIBLE                                       [[FILL]]
================================================================================

Instrument ............. <nezuko R107-J' paired --local-submit | fern ABBA>
Blocks / runs .......... <n>
Point estimate ......... <d(ln score)> %
CI95 ................... [<lo>, <hi>] %
Correctness ............ <gates/passed_correctness, checked_steps>

Two standing caveats travel with any number in this box, and I am not going to bury
them:

(a) The correctness gate is weaker than its name. `max_abs_diff` is hard-coded to 0 at
    all seven emit sites; the real gate is exact token-ID equality at
    Sources/MLXFastCore/Golden.swift:387 and :535, on a small fixture set. The
    `golden_hash b9509697c08a2cf3` that has been quoted as evidence is a digest of the
    fixture INPUT, so it carries zero information about outputs. Anything certified this
    way is "token-identical on the fixtures", Rule 105.15 class 2 — not bit-exact. The
    bit-exact column has been retired from the integration tree.

(b) Paired instruments are mandatory. Unpaired or level `--local-iterate` comparisons
    are not evidence (Rule 86), and kernel-local cache-resident numbers inflate by
    roughly 30x and must never be headlined (Rule 98.9). Where a null cell exists it is
    reported (Rule 79).

================================================================================
5. RISKS I AM ACCEPTING, EXPLICITLY                                     [[FIXED]]
================================================================================

R1. Prefill does not transfer between hosts. Decode M4->M5 transfers ~exactly, but
    prefill does not (M4 1.1198x vs M5 1.9834x, -43.54 %). No prefill delta in this
    submission is being converted to composite score (Rule 105.4).

R2. This host is gen 16 (`applegpu_g16s`). The `_nax` kernel family requires
    gen >= 17 (>= 18 for arch 'p') at device.cpp:1083-1101, so no `_nax` path is
    reachable here and none is claimed.

R3. Dedup is content-addressed on the archive, not on the note. An identical archive
    returns `result.job === null` with the heading "Submission already exists" and the
    new note is DISCARDED. A resubmission intended to attach better prose will silently
    lose that prose. If the tree is unchanged, do not resubmit.

R4. Resubmission noise is real: sd(ln cs) = 0.3607 %, sigma_resubmit = 0.3016 %. A
    clean +0.4 % still leaves z ~ 4.10 against the record gap. "No draw" remains the
    modal outcome (Rule 96.2) and is not a failure state.

R5. Two environment knobs stay UNSET and are not part of this draw:
    DARKBLOOM_QMV_WIDE_CODES (measured -0.5363 %, i.e. actively harmful) and
    DARKBLOOM_EXPERT_DOWN_BN. Neither is a wrapper predicate; both are advisory only.

================================================================================
6. BYTE FLOOR                                                           [[FIXED]]
================================================================================

`mlxfast submit` enforces SUBMISSION_NOTE_MIN_BYTES = 5 * 1024 = 5,120 bytes on the
STORED note, and the stored note is `Model: ${model}\n\n${rawNote}`. For model `senpai`
that prefix is 15 bytes, so the body of this file must be at least 5,105 bytes or the
call is rejected before the receipt is spent. The maximum is 100 * 1024 bytes.
`--note` and `--note-file` are mutually exclusive. `--model` is a requiredOption of the
CLI and is supplied by the wrapper as `senpai`; passing our own causes wrapper exit 2.

Verify before submitting:

    wc -c research/artifacts/maple-fern-r108m/draw_note.md   # must be >= 5105

Correct invocation, with no `--model`:

    bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
      --note-file research/artifacts/maple-fern-r108m/draw_note.md
