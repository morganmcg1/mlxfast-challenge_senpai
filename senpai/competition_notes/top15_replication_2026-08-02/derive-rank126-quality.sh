#!/usr/bin/env bash
set -euo pipefail

derived_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
derived_repo="$(git -C "${derived_script_dir}" rev-parse --show-toplevel)"
derived_manifest="${derived_script_dir}/candidates.json"
derived_primary_results="${derived_repo}/quality-results/leaderboard-top15-20260802"
derived_workspace="${derived_repo}/quality-results/.top15-workspace-20260802"
derived_output="${MLXFAST_TOP15_RANK126_RESULTS:-${derived_repo}/quality-results/leaderboard-top15-rank126-relative-20260803}"
derived_evaluator_source_project="${derived_workspace}/senpai/quality_eval"
derived_primary_runner="${derived_script_dir}/run-study.sh"
derived_uv="${MLXFAST_TOP15_UV_BIN:-${HOME}/.local/bin/uv}"
derived_evaluator_snapshot=""
derived_records=""
derived_summary_tmp=""
derived_allowed_files=""
derived_actual_files=""
derived_checksum_files=""
derived_active_comparison_tmp=""
derived_active_log_tmp=""
derived_primary_status_tmp=""
derived_checksum_tmp=""

cleanup() {
  [[ -z "${derived_evaluator_snapshot}" ]] \
    || rm -rf "${derived_evaluator_snapshot}"
  rm -f \
    "${derived_records}" \
    "${derived_summary_tmp}" \
    "${derived_allowed_files}" \
    "${derived_actual_files}" \
    "${derived_checksum_files}" \
    "${derived_active_comparison_tmp}" \
    "${derived_active_log_tmp}" \
    "${derived_primary_status_tmp}" \
    "${derived_checksum_tmp}"
}
trap cleanup EXIT

die() {
  echo "rank126-quality: $*" >&2
  exit 1
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

real_path() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

derived_manifest_sha256="$(sha256_file "${derived_manifest}")"
derived_output_real="$(real_path "${derived_output}")"
derived_primary_real="$(real_path "${derived_primary_results}")"
derived_quality_root_real="$(real_path "${derived_repo}/quality-results")"
derived_output_parent_real="$(dirname "${derived_output_real}")"
derived_output_name="$(basename "${derived_output_real}")"
[[ "${derived_output_real}" != "${derived_primary_real}" ]] \
  || die "derived output must not overlap the frozen primary results"
[[ "${derived_output_parent_real}" == "${derived_quality_root_real}" \
    && "${derived_output_name}" =~ ^leaderboard-top15-rank126-relative-[0-9]{8}$ ]] \
  || die "derived output must be a dedicated leaderboard-top15-rank126-relative-YYYYMMDD directory directly under ${derived_quality_root_real}"
[[ ! -L "${derived_output}" ]] || die "derived output may not be a symlink"
[[ -d "${derived_evaluator_source_project}/laguna_quality" ]] \
  || die "missing evaluator project: ${derived_evaluator_source_project}"
[[ -x "${derived_uv}" ]] || die "missing uv runtime: ${derived_uv}"
[[ -x "${derived_primary_runner}" ]] || die "missing primary runner: ${derived_primary_runner}"

derived_owner="${derived_output}/.mlxfast-rank126-relative-owner.json"
derived_owner_expected="$(jq -S -n \
  --arg schema "mlxfast-rank126-relative-owner-v1" \
  --arg repo "$(real_path "${derived_repo}")" \
  --arg output "${derived_output_real}" \
  --arg manifest_sha256 "${derived_manifest_sha256}" \
  '{schema:$schema,repo:$repo,output:$output,manifest_sha256:$manifest_sha256}')"
if [[ -d "${derived_output}" ]]; then
  [[ -f "${derived_owner}" ]] \
    || die "existing derived output lacks its ownership sentinel: ${derived_owner}"
  [[ "$(jq -S . "${derived_owner}")" == "${derived_owner_expected}" ]] \
    || die "derived output ownership sentinel does not match this campaign"
else
  mkdir "${derived_output}"
  printf '%s\n' "${derived_owner_expected}" > "${derived_owner}.tmp"
  mv "${derived_owner}.tmp" "${derived_owner}"
fi

derived_evaluator_commit="$(jq -er '.evaluator_commit' "${derived_manifest}")"
derived_expected_evaluator_sha256="$(jq -er '.evaluator_sha256' "${derived_manifest}")"
git -C "${derived_repo}" cat-file -e "${derived_evaluator_commit}^{commit}" \
  || die "frozen evaluator commit is unavailable: ${derived_evaluator_commit}"
derived_evaluator_snapshot="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-rank126-evaluator.XXXXXX")"
derived_evaluator_archive="${derived_evaluator_snapshot}/evaluator.tar"
git -C "${derived_repo}" archive \
  --format=tar \
  --output="${derived_evaluator_archive}" \
  "${derived_evaluator_commit}" \
  -- senpai/quality_eval \
  || die "could not snapshot the frozen evaluator commit"
