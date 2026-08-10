#!/usr/bin/env python3

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath


READY = "SELECTOR_ATTESTATION_STATIC_RESUME_READY"
INCOMPLETE = "SELECTOR_ATTESTATION_INCOMPLETE"
INVALID = "SELECTOR_ATTESTATION_INVALID"
AUTHORIZATION_SCOPE = "PR_670_FUTURE_STATIC_RESUMPTION_ONLY"
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("ranked_selector_attestation.schema.json")
EXPECTED_SCHEMA_SHA256 = "d27b3c1db7394089dcc328de0f715c3dd1ba596c3a6bd878dbf8d9c4ab41055e"
STATIC_RESUME_TARGET = {
    "selector_audit_pr_number": 670,
    "frozen_experiment_base_sha": "ccbe6fad8fc0923709ae335a83bdbafcc5a3fcdb",
    "frozen_environment_audit_sha256": "09dedaf97a31e0be10e679b792587c04142e5c662763486a32e097789f0d4375",
    "current_source_revision": "ac0e7cf6f283c8ac655af955d7ccf57c5141185e",
    "pinned_source_revision": "15852ee52858def42ddd4f32bca7e59d275e020e",
}
STATIC_RESUME_TARGET_KEYS = set(STATIC_RESUME_TARGET)
PHASES = (
    "current_public_correctness",
    "current_hidden_gates",
    "pinned_baseline_timed",
    "current_candidate_timed",
)
PHASE_ROLES = {
    "current_public_correctness": "current",
    "current_hidden_gates": "current",
    "pinned_baseline_timed": "pinned",
    "current_candidate_timed": "current",
}
PARSER_PROFILES = {
    "bool_exact_1_v1",
    "bool_nonzero_v1",
    "int_v1",
    "enum_identity_v1",
}
ROOT_KEYS = {
    "schema_version",
    "static_resume_target",
    "audited_source_revisions",
    "workflow_sha256",
    "selector_census_sha256",
    "ranked_job_id",
    "ranked_run_id",
    "host_class",
    "trusted_collector_id",
    "capture_epoch",
    "installed_authority_bundle_digest",
    "comparison_intent",
    "revision_only_policy",
    "censuses",
    "phases",
    "manifest",
    "canonical_bundle_sha256",
}
EXPECTATION_KEYS = {
    "schema_version",
    "static_resume_target",
    "audited_source_revisions",
    "workflow_sha256",
    "selector_census_sha256",
    "ranked_job_id",
    "ranked_run_id",
    "host_class",
    "trusted_collector_id",
    "capture_epoch",
    "installed_authority_bundle_digest",
    "canonical_bundle_sha256",
}
CENSUS_KEYS = {
    "schema_version",
    "revision_role",
    "source_revision",
    "consumer_inventory_sha256",
    "rows",
}
CENSUS_ROW_KEYS = {
    "row_id",
    "name",
    "source_locator",
    "parser_profile",
    "allowed_values_utf8_b64",
    "absent_normalized",
}
SNAPSHOT_KEYS = {
    "schema_version",
    "process_class",
    "stage",
    "source_revision",
    "census_sha256",
    "spawn_edge_id",
    "capture_epoch",
    "rows",
    "forced_runtime_worker",
    "canonical_selector_map_sha256",
}
SNAPSHOT_ROW_KEYS = {
    "name",
    "census_row_id",
    "source_revision",
    "parser_profile",
    "state",
    "value_utf8_b64",
    "normalized_semantic",
    "canonical_row_sha256",
}
PHASE_KEYS = {
    "process_class",
    "source_revision_role",
    "spawn_edge_id",
    "parent_snapshot",
    "worker_snapshot",
}
MANIFEST_KEYS = {"role", "path", "byte_size", "sha256"}
POLICY_KEYS = {
    "key",
    "present_in_revision",
    "missing_from_revision",
    "reason_code",
    "allowed_state",
    "allowed_value_sha256",
    "justification",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EPOCH_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
METADATA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")
RELATIVE_PATH_RE = re.compile(
    r"^(?!.*(?:^|/)\.{1,2}(?:/|$))[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
SELECTOR_RE = re.compile(r"^(?:DARKBLOOM_|MLX_)[A-Z0-9_]+$")
SECRET_NAME_RE = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY|AUTH_SOCK|CREDENTIAL|COOKIE|SESSION)"
)
REDACTION_VALUES = {
    "<redacted>",
    "[redacted]",
    "redacted",
    "***",
    "xxxxx",
    "hidden",
    "masked",
}


class ValidationFailure(Exception):
    def __init__(self, code, location, detail):
        super().__init__(f"{code}: {location}: {detail}")
        self.code = code
        self.location = location
        self.detail = detail


class DuplicateKey(ValueError):
    pass


def fail(code, location, detail):
    raise ValidationFailure(code, location, detail)


def canonical_json_bytes(value, trailing_lf=False):
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return data + (b"\n" if trailing_lf else b"")


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(key)
        result[key] = value
    return result


def strict_load_bytes(data, location):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("JSON_UTF8_INVALID", location, f"invalid UTF-8 at byte {exc.start}")
    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except DuplicateKey as exc:
        fail("JSON_DUPLICATE_KEY", location, f"duplicate key {exc.args[0]!r}")
    except (json.JSONDecodeError, ValueError) as exc:
        fail("JSON_INVALID", location, str(exc))


def strict_load_file(path, location):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        fail("DECLARED_FILE_MISSING", location, "file is absent")
    except OSError as exc:
        fail("FILE_READ_FAILED", location, str(exc))
    return strict_load_bytes(data, location)


def strict_load_canonical_bytes(data, location):
    value = strict_load_bytes(data, location)
    if data != canonical_json_bytes(value, trailing_lf=True):
        fail("PHYSICAL_JSON_NONCANONICAL", location, "expected compact sorted-key JSON with one LF")
    return value


def strict_load_canonical_file(path, location):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        fail("DECLARED_FILE_MISSING", location, "file is absent")
    except OSError as exc:
        fail("FILE_READ_FAILED", location, str(exc))
    return strict_load_canonical_bytes(data, location)


def load_pinned_expectations(path, expected_sha256):
    if expected_sha256 is None:
        fail(
            "TRUSTED_EXPECTATIONS_PIN_MISSING",
            "expected_expectations_sha256",
            "verifier-owned trusted expectations digest is required",
        )
    require_sha256(expected_sha256, "expected_expectations_sha256")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        fail("DECLARED_FILE_MISSING", "expectations", "file is absent")
    except OSError as exc:
        fail("FILE_READ_FAILED", "expectations", str(exc))
    actual_sha256 = sha256_bytes(data)
    if actual_sha256 != expected_sha256:
        fail(
            "TRUSTED_EXPECTATIONS_DIGEST_MISMATCH",
            "expectations",
            f"expected {expected_sha256}, got {actual_sha256}",
        )
    return strict_load_canonical_bytes(data, "expectations")


def exact_object(value, keys, location):
    if not isinstance(value, dict):
        fail("SCHEMA_INVALID", location, "expected object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        fail("SCHEMA_INVALID", location, f"missing={missing}, extra={extra}")


def require_list(value, location):
    if not isinstance(value, list):
        fail("SCHEMA_INVALID", location, "expected array")
    return value


def require_string(value, location):
    if not isinstance(value, str):
        fail("SCHEMA_INVALID", location, "expected string")
    return value


def require_schema_version(value, location):
    if type(value) is not int or value != 1:
        fail("SCHEMA_INVALID", location, "only integer schema version 1 is supported")


def require_sha256(value, location):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        fail("SCHEMA_INVALID", location, "expected lowercase SHA-256")


def require_git_sha(value, location):
    if not isinstance(value, str) or not GIT_SHA_RE.fullmatch(value):
        fail("SCHEMA_INVALID", location, "expected lowercase 40-byte git SHA")


def require_metadata(value, location):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 160
        or not METADATA_RE.fullmatch(value)
    ):
        fail("SCHEMA_INVALID", location, "invalid non-secret metadata token")


