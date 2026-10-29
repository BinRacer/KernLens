# Naming conventions

KernLens has two naming surfaces:

- the **GDB command line**, where commands must stay short and easy to
  type (`kernlens-walk`, `kl-walk`);
- the **Python API**, where names are read in scripts, test failures,
  and tracebacks, so they must stay readable without becoming long.

The rules below describe both surfaces and are enforced by review, not
by a linter.

## GDB commands

- Canonical commands are `kernlens-<verb>`; the suffix is one or two
  words: `kernlens-slab`, `kernlens-kaslr-offset`.
- Every canonical command has a `kl-<verb>` alias.  Aliases are the
  intended interactive form; canonical names are used in scripts and
  documentation.
- Commands are **not** renamed when the Python API changes.  The
  command layer is a stable user interface; the Python layer is the
  implementation.
- Commands live in `kernlens.commands` (one module per domain) as
  **plain functions** in the pwndbg style: a function named
  `kernlens_<verb>` decorated with `@Command(parser, category, ...)`.
  The framework derives the `kernlens-<verb>` command name from the
  function name (underscores become dashes); the decorator records a
  `CommandDefinition` and `register_all()` instantiates the
  `gdb.Command` wrappers, so no class is written by hand.
- Every command binds an `argparse.ArgumentParser`; `-h`/`--help`
  render the parser (with examples, notes, and the alias list folded
  into the epilog).  Domain functions annotate their options with the
  same names as the argparse `dest`s.
- Ported pwndbg commands keep pwndbg's option spellings -- both the
  long names and the short ones (`-p/--progs`, `-p/--pcp-only`,
  `-b/--break`, `-r/--range`) -- and pwndbg's metavars (`<vaddr>`,
  `<paddr>`), so a line copied from a pwndbg workflow keeps working.
  KernLens-only options are added in the same style, and options that
  pwndbg does not have (`kl-base --rebase`, `kl-slab --detail`) stay
  functional but are registered through `framework.hide()` so `--help`
  shows only the pwndbg surface.

## Modules and packages

- Packages are short, lower-case nouns: `core`, `output`, `gdb`,
  `commands`, `inspectors`.
- Modules are `snake_case` and name one concern: `bitops.py`,
  `codec.py`, `paging.py`, `palette.py`, `walker.py`.
- A package may group many small modules under a private-prefixed
  shared base (`inspectors/_base.py`); the underscore marks it as
  internal plumbing rather than a domain module.
- A package's `__init__.py` re-exports its public surface; it may contain
  lazy import wiring but no domain logic.
- Every module owns one implementation; there are no historical
  re-export modules at the package root.

## Example files

Examples are not library modules: a reader meets one before knowing what
it is for, and the filename is the only description available in a
directory listing, a traceback or a `git diff`.  So they carry one extra
piece of information -- what kind of thing the file is.

**`<subject>_<kind>.py`**, lower-case `snake_case`, no digits-only
subjects, no verbs standing in for kinds.

| Kind | The file | Its product |
| --- | --- | --- |
| `_tour` | installs one command and prints a sequence of sections | a walkthrough of one subject |
| `_walk` | installs one command and follows a structure link by link | the chain it traversed |
| `_tracer` | installs breakpoints that never stop the debuggee | a log |
| `_bp` | installs a breakpoint whose purpose is to stop, or to decide | one trap |
| `_snapshot` | computes a report from constants, with no target | a table |
| `_sample` | the smallest thing that works | a starting point to copy |

| File | Subject | Kind |
| --- | --- | --- |
| `api/address_tour.py` | page-table views of one address | `_tour` |
| `api/installed_api_tour.py` | the names `gdbinit.py` installs | `_tour` |
| `api/kernel_facts_tour.py` | identity of the target | `_tour` |
| `api/freelist_walk.py` | the SLUB freelist encoding | `_walk` |
| `api/slab_snapshot.py` | a slab report from constants | `_snapshot` |
| `api/hello_sample.py` | the minimum viable script | `_sample` |
| `tracing/gdb_tracer.py` | `kfree` arguments | `_tracer` |
| `tracing/cve_2025_38616_tracer.py` | one CVE's UAF chain | `_tracer` |
| `breakpoints/conditional_bp.py` | one object's frees | `_bp` |
| `breakpoints/per_cpu_bp.py` | per-CPU addressing | `_bp` |

