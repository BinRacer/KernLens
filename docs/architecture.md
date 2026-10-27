# Architecture

**KernLens** (`kernlens`) is a small, dependency-light toolkit for Linux
kernel debugging from Python and GDB.  It is deliberately split into a
pure-Python core that can be unit tested anywhere and a GDB adapter that
keeps `gdb`-dependent modules out of the core import path.  Importing
`kernlens` or `kernlens.gdb` is safe outside GDB; resolving a component
that imports `gdb` requires a debugger session.

## Goals

- **Pure Python core.** Encoding, bit math, address classification,
  page-table arithmetic, formatting, and logging work without GDB,
  Linux, or a target kernel.
- **Explicit state.** Pure helpers are static and module-level state is
  immutable.  Mutable state lives in explicit `Logger`, `Styler`,
  `DebugConfig`, adapter-component, and `kdbg` instances.
- **Predictable 64-bit semantics.** Pointer and page-table helpers mask
  inputs to 64 bits, so negative Python integers behave like the
  corresponding unsigned kernel values.
- **Validate at the boundary.** Public helpers reject impossible
  widths, alignments, type codes, and offsets instead of silently
  producing nonsense.
- **Plain-text output.** The formatters return `str`; color is an
  opt-in decoration, never a structural requirement.
- **Test without a debugger.** The GDB adapter is integration-tested
  against a fake `gdb` module.

## Naming

GDB commands are the short, stable surface: `kernlens-<verb>` plus a
`kl-<verb>` alias.  The Python API uses one readable, medium-length
style — `snake_case` functions, `PascalCase` classes, no cryptic
C-library abbreviations, and no overlong project-specific names.  The
full rules and abbreviation table live in [`naming.md`](naming.md).

## Repository layout

```
.
├── src/kernlens/
│   ├── __init__.py       # public re-exports and __version__
│   ├── core/
│   │   ├── constants.py  # layout constants
│   │   ├── validation.py # boundary validators
│   │   ├── bitops.py     # BitOps / BITS
│   │   ├── codec.py      # IntCodec / ByteOrderCodec / LE / BE
│   │   ├── fmt.py        # IntFmt
│   │   ├── addr.py       # KAddr
│   │   └── paging.py     # KPageTable
│   ├── output/
│   │   ├── palette.py    # Palette (raw ANSI)
│   │   ├── colors.py     # semantic colour roles
│   │   ├── levels.py     # LogLevel
│   │   ├── logger.py     # Logger
│   │   └── styler.py     # Styler
│   ├── commands/
│   │   ├── __init__.py   # package exports + registry accessors
│   │   ├── framework.py  # @Command framework: argparse + guards + registry
│   │   ├── formatting.py # shared output/parse helpers
│   │   ├── help.py       # GROUP_ORDER + kl-help overview / detail renderers
│   │   ├── overview.py   # kl-status
│   │   ├── kernel_base.py# kl-base / kl-kbase / kl-kaslr(-offset)
│   │   ├── memory.py     # kl-slab (list/info/contains/details) / kl-sym / kl-bt / ...
│   │   ├── metadata.py   # kl-kcmdline / kl-kversion / kl-kconfig / ...
│   │   ├── misc.py       # kl-cpu / kl-percpu / kl-msr / kl-color
│   │   ├── paging.py     # kl-addr / kl-page / kl-pt(e) / kl-walk / ...
│   │   └── primitives.py # kl-bits / kl-int
│   ├── gdb/
│   │   ├── __init__.py   # lazy component exports
│   │   ├── _types.py     # Pyright protocols
│   │   ├── config.py     # DebugConfig
│   │   ├── styler.py     # KernelStyler
│   │   ├── reader.py     # MemoryReader
│   │   ├── symbols.py    # SymbolResolver
│   │   ├── kaslr.py      # Kaslr
│   │   ├── kbase.py      # Kbase / IDT-based text base recovery
│   │   ├── cpu.py        # CpuInfo
│   │   ├── walker.py     # PageTableWalker / PageWalk / WalkLevel
│   │   ├── btf.py        # self-contained BTF type parser (no libbpf)
│   │   ├── layouts.py    # verified fallback struct layouts
│   │   ├── kernel.py     # KernelInspector (thin composition of inspectors/)
│   │   ├── inspectors/   # one module per kernel subsystem
│   │   │   ├── _base.py      # InspectorBase + shared read primitives
│   │   │   ├── metadata.py   # version / cmdline / CONFIG_*
│   │   │   ├── modules.py    # modules list + sys_call_table
│   │   │   ├── structpage.py # x86_64 struct page
│   │   │   ├── kallsyms.py   # embedded symbol table
│   │   │   ├── dmesg.py      # printk_ringbuffer
│   │   │   ├── bpf.py        # prog_idr / map_idr
│   │   │   ├── buddy.py      # buddy free lists / zone metadata
│   │   │   ├── slabcache.py  # SLUB cache list / object lookup
│   │   │   └── dmabuf.py     # dma-buf + scatterlists
│   │   ├── slub.py       # SlubInspector
│   │   ├── api.py        # public API bootstrap for sourced scripts
│   │   └── facade.py     # KernelDebugger / kdbg + _BINDINGS table
│   └── py.typed          # PEP 561 marker
├── tests/
│   ├── contract_spec.py  # frozen external-contract constants
│   ├── unit/             # pure-Python tests
│   └── integration/      # adapter + gdbinit tests with fake modules
├── docs/
│   ├── architecture.md   # layout, API map, and design notes
│   └── naming.md         # command and Python naming rules
├── gdbinit.py            # thin bootstrap sourced by GDB
├── examples/
│   ├── slab_snapshot.py  # pure-Python report
│   ├── gdb_tracer.py     # GDB breakpoint / command example
│   ├── trace.py          # script sourced after gdbinit.py
│   ├── cve_2025_38616_trace.py  # CVE-specific KTLS tracer
│   └── gdbinit.example   # sample ~/.gdbinit
├── images/banner.svg
├── pyproject.toml
├── uv.lock
└── CHANGELOG.md
```

