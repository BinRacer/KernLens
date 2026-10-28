"""The ``kernlens`` console script.

``kernlens`` is the first command a wheel user runs, and two of its
subcommands edit ``~/.gdbinit``.  These tests point it at a temporary
file, so the real startup file is never touched.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from kernlens import __version__, cli, install


def _run(*argv: str) -> tuple[int, str, str]:
    """Call ``cli.main`` and capture what it printed."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = cli.main(list(argv))
    return status, out.getvalue(), err.getvalue()


class PathAndVersionTests(unittest.TestCase):
    def test_path_prints_the_packaged_startup_file(self) -> None:
        status, out, _ = _run("path")
        self.assertEqual(status, 0)
        path = Path(out.strip())
        self.assertTrue(path.is_file())
        self.assertEqual(path, install.startup_path())

    def test_version_prints_the_package_version(self) -> None:
        status, out, _ = _run("version")
        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), f"kernlens {__version__}")

    def test_help_lists_every_subcommand(self) -> None:
        status, out, _ = _run("--help")
        self.assertEqual(status, 0)
        for command in ("path", "install", "doctor", "version"):
            with self.subTest(command=command):
                self.assertIn(command, out)


class DispatchTests(unittest.TestCase):
    def test_no_argument_runs_doctor(self) -> None:
        with mock.patch.object(cli.doctor, "main", return_value=0) as doctor:
            self.assertEqual(cli.main([]), 0)
        doctor.assert_called_once_with([])

    def test_flags_without_a_subcommand_still_reach_doctor(self) -> None:
        # ``kernlens --vmlinux ...`` predates the subcommands; it must
        # keep meaning ``kernlens doctor --vmlinux ...``.
        with mock.patch.object(cli.doctor, "main", return_value=1) as doctor:
            self.assertEqual(cli.main(["--vmlinux", "/nonexistent"]), 1)
        doctor.assert_called_once_with(["--vmlinux", "/nonexistent"])

    def test_doctor_subcommand_passes_the_rest_through(self) -> None:
        with mock.patch.object(cli.doctor, "main", return_value=0) as doctor:
            self.assertEqual(cli.main(["doctor", "--btf", "/tmp/btf"]), 0)
        doctor.assert_called_once_with(["--btf", "/tmp/btf"])


class InstallCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rc = Path(self._tmp.name) / ".gdbinit"
        self.startup = Path(self._tmp.name) / "gdbinit.py"
        self.startup.write_text(
            "def bootstrap(namespace):\n    pass\n", encoding="utf-8",
        )

    def _install(self, *extra: str, dry_run: bool = False) -> tuple[int, str, str]:
        argv = [
            "install",
            "--gdbinit", str(self.rc),
            "--startup", str(self.startup),
            *extra,
        ]
        if dry_run:
            argv.append("--dry-run")
        return _run(*argv)

    def test_writes_one_block_and_names_the_next_command(self) -> None:
        status, out, _ = self._install()
        self.assertEqual(status, 0)
        text = self.rc.read_text(encoding="utf-8")
        self.assertEqual(text.count(install.MARKER_START), 1)
        self.assertIn(f"source {self.startup}", text)
        self.assertIn("Next: gdb", out)

    def test_running_twice_does_not_duplicate_the_block(self) -> None:
        self.assertEqual(self._install()[0], 0)
        status, out, _ = self._install()
        self.assertEqual(status, 0)
        self.assertIn("already sources", out)
        text = self.rc.read_text(encoding="utf-8")
        self.assertEqual(text.count(install.MARKER_START), 1)

    def test_existing_lines_are_preserved(self) -> None:
        self.rc.write_text(
            "set pagination off\nsource /tmp/other.py\n", encoding="utf-8",
        )
        self.assertEqual(self._install()[0], 0)
        text = self.rc.read_text(encoding="utf-8")
        self.assertIn("set pagination off", text)
        self.assertIn("source /tmp/other.py", text)
        self.assertEqual(text.count(install.MARKER_START), 1)

    def test_uninstall_removes_only_the_block(self) -> None:
        self.rc.write_text(
            "set pagination off\n", encoding="utf-8",
        )
        self.assertEqual(self._install()[0], 0)
        status, out, _ = self._install("--uninstall")
        self.assertEqual(status, 0)
        self.assertIn("removed", out)
        self.assertEqual(
            self.rc.read_text(encoding="utf-8"), "set pagination off\n",
        )

    def test_dry_run_writes_nothing(self) -> None:
        status, out, _ = self._install(dry_run=True)
        self.assertEqual(status, 0)
        self.assertFalse(self.rc.exists())
        self.assertIn("would write", out)

    def test_missing_startup_fails_without_writing(self) -> None:
        argv = [
            "install",
            "--gdbinit", str(self.rc),
            "--startup", str(self.startup.with_name("missing.py")),
        ]
        status, _, err = _run(*argv)
        self.assertEqual(status, 1)
        self.assertIn("startup file not found", err)
        self.assertFalse(self.rc.exists())


if __name__ == "__main__":
    unittest.main()
