"""Frozen external contract for the KernLens public surfaces.

These constants pin the *observable* surfaces — the GDB command names,
the facade's bound methods, and the free functions installed into a
sourced script's namespace — so the internal package layout
(``gdb/kernel.py``, ``gdbinit.py``) can be restructured without changing
behaviour the user or their scripts can see.

They describe "the classic KernLens API is still present", never "the
file lives at path X".  Both ``tests/unit`` and ``tests/integration``
import this module (``tests/conftest.py`` puts ``tests/`` on
``sys.path``).
"""

from __future__ import annotations

#: Every canonical GDB command, in sorted order.  Each one also has a
#: ``kl-<verb>`` alias, which ``test_gdbinit`` verifies.
CANONICAL_COMMANDS: tuple[str, ...] = (
    "kernlens-addr",
    "kernlens-base",
    "kernlens-bits",
    "kernlens-bt",
    "kernlens-buddydump",
    "kernlens-chain",
    "kernlens-color",
    "kernlens-cpu",
    "kernlens-help",
    "kernlens-int",
    "kernlens-kaslr",
    "kernlens-kaslr-offset",
    "kernlens-kbase",
    "kernlens-kbpf",
    "kernlens-kchecksec",
    "kernlens-kcmdline",
    "kernlens-kconfig",
    "kernlens-kdmabuf",
    "kernlens-kdmesg",
    "kernlens-klookup",
    "kernlens-kmod",
    "kernlens-ksyscalls",
    "kernlens-kvar",
    "kernlens-kversion",
    "kernlens-msr",
    "kernlens-p2v",
    "kernlens-page",
    "kernlens-pageinfo",
    "kernlens-pagewalk",
    "kernlens-percpu",
    "kernlens-pt",
    "kernlens-pte",
    "kernlens-read",
    "kernlens-read-field",
    "kernlens-slab",
    "kernlens-status",
    "kernlens-sym",
    "kernlens-v2p",
    "kernlens-walk",
)

#: Methods/traits bound directly onto the ``kdbg`` facade.  Tracer
#: scripts and the command layer call these; the refactor must keep the
#: names (the *implementation* is free to move between components).
FACADE_BOUND_NAMES: tuple[str, ...] = (
    "addr", "arg", "arrow", "assert_", "backtrace", "banner", "bar",
    "bits", "block", "box", "bp_spec", "bpf_map_value", "bpf_maps",
    "bpf_progs", "branch", "buddy_zones", "bullet", "cache_name",
    "center", "chain", "check", "color_chain", "cols", "compound_head",
    "config_key", "counter", "cpu_active_slab", "cpu_freelist",
    "cpu_online", "cpu_slab_ptr", "cross", "cur_cpu", "debug", "dec",
    "decode_freeptr", "depth_marker", "dict", "dmabufs", "dmesg", "error",
    "fields", "find_kbase", "fl_tag", "fmt_chain", "fmt_line", "fn",
    "freelist_dist", "freeptr_offset", "freeptr_random", "head_to_page",
    "hex", "hex16", "hex32", "hex64", "hex8", "highlight", "in_partial",
    "indent", "info", "kallsyms", "kcmdline", "kconfig",
    "kconfig_contains", "kconfig_get", "kconfig_update", "krelease", "kv",
    "kv_bool", "kv_cpu", "kv_err", "kv_group", "kv_hex", "kv_int",
    "kv_online", "kv_seq", "kv_trans", "kvar_addr", "kversion", "line",
    "link_text", "list", "ljust", "loc", "lookup", "modules", "named",
    "nr_cpus", "nr_nodes", "once", "pad", "page_bytes", "page_refcount",
    "page_type", "pairs", "partial_info", "percent", "percpu_off", "pfn",
    "print_slab", "range", "read_field", "read_kvar", "rjust", "rule",
    "seq", "set", "size", "slab_cache", "slab_caches", "slab_object",
    "style", "success", "summary", "sym", "syscall_count", "syscalls",
    "table", "throttle", "tick", "tk_epoch", "truncate", "tuple", "u64",
    "walk", "warn",
)

#: Free functions/names installed into a sourced script's namespace by
#: ``install_public_api`` beyond the facade bindings and core statics.
PUBLIC_API_EXTRA: tuple[str, ...] = (
    "KAddr",
    "KERNLENS_API",
    "KERNLENS_CLASSES",
    "KERNLENS_INSTANCES",
    "KERNLENS_PREFIXED",
    "KERNLENS_QUALIFIED",
    "KPageTable",
    "KernelDebugger",
    "IntCodec",
    "IntFmt",
    "BitOps",
    "byte_swap64",
    "kdbg",
    "pack_u16",
    "popcount",
    "split_4",
    "virt_to_phys",
)

#: Component instances exposed as ``KERNLENS_INSTANCES`` / attributes.
COMPONENT_INSTANCE_NAMES: tuple[str, ...] = (
    "config",
    "cpu",
    "kbase",
    "kernel",
    "logger",
    "reader",
    "styler",
    "symbols",
    "walker",
)

__all__ = [
    "CANONICAL_COMMANDS",
    "COMPONENT_INSTANCE_NAMES",
    "FACADE_BOUND_NAMES",
    "PUBLIC_API_EXTRA",
]