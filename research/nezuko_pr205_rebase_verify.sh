#!/bin/bash
# Re-verify the merge-epilogue change after rebasing onto the advanced base
# 747d130b (PR #170, NVFP4 quantized vendor kernels).
#
# #170 touches only fp_quantized_nax.{cpp,h} and quantized.cpp, i.e. it changes
# the *values* flowing into the decode attention kernels but not their reduction
# structure. The bit-identity argument for this change is structural and so
# survives that, but the certificate itself was measured on the old base, so it
# is re-taken here against the new one.
set -u
cd "$(dirname "$0")/.." || exit 1

BASE_SHA=747d130be532383d3eabd190f54f8b1b2bc6f9fd
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=/tmp/nezreb
BIN=.build-worker/release/mlxfast-runtime-worker

# `git checkout <sha> -- <path>` writes the index too, so restore from HEAD to
# reset index and worktree together.
restore_src() { git checkout HEAD -- "${SRC}" 2>/dev/null; git checkout HEAD -- Package.resolved 2>/dev/null; }
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

digest() {
  python3 research/frieren_pr80_logit_bitwise.py \
    --label "$1" --steps 64 --top-k 100352 --out "${OUT}/$1.json"
}

echo "=== CANDIDATE (worktree HEAD) ==="
build_worker || exit 1
cp "${BIN}" "${OUT}/worker.cand" || exit 1
digest cand || exit 1

echo "=== BASE (${BASE_SHA} version of ${SRC}) ==="
git checkout "${BASE_SHA}" -- "${SRC}" || exit 1
build_worker || exit 1
cp "${BIN}" "${OUT}/worker.base" || exit 1
digest ref || exit 1

restore_src
echo "PROVENANCE cand=$(md5 -q "${OUT}/worker.cand") base=$(md5 -q "${OUT}/worker.base")"
echo "PROVENANCE worktree_clean=$(git status --porcelain | wc -l | tr -d ' ')"

echo "=== DIGEST COMPARISON ==="
python3 - "${OUT}/ref.json" "${OUT}/cand.json" <<'PY'
import json, sys
ref = json.load(open(sys.argv[1]))
cand = json.load(open(sys.argv[2]))
print("REF_RUN_DIGEST ", ref.get("run_digest"))
print("CAND_RUN_DIGEST", cand.get("run_digest"))
print("RUN_DIGEST_EQUAL", ref.get("run_digest") == cand.get("run_digest"))
rs = ref.get("steps", []); cs = cand.get("steps", [])
diff = sum(1 for a, b in zip(rs, cs) if a.get("digest") != b.get("digest"))
print(f"STEP_DIGESTS_DIFFERING {diff} of {min(len(rs), len(cs))}")
print("REF_TOKEN_MISMATCHES ", ref.get("token_mismatches"))
print("CAND_TOKEN_MISMATCHES", cand.get("token_mismatches"))
PY

echo "=== rebuilding candidate worker for the official gate ==="
build_worker || exit 1

echo "=== ./benchmark.sh --local-submit ==="
./benchmark.sh --local-submit > "${OUT}/local_submit.txt" 2>&1
echo "LOCAL_SUBMIT_RC=$?"
tail -40 "${OUT}/local_submit.txt"

echo "VERIFY_DONE"
