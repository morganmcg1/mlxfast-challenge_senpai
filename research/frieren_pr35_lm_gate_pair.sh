#!/usr/bin/env bash
# PR35 r3: V3 (shipping golden gate, clean) and V4c (the same gate, fault
# injected) in one session.
#
# V3 is the bit-exactness proof the brief requires: passed:true, max_abs_diff 0,
# checked_steps 1025, on the exact shipping code with no research hook compiled
# in.
#
# V4c is the tier-3 power control. Two instruments are already shown blind to a
# lane-major scale ADDRESSING fault (greedy probe: modes 5/6/1 gave 0
# divergences at 128 steps; upstream-equivalence oracle: structurally never
# builds the bank, so neither arm ever executes the path). The golden gate runs
# through LagunaRuntimeWeightCache, so it provably does build and dispatch the
# bank, and --local-submit checks 1025 steps, 8x the greedy probe.
#
# Mode 5 (reverse the four K-block codes inside a lane's word) is the
# discriminating fault: it moves a code across columns 512 apart, where
# neighbouring-group correlation cannot mask the swap.
#
# THERMAL HONESTY. This host idles at ~39.9C GPU against a 40C gate threshold,
# and a previous V3 aborted on COOL_GATE_STALL_SECONDS at a 40.7C floor with no
# competing GPU load. A thermal abort ALSO writes passed:false, so the verdict
# logic below refuses to read passed:false as fault detection unless correctness
# actually ran (checked_steps > 0). Each arm makes one honest gated attempt and
# only falls back to MLXFAST_LOCAL_COOL_GATE=0 after a demonstrated thermal
# abort. That fallback voids the run's TIMINGS, which are already documented
# non-instruments on a sub-64GiB host (prefill_speedup 0.327x when
# byte-identical); it does not touch the correctness verdict, which is all V3
# and V4c consume.
set -u
cd "$(dirname "$0")/.."

patch="research/frieren-pr35-lanemajor-fault.patch"
start=$(date +%s)
macmon="${HOME}/bin/macmon"

elapsed() { echo $(( $(date +%s) - start )); }

gpu_temp() {
    [[ -x "${macmon}" ]] || { echo "na"; return; }
    "${macmon}" pipe -s1 2>/dev/null | jq -r '.temp.gpu_temp_avg // empty' 2>/dev/null
}

# Bounded idle wait so a second full pass does not start into its own heat soak.
# Not a polling loop on a tool-owned resource: this is the run's own pacing.
cool_wait() {
    local budget="$1" t
    local deadline=$(( $(date +%s) + budget ))
    while (( $(date +%s) < deadline )); do
        t=$(gpu_temp)
        [[ -z "${t}" || "${t}" == "na" ]] && return 0
        awk -v v="${t}" 'BEGIN{exit !(v<=39.0)}' && {
            echo "[cool_wait] gpu=${t}C ok after $(( budget - (deadline - $(date +%s)) ))s"
            return 0
        }
        sleep 15
    done
    echo "[cool_wait] gave up after ${budget}s, gpu=$(gpu_temp)C"
}

# Classify a finished --local-submit from its score.json.
#   pass       correctness ran and matched
#   fail       correctness ran and did NOT match
#   thermal    cool-down gate aborted before correctness ran
#   broken     anything else
#
# NOTE ON SHAPE: score.json is {passed, score, metrics{...}}. checked_steps,
# error, max_abs_diff, golden_hash and commit all live under .metrics, not at
# top level. Reading them at top level silently yields None/0 and misclassifies
# every arm as "broken", which is exactly how a thermal abort could have been
# mistaken for a clean pass.
classify() {
    python3 - "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("broken no-score-file"); sys.exit()
m = d.get("metrics") or {}
err = m.get("error") or ""
steps = m.get("checked_steps") or 0
passed = d.get("passed")
if "cool-down gate" in err or "cool_down" in err:
    print(f"thermal steps={steps} err={err}"); sys.exit()
if steps == 0:
    print(f"broken steps=0 passed={passed} err={err!r}"); sys.exit()
print(("pass" if passed else "fail")
      + f" steps={steps} max_abs_diff={m.get('max_abs_diff')}"
      + f" golden_hash={str(m.get('golden_hash'))[:16]} peak_ram_gb={m.get('peak_ram_gb')}"
      + (f" err={err}" if err else ""))
PY
}

