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
import re
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/BinRacer/KernLens"
SITE = "https://binracer.github.io/KernLens"
RAW = "https://raw.githubusercontent.com/BinRacer/KernLens/main"

#: Prefixed to every generated page, so an edit in the wrong file is
#: obvious in a diff and in the rendered page source.
BANNER = (
    "<!-- Generated from {source} by tools/gen_docs_site.py. "
    "Edit the source, not this file. -->"
)

#: Where each generated page goes, relative to ``docs/``.  The English
#: pages sit at the root because English is the default language and
#: ``/`` should be it; the Chinese ones live one directory down.  The
#: directory is what :func:`rewrite_target` uses to work out how far a
#: relative link has to climb.
OUTPUT: dict[str, str] = {
    "README.md": "index.md",
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
    "index.md": (
        "what KernLens is, the demo, the install, and the command summary"
    ),
    "zh-CN/index.md": "the same front page in Chinese",
    "commands.md": "every command and alias, generated from the registry",
    "tutorial/README.md": (
        "one page per command, with output captured from a real kernel"
    ),
    "demo-container.md": (
        "a kernel built from source, booted under QEMU, and attached in GDB"
    ),
    "api.md": "the Python API: classes, facade functions, and examples",
    "zh-CN/api.md": "the same API reference in Chinese",
    "architecture.md": (
        "package layout, the loading path, and why the boundaries are there"
    ),
    "compatibility.md": (
        "which environments were measured, which are expected, and which "
        "are not claimed"
    ),
    "releasing.md": (
        "what has to agree before a tag, and what the tag does"
    ),
    "naming.md": "command, example, and filename conventions",
}

#: Pages that are published but not linked from the nav, with the title
#: ``llms.txt`` lists them under.
#:
#: The Chinese pages are here because choosing a language is the header
#: switcher's job, and repeating it as a nav section made it look like a
#: chapter of the documentation.  They still have to appear in
#: ``llms.txt``: that file is an index of what is *published*, not a
#: mirror of the sidebar, and an assistant reading it would otherwise
#: believe the Chinese pages do not exist.
OFF_NAV: tuple[tuple[str, str], ...] = (
    ("首页", "zh-CN/index.md"),
    ("Python API", "zh-CN/api.md"),
)

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


def _climb(dest: str) -> str:
    """The ``..`` prefix a page at *dest* needs to reach the site root.

    ``docs/`` is the site root, so a page at ``zh-CN/index.md`` is one
    directory down and has to climb once to name ``assets/demo.svg`` the
    way an English page does.  Getting this wrong is not a warning:
    mkdocs leaves a raw-HTML ``src`` as written, so the browser asks for
    ``/zh-CN/assets/demo.svg`` and gets a 404 while the English page
    renders, because its guess and the truth happen to coincide.
    """
    depth = dest.count("/")
    return "../" * depth


def rewrite_target(target: str, dest: str = "index.md") -> str:
    """Rewrite one Markdown link target for the site.

    Absolute URLs, anchors, and ``mailto:`` are returned unchanged.
    ``docs/...`` becomes a site path relative to *dest*; everything else
    is outside the site and becomes a GitHub URL.
    """
    if _is_external(target):
        return target
    back = _climb(dest)
    path, _, fragment = target.partition("#")
    if path.startswith("docs/"):
        path = path[len("docs/"):]
        if path.endswith("/"):
            # ``docs/tutorial/`` is the generated index page; mkdocs
            # treats a directory link as unrecognized and leaves it as
            # written, which 404s from every page but the root.
            path += "README.md"
        path = back + path
    elif path:
        path = _github(path)
    return f"{path}#{fragment}" if fragment else path


def rewrite_attribute(name: str, target: str, dest: str = "index.md") -> str:
    """Rewrite one raw-HTML ``href``/``src`` for the site."""
    if _is_external(target):
        return target
    back = _climb(dest)
    path = target.removeprefix("./")
    if path in SITE_LINKS:
        return SITE_LINKS[path]
    if path.startswith("docs/"):
        return back + path[len("docs/"):]
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
    """The ``(title, target)`` pairs of the nav, in order."""
    entries: list[tuple[str, str]] = []
    inside = False
    for line in mkdocs.splitlines():
        if line.strip() == "nav:":
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
    """The published URL of a local nav target.

    ``index.md`` is the site root and ``zh-CN/index.md`` is the Chinese
    root; both have to lose their filename, or mkdocs would publish them
    at ``/zh-CN/index/`` and the switcher would point at a redirect.
    """
    path = target[:-len(".md")]
    if path == "index":
        return SITE + "/"
    if path.endswith("/index"):
        path = path[:-len("index")].rstrip("/")
    if path.endswith("/README"):
        path = path[:-len("README")].rstrip("/")
    return f"{SITE}/{path}/"


def render_llms(nav: Sequence[tuple[str, str]]) -> str:
    """Render ``llms.txt`` from the nav, :data:`OFF_NAV`, and the notes.

    ``OFF_NAV`` comes after the nav and under its own heading, so the
    file says both things a reader needs: which pages the site links to,
    and which pages exist anyway.  Folding them into one list would lose
    the distinction that made them worth separating.
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
    if OFF_NAV:
        lines += [
            "",
            "## Not in the sidebar",
            "",
            "Reached from the language switcher in the site header, which",
            "applies to every page; listing them in the nav as well would",
            "present a language choice as a chapter of the documentation.",
            "",
        ]
        for title, target in OFF_NAV:
            if target not in PAGE_NOTES:
                raise SystemExit(
                    f"off-nav page {target!r} has no description; add one "
                    "to PAGE_NOTES in tools/gen_docs_site.py"
                )
            lines.append(
                f"- [{title}]({page_url(target)}): {PAGE_NOTES[target]}"
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