## Public API map

The package root is a convenience surface, not a compatibility layer:
it re-exports the pure-Python core and output names.  The GDB adapter is
opt-in and uses canonical submodule imports.  There are no historical
module aliases.

| Import | Main public names | Needs GDB |
|--------|-------------------|-----------|
| `from kernlens import ...` | `BitOps`, `IntCodec`, `IntFmt`, `KAddr`, `KPageTable`, `Logger`, `Palette`, `Styler`, constants | no |
| `from kernlens.core import ...` | same core names at their canonical layer | no |
| `from kernlens.output import ...` | `Logger`, `LogLevel`, `Palette`, `Styler`, `colors` | no |
| `from kernlens.commands import ...` | `Command`, `CommandCategory`, `registry`, `register_all`, `GROUP_ORDER` | yes |
| `from kernlens.gdb import ...` | lazy component exports such as `DebugConfig`, `MemoryReader`, `KernelDebugger` | when a gdb-backed name is resolved |
| `from kernlens.gdb.api import ...` | `install_public_api`, `core_functions`, `FACADE_FUNCTIONS`, `kdbg` | yes |
| `from kernlens.gdb.facade import kdbg` | `KernelDebugger` composition and the `kdbg` singleton | yes |

```python
from kernlens import BitOps, IntCodec, IntFmt, KAddr, KPageTable

# Inside a GDB Python session:
from kernlens.gdb.facade import kdbg
```

The core and output layers never import `gdb`; `output` also does not
import `core`.  This is enforced by `tests/unit/test_structure.py`.

## Dependency graph

```
core.constants / core.validation
   ├── core.bitops ── core.codec
   ├── core.fmt ───── core.codec
   ├── core.addr
   └── core.paging

output.palette
   ├── output.colors
   ├── output.levels
   ├── output.logger
   └── output.styler

gdb._types / gdb.config
   ├── gdb.styler ── output
   ├── gdb.reader
   ├── gdb.symbols ── output
   ├── gdb.kaslr
   ├── gdb.kbase ── core.addr
   ├── gdb.walker ── core.paging
   ├── gdb.cpu
   ├── gdb.inspectors.* ── core.addr, gdb.reader
   ├── gdb.kernel ── gdb.inspectors.*
   ├── gdb.slub ── output
   └── gdb.facade ── every component

commands.framework ── gdb.facade, output.message, output.tree
   ├── commands.formatting ── gdb.facade, output.colors
   ├── commands.overview / kernel_base / memory / metadata / misc /
   │   paging / primitives ── commands.framework
   └── commands.help ── commands.framework (registry passed in)
```

