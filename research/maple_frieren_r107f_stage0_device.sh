#!/bin/bash
# Research-only (PR #597, R107-F Stage 0). Never committed in an instrumented state:
# the trap restores Sources/ and Vendor/ unconditionally.
#
# Answers four Stage-0 questions on the live device rather than by inference:
#   1. which of the four `lagunaRoutedSharedDownResidual*` pipelines actually
#      resolves (`sharedHalved` x `staged`), i.e. the shipped kernel name;
#   2. the Rule 77 geometry of every resolved pipeline (`maxTotalThreadsPerThreadgroup`,
#      `threadExecutionWidth`, `staticThreadgroupMemoryLength`) -- the GPUPSO line
#      the nezuko hook already emits;
#   3. the spill proxy: maxTotalThreadsPerThreadgroup for the shipped kernel must
#      be >= the 288 threads the launch wrapper asks for;
#   4. a fresh in-situ per-call anchor for the shipped kernel (GPUPROF).
#
# It also dumps the exact generated MSL body for all four (sharedHalved, staged)
# combinations so the AIR census in Stage 1 censuses the shipped text, not a
# hand-transcribed copy.
#
#   STEPS=33 OUT=research/artifacts/maple-frieren-r107f \
#     bash research/maple_frieren_r107f_stage0_device.sh
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD

STEPS=${STEPS:-33}
OUT=${OUT:-research/artifacts/maple-frieren-r107f}
PATCH=research/nezuko-pr158-gpuprof-hook.patch
MSL_DIR="$ROOT/$OUT/msl"
mkdir -p "$OUT" "$MSL_DIR"

cleanup() {
  echo "=== restoring Sources/ Vendor/ ==="
  git checkout -- Sources/ Vendor/ Package.resolved 2>/dev/null || true
  git status --porcelain=v1 -- Sources/ Vendor/ benchmark.json
}
trap cleanup EXIT

echo "=== applying $PATCH ==="
git apply "$PATCH" || exit 1

echo "=== injecting the temporary MSL dump + resolved-name print ==="
python3 - <<'PY' || exit 1
import io, sys
p = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
src = io.open(p, encoding="utf-8").read()
anchor = "    let sharedHalved = sharedDownScales.ndim == 1\n"
assert src.count(anchor) == 1, src.count(anchor)
inject = anchor + '''
    if let r107fDir = ProcessInfo.processInfo.environment["MAPLE_R107F_DUMP_MSL"] {
        for h in [false, true] {
            for s in [false, true] {
                let tag = "sh\\(h ? 1 : 0)_stage\\(s ? 1 : 0)"
                try? lagunaRoutedSharedDownResidualSource(sharedHalved: h, staged: s)
                    .write(toFile: "\\(r107fDir)/down_residual_\\(tag).msl",
                           atomically: true, encoding: .utf8)
            }
        }
        FileHandle.standardError.write(
            ("R107F_RESOLVED sharedHalved=\\(sharedHalved) staged=\\(staged)"
             + " sharedFirst=\\(lagunaSharedFirstDownOrderEnabled)"
             + " fusedStaging=\\(lagunaFusedDownRowStagingEnabled)"
             + " sharedScalesNdim=\\(sharedDownScales.ndim)"
             + " sharedScalesSize=\\(sharedDownScales.size)"
             + " routedScalesSize=\\(routedDownScales.size)\\n").data(using: .utf8)!)
    }
'''
io.open(p, "w", encoding="utf-8").write(src.replace(anchor, inject))
print("injected")
PY
git status --porcelain=v1 -- Sources/ Vendor/

echo "=== building instrumented worker ==="
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${PWD}/.build-worker/clang-module-cache}" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker || exit 1

echo "=== running decode probe ($STEPS steps, split dispatches) ==="
MAPLE_R107F_DUMP_MSL="$MSL_DIR" \
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
  python3 research/decode_probe.py --steps "$STEPS" --profile --profile-top 20 \
    --stderr "$OUT/stage0_device.err" >"$OUT/stage0_device.log" 2>&1
status=$?
echo "exit=$status"

echo "=== R107F_RESOLVED (first occurrence) ==="
grep -m1 "R107F_RESOLVED" "$OUT/stage0_device.err" | tee "$OUT/stage0_resolved.txt"

echo "=== GPUPSO geometry for the down-residual family ==="
grep "^GPUPSO" "$OUT/stage0_device.err" | sort -u | tee "$OUT/stage0_gpupso.txt" \
  | grep -i "down_residual" || true

echo "=== dumped MSL ==="
ls -la "$MSL_DIR"

echo "=== top pipelines by GPU time ==="
grep -A30 "per steady step" "$OUT/stage0_device.log" | head -40
exit "$status"
