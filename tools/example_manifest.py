#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""The coverage contract for the ``examples/`` tree.

The tutorial has a frozen contract (``tests/contract_spec.py``), a
capture of real output, and a ``--check`` mode in CI.  The examples had
none of the three, which is why their coverage was never a number anyone
could fail a build over.

This module is the missing piece, and like the tutorial's contract it is
**data, not prose**.  Each row says what one example is responsible for
exercising:

* ``surface`` -- the API names the file must reference, written as they
  appear in the source (``BitOps.byte_swap64``, ``kdbg.sym``, ``walk``
  for a bare free function).  :mod:`tools.check_examples` parses the
  file and fails when a claimed name is absent, so a row cannot outlive
  the code it describes.
* ``commands`` -- the GDB commands the file invokes.  The checker
  verifies these are real command names, and the coverage report counts
  the union against the whole registry.

Coverage is the union of these claims.  That makes this table the single
place to raise the number: adding an example without a row changes
nothing, adding a row without the code fails the build.

Two honest limits, both written down rather than left implicit:

* **Constants are excluded.**  ``KPageTable``'s 21 constant names are
  already tabulated in ``README.md``; an example that referenced them
  would be transcribing a table.  :func:`tools.check_examples.is_surface_name`
  filters them out by their ``UPPER_CASE`` spelling.
* **``REQUIRED_COMMAND_COVERAGE`` is a ratchet.**  It records how many
  commands the examples cover today and may only ever increase.  Phase 1
  of ``docs/example-coverage-plan.md`` raises it from 0 to 40; nothing
  lowers it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Directories the examples are grouped into, in report order.
EXAMPLE_ROOTS: tuple[str, ...] = ("api", "tracing", "breakpoints")

#: How many distinct commands the examples must cover between them.
#:
#: A ratchet, not a target: raise it when coverage grows, never lower it.
#: Today the examples demonstrate two invocations in a single file, both
#: incidental to a tracer; Phase 1 of the plan adds six workflow examples
#: that cover all 40.
REQUIRED_COMMAND_COVERAGE: int = 0


@dataclass(frozen=True)
class Example:
    """One file under ``examples/`` and what it must exercise."""

    #: Path relative to the repository root.
    path: str
    #: What a reader gets from it, in one line.
    purpose: str
    #: ``script`` files are parsed for ``surface``; ``config`` files are
    #: only checked for their existence and their README link.
    kind: str = "script"
    #: API names the file must reference, spelled as in the source.
    surface: tuple[str, ...] = ()
    #: GDB commands the file invokes.
    commands: tuple[str, ...] = ()
    #: The README that must link to this file.
    readme: str = ""


def _example(root: str, name: str, **kwargs: object) -> Example:
    return Example(
        path=f"examples/{root}/{name}",
        readme=f"examples/{root}/README.md",
        **kwargs,  # type: ignore[arg-type]
    )


#: Every example, grouped as the directory tree groups them.
EXAMPLES: tuple[Example, ...] = (
    # --- api/ -----------------------------------------------------------
    _example(
        "api", "hello.py",
        purpose="the smallest script: installed names, the outside-GDB "
                "fallback, and four pure-Python calls",
        surface=(
            "BitOps.byte_swap64",
            "BitOps.popcount",
            "KAddr.is_canonical",
            "KAddr.is_kernel",
            "KPageTable.page_offset",
            "KPageTable.split_4",
        ),
    ),
    _example(
        "api", "trace.py",
        purpose="using the installed public API directly after gdbinit.py",
        surface=(
            "BitOps.byte_swap64",
            "BitOps.popcount",
            "KAddr.is_canonical",
            "KAddr.is_direct_map",
            "KPageTable.split_4",
            "kdbg.print_slab",
            "kdbg.sym",
            "kdbg.u64",
            "bp_spec",
            "walk",
        ),
    ),
    _example(
        "api", "slab_snapshot.py",
        purpose="a full slab report with no debugger at all",
        surface=(
            "IntFmt.addr",
            "IntFmt.hex64",
            "IntFmt.pfn",
            "IntFmt.size",
            "KAddr.virt_to_page",
            "KAddr.virt_to_phys",
            "KPageTable.pte_flags",
            "KPageTable.pte_phys",
            "KPageTable.pte_to_phys",
            "KPageTable.split_4",
        ),
    ),
    _example(
        "api", "gdbinit.example",
        purpose="loading KernLens in every session",
        kind="config",
    ),
    # --- tracing/ -------------------------------------------------------
    _example(
        "tracing", "gdb_tracer.py",
        purpose="a kfree breakpoint plus two prefixed commands",
        surface=(
            "kdbg.addr",
            "kdbg.bp_spec",
            "kdbg.info",
            "kdbg.link_text",
            "kdbg.print_slab",
            "kdbg.warn",
        ),
    ),
    _example(
        "tracing", "cve_2025_38616_trace.py",
        purpose="a CVE-2025-38616 KTLS use-after-free tracer",
        surface=(
            "kdbg.addr",
            "kdbg.arg",
            "kdbg.backtrace",
            "kdbg.bp_spec",
            "kdbg.branch",
            "kdbg.chain",
            "kdbg.color_chain",
            "kdbg.cpu_online",
            "kdbg.cur_cpu",
            "kdbg.kv",
            "kdbg.kv_cpu",
            "kdbg.kv_err",
            "kdbg.kv_hex",
            "kdbg.kv_int",
            "kdbg.kv_online",
            "kdbg.kv_trans",
            "kdbg.link_text",
            "kdbg.nr_cpus",
            "kdbg.nr_nodes",
            "kdbg.print_slab",
            "kdbg.read_field",
            "kdbg.read_kvar",
            "kdbg.style",
            "kdbg.u64",
            "arg",
            "chain",
            "cur_cpu",
            "link_text",
            "nr_cpus",
        ),
    ),
    # --- breakpoints/ ---------------------------------------------------
    _example(
        "breakpoints", "conditional.py",
        purpose="stop only when the freed object is the one being watched",
        surface=(
            "kdbg.bp_spec",
            "kdbg.info",
            "kdbg.slab_object",
            "kdbg.u64",
            "kdbg.warn",
        ),
    ),
    _example(
        "breakpoints", "watchfield.py",
        purpose="report only the write that reaches a chosen value",
        surface=("kdbg.warn",),
    ),
)


def declares(example: Example) -> bool:
    """Whether an example makes any coverage claim at all.

    A row with neither ``surface`` nor ``commands`` contributes nothing
    to the report, which is a legitimate state for a config sample but
    worth flagging for a script.
    """
    return bool(example.surface or example.commands)


__all__ = [
    "EXAMPLE_ROOTS",
    "EXAMPLES",
    "Example",
    "REQUIRED_COMMAND_COVERAGE",
    "declares",
]