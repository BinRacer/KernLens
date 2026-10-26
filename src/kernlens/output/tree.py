#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Indented, tree-structured command output (pwndbg's ``IndentContextManager``).

Commands print nested blocks by entering the context manager::

    indent = IndentContextManager()
    indent.print(indent.prefix("Slab Cache") + " @ " + indent.addr_hex(addr))
    with indent:
        indent.print(indent.prefix("Name") + ": " + name)

The tree mirrors pwndbg's: addresses are yellow, auxiliary hex values are
red, and structural prefixes alternate blue / green by depth.  With colour
disabled every helper returns the plain text.
"""

from __future__ import annotations

from types import TracebackType

from . import message

#: ANSI SGR codes for the tree palette.
_BLUE = "\x1b[34m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"


class IndentContextManager:
    """Track the current indent depth and paint tree output.

    ``with indent:`` increments the depth; leaving it decrements.  Depth is
    painted in units of ``indent_str`` (four spaces by default, configurable
    through :class:`~kernlens.gdb.config.DebugConfig`).
    """

    __slots__: tuple[str, ...] = ("_depth", "_unit")

    def __init__(self, unit: str = "    ") -> None:
        self._depth: int = 0
        self._unit: str = unit

    @property
    def depth(self) -> int:
        """The current nesting depth."""
        return self._depth

    @property
    def unit(self) -> str:
        """The per-level indent string."""
        return self._unit

    def set_unit(self, unit: str) -> None:
        """Change the per-level indent string."""
        self._unit = unit

    def __enter__(self) -> "IndentContextManager":
        self._depth += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._depth -= 1
        if self._depth < 0:  # pragma: no cover - defensive
            self._depth = 0

    def print(self, *args: object, **kwargs: object) -> None:
        """Print one line, prefixed by the current indent.

        The indent is glued to the first argument (no ``sep`` space), so
        ``indent.print("Name:", value)`` reads ``    Name: value`` rather
        than ``     Name: value``.
        """
        prefix = self._unit * self._depth
        if args:
            print(f"{prefix}{args[0]}", *args[1:], **kwargs)
        else:
            print(prefix, **kwargs)

    def addr_hex(self, value: int) -> str:
        """Paint an address (yellow, pwndbg's ``addr_hex``)."""
        return message.colorize(hex(value), _YELLOW)

    def aux_hex(self, value: int) -> str:
        """Paint an auxiliary hex value (red, pwndbg's ``aux_hex``)."""
        return message.colorize(hex(value), _RED)

    def prefix(self, text: str) -> str:
        """Paint a structural prefix, alternating by depth."""
        color = _BLUE if self._depth % 2 == 0 else _GREEN
        return message.colorize(text, color)


__all__ = ["IndentContextManager"]