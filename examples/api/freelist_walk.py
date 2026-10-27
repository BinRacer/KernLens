#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Follow a SLUB freelist, including the part that is not a pointer.

Every other slab example in this tree reads the allocator through the
high-level helpers.  This one reads the *encoding*, because that is the
piece a reader cannot guess and the piece a use-after-free tracer has to
get right.

The mechanism, in three lines:

1. A free object's first `offset` bytes hold a **stored** word, not the
   next object's address.  `kmem_cache->offset` says where the slot is --
   `0x200` on `kmalloc-1k`, i.e. the middle of the object, because the
   kernel puts it where `INIT_ON_ALLOC` padding and the free pointer do
   not overlap.
2. With `CONFIG_SLAB_FREELIST_HARDENED=y`, that word is
   `next ^ random ^ swab(slot_address)`, so it looks like garbage.
   `kmem_cache->random` is the per-cache key.
3. `decode_freeptr(stored, random, slot)` is the inverse.  It needs the
   **slot's own address**, which is why the same stored value means
   different objects in different slots.

The example walks the chain and prints both sides -- the stored word and
the decoded pointer -- because the point is that the first is
unrecognisable and the second is obviously a heap address.  It also
verifies each decoded pointer belongs to the cache's slab, which is the
check that catches a wrong `offset` or a wrong `random`:

* a decoded address outside the slab means the key or the slot is wrong,
  and the walk should stop rather than follow garbage;
* a chain longer than `oo_objects` means the same thing, and is how a
  corrupted freelist shows up as a loop.

`CONFIG_SLAB_FREELIST_RANDOM=y` is why the chain is not in address
order: the kernel randomises the initial order to make heap grooming
harder, so consecutive objects are not adjacent.  That is worth seeing
once, because it is the reason a freelist walk cannot be replaced by
"start at the slab base and step by object size".

Requires a live target::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/freelist_walk.py
    (gdb) flwalk                 # kmalloc-1k, every CPU
    (gdb) flwalk kmalloc-32 -c 2
    (gdb) flwalk kmalloc-1k --limit 4
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("freelist_walk.py must be sourced by GDB") from exc


def _bootstrap_if_needed() -> None:
    """Load the public API if this file was not sourced after gdbinit."""
    try:
        kdbg  # type: ignore[used-before-def]  # noqa: B018
    except NameError:
        import sys
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from kernlens.gdb.api import install_public_api

        install_public_api(globals())


_bootstrap_if_needed()


def _section(title: str) -> None:
    gdb.write(f"\n=== {title} " + "=" * max(0, 62 - len(title)) + "\n")


#: Which hardening options change the picture, and how.  Printed up front
#: because a reader who does not know `SLAB_FREELIST_HARDENED` is on will
#: read the stored words as corruption.
HARDENING_NOTES: dict[str, str] = {
    "SLAB_FREELIST_HARDENED": "stored word is XORed with a key and the slot address",
    "SLAB_FREELIST_RANDOM": "initial order is randomised, so the chain is not sequential",
    "INIT_ON_ALLOC_DEFAULT_ON": "freshly allocated objects are zeroed",
    "INIT_ON_FREE_DEFAULT_ON": "freed objects are zeroed, which destroys the chain",
}


def report_hardening() -> None:
    """What this kernel does to the chain, before showing it.

    `config_get()` returns the *value* (``"y"``, ``"n"``, or ``"m"`` for
    a tristate) and ``None`` when the key is not in the parsed map.
    Testing that return for truthiness -- the obvious thing to write --
    reports every option this kernel sets to ``n`` as ``y``, which here
    would have claimed that freed objects are zeroed, the exact misreading
    this section exists to prevent.

    ``None`` is not quite ``"n"`` either.  The parser keeps only
    ``NAME=value`` lines, so ``# CONFIG_X is not set`` never reaches the
    map: an option disabled in the config and an option that appears
    nowhere look identical.  Both mean "off", which is what gets printed,
    but the difference is flagged with ``*`` because a reader debugging a
    surprising chain should know the tool cannot tell them apart.
    """
    _section("what this kernel does to the freelist")
    absent: list[str] = []
    for name, effect in HARDENING_NOTES.items():
        value = kdbg.kconfig_get(name)  # noqa: F821
        if value is None:
            absent.append(name)
            state = "n*"
        else:
            state = value
        gdb.write(f"{name:<28s} = {state:<8s} {effect}\n")
    if absent:
        gdb.write(
            "\n* not in the parsed CONFIG_* map.  The parser keeps only\n"
            "  NAME=value lines, so '# X is not set' is dropped: this\n"
            "  reads 'off', but 'off' and 'unknown' cannot be told apart\n"
            "  from here.  Both mean there is nothing to watch.\n"
        )


