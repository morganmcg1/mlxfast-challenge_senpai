#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "ranked-authority-evidence-bundle/v4"
FIXTURE_VERSION = "ranked-authority-evidence-fixtures/v5"
TRUST_SCHEMA_VERSION = "ranked-authority-external-trust/v2"
AUTHORITY_CONTRACT_VERSION = "pr671-ranked-installed-authority/v4"
SCHEMA_PATH = Path(__file__).with_name("ranked_authority_evidence_bundle.schema.json")
MANDATORY_ROLES = {
    "workflow_file",
    "installation_recipe",
    "bench_exec",
    "measure_job",
    "reaper",
    "worker_launcher",
    "runtime_worker",
    "worker_sandbox_profile_generator",
    "profile_generator_input",
    "worker_sandbox_profile",
}
RANKED_SCOPE = {
    "assignment_pr": 671,
    "audit_path": "research/ranked-weight-load-provenance-audit.md",
    "audit_terminal": "RANKED_WEIGHT_PROVENANCE_INDETERMINATE",
    "first_unavailable_path": "/opt/bench/bench-exec.sh",
    "audited_base_sha": "5593d8f4a394023e83dfbfe11ef01fa01a5b7f15",
    "workflow_path": ".github/workflows/benchmark.yml",
    "workflow_blob_sha": "cd045c1b29009a041acb70360c2907a2623a146a",
    "workflow_file_sha256": "a73f67d041e780371b8bae45de1f94f0649fb9e09fe846e4e5b79062ae6d2e18",
    "stopped_edge": "trusted runner hash of transformed weight tree -> bench-exec-mediated reaper / worker launch / sandbox injection -> worker's independent pathname opens during the load epoch",
}
KNOWN_RANKED_PATHS = {
    "bench_exec": "/opt/bench/bench-exec.sh",
    "measure_job": "/opt/bench-runner/measure-job.sh",
}
EXPECTED_ACTORS = {
    "controller": None,
    "bench": "controller",
    "worker": "bench",
}
EXPECTED_PHASE_ACTORS = {
    "transform": "bench",
    "trusted_hash": "bench",
    "reaper": "bench",
    "worker_spawn": "bench",
    "worker_load_epoch": "worker",
}
EXPECTED_EVENTS = [
    ("transform", "transform", "bench", "bench_exec"),
    ("trusted-hash", "trusted_hash", "bench", "bench_exec"),
    ("reaper", "reaper", "bench", "bench_exec"),
    ("profile-generated", "profile_generated", "bench", "worker_sandbox_profile_generator"),
    ("sandbox-injected", "sandbox_injected", "bench", "worker_launcher"),
    ("worker-spawn", "worker_spawn", "bench", "measure_job"),
    ("load-start", "load_start", "worker", "runtime_worker"),
    ("load-end", "load_end", "worker", "runtime_worker"),
]
REQUIRED_EVENTS = [item[1] for item in EXPECTED_EVENTS]
REQUIRED_EVENT_EDGES = [
    ("transform", "trusted-hash", "happens_before"),
    ("trusted-hash", "reaper", "happens_before"),
    ("reaper", "profile-generated", "happens_before"),
    ("profile-generated", "sandbox-injected", "sandbox_injection"),
    ("sandbox-injected", "worker-spawn", "spawn"),
    ("worker-spawn", "load-start", "spawn"),
    ("load-start", "load-end", "load_epoch_bounds"),
]
EXPECTED_CAPABILITIES = {
    "transform": ("bench", True, True, True, True),
    "trusted_hash": ("bench", True, False, False, False),
    "reaper": ("bench", False, False, False, False),
    "worker_spawn": ("bench", True, False, False, False),
    "worker_load_epoch": ("worker", True, False, False, False),
}
SECRET_KEY_PATTERN = re.compile(r"(?:^|_)(?:api_?key|credential|password|private_?key|secret|token)(?:$|_)", re.IGNORECASE)
ZERO_SHA256 = "0" * 64


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest_value(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_file(path):
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_acl(text):
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def observed_acl(path):
    commands = (["ls", "-lde", str(path)], ["getfacl", "-cp", str(path)])
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            continue
        lines = result.stdout.splitlines()
        if command[0] == "ls":
            lines = lines[1:]
        return normalize_acl("\n".join(lines))
    return ""


def filesystem_type(path):
    result = subprocess.run(["mount"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return "unknown"
    resolved = str(path.resolve())
    best_match = (-1, "unknown")
    for line in result.stdout.splitlines():
        if " on " not in line:
            continue
        remainder = line.split(" on ", 1)[1]
        if " type " in remainder:
            mountpoint, details = remainder.rsplit(" type ", 1)
            filesystem = details.split(" ", 1)[0]
        elif " (" in remainder:
            mountpoint, details = remainder.rsplit(" (", 1)
            filesystem = details.rstrip(")").split(",", 1)[0]
        else:
            continue
        mountpoint = mountpoint.replace("\\040", " ")
        prefix = mountpoint.rstrip("/") + "/"
        if (resolved == mountpoint or resolved.startswith(prefix)) and len(mountpoint) > best_match[0]:
            best_match = (len(mountpoint), filesystem)
    return best_match[1]


def flag_names(raw):
    names = []
    for name in (
        "UF_NODUMP",
        "UF_IMMUTABLE",
        "UF_APPEND",
        "UF_OPAQUE",
        "UF_HIDDEN",
        "SF_ARCHIVED",
        "SF_IMMUTABLE",
        "SF_APPEND",
    ):
        value = getattr(stat, name, 0)
        if value and raw & value:
            names.append(name)
    return names


def physical_metadata(path, mount_id):
    info = path.lstat()
    acl = observed_acl(path)
    raw_flags = getattr(info, "st_flags", 0)
    return {
        "owner_uid": info.st_uid,
        "owner_gid": info.st_gid,
        "mode": f"0{stat.S_IMODE(info.st_mode):03o}",
        "acl": {"normalized_text": acl, "sha256": hashlib.sha256(acl.encode()).hexdigest()},
        "flags": {"raw": raw_flags, "names": flag_names(raw_flags)},
        "link_count": info.st_nlink,
        "symlink": stat.S_ISLNK(info.st_mode),
        "device_id": info.st_dev,
        "filesystem": filesystem_type(path),
        "mount_id": mount_id,
    }


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_bundle_path(root, relative):
    if not isinstance(relative, str) or not relative:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        return None
    candidate = root.joinpath(*pure.parts)
    try:
        resolved_parent = candidate.parent.resolve(strict=False)
        resolved_parent.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def error(code, path, message):
    return {"code": code, "path": path, "message": message}


def resolve_schema_ref(root_schema, reference):
    if not reference.startswith("#/"):
        raise ValueError(f"unsupported schema reference: {reference}")
    value = root_schema
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def schema_type_matches(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_schema_instance(value, schema, root_schema, path="$", errors=None):
    errors = errors if errors is not None else []
    if "$ref" in schema:
        return validate_schema_instance(value, resolve_schema_ref(root_schema, schema["$ref"]), root_schema, path, errors)
    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            branch_errors = []
            validate_schema_instance(value, branch, root_schema, path, branch_errors)
            matches += not branch_errors
        if matches != 1:
            errors.append(error("SCHEMA_ONE_OF", path, "value must match exactly one allowed schema branch"))
        return errors

    expected_type = schema.get("type")
    if expected_type is not None:
        accepted = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(schema_type_matches(value, item) for item in accepted):
            errors.append(error("SCHEMA_TYPE", path, f"value must have type {expected_type}"))
            return errors
    if "const" in schema and value != schema["const"]:
        errors.append(error("SCHEMA_CONST", path, "value does not match the committed constant"))
    if "enum" in schema and value not in schema["enum"]:
        errors.append(error("SCHEMA_ENUM", path, "value is outside the committed enumeration"))

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(error("SCHEMA_REQUIRED", f"{path}.{name}", "required property is absent"))
        if schema.get("additionalProperties") is False:
            for name in sorted(set(value) - set(properties)):
                errors.append(error("SCHEMA_ADDITIONAL_PROPERTY", f"{path}.{name}", "undeclared property is forbidden"))
        for name, child in value.items():
            if name in properties:
                validate_schema_instance(child, properties[name], root_schema, f"{path}.{name}", errors)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(error("SCHEMA_MIN_ITEMS", path, "array is shorter than the committed minimum"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(error("SCHEMA_MAX_ITEMS", path, "array is longer than the committed maximum"))
        if schema.get("uniqueItems"):
            serialized = [canonical_bytes(item) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append(error("SCHEMA_UNIQUE_ITEMS", path, "array items must be unique"))
        item_schema = schema.get("items")
        if item_schema:
            for index, child in enumerate(value):
                validate_schema_instance(child, item_schema, root_schema, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(error("SCHEMA_MIN_LENGTH", path, "string is shorter than the committed minimum"))
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(error("SCHEMA_PATTERN", path, "string does not match the committed pattern"))
        if schema.get("format") == "date-time" and parse_timestamp(value) is None:
            errors.append(error("SCHEMA_FORMAT", path, "string is not an ISO-8601 date-time"))
    elif isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(error("SCHEMA_MINIMUM", path, "integer is below the committed minimum"))
    return errors


def validate_committed_schema(data):
    schema = json.loads(SCHEMA_PATH.read_text())
    return validate_schema_instance(data, schema, schema)


def scan_for_secret_fields(value, errors, path="$", environment_observation=False):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_PATTERN.search(key):
                errors.append(error("SECRET_FIELD_FORBIDDEN", child_path, "secret-bearing field names are forbidden"))
            if key == "value" and environment_observation and isinstance(child, str) and value.get("redacted") is not True:
                policy_secret = value.get("name", "").upper().endswith(("SECRET", "TOKEN", "PASSWORD", "KEY"))
                if policy_secret:
                    errors.append(error("SECRET_VALUE_FORBIDDEN", child_path, "secret-like environment values are forbidden"))
            if isinstance(child, str) and "-----BEGIN " in child and "PRIVATE KEY-----" in child:
                errors.append(error("SECRET_VALUE_FORBIDDEN", child_path, "private key material is forbidden"))
            scan_for_secret_fields(child, errors, child_path, path.endswith(".observed") or environment_observation)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_for_secret_fields(child, errors, f"{path}[{index}]", path.endswith(".observed") or environment_observation)


def installed_path_census_payload():
    return [{"role": role, "installed_path": MANDATORY_INSTALLED_PATHS[role]} for role in sorted(MANDATORY_ROLES)]


def canonical_absolute_path(value):
    if not isinstance(value, str) or not value.startswith("/"):
        return False
    pure = PurePosixPath(value)
    return pure.is_absolute() and str(pure) == value and "." not in pure.parts and ".." not in pure.parts



def compare_identity(errors, target, capture):
    fields = {
        "repository": "IDENTITY_REPOSITORY_DRIFT",
        "base_sha": "IDENTITY_BASE_DRIFT",
        "workflow_sha": "IDENTITY_WORKFLOW_DRIFT",
        "run_id": "IDENTITY_RUN_DRIFT",
        "job_id": "IDENTITY_JOB_DRIFT",
    }
    for field, code in fields.items():
        if target.get(field) != capture.get(field):
            errors.append(error(code, f"capture_identity.{field}", "captured identity does not match the requested ranked authority"))


def validate_capture_window(errors, data):
    capture = data.get("capture_identity", {})
    authority = data.get("authority", {})
    started = parse_timestamp(capture.get("job_started_at"))
    finished = parse_timestamp(capture.get("job_finished_at"))
    captured = parse_timestamp(authority.get("captured_at"))
    if not all((started, finished, captured)):
        errors.append(error("TIMESTAMP_INVALID", "authority/capture_identity", "capture timestamps must be ISO-8601 date-times"))
        return None, None
    if started > finished or not started <= captured <= finished:
        errors.append(error("STALE_CAPTURE", "authority.captured_at", "capture timestamp is outside the ranked job interval"))
    return started, finished


def validate_artifacts(errors, data, root, missing_role):
    artifacts = data.get("artifacts")
    required = data.get("required_artifact_roles")
    if not isinstance(artifacts, list) or not isinstance(required, list):
        errors.append(error("TOP_LEVEL_TYPE", "artifacts/required_artifact_roles", "artifact collections must be arrays"))
        return {}, {}

    if len(required) != len(set(required)):
        errors.append(error("DUPLICATE_REQUIRED_ROLE", "required_artifact_roles", "required artifact roles must be unique"))
    if set(required) != MANDATORY_ROLES or len(required) != len(MANDATORY_ROLES):
        errors.append(error("MANDATORY_ROLE_CENSUS_MISMATCH", "required_artifact_roles", "required roles must equal the versioned PR #671 authority census"))
    expected_census = digest_value(installed_path_census_payload())
    if data.get("installed_path_census_sha256") != expected_census:
        errors.append(error("INSTALLED_PATH_CENSUS_DIGEST_MISMATCH", "installed_path_census_sha256", "installed-path census digest does not match the validator contract"))

    by_role = {}
    by_path = {}
    installed_paths = {}
    for index, artifact in enumerate(artifacts):
        path = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(error("ARTIFACT_TYPE", path, "artifact must be an object"))
            continue
        role = artifact.get("role")
        if not isinstance(role, str):
            errors.append(error("ARTIFACT_ROLE_INVALID", f"{path}.role", "artifact role must be a string"))
            continue
        if role in by_role:
            errors.append(error("DUPLICATE_ARTIFACT_ROLE", f"{path}.role", f"artifact role {role} appears more than once"))
            continue
        by_role[role] = artifact
        bundle_path = artifact.get("bundle_path")
        if bundle_path in by_path:
            errors.append(error("BUNDLE_PATH_COLLISION", f"{path}.bundle_path", "two artifacts use the same bundle path"))
        else:
            by_path[bundle_path] = role
        installed_path = artifact.get("installed_path")
        if not canonical_absolute_path(installed_path):
            errors.append(error("INSTALLED_PATH_NONCANONICAL", f"{path}.installed_path", "installed path must be canonical and absolute"))
        elif MANDATORY_INSTALLED_PATHS.get(role) != installed_path:
            errors.append(error("INSTALLED_PATH_CENSUS_MISMATCH", f"{path}.installed_path", "installed path does not match the versioned role census"))
        if installed_path in installed_paths:
            errors.append(error("INSTALLED_PATH_COLLISION", f"{path}.installed_path", "two roles claim the same installed path"))
        else:
            installed_paths[installed_path] = role

    observed_roles = set(by_role)
    absent = sorted(MANDATORY_ROLES - observed_roles)
    extra = sorted(observed_roles - MANDATORY_ROLES)
    if extra:
        errors.append(error("ARTIFACT_ROLE_CENSUS_MISMATCH", "artifacts", f"unknown artifact roles are present: {', '.join(extra)}"))
    if absent:
        if len(absent) == 1 and absent[0] == missing_role:
            pass
        elif len(absent) == 1:
            errors.append(error("MISSING_AUTHORITY_UNDECLARED", "artifacts", f"mandatory artifact role {absent[0]} is absent without the matching missing_authority declaration"))
        else:
            errors.append(error("MULTIPLE_MISSING_AUTHORITIES", "artifacts", f"multiple mandatory artifact roles are absent: {', '.join(absent)}"))
    elif missing_role is not None:
        errors.append(error("UNEXPECTED_MISSING_AUTHORITY", "missing_authority", "declared missing authority is present in the artifact set"))

    observed = {}
    for role, artifact in by_role.items():
        path = f"artifacts[{role}]"
        candidate = safe_bundle_path(root, artifact.get("bundle_path"))
        if candidate is None:
            errors.append(error("BUNDLE_PATH_ESCAPE", f"{path}.bundle_path", "bundle path must be canonical, relative, and remain below the bundle root"))
            continue
        if not candidate.exists() and not candidate.is_symlink():
            errors.append(error("PHYSICAL_FILE_MISSING", f"{path}.bundle_path", "self-declared artifact has no matching physical file"))
            continue
        metadata = artifact.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(error("ARTIFACT_METADATA_MISSING", f"{path}.metadata", "artifact metadata is required"))
            continue
        try:
            actual = physical_metadata(candidate, metadata.get("mount_id", "unknown"))
        except OSError as exc:
            errors.append(error("PHYSICAL_STAT_FAILED", f"{path}.bundle_path", f"cannot inspect physical artifact: {exc.strerror}"))
            continue
        observed[role] = actual
        if actual["symlink"]:
            errors.append(error("PHYSICAL_SYMLINK", f"{path}.bundle_path", "authority artifacts must not be symbolic links"))
            continue
        if not candidate.is_file():
            errors.append(error("PHYSICAL_NONREGULAR", f"{path}.bundle_path", "authority artifacts must be regular files"))
            continue
        actual_size = candidate.stat().st_size
        actual_hash = digest_file(candidate)
        if artifact.get("size") != actual_size:
            errors.append(error("PHYSICAL_SIZE_MISMATCH", f"{path}.size", "declared size does not match the physical file"))
        if artifact.get("sha256") != actual_hash:
            errors.append(error("PHYSICAL_HASH_MISMATCH", f"{path}.sha256", "declared hash does not match the physical file bytes"))
        checks = (
            ("owner_uid", "PHYSICAL_OWNER_UID_MISMATCH"),
            ("owner_gid", "PHYSICAL_OWNER_GID_MISMATCH"),
            ("mode", "PHYSICAL_MODE_MISMATCH"),
            ("acl", "PHYSICAL_ACL_MISMATCH"),
            ("flags", "PHYSICAL_FLAGS_MISMATCH"),
            ("link_count", "PHYSICAL_LINK_COUNT_MISMATCH"),
            ("symlink", "PHYSICAL_SYMLINK_DECLARATION_MISMATCH"),
            ("device_id", "PHYSICAL_DEVICE_MISMATCH"),
            ("filesystem", "PHYSICAL_FILESYSTEM_MISMATCH"),
        )
        for field, code in checks:
            if metadata.get(field) != actual[field]:
                errors.append(error(code, f"{path}.metadata.{field}", f"declared {field} does not match the physical file"))
        if actual["link_count"] != 1:
            errors.append(error("HARDLINK_AMBIGUITY", f"{path}.metadata.link_count", "authority artifacts must have exactly one hard link"))
        declared_acl = metadata.get("acl", {})
        if isinstance(declared_acl, dict):
            normalized = normalize_acl(declared_acl.get("normalized_text", ""))
            if declared_acl.get("normalized_text") != normalized or declared_acl.get("sha256") != hashlib.sha256(normalized.encode()).hexdigest():
                errors.append(error("ACL_DIGEST_MISMATCH", f"{path}.metadata.acl", "ACL text is not normalized or its digest is incorrect"))

        installation = artifact.get("installation")
        if not isinstance(installation, dict):
            errors.append(error("INSTALL_PROVENANCE_MISSING", f"{path}.installation", "installation provenance is required"))
            continue
        package = installation.get("package")
        if not isinstance(package, dict) or not all(package.get(key) for key in ("name", "version", "digest_sha256")):
            errors.append(error("INSTALL_PROVENANCE_MISSING", f"{path}.installation.package", "package name, version, and digest are required"))
        if installation.get("expected_metadata") != metadata:
            errors.append(error("INSTALL_METADATA_MISMATCH", f"{path}.installation.expected_metadata", "install recipe metadata does not match captured installed metadata"))

    for role, artifact in by_role.items():
        installation = artifact.get("installation", {})
        recipe_role = installation.get("recipe_role")
        if recipe_role == missing_role:
            continue
        recipe = by_role.get(recipe_role)
        if recipe is None:
            errors.append(error("INSTALL_RECIPE_MISSING", f"artifacts[{role}].installation.recipe_role", "referenced installation recipe artifact is absent"))
        elif installation.get("recipe_sha256") != recipe.get("sha256"):
            errors.append(error("INSTALL_RECIPE_HASH_MISMATCH", f"artifacts[{role}].installation.recipe_sha256", "installation recipe hash does not match its physical artifact declaration"))
    return by_role, observed


def validate_environment(errors, data):
    environment = data.get("environment")
    if not isinstance(environment, dict):
        errors.append(error("ENVIRONMENT_MISSING", "environment", "environment evidence is required"))
        return {}
    policy = environment.get("policy", [])
    observed = environment.get("observed", [])
    policy_by_name = {}
    for index, entry in enumerate(policy if isinstance(policy, list) else []):
        name = entry.get("name") if isinstance(entry, dict) else None
        if name in policy_by_name:
            errors.append(error("ENV_POLICY_DUPLICATE", f"environment.policy[{index}].name", "environment names may be declared only once"))
        elif name:
            policy_by_name[name] = entry
    observed_pairs = set()
    for index, item in enumerate(observed if isinstance(observed, list) else []):
        if not isinstance(item, dict):
            errors.append(error("ENV_OBSERVATION_TYPE", f"environment.observed[{index}]", "environment observation must be an object"))
            continue
        actor_id = item.get("actor_id")
        name = item.get("name")
        if actor_id not in EXPECTED_ACTORS:
            errors.append(error("ENV_ACTOR_UNKNOWN", f"environment.observed[{index}].actor_id", "environment observation actor is outside the closed-world census"))
        pair = (actor_id, name)
        if pair in observed_pairs:
            errors.append(error("ENV_OBSERVATION_DUPLICATE", f"environment.observed[{index}]", "each actor and policy name must have exactly one observation"))
        observed_pairs.add(pair)
        policy_entry = policy_by_name.get(name)
        if policy_entry is None:
            errors.append(error("ENV_UNDECLARED_NAME", f"environment.observed[{index}].name", "observed environment name is not in the capture policy"))
            continue
        sensitivity = policy_entry.get("sensitivity")
        capture = policy_entry.get("capture")
        if sensitivity == "secret":
            if "value" in item or item.get("redacted") is not True or capture != "redacted":
                errors.append(error("ENV_SECRET_LEAK", f"environment.observed[{index}]", "secret variables must record only their name and a redacted marker"))
        elif capture == "value" and "value" not in item:
            errors.append(error("ENV_VALUE_MISSING", f"environment.observed[{index}]", "public value capture policy requires a value"))
        elif capture == "name_only" and "value" in item:
            errors.append(error("ENV_NAME_ONLY_VALUE", f"environment.observed[{index}]", "name-only policy forbids a captured value"))
    expected_pairs = {(actor_id, name) for actor_id in EXPECTED_ACTORS for name in policy_by_name}
    missing_pairs = sorted(expected_pairs - observed_pairs)
    if missing_pairs:
        errors.append(error("ENV_OBSERVATION_MISSING", "environment.observed", f"actor/policy observations are absent: {missing_pairs}"))
    expected_policy = digest_value(policy)
    expected_observed = digest_value(observed)
    if environment.get("policy_sha256") != expected_policy:
        errors.append(error("ENV_POLICY_DIGEST_MISMATCH", "environment.policy_sha256", "environment policy digest is incorrect"))
    if environment.get("observed_sha256") != expected_observed:
        errors.append(error("ENV_OBSERVED_DIGEST_MISMATCH", "environment.observed_sha256", "environment observation digest is incorrect"))
    return policy_by_name


def validate_actors_and_phases(errors, data, artifacts):
    actors = data.get("actors", [])
    by_id = {}
    for index, actor in enumerate(actors if isinstance(actors, list) else []):
        actor_id = actor.get("id") if isinstance(actor, dict) else None
        if not actor_id:
            errors.append(error("ACTOR_ID_INVALID", f"actors[{index}]", "actor identity is required"))
        elif actor_id in by_id:
            errors.append(error("DUPLICATE_ACTOR", f"actors[{index}].id", "actor identities must be unique"))
        else:
            by_id[actor_id] = actor
        if isinstance(actor, dict) and actor.get("environment_policy_sha256") != data.get("environment", {}).get("policy_sha256"):
            errors.append(error("ACTOR_ENV_POLICY_MISMATCH", f"actors[{index}].environment_policy_sha256", "actor must bind the captured environment policy"))
    if set(by_id) != set(EXPECTED_ACTORS) or len(by_id) != len(EXPECTED_ACTORS):
        errors.append(error("ACTOR_CENSUS_MISMATCH", "actors", "actors must equal the closed-world controller, bench, and worker census"))
    for actor_id, actor in by_id.items():
        parent = actor.get("parent_actor_id")
        if actor_id in EXPECTED_ACTORS and parent != EXPECTED_ACTORS[actor_id]:
            errors.append(error("ACTOR_PARENT_CONTRADICTION", f"actors[{actor_id}].parent_actor_id", "actor parent contradicts the closed-world hierarchy"))
        if parent is not None and parent not in by_id:
            errors.append(error("ACTOR_PARENT_MISSING", f"actors[{actor_id}].parent_actor_id", "parent actor is absent"))
        visited = set()
        cursor = actor_id
        while cursor is not None and cursor in by_id:
            if cursor in visited:
                errors.append(error("ACTOR_PARENT_CYCLE", f"actors[{actor_id}].parent_actor_id", "actor parent chain contains a cycle"))
                break
            visited.add(cursor)
            cursor = by_id[cursor].get("parent_actor_id")

    phases = data.get("phases", [])
    by_name = {}
    for index, phase in enumerate(phases if isinstance(phases, list) else []):
        if not isinstance(phase, dict):
            errors.append(error("PHASE_TYPE", f"phases[{index}]", "phase must be an object"))
            continue
        name = phase.get("name")
        if name in by_name:
            errors.append(error("DUPLICATE_PHASE", f"phases[{index}].name", "phase names must be unique"))
        else:
            by_name[name] = phase
        actor = by_id.get(phase.get("actor_id"))
        transition = phase.get("transition", {})
        source = by_id.get(transition.get("from_actor_id"))
        target = by_id.get(transition.get("to_actor_id"))
        if actor is None or source is None or target is None:
            errors.append(error("PHASE_ACTOR_MISSING", f"phases[{index}]", "phase transition actors must exist"))
            continue
        expected = (source.get("euid"), source.get("egid"), target.get("euid"), target.get("egid"))
        declared = (transition.get("from_uid"), transition.get("from_gid"), transition.get("to_uid"), transition.get("to_gid"))
        if expected != declared or phase.get("actor_id") != target.get("id"):
            errors.append(error("TRANSITION_IDENTITY_CONTRADICTION", f"phases[{index}].transition", "declared UID/GID transition contradicts actor identities"))
        authorizer = transition.get("authorized_by_artifact_role")
        if authorizer not in artifacts:
            errors.append(error("TRANSITION_AUTHORIZER_MISSING", f"phases[{index}].transition.authorized_by_artifact_role", "transition authorizer artifact is absent"))
        if transition.get("kind") in ("none", "exec_inherited") and expected[:2] != expected[2:]:
            errors.append(error("TRANSITION_KIND_CONTRADICTION", f"phases[{index}].transition.kind", "non-privileged transition changes effective identity"))
    if set(by_name) != set(EXPECTED_PHASE_ACTORS) or len(by_name) != len(EXPECTED_PHASE_ACTORS):
        errors.append(error("PHASE_CENSUS_MISMATCH", "phases", "phases must equal the closed-world ranked phase census"))
    for name, actor_id in EXPECTED_PHASE_ACTORS.items():
        phase = by_name.get(name)
        if phase is not None and phase.get("actor_id") != actor_id:
            errors.append(error("PHASE_ACTOR_CONTRADICTION", f"phases[{name}].actor_id", "phase actor contradicts the ranked phase census"))
    return by_id, by_name


def validate_events(errors, data, artifacts, actors, started, finished, missing_role):
    events = data.get("events", [])
    edges = data.get("event_edges", [])
    by_id = {}
    by_type = {}
    for index, event_item in enumerate(events if isinstance(events, list) else []):
        if not isinstance(event_item, dict):
            errors.append(error("EVENT_TYPE_INVALID", f"events[{index}]", "event must be an object"))
            continue
        event_id = event_item.get("id")
        event_type = event_item.get("type")
        if event_id in by_id:
            errors.append(error("DUPLICATE_EVENT_ID", f"events[{index}].id", "event IDs must be unique"))
        else:
            by_id[event_id] = event_item
        if event_type in by_type:
            errors.append(error("DUPLICATE_EVENT_TYPE", f"events[{index}].type", "required event types must be unique"))
        else:
            by_type[event_type] = event_item
        if event_item.get("actor_id") not in actors:
            errors.append(error("EVENT_ACTOR_MISSING", f"events[{index}].actor_id", "event actor is absent"))
        command = event_item.get("command", {})
        role = command.get("artifact_role")
        artifact = artifacts.get(role)
        if artifact is None:
            if role != missing_role:
                errors.append(error("EVENT_COMMAND_ARTIFACT_MISSING", f"events[{index}].command.artifact_role", "event command artifact is absent"))
        elif command.get("artifact_sha256") != artifact.get("sha256"):
            errors.append(error("EVENT_COMMAND_HASH_MISMATCH", f"events[{index}].command.artifact_sha256", "event command hash does not match the captured artifact"))
        timestamp = parse_timestamp(event_item.get("timestamp"))
        if timestamp is None:
            errors.append(error("EVENT_TIMESTAMP_INVALID", f"events[{index}].timestamp", "event timestamp is invalid"))
        elif started and finished and not started <= timestamp <= finished:
            errors.append(error("EVENT_OUTSIDE_JOB", f"events[{index}].timestamp", "event is outside the ranked job interval"))

    expected_ids = {item[0] for item in EXPECTED_EVENTS}
    if set(by_id) != expected_ids or len(by_id) != len(EXPECTED_EVENTS):
        errors.append(error("EVENT_CENSUS_MISMATCH", "events", "events must equal the closed-world ranked event census"))
    for event_id, event_type, actor_id, artifact_role in EXPECTED_EVENTS:
        event_item = by_id.get(event_id)
        if event_item is None:
            continue
        actual = (event_item.get("type"), event_item.get("actor_id"), event_item.get("command", {}).get("artifact_role"))
        if actual != (event_type, actor_id, artifact_role):
            errors.append(error("EVENT_BINDING_CONTRADICTION", f"events[{event_id}]", "event type, actor, or command role contradicts the ranked census"))
    if expected_ids <= set(by_id):
        ordered = [by_id[item[0]] for item in EXPECTED_EVENTS]
        sequences = [item.get("sequence") for item in ordered]
        if sequences != [10 * index for index in range(1, len(EXPECTED_EVENTS) + 1)]:
            errors.append(error("EVENT_ORDER_REVERSAL", "events", "required ranked events are not in strict transform-to-load order"))
        timestamps = [parse_timestamp(item.get("timestamp")) for item in ordered]
        if all(timestamp is not None for timestamp in timestamps) and any(left >= right for left, right in zip(timestamps, timestamps[1:])):
            errors.append(error("EVENT_TIMESTAMP_REVERSAL", "events", "ranked event timestamps are not strictly increasing"))

    adjacency = {event_id: [] for event_id in by_id}
    edge_triples = set()
    for index, edge_item in enumerate(edges if isinstance(edges, list) else []):
        if not isinstance(edge_item, dict):
            errors.append(error("EVENT_EDGE_TYPE", f"event_edges[{index}]", "event edge must be an object"))
            continue
        source = edge_item.get("from")
        target = edge_item.get("to")
        edge_type = edge_item.get("type")
        if source not in by_id or target not in by_id:
            errors.append(error("EVENT_EDGE_ENDPOINT_MISSING", f"event_edges[{index}]", "event edge endpoint is absent"))
            continue
        adjacency[source].append(target)
        edge_triples.add((source, target, edge_type))
        source_seq = by_id[source].get("sequence")
        target_seq = by_id[target].get("sequence")
        if not isinstance(source_seq, int) or not isinstance(target_seq, int) or source_seq >= target_seq:
            errors.append(error("EVENT_ORDER_REVERSAL", f"event_edges[{index}]", "event edge contradicts sequence order"))

    color = {}

    def visit(node):
        color[node] = 1
        for neighbor in adjacency.get(node, []):
            if color.get(neighbor) == 1:
                return True
            if color.get(neighbor, 0) == 0 and visit(neighbor):
                return True
        color[node] = 2
        return False

    if any(color.get(node, 0) == 0 and visit(node) for node in sorted(adjacency)):
        errors.append(error("EVENT_CYCLE", "event_edges", "event graph contains a cycle"))

    required_edges = set(REQUIRED_EVENT_EDGES)
    missing_edges = sorted(required_edges - edge_triples)
    extra_edges = sorted(edge_triples - required_edges)
    if missing_edges:
        errors.append(error("REQUIRED_EVENT_EDGE_MISSING", "event_edges", f"required typed edges are absent: {missing_edges}"))
    if extra_edges:
        errors.append(error("EVENT_EDGE_CENSUS_MISMATCH", "event_edges", f"unexpected typed edges are present: {extra_edges}"))

    survivor_policy = data.get("survivor_policy")
    reaper_event = by_type.get("reaper")
    if reaper_event and reaper_event.get("survivor_policy") != survivor_policy:
        errors.append(error("SURVIVOR_POLICY_CONTRADICTION", "events[reaper].survivor_policy", "reaper event contradicts the bundle survivor policy"))
    for event_type, event_item in by_type.items():
        if event_type != "reaper" and event_item.get("survivor_policy") is not None:
            errors.append(error("SURVIVOR_POLICY_UNEXPECTED", f"events[{event_type}].survivor_policy", "only the reaper event may carry survivor policy"))
    return by_id, by_type


def validate_confinement(errors, data, artifacts, phases, missing_role):
    confinement = data.get("confinement")
    if not isinstance(confinement, dict):
        errors.append(error("CONFINEMENT_MISSING", "confinement", "confinement evidence is required"))
        return
    mounts = confinement.get("mounts", [])
    mount_by_id = {}
    for index, mount in enumerate(mounts if isinstance(mounts, list) else []):
        mount_id = mount.get("id") if isinstance(mount, dict) else None
        if mount_id in mount_by_id:
            errors.append(error("DUPLICATE_MOUNT", f"confinement.mounts[{index}].id", "mount IDs must be unique"))
        elif mount_id:
            mount_by_id[mount_id] = mount
    weights = confinement.get("weights_root", {})
    weight_mount = mount_by_id.get(weights.get("mount_id"))
    if weight_mount is None:
        errors.append(error("WEIGHTS_MOUNT_MISSING", "confinement.weights_root.mount_id", "weights root mount is absent"))
    elif weights.get("device_id") != weight_mount.get("device_id") or weights.get("filesystem") != weight_mount.get("filesystem"):
        errors.append(error("MOUNT_PATH_CONTRADICTION", "confinement.weights_root", "weights root device/filesystem contradicts its mount"))

    access = weights.get("worker_access")
    descriptor_hash = weights.get("descriptor_manifest_sha256")
    if access == "immutable_descriptors" and not descriptor_hash:
        errors.append(error("DESCRIPTOR_MANIFEST_MISSING", "confinement.weights_root.descriptor_manifest_sha256", "immutable descriptor access requires a descriptor manifest"))
    if access == "pathnames" and descriptor_hash is not None:
        errors.append(error("PATH_DESCRIPTOR_CONTRADICTION", "confinement.weights_root", "pathname access cannot claim an immutable descriptor manifest"))

    capability_by_phase = {}
    capabilities = confinement.get("capabilities", [])
    for index, capability in enumerate(capabilities if isinstance(capabilities, list) else []):
        if not isinstance(capability, dict):
            errors.append(error("CAPABILITY_TYPE", f"confinement.capabilities[{index}]", "capability must be an object"))
            continue
        phase_name = capability.get("phase")
        if phase_name in capability_by_phase:
            errors.append(error("DUPLICATE_CAPABILITY_PHASE", f"confinement.capabilities[{index}].phase", "capability phases must be unique"))
        else:
            capability_by_phase[phase_name] = capability
        phase = phases.get(phase_name)
        if phase is None or capability.get("actor_id") != phase.get("actor_id"):
            errors.append(error("CAPABILITY_ACTOR_CONTRADICTION", f"confinement.capabilities[{index}]", "capability actor contradicts phase actor"))
    if set(capability_by_phase) != set(EXPECTED_CAPABILITIES) or len(capability_by_phase) != len(EXPECTED_CAPABILITIES):
        errors.append(error("CAPABILITY_CENSUS_MISMATCH", "confinement.capabilities", "capabilities must equal the closed-world ranked phase census"))
    for phase_name, expected in EXPECTED_CAPABILITIES.items():
        capability = capability_by_phase.get(phase_name)
        if capability is None:
            continue
        actual = tuple(capability.get(field) for field in ("actor_id", "read", "write", "rename", "unlink"))
        if actual != expected:
            errors.append(error("CAPABILITY_RIGHTS_CONTRADICTION", f"confinement.capabilities[{phase_name}]", "capability actor or rights contradict the ranked phase contract"))
    load_capability = capability_by_phase.get("worker_load_epoch")
    if load_capability is None:
        errors.append(error("LOAD_CAPABILITY_MISSING", "confinement.capabilities", "worker load epoch capability is absent"))
    elif not load_capability.get("read") or (weights.get("immutable_during_load") and any(load_capability.get(name) for name in ("write", "rename", "unlink"))):
        errors.append(error("LOAD_IMMUTABILITY_CONTRADICTION", "confinement.capabilities[worker_load_epoch]", "load epoch rights contradict immutable read-only weights"))

    profile_role = confinement.get("sandbox_profile_role")
    generator_role = confinement.get("profile_generator_role")
    input_roles = confinement.get("profile_generator_input_roles", [])
    if (profile_role, generator_role, input_roles) != (
        "worker_sandbox_profile",
        "worker_sandbox_profile_generator",
        ["profile_generator_input"],
    ):
        errors.append(error("PROFILE_CONFINEMENT_ROLE_DRIFT", "confinement", "profile output, generator, and input roles must match the ranked authority contract"))
    profile = artifacts.get(profile_role)
    if profile is None:
        if profile_role != missing_role:
            errors.append(error("PROFILE_ARTIFACT_MISSING", "confinement.sandbox_profile_role", "sandbox profile artifact is absent"))
    elif confinement.get("sandbox_profile_sha256") != profile.get("sha256"):
        errors.append(error("PROFILE_HASH_MISMATCH", "confinement.sandbox_profile_sha256", "sandbox profile hash does not match the physical profile artifact"))
    if generator_role not in artifacts and generator_role != missing_role:
        errors.append(error("PROFILE_GENERATOR_MISSING", "confinement.profile_generator_role", "profile generator artifact is absent"))
    for index, role in enumerate(input_roles if isinstance(input_roles, list) else []):
        if role not in artifacts and role != missing_role:
            errors.append(error("PROFILE_GENERATOR_INPUT_MISSING", f"confinement.profile_generator_input_roles[{index}]", "profile generator input artifact is absent"))

    for role, artifact in artifacts.items():
        metadata = artifact.get("metadata", {})
        mount = mount_by_id.get(metadata.get("mount_id"))
        if mount is None:
            errors.append(error("ARTIFACT_MOUNT_MISSING", f"artifacts[{role}].metadata.mount_id", "artifact mount is absent from confinement evidence"))
        elif metadata.get("device_id") != mount.get("device_id") or metadata.get("filesystem") != mount.get("filesystem"):
            errors.append(error("ARTIFACT_MOUNT_CONTRADICTION", f"artifacts[{role}].metadata", "artifact device/filesystem contradicts its mount"))


def artifact_set_payload(data):
    return sorted(data.get("artifacts", []), key=lambda item: (item.get("role", ""), item.get("bundle_path", "")))


def event_graph_payload(data):
    return {
        "actors": sorted(data.get("actors", []), key=lambda item: item.get("id", "")),
        "phases": sorted(data.get("phases", []), key=lambda item: item.get("name", "")),
        "events": sorted(data.get("events", []), key=lambda item: (item.get("sequence", -1), item.get("id", ""))),
        "event_edges": sorted(data.get("event_edges", []), key=lambda item: (item.get("from", ""), item.get("to", ""), item.get("type", ""))),
        "survivor_policy": data.get("survivor_policy"),
    }


def generation_payload(link):
    return {key: value for key, value in link.items() if key != "link_sha256"}


def authority_payload(data):
    crypto = data.get("crypto_linkage", {})
    return {
        "target_identity": data.get("target_identity"),
        "capture_identity": data.get("capture_identity"),
        "artifact_set_sha256": crypto.get("artifact_set_sha256"),
        "environment_sha256": crypto.get("environment_sha256"),
        "event_graph_sha256": crypto.get("event_graph_sha256"),
        "confinement_sha256": crypto.get("confinement_sha256"),
        "generation_link_sha256": [item.get("link_sha256") for item in crypto.get("generation_links", [])],
    }


def validate_crypto(errors, data, artifacts, missing_role):
    crypto = data.get("crypto_linkage")
    if not isinstance(crypto, dict):
        errors.append(error("CRYPTO_LINKAGE_MISSING", "crypto_linkage", "cryptographic linkage is required"))
        return
    expected = {
        "artifact_set_sha256": digest_value(artifact_set_payload(data)),
        "environment_sha256": digest_value({
            "policy_sha256": data.get("environment", {}).get("policy_sha256"),
            "observed_sha256": data.get("environment", {}).get("observed_sha256"),
        }),
        "event_graph_sha256": digest_value(event_graph_payload(data)),
        "confinement_sha256": digest_value(data.get("confinement")),
    }
    codes = {
        "artifact_set_sha256": "ARTIFACT_SET_DIGEST_MISMATCH",
        "environment_sha256": "ENVIRONMENT_LINK_DIGEST_MISMATCH",
        "event_graph_sha256": "EVENT_GRAPH_DIGEST_MISMATCH",
        "confinement_sha256": "CONFINEMENT_DIGEST_MISMATCH",
    }
    for field, value in expected.items():
        if crypto.get(field) != value:
            errors.append(error(codes[field], f"crypto_linkage.{field}", "cryptographic linkage digest is incorrect"))

    capture = data.get("capture_identity", {})
    confinement = data.get("confinement", {})
    events = {item.get("id"): item for item in data.get("events", []) if isinstance(item, dict)}
    expected_roles = ("worker_sandbox_profile", "worker_sandbox_profile_generator", ["profile_generator_input"])
    expected_argv = [
        MANDATORY_INSTALLED_PATHS["worker_sandbox_profile_generator"],
        MANDATORY_INSTALLED_PATHS["profile_generator_input"],
        MANDATORY_INSTALLED_PATHS["worker_sandbox_profile"],
    ]
    for index, link in enumerate(crypto.get("generation_links", [])):
        path = f"crypto_linkage.generation_links[{index}]"
        if not isinstance(link, dict):
            errors.append(error("GENERATION_LINK_TYPE", path, "generation link must be an object"))
            continue
        linked_roles = (link.get("output_role"), link.get("generator_role"), link.get("input_roles"))
        if linked_roles != expected_roles:
            errors.append(error("GENERATION_ROLE_DRIFT", path, "generation output, generator, and input roles contradict the ranked authority contract"))
        confinement_roles = (
            confinement.get("sandbox_profile_role"),
            confinement.get("profile_generator_role"),
            confinement.get("profile_generator_input_roles"),
        )
        if linked_roles != confinement_roles:
            errors.append(error("GENERATION_ROLE_DRIFT", path, "generation link roles contradict confinement evidence"))

        event_id = link.get("event_id")
        generation_event = events.get(event_id)
        event_command = generation_event.get("command", {}) if generation_event else {}
        if (
            event_id != "profile-generated"
            or generation_event is None
            or link.get("generated_at") != generation_event.get("timestamp")
            or event_command.get("artifact_role") != "worker_sandbox_profile_generator"
            or event_command.get("argv") != expected_argv
        ):
            errors.append(error("GENERATION_EVENT_DRIFT", path, "generation link does not exactly match the canonical profile-generated event"))

        output = artifacts.get(link.get("output_role"))
        generator = artifacts.get(link.get("generator_role"))
        input_roles = link.get("input_roles", [])
        inputs = [artifacts.get(role) for role in input_roles] if isinstance(input_roles, list) else []
        roles = [link.get("output_role"), link.get("generator_role")] + (input_roles if isinstance(input_roles, list) else [])
        absent_roles = [role for role, artifact in zip(roles, [output, generator] + inputs) if artifact is None]
        undeclared_absent = [role for role in absent_roles if role != missing_role]
        if undeclared_absent:
            errors.append(error("GENERATION_ARTIFACT_MISSING", path, f"generation link references absent artifacts: {undeclared_absent}"))
        if output is not None and generator is not None:
            if link.get("output_sha256") != output.get("sha256") or link.get("generator_sha256") != generator.get("sha256"):
                errors.append(error("GENERATION_HASH_MISMATCH", path, "generation output/generator hash is not linked to the artifact set"))
        if all(item is not None for item in inputs) and link.get("input_sha256") != [item.get("sha256") for item in inputs]:
            errors.append(error("GENERATION_INPUT_HASH_MISMATCH", f"{path}.input_sha256", "generation input hashes are not linked to the artifact set"))
        for field in ("base_sha", "workflow_sha", "run_id", "job_id"):
            if link.get(field) != capture.get(field):
                errors.append(error("GENERATION_IDENTITY_DRIFT", f"{path}.{field}", "generation context does not match the ranked capture"))
        if link.get("link_sha256") != digest_value(generation_payload(link)):
            errors.append(error("GENERATION_LINK_DIGEST_MISMATCH", f"{path}.link_sha256", "generation link digest is incorrect"))

    if crypto.get("authority_link_sha256") != digest_value(authority_payload(data)):
        errors.append(error("AUTHORITY_LINK_DIGEST_MISMATCH", "crypto_linkage.authority_link_sha256", "top-level authority linkage digest is incorrect"))


def validate_bundle(data, root):
    errors = []
    if not isinstance(data, dict):
        return {
            "state": "INVALID",
            "bundle_digest_sha256": digest_value(data),
            "errors": [error("TOP_LEVEL_TYPE", "$", "bundle must be an object")],
            "missing_authority": None,
            "authoritative": False,
        }
    errors.extend(validate_committed_schema(data))
    scan_for_secret_fields(data, errors)
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("SCHEMA_VERSION", "schema_version", f"expected {SCHEMA_VERSION}"))
    if data.get("authority_contract_version") != AUTHORITY_CONTRACT_VERSION:
        errors.append(error("AUTHORITY_CONTRACT_VERSION", "authority_contract_version", f"expected {AUTHORITY_CONTRACT_VERSION}"))
    required_top = {
        "schema_version", "authority_contract_version", "installed_path_census_sha256",
        "authority", "target_identity", "capture_identity", "required_artifact_roles", "artifacts",
        "environment", "actors", "phases", "events", "event_edges", "survivor_policy",
        "confinement", "crypto_linkage", "missing_authority",
    }
    missing_top = sorted(required_top - set(data))
    if missing_top:
        errors.append(error("TOP_LEVEL_MISSING", "$", f"required top-level fields are absent: {', '.join(missing_top)}"))

    missing_declaration = data.get("missing_authority")
    missing_role = missing_declaration.get("role") if isinstance(missing_declaration, dict) else None
    if missing_declaration is not None and not isinstance(missing_declaration, dict):
        errors.append(error("MISSING_AUTHORITY_TYPE", "missing_authority", "missing_authority must be null or an object"))
    elif isinstance(missing_declaration, dict):
        if missing_declaration.get("kind") != "artifact_role" or not all(missing_declaration.get(key) for key in ("role", "fact", "reason")):
            errors.append(error("MISSING_AUTHORITY_INVALID", "missing_authority", "missing authority must identify exactly one artifact role and fact"))

    try:
        compare_identity(errors, data.get("target_identity", {}), data.get("capture_identity", {}))
        started, finished = validate_capture_window(errors, data)
        artifacts, _ = validate_artifacts(errors, data, root, missing_role)
        validate_environment(errors, data)
        actors, phases = validate_actors_and_phases(errors, data, artifacts)
        validate_events(errors, data, artifacts, actors, started, finished, missing_role)
        validate_confinement(errors, data, artifacts, phases, missing_role)
        validate_crypto(errors, data, artifacts, missing_role)
    except (AttributeError, KeyError, TypeError, ValueError) as exception:
        errors.append(error("VALIDATOR_INPUT_UNSAFE", "$", f"malformed input prevented semantic validation: {type(exception).__name__}"))

    errors = sorted(errors, key=lambda item: (item["code"], item["path"], item["message"]))
    if errors:
        state = "INVALID"
    elif missing_role:
        state = "INCOMPLETE"
    else:
        state = "STATIC_RESUME_READY"
    authority = data.get("authority", {})
    is_authoritative = (
        state == "STATIC_RESUME_READY"
        and isinstance(authority, dict)
        and bool(authority.get("authoritative"))
        and not bool(authority.get("synthetic"))
    )
    return {
        "state": state,
        "bundle_digest_sha256": digest_value(data),
        "errors": errors,
        "missing_authority": missing_declaration,
        "authoritative": is_authoritative,
    }


def refresh_derived(data, artifacts_by_role=None):
    artifacts_by_role = artifacts_by_role or {item["role"]: item for item in data.get("artifacts", [])}
    data["authority_contract_version"] = AUTHORITY_CONTRACT_VERSION
    data["installed_path_census_sha256"] = digest_value(installed_path_census_payload())
    environment = data["environment"]
    environment["policy_sha256"] = digest_value(environment["policy"])
    environment["observed_sha256"] = digest_value(environment["observed"])
    for actor in data["actors"]:
        actor["environment_policy_sha256"] = environment["policy_sha256"]
    crypto = data["crypto_linkage"]
    crypto["artifact_set_sha256"] = digest_value(artifact_set_payload(data))
    crypto["environment_sha256"] = digest_value({
        "policy_sha256": environment["policy_sha256"],
        "observed_sha256": environment["observed_sha256"],
    })
    crypto["event_graph_sha256"] = digest_value(event_graph_payload(data))
    crypto["confinement_sha256"] = digest_value(data["confinement"])
    capture = data["capture_identity"]
    for link in crypto["generation_links"]:
        output = artifacts_by_role.get(link["output_role"])
        generator = artifacts_by_role.get(link["generator_role"])
        inputs = [artifacts_by_role.get(role) for role in link["input_roles"]]
        if output is not None:
            link["output_sha256"] = output["sha256"]
        if generator is not None:
            link["generator_sha256"] = generator["sha256"]
        if all(item is not None for item in inputs):
            link["input_sha256"] = [item["sha256"] for item in inputs]
        for field in ("base_sha", "workflow_sha", "run_id", "job_id"):
            link[field] = capture[field]
        link["link_sha256"] = digest_value(generation_payload(link))
    crypto["authority_link_sha256"] = digest_value(authority_payload(data))


def hydrate_fixture(data, root):
    by_role = {item["role"]: item for item in data["artifacts"]}
    for artifact in data["artifacts"]:
        file_path = safe_bundle_path(root, artifact["bundle_path"])
        metadata = physical_metadata(file_path, artifact["metadata"]["mount_id"])
        artifact["size"] = file_path.stat().st_size
        artifact["sha256"] = digest_file(file_path)
        artifact["metadata"] = metadata
        artifact["installation"]["expected_metadata"] = copy.deepcopy(metadata)
    recipe = by_role["installation_recipe"]
    for artifact in data["artifacts"]:
        artifact["installation"]["recipe_sha256"] = recipe["sha256"]
    mount = data["confinement"]["mounts"][0]
    any_metadata = data["artifacts"][0]["metadata"]
    mount["device_id"] = any_metadata["device_id"]
    mount["filesystem"] = any_metadata["filesystem"]
    weights = data["confinement"]["weights_root"]
    weights["device_id"] = mount["device_id"]
    weights["filesystem"] = mount["filesystem"]
    profile = by_role[data["confinement"]["sandbox_profile_role"]]
    data["confinement"]["sandbox_profile_sha256"] = profile["sha256"]
    for event_item in data["events"]:
        artifact = by_role[event_item["command"]["artifact_role"]]
        event_item["command"]["artifact_sha256"] = artifact["sha256"]
    refresh_derived(data, by_role)


def remove_fixture_artifact(data, root, role, declare_missing):
    artifact = next(item for item in data["artifacts"] if item["role"] == role)
    safe_bundle_path(root, artifact["bundle_path"]).unlink()
    data["artifacts"] = [item for item in data["artifacts"] if item["role"] != role]
    if declare_missing:
        data["missing_authority"] = {
            "kind": "artifact_role",
            "role": role,
            "fact": "exact profile generator input bytes and installed metadata",
            "reason": "synthetic fixture intentionally omits the first unavailable authority fact",
        }


def mutate_fixture(name, data, root):
    by_role = {item["role"]: item for item in data["artifacts"]}
    target = by_role.get("bench_exec")
    if name == "none":
        return
    if name == "missing_profile_generator_input":
        remove_fixture_artifact(data, root, "profile_generator_input", True)
        refresh_derived(data)
        return
    if name == "unknown_field":
        data["unexpected_field"] = "synthetic"
        refresh_derived(data)
        return
    if name == "unknown_secret_field":
        data["api_token"] = "synthetic-redacted-probe"
        refresh_derived(data)
        return
    if name == "jointly_omitted_roles":
        remove_fixture_artifact(data, root, "profile_generator_input", False)
        data["required_artifact_roles"].remove("profile_generator_input")
        refresh_derived(data)
        return
    if name == "installed_path_alias":
        target["installed_path"] = "/opt/bench/../bench/bench-exec.sh"
        refresh_derived(data)
        return
    if name == "byte_drift":
        with safe_bundle_path(root, target["bundle_path"]).open("ab") as handle:
            handle.write(b"drift\n")
        return
    if name == "hash_drift":
        target["sha256"] = "f" * 64
        refresh_derived(data)
        return
    if name == "size_drift":
        target["size"] += 1
        refresh_derived(data)
        return
    if name == "path_escape":
        target["bundle_path"] = "../escape"
        refresh_derived(data)
        return
    if name == "symlink":
        file_path = safe_bundle_path(root, target["bundle_path"])
        file_path.unlink()
        file_path.symlink_to("measure-job.sh")
        return
    if name == "duplicate_role":
        data["artifacts"].append(copy.deepcopy(target))
        refresh_derived(data)
        return
    if name == "owner_mismatch":
        target["metadata"]["owner_uid"] += 1
        target["installation"]["expected_metadata"] = copy.deepcopy(target["metadata"])
        refresh_derived(data)
        return
    if name == "mode_mismatch":
        target["metadata"]["mode"] = "0600"
        target["installation"]["expected_metadata"] = copy.deepcopy(target["metadata"])
        refresh_derived(data)
        return
    if name == "acl_mismatch":
        text = "0: user:synthetic:read"
        target["metadata"]["acl"] = {"normalized_text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        target["installation"]["expected_metadata"] = copy.deepcopy(target["metadata"])
        refresh_derived(data)
        return
    if name == "hardlink_ambiguity":
        os.link(safe_bundle_path(root, target["bundle_path"]), root / "artifacts" / "bench-exec-hardlink.sh")
        return
    if name in {"workflow_drift", "base_drift", "job_drift"}:
        field = {"workflow_drift": "workflow_sha", "base_drift": "base_sha", "job_drift": "job_id"}[name]
        data["capture_identity"][field] = ("e" * 40) if field.endswith("sha") else "synthetic-job-drift"
        refresh_derived(data)
        return
    if name == "stale_capture":
        data["authority"]["captured_at"] = "2026-01-01T00:00:00Z"
        return
    if name == "missing_install_provenance":
        del target["installation"]["package"]
        refresh_derived(data)
        return
    if name == "profile_hash_mismatch":
        data["confinement"]["sandbox_profile_sha256"] = "d" * 64
        refresh_derived(data)
        return
    if name == "secret_leak":
        data["environment"]["observed"][1]["redacted"] = False
        data["environment"]["observed"][1]["value"] = "synthetic-secret-value"
        refresh_derived(data)
        return
    if name == "undeclared_environment":
        data["environment"]["observed"].append({"actor_id": "worker", "name": "UNDECLARED_SYNTHETIC", "value": "x"})
        refresh_derived(data)
        return
    if name == "missing_environment_observation":
        data["environment"]["observed"].pop()
        refresh_derived(data)
        return
    if name == "unknown_environment_actor":
        data["environment"]["observed"][0]["actor_id"] = "intruder"
        refresh_derived(data)
        return
    if name == "transition_contradiction":
        data["phases"][3]["transition"]["to_uid"] += 1
        refresh_derived(data)
        return
    if name == "survivor_contradiction":
        reaper = next(item for item in data["events"] if item["type"] == "reaper")
        reaper["survivor_policy"]["residual_survivors"] = "fail"
        refresh_derived(data)
        return
    if name == "event_cycle":
        data["event_edges"].append({"from": "load-end", "to": "transform", "type": "happens_before"})
        refresh_derived(data)
        return
    if name == "order_reversal":
        sandbox = next(item for item in data["events"] if item["type"] == "sandbox_injected")
        sandbox["sequence"] = 3
        refresh_derived(data)
        return
    if name == "early_chain_edge_reversal":
        edge = next(item for item in data["event_edges"] if item["from"] == "transform")
        edge["from"], edge["to"] = edge["to"], edge["from"]
        refresh_derived(data)
        return
    if name in {"timestamp_reversal", "incomplete_timestamp_reversal"}:
        if name.startswith("incomplete_"):
            remove_fixture_artifact(data, root, "profile_generator_input", True)
        trusted_hash = next(item for item in data["events"] if item["id"] == "trusted-hash")
        trusted_hash["timestamp"] = "2026-08-10T12:00:00Z"
        refresh_derived(data)
        return
    if name == "generation_event_drift":
        data["crypto_linkage"]["generation_links"][0]["event_id"] = "sandbox-injected"
        refresh_derived(data)
        return
    if name in {"generator_confinement_drift", "incomplete_generator_drift"}:
        if name.startswith("incomplete_"):
            remove_fixture_artifact(data, root, "profile_generator_input", True)
        data["confinement"]["profile_generator_role"] = "worker_launcher"
        refresh_derived(data)
        return
    if name == "missing_capability":
        data["confinement"]["capabilities"].pop()
        refresh_derived(data)
        return
    if name == "mount_path_contradiction":
        data["confinement"]["weights_root"]["device_id"] += 1
        refresh_derived(data)
        return
    if name == "absent_declared_artifact":
        safe_bundle_path(root, target["bundle_path"]).unlink()
        return
    raise ValueError(f"unknown fixture mutation: {name}")


def run_fixture_suite(fixture_path):
    fixture_document = json.loads(fixture_path.read_text())
    if fixture_document.get("schema_version") != FIXTURE_VERSION or fixture_document.get("non_authoritative") is not True:
        raise ValueError("fixture document must be explicitly synthetic and non-authoritative")
    results = []
    failures = []
    for case in fixture_document["cases"]:
        with tempfile.TemporaryDirectory(prefix="ranked-authority-fixture-") as temporary:
            root = Path(temporary)
            for relative, specification in fixture_document["files"].items():
                destination = safe_bundle_path(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(specification["text"].encode())
                destination.chmod(int(specification["mode"], 8))
            data = copy.deepcopy(fixture_document["base_bundle"])
            hydrate_fixture(data, root)
            mutate_fixture(case["mutation"], data, root)
            result = validate_bundle(data, root)
        actual_codes = sorted({item["code"] for item in result["errors"]})
        expected_codes = sorted(case.get("expected_error_codes", []))
        passed = result["state"] == case["expected_state"] and all(code in actual_codes for code in expected_codes)
        case_result = {
            "id": case["id"],
            "state": result["state"],
            "bundle_digest_sha256": result["bundle_digest_sha256"],
            "error_codes": actual_codes,
            "passed": passed,
        }
        if result["state"] == "INCOMPLETE":
            case_result["missing_authority"] = result["missing_authority"]
        results.append(case_result)
        if not passed:
            failures.append({
                "id": case["id"],
                "expected_state": case["expected_state"],
                "actual_state": result["state"],
                "expected_error_codes": expected_codes,
                "actual_error_codes": actual_codes,
            })
    output = {
        "schema_version": "ranked-authority-evidence-fixture-results/v2",
        "fixture_source_sha256": digest_file(fixture_path),
        "non_authoritative": True,
        "case_count": len(results),
        "passed": not failures,
        "results": results,
        "failures": failures,
    }
    return output


_validate_events_v2 = validate_events
_validate_confinement_v2 = validate_confinement
_mutate_fixture_v2 = mutate_fixture


def installed_path_census_payload(census):
    return sorted(
        ({"role": item.get("role"), "installed_path": item.get("installed_path")} for item in census),
        key=lambda item: (item["role"] or "", item["installed_path"] or ""),
    )


def compare_identity(errors, target, capture):
    fields = {
        "repository": "IDENTITY_REPOSITORY_DRIFT",
        "base_sha": "IDENTITY_BASE_DRIFT",
        "workflow_sha": "IDENTITY_WORKFLOW_DRIFT",
        "run_id": "IDENTITY_RUN_DRIFT",
        "job_id": "IDENTITY_JOB_DRIFT",
        "workflow_path": "IDENTITY_WORKFLOW_DRIFT",
        "workflow_blob_sha": "IDENTITY_WORKFLOW_DRIFT",
        "workflow_file_sha256": "IDENTITY_WORKFLOW_DRIFT",
    }
    for field, code in fields.items():
        if target.get(field) != capture.get(field):
            errors.append(error(code, f"capture_identity.{field}", "captured identity does not match the requested ranked authority"))


def installed_mount_payload(data):
    return sorted(
        (
            {
                "role": item.get("role"),
                "installed_path": item.get("installed_path"),
                "sha256": item.get("sha256"),
                "installed_metadata": item.get("installed_metadata"),
            }
            for item in data.get("artifacts", [])
        ),
        key=lambda item: (item["role"] or "", item["installed_path"] or ""),
    )


def collector_attestation_payload(data, trust):
    collector = copy.deepcopy(trust.get("trusted_collector", {}))
    return {
        "authority": data.get("authority"),
        "target_identity": data.get("target_identity"),
        "capture_identity": data.get("capture_identity"),
        "missing_authority": data.get("missing_authority"),
        "source_kind": trust.get("source_kind"),
        "scope": trust.get("scope"),
        "accepted_target_identity": trust.get("accepted_target_identity"),
        "expected_authority": trust.get("expected_authority"),
        "trusted_collector": collector,
        "installed_path_census": installed_path_census_payload(trust.get("installed_path_census", [])),
        "installed_path_census_sha256": trust.get("installed_path_census_sha256"),
        "census_complete": trust.get("census_complete"),
        "first_missing_fact": trust.get("first_missing_fact"),
        "command_policies": sorted(trust.get("command_policies", []), key=lambda item: item.get("event_type", "")),
        "installed_artifacts": installed_mount_payload(data),
    }


def authenticate_external_trust(errors, trust, expected_sha256):
    if not isinstance(trust, dict):
        errors.append(error("EXTERNAL_TRUST_REQUIRED", "$external_trust", "a separate verifier-owned trust document is required"))
        return False
    if expected_sha256 is None:
        errors.append(error("EXTERNAL_TRUST_PIN_REQUIRED", "$external_trust_sha256", "a verifier-owned SHA-256 pin is required"))
        return False
    if not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        errors.append(error("EXTERNAL_TRUST_PIN_INVALID", "$external_trust_sha256", "external trust pin must be exactly 64 lowercase hexadecimal characters"))
        return False
    if digest_value(trust) != expected_sha256:
        errors.append(error("EXTERNAL_TRUST_PIN_MISMATCH", "$external_trust_sha256", "canonical external trust document differs from the verifier-owned pin"))
        return False
    return True


def validate_external_trust(errors, data, trust):
    schema = json.loads(SCHEMA_PATH.read_text())
    validate_schema_instance(trust, schema["$defs"]["externalTrust"], schema, "$external_trust", errors)
    scan_for_secret_fields(trust, errors, "$external_trust")
    if trust.get("schema_version") != TRUST_SCHEMA_VERSION:
        errors.append(error("TRUST_SCHEMA_VERSION", "$external_trust.schema_version", f"expected {TRUST_SCHEMA_VERSION}"))
    if trust.get("authority_contract_version") != AUTHORITY_CONTRACT_VERSION:
        errors.append(error("TRUST_CONTRACT_VERSION", "$external_trust.authority_contract_version", f"expected {AUTHORITY_CONTRACT_VERSION}"))
    if trust.get("scope") != RANKED_SCOPE:
        errors.append(error("TRUST_SCOPE_MISMATCH", "$external_trust.scope", "external trust does not pin the exact PR #671 audit boundary"))
    if trust.get("accepted_target_identity") != data.get("target_identity"):
        errors.append(error("TRUST_TARGET_IDENTITY_MISMATCH", "$external_trust.accepted_target_identity", "bundle target identity is not accepted by the verifier-owned trust root"))
    if trust.get("expected_authority") != data.get("authority"):
        errors.append(error("TRUST_AUTHORITY_MISMATCH", "$external_trust.expected_authority", "bundle authority claims differ from verifier-owned expectations"))

    collector = trust.get("trusted_collector", {})
    authority = data.get("authority", {})
    if collector.get("id") != authority.get("trusted_collector") or collector.get("authority") != authority.get("collector_authority"):
        errors.append(error("TRUST_COLLECTOR_MISMATCH", "$external_trust.trusted_collector", "collector identity or authority differs from the bundle claim"))

    census = trust.get("installed_path_census", [])
    census_by_role = {}
    seen_paths = set()
    for index, item in enumerate(census if isinstance(census, list) else []):
        role = item.get("role") if isinstance(item, dict) else None
        installed_path = item.get("installed_path") if isinstance(item, dict) else None
        if role in census_by_role:
            errors.append(error("TRUST_CENSUS_DUPLICATE_ROLE", f"$external_trust.installed_path_census[{index}]", "installed role appears twice"))
        elif role:
            census_by_role[role] = item
        if not canonical_absolute_path(installed_path):
            errors.append(error("INSTALLED_PATH_NONCANONICAL", f"$external_trust.installed_path_census[{index}].installed_path", "trusted installed path must be canonical and absolute"))
        if installed_path in seen_paths:
            errors.append(error("TRUST_CENSUS_DUPLICATE_PATH", f"$external_trust.installed_path_census[{index}]", "installed path appears twice"))
        seen_paths.add(installed_path)
    census_digest = digest_value(installed_path_census_payload(census))
    if trust.get("installed_path_census_sha256") != census_digest:
        errors.append(error("TRUST_CENSUS_DIGEST_MISMATCH", "$external_trust.installed_path_census_sha256", "trusted installed-path census digest is incorrect"))
    if data.get("installed_path_census_sha256") != census_digest:
        errors.append(error("INSTALLED_PATH_CENSUS_DIGEST_MISMATCH", "installed_path_census_sha256", "bundle does not bind the verifier-owned installed-path census"))

    missing = data.get("missing_authority")
    complete = trust.get("census_complete") is True
    expected_roles = set(MANDATORY_ROLES)
    census_roles = set(census_by_role)
    if complete:
        if census_roles != expected_roles:
            errors.append(error("TRUST_CENSUS_MISMATCH", "$external_trust.installed_path_census", "complete trust must cover every mandatory authority role"))
        if trust.get("first_missing_fact") is not None or missing is not None:
            errors.append(error("TRUST_COMPLETENESS_CONTRADICTION", "$external_trust.census_complete", "complete trust cannot declare a missing authority fact"))
    else:
        missing_role = missing.get("role") if isinstance(missing, dict) else None
        if trust.get("first_missing_fact") != missing:
            errors.append(error("TRUST_MISSING_FACT_MISMATCH", "$external_trust.first_missing_fact", "first missing fact must equal the bundle declaration"))
        if missing_role is None or census_roles != expected_roles - {missing_role}:
            errors.append(error("TRUST_CENSUS_MISMATCH", "$external_trust.installed_path_census", "incomplete trust must stop at exactly one declared missing role"))

    if trust.get("source_kind") == "ranked":
        identity = trust.get("accepted_target_identity", {})
        ranked_identity = {
            "repository": "morganmcg1/mlxfast-challenge_senpai",
            "base_sha": RANKED_SCOPE["audited_base_sha"],
            "workflow_path": RANKED_SCOPE["workflow_path"],
            "workflow_blob_sha": RANKED_SCOPE["workflow_blob_sha"],
            "workflow_file_sha256": RANKED_SCOPE["workflow_file_sha256"],
        }
        for field, expected in ranked_identity.items():
            if identity.get(field) != expected:
                errors.append(error("TRUST_RANKED_IDENTITY_MISMATCH", f"$external_trust.accepted_target_identity.{field}", "ranked trust must pin the source-backed audited identity"))
        for role, expected in KNOWN_RANKED_PATHS.items():
            if census_by_role.get(role, {}).get("installed_path") != expected:
                errors.append(error("TRUST_CENSUS_MISMATCH", f"$external_trust.installed_path_census[{role}]", "ranked trust contradicts a source-backed installed path"))

    policy_by_type = {}
    for index, policy in enumerate(trust.get("command_policies", [])):
        event_type = policy.get("event_type") if isinstance(policy, dict) else None
        if event_type in policy_by_type:
            errors.append(error("TRUST_COMMAND_POLICY_DUPLICATE", f"$external_trust.command_policies[{index}]", "command policy event type appears twice"))
        elif event_type:
            policy_by_type[event_type] = policy
    expected_types = {item[1] for item in EXPECTED_EVENTS}
    if set(policy_by_type) != expected_types:
        errors.append(error("TRUST_COMMAND_POLICY_CENSUS_MISMATCH", "$external_trust.command_policies", "external trust must bind every required event type exactly once"))

    mount_digest = digest_value(installed_mount_payload(data))
    if collector.get("installation_mount_identity_sha256") != mount_digest:
        errors.append(error("TRUST_MOUNT_IDENTITY_MISMATCH", "$external_trust.trusted_collector.installation_mount_identity_sha256", "collector-attested installed metadata or mount identity changed"))
    if trust.get("collector_attestation_sha256") != digest_value(collector_attestation_payload(data, trust)):
        errors.append(error("COLLECTOR_ATTESTATION_MISMATCH", "$external_trust.collector_attestation_sha256", "verifier-owned collector attestation does not match the bundle and trust facts"))
    return census_by_role, policy_by_type, complete


def validate_artifacts(errors, data, root, missing_role, census_by_role):
    artifacts = data.get("artifacts", [])
    required = data.get("required_artifact_roles", [])
    if len(required) != len(set(required)):
        errors.append(error("DUPLICATE_REQUIRED_ROLE", "required_artifact_roles", "required artifact roles must be unique"))
    if set(required) != MANDATORY_ROLES or len(required) != len(MANDATORY_ROLES):
        errors.append(error("MANDATORY_ROLE_CENSUS_MISMATCH", "required_artifact_roles", "required roles must equal the versioned PR #671 authority census"))
    by_role = {}
    bundle_paths = set()
    installed_paths = set()
    for index, artifact in enumerate(artifacts if isinstance(artifacts, list) else []):
        path = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            continue
        role = artifact.get("role")
        if role in by_role:
            errors.append(error("DUPLICATE_ARTIFACT_ROLE", f"{path}.role", "artifact role appears more than once"))
            continue
        by_role[role] = artifact
        if artifact.get("bundle_path") in bundle_paths:
            errors.append(error("BUNDLE_PATH_COLLISION", f"{path}.bundle_path", "two artifacts use the same bundle path"))
        bundle_paths.add(artifact.get("bundle_path"))
        installed_path = artifact.get("installed_path")
        if not canonical_absolute_path(installed_path):
            errors.append(error("INSTALLED_PATH_NONCANONICAL", f"{path}.installed_path", "installed path must be canonical and absolute"))
        if installed_path in installed_paths:
            errors.append(error("INSTALLED_PATH_COLLISION", f"{path}.installed_path", "two roles claim the same installed path"))
        installed_paths.add(installed_path)
        trusted_path = census_by_role.get(role, {}).get("installed_path")
        if trusted_path != installed_path:
            errors.append(error("TRUST_CENSUS_MISMATCH", f"{path}.installed_path", "bundle installed path differs from verifier-owned census"))
        if role in KNOWN_RANKED_PATHS and census_by_role.get(role, {}).get("installed_path") == KNOWN_RANKED_PATHS[role] and installed_path != KNOWN_RANKED_PATHS[role]:
            errors.append(error("INSTALLED_PATH_CENSUS_MISMATCH", f"{path}.installed_path", "installed path contradicts the source-backed ranked path"))

        candidate = safe_bundle_path(root, artifact.get("bundle_path"))
        if candidate is None:
            errors.append(error("BUNDLE_PATH_ESCAPE", f"{path}.bundle_path", "bundle path must remain below the evidence root"))
            continue
        if not candidate.exists() and not candidate.is_symlink():
            errors.append(error("PHYSICAL_FILE_MISSING", f"{path}.bundle_path", "declared artifact has no matching physical file"))
            continue
        metadata = artifact.get("bundle_metadata")
        if not isinstance(metadata, dict):
            errors.append(error("ARTIFACT_METADATA_MISSING", f"{path}.bundle_metadata", "copied bundle metadata is required"))
            continue
        actual = physical_metadata(candidate, metadata.get("mount_id", "unknown"))
        if actual["symlink"]:
            errors.append(error("PHYSICAL_SYMLINK", f"{path}.bundle_path", "authority artifacts must not be symbolic links"))
            continue
        if not candidate.is_file():
            errors.append(error("PHYSICAL_NONREGULAR", f"{path}.bundle_path", "authority artifacts must be regular files"))
            continue
        if candidate.stat().st_size != artifact.get("size"):
            errors.append(error("PHYSICAL_SIZE_MISMATCH", f"{path}.size", "declared size does not match physical bytes"))
        if digest_file(candidate) != artifact.get("sha256"):
            errors.append(error("PHYSICAL_HASH_MISMATCH", f"{path}.sha256", "declared hash does not match physical bytes"))
        checks = (
            ("owner_uid", "PHYSICAL_OWNER_UID_MISMATCH"), ("owner_gid", "PHYSICAL_OWNER_GID_MISMATCH"),
            ("mode", "PHYSICAL_MODE_MISMATCH"), ("acl", "PHYSICAL_ACL_MISMATCH"),
            ("flags", "PHYSICAL_FLAGS_MISMATCH"), ("link_count", "PHYSICAL_LINK_COUNT_MISMATCH"),
            ("symlink", "PHYSICAL_SYMLINK_DECLARATION_MISMATCH"), ("device_id", "PHYSICAL_DEVICE_MISMATCH"),
            ("filesystem", "PHYSICAL_FILESYSTEM_MISMATCH"),
        )
        for field, code in checks:
            if metadata.get(field) != actual.get(field):
                errors.append(error(code, f"{path}.bundle_metadata.{field}", "copied bundle metadata differs from the physical artifact"))
        if actual.get("link_count") != 1:
            errors.append(error("HARDLINK_AMBIGUITY", f"{path}.bundle_metadata.link_count", "authority artifact has multiple physical names"))
        installation = artifact.get("installation")
        if not isinstance(installation, dict):
            errors.append(error("INSTALL_PROVENANCE_MISSING", f"{path}.installation", "installation provenance is required"))
            continue
        package = installation.get("package")
        if not isinstance(package, dict) or not all(package.get(key) for key in ("name", "version", "digest_sha256")):
            errors.append(error("INSTALL_PROVENANCE_MISSING", f"{path}.installation.package", "package name, version, and digest are required"))
        if installation.get("expected_metadata") != artifact.get("installed_metadata"):
            errors.append(error("INSTALL_METADATA_MISMATCH", f"{path}.installation.expected_metadata", "installation provenance must bind collector-attested installed metadata"))
    for role, artifact in by_role.items():
        installation = artifact.get("installation", {})
        recipe_role = installation.get("recipe_role")
        if recipe_role == missing_role:
            continue
        recipe = by_role.get(recipe_role)
        if recipe is None:
            errors.append(error("INSTALL_RECIPE_MISSING", f"artifacts[{role}].installation.recipe_role", "referenced installation recipe artifact is absent"))
        elif installation.get("recipe_sha256") != recipe.get("sha256"):
            errors.append(error("INSTALL_RECIPE_HASH_MISMATCH", f"artifacts[{role}].installation.recipe_sha256", "installation recipe hash does not match its artifact declaration"))
    observed_roles = set(by_role)
    absent = sorted(MANDATORY_ROLES - observed_roles)
    extra = sorted(observed_roles - MANDATORY_ROLES)
    if extra:
        errors.append(error("ARTIFACT_ROLE_CENSUS_MISMATCH", "artifacts", f"unknown roles are present: {extra}"))
    if absent != ([missing_role] if missing_role else []):
        code = "MULTIPLE_MISSING_AUTHORITIES" if len(absent) > 1 else "MISSING_AUTHORITY_UNDECLARED"
        errors.append(error(code, "artifacts", f"artifact absence does not match the first missing authority: {absent}"))
    return by_role


def validate_events(errors, data, artifacts, actors, started, finished, missing_role, policies, census):
    by_id, by_type = _validate_events_v2(errors, data, artifacts, actors, started, finished, missing_role)
    for index, event_item in enumerate(data.get("events", [])):
        command = event_item.get("command", {})
        role = command.get("artifact_role")
        artifact = artifacts.get(role)
        trusted_path = census.get(role, {}).get("installed_path")
        policy = policies.get(event_item.get("type"))
        path = f"events[{index}].command"
        if policy is None:
            continue
        if policy.get("event_actor_id") != event_item.get("actor_id") or policy.get("primary_role") != role:
            errors.append(error("COMMAND_POLICY_BINDING_MISMATCH", path, "event actor or primary role differs from external trust"))
        if artifact is None and role == missing_role:
            continue
        if artifact is None:
            continue
        if command.get("artifact_sha256") != artifact.get("sha256"):
            errors.append(error("EVENT_COMMAND_HASH_MISMATCH", f"{path}.artifact_sha256", "primary executable hash differs from captured artifact"))
        if command.get("executable_path") != artifact.get("installed_path") or command.get("executable_path") != trusted_path:
            errors.append(error("COMMAND_EXECUTABLE_PATH_MISMATCH", f"{path}.executable_path", "primary executable path differs from verifier-owned census"))
        argv = command.get("argv", [])
        if not argv or argv[0] != command.get("executable_path"):
            errors.append(error("COMMAND_ARGV0_MISMATCH", f"{path}.argv[0]", "argv[0] must equal the bound executable path"))
        argv_digest = digest_value(argv)
        if command.get("argv_sha256") != argv_digest or policy.get("argv_sha256") != argv_digest:
            errors.append(error("COMMAND_ARGV_DIGEST_MISMATCH", f"{path}.argv_sha256", "argv differs from the externally trusted command"))
        chain = command.get("exec_chain", [])
        chain_roles = [item.get("artifact_role") for item in chain if isinstance(item, dict)]
        if chain_roles != policy.get("exec_chain_roles"):
            errors.append(error("COMMAND_CHAIN_POLICY_MISMATCH", f"{path}.exec_chain", "launcher/worker chain differs from external trust"))
        for chain_index, item in enumerate(chain):
            chain_role = item.get("artifact_role") if isinstance(item, dict) else None
            chain_artifact = artifacts.get(chain_role)
            trusted_chain_path = census.get(chain_role, {}).get("installed_path")
            if chain_artifact is None:
                errors.append(error("COMMAND_CHAIN_ARTIFACT_MISSING", f"{path}.exec_chain[{chain_index}]", "chain artifact is absent"))
                continue
            if (
                item.get("installed_path") != chain_artifact.get("installed_path")
                or item.get("installed_path") != trusted_chain_path
                or item.get("artifact_sha256") != chain_artifact.get("sha256")
            ):
                errors.append(error("COMMAND_CHAIN_IDENTITY_MISMATCH", f"{path}.exec_chain[{chain_index}]", "chain identity differs from captured artifacts or verifier-owned census"))
        process = command.get("process_start", {})
        actor = actors.get(process.get("actor_id"))
        last_role = chain_roles[-1] if chain_roles else None
        last_artifact = artifacts.get(last_role)
        process_expected = (
            policy.get("process_actor_id"),
            actor.get("pid") if actor else None,
            actor.get("ppid") if actor else None,
            last_role,
            census.get(last_role, {}).get("installed_path"),
            last_artifact.get("sha256") if last_artifact else None,
            event_item.get("timestamp"),
        )
        process_actual = (
            process.get("actor_id"), process.get("pid"), process.get("ppid"), process.get("executable_role"),
            process.get("executable_path"), process.get("executable_sha256"), process.get("started_at"),
        )
        if process_actual != process_expected:
            errors.append(error("PROCESS_START_IDENTITY_MISMATCH", f"{path}.process_start", "process start identity differs from actor, chain, or event evidence"))
        parent_actor_id = actor.get("parent_actor_id") if actor else None
        parent_actor = actors.get(parent_actor_id)
        if parent_actor_id is not None and parent_actor is not None and process.get("ppid") != parent_actor.get("pid"):
            errors.append(error("PROCESS_PARENT_ACTOR_PID_MISMATCH", f"{path}.process_start.ppid", "process parent PID differs from the declared parent actor PID"))
    return by_id, by_type


def validate_confinement(errors, data, artifacts, phases, missing_role):
    legacy_artifacts = {role: {**artifact, "metadata": artifact.get("bundle_metadata", {})} for role, artifact in artifacts.items()}
    _validate_confinement_v2(errors, data, legacy_artifacts, phases, missing_role)


def authority_payload(data):
    crypto = data.get("crypto_linkage", {})
    return {
        "authority": data.get("authority"),
        "missing_authority": data.get("missing_authority"),
        "required_artifact_roles": data.get("required_artifact_roles"),
        "installed_path_census_sha256": data.get("installed_path_census_sha256"),
        "target_identity": data.get("target_identity"),
        "capture_identity": data.get("capture_identity"),
        "artifact_set_sha256": crypto.get("artifact_set_sha256"),
        "environment_sha256": crypto.get("environment_sha256"),
        "event_graph_sha256": crypto.get("event_graph_sha256"),
        "confinement_sha256": crypto.get("confinement_sha256"),
        "generation_link_sha256": [item.get("link_sha256") for item in crypto.get("generation_links", [])],
    }


def validate_crypto(errors, data, artifacts, missing_role):
    crypto = data.get("crypto_linkage", {})
    expected = {
        "artifact_set_sha256": digest_value(artifact_set_payload(data)),
        "environment_sha256": digest_value({
            "policy_sha256": data.get("environment", {}).get("policy_sha256"),
            "observed_sha256": data.get("environment", {}).get("observed_sha256"),
        }),
        "event_graph_sha256": digest_value(event_graph_payload(data)),
        "confinement_sha256": digest_value(data.get("confinement")),
    }
    codes = {
        "artifact_set_sha256": "ARTIFACT_SET_DIGEST_MISMATCH", "environment_sha256": "ENVIRONMENT_LINK_DIGEST_MISMATCH",
        "event_graph_sha256": "EVENT_GRAPH_DIGEST_MISMATCH", "confinement_sha256": "CONFINEMENT_DIGEST_MISMATCH",
    }
    for field, value in expected.items():
        if crypto.get(field) != value:
            errors.append(error(codes[field], f"crypto_linkage.{field}", "cryptographic linkage digest is incorrect"))
    events = {item.get("id"): item for item in data.get("events", []) if isinstance(item, dict)}
    confinement = data.get("confinement", {})
    capture = data.get("capture_identity", {})
    expected_roles = ("worker_sandbox_profile", "worker_sandbox_profile_generator", ["profile_generator_input"])
    generation_command_roles = ("worker_sandbox_profile_generator", "profile_generator_input", "worker_sandbox_profile")
    expected_argv = [artifacts.get(role, {}).get("installed_path") for role in generation_command_roles]
    for index, link in enumerate(crypto.get("generation_links", [])):
        path = f"crypto_linkage.generation_links[{index}]"
        linked_roles = (link.get("output_role"), link.get("generator_role"), link.get("input_roles"))
        if linked_roles != expected_roles or linked_roles != (
            confinement.get("sandbox_profile_role"), confinement.get("profile_generator_role"), confinement.get("profile_generator_input_roles")
        ):
            errors.append(error("GENERATION_ROLE_DRIFT", path, "generation roles differ from the ranked confinement contract"))
        event_item = events.get(link.get("event_id"))
        actual_argv = event_item.get("command", {}).get("argv", []) if event_item else []
        argv_matches = len(actual_argv) == len(expected_argv) and all(
            canonical_absolute_path(actual) if role == missing_role else actual == expected
            for role, actual, expected in zip(generation_command_roles, actual_argv, expected_argv)
        )
        if link.get("event_id") != "profile-generated" or event_item is None or link.get("generated_at") != event_item.get("timestamp") or not argv_matches:
            errors.append(error("GENERATION_EVENT_DRIFT", path, "generation link does not exactly match the profile-generated event"))
        output = artifacts.get(link.get("output_role"))
        generator = artifacts.get(link.get("generator_role"))
        inputs = [artifacts.get(role) for role in link.get("input_roles", [])]
        absent = [role for role, item in zip([link.get("output_role"), link.get("generator_role")] + link.get("input_roles", []), [output, generator] + inputs) if item is None]
        if any(role != missing_role for role in absent):
            errors.append(error("GENERATION_ARTIFACT_MISSING", path, f"generation link references absent artifacts: {absent}"))
        if output and generator and (link.get("output_sha256") != output.get("sha256") or link.get("generator_sha256") != generator.get("sha256")):
            errors.append(error("GENERATION_HASH_MISMATCH", path, "generation output or generator hash differs from artifacts"))
        if all(inputs) and link.get("input_sha256") != [item.get("sha256") for item in inputs]:
            errors.append(error("GENERATION_INPUT_HASH_MISMATCH", path, "generation input hashes differ from artifacts"))
        for field in ("base_sha", "workflow_sha", "run_id", "job_id"):
            if link.get(field) != capture.get(field):
                errors.append(error("GENERATION_IDENTITY_DRIFT", f"{path}.{field}", "generation identity differs from capture identity"))
        if link.get("link_sha256") != digest_value(generation_payload(link)):
            errors.append(error("GENERATION_LINK_DIGEST_MISMATCH", f"{path}.link_sha256", "generation link digest is incorrect"))
    if crypto.get("authority_link_sha256") != digest_value(authority_payload(data)):
        errors.append(error("AUTHORITY_LINK_DIGEST_MISMATCH", "crypto_linkage.authority_link_sha256", "authority claims are not included in authenticated linkage"))


def validate_bundle(data, root, external_trust=None, expected_external_trust_sha256=None):
    errors = []
    if not isinstance(data, dict):
        return {"state": "INVALID", "bundle_digest_sha256": digest_value(data), "errors": [error("TOP_LEVEL_TYPE", "$", "bundle must be an object")], "missing_authority": None, "authoritative": False, "resumption_authorized": False}
    errors.extend(validate_committed_schema(data))
    scan_for_secret_fields(data, errors)
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("SCHEMA_VERSION", "schema_version", f"expected {SCHEMA_VERSION}"))
    if data.get("authority_contract_version") != AUTHORITY_CONTRACT_VERSION:
        errors.append(error("AUTHORITY_CONTRACT_VERSION", "authority_contract_version", f"expected {AUTHORITY_CONTRACT_VERSION}"))
    missing = data.get("missing_authority")
    missing_role = missing.get("role") if isinstance(missing, dict) else None
    trust_authenticated = authenticate_external_trust(errors, external_trust, expected_external_trust_sha256)
    if not trust_authenticated:
        errors = sorted(errors, key=lambda item: (item["code"], item["path"], item["message"]))
        return {
            "state": "INVALID",
            "bundle_digest_sha256": digest_value(data),
            "errors": errors,
            "missing_authority": missing,
            "authoritative": False,
            "resumption_authorized": False,
        }
    try:
        census, policies, trust_complete = validate_external_trust(errors, data, external_trust)
        compare_identity(errors, data.get("target_identity", {}), data.get("capture_identity", {}))
        started, finished = validate_capture_window(errors, data)
        artifacts = validate_artifacts(errors, data, root, missing_role, census)
        validate_environment(errors, data)
        actors, phases = validate_actors_and_phases(errors, data, artifacts)
        validate_events(errors, data, artifacts, actors, started, finished, missing_role, policies, census)
        validate_confinement(errors, data, artifacts, phases, missing_role)
        validate_crypto(errors, data, artifacts, missing_role)
    except (AttributeError, KeyError, TypeError, ValueError, OSError) as exception:
        errors.append(error("VALIDATOR_INPUT_UNSAFE", "$", f"malformed input prevented semantic validation: {type(exception).__name__}"))
        trust_complete = False
    errors = sorted(errors, key=lambda item: (item["code"], item["path"], item["message"]))
    state = "INVALID" if errors else ("INCOMPLETE" if missing_role or not trust_complete else "STATIC_RESUME_READY")
    authority = data.get("authority", {})
    authorized = (
        state == "STATIC_RESUME_READY"
        and trust_authenticated
        and external_trust.get("source_kind") == "ranked"
        and external_trust.get("census_complete") is True
        and authority.get("authoritative") is True
        and authority.get("synthetic") is False
    )
    return {
        "state": state,
        "bundle_digest_sha256": digest_value(data),
        "errors": errors,
        "missing_authority": missing,
        "authoritative": authorized,
        "resumption_authorized": authorized,
    }


def seal_bundle_commands(data):
    artifacts = {item["role"]: item for item in data.get("artifacts", [])}
    actors = {item["id"]: item for item in data.get("actors", [])}
    for event_item in data.get("events", []):
        command = event_item["command"]
        primary = artifacts.get(command["artifact_role"])
        if primary:
            command["artifact_sha256"] = primary["sha256"]
            command["executable_path"] = primary["installed_path"]
        command["argv_sha256"] = digest_value(command["argv"])
        for entry in command["exec_chain"]:
            artifact = artifacts.get(entry["artifact_role"])
            if artifact:
                entry["installed_path"] = artifact["installed_path"]
                entry["artifact_sha256"] = artifact["sha256"]
        process = command["process_start"]
        actor = actors.get(process["actor_id"])
        if actor:
            process["pid"] = actor["pid"]
            process["ppid"] = actor["ppid"]
        if command["exec_chain"]:
            last = artifacts.get(command["exec_chain"][-1]["artifact_role"])
            if last:
                process["executable_role"] = last["role"]
                process["executable_path"] = last["installed_path"]
                process["executable_sha256"] = last["sha256"]
        process["started_at"] = event_item["timestamp"]


def refresh_derived(data, artifacts_by_role=None):
    artifacts_by_role = artifacts_by_role or {item["role"]: item for item in data.get("artifacts", [])}
    data["authority_contract_version"] = AUTHORITY_CONTRACT_VERSION
    data["installed_path_census_sha256"] = digest_value(installed_path_census_payload(data.get("artifacts", [])))
    environment = data["environment"]
    environment["policy_sha256"] = digest_value(environment["policy"])
    environment["observed_sha256"] = digest_value(environment["observed"])
    for actor in data["actors"]:
        actor["environment_policy_sha256"] = environment["policy_sha256"]
    crypto = data["crypto_linkage"]
    crypto["artifact_set_sha256"] = digest_value(artifact_set_payload(data))
    crypto["environment_sha256"] = digest_value({"policy_sha256": environment["policy_sha256"], "observed_sha256": environment["observed_sha256"]})
    crypto["event_graph_sha256"] = digest_value(event_graph_payload(data))
    crypto["confinement_sha256"] = digest_value(data["confinement"])
    capture = data["capture_identity"]
    for link in crypto["generation_links"]:
        output = artifacts_by_role.get(link["output_role"])
        generator = artifacts_by_role.get(link["generator_role"])
        inputs = [artifacts_by_role.get(role) for role in link["input_roles"]]
        if output:
            link["output_sha256"] = output["sha256"]
        if generator:
            link["generator_sha256"] = generator["sha256"]
        if all(inputs):
            link["input_sha256"] = [item["sha256"] for item in inputs]
        for field in ("base_sha", "workflow_sha", "run_id", "job_id"):
            link[field] = capture[field]
        link["link_sha256"] = digest_value(generation_payload(link))
    crypto["authority_link_sha256"] = digest_value(authority_payload(data))


def seal_external_trust(data, trust):
    trust["schema_version"] = TRUST_SCHEMA_VERSION
    trust["authority_contract_version"] = AUTHORITY_CONTRACT_VERSION
    trust["installed_path_census"] = installed_path_census_payload(trust.get("installed_path_census", []))
    trust["installed_path_census_sha256"] = digest_value(trust["installed_path_census"])
    data["installed_path_census_sha256"] = trust["installed_path_census_sha256"]
    events = {item["type"]: item for item in data.get("events", [])}
    for policy in trust.get("command_policies", []):
        event_item = events.get(policy["event_type"])
        if event_item:
            policy["argv_sha256"] = event_item["command"]["argv_sha256"]
    trust["trusted_collector"]["installation_mount_identity_sha256"] = digest_value(installed_mount_payload(data))
    trust["collector_attestation_sha256"] = digest_value(collector_attestation_payload(data, trust))


def hydrate_fixture(data, root, trust):
    by_role = {item["role"]: item for item in data["artifacts"]}
    for artifact in data["artifacts"]:
        file_path = safe_bundle_path(root, artifact["bundle_path"])
        bundle_metadata = physical_metadata(file_path, artifact["bundle_metadata"]["mount_id"])
        installed_mount = artifact["installed_metadata"]["mount_id"]
        installed_metadata = copy.deepcopy(bundle_metadata)
        installed_metadata["mount_id"] = installed_mount
        artifact["size"] = file_path.stat().st_size
        artifact["sha256"] = digest_file(file_path)
        artifact["bundle_metadata"] = bundle_metadata
        artifact["installed_metadata"] = installed_metadata
        artifact["installation"]["expected_metadata"] = copy.deepcopy(installed_metadata)
    recipe = by_role["installation_recipe"]
    for artifact in data["artifacts"]:
        artifact["installation"]["recipe_sha256"] = recipe["sha256"]
    mount = data["confinement"]["mounts"][0]
    bundle_metadata = data["artifacts"][0]["bundle_metadata"]
    mount["device_id"] = bundle_metadata["device_id"]
    mount["filesystem"] = bundle_metadata["filesystem"]
    weights = data["confinement"]["weights_root"]
    weights["device_id"] = mount["device_id"]
    weights["filesystem"] = mount["filesystem"]
    profile = by_role[data["confinement"]["sandbox_profile_role"]]
    data["confinement"]["sandbox_profile_sha256"] = profile["sha256"]
    seal_bundle_commands(data)
    refresh_derived(data, by_role)
    seal_external_trust(data, trust)


def remove_fixture_artifact(data, root, role, declare_missing):
    artifact = next(item for item in data["artifacts"] if item["role"] == role)
    safe_bundle_path(root, artifact["bundle_path"]).unlink()
    data["artifacts"] = [item for item in data["artifacts"] if item["role"] != role]
    if declare_missing:
        data["missing_authority"] = {
            "kind": "artifact_role",
            "role": role,
            "fact": "exact profile generator input bytes and installed metadata",
            "reason": "synthetic fixture intentionally omits the first unavailable authority fact",
        }


def mutate_fixture(name, data, root, trust):
    if name == "none":
        return trust
    if name == "missing_external_trust":
        return None
    if name == "ranked_trust_positive":
        ranked_identity = {
            "repository": "morganmcg1/mlxfast-challenge_senpai",
            "base_sha": RANKED_SCOPE["audited_base_sha"],
            "workflow_path": RANKED_SCOPE["workflow_path"],
            "workflow_blob_sha": RANKED_SCOPE["workflow_blob_sha"],
            "workflow_file_sha256": RANKED_SCOPE["workflow_file_sha256"],
        }
        for identity in (data["target_identity"], data["capture_identity"]):
            identity.update(ranked_identity)
        trust["source_kind"] = "ranked"
        trust["accepted_target_identity"] = copy.deepcopy(data["target_identity"])
        for role, ranked_path in KNOWN_RANKED_PATHS.items():
            artifact = next(item for item in data["artifacts"] if item["role"] == role)
            old_path = artifact["installed_path"]
            artifact["installed_path"] = ranked_path
            for event_item in data["events"]:
                command = event_item["command"]
                command["argv"] = [ranked_path if value == old_path else value for value in command["argv"]]
            census_item = next(item for item in trust["installed_path_census"] if item["role"] == role)
            census_item["installed_path"] = ranked_path
        seal_bundle_commands(data)
        refresh_derived(data)
        trust["expected_authority"] = copy.deepcopy(data["authority"])
        seal_external_trust(data, trust)
        return trust
    if name == "self_resealed_substituted_trust":
        data["authority"]["trusted_collector"] = "synthetic-substituted-collector"
        data["authority"]["collector_authority"] = "synthetic-substituted-authority"
        trust["trusted_collector"]["id"] = data["authority"]["trusted_collector"]
        trust["trusted_collector"]["authority"] = data["authority"]["collector_authority"]
        trust["expected_authority"] = copy.deepcopy(data["authority"])
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name == "source_kind_drift":
        trust["source_kind"] = "ranked"
        seal_external_trust(data, trust)
        return trust
    if name == "coherent_parent_ppid_drift":
        worker = next(item for item in data["actors"] if item["id"] == "worker")
        worker["ppid"] += 1
        for event_item in data["events"]:
            process = event_item["command"]["process_start"]
            if process["actor_id"] == "worker":
                process["ppid"] = worker["ppid"]
        refresh_derived(data)
        return trust
    if name == "authority_claim_flip":
        data["authority"]["authoritative"] = not data["authority"]["authoritative"]
        refresh_derived(data)
        return trust
    if name == "coherent_foreign_target":
        for identity in (data["target_identity"], data["capture_identity"]):
            identity["repository"] = "synthetic/foreign-target"
            identity["base_sha"] = "f" * 40
        refresh_derived(data)
        return trust
    if name == "wrong_measure_path":
        artifact = next(item for item in data["artifacts"] if item["role"] == "measure_job")
        old = artifact["installed_path"]
        artifact["installed_path"] = "/synthetic/installed/bench-runner/wrong-measure-job.sh"
        for event_item in data["events"]:
            command = event_item["command"]
            command["argv"] = [artifact["installed_path"] if value == old else value for value in command["argv"]]
        seal_bundle_commands(data)
        refresh_derived(data)
        return trust
    if name == "arbitrary_worker_argv0":
        event_item = next(item for item in data["events"] if item["type"] == "worker_spawn")
        event_item["command"]["argv"][0] = "/synthetic/arbitrary/argv0"
        refresh_derived(data)
        return trust
    if name == "launch_chain_substitution":
        event_item = next(item for item in data["events"] if item["type"] == "worker_spawn")
        event_item["command"]["exec_chain"] = [item for item in event_item["command"]["exec_chain"] if item["artifact_role"] != "bench_exec"]
        seal_bundle_commands(data)
        refresh_derived(data)
        return trust
    if name == "process_identity_drift":
        event_item = next(item for item in data["events"] if item["type"] == "worker_spawn")
        event_item["command"]["process_start"]["pid"] += 1
        refresh_derived(data)
        return trust
    if name == "installed_metadata_reseal":
        artifact = next(item for item in data["artifacts"] if item["role"] == "bench_exec")
        artifact["installed_metadata"]["mount_id"] += "-resealed"
        artifact["installation"]["expected_metadata"] = copy.deepcopy(artifact["installed_metadata"])
        refresh_derived(data)
        return trust

    for artifact in data.get("artifacts", []):
        artifact["metadata"] = artifact["bundle_metadata"]
    try:
        _mutate_fixture_v2(name, data, root)
    finally:
        for artifact in data.get("artifacts", []):
            if "metadata" in artifact:
                artifact["bundle_metadata"] = artifact.pop("metadata")
    if name == "missing_install_provenance":
        refresh_derived(data)
    if name == "missing_profile_generator_input":
        trust["installed_path_census"] = [item for item in trust["installed_path_census"] if item["role"] != "profile_generator_input"]
        trust["census_complete"] = False
        trust["first_missing_fact"] = copy.deepcopy(data["missing_authority"])
        refresh_derived(data)
        seal_external_trust(data, trust)
    return trust


def run_fixture_suite(fixture_path):
    fixture_document = json.loads(fixture_path.read_text())
    if fixture_document.get("schema_version") != FIXTURE_VERSION or fixture_document.get("non_authoritative") is not True:
        raise ValueError("fixture document must be explicitly synthetic and non-authoritative")
    results = []
    failures = []
    for case in fixture_document["cases"]:
        with tempfile.TemporaryDirectory(prefix="ranked-authority-fixture-") as temporary:
            root = Path(temporary)
            for relative, specification in fixture_document["files"].items():
                destination = safe_bundle_path(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(specification["text"].encode())
                destination.chmod(int(specification["mode"], 8))
            data = copy.deepcopy(fixture_document["base_bundle"])
            trust = copy.deepcopy(fixture_document["base_external_trust"])
            hydrate_fixture(data, root, trust)
            pre_mutation_pin = digest_value(trust)
            trust = mutate_fixture(case["mutation"], data, root, trust)
            pin_mode = case.get("external_trust_pin", "current")
            if pin_mode == "missing":
                trust_pin = None
            elif pin_mode == "invalid":
                trust_pin = "A" * 64
            elif pin_mode == "mismatch":
                trust_pin = ZERO_SHA256
            elif pin_mode == "pre_mutation":
                trust_pin = pre_mutation_pin
            elif pin_mode == "current":
                trust_pin = digest_value(trust) if isinstance(trust, dict) else pre_mutation_pin
            else:
                raise ValueError(f"unknown external trust pin mode: {pin_mode}")
            result = validate_bundle(data, root, trust, trust_pin)
        actual_codes = sorted({item["code"] for item in result["errors"]})
        expected_codes = sorted(case["expected_error_codes"])
        passed = (
            result["state"] == case["expected_state"]
            and actual_codes == expected_codes
            and result["authoritative"] is case["expected_authoritative"]
            and result["resumption_authorized"] is case["expected_resumption_authorized"]
        )
        case_result = {
            "id": case["id"], "state": result["state"], "bundle_digest_sha256": result["bundle_digest_sha256"],
            "error_codes": actual_codes, "authoritative": result["authoritative"],
            "resumption_authorized": result["resumption_authorized"], "passed": passed,
        }
        if result["state"] == "INCOMPLETE":
            case_result["missing_authority"] = result["missing_authority"]
        results.append(case_result)
        if not passed:
            failures.append({
                "id": case["id"], "expected_state": case["expected_state"], "actual_state": result["state"],
                "expected_error_codes": expected_codes, "actual_error_codes": actual_codes,
                "expected_authoritative": case["expected_authoritative"],
                "actual_authoritative": result["authoritative"],
                "expected_resumption_authorized": case["expected_resumption_authorized"],
                "actual_resumption_authorized": result["resumption_authorized"],
            })
    return {
        "schema_version": "ranked-authority-evidence-fixture-results/v4",
        "fixture_source_sha256": digest_file(fixture_path), "non_authoritative": True,
        "case_count": len(results), "passed": not failures, "results": results, "failures": failures,
    }


_scan_for_secret_fields_v4 = scan_for_secret_fields
_event_graph_payload_v4 = event_graph_payload
_collector_attestation_payload_v4 = collector_attestation_payload
_validate_artifacts_v4 = validate_artifacts
_validate_bundle_v4 = validate_bundle
_mutate_fixture_v4 = mutate_fixture
_seal_external_trust_v4 = seal_external_trust

CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
)
PROCESS_EXECUTABLE_ROLES = {
    "controller": "measure_job",
    "bench": "bench_exec",
    "worker": "runtime_worker",
}


def secret_value_present(value):
    return isinstance(value, str) and any(pattern.search(value) for pattern in CREDENTIAL_VALUE_PATTERNS)


def scan_for_secret_fields(value, errors, path="$", environment_observation=False):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_PATTERN.search(key):
                errors.append(error("SECRET_FIELD_FORBIDDEN", child_path, "secret-bearing field names are forbidden"))
            if key == "value" and environment_observation and isinstance(child, str) and value.get("redacted") is not True:
                policy_secret = value.get("name", "").upper().endswith(("SECRET", "TOKEN", "PASSWORD", "KEY"))
                if policy_secret:
                    errors.append(error("SECRET_VALUE_FORBIDDEN", child_path, "secret-like environment values are forbidden"))
            if secret_value_present(child):
                errors.append(error("SECRET_VALUE_FORBIDDEN", child_path, "credential-like string values are forbidden"))
            scan_for_secret_fields(child, errors, child_path, path.endswith(".observed") or environment_observation)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_for_secret_fields(child, errors, f"{path}[{index}]", path.endswith(".observed") or environment_observation)


def event_graph_payload(data):
    payload = _event_graph_payload_v4(data)
    payload["process_births"] = sorted(data.get("process_births", []), key=lambda item: (item.get("pid", -1), item.get("actor_id", "")))
    return payload


def collector_attestation_payload(data, trust):
    payload = _collector_attestation_payload_v4(data, trust)
    payload["expected_bundle_sha256"] = trust.get("expected_bundle_sha256")
    return payload


def validate_artifacts(errors, data, root, missing_role, census_by_role):
    by_role = _validate_artifacts_v4(errors, data, root, missing_role, census_by_role)
    for index, artifact in enumerate(data.get("artifacts", [])):
        try:
            file_path = safe_bundle_path(root, artifact.get("bundle_path"))
            if file_path.is_file() and secret_value_present(file_path.read_bytes().decode("latin-1")):
                errors.append(error("SECRET_VALUE_FORBIDDEN", f"artifacts[{index}].bundle_path.bytes", "credential-like artifact bytes are forbidden"))
        except (OSError, TypeError, ValueError):
            continue
    return by_role


def validate_events(errors, data, artifacts, actors, started, finished, missing_role, policies, census):
    by_id, by_type = _validate_events_v2(errors, data, artifacts, actors, started, finished, missing_role)
    births = data.get("process_births", [])
    births_by_actor = {}
    birth_pid_indices = {}
    for index, birth in enumerate(births if isinstance(births, list) else []):
        if not isinstance(birth, dict):
            continue
        path = f"process_births[{index}]"
        actor_id = birth.get("actor_id")
        pid = birth.get("pid")
        if actor_id in births_by_actor:
            errors.append(error("PROCESS_BIRTH_ACTOR_DUPLICATE", path, "each actor must have exactly one immutable process birth"))
        else:
            births_by_actor[actor_id] = birth
        if pid in birth_pid_indices:
            errors.append(error("PROCESS_BIRTH_PID_DUPLICATE", path, "each PID must have exactly one immutable process birth"))
        else:
            birth_pid_indices[pid] = index
        actor = actors.get(actor_id)
        role = PROCESS_EXECUTABLE_ROLES.get(actor_id)
        artifact = artifacts.get(role)
        expected = (
            actor_id,
            actor.get("pid") if actor else None,
            actor.get("ppid") if actor else None,
            actor.get("parent_actor_id") if actor else None,
            role,
            census.get(role, {}).get("installed_path"),
            artifact.get("sha256") if artifact else None,
        )
        actual = (
            birth.get("actor_id"), birth.get("pid"), birth.get("ppid"), birth.get("parent_actor_id"),
            birth.get("executable_role"), birth.get("executable_path"), birth.get("executable_sha256"),
        )
        if actual != expected:
            errors.append(error("PROCESS_BIRTH_IDENTITY_MISMATCH", path, "process birth differs from actor, executable, or verifier-owned census"))
        parent_actor_id = birth.get("parent_actor_id")
        parent_actor = actors.get(parent_actor_id)
        if parent_actor_id is not None and parent_actor is not None and birth.get("ppid") != parent_actor.get("pid"):
            errors.append(error("PROCESS_PARENT_ACTOR_PID_MISMATCH", f"{path}.ppid", "process parent PID differs from the declared parent actor PID"))
        birth_started = parse_timestamp(birth.get("started_at"))
        observed = parse_timestamp(birth.get("observed_at"))
        if birth_started is not None and observed is not None and birth_started > observed:
            errors.append(error("PROCESS_BIRTH_TIME_INVALID", path, "process birth start must not follow its observation"))

    if set(births_by_actor) != set(actors):
        errors.append(error("PROCESS_BIRTH_CENSUS_MISMATCH", "process_births", "process births must cover every actor exactly once"))
    for actor_id, birth in births_by_actor.items():
        parent = births_by_actor.get(birth.get("parent_actor_id"))
        child_started = parse_timestamp(birth.get("started_at"))
        parent_started = parse_timestamp(parent.get("started_at")) if parent else None
        if child_started is not None and parent_started is not None and child_started < parent_started:
            errors.append(error("PROCESS_BIRTH_LIFECYCLE_ORDER_INVALID", f"process_births[{actor_id}]", "child process birth precedes its parent birth"))
        observed = parse_timestamp(birth.get("observed_at"))
        first_event = min(
            (
                parse_timestamp(event_item.get("timestamp"))
                for event_item in data.get("events", [])
                if policies.get(event_item.get("type"), {}).get("process_actor_id") == actor_id
                and parse_timestamp(event_item.get("timestamp")) is not None
            ),
            default=None,
        )
        if observed is not None and first_event is not None and observed > first_event:
            errors.append(error("PROCESS_BIRTH_LIFECYCLE_ORDER_INVALID", f"process_births[{actor_id}].observed_at", "process birth observation follows the first event using that process"))

    for index, event_item in enumerate(data.get("events", [])):
        command = event_item.get("command", {})
        role = command.get("artifact_role")
        artifact = artifacts.get(role)
        trusted_path = census.get(role, {}).get("installed_path")
        policy = policies.get(event_item.get("type"))
        path = f"events[{index}].command"
        if policy is None:
            continue
        if policy.get("event_actor_id") != event_item.get("actor_id") or policy.get("primary_role") != role:
            errors.append(error("COMMAND_POLICY_BINDING_MISMATCH", path, "event actor or primary role differs from external trust"))
        if artifact is None and role == missing_role:
            continue
        if artifact is None:
            continue
        if command.get("artifact_sha256") != artifact.get("sha256"):
            errors.append(error("EVENT_COMMAND_HASH_MISMATCH", f"{path}.artifact_sha256", "primary executable hash differs from captured artifact"))
        if command.get("executable_path") != artifact.get("installed_path") or command.get("executable_path") != trusted_path:
            errors.append(error("COMMAND_EXECUTABLE_PATH_MISMATCH", f"{path}.executable_path", "primary executable path differs from verifier-owned census"))
        argv = command.get("argv", [])
        if not argv or argv[0] != command.get("executable_path"):
            errors.append(error("COMMAND_ARGV0_MISMATCH", f"{path}.argv[0]", "argv[0] must equal the bound executable path"))
        argv_digest = digest_value(argv)
        if command.get("argv_sha256") != argv_digest or policy.get("argv_sha256") != argv_digest:
            errors.append(error("COMMAND_ARGV_DIGEST_MISMATCH", f"{path}.argv_sha256", "argv differs from the externally trusted command"))
        chain = command.get("exec_chain", [])
        chain_roles = [item.get("artifact_role") for item in chain if isinstance(item, dict)]
        if chain_roles != policy.get("exec_chain_roles"):
            errors.append(error("COMMAND_CHAIN_POLICY_MISMATCH", f"{path}.exec_chain", "launcher/worker chain differs from external trust"))
        for chain_index, item in enumerate(chain):
            chain_role = item.get("artifact_role") if isinstance(item, dict) else None
            chain_artifact = artifacts.get(chain_role)
            trusted_chain_path = census.get(chain_role, {}).get("installed_path")
            if chain_artifact is None:
                errors.append(error("COMMAND_CHAIN_ARTIFACT_MISSING", f"{path}.exec_chain[{chain_index}]", "chain artifact is absent"))
                continue
            if (
                item.get("installed_path") != chain_artifact.get("installed_path")
                or item.get("installed_path") != trusted_chain_path
                or item.get("artifact_sha256") != chain_artifact.get("sha256")
            ):
                errors.append(error("COMMAND_CHAIN_IDENTITY_MISMATCH", f"{path}.exec_chain[{chain_index}]", "chain identity differs from captured artifacts or verifier-owned census"))
        process_actor_id = policy.get("process_actor_id")
        birth = births_by_actor.get(process_actor_id)
        if birth is None or command.get("process_birth_pid") != birth.get("pid"):
            errors.append(error("PROCESS_BIRTH_REFERENCE_MISMATCH", f"{path}.process_birth_pid", "event command does not reference the immutable birth of its trusted process actor"))
    return by_id, by_type


def seal_bundle_commands(data):
    artifacts = {item["role"]: item for item in data.get("artifacts", [])}
    actors = {item["id"]: item for item in data.get("actors", [])}
    for birth in data.get("process_births", []):
        actor = actors.get(birth.get("actor_id"))
        if actor:
            birth["pid"] = actor["pid"]
            birth["ppid"] = actor["ppid"]
            birth["parent_actor_id"] = actor["parent_actor_id"]
        artifact = artifacts.get(birth.get("executable_role"))
        if artifact:
            birth["executable_path"] = artifact["installed_path"]
            birth["executable_sha256"] = artifact["sha256"]
    for event_item in data.get("events", []):
        command = event_item["command"]
        primary = artifacts.get(command["artifact_role"])
        if primary:
            command["artifact_sha256"] = primary["sha256"]
            command["executable_path"] = primary["installed_path"]
        command["argv_sha256"] = digest_value(command["argv"])
        for entry in command["exec_chain"]:
            artifact = artifacts.get(entry["artifact_role"])
            if artifact:
                entry["installed_path"] = artifact["installed_path"]
                entry["artifact_sha256"] = artifact["sha256"]


def seal_external_trust(data, trust):
    _seal_external_trust_v4(data, trust)
    trust["expected_bundle_sha256"] = digest_value(data)
    trust["collector_attestation_sha256"] = digest_value(collector_attestation_payload(data, trust))


def validate_bundle(data, root, external_trust=None, expected_external_trust_sha256=None):
    result = _validate_bundle_v4(data, root, external_trust, expected_external_trust_sha256)
    if not result["errors"] and isinstance(external_trust, dict):
        if external_trust.get("expected_bundle_sha256") != result["bundle_digest_sha256"]:
            result["errors"] = [error("TRUST_BUNDLE_DIGEST_MISMATCH", "$external_trust.expected_bundle_sha256", "canonical bundle differs from the externally authenticated digest")]
            result["state"] = "INVALID"
            result["authoritative"] = False
            result["resumption_authorized"] = False
    return result


def shifted_timestamp(value, seconds=10):
    parsed = parse_timestamp(value)
    return (parsed + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def fictional_secret(kind):
    if kind == "github":
        return "gh" + "p_" + "F" * 36
    if kind == "aws":
        return "AK" + "IA" + "F" * 16
    if kind == "bearer":
        return "Bear" + "er " + "fake" * 8
    if kind == "private_key":
        return "-----BEGIN " + "PRIVATE KEY-----"
    raise ValueError(f"unknown fictional secret kind: {kind}")


def mutate_fixture(name, data, root, trust):
    if name == "coherent_whole_bundle_rewrite":
        old_to_new = {actor["pid"]: actor["pid"] + 1000 for actor in data["actors"]}
        for actor in data["actors"]:
            actor["pid"] = old_to_new[actor["pid"]]
            actor["ppid"] = old_to_new.get(actor["ppid"], actor["ppid"])
            actor["pgid"] = old_to_new.get(actor["pgid"], actor["pgid"])
            actor["sid"] = old_to_new.get(actor["sid"], actor["sid"])
        for birth in data["process_births"]:
            birth["pid"] = old_to_new[birth["pid"]]
            birth["ppid"] = old_to_new.get(birth["ppid"], birth["ppid"])
            birth["started_at"] = shifted_timestamp(birth["started_at"])
            birth["observed_at"] = shifted_timestamp(birth["observed_at"])
        for event_item in data["events"]:
            event_item["timestamp"] = shifted_timestamp(event_item["timestamp"])
            event_item["command"]["process_birth_pid"] = old_to_new[event_item["command"]["process_birth_pid"]]
        for phase in data["phases"]:
            phase["started_at"] = shifted_timestamp(phase["started_at"])
            phase["finished_at"] = shifted_timestamp(phase["finished_at"])
        data["capture_window"]["started_at"] = shifted_timestamp(data["capture_window"]["started_at"])
        data["capture_window"]["finished_at"] = shifted_timestamp(data["capture_window"]["finished_at"])
        seal_bundle_commands(data)
        refresh_derived(data)
        return trust
    if name == "duplicate_process_birth":
        data["process_births"].append(copy.deepcopy(data["process_births"][0]))
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name == "process_birth_start_after_observation":
        birth = next(item for item in data["process_births"] if item["actor_id"] == "worker")
        birth["started_at"] = shifted_timestamp(birth["observed_at"])
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name == "process_birth_observed_after_first_event":
        birth = next(item for item in data["process_births"] if item["actor_id"] == "worker")
        first = next(item for item in data["events"] if item["type"] == "worker_spawn")
        birth["observed_at"] = shifted_timestamp(first["timestamp"])
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name == "process_identity_drift":
        event_item = next(item for item in data["events"] if item["type"] == "worker_spawn")
        event_item["command"]["process_birth_pid"] += 1
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name == "coherent_parent_ppid_drift":
        worker = next(item for item in data["actors"] if item["id"] == "worker")
        worker["ppid"] += 1
        birth = next(item for item in data["process_births"] if item["actor_id"] == "worker")
        birth["ppid"] = worker["ppid"]
        refresh_derived(data)
        seal_external_trust(data, trust)
        return trust
    if name.startswith("secret_") and name != "secret_leak":
        remainder = name.removeprefix("secret_")
        target = next(
            value
            for value in ("external_trust", "artifact_bytes", "manifest")
            if remainder.endswith("_" + value)
        )
        kind = remainder[: -(len(target) + 1)]
        secret = fictional_secret(kind)
        if target == "manifest":
            data["environment"]["observed"][0]["value"] = secret
            refresh_derived(data)
            seal_external_trust(data, trust)
        elif target == "external_trust":
            data["authority"]["collector_authority"] = secret
            trust["expected_authority"] = copy.deepcopy(data["authority"])
            trust["trusted_collector"]["authority"] = secret
            refresh_derived(data)
            seal_external_trust(data, trust)
        else:
            artifact = next(item for item in data["artifacts"] if item["role"] == "profile_generator_input")
            file_path = safe_bundle_path(root, artifact["bundle_path"])
            file_path.write_bytes(file_path.read_bytes() + b"\n" + secret.encode())
            hydrate_fixture(data, root, trust)
        return trust
    return _mutate_fixture_v4(name, data, root, trust)


def invalid_json_result(code, path, raw):
    return {
        "state": "INVALID",
        "bundle_digest_sha256": hashlib.sha256(raw).hexdigest(),
        "errors": [error(code, path, "input is not valid JSON")],
        "missing_authority": None,
        "authoritative": False,
        "resumption_authorized": False,
    }


def validate_serialized_bundle(manifest_bytes, root, trust_bytes, trust_pin):
    try:
        data = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return invalid_json_result("MANIFEST_JSON_INVALID", "$manifest", manifest_bytes)
    try:
        trust = json.loads(trust_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return invalid_json_result("EXTERNAL_TRUST_JSON_INVALID", "$external_trust", trust_bytes)
    return validate_bundle(data, root, trust, trust_pin)


def run_fixture_suite(fixture_path):
    fixture_document = json.loads(fixture_path.read_text())
    if fixture_document.get("schema_version") != FIXTURE_VERSION or fixture_document.get("non_authoritative") is not True:
        raise ValueError("fixture document must be explicitly synthetic and non-authoritative")
    results = []
    failures = []
    for case in fixture_document["cases"]:
        with tempfile.TemporaryDirectory(prefix="ranked-authority-fixture-") as temporary:
            root = Path(temporary)
            for relative, specification in fixture_document["files"].items():
                destination = safe_bundle_path(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(specification["text"].encode())
                destination.chmod(int(specification["mode"], 8))
            data = copy.deepcopy(fixture_document["base_bundle"])
            trust = copy.deepcopy(fixture_document["base_external_trust"])
            hydrate_fixture(data, root, trust)
            pre_mutation_pin = digest_value(trust)
            trust = mutate_fixture(case["mutation"], data, root, trust)
            pin_mode = case.get("external_trust_pin", "current")
            if pin_mode == "missing":
                trust_pin = None
            elif pin_mode == "invalid":
                trust_pin = "A" * 64
            elif pin_mode == "mismatch":
                trust_pin = ZERO_SHA256
            elif pin_mode == "pre_mutation":
                trust_pin = pre_mutation_pin
            elif pin_mode == "current":
                trust_pin = digest_value(trust) if isinstance(trust, dict) else pre_mutation_pin
            else:
                raise ValueError(f"unknown external trust pin mode: {pin_mode}")
            manifest_bytes = canonical_bytes(data)
            trust_bytes = canonical_bytes(trust)
            malformed = case.get("malformed_input")
            if malformed == "manifest":
                manifest_bytes = b"{"
            elif malformed == "external_trust":
                trust_bytes = b"{"
            first = validate_serialized_bundle(manifest_bytes, root, trust_bytes, trust_pin)
            second = validate_serialized_bundle(manifest_bytes, root, trust_bytes, trust_pin)
        deterministic = first == second
        result = first
        actual_codes = sorted({item["code"] for item in result["errors"]})
        expected_codes = sorted(case["expected_error_codes"])
        passed = (
            deterministic
            and result["state"] == case["expected_state"]
            and actual_codes == expected_codes
            and result["authoritative"] is case["expected_authoritative"]
            and result["resumption_authorized"] is case["expected_resumption_authorized"]
        )
        case_result = {
            "id": case["id"], "state": result["state"], "bundle_digest_sha256": result["bundle_digest_sha256"],
            "error_codes": actual_codes, "authoritative": result["authoritative"],
            "resumption_authorized": result["resumption_authorized"], "deterministic": deterministic, "passed": passed,
        }
        if result["state"] == "INCOMPLETE":
            case_result["missing_authority"] = result["missing_authority"]
        results.append(case_result)
        if not passed:
            failures.append({
                "id": case["id"], "expected_state": case["expected_state"], "actual_state": result["state"],
                "expected_error_codes": expected_codes, "actual_error_codes": actual_codes,
                "expected_authoritative": case["expected_authoritative"], "actual_authoritative": result["authoritative"],
                "expected_resumption_authorized": case["expected_resumption_authorized"],
                "actual_resumption_authorized": result["resumption_authorized"], "deterministic": deterministic,
            })
    return {
        "schema_version": "ranked-authority-evidence-fixture-results/v5",
        "fixture_source_sha256": digest_file(fixture_path), "non_authoritative": True,
        "case_count": len(results), "passed": not failures, "results": results, "failures": failures,
    }



def main():
    parser = argparse.ArgumentParser(description="Validate a ranked installed-authority evidence bundle")
    parser.add_argument("--bundle-root", type=Path, help="directory containing physical evidence files")
    parser.add_argument("--manifest", type=Path, help="bundle manifest JSON (defaults to BUNDLE_ROOT/bundle.json)")
    parser.add_argument("--external-trust", type=Path, help="verifier-owned external trust JSON")
    parser.add_argument(
        "--external-trust-sha256",
        help="verifier-owned lowercase SHA256 of the complete canonical external trust JSON",
    )
    parser.add_argument("--run-fixtures", type=Path, help="run the committed synthetic fixture suite")
    args = parser.parse_args()

    if args.run_fixtures:
        if args.bundle_root or args.manifest or args.external_trust or args.external_trust_sha256:
            parser.error("--run-fixtures cannot be combined with bundle arguments")
        output = run_fixture_suite(args.run_fixtures.resolve())
        sys.stdout.buffer.write(canonical_bytes(output))
        return 0 if output["passed"] else 1
    if args.bundle_root is None:
        parser.error("--bundle-root is required unless --run-fixtures is used")
    root = args.bundle_root.resolve()
    manifest = (args.manifest or root / "bundle.json").resolve()
    manifest_bytes = manifest.read_bytes()
    trust_bytes = b"null"
    if args.external_trust is not None:
        trust_bytes = args.external_trust.resolve().read_bytes()
    output = validate_serialized_bundle(
        manifest_bytes,
        root,
        trust_bytes,
        args.external_trust_sha256,
    )
    sys.stdout.buffer.write(canonical_bytes(output))
    return 0 if output["resumption_authorized"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
