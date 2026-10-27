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
#: Phase 0 shipped at 0, when the only executed command was an incidental
#: `kl-base` inside a tracer.  The six workflow examples added in Phase 1
#: take it to 35 of the 40; the remaining five are listed below and are
#: deliberately left for a later phase rather than faked here.
REQUIRED_COMMAND_COVERAGE: int = 35

#: Commands no example executes yet, and why.  Recorded so that "35 of 40"
#: reads as a decision rather than an oversight -- and so that whoever
#: closes the gap knows what the gap is.
UNCOVERED_COMMANDS: dict[str, str] = {
    "kernlens-bits": "bit/integer primitives; a tour is planned for Phase 3",
    "kernlens-int": "same as kernlens-bits",
    "kernlens-buddydump": "needs a workload that leaves free blocks at a known order",
    "kernlens-kbpf": "needs BPF programs loaded in the target",
    "kernlens-kdmabuf": "needs a DMA-buf exporter; nothing exports on an idle VM",
}


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
    _example(
        "api", "kernel_facts.py",
        purpose="establish what the target is before trusting an address",
        commands=(
            "kernlens-kversion",
            "kernlens-kcmdline",
            "kernlens-kconfig",
            "kernlens-kchecksec",
            "kernlens-kmod",
            "kernlens-ksyscalls",
            "kernlens-klookup",
            "kernlens-kdmesg",
        ),
    ),
    _example(
        "api", "address_tour.py",
        purpose="carry one address through all nine page-table views",
        surface=(
            "KAddr.virt_to_phys",
            "kdbg.page_bytes",
            "kdbg.walk",
            "read_kvar",
        ),
        commands=(
            "kernlens-base",
            "kernlens-addr",
            "kernlens-page",
            "kernlens-pt",
            "kernlens-walk",
            "kernlens-pagewalk",
            "kernlens-pte",
            "kernlens-v2p",
            "kernlens-p2v",
            "kernlens-pageinfo",
        ),
    ),
    _example(
        "api", "slab_tour.py",
        purpose="read allocator state from the cache down to one object",
        surface=("kdbg.cpu_freelist", "kdbg.slab_cache"),
        commands=("kernlens-base", "kernlens-slab", "kernlens-buddy"),
    ),
    _example(
        "api", "symbols_tour.py",
        purpose="resolve a symbol, then read it, then decode it",
        surface=("kdbg.lookup",),
        commands=(
            "kernlens-base",
            "kernlens-klookup",
            "kernlens-sym",
            "kernlens-read",
            "kernlens-kvar",
            "kernlens-read-field",
            "kernlens-bt",
            "kernlens-chain",
        ),
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
        # `commands` lists only what the tracer *executes*.  It names
        # `kl-kaslr` and `kl-kaslr-offset` in its banner and forwards to
        # them through `_delegate_kaslr()`, which builds the command name
        # dynamically (`f"kl-{command}"`) and so cannot be resolved
        # statically -- deliberately not claimed.
        commands=("kernlens-base",),
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
    _example(
        "breakpoints", "per_cpu.py",
        purpose="read the right CPU's copy of a per-CPU variable",
        surface=("kdbg.nr_cpus", "kdbg.percpu_off"),
        commands=(
            "kernlens-base",
            "kernlens-cpu",
            "kernlens-percpu",
            "kernlens-msr",
        ),
    ),
    # --- tracing/ (continued) -------------------------------------------
    _example(
        "tracing", "kaslr_retarget.py",
        purpose="make a tracer work when the KASLR slide is not what you assumed",
        surface=("kdbg.link_text",),
        commands=(
            "kernlens-status",
            "kernlens-kbase",
            "kernlens-base",
            "kernlens-kaslr",
            "kernlens-kaslr-offset",
            "kernlens-color",
            "kernlens-help",
            "kernlens-sym",
            "kernlens-kvar",
        ),
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