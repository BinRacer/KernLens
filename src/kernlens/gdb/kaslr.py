#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""KASLR slide handling and breakpoint-spec construction."""

from __future__ import annotations

from typing import cast, final

import gdb  # type: ignore[import-not-found]

from ._types import _IntConvertible
from .config import DebugConfig
from .reader import MemoryReader


@final
class Kaslr:
    """Breakpoint spec construction and link-time ``_text`` lookup."""

    __slots__: tuple[str, ...] = ("_config", "_reader")

    def __init__(self, config: DebugConfig, reader: MemoryReader) -> None:
        self._config: DebugConfig = config
        self._reader: MemoryReader = reader

    def bp_spec(self, symbol: str) -> str:
        """Breakpoint spec: bare symbol name or ``*<runtime_addr>``."""
        if self._config.kaslr_offset == 0:
            return symbol
        try:
            value = gdb.parse_and_eval(f"(unsigned long)&{symbol}")
            link = int(cast(_IntConvertible, value))
        except (gdb.error, TypeError, ValueError):
            return symbol
        if link == 0:
            return symbol
        runtime = (link + self._config.kaslr_offset) & 0xFFFFFFFFFFFFFFFF
        return f"*{runtime:#x}"

    def link_text(self) -> int | None:
        """Read the link-time ``_text`` address.

        Callers add ``kdbg.kaslr_offset`` themselves, so this stays the
        address GDB's symbol table reports (``&_text``) and is the same
        for every boot.
        """
        return self._reader.u64("(unsigned long)&_text")


__all__ = ["Kaslr"]