def decode_one(cache_name: str, cpu: int) -> None:
    """Step 1-3 on a single object: stored word versus decoded pointer.

    Reading the same slot twice -- once raw, once decoded -- is the whole
    demonstration.  A reader who has only seen `decode_freeptr()` in a
    docstring has not seen that the input is unrecognisable.
    """
    cache = kdbg.slab_cache(cache_name)  # noqa: F821
    if cache is None:
        _section(f"{cache_name} is absent")
        gdb.write("-- no such cache on this kernel\n")
        return

    offset = kdbg.freeptr_offset(cache.address)  # noqa: F821
    random = kdbg.freeptr_random(cache.address)  # noqa: F821
    # A kernel without `CONFIG_SLAB_FREELIST_HARDENED` has no `random`
    # member and reads 0, *not* `None`.  Testing `random is not None`
    # would therefore print the arithmetic section on an unhardened
    # kernel, where `stored` is the next pointer verbatim and the XOR
    # line would be a tautology dressed up as a derivation.
    hardened = bool(random)

    _section(f"{cache_name}: geometry and key")
    # `page_bytes` is sizeof(struct page), not PAGE_SIZE -- a metric that
    # names itself honestly is the reason `head_to_page()` arithmetic can
    # be checked by eye below.
    gdb.write(
        f"cache       : {cache.address:#x}\n"
        f"object size : {cache.size} bytes\n"
        f"objects/slab: {cache.oo_objects}  (order {cache.oo_order})\n"
        f"page slot   : {kdbg.page_bytes()} bytes (sizeof(struct page))\n"  # noqa: F821
    )
    template = kdbg.cpu_slab_ptr(cache.address)  # noqa: F821
    gdb.write(
        f"cpu_slab    : {template:#x} (__percpu template)\n" if template
        else "cpu_slab    : (none)\n"
    )
    gdb.write(
        f"freeptr     : offset={offset}  random={random:#x}  "
        f"({'hardened' if hardened else 'not hardened'})\n"
    )

    top = kdbg.cpu_freelist(cache.address, cpu)  # noqa: F821
    if not top:
        gdb.write(f"\ncpu {cpu}: freelist is empty (all objects allocated)\n")
        return

    slot = int(top) + int(offset or 0)
    stored = kdbg.u64(f"*(unsigned long *){slot:#x}")  # noqa: F821
    if stored is None:
        gdb.write(f"\ncpu {cpu}: slot {slot:#x} is unreadable\n")
        return

    decoded = kdbg.decode_freeptr(stored, random, slot)  # noqa: F821
    gdb.write(
        f"\ncpu {cpu} first object : {int(top):#x}\n"
        f"  slot address   : {slot:#x}   (object + offset {offset})\n"
        f"  stored word    : {stored:#018x}\n"
        f"  decoded next   : {decoded:#018x}\n"
    )
    if hardened:
        # Showing the arithmetic is what makes the formula believable.
        swab = int.from_bytes(slot.to_bytes(8, "little"), "big")
        gdb.write(
            f"  the arithmetic : {decoded:#x} ^ {random:#x} ^ "
            f"swab({slot:#x}) = {stored:#x}\n"
            f"  check          : {decoded ^ random ^ swab:#x}\n"
        )
    else:
        gdb.write(
            "  (not hardened: `stored` is the next pointer verbatim, so\n"
            "   there is no arithmetic to verify here)\n"
        )


