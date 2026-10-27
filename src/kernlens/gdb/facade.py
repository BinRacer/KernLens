#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Facade that composes the GDB adapter components.

:class:`KernelDebugger` owns one instance of each adapter and republishes
its methods under flat names (``kdbg.info``, ``kdbg.style``,
``kdbg.print_slab``).  The republication is driven by the single
:data:`_BINDINGS` table below, so the public surface is declared once and
``api.py`` derives the exported free functions from it instead of keeping
a second list in sync.
"""

from __future__ import annotations

from typing import final

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
        for name, component, member, _free in _BINDINGS:
            setattr(self, name, getattr(getattr(self, component), member))

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

    def find_kbase_adaptive(self) -> KbaseResult | None:
        """Recover the kernel base and keep the reader's slide in sync.

        Used by KASLR-aware callers that want the two to agree; it only
        touches the slide when the IDT reports a *different* one, so a
        plain ``kl-kbase`` diagnostic stays read-only.
        """
        result: KbaseResult | None = self.kbase.find()
        if result is None:
            return None
        offset = self._result_offset(result)
        if offset is not None and offset != self.config.kaslr_offset:
            self.config.kaslr_offset = offset
            self.kernel.reset()
        return result

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

kdbg = KernelDebugger()


__all__ = [
    "BOUND_NAMES",
    "COMPONENT_NAMES",
    "FREE_FUNCTION_NAMES",
    "KernelDebugger",
    "kdbg",
]