def require_capture_epoch(value, location):
    if not isinstance(value, str) or not EPOCH_RE.fullmatch(value):
        fail("SCHEMA_INVALID", location, "expected UTC second timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        fail("CAPTURE_EPOCH_INVALID", location, "timestamp is not a real UTC calendar instant")


def require_selector_name(value, location):
    name = require_string(value, location)
    if secret_name_forbidden(name):
        fail("SECRET_NAME_FORBIDDEN", location, name)
    if len(name) > 160:
        fail("SELECTOR_NAME_INVALID", location, "selector exceeds 160 characters")
    if not SELECTOR_RE.fullmatch(name):
        fail("UNKNOWN_SELECTOR", location, name)
    return name


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def require_closed_schema_object(definition, keys, location):
    if not isinstance(definition, dict) or definition.get("additionalProperties") is not False:
        fail("SCHEMA_CONTRACT_DRIFT", location, "object is not closed-world")
    if set(definition.get("required", [])) != keys or set(definition.get("properties", {})) != keys:
        fail("SCHEMA_CONTRACT_DRIFT", location, "required/properties differ from validator")


def validate_schema_contract(schema_path):
    path = Path(schema_path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail("SCHEMA_CONTRACT_MISSING", "schema", str(exc))
    digest = sha256_bytes(data)
    if digest != EXPECTED_SCHEMA_SHA256:
        fail("SCHEMA_CONTRACT_DRIFT", "schema", f"expected {EXPECTED_SCHEMA_SHA256}, got {digest}")
    schema = strict_load_bytes(data, str(path))
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs", "definitions object is absent")
    object_contracts = (
        ("schema", schema, ROOT_KEYS),
        ("schema.$defs.phase", definitions.get("phase"), PHASE_KEYS),
        ("schema.$defs.manifestEntry", definitions.get("manifestEntry"), MANIFEST_KEYS),
        ("schema.$defs.revisionOnlyRule", definitions.get("revisionOnlyRule"), POLICY_KEYS),
        ("schema.$defs.census", definitions.get("census"), CENSUS_KEYS),
        ("schema.$defs.censusRow", definitions.get("censusRow"), CENSUS_ROW_KEYS),
        ("schema.$defs.snapshot", definitions.get("snapshot"), SNAPSHOT_KEYS),
        ("schema.$defs.snapshotRow", definitions.get("snapshotRow"), SNAPSHOT_ROW_KEYS),
        ("schema.$defs.staticResumeTarget", definitions.get("staticResumeTarget"), STATIC_RESUME_TARGET_KEYS),
        ("schema.$defs.trustedExpectations", definitions.get("trustedExpectations"), EXPECTATION_KEYS),
        ("schema.$defs.forcedRuntimeWorker", definitions.get("forcedRuntimeWorker"), {"name", "value_utf8_b64"}),
    )
    for location, definition, keys in object_contracts:
        require_closed_schema_object(definition, keys, location)
    root_properties = schema["properties"]
    expectation_properties = definitions["trustedExpectations"]["properties"]
    for prefix, properties in (("schema", root_properties), ("schema.$defs.trustedExpectations", expectation_properties)):
        require_closed_schema_object(properties["audited_source_revisions"], {"current", "pinned"}, f"{prefix}.audited_source_revisions")
        require_closed_schema_object(properties["selector_census_sha256"], {"current", "pinned"}, f"{prefix}.selector_census_sha256")
    require_closed_schema_object(root_properties["comparison_intent"], {"kind", "policy_id"}, "schema.comparison_intent")
    require_closed_schema_object(root_properties["censuses"], {"current", "pinned"}, "schema.censuses")
    target_properties = definitions["staticResumeTarget"]["properties"]
    for key, value in STATIC_RESUME_TARGET.items():
        if target_properties[key].get("const") != value:
            fail("SCHEMA_CONTRACT_DRIFT", f"schema.$defs.staticResumeTarget.{key}", "constant differs")
    selector = definitions.get("selectorName", {})
    if selector.get("type") != "string" or selector.get("maxLength") != 160 or selector.get("pattern") != SELECTOR_RE.pattern:
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs.selectorName", "selector limits differ")
    capture = definitions.get("captureEpoch", {})
    if capture.get("type") != "string" or capture.get("pattern") != EPOCH_RE.pattern or capture.get("format") != "date-time":
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs.captureEpoch", "UTC timestamp contract differs")
    relative_path = definitions.get("relativePath", {})
    if relative_path != {
        "type": "string",
        "minLength": 1,
        "maxLength": 240,
        "pattern": RELATIVE_PATH_RE.pattern,
    }:
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs.relativePath", "relative path grammar differs")
    base64_value = definitions.get("base64Value", {})
    if base64_value.get("type") != "string" or base64_value.get("maxLength") != 344:
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs.base64Value", "base64 length differs")
    snapshot_value = definitions["snapshotRow"]["properties"]["value_utf8_b64"]["oneOf"]
    if {json.dumps(item, sort_keys=True) for item in snapshot_value} != {
        json.dumps({"$ref": "#/$defs/base64Value"}, sort_keys=True),
        json.dumps({"type": "null"}, sort_keys=True),
    }:
        fail("SCHEMA_CONTRACT_DRIFT", "schema.$defs.snapshotRow.value_utf8_b64", "base64 reference differs")
    return digest


def u32(value):
    return struct.pack(">I", value)


def u64(value):
    return struct.pack(">Q", value)


def frame_text(value):
    data = value.encode("utf-8")
    return u32(len(data)) + data


def strict_b64_decode(value, location):
    if not isinstance(value, str) or len(value) > 344:
        fail("SCHEMA_INVALID", location, "expected base64 string of at most 344 characters")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        fail("BASE64_INVALID", location, "non-canonical base64")
    if base64.b64encode(data).decode("ascii") != value:
        fail("BASE64_INVALID", location, "non-canonical base64 padding")
    return data


def b64(data):
    return base64.b64encode(data).decode("ascii")


def canonical_row_hash(row, value_bytes):
    state_byte = b"\x00" if row["state"] == "ABSENT" else b"\x01"
    value_frame = u64((1 << 64) - 1)
    if value_bytes is not None:
        value_frame = u64(len(value_bytes)) + value_bytes
    payload = b"RANKED_SELECTOR_ROW_V1\x00"
    for field in ("name", "census_row_id", "source_revision", "parser_profile"):
        payload += frame_text(row[field])
    payload += state_byte + value_frame
    normalized = canonical_json_bytes(row["normalized_semantic"])
    payload += u32(len(normalized)) + normalized
    return sha256_bytes(payload)


def canonical_map_hash(rows):
    payload = b"RANKED_SELECTOR_MAP_V1\x00" + u32(len(rows))
    for row in sorted(rows, key=lambda item: item["name"].encode("utf-8")):
        name = row["name"].encode("utf-8")
        payload += u32(len(name)) + name
        if row["state"] == "ABSENT":
            payload += b"\x00" + u64((1 << 64) - 1)
        else:
            value = base64.b64decode(row["value_utf8_b64"], validate=True)
            payload += b"\x01" + u64(len(value)) + value
    return sha256_bytes(payload)


def canonical_bundle_hash(root):
    copy = dict(root)
    copy.pop("canonical_bundle_sha256", None)
    return sha256_bytes(canonical_json_bytes(copy))


def safe_relative_path(value, location):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 240
        or not RELATIVE_PATH_RE.fullmatch(value)
    ):
        fail("PATH_ESCAPE", location, "path violates the lexical POSIX relative grammar")
    path = PurePosixPath(value)
    if str(path) != value:
        fail("PATH_ESCAPE", location, "path is not lexically canonical")
    return path


def ensure_non_symlink_path(root, relative, location):
    try:
        root_stat = os.lstat(root)
    except OSError as exc:
        fail("FILE_READ_FAILED", "bundle", str(exc))
    if stat.S_ISLNK(root_stat.st_mode):
        fail("SYMLINK_FORBIDDEN", "bundle", "bundle root is a symlink")
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            fail("DECLARED_FILE_MISSING", location, "declared path is absent")
        except OSError as exc:
            fail("FILE_READ_FAILED", location, str(exc))
        if stat.S_ISLNK(mode):
            fail("SYMLINK_FORBIDDEN", location, "path component is a symlink")
    if not stat.S_ISREG(mode):
        fail("REGULAR_FILE_REQUIRED", location, "evidence is not a regular file")


def secret_name_forbidden(name):
    return bool(SECRET_NAME_RE.search(name))


def inspect_value_safety(value_bytes, location, subject="selector value"):
    try:
        value = value_bytes.decode("utf-8")
    except UnicodeDecodeError:
        fail("VALUE_UTF8_INVALID", location, f"{subject} is not UTF-8")
    if len(value_bytes) > 256 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        fail("SECRET_VALUE_FORBIDDEN", location, f"unsafe {subject} control bytes or excessive length")
    if value.strip().lower() in REDACTION_VALUES:
        fail("REDACTION_PLACEHOLDER_FORBIDDEN", location, "redaction marker is evidence")
    token_pattern = re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}")
    if token_pattern.search(value) or re.search(r"eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}", value):
        fail("SECRET_VALUE_FORBIDDEN", location, f"credential-shaped {subject}")
    return value


def require_process_metadata(value, location):
    require_metadata(value, location)
    inspect_value_safety(value.encode("utf-8"), location, "process metadata")


def normalize_value(profile, value, location):
    if profile == "bool_exact_1_v1":
        return value == "1"
    if profile == "bool_nonzero_v1":
        try:
            return int(value, 10) != 0
        except ValueError:
            fail("SELECTOR_VALUE_INVALID", location, "expected base-10 integer boolean")
    if profile == "int_v1":
        try:
            return int(value, 10)
        except ValueError:
            fail("SELECTOR_VALUE_INVALID", location, "expected base-10 integer")
    if profile == "enum_identity_v1":
        return value
    fail("PARSER_PROFILE_UNKNOWN", location, profile)


