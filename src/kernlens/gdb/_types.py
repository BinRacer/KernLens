#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Private protocols used to keep Pyright happy around GDB types."""

from __future__ import annotations

from typing import Protocol


class _IntConvertible(Protocol):
    """Protocol for values that ``int()`` can convert."""

    def __int__(self) -> int: ...


class _StrLike(Protocol):
    """Protocol for string-like returns from ``gdb.execute``.

    ``gdb.execute(..., to_string=True)`` is annotated as returning this
    (opaque) type rather than ``str`` in the bundled ``gdb`` stub, so every
    operation the code performs on the result has to be declared here.  A
    missing member is not cosmetic: ``'"' in text`` was accepted by the
    runtime and rejected by the checker, which is why the call sites used
    to carry ``# pyright: ignore`` comments.
    """

    def strip(self) -> str: ...

    def split(
        self, sep: str | None = None, maxsplit: int = -1
    ) -> list[str]: ...

    def __contains__(self, item: str) -> bool: ...


__all__ = ["_IntConvertible", "_StrLike"]
