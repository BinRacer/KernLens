#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Runtime knobs shared by the GDB adapter components."""

from __future__ import annotations

from typing import final


@final
class DebugConfig:
    """Runtime knobs shared by every component.

    ``kaslr_offset`` is the only field mutated at runtime; the rest are
    set once in ``__init__`` and treated as constants.

    Color control lives on :class:`Logger` / :class:`Styler`
    (``set_color_enabled`` on each); this class does not carry a
    ``color_enabled`` field.
    """

    def __init__(self) -> None:
        self.kaslr_offset: int = 0
        self.header_width: int = 13
        self.indent: str = " " * self.header_width
        self.indent_nested: str = self.indent + "      "
        self.freelist_scan_limit: int = 4096
        #: Optional path to a BTF blob (raw blob or an ELF with a
        #: ``.BTF`` section) used *after* DWARF when a struct is absent
        #: from the debug info.  ``None`` (the default) reads the
        #: ``.BTF`` section of the loaded image; a remote target with no
        #: usable section can point this at its own blob.
        self.btf_path: str | None = None


__all__ = ["DebugConfig"]
