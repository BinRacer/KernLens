#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Verified fallback struct layouts for kernels without debug info.

The inspectors resolve every field offset from the running kernel through
a three-tier chain:

1. the loaded ``vmlinux``'s **DWARF** (exact for the build at hand);
2. the image's embedded **BTF** (``CONFIG_DEBUG_INFO_BTF``), read by
   :mod:`kernlens.gdb.btf`;
3. the **table here** -- only when neither is available, for a stripped
   ``vmlinux`` or a remote target with no symbol file.

That last tier is why this module exists.  It is **not** a substitute for
DWARF or BTF: these values were read from a real ``vmlinux`` (x86_64),
and struct layouts depend on far more than the kernel version --
``CONFIG_*`` options add or remove members (``CONFIG_SECURITY`` inserts
``void *security`` ahead of ``enum bpf_map_type map_type``), so a table
entry can be silently wrong for another build of the *same* version.
When a fallback is used the command layer prints a warning telling the
user to prefer DWARF.

Each entry records where the struct is defined and which version the
values were verified against, so the table can be regenerated and
audited (``tools/gen_layouts.py``).  Field offsets were read from the
``.BTF`` of :data:`VERIFIED_KERNEL`, with ``CONFIG_SECURITY=y``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

#: The kernels the table's numbers were read from.  Every band records
#: which probe produced it, because a value nobody measured is a guess.
VERIFIED_KERNEL = (
    "Linux 6.1.134 (x86_64, this project's test VM, DWARF) and "
    "Linux 7.0.0-38-generic (x86_64, CONFIG_SECURITY=y, host BTF)"
)

#: ``CONFIG_*`` predicate: ``"y"`` requires the option set, ``"n"``
#: requires it unset, anything else must match the value exactly.
Feature = tuple[str, str]

#: A kernel version, as a tuple of integers (``(6, 1, 134)``).
Version = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StructVariant:
    """One ``CONFIG_*``/version-gated layout of a struct."""

    note: str
    fields: Mapping[str, int]
    #: Optional ``CONFIG_*`` predicates the build must satisfy.
    config: tuple[Feature, ...] = ()
    #: Optional inclusive lower/upper bound on the kernel version.
    version_min: Version | None = None
    version_max: Version | None = None
    #: Optional ``sizeof`` for this band, when the struct's size moved.
    #: A variant that declares any size makes the bands authoritative
    #: for that name, so a release no band covers gets no answer instead
    #: of the neighbouring band's (see :meth:`StructLayout.resolved_size`).
    sizes: Mapping[str, int] = field(default_factory=dict)

    def matches(
        self, version: Version | None, config: Mapping[str, str] | None,
    ) -> bool:
        """Whether this variant applies to *version* + *config*.

        ``None`` means "unknown" for either input, in which case that
        dimension is not gated: an unreadable ``.config`` must not be
        treated as every option being *disabled*.
        """
        if version is not None:
            if self.version_min is not None and version < self.version_min:
                return False
            if self.version_max is not None and version >= self.version_max:
                return False
        if config is None:
            return True
        for name, expected in self.config:
            enabled = config.get(name) == "y"
            if expected == "y" and not enabled:
                return False
            if expected == "n" and enabled:
                return False
            if expected not in ("y", "n") and config.get(name) != expected:
                return False
        return True


@dataclass(frozen=True, slots=True)
class StructLayout:
    """All known variants of one kernel struct."""

    type_name: str
    origin_version: str
    origin_path: str
    variants: tuple[StructVariant, ...]
    #: ``sizeof`` in bytes, when the inspectors need it.
    sizes: Mapping[str, int] = field(default_factory=dict)

    def field(self, path: str) -> int | None:
        """Return the first variant's offset for *path*, or ``None``."""
        for variant in self.variants:
            if path in variant.fields:
                return variant.fields[path]
        return None

    def resolved_field(
        self, path: str, version: Version | None,
        config: Mapping[str, str] | None,
    ) -> int | None:
        """Return *path*'s offset for the first matching variant."""
        for variant in self.variants:
            if path in variant.fields and variant.matches(version, config):
                return variant.fields[path]
        return None

    def resolved_size(
        self, name: str, version: Version | None,
        config: Mapping[str, str] | None,
    ) -> int | None:
        """Return a named ``sizeof`` for the matching band, or ``None``.

        Two storage styles, and the precedence matters.  When no variant
        declares a size, the layout-level :attr:`sizes` map is the whole
        answer (it is unversioned, which is fine for a struct whose size
        never moved).  As soon as one variant declares sizes, the bands
        own that name: only a *matching* band answers, and an uncovered
        release yields ``None`` rather than the neighbouring band's
        number -- a wrong stride is worse than a missing one.
        """
        declaring = [v for v in self.variants if name in v.sizes]
        if not declaring:
            return self.sizes.get(name)
        for variant in declaring:
            if variant.matches(version, config):
                return variant.sizes[name]
        return None


