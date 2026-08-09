#!/usr/bin/env bash
# Local reconstruction of the ranked submission surface.
#
# Ranked CI never builds a participant checkout. It checks out TRUSTED
# organizer main, overlays exactly benchmark.json's editablePaths from the
# submission, deletes the submission worktree, and builds/measures that tree
# (.github/workflows/benchmark.yml "Checkout submitted editable paths" ->
# "Overlay submitted editable paths" -> "Build ... in bench sandbox" ->
# "Public behavior gate").
#
# This script reproduces that locally so a candidate can be validated as the
# ranked box will actually see it, instead of as the working checkout sees it.
# It is research-only: it lives outside editablePaths and contributes zero
# submission bytes.
#
# Fidelity notes (deliberate deviations, all reported by --report-only):
#   * The overlay itself is the REAL trusted script from the reconstructed
#     trusted tree, driven with the REAL trusted benchmark.json. Nothing about
#     path selection is reimplemented here.
#   * The bench uid, Seatbelt/ACL confinement, PF egress block, harness pins
#     and hidden gates are operator infrastructure and are out of scope.
#   * The transform stage is not re-run: this host has no reference checkpoint
#     (reference_weights/ is empty after setup). Reusing the working
#     checkout's weights/ is sound only while the reconstructed
#     Sources/MLXFastTransform/ tree is byte-identical to the working
#     checkout's, which the script asserts before running the gate.
set -euo pipefail

TRUSTED_REMOTE_DEFAULT="https://github.com/Layr-Labs/mlxfast-challenge"
TRUSTED_REF_DEFAULT="c5b0a13c5cc032b485022db41bcd745792316714"
GOLDEN_REL_DEFAULT="correctness_prompts/public_longcopy_gate_english_512_256.json"
GOLDEN_SHA256_DEFAULT="b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
EXPECTED_STEPS_PER_CASE_DEFAULT=64

# Fork-only trees that exist in the research checkout and not in the organizer
# repository. They are outside editablePaths by construction, so the overlay
# drops them; listing each file individually would bury the real findings.
FORK_ONLY_PREFIXES=("research/" "senpai/" "notes/" ".agents/")

trusted_remote="${TRUSTED_REMOTE_DEFAULT}"
trusted_ref="${TRUSTED_REF_DEFAULT}"
out_dir=""
candidate_root=""
weights_path=""
golden_rel="${GOLDEN_REL_DEFAULT}"
golden_sha256="${GOLDEN_SHA256_DEFAULT}"
expected_steps_per_case="${EXPECTED_STEPS_PER_CASE_DEFAULT}"
do_report=1
do_build=1
do_gate=1
no_fetch=0

usage() {
  cat <<'USAGE'
usage: research/reconstruct-surface.sh [options]

  --trusted-remote URL   organizer repository (default Layr-Labs/mlxfast-challenge)
  --trusted-ref REF      trusted main commit to reconstruct against
  --candidate-root DIR   submission worktree (default: repository root)
  --out DIR              reconstruction root (default: <repo>/../mlxfast-recon)
  --weights DIR          transformed weights (default: <candidate>/weights)
  --golden REL           public gate fixture, repo-relative
  --golden-sha256 HEX    expected fixture hash
  --report-only          static reconstruction + delta report, no build/gate
  --skip-build           reuse an existing build in --out
  --skip-gate            build only
  --no-fetch             do not contact the organizer remote; --trusted-ref must be local
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trusted-remote) trusted_remote="$2"; shift 2 ;;
    --trusted-ref) trusted_ref="$2"; shift 2 ;;
    --candidate-root) candidate_root="$2"; shift 2 ;;
    --out) out_dir="$2"; shift 2 ;;
    --weights) weights_path="$2"; shift 2 ;;
    --golden) golden_rel="$2"; shift 2 ;;
    --golden-sha256) golden_sha256="$2"; shift 2 ;;
    --report-only) do_build=0; do_gate=0; shift ;;
    --skip-build) do_build=0; shift ;;
    --skip-gate) do_gate=0; shift ;;
    --no-fetch) no_fetch=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "reconstruct-surface: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "reconstruct-surface: jq is required" >&2; exit 1; }

