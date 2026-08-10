#!/usr/bin/env bash
# R107-J' two-tree certification: stage one compiled tree for paired timing.
#
# WHY THIS EXISTS
# ---------------
# maple-nezuko-r107j-certify.sh differentiates arms by environment only. That
# is enough for a gated knob, but a merge candidate (e.g. family-E source
# transplants) is a SOURCE change with no env gate. Asking the author to add a
# gate is worse than useless for certification: rule 105.22(b) requires ten
# paired blocks on the exact tree being submitted, and a default-off gate means
# the candidate arm is not the submitted default.
#
# benchmark.sh already provides the clean lever:
#
#   benchmark.sh:212  RUNTIME_WORKER_BIN="${MLXFAST_RUNTIME_WORKER_EXECUTABLE:-.build-worker/release/mlxfast-runtime-worker}"
#   benchmark.sh:213  MLX_METALLIB="${MLXFAST_MLX_METALLIB:-$(dirname "${RUNTIME_WORKER_BIN}")/mlx.metallib}"
#   benchmark.sh:1543 the worker sandbox exec-allows exactly that absolute path
#
# So a staged directory holding {worker, mlx.metallib, resource bundles} is a
# self-contained, immutable timing artifact, and a certify arm becomes:
#
#   B:MLXFAST_RUNTIME_WORKER_EXECUTABLE=/tmp/r107j-stage/B/mlxfast-runtime-worker
#
# Both arms then time real compiled trees, back to back, in one ABBA session,
# under one thermal gate, with no rebuild between arms. That is the strongest
# available local evidence and it needs no cooperation from the candidate author.
#
# USAGE
# -----
#   research/maple-nezuko-r107j-stage-tree.sh LABEL              # stage cwd tree
#   research/maple-nezuko-r107j-stage-tree.sh --verify LABEL      # custody recheck
#   research/maple-nezuko-r107j-stage-tree.sh --diff-guard REF    # A<->B legality
#
# The tool never touches git. The operator arranges the working tree (checkout,
# merge, cherry-pick), then stages it. That keeps tree custody auditable and
# keeps this script out of the business of restoring someone else's work tree.
#
# STAGE_ROOT defaults to /tmp/r107j-stage. ~208 MB per tree.
set -u -o pipefail

STAGE_ROOT="${STAGE_ROOT:-/tmp/r107j-stage}"

die() { echo "FATAL: $*" >&2; exit 2; }
note() { echo "=== $*"; }

[ -f ./benchmark.sh ] || die "run from the repository root (./benchmark.sh not found)"

