#!/usr/bin/env bash
# Research-only (PR #571, R103-A rung 0): build and snapshot one worker binary
# per revision under test.
#
# ARMS is a space-separated list of `name=committish`, built left to right.
# `HEAD` is allowed and means the current checkout.
#
#   default (rung 0, two arms):
#     ARMS="new=HEAD old=30f752df"  NULL_COPIES="oldA=old oldB=old"
#
#   advisor amendment r103-a-fb2 (rung 1B, three arms):
#     ARMS="C=HEAD B=e17bdeb1 A=30f752df"  NULL_COPIES=""
#       A = 30f752df, Arm R receipt tree      (7ce1262d)
#       B = e17bdeb1, frontier receipt tree   (e08d759f; Sources == a4d3b8dc)
#       C = HEAD      = assignment base 0f6862d0 = B + R3 (#558)
#
# The arm is a whole-tree source difference over Sources/ + Vendor/, so each arm
# is a prebuilt binary snapshotted before any timing. The worker links every
# project module statically and resolves mlx.metallib through @loader_path, so a
# snapshot is exactly {executable, mlx.metallib}.
#
# NULL_COPIES is a list of `name=source` byte-identical duplicates used as
# rule-79 identical-code null arms.
#
# Rule 75: the sha256 digest of the whole Sources+Vendor tree is published
# before and after, and must round-trip to its HEAD value.
#
#   SNAP=/tmp/maple-r103a-snap bash research/maple-frieren-r103a-build-arms.sh
#
# Setting HOOK to a patch path applies it to *every* arm as a build-time input
# and reverts it before every digest, giving profiled twins of the same
# binaries. Rung 2 uses HOOK=research/nezuko-pr158-gpuprof-hook.patch, which
# touches only Vendor/.../metal/device.{cpp,h} — two files that are byte-
# identical at every arm, so the instrument is strictly common mode and cannot
# itself create an arm difference.
#
#   SNAP=/tmp/maple-r103a-snap-prof OUT=/tmp/maple-r103a/rung2 \
#     HOOK=research/nezuko-pr158-gpuprof-hook.patch PROV_NAME=rung2-build \
#     bash research/maple-frieren-r103a-build-arms.sh
set -uo pipefail

ARMS="${ARMS:-new=HEAD old=30f752df}"
NULL_COPIES="${NULL_COPIES:-oldA=old oldB=old}"
SNAP="${SNAP:-/tmp/maple-r103a-snap}"
OUT="${OUT:-/tmp/maple-r103a}"
HOOK="${HOOK:-}"
PROV_NAME="${PROV_NAME:-rung0-provenance}"
mkdir -p "${OUT}" "${SNAP}"
PROV="${OUT}/${PROV_NAME}.txt"
: >"${PROV}"

log() { printf '%s\n' "$*" | tee -a "${PROV}"; }

tree_digest() {
  find Sources Vendor -type f -print0 | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
}

if ! git diff --quiet -- Sources Vendor || \
   [ -n "$(git ls-files --others --exclude-standard -- Sources Vendor)" ]; then
  echo "refusing: Sources/Vendor tree is dirty; commit or revert first" >&2
  exit 2
fi

