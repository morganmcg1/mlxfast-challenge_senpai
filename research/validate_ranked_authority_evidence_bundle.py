#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "ranked-authority-evidence-bundle/v1"
FIXTURE_VERSION = "ranked-authority-evidence-fixtures/v1"
REQUIRED_PHASES = {"transform", "trusted_hash", "reaper", "worker_spawn", "worker_load_epoch"}
REQUIRED_EVENTS = [
    "transform",
    "trusted_hash",
    "reaper",
    "profile_generated",
    "sandbox_injected",
    "worker_spawn",
    "load_start",
    "load_end",
]
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
        if installed_path in installed_paths:
            errors.append(error("INSTALLED_PATH_COLLISION", f"{path}.installed_path", "two roles claim the same installed path"))
        else:
            installed_paths[installed_path] = role

    absent = sorted(set(required) - set(by_role))
    if absent:
        if len(absent) == 1 and absent[0] == missing_role:
            pass
        elif len(absent) == 1:
            errors.append(error("MISSING_AUTHORITY_UNDECLARED", "required_artifact_roles", f"required artifact role {absent[0]} is absent without the matching missing_authority declaration"))
        else:
            errors.append(error("MULTIPLE_MISSING_AUTHORITIES", "required_artifact_roles", f"multiple required artifact roles are absent: {', '.join(absent)}"))
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
    for index, item in enumerate(observed if isinstance(observed, list) else []):
        if not isinstance(item, dict):
            errors.append(error("ENV_OBSERVATION_TYPE", f"environment.observed[{index}]", "environment observation must be an object"))
            continue
        name = item.get("name")
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
    for actor_id, actor in by_id.items():
        parent = actor.get("parent_actor_id")
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
    missing = sorted(REQUIRED_PHASES - set(by_name))
    if missing:
        errors.append(error("REQUIRED_PHASE_MISSING", "phases", f"required phases are absent: {', '.join(missing)}"))
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

    missing_types = [event_type for event_type in REQUIRED_EVENTS if event_type not in by_type]
    if missing_types:
        errors.append(error("REQUIRED_EVENT_MISSING", "events", f"required event types are absent: {', '.join(missing_types)}"))
    else:
        sequences = [by_type[event_type].get("sequence") for event_type in REQUIRED_EVENTS]
        if any(not isinstance(value, int) for value in sequences) or sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            errors.append(error("EVENT_ORDER_REVERSAL", "events", "required ranked events are not in strict transform-to-load order"))

    adjacency = {event_id: [] for event_id in by_id}
    edge_types = set()
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
        edge_types.add((by_id[source].get("type"), by_id[target].get("type"), edge_type))
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

    required_edges = {
        ("profile_generated", "sandbox_injected", "sandbox_injection"),
        ("sandbox_injected", "worker_spawn", "spawn"),
        ("worker_spawn", "load_start", "spawn"),
        ("load_start", "load_end", "load_epoch_bounds"),
    }
    missing_edges = sorted(required_edges - edge_types)
    if missing_edges:
        errors.append(error("REQUIRED_EVENT_EDGE_MISSING", "event_edges", f"required typed edges are absent: {missing_edges}"))

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
    for index, capability in enumerate(confinement.get("capabilities", [])):
        if not isinstance(capability, dict):
            errors.append(error("CAPABILITY_TYPE", f"confinement.capabilities[{index}]", "capability must be an object"))
            continue
        phase_name = capability.get("phase")
        phase = phases.get(phase_name)
        if phase is None or capability.get("actor_id") != phase.get("actor_id"):
            errors.append(error("CAPABILITY_ACTOR_CONTRADICTION", f"confinement.capabilities[{index}]", "capability actor contradicts phase actor"))
        capability_by_phase[phase_name] = capability
    load_capability = capability_by_phase.get("worker_load_epoch")
    if load_capability is None:
        errors.append(error("LOAD_CAPABILITY_MISSING", "confinement.capabilities", "worker load epoch capability is absent"))
    elif not load_capability.get("read") or (weights.get("immutable_during_load") and any(load_capability.get(name) for name in ("write", "rename", "unlink"))):
        errors.append(error("LOAD_IMMUTABILITY_CONTRADICTION", "confinement.capabilities[worker_load_epoch]", "load epoch rights contradict immutable read-only weights"))

    profile_role = confinement.get("sandbox_profile_role")
    profile = artifacts.get(profile_role)
    if profile is None:
        if profile_role != missing_role:
            errors.append(error("PROFILE_ARTIFACT_MISSING", "confinement.sandbox_profile_role", "sandbox profile artifact is absent"))
    elif confinement.get("sandbox_profile_sha256") != profile.get("sha256"):
        errors.append(error("PROFILE_HASH_MISMATCH", "confinement.sandbox_profile_sha256", "sandbox profile hash does not match the physical profile artifact"))
    generator_role = confinement.get("profile_generator_role")
    if generator_role not in artifacts and generator_role != missing_role:
        errors.append(error("PROFILE_GENERATOR_MISSING", "confinement.profile_generator_role", "profile generator artifact is absent"))
    for index, role in enumerate(confinement.get("profile_generator_input_roles", [])):
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
    for index, link in enumerate(crypto.get("generation_links", [])):
        if not isinstance(link, dict):
            errors.append(error("GENERATION_LINK_TYPE", f"crypto_linkage.generation_links[{index}]", "generation link must be an object"))
            continue
        roles = [link.get("output_role"), link.get("generator_role")] + list(link.get("input_roles", []))
        if missing_role in roles:
            continue
        output = artifacts.get(link.get("output_role"))
        generator = artifacts.get(link.get("generator_role"))
        inputs = [artifacts.get(role) for role in link.get("input_roles", [])]
        if output is None or generator is None or any(item is None for item in inputs):
            errors.append(error("GENERATION_ARTIFACT_MISSING", f"crypto_linkage.generation_links[{index}]", "generation link references an absent artifact"))
            continue
        if link.get("output_sha256") != output.get("sha256") or link.get("generator_sha256") != generator.get("sha256"):
            errors.append(error("GENERATION_HASH_MISMATCH", f"crypto_linkage.generation_links[{index}]", "generation output/generator hash is not linked to the artifact set"))
        if link.get("input_sha256") != [item.get("sha256") for item in inputs]:
            errors.append(error("GENERATION_INPUT_HASH_MISMATCH", f"crypto_linkage.generation_links[{index}].input_sha256", "generation input hashes are not linked to the artifact set"))
        for field in ("base_sha", "workflow_sha", "run_id", "job_id"):
            if link.get(field) != capture.get(field):
                errors.append(error("GENERATION_IDENTITY_DRIFT", f"crypto_linkage.generation_links[{index}].{field}", "generation context does not match the ranked capture"))
        if link.get("link_sha256") != digest_value(generation_payload(link)):
            errors.append(error("GENERATION_LINK_DIGEST_MISMATCH", f"crypto_linkage.generation_links[{index}].link_sha256", "generation link digest is incorrect"))

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
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(error("SCHEMA_VERSION", "schema_version", f"expected {SCHEMA_VERSION}"))
    required_top = {
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

    compare_identity(errors, data.get("target_identity", {}), data.get("capture_identity", {}))
    started, finished = validate_capture_window(errors, data)
    artifacts, _ = validate_artifacts(errors, data, root, missing_role)
    validate_environment(errors, data)
    actors, phases = validate_actors_and_phases(errors, data, artifacts)
    validate_events(errors, data, artifacts, actors, started, finished, missing_role)
    validate_confinement(errors, data, artifacts, phases, missing_role)
    validate_crypto(errors, data, artifacts, missing_role)

    errors = sorted(errors, key=lambda item: (item["code"], item["path"], item["message"]))
    if errors:
        state = "INVALID"
    elif missing_role:
        state = "INCOMPLETE"
    else:
        state = "STATIC_RESUME_READY"
    authority = data.get("authority", {})
    return {
        "state": state,
        "bundle_digest_sha256": digest_value(data),
        "errors": errors,
        "missing_authority": missing_declaration,
        "authoritative": bool(authority.get("authoritative")) and not bool(authority.get("synthetic")),
    }


def refresh_derived(data, artifacts_by_role=None):
    artifacts_by_role = artifacts_by_role or {item["role"]: item for item in data.get("artifacts", [])}
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


def mutate_fixture(name, data, root):
    by_role = {item["role"]: item for item in data["artifacts"]}
    target = by_role.get("bench_exec")
    if name == "none":
        return
    if name == "missing_profile_generator_input":
        role = "profile_generator_input"
        artifact = by_role[role]
        safe_bundle_path(root, artifact["bundle_path"]).unlink()
        data["artifacts"] = [item for item in data["artifacts"] if item["role"] != role]
        data["missing_authority"] = {
            "kind": "artifact_role",
            "role": role,
            "fact": "exact profile generator input bytes and installed metadata",
            "reason": "synthetic fixture intentionally omits the first unavailable authority fact",
        }
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
        "schema_version": "ranked-authority-evidence-fixture-results/v1",
        "fixture_source_sha256": digest_file(fixture_path),
        "non_authoritative": True,
        "case_count": len(results),
        "passed": not failures,
        "results": results,
        "failures": failures,
    }
    return output


def main():
    parser = argparse.ArgumentParser(description="Validate a ranked installed-authority evidence bundle")
    parser.add_argument("--bundle-root", type=Path, help="directory containing physical evidence files")
    parser.add_argument("--manifest", type=Path, help="bundle manifest JSON (defaults to BUNDLE_ROOT/bundle.json)")
    parser.add_argument("--run-fixtures", type=Path, help="run the committed synthetic fixture suite")
    args = parser.parse_args()

    if args.run_fixtures:
        if args.bundle_root or args.manifest:
            parser.error("--run-fixtures cannot be combined with bundle arguments")
        output = run_fixture_suite(args.run_fixtures.resolve())
        sys.stdout.buffer.write(canonical_bytes(output))
        return 0 if output["passed"] else 1
    if args.bundle_root is None:
        parser.error("--bundle-root is required unless --run-fixtures is used")
    root = args.bundle_root.resolve()
    manifest = (args.manifest or root / "bundle.json").resolve()
    data = json.loads(manifest.read_text())
    output = validate_bundle(data, root)
    sys.stdout.buffer.write(canonical_bytes(output))
    return 0 if output["state"] in {"STATIC_RESUME_READY", "INCOMPLETE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
