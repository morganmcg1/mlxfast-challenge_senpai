#!/usr/bin/env bash
# Research-only (PR #457, R85-C stage 3): does displacing the halved plane's
# address change PR #443's six-kernel give-back?
#
# Stage 2 showed the give-back tracks the *read* switch and not the prep-time
# allocation dose, so the remaining placement variant is the address of the
# buffer the decode kernel actually reads. `halved_pad` materializes and
# retains a five-page (80 KiB) pad immediately before each of the 39 planes,
# leaving the read pattern, the byte count and the tokens identical.
#
# Five pages is chosen so the per-plane allocation stride becomes 8 x 16 KiB =
# 128 KiB instead of 3 x 16 KiB = 48 KiB. A power-of-two stride is the
# maximally aliasing configuration, so if cache-set or DRAM-bank aliasing of
# the read set drives the give-back this arm should amplify it, not just
# perturb it.
#
#   bash research/maple_r85_pad_session.sh
set -uo pipefail

# The `base halved` duplexes are a within-session positive control: a null pad
# result is only interpretable if the give-back it is meant to move is visible
# in the same session. Offset 0 pairs slots (1,2) (3,4) (5,6) (7,8), so each
# rep contributes one forward and one reversed duplex of both contrasts.
export ARMS="base halved halved_pad"
export ORDER="halved halved_pad halved_pad halved base halved halved base"
export REPS="${REPS:-5}"
export PAD_PAGES="${PAD_PAGES:-5}"
export INERT_OUT="${INERT_OUT:-/tmp/maple-r85-pad-inert}"
export ARMS_OUT="${ARMS_OUT:-/tmp/maple-r85-pad-arms}"

bash research/maple_r85_session.sh