def walk(cache_name: str, cpu: int, limit: int) -> None:
    """Follow the whole chain, and stop when it stops making sense.

    The two stop conditions are the interesting part: a decoded pointer
    outside the slab, and a chain longer than the slab has objects.  Both
    mean the offset or the key is wrong, and continuing would print a
    convincing list of garbage.
    """
    cache = kdbg.slab_cache(cache_name)  # noqa: F821
    if cache is None:
        return
    offset = kdbg.freeptr_offset(cache.address)  # noqa: F821
    random = kdbg.freeptr_random(cache.address)  # noqa: F821
    top = kdbg.cpu_freelist(cache.address, cpu)  # noqa: F821

    _section(f"{cache_name} cpu {cpu}: the chain")
    if not top or offset is None:
        gdb.write("-- nothing to walk\n")
        return

    # The slab this object belongs to.  Asking the kernel is more
    # reliable than deriving it from the address: `cpu_active_slab` is
    # the slab the CPU is allocating from, which is by definition the one
    # this freelist belongs to.  Read it once, not per link.
    head = kdbg.cpu_active_slab(cache.address, cpu)  # noqa: F821
    head = int(head) if head else 0
    objects = 0
    if head:
        counters = kdbg.slab_counters(head)  # noqa: F821
        if counters is not None:
            objects = counters[1]

    current = int(top)
    seen: set[int] = set()
    for depth in range(limit):
        gdb.write(f"  [{depth:2d}] {current:#018x}")
        if current in seen:
            gdb.write("   <- cycle, stopping\n")
            return
        seen.add(current)

        # A chain longer than the slab has objects means the key or the
        # slot is wrong: the kernel cannot hand out more links than it
        # stores objects.  This is the condition that catches a corrupted
        # freelist which still points at readable slab memory.
        if objects and depth >= objects:
            gdb.write(
                f"   <- longer than the slab ({objects} objects), "
                "stopping\n"
            )
            return

        if head:
            located = kdbg.object_index(head, current, cache.address)  # noqa: F821
            if located is not None:
                index, _ = located
                gdb.write(f"        object {index} of {objects}")
        gdb.write("\n")

        slot = current + int(offset)
        stored = kdbg.u64(f"*(unsigned long *){slot:#x}")  # noqa: F821
        if stored is None:
            gdb.write("        slot unreadable, stopping\n")
            return
        nxt = kdbg.decode_freeptr(stored, random, slot)  # noqa: F821
        if nxt == 0:
            gdb.write("        end of chain (NULL)\n")
            return
        resolved = kdbg.slab_object(nxt)  # noqa: F821
        if resolved is None:
            gdb.write(
                f"        decoded {nxt:#x} is not a slab object -- "
                "wrong offset or key, stopping\n"
            )
            return
        # `slab_object` also answers *which* cache the target belongs to.
        # The link is only meaningful if it points back into this one: a
        # faithful decode of a stale link can land on a different
        # cache's slab and still pass the is-it-a-slab check above.
        if resolved[1].address != cache.address:
            gdb.write(
                f"        decoded {nxt:#x} belongs to "
                f"{resolved[1].name}, not {cache.name} -- stopping\n"
            )
            return
        current = nxt

    gdb.write(f"  ... stopped at --limit {limit}\n")


def head_chain(obj: int, head: int) -> None:
    """Show why the slab head is not the page the object sits on.

    An order-2 slab spans four pages.  `head_to_page()` translates the
    object's address to the `struct page` that *contains* it, but only
    the first page of the block carries the slab -- the rest are tail
    pages whose `counters` word reads as zero.  `compound_head()`
    performs the walk back to the first page.

    This is the bug that produced ``object 3 of 0`` in the draft of this
    example: the index was right because the arithmetic is relative to
    the page passed in, but the object count was read from a tail page.
    """
    _section("the page that contains the object is not the slab head")
    page = kdbg.head_to_page(obj)  # noqa: F821
    if page is None:
        gdb.write("-- head_to_page could not translate the address\n")
        return
    page = int(page)
    compound = int(kdbg.compound_head(page))  # noqa: F821
    gdb.write(
        f"object      : {obj:#x}\n"
        f"its page    : {page:#x}\n"
        f"compound    : {compound:#x}\n"
        f"cpu slab    : {head:#x}\n"
    )
    for label, candidate in (("its page", page), ("compound", compound)):
        counters = kdbg.slab_counters(candidate)  # noqa: F821
        if counters is None:
            gdb.write(f"{label:12}: counters unreadable\n")
            continue
        inuse, objects, frozen = counters
        gdb.write(
            f"{label:12}: inuse={inuse:<3} objects={objects:<3} "
            f"frozen={frozen}  -> {kdbg.slab_state(candidate)}\n"  # noqa: F821
        )
    if compound == page:
        gdb.write(
            "\nThis slab starts on the page the object sits on, so the two\n"
            "agree -- for an order-0 slab they always do.  The bug only\n"
            "shows up once a slab spans several pages.\n"
        )
    else:
        gdb.write(
            "\nReading `counters` from the object's own page gives zeros:\n"
            "it is a tail page, not the slab.  The count is only valid on\n"
            "the compound head.\n"
        )


