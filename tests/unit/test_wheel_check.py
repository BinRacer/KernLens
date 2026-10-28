"""The wheel check that replaced the source-only tripwire.

The old test asserted that ``[project.scripts]`` was absent, because a
wheel without the startup file could not work.  Both facts changed
together, so the guard moved to the build itself: a wheel that omits
``kernlens/gdbinit.py`` or the console script fails here.
"""

from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import check_wheel


def _wheel(root: Path, *, entries: dict[str, str] | None = None) -> Path:
    contents = {
        "kernlens/__init__.py": "",
        "kernlens/cli.py": "",
        "kernlens/gdbinit.py": "",
        "kernlens/py.typed": "",
        "kernlens-0.3.0.dist-info/entry_points.txt": (
            "[console_scripts]\n"
            "kernlens = kernlens.cli:main\n"
        ),
    }
    contents.update(entries or {})
    path = root / "kernlens-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in contents.items():
            archive.writestr(name, text)
    return path


class WheelCheckTests(unittest.TestCase):
    def test_a_complete_wheel_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel = _wheel(Path(tmp))
            self.assertEqual(check_wheel.check(wheel), [])

    def test_a_missing_startup_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("kernlens/__init__.py", "")
                archive.writestr("kernlens/cli.py", "")
                archive.writestr("kernlens/py.typed", "")
                archive.writestr(
                    "kernlens-0.3.0.dist-info/entry_points.txt",
                    "[console_scripts]\nkernlens = kernlens.cli:main\n",
                )
            self.assertIn(
                "missing kernlens/gdbinit.py", check_wheel.check(path),
            )

    def test_a_missing_console_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel = _wheel(
                Path(tmp),
                entries={
                    "kernlens-0.3.0.dist-info/entry_points.txt":
                        "[console_scripts]\nother = other:main\n",
                },
            )
            problems = check_wheel.check(wheel)
        self.assertTrue(
            any("entry_points.txt" in problem for problem in problems),
            problems,
        )

    def test_main_reports_every_problem_and_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.whl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("kernlens/__init__.py", "")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = check_wheel.main([str(path)])
        self.assertEqual(status, 1)
        self.assertIn("missing kernlens/gdbinit.py", err.getvalue())


if __name__ == "__main__":
    unittest.main()
