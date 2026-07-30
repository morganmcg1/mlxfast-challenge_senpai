"""GSM8K 8-shot chain-of-thought evaluator for a local OpenAI endpoint.

The protocol mirrors lm-eval-harness conventions: deterministic train exemplars,
strict extraction from ``The answer is N.`` with a last-number fallback, and
numeric exact-match scoring. Seeded item IDs and few-shot signatures make runs
directly comparable, and raw completions are saved by default.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Dataset loading (no `datasets` dep -- HF datasets-server /rows API, paginated)
# --------------------------------------------------------------------------- #
GSM8K_DATASET = "openai/gsm8k"
GSM8K_CONFIG = "main"


def _rows_api(dataset: str, config: str, split: str, offset: int, length: int) -> dict[str, Any]:
    url = (
        "https://datasets-server.huggingface.co/rows"
        f"?dataset={urllib.parse.quote(dataset)}&config={urllib.parse.quote(config)}"
        f"&split={urllib.parse.quote(split)}&offset={offset}&length={length}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "senpai-gsm8k-eval"})
    tok = os.environ.get("HF_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as exc:  # transient datasets-server hiccup
            last_err = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"datasets-server /rows failed after retries: {last_err!r}")


def _load_split(split: str, n: int | None) -> list[dict[str, str]]:
    """Load up to ``n`` rows of a GSM8K split (paginated; /rows caps length at 100)."""
    out: list[dict[str, str]] = []
    offset = 0
    page = 100
    total = None
    while True:
        data = _rows_api(GSM8K_DATASET, GSM8K_CONFIG, split, offset, page)
        if total is None:
            total = data.get("num_rows_total")
        rows = data.get("rows", [])
        if not rows:
            break
        for row in rows:
            r = row["row"]
            out.append({"question": str(r["question"]), "answer": str(r["answer"])})
            if n is not None and len(out) >= n:
                return out
        offset += len(rows)
        if total is not None and offset >= total:
            break
    return out


def filter_by_ids(
    items: list[dict[str, Any]],
    requested_ids: list[Any],
) -> list[dict[str, Any]]:
    """Select requested IDs while preserving the dataset's existing order."""
    requested = [str(item_id) for item_id in requested_ids]
    duplicate_requests = sorted(
        item_id for item_id, count in Counter(requested).items() if count > 1
    )
    if duplicate_requests:
        raise ValueError(
            f"duplicate requested IDs: {', '.join(duplicate_requests)}"
        )

    requested_set = set(requested)
    selected: list[dict[str, Any]] = []
    found: set[str] = set()
    duplicate_items: set[str] = set()
    for item in items:
        item_id = str(item["id"])
        if item_id not in requested_set:
            continue
        if item_id in found:
            duplicate_items.add(item_id)
        else:
            selected.append(item)
        found.add(item_id)
    if duplicate_items:
        raise ValueError(
            f"duplicate dataset IDs: {', '.join(sorted(duplicate_items))}"
        )

    missing = [item_id for item_id in requested if item_id not in found]
    if missing:
        raise ValueError(f"requested IDs not found: {', '.join(missing)}")
    return selected


