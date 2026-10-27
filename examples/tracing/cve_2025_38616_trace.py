#!/usr/bin/env python3
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ruff: noqa: EXE001, F821
# pyright: reportImplicitRelativeImport=false, reportUndefinedVariable=false
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
# See the LICENSE file in the top-level directory for details.
"""CVE-2025-38616 KTLS use-after-free tracer for GDB.

``gdbinit.py`` is expected to be loaded already (for example from
``~/.gdbinit``).  It installs the public KernLens API into GDB's
``__main__`` namespace, so this tracer uses ``kdbg`` and ``Palette``
directly; it does not modify ``sys.path``, import ``kernlens``, or
create per-file aliases for the facade.

Load the tracer from GDB after ``gdbinit.py``::

    (gdb) source examples/tracing/cve_2025_38616_trace.py
    (gdb) trace-start                    # auto base + install
    (gdb) trace-color on|off             # ANSI color toggle
    (gdb) c

``trace-start`` invokes the registered ``kl-base`` command, so a running
kernel is detected automatically.  For a manually selected base, run
``kl-kaslr`` / ``kl-kaslr-offset`` first and then ``trace-start manual``;
the compatibility commands ``kaslr-text`` / ``kaslr-offset`` delegate to
the same registered ``kl-kaslr`` / ``kl-kaslr-offset`` implementation.
A zero manual slide is rejected so breakpoints cannot silently use
link-time (nokaslr) addresses.
"""

from __future__ import annotations

import gdb  # type: ignore[import-not-found]

# ``gdbinit.py`` installs these names into ``__main__``; sourcing this
# file on its own is a configuration error, not a reason to bootstrap a
# second copy of the toolkit.
try:
    kdbg
    Palette
except NameError as exc:  # pragma: no cover - configuration error
    raise RuntimeError(
        "source KernLens gdbinit.py before this tracer"
    ) from exc


# =========================================================================
# Output
# =========================================================================

def _echo(message: str) -> None:
    """Write one preformatted tracer line without a logger prefix."""
    gdb.write(message + "\n")


# =========================================================================
# CVE-specific tuning
# =========================================================================

BT_DEPTH_EVENT = 6
BT_DEPTH_WAKE = 8
BT_DEPTH_KFREE = 7
NOHDR_DATAREF_THRESHOLD = 0x10000


_TAG_COLOR = {
    "[CONN]": Palette.CYAN,
    "[wait]": Palette.CYAN,
    "[load]": Palette.CYAN,
    "[anchor]": Palette.BLUE,
    "[H]": Palette.BLUE,
    "[P1]": Palette.BLUE,
    "[wake:skb]": Palette.MAGENTA,
    "[wake:err]": Palette.MAGENTA,
    "[eat]": Palette.YELLOW,
    "[hold]": Palette.YELLOW,
    "[clone]": Palette.YELLOW,
    "[defer?]": Palette.DIM,
    "[release]": Palette.DIM,
    "[kfree]": Palette.BRIGHT_RED,
    "[trace]": Palette.BRIGHT_RED,
    "[+]": Palette.GREEN,
    "[-]": Palette.RED,
}


def _hdr(tag: str) -> str:
    """Format an event tag padded to the standard header column."""
    padded = f"{tag:<{kdbg.header_width}}"
    return kdbg.style(padded, _TAG_COLOR.get(tag, ""))


# =========================================================================
# CVE-specific state
# =========================================================================

_CONN_SK = [0]
_H = [0]
_P1 = [0]
_SEEN: set = set()
_INSTALLED = [False]
_EXPLOIT_DONE = [False]
_KFREE_COUNT = [0]
_LAST_COPIED_SEQ = [0]
_BREAKPOINTS_OBJ: list = []


def _once(tag: str, key: str) -> bool:
    """Return True the first time ``(tag, key)`` is seen, False after."""
    token = (tag, key)
    if token in _SEEN:
        return False
    _SEEN.add(token)
    return True


# =========================================================================
# sk_buff helpers (CVE-specific)
# =========================================================================

def _skb_field(skb: int, path: str) -> int | None:
    """Read ``skb->path`` as an int."""
    return kdbg.read_field(skb, "struct sk_buff", path)


def _skb_head(skb: int) -> int:
    """Return ``skb->head``, or 0 on failure."""
    value = _skb_field(skb, "head")
    return value if value is not None else 0


def _skb_fclone(skb: int) -> int:
    """Return ``skb->fclone`` (0/1/2)."""
    value = _skb_field(skb, "fclone")
    return value if value is not None else 0


