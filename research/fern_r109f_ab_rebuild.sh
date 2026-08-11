#!/usr/bin/env bash
# fern R109-F: rebuild the scored worker from the current worktree and run the
# local-iterate benchmark, archiving the score under a caller-supplied label.
#
# Usage: bash research/fern_r109f_ab_rebuild.sh <label>
#
# The metallib and swift builds are incremental (CMake + SwiftPM scratch path
# .build-worker), so an A/B that only touches Sources/ + Vendor/ rebuilds just
# the changed translation units.  The harness itself (benchmark.sh, tools/) is
# NOT part of the A/B: it stays at the integration-branch revision so that
# harness_hash is constant across arms.
set -uo pipefail

label="${1:?usage: fern_r109f_ab_rebuild.sh <label>}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

outdir="research/artifacts/fern-r109f/ab"
mkdir -p "$outdir"

echo "=== [$label] worktree provenance ==="
git rev-parse HEAD
git status --porcelain | head -20
echo

echo "=== [$label] metallib build ==="
if ! bash tools/build-mlx-metallib.sh; then
  echo "FAIL: metallib build failed for $label" >&2
  exit 10
fi
ls -l .build-worker/release/mlx.metallib
echo

echo "=== [$label] swift worker build ==="
if ! swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker; then
  echo "FAIL: swift worker build failed for $label" >&2
  exit 11
fi
ls -l .build-worker/release/mlxfast-runtime-worker
echo

echo "=== [$label] local-iterate benchmark ==="
if ! bash benchmark.sh --local-iterate; then
  echo "FAIL: benchmark failed for $label" >&2
  exit 12
fi

cp score.local-iterate.json "$outdir/score.$label.json"
echo
echo "=== [$label] archived $outdir/score.$label.json ==="
python3 - "$outdir/score.$label.json" "$label" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))["metrics"]
print("%-28s decode %.6f s/tok  prefill %.6f s/tok  correct=%s" % (
    sys.argv[2],
    m["decode_seconds_per_token"],
    m["prefill_seconds_per_token"],
    m["passed_correctness"],
))
PY
