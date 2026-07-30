from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .artifact import Artifact, artifact_identity
from .bridge import BridgeProcess
from .ppl_manifest import build_manifest
from .public_probe import run_public_correctness_probe
from .server import (
    CHAT_PROMPT_FORMAT,
    MODEL_NAME,
    RAW_SINGLE_USER_PROMPT_FORMAT,
    LagunaAPI,
    QualityHTTPServer,
    RequestJournal,
)
from .tokenizer import LagunaTokenizer


ALL_SUITES = ("ppl", "mmlu_pro", "gpqa_diamond", "aime", "gsm8k")
PROMPT_HASH_SUITES = {"mmlu_pro", "gpqa_diamond", "aime", "gsm8k"}
RANKED_GPQA_MAX_TOKENS = 128
MMLU_DATASET_SEED = 12_345
GPQA_DATASET_SEED = 2
TOKEN_IDS_PROMPT_FORMAT = "token_ids"
METRIC_RETENTION_NUMERATOR = 97
METRIC_RETENTION_DENOMINATOR = 100
METRIC_RETENTION_FLOOR = (
    METRIC_RETENTION_NUMERATOR / METRIC_RETENTION_DENOMINATOR
)
BEHAVIOR_MATCH_NUMERATOR = 7
BEHAVIOR_MATCH_DENOMINATOR = 9
@dataclass(frozen=True)
class Profile:
    max_tokens: int
    aime_max_tokens: int
    min_tokens: int
    gpqa_sample_temperature: float
    multiple_choice_cot: bool
    mmlu_ids_file: str | None
    gpqa_ids_file: str | None
    aime_ids_file: str | None
    gsm8k_ids_file: str | None
    mmlu_n: int
    mmlu_limit: int | None
    gpqa_limit: int | None
    aime_limit: int | None
    gsm8k_n: int
    gsm8k_limit: int | None
    ppl_records: int | None
    ppl_target_tokens: int | None
    max_connections: int
    request_timeout_s: int


PROFILES = {
    # Fast plumbing and gross-regression check. It deliberately exercises
    # every scoring path, including sampled GPQA and teacher-forced PPL.
    "smoke": Profile(
        max_tokens=1_024,
        aime_max_tokens=2_048,
        min_tokens=0,
        gpqa_sample_temperature=1.0,
        multiple_choice_cot=False,
        mmlu_ids_file=None,
        gpqa_ids_file=None,
        aime_ids_file=None,
        gsm8k_ids_file=None,
        mmlu_n=2,
        mmlu_limit=2,
        gpqa_limit=2,
        aime_limit=2,
        gsm8k_n=2,
        gsm8k_limit=2,
        ppl_records=2,
        ppl_target_tokens=24,
        max_connections=2,
        request_timeout_s=600,
    ),
    # Routine matched-regression panel for local use. Its bounded one-pass
    # workload covers every evaluator and both Laguna head paths while staying
    # small enough for a 10-20 minute pre-submission check on the 128 GB M4 Max.
    "quick": Profile(
        max_tokens=1_024,
        aime_max_tokens=2_048,
        min_tokens=0,
        gpqa_sample_temperature=0.5,
        multiple_choice_cot=False,
        mmlu_ids_file="quick_mmlu_pro.json",
        gpqa_ids_file="quick_gpqa_diamond.json",
        aime_ids_file="quick_aime.json",
        gsm8k_ids_file="quick_gsm8k.json",
        mmlu_n=20,
        mmlu_limit=None,
        gpqa_limit=9,
        aime_limit=9,
        gsm8k_n=6,
        gsm8k_limit=None,
        ppl_records=None,
        ppl_target_tokens=32,
        max_connections=1,
        request_timeout_s=900,
    ),
    # A useful local panel that remains substantially smaller than the
    # challenge-era publication run on a serial Apple-Silicon endpoint.
    "standard": Profile(
        max_tokens=1_024,
        aime_max_tokens=2_048,
        min_tokens=8,
        gpqa_sample_temperature=1.0,
        multiple_choice_cot=True,
        mmlu_ids_file=None,
        gpqa_ids_file=None,
        aime_ids_file=None,
        gsm8k_ids_file=None,
        mmlu_n=100,
        mmlu_limit=None,
        gpqa_limit=50,
        aime_limit=15,
        gsm8k_n=100,
        gsm8k_limit=None,
        ppl_records=None,
        ppl_target_tokens=64,
        max_connections=8,
        request_timeout_s=1_800,
    ),
    # Exact downstream sizes/decode budget from EVAL_METHODOLOGY.md. The
    # caller normally pairs this with five passes; it can take many hours.
    "full": Profile(
        max_tokens=6_144,
        aime_max_tokens=6_144,
        min_tokens=8,
        gpqa_sample_temperature=1.0,
        multiple_choice_cot=True,
        mmlu_ids_file=None,
        gpqa_ids_file=None,
        aime_ids_file=None,
        gsm8k_ids_file=None,
        mmlu_n=500,
        mmlu_limit=None,
        gpqa_limit=None,
        aime_limit=None,
        gsm8k_n=500,
        gsm8k_limit=None,
        ppl_records=None,
        ppl_target_tokens=None,
        max_connections=16,
        request_timeout_s=7_200,
    ),
}


@dataclass(frozen=True)
class RunOptions:
    output: Path
    profile: str = "smoke"
    passes: int = 1
    suites: tuple[str, ...] = ALL_SUITES
    request_timeout: float | None = None
    startup_timeout: float = 900.0
    keep_going: bool = False
    ppl_dataset: Path | None = None
    preparation_wall_s: float = 0.0
    weave_project: str | None = None
    change_label: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()


def run_evaluations(artifact: Artifact, options: RunOptions) -> dict[str, Any]:
    if options.profile not in PROFILES:
        raise ValueError(f"unknown profile {options.profile!r}")
    if options.passes < 1:
        raise ValueError("passes must be at least one")
    unknown = set(options.suites) - set(ALL_SUITES)
    if unknown:
        raise ValueError(f"unknown suites: {', '.join(sorted(unknown))}")
    if not options.suites:
        raise ValueError("select at least one evaluation suite")
    if options.ppl_dataset is not None and "ppl" not in options.suites:
        raise ValueError("--ppl-dataset requires the ppl suite")
    if options.request_timeout is not None and options.request_timeout <= 0:
        raise ValueError("request timeout must be positive")
    if options.startup_timeout <= 0:
        raise ValueError("startup timeout must be positive")
    if options.weave_project is not None and not options.weave_project.strip():
        raise ValueError("--weave-project cannot be empty")
    attribute_keys = [key for key, _ in options.attributes]
    if any(not key for key in attribute_keys) or len(set(attribute_keys)) != len(
        attribute_keys
    ):
        raise ValueError("Weave attribute keys must be non-empty and unique")

    profile = PROFILES[options.profile]
    output = options.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            f"output directory is not empty: {output}; choose a new --output path"
        )
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "run.json"
    started_at = time.time()
    run_manifest: dict[str, Any] = {
        "status": "running",
        "started_at": _timestamp(started_at),
        "artifact": artifact.as_dict(),
        "profile": options.profile,
        "profile_settings": asdict(profile),
        "passes": options.passes,
        "suites": list(options.suites),
        "head_modes": {
            mode: {
                "lm_head": "full_bf16" if mode == "full" else "ranked_default",
                "min_tokens": profile.min_tokens if mode == "full" else 0,
                "max_tokens": (
                    profile.max_tokens if mode == "full" else RANKED_GPQA_MAX_TOKENS
                ),
                "role": "quality_panel" if mode == "full" else "behavior_proxy",
            }
            for mode in _head_modes(options.suites)
        },
        "prompt_formats": _prompt_formats(options.suites),
        "host_identity": _host_identity(),
        "model": MODEL_NAME,
        "evaluator_provenance": _evaluation_provenance(),
        "output": str(output),
        "commands": [],
        "failures": [],
        "evaluation_valid": False,
        "quality_gate_passed": None,
        "preparation_wall_s": options.preparation_wall_s,
        "change_label": options.change_label,
        "weave": {
            "project": options.weave_project,
            "logging_enabled": options.weave_project is not None,
            "parallelism": 1,
            "trials": 1,
            "evaluations": [],
        },
    }
    _write_json(manifest_path, run_manifest)

    bridge_log: Any = None
    weave_module: Any = None
    weave_client: Any = None
    try:
        print("[quality-eval] fingerprinting the executable model artifact", flush=True)
        run_manifest["artifact_identity"] = artifact_identity(artifact)
        weave_module, weave_client = _initialize_weave(options.weave_project)
        run_manifest["weave"]["attributes"] = _weave_attributes(
            options,
            run_manifest,
            output,
        )
        _write_json(manifest_path, run_manifest)
        tokenizer = LagunaTokenizer(artifact.tokenizer)
        run_manifest["tokenizer_stop_token_ids"] = tokenizer.stop_token_ids
        _write_json(manifest_path, run_manifest)
        ppl_dataset = options.ppl_dataset
        if "ppl" in options.suites and ppl_dataset is None:
            ppl_dataset = output / "ppl_manifest.jsonl"
            run_manifest["ppl_manifest"] = build_manifest(
                tokenizer,
                ppl_dataset,
                limit=profile.ppl_records,
                max_target_tokens=profile.ppl_target_tokens,
            )
            _write_json(manifest_path, run_manifest)
        elif ppl_dataset is not None:
            ppl_dataset = ppl_dataset.expanduser().resolve()
            if not ppl_dataset.is_file():
                raise ValueError(f"PPL dataset does not exist: {ppl_dataset}")
            run_manifest["ppl_manifest"] = {
                "manifest": str(ppl_dataset),
                "external": True,
                "sha256": hashlib.sha256(ppl_dataset.read_bytes()).hexdigest(),
                "num_records": _ppl_manifest_record_count(ppl_dataset),
            }
            _write_json(manifest_path, run_manifest)

        request_timeout = options.request_timeout or float(profile.request_timeout_s)
        journal = RequestJournal(output / "responses.jsonl")
        bridge_log = (output / "bridge.log").open("a")
        for head_mode in _head_modes(options.suites):
            _run_head_phase(
                artifact=artifact,
                tokenizer=tokenizer,
                journal=journal,
                bridge_log=bridge_log,
                head_mode=head_mode,
                options=options,
                profile=profile,
                output=output,
                manifest_path=manifest_path,
                run_manifest=run_manifest,
                ppl_dataset=ppl_dataset,
                request_timeout=request_timeout,
                weave_module=weave_module,
                weave_attributes=run_manifest["weave"]["attributes"],
            )

        if run_manifest["failures"]:
            raise ValueError(
                f"{len(run_manifest['failures'])} evaluator job(s) failed"
            )
        _validate_run_outputs(output, run_manifest)
        if PROMPT_HASH_SUITES.intersection(options.suites):
            _check_prompt_sets(output, options.passes)
        summary = summarize_runs([output])
        _validate_summary(summary, options.suites, options.passes)
        _write_json(output / "summary.json", summary)
        run_manifest["status"] = "failed" if run_manifest["failures"] else "completed"
        run_manifest["evaluation_valid"] = not run_manifest["failures"]
        run_manifest["summary"] = str(output / "summary.json")
        run_manifest["finished_at"] = _timestamp()
        run_manifest["wall_s"] = time.time() - started_at
        run_manifest["total_wall_s"] = (
            options.preparation_wall_s + run_manifest["wall_s"]
        )
        _write_json(manifest_path, run_manifest)
        _print_run_metrics(summary)
        print("[quality-eval] EVALUATION RUN: PASS", flush=True)
        print(
            f"[quality-eval] completed in {run_manifest['wall_s']:.1f}s "
            f"({run_manifest['total_wall_s']:.1f}s including preparation)",
            flush=True,
        )
        print(f"[quality-eval] results saved to {output}", flush=True)
        return run_manifest
    except BaseException as error:
        run_manifest["status"] = "failed"
        run_manifest["finished_at"] = _timestamp()
        run_manifest["wall_s"] = time.time() - started_at
        run_manifest["total_wall_s"] = (
            options.preparation_wall_s + run_manifest["wall_s"]
        )
        run_manifest["error"] = str(error)
        _write_json(manifest_path, run_manifest)
        print(f"[quality-eval] EVALUATION RUN: FAIL ({error})", flush=True)
        raise
    finally:
        if bridge_log is not None:
            bridge_log.close()
        if weave_client is not None and weave_module is not None:
            weave_module.finish()