def _skb_cloned(skb: int) -> int:
    """Return ``skb->cloned``."""
    value = _skb_field(skb, "cloned")
    return value if value is not None else 0


def _skb_alloc_cpu(skb: int) -> int:
    """Return ``skb->alloc_cpu``, or -1 on failure."""
    value = _skb_field(skb, "alloc_cpu")
    return value if value is not None else -1


def _skb_shinfo(skb: int) -> int:
    """Locate ``struct skb_shared_info`` at ``skb->head + skb->end``."""
    via_helper = kdbg.u64(f"(unsigned long)skb_shinfo((struct sk_buff *){skb})")
    if via_helper is not None and via_helper:
        return via_helper
    head = _skb_field(skb, "head")
    if not head:
        return 0
    end = kdbg.u64(f"(unsigned int)((struct sk_buff *){skb})->end")
    if end is None:
        return 0
    return head + end


def _shinfo_field(skb: int, path: str) -> int | None:
    """Read a field from the skb's ``skb_shared_info``."""
    sh = _skb_shinfo(skb)
    if not sh:
        return None
    return kdbg.read_field(sh, "struct skb_shared_info", path)


def _dataref(skb: int) -> int:
    """Read ``shinfo->dataref`` (atomic_t); -1 if unreadable."""
    value = _shinfo_field(skb, "dataref.counter")
    if value is not None:
        return value
    value = _shinfo_field(skb, "dataref")
    return value if value is not None else -1


def _nr_frags(skb: int) -> int:
    """Read ``shinfo->nr_frags``; -1 if unreadable."""
    value = _shinfo_field(skb, "nr_frags")
    return value if value is not None else -1


def _frag0_page(skb: int) -> int:
    """Read ``shinfo->frags[0].bv_page``; -1 if unreadable."""
    value = _shinfo_field(skb, "frags[0].bv_page")
    return value if value is not None else -1


def _page_ref(page: int) -> int:
    """Read ``page->_refcount.counter``; -1 on failure."""
    if page <= 0:
        return -1
    value = kdbg.read_field(page, "struct page", "_refcount.counter")
    return value if value is not None else -1


def _frag_list(skb: int) -> int:
    """Read ``shinfo->frag_list``, preserving 0 for NULL."""
    value = _shinfo_field(skb, "frag_list")
    return value if value is not None else -1


def _tcp_inq(sk: int) -> int:
    """Compute ``tp->rcv_nxt - tp->copied_seq``; -1 on failure."""
    rcv_nxt = kdbg.read_field(sk, "struct tcp_sock", "rcv_nxt")
    copied = kdbg.read_field(sk, "struct tcp_sock", "copied_seq")
    if rcv_nxt is None or copied is None:
        return -1
    return (rcv_nxt - copied) & 0xFFFFFFFF


def _skb_desc(skb: int, label: str = "skb") -> str:
    """Format ``label=0x.. head=0x.. alloc_cpu=N`` for an skb."""
    if not skb:
        return (
            f"{kdbg.style(label, Palette.CYAN)}=0x0 "
            + f"{kdbg.kv_hex('head', 0)} "
            + f"{kdbg.kv_cpu('alloc_cpu', -1)}"
        )
    return (
        f"{kdbg.kv_hex(label, skb)} "
        + f"{kdbg.kv_hex('head', _skb_head(skb))} "
        + f"{kdbg.kv_cpu('alloc_cpu', _skb_alloc_cpu(skb))}"
    )


def _skb_kv(skb: int, kind: str) -> str:
    """Uniform skb prefix used by every event line."""
    return (
        f"{kdbg.style(kind, Palette.BOLD + Palette.MAGENTA)} "
        + f"{kdbg.kv_hex('skb', skb)} "
        + f"{kdbg.kv_hex('head', _skb_head(skb))} "
        + f"{kdbg.kv_cpu('alloc_cpu', _skb_alloc_cpu(skb))}"
    )


KIND_A = "A"
KIND_A_CLONE = "A_clone"
KIND_N = "n"
KIND_NULL = "NULL"


def _skb_kind(skb: int) -> str:
    """Classify an skb as ``A`` / ``A_clone`` / ``n`` / ``NULL``."""
    if skb <= 0:
        return KIND_NULL
    fclone = _skb_fclone(skb)
    if fclone == 1:
        return KIND_A
    if fclone == 2:
        return KIND_A_CLONE
    return KIND_N