if [[ -z "${candidate_root}" ]]; then
  candidate_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
candidate_root="$(cd "${candidate_root}" && pwd)"
[[ -f "${candidate_root}/benchmark.json" ]] || {
  echo "reconstruct-surface: ${candidate_root} is not an mlxfast checkout" >&2; exit 1; }

# The reconstruction root must live OUTSIDE the checkout: it holds a second
# copy of the tree plus two SwiftPM build roots, and anything under the
# checkout would pollute git status and the editable-surface audits.
if [[ -z "${out_dir}" ]]; then
  out_dir="$(dirname "${candidate_root}")/mlxfast-recon"
fi
mkdir -p "${out_dir}"
out_dir="$(cd "${out_dir}" && pwd)"
case "${out_dir}/" in
  "${candidate_root}/"*)
    echo "reconstruct-surface: --out must not be inside the checkout (${out_dir})" >&2
    exit 1 ;;
esac

[[ -n "${weights_path}" ]] || weights_path="${candidate_root}/weights"

recon_root="${out_dir}/tree"
report_dir="${out_dir}/report"
mkdir -p "${report_dir}"

log() { printf 'reconstruct-surface: %s\n' "$*"; }

### 1. Materialize the trusted organizer tree ################################

if [[ "${no_fetch}" -eq 0 ]]; then
  log "fetching ${trusted_remote} main"
  git -C "${candidate_root}" fetch --no-tags --quiet "${trusted_remote}" main
fi
git -C "${candidate_root}" cat-file -e "${trusted_ref}^{commit}" 2>/dev/null || {
  echo "reconstruct-surface: trusted ref ${trusted_ref} is not available locally" >&2
  exit 1
}
trusted_sha="$(git -C "${candidate_root}" rev-parse "${trusted_ref}^{commit}")"
log "trusted base ${trusted_sha}"

# Keep the SwiftPM dependency checkouts across reconstructions; only the source
# tree is rebuilt from the trusted archive.
for scratch in .build .build-worker; do
  if [[ -d "${recon_root}/${scratch}" ]]; then
    mkdir -p "${out_dir}/keep"
    rm -rf "${out_dir}/keep/${scratch}"
    mv "${recon_root}/${scratch}" "${out_dir}/keep/${scratch}"
  fi
done
rm -rf "${recon_root}"
mkdir -p "${recon_root}"
git -C "${candidate_root}" archive --format=tar "${trusted_sha}" \
  | tar -xf - -C "${recon_root}"
for scratch in .build .build-worker; do
  if [[ -d "${out_dir}/keep/${scratch}" ]]; then
    mv "${out_dir}/keep/${scratch}" "${recon_root}/${scratch}"
  fi
done
rmdir "${out_dir}/keep" 2>/dev/null || true

# Reference copy of the pristine trusted tree for the delta report. Cheap on
# APFS (clonefile) and never built in.
trusted_pristine="${out_dir}/trusted-pristine"
rm -rf "${trusted_pristine}"
mkdir -p "${trusted_pristine}"
git -C "${candidate_root}" archive --format=tar "${trusted_sha}" \
  | tar -xf - -C "${trusted_pristine}"

### 2. Overlay the candidate's editable surface ##############################
#
# Driven by the trusted script and the trusted contract, exactly as CI does.
overlay_log="${report_dir}/overlay.log"
log "overlaying editablePaths from ${candidate_root}"
(
  cd "${recon_root}"
  SUBMISSION_WORKTREE="${candidate_root}" \
  CONTRACT_PATH="benchmark.json" \
  GITHUB_WORKSPACE="${recon_root}" \
  TRUSTED_MAIN_SHA="${trusted_sha}" \
    ./.github/scripts/overlay-editable-paths.sh
) > "${overlay_log}" 2>&1 || {
  echo "reconstruct-surface: overlay FAILED; see ${overlay_log}" >&2
  tail -20 "${overlay_log}" >&2
  exit 1
}
overlaid_count="$(grep -c '^benchmark: overlaid editable path ' "${overlay_log}" || true)"
log "overlaid ${overlaid_count} editable paths"
if grep -q '::warning' "${overlay_log}"; then
  log "overlay warnings (stale-editable-file check):"
  grep '::warning' "${overlay_log}" | sed 's/^/  /'
