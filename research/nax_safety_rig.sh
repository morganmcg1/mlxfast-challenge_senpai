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
#   BASE_REV=<rev>   git revision for the inertness baseline (default HEAD;
#                    must predate the relax or check 2 refuses to run)
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
# BASE_REV defaults to HEAD, so running this rig on a clean tree after
# committing the very edit under test compares that edit against itself and
# reports a green PASS that proves nothing. Refuse that comparison: the
# baseline has to be a revision that predates the relax.
identical=1
for f in utils gemm_nax quantized_utils fp_quantized_nax; do
  cmp -s "${BASE_GEN}/${f}.cpp" "${REPO_ROOT}/${GEN_REL}/${f}.cpp" || identical=0
done
if [ "${missing}" -ne 0 ]; then
  fail "could not extract ${BASE_REV} generated sources"
elif [ "${identical}" -eq 1 ]; then
  fail "VACUOUS: ${BASE_REV} generated sources equal the working tree; pass BASE_REV=<rev predating the relax>"
else
  # Both sides must compile through the SAME scratch path: AIR embeds the
  # source file name, so two output directories differ for a trivial reason.
  IN="${RIG}/inert"
  BK=64 OUT_DIR="${IN}" GEN_DIR="${BASE_GEN}" "${CHECK}" \
      > "${RIG}/inert_base.log" 2>&1
  cp "${IN}/unit.air" "${RIG}/inert_base.air" 2>/dev/null
  BK=64 OUT_DIR="${IN}" "${CHECK}" > "${RIG}/inert_head.log" 2>&1
  cp "${IN}/unit.air" "${RIG}/inert_head.air" 2>/dev/null
  if [ ! -f "${RIG}/inert_base.air" ] || [ ! -f "${RIG}/inert_head.air" ]; then
    fail "inertness: one side did not compile"
  elif cmp -s "${RIG}/inert_base.air" "${RIG}/inert_head.air"; then
    pass "BK=64 AIR byte-identical to ${BASE_REV} ($(wc -c < "${RIG}/inert_head.air") B)"
  else
    fail "BK=64 AIR DIFFERS from ${BASE_REV}: the relax is not inert"
  fi
fi

# ------------------------------------------------------------------- 3. mma
# tile_matmad_nax lowers to the tensorops cooperative matmul builtin. It
# compiles to NOTHING for odd TN>1 and for TM=0 (SM<16), and such a kernel
# still builds, links and runs -- returning zeros, very fast. Count the calls.
echo "== 3. non-empty MMA body =="
for bk in "${BKS[@]}"; do
  ll="${RIG}/bk${bk}/unit.ll"
  [ -f "${ll}" ] || { fail "BK=${bk}: no IR"; continue; }
  n=$(grep -cE '@__tensorops_impl_matmul2d_op_run_cooperative' "${ll}")
  if [ "${n}" -gt 0 ]; then
    pass "BK=${bk}: ${n} cooperative matmul calls"
  else
    fail "BK=${bk}: ZERO matmul calls -- kernel computes nothing"
  fi
done

# -------------------------------------------------------------- 4. wide load
# `-S -emit-llvm` is front-end output, so the loader survives as a call whose
# Itanium mangling carries its template args: QuantizedBlockLoader<Wtype,
# BROWS, BCOLS, dst_ld, reduction_dim, tgp_size, group_size, bits>. Recompute
# kSrcBytes from BCOLS/BROWS/tgp_size and require it to be a shape the widened
# path accepts, so a silent scalar fallback is caught by name rather than by
# guessing at optimized load widths.
#
# The accepted set is scraped from kWideLoadShapeOk/kWideLoad8ShapeOk in the
# kernel source, never hardcoded here: a rig carrying its own allow-list tests
# the author's belief about the predicate instead of the predicate.
HDR="${REPO_ROOT}/Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h"
OKSET=$(sed -n '/kWideLoadShapeOk =/,/;/p;/kWideLoad8ShapeOk =/,/;/p' "${HDR}" \
  | grep -oE 'kSrcBytes == [0-9]+' | grep -oE '[0-9]+' | sort -un | tr '\n' ' ')
echo "== 4. widened device load reachable in the emitted loader =="
if [ -z "${OKSET}" ]; then
  fail "could not scrape the accepted kSrcBytes set from fp_quantized_nax.h"
