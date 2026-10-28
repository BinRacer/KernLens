"""The release gate has to fail before a tag does.

`tools/release.py` is the only thing standing between a tag and a PyPI
version that cannot be replaced, so its checks are tested against
deliberately broken inputs rather than only against the current tree.
The workflow is read as text for the same reason: the trusted-publishing
setup is a few lines in a YAML file, and deleting one of them turns a
release into a job that fails after the tag is already public.
"""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path

import kernlens
import release

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

#: A changelog with two releases, so section boundaries can be tested.
CHANGELOG = """# Changelog

## [1.2.3] - 2026-01-02

### Added

- a thing that shipped

### Fixed

- another thing that shipped

## [1.2.2] - 2025-12-01

### Fixed

- the previous release
"""

CITATION = """cff-version: 1.2.0
title: KernLens
version: 1.2.3
date-released: 2026-01-02
"""

RELEASED = datetime.date(2026, 1, 3)


def _changelog(body: str) -> str:
    """A changelog whose 1.2.3 section is *body*."""
    return "# Changelog\n\n## [1.2.3] - 2026-01-02\n\n" + body + "\n"


class CurrentTreeTests(unittest.TestCase):
    """The tree that is about to be tagged, checked as it stands."""

    def test_the_current_tree_is_releasable(self) -> None:
        self.assertEqual(release.check(), [])

    def test_the_current_tag_matches_the_package(self) -> None:
        self.assertEqual(release.check(f"v{kernlens.__version__}"), [])

    def test_the_current_notes_are_not_empty(self) -> None:
        text = release.notes()
        self.assertIn("\n## ", text)
        self.assertIn("- ", text)

    def test_citation_cff_is_in_the_repository(self) -> None:
        text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {kernlens.__version__}", text)
        self.assertIn("date-released:", text)


class TagTests(unittest.TestCase):
    def test_a_different_tag_is_rejected(self) -> None:
        problems = release.check(
            "v0.4.0", changelog=CHANGELOG, citation=CITATION,
            version="1.2.3", today=RELEASED,
        )
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("v0.4.0", problems[0])
        self.assertIn("1.2.3", problems[0])

    def test_a_tag_without_the_prefix_is_rejected(self) -> None:
        problems = release.check(
            "1.2.3", changelog=CHANGELOG, citation=CITATION,
            version="1.2.3", today=RELEASED,
        )
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("does not start with 'v'", problems[0])

    def test_no_tag_is_not_a_problem(self) -> None:
        # The gate runs before the tag exists, which is the point.
        self.assertEqual(
            release.check(
                changelog=CHANGELOG, citation=CITATION,
                version="1.2.3", today=RELEASED,
            ),
            [],
        )


class ChangelogTests(unittest.TestCase):
    def test_a_missing_section_is_rejected(self) -> None:
        problems = release.check(
            changelog="# Changelog\n\n## [1.0.0] - 2025-01-01\n\n- old\n",
            citation=CITATION, version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("no '## [1.2.3]' section" in p for p in problems))

    def test_an_undated_section_is_rejected(self) -> None:
        problems = release.check(
            changelog=_changelog("- a thing").replace(
                "## [1.2.3] - 2026-01-02", "## [1.2.3]",
            ),
            citation=CITATION, version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("no release date" in p for p in problems))

    def test_an_empty_section_is_rejected(self) -> None:
        problems = release.check(
            changelog=_changelog(""),
            citation=CITATION, version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("has no entries" in p for p in problems))

    def test_a_future_date_is_rejected(self) -> None:
        problems = release.check(
            changelog=CHANGELOG, citation=CITATION, version="1.2.3",
            today=datetime.date(2026, 1, 1),
        )
        self.assertTrue(any("is in the future" in p for p in problems))

    def test_the_section_ends_at_the_next_heading(self) -> None:
        # A missing boundary would make every release note contain the
        # history below it.
        body = release.section("1.2.3", changelog=CHANGELOG)
        assert body is not None
        date, text = body
        self.assertEqual(date, "2026-01-02")
        self.assertIn("a thing that shipped", text)
        self.assertNotIn("the previous release", text)


