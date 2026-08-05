#!/usr/bin/env bash
# PR35 r3, V3 + V4c in one session: the shipping 1024-step golden gate, run
# clean and then fault-injected.
#
# V3 (clean) is the bit-exactness proof the brief requires: passed:true,
# max_abs_diff 0, checked_steps 1025, flat peak_ram_gb, on the exact shipping
# code with no research hook compiled in.
#
# V4c (fault) is the tier-3 power control. Two instruments are already shown
# blind to a lane-major scale ADDRESSING fault (greedy probe: modes 5/6/1 gave
# 0 divergences at 128 steps; upstream-equivalence oracle: structurally never
# builds the bank). The golden gate runs through LagunaRuntimeWeightCache, so
# it provably does build and dispatch the bank, and --local-submit checks 1025
# steps -- 8x the greedy probe.
#
# PASS for V4c = the fault arm reports passed:false or max_abs_diff != 0.
# FAIL = no available external instrument can see an addressing permutation,
#        which is itself the reportable result.
#
# Mode 5 (reverse the four K-block codes inside a lane's word) is the
# discriminating fault. Mode 6 (read the word 16 lanes away) runs only if 5 is
# silent and there is wall clock left, to make the negative claim independent.
set -u
cd "$(dirname "$0")/.."

patch="research/frieren-pr35-lanemajor-fault.patch"
start=$(date +%s)

readout() {
    local tag="$1" log="$2" score="$3"
    echo "--- ${tag}: score fields ---"
    if [[ -f "${score}" ]]; then
        python3 - "${score}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{p}/{k}")
    else:
        yield p, o
keys = ("passed", "max_abs_diff", "checked_steps", "golden_hash", "peak_ram_gb",
        "divergen", "first_fail", "case_count", "seconds_per_token", "speedup",
        "error", "reason")
for p, v in walk(d):
    if any(k in p.lower() for k in keys):
        print(f"{p} = {v}")
PY
    else
        echo "NO SCORE FILE at ${score}"
    fi
    echo "--- ${tag}: log lines ---"
    grep -nE 'lane-major|narrow-scales|max_abs_diff|checked_steps|passed|divergen|FAIL|error' "${log}" \
        | tail -25
}

echo "=== V3: clean --local-submit at HEAD $(git rev-parse --short HEAD) ==="
git status --short
clean_log=/tmp/pr35_gate_clean.txt
env DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 ./benchmark.sh --local-submit >"${clean_log}" 2>&1
rc=$?
echo "clean exit=${rc} elapsed=$(( $(date +%s) - start ))s"
cp -f score.json /tmp/pr35_gate_clean_score.json 2>/dev/null
readout CLEAN "${clean_log}" /tmp/pr35_gate_clean_score.json

if ! grep -q '"passed" *: *true' /tmp/pr35_gate_clean_score.json 2>/dev/null; then
    echo "=== CLEAN ARM DID NOT REPORT passed:true - stopping, fault arm would be meaningless ==="
    exit 1
fi

run_fault() {
    local mode="$1"
    local log="/tmp/pr35_gate_fault${mode}.txt"
    echo "=== V4c: fault-injected --local-submit, DARKBLOOM_LM_FAULT=${mode} ==="
    git apply "${patch}" || { echo "PATCH FAILED"; return 2; }
    env DARKBLOOM_LM_FAULT="${mode}" DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
        ./benchmark.sh --local-submit >"${log}" 2>&1
    local frc=$?
    git checkout -- Sources/
    echo "fault${mode} exit=${frc} elapsed=$(( $(date +%s) - start ))s"
    cp -f score.json "/tmp/pr35_gate_fault${mode}_score.json" 2>/dev/null
    readout "FAULT${mode}" "${log}" "/tmp/pr35_gate_fault${mode}_score.json"
    if grep -q '"passed" *: *true' "/tmp/pr35_gate_fault${mode}_score.json" 2>/dev/null; then
        echo "VERDICT mode ${mode}: SILENT (gate still passed) - instrument has no power here"
        return 1
    fi
    echo "VERDICT mode ${mode}: FLAGGED - the gate is a real addressing certificate"
    return 0
}

trap 'git checkout -- Sources/ 2>/dev/null' EXIT

if run_fault 5; then
    echo "=== done: mode 5 flagged, no further arm needed ==="
    exit 0
fi

elapsed=$(( $(date +%s) - start ))
if (( elapsed < 3000 )); then
    run_fault 6 || true
else
    echo "=== skipping mode 6: ${elapsed}s already spent ==="
fi
echo "=== done elapsed=$(( $(date +%s) - start ))s ==="
