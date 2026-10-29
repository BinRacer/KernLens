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

#: The tag a page gets when its source is the default language.  A
#: constant rather than the theme's value, because the same
#: ``on_post_page`` handles pages from both languages.
CHINESE_LANG = "zh-CN"
DEFAULT_LANG = "en"

#: Document titles for pages the theme would name after the file.  Keyed
#: by source path so a rename fails visibly (the page reverts to
#: ``Index - KernLens``) rather than silently keeping a stale title.
TITLES: dict[str, str] = {
    "zh-CN/index.md": "KernLens -- \u7b80\u4f53\u4e2d\u6587",
}


def on_post_page(output: str, *, page, config) -> str:
    """Rewrite the ``lang`` attribute, and the title where it is needed.

    The attribute declares the language of the *text*, which is not
    always the language of the URL.  ``fallback_to_default`` publishes
    every untranslated page under ``/zh-CN/`` as well, built from the
    English source, so a page can live at ``/zh-CN/tutorial/kl-walk/``
    and be entirely English.  Announcing that as Chinese is worse than
    saying nothing: a screen reader picks a Chinese voice, the browser
    picks a Chinese font stack, and the search index applies Chinese
    rules to English prose.

    ``page.file.locale`` is the source file's own locale, and it is what
    tells the two apart -- the URL does not.  A translated page has
    ``locale == "zh-CN"``; a fallback page keeps ``"en"`` while its URL
    is rewritten.  So the tag follows the file, not the directory.
    """
    source = getattr(page.file, "src_uri", "") or ""
    if source in TITLES:
        output = _TITLE.sub(f"<title>{TITLES[source]}</title>", output, count=1)
    locale = getattr(page.file, "locale", None) or ""
    language = CHINESE_LANG if locale == CHINESE_LANG else DEFAULT_LANG
    return _HTML_TAG.sub(f'<html lang="{language}"', output, count=1)