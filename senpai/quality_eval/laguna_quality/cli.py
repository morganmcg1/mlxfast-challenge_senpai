from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .artifact import (
    Artifact,
    ArtifactError,
    ensure_bridge,
    ensure_metallib,
    ensure_weights,
    resolve_artifact,
)
from .bridge import BridgeError, BridgeProcess
from .runner import (
    ALL_SUITES,
    PROFILES,
    RunOptions,
    check_prompt_sets,
    compare_runs,
    run_evaluations,
    summarize_runs,
)
from .run_lock import ModelRunLock, ModelRunLockError
from .server import LagunaAPI, QualityHTTPServer, RequestJournal
from .tokenizer import LagunaTokenizer, TokenizerError


def _artifact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("artifact", help="prepared challenge checkout or quality artifact")
    parser.add_argument("--weights", help="override transformed weights directory")
    parser.add_argument("--reference", help="override the pinned reference checkpoint")
    parser.add_argument("--tokenizer", help="override Laguna tokenizer directory")
    parser.add_argument("--bridge", help="override laguna-quality-bridge executable")
    parser.add_argument("--metallib", help="override mlx.metallib path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quality-eval",
        description="Run local quality evaluations against a modified Laguna checkout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="resolve and validate a prepared checkout or artifact"
    )
    _artifact_arguments(inspect_parser)

    serve_parser = subparsers.add_parser(
        "serve", help="serve the modified model through the evaluator API"
    )
    _artifact_arguments(serve_parser)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=900.0,
        help="seconds to wait while the bridge loads the model (default: 900)",
    )
    serve_parser.add_argument(
        "--request-timeout",
        type=float,
        default=None,
        help="optional per-generation bridge timeout in seconds",
    )
    serve_parser.add_argument(
        "--request-log",
        type=Path,
        help="append every HTTP request and response to this JSONL file",
    )
    serve_parser.add_argument(
        "--head-mode",
        choices=("full", "ranked"),
        default="full",
        help="full supports sampling/PPL; ranked tests submitted greedy behavior",
    )
    serve_parser.add_argument(
        "--no-build",
        action="store_true",
        help="do not refresh weights or incrementally rebuild the bridge/metallib",
    )

    run_parser = subparsers.add_parser(
        "run", help="run a persisted Laguna quality panel"
    )
    _artifact_arguments(run_parser)
    run_parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="smoke",
        help="smoke checks plumbing; quick is the routine gate",
    )
    run_parser.add_argument(
        "--passes",
        type=int,
        help="complete passes (default: 1)",
    )
    run_parser.add_argument(
        "--suite",
        action="append",
        choices=["all", *ALL_SUITES],
        help="suite to run; repeat to select several (default: all)",
    )
    run_parser.add_argument(
        "--output",
        type=Path,
        help="new result directory (default: quality-results/<timestamp>-<profile>)",
    )
    run_parser.add_argument(
        "--ppl-dataset",
        type=Path,
        help="optional Laguna-tokenized PPL JSON/JSONL manifest",
    )
    run_parser.add_argument("--startup-timeout", type=float, default=900.0)
    run_parser.add_argument("--request-timeout", type=float)
    run_parser.add_argument(
        "--keep-going",
        action="store_true",
        help="continue remaining evaluators after an evaluator failure",
    )
    run_parser.add_argument(
        "--no-build",
        action="store_true",
        help="do not refresh weights or incrementally rebuild the bridge/metallib",
    )
    run_parser.add_argument(
        "--baseline",
        type=Path,
        help="compare this run with a matched baseline and exit 3 if the gate fails",
    )
    run_parser.add_argument(
        "--weave-project",
        help="optional ENTITY/PROJECT for online W&B Weave logging",
    )
    run_parser.add_argument(
        "--change-label",
        help="short description of the model change being evaluated",
    )
    run_parser.add_argument(
        "--attribute",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="additional Weave metadata; repeat for multiple values",
    )

    summarize_parser = subparsers.add_parser(
        "summarize", help="summarize one or more completed result directories"
    )
    summarize_parser.add_argument("run_dirs", nargs="+", type=Path)
    summarize_parser.add_argument("--output", type=Path)

    compare_parser = subparsers.add_parser(
        "compare", help="compare matched baseline and candidate result directories"
    )
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    compare_parser.add_argument("--output", type=Path)
    compare_parser.add_argument(
        "--skip-prompt-check",
        action="store_true",
        help="skip downstream prompt-hash validation",
    )
    compare_parser.add_argument(
        "--report-only",
        action="store_true",
        help="report observed regressions without returning exit status 3",
    )

    prompt_parser = subparsers.add_parser(
        "check-prompts", help="verify frozen downstream prompts across runs"
    )
    prompt_parser.add_argument("run_dirs", nargs="+", type=Path)
    return parser


