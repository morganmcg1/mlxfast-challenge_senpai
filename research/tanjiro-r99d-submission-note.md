Anchor submission: unmodified frontier snapshot, no candidate change.

This submits the editable surface exactly as recorded at base
`c6c66344d9848d95158edc31f31943aabe4de079`, with a verified empty diff against
that base across `Sources/`, `Vendor/` and `benchmark.json`. It is deliberately
not an optimization attempt.

Three purposes:

1. **Re-anchor.** Our prior paired anchors were measured on an earlier snapshot.
   The frontier has since moved, so every stored speedup pair is cross-snapshot
   and cannot be differenced against a new candidate. This run restores a
   same-session paired anchor on the current surface.
2. **Soundness check.** The current frontier includes an operator-applied
   snapshot move that has not yet been validated end to end by an official run.
   Submitting it unmodified separates "the snapshot is healthy" from "our
   candidate is good", so a future failure cannot be mis-attributed.
3. **Free draw.** The measurement is paired and correctness-gated regardless, so
   the run also samples baseline health on the ranked host at no extra cost.

Expected verdict: correctness pass, both floors pass, and a ranking status of
`rejected` in the sense of "did not beat current best" — which for an
unmodified snapshot is the intended outcome, not a failure.

_This submission was dispatched by an AI agent (OpenHands) on behalf of the
Senpai research campaign._