There are no import cycles.  `core.codec` is dependency-free;
`core.bitops` and `core.fmt` import it; `output` is independent of
`core`; the `gdb` components import only `core.*`, `output`, and their
sibling modules, and `gdb.facade` composes all of them.  The
`commands.framework` module owns the `@Command` decorator, the
`CommandDefinition` record, the `OnlyWhen*` guards, and the registry;
the domain modules import it (plus `commands.formatting`) and never
`commands.help` — `help.py` reads the registry through
`framework.registry()` instead of importing the command modules.

## Module responsibilities

### `core.constants` / `core.validation`

- Page and pointer constants: `PAGE_SHIFT`, `PAGE_SIZE`, `PAGE_MASK`,
  `PTR_BITS`, `PTR_HEX_DIGITS`, `PTR_MASK`.
- x86-64 address-space boundaries: `KERNEL_BASE`, `KERNEL_BOTTOM`,
  `PAGE_OFFSET_BASE`, `VMEMAP_BASE`, `VMALLOC_START/END`,
  `MODULE_START/END`, `USER_TOP`, `MAX_ERRNO`.
- Validation helpers: `check_bits`, `check_pow2`, `check_nonneg`.

The modules are pure data/validation; public constants are re-exported
by `kernlens/__init__.py`.

### `core.bitops`

A stateless namespace of integer bit operations.  Inputs are masked to
the requested width before operating; methods that take an explicit
width validate it.  Families:

- byte swap (`byte_swap`, `byte_swap16/32/64`);
- width reinterpretation (`sign_extend`, `truncate`, `to_u*`, `to_i*`,
  `coerce`);
- width metadata (`mask`, `sign_bit`, ranges);
- population and scans (`popcount`, `leading_zeros`, `trailing_zeros`, `first_set`, `last_set`);
- power-of-two and logarithms;
- rotation;
- alignment;
- single bits and bit fields;
- `cpumask` word helpers.

`BITS` is the conventional short alias.

### `core.codec`

Byte-order-aware integer <-> bytes conversion built on `struct`.  The
statics take a trailing `byteorder` keyword.  `ByteOrder` is the enum of
`"<"` / `">"`; `IntType` describes the eight integer types (4 widths x
2 signednesses) and exposes `code`, `width`, `bits`, `signed`, `mask`,
`min_value`, and `max_value`.

`ByteOrderCodec` binds one order to the statics (`LE.pack_u16(...)`).
The `byteorder` parameters accept either a `ByteOrder` member or a
bound codec, so `IntFmt.bytes_u16_array(data, byteorder=LE)` and
`IntCodec.pack_u16(value, BE)` both work.

Validation is delegated to `struct` for range and buffer-size errors;
negative array counts are rejected explicitly.

### `core.fmt`

Integer and byte-string formatting on top of `IntCodec`.  It returns
plain strings and has no color or logging dependency.  It covers
addresses, sized hex, offsets, human-readable sizes, `ERR_PTR`-style
flags, percentages, timestamps, durations, byte hex/ASCII/C-string
views, hexdumps, and typed array formatting.

### `core.addr`

x86-64 address classification and direct-map translation:

- user/kernel and canonical checks (48-bit and 57-bit);
- direct map, vmemmap, vmalloc, module, and text ranges;
- virtual <-> physical and pfn <-> page conversions;
- page alignment;
- KASLR link/runtime conversion;
- `ERR_PTR` encode/decode;
- pointer tag extraction.

All inputs are masked to 64 bits.  The layout constants assume a
reasonably recent x86-64 Linux with a 64 TiB direct map and 52-bit
physical addresses; callers can pass explicit bases/sizes where the
kernel configuration differs.

### `core.paging`

Pure page-table geometry and PTE decoding.  It never reads memory.
It supports 4-level and 5-level paging, index extraction, splitting a
virtual address into indices plus offset, canonicalization, entry
address computation, PTE flag decoding, huge-page alignment/base
helpers, and physical-address reconstruction for 4 KiB, 2 MiB, and
1 GiB leaves.

