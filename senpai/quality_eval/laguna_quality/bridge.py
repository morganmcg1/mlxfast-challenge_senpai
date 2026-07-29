from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Mapping
from typing import Any, TextIO

from .artifact import Artifact


class BridgeError(RuntimeError):
    """The Laguna bridge exited or violated its JSONL protocol."""


class BridgeProcess:
    """One persistent, serialized connection to the RAM-resident Swift model."""

    def __init__(
        self,
        artifact: Artifact,
        *,
        startup_timeout: float = 900.0,
        stderr: TextIO | None = None,
        command: list[str] | None = None,
        full_logits: bool = False,
    ) -> None:
        self.artifact = artifact
        self.startup_timeout = startup_timeout
        self.stderr = stderr or sys.stderr
        self.full_logits = full_logits
        self.command = command or self._artifact_command(
            artifact,
            full_logits=full_logits,
        )
        self._process: subprocess.Popen[str] | None = None
        self._stdout: queue.Queue[str | None] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self.ready: dict[str, Any] | None = None

    @staticmethod
    def _artifact_command(artifact: Artifact, *, full_logits: bool) -> list[str]:
        command = [str(artifact.bridge), "--weights", str(artifact.weights)]
        if artifact.metallib:
            command.extend(["--metallib", str(artifact.metallib)])
        if full_logits:
            command.append("--full-logits")
        return command

    def start(self) -> dict[str, Any]:
        if self._process is not None:
            if self.ready is None:
                raise BridgeError("bridge startup is already in progress")
            return self.ready

        self._stdout = queue.Queue()
        environment = dict(os.environ)
        for name in tuple(environment):
            if name.startswith("DARKBLOOM_"):
                environment.pop(name)
        if self.full_logits:
            # Sampling and PPL need the true full-vocabulary distribution.
            environment["DARKBLOOM_LM_HEAD_PRUNE"] = "0"
        # The remaining candidate feature switches use their submitted/default
        # values rather than inheriting local ablation flags from the shell.
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        stdout_queue = self._stdout
        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            args=(self._process.stdout, stdout_queue),
            name="laguna-bridge-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(self._process.stderr,),
            name="laguna-bridge-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        line = self._get_line(self.startup_timeout, "startup")
        try:
            ready = self._decode(line)
        except BridgeError:
            self.close()
            raise
        if ready.get("kind") != "ready" or ready.get("ok") is not True:
            self.close()
            raise BridgeError(f"expected bridge ready record, received {ready!r}")
        ready["head_mode"] = "full" if self.full_logits else "ranked"
        self.ready = ready
        return ready

    def request(self, request: Mapping[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        with self._lock:
            self.start()
            process = self._require_running()
            request_id = request.get("id")
            if request_id is None:
                self._next_id += 1
                request_id = f"q{self._next_id}"
            payload = {**request, "id": str(request_id)}
            assert process.stdin is not None
            try:
                process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise BridgeError(self._exit_message("bridge write failed")) from error

            line = self._get_line(timeout, f"request {request_id}")
            try:
                response = self._decode(line)
            except BridgeError:
                self.close()
                raise
            if response.get("id") != str(request_id):
                self.close()
                raise BridgeError(
                    f"bridge response id {response.get('id')!r} does not match {request_id!r}"
                )
            if response.get("ok") is not True:
                raise BridgeError(str(response.get("error") or "bridge request failed"))
            return response

    @staticmethod
    def _read_stdout(
        stream: TextIO,
        output: queue.Queue[str | None],
    ) -> None:
        for line in stream:
            output.put(line)
        output.put(None)

    def _read_stderr(self, stream: TextIO) -> None:
        for line in stream:
            self.stderr.write(line)
            self.stderr.flush()

    def _get_line(self, timeout: float | None, operation: str) -> str:
        try:
            line = self._stdout.get(timeout=timeout)
        except queue.Empty as error:
            self.close()
            raise BridgeError(f"timed out during bridge {operation}") from error
        if line is None:
            message = self._exit_message(f"bridge exited during {operation}")
            self.close()
            raise BridgeError(message)
        return line

    @staticmethod
    def _decode(line: str) -> dict[str, Any]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BridgeError(f"bridge emitted invalid JSON: {line.rstrip()!r}") from error
        if not isinstance(value, dict):
            raise BridgeError(f"bridge emitted a non-object response: {value!r}")
        return value

    def _require_running(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise BridgeError("bridge has not started")
        if self._process.poll() is not None:
            raise BridgeError(self._exit_message("bridge is not running"))
        return self._process

    def _exit_message(self, prefix: str) -> str:
        if self._process is None:
            return prefix
        code = self._process.poll()
        return f"{prefix} (exit status {code})" if code is not None else prefix

    def close(self) -> None:
        process, self._process = self._process, None
        self.ready = None
        if process is None:
            return
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
        if self._stdout_thread:
            self._stdout_thread.join(timeout=2)
        if self._stderr_thread:
            self._stderr_thread.join(timeout=2)
        self._stdout_thread = None
        self._stderr_thread = None

    def __enter__(self) -> BridgeProcess:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
