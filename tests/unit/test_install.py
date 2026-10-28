"""The one-command installer.

The installer is the first code a new user runs, and the only thing it
must never do is make ``~/.gdbinit`` worse: a duplicated ``source`` line
is harmless, a half-written one is not.  These tests run it against a
local git repository, so they exercise the real clone path without a
network.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.sh"

MARKER_START = "# >>> kernlens >>>"
MARKER_END = "# <<< kernlens <<<"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def _make_repo(root: Path) -> Path:
    """A minimal checkout: the installer only needs git and gdbinit.py."""
    repo = root / "upstream"
    (repo / "src" / "kernlens").mkdir(parents=True)
    (repo / "gdbinit.py").write_text(
        'print("fake gdbinit")\n', encoding="utf-8",
    )
    (repo / "src" / "kernlens" / "__init__.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8",
    )
    (repo / "src" / "kernlens" / "doctor.py").write_text(
        "import sys\nprint('fake doctor', sys.argv[1:])\n",
        encoding="utf-8",
    )
    (repo / "src" / "kernlens" / "cli.py").write_text(
        "import sys\nprint('fake cli', sys.argv[1:])\n",
        encoding="utf-8",
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(
        repo, "-c", "user.email=test@example.com",
        "-c", "user.name=Test", "commit", "-qm", "init",
    )
    return repo


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("XDG_DATA_HOME", None)
    env.pop("KERNLENS_DIR", None)
    env.pop("KERNLENS_PREFIX", None)
    env.pop("KERNLENS_GDBINIT", None)
    return env


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = _make_repo(self.root)
        self.home = self.root / "home"
        self.home.mkdir()
        self.data = self.home / "data"
        self.prefix = self.home / "prefix"
        self.rc = self.home / ".gdbinit"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def install(self, *extra: str, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
        command = [
            "sh", str(SCRIPT),
            "--repo", f"file://{self.repo}",
            "--ref", "main",
            "--dir", str(self.data),
            "--prefix", str(self.prefix),
            "--gdbinit", str(self.rc),
            *extra,
        ]
        if dry_run:
            command.append("--dry-run")
        return subprocess.run(
            command,
            env=_env(self.home),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_script_is_valid_posix_shell(self) -> None:
        result = subprocess.run(
            ["sh", "-n", str(SCRIPT)], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_install_clones_and_writes_one_block(self) -> None:
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.data / ".git").is_dir())
        text = self.rc.read_text(encoding="utf-8")
        self.assertEqual(text.count(MARKER_START), 1)
        self.assertEqual(text.count(MARKER_END), 1)
        expected = f"source {self.data / 'gdbinit.py'}"
        self.assertIn(expected, text)
        wrapper = self.prefix / "bin" / "kernlens"
        self.assertTrue(wrapper.is_file())
        self.assertTrue(wrapper.stat().st_mode & 0o111)

    def test_running_twice_does_not_duplicate_the_block(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stderr)
        text = self.rc.read_text(encoding="utf-8")
        self.assertEqual(text.count(MARKER_START), 1)

    def test_existing_gdbinit_content_is_preserved(self) -> None:
        self.rc.write_text(
            "set pagination off\nsource /tmp/other.py\n", encoding="utf-8",
        )
        self.assertEqual(self.install().returncode, 0)
        text = self.rc.read_text(encoding="utf-8")
        self.assertIn("set pagination off", text)
        self.assertIn("source /tmp/other.py", text)
        self.assertEqual(text.count(MARKER_START), 1)

    def test_wrapper_runs_the_cli_from_the_checkout(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        wrapper = self.prefix / "bin" / "kernlens"
        result = subprocess.run(
            [str(wrapper), "doctor", "--help"],
            env=_env(self.home),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fake cli", result.stdout)
        self.assertIn("--help", result.stdout)

    def test_the_shell_and_python_installers_share_the_markers(self) -> None:
        # ``install.sh`` cannot import the package, so the two installers
        # spell the markers twice.  A drift would make ``kernlens doctor``
        # miss a block the shell installer wrote.
        from kernlens import install

        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(f"marker_start='{install.MARKER_START}'", text)
        self.assertIn(f"marker_end='{install.MARKER_END}'", text)

    def test_dry_run_changes_nothing(self) -> None:
        result = self.install(dry_run=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.data.exists())
        self.assertFalse(self.rc.exists())
        self.assertFalse((self.prefix / "bin" / "kernlens").exists())
        self.assertIn("would clone", result.stdout)

    def test_uninstall_removes_the_block_and_the_wrapper(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        result = self.install("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.rc.read_text(encoding="utf-8")
        self.assertNotIn(MARKER_START, text)
        self.assertNotIn("gdbinit.py", text)
        self.assertFalse((self.prefix / "bin" / "kernlens").exists())
        # Removing the integration must not delete the checkout: that is
        # the user's data, and a second install would have to re-clone.
        self.assertTrue((self.data / ".git").is_dir())

    def test_unknown_option_fails_with_a_hint(self) -> None:
        result = self.install("--bogus")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--help", result.stderr)


if __name__ == "__main__":
    unittest.main()