def validate_root_shape(root, expectations):
    exact_object(root, ROOT_KEYS, "attestation")
    exact_object(expectations, EXPECTATION_KEYS, "expectations")
    require_schema_version(root["schema_version"], "schema_version")
    require_schema_version(expectations["schema_version"], "expectations.schema_version")
    for location, target in (
        ("static_resume_target", root["static_resume_target"]),
        ("expectations.static_resume_target", expectations["static_resume_target"]),
    ):
        exact_object(target, STATIC_RESUME_TARGET_KEYS, location)
        if target != STATIC_RESUME_TARGET:
            fail("STATIC_RESUME_TARGET_MISMATCH", location, "PR #670 frozen audit/base identity differs")
    for container_name, container in (
        ("audited_source_revisions", root["audited_source_revisions"]),
        ("selector_census_sha256", root["selector_census_sha256"]),
        ("expectations.audited_source_revisions", expectations["audited_source_revisions"]),
        ("expectations.selector_census_sha256", expectations["selector_census_sha256"]),
    ):
        exact_object(container, {"current", "pinned"}, container_name)
    for role in ("current", "pinned"):
        require_git_sha(root["audited_source_revisions"][role], f"audited_source_revisions.{role}")
        require_git_sha(expectations["audited_source_revisions"][role], f"expectations.audited_source_revisions.{role}")
        require_sha256(root["selector_census_sha256"][role], f"selector_census_sha256.{role}")
        require_sha256(expectations["selector_census_sha256"][role], f"expectations.selector_census_sha256.{role}")
    if root["audited_source_revisions"] != {
        "current": STATIC_RESUME_TARGET["current_source_revision"],
        "pinned": STATIC_RESUME_TARGET["pinned_source_revision"],
    }:
        fail("STATIC_RESUME_TARGET_MISMATCH", "audited_source_revisions", "source revisions differ from frozen target")
    require_sha256(root["workflow_sha256"], "workflow_sha256")
    require_sha256(expectations["workflow_sha256"], "expectations.workflow_sha256")
    for field in ("ranked_job_id", "ranked_run_id", "host_class", "trusted_collector_id"):
        require_process_metadata(root[field], field)
        require_process_metadata(expectations[field], f"expectations.{field}")
    require_capture_epoch(root["capture_epoch"], "capture_epoch")
    require_capture_epoch(expectations["capture_epoch"], "expectations.capture_epoch")
    for location, digest in (
        ("installed_authority_bundle_digest", root["installed_authority_bundle_digest"]),
        ("expectations.installed_authority_bundle_digest", expectations["installed_authority_bundle_digest"]),
    ):
        if digest is not None:
            require_sha256(digest, location)
    require_sha256(root["canonical_bundle_sha256"], "canonical_bundle_sha256")
    require_sha256(expectations["canonical_bundle_sha256"], "expectations.canonical_bundle_sha256")
    exact_object(root["censuses"], {"current", "pinned"}, "censuses")
    exact_object(root["comparison_intent"], {"kind", "policy_id"}, "comparison_intent")
    intent = root["comparison_intent"]
    if intent["kind"] not in {"all_selectors_absent", "intentional_identical_explicit_map"}:
        fail("SCHEMA_INVALID", "comparison_intent.kind", "unknown comparison intent")
    if intent["policy_id"] is not None:
        require_metadata(intent["policy_id"], "comparison_intent.policy_id")
    require_list(root["revision_only_policy"], "revision_only_policy")
    require_list(root["phases"], "phases")
    require_list(root["manifest"], "manifest")


def validate_trust_binding(root, expectations):
    if root["static_resume_target"] != expectations["static_resume_target"]:
        fail("STATIC_RESUME_TARGET_MISMATCH", "static_resume_target", "trusted target differs")
    if root["audited_source_revisions"] != expectations["audited_source_revisions"]:
        fail("SOURCE_REVISION_MISMATCH", "audited_source_revisions", "trusted revisions differ")
    if root["workflow_sha256"] != expectations["workflow_sha256"]:
        fail("WORKFLOW_DIGEST_MISMATCH", "workflow_sha256", "trusted workflow differs")
    for role, code in (("current", "CURRENT_CENSUS_DIGEST_MISMATCH"), ("pinned", "PINNED_CENSUS_DIGEST_MISMATCH")):
        if root["selector_census_sha256"][role] != expectations["selector_census_sha256"][role]:
            fail(code, f"selector_census_sha256.{role}", "trusted census digest differs")
    for field in ("ranked_job_id", "ranked_run_id", "host_class", "trusted_collector_id"):
        if root[field] != expectations[field]:
            fail("TRUSTED_METADATA_MISMATCH", field, "trusted expectation differs")
    if root["capture_epoch"] != expectations["capture_epoch"]:
        fail("CAPTURE_EPOCH_MISMATCH", "capture_epoch", "trusted epoch differs")
    if root["installed_authority_bundle_digest"] != expectations["installed_authority_bundle_digest"]:
        fail("AUTHORITY_DIGEST_MISMATCH", "installed_authority_bundle_digest", "trusted foreign authority digest differs")
    if root["canonical_bundle_sha256"] != expectations["canonical_bundle_sha256"]:
        fail("TRUSTED_BUNDLE_DIGEST_MISMATCH", "canonical_bundle_sha256", "trusted captured bundle differs")


def validate_policy_shapes(root):
    policies = set()
    for index, rule in enumerate(root["revision_only_policy"]):
        location = f"revision_only_policy[{index}]"
        exact_object(rule, POLICY_KEYS, location)
        key = require_selector_name(rule["key"], f"{location}.key")
        if key in policies:
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.key", "duplicate rule")
        policies.add(key)
        present = rule["present_in_revision"]
        missing = rule["missing_from_revision"]
        if present not in {"current", "pinned"} or missing not in {"current", "pinned"} or present == missing:
            fail("UNSUPPORTED_REVISION_POLICY", location, "revision roles are not complementary")
        if rule["reason_code"] != "REVISION_ONLY_NO_CONSUMER":
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.reason_code", str(rule["reason_code"]))
        if rule["allowed_state"] not in {"ABSENT", "VALUE"}:
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.allowed_state", str(rule["allowed_state"]))
        if rule["allowed_value_sha256"] is not None:
            require_sha256(rule["allowed_value_sha256"], f"{location}.allowed_value_sha256")
        require_metadata(rule["justification"], f"{location}.justification")


def validate_phases(root):
    phases = root["phases"]
    if len(phases) != 4:
        fail("PHASE_SET_MISMATCH", "phases", "exactly four process classes are required")
    names = []
    spawn_edges = set()
    for index, phase in enumerate(phases):
        location = f"phases[{index}]"
        exact_object(phase, PHASE_KEYS, location)
        name = require_string(phase["process_class"], f"{location}.process_class")
        if name in names:
            fail("DUPLICATE_PHASE", f"{location}.process_class", name)
        names.append(name)
        if name not in PHASE_ROLES:
            fail("PHASE_SET_MISMATCH", f"{location}.process_class", name)
        if phase["source_revision_role"] != PHASE_ROLES[name]:
            fail("SOURCE_REVISION_MISMATCH", f"{location}.source_revision_role", name)
        require_metadata(phase["spawn_edge_id"], f"{location}.spawn_edge_id")
        if phase["spawn_edge_id"] in spawn_edges:
            fail("DUPLICATE_SPAWN_EDGE", f"{location}.spawn_edge_id", phase["spawn_edge_id"])
        spawn_edges.add(phase["spawn_edge_id"])
        for stage in ("parent_snapshot", "worker_snapshot"):
            value = phase[stage]
            if value is not None:
                safe_relative_path(value, f"{location}.{stage}")
    if tuple(names) != PHASES:
        fail("PHASE_ORDER_MISMATCH", "phases", f"expected {list(PHASES)}")
    return {phase["process_class"]: phase for phase in phases}


def expected_artifact_roles(root, phases):
    roles = {}
    for role in ("current", "pinned"):
        path = root["censuses"][role]
        if path is not None:
            safe_relative_path(path, f"censuses.{role}")
            roles[f"{role}_census"] = path
    for name in PHASES:
        phase = phases[name]
        for property_name, suffix in (
            ("parent_snapshot", "parent_snapshot"),
            ("worker_snapshot", "worker_snapshot"),
        ):
            path = phase[property_name]
            if path is not None:
                roles[f"{name}.{suffix}"] = path
    return roles


