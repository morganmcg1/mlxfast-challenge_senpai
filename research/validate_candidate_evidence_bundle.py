#!/usr/bin/env python3

import argparse
import copy
import errno
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path, PurePosixPath

SCHEMA_ID = "https://mlxfast.invalid/schemas/candidate-evidence-bundle-v3.json"
STRICT_RANKED_MARGIN = Decimal("1.0037802719941367788")
COMPONENT_FLOOR = Decimal("0.95")
DECIMAL_TOLERANCE = Decimal("1e-24")
GATE_NAMES = (
    "PUBLIC_GREEDY_64",
    "SERIAL_PROTOCOL",
    "TIMED_TOKEN_VALIDATION",
    "HIDDEN_TEACHER_FORCED_512",
    "HIDDEN_ANCHORS",
    "HIDDEN_FREE_RUNS",
    "GPQA_BEHAVIOR",
    "TTFT",
    "SEMANTIC_GPQA",
)
ORDER_ARMS = {
    "ABBA": ("BASE", "CANDIDATE", "CANDIDATE", "BASE"),
    "BAAB": ("CANDIDATE", "BASE", "BASE", "CANDIDATE"),
}
ROLE_CONTRACT = {
    "ISOLATED_RAW_ROWS": ("ISOLATED", "seconds_per_invocation"),
    "WHOLE_MODEL_RAW_ROWS": ("WHOLE_MODEL", "seconds_per_token"),
    "RANKED_M5_RECEIPT": ("RANKED_M5", "dimensionless_speedup"),
}
ARTIFACT_DEFINITIONS = {
    "ISOLATED_RAW_ROWS": "#/$defs/isolatedArtifactDocument",
    "WHOLE_MODEL_RAW_ROWS": "#/$defs/wholeModelArtifactDocument",
    "RANKED_M5_RECEIPT": "#/$defs/rankedReceiptArtifactDocument",
}
ARTIFACT_PHASE_KEYS = {
    "ISOLATED_RAW_ROWS": "isolated",
    "WHOLE_MODEL_RAW_ROWS": "whole_model",
    "RANKED_M5_RECEIPT": "ranked_m5",
}
TERMINAL_CONTRACT = {
    "ISOLATED_COMPLETE": ("ISOLATED_COMPLETE", "ISOLATED_EVIDENCE_COMPLETE"),
    "WHOLE_MODEL_COMPLETE": ("WHOLE_MODEL_COMPLETE", "WHOLE_MODEL_EVIDENCE_COMPLETE"),
    "CENSORED_VALID": ("CENSORED", "PREDECLARED_EARLY_STOP"),
    "RANKED_MARGIN_COMPLETE": ("RANKED_MARGIN_COMPLETE", "RANKED_MARGIN_EVIDENCE_COMPLETE"),
}


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def issue(code, path, message):
    return {"code": code, "path": path, "message": message}


def stable_issues(errors):
    unique = {(item["code"], item["path"], item["message"]): item for item in errors}
    return [unique[key] for key in sorted(unique)]


