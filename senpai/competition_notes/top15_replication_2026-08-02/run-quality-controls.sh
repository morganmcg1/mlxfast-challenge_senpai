#!/usr/bin/env bash
set -euo pipefail

control_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
control_repo="$(git -C "${control_script_dir}" rev-parse --show-toplevel)"
control_command="${1:-status}"
control_workspace="${MLXFAST_TOP15_CONTROL_WORKSPACE:-${control_repo}/quality-results/.top15-workspace-controls-20260802}"
control_results="${MLXFAST_TOP15_CONTROL_RESULTS:-${control_repo}/quality-results/leaderboard-top15-controls-20260802}"
control_primary_workspace="${control_repo}/quality-results/.top15-workspace-20260802"
control_primary_results="${control_repo}/quality-results/leaderboard-top15-20260802"

control_real_path() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

resolved_control_workspace="$(control_real_path "${control_workspace}")"
resolved_control_results="$(control_real_path "${control_results}")"
resolved_primary_workspace="$(control_real_path "${control_primary_workspace}")"
resolved_primary_results="$(control_real_path "${control_primary_results}")"

case "${resolved_control_workspace}" in
  "${resolved_primary_workspace}"|"${resolved_primary_workspace}"/*)
    echo "quality-controls: workspace must remain separate from the primary study" >&2
    exit 1
    ;;
esac
case "${resolved_control_results}" in
  "${resolved_primary_results}"|"${resolved_primary_results}"/*)
    echo "quality-controls: results must remain separate from the primary study" >&2
    exit 1
    ;;
esac
[[ "${resolved_control_workspace}" != "${resolved_control_results}" ]] \
  || { echo "quality-controls: workspace and results must be different paths" >&2; exit 1; }

case "${control_command}" in
  prepare|quality|status) ;;
  -h|--help|help)
    cat <<'EOF'
Usage:
  run-quality-controls.sh prepare
  run-quality-controls.sh quality [all|CONTROL_RANK|SUBMISSION_PREFIX]
  run-quality-controls.sh status

Controls use a frozen quality-only manifest and isolated workspace/results.
EOF
    exit 0
    ;;
  perf)
    echo "quality-controls: performance is intentionally disabled for this cohort" >&2
    exit 1
    ;;
  *)
    echo "quality-controls: unsupported command: ${control_command}" >&2
    exit 1
    ;;
esac

export MLXFAST_TOP15_MANIFEST="${control_script_dir}/control-run.json"
export MLXFAST_TOP15_WORKSPACE="${control_workspace}"
export MLXFAST_TOP15_RESULTS="${control_results}"

exec "${control_script_dir}/run-study.sh" "$@"