else
  echo "     accepted kSrcBytes (from kernel source): ${OKSET}"
fi
for bk in "${BKS[@]}"; do
  ll="${RIG}/bk${bk}/unit.ll"
  [ -f "${ll}" ] || { fail "BK=${bk}: no IR"; continue; }
  sigs=$(grep -oE 'QuantizedBlockLoaderI[A-Za-z0-9_]*?(Ls[0-9]+E){7}' "${ll}" \
    | grep -oE '(Ls[0-9]+E){7}' | sort -u)
  [ -z "${sigs}" ] && { fail "BK=${bk}: no QuantizedBlockLoader in IR"; continue; }
  bad=0
  for sig in ${sigs}; do
    read -r brows bcols dst_ld rdim tgp gs bits <<< \
      "$(echo "${sig}" | grep -oE '[0-9]+' | tr '\n' ' ')"
    pack_factor=$((8 / bits))
    src_bytes=$(((bcols / pack_factor) * brows / tgp))  # bytes_per_pack==1
    if [[ " ${OKSET}" == *" ${src_bytes} "* ]]; then
      echo "        loader<${brows},${bcols},tgp=${tgp}> kSrcBytes=${src_bytes} widened"
    else
      bad=1
      echo "        loader<${brows},${bcols},tgp=${tgp}> kSrcBytes=${src_bytes} NOT widenable"
    fi
  done
  if [ "${bad}" -eq 0 ]; then
    pass "BK=${bk}: every emitted loader takes the widened device load"
  else
    fail "BK=${bk}: a loader falls back to per-byte scalar device loads"
  fi
done

# ------------------------------------------------------- 5. the guard fires
# A rig that cannot fail proves nothing. The in-kernel static_assert added
# beside loader_w_t is the authoritative detector for the silent scalar
# fallback, because it is compiled from the real predicate rather than from a
# copy of it. Verify it by reverting ONLY the kSrcBytes relax and requiring
# the largest requested BK to be REJECTED at build time, while BK=64 still
# builds -- which is also the second, constructive half of the inertness
# proof in check 2.
echo "== 5. wide-load guard fires (negative control) =="
NEG="${RIG}/neg_gen"
mkdir -p "${NEG}"
cp "${REPO_ROOT}/${GEN_REL}"/{utils,gemm_nax,quantized_utils,fp_quantized_nax}.cpp \
   "${NEG}/" 2>/dev/null
# Narrow the predicate back to the single 16B case.
perl -0pi -e 's/kWidenShapeOk && \(\(kSrcBytes == 16\) \|\| \(kSrcBytes == 32\)\)/kWidenShapeOk \&\& (kSrcBytes == 16)/' \
  "${NEG}/fp_quantized_nax.cpp"
if grep -q 'kSrcBytes == 16) || (kSrcBytes == 32' "${NEG}/fp_quantized_nax.cpp"; then
  fail "negative control: could not narrow kWideLoadShapeOk"
else
  big=64
  for bk in "${BKS[@]}"; do [ "${bk}" -gt "${big}" ] && big="${bk}"; done
  if BK=64 OUT_DIR="${RIG}/neg64" GEN_DIR="${NEG}" "${CHECK}" \
      > "${RIG}/neg64.log" 2>&1; then
    pass "narrowed predicate still builds BK=64 (relax does not reach it)"
  else
    fail "narrowed predicate broke BK=64: the relax is NOT inert"
  fi
  if [ "${big}" -gt 64 ]; then
    if BK="${big}" OUT_DIR="${RIG}/negbig" GEN_DIR="${NEG}" "${CHECK}" \
        > "${RIG}/negbig.log" 2>&1; then
      fail "narrowed predicate STILL built BK=${big}: guard does not fire, a silent scalar fallback would ship"
    else
      pass "narrowed predicate rejects BK=${big} at build time ($(grep -c 'static_assert failed' "${RIG}/negbig.log") static_assert errors)"
    fi
  fi
fi

echo
if [ "${fails}" -eq 0 ]; then
  echo "SAFETY RIG: all checks passed"
else
  echo "SAFETY RIG: ${fails} check(s) FAILED"
fi
[ "${KEEP:-0}" = "1" ] || true
exit "${fails}"
