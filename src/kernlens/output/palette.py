#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""ANSI SGR palette used by the logger and styler."""

from enum import Enum
from typing import final

from ._typing import override


@final
class Palette(str, Enum):
    """ANSI SGR escape sequences as a ``str``-valued enum."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"

    BRIGHT_RED_BOLD = "\033[91m\033[1m"
    BRIGHT_YELLOW_BOLD = "\033[93m\033[1m"

    @override
    def __str__(self) -> str:
        """Return the SGR sequence."""
        return self.value

    @override
    def __format__(self, spec: str) -> str:
        """Format the SGR sequence (keeps f-strings portable)."""
        return format(self.value, spec)


# =========================================================================

__all__ = ["Palette"]