def validate_manifest_and_files(bundle, root, phases):
    manifest_by_role = {}
    manifest_paths = set()
    for index, entry in enumerate(root["manifest"]):
        location = f"manifest[{index}]"
        exact_object(entry, MANIFEST_KEYS, location)
        require_metadata(entry["role"], f"{location}.role")
        relative = safe_relative_path(entry["path"], f"{location}.path")
        if entry["role"] in manifest_by_role:
            fail("DUPLICATE_MANIFEST_ROLE", f"{location}.role", entry["role"])
        if entry["path"] in manifest_paths:
            fail("DUPLICATE_MANIFEST_PATH", f"{location}.path", entry["path"])
        manifest_by_role[entry["role"]] = entry
        manifest_paths.add(entry["path"])
        if not isinstance(entry["byte_size"], int) or isinstance(entry["byte_size"], bool):
            fail("SCHEMA_INVALID", f"{location}.byte_size", "expected integer")
        if not 1 <= entry["byte_size"] <= 16 * 1024 * 1024:
            fail("SCHEMA_INVALID", f"{location}.byte_size", "size outside contract")
        require_sha256(entry["sha256"], f"{location}.sha256")
        ensure_non_symlink_path(bundle, relative, location)
    expected = expected_artifact_roles(root, phases)
    if set(manifest_by_role) != set(expected):
        missing = sorted(set(expected) - set(manifest_by_role))
        extra = sorted(set(manifest_by_role) - set(expected))
        fail("MANIFEST_ROLE_SET_MISMATCH", "manifest", f"missing={missing}, extra={extra}")
    for role, path in expected.items():
        if manifest_by_role[role]["path"] != path:
            fail("MANIFEST_REFERENCE_MISMATCH", f"manifest.{role}", "reference path differs")
    actual_files = set()
    for directory, dirnames, filenames in os.walk(bundle, followlinks=False):
        directory_path = Path(directory)
        for dirname in sorted(dirnames):
            candidate = directory_path / dirname
            if candidate.is_symlink():
                relative = candidate.relative_to(bundle).as_posix()
                fail("SYMLINK_FORBIDDEN", relative, "directory is a symlink")
        for filename in sorted(filenames):
            candidate = directory_path / filename
            relative = candidate.relative_to(bundle).as_posix()
            if candidate.is_symlink():
                fail("SYMLINK_FORBIDDEN", relative, "file is a symlink")
            if relative != "attestation.json":
                actual_files.add(relative)
    undeclared = sorted(actual_files - manifest_paths)
    if undeclared:
        fail("UNDECLARED_FILE", undeclared[0], "physical file is outside the manifest")
    missing = sorted(manifest_paths - actual_files)
    if missing:
        fail("DECLARED_FILE_MISSING", missing[0], "manifest file is absent")
    for role in sorted(manifest_by_role):
        entry = manifest_by_role[role]
        data = (bundle / PurePosixPath(entry["path"])).read_bytes()
        digest = sha256_bytes(data)
        if digest != entry["sha256"]:
            fail("ARTIFACT_HASH_MISMATCH", entry["path"], f"role={role}")
        if len(data) != entry["byte_size"]:
            fail("ARTIFACT_SIZE_MISMATCH", entry["path"], f"role={role}")
    expected_bundle_hash = canonical_bundle_hash(root)
    if expected_bundle_hash != root["canonical_bundle_sha256"]:
        fail("CANONICAL_BUNDLE_HASH_MISMATCH", "canonical_bundle_sha256", "root framing differs")
    return manifest_by_role


def first_missing_reference(root, phases):
    missing = []
    if root["installed_authority_bundle_digest"] is None:
        missing.append("installed_authority_bundle_digest")
    for role in ("current", "pinned"):
        if root["censuses"][role] is None:
            missing.append(f"{role}.census")
    for name in PHASES:
        phase = phases[name]
        for property_name in ("parent_snapshot", "worker_snapshot"):
            if phase[property_name] is None:
                missing.append(f"{name}.{property_name}")
    return missing


def validate_census(bundle, root, role):
    relative = root["censuses"][role]
    location = f"censuses.{role}"
    data = (bundle / PurePosixPath(relative)).read_bytes()
    digest = sha256_bytes(data)
    code = "CURRENT_CENSUS_DIGEST_MISMATCH" if role == "current" else "PINNED_CENSUS_DIGEST_MISMATCH"
    if digest != root["selector_census_sha256"][role]:
        fail(code, location, "physical census digest differs")
    census = strict_load_canonical_bytes(data, relative)
    exact_object(census, CENSUS_KEYS, relative)
    require_schema_version(census["schema_version"], f"{relative}.schema_version")
    if census["revision_role"] != role:
        fail("SCHEMA_INVALID", f"{relative}.revision_role", "revision role differs")
    expected_revision = root["audited_source_revisions"][role]
    if census["source_revision"] != expected_revision:
        fail("SOURCE_REVISION_MISMATCH", f"{relative}.source_revision", role)
    require_sha256(census["consumer_inventory_sha256"], f"{relative}.consumer_inventory_sha256")
    rows = require_list(census["rows"], f"{relative}.rows")
    if not rows:
        fail("SCHEMA_INVALID", f"{relative}.rows", "empty selector census")
    result = {}
    ids = set()
    ordered_names = []
    for index, row in enumerate(rows):
        row_location = f"{relative}.rows[{index}]"
        exact_object(row, CENSUS_ROW_KEYS, row_location)
        name = require_selector_name(row["name"], f"{row_location}.name")
        require_metadata(row["row_id"], f"{row_location}.row_id")
        require_metadata(row["source_locator"], f"{row_location}.source_locator")
        if name in result or row["row_id"] in ids:
            fail("DUPLICATE_SELECTOR", row_location, name)
        if row["parser_profile"] not in PARSER_PROFILES:
            fail("PARSER_PROFILE_UNKNOWN", f"{row_location}.parser_profile", str(row["parser_profile"]))
        allowed = require_list(row["allowed_values_utf8_b64"], f"{row_location}.allowed_values_utf8_b64")
        if not allowed or len(allowed) != len(set(allowed)):
            fail("SCHEMA_INVALID", f"{row_location}.allowed_values_utf8_b64", "empty or duplicate values")
        allowed_bytes = []
        for allowed_index, encoded in enumerate(allowed):
            value_bytes = strict_b64_decode(encoded, f"{row_location}.allowed_values_utf8_b64[{allowed_index}]")
            value = inspect_value_safety(value_bytes, f"{row_location}.allowed_values_utf8_b64[{allowed_index}]")
            normalize_value(row["parser_profile"], value, row_location)
            allowed_bytes.append(value_bytes)
        if not isinstance(row["absent_normalized"], (bool, int, str)):
            fail("SCHEMA_INVALID", f"{row_location}.absent_normalized", "unsupported semantic type")
        result[name] = {**row, "allowed_bytes": allowed_bytes}
        ids.add(row["row_id"])
        ordered_names.append(name)
    if ordered_names != sorted(ordered_names, key=lambda item: item.encode("utf-8")):
        fail("CENSUS_ORDER_INVALID", f"{relative}.rows", "rows must be sorted by UTF-8 name")
    return result


def validate_snapshot_row(row, census_row, revision, location):
    exact_object(row, SNAPSHOT_ROW_KEYS, location)
    name = require_selector_name(row["name"], f"{location}.name")
    if census_row is None:
        fail("UNKNOWN_SELECTOR", f"{location}.name", name)
    if row["census_row_id"] != census_row["row_id"]:
        fail("CENSUS_ROW_ID_MISMATCH", f"{location}.census_row_id", name)
    if row["source_revision"] != revision:
        fail("SOURCE_REVISION_MISMATCH", f"{location}.source_revision", name)
    if row["parser_profile"] != census_row["parser_profile"]:
        fail("PARSER_PROFILE_MISMATCH", f"{location}.parser_profile", name)
    if row["state"] not in {"ABSENT", "VALUE"}:
        fail("SCHEMA_INVALID", f"{location}.state", "expected ABSENT or VALUE")
    value_bytes = None
    if row["state"] == "ABSENT":
        if row["value_utf8_b64"] is not None:
            fail("ABSENCE_ENCODING_INVALID", f"{location}.value_utf8_b64", name)
        expected_semantic = census_row["absent_normalized"]
    else:
        value_bytes = strict_b64_decode(row["value_utf8_b64"], f"{location}.value_utf8_b64")
        value = inspect_value_safety(value_bytes, f"{location}.value_utf8_b64")
        if value_bytes not in census_row["allowed_bytes"]:
            fail("SELECTOR_VALUE_NOT_ALLOWED", f"{location}.value_utf8_b64", name)
        expected_semantic = normalize_value(row["parser_profile"], value, location)
    if type(row["normalized_semantic"]) is not type(expected_semantic) or row["normalized_semantic"] != expected_semantic:
        fail("NORMALIZED_SEMANTIC_MISMATCH", f"{location}.normalized_semantic", name)
    require_sha256(row["canonical_row_sha256"], f"{location}.canonical_row_sha256")
    if canonical_row_hash(row, value_bytes) != row["canonical_row_sha256"]:
        fail("CANONICAL_ROW_HASH_MISMATCH", f"{location}.canonical_row_sha256", name)
    return {"state": row["state"], "value_bytes": value_bytes, "semantic": expected_semantic}


