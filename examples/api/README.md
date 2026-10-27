# Scripting the KernLens API

Scripts whose product is a value or a report.  They show how to reach the
API, not how to trap the kernel — for that see
[`../tracing/`](../tracing/README.md) and
[`../breakpoints/`](../breakpoints/README.md).

| File | Runs where | Shows |
| --- | --- | --- |
| [`hello.py`](hello.py) | GDB **or** plain Python | the minimum script: names, the outside-GDB fallback, and four pure-Python calls |
| [`trace.py`](trace.py) | GDB (after `gdbinit.py`) | using the installed public API directly, plus one breakpoint-based report |
| [`slab_snapshot.py`](slab_snapshot.py) | plain Python | a full slab report with no debugger at all |
| [`gdbinit.example`](gdbinit.example) | `~/.gdbinit` | loading KernLens in every session |

## Start with `hello.py`

It answers the two questions every new script hits:

**Where do the names come from?**  `gdbinit.py` installs them into
`__main__`, which is where a sourced file runs, so `kdbg`, `KAddr` and
`BitOps` are simply there.  No import, no `sys.path` surgery.

**What if the file is run outside GDB?**  Then nothing installed those
names.  `hello.py` probes with `try: KAddr` and falls back to importing
the package.  That fallback is what lets the arithmetic half of a script
be unit-tested on the host.

The four calls it makes — `BitOps.byte_swap64`, `BitOps.popcount`,
`KAddr.is_canonical`, `KPageTable.split_4` — never touch the debugger, so
they give the same answer in both contexts.  That is the split worth
copying: keep the arithmetic pure and only the memory reads need a
target.

```console
$ PYTHONPATH=src python examples/api/hello.py
address      : 0xffffffff81000000
byte_swap64  : 0x00000081ffffffff
popcount     : 34
canonical 48 : True
canonical 57 : True
kernel       : True
page offset  : 0x0
4-level      : (511, 510, 8, 0, 0)
```

## `trace.py` — the installed API in GDB

Sourced after `gdbinit.py`, it prints one line per API family so you can
see what is available.  It ends by calling
`kernlens_trace_report(...)` on a real direct-map address, then defines
`install_slab_trace()` for the breakpoint half.

Its header is worth reading for the address it uses and why: the
direct-map alias of a page the test kernel's own page tables map.

## `slab_snapshot.py` — no debugger required

The largest API example and the only one you can run on any host:

```console
$ PYTHONPATH=src python examples/api/slab_snapshot.py
```

It assembles the same table `../tracing/gdb_tracer.py` builds from live
memory, from constants alone.  The constants are split the way the
integration fixtures are — boot-invariant values (4 KiB pages,
`sizeof(struct page) == 64`, the `kmalloc-1k` shape) versus one sample
boot's bases (`page_offset_base`, `vmemmap_base`) — and the latter are
overridable with `--page-offset-base` / `--vmemmap-base`.

## `gdbinit.example`

Copy it to `~/.gdbinit` (or `source` it) to have KernLens available in
every session.  It uses the `kernlens-` prefix, so it coexists with
pwndbg: KernLens never registers a bare command name.