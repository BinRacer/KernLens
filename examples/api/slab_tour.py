#!/usr/bin/env python3
#
# ruff: noqa: F821
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Read allocator state from the cache down to one object.

A slab report is easy to print and easy to misread.  The numbers in it
come from three different places -- the cache descriptor, the per-CPU
slab, and the page flags -- and the interesting failures happen when
those three disagree.  This example walks that hierarchy deliberately,
one level at a time:

1. `kl-slab list kmalloc` -- which caches exist, and their geometry.
   `Objs` and `Obj Size` are what tell you a cache's object count is not
   `slab size / object size`: the metadata lives inside the object.
2. `kl-slab info <cache> -v` -- one cache in full.  Read the freelist
   pointers against the `Offset` field: on a hardened kernel the word at
   `Offset` is *encoded*, so it will not look like a heap address.
3. `kl-slab contains <addr>` -- which cache owns an address.  This is
   the step that matters for a use-after-free: given a dangling pointer,
   this says whether it still resolves to a live slab.
4. `kl-buddy list -o N` -- the page allocator underneath.  A slab is a
   buddy allocation, so `nr_free` at this order bounds how many new
   slabs the cache can get.
5. `kl-buddy info <addr>` -- one page, classified.

Source it after `gdbinit.py` and run `stour`::

    (gdb) source /path/to/KernLens/gdbinit.py
    (gdb) source /path/to/KernLens/examples/api/slab_tour.py
    (gdb) stour                       # kmalloc-1k, CPU 0
    (gdb) stour kmalloc-512
    (gdb) stour kmalloc-32 -c 1

The last section prints one object's neighbours using the SLUB model
rather than a hexdump, which is the difference between "here are bytes"
and "here is the object before and after it".
"""

from __future__ import annotations

import argparse
import shlex

try:
    import gdb
except ImportError as exc:  # pragma: no cover - GDB only
    raise SystemExit("slab_tour.py must be sourced by GDB") from exc


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
    gdb.write(f"\n=== {title} " + "=" * max(0, 58 - len(title)) + "\n")


def _run(command: str) -> None:
    gdb.write(f"-- {command}\n")
    gdb.execute(command)


def _cache(name: str) -> object | None:
    """The `SlabCache` descriptor for ``name``, or None.

    `slab_cache` returns a `SlabCache` record -- with `address`,
    `oo_order`, `size` and the usercopy window already parsed -- rather
    than a bare address.  Every `SlubInspector` method below then wants
    `cache.address`, which is the shape difference worth noticing: the
    inspector takes raw addresses because it works on captured dumps
    too, while the report keeps the parsed form.

    It returns None rather than raising for an unknown name, which is
    the behaviour a tracer wants: a cache that is not compiled in is
    normal, not an error.
    """
    return kdbg.slab_cache(name)  # noqa: F821


def _slab_order(cache: object) -> int:
    """The buddy order one slab of this cache occupies.

    Read from the descriptor rather than hard-coded: the order is a
    function of object size, so `kmalloc-1k` is order 2 and
    `kmalloc-32` is order 0, and a table of those would go stale.
    """
    return int(cache.oo_order)


def _a_free_object(cache: int, cpu: int) -> int | None:
    """One address from the cache's per-CPU freelist, if there is one.

    This is what makes the later steps concrete: `kl-slab contains` and
    the neighbour listing both need an address that really belongs to
    this cache, and inventing one would produce a confident wrong answer.

    Note the signature: every `SlubInspector` method takes the cache as a
    *`kmem_cache` address*, not as a name, and the per-CPU ones take a
    CPU index as well.  Passing the name is the mistake this example is
    written to avoid.
    """
    head = kdbg.cpu_freelist(cache, cpu)  # noqa: F821
    return int(head) if head else None


def tour(name: str, cpu: int) -> None:
    """Walk from the cache list down to a single object."""
    # Every one of these commands resolves symbols, so the slide has to
    # be set first or the addresses will be link-time ones.
    _run("kl-base")

    _section("1. which caches exist (kl-slab list)")
    _run(f"kl-slab list {name.split('-')[0]}")

    _section(f"2. one cache in full (kl-slab info {name} -v)")
    _run(f"kl-slab info {name} -v -c {cpu}")

    cache = _cache(name)
    if cache is None:
        _section("3. the cache is absent")
        gdb.write(
            f"-- {name} is not present on this kernel; the rest of the\n"
            "   tour needs a live cache.  Try `stour kmalloc-1k`.\n"
        )
        return

    _section("3. cache geometry, from the API rather than the report")
    _run(f"kl-slab info {name} -i -r --ctor --reclaim")

    example = _a_free_object(cache.address, cpu)
    if example is None:
        gdb.write(
            "-- no per-CPU freelist entry on this CPU; the cache is full.\n"
            "   `kl-slab contains` needs an object address, so that step is\n"
            "   skipped rather than given a guessed one.\n"
        )
    else:
        _section(f"4. which cache owns {example:#x} (kl-slab contains)")
        _run(f"kl-slab contains {example:#x}")

        _section("5. that object, in SLUB terms (kl-slab details)")
        _run(f"kl-slab details {example:#x} -c {cpu}")

    _section("6. the buddy allocator underneath (kl-buddy list)")
    # A slab is a buddy allocation, so the order matters: the cache's
    # `oo_order` field said which one, and reading it beats guessing.
    order = _slab_order(cache)
    _run(f"kl-buddy list -o {order}")

    _section("7. one page, classified (kl-buddy info)")
    if example is not None:
        _run(f"kl-buddy info {example:#x}")
    else:
        gdb.write("-- skipped: no object address from step 3.\n")

    _section("reading the result")
    gdb.write(
        "The freelist pointers in step 2 are the thing to look at twice.\n"
        "`Offset` says where in the object the freelist word lives, and on\n"
        "this kernel `CONFIG_SLAB_FREELIST_HARDENED=y` means that word is\n"
        "`ptr ^ key ^ swab(address)` rather than a plain pointer.  A value\n"
        "there that does not resemble a heap address is therefore expected,\n"
        "not evidence of corruption -- `kdbg.decode_freeptr()` is how to\n"
        "check, and `examples/api/freelist_walk.py` is the follow-up.\n"
    )


class SlabTourCommand(gdb.Command):
    """stour [cache] [-c CPU] -- allocator state, cache to object."""

    def __init__(self) -> None:
        super().__init__("stour", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        parser = argparse.ArgumentParser(prog="stour", add_help=False)
        parser.add_argument("cache", nargs="?", default="kmalloc-1k")
        parser.add_argument("-c", "--cpu", type=int, default=0)
        try:
            args = parser.parse_args(shlex.split(arg))
        except SystemExit:
            gdb.write("usage: stour [cache] [-c CPU]\n")
            return
        tour(args.cache, args.cpu)


_STOUR = SlabTourCommand()

gdb.write(
    "slab_tour: run 'stour' for kmalloc-1k on CPU 0, "
    "'stour <cache> -c N' for another\n"
)