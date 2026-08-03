#!/usr/bin/env bash
set -euo pipefail

anchor_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
anchor_repo="$(git -C "${anchor_script_dir}" rev-parse --show-toplevel)"
anchor_command="${1:-status}"
anchor_manifest="${anchor_script_dir}/quality-anchor-run.json"
anchor_primary_manifest="${anchor_script_dir}/candidates.json"
anchor_workspace="${MLXFAST_TOP15_ANCHOR_WORKSPACE:-${anchor_repo}/quality-results/.top15-workspace-quality-anchor-20260803}"
anchor_results="${MLXFAST_TOP15_ANCHOR_RESULTS:-${anchor_repo}/quality-results/leaderboard-top15-quality-anchor-20260803}"
anchor_primary_workspace="${anchor_repo}/quality-results/.top15-workspace-20260802"
anchor_primary_results="${anchor_repo}/quality-results/leaderboard-top15-20260802"

anchor_real_path() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

resolved_anchor_workspace="$(anchor_real_path "${anchor_workspace}")"
resolved_anchor_results="$(anchor_real_path "${anchor_results}")"
resolved_primary_workspace="$(anchor_real_path "${anchor_primary_workspace}")"
resolved_primary_results="$(anchor_real_path "${anchor_primary_results}")"
resolved_quality_root="$(anchor_real_path "${anchor_repo}/quality-results")"

[[ ! -L "${anchor_workspace}" && ! -L "${anchor_results}" ]] \
  || { echo "quality-anchor: workspace/results may not be symlinks" >&2; exit 1; }
[[ "$(dirname "${resolved_anchor_workspace}")" == "${resolved_quality_root}" \
    && "$(basename "${resolved_anchor_workspace}")" =~ ^\.top15-workspace-quality-anchor-[0-9]{8}$ ]] \
  || { echo "quality-anchor: workspace must use its dedicated quality-anchor prefix" >&2; exit 1; }
[[ "$(dirname "${resolved_anchor_results}")" == "${resolved_quality_root}" \
    && "$(basename "${resolved_anchor_results}")" =~ ^leaderboard-top15-quality-anchor-[0-9]{8}$ ]] \
  || { echo "quality-anchor: results must use their dedicated quality-anchor prefix" >&2; exit 1; }

case "${resolved_anchor_workspace}" in
  "${resolved_primary_workspace}"|"${resolved_primary_workspace}"/*)
    echo "quality-anchor: workspace must remain separate from the primary study" >&2
    exit 1
    ;;
esac
case "${resolved_anchor_results}" in
  "${resolved_primary_results}"|"${resolved_primary_results}"/*)
    echo "quality-anchor: results must remain separate from the primary study" >&2
    exit 1
    ;;
esac
[[ "${resolved_anchor_workspace}" != "${resolved_anchor_results}" ]] \
  || { echo "quality-anchor: workspace and results must be different paths" >&2; exit 1; }
case "${resolved_anchor_results}" in
  "${resolved_anchor_workspace}"/*)
    echo "quality-anchor: results may not be nested under the workspace" >&2
    exit 1
    ;;
esac
case "${resolved_anchor_workspace}" in
  "${resolved_anchor_results}"/*)
    echo "quality-anchor: workspace may not be nested under the results" >&2
    exit 1
    ;;
esac

anchor_primary_sha256="$(shasum -a 256 "${anchor_primary_manifest}" | awk '{print $1}')"
[[ "$(jq -er '.primary_manifest.path' "${anchor_manifest}")" == "candidates.json" \
    && "$(jq -er '.primary_manifest.sha256' "${anchor_manifest}")" == "${anchor_primary_sha256}" ]] \
  || { echo "quality-anchor: primary manifest binding is stale" >&2; exit 1; }
jq -e --slurpfile anchor "${anchor_manifest}" '
  ($anchor[0].candidates | length) == 1
  and (($anchor[0].candidates[0] | {rank,submission_id,source_ref})
    == (.baseline | {rank,submission_id,source_ref}))
' "${anchor_primary_manifest}" >/dev/null \
  || { echo "quality-anchor: rank-111 identity differs from the primary baseline" >&2; exit 1; }
jq -e --slurpfile anchor "${anchor_manifest}" '
  . as $primary
  | $anchor[0] as $quality_anchor
  | ($primary
      | has("harness_commit")
        and has("evaluator_commit")
        and has("evaluator_sha256")
        and has("quality_baseline")
        and has("host")
        and has("required_environment"))
    and ($quality_anchor
      | has("harness_commit")
        and has("evaluator_commit")
        and has("evaluator_sha256")
        and has("quality_baseline")
        and has("host")
        and has("required_environment"))
    and ($quality_anchor.harness_commit == $primary.harness_commit)
    and ($quality_anchor.evaluator_commit == $primary.evaluator_commit)
    and ($quality_anchor.evaluator_sha256 == $primary.evaluator_sha256)
    and ($quality_anchor.quality_baseline == $primary.quality_baseline)
    and ($quality_anchor.host == $primary.host)
    and ($quality_anchor.required_environment == $primary.required_environment)
' "${anchor_primary_manifest}" >/dev/null \
  || { echo "quality-anchor: shared quality contract differs from the primary manifest" >&2; exit 1; }

case "${anchor_command}" in
  prepare|quality|status) ;;
  -h|--help|help)
    cat <<'EOF'
Usage:
  run-quality-anchor.sh prepare
  run-quality-anchor.sh quality 111
  run-quality-anchor.sh status

The rank-111 quality anchor uses a frozen quality-only manifest and isolated
workspace/results. It never changes the primary 15-arm cohort.
EOF
    exit 0
    ;;
  perf)
    echo "quality-anchor: performance is intentionally disabled for this cohort" >&2
    exit 1
    ;;
  *)
    echo "quality-anchor: unsupported command: ${anchor_command}" >&2
    exit 1
    ;;
esac

export MLXFAST_TOP15_MANIFEST="${anchor_manifest}"
export MLXFAST_TOP15_WORKSPACE="${anchor_workspace}"
export MLXFAST_TOP15_RESULTS="${anchor_results}"

exec "${anchor_script_dir}/run-study.sh" "$@"