/usr/bin/tar -xf "${derived_evaluator_archive}" -C "${derived_evaluator_snapshot}" \
  || die "could not extract the frozen evaluator snapshot"
rm -f "${derived_evaluator_archive}"
derived_evaluator_project="${derived_evaluator_snapshot}/senpai/quality_eval"
[[ -d "${derived_evaluator_project}/laguna_quality" ]] \
  || die "frozen evaluator snapshot is incomplete"
derived_uv_cache="${derived_evaluator_source_project}/.uv-cache"
derived_actual_evaluator_sha256="$(
  /usr/bin/env -i \
    HOME="${HOME}" \
    LOGNAME="${LOGNAME:-${USER:-}}" \
    PATH="$(dirname "${derived_uv}"):/usr/bin:/bin:/usr/sbin:/sbin" \
    PYTHONPATH="${derived_evaluator_project}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    USER="${USER:-}" \
    UV_CACHE_DIR="${derived_uv_cache}" \
    UV_OFFLINE=1 \
    "${derived_uv}" run --project "${derived_evaluator_project}" --locked \
      python -c 'from laguna_quality.runner import _evaluation_provenance; print(_evaluation_provenance()["sha256"])'
)"
[[ "${derived_actual_evaluator_sha256}" == "${derived_expected_evaluator_sha256}" ]] \
  || die "executing evaluator provenance differs from the frozen manifest"

derived_primary_status="$("${derived_primary_runner}" status)"
grep -Fqx 'quality: 15/15 processed (11 valid comparisons, 4 bounded non-completions)' \
  <<< "${derived_primary_status}" \
  || die "primary runner did not validate all 15 quality artifacts"

derived_allowed_files="$(mktemp "${TMPDIR:-/tmp}/mlxfast-rank126-allowed.XXXXXX")"
derived_actual_files="$(mktemp "${TMPDIR:-/tmp}/mlxfast-rank126-actual.XXXXXX")"
derived_checksum_files="$(mktemp "${TMPDIR:-/tmp}/mlxfast-rank126-checksums.XXXXXX")"
printf '%s\n' \
  .mlxfast-rank126-relative-owner.json \
  checksums.sha256 \
  primary-status.txt \
  summary.json \
  > "${derived_allowed_files}"
while IFS=$'\t' read -r derived_rank derived_id; do
  derived_arm="${derived_primary_results}/quality/${derived_rank}-${derived_id}"
  if [[ -f "${derived_arm}/selected-attempt.txt" ]]; then
    printf 'rank-%s.json\nrank-%s.log\n' "${derived_rank}" "${derived_rank}" \
      >> "${derived_allowed_files}"
  fi