fi

### 3. Delta report ##########################################################

# bash 3.2 on macOS has no mapfile.
editable_paths=()
while IFS= read -r line; do
  if [[ -n "${line}" ]]; then editable_paths+=("${line}"); fi
done < <(jq -r '.editablePaths[]' "${recon_root}/benchmark.json")
[[ "${#editable_paths[@]}" -gt 0 ]] || {
  echo "reconstruct-surface: trusted contract has no editablePaths" >&2; exit 1; }
printf '%s\n' "${editable_paths[@]}" > "${report_dir}/editable-paths.txt"

is_editable() {
  local candidate="$1" allowed
  for allowed in "${editable_paths[@]}"; do
    if [[ "${candidate}" == "${allowed}" || "${candidate}" == "${allowed}/"* ]]; then
      return 0
    fi
  done
  return 1
}

is_fork_only() {
  local candidate="$1" prefix
  for prefix in "${FORK_ONLY_PREFIXES[@]}"; do
    if [[ "${candidate}" == "${prefix}"* ]]; then return 0; fi
  done
  return 1
}

list_files() { ( cd "$1" && find . -type f -print | sed 's|^\./||' | LC_ALL=C sort ); }

# (a) Contract drift: CI reads the TRUSTED contract, so a candidate that edits
#     benchmark.json's editablePaths changes nothing about what is submitted.
contract_report="${report_dir}/contract-drift.txt"
: > "${contract_report}"
if ! diff -q \
    <(jq -S '.editablePaths' "${recon_root}/benchmark.json") \
    <(jq -S '.editablePaths' "${candidate_root}/benchmark.json") >/dev/null; then
  {
    echo "editablePaths differ between trusted main and the candidate."
    echo "CI reads the TRUSTED list; the candidate's list is inert."
    diff <(jq -r '.editablePaths[]' "${recon_root}/benchmark.json" | LC_ALL=C sort) \
         <(jq -r '.editablePaths[]' "${candidate_root}/benchmark.json" | LC_ALL=C sort) || true
  } > "${contract_report}"
fi

# The reconstruction is compared file-by-file against the pristine trusted
# tree. Everything the overlay carried in shows up as changed/new/deleted
# under an editable path; everything the candidate changed outside the surface
# shows up as trusted content the reconstruction still has.
dead_report="${report_dir}/submitted-but-dead.txt"
changed_report="${report_dir}/submitted-and-changed.txt"
new_report="${report_dir}/submitted-new-files.txt"
deleted_report="${report_dir}/submitted-deletions.txt"
lost_report="${report_dir}/changed-outside-surface.txt"
lost_fork_report="${report_dir}/changed-outside-surface-fork-only.txt"
for f in "${dead_report}" "${changed_report}" "${new_report}" "${deleted_report}" \
         "${lost_report}" "${lost_fork_report}"; do : > "${f}"; done

recon_files="${report_dir}/recon-files.txt"
trusted_files="${report_dir}/trusted-files.txt"
list_files "${recon_root}" | grep -v '^\.build' > "${recon_files}"
list_files "${trusted_pristine}" > "${trusted_files}"

# Files present in the reconstruction: submitted surface vs trusted remainder.
while IFS= read -r rel; do
  [[ -n "${rel}" ]] || continue
  if is_editable "${rel}"; then
    if [[ ! -e "${trusted_pristine}/${rel}" ]]; then
      printf '%s\n' "${rel}" >> "${new_report}"
    elif cmp -s "${trusted_pristine}/${rel}" "${recon_root}/${rel}"; then
      printf '%s\n' "${rel}" >> "${dead_report}"
    else
      printf '%s\n' "${rel}" >> "${changed_report}"
    fi
  else
    # Non-editable: the reconstruction holds trusted content by construction.
    # If the candidate's copy differs, that difference is silently reverted.
    if [[ ! -e "${candidate_root}/${rel}" ]] \
        || ! cmp -s "${recon_root}/${rel}" "${candidate_root}/${rel}"; then
      if is_fork_only "${rel}"; then
        printf '%s\n' "${rel}" >> "${lost_fork_report}"
      else
        printf '%s\n' "${rel}" >> "${lost_report}"
      fi
    fi
  fi
