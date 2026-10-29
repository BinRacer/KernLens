"""The documentation site must be generated, reachable, and buildable.

The site is assembled from pages that already existed plus two generated
index pages.  Two failure modes matter: a page that is published but not
in the nav (so nobody finds it), and a generated file that was edited by
hand (so the README and the front page disagree).  Both are cheap to
check here; ``mkdocs build --strict`` in CI covers the rest.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import gen_docs_site

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
MKDOCS = ROOT / "mkdocs.yml"

_LOCAL_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _mkdocs() -> str:
    return MKDOCS.read_text(encoding="utf-8")


def _nav() -> list[tuple[str, str]]:
    return gen_docs_site.nav_entries(_mkdocs())


def _local_targets(text: str) -> list[str]:
    """Relative link targets in *text*, with the fragment removed."""
    targets = []
    for match in _LOCAL_LINK.finditer(text):
        target = match.group(1)
        if gen_docs_site._is_external(target):
            continue
        path = target.partition("#")[0]
        if path:
            targets.append(path)
    return targets


class GeneratedFileTests(unittest.TestCase):
    def test_the_committed_files_match_the_generator(self) -> None:
        for path, content in gen_docs_site.generate().items():
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertEqual(
                    path.read_text(encoding="utf-8"), content,
                    "run tools/gen_docs_site.py",
                )

    def test_each_generated_page_names_its_source(self) -> None:
        for path in (DOCS / "index.md", DOCS / "zh-CN.md"):
            with self.subTest(path=path.name):
                first = path.read_text(encoding="utf-8").splitlines()[0]
                self.assertIn("tools/gen_docs_site.py", first)

    def test_no_link_still_points_at_the_checkout(self) -> None:
        # ``docs/api.md`` from ``docs/index.md`` would 404 under mkdocs:
        # it has to become ``api.md``.  A ``../`` target is worse, because
        # mkdocs cannot see the file at all.
        for path in (DOCS / "index.md", DOCS / "zh-CN.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("](docs/", text)
                self.assertNotIn("](../", text)
                self.assertNotIn('href="../', text)
                self.assertNotIn('src="../', text)

    def test_every_relative_link_resolves_inside_the_site(self) -> None:
        for path in (DOCS / "index.md", DOCS / "zh-CN.md"):
            for target in _local_targets(path.read_text(encoding="utf-8")):
                with self.subTest(page=path.name, target=target):
                    self.assertTrue((DOCS / target).exists(), target)

    def test_the_language_switcher_is_absolute(self) -> None:
        # mkdocs does not rewrite raw HTML hrefs, so a relative one would
        # be emitted verbatim and point at a file that is not in the site.
        for path in (DOCS / "index.md", DOCS / "zh-CN.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                self.assertIn(f'href="{gen_docs_site.SITE}/"', text)
                self.assertIn(
                    f'href="{gen_docs_site.SITE}/zh-CN/"', text,
                )


class RenderedOutputTests(unittest.TestCase):
    """Published output blocks must be readable text, not ANSI escapes.

    A captured command prints its section labels through
    ``message.notice``, which wraps them in ``\\x1b[35m ... \\x1b[0m``.  A
    ```text``` fence cannot render that: the site showed a literal
    ``[35mAlias:[0m`` where the label should have been, and the same text
    was unreachable to a reader of the raw Markdown.

    Two separate defects produced it, and either one alone would have.
    The epilog was painted once at import time, so ``kl-color off`` could
    not undo it (see ``HelpColourTests``); and the capture ran
    ``kernlens-color on``, which left colour enabled for every case after
    it.  These tests guard the artifacts, whatever the cause, because the
    artifacts are what a reader sees.
    """

    #: Matches one SGR sequence: ``ESC [ params m``.
    _SGR = re.compile(r"\x1b\[[0-9;]*m")

    def test_no_published_page_contains_an_escape_sequence(self) -> None:
        offenders = []
        for path in sorted(DOCS.rglob("*.md")):
            if self._SGR.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [], "run tools/gen_tutorial.py")

    def test_no_generated_asset_contains_a_raw_escape(self) -> None:
        # ``docs/assets/demo.svg`` is XML: a bare ESC makes it malformed,
        # and ``demo.cast`` is a JSON text record.  Neither can carry
        # colour, so neither may contain the byte.
        for path in sorted((DOCS / "assets").iterdir()):
            if not path.is_file():
                continue
            with self.subTest(asset=path.name):
                raw = path.read_bytes()
                self.assertNotIn(b"\x1b", raw)

    def test_the_generators_strip_escapes_themselves(self) -> None:
        """The strip has to live in the renderer, not in the capture.

        A capture taken with colour on is a legitimate capture; the
        renderer is what has to make a reader-facing artifact out of it.
        Checking the source rather than the output means the guard still
        holds when someone re-captures on a fresh kernel.
        """
        for name in ("gen_tutorial.py", "gen_demo.py"):
            text = (ROOT / "tools" / name).read_text(encoding="utf-8")
            with self.subTest(tool=name):
                self.assertIn("_SGR", text)
                self.assertRegex(text, r'_SGR\s*=\s*re\.compile\(r?"')


class NavigationTests(unittest.TestCase):
    def test_every_nav_target_exists(self) -> None:
        for title, target in _nav():
            if gen_docs_site._is_external(target):
                continue
            with self.subTest(page=title):
                self.assertTrue((DOCS / target).is_file(), target)

    def test_every_page_is_reachable(self) -> None:
        """A page nobody links to is a page nobody reads.

        The 40 tutorial pages are reached from the generated index
        instead of being 40 nav entries, so that index is checked to name
        each of them.
        """
        nav = {target for _, target in _nav()}
        tutorial = (DOCS / "tutorial" / "README.md").read_text(
            encoding="utf-8",
        )
        for path in sorted(DOCS.rglob("*")):
            if not path.is_file() or path.suffix != ".md":
                continue
            relative = path.relative_to(DOCS).as_posix()
            if relative in nav:
                continue
            if relative.startswith("tutorial/"):
                self.assertIn(path.name, tutorial, relative)
                continue
            self.fail(f"{relative} is not in the nav")

    def test_every_nav_page_has_an_llms_note(self) -> None:
        for title, target in _nav():
            if gen_docs_site._is_external(target):
                continue
            with self.subTest(page=title):
                self.assertIn(target, gen_docs_site.PAGE_NOTES)

    def test_llms_lists_every_nav_page(self) -> None:
        text = (DOCS / "llms.txt").read_text(encoding="utf-8")
        for title, target in _nav():
            with self.subTest(page=title):
                url = (
                    target if gen_docs_site._is_external(target)
                    else gen_docs_site.page_url(target)
                )
                self.assertIn(f"[{title}]({url})", text)
                self.assertNotIn("//)", text)


class ConfigurationTests(unittest.TestCase):
    def test_the_site_url_matches_the_repository(self) -> None:
        """Renaming the repository has to move the site with it.

        The generated index uses absolute URLs, so a stale ``site_url``
        would send readers to the old name rather than fail loudly.
        """
        text = _mkdocs()
        repo = re.search(r"repo_url:\s*(\S+)", text)
        site = re.search(r"site_url:\s*(\S+)", text)
        self.assertIsNotNone(repo)
        self.assertIsNotNone(site)
        slug = repo.group(1).rstrip("/").rsplit("/", 2)[-2:]
        expected = f"https://{slug[0].lower()}.github.io/{slug[1]}/"
        self.assertEqual(site.group(1), expected)

    def test_the_docs_directory_is_the_site_root(self) -> None:
        text = _mkdocs()
        self.assertIn("docs_dir: docs", text)
        self.assertIn("site_dir: site", text)

    def test_the_build_output_is_ignored(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(ignored, r"(?m)^site/$")

    def test_ci_builds_the_site_strictly(self) -> None:
        """The build is the check; without it the site is unverified.

        ``--strict`` turns a broken internal link or a missing page into a
        failure, which is the only thing that distinguishes "the site
        builds" from "the Markdown files parse".
        """
        workflow = (
            ROOT / ".github" / "workflows" / "docs.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("mkdocs build --strict", workflow)
        self.assertIn("gen_docs_site.py --check", workflow)
        self.assertIn("deploy-pages", workflow)


if __name__ == "__main__":
    unittest.main()
