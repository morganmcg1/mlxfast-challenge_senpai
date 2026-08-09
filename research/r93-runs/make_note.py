#!/usr/bin/env python3
"""Generate an official submission note for one R93 replicate.

The submission API enforces a 5 KiB minimum note, and the service deduplicates
by editable-surface content, so every replicate needs its own marker and its own
note. Rather than hand-write near-identical prose eight times, this renders the
replicate-specific fields into a shared body and splices in whatever receipts
have already landed.

  python3 research/r93-runs/make_note.py null 3 --prior research/r93-runs/prior.json
  python3 research/r93-runs/make_note.py ladder 120 --prior research/r93-runs/prior.json
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NULL_SRC = os.path.join(HERE, "note-null-1.md")
LADDER_SRC = os.path.join(HERE, "note-ladder.tmpl.md")
PROBE_SRC = os.path.join(HERE, "note-probe.tmpl.md")


def prior_table(prior) -> str:
    if not prior:
        return ("No receipt from this arm has landed yet at the time of writing.\n"
                "Every receipt we do obtain will be published in the research log,\n"
                "including any that contradicts our expectation.\n")
    rows = ["| marker | submission | status | cand decode s/tok | cand prefill s/tok |"
            " baseline decode s/tok |", "| --- | --- | --- | --- | --- | --- |"]
    for r in prior:
        rows.append(
            "| `{marker}` | `{id}` | {status} | {cand_dec} | {cand_pre} | {bl_dec} |".format(
                marker=r.get("marker", "?"), id=r.get("id", "?"),
                status=r.get("status", "?"),
                cand_dec=r.get("cand_dec", "?"), cand_pre=r.get("cand_pre", "?"),
                bl_dec=r.get("bl_dec", "?")))
    body = "\n".join(rows) + "\n"
    body += ("\nThese are **raw** per-token timings read straight off the receipts, not\n"
             "ranked scores. We never compare ranked scores across sessions: each score is\n"
             "normalised against a same-session baseline draw whose own dispersion is\n"
             "several times the candidate's, so a score-to-score comparison imports that\n"
             "baseline noise twice.\n")
    return body


def splice(text: str, start: str, end: str, body: str) -> str:
    i = text.index(start)
    j = text.index(end)
    head = text[:i] + start + "\n\n"
    return head + body + "\n" + text[j:]


def render_null(n: int, prior) -> str:
    text = open(NULL_SRC).read()
    text = text.replace("null replicate 1/5", "null replicate %d/5" % n)
    text = text.replace("(true null, replicate 1 of 5)", "(true null, replicate %d of 5)" % n)
    text = text.replace("senpai-r93-null-1", "senpai-r93-null-%d" % n)
    text = text.replace("note-null-1.md", "note-null-%d.md" % n)
    text = text.replace("through `senpai-r93-null-%d`" % n, "through `senpai-r93-null-5`")
    return splice(text, "## 10. Measured results", "## 11. Caveats", prior_table(prior))


def render_ladder(k: int, prior) -> str:
    text = open(LADDER_SRC).read()
    text = text.replace("{{K}}", str(k))
    text = text.replace("{{PRIOR}}", prior_table(prior))
    return text


def render_probe(n: int, prior) -> str:
    text = open(PROBE_SRC).read()
    text = text.replace("{{N}}", str(n))
    text = text.replace("{{PRIOR}}", prior_table(prior))
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["null", "ladder", "probe"])
    ap.add_argument("value", type=int)
    ap.add_argument("--prior", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    prior = json.load(open(args.prior)) if args.prior and os.path.exists(args.prior) else []
    if args.kind == "null":
        text = render_null(args.value, prior)
        out = args.out or os.path.join(HERE, "note-null-%d.md" % args.value)
    elif args.kind == "probe":
        text = render_probe(args.value, prior)
        out = args.out or os.path.join(HERE, "note-probe-routed-fma-%d.md" % args.value)
    else:
        text = render_ladder(args.value, prior)
        out = args.out or os.path.join(HERE, "note-ladder-K%d.md" % args.value)
    with open(out, "w") as fh:
        fh.write(text)
    print("%s bytes=%d" % (out, len(text.encode())))
    if len(text.encode()) < 5120:
        print("WARNING: below the 5 KiB submission-note minimum")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
