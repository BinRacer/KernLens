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
_NAV_ENTRY = re.compile(r"^\s*-\s+(?P<title>[^:]+):\s+(?P<target>\S+)\s*$")


def _mkdocs() -> str:
    return MKDOCS.read_text(encoding="utf-8")


def _nav() -> list[tuple[str, str]]:
    return gen_docs_site.nav_entries(_mkdocs())


def _is_url(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))


def _page(src_uri: str, *, locale: str, url: str = ""):
    """A stand-in for the ``Page`` that ``on_post_page`` receives.

    Only three attributes are read -- ``file.src_uri``, ``file.locale``
    and ``file`` itself -- so a namespace is enough, and it says which
    ones the hook actually depends on.  ``locale`` is separate from
    ``src_uri`` on purpose: for a fallback page they disagree, and that
    disagreement is the whole point of the language rule.
    """
    file = type("File", (), {"src_uri": src_uri, "locale": locale})()
    return type("Page", (), {"file": file, "url": url, "title": ""})()


def _locale_nav(mkdocs: str, locale: str) -> list[tuple[str, str]]:
    """The ``nav`` one locale overrides, as ``(title, target)`` pairs.

    A locale's nav lives under ``plugins.i18n.languages`` and is indented
    by a different amount from the top-level one, so it cannot be read by
    the same scan.  The block is found by its own ``locale:`` line and
    then followed until the indentation drops back.
    """
    lines = mkdocs.splitlines()
    start = next(
        index for index, line in enumerate(lines)
        if line.strip() == f"- locale: {locale}"
    )
    indent = len(lines[start]) - len(lines[start].lstrip())
    entries: list[tuple[str, str]] = []
    inside = False
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        if line.strip() == "nav:":
            inside = True
            continue
        if not inside:
            continue
        match = _NAV_ENTRY.match(line)
        if match is not None:
            entries.append(
                (match.group("title").strip(), match.group("target"))
            )
    return entries


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
        for path in (DOCS / "en" / "index.md", DOCS / "zh-CN" / "index.md"):
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
        for path in (DOCS / "en" / "index.md", DOCS / "zh-CN" / "index.md"):
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                first = path.read_text(encoding="utf-8").splitlines()[0]
                self.assertEqual(first, "---")

    def test_no_link_still_points_at_the_checkout(self) -> None:
        # ``docs/api.md`` from ``docs/index.md`` would 404 under mkdocs:
        # it has to become ``api.md``.  A ``docs/`` prefix means the
        # rewrite did not happen at all.
        for path in (DOCS / "en" / "index.md", DOCS / "zh-CN" / "index.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(DOCS).as_posix()):
                self.assertNotIn("](docs/", text)

    def test_the_english_front_page_does_not_climb(self) -> None:
        """English is the default and is published at the site root.

        The page is one directory down *on disk*, which is what a naive
        depth count sees -- but the i18n plugin strips ``en/`` when it
        builds, so the page is at ``/`` and ``../assets/demo.svg`` leaves
        the site.  A raw-HTML ``src`` is not rewritten by mkdocs, so the
        wrong prefix reaches the browser and 404s.  The climb is measured
        in published depth, not source depth.
        """
        text = (DOCS / "en" / "index.md").read_text(encoding="utf-8")
        self.assertIn('src="assets/demo.svg"', text)
        self.assertNotIn('src="../', text)
        self.assertNotIn('href="../', text)

    def test_the_chinese_page_climbs_exactly_one_level(self) -> None:
        """Chinese keeps its directory, so it climbs out of it once.

        ``/zh-CN/`` is one level below the root, and ``assets/demo.svg``
        is served once, at the root.  An unprefixed path would be emitted
        verbatim and resolve to ``/zh-CN/assets/demo.svg`` -- a 404 that
        the English page never showed, because there the wrong guess and
        the truth coincided.
        """
        text = (DOCS / "zh-CN" / "index.md").read_text(encoding="utf-8")
        self.assertIn('src="../assets/demo.svg"', text)
        self.assertNotIn('src="assets/', text)
        self.assertNotIn('src="../../', text)

    def test_every_relative_link_resolves_inside_the_site(self) -> None:
        for path in (DOCS / "en" / "index.md", DOCS / "zh-CN" / "index.md"):
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
        for path in (DOCS / "en" / "index.md", DOCS / "zh-CN" / "index.md"):
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


class PathRewriteTests(unittest.TestCase):
    """Relative depth is a property of the URL, not of the source tree.

    The two differ exactly once, and it is the case that broke: the
    default language is stored one directory down (``docs/en/index.md``)
    but published at the site root.  Counting source separators made the
    English front page emit ``../assets/demo.svg``, which leaves the site
    from ``/``; a raw-HTML ``src`` is never rewritten by mkdocs, so the
    browser requested it and 404'd while the Chinese page -- where the
    naive count happens to be right -- rendered fine.
    """

    def test_raw_html_depth_follows_the_published_url(self) -> None:
        for dest, expected in (
            ("en/index.md", "assets/demo.svg"),
            ("zh-CN/index.md", "../assets/demo.svg"),
            # Use directory URLs, so a page that is not an index is
            # served one level deeper: ``/tutorial/kl-help/``.
            ("en/tutorial/kl-help.md", "../../assets/demo.svg"),
            ("zh-CN/tutorial/README.md", "../../assets/demo.svg"),
        ):
            with self.subTest(dest=dest):
                self.assertEqual(
                    gen_docs_site.rewrite_attribute("src", "docs/assets/demo.svg", dest),
                    expected,
                )

    def test_markdown_links_climb_out_of_the_language_directory(self) -> None:
        """Assets are shared; pages are duplicated per locale.

        ``commands.md`` exists beside the page in both languages, so the
        link stays flat.  ``assets/demo.cast`` exists once, at the root,
        so a page in a language directory climbs to it -- and ``docs/``
        prefixes never reach the output, because mkdocs cannot serve them.
        """
        self.assertEqual(
            gen_docs_site.rewrite_target("docs/en/commands.md", "en/index.md"),
            "commands.md",
        )
        # ``docs/en/commands.md`` names the default language's file, but
        # the locale is chosen by the page: on a Chinese page it means
        # "the Chinese commands page", which exists.
        self.assertEqual(
            gen_docs_site.rewrite_target("docs/en/commands.md", "zh-CN/index.md"),
            "commands.md",
        )
        self.assertEqual(
            gen_docs_site.rewrite_target("docs/assets/demo.cast", "zh-CN/index.md"),
            "../assets/demo.cast",
        )

    def test_an_untranslated_page_falls_back_to_the_default_language(self) -> None:
        """A missing translation must link somewhere that exists.

        The fallback order is the plugin's own: this locale, then the
        default, then the root.  ``tutorial`` has a Chinese index but no
        Chinese command pages, so it resolves inside ``zh-CN`` while a
        page nobody has translated resolves into ``en``.
        """
        self.assertEqual(
            gen_docs_site.rewrite_target(
                "docs/en/tutorial/README.md", "zh-CN/index.md",
            ),
            "tutorial/README.md",
        )
        # ``releasing.md`` has a Chinese translation, so it stays flat;
        # a command page does not, so the link crosses into ``en/``.  Both
        # resolve to a file that exists in the build.
        self.assertEqual(
            gen_docs_site.rewrite_target("docs/en/releasing.md", "zh-CN/index.md"),
            "releasing.md",
        )
        self.assertEqual(
            gen_docs_site.rewrite_target(
                "docs/en/tutorial/kl-help.md", "zh-CN/index.md",
            ),
            "../en/tutorial/kl-help.md",
        )

    def test_an_asset_outside_docs_is_copied_not_linked(self) -> None:
        """The site must not fetch its only image from GitHub.

        ``images/banner.svg`` sits beside ``src/``, so mkdocs does not
        publish it, and the front page linked
        ``raw.githubusercontent.com/.../main/images/banner.svg`` instead.
        That has three consequences a reader would not guess: the site
        depends on a third party for an image, the banner shown is
        whatever is on ``main`` rather than the commit being built, and a
        fork's site displays the upstream banner.

        The asset is copied into ``docs/assets/`` now and referenced
        relatively, so the same two pages work at either depth.
        """
        self.assertIn("images/banner.svg", gen_docs_site.COPIED_ASSETS)
        self.assertEqual(
            gen_docs_site.rewrite_attribute("src", "images/banner.svg", "en/index.md"),
            "assets/banner.svg",
        )
        self.assertEqual(
            gen_docs_site.rewrite_attribute(
                "src", "images/banner.svg", "zh-CN/index.md",
            ),
            "../assets/banner.svg",
        )

    def test_the_copied_assets_are_committed_and_match(self) -> None:
        """A copy that is not regenerated is a banner that stops updating.

        This is the failure the user reported: the SVG was edited and the
        docs site kept showing the old one.  The banner is generated now,
        so ``gen_docs_site.py --check`` compares it like any other
        generated page -- and this asserts the comparison actually covers
        it, rather than trusting that it does.
        """
        generated = gen_docs_site.generate()
        for asset in gen_docs_site.COPIED_ASSETS:
            copy = DOCS / "assets" / Path(asset).name
            with self.subTest(asset=asset):
                self.assertIn(copy, generated)
                self.assertTrue(copy.is_file(), f"{copy} is missing")
                self.assertEqual(
                    copy.read_text(encoding="utf-8"),
                    (ROOT / asset).read_text(encoding="utf-8"),
                    f"{copy.relative_to(ROOT)} is stale; "
                    "run tools/gen_docs_site.py",
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
        #
        # Binary assets are skipped, and that is not a loophole: a PNG's
        # bytes are zlib streams, so 0x1b occurs as data rather than as an
        # escape sequence, and it is impossible to render text into a PNG
        # in the first place.  The check is about a *text* artifact that
        # claims to be colour-free, which is the failure that happened.
        text_suffixes = {".svg", ".cast", ".css", ".txt", ".md"}
        for path in sorted((DOCS / "assets").iterdir()):
            if not path.is_file() or path.suffix not in text_suffixes:
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
    def test_the_sidebar_lists_every_registry_command(self) -> None:
        """The sidebar is generated from the registry, not written by hand.

        A command page that exists but is missing from the sidebar is the
        failure this catches: the page builds, the URL works, and nobody
        finds it.  It is a real risk because the list is 30 entries long
        and the nav is 200 lines of YAML.
        """
        listed = {target for _, target in _nav()}
        expected = {page for _category, _name, page in
                    gen_docs_site.command_pages()}
        self.assertEqual(expected - listed, set())
        self.assertEqual(len(expected), 30)

    def test_every_command_page_is_grouped_by_its_kl_help_category(
        self,
    ) -> None:
        """The sidebar's groups are `kl-help`'s groups, in its order.

        A reader who learned the taxonomy from `kl-help` should meet the
        same eight headings on the site.  Sorting them differently, or
        inventing a group, would make the two disagree for no gain.
        """
        categories = [
            category for category, _name, _page
            in gen_docs_site.command_pages()
        ]
        seen: list[str] = []
        for category in categories:
            if not seen or seen[-1] != category:
                seen.append(category)
        self.assertEqual(
            seen, [c for c in gen_docs_site.category_order() if c in seen],
        )

    def test_every_nav_target_exists(self) -> None:
        for title, target in _nav():
            if gen_docs_site._is_external(target):
                continue
            with self.subTest(page=title):
                self.assertTrue((DOCS / target).is_file(), target)

    def test_every_page_is_reachable(self) -> None:
        """A page nobody links to is a page nobody reads.

        Two kinds of page are not nav entries, and each has a different
        reason, so each is checked differently:

        - the 30 tutorial pages are reached from the generated index, and
          every language's index has to name them -- the pages themselves
          are not translated, so the Chinese index links to them where
          they are published (see ``LINK_DIR``);
        - the Chinese pages are reached from the header switcher, which is
          the same control on every page, and each locale overrides
          ``nav`` so they are nav entries of their own build -- checked
          here against ``llms.txt``, which lists them at their own URLs;
        - anything else has no excuse and fails.
        """
        nav = {target for _, target in _nav()}
        indexes = {
            locale: (DOCS / locale / "tutorial" / "README.md").read_text(
                encoding="utf-8",
            )
            for locale in ("en", "zh-CN")
        }
        llms = (DOCS / "llms.txt").read_text(encoding="utf-8")
        for path in sorted(DOCS.rglob("*")):
            if not path.is_file() or path.suffix != ".md":
                continue
            relative = path.relative_to(DOCS).as_posix()
            if relative in nav:
                continue
            locale, _, rest = relative.partition("/")
            if rest.startswith("tutorial/") and path.stem.startswith("kl-"):
                self.assertIn(path.name, indexes[locale], relative)
                continue
            if locale == "zh-CN":
                self.assertIn(
                    gen_docs_site.page_url(relative), llms, relative,
                )
                continue
            self.fail(f"{relative} is not in the nav")

    def test_every_locale_directory_is_backed_by_the_plugin(self) -> None:
        """Two directories on disk, two locales in the build.

        ``docs_structure: folder`` pairs ``en/x.md`` with ``zh-CN/x.md``
        by path, so a directory that the plugin does not know about is
        published under its own name instead of being treated as a
        language.  ``fallback_to_default`` is what keeps a page published
        in Chinese when nobody has translated it yet.
        """
        text = _mkdocs()
        self.assertIn("docs_structure: folder", text)
        self.assertIn("fallback_to_default: true", text)
        configured = set(re.findall(r"locale:\s*(\S+)", text))
        # Every directory that holds pages is a locale, and every locale
        # has a directory.  A directory missing from the config would be
        # published at ``/its-own-name/`` with no nav of its own.
        on_disk = {
            path.name for path in DOCS.iterdir()
            if path.is_dir() and path.name != "assets"
        }
        self.assertEqual(configured, on_disk)
        self.assertEqual(configured, {"en", "zh-CN"})

    def test_every_nav_page_has_an_llms_note(self) -> None:
        """Every sidebar entry has a one-line reason to open it.

        Hand-written pages carry theirs in ``PAGE_NOTES``; the tutorial's
        command pages get theirs from ``tools/tutorial_meta.json``, which
        is where the command reference already reads them.  Asking
        ``note_for`` rather than the dict is what lets the second kind
        exist at all -- a dict lookup would demand 30 hand-copied
        sentences that the registry already has.
        """
        for title, target in _nav():
            if _is_url(target):
                continue
            with self.subTest(page=title):
                self.assertIsNotNone(
                    gen_docs_site.note_for(target),
                    f"no description for {target}",
                )

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

    def test_every_page_lives_under_a_language_directory(self) -> None:
        """The plugin pairs translations by path, so the path has a shape.

        ``docs/en/api.md`` and ``docs/zh-CN/api.md`` are the same page;
        a file at ``docs/api.md`` would belong to no locale and be
        published once, unlinked.  Assets are the exception -- they are
        not translated, so they stay at the root and every page climbs
        out of its directory to reach them.
        """
        loose = sorted(
            path.name for path in DOCS.glob("*.md")
        )
        self.assertEqual(loose, [], "pages must live under en/ or zh-CN/")
        for path in sorted(DOCS.glob("*/**/*.md")):
            with self.subTest(page=path.relative_to(DOCS).as_posix()):
                self.assertIn(
                    path.relative_to(DOCS).parts[0], ("en", "zh-CN"),
                )

    def test_no_page_grew_a_language_suffix(self) -> None:
        """The directory names the language; the filename does not.

        ``docs_structure: folder`` is the strategy in use, and mixing in
        the ``suffix`` convention (``index.en.md``) would leave files the
        plugin reads as ordinary pages called "index.en".
        """
        self.assertEqual(list(DOCS.rglob("*.en.md")), [])
        self.assertEqual(list(DOCS.rglob("*.zh-CN.md")), [])
        self.assertTrue((DOCS / "en" / "index.md").is_file())
        self.assertTrue((DOCS / "en" / "api.md").is_file())

    def test_each_language_navigates_its_own_pages(self) -> None:
        """The sidebar follows the language, not the file on disk.

        A single shared nav cannot do this: the entries point at source
        paths, so listing ``en/api.md`` under a Chinese build would send
        the reader into the English tree while the page around it is
        Chinese.  Each locale therefore overrides ``nav`` with paths of
        its own.  English keeps the top-level ``nav`` because it is the
        default, and the plugin builds it on the site root.
        """
        text = _mkdocs()
        english = [target for _, target in _nav()]
        self.assertTrue(english, "the default nav is empty")
        self.assertTrue(all(t.startswith("en/") or _is_url(t)
                            for t in english), english)

        # The Chinese nav does not carry the prefix: its targets are
        # resolved inside the locale's own copy of the docs tree, which
        # is how the plugin pairs the two directories.  A prefixed target
        # here would send the sidebar to the English pages.  The tutorial
        # command pages are the exception -- they are not translated, so
        # the entry names the English file and the plugin republishes it
        # at ``/zh-CN/tutorial/``.
        chinese = [target for _, target in _locale_nav(text, "zh-CN")]
        self.assertTrue(chinese, "zh-CN has no nav of its own")
        self.assertTrue(
            all(
                not target.startswith(("en/", "zh-CN/"))
                or _is_url(target)
                or target.startswith(("en/tutorial/", "zh-CN/tutorial/"))
                for target in chinese
            ),
            chinese,
        )
        self.assertEqual(len(chinese), len(english))

    def test_the_two_navs_list_the_same_pages(self) -> None:
        """A page added to one language's sidebar is added to both.

        ``fallback_to_default`` publishes an English page under the
        Chinese prefix when it has no translation, so the Chinese nav can
        always offer every page the English one does.  Forgetting to add
        the entry is silent otherwise: the page is built and reachable by
        URL, just not from the sidebar.

        The tutorial command pages are the one set that keep the ``en/``
        prefix in the Chinese nav.  They are generated from the registry
        and not translated, so pointing the Chinese sidebar at
        ``zh-CN/tutorial/kl-x.md`` would name a file that does not exist;
        the plugin serves the English source under ``/zh-CN/`` and that
        fallback is what the entry has to match.
        """
        text = _mkdocs()
        english = {
            self._without_prefix(target)
            for _, target in _nav()
            if not _is_url(target)
        }
        chinese = {
            self._without_prefix(target)
            for _, target in _locale_nav(text, "zh-CN")
            if not _is_url(target)
        }
        self.assertEqual(english, chinese)

    @staticmethod
    def _without_prefix(target: str) -> str:
        """The page path with its language directory removed."""
        for prefix in ("en/", "zh-CN/"):
            if target.startswith(prefix):
                return target[len(prefix):]
        return target

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
        chinese = _page("zh-CN/api.md", locale="zh-CN")
        english = _page("api.md", locale="en")
        rendered = '<html lang="en" class="no-js">'

        self.assertEqual(
            language.on_post_page(rendered, page=chinese, config=config),
            '<html lang="zh-CN" class="no-js">',
        )
        self.assertEqual(
            language.on_post_page(rendered, page=english, config=config),
            rendered,
        )

    def test_an_untranslated_page_does_not_claim_to_be_chinese(self) -> None:
        """A fallback page is published under ``/zh-CN/`` and is English.

        ``fallback_to_default: true`` builds every untranslated page for
        both locales, so ``/zh-CN/tutorial/kl-walk/`` exists and is
        English prose.  Choosing the tag from the URL prefix made those
        30 pages announce ``lang="zh-CN"``, which hands English text to
        a Chinese screen-reader voice and a Chinese font stack.

        The giveaway is ``page.file.locale``: it names the language of
        the source file, so a fallback page keeps ``en`` even though its
        ``url`` was rewritten.  Both halves are asserted here, because a
        fix that keyed on the URL would pass the first assertion alone.
        """
        import language

        config = type("Config", (), {"docs_dir": str(DOCS)})()
        fallback = _page("en/tutorial/kl-walk.md", locale="en",
                         url="zh-CN/tutorial/kl-walk/")
        translated = _page("zh-CN/api.md", locale="zh-CN", url="zh-CN/api/")
        rendered = '<html lang="zh" class="no-js">'

        self.assertEqual(
            language.on_post_page(rendered, page=fallback, config=config),
            '<html lang="en" class="no-js">',
        )
        self.assertEqual(
            language.on_post_page(rendered, page=translated, config=config),
            '<html lang="zh-CN" class="no-js">',
        )

    def test_the_chinese_front_page_gets_a_document_title(self) -> None:
        """Off-nav pages are named after their file, which is not a title.

        ``docs/zh-CN/index.md`` is neither the homepage nor a nav entry,
        so ``<title>`` came out as ``Index - KernLens``.  Fixing it in
        front matter would not work: the theme appends ``- site_name`` to
        any ``meta.title``, and ``KernLens - KernLens`` is worse than the
        filename.  So the hook writes the tag.
        """
        import language

        config = type("Config", (), {"docs_dir": str(DOCS)})()
        source = "zh-CN/index.md"
        page = _page(source, locale="zh-CN", url="zh-CN/")
        rendered = '<html lang="en"><head><title>Index - KernLens</title>'
        out = language.on_post_page(rendered, page=page, config=config)
        self.assertIn(f"<title>{language.TITLES[source]}</title>", out)
        self.assertNotIn("Index - KernLens", out)

    def test_a_title_is_only_written_for_the_pages_that_need_one(self) -> None:
        # The rest of the Chinese tree keeps whatever the theme worked
        # out; a blanket title would flatten the API page's real heading.
        import language

        for source in ("zh-CN/api.md", "zh-CN/index.md"):
            with self.subTest(source=source):
                self.assertEqual(
                    source in language.TITLES,
                    source == "zh-CN/index.md",
                )

    def test_the_language_hook_is_configured(self) -> None:
        self.assertIn("hooks/language.py", _mkdocs())
        self.assertTrue((ROOT / "hooks" / "language.py").is_file())


class SearchIndexTests(unittest.TestCase):
    """The search box has to be usable in Chinese, not just in English.

    There is one ``search_index.json`` for the whole site, so one
    tokenizer has to serve both languages.  The default separator is
    ``[\\s\\-]+``, which is fine for English and wrong for Chinese: with
    no spaces to split on, a whole paragraph becomes a single token, and
    a query only matches where it happens to begin one.  Measured on the
    docs before the fix: ``分页`` and ``结构体`` matched nothing at all.

    The theme already solves this, but only if ``jieba`` can be imported
    -- it then segments every Han run and joins the words with U+200B.
    Two things therefore have to stay true, and neither is visible in the
    rendered page: the dependency, and a separator that treats U+200B as a
    boundary.
    """

    def test_the_separator_splits_on_the_boundary_jieba_inserts(self) -> None:
        """U+200B has to be in the separator, or segmentation is inert.

        ``_segment_chinese`` joins the words it finds with ``\\u200b``.
        Every other character class in the theme's Chinese separator
        (``\\u3000``, ``、``, ``，``) is about full-width punctuation, which
        a Markdown page rarely contains; the ZWSP is the one that carries
        the segmentation.  Dropping it leaves the dependency installed and
        the index unchanged.
        """
        text = _mkdocs()
        separator = next(
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.strip().startswith("separator:")
        )
        self.assertIn("\\u200b", separator)

    def test_the_docs_group_installs_the_tokenizer(self) -> None:
        """The build is the only consumer, so the docs group is where it goes.

        Putting it in the runtime dependencies would ship 37 MB of
        dictionary to everyone who installs KernLens, for a feature that
        only the site build uses.
        """
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        group = re.search(r"^docs = \[(.*?)^\]", pyproject, re.S | re.M)
        self.assertIsNotNone(group, "no `docs` dependency group")
        self.assertIn("jieba", group.group(1))


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
                # The default locale is built on the site root, so the
                # unprefixed URL is the English front page -- which lives
                # at ``docs/en/index.md``, its own language directory.
                locale = relative or gen_docs_site.DEFAULT_LOCALE
                page = DOCS / locale / "index.md"
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