class NotesTests(unittest.TestCase):
    def test_headings_are_shifted_one_level(self) -> None:
        text = release.notes("1.2.3", changelog=CHANGELOG)
        self.assertTrue(text.startswith("## Added"), text)
        self.assertIn("\n## Fixed", text)
        self.assertNotIn("### ", text)

    def test_the_notes_stop_at_the_next_release(self) -> None:
        text = release.notes("1.2.3", changelog=CHANGELOG)
        self.assertNotIn("the previous release", text)

    def test_a_missing_section_fails_instead_of_printing_nothing(self) -> None:
        with self.assertRaises(SystemExit):
            release.notes("9.9.9", changelog=CHANGELOG)

    def test_an_empty_section_fails(self) -> None:
        with self.assertRaises(SystemExit):
            release.notes("1.2.3", changelog=_changelog(""))


class CitationTests(unittest.TestCase):
    def test_a_version_drift_is_rejected(self) -> None:
        problems = release.check(
            changelog=CHANGELOG,
            citation=CITATION.replace("version: 1.2.3", "version: 1.2.2"),
            version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("CITATION.cff says 1.2.2" in p for p in problems))

    def test_a_date_drift_is_rejected(self) -> None:
        problems = release.check(
            changelog=CHANGELOG,
            citation=CITATION.replace(
                "date-released: 2026-01-02", "date-released: 2025-12-31",
            ),
            version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("CITATION.cff says 2025-12-31" in p for p in problems))

    def test_a_missing_version_is_rejected(self) -> None:
        problems = release.check(
            changelog=CHANGELOG,
            citation="cff-version: 1.2.0\ndate-released: 2026-01-02\n",
            version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("has no version" in p for p in problems))

    def test_a_missing_date_is_rejected(self) -> None:
        problems = release.check(
            changelog=CHANGELOG,
            citation="cff-version: 1.2.0\nversion: 1.2.3\n",
            version="1.2.3", today=RELEASED,
        )
        self.assertTrue(any("has no date-released" in p for p in problems))


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_it_runs_on_a_version_tag_only(self) -> None:
        self.assertIn('tags: ["v*"]', self.text)

    def test_it_checks_the_release_files_before_building(self) -> None:
        self.assertIn("tools/release.py check", self.text)

    def test_it_runs_the_test_suite(self) -> None:
        # A tag can point at a commit no pull request ever tested.
        self.assertIn("pytest -q", self.text)

    def test_it_checks_the_built_distributions(self) -> None:
        self.assertIn("tools/check_wheel.py", self.text)
        self.assertIn("twine check", self.text)

    def test_it_publishes_through_trusted_publishing(self) -> None:
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", self.text)
        self.assertIn("id-token: write", self.text)
        self.assertIn("name: pypi", self.text)
        # A stored token would defeat the point of the environment.
        self.assertNotIn("password:", self.text)

    def test_pypi_is_published_before_the_github_release(self) -> None:
        # Reversing this would leave a release whose artifacts failed to
        # upload.  The dependency is what enforces the order.
        self.assertLess(
            self.text.index("publish-pypi:"),
            self.text.index("github-release:"),
        )
        self.assertIn("needs: [build, publish-pypi]", self.text)

    def test_the_release_carries_the_distributions_and_the_demo(self) -> None:
        self.assertIn("gh release create", self.text)
        self.assertIn("dist/*", self.text)
        self.assertIn("docs/assets/demo.cast", self.text)

    def test_the_rehearsal_targets_testpypi(self) -> None:
        self.assertIn("inputs.index == 'testpypi'", self.text)
        self.assertIn("https://test.pypi.org/legacy/", self.text)


class DependencyGroupTests(unittest.TestCase):
    def test_twine_is_a_release_group_not_a_dev_dependency(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        lines = text.splitlines()
        start = lines.index("[dependency-groups]") + 1
        end = next(
            index for index in range(start, len(lines))
            if lines[index].startswith("[")
        )
        block = "\n".join(lines[start:end])

        dev_start = block.index("dev = [")
        dev_end = block.index("\n]", dev_start)
        self.assertNotIn("twine", block[dev_start:dev_end])

        release_line = next(
            line for line in block.splitlines()
            if line.startswith("release = [")
        )
        self.assertIn("twine", release_line)


if __name__ == "__main__":
    unittest.main()