done < "${recon_files}"

# Editable trusted files the candidate deleted: the overlay drops them too.
while IFS= read -r rel; do
  [[ -n "${rel}" ]] || continue
  is_editable "${rel}" || continue
  if [[ ! -e "${recon_root}/${rel}" ]]; then
    printf '%s\n' "${rel}" >> "${deleted_report}"
  fi
done < "${trusted_files}"

# Candidate files outside the surface that trusted main does not have at all:
# the overlay never carries them, so a candidate that depends on one is broken
# on the ranked box.
extra_report="${report_dir}/candidate-only-outside-surface.txt"
: > "${extra_report}"
while IFS= read -r rel; do
  [[ -n "${rel}" ]] || continue
  if is_editable "${rel}"; then continue; fi
  if is_fork_only "${rel}"; then continue; fi
  if [[ ! -e "${recon_root}/${rel}" ]]; then
    printf '%s\n' "${rel}" >> "${extra_report}"
  fi
done < <( cd "${candidate_root}" && git ls-files | LC_ALL=C sort )

count() {
  if [[ -s "$1" ]]; then wc -l < "$1" | tr -d ' '; else echo 0; fi
}

summary="${report_dir}/summary.txt"
{
  echo "reconstruct-surface report"
  echo "  trusted base        : ${trusted_sha}"
  echo "  candidate           : ${candidate_root} @ $(git -C "${candidate_root}" rev-parse --short HEAD)"
  echo "  reconstruction root : ${recon_root}"
  echo "  editablePaths       : ${#editable_paths[@]} contract entries"
  echo
  echo "  submitted files that differ from trusted main   : $(count "${changed_report}")"
  echo "  submitted files IDENTICAL to trusted main (dead): $(count "${dead_report}")"
  echo "  submitted files new in the candidate            : $(count "${new_report}")"
  echo "  editable files the candidate deleted            : $(count "${deleted_report}")"
  echo "  candidate changes outside the surface (REVERTED): $(count "${lost_report}")"
  echo "  fork-only files dropped by the overlay          : $(count "${lost_fork_report}")"
  echo "  candidate-only files outside the surface        : $(count "${extra_report}")"
  if [[ -s "${contract_report}" ]]; then
    echo "  benchmark.json editablePaths drift              : YES (candidate list is inert)"
  else
    echo "  benchmark.json editablePaths drift              : none"
  fi
  echo
  if [[ -s "${lost_report}" ]]; then
    echo "Candidate changes the overlay reverts (not on the ranked box):"
    sed 's/^/  /' "${lost_report}"
    echo
  fi
  if [[ -s "${extra_report}" ]]; then
    echo "Candidate-only files the overlay never carries:"
    sed 's/^/  /' "${extra_report}"
    echo
  fi
  if [[ -s "${new_report}" ]]; then
    echo "New submitted files carried by the overlay:"
    sed 's/^/  /' "${new_report}"
    echo
  fi
  if [[ -s "${deleted_report}" ]]; then
    echo "Editable files the candidate deleted:"
    sed 's/^/  /' "${deleted_report}"
    echo
  fi
} > "${summary}"
cat "${summary}"
log "detailed lists in ${report_dir}"

[[ "${do_build}" -eq 1 || "${do_gate}" -eq 1 ]] || exit 0

### 4. Build the reconstructed tree ##########################################

