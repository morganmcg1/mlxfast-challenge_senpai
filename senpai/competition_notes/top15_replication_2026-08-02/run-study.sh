#!/usr/bin/env bash
set -euo pipefail

study_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
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

die() {
  echo "top15-study: $*" >&2
  exit 1
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
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
  done < <(jq -r '.candidates[].source_ref' "${study_manifest}")
  if [[ "${study_performance_enabled}" == "true" ]]; then
    [[ -n "${study_baseline_commit}" && -n "${study_baseline_rank}" && -n "${study_baseline_id}" ]] \
      || die "performance-enabled manifest requires a complete baseline"
    git -C "${study_repo}" cat-file -e "${study_baseline_commit}^{commit}" \
      || die "manifest performance baseline commit is unavailable: ${study_baseline_commit}"
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
  jq -n \
    --arg label "${snapshot_label}" \
    --arg source_ref "${snapshot_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg applied_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{label:$label, source_ref:$source_ref, harness_ref:$harness_ref, applied_at:$applied_at}' \
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

performance_attempt_valid() {
  local arm_dir="$1"
  local attempt_name="$2"
  local arm_rank="$3"
  local arm_id="$4"
  local arm_commit="$5"
  local score_file="${arm_dir}/${attempt_name}.score.json"
  local meta_file="${arm_dir}/${attempt_name}.meta.json"
  local integrity_file="${arm_dir}/${attempt_name}.integrity.json"
  arm_spec_matches "${arm_dir}" performance "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ -f "${score_file}" && -f "${meta_file}" && -f "${integrity_file}" ]] || return 1
  jq -e \
    --arg runtime "${study_perf_runtime}" \
    --arg allow "${study_allow_golden_drift}" '
      (.score | numbers) > 0
      and (.metrics.decode_seconds_per_token | numbers) > 0
      and (.metrics.prefill_seconds_per_token | numbers) > 0
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
    --arg expert_aligned_gather "0" \
    --arg allow_golden_drift "${study_allow_golden_drift}" '
      .exit_code == 0
      and .source_ref == $source_ref
      and .harness_ref == $harness_ref
      and .manifest_sha256 == $manifest_sha256
      and .mode == $mode
      and .runtime == $runtime
      and .environment.DARKBLOOM_EXPERT_ALIGNED_GATHER == $expert_aligned_gather
      and .environment.MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT == $allow_golden_drift
    ' "${meta_file}" >/dev/null || return 1
  jq -e 'type == "object"' "${integrity_file}" >/dev/null || return 1
  [[ "$(jq -r '.score_sha256' "${meta_file}")" == "$(sha256_file "${score_file}")" ]] || return 1
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
  performance_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}" \
    || return 1
  [[ "$(sha256_file "${arm_dir}/score.json")" == "$(sha256_file "${arm_dir}/${attempt_name}.score.json")" ]]
}

run_performance_arm() {
  local arm_rank="$1"
  local arm_id="$2"
  local arm_commit="$3"
  local arm_dir="${study_results}/performance/${arm_rank}-${arm_id}"
  mkdir -p "${arm_dir}"
  ensure_arm_spec "${arm_dir}" performance "${arm_rank}" "${arm_id}" "${arm_commit}"
  if performance_result_valid "${arm_dir}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
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
  local benchmark_status
  set +e
  (
    cd "${study_workspace}"
    env \
      DARKBLOOM_EXPERT_ALIGNED_GATHER=0 \
      MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT="${study_allow_golden_drift}" \
      MLXFAST_REFERENCE_DIR="${study_reference}" \
      MLXFAST_WEIGHTS_PATH="${study_weights}" \
      MLXFAST_SKIP_TRANSFORM=1 \
      MLXFAST_SCORE_PATH="${attempt_score}" \
      MLXFAST_INTEGRITY_PATH="${attempt_integrity}" \
      ./benchmark.sh "${study_perf_mode}"
  ) 2>&1 | tee "${attempt_log}"
  benchmark_status="${PIPESTATUS[0]}"
  set -e
  local score_sha256=""
  local integrity_sha256=""
  [[ ! -f "${attempt_score}" ]] || score_sha256="$(sha256_file "${attempt_score}")"
  [[ ! -f "${attempt_integrity}" ]] || integrity_sha256="$(sha256_file "${attempt_integrity}")"
  jq -n \
    --argjson exit_code "${benchmark_status}" \
    --arg finished_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg source_ref "${arm_commit}" \
    --arg harness_ref "${study_harness_commit}" \
    --arg manifest_sha256 "${study_manifest_sha256}" \
    --arg mode "${study_perf_mode}" \
    --arg runtime "${study_perf_runtime}" \
    --arg score_sha256 "${score_sha256}" \
    --arg integrity_sha256 "${integrity_sha256}" \
    --arg expert_aligned_gather "0" \
    --arg allow_golden_drift "${study_allow_golden_drift}" '
      {
        exit_code:$exit_code,
        finished_at:$finished_at,
        source_ref:$source_ref,
        harness_ref:$harness_ref,
        manifest_sha256:$manifest_sha256,
        mode:$mode,
        runtime:$runtime,
        score_sha256:$score_sha256,
        integrity_sha256:$integrity_sha256,
        environment:{
          DARKBLOOM_EXPERT_ALIGNED_GATHER:$expert_aligned_gather,
          MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT:$allow_golden_drift
        }
      }
    ' > "${attempt_meta}"
  if [[ "${benchmark_status}" -eq 130 ]]; then
    return 130
  fi
  if performance_attempt_valid "${arm_dir}" "${attempt_name}" "${arm_rank}" "${arm_id}" "${arm_commit}"; then
    cp "${attempt_score}" "${arm_dir}/score.json"
    printf '%s\n' "${attempt_name}" > "${arm_dir}/selected-attempt.txt"
    echo "top15-study: performance complete for ${arm_rank}-${arm_id}"
    return 0
  fi
  echo "top15-study: performance failed for ${arm_rank}-${arm_id}; see ${attempt_log}" >&2
  return 1
}