readout() {
    local tag="$1" log="$2" score="$3"
    echo "--- ${tag}: classify -> $(classify "${score}") ---"
    echo "--- ${tag}: score fields ---"
    python3 - "${score}" <<'PY' 2>/dev/null || echo "(no score file)"
import json, sys
d = json.load(open(sys.argv[1]))
m = d.get("metrics") or {}
for k in ("passed", "score"):
    print(f"  {k} = {d.get(k)}")
for k in ("max_abs_diff","checked_steps","golden_hash","correctness_seconds",
          "peak_ram_gb","mlx_peak_gb","error","commit","benchmark_wall_seconds",
          "decode_speedup","prefill_speedup","seconds_per_token",
          "weights_hash","harness_hash"):
    if k in m: print(f"  metrics.{k} = {m[k]}")
PY
    echo "--- ${tag}: log tail ---"
    grep -nE 'lane-major|narrow-scales|max_abs_diff|checked_steps|divergen|thermal|cool|ERROR|FAIL' \
        "${log}" 2>/dev/null | tail -20
}

# Run one --local-submit arm. $1=tag  $2=extra env assignments (may be empty)
# Sets ARM_CLASS / ARM_LOG / ARM_SCORE.
run_arm() {
    local tag="$1"; shift
    local log="/tmp/pr35_gate_${tag}.txt"
    local score="/tmp/pr35_gate_${tag}_score.json"
    echo "=== arm ${tag}: env[$*] gpu=$(gpu_temp)C t=$(elapsed)s ==="
    env "$@" DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 ./benchmark.sh --local-submit \
        >"${log}" 2>&1
    echo "arm ${tag} exit=$? t=$(elapsed)s"
    cp -f score.json "${score}" 2>/dev/null
    readout "${tag}" "${log}" "${score}"
    ARM_CLASS=$(classify "${score}")
    ARM_LOG="${log}"; ARM_SCORE="${score}"
}

restore_sources() {
    git checkout -- Sources/ 2>/dev/null
    if grep -rqn 'LM_FAULT\|lagunaLaneMajorFaultMode' Sources/ 2>/dev/null; then
        echo "!!! Sources/ STILL CARRIES THE FAULT HOOK - DO NOT SUBMIT !!!"
    fi
}
trap restore_sources EXIT

echo "=== HEAD $(git rev-parse --short HEAD); worktree: ==="
git status --short
echo "=== start gpu=$(gpu_temp)C ==="

# ---------------------------------------------------------------- V3, clean
# Scalar, not an array: this host runs bash 3.2, where expanding an empty array
# under `set -u` aborts the script.
COOL_ENV=""
run_arm v3_gated
case "${ARM_CLASS}" in
  thermal*)
    echo "=== V3 gated attempt aborted thermally; retrying ungated (correctness only) ==="
    cool_wait 120
    COOL_ENV="MLXFAST_LOCAL_COOL_GATE=0"
    run_arm v3_ungated ${COOL_ENV}
    ;;
esac
V3_CLASS="${ARM_CLASS}"
echo "### V3 VERDICT: ${V3_CLASS}"

case "${V3_CLASS}" in
  pass*) : ;;
  *) echo "### V3 did not pass. A fault arm would be uninterpretable. Stopping."
     exit 1 ;;
esac

# ---------------------------------------------------------------- V4c, fault
cool_wait 180
echo "=== applying fault patch (mode 5) ==="
git apply "${patch}" || { echo "PATCH FAILED - V4c not run"; exit 3; }
run_arm v4c_mode5 DARKBLOOM_LM_FAULT=5 ${COOL_ENV}
F_CLASS="${ARM_CLASS}"
restore_sources

case "${F_CLASS}" in
  fail*)
    echo "### V4c VERDICT: FLAGGED. The 1025-step golden gate detects a"
    echo "### lane-major addressing permutation. B has a real external"
    echo "### addressing certificate, not only the analytic argument."
    ;;
  pass*)
    echo "### V4c VERDICT: SILENT. The golden gate ran 1025 checked steps and"
    echo "### still matched under mode 5. No available external instrument can"
    echo "### see a lane-major addressing permutation; B's addressing rests on"
    echo "### the analytic derivation plus the reconstruction certificate, and"
    echo "### the one-hot 128-probe design in the b-verification note is the"
    echo "### only route to a real certificate. This negative is the result."
    ;;
  *)
    echo "### V4c VERDICT: INCONCLUSIVE (${F_CLASS}). Not evidence either way."
    ;;
esac
echo "=== done t=$(elapsed)s gpu=$(gpu_temp)C ==="