### `gdb.walker.PageTableWalker`

`KPageTable` is pure arithmetic, so it cannot translate a live address.
`PageTableWalker` closes that gap without moving memory access into the
core: it reads 8-byte entries through `MemoryReader`, starting at
`$cr3` (falling back to `init_top_pgt` / `swapper_pg_dir`) and choosing
4-level or 5-level geometry from `CR4.LA57`.

`walk(va, *, five_level=None, root=None)` accepts explicit roots and
paging modes for replaying captured tables and returns a frozen
`PageWalk` with one `WalkLevel` per decoded level, the final physical
address, the leaf size (4 KiB / 2 MiB / 1 GiB), and a `note` when the
walk stopped early.  Unreadable, absent, and non-present entries do not
raise, because the walker is usable from breakpoint callbacks.  The
`kernlens-walk` command is the GDB frontend (per-level detail) and
`kernlens-pagewalk` mirrors pwndbg's deepest-level-first presentation
with an optional `--pgd` root override.

### `output.Logger` / `output.Styler`

`Logger` is a small severity-leveled writer with level filtering,
prefix control, stream injection, `once` / `throttle` / `counter`
state, checks, banners, and rules.  `Styler` owns all presentation:
colors, alignment, key/value pairs, containers, tables, boxes, columns,
blocks, highlights, and progress bars.

`Styler` never requires color.  With `color_enabled=False`, every method
returns the same plain text that the colored path wraps in SGR
sequences.  Layout methods share `fill`, `aligns`, and
`max_col_width`; box drawing uses Unicode by default but accepts custom
characters and joints.

`output.colors` maps *meaning* onto raw ANSI sequences (a field label is
always `LABEL`, a tri-state flag `TRUE` / `FALSE` / `MISSING`, and so
on).  The command-layer formatting helpers read these roles, so a
restyle touches one file instead of every command module.

### `gdb/` components

The GDB adapter is split by responsibility.  Only the modules that
touch the debuggee import `gdb`; `config.py` and `styler.py` stay
debugger-independent:

| Module | Responsibility |
|--------|----------------|
| `config.py` | KASLR slide, header width, indentation, freelist scan limit |
| `styler.py` | kernel-specific symbol/location/SLUB formatters on top of `Styler` |
| `reader.py` | safe expression/memory reads with self-healing KASLR translation |
| `symbols.py` | pc -> symbol, `file:line`, backtrace, call chain |
| `kaslr.py` | breakpoint specs and link-time `_text` |
| `kbase.py` | IDT gate decoding and runtime kernel text-base recovery |
| `cpu.py` | CPU count, online mask, current CPU, per-CPU offsets |
| `walker.py` | `CR3`-based walks, 4/5-level selection, huge-page leaves |
| `btf.py` | self-contained BTF parser (`.BTF` in the image, or `btf_path`); no `libbpf`/`bpftool` |
| `layouts.py` | the verified fallback struct layouts used only when no DWARF **and** no BTF is available |
| `inspectors/` | one mixin per kernel subsystem (see below); each owns its constants, dataclasses, and methods |
| `kernel.py` | `KernelInspector`, a thin composition of the `inspectors/` mixins behind one object |
| `slub.py` | `struct page`/`struct slab` decoding, freelists, partial lists, slab block printing |
| `facade.py` | `KernelDebugger` composition, the `_BINDINGS` table, and the `kdbg` singleton |

`KernelDebugger` composes one instance of each component and republishes
the commonly used methods directly onto the facade.  The republication
is driven by a single `_BINDINGS` table (125 rows of `(public_name,
component, member, free_function)`); `api.FACADE_FUNCTIONS` and
`api.INSTANCE_NAMES` are derived from it, so the public surface is
declared exactly once.  Component accessors (`kdbg.logger`,
`kdbg.styler`, `kdbg.reader`, `kdbg.symbols`, `kdbg.kaslr`, `kdbg.kbase`,
`kdbg.cpu`, `kdbg.walker`, `kdbg.kernel`, `kdbg.slub`) remain available.

