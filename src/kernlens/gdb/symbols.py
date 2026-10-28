#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Symbol, source-line, backtrace, and call-chain resolution."""

from __future__ import annotations

from typing import cast, final

import gdb

from ..output import Logger, Palette
from ._types import _IntConvertible, _StrLike
from .config import DebugConfig
from .styler import KernelStyler


@final
class SymbolResolver:
    """Symbol name, file:line, and backtrace resolution.

    KASLR-aware: on lookup miss the runtime pc is shifted back by
    ``config.kaslr_offset`` and the link-time address is tried against
    vmlinux's debug info.  This makes both ``sym()`` and ``line()``
    work on a relocated kernel.
    """

    __slots__: tuple[str, ...] = ("_config", "_logger", "_styler")

    def __init__(
        self,
        config: DebugConfig,
        styler: KernelStyler,
        logger: Logger,
    ) -> None:
        self._config: DebugConfig = config
        self._styler: KernelStyler = styler
        self._logger: Logger = logger

    def sym(self, pc: int) -> str:
        """Resolve a runtime pc to a symbol name."""
        if pc <= 0:
            return "?"
        candidates = [pc]
        if self._config.kaslr_offset:
            candidates.append(
                (pc - self._config.kaslr_offset) & 0xFFFFFFFFFFFFFFFF
            )
        for addr in candidates:
            if addr <= 0:
                continue
            try:
                raw = gdb.execute(f"info symbol {addr:#x}", to_string=True)
            except gdb.error:
                continue
            text = cast(_StrLike, raw).strip()
            if "No symbol matches" in text:
                continue
            name = text.split(" in section")[0].split(" +")[0].strip()
            if name.startswith("0x"):
                continue
            return name
        return "?"

    def line(self, pc: int) -> str:
        """Return ``file:line`` for a runtime pc."""
        candidates = [pc]
        if self._config.kaslr_offset:
            candidates.insert(
                0,
                (pc - self._config.kaslr_offset) & 0xFFFFFFFFFFFFFFFF,
            )
        for addr in candidates:
            if addr <= 0:
                continue
            try:
                sal = gdb.find_pc_line(addr)
            except gdb.error:
                continue
            if sal is None:
                continue
            try:
                symtab = sal.symtab
                lineno = sal.line
            except AttributeError:
                continue
            if symtab and lineno and lineno > 0:
                return f"{symtab.filename}:{lineno}"
        return "??"

    def _walk_pcs(self, depth: int) -> list[int]:
        """Collect up to ``depth`` pc values walking older frames."""
        pcs: list[int] = []
        frame: gdb.Frame | None
        try:
            frame = gdb.newest_frame()
        except gdb.error:
            return pcs
        while frame is not None and len(pcs) < depth:
            try:
                pc = int(cast(_IntConvertible, frame.pc()))
            except (gdb.error, TypeError, ValueError):
                break
            pcs.append(pc)
            try:
                frame = frame.older()
            except gdb.error:
                break
        return pcs

    def backtrace(self, depth: int) -> None:
        """Emit a multi-line backtrace with file:line per frame.

        The whole block is emitted through a single ``Logger.info``
        call: the first line carries the ``[INFO]`` tag, subsequent
        frame lines are printed verbatim so their indentation aligns
        under the header.
        """
        frames = self._walk_pcs(depth)
        if not frames:
            return
        lines: list[str] = [self._styler.style("bt:", Palette.CYAN)]
        for i, pc in enumerate(frames):
            name = self.sym(pc)
            loc = self.line(pc)
            if name == "?":
                lines.append(
                    f"{self._config.indent_nested}#{i}  "
                    + f"{self._styler.addr(pc)}  ??"
                )
            else:
                lines.append(
                    f"{self._config.indent_nested}#{i}  "
                    + f"{self._styler.addr(pc)}  "
                    + f"{self._styler.fn(name)}  "
                    + f"at {self._styler.loc(loc)}"
                )
        self._logger.info("\n".join(lines))

    def chain(self, depth: int) -> str:
        """Return ``fn1 <- fn2 <- fn3`` for the given call depth."""
        names: list[str] = []
        for pc in self._walk_pcs(depth):
            name = self.sym(pc)
            if name != "?":
                names.append(name)
        return " <- ".join(names) if names else "?"

    def color_chain(self, chain: str) -> str:
        """Colorize a chain string produced by :meth:`chain`."""
        if chain == "?":
            return chain
        return " <- ".join(
            self._styler.fn(part) for part in chain.split(" <- ")
        )


__all__ = ["SymbolResolver"]
