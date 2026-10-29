#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""mkdocs hook: declare the language each page is actually written in.

``mkdocs-material`` emits ``<html lang="{{ lang.t('language') }}">``, and
``theme.language`` in ``mkdocs.yml`` is one value for the whole site.
With two languages in one site that is wrong for one of them: the
Chinese pages were served as ``lang="en"``.

That is not cosmetic.  ``lang`` drives hyphenation, the font fallback the
browser picks, and -- because mkdocs-material feeds it to search -- the
stemmer that indexes the page.  An English stemmer over Chinese text
indexes almost nothing, so the Chinese pages were effectively unsearchable
while looking fine.

The tag is the first line of ``base.html`` and is not inside a
``{% block %}``, so it cannot be overridden without copying the whole
template.  A hook runs after rendering instead, which leaves the theme
untouched.

The same hook fixes the one page whose document title the theme cannot
work out.  ``docs/zh-CN/index.md`` is neither the homepage nor a nav
entry, so mkdocs names it after its file and the browser tab reads
``Index - KernLens``.

Configured in ``mkdocs.yml``::

    hooks:
      - hooks/language.py
"""

from __future__ import annotations

import re

#: ``<html lang="en" class="no-js">``, the first line the theme writes.
_HTML_TAG = re.compile(r'<html lang="[^"]*"')

#: ``<title>...</title>``, the only one in the document.
_TITLE = re.compile(r"<title>.*?</title>", re.DOTALL)

#: Directory under ``docs/`` whose pages are Chinese, and the tag they
#: need.  A path prefix rather than a filename test: the rule is "this
#: directory is a language", which is what makes adding a page to it safe.
CHINESE_DIR = "zh-CN/"
CHINESE_LANG = "zh-CN"

#: Document titles for pages the theme would name after the file.  Keyed
#: by source path so a rename fails visibly (the page reverts to
#: ``Index - KernLens``) rather than silently keeping a stale title.
TITLES: dict[str, str] = {
    "zh-CN/index.md": "KernLens -- \u7b80\u4f53\u4e2d\u6587",
}


def on_post_page(output: str, *, page, config) -> str:
    """Rewrite the ``lang`` attribute, and the title where it is needed."""
    source = getattr(page.file, "src_uri", "") or ""
    if not source.startswith(CHINESE_DIR):
        return output
    output = _HTML_TAG.sub(f'<html lang="{CHINESE_LANG}"', output, count=1)
    if source in TITLES:
        output = _TITLE.sub(f"<title>{TITLES[source]}</title>", output, count=1)
    return output