`KernelDebugger.indent` is bound to the `Styler.indent` text formatter;
the configuration prefix is exposed separately as `indent_str` to avoid
a name collision on the facade.

### `gdb/inspectors/`

`KernelInspector` used to be a 1.6k-line class.  It is now split by
kernel subsystem: each `InspectorBase` subclass is a mixin that owns its
domain's constants, dataclasses, and methods, and `KernelInspector`
combines them behind one API.

| Module | Subsystem |
|--------|-----------|
| `_base.py` | `InspectorBase` (reader + byte/word reads, `_cstring`, `_walk_list`, `vmemmap_base` / `page_offset_base`) and `_ByteReader`; also the three-tier struct-offset resolver |
| `metadata.py` | `linux_banner`, `saved_command_line`, the `IKCFG` `CONFIG_*` image |
| `modules.py` | the `struct module` list and `sys_call_table` |
| `structpage.py` | x86_64 `struct page` type/refcount packing |
| `kallsyms.py` | the embedded `kallsyms` table (token expansion + addresses) |
| `dmesg.py` | the `printk_ringbuffer` (`printk_rb_static`) and `tk_core` |
| `bpf.py` | BPF `prog_idr` / `map_idr` (xarray walk) |
| `buddy.py` | `node_data[].node_zones[].free_area[]` and zone/node metadata |
| `slabcache.py` | the global `slab_caches` list and object->cache lookup |
| `dmabuf.py` | the dma-buf list (`debugfs_list` / `db_list`) and scatterlists |

Every mixin declares `__slots__ = ()`; the cache slots live only on
`KernelInspector` (multiple bases with non-empty slots would raise
"instance lay-out conflict").  `tests/unit/test_structure.py` enforces
the package shape and that the inspectors never import `kernel`,
`facade`, or `api`.

#### Struct-offset resolution

Nothing may hardcode a struct field offset, because the layout depends
on the kernel version and on `CONFIG_*` (for example `CONFIG_SECURITY`
inserts `void *security` before `struct bpf_map::map_type`, moving it
from `0x10` to `0x18`).  The inspectors call
`InspectorBase._layout_offset(type, path)` / `_layout_sizeof(type)`,
which resolve through a three-tier chain and cache the result:

1. **DWARF** -- `gdb.parse_and_eval` on the loaded `vmlinux`;
2. **BTF** -- `gdb/btf.py` parsing the image's `.BTF` section (or
   `reader.config.btf_path`); BTF is real type information, so a hit
   here is *not* a fallback and does not warn;
3. **the registry** -- `gdb/layouts.py`, whose `StructVariant` entries
   are gated on `version_min`/`version_max` and `CONFIG_*` predicates.

The resolvers pass the registry value as the `default` argument of
`_offset_of` / `_sizeof`; the base records the key in `_fallbacks` the
first time a default is used, and `CommandDefinition.invoke` prints one
`message.warn` per struct type (via `framework.warn_fallback_layouts`)
when that set is non-empty.  `reset()` clears the offset cache, the
fallback report, and the cached BTF handle.

Only the *loaded* image's BTF is consulted -- never the host's -- so a
cross-kernel session cannot silently borrow the wrong layout.
`tools/gen_layouts.py` regenerates and verifies the registry against a
real kernel.

### `commands/`

The GDB commands follow pwndbg's convention.  A command is a plain
function named `kernlens_<verb>` decorated with
`@Command(parser, category=..., aliases=[...], examples=..., notes=...)`
and (optionally) a guard:

```python
_parser = argparse.ArgumentParser(description="Displays the loaded modules.")
_parser.add_argument("module_name", nargs="?", default=None)

@Command(_parser, category=CommandCategory.KERNEL_METADATA, aliases=["kl-kmod"])
@OnlyWithKernelSymbols
def kernlens_kmod(module_name: str | None = None) -> None:
    ...
```

The framework (`commands/framework.py`) reproduces pwndbg's semantics:

- the decorator records a `CommandDefinition` (function, parser,
  category, aliases, examples, notes) and derives the command name from
  the function name, so the registry is populated without a
  hand-maintained list;
- `-h`/`--help` print the parser, whose epilog carries the examples,
  notes, and alias list;
