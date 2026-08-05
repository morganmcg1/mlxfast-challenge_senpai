#!/usr/bin/env bash
# Check the working tree's base-authorized editable surface before a costly run.
set -euo pipefail

MAX_TOTAL_BYTES=3000000
MAX_FILE_BYTES=524288
MAX_GROWTH_BYTES=262144

if [[ $# -ne 1 ]]; then
  echo "usage: $0 BASE_SHA" >&2
  exit 2
fi
base_input="$1"

if [[ "${base_input}" == *[!0-9a-fA-F]* ]] \
  || { [[ ${#base_input} -ne 40 ]] && [[ ${#base_input} -ne 64 ]]; }
then
  echo "editable budget: BASE_SHA must be a full 40- or 64-character commit hash" >&2
  exit 2
fi
for command_name in git jq find wc; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "editable budget: ${command_name} is required" >&2
    exit 2
  fi
done

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "editable budget: run this command inside a git worktree" >&2
  exit 2
fi
cd "${repo_root}"
if ! base_sha="$(git rev-parse --verify --quiet "${base_input}^{commit}")"; then
  echo "editable budget: BASE_SHA ${base_input} is not a commit in this repository" >&2
  exit 2
fi
if ! contract="$(git show "${base_sha}:benchmark.json" 2>/dev/null)"; then
  echo "editable budget: ${base_sha} has no readable benchmark.json" >&2
  exit 2
fi
if ! jq -e '
  .editablePaths
  | type == "array" and length > 0
    and all(.[]; type == "string" and length > 0)
' >/dev/null <<<"${contract}"; then
  echo "editable budget: ${base_sha}:benchmark.json has no usable editablePaths" >&2
  exit 2
fi

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/mlxfast-budget.XXXXXX")"
trap 'rm -rf "${temporary_dir}"' EXIT
base_seen="${temporary_dir}/base-seen"
working_seen="${temporary_dir}/working-seen"
: > "${base_seen}"
: > "${working_seen}"

base_total=0
base_count=0
working_total=0
working_count=0

account_base_file() {
  local path="$1"
  local bytes
  if grep -Fqx -- "${path}" "${base_seen}"; then
    return
  fi
  printf '%s\n' "${path}" >> "${base_seen}"
  bytes="$(git cat-file -s "${base_sha}:${path}")"
  base_total=$((base_total + bytes))
  base_count=$((base_count + 1))
}

account_working_file() {
  local path="$1"
  local bytes
  if [[ "${path}" == *$'\n'* || "${path}" == *$'\r'* ]]; then
    echo "editable budget: control character in editable filename" >&2
    exit 1
  fi
  if grep -Fqx -- "${path}" "${working_seen}"; then
    return
  fi
  printf '%s\n' "${path}" >> "${working_seen}"
  bytes="$(wc -c < "${path}" | tr -d ' ')"
  if (( bytes > MAX_FILE_BYTES )); then
    echo "editable budget: ${path} is ${bytes} bytes; per-file limit is ${MAX_FILE_BYTES}" >&2
    exit 1
  fi
  working_total=$((working_total + bytes))
  working_count=$((working_count + 1))
  if (( working_total > MAX_TOTAL_BYTES )); then
    echo "editable budget: surface is at least ${working_total} bytes; total limit is ${MAX_TOTAL_BYTES}" >&2
    exit 1
  fi
}

while IFS= read -r editable_path; do
  if [[ -z "${editable_path}" || "${editable_path}" == /* \
    || "${editable_path}" == :* || "${editable_path}" == *\\* ]]
  then
    echo "editable budget: invalid editablePaths entry '${editable_path}'" >&2
    exit 2
  fi
  case "/${editable_path}/" in
    *"//"*|*"/../"*|*"/./"*)
      echo "editable budget: invalid editablePaths entry '${editable_path}'" >&2
      exit 2
      ;;
  esac

  while IFS= read -r -d '' base_file; do
    account_base_file "${base_file}"
  done < <(git ls-tree -r --name-only -z "${base_sha}" -- "${editable_path}")

  if [[ -L "${editable_path}" ]]; then
    echo "editable budget: editable path is a symlink: ${editable_path}" >&2
    exit 1
  fi
  if [[ -f "${editable_path}" ]]; then
    account_working_file "${editable_path}"
    continue
  fi
  if [[ -d "${editable_path}" ]]; then
    if find "${editable_path}" -type l -print -quit | grep -q .; then
      echo "editable budget: symlink found under editable directory ${editable_path}" >&2
      exit 1
    fi
    while IFS= read -r -d '' working_file; do
      account_working_file "${working_file}"
    done < <(find "${editable_path}" -type f -print0)
  fi
done < <(jq -r '.editablePaths[]' <<<"${contract}")

growth=$((working_total - base_total))
if (( growth > MAX_GROWTH_BYTES )); then
  echo "editable budget: surface grew ${growth} bytes from BASE_SHA; growth limit is ${MAX_GROWTH_BYTES}" >&2
  exit 1
fi

headroom=$((MAX_TOTAL_BYTES - working_total))
echo "editable budget OK: current=${working_total}/${MAX_TOTAL_BYTES} bytes headroom=${headroom} growth=${growth}/${MAX_GROWTH_BYTES} files=${working_count} (file count is diagnostic only; base=${base_count})"
