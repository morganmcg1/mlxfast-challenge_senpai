#!/bin/bash
# Matched base-vs-candidate end-to-end timing for the merge-epilogue change.
#
# Builds both workers from real source (no local-only runtime override), then
# interleaves them ABBAABBA at the canonical worker path so benchmark.sh's
# sandbox, freshness gate and thermal gate all behave exactly as in a normal
# run. Only the worker binary differs between arms.
cd "$(dirname "$0")/.." || exit 1

BASE_SHA=1fe609eb920dd96a409f2949a0e901d3bb525af6
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=/tmp/nezarm
BIN=.build-worker/release/mlxfast-runtime-worker
CLI=.build/release/mlxfast-swift

restore_src() { git checkout -- "${SRC}" 2>/dev/null; git checkout -- Package.resolved 2>/dev/null; }
trap restore_src EXIT

mkdir -p "${OUT}"

build_worker() {
  mkdir -p .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker || return 1
  git checkout -- Package.resolved 2>/dev/null
  return 0
}

echo "=== building CANDIDATE worker (worktree HEAD) ==="
build_worker || exit 1
cp "${BIN}" "${OUT}/worker.cand" || exit 1

echo "=== building BASE worker (${BASE_SHA} version of ${SRC}) ==="
git checkout "${BASE_SHA}" -- "${SRC}" || exit 1
build_worker || exit 1
cp "${BIN}" "${OUT}/worker.base" || exit 1
restore_src

# Prove the two binaries really differ, and that the restored tree is the
# candidate again. A silent no-op build would make the whole ABBA a null test.
echo "PROVENANCE cand=$(md5 -q "${OUT}/worker.cand") base=$(md5 -q "${OUT}/worker.base")"
git --no-pager diff --stat HEAD -- "${SRC}"
echo "PROVENANCE worktree_clean=$(git status --porcelain | wc -l | tr -d ' ')"

run_arm() {
  local arm="$1" idx="$2"
  cp "${OUT}/worker.${arm}" "${BIN}" || return 1
  # Both products must look newer than every build input or benchmark.sh
  # rebuilds the worker from the worktree and destroys the arm.
  touch "${BIN}" "${CLI}"
  echo "=== ARM ${idx} ${arm} $(date -u +%H:%M:%S) ==="
  ./benchmark.sh --local-iterate > "${OUT}/log.${idx}.${arm}.txt" 2>&1
  local rc=$?
  cp score.local-iterate.json "${OUT}/score.${idx}.${arm}.json" 2>/dev/null
  python3 - "${OUT}/score.${idx}.${arm}.json" "${idx}" "${arm}" "${rc}" <<'PY'
import json, sys
p, idx, arm, rc = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
try:
    m = json.load(open(p))["metrics"]
    print("ARMRESULT idx=%s arm=%s rc=%s decode_s_per_tok=%.9f decode_speedup=%.6f "
          "prefill_s_per_tok=%.9f passed_corr=%s max_abs_diff=%s wall=%s"
          % (idx, arm, rc, m["decode_seconds_per_token"], m["decode_speedup"],
             m["prefill_seconds_per_token"], m["passed_correctness"],
             m["max_abs_diff"], m["benchmark_wall_seconds"]))
except Exception as e:
    print("ARMRESULT idx=%s arm=%s rc=%s PARSE_FAIL %s" % (idx, arm, rc, e))
PY
  return 0
}

i=0
for arm in cand base base cand cand base base cand; do
  i=$((i + 1))
  run_arm "${arm}" "${i}" || { echo "ARM ${i} FAILED HARD"; break; }
done

echo "=== SUMMARY ==="
python3 - "${OUT}" <<'PY'
import glob, json, os, re, statistics, sys
out = sys.argv[1]
rows = []
for p in sorted(glob.glob(os.path.join(out, "score.*.json"))):
    idx, arm = re.match(r"score\.(\d+)\.(\w+)\.json", os.path.basename(p)).groups()
    m = json.load(open(p))["metrics"]
    rows.append((int(idx), arm, m["decode_seconds_per_token"], m["prefill_seconds_per_token"]))
rows.sort()
for r in rows:
    print("row idx=%d arm=%-4s decode=%.9f prefill=%.9f" % r)

for name, col in (("decode", 2), ("prefill", 3)):
    c = [r[col] for r in rows if r[1] == "cand"]
    b = [r[col] for r in rows if r[1] == "base"]
    if not c or not b:
        continue
    mc, mb = statistics.mean(c), statistics.mean(b)
    print("%s cand n=%d mean=%.9f sd=%.9f | base n=%d mean=%.9f sd=%.9f | "
          "cand faster by %+.4f%% (%+.2f us/step)"
          % (name, len(c), mc, statistics.pstdev(c) if len(c) > 1 else 0.0,
             len(b), mb, statistics.pstdev(b) if len(b) > 1 else 0.0,
             100.0 * (mb - mc) / mb, 1e6 * (mb - mc)))
    # ABBA pairing: consecutive (cand,base) blocks 1-2, 3-4, 5-6, 7-8
    pairs = []
    for k in range(0, len(rows) - 1, 2):
        a, bb = rows[k], rows[k + 1]
        if {a[1], bb[1]} == {"cand", "base"}:
            cv = a[col] if a[1] == "cand" else bb[col]
            bv = a[col] if a[1] == "base" else bb[col]
            pairs.append(1e6 * (bv - cv))
    if pairs:
        print("%s paired us/step saved: %s | median %+.2f | mean %+.2f"
              % (name, " ".join("%+.2f" % x for x in pairs),
                 statistics.median(pairs), statistics.mean(pairs)))
PY
echo "ABBA_DONE"