- a guard that fails prints `message.error(...)` and returns instead of
  raising, and any `gdb.GdbError` from the body is reported as
  `message.error` and swallowed — a command never aborts the session;
- `register_all()` instantiates one `gdb.Command` subclass per
  definition (plus one per `kl-` alias) and is idempotent, so sourcing
  `gdbinit.py` twice is safe.

Output uses the pwndbg `print` idiom with the shared
`output.message` (`error`/`warn`/`hint`/`notice`/`success`/`info`/`on`/
`off`) and `output.tree.IndentContextManager` helpers.  `commands/help.py`
renders the grouped `kl-help` overview from the categories and the
per-command detail from the parser; it reads the registry through the
framework, so it never imports the domain modules.  `gdbinit.py` is
only a bootstrap: it imports the package, calls `register_all()`, and
installs the public Python API.

## Loading inside GDB

Normal package import:

```python
import sys
sys.path.insert(0, "/path/to/repo/src")
from kernlens.gdb.facade import kdbg
```

Importing `kernlens.gdb` itself is safe outside GDB; its public names are
resolved lazily from their own modules.  Resolving a component that
imports `gdb` (`reader`, `symbols`, `kaslr`, `kbase`, `cpu`, `walker`,
`slub`, `facade`) requires a debugger session; `config` and `styler` do
not.

`gdbinit.py` is a thin bootstrap: it imports `kernlens.commands`, which
registers the `kernlens-*` commands and their `kl-*` aliases, then calls
`register_all()`.  The complete command table, aliases, and invocation
examples live in the [project README](../README.md); `kl-help` lists
them grouped by category and `kl-help kl-<command>` (or
`kl-help kernlens-<command>`) shows one in detail.

It also calls `kernlens.gdb.api.install_public_api()` with its own
globals.  GDB sources Python files into `__main__`, so a later
`source trace.py` can use `KAddr`, `KPageTable`, `IntFmt`, `kdbg`,
`read_kvar`, `walk`, `sym`, `head_to_page`, `print_slab`, `find_kbase`,
and the other names in `FACADE_FUNCTIONS` without imports.  Stateless
core methods are also exported as free functions (`byte_swap64`,
`popcount`, `pack_u16`, `virt_to_phys`, `split_4`, ...) from `BitOps`,
`IntCodec`, `KAddr`, `KPageTable`, and `IntFmt`; `core_functions()`
returns that mapping.
Class-qualified access (`BitOps.byte_swap64`), identifier-safe aliases
(`BitOps_byte_swap64`), and dotted keys in `KERNLENS_QUALIFIED` are
available when collision-free names are preferred.  Stateful
components (`logger`, `styler`, `config`, `reader`, `symbols`, `kaslr`,
`kbase`, `cpu`, `walker`, `slub`) are installed as the default instances owned
by `kdbg`; `KERNLENS_INSTANCES` maps them, and `KERNLENS_CLASSES`
supports constructing independent instances.  Constructors allocate
fresh state (for example a new `Logger` has its own counters and
minimum level); mutating a local instance never changes the global
defaults.  `KERNLENS_API` records the installed mapping.  This is a
GDB-only bootstrap; ordinary host code should import from `kernlens` or
`kernlens.gdb` explicitly.

## SLUB inspection model

`SlubInspector` targets contemporary SLUB layouts:

1. **Head -> page.**  For a direct-map object address, subtract
   `page_offset_base`, shift by `PAGE_SHIFT` to get a pfn, and add
   `pfn * sizeof(struct page)` to `vmemmap_base`.
2. **Tail -> head.**  A `struct page` with `compound_head & 1` is a tail
   page; clear the low bit to recover the head.
3. **Cache.**  `struct slab.slab_cache` points at the `kmem_cache`; the
   cache name is read as a C string.
4. **Counters.**  `struct slab.counters` packs `inuse:16`,
   `objects:15`, and `frozen:1`.
5. **Freelist.**  `kmem_cache.offset` is the freeptr slot.  A value
   of `0` is valid: SLUB stores the pointer at the start of the object
   for ordinary caches.  When `CONFIG_SLAB_FREELIST_HARDENED` is on,
   the stored word is `ptr ^ random ^ swab(ptr_addr)`; `decode_freeptr`
   inverts that.  `freelist_dist` walks the chain with a scan limit
   and cycle detection.
