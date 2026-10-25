#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Severity-leveled stdout writer."""

from __future__ import annotations

import sys
import time
from typing import ClassVar, TextIO

from .levels import LogLevel
from .palette import Palette


class Logger:
    """Severity-leveled stdout writer with per-session debugging state."""

    __slots__: tuple[str, ...] = (
        "_color_enabled",
        "_counters",
        "_min_level",
        "_once_keys",
        "_show_tag",
        "_show_time",
        "_stream",
        "_throttle",
    )

    _SEVERITY: ClassVar[dict[LogLevel, int]] = {
        LogLevel.DEBUG: 10,
        LogLevel.INFO: 20,
        LogLevel.SUCCESS: 25,
        LogLevel.WARN: 30,
        LogLevel.ERROR: 40,
    }

    def __init__(
        self,
        color_enabled: bool = True,
        min_level: LogLevel = LogLevel.DEBUG,
        show_tag: bool = True,
        show_time: bool = False,
        stream: TextIO | None = None,
    ) -> None:
        self._color_enabled: bool = color_enabled
        self._min_level: LogLevel = min_level
        self._show_tag: bool = show_tag
        self._show_time: bool = show_time
        self._stream: TextIO | None = stream
        self._once_keys: set[str] = set()
        self._counters: dict[str, int] = {}
        self._throttle: dict[str, float] = {}

    # --- settings -------------------------------------------------------

    @property
    def color_enabled(self) -> bool:
        return self._color_enabled

    def set_color_enabled(self, enabled: bool) -> None:
        self._color_enabled = enabled

    def enable_color(self) -> None:
        self._color_enabled = True

    def disable_color(self) -> None:
        self._color_enabled = False

    @property
    def min_level(self) -> LogLevel:
        return self._min_level

    def set_min_level(self, level: LogLevel) -> None:
        self._min_level = level

    @property
    def show_tag(self) -> bool:
        return self._show_tag

    def set_show_tag(self, enabled: bool) -> None:
        self._show_tag = enabled

    @property
    def show_time(self) -> bool:
        return self._show_time

    def set_show_time(self, enabled: bool) -> None:
        self._show_time = enabled

    def set_stream(self, stream: TextIO | None) -> None:
        self._stream = stream

    def is_enabled(self, level: LogLevel) -> bool:
        return self._SEVERITY[level] >= self._SEVERITY[self._min_level]

    # --- severity levels ------------------------------------------------

    def debug(self, message: str) -> None:
        self._emit(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        self._emit(LogLevel.INFO, message)

    def success(self, message: str) -> None:
        self._emit(LogLevel.SUCCESS, message)

    def warn(self, message: str) -> None:
        self._emit(LogLevel.WARN, message)

    def error(self, message: str) -> None:
        self._emit(LogLevel.ERROR, message)

    # --- once / throttle -----------------------------------------------

    def once(
        self, key: str, message: str,
        level: LogLevel = LogLevel.INFO,
    ) -> bool:
        if key in self._once_keys:
            return False
        self._once_keys.add(key)
        self._emit(level, message)
        return True

    def reset_once(self) -> None:
        self._once_keys.clear()

    def throttle(
        self, key: str, interval: float, message: str,
        level: LogLevel = LogLevel.INFO,
    ) -> bool:
        if interval <= 0:
            self._emit(level, message)
            return True
        now = time.monotonic()
        last = self._throttle.get(key, float("-inf"))
        if now - last < interval:
            return False
        self._throttle[key] = now
        self._emit(level, message)
        return True

    def reset_throttle(self) -> None:
        self._throttle.clear()

    # --- counters -------------------------------------------------------

    def counter(self, key: str, delta: int = 1) -> int:
        self._counters[key] = self._counters.get(key, 0) + delta
        return self._counters[key]

    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def reset_counters(self) -> None:
        self._counters.clear()

    def summary(
        self, *, level: LogLevel = LogLevel.INFO, sort_by: str = "key",
    ) -> None:
        if not self._counters:
            self._emit(level, "counters: <empty>")
            return
        if sort_by == "value":
            items = sorted(
                self._counters.items(), key=lambda item: (-item[1], item[0])
            )
        else:
            items = sorted(self._counters.items())
        self._emit(level, f"counters: {len(items)}")
        for key, value in items:
            self._emit(level, f"  {key}: {value}")

    # --- checks ---------------------------------------------------------

    def check(
        self, cond: bool, ok_msg: str,
        *, fail_msg: str | None = None,
        fail_level: LogLevel = LogLevel.WARN,
    ) -> bool:
        if cond:
            self._emit(LogLevel.INFO, ok_msg)
        else:
            self._emit(
                fail_level,
                fail_msg if fail_msg is not None else f"FAIL: {ok_msg}",
            )
        return cond

    def assert_(self, cond: bool, message: str) -> bool:
        if not cond:
            self._emit(LogLevel.ERROR, f"ASSERT: {message}")
        return cond

    # --- helpers --------------------------------------------------------

    def fmt_line(self, level: LogLevel, message: str) -> str:
        prefix = self._fmt_prefix(level)
        return f"{prefix} {message}" if prefix else message

    def banner(
        self, title: str, *,
        char: str = "=", width: int = 80,
        color: Palette | str = Palette.CYAN,
    ) -> None:
        if width <= len(title) + 2:
            line = title
        else:
            pad = width - len(title) - 2
            left = pad // 2
            right = pad - left
            line = f"{char * left} {title} {char * right}"
        self._emit(LogLevel.INFO, self._paint(line, color))

    def rule(
        self, *,
        char: str = "-", width: int = 80,
        color: Palette | str = Palette.DIM,
    ) -> None:
        self._emit(LogLevel.INFO, self._paint(char * width, color))

    def reset(self) -> None:
        self._once_keys.clear()
        self._counters.clear()
        self._throttle.clear()

    # --- internals ------------------------------------------------------

    def _emit(self, level: LogLevel, message: str) -> None:
        if not self.is_enabled(level):
            return
        stream = self._stream if self._stream is not None else sys.stdout
        print(self.fmt_line(level, message), file=stream, flush=True)

    def _fmt_prefix(self, level: LogLevel) -> str:
        parts: list[str] = []
        if self._show_time:
            parts.append(self._paint(f"[{time.time():12.6f}]", Palette.DIM))
        if self._show_tag:
            parts.append(self._paint(level.tag, level.color))
        return " ".join(parts)

    def _paint(self, text: str, color: Palette | str) -> str:
        if not color or not self._color_enabled:
            return text
        return f"{color}{text}{Palette.RESET}"


# =========================================================================

__all__ = ["Logger"]
