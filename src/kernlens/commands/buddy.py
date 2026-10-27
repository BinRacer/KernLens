#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""The buddy-allocator command: ``kl-buddy``.

Where ``kl-buddydump`` answers "which pages are free", this answers "what
is *this* address":

* ``kl-buddy list`` -- a per-zone/order/migratetype census of ``nr_free``;
* ``kl-buddy info <addr>`` -- the zone, the containing block, the position
  inside that block, and whether the page is free or allocated;
* ``kl-buddy freelist -o N`` -- the blocks on one free list, in the order
  the allocator would hand them out.

Every number comes from the running kernel.  The order is read from the
block head's ``private`` (which the kernel only sets while the block is
free), never assumed from the address.
"""

from __future__ import annotations

import argparse

from ..gdb.facade import kdbg
from ..gdb.inspectors import BlockLocation
from ..output import message
from ..output.tree import IndentContextManager
from .framework import Command, CommandCategory, parse_int_arg

_BUDDY_SUBCOMMANDS = ("list", "info", "freelist")

#: How many blocks ``freelist -v`` prints before truncating.
FREELIST_SHOW_LIMIT = 64


def _size_text(size_pages: int) -> str:
    """Render a page count as ``256 pages  1024 KiB  1 MiB``.

    ``order`` is always shown as a decimal ordinal elsewhere, so this is
    the only place a byte size appears; KiB comes first and MiB is
    appended once it is exact, which keeps the units ordered.
    """
    kib = size_pages * 4
    text = f"{size_pages} pages  {kib} KiB"
    if kib >= 1024 and kib % 1024 == 0:
        text += f"  {kib // 1024} MiB"
    return text


def _address_forms(address: int) -> list[tuple[str, int | None]]:
    """Return ``[(kind, value), ...]`` candidates for one input address.

    Mirrors :meth:`kernlens.gdb.slub.SlubInspector.head_to_page`: a
    direct-map address yields a *physical* address, a vmemmap address
    yields a *struct page*, and anything else is tried as a physical
    address.  The first two are already resolved here, so callers must
    use the returned value as-is -- re-applying the base would subtract
    it twice and produce a negative physical address.

    The bases are read with :meth:`read_kvar`, not with a bare symbol:
    ``page_offset_base`` and ``vmemmap_base`` are kernel *variables* the
    boot code picks, so under KASLR the symbol's link-time address holds
    nothing useful.
    """
    page_offset = kdbg.read_kvar("page_offset_base")
    vmemmap = kdbg.read_kvar("vmemmap_base")
    forms: list[tuple[str, int | None]] = []
    # The vmemmap range sits *above* page_offset_base, so a ``struct
    # page`` pointer also satisfies the direct-map test.  Try the
    # narrower interpretation first, or a page address would be
    # translated as a direct-map one and land on a bogus physical
    # address that still looks plausible.
    if vmemmap and address >= vmemmap:
        forms.append(("page", address))
    if page_offset and address >= page_offset:
        forms.append(("phys", address - page_offset))
    forms.append(("phys", address))
    return forms


def _resolve_one(spec: str) -> BlockLocation | None:
    """Resolve a user-supplied address to a :class:`BlockLocation`.

    ``spec`` is either a bare number (interpreted as virtual, then page,
    then physical) or ``pfn:<n>`` / ``phys:<n>`` / ``page:0x..`` to force
    one reading.
    """
    kind: str | None = None
    text = spec
    if ":" in spec:
        head, _, tail = spec.partition(":")
        if head in ("pfn", "phys", "page", "virt"):
            kind, text = head, tail
    value = parse_int_arg(text)
    spans = kdbg.zone_spans()
    if kind in ("pfn", "phys"):
        pfn = value if kind == "pfn" else value >> 12
        return kdbg.block_of_pfn(pfn, pfn << 12, spans=spans)
    if kind == "page":
        # ``value`` is the ``struct page`` address, not a pfn: reverse
        # the vmemmap mapping without re-deriving the base.
        page_bytes = kdbg.page_bytes()
        vmemmap = kdbg.read_kvar("vmemmap_base")
        if vmemmap is None:
            return None
        pfn = (value - vmemmap) // page_bytes
        return kdbg.block_of_pfn(pfn, pfn << 12, spans=spans)
    if kind == "virt":
        # ``value`` is a direct-map virtual address.
        page_offset = kdbg.read_kvar("page_offset_base")
        if page_offset is None:
            return None
        phys = value - page_offset
        return kdbg.block_of_pfn(phys >> 12, phys, spans=spans)
    for kind, value in _address_forms(value):
        if value is None:
            continue
        location = _resolve_one(f"{kind}:{value:#x}")
        if location is not None and _looks_like_memory(location):
            return location
    return None


def _looks_like_memory(location: BlockLocation) -> bool:
    """Whether a guess landed in memory any zone claims."""
    if location.managed:
        return True
    # An unmanaged reading is only plausible when the pfn is sane: a
    # negative pfn means a base was applied twice, and a physical
    # address above the direct map cannot be RAM.
    return 0 <= location.pfn < (1 << 40)


def _buddy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Locates an address in the buddy allocator: its zone, its "
            "free block, and where it sits inside that block."
        )
    )
    parser.add_argument(
        "command", nargs="*", metavar="command",
        help=(
            "list [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] | "
            "info <addr> | freelist -o ORDER [-m MTYPE] | <addr>"
        ),
    )
    parser.add_argument(
        "-z", "--zone", type=str, dest="zone", default=None,
        help="restrict to one zone (e.g. Normal).",
    )
    parser.add_argument(
        "-o", "--order", type=int, dest="order", default=None,
        help="restrict to one buddy order (decimal).",
    )
    parser.add_argument(
        "-m", "--mtype", type=str, dest="mtype", default=None,
        help="restrict to one migratetype (e.g. Movable).",
    )
    parser.add_argument(
        "-n", "--node", type=int, dest="node", default=None,
        help="restrict to one NUMA node.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="expand (freelist) or add detail (info).",
    )
    parser.add_argument(
        "--limit", type=int, dest="limit", default=FREELIST_SHOW_LIMIT,
        help=f"max blocks to expand with freelist -v (default {FREELIST_SHOW_LIMIT}).",
    )
    return parser


_buddy_parser_obj = _buddy_parser()


@Command(
    _buddy_parser_obj,
    category=CommandCategory.MEMORY,
    aliases=["kl-buddy"],
    examples=(
        "kl-buddy list -o 10\n"
        "kl-buddy info 0xffff8880032a1000\n"
        "kl-buddy info pfn:0x7400 -v\n"
        "kl-buddy freelist -o 10 -m Movable -v"
    ),
    notes=(
        "`inf`o` accepts a virtual address, a physical address, a "
        "`struct page` address, or a `pfn:`/`phys:`/`page:`/`virt:` "
        "prefixed value.  The order comes from the block head's "
        "`private` field, which the kernel only maintains while a block "
        "is free; an allocated page reports `Order: -`."
    ),
)
def kernlens_buddy(
    command: list[str] | None = None,
    zone: str | None = None,
    order: int | None = None,
    mtype: str | None = None,
    node: int | None = None,
    verbose: bool = False,
    limit: int = FREELIST_SHOW_LIMIT,
) -> None:
    tokens = list(command or [])
    sub = tokens[0] if tokens and tokens[0] in _BUDDY_SUBCOMMANDS else "info"
    rest = tokens[1:] if tokens and tokens[0] in _BUDDY_SUBCOMMANDS else tokens
    if sub == "list":
        _buddy_list(zone, order, mtype, node)
        return
    if sub == "freelist":
        _buddy_freelist(zone, order, mtype, node, verbose, limit)
        return
    if not rest:
        _buddy_parser_obj.print_usage()
        return
    for spec in rest:
        _buddy_info(spec, verbose)


def _buddy_list(
    zone: str | None, order: int | None, mtype: str | None,
    node: int | None,
) -> None:
    """Census every non-empty ``free_area``, one row per order.

    ``nr_free`` is the kernel's own per-order total (it counts every
    migratetype in that ``free_area``), so it is printed once per order.
    The per-migratetype breakdown is a property of the *lists*, which is
    what `kl-buddy freelist -v` expands.
    """
    kinds = (
        ("zone", zone), ("order", order), ("mtype", mtype), ("node", node),
    )
    active = " ".join(
        f"{name}={value}" for name, value in kinds if value is not None
    )
    print(message.hint(f"buddy free lists  ({active or 'all'})"))
    rows = kdbg.free_area_counts(
        zone=zone, order=order, mtype=mtype, node=node,
    )
    if not rows:
        print(
            message.warn(
                "no non-empty free area matched (needs node_data and a "
                "readable vmemmap)"
            )
        )
        return
    table = [
        (label, f"{node_index}", str(area_order), str(count),
         str(count << area_order))
        for label, node_index, area_order, count in rows
    ]
    print(
        kdbg.table(
            ("zone", "node", "order", "nr_free", "pages(1<<order)"), table,
        )
    )
    print(f"{len(rows)} non-empty order(s)")


def _buddy_info(spec: str, verbose: bool) -> None:
    """Describe one address: zone, block, position, state."""
    if not spec:
        _buddy_parser_obj.print_usage()
        return
    location = _resolve_one(spec)
    if location is None:
        print(message.error(f"cannot resolve {spec!r}"))
        return
    indent = IndentContextManager()
    indent.print(
        indent.prefix("Input") + f": {spec}"
    )
    indent.print(
        indent.prefix("Physical") + ": " + indent.aux_hex(location.phys)
        + "  " + indent.prefix("pfn") + f"={location.pfn:#x}"
    )
    indent.print(
        indent.prefix("Page") + ": " + indent.addr_hex(location.page)
    )
    if location.zone is None:
        indent.print(
            indent.prefix("Zone") + ": "
            + message.warn("not managed (no zone spans this pfn)")
        )
    else:
        suffix = "  [hole: inside spanned but outside present]" if location.hole else ""
        indent.print(
            indent.prefix("Zone") + ": " + message.notice(location.zone.name)
            + f"  node={location.zone.node}"
            + f"  start_pfn={location.zone.start_pfn:#x}"
            + f"  end_pfn={location.zone.end_pfn:#x}" + suffix
        )
    if location.free:
        indent.print(
            indent.prefix("Status") + ": "
            + message.on("free") + "  (on a buddy free list)"
        )
        assert location.order is not None
        assert location.size_pages is not None
        indent.print(
            indent.prefix("Order") + f": {location.order}      "
            + _size_text(location.size_pages)
        )
    else:
        indent.print(
            indent.prefix("Status") + ": " + message.off("allocated")
            + "  (not on any buddy free list)"
        )
        indent.print(
            indent.prefix("Order") + ": " + message.warn("-")
            + "  (the order is only recorded while a block is free)"
        )
    _buddy_block_lines(indent, location)
    if verbose:
        _buddy_verbose_lines(indent, location)


def _buddy_block_lines(
    indent: IndentContextManager, location: BlockLocation,
) -> None:
    """Print ``Block base`` / ``Position`` / ``Own block head``."""
    if location.base_pfn is None or location.size_pages is None:
        for label in ("Block base", "Position", "Own block head"):
            indent.print(
                indent.prefix(label) + ": " + message.warn("-")
            )
        return
    indent.print(
        indent.prefix("Block base") + f": order {location.order}  page "
        + indent.addr_hex(location.block_page or 0)
        + f"  pfn={location.base_pfn:#x}"
        + "  " + indent.prefix("phys") + "="
        + indent.aux_hex(location.block_phys or 0)
    )
    if location.is_block_head:
        indent.print(
            indent.prefix("Position") + ": 0 / "
            + f"{location.size_pages} pages  (block head)"
        )
    else:
        indent.print(
            indent.prefix("Position") + f": {location.position} / "
            + f"{location.size_pages} pages   "
            + f"(0x{(location.position or 0) << 12:x} bytes into the block)"
        )
    if location.is_block_head:
        indent.print(
            indent.prefix("Own block head") + ": order "
            + message.notice(str(location.order))
            + "  (this pfn is aligned to its own block)"
        )
    else:
        indent.print(
            indent.prefix("Own block head") + ": "
            + message.off("none")
            + " (this pfn is not aligned to its own order)"
        )


def _buddy_verbose_lines(
    indent: IndentContextManager, location: BlockLocation,
) -> None:
    """Print the block's span and its buddy's state."""
    span = kdbg.block_range(location)
    if span is not None:
        first_pfn, last_pfn, first_phys, last_phys = span
        indent.print(
            indent.prefix("Block span") + f": pfn {first_pfn:#x}-{last_pfn:#x}"
            + f"  phys {first_phys:#x}-{last_phys:#x}"
        )
    buddy = kdbg.buddy_pfn(location)
    if buddy is None:
        indent.print(indent.prefix("Buddy") + ": " + message.warn("-"))
        return
    buddy_pfn, buddy_phys = buddy
    page_bytes = kdbg.page_bytes()
    vmemmap = kdbg.read_kvar("vmemmap_base")
    if vmemmap is None:
        indent.print(
            indent.prefix("Buddy") + f": pfn={buddy_pfn:#x}"
            + "  " + message.warn("(vmemmap_base unreadable)")
        )
        return
    buddy_page = vmemmap + buddy_pfn * page_bytes
    buddy_order = kdbg.buddy_order(buddy_page)
    if buddy_order is None and kdbg.page_is_buddy(buddy_page) is None:
        state = message.warn("unknown (page unreadable)")
    elif buddy_order is not None:
        state = message.on("free") + f" (order {buddy_order})"
    else:
        state = message.off("allocated") + " (or merged into a larger block)"
    indent.print(
        indent.prefix("Buddy") + f": pfn={buddy_pfn:#x}"
        + "  " + indent.prefix("phys") + "=" + indent.aux_hex(buddy_phys)
        + "  status=" + state
    )
    if location.zone is not None:
        indent.print(
            indent.prefix("zone") + ": " + message.notice(location.zone.name)
            + f"  spanned={location.zone.spanned_pages} pages"
            + f"  present={location.zone.present_pages} pages"
        )


def _buddy_freelist(
    zone: str | None, order: int | None, mtype: str | None,
    node: int | None, verbose: bool, limit: int,
) -> None:
    """Print ``nr_free`` per order, or the blocks on one list (``-v``)."""
    if not verbose:
        _buddy_list(zone, order, mtype, node)
        return
    if order is None or zone is None or mtype is None:
        print(
            message.error(
                "freelist -v needs -z/--zone, -o/--order and -m/--mtype to "
                "pick exactly one list (the kernel stores only a per-order "
                "total, so the per-type breakdown requires choosing a type)"
            )
        )
        return
    blocks = kdbg.freelist_blocks(zone, order, mtype, node=node or 0,
                                  limit=max(limit, 1))
    indent = IndentContextManager()
    total = next(
        (
            count for label, _n, area_order, count in kdbg.free_area_counts(
                zone=zone, order=order, node=node,
            )
            if label.lower() == zone.lower() and area_order == order
        ),
        len(blocks),
    )
    indent.print(
        indent.prefix("free_area") + f"[order {order}]"
        + f"  mtype={mtype}  zone={zone}  node={node or 0}"
        + f"  nr_free={total}  pages={total << order}"
    )
    with indent:
        if not blocks:
            indent.print(message.warn("(this migratetype list is empty)"))
        for block in blocks:
            indent.print(
                "- " + indent.prefix(f"#{block.index}")
                + " pfn=" + indent.aux_hex(block.phys >> 12)
                + " phys=" + indent.aux_hex(block.phys)
                + " virt=" + indent.addr_hex(block.virt)
            )
        if total > len(blocks):
            indent.print(
                message.warn(
                    f"... (truncated, {len(blocks)} of {total} block(s))"
                )
            )