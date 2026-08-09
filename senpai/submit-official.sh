#!/usr/bin/env bash
# Refuse an official submission unless its recorded base includes current fork main.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 BASE_SHA [mlxfast submit arguments...]" >&2
  exit 2
fi
base_input="$1"
shift

if [[ "${base_input}" == *[!0-9a-fA-F]* ]] \
  || { [[ ${#base_input} -ne 40 ]] && [[ ${#base_input} -ne 64 ]]; }
then
  echo "official submit: BASE_SHA must be a full 40- or 64-character commit hash" >&2
  exit 2
fi
for argument in "$@"; do
  if [[ "${argument}" == "--model" || "${argument}" == --model=* ]]; then
    echo "official submit: model attribution is fixed to senpai" >&2
    exit 2
  fi
done
for command_name in git jq mlxfast; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "official submit: ${command_name} is required" >&2
    exit 2
  fi
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "official submit: run this command inside a git worktree" >&2
  exit 2
}
cd "${repo_root}"
base_sha="$(git rev-parse --verify --quiet "${base_input}^{commit}")" || {
  echo "official submit: BASE_SHA ${base_input} is not a local commit" >&2
  exit 2
}

fetch_args=(--no-tags origin +refs/heads/main:refs/remotes/origin/main)
if [[ -f "$(git rev-parse --git-path shallow)" ]]; then
  fetch_args=(--no-tags --unshallow origin +refs/heads/main:refs/remotes/origin/main)
fi
if ! git fetch "${fetch_args[@]}"; then
  echo "official submit: could not refresh origin/main; no submission was sent" >&2
  exit 1
fi
main_sha="$(git rev-parse --verify refs/remotes/origin/main^{commit})"

if ! git merge-base --is-ancestor "${base_sha}" HEAD; then
  echo "official submit: BASE_SHA ${base_sha} is not an ancestor of HEAD" >&2
  exit 1
fi

contract="$(git show "${main_sha}:benchmark.json" 2>/dev/null)" || {
  echo "official submit: current origin/main has no readable benchmark.json" >&2
  exit 1
}
if ! jq -e '
  .editablePaths
  | type == "array" and length > 0
    and all(.[]; type == "string" and length > 0)
' >/dev/null <<<"${contract}"; then
  echo "official submit: BASE_SHA has no usable editablePaths" >&2
  exit 1
fi

protected_paths=(benchmark.json)
while IFS= read -r editable_path; do
  protected_paths+=("${editable_path}")
done < <(jq -r '.editablePaths[]' <<<"${contract}")

if ! git diff --quiet "${main_sha}" "${base_sha}" -- "${protected_paths[@]}"; then
  echo "official submit: BASE_SHA submitted snapshot differs from current origin/main" >&2
  echo "official submit: reapply and remeasure the candidate on a current snapshot" >&2
  exit 1
fi
if ! git diff --quiet "${main_sha}" HEAD -- benchmark.json; then
  echo "official submit: benchmark.json differs from current origin/main" >&2
  exit 1
fi

if ! index_entries="$(git ls-files -v -- "${protected_paths[@]}")"; then
  echo "official submit: could not inspect submitted index entries" >&2
  exit 1
fi
while IFS=' ' read -r index_tag _; do
  case "${index_tag}" in
    S|[a-z])
      echo "official submit: skip-worktree/assume-unchanged is set under submitted paths" >&2
      exit 1
      ;;
  esac
done <<<"${index_entries}"

if ! working_status="$(
  git status --porcelain=v1 --untracked-files=all --ignored=matching \
    -- "${protected_paths[@]}"
)"; then
  echo "official submit: could not inspect the submitted working tree" >&2
  exit 1
fi
if [[ -n "${working_status}" ]]; then
  echo "official submit: commit or discard changes under benchmark.json/editablePaths first" >&2
  exit 1
fi

exec mlxfast submit --model senpai "$@"