def _resolve(args: argparse.Namespace, *, build: bool) -> Artifact:
    bridge = args.bridge
    root = Path(args.artifact).expanduser().resolve()
    is_checkout = (root / "Package.swift").is_file() and (
        root / "Sources" / "MLXFastModel"
    ).is_dir()
    weights = args.weights
    if weights is None and is_checkout:
        weights = str(
            ensure_weights(root, build=build, reference=args.reference)
        )
    metallib = args.metallib
    if bridge is None and is_checkout:
        # Incremental builds are cheap; --no-build instead validates the exact
        # source fingerprint recorded beside the existing executable.
        bridge = str(ensure_bridge(root, build=build))
    if metallib is None and is_checkout:
        metallib = str(ensure_metallib(root, build=build))
    return resolve_artifact(
        args.artifact,
        weights=weights,
        tokenizer=args.tokenizer,
        bridge=bridge,
        metallib=metallib,
    )


def _serve(args: argparse.Namespace) -> int:
    label = str(Path(args.artifact).expanduser().resolve())
    with ModelRunLock(label):
        artifact = _resolve(args, build=not args.no_build)
        _require_metallib(artifact)
        return _serve_resolved(args, artifact)


def _serve_resolved(args: argparse.Namespace, artifact: Artifact) -> int:
    tokenizer = LagunaTokenizer(artifact.tokenizer)
    journal = RequestJournal(args.request_log.resolve()) if args.request_log else None
    bridge = BridgeProcess(
        artifact,
        startup_timeout=args.startup_timeout,
        full_logits=args.head_mode == "full",
    )
    try:
        ready = bridge.start()
        api = LagunaAPI(bridge, tokenizer, request_timeout=args.request_timeout)
        server = QualityHTTPServer((args.host, args.port), api, journal=journal)
        port = server.server_address[1]
        print(
            json.dumps(
                {
                    "event": "ready",
                    "base_url": f"http://{args.host}:{port}",
                    "model": api.model,
                    "artifact": artifact.as_dict(),
                    "bridge": ready,
                    "request_log": str(journal.path) if journal else None,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        def stop_server(*_: Any) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop_server)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        bridge.close()
    return 0


def _run(args: argparse.Namespace) -> int:
    label = str(Path(args.artifact).expanduser().resolve())
    with ModelRunLock(label):
        preparation_started = time.monotonic()
        artifact = _resolve(args, build=not args.no_build)
        _require_metallib(artifact)
        return _run_resolved(
            args,
            artifact,
            preparation_wall_s=time.monotonic() - preparation_started,
        )


def _run_resolved(
    args: argparse.Namespace,
    artifact: Artifact,
    *,
    preparation_wall_s: float = 0.0,
) -> int:
    selected = ALL_SUITES if not args.suite or "all" in args.suite else args.suite
    suites = tuple(dict.fromkeys(selected))
    passes = args.passes if args.passes is not None else 1
    output = args.output.expanduser() if args.output else Path("quality-results") / (
        time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{args.profile}"
    )
    attributes = tuple(_parse_attribute(value) for value in args.attribute)
    result = run_evaluations(
        artifact,
        RunOptions(
            output=output,
            profile=args.profile,
            passes=passes,
            suites=suites,
            request_timeout=args.request_timeout,
            startup_timeout=args.startup_timeout,
            keep_going=args.keep_going,
            ppl_dataset=args.ppl_dataset,
            preparation_wall_s=preparation_wall_s,
            weave_project=args.weave_project,
            change_label=args.change_label,
            attributes=attributes,
        ),
    )
    if result["status"] != "completed":
        return 1
    if args.baseline is None:
        return 0
    comparison = compare_runs(args.baseline, output)
    comparison_path = output.expanduser().resolve() / "comparison.json"
    _emit_json(comparison, comparison_path)
    _print_comparison(comparison)
    return (
        0
        if comparison["decision"]["local_retention_gate_passed"] is True
        else 3
    )


def _parse_attribute(value: str) -> tuple[str, str]:
    key, separator, attribute_value = value.partition("=")
    key = key.strip()
    if not separator or not key:
        raise ValueError(f"invalid --attribute {value!r}; expected KEY=VALUE")
    return key, attribute_value


def _require_metallib(artifact: Artifact) -> None:
    if artifact.metallib is None:
        raise ArtifactError(
            "quality artifacts must include mlx.metallib; "
            "set it in quality-artifact.json or pass --metallib"
        )


def _emit_json(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text)
        print(f"quality-eval: wrote {output}", file=sys.stderr)
    print(text, end="")


def _print_comparison(comparison: dict[str, Any]) -> None:
    print("[quality-eval] gate metrics")
    metrics = comparison.get("metrics") or {}
    overall = metrics.get("overall_score") or {}
    if overall.get("available"):
        overall_status = (
            "PASS"
            if overall.get("gate_passed") is True
            else "FAIL"
            if overall.get("gate_passed") is False
            else "N/A"
        )
        print(
            "[quality-eval]   Overall downstream: "
            f"baseline={overall.get('baseline_correct')}/{overall.get('baseline_total')} "
            f"candidate={overall.get('candidate_correct')}/{overall.get('candidate_total')} "
            f"required={overall.get('required_correct')}/{overall.get('baseline_total')} "
            f"{overall_status}"
        )
    ppl = metrics.get("ppl") or {}
    if ppl.get("available"):
        print(
            "[quality-eval]   PPL: "
            f"baseline={float(ppl['baseline']):.6f} "
            f"candidate={float(ppl['candidate']):.6f} "
            f"maximum={float(ppl['threshold']):.6f} "
            f"{'PASS' if ppl.get('gate_passed') else 'FAIL'}"
        )
    decision = comparison["decision"]
    behavior = decision.get("behavior_response_passed")
    if behavior is not None:
        ranked = comparison["response_identity"]["ranked_gpqa"]
        print(
            "[quality-eval]   Ranked GPQA behavior: "
            f"{ranked['matched']}/{ranked['total']} matched; "
            f"required={ranked['required_matches']} "
            f"{'PASS' if behavior else 'FAIL'}"
        )
    probe = decision.get("public_probe_passed")
    if probe is not None:
        print(
            "[quality-eval]   Public first-token probe: "
            f"{'PASS' if probe else 'FAIL'}"
        )
    passed = decision.get("local_retention_gate_passed") is True
    print(f"[quality-eval] QUALITY GATE: {'PASS' if passed else 'FAIL'}")


def main(argv: list[str] | None = None) -> int:
    def interrupt_on_termination(*_: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt_on_termination)
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(_resolve(args, build=False).as_dict(), indent=2))
            return 0
        if args.command == "serve":
            return _serve(args)
        if args.command == "run":
            return _run(args)
        if args.command == "summarize":
            _emit_json(summarize_runs(args.run_dirs), args.output)
            return 0
        if args.command == "compare":
            comparison = compare_runs(
                args.baseline,
                args.candidate,
                check_prompts=not args.skip_prompt_check,
            )
            output = (
                args.output
                if args.output is not None
                else args.candidate.expanduser().resolve() / "comparison.json"
            )
            _emit_json(comparison, output)
            _print_comparison(comparison)
            gate_passed = comparison["decision"]["local_retention_gate_passed"]
            return 3 if gate_passed is not True and not args.report_only else 0
        if args.command == "check-prompts":
            check_prompt_sets(args.run_dirs)
            return 0
        raise AssertionError(f"unhandled command {args.command}")
    except subprocess.CalledProcessError as error:
        print(
            f"quality-eval: command failed with exit status {error.returncode}",
            file=sys.stderr,
        )
        return 1
    except (
        ArtifactError,
        BridgeError,
        ModelRunLockError,
        TokenizerError,
        ValueError,
        OSError,
    ) as error:
        print(f"quality-eval: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("quality-eval: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
