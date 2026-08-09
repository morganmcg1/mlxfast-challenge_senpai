#!/usr/bin/env bash
# R97-A Stage 2 smoke (research only, not part of the submission).
#
# Runs the teacher-forced decode probe once per rung state, selected by the
# shipped build-time env flags rather than the research rung map, and prints
# the token-stream hash and mismatch count for each. All three hashes must be
# identical and every mismatch count must be 0.
#
#   OUT=/tmp/r97/smoke STEPS=48 bash research/fern_r97_smoke.sh
set -uo pipefail
cd "$(dirname "$0")/.."

OUT="${OUT:-/tmp/r97/smoke}"
STEPS="${STEPS:-48}"
WORKER="${WORKER:-.build-worker/release/mlxfast-runtime-worker}"
mkdir -p "$OUT"

run_state() {
  local name="$1" gate="$2" down="$3"
  echo "=== state $name (BEXP_GATE_UP=$gate BEXP_DOWN=$down) $(date -u +%H:%M:%S) ==="
  DECODE_PROBE_WORKER="$WORKER" \
  DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
  DARKBLOOM_DENSE_BEXP_GATE_UP="$gate" DARKBLOOM_DENSE_BEXP_DOWN="$down" \
    python3 research/fern_r93_nested_probe.py \
      --runs 1 --steps "$STEPS" --warmup-runs 0 --no-thermals \
      --label "smoke-$name" --schedule const:0 \
      --stderr "$OUT/$name.err" --out "$OUT/$name.json" || return 1
  grep -iE "block.exponent|bexp|decline|certificate" "$OUT/$name.err" | sort | uniq -c
  return 0
}

run_state stock 0 0 || exit 1
run_state gateup 1 0 || exit 1
run_state both 1 1 || exit 1

python3 - "$OUT" <<'PY'
import json, sys, os
out = sys.argv[1]
hashes = {}
for name in ("stock", "gateup", "both"):
    d = json.load(open(os.path.join(out, name + ".json")))
    hashes[name] = (d["token_stream_hashes"], d["teacher_forced_mismatches"])
    print(name, d["token_stream_hashes"], "mismatches=", d["teacher_forced_mismatches"])
uniq = {h[0][0] for h in hashes.values()}
bad = any(h[1] for h in hashes.values())
print("PASS" if len(uniq) == 1 and not bad else "FAIL")
sys.exit(0 if len(uniq) == 1 and not bad else 1)
PY
