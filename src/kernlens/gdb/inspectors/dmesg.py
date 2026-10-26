#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# Portions of the code are adapted from pwndbg
# (https://github.com/pwndbg/pwndbg), which is distributed under the
# MIT License.  See CREDITS.md for the full attribution.
"""Read the ``printk_ringbuffer`` (``dmesg``, kernel >= 5.10).

``printk_rb_static`` is read directly: ``desc_ring.count_bits`` gives the
descriptor count, ``descs``/``infos`` point at the parallel arrays, and
``text_data_ring`` holds the message text.  Records are walked from
``tail_id`` to ``head_id``, skipping non-committed/non-finalized slots.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._base import MASK64, PTRSIZE, InspectorBase

#: ``struct printk_ringbuffer`` (kernel >= 5.10): ``desc_ring`` is
#: ``{u64 count_bits, atomic_long head_id, tail_id, struct prb_desc *descs,
#: struct printk_info *infos}`` and ``text_data_ring`` follows it.  Every
#: offset is resolved from the debug info or :mod:`kernlens.gdb.layouts`.

#: ``prb_desc.state_var`` flags live in the top two bits of a long.
DESC_FLAGS_SHIFT = 62
DESC_FLAGS_MASK = 3 << DESC_FLAGS_SHIFT
DESC_ID_MASK = MASK64 & ~DESC_FLAGS_MASK

#: Bounds on a dmesg walk (records are self-delimiting; this is a guard).
DMESG_LIMIT = 1 << 16


@dataclass(frozen=True, slots=True)
class DmesgRecord:
    """One decoded ``printk_ringbuffer`` record."""

    seq: int
    timestamp: float
    text: str


class DmesgInspector(InspectorBase):
    """The printk ring buffer and the wall-clock epoch."""

    __slots__: tuple[str, ...] = ()

    def dmesg(self) -> tuple[DmesgRecord, ...]:
        """Return the printk ring-buffer records (kernel >= 5.10).

        Reads ``printk_rb_static`` directly: ``desc_ring.count_bits``
        gives the descriptor count, ``descs``/``infos`` point at the
        parallel arrays, and ``text_data_ring`` holds the message text.
        Records are walked from ``tail_id`` to ``head_id``, skipping
        non-committed/non-finalized descriptors.
        """
        prb = self._reader.kvar_addr("printk_rb_static")
        if not prb:
            return ()
        count_bits = (self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "desc_ring.count_bits"
            )
        ) or 0)
        if not 0 < count_bits < 32:
            return ()
        count = 1 << count_bits
        head = (self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "desc_ring.head_id"
            )
        ) or 0) & DESC_ID_MASK
        tail = (self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "desc_ring.tail_id"
            )
        ) or 0) & DESC_ID_MASK
        descs = self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "desc_ring.descs"
            )
        ) or 0
        infos = self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "desc_ring.infos"
            )
        ) or 0
        # ``text_data_ring.size_bits`` is already absolute from the start
        # of ``printk_ringbuffer``, so it is used directly (no base add).
        size_bits = self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "text_data_ring.size_bits"
            )
        ) or 0
        text_data = self._read_u64(
            prb + self._layout_offset(
                "struct printk_ringbuffer", "text_data_ring.data"
            )
        ) or 0
        if not descs or not infos or not 0 < size_bits < 40 or not text_data:
            return ()
        text_size = 1 << size_bits
        desc_size = self._layout_sizeof("struct prb_desc") or 0
        info_size = self._layout_sizeof("struct printk_info") or 0
        desc_state = self._layout_offset("struct prb_desc", "state_var")
        desc_begin = self._layout_offset(
            "struct prb_desc", "text_blk_lpos.begin"
        )
        desc_next = self._layout_offset(
            "struct prb_desc", "text_blk_lpos.next"
        )
        info_ts = self._layout_offset("struct printk_info", "ts_nsec")
        info_seq = self._layout_offset("struct printk_info", "seq")
        info_len = self._layout_offset("struct printk_info", "text_len")
        if not desc_size or not info_size:
            return ()
        if None in (desc_state, desc_begin, desc_next, info_ts, info_seq,
                     info_len):
            return ()

        records: list[DmesgRecord] = []
        did = tail
        seen: set[int] = set()
        while len(records) < DMESG_LIMIT:
            index = did % count
            desc = descs + index * desc_size
            state_var = self._read_u64(desc + desc_state)
            if state_var is None:
                break
            state = (state_var >> DESC_FLAGS_SHIFT) & 3
            if state not in (1, 2):  # desc_committed / desc_finalized
                if did == head:
                    break
                did = (did + 1) & DESC_ID_MASK
                if did in seen:
                    break
                seen.add(did)
                continue

            begin_raw = self._read_u64(desc + desc_begin) or 0
            next_raw = self._read_u64(desc + desc_next) or 0
            info = infos + index * info_size
            seq = self._read_u64(info + info_seq) or 0
            ts_nsec = self._read_u64(info + info_ts) or 0
            # ``text_len`` is a ``u16`` followed by ``dict_len``; reading
            # it as a word would fold in the neighbouring fields.
            text_len = self._read_u16(info + info_len) or 0

            begin = begin_raw % text_size
            end = next_raw % text_size
            if begin & 1 == 1:
                text = ""
            else:
                if begin > end:
                    begin = 0
                start = begin + PTRSIZE
                length = min(max(0, text_len), end - start)
                raw = self._read_bytes(text_data + start, length) or b""
                text = raw.decode("utf-8", "replace")

            records.append(
                DmesgRecord(
                    seq=seq,
                    timestamp=ts_nsec / 1e9,
                    # A ring buffer can pad a record; a NUL would abort
                    # the terminal writer, so keep only real characters.
                    text=text.replace("\x00", "").rstrip("\n"),
                )
            )
            if did == head:
                break
            did = (did + 1) & DESC_ID_MASK
        return tuple(records)

    def tk_epoch(self) -> int | None:
        """Return ``tk_core.timekeeper.xtime_sec`` for wall-clock times."""
        tk_core = self._reader.kvar_addr("tk_core")
        if not tk_core:
            return None
        return self._read_u64(tk_core)


__all__ = [
    "DESC_FLAGS_MASK",
    "DESC_FLAGS_SHIFT",
    "DESC_ID_MASK",
    "DMESG_LIMIT",
    "DmesgInspector",
    "DmesgRecord",
]