def validate_snapshot(bundle, root, phase, stage, census, parent_names=None):
    relative = phase[f"{stage}_snapshot"]
    location = f"{phase['process_class']}.{stage}_snapshot"
    snapshot = strict_load_canonical_file(bundle / PurePosixPath(relative), relative)
    exact_object(snapshot, SNAPSHOT_KEYS, relative)
    require_schema_version(snapshot["schema_version"], f"{relative}.schema_version")
    if snapshot["process_class"] != phase["process_class"] or snapshot["stage"] != stage:
        fail("SNAPSHOT_IDENTITY_MISMATCH", relative, location)
    role = phase["source_revision_role"]
    revision = root["audited_source_revisions"][role]
    if snapshot["source_revision"] != revision:
        fail("SOURCE_REVISION_MISMATCH", f"{relative}.source_revision", location)
    if snapshot["census_sha256"] != root["selector_census_sha256"][role]:
        fail("SNAPSHOT_CENSUS_MISMATCH", f"{relative}.census_sha256", location)
    if snapshot["spawn_edge_id"] != phase["spawn_edge_id"]:
        fail("SPAWN_EDGE_MISMATCH", f"{relative}.spawn_edge_id", location)
    require_capture_epoch(snapshot["capture_epoch"], f"{relative}.capture_epoch")
    if snapshot["capture_epoch"] != root["capture_epoch"]:
        fail("CAPTURE_EPOCH_MISMATCH", f"{relative}.capture_epoch", location)
    rows = require_list(snapshot["rows"], f"{relative}.rows")
    if not rows:
        fail("SCHEMA_INVALID", f"{relative}.rows", "empty selector snapshot")
    names = []
    for index, row in enumerate(rows):
        row_location = f"{relative}.rows[{index}]"
        exact_object(row, SNAPSHOT_ROW_KEYS, row_location)
        names.append(require_selector_name(row["name"], f"{row_location}.name"))
    if len(names) != len(set(names)):
        fail("DUPLICATE_SELECTOR", f"{relative}.rows", "duplicate selector name")
    if stage == "worker" and parent_names is not None:
        additions = sorted(set(names) - set(parent_names))
        if additions:
            fail("UNAUTHORIZED_WORKER_ADDITION", f"{relative}.rows", additions[0])
    unknown = sorted(name for name in set(names) if name not in census)
    if unknown:
        fail("UNKNOWN_SELECTOR", f"{relative}.rows", str(unknown[0]))
    if set(names) != set(census):
        fail("SELECTOR_ROW_SET_MISMATCH", f"{relative}.rows", "omission is not absence")
    expected_order = sorted(names, key=lambda item: item.encode("utf-8"))
    if names != expected_order:
        fail("SNAPSHOT_ORDER_INVALID", f"{relative}.rows", "rows must be sorted by UTF-8 name")
    selector_map = {}
    for index, row in enumerate(rows):
        selector_map[row["name"]] = validate_snapshot_row(
            row,
            census.get(row["name"]),
            revision,
            f"{relative}.rows[{index}]",
        )
    if stage == "parent":
        if snapshot["forced_runtime_worker"] is not None:
            fail("FORCED_RUNTIME_WORKER_UNEXPECTED", f"{relative}.forced_runtime_worker", location)
    else:
        forced = snapshot["forced_runtime_worker"]
        if forced is None:
            fail("FORCED_RUNTIME_WORKER_MISSING", f"{relative}.forced_runtime_worker", location)
        exact_object(forced, {"name", "value_utf8_b64"}, f"{relative}.forced_runtime_worker")
        if forced != {"name": "MLXFAST_USE_RUNTIME_WORKER", "value_utf8_b64": "MA=="}:
            fail("FORCED_RUNTIME_WORKER_MISMATCH", f"{relative}.forced_runtime_worker", location)
    require_sha256(snapshot["canonical_selector_map_sha256"], f"{relative}.canonical_selector_map_sha256")
    if canonical_map_hash(rows) != snapshot["canonical_selector_map_sha256"]:
        fail("CANONICAL_MAP_HASH_MISMATCH", f"{relative}.canonical_selector_map_sha256", location)
    return snapshot, selector_map


def map_entry_equal(left, right):
    return (
        left["state"] == right["state"]
        and left["value_bytes"] == right["value_bytes"]
        and type(left["semantic"]) is type(right["semantic"])
        and left["semantic"] == right["semantic"]
    )


def compare_available_entries(key, names, phase_maps):
    available = [(name, phase_maps[name][key]) for name in names if name in phase_maps]
    if not available:
        return None
    reference = available[0][1]
    for name, entry in available[1:]:
        if not map_entry_equal(reference, entry):
            fail("CROSS_PROCESS_SELECTOR_MISMATCH", key, f"phase={name}")
    return reference


def validate_policy(root, censuses, phase_maps):
    policies = {}
    for index, rule in enumerate(root["revision_only_policy"]):
        location = f"revision_only_policy[{index}]"
        exact_object(rule, POLICY_KEYS, location)
        key = rule["key"]
        if not isinstance(key, str) or secret_name_forbidden(key):
            fail("SECRET_NAME_FORBIDDEN", f"{location}.key", str(key))
        if key in policies:
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.key", "duplicate rule")
        present = rule["present_in_revision"]
        missing = rule["missing_from_revision"]
        if present not in {"current", "pinned"} or missing not in {"current", "pinned"} or present == missing:
            fail("UNSUPPORTED_REVISION_POLICY", location, "revision roles are not complementary")
        if present in censuses and key not in censuses[present]:
            fail("UNSUPPORTED_REVISION_POLICY", location, "key is absent from declared present revision")
        if missing in censuses and key in censuses[missing]:
            fail("UNSUPPORTED_REVISION_POLICY", location, "key exists in declared missing revision")
        if rule["reason_code"] != "REVISION_ONLY_NO_CONSUMER":
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.reason_code", str(rule["reason_code"]))
        if rule["allowed_state"] not in {"ABSENT", "VALUE"}:
            fail("UNSUPPORTED_REVISION_POLICY", f"{location}.allowed_state", str(rule["allowed_state"]))
        require_metadata(rule["justification"], f"{location}.justification")
        relevant_phases = [name for name in PHASES if PHASE_ROLES[name] == present]
        actual = compare_available_entries(key, relevant_phases, phase_maps)
        if actual is not None:
            if actual["state"] != rule["allowed_state"]:
                fail("UNSUPPORTED_REVISION_POLICY", f"{location}.allowed_state", "actual state differs")
            expected_digest = None if actual["value_bytes"] is None else sha256_bytes(actual["value_bytes"])
            if rule["allowed_value_sha256"] != expected_digest:
                fail("UNSUPPORTED_REVISION_POLICY", f"{location}.allowed_value_sha256", "actual value differs")
        policies[key] = rule
    return policies


def validate_cross_process(root, censuses, phase_maps):
    for role, census in censuses.items():
        relevant = [name for name in PHASES if PHASE_ROLES[name] == role]
        for key in sorted(census):
            compare_available_entries(key, relevant, phase_maps)

    policies = validate_policy(root, censuses, phase_maps)
    if set(censuses) == {"current", "pinned"}:
        shared = set(censuses["current"]) & set(censuses["pinned"])
        for key in sorted(shared):
            compare_available_entries(key, PHASES, phase_maps)
        revision_only = set(censuses["current"]) ^ set(censuses["pinned"])
        for key in sorted(revision_only):
            present = "current" if key in censuses["current"] else "pinned"
            relevant = [name for name in PHASES if PHASE_ROLES[name] == present]
            reference = compare_available_entries(key, relevant, phase_maps)
            if reference is not None and reference["state"] == "VALUE" and key not in policies:
                fail("UNSUPPORTED_REVISION_POLICY", key, "explicit revision-only value lacks a rule")
        extra_rules = sorted(set(policies) - revision_only)
        if extra_rules:
            fail("UNSUPPORTED_REVISION_POLICY", extra_rules[0], "rule is not revision-only")

    if set(censuses) != {"current", "pinned"} or set(phase_maps) != set(PHASES):
        return None
    any_value = any(
        entry["state"] == "VALUE"
        for process_map in phase_maps.values()
        for entry in process_map.values()
    )
    intent = root["comparison_intent"]
    kind = intent["kind"]
    if any_value:
        if kind != "intentional_identical_explicit_map" or intent["policy_id"] != "REVISION_ONLY_EXACT_VALUE_V1":
            fail("COMPARISON_INTENT_MISMATCH", "comparison_intent", "explicit map policy differs")
        return "intentional_identical_explicit_map"
    if kind != "all_selectors_absent" or intent["policy_id"] is not None or policies:
        fail("COMPARISON_INTENT_MISMATCH", "comparison_intent", "absence policy differs")
    return "all_selectors_absent"


