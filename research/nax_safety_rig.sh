#!/usr/bin/env bash
# _nax safety rig: catch the silent-failure modes that a compile/link check
# cannot see, on a host that never dispatches the `_nax` kernels.
#
# M4 Pro reports Apple GPU generation 16, so `_nax` is unreachable locally and
# NO local benchmark exercises this code. Every _nax change therefore ships on
# static evidence alone. The four checks below are the evidence:
#
#   1. compile   -- every requested BK instantiates and links (both shapes).
#   2. inert     -- a guard/constant relax that is claimed not to change the
#                   BK=64 path emits byte-identical AIR against a git revision.
#   3. mma       -- the MMA body is non-empty. tile_matmad_nax compiles to
#                   nothing for odd TN>1 and TM=0 when SM<16; either produces a
#                   kernel that runs fast and returns zeros.
#   4. wideload  -- the widened device load is actually taken. When
#                   kWideLoadShapeOk goes false the loader silently falls back
#                   to kSrcBytes scalar byte loads per thread per k-iteration.
#
# Usage: research/nax_safety_rig.sh [BK ...]        (default: 64 128)
#   BASE_REV=<rev>   git revision for the inertness baseline (default HEAD)
#   KEEP=1           keep scratch dirs
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="${REPO_ROOT}/research/nax_msl_compile_check.sh"
GEN_REL="Vendor/mlx-swift/Source/Cmlx/mlx-generated"
BASE_REV="${BASE_REV:-HEAD}"
BKS=("$@")
[ "${#BKS[@]}" -eq 0 ] && BKS=(64 128)
RIG="/tmp/nax_safety_rig"
rm -rf "${RIG}"; mkdir -p "${RIG}"
fails=0
pass() { printf '  PASS  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# ---------------------------------------------------------------- 1. compile
echo "== 1. compile + link =="
for bk in "${BKS[@]}"; do
  out="${RIG}/bk${bk}"
  if BK="${bk}" OUT_DIR="${out}" EMIT_LIB=1 EMIT_IR=1 "${CHECK}" \
      > "${out}.log" 2>&1; then
    pass "BK=${bk} compiles, links, emits IR"
  else
    fail "BK=${bk}: $(grep -E 'error:|failed' "${out}.log" | head -3 | tr '\n' ' ')"
  fi
done

# -------------------------------------------------------------- 2. inertness
# Compile BK=64 from the working tree and from BASE_REV's generated sources.
# Any constant relax gated on a shape BK=64 does not reach must produce
# identical AIR; a diff means the "inert" claim is false and the arm is
# confounded.
echo "== 2. BK=64 inertness vs ${BASE_REV} =="
BASE_GEN="${RIG}/base_gen"
mkdir -p "${BASE_GEN}"
missing=0
for f in utils gemm_nax quantized_utils fp_quantized_nax; do
  if ! git -C "${REPO_ROOT}" show "${BASE_REV}:${GEN_REL}/${f}.cpp" \
      > "${BASE_GEN}/${f}.cpp" 2>/dev/null; then
    missing=1
  fi
done
if [ "${missing}" -ne 0 ]; then
  fail "could not extract ${BASE_REV} generated sources"
else
  BK=64 OUT_DIR="${RIG}/inert_base" GEN_DIR="${BASE_GEN}" "${CHECK}" \
      > "${RIG}/inert_base.log" 2>&1
  BK=64 OUT_DIR="${RIG}/inert_head" "${CHECK}" > "${RIG}/inert_head.log" 2>&1
  if [ ! -f "${RIG}/inert_base/unit.air" ] || [ ! -f "${RIG}/inert_head/unit.air" ]; then
    fail "inertness: one side did not compile"
  elif cmp -s "${RIG}/inert_base/unit.air" "${RIG}/inert_head/unit.air"; then
    pass "BK=64 AIR byte-identical to ${BASE_REV} ($(wc -c < "${RIG}/inert_head/unit.air") B)"
  else
    fail "BK=64 AIR DIFFERS from ${BASE_REV}: the relax is not inert"
  fi
fi

# ------------------------------------------------------------------- 3. mma
# tile_matmad_nax lowers to air.simdgroup / matrix intrinsics. A kernel whose
# MMA body vanished still compiles and links, so count the intrinsic calls per
# host_name'd function rather than trusting the build.
echo "== 3. non-empty MMA body =="
for bk in "${BKS[@]}"; do
  ll="${RIG}/bk${bk}/unit.ll"
  [ -f "${ll}" ] || { fail "BK=${bk}: no IR"; continue; }
  n=$(grep -cE 'call .*@air\.(simdgroup_)?matrix|@air\.mma|tile_matmad' "${ll}")
  if [ "${n}" -gt 0 ]; then
    pass "BK=${bk}: ${n} MMA intrinsic calls"
  else
    fail "BK=${bk}: ZERO MMA intrinsics -- kernel computes nothing"
  fi
done

# -------------------------------------------------------------- 4. wide load
# The 4/8/16-lane device loads the staging path is supposed to emit show up as
# `load <N x iM>` / `<N x half>` from addrspace(1). The scalar fallback emits
# `load i8` from addrspace(1) instead, once per source byte per thread.
echo "== 4. widened device load taken =="
for bk in "${BKS[@]}"; do
  ll="${RIG}/bk${bk}/unit.ll"
  [ -f "${ll}" ] || { fail "BK=${bk}: no IR"; continue; }
  wide=$(grep -cE 'load <(4|8|16) x i(8|32)>, ptr addrspace\(1\)' "${ll}")
  scalar=$(grep -cE 'load i8, ptr addrspace\(1\)' "${ll}")
  if [ "${wide}" -gt 0 ]; then
    pass "BK=${bk}: ${wide} wide device loads (${scalar} scalar i8)"
  else
    fail "BK=${bk}: ZERO wide device loads, ${scalar} scalar i8 -- fell back"
  fi
done

echo
if [ "${fails}" -eq 0 ]; then
  echo "SAFETY RIG: all checks passed"
else
  echo "SAFETY RIG: ${fails} check(s) FAILED"
fi
[ "${KEEP:-0}" = "1" ] || true
exit "${fails}"
