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
        # The banner is no longer the first line: the front matter has to
        # be, or mkdocs reads the whole block as prose.  So the claim is
        # "the page says where it came from", not "on line one".
        for path in (DOCS / "index.md", DOCS / "zh-CN" / "index.md"):
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                head = path.read_text(encoding="utf-8").splitlines()[:8]
                self.assertTrue(
                    any("tools/gen_docs_site.py" in line for line in head),
                    head,
                )

    def test_the_front_matter_is_the_first_thing_in_the_file(self) -> None:
        """YAML front matter only counts at the very top.

        A comment above it -- which is what the generator wrote first --
        silently demotes the block to prose and the page renders a stray
        horizontal rule plus the literal ``hide:`` lines.  Nothing else in
        the build reports that, so it is checked here.
        """
        for path in (DOCS / "index.md", DOCS / "zh-CN" / "index.md"):
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                first = path.read_text(encoding="utf-8").splitlines()[0]
                self.assertEqual(first, "---")

    def test_no_link_still_points_at_the_checkout(self) -> None:
        # ``docs/api.md`` from ``docs/index.md`` would 404 under mkdocs:
        # it has to become ``api.md``.  A ``docs/`` prefix means the
        # rewrite did not happen at all.
        for path in (DOCS / "index.md", DOCS / "zh-CN" / "index.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                self.assertNotIn("](docs/", text)

    def test_the_english_front_page_does_not_climb(self) -> None:
        """English is the default and lives at the site root.

        ``../`` from ``index.md`` would leave the site directory, which
        mkdocs cannot serve.  The Chinese page is the one that climbs,
        and it has to -- see the test below.
        """
        text = (DOCS / "index.md").read_text(encoding="utf-8")
        self.assertNotIn("](../", text)
        self.assertNotIn('href="../', text)
        self.assertNotIn('src="../', text)

    def test_the_chinese_page_climbs_exactly_one_level(self) -> None:
        """Every site path on the Chinese page needs one ``..``.

        ``docs/`` is the site root, so ``zh-CN/index.md`` is one directory
        down and an unprefixed ``assets/demo.svg`` would be emitted
        verbatim by mkdocs (raw HTML is not rewritten) and resolve to
        ``/zh-CN/assets/demo.svg`` -- a 404 that the English page never
        showed, because there the same wrong guess and the truth coincide.
        """
        text = (DOCS / "zh-CN" / "index.md").read_text(encoding="utf-8")
        self.assertIn('src="../assets/demo.svg"', text)
        self.assertNotIn('src="assets/', text)
        self.assertNotIn("](tutorial/", text)

    def test_every_relative_link_resolves_inside_the_site(self) -> None:
        for path in (DOCS / "index.md", DOCS / "zh-CN" / "index.md"):
            here = path.parent.relative_to(DOCS)
            for target in _local_targets(path.read_text(encoding="utf-8")):
                with self.subTest(
                    page=path.relative_to(DOCS).as_posix(), target=target,
                ):
                    self.assertTrue((DOCS / here / target).exists(), target)

    def test_the_generated_pages_carry_no_language_links(self) -> None:
        """The switcher belongs to the theme, not to the page body.

        The READMEs need their own switcher -- on GitHub those two files
        are all there is.  On the site the header has one on every page,
        so copying it in would put two identical controls on the front
        page, one of them linking to itself.  The generator drops it.
        """
        for path in (DOCS / "index.md", DOCS / "zh-CN" / "index.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                self.assertNotIn('README.zh-CN.md">', text)
                self.assertNotIn('README.md">English', text)

    def test_the_readmes_still_have_one(self) -> None:
        # Dropping it from the generated copy must not mean dropping it
        # from the file GitHub renders.
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn('README.md">English', text)


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


class LanguageLayoutTests(unittest.TestCase):
    """Each language owns a directory, and English owns the root.

    English is the default, so it stays where it was -- ``/`` should be
    the front page, not a redirect to ``/en/``.  Chinese lives under
    ``docs/zh-CN/``, which means it is one directory deeper than every
    page it links to.  That depth is the whole reason the demo image
    failed there and nowhere else, so it is checked rather than assumed.
    """

    def test_the_chinese_pages_are_in_their_own_directory(self) -> None:
        chinese = sorted(
            path.name for path in (DOCS / "zh-CN").glob("*.md")
        )
        self.assertEqual(chinese, ["api.md", "index.md"])
        # And no Chinese page is left loose in the root.
        self.assertEqual(
            [path.name for path in DOCS.glob("*.zh-CN.md")], [],
        )

    def test_no_english_page_grew_a_language_suffix(self) -> None:
        # ``index.md``, not ``index.en.md``: English is the default and
        # an unnamed page is what a default language should look like.
        self.assertEqual(list(DOCS.glob("*.en.md")), [])
        self.assertTrue((DOCS / "index.md").is_file())
        self.assertTrue((DOCS / "api.md").is_file())

    def test_the_nav_keeps_the_languages_apart(self) -> None:
        """One section per language, and only the Chinese one is nested."""
        nav = _nav()
        targets = [target for _, target in nav]
        self.assertIn("index.md", targets)
        self.assertIn("zh-CN/index.md", targets)
        self.assertNotIn("zh-CN.md", targets)
        # English pages do not live under a language directory.
        self.assertFalse(
            [t for t in targets if t.startswith("en/")], targets,
        )

    def test_the_chinese_pages_declare_themselves_chinese(self) -> None:
        """``<html lang>`` is per page, and the theme has one value.

        ``mkdocs-material`` writes ``lang="{{ lang.t('language') }}"`` from
        ``theme.language``, which is site-wide, so the Chinese pages were
        served as ``lang="en"``.  That reaches further than the attribute:
        mkdocs-material feeds it to search, so Chinese text got an English
        stemmer and was effectively unsearchable.

        The tag is outside every ``{% block %}``, so it cannot be
        overridden by a template that still extends the theme; the hook in
        ``hooks/language.py`` rewrites it after rendering instead.  The
        unit test drives the hook directly, because ``mkdocs build`` is
        not something the test suite runs.
        """
        import language

        config = type("Config", (), {"docs_dir": str(DOCS)})()
        chinese = type(
            "Page", (), {"file": type("File", (), {"src_uri": "zh-CN/api.md"})()},
        )()
        english = type(
            "Page", (), {"file": type("File", (), {"src_uri": "api.md"})()},
        )()
        rendered = '<html lang="en" class="no-js">'

        self.assertEqual(
            language.on_post_page(rendered, page=chinese, config=config),
            '<html lang="zh-CN" class="no-js">',
        )
        self.assertEqual(
            language.on_post_page(rendered, page=english, config=config),
            rendered,
        )

    def test_the_language_hook_is_configured(self) -> None:
        self.assertIn("hooks/language.py", _mkdocs())
        self.assertTrue((ROOT / "hooks" / "language.py").is_file())


class LanguageSwitcherTests(unittest.TestCase):
    """The switcher has to be in the header, reachable, and honest.

    It is the theme's own `partials/alternate.html`, rendered from
    `extra.alternate`, so it sits on the same row as the palette toggle
    and the search box.  An earlier version put a button of its own in the
    content area: it worked, but it read as part of the page rather than
    as a site-wide control, and it pushed the front page down a row.

    mkdocs.yml is therefore the source of truth, and `overrides/main.html`
    must not carry the switcher a second time.
    """

    OVERRIDE = ROOT / "overrides" / "main.html"

    #: The `extra.alternate` entries, as `(name, link, lang)`.
    #:
    #: Parsed with a regex rather than a YAML loader: the config contains
    #: `!!python/object/apply:pymdownx.slugs.slugify`, which `safe_load`
    #: refuses and `unsafe_load` would execute.  The block is three keys
    #: on three lines, so a small reader is the honest option.
    _ALT_ENTRY = re.compile(
        r"^\s+-\s+name:\s*(?P<name>.+?)\s*$\n"
        r"^\s+link:\s*(?P<link>\S+)\s*$\n"
        r"^\s+lang:\s*(?P<lang>\S+)\s*$",
        re.MULTILINE,
    )

    @classmethod
    def _alternate(cls) -> list[tuple[str, str, str]]:
        text = _mkdocs()
        start = text.index("alternate:")
        # The block ends at the next top-level key.
        rest = text[start:].splitlines()[1:]
        block = []
        for line in rest:
            if line and not line[0].isspace():
                break
            block.append(line)
        return [
            (m.group("name"), m.group("link"), m.group("lang"))
            for m in cls._ALT_ENTRY.finditer("\n".join(block))
        ]

    def test_the_switcher_is_the_themes_own(self) -> None:
        """It is configured, not hand-written.

        A custom control has to re-implement the header slot, the icon,
        and the dropdown, and then it drifts from the theme.  The four
        keys are read straight from the config, so a rename here fails
        rather than silently rendering nothing.
        """
        entries = self._alternate()
        self.assertEqual([entry[2] for entry in entries], ["en", "zh-CN"])

    def test_the_override_does_not_carry_a_second_switcher(self) -> None:
        text = self.OVERRIDE.read_text(encoding="utf-8")
        self.assertNotIn("md-select", text)
        self.assertNotIn("kl-lang-bar", text)

    def test_the_stylesheet_has_no_orphan_switcher_rules(self) -> None:
        # `extra.css` used to style `.kl-lang`; the class is gone, and a
        # rule for markup that does not exist is worse than no rule --
        # it reads like the control is still there.
        css = (DOCS / "assets" / "extra.css").read_text(encoding="utf-8")
        self.assertNotIn(".kl-lang", css)

    def test_both_languages_are_offered(self) -> None:
        entries = self._alternate()
        names = [name for name, _, _ in entries]
        self.assertIn("English", names)
        self.assertIn("简体中文", names)

    def test_the_switcher_targets_a_page_that_exists(self) -> None:
        """Whatever the entries point at has to be a published page.

        Only two pages exist in Chinese, so the switcher lands on the
        Chinese front page rather than a translation of the current one.
        If that page were ever renamed, this is the test that notices.
        """
        for _, url, _ in self._alternate():
            with self.subTest(url=url):
                self.assertTrue(
                    url.startswith(gen_docs_site.SITE), url,
                )
                relative = url[len(gen_docs_site.SITE):].strip("/")
                page = (
                    DOCS / relative / "index.md" if relative
                    else DOCS / "index.md"
                )
                self.assertTrue(page.is_file(), page)

    def test_the_links_are_absolute(self) -> None:
        # The switcher appears on pages at different depths, and raw
        # config links are emitted as given.
        for _, url, _ in self._alternate():
            with self.subTest(url=url):
                self.assertTrue(url.startswith("https://"), url)


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
