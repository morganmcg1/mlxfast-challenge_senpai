#!/usr/bin/env python3
"""Run the four frozen 6,144-token AIME diagnostics for the top-15 study.

This is intentionally separate from run-study.sh.  It accepts only primary
quality arms that ended in the validated, hash-bound AIME length condition,
and it never writes into the primary results tree.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from typing import Any, Iterator, Sequence


FROZEN_RANKS = (116, 117, 118, 119)
FROZEN_ID = "2024-2024-II-2"
MODEL_NAME = "laguna-xs-2.1"
MAX_TOKENS = 6_144
ORIGINAL_MAX_TOKENS = 2_048
REQUEST_TIMEOUT_S = 900
STARTUP_TIMEOUT_S = 900
READY_TIMEOUT_S = 930
SCHEMA = "mlxfast-top15-extended-aime-v1"


class DiagnosticError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DiagnosticError(f"cannot read JSON {path}: {error}") from error


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_bytes_once(path: Path, payload: bytes, *, accept_same: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if accept_same and path.read_bytes() == payload:
            return
        raise DiagnosticError(f"refusing to overwrite immutable artifact: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            if accept_same and path.read_bytes() == payload:
                return
            raise DiagnosticError(f"immutable artifact appeared concurrently: {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def write_json_once(path: Path, value: Any, *, accept_same: bool = False) -> None:
    write_bytes_once(path, json_bytes(value), accept_same=accept_same)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DiagnosticError(message)


def require_sha(value: Any, label: str) -> str:
    require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} is not a SHA-256",
    )
    return value


def require_git_sha(value: Any, label: str) -> str:
    require(
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value),
        f"{label} is not a full Git commit",
    )
    return value


def checked_path(root: Path, relative: Any, label: str) -> Path:
    require(isinstance(relative, str) and relative, f"{label} path is missing")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise DiagnosticError(f"{label} escapes its arm directory: {relative}") from error
    return candidate


def run_checked(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=True,
            text=True,
            capture_output=capture,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or error.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise DiagnosticError(f"command failed: {' '.join(command)}{suffix}") from error


@dataclasses.dataclass(frozen=True)
class Config:
    script: Path
    study_dir: Path
    repo: Path
    manifest: Path
    workspace: Path
    primary_results: Path
    results: Path
    weights: Path
    reference: Path
    wrapper: Path
    ids: Path
    manifest_data: dict[str, Any]

    @classmethod
    def discover(cls) -> "Config":
        script = Path(__file__).resolve()
        study_dir = script.parent
        repo_text = run_checked(
            ["git", "-C", str(study_dir), "rev-parse", "--show-toplevel"]
        ).stdout.strip()
        repo = Path(repo_text).resolve()
        manifest = Path(
            os.environ.get("MLXFAST_TOP15_MANIFEST", study_dir / "candidates.json")
        ).expanduser().resolve()
        data = load_json(manifest)
        require(isinstance(data, dict), f"manifest must be an object: {manifest}")
        workspace = Path(
            os.environ.get(
                "MLXFAST_TOP15_WORKSPACE",
                repo / "quality-results/.top15-workspace-20260802",
            )
        ).expanduser().resolve()
        primary_results = Path(
            os.environ.get(
                "MLXFAST_TOP15_PRIMARY_RESULTS",
                repo / "quality-results/leaderboard-top15-20260802",
            )
        ).expanduser().resolve()
        results = Path(
            os.environ.get(
                "MLXFAST_TOP15_EXTENDED_AIME_RESULTS",
                repo / "quality-results/leaderboard-top15-20260802-aime-extended-6144",
            )
        ).expanduser().resolve()
        weights = Path(
            os.environ.get("MLXFAST_TOP15_WEIGHTS", repo / "weights")
        ).expanduser().resolve()
        reference = Path(
            os.environ.get(
                "MLXFAST_TOP15_REFERENCE",
                repo / "reference_weights/laguna-xs-2.1-nvfp4-mlx",
            )
        ).expanduser().resolve()
        return cls(
            script=script,
            study_dir=study_dir,
            repo=repo,
            manifest=manifest,
            workspace=workspace,
            primary_results=primary_results,
            results=results,
            weights=weights,
            reference=reference,
            wrapper=study_dir / "quality-bridge-wrapper.sh",
            ids=study_dir / "extended-aime-ids.json",
            manifest_data=data,
        )

    @property
    def study(self) -> str:
        return str(self.manifest_data["study"])

    @property
    def harness_commit(self) -> str:
        return str(self.manifest_data["harness_commit"])

    @property
    def evaluator_commit(self) -> str:
        return str(self.manifest_data["evaluator_commit"])

    @property
    def evaluator_sha256(self) -> str:
        return str(self.manifest_data["evaluator_sha256"])

    @property
    def manifest_sha256(self) -> str:
        return sha256_file(self.manifest)

    @property
    def evaluator_root(self) -> Path:
        return self.results / "_pinned-evaluator"

    @property
    def evaluator_cli(self) -> Path:
        return self.evaluator_root / "senpai/quality-eval"

    @property
    def evaluator_project(self) -> Path:
        return self.evaluator_root / "senpai/quality_eval"

    @property
    def uv_cache(self) -> Path:
        return self.workspace / "senpai/quality_eval/.uv-cache"


@dataclasses.dataclass(frozen=True)
class Candidate:
    rank: int
    submission_id: str
    source_ref: str

    @property
    def name(self) -> str:
        return f"{self.rank}-{self.submission_id}"


@dataclasses.dataclass(frozen=True)
class PrimaryEvidence:
    candidate: Candidate
    arm_dir: Path
    marker_path: Path
    marker_sha256: str
    marker: dict[str, Any]
    run_spec_path: Path
    run_spec_sha256: str
    run_path: Path
    run_sha256: str
    aime_path: Path
    aime_sha256: str
    prompt_sha256: str
    gold: int
    original_answer: int | None
    original_sample_chars: int
    bridge_sha256: str
    bridge_source_sha256: str
    metallib_sha256: str
    editable_source_sha256: str


def candidates(config: Config) -> list[Candidate]:
    raw = config.manifest_data.get("candidates")
    require(isinstance(raw, list), "manifest candidates must be a list")
    parsed: list[Candidate] = []
    for row in raw:
        require(isinstance(row, dict), "manifest candidate row must be an object")
        parsed.append(
            Candidate(
                rank=int(row["rank"]),
                submission_id=str(row["submission_id"]),
                source_ref=str(row["source_ref"]),
            )
        )
    by_rank = {candidate.rank: candidate for candidate in parsed}
    require(len(by_rank) == len(parsed), "manifest candidate ranks are not unique")
    missing = [rank for rank in FROZEN_RANKS if rank not in by_rank]
    require(not missing, f"manifest lacks frozen diagnostic ranks: {missing}")
    return [by_rank[rank] for rank in FROZEN_RANKS]


def select_candidates(config: Config, selector: str) -> list[Candidate]:
    available = candidates(config)
    if selector == "all":
        return available
    matches = [
        candidate
        for candidate in available
        if str(candidate.rank) == selector or candidate.submission_id.startswith(selector)
    ]
    require(len(matches) == 1, f"selector must match exactly one frozen arm: {selector}")
    return matches


def validate_workspace_owner(config: Config) -> None:
    require(not config.workspace.is_symlink(), f"workspace may not be a symlink: {config.workspace}")
    require((config.workspace / ".git").is_dir(), f"workspace is not a Git checkout: {config.workspace}")
    owner_path = config.workspace / ".mlxfast-top15-study-owner.json"
    owner = load_json(owner_path)
    expected = {
        "study": config.study,
        "source_repo": str(config.repo),
        "workspace": str(config.workspace),
    }
    require(owner == expected, f"workspace ownership sentinel does not match: {owner_path}")
    origin = run_checked(
        ["git", "-C", str(config.workspace), "remote", "get-url", "origin"]
    ).stdout.strip()
    require(Path(origin).expanduser().resolve() == config.repo, "workspace origin does not match source repository")


def evaluator_environment(config: Config, project: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "LAGUNA_QUALITY_BOOTSTRAPPED": "1",
            "PYTHONPATH": str(project),
            "UV_CACHE_DIR": str(config.uv_cache),
        }
    )
    return environment


def evaluator_provenance(config: Config, project: Path) -> dict[str, Any]:
    program = (
        "import json; from laguna_quality.runner import _evaluation_provenance; "
        "print(json.dumps(_evaluation_provenance(), sort_keys=True))"
    )
    output = run_checked(
        [sys.executable, "-c", program],
        env=evaluator_environment(config, project),
    ).stdout
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise DiagnosticError("pinned evaluator emitted invalid provenance JSON") from error
    require(value.get("sha256") == config.evaluator_sha256, "pinned evaluator SHA does not match manifest")
    return value


def validate_common_inputs(config: Config, *, evaluator_project: Path | None = None) -> dict[str, Any]:
    for executable in ("git", "uv"):
        require(shutil.which(executable) is not None, f"{executable} is required")
    require(config.study, "manifest study is empty")
    require(config.manifest_data.get("required_environment", {}).get("DARKBLOOM_EXPERT_ALIGNED_GATHER") == "0", "manifest must freeze DARKBLOOM_EXPERT_ALIGNED_GATHER=0")
    require_git_sha(config.harness_commit, "harness commit")
    require_git_sha(config.evaluator_commit, "evaluator commit")
    require_sha(config.evaluator_sha256, "evaluator provenance")
    require(load_json(config.ids) == [FROZEN_ID], f"frozen IDs file must contain only {FROZEN_ID}")
    require(config.wrapper.is_file() and os.access(config.wrapper, os.X_OK), f"quality wrapper is not executable: {config.wrapper}")
    for path in (
        config.weights / "config.json",
        config.weights / "model.safetensors.index.json",
        config.weights / ".benchmark-source.sha256",
        config.reference / "config.json",
        config.reference / "tokenizer.json",
    ):
        require(path.is_file(), f"required shared artifact is missing: {path}")
    for commit in (config.harness_commit, config.evaluator_commit):
        run_checked(["git", "-C", str(config.repo), "cat-file", "-e", f"{commit}^{{commit}}"])
    for candidate in candidates(config):
        require_git_sha(candidate.source_ref, f"rank {candidate.rank} source_ref")
        run_checked(["git", "-C", str(config.repo), "cat-file", "-e", f"{candidate.source_ref}^{{commit}}"])
    validate_workspace_owner(config)
    project = evaluator_project or config.workspace / "senpai/quality_eval"
    require(project.is_dir(), f"pinned evaluator project is missing: {project}")
    return evaluator_provenance(config, project)


def current_host_identity() -> dict[str, Any]:
    output = run_checked(["system_profiler", "SPHardwareDataType", "-json"]).stdout
    try:
        rows = json.loads(output).get("SPHardwareDataType", [])
    except (AttributeError, json.JSONDecodeError) as error:
        raise DiagnosticError("system_profiler emitted invalid hardware JSON") from error
    require(isinstance(rows, list) and len(rows) == 1, "system_profiler returned an unexpected hardware record")
    row = rows[0]
    return {
        "model": row.get("machine_model"),
        "chip": row.get("chip_type"),
        "memory": row.get("physical_memory"),
        "macos_version": run_checked(["sw_vers", "-productVersion"]).stdout.strip(),
    }


def validate_current_host(config: Config) -> dict[str, Any]:
    actual = current_host_identity()
    expected = config.manifest_data.get("host", {})
    require(actual.get("model") == expected.get("model"), "diagnostic host model differs from frozen study host")
    require(actual.get("chip") == expected.get("chip"), "diagnostic host chip differs from frozen study host")
    expected_memory = expected.get("memory_gb")
    require(actual.get("memory") == f"{expected_memory} GB", "diagnostic host memory differs from frozen study host")
    return actual


def validate_hashed_artifact(arm_dir: Path, descriptor: Any, label: str) -> Path:
    require(isinstance(descriptor, dict), f"{label} descriptor is missing")
    path = checked_path(arm_dir, descriptor.get("path"), label)
    require(path.is_file(), f"{label} is missing: {path}")
    expected = require_sha(descriptor.get("sha256"), f"{label} hash")
    require(sha256_file(path) == expected, f"{label} hash mismatch: {path}")
    return path


def validate_primary_evidence(config: Config, candidate: Candidate) -> PrimaryEvidence:
    arm_dir = config.primary_results / "quality" / candidate.name
    marker_path = arm_dir / "terminal-noncompletion.json"
    require(marker_path.is_file(), f"primary bounded-noncompletion marker is missing: {marker_path}")
    require(not (arm_dir / "selected-attempt.txt").exists(), f"primary arm unexpectedly has a selected attempt: {arm_dir}")
    marker = load_json(marker_path)
    require(isinstance(marker, dict), f"primary marker is not an object: {marker_path}")
    require(marker.get("schema") == "mlxfast-top15-quality-terminal-v1", "primary marker schema mismatch")
    require(marker.get("status") == "bounded_noncompletion" and marker.get("reason") == "aime_length", "primary arm is not the required bounded AIME non-completion")
    expected_arm = {
        "rank": candidate.rank,
        "submission_id": candidate.submission_id,
        "source_ref": candidate.source_ref,
    }
    require(marker.get("arm") == expected_arm, "primary marker arm identity mismatch")
    require(marker.get("harness_ref") == config.harness_commit, "primary marker harness mismatch")
    require(marker.get("manifest_sha256") == config.manifest_sha256, "primary marker manifest hash mismatch")
    require(marker.get("evaluator_sha256") == config.evaluator_sha256, "primary marker evaluator hash mismatch")
    wrapper_sha = sha256_file(config.wrapper)
    require(marker.get("wrapper_sha256") == wrapper_sha, "primary marker wrapper hash mismatch")
    truncated = marker.get("truncated_items")
    require(isinstance(truncated, list) and len(truncated) == 1, "primary marker must identify exactly one truncated item")
    require(truncated[0].get("id") == FROZEN_ID and truncated[0].get("finish_reasons") == ["length"], f"primary marker is not bounded by frozen ID {FROZEN_ID}")

    artifacts = marker.get("artifacts")
    require(isinstance(artifacts, dict), "primary marker lacks artifacts")
    run_spec_path = validate_hashed_artifact(arm_dir, artifacts.get("run_spec"), "primary run spec")
    run_path = validate_hashed_artifact(arm_dir, artifacts.get("run"), "primary run")
    validate_hashed_artifact(arm_dir, artifacts.get("meta"), "primary meta")
    validate_hashed_artifact(arm_dir, artifacts.get("log"), "primary log")
    validate_hashed_artifact(arm_dir, artifacts.get("responses"), "primary response journal")
    raw = artifacts.get("raw")
    require(isinstance(raw, dict), "primary marker lacks raw artifacts")
    for key, descriptor in raw.items():
        validate_hashed_artifact(arm_dir, descriptor, f"primary raw {key}")
    aime_path = validate_hashed_artifact(arm_dir, raw.get("aime"), "primary raw AIME")

    bridge_descriptor = artifacts.get("real_bridge")
    bridge_path = validate_hashed_artifact(arm_dir, bridge_descriptor, "primary real bridge")
    require(os.access(bridge_path, os.X_OK), "primary real bridge is not executable")
    sidecar = bridge_path.with_name(bridge_path.name + ".source.sha256")
    require(sidecar.is_file(), "primary real bridge source sidecar is missing")
    require(sha256_file(sidecar) == require_sha(bridge_descriptor.get("source_sidecar_sha256"), "primary bridge sidecar hash"), "primary real bridge sidecar hash mismatch")
    bridge_source = sidecar.read_text().strip()
    require(bridge_source == require_sha(bridge_descriptor.get("source_sha256"), "primary bridge source hash"), "primary bridge source fingerprint mismatch")

    run_spec = load_json(run_spec_path)
    require(run_spec.get("study") == config.study and run_spec.get("phase") == "quality", "primary run spec identity mismatch")
    spec_arm = run_spec.get("arm", {})
    require(str(spec_arm.get("rank")) == str(candidate.rank), "primary run spec rank mismatch")
    require(spec_arm.get("submission_id") == candidate.submission_id and spec_arm.get("source_ref") == candidate.source_ref, "primary run spec source identity mismatch")
    require(run_spec.get("harness_ref") == config.harness_commit, "primary run spec harness mismatch")
    require(run_spec.get("manifest_sha256") == config.manifest_sha256, "primary run spec manifest mismatch")
    require(run_spec.get("quality", {}).get("evaluator_sha256") == config.evaluator_sha256, "primary run spec evaluator mismatch")
    require(run_spec.get("quality", {}).get("launcher_wrapper_sha256") == wrapper_sha, "primary run spec wrapper mismatch")

    run = load_json(run_path)
    require(run.get("status") == "failed" and run.get("evaluation_valid") is False, "primary evaluator run is not the expected non-completion")
    require(run.get("profile") == "quick" and run.get("passes") == 1, "primary evaluator profile mismatch")
    require(run.get("evaluator_provenance", {}).get("sha256") == config.evaluator_sha256, "primary run evaluator provenance mismatch")
    primary_host = run.get("host_identity", {})
    require(primary_host.get("hardware_model") == config.manifest_data.get("host", {}).get("model"), "primary run host model mismatch")
    require(primary_host.get("cpu_brand") == config.manifest_data.get("host", {}).get("chip"), "primary run host chip mismatch")
    checkout = run.get("artifact_identity", {}).get("checkout", {})
    require(checkout.get("git_head") == config.harness_commit, "primary run checkout harness mismatch")
    editable_source = require_sha(checkout.get("editable_source_sha256"), "primary editable-source hash")
    run_files = run.get("artifact_identity", {}).get("files", {})
    metallib_sha = require_sha(run_files.get("metallib", {}).get("sha256"), "primary metallib hash")
    require(run_files.get("bridge", {}).get("sha256") == wrapper_sha, "primary run wrapper artifact mismatch")

    aime = load_json(aime_path)
    require(aime.get("n_problems") == 9 and aime.get("total_samples") == 9, "primary AIME panel shape mismatch")
    require(aime.get("k") == 1 and aime.get("maj_k") == 1 and aime.get("client_concurrency") == 1, "primary AIME sampling shape mismatch")
    require(aime.get("years") == ["2024", "2025-I", "2025-II"], "primary AIME years mismatch")
    sampling = aime.get("sampling", {})
    require(
        sampling == {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": -1,
            "max_tokens": ORIGINAL_MAX_TOKENS,
            "min_tokens": 0,
            "seed": 1234,
            "enable_thinking": False,
        },
        "primary AIME sampling contract mismatch",
    )
    matches = [row for row in aime.get("per_problem", []) if row.get("id") == FROZEN_ID]
    require(len(matches) == 1, f"primary AIME result does not contain exactly one {FROZEN_ID}")
    row = matches[0]
    require(row.get("finish_reasons") == ["length"] and row.get("k") == 1, "primary frozen AIME item is not length-bounded")
    require(len(row.get("sample_chars", [])) == 1 and len(row.get("answers", [])) == 1, "primary frozen AIME item shape mismatch")
    require_sha(row.get("prompt_sha"), "primary frozen prompt hash")
    require(isinstance(row.get("gold"), int), "primary frozen AIME gold is missing")

    return PrimaryEvidence(
        candidate=candidate,
        arm_dir=arm_dir,
        marker_path=marker_path,
        marker_sha256=sha256_file(marker_path),
        marker=marker,
        run_spec_path=run_spec_path,
        run_spec_sha256=sha256_file(run_spec_path),
        run_path=run_path,
        run_sha256=sha256_file(run_path),
        aime_path=aime_path,
        aime_sha256=sha256_file(aime_path),
        prompt_sha256=row["prompt_sha"],
        gold=row["gold"],
        original_answer=row["answers"][0],
        original_sample_chars=row["sample_chars"][0],
        bridge_sha256=sha256_file(bridge_path),
        bridge_source_sha256=bridge_source,
        metallib_sha256=metallib_sha,
        editable_source_sha256=editable_source,
    )


def safe_extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:") as bundle:
        for member in bundle.getmembers():
            member_path = Path(member.name)
            require(
                not member_path.is_absolute() and ".." not in member_path.parts,
                f"unsafe path in pinned evaluator archive: {member.name}",
            )
        bundle.extractall(destination, filter="data")


def export_evaluator(config: Config, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(prefix="top15-evaluator-", suffix=".tar", delete=False) as handle:
        archive = Path(handle.name)
    try:
        run_checked(
            [
                "git",
                "-C",
                str(config.repo),
                "archive",
                "--format=tar",
                f"--output={archive}",
                config.evaluator_commit,
                "--",
                "senpai/quality-eval",
                "senpai/quality_eval",
            ]
        )
        safe_extract_archive(archive, destination)
        (destination / "senpai/quality-eval").chmod(0o755)
    finally:
        archive.unlink(missing_ok=True)


def ensure_evaluator_bundle(config: Config) -> dict[str, Any]:
    root = config.evaluator_root
    identity_path = config.results / "_pinned-evaluator.json"
    if root.exists():
        require(root.is_dir() and not root.is_symlink(), f"invalid pinned evaluator bundle: {root}")
        provenance = evaluator_provenance(config, config.evaluator_project)
        expected_identity = {
            "schema": f"{SCHEMA}-evaluator",
            "commit": config.evaluator_commit,
            "provenance": provenance,
        }
        if not identity_path.exists():
            write_json_once(identity_path, expected_identity)
        identity = load_json(identity_path)
        require(identity.get("schema") == f"{SCHEMA}-evaluator", "pinned evaluator identity schema mismatch")
        require(identity.get("commit") == config.evaluator_commit, "pinned evaluator commit mismatch")
        require(identity.get("provenance") == provenance, "pinned evaluator identity mismatch")
        return provenance

    config.results.mkdir(parents=True, exist_ok=True)
    stage = config.results / f"._pinned-evaluator.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    require(not stage.exists(), f"evaluator staging path already exists: {stage}")
    stage.mkdir()
    try:
        export_evaluator(config, stage)
        provenance = evaluator_provenance(config, stage / "senpai/quality_eval")
        os.rename(stage, root)
    except BaseException:
        # The staging tree is deliberate failure evidence.  It is never reused.
        raise
    identity = {
        "schema": f"{SCHEMA}-evaluator",
        "commit": config.evaluator_commit,
        "provenance": provenance,
    }
    write_json_once(identity_path, identity)
    return provenance


@contextlib.contextmanager
def workspace_lock(config: Config) -> Iterator[None]:
    lock_path = config.workspace / ".mlxfast-top15-extended-aime.lock"
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DiagnosticError(f"another extended-AIME runner owns {lock_path}") from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started_at={utc_now()}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def process_ancestors() -> set[int]:
    ancestors = {os.getpid()}
    current = os.getppid()
    while current > 1 and current not in ancestors:
        ancestors.add(current)
        try:
            output = run_checked(["ps", "-o", "ppid=", "-p", str(current)]).stdout.strip()
            current = int(output)
        except (DiagnosticError, ValueError):
            break
    return ancestors


def require_workspace_idle(config: Config) -> None:
    output = run_checked(["ps", "-axo", "pid=,command="]).stdout
    ignored = process_ancestors()
    conflicts: list[str] = []
    workspace_text = str(config.workspace)
    study_runner = str(config.study_dir / "run-study.sh")
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        command = fields[1]
        if pid in ignored:
            continue
        if study_runner in command or "run-study.sh" in command or (
            workspace_text in command
            and any(token in command for token in ("quality-eval", "benchmark.sh", "swift build"))
        ):
            conflicts.append(f"pid {pid}: {command}")
    require(
        not conflicts,
        "owned workspace is active in another study process:\n  " + "\n  ".join(conflicts),
    )


def log_message(handle: Any, message: str) -> None:
    handle.write((message.rstrip() + "\n").encode())
    handle.flush()


def run_logged(
    command: Sequence[str],
    *,
    log: Any,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> int:
    log_message(log, f"$ {' '.join(command)}")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as error:
        log_message(log, f"launch failed: {error}")
        return 127
    try:
        return process.wait()
    except BaseException:
        terminate_process(process)
        raise


def terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def editable_paths(config: Config) -> list[str]:
    benchmark = load_json(config.workspace / "benchmark.json")
    paths = benchmark.get("editablePaths") if isinstance(benchmark, dict) else None
    require(
        isinstance(paths, list) and paths and all(isinstance(path, str) and path for path in paths),
        "workspace benchmark editablePaths are invalid",
    )
    return paths


def apply_snapshot(config: Config, evidence: PrimaryEvidence, log: Any) -> None:
    candidate = evidence.candidate
    require_workspace_idle(config)
    validate_workspace_owner(config)
    commands: list[list[str]] = [
        ["git", "-C", str(config.workspace), "reset", "--hard", config.harness_commit],
    ]
    for command in commands:
        require(run_logged(command, log=log, cwd=config.repo) == 0, "failed to reset owned workspace")
    paths = editable_paths(config)
    require(
        run_logged(
            ["git", "-C", str(config.workspace), "clean", "-fd", "--", *paths],
            log=log,
            cwd=config.repo,
        )
        == 0,
        "failed to clean participant-editable paths",
    )
    require(
        run_logged(
            [
                "git",
                "-C",
                str(config.workspace),
                "restore",
                f"--source={candidate.source_ref}",
                "--staged",
                "--worktree",
                "--",
                *paths,
            ],
            log=log,
            cwd=config.repo,
        )
        == 0,
        f"failed to restore rank {candidate.rank} editable snapshot",
    )
    require(
        run_logged(
            ["git", "-C", str(config.workspace), "diff", "--quiet", candidate.source_ref, "--", *paths],
            log=log,
            cwd=config.repo,
        )
        == 0,
        f"rank {candidate.rank} editable snapshot verification failed",
    )
    untracked = run_checked(
        ["git", "-C", str(config.workspace), "ls-files", "--others", "--exclude-standard", "--", *paths]
    ).stdout.strip()
    require(not untracked, f"untracked files remain in rank {candidate.rank} editable snapshot")

    log_message(log, f"install pinned evaluator commit {config.evaluator_commit}")
    export_evaluator(config, config.workspace)
    provenance = evaluator_provenance(config, config.workspace / "senpai/quality_eval")
    require(provenance.get("sha256") == config.evaluator_sha256, "workspace evaluator install mismatch")


def next_number(directory: Path, prefix: str) -> int:
    highest = 0
    if directory.is_dir():
        for child in directory.iterdir():
            if not child.is_dir() or not child.name.startswith(prefix):
                continue
            suffix = child.name[len(prefix) :]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return highest + 1


def find_built_bridge(config: Config) -> Path:
    options = (
        config.workspace / ".build-quality/release/laguna-quality-bridge",
        config.workspace / ".build-quality/arm64-apple-macosx/release/laguna-quality-bridge",
    )
    for path in options:
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    raise DiagnosticError("quality bridge build did not publish an executable")


def find_built_metallib(config: Config) -> Path:
    options = (
        config.workspace / ".build-worker/release/mlx.metallib",
        config.workspace / ".build-worker/arm64-apple-macosx/release/mlx.metallib",
    )
    for path in options:
        if path.is_file():
            return path.resolve()
    raise DiagnosticError("metallib build did not publish mlx.metallib")


def copied_file(stage: Path, name: str, source: Path, *, executable: bool = False) -> Path:
    target = stage / name
    with source.open("rb") as input_handle, target.open("xb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle, length=4 * 1024 * 1024)
    shutil.copystat(source, target)
    if executable:
        target.chmod(target.stat().st_mode | 0o111)
    return target


def artifact_identity(artifact_dir: Path) -> dict[str, Any]:
    names = (
        "builder.json",
        "candidate-bridge",
        "candidate-bridge.source.sha256",
        "mlx.metallib",
        "mlx.metallib.fingerprint",
        "quality-bridge-wrapper.sh",
        "ids.json",
        "quality-artifact.json",
    )
    files: dict[str, Any] = {}
    for name in names:
        path = artifact_dir / name
        require(path.is_file(), f"preserved artifact is missing: {path}")
        files[name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    builder = load_json(artifact_dir / "builder.json")
    require(builder.get("schema") == f"{SCHEMA}-artifact-builder", "artifact builder provenance mismatch")
    require_sha(builder.get("runner", {}).get("sha256"), "artifact builder runner hash")
    return {"schema": f"{SCHEMA}-artifact", "builder": builder, "files": files}


def shared_artifact_identity(config: Config) -> dict[str, Any]:
    weight_files = {
        "config.json": sha256_file(config.weights / "config.json"),
        "model.safetensors.index.json": sha256_file(
            config.weights / "model.safetensors.index.json"
        ),
        ".benchmark-source.sha256": sha256_file(
            config.weights / ".benchmark-source.sha256"
        ),
    }
    tokenizer_files: dict[str, str] = {}
    for name in (
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
    ):
        path = config.reference / name
        if path.is_file():
            tokenizer_files[name] = sha256_file(path)
    return {
        "weights": {"path": str(config.weights), "files": weight_files},
        "tokenizer": {"path": str(config.reference), "files": tokenizer_files},
    }


def expected_run_spec(
    config: Config,
    evidence: PrimaryEvidence,
    identity: dict[str, Any],
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    aime_script_hash = require_sha(
        evaluator.get("files", {}).get("upstream/aime_eval.py"),
        "pinned AIME evaluator hash",
    )
    return {
        "schema": f"{SCHEMA}-run-spec",
        "study": config.study,
        "phase": "diagnostic_extended_aime",
        "arm": dataclasses.asdict(evidence.candidate),
        "harness_ref": config.harness_commit,
        "manifest_sha256": config.manifest_sha256,
        "runner": identity["builder"]["runner"],
        "evaluator": {
            "commit": config.evaluator_commit,
            "sha256": config.evaluator_sha256,
            "aime_eval_sha256": aime_script_hash,
        },
        "primary_evidence": {
            "terminal_marker": {
                "path": str(evidence.marker_path),
                "sha256": evidence.marker_sha256,
            },
            "run_spec": {
                "path": str(evidence.run_spec_path),
                "sha256": evidence.run_spec_sha256,
            },
            "run": {"path": str(evidence.run_path), "sha256": evidence.run_sha256},
            "aime": {"path": str(evidence.aime_path), "sha256": evidence.aime_sha256},
            "frozen_item": {
                "id": FROZEN_ID,
                "prompt_sha256": evidence.prompt_sha256,
                "gold": evidence.gold,
                "finish_reason": "length",
                "max_tokens": ORIGINAL_MAX_TOKENS,
                "answer": evidence.original_answer,
                "sample_chars": evidence.original_sample_chars,
            },
            "real_bridge": {
                "sha256": evidence.bridge_sha256,
                "source_sha256": evidence.bridge_source_sha256,
            },
            "metallib_sha256": evidence.metallib_sha256,
            "editable_source_sha256": evidence.editable_source_sha256,
        },
        "diagnostic_contract": {
            "diagnostic_only": True,
            "formally_comparable": False,
            "modifies_primary_quality_result": False,
            "retroactively_validates_primary_quick_result": False,
            "suite": "aime",
            "ids": [FROZEN_ID],
            "ids_sha256": identity["files"]["ids.json"]["sha256"],
            "model": MODEL_NAME,
            "years": ["2024", "2025-I", "2025-II"],
            "k": 1,
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": -1,
            "max_tokens": MAX_TOKENS,
            "min_tokens": 0,
            "enable_thinking": False,
            "seed": 1234,
            "client_concurrency": 1,
            "request_timeout_s": REQUEST_TIMEOUT_S,
            "save_text": True,
            "expect_count": 1,
            "head_mode": "full",
        },
        "environment": {"DARKBLOOM_EXPERT_ALIGNED_GATHER": "0"},
        "host_contract": config.manifest_data.get("host"),
        "artifacts": identity,
        "shared_artifacts": shared_artifact_identity(config),
    }


def validate_shared_artifacts(config: Config, spec: dict[str, Any]) -> None:
    require(
        spec.get("shared_artifacts") == shared_artifact_identity(config),
        "shared weights/tokenizer identity changed since the diagnostic was frozen",
    )


def validate_artifact_bundle(
    config: Config,
    evidence: PrimaryEvidence,
    evaluator: dict[str, Any],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    arm_dir = config.results / evidence.candidate.name
    artifact_dir = arm_dir / "artifacts"
    spec_path = arm_dir / "run-spec.json"
    require(artifact_dir.is_dir() and not artifact_dir.is_symlink(), f"preserved artifact bundle is missing: {artifact_dir}")
    require(spec_path.is_file(), f"diagnostic run spec is missing: {spec_path}")
    identity_path = artifact_dir / "identity.json"
    require(identity_path.is_file(), f"artifact identity is missing: {identity_path}")
    identity = load_json(identity_path)
    require(identity == artifact_identity(artifact_dir), "preserved artifact identity mismatch")
    spec = load_json(spec_path)
    expected_spec = expected_run_spec(config, evidence, identity, evaluator)
    require(spec == expected_spec, "diagnostic run spec differs from its frozen contract")
    require(spec.get("schema") == f"{SCHEMA}-run-spec", "diagnostic run-spec schema mismatch")
    require(spec.get("study") == config.study and spec.get("phase") == "diagnostic_extended_aime", "diagnostic run-spec identity mismatch")
    require(spec.get("arm") == dataclasses.asdict(evidence.candidate), "diagnostic run-spec arm mismatch")
    require(spec.get("harness_ref") == config.harness_commit, "diagnostic run-spec harness mismatch")
    require(spec.get("manifest_sha256") == config.manifest_sha256, "diagnostic run-spec manifest mismatch")
    require(spec.get("evaluator", {}).get("commit") == config.evaluator_commit, "diagnostic evaluator commit mismatch")
    require(spec.get("evaluator", {}).get("sha256") == config.evaluator_sha256, "diagnostic evaluator hash mismatch")
    require(spec.get("evaluator", {}).get("aime_eval_sha256") == evaluator.get("files", {}).get("upstream/aime_eval.py"), "diagnostic AIME evaluator hash mismatch")
    primary = spec.get("primary_evidence", {})
    require(primary.get("terminal_marker", {}).get("sha256") == evidence.marker_sha256, "diagnostic primary marker binding mismatch")
    require(primary.get("run_spec", {}).get("sha256") == evidence.run_spec_sha256, "diagnostic primary run-spec binding mismatch")
    require(primary.get("run", {}).get("sha256") == evidence.run_sha256, "diagnostic primary run binding mismatch")
    require(primary.get("aime", {}).get("sha256") == evidence.aime_sha256, "diagnostic primary AIME binding mismatch")
    require(primary.get("frozen_item", {}).get("prompt_sha256") == evidence.prompt_sha256, "diagnostic prompt binding mismatch")
    require(primary.get("real_bridge", {}).get("source_sha256") == evidence.bridge_source_sha256, "diagnostic bridge-source binding mismatch")
    require(primary.get("metallib_sha256") == evidence.metallib_sha256, "diagnostic metallib binding mismatch")
    contract = spec.get("diagnostic_contract", {})
    require(
        contract.get("diagnostic_only") is True
        and contract.get("formally_comparable") is False
        and contract.get("modifies_primary_quality_result") is False
        and contract.get("retroactively_validates_primary_quick_result") is False,
        "diagnostic-only interpretation was changed",
    )
    expected_contract = expected_run_spec(config, evidence, identity, evaluator)["diagnostic_contract"]
    require(contract == expected_contract, "extended-AIME command contract mismatch")
    require(spec.get("artifacts") == identity, "diagnostic artifact hashes do not match run spec")
    validate_shared_artifacts(config, spec)
    require((artifact_dir / "candidate-bridge.source.sha256").read_text().strip() == evidence.bridge_source_sha256, "preserved bridge source fingerprint mismatch")
    require(os.access(artifact_dir / "candidate-bridge", os.X_OK), "preserved candidate bridge is not executable")
    require(os.access(artifact_dir / "quality-bridge-wrapper.sh", os.X_OK), "preserved quality wrapper is not executable")
    require(identity["files"]["mlx.metallib"]["sha256"] == evidence.metallib_sha256, "preserved metallib does not match primary run")
    require(identity["files"]["quality-bridge-wrapper.sh"]["sha256"] == sha256_file(config.wrapper), "preserved wrapper mismatch")
    require(load_json(artifact_dir / "ids.json") == [FROZEN_ID], "preserved IDs changed")
    artifact_manifest = load_json(artifact_dir / "quality-artifact.json")
    require(
        artifact_manifest
        == {
            "weights": str(config.weights),
            "tokenizer": str(config.reference),
            "bridge": "quality-bridge-wrapper.sh",
            "metallib": "mlx.metallib",
        },
        "quality artifact manifest mismatch",
    )
    return artifact_dir, spec, identity


def build_and_preserve_artifact(
    config: Config,
    evidence: PrimaryEvidence,
    evaluator: dict[str, Any],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    arm_dir = config.results / evidence.candidate.name
    arm_dir.mkdir(parents=True, exist_ok=True)
    if (arm_dir / "artifacts").exists():
        artifact_dir = arm_dir / "artifacts"
        identity_path = artifact_dir / "identity.json"
        require(identity_path.is_file(), f"partial preserved artifact lacks identity: {artifact_dir}")
        identity = load_json(identity_path)
        require(identity == artifact_identity(artifact_dir), "partial preserved artifact identity mismatch")
        if not (arm_dir / "run-spec.json").exists():
            write_json_once(
                arm_dir / "run-spec.json",
                expected_run_spec(config, evidence, identity, evaluator),
            )
        return validate_artifact_bundle(config, evidence, evaluator)
    require(not (arm_dir / "run-spec.json").exists(), "run spec exists without its preserved artifact bundle")

    attempt_number = next_number(arm_dir, "build-attempt-")
    build_dir = arm_dir / f"build-attempt-{attempt_number}"
    build_dir.mkdir()
    started = {
        "schema": f"{SCHEMA}-build-started",
        "started_at": utc_now(),
        "arm": dataclasses.asdict(evidence.candidate),
        "source_ref": evidence.candidate.source_ref,
        "harness_ref": config.harness_commit,
        "workspace": str(config.workspace),
        "runner": {"path": str(config.script), "sha256": sha256_file(config.script)},
    }
    write_json_once(build_dir / "started.json", started)
    status = 1
    error_message: str | None = None
    bridge: Path | None = None
    metallib: Path | None = None
    build_log = build_dir / "build.log"
    try:
        with build_log.open("xb") as log:
            apply_snapshot(config, evidence, log)
            require_workspace_idle(config)
            helper = (
                "from laguna_quality.artifact import build_bridge, ensure_metallib; "
                "build_bridge('.'); ensure_metallib('.', build=True)"
            )
            command = [
                "uv",
                "run",
                "--project",
                str(config.evaluator_project),
                "--locked",
                "python",
                "-c",
                helper,
            ]
            status = run_logged(
                command,
                log=log,
                cwd=config.workspace,
                env=evaluator_environment(config, config.evaluator_project),
            )
            require(status == 0, "candidate bridge/metallib build failed")
            bridge = find_built_bridge(config)
            metallib = find_built_metallib(config)
            sidecar = bridge.with_name(bridge.name + ".source.sha256")
            fingerprint = metallib.with_suffix(metallib.suffix + ".fingerprint")
            require(sidecar.is_file(), "built bridge source sidecar is missing")
            require(fingerprint.is_file(), "built metallib fingerprint is missing")
            require(sidecar.read_text().strip() == evidence.bridge_source_sha256, "rebuilt bridge source fingerprint differs from primary evidence")
            require(sha256_file(metallib) == evidence.metallib_sha256, "rebuilt metallib differs from the primary evaluator artifact")

            stage = arm_dir / f".artifacts.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            stage.mkdir()
            copied_file(stage, "candidate-bridge", bridge, executable=True)
            copied_file(stage, "candidate-bridge.source.sha256", sidecar)
            copied_file(stage, "mlx.metallib", metallib)
            copied_file(stage, "mlx.metallib.fingerprint", fingerprint)
            copied_file(stage, "quality-bridge-wrapper.sh", config.wrapper, executable=True)
            copied_file(stage, "ids.json", config.ids)
            write_json_once(
                stage / "builder.json",
                {
                    "schema": f"{SCHEMA}-artifact-builder",
                    "build_attempt": build_dir.name,
                    "runner": started["runner"],
                },
            )
            write_json_once(
                stage / "quality-artifact.json",
                {
                    "weights": str(config.weights),
                    "tokenizer": str(config.reference),
                    "bridge": "quality-bridge-wrapper.sh",
                    "metallib": "mlx.metallib",
                },
            )
            identity = artifact_identity(stage)
            write_json_once(stage / "identity.json", identity)
            os.rename(stage, arm_dir / "artifacts")
            spec = expected_run_spec(config, evidence, identity, evaluator)
            write_json_once(arm_dir / "run-spec.json", spec)
            status = 0
    except BaseException as error:
        error_message = f"{type(error).__name__}: {error}"
        if isinstance(error, KeyboardInterrupt):
            status = 130
        elif status == 0:
            status = 1
        raise
    finally:
        finished = {
            "schema": f"{SCHEMA}-build-finished",
            "finished_at": utc_now(),
            "exit_code": status,
            "error": error_message,
            "log_sha256": sha256_file(build_log) if build_log.is_file() else None,
            "bridge_path": str(bridge) if bridge else None,
            "metallib_path": str(metallib) if metallib else None,
        }
        write_json_once(build_dir / "finished.json", finished)
    return validate_artifact_bundle(config, evidence, evaluator)


def read_json_lines(path: Path) -> list[Any]:
    try:
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]
    except (OSError, json.JSONDecodeError) as error:
        raise DiagnosticError(f"cannot read JSONL {path}: {error}") from error


def validate_diagnostic_result(result_path: Path, evidence: PrimaryEvidence) -> dict[str, Any]:
    result = load_json(result_path)
    require(isinstance(result, dict), "extended AIME result is not an object")
    require(result.get("label") == f"top15-extended-aime-{evidence.candidate.name}", "extended AIME label mismatch")
    require(result.get("model") == MODEL_NAME, "extended AIME model mismatch")
    require(result.get("years") == ["2024", "2025-I", "2025-II"], "extended AIME years mismatch")
    require(result.get("k") == 1 and result.get("maj_k") == 1, "extended AIME k mismatch")
    require(result.get("client_concurrency") == 1, "extended AIME concurrency mismatch")
    require(result.get("n_problems") == 1 and result.get("total_samples") == 1, "extended AIME result shape mismatch")
    require(
        result.get("sampling")
        == {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": -1,
            "max_tokens": MAX_TOKENS,
            "min_tokens": 0,
            "seed": 1234,
            "enable_thinking": False,
        },
        "extended AIME sampling contract mismatch",
    )
    rows = result.get("per_problem")
    require(isinstance(rows, list) and len(rows) == 1, "extended AIME must contain one problem")
    row = rows[0]
    require(row.get("id") == FROZEN_ID and row.get("year") == "2024", "extended AIME frozen ID mismatch")
    require(row.get("prompt_sha") == evidence.prompt_sha256, "extended AIME prompt differs from primary evidence")
    require(row.get("gold") == evidence.gold, "extended AIME gold differs from primary evidence")
    require(row.get("k") == 1, "extended AIME per-problem k mismatch")
    require(len(row.get("answers", [])) == 1, "extended AIME answer shape mismatch")
    require(len(row.get("sample_chars", [])) == 1, "extended AIME sample shape mismatch")
    require(len(row.get("texts", [])) == 1, "extended AIME text was not retained")
    finish_reasons = row.get("finish_reasons")
    require(finish_reasons in (["stop"], ["length"]), "extended AIME finish reason is invalid")
    return result


def validate_request_journal(path: Path, result: dict[str, Any]) -> None:
    records = read_json_lines(path)
    require(len(records) == 1, "extended AIME request journal must contain exactly one request")
    record = records[0]
    request = record.get("request", {})
    require(record.get("endpoint") == "/v1/chat/completions" and record.get("status") == 200, "extended AIME HTTP request failed")
    require(request.get("model") == MODEL_NAME, "extended AIME request model mismatch")
    require(request.get("n") == 1, "extended AIME request n mismatch")
    require(request.get("temperature") == 0.0 and request.get("top_p") == 1.0, "extended AIME request sampling mismatch")
    require(request.get("top_k") == -1 and request.get("seed") == 1234, "extended AIME request seed/top-k mismatch")
    require(request.get("max_tokens") == MAX_TOKENS and request.get("min_tokens") == 0, "extended AIME request token budget mismatch")
    messages = request.get("messages")
    require(isinstance(messages, list), "extended AIME request messages are missing")
    prompt_payload = json.dumps(
        {"messages": messages, "gold": result["per_problem"][0]["gold"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    journal_prompt_sha = hashlib.sha256(prompt_payload.encode()).hexdigest()
    require(
        journal_prompt_sha == result["per_problem"][0]["prompt_sha"],
        "extended AIME request prompt differs from the scored prompt",
    )
    journal_finish = [choice.get("finish_reason") for choice in record.get("response", {}).get("choices", [])]
    result_finish = result["per_problem"][0]["finish_reasons"]
    require(journal_finish == result_finish, "extended AIME journal/result finish reason mismatch")


def parse_ready(stdout_path: Path) -> dict[str, Any] | None:
    if not stdout_path.is_file():
        return None
    try:
        lines = stdout_path.read_text().splitlines()
    except OSError as error:
        raise DiagnosticError(f"cannot read quality server output {stdout_path}: {error}") from error
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # The serving process may still be flushing the current JSONL row.
            continue
        if isinstance(value, dict) and value.get("event") == "ready":
            return value
    return None


def wait_for_ready(process: subprocess.Popen[Any], stdout_path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        ready = parse_ready(stdout_path)
        if ready is not None:
            require(isinstance(ready.get("base_url"), str), "quality server ready event lacks base_url")
            return ready
        status = process.poll()
        if status is not None:
            raise DiagnosticError(f"quality server exited before readiness with status {status}")
        time.sleep(0.5)
    raise DiagnosticError(f"quality server did not become ready within {READY_TIMEOUT_S} seconds")


def attempt_hashes(attempt_dir: Path) -> dict[str, str]:
    names = (
        "started.json",
        "server.stdout.jsonl",
        "server.stderr.log",
        "invocation.json",
        "evaluator.log",
        "responses.jsonl",
        "aime-extended.json",
    )
    hashes: dict[str, str] = {}
    for name in names:
        path = attempt_dir / name
        if path.is_file():
            hashes[name] = sha256_file(path)
    return hashes


def validate_attempt(
    config: Config,
    evidence: PrimaryEvidence,
    attempt_dir: Path,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require(attempt_dir.is_dir(), f"diagnostic attempt is missing: {attempt_dir}")
    finished_path = attempt_dir / "finished.json"
    require(finished_path.is_file(), f"diagnostic attempt is unfinished: {attempt_dir}")
    finished = load_json(finished_path)
    require(finished.get("schema") == f"{SCHEMA}-attempt-finished", "diagnostic attempt schema mismatch")
    require(finished.get("exit_code") == 0, "diagnostic attempt did not exit cleanly")
    require(finished.get("server_shutdown_clean") is True, "diagnostic server shutdown was not clean")
    require(finished.get("server_exit_code") in (0, 130), "diagnostic server exit code is unexpected")
    require(finished.get("arm") == dataclasses.asdict(evidence.candidate), "diagnostic attempt arm mismatch")
    require(finished.get("run_spec_sha256") == sha256_file(config.results / evidence.candidate.name / "run-spec.json"), "diagnostic attempt run-spec binding mismatch")
    require(finished.get("hashes") == attempt_hashes(attempt_dir), "diagnostic attempt artifact hash mismatch")
    require(finished.get("shared_artifacts_after") == spec.get("shared_artifacts"), "shared artifact identity changed during diagnostic")

    started = load_json(attempt_dir / "started.json")
    require(started.get("schema") == f"{SCHEMA}-attempt-started", "diagnostic start record schema mismatch")
    require(started.get("arm") == dataclasses.asdict(evidence.candidate), "diagnostic start record arm mismatch")
    expected_host = spec.get("host_contract", {})
    started_host = started.get("host_identity", {})
    require(started_host.get("model") == expected_host.get("model"), "diagnostic attempt host model mismatch")
    require(started_host.get("chip") == expected_host.get("chip"), "diagnostic attempt host chip mismatch")
    require(started_host.get("memory") == f"{expected_host.get('memory_gb')} GB", "diagnostic attempt host memory mismatch")
    execution_runner = started.get("execution_runner", {})
    require(execution_runner.get("path") == str(config.script), "diagnostic execution runner path mismatch")
    require_sha(execution_runner.get("sha256"), "diagnostic execution runner hash")
    invocation = load_json(attempt_dir / "invocation.json")
    require(invocation.get("schema") == f"{SCHEMA}-invocation", "diagnostic invocation schema mismatch")
    require(invocation.get("contract") == spec.get("diagnostic_contract"), "diagnostic invocation contract mismatch")
    require(invocation.get("host_identity") == started_host, "diagnostic invocation host identity mismatch")
    require(invocation.get("execution_runner") == execution_runner, "diagnostic invocation runner mismatch")
    ready = invocation.get("server_ready", {})
    require(ready.get("event") == "ready" and ready.get("model") == MODEL_NAME, "diagnostic server readiness mismatch")
    artifact = ready.get("artifact", {})
    artifact_dir = config.results / evidence.candidate.name / "artifacts"
    require(Path(str(artifact.get("root"))).resolve() == artifact_dir.resolve(), "diagnostic server used the wrong artifact root")
    require(Path(str(artifact.get("bridge"))).resolve() == (artifact_dir / "quality-bridge-wrapper.sh").resolve(), "diagnostic server used the wrong wrapper")
    require(Path(str(artifact.get("metallib"))).resolve() == (artifact_dir / "mlx.metallib").resolve(), "diagnostic server used the wrong metallib")

    result = validate_diagnostic_result(attempt_dir / "aime-extended.json", evidence)
    validate_request_journal(attempt_dir / "responses.jsonl", result)
    return finished, result


def completion_marker(
    config: Config,
    evidence: PrimaryEvidence,
    attempt_dir: Path,
    finished: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    row = result["per_problem"][0]
    finish_reason = row["finish_reasons"][0]
    outcome = (
        "completed_before_extended_ceiling"
        if finish_reason == "stop"
        else "still_length_bounded_at_6144"
    )
    return {
        "schema": f"{SCHEMA}-completed",
        "status": "completed_diagnostic",
        "outcome": outcome,
        "study": config.study,
        "arm": dataclasses.asdict(evidence.candidate),
        "attempt": attempt_dir.name,
        "finished_at": finished["finished_at"],
        "interpretation": {
            "diagnostic_only": True,
            "formally_comparable": False,
            "local_retention_gate_evaluated": False,
            "primary_quick_result_changed": False,
            "detail": (
                "This isolated rerun changes only the frozen AIME response ceiling from "
                "2048 to 6144 tokens. It does not select, validate, or modify the primary "
                "quick-profile quality arm."
            ),
        },
        "frozen_item": {
            "id": FROZEN_ID,
            "prompt_sha256": row["prompt_sha"],
            "gold": row["gold"],
            "answer": row["answers"][0],
            "maj_correct": row["maj_correct"],
            "finish_reason": finish_reason,
            "sample_chars": row["sample_chars"][0],
            "max_tokens": MAX_TOKENS,
        },
        "artifacts": {
            "run_spec": {
                "path": "run-spec.json",
                "sha256": sha256_file(config.results / evidence.candidate.name / "run-spec.json"),
            },
            "finished": {
                "path": f"{attempt_dir.name}/finished.json",
                "sha256": sha256_file(attempt_dir / "finished.json"),
            },
            "result": {
                "path": f"{attempt_dir.name}/aime-extended.json",
                "sha256": sha256_file(attempt_dir / "aime-extended.json"),
            },
            "request_journal": {
                "path": f"{attempt_dir.name}/responses.jsonl",
                "sha256": sha256_file(attempt_dir / "responses.jsonl"),
                "records": 1,
            },
        },
        "primary_terminal_marker_sha256": evidence.marker_sha256,
        "host_identity": validate_current_host(config),
    }


def validate_completion(
    config: Config,
    evidence: PrimaryEvidence,
    spec: dict[str, Any],
) -> dict[str, Any]:
    arm_dir = config.results / evidence.candidate.name
    marker_path = arm_dir / "completed.json"
    require(marker_path.is_file(), f"diagnostic completion marker is missing: {marker_path}")
    marker = load_json(marker_path)
    attempt_name = marker.get("attempt")
    require(isinstance(attempt_name, str) and attempt_name.startswith("attempt-"), "diagnostic completion attempt is invalid")
    attempt_dir = arm_dir / attempt_name
    finished, result = validate_attempt(config, evidence, attempt_dir, spec)
    require(marker == completion_marker(config, evidence, attempt_dir, finished, result), "diagnostic completion marker mismatch")
    return marker


def recover_completed_attempt(
    config: Config,
    evidence: PrimaryEvidence,
    spec: dict[str, Any],
) -> bool:
    arm_dir = config.results / evidence.candidate.name
    if (arm_dir / "completed.json").is_file():
        validate_completion(config, evidence, spec)
        return True
    attempts = sorted(
        (path for path in arm_dir.glob("attempt-*") if path.is_dir()),
        key=lambda path: int(path.name.removeprefix("attempt-"))
        if path.name.removeprefix("attempt-").isdigit()
        else 0,
    )
    for attempt_dir in attempts:
        try:
            finished, result = validate_attempt(config, evidence, attempt_dir, spec)
        except DiagnosticError:
            continue
        write_json_once(
            arm_dir / "completed.json",
            completion_marker(config, evidence, attempt_dir, finished, result),
        )
        return True
    return False


def run_attempt(
    config: Config,
    evidence: PrimaryEvidence,
    artifact_dir: Path,
    spec: dict[str, Any],
) -> None:
    arm_dir = config.results / evidence.candidate.name
    number = next_number(arm_dir, "attempt-")
    attempt_dir = arm_dir / f"attempt-{number}"
    attempt_dir.mkdir()
    run_spec_path = arm_dir / "run-spec.json"
    started = {
        "schema": f"{SCHEMA}-attempt-started",
        "started_at": utc_now(),
        "arm": dataclasses.asdict(evidence.candidate),
        "run_spec_sha256": sha256_file(run_spec_path),
        "artifact_identity_sha256": sha256_file(artifact_dir / "identity.json"),
        "primary_terminal_marker_sha256": evidence.marker_sha256,
        "host_identity": validate_current_host(config),
        "execution_runner": {
            "path": str(config.script),
            "sha256": sha256_file(config.script),
        },
    }
    write_json_once(attempt_dir / "started.json", started)

    server_stdout_path = attempt_dir / "server.stdout.jsonl"
    server_stderr_path = attempt_dir / "server.stderr.log"
    evaluator_log_path = attempt_dir / "evaluator.log"
    responses_path = attempt_dir / "responses.jsonl"
    result_path = attempt_dir / "aime-extended.json"
    server: subprocess.Popen[Any] | None = None
    evaluator_status = 1
    server_status: int | None = None
    error_message: str | None = None
    interrupted = False
    server_shutdown_requested = False

    server_stdout = server_stdout_path.open("xb")
    server_stderr = server_stderr_path.open("xb")
    try:
        validate_shared_artifacts(config, spec)
        server_environment = evaluator_environment(config, config.evaluator_project)
        server_environment["MLXFAST_TOP15_REAL_QUALITY_BRIDGE"] = str(
            artifact_dir / "candidate-bridge"
        )
        server_command = [
            "uv",
            "run",
            "--project",
            str(config.evaluator_project),
            "--locked",
            str(config.evaluator_cli),
            "serve",
            str(artifact_dir),
            "--no-build",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--startup-timeout",
            str(STARTUP_TIMEOUT_S),
            "--request-timeout",
            str(REQUEST_TIMEOUT_S),
            "--request-log",
            str(responses_path),
            "--head-mode",
            "full",
        ]
        server = subprocess.Popen(
            server_command,
            cwd=artifact_dir,
            env=server_environment,
            stdout=server_stdout,
            stderr=server_stderr,
            start_new_session=True,
        )
        ready = wait_for_ready(server, server_stdout_path)
        base_url = ready["base_url"]
        evaluator_command = [
            "uv",
            "run",
            "--project",
            str(config.evaluator_project),
            "--locked",
            "python",
            str(config.evaluator_project / "upstream/aime_eval.py"),
            "--base-url",
            base_url,
            "--model",
            MODEL_NAME,
            "--years",
            "2024,2025-I,2025-II",
            "--k",
            "1",
            "--temperature",
            "0.0",
            "--top-p",
            "1.0",
            "--top-k",
            "-1",
            "--max-tokens",
            str(MAX_TOKENS),
            "--min-tokens",
            "0",
            "--no-thinking",
            "--seed",
            "1234",
            "--client-concurrency",
            "1",
            "--request-timeout-s",
            str(REQUEST_TIMEOUT_S),
            "--save-text",
            "--label",
            f"top15-extended-aime-{evidence.candidate.name}",
            "--out",
            str(result_path),
            "--expect-count",
            "1",
            "--ids-file",
            str(artifact_dir / "ids.json"),
        ]
        invocation = {
            "schema": f"{SCHEMA}-invocation",
            "created_at": utc_now(),
            "contract": spec["diagnostic_contract"],
            "server_command": server_command,
            "evaluator_command": evaluator_command,
            "server_ready": ready,
            "host_identity": started["host_identity"],
            "execution_runner": started["execution_runner"],
        }
        write_json_once(attempt_dir / "invocation.json", invocation)
        with evaluator_log_path.open("xb") as evaluator_log:
            evaluator_status = run_logged(
                evaluator_command,
                log=evaluator_log,
                cwd=artifact_dir,
                env=evaluator_environment(config, config.evaluator_project),
            )
        require(evaluator_status == 0, f"pinned AIME evaluator exited with status {evaluator_status}")
        validate_diagnostic_result(result_path, evidence)
    except KeyboardInterrupt:
        interrupted = True
        evaluator_status = 130
        error_message = "KeyboardInterrupt"
    except BaseException as error:
        error_message = f"{type(error).__name__}: {error}"
    finally:
        if server is not None:
            server_shutdown_requested = server.poll() is None
            terminate_process(server)
            server_status = server.returncode
        server_stdout.close()
        server_stderr.close()

    try:
        shared_after = shared_artifact_identity(config)
    except BaseException as error:
        shared_after = {"error": f"{type(error).__name__}: {error}"}
        if error_message is None:
            error_message = str(shared_after["error"])
    server_shutdown_clean = server_status == 0 or (
        server_shutdown_requested and server_status == 130
    )
    exit_code = (
        0
        if evaluator_status == 0 and server_shutdown_clean and error_message is None
        else evaluator_status or server_status or 1
    )
    finished = {
        "schema": f"{SCHEMA}-attempt-finished",
        "finished_at": utc_now(),
        "arm": dataclasses.asdict(evidence.candidate),
        "exit_code": exit_code,
        "server_exit_code": server_status,
        "server_shutdown_requested": server_shutdown_requested,
        "server_shutdown_clean": server_shutdown_clean,
        "error": error_message,
        "run_spec_sha256": sha256_file(run_spec_path),
        "shared_artifacts_after": shared_after,
        "hashes": attempt_hashes(attempt_dir),
    }
    write_json_once(attempt_dir / "finished.json", finished)
    if interrupted:
        raise KeyboardInterrupt
    require(exit_code == 0, f"extended AIME attempt failed; see {attempt_dir}")
    validated_finished, result = validate_attempt(config, evidence, attempt_dir, spec)
    write_json_once(
        arm_dir / "completed.json",
        completion_marker(config, evidence, attempt_dir, validated_finished, result),
    )


def validate_results_separation(config: Config) -> None:
    primary = config.primary_results.resolve()
    results = config.results.resolve()
    workspace = config.workspace.resolve()
    require(results != primary and results != workspace, "diagnostic results must be separate from primary results and workspace")
    require(primary not in results.parents and results not in primary.parents, "diagnostic and primary result trees must be disjoint")
    require(not config.results.is_symlink(), f"diagnostic results root may not be a symlink: {config.results}")


def command_preflight(config: Config) -> int:
    validate_results_separation(config)
    provenance = validate_common_inputs(config)
    host = validate_current_host(config)
    evidence = [validate_primary_evidence(config, candidate) for candidate in candidates(config)]
    print(
        f"extended-aime: preflight OK; evaluator={provenance['sha256']} "
        f"host={host['model']} ({host['chip']}, {host['memory']})"
    )
    for item in evidence:
        print(
            f"extended-aime: eligible rank {item.candidate.rank} "
            f"{item.candidate.submission_id} primary_marker={item.marker_sha256}"
        )
    print("extended-aime: no build or model process was launched")
    return 0


def command_run(config: Config, selector: str) -> int:
    validate_results_separation(config)
    validate_common_inputs(config)
    validate_current_host(config)
    chosen = select_candidates(config, selector)
    evidence_rows = [validate_primary_evidence(config, candidate) for candidate in chosen]
    failures = 0
    with workspace_lock(config):
        require_workspace_idle(config)
        evaluator = ensure_evaluator_bundle(config)
        for evidence in evidence_rows:
            try:
                artifact_dir, spec, _ = build_and_preserve_artifact(
                    config, evidence, evaluator
                )
                if recover_completed_attempt(config, evidence, spec):
                    print(f"extended-aime: rank {evidence.candidate.rank} already complete")
                    continue
                print(f"extended-aime: running rank {evidence.candidate.rank} {FROZEN_ID}")
                run_attempt(config, evidence, artifact_dir, spec)
                marker = validate_completion(config, evidence, spec)
                print(
                    f"extended-aime: rank {evidence.candidate.rank} complete "
                    f"outcome={marker['outcome']}"
                )
            except KeyboardInterrupt:
                raise
            except Exception as error:
                failures += 1
                print(
                    f"extended-aime: rank {evidence.candidate.rank} failed: "
                    f"{type(error).__name__}: {error}",
                    file=sys.stderr,
                )
    if failures:
        raise DiagnosticError(f"{failures} extended-AIME arm(s) failed; immutable evidence was retained")
    return 0


def result_status(
    config: Config,
    evidence: PrimaryEvidence,
    evaluator: dict[str, Any],
) -> tuple[str, str]:
    arm_dir = config.results / evidence.candidate.name
    if not arm_dir.exists():
        return "pending", "no diagnostic artifacts"
    try:
        _, spec, _ = validate_artifact_bundle(config, evidence, evaluator)
        if (arm_dir / "completed.json").is_file():
            marker = validate_completion(config, evidence, spec)
            return "complete", str(marker["outcome"])
        attempts = len([path for path in arm_dir.glob("attempt-*") if path.is_dir()])
        return "pending", f"artifact frozen; {attempts} incomplete/failed attempt(s)"
    except DiagnosticError as error:
        return "invalid", str(error)


def command_status(config: Config, *, require_complete: bool = False) -> int:
    validate_results_separation(config)
    workspace_provenance = validate_common_inputs(config)
    evaluator = workspace_provenance
    if config.evaluator_root.exists():
        evaluator = evaluator_provenance(config, config.evaluator_project)
    complete = 0
    invalid = 0
    for candidate in candidates(config):
        evidence = validate_primary_evidence(config, candidate)
        status, detail = result_status(config, evidence, evaluator)
        print(f"rank {candidate.rank}: {status} - {detail}")
        complete += int(status == "complete")
        invalid += int(status == "invalid")
    print(f"extended-aime: {complete}/{len(FROZEN_RANKS)} complete; results={config.results}")
    if invalid or (require_complete and complete != len(FROZEN_RANKS)):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run isolated 6,144-token diagnostics for the four frozen AIME "
            "length-bounded top-15 quality arms."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "preflight", help="validate all frozen inputs and primary evidence without building or serving"
    )
    run_parser = subparsers.add_parser("run", help="build/preserve and run diagnostic arms serially")
    run_parser.add_argument(
        "selector",
        nargs="?",
        default="all",
        help="all, one of ranks 116-119, or one submission UUID prefix",
    )
    subparsers.add_parser("status", help="validate and summarize current diagnostic artifacts")
    verify_parser = subparsers.add_parser("verify", help="verify current artifacts without building or serving")
    verify_parser.add_argument(
        "--require-complete",
        action="store_true",
        help="return nonzero unless all four diagnostic arms are complete",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    config = Config.discover()
    if arguments.command == "preflight":
        return command_preflight(config)
    if arguments.command == "run":
        return command_run(config, arguments.selector)
    if arguments.command == "status":
        return command_status(config)
    if arguments.command == "verify":
        return command_status(config, require_complete=arguments.require_complete)
    raise DiagnosticError(f"unknown command: {arguments.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("extended-aime: interrupted; partial attempt retained", file=sys.stderr)
        raise SystemExit(130)
    except DiagnosticError as error:
        print(f"extended-aime: {error}", file=sys.stderr)
        raise SystemExit(1)