6. **Partial lists.**  `kmem_cache.node[node].partial` is a
   `list_head`; the slab is recovered by subtracting the `slab_list`
   offset.  `in_partial` scans with a bound and cycle guard.

Per-CPU slabs are read through `kmem_cache.cpu_slab` plus
`__per_cpu_offset[cpu]`.  `print_slab` prints the head, per-CPU
freelists, node partial lists, and the head slab's freelist chain.

The code assumes the kernel has `struct slab` (5.17+) and the usual
`page_offset_base` / `vmemmap_base` symbols.  Kernels with a different
SLUB layout need a small adapter rather than changes to the generic
core.

## Error handling and limits

- Public pure-Python helpers raise `ValueError` for invalid widths,
  alignments, counts, offsets, and ranges.
- `IntCodec` lets `struct.error` propagate for overflow and short
  buffers.
- GDB-facing readers return `None` when a read fails; callers decide
  whether that is fatal.
- Page-table walks are bounded by the paging level count (4 or 5) and
  return a `note` instead of raising on an unreadable or missing entry.
- Freelist walks are bounded by `DebugConfig.freelist_scan_limit`
  (default 4096) and detect cycles.  Partial-list scans are capped at
  10,000 links and stop on the list head or a repeated link.
- KASLR is self-healing.  `MemoryReader` applies `DebugConfig.kaslr_offset`
  to KASLR-aware reads and, when the slide is unset (or a read fails at
  it), asks the facade's IDT-based detector for the current slide and
  retries.  A link-time read is tried last, so a debugger that already
  carries the relocation (`add-symbol-file vmlinux <runtime>`) still
  works.  Whenever the slide changes the reader fires an `on_change`
  hook that drops `KernelInspector`'s address-derived caches, which is
  what makes every ported command follow a KASLR change without a manual
  `kl-base`.  `kl-base` and `kl-kbase --set` remain the explicit,
  user-facing way to pin the slide; `kl-kaslr` / `kl-kaslr-offset`
  override it by hand.

## Testing strategy

- **Unit tests** cover every pure-Python module, including validation
  errors and boundary values.
- **Integration tests** install a fake `gdb` module before importing
  `kernlens.gdb.facade`.  The fake implements `parse_and_eval`,
  `execute`, `find_pc_line`, `newest_frame`, and `error`, and provides a
  deterministic memory/symbol model.  `tests/integration/test_gdb_facade.py`
  covers `MemoryReader`, `SymbolResolver`, `Kaslr`, `CpuInfo`,
  `SlubInspector`, `PageTableWalker`, and the facade without a live
  kernel, including complete 4-level and 5-level walks over synthetic
  tables.
- `tests/integration/test_gdbinit.py` executes the real `gdbinit.py`
  against a recording fake `gdb` and a stub facade, covering command
  registration, aliases, argument validation, and output formatting.
- `tests/contract_spec.py` freezes the observable external contract
  (the canonical command set, the facade's bound names, the installed
  free functions, and the component instances).  `tests/unit/test_contract.py`
  checks the constants are self-consistent, and both integration suites
  assert that the live registry, aliases, facade, and public API match
  the frozen set — so the internal package layout can be restructured
  without silently changing the public surface.
- **Examples** are intentionally small and can be run as smoke tests
  (`uv run python examples/slab_snapshot.py` from a checkout).

Development is managed with uv.  `uv sync` installs the project and the
`dev` dependency group from the committed `uv.lock`; run tests with
either runner inside that environment:

```bash
uv sync
uv run pytest --cov=kernlens
uv run python -m unittest discover -s tests/unit
uv run python -m unittest discover -s tests/integration
```

## Runtime requirements

- Python 3.10+.
- Linux x86-64 kernel targets.
- GDB built with Python 3.10+ (the adapter uses the standard GDB Python
  API; no debugger-specific extension is required).
- UTF-8 terminal for the default box-drawing and progress characters;
  custom `chars` / `joints` are available for ASCII-only terminals.
- `typing_extensions` is only required on Python < 3.12 (for
  `typing.override`).