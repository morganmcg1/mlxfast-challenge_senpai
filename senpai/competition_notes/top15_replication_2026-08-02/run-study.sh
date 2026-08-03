#!/usr/bin/env bash
set -euo pipefail

study_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
study_runner_source="${study_script_dir}/run-study.sh"
study_runner_sha256="$(shasum -a 256 "${study_runner_source}" | awk '{print $1}')"
study_manifest="${MLXFAST_TOP15_MANIFEST:-${study_script_dir}/candidates.json}"
study_repo="$(git -C "${study_script_dir}" rev-parse --show-toplevel)"
study_workspace="${MLXFAST_TOP15_WORKSPACE:-${study_repo}/quality-results/.top15-workspace-20260802}"
study_results="${MLXFAST_TOP15_RESULTS:-${study_repo}/quality-results/leaderboard-top15-20260802}"
study_weights="${MLXFAST_TOP15_WEIGHTS:-${study_repo}/weights}"
study_reference="${MLXFAST_TOP15_REFERENCE:-$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${study_repo}/reference_weights/laguna-xs-2.1-nvfp4-mlx")}"
study_quality_baseline_relative="$(jq -r '.quality_baseline' "${study_manifest}")"
study_quality_baseline="${MLXFAST_TOP15_QUALITY_BASELINE:-${study_repo}/${study_quality_baseline_relative}}"
study_id="$(jq -r '.study' "${study_manifest}")"
study_manifest_sha256="$(shasum -a 256 "${study_manifest}" | awk '{print $1}')"
study_harness_commit="$(jq -r '.harness_commit' "${study_manifest}")"
study_evaluator_commit="$(jq -r '.evaluator_commit' "${study_manifest}")"
study_evaluator_sha256="$(jq -r '.evaluator_sha256' "${study_manifest}")"
study_performance_enabled="$(jq -r 'if (.performance | type) == "object" and (.performance | has("enabled")) then .performance.enabled else true end' "${study_manifest}")"
study_baseline_commit="$(jq -r '.baseline.source_ref // empty' "${study_manifest}")"
study_baseline_rank="$(jq -r '.baseline.rank // empty' "${study_manifest}")"
study_baseline_id="$(jq -r '.baseline.submission_id // empty' "${study_manifest}")"
study_change_label_prefix="$(jq -r '.change_label_prefix // "leaderboard"' "${study_manifest}")"
study_perf_mode="${MLXFAST_TOP15_PERF_MODE:---local-submit}"
study_perf_runtime="swift-${study_perf_mode#--}"
study_quality_retries="${MLXFAST_TOP15_QUALITY_RETRIES:-3}"
study_allow_golden_drift="${MLXFAST_TOP15_ALLOW_GOLDEN_DRIFT:-0}"
study_owner_file="${study_workspace}/.mlxfast-top15-study-owner.json"
study_quality_wrapper_source="${study_script_dir}/quality-bridge-wrapper.sh"
study_quality_wrapper="${study_workspace}/senpai/top15-quality-bridge-wrapper.sh"
study_local_benchmark_source="${study_repo}/benchmark.sh"
study_fan_control_source="${study_repo}/tools/fan-control.sh"
study_macmon_source="${HOME}/bin/macmon"
# Deliberately frozen for this cohort. The rank-126 harness copy warned on
# impossible telemetry but still timed; this content-identical replacement
# changes only local cooling behavior and makes that gate fail closed.
study_local_benchmark_sha256="05d60dd7b8dec7490f32802f201496407fd4687c55f0bf3c28a2bc55fc1c3877"
study_fan_control_sha256="d0281dd62612d5c3371904e317045ed9ae2e7d14021aee65e5b889ee1e46f84a"
study_macmon_sha256="495da8787023c9ebcd62d19e348cd6f1dec5dba3ef2d4f1ff55d9e2079860e19"
study_macmon_version="macmon 0.7.2"
study_local_benchmark_cutover="2026-08-02T22:27:54Z"
study_performance_environment_policy="env-i-v2"
study_performance_fan_policy="auto"
study_thermal_preflight_schema="mlxfast-top15-thermal-preflight-v1"
study_thermal_preflight_samples=5
study_thermal_preflight_interval_ms=1000
study_thermal_reader_timeout_seconds=15
study_thermal_preflight_handoff_seconds=30
study_legacy_baseline_log_sha256="f324d48d983efb427326c13caf0bc3dd0cc5b5e71a786f4f06c4c492270c4130"
study_next_preflight_requires_cool=1
study_current_performance_preflight=""
study_current_performance_preflight_sha256=""
study_supervised_command_pid=""
study_supervised_command_pgid=""
study_supervised_signal_status=0
study_supervised_signal_count=0
study_supervised_term_sent=0
study_supervised_saved_hup_trap=""
study_supervised_saved_int_trap=""
study_supervised_saved_quit_trap=""
study_supervised_saved_term_trap=""
study_supervised_saved_exit_trap=""
study_supervised_monitor_was_on=0
study_capture_pid=""
study_capture_pgid=""
study_capture_signal_status=0
study_capture_term_sent=0
study_capture_saved_hup_trap=""
study_capture_saved_int_trap=""
study_capture_saved_quit_trap=""
study_capture_saved_term_trap=""
study_capture_saved_exit_trap=""
study_capture_monitor_was_on=0
study_capture_state_dir=""
study_capture_status_file=""
study_capture_status_tmp_file=""

die() {
  echo "top15-study: $*" >&2
  exit 1
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

utc_now() {
  python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))'
}

signal_process_tree() {
  local parent_pid="$1"
  local signal="$2"
  local child_pid
  for child_pid in $(pgrep -P "${parent_pid}" 2>/dev/null || true); do
    signal_process_tree "${child_pid}" "${signal}"
  done
  kill -s "${signal}" "${parent_pid}" 2>/dev/null || true
}

process_group_has_live_members() {
  local pgid="$1"
  local process_rows
  if process_rows="$(ps -axo pgid=,stat= 2>/dev/null)"; then
    printf '%s\n' "${process_rows}" \
      | awk -v wanted="${pgid}" '$1 == wanted && $2 !~ /^Z/ { found = 1 } END { exit !found }'
    return "$?"
  fi
  kill -0 -- "-${pgid}" 2>/dev/null
}

terminate_supervised_group() {
  local pgid="${study_supervised_command_pgid}"
  local leader="${study_supervised_command_pid}"
  [[ "${pgid}" =~ ^[1-9][0-9]*$ ]] || return 0
  process_group_has_live_members "${pgid}" || return 0

  if [[ "${study_supervised_term_sent}" == "0" ]]; then
    kill -TERM -- "-${pgid}" 2>/dev/null || true
    study_supervised_term_sent=1
  fi
  local waited_ticks=0
  while process_group_has_live_members "${pgid}" \
      && [[ "${waited_ticks}" -lt 50 ]] \
      && [[ "${study_supervised_signal_count}" -lt 2 ]]; do
    /bin/sleep 0.1
    waited_ticks=$((waited_ticks + 1))
  done
  if process_group_has_live_members "${pgid}"; then
    if [[ "${leader}" =~ ^[1-9][0-9]*$ ]]; then
      signal_process_tree "${leader}" KILL
    fi
    kill -KILL -- "-${pgid}" 2>/dev/null || true
  fi

  waited_ticks=0
  while process_group_has_live_members "${pgid}" && [[ "${waited_ticks}" -lt 20 ]]; do
    /bin/sleep 0.1
    waited_ticks=$((waited_ticks + 1))
  done
  ! process_group_has_live_members "${pgid}"
}

forward_supervised_signal() {
  local status="$1"
  study_supervised_signal_count=$((study_supervised_signal_count + 1))
  if [[ "${study_supervised_signal_status}" == "0" ]]; then
    study_supervised_signal_status="${status}"
  fi
  if [[ "${study_supervised_command_pgid}" =~ ^[1-9][0-9]*$ ]]; then
    if [[ "${study_supervised_term_sent}" == "0" ]]; then
      kill -TERM -- "-${study_supervised_command_pgid}" 2>/dev/null || true
      study_supervised_term_sent=1
    fi
  fi
}

restore_trap() {
  local saved="$1"
  local signal="$2"
  if [[ -n "${saved}" ]]; then
    eval "${saved}"
  else
    trap - "${signal}"
  fi
}

restore_supervised_shell_state() {
  trap - HUP INT QUIT TERM EXIT
  restore_trap "${study_supervised_saved_hup_trap}" HUP
  restore_trap "${study_supervised_saved_int_trap}" INT
  restore_trap "${study_supervised_saved_quit_trap}" QUIT
  restore_trap "${study_supervised_saved_term_trap}" TERM
  restore_trap "${study_supervised_saved_exit_trap}" EXIT
  if [[ "${study_supervised_monitor_was_on}" == "1" ]]; then
    set -m
  else
    set +m
  fi
}

clear_supervised_state() {
  study_supervised_command_pid=""
  study_supervised_command_pgid=""
  study_supervised_signal_status=0
  study_supervised_signal_count=0
  study_supervised_term_sent=0
  study_supervised_saved_hup_trap=""
  study_supervised_saved_int_trap=""
  study_supervised_saved_quit_trap=""
  study_supervised_saved_term_trap=""
  study_supervised_saved_exit_trap=""
  study_supervised_monitor_was_on=0
}

supervised_exit_cleanup() {
  local exit_status="$?"
  trap - HUP INT QUIT TERM EXIT
  if terminate_supervised_group; then
    if [[ "${study_supervised_command_pid}" =~ ^[1-9][0-9]*$ ]]; then
      wait "${study_supervised_command_pid}" 2>/dev/null || true
    fi
  else
    echo "top15-study: ERROR: supervised process group ${study_supervised_command_pgid} survived EXIT teardown" >&2
  fi
  if [[ -n "${study_supervised_saved_exit_trap}" ]]; then
    (
      trap - EXIT
      eval "${study_supervised_saved_exit_trap}"
      exit "${exit_status}"
    ) || true
  fi
  return "${exit_status}"
}

run_supervised_logged_command() {
  local log_file="$1"
  shift
  local command_status=0
  local leaked_group=0
  study_supervised_command_pid=""
  study_supervised_command_pgid=""
  study_supervised_signal_status=0
  study_supervised_signal_count=0
  study_supervised_term_sent=0
  study_supervised_saved_hup_trap="$(trap -p HUP)"
  study_supervised_saved_int_trap="$(trap -p INT)"
  study_supervised_saved_quit_trap="$(trap -p QUIT)"
  study_supervised_saved_term_trap="$(trap -p TERM)"
  study_supervised_saved_exit_trap="$(trap -p EXIT)"
  case "$-" in
    *m*) study_supervised_monitor_was_on=1 ;;
    *) study_supervised_monitor_was_on=0 ;;
  esac
  trap 'forward_supervised_signal 129' HUP
  trap 'forward_supervised_signal 130' INT
  trap 'forward_supervised_signal 131' QUIT
  trap 'forward_supervised_signal 143' TERM
  trap supervised_exit_cleanup EXIT

  if [[ "${study_supervised_signal_status}" != "0" ]]; then
    command_status="${study_supervised_signal_status}"
    restore_supervised_shell_state
    clear_supervised_state
    return "${command_status}"
  fi

  set -m
  (
    set +m
    set +e
    "$@" 2>&1 | tee "${log_file}"
    pipeline_status=("${PIPESTATUS[@]}")
    local_command_status="${pipeline_status[0]}"
    local_tee_status="${pipeline_status[1]}"
    if [[ "${local_tee_status}" != "0" ]]; then
      exit "${local_tee_status}"
    fi
    exit "${local_command_status}"
  ) &
  study_supervised_command_pid="$!"
  study_supervised_command_pgid="${study_supervised_command_pid}"
  if [[ "${study_supervised_monitor_was_on}" == "0" ]]; then
    set +m
  fi
  if [[ "${study_supervised_signal_status}" != "0" ]]; then
    if [[ "${study_supervised_term_sent}" == "0" ]]; then
      kill -TERM -- "-${study_supervised_command_pgid}" 2>/dev/null || true
      study_supervised_term_sent=1
    fi
  fi

  if wait "${study_supervised_command_pid}"; then
    command_status=0
  else
    command_status="$?"
  fi

  if [[ "${study_supervised_signal_status}" != "0" ]]; then
    if terminate_supervised_group; then
      wait "${study_supervised_command_pid}" 2>/dev/null || true
      command_status="${study_supervised_signal_status}"
    else
      leaked_group=1
    fi
  elif process_group_has_live_members "${study_supervised_command_pgid}"; then
    echo "top15-study: ERROR: supervised command exited while descendants remained; terminating process group ${study_supervised_command_pgid}" >&2
    terminate_supervised_group || leaked_group=1
    command_status=125
  fi

  # Signal status has final precedence. A trap can interrupt the first wait or
  # arrive during the post-wait descendant check; never erase that late signal
  # while clearing supervisor state. A process group that survives KILL is the
  # stronger invariant failure and still returns 125.
  if [[ "${study_supervised_signal_status}" != "0" ]]; then
    if terminate_supervised_group; then
      wait "${study_supervised_command_pid}" 2>/dev/null || true
      if [[ "${leaked_group}" == "0" ]]; then
        command_status="${study_supervised_signal_status}"
      fi
    else
      leaked_group=1
    fi
  fi
  if [[ "${leaked_group}" == "1" ]]; then
    echo "top15-study: ERROR: supervised process group ${study_supervised_command_pgid} survived bounded TERM/KILL teardown" >&2
    command_status=125
  fi
  restore_supervised_shell_state
  clear_supervised_state
  return "${command_status}"
}

terminate_capture_group() {
  local pgid="${study_capture_pgid}"
  local leader="${study_capture_pid}"
  [[ "${pgid}" =~ ^[1-9][0-9]*$ ]] || return 0
  if process_group_has_live_members "${pgid}"; then
    if [[ "${study_capture_term_sent}" == "0" ]]; then
      kill -TERM -- "-${pgid}" 2>/dev/null || true
      study_capture_term_sent=1
    fi
    local waited_ticks=0
    while process_group_has_live_members "${pgid}" && [[ "${waited_ticks}" -lt 20 ]]; do
      /bin/sleep 0.1
      waited_ticks=$((waited_ticks + 1))
    done
    if process_group_has_live_members "${pgid}"; then
      if [[ "${leader}" =~ ^[1-9][0-9]*$ ]]; then
        signal_process_tree "${leader}" KILL
      fi
      kill -KILL -- "-${pgid}" 2>/dev/null || true
    fi
  fi
  local settle_ticks=0
  while process_group_has_live_members "${pgid}" && [[ "${settle_ticks}" -lt 20 ]]; do
    /bin/sleep 0.1
    settle_ticks=$((settle_ticks + 1))
  done
  if process_group_has_live_members "${pgid}"; then
    echo "top15-study: ERROR: bounded capture process group ${pgid} survived TERM/KILL teardown" >&2
    return 1
  fi
  if [[ "${leader}" =~ ^[1-9][0-9]*$ ]]; then
    wait "${leader}" 2>/dev/null || true
  fi
  study_capture_pid=""
  study_capture_pgid=""
}

forward_capture_signal() {
  local status="$1"
  if [[ "${study_capture_signal_status}" == "0" ]]; then
    study_capture_signal_status="${status}"
  fi
  if [[ "${study_capture_pgid}" =~ ^[1-9][0-9]*$ ]]; then
    if [[ "${study_capture_term_sent}" == "0" ]]; then
      kill -TERM -- "-${study_capture_pgid}" 2>/dev/null || true
      study_capture_term_sent=1
    fi
  fi
}

restore_capture_shell_state() {
  trap - HUP INT QUIT TERM EXIT
  restore_trap "${study_capture_saved_hup_trap}" HUP
  restore_trap "${study_capture_saved_int_trap}" INT
  restore_trap "${study_capture_saved_quit_trap}" QUIT
  restore_trap "${study_capture_saved_term_trap}" TERM
  restore_trap "${study_capture_saved_exit_trap}" EXIT
  if [[ "${study_capture_monitor_was_on}" == "1" ]]; then set -m; else set +m; fi
}

clear_capture_state() {
  study_capture_pid=""
  study_capture_pgid=""
  study_capture_signal_status=0
  study_capture_term_sent=0
  study_capture_saved_hup_trap=""
  study_capture_saved_int_trap=""
  study_capture_saved_quit_trap=""
  study_capture_saved_term_trap=""
  study_capture_saved_exit_trap=""
  study_capture_monitor_was_on=0
  study_capture_state_dir=""
  study_capture_status_file=""
  study_capture_status_tmp_file=""
}

capture_exit_cleanup() {
  local exit_status="$?"
  trap - HUP INT QUIT TERM EXIT
  terminate_capture_group || true
  [[ -z "${study_capture_status_file}" ]] || rm -f "${study_capture_status_file}" || true
  [[ -z "${study_capture_status_tmp_file}" ]] || rm -f "${study_capture_status_tmp_file}" || true
  [[ -z "${study_capture_state_dir}" ]] || rmdir "${study_capture_state_dir}" 2>/dev/null || true
  if [[ -n "${study_capture_saved_exit_trap}" ]]; then
    (
      trap - EXIT
      eval "${study_capture_saved_exit_trap}"
      exit "${exit_status}"
    ) || true
  fi
  return "${exit_status}"
}

