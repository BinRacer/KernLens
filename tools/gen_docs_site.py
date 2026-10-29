#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Generate the documentation-site pages that are not written by hand.

Three files are derived, and committed so a reader without mkdocs can
read them:

``docs/index.md``
    ``README.md`` with its links rewritten for the site.  The README is
    the front page; a second hand-written copy would be a third place to
    keep true.
``docs/zh-CN/index.md``
    the same for ``README.zh-CN.md``, under its own directory.  English
    is the default and owns the site root, so the Chinese pages live one
    level down and every path on them is one ``..`` deeper -- including
    the images, which is why the depth is computed rather than assumed.
``docs/llms.txt``
    a short plain-text index of the published pages, for assistants that
    read one file instead of crawling.  It is built from the nav in
    ``mkdocs.yml``, so a page cannot be published and stay unlisted.

The rewrite is the only interesting part.  A checkout path means one
thing on GitHub and another under mkdocs: ``docs/api.md`` is ``api.md``
from ``docs/index.md``, while ``CONTRIBUTING.md`` is outside the site
directory and has to become a GitHub URL.  A link from a page inside
``docs/zh-CN/`` needs one more ``..`` for the same reason: the site root
is ``docs/``, so a Chinese page is two levels from ``docs/assets/`` and
an English one is not.  Doing that by hand in a copy would rot at the
first rename, so it is done here and checked by ``--check``.

Usage::

    python tools/gen_docs_site.py
    python tools/gen_docs_site.py --check
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/BinRacer/KernLens"
SITE = "https://binracer.github.io/KernLens"
RAW = "https://raw.githubusercontent.com/BinRacer/KernLens/main"

#: The docs tree and the two locales.  Every page lives in a language
#: directory; `mkdocs-static-i18n` builds the default one on the site root
#: and every other one under ``/<locale>/``.
DOCS = ROOT / "docs"
DEFAULT_LOCALE = "en"
OTHER_LOCALE = "zh-CN"

#: Prefixed to every generated page, so an edit in the wrong file is
#: obvious in a diff and in the rendered page source.
BANNER = (
    "<!-- Generated from {source} by tools/gen_docs_site.py. "
    "Edit the source, not this file. -->"
)

#: Where each generated page goes, relative to ``docs/``.  Both languages
#: live in their own directory because `mkdocs-static-i18n` pairs files by
#: path: ``en/index.md`` and ``zh-CN/index.md`` are the same page in two
#: languages.  The default language is still built on the site root, so
#: ``en/`` disappears from the published URL -- ``docs/en/index.md`` is
#: ``/``, not ``/en/``.  The directory is what :func:`rewrite_target` uses
#: to work out how far a relative link has to climb.
OUTPUT: dict[str, str] = {
    "README.md": "en/index.md",
    "README.zh-CN.md": "zh-CN/index.md",
}

#: The language switcher is raw HTML, which mkdocs does not rewrite, so
#: these two hrefs have to be final URLs.  Absolute ones are the only
#: spelling that works from a page at either depth.
SITE_LINKS = {
    "README.md": SITE + "/",
    "README.zh-CN.md": SITE + "/zh-CN/",
}

#: One line per published page, keyed by the nav target.  A nav entry
#: without a note fails the generator: ``llms.txt`` is a list of pages
#: with a reason to open them, not a list of filenames.
PAGE_NOTES: dict[str, str] = {
    "en/index.md": (
        "what KernLens is, the demo, the install, and the command summary"
    ),
    "zh-CN/index.md": "the same front page in Chinese",
    "en/commands.md": "every command and alias, generated from the registry",
    "en/tutorial/README.md": (
        "one page per command, with output captured from a real kernel"
    ),
    "en/demo-container.md": (
        "a kernel built from source, booted under QEMU, and attached in GDB"
    ),
    "en/api.md": "the Python API: classes, facade functions, and examples",
    "zh-CN/api.md": "the same API reference in Chinese",
    "en/architecture.md": (
        "package layout, the loading path, and why the boundaries are there"
    ),
    "en/compatibility.md": (
        "which environments were measured, which are expected, and which "
        "are not claimed"
    ),
    "en/releasing.md": (
        "what has to agree before a tag, and what the tag does"
    ),
    "en/naming.md": "command, example, and filename conventions",
}

_MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")
_HTML_LINK = re.compile(r'(?P<name>href|src)="(?P<target>[^"]+)"')
_NAV = re.compile(r"^\s*-\s+(?P<title>[^:]+):\s+(?P<target>\S+)\s*$")

#: The README's own language switcher, which the site does not need.
#:
#: It is there for GitHub, where the two files are all a reader can
#: navigate between.  On the site the header carries a switcher on every
#: page, so keeping this one puts two identical controls on the front
#: page -- one of them pointing at the page it is already on.
_README_SWITCHER = re.compile(
    r"<p>\s*<a href=\"\./README(?:\.zh-CN)?\.md\">[^<]*</a>"
    r"(?:\s*\|\s*<a href=\"\./README(?:\.zh-CN)?\.md\">[^<]*</a>)+\s*</p>",
    re.MULTILINE,
)

#: Front matter prepended to a generated page the site should not add a
#: title heading to.  Both front pages open with the banner image, so a
#: nav-title heading above it reads as a caption for the wrong thing.
#: ``title`` is the key that hides the heading; ``navigation`` hides the
#: sidebar, which these pages still want.
HIDE_NAV_TITLE = "---\nhide:\n  - title\n---\n"


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "#", "mailto:"))


def _github(target: str) -> str:
    """Turn a checkout-relative path into a GitHub URL."""
    kind = "tree" if target.endswith("/") else "blob"
    return f"{REPO}/{kind}/main/{target}"


def _locale(dest: str) -> str:
    """The language a page at *dest* belongs to."""
    head = PurePosixPath(dest).parts[0]
    return head if head == OTHER_LOCALE else DEFAULT_LOCALE


def _published_depth(dest: str) -> int:
    """How many directories deep a page at *dest* is published.

    The source depth is the wrong measure.  ``en/index.md`` and
    ``zh-CN/index.md`` are both one directory down on disk, but only the
    second is one directory down in the URL: the default language is
    built on the site root, so ``en/index.md`` is ``/`` and needs no
    ``..`` at all.  Counting source separators made the English front
    page emit ``../assets/demo.svg``, which from ``/`` leaves the site
    and 404s -- a raw-HTML ``src`` is never rewritten by mkdocs, so the
    wrong guess reaches the browser.
    """
    path = PurePosixPath(dest)
    parts = path.parts[:-1]
    if parts and parts[0] == DEFAULT_LOCALE:
        parts = parts[1:]
    depth = len(parts)
    # ``use_directory_urls`` is on (mkdocs' default), so ``index.md`` and
    # ``README.md`` are served at their directory and everything else at a
    # directory named after the file.  That extra level is one more ``..``
    # to climb.
    if path.stem not in {"index", "README"}:
        depth += 1
    return depth


def _climb(dest: str) -> str:
    """The ``..`` prefix a page at *dest* needs to reach the site root."""
    return "../" * _published_depth(dest)


def _source_target(path: str, dest: str) -> str:
    """The source-relative path from a page at *dest* to ``docs/<path>``.

    Markdown links are resolved by mkdocs against the *source* tree, so
    this one is source-relative while the raw-HTML rewrite above is
    URL-relative.  The two cases diverge again on language: pages are
    duplicated per locale, assets are not.  ``commands.md`` therefore
    resolves beside the page, while ``assets/demo.svg`` exists once and
    the page has to climb out of its language directory to name it.

    The fallback order is the one the i18n plugin uses when it resolves a
    link itself -- the page's own language, then the default language,
    then the root -- because that is the set of files that will exist in
    the built site.  A translated page therefore links to
    ``../en/architecture.md`` for a page nobody has translated yet, and
    the reader lands on the English text rather than a 404.
    """
    here = PurePosixPath(dest).parent
    # A ``docs/``-prefixed target names a checkout path, and every
    # hand-written one points into the default language.  The locale is
    # chosen by the page, not by the link: ``docs/en/api.md`` on the
    # Chinese front page means "the Chinese API page if it exists".
    path = posixpath.normpath(path)
    if path.startswith(DEFAULT_LOCALE + "/"):
        path = path[len(DEFAULT_LOCALE) + 1:]
    for candidate in (
        DOCS / here / path,
        DOCS / DEFAULT_LOCALE / path,
        DOCS / path,
    ):
        if candidate.is_file():
            return posixpath.relpath(
                candidate.as_posix(), (DOCS / here).as_posix(),
            )
    return path