def _on_H(skb: int) -> bool:
    """Return True if ``skb->head`` equals the shared H."""
    return _H[0] != 0 and _skb_head(skb) == _H[0]


def _auto_H(skb: int, source: str) -> None:
    """Discover H from the first ``SKB_FCLONE_CLONE`` skb seen."""
    if _H[0] or skb <= 0:
        return
    if _skb_fclone(skb) != 2:
        return
    head = _skb_head(skb)
    if head <= 0:
        return
    _H[0] = head
    _echo(f"{_hdr('[H]')}{kdbg.kv_hex('head', _H[0])}")
    _echo(
        f"{kdbg.indent_str}"
        + f"{kdbg.style('first_seen_via', Palette.CYAN)} "
        + f"{_skb_desc(skb)}"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.kv('from', source, value_color=Palette.DIM)}"
    )


def _auto_P1(skb: int) -> None:
    """Discover P1 from the first skb whose frags[0] we can read."""
    if _P1[0] or _nr_frags(skb) <= 0:
        return
    page = _frag0_page(skb)
    if page > 0:
        _P1[0] = page
        _echo(f"{_hdr('[P1]')}{kdbg.kv_hex('page', _P1[0])}")
        _echo(
            f"{kdbg.indent_str}{kdbg.style('from', Palette.CYAN)} {_skb_desc(skb)}"
        )


# =========================================================================
# Breakpoint installation / KASLR state
# =========================================================================

def _reset_exploit_state() -> None:
    """Reset every per-run field in preparation for a fresh run."""
    _CONN_SK[0] = 0
    _H[0] = 0
    _P1[0] = 0
    _SEEN.clear()
    _EXPLOIT_DONE[0] = False
    _KFREE_COUNT[0] = 0
    _LAST_COPIED_SEQ[0] = 0


def _delete_breakpoints() -> None:
    """Delete every installed breakpoint and clear the tracking list."""
    for bp in _BREAKPOINTS_OBJ:
        try:
            bp.delete()
        except gdb.error:
            pass
    _BREAKPOINTS_OBJ.clear()
    _INSTALLED[0] = False


def _install_breakpoints() -> None:
    """Install every tracer breakpoint at the current KASLR base."""
    slide = kdbg.kaslr_offset
    for name, bp_cls in BREAKPOINTS:
        spec = kdbg.bp_spec(name)
        try:
            bp = bp_cls(
                spec,
                gdb.BP_BREAKPOINT,
                internal=False,
            )
            _BREAKPOINTS_OBJ.append(bp)
            _echo(f"{_hdr('[+]')}{name} @ {bp.location}")
            # ``bp_spec()`` returns a bare symbol when GDB cannot express
            # the address as ``&symbol`` -- which is exactly what happens
            # for a ``static`` function the kernel exposes only as
            # inlined locations (e.g. ``tcp_eat_recv_skb``).  GDB then
            # resolves the name through DWARF at its LINK-TIME address, so
            # on a KASLR kernel the breakpoint would sit at the wrong
            # place.  Say so instead of printing a breakpoint that looks
            # relocated but is not.
            if slide and spec == name:
                note = kdbg.style(
                    "! no &symbol; breakpoint uses the link-time address",
                    Palette.YELLOW,
                )
                _echo(f"{kdbg.indent_str}{note}")
        except gdb.error as exc:
            _echo(f"{_hdr('[-]')}{name}: {exc}")
    _INSTALLED[0] = True
    _echo(f"{_hdr('[trace]')}ready. run 'c' to continue")


def _apply_kaslr_offset(offset: int) -> None:
    """Set the KASLR slide, then reinstall the breakpoints."""
    if offset < 0:
        offset &= 0xFFFFFFFFFFFFFFFF
    kdbg.kaslr_offset = offset
    link_text = kdbg.link_text()
    runtime_text = (
        (link_text + offset) if link_text is not None else None)
    if link_text is not None and runtime_text is not None:
        _echo(
            f"{_hdr('[+]')}KASLR offset "
            + f"{kdbg.style(f'+{offset:#x}', Palette.BRIGHT_GREEN)} "
            + f"(link _text={kdbg.addr(link_text)}, "
            + f"runtime _text={kdbg.addr(runtime_text)})"
        )
    else:
        _echo(
            f"{_hdr('[+]')}KASLR offset "
            + f"{kdbg.style(f'+{offset:#x}', Palette.BRIGHT_GREEN)}"
        )
    if _INSTALLED[0]:
        _delete_breakpoints()
    _reset_exploit_state()
    _install_breakpoints()


