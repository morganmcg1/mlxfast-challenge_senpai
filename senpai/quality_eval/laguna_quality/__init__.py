"""Local quality-evaluation adapter for modified Laguna checkouts."""

from .artifact import Artifact, ArtifactError, resolve_artifact
from .bridge import BridgeError, BridgeProcess

__all__ = [
    "Artifact",
    "ArtifactError",
    "BridgeError",
    "BridgeProcess",
    "resolve_artifact",
]