def rewrite_target(target: str, dest: str = "en/index.md") -> str:
    """Rewrite one Markdown link target for the site.

    Absolute URLs, anchors, and ``mailto:`` are returned unchanged.
    ``docs/...`` becomes a site path relative to *dest*; everything else
    is outside the site and becomes a GitHub URL.
    """
    if _is_external(target):
        return target
    path, _, fragment = target.partition("#")
    if path.startswith("docs/"):
        path = path[len("docs/"):]
        if path.endswith("/"):
            # ``docs/tutorial/`` is the generated index page; mkdocs
            # treats a directory link as unrecognized and leaves it as
            # written, which 404s from every page but the root.
            path += "README.md"
        path = _source_target(path, dest)
    elif path:
        path = _github(path)
    return f"{path}#{fragment}" if fragment else path


def rewrite_attribute(name: str, target: str, dest: str = "en/index.md") -> str:
    """Rewrite one raw-HTML ``href``/``src`` for the site."""
    if _is_external(target):
        return target
    path = target.removeprefix("./")
    if path in SITE_LINKS:
        return SITE_LINKS[path]
    if path.startswith("docs/"):
        return _climb(dest) + path[len("docs/"):]
    # ``images/banner.svg`` is beside ``src/``, not inside ``docs/``, so
    # the site cannot serve it.  Raw is the one GitHub URL that an ``img``
    # can load (``blob`` returns an HTML page).
    base = RAW if name == "src" else f"{REPO}/blob/main"
    return f"{base}/{path}"


def render_index(readme: str, source: str, dest: str) -> str:
    """Return *readme* with its links rewritten, behind the banner.

    The README's own language switcher is dropped: the site header has
    one on every page, and on the front page the README copy points at
    the page it is already on.
    """
    body = _README_SWITCHER.sub("", readme)
    body = _MARKDOWN_LINK.sub(
        lambda match: f"]({rewrite_target(match.group(1), dest)})", body,
    )
    body = _HTML_LINK.sub(
        lambda match: (
            f'{match.group("name")}="'
            f'{rewrite_attribute(match.group("name"), match.group("target"), dest)}"'
        ),
        body,
    )
    # The front matter has to be the first thing in the file: mkdocs
    # parses YAML front matter only at the very top, so a comment or a
    # blank line above it silently turns the whole block into prose that
    # renders as a stray horizontal rule.
    return HIDE_NAV_TITLE + "\n" + BANNER.format(source=source) + "\n\n" + body


def nav_entries(mkdocs: str) -> list[tuple[str, str]]:
    """The ``(title, target)`` pairs of the top-level nav, in order.

    Top-level means column zero.  Each locale can override ``nav`` under
    ``plugins.i18n.languages``, so a plain "first ``nav:`` wins" scan
    would read the Chinese nav -- it is nearer the top of the file -- and
    ``llms.txt`` would list Chinese titles pointing at English URLs.
    """
    entries: list[tuple[str, str]] = []
    inside = False
    for line in mkdocs.splitlines():
        if line == "nav:":
            inside = True
            continue
        if inside and line and not line[0].isspace():
            break
        if not inside:
            continue
        match = _NAV.match(line)
        if match is not None:
            entries.append(
                (match.group("title").strip(), match.group("target"))
            )
    return entries


