"""Packaging checks for the PEP 561 ``py.typed`` marker."""

from __future__ import annotations

import ast
import unittest
from importlib.resources import files
from pathlib import Path

import kernlens

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "kernlens"


def _unannotated_functions() -> list[str]:
    """Return ``path:line name`` for every def missing a signature type."""
    missing: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            where = f"{path.relative_to(ROOT)}:{node.lineno} {node.name}"
            if node.returns is None:
                missing.append(f"{where} (return)")
            for argument in node.args.args + node.args.kwonlyargs:
                if argument.arg in ("self", "cls"):
                    continue
                if argument.annotation is None:
                    missing.append(f"{where} ({argument.arg})")
            for argument in (node.args.vararg, node.args.kwarg):
                if argument is not None and argument.annotation is None:
                    missing.append(f"{where} ({argument.arg})")
    return missing


class PyTypedMarkerTests(unittest.TestCase):
    def test_marker_is_installed(self) -> None:
        marker = files("kernlens").joinpath("py.typed")
        self.assertTrue(marker.is_file())

    def test_marker_marks_a_complete_package(self) -> None:
        marker = files("kernlens").joinpath("py.typed")
        content = marker.read_text(encoding="utf-8").strip()
        # An empty marker means "every module in this distribution is
        # typed".  PEP 561 reserves ``partial`` for a *stub* package that
        # covers only part of a distribution; it is not the spelling of
        # "some inline annotations are missing".  If this package ever
        # stops being fully typed, the annotations are the thing to fix.
        self.assertEqual(
            content, "",
            "py.typed must be empty while the package declares itself fully "
            "typed; 'partial' is for partial stub packages, not for a "
            "distribution with gaps in its inline annotations",
        )

    def test_every_function_is_annotated(self) -> None:
        """The empty marker is a claim; this is the check behind it.

        The marker itself only says "type checkers should read this
        package".  Without this test an unannotated function could appear
        while the marker kept claiming completeness.  ``self``/``cls`` are
        skipped because their types are implied.
        """
        self.assertEqual(_unannotated_functions(), [])

    def test_marker_is_declared_for_wheel_and_sdist(self) -> None:
        """The source marker is not enough; the build must ship it.

        ``test_marker_is_installed`` runs against ``src/`` because pytest
        sets ``pythonpath = ["src"]``, so it cannot notice a package-data
        entry that was dropped from ``pyproject.toml``.  These two lines
        are what put the marker in the wheel and the sdist.
        """
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('kernlens = ["py.typed"]', pyproject)
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("include src/kernlens/py.typed", manifest)

    def test_version_is_exported(self) -> None:
        self.assertIsInstance(kernlens.__version__, str)
        self.assertIn("__version__", kernlens.__all__)
