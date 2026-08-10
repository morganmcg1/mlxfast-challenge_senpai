#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = "Sources/MLXFastModel/LagunaRuntimeModel.swift"
MANIFEST = "research/submitted_surface_reclamation_manifest.json"
AUDIT_TOOL = "research/audit_submitted_surface_reclamation.py"
RECEIPT = "research/plain_comment_reclamation_receipt.json"
REQUIRED_BASE_SHA = "8d9ae30c3ecda31b52286f0fbfb4094cdfb29d64"
EXPECTED_CONTRACT_SHA256 = "e01d3ea1c9281cfe81e1693d987627005fed6963440fbef6a761e4f28dd67fb6"
EXPECTED_MANIFEST_SHA256 = "6d6fb5b582f8d06ba3bcd9c10a7f7ee8ab8461e77a9e0e4c22758e8acdd015a9"
EXPECTED_AUDIT_SHA256 = "c3ae403d400f359b7c8f6b1fa1943490c0f55c307b056d54add984d2549e7a01"
EXPECTED_ORIGINAL_SHA256 = "ed084a8aa840f651449b8c9f344c2cd40786de9eccee2c291bde419716022ccb"
EXPECTED_ORIGINAL_BYTES = 511_690
EXPECTED_CANDIDATE_BYTES = 480_894
EXPECTED_RECLAIMED_BYTES = 30_796
EXPECTED_RANGE_COUNT = 448
EXPECTED_NEWLINE_COUNT = 12_008
EXPECTED_SURFACE_FILES = 142
EXPECTED_SURFACE_BEFORE = 2_984_121
EXPECTED_SURFACE_AFTER = 2_953_325
MAX_TOTAL_BYTES = 3_000_000
MAX_FILE_BYTES = 524_288
ADDRESS_PATTERN = re.compile(rb"0x[0-9a-fA-F]+")


class ProofError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)


def git_bytes(*args: str) -> bytes:
    process = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise ProofError(f"git {' '.join(args)} failed: {detail}")
    return process.stdout


def checked_file(relative: str) -> Path:
    path = ROOT / relative
    require(path.is_file() and not path.is_symlink(), f"not a regular file: {relative}")
    return path


def load_frozen_inputs() -> tuple[dict[str, Any], bytes]:
    contract_raw = checked_file("benchmark.json").read_bytes()
    manifest_raw = checked_file(MANIFEST).read_bytes()
    audit_raw = checked_file(AUDIT_TOOL).read_bytes()
    require(sha256(contract_raw) == EXPECTED_CONTRACT_SHA256, "benchmark.json drifted")
    require(sha256(manifest_raw) == EXPECTED_MANIFEST_SHA256, "frozen manifest drifted")
    require(sha256(audit_raw) == EXPECTED_AUDIT_SHA256, "frozen audit tool drifted")
    manifest = json.loads(manifest_raw)
    require(manifest["surface"]["contract_sha256"] == EXPECTED_CONTRACT_SHA256, "manifest contract mismatch")
    require(manifest["surface"]["expanded_regular_files"] == EXPECTED_SURFACE_FILES, "manifest file count mismatch")
    require(manifest["surface"]["current_bytes"] == EXPECTED_SURFACE_BEFORE, "manifest surface total mismatch")
    return manifest, contract_raw


def load_original(manifest: dict[str, Any]) -> bytes:
    original = git_bytes("show", f"{REQUIRED_BASE_SHA}:{TARGET}")
    require(len(original) == EXPECTED_ORIGINAL_BYTES, "required-base target size drifted")
    require(sha256(original) == EXPECTED_ORIGINAL_SHA256, "required-base target hash drifted")
    plan = manifest["reclamation_plan"]
    require(plan["original_bytes"] == EXPECTED_ORIGINAL_BYTES, "manifest target size mismatch")
    require(plan["original_sha256"] == EXPECTED_ORIGINAL_SHA256, "manifest target hash mismatch")
    return original


def expanded_surface(contract_raw: bytes) -> set[str]:
    rules = json.loads(contract_raw)["editablePaths"]
    require(isinstance(rules, list) and len(rules) == 97, "editablePaths contract drifted")
    paths: set[str] = set()
    for rule in rules:
        require(isinstance(rule, str) and rule and ".." not in Path(rule).parts, f"unsafe editable path: {rule!r}")
        path = ROOT / rule
        require(path.exists() and not path.is_symlink(), f"editable path missing or symlinked: {rule}")
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        matched = 0
        for candidate in candidates:
            if candidate.is_dir():
                continue
            require(candidate.is_file() and not candidate.is_symlink(), f"non-regular submitted path: {candidate}")
            relative = candidate.relative_to(ROOT).as_posix()
            require(relative not in paths, f"submitted path matched multiple rules: {relative}")
            paths.add(relative)
            matched += 1
        require(matched > 0, f"editable path matched no regular files: {rule}")
    return paths