Exempt: `api/gdbinit.example` is a dotfile fragment, not a script.

The kind is not decoration -- it is the first thing a reader needs and
the last thing a filename tends to say.  `trace.py` named neither its
subject nor its kind; it is now `installed_api_tour.py`, and the rename
is the whole argument for the rule.  `gdb_tracer.py` keeps its subject
(`gdb`) only because it is the *generic* tracer that other tracers are
modelled on; a file about a specific subsystem names the subsystem.

`tools/check_examples.py --check` enforces the pattern, so a new example
with an unclassified name fails the build rather than being discovered
later.

## Import paths

- `from kernlens import ...` is the convenient public surface for the
  pure-Python core and output layers.
- `from kernlens.core.<module> import ...` and
  `from kernlens.output import ...` are the canonical layer imports.
- GDB code uses `from kernlens.gdb.facade import kdbg`; component
  modules such as `kernlens.gdb.walker` are imported directly when only
  one adapter component is needed, and the kernel subsystem mixins live
  under `kernlens.gdb.inspectors`.
- GDB commands live in `kernlens.commands`; `gdbinit.py` only bootstraps
  them.
- Do not add compatibility aliases or re-export modules; new code uses
  these canonical paths.

## Python API

### Classes

- `PascalCase`, noun-first: `PageTableWalker`, `KernelDebugger`,
  `MemoryReader`, `SlubInspector`.
- Kernel acronyms are written as words: `CpuInfo`, `Kaslr`,
  `SlubInspector`.
- `KAddr` and `KPageTable` are established exceptions; do not add new
  `K`-prefixed classes.

### Functions and methods

- `snake_case`, verb-first for actions: `read_*`, `write_*`,
  `print_*`, `walk`, `kvar_addr`, `decode_*`.
- Predicates start with `is_` / `has_`: `is_present`, `is_direct_map`.
- Formatters start with `fmt_` or are short nouns inside a formatter
  namespace: `fmt_line`, `IntFmt.addr`, `Styler.hex64`.
- Converters use `<source>_to_<target>`: `virt_to_phys`,
  `phys_to_pfn`.
- Readers use `read_*`; a reader that returns a kernel address uses
  `kvar_addr` rather than a second `read_*` verb.
- Avoid the `get_` prefix on simple queries: `counters()`, not
  `get_counters()`.
- One concept, one spelling: do not mix `format_` and `fmt_`, `typ`
  and `int_type`, or `offset` and `off` inside the same layer.

### Variables and parameters

- `snake_case`; noun plus unit where it matters: `kaslr_offset`,
  `page_size`, `byte_count`.
- Single letters are allowed only as loop indices (`i`, `j`) or
  conventional math names (`x`, `y`).
- Booleans read as assertions: `color_enabled`, `five_level`,
  `in_partial`.
- Private module state and helpers start with `_`; constants are
  `UPPER_SNAKE`.

### Abbreviations

These are part of the house style and may be used without expansion:

```
addr  off   len   nr    cur   prev  cfg   ctx   buf   tmp   ptr
val   ret   err   pfn   pte   pgd   pud   pmd   p4d   va    pa
phys  virt  kaslr percpu slub kvar  freeptr fmt  bt    kv    id
u8 u16 u32 u64 i8 i16 i32 i64 le be
```

Everything else is spelled out.  In particular, do not add C-library
abbreviations such as `clz`, `ctz`, `ffs`, `fls`, `rotl`, `rotr`, or
`bswap` to the public API; the readable forms are `leading_zeros`,
`trailing_zeros`, `first_set`, `last_set`, `rotate_left`,
`rotate_right`, and `byte_swap`.

### Length

- Target two words, tolerate three.
- A public name longer than ~20 characters needs a reason; prefer a
  shorter noun (`cpu_slab_ptr`, not `cpu_slab_template_pointer`).
- Private helpers may be longer when the extra words prevent a bug,
  but the same abbreviation table applies.
