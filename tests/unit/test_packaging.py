"""Packaging checks for the PEP 561 ``py.typed`` marker."""

from __future__ import annotations

import unittest
from importlib.resources import files

import kernlens


class PyTypedMarkerTests(unittest.TestCase):
    def test_marker_is_installed(self) -> None:
        marker = files("kernlens").joinpath("py.typed")
        self.assertTrue(marker.is_file())

    def test_marker_marks_a_complete_package(self) -> None:
        marker = files("kernlens").joinpath("py.typed")
        content = marker.read_text(encoding="utf-8").strip()
        self.assertEqual(
            content, "",
            "py.typed must be empty for a fully typed package; "
            "use 'partial' only for a partial distribution",
        )

    def test_version_is_exported(self) -> None:
        self.assertIsInstance(kernlens.__version__, str)
        self.assertIn("__version__", kernlens.__all__)