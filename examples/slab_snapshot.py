#!/usr/bin/env python3
"""Render a SLUB slab snapshot with the pure-Python part of kernlens.

Run from an installed environment::

    python examples/slab_snapshot.py

or from a checkout::

    PYTHONPATH=src python examples/slab_snapshot.py

This example is deliberately self-contained: it works on a slab head and
a page-table entry that need no live target.  The defaults are the
values this project's test kernel actually has -- Linux 6.1.134 as built
for the pwn4kernel VM -- instead of invented stand-ins, and they are
split the same way as the integration fixtures:

* **boot-invariant** facts: a page is 4 KiB and ``sizeof(struct page)``
is 64, so ``phys`` and ``struct page`` follow from a head address with
no extra input; the ``kmalloc-1k`` size/objects/order are the cache's own
configuration.
* **one sample boot** values: ``page_offset_base`` and ``vmemmap_base``
are kernel *variables* filled in from the physical memory map, so they
move on every boot.  The direct-map head and its PTE below were read
from one real boot; override ``--page-offset-base`` / ``--vmemmap-base``
(or ``--head``) to match your own kernel.

``examples/gdb_tracer.py`` shows the same table assembled from live
memory inside GDB.
"""

from __future__ import annotations

import argparse

from kernlens import IntFmt, KAddr, KPageTable, Logger, Palette, Styler

# Real test-kernel parameters: PageTable's own defaults describe a generic
# nokaslr kernel, so pass the live bases explicitly below.
#: real ``page_offset_base`` of the test kernel (a sample boot: the value
#: is picked from the physical memory map at boot).
PAGE_OFFSET_BASE = 0xFFFF9DBDC0000000
#: real ``vmemmap_base`` of the test kernel (also chosen at boot).
VMEMAP_BASE = 0xFFFFE1AFC0000000
#: ``sizeof(struct page)`` on this kernel (boot-invariant).
PAGE_BYTES = 64
#: real ``kmalloc-1k`` shape (boot-invariant for this build).
CACHE_NAME = "kmalloc-1k"
CACHE_OBJECT_SIZE = 0x400
CACHE_OBJECTS = 16
CACHE_ORDER = 2
#: a real direct-map page: physical 0x120000 is a free buddy page on the
#: test kernel, so its direct-map address and ``struct page`` are known.
DEFAULT_PHYS = 0x120000
DEFAULT_HEAD = PAGE_OFFSET_BASE + DEFAULT_PHYS
#: the real 4 KiB PTE the live page tables hold for ``DEFAULT_HEAD``
#: (present, writable, accessed, dirty, NX -> physical base 0x120000).
SAMPLE_PTE = 0x8000000000120063


def build_snapshot(
    head: int,
    page_offset_base: int = PAGE_OFFSET_BASE,
    vmemmap_base: int = VMEMAP_BASE,
) -> list[list[str]]:
    """Return the field/value rows for *head*."""
    phys = KAddr.virt_to_phys(head, page_offset_base)
    page = KAddr.virt_to_page(
        head, page_offset_base, vmemmap_base, PAGE_BYTES,
    )
    pgd, pud, pmd, pte, offset = KPageTable.split_4(head)

    return [
        ["head", IntFmt.addr(head)],
        ["phys", IntFmt.hex64(phys)],
        ["page", IntFmt.addr(page)],
        ["pfn", IntFmt.pfn(phys)],
        ["cache", CACHE_NAME],
        ["object size", IntFmt.size(CACHE_OBJECT_SIZE)],
        ["objects / order", f"{CACHE_OBJECTS} / {CACHE_ORDER}"],
        ["pgd / pud / pmd / pte", f"{pgd:#x} / {pud:#x} / {pmd:#x} / {pte:#x}"],
        ["page offset", f"{offset:#x}"],
    ]


def _int(text: str) -> int:
    """Parse a decimal, hex (``0x``) or python int literal."""
    return int(text, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--head", type=_int, default=DEFAULT_HEAD,
        help="slab head virtual address (default: 0x%x)" % DEFAULT_HEAD,
    )
    parser.add_argument(
        "--page-offset-base", type=_int, default=PAGE_OFFSET_BASE,
        dest="page_offset_base",
        help="direct-map base (default: 0x%x)" % PAGE_OFFSET_BASE,
    )
    parser.add_argument(
        "--vmemmap-base", type=_int, default=VMEMAP_BASE,
        dest="vmemmap_base",
        help="vmemmap base (default: 0x%x)" % VMEMAP_BASE,
    )
    parser.add_argument(
        "--color", action="store_true", help="force ANSI color output",
    )
    args = parser.parse_args()

    log = Logger(color_enabled=args.color)
    sty = Styler(color_enabled=args.color)

    log.banner("kernlens slab snapshot", width=60)
    log.info(sty.table(
        ["field", "value"],
        build_snapshot(args.head, args.page_offset_base, args.vmemmap_base),
        aligns=["l", "r"],
        header_color=Palette.CYAN,
    ))

    # Page-table helpers are pure arithmetic: they can decode a saved
    # PTE even when no kernel is running.  ``SAMPLE_PTE`` is the real
    # entry the test kernel's page tables hold for the default head.
    pte = SAMPLE_PTE
    log.info(sty.kv("sample pte", IntFmt.hex64(pte)))
    log.info(sty.kv("pte pfn", IntFmt.pfn(KPageTable.pte_phys(pte))))
    log.info(sty.kv("pte flags", "|".join(KPageTable.pte_flags(pte))))
    log.info(sty.kv(
        "leaf phys",
        IntFmt.hex64(KPageTable.pte_to_phys(pte, args.head)),
    ))


if __name__ == "__main__":
    main()