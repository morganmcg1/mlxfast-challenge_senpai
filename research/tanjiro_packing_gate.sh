#!/usr/bin/env bash
# Research-only per-arm golden correctness gate for the packing curve.
#
#   research/tanjiro_packing_gate.sh /tmp/tanjiro/gate [ARMS...]
#   EXPECT=fail research/tanjiro_packing_gate.sh /tmp/tanjiro/fault 2 16
#
# Runs the trusted CLI's public golden gate once per simdgroups-per-threadgroup
# value and prints `passed`, `checked_steps`, `first_failing_case/step`, and
# `golden_hash` for each. The CLI verdict field is a boolean `passed` plus
# failure locators; there is no numeric tolerance field, because the gate is
# exact greedy-token equality rather than an epsilon compare.
#
# With EXPECT=fail the script inverts its own success criterion: it is being used
# as a fault-injection control, so an arm that *passes* means the tripwire is not
# load-bearing and the whole sweep is uninterpretable. That case exits 2, copying
# PR #300's discipline of making a non-falsifiable gate a hard error rather than a
# footnote.
set -uo pipefail
OUTDIR="${1:?outdir}"; shift
ARMS="${*:-1 2 4 8 16 32}"
EXPECT="${EXPECT:-pass}"
WORKER="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-$PWD/.build-worker/release/mlxfast-runtime-worker}"
CLI="${CLI:-$PWD/.build/release/mlxfast-swift}"
GOLDEN="${GOLDEN:-correctness_prompts/public_longcopy_gate_english_512_256.json}"
[[ -x "$WORKER" ]] || { echo "missing worker: $WORKER" >&2; exit 2; }
[[ -x "$CLI" ]] || { echo "missing cli: $CLI" >&2; exit 2; }
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$WORKER"
mkdir -p "$OUTDIR"

bad=0
for sg in ${ARMS}; do
  echo "=== $(date -u +%H:%M:%S) gate S=${sg} (expect ${EXPECT})"
  MLXFAST_NO_SANDBOX=1 \
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0 \
    "$CLI" correctness --weights weights --golden "$GOLDEN" \
    > "${OUTDIR}/gate_s${sg}.json" 2> "${OUTDIR}/gate_s${sg}.err"
  rc=$?
  SG="${sg}" RC="${rc}" EXPECT="${EXPECT}" JSON="${OUTDIR}/gate_s${sg}.json" python3 - <<'PY' || bad=1
import json, os, sys
sg, rc, expect = os.environ["SG"], os.environ["RC"], os.environ["EXPECT"]
raw = open(os.environ["JSON"]).read()
row = {}
i = raw.find("{")
if i >= 0:
    try:
        row, _ = json.JSONDecoder().raw_decode(raw[i:])
    except Exception as exc:
        print(f"  S={sg}: unparseable gate output: {exc}", file=sys.stderr)
passed = row.get("passed")
print(f"  S={sg:>2s} rc={rc} passed={passed} "
      f"checked_steps={row.get('checked_steps')} "
      f"cases={row.get('case_count')} "
      f"first_failing_case={row.get('first_failing_case')} "
      f"first_failing_step={row.get('first_failing_step')} "
      f"golden_hash={str(row.get('golden_hash'))[:16]} "
      f"error={row.get('error')!r}")
ok = (passed is True and rc == "0") if expect == "pass" else (passed is not True or rc != "0")
if not ok:
    print(f"  S={sg}: UNEXPECTED gate verdict (expected {expect})", file=sys.stderr)
    sys.exit(1)
PY
done

if [[ "${bad}" != "0" ]]; then
  if [[ "${EXPECT}" == "fail" ]]; then
    echo "FAULT INJECTION INVALID: an injected-fault arm passed the golden gate." >&2
    echo "The tripwire is not load-bearing; Stage 1 is INVALID." >&2
  else
    echo "GOLDEN GATE FAILED for at least one arm; the repack is not bit-exact." >&2
  fi
  exit 2
fi
echo "=== $(date -u +%H:%M:%S) all arms matched EXPECT=${EXPECT}"
