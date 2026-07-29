from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ArtifactError(ValueError):
    """The supplied path is not a runnable Laguna quality-eval artifact."""


@dataclass(frozen=True)
class Artifact:
    root: Path
    weights: Path
    tokenizer: Path
    bridge: Path
    metallib: Path | None
    kind: str
    transform_source_sha256: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "root": str(self.root),
            "weights": str(self.weights),
            "tokenizer": str(self.tokenizer),
            "bridge": str(self.bridge),
            "metallib": str(self.metallib) if self.metallib else None,
            "transform_source_sha256": self.transform_source_sha256,
        }


def _resolve(root: Path, value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / "quality-artifact.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ArtifactError(f"{path} must contain a JSON object")
    return value


def _first_file(paths: list[Path]) -> Path | None:
    return next((path.resolve() for path in paths if path.is_file()), None)


def _first_dir(paths: list[Path], predicate: Any) -> Path | None:
    return next((path.resolve() for path in paths if path.is_dir() and predicate(path)), None)


def _has_weights(path: Path) -> bool:
    return (
        (path / "config.json").is_file()
        and (path / "model.safetensors.index.json").is_file()
        and any(path.glob("*.safetensors"))
    )


def _has_tokenizer(path: Path) -> bool:
    return (path / "tokenizer.json").is_file() and (
        (path / "chat_template.jinja").is_file()
        or _tokenizer_config_has_template(path / "tokenizer_config.json")
    )


def _tokenizer_config_has_template(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        config = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(config, dict) and config.get("chat_template"))


def _require_file(path: Path | None, label: str, hint: str) -> Path:
    if path is None or not path.is_file():
        actual = str(path) if path else "not found"
        raise ArtifactError(f"{label} {actual}; {hint}")
    return path.resolve()


def _require_dir(path: Path | None, label: str, predicate: Any, hint: str) -> Path:
    if path is None or not path.is_dir() or not predicate(path):
        actual = str(path) if path else "not found"
        raise ArtifactError(f"{label} {actual}; {hint}")
    return path.resolve()


def resolve_artifact(
    artifact: str | os.PathLike[str],
    *,
    weights: str | os.PathLike[str] | None = None,
    tokenizer: str | os.PathLike[str] | None = None,
    bridge: str | os.PathLike[str] | None = None,
    metallib: str | os.PathLike[str] | None = None,
) -> Artifact:
    """Resolve a prepared checkout or a self-contained quality artifact.

    A checkout is the normal input. A portable artifact can instead provide
    ``quality-artifact.json`` with relative ``weights``, ``tokenizer``,
    ``bridge``, and optional ``metallib`` paths.
    """

    root = Path(artifact).expanduser().resolve()
    if not root.is_dir():
        raise ArtifactError(f"artifact directory does not exist: {root}")

    manifest = _read_manifest(root)
    is_checkout = (root / "Package.swift").is_file() and (
        root / "Sources" / "MLXFastModel"
    ).is_dir()
    kind = "checkout" if is_checkout else "bundle"

    weights_path = _resolve(root, weights or manifest.get("weights"))
    if weights_path is None:
        weights_path = _first_dir([root / "weights"], _has_weights)
    weights_path = _require_dir(
        weights_path,
        "transformed weights not found at",
        _has_weights,
        "run the checkout's transform step or pass --weights",
    )

    tokenizer_path = _resolve(root, tokenizer or manifest.get("tokenizer"))
    if tokenizer_path is None:
        tokenizer_path = _first_dir(
            [
                root / "tokenizer",
                root / "reference_weights" / "laguna-xs-2.1-nvfp4-mlx",
                weights_path,
            ],
            _has_tokenizer,
        )
    tokenizer_path = _require_dir(
        tokenizer_path,
        "Laguna tokenizer not found at",
        _has_tokenizer,
        "pass --tokenizer pointing to tokenizer.json plus chat_template.jinja",
    )

    bridge_path = _resolve(root, bridge or manifest.get("bridge"))
    if bridge_path is None:
        bridge_path = _first_file(
            [
                root / ".build-quality" / "release" / "laguna-quality-bridge",
                root
                / ".build-quality"
                / "arm64-apple-macosx"
                / "release"
                / "laguna-quality-bridge",
                root
                / "senpai"
                / "quality_eval"
                / "bridge"
                / ".build"
                / "release"
                / "laguna-quality-bridge",
                root / "bin" / "laguna-quality-bridge",
                root / "laguna-quality-bridge",
            ]
        )
    bridge_path = _require_file(
        bridge_path,
        "quality bridge not found at",
        "build laguna-quality-bridge or pass --bridge",
    )
    if not os.access(bridge_path, os.X_OK):
        raise ArtifactError(f"quality bridge is not executable: {bridge_path}")

    metallib_path = _resolve(root, metallib or manifest.get("metallib"))
    if metallib_path is None:
        metallib_path = _first_file(
            [
                root / ".build-worker" / "release" / "mlx.metallib",
                root
                / ".build-worker"
                / "arm64-apple-macosx"
                / "release"
                / "mlx.metallib",
                root / ".build-quality" / "release" / "mlx.metallib",
                root
                / ".build-quality"
                / "arm64-apple-macosx"
                / "release"
                / "mlx.metallib",
                root / "lib" / "mlx.metallib",
            ]
        )
    if metallib_path is not None and not metallib_path.is_file():
        raise ArtifactError(f"Metal library does not exist: {metallib_path}")

    return Artifact(
        root=root,
        weights=weights_path,
        tokenizer=tokenizer_path,
        bridge=bridge_path,
        metallib=metallib_path,
        kind=kind,
        transform_source_sha256=_transform_marker(weights_path),
    )


def _transform_marker(weights: Path) -> str | None:
    path = weights / ".benchmark-source.sha256"
    if not path.is_file():
        return None
    value = path.read_text().strip()
    return value or None


def artifact_identity(artifact: Artifact) -> dict[str, Any]:
    """Capture durable identities for the exact executable model artifact."""

    named_paths: dict[str, Path] = {
        "bridge": artifact.bridge,
        "weights/config.json": artifact.weights / "config.json",
        "weights/model.safetensors.index.json": (
            artifact.weights / "model.safetensors.index.json"
        ),
        "tokenizer/tokenizer.json": artifact.tokenizer / "tokenizer.json",
        "tokenizer/tokenizer_config.json": artifact.tokenizer / "tokenizer_config.json",
        "tokenizer/chat_template.jinja": artifact.tokenizer / "chat_template.jinja",
        "tokenizer/config.json": artifact.tokenizer / "config.json",
    }
    if artifact.metallib is not None:
        named_paths["metallib"] = artifact.metallib
    for path in sorted(artifact.weights.glob("*.safetensors")):
        named_paths[f"weights/{path.name}"] = path

    files: dict[str, dict[str, Any]] = {}
    for name, path in named_paths.items():
        if not path.is_file():
            continue
        files[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }

    identity: dict[str, Any] = {
        "files": files,
        "transform_source_sha256": artifact.transform_source_sha256,
    }
    if artifact.kind == "checkout":
        identity["checkout"] = _checkout_source_identity(artifact.root)
    return identity


def _checkout_source_identity(root: Path) -> dict[str, Any]:
    benchmark_path = root / "benchmark.json"
    try:
        benchmark = json.loads(benchmark_path.read_text())
        editable = benchmark["editablePaths"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ArtifactError(f"cannot read editablePaths from {benchmark_path}: {error}") from error
    if not isinstance(editable, list) or not all(isinstance(path, str) for path in editable):
        raise ArtifactError(f"{benchmark_path} editablePaths must be a list of strings")

    files: set[Path] = set()
    missing: list[str] = []
    for relative in editable:
        path = root / relative
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(candidate for candidate in path.rglob("*") if candidate.is_file())
        else:
            missing.append(relative)

    digest = hashlib.sha256()
    for path in sorted(files):
        relative = str(path.relative_to(root))
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(_file_sha256(path).encode())
        digest.update(b"\n")
    for relative in sorted(missing):
        digest.update(relative.encode())
        digest.update(b"\0MISSING\n")

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *editable],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to capture checkout source identity: {error}") from error
    return {
        "git_head": head,
        "git_dirty": bool(status),
        "editable_source_sha256": digest.hexdigest(),
        "editable_file_count": len(files),
        "missing_editable_paths": missing,
    }


def bridge_source_sha256(checkout: str | os.PathLike[str]) -> str:
    root = Path(checkout).expanduser().resolve()
    digest = hashlib.sha256()
    source_identity = _checkout_source_identity(root)
    digest.update(str(source_identity["git_head"]).encode())
    digest.update(b"\n")
    digest.update(str(source_identity["editable_source_sha256"]).encode())
    digest.update(b"\n")
    digest.update(_bridge_dependency_dirty_sha256(root).encode())
    digest.update(b"\n")
    inputs = [
        root / "Package.swift",
        root / "Package.resolved",
        root / "senpai" / "quality_eval" / "bridge" / "Package.swift",
        root / "senpai" / "quality_eval" / "bridge" / "Package.resolved",
        *sorted(
            (root / "senpai" / "quality_eval" / "bridge" / "Sources").rglob("*")
        ),
    ]
    for path in inputs:
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(_file_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _bridge_dependency_dirty_sha256(root: Path) -> str:
    """Fingerprint uncommitted inputs outside the participant-editable surface."""

    paths = (
        "Package.swift",
        "Package.resolved",
        "Sources/MLXFastCore",
        "Sources/MLXFastModel",
        "Vendor/mlx-swift",
        "Vendor/mlx-swift-lm",
    )
    try:
        changes = subprocess.run(
            [
                "git",
                "diff",
                "--binary",
                "--no-ext-diff",
                "--no-textconv",
                "HEAD",
                "--",
                *paths,
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        untracked = subprocess.run(
            [
                "git",
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *paths,
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(
            f"failed to fingerprint quality bridge dependencies: {error}"
        ) from error

    digest = hashlib.sha256(changes)
    for encoded in untracked.split(b"\0"):
        if not encoded:
            continue
        relative = os.fsdecode(encoded)
        path = root / relative
        digest.update(encoded)
        digest.update(b"\0")
        if path.is_file():
            digest.update(_file_sha256(path).encode())
        else:
            digest.update(b"MISSING")
        digest.update(b"\n")
    return digest.hexdigest()


def transform_source_sha256(checkout: str | os.PathLike[str]) -> str:
    """Match benchmark.sh's source_hash for the submitted transform surface."""

    root = Path(checkout).expanduser().resolve()
    paths = (
        "Package.swift",
        "Package.resolved",
        "Sources/MLXFastCore",
        "Sources/MLXFastTransform",
    )
    try:
        listed = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                *paths,
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to fingerprint transform sources: {error}") from error

    digest = hashlib.sha256()
    for encoded in listed.split(b"\0"):
        if not encoded:
            continue
        relative = os.fsdecode(encoded)
        path = root / relative
        digest.update(encoded)
        digest.update(b"\0")
        if path.is_file():
            file_digest = _file_sha256(path)
            digest.update(f"{file_digest}  {relative}\n".encode())
        else:
            digest.update(b"MISSING\0")
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_weights(
    checkout: str | os.PathLike[str],
    *,
    build: bool,
    reference: str | os.PathLike[str] | None = None,
) -> Path:
    """Return transformed weights that match the checkout's transform sources."""

    root = Path(checkout).expanduser().resolve()
    weights = root / "weights"
    expected = transform_source_sha256(root)
    if _has_weights(weights) and _transform_marker(weights) == expected:
        return weights.resolve()
    if not build:
        raise ArtifactError(
            "transformed weights are missing or stale for this checkout; "
            "rerun without --no-build, or run ./benchmark.sh --local-submit"
        )

    reference_path = (
        _resolve(root, reference)
        if reference is not None
        else root / "reference_weights" / "laguna-xs-2.1-nvfp4-mlx"
    )
    if reference_path is None or not _has_weights(reference_path):
        raise ArtifactError(
            f"reference checkpoint not found at {reference_path}; "
            "run ./setup.sh or pass --reference"
        )

    binary = _build_transform_cli(root)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".quality-transform.", dir=root)
    ).resolve()
    staged_weights = staging_root / "weights"
    previous_weights = staging_root / "previous-weights"
    preserve_staging = False
    try:
        environment = dict(os.environ)
        environment["MLXFAST_OFFLINE_WRITABLE_PATHS"] = str(staging_root)
        subprocess.run(
            [
                str(root / ".github" / "scripts" / "run-offline.sh"),
                str(binary),
                "transform",
                "--reference",
                str(reference_path),
                "--output",
                str(staged_weights),
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        if not _has_weights(staged_weights):
            raise ArtifactError(
                f"transform completed without a runnable artifact at {staged_weights}"
            )
        (staged_weights / ".benchmark-source.sha256").write_text(expected + "\n")
        (staged_weights / ".gitkeep").touch()

        if weights.exists():
            if weights.is_symlink() or not weights.is_dir():
                raise ArtifactError(f"refusing to replace non-directory weights path: {weights}")
            weights.replace(previous_weights)
        try:
            staged_weights.replace(weights)
        except BaseException:
            if previous_weights.exists() and not weights.exists():
                try:
                    previous_weights.replace(weights)
                except BaseException:
                    preserve_staging = True
            raise
        if previous_weights.exists():
            shutil.rmtree(previous_weights)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to prepare transformed weights: {error}") from error
    finally:
        if not preserve_staging:
            shutil.rmtree(staging_root, ignore_errors=True)

    if not _has_weights(weights) or _transform_marker(weights) != expected:
        raise ArtifactError("installed transformed weights failed freshness validation")
    return weights.resolve()


def _build_transform_cli(root: Path) -> Path:
    try:
        subprocess.run(
            [
                "swift",
                "build",
                "-c",
                "release",
                "--force-resolved-versions",
                "--package-path",
                str(root),
                "--scratch-path",
                str(root / ".build"),
                "--product",
                "mlxfast-swift",
            ],
            cwd=root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to build the transform CLI: {error}") from error
    binary = _first_file(
        [
            root / ".build" / "release" / "mlxfast-swift",
            root
            / ".build"
            / "arm64-apple-macosx"
            / "release"
            / "mlxfast-swift",
        ]
    )
    return _require_file(binary, "built transform CLI not found at", str(root / ".build"))


def build_bridge(checkout: str | os.PathLike[str]) -> Path:
    root = Path(checkout).expanduser().resolve()
    package = root / "senpai" / "quality_eval" / "bridge" / "Package.swift"
    if not package.is_file():
        raise ArtifactError(
            f"quality bridge package not found at {package}; pass a prepared bundle or --bridge"
        )
    scratch = root / ".build-quality"
    try:
        subprocess.run(
            [
                "swift",
                "build",
                "-c",
                "release",
                "--force-resolved-versions",
                "--package-path",
                str(package.parent),
                "--scratch-path",
                str(scratch),
                "--product",
                "laguna-quality-bridge",
            ],
            cwd=root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to build laguna-quality-bridge: {error}") from error
    binary = _first_file(
        [
            scratch / "release" / "laguna-quality-bridge",
            scratch
            / "arm64-apple-macosx"
            / "release"
            / "laguna-quality-bridge",
        ]
    )
    binary = _require_file(binary, "built quality bridge not found at", str(scratch))
    _bridge_source_sidecar(binary).write_text(bridge_source_sha256(root) + "\n")
    return binary


def ensure_bridge(
    checkout: str | os.PathLike[str],
    *,
    build: bool,
) -> Path:
    root = Path(checkout).expanduser().resolve()
    if build:
        return build_bridge(root)
    scratch = root / ".build-quality"
    binary = _first_file(
        [
            scratch / "release" / "laguna-quality-bridge",
            scratch
            / "arm64-apple-macosx"
            / "release"
            / "laguna-quality-bridge",
        ]
    )
    binary = _require_file(
        binary,
        "quality bridge not found at",
        "rerun without --no-build",
    )
    sidecar = _bridge_source_sidecar(binary)
    current = sidecar.read_text().strip() if sidecar.is_file() else ""
    if current != bridge_source_sha256(root):
        raise ArtifactError(
            "quality bridge is missing or stale for this checkout; "
            "rerun without --no-build"
        )
    return binary


def _bridge_source_sidecar(binary: Path) -> Path:
    return binary.with_name(binary.name + ".source.sha256")


def ensure_metallib(
    checkout: str | os.PathLike[str],
    *,
    build: bool,
) -> Path:
    root = Path(checkout).expanduser().resolve()
    script = root / "tools" / "build-mlx-metallib.sh"
    if not script.is_file():
        raise ArtifactError(f"MLX metallib builder not found at {script}")
    metallib = root / ".build-worker" / "release" / "mlx.metallib"
    sidecar = metallib.with_suffix(metallib.suffix + ".fingerprint")
    try:
        fingerprint = subprocess.run(
            [str(script), "--print-fingerprint"],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to fingerprint vendored MLX sources: {error}") from error
    expected = f"mlxfast-metallib-fingerprint-v1 {fingerprint}"
    current = sidecar.read_text().strip() if sidecar.is_file() else ""
    if metallib.is_file() and current == expected:
        return metallib.resolve()
    if not build:
        raise ArtifactError(
            "mlx.metallib is missing or stale for this checkout; "
            "rerun without --no-build or run tools/build-mlx-metallib.sh"
        )
    try:
        subprocess.run([str(script)], cwd=root, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"failed to build mlx.metallib: {error}") from error
    if not metallib.is_file() or not sidecar.is_file():
        raise ArtifactError(f"metallib build did not publish {metallib} and its fingerprint")
    if sidecar.read_text().strip() != expected:
        raise ArtifactError("built mlx.metallib fingerprint does not match current sources")
    return metallib.resolve()