def _head_modes(suites: tuple[str, ...]) -> tuple[str, ...]:
    modes = ["full"]
    if "gpqa_diamond" in suites:
        modes.append("ranked")
    return tuple(modes)


def _prompt_formats(suites: tuple[str, ...]) -> dict[str, dict[str, str]]:
    formats: dict[str, dict[str, str]] = {}
    for suite in suites:
        formats[suite] = {
            "full": (
                TOKEN_IDS_PROMPT_FORMAT
                if suite == "ppl"
                else CHAT_PROMPT_FORMAT
            )
        }
    if "gpqa_diamond" in formats:
        formats["gpqa_diamond"]["ranked"] = RAW_SINGLE_USER_PROMPT_FORMAT
    return formats


def _host_identity() -> dict[str, str | None]:
    return {
        "system": platform.system(),
        "system_release": platform.release(),
        "machine": platform.machine(),
        "macos_version": platform.mac_ver()[0] or None,
        "hardware_model": _sysctl_value("hw.model"),
        "cpu_brand": _sysctl_value("machdep.cpu.brand_string"),
    }


def _sysctl_value(name: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    completed = subprocess.run(
        ["sysctl", "-n", name],
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _initialize_weave(project: str | None) -> tuple[Any, Any]:
    os.environ["WEAVE_PARALLELISM"] = "1"
    if project is None:
        os.environ["WEAVE_DISABLED"] = "true"
    else:
        os.environ.pop("WEAVE_DISABLED", None)

    import weave

    if project is None:
        return weave, None
    return weave, weave.init(project)


def _weave_attributes(
    options: RunOptions,
    manifest: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    identity = manifest["artifact_identity"]
    checkout = identity.get("checkout") or {}
    attributes = dict(options.attributes)
    attributes.update(
        {
            "quality.run_id": output.name,
            "quality.profile": options.profile,
            "quality.trials": 1,
            "quality.passes": options.passes,
            "quality.suites": ",".join(options.suites),
            "quality.change_label": options.change_label,
            "quality.evaluator_sha256": manifest["evaluator_provenance"]["sha256"],
            "model.git_commit": checkout.get("git_head"),
            "model.git_dirty": checkout.get("git_dirty"),
            "model.editable_source_sha256": checkout.get("editable_source_sha256"),
            "model.transform_source_sha256": identity.get("transform_source_sha256"),
            "host.hardware_model": manifest["host_identity"].get("hardware_model"),
            "host.cpu_brand": manifest["host_identity"].get("cpu_brand"),
            "host.macos_version": manifest["host_identity"].get("macos_version"),
        }
    )
    return {key: value for key, value in attributes.items() if value is not None}


def _artifact_source_sha256(manifest: dict[str, Any]) -> str:
    identity = manifest["artifact_identity"]
    checkout = identity.get("checkout") or {}
    source = checkout.get("editable_source_sha256")
    if isinstance(source, str) and source:
        return source
    transform = identity.get("transform_source_sha256")
    if isinstance(transform, str) and transform:
        return transform
    bridge = (identity.get("files") or {}).get("bridge") or {}
    digest = bridge.get("sha256")
    if isinstance(digest, str) and digest:
        return digest
    raise ValueError("model artifact has no source or executable identity")


def _job_result_path(name: str, pass_dir: Path) -> Path:
    if name == "ppl":
        return pass_dir / "ppl_summary.json"
    if name == "gsm8k_greedy":
        return pass_dir / "candidate_gsm8k_greedy.json"
    return pass_dir / f"{name}.json"


def _job_category(name: str) -> str:
    if name == "ppl":
        return "ppl"
    if name == "gpqa_diamond_ranked_greedy":
        return "behavior"
    return "downstream"


def _read_job_result(name: str, path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    result: dict[str, Any] = {
        "status": "passed",
        "exit_code": 0,
        "job_name": name,
        "result_path": str(path),
    }
    if name == "ppl":
        total = payload.get("num_records")
        if (
            not isinstance(total, int)
            or isinstance(total, bool)
            or total < 1
        ):
            raise ValueError(f"{path}: invalid PPL record count")
        result.update(
            {
                "ppl": _finite_metric(payload, "ppl", path, positive=True),
                "total": total,
            }
        )
        return result

    if name == "aime_greedy":
        correct_key, total_key, score_key = (
            "n_correct_maj",
            "n_problems",
            "maj_k_accuracy",
        )
    elif name == "gsm8k_greedy":
        correct_key, total_key, score_key = "n_correct", "n_problems", "accuracy"
    else:
        correct_key, total_key, score_key = "n_correct", "n_expected", "accuracy"
    correct = payload.get(correct_key)
    total = payload.get(total_key)
    if (
        not isinstance(correct, int)
        or isinstance(correct, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < 1
        or not 0 <= correct <= total
    ):
        raise ValueError(f"{path}: invalid correct/total result")
    score = _finite_metric(
        payload,
        score_key,
        path,
        minimum=0.0,
        maximum=1.0,
    )
    if not math.isclose(score, correct / total, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError(f"{path}: score does not match correct/total")
    result.update(
        {
            "correct": correct,
            "total": total,
            "score": score,
        }
    )
    return result


def _weave_score_summary(
    category: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    failed = sum(
        not isinstance(row, dict) or row.get("passed") is not True
        for row in rows
    )
    summary: dict[str, Any] = {
        "jobs": len(rows),
        "failed_jobs": failed,
        "passed": bool(rows) and failed == 0,
    }
    if category == "ppl":
        ppls = [
            float(row["ppl"])
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("ppl"), (int, float))
            and not isinstance(row.get("ppl"), bool)
        ]
        summary["ppl"] = (
            ppls[0] if summary["passed"] and len(ppls) == 1 else None
        )
    elif category == "downstream":
        correct = sum(
            int(row["correct"])
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("correct"), int)
            and not isinstance(row.get("correct"), bool)
        )
        total = sum(
            int(row["total"])
            for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("total"), int)
            and not isinstance(row.get("total"), bool)
        )
        summary.update(
            {
                "correct": correct,
                "total": total,
                "overall_score": (
                    correct / total if summary["passed"] and total else None
                ),
            }
        )
    return summary


def _run_weave_jobs(
    *,
    weave_module: Any,
    jobs: list[dict[str, Any]],
    model_config: dict[str, Any],
    evaluation_metadata: dict[str, Any],
    attributes: dict[str, Any],
    display_prefix: str,
    keep_going: bool,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    outcomes: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()
    stop_requested = threading.Event()

    class CommandModel(weave_module.Model):
        profile: str
        head_mode: str
        artifact_sha256: str
        git_commit: str | None = None
        change_label: str | None = None

        @weave_module.op
        async def predict(
            self,
            job_name: str,
            command: list[str],
            log_path: str,
            result_path: str,
            category: str,
        ) -> dict[str, Any]:
            del category
            if stop_requested.is_set():
                outcome = {
                    "status": "skipped",
                    "exit_code": 1,
                    "job_name": job_name,
                    "error": "skipped after an earlier evaluator failure",
                    "wall_s": 0.0,
                }
                with lock:
                    outcomes[job_name] = outcome
                return outcome
            started = time.monotonic()
            try:
                await _run_command_async(command, Path(log_path))
                outcome = _read_job_result(job_name, Path(result_path))
            except subprocess.CalledProcessError as error:
                outcome = {
                    "status": "failed",
                    "exit_code": error.returncode,
                    "job_name": job_name,
                    "error": f"evaluator exited with status {error.returncode}",
                }
            except Exception as error:
                outcome = {
                    "status": "failed",
                    "exit_code": 1,
                    "job_name": job_name,
                    "error": f"{type(error).__name__}: {error}",
                }
            outcome["wall_s"] = time.monotonic() - started
            if not keep_going and outcome.get("status") != "passed":
                stop_requested.set()
            with lock:
                outcomes[job_name] = outcome
            return outcome

    class CommandScorer(weave_module.Scorer):
        category: str

        @weave_module.op
        def score(self, *, output: dict[str, Any]) -> dict[str, Any]:
            row = {
                "passed": output.get("status") == "passed",
                "correct": output.get("correct"),
                "total": output.get("total"),
                "score": output.get("score"),
                "ppl": output.get("ppl"),
            }
            return {key: value for key, value in row.items() if value is not None}

        @weave_module.op
        def summarize(self, score_rows: list[dict[str, Any]]) -> dict[str, Any]:
            return _weave_score_summary(self.category, score_rows)

    async def evaluate_all() -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        model = CommandModel(**model_config)
        for category in ("ppl", "downstream", "behavior"):
            category_jobs = [job for job in jobs if job["category"] == category]
            if not category_jobs:
                continue
            evaluation_name = f"{display_prefix}-{category}"
            evaluation = weave_module.Evaluation(
                dataset=category_jobs,
                scorers=[CommandScorer(category=category)],
                trials=1,
                metadata={**evaluation_metadata, "category": category},
                evaluation_name=evaluation_name,
            )
            with weave_module.attributes(attributes):
                summary = await evaluation.evaluate(model)
            records.append(
                {
                    "name": evaluation_name,
                    "category": category,
                    "trials": 1,
                    "jobs": [job["job_name"] for job in category_jobs],
                    "summary": _json_safe(summary),
                }
            )
            if stop_requested.is_set():
                break
        return records

    return outcomes, asyncio.run(evaluate_all())


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def _run_head_phase(
    *,
    artifact: Artifact,
    tokenizer: LagunaTokenizer,
    journal: RequestJournal,
    bridge_log: Any,
    head_mode: str,
    options: RunOptions,
    profile: Profile,
    output: Path,
    manifest_path: Path,
    run_manifest: dict[str, Any],
    ppl_dataset: Path | None,
    request_timeout: float,
    weave_module: Any,
    weave_attributes: dict[str, Any],
) -> None:
    phase_started = time.time()
    phase_record = run_manifest.setdefault("head_timings", {}).setdefault(
        head_mode,
        {},
    )
    phase_record["started_at"] = _timestamp(phase_started)
    _write_json(manifest_path, run_manifest)
    full_logits = head_mode == "full"
    bridge = BridgeProcess(
        artifact,
        startup_timeout=options.startup_timeout,
        stderr=bridge_log,
        full_logits=full_logits,
    )
    server = QualityHTTPServer(
        ("127.0.0.1", 0),
        LagunaAPI(bridge, tokenizer, request_timeout=request_timeout),
        journal=journal,
    )
    server_thread = threading.Thread(
        target=server.serve_forever,
        name=f"laguna-quality-http-{head_mode}",
        daemon=True,
    )
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    run_manifest.setdefault("base_urls", {})[head_mode] = base_url
    _write_json(manifest_path, run_manifest)

    server_started = False
    try:
        bridge_log.write(f"quality-eval: loading head_mode={head_mode}\n")
        bridge_log.flush()
        startup_started = time.time()
        bridge.start()
        phase_record["ready_at"] = _timestamp()
        phase_record["startup_wall_s"] = time.time() - startup_started
        if head_mode == "full":
            probe = run_public_correctness_probe(
                artifact.root,
                bridge,
                timeout=request_timeout,
            )
            run_manifest["local_public_correctness_probe"] = probe
            if probe.get("available") and not probe.get("matches_m5_fixture"):
                print(
                    "[quality-eval] warning: this host diverges from the "
                    "checked-in M5 public fixture on the first token; use a "
                    "matched baseline comparison for generation regressions",
                    flush=True,
                )
        _write_json(manifest_path, run_manifest)
        server_thread.start()
        server_started = True
        print(
            f"[quality-eval] model ready; head={head_mode} "
            f"profile={options.profile} passes={options.passes} output={output}",
            flush=True,
        )
        for pass_number in range(1, options.passes + 1):
            pass_dir = output / f"pass_{pass_number}"
            pass_dir.mkdir(parents=True, exist_ok=True)
            jobs: list[dict[str, Any]] = []
            for name, command in _pass_commands(
                pass_number=pass_number,
                pass_dir=pass_dir,
                suites=options.suites,
                profile=profile,
                base_url=base_url,
                ppl_dataset=ppl_dataset,
                ppl_records=(
                    (run_manifest.get("ppl_manifest") or {}).get("num_records")
                ),
                request_timeout_s=math.ceil(request_timeout),
                head_mode=head_mode,
            ):
                record = {
                    "pass": pass_number,
                    "name": name,
                    "head_mode": head_mode,
                    "command": command,
                    "log": str(pass_dir / f"{name}.log"),
                    "started_at": _timestamp(),
                }
                run_manifest["commands"].append(record)
                jobs.append(
                    {
                        "job_name": name,
                        "command": command,
                        "log_path": record["log"],
                        "result_path": str(_job_result_path(name, pass_dir)),
                        "category": _job_category(name),
                    }
                )
            _write_json(manifest_path, run_manifest)
            outcomes, weave_results = _run_weave_jobs(
                weave_module=weave_module,
                jobs=jobs,
                model_config={
                    "profile": options.profile,
                    "head_mode": head_mode,
                    "artifact_sha256": _artifact_source_sha256(run_manifest),
                    "git_commit": (
                        run_manifest["artifact_identity"]
                        .get("checkout", {})
                        .get("git_head")
                    ),
                    "change_label": options.change_label,
                },
                evaluation_metadata={
                    "evaluator_sha256": run_manifest["evaluator_provenance"]["sha256"],
                    "profile": options.profile,
                    "head_mode": head_mode,
                    "pass": pass_number,
                    "trials": 1,
                },
                attributes=weave_attributes,
                display_prefix=f"{output.name}-{head_mode}-p{pass_number}",
                keep_going=options.keep_going,
            )
            run_manifest["weave"]["evaluations"].extend(weave_results)
            records = {
                (record["pass"], record["head_mode"], record["name"]): record
                for record in run_manifest["commands"]
            }
            first_failure: subprocess.CalledProcessError | None = None
            for job in jobs:
                name = job["job_name"]
                outcome = outcomes.get(name) or {
                    "status": "failed",
                    "exit_code": 1,
                    "error": "Weave returned no outcome",
                }
                record = records[(pass_number, head_mode, name)]
                record.update(
                    {
                        key: value
                        for key, value in outcome.items()
                        if key in {"status", "exit_code", "error", "wall_s"}
                    }
                )
                record["finished_at"] = _timestamp()
                if outcome.get("status") != "passed":
                    exit_code = int(outcome.get("exit_code") or 1)
                    run_manifest["failures"].append(
                        {
                            "pass": pass_number,
                            "name": name,
                            "head_mode": head_mode,
                            "exit_code": exit_code,
                        }
                    )
                    first_failure = first_failure or subprocess.CalledProcessError(
                        exit_code,
                        job["command"],
                    )
            _write_json(manifest_path, run_manifest)
            if first_failure is not None and not options.keep_going:
                raise first_failure
    finally:
        if server_started:
            server.shutdown()
        server.server_close()
        bridge.close()
        if server_started:
            server_thread.join(timeout=5)
        phase_record["finished_at"] = _timestamp()
        phase_record["wall_s"] = time.time() - phase_started
        _write_json(manifest_path, run_manifest)


def summarize_runs(run_dirs: list[Path]) -> dict[str, Any]:
    run_dirs = [path.expanduser().resolve() for path in run_dirs]
    upstream = _upstream_dir()
    command = [
        sys.executable,
        str(upstream / "summarize_five_pass.py"),
        *(str(path) for path in run_dirs),
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("summarizer returned a non-object")
    return value


def _print_run_metrics(summary: dict[str, Any]) -> None:
    arms = summary.get("arms")
    if not isinstance(arms, list) or len(arms) != 1:
        return
    arm = arms[0]
    metrics = arm.get("metrics") or {}
    labels = (
        ("mmlu", "MMLU-Pro"),
        ("gpqa_greedy", "GPQA greedy"),
        ("gpqa_sampled", "GPQA sampled"),
        ("aime", "AIME"),
        ("gsm8k", "GSM8K"),
    )
    print("[quality-eval] metrics", flush=True)
    components = (arm.get("overall_score") or {}).get("components") or {}
    for name, label in labels:
        component = components.get(name)
        if isinstance(component, dict):
            print(
                f"[quality-eval]   {label}: "
                f"{component['correct']}/{component['total']} "
                f"({100.0 * component['score']:.2f}%)",
                flush=True,
            )
        else:
            mean = (metrics.get(name) or {}).get("mean")
            if isinstance(mean, (int, float)):
                print(
                    f"[quality-eval]   {label}: {100.0 * float(mean):.2f}%",
                    flush=True,
                )
    overall = arm.get("overall_score")
    if isinstance(overall, dict):
        print(
            f"[quality-eval]   Overall downstream: "
            f"{overall['correct']}/{overall['total']} "
            f"({100.0 * overall['score']:.2f}%)",
            flush=True,
        )
    ppl = (metrics.get("ppl") or {}).get("mean")
    if isinstance(ppl, (int, float)):
        print(f"[quality-eval]   PPL: {float(ppl):.6f}", flush=True)
    ranked = (metrics.get("gpqa_ranked") or {}).get("mean")
    if isinstance(ranked, (int, float)):
        print(
            f"[quality-eval]   Ranked GPQA diagnostic: "
            f"{100.0 * float(ranked):.2f}%",
            flush=True,
        )


def compare_runs(
    baseline: Path,
    candidate: Path,
    *,
    check_prompts: bool = True,
) -> dict[str, Any]:
    baseline = baseline.expanduser().resolve()
    candidate = candidate.expanduser().resolve()
    compatibility = _compare_contracts(baseline, candidate)
    baseline_manifest = json.loads((baseline / "run.json").read_text())
    candidate_manifest = json.loads((candidate / "run.json").read_text())
    if check_prompts and PROMPT_HASH_SUITES.intersection(
        baseline_manifest.get("suites") or []
    ):
        check_prompt_sets([baseline, candidate])
    summary = summarize_runs([baseline, candidate])
    _validate_summary(
        summary,
        baseline_manifest["suites"],
        baseline_manifest["passes"],
    )
    arms = summary.get("arms", [])
    if not isinstance(arms, list) or len(arms) != 2:
        raise ValueError("comparison requires exactly one baseline and one candidate")
    baseline_metrics = arms[0].get("metrics", {})
    candidate_metrics = arms[1].get("metrics", {})
    metrics: dict[str, Any] = {}
    for name in sorted(set(baseline_metrics) | set(candidate_metrics)):
        base = baseline_metrics.get(name, {}).get("mean")
        cand = candidate_metrics.get(name, {}).get("mean")
        if name == "overall_score":
            metrics[name] = _overall_score_comparison(
                base,
                cand,
                arms[0].get("overall_score"),
                arms[1].get("overall_score"),
            )
        else:
            metrics[name] = _metric_comparison(name, base, cand)
    response_identity = _compare_responses(baseline, candidate)
    response_identity["public_probe"] = _compare_public_probes(
        baseline_manifest,
        candidate_manifest,
    )
    return {
        "baseline": str(baseline.resolve()),
        "candidate": str(candidate.resolve()),
        "compatibility": compatibility,
        "minimum_retention": METRIC_RETENTION_FLOOR,
        "metrics": metrics,
        "response_identity": response_identity,
        "decision": _regression_decision(metrics, response_identity),
    }


def check_prompt_sets(run_dirs: list[Path]) -> None:
    directories: list[Path] = []
    for path in run_dirs:
        path = path.expanduser().resolve()
        passes = sorted(candidate for candidate in path.glob("pass_*") if candidate.is_dir())
        directories.extend(passes or [path])
    command = [
        sys.executable,
        str(_upstream_dir() / "check_prompt_sets.py"),
        *(str(path.resolve()) for path in directories),
    ]
    subprocess.run(command, check=True)


def _check_prompt_sets(output: Path, passes: int) -> None:
    pass_dirs = [output / f"pass_{number}" for number in range(1, passes + 1)]
    check_prompt_sets(pass_dirs)


def _expected_counts(profile: Profile | dict[str, Any]) -> dict[str, int]:
    value = asdict(profile) if isinstance(profile, Profile) else profile

    def manifest_count(setting: str) -> int | None:
        filename = value.get(setting)
        if filename is None:
            return None
        _, ids = _id_manifest(str(filename))
        return len(ids)

    def capped(primary: str, limit: str, maximum: int | None = None) -> int:
        count = value.get(limit)
        if count is None:
            count = value.get(primary)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"profile setting {primary}/{limit} must select samples")
        return min(count, maximum) if maximum is not None else count

    def canonical(limit: str, size: int) -> int:
        count = value.get(limit)
        if count is None:
            return size
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"profile setting {limit} must select samples")
        return min(count, size)

    return {
        "mmlu_pro": manifest_count("mmlu_ids_file")
        or capped("mmlu_n", "mmlu_limit"),
        "gpqa_diamond": manifest_count("gpqa_ids_file")
        or canonical("gpqa_limit", 198),
        "aime": manifest_count("aime_ids_file") or canonical("aime_limit", 60),
        "gsm8k": manifest_count("gsm8k_ids_file")
        or capped("gsm8k_n", "gsm8k_limit", 1_319),
    }


def _id_manifest(filename: str) -> tuple[Path, list[str]]:
    root = (_upstream_dir().parent / "manifests").resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError(f"unknown question manifest: {filename}")
    payload = json.loads(path.read_text())
    if (
        not isinstance(payload, list)
        or not payload
        or any(not isinstance(item, str) or not item for item in payload)
        or len(set(payload)) != len(payload)
    ):
        raise ValueError(f"question manifest must contain unique string IDs: {path}")
    return path, payload


def _ppl_manifest_record_count(path: Path) -> int:
    text = path.read_text().strip()
    if not text:
        raise ValueError(f"PPL manifest is empty: {path}")
    if text.startswith("["):
        records = json.loads(text)
    else:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(records, list) or not records or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError(f"PPL manifest must contain one or more JSON objects: {path}")
    return len(records)


def _pass_commands(
    *,
    pass_number: int,
    pass_dir: Path,
    suites: tuple[str, ...],
    profile: Profile,
    base_url: str,
    ppl_dataset: Path | None,
    ppl_records: int | None = None,
    request_timeout_s: int | None = None,
    head_mode: str = "all",
) -> list[tuple[str, list[str]]]:
    if head_mode not in {"all", "ranked", "full"}:
        raise ValueError(f"unknown quality head mode {head_mode!r}")
    upstream = _upstream_dir()
    python = sys.executable
    commands: list[tuple[str, list[str]]] = []
    timeout_s = request_timeout_s or profile.request_timeout_s
    expected = _expected_counts(profile)
    mmlu_ids = (
        _id_manifest(profile.mmlu_ids_file)[0]
        if profile.mmlu_ids_file is not None
        else None
    )
    gpqa_ids = (
        _id_manifest(profile.gpqa_ids_file)[0]
        if profile.gpqa_ids_file is not None
        else None
    )
    aime_ids = (
        _id_manifest(profile.aime_ids_file)[0]
        if profile.aime_ids_file is not None
        else None
    )
    gsm8k_ids = (
        _id_manifest(profile.gsm8k_ids_file)[0]
        if profile.gsm8k_ids_file is not None
        else None
    )
    common_eval = [
        "--max-tokens",
        str(
            RANKED_GPQA_MAX_TOKENS
            if head_mode == "ranked"
            else profile.max_tokens
        ),
        "--min-tokens",
        str(0 if head_mode == "ranked" else profile.min_tokens),
        "--max-connections",
        str(profile.max_connections),
        "--base-url",
        f"{base_url}/v1",
        "--model",
        MODEL_NAME,
    ]
    if "ppl" in suites and head_mode in {"all", "full"}:
        assert ppl_dataset is not None
        if not isinstance(ppl_records, int) or ppl_records < 1:
            raise ValueError("PPL suite requires a positive expected record count")
        commands.append(
            (
                "ppl",
                [
                    python,
                    str(upstream / "ppl_endpoint.py"),
                    "--base-url",
                    base_url,
                    "--model",
                    MODEL_NAME,
                    "--dataset-path",
                    str(ppl_dataset),
                    "--output-file",
                    str(pass_dir / "ppl_results.jsonl"),
                    "--summary-file",
                    str(pass_dir / "ppl_summary.json"),
                    "--request-timeout-s",
                    str(timeout_s),
                    "--expect-records",
                    str(ppl_records),
                ],
            )
        )
    if "mmlu_pro" in suites and head_mode in {"all", "full"}:
        command = [
            python,
            str(upstream / "run_eval.py"),
            "--task",
            "mmlu_pro",
            "--arm",
            "candidate",
            "--out",
            str(pass_dir / "mmlu_pro_greedy.json"),
            "--n",
            "0" if mmlu_ids is not None else str(profile.mmlu_n),
            "--expect-count",
            str(expected["mmlu_pro"]),
            "--seed",
            str(MMLU_DATASET_SEED),
            *common_eval,
        ]
        if mmlu_ids is not None:
            command.extend(["--ids-file", str(mmlu_ids)])
        elif profile.mmlu_limit is not None:
            command.extend(["--limit", str(profile.mmlu_limit)])
        if not profile.multiple_choice_cot:
            command.append("--no-cot")
        commands.append(("mmlu_pro_greedy", command))
    if "gpqa_diamond" in suites:
        greedy = [
            python,
            str(upstream / "run_eval.py"),
            "--task",
            "gpqa_diamond",
            "--arm",
            "candidate",
            "--out",
            str(pass_dir / "gpqa_diamond_greedy.json"),
            "--seed",
            str(GPQA_DATASET_SEED),
            "--expect-count",
            str(expected["gpqa_diamond"]),
            *common_eval,
        ]
        sampled_seed = pass_number - 1
        sampled = [
            python,
            str(upstream / "run_eval.py"),
            "--task",
            "gpqa_diamond",
            "--arm",
            "candidate",
            "--out",
            str(pass_dir / f"gpqa_diamond_sampled_s{sampled_seed}.json"),
            "--seed",
            str(GPQA_DATASET_SEED),
            "--temperature",
            str(profile.gpqa_sample_temperature),
            "--top-p",
            "0.95",
            "--top-k",
            "64",
            "--sampling-seed",
            str(sampled_seed),
            "--expect-count",
            str(expected["gpqa_diamond"]),
            *common_eval,
        ]
        if gpqa_ids is not None:
            for command in (greedy, sampled):
                command.extend(["--ids-file", str(gpqa_ids)])
        elif profile.gpqa_limit is not None:
            greedy.extend(["--limit", str(profile.gpqa_limit)])
            sampled.extend(["--limit", str(profile.gpqa_limit)])
        if not profile.multiple_choice_cot:
            greedy.append("--no-cot")
            sampled.append("--no-cot")
        if head_mode in {"all", "full"}:
            commands.append(("gpqa_diamond_greedy", greedy))
        if head_mode in {"all", "full"}:
            commands.append((f"gpqa_diamond_sampled_s{sampled_seed}", sampled))
        if head_mode == "ranked":
            ranked = [
                python,
                str(upstream / "run_eval.py"),
                "--task",
                "gpqa_diamond",
                "--arm",
                "candidate",
                "--out",
                str(pass_dir / "gpqa_diamond_ranked_greedy.json"),
                "--seed",
                str(GPQA_DATASET_SEED),
                "--expect-count",
                str(expected["gpqa_diamond"]),
                *common_eval,
                "--prompt-format",
                RAW_SINGLE_USER_PROMPT_FORMAT,
            ]
            if gpqa_ids is not None:
                ranked.extend(["--ids-file", str(gpqa_ids)])
            elif profile.gpqa_limit is not None:
                ranked.extend(["--limit", str(profile.gpqa_limit)])
            commands.append(("gpqa_diamond_ranked_greedy", ranked))
    if "aime" in suites and head_mode in {"all", "full"}:
        command = [
            python,
            str(upstream / "aime_eval.py"),
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
            str(profile.aime_max_tokens),
            "--min-tokens",
            str(profile.min_tokens),
            "--no-thinking",
            "--seed",
            "1234",
            "--client-concurrency",
            str(profile.max_connections),
            "--request-timeout-s",
            str(timeout_s),
            "--save-text",
            "--label",
            f"candidate_aime_greedy_p{pass_number}",
            "--out",
            str(pass_dir / "aime_greedy.json"),
            "--expect-count",
            str(expected["aime"]),
        ]
        if aime_ids is not None:
            command.extend(["--ids-file", str(aime_ids)])
        elif profile.aime_limit is not None:
            command.extend(["--limit", str(profile.aime_limit)])
        commands.append(("aime_greedy", command))
    if "gsm8k" in suites and head_mode in {"all", "full"}:
        command = [
            python,
            str(upstream / "gsm8k_eval.py"),
            "--base-url",
            base_url,
            "--model",
            MODEL_NAME,
            "--label",
            "candidate_gsm8k",
            "--regimes",
            "greedy",
            "--n",
            str(profile.gsm8k_n),
            "--expect-count",
            str(expected["gsm8k"]),
            "--n-shot",
            "8",
            "--seed",
            "1234",
            "--max-tokens",
            str(profile.max_tokens),
            "--min-tokens",
            str(profile.min_tokens),
            "--concurrency",
            str(profile.max_connections),
            "--request-timeout-s",
            str(timeout_s),
            "--save-text",
            "--out-dir",
            str(pass_dir),
        ]
        if gsm8k_ids is not None:
            command.extend(["--ids-file", str(gsm8k_ids)])
        elif profile.gsm8k_limit is not None:
            command.extend(["--limit", str(profile.gsm8k_limit)])
        commands.append(("gsm8k_greedy", command))
    return commands


async def _run_command_async(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[quality-eval] running {log_path.stem}", flush=True)
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        with log_path.open("w") as log:
            while line := await process.stdout.readline():
                text = line.decode(errors="replace")
                print(text, end="", flush=True)
                log.write(text)
                log.flush()
        return_code = await process.wait()
    except BaseException:
        await _terminate_process_group_async(process)
        raise
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


async def _terminate_process_group_async(
    process: asyncio.subprocess.Process,
) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
def _upstream_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "upstream"


def _compare_responses(baseline: Path, candidate: Path) -> dict[str, Any]:
    baseline_rows = _response_rows(baseline)
    candidate_rows = _response_rows(candidate)
    common = sorted(set(baseline_rows) & set(candidate_rows))
    mismatched_keys = [
        key for key in common if baseline_rows[key] != candidate_rows[key]
    ]
    mismatches = [{"result": key[0], "id": key[1]} for key in mismatched_keys]
    ranked_results = sorted(
        {
            key[0]
            for key in set(baseline_rows) | set(candidate_rows)
            if key[0].endswith("gpqa_diamond_ranked_greedy.json")
        }
    )
    ranked_by_result = []
    for result in ranked_results:
        baseline_keys = {key for key in baseline_rows if key[0] == result}
        candidate_keys = {key for key in candidate_rows if key[0] == result}
        common_keys = baseline_keys & candidate_keys
        matched = sum(
            baseline_rows[key] == candidate_rows[key] for key in common_keys
        )
        total = len(baseline_keys)
        required = _required_behavior_matches(total)
        baseline_only = len(baseline_keys - candidate_keys)
        candidate_only = len(candidate_keys - baseline_keys)
        ranked_by_result.append(
            {
                "result": result,
                "matched": matched,
                "total": total,
                "compared": len(common_keys),
                "match_rate": matched / total if total else None,
                "required_matches": required,
                "baseline_only": baseline_only,
                "candidate_only": candidate_only,
                "passed": (
                    baseline_only == 0
                    and candidate_only == 0
                    and total > 0
                    and matched >= required
                ),
            }
        )
    ranked_total = sum(result["total"] for result in ranked_by_result)
    ranked_matched = sum(result["matched"] for result in ranked_by_result)
    return {
        "matched": len(common) - len(mismatches),
        "total": len(common),
        "match_rate": (len(common) - len(mismatches)) / len(common) if common else None,
        "baseline_only": len(set(baseline_rows) - set(candidate_rows)),
        "candidate_only": len(set(candidate_rows) - set(baseline_rows)),
        "mismatches": mismatches[:100],
        "mismatches_truncated": len(mismatches) > 100,
        "ranked_gpqa": {
            "matched": ranked_matched,
            "total": ranked_total,
            "compared": sum(result["compared"] for result in ranked_by_result),
            "match_rate": ranked_matched / ranked_total if ranked_total else None,
            "required_matches": sum(
                result["required_matches"] for result in ranked_by_result
            ),
            "baseline_only": sum(
                result["baseline_only"] for result in ranked_by_result
            ),
            "candidate_only": sum(
                result["candidate_only"] for result in ranked_by_result
            ),
            "passed": (
                all(result["passed"] for result in ranked_by_result)
                if ranked_by_result
                else None
            ),
            "results": ranked_by_result,
        },
    }


def _compare_public_probes(
    baseline_manifest: dict[str, Any],
    candidate_manifest: dict[str, Any],
) -> dict[str, Any]:
    baseline = baseline_manifest["local_public_correctness_probe"]
    candidate = candidate_manifest["local_public_correctness_probe"]
    if not baseline["available"]:
        return {"available": False, "matched": None}
    baseline_token = baseline["actual_token"]
    candidate_token = candidate["actual_token"]
    return {
        "available": True,
        "baseline_token": baseline_token,
        "candidate_token": candidate_token,
        "matched": baseline_token == candidate_token,
    }


def _regression_decision(
    metrics: dict[str, Any],
    response_identity: dict[str, Any],
) -> dict[str, Any]:
    regressions = [
        {"metric": name, **values}
        for name, values in metrics.items()
        if values.get("gate_passed") is False
    ]
    row_set_drift = any(
        response_identity.get(key, 0)
        for key in ("baseline_only", "candidate_only")
    )
    ranked_gpqa = response_identity["ranked_gpqa"]
    behavior_passed = ranked_gpqa["passed"]
    probe_passed = (response_identity.get("public_probe") or {}).get("matched")
    response_drift = row_set_drift or bool(response_identity.get("mismatches")) or (
        (response_identity.get("public_probe") or {}).get("matched") is False
    )
    regression = (
        bool(regressions)
        or row_set_drift
        or behavior_passed is False
        or probe_passed is False
    )
    informative_metrics = [
        name for name, values in metrics.items() if values.get("informative")
    ]
    uninformative_metrics = [
        name
        for name, values in metrics.items()
        if values.get("available")
        and values.get("gate_role") != "monitor_only"
        and not values.get("informative")
    ]
    unavailable_metrics = [
        name for name, values in metrics.items() if not values.get("available")
    ]
    monitor_only_metrics = [
        name
        for name, values in metrics.items()
        if values.get("available") and values.get("gate_role") == "monitor_only"
    ]
    evidence_available = (
        bool(informative_metrics)
        or behavior_passed is not None
    )
    local_gate_passed = False if regression else True if evidence_available else None
    return {
        "status": (
            "regression"
            if regression
            else "retained"
            if evidence_available
            else "insufficient_evidence"
        ),
        "baseline_regression": regression,
        "minimum_retention": METRIC_RETENTION_FLOOR,
        "metric_regressions": regressions,
        "response_drift": response_drift,
        "metric_retention_passed": (
            not regressions if informative_metrics else None
        ),
        "informative_metrics": informative_metrics,
        "uninformative_metrics": uninformative_metrics,
        "unavailable_metrics": unavailable_metrics,
        "monitor_only_metrics": monitor_only_metrics,
        "behavior_response_passed": behavior_passed,
        "public_probe_passed": probe_passed,
        "row_sets_match": not row_set_drift,
        "local_retention_gate_passed": local_gate_passed,
        "quality_gate_passed": None,
    }


def _metric_comparison(
    name: str,
    baseline: Any,
    candidate: Any,
) -> dict[str, Any]:
    result = {
        "baseline": baseline,
        "candidate": candidate,
        "delta": None,
        "relative": None,
        "direction": "lower_is_better" if name == "ppl" else "higher_is_better",
        "gate_role": (
            "ppl"
            if name == "ppl"
            else "downstream_aggregate"
            if name == "overall_score"
            else "monitor_only"
        ),
        "retention": None,
        "minimum_retention": METRIC_RETENTION_FLOOR,
        "threshold": None,
        "available": False,
        "informative": False,
        "gate_passed": None,
    }
    if not isinstance(baseline, (int, float)) or not isinstance(
        candidate, (int, float)
    ):
        return result

    baseline = float(baseline)
    candidate = float(candidate)
    result["available"] = True
    result["delta"] = candidate - baseline
    if baseline != 0.0:
        result["relative"] = candidate / baseline
    if name == "ppl":
        if baseline <= 0.0 or candidate <= 0.0:
            result["gate_passed"] = False
            return result
        result["retention"] = baseline / candidate
        result["threshold"] = baseline / METRIC_RETENTION_FLOOR
        result["informative"] = True
        result["gate_passed"] = candidate <= result["threshold"] + 1e-12
    elif name == "overall_score" and baseline > 0.0:
        result["retention"] = candidate / baseline
        result["threshold"] = baseline * METRIC_RETENTION_FLOOR
        result["informative"] = True
        result["gate_passed"] = candidate + 1e-12 >= result["threshold"]
    elif name == "overall_score":
        result["threshold"] = baseline
    return result


def _overall_score_comparison(
    baseline: Any,
    candidate: Any,
    baseline_counts: Any,
    candidate_counts: Any,
) -> dict[str, Any]:
    result = _metric_comparison("overall_score", baseline, candidate)
    if not isinstance(baseline_counts, dict) or not isinstance(
        candidate_counts,
        dict,
    ):
        result["available"] = False
        result["informative"] = False
        result["gate_passed"] = None
        return result
    base_correct = baseline_counts.get("correct")
    base_total = baseline_counts.get("total")
    candidate_correct = candidate_counts.get("correct")
    candidate_total = candidate_counts.get("total")
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in (base_correct, base_total, candidate_correct, candidate_total)
    ):
        result["available"] = False
        result["informative"] = False
        result["gate_passed"] = None
        return result
    result.update(
        {
            "baseline_correct": base_correct,
            "baseline_total": base_total,
            "candidate_correct": candidate_correct,
            "candidate_total": candidate_total,
            "required_correct": (
                METRIC_RETENTION_NUMERATOR * base_correct
                + METRIC_RETENTION_DENOMINATOR
                - 1
            )
            // METRIC_RETENTION_DENOMINATOR,
            "counts_match": base_total == candidate_total,
        }
    )
    result["gate_passed"] = (
        (
            base_total == candidate_total
            and candidate_correct >= result["required_correct"]
        )
        if result["informative"]
        else None
    )
    return result


def _required_behavior_matches(total: int) -> int:
    return (
        total * BEHAVIOR_MATCH_NUMERATOR + BEHAVIOR_MATCH_DENOMINATOR - 1
    ) // BEHAVIOR_MATCH_DENOMINATOR


def _validate_run_outputs(root: Path, manifest: dict[str, Any]) -> None:
    settings = manifest.get("profile_settings")
    if not isinstance(settings, dict):
        raise ValueError(f"run has invalid profile_settings: {root / 'run.json'}")
    expected = _expected_counts(settings)
    passes = manifest.get("passes")
    suites = manifest.get("suites")
    if not isinstance(passes, int) or passes < 1:
        raise ValueError(f"run has invalid pass count: {root / 'run.json'}")
    if (
        not isinstance(suites, list)
        or not suites
        or any(suite not in ALL_SUITES for suite in suites)
    ):
        raise ValueError(f"run has invalid suites: {root / 'run.json'}")
    expected_head_modes = {
        mode: {
            "lm_head": "full_bf16" if mode == "full" else "ranked_default",
            "min_tokens": settings["min_tokens"] if mode == "full" else 0,
            "max_tokens": (
                settings["max_tokens"] if mode == "full" else RANKED_GPQA_MAX_TOKENS
            ),
            "role": "quality_panel" if mode == "full" else "behavior_proxy",
        }
        for mode in _head_modes(tuple(suites))
    }
    if manifest.get("head_modes") != expected_head_modes:
        raise ValueError(f"run has invalid head-mode policy: {root / 'run.json'}")
    if manifest.get("prompt_formats") != _prompt_formats(tuple(suites)):
        raise ValueError(f"run has invalid prompt-format policy: {root / 'run.json'}")
    host_identity = manifest.get("host_identity")
    if not isinstance(host_identity, dict) or any(
        not isinstance(host_identity.get(name), str) or not host_identity[name]
        for name in ("system", "system_release", "machine")
    ):
        raise ValueError(f"run lacks valid host identity: {root / 'run.json'}")
    _public_probe_contract(manifest, root)
    provenance = manifest.get("evaluator_provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("sha256"), str):
        raise ValueError(f"run lacks evaluator provenance: {root / 'run.json'}")
    _tokenizer_sha256s(manifest, root)
    stop_ids = manifest.get("tokenizer_stop_token_ids")
    if (
        not isinstance(stop_ids, list)
        or not stop_ids
        or any(
            not isinstance(token_id, int)
            or isinstance(token_id, bool)
            or token_id < 0
            for token_id in stop_ids
        )
    ):
        raise ValueError(f"run lacks valid tokenizer stop IDs: {root / 'run.json'}")

    ppl_records: int | None = None
    if "ppl" in suites:
        ppl_manifest = manifest.get("ppl_manifest")
        if not isinstance(ppl_manifest, dict):
            raise ValueError(f"PPL run lacks manifest metadata: {root / 'run.json'}")
        ppl_records = ppl_manifest.get("num_records")
        if (
            not isinstance(ppl_records, int)
            or isinstance(ppl_records, bool)
            or ppl_records < 1
            or not isinstance(ppl_manifest.get("sha256"), str)
        ):
            raise ValueError(
                f"PPL run is missing a positive manifest record count: {root / 'run.json'}"
            )

    for pass_number in range(1, passes + 1):
        pass_dir = root / f"pass_{pass_number}"
        if not pass_dir.is_dir():
            raise ValueError(f"run is incomplete; missing {pass_dir}")
        if "ppl" in suites:
            assert ppl_records is not None
            _validate_ppl_output(pass_dir, ppl_records)
        if "mmlu_pro" in suites:
            _validate_choice_output(
                pass_dir / "mmlu_pro_greedy.json",
                expected["mmlu_pro"],
            )
        if "gpqa_diamond" in suites:
            _validate_choice_output(
                pass_dir / "gpqa_diamond_greedy.json",
                expected["gpqa_diamond"],
            )
            _validate_choice_output(
                pass_dir / f"gpqa_diamond_sampled_s{pass_number - 1}.json",
                expected["gpqa_diamond"],
            )
            _validate_choice_output(
                pass_dir / "gpqa_diamond_ranked_greedy.json",
                expected["gpqa_diamond"],
                allow_length_truncation=True,
            )
        if "aime" in suites:
            _validate_problem_output(
                pass_dir / "aime_greedy.json",
                expected["aime"],
                metric="maj_k_accuracy",
                raw_field="texts",
            )
        if "gsm8k" in suites:
            matches = sorted(pass_dir.glob("*gsm8k*_greedy*.json"))
            if len(matches) != 1:
                raise ValueError(
                    f"expected exactly one GSM8K greedy result in {pass_dir}; "
                    f"found {len(matches)}"
                )
            _validate_problem_output(
                matches[0],
                expected["gsm8k"],
                metric="accuracy",
                raw_field="text",
                require_zero_errors=True,
            )
        if manifest.get("profile") == "quick":
            _validate_quick_prompt_contract(pass_dir, suites)


def _validate_quick_prompt_contract(
    pass_dir: Path,
    suites: list[str],
) -> None:
    contract_path = _upstream_dir().parent / "manifests" / "quick_prompt_contract.json"
    contract = _read_json_object(contract_path)
    paths: dict[str, Path] = {}
    if "mmlu_pro" in suites:
        paths["mmlu_pro_greedy"] = pass_dir / "mmlu_pro_greedy.json"
    if "gpqa_diamond" in suites:
        paths.update(
            {
                "gpqa_diamond_greedy": pass_dir / "gpqa_diamond_greedy.json",
                "gpqa_diamond_ranked_greedy": (
                    pass_dir / "gpqa_diamond_ranked_greedy.json"
                ),
            }
        )
        sampled = sorted(pass_dir.glob("gpqa_diamond_sampled_s*.json"))
        if len(sampled) != 1:
            raise ValueError(
                f"expected one quick GPQA sampled result in {pass_dir}"
            )
        paths["gpqa_diamond_sampled"] = sampled[0]
    if "aime" in suites:
        paths["aime_greedy"] = pass_dir / "aime_greedy.json"
    if "gsm8k" in suites:
        gsm8k = sorted(pass_dir.glob("*gsm8k*_greedy*.json"))
        if len(gsm8k) != 1:
            raise ValueError(f"expected one quick GSM8K result in {pass_dir}")
        paths["gsm8k_greedy"] = gsm8k[0]
    for name, path in paths.items():
        expected = contract.get(name)
        actual = _read_json_object(path).get("dataset_sha256")
        if (
            not isinstance(expected, str)
            or len(expected) != 64
            or actual != expected
        ):
            raise ValueError(
                f"{path}: prompt contract drift for {name}; "
                f"expected {expected}, got {actual}"
            )


def _validate_choice_output(
    path: Path,
    expected: int,
    *,
    allow_length_truncation: bool = False,
) -> None:
    payload = _read_json_object(path)
    rows = _prompt_rows(payload, "per_sample", path, expected)
    accuracy = _finite_metric(payload, "accuracy", path, minimum=0.0, maximum=1.0)
    if any(not isinstance(row.get("correct"), bool) for row in rows):
        raise ValueError(f"{path}: every sample must record boolean correctness")
    n_correct = sum(row["correct"] for row in rows)
    if payload.get("n_correct") != n_correct or not math.isclose(
        accuracy, n_correct / expected, rel_tol=0.0, abs_tol=1e-15
    ):
        raise ValueError(f"{path}: accuracy does not match per-sample correctness")
    for key in ("n_samples", "n_expected", "n_scored"):
        if payload.get(key) != expected:
            raise ValueError(f"{path}: {key} is {payload.get(key)!r}; expected {expected}")
    if payload.get("n_error") != 0 or payload.get("incomplete") is not False:
        raise ValueError(f"{path}: evaluator recorded errors or an incomplete sample set")
    if any(not isinstance(row.get("completion"), str) for row in rows):
        raise ValueError(f"{path}: every sample must preserve its raw completion")
    if not allow_length_truncation and any(
        row.get("stop_reason") in {"max_tokens", "model_length"} for row in rows
    ):
        raise ValueError(f"{path}: quality answer was truncated before completion")


def _validate_problem_output(
    path: Path,
    expected: int,
    *,
    metric: str,
    raw_field: str,
    require_zero_errors: bool = False,
) -> None:
    payload = _read_json_object(path)
    rows = _prompt_rows(payload, "per_problem", path, expected)
    score = _finite_metric(payload, metric, path, minimum=0.0, maximum=1.0)
    correctness = "maj_correct" if metric == "maj_k_accuracy" else "correct"
    correct_count = "n_correct_maj" if metric == "maj_k_accuracy" else "n_correct"
    if any(not isinstance(row.get(correctness), bool) for row in rows):
        raise ValueError(f"{path}: every problem must record boolean correctness")
    n_correct = sum(row[correctness] for row in rows)
    if payload.get(correct_count) != n_correct or not math.isclose(
        score, n_correct / expected, rel_tol=0.0, abs_tol=1e-15
    ):
        raise ValueError(f"{path}: score does not match per-problem correctness")
    if payload.get("n_problems") != expected:
        raise ValueError(
            f"{path}: n_problems is {payload.get('n_problems')!r}; expected {expected}"
        )
    if require_zero_errors and payload.get("n_error") != 0:
        raise ValueError(f"{path}: evaluator recorded endpoint errors")
    if raw_field == "texts":
        valid_raw = (
            payload.get("maj_k") == 1
            and payload.get("total_samples") == expected
            and all(
                row.get("k") == 1
                and isinstance(row.get("texts"), list)
                and len(row["texts"]) == 1
                and isinstance(row["texts"][0], str)
                and isinstance(row.get("answers"), list)
                and len(row["answers"]) == 1
                and isinstance(row.get("finish_reasons"), list)
                and len(row["finish_reasons"]) == 1
                and row["finish_reasons"][0] in {"stop", "length"}
                for row in rows
            )
        )
    else:
        valid_raw = all(
            isinstance(row.get("text"), str)
            and row.get("finish_reason") in {"stop", "length"}
            for row in rows
        )
    if not valid_raw:
        raise ValueError(f"{path}: every problem must preserve raw response field {raw_field!r}")
    if raw_field == "texts":
        truncated = any(row["finish_reasons"][0] == "length" for row in rows)
    else:
        truncated = any(row["finish_reason"] == "length" for row in rows)
    if truncated:
        raise ValueError(f"{path}: quality answer was truncated before completion")


def _prompt_rows(
    payload: dict[str, Any],
    key: str,
    path: Path,
    expected: int,
) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if (
        not isinstance(rows, list)
        or len(rows) != expected
        or any(not isinstance(row, dict) for row in rows)
    ):
        actual = len(rows) if isinstance(rows, list) else "invalid"
        raise ValueError(f"{path}: {key} has {actual} rows; expected {expected}")
    pairs: list[tuple[str, str]] = []
    for row in rows:
        sample_id = row.get("id")
        prompt_sha = row.get("prompt_sha")
        if sample_id is None or not isinstance(prompt_sha, str) or not prompt_sha:
            raise ValueError(f"{path}: every result row needs id and prompt_sha")
        pairs.append((str(sample_id), prompt_sha))
    if len({sample_id for sample_id, _ in pairs}) != expected:
        raise ValueError(f"{path}: result IDs are not unique")
    encoded = json.dumps(sorted(pairs), ensure_ascii=False, separators=(",", ":"))
    expected_sha = hashlib.sha256(encoded.encode()).hexdigest()
    if payload.get("dataset_sha256") != expected_sha:
        raise ValueError(f"{path}: dataset_sha256 does not match result prompt hashes")
    return rows


def _validate_ppl_output(pass_dir: Path, expected: int) -> None:
    summary_path = pass_dir / "ppl_summary.json"
    result_path = pass_dir / "ppl_results.jsonl"
    summary = _read_json_object(summary_path)
    if summary.get("num_records") != expected:
        raise ValueError(
            f"{summary_path}: num_records is {summary.get('num_records')!r}; "
            f"expected {expected}"
        )
    _finite_metric(summary, "ppl", summary_path, positive=True)
    _finite_metric(summary, "mean_record_ppl", summary_path, positive=True)
    _finite_metric(summary, "neg_log_likelihood", summary_path)
    num_tokens = summary.get("num_tokens")
    if not isinstance(num_tokens, int) or num_tokens < 1:
        raise ValueError(f"{summary_path}: num_tokens must be positive")

    if not result_path.is_file():
        raise ValueError(f"run is incomplete; missing {result_path}")
    try:
        rows = [
            json.loads(line)
            for line in result_path.read_text().splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read PPL results {result_path}: {error}") from error
    if len(rows) != expected or any(not isinstance(row, dict) for row in rows):
        raise ValueError(
            f"{result_path}: contains {len(rows)} records; expected {expected}"
        )
    if len({str(row.get("id")) for row in rows}) != expected:
        raise ValueError(f"{result_path}: PPL record IDs are not unique")

    row_tokens = 0
    row_nll = 0.0
    row_ppls: list[float] = []
    for row in rows:
        count = row.get("num_tokens")
        values = row.get("token_logprobs")
        if (
            not isinstance(count, int)
            or count < 1
            or not isinstance(values, list)
            or len(values) != count
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in values
            )
        ):
            raise ValueError(f"{result_path}: invalid token logprobs for record {row.get('id')}")
        calculated_nll = -sum(float(value) for value in values)
        record_nll = _finite_metric(row, "neg_log_likelihood", result_path)
        record_ppl = _finite_metric(row, "ppl", result_path, positive=True)
        if not math.isclose(
            record_nll, calculated_nll, rel_tol=1e-12, abs_tol=1e-9
        ) or not math.isclose(
            record_ppl,
            math.exp(record_nll / count),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError(f"{result_path}: inconsistent PPL row {row.get('id')}")
        row_tokens += count
        row_nll += record_nll
        row_ppls.append(record_ppl)
    if row_tokens != num_tokens or not math.isclose(
        row_nll,
        float(summary["neg_log_likelihood"]),
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(f"{summary_path}: aggregate does not match PPL result rows")
    if not math.isclose(
        float(summary["ppl"]),
        math.exp(row_nll / row_tokens),
        rel_tol=1e-12,
        abs_tol=1e-12,
    ) or not math.isclose(
        float(summary["mean_record_ppl"]),
        sum(row_ppls) / len(row_ppls),
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError(f"{summary_path}: PPL metrics do not match result rows")


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"run is incomplete; missing {path}")
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read evaluator result {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"evaluator result is not a JSON object: {path}")
    return payload


def _finite_metric(
    payload: dict[str, Any],
    key: str,
    path: Path,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    positive: bool = False,
) -> float:
    value = payload.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{path}: metric {key} must be finite")
    result = float(value)
    if positive and result <= 0:
        raise ValueError(f"{path}: metric {key} must be positive")
    if minimum is not None and result < minimum:
        raise ValueError(f"{path}: metric {key} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{path}: metric {key} must be at most {maximum}")
    return result


def _validate_summary(
    summary: dict[str, Any],
    suites: list[str] | tuple[str, ...],
    passes: int,
) -> None:
    selected = {
        "ppl": ("ppl",),
        "mmlu_pro": ("mmlu",),
        "gpqa_diamond": ("gpqa_greedy", "gpqa_sampled", "gpqa_ranked"),
        "aime": ("aime",),
        "gsm8k": ("gsm8k",),
    }
    arms = summary.get("arms")
    if not isinstance(arms, list) or not arms:
        raise ValueError("quality summary contains no arms")
    for arm in arms:
        metrics = arm.get("metrics") if isinstance(arm, dict) else None
        if not isinstance(metrics, dict):
            raise ValueError("quality summary arm has no metrics")
        for suite in suites:
            for name in selected[suite]:
                metric = metrics.get(name)
                if not isinstance(metric, dict) or metric.get("n") != passes:
                    raise ValueError(
                        f"quality summary metric {name} does not contain {passes} passes"
                    )
                _finite_metric(metric, "mean", Path("summary.json"), positive=name == "ppl")
                _finite_metric(metric, "stdev", Path("summary.json"), minimum=0.0)
        if set(suites) - {"ppl"}:
            metric = metrics.get("overall_score")
            if not isinstance(metric, dict) or metric.get("n") != passes:
                raise ValueError(
                    "quality summary overall_score does not contain "
                    f"{passes} passes"
                )
            overall_mean = _finite_metric(
                metric,
                "mean",
                Path("summary.json"),
                minimum=0.0,
                maximum=1.0,
            )
            _finite_metric(metric, "stdev", Path("summary.json"), minimum=0.0)
            overall = arm.get("overall_score")
            if not isinstance(overall, dict):
                raise ValueError("quality summary arm has no overall score counts")
            correct = overall.get("correct")
            total = overall.get("total")
            score = overall.get("score")
            if (
                not isinstance(correct, int)
                or isinstance(correct, bool)
                or not isinstance(total, int)
                or isinstance(total, bool)
                or total < 1
                or not 0 <= correct <= total
                or not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isclose(
                    float(score),
                    correct / total,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
                or not math.isclose(
                    overall_mean,
                    correct / total,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
            ):
                raise ValueError("quality summary overall score is inconsistent")


def _tokenizer_sha256s(manifest: dict[str, Any], root: Path) -> dict[str, str]:
    identity = manifest.get("artifact_identity")
    if not isinstance(identity, dict):
        raise ValueError(f"run lacks tokenizer identity: {root / 'run.json'}")
    files = identity.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"run lacks tokenizer identity: {root / 'run.json'}")
    names = (
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
        "tokenizer/chat_template.jinja",
        "tokenizer/config.json",
    )
    values = {
        name: entry.get("sha256")
        for name in names
        if isinstance((entry := files.get(name)), dict)
        and isinstance(entry.get("sha256"), str)
    }
    if "tokenizer/tokenizer.json" not in values or not any(
        name in values
        for name in ("tokenizer/tokenizer_config.json", "tokenizer/chat_template.jinja")
    ):
        raise ValueError(f"run lacks tokenizer identity: {root / 'run.json'}")
    return values


def _compare_contracts(baseline: Path, candidate: Path) -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    for root in (baseline, candidate):
        root = root.expanduser().resolve()
        path = root / "run.json"
        if not path.is_file():
            raise ValueError(f"run is incomplete; missing {path}")
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError(f"run manifest is not a JSON object: {path}")
        if value.get("status") != "completed" or value.get("evaluation_valid") is not True:
            raise ValueError(
                f"run is not eligible for comparison: {path} "
                f"has status {value.get('status')!r} and "
                f"evaluation_valid={value.get('evaluation_valid')!r}"
            )
        if value.get("failures"):
            raise ValueError(f"run records evaluator failures: {path}")
        if not (root / "summary.json").is_file():
            raise ValueError(f"run is incomplete; missing {root / 'summary.json'}")
        _validate_run_outputs(root, value)
        _validate_summary(
            _read_json_object(root / "summary.json"),
            value["suites"],
            value["passes"],
        )
        manifests.append(value)

    baseline_manifest, candidate_manifest = manifests
    compared = {
        "profile": (
            baseline_manifest.get("profile"),
            candidate_manifest.get("profile"),
        ),
        "profile_settings": (
            baseline_manifest.get("profile_settings"),
            candidate_manifest.get("profile_settings"),
        ),
        "passes": (
            baseline_manifest.get("passes"),
            candidate_manifest.get("passes"),
        ),
        "suites": (
            sorted(baseline_manifest.get("suites") or []),
            sorted(candidate_manifest.get("suites") or []),
        ),
        "head_modes": (
            baseline_manifest.get("head_modes"),
            candidate_manifest.get("head_modes"),
        ),
        "prompt_formats": (
            baseline_manifest.get("prompt_formats"),
            candidate_manifest.get("prompt_formats"),
        ),
        "host_identity": (
            baseline_manifest.get("host_identity"),
            candidate_manifest.get("host_identity"),
        ),
        "public_correctness_probe": (
            _public_probe_contract(baseline_manifest, baseline),
            _public_probe_contract(candidate_manifest, candidate),
        ),
        "ppl_sha256": (
            (baseline_manifest.get("ppl_manifest") or {}).get("sha256"),
            (candidate_manifest.get("ppl_manifest") or {}).get("sha256"),
        ),
        "evaluator_provenance": (
            baseline_manifest.get("evaluator_provenance"),
            candidate_manifest.get("evaluator_provenance"),
        ),
        "tokenizer_sha256s": (
            _tokenizer_sha256s(baseline_manifest, baseline),
            _tokenizer_sha256s(candidate_manifest, candidate),
        ),
        "tokenizer_stop_token_ids": (
            baseline_manifest.get("tokenizer_stop_token_ids"),
            candidate_manifest.get("tokenizer_stop_token_ids"),
        ),
    }
    mismatches = {
        name: {"baseline": values[0], "candidate": values[1]}
        for name, values in compared.items()
        if values[0] != values[1]
    }
    if mismatches:
        details = ", ".join(sorted(mismatches))
        raise ValueError(f"runs are not comparable; mismatched {details}")
    return {"validated": True, "fields": sorted(compared)}


def _public_probe_contract(
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    probe = manifest.get("local_public_correctness_probe")
    if not isinstance(probe, dict) or not isinstance(probe.get("available"), bool):
        raise ValueError(
            f"run lacks valid local public correctness probe: {root / 'run.json'}"
        )
    if not probe["available"]:
        return {"available": False}
    required = {
        "fixture_sha256": str,
        "prompt_token_count": int,
        "expected_token": int,
        "actual_token": int,
    }
    if any(
        not isinstance(probe.get(name), expected_type)
        or isinstance(probe.get(name), bool)
        for name, expected_type in required.items()
    ) or (
        not probe["fixture_sha256"]
        or probe["prompt_token_count"] < 1
        or probe["expected_token"] < 0
        or probe["actual_token"] < 0
        or not isinstance(probe.get("matches_m5_fixture"), bool)
        or probe["matches_m5_fixture"]
        != (probe["actual_token"] == probe["expected_token"])
    ):
        raise ValueError(
            f"run has invalid local public correctness probe: {root / 'run.json'}"
        )
    return {
        "available": True,
        "fixture_sha256": probe["fixture_sha256"],
        "prompt_token_count": probe["prompt_token_count"],
        "expected_token": probe["expected_token"],
    }


def _evaluation_provenance() -> dict[str, Any]:
    root = _upstream_dir().parent
    candidates = [
        root / "pyproject.toml",
        root / "uv.lock",
        *sorted((root / "laguna_quality").glob("*.py")),
        *sorted((root / "manifests").glob("*.json")),
        *sorted((root / "upstream").glob("*.py")),
        root / "upstream" / "PROVENANCE.json",
        root / "bridge" / "Package.swift",
        root / "bridge" / "Package.resolved",
        *sorted((root / "bridge" / "Sources").rglob("*")),
    ]
    files: dict[str, str] = {}
    combined = hashlib.sha256()
    for path in candidates:
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[relative] = digest
        combined.update(relative.encode())
        combined.update(b"\0")
        combined.update(digest.encode())
        combined.update(b"\n")

    source_path = root / "upstream" / "PROVENANCE.json"
    source = json.loads(source_path.read_text())
    imports = [
        {
            key: entry.get(key)
            for key in ("file", "source_commit", "source_last_changed_commit", "source_path")
            if entry.get(key) is not None
        }
        for entry in source.get("imports", [])
    ]
    return {
        "sha256": combined.hexdigest(),
        "files": files,
        "source_repository": source.get("source_repository"),
        "imports": imports,
    }


def _response_rows(run_dir: Path) -> dict[tuple[str, str], str]:
    rows: dict[tuple[str, str], str] = {}
    for path in sorted(run_dir.glob("pass_*/*.json")):
        if path.name.endswith("summary.json"):
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        relative = str(path.relative_to(run_dir))
        samples = data.get("per_sample") if isinstance(data, dict) else None
        if isinstance(samples, list):
            for sample in samples:
                if isinstance(sample, dict) and isinstance(sample.get("completion"), str):
                    rows[(relative, str(sample.get("id")))] = sample["completion"]
        problems = data.get("per_problem") if isinstance(data, dict) else None
        if isinstance(problems, list):
            for problem in problems:
                if not isinstance(problem, dict):
                    continue
                if isinstance(problem.get("text"), str):
                    rows[(relative, str(problem.get("id")))] = problem["text"]
                elif isinstance(problem.get("texts"), list):
                    rows[(relative, str(problem.get("id")))] = json.dumps(
                        problem["texts"], ensure_ascii=False
                    )
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _timestamp(value: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))