HEAD_SHA="$(git rev-parse HEAD)"
DIGEST_HEAD="$(tree_digest)"
log "head=${HEAD_SHA}"
log "digest_head=${DIGEST_HEAD}"
log "arms=${ARMS}"
log "null_copies=${NULL_COPIES:-<none>}"
for spec in ${ARMS}; do
  log "arm_resolved ${spec%%=*} = $(git rev-parse "${spec#*=}")"
done
log "host=$(sysctl -n machdep.cpu.brand_string) mem=$(sysctl -n hw.memsize)"

build_worker() {
  log "### building worker ($1)${HOOK:+ [hook: ${HOOK}]}"
  if [ -n "${HOOK}" ]; then
    git apply "${HOOK}" || { log "FAIL: hook did not apply at $1"; return 20; }
  fi
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker \
      2>&1 | tail -20 | tee -a "${PROV}"
  local rc="${PIPESTATUS[0]}"
  git checkout -- Package.resolved 2>/dev/null || true
  # The hook is a build-time input only; revert it immediately so every digest
  # this script publishes describes the unhooked tree.
  if [ -n "${HOOK}" ]; then
    git apply -R "${HOOK}" || { log "FAIL: hook did not revert at $1"; return 21; }
  fi
  return "${rc}"
}

snapshot() {
  local name="$1" dir="${SNAP}/$1"
  rm -rf "${dir}" && mkdir -p "${dir}"
  cp .build-worker/release/mlxfast-runtime-worker "${dir}/" || return 1
  cp .build-worker/release/mlx.metallib "${dir}/" || return 1
  log "### snapshot ${name}: $(shasum -a 256 "${dir}/mlxfast-runtime-worker" \
    | cut -c1-16) $(stat -f%z "${dir}/mlxfast-runtime-worker") bytes"
}

# Files HEAD has but the arm revision does not must be deleted after checking
# the arm out, otherwise the build compiles duplicate symbols from files that
# revision never had.
checkout_arm() {
  local sha="$1"
  log "### checking out ${sha} over Sources+Vendor"
  git checkout "${sha}" -- Sources Vendor || return 1
  comm -13 \
    <(git ls-tree -r --name-only "${sha}" -- Sources Vendor | sort) \
    <(git ls-tree -r --name-only HEAD     -- Sources Vendor | sort) \
    | while IFS= read -r p; do [ -n "${p}" ] && rm -f "${p}"; done
  log "digest_at_${sha}=$(tree_digest)"
}

restore_head() {
  log "### restoring HEAD Sources+Vendor"
  git checkout HEAD -- Sources Vendor
  # An arm checkout also stages arm-only paths, which `git checkout HEAD`
  # cannot unstage because HEAD has no entry for them. Reset the index first,
  # which demotes them to untracked, then delete them. The entry guard above
  # proved Sources+Vendor had no untracked files before the script started.
  git reset -q HEAD -- Sources Vendor
  git ls-files --others --exclude-standard -- Sources Vendor \
    | while IFS= read -r p; do [ -n "${p}" ] && rm -f "${p}"; done
  local after; after="$(tree_digest)"
  log "digest_after_restore=${after}"
  if [ "${after}" != "${DIGEST_HEAD}" ]; then
    log "FAIL(G0.4): Sources+Vendor digest did not round-trip to its HEAD value"
    return 1
  fi
  log "PASS(G0.4): Sources+Vendor digest round-tripped"
}
trap 'restore_head || true' EXIT

NAMES=()
for spec in ${ARMS}; do
  name="${spec%%=*}"; sha="${spec#*=}"
  NAMES+=("${name}")
  if [ "${sha}" != "HEAD" ]; then
    checkout_arm "${sha}" || exit 6
  else
    log "### arm ${name} is HEAD; no checkout needed"
    log "digest_at_HEAD=$(tree_digest)"
  fi
  build_worker "${name} ($(git rev-parse --short "${sha}"))" \
    || { log "FAIL(G0.1): ${name} build"; exit 4; }
  snapshot "${name}" || exit 5
  if [ "${sha}" != "HEAD" ]; then
    restore_head || exit 9
  fi
done

restore_head || exit 9
trap - EXIT

########## identical-code null arms ##########
for spec in ${NULL_COPIES}; do
  name="${spec%%=*}"; src="${spec#*=}"
  rm -rf "${SNAP}/${name}" && cp -R "${SNAP}/${src}" "${SNAP}/${name}"
  NAMES+=("${name}")
  log "### ${name} is a byte-identical copy of ${src} (rule-79 null arm)"
done

########## G0.3 pairwise distinctness ##########
for ((i = 0; i < ${#NAMES[@]}; i++)); do
  for ((j = i + 1; j < ${#NAMES[@]}; j++)); do
    a="${NAMES[$i]}"; b="${NAMES[$j]}"
    if cmp -s "${SNAP}/${a}/mlxfast-runtime-worker" \
              "${SNAP}/${b}/mlxfast-runtime-worker"; then
      log "  G0.3 ${a} vs ${b}: IDENTICAL"
    else
      log "  G0.3 ${a} vs ${b}: differ"
    fi
  done
done
log "NOTE(G0.3): declared null twins and their shared source arm are expected"
log "            to compare IDENTICAL; any other identical pair is a collision"
log "            between two distinct revisions and invalidates that contrast."

########## G0.5 metallib ##########
MLIB_UNIQ=$(shasum -a 256 "${SNAP}"/*/mlx.metallib | awk '{print $1}' \
  | sort -u | wc -l | tr -d ' ')
if [ "${MLIB_UNIQ}" = "1" ]; then
  log "PASS(G0.5): mlx.metallib byte-identical across all arms (AOT surface unchanged)"
else
  log "NOTE(G0.5): ${MLIB_UNIQ} distinct mlx.metallib; each snapshot carries its own"
fi

shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker "${SNAP}"/*/mlx.metallib \
  | tee "${OUT}/binaries.sha256" | tee -a "${PROV}"
log "### build complete: ${NAMES[*]}"