# =========================================================================
# Breakpoints
# =========================================================================

class SkWaitBp(gdb.Breakpoint):
    """``sk_wait_data``: capture CONN_SK and log TCP state changes."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        sk = kdbg.arg("sk", "rdi")
        if not sk:
            return False
        first = not _CONN_SK[0]
        if first:
            _CONN_SK[0] = sk
            _echo(f"{_hdr('[CONN]')}{kdbg.kv_hex('sk', _CONN_SK[0])}")
        if sk != _CONN_SK[0]:
            return False
        copied_seq = kdbg.read_field(sk, "struct tcp_sock", "copied_seq")
        copied_val = copied_seq if copied_seq is not None else 0
        qlen = kdbg.read_field(sk, "struct sock", "sk_receive_queue.qlen")
        qlen_val = qlen if qlen is not None else 0
        sk_err = kdbg.read_field(sk, "struct sock", "sk_err")
        if first:
            _LAST_COPIED_SEQ[0] = copied_val
            delta = 0
        else:
            delta = (copied_val - _LAST_COPIED_SEQ[0]) & 0xFFFFFFFF
            _LAST_COPIED_SEQ[0] = copied_val
        delta_color = (
            Palette.BRIGHT_YELLOW if delta else Palette.DIM)
        _echo(
            f"{_hdr('[wait]')}"
            + f"{kdbg.kv_int('copied_seq', copied_val, value_color=Palette.DIM)} "
            + f"{kdbg.kv_int('Δ', delta, value_color=delta_color)} "
            + f"{kdbg.kv_int('qlen', qlen_val)} "
            + f"{kdbg.kv_err(sk_err)}"
        )
        return False


class TlsStrpMsgLoadBp(gdb.Breakpoint):
    """``tls_strp_msg_load``: log force_refresh and load/warn branch."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        strp = kdbg.arg("strp", "rdi")
        if not strp:
            return False
        sk = kdbg.read_field(strp, "struct tls_strparser", "sk")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        force = kdbg.arg("force_refresh", "rsi")
        force_val = force if force is not None else 0
        full_len_raw = kdbg.read_field(
            strp, "struct tls_strparser", "stm.full_len")
        full_len = full_len_raw if full_len_raw is not None else 0
        inq = _tcp_inq(sk if sk is not None else 0)
        if force_val and inq < full_len:
            extra = kdbg.style(
                "-> WARN_ON, anchor NOT refreshed",
                Palette.BRIGHT_YELLOW + Palette.BOLD)
            inq_color = Palette.BRIGHT_YELLOW
        else:
            extra = kdbg.style("-> load ok", Palette.GREEN)
            inq_color = Palette.GREEN
        force_color = (
            Palette.BRIGHT_YELLOW if force_val else Palette.DIM)
        force_str = "true" if force_val else "false"
        _echo(
            f"{_hdr('[load]')}"
            + f"{kdbg.kv('force_refresh', force_str, value_color=force_color)} "
            + f"{kdbg.kv_int('tcp_inq', inq, value_color=inq_color)} "
            + f"{kdbg.kv_int('full_len', full_len, value_color=Palette.CYAN)} "
            + extra
        )
        return False


class AnchorBp(gdb.Breakpoint):
    """``tls_strp_load_anchor_with_queue``: link or reset anchor."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        strp = kdbg.arg("strp", "rdi")
        if not strp:
            return False
        sk = kdbg.read_field(strp, "struct tls_strparser", "sk")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        anchor = kdbg.read_field(strp, "struct tls_strparser", "anchor")
        anchor_val = anchor if anchor is not None else 0
        frag = _frag_list(anchor_val)
        if frag <= 0:
            if _once("anchor_reset", "0"):
                _echo(f"{_hdr('[anchor]')}reset (frag_list=NULL)")
            return False
        _auto_H(frag, "load_anchor")
        _auto_P1(frag)
        if _H[0] and _skb_head(frag) != _H[0]:
            return False
        kind = _skb_kind(frag)
        _echo(
            f"{_hdr('[anchor]')}{_skb_kv(frag, kind)} link frag_list"
        )
        return False


class WakeReadyBp(gdb.Breakpoint):
    """``tls_rx_msg_ready``: first wake-up driven by data arrival."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        strp = kdbg.arg("strp", "rdi")
        if not strp:
            return False
        sk = kdbg.read_field(strp, "struct tls_strparser", "sk")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        if not _once("wake_skb", "msg_ready"):
            return False
        _echo(
            f"{_hdr('[wake:skb]')}tls_rx_msg_ready (data arrival)"
        )
        kdbg.backtrace(BT_DEPTH_EVENT)
        return False


