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
    """Protocol for string-like returns from ``gdb.execute``."""

    def strip(self) -> str: ...


__all__ = ["_IntConvertible", "_StrLike"]