def validate_surface(
    manifest: dict[str, Any], contract_raw: bytes, target_sha: str, target_size: int
) -> dict[str, int]:
    records = manifest["surface"]["files"]
    require(len(records) == EXPECTED_SURFACE_FILES, "frozen surface records drifted")
    expected_paths = {item["path"] for item in records}
    require(len(expected_paths) == EXPECTED_SURFACE_FILES, "duplicate frozen surface record")
    require(expanded_surface(contract_raw) == expected_paths, "working submitted path set differs from frozen manifest")
    total = 0
    for item in records:
        path = checked_file(item["path"])
        data = path.read_bytes()
        expected_sha = target_sha if item["path"] == TARGET else item["sha256"]
        expected_size = target_size if item["path"] == TARGET else item["bytes"]
        require(len(data) == expected_size, f"submitted size mismatch: {item['path']}")
        require(sha256(data) == expected_sha, f"submitted hash mismatch: {item['path']}")
        total += len(data)
    expected_total = EXPECTED_SURFACE_BEFORE - EXPECTED_ORIGINAL_BYTES + target_size
    require(total == expected_total, "working submitted surface total mismatch")
    return {
        "files": len(records),
        "bytes": total,
        "global_headroom_bytes": MAX_TOTAL_BYTES - total,
        "target_headroom_bytes": MAX_FILE_BYTES - target_size,
    }