def validate_bundle(
    bundle_path,
    expectations_path,
    expected_expectations_sha256,
    schema_path=DEFAULT_SCHEMA_PATH,
):
    validate_schema_contract(schema_path)
    bundle = Path(bundle_path)
    expectations_file = Path(expectations_path)
    if bundle.is_symlink():
        fail("SYMLINK_FORBIDDEN", "bundle", "bundle root is a symlink")
    if not bundle.is_dir():
        fail("BUNDLE_MISSING", "bundle", "bundle directory is absent")
    entry = bundle / "attestation.json"
    if entry.is_symlink():
        fail("SYMLINK_FORBIDDEN", "attestation.json", "entry point is a symlink")
    root = strict_load_canonical_file(entry, "attestation.json")
    expectations = load_pinned_expectations(expectations_file, expected_expectations_sha256)
    validate_root_shape(root, expectations)
    validate_trust_binding(root, expectations)
    validate_policy_shapes(root)
    phases = validate_phases(root)
    validate_manifest_and_files(bundle, root, phases)

    censuses = {}
    for role in ("current", "pinned"):
        if root["censuses"][role] is not None:
            censuses[role] = validate_census(bundle, root, role)

    phase_maps = {}
    for name in PHASES:
        phase = phases[name]
        role = phase["source_revision_role"]
        present_stages = [stage for stage in ("parent", "worker") if phase[f"{stage}_snapshot"] is not None]
        if present_stages and role not in censuses:
            fail("SNAPSHOT_WITHOUT_CENSUS", name, f"missing {role} census")
        if not present_stages:
            continue
        snapshots = {}
        maps = {}
        for stage in present_stages:
            snapshots[stage], maps[stage] = validate_snapshot(
                bundle,
                root,
                phase,
                stage,
                censuses[role],
                parent_names=(
                    [row["name"] for row in snapshots["parent"]["rows"]]
                    if stage == "worker" and "parent" in snapshots
                    else None
                ),
            )
        if set(maps) == {"parent", "worker"}:
            for key in sorted(maps["parent"]):
                if not map_entry_equal(maps["parent"][key], maps["worker"][key]):
                    fail("PARENT_WORKER_FORWARDING_MISMATCH", f"{name}.{key}", "raw or semantic value differs")
        phase_maps[name] = maps["parent"] if "parent" in maps else maps["worker"]

    comparison = validate_cross_process(root, censuses, phase_maps)
    missing = first_missing_reference(root, phases)
    common = {
        "authorization_scope": AUTHORIZATION_SCOPE,
        "ranked_run_or_submission_authorized": False,
        "static_resume_target": STATIC_RESUME_TARGET,
    }
    if missing:
        return {
            **common,
            "classification": INCOMPLETE,
            "first_missing": missing[0],
            "missing": missing,
        }
    return {
        **common,
        "canonical_bundle_sha256": root["canonical_bundle_sha256"],
        "classification": READY,
        "comparison_intent": comparison,
        "validated_process_classes": list(PHASES),
    }


def invalid_result(exc):
    return {
        "classification": INVALID,
        "detail": exc.detail,
        "error_code": exc.code,
        "location": exc.location,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value, trailing_lf=True))


def make_census_row(row_id, name, parser, allowed, absent):
    return {
        "row_id": row_id,
        "name": name,
        "source_locator": f"synthetic/{row_id}",
        "parser_profile": parser,
        "allowed_values_utf8_b64": [b64(value.encode("utf-8")) for value in allowed],
        "absent_normalized": absent,
    }


def synthetic_constants():
    return {
        "current": STATIC_RESUME_TARGET["current_source_revision"],
        "pinned": STATIC_RESUME_TARGET["pinned_source_revision"],
        "workflow": "a" * 64,
        "authority": "b" * 64,
        "epoch": "2099-01-01T00:00:00Z",
        "job": "synthetic-ranked-job.invalid",
        "run": "synthetic-ranked-run.invalid",
        "host": "SYNTHETIC_M5_CLASS_DO_NOT_DEPLOY",
        "collector": "synthetic-collector.invalid/v1",
    }


def make_censuses(constants):
    shared = [
        make_census_row("selector-001", "DARKBLOOM_FAST_PATH", "bool_exact_1_v1", ["0", "1"], False),
        make_census_row("selector-002", "MLX_ENABLE_TF32", "bool_nonzero_v1", ["0", "1"], True),
    ]
    current_only = make_census_row(
        "selector-003",
        "DARKBLOOM_CURRENT_ONLY",
        "enum_identity_v1",
        ["auto", "balanced"],
        "auto",
    )
    current_rows = sorted(shared + [current_only], key=lambda row: row["name"].encode("utf-8"))
    pinned_rows = sorted(shared, key=lambda row: row["name"].encode("utf-8"))
    return {
        "current": {
            "schema_version": 1,
            "revision_role": "current",
            "source_revision": constants["current"],
            "consumer_inventory_sha256": "c" * 64,
            "rows": current_rows,
        },
        "pinned": {
            "schema_version": 1,
            "revision_role": "pinned",
            "source_revision": constants["pinned"],
            "consumer_inventory_sha256": "d" * 64,
            "rows": pinned_rows,
        },
    }


def make_snapshot_row(census_row, revision, state, value=None):
    if state == "ABSENT":
        encoded = None
        semantic = census_row["absent_normalized"]
        value_bytes = None
    else:
        value_bytes = value.encode("utf-8")
        encoded = b64(value_bytes)
        semantic = normalize_value(census_row["parser_profile"], value, "synthetic")
    row = {
        "name": census_row["name"],
        "census_row_id": census_row["row_id"],
        "source_revision": revision,
        "parser_profile": census_row["parser_profile"],
        "state": state,
        "value_utf8_b64": encoded,
        "normalized_semantic": semantic,
        "canonical_row_sha256": "0" * 64,
    }
    row["canonical_row_sha256"] = canonical_row_hash(row, value_bytes)
    return row


def reseal_snapshot(snapshot):
    for row in snapshot["rows"]:
        value_bytes = None
        if row["state"] == "VALUE" and isinstance(row["value_utf8_b64"], str):
            value_bytes = base64.b64decode(row["value_utf8_b64"], validate=True)
        row["canonical_row_sha256"] = canonical_row_hash(row, value_bytes)
    snapshot["rows"].sort(key=lambda row: row["name"].encode("utf-8"))
    snapshot["canonical_selector_map_sha256"] = canonical_map_hash(snapshot["rows"])


def snapshot_values(variant, census_rows):
    values = {}
    for row in census_rows:
        if variant == "all_absent":
            values[row["name"]] = ("ABSENT", None)
        elif row["name"] == "DARKBLOOM_FAST_PATH":
            values[row["name"]] = ("VALUE", "1")
        elif row["name"] == "MLX_ENABLE_TF32":
            values[row["name"]] = ("VALUE", "0")
        else:
            values[row["name"]] = ("VALUE", "balanced")
    return values


def build_synthetic_bundle(bundle, expectations_path, variant):
    constants = synthetic_constants()
    censuses = make_censuses(constants)
    census_paths = {"current": "census/current.json", "pinned": "census/pinned.json"}
    census_digests = {}
    for role in ("current", "pinned"):
        write_json(bundle / census_paths[role], censuses[role])
        census_digests[role] = sha256_bytes((bundle / census_paths[role]).read_bytes())
    phases = []
    for index, name in enumerate(PHASES, start=1):
        role = PHASE_ROLES[name]
        phase = {
            "process_class": name,
            "source_revision_role": role,
            "spawn_edge_id": f"synthetic-spawn-{index}",
            "parent_snapshot": f"snapshots/{name}.parent.json",
            "worker_snapshot": f"snapshots/{name}.worker.json",
        }
        phases.append(phase)
        values = snapshot_values(variant, censuses[role]["rows"])
        rows = [
            make_snapshot_row(row, constants[role], *values[row["name"]])
            for row in censuses[role]["rows"]
        ]
        for stage in ("parent", "worker"):
            snapshot = {
                "schema_version": 1,
                "process_class": name,
                "stage": stage,
                "source_revision": constants[role],
                "census_sha256": census_digests[role],
                "spawn_edge_id": phase["spawn_edge_id"],
                "capture_epoch": constants["epoch"],
                "rows": json.loads(json.dumps(rows)),
                "forced_runtime_worker": (
                    None
                    if stage == "parent"
                    else {"name": "MLXFAST_USE_RUNTIME_WORKER", "value_utf8_b64": "MA=="}
                ),
                "canonical_selector_map_sha256": canonical_map_hash(rows),
            }
            write_json(bundle / phase[f"{stage}_snapshot"], snapshot)
    policy = []
    intent = {"kind": "all_selectors_absent", "policy_id": None}
    if variant == "identical_explicit":
        value = b"balanced"
        policy = [{
            "key": "DARKBLOOM_CURRENT_ONLY",
            "present_in_revision": "current",
            "missing_from_revision": "pinned",
            "reason_code": "REVISION_ONLY_NO_CONSUMER",
            "allowed_state": "VALUE",
            "allowed_value_sha256": sha256_bytes(value),
            "justification": "synthetic-current-revision-only-consumer",
        }]
        intent = {
            "kind": "intentional_identical_explicit_map",
            "policy_id": "REVISION_ONLY_EXACT_VALUE_V1",
        }
    root = {
        "schema_version": 1,
        "static_resume_target": dict(STATIC_RESUME_TARGET),
        "audited_source_revisions": {"current": constants["current"], "pinned": constants["pinned"]},
        "workflow_sha256": constants["workflow"],
        "selector_census_sha256": census_digests,
        "ranked_job_id": constants["job"],
        "ranked_run_id": constants["run"],
        "host_class": constants["host"],
        "trusted_collector_id": constants["collector"],
        "capture_epoch": constants["epoch"],
        "installed_authority_bundle_digest": constants["authority"],
        "comparison_intent": intent,
        "revision_only_policy": policy,
        "censuses": census_paths,
        "phases": phases,
        "manifest": [],
        "canonical_bundle_sha256": "0" * 64,
    }
    refresh_manifest_and_root(bundle, root)
    expectations = {
        "schema_version": 1,
        "static_resume_target": dict(STATIC_RESUME_TARGET),
        "audited_source_revisions": root["audited_source_revisions"],
        "workflow_sha256": root["workflow_sha256"],
        "selector_census_sha256": root["selector_census_sha256"],
        "ranked_job_id": root["ranked_job_id"],
        "ranked_run_id": root["ranked_run_id"],
        "host_class": root["host_class"],
        "trusted_collector_id": root["trusted_collector_id"],
        "capture_epoch": root["capture_epoch"],
        "installed_authority_bundle_digest": root["installed_authority_bundle_digest"],
        "canonical_bundle_sha256": root["canonical_bundle_sha256"],
    }
    write_json(expectations_path, expectations)