done < <(jq -r '.candidates[] | [.rank,.submission_id] | @tsv' "${derived_manifest}")
LC_ALL=C sort -u -o "${derived_allowed_files}" "${derived_allowed_files}"
derived_nonfile_entry="$(find "${derived_output}" -mindepth 1 -maxdepth 1 ! -type f -print -quit)"
[[ -z "${derived_nonfile_entry}" ]] \
  || die "derived output contains an unexpected non-file entry: ${derived_nonfile_entry}"
find "${derived_output}" -mindepth 1 -maxdepth 1 -type f -exec basename {} \; \
  | LC_ALL=C sort -u > "${derived_actual_files}"
derived_unexpected_files="$(comm -23 "${derived_actual_files}" "${derived_allowed_files}")"
[[ -z "${derived_unexpected_files}" ]] \
  || die "derived output contains unexpected files: ${derived_unexpected_files//$'\n'/, }"

derived_primary_status_tmp="${derived_output}/.primary-status.txt.$$"
printf '%s\n' "${derived_primary_status}" > "${derived_primary_status_tmp}"
mv "${derived_primary_status_tmp}" "${derived_output}/primary-status.txt"
derived_primary_status_tmp=""

derived_baseline_id="$(jq -er '.candidates[] | select(.rank == 126) | .submission_id' "${derived_manifest}")"
derived_baseline_ref="$(jq -er '.candidates[] | select(.rank == 126) | .source_ref' "${derived_manifest}")"
derived_baseline_arm="${derived_primary_results}/quality/126-${derived_baseline_id}"
[[ -f "${derived_baseline_arm}/selected-attempt.txt" ]] \
  || die "rank 126 has no selected quality attempt"
derived_baseline_attempt="$(tr -d '[:space:]' < "${derived_baseline_arm}/selected-attempt.txt")"
[[ "${derived_baseline_attempt}" =~ ^attempt-[1-9][0-9]*$ ]] \
  || die "rank 126 selected attempt is malformed"
derived_baseline="${derived_baseline_arm}/${derived_baseline_attempt}"
derived_baseline_real="$(real_path "${derived_baseline}")"

jq -e --arg evaluator_sha256 "${derived_expected_evaluator_sha256}" '
  .evaluation_valid == true
  and .status == "completed"
  and .evaluator_provenance.sha256 == $evaluator_sha256
' "${derived_baseline}/run.json" >/dev/null \
  || die "rank 126 is not a complete artifact with the frozen evaluator provenance"

derived_records="$(mktemp "${TMPDIR:-/tmp}/mlxfast-rank126-records.XXXXXX")"
derived_summary_tmp="$(mktemp "${TMPDIR:-/tmp}/mlxfast-rank126-summary.XXXXXX")"