# --------------------------------------------------------------------------- #
# Gold + prediction answer extraction (mirrors lm-eval-harness GSM8K)
# --------------------------------------------------------------------------- #
_GOLD_RE = re.compile(r"####\s*(.+?)\s*$", re.MULTILINE)
# "The answer is N", "answer: N", "#### N" -- the strict instructed/canonical anchors.
_STRICT_RE = re.compile(
    r"(?:the\s+answer\s+is|answer\s*[:=]|####)\s*\$?\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
# Any signed number with optional thousands separators / decimal.
_NUM_RE = re.compile(r"-?[0-9][0-9,]*(?:\.[0-9]+)?")
_CALC_RE = re.compile(r"<<[^>]*>>")  # GSM8K calculator annotations in train CoT


def normalize_num(s: str) -> float | None:
    """Parse a GSM8K numeric token to a float, or None. Strips $ and thousands commas."""
    if s is None:
        return None
    t = str(s).strip().strip("$").replace(",", "").rstrip(".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        m = re.search(r"-?[0-9]+(?:\.[0-9]+)?", t)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None


def gold_answer(answer_field: str) -> float | None:
    """Gold numeric answer from a GSM8K ``answer`` field (the value after '#### ')."""
    m = _GOLD_RE.search(answer_field)
    if not m:
        return None
    return normalize_num(m.group(1))


def extract_pred(text: str) -> tuple[float | None, str]:
    """Final numeric prediction from a completion.

    Priority: the LAST strict anchor ('the answer is N' / 'answer: N' / '#### N'); else the
    LAST bare number anywhere (flexible fallback). Returns (value, mode) where mode is
    'strict' | 'flexible' | 'none'.
    """
    if not text:
        return None, "none"
    strict = list(_STRICT_RE.finditer(text))
    if strict:
        val = normalize_num(strict[-1].group(1))
        if val is not None:
            return val, "strict"
    nums = list(_NUM_RE.finditer(text))
    for m in reversed(nums):
        val = normalize_num(m.group(0))
        if val is not None:
            return val, "flexible"
    return None, "none"


def is_correct(pred: float | None, gold: float | None) -> bool:
    if pred is None or gold is None:
        return False
    return abs(pred - gold) < 1e-4


# --------------------------------------------------------------------------- #
# 8-shot CoT prompt (exemplars drawn deterministically from the train split)
# --------------------------------------------------------------------------- #
SYSTEM_INSTRUCTION = (
    "Solve the grade-school math word problems. For each question, reason step by step, "
    "then state the final answer on its own at the end as 'The answer is N.' where N is a "
    "single number."
)


def _clean_cot(answer_field: str) -> tuple[str, float | None]:
    """Turn a GSM8K train ``answer`` (CoT + '#### N') into a clean exemplar CoT.

    Strips ``<<calc>>`` annotations and the '#### N' tail, re-appends 'The answer is N.'."""
    gold = gold_answer(answer_field)
    body = _GOLD_RE.sub("", answer_field).strip()
    body = _CALC_RE.sub("", body).strip()
    if gold is not None:
        g = int(gold) if float(gold).is_integer() else gold
        body = f"{body}\nThe answer is {g}."
    return body, gold


def build_fewshot(n_shot: int, seed: int) -> tuple[list[dict[str, str]], list[str]]:
    """Deterministic n_shot exemplars from the train split. Returns (exemplars, signature)."""
    train = _load_split("train", n=max(n_shot * 4, 64))
    import random

    rng = random.Random(seed)
    idxs = list(range(len(train)))
    rng.shuffle(idxs)
    chosen = idxs[:n_shot]
    exemplars: list[dict[str, str]] = []
    sig: list[str] = []
    for i in chosen:
        cot, gold = _clean_cot(train[i]["answer"])
        exemplars.append({"question": train[i]["question"], "cot": cot})
        sig.append(f"{i}:{gold}")
    return exemplars, sig


def build_prompt(exemplars: list[dict[str, str]], question: str) -> str:
    parts = [SYSTEM_INSTRUCTION, "", "Here are some worked examples:", ""]
    for ex in exemplars:
        parts.append(f"Question: {ex['question']}")
        parts.append(f"Answer: {ex['cot']}")
        parts.append("")
    parts.append("Now solve this problem.")
    parts.append("")
    parts.append(f"Question: {question}")
    parts.append("Answer:")
    return "\n".join(parts)


def build_messages(prompt: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": prompt}]


def prompt_sha256(messages: list[dict[str, str]], gold: float | None) -> str:
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


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
def chat_completion(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
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
        "n": 1,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": False,
        "top_k": top_k,  # OpenAI-compatible endpoint extension
    }
    if min_tokens is not None:
        # Endpoint extension: forbid EOS/stop until >= min_tokens generated.
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
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        return json.loads(r.read().decode())


def eval_endpoint(
    base_url: str,
    model: str,
    problems: list[dict[str, Any]],
    exemplars: list[dict[str, str]],
    *,
    temperature: float,
    top_p: float,
    top_k: int,
    max_tokens: int,
    seed: int,
    enable_thinking: bool,
    concurrency: int,
    request_timeout_s: int,
    save_text: bool = True,
    min_tokens: int | None = None,
) -> dict[str, Any]:
    t0 = time.time()
    results: dict[int, dict[str, Any]] = {}
    prompts = [build_prompt(exemplars, prob["question"]) for prob in problems]
    prompt_hashes = [
        prompt_sha256(build_messages(prompt), prob["gold"])
        for prompt, prob in zip(prompts, problems)
    ]

    def _one(idx: int, prob: dict[str, Any]) -> dict[str, Any]:
        prompt = prompts[idx]
        resp = chat_completion(
            base_url,
            model,
            build_messages(prompt),
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            seed=seed,
            enable_thinking=enable_thinking,
            timeout_s=request_timeout_s,
            min_tokens=min_tokens,
        )
        choice = (resp.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content") or ""
        finish = choice.get("finish_reason")
        pred, mode = extract_pred(text)
        gold = prob["gold"]
        correct = is_correct(pred, gold)
        rec = {
            "id": prob["id"],
            "gold": gold,
            "pred": pred,
            "extract_mode": mode,
            "correct": correct,
            "finish_reason": finish,
            "sample_chars": len(text),
            "prompt_sha": prompt_hashes[idx],
        }
        if save_text:
            rec["text"] = text
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = {pool.submit(_one, i, p): i for i, p in enumerate(problems)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as exc:
                prob = problems[i]
                results[i] = {
                    "id": prob["id"],
                    "gold": prob["gold"],
                    "pred": None,
                    "extract_mode": "error",
                    "correct": False,
                    "finish_reason": "error",
                    "sample_chars": 0,
                    "prompt_sha": prompt_hashes[i],
                    "error": repr(exc),
                }
            done += 1
            if done % 25 == 0 or done == len(problems):
                acc = sum(1 for r in results.values() if r["correct"]) / done
                print(f"[gsm8k] {done}/{len(problems)} running_acc={acc:.4f}", flush=True)

    per_problem = [results[i] for i in range(len(problems))]
    n = len(per_problem)
    n_correct = sum(1 for r in per_problem if r["correct"])
    n_error = sum(1 for r in per_problem if r["extract_mode"] == "error")
    n_strict = sum(1 for r in per_problem if r["extract_mode"] == "strict")
    n_extract_fail = sum(1 for r in per_problem if r["extract_mode"] in ("none", "error"))
    n_trunc = sum(1 for r in per_problem if r["finish_reason"] == "length")
    prompt_pairs = [(str(r["id"]), str(r["prompt_sha"])) for r in per_problem]
    return {
        "n_problems": n,
        "dataset_sha256": dataset_sha256(prompt_pairs),
        "accuracy": n_correct / n if n else 0.0,
        "n_correct": n_correct,
        "n_error": n_error,
        "strict_rate": n_strict / n if n else 0.0,
        "extract_fail_rate": n_extract_fail / n if n else 0.0,
        "truncation_rate": n_trunc / n if n else 0.0,
        "wall_s": time.time() - t0,
        "per_problem": per_problem,
    }


# --------------------------------------------------------------------------- #
# Self-test (no GPU): prove gold + prediction extraction is sound.
# --------------------------------------------------------------------------- #
def self_test() -> int:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(f"[self-test] {'ok' if cond else 'FAIL'}: {msg}")
        if not cond:
            ok = False

    check(gold_answer("blah blah\n#### 18") == 18.0, "gold #### 18")
    check(gold_answer("calc <<3*2=6>>6 ... #### 72,000") == 72000.0, "gold comma thousands")
    p, m = extract_pred("First 2+2=4. The answer is 4.")
    check(p == 4.0 and m == "strict", "strict 'the answer is 4'")
    p, m = extract_pred("...\nThe answer is 1,024.")
    check(p == 1024.0 and m == "strict", "strict comma")
    p, m = extract_pred("we get 7 then 42 with no anchor")
    check(p == 42.0 and m == "flexible", "flexible last number")
    p, m = extract_pred("answer: $250")
    check(p == 250.0 and m == "strict", "strict 'answer: $250'")
    p, m = extract_pred("no digits here")
    check(p is None and m == "none", "no number -> none")
    check(is_correct(18.0, 18.0) and not is_correct(18.0, 19.0), "is_correct")
    check(_clean_cot("She has <<3*4=12>>12 left.\n#### 12")[0].endswith("The answer is 12."),
          "_clean_cot strips calc + appends 'The answer is N.'")
    messages = build_messages(build_prompt([], "What is 1+1?"))
    sha = prompt_sha256(messages, 2.0)
    check(sha == prompt_sha256(messages, 2.0), "prompt hash is stable")
    check(sha != prompt_sha256(messages, 3.0), "prompt hash includes gold")
    print("[self-test] PASS" if ok else "[self-test] FAILURES PRESENT")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="run extractor self-test and exit (no GPU)")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint root, without /v1")
    ap.add_argument("--model", default="laguna-xs-2.1", help="served model name")
    ap.add_argument("--label", required=False, help="model-artifact label")
    ap.add_argument("--regimes", default="sampled,greedy", help="comma list from {sampled,greedy}")
    ap.add_argument("--n", type=int, default=500, help="number of test items (seeded subset; -1 = full 1319)")
    ap.add_argument("--n-shot", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="cap items (smoke); overrides --n when smaller")
    ap.add_argument(
        "--expect-count",
        type=int,
        default=None,
        help="fail unless exactly this many test items are loaded",
    )
    ap.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="JSON list of test IDs; selects from the full seeded order and supersedes --n/--limit",
    )
    ap.add_argument("--seed", type=int, default=1234, help="seed for subset + fewshot (+ sampler unless --sampling-seed given)")
    ap.add_argument("--sampling-seed", type=int, default=None,
                    help="per-request decode RNG seed. Distinct from --seed "
                         "(which fixes the test subset + few-shot). Vary across runs to estimate decode "
                         "variance with byte-identical prompts. Defaults to --seed.")
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--top-k", type=int, default=64)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--min-tokens", type=int, default=None,
                    help="endpoint min_tokens extension (default: unset)")
    ap.add_argument("--enable-thinking", action="store_true", help="request template thinking mode")
    ap.add_argument("--concurrency", type=int, default=32, help="number of queued endpoint requests")
    ap.add_argument(
        "--save-text",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="persist raw completion text per item (default: enabled)",
    )
    ap.add_argument("--request-timeout-s", type=int, default=600)
    ap.add_argument("--out-dir", type=Path, default=Path("research/downstream_quality_gsm8k"))
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.base_url:
        ap.error("--base-url is required (or use --self-test)")
    if not args.label:
        ap.error("--label is required for a model run")

    regimes = [r.strip() for r in args.regimes.split(",") if r.strip()]
    for r in regimes:
        if r not in ("sampled", "greedy"):
            ap.error(f"unknown regime {r!r} (want sampled|greedy)")

    # --- deterministic items + few-shot (shared across arms via seed) ---
    n_items = args.n
    if args.limit is not None:
        n_items = args.limit
    full = _load_split("test", n=None)
    import random

    rng = random.Random(args.seed)
    order = list(range(len(full)))
    rng.shuffle(order)
    if args.ids_file is None and n_items is not None and n_items >= 0:
        order = order[:n_items]
    problems: list[dict[str, Any]] = []
    for rank, i in enumerate(order):
        problems.append(
            {
                "id": f"test-{i}",
                "question": full[i]["question"],
                "gold": gold_answer(full[i]["answer"]),
            }
        )
    if args.ids_file is not None:
        requested_ids = json.loads(args.ids_file.read_text())
        if not isinstance(requested_ids, list):
            raise ValueError(
                f"{args.ids_file}: IDs file must contain a JSON list"
            )
        problems = filter_by_ids(problems, requested_ids)
        n_items = len(problems)
    if args.expect_count is not None and len(problems) != args.expect_count:
        raise RuntimeError(
            f"GSM8K loaded {len(problems)} test items; expected {args.expect_count}"
        )
    if not problems:
        raise RuntimeError("GSM8K loaded no test items")
    exemplars, fewshot_sig = build_fewshot(args.n_shot, args.seed)
    if len(exemplars) != args.n_shot or len(fewshot_sig) != args.n_shot:
        raise RuntimeError(
            f"GSM8K loaded {len(exemplars)} few-shot exemplars; expected {args.n_shot}"
        )
    print(f"[gsm8k] {len(problems)} test items (seed={args.seed}); {len(exemplars)}-shot "
          f"fewshot_sig={','.join(fewshot_sig)}", flush=True)

    # Decode RNG seed: --sampling-seed if given, else --seed (back-compat). The
    # subset/few-shot stay tied to --seed so the benchmark is byte-identical across
    # sampling seeds; only the per-request sampler RNG moves (PR #590 multi-seed CI).
    req_seed = args.sampling_seed if args.sampling_seed is not None else args.seed

    def _sampling(regime: str) -> dict[str, Any]:
        if regime == "greedy":
            return {"temperature": 0.0, "top_p": 1.0, "top_k": -1,
                    "max_tokens": args.max_tokens, "seed": req_seed,
                    "enable_thinking": args.enable_thinking, "min_tokens": args.min_tokens}
        return {"temperature": 1.0, "top_p": args.top_p, "top_k": args.top_k,
                "max_tokens": args.max_tokens, "seed": req_seed,
                "enable_thinking": args.enable_thinking, "min_tokens": args.min_tokens}

    args.out_dir.mkdir(parents=True, exist_ok=True)

    def _run(base_url: str, model: str) -> int:
        total_errors = 0
        for regime in regimes:
            s = _sampling(regime)
            print(f"[gsm8k] === arm={args.label} regime={regime} sampling={s} ===", flush=True)
            res = eval_endpoint(
                base_url, model, problems, exemplars,
                temperature=s["temperature"], top_p=s["top_p"], top_k=s["top_k"],
                max_tokens=s["max_tokens"], seed=s["seed"],
                enable_thinking=s["enable_thinking"],
                concurrency=args.concurrency, request_timeout_s=args.request_timeout_s,
                save_text=args.save_text, min_tokens=s["min_tokens"],
            )
            out = {
                "label": args.label,
                "regime": regime,
                "model": model,
                "base_url": base_url,
                "n_shot": args.n_shot,
                "fewshot_sig": fewshot_sig,
                "seed": args.seed,
                "sampling_seed": req_seed,
                "n_requested": n_items,
                "item_ids": [p["id"] for p in problems],
                "sampling": s,
                "concurrency": args.concurrency,
                "created_at": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
                **res,
            }
            seed_tag = "" if args.sampling_seed is None else f"_s{req_seed}"
            out_path = args.out_dir / f"{args.label}_{regime}{seed_tag}.json"
            out_path.write_text(json.dumps(out, indent=2))
            total_errors += res["n_error"]
            print(
                f"[gsm8k] DONE arm={args.label} regime={regime} acc={res['accuracy']:.4f} "
                f"({res['n_correct']}/{res['n_problems']}) strict={res['strict_rate']:.3f} "
                f"extract_fail={res['extract_fail_rate']:.3f} trunc={res['truncation_rate']:.3f} "
                f"wall={res['wall_s']:.0f}s -> {out_path}",
                flush=True,
            )
        return total_errors

    n_error = _run(args.base_url, args.model)
    if n_error:
        print(
            f"[gsm8k] FATAL: {n_error} endpoint request(s) failed; "
            "results were saved but are not a valid quality score",
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