def referenced_roles(root):
    roles = {}
    for role in ("current", "pinned"):
        path = root["censuses"][role]
        if path is not None:
            roles[f"{role}_census"] = path
    for phase in root["phases"]:
        name = phase["process_class"]
        for property_name in ("parent_snapshot", "worker_snapshot"):
            path = phase[property_name]
            if path is not None:
                roles[f"{name}.{property_name}"] = path
    return roles


def refresh_manifest_and_root(bundle, root):
    entries = []
    for role, relative in sorted(referenced_roles(root).items()):
        path = bundle / PurePosixPath(relative)
        data = path.read_bytes()
        entries.append({"role": role, "path": relative, "byte_size": len(data), "sha256": sha256_bytes(data)})
    root["manifest"] = entries
    root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
    write_json(bundle / "attestation.json", root)


def load_root(bundle):
    return strict_load_file(bundle / "attestation.json", "synthetic.attestation")


def load_expectations(expectations_path):
    return strict_load_file(expectations_path, "synthetic.expectations")


def sync_expected_bundle_digest(bundle, expectations_path):
    expectations = load_expectations(expectations_path)
    expectations["canonical_bundle_sha256"] = load_root(bundle)["canonical_bundle_sha256"]
    write_json(expectations_path, expectations)


def load_snapshot(bundle, relative):
    return strict_load_file(bundle / PurePosixPath(relative), f"synthetic.{relative}")


def save_snapshot_and_reseal(bundle, root, relative, snapshot):
    reseal_snapshot(snapshot)
    write_json(bundle / PurePosixPath(relative), snapshot)
    refresh_manifest_and_root(bundle, root)


def phase_by_name(root, name):
    return next(phase for phase in root["phases"] if phase["process_class"] == name)


def remove_pinned_worker(bundle, root, pinned):
    relative = pinned["worker_snapshot"]
    (bundle / PurePosixPath(relative)).unlink()
    pinned["worker_snapshot"] = None
    refresh_manifest_and_root(bundle, root)


def replace_public_parent_name(bundle, root, public, replacement):
    relative = public["parent_snapshot"]
    snapshot = load_snapshot(bundle, relative)
    snapshot["rows"][0]["name"] = replacement
    write_json(bundle / PurePosixPath(relative), snapshot)
    refresh_manifest_and_root(bundle, root)


def make_public_parent_noncanonical(bundle, root, public):
    relative = public["parent_snapshot"]
    snapshot = load_snapshot(bundle, relative)
    data = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (bundle / PurePosixPath(relative)).write_bytes(data)
    refresh_manifest_and_root(bundle, root)


