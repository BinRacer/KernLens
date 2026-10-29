#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Address and page-table commands (pwndbg-style).

``kernlens-addr`` / ``pt`` / ``walk`` / ``p2v`` / ``v2p`` / ``pageinfo``.

``page``, ``pte`` and ``pagewalk`` used to be commands of their own and are
now a mode of the command that already answered the same question: ``addr``
classified an address and ``page -v`` delegated to it, ``pt`` split an
address while ``pte`` decoded an entry value, and ``walk``/``pagewalk`` ran
the same page walk with two presentations.
"""

from __future__ import annotations

import argparse

from .. import KERNEL_BASE, KAddr, KPageTable
from ..gdb.facade import kdbg
from ..gdb.walker import PageWalk
from ..output import message
from ..output.tree import IndentContextManager
from .formatting import (
    fmt_onoff,
    page_offset_base,
    parse_int,
    vmemmap_base,
)
from .framework import Command, CommandCategory, parse_int_arg


def _runtime_text() -> int | None:
    """Return runtime ``_text`` when the symbol is available."""
    link = kdbg.link_text()
    if link is None:
        return None
    return (link + kdbg.kaslr_offset) & 0xFFFFFFFFFFFFFFFF


def _print_page_info(indent: IndentContextManager, phys: int, page: int) -> None:
    """Print the ``struct page`` type and refcount (pwndbg-style block)."""
    indent.print(indent.prefix("page") + ": " + indent.addr_hex(page))
    type_name = kdbg.page_type(page)
    indent.print(
        indent.prefix("PFN") + f": {KAddr.phys_to_pfn(phys)}"
        + "  type: " + message.notice(type_name)
    )
    refcount = kdbg.page_refcount(page)
    indent.print(
        indent.prefix("refcount")
        + ": "
        + (str(refcount) if refcount is not None else message.warn("?"))
    )


# =========================================================================
# addr (was: addr + page)
# =========================================================================

_addr_parser = argparse.ArgumentParser(
    description="Classifies an address and reports where it maps."
)
_addr_parser.add_argument(
    "address", type=parse_int_arg, help="address or GDB expression to analyse",
)
_addr_parser.add_argument(
    "tag_mask", nargs="?", type=parse_int_arg, default=None,
    help="mask used for pointer-tag analysis (e.g. 0xfff)",
)
_addr_parser.add_argument(
    "-b", "--brief", action="store_true",
    help="only the class, the translation, and the two bases",
)


@Command(
    _addr_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-addr"],
    examples=(
        "kl-addr 0xffff888000001234\n"
        "kl-addr 0xffff888000001234 0xfff\n"
        "kl-addr 0xffff888000001234 --brief"
    ),
    notes=(
        "``-b/--brief`` answers the one question most lookups have --\n"
        "which region is this, and what does it map to -- and stops.  It\n"
        "replaces ``kl-page``, which printed the same block behind a\n"
        "command name that differed from ``kl-addr`` by two letters."
    ),
)
def kernlens_addr(
    address: int, tag_mask: int | None = None, brief: bool = False,
) -> None:
    if brief:
        _addr_brief(address)
        return
    page_offset = page_offset_base()
    vmemmap = vmemmap_base()
    text = _runtime_text()
    direct = KAddr.is_direct_map(address, page_offset)
    indent = IndentContextManager()
    indent.print(indent.prefix("Address") + ": " + indent.addr_hex(address))
    indent.print(
        indent.prefix("Canonical")
        + ": 48=" + fmt_onoff(KAddr.is_canonical(address, 48))
        + "  57=" + fmt_onoff(KAddr.is_canonical(address, 57))
    )
    indent.print(
        indent.prefix("Region")
        + ": kernel=" + fmt_onoff(KAddr.is_kernel(address))
        + " user=" + fmt_onoff(KAddr.is_user(address))
        + " direct=" + fmt_onoff(direct)
        + " vmemmap=" + fmt_onoff(KAddr.is_vmemmap(address, vmemmap))
        + " vmalloc=" + fmt_onoff(KAddr.is_vmalloc(address))
        + " module=" + fmt_onoff(KAddr.is_module(address))
        + " text=" + fmt_onoff(KAddr.is_text(address, text or KERNEL_BASE))
    )
    if KAddr.is_err(address):
        indent.print(
            indent.prefix("ERR_PTR") + ": " + message.error("yes")
            + f"  errno={KAddr.ptr_err(address)}"
        )
    else:
        indent.print(indent.prefix("ERR_PTR") + ": " + message.success("no"))
    indent.print(
        indent.prefix("Alignment")
        + ": down=" + indent.addr_hex(KAddr.page_align(address))
        + " up=" + indent.addr_hex(KAddr.page_align_up(address))
    )
    if tag_mask is not None:
        indent.print(
            indent.prefix("Tags")
            + ": mask=" + indent.addr_hex(tag_mask)
            + " tag=" + indent.addr_hex(KAddr.ptr_tag(address, tag_mask))
            + " stripped=" + indent.addr_hex(KAddr.strip_tag(address, tag_mask))
        )
    if direct:
        phys = KAddr.virt_to_phys(address, page_offset)
        indent.print(
            indent.prefix("Physical") + ": " + indent.aux_hex(phys)
            + f"  pfn={KAddr.phys_to_pfn(phys)}"
        )
        indent.print(
            indent.prefix("page") + ": "
            + indent.aux_hex(KAddr.phys_to_page(phys, vmemmap))
        )


def _addr_brief(address: int) -> None:
    """The short form: class, translation, and the two bases.

    Same text ``kl-page`` printed before it became ``kl-addr --brief``.
    """
    page_offset = page_offset_base()
    vmemmap = vmemmap_base()
    text = _runtime_text()
    direct = KAddr.is_direct_map(address, page_offset)
    indent = IndentContextManager()
    indent.print(indent.prefix("Address") + ": " + indent.addr_hex(address))
    indent.print(
        indent.prefix("Class")
        + ": kernel=" + fmt_onoff(KAddr.is_kernel(address))
        + " user=" + fmt_onoff(KAddr.is_user(address))
        + " direct=" + fmt_onoff(direct)
        + " vmemmap=" + fmt_onoff(KAddr.is_vmemmap(address, vmemmap))
        + " vmalloc=" + fmt_onoff(KAddr.is_vmalloc(address))
        + " module=" + fmt_onoff(KAddr.is_module(address))
        + " text=" + fmt_onoff(KAddr.is_text(address, text or KERNEL_BASE))
    )
    if direct:
        phys = KAddr.virt_to_phys(address, page_offset)
        page = KAddr.phys_to_page(phys, vmemmap)
        indent.print(
            indent.prefix("Physical") + ": " + indent.aux_hex(phys)
            + f"  pfn={KAddr.phys_to_pfn(phys)}"
        )
        indent.print(indent.prefix("page") + ": " + indent.aux_hex(page))
    indent.print(
        indent.prefix("bases")
        + ": page_offset=" + indent.addr_hex(page_offset)
        + " vmemmap=" + indent.addr_hex(vmemmap)
    )


# =========================================================================
# pt (was: pt + pte)
# =========================================================================

_pt_parser = argparse.ArgumentParser(
    description=(
        "Splits a virtual address into page-table indices, or decodes a "
        "page-table entry."
    )
)
# One positional drives both views, because ``kl-pt`` and ``kl-pte``
# differed only in what the number meant.  ``--entry`` says it is an entry
# value; the default reads it as an address.  A single ``nargs="*"``
# positional avoids argparse deciding which of two optional positionals an
# argument belongs to.
_pt_parser.add_argument(
    "values", nargs="*", metavar="VALUE",
    help="virtual address [leaf address used for the translations]",
)
_pt_parser.add_argument(
    "-e", "--entry", action="store_true",
    help="treat VALUE as a raw page-table entry instead of an address",
)
_pt_parser.add_argument(
    "--paging", choices=["4", "5"], default=None,
    help="force one geometry instead of printing both",
)


@Command(
    _pt_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-pt"],
    examples=(
        "kl-pt 0xffff888000001234\n"
        "kl-pt 0xffff888000001234 --paging 5\n"
        "kl-pt --entry 0x8000000000123067\n"
        "kl-pt --entry 0x8000000000123067 0xffff888000001234"
    ),
    notes=(
        "``--entry`` decodes a page-table *value* (flags, physical address,\n"
        "and the three leaf interpretations when a second address is given);\n"
        "without it the argument is treated as an address and split into\n"
        "indices.  It replaces ``kl-pte``, which was the same decoder behind\n"
        "a name that differed from ``kl-pt`` by one letter."
    ),
)
def kernlens_pt(
    values: list[str] | None = None,
    entry: bool = False,
    paging: str | None = None,
) -> None:
    tokens = list(values or [])
    if not tokens:
        _pt_parser.print_usage()
        return
    if entry:
        raw = parse_int(tokens[0])
        va = parse_int(tokens[1]) if len(tokens) > 1 else None
        _pt_entry(raw, va)
        return
    if len(tokens) > 1:
        print(
            message.error(
                "a virtual address takes one argument; pass --entry to "
                "decode a table entry"
            )
        )
        return
    _pt_indices(parse_int_arg(tokens[0]), paging)


def _pt_entry(entry_value: int, va: int | None = None) -> None:
    """Decode one page-table entry value (the former ``kl-pte``)."""
    entry = entry_value
    indent = IndentContextManager()
    indent.print(
        indent.prefix("PTE") + ": " + indent.addr_hex(entry)
        + " present=" + fmt_onoff(KPageTable.pte_present(entry))
        + " bit7=PS/PAT"
    )
    indent.print(
        indent.prefix("Flags")
        + ": " + message.notice(" ".join(KPageTable.pte_flags(entry)) or "-")
    )
    indent.print(
        indent.prefix("Physical")
        + ": " + indent.aux_hex(KPageTable.pte_phys(entry))
        + f"  pfn={KPageTable.pte_pfn(entry)}"
    )
    if va is not None:
        # Bit 7 means PS in a PUD/PMD and PAT in a PTE, so the level is
        # unknown here: print all three leaf interpretations.
        indent.print(indent.prefix("VA") + ": " + indent.addr_hex(va))
        indent.print(
            indent.prefix("4k leaf")
            + ": " + indent.aux_hex(KPageTable.pte_to_phys(entry, va))
        )
        indent.print(
            indent.prefix("2m leaf")
            + ": " + indent.aux_hex(KPageTable.pmd_to_phys(entry, va))
        )
        indent.print(
            indent.prefix("1g leaf")
            + ": " + indent.aux_hex(KPageTable.pud_to_phys(entry, va))
        )


def _pt_indices(va: int, paging: str | None = None) -> None:
    """Split one virtual address into page-table indices."""
    pgd, pud, pmd, pte, offset = KPageTable.split_4(va)
    pgd5, p4d, pud5, pmd5, pte5, offset5 = KPageTable.split_5(va)
    indent = IndentContextManager()
    indent.print(indent.prefix("VA") + ": " + indent.addr_hex(va))
    if paging != "5":
        indent.print(
            indent.prefix("4-level")
            + f": pgd={pgd} pud={pud} pmd={pmd} pte={pte}"
            + " off=" + indent.aux_hex(offset)
        )
    if paging != "4":
        indent.print(
            indent.prefix("5-level")
            + f": pgd={pgd5} p4d={p4d} pud={pud5} pmd={pmd5} pte={pte5}"
            + " off=" + indent.aux_hex(offset5)
        )
    indent.print(
        indent.prefix("huge")
        + ": 2m_base=" + indent.addr_hex(KPageTable.huge_2m_base(va))
        + " 1g_base=" + indent.addr_hex(KPageTable.huge_1g_base(va))
    )
    indent.print(
        indent.prefix("aligned")
        + ": 2m=" + fmt_onoff(KPageTable.is_2m_aligned(va))
        + " 1g=" + fmt_onoff(KPageTable.is_1g_aligned(va))
        + " page_offset=" + indent.aux_hex(KPageTable.page_offset(va))
    )
    indent.print(
        indent.prefix("canonical")
        + ": 4-level=" + indent.addr_hex(KPageTable.canonicalize(va, False))
        + " 5-level=" + indent.addr_hex(KPageTable.canonicalize(va, True))
    )


# =========================================================================
# walk / pagewalk
# =========================================================================

_walk_parser = argparse.ArgumentParser(
    description="Walks the live page tables and decodes every level."
)
_walk_parser.add_argument(
    "va", type=parse_int_arg, help="virtual address to translate",
)
_walk_parser.add_argument(
    "mode", nargs="?", choices=["4", "5"], default=None,
    help="force 4-level or 5-level paging (default: auto)",
)
_walk_parser.add_argument(
    "-p", "--pgd", dest="root", type=parse_int_arg, default=None,
    help="top-level table to start from (default: the live CR3)",
)
_walk_parser.add_argument(
    "-s", "--style", choices=["levels", "pwndbg"], default="levels",
    help=(
        "presentation: one row per level, or pwndbg's pagewalk order "
        "(default: levels)"
    ),
)


@Command(
    _walk_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-walk"],
    examples=(
        "kl-walk 0xffff888000001234\n"
        "kl-walk 0xffff800000201234 5\n"
        "kl-walk 0xffff888000001234 --pgd 0x10000\n"
        "kl-walk 0xffff888000001234 --style pwndbg"
    ),
    notes=(
        "``-p/--pgd`` walks a table other than the live CR3 -- a saved or\n"
        "foreign root, so a page table of another task can be followed\n"
        "without switching to it.\n"
        "\n"
        "``-s/--style pwndbg`` prints the deepest level first, in\n"
        "pwndbg's ``vmmap``-style layout; ``levels`` (the default) prints\n"
        "one row per level from the top down.  It is one walk either way,\n"
        "so it is one command."
    ),
)
def kernlens_walk(
    va: int,
    mode: str | None = None,
    root: int | None = None,
    style: str = "levels",
) -> None:
    five_level = None if mode is None else mode == "5"
    walk = kdbg.walk(va, five_level=five_level, root=root)
    if style == "pwndbg":
        _walk_pwndbg(walk)
        return
    indent = IndentContextManager()
    indent.print(indent.prefix("VA") + ": " + indent.addr_hex(walk.va))
    indent.print(
        indent.prefix("Paging")
        + f": {5 if walk.five_level else 4}-level  root="
        + indent.addr_hex(walk.root or 0)
    )
    for level in walk.levels:
        line = (
            indent.prefix(f"{level.name:<9}")
            + ": idx=" + indent.aux_hex(level.index)
            + " entry=" + indent.addr_hex(level.entry_addr)
            + " value=" + indent.aux_hex(level.value)
        )
        if level.huge:
            line += " " + message.notice("(huge leaf)")
        elif level.next_table is not None:
            line += " -> " + indent.addr_hex(level.next_table)
        indent.print(line)
    if walk.phys is not None:
        size = walk.page_size or 0
        kind = {1 << 12: "4 KiB", 1 << 21: "2 MiB huge", 1 << 30: "1 GiB huge"}
        leaf_entry = walk.levels[-1].value if walk.levels else 0
        indent.print(
            indent.prefix("Leaf")
            + ": " + message.notice(kind.get(size, "leaf"))
            + " pa=" + indent.aux_hex(walk.phys)
            + " offset=" + indent.aux_hex(walk.va & (size - 1))
        )
        indent.print(
            indent.prefix("Flags")
            + ": " + message.notice(" ".join(KPageTable.pte_flags(leaf_entry)) or "-")
        )
    else:
        indent.print(
            indent.prefix("Note")
            + ": " + message.warn(walk.note or "walk did not reach a leaf")
        )


def _walk_pwndbg(walk: PageWalk) -> None:
    """Print a completed walk in pwndbg's ``pagewalk`` layout.

    The deepest level comes first and the resolved physical address last,
    which is the order a reader of pwndbg's output already knows.  Same
    walk, same data -- only the presentation differs, which is why this is
    a style of ``kl-walk`` rather than a command of its own.
    """
    indent = IndentContextManager()
    # pwndbg prints the deepest level first, then the final result.
    for level in reversed(walk.levels):
        pointer = ""
        if level.next_table:
            pointer = " -> " + indent.addr_hex(level.next_table)
        suffix = " " + message.notice("(huge)") if level.huge else ""
        indent.print(
            indent.prefix(f"{level.name:<7}") + "@ " + indent.addr_hex(level.entry_addr)
            + f" [{level.index:03x}] "
            + message.notice(f"{level.name}e:")
            + " " + indent.aux_hex(level.value) + pointer + "  "
            + message.notice(" ".join(KPageTable.pte_flags(level.value)) or "-")
            + suffix
        )
    if walk.phys is None:
        indent.print(message.warn("address is not mapped"))
        if walk.note:
            indent.print(indent.prefix("Note") + ": " + message.warn(walk.note))
        return
    indent.print(
        indent.prefix("pagewalk result")
        + ": " + indent.addr_hex(walk.va)
        + " [phys: " + indent.aux_hex(walk.phys) + "]"
    )


# =========================================================================
# p2v / v2p / pageinfo
# =========================================================================

_p2v_parser = argparse.ArgumentParser(
    description="Translates a physical address to virtual + struct page."
)
_p2v_parser.add_argument(
    "paddr", type=parse_int_arg, help="physical address to translate",
)


@Command(
    _p2v_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-p2v"],
    examples="kl-p2v 0x1000",
)
def kernlens_p2v(paddr: int) -> None:
    phys = paddr
    if phys < 0:
        print(message.error("physical address must be >= 0"))
        return
    virt = KAddr.phys_to_virt(phys, page_offset_base())
    page = KAddr.phys_to_page(phys, vmemmap_base(), kdbg.page_bytes())
    indent = IndentContextManager()
    indent.print(indent.prefix("Physical") + ": " + indent.aux_hex(phys))
    indent.print(indent.prefix("Virtual") + ": " + indent.addr_hex(virt))
    _print_page_info(indent, phys, page)


_v2p_parser = argparse.ArgumentParser(
    description="Translates a virtual address (live page tables) to physical."
)
_v2p_parser.add_argument(
    "vaddr", type=parse_int_arg, help="virtual address to translate",
)


@Command(
    _v2p_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-v2p"],
    examples="kl-v2p 0xffff888000001234",
)
def kernlens_v2p(vaddr: int) -> None:
    va = vaddr
    walk = kdbg.walk(va)
    if walk.phys is None:
        print(
            message.error(
                "unmapped virtual address: "
                + (walk.note or "page walk did not reach a leaf")
            )
        )
        return
    phys = walk.phys
    page = KAddr.phys_to_page(phys, vmemmap_base(), kdbg.page_bytes())
    indent = IndentContextManager()
    indent.print(indent.prefix("Virtual") + ": " + indent.addr_hex(va))
    indent.print(indent.prefix("Physical") + ": " + indent.aux_hex(phys))
    _print_page_info(indent, phys, page)


_pageinfo_parser = argparse.ArgumentParser(
    description="Translates a struct page to virtual and physical addresses."
)
_pageinfo_parser.add_argument(
    "page", type=parse_int_arg, help="address of a struct page (head page)",
)


@Command(
    _pageinfo_parser,
    category=CommandCategory.PAGING,
    aliases=["kl-pageinfo"],
    examples="kl-pageinfo 0xffffea0000000040",
)
def kernlens_pageinfo(page: int) -> None:
    try:
        phys = KAddr.page_to_phys(page, vmemmap_base(), kdbg.page_bytes())
        virt = KAddr.page_to_virt(
            page, page_offset_base(), vmemmap_base(), kdbg.page_bytes(),
        )
    except ValueError as exc:
        print(message.error(f"invalid struct page: {exc}"))
        return
    indent = IndentContextManager()
    indent.print(indent.prefix("Virtual") + ": " + indent.addr_hex(virt))
    indent.print(indent.prefix("Physical") + ": " + indent.aux_hex(phys))
    _print_page_info(indent, phys, page)


__all__ = [
    "kernlens_addr",
    "kernlens_p2v",
    "kernlens_pageinfo",
    "kernlens_pt",
    "kernlens_v2p",
    "kernlens_walk",
]