if [[ "${do_build}" -eq 1 ]]; then
  # Seed SwiftPM dependency state from the working checkout so the
  # reconstruction does not refetch ~30 packages. Only checkouts/artifacts are
  # copied; every object file is compiled from the reconstructed sources.
  for scratch in .build .build-worker; do
    src="${candidate_root}/${scratch}"
    dst="${recon_root}/${scratch}"
    [[ -d "${src}" ]] || continue
    mkdir -p "${dst}"
    for sub in checkouts repositories artifacts; do
      if [[ -d "${src}/${sub}" && ! -d "${dst}/${sub}" ]]; then
        cp -c -R "${src}/${sub}" "${dst}/${sub}" 2>/dev/null \
          || cp -R "${src}/${sub}" "${dst}/${sub}"
      fi
    done
    if [[ -f "${src}/workspace-state.json" && ! -f "${dst}/workspace-state.json" ]]; then
      cp "${src}/workspace-state.json" "${dst}/workspace-state.json"
    fi
  done

  log "building trusted CLI (mlxfast-swift)"
  ( cd "${recon_root}" \
    && swift build -c release --force-resolved-versions --product mlxfast-swift )
  log "building participant worker (mlxfast-runtime-worker)"
  ( cd "${recon_root}" \
    && swift build -c release --force-resolved-versions \
         --scratch-path .build-worker --product mlxfast-runtime-worker )
  log "building participant mlx.metallib"
  ( cd "${recon_root}" && ./tools/build-mlx-metallib.sh )
fi

test -x "${recon_root}/.build/release/mlxfast-swift"
test -x "${recon_root}/.build-worker/release/mlxfast-runtime-worker"
test -s "${recon_root}/.build-worker/release/mlx.metallib"
test -s "${recon_root}/.build-worker/release/mlx.metallib.fingerprint"

[[ "${do_gate}" -eq 1 ]] || exit 0

### 5. Public behavior gate ##################################################

# Reusing weights/ is only sound while the reconstructed transform is
# byte-identical to the one that produced them.
if ! diff -r -q "${candidate_root}/Sources/MLXFastTransform" \
      "${recon_root}/Sources/MLXFastTransform" >/dev/null; then
  echo "reconstruct-surface: reconstructed transform differs from the working checkout;" >&2
  echo "  re-running the transform is required and this host has no reference checkpoint" >&2
  exit 1
fi
[[ -f "${weights_path}/config.json" ]] || {
  echo "reconstruct-surface: no transformed weights at ${weights_path}" >&2; exit 1; }

actual_golden_sha="$(shasum -a 256 "${recon_root}/${golden_rel}" | awk '{print $1}')"
if [[ "${actual_golden_sha}" != "${golden_sha256}" ]]; then
  echo "reconstruct-surface: golden hash mismatch (${actual_golden_sha})" >&2
  exit 1
fi

report_json="${report_dir}/public-gate-report.json"
log "running the public behavior gate"
status=0
( cd "${recon_root}" \
  && ./.build/release/mlxfast-swift correctness \
       --weights "${weights_path}" \
       --golden "${golden_rel}" ) > "${report_json}" || status=$?

case_count="$(jq -r '.case_count' "${report_json}")"
jq -r '"reconstruct-surface: public gate passed=\(.passed) checked_steps=\(.checked_steps) case_count=\(.case_count) golden_hash=\(.golden_hash) error=\"\(.error)\""' \
  "${report_json}"

# The same assertions the ranked workflow applies to the gate report.
jq -e \
  --argjson want_steps "$(( case_count * expected_steps_per_case ))" \
  --argjson want_cases "${case_count}" \
  --arg want_hash "${golden_sha256}" '
    .passed == true
    and .checked_steps == $want_steps
    and .case_count == $want_cases
    and .golden_hash == $want_hash
    and .error == ""
    and .first_failing_case == null
    and .first_failing_step == null
    and .expected_token == null
    and .actual_token == null
  ' "${report_json}" >/dev/null || {
  echo "reconstruct-surface: public behavior gate FAILED on the reconstructed tree" >&2
  exit 1
}

[[ "${status}" -eq 0 ]] || {
  echo "reconstruct-surface: correctness exited ${status}" >&2; exit "${status}"; }

log "public behavior gate PASSED on the reconstructed surface"