run_performance() {
  local candidate_selector="${1:-all}"
  [[ "${study_performance_enabled}" == "true" ]] \
    || die "performance is disabled by manifest: ${study_manifest}"
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
      [[ "${arm_status}" -ne 130 ]] || return 130
      failure_count="$((failure_count + 1))"
    fi
  done < <(candidate_rows "${candidate_selector}")
  [[ "${candidate_selector}" == "all" || "${selected_count}" -gt 0 ]] \
    || die "no candidate matched ${candidate_selector}"
  [[ "${failure_count}" -eq 0 ]] \
    || die "${failure_count} performance arm(s) failed; valid arms were retained"
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
  local quality_valid=0
  local quality_bounded=0
  local candidate_total
  candidate_total="$(jq -r '.candidates | length' "${study_manifest}")"
  local candidate_rank candidate_id candidate_commit
  if [[ "${study_performance_enabled}" == "true" ]]; then
    local baseline_dir="${study_results}/performance/${study_baseline_rank}-${study_baseline_id}"
    if performance_result_valid "${baseline_dir}" "${study_baseline_rank}" "${study_baseline_id}" "${study_baseline_commit}"; then
      performance_complete="$((performance_complete + 1))"
    fi
  fi
  while IFS=$'\t' read -r candidate_rank candidate_id candidate_commit; do
    if [[ "${study_performance_enabled}" == "true" ]]; then
      local performance_dir="${study_results}/performance/${candidate_rank}-${candidate_id}"
      if performance_result_valid "${performance_dir}" "${candidate_rank}" "${candidate_id}" "${candidate_commit}"; then
        performance_complete="$((performance_complete + 1))"
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
    echo "performance: ${performance_complete}/$((candidate_total + 1)) (rank-${study_baseline_rank} local comparator + ${candidate_total} candidates)"
  else
    echo "performance: disabled by manifest"
  fi
  echo "quality: $((quality_valid + quality_bounded))/${candidate_total} processed (${quality_valid} valid comparisons, ${quality_bounded} bounded non-completions)"
}

usage() {
  cat <<'EOF'
Usage:
  run-study.sh prepare
  run-study.sh perf [all|baseline|RANK|SUBMISSION_PREFIX]
  run-study.sh quality [all|RANK|SUBMISSION_PREFIX]
  run-study.sh status

The runner is resumable and skips valid completed artifacts. Performance uses
--local-submit by default; set MLXFAST_TOP15_PERF_MODE=--local-iterate only for
a deliberately weaker screen. The performance baseline is promoted rank 111,
the exact parent of rank 112. Do not set MLXFAST_TOP15_ALLOW_GOLDEN_DRIFT=1
until that unchanged comparator demonstrates a reproducible M4-only drift.
EOF
}

main() {
  local command_name="${1:-status}"
  local command_selector="${2:-all}"
  case "${command_name}" in
    prepare) prepare_workspace ;;
    perf) run_performance "${command_selector}" ;;
    quality) run_quality "${command_selector}" ;;
    status) show_status ;;
    -h|--help|help) usage ;;
    *) usage >&2; die "unknown command: ${command_name}" ;;
  esac
}

main "$@"