class SchemaChecker:
    def __init__(self, schema):
        self.schema = schema

    def check(self, instance):
        errors = []
        self._check(instance, self.schema, "$", errors)
        return stable_issues(errors)

    def check_reference(self, instance, reference, path):
        errors = []
        self._check(instance, self._resolve(reference), path, errors)
        return stable_issues(errors)

    def _resolve(self, reference):
        if not reference.startswith("#/"):
            raise ValueError("only local schema references are supported")
        node = self.schema
        for part in reference[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node

    def _branch_valid(self, instance, schema, path):
        branch_errors = []
        self._check(instance, schema, path, branch_errors)
        return not branch_errors

    def _check(self, instance, schema, path, errors):
        if "$ref" in schema:
            self._check(instance, self._resolve(schema["$ref"]), path, errors)
            return
        if "oneOf" in schema:
            matches = sum(self._branch_valid(instance, branch, path) for branch in schema["oneOf"])
            if matches != 1:
                errors.append(issue("SCHEMA_VIOLATION", path, "value must match exactly one schema branch"))
            return
        if "const" in schema and instance != schema["const"]:
            errors.append(issue("SCHEMA_VIOLATION", path, f"value must equal {schema['const']!r}"))
            return
        if "enum" in schema and instance not in schema["enum"]:
            errors.append(issue("SCHEMA_VIOLATION", path, "value is outside the allowed enumeration"))
            return
        expected_type = schema.get("type")
        type_ok = {
            "object": isinstance(instance, dict),
            "array": isinstance(instance, list),
            "string": isinstance(instance, str),
            "integer": isinstance(instance, int) and not isinstance(instance, bool),
            "boolean": isinstance(instance, bool),
            "null": instance is None,
        }.get(expected_type, True)
        if not type_ok:
            errors.append(issue("SCHEMA_VIOLATION", path, f"value must have type {expected_type}"))
            return
        if isinstance(instance, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in instance:
                    errors.append(issue("SCHEMA_VIOLATION", f"{path}.{key}", "required property is missing"))
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                for key in instance:
                    if key not in properties:
                        errors.append(issue("SCHEMA_VIOLATION", f"{path}.{key}", "additional property is forbidden"))
            additional = schema.get("additionalProperties")
            for key, value in instance.items():
                child_schema = properties.get(key)
                if child_schema is None and isinstance(additional, dict):
                    child_schema = additional
                if child_schema is not None:
                    self._check(value, child_schema, f"{path}.{key}", errors)
            if len(instance) < schema.get("minProperties", 0):
                errors.append(issue("SCHEMA_VIOLATION", path, "object has too few properties"))
            if "propertyNames" in schema:
                for key in instance:
                    self._check(key, schema["propertyNames"], f"{path}.<property-name>", errors)
        elif isinstance(instance, list):
            if len(instance) < schema.get("minItems", 0):
                errors.append(issue("SCHEMA_VIOLATION", path, "array has too few items"))
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                errors.append(issue("SCHEMA_VIOLATION", path, "array has too many items"))
            if "items" in schema:
                for index, value in enumerate(instance):
                    self._check(value, schema["items"], f"{path}[{index}]", errors)
        elif isinstance(instance, str):
            if len(instance) < schema.get("minLength", 0):
                errors.append(issue("SCHEMA_VIOLATION", path, "string is too short"))
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                errors.append(issue("SCHEMA_VIOLATION", path, "string is too long"))
            if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
                errors.append(issue("SCHEMA_VIOLATION", path, "string does not match the required pattern"))
        elif isinstance(instance, int) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(issue("SCHEMA_VIOLATION", path, "integer is below its minimum"))
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(issue("SCHEMA_VIOLATION", path, "integer is above its maximum"))


def parse_decimal(value, path, errors):
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        errors.append(issue("DECIMAL_INVALID", path, "value is not a finite decimal string"))
        return None
    if not result.is_finite():
        errors.append(issue("DECIMAL_INVALID", path, "value is not finite"))
        return None
    return result


def decimal_close(actual, expected):
    scale = max(abs(actual), abs(expected), Decimal(1))
    return abs(actual - expected) <= DECIMAL_TOLERANCE * scale


def check_declared_decimal(declared, expected, path, errors):
    actual = parse_decimal(declared, path, errors)
    if actual is not None and not decimal_close(actual, expected):
        errors.append(issue("ARITHMETIC_MISMATCH", path, f"declared {actual} does not match recomputed {expected}"))


def mean(values):
    return sum(values, Decimal(0)) / Decimal(len(values))


def weighted_factor(prefill_factor, decode_factor):
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        return (prefill_factor.ln() * Decimal("0.25") + decode_factor.ln() * Decimal("0.75")).exp()


def relative_half_range(values):
    center = mean(values)
    if center == 0:
        return Decimal(0)
    return (max(values) - min(values)) / (Decimal(2) * center)


def maximum_arm_uncertainty(rows, field):
    uncertainties = []
    for arm in ("BASE", "CANDIDATE"):
        values = [Decimal(row[field]) for row in rows if row["arm"] == arm]
        uncertainties.append(relative_half_range(values))
    return max(uncertainties)


def expected_join(bundle):
    identity = bundle["identity"]
    return {
        "assignment_id": bundle["assignment_id"],
        "revision_id": bundle["revision_id"],
        "mechanism_id": bundle["mechanism_id"],
        "family_id": bundle["family_id"],
        "base_sha": identity["base_sha"],
        "candidate_sha": identity["candidate_sha"],
        "submitted_surface_sha256": identity["submitted_surface"]["canonical_sha256"],
        "benchmark_id": identity["benchmark_id"],
        "benchmark_contract_sha256": identity["benchmark_contract_sha256"],
        "configuration_sha256": identity["configuration_sha256"],
        "fixture_id": identity["fixture_id"],
        "window_id": identity["window"]["id"],
        "isolated_component_id": identity["components"]["isolated"],
        "prefill_component_id": identity["components"]["prefill"],
        "decode_component_id": identity["components"]["decode"],
    }


def check_join(actual, expected, path, errors, code="IDENTITY_MISMATCH"):
    for key in sorted(expected):
        if actual.get(key) != expected[key]:
            errors.append(issue(code, f"{path}.{key}", "identity does not join to the candidate revision"))


def check_surface(identity, errors):
    surface = identity["submitted_surface"]
    files = surface["files"]
    paths = [entry["path"] for entry in files]
    if len(paths) != len(set(paths)):
        errors.append(issue("SURFACE_DUPLICATE_PATH", "$.identity.submitted_surface.files", "submitted paths must be unique"))
    for index, path in enumerate(paths):
        if PurePosixPath(path).is_absolute() or "\\" in path or path != posixpath.normpath(path) or ".." in PurePosixPath(path).parts:
            errors.append(issue("SURFACE_PATH_INVALID", f"$.identity.submitted_surface.files[{index}].path", "surface path must be normalized and relative"))
    canonical = canonical_bytes(sorted(files, key=lambda entry: entry["path"]))
    actual = sha256_bytes(canonical)
    if surface["canonical_sha256"] != actual:
        errors.append(issue("SURFACE_DIGEST_MISMATCH", "$.identity.submitted_surface.canonical_sha256", "canonical submitted-surface digest does not match file entries"))


def path_is_safe(relative_path):
    pure = PurePosixPath(relative_path)
    return (
        relative_path != ""
        and not pure.is_absolute()
        and "\\" not in relative_path
        and relative_path == posixpath.normpath(relative_path)
        and ".." not in pure.parts
        and "." not in pure.parts
    )


class NonRegularFileError(OSError):
    pass


def read_relative_regular_file(root, relative):
    common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = common_flags | nofollow | getattr(os, "O_DIRECTORY", 0)
    file_flags = common_flags | nofollow
    descriptors = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise NonRegularFileError(errno.EINVAL, "file must be regular", relative)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_regular_file(root, relative, path, prefix, errors, byte_reader=read_relative_regular_file):
    if not path_is_safe(relative):
        errors.append(issue(f"{prefix}_PATH_ESCAPE", path, "path must be normalized, relative, and contained"))
        return None
    root = Path(root)
    target = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except PermissionError:
            errors.append(issue(f"{prefix}_UNREADABLE", path, "file could not be inspected due to permissions"))
            return None
        except OSError:
            errors.append(issue(f"{prefix}_INSPECTION_FAILED", path, "file could not be inspected"))
            return None
        if stat.S_ISLNK(mode):
            try:
                resolved_root = root.resolve(strict=True)
                resolved_target = target.resolve(strict=False)
            except PermissionError:
                errors.append(issue(f"{prefix}_UNREADABLE", path, "symlink target could not be inspected due to permissions"))
            except OSError:
                errors.append(issue(f"{prefix}_INSPECTION_FAILED", path, "symlink target could not be inspected"))
            except RuntimeError:
                errors.append(issue(f"{prefix}_SYMLINK", path, "symlinks are forbidden"))
            else:
                try:
                    resolved_target.relative_to(resolved_root)
                except ValueError:
                    errors.append(issue(f"{prefix}_PATH_ESCAPE", path, "path resolves outside its trusted root"))
                else:
                    errors.append(issue(f"{prefix}_SYMLINK", path, "symlinks are forbidden"))
            return None
    try:
        mode = os.lstat(target).st_mode
    except FileNotFoundError:
        errors.append(issue(f"{prefix}_MISSING", path, "file does not exist"))
        return None
    except PermissionError:
        errors.append(issue(f"{prefix}_UNREADABLE", path, "file could not be inspected due to permissions"))
        return None
    except NotADirectoryError:
        errors.append(issue(f"{prefix}_NOT_REGULAR", path, "file must be regular"))
        return None
    except OSError:
        errors.append(issue(f"{prefix}_INSPECTION_FAILED", path, "file could not be inspected"))
        return None
    if not stat.S_ISREG(mode):
        errors.append(issue(f"{prefix}_NOT_REGULAR", path, "file must be regular"))
        return None
    try:
        return byte_reader(root, relative)
    except FileNotFoundError:
        errors.append(issue(f"{prefix}_DISAPPEARED", path, "file disappeared before its bytes could be read"))
    except PermissionError:
        errors.append(issue(f"{prefix}_UNREADABLE", path, "file bytes could not be read due to permissions"))
    except NonRegularFileError:
        errors.append(issue(f"{prefix}_NOT_REGULAR", path, "file must remain regular while being read"))
    except OSError as error:
        if error.errno == errno.ELOOP:
            errors.append(issue(f"{prefix}_SYMLINK", path, "symlinks are forbidden"))
        elif error.errno in {errno.ENOTDIR, errno.EISDIR, errno.ENXIO}:
            errors.append(issue(f"{prefix}_NOT_REGULAR", path, "file must remain regular while being read"))
        else:
            errors.append(issue(f"{prefix}_READ_FAILED", path, "file bytes could not be read"))
    return None


def valid_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def check_trusted_context(bundle, trusted_context, trusted_bytes, expected_context_sha256, errors):
    if trusted_bytes != canonical_bytes(trusted_context):
        errors.append(issue("TRUSTED_CONTEXT_NONCANONICAL", "$trusted_context", "trusted context must be canonical JSON with one trailing LF"))
    digest = sha256_bytes(trusted_bytes)
    if expected_context_sha256 is None:
        errors.append(issue("EXTERNAL_TRUST_PIN_REQUIRED", "$verifier.expected_context_sha256", "a verifier-owned trusted-context digest is required"))
    elif not valid_sha256(expected_context_sha256):
        errors.append(issue("EXTERNAL_TRUST_PIN_INVALID", "$verifier.expected_context_sha256", "external trusted-context digest must be lowercase SHA-256"))
    elif expected_context_sha256 != digest:
        errors.append(issue("EXTERNAL_TRUST_PIN_MISMATCH", "$verifier.expected_context_sha256", "supplied trusted context does not match the verifier-owned digest"))
    if bundle["trusted_context_sha256"] != digest:
        errors.append(issue("TRUSTED_CONTEXT_DIGEST_MISMATCH", "$.trusted_context_sha256", "bundle does not bind the supplied trusted context bytes"))
    expected = {
        "assignment_id": bundle["assignment_id"],
        "revision_id": bundle["revision_id"],
        "mechanism_id": bundle["mechanism_id"],
        "family_id": bundle["family_id"],
        "identity": bundle["identity"],
    }
    for key, value in expected.items():
        if trusted_context.get(key) != value:
            errors.append(issue("TRUSTED_CONTEXT_MISMATCH", f"$trusted_context.{key}", "bundle field disagrees with separately pinned trusted input"))
    pinned_environments = trusted_context["phase_environments"]
    phase_environments = {
        name: None if phase is None else phase["environment"]
        for name, phase in bundle["phases"].items()
    }
    for name in sorted(phase_environments):
        if pinned_environments[name] != phase_environments[name]:
            errors.append(issue("TRUSTED_ENVIRONMENT_MISMATCH", f"$trusted_context.phase_environments.{name}", "phase environment disagrees with the external trust root"))
    isolated_environment = phase_environments["isolated"]
    whole_environment = phase_environments["whole_model"]
    if whole_environment is not None and whole_environment != isolated_environment:
        errors.append(issue("LOCAL_PHASE_ENVIRONMENT_MISMATCH", "$.phases.whole_model.environment", "isolated and whole-model host, toolchain, thermal, telemetry, and protocol identities must match exactly"))
    roles = [pin["role"] for pin in trusted_context["artifact_pins"]]
    if len(roles) != len(set(roles)):
        errors.append(issue("TRUSTED_ARTIFACT_DUPLICATE_ROLE", "$trusted_context.artifact_pins", "trusted artifact roles must be unique"))


def check_directory_root(root, path, prefix, noun, errors):
    root = Path(root)
    try:
        root_mode = os.lstat(root).st_mode
    except FileNotFoundError:
        errors.append(issue(f"{prefix}_ROOT_MISSING", path, f"{noun} root does not exist"))
        return None
    except PermissionError:
        errors.append(issue(f"{prefix}_ROOT_UNREADABLE", path, f"{noun} root could not be inspected due to permissions"))
        return None
    except OSError:
        errors.append(issue(f"{prefix}_ROOT_INSPECTION_FAILED", path, f"{noun} root could not be inspected"))
        return None
    if stat.S_ISLNK(root_mode):
        errors.append(issue(f"{prefix}_ROOT_SYMLINK", path, f"{noun} root must not be a symlink"))
        return None
    if not stat.S_ISDIR(root_mode):
        errors.append(issue(f"{prefix}_ROOT_NOT_DIRECTORY", path, f"{noun} root must be a directory"))
        return None
    return root


def collect_candidate_surface(candidate_root, errors):
    root = check_directory_root(candidate_root, "$candidate_root", "SURFACE", "candidate", errors)
    if root is None:
        return None

    regular_files = set()

    def visit(directory, prefix):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            errors.append(issue("SURFACE_SCAN_FAILED", f"$candidate_root.{prefix.as_posix()}", "candidate surface could not be enumerated"))
            return
        for entry in entries:
            relative = prefix / entry.name
            relative_text = relative.as_posix()
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError:
                errors.append(issue("SURFACE_SCAN_FAILED", f"$candidate_root.{relative_text}", "candidate surface entry could not be inspected"))
                continue
            if stat.S_ISLNK(mode):
                errors.append(issue("SURFACE_FILE_SYMLINK", f"$candidate_root.{relative_text}", "symlinks are forbidden anywhere in the candidate surface"))
            elif stat.S_ISDIR(mode):
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(mode):
                regular_files.add(relative_text)
            else:
                errors.append(issue("SURFACE_FILE_NOT_REGULAR", f"$candidate_root.{relative_text}", "candidate surface entries must be regular files or containing directories"))

    visit(root, PurePosixPath())
    return regular_files


def check_candidate_surface(trusted_context, candidate_root, errors, byte_reader=read_relative_regular_file):
    files = trusted_context["identity"]["submitted_surface"]["files"]
    expected_paths = {entry["path"] for entry in files}
    initial_error_count = len(errors)
    actual_paths = collect_candidate_surface(candidate_root, errors)
    if actual_paths is None:
        if any(error["code"] == "SURFACE_ROOT_MISSING" for error in errors[initial_error_count:]):
            for index, entry in enumerate(files):
                relative = entry["path"]
                errors.append(issue("SURFACE_LISTED_FILE_MISSING", f"$candidate_root.{relative}", "trusted submitted-surface file is absent from the physical candidate root"))
                errors.append(issue("SURFACE_FILE_MISSING", f"$trusted_context.identity.submitted_surface.files[{index}].path", "file does not exist"))
        return
    for relative in sorted(expected_paths - actual_paths):
        errors.append(issue("SURFACE_LISTED_FILE_MISSING", f"$candidate_root.{relative}", "trusted submitted-surface file is absent from the physical candidate root"))
    for relative in sorted(actual_paths - expected_paths):
        errors.append(issue("SURFACE_UNLISTED_FILE", f"$candidate_root.{relative}", "physical candidate root contains a regular file absent from the trusted submitted surface"))
    for index, entry in enumerate(files):
        path = f"$trusted_context.identity.submitted_surface.files[{index}]"
        data = read_regular_file(candidate_root, entry["path"], f"{path}.path", "SURFACE_FILE", errors, byte_reader)
        if data is None:
            continue
        if len(data) != entry["size"]:
            errors.append(issue("SURFACE_FILE_SIZE_MISMATCH", f"{path}.size", "actual candidate file size disagrees with trusted input"))
        if sha256_bytes(data) != entry["sha256"]:
            errors.append(issue("SURFACE_FILE_HASH_MISMATCH", f"{path}.sha256", "actual candidate file bytes disagree with trusted input"))


def check_artifacts(bundle, artifact_root, join, trusted_context, checker, errors, byte_reader=read_relative_regular_file):
    artifact_root = check_directory_root(artifact_root, "$artifact_root", "ARTIFACT", "artifact", errors)
    if artifact_root is None:
        return {}
    manifests = bundle["artifact_manifest"]
    roles = [entry["role"] for entry in manifests]
    paths = [entry["path"] for entry in manifests]
    for role in sorted(set(roles)):
        if roles.count(role) > 1:
            errors.append(issue("ARTIFACT_DUPLICATE_ROLE", "$.artifact_manifest", f"artifact role {role} is duplicated"))
    for relative in sorted(set(paths)):
        if paths.count(relative) > 1:
            errors.append(issue("ARTIFACT_DUPLICATE_PATH", "$.artifact_manifest", f"artifact path {relative} is duplicated"))
    required_roles = {"ISOLATED_RAW_ROWS"}
    if bundle["phases"]["whole_model"] is not None:
        required_roles.add("WHOLE_MODEL_RAW_ROWS")
    if bundle["phases"]["ranked_m5"] is not None:
        required_roles.add("RANKED_M5_RECEIPT")
    if set(roles) != required_roles:
        errors.append(issue("ARTIFACT_ROLE_SET_INVALID", "$.artifact_manifest", "artifact roles do not exactly match populated phases"))

    pins = {pin["role"]: pin for pin in trusted_context["artifact_pins"]}
    if set(pins) != required_roles:
        errors.append(issue("TRUSTED_ARTIFACT_ROLE_SET_INVALID", "$trusted_context.artifact_pins", "trusted artifact roles do not exactly match populated phases"))
    documents = {}
    for index, artifact in enumerate(manifests):
        path = f"$.artifact_manifest[{index}]"
        role = artifact["role"]
        expected_phase, expected_unit = ROLE_CONTRACT[role]
        if artifact["producing_phase"] != expected_phase or artifact["canonical_units"] != expected_unit:
            errors.append(issue("ARTIFACT_UNIT_MISMATCH", path, "artifact role, phase, and canonical units disagree"))
        check_join(artifact["binding"], join, f"{path}.binding", errors)
        pin = pins.get(role)
        if pin is not None:
            actual_pin = {key: artifact[key] for key in ("role", "path", "size", "sha256")}
            if actual_pin != pin:
                errors.append(issue("TRUSTED_ARTIFACT_MISMATCH", path, "manifest disagrees with separately pinned artifact identity"))
        data = read_regular_file(artifact_root, artifact["path"], f"{path}.path", "ARTIFACT", errors, byte_reader)
        if data is None:
            continue
        if len(data) != artifact["size"]:
            errors.append(issue("ARTIFACT_SIZE_MISMATCH", f"{path}.size", "artifact byte length does not match manifest"))
        if sha256_bytes(data) != artifact["sha256"]:
            errors.append(issue("ARTIFACT_HASH_MISMATCH", f"{path}.sha256", "artifact bytes do not match manifest hash"))
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(issue("ARTIFACT_JSON_INVALID", f"{path}.path", "artifact bytes are not parseable UTF-8 JSON"))
            continue
        if data != canonical_bytes(document):
            errors.append(issue("ARTIFACT_NONCANONICAL", f"{path}.path", "artifact must be canonical JSON with one trailing LF"))
        semantic_errors = checker.check_reference(document, ARTIFACT_DEFINITIONS[role], f"$artifact[{role}]")
        for semantic_error in semantic_errors:
            errors.append(issue("ARTIFACT_SEMANTIC_SCHEMA_INVALID", semantic_error["path"], semantic_error["message"]))
        if semantic_errors:
            continue
        documents[role] = document
        check_join(document["binding"], join, f"$artifact[{role}].binding", errors, code="ARTIFACT_IDENTITY_MISMATCH")
        if document["binding"] != artifact["binding"]:
            errors.append(issue("ARTIFACT_SEMANTIC_MISMATCH", f"$artifact[{role}].binding", "artifact binding disagrees with manifest binding"))
        phase = bundle["phases"][ARTIFACT_PHASE_KEYS[role]]
        if document["evidence"] != phase:
            errors.append(issue("ARTIFACT_SEMANTIC_MISMATCH", f"$artifact[{role}].evidence", "parsed artifact evidence disagrees with bundle phase"))
    return documents


def check_environment(environment, path, errors, ranked=False):
    hardware_class = environment["hardware_class"]
    chip = environment["chip"].upper()
    authority = environment["provenance_authority"]
    consistent = (
        (hardware_class == "M4_LOCAL" and "M4" in chip and authority == "LOCAL_OBSERVATION")
        or (hardware_class == "M5_RANKED" and "M5" in chip and authority == "OFFICIAL_RANKED_RECEIPT")
        or (hardware_class == "OTHER" and authority == "DECLARED_OTHER")
    )
    if not consistent:
        errors.append(issue("ENVIRONMENT_INCONSISTENT", path, "hardware class, chip, and provenance authority disagree"))
    if ranked and hardware_class != "M5_RANKED":
        errors.append(issue("RANKED_HARDWARE_REQUIRED", f"{path}.hardware_class", "ranked evidence requires official M5-ranked hardware"))


def check_correctness(correctness, path, errors, required_gates):
    if correctness["exactness_status"] != "PASS":
        errors.append(issue("CORRECTNESS_FAILED", f"{path}.exactness_status", "exactness must pass"))
    if correctness["checked_token_count"] <= 0:
        errors.append(issue("CHECKED_TOKENS_INVALID", f"{path}.checked_token_count", "at least one checked token is required"))
    memory = correctness["peak_memory"]
    if memory["status"] != "PASS" or memory["measured_bytes"] > memory["limit_bytes"]:
        errors.append(issue("MEMORY_GATE_FAILED", f"{path}.peak_memory", "peak-memory gate must pass within its limit"))
    gate_rows = correctness["gates"]
    names = [row["name"] for row in gate_rows]
    if set(names) != set(GATE_NAMES) or len(names) != len(set(names)):
        errors.append(issue("GATE_SET_INVALID", f"{path}.gates", "all correctness gates must appear exactly once"))
        return
    statuses = {row["name"]: row["status"] for row in gate_rows}
    for name in required_gates:
        if statuses.get(name) != "PASS":
            errors.append(issue("CORRECTNESS_FAILED", f"{path}.gates.{name}", "required correctness gate did not pass"))


def flatten_rows(orders):
    return [row for order in orders for row in order["rows"]]


def check_orders(orders, path, errors, require_both=True, complete_rows=True):
    labels = [order["label"] for order in orders]
    expected_labels = {"ABBA", "BAAB"} if require_both else set(labels)
    if set(labels) != expected_labels or len(labels) != len(set(labels)):
        errors.append(issue("ORDER_SET_INVALID", path, "required mirrored order labels must appear exactly once"))
    for order_index, order in enumerate(orders):
        label = order["label"]
        rows = order["rows"]
        if complete_rows and len(rows) != 4:
            errors.append(issue("ORDER_SEQUENCE_INVALID", f"{path}[{order_index}].rows", "complete order must have four rows"))
            continue
        indices = [row["sequence_index"] for row in rows]
        if indices != list(range(len(rows))):
            errors.append(issue("ORDER_SEQUENCE_INVALID", f"{path}[{order_index}].rows", "sequence indices must be contiguous from zero"))
        expected_arms = ORDER_ARMS[label][:len(rows)]
        if tuple(row["arm"] for row in rows) != expected_arms:
            errors.append(issue("ORDER_SEQUENCE_INVALID", f"{path}[{order_index}].rows", "row arms do not match the declared order"))


def check_isolated(phase, join, errors):
    path = "$.phases.isolated"
    check_join(phase["join_identity"], join, f"{path}.join_identity", errors)
    check_environment(phase["environment"], f"{path}.environment", errors)
    check_correctness(phase["correctness"], f"{path}.correctness", errors, {"PUBLIC_GREEDY_64", "SERIAL_PROTOCOL"})
    complete = phase["status"] == "COMPLETE"
    check_orders(phase["orders"], f"{path}.orders", errors, require_both=complete, complete_rows=True)
    rows = flatten_rows(phase["orders"])
    base = [Decimal(row["seconds"]) for row in rows if row["arm"] == "BASE"]
    candidate = [Decimal(row["seconds"]) for row in rows if row["arm"] == "CANDIDATE"]
    if not base or not candidate:
        errors.append(issue("ORDER_ARMS_INCOMPLETE", f"{path}.orders", "both baseline and candidate observations are required"))
        return
    base_mean = mean(base)
    candidate_mean = mean(candidate)
    factor = base_mean / candidate_mean
    if complete:
        if not phase["complete_chain"]:
            errors.append(issue("CHAIN_INCOMPLETE", f"{path}.complete_chain", "complete isolated evidence must close its chain"))
        if "summary" not in phase:
            errors.append(issue("SUMMARY_MISSING", f"{path}.summary", "complete isolated evidence requires a summary"))
        else:
            check_declared_decimal(phase["summary"]["base_seconds"], base_mean, f"{path}.summary.base_seconds", errors)
            check_declared_decimal(phase["summary"]["candidate_seconds"], candidate_mean, f"{path}.summary.candidate_seconds", errors)
            check_declared_decimal(phase["summary"]["factor"], factor, f"{path}.summary.factor", errors)
        if "uncertainty" not in phase:
            errors.append(issue("UNCERTAINTY_MISSING", f"{path}.uncertainty", "complete isolated evidence requires uncertainty"))
        else:
            uncertainty = max(relative_half_range(base), relative_half_range(candidate))
            check_declared_decimal(phase["uncertainty"]["value"], uncertainty, f"{path}.uncertainty.value", errors)
            limit = Decimal(phase["stop_thresholds"]["max_relative_uncertainty"])
            if uncertainty > limit:
                errors.append(issue("UNCERTAINTY_THRESHOLD_FAILED", f"{path}.uncertainty.value", "isolated uncertainty exceeds its predeclared limit"))
        if "censor" in phase:
            errors.append(issue("CENSOR_CONTRADICTION", f"{path}.censor", "complete isolated evidence cannot carry a censor record"))
        if factor < Decimal(phase["stop_thresholds"]["promote_factor_gte"]):
            errors.append(issue("PROMOTION_THRESHOLD_FAILED", f"{path}.summary.factor", "isolated factor misses its predeclared promotion threshold"))
    else:
        if phase["complete_chain"]:
            errors.append(issue("CENSOR_CONTRADICTION", f"{path}.complete_chain", "censored evidence cannot claim a complete chain"))
        if "summary" in phase or "uncertainty" in phase:
            errors.append(issue("CENSORED_NUMERIC_FABRICATION", path, "censored evidence cannot fabricate complete summary or uncertainty fields"))
        censor = phase.get("censor")
        if censor is None:
            errors.append(issue("CENSOR_RECORD_MISSING", f"{path}.censor", "censored evidence requires its predeclared stop record"))
        else:
            threshold = Decimal(phase["stop_thresholds"]["censor_factor_lte"])
            check_declared_decimal(censor["threshold"], threshold, f"{path}.censor.threshold", errors)
            check_declared_decimal(censor["observed_factor"], factor, f"{path}.censor.observed_factor", errors)
            if factor > threshold:
                errors.append(issue("CENSOR_THRESHOLD_FAILED", f"{path}.censor.observed_factor", "observed factor does not satisfy the predeclared censor rule"))


def check_full_phase(phase, join, path, errors, ranked=False):
    check_join(phase["join_identity"], join, f"{path}.join_identity", errors)
    check_environment(phase["environment"], f"{path}.environment", errors, ranked=ranked)
    required_gates = set(GATE_NAMES) if ranked else {"PUBLIC_GREEDY_64", "SERIAL_PROTOCOL", "TIMED_TOKEN_VALIDATION"}
    check_correctness(phase["correctness"], f"{path}.correctness", errors, required_gates)
    check_orders(phase["orders"], f"{path}.orders", errors)
    rows = flatten_rows(phase["orders"])
    values = {}
    for arm in ("BASE", "CANDIDATE"):
        arm_rows = [row for row in rows if row["arm"] == arm]
        values[arm] = {
            "prefill": mean([Decimal(row["prefill_seconds_per_token"]) for row in arm_rows]),
            "decode": mean([Decimal(row["decode_seconds_per_token"]) for row in arm_rows]),
        }
    prefill_factor = values["BASE"]["prefill"] / values["CANDIDATE"]["prefill"]
    decode_factor = values["BASE"]["decode"] / values["CANDIDATE"]["decode"]
    weighted = weighted_factor(prefill_factor, decode_factor)
    summary = phase["summary"]
    for arm, declared_name in (("BASE", "base"), ("CANDIDATE", "candidate")):
        check_declared_decimal(summary[declared_name]["prefill_seconds_per_token"], values[arm]["prefill"], f"{path}.summary.{declared_name}.prefill_seconds_per_token", errors)
        check_declared_decimal(summary[declared_name]["decode_seconds_per_token"], values[arm]["decode"], f"{path}.summary.{declared_name}.decode_seconds_per_token", errors)
    check_declared_decimal(summary["factors"]["prefill"], prefill_factor, f"{path}.summary.factors.prefill", errors)
    check_declared_decimal(summary["factors"]["decode"], decode_factor, f"{path}.summary.factors.decode", errors)
    check_declared_decimal(summary["factors"]["weighted"], weighted, f"{path}.summary.factors.weighted", errors)
    prefill_uncertainty = maximum_arm_uncertainty(rows, "prefill_seconds_per_token")
    decode_uncertainty = maximum_arm_uncertainty(rows, "decode_seconds_per_token")
    check_declared_decimal(summary["uncertainty"]["prefill"], prefill_uncertainty, f"{path}.summary.uncertainty.prefill", errors)
    check_declared_decimal(summary["uncertainty"]["decode"], decode_uncertainty, f"{path}.summary.uncertainty.decode", errors)
    expected_prefill_pass = prefill_factor >= COMPONENT_FLOOR
    expected_decode_pass = decode_factor >= COMPONENT_FLOOR
    floors = summary["floors"]
    if floors["prefill_pass"] != expected_prefill_pass or floors["decode_pass"] != expected_decode_pass:
        errors.append(issue("FLOOR_VERDICT_MISMATCH", f"{path}.summary.floors", "declared component-floor verdicts disagree with recomputed factors"))
    if not expected_prefill_pass or not expected_decode_pass:
        errors.append(issue("COMPONENT_FLOOR_FAILED", f"{path}.summary.factors", "prefill and decode factors must each be at least 0.95"))
    if ranked and weighted <= STRICT_RANKED_MARGIN:
        errors.append(issue("RANKED_MARGIN_NOT_STRICT", f"{path}.summary.factors.weighted", "ranked weighted factor must strictly exceed the immutable margin"))
    return weighted


def check_receipt(phase, bundle, join, errors):
    path = "$.phases.ranked_m5.receipt"
    receipt = phase["receipt"]
    fields = {
        "assignment_id": join["assignment_id"],
        "revision_id": join["revision_id"],
        "base_sha": join["base_sha"],
        "candidate_sha": join["candidate_sha"],
        "submitted_surface_sha256": join["submitted_surface_sha256"],
        "benchmark_id": join["benchmark_id"],
        "benchmark_contract_sha256": join["benchmark_contract_sha256"],
        "configuration_sha256": join["configuration_sha256"],
        "fixture_id": join["fixture_id"],
        "window_id": join["window_id"],
        "isolated_component_id": join["isolated_component_id"],
        "prefill_component_id": join["prefill_component_id"],
        "decode_component_id": join["decode_component_id"],
        "ranked_environment_sha256": sha256_bytes(canonical_bytes(phase["environment"])),
        "checked_token_count": phase["correctness"]["checked_token_count"],
        "correctness_status": "PASS",
        "peak_memory_status": "PASS",
    }
    for key, expected in fields.items():
        if receipt.get(key) != expected:
            errors.append(issue("RECEIPT_IDENTITY_MISMATCH", f"{path}.{key}", "ranked receipt does not bind to this candidate revision and environment"))


def classify_and_check_terminal(bundle, errors):
    isolated = bundle["phases"]["isolated"]
    whole = bundle["phases"]["whole_model"]
    ranked = bundle["phases"]["ranked_m5"]
    if isolated["status"] == "CENSORED":
        classification = "CENSORED_VALID"
        if whole is not None or ranked is not None:
            errors.append(issue("CENSOR_CONTRADICTION", "$.phases", "censored isolated evidence cannot contain later phases"))
    elif ranked is not None:
        classification = "RANKED_MARGIN_COMPLETE"
        if whole is None:
            errors.append(issue("CHAIN_INCOMPLETE", "$.phases.whole_model", "ranked evidence requires a whole-model predecessor"))
    elif whole is not None:
        classification = "WHOLE_MODEL_COMPLETE"
    else:
        classification = "ISOLATED_COMPLETE"
    expected_state, expected_reason = TERMINAL_CONTRACT[classification]
    terminal = bundle["terminal"]
    if terminal["state"] != expected_state or terminal["predeclared_stop_reason"] != expected_reason or terminal["pending_phases"]:
        errors.append(issue("TERMINAL_CONTRADICTION", "$.terminal", "terminal declaration disagrees with populated evidence phases"))
    return classification


def validate_bundle(
    bundle,
    artifact_root,
    candidate_root,
    trusted_context,
    trusted_bytes,
    expected_context_sha256,
    schema,
    byte_reader=read_relative_regular_file,
):
    digest = sha256_bytes(canonical_bytes(bundle)) if isinstance(bundle, (dict, list)) else sha256_bytes(repr(bundle).encode())
    checker = SchemaChecker(schema)
    errors = checker.check(bundle)
    errors.extend(checker.check_reference(trusted_context, "#/$defs/trustedContext", "$trusted_context"))
    errors = stable_issues(errors)
    if errors:
        return {"bundle_digest": digest, "classification": "INVALID", "errors": errors}
    errors = []
    check_surface(bundle["identity"], errors)
    check_trusted_context(bundle, trusted_context, trusted_bytes, expected_context_sha256, errors)
    check_candidate_surface(trusted_context, candidate_root, errors, byte_reader)
    join = expected_join(bundle)
    check_artifacts(bundle, artifact_root, join, trusted_context, checker, errors, byte_reader)
    check_isolated(bundle["phases"]["isolated"], join, errors)
    whole = bundle["phases"]["whole_model"]
    ranked = bundle["phases"]["ranked_m5"]
    if whole is not None:
        if bundle["phases"]["isolated"]["status"] != "COMPLETE":
            errors.append(issue("CHAIN_INCOMPLETE", "$.phases.isolated", "whole-model evidence requires complete isolated evidence"))
        check_full_phase(whole, join, "$.phases.whole_model", errors)
    if ranked is not None:
        if whole is None or bundle["phases"]["isolated"]["status"] != "COMPLETE":
            errors.append(issue("CHAIN_INCOMPLETE", "$.phases", "ranked evidence requires complete isolated and whole-model phases"))
        check_full_phase(ranked, join, "$.phases.ranked_m5", errors, ranked=True)
        check_receipt(ranked, bundle, join, errors)
    classification = classify_and_check_terminal(bundle, errors)
    errors = stable_issues(errors)
    return {
        "bundle_digest": digest,
        "classification": "INVALID" if errors else classification,
        "errors": errors,
    }


def fixture_join(spec, surface_digest):
    return {
        "assignment_id": spec["assignment_id"],
        "revision_id": spec["revision_id"],
        "mechanism_id": spec["mechanism_id"],
        "family_id": spec["family_id"],
        "base_sha": spec["base_sha"],
        "candidate_sha": spec["candidate_sha"],
        "submitted_surface_sha256": surface_digest,
        "benchmark_id": spec["benchmark_id"],
        "benchmark_contract_sha256": spec["benchmark_contract_sha256"],
        "configuration_sha256": spec["configuration_sha256"],
        "fixture_id": spec["fixture_id"],
        "window_id": spec["window_id"],
        "isolated_component_id": spec["isolated_component_id"],
        "prefill_component_id": spec["prefill_component_id"],
        "decode_component_id": spec["decode_component_id"],
    }


def fixture_environment(ranked=False):
    if ranked:
        return {
            "host_model": "Official M5 Max ranked worker",
            "chip": "Apple M5 Max",
            "os": "macOS synthetic-ranked",
            "toolchain": "Swift synthetic-ranked",
            "thermal_policy_id": "official-40c-gate-v1",
            "telemetry_policy_id": "official-ranked-telemetry-v1",
            "protocol_id": "official-ranked-protocol-v1",
            "hardware_class": "M5_RANKED",
            "provenance_authority": "OFFICIAL_RANKED_RECEIPT",
        }
    return {
        "host_model": "AWS EC2 Mac local worker",
        "chip": "Apple M4 Pro",
        "os": "macOS synthetic-local",
        "toolchain": "Swift synthetic-local",
        "thermal_policy_id": "local-40c-gate-v1",
        "telemetry_policy_id": "local-telemetry-v1",
        "protocol_id": "local-abba-baab-protocol-v1",
        "hardware_class": "M4_LOCAL",
        "provenance_authority": "LOCAL_OBSERVATION",
    }


def fixture_correctness(mode, token_count):
    if mode == "ranked":
        passed = set(GATE_NAMES)
    elif mode == "whole":
        passed = {"PUBLIC_GREEDY_64", "SERIAL_PROTOCOL", "TIMED_TOKEN_VALIDATION"}
    else:
        passed = {"PUBLIC_GREEDY_64", "SERIAL_PROTOCOL"}
    return {
        "exactness_status": "PASS",
        "checked_token_count": token_count,
        "dispatch_call_census": {
            "decode_dispatch_calls": 128 if mode != "isolated" else 1,
            "isolated_dispatch_calls": 8 if mode == "isolated" else 1,
            "prefill_dispatch_calls": 1,
        },
        "peak_memory": {"status": "PASS", "measured_bytes": 24000000000, "limit_bytes": 120000000000},
        "gates": [{"name": name, "status": "PASS" if name in passed else "NOT_RUN"} for name in GATE_NAMES],
    }


def fixture_isolated_orders(base, candidate, labels=("ABBA", "BAAB")):
    timings = {"BASE": base, "CANDIDATE": candidate}
    return [
        {
            "label": label,
            "rows": [
                {"sequence_index": index, "arm": arm, "seconds": timings[arm]}
                for index, arm in enumerate(ORDER_ARMS[label])
            ],
        }
        for label in labels
    ]


def fixture_full_orders(base_prefill, base_decode, candidate_prefill, candidate_decode):
    timings = {
        "BASE": (base_prefill, base_decode),
        "CANDIDATE": (candidate_prefill, candidate_decode),
    }
    return [
        {
            "label": label,
            "rows": [
                {
                    "sequence_index": index,
                    "arm": arm,
                    "prefill_seconds_per_token": timings[arm][0],
                    "decode_seconds_per_token": timings[arm][1],
                }
                for index, arm in enumerate(ORDER_ARMS[label])
            ],
        }
        for label in ("ABBA", "BAAB")
    ]


def full_summary(base_prefill, base_decode, candidate_prefill, candidate_decode):
    prefill = Decimal(base_prefill) / Decimal(candidate_prefill)
    decode = Decimal(base_decode) / Decimal(candidate_decode)
    weighted = weighted_factor(prefill, decode)
    return {
        "base": {"prefill_seconds_per_token": base_prefill, "decode_seconds_per_token": base_decode},
        "candidate": {"prefill_seconds_per_token": candidate_prefill, "decode_seconds_per_token": candidate_decode},
        "factors": {"prefill": str(prefill), "decode": str(decode), "weighted": str(weighted)},
        "uncertainty": {"method": "RELATIVE_HALF_RANGE", "prefill": "0", "decode": "0"},
        "floors": {
            "threshold": "0.95",
            "prefill_pass": prefill >= COMPONENT_FLOOR,
            "decode_pass": decode >= COMPONENT_FLOOR,
        },
    }


def build_fixture_bundle(spec, artifact_specs, candidate_specs):
    candidate_files = {entry["path"]: entry["content"].encode("utf-8") for entry in candidate_specs}
    surface_files = [
        {"path": relative, "size": len(data), "sha256": sha256_bytes(data)}
        for relative, data in sorted(candidate_files.items())
    ]
    surface_digest = sha256_bytes(canonical_bytes(surface_files))
    join = fixture_join(spec, surface_digest)
    identity = {
        "base_sha": spec["base_sha"],
        "candidate_sha": spec["candidate_sha"],
        "submitted_surface": {"files": surface_files, "canonical_sha256": surface_digest},
        "benchmark_id": spec["benchmark_id"],
        "benchmark_contract_sha256": spec["benchmark_contract_sha256"],
        "configuration_sha256": spec["configuration_sha256"],
        "fixture_id": spec["fixture_id"],
        "window": {"id": spec["window_id"], "prefill_tokens": 512, "decode_seed_tokens": 512, "decode_steps": 128},
        "components": {
            "isolated": spec["isolated_component_id"],
            "prefill": spec["prefill_component_id"],
            "decode": spec["decode_component_id"],
        },
    }
    profile = spec["profile"]
    censored = profile == "CENSORED"
    isolated_base = "0.0100"
    isolated_candidate = "0.0102" if censored else "0.0098"
    isolated_factor = Decimal(isolated_base) / Decimal(isolated_candidate)
    isolated = {
        "status": "CENSORED" if censored else "COMPLETE",
        "join_identity": copy.deepcopy(join),
        "environment": fixture_environment(),
        "correctness": fixture_correctness("isolated", 64),
        "perturbation": {"name": "synthetic-threadgroup-width", "value": "64", "unit": "threads"},
        "stop_thresholds": {"promote_factor_gte": "1.01", "censor_factor_lte": "0.99", "max_relative_uncertainty": "0.01"},
        "orders": fixture_isolated_orders(isolated_base, isolated_candidate, ("ABBA",) if censored else ("ABBA", "BAAB")),
        "complete_chain": not censored,
    }
    if censored:
        isolated["censor"] = {"rule": "CANDIDATE_FACTOR_LTE", "threshold": "0.99", "observed_factor": str(isolated_factor)}
    else:
        isolated["summary"] = {"base_seconds": isolated_base, "candidate_seconds": isolated_candidate, "factor": str(isolated_factor)}
        isolated["uncertainty"] = {"method": "RELATIVE_HALF_RANGE", "value": "0"}

    artifact_names = ["censored_isolated" if censored else "isolated"]
    whole = None
    ranked = None
    terminal = {
        "state": "CENSORED" if censored else "ISOLATED_COMPLETE",
        "predeclared_stop_reason": "PREDECLARED_EARLY_STOP" if censored else "ISOLATED_EVIDENCE_COMPLETE",
        "pending_phases": False,
    }
    if profile in {"WHOLE_MODEL_LOCAL", "RANKED_JUST_ABOVE_MARGIN"}:
        whole = {
            "status": "COMPLETE",
            "join_identity": copy.deepcopy(join),
            "environment": fixture_environment(),
            "correctness": fixture_correctness("whole", 640),
            "orders": fixture_full_orders("0.000200", "0.005000", "0.000198", "0.004950"),
            "summary": full_summary("0.000200", "0.005000", "0.000198", "0.004950"),
            "complete_chain": True,
        }
        artifact_names.append("whole_model")
        terminal = {"state": "WHOLE_MODEL_COMPLETE", "predeclared_stop_reason": "WHOLE_MODEL_EVIDENCE_COMPLETE", "pending_phases": False}
    if profile == "RANKED_JUST_ABOVE_MARGIN":
        ranked = {
            "status": "COMPLETE",
            "join_identity": copy.deepcopy(join),
            "environment": fixture_environment(ranked=True),
            "correctness": fixture_correctness("ranked", 640),
            "orders": fixture_full_orders("0.0010038", "0.005019", "0.001", "0.005"),
            "summary": full_summary("0.0010038", "0.005019", "0.001", "0.005"),
            "receipt": {
                "receipt_id": "synthetic-ranked-receipt-v1",
                "benchmark_id": spec["benchmark_id"],
                "terminal": True,
                "assignment_id": spec["assignment_id"],
                "revision_id": spec["revision_id"],
                "base_sha": spec["base_sha"],
                "candidate_sha": spec["candidate_sha"],
                "submitted_surface_sha256": surface_digest,
                "benchmark_contract_sha256": spec["benchmark_contract_sha256"],
                "configuration_sha256": spec["configuration_sha256"],
                "fixture_id": spec["fixture_id"],
                "window_id": spec["window_id"],
                "isolated_component_id": spec["isolated_component_id"],
                "prefill_component_id": spec["prefill_component_id"],
                "decode_component_id": spec["decode_component_id"],
                "ranked_environment_sha256": sha256_bytes(canonical_bytes(fixture_environment(ranked=True))),
                "checked_token_count": 640,
                "correctness_status": "PASS",
                "peak_memory_status": "PASS",
            },
            "complete_chain": True,
        }
        artifact_names.append("ranked_receipt")
        terminal = {"state": "RANKED_MARGIN_COMPLETE", "predeclared_stop_reason": "RANKED_MARGIN_EVIDENCE_COMPLETE", "pending_phases": False}

    role_details = {
        "isolated": ("ISOLATED_RAW_ROWS", "ISOLATED", "seconds_per_invocation", isolated),
        "censored_isolated": ("ISOLATED_RAW_ROWS", "ISOLATED", "seconds_per_invocation", isolated),
        "whole_model": ("WHOLE_MODEL_RAW_ROWS", "WHOLE_MODEL", "seconds_per_token", whole),
        "ranked_receipt": ("RANKED_M5_RECEIPT", "RANKED_M5", "dimensionless_speedup", ranked),
    }
    manifest = []
    artifact_files = {}
    for name in artifact_names:
        artifact_spec = artifact_specs[name]
        role, phase, units, evidence = role_details[name]
        document = {
            "artifact_schema_version": 1,
            "artifact_type": role,
            "binding": copy.deepcopy(join),
            "evidence": copy.deepcopy(evidence),
        }
        data = canonical_bytes(document)
        artifact_files[artifact_spec["path"]] = data
        manifest.append({
            "role": role,
            "path": artifact_spec["path"],
            "size": len(data),
            "sha256": sha256_bytes(data),
            "canonical_units": units,
            "producing_phase": phase,
            "binding": copy.deepcopy(join),
        })
    bundle = {
        "schema_version": 3,
        "assignment_id": spec["assignment_id"],
        "revision_id": spec["revision_id"],
        "mechanism_id": spec["mechanism_id"],
        "family_id": spec["family_id"],
        "trusted_context_sha256": "0" * 64,
        "identity": identity,
        "artifact_manifest": manifest,
        "phases": {"isolated": isolated, "whole_model": whole, "ranked_m5": ranked},
        "terminal": terminal,
        "submission_authorization": False,
    }
    trusted_context = {
        "trust_schema_version": 2,
        "assignment_id": spec["assignment_id"],
        "revision_id": spec["revision_id"],
        "mechanism_id": spec["mechanism_id"],
        "family_id": spec["family_id"],
        "identity": copy.deepcopy(identity),
        "phase_environments": {
            "isolated": copy.deepcopy(isolated["environment"]),
            "whole_model": None if whole is None else copy.deepcopy(whole["environment"]),
            "ranked_m5": None if ranked is None else copy.deepcopy(ranked["environment"]),
        },
        "artifact_pins": [
            {key: entry[key] for key in ("role", "path", "size", "sha256")}
            for entry in manifest
        ],
    }
    bundle["trusted_context_sha256"] = sha256_bytes(canonical_bytes(trusted_context))
    return bundle, artifact_files, trusted_context, candidate_files


def deep_parent(value, dotted_path):
    parts = dotted_path.split(".")
    current = value
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    final = int(parts[-1]) if isinstance(current, list) else parts[-1]
    return current, final


def apply_mutation(bundle, mutation):
    operation = mutation["operation"]
    if operation == "set":
        parent, key = deep_parent(bundle, mutation["path"])
        parent[key] = copy.deepcopy(mutation["value"])
    elif operation == "delete":
        parent, key = deep_parent(bundle, mutation["path"])
        del parent[key]
    elif operation == "append_copy":
        parent, key = deep_parent(bundle, mutation["path"])
        parent[key].append(copy.deepcopy(parent[key][mutation["source_index"]]))
    elif operation == "ranked_exact_tie":
        phase = bundle["phases"]["ranked_m5"]
        margin = str(STRICT_RANKED_MARGIN)
        phase["orders"] = fixture_full_orders(margin, margin, "1", "1")
        phase["summary"] = full_summary(margin, margin, "1", "1")
    elif operation == "ranked_floor_failure":
        phase = bundle["phases"]["ranked_m5"]
        phase["orders"] = fixture_full_orders("0.949", "1.1", "1", "1")
        phase["summary"] = full_summary("0.949", "1.1", "1", "1")
    elif operation not in {
        "artifact_bytes", "artifact_symlink", "artifact_arbitrary_rehash",
        "artifact_semantic_rehash", "coherent_revision_relabel",
        "coherent_m4_as_m5", "coherent_receipt_base_drift",
        "coherent_receipt_benchmark_drift", "coherent_whole_environment_drift",
        "coherent_context_reseal", "candidate_bytes", "candidate_extra_file",
        "candidate_omit_file", "candidate_symlink", "candidate_directory",
    }:
        raise ValueError(f"unknown mutation operation {operation}")


def manifest_for_role(bundle, role):
    return next(entry for entry in bundle["artifact_manifest"] if entry["role"] == role)


def refresh_artifact(bundle, artifact_files, role, document):
    manifest = manifest_for_role(bundle, role)
    data = canonical_bytes(document)
    artifact_files[manifest["path"]] = data
    manifest["size"] = len(data)
    manifest["sha256"] = sha256_bytes(data)


def refresh_trusted_artifact_pin(bundle, trusted_context, role):
    manifest = manifest_for_role(bundle, role)
    pin = next(pin for pin in trusted_context["artifact_pins"] if pin["role"] == role)
    pin.update({key: manifest[key] for key in ("role", "path", "size", "sha256")})
    bundle["trusted_context_sha256"] = sha256_bytes(canonical_bytes(trusted_context))


def replace_revision(value, old, new):
    if isinstance(value, dict):
        for key in value:
            value[key] = replace_revision(value[key], old, new)
    elif isinstance(value, list):
        for index in range(len(value)):
            value[index] = replace_revision(value[index], old, new)
    elif value == old:
        return new
    return value


def mutate_fixture_state(bundle, artifact_files, trusted_context, candidate_files, mutation):
    apply_mutation(bundle, mutation)
    operation = mutation["operation"]
    if operation == "artifact_bytes":
        manifest = bundle["artifact_manifest"][mutation["artifact_index"]]
        artifact_files[manifest["path"]] += b"mutated"
    elif operation == "artifact_arbitrary_rehash":
        manifest = manifest_for_role(bundle, "RANKED_M5_RECEIPT")
        data = b"arbitrary bytes with a refreshed manifest hash\n"
        artifact_files[manifest["path"]] = data
        manifest["size"] = len(data)
        manifest["sha256"] = sha256_bytes(data)
    elif operation == "artifact_semantic_rehash":
        manifest = manifest_for_role(bundle, "RANKED_M5_RECEIPT")
        document = json.loads(artifact_files[manifest["path"]])
        document["evidence"]["receipt"]["checked_token_count"] += 1
        refresh_artifact(bundle, artifact_files, "RANKED_M5_RECEIPT", document)
    elif operation == "coherent_revision_relabel":
        old = bundle["revision_id"]
        new = mutation["value"]
        replace_revision(bundle, old, new)
        for role in list(ARTIFACT_DEFINITIONS):
            try:
                manifest = manifest_for_role(bundle, role)
            except StopIteration:
                continue
            document = json.loads(artifact_files[manifest["path"]])
            replace_revision(document, old, new)
            refresh_artifact(bundle, artifact_files, role, document)
    elif operation == "coherent_m4_as_m5":
        manifest = manifest_for_role(bundle, "RANKED_M5_RECEIPT")
        document = json.loads(artifact_files[manifest["path"]])
        m4_environment = fixture_environment()
        environment_digest = sha256_bytes(canonical_bytes(m4_environment))
        bundle["phases"]["ranked_m5"]["environment"] = copy.deepcopy(m4_environment)
        bundle["phases"]["ranked_m5"]["receipt"]["ranked_environment_sha256"] = environment_digest
        document["evidence"]["environment"] = copy.deepcopy(m4_environment)
        document["evidence"]["receipt"]["ranked_environment_sha256"] = environment_digest
        trusted_context["phase_environments"]["ranked_m5"] = copy.deepcopy(m4_environment)
        refresh_artifact(bundle, artifact_files, "RANKED_M5_RECEIPT", document)
        refresh_trusted_artifact_pin(bundle, trusted_context, "RANKED_M5_RECEIPT")
    elif operation == "coherent_whole_environment_drift":
        phase = bundle["phases"]["whole_model"]
        phase["environment"][mutation["field"]] = copy.deepcopy(mutation["value"])
        manifest = manifest_for_role(bundle, "WHOLE_MODEL_RAW_ROWS")
        document = json.loads(artifact_files[manifest["path"]])
        document["evidence"]["environment"] = copy.deepcopy(phase["environment"])
        trusted_context["phase_environments"]["whole_model"] = copy.deepcopy(phase["environment"])
        refresh_artifact(bundle, artifact_files, "WHOLE_MODEL_RAW_ROWS", document)
        refresh_trusted_artifact_pin(bundle, trusted_context, "WHOLE_MODEL_RAW_ROWS")
    elif operation == "coherent_context_reseal":
        phase = bundle["phases"]["ranked_m5"]
        environment = copy.deepcopy(phase["environment"])
        environment["toolchain"] = "Swift synthetic-ranked-resealed"
        environment_digest = sha256_bytes(canonical_bytes(environment))
        phase["environment"] = environment
        phase["receipt"]["ranked_environment_sha256"] = environment_digest
        manifest = manifest_for_role(bundle, "RANKED_M5_RECEIPT")
        document = json.loads(artifact_files[manifest["path"]])
        document["evidence"]["environment"] = copy.deepcopy(environment)
        document["evidence"]["receipt"]["ranked_environment_sha256"] = environment_digest
        trusted_context["phase_environments"]["ranked_m5"] = copy.deepcopy(environment)
        refresh_artifact(bundle, artifact_files, "RANKED_M5_RECEIPT", document)
        refresh_trusted_artifact_pin(bundle, trusted_context, "RANKED_M5_RECEIPT")
    elif operation in {"coherent_receipt_base_drift", "coherent_receipt_benchmark_drift"}:
        key = "base_sha" if operation.endswith("base_drift") else "benchmark_id"
        bundle["phases"]["ranked_m5"]["receipt"][key] = mutation["value"]
        manifest = manifest_for_role(bundle, "RANKED_M5_RECEIPT")
        document = json.loads(artifact_files[manifest["path"]])
        document["evidence"]["receipt"][key] = mutation["value"]
        refresh_artifact(bundle, artifact_files, "RANKED_M5_RECEIPT", document)
    elif operation == "candidate_bytes":
        relative = sorted(candidate_files)[mutation.get("file_index", 0)]
        candidate_files[relative] += b"mutated"
    elif operation == "candidate_extra_file":
        candidate_files["Sources/MLXFastModel/Unlisted.swift"] = b"unlisted\n"
    elif operation == "candidate_omit_file":
        del candidate_files[sorted(candidate_files)[mutation.get("file_index", 0)]]


def write_files(root, files):
    for relative, data in files.items():
        target = root.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def result_exit_code(result):
    return 1 if result["classification"] == "INVALID" else 0


def remove_path(path):
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def mutate_filesystem_control(control, root, artifact_root, candidate_root, bundle, candidate_files):
    scope = control["scope"]
    operation = control["operation"]
    byte_reader = read_relative_regular_file
    if scope in {"candidate_root", "artifact_root"}:
        if operation not in {"missing", "symlink", "regular", "fifo"}:
            raise ValueError(f"unknown root filesystem control operation: {operation}")
        target = candidate_root if scope == "candidate_root" else artifact_root
        remove_path(target)
        if operation == "symlink":
            other = root / f"{control['id']}-target"
            other.mkdir()
            target.symlink_to(other, target_is_directory=True)
        elif operation == "regular":
            target.write_bytes(b"not a directory\n")
        elif operation == "fifo":
            os.mkfifo(target)
    elif scope in {"candidate_entry", "artifact_entry"}:
        if operation not in {"directory", "fifo", "symlink"}:
            raise ValueError(f"unknown entry filesystem control operation: {operation}")
        if scope == "candidate_entry":
            relative = sorted(candidate_files)[0]
            target_root = candidate_root
        else:
            relative = bundle["artifact_manifest"][0]["path"]
            target_root = artifact_root
        target = target_root.joinpath(*PurePosixPath(relative).parts)
        remove_path(target)
        if operation == "directory":
            target.mkdir()
        elif operation == "fifo":
            os.mkfifo(target)
        else:
            target.symlink_to(target.parent, target_is_directory=True)
    elif scope in {"candidate_transition", "artifact_transition"}:
        if operation not in {"disappears", "unreadable"}:
            raise ValueError(f"unknown transition filesystem control operation: {operation}")
        transition_root = candidate_root if scope == "candidate_transition" else artifact_root
        transition_relative = (
            sorted(candidate_files)[0]
            if scope == "candidate_transition"
            else bundle["artifact_manifest"][0]["path"]
        )

        def transition_reader(read_root, relative):
            if Path(read_root) == transition_root and relative == transition_relative:
                if operation == "disappears":
                    raise FileNotFoundError(errno.ENOENT, "synthetic disappearance", relative)
                raise PermissionError(errno.EACCES, "synthetic unreadable file", relative)
            return read_relative_regular_file(read_root, relative)

        byte_reader = transition_reader
    else:
        raise ValueError(f"unknown filesystem control scope: {scope}")
    return byte_reader


def execute_filesystem_control_suite(fixtures, schema):
    positives = {entry["id"]: entry for entry in fixtures["positive_fixtures"]}
    spec = positives["isolated-only"]
    artifact_specs = fixtures["artifact_files"]
    candidate_specs = fixtures["candidate_files"]
    results = []
    for control in sorted(fixtures["filesystem_controls"], key=lambda entry: entry["id"]):
        bundle, artifacts, trusted_context, candidate_files = build_fixture_bundle(spec, artifact_specs, candidate_specs)
        trusted_bytes = canonical_bytes(trusted_context)
        expected_context_sha256 = sha256_bytes(trusted_bytes)
        with tempfile.TemporaryDirectory(prefix="candidate-evidence-filesystem-") as directory:
            root = Path(directory)
            artifact_root = root / "artifact-root"
            candidate_root = root / "candidate-root"
            write_files(artifact_root, artifacts)
            write_files(candidate_root, candidate_files)
            byte_reader = mutate_filesystem_control(
                control,
                root,
                artifact_root,
                candidate_root,
                bundle,
                candidate_files,
            )
            result = validate_bundle(
                bundle,
                artifact_root,
                candidate_root,
                trusted_context,
                trusted_bytes,
                expected_context_sha256,
                schema,
                byte_reader,
            )
        actual_errors = sorted((entry["code"], entry["path"]) for entry in result["errors"])
        expected_errors = sorted((entry["code"], entry["path"]) for entry in control["expected_errors"])
        exit_code = result_exit_code(result)
        passed = result["classification"] == "INVALID" and exit_code == 1 and actual_errors == expected_errors
        results.append(
            {
                "classification": result["classification"],
                "errors": result["errors"],
                "exit_code": exit_code,
                "id": control["id"],
                "kind": "filesystem",
                "passed": passed,
            }
        )
    return results


def execute_exception_passthrough_controls():
    controls = {}
    with tempfile.TemporaryDirectory(prefix="candidate-evidence-exceptions-") as directory:
        root = Path(directory)
        relative = "regular.txt"
        write_files(root, {relative: b"regular\n"})

        def fail_with_programming_error(_root, _relative):
            raise ValueError("synthetic programming error")

        try:
            read_regular_file(root, relative, "$test.path", "TEST", [], fail_with_programming_error)
        except ValueError:
            controls["reader_value_error"] = True
        else:
            controls["reader_value_error"] = False

        reader_errors = {
            "reader_not_a_directory": (NotADirectoryError(errno.ENOTDIR, "synthetic not-a-directory"), "TEST_NOT_REGULAR"),
            "reader_os_error": (OSError(errno.EIO, "synthetic read failure"), "TEST_READ_FAILED"),
            "reader_permission_error": (PermissionError(errno.EACCES, "synthetic unreadable"), "TEST_UNREADABLE"),
        }
        for name, (failure, expected_code) in reader_errors.items():
            errors = []

            def fail_with_filesystem_error(_root, _relative, error=failure):
                raise error

            contents = read_regular_file(root, relative, "$test.path", "TEST", errors, fail_with_filesystem_error)
            controls[name] = contents is None and [entry["code"] for entry in errors] == [expected_code]
    try:
        SchemaChecker({"$ref": "https://mlxfast.invalid/external"}).check({})
    except ValueError:
        controls["schema_value_error"] = True
    else:
        controls["schema_value_error"] = False
    return controls


def execute_fixture_suite(fixtures, schema):
    positives = {entry["id"]: entry for entry in fixtures["positive_fixtures"]}
    artifact_specs = fixtures["artifact_files"]
    candidate_specs = fixtures["candidate_files"]
    results = []
    for fixture_id in sorted(positives):
        spec = positives[fixture_id]
        bundle, artifacts, trusted_context, candidate_files = build_fixture_bundle(spec, artifact_specs, candidate_specs)
        expected_context_sha256 = sha256_bytes(canonical_bytes(trusted_context))
        with tempfile.TemporaryDirectory(prefix="candidate-evidence-") as directory:
            root = Path(directory)
            artifact_root = root / "artifact-root"
            candidate_root = root / "candidate-root"
            write_files(artifact_root, artifacts)
            write_files(candidate_root, candidate_files)
            trusted_bytes = canonical_bytes(trusted_context)
            result = validate_bundle(
                bundle,
                artifact_root,
                candidate_root,
                trusted_context,
                trusted_bytes,
                expected_context_sha256,
                schema,
            )
        passed = result["classification"] == spec["expected_classification"] and not result["errors"]
        if "expected_weighted_factor" in spec:
            weighted = bundle["phases"]["ranked_m5"]["summary"]["factors"]["weighted"]
            passed = passed and Decimal(weighted) == Decimal(spec["expected_weighted_factor"])
        results.append({"classification": result["classification"], "errors": result["errors"], "id": fixture_id, "kind": "positive", "passed": passed})

    for mutation in sorted(fixtures["negative_mutations"], key=lambda entry: entry["id"]):
        spec = positives[mutation["source_fixture"]]
        bundle, artifacts, trusted_context, candidate_files = build_fixture_bundle(spec, artifact_specs, candidate_specs)
        expected_context_sha256 = sha256_bytes(canonical_bytes(trusted_context))
        mutate_fixture_state(bundle, artifacts, trusted_context, candidate_files, mutation)
        with tempfile.TemporaryDirectory(prefix="candidate-evidence-") as directory:
            root = Path(directory)
            artifact_root = root / "artifact-root"
            candidate_root = root / "candidate-root"
            write_files(artifact_root, artifacts)
            write_files(candidate_root, candidate_files)
            if mutation["operation"] == "artifact_symlink":
                manifest = bundle["artifact_manifest"][mutation["artifact_index"]]
                target = artifact_root.joinpath(*PurePosixPath(manifest["path"]).parts)
                other = artifact_root / "safe-symlink-target.json"
                other.write_bytes(target.read_bytes())
                target.unlink()
                target.symlink_to(other)
            elif mutation["operation"] in {"candidate_symlink", "candidate_directory"}:
                relative = sorted(candidate_files)[mutation.get("file_index", 0)]
                target = candidate_root.joinpath(*PurePosixPath(relative).parts)
                target.unlink()
                if mutation["operation"] == "candidate_symlink":
                    other = root / "candidate-safe-target"
                    other.write_bytes(b"safe target\n")
                    target.symlink_to(other)
                else:
                    target.mkdir()
            trusted_bytes = canonical_bytes(trusted_context)
            expected_pin = None if mutation["operation"] == "coherent_context_reseal" else expected_context_sha256
            result = validate_bundle(
                bundle,
                artifact_root,
                candidate_root,
                trusted_context,
                trusted_bytes,
                expected_pin,
                schema,
            )
        codes = {entry["code"] for entry in result["errors"]}
        passed = result["classification"] == "INVALID" and mutation["expected_error_code"] in codes
        results.append({"classification": result["classification"], "errors": result["errors"], "id": mutation["id"], "kind": "negative", "passed": passed})
    return results


def run_self_test(fixtures_path, schema_path):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    if (
        schema.get("$id") != SCHEMA_ID
        or schema.get("properties", {}).get("schema_version", {}).get("const") != 3
        or fixtures.get("fixture_schema_version") != 3
    ):
        raise ValueError("contract identity/version mismatch")
    legacy_first = execute_fixture_suite(fixtures, schema)
    legacy_second = execute_fixture_suite(fixtures, schema)
    filesystem_first = execute_filesystem_control_suite(fixtures, schema)
    filesystem_second = execute_filesystem_control_suite(fixtures, schema)
    exceptions_first = execute_exception_passthrough_controls()
    exceptions_second = execute_exception_passthrough_controls()
    legacy_first_bytes = canonical_bytes(legacy_first)
    legacy_second_bytes = canonical_bytes(legacy_second)
    filesystem_first_bytes = canonical_bytes(filesystem_first)
    filesystem_second_bytes = canonical_bytes(filesystem_second)
    combined_first = legacy_first + filesystem_first
    combined_second = legacy_second + filesystem_second
    combined_first_bytes = canonical_bytes(combined_first)
    combined_second_bytes = canonical_bytes(combined_second)
    legacy_digest = sha256_bytes(legacy_first_bytes)
    filesystem_digest = sha256_bytes(filesystem_first_bytes)
    deterministic = (
        legacy_first_bytes == legacy_second_bytes
        and filesystem_first_bytes == filesystem_second_bytes
        and combined_first_bytes == combined_second_bytes
        and exceptions_first == exceptions_second
    )
    passed = (
        deterministic
        and len(legacy_first) == 49
        and len(filesystem_first) == len(fixtures["filesystem_controls"])
        and legacy_digest == "75d8e716d4887e3b4aaac08499d44da281923d7de465ecf35de500bffc444124"
        and all(result["passed"] for result in combined_first)
        and all(exceptions_first.values())
    )
    output = {
        "case_count": len(combined_first),
        "deterministic": deterministic,
        "exception_passthrough": exceptions_first,
        "filesystem_case_count": len(filesystem_first),
        "filesystem_results_digest": filesystem_digest,
        "legacy_case_count": len(legacy_first),
        "legacy_results_digest": legacy_digest,
        "results_digest": sha256_bytes(combined_first_bytes),
        "schema_id": SCHEMA_ID,
        "status": (
            "CANDIDATE_EVIDENCE_ROOTS_FAIL_CLOSED"
            if passed
            else "CANDIDATE_EVIDENCE_ROOTS_FAIL_CLOSED_FAILED"
        ),
        "tests": combined_first,
    }
    print(canonical_bytes(output).decode("utf-8"), end="")
    return 0 if passed else 1


def main():
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Validate one content-addressed MLXFast candidate evidence bundle")
    parser.add_argument("bundle", nargs="?", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--trusted-context", type=Path)
    parser.add_argument("--expected-context-sha256")
    parser.add_argument("--schema", type=Path, default=directory / "candidate_evidence_bundle.schema.json")
    parser.add_argument("--fixtures", type=Path, default=directory / "candidate_evidence_bundle_fixtures.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test(args.fixtures, args.schema)
    if (
        args.bundle is None
        or args.artifact_root is None
        or args.candidate_root is None
        or args.trusted_context is None
        or args.expected_context_sha256 is None
    ):
        parser.error(
            "bundle, --artifact-root, --candidate-root, --trusted-context, and "
            "--expected-context-sha256 are required unless --self-test is used"
        )
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    trusted_bytes = args.trusted_context.read_bytes()
    trusted_context = json.loads(trusted_bytes.decode("utf-8"))
    result = validate_bundle(
        bundle,
        args.artifact_root,
        args.candidate_root,
        trusted_context,
        trusted_bytes,
        args.expected_context_sha256,
        schema,
    )
    print(canonical_bytes(result).decode("utf-8"), end="")
    return result_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
