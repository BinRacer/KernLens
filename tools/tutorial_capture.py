#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Capture real command output for the tutorial.

This is the half of the tutorial pipeline that must run **inside GDB**
against a live kernel; ``tools/gen_tutorial.py`` is the half that runs
anywhere.  Split that way, the documentation cannot drift from reality
without someone noticing: the pages are re-rendered from a capture, and
a capture can only be produced by running the commands.

Run it from GDB::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) file /path/to/vmlinux
    (gdb) target remote :1234
    (gdb) kl-color off
    (gdb) python exec(open("tools/tutorial_capture.py").read())

It writes ``tools/tutorial_capture.json`` beside this file.  Colour is
turned off first so the captured text is plain, but the capture also
*runs* ``kernlens-color on`` and ``kernlens-color toggle`` to document
them, so later cases in the same run are captured with colour on.  That
is expected: the JSON records what the command printed.  Stripping the
escape sequences is the renderer's job (``gen_tutorial.py`` and
``gen_demo.py`` both do it), because a ```text``` fence cannot render an
SGR sequence and an SVG cannot contain one at all.

Adding an example: add the invocation to the matching list below and
reference it verbatim from ``tools/tutorial_prose.py``;
``gen_tutorial.py --check`` then fails until the page shows the real
output.
"""

from __future__ import annotations

import json
import os
import pathlib

import gdb  # type: ignore[import-not-found]

from kernlens.gdb.facade import kdbg

#: Directory holding this script.  ``__file__`` is absent when the file is
#: run through ``exec(open(...).read())``, which is how GDB is told to load
#: it, so the path is taken from the environment instead and defaults to
#: the repository's ``tools/`` directory.
_TOOLS = pathlib.Path(
    os.environ.get("KERNLENS_TOOLS", "tools")
).resolve()

#: Physical address of a free page used by the buddy/memory examples.
#: 0x400000 is the head of an order-10 block in the DMA zone on the
#: 128 MiB test guest, so it exercises the huge-page and block-head
#: paths at once.
FREE_PHYS = 0x400000

#: PFN of the same page, for the forms that take a pfn directly.
FREE_PFN = FREE_PHYS >> 12


def _probe() -> dict:
    """Read the live kernel facts the invocations are built from.

    Every address in the tutorial is derived from what the kernel
    reports, never hardcoded: the KASLR slide and the two bases change on
    each boot, so a literal would be wrong on the next capture.
    """
    slide = kdbg.kaslr_slide()
    link = kdbg.link_text()
    page_offset = kdbg.read_kvar("page_offset_base")
    vmemmap = kdbg.read_kvar("vmemmap_base")
    return {
        "kernel": ".".join(str(p) for p in kdbg.krelease() or ()),
        "slide": slide,
        "link_text": link,
        "text": (link + slide) & 0xFFFFFFFFFFFFFFFF,
        "page_offset_base": page_offset,
        "vmemmap_base": vmemmap,
        "direct": page_offset + FREE_PHYS,
        "text_addr": (link + slide + 0x100000) & 0xFFFFFFFFFFFFFFFF,
        "text_sym": (link + slide + 0x100) & 0xFFFFFFFFFFFFFFFF,
        "vmemmap_page": vmemmap + FREE_PFN * kdbg.page_bytes(),
        "slab_object": _slab_object(),
        "nr_cpus": kdbg.nr_cpus(),
        "cache_count": len(kdbg.slab_caches()),
    }


def _slab_object() -> int:
    """Return a real object address from a real cache.

    ``dentry`` is preferred because it exists on every SLUB kernel and
    has a non-trivial usercopy window, so its ``info`` page has something
    worth showing.

    A node's partial list is preferred over a per-CPU freelist because an
    object is only useful for ``kl-slab details`` if its *page* still
    holds a ``slab->freelist`` chain: that is what shows a decoded free
    pointer.  A per-CPU slab is frequently drained (``freelist: NULL``)
    because the allocator hands its last object to the caller, which
    would render a page with nothing to decode.  The order therefore goes
    partial list first, per-CPU second, active slab last.
    """
    cache = kdbg.slab_cache("dentry")
    if cache is None:
        cache = kdbg.slab_caches()[0]
    address = cache.address
    for node in range(max(kdbg.nr_nodes(), 1)):
        count, _node, _head_slab, head_freelist = kdbg.partial_info(
            address, node,
        )
        if count and head_freelist:
            return head_freelist
    for cpu in range(kdbg.nr_cpus()):
        freelist = kdbg.cpu_freelist(address, cpu)
        if freelist:
            return freelist
    return kdbg.cpu_active_slab(address, 0) or 0


def _cases(ctx: dict) -> list[tuple[str, list[str]]]:
    """Return ``[(command, [invocation, ...]), ...]`` to capture."""
    direct = f"{ctx['direct']:#x}"
    vmemmap_page = f"{ctx['vmemmap_page']:#x}"
    text_addr = f"{ctx['text_addr']:#x}"
    slide = f"{ctx['slide']:#x}"
    obj = f"{_slab_object():#x}"
    names = [c.name for c in kdbg.slab_caches()]
    small = "dentry" if "dentry" in names else names[0]
    return [
        ("kl-help", [
            "kl-help", "kl-help kl-walk",
            "kl-help kernlens-slab", "kl-help kl-buddy",
        ]),
        ("kl-status", ["kl-status"]),
        ("kl-color", [
            "kl-color", "kl-color toggle",
            "kl-color on", "kl-color off",
        ]),
        ("kl-base", [
            "kl-base", "kl-base show", "kl-base -v",
            "kl-base idt 4", "kl-base rebase",
            f"kl-base text {ctx['text']:#x}",
            f"kl-base {ctx['text']:#x}",
            f"kl-base offset {slide}",
        ]),
        ("kl-kcmdline", ["kl-kcmdline"]),
        ("kl-kversion", ["kl-kversion"]),
        ("kl-kconfig", [
            "kl-kconfig RANDOMIZE_BASE", "kl-kconfig",
            "kl-kconfig --check",
        ]),
        ("kl-kmod", ["kl-kmod", "kl-kmod nonexistent"]),
        ("kl-ksyscalls", [
            "kl-ksyscalls", "kl-ksyscalls read",
            "kl-ksyscalls 0",
        ]),
        ("kl-kdmesg", ["kl-kdmesg", "kl-kdmesg --ctime"]),
        ("kl-cpu", ["kl-cpu", "kl-cpu 0"]),
        ("kl-percpu", [
            "kl-percpu current_task", "kl-percpu current_task 1",
        ]),
        ("kl-msr", [
            "kl-msr -l", "kl-msr 0xc0000082",
            "kl-msr MSR_LSTAR",
            "kl-msr --range 0xc0000080-0xc0000084",
        ]),
        ("kl-addr", [
            f"kl-addr {direct}", f"kl-addr {text_addr}",
            "kl-addr 0xffff888000001234", "kl-addr 0x5",
            f"kl-addr {direct} 0xfff",
            f"kl-addr {direct} --brief",
            f"kl-addr {vmemmap_page} --brief",
        ]),
        ("kl-pt", [
            f"kl-pt {direct}", f"kl-pt {text_addr}",
            "kl-pt 0xffff888000001234",
            "kl-pt --entry 0x8000000000120063",
            f"kl-pt --entry 0x8000000000120063 {direct}",
        ]),
        ("kl-walk", [
            f"kl-walk {direct}", f"kl-walk {direct} 5",
            f"kl-walk {direct} --style pwndbg",
        ]),
        ("kl-pageinfo", [f"kl-pageinfo {vmemmap_page}"]),
        ("kl-p2v", [f"kl-p2v {FREE_PHYS:#x}"]),
        ("kl-v2p", [f"kl-v2p {direct}"]),
        ("kl-sym", [
            f"kl-sym {ctx['text_sym']:#x}",
            f"kl-sym {direct}",
            "kl-sym --find commit_creds",
            "kl-sym --find page_offset_base",
        ]),
        ("kl-bt", [
            "kl-bt", "kl-bt 4",
            "kl-bt --chain", "kl-bt 12 --chain",
        ]),
        ("kl-read", [
            f"kl-read {direct}", f"kl-read {direct} 16 -m ascii",
        ]),
        ("kl-kvar", [
            "kl-kvar page_offset_base", "kl-kvar vmemmap_base",
            "kl-kvar nr_online_nodes",
        ]),
        ("kl-read-field", [
            f"kl-read-field {vmemmap_page} 'struct page' "
            "_refcount.counter",
        ]),
        ("kl-slab", [
            "kl-slab list", "kl-slab list kmalloc",
            "kl-slab list dentry", f"kl-slab info {small}",
            f"kl-slab info {small} -i -r --reclaim --ctor",
            f"kl-slab info {small} -p", f"kl-slab info {small} -a",
            "kl-slab info kmalloc-1k", f"kl-slab contains {obj}",
            f"kl-slab details {obj}",
        ]),
        ("kl-buddy", [
            "kl-buddy list", "kl-buddy list -z DMA",
            "kl-buddy info pfn:1024", f"kl-buddy info {direct}",
            "kl-buddy info pfn:1024 -v",
            "kl-buddy freelist -z DMA -o 10 -m Movable",
            "kl-buddy freelist -z DMA -o 10 -m Movable -v",
            "kl-buddy freelist -z DMA -o 10 -m Unmovable -v",
            "kl-buddy dump", "kl-buddy dump -z DMA",
            "kl-buddy dump -z DMA -o 10",
            f"kl-buddy dump -f {direct}",
            "kl-buddy dump --MIGRATE_TYPES 5",
        ]),
        ("kl-kbpf", [
            "kl-kbpf", "kl-kbpf -p", "kl-kbpf -m",
        ]),
        ("kl-kdmabuf", ["kl-kdmabuf"]),
        ("kl-bits", [
            "kl-bits 0xff 3", f"kl-bits {text_addr}",
        ]),
        ("kl-int", [
            "kl-int 0xff", "kl-int 0xff 8", "kl-int -1 32",
            "kl-int 0x1234 16",
        ]),
    ]


def _run(cases: list[tuple[str, list[str]]]) -> list[dict]:
    """Execute every invocation, keeping failures as data."""
    results: list[dict] = []
    for command, invocations in cases:
        for invocation in invocations:
            try:
                output = gdb.execute(invocation, to_string=True)
            except Exception as exc:  # noqa: BLE001 - reported verbatim
                output = f"<EXCEPTION> {type(exc).__name__}: {exc}"
            results.append({
                "command": command,
                "invocation": invocation,
                "output": output,
            })
    return results


def main() -> None:
    context = _probe()
    results = _run(_cases(context))
    failing = [r for r in results if r["output"].startswith("<EXCEPTION>")]
    target = _TOOLS / "tutorial_capture.json"
    target.write_text(
        json.dumps({"context": context, "cases": results}, indent=1),
        encoding="utf-8",
    )
    print(f"captured {len(results)} invocation(s) -> {target}")
    if failing:
        print(f"WARNING: {len(failing)} invocation(s) raised:")
        for row in failing:
            print(f"  {row['invocation']}: {row['output']}")


main()