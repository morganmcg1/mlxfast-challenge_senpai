"""AIME maj@k evaluator for an OpenAI-compatible local endpoint.

The scoring mirrors inspect_evals AIME conventions: extract the last boxed
integer, score integer equality, and majority-vote k samples. Output includes
per-problem raw completions, extracted answers, maj@k correctness, and continuous
pass rate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Dataset loading (no `datasets` dep — HF datasets-server /rows API)
# --------------------------------------------------------------------------- #
# AIME is 30 problems/year, so one /rows page (length<=100) holds a whole split.
AIME_REGISTRY: dict[str, dict[str, str]] = {
    "2024": {
        "dataset": "Maxwell-Jia/AIME_2024",
        "config": "default",
        "split": "train",
        "id_col": "ID",
        "problem_col": "Problem",
        "answer_col": "Answer",
    },
    # opencompass/AIME2025 ships two configs (AIME2025-I / -II), 15 problems each.
    # AIME2025-I has been server-side 500-down on the HF datasets-server since at
    # least PR #535; the canonical 15 Part-I problems are recovered from the
    # yentinglin/aime_2025 mirror. Validity (ubel #567 cross-check): the mirror's
    # Part-I answers are byte-identical to MathArena/aime_2025_I, and its Part-II
    # answers are byte-identical to the (working) canonical opencompass AIME2025-II
    # below -> the mirror faithfully reproduces the canonical 2025 set. Original
    # broken source kept on record: opencompass/AIME2025 / AIME2025-I / test.
    "2025-I": {
        "dataset": "yentinglin/aime_2025",
        "config": "part1",
        "split": "train",
        "id_col": "",
        "problem_col": "problem",
        "answer_col": "answer",
    },
    "2025-II": {
        "dataset": "opencompass/AIME2025",
        "config": "AIME2025-II",
        "split": "test",
        "id_col": "",
        "problem_col": "question",
        "answer_col": "answer",
    },
    # Full AIME-2025 (parts I+II, 30 problems) via the SAME mirror the canonical
    # inspect_evals `aime2025` task uses (math-ai/aime25, split=test). opencompass's
    # per-part configs (AIME2025-I above) are persistently server-side 500-down on the
    # datasets-server /rows API; this single reachable config restores the full set, so
    # `--years 2024,2025` yields the canonical 60 = 2024(30) + 2025(30).
    "2025": {
        "dataset": "math-ai/aime25",
        "config": "default",
        "split": "test",
        "id_col": "id",
        "problem_col": "problem",
        "answer_col": "answer",
    },
    # The curated AIMO-validation AIME set: 90 problems = AIME 2022 + 2023 + 2024
    # (30 each, I+II). One reachable dataset that triples n for a power-bearing
    # Wilson-CI comparison (PR #535 matched-conc arm); opencompass AIME2025-I is
    # server-side 500-down, so 2022 substitutes to reach n=90 with 2023/2024 present.
    # `url_col` lets load_aime tag each problem with its real contest year.
    "aimo-2022-2024": {
        "dataset": "AI-MO/aimo-validation-aime",
        "config": "default",
        "split": "train",
        "id_col": "id",
        "problem_col": "problem",
        "answer_col": "answer",
        "url_col": "url",
    },
}


def _rows_api(dataset: str, config: str, split: str, length: int = 100) -> list[dict[str, Any]]:
    url = (
        "https://datasets-server.huggingface.co/rows"
        f"?dataset={urllib.parse.quote(dataset)}&config={urllib.parse.quote(config)}"
        f"&split={urllib.parse.quote(split)}&offset=0&length={length}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "senpai-aime-eval"})
    tok = os.environ.get("HF_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    # The datasets-server intermittently returns 429/500/503; retry with backoff so a
    # transient blip at run start doesn't waste a served GPU slot.
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            return [row["row"] for row in data.get("rows", [])]
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503):
                raise
            last_exc = exc
        except urllib.error.URLError as exc:
            last_exc = exc
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"datasets-server unreachable after retries for {dataset}/{config}/{split}") from last_exc


def load_aime(years: list[str], limit: int | None = None) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for year in years:
        spec = AIME_REGISTRY[year]
        rows = _rows_api(spec["dataset"], spec["config"], spec["split"])
        url_col = spec.get("url_col")
        for i, row in enumerate(rows):
            ans_raw = row[spec["answer_col"]]
            ans = _to_int(ans_raw)
            if ans is None:
                continue  # AIME answers are integers 0-999; skip anything malformed
            # Multi-year datasets (e.g. AIMO-validation) carry the real contest year
            # in a url; tag each problem with it so per-year breakdowns stay honest.
            row_year = year
            if url_col:
                m = re.search(r"(\d{4})_AIME", str(row.get(url_col, "")))
                if m:
                    row_year = m.group(1)
            pid = f"{row_year}-{row[spec['id_col']]}" if spec["id_col"] else f"{year}-{i+1:02d}"
            problems.append(
                {
                    "id": pid,
                    "year": row_year,
                    "problem": str(row[spec["problem_col"]]),
                    "answer": ans,
                }
            )
    if limit is not None:
        problems = problems[:limit]
    return problems


# --------------------------------------------------------------------------- #
# Answer extraction (mirrors inspect_evals AIME: last \boxed{} integer)
# --------------------------------------------------------------------------- #
_BOXED_RE = re.compile(r"\\boxed\s*\{")
_INT_RE = re.compile(r"-?\d[\d,]*")


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip().replace(",", "")
    m = re.search(r"-?\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def _extract_boxed_spans(text: str) -> list[str]:
    """Return the brace-balanced contents of every ``\\boxed{...}`` in order."""
    spans: list[str] = []
    for m in _BOXED_RE.finditer(text):
        i = m.end()  # position just after the '{'
        depth = 1
        out: list[str] = []
        while i < len(text) and depth > 0:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            out.append(c)
            i += 1
        spans.append("".join(out))
    return spans


def extract_answer(text: str) -> int | None:
    """AIME integer answer from a completion.

    Priority: the LAST ``\\boxed{...}`` that contains an integer (the final answer
    after any thinking channel); else the last ``0-999``-range integer token in the
    text. Returns ``None`` when nothing parses (counts as wrong, never crashes).
    """
    if not text:
        return None
    for span in reversed(_extract_boxed_spans(text)):
        val = _to_int(span)
        if val is not None:
            return val
    # Fallback: last integer in [0, 999] (AIME answer range) anywhere in the text.
    last: int | None = None
    for m in _INT_RE.finditer(text):
        v = _to_int(m.group(0))
        if v is not None and 0 <= v <= 999:
            last = v
    return last


def majority_vote(answers: list[int | None]) -> tuple[int | None, dict[str, int]]:
    """Most common non-None answer; deterministic tie-break by smallest value."""
    valid = [a for a in answers if a is not None]
    counts = Counter(valid)
    if not counts:
        return None, {}
    top = max(counts.values())
    winner = min(a for a, c in counts.items() if c == top)
    return winner, {str(k): v for k, v in counts.items()}


# --------------------------------------------------------------------------- #
# Prompting + endpoint
# --------------------------------------------------------------------------- #
AIME_INSTRUCTION = (
    "Please reason step by step to solve the problem, and put your final answer "
    "(a single integer between 0 and 999) within \\boxed{}."
)


def build_messages(problem: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": f"{problem}\n\n{AIME_INSTRUCTION}"}]


def prompt_sha256(messages: list[dict[str, str]], gold: int) -> str:
    """Hash the exact endpoint messages together with the scoring gold."""
    payload = json.dumps(
        {"messages": messages, "gold": gold},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dataset_sha256(pairs: list[tuple[str, str]]) -> str:
    """Order-independent aggregate of the evaluated ``(id, prompt_sha)`` set."""
    payload = json.dumps(
        sorted(pairs),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chat_completion(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    n: int,
    temperature: float,
    top_p: float,
    top_k: int,
    max_tokens: int,
    seed: int,
    enable_thinking: bool,
    timeout_s: int,
    min_tokens: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "n": n,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": False,
        # OpenAI-compatible extension used by the local Laguna adapter.
        "top_k": top_k,
    }
    if min_tokens is not None:
        # Endpoint extension: forces >= min_tokens before EOS may be emitted.
        payload["min_tokens"] = min_tokens
    if enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Retry transient transport failures with the same seeded request. HTTP status
    # failures are endpoint errors and are surfaced immediately.
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
            last_exc = exc
            if attempt == 3:
                raise
            time.sleep(2.0 * (attempt + 1))
    raise last_exc  # unreachable; satisfies type-checkers


def eval_endpoint(
    base_url: str,
    model: str,
    problems: list[dict[str, Any]],
    *,
    k: int,
    temperature: float,
    top_p: float,
    top_k: int,
    max_tokens: int,
    seed: int,
    enable_thinking: bool,
    request_timeout_s: int,
    save_text: bool = True,
    min_tokens: int | None = None,
    client_concurrency: int = 1,
) -> dict[str, Any]:
    # Dispatch order never changes the problem list or output order. The local
    # Laguna adapter serializes model execution while allowing queued HTTP clients.
    def _eval_one(idx: int, prob: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
        messages = build_messages(prob["problem"])
        prompt_sha = prompt_sha256(messages, prob["answer"])
        resp = chat_completion(
            base_url,
            model,
            messages,
            n=k,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            seed=seed,
            enable_thinking=enable_thinking,
            timeout_s=request_timeout_s,
            min_tokens=min_tokens,
        )
        texts = [c.get("message", {}).get("content") or "" for c in resp.get("choices", [])]
        finish = [c.get("finish_reason") for c in resp.get("choices", [])]
        answers = [extract_answer(t) for t in texts]
        maj, counts = majority_vote(answers)
        gold = prob["answer"]
        correct_samples = sum(1 for a in answers if a == gold)
        pass_rate = correct_samples / len(answers) if answers else 0.0
        maj_correct = maj is not None and maj == gold
        rec = {
            "id": prob["id"],
            "year": prob["year"],
            "gold": gold,
            "answers": answers,
            "answer_counts": counts,
            "maj_answer": maj,
            "maj_correct": maj_correct,
            "correct_samples": correct_samples,
            "k": len(answers),
            "pass_rate": pass_rate,
            "finish_reasons": finish,
            "sample_chars": [len(t) for t in texts],
            "prompt_sha": prompt_sha,
            **({"texts": texts} if save_text else {}),
        }
        line = (
            f"[aime] {idx+1}/{len(problems)} id={prob['id']} gold={gold} "
            f"maj={maj} ({'OK' if maj_correct else 'x'}) pass={correct_samples}/{len(answers)} "
            f"counts={counts}"
        )
        return idx, rec, line

    t0 = time.time()
    results: list[dict[str, Any] | None] = [None] * len(problems)
    if client_concurrency <= 1:
        for idx, prob in enumerate(problems):
            i, rec, line = _eval_one(idx, prob)
            results[i] = rec
            print(line, flush=True)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=client_concurrency) as ex:
            futs = {ex.submit(_eval_one, idx, prob): idx for idx, prob in enumerate(problems)}
            done = 0
            for fut in as_completed(futs):
                i, rec, line = fut.result()
                results[i] = rec
                done += 1
                print(f"{line}  [{done}/{len(problems)} returned]", flush=True)

    # Accumulate after collection. All aggregates are order-independent sums, and
    # per_problem is reassembled in problem order, so the output is identical to
    # the sequential path for any client_concurrency.
    per_problem: list[dict[str, Any]] = [r for r in results if r is not None]
    n_correct_maj = sum(int(r["maj_correct"]) for r in per_problem)
    pass_rates = [r["pass_rate"] for r in per_problem]
    extract_fail = sum(1 for r in per_problem for a in r["answers"] if a is None)
    total_samples = sum(r["k"] for r in per_problem)
    n = len(problems)
    prompt_pairs = [(str(r["id"]), str(r["prompt_sha"])) for r in per_problem]
    return {
        "n_problems": n,
        "dataset_sha256": dataset_sha256(prompt_pairs),
        "maj_k": k,
        "maj_k_accuracy": n_correct_maj / n if n else 0.0,
        "n_correct_maj": n_correct_maj,
        "mean_pass_rate": sum(pass_rates) / n if n else 0.0,
        "extract_fail_rate": extract_fail / total_samples if total_samples else 0.0,
        "total_samples": total_samples,
        "wall_s": time.time() - t0,
        "client_concurrency": client_concurrency,
        "per_problem": per_problem,
    }


# --------------------------------------------------------------------------- #
# Self-test (no GPU): prove the extractor is sound before any model run.
# --------------------------------------------------------------------------- #
def self_test() -> int:
    cases: list[tuple[str, int | None]] = [
        ("After working it out, the answer is \\boxed{42}.", 42),
        ("<|think|>messy 17 then 200<|/think|> Final: \\boxed{073}", 73),
        ("two boxes \\boxed{1} ... and later \\boxed{ 204 }", 204),
        ("comma form \\boxed{1,024}", 1024),  # extractor strips commas (then out of range, see note)
        ("nested \\boxed{\\frac{3}{1}=3 so \\boxed{3}}", 3),
        ("no box, the value is 250 at the end", 250),
        ("garbage with no integer at all", None),
    ]
    ok = True
    for text, want in cases:
        got = extract_answer(text)
        # the comma case parses to 1024 which is out of AIME range only for the
        # *fallback*; a boxed value is taken verbatim, so 1024 is expected here.
        flag = "ok" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"[self-test] {flag}: extract({text!r}) = {got} (want {want})")
    maj, counts = majority_vote([5, 5, 7, None, 5])
    if maj != 5:
        ok = False
        print(f"[self-test] FAIL majority_vote -> {maj} (want 5)")
    else:
        print(f"[self-test] ok: majority_vote -> {maj} counts={counts}")
    messages = build_messages("What is 1+1?")
    sha = prompt_sha256(messages, 2)
    if sha != prompt_sha256(messages, 2) or sha == prompt_sha256(messages, 3):
        ok = False
        print("[self-test] FAIL prompt hash stability/gold sensitivity")
    else:
        print("[self-test] ok: prompt hash is stable and gold-sensitive")
    print("[self-test] PASS" if ok else "[self-test] FAILURES PRESENT")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="run the extractor self-test and exit (no GPU)")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint root, without /v1")
    ap.add_argument("--model", default="laguna-xs-2.1", help="served model name")
    ap.add_argument("--years", default="2024", help="comma list from {2024,2025-I,2025-II}")
    ap.add_argument("--k", type=int, default=8, help="maj@k samples per problem")
    ap.add_argument("--limit", type=int, default=None, help="cap number of problems (smoke)")
    ap.add_argument(
        "--expect-count",
        type=int,
        default=None,
        help="fail unless exactly this many problems are loaded",
    )
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=64)
    ap.add_argument("--max-tokens", type=int, default=3072)
    ap.add_argument("--min-tokens", type=int, default=None,
                    help="endpoint min_tokens extension (default: unset)")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--no-thinking", action="store_true", help="disable enable_thinking chat-template kwarg")
    ap.add_argument("--client-concurrency", type=int, default=1,
                    help="number of queued endpoint requests (default: 1)")
    ap.add_argument(
        "--save-text",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="persist raw completion text per problem (default: enabled)",
    )
    ap.add_argument("--request-timeout-s", type=int, default=1200)
    ap.add_argument("--label", default=None, help="label for this model artifact")
    ap.add_argument("--out", type=Path, required=False, help="results JSON path")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.base_url:
        ap.error("--base-url is required (or use --self-test)")

    years = [y.strip() for y in args.years.split(",") if y.strip()]
    problems = load_aime(years, limit=args.limit)
    if args.expect_count is not None and len(problems) != args.expect_count:
        raise RuntimeError(
            f"AIME loaded {len(problems)} problems; expected {args.expect_count}"
        )
    if not problems:
        raise RuntimeError("AIME loaded no problems")
    print(f"[aime] loaded {len(problems)} problems from years={years}", flush=True)

    sampling = {
        "temperature": args.temperature,
        "top_p": args.top_p,
        "top_k": args.top_k,
        "max_tokens": args.max_tokens,
        "min_tokens": args.min_tokens,
        "seed": args.seed,
        "enable_thinking": not args.no_thinking,
    }
    meta = {
        "label": args.label,
        "model": args.model,
        "years": years,
        "k": args.k,
        "sampling": sampling,
        "created_at": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
    }

    def _run(base_url: str) -> dict[str, Any]:
        return eval_endpoint(
            base_url,
            args.model,
            problems,
            k=args.k,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            max_tokens=args.max_tokens,
            seed=args.seed,
            enable_thinking=not args.no_thinking,
            request_timeout_s=args.request_timeout_s,
            save_text=args.save_text,
            min_tokens=args.min_tokens,
            client_concurrency=args.client_concurrency,
        )

    meta["base_url"] = args.base_url
    result = _run(args.base_url)

    out = {**meta, **result}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=2))
        print(f"[aime] wrote {args.out}", flush=True)
    print(
        f"[aime] DONE label={args.label} maj@{args.k}={result['maj_k_accuracy']:.4f} "
        f"({result['n_correct_maj']}/{result['n_problems']}) "
        f"mean_pass_rate={result['mean_pass_rate']:.4f} "
        f"extract_fail_rate={result['extract_fail_rate']:.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
