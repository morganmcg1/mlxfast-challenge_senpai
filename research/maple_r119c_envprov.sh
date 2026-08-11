#!/bin/bash
# R119-C provenance leg for L-MEASURE-AT-RANKED-STARTUP-PROFILE.
#
# Reads MLX_MAX_OPS_PER_BUFFER / MLX_MAX_MB_PER_BUFFER / MLX_BFS_MAX_WIDTH with
# getenv from inside the worker process after the startup memory policy has run,
# so an export that the policy discards with overwrite=1 cannot be mistaken for
# the effective value. Three decode steps; this is a readback, not a timing run.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=research/r119c-runs/envprov
mkdir -p "$OUT"

swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3
git checkout -- Package.resolved 2>/dev/null || true

# Cell 1: exactly what the atlas ran (nothing exported).
# Cell 2: an export the low-memory policy is expected to discard, which is the
# failure mode the law warns about.
for cell in default exported; do
  extra=(DARKBLOOM_ENV_READBACK=1)
  if [ "$cell" = exported ]; then
    extra+=(MLX_MAX_OPS_PER_BUFFER=200 MLX_MAX_MB_PER_BUFFER=200 MLX_BFS_MAX_WIDTH=50)
  fi
  echo "=== cell=$cell ==="
  env "${extra[@]}" \
    python3 research/decode_probe.py --steps 3 \
      --stderr "$OUT/$cell.err" > "$OUT/$cell.log" 2>&1
  echo "rc=$?"
  grep -m1 "ENV_READBACK" "$OUT/$cell.err" | tee -a "$OUT/readback.txt"
  grep -m1 "low-memory startup profile active" "$OUT/$cell.err" \
    | cut -c1-140 | tee -a "$OUT/readback.txt"
  # The stderr capture is large and reproducible; keep only the readback.
  rm -f "$OUT/$cell.err"
done
echo "--- readback ---"
cat "$OUT/readback.txt"