class WakeErrBp(gdb.Breakpoint):
    """``sk_error_report``: log every error wake on CONN_SK."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        sk = kdbg.arg("sk", "rdi")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        sk_err = kdbg.read_field(sk, "struct sock", "sk_err")
        chain = kdbg.chain(2)
        if not _once("wake_err", chain):
            return False
        _echo(
            f"{_hdr('[wake:err]')}"
            + f"{kdbg.kv_err(sk_err)}  "
            + f"{kdbg.style('via', Palette.CYAN)} {kdbg.color_chain(chain)}"
        )
        kdbg.backtrace(BT_DEPTH_WAKE)
        return False


class TcpEatRecvSkbBp(gdb.Breakpoint):
    """``tcp_eat_recv_skb``: reader removes A_clone from the queue."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        sk = kdbg.arg("sk", "rdi")
        skb = kdbg.arg("skb", "rsi")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        if not skb or not _on_H(skb):
            return False
        kind = _skb_kind(skb)
        _echo(
            f"{_hdr('[eat]')}{_skb_kv(skb, kind)} "
            + "removed from sk_receive_queue"
        )
        return False


class SkbAttemptDeferFreeBp(gdb.Breakpoint):
    """``skb_attempt_defer_free``: show alloc_cpu vs current CPU."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        skb = kdbg.arg("skb", "rdi")
        if not skb:
            return False
        kind = _skb_kind(skb)
        if kind != KIND_A_CLONE and not _on_H(skb):
            return False
        _auto_H(skb, "attempt_defer_free")
        _auto_P1(skb)
        alloc_cpu = _skb_alloc_cpu(skb)
        nr_cpus = kdbg.nr_cpus()
        cur_cpu = kdbg.cur_cpu()
        online = kdbg.cpu_online(alloc_cpu) if alloc_cpu >= 0 else None
        if alloc_cpu < 0:
            branch = "nodefer (alloc_cpu unreadable)"
        elif nr_cpus > 0 and alloc_cpu >= nr_cpus:
            branch = "nodefer (alloc_cpu >= nr_cpus)"
        elif online is False:
            branch = "nodefer (alloc_cpu offline)"
        elif cur_cpu is None:
            branch = "defer? (cur_cpu unreadable)"
        elif alloc_cpu == cur_cpu:
            branch = "nodefer (alloc_cpu == cur_cpu)"
        else:
            branch = "defer (alloc_cpu != cur_cpu)"
        _echo(
            f"{_hdr('[defer?]')}{_skb_kv(skb, kind)} "
            + f"{kdbg.kv_online(online)} "
            + f"{kdbg.kv_int('nr_cpus', nr_cpus)} "
            + f"{kdbg.kv_cpu('cur_cpu', cur_cpu, alloc_cpu)} "
            + f"-> {kdbg.branch(branch)}"
        )
        return False


class HoldBp(gdb.Breakpoint):
    """``tls_strp_msg_hold``: clone the dangling frag_list into n."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        strp = kdbg.arg("strp", "rdi")
        if not strp:
            return False
        sk = kdbg.read_field(strp, "struct tls_strparser", "sk")
        if not _CONN_SK[0] or sk != _CONN_SK[0]:
            return False
        full_len = kdbg.read_field(
            strp, "struct tls_strparser", "stm.full_len")
        anchor = kdbg.read_field(strp, "struct tls_strparser", "anchor")
        anchor_val = anchor if anchor is not None else 0
        frag = _frag_list(anchor_val)
        if _H[0] and frag > 0 and _skb_head(frag) != _H[0]:
            return False
        kind = _skb_kind(frag)
        full_len_str = str(full_len) if full_len is not None else "?"
        _echo(
            f"{_hdr('[hold]')}{_skb_kv(frag, kind)} "
            + f"{kdbg.kv('full_len', full_len_str, value_color=Palette.CYAN)}"
        )
        kdbg.backtrace(4)
        return False


