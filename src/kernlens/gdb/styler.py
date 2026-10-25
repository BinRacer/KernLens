#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Kernel-debug formatters layered on the generic styler."""

from __future__ import annotations

from typing import final

from ..output import Palette, Styler


@final
class KernelStyler(Styler):
    """Kernel-debug formatters layered on the generic :class:`Styler`.

    Inherits every primitive, ``kv`` family, container, layout,
    numeric, and symbol method from :class:`kernlens.output.Styler`, and
    adds the formatters whose meaning is specific to kernel debugging:

    * ``fn`` / ``loc`` — symbol name and ``file:line`` coloring.
    * ``depth_marker`` — the ``H@depthN`` SLUB marker.
    * ``branch`` — the ``nodefer`` / ``defer`` branch label.
    * ``fl_tag`` — a freelist pointer's relation to H.
    * ``kv_cpu`` / ``kv_online`` / ``kv_err`` / ``kv_trans`` — CPU,
      online-flag, socket-error and state-transition ``k=v`` helpers.

    When ``color_enabled`` is off, every formatter returns plain text.
    """

    __slots__: tuple[str, ...] = ()

    # --- symbol / location ----------------------------------------------

    def fn(self, name: str) -> str:
        """Format a function name in bright cyan."""
        if name in ("?", "??"):
            return "??"
        return self.style(name, Palette.BRIGHT_CYAN)

    def loc(self, location: str) -> str:
        """Format a ``file:line`` location in dim color."""
        if location in ("?", "??"):
            return "??"
        return self.style(location, Palette.DIM)

    # --- SLUB-specific primitives ---------------------------------------

    def depth_marker(self, depth: int) -> str:
        """Format ``H@depthN`` in bright yellow."""
        return self.style(
            f"H@depth{depth}",
            Palette.BRIGHT_YELLOW_BOLD,
        )

    def branch(self, branch_label: str) -> str:
        """Format a ``nodefer`` / ``defer`` branch label."""
        if branch_label.startswith("nodefer"):
            return (
                self.style("nodefer", Palette.GREEN)
                + self.style(branch_label[len("nodefer"):], Palette.DIM)
            )
        if branch_label.startswith("defer"):
            return (
                self.style("defer", Palette.BRIGHT_YELLOW_BOLD)
                + self.style(branch_label[len("defer"):], Palette.DIM)
            )
        return branch_label

    def fl_tag(self, value: int, head: int, short: bool = False) -> str:
        """Format a freelist pointer, color-coding its relation to H."""
        if not value:
            return self.style("NULL", Palette.GREEN)
        if short:
            if value == head:
                return self.style("=H", Palette.BRIGHT_RED_BOLD)
            return self.style("!=H", Palette.BRIGHT_GREEN)
        if value == head:
            return f"{value:#x}" + self.style("(=H)", Palette.BRIGHT_RED_BOLD)
        return f"{value:#x}" + self.style("(!=H)", Palette.BRIGHT_GREEN)

    # --- kernel-debug k=v helpers ---------------------------------------

    def kv_cpu(
        self, label: str, value: int | None, match_cpu: int = -999,
    ) -> str:
        """Format a CPU id, green when equal to ``match_cpu``."""
        if value is None or value < 0:
            return self.kv(label, "?", value_color=Palette.YELLOW)
        v_str = str(value)
        if match_cpu != -999 and value == match_cpu:
            return self.kv(label, v_str, value_color=Palette.GREEN)
        return self.kv(label, v_str, value_color=Palette.BRIGHT_CYAN)

    def kv_online(self, value: bool | None) -> str:
        """Format an online flag: green for ``True``, red for ``False``."""
        if value is None:
            return self.kv("online", "?", value_color=Palette.YELLOW)
        return self.kv(
            "online",
            "1" if value else "0",
            value_color=Palette.GREEN if value else Palette.RED,
        )

    def kv_err(self, value: int | None) -> str:
        """Format ``sk_err``: green when zero, bright red otherwise."""
        if value is None:
            return self.kv("sk_err", "?", value_color=Palette.YELLOW)
        return self.kv(
            "sk_err",
            str(value),
            value_color=Palette.GREEN if value == 0 else Palette.BRIGHT_RED,
        )

    def kv_trans(
        self,
        label: str,
        before: int,
        after: int,
        danger_if_zero: bool = True,
    ) -> str:
        """Format ``label before->after`` with direction-aware colors."""
        lbl = self.style(label, Palette.CYAN)
        if danger_if_zero and after == 0:
            after_color = Palette.BRIGHT_RED_BOLD
        elif after < before:
            after_color = Palette.BRIGHT_GREEN
        elif after > before:
            after_color = Palette.BRIGHT_YELLOW
        else:
            after_color = Palette.DIM
        return (
            lbl + " " + self.style(str(before), Palette.DIM)
            + "->"
            + self.style(str(after), after_color)
        )


__all__ = ["KernelStyler"]
