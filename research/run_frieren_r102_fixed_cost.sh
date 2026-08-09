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
# Every invocation is its own NULL control: the probe builds the same kernel
# twice and reports the paired base-vs-itself delta (null N-A).

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

run() { # run <tag> <rows> <ladder> [extra env assignments...]
  local tag=$1 rows=$2 ladder=$3
  shift 3
  echo ">>> $tag  rows=$rows ladder=$ladder $*"
  env FERN_ROWS="$rows" FERN_LADDER="$ladder" "$@" \
    "$PROBE" "$SRC" >"$OUT/$tag.log" 2>&1 \
    || echo "!!! $tag FAILED"
}

# ---- Block R: resident, N sweep ------------------------------------------
for N in 512 384 256 128 96; do
  run "R_n$N" "$N" 20,32,40,64,128 FERN_DEFEAT_SLOTS=1 FERN_CACHE_COPIES=1
done

# ---- Block D: SLC-defeat, N sweep, unique bytes held constant -------------
# Slot stride pinned to 32 kv-heads (4 MiB) so address spread is identical at
# every N; slot count scaled as 512/N so the DRAM working set stays ~100 MiB
# and no point is allowed to fall back into the ~24 MiB SLC.
for pair in "512 48" "384 64" "256 96" "128 192" "96 256"; do
  set -- $pair
  run "D_n$1" "$1" 20,32,40 \
    FERN_STRIDE_KV=32 FERN_CACHE_COPIES=64 FERN_DEFEAT_SLOTS="$2"
done

# ---- Block M3D: split emulation under SLC defeat --------------------------
# (K,N) = (32,512) (64,256) (128,128) conserve threadgroup-rows AND kv-head-rows,
# so with a pinned stride and slot count all three read the same bytes from the
# same address spread. Only the threadgroup count differs.
for pair in "32 512" "64 256" "128 128"; do
  set -- $pair
  run "M3D_k$1" "$2" "$1" \
    FERN_STRIDE_KV=32 FERN_CACHE_COPIES=12 FERN_DEFEAT_SLOTS=48
done

echo "=== rule 75 surface digest (post-timing) ===" | tee -a "$OUT/surface_digest.txt"
digest | tee -a "$OUT/surface_digest.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ" | tee -a "$OUT/surface_digest.txt"
pgrep -fl 'benchmark|mlxfast-worker' | tee -a "$OUT/surface_digest.txt"
echo "done"
