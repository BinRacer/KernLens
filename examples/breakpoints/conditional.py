#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# ruff: noqa: F821
"""A conditional breakpoint that stops only on interesting calls.

The pattern here is "break, test, decide": instead of stopping at every
``kfree`` and reading output by hand, the breakpoint evaluates a
condition at the trap and returns ``True`` only when the condition holds.
Every other hit is passed through silently, so the debuggee keeps
running and the interesting hit is the *only* thing that stops it.

Load after ``gdbinit.py``::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/breakpoints/conditional.py
    (gdb) kbp-object 0xffff9a0d44c42b00
    (gdb) continue

``kbp-object`` also removes itself after the first stop unless
``--keep`` is given, so a repeated call does not flood the session.
"""

from __future__ import annotations

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit(
        "conditional.py must be sourced by GDB (it defines a breakpoint)"
    ) from exc

#: The argument register for the first parameter on x86-64 System V.
ARG0 = "$rdi"


class ObjectFreeBreakpoint(gdb.Breakpoint):
    """Stop only when ``kfree`` is asked to free a specific object.

    ``kfree`` may legitimately receive a pointer *inside* an object (it
    rounds down to the slab head), so the comparison is made on the slab
    head the cache reports, not on the raw argument.  That is what makes
    this a useful filter: trapping on the exact argument would miss the
    interior-pointer frees that matter in a use-after-free.
    """

    def __init__(
        self,
        spec: str,
        target: int,
        *,
        keep: bool = False,
    ) -> None:
        super().__init__(spec, internal=False)
        self.silent = True
        self._target = target
        self._keep = keep
        self._hits = 0
        self._matches = 0

    def stop(self) -> bool:
        self._hits += 1
        try:
            argument = kdbg.u64(ARG0)  # noqa: F821 - installed by gdbinit
        except (gdb.error, TypeError, ValueError) as exc:
            kdbg.warn(f"cannot read {ARG0}: {exc}")  # noqa: F821
            return False
        if not argument:
            return False
        obj = _slab_object(argument)
        if obj != self._target:
            return False
        self._matches += 1
        kdbg.info(  # noqa: F821
            f"free of the target: arg={argument:#x} object={obj:#x} "
            f"(hit {self._matches}/{self._hits})"
        )
        if not self._keep:
            self.enabled = False
        return True


def _slab_object(address: int) -> int:
    """Return the object start holding *address*, or *address* itself.

    ``kdbg.slab_object`` returns ``(object_addr, cache)`` or ``None``.
    When the address is not in a SLUB object -- a vmalloc address, a
    stack address, a user pointer -- the honest answer is the address
    unchanged, so the caller can still compare it against its target.
    """
    try:
        found = kdbg.slab_object(address)  # noqa: F821 - from gdbinit
    except (gdb.error, AttributeError, TypeError, ValueError):
        return address
    if not found:
        return address
    return found[0]


class ObjectBreakpointCommand(gdb.Command):
    """``kbp-object <address> [--keep]`` -- break on frees of one object."""

    def __init__(self) -> None:
        super().__init__("kbp-object", gdb.COMMAND_BREAKPOINTS)

    def invoke(self, argument: str, from_tty: bool) -> None:
        del from_tty
        words = argument.split()
        keep = "--keep" in words
        words = [w for w in words if w != "--keep"]
        if len(words) != 1:
            raise gdb.GdbError("usage: kbp-object <address> [--keep]")
        try:
            target = _slab_object(int(gdb.parse_and_eval(words[0])))
        except (gdb.error, TypeError, ValueError) as exc:
            raise gdb.GdbError(
                f"cannot evaluate {words[0]!r}: {exc}"
            ) from exc
        # ``bp_spec`` turns the symbol into a runtime address; a bare
        # symbol under KASLR would be planted at its link-time address.
        breakpoint = ObjectFreeBreakpoint(
            kdbg.bp_spec("kfree"), target, keep=keep,  # noqa: F821
        )
        gdb.write(
            f"kbp-object: watching frees of {target:#x}"
            f"{'' if keep else ' (removes itself after the first match)'}\n"
        )
        if breakpoint is None:  # pragma: no cover - defensive
            raise gdb.GdbError("failed to create the breakpoint")


#: A real object address from the test kernel, for the sourced example:
#: the ``kmalloc-1k`` cache, whose slab head the project's fixtures use.
SAMPLE_OBJECT = 0xFFFF9A0D44C42B00

# ``gdb.Command`` registers itself in ``__init__``, so defining the class
# is not enough: the instance has to exist.  Sourcing this file runs in
# ``__main__``, so the object is kept alive by that namespace.
_OBJECT_COMMAND = ObjectBreakpointCommand()

gdb.write(
    "conditional.py: kbp-object <address> [--keep] is ready "
    f"(sample: kbp-object {SAMPLE_OBJECT:#x})\n"
)