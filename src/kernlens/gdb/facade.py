#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Facade that composes the GDB adapter components.

:class:`KernelDebugger` owns one instance of each adapter and republishes
its methods under flat names (``kdbg.info``, ``kdbg.style``,
``kdbg.print_slab``).  :data:`_BINDINGS` below is the source of truth for
that surface: ``api.py`` derives the exported free functions from it, and
``__init__`` binds every entry with an explicit
``self.<name> = self.<component>.<member>`` assignment.  The assignments
are spelled out rather than generated with ``setattr`` so a type checker
can see each method's real signature -- with ``setattr`` the whole flat
surface was invisible and every ``kdbg.<name>`` was an attribute error.
``tests/unit/test_structure.py`` compares the two spellings so they cannot
drift.
"""

from __future__ import annotations

from typing import Final, final

from ..output import Logger
from ..output import message as message
from .config import DebugConfig
from .cpu import CpuInfo
from .kaslr import Kaslr
from .kbase import Kbase, KbaseResult
from .kernel import KernelInspector
from .reader import MemoryReader
from .slub import SlubInspector
from .styler import KernelStyler
from .symbols import SymbolResolver
from .walker import PageTableWalker

#: Stateful components composed into the facade, in attribute order.
COMPONENT_NAMES: tuple[str, ...] = (
    "config",
    "logger",
    "styler",
    "reader",
    "symbols",
    "kaslr",
    "kbase",
    "cpu",
    "walker",
    "kernel",
    "slub",
)

#: Every method republished on the facade as ``(public_name, component,
#: member, free_function)``.
#:
#: ``public_name`` is the flat name scripts call (``kdbg.<public_name>``),
#: ``component``/``member`` locate the implementation, and ``free_function``
#: marks the subset that ``api.py`` also installs as a bare function in a
#: sourced script's namespace.  This one table is the source of truth for
#: both the bound methods and ``api.FACADE_FUNCTIONS``.
_BINDINGS: tuple[tuple[str, str, str, bool], ...] = (
    # --- logging --------------------------------------------------------
    ("debug", "logger", "debug", False),
    ("info", "logger", "info", False),
    ("success", "logger", "success", False),
    ("warn", "logger", "warn", False),
    ("error", "logger", "error", False),
    ("once", "logger", "once", False),
    ("throttle", "logger", "throttle", False),
    ("counter", "logger", "counter", False),
    ("summary", "logger", "summary", False),
    ("check", "logger", "check", False),
    ("assert_", "logger", "assert_", False),
    ("banner", "logger", "banner", False),
    ("rule", "logger", "rule", False),
    ("fmt_line", "logger", "fmt_line", False),
    # --- styler: primitives / numeric / align ---------------------------
    ("style", "styler", "style", False),
    ("addr", "styler", "addr", False),
    ("hex", "styler", "hex", False),
    ("hex8", "styler", "hex8", False),
    ("hex16", "styler", "hex16", False),
    ("hex32", "styler", "hex32", False),
    ("hex64", "styler", "hex64", False),
    ("dec", "styler", "dec", False),
    ("size", "styler", "size", False),
    ("pfn", "styler", "pfn", False),
    ("percent", "styler", "percent", False),
    ("bits", "styler", "bits", False),
    ("ljust", "styler", "ljust", False),
    ("rjust", "styler", "rjust", False),
    ("center", "styler", "center", False),
    ("pad", "styler", "pad", False),
    ("truncate", "styler", "truncate", False),
    # --- styler: k=v family ---------------------------------------------
    ("kv", "styler", "kv", False),
    ("kv_int", "styler", "kv_int", False),
    ("kv_hex", "styler", "kv_hex", False),
    ("kv_bool", "styler", "kv_bool", False),
    # --- styler: containers ---------------------------------------------
    ("seq", "styler", "seq", False),
    ("list", "styler", "list", False),
    ("tuple", "styler", "tuple", False),
    ("set", "styler", "set", False),
    ("dict", "styler", "dict", False),
    ("pairs", "styler", "pairs", False),
    ("range", "styler", "range", False),
    ("named", "styler", "named", False),
    ("kv_seq", "styler", "kv_seq", False),
    # --- styler: layout -------------------------------------------------
    ("table", "styler", "table", False),
    ("box", "styler", "box", False),
    ("fmt_chain", "styler", "chain", False),
    ("cols", "styler", "cols", False),
    ("block", "styler", "block", False),
    ("highlight", "styler", "highlight", False),
    ("indent", "styler", "indent", False),
    ("fields", "styler", "fields", False),
    ("kv_group", "styler", "kv_group", False),
    # --- styler: symbols / progress -------------------------------------
    ("tick", "styler", "tick", False),
    ("cross", "styler", "cross", False),
    ("bullet", "styler", "bullet", False),
    ("arrow", "styler", "arrow", False),
    ("bar", "styler", "bar", False),
    # --- styler: kernel extras ------------------------------------------
    ("fn", "styler", "fn", False),
    ("loc", "styler", "loc", False),
    ("depth_marker", "styler", "depth_marker", False),
    ("branch", "styler", "branch", False),
    ("fl_tag", "styler", "fl_tag", False),
    ("kv_cpu", "styler", "kv_cpu", False),
    ("kv_online", "styler", "kv_online", False),
    ("kv_err", "styler", "kv_err", False),
    ("kv_trans", "styler", "kv_trans", False),
    # --- reader ---------------------------------------------------------
    ("u64", "reader", "u64", True),
    ("read_kvar", "reader", "read_kvar", True),
    ("kvar_addr", "reader", "kvar_addr", True),
    ("arg", "reader", "arg", True),
    ("read_field", "reader", "read_field", True),
    # --- symbols --------------------------------------------------------
    ("sym", "symbols", "sym", True),
    ("line", "symbols", "line", True),
    ("backtrace", "symbols", "backtrace", True),
    ("chain", "symbols", "chain", True),
    ("color_chain", "symbols", "color_chain", False),
    # --- kaslr ----------------------------------------------------------
    ("bp_spec", "kaslr", "bp_spec", True),
    ("link_text", "kaslr", "link_text", True),
    ("find_kbase", "kbase", "find", True),
    # --- cpu ------------------------------------------------------------
    ("nr_cpus", "cpu", "nr_cpus", True),
    ("nr_nodes", "cpu", "nr_nodes", True),
    ("cpu_online", "cpu", "cpu_online", True),
    ("cur_cpu", "cpu", "cur_cpu", True),
    ("percpu_off", "cpu", "percpu_off", True),
    # --- page tables ----------------------------------------------------
    ("walk", "walker", "walk", True),
    # --- kernel metadata ------------------------------------------------
    ("kversion", "kernel", "version", True),
    ("krelease", "kernel", "release", True),
    ("kcmdline", "kernel", "cmdline", True),
    ("kconfig", "kernel", "kconfig", True),
    ("kconfig_get", "kernel", "config_get", True),
    ("kconfig_contains", "kernel", "config_contains", True),
    ("kconfig_update", "kernel", "config_update", False),
    ("config_key", "kernel", "config_key", False),
    ("modules", "kernel", "modules", True),
    ("syscalls", "kernel", "syscalls", True),
    ("syscall_count", "kernel", "syscall_count", True),
    ("page_type", "kernel", "page_type", True),
    ("page_refcount", "kernel", "page_refcount", True),
    ("buddy_order", "kernel", "buddy_order", True),
    ("page_is_buddy", "kernel", "page_is_buddy", True),
    ("page_is_slab", "kernel", "page_is_slab", True),
    ("kallsyms", "kernel", "kallsyms", True),
    ("lookup", "kernel", "lookup", True),
    ("dmesg", "kernel", "dmesg", True),
    ("tk_epoch", "kernel", "tk_epoch", False),
    ("bpf_progs", "kernel", "bpf_progs", True),
    ("bpf_maps", "kernel", "bpf_maps", True),
    ("bpf_map_value", "kernel", "bpf_map_value", False),
    ("buddy_zones", "kernel", "buddy_zones", True),
    ("zone_spans", "kernel", "zone_spans", True),
    ("zone_of_pfn", "kernel", "zone_of_pfn", True),
    ("block_of_pfn", "kernel", "block_of_pfn", True),
    ("block_range", "kernel", "block_range", True),
    ("buddy_pfn", "kernel", "buddy_pfn", True),
    ("free_area_counts", "kernel", "free_area_counts", True),
    ("freelist_blocks", "kernel", "freelist_blocks", True),
    ("freelist_count", "kernel", "freelist_count", True),
    ("slab_caches", "kernel", "slab_caches", True),
    ("slab_cache", "kernel", "slab_cache", True),
    ("slab_object", "kernel", "slab_object", True),
    ("dmabufs", "kernel", "dmabufs", True),
    # --- slub -----------------------------------------------------------
    ("page_bytes", "slub", "page_bytes", True),
    ("head_to_page", "slub", "head_to_page", True),
    ("compound_head", "slub", "compound_head", True),
    ("cache_name", "slub", "cache_name", True),
    ("cpu_slab_ptr", "slub", "cpu_slab_ptr", True),
    ("cpu_active_slab", "slub", "cpu_active_slab", True),
    ("cpu_freelist", "slub", "cpu_freelist", True),
    ("freeptr_offset", "slub", "freeptr_offset", True),
    ("freeptr_random", "slub", "freeptr_random", True),
    ("decode_freeptr", "slub", "decode_freeptr", True),
    ("freelist_dist", "slub", "freelist_dist", True),
    ("partial_info", "slub", "partial_info", True),
    ("in_partial", "slub", "in_partial", True),
    ("slab_counters", "slub", "slab_counters", True),
    ("slab_state", "slub", "slab_state", True),
    ("object_index", "slub", "object_index", True),
    ("neighbour_objects", "slub", "neighbour_objects", True),
    ("print_slab", "slub", "print_slab", True),
)

#: Flat names bound onto the facade, in table order.
BOUND_NAMES: tuple[str, ...] = tuple(name for name, _, _, _ in _BINDINGS)

#: Bound names that ``api.py`` also exposes as bare free functions.
FREE_FUNCTION_NAMES: tuple[str, ...] = tuple(
    name for name, _, _, free in _BINDINGS if free
)


@final
class KernelDebugger:
    """Facade composing the toolkit components.

    Tracer code calls the bound methods directly (``kdbg.info``,
    ``kdbg.style``, ``kdbg.print_slab``, ...).  Component accessors
    (``kdbg.logger`` / ``kdbg.styler`` / ``kdbg.reader`` /
    ``kdbg.symbols`` / ``kdbg.kaslr`` / ``kdbg.kbase`` / ``kdbg.cpu`` /
    ``kdbg.walker`` / ``kdbg.kernel`` / ``kdbg.slub``) are available for
    callers that need narrower access.
    """

    def __init__(self) -> None:
        self.config: DebugConfig = DebugConfig()
        self.logger: Logger = Logger()
        self.styler: KernelStyler = KernelStyler()
        self.reader: MemoryReader = MemoryReader(self.config)
        self.symbols: SymbolResolver = SymbolResolver(
            self.config, self.styler, self.logger
        )
        self.kaslr: Kaslr = Kaslr(self.config, self.reader)
        self.kbase: Kbase = Kbase(self.config, self.reader)
        self.cpu: CpuInfo = CpuInfo(self.reader)
        self.walker: PageTableWalker = PageTableWalker(self.reader)
        self.kernel: KernelInspector = KernelInspector(self.reader)
        self.slub: SlubInspector = SlubInspector(
            self.config, self.reader, self.styler, self.logger, self.cpu
        )

        # Make the reader follow KASLR on its own: when the slide is unset
        # (or a read fails at it) the reader re-derives it from the live
        # IDT and drops the inspector's address-derived caches.
        self.reader.set_kaslr_hooks(
            self._detect_kaslr, self.kernel.reset,
        )

        # Republish every component method declared in ``_BINDINGS``.
        #
        # Plain assignments rather than a ``setattr`` loop: a type checker
        # can follow ``self.info = self.logger.info`` and give ``kdbg.info``
        # the component method's real signature, while ``setattr`` leaves
        # the whole flat surface invisible and turns every ``kdbg.<name>``
        # into an attribute error.  ``_BINDINGS`` above stays the source of
        # truth for ``api.py``; ``test_facade_bindings`` compares this block
        # against it so the two cannot drift.
        #
        # ``Final`` is what turns each of these into a *declared* type for
        # ``pyright --verifytypes``: an unannotated ``self.x = ...`` is
        # reported as "could be inferred differently by type checkers",
        # which is 140 of the 173 symbols that kept the package's
        # completeness score at 0.88.  It also keeps the inferred signature
        # (parameter names and defaults included), so nothing is restated
        # by hand and nothing can drift from the component; reassigning a
        # bound name after construction becomes a type error, which is the
        # intended contract.
        self.debug: Final = self.logger.debug
        self.info: Final = self.logger.info
        self.success: Final = self.logger.success
        self.warn: Final = self.logger.warn
        self.error: Final = self.logger.error
        self.once: Final = self.logger.once
        self.throttle: Final = self.logger.throttle
        self.counter: Final = self.logger.counter
        self.summary: Final = self.logger.summary
        self.check: Final = self.logger.check
        self.assert_: Final = self.logger.assert_
        self.banner: Final = self.logger.banner
        self.rule: Final = self.logger.rule
        self.fmt_line: Final = self.logger.fmt_line
        self.style: Final = self.styler.style
        self.addr: Final = self.styler.addr
        self.hex: Final = self.styler.hex
        self.hex8: Final = self.styler.hex8
        self.hex16: Final = self.styler.hex16
        self.hex32: Final = self.styler.hex32
        self.hex64: Final = self.styler.hex64
        self.dec: Final = self.styler.dec
        self.size: Final = self.styler.size
        self.pfn: Final = self.styler.pfn
        self.percent: Final = self.styler.percent
        self.bits: Final = self.styler.bits
        self.ljust: Final = self.styler.ljust
        self.rjust: Final = self.styler.rjust
        self.center: Final = self.styler.center
        self.pad: Final = self.styler.pad
        self.truncate: Final = self.styler.truncate
        self.kv: Final = self.styler.kv
        self.kv_int: Final = self.styler.kv_int
        self.kv_hex: Final = self.styler.kv_hex
        self.kv_bool: Final = self.styler.kv_bool
        self.seq: Final = self.styler.seq
        self.list: Final = self.styler.list
        self.tuple: Final = self.styler.tuple
        self.set: Final = self.styler.set
        self.dict: Final = self.styler.dict
        self.pairs: Final = self.styler.pairs
        self.range: Final = self.styler.range
        self.named: Final = self.styler.named
        self.kv_seq: Final = self.styler.kv_seq
        self.table: Final = self.styler.table
        self.box: Final = self.styler.box
        self.fmt_chain: Final = self.styler.chain
        self.cols: Final = self.styler.cols
        self.block: Final = self.styler.block
        self.highlight: Final = self.styler.highlight
        self.indent: Final = self.styler.indent
        self.fields: Final = self.styler.fields
        self.kv_group: Final = self.styler.kv_group
        self.tick: Final = self.styler.tick
        self.cross: Final = self.styler.cross
        self.bullet: Final = self.styler.bullet
        self.arrow: Final = self.styler.arrow
        self.bar: Final = self.styler.bar
        self.fn: Final = self.styler.fn
        self.loc: Final = self.styler.loc
        self.depth_marker: Final = self.styler.depth_marker
        self.branch: Final = self.styler.branch
        self.fl_tag: Final = self.styler.fl_tag
        self.kv_cpu: Final = self.styler.kv_cpu
        self.kv_online: Final = self.styler.kv_online
        self.kv_err: Final = self.styler.kv_err
        self.kv_trans: Final = self.styler.kv_trans
        self.u64: Final = self.reader.u64
        self.read_kvar: Final = self.reader.read_kvar
        self.kvar_addr: Final = self.reader.kvar_addr
        self.arg: Final = self.reader.arg
        self.read_field: Final = self.reader.read_field
        self.sym: Final = self.symbols.sym
        self.line: Final = self.symbols.line
        self.backtrace: Final = self.symbols.backtrace
        self.chain: Final = self.symbols.chain
        self.color_chain: Final = self.symbols.color_chain
        self.bp_spec: Final = self.kaslr.bp_spec
        self.link_text: Final = self.kaslr.link_text
        self.find_kbase: Final = self.kbase.find
        self.nr_cpus: Final = self.cpu.nr_cpus
        self.nr_nodes: Final = self.cpu.nr_nodes
        self.cpu_online: Final = self.cpu.cpu_online
        self.cur_cpu: Final = self.cpu.cur_cpu
        self.percpu_off: Final = self.cpu.percpu_off
        self.walk: Final = self.walker.walk
        self.kversion: Final = self.kernel.version
        self.krelease: Final = self.kernel.release
        self.kcmdline: Final = self.kernel.cmdline
        self.kconfig: Final = self.kernel.kconfig
        self.kconfig_get: Final = self.kernel.config_get
        self.kconfig_contains: Final = self.kernel.config_contains
        self.kconfig_update: Final = self.kernel.config_update
        self.config_key: Final = self.kernel.config_key
        self.modules: Final = self.kernel.modules
        self.syscalls: Final = self.kernel.syscalls
        self.syscall_count: Final = self.kernel.syscall_count
        self.page_type: Final = self.kernel.page_type
        self.page_refcount: Final = self.kernel.page_refcount
        self.buddy_order: Final = self.kernel.buddy_order
        self.page_is_buddy: Final = self.kernel.page_is_buddy
        self.page_is_slab: Final = self.kernel.page_is_slab
        self.kallsyms: Final = self.kernel.kallsyms
        self.lookup: Final = self.kernel.lookup
        self.dmesg: Final = self.kernel.dmesg
        self.tk_epoch: Final = self.kernel.tk_epoch
        self.bpf_progs: Final = self.kernel.bpf_progs
        self.bpf_maps: Final = self.kernel.bpf_maps
        self.bpf_map_value: Final = self.kernel.bpf_map_value
        self.buddy_zones: Final = self.kernel.buddy_zones
        self.zone_spans: Final = self.kernel.zone_spans
        self.zone_of_pfn: Final = self.kernel.zone_of_pfn
        self.block_of_pfn: Final = self.kernel.block_of_pfn
        self.block_range: Final = self.kernel.block_range
        self.buddy_pfn: Final = self.kernel.buddy_pfn
        self.free_area_counts: Final = self.kernel.free_area_counts
        self.freelist_blocks: Final = self.kernel.freelist_blocks
        self.freelist_count: Final = self.kernel.freelist_count
        self.slab_caches: Final = self.kernel.slab_caches
        self.slab_cache: Final = self.kernel.slab_cache
        self.slab_object: Final = self.kernel.slab_object
        self.dmabufs: Final = self.kernel.dmabufs
        self.page_bytes: Final = self.slub.page_bytes
        self.head_to_page: Final = self.slub.head_to_page
        self.compound_head: Final = self.slub.compound_head
        self.cache_name: Final = self.slub.cache_name
        self.cpu_slab_ptr: Final = self.slub.cpu_slab_ptr
        self.cpu_active_slab: Final = self.slub.cpu_active_slab
        self.cpu_freelist: Final = self.slub.cpu_freelist
        self.freeptr_offset: Final = self.slub.freeptr_offset
        self.freeptr_random: Final = self.slub.freeptr_random
        self.decode_freeptr: Final = self.slub.decode_freeptr
        self.freelist_dist: Final = self.slub.freelist_dist
        self.partial_info: Final = self.slub.partial_info
        self.in_partial: Final = self.slub.in_partial
        self.slab_counters: Final = self.slub.slab_counters
        self.slab_state: Final = self.slub.slab_state
        self.object_index: Final = self.slub.object_index
        self.neighbour_objects: Final = self.slub.neighbour_objects
        self.print_slab: Final = self.slub.print_slab

    # --- KASLR adaptation ------------------------------------------------

    def _detect_kaslr(self) -> int | None:
        """IDT-based slide detection used by the reader's self-healing.

        Returns ``None`` when no base can be recovered, so the reader
        leaves the current slide untouched.
        """
        result: KbaseResult | None = self.kbase.find()
        if result is None:
            return None
        return self._result_offset(result)

    def _result_offset(self, result: KbaseResult) -> int | None:
        """Return the KASLR slide implied by a base-recovery result."""
        offset = result.kaslr_offset
        if offset is not None:
            return offset
        reference = result.link_text
        if reference is None:
            reference = self.kaslr.link_text()
        if reference is None:
            return None
        return (result.base - reference) & 0xFFFFFFFFFFFFFFFF

    def kaslr_slide(self) -> int:
        """Return the slide in effect, deriving it from the live kernel.

        ``kdbg.kaslr_offset`` is a plain attribute that stays ``0`` until
        a command sets it, while the reader follows KASLR on its own for
        every read.  Diagnostic commands (``kl-status``) want the value
        the reader is actually using, so this asks the reader to derive
        it (once, cached) instead of reporting a stale zero.
        """
        return self.reader.ensure_kaslr()

    # --- color control (facade level) -----------------------------------

    @property
    def color_enabled(self) -> bool:
        """Both logger and styler colors on."""
        return self.logger.color_enabled and self.styler.color_enabled

    @color_enabled.setter
    def color_enabled(self, value: bool) -> None:
        self.logger.set_color_enabled(value)
        self.styler.set_color_enabled(value)
        message.set_color_enabled(value)

    def set_color_enabled(self, enabled: bool) -> None:
        """Set both logger and styler color states."""
        self.logger.set_color_enabled(enabled)
        self.styler.set_color_enabled(enabled)
        message.set_color_enabled(enabled)

    def enable_color(self) -> None:
        """Turn color on for both logger and styler."""
        self.logger.enable_color()
        self.styler.enable_color()
        message.set_color_enabled(True)

    def disable_color(self) -> None:
        """Turn color off for both logger and styler."""
        self.logger.disable_color()
        self.styler.disable_color()
        message.set_color_enabled(False)

    # --- config passthrough ---------------------------------------------

    @property
    def kaslr_offset(self) -> int:
        """The KASLR slide added to symbol addresses."""
        return self.config.kaslr_offset

    @kaslr_offset.setter
    def kaslr_offset(self, value: int) -> None:
        self.config.kaslr_offset = value

    @property
    def header_width(self) -> int:
        """The event-tag column width in characters."""
        return self.config.header_width

    @property
    def indent_str(self) -> str:
        """The base indentation string used by event detail lines.

        ``KernelDebugger.indent`` is the inherited Styler method, so the
        configuration value is exposed under this distinct name.
        """
        return self.config.indent

    @property
    def indent_nested(self) -> str:
        """The nested indentation string used by slab/bt blocks."""
        return self.config.indent_nested


# =========================================================================
# Module-level singleton shared with the tracer
# =========================================================================

kdbg: KernelDebugger = KernelDebugger()


__all__ = [
    "BOUND_NAMES",
    "COMPONENT_NAMES",
    "FREE_FUNCTION_NAMES",
    "KernelDebugger",
    "kdbg",
]