while IFS=$'\t' read -r derived_rank derived_id derived_ref; do
  derived_arm="${derived_primary_results}/quality/${derived_rank}-${derived_id}"
  if [[ -f "${derived_arm}/selected-attempt.txt" ]]; then
    derived_attempt="$(tr -d '[:space:]' < "${derived_arm}/selected-attempt.txt")"
    [[ "${derived_attempt}" =~ ^attempt-[1-9][0-9]*$ ]] \
      || die "rank ${derived_rank} selected attempt is malformed"
    derived_candidate="${derived_arm}/${derived_attempt}"
    derived_candidate_real="$(real_path "${derived_candidate}")"
    derived_comparison="${derived_output}/rank-${derived_rank}.json"
    derived_log="${derived_output}/rank-${derived_rank}.log"
    derived_active_comparison_tmp="$(mktemp "${derived_output}/.rank-${derived_rank}.json.XXXXXX")"
    derived_active_log_tmp="$(mktemp "${derived_output}/.rank-${derived_rank}.log.XXXXXX")"

    if ! /usr/bin/env -i \
      HOME="${HOME}" \
      LOGNAME="${LOGNAME:-${USER:-}}" \
      PATH="$(dirname "${derived_uv}"):/usr/bin:/bin:/usr/sbin:/sbin" \
      PYTHONPATH="${derived_evaluator_project}" \
      TMPDIR="${TMPDIR:-/tmp}" \
      USER="${USER:-}" \
      UV_CACHE_DIR="${derived_uv_cache}" \
      UV_OFFLINE=1 \
      "${derived_uv}" run --project "${derived_evaluator_project}" --locked \
        python -c 'from laguna_quality.cli import main; raise SystemExit(main())' compare \
        "${derived_baseline}" "${derived_candidate}" \
        --output "${derived_active_comparison_tmp}" --report-only \
        > "${derived_active_log_tmp}" 2>&1; then
      die "rank ${derived_rank} comparison failed"
    fi

    jq -e \
      --arg baseline "${derived_baseline_real}" \
      --arg candidate "${derived_candidate_real}" '
        .baseline == $baseline
        and .candidate == $candidate
        and .compatibility.validated == true
        and .minimum_retention == 0.97
        and (.decision.status == "retained" or .decision.status == "regression")
      ' "${derived_active_comparison_tmp}" >/dev/null \
      || die "rank ${derived_rank} comparison failed provenance or contract validation"
    mv "${derived_active_comparison_tmp}" "${derived_comparison}"
    mv "${derived_active_log_tmp}" "${derived_log}"
    derived_active_comparison_tmp=""
    derived_active_log_tmp=""

    jq -cn \
      --argjson rank "${derived_rank}" \
      --arg submission_id "${derived_id}" \
      --arg source_ref "${derived_ref}" \
      --arg attempt "${derived_attempt}" \
      --arg comparison_sha256 "$(sha256_file "${derived_comparison}")" \
      --arg log_sha256 "$(sha256_file "${derived_log}")" \
      --arg source_run_spec_sha256 "$(sha256_file "${derived_arm}/run-spec.json")" \
      --arg source_selected_attempt_sha256 "$(sha256_file "${derived_arm}/selected-attempt.txt")" \
      --arg source_attempt_meta_sha256 "$(sha256_file "${derived_arm}/${derived_attempt}.meta.json")" \
      --arg source_attempt_log_sha256 "$(sha256_file "${derived_arm}/${derived_attempt}.log")" \
      --arg source_original_comparison_sha256 "$(sha256_file "${derived_candidate}/comparison.json")" \
      --arg source_bridge_sha256 "$(sha256_file "${derived_arm}/candidate-bridge")" \
      --arg source_bridge_sidecar_sha256 "$(sha256_file "${derived_arm}/candidate-bridge.source.sha256")" \
      --arg source_bridge_source_sha256 "$(tr -d '[:space:]' < "${derived_arm}/candidate-bridge.source.sha256")" \
      --arg run_sha256 "$(sha256_file "${derived_candidate}/run.json")" \
      --arg summary_sha256 "$(sha256_file "${derived_candidate}/summary.json")" \
      --arg responses_sha256 "$(sha256_file "${derived_candidate}/responses.jsonl")" \
      --slurpfile comparison "${derived_comparison}" '
        {
          rank:$rank,
          submission_id:$submission_id,
          source_ref:$source_ref,
          evidence_status:"formal_comparison",
          attempt:$attempt,
          decision:$comparison[0].decision.status,
          local_retention_gate_passed:$comparison[0].decision.local_retention_gate_passed,
          downstream_correct:$comparison[0].metrics.overall_score.candidate_correct,
          downstream_total:$comparison[0].metrics.overall_score.candidate_total,
          ppl:$comparison[0].metrics.ppl.candidate,
          ranked_gpqa_matches:$comparison[0].response_identity.ranked_gpqa.matched,
          ranked_gpqa_total:$comparison[0].response_identity.ranked_gpqa.total,
          public_probe_matched:$comparison[0].response_identity.public_probe.matched,
          response_match_rate:$comparison[0].response_identity.match_rate,
          evidence:{
            comparison:{path:("rank-" + ($rank|tostring) + ".json"),sha256:$comparison_sha256},
            log:{path:("rank-" + ($rank|tostring) + ".log"),sha256:$log_sha256},
            source_run_spec_sha256:$source_run_spec_sha256,
            source_selected_attempt_sha256:$source_selected_attempt_sha256,
            source_attempt_meta_sha256:$source_attempt_meta_sha256,
            source_attempt_log_sha256:$source_attempt_log_sha256,
            source_original_comparison_sha256:$source_original_comparison_sha256,
            source_bridge_sha256:$source_bridge_sha256,
            source_bridge_sidecar_sha256:$source_bridge_sidecar_sha256,
            source_bridge_source_sha256:$source_bridge_source_sha256,
            source_run_sha256:$run_sha256,
            source_summary_sha256:$summary_sha256,
            source_responses_sha256:$responses_sha256
          }
        }
      ' >> "${derived_records}"
  else
    derived_terminal="${derived_arm}/terminal-noncompletion.json"
    [[ -f "${derived_terminal}" ]] \
      || die "rank ${derived_rank} has neither a selected attempt nor bounded evidence"
    jq -cn \
      --argjson rank "${derived_rank}" \
      --arg submission_id "${derived_id}" \
      --arg source_ref "${derived_ref}" \
      --arg terminal_sha256 "$(sha256_file "${derived_terminal}")" '
        {
          rank:$rank,
          submission_id:$submission_id,
          source_ref:$source_ref,
          evidence_status:"bounded_noncompletion",
          decision:"no_formal_decision",
          reason:"The frozen primary quick-profile AIME evaluation was length-bounded; no complete primary summary exists for comparison. Extended diagnostics are audited separately.",
          evidence:{terminal_noncompletion_sha256:$terminal_sha256}
        }
      ' >> "${derived_records}"
  fi
