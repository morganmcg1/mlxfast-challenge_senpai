#!/bin/bash
# R102-A rung 1: split-invariant fixed cost of the decode attention kernel.
#
# Measures tau(N) = f + c*N for one threadgroup of
# `laguna_sliding_fused_attn_ring_v1` by rewriting only the KV row-loop bound,
# then emulates a work- and byte-conserving KV split directly.
#
# Blocks:
#   R   resident   N sweep, ladder 20/32/40/64/128
#   D   defeat     N sweep, ladder 20/32/40, unique bytes held at ~100 MiB
#   M3D defeat     work/byte-conserving split emulation at fixed slot spread
#
# All three use the probe's interleaved row sweep: one process, one pipeline per
# N built up front, and every round visits the N points in rotating order. A
# first attempt used one process per N and the resulting block-order drift
# reached 14% with inconsistent sign, which an intercept fit cannot survive.
#
# Every invocation is also its own NULL control twice over: the probe builds the
# same kernel twice and reports the paired base-vs-itself delta (null N-A), and
# N=512 appears twice in each sweep list so the two columns must agree.

set -u
cd "$(dirname "$0")/.."

OUT=research/artifacts/frieren-r102
mkdir -p "$OUT"
PROBE=/tmp/fernattn
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift

export FERN_ROUNDS=${FERN_ROUNDS:-21}
export FERN_REPS=${FERN_REPS:-2000}

# Rule 75: the submitted surface must be byte-identical before the build and
# after the last timed dispatch.
digest() {
  find Sources Vendor -type f \( -name '*.swift' -o -name '*.metal' -o -name '*.h' \
    -o -name '*.cpp' \) -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256
}

echo "=== rule 75 surface digest (pre-build) ===" | tee "$OUT/surface_digest.txt"
digest | tee -a "$OUT/surface_digest.txt"
echo "=== host state (pre) ===" | tee -a "$OUT/surface_digest.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee -a "$OUT/surface_digest.txt"
pgrep -fl 'benchmark|mlxfast-worker' | tee -a "$OUT/surface_digest.txt"
echo "(empty pgrep list above means no competing model-holding process)" \
  | tee -a "$OUT/surface_digest.txt"

xcrun swiftc -O research/fern_r100_attn_probe.swift -o "$PROBE" || exit 1

# BLOCKS selects which measurement blocks run; the default is all of them.
# Re-running a subset never clobbers the logs of a block that is not selected.
BLOCKS=${BLOCKS:-R_sweep,D_sweep,M3D,F2,F2D}

run() { # run <tag> <sweep-rows> <ladder> [extra env assignments...]
  local tag=$1 sweep=$2 ladder=$3
  shift 3
  case ",$BLOCKS," in *",$tag,"*) ;; *) echo "--- $tag skipped"; return ;; esac
  echo ">>> $tag  sweep=$sweep ladder=$ladder $*"
  env FERN_ROWS_SWEEP="$sweep" FERN_LADDER="$ladder" "$@" \
    "$PROBE" "$SRC" >"$OUT/$tag.log" 2>&1 \
    || echo "!!! $tag FAILED"
}

# ---- Block R: resident, N sweep ------------------------------------------
run R_sweep 512,384,256,128,96,512 20,32,40,64,128 \
  FERN_DEFEAT_SLOTS=1 FERN_CACHE_COPIES=1

# ---- Block D: SLC-defeat, N sweep, unique bytes held constant -------------
# Slot stride pinned to 32 kv-heads (4 MiB) so the address spread per slot is
# identical at every N; FERN_MATCH_BYTES scales the slot count as 512/N so the
# DRAM working set stays ~100 MiB and no point falls back into the ~24 MiB SLC.
run D_sweep 512,384,256,128,96,512 20,32,40 \
  FERN_STRIDE_KV=32 FERN_CACHE_COPIES=64 FERN_DEFEAT_SLOTS=48 FERN_MATCH_BYTES=1

# ---- Block M3D: split emulation under SLC defeat --------------------------
# The diagonal (K,N) = (32,512) (64,256) (128,128) conserves threadgroup-rows
# AND kv-head-rows, so at a pinned stride and a fixed slot count all three read
# the same bytes from the same address spread. Only the threadgroup count
# differs. Byte matching is off here precisely so the diagonal stays matched.
run M3D 512,256,128,512 32,64,128 \
  FERN_STRIDE_KV=32 FERN_CACHE_COPIES=12 FERN_DEFEAT_SLOTS=48

# ---- Block F2/F2D: falsify the model's own predicted win -------------------
# The wave model predicts that full attention (K_real = 24 threadgroups) DOES
# win from a 2-way split on a 20-core host, because (24,W=2) -> (48,W=3) adds
# one wave while halving the ring. The byte-matched diagonal is
# (K=24,N=512) = 6 kv-heads x 512 rows vs (K=48,N=256) = 12 x 256. N=96 gives
# the M=0 fixed-cost anchor for both K, and the trailing 512 is the drift check.
# A confirmed win makes the model predictive rather than merely descriptive;
# a loss closes the split-K family harder than the sliding arm alone can.
run F2  512,256,96,512 24,48 \
  FERN_DEFEAT_SLOTS=1 FERN_CACHE_COPIES=1
run F2D 512,256,96,512 24,48 \
  FERN_STRIDE_KV=32 FERN_CACHE_COPIES=12 FERN_DEFEAT_SLOTS=48

echo "=== rule 75 surface digest (post-timing) ===" | tee -a "$OUT/surface_digest.txt"
digest | tee -a "$OUT/surface_digest.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee -a "$OUT/surface_digest.txt"
pgrep -fl 'benchmark|mlxfast-worker' | tee -a "$OUT/surface_digest.txt"
echo "done"