# The runtime artifacts a swapped-in worker needs beside itself: the binary,
# the participant metallib it loads by sibling path, its fingerprint record,
# and every SwiftPM resource bundle Bundle.module resolves next to the exe.
REL=".build-worker/release"
STAGE_ITEMS=(mlxfast-runtime-worker mlx.metallib mlx.metallib.fingerprint)
STAGE_GLOBS=("${REL}"/*.bundle)

tree_fingerprint() {
  # Identity of what was compiled: staged index + any uncommitted content of
  # every build input. Two trees with equal fingerprints cannot differ in the
  # timed binary, so a paired difference between them must be zero.
  {
    git ls-files -s -- Package.swift Package.resolved Sources Vendor 2>/dev/null
    git diff HEAD -- Package.swift Package.resolved Sources Vendor 2>/dev/null
  } | shasum -a 256 | awk '{print $1}'
}

# ---------------------------------------------------------------- --diff-guard
# Refuse the two-tree shortcut where a binary swap is NOT a faithful stand-in
# for the whole candidate. Two classes matter:
#   weights/  : regenerated from Package.*, MLXFastCore, MLXFastTransform
#               (benchmark.sh source_hash(), ~line 1585). Both arms share one
#               weights/ directory, so a transform-side change cannot be
#               certified by swapping workers alone.
#   metallib  : AOT vendored Metal sources. Staging carries each tree's own
#               metallib, so this is legal, but the trusted CLI will warn that
#               the overridden metallib does not match the checked-out sources.
#               That warning is expected and is not a defect.
if [ "${1:-}" = "--diff-guard" ]; then
  ref="${2:-}"
  [ -n "$ref" ] || die "--diff-guard needs a REF to compare the working tree against"
  git rev-parse --verify "$ref" >/dev/null 2>&1 || die "unknown ref '${ref}'"
  changed="$(git diff --name-only "$ref" -- Package.swift Package.resolved \
    Sources/MLXFastCore Sources/MLXFastTransform 2>/dev/null)"
  if [ -n "$changed" ]; then
    echo "ILLEGAL for two-tree staging: the candidate changes weights-generating inputs:" >&2
    echo "$changed" | sed 's/^/  /' >&2
    echo "Both arms share one weights/ directory, so a worker swap would time" >&2
    echo "the candidate binary against the WRONG weights. Certify such a" >&2
    echo "candidate with a full rebuild+regenerate per arm instead." >&2
    exit 3
  fi
  aot="$(git diff --name-only "$ref" -- \
    Vendor/mlx-swift/Source/Cmlx/mlx Vendor/mlx-swift/Source/Cmlx/mlx-generated 2>/dev/null)"
  if [ -n "$aot" ]; then
    note "NOTE: candidate touches AOT metallib inputs ($(echo "$aot" | wc -l | tr -d ' ') files)."
    note "      Staging carries a per-tree metallib, so this is legal, but expect a"
    note "      'metallib fingerprint' warning in the arm whose metallib differs"
    note "      from the checked-out sources. That warning is expected here."
  fi
  note "two-tree staging LEGAL for this candidate (no weights-input changes)"
  exit 0
fi

# -------------------------------------------------------------------- --verify
if [ "${1:-}" = "--verify" ]; then
  label="${2:-}"
  [ -n "$label" ] || die "--verify needs a LABEL"
  dir="${STAGE_ROOT}/${label}"
  [ -d "$dir" ] || die "no staged tree at ${dir}"
  [ -f "${dir}/MANIFEST" ] || die "no MANIFEST in ${dir}"
  ( cd "$dir" && shasum -a 256 -c SHA256SUMS ) || die "custody BROKEN for '${label}': staged artifact changed since staging"
  note "custody OK for '${label}'"
  sed 's/^/    /' "${dir}/MANIFEST"
  exit 0
fi

# --------------------------------------------------------------------- staging
LABEL="${1:-}"
[ -n "$LABEL" ] || die "usage: $0 LABEL | --verify LABEL | --diff-guard REF"
case "$LABEL" in
  ''|*[!A-Za-z0-9_]*) die "LABEL '${LABEL}' must be alphanumeric/underscore" ;;
esac

DIR="${STAGE_ROOT}/${LABEL}"
[ -e "$DIR" ] && die "${DIR} already exists; staged trees are immutable (rm -rf it deliberately)"

HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
DIRTY="$(git status --porcelain -- Package.swift Package.resolved Sources Vendor 2>/dev/null | wc -l | tr -d ' ')"
FP="$(tree_fingerprint)"

note "staging tree '${LABEL}'"
note "  head=${HEAD_SHA} dirty_build_inputs=${DIRTY}"
note "  tree_fingerprint=${FP}"
[ "$DIRTY" != "0" ] && note "  NOTE: build inputs are dirty; the fingerprint above covers that content"

# Build exactly the way benchmark.sh does (benchmark.sh:2011-2023). A bare
# `swift build -c release` writes .build/release, and the CLI deliberately
# prefers the .build-worker twin, so --scratch-path is not optional here.
if ! git diff --quiet HEAD -- Package.swift Package.resolved 2>/dev/null; then
  die "Package.swift/Package.resolved differ from HEAD; the dependency graph is frozen"
fi
note "  building trusted CLI + participant worker"
mkdir -p .build/clang-module-cache .build-worker/clang-module-cache || die "cannot create module caches"
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${PWD}/.build/clang-module-cache}" \
  swift build -c release --force-resolved-versions --product mlxfast-swift \
  || die "trusted CLI build failed"
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${PWD}/.build-worker/clang-module-cache}" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker --product mlxfast-runtime-worker \
  || die "participant worker build failed"

# Metallib staleness, same input set as benchmark.sh:1938-1958.
if [ -n "$(find Vendor/mlx-swift/Source/Cmlx/mlx Vendor/mlx-swift/Source/Cmlx/mlx-generated \
      -type f -newer "${REL}/mlx.metallib" -print -quit 2>/dev/null || true)" ]; then
  note "  mlx.metallib is stale; rebuilding"
  tools/build-mlx-metallib.sh || die "metallib rebuild failed"
fi

mkdir -p "$DIR" || die "cannot create ${DIR}"
for item in "${STAGE_ITEMS[@]}"; do
  [ -e "${REL}/${item}" ] || die "missing build product ${REL}/${item}"
  cp "${REL}/${item}" "${DIR}/" || die "cannot stage ${item}"
done
for b in "${STAGE_GLOBS[@]}"; do
  [ -e "$b" ] || continue
  cp -R "$b" "${DIR}/" || die "cannot stage $(basename "$b")"
done
[ -x "${DIR}/mlxfast-runtime-worker" ] || die "staged worker is not executable"

# Plain cp gives the staged copies an mtime of now, which is newer than every
# build input. That is load-bearing: it keeps benchmark.sh's freshness gates
# (swift_build_required, metallib_rebuild_required) quiet for the whole
# campaign, so no arm can silently rebuild a third binary mid-session.
( cd "$DIR" && shasum -a 256 mlxfast-runtime-worker mlx.metallib mlx.metallib.fingerprint > SHA256SUMS ) \
  || die "cannot write SHA256SUMS"

{
  echo "label=${LABEL}"
  echo "staged_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "head_sha=${HEAD_SHA}"
  echo "dirty_build_inputs=${DIRTY}"
  echo "tree_fingerprint=${FP}"
  echo "worker_sha256=$(awk '$2=="mlxfast-runtime-worker"{print $1}' "${DIR}/SHA256SUMS")"
  echo "metallib_sha256=$(awk '$2=="mlx.metallib"{print $1}' "${DIR}/SHA256SUMS")"
  echo "host=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
} > "${DIR}/MANIFEST" || die "cannot write MANIFEST"

note "staged '${LABEL}' -> ${DIR}"
sed 's/^/    /' "${DIR}/MANIFEST"
cat <<EOF

Certify arm spec for this tree:

  ${LABEL}:MLXFAST_RUNTIME_WORKER_EXECUTABLE=${DIR}/mlxfast-runtime-worker

Stage the other tree, confirm the two worker_sha256 values DIFFER, then run
ten paired blocks:

  research/maple-nezuko-r107j-certify.sh --blocks 10 \\
    BASE:MLXFAST_RUNTIME_WORKER_EXECUTABLE=${STAGE_ROOT}/BASE/mlxfast-runtime-worker \\
    CAND:MLXFAST_RUNTIME_WORKER_EXECUTABLE=${STAGE_ROOT}/CAND/mlxfast-runtime-worker

Re-verify custody afterwards ( --verify BASE, --verify CAND ) before reporting.
EOF
