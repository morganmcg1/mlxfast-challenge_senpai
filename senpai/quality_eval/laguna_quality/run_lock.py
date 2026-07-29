from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


class ModelRunLockError(RuntimeError):
    """Another process already owns the machine's single-model budget."""


class ModelRunLock:
    """Interoperate with benchmark.sh's per-user, mkdir-based model lock."""

    def __init__(self, label: str) -> None:
        root = Path(
            os.environ.get(
                "MLXFAST_LOCAL_RUN_LOCK_DIR",
                str(Path.home() / ".cache" / "mlxfast"),
            )
        ).expanduser()
        self.path = root / f"mlxfast-local-benchmark-{os.getuid()}.lock"
        self.label = label
        self.acquired = False

    def acquire(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ModelRunLockError(
                f"cannot create model-run lock directory {self.path.parent}: {error}; "
                "set MLXFAST_LOCAL_RUN_LOCK_DIR to a writable shared directory"
            ) from error

        for attempt in range(2):
            try:
                self.path.mkdir()
            except FileExistsError:
                holder = self._holder_pid()
                if holder is None and attempt == 0:
                    time.sleep(0.2)
                    holder = self._holder_pid()
                if holder is not None and _process_exists(holder):
                    raise ModelRunLockError(
                        f"another model run (pid {holder}) holds {self.path}; "
                        "wait for it to finish"
                    )
                try:
                    shutil.rmtree(self.path)
                except OSError as error:
                    raise ModelRunLockError(
                        f"cannot reclaim stale model-run lock {self.path}: {error}"
                    ) from error
                continue
            except OSError as error:
                raise ModelRunLockError(
                    f"cannot acquire model-run lock {self.path}: {error}"
                ) from error
            else:
                self.acquired = True
                try:
                    (self.path / "pid").write_text(f"{os.getpid()}\n")
                    (self.path / "owner").write_text(f"quality-eval {self.label}\n")
                except OSError:
                    self.release()
                    raise
                residents = _resident_model_processes()
                if residents:
                    self.release()
                    details = "\n".join(f"  {line}" for line in residents)
                    raise ModelRunLockError(
                        "a model-holding Laguna process is already running; "
                        "wait for it or clean up a verified orphan:\n"
                        f"{details}"
                    )
                return
        raise ModelRunLockError(f"could not acquire model-run lock {self.path}")

    def _holder_pid(self) -> int | None:
        try:
            value = (self.path / "pid").read_text().strip()
        except OSError:
            return None
        return int(value) if value.isdigit() else None

    def release(self) -> None:
        if not self.acquired:
            return
        holder = self._holder_pid()
        if holder not in (None, os.getpid()):
            return
        shutil.rmtree(self.path, ignore_errors=True)
        self.acquired = False

    def __enter__(self) -> ModelRunLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _resident_model_processes() -> list[str]:
    pattern = (
        r"runtime-worker[[:space:]]+--weights"
        r"|mlxfast-swift[[:space:]]+(benchmark|correctness|correctness-trace|"
        r"generate-golden|generate-gpqa-answers|attach-free-run-gate)"
        r"|laguna-quality-bridge[[:space:]]+--weights"
    )
    try:
        result = subprocess.run(
            ["pgrep", "-u", str(os.getuid()), "-f", pattern],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    excluded = {os.getpid(), os.getppid()}
    pids = [
        int(value)
        for value in result.stdout.split()
        if value.isdigit() and int(value) not in excluded
    ]
    if not pids:
        return []
    try:
        details = subprocess.run(
            [
                "ps",
                "-o",
                "pid=,ppid=,rss=,command=",
                "-p",
                ",".join(map(str, pids)),
            ],
            text=True,
            capture_output=True,
            check=False,
        ).stdout
    except OSError:
        return [str(pid) for pid in pids]
    return [line.strip() for line in details.splitlines() if line.strip()]