done < <(jq -r '.candidates[] | [.rank,.submission_id,.source_ref] | @tsv' "${derived_manifest}")

derived_formal_count="$(jq -s '[.[] | select(.evidence_status == "formal_comparison")] | length' "${derived_records}")"
derived_bounded_count="$(jq -s '[.[] | select(.evidence_status == "bounded_noncompletion")] | length' "${derived_records}")"
derived_self_control_count="$(jq -s '[.[] | select(.rank == 126 and .evidence_status == "formal_comparison")] | length' "${derived_records}")"
derived_retrospective_count="$((derived_formal_count - derived_self_control_count))"
[[ "${derived_formal_count}" == "11" && "${derived_bounded_count}" == "4" ]] \
  || die "unexpected coverage: formal=${derived_formal_count} bounded=${derived_bounded_count}"
[[ "${derived_self_control_count}" == "1" && "${derived_retrospective_count}" == "10" ]] \
  || die "unexpected self-control coverage"
[[ "$(jq -s -r '[.[] | select(.evidence_status == "bounded_noncompletion") | .rank] | sort | @json' "${derived_records}")" \
    == "[116,117,118,119]" ]] \
  || die "bounded rank set differs from the frozen primary evidence"

derived_baseline_comparison="${derived_output}/rank-126.json"
jq -e \
  --arg baseline "${derived_baseline_real}" '
    .baseline == $baseline
    and .candidate == $baseline
    and .compatibility.validated == true
    and .decision.status == "retained"
    and .decision.local_retention_gate_passed == true
    and .response_identity.ranked_gpqa.passed == true
    and .response_identity.public_probe.matched == true
    and .response_identity.matched == .response_identity.total
  ' "${derived_baseline_comparison}" >/dev/null \
  || die "rank 126 self-control did not reproduce the frozen comparison contract"
