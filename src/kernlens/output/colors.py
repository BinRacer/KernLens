#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Semantic colour roles.

:class:`~kernlens.output.palette.Palette` lists raw ANSI sequences; this
module maps *meaning* onto them so every command paints the same concept
the same way (a field label is always :data:`LABEL`, a tri-state flag is
always :data:`TRUE` / :data:`FALSE` / :data:`MISSING`, and so on).

Keeping the choices here means a restyle touches one file instead of
every command module.
"""

from __future__ import annotations

from typing import Final

from .palette import Palette

#: Field labels and structural prefixes (``head      : ``).
LABEL: Final[str] = str(Palette.CYAN)

#: Addresses and physical/virtual pointers.
ADDR: Final[str] = str(Palette.DIM)

#: Fixed-width hex values.
HEX: Final[str] = str(Palette.DIM)

#: Decimal counts and indices.
DEC: Final[str] = str(Palette.BRIGHT_CYAN)

#: Human-readable byte sizes.
SIZE: Final[str] = str(Palette.DIM)

#: A successfully resolved name (symbol, cache, subcommand keyword).
NAME: Final[str] = str(Palette.BRIGHT_YELLOW)

#: A value emphasised inside a line (leaf kind, migrated page, option).
ACCENT: Final[str] = str(Palette.BRIGHT_YELLOW_BOLD)

#: Tri-state ``True`` / a good audit result / an enabled feature.
TRUE: Final[str] = str(Palette.GREEN)

#: Tri-state ``False`` / a bad audit result / an error marker.
FALSE: Final[str] = str(Palette.RED)

#: A missing or unreadable value (``?``).
MISSING: Final[str] = str(Palette.YELLOW)

#: A hard error (``<unreadable>``).
ERROR: Final[str] = str(Palette.RED)

#: Highlights that stand out from the surrounding text.
HIGHLIGHT: Final[str] = str(Palette.BRIGHT_YELLOW)

#: Titles and group headings.
TITLE: Final[str] = str(Palette.CYAN)

#: Structures, borders, and dimmed metadata.
BORDER: Final[str] = str(Palette.DIM)

#: Bold emphasis (banners, the resolved command name).
BOLD: Final[str] = str(Palette.BOLD)


__all__ = [
    "ACCENT",
    "ADDR",
    "BOLD",
    "BORDER",
    "DEC",
    "ERROR",
    "FALSE",
    "HEX",
    "HIGHLIGHT",
    "LABEL",
    "MISSING",
    "NAME",
    "SIZE",
    "TITLE",
    "TRUE",
]