class CloneBp(gdb.Breakpoint):
    """``__skb_clone``: link A -> A_clone and A_clone -> n."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        new_skb = kdbg.arg("n", "rdi")
        src_skb = kdbg.arg("skb", "rsi")
        if not src_skb:
            return False
        _auto_H(src_skb, "clone")
        if not _H[0]:
            return False
        if _skb_head(src_skb) != _H[0]:
            return False
        dataref = _dataref(src_skb)
        if dataref > NOHDR_DATAREF_THRESHOLD:
            return False
        src_kind = _skb_kind(src_skb)
        dst_kind = _skb_kind(new_skb if new_skb else 0)
        src_head = _skb_head(src_skb)
        dst_head = _skb_head(new_skb if new_skb else 0)
        chain = kdbg.chain(3)
        dataref_trans = kdbg.kv_trans(
            "H->dataref", dataref, dataref + 1,
            danger_if_zero=False,
        )
        _echo(
            f"{_hdr('[clone]')}{_skb_kv(src_skb, src_kind)} -> "
            + f"{kdbg.style(dst_kind, Palette.BOLD + Palette.MAGENTA)}"
            + f"({kdbg.addr(new_skb if new_skb else 0)}) "
            + f"{dataref_trans}"
        )
        _echo(
            f"{kdbg.indent_str}"
            + f"{kdbg.kv_hex('src_head', src_head)} "
            + f"{kdbg.kv_hex('dst_head', dst_head)}  "
            + f"{kdbg.style('chain', Palette.CYAN)}: {kdbg.color_chain(chain)}"
        )
        return False


class ReleaseBp(gdb.Breakpoint):
    """``skb_release_data``: log when the frags loop will run."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        skb = kdbg.arg("skb", "rdi")
        if not skb or not _on_H(skb):
            return False
        dataref = _dataref(skb)
        cloned = _skb_cloned(skb)
        nr_frags = _nr_frags(skb)
        if cloned != 1 and nr_frags == 0:
            return False
        kind = _skb_kind(skb)
        cloned_color = Palette.YELLOW if cloned else Palette.DIM
        if dataref < 0:
            _echo(
                f"{_hdr('[release]')}{_skb_kv(skb, kind)} "
                + f"{kdbg.kv_int('cloned', cloned, value_color=cloned_color)} "
                + f"{kdbg.kv_int('frags', nr_frags)} "
                + kdbg.style(
                    "[H->dataref unreadable]",
                    Palette.BRIGHT_YELLOW + Palette.BOLD,
                )
            )
            return False
        will_run_frags = (
            (cloned == 0) or (cloned == 1 and dataref == 1))
        if not will_run_frags:
            return False
        page = _frag0_page(skb) if nr_frags > 0 else -1
        page_ref = _page_ref(page) if page > 0 else -1
        _auto_P1(skb)
        next_dataref = dataref - 1 if cloned else dataref
        next_page_ref = page_ref - 1 if page_ref > 0 else -1
        _echo(
            f"{_hdr('[release]')}{_skb_kv(skb, kind)} "
            + f"{kdbg.kv_int('cloned', cloned, value_color=cloned_color)} "
            + f"{kdbg.kv_trans('H->dataref', dataref, next_dataref)} "
            + f"{kdbg.kv_int('frags', nr_frags)} "
            + f"{kdbg.kv_trans('page_ref', page_ref, next_page_ref)}"
        )
        kdbg.backtrace(BT_DEPTH_EVENT)
        return False


class FreeHeadBp(gdb.Breakpoint):
    """``skb_free_head``: log every free of H (deduped per skb)."""

    def stop(self) -> bool:
        if _EXPLOIT_DONE[0]:
            return False
        skb = kdbg.arg("skb", "rdi")
        if not skb or not _on_H(skb):
            return False
        if not _once("freehead", f"{skb:#x}"):
            return False
        _KFREE_COUNT[0] += 1
        kind = _skb_kind(skb)
        cur_cpu = kdbg.cur_cpu()
        head = _skb_head(skb)
        _echo(
            f"{_hdr('[kfree]')}{_skb_kv(skb, kind)} "
            + f"{kdbg.kv_cpu('cur_cpu', cur_cpu, _skb_alloc_cpu(skb))}"
        )
        kdbg.print_slab(head)
        kdbg.backtrace(BT_DEPTH_KFREE)
        if _KFREE_COUNT[0] >= 2:
            _EXPLOIT_DONE[0] = True
            _echo(
                f"{_hdr('[trace]')}"
                + kdbg.style(
                    "exploit chain complete",
                    Palette.BRIGHT_RED + Palette.BOLD,
                )
            )
            return True
        return False


# =========================================================================
# GDB commands
# =========================================================================

