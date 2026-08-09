#!/usr/bin/env bash
# Research-only (PR #571, R103-A rung 0): build and snapshot the two worker
# binaries whose official receipts bracket the round-100 frontier adoption.
#
#   new  = HEAD (assignment base 0f6862d0, receipt e08d759f, 4913.117 us/step)
#   old  = OLD_SHA          (30f752df, receipt 7ce1262d, 4893.712 us/step)
#
# The arm is a whole-tree source difference over Sources/ + Vendor/, so each arm
# is a prebuilt binary snapshotted before any timing. The worker links every
# project module statically and resolves mlx.metallib through @loader_path, so a
# snapshot is exactly {executable, mlx.metallib}.
#
# oldA and oldB are byte-identical copies of old. Rung 1 places them on the
# exterior ABBA slots to obtain a rule-79 identical-code null in the same
# session as the real contrast.
#
# Rule 75: the sha256 digest of the whole Sources+Vendor tree is published
# before and after, and must round-trip to its HEAD value.
#
#   SNAP=/tmp/maple-r103a-snap bash research/maple-frieren-r103a-build-arms.sh
#
# Setting HOOK to a patch path applies it to *both* arms as a build-time input
# and reverts it before every digest, giving profiled twins of the same two
# binaries. Rung 2 uses HOOK=research/nezuko-pr158-gpuprof-hook.patch, which
# touches only Vendor/.../metal/device.{cpp,h} — two files that are byte-
# identical at OLD and at NEW, so the instrument is strictly common mode and
# cannot itself create an arm difference.
#
#   SNAP=/tmp/maple-r103a-snap-prof OUT=/tmp/maple-r103a/rung2 \
#     HOOK=research/nezuko-pr158-gpuprof-hook.patch PROV_NAME=rung2-build \
#     bash research/maple-frieren-r103a-build-arms.sh
set -uo pipefail

OLD_SHA="${OLD_SHA:-30f752df}"
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
log "old_sha=$(git rev-parse "${OLD_SHA}")"
log "digest_head=${DIGEST_HEAD}"
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

# NEW-only files must be deleted when checking out OLD, otherwise the OLD build
# compiles duplicate symbols from files that revision never had.
NEW_ONLY="${OUT}/new-only-paths.txt"
comm -13 \
  <(git ls-tree -r --name-only "${OLD_SHA}" -- Sources Vendor | sort) \
  <(git ls-tree -r --name-only HEAD        -- Sources Vendor | sort) \
  >"${NEW_ONLY}"
log "new_only_paths=$(wc -l <"${NEW_ONLY}" | tr -d ' ')"
sed 's/^/  new-only: /' "${NEW_ONLY}" >>"${PROV}"

restore_head() {
  log "### restoring HEAD Sources+Vendor"
  git checkout HEAD -- Sources Vendor
  # The OLD checkout also staged OLD-only paths, which `git checkout HEAD`
  # cannot unstage because HEAD has no entry for them. Reset the index first,
  # which demotes them to untracked, then delete them from the worktree.
  git reset -q HEAD -- Sources Vendor
  comm -23 \
    <(git ls-tree -r --name-only "${OLD_SHA}" -- Sources Vendor | sort) \
    <(git ls-tree -r --name-only HEAD        -- Sources Vendor | sort) \
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

########## arm: new (HEAD) ##########
build_worker "new (${HEAD_SHA:0:8})" || { log "FAIL(G0.1): new build"; exit 4; }
snapshot new || exit 5
log "digest_at_new_build=$(tree_digest)"

########## arm: old ##########
log "### checking out ${OLD_SHA} over Sources+Vendor"
git checkout "${OLD_SHA}" -- Sources Vendor || exit 6
while IFS= read -r p; do [ -n "${p}" ] && rm -f "${p}"; done <"${NEW_ONLY}"
log "digest_at_old=$(tree_digest)"
build_worker "old (${OLD_SHA})" || { log "FAIL(G0.1): old build"; exit 7; }
snapshot old || exit 8

restore_head || exit 9
trap - EXIT

########## identical-code null arms ##########
for c in oldA oldB; do
  rm -rf "${SNAP}/${c}" && cp -R "${SNAP}/old" "${SNAP}/${c}"
done
log "### oldA/oldB are byte-identical copies of old (rule-79 null arms)"

########## G0.3 distinct binaries ##########
if cmp -s "${SNAP}/old/mlxfast-runtime-worker" \
          "${SNAP}/new/mlxfast-runtime-worker"; then
  log "FAIL(G0.3): old and new executables are byte-identical"
  exit 10
fi
log "PASS(G0.3): old and new executables differ"

########## G0.5 metallib ##########
if cmp -s "${SNAP}/old/mlx.metallib" "${SNAP}/new/mlx.metallib"; then
  log "PASS(G0.5): mlx.metallib byte-identical across arms (AOT surface unchanged)"
else
  log "NOTE(G0.5): mlx.metallib differs across arms; each snapshot carries its own"
fi

shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker "${SNAP}"/*/mlx.metallib \
  | tee "${OUT}/binaries.sha256" | tee -a "${PROV}"
log "### rung 0 build complete"