IFS=$'\t' read -r \
  derived_baseline_correct derived_baseline_total derived_baseline_ppl \
  derived_required_correct derived_maximum_ppl derived_required_ranked_matches \
  derived_ranked_total \
  < <(jq -r '[
    .metrics.overall_score.baseline_correct,
    .metrics.overall_score.baseline_total,
    .metrics.ppl.baseline,
    .metrics.overall_score.required_correct,
    .metrics.ppl.threshold,
    .response_identity.ranked_gpqa.required_matches,
    .response_identity.ranked_gpqa.total
  ] | @tsv' "${derived_baseline_comparison}")

derived_actual_evaluator_sha256_after="$(
  /usr/bin/env -i \
    HOME="${HOME}" \
    LOGNAME="${LOGNAME:-${USER:-}}" \
    PATH="$(dirname "${derived_uv}"):/usr/bin:/bin:/usr/sbin:/sbin" \
    PYTHONPATH="${derived_evaluator_project}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    USER="${USER:-}" \
    UV_CACHE_DIR="${derived_uv_cache}" \
    UV_OFFLINE=1 \
    "${derived_uv}" run --project "${derived_evaluator_project}" --locked \
      python -c 'from laguna_quality.runner import _evaluation_provenance; print(_evaluation_provenance()["sha256"])'
)"
[[ "${derived_actual_evaluator_sha256_after}" == "${derived_actual_evaluator_sha256}" ]] \
  || die "evaluator snapshot changed while deriving comparisons"
derived_primary_status_after="$("${derived_primary_runner}" status)"
[[ "${derived_primary_status_after}" == "${derived_primary_status}" ]] \
  || die "primary artifact validation changed while deriving comparisons"

jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg manifest_sha256 "${derived_manifest_sha256}" \
  --arg evaluator_commit "${derived_evaluator_commit}" \
  --arg evaluator_bundle_sha256 "${derived_actual_evaluator_sha256}" \
  --arg derivation_script_sha256 "$(sha256_file "${BASH_SOURCE[0]}")" \
  --arg primary_audit_runner_sha256 "$(sha256_file "${derived_primary_runner}")" \
  --arg primary_audit_status_sha256 "$(sha256_file "${derived_output}/primary-status.txt")" \
  --arg uv_sha256 "$(sha256_file "${derived_uv}")" \
  --arg uv_version "$("${derived_uv}" --version)" \
  --arg baseline_submission_id "${derived_baseline_id}" \
  --arg baseline_source_ref "${derived_baseline_ref}" \
  --arg baseline_attempt "${derived_baseline_attempt}" \
  --arg baseline_run_sha256 "$(sha256_file "${derived_baseline}/run.json")" \
  --arg baseline_summary_sha256 "$(sha256_file "${derived_baseline}/summary.json")" \
  --arg baseline_responses_sha256 "$(sha256_file "${derived_baseline}/responses.jsonl")" \
  --argjson baseline_correct "${derived_baseline_correct}" \
  --argjson baseline_total "${derived_baseline_total}" \
  --argjson baseline_ppl "${derived_baseline_ppl}" \
  --argjson required_correct "${derived_required_correct}" \
  --argjson maximum_ppl "${derived_maximum_ppl}" \
  --argjson required_ranked_matches "${derived_required_ranked_matches}" \
  --argjson ranked_total "${derived_ranked_total}" \
  --argjson formal_count "${derived_formal_count}" \
  --argjson retrospective_count "${derived_retrospective_count}" \
  --argjson self_control_count "${derived_self_control_count}" \
  --argjson bounded_count "${derived_bounded_count}" \
  --slurpfile results "${derived_records}" '
    {
      schema:"mlxfast-rank126-relative-quality-v1",
      generated_at:$generated_at,
      scope:"Same-host incremental quality diagnostic using the completed rank-126 artifact as the reference. This is not a private-gate surrogate or an official M5 result.",
      provenance:{
        primary_manifest_sha256:$manifest_sha256,
        evaluator_commit:$evaluator_commit,
        evaluator_bundle_sha256:$evaluator_bundle_sha256,
        derivation_script_sha256:$derivation_script_sha256,
        primary_audit_runner_sha256:$primary_audit_runner_sha256,
        primary_audit_status_path:"primary-status.txt",
        primary_audit_status_sha256:$primary_audit_status_sha256,
        uv_sha256:$uv_sha256,
        uv_version:$uv_version,
        offline:true
      },
      baseline:{
        rank:126,
        submission_id:$baseline_submission_id,
        source_ref:$baseline_source_ref,
        attempt:$baseline_attempt,
        downstream_correct:$baseline_correct,
        downstream_total:$baseline_total,
        ppl:$baseline_ppl,
        retention_contract:{minimum_retention:0.97,required_correct:$required_correct,maximum_ppl:$maximum_ppl,required_ranked_gpqa_matches:$required_ranked_matches,ranked_gpqa_total:$ranked_total,require_public_probe_match:true},
        evidence:{run_sha256:$baseline_run_sha256,summary_sha256:$baseline_summary_sha256,responses_sha256:$baseline_responses_sha256}
      },
      coverage:{formal_comparisons:$formal_count,retrospective_comparisons:$retrospective_count,self_controls:$self_control_count,bounded_noncompletions:$bounded_count,total:($formal_count+$bounded_count)},
      results:($results | sort_by(.rank)),
      interpretation:[
        "Ranks 120-125 retain rank 126 under the frozen 3% numeric plus 7/9 ranked-GPQA plus public-probe contract; rank 126 is the tautological self-control.",
        "Ranks 112-115 have equal-or-better aggregate score and PPL but fail response identity against rank 126; response behavior, not the 3% numeric terms, separates these lineage phases.",
        "Ranks 116-119 remain no-decisions because their AIME artifacts are incomplete.",
        "Comparisons from rank 126 back to earlier ranks are reverse-chronological diagnostics. Rank 126 is intended as the baseline for future autoresearch candidates."
      ]
    }
  ' > "${derived_summary_tmp}"