def _delegate_kaslr(command: str, argument: str) -> None:
    """Run a registered KernLens KASLR command, then install breakpoints."""
    label = "kaslr-text" if command == "kaslr" else command
    if not argument:
        placeholder = (
            "runtime-text-address" if command == "kaslr" else "offset"
        )
        _echo(f"usage: {label} <{placeholder}>")
        return
    try:
        gdb.execute(f"kl-{command} {argument}", to_string=True)
    except gdb.error as exc:
        _echo(f"{_hdr('[-]')}{label}: {exc}")
        return
    _apply_kaslr_offset(kdbg.kaslr_offset)


def set_runtime_text(runtime_text: int) -> None:
    """Compatibility entry point for ``kaslr-text``; uses ``kl-kaslr``."""
    _delegate_kaslr("kaslr", f"{runtime_text:#x}")


class KaslrTextCmd(gdb.Command):
    """kaslr-text <runtime-text-address> — wrapper for ``kl-kaslr``."""

    def __init__(self) -> None:
        super().__init__("kaslr-text", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        _delegate_kaslr("kaslr", arg.strip())


class KaslrOffsetCmd(gdb.Command):
    """kaslr-offset <offset> — wrapper for ``kl-kaslr-offset``."""

    def __init__(self) -> None:
        super().__init__("kaslr-offset", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        _delegate_kaslr("kaslr-offset", arg.strip())


class TraceStartCmd(gdb.Command):
    """trace-start [auto|manual] — select the base and install breakpoints.

    ``auto`` (the default) runs the registered ``kl-base`` command, which
    detects a live kernel's runtime base and applies its KASLR slide.
    ``manual`` keeps whatever slide was set by the registered
    ``kl-kaslr`` / ``kl-kaslr-offset`` commands.  A zero slide is rejected
    for ``manual`` because breakpoints would be installed at their
    link-time (nokaslr) addresses; use ``trace-start`` for nokaslr.
    """

    def __init__(self) -> None:
        super().__init__("trace-start", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        mode = arg.strip().lower() or "auto"
        if mode not in ("auto", "manual"):
            _echo("usage: trace-start [auto|manual]")
            return
        if mode == "auto":
            try:
                gdb.execute("kl-base")
            except gdb.error as exc:
                _echo(f"{_hdr('[-]')}kl-base: {exc}")
                return
        elif not kdbg.kaslr_offset:
            # ``bp_spec()`` returns a bare symbol when the slide is zero, so
            # GDB would plant every breakpoint at its link-time (nokaslr)
            # address.  Do not let a manual start silently do that.
            _echo(
                f"{_hdr('[-]')}KASLR offset is 0; breakpoints would use "
                + "nokaslr addresses"
            )
            _echo(
                f"{kdbg.indent_str}run kl-base (auto), or kl-kaslr / "
                + "kl-kaslr-offset first"
            )
            return
        _apply_kaslr_offset(kdbg.kaslr_offset)


class TraceColorCmd(gdb.Command):
    """trace-color on|off — enable or disable ANSI color output."""

    def __init__(self) -> None:
        super().__init__("trace-color", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        arg = arg.strip().lower()
        if arg not in ("on", "off"):
            _echo("usage: trace-color on|off")
            current = "on" if kdbg.color_enabled else "off"
            _echo(f"       current: {current}")
            return
        kdbg.color_enabled = (arg == "on")
        marker = (
            kdbg.style("on", Palette.GREEN)
            if kdbg.color_enabled else "off"
        )
        _echo(f"{_hdr('[trace]')}color {marker}")


class TraceStatusCmd(gdb.Command):
    """trace-status — print the tracer's current state."""

    def __init__(self) -> None:
        super().__init__("trace-status", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        page_offset_base = kdbg.read_kvar("page_offset_base")
        vmemmap_base = kdbg.read_kvar("vmemmap_base")
        color_str = "on" if kdbg.color_enabled else "off"
        _echo(
            f"{_hdr('[trace]')}KASLR "
            + f"{kdbg.style(f'+{kdbg.kaslr_offset:#x}', Palette.BRIGHT_GREEN)}  "
            + f"bps={_INSTALLED[0]}({len(_BREAKPOINTS_OBJ)})  "
            + f"kfree={_KFREE_COUNT[0]}  "
            + f"color={color_str}"
        )
        _echo(
            f"{kdbg.indent_str}"
            + f"_CONN_SK={kdbg.addr(_CONN_SK[0])} "
            + f"_H={kdbg.addr(_H[0])} "
            + f"_P1={kdbg.addr(_P1[0])}"
        )
        page_offset_str = (
            f"{page_offset_base:#x}"
            if page_offset_base is not None else "?"
        )
        vmemmap_str = (
            f"{vmemmap_base:#x}"
            if vmemmap_base is not None else "?"
        )
        _echo(
            f"{kdbg.indent_str}"
            + f"page_offset={page_offset_str}  "
            + f"vmemmap={vmemmap_str}  "
            + f"nr_cpu={kdbg.nr_cpus()} "
            + f"nr_node={kdbg.nr_nodes()}"
        )


class TraceHinfoCmd(gdb.Command):
    """trace-hinfo — inspect the H object discovered so far."""

    def __init__(self) -> None:
        super().__init__("trace-hinfo", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        if not _H[0]:
            _echo(f"{_hdr('[trace]')}_H not discovered yet")
            return
        _echo(f"{_hdr('[trace]')}{kdbg.kv_hex('H', _H[0])}")
        kdbg.print_slab(_H[0])


class TracePageinfoCmd(gdb.Command):
    """trace-pageinfo <address> — inspect any head address's slab."""

    def __init__(self) -> None:
        super().__init__("trace-pageinfo", gdb.COMMAND_USER)

    def invoke(self, arg: str, from_tty: bool) -> None:
        arg = arg.strip()
        if not arg:
            _echo("usage: trace-pageinfo <address>")
            return
        try:
            head = int(arg, 16)
        except ValueError:
            _echo(
                f"{_hdr('[-]')}trace-pageinfo: cannot parse hex: {arg}"
            )
            return
        _echo(f"{_hdr('[trace]')}{kdbg.kv_hex('head', head)}")
        kdbg.print_slab(head)


# =========================================================================
# Registration
# =========================================================================

BREAKPOINTS = [
    ("sk_wait_data",                    SkWaitBp),
    ("tls_rx_msg_ready",                WakeReadyBp),
    ("sk_error_report",                 WakeErrBp),
    ("tls_strp_msg_load",               TlsStrpMsgLoadBp),
    ("tls_strp_load_anchor_with_queue", AnchorBp),
    ("tcp_eat_recv_skb",                TcpEatRecvSkbBp),
    ("skb_attempt_defer_free",          SkbAttemptDeferFreeBp),
    ("tls_strp_msg_hold",               HoldBp),
    ("__skb_clone",                     CloneBp),
    ("skb_release_data",                ReleaseBp),
    ("skb_free_head",                   FreeHeadBp),
]


def _register() -> None:
    """Register the tracer's GDB commands and print the boot banner."""
    # The tracer supplies its own event headers; keep the toolkit's
    # multiline slab/backtrace output free of the generic [INFO] prefix.
    kdbg.logger.set_show_tag(False)
    KaslrTextCmd()
    KaslrOffsetCmd()
    TraceStartCmd()
    TraceColorCmd()
    TraceStatusCmd()
    TraceHinfoCmd()
    TracePageinfoCmd()
    _echo(kdbg.style("=" * 60, Palette.BOLD))
    _echo(kdbg.style("CVE-2025-38616 KTLS UAF tracer", Palette.BOLD))
    _echo(kdbg.style("=" * 60, Palette.BOLD))
    _echo(
        f"{_hdr('[trace]')}kernlens loaded from "
        + f"{kdbg.style(kdbg.__class__.__module__, Palette.DIM)}"
    )
    _echo(f"{_hdr('[trace]')}breakpoints NOT installed yet")
    _echo(f"{_hdr('[trace]')}installed KernLens commands are reused:")
    _echo(
        f"{kdbg.indent_str}{kdbg.style('trace-start', Palette.CYAN)} "
        + "                    (auto: kl-base + install)"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.style('trace-start manual', Palette.CYAN)} "
        + "             (non-zero manual slide)"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.style('kl-base', Palette.CYAN)} "
        + "                         (show/apply runtime base)"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.style('kl-kaslr', Palette.CYAN)} "
        + " | "
        + f"{kdbg.style('kl-kaslr-offset', Palette.CYAN)}"
        + "  (manual base/slide)"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.style('kaslr-text', Palette.CYAN)} "
        + " | "
        + f"{kdbg.style('kaslr-offset', Palette.CYAN)}"
        + "  (compat wrappers)"
    )
    _echo(
        f"{kdbg.indent_str}{kdbg.style('trace-color on|off', Palette.CYAN)} "
        + "            (default on)"
    )


_register()