# ---------------------------------------------------------------------
# The verified tables (x86_64, read from the BTF of VERIFIED_KERNEL).
# ---------------------------------------------------------------------

_LAYOUTS: tuple[StructLayout, ...] = (
    StructLayout(
        type_name="struct kmem_cache",
        origin_version="v2.6.23",
        origin_path="mm/slab.h / mm/slub.h",
        variants=(
            StructVariant(
                note=(
                    "7.0 probe (host BTF).  `cpu_slab` is GONE: 6.18 and "
                    "6.19 still carried it at +0 (next to the new "
                    "`cpu_sheaves`), and 7.0 dropped it.  `node[]` became "
                    "`per_node[]` in 7.1, past every field here."
                ),
                version_min=(7, 0),
                fields={
                    "name": 0x58,
                    "size": 0x18,
                    "object_size": 0x1C,
                    "offset": 0x28,
                    "oo": 0x30,
                    "align": 0x4C,
                    "flags": 0x08,
                    "list": 0x60,
                },
            ),
            StructVariant(
                note=(
                    "NOT probed -- 6.18/6.19 kept `cpu_slab` at +0 and "
                    "inserted `lock_key` plus `sheaf_capacity` before "
                    "`oo`, so every offset below differs from 7.0's.  "
                    "Only `cpu_slab` (the slot slub.py reads) is claimed "
                    "here; derive the rest with `abi_ranges.py` and pin "
                    "them with `gen_layouts.py --vmlinux` on a 6.18 "
                    "kernel before adding them."
                ),
                version_min=(6, 18),
                version_max=(7, 0),
                fields={
                    "cpu_slab": 0x00,
                },
            ),
            StructVariant(
                note=(
                    "6.1.134 probe (DWARF).  One band covers 5.19-6.17: "
                    "6.12 only moved the definition from slub_def.h to "
                    "mm/slab.h.  `cpu_slab` is the first member -- the "
                    "slot slub.py reads to reach the per-CPU area -- up "
                    "to and including 6.19; 7.0 removed it.  The earlier "
                    "releases also had `max` after `oo`; that is past "
                    "every field here."
                ),
                version_min=(5, 19),
                version_max=(6, 18),
                fields={
                    "cpu_slab": 0x00,
                    "name": 0x60,
                    "size": 0x18,
                    "object_size": 0x1C,
                    "offset": 0x28,
                    "oo": 0x34,
                    "align": 0x54,
                    "flags": 0x08,
                    "list": 0x68,
                },
            ),
            StructVariant(
                note=(
                    "Pre-5.9 layout: no `reciprocal_size`, so everything "
                    "from `offset` on sits one word earlier.  NOT probed "
                    "-- derived from the member order in this project's "
                    "linux-stable clone (`tools/abi_ranges.py`), which "
                    "shows `reciprocal_size` appears at 5.9.  "
                    "`cpu_slab` is the first member throughout.  "
                    "Verify with `gen_layouts.py --vmlinux` before "
                    "trusting it."
                ),
                version_max=(5, 9),
                fields={
                    "cpu_slab": 0x00,
                    "name": 0x58,
                    "size": 0x18,
                    "object_size": 0x1C,
                    "offset": 0x20,
                    "oo": 0x2C,
                    "align": 0x4C,
                    "flags": 0x08,
                    "list": 0x60,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct kmem_cache_node",
        origin_version="v3.10",
        origin_path="mm/slab.h (moved to mm/slub.c at v6.8)",
        variants=(
            StructVariant(
                note=(
                    "The SLUB branch of the dual CONFIG_SLAB/CONFIG_SLUB "
                    "definition: `spinlock_t list_lock` then `nr_partial` "
                    "and `partial`.  Verified on 6.1.134 (DWARF: "
                    "nr_partial +0x8, partial +0x10) and on 7.0 (host BTF: "
                    "same two offsets, with `barn` appended at v6.18).  "
                    "`partial` is what slub.py walks, so a missing row "
                    "here used to leave a no-debug-info build with no "
                    "answer at all."
                ),
                config=(("CONFIG_SLUB", "y"),),
                fields={
                    "nr_partial": 0x08,
                    "partial": 0x10,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct kmem_cache_cpu",
        origin_version="v3.6",
        origin_path=(
            "include/linux/slub_def.h (moved to mm/slub.c at v6.8; "
            "removed at v7.0 in favour of struct slub_percpu_sheaves)"
        ),
        variants=(
            StructVariant(
                note=(
                    "6.1.134 probe (DWARF).  `slab` and `freelist` have "
                    "sat at +0x10 and +0 throughout 5.17-6.19: the v6.5 "
                    "`freelist_tid` union and the v6.19 anonymous "
                    "`struct freelist_tid` both leave the pair where it "
                    "was, and 6.18 only widens `lock`."
                ),
                version_min=(5, 17),
                version_max=(6, 8),
                fields={
                    "freelist": 0x00,
                    "tid": 0x08,
                    "slab": 0x10,
                },
            ),
            StructVariant(
                note=(
                    "Same slots after the definition moved from "
                    "slub_def.h to mm/slub.c (v6.8); 6.5 added the "
                    "`freelist_tid` union over `freelist`/`tid`, and 6.5 "
                    "added `freelist_tid` again as a named member in 6.19.  "
                    "NOT probed on a 6.8-6.19 kernel -- derived from the "
                    "member lists in this project's linux-stable clone."
                ),
                version_min=(6, 8),
                version_max=(6, 20),
                fields={
                    "freelist": 0x00,
                    "tid": 0x08,
                    "slab": 0x10,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct bpf_map",
        origin_version="v3.18",
        origin_path="include/linux/bpf.h",
        variants=(
            StructVariant(
                note=(
                    "CONFIG_SECURITY adds `security` at +0x38; 6.x adds "
                    "`record`, BPF token `sha`.  Offsets are 6.x-only."
                ),
                config=(("CONFIG_SECURITY", "y"),),
                fields={
                    "map_type": 0x40,
                    "key_size": 0x44,
                    "value_size": 0x48,
                    "max_entries": 0x4C,
                },
            ),
            StructVariant(
                note="no LSM pointer (CONFIG_SECURITY=n)",
                config=(("CONFIG_SECURITY", "n"),),
                fields={
                    "map_type": 0x38,
                    "key_size": 0x3C,
                    "value_size": 0x40,
                    "max_entries": 0x44,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct bpf_prog",
        origin_version="v3.18",
        origin_path="include/linux/filter.h",
        variants=(
            StructVariant(
                note=(
                    "packed bitfields then type/expected_attach_type/len; "
                    "6.8 with CONFIG_CFI adds a func_stats block"
                ),
                fields={
                    "type": 0x04,
                    "expected_attach_type": 0x08,
                    "len": 0x0C,
                    "jited_len": 0x10,
                    "bpf_func": 0x48,
                    "aux": 0x50,
                    "insns": 0x60,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct dma_buf",
        origin_version="v3.3",
        origin_path="include/linux/dma-buf.h",
        variants=(
            StructVariant(
                note=(
                    "`name_lock` (6.1) and the BPF token `sha` block push "
                    "`priv` from 0x90 (5.x) to 0x70 here"
                ),
                fields={
                    "size": 0x00,
                    "file": 0x08,
                    "exp_name": 0x40,
                    "name": 0x48,
                    "owner": 0x58,
                    "list_node": 0x60,
                    "priv": 0x70,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct page",
        origin_version="v2.6.0",
        origin_path="include/linux/mm_types.h",
        variants=(
            StructVariant(
                note="x86_64: lru shares the compound_head union word",
                fields={
                    "lru": 0x08,
                    "compound_head": 0x08,
                    "_mapcount": 0x30,
                    "_refcount": 0x34,
                },
            ),
        ),
        sizes={"struct page": 0x40},
    ),
    StructLayout(
        type_name="struct slab",
        origin_version="v5.17",
        origin_path="mm/slab.h",
        variants=(
            StructVariant(
                note=(
                    "7.0 probe (host BTF): `slab_cache` moved to +0x8 "
                    "when the union was reordered at 6.2.  The 6.5-6.9 "
                    "`freelist_counter` union and 6.10's `__page_type` "
                    "rename do not move any field read here, and the "
                    "struct ended up 0x40 from 6.10."
                ),
                version_min=(6, 2),
                fields={
                    "slab_cache": 0x08,
                    "slab_list": 0x10,
                    "freelist": 0x20,
                    "counters": 0x28,
                },
            ),
            StructVariant(
                note=(
                    "6.1.134 probe (DWARF): `slab_list` is the first "
                    "union word, so `slab_cache` is the third (+0x18).  "
                    "Spans 5.17-6.1; the struct does not exist before "
                    "5.17."
                ),
                version_max=(6, 2),
                fields={
                    "slab_cache": 0x18,
                    "slab_list": 0x08,
                    "freelist": 0x20,
                    "counters": 0x28,
                },
            ),
        ),
        sizes={"struct slab": 0x40},
    ),
    StructLayout(
        type_name="struct zone",
        origin_version="v2.6.0",
        origin_path="include/linux/mmzone.h",
        variants=(
            StructVariant(
                note=(
                    "7.0 probe (host BTF): a larger page-set/compact block "
                    "before the (unchanged) +0x100 `free_area` grows the "
                    "struct to 0x6c0.  Also the value used for 6.4-6.18, "
                    "because the size was not probed per release -- "
                    "re-verify with `gen_layouts.py --vmlinux` if a "
                    "6.4-6.12 kernel relies on it."
                ),
                version_min=(6, 4),
                fields={"free_area": 0x100},
                sizes={"struct zone": 0x6C0},
            ),
            StructVariant(
                note=(
                    "6.1.134 probe (DWARF), and the size the buddy walk "
                    "strides by: `free_area` is at +0x100 and the struct "
                    "is 0x600.  The layout between the watermarks and "
                    "`free_area` changed at 6.4 (compact controls) but "
                    "`free_area` did not move.  5.14 is the lower bound "
                    "because that release renamed `pageset` to "
                    "`per_cpu_pageset` + `per_cpu_zonestats`; the member "
                    "list is byte-identical from 5.14 to 6.3 "
                    "(`tools/abi_ranges.py`)."
                ),
                version_min=(5, 14),
                version_max=(6, 4),
                fields={"free_area": 0x100},
                sizes={"struct zone": 0x600},
            ),
        ),
    ),
    StructLayout(
        type_name="struct printk_ringbuffer",
        origin_version="v5.10",
        origin_path="kernel/printk/printk_ringbuffer.h",
        variants=(
            StructVariant(
                note="desc_ring then text_data_ring; offsets absolute in the struct",
                fields={
                    "desc_ring.count_bits": 0x00,
                    "desc_ring.descs": 0x08,
                    "desc_ring.infos": 0x10,
                    "desc_ring.head_id": 0x18,
                    "desc_ring.tail_id": 0x20,
                    "text_data_ring.size_bits": 0x30,
                    "text_data_ring.data": 0x38,
                },
            ),
        ),
        sizes={"struct printk_ringbuffer": 0x58},
    ),
    StructLayout(
        type_name="struct prb_desc",
        origin_version="v5.10",
        origin_path="kernel/printk/printk_ringbuffer.h",
        variants=(
            StructVariant(
                note="atomic_long state_var then a text_blk_lpos struct",
                fields={
                    "state_var": 0x00,
                    "text_blk_lpos.begin": 0x08,
                    "text_blk_lpos.next": 0x10,
                },
            ),
        ),
        sizes={"struct prb_desc": 0x18},
    ),
    StructLayout(
        type_name="struct printk_info",
        origin_version="v5.10",
        origin_path="kernel/printk/printk_ringbuffer.h",
        variants=(
            StructVariant(
                note="text_len is a u16; 6.x grows 0x58 -> 0x70 with dev_info",
                fields={
                    "seq": 0x00,
                    "ts_nsec": 0x08,
                    "text_len": 0x10,
                },
            ),
        ),
        sizes={"struct printk_info": 0x70},
    ),
    StructLayout(
        type_name="struct xarray",
        origin_version="v4.17",
        origin_path="lib/xarray.c / include/linux/xarray.h",
        variants=(
            StructVariant(
                note=(
                    "xa_head is the only pointer; xa_lock/xa_flags precede "
                    "it, so the head is never at offset 0"
                ),
                fields={
                    "xa_head": 0x08,
                },
            ),
        ),
        sizes={"struct xarray": 0x10},
    ),
    StructLayout(
        type_name="struct idr",
        origin_version="v4.17",
        origin_path="lib/idr.c / include/linux/idr.h",
        variants=(
            StructVariant(
                note=(
                    "idr_rt is an embedded struct xarray, so xa_head is "
                    "reachable only through it; idr_base/idr_next follow"
                ),
                fields={
                    "idr_rt.xa_head": 0x08,
                    "idr_base": 0x10,
                    "idr_next": 0x14,
                },
            ),
        ),
        sizes={"struct idr": 0x18},
    ),
    StructLayout(
        type_name="struct xa_node",
        origin_version="v4.17",
        origin_path="lib/xarray.c / include/linux/xarray.h",
        variants=(
            StructVariant(
                note="u8 shift + offset + u16 count, slots start at 0x28",
                fields={
                    "shift": 0x00,
                    "count": 0x02,
                    "slots": 0x28,
                },
            ),
        ),
    ),
    StructLayout(
        type_name="struct module",
        origin_version="v2.6.0",
        origin_path="include/linux/module.h",
        variants=(
            StructVariant(
                note=(
                    "CONFIG_MODULE_UNLOAD adds refcnt; 6.x grows the struct "
                    "and moves refcnt from 0x330 to 0x4b0"
                ),
                fields={"list": 0x08, "name": 0x18, "refcnt": 0x4B0},
            ),
        ),
    ),
)

#: ``type_name`` -> :class:`StructLayout`.
_BY_TYPE: dict[str, StructLayout] = {entry.type_name: entry for entry in _LAYOUTS}


def parse_version(text: str | None) -> Version | None:
    """Parse ``"Linux version 6.1.134 ..."`` into ``(6, 1, 134)``."""
    if not text:
        return None
    digits = ""
    started = False
    parts: list[int] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isdigit():
            started = True
            digits += char
        elif started:
            parts.append(int(digits))
            digits = ""
            if char == ".":
                index += 1
                continue
            break
        index += 1
    if digits:
        parts.append(int(digits))
    return tuple(parts) if parts else None


def lookup(type_name: str) -> StructLayout | None:
    """Return the registry entry for *type_name*, or ``None``."""
    return _BY_TYPE.get(type_name)


def offset(
    type_name: str,
    path: str,
    version: Version | None = None,
    config: Mapping[str, str] | None = None,
) -> int | None:
    """Return a fallback ``offsetof(type_name, path)``, or ``None``.

    The first :class:`StructVariant` whose version range and ``CONFIG_*``
    predicates match is used.  Returning the first *declaring* variant
    regardless only happens when **both** inputs are unknown (``None``):
    that is the "neither the version banner nor ``.config`` was readable"
    path, where something is better than nothing and the caller already
    warns that the table may not fit.

    Once the caller supplied a version or a config, a non-match is an
    answer: the field does not exist in that build.  Handing out the
    neighbouring band's offset is the exact bug this table exists to
    prevent -- a 5.14 kernel must never be told 5.9's ``offset``, a 7.0
    kernel has no ``cpu_slab`` at all, and a ``CONFIG_SLUB=n`` build has
    no ``kmem_cache_node.partial``.
    """
    layout = _BY_TYPE.get(type_name)
    if layout is None:
        return None
    resolved = layout.resolved_field(path, version, config or None)
    if resolved is not None:
        return resolved
    if version is None and config is None:
        return layout.field(path)
    return None


def sizeof(
    type_name: str,
    version: Version | None = None,
    config: Mapping[str, str] | None = None,
) -> int | None:
    """Return a fallback ``sizeof(type_name)``, or ``None``."""
    layout = _BY_TYPE.get(type_name)
    if layout is None:
        return None
    return layout.resolved_size(type_name, version, config or None)


def type_names() -> tuple[str, ...]:
    """Return every struct type the registry knows about."""
    return tuple(entry.type_name for entry in _LAYOUTS)


def entries() -> tuple[StructLayout, ...]:
    """Return every registry entry, in declaration order."""
    return _LAYOUTS


def describe(type_name: str) -> str:
    """Return a short provenance string for *type_name*."""
    layout = _BY_TYPE.get(type_name)
    if layout is None:
        return f"{type_name}: not in the fallback registry"
    return (
        f"{type_name}: defined in {layout.origin_path} "
        f"(since {layout.origin_version})"
    )


__all__ = [
    "Feature",
    "StructLayout",
    "StructVariant",
    "Version",
    "describe",
    "entries",
    "lookup",
    "offset",
    "parse_version",
    "sizeof",
    "type_names",
]