def validate_ranges(original: bytes, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranges = manifest["reclamation_plan"]["ranges"]
    require(len(ranges) == manifest["reclamation_plan"]["range_count"], "manifest range count mismatch")
    selected: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    cursor = 0
    for item in ranges:
        start = item["start_byte"]
        end = item["end_byte_exclusive"]
        require(cursor <= start < end <= len(original), "range ordering or bounds failure")
        removed = original[start:end]
        require(len(removed) == item["bytes"], "range byte count mismatch")
        require(sha256(removed) == item["removed_sha256"], "range removed-byte hash mismatch")
        require(start == 0 or original[start - 1 : start] == b"\n", "range does not begin at a line boundary")
        require(end == len(original) or original[end : end + 1] == b"\n", "range does not preserve its newline")
        require(b"\n" not in removed and b"\r" not in removed, "range includes a newline")
        line = original.count(b"\n", 0, start) + 1
        require(item["start_line"] == line and item["end_line"] == line, "range line metadata mismatch")
        stripped = removed.lstrip(b" \t")
        require(stripped.startswith(b"//"), "manifest range is not a whole-line // comment")
        if stripped.startswith(b"///"):
            docs.append(item)
        else:
            selected.append(item)
        cursor = end
    reclaimed = sum(item["bytes"] for item in selected)
    require(len(selected) == EXPECTED_RANGE_COUNT, "plain-comment range count is not exactly 448")
    require(reclaimed == EXPECTED_RECLAIMED_BYTES, "plain-comment byte total is not exactly 30,796")
    require(docs, "frozen manifest contains no /// positive control")
    first_doc = original[docs[0]["start_byte"] : docs[0]["end_byte_exclusive"]].lstrip(b" \t")
    require(first_doc.startswith(b"///") and not (first_doc.startswith(b"//") and not first_doc.startswith(b"///")), "/// positive control was not rejected")
    return selected, docs


def apply_ranges(original: bytes, ranges: list[dict[str, Any]]) -> bytes:
    output: list[bytes] = []
    cursor = 0
    for item in ranges:
        start = item["start_byte"]
        end = item["end_byte_exclusive"]
        require(cursor <= start < end <= len(original), "selected range ordering failure")
        removed = original[start:end]
        require(sha256(removed) == item["removed_sha256"], "selected range hash mismatch")
        output.append(original[cursor:start])
        cursor = end
    output.append(original[cursor:])
    return b"".join(output)


def reconstruct_original(candidate: bytes, receipt_ranges: list[dict[str, Any]]) -> bytes:
    output: list[bytes] = []
    original_cursor = 0
    candidate_cursor = 0
    for item in receipt_ranges:
        deleted = base64.b64decode(item["deleted_base64"], validate=True)
        require(len(deleted) == item["bytes"], "receipt deleted-byte count mismatch")
        require(sha256(deleted) == item["removed_sha256"], "receipt deleted-byte hash mismatch")
        gap = item["start_byte"] - original_cursor
        require(gap >= 0, "receipt range ordering failure")
        output.append(candidate[candidate_cursor : candidate_cursor + gap])
        candidate_cursor += gap
        output.append(deleted)
        original_cursor = item["end_byte_exclusive"]
    tail = EXPECTED_ORIGINAL_BYTES - original_cursor
    require(tail >= 0, "receipt original size underflow")
    output.append(candidate[candidate_cursor : candidate_cursor + tail])
    candidate_cursor += tail
    require(candidate_cursor == len(candidate), "reverse reconstruction did not consume candidate")
    return b"".join(output)


def document_proof(
    original: bytes, candidate: bytes, selected: list[dict[str, Any]], docs: list[dict[str, Any]]
) -> dict[str, Any]:
    original_docs: list[bytes] = []
    candidate_docs: list[bytes] = []
    deleted_before = 0
    selected_index = 0
    for doc in docs:
        while selected_index < len(selected) and selected[selected_index]["end_byte_exclusive"] <= doc["start_byte"]:
            deleted_before += selected[selected_index]["bytes"]
            selected_index += 1
        original_bytes = original[doc["start_byte"] : doc["end_byte_exclusive"]]
        mapped_start = doc["start_byte"] - deleted_before
        mapped_end = doc["end_byte_exclusive"] - deleted_before
        candidate_bytes = candidate[mapped_start:mapped_end]
        require(candidate_bytes == original_bytes, f"documentation comment changed at line {doc['start_line']}")
        original_docs.append(original_bytes)
        candidate_docs.append(candidate_bytes)
    original_joined = b"".join(original_docs)
    candidate_joined = b"".join(candidate_docs)
    require(original_joined == candidate_joined, "documentation aggregate changed")
    return {
        "range_count": len(docs),
        "bytes": len(original_joined),
        "sha256": sha256(original_joined),
        "positive_control": "first frozen /// range rejected by plain-comment predicate",
    }


def parse_dump(data: bytes, source_path: Path) -> bytes:
    source_path.write_bytes(data)
    process = subprocess.run(
        ["swiftc", "-frontend", "-dump-parse", str(source_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace")[-2000:]
        raise ProofError(f"swift parser failed: {detail}")
    combined = process.stdout + b"\n--STDERR--\n" + process.stderr
    combined = combined.replace(os.fsencode(source_path.resolve()), b"<SOURCE_PATH>")
    combined = combined.replace(os.fsencode(source_path), b"<SOURCE_PATH>")
    return ADDRESS_PATTERN.sub(b"0xADDR", combined)


def parser_proof(original: bytes, candidate: bytes) -> dict[str, Any]:
    require(shutil.which("swiftc") is not None, "swiftc is unavailable")
    with tempfile.TemporaryDirectory(prefix="plain-comment-proof-") as directory:
        source_path = Path(directory) / "LagunaRuntimeModel.swift"
        original_dump = parse_dump(original, source_path)
        candidate_dump = parse_dump(candidate, source_path)
    require(original_dump == candidate_dump, "normalized Swift parse dumps differ")
    version = subprocess.run(
        ["swiftc", "--version"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.decode("utf-8", errors="replace").strip()
    return {
        "command": "swiftc -frontend -dump-parse <same-temporary-path>",
        "normalization": "temporary source path replaced with <SOURCE_PATH>; hexadecimal pointer-like addresses replaced with 0xADDR",
        "normalized_bytes": len(original_dump),
        "normalized_sha256": sha256(original_dump),
        "equal": True,
        "swiftc_version": version,
    }


def receipt_ranges(original: bytes, selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in selected:
        deleted = original[item["start_byte"] : item["end_byte_exclusive"]]
        output.append({
            "start_byte": item["start_byte"],
            "end_byte_exclusive": item["end_byte_exclusive"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "bytes": item["bytes"],
            "removed_sha256": item["removed_sha256"],
            "deleted_base64": base64.b64encode(deleted).decode("ascii"),
        })
    return output


def build_receipt(
    original: bytes,
    candidate: bytes,
    selected: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    parser: dict[str, Any],
    surface: dict[str, int],
) -> dict[str, Any]:
    ranges = receipt_ranges(original, selected)
    deleted = b"".join(base64.b64decode(item["deleted_base64"]) for item in ranges)
    reconstructed = reconstruct_original(candidate, ranges)
    require(reconstructed == original, "reverse reconstruction differs from required-base source")
    require(candidate.count(b"\n") == original.count(b"\n") == EXPECTED_NEWLINE_COUNT, "newline count changed")
    docs_proof = document_proof(original, candidate, selected, docs)
    return {
        "schema_version": 1,
        "assignment": {
            "pull_request": 668,
            "assignment_id": "cedar-nezuko-plain-comment-headroom-reclaim-20260810",
            "revision_id": "cedar-nezuko-plain-comment-headroom-reclaim-20260810-r1",
            "required_base_sha": REQUIRED_BASE_SHA,
        },
        "frozen_inputs": {
            "contract": {"path": "benchmark.json", "sha256": EXPECTED_CONTRACT_SHA256},
            "manifest": {"path": MANIFEST, "sha256": EXPECTED_MANIFEST_SHA256},
            "audit_tool": {"path": AUDIT_TOOL, "sha256": EXPECTED_AUDIT_SHA256},
            "application_tool": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha256(Path(__file__).read_bytes())},
        },
        "selection": {
            "predicate": "lstrip(space-or-tab).startswith('//') and not startswith('///') over frozen manifest ranges",
            "range_count": len(ranges),
            "reclaimed_bytes": len(deleted),
            "deleted_bytes_sha256": sha256(deleted),
            "excluded_documentation": docs_proof,
        },
        "target": {
            "path": TARGET,
            "before": {"bytes": len(original), "sha256": sha256(original), "newline_count": original.count(b"\n")},
            "after": {"bytes": len(candidate), "sha256": sha256(candidate), "newline_count": candidate.count(b"\n")},
            "reverse_reconstruction_sha256": sha256(reconstructed),
            "reverse_reconstruction_matches_original": reconstructed == original,
            "nondeleted_bytes_remain_in_order": True,
        },
        "surface": surface,
        "proofs": {
            "swift_parse_dump": parser,
            "every_newline_preserved": True,
            "documentation_bytes_preserved": True,
            "only_plain_whole_line_comment_bodies_removed": True,
        },
        "ranges": ranges,
    }


def encode_receipt(receipt: dict[str, Any]) -> bytes:
    return (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as temporary:
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, mode)
    os.replace(temporary_path, path)


def prepare() -> tuple[dict[str, Any], bytes, bytes, list[dict[str, Any]], list[dict[str, Any]], bytes]:
    manifest, contract_raw = load_frozen_inputs()
    original = load_original(manifest)
    selected, docs = validate_ranges(original, manifest)
    candidate = apply_ranges(original, selected)
    require(len(candidate) == EXPECTED_CANDIDATE_BYTES, "candidate size is not exactly 480,894")
    require(len(original) - len(candidate) == EXPECTED_RECLAIMED_BYTES, "candidate byte delta mismatch")
    require(candidate.count(b"\n") == EXPECTED_NEWLINE_COUNT, "candidate newline count mismatch")
    return manifest, contract_raw, original, selected, docs, candidate


def apply() -> dict[str, Any]:
    manifest, contract_raw, original, selected, docs, candidate = prepare()
    current = checked_file(TARGET).read_bytes()
    require(current == original, "--apply requires the exact frozen original target")
    before_surface = validate_surface(
        manifest, contract_raw, EXPECTED_ORIGINAL_SHA256, EXPECTED_ORIGINAL_BYTES
    )
    parser = parser_proof(original, candidate)
    surface = {
        "files": before_surface["files"],
        "bytes": EXPECTED_SURFACE_AFTER,
        "global_headroom_bytes": MAX_TOTAL_BYTES - EXPECTED_SURFACE_AFTER,
        "target_headroom_bytes": MAX_FILE_BYTES - len(candidate),
    }
    receipt = build_receipt(original, candidate, selected, docs, parser, surface)
    target_path = ROOT / TARGET
    target_mode = target_path.stat().st_mode & 0o777
    atomic_write(target_path, candidate, target_mode)
    atomic_write(ROOT / RECEIPT, encode_receipt(receipt), 0o644)
    return receipt


def verify() -> dict[str, Any]:
    manifest, contract_raw, original, selected, docs, candidate = prepare()
    current = checked_file(TARGET).read_bytes()
    require(current == candidate, "working target is not the deterministic plain-comment candidate")
    candidate_sha = sha256(candidate)
    surface = validate_surface(manifest, contract_raw, candidate_sha, len(candidate))
    parser = parser_proof(original, candidate)
    expected = build_receipt(original, candidate, selected, docs, parser, surface)
    receipt_raw = checked_file(RECEIPT).read_bytes()
    actual = json.loads(receipt_raw)
    require(actual == expected, "receipt differs from freshly reproduced proof")
    reconstructed = reconstruct_original(candidate, actual["ranges"])
    require(sha256(reconstructed) == EXPECTED_ORIGINAL_SHA256, "receipt reconstruction hash mismatch")
    require(encode_receipt(actual) == receipt_raw, "receipt is not canonical compact JSON")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or verify frozen plain-comment source reclamation")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    try:
        receipt = apply() if arguments.apply else verify()
    except (ProofError, KeyError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"plain-comment reclamation proof failed: {error}", file=os.sys.stderr)
        return 1
    result = {
        "status": "applied" if arguments.apply else "verified",
        "range_count": receipt["selection"]["range_count"],
        "reclaimed_bytes": receipt["selection"]["reclaimed_bytes"],
        "candidate_sha256": receipt["target"]["after"]["sha256"],
        "surface_bytes": receipt["surface"]["bytes"],
        "global_headroom_bytes": receipt["surface"]["global_headroom_bytes"],
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