# Capture stdout/stderr from one finite command behind a wall-clock deadline.
# Bash 3.2 has no `wait -n` or portable `timeout`, so an isolated wrapper
# publishes its status atomically and the parent polls that marker. Signals and
# deadline expiry tear down the entire reader group with bounded TERM -> KILL.
run_bounded_capture() {
  local stdout_file="$1"
  local stderr_file="$2"
  local timeout_seconds="$3"
  shift 3
  local state_dir status_file status_tmp_file
  state_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-capture.XXXXXX")" || return 125
  status_file="${state_dir}/status"
  status_tmp_file="${state_dir}/status.tmp"
  study_capture_state_dir="${state_dir}"
  study_capture_status_file="${status_file}"
  study_capture_status_tmp_file="${status_tmp_file}"

  study_capture_pid=""
  study_capture_pgid=""
  study_capture_signal_status=0
  study_capture_term_sent=0
  study_capture_saved_hup_trap="$(trap -p HUP)"
  study_capture_saved_int_trap="$(trap -p INT)"
  study_capture_saved_quit_trap="$(trap -p QUIT)"
  study_capture_saved_term_trap="$(trap -p TERM)"
  study_capture_saved_exit_trap="$(trap -p EXIT)"
  case "$-" in *m*) study_capture_monitor_was_on=1 ;; *) study_capture_monitor_was_on=0 ;; esac
  trap 'forward_capture_signal 129' HUP
  trap 'forward_capture_signal 130' INT
  trap 'forward_capture_signal 131' QUIT
  trap 'forward_capture_signal 143' TERM
  trap capture_exit_cleanup EXIT

  set -m
  (
    set +m
    set +e
    "$@" > "${stdout_file}" 2> "${stderr_file}"
    capture_status="$?"
    if printf '%s\n' "${capture_status}" > "${status_tmp_file}"; then
      mv "${status_tmp_file}" "${status_file}"
    fi
    exit "${capture_status}"
  ) &
  study_capture_pid="$!"
  study_capture_pgid="${study_capture_pid}"
  if [[ "${study_capture_monitor_was_on}" == "0" ]]; then set +m; fi

  local waited_ticks=0
  local timeout_ticks=$((timeout_seconds * 10))
  while [[ ! -f "${status_file}" \
      && "${study_capture_signal_status}" == "0" \
      && "${waited_ticks}" -lt "${timeout_ticks}" ]]; do
    /bin/sleep 0.1
    waited_ticks=$((waited_ticks + 1))
  done

  local capture_status=0
  local teardown_failed=0
  if [[ "${study_capture_signal_status}" != "0" ]]; then
    capture_status="${study_capture_signal_status}"
    terminate_capture_group || teardown_failed=1
  elif [[ ! -f "${status_file}" ]]; then
    printf 'telemetry reader exceeded %ss wall-clock deadline\n' \
      "${timeout_seconds}" >> "${stderr_file}"
    capture_status=124
    terminate_capture_group || teardown_failed=1
  else
    capture_status="$(tr -d '[:space:]' < "${status_file}")"
    if [[ "${study_capture_pid}" =~ ^[1-9][0-9]*$ ]]; then
      wait "${study_capture_pid}" 2>/dev/null || true
    fi
    local completed_pgid="${study_capture_pgid}"
    if [[ "${study_capture_signal_status}" != "0" ]]; then
      terminate_capture_group || teardown_failed=1
      capture_status="${study_capture_signal_status}"
    elif process_group_has_live_members "${completed_pgid}"; then
      terminate_capture_group || teardown_failed=1
      capture_status=125
    elif [[ ! "${capture_status}" =~ ^[0-9]+$ ]] \
        || [[ "${capture_status}" -gt 255 ]]; then
      capture_status=125
      study_capture_pid=""
      study_capture_pgid=""
    else
      study_capture_pid=""
      study_capture_pgid=""
    fi
  fi

  rm -f "${status_file}" "${status_tmp_file}" || true
  rmdir "${state_dir}" 2>/dev/null || true
  # As above, preserve a signal delivered after the status marker, during
  # residual-group validation, or while the private status files are removed.
  # Keep this as the final operation before restoring the caller's traps.
  if [[ "${study_capture_signal_status}" != "0" ]]; then
    if terminate_capture_group; then
      if [[ "${teardown_failed}" == "0" ]]; then
        capture_status="${study_capture_signal_status}"
      fi
    else
      teardown_failed=1
    fi
  fi
  if [[ "${teardown_failed}" == "1" ]]; then
    capture_status=125
  fi
  restore_capture_shell_state
  clear_capture_state
  return "${capture_status}"
}

real_path() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

next_attempt_number() {
  local arm_dir="$1"
  local kind="$2"
  local highest
  highest="$(
    find "${arm_dir}" -maxdepth 1 -name "attempt-*.${kind}" -print \
      | sed -E "s|.*/attempt-([0-9]+)\\.${kind}$|\\1|" \
      | sort -n \
      | tail -1
  )"
  echo "$(( ${highest:-0} + 1 ))"
}

initialize_workspace_owner() {
  jq -n \
    --arg study "${study_id}" \
    --arg source_repo "$(real_path "${study_repo}")" \
    --arg workspace "$(real_path "${study_workspace}")" \
    '{study:$study, source_repo:$source_repo, workspace:$workspace}' \
    > "${study_owner_file}"
}

verify_workspace_owner() {
  [[ ! -L "${study_workspace}" ]] || die "workspace may not be a symlink: ${study_workspace}"
  [[ -d "${study_workspace}/.git" ]] || die "study workspace is not a Git checkout"
  [[ -f "${study_owner_file}" ]] || die "study workspace lacks ownership sentinel: ${study_owner_file}"
  local origin
  origin="$(git -C "${study_workspace}" remote get-url origin)"
  [[ "$(real_path "${origin}")" == "$(real_path "${study_repo}")" ]] \
    || die "study workspace origin does not match ${study_repo}"
  jq -e \
    --arg study "${study_id}" \
    --arg source_repo "$(real_path "${study_repo}")" \
    --arg workspace "$(real_path "${study_workspace}")" \
    '.study == $study and .source_repo == $source_repo and .workspace == $workspace' \
    "${study_owner_file}" >/dev/null \
    || die "study workspace ownership sentinel does not match this campaign"
}

require_inputs() {
  command -v git >/dev/null || die "git is required"
  command -v jq >/dev/null || die "jq is required"
  command -v shasum >/dev/null || die "shasum is required"
  command -v uv >/dev/null || die "uv is required"
  [[ -f "${study_manifest}" ]] || die "manifest not found: ${study_manifest}"
  [[ "${study_performance_enabled}" == "true" || "${study_performance_enabled}" == "false" ]] \
    || die "manifest performance.enabled must be boolean"
  [[ "${study_change_label_prefix}" =~ ^[a-z0-9][a-z0-9-]*$ ]] \
    || die "manifest change_label_prefix is invalid"
  [[ "$(jq -r '.required_environment.DARKBLOOM_EXPERT_ALIGNED_GATHER' "${study_manifest}")" == "0" ]] \
    || die "manifest must require DARKBLOOM_EXPERT_ALIGNED_GATHER=0"
  jq -e '
    (.study | type) == "string" and (.study | length) > 0
    and (.candidates | length) > 0
    and ([.candidates[].rank] | unique | length) == (.candidates | length)
    and ([.candidates[].submission_id] | unique | length) == (.candidates | length)
    and all(.candidates[];
      (.rank | type) == "number"
      and .rank == (.rank | floor)
      and (.submission_id | test("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"))
      and (.source_ref | test("^[0-9a-f]{40}$"))
    )
  ' "${study_manifest}" >/dev/null || die "manifest candidates are invalid"
  git -C "${study_repo}" cat-file -e "${study_harness_commit}^{commit}" \
    || die "manifest harness commit is unavailable: ${study_harness_commit}"
  git -C "${study_repo}" cat-file -e "${study_evaluator_commit}^{commit}" \
    || die "manifest evaluator commit is unavailable: ${study_evaluator_commit}"
  local candidate_source_ref
  while IFS= read -r candidate_source_ref; do
    git -C "${study_repo}" cat-file -e "${candidate_source_ref}^{commit}" \
      || die "manifest candidate commit is unavailable: ${candidate_source_ref}"
    git -C "${study_repo}" diff --quiet \
      "${study_harness_commit}" "${candidate_source_ref}" -- Sources/MLXFastTransform \
      || die "candidate ${candidate_source_ref} changes the offline transform but the study reuses shared weights"
  done < <(jq -r '.candidates[].source_ref' "${study_manifest}")
  if [[ "${study_performance_enabled}" == "true" ]]; then
    [[ -n "${study_baseline_commit}" && -n "${study_baseline_rank}" && -n "${study_baseline_id}" ]] \
      || die "performance-enabled manifest requires a complete baseline"
    git -C "${study_repo}" cat-file -e "${study_baseline_commit}^{commit}" \
      || die "manifest performance baseline commit is unavailable: ${study_baseline_commit}"
    git -C "${study_repo}" diff --quiet \
      "${study_harness_commit}" "${study_baseline_commit}" -- Sources/MLXFastTransform \
      || die "performance baseline changes the offline transform but the study reuses shared weights"
  fi
  local control_definition_path control_definition_sha256
  control_definition_path="$(jq -r '.control_definition.path // empty' "${study_manifest}")"
  control_definition_sha256="$(jq -r '.control_definition.sha256 // empty' "${study_manifest}")"
  if [[ -n "${control_definition_path}" || -n "${control_definition_sha256}" ]]; then
    [[ "${control_definition_path}" =~ ^[A-Za-z0-9._-]+$ \
        && "${control_definition_sha256}" =~ ^[0-9a-f]{64}$ ]] \
      || die "control definition provenance is invalid"
    local control_definition="$(dirname "${study_manifest}")/${control_definition_path}"
    [[ -f "${control_definition}" ]] || die "control definition is missing: ${control_definition}"
    [[ "$(sha256_file "${control_definition}")" == "${control_definition_sha256}" ]] \
      || die "control definition SHA mismatch"
    jq -e --slurpfile controls "${control_definition}" '
      $controls[0] as $definition
      | ([.candidates[] | {submission_id, source_ref}] | sort_by(.submission_id))
          == ([$definition.controls[] | {submission_id, source_ref}] | sort_by(.submission_id))
      and .harness_commit == $definition.provenance.common_harness_ref
      and .evaluator_commit == $definition.provenance.evaluator_commit
      and .evaluator_sha256 == $definition.provenance.evaluator_sha256
      and .quality_baseline == $definition.provenance.quality_baseline
      and .host == $definition.provenance.host
      and .required_environment == $definition.provenance.required_environment
    ' "${study_manifest}" >/dev/null || die "control run manifest diverges from its frozen definition"
  fi
  [[ -f "${study_weights}/config.json" ]] || die "shared transformed weights are missing: ${study_weights}"
  [[ -f "${study_weights}/model.safetensors.index.json" ]] \
    || die "shared transformed weight index is missing: ${study_weights}"
  [[ -f "${study_weights}/.benchmark-source.sha256" ]] \
    || die "shared transformed weights lack their source marker"
  [[ -f "${study_reference}/config.json" ]] || die "reference checkpoint is missing: ${study_reference}"
  [[ -f "${study_quality_baseline}/run.json" ]] || die "quality baseline is missing: ${study_quality_baseline}"
  [[ -f "${study_quality_baseline}/summary.json" ]] || die "quality baseline summary is missing"
  [[ -x "${study_quality_wrapper_source}" ]] || die "quality bridge wrapper is not executable"
  [[ -x "${study_local_benchmark_source}" ]] || die "pinned local benchmark is not executable"
  [[ -x "${study_fan_control_source}" ]] || die "pinned fan-control helper is not executable"
  [[ -x "${study_macmon_source}" ]] || die "pinned macmon reader is not executable"
  [[ "$(sha256_file "${study_local_benchmark_source}")" == "${study_local_benchmark_sha256}" ]] \
    || die "pinned local benchmark SHA mismatch: ${study_local_benchmark_source}"
  [[ "$(sha256_file "${study_fan_control_source}")" == "${study_fan_control_sha256}" ]] \
    || die "pinned fan-control SHA mismatch: ${study_fan_control_source}"
  [[ "$(sha256_file "${study_macmon_source}")" == "${study_macmon_sha256}" ]] \
    || die "pinned macmon SHA mismatch: ${study_macmon_source}"
  [[ "$("${study_macmon_source}" --version 2>&1 | head -n 1)" == "${study_macmon_version}" ]] \
    || die "pinned macmon version differs"
  grep -q 'gpu_telemetry_implausibility() {' "${study_local_benchmark_source}" \
    || die "pinned local benchmark lacks the fail-closed telemetry validator"
  grep -q 'refusing to claim a thermally gated local timing' "${study_local_benchmark_source}" \
    || die "pinned local benchmark lacks the fail-closed telemetry outcome"
  jq -e \
    --arg evaluator "${study_evaluator_sha256}" \
    --arg hardware_model "$(jq -r '.host.model' "${study_manifest}")" \
    --arg cpu_brand "$(jq -r '.host.chip' "${study_manifest}")" '
      .status == "completed"
      and .evaluation_valid == true
      and .profile == "quick"
      and .passes == 1
      and ((.suites | sort) == (["ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"] | sort))
      and .evaluator_provenance.sha256 == $evaluator
      and .host_identity.hardware_model == $hardware_model
      and .host_identity.cpu_brand == $cpu_brand
    ' "${study_quality_baseline}/run.json" >/dev/null \
    || die "quality baseline does not match the frozen full-quick M4 contract"
  jq -e '
    (.arms | length) == 1
    and .arms[0].overall_score.correct == 26
    and .arms[0].overall_score.total == 53
    and (.arms[0].metrics.ppl.mean | numbers) > 0
  ' "${study_quality_baseline}/summary.json" >/dev/null \
    || die "quality baseline counts do not match the frozen 26/53 contract"
  case "${study_workspace}" in
    /private/tmp/mlxfast-top15-*|/tmp/mlxfast-top15-*|"${study_repo}"/quality-results/.top15-workspace-*) ;;
    *) die "workspace must remain under a dedicated top-15 study prefix" ;;
  esac
  [[ "${study_perf_mode}" == "--local-submit" || "${study_perf_mode}" == "--local-iterate" ]] \
    || die "MLXFAST_TOP15_PERF_MODE must be --local-submit or --local-iterate"
  [[ "${study_allow_golden_drift}" == "0" || "${study_allow_golden_drift}" == "1" ]] \
    || die "MLXFAST_TOP15_ALLOW_GOLDEN_DRIFT must be 0 or 1"
  [[ "${study_quality_retries}" =~ ^[1-9][0-9]*$ ]] \
    || die "MLXFAST_TOP15_QUALITY_RETRIES must be a positive integer"
  local wrapper_environment
  wrapper_environment="$(MLXFAST_TOP15_REAL_QUALITY_BRIDGE=/usr/bin/env "${study_quality_wrapper_source}")" \
    || die "quality bridge wrapper failed to execute its preflight"
  printf '%s\n' "${wrapper_environment}" \
    | grep -qx 'DARKBLOOM_EXPERT_ALIGNED_GATHER=0' \
    || die "quality bridge wrapper failed its M4 override preflight"
  if printf '%s\n' "${wrapper_environment}" \
      | grep -q '^MLXFAST_TOP15_REAL_QUALITY_BRIDGE='; then
    die "quality bridge wrapper leaked its launcher variable"
  fi
}

copy_evaluator() {
  mkdir -p "${study_workspace}/senpai"
  git -C "${study_repo}" archive "${study_evaluator_commit}" -- \
    senpai/quality-eval senpai/quality_eval \
    | tar -x -C "${study_workspace}"
  chmod +x "${study_workspace}/senpai/quality-eval"
  install -m 755 "${study_quality_wrapper_source}" "${study_quality_wrapper}"
  local actual_evaluator
  actual_evaluator="$(
    LAGUNA_QUALITY_BOOTSTRAPPED=1 \
      PYTHONPATH="${study_workspace}/senpai/quality_eval" \
      python3 -c 'from laguna_quality.runner import _evaluation_provenance; print(_evaluation_provenance()["sha256"])'
  )"
  local expected_evaluator
  expected_evaluator="${study_evaluator_sha256}"
  [[ "${actual_evaluator}" == "${expected_evaluator}" ]] \
    || die "evaluator SHA mismatch: expected ${expected_evaluator}, got ${actual_evaluator}"
}

install_local_benchmark() {
  [[ "$(sha256_file "${study_local_benchmark_source}")" == "${study_local_benchmark_sha256}" ]] \
    || die "pinned local benchmark changed during the campaign"
  install -m 755 "${study_local_benchmark_source}" "${study_workspace}/benchmark.sh"
  install -m 755 "${study_fan_control_source}" "${study_workspace}/tools/fan-control.sh"
  [[ "$(sha256_file "${study_workspace}/benchmark.sh")" == "${study_local_benchmark_sha256}" ]] \
    || die "failed to install the pinned fail-closed local benchmark"
  [[ "$(sha256_file "${study_workspace}/tools/fan-control.sh")" == "${study_fan_control_sha256}" ]] \
    || die "failed to install the pinned fan-control helper"
}