def page_url(target: str) -> str:
    """The published URL of a nav target.

    The default language is built on the site root, so ``en/index.md`` is
    ``/`` and ``en/api.md`` is ``/api/`` -- the ``en/`` never appears in a
    URL.  Every other locale keeps its directory: ``zh-CN/api.md`` is
    ``/zh-CN/api/``.

    ``index.md`` and ``README.md`` both lose their filename, or mkdocs
    would publish them at ``/zh-CN/index/`` and every link would take a
    redirect.
    """
    path = target[:-len(".md")]
    if path.startswith(DEFAULT_LOCALE + "/"):
        path = path[len(DEFAULT_LOCALE) + 1:]
    for tail in ("/index", "/README", "index", "README"):
        if path == tail:
            path = ""
            break
        if path.endswith(tail):
            path = path[:-len(tail)].rstrip("/")
            break
    return f"{SITE}/{path}/" if path else SITE + "/"


def _translated(target: str) -> str | None:
    """The Chinese counterpart of a default-language nav target, if any.

    Deciding this from the files rather than from the ``zh-CN`` nav in
    ``mkdocs.yml`` keeps ``llms.txt`` honest for free: a page that gains a
    translation shows up, and one whose translation is deleted disappears.
    Parsing the second nav would also mean teaching this module to read
    the nested ``plugins:`` tree, for information it can observe directly.
    """
    if _is_external(target):
        return None
    candidate = DOCS / OTHER_LOCALE / target[len(DEFAULT_LOCALE) + 1:] \
        if target.startswith(DEFAULT_LOCALE + "/") else None
    if candidate is not None and candidate.is_file():
        return candidate.relative_to(DOCS).as_posix()
    return None


def render_llms(nav: Sequence[tuple[str, str]]) -> str:
    """Render ``llms.txt`` from the default-language nav and the files.

    One section per language: the default language is the canonical set,
    and the second section lists exactly the pages that have been
    translated.  That split is the useful fact for a reader -- which pages
    exist in Chinese is a property of the site, not of the sidebar.
    """
    lines = [
        "# KernLens",
        "",
        "> Linux kernel debugging from Python and GDB: 40 commands, a",
        "> pure-Python core, and a startup file sourced inside GDB.",
        "",
        f"- Site: {SITE}/",
        f"- Source: {REPO}",
        f"- Install: {REPO}/blob/main/install.sh",
        "",
        "## Pages",
        "",
    ]
    translated: list[tuple[str, str]] = []
    for title, target in nav:
        if _is_external(target):
            lines.append(f"- [{title}]({target})")
            continue
        if target not in PAGE_NOTES:
            raise SystemExit(
                f"nav entry {target!r} has no description; add one to "
                "PAGE_NOTES in tools/gen_docs_site.py"
            )
        lines.append(
            f"- [{title}]({page_url(target)}): {PAGE_NOTES[target]}"
        )
        other = _translated(target)
        if other is not None:
            translated.append((title, other))
    if translated:
        lines += [
            "",
            f"## {OTHER_LOCALE}",
            "",
            "The same pages in Chinese, at their own URLs.  Pages with no",
            "counterpart here are served in English under the Chinese",
            "prefix, so every link works and the language of what you land",
            "on is never a surprise.",
            "",
        ]
        for title, target in translated:
            lines.append(
                f"- [{title}]({page_url(target)}): "
                f"{PAGE_NOTES.get(target, '(translation)')}"
            )
    lines.append("")
    return "\n".join(lines)


def generate() -> dict[Path, str]:
    """Every generated file, mapped to its content."""
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    nav = nav_entries(mkdocs)
    if not nav:
        raise SystemExit("mkdocs.yml has no nav entries")
    pages = {
        ROOT / "docs" / dest: render_index(
            (ROOT / source).read_text(encoding="utf-8"), source, dest,
        )
        for source, dest in OUTPUT.items()
    }
    pages[ROOT / "docs" / "llms.txt"] = render_llms(nav)
    return pages


def main(argv: Sequence[str] | None = None) -> int:
    """Write the generated files, or check them with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="fail when a generated file is out of date",
    )
    args = parser.parse_args(argv)

    stale = 0
    for path, content in generate().items():
        name = path.relative_to(ROOT)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != content:
                stale += 1
                print(f"{name} is out of date", file=sys.stderr)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {name}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
