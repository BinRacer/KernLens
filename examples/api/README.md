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

## Workflow tours

Four scripts that drive a group of commands in the order an
investigation actually uses them, rather than one command at a time.
Each is a `gdb.Command`, so the whole tour is one word at the prompt, and
each prints the command it is about to run so any line can be copied out
and used alone.

| Command | File | Covers |
| --- | --- | --- |
| `kfacts [symbol]` | [`kernel_facts.py`](kernel_facts.py) | `kl-kversion` `kl-kcmdline` `kl-kconfig` `kl-kchecksec` `kl-kmod` `kl-ksyscalls` `kl-klookup` `kl-kdmesg` |
| `atour [addr]` | [`address_tour.py`](address_tour.py) | `kl-addr` `kl-page` `kl-pt` `kl-walk` `kl-pagewalk` `kl-pte` `kl-v2p` `kl-p2v` `kl-pageinfo` |
| `stour [cache]` | [`slab_tour.py`](slab_tour.py) | `kl-slab` `kl-buddy` |
| `ytour [symbol]` | [`symbols_tour.py`](symbols_tour.py) | `kl-klookup` `kl-sym` `kl-read` `kl-kvar` `kl-read-field` `kl-bt` `kl-chain` |

## The pure-Python tours

Three scripts for the half of KernLens that needs no debugger at all.
They run from a plain interpreter, from a test, and from inside GDB
without changing a line -- which is the property that makes them worth
reading: the arithmetic half of any tracer can be unit-tested on the
host, and only the memory reads need a target.

| Command | File | Covers |
| --- | --- | --- |
| `icodec` | [`intcodec_tour.py`](intcodec_tour.py) | every integer width, both byte orders, arrays, offsets |
| `ifmt` | [`intfmt_tour.py`](intfmt_tour.py) | addresses, sizes, byte dumps, signed/masked values, times |
| `btour` | [`bitops_tour.py`](bitops_tour.py) | alignment, field packing, single bits, CPU masks, sign extension |

**`icodec`** round-trips `u8` through `u64` and `i8` through `i64`, in
both byte orders, printing the *bytes* as well as the decoded value.  That
is deliberate: a width mistake drops the top bytes and a byte-order
mistake reverses them, and both produce a number that looks plausible.
Step 6 reads a real `struct page` when a target is attached and says so
plainly when it is using a stand-in.

**`ifmt`** is organised by *what the value is*, not by method name.  The
section worth reading twice is step 1: `pfn()` and `page_off()` take a
**physical** address and do not translate, so handing them a virtual one
yields a number shaped like a PFN and off by the whole direct-map base.
The example shows both the correct and the incorrect call.

**`btour`** decodes a real packed word -- `inuse:16 | objects:15 |
frozen:1` from a 6.1.134 `struct slab` -- and checks the round trip
closes.  It uses `kdbg.kvar_addr` rather than `gdb.parse_and_eval` to read
`__cpu_online_mask`, because the macro spelling has no symbol and the
variable only resolves once the slide is applied.

**`kfacts`** starts from nothing and asks what the target is.  Run it
before any other example: `CONFIG_SLAB_FREELIST_HARDENED=y` is the reason
`stour` will show encoded freelist pointers, and `CONFIG_INIT_ON_ALLOC_DEFAULT_ON=y`
is the reason a fresh object reads as zeros.

**`atour`** carries one address through all nine views.  The pair worth
comparing is step 3 versus step 4: `kl-pt` is arithmetic and never fails,
`kl-walk` reads memory and stops at the first absent entry, so an address
that gets indices but no walk is unmapped.

**`stour`** reads the allocator from the cache descriptor down to one
object, and ends at the buddy order the slab itself occupies.

**`ytour`** resolves a symbol, reads it raw, reads it typed, and prints
the stack.  Step 1 returning eight symbols for `init_task` is expected --
kallsyms is a substring search, so selecting by exact name is the
caller's job.

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