def partial_side(cache_address: int, cpu: int, top: int) -> None:
    """The depth of a free object in its chain, and the partial list.

    `freelist_dist()` answers "how far down is this object?" without
    re-implementing the decode loop, and `in_partial()` answers the
    question a report cannot: is this slab waiting for reuse on a node
    list, or is it only on the per-CPU freelist?
    """
    _section("chain depth and the partial list")
    # `freeptr_random()` has no ``None`` case to check: on a kernel built
    # without ``CONFIG_SLAB_FREELIST_HARDENED`` the keyword does not exist
    # and the key is 0, which `decode_freeptr()` already treats as "no
    # XOR".  So `offset` is the only thing that can be missing here.
    second = None
    if top:
        offset = kdbg.freeptr_offset(cache_address)  # noqa: F821
        random = kdbg.freeptr_random(cache_address)  # noqa: F821
        if offset is not None:
            slot = top + offset
            raw = kdbg.u64(f"*(unsigned long *){slot:#x}")  # noqa: F821
            if raw is not None:
                second = int(kdbg.decode_freeptr(raw, random, slot))  # noqa: F821
                if not second:
                    second = None
    if second:
        depth = kdbg.freelist_dist(cache_address, second, top)  # noqa: F821
        gdb.write(
            f"cpu {cpu} head     : {top:#x}  depth 0 by definition\n"
            f"its successor   : {second:#x}  depth {depth}\n"
        )
    else:
        gdb.write(f"cpu {cpu} freelist holds at most one object\n")

    node_id = 0
    count, node_ptr, first_page, first_free = kdbg.partial_info(  # noqa: F821
        cache_address, node_id
    )
    if node_ptr is None:
        gdb.write(f"node {node_id}        : (no kmem_cache_node)\n")
        return
    gdb.write(
        f"node {node_id}        : {node_ptr:#x}\n"
        f"partial slabs   : {count}\n"
    )
    if first_page is None:
        gdb.write("-- nothing on the partial list; every slab is either\n"
                  "   frozen on a CPU or full\n")
        return
    gdb.write(
        f"first slab      : {first_page:#x}\n"
        f"on the list     : {kdbg.in_partial(cache_address, first_page, node_id)}\n"  # noqa: F821
    )
    if first_free:
        gdb.write(f"its freelist    : {int(first_free):#x}\n")


