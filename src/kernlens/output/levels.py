#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Severity levels and their fixed-width tags."""

from enum import Enum
from typing import final

from .palette import Palette


@final
class LogLevel(Enum):
    """The five severity levels."""

    DEBUG = ("[DEBUG]  ", Palette.DIM)
    INFO = ("[INFO]   ", Palette.CYAN)
    SUCCESS = ("[SUCCESS]", Palette.BRIGHT_GREEN)
    WARN = ("[WARN]   ", Palette.BRIGHT_YELLOW)
    ERROR = ("[ERROR]  ", Palette.BRIGHT_RED_BOLD)

    @property
    def tag(self) -> str:
        """The fixed-width level tag, e.g. ``"[INFO]   "``."""
        return self.value[0]

    @property
    def color(self) -> Palette:
        """The tag color."""
        return self.value[1]


# =========================================================================

__all__ = ["LogLevel"]
