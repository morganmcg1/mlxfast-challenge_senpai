#!/bin/bash
# One-hot coherent-addressing sweep over the decode QKV NVFP4 scale plane.
#
# For each probe index L in the argument list, group L's reconstructed scale is
# replaced by group (L+1)&127's scale in BOTH the fitting and the escaped arm of
# `lagunaDecodeNVFP4QKVLaneMajorSource`. The probe index is delivered through
# `DARKBLOOM_LM_PROBE`, which is interpolated into the JIT kernel source, so no
# rebuild is needed between L values and `Sources/` stays byte-identical.
#
# Result is appended to $OUT as
#   L,passed,checked_steps,first_failing_step,first_failing_case,expected,actual,seconds
#
# Usage: research/frieren_pr35_lm_probe_sweep.sh 1 3 5 ...
set -u

OUT="${OUT:-/tmp/pr35_lm_sweep.csv}"
WORKER="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-$PWD/.build-worker/release/mlxfast-runtime-worker}"
CLI="${CLI:-$PWD/.build/release/mlxfast-swift}"
GOLDEN="${GOLDEN:-correctness_prompts/public_longcopy_gate_english_512_256.json}"

if [[ ! -x "$WORKER" ]]; then echo "missing worker: $WORKER" >&2; exit 2; fi
if [[ ! -x "$CLI" ]]; then echo "missing cli: $CLI" >&2; exit 2; fi
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$WORKER"

for L in "$@"; do
    json="/tmp/pr35_sweep_probe${L}.json"
    t0=$(date +%s)
    MLXFAST_NO_SANDBOX=1 DARKBLOOM_LM_PROBE="$L" \
        "$CLI" correctness --weights weights --golden "$GOLDEN" \
        >"$json" 2>"/tmp/pr35_sweep_probe${L}.err"
    rc=$?
    t1=$(date +%s)
    L="$L" RC="$rc" SECS=$(( t1 - t0 )) JSON="$json" OUT="$OUT" python3 - <<'PY'
import json, os, sys
L = os.environ["L"]; rc = os.environ["RC"]; secs = os.environ["SECS"]
raw = open(os.environ["JSON"]).read()
row = None
i = raw.find("{")
if i >= 0:
    dec = json.JSONDecoder()
    try:
        row, _ = dec.raw_decode(raw[i:])
    except Exception as exc:
        print(f"probe {L}: parse failure {exc}", file=sys.stderr)
if row is None:
    line = f"{L},PARSE_FAIL,,,,,,{secs}"
else:
    line = ",".join(str(row.get(k, "")) for k in (
        "passed", "checked_steps", "first_failing_step", "first_failing_case",
        "expected_token", "actual_token"))
    line = f"{L},{line},{secs}"
with open(os.environ["OUT"], "a") as fh:
    fh.write(line + "\n")
print(f"rc={rc} {line}")
PY
done