def neighbours(cache_name: str, cpu: int) -> None:
    """The objects either side of the first free one.

    This is what makes the "interior pointer" case concrete: a dangling
    pointer into the middle of an object still resolves to *this* slab,
    and the neighbours are how a tracer says which object was hit.
    """
    cache = kdbg.slab_cache(cache_name)  # noqa: F821
    if cache is None:
        return
    top = kdbg.cpu_freelist(cache.address, cpu)  # noqa: F821
    if not top:
        return

    _section(f"{cache_name} cpu {cpu}: neighbourhood of the first free object")
    # `cpu_active_slab` is the slab the CPU is allocating from -- the same
    # one the freelist belongs to.  Deriving the page from the object
    # address instead gives a `struct page` whose counters read as zero,
    # because a compound slab's head is not the page the object sits on.
    head = kdbg.cpu_active_slab(cache.address, cpu)  # noqa: F821
    if not head:
        gdb.write("-- the CPU reports no active slab\n")
        return
    head = int(head)
    located = kdbg.object_index(head, int(top), cache.address)  # noqa: F821
    if located is None:
        gdb.write("-- object_index returned None (layout mismatch?)\n")
        return
    index, objects = located
    previous, following = kdbg.neighbour_objects(  # noqa: F821
        cache.address, int(top), head
    )
    gdb.write(
        f"cache name: {kdbg.cache_name(cache.address)}\n"  # noqa: F821
        f"slab head : {head:#x}\n"
        f"object    : {int(top):#x}  ({index} of {objects})\n"
    )
    if previous is None:
        gdb.write("previous  : (none, first in slab)\n")
    else:
        gdb.write(f"previous  : {previous:#x}\n")
    if following is None:
        gdb.write("following : (none, last in slab)\n")
    else:
        gdb.write(f"following : {following:#x}\n")
    counters = kdbg.slab_counters(head)  # noqa: F821
    gdb.write(f"slab state: {kdbg.slab_state(head)}\n")  # noqa: F821
    if counters is not None:
        inuse, total, frozen = counters
        gdb.write(f"counters  : inuse={inuse} objects={total} frozen={frozen}\n")

    # The same slab through the library's own renderer.  Note the
    # argument: an *object* address, not a `struct page` -- `print_slab`
    # does the `head_to_page` + `compound_head` walk internally, which is
    # exactly the step this example spelled out by hand above.
    _section(f"{cache_name}: the same slab, rendered by the library")
    kdbg.print_slab(int(top))  # noqa: F821


def freelist_walk(cache_name: str, cpu: int | None, limit: int) -> None:
    """Run the whole tour."""
    gdb.write("--- SLUB freelist: the encoding, not just the report ---\n")
    gdb.execute("kl-base")
    report_hardening()

    # `nr_cpus()` returns -1 when `nr_cpu_ids` is unreadable, and
    # `range(-1)` is empty -- so a failed read used to skip every chain
    # *and* index `cpus[0]`.  Treat it as unknown and fall back to CPU 0.
    total = kdbg.nr_cpus()  # noqa: F821
    if total <= 0:
        gdb.write(
            "\n-- nr_cpu_ids unreadable; assuming a single CPU.  Every\n"
            "   chain below may be incomplete.\n"
        )
        total = 1
    cpus = [cpu] if cpu is not None else list(range(total))

    cache = kdbg.slab_cache(cache_name)  # noqa: F821
    if cache is None:
        _section(f"{cache_name} is absent")
        gdb.write("-- no such cache on this kernel\n")
        return

    decode_one(cache_name, cpus[0])
    for index in cpus:
        walk(cache_name, index, limit)
    neighbours(cache_name, cpus[0])

    top = kdbg.cpu_freelist(cache.address, cpus[0])  # noqa: F821
    head = kdbg.cpu_active_slab(cache.address, cpus[0])  # noqa: F821
    if top and head:
        head_chain(int(top), int(head))
    if top:
        partial_side(cache.address, cpus[0], int(top))

    _section("reading the result")
    gdb.write(
        "The stored word and the decoded pointer are the same memory read.\n"
        "If the decoded value is not a slab address, either `offset` or\n"
        "`random` is wrong for this cache -- and the walk above stops\n"
        "rather than printing a convincing chain of garbage.  That stop is\n"
        "the difference between a tracer and a plausible-looking one.\n\n"
        "If `INIT_ON_FREE_DEFAULT_ON` above is not `n`, the chain is\n"
        "zeroed on free and there is nothing to follow: that is not a bug\n"
        "in the walk, it is the hardening working.\n"
    )


class FreelistWalkCommand(gdb.Command):
    """flwalk [cache] [-c CPU] [--limit N] -- follow a SLUB freelist."""

    def __init__(self) -> None:
        super().__init__("flwalk", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="flwalk", add_help=False)
        parser.add_argument("cache", nargs="?", default="kmalloc-1k")
        parser.add_argument("-c", "--cpu", type=int, default=None)
        parser.add_argument("--limit", type=int, default=8)
        try:
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: flwalk [cache] [-c CPU] [--limit N]\n")
            return
        freelist_walk(args.cache, args.cpu, args.limit)


_FLWALK = FreelistWalkCommand()

gdb.write(
    "freelist_walk: run 'flwalk' to follow kmalloc-1k's chain, "
    "'flwalk <cache>' for another\n"
)