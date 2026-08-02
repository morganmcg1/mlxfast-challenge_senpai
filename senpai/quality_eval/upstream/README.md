# Vendored quality evaluators

These scripts are pinned imports from
[`morganmcg1/gemma-challenge-senpai`](https://github.com/morganmcg1/gemma-challenge-senpai).
`PROVENANCE.json` records the source commit, path, Git blob, pristine SHA-256,
and every local adaptation for each file.

The scoring and dataset-construction logic is unchanged. Local adaptations add
the Laguna endpoint's model name, full response retention, prompt/dataset
hashes, and fail-closed validation. Generative evaluators save completion text
by default, and the PPL scorer saves its scored token log-probabilities.
Profile-sized runs reject shortened datasets, non-finite PPL values, and
item-level endpoint failures so infrastructure errors cannot masquerade as
quality scores. `PROVENANCE.json` lists every adaptation per imported file.
