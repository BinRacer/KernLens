#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Memory and symbol commands in the pwndbg style.

``kernlens-slab`` / ``slabs`` / ``sym`` / ``bt`` / ``chain`` / ``read`` /
``kvar`` / ``read-field`` / ``kbpf`` / ``buddydump`` / ``kdmabuf``.
"""

from __future__ import annotations

import argparse

import gdb  # type: ignore[import-not-found]

from .. import IntFmt
from ..gdb.facade import kdbg
from ..output import message
from ..output.tree import IndentContextManager
from .framework import Command, CommandCategory, hide, parse_int_arg
from .misc import cpu_limitcheck

_MASK64 = 0xFFFFFFFFFFFFFFFF

#: pg_free_list / dma-buf result caps, matching pwndbg.
MAX_PG_FREE_LIST_STR_RESULT_CNT = 0x10
MAX_SG_RESULT_CNT = 0x10


# =========================================================================
# slab (pwndbg's `slab list|info|contains`, plus the legacy address form)
# =========================================================================

_slab_parser = argparse.ArgumentParser(
    description=(
        "Prints information about the linux kernel's slab allocator SLUB."
    )
)
# One token list drives both the pwndbg subcommands and the legacy
# bare-address form; a single `nargs="*"` positional avoids argparse
# stealing the subcommand name into a separate address positional.
_slab_parser.add_argument(
    "args", nargs="*", metavar="command",
    help=(
        "list [filter] | info <name>... | contains <addr>... "
        "| details <addr>... | <addr>"
    ),
)
_slab_parser.add_argument(
    "-v", "--verbose", action="store_true",
    help="display more detailed information (with `info`)",
)
_slab_parser.add_argument(
    "-c", "--cpu", type=int, help="CPU to display",
)
_slab_parser.add_argument(
    "-n", "--node", type=int, help="",
)
_slab_parser.add_argument(
    "-p", "--partial", action="store_true", help="displays partial lists",
)
_slab_parser.add_argument(
    "-a", "--active", action="store_true", help="displays the active list",
)
# Legacy flag for the bare-address form (kept, hidden from --help).
hide(_slab_parser.add_argument(
    "-d", "--detail", action="store_true", dest="detail",
))

_SLAB_SUBCOMMANDS = ("list", "info", "contains", "details", "detail")


@Command(
    _slab_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-slab", "kl-slabs"],
    examples=(
        "kl-slab list\n"
        "kl-slab list kmalloc\n"
        "kl-slab info kmalloc-1k -v\n"
        "kl-slab contains 0xffff8880032a1c40\n"
        "kl-slab details 0xffff8880032a1c40 -c 0\n"
        "kl-slab 0xffff8880032a1c40            # legacy bare-address form"
    ),
)
def kernlens_slab(
    args: list[str] | None = None,
    verbose: bool = False,
    cpu: int | None = None,
    node: int | None = None,
    partial: bool = False,
    active: bool = False,
    detail: bool = False,
) -> None:
    tokens = list(args or [])
    if tokens and tokens[0] in _SLAB_SUBCOMMANDS:
        _slab_dispatch(
            tokens[0], tokens[1:], verbose, cpu, node, partial, active,
        )
        return
    # Legacy form: the first token is an object/slab address.
    if not tokens:
        _slab_parser.print_usage()
        return
    address = parse_int_arg(tokens[0])
    if detail or cpu is not None:
        _slab_detail(address, cpu)
        return
    kdbg.print_slab(address)


def _slab_dispatch(
    command: str,
    tokens: list[str],
    verbose: bool,
    cpu: int | None,
    node: int | None,
    partial: bool,
    active: bool,
) -> None:
    """Run a pwndbg-parity ``slab`` subcommand from raw tokens."""
    if command == "list":
        _slabs_list_cmd(tokens[0] if tokens else None)
        return
    if command == "info":
        if not tokens:
            _slab_parser.print_usage()
            return
        # pwndbg displays both partial and active lists unless the user
        # explicitly narrowed the request.
        if not partial and not active:
            partial = active = True
        for name in tokens:
            _slabs_info_cmd(name, verbose, cpu, node, partial, active)
        return
    if command == "contains":
        if not tokens:
            _slab_parser.print_usage()
            return
        for token in tokens:
            _slabs_contains_cmd(parse_int_arg(token))
        return
    if command in ("details", "detail"):
        # kernlens extra: the granular SLUB inspector for one address.
        if not tokens:
            _slab_parser.print_usage()
            return
        for token in tokens:
            _slab_detail(parse_int_arg(token), cpu)


def _slab_detail(head: int, focus_cpu: int | None) -> None:
    """Print the granular SLUB inspector output (``--detail``)."""
    page = kdbg.head_to_page(head)
    if page is None:
        print(message.error(f"cannot translate {head:#x} to a struct page"))
        return
    page = kdbg.compound_head(page)
    cache = kdbg.read_field(page, "struct slab", "slab_cache")
    if not cache:
        print(message.error(f"{page:#x} is not a slab page"))
        return
    indent = IndentContextManager()
    indent.print(
        indent.prefix("Slab") + " @ " + indent.addr_hex(head)
        + " page: " + indent.aux_hex(page)
    )
    with indent:
        indent.print(
            indent.prefix("cache") + ": " + indent.addr_hex(cache)
            + " " + message.notice(kdbg.cache_name(cache))
            + f"  page_bytes={kdbg.page_bytes()}"
        )
        offset = kdbg.freeptr_offset(cache)
        random = kdbg.freeptr_random(cache)
        indent.print(
            indent.prefix("freeptr") + ": offset="
            + (str(offset) if offset is not None else message.warn("?"))
            + " random="
            + (indent.aux_hex(random) if random is not None else message.warn("?"))
        )
        slab_freelist = kdbg.read_field(page, "struct slab", "freelist")
        indent.print(
            indent.prefix("freelist") + ": "
            + (indent.addr_hex(slab_freelist) if slab_freelist else message.on("NULL"))
        )
        if slab_freelist and offset is not None:
            raw = _safe_read_u64(slab_freelist + offset)
            if raw is not None:
                nxt = kdbg.decode_freeptr(raw, random, slab_freelist + offset)
                indent.print(
                    indent.prefix("next") + ": " + indent.aux_hex(raw)
                    + " decoded=" + indent.addr_hex(nxt)
                )
        nr_cpus = kdbg.nr_cpus()
        if focus_cpu is not None:
            cpu_iter = [focus_cpu]
        elif nr_cpus > 0:
            cpu_iter = list(range(min(nr_cpus, 8)))
        else:
            cpu_iter = []
        for cpu in cpu_iter:
            active = kdbg.cpu_active_slab(cache, cpu)
            freelist = kdbg.cpu_freelist(cache, cpu)
            indent.print(
                indent.prefix(f"cpu {cpu}") + ": active="
                + (indent.addr_hex(active) if active else message.on("NULL"))
                + " freelist="
                + (indent.addr_hex(freelist) if freelist else message.on("NULL"))
            )
        nr_nodes = kdbg.nr_nodes()
        for node in range(nr_nodes) if nr_nodes > 0 else []:
            count, _node_ptr, head_slab, _head_fl = kdbg.partial_info(cache, node)
            membership = kdbg.in_partial(cache, page, node)
            indent.print(
                indent.prefix(f"node {node}")
                + f": partial={count} head="
                + (
                    indent.addr_hex(head_slab)
                    if head_slab
                    else message.warn("?")
                )
                + " in_partial="
                + (
                    message.on("True")
                    if membership is True
                    else message.off("False")
                    if membership is False
                    else message.warn("?")
                )
            )


def _slabs_node_partial(
    indent: IndentContextManager,
    cache: object,
    node: int | None,
    verbose: bool,
) -> None:
    """Print the per-node ``kmem_cache_node`` partial slab lists (``-p``).

    pwndbg prints the node's partial slabs only when ``--partial`` is
    given; the count/head come from the same ``partial_info`` the
    granular inspector uses.
    """
    address = cache.address  # type: ignore[attr-defined]
    nr_nodes = kdbg.nr_nodes()
    nodes = [node] if node is not None else (
        list(range(nr_nodes)) if nr_nodes > 0 else []
    )
    for node_id in nodes:
        count, _node_ptr, head_slab, head_freelist = kdbg.partial_info(
            address, node_id,
        )
        indent.print(
            indent.prefix(f"node {node_id}")
            + f": nr_partial={count}"
        )
        if count <= 0:
            indent.print(indent.prefix("Partial Slabs") + ": (none)")
            continue
        indent.print(
            indent.prefix("head")
            + ": "
            + (indent.addr_hex(head_slab) if head_slab else message.warn("?"))
            + " freelist="
            + (
                indent.addr_hex(head_freelist)
                if head_freelist
                else message.on("NULL")
            )
        )
        if verbose and head_slab:
            _slab_detail(head_slab, None)


def _safe_read_u64(addr: int) -> int | None:
    """Read ``*(unsigned long *)addr``; ``None`` when unreadable."""
    try:
        return kdbg.u64(f"*(unsigned long *)({addr:#x})")
    except (gdb.error, gdb.MemoryError):
        return None


# =========================================================================
# slab helper commands (list / info / contains bodies)
# =========================================================================

def _slabs_list_cmd(name_filter: str | None) -> None:
    caches = kdbg.slab_caches()
    if not caches:
        print(message.error("no kmem_cache found (needs the slab_caches symbol)"))
        return
    rows = [
        [
            message.notice(cache.name),
            cache.oo_objects,
            cache.size,
            cache.object_size,
            cache.oo_order,
        ]
        for cache in caches
        if name_filter is None or name_filter in cache.name
    ]
    print(kdbg.table(("Name", "# Objects", "Size", "Obj Size", "order"), rows))
    print()
    print(f"{len(rows)} of {len(caches)} cache(s) shown")


def _slabs_info_cmd(
    name: str,
    verbose: bool,
    cpu: int | None = None,
    node: int | None = None,
    partial: bool = False,
    active: bool = False,
) -> None:
    cache = kdbg.slab_cache(name)
    if cache is None:
        print(message.error(f"Cache {name} not found"))
        return
    indent = IndentContextManager()
    indent.print(indent.prefix("Slab Cache") + " @ " + indent.addr_hex(cache.address))
    with indent:
        # The row order and labels below follow pwndbg's `slab info`, so
        # a user moving between the two tools reads the same block.
        # KernLens-only rows are appended after them.
        indent.print(indent.prefix("Name") + f": {message.notice(cache.name)}")
        flags = " | ".join(cache.flags) if cache.flags else "(none)"
        indent.print(indent.prefix("Flags") + f": {flags}")
        indent.print(indent.prefix("Offset") + ": " + indent.aux_hex(cache.offset))
        indent.print(
            indent.prefix("Slab size") + ": " + indent.aux_hex(cache.slab_size)
        )
        indent.print(
            indent.prefix("Size (including metadata)")
            + ": " + indent.aux_hex(cache.size)
        )
        indent.print(indent.prefix("Align") + ": " + indent.aux_hex(cache.align))
        indent.print(
            indent.prefix("Object Size") + ": " + indent.aux_hex(cache.object_size)
        )
        # pwndbg prints these only when the build carries the fields
        # (CONFIG_HARDENED_USERCOPY); so do we.
        if cache.useroffset is not None and cache.usersize is not None:
            indent.print(
                indent.prefix("Usercopy region offset")
                + f": {cache.useroffset}"
            )
            indent.print(
                indent.prefix("Usercopy region size") + f": {cache.usersize}"
            )
        # KernLens only: the raw packed order/objects word, which pwndbg
        # stopped displaying.
        indent.print(
            indent.prefix("oo_order") + f": {cache.oo_order}"
            + f"  oo_objects={cache.oo_objects}"
        )
        # pwndbg displays the per-CPU active cache for `info` by default
        # (it forces --partial/--active on), so the per-CPU walk runs
        # unless the user narrowed the request to one CPU/node.
        nr_cpus = kdbg.nr_cpus()
        if cpu is not None:
            cpu_iter = [cpu]
        elif nr_cpus > 0:
            cpu_iter = list(range(min(nr_cpus, 8)))
        else:
            cpu_iter = []
        # The inspector wants the cache *address*: passing the dataclass
        # would build `((struct kmem_cache *)<SlabCache>)` and every CPU
        # would silently read NULL.
        cache_addr = cache.address
        for cpu_id in cpu_iter:
            if active:
                active_slab = kdbg.cpu_active_slab(cache_addr, cpu_id)
                freelist = kdbg.cpu_freelist(cache_addr, cpu_id)
                indent.print(
                    indent.prefix(f"cpu {cpu_id}") + ": active="
                    + (
                        indent.addr_hex(active_slab)
                        if active_slab
                        else message.on("NULL")
                    )
                    + " freelist="
                    + (indent.addr_hex(freelist) if freelist else message.on("NULL"))
                )
        if partial:
            _slabs_node_partial(indent, cache, node, verbose)


def _slabs_contains_cmd(addr: int) -> None:
    found = kdbg.slab_object(addr)
    if found is None:
        print(message.error(f"{addr:#x} does not belong to a SLUB cache"))
        return
    obj, cache = found
    print(
        indent_addr(obj) + " @ " + message.notice(cache.name)
        + f"  size={cache.size} object_size={cache.object_size}"
    )


def indent_addr(value: int) -> str:
    """Paint a bare address (yellow), without a context manager."""
    return message.colorize(hex(value), "\x1b[33m")


# =========================================================================
# sym / bt / chain
# =========================================================================

_sym_parser = argparse.ArgumentParser(
    description="Resolves an address to a symbol and source location."
)
_sym_parser.add_argument("address", type=parse_int_arg, help="address to resolve")


@Command(
    _sym_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-sym"],
    examples="kl-sym $pc\nkl-sym 0xffffffff81000000",
)
def kernlens_sym(address: int) -> None:
    name = kdbg.sym(address)
    line = kdbg.line(address)
    print(
        indent_addr(address) + "  "
        + message.notice(kdbg.fn(name)) + " at " + kdbg.loc(line)
    )


def _valid_depth(depth: int) -> bool:
    """Report and reject a frame count outside 1-128.

    Shared by ``kl-bt`` and its ``--chain`` view so the limit is stated
    once instead of once per command.
    """
    if 1 <= depth <= 128:
        return True
    print(message.error("depth must be between 1 and 128"))
    return False


_bt_parser = argparse.ArgumentParser(
    description="Prints a formatted kernel backtrace."
)
_bt_parser.add_argument(
    "depth", nargs="?", type=int, default=8,
    help="maximum frames, 1-128 (default 8)",
)
_bt_parser.add_argument(
    "--chain", action="store_true",
    help="print the compact caller <- callee chain instead of the frames",
)


@Command(
    _bt_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-bt"],
    examples="kl-bt\nkl-bt 24\nkl-bt 24 --chain",
    notes=(
        "``--chain`` selects the ``kl-chain`` presentation, so the compact "
        "view is reachable from the backtrace command itself."
    ),
)
def kernlens_bt(depth: int = 8, chain: bool = False) -> None:
    if not _valid_depth(depth):
        return
    if chain:
        print(kdbg.color_chain(kdbg.chain(depth)))
        return
    try:
        frame = gdb.newest_frame()
    except (gdb.error, gdb.MemoryError):
        frame = None
    if frame is None:
        print(message.warn("no stack frames"))
        return
    kdbg.backtrace(depth)


_chain_parser = argparse.ArgumentParser(
    description="Prints a compact caller <- callee call chain."
)
_chain_parser.add_argument(
    "depth", nargs="?", type=int, default=8,
    help="maximum frames, 1-128 (default 8)",
)


@Command(
    _chain_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-chain"],
    examples="kl-chain\nkl-chain 12",
)
def kernlens_chain(depth: int = 8) -> None:
    if not _valid_depth(depth):
        return
    print(kdbg.color_chain(kdbg.chain(depth)))


# =========================================================================
# read / kvar / read-field
# =========================================================================

_read_parser = argparse.ArgumentParser(
    description="Dumps kernel memory as 64-bit words with symbol annotations."
)
_read_parser.add_argument("address", type=parse_int_arg, help="address to read")
_read_parser.add_argument(
    "count", nargs="?", type=int, default=8,
    help="number of 8-byte words, 1-64 (default 8)",
)
_read_parser.add_argument(
    "-m", "--mode", choices=["ascii"], default=None,
    help="dump raw bytes with an ASCII sidebar",
)


@Command(
    _read_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-read"],
    examples=(
        "kl-read 0xffff8880032a1c40\n"
        "kl-read $rsp 16\n"
        "kl-read 0xffff8880032a1c40 64 --mode ascii"
    ),
)
def kernlens_read(
    address: int, count: int = 8, mode: str | None = None,
) -> None:
    if not 1 <= count <= 64:
        print(message.error("count must be between 1 and 64"))
        return
    if mode == "ascii":
        _read_bytes(address, count)
        return
    for index in range(count):
        current = (address + index * 8) & _MASK64
        try:
            value = kdbg.u64(f"*(unsigned long *)({current:#x})")
        except (gdb.error, gdb.MemoryError):
            value = None
        if value is None:
            print(indent_addr(current) + ": " + message.error("<unreadable>"))
            break
        name = kdbg.sym(current)
        line = kdbg.line(current)
        print(
            indent_addr(current) + ": " + message.highlight(f"{value:#018x}")
            + f"  {kdbg.fn(name)} {kdbg.loc(line)}"
        )


def _read_bytes(address: int, count: int) -> None:
    """Dump *count* bytes as a hex/ASCII block (``--mode ascii``)."""
    data = bytearray()
    for index in range(count):
        current = (address + index) & _MASK64
        try:
            byte = kdbg.u64(f"*(unsigned char *)({current:#x})")
        except (gdb.error, gdb.MemoryError):
            byte = None
        if byte is None:
            break
        data.append(byte & 0xFF)
    if not data:
        print(message.error("<unreadable>"))
        return
    print(f"{len(data)} byte(s) at {indent_addr(address)}")
    for line in IntFmt.bytes_dump(bytes(data), base=address).splitlines():
        print(message.hint(line))


_kvar_parser = argparse.ArgumentParser(
    description="Reads a KASLR-aware kernel global variable."
)
_kvar_parser.add_argument(
    "symbol", help="kernel global name (e.g. jiffies), with optional leading &",
)


@Command(
    _kvar_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-kvar"],
    examples="kl-kvar jiffies\nkl-kvar &init_task",
)
def kernlens_kvar(symbol: str) -> None:
    symbol = symbol.lstrip("&")
    address = kdbg.kvar_addr(symbol)
    if address is None:
        print(
            message.error(
                f"cannot resolve {symbol!r}; load a matching vmlinux first"
            )
        )
        return
    value = kdbg.read_kvar(symbol)
    indent = IndentContextManager()
    indent.print(indent.prefix("symbol") + ": " + message.notice(symbol))
    indent.print(indent.prefix("address") + ": " + indent.addr_hex(address))
    indent.print(
        indent.prefix("value") + ": "
        + (
            indent.aux_hex(value)
            if value is not None
            else message.error("<unreadable>")
        )
    )


_read_field_parser = argparse.ArgumentParser(
    description="Reads a struct field (including nested paths) as an integer."
)
_read_field_parser.add_argument("address", type=parse_int_arg, help="struct instance")
_read_field_parser.add_argument("type", help="C type name (e.g. 'struct slab')")
_read_field_parser.add_argument("path", help="field path (e.g. freelist or node[0])")


@Command(
    _read_field_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-read-field"],
    examples="kl-read-field 0xffffea0000a1c000 'struct slab' slab_cache",
)
def kernlens_read_field(address: int, type: str, path: str) -> None:
    value = kdbg.read_field(address, type, path)
    indent = IndentContextManager()
    indent.print(
        indent.prefix("field") + ": "
        + message.hint(f"(({type} *){address:#x})->{path}")
    )
    indent.print(
        indent.prefix("value") + ": "
        + (
            indent.aux_hex(value)
            if value is not None
            else message.error("<unreadable>")
        )
    )


# =========================================================================
# kbpf
# =========================================================================

_kbpf_parser = argparse.ArgumentParser(
    description="Prints information about the linux kernel bpf progs and maps."
)
_kbpf_parser.add_argument(
    "-v", "--verbose", action="count", default=0,
    dest="verbose", help="Increase the verbosity.",
)
_kbpf_parser.add_argument(
    "-b", "--break", dest="nth", type=int, default=None,
    help="Break at the start of the nth JIT compiled ebpf prog.",
)
_kbpf_parser.add_argument(
    "-p", "--progs", dest="progs", action="store_true", default=False,
    help="Print progs",
)
_kbpf_parser.add_argument(
    "-m", "--maps", dest="maps", action="store_true", default=False,
    help="Print maps",
)
# KernLens extra: dump array-map element values.
_kbpf_parser.add_argument(
    "--values", action="store_true", help="dump array-map element values",
)


@Command(
    _kbpf_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-kbpf"],
    examples=(
        "kl-kbpf\nkl-kbpf -p -v\nkl-kbpf -m --values\nkl-kbpf -b 0"
    ),
)
def kernlens_kbpf(
    verbose: int = 0,
    nth: int | None = None,
    progs: bool = False,
    maps: bool = False,
    values: bool = False,
) -> None:
    if nth is not None:
        progs = True
    if not progs and not maps:
        progs = maps = True
    if progs:
        _kbpf_progs(bool(verbose), nth)
    if maps:
        _kbpf_maps(bool(verbose), values)


def _kbpf_break(prog: object) -> None:
    """Break at the nth JIT-compiled prog's ``bpf_func`` (pwndbg ``-b``)."""
    target = prog.func  # type: ignore[attr-defined]
    index = prog.index  # type: ignore[attr-defined]
    if not target:
        print(message.error(f"prog {index} has no compiled function"))
        return
    try:
        gdb.execute(f"break *{target:#x}")
    except (gdb.error, gdb.MemoryError) as exc:
        print(message.error(f"cannot break at {target:#x}: {exc}"))
        return
    print(
        message.success(f"breakpoint set at prog {index} @ {target:#x}")
    )