prepare_workspace() {
  require_inputs
  mkdir -p "$(dirname "${study_workspace}")" "${study_results}/setup"
  if [[ ! -d "${study_workspace}/.git" ]]; then
    [[ ! -e "${study_workspace}" ]] || die "non-repository workspace already exists: ${study_workspace}"
    git clone --shared --no-checkout "${study_repo}" "${study_workspace}"
    initialize_workspace_owner
  fi
  verify_workspace_owner
  git -C "${study_workspace}" cat-file -e "${study_harness_commit}^{commit}"
  git -C "${study_workspace}" reset --hard "${study_harness_commit}"
  install_local_benchmark
  copy_evaluator
  if [[ ! -s "${study_workspace}/.build-worker/release/mlx.metallib" ]]; then
    (
      cd "${study_workspace}"
      env \
        MLXFAST_REFERENCE_DIR="${study_reference}" \
        MLXFAST_SKIP_WEIGHTS_DOWNLOAD=1 \
        ./setup.sh
    ) 2>&1 | tee "${study_results}/setup/setup.log"
  fi
  echo "top15-study: workspace ready at ${study_workspace}"
}

editable_paths() {
  jq -r '.editablePaths[]' "${study_workspace}/benchmark.json"
}

apply_snapshot() {
  local snapshot_commit="$1"
  local snapshot_label="$2"
  local -a snapshot_paths
  snapshot_paths=()
  local snapshot_path
  verify_workspace_owner
  while IFS= read -r snapshot_path; do
    snapshot_paths[${#snapshot_paths[@]}]="${snapshot_path}"
  done < <(editable_paths)
  [[ "${#snapshot_paths[@]}" -gt 0 ]] || die "benchmark editablePaths is empty"
  git -C "${study_workspace}" cat-file -e "${snapshot_commit}^{commit}" \
    || die "snapshot commit is unavailable: ${snapshot_commit}"
  git -C "${study_workspace}" reset --hard "${study_harness_commit}" >/dev/null \
    || die "failed to reset the owned workspace to ${study_harness_commit}"
  git -C "${study_workspace}" clean -fd -- "${snapshot_paths[@]}" >/dev/null \
    || die "failed to clean editable paths for ${snapshot_label}"
  git -C "${study_workspace}" restore \
    --source="${snapshot_commit}" --staged --worktree -- "${snapshot_paths[@]}" \
    || die "failed to restore editable paths for ${snapshot_label}"
  git -C "${study_workspace}" diff --quiet "${snapshot_commit}" -- "${snapshot_paths[@]}" \
    || die "editable snapshot verification failed for ${snapshot_label} (${snapshot_commit})"
  if git -C "${study_workspace}" ls-files --others --exclude-standard -- "${snapshot_paths[@]}" \
      | grep -q .; then
    die "untracked files remain inside editablePaths for ${snapshot_label}"
  fi
  # reset --hard above restores the legacy warn-and-continue gate. Reinstall
  # and verify the frozen fail-closed trusted wrapper before every arm.
  install_local_benchmark
  jq -n \
    --arg label "${snapshot_label}" \
    --arg source_ref "${snapshot_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg runner_sha256 "${study_runner_sha256}" \
    --arg local_benchmark_sha256 "${study_local_benchmark_sha256}" \
    --arg fan_control_sha256 "${study_fan_control_sha256}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg applied_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{label:$label, source_ref:$source_ref, harness_ref:$harness_ref, runner_sha256:$runner_sha256, local_benchmark_sha256:$local_benchmark_sha256, fan_control_sha256:$fan_control_sha256, macmon_sha256:$macmon_sha256, macmon_version:$macmon_version, applied_at:$applied_at}' \
    > "${study_results}/current-snapshot.json"
  echo "top15-study: applied ${snapshot_label} (${snapshot_commit})"
}

candidate_rows() {
  local candidate_selector="${1:-all}"
  if [[ "${candidate_selector}" == "all" ]]; then
    jq -r '.candidates[] | [.rank, .submission_id, .source_ref] | @tsv' "${study_manifest}"
    return
  fi
  jq -r --arg selector "${candidate_selector}" '
    .candidates[]
    | select((.rank | tostring) == $selector or (.submission_id | startswith($selector)))
    | [.rank, .submission_id, .source_ref]
    | @tsv
  ' "${study_manifest}"
}

arm_spec_json() {
  local phase="$1"
  local arm_rank="$2"
  local arm_id="$3"
  local arm_commit="$4"
  local performance_spec
  if [[ "${study_performance_enabled}" == "true" ]]; then
    performance_spec="$(jq -c -n \
      --arg mode "${study_perf_mode}" \
      --arg runtime "${study_perf_runtime}" \
      --arg allow_golden_drift "${study_allow_golden_drift}" \
      '{mode:$mode, runtime:$runtime, allow_golden_drift:$allow_golden_drift}')"
  else
    performance_spec='{"enabled":false}'
  fi
  jq -S -n \
    --arg study "${study_id}" \
    --arg phase "${phase}" \
    --arg rank "${arm_rank}" \
    --arg submission_id "${arm_id}" \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --argjson performance "${performance_spec}" \
    --arg evaluator_sha256 "${study_evaluator_sha256}" \
    --arg quality_baseline_run_sha256 "$(sha256_file "${study_quality_baseline}/run.json")" \
    --arg quality_baseline_summary_sha256 "$(sha256_file "${study_quality_baseline}/summary.json")" \
    --arg weights "$(real_path "${study_weights}")" \
    --arg weights_config_sha256 "$(sha256_file "${study_weights}/config.json")" \
    --arg weights_index_sha256 "$(sha256_file "${study_weights}/model.safetensors.index.json")" \
    --arg weights_transform_marker_sha256 "$(sha256_file "${study_weights}/.benchmark-source.sha256")" \
    --arg reference "$(real_path "${study_reference}")" \
    --arg reference_config_sha256 "$(sha256_file "${study_reference}/config.json")" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" '
      {
        study:$study,
        phase:$phase,
        arm:{rank:$rank, submission_id:$submission_id, source_ref:$source_ref},
        harness_ref:$harness_ref,
        manifest_sha256:$manifest_sha256,
        performance:$performance,
        quality:{
          evaluator_sha256:$evaluator_sha256,
          baseline_run_sha256:$quality_baseline_run_sha256,
          baseline_summary_sha256:$quality_baseline_summary_sha256,
          launcher_wrapper_sha256:$wrapper_sha256
        },
        artifacts:{
          weights:{
            path:$weights,
            config_sha256:$weights_config_sha256,
            index_sha256:$weights_index_sha256,
            transform_marker_sha256:$weights_transform_marker_sha256
          },
          reference:{path:$reference, config_sha256:$reference_config_sha256}
        },
        environment:{DARKBLOOM_EXPERT_ALIGNED_GATHER:"0"}
      }
    '
}

arm_spec_matches() {
  local arm_dir="$1"
  local phase="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  [[ -f "${arm_dir}/run-spec.json" ]] || return 1
  [[ "$(jq -S . "${arm_dir}/run-spec.json")" == "$(arm_spec_json "${phase}" "${arm_rank}" "${arm_id}" "${arm_commit}")" ]]
}

ensure_arm_spec() {
  local arm_dir="$1"
  local phase="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local expected
  expected="$(arm_spec_json "${phase}" "${arm_rank}" "${arm_id}" "${arm_commit}")"
  if [[ -f "${arm_dir}/run-spec.json" ]]; then
    if [[ "$(jq -S . "${arm_dir}/run-spec.json")" != "${expected}" ]]; then
      [[ ! -f "${arm_dir}/selected-attempt.txt" \
          && ! -f "${arm_dir}/terminal-noncompletion.json" ]] \
        || die "completed ${phase} arm cannot change its frozen run specification"
      local archived_spec="${arm_dir}/run-spec.previous.$(date -u +%Y%m%dT%H%M%SZ)-$$.json"
      mv "${arm_dir}/run-spec.json" "${archived_spec}" \
        || die "failed to archive the prior run specification"
      printf '%s\n' "${expected}" > "${arm_dir}/run-spec.json" \
        || die "failed to write the revised run specification"
    fi
  else
    printf '%s\n' "${expected}" > "${arm_dir}/run-spec.json" \
      || die "failed to write the run specification"
  fi
}

performance_log_thermal_valid() {
  local log_file="$1"
  local require_strict_confirmation="${2:-0}"
  [[ -f "${log_file}" ]] || return 1
  [[ "${require_strict_confirmation}" == "0" || "${require_strict_confirmation}" == "1" ]] \
    || return 1
  awk -v require_strict_confirmation="${require_strict_confirmation}" '
    /^mlxfast: benchmark elapsed=[0-9]+(\.[0-9]+)?s local thermal gate start phase=prefill$/ {
      if (state != 0) invalid = 1
      state = 1
      next
    }
    /^mlxfast: benchmark elapsed=[0-9]+(\.[0-9]+)?s local thermal gate complete phase=prefill$/ {
      if (state != 2) invalid = 1
      state = 3
      next
    }
    /^mlxfast: benchmark elapsed=[0-9]+(\.[0-9]+)?s local thermal gate start phase=decode$/ {
      if (state != 3) invalid = 1
      state = 4
      next
    }
    /^mlxfast: benchmark elapsed=[0-9]+(\.[0-9]+)?s local thermal gate complete phase=decode$/ {
      if (state != 5) invalid = 1
      state = 6
      next
    }
    /^benchmark\.sh: GPU cool-down gate passed \(current [0-9]+(\.[0-9]+)?C, target <=40C, waited [0-9]+s\)$/ {
      temperature = $0
      sub(/^.*current /, "", temperature)
      sub(/C,.*$/, "", temperature)
      temperature += 0
      if (state == 1) {
        if (require_strict_confirmation && (prefill_confirmations != 1 || prefill_confirmed_temp != temperature)) invalid = 1
        state = 2
      }
      else if (state == 4) {
        if (require_strict_confirmation && (decode_confirmations != 1 || decode_confirmed_temp != temperature)) invalid = 1
        state = 5
      }
      else invalid = 1
      passes += 1
      if (!(temperature > 5 && temperature <= 40)) invalid = 1
      next
    }
    /^benchmark\.sh: strict persistent macmon confirmed phase=(prefill|decode) samples=5 interval=1000ms final=[0-9]+(\.[0-9]+)?C$/ {
      phase = $0
      sub(/^.*phase=/, "", phase)
      sub(/ samples=.*$/, "", phase)
      temperature = $0
      sub(/^.* final=/, "", temperature)
      sub(/C$/, "", temperature)
      temperature += 0
      if (phase == "prefill" && state == 1) {
        prefill_confirmations += 1
        prefill_confirmed_temp = temperature
      } else if (phase == "decode" && state == 4) {
        decode_confirmations += 1
        decode_confirmed_temp = temperature
      } else invalid = 1
      next
    }
    /GPU cool-down gate passed|strict persistent macmon confirmed|local thermal gate (start|complete) phase=/ {
      invalid = 1
    }
    /local GPU cool-down gate disabled|skipping the GPU cool-down gate|temperature reading looks implausible|plausibility floor|retrying the temperature reader|strict local thermal telemetry|refusing to claim a thermally gated local timing|temperature reader returned no usable sample|local thermal gate failed/ {
      invalid = 1
    }
    END {
      exit !(state == 6 && passes == 2 && invalid == 0 && (!require_strict_confirmation || (prefill_confirmations == 1 && decode_confirmations == 1)))
    }
  ' "${log_file}"
}

thermal_samples_healthy() {
  local samples_file="$1"
  [[ -f "${samples_file}" ]] || return 1
  jq -s -e --argjson expected "${study_thermal_preflight_samples}" '
    length == $expected
    and all(.[];
      (.timestamp | type) == "string"
      and (.timestamp | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"))
      and (.temp.cpu_temp_avg | type) == "number"
      and (.temp.gpu_temp_avg | type) == "number"
      and .temp.cpu_temp_avg > 5
      and .temp.cpu_temp_avg <= 120
      and .temp.gpu_temp_avg > 5
      and .temp.gpu_temp_avg <= 120
    )
    and ([.[].timestamp] as $timestamps
      | ($timestamps | unique | length) == $expected
      and $timestamps == ($timestamps | sort))
    and ([.[].temp.gpu_temp_avg] | unique | length) >= 2
  ' "${samples_file}" >/dev/null
}

thermal_samples_ready() {
  local samples_file="$1"
  thermal_samples_healthy "${samples_file}" \
    && jq -s -e '.[-1].temp.gpu_temp_avg <= 40' "${samples_file}" >/dev/null
}

thermal_samples_fresh() {
  local samples_file="$1"
  local started_at="$2"
  local finished_at="$3"
  python3 -c '
import json
import sys
from datetime import datetime

def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

try:
    samples = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
    observed = [stamp(sample["timestamp"]) for sample in samples]
    started = stamp(sys.argv[2])
    finished = stamp(sys.argv[3])
except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if observed and started <= observed[0] <= observed[-1] < finished + 1.0 else 1)
' "${samples_file}" "${started_at}" "${finished_at}"
}

read_performance_fan_status() {
  /usr/bin/env -i \
    HOME="${HOME}" \
    LOGNAME="${LOGNAME:-${USER:-}}" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:${HOME}/bin" \
    TMPDIR="${TMPDIR:-/tmp}" \
    USER="${USER:-}" \
    "${study_fan_control_source}" status 2>/dev/null
}

performance_fan_status() {
  local fan_status
  fan_status="$(read_performance_fan_status)" || return 1
  [[ "${fan_status}" == "${study_performance_fan_policy}" ]] || return 1
  printf '%s\n' "${fan_status}"
}

performance_preflight_receipt_valid() {
  local receipt_name="$1"
  local receipt_sha256="$2"
  local expected_rank="${3:-}"
  local expected_id="${4:-}"
  local expected_source_ref="${5:-}"
  local expected_attempt="${6:-}"
  local attempt_started_at="${7:-}"
  local expected_require_cool="${8:-1}"
  [[ "${receipt_name}" =~ ^thermal-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9]+$ ]] || return 1
  [[ "${receipt_sha256}" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "${expected_require_cool}" == "0" || "${expected_require_cool}" == "1" ]] || return 1
  if [[ -n "${expected_rank}" ]]; then
    [[ "${expected_rank}" =~ ^[0-9]+$ \
        && "${expected_id}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ \
        && "${expected_source_ref}" =~ ^[0-9a-f]{40}$ \
        && "${expected_attempt}" =~ ^attempt-[1-9][0-9]*$ ]] || return 1
  else
    [[ -z "${expected_id}${expected_source_ref}${expected_attempt}${attempt_started_at}" ]] || return 1
  fi
  local receipt_dir="${study_results}/preflight/${receipt_name}"
  local meta_file="${receipt_dir}/meta.json"
  local samples_file="${receipt_dir}/samples.jsonl"
  local stderr_file="${receipt_dir}/macmon.stderr"
  [[ -d "${receipt_dir}" && ! -L "${receipt_dir}" ]] || return 1
  [[ -f "${meta_file}" && ! -L "${meta_file}" \
      && -f "${samples_file}" && ! -L "${samples_file}" \
      && -f "${stderr_file}" && ! -L "${stderr_file}" ]] || return 1
  [[ "$(sha256_file "${meta_file}")" == "${receipt_sha256}" ]] || return 1
  jq -e \
    --arg schema "${study_thermal_preflight_schema}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg fan_policy "${study_performance_fan_policy}" \
    --arg samples_sha256 "$(sha256_file "${samples_file}")" \
    --arg stderr_sha256 "$(sha256_file "${stderr_file}")" \
    --arg expected_rank "${expected_rank}" \
    --arg expected_id "${expected_id}" \
    --arg expected_source_ref "${expected_source_ref}" \
    --arg expected_attempt "${expected_attempt}" \
    --argjson expected_samples "${study_thermal_preflight_samples}" \
    --argjson expected_interval "${study_thermal_preflight_interval_ms}" \
    --argjson expected_reader_timeout "${study_thermal_reader_timeout_seconds}" \
    --argjson expected_require_cool "$([[ "${expected_require_cool}" == "1" ]] && echo true || echo false)" '
      .schema == $schema
      and .reader_exit_code == 0
      and .macmon_sha256 == $macmon_sha256
      and .macmon_version == $macmon_version
      and .fan_policy == $fan_policy
      and .fan_status == $fan_policy
      and .expected_samples == $expected_samples
      and .sample_count == $expected_samples
      and .interval_ms == $expected_interval
      and .reader_timeout_seconds == $expected_reader_timeout
      and .samples_sha256 == $samples_sha256
      and .stderr_sha256 == $stderr_sha256
      and .required_cool == $expected_require_cool
      and (
        if $expected_rank == "" then
          .attempt == null
        else
          .attempt.rank == ($expected_rank | tonumber)
          and .attempt.submission_id == $expected_id
          and .attempt.source_ref == $expected_source_ref
          and .attempt.name == $expected_attempt
        end
      )
      and (
        (.required_cool == true and .status == "healthy_ready")
        or (.required_cool == false and (.status == "healthy_ready" or .status == "healthy_hot"))
      )
    ' "${meta_file}" >/dev/null || return 1
  thermal_samples_healthy "${samples_file}" || return 1
  thermal_samples_fresh \
    "${samples_file}" \
    "$(jq -r '.started_at' "${meta_file}")" \
    "$(jq -r '.finished_at' "${meta_file}")" \
    || return 1
  if [[ "$(jq -r '.required_cool' "${meta_file}")" == "true" ]]; then
    thermal_samples_ready "${samples_file}" || return 1
  fi
  if [[ -n "${attempt_started_at}" ]]; then
    python3 -c '
import json
import sys
from datetime import datetime

def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

try:
    receipt = json.load(open(sys.argv[1], encoding="utf-8"))
    handoff = stamp(sys.argv[2]) - stamp(receipt["finished_at"])
    maximum = float(sys.argv[3])
except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)
raise SystemExit(0 if 0 <= handoff <= maximum else 1)
' "${meta_file}" "${attempt_started_at}" "${study_thermal_preflight_handoff_seconds}" || return 1
  fi
}

run_thermal_preflight() {
  local require_cool="${1:-1}"
  local attempt_rank="${2:-}"
  local attempt_id="${3:-}"
  local attempt_source_ref="${4:-}"
  local attempt_name="${5:-}"
  [[ "${require_cool}" == "0" || "${require_cool}" == "1" ]] \
    || die "thermal preflight require_cool must be 0 or 1"
  if [[ -n "${attempt_rank}" ]]; then
    [[ "${attempt_rank}" =~ ^[0-9]+$ \
        && "${attempt_id}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ \
        && "${attempt_source_ref}" =~ ^[0-9a-f]{40}$ \
        && "${attempt_name}" =~ ^attempt-[1-9][0-9]*$ ]] \
      || die "thermal preflight attempt binding is incomplete or invalid"
  else
    [[ -z "${attempt_id}${attempt_source_ref}${attempt_name}" ]] \
      || die "thermal preflight attempt binding is incomplete or invalid"
  fi
  require_inputs
  local fan_status
  if ! fan_status="$(performance_fan_status)"; then
    local observed_fan_status
    observed_fan_status="$(read_performance_fan_status || true)"
    echo "top15-study: thermal preflight requires '${study_performance_fan_policy}' fan control; observed '${observed_fan_status:-unreadable}'" >&2
    echo "top15-study: restore automatic control before measuring; never mix the legacy manual-80 comparator with auto-fan candidates" >&2
    return 75
  fi

  local preflight_root="${study_results}/preflight"
  [[ ! -L "${preflight_root}" ]] || die "thermal preflight root may not be a symlink: ${preflight_root}"
  mkdir -p "${preflight_root}"
  local receipt_dir
  receipt_dir="$(mktemp -d "${preflight_root}/thermal-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
  local samples_file="${receipt_dir}/samples.jsonl"
  local stderr_file="${receipt_dir}/macmon.stderr"
  local meta_file="${receipt_dir}/meta.json"
  local started_at finished_at reader_status
  started_at="$(utc_now)"
  if run_bounded_capture \
      "${samples_file}" "${stderr_file}" "${study_thermal_reader_timeout_seconds}" \
      /usr/bin/env -i \
        HOME="${HOME}" \
        LOGNAME="${LOGNAME:-${USER:-}}" \
        PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:${HOME}/bin" \
        TMPDIR="${TMPDIR:-/tmp}" \
        USER="${USER:-}" \
        "${study_macmon_source}" pipe \
          --samples "${study_thermal_preflight_samples}" \
          --interval "${study_thermal_preflight_interval_ms}"; then
    reader_status=0
  else
    reader_status="$?"
  fi
  finished_at="$(utc_now)"

  local health_status="invalid"
  local sample_count="0"
  local final_gpu_temp=""
  if [[ "${reader_status}" -eq 0 ]] && thermal_samples_healthy "${samples_file}"; then
    sample_count="$(jq -s 'length' "${samples_file}")"
    final_gpu_temp="$(jq -sr '.[-1].temp.gpu_temp_avg' "${samples_file}")"
    if thermal_samples_ready "${samples_file}"; then
      health_status="healthy_ready"
    else
      health_status="healthy_hot"
    fi
  fi

  jq -n \
    --arg schema "${study_thermal_preflight_schema}" \
    --arg started_at "${started_at}" \
    --arg finished_at "${finished_at}" \
    --argjson reader_exit_code "${reader_status}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg fan_policy "${study_performance_fan_policy}" \
    --arg fan_status "${fan_status}" \
    --arg status "${health_status}" \
    --arg sample_count "${sample_count}" \
    --arg final_gpu_temp_c "${final_gpu_temp}" \
    --arg samples_sha256 "$(sha256_file "${samples_file}")" \
    --arg stderr_sha256 "$(sha256_file "${stderr_file}")" \
    --arg attempt_rank "${attempt_rank}" \
    --arg attempt_id "${attempt_id}" \
    --arg attempt_source_ref "${attempt_source_ref}" \
    --arg attempt_name "${attempt_name}" \
    --argjson required_cool "$([[ "${require_cool}" == "1" ]] && echo true || echo false)" \
    --argjson expected_samples "${study_thermal_preflight_samples}" \
    --argjson interval_ms "${study_thermal_preflight_interval_ms}" \
    --argjson reader_timeout_seconds "${study_thermal_reader_timeout_seconds}" '
      {
        schema:$schema,
        started_at:$started_at,
        finished_at:$finished_at,
        reader_exit_code:$reader_exit_code,
        macmon_sha256:$macmon_sha256,
        macmon_version:$macmon_version,
        fan_policy:$fan_policy,
        fan_status:$fan_status,
        required_cool:$required_cool,
        expected_samples:$expected_samples,
        interval_ms:$interval_ms,
        reader_timeout_seconds:$reader_timeout_seconds,
        status:$status,
        sample_count:($sample_count | tonumber? // 0),
        final_gpu_temp_c:($final_gpu_temp_c | tonumber? // null),
        samples_sha256:$samples_sha256,
        stderr_sha256:$stderr_sha256,
        attempt:(
          if $attempt_rank == "" then null
          else {
            rank:($attempt_rank | tonumber),
            submission_id:$attempt_id,
            source_ref:$attempt_source_ref,
            name:$attempt_name
          }
          end
        )
      }
    ' > "${meta_file}"

  local receipt_name
  receipt_name="$(basename "${receipt_dir}")"
  case "${reader_status}" in
    125|129|130|131|143)
      echo "top15-study: thermal preflight reader supervision/termination failed with status ${reader_status}; receipt: ${meta_file}" >&2
      return "${reader_status}"
      ;;
  esac
  if [[ "${reader_status}" -ne 0 || "${health_status}" == "invalid" ]]; then
    echo "top15-study: thermal preflight rejected unhealthy or frozen telemetry; receipt: ${meta_file}" >&2
    return 75
  fi
  if [[ "${require_cool}" == "1" && "${health_status}" != "healthy_ready" ]]; then
    echo "top15-study: thermal preflight is healthy but GPU is ${final_gpu_temp}C (target <=40C); no model was loaded" >&2
    echo "top15-study: receipt: ${meta_file}" >&2
    return 75
  fi
  if ! performance_preflight_receipt_valid \
      "${receipt_name}" "$(sha256_file "${meta_file}")" \
      "${attempt_rank}" "${attempt_id}" "${attempt_source_ref}" "${attempt_name}" "" "${require_cool}"; then
    echo "top15-study: thermal preflight receipt failed its integrity check: ${meta_file}" >&2
    return 75
  fi
  study_current_performance_preflight="${receipt_name}"
  study_current_performance_preflight_sha256="$(sha256_file "${meta_file}")"
  echo "top15-study: thermal preflight ${health_status} at ${final_gpu_temp}C (${study_thermal_preflight_samples} responsive samples; fans ${fan_status})"
  echo "top15-study: thermal preflight receipt: ${meta_file}"
}

performance_log_thermal_self_test() {
  local test_dir valid_log invalid_log forged_log
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-thermal-test.XXXXXX")"
  valid_log="${test_dir}/valid.log"
  invalid_log="${test_dir}/invalid.log"
  forged_log="${test_dir}/forged.log"
  printf '%s\n' \
    'mlxfast: benchmark elapsed=77.0s local thermal gate start phase=prefill' \
    'benchmark.sh: strict persistent macmon confirmed phase=prefill samples=5 interval=1000ms final=40.0C' \
    'benchmark.sh: GPU cool-down gate passed (current 40.0C, target <=40C, waited 240s)' \
    'mlxfast: benchmark elapsed=529.3s local thermal gate complete phase=prefill' \
    'mlxfast: benchmark elapsed=573.5s local thermal gate start phase=decode' \
    'benchmark.sh: strict persistent macmon confirmed phase=decode samples=5 interval=1000ms final=39.9C' \
    'benchmark.sh: GPU cool-down gate passed (current 39.9C, target <=40C, waited 150s)' \
    'mlxfast: benchmark elapsed=855.2s local thermal gate complete phase=decode' \
    > "${valid_log}"
  printf '%s\n' \
    'mlxfast: benchmark elapsed=77.0s local thermal gate start phase=prefill' \
    'benchmark.sh: warning: the GPU temperature reads 1.5C; the temperature reading looks implausible' \
    'benchmark.sh: GPU cool-down gate passed (current 1.5C, target <=40C, waited 0s)' \
    'mlxfast: benchmark elapsed=80.0s local thermal gate complete phase=prefill' \
    'mlxfast: benchmark elapsed=81.0s local thermal gate start phase=decode' \
    'benchmark.sh: GPU cool-down gate passed (current 1.5C, target <=40C, waited 0s)' \
    'mlxfast: benchmark elapsed=82.0s local thermal gate complete phase=decode' \
    > "${invalid_log}"
  printf '%s\n' \
    'mlxfast: benchmark elapsed=77.0s local thermal gate start phase=prefill' \
    'mlxfast-worker: benchmark.sh: GPU cool-down gate passed (current 39.0C, target <=40C, waited 0s)' \
    'mlxfast: benchmark elapsed=78.0s local thermal gate complete phase=prefill' \
    'benchmark.sh: warning: skipping the GPU cool-down gate: no GPU temperature reader found.' \
    > "${forged_log}"
  performance_log_thermal_valid "${valid_log}" \
    || { rm -f "${valid_log}" "${invalid_log}" "${forged_log}"; rmdir "${test_dir}"; die "credible thermal log failed self-test"; }
  performance_log_thermal_valid "${valid_log}" 1 \
    || { rm -f "${valid_log}" "${invalid_log}" "${forged_log}"; rmdir "${test_dir}"; die "strict responsive thermal log failed self-test"; }
  if performance_log_thermal_valid "${invalid_log}"; then
    rm -f "${valid_log}" "${invalid_log}" "${forged_log}"
    rmdir "${test_dir}"
    die "implausible thermal log passed self-test"
  fi
  if performance_log_thermal_valid "${forged_log}"; then
    rm -f "${valid_log}" "${invalid_log}" "${forged_log}"
    rmdir "${test_dir}"
    die "worker-prefixed or skipped thermal gate passed self-test"
  fi
  rm -f "${valid_log}" "${invalid_log}" "${forged_log}"
  rmdir "${test_dir}"
  echo "top15-study: thermal log self-test passed"
}

thermal_samples_self_test() {
  local test_dir good frozen implausible hot out_of_order
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-samples-test.XXXXXX")"
  good="${test_dir}/good.jsonl"
  frozen="${test_dir}/frozen.jsonl"
  implausible="${test_dir}/implausible.jsonl"
  hot="${test_dir}/hot.jsonl"
  out_of_order="${test_dir}/out-of-order.jsonl"
  printf '%s\n' \
    '{"timestamp":"2026-08-03T00:00:00.000000+00:00","temp":{"cpu_temp_avg":38.0,"gpu_temp_avg":39.2}}' \
    '{"timestamp":"2026-08-03T00:00:01.000000+00:00","temp":{"cpu_temp_avg":38.1,"gpu_temp_avg":39.1}}' \
    '{"timestamp":"2026-08-03T00:00:02.000000+00:00","temp":{"cpu_temp_avg":38.0,"gpu_temp_avg":39.0}}' \
    '{"timestamp":"2026-08-03T00:00:03.000000+00:00","temp":{"cpu_temp_avg":37.9,"gpu_temp_avg":38.9}}' \
    '{"timestamp":"2026-08-03T00:00:04.000000+00:00","temp":{"cpu_temp_avg":37.8,"gpu_temp_avg":38.8}}' \
    > "${good}"
  sed -E 's/"gpu_temp_avg":[0-9]+\.[0-9]+/"gpu_temp_avg":39.0/' "${good}" > "${frozen}"
  sed 's/"gpu_temp_avg":39.0/"gpu_temp_avg":1.5/' "${frozen}" > "${implausible}"
  sed -E 's/"gpu_temp_avg":[0-9]+\.[0-9]+/"gpu_temp_avg":52.0/' "${good}" \
    | sed '5s/52.0/51.9/' > "${hot}"
  { sed -n '1p' "${good}"; sed -n '3p' "${good}"; sed -n '2p' "${good}"; sed -n '4,5p' "${good}"; } \
    > "${out_of_order}"
  thermal_samples_healthy "${good}" && thermal_samples_ready "${good}" \
    || die "responsive cool samples failed self-test"
  thermal_samples_fresh \
    "${good}" "2026-08-03T00:00:00Z" "2026-08-03T00:00:05Z" \
    || die "fresh samples failed self-test"
  ! thermal_samples_fresh \
    "${good}" "2026-08-03T01:00:00Z" "2026-08-03T01:00:05Z" \
    || die "stale samples passed self-test"
  ! thermal_samples_healthy "${frozen}" \
    || die "frozen plausible samples passed self-test"
  ! thermal_samples_healthy "${implausible}" \
    || die "implausible samples passed self-test"
  thermal_samples_healthy "${hot}" && ! thermal_samples_ready "${hot}" \
    || die "healthy hot samples failed self-test"
  ! thermal_samples_healthy "${out_of_order}" \
    || die "out-of-order sample timestamps passed self-test"
  rm -f "${good}" "${frozen}" "${implausible}" "${hot}" "${out_of_order}"
  rmdir "${test_dir}"
  echo "top15-study: persistent thermal sample self-test passed"
}

bounded_capture_self_test() {
  local test_dir fixture stdout_file stderr_file leader_file child_file
  local leader_pid child_pid status poll
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-capture-test.XXXXXX")"
  fixture="${test_dir}/stubborn.sh"
  stdout_file="${test_dir}/stdout"
  stderr_file="${test_dir}/stderr"
  leader_file="${test_dir}/leader.pid"
  child_file="${test_dir}/child.pid"
  printf '%s\n' \
    '#!/bin/bash' \
    'trap "" TERM' \
    'printf "%s\n" "$$" > "$1"' \
    '/bin/bash -c '\''trap "" TERM; printf "%s\n" "$$" > "$1"; while :; do /bin/sleep 1; done'\'' child "$2" &' \
    'while :; do /bin/sleep 1; done' \
    > "${fixture}"
  chmod 700 "${fixture}"
  if run_bounded_capture \
      "${stdout_file}" "${stderr_file}" 1 \
      "${fixture}" "${leader_file}" "${child_file}"; then
    status=0
  else
    status="$?"
  fi
  [[ "${status}" == "124" ]] \
    || die "bounded capture fixture returned ${status}, expected 124"
  grep -F 'exceeded 1s wall-clock deadline' "${stderr_file}" >/dev/null \
    || die "bounded capture timeout diagnostic is missing"
  [[ -s "${leader_file}" && -s "${child_file}" ]] \
    || die "bounded capture fixture did not record its process tree"
  leader_pid="$(tr -d '[:space:]' < "${leader_file}")"
  child_pid="$(tr -d '[:space:]' < "${child_file}")"
  for pid in "${leader_pid}" "${child_pid}"; do
    for poll in $(seq 1 20); do
      kill -0 "${pid}" 2>/dev/null || break
      /bin/sleep 0.1
    done
    if kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
      die "bounded capture fixture orphaned live pid ${pid}"
    fi
  done
  rm -f "${test_dir}"/*
  rmdir "${test_dir}"
  echo "top15-study: bounded capture self-test passed"
}

late_signal_self_test() {
  local test_dir
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-late-signal-test.XXXXXX")"
  (
    injected=0
    process_group_has_live_members() {
      if [[ "${injected}" == "0" ]]; then
        injected=1
        /bin/sh -c 'kill -TERM "$PPID"'
      fi
      return 1
    }
    if run_supervised_logged_command \
        "${test_dir}/supervised.log" /bin/bash -c 'exit 0'; then
      status=0
    else
      status="$?"
    fi
    [[ "${status}" == "143" ]]
  ) || die "supervised command erased a signal delivered during final group validation"
  (
    injected=0
    process_group_has_live_members() {
      if [[ "${injected}" == "0" ]]; then
        injected=1
        /bin/sh -c 'kill -TERM "$PPID"'
      fi
      return 1
    }
    if run_bounded_capture \
        "${test_dir}/capture.stdout" "${test_dir}/capture.stderr" 1 \
        /bin/bash -c 'exit 0'; then
      status=0
    else
      status="$?"
    fi
    [[ "${status}" == "143" ]]
  ) || die "bounded capture erased a signal delivered after its status marker"
  (
    injected=0
    rm() {
      if [[ "${injected}" == "0" ]]; then
        injected=1
        /bin/sh -c 'kill -TERM "$PPID"'
      fi
      command rm "$@"
    }
    if run_bounded_capture \
        "${test_dir}/cleanup.stdout" "${test_dir}/cleanup.stderr" 1 \
        /bin/bash -c 'exit 0'; then
      status=0
    else
      status="$?"
    fi
    [[ "${status}" == "143" ]]
  ) || die "bounded capture erased a signal delivered during private-file cleanup"
  rm -f "${test_dir}"/*
  rmdir "${test_dir}"
  echo "top15-study: late-signal precedence self-test passed"
}

supervised_pipeline_self_test() {
  local test_dir log_file fixture leader_pid_file child_pid_file
  local supervisor_pid leader_pid child_pid orphan_pid status=""
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-supervision-test.XXXXXX")"
  log_file="${test_dir}/command.log"
  fixture="${test_dir}/stubborn.sh"
  leader_pid_file="${test_dir}/leader.pid"
  child_pid_file="${test_dir}/child.pid"

  if run_supervised_logged_command \
      "${log_file}" /bin/bash -c 'printf "stdout-marker\n"; printf "stderr-marker\n" >&2; exit 37'; then
    status=0
  else
    status="$?"
  fi
  [[ "${status}" == "37" ]] \
    || die "supervised command status self-test returned ${status}, expected 37"
  grep -Fx 'stdout-marker' "${log_file}" >/dev/null \
    || die "supervised command stdout was not logged"
  grep -Fx 'stderr-marker' "${log_file}" >/dev/null \
    || die "supervised command stderr was not logged"

  for expected_monitor in off on; do
    (
      if [[ "${expected_monitor}" == "on" ]]; then set -m; else set +m; fi
      trap ':' HUP
      trap ':' INT
      trap ':' QUIT
      trap ':' TERM
      trap ':' EXIT
      before_hup="$(trap -p HUP)"
      before_int="$(trap -p INT)"
      before_quit="$(trap -p QUIT)"
      before_term="$(trap -p TERM)"
      before_exit="$(trap -p EXIT)"
      before_monitor="$-"
      run_supervised_logged_command "${test_dir}/state-${expected_monitor}.log" /bin/bash -c 'exit 0'
      [[ "$(trap -p HUP)" == "${before_hup}" \
          && "$(trap -p INT)" == "${before_int}" \
          && "$(trap -p QUIT)" == "${before_quit}" \
          && "$(trap -p TERM)" == "${before_term}" \
          && "$(trap -p EXIT)" == "${before_exit}" \
          && "$-" == "${before_monitor}" ]]
    ) || die "supervised command did not restore traps/monitor mode (${expected_monitor})"
  done

  printf '%s\n' \
    '#!/bin/bash' \
    'trap "" TERM' \
    'printf "%s\n" "$$" > "$1"' \
    '/bin/bash -c '\''trap "" TERM; printf "%s\n" "$$" > "$1"; while :; do /bin/sleep 1; done'\'' child "$2" &' \
    'while :; do /bin/sleep 1; done' \
    > "${fixture}"
  chmod 700 "${fixture}"
  (
    run_supervised_logged_command \
      "${log_file}" "${fixture}" "${leader_pid_file}" "${child_pid_file}"
  ) &
  supervisor_pid="$!"
  local poll
  for poll in $(seq 1 100); do
    [[ ! -s "${leader_pid_file}" || ! -s "${child_pid_file}" ]] || break
    sleep 0.05
  done
  [[ -s "${leader_pid_file}" && -s "${child_pid_file}" ]] \
    || { kill -TERM "${supervisor_pid}" 2>/dev/null || true; wait "${supervisor_pid}" 2>/dev/null || true; die "supervised process-tree fixture did not start"; }
  leader_pid="$(tr -d '[:space:]' < "${leader_pid_file}")"
  child_pid="$(tr -d '[:space:]' < "${child_pid_file}")"
  kill -TERM "${supervisor_pid}"
  if wait "${supervisor_pid}"; then
    status=0
  else
    status="$?"
  fi
  [[ "${status}" == "143" ]] \
    || die "supervised process-tree fixture returned ${status}, expected 143"
  for pid in "${leader_pid}" "${child_pid}"; do
    for poll in $(seq 1 20); do
      kill -0 "${pid}" 2>/dev/null || break
      /bin/sleep 0.1
    done
    if kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
      die "supervised process-tree fixture orphaned live pid ${pid}"
    fi
  done

  if run_supervised_logged_command \
      "${test_dir}/orphan.log" /bin/bash -c \
      '/bin/sleep 30 </dev/null >/dev/null 2>&1 & printf "%s\n" "$!" > "$1"' \
      fixture "${test_dir}/orphan.pid"; then
    status=0
  else
    status="$?"
  fi
  [[ "${status}" == "125" ]] \
    || die "normal-exit orphan fixture returned ${status}, expected 125"
  orphan_pid="$(tr -d '[:space:]' < "${test_dir}/orphan.pid")"
  for poll in $(seq 1 20); do
    kill -0 "${orphan_pid}" 2>/dev/null || break
    /bin/sleep 0.1
  done
  if kill -0 "${orphan_pid}" 2>/dev/null; then
    kill -KILL "${orphan_pid}" 2>/dev/null || true
    die "normal-exit orphan fixture left live child ${orphan_pid}"
  fi

  rm -f "${test_dir}"/*
  rmdir "${test_dir}"
  echo "top15-study: supervised process-tree self-test passed"
}

run_self_tests() {
  performance_log_thermal_self_test
  thermal_samples_self_test
  bounded_capture_self_test
  late_signal_self_test
  supervised_pipeline_self_test
  performance_batch_self_test
}

performance_attempt_valid() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local score_file="${arm_dir}/${attempt_name}.score.json"
  local meta_file="${arm_dir}/${attempt_name}.meta.json"
  local integrity_file="${arm_dir}/${attempt_name}.integrity.json"
  local log_file="${arm_dir}/${attempt_name}.log"
  arm_spec_matches "${arm_dir}" performance "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ -f "${score_file}" && -f "${meta_file}" && -f "${integrity_file}" ]] || return 1
  local require_strict_confirmation=0
  if [[ "$(jq -r '.runner_sha256 // empty' "${meta_file}")" == "${study_runner_sha256}" ]]; then
    require_strict_confirmation=1
  fi
  performance_log_thermal_valid "${log_file}" "${require_strict_confirmation}" || return 1
  jq -e \
    --arg runtime "${study_perf_runtime}" \
    --arg allow "${study_allow_golden_drift}" '
      (.score | numbers) > 0
      and (.metrics.decode_seconds_per_token | numbers) > 0
      and (.metrics.prefill_seconds_per_token | numbers) > 0
      and (.metrics.baseline_decode_seconds_per_token | numbers) > 0
      and (.metrics.baseline_prefill_seconds_per_token | numbers) > 0
      and (.metrics.decode_speedup | numbers) > 0
      and (.metrics.prefill_speedup | numbers) > 0
      and .metrics.decode_speedup_floor == 0.95
      and .metrics.prefill_speedup_floor == 0.95
      and .metrics.passed_decode_speedup_floor
          == (.metrics.decode_speedup >= .metrics.decode_speedup_floor)
      and .metrics.passed_prefill_speedup_floor
          == (.metrics.prefill_speedup >= .metrics.prefill_speedup_floor)
      and .metrics.checked_steps == 1025
      and .metrics.case_count == 1
      and (.metrics.golden_hash | test("^[0-9a-f]{64}$"))
      and .metrics.runtime == $runtime
      and .metrics.partial_result == false
      and (
        ($allow == "0" and .passed == true and .metrics.passed_correctness == true)
        or
        ($allow == "1" and (
          (.passed == true and .metrics.passed_correctness == true)
          or (.passed == false and .metrics.passed_correctness == false)
        ))
      )
    ' "${score_file}" >/dev/null || return 1
  local baseline_decode decode decode_speedup baseline_prefill prefill prefill_speedup score
  IFS=$'\t' read -r \
    baseline_decode decode decode_speedup baseline_prefill prefill prefill_speedup score \
    < <(jq -r '[
      .metrics.baseline_decode_seconds_per_token,
      .metrics.decode_seconds_per_token,
      .metrics.decode_speedup,
      .metrics.baseline_prefill_seconds_per_token,
      .metrics.prefill_seconds_per_token,
      .metrics.prefill_speedup,
      .score
    ] | @tsv' "${score_file}")
  awk \
    -v bd="${baseline_decode}" -v d="${decode}" -v ds="${decode_speedup}" \
    -v bp="${baseline_prefill}" -v p="${prefill}" -v ps="${prefill_speedup}" \
    -v score="${score}" '
      function absolute(value) { return value < 0 ? -value : value }
      BEGIN {
        expected_ds = bd / d
        expected_ps = bp / p
        expected_score = (expected_ds ^ 0.75) * (expected_ps ^ 0.25)
        valid = absolute(ds - expected_ds) <= 1e-10 && absolute(ps - expected_ps) <= 1e-10 && absolute(score - expected_score) <= 1e-10
        exit !valid
      }
    ' || return 1
  if [[ "${study_allow_golden_drift}" == "1" \
      && "$(jq -r '.metrics.passed_correctness' "${score_file}")" == "false" \
      && "${arm_commit}" != "${study_baseline_commit}" ]]; then
    local baseline_score="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}/score.json"
    [[ -f "${baseline_score}" ]] || return 1
    [[ "$(jq -c '{golden_hash:.metrics.golden_hash,first_failing_case:.metrics.first_failing_case,first_failing_step:.metrics.first_failing_step,expected_token:.metrics.expected_token,actual_token:.metrics.actual_token}' "${score_file}")" \
        == "$(jq -c '{golden_hash:.metrics.golden_hash,first_failing_case:.metrics.first_failing_case,first_failing_step:.metrics.first_failing_step,expected_token:.metrics.expected_token,actual_token:.metrics.actual_token}' "${baseline_score}")" ]] \
      || return 1
  fi
  jq -e \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg mode "${study_perf_mode}" \
    --arg runtime "${study_perf_runtime}" \
    --arg runner_sha256 "${study_runner_sha256}" \
    --arg local_benchmark_sha256 "${study_local_benchmark_sha256}" \
    --arg fan_control_sha256 "${study_fan_control_sha256}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg fan_policy "${study_performance_fan_policy}" \
    --arg log_sha256 "$(sha256_file "${log_file}")" \
    --arg environment_policy "${study_performance_environment_policy}" \
    --arg local_benchmark_cutover "${study_local_benchmark_cutover}" \
    --arg legacy_baseline_ref "${study_baseline_commit}" \
    --arg legacy_baseline_log_sha256 "${study_legacy_baseline_log_sha256}" \
    --arg expert_aligned_gather "0" \
    --arg reader_timeout_seconds "${study_thermal_reader_timeout_seconds}" \
    --arg allow_golden_drift "${study_allow_golden_drift}" '
      .exit_code == 0
      and .source_ref == $source_ref
      and .harness_ref == $harness_ref
      and .manifest_sha256 == $manifest_sha256
      and .mode == $mode
      and .runtime == $runtime
      and (
        (
          .local_benchmark_sha256 == $local_benchmark_sha256
          and .runner_sha256 == $runner_sha256
          and .fan_control_sha256 == $fan_control_sha256
          and .macmon_sha256 == $macmon_sha256
          and .macmon_version == $macmon_version
          and .fan_policy == $fan_policy
          and .fan_status_before == $fan_policy
          and .fan_status_after == $fan_policy
          and (.started_at | type) == "string"
          and (.thermal_preflight_receipt | type) == "string"
          and (.thermal_preflight_sha256 | test("^[0-9a-f]{64}$"))
          and .log_sha256 == $log_sha256
          and .environment_policy == $environment_policy
          and .environment.MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY == "1"
          and .environment.MLXFAST_LOCAL_COOL_GATE_READER_TIMEOUT_SECONDS == $reader_timeout_seconds
          and .environment.MLXFAST_LOCAL_FAN_PROMPT == "0"
        )
        or (
          (has("local_benchmark_sha256") | not)
          and (has("runner_sha256") | not)
          and (has("fan_control_sha256") | not)
          and (has("macmon_sha256") | not)
          and (has("log_sha256") | not)
          and (has("environment_policy") | not)
          and (.finished_at | type) == "string"
          and .finished_at <= $local_benchmark_cutover
          and $source_ref == $legacy_baseline_ref
          and $log_sha256 == $legacy_baseline_log_sha256
        )
      )
      and .environment.DARKBLOOM_EXPERT_ALIGNED_GATHER == $expert_aligned_gather
      and .environment.MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT == $allow_golden_drift
    ' "${meta_file}" >/dev/null || return 1
  if [[ "$(jq -r '.runner_sha256 // empty' "${meta_file}")" == "${study_runner_sha256}" ]]; then
    local preflight_receipt preflight_sha256 attempt_started_at preflight_required_cool
    IFS=$'\t' read -r preflight_receipt preflight_sha256 attempt_started_at \
      < <(jq -r '[.thermal_preflight_receipt, .thermal_preflight_sha256, .started_at] | @tsv' "${meta_file}")
    [[ "${preflight_receipt}" =~ ^thermal-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9]+$ ]] \
      || return 1
    case "$(jq -r '.required_cool' "${study_results}/preflight/${preflight_receipt}/meta.json" 2>/dev/null)" in
      true) preflight_required_cool=1 ;;
      false) preflight_required_cool=0 ;;
      *) return 1 ;;
    esac
    performance_preflight_receipt_valid \
      "${preflight_receipt}" "${preflight_sha256}" \
      "${arm_rank}" "${arm_id}" "${arm_commit}" "${attempt_name}" \
      "${attempt_started_at}" "${preflight_required_cool}" \
      || return 1
  fi
  local score_sha256
  score_sha256="$(sha256_file "${score_file}")"
  jq -e \
    --arg score_sha256 "${score_sha256}" \
    --arg weights_sha256 "$(jq -r '.metrics.weights_hash' "${score_file}")" \
    --argjson weights_file_count "$(jq -r '.metrics.weights_file_count' "${score_file}")" \
    --argjson weights_byte_count "$(jq -r '.metrics.weights_byte_count' "${score_file}")" \
    --arg golden_sha256 "$(jq -r '.metrics.golden_hash' "${score_file}")" '
      type == "object"
      and .score_sha256 == $score_sha256
      and .weights_sha256 == $weights_sha256
      and .weights_file_count == $weights_file_count
      and .weights_byte_count == $weights_byte_count
      and .golden_sha256 == $golden_sha256
    ' "${integrity_file}" >/dev/null || return 1
  [[ "$(jq -r '.score_sha256' "${meta_file}")" == "${score_sha256}" ]] || return 1
  [[ "$(jq -r '.integrity_sha256' "${meta_file}")" == "$(sha256_file "${integrity_file}")" ]] || return 1
}

performance_result_valid() {
  local arm_dir="$1"
  local arm_rank="$2"
  local arm_id="$3"
  local arm_commit="$4"
  [[ -f "${arm_dir}/selected-attempt.txt" && -f "${arm_dir}/score.json" ]] || return 1
  local attempt_name
  attempt_name="$(tr -d '[:space:]' < "${arm_dir}/selected-attempt.txt")"
  [[ "${attempt_name}" =~ ^attempt-[1-9][0-9]*$ ]] || return 1
  performance_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ "$(sha256_file "${arm_dir}/score.json")" == "$(sha256_file "${arm_dir}/${attempt_name}.score.json")" ]]
}

performance_attempt_current_contract() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  performance_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  jq -e \
    --arg runner_sha256 "${study_runner_sha256}" \
    --arg local_benchmark_sha256 "${study_local_benchmark_sha256}" \
    --arg fan_control_sha256 "${study_fan_control_sha256}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg environment_policy "${study_performance_environment_policy}" \
    --arg reader_timeout_seconds "${study_thermal_reader_timeout_seconds}" \
    --arg fan_policy "${study_performance_fan_policy}" '
      .runner_sha256 == $runner_sha256
      and .local_benchmark_sha256 == $local_benchmark_sha256
      and .fan_control_sha256 == $fan_control_sha256
      and .macmon_sha256 == $macmon_sha256
      and .macmon_version == $macmon_version
      and .environment_policy == $environment_policy
      and .fan_policy == $fan_policy
      and .fan_status_before == $fan_policy
      and .fan_status_after == $fan_policy
      and .environment.MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY == "1"
      and .environment.MLXFAST_LOCAL_COOL_GATE_READER_TIMEOUT_SECONDS == $reader_timeout_seconds
      and .environment.MLXFAST_LOCAL_FAN_PROMPT == "0"
    ' "${arm_dir}/${attempt_name}.meta.json" >/dev/null
}

performance_result_current_contract() {
  local arm_dir="$1"
  local arm_rank="$2"
  local arm_id="$3"
  local arm_commit="$4"
  [[ -f "${arm_dir}/selected-attempt.txt" && -f "${arm_dir}/score.json" ]] || return 1
  local attempt_name
  attempt_name="$(tr -d '[:space:]' < "${arm_dir}/selected-attempt.txt")"
  [[ "${attempt_name}" =~ ^attempt-[1-9][0-9]*$ ]] || return 1
  performance_attempt_current_contract \
    "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ "$(sha256_file "${arm_dir}/score.json")" == "$(sha256_file "${arm_dir}/${attempt_name}.score.json")" ]]
}

performance_selection_current_complete() {
  local candidate_selector="$1"
  local baseline_dir="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}"
  performance_result_current_contract \
    "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}" \
    || return 1
  [[ "${candidate_selector}" == "baseline" ]] && return 0
  local selected_count=0
  local candidate_rank candidate_id candidate_commit performance_dir
  while IFS=$'\t' read -r candidate_rank candidate_id candidate_commit; do
    [[ -n "${candidate_rank}" ]] || continue
    selected_count="$((selected_count + 1))"
    performance_dir="${study_results}/performance/${candidate_rank}-${candidate_id}"
    performance_result_current_contract \
      "${performance_dir}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}" \
      || return 1
  done < <(candidate_rows "${candidate_selector}")
  [[ "${selected_count}" -gt 0 ]]
}

print_performance_comparison() {
  local arm_rank="$1"
  local score_file="$2"
  local baseline_score="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}/score.json"
  local candidate_prefill candidate_decode calibration_score
  IFS=$'\t' read -r candidate_prefill candidate_decode calibration_score \
    < <(jq -r '[.metrics.prefill_seconds_per_token, .metrics.decode_seconds_per_token, .score] | @tsv' "${score_file}")
  if [[ "${arm_rank}" == "${study_baseline_rank}" ]]; then
    printf 'top15-study: rank-%s local comparator prefill=%.6fms/token decode=%.6fms/token; harness estimate=%.6f vs pinned M5 calibration (not the study comparison)\n' \
      "${arm_rank}" \
      "$(awk -v value="${candidate_prefill}" 'BEGIN { print value * 1000 }')" \
      "$(awk -v value="${candidate_decode}" 'BEGIN { print value * 1000 }')" \
      "${calibration_score}"
    return 0
  fi
  local baseline_dir="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}"
  if ! performance_result_current_contract \
      "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"; then
    echo "top15-study: rank-${arm_rank} completed, but no current-contract rank-${study_baseline_rank} comparison is available" >&2
    return 0
  fi
  local baseline_prefill baseline_decode
  IFS=$'\t' read -r baseline_prefill baseline_decode \
    < <(jq -r '[.metrics.prefill_seconds_per_token, .metrics.decode_seconds_per_token] | @tsv' "${baseline_score}")
  awk \
    -v rank="${arm_rank}" \
    -v bp="${baseline_prefill}" -v bd="${baseline_decode}" \
    -v cp="${candidate_prefill}" -v cd="${candidate_decode}" \
    -v calibration="${calibration_score}" '
      BEGIN {
        prefill = bp / cp
        decode = bd / cd
        index = (decode ^ 0.75) * (prefill ^ 0.25)
        printf "top15-study: rank-%s vs rank-111 on this M4: prefill=%.6fx decode=%.6fx weighted_index=%.6fx; harness estimate=%.6f vs pinned M5 calibration (not the study comparison)\n", rank, prefill, decode, index, calibration
      }
    '
}

execute_performance_benchmark() {
  local attempt_score="$1"
  local attempt_integrity="$2"
  (
    cd "${study_workspace}"
    /usr/bin/env -i \
      HOME="${HOME}" \
      LOGNAME="${LOGNAME:-${USER:-}}" \
      PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:${HOME}/bin" \
      TMPDIR="${TMPDIR:-/tmp}" \
      USER="${USER:-}" \
      DARKBLOOM_EXPERT_ALIGNED_GATHER=0 \
      MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT="${study_allow_golden_drift}" \
      MLXFAST_LOCAL_COOL_GATE=1 \
      MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY=1 \
      MLXFAST_LOCAL_COOL_GATE_READER_TIMEOUT_SECONDS="${study_thermal_reader_timeout_seconds}" \
      MLXFAST_LOCAL_FAN_PROMPT=0 \
      MLXFAST_MACMON_BIN="${study_macmon_source}" \
      MLXFAST_REFERENCE_DIR="${study_reference}" \
      MLXFAST_WEIGHTS_PATH="${study_weights}" \
      MLXFAST_SKIP_TRANSFORM=1 \
      MLXFAST_SCORE_PATH="${attempt_score}" \
      MLXFAST_INTEGRITY_PATH="${attempt_integrity}" \
      ./benchmark.sh "${study_perf_mode}"
  )
}

run_performance_arm() {
  local arm_rank="$1"
  local arm_id="$2"
  local arm_commit="$3"
  local arm_dir="${study_results}/performance/${arm_rank}-${arm_id}"
  mkdir -p "${arm_dir}"
  ensure_arm_spec "${arm_dir}" performance "${arm_rank}" "${arm_id}" "${arm_commit}"
  if performance_result_current_contract "${arm_dir}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
    echo "top15-study: performance already complete for ${arm_rank}-${arm_id}"
    return 0
  fi
  apply_snapshot "${arm_commit}" "${arm_rank}-${arm_id}"
  local attempt_number
  attempt_number="$(next_attempt_number "${arm_dir}" log)"
  local attempt_name="attempt-${attempt_number}"
  local attempt_log="${arm_dir}/${attempt_name}.log"
  local attempt_score="${arm_dir}/${attempt_name}.score.json"
  local attempt_integrity="${arm_dir}/${attempt_name}.integrity.json"
  local attempt_meta="${arm_dir}/${attempt_name}.meta.json"
  local fan_status_before
  if ! fan_status_before="$(performance_fan_status)"; then
    echo "top15-study: refusing performance arm ${arm_rank}: fan policy is not verified '${study_performance_fan_policy}'" >&2
    return 75
  fi
  local require_cool="${study_next_preflight_requires_cool}"
  local preflight_status
  if run_thermal_preflight \
      "${require_cool}" "${arm_rank}" "${arm_id}" "${arm_commit}" "${attempt_name}"; then
    :
  else
    preflight_status="$?"
    return "${preflight_status}"
  fi
  local attempt_preflight="${study_current_performance_preflight}"
  local attempt_preflight_sha256="${study_current_performance_preflight_sha256}"
  study_current_performance_preflight=""
  study_current_performance_preflight_sha256=""
  local attempt_started_at
  attempt_started_at="$(utc_now)"
  performance_preflight_receipt_valid \
    "${attempt_preflight}" "${attempt_preflight_sha256}" \
    "${arm_rank}" "${arm_id}" "${arm_commit}" "${attempt_name}" \
    "${attempt_started_at}" "${require_cool}" \
    || die "attempt-bound thermal preflight failed its handoff check"
  study_next_preflight_requires_cool=0

  local benchmark_status
  if run_supervised_logged_command \
      "${attempt_log}" execute_performance_benchmark "${attempt_score}" "${attempt_integrity}"; then
    benchmark_status=0
  else
    benchmark_status="$?"
  fi
  local fan_status_after
  fan_status_after="$(read_performance_fan_status || true)"
  local score_sha256=""
  local integrity_sha256=""
  local log_sha256
  [[ ! -f "${attempt_score}" ]] || score_sha256="$(sha256_file "${attempt_score}")"
  [[ ! -f "${attempt_integrity}" ]] || integrity_sha256="$(sha256_file "${attempt_integrity}")"
  log_sha256="$(sha256_file "${attempt_log}")"
  jq -n \
    --argjson exit_code "${benchmark_status}" \
    --arg started_at "${attempt_started_at}" \
    --arg finished_at "$(utc_now)" \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg mode "${study_perf_mode}" \
    --arg runtime "${study_perf_runtime}" \
    --arg runner_sha256 "${study_runner_sha256}" \
    --arg local_benchmark_sha256 "${study_local_benchmark_sha256}" \
    --arg fan_control_sha256 "${study_fan_control_sha256}" \
    --arg macmon_sha256 "${study_macmon_sha256}" \
    --arg macmon_version "${study_macmon_version}" \
    --arg fan_policy "${study_performance_fan_policy}" \
    --arg fan_status_before "${fan_status_before}" \
    --arg fan_status_after "${fan_status_after}" \
    --arg thermal_preflight_receipt "${attempt_preflight}" \
    --arg thermal_preflight_sha256 "${attempt_preflight_sha256}" \
    --arg log_sha256 "${log_sha256}" \
    --arg environment_policy "${study_performance_environment_policy}" \
    --arg score_sha256 "${score_sha256}" \
    --arg integrity_sha256 "${integrity_sha256}" \
    --arg expert_aligned_gather "0" \
    --arg reader_timeout_seconds "${study_thermal_reader_timeout_seconds}" \
    --arg allow_golden_drift "${study_allow_golden_drift}" '
      {
        exit_code:$exit_code,
        started_at:$started_at,
        finished_at:$finished_at,
        source_ref:$source_ref,
        harness_ref:$harness_ref,
        manifest_sha256:$manifest_sha256,
        mode:$mode,
        runtime:$runtime,
        runner_sha256:$runner_sha256,
        local_benchmark_sha256:$local_benchmark_sha256,
        fan_control_sha256:$fan_control_sha256,
        macmon_sha256:$macmon_sha256,
        macmon_version:$macmon_version,
        fan_policy:$fan_policy,
        fan_status_before:$fan_status_before,
        fan_status_after:$fan_status_after,
        thermal_preflight_receipt:$thermal_preflight_receipt,
        thermal_preflight_sha256:$thermal_preflight_sha256,
        log_sha256:$log_sha256,
        environment_policy:$environment_policy,
        score_sha256:$score_sha256,
        integrity_sha256:$integrity_sha256,
        environment:{
          DARKBLOOM_EXPERT_ALIGNED_GATHER:$expert_aligned_gather,
          MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT:$allow_golden_drift,
          MLXFAST_LOCAL_COOL_GATE_STRICT_TELEMETRY:"1",
          MLXFAST_LOCAL_COOL_GATE_READER_TIMEOUT_SECONDS:$reader_timeout_seconds,
          MLXFAST_LOCAL_FAN_PROMPT:"0"
        }
      }
    ' > "${attempt_meta}"
  if [[ "${fan_status_after}" != "${study_performance_fan_policy}" ]]; then
    echo "top15-study: aborting the performance campaign because post-arm fan policy is '${fan_status_after:-unreadable}', expected '${study_performance_fan_policy}'" >&2
    return 75
  fi
  case "${benchmark_status}" in
    125|129|130|131|143) return "${benchmark_status}" ;;
  esac
  if performance_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
    cp "${attempt_score}" "${arm_dir}/score.json"
    printf '%s\n' "${attempt_name}" > "${arm_dir}/selected-attempt.txt"
    print_performance_comparison "${arm_rank}" "${attempt_score}"
    echo "top15-study: performance complete for ${arm_rank}-${arm_id}"
    return 0
  fi
  echo "top15-study: performance failed for ${arm_rank}-${arm_id}; see ${attempt_log}" >&2
  if [[ "${benchmark_status}" -eq 0 ]] \
      && ! performance_log_thermal_valid "${attempt_log}"; then
    echo "top15-study: aborting the performance campaign because a status-0 attempt lacks two trustworthy ordered thermal gates" >&2
    return 75
  fi
  if grep -Eq \
      'local GPU cool-down gate failed|strict local thermal telemetry|temperature reading looks implausible|refusing to claim a thermally gated local timing|skipping the GPU cool-down gate|temperature reader returned no usable sample' \
      "${attempt_log}"; then
    echo "top15-study: aborting the performance campaign because thermal state or telemetry is not trustworthy" >&2
    return 75
  fi
  return 1
}

run_performance() {
  local candidate_selector="${1:-all}"
  [[ "${study_performance_enabled}" == "true" ]] \
    || die "performance is disabled by manifest: ${study_manifest}"
  require_inputs
  if performance_selection_current_complete "${candidate_selector}"; then
    echo "top15-study: selected performance work is already complete under the current contract"
    return 0
  fi
  local baseline_dir="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}"
  if [[ "${candidate_selector}" != "all" && "${candidate_selector}" != "baseline" ]]; then
    performance_result_current_contract \
      "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}" \
      || die "rank-${study_baseline_rank} must be refreshed under the current auto-fan/env-i/telemetry contract before any candidate; run: $0 perf baseline"
  fi
  study_next_preflight_requires_cool=1
  prepare_workspace
  if [[ "${candidate_selector}" == "all" || "${candidate_selector}" == "baseline" ]]; then
    local baseline_status
    if run_performance_arm "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"; then
      :
    else
      baseline_status="$?"
      return "${baseline_status}"
    fi
    [[ "${candidate_selector}" == "baseline" ]] && return
  fi
  local selected_count=0
  local failure_count=0
  local candidate_rank candidate_id candidate_commit arm_status
  while IFS=$'\t' read -r candidate_rank candidate_id candidate_commit; do
    [[ -n "${candidate_rank}" ]] || continue
    selected_count="$((selected_count + 1))"
    if run_performance_arm "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
      :
    else
      arm_status="$?"
      case "${arm_status}" in
        75|125|129|130|131|143) return "${arm_status}" ;;
      esac
      failure_count="$((failure_count + 1))"
    fi
  done < <(candidate_rows "${candidate_selector}")
  [[ "${candidate_selector}" == "all" || "${selected_count}" -gt 0 ]] \
    || die "no candidate matched ${candidate_selector}"
  [[ "${failure_count}" -eq 0 ]] \
    || die "${failure_count} performance arm(s) failed; valid arms were retained"
}

# Run one freshly normalized, explicitly bounded local sample. This is the
# detached-campaign entrypoint: refresh rank 111 first, then execute one to
# three uniquely resolved candidates in the requested order. Any arm error
# exits immediately, so launchd never advances past a failed correctness,
# telemetry, thermal, or process-supervision boundary.
run_performance_batch() {
  [[ "$#" -ge 1 && "$#" -le 3 ]] \
    || die "perf-batch requires one to three candidate ranks or submission prefixes"
  local selectors=("$@")
  local resolved_ranks=()
  local resolved_ids=()
  local resolved_refs=()
  local resolved_count=0
  local selector rows row_count rank submission_id source_ref existing
  for selector in "${selectors[@]}"; do
    [[ "${selector}" != "all" && "${selector}" != "baseline" ]] \
      || die "perf-batch candidates must be explicit ranks or submission prefixes"
    rows="$(candidate_rows "${selector}")"
    row_count="$(printf '%s\n' "${rows}" | awk 'NF { count += 1 } END { print count + 0 }')"
    [[ "${row_count}" == "1" ]] \
      || die "perf-batch selector '${selector}' resolved to ${row_count} candidates; use an exact rank or longer submission prefix"
    IFS=$'\t' read -r rank submission_id source_ref <<< "${rows}"
    if [[ "${resolved_count}" -gt 0 ]]; then
      for existing in "${resolved_ranks[@]}"; do
        [[ "${existing}" != "${rank}" ]] \
          || die "perf-batch resolves candidate rank ${rank} more than once"
      done
    fi
    resolved_ranks+=("${rank}")
    resolved_ids+=("${submission_id}")
    resolved_refs+=("${source_ref}")
    resolved_count=$((resolved_count + 1))
  done

  echo "top15-study: bounded performance batch: baseline rank-${study_baseline_rank}, then candidates ${resolved_ranks[*]}"
  start_performance_batch_caffeinate
  [[ "${study_performance_enabled}" == "true" ]] \
    || die "performance is disabled by manifest: ${study_manifest}"
  require_inputs
  wait_for_performance_batch_cool
  # A single process owns the whole thermal handoff. Only the first new arm
  # must already be <=40C at preflight; later preflights may be healthy-hot and
  # the benchmark's phase-boundary gate performs the actual cool-down.
  study_next_preflight_requires_cool=1
  prepare_workspace
  run_performance_arm \
    "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"
  local index
  for index in "${!resolved_ranks[@]}"; do
    run_performance_arm \
      "${resolved_ranks[${index}]}" \
      "${resolved_ids[${index}]}" \
      "${resolved_refs[${index}]}"
  done
  echo "top15-study: bounded performance batch complete"
}

# A detached batch may be launched while the host is still cooling from setup
# or tests. Wait here, before applying a snapshot or loading the model, using
# the same responsive persistent reader contract as the attempt receipt. A bad
# reader fails immediately; only healthy-hot telemetry is allowed to wait.
wait_for_performance_batch_cool() {
  local wait_root started_at finished_at samples_file stderr_file reader_status
  local final_gpu_temp now deadline iteration=0 fan_status
  wait_root="$(mktemp -d "${study_results}/preflight-wait-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")" \
    || die "could not create detached batch cool-wait evidence directory"
  now="$(date +%s)"
  deadline=$((now + 900))
  while :; do
    iteration=$((iteration + 1))
    samples_file="${wait_root}/samples-${iteration}.jsonl"
    stderr_file="${wait_root}/macmon-${iteration}.stderr"
    fan_status="$(performance_fan_status)" \
      || { echo "top15-study: detached cool wait lost automatic fan policy; evidence: ${wait_root}" >&2; return 75; }
    started_at="$(utc_now)"
    if run_bounded_capture \
        "${samples_file}" "${stderr_file}" "${study_thermal_reader_timeout_seconds}" \
        /usr/bin/env -i \
          HOME="${HOME}" \
          LOGNAME="${LOGNAME:-${USER:-}}" \
          PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:${HOME}/bin" \
          TMPDIR="${TMPDIR:-/tmp}" \
          USER="${USER:-}" \
          "${study_macmon_source}" pipe \
            --samples "${study_thermal_preflight_samples}" \
            --interval "${study_thermal_preflight_interval_ms}"; then
      reader_status=0
    else
      reader_status="$?"
    fi
    finished_at="$(utc_now)"
    case "${reader_status}" in
      125|129|130|131|143) return "${reader_status}" ;;
    esac
    if [[ "${reader_status}" -ne 0 ]] \
        || ! thermal_samples_healthy "${samples_file}" \
        || ! thermal_samples_fresh "${samples_file}" "${started_at}" "${finished_at}"; then
      echo "top15-study: detached cool wait rejected unhealthy, frozen, or stale telemetry; evidence: ${wait_root}" >&2
      return 75
    fi
    final_gpu_temp="$(jq -sr '.[-1].temp.gpu_temp_avg' "${samples_file}")"
    if thermal_samples_ready "${samples_file}"; then
      echo "top15-study: detached cool wait complete at ${final_gpu_temp}C after ${iteration} responsive stream(s); evidence: ${wait_root}"
      return 0
    fi
    now="$(date +%s)"
    if [[ "${now}" -ge "${deadline}" ]]; then
      echo "top15-study: detached cool wait timed out after 900s at ${final_gpu_temp}C; no model was loaded; evidence: ${wait_root}" >&2
      return 75
    fi
    echo "top15-study: waiting to launch model; healthy GPU telemetry is ${final_gpu_temp}C (target <=40C, fans ${fan_status})"
    /bin/sleep 10
  done
}

start_performance_batch_caffeinate() {
  [[ -x /usr/bin/caffeinate ]] \
    || die "perf-batch requires /usr/bin/caffeinate so idle sleep cannot suspend a detached timing campaign"
  /usr/bin/caffeinate -is -w "$$" >/dev/null 2>&1 &
  local caffeinate_pid="$!"
  /bin/sleep 0.1
  if ! kill -0 "${caffeinate_pid}" 2>/dev/null; then
    wait "${caffeinate_pid}" 2>/dev/null || true
    die "perf-batch could not establish its idle/system-sleep assertion"
  fi
  echo "top15-study: sleep prevention active via caffeinate pid ${caffeinate_pid} (display sleep remains allowed)"
}

performance_batch_self_test() {
  local test_dir sequence_file actual expected
  test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-top15-batch-test.XXXXXX")"
  sequence_file="${test_dir}/sequence"
  (
    require_inputs() { :; }
    prepare_workspace() { :; }
    start_performance_batch_caffeinate() { :; }
    wait_for_performance_batch_cool() { :; }
    run_performance_arm() {
      printf '%s:%s\n' "$1" "${study_next_preflight_requires_cool}" >> "${sequence_file}"
      study_next_preflight_requires_cool=0
    }
    run_performance_batch 112 120 >/dev/null
  ) || { rm -f "${sequence_file}"; rmdir "${test_dir}"; die "bounded performance batch failed its model-free sequence"; }
  actual="$(cat "${sequence_file}")"
  expected=$'111:1\n112:0\n120:0'
  [[ "${actual}" == "${expected}" ]] \
    || { rm -f "${sequence_file}"; rmdir "${test_dir}"; die "bounded performance batch lost its baseline/order/hot-handoff contract"; }
  if (run_performance_batch 112 aa6660cb >/dev/null 2>&1); then
    rm -f "${sequence_file}"
    rmdir "${test_dir}"
    die "bounded performance batch accepted one candidate twice"
  fi
  if (run_performance_batch 112 120 125 126 >/dev/null 2>&1); then
    rm -f "${sequence_file}"
    rmdir "${test_dir}"
    die "bounded performance batch accepted more than three candidates"
  fi
  rm -f "${sequence_file}"
  rmdir "${test_dir}"
  echo "top15-study: bounded performance batch self-test passed"
}

quality_bridge_binary() {
  local first="${study_workspace}/.build-quality/release/laguna-quality-bridge"
  local second="${study_workspace}/.build-quality/arm64-apple-macosx/release/laguna-quality-bridge"
  if [[ -x "${first}" ]]; then
    echo "${first}"
  elif [[ -x "${second}" ]]; then
    echo "${second}"
  else
    return 1
  fi
}

build_quality_bridge() {
  if ! (
    cd "${study_workspace}"
    env \
      PYTHONPATH="${study_workspace}/senpai/quality_eval" \
      UV_CACHE_DIR="${study_workspace}/senpai/quality_eval/.uv-cache" \
      uv run --project "${study_workspace}/senpai/quality_eval" --locked \
        python -c 'from laguna_quality.artifact import build_bridge; build_bridge(".")'
  ); then
    die "quality bridge build failed for the applied snapshot"
  fi
  quality_bridge_binary >/dev/null \
    || die "quality bridge build completed without an executable"
  local built_bridge
  built_bridge="$(quality_bridge_binary)" \
    || die "failed to resolve the freshly built quality bridge"
  [[ -s "${built_bridge}.source.sha256" ]] \
    || die "freshly built quality bridge lacks its source fingerprint"
}

quality_attempt_valid() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local attempt_dir="${arm_dir}/${attempt_name}"
  local meta_file="${arm_dir}/${attempt_name}.meta.json"
  local preserved_bridge="${arm_dir}/candidate-bridge"
  arm_spec_matches "${arm_dir}" quality "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ -f "${attempt_dir}/run.json" && -f "${attempt_dir}/summary.json" \
      && -f "${attempt_dir}/comparison.json" && -f "${meta_file}" \
      && -x "${preserved_bridge}" && -f "${preserved_bridge}.source.sha256" ]] || return 1
  jq -e \
    --arg evaluator "${study_evaluator_sha256}" \
    --arg hardware_model "$(jq -r '.host.model' "${study_manifest}")" \
    --arg cpu_brand "$(jq -r '.host.chip' "${study_manifest}")" \
    --arg harness_ref "${study_harness_commit}" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" \
    --arg real_bridge_sha256 "$(sha256_file "${preserved_bridge}")" \
    --arg label "${study_change_label_prefix}-${arm_rank}-${arm_id}" \
    --arg submission_id "${arm_id}" \
    --arg source_ref "${arm_commit}" '
      .status == "completed"
      and .evaluation_valid == true
      and .profile == "quick"
      and .passes == 1
      and ((.suites | sort) == (["ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"] | sort))
      and .evaluator_provenance.sha256 == $evaluator
      and .host_identity.hardware_model == $hardware_model
      and .host_identity.cpu_brand == $cpu_brand
      and .artifact_identity.checkout.git_head == $harness_ref
      and (.artifact_identity.checkout.editable_source_sha256 | type) == "string"
      and .artifact_identity.files.bridge.sha256 == $wrapper_sha256
      and .change_label == $label
      and .weave.attributes.submission_id == $submission_id
      and .weave.attributes.promoted_commit == $source_ref
      and .weave.attributes.host_compatibility == "DARKBLOOM_EXPERT_ALIGNED_GATHER=0"
      and .weave.attributes.real_quality_bridge_sha256 == $real_bridge_sha256
    ' "${attempt_dir}/run.json" >/dev/null || return 1
  jq -e '
    .compatibility.validated == true
    and (.decision.local_retention_gate_passed | type) == "boolean"
  ' "${attempt_dir}/comparison.json" >/dev/null || return 1
  jq -e \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg evaluator_sha256 "${study_evaluator_sha256}" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" '
      (.exit_code == 0 or .exit_code == 3)
      and .source_ref == $source_ref
      and .harness_ref == $harness_ref
      and .manifest_sha256 == $manifest_sha256
      and .evaluator_sha256 == $evaluator_sha256
      and .wrapper_sha256 == $wrapper_sha256
      and .environment.DARKBLOOM_EXPERT_ALIGNED_GATHER == "0"
    ' "${meta_file}" >/dev/null || return 1
  [[ "$(jq -r '.real_bridge_sha256' "${meta_file}")" == "$(sha256_file "${preserved_bridge}")" ]] \
    || return 1
  [[ "$(jq -r '.real_bridge_source_sha256' "${meta_file}")" == "$(tr -d '[:space:]' < "${preserved_bridge}.source.sha256")" ]] \
    || return 1
}

quality_attempt_noncompletion_evidence_valid() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local attempt_dir="${arm_dir}/${attempt_name}"
  local pass_dir="${attempt_dir}/pass_1"
  local meta_file="${arm_dir}/${attempt_name}.meta.json"
  local log_file="${arm_dir}/${attempt_name}.log"
  local preserved_bridge="${arm_dir}/candidate-bridge"
  local run_file="${attempt_dir}/run.json"
  local ppl_results="${pass_dir}/ppl_results.jsonl"
  local ppl_summary="${pass_dir}/ppl_summary.json"
  local mmlu_file="${pass_dir}/mmlu_pro_greedy.json"
  local gpqa_greedy_file="${pass_dir}/gpqa_diamond_greedy.json"
  local gpqa_sampled_file="${pass_dir}/gpqa_diamond_sampled_s0.json"
  local aime_file="${pass_dir}/aime_greedy.json"
  local gsm_file="${pass_dir}/candidate_gsm8k_greedy.json"
  local ranked_file="${pass_dir}/gpqa_diamond_ranked_greedy.json"

  arm_spec_matches "${arm_dir}" quality "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ -f "${run_file}" && -f "${meta_file}" && -f "${log_file}" \
      && -f "${attempt_dir}/responses.jsonl" && -f "${ppl_results}" \
      && -f "${ppl_summary}" && -f "${mmlu_file}" \
      && -f "${gpqa_greedy_file}" && -f "${gpqa_sampled_file}" \
      && -f "${aime_file}" && -f "${gsm_file}" && -f "${ranked_file}" \
      && -x "${preserved_bridge}" && -f "${preserved_bridge}.source.sha256" ]] \
    || return 1

  jq -e \
    --arg evaluator "${study_evaluator_sha256}" \
    --arg hardware_model "$(jq -r '.host.model' "${study_manifest}")" \
    --arg cpu_brand "$(jq -r '.host.chip' "${study_manifest}")" \
    --arg harness_ref "${study_harness_commit}" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" \
    --arg real_bridge_sha256 "$(sha256_file "${preserved_bridge}")" \
    --arg label "${study_change_label_prefix}-${arm_rank}-${arm_id}" \
    --arg submission_id "${arm_id}" \
    --arg source_ref "${arm_commit}" '
      .status == "failed"
      and .evaluation_valid == false
      and .profile == "quick"
      and .passes == 1
      and ((.suites | sort) == (["ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k"] | sort))
      and (.error | type) == "string"
      and (.error | endswith("/pass_1/aime_greedy.json: quality answer was truncated before completion"))
      and (.commands | length) == 7
      and ([.commands[].name] | sort) == ([
        "ppl", "mmlu_pro_greedy", "gpqa_diamond_greedy",
        "gpqa_diamond_sampled_s0", "aime_greedy", "gsm8k_greedy",
        "gpqa_diamond_ranked_greedy"
      ] | sort)
      and all(.commands[]; .exit_code == 0 and .status == "passed")
      and .evaluator_provenance.sha256 == $evaluator
      and .host_identity.hardware_model == $hardware_model
      and .host_identity.cpu_brand == $cpu_brand
      and .artifact_identity.checkout.git_head == $harness_ref
      and (.artifact_identity.checkout.editable_source_sha256 | type) == "string"
      and .artifact_identity.files.bridge.sha256 == $wrapper_sha256
      and .change_label == $label
      and .weave.attributes.submission_id == $submission_id
      and .weave.attributes.promoted_commit == $source_ref
      and .weave.attributes.host_compatibility == "DARKBLOOM_EXPERT_ALIGNED_GATHER=0"
      and .weave.attributes.real_quality_bridge_sha256 == $real_bridge_sha256
      and .local_public_correctness_probe.available == true
      and .local_public_correctness_probe.matches_m5_fixture == true
      and .local_public_correctness_probe.actual_token == .local_public_correctness_probe.expected_token
    ' "${run_file}" >/dev/null || return 1

  jq -e \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg evaluator_sha256 "${study_evaluator_sha256}" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" '
      .exit_code == 2
      and .source_ref == $source_ref
      and .harness_ref == $harness_ref
      and .manifest_sha256 == $manifest_sha256
      and .evaluator_sha256 == $evaluator_sha256
      and .wrapper_sha256 == $wrapper_sha256
      and .environment.DARKBLOOM_EXPERT_ALIGNED_GATHER == "0"
    ' "${meta_file}" >/dev/null || return 1
  [[ "$(jq -r '.real_bridge_sha256' "${meta_file}")" == "$(sha256_file "${preserved_bridge}")" ]] \
    || return 1
  [[ "$(jq -r '.real_bridge_source_sha256' "${meta_file}")" == "$(tr -d '[:space:]' < "${preserved_bridge}.source.sha256")" ]] \
    || return 1

  jq -e '
    .num_records == 8
    and .num_tokens == 256
    and .prompt_logprobs == 1
    and (.ppl | numbers) > 0
  ' "${ppl_summary}" >/dev/null || return 1
  [[ "$(wc -l < "${ppl_results}" | tr -d '[:space:]')" == "8" ]] || return 1
  jq -s -e 'length == 8 and all(.[]; ((.error? // null) == null))' \
    "${ppl_results}" >/dev/null || return 1

  jq -e '
    .n_samples == 20
    and .n_expected == 20
    and .n_scored == 20
    and .n_error == 0
    and .n_length_truncated == 0
    and .incomplete == false
    and (.per_sample | length) == 20
    and all(.per_sample[]; .error == null and .length_truncated == false and .stop_reason == "stop")
  ' "${mmlu_file}" >/dev/null || return 1
  local gpqa_file
  for gpqa_file in "${gpqa_greedy_file}" "${gpqa_sampled_file}"; do
    jq -e '
      .n_samples == 9
      and .n_expected == 9
      and .n_scored == 9
      and .n_error == 0
      and .n_length_truncated == 0
      and .incomplete == false
      and (.per_sample | length) == 9
      and all(.per_sample[]; .error == null and .length_truncated == false and .stop_reason == "stop")
    ' "${gpqa_file}" >/dev/null || return 1
  done

  jq -e '
    .n_problems == 9
    and .total_samples == 9
    and (.per_problem | length) == 9
    and ([.per_problem[].id] | unique | length) == 9
    and ([.per_problem[].finish_reasons[]] | length) == 9
    and ([.per_problem[].finish_reasons[] | select(. == "length")] | length) > 0
    and all(.per_problem[];
      (.finish_reasons | length) == 1
      and (.sample_chars | length) == 1
      and (.texts | length) == 1
      and (.answers | length) == 1
      and all(.finish_reasons[]; . == "stop" or . == "length")
    )
  ' "${aime_file}" >/dev/null || return 1
  jq -e '
    .n_problems == 6
    and .n_requested == 6
    and .n_error == 0
    and .truncation_rate == 0
    and (.per_problem | length) == 6
    and all(.per_problem[]; .finish_reason == "stop")
  ' "${gsm_file}" >/dev/null || return 1
  jq -e '
    .n_samples == 9
    and .n_expected == 9
    and .n_scored == 9
    and .n_error == 0
    and .incomplete == false
    and (.per_sample | length) == 9
    and all(.per_sample[];
      .error == null
      and (.stop_reason == "stop" or .stop_reason == "max_tokens")
    )
  ' "${ranked_file}" >/dev/null || return 1
  [[ "$(wc -l < "${attempt_dir}/responses.jsonl" | tr -d '[:space:]')" == "70" ]] \
    || return 1
  jq -s -e 'length == 70 and all(.[]; ((.error? // null) == null))' \
    "${attempt_dir}/responses.jsonl" >/dev/null || return 1
}

quality_noncompletion_marker_json() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local attempt_dir="${arm_dir}/${attempt_name}"
  local pass_dir="${attempt_dir}/pass_1"
  local meta_file="${arm_dir}/${attempt_name}.meta.json"
  local log_file="${arm_dir}/${attempt_name}.log"
  local preserved_bridge="${arm_dir}/candidate-bridge"
  local run_file="${attempt_dir}/run.json"
  local ppl_results="${pass_dir}/ppl_results.jsonl"
  local ppl_summary="${pass_dir}/ppl_summary.json"
  local mmlu_file="${pass_dir}/mmlu_pro_greedy.json"
  local gpqa_greedy_file="${pass_dir}/gpqa_diamond_greedy.json"
  local gpqa_sampled_file="${pass_dir}/gpqa_diamond_sampled_s0.json"
  local aime_file="${pass_dir}/aime_greedy.json"
  local gsm_file="${pass_dir}/candidate_gsm8k_greedy.json"
  local ranked_file="${pass_dir}/gpqa_diamond_ranked_greedy.json"

  jq -S -n \
    --arg study "${study_id}" \
    --argjson rank "${arm_rank}" \
    --arg submission_id "${arm_id}" \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg evaluator_sha256 "${study_evaluator_sha256}" \
    --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" \
    --arg attempt "${attempt_name}" \
    --arg finished_at "$(jq -r '.finished_at' "${meta_file}")" \
    --arg run_spec_sha256 "$(sha256_file "${arm_dir}/run-spec.json")" \
    --arg run_sha256 "$(sha256_file "${run_file}")" \
    --arg meta_sha256 "$(sha256_file "${meta_file}")" \
    --arg log_sha256 "$(sha256_file "${log_file}")" \
    --arg responses_sha256 "$(sha256_file "${attempt_dir}/responses.jsonl")" \
    --arg ppl_results_sha256 "$(sha256_file "${ppl_results}")" \
    --arg ppl_summary_sha256 "$(sha256_file "${ppl_summary}")" \
    --arg mmlu_sha256 "$(sha256_file "${mmlu_file}")" \
    --arg gpqa_greedy_sha256 "$(sha256_file "${gpqa_greedy_file}")" \
    --arg gpqa_sampled_sha256 "$(sha256_file "${gpqa_sampled_file}")" \
    --arg aime_sha256 "$(sha256_file "${aime_file}")" \
    --arg gsm_sha256 "$(sha256_file "${gsm_file}")" \
    --arg ranked_sha256 "$(sha256_file "${ranked_file}")" \
    --arg real_bridge_sha256 "$(sha256_file "${preserved_bridge}")" \
    --arg real_bridge_sidecar_sha256 "$(sha256_file "${preserved_bridge}.source.sha256")" \
    --arg real_bridge_source_sha256 "$(tr -d '[:space:]' < "${preserved_bridge}.source.sha256")" \
    --slurpfile run "${run_file}" \
    --slurpfile ppl "${ppl_summary}" \
    --slurpfile mmlu "${mmlu_file}" \
    --slurpfile gpqa_greedy "${gpqa_greedy_file}" \
    --slurpfile gpqa_sampled "${gpqa_sampled_file}" \
    --slurpfile aime "${aime_file}" \
    --slurpfile gsm "${gsm_file}" \
    --slurpfile ranked "${ranked_file}" '
      {
        schema:"mlxfast-top15-quality-terminal-v1",
        status:"bounded_noncompletion",
        reason:"aime_length",
        study:$study,
        arm:{rank:$rank, submission_id:$submission_id, source_ref:$source_ref},
        harness_ref:$harness_ref,
        manifest_sha256:$manifest_sha256,
        evaluator_sha256:$evaluator_sha256,
        wrapper_sha256:$wrapper_sha256,
        attempt:$attempt,
        finished_at:$finished_at,
        interpretation:{
          formally_comparable:false,
          local_retention_gate_evaluated:false,
          detail:"All quick-profile jobs returned complete artifacts, but at least one AIME answer reached the fixed 2048-token ceiling. Raw scores are retained as diagnostics only."
        },
        truncated_items:[
          $aime[0].per_problem[]
          | select(any(.finish_reasons[]; . == "length"))
          | {id, finish_reasons, sample_chars, answers}
        ],
        raw_quality:{
          validation_status:"unvalidated_due_aime_length",
          overall:{
            correct:($mmlu[0].n_correct + $gpqa_greedy[0].n_correct + $gpqa_sampled[0].n_correct + $aime[0].n_correct_maj + $gsm[0].n_correct),
            total:53
          },
          mmlu_pro:{correct:$mmlu[0].n_correct, total:$mmlu[0].n_samples},
          gpqa_greedy:{correct:$gpqa_greedy[0].n_correct, total:$gpqa_greedy[0].n_samples},
          gpqa_sampled:{correct:$gpqa_sampled[0].n_correct, total:$gpqa_sampled[0].n_samples},
          aime:{correct:$aime[0].n_correct_maj, total:$aime[0].n_problems},
          gsm8k:{correct:$gsm[0].n_correct, total:$gsm[0].n_problems},
          ppl:{value:$ppl[0].ppl, records:$ppl[0].num_records, tokens:$ppl[0].num_tokens},
          ranked_gpqa:{
            raw_task_correct:$ranked[0].n_correct,
            total:$ranked[0].n_samples,
            formal_prefix_comparison:false
          }
        },
        public_probe:$run[0].local_public_correctness_probe,
        command_contract:($run[0].commands | map({name, exit_code, status, head_mode})),
        artifacts:{
          run_spec:{path:"run-spec.json", sha256:$run_spec_sha256},
          run:{path:($attempt + "/run.json"), sha256:$run_sha256},
          meta:{path:($attempt + ".meta.json"), sha256:$meta_sha256},
          log:{path:($attempt + ".log"), sha256:$log_sha256},
          responses:{path:($attempt + "/responses.jsonl"), sha256:$responses_sha256, records:70},
          raw:{
            ppl_results:{path:($attempt + "/pass_1/ppl_results.jsonl"), sha256:$ppl_results_sha256, records:8},
            ppl_summary:{path:($attempt + "/pass_1/ppl_summary.json"), sha256:$ppl_summary_sha256},
            mmlu_pro:{path:($attempt + "/pass_1/mmlu_pro_greedy.json"), sha256:$mmlu_sha256},
            gpqa_greedy:{path:($attempt + "/pass_1/gpqa_diamond_greedy.json"), sha256:$gpqa_greedy_sha256},
            gpqa_sampled:{path:($attempt + "/pass_1/gpqa_diamond_sampled_s0.json"), sha256:$gpqa_sampled_sha256},
            aime:{path:($attempt + "/pass_1/aime_greedy.json"), sha256:$aime_sha256},
            gsm8k:{path:($attempt + "/pass_1/candidate_gsm8k_greedy.json"), sha256:$gsm_sha256},
            ranked_gpqa:{path:($attempt + "/pass_1/gpqa_diamond_ranked_greedy.json"), sha256:$ranked_sha256}
          },
          real_bridge:{
            path:"candidate-bridge",
            sha256:$real_bridge_sha256,
            source_sidecar_sha256:$real_bridge_sidecar_sha256,
            source_sha256:$real_bridge_source_sha256
          }
        }
      }
    '
}

quality_noncompletion_result_valid() {
  local arm_dir="$1"
  local arm_rank="$2"
  local arm_id="$3"
  local arm_commit="$4"
  local marker_file="${arm_dir}/terminal-noncompletion.json"
  [[ -f "${marker_file}" ]] || return 1
  local attempt_name
  attempt_name="$(jq -r '.attempt // empty' "${marker_file}")"
  [[ "${attempt_name}" =~ ^attempt-[1-9][0-9]*$ ]] || return 1
  quality_attempt_noncompletion_evidence_valid \
    "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ "$(jq -S . "${marker_file}")" == "$(quality_noncompletion_marker_json \
    "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}")" ]]
}

write_quality_noncompletion_marker() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  quality_attempt_noncompletion_evidence_valid \
    "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  local marker_file="${arm_dir}/terminal-noncompletion.json"
  local temporary_marker="${arm_dir}/.terminal-noncompletion.$$.json"
  quality_noncompletion_marker_json \
    "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    > "${temporary_marker}" || return 1
  mv "${temporary_marker}" "${marker_file}" || return 1
  quality_noncompletion_result_valid "${arm_dir}" "${arm_rank}" "${arm_id}" "${arm_commit}"
}

run_quality_arm() {
  local arm_rank="$1"
  local arm_id="$2"
  local arm_commit="$3"
  local arm_dir="${study_results}/quality/${arm_rank}-${arm_id}"
  mkdir -p "${arm_dir}"
  ensure_arm_spec "${arm_dir}" quality "${arm_rank}" "${arm_id}" "${arm_commit}"
  local prior_attempt prior_name
  for prior_attempt in "${arm_dir}"/attempt-*; do
    [[ -d "${prior_attempt}" ]] || continue
    prior_name="$(basename "${prior_attempt}")"
    if quality_attempt_valid "${arm_dir}" "${prior_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
      printf '%s\n' "${prior_name}" > "${arm_dir}/selected-attempt.txt"
      echo "top15-study: quality already complete for ${arm_rank}-${arm_id}"
      return 0
    fi
  done
  if [[ -f "${arm_dir}/terminal-noncompletion.json" ]]; then
    quality_noncompletion_result_valid "${arm_dir}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
      || die "invalid bounded-noncompletion marker for ${arm_rank}-${arm_id}"
    echo "top15-study: quality already processed as bounded non-completion for ${arm_rank}-${arm_id}"
    return 0
  fi
  for prior_attempt in "${arm_dir}"/attempt-*; do
    [[ -d "${prior_attempt}" ]] || continue
    prior_name="$(basename "${prior_attempt}")"
    if write_quality_noncompletion_marker \
        "${arm_dir}" "${prior_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
      echo "top15-study: quality processed as bounded non-completion for ${arm_rank}-${arm_id} (${prior_name})"
      return 0
    fi
  done
  apply_snapshot "${arm_commit}" "${arm_rank}-${arm_id}"
  build_quality_bridge
  local real_bridge
  real_bridge="$(quality_bridge_binary)" \
    || die "failed to resolve the candidate quality bridge"
  local real_bridge_sidecar="${real_bridge}.source.sha256"
  [[ -f "${real_bridge_sidecar}" ]] || die "quality bridge source sidecar is missing"
  local preserved_bridge="${arm_dir}/candidate-bridge"
  install -m 755 "${real_bridge}" "${preserved_bridge}" \
    || die "failed to preserve the candidate quality bridge"
  cp "${real_bridge_sidecar}" "${preserved_bridge}.source.sha256" \
    || die "failed to preserve the candidate bridge source fingerprint"
  local real_bridge_sha256
  real_bridge_sha256="$(sha256_file "${preserved_bridge}")"
  local real_bridge_source_sha256
  real_bridge_source_sha256="$(tr -d '[:space:]' < "${preserved_bridge}.source.sha256")"
  local first_attempt
  first_attempt="$(next_attempt_number "${arm_dir}" log)"
  local attempt_number
  for ((attempt_number=first_attempt; attempt_number < first_attempt + study_quality_retries; attempt_number++)); do
    local attempt_name="attempt-${attempt_number}"
    local attempt_dir="${arm_dir}/${attempt_name}"
    local attempt_log="${arm_dir}/${attempt_name}.log"
    local attempt_meta="${arm_dir}/${attempt_name}.meta.json"
    local quality_status
    set +e
    (
      cd "${study_workspace}"
      env MLXFAST_TOP15_REAL_QUALITY_BRIDGE="${preserved_bridge}" \
        ./senpai/quality-eval run . \
          --profile quick \
          --weights "${study_weights}" \
          --tokenizer "${study_reference}" \
          --bridge "${study_quality_wrapper}" \
          --change-label "${study_change_label_prefix}-${arm_rank}-${arm_id}" \
          --attribute "submission_id=${arm_id}" \
          --attribute "promoted_commit=${arm_commit}" \
          --attribute "host_compatibility=DARKBLOOM_EXPERT_ALIGNED_GATHER=0" \
          --attribute "real_quality_bridge_sha256=${real_bridge_sha256}" \
          --baseline "${study_quality_baseline}" \
          --output "${attempt_dir}" \
          --keep-going
    ) 2>&1 | tee "${attempt_log}"
    quality_status="${PIPESTATUS[0]}"
    set -e
    jq -n \
      --argjson exit_code "${quality_status}" \
      --arg finished_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg source_ref "${arm_commit}" \
      --arg harness_ref "${study_harness_commit}" \
      --arg manifest_sha256 "${study_manifest_sha256}" \
      --arg evaluator_sha256 "${study_evaluator_sha256}" \
      --arg wrapper_sha256 "$(sha256_file "${study_quality_wrapper_source}")" \
      --arg real_bridge_sha256 "${real_bridge_sha256}" \
      --arg real_bridge_source_sha256 "${real_bridge_source_sha256}" '
        {
          exit_code:$exit_code,
          finished_at:$finished_at,
          source_ref:$source_ref,
          harness_ref:$harness_ref,
          manifest_sha256:$manifest_sha256,
          evaluator_sha256:$evaluator_sha256,
          wrapper_sha256:$wrapper_sha256,
          real_bridge_sha256:$real_bridge_sha256,
          real_bridge_source_sha256:$real_bridge_source_sha256,
          environment:{DARKBLOOM_EXPERT_ALIGNED_GATHER:"0"}
        }
      ' > "${attempt_meta}"
    [[ "${quality_status}" -ne 130 ]] || return 130
    if quality_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
      printf '%s\n' "${attempt_name}" > "${arm_dir}/selected-attempt.txt"
      echo "top15-study: quality complete for ${arm_rank}-${arm_id} (exit ${quality_status})"
      return 0
    fi
    if write_quality_noncompletion_marker \
        "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
      echo "top15-study: quality processed as bounded non-completion for ${arm_rank}-${arm_id} (${attempt_name})"
      return 0
    fi
    echo "top15-study: invalid quality attempt ${attempt_number} for ${arm_rank}-${arm_id}; retrying" >&2
  done
  echo "top15-study: quality exhausted retries for ${arm_rank}-${arm_id}" >&2
  return 1
}

run_quality() {
  local candidate_selector="${1:-all}"
  prepare_workspace
  local selected_count=0
  local failure_count=0
  local candidate_rank candidate_id candidate_commit arm_status
  while IFS=$'\t' read -r candidate_rank candidate_id candidate_commit; do
    [[ -n "${candidate_rank}" ]] || continue
    selected_count="$((selected_count + 1))"
    if run_quality_arm "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
      :
    else
      arm_status="$?"
      [[ "${arm_status}" -ne 130 ]] || return 130
      failure_count="$((failure_count + 1))"
    fi
  done < <(candidate_rows "${candidate_selector}")
  [[ "${selected_count}" -gt 0 ]] || die "no candidate matched ${candidate_selector}"
  [[ "${failure_count}" -eq 0 ]] \
    || die "${failure_count} quality arm(s) failed; valid arms were retained"
}

show_status() {
  require_inputs
  local performance_complete=0
  local performance_current_contract=0
  local performance_invalid=0
  local quality_valid=0
  local quality_bounded=0
  local candidate_total
  candidate_total="$(jq -r '.candidates | length' "${study_manifest}")"
  local candidate_rank candidate_id candidate_commit
  if [[ "${study_performance_enabled}" == "true" ]]; then
    local baseline_dir="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}"
    if performance_result_valid "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"; then
      performance_complete="$((performance_complete + 1))"
      if performance_result_current_contract "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"; then
        performance_current_contract="$((performance_current_contract + 1))"
      fi
    elif [[ -f "${baseline_dir}/selected-attempt.txt" ]]; then
      performance_invalid="$((performance_invalid + 1))"
    fi
  fi
  while IFS=$'\t' read -r candidate_rank candidate_id candidate_commit; do
    if [[ "${study_performance_enabled}" == "true" ]]; then
      local performance_dir="${study_results}/performance/${candidate_rank}-${candidate_id}"
      if performance_result_valid "${performance_dir}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
        performance_complete="$((performance_complete + 1))"
        if performance_result_current_contract "${performance_dir}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
          performance_current_contract="$((performance_current_contract + 1))"
        fi
      elif [[ -f "${performance_dir}/selected-attempt.txt" ]]; then
        performance_invalid="$((performance_invalid + 1))"
      fi
    fi
    local quality_dir="${study_results}/quality/${candidate_rank}-${candidate_id}"
    local selected_file="${quality_dir}/selected-attempt.txt"
    if [[ -f "${selected_file}" ]]; then
      local selected_name
      selected_name="$(tr -d '[:space:]' < "${selected_file}")"
      if quality_attempt_valid "${quality_dir}" "${selected_name}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
        quality_valid="$((quality_valid + 1))"
      fi
    elif quality_noncompletion_result_valid "${quality_dir}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
      quality_bounded="$((quality_bounded + 1))"
    fi
  done < <(candidate_rows all)
  echo "workspace: ${study_workspace}"
  echo "results: ${study_results}"
  if [[ "${study_performance_enabled}" == "true" ]]; then
    echo "performance: ${performance_complete}/$((candidate_total + 1)) valid, ${performance_invalid} invalid selected, $((candidate_total + 1 - performance_complete - performance_invalid)) pending (rank-${study_baseline_rank} local comparator + ${candidate_total} candidates)"
    echo "performance current contract: ${performance_current_contract}/$((candidate_total + 1)) auto-fan/env-i/strict-telemetry receipts (fresh rank-${study_baseline_rank} required before candidates)"
  else
    echo "performance: disabled by manifest"
  fi
  echo "quality: $((quality_valid + quality_bounded))/${candidate_total} processed (${quality_valid} valid comparisons, ${quality_bounded} bounded non-completions)"
}

usage() {
  cat <<'EOF'
Usage:
  run-study.sh prepare
  run-study.sh thermal-preflight
  run-study.sh perf [all|baseline|RANK|SUBMISSION_PREFIX]
  run-study.sh perf-batch CANDIDATE [CANDIDATE ...]  # one to three
  run-study.sh quality [all|RANK|SUBMISSION_PREFIX]
  run-study.sh status
  run-study.sh self-test

The runner is resumable and skips valid completed artifacts. Performance uses
--local-submit by default; set MLXFAST_TOP15_PERF_MODE=--local-iterate only for
a deliberately weaker screen. The performance baseline is promoted rank 111,
the exact parent of rank 112. A fresh rank-111 auto-fan/current-contract receipt
is mandatory before any candidate. `thermal-preflight` loads no model; it
requires five responsive macmon samples, a <=40C final sample, and automatic
fan control. `perf-batch` owns one bounded baseline/candidate sequence and
stops on the first failed arm. Do not set MLXFAST_TOP15_ALLOW_GOLDEN_DRIFT=1
until that unchanged comparator demonstrates a reproducible M4-only drift.
EOF
}

main() {
  local command_name="${1:-status}"
  local command_selector="${2:-all}"
  case "${command_name}" in
    prepare) prepare_workspace ;;
    thermal-preflight) run_thermal_preflight 1 ;;
    perf) run_performance "${command_selector}" ;;
    perf-batch)
      shift
      run_performance_batch "$@"
      ;;
    quality) run_quality "${command_selector}" ;;
    status) show_status ;;
    self-test) run_self_tests ;;
    -h|--help|help) usage ;;
    *) usage >&2; die "unknown command: ${command_name}" ;;
  esac
}

main "$@"
