"""The compatibility page must not drift from the things it describes.

The page's whole value is that its words mean something: *measured* points
at a capture, *expected* points at a requirement, *unsupported* points at
a boundary.  A table of environments is exactly the kind of document that
rots silently -- the kernel version stays 6.1.134 after the capture moves
to 6.2, the Python range stays 3.10--3.13 after the CI matrix grows a
version -- so the parts that can be checked without a debuggee are checked
here.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "compatibility.md"

#: The vocabulary the page defines.  A new word has to be defined there
#: before it can be used, or the table stops being readable as a claim.
STATUSES = frozenset(
    {"measured", "measured in tests", "expected", "unsupported"}
)


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _matrix_rows(text: str) -> list[list[str]]:
    """Rows of the first table under ``## Matrix``, split into cells."""
    lines = text.splitlines()
    start = lines.index("## Matrix")
    table: list[str] = []
    for line in lines[start:]:
        if line.startswith("|"):
            table.append(line)
        elif table:
            break
    rows = []
    for line in table[2:]:  # header and the ``| --- |`` separator
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def _status(cells: list[str]) -> str:
    return cells[5].strip("`").strip()


def _python_matrix() -> list[tuple[int, int]]:
    """The CI matrix, as ``(major, minor)`` pairs, sorted."""
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8",
    )
    match = re.search(r"python-version: \[([^\]]+)\]", text)
    if match is None:  # pragma: no cover - the matrix is in the workflow
        raise AssertionError("ci.yml has no python-version matrix")
    return sorted(
        (int(major), int(minor))
        for major, minor in re.findall(r'"(\d+)\.(\d+)"', match.group(1))
    )


def _requires_python() -> tuple[int, int]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text)
    if match is None:  # pragma: no cover - pyproject declares it
        raise AssertionError("pyproject.toml has no requires-python floor")
    return int(match.group(1)), int(match.group(2))


class PlacementTests(unittest.TestCase):
    def test_the_page_exists(self) -> None:
        self.assertTrue(PAGE.is_file())

    def test_both_readmes_link_it(self) -> None:
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("(docs/compatibility.md)", text)

    def test_the_architecture_tree_lists_it(self) -> None:
        text = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertIn("compatibility.md", text)


class MatrixTests(unittest.TestCase):
    def test_every_row_uses_a_defined_status(self) -> None:
        rows = _matrix_rows(_page())
        self.assertGreater(len(rows), 5)
        for cells in rows:
            with self.subTest(row=cells[0]):
                self.assertEqual(len(cells), 7, cells)
                self.assertIn(_status(cells), STATUSES)

    def test_all_four_claims_are_represented(self) -> None:
        # A page that only lists "expected" rows has not measured
        # anything; one that only lists "measured" rows has no boundaries.
        seen = {_status(cells) for cells in _matrix_rows(_page())}
        self.assertEqual(seen, STATUSES)

    def test_every_row_names_its_evidence(self) -> None:
        for cells in _matrix_rows(_page()):
            with self.subTest(row=cells[0]):
                self.assertTrue(cells[6], "a status without evidence")

    def test_the_unsupported_rows_name_the_x86_64_boundary(self) -> None:
        rows = [
            cells for cells in _matrix_rows(_page())
            if _status(cells) == "unsupported"
        ]
        self.assertTrue(
            any("x86_64" in cell for cells in rows for cell in cells),
            [cells[0] for cells in rows],
        )

    def test_the_measured_kernel_is_the_capture_kernel(self) -> None:
        capture = json.loads(
            (ROOT / "tools" / "tutorial_capture.json").read_text(
                encoding="utf-8",
            )
        )
        kernel = capture["context"]["kernel"]
        self.assertIn(kernel, _page())


class InterpreterTests(unittest.TestCase):
    def test_the_page_separates_the_two_interpreters(self) -> None:
        text = _page()
        self.assertIn("GDB's embedded Python", text)
        self.assertIn("Host Python", text)
        self.assertIn("kernlens doctor", text)
        self.assertIn("sys.path", text)

    def test_the_python_floor_matches_pyproject(self) -> None:
        major, minor = _requires_python()
        self.assertIn(f"{major}.{minor}", _page())
        self.assertIn("requires-python", _page())

    def test_the_documented_range_matches_the_ci_matrix(self) -> None:
        """The page spells the range; CI is the measurement.

        The range notation is only honest while the matrix is contiguous,
        so a gap in CI fails here too: ``3.10 -- 3.13`` would no longer
        describe what is tested.
        """
        matrix = _python_matrix()
        self.assertGreaterEqual(len(matrix), 2)
        for before, after in zip(matrix, matrix[1:]):
            with self.subTest(before=before, after=after):
                self.assertEqual(before[0], after[0])
                self.assertEqual(after[1], before[1] + 1)

        low = "{}.{}".format(*matrix[0])
        high = "{}.{}".format(*matrix[-1])
        self.assertEqual(low, "{}.{}".format(*_requires_python()))
        self.assertIn(f"{low} -- {high}", _page())


class SupportWindowTests(unittest.TestCase):
    def test_the_window_matches_security_md(self) -> None:
        page = _page()
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        for text in (page, security):
            # Both wrap the sentence, so match the words, not the line.
            self.assertRegex(text, r"not\s+back-patched")
        self.assertIn("SECURITY.md", page)


if __name__ == "__main__":
    unittest.main()