def _kbpf_progs(verbose: bool, nth: int | None = None) -> None:
    progs = kdbg.bpf_progs()
    indent = IndentContextManager()
    indent.print(indent.prefix("bpf progs") + f": {len(progs)}")
    for prog in progs:
        if nth is not None and prog.index != nth:
            continue
        indent.print(
            "- " + indent.prefix(f"[0x{prog.index:02x}]")
            + " @ " + indent.addr_hex(prog.address)
            + " type=" + message.notice(prog.type)
            + " attach=" + message.notice(prog.attach_type)
        )
        with indent:
            indent.print(
                indent.prefix("func") + ": " + indent.aux_hex(prog.func)
                + f"  jited_len={prog.jited_len} insns={prog.insn_count}"
                + " aux=" + indent.aux_hex(prog.aux)
            )
            if verbose and prog.insns:
                raw = " ".join(f"{byte:02x}" for byte in prog.insns)
                indent.print(indent.prefix("bytecode") + ": " + message.hint(raw))
        if nth is not None:
            _kbpf_break(prog)


def _kbpf_maps(verbose: bool, values: bool) -> None:
    del verbose
    maps = kdbg.bpf_maps()
    indent = IndentContextManager()
    indent.print(indent.prefix("bpf maps") + f": {len(maps)}")
    for bpf_map in maps:
        indent.print(
            "- " + indent.prefix(f"[0x{bpf_map.index:02x}]")
            + " @ " + indent.addr_hex(bpf_map.address)
            + " type=" + message.notice(bpf_map.type)
        )
        with indent:
            array = (
                indent.aux_hex(bpf_map.array_addr)
                if bpf_map.array_addr is not None
                else message.warn("?")
            )
            indent.print(
                indent.prefix("array") + ": " + array
                + f"  key_size={bpf_map.key_size}"
                + f" value_size={bpf_map.value_size}"
                + f" max_entries={bpf_map.max_entries}"
            )
            if values and bpf_map.array_addr is not None and bpf_map.max_entries > 0:
                _kbpf_values(indent, bpf_map)


