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

Configured in ``mkdocs.yml``::

    hooks:
      - hooks/language.py
"""

from __future__ import annotations

import re

#: ``<html lang="en" class="no-js">``, the first line the theme writes.
_HTML_TAG = re.compile(r'<html lang="[^"]*"')

#: Directory under ``docs/`` whose pages are Chinese, and the tag they
#: need.  A path prefix rather than a filename test: the rule is "this
#: directory is a language", which is what makes adding a page to it safe.
CHINESE_DIR = "zh-CN/"
CHINESE_LANG = "zh-CN"


def on_post_page(output: str, *, page, config) -> str:
    """Rewrite the ``lang`` attribute of a page under ``docs/zh-CN/``."""
    source = getattr(page.file, "src_uri", "") or ""
    if not source.startswith(CHINESE_DIR):
        return output
    return _HTML_TAG.sub(f'<html lang="{CHINESE_LANG}"', output, count=1)