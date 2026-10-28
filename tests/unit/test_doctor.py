"""The host-side installation check.

``kernlens doctor`` exists to answer "why did nothing happen?" before the
user files an issue.  These tests pin the two properties that make it
useful: every probe has a distinct, actionable outcome, and the report
never pretends a missing prerequisite is fine.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kernlens import doctor

ROOT = Path(__file__).resolve().parents[2]


def _answers(command: list[str]) -> tuple[int, str]:
    """A stand-in GDB that answers the three probes doctor makes."""
    joined = " ".join(command)
    if "--version" in command:
        return 0, "GNU gdb (fake) 15.1\nCopyright ..."
    if "KLPY=" in joined:
        return 0, "KLPY=3.12.3"
    if "KLVER=" in joined:
        return 0, "KernLens 0.3.0 loaded\nKLVER=0.3.0"
    return 0, ""


def _options(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "gdbinit": str(Path("/nonexistent/.gdbinit")),
        "startup": None,
        "vmlinux": None,
        "btf": "/nonexistent/btf",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class RunnerTests(unittest.TestCase):
    def test_run_command_drops_the_launchers_pythonpath(self) -> None:
        # ``bin/kernlens`` exports PYTHONPATH so its own import works.
        # If the GDB probe inherited it, ``import kernlens`` would pass
        # even when the startup file failed to load.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "show.py"
            script.write_text(
                "import os\n"
                "print(os.environ.get('PYTHONPATH', 'unset'))\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ, {"PYTHONPATH": "/should/not/leak"},
            ):
                status, output = doctor.run_command(
                    [sys.executable, str(script)],
                    env=None,
                )
        self.assertEqual(status, 0, output)
        self.assertEqual(output, "unset")


class RenderTests(unittest.TestCase):
    def test_report_lists_every_check_with_its_status(self) -> None:
        text = doctor.render([
            doctor.Check("python", doctor.OK, "3.12.3"),
            doctor.Check("gdb", doctor.WARN, "not found"),
        ])
        self.assertIn("ok    python", text)
        self.assertIn("warn  gdb", text)

    def test_failures_change_the_summary(self) -> None:
        text = doctor.render([doctor.Check("gdb", doctor.FAIL, "missing")])
        self.assertIn("1 check(s) failed", text)
        self.assertNotIn("All checks passed", text)

    def test_warnings_change_the_summary_without_failing(self) -> None:
        text = doctor.render([doctor.Check("vmlinux", doctor.WARN, "none")])
        self.assertIn("1 warning(s)", text)
        self.assertNotIn("failed", text)


class SourceLineTests(unittest.TestCase):
    def test_finds_the_last_source_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / ".gdbinit"
            first = Path(tmp) / "old" / "gdbinit.py"
            second = Path(tmp) / "new" / "gdbinit.py"
            rc.write_text(
                "# source /ignored/gdbinit.py\n"
                f"source {first}\n"
                f'source "{second}"\n',
                encoding="utf-8",
            )
            self.assertEqual(doctor.find_source_line(rc), second)

    def test_resolves_relative_to_the_startup_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / ".gdbinit"
            rc.write_text("source ./kernlens/gdbinit.py\n", encoding="utf-8")
            self.assertEqual(
                doctor.find_source_line(rc),
                Path(tmp) / "kernlens" / "gdbinit.py",
            )

    def test_ignores_other_source_lines_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / ".gdbinit"
            rc.write_text(
                "# source /tmp/gdbinit.py\n"
                "source /tmp/other.py\n"
                "set pagination off\n",
                encoding="utf-8",
            )
            self.assertIsNone(doctor.find_source_line(rc))

    def test_missing_rc_is_not_an_error(self) -> None:
        self.assertIsNone(doctor.find_source_line(Path("/nonexistent/rc")))


class GdbinitCheckTests(unittest.TestCase):
    def test_missing_source_line_warns_with_the_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / ".gdbinit"
            rc.write_text("set pagination off\n", encoding="utf-8")
            check = doctor.check_gdbinit(rc, startup=Path("/opt/kernlens/gdbinit.py"))
        self.assertEqual(check.status, doctor.WARN)
        self.assertIn("source /opt/kernlens/gdbinit.py", check.detail)

    def test_dangling_source_line_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = Path(tmp) / ".gdbinit"
            rc.write_text("source /missing/gdbinit.py\n", encoding="utf-8")
            check = doctor.check_gdbinit(rc)
        self.assertEqual(check.status, doctor.FAIL)
        self.assertIn("does not exist", check.detail)

    def test_existing_source_line_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "gdbinit.py"
            startup.write_text("", encoding="utf-8")
            rc = Path(tmp) / ".gdbinit"
            rc.write_text(f"source {startup}\n", encoding="utf-8")
            check = doctor.check_gdbinit(rc)
        self.assertEqual(check.status, doctor.OK)


class LoadCheckTests(unittest.TestCase):
    def test_the_source_line_is_not_quoted(self) -> None:
        # GDB's ``source`` does not strip quotes: ``source "/path"``
        # looks for a file whose name begins with a quote.  The probe has
        # to send the bare path, which also keeps spaces working.
        seen: list[list[str]] = []

        def runner(command: list[str]) -> tuple[int, str]:
            seen.append(list(command))
            return 0, "KLVER=0.3.0"

        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "with space" / "gdbinit.py"
            startup.parent.mkdir()
            startup.write_text("", encoding="utf-8")
            doctor.check_gdb_load("/usr/bin/gdb", startup, runner=runner)
        source = next(
            item for item in seen[0] if item.startswith("source ")
        )
        self.assertEqual(source, f"source {startup}")

    def test_success_reports_the_loaded_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "gdbinit.py"
            startup.write_text("", encoding="utf-8")
            check = doctor.check_gdb_load("/usr/bin/gdb", startup, runner=_answers)
        self.assertEqual(check.status, doctor.OK)
        self.assertIn("0.3.0", check.detail)

    def test_failure_keeps_the_last_error_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "gdbinit.py"
            startup.write_text("", encoding="utf-8")

            def broken(command: list[str]) -> tuple[int, str]:
                del command
                return 1, "Python Exception\nModuleNotFoundError: gdb"

            check = doctor.check_gdb_load(
                "/usr/bin/gdb", startup, runner=broken,
            )
        self.assertEqual(check.status, doctor.FAIL)
        self.assertIn("ModuleNotFoundError", check.detail)

    def test_missing_startup_fails_without_running_gdb(self) -> None:
        def never(command: list[str]) -> tuple[int, str]:
            raise AssertionError(f"ran {command}")

        check = doctor.check_gdb_load(
            "/usr/bin/gdb", Path("/nonexistent/gdbinit.py"), runner=never,
        )
        self.assertEqual(check.status, doctor.FAIL)


class VmlinuxCheckTests(unittest.TestCase):
    def test_missing_argument_warns(self) -> None:
        self.assertEqual(
            doctor.check_vmlinux(None).status, doctor.WARN,
        )

    def test_non_elf_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "vmlinux"
            image.write_bytes(b"not an elf")
            check = doctor.check_vmlinux(image)
        self.assertEqual(check.status, doctor.FAIL)
        self.assertIn("not an ELF", check.detail)

    def test_elf_file_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "vmlinux"
            image.write_bytes(b"\x7fELF" + b"\0" * 64)
            check = doctor.check_vmlinux(image)
        self.assertEqual(check.status, doctor.OK)


class CollectTests(unittest.TestCase):
    def test_default_startup_is_the_packaged_file(self) -> None:
        path = doctor.default_startup()
        self.assertTrue(path.is_file())
        self.assertEqual(
            path.parent, Path(doctor.__file__).resolve().parent,
        )
        self.assertIn("def bootstrap", path.read_text(encoding="utf-8"))

    def test_collects_every_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "gdbinit.py"
            startup.write_bytes(b"\x7fELF")
            rc = Path(tmp) / ".gdbinit"
            rc.write_text(f"source {startup}\n", encoding="utf-8")
            checks = doctor.collect(
                _options(gdbinit=str(rc)),
                which=lambda name: "/usr/bin/gdb" if name == "gdb" else None,
                runner=_answers,
            )
        names = [check.name for check in checks]
        self.assertEqual(
            names,
            [
                "python", "package", "gdb", "gdb-python", "gdb-load",
                "gdbinit", "vmlinux", "btf", "target",
            ],
        )
        self.assertFalse([check for check in checks if check.status == doctor.FAIL])

    def test_missing_gdb_skips_the_gdb_only_probes(self) -> None:
        checks = doctor.collect(
            _options(),
            which=lambda name: None,
            runner=_answers,
        )
        names = [check.name for check in checks]
        self.assertIn("gdb", names)
        self.assertNotIn("gdb-python", names)
        self.assertNotIn("gdb-load", names)
        self.assertEqual(
            next(c for c in checks if c.name == "gdb").status, doctor.FAIL,
        )


class EntryPointTests(unittest.TestCase):
    def test_module_help_runs_without_gdb(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "kernlens.doctor", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--vmlinux", result.stdout)

    def test_checkout_launcher_exists_and_is_executable(self) -> None:
        launcher = ROOT / "bin" / "kernlens"
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