def _kbpf_values(indent: IndentContextManager, bpf_map: object) -> None:
    stride = ((bpf_map.value_size + 7) // 8) * 8  # type: ignore[attr-defined]
    if stride <= 0:
        return
    limit = min(bpf_map.max_entries, 0x10)  # type: ignore[attr-defined]
    for index in range(limit):
        raw = kdbg.bpf_map_value(
            bpf_map.array_addr + index * stride,  # type: ignore[attr-defined]
            bpf_map.value_size,  # type: ignore[attr-defined]
        )
        if raw is None:
            break
        shown = " ".join(f"{byte:02x}" for byte in raw)
        suffix = (
            " " + message.warn("...")
            if len(raw) < bpf_map.value_size  # type: ignore[attr-defined]
            else ""
        )
        indent.print(
            indent.prefix(f"[0x{index:02x}]") + ": " + message.hint(shown) + suffix
        )


# =========================================================================
# buddydump
# =========================================================================

_buddy_parser = argparse.ArgumentParser(
    description="Displays metadata and freelists of the buddy allocator."
)
_buddy_parser.add_argument(
    "-z", "--zone", type=str, dest="zone", default=None,
    help="Displays/searches lists only in the specified zone.",
)
_buddy_parser.add_argument(
    "-o", "--order", type=int, dest="order", default=None,
    help="Displays/searches lists only with the specified order.",
)
_buddy_parser.add_argument(
    "-m", "--mtype", type=str, dest="mtype", default=None,
    help="Displays/searches lists only with the specified mtype.",
)
_buddy_parser.add_argument(
    "-p", "--pcp-only", action="store_true", dest="pcp_only",
    default=False, help="Displays/searches only PCP lists.",
)
_buddy_parser.add_argument(
    "-c", "--cpu", type=cpu_limitcheck, dest="cpu", default=None,
    help="CPU nr for searching PCP.",
)
_buddy_parser.add_argument(
    "-n", "--node", type=int, dest="node", default=None,
)
_buddy_parser.add_argument(
    "-f", "--find", type=parse_int_arg, dest="find", default=None,
    help="The address to find in page free lists.",
)
_buddy_parser.add_argument(
    "--MIGRATE_TYPES", type=int, default=3,
    help="Use the specified MIGRATE_TYPES value",
)


@Command(
    _buddy_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-buddydump"],
    examples="kl-buddydump\nkl-buddydump -z Normal -o 0",
)
def kernlens_buddydump(
    zone: str | None = None,
    order: int | None = None,
    mtype: str | None = None,
    pcp_only: bool = False,
    cpu: int | None = None,
    node: int | None = None,
    find: int | None = None,
    MIGRATE_TYPES: int = 3,  # noqa: N803 - pwndbg's option name
) -> None:
    del MIGRATE_TYPES
    if pcp_only or cpu is not None:
        print(
            message.warn(
                "PCP (per-CPU page) lists are not modelled; showing the "
                "buddy free lists instead"
            )
        )
    pages = kdbg.buddy_zones(zone=zone, order=order, mtype=mtype, node=node)
    if find is not None:
        pages = tuple(p for p in pages if find in (p.phys, p.virt, p.page))
    if not pages:
        print(
            message.warn(
                "no free pages matched (needs node_data and a readable "
                "vmemmap; refine --zone/--order/--mtype/--node)"
            )
        )
        return
    indent = IndentContextManager()
    indent.print(
        indent.prefix("zone") + f": {zone or 'all'} order={order} "
        f"mtype={mtype or 'all'}"
    )
    shown = pages[:MAX_PG_FREE_LIST_STR_RESULT_CNT]
    with indent:
        for page in shown:
            indent.print(
                "- " + indent.prefix(f"[0x{page.index:02x}]")
                + " " + indent.addr_hex(page.virt)
                + " [page: " + indent.aux_hex(page.page)
                + ", phys: " + indent.aux_hex(page.phys) + "]"
            )
    if len(pages) > len(shown):
        indent.print(
            message.warn(
                f"... (truncated, {len(pages)} page(s) total)"
            )
        )
    print(f"{len(pages)} free page(s)")


# =========================================================================
# kdmabuf
# =========================================================================

_kdmabuf_parser = argparse.ArgumentParser(description="Prints DMA buf info.")


@Command(
    _kdmabuf_parser,
    category=CommandCategory.MEMORY,
    aliases=["kl-kdmabuf"],
    examples="kl-kdmabuf",
)
def kernlens_kdmabuf() -> None:
    buffers = kdbg.dmabufs()
    if not buffers:
        print(
            message.warn(
                "no dma-bufs found (needs the db_list/debugfs_list symbol "
                "and at least one exported buffer)"
            )
        )
        return
    indent = IndentContextManager()
    for buf in buffers:
        desc = (
            "- " + indent.prefix(f"[0x{buf.index:02x}] DMA-buf")
            + " @ " + indent.addr_hex(buf.address)
            + " [size: " + indent.aux_hex(buf.size)
            + ", file: " + indent.aux_hex(buf.file)
            + ", exporter: " + message.notice(buf.exporter or "?") + "]"
        )
        if buf.name:
            desc += " (name: " + message.notice(buf.name) + ")"
        indent.print(desc)
        if not buf.sg_entries:
            indent.print(message.warn("(no entries)"))
            continue
        with indent:
            indent.print(
                indent.prefix("system_heap_buffer")
                + " @ " + indent.addr_hex(buf.priv)
                + f" [nents: {indent.aux_hex(len(buf.sg_entries))}]"
            )
            for entry in buf.sg_entries[:MAX_SG_RESULT_CNT]:
                indent.print(
                    "- " + indent.prefix(f"[0x{entry.index:02x}]")
                    + " " + indent.addr_hex(entry.virt)
                    + " (len: " + indent.aux_hex(entry.length)
                    + ", off: " + indent.aux_hex(entry.offset) + ")"
                    + " [page: " + indent.aux_hex(entry.page)
                    + ", phys: " + indent.aux_hex(entry.phys) + "]"
                )


__all__ = [
    "kernlens_bt",
    "kernlens_buddydump",
    "kernlens_chain",
    "kernlens_kbpf",
    "kernlens_kdmabuf",
    "kernlens_kvar",
    "kernlens_read",
    "kernlens_read_field",
    "kernlens_slab",
    "kernlens_sym",
]