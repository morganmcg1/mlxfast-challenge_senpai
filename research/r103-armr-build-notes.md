# R103 arm-R build notes: standing up a second, older revision side by side

Research-only. Nothing here is on the submitted surface.

Written for R103-A (frieren) and anybody else who needs to run the arm-R OLD
revision `30f752df` next to the current base `0f6862d0` on the same host.
The recipe below is exactly what R103-B used; both trees built and both
produced token-identical greedy output on an M4 Pro / 48 GiB host.

## 0. Why a detached worktree

`run_job` refuses to start while the assignment worktree is dirty, and the
local benchmark lock refuses a second model-holding process. Building the old
revision *in place* therefore costs a checkout round trip per measurement and
makes the assignment branch dirty. A detached `git worktree` under the
gitignored `.mlxfast-private/` avoids both problems and lets you keep the two
trees resident at the same time.

```bash
cd "$TARGET"                       # the assignment worktree
git worktree add --detach .mlxfast-private/r103b-old 30f752df
git worktree add --detach .mlxfast-private/r103b-new 0f6862d0
```

`.mlxfast-private/` is already ignored, so neither tree can leak into a commit.
Remove them with `git worktree remove --force .mlxfast-private/r103b-old` when
finished.

## 1. Build only the worker, into a private scratch path

The trusted CLI (`mlxfast-swift`) is **identical** at `30f752df` and
`0f6862d0`: nothing under `Sources/MLXFastCLI`, `Sources/MLXFastTrustedHarness`
or `Sources/MLXFastCore` differs. One CLI binary can therefore drive both
workers, and only `mlxfast-runtime-worker` has to be rebuilt per revision.
That cuts each tree's build to ~4-5 minutes instead of a full harness build.

```bash
for w in r103b-new r103b-old; do
  cd "$TARGET/.mlxfast-private/$w"
  mkdir -p .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="$PWD/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  git checkout -- Package.resolved 2>/dev/null || true
done
```

`--scratch-path .build-worker` matters: it mirrors the directory layout the
scored worker build uses, which is where the worker looks for `mlx.metallib`.
`--force-resolved-versions` is required by AGENTS.md; without it an unflagged
`swift build` can rewrite `Package.resolved`.

## 2. Metallib placement

The worker resolves `mlx.metallib` next to its own executable
(`.build-worker/arm64-apple-macosx/release/`). `swift build --product
mlxfast-runtime-worker` does **not** produce it, so copy one in:

```bash
SRC="$TARGET/.build-worker/arm64-apple-macosx/release"
for w in r103b-new r103b-old; do
  DST="$TARGET/.mlxfast-private/$w/.build-worker/arm64-apple-macosx/release"
  cp "$SRC/mlx.metallib" "$SRC/mlx.metallib.fingerprint" "$DST/"
done
```

R103-B deliberately copied the **same** metallib into both trees and recorded
that as a control. That is sound here because every AOT `.metal` / `.h` source
that differs between `30f752df` and `0f6862d0` differs by comments and
whitespace only (proved in
`research/maple-tanjiro-r103b-kernel-text-differential.md`, rung 1), so the two
revisions would compile to the same metallib anyway. **If your arm changes an
AOT kernel source, this shortcut is invalid** - run
`tools/build-mlx-metallib.sh` in that tree instead.

`enforceMetallibFingerprint` only warns locally, so a fingerprint mismatch will
not stop the run; it will just print a warning.

## 3. Weights: do not create a nested symlink

The tracked `weights/` directory already exists in every worktree with only a
`.gitkeep` in it. The obvious `ln -s ../../weights weights` **inside** that
directory resolves to `.mlxfast-private/weights` and silently breaks. The
symptom is not obvious from the CLI:

```
mlxfast-swift: runtime worker closed stdout before returning a response: exit_status=15
```

with an empty worker stderr, because the CLI drops worker stderr (see §5).
Running the worker by hand exposes the real cause:

```
mlxfast-runtime-worker: participant worker preflight failed:
  ... "config.json" couldn't be opened ...
```

Simplest fix: don't symlink. Point `--weights` at the primary checkout's real
weights directory, which both arms then provably share:

```bash
--weights "$TARGET/weights"
```

## 4. Driving a fixed, token-checked forward pass

`mlxfast-swift correctness-trace` always spawns a worker subprocess
(`Sources/MLXFastCLI/main.swift:175-217`), runs one 512-token prefill, then
`--step N` teacher-forced decode steps `0...N`, and prints a JSON report with
`generated_prefix`, `matched_prefix_steps` and `top_logits`. It is the cheapest
way to get a fixed, verified decode workload out of an arbitrary worker binary.

```bash
"$TARGET/.build/release/mlxfast-swift" correctness-trace \
  --weights "$TARGET/weights" \
  --golden  "$TARGET/correctness_prompts/public_longcopy_gate_english_512_256.json" \
  --step 5 --top-k 5
```

Gotchas:

- `--case` takes a **case name**, not an index. The public golden's only case is
  `longcopy-gate-english-512`. Passing `--case 0` fails with
  `correctness golden does not contain case 0`. Just omit `--case`.
- `--top-k` is only forwarded to the worker at step 0
  (`LagunaRuntimeCorrectnessCompare.swift:56-60`), but the report still carries
  the final step's `top_logits`.
- One pass costs ~60 s wall on an M4 Pro / 48 GiB host, essentially all of it
  weight load.

## 5. Two harness facts that cost R103-B an hour

**Worker stderr is discarded.** `RuntimeWorkerClient` installs
`WorkerStderrDrain(..., emit: options.forwardsWorkerStderr ? nil : { _ in })`
(`Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:~1716`), and
`correctness-trace` does not set `forwardsWorkerStderr`. Every worker
diagnostic - including the reason it died - is thrown away, and the CLI reports
only `exit_status=15` (SIGTERM from its own `stopRuntimeWorkerProcess`).

Recover it with a wrapper script and
`MLXFAST_RUNTIME_WORKER_EXECUTABLE`. `runtimeWorkerOptions`
(`Sources/MLXFastCLI/main.swift:1239-1320`) only checks `isExecutableFile`, so a
`#!/bin/bash` shim is accepted:

```bash
cat > wrap.sh <<EOF
#!/bin/bash
exec "$REAL_WORKER" "\$@" 2>> "$LOGDIR/worker_stderr.log"
EOF
chmod +x wrap.sh
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$PWD/wrap.sh"
export MLXFAST_NO_SANDBOX=1          # skip Seatbelt so the shim can exec
```

**The worker environment is a strict allowlist.**
`sanitizedRuntimeWorkerEnvironment` (`LagunaRuntimeWorker.swift:1993-2025`)
passes exactly `HF_HUB_OFFLINE, HOME, LANG, LOGNAME, PATH, SHELL, TERM, TMPDIR,
TRANSFORMERS_OFFLINE, USER, __CF_USER_TEXT_ENCODING` plus the prefixes
`DARKBLOOM_, DYLD_, LC_, METAL_, MLX_, MTL_`. Everything else, **including every
`MLXFAST_*` variable**, is stripped before the worker starts. Any research knob
you want the worker to see must be named `DARKBLOOM_*`, `MLX_*`, `METAL_*` or
`MTL_*`. Also note `HOME`/`USER`/`LOGNAME` are not guaranteed to be set inside a
`run_job` environment, so default them yourself if you build the env with
`env -i`.

## 6. Provenance of the two revisions

| | OLD | NEW |
|---|---|---|
| commit | `30f752df` | `0f6862d0` |
| role | arm R receipt `7ce1262d` | current advisor base |
| official `cs` | 2.589321 | 2.582286 |
| official us/step | 4893.712 | 4913.117 |

`30f752df` is an ancestor of `0f6862d0`; roughly 250 commits separate them,
spanning rounds ~89-103.