mv "${derived_summary_tmp}" "${derived_output}/summary.json"
derived_summary_tmp=""

derived_checksum_tmp="${derived_output}/checksums.sha256.tmp"
(
  cd "${derived_output}"
  grep -vx 'checksums.sha256' "${derived_allowed_files}" > "${derived_checksum_files}"
  while IFS= read -r derived_receipt_file; do
    [[ -f "${derived_receipt_file}" ]] \
      || die "derived receipt is missing expected file: ${derived_receipt_file}"
    shasum -a 256 "${derived_receipt_file}"
  done < "${derived_checksum_files}" > "${derived_checksum_tmp}"
  mv "${derived_checksum_tmp}" checksums.sha256
)
derived_checksum_tmp=""

find "${derived_output}" -mindepth 1 -maxdepth 1 -type f -exec basename {} \; \
  | LC_ALL=C sort -u > "${derived_actual_files}"
cmp -s "${derived_allowed_files}" "${derived_actual_files}" \
  || die "derived output file set differs from the audited receipt contract"
(
  cd "${derived_output}"
  shasum -a 256 -c checksums.sha256 >/dev/null
) || die "derived output checksum verification failed"

echo "rank126-quality: wrote ${derived_output}/summary.json"
jq -r '
  "rank\tevidence\tdecision\tcorrect\tppl\tranked_gpqa\tpublic\tresponse_match",
  (.results[] | [
    (.rank|tostring),
    .evidence_status,
    .decision,
    (if .downstream_correct == null then "-" else (.downstream_correct|tostring) end),
    (if .ppl == null then "-" else (.ppl|tostring) end),
    (if .ranked_gpqa_matches == null then "-" else ((.ranked_gpqa_matches|tostring)+"/"+(.ranked_gpqa_total|tostring)) end),
    (if .public_probe_matched == null then "-" else (.public_probe_matched|tostring) end),
    (if .response_match_rate == null then "-" else (.response_match_rate|tostring) end)
  ] | @tsv)
' "${derived_output}/summary.json"