def mutate_fixture(bundle, expectations_path, mutation):
    if mutation in {
        "none",
        "missing_expected_expectations_pin",
        "schema_drift",
        "trusted_bundle_digest_mismatch",
    }:
        return
    root = load_root(bundle)
    public = phase_by_name(root, "current_public_correctness")
    hidden = phase_by_name(root, "current_hidden_gates")
    pinned = phase_by_name(root, "pinned_baseline_timed")
    if mutation == "coherent_bundle_expectations_reseal_without_external_pin":
        value = "synthetic-ranked-job-resealed"
        root["ranked_job_id"] = value
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
        expectations = load_expectations(expectations_path)
        expectations["ranked_job_id"] = value
        write_json(expectations_path, expectations)
    elif mutation == "credential_shaped_process_metadata":
        leaked = "gh" + "p_" + "x" * 24
        root["ranked_job_id"] = leaked
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
        expectations = load_expectations(expectations_path)
        expectations["ranked_job_id"] = leaked
        write_json(expectations_path, expectations)
    elif mutation == "relative_path_at_rejected":
        root["censuses"]["current"] = "censuses/current@.json"
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "null_authority":
        root["installed_authority_bundle_digest"] = None
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
        expectations = load_expectations(expectations_path)
        expectations["installed_authority_bundle_digest"] = None
        write_json(expectations_path, expectations)
    elif mutation == "static_resume_target_mismatch":
        root["static_resume_target"]["frozen_environment_audit_sha256"] = "f" * 64
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "impossible_capture_date":
        root["capture_epoch"] = "2099-02-30T00:00:00Z"
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "selector_name_too_long":
        replace_public_parent_name(bundle, root, public, "DARKBLOOM_" + "A" * 160)
    elif mutation == "selector_name_wrong_type":
        replace_public_parent_name(bundle, root, public, 17)
    elif mutation == "noncanonical_snapshot_json":
        make_public_parent_noncanonical(bundle, root, public)
    elif mutation == "missing_worker_with_invalid_selector":
        remove_pinned_worker(bundle, root, pinned)
        replace_public_parent_name(bundle, root, public, "DARKBLOOM_" + "A" * 160)
    elif mutation == "missing_worker_with_noncanonical_snapshot":
        remove_pinned_worker(bundle, root, pinned)
        make_public_parent_noncanonical(bundle, root, public)
    elif mutation == "artifact_byte_hash_drift":
        path = bundle / PurePosixPath(public["parent_snapshot"])
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "artifact_size_drift":
        role = "current_public_correctness.parent_snapshot"
        next(entry for entry in root["manifest"] if entry["role"] == role)["byte_size"] += 1
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "path_escape":
        root["censuses"]["current"] = "../current.json"
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "symlink_snapshot":
        path = bundle / PurePosixPath(public["parent_snapshot"])
        path.unlink()
        path.symlink_to(Path(hidden["parent_snapshot"]).name)
    elif mutation == "duplicate_phase":
        root["phases"][1]["process_class"] = "current_public_correctness"
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "duplicate_manifest_path":
        root["manifest"][1]["path"] = root["manifest"][0]["path"]
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "current_census_digest_drift":
        root["selector_census_sha256"]["current"] = "e" * 64
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "pinned_census_digest_drift":
        root["selector_census_sha256"]["pinned"] = "e" * 64
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "source_revision_drift":
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        snapshot["source_revision"] = "3" * 40
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "implicit_omitted_selector_row":
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        snapshot["rows"].pop()
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "unknown_darkbloom_selector":
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        template = dict(snapshot["rows"][0])
        template["name"] = "DARKBLOOM_UNAUDITED_SELECTOR"
        template["census_row_id"] = "unknown-selector"
        snapshot["rows"].append(template)
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation in {
        "hidden_override_differs_from_candidate",
        "missing_plus_cross_process_mismatch",
    }:
        for stage in ("parent", "worker"):
            relative = hidden[f"{stage}_snapshot"]
            snapshot = load_snapshot(bundle, relative)
            row = next(item for item in snapshot["rows"] if item["name"] == "DARKBLOOM_FAST_PATH")
            row["value_utf8_b64"] = b64(b"0")
            row["normalized_semantic"] = False
            reseal_snapshot(snapshot)
            write_json(bundle / PurePosixPath(relative), snapshot)
        refresh_manifest_and_root(bundle, root)
        if mutation == "missing_plus_cross_process_mismatch":
            remove_pinned_worker(bundle, root, pinned)
    elif mutation == "parent_worker_value_mutation":
        relative = public["worker_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        row = next(item for item in snapshot["rows"] if item["name"] == "DARKBLOOM_FAST_PATH")
        row["value_utf8_b64"] = b64(b"0")
        row["normalized_semantic"] = False
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation in {"unauthorized_worker_addition", "credential_variable_inclusion"}:
        relative = public["worker_snapshot"] if mutation == "unauthorized_worker_addition" else public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        template = dict(snapshot["rows"][0])
        template["name"] = "DARKBLOOM_UNDECLARED" if mutation == "unauthorized_worker_addition" else "MLX_API_KEY"
        template["census_row_id"] = "synthetic-extra"
        snapshot["rows"].append(template)
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "missing_forced_runtime_worker":
        relative = public["worker_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        snapshot["forced_runtime_worker"] = None
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "canonical_framing_mutation":
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        snapshot["canonical_selector_map_sha256"] = "0" * 64
        write_json(bundle / PurePosixPath(relative), snapshot)
        refresh_manifest_and_root(bundle, root)
    elif mutation == "mixed_capture_epoch":
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        snapshot["capture_epoch"] = "2099-01-01T00:00:01Z"
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "authority_foreign_key_mismatch":
        root["installed_authority_bundle_digest"] = "f" * 64
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation == "unsupported_revision_exception":
        root["revision_only_policy"][0]["reason_code"] = "WILDCARD_EXCEPTION"
        root["canonical_bundle_sha256"] = canonical_bundle_hash(root)
        write_json(bundle / "attestation.json", root)
    elif mutation in {"secret_value_leakage", "redaction_placeholder_leakage"}:
        relative = public["parent_snapshot"]
        snapshot = load_snapshot(bundle, relative)
        row = next(item for item in snapshot["rows"] if item["name"] == "DARKBLOOM_CURRENT_ONLY")
        leaked = ("gh" + "p_" + "x" * 24) if mutation == "secret_value_leakage" else "<redacted>"
        row["value_utf8_b64"] = b64(leaked.encode("utf-8"))
        row["normalized_semantic"] = leaked
        save_snapshot_and_reseal(bundle, root, relative, snapshot)
    elif mutation == "generic_environment_dump":
        (bundle / "environment.txt").write_text("synthetic generic dump forbidden\n", encoding="utf-8")
    elif mutation == "declared_file_missing":
        (bundle / PurePosixPath(public["parent_snapshot"])).unlink()
    elif mutation == "missing_pinned_worker":
        remove_pinned_worker(bundle, root, pinned)
    else:
        raise ValueError(f"unknown mutation {mutation}")


def fixture_bytes_digest(
    bundle,
    expectations_path,
    expected_expectations_sha256,
    schema_path,
):
    payload = b"RANKED_SELECTOR_FIXTURE_BYTES_V3\x00"
    paths = sorted(path for path in bundle.rglob("*") if path.is_file() and not path.is_symlink())
    for path in paths:
        relative = f"bundle/{path.relative_to(bundle).as_posix()}".encode("utf-8")
        data = path.read_bytes()
        payload += u32(len(relative)) + relative + u64(len(data)) + data
    for path in sorted(path for path in bundle.rglob("*") if path.is_symlink()):
        relative = f"bundle-symlink/{path.relative_to(bundle).as_posix()}".encode("utf-8")
        target = os.readlink(path).encode("utf-8")
        payload += u32(len(relative)) + relative + u64(len(target)) + target
    for label, path in (
        (b"trusted-expectations.json", expectations_path),
        (b"ranked-selector-attestation.schema.json", schema_path),
    ):
        data = Path(path).read_bytes()
        payload += u32(len(label)) + label + u64(len(data)) + data
    label = b"expected-expectations-sha256"
    data = (
        b""
        if expected_expectations_sha256 is None
        else expected_expectations_sha256.encode("ascii")
    )
    payload += u32(len(label)) + label + u64(len(data)) + data
    return sha256_bytes(payload)


def execute_case(case, schema_path):
    with tempfile.TemporaryDirectory(prefix="selector-attestation-") as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        expectations = root / "trusted-expectations.json"
        case_schema = root / "ranked-selector-attestation.schema.json"
        bundle.mkdir()
        case_schema.write_bytes(Path(schema_path).read_bytes())
        build_synthetic_bundle(bundle, expectations, case["base_variant"])
        original_expectations_sha256 = sha256_bytes(expectations.read_bytes())
        mutate_fixture(bundle, expectations, case["mutation"])
        sync_expected_bundle_digest(bundle, expectations)
        if case["mutation"] == "trusted_bundle_digest_mismatch":
            trusted = load_expectations(expectations)
            trusted["canonical_bundle_sha256"] = "f" * 64
            write_json(expectations, trusted)
        elif case["mutation"] == "schema_drift":
            schema = strict_load_file(case_schema, "synthetic.schema")
            schema["$defs"]["selectorName"]["maxLength"] += 1
            write_json(case_schema, schema)

        if case["mutation"] == "missing_expected_expectations_pin":
            expected_expectations_sha256 = None
        elif case["mutation"] == "coherent_bundle_expectations_reseal_without_external_pin":
            expected_expectations_sha256 = original_expectations_sha256
        else:
            expected_expectations_sha256 = sha256_bytes(expectations.read_bytes())
        bytes_digest = fixture_bytes_digest(
            bundle,
            expectations,
            expected_expectations_sha256,
            case_schema,
        )
        try:
            result = validate_bundle(
                bundle,
                expectations,
                expected_expectations_sha256,
                case_schema,
            )
        except ValidationFailure as exc:
            result = invalid_result(exc)
        summary = {
            "classification": result["classification"],
            "fixture_bytes_sha256": bytes_digest,
            "id": case["id"],
        }
        for field in ("comparison_intent", "first_missing", "error_code"):
            if field in result:
                summary[field] = result[field]
        return summary


def assert_case_result(case, result):
    expected_classification = case.get("expected_classification", INVALID)
    if result["classification"] != expected_classification:
        raise AssertionError(
            f"{case['id']}: expected {expected_classification}, got {result}"
        )
    for expected_field, actual_field in (
        ("expected_comparison", "comparison_intent"),
        ("expected_first_missing", "first_missing"),
        ("expected_error", "error_code"),
    ):
        if expected_field in case and result.get(actual_field) != case[expected_field]:
            raise AssertionError(
                f"{case['id']}: expected {actual_field}={case[expected_field]}, got {result}"
            )


def run_self_test(fixtures_path, schema_path=DEFAULT_SCHEMA_PATH):
    schema_digest = validate_schema_contract(schema_path)
    fixture_bytes = Path(fixtures_path).read_bytes()
    fixtures = strict_load_bytes(fixture_bytes, str(fixtures_path))
    if fixtures.get("schema_version") != 1 or fixtures.get("synthetic_only") is not True:
        raise AssertionError("fixture catalog must be synthetic schema version 1")
    runs = fixtures.get("determinism", {}).get("runs")
    if runs != 2 or fixtures["determinism"].get("require_byte_identical_results") is not True:
        raise AssertionError("fixture catalog must require two byte-identical runs")
    cases = fixtures["positive_cases"] + fixtures["negative_controls"]
    outputs = []
    for _ in range(runs):
        run_results = []
        for case in cases:
            result = execute_case(case, schema_path)
            assert_case_result(case, result)
            run_results.append(result)
        outputs.append(canonical_json_bytes(run_results))
    if outputs[0] != outputs[1]:
        raise AssertionError("determinism runs differed byte-for-byte")
    results = json.loads(outputs[0].decode("utf-8"))
    return {
        "case_count": len(cases),
        "case_results_sha256": sha256_bytes(outputs[0]),
        "classification": "SELF_TEST_PASS",
        "determinism_runs": runs,
        "fixture_catalog_sha256": sha256_bytes(fixture_bytes),
        "schema_sha256": schema_digest,
        "results": results,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Validate prospective ranked selector effective-environment attestation bundles."
    )
    parser.add_argument("--bundle", help="bundle directory containing attestation.json")
    parser.add_argument("--expectations", help="separately trusted expectations JSON")
    parser.add_argument(
        "--expected-expectations-sha256",
        help="verifier-owned SHA-256 of trusted expectations bytes",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="pinned ranked selector attestation JSON Schema",
    )
    parser.add_argument("--self-test", action="store_true", help="run synthetic positive and negative controls")
    parser.add_argument(
        "--fixtures",
        default=str(Path(__file__).with_name("ranked_selector_attestation_fixtures.json")),
        help="synthetic fixture catalog used by --self-test",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        if args.bundle or args.expectations or args.expected_expectations_sha256:
            parser.error(
                "--self-test cannot be combined with --bundle, --expectations, "
                "or --expected-expectations-sha256"
            )
    elif not all(
        (args.bundle, args.expectations, args.expected_expectations_sha256)
    ):
        parser.error(
            "--bundle, --expectations, and --expected-expectations-sha256 "
            "are required unless --self-test is used"
        )
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.self_test:
            result = run_self_test(args.fixtures, args.schema)
            exit_code = 0
        else:
            result = validate_bundle(
                args.bundle,
                args.expectations,
                args.expected_expectations_sha256,
                args.schema,
            )
            exit_code = 0 if result["classification"] == READY else 2
    except ValidationFailure as exc:
        result = invalid_result(exc)
        exit_code = 1
    except (AssertionError, OSError, ValueError) as exc:
        result = {
            "classification": INVALID,
            "detail": str(exc),
            "error_code": "SELF_TEST_FAILURE" if args.self_test else "VALIDATOR_INTERNAL_ERROR",
            "location": "self_test" if args.self_test else "validator",
        }
        exit_code = 1
    sys.stdout.buffer.write(canonical_json_bytes(result, trailing_lf=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
