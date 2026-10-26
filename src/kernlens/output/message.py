#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Semantic message colours, mirroring pwndbg's ``pwndbg.color.message``.

Commands wrap user-facing text in these helpers instead of raising on
soft errors: a failed lookup prints :func:`error` / :func:`warn` and
returns, exactly as pwndbg does.  Every helper is a no-op when colour is
disabled (``kl-color off``), so ``kdbg.disable_color()`` keeps output
byte-identical plain text.
"""

from __future__ import annotations

#: ANSI SGR codes, kept private so callers use the role helpers.
_NORMAL = "\x1b[0m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_BLUE = "\x1b[34m"
_PURPLE = "\x1b[35m"
_LIGHT_RED = "\x1b[91m"
_LIGHT_GREEN = "\x1b[92m"
_WHITE = "\x1b[97m"

#: Module-level switch toggled by ``kdbg.enable_color`` / ``disable_color``.
_color_enabled: bool = True


def set_color_enabled(enabled: bool) -> None:
    """Enable or disable colour for every message helper."""
    global _color_enabled
    _color_enabled = bool(enabled)


def color_enabled() -> bool:
    """Whether the message helpers currently emit ANSI sequences."""
    return _color_enabled


def colorize(text: object, color: str) -> str:
    """Wrap *text* in *color* (no-op when colour is disabled)."""
    plain = str(text)
    if not _color_enabled or not color:
        return plain
    return f"{color}{plain}{_NORMAL}"


def error(text: object) -> str:
    """An error message (red)."""
    return colorize(text, _RED)


def warn(text: object) -> str:
    """A warning message (yellow)."""
    return colorize(text, _YELLOW)


def hint(text: object) -> str:
    """A hint or marker message (yellow)."""
    return colorize(text, _YELLOW)


def notice(text: object) -> str:
    """A section notice such as ``Examples:`` (purple)."""
    return colorize(text, _PURPLE)


def success(text: object) -> str:
    """A success message (green)."""
    return colorize(text, _GREEN)


def info(text: object) -> str:
    """An informational message (white)."""
    return colorize(text, _WHITE)


def on(text: object) -> str:
    """An "on" status (green)."""
    return colorize(text, _GREEN)


def off(text: object) -> str:
    """An "off" status (red)."""
    return colorize(text, _RED)


def system(text: object) -> str:
    """A system message (light red)."""
    return colorize(text, _LIGHT_RED)


def debug(text: object) -> str:
    """A debug message (blue)."""
    return colorize(text, _BLUE)


def highlight(text: object) -> str:
    """An emphasised value (light green)."""
    return colorize(text, _LIGHT_GREEN)


__all__ = [
    "color_enabled",
    "colorize",
    "debug",
    "error",
    "hint",
    "highlight",
    "info",
    "notice",
    "off",
    "on",
    "set_color_enabled",
    "success",
    "system",
    "warn",
]