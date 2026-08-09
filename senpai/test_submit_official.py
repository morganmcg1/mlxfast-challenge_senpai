#!/usr/bin/env python3
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("submit-official.sh").resolve()


def run(argv, cwd, *, env=None, check=True):
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and result.returncode:
        raise AssertionError(f"{argv!r} failed ({result.returncode}):\n{result.stdout}")
    return result


class OfficialSubmissionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mlxfast-submit-guard-")
        self.root = Path(self.temporary.name)
        self.remote = self.root / "origin.git"
        self.repository = self.root / "candidate"
        self.bin = self.root / "bin"
        self.log = self.root / "mlxfast-argv"

        run(["git", "init", "--bare", "-q", self.remote], self.root)
        run(["git", "init", "-q", self.repository], self.root)
        run(["git", "config", "user.name", "Test"], self.repository)
        run(["git", "config", "user.email", "test@example.com"], self.repository)
        run(["git", "branch", "-M", "main"], self.repository)

        (self.repository / "Sources").mkdir()
        (self.repository / "benchmark.json").write_text(
            '{"editablePaths":["Sources/"]}\n', encoding="utf-8"
        )
        (self.repository / "Sources/kernel.swift").write_text("base\n", encoding="utf-8")
        (self.repository / "research.md").write_text("notes\n", encoding="utf-8")
        run(["git", "add", "."], self.repository)
        run(["git", "commit", "-qm", "base"], self.repository)
        self.base = run(["git", "rev-parse", "HEAD"], self.repository).stdout.strip()
        run(["git", "remote", "add", "origin", self.remote], self.repository)
        run(["git", "push", "-qu", "origin", "main"], self.repository)

        run(["git", "switch", "-qc", "experiment"], self.repository)
        (self.repository / "Sources/kernel.swift").write_text("candidate\n", encoding="utf-8")
        run(["git", "add", "Sources/kernel.swift"], self.repository)
        run(["git", "commit", "-qm", "candidate"], self.repository)
        self.candidate = run(["git", "rev-parse", "HEAD"], self.repository).stdout.strip()

        self.bin.mkdir()
        fake_cli = self.bin / "mlxfast"
        fake_cli.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" > "$MLXFAST_FAKE_LOG"\n',
            encoding="utf-8",
        )
        fake_cli.chmod(0o755)
        self.environment = os.environ | {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "MLXFAST_FAKE_LOG": str(self.log),
        }

    def tearDown(self):
        self.temporary.cleanup()

    def submit(self, *arguments):
        return self.submit_with_base(self.base, *arguments)

    def submit_with_base(self, base, *arguments):
        return run(
            ["/bin/bash", SCRIPT, base, *arguments],
            self.repository,
            env=self.environment,
            check=False,
        )

    def test_current_base_submits_with_fixed_attribution_from_detached_head(self):
        run(["git", "switch", "--detach", "-q", self.candidate], self.repository)
        result = self.submit("--note-file", "submission-note.md")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            self.log.read_text(encoding="utf-8").splitlines(),
            ["submit", "--model", "senpai", "--note-file", "submission-note.md"],
        )

    def test_dirty_research_is_allowed_but_dirty_submission_surface_is_not(self):
        (self.repository / "research.md").write_text("working notes\n", encoding="utf-8")
        allowed = self.submit()
        self.assertEqual(allowed.returncode, 0, allowed.stdout)

        self.log.unlink()
        (self.repository / "Sources/kernel.swift").write_text("uncommitted\n", encoding="utf-8")
        refused = self.submit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("commit or discard changes", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_remote_main_advance_invalidates_the_old_base_before_cli_execution(self):
        publisher = self.root / "publisher"
        run(["git", "clone", "-q", "--branch", "main", self.remote, publisher], self.root)
        run(["git", "config", "user.name", "Test"], publisher)
        run(["git", "config", "user.email", "test@example.com"], publisher)
        (publisher / "Sources/kernel.swift").write_text("new frontier\n", encoding="utf-8")
        run(["git", "add", "Sources/kernel.swift"], publisher)
        run(["git", "commit", "-qm", "advance frontier"], publisher)
        run(["git", "push", "-q", "origin", "main"], publisher)

        refused = self.submit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("submitted snapshot differs", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_docs_only_main_advance_does_not_invalidate_the_recorded_base(self):
        publisher = self.root / "publisher"
        run(["git", "clone", "-q", "--branch", "main", self.remote, publisher], self.root)
        run(["git", "config", "user.name", "Test"], publisher)
        run(["git", "config", "user.email", "test@example.com"], publisher)
        (publisher / "frontier.txt").write_text("research note\n", encoding="utf-8")
        run(["git", "add", "frontier.txt"], publisher)
        run(["git", "commit", "-qm", "document frontier"], publisher)
        run(["git", "push", "-q", "origin", "main"], publisher)

        allowed = self.submit()
        self.assertEqual(allowed.returncode, 0, allowed.stdout)
        self.assertTrue(self.log.exists())

    def test_model_override_is_rejected(self):
        refused = self.submit("--model", "other")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("fixed to senpai", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_committed_contract_change_is_rejected(self):
        (self.repository / "benchmark.json").write_text(
            '{"editablePaths":["Sources/","research.md"]}\n', encoding="utf-8"
        )
        run(["git", "add", "benchmark.json"], self.repository)
        run(["git", "commit", "-qm", "poison submission contract"], self.repository)

        refused = self.submit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("benchmark.json differs", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_descendant_base_with_rewritten_submitted_source_is_rejected(self):
        refused = self.submit_with_base(self.candidate)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("submitted snapshot differs", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_ignored_file_under_editable_directory_is_rejected(self):
        exclude = self.repository / ".git/info/exclude"
        exclude.write_text("Sources/ignored.swift\n", encoding="utf-8")
        (self.repository / "Sources/ignored.swift").write_text("ignored\n", encoding="utf-8")

        refused = self.submit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("commit or discard changes", refused.stdout)
        self.assertFalse(self.log.exists())

    def test_skip_worktree_entry_is_rejected(self):
        run(
            ["git", "update-index", "--skip-worktree", "Sources/kernel.swift"],
            self.repository,
        )
        (self.repository / "Sources/kernel.swift").write_text("hidden change\n", encoding="utf-8")

        refused = self.submit()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("skip-worktree/assume-unchanged", refused.stdout)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
