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
#: took it to 35 of the 40.
#:
#: Phase 3 (the three pure-Python tours) deliberately does not raise it:
#: it grew *surface* coverage -- IntCodec from 0/21 to 8, BitOps from 2/44
#: to 40, IntFmt from 4/26 to 25 -- without adding a command, because the
#: primitives are reachable from Python and have no command of their own.
#: Raising this number without adding a command would be a lie; the
#: surface totals are what Phase 3 moved.
REQUIRED_COMMAND_COVERAGE: int = 37

#: Commands no example executes yet, and why.  Recorded so that "37 of 40"
#: reads as a decision rather than an oversight -- and so that whoever
#: closes the gap knows what the gap is.
UNCOVERED_COMMANDS: dict[str, str] = {
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
    #: Where the file can be executed, and therefore where it can be
    #: *tested* rather than merely inspected.
    #:
    #: ``"host"`` -- runs from a plain interpreter, so a test can call it
    #: and assert on its output.  ``"gdb"`` -- needs a live target, so the
    #: only check available in CI is ``tools/run_examples_gdb.py``.
    #:
    #: The default is deliberately the weaker claim.  Declaring ``host``
    #: is a promise that a test enforces: ``tests/integration/
    #: test_examples_pure.py`` runs every such file and fails if it
    #: exits non-zero.  A file that quietly stops being portable would
    #: otherwise keep its ``host`` claim and never be executed again --
    #: which is the failure mode this field exists to prevent.
    runs_on: str = "gdb"
    #: Arguments passed when the file is executed on the host.  Only
    #: meaningful with ``runs_on="host"``.
    argv: tuple[str, ...] = ()
    #: The command line ``tools/run_examples_gdb.py`` should type at the
    #: prompt to exercise this example, when one invocation with no
    #: arguments is not enough.
    #:
    #: It defaults to the example's own registered command, which is right
    #: for the tours.  It has to be spelled out for the files that need
    #: an argument -- ``kbp-object`` raises ``GdbError`` without an
    #: address, and ``kernlens-tracer-slab`` with it -- and for the two
    #: monitoring commands, whose no-argument form installs a breakpoint
    #: that only a later kernel event would reveal.
    probe: str = ""


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
        "api", "hello_sample.py",
        purpose="the smallest script: installed names, the outside-GDB "
                "fallback, and four pure-Python calls",
        runs_on="host",
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
        "api", "installed_api_tour.py",
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
        runs_on="host",
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
        "api", "kernel_facts_tour.py",
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
        "api", "freelist_walk.py",
        purpose=(
            "decode the SLUB freelist instead of describing it -- the "
            "stored word, the arithmetic that turns it into a pointer, "
            "and the page-versus-head distinction that makes the count "
            "readable"
        ),
        surface=(
            "kdbg.cache_name",
            "kdbg.compound_head",
            "kdbg.cpu_active_slab",
            "kdbg.cpu_freelist",
            "kdbg.cpu_slab_ptr",
            "kdbg.decode_freeptr",
            "kdbg.freelist_dist",
            "kdbg.freeptr_offset",
            "kdbg.freeptr_random",
            "kdbg.head_to_page",
            "kdbg.in_partial",
            "kdbg.kconfig_get",
            "kdbg.neighbour_objects",
            "kdbg.nr_cpus",
            "kdbg.object_index",
            "kdbg.page_bytes",
            "kdbg.partial_info",
            "kdbg.print_slab",
            "kdbg.slab_cache",
            "kdbg.slab_counters",
            "kdbg.slab_state",
            "kdbg.u64",
        ),
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
    _example(
        "api", "intcodec_tour.py",
        purpose="round-trip every integer width, in both byte orders",
        runs_on="host",
        surface=(
            "IntCodec.is_in_range",
            "IntCodec.pack",
            "IntCodec.pack_array",
            "IntCodec.pack_i16",
            "IntCodec.pack_i32",
            "IntCodec.pack_i64",
            "IntCodec.pack_i8",
            "IntCodec.pack_u16",
            "IntCodec.pack_u32",
            "IntCodec.pack_u64",
            "IntCodec.pack_u8",
            "IntCodec.unpack",
            "IntCodec.unpack_array",
            "IntCodec.unpack_i16",
            "IntCodec.unpack_i32",
            "IntCodec.unpack_i64",
            "IntCodec.unpack_i8",
            "IntCodec.unpack_u16",
            "IntCodec.unpack_u32",
            "IntCodec.unpack_u64",
            "IntCodec.unpack_u8",
            "read_kvar",
        ),
    ),
    _example(
        "api", "intfmt_tour.py",
        purpose="format the values a kernel reader actually produces",
        runs_on="host",
        surface=(
            "IntFmt.addr",
            "IntFmt.bits",
            "IntFmt.bytes_ascii",
            "IntFmt.bytes_cstring",
            "IntFmt.bytes_dump",
            "IntFmt.bytes_hex",
            "IntFmt.bytes_u16_array",
            "IntFmt.bytes_u32_array",
            "IntFmt.bytes_u64_array",
            "IntFmt.duration_ns",
            "IntFmt.field_off",
            "IntFmt.flags",
            "IntFmt.hex",
            "IntFmt.hex8",
            "IntFmt.hex16",
            "IntFmt.hex32",
            "IntFmt.hex64",
            "IntFmt.mask",
            "IntFmt.off",
            "IntFmt.page_off",
            "IntFmt.percent",
            "IntFmt.pfn",
            "IntFmt.signed",
            "IntFmt.signed_hex",
            "IntFmt.size",
            "IntFmt.timestamp",
            "read_kvar",
        ),
    ),
    _example(
        "api", "bitops_tour.py",
        purpose="decode the bitfields a kernel struct is actually made of",
        runs_on="host",
        surface=(
            "BitOps.align_down",
            "BitOps.align_up",
            "BitOps.bit_clear",
            "BitOps.bit_set",
            "BitOps.bit_test",
            "BitOps.bit_toggle",
            "BitOps.byte_swap",
            "BitOps.byte_swap16",
            "BitOps.byte_swap32",
            "BitOps.byte_swap64",
            "BitOps.clear_bits",
            "BitOps.coerce",
            "BitOps.cpumask_count",
            "BitOps.cpumask_first",
            "BitOps.cpumask_next",
            "BitOps.cpumask_test",
            "BitOps.extract_bits",
            "BitOps.first_set",
            "BitOps.insert_bits",
            "BitOps.is_aligned",
            "BitOps.is_power_of_2",
            "BitOps.last_set",
            "BitOps.leading_zeros",
            "BitOps.log2_ceil",
            "BitOps.log2_floor",
            "BitOps.mask",
            "BitOps.next_power_of_2",
            "BitOps.popcount",
            "BitOps.rotate_left",
            "BitOps.rotate_right",
            "BitOps.sign_bit",
            "BitOps.sign_extend",
            "BitOps.signed_range",
            "BitOps.to_i16",
            "BitOps.to_i32",
            "BitOps.to_i64",
            "BitOps.to_i8",
            "BitOps.to_u16",
            "BitOps.to_u32",
            "BitOps.to_u64",
            "BitOps.to_u8",
            "BitOps.trailing_zeros",
            "BitOps.truncate",
            "BitOps.unsigned_range",
            "kdbg.kvar_addr",
            "kdbg.nr_cpus",
        ),
    ),
    _example(
        "api", "bits_tour.py",
        purpose="read a packed word with the calls kl-bits makes",
        # `kl-bits` needs no debuggee: it is `BitOps` on a number the
        # caller supplies.  That made "the command form has no example"
        # an odd gap -- the barrier was not the missing target, it was
        # that nobody had written the example.
        runs_on="host",
        commands=("kernlens-bits",),
        surface=(
            "BitOps.bit_test",
            "BitOps.cpumask_count",
            "BitOps.cpumask_first",
            "BitOps.cpumask_next",
            "BitOps.extract_bits",
            "BitOps.first_set",
            "BitOps.is_power_of_2",
            "BitOps.last_set",
            "BitOps.log2_floor",
            "BitOps.popcount",
        ),
    ),
    _example(
        "api", "int_tour.py",
        purpose="one value as every width, the way kl-int shows it",
        runs_on="host",
        commands=("kernlens-int",),
        surface=(
            "IntCodec.is_in_range",
            "IntCodec.pack_array",
            "IntCodec.pack_u32",
            "IntCodec.unpack_i32",
            "IntCodec.unpack_u32",
        ),
    ),
    # --- tracing/ -------------------------------------------------------
    _example(
        "tracing", "gdb_tracer.py",
        purpose="a kfree breakpoint plus two prefixed commands",
        # `kernlens-tracer-slab` raises GdbError without an expression, and
        # `kernlens-tracer-color` with an argument.  Neither is the point
        # of the file; the point is that both register under a prefix so
        # they coexist with pwndbg.  Driving the colour command is the
        # invocation that touches the most code without needing a target
        # to have been stopped somewhere specific.
        probe="kernlens-tracer-color",
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
        "tracing", "cve_2025_38616_tracer.py",
        purpose="a CVE-2025-38616 KTLS use-after-free tracer",
        # `trace-start` installs breakpoints and then waits for the kernel
        # to hit them, so in a batch run it blocks rather than returning.
        # The harness still sources the file -- which is what catches a
        # tracer that no longer loads -- and stops there.  The kaslr
        # wrappers it forwards to are exercised by `kaslr_retarget_tour.py`.
        probe="-",
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
        "breakpoints", "conditional_bp.py",
        purpose="stop only when the freed object is the one being watched",
        # `kbp-object` takes exactly one address and raises GdbError
        # otherwise.  `init_task` is a real symbol whose address is a
        # valid pointer, so the probe reaches the code that resolves and
        # uses it rather than stopping at the argument check.
        probe="kbp-object &init_task",
        surface=(
            "kdbg.bp_spec",
            "kdbg.info",
            "kdbg.slab_object",
            "kdbg.u64",
            "kdbg.warn",
        ),
    ),
    _example(
        "breakpoints", "watchfield_bp.py",
        purpose="report only the write that reaches a chosen value",
        # `kwatch-field` installs a *hardware* watchpoint, and the QEMU
        # gdbstub behind the test VM rejects those ("this target may not
        # support them").  The harness therefore sources the file -- which
        # proves the command registers and the module imports -- and stops
        # there.  Driving it needs a target that implements watchpoints,
        # which is a property of the debuggee rather than of this example.
        probe="-",
        surface=("kdbg.warn",),
    ),
    _example(
        "breakpoints", "per_cpu_bp.py",
        purpose="read the right CPU's copy of a per-CPU variable",
        # The bare command installs a breakpoint and waits, so it would
        # look like a pass while proving nothing.  `--off` exercises the
        # removal path the file has to get right.
        probe="pbreak --off",
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
        "tracing", "kaslr_retarget_tour.py",
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