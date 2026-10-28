# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-28

### Added

- **The startup file ships in the package, and `kernlens` is a console
  script.**  `gdbinit.py` used to live beside `src/`, which is why the
  wheel could not work and why a test forbade install commands.  The
  bootstrap moved to `src/kernlens/gdbinit.py` as package data; it adds
  the parent of its own package (`src/` in a checkout, `site-packages` in
  a wheel) to `sys.path`, so GDB's embedded Python can import KernLens
  even when it cannot see the interpreter that installed it.  The root
  `gdbinit.py` is a shim that calls `bootstrap()` with the namespace GDB
  sourced, so existing `~/.gdbinit` lines keep working.  `[project.scripts]`
  adds `kernlens path`, `install`, `doctor`, and `version`;
  `tools/check_wheel.py` fails when a built wheel omits the startup file
  or the entry point, and CI builds the wheel to run it.  Verified by
  installing the wheel into a clean venv and sourcing it in a GDB that
  could not import that venv: `KernLens 0.3.0 loaded`.
- **`kernlens install` writes the same marked block as `install.sh`.**
  The block and the startup path live in `src/kernlens/install.py`, so
  the shell installer and the console script cannot disagree about the
  markers, and `tests/unit/test_install.py` compares the two spellings.
  `kernlens install --uninstall` removes only the block and leaves the
  rest of `~/.gdbinit` byte-for-byte intact.

- **One command installs a checkout, and one command checks it.**
  `install.sh` clones to `${XDG_DATA_HOME:-~/.local/share}/kernlens`,
  writes a single marked block into `~/.gdbinit`, and leaves a
  `kernlens` wrapper in `~/.local/bin`; re-running it updates the
  checkout instead of appending a second block, and `--uninstall`
  removes the block and the wrapper without touching the checkout.
  `kernlens doctor` (also `python -m kernlens.doctor`) reports the host
  Python, the Python GDB embeds, whether `~/.gdbinit` sources an
  existing startup file, whether a real `gdb --batch` can import
  `kernlens`, and whether a target is attached.  `kl-status --doctor`
  adds the in-session half (objfile, DWARF/BTF, inferior) as a flag
  rather than a 41st command, so the frozen command surface is
  unchanged.  `InstallScriptTests` (8) run the installer against a local
  git repository: clone, idempotent rewrite, dry run, wrapper, and
  uninstall.
- **The front page shows the tool running, and the command table is
  generated.**  `docs/assets/demo.svg` is an animated terminal replaying
  `kl-walk` and `kl-slab details` from the 6.1.134 capture, with
  `docs/assets/demo.cast` for `asciinema play`; both are rendered by
  `tools/gen_demo.py`, whose `--check` fails when the animation and the
  capture disagree.  The 40-row table moved out of both READMEs into
  `docs/commands.md`, rendered from `tools/tutorial_meta.json` by
  `tools/gen_commands.py --check`, so the page and `kl-help` share one
  order and one source.  `DemoAssetTests` (6) and
  `CommandReferenceTests` (4) pin both.
- **The README's captured output now matches the capture.**  The
  page-walk, 5-level, SLUB, and freelist blocks were typed during an
  earlier front-page rewrite; they now use the exact lines recorded in
  `tools/tutorial_capture.json` (same addresses, same `freeptr` and
  `decoded=` fields), and `ReadmeStructureTests` asserts those markers
  instead of the old hand-written `stored word` text.

- **The `py.typed` marker is now backed by a checker, not just an empty
  file.**  The marker promised that a type checker could read this
  package, but nothing ran one, and `KernelDebugger` republished its whole
  flat surface with `setattr` -- so every `kdbg.info` / `kdbg.print_slab`
  was an attribute error.  That one pattern accounted for 138 of the 202
  errors pyright reported against `src/kernlens`.  The bindings are now
  explicit `self.<name> = self.<component>.<member>` assignments, which
  give each name the component method's real signature and are compared
  against `_BINDINGS` by `test_facade_has_the_single_binding_table`.  CI
  runs `uv run pyright` (standard mode, Python 3.10, reading the `gdb`
  stub from the `types-gdb` dev dependency), and `test_every_function_is_annotated`
  asserts that every function -- including `*args`/`**kwargs` -- still has
  a return and parameter annotation.  The packaging test now also pins
  the `pyproject.toml` and `MANIFEST.in` entries, and the build job
  checks that `py.typed` is really inside both the wheel and the sdist;
  the old test read the marker from `src/` and could not notice a dropped
  `package-data` entry.  The audit also found two defects: `_mapped_root`
  was defined twice in `PageTableWalker` (the first copy was dead), and
  `_StrLike` did not declare `split` although three call sites used it.
- **`kl-bits` and `kl-int` have examples, so the coverage ratchet moves
  from 35/40 to 37/40.**  Both were listed in `UNCOVERED_COMMANDS` with
  the reason "covered as Python API by bitops_tour.py / intcodec_tour.py,
  but the command form has no example of its own" -- which names the gap
  without explaining it, since these are the two commands that need **no
  debuggee at all**.  The barrier was never the missing target; nobody
  had written the file.
  `bits_tour.py` and `int_tour.py` run on the host as scripts and execute
  the real command when sourced inside GDB, so the two paths are compared
  rather than assumed equal.  They also document the conventions that
  cost an afternoon to learn: `first_set`/`last_set` report **1-based**
  bit numbers following the kernel's own `ffs`/`fls` (so `last_set` of 64
  means bit 63), and `cpumask_next` takes the mask first and the CPU
  second (reversing them returns -1 for a non-empty mask).
  The three commands left have reasons that are actually about the
  target: `kl-buddydump` needs free blocks at a known order,
  `kl-kbpf` needs BPF programs loaded, `kl-kdmembuf` needs a DMA-buf
  exporter, and nothing exports on an idle VM.
- **`KernelStyler` has tests.**  The class produces the text of every
  SLUB and symbol line a user reads, and `src/kernlens/gdb/styler.py` sat
  at 27% coverage while its sibling `src/kernlens/output/styler.py` was
  at 99% -- so the gap was not "styling is hard to test".  `KernelStyler`
  inherits from the pure-Python `Styler` and imports no `gdb`, which
  means every method runs on the host with no debugger and no fake.
  `test_kernel_styler.py` (21 tests) checks each formatter twice: with
  colour off, where the output must be the plain text a log file is
  diffed against, and with colour on, where the *choice* of colour is the
  meaning.  A formatter that colours a dangerous value the same as a safe
  one has broken the only thing it was for, and that failure is invisible
  in the plain-text half.  `gdb/styler.py` is now at 100%.
- **The tutorial can be regenerated on a different boot.**  The prose
  named twenty-five invocations with literal addresses, while its own
  docstring said the values "change between boots".  Both statements
  could not hold: re-running `tools/tutorial_capture.py` on a new boot
  produced a capture the prose no longer matched, and
  `gen_tutorial.py` refused to write anything -- so the tutorial could
  only be rebuilt on the machine that first produced it, which is the
  same thing as not being rebuildable.
  Invocations now name boot-dependent values as `{placeholders}`
  (`{direct}`, `{text_addr}`, `{slide}`, `{vmemmap_page}`,
  `{slab_object}`, ...) filled from the capture's own context block.
  `TutorialPlaceholderTests` (3) pin it in both directions: no literal
  may reappear, and no placeholder may name a key the capture lacks.
  Verified by rebooting -- slide `0x14000000` -> `0x17400000`, direct
  map `0xffff8fe6c0400000` -> `0xffff992880400000` -- and regenerating
  all 40 pages without a source edit.
- **The distribution policy is stated, and enforced.**  KernLens is
  installed from a checkout and is not published to PyPI.  The previous
  release commit recorded that as an open question; this closes it, with
  the reason a reader can check: every quickstart path ends at `source
  gdbinit.py`, and `gdbinit.py` is not in the wheel, which is built from
  `src/` alone.  A published package would install cleanly and then be
  unusable by following the documentation -- which reads as a broken
  tool, not an unpackaged one.
  Both READMEs now say so where a reader looks for installation, both
  CONTRIBUTING files carry the reason, and `SourceOnlyDistributionTests`
  (4) makes the reversal fail: no document may offer an install command
  that cannot work, the README must still say `git clone`, the policy
  must still be stated with its cause, and `pyproject.toml` must still
  have no console-script entry point.  That last one is the tripwire --
  shipping `gdbinit.py` as package data later fails the test on purpose,
  so the prose and the packaging have to change together.
- `ReadmeStructureTests` (3 tests) pinning the three properties that
  made the rewrite worth doing: the front page stays under a line
  ceiling, it shows real captured output, and the material moved out of
  it is still reachable from it.  Growing the README back is the easy
  mistake -- appending one more table is always locally reasonable.
- A CI status badge in both READMEs, pointing at the `CI` workflow
  rather than at a hardcoded state, so it reports what actually
  happened on the last run.
- `SECURITY.md`, separating the failure modes this project cares about
  from the ones it does not.  The first category is *confident wrong
  answers* -- a page walk that reports a present mapping that is not
  there, a SLUB decode that names the wrong cache.  A tool that is
  trusted about memory makes a plausible wrong number worse than an
  error.  The document also says what is explicitly *not* a
  vulnerability (a value the command marked as unconfirmed, a
  non-x86_64 kernel, a missing debuggee) so that reports can start at
  the interesting end.
- Issue templates: a wrong-answer template that asks for the comparison
  that makes a report actionable, a bug template that asks for the GDB
  Python version (the tool is imported by GDB's interpreter, not the
  shell's), and a feature template that asks what the command must
  *refuse*.  Plus a PR template whose checklist includes "the tutorial
  was regenerated, not hand-edited".
- The front page was rewritten around measurements rather than layout: it
  opened with the order the modules were built in, put the 40-line
  repository tree second, and contained **zero** captured command output
  in 927 lines.  It now runs to about a fifth of that length, opens with
  real command output, and reaches reference material in `docs/api.md`
  rather than carrying it.  The banner states the 40-command surface and
  a real output fragment instead of a bare gradient wordmark.  The
  figures behind these choices are reproducible with
  `tools/check_examples.py --report`; the reading rules that keep the
  front page short are enforced by `ReadmeStructureTests`.
- `DocumentationTrackingTests` in `tests/unit/test_structure.py` (3
  tests).  The architecture tree drifted twice -- once when the examples
  were regrouped, once when they were renamed -- and both times the
  failure was silent, because a stale filename in prose reads exactly
  like a current one.  The tests check that every name in the tree block
  exists, that every example is listed, and that no document cites a
  rooted path the repository does not have.  `CHANGELOG.md` and
  `CREDITS.md` are exempt: the first is a record of what was once true,
  the second names pwndbg's own files as licence provenance.
- The examples are now *executed* by CI, not merely inspected.  Three
  questions that fail in three different ways, each with its own
  mechanism:
  - `Example.runs_on` in `tools/example_manifest.py` declares where a
    file can run, defaulting to the weaker claim.  `"host"` is a promise
    a test enforces, so a file that quietly stops being portable fails
    instead of keeping a claim nobody checks.
    `check_runner_declarations()` rejects a `host` row that imports
    `gdb` without a fallback, or that reaches for `kdbg.*` outside a
    `try` catching `NameError` -- the handler is what makes the call
    safe, not its absence.
  - `tests/integration/test_examples_pure.py` runs every `host` row in a
    subprocess and asserts the section headings its output must contain,
    so a script printing nothing and exiting 0 fails too.
  - `tools/run_examples_gdb.py` replays the twelve target-dependent
    examples from inside GDB and records what each printed.
    `tools/check_example_capture.py` then checks -- without a kernel --
    that every heading a recorded real run produced is still in the
    source that produced it.  That is the compromise CI needs: it cannot
    re-run these, but it can notice a section renamed out of existence.
- Two examples are declared source-only with a stated reason.
  `trace-start` installs breakpoints and waits for the kernel to reach
  them, so a batch run blocks; `kwatch-field` installs a *hardware*
  watchpoint, which the QEMU gdbstub rejects outright.  Both are still
  sourced, so a tracer that no longer loads is caught.
- `tools/gen_examples_readme.py` generates the coverage block in
  `examples/README.md` from the measurement, and `--check` fails when the
  two drift.  The hand-written version had already gone stale: it claimed
  `facade bound 34/140` when the measured figure was 51.
- 19 tests: `RunnerDeclarationTests` (7, exercising each rejection path
  against a scratch tree, including that a *narrow* `except gdb.error`
  does not count as safe) and `GeneratedCoverageTests` (4).
- `examples/api/freelist_walk.py` (`flwalk`) — the SLUB freelist as an
  *encoding* rather than a report.  It prints the hardening config first
  (`SLAB_FREELIST_HARDENED`, `SLAB_FREELIST_RANDOM`, `INIT_ON_*`),
  then decodes a live `kmalloc-1k` slot three ways: the stored word, the
  decoded pointer, and the XOR arithmetic that relates them, so the
  formula is checkable instead of quoted.  It follows each CPU's chain
  with cycle detection, then shows the compound-head distinction that a
  tail page hides.  This closes `slub` 3/18 -> **18/18**, the only
  facade component of size that is now complete.
- Two real defects were found by running it and are now part of the
  output rather than edited away:
  - Deriving the slab head from an object address by hand lands on a
    tail page for any slab larger than one page, and that page's
    `counters` word reads as zero -- so the object index was right and
    the count was nonsense (`object 3 of 0`).  `cpu_active_slab()` was
    the correct source; the example prints the tail-page reading, the
    `compound_head()` reading and the `cpu_active_slab()` reading side
    by side.
  - `print_slab()` takes an *object* address and walks to the slab
    internally; passing a `struct page` yields `<cannot translate head>`.
- The worked examples record the measured numbers next to the code that
  produces them, and note where execution diverged from the intended
  shape: `slab_tour.py` was not extended, because splitting the ten extra
  bindings across two files would have meant assembling one model from
  two places.
- `UNCOVERED_COMMANDS` reasons for `kernlens-bits` / `kernlens-int`
  corrected.  They said "a tour is planned for Phase 3"; Phase 3
  covered the *primitives* as Python API and the command forms are
  still unexercised, which is what the strings now say.
- Three pure-Python tours that close the core-class coverage completely.
  All three run on the host as well as inside GDB, so their *output* is
  asserted in tests rather than merely their existence:
  - `examples/api/intcodec_tour.py` (`icodec`) — round-trips every
    `pack_*`/`unpack_*` pair in both byte orders, plus the array and
    offset forms.  `IntCodec` 0/21 -> **21/21**.
  - `examples/api/intfmt_tour.py` (`ifmt`) — organised by what the value
    *is* (address, size, byte span, signed/masked, offset, time) rather
    than by method name.  `IntFmt` 4/26 -> **26/26**.
  - `examples/api/bitops_tour.py` (`btour`) — alignment, field packing on
    a real packed `struct slab` word (`inuse:16 | objects:15 | frozen:1`,
    round trip checked), single bits, CPU masks read from a live
    `__cpu_online_mask`, sign extension, rotations, byte order.
    `BitOps` 2/44 -> **44/44**.
- `KAddr` (5/25) and `KPageTable` (5/38) are deliberately not covered yet:
  both need real page-table state to demonstrate honestly, and both are
  declared as deferred in `UNCOVERED_COMMANDS` so the gap is visible in
  the measurement rather than in prose.
- The examples' failure modes are now tested, which forced three fixes:
  - The tours guard command registration with `hasattr(gdb, "Command")`.
    The test suite installs a stub `gdb` that imports but has no
    `Command`, and an example that cannot be imported there cannot be
    tested anywhere.
  - `ByteOrder` and `IntType` are imported unconditionally from the
    package: `gdbinit.py` installs classes and helpers, not the codec
    enums, so probing for them left a `None` branch only GDB could reach.
  - `check_examples._known_bare()` subtracts `builtins`, so a script
    calling Python's `hex()` no longer reads as using the facade's
    `hex()`.  A genuine `kdbg.hex()` call still counts.
- Six workflow examples, each driving a group of commands in the order an
  investigation actually uses them rather than one command at a time.
  Together they take command coverage from 1 of 40 to **35 of 40**, all
  verified against the 6.1.134 test kernel:
  - `examples/api/kernel_facts_tour.py` (`kfacts`) — establish what the target
    is before trusting an address: version, command line, the config flags
    that change how a *value* is interpreted, the hardening checklist,
    modules, the syscall table, symbol lookup and the boot log.
  - `examples/api/address_tour.py` (`atour`) — carry one address through
    all nine page-table views.  Steps 3 and 4 are the pair worth
    comparing: `kl-pt` is arithmetic and never fails, `kl-walk` reads
    memory and stops at the first absent entry, so an address that gets
    indices but no walk is unmapped.
  - `examples/api/slab_tour.py` (`stour`) — allocator state from the
    cache descriptor down to a single object, ending at the buddy order
    the slab itself occupies.
  - `examples/api/symbols_tour.py` (`ytour`) — resolve, read raw, read
    typed, and print the stack.  Step 1 returning eight symbols for
    `init_task` is expected: kallsyms is a substring search, so selecting
    by exact name is the caller's job, and step 2 is how to confirm it.
  - `examples/breakpoints/per_cpu_bp.py` (`pbreak`) — stop in `schedule` and
    read the *right* CPU's copy of a per-CPU variable.  GDB shows one
    thread, so the naive read gives CPU 0's copy whichever CPU took the
    breakpoint: wrong three times out of four, silently.
  - `examples/tracing/kaslr_retarget_tour.py` (`retarget`) — discover and apply
    the KASLR slide, then prove the addresses moved.  Finding the slide is
    not applying it, and that is the step people skip.
- `example_manifest.UNCOVERED_COMMANDS` records the five commands no
  example executes yet, each with a reason: `kl-bits` and `kl-int` belong
  with the primitives tour, while `kl-buddydump`, `kl-kbpf` and
  `kl-kdmabuf` need a workload that an idle VM cannot provide.  A gap that
  is written down is a decision; a gap that is not is an oversight.
- `tools/example_manifest.py` and `tools/check_examples.py` make the
  examples' coverage a checked claim instead of an impression.  The
  manifest is one row per example declaring the API names and commands
  it is responsible for; the checker derives the real surface from the
  source (the facade's `_BINDINGS` literal and the core classes, both
  parsed without importing `gdb`) and fails when a claim and the code
  disagree.  `--report` prints the coverage table and `--list-commands`
  prints the commands no example runs yet.  CI runs `--check` on every
  push, and the report is echoed into the log so a green build says what
  it covers.
  - The checker counts only the first argument of an actual
    `gdb.execute(...)` call as a demonstration.  A command named in a
    docstring or printed in a banner does not count, which is the
    difference between the two numbers that made the previous estimate
    of this gap too generous: grepping suggests 23 of 40 commands
    appear in `examples/`, and one is executed.
  - Constants are excluded by `is_surface_name`: `KPageTable`'s 21
    constant names are already a table in the README, and a row
    mentioning `PTE_NX` would otherwise read as coverage.
  - `REQUIRED_COMMAND_COVERAGE` is a ratchet that may only increase.
    The six workflow examples above raise it from `0` to `35`, and a test
    asserts it equals the measured coverage rather than sitting below it.
  - `tests/unit/test_examples.py` has 51 tests, 11 of them negative --
    a claim without the code, an unknown name, a command only mentioned
    in prose, a missing README link, a ratchet above actual coverage, a
    function that is not really a forwarding wrapper, and a locally bound
    name masquerading as an API reference all fail.
- Four commands gained an option that previously lived on a sibling
  command, so a task no longer needs a detour through the other one.
  Every addition is opt-in: the existing invocations, defaults, and
  output are unchanged, and pwndbg-derived help stays identical.
  - `kl-walk --pgd <table>` (short `-p`) walks a top-level table other
    than the live CR3, so a saved or foreign root can be followed
    without switching to its task.  It is the same option `kl-pagewalk`
    already had.
  - `kl-page --verbose` (short `-v`) adds the full `kl-addr` analysis
    (canonicality, alignment, tags) to the classification output.
  - `kl-bt --chain` selects the compact `kl-chain` presentation, and the
    1-128 depth limit both commands share is now validated once.
  - `kl-kbase --text <addr>` and `kl-kbase --offset <slide>` set the
    KASLR slide at the point where `kl-kbase` already reports
    `kaslr=+0x...`; they are the equivalents of `kl-kaslr` and
    `kl-kaslr-offset`, both of which are kept.  They are registered as a
    mutually exclusive pair and, like the other KernLens-only `kbase`
    extras, hidden from `--help` (documented in the `Notes` section
    instead) so the pwndbg option surface is unchanged.
- `kernlens.gdb.btf`, a self-contained parser for the kernel's BTF type
  information.  It reads the fixed header plus the type and string
  sections and answers ``offset(type, path)`` / ``sizeof(type)``,
  descending named members (``desc_ring.descs``) and following
  typedef/const modifiers.  The blob comes from the loaded image's
  ``.BTF`` section (through GDB, from the inferior or the objfile on
  disk) or, when ``reader.config.btf_path`` is set, from a raw blob or
  any ELF carrying one.  A malformed or absent blob yields ``None``
  rather than raising, so "no BTF" and "no DWARF" behave alike.
- `tools/gen_layouts.py`, which probes a real kernel for the struct
  layouts the fallback registry declares and verifies the registry
  against it.  It reads a `vmlinux` through GDB's DWARF (`--vmlinux`) or
  a BTF blob with the project's own parser (`--btf`, e.g.
  `/sys/kernel/btf/vmlinux` -- no `bpftool`, no `libbpf`);
  `--check` exits non-zero on any drift (including a struct or field the
  probe could not resolve, so an incomplete probe cannot pass silently),
  and the default mode prints a ready-to-paste variant block.  The pure
  helpers (`build_spec`, `compare`, `render`, `probe_btf`) are
  unit-tested, and CI asserts the probe resolves every registry struct
  from the runner kernel.
  - `kl-walk` / `kl-v2p` / `kl-pagewalk` failed with "unreadable pgd
    entry" because `$cr3` is a *physical* address and the page tables
    are only mapped in the direct map.  The walker now maps the root
    and every entry through `page_offset_base`.
  - `kl-kdmesg` decoded no records: the printk ringbuffer field offsets
    were wrong, `text_len` is a `u16` (reading a word folded in the
    neighbouring fields), `seq` was taken from the ring index instead of
    `printk_info.seq`, and an embedded NUL aborted the writer.
  - `kl-ksyscalls` / `kl-klookup` could not name syscalls: GDB's symbol
    table is indexed by *link-time* addresses, so the KASLR slide is now
    removed before `info symbol`.
  - `kl-buddydump` dereferenced the resolved pgdat a second time when
    walking the per-node zones, and `sizeof(struct zone)` was assumed to
    be `0xC00` (it is `0x600` on this build).
  - `kl-msr` raised on targets where `$lstar` cannot be cast to `long`;
    it now falls back to the frame register API and reports an
    unreadable MSR instead of aborting.
  - `kl-kmod` reported "cannot read the modules list" for an empty (but
    valid) module list; it now distinguishes "no modules loaded".
- Self-healing KASLR adaptation.  `MemoryReader` now detects the KASLR
  slide on demand through an IDT-based recovery hook and re-detects it
  when a read fails at the current slide, retrying the read; a link-time
  read is tried last, so a debugger that already carries the relocation
  (`add-symbol-file vmlinux <runtime>`) also works.  A change of slide
  fires an `on_change` hook that resets `KernelInspector`'s
  address-derived caches, which makes every ported command follow a
  KASLR change without a manual `kl-base`.  `kl-base` and
  `kl-kbase --set` remain the explicit way to pin the slide, and
  `kl-kaslr` / `kl-kaslr-offset` still override it by hand.
- pwndbg-derived kernel metadata commands (behaviour adapted from
  pwndbg, MIT — see `CREDITS.md`): `kernlens-kcmdline` / `kl-kcmdline`
  (boot command line), `kernlens-kversion` / `kl-kversion` (version
  banner + parsed release), `kernlens-kconfig [name] [--load <file>]` /
  `kl-kconfig` (the embedded `IKCFG` `CONFIG_*` image),
  `kernlens-kchecksec` / `kl-kchecksec` (hardening `CONFIG_*` audit),
  `kernlens-kmod [name]` / `kl-kmod` (the `modules` linked list, with
  the `struct module` name and `MOD_MEM_*` descriptor offsets recovered
  by scanning), and `kernlens-ksyscalls [name]` / `kl-ksyscalls` (the
  `sys_call_table` with per-entry symbol resolution).  They are backed
  by the `KernelInspector` component (`kernlens.gdb.kernel`, facade
  `kdbg.kernel`), which reads `linux_banner`, `saved_command_line`,
  `kernel_config_data`/`_end`, `modules`, and `sys_call_table` through
  the KASLR-aware reader.
- pwndbg-derived paging commands (behaviour adapted from pwndbg's
  `commands/paging.py`, MIT — see `CREDITS.md`): `kernlens-p2v
  <physical-address>` / `kl-p2v`, `kernlens-v2p <virtual-address>` /
  `kl-v2p`, and `kernlens-pageinfo <struct-page>` / `kl-pageinfo`.
  `v2p` translates through the live page tables (so it works for any
  mapped page), `p2v` uses the direct-map base, and `pageinfo` decodes
  a `struct page`; all three print the `struct page`, its `enum
  page_type`, PFN, and refcount.  New `KAddr.page_to_phys` /
  `KAddr.page_to_virt` supply the inverse translation, and
  `KernelInspector.page_type` / `page_refcount` decode the x86_64
  `struct page` (64-bit only).
- `kernlens-kbase` gained `--rebase` / `-r`, which reloads the loaded
  symbol file at the recovered base (pwndbg's `kbase --rebase`).
- pwndbg-derived paging, symbol, and MSR commands (behaviour adapted
  from pwndbg, MIT — see `CREDITS.md`): `kernlens-pagewalk
  <virtual-address> [--pgd <table>]` / `kl-pagewalk` (pwndbg's pagewalk
  layout: deepest level first with per-level flags, then a
  `pagewalk result` line, with `--pgd` overriding CR3),
  `kernlens-klookup [symbol]` / `kl-klookup` (kallsyms lookup by name
  substring or exact address), and `kernlens-msr [name] [--write <v>]
  [--list] [--range A-B]` / `kl-msr` (x86_64 model-specific registers,
  including a `--list` table from `arch/x86/include/asm/msr-index.h`).
  The kallsyms reader (`KernelInspector.kallsyms()` /
  `KernelInspector.lookup()`, facade `kdbg.kallsyms` / `kdbg.lookup`)
  decodes the embedded `kallsyms_token_table` / `kallsyms_names` stream
  on demand through a chunked reader and hashes address-relative
  `kallsyms_offsets` (or absolute `kallsyms_addresses`) into runtime
  addresses.
- pwndbg-derived ring-buffer, BPF, and buddy-allocator commands
  (behaviour adapted from pwndbg, MIT — see `CREDITS.md`):
  `kernlens-kdmesg [--ctime]` / `kl-kdmesg` (the `printk_ringbuffer`,
  walked from `tail_id` to `head_id`, with optional wall-clock
  timestamps via `tk_core`), `kernlens-kbpf [--progs] [--maps]
  [--verbose] [--values]` / `kl-kbpf` (the XArray behind `prog_idr` and
  `map_idr`, with a program/attach/map-type name table, program
  bytecode, and array-map element values), and `kernlens-buddydump
  [--zone z] [--order n] [--mtype m] [--node n]` / `kl-buddydump` (the
  `node_data[].node_zones[].free_area[].free_list[]` buddy lists, with
  `struct page.lru`'s offset recovered from the zero page).  Backed by
  `KernelInspector.dmesg()` / `tk_epoch()` / `bpf_progs()` /
  `bpf_maps()` / `bpf_map_value()` / `buddy_zones()` (facade
  `kdbg.dmesg` / `kdbg.bpf_progs` / `kdbg.bpf_maps` /
  `kdbg.buddy_zones`), a `MemoryReader.read_bytes` helper, and
  `bpf_prog_type_name` / `bpf_attach_type_name` / `bpf_map_type_name`.
- pwndbg-derived SLUB and dma-buf commands (behaviour adapted from
  pwndbg's `commands/slab.py` and `commands/kdmabuf.py`, MIT — see
  `CREDITS.md`): `kernlens-slabs <list|info|contains> [arg]` /
  `kl-slabs` (walk the global `slab_caches` list to tabulate caches,
  describe one cache's flags and geometry, or map an object address to
  its cache) and `kernlens-kdmabuf` / `kl-kdmabuf` (walk the dma-buf
  global list — `debugfs_list` on >= 6.10, `db_list` before — recovering
  `struct dma_buf`'s field offsets from the first entry and printing each
  buffer's exporter and `system_heap_buffer` scatterlist pages).
  Backed by `KernelInspector.slab_caches()` / `slab_cache()` /
  `slab_object()` / `dmabufs()` and the `SlabCache` / `DmabufEntry` /
  `SgEntry` dataclasses (facade `kdbg.slab_caches` / `kdbg.slab_cache` /
  `kdbg.slab_object` / `kdbg.dmabufs`).
- `kernlens-read-field <address> <type> <path>` / `kl-read-field`:
  read a struct field (including nested paths such as `node[0]`) as an
  integer through `MemoryReader.read_field`.
- `kernlens-help [command]` / `kl-help`: list every command grouped by
  category, or show usage, options, and examples for one command.  Every
  command now also accepts `-h` / `--help` / `help` / `?`.
- Guided usage errors: invalid arguments print a multi-line message with
  the correct usage line and a `kl-help <command>` pointer instead of a
  bare `usage:` string.
- Real `help <command>` output: each command's GDB docstring now carries
  its summary, usage, arguments, and examples, and the `kl-` aliases
  inherit it.
- Added `examples/tracing/cve_2025_38616_tracer.py`, a CVE-2025-38616 KTLS
  use-after-free tracer refactored to use `kernlens.gdb.facade`
  directly instead of loading a separate helper module.
- Added a project-level `gdbinit.py` and `examples/gdbinit.example`.
  Sourcing the startup file from `~/.gdbinit` registers
  `kernlens-status`, `kernlens-slab`, `kernlens-page`, `kernlens-pte`,
  KASLR, and color commands without installing breakpoints.
- Added short `kl-` command aliases (`kl-status`, `kl-slab`, `kl-page`,
  `kl-pte`, `kl-sym`, `kl-bt`, `kl-chain`, `kl-read`, `kl-cpu`,
  `kl-percpu`, `kl-kaslr`, `kl-kaslr-offset`, `kl-color`) while
  retaining every original `kernlens-*` command.
- Expanded the startup commands with symbol resolution, backtrace,
  call-chain, memory-dump, CPU topology, and per-CPU address helpers.
- Added command frontends for the pure-Python helpers: `kernlens-kvar`
  (KASLR-aware global reads), `kernlens-addr` (KAddr), `kernlens-pt`
  (KPageTable), `kernlens-bits` (BitOps), and `kernlens-int`
  (IntCodec / IntFmt).
- Pure-Python package with a standard `src/kernlens` layout, `py.typed`
  marker, and setuptools configuration (`pip install -e .`).
- `kernlens.BitOps` / `BITS`: byte swap, width reinterpretation,
  population/scan, power-of-two, rotation, alignment, bit-field, and
  `cpumask` helpers.
- `kernlens.IntCodec` / `ByteOrderCodec` / `LE` / `BE`: struct-based
  integer packing, unpacking, arrays, and range checks for the eight
  integer types.
- `kernlens.IntFmt`: address/hex/size/offset/flags formatting, byte
  hex/ASCII/C-string views, hexdumps, and typed array formatting.
- `kernlens.KAddr`: x86-64 classification, canonical checks, direct-map
  translation, page alignment, KASLR conversion, `ERR_PTR`, and tag
  helpers.
- `kernlens.KPageTable`: 4-level and 5-level page-table geometry,
  canonicalization, entry addresses, PTE decoding, huge-page helpers,
  and leaf-to-physical reconstruction.
- `kernlens.Logger` / `LogLevel` / `Palette` / `Styler`: severity
  filtering, prefix and stream control, once/throttle/counter state,
  checks, banners, rules, and a full set of ANSI-aware layout helpers.
- `kernlens.gdb.toolkit`: `DebugConfig`, `KernelStyler`, `MemoryReader`,
  `SymbolResolver`, `Kaslr`, `CpuInfo`, `SlubInspector`,
  `KernelDebugger`, and the `kdbg` singleton.  The package supports
  both normal imports and the legacy `exec()` loading mode.
- Slab inspection: head/tail translation, cache names, per-CPU slabs,
  hardened freelist decoding, bounded freelist distance, partial-list
  scanning, and a multi-line `print_slab` report.
- Unit and integration test suites, including a fake `gdb` module that
  exercises the toolkit without a running kernel.
- Architecture documentation, a pure-Python snapshot example, a GDB
  tracer example, and CI configuration.
- `CHANGELOG.md`, `.gitignore`, and project metadata.
- **`py.typed` now measures 1.0 instead of 0.8764.**  The marker has been
  there for a release, but "the checker runs" and "the checker can see
  every exported name" are different claims.  `pyright --verifytypes
  kernlens` counted 173 of 1399 exported symbols as *ambiguous*: 140
  facade bindings whose types were inferred rather than declared, the
  three `Only*` guards, the `kdbg` singleton, and the module-level
  re-exports that carried them.  Each is now a declared type (see
  Changed), and the report is 1399 known / 0 ambiguous / 0 unknown.  That
  number is the promise `py.typed` actually makes: a user's checker sees
  the same thing the package's own checker does.
- **`mypy` is a second gate, with the same `gdb` types as pyright.**  It
  was a blind spot before: without a stub for `gdb` it either skipped the
  package or demanded `type: ignore` comments that the runtime import
  does not need.  `types-gdb` is now a dev dependency, so both checkers
  read one stub, and `uv run mypy` (strict, `files = ["src/kernlens"]`,
  in CI next to pyright) checks the same 57 modules.  It found 74 errors
  on its first run.  Every one was real and fixed rather than silenced:
  nine cache attributes assigned in mixins but declared by no `__slots__`,
  a `**dict` that hid a `BlockLocation` constructor, `int | None` values
  reused as `int`, three redundant casts, and ten `# type: ignore`
  comments in the memory commands that papered over `object`-typed
  parameters -- those are now `SlabCache` / `BpfProg` / `BpfMap`, which
  removed the ignores and made the `array_addr is not None` invariant
  explicit at the function boundary.
- **`tests/unit/test_typing.py` guards the annotations themselves.**  Two
  checks, because static checkers accept annotations that cannot be
  evaluated at runtime: no annotation in any class body may name a member
  of that class (`__slots__: tuple[str, ...]` next to a method called
  `tuple` resolves to the method, not the builtin), and
  `typing.get_type_hints` must succeed for every public class and
  function in the modules that import without GDB.  The static half reads
  the GDB-only modules too, which is where the original break lived.

### Changed

- **`tools/tutorial_meta.json` no longer carries `examples` or `notes`.**
  The snapshot is a dump of each command's parser, and the renderer reads
  exactly six fields from it: `name`, `aliases`, `category`, `summary`,
  `usage`, `options`.  The other two were copies of strings that live in
  the command modules and are rendered from there, so nothing read the
  copies and nothing could notice them going stale -- and they had.
  Six commands disagreed with their own source.  `kernlens-buddy`'s copy
  still read ``` `inf`o` accepts a virtual address ``` where the module
  says `` `kl-buddy info` ``, and carried its notes block as one
  unwrapped line where the module has five.  A reader who opened the
  snapshot to ask "what does this command say?" got a different answer
  from a reader who opened the command -- and the snapshot is the file
  that looks authoritative, being a generated-looking JSON dump.
  Three and a half kilobytes of duplication removed; the 40 tutorial
  pages render identically without it, which is the proof they never
  consumed it.
  `TutorialTests.test_metadata_carries_only_what_the_renderer_reads`
  pins the field set, so the next person who thinks a copy would be
  convenient gets a failure instead of a slow drift.  Verified by adding
  `notes` back to one entry: the test names both the command and the
  field.
- **The README is a front page again.**  927 lines -> 266, in both
  languages, organised around what the tool does rather than how it is
  built:
  - it opens with two captured outputs instead of a module list -- a
    2 MiB page walk that stops at `(huge leaf)`, and a SLUB freelist
    decode showing the stored word and the XOR that relates it to the
    pointer.  The old README contained 34 fenced blocks and **zero**
    lines of command output.
  - the command surface is stated.  "40" did not appear in the file
    before; a reader could not tell what they were buying.  There is now
    a table of all 40, grouped as `kl-help` groups them, generated from
    the registry and the tutorial pages.
  - quickstart is three commands: clone, one line in `~/.gdbinit`,
    `kl-base`.  Contributor setup moved to `CONTRIBUTING.md`.
  - the repository tree and dependency graph moved to
    `docs/architecture.md`, where an equivalent tree already lived.
- `docs/api.md` and `docs/api.zh-CN.md` hold the 317-line API reference
  that was in the middle of the README; `CONTRIBUTING.md` and
  `CONTRIBUTING.zh-CN.md` hold the 110 lines of development notes.  The
  text is moved, not rewritten -- it was accurate.  The `Conventions`
  list went with the API reference, being a set of behavioural
  guarantees about the classes.
- **Every example filename is now `<subject>_<kind>.py`.**  The tree had
  four parallel conventions -- `_tour`, `_tracer` beside `_trace`, a bare
  `_walk`, and seven files with no marker at all -- and `trace.py`
  managed to name neither its subject nor its kind.  A reader meets an
  example before knowing what it is for, and the filename is the only
  description available in a listing, a traceback or a `diff`.
  - `api/hello.py` -> `api/hello_sample.py`
  - `api/trace.py` -> `api/installed_api_tour.py` (it demonstrates the
    names `gdbinit.py` installs; `trace` said nothing)
  - `api/kernel_facts.py` -> `api/kernel_facts_tour.py`
  - `tracing/cve_2025_38616_trace.py` -> `tracing/cve_2025_38616_tracer.py`
  - `tracing/kaslr_retarget.py` -> `tracing/kaslr_retarget_tour.py`
  - `breakpoints/{conditional,watchfield,per_cpu}.py` -> `..._bp.py`
- The kind set is `_tour`, `_walk`, `_tracer`, `_bp`, `_snapshot` and
  `_sample`; `docs/naming.md` tabulates every file against it, and
  `check_examples.check_example_names()` fails the build on an
  unclassified name or a kind with no subject.  The one exemption
  (`api/gdbinit.example`, a `~/.gdbinit` fragment rather than a script)
  is a data entry, so a new non-script file has to be a deliberate act.
- `gdb_tracer.py` keeps the generic subject `gdb` on purpose: it is the
  tracer other tracers are modelled on, and a file about a specific
  subsystem names the subsystem.
- The `examples/` tree is now grouped by intent: `examples/api/` for
  scripts written against the API, `examples/tracing/` for breakpoints
  that log and keep running, and `examples/breakpoints/` for breakpoints
  whose whole purpose is to stop.  The existing scripts moved unchanged
  apart from their self-references (`slab_snapshot.py`, `trace.py`, and
  `gdbinit.example` into `api/`; `gdb_tracer.py` and
  `cve_2025_38616_tracer.py` into `tracing/`), and every path that named
  them -- `gdbinit.py`, `MANIFEST.in`, the CI workflow, both READMEs,
  and `docs/architecture.md` -- follows.  Each directory carries a
  README that starts from the question the reader actually has, and
  `examples/README.md` routes between them.
  - New `examples/api/hello_sample.py` is the smallest useful script: it shows
    where the installed names come from, how to fall back to importing
    `src/` when run outside GDB, and four pure-Python calls.  It prints
    the same eight lines in both contexts.
  - New `examples/breakpoints/conditional_bp.py` installs
    `kbp-object <address>`, a `kfree` breakpoint that stops only for one
    object.  It compares the slab object start rather than the raw
    argument, because `kfree` legitimately receives interior pointers.
  - New `examples/breakpoints/watchfield_bp.py` installs
    `kwatch-field <type> <field> <address> --expect N`, which reports
    only the transition into a chosen value.  QEMU's gdbstub implements
    no hardware watchpoints, so the command catches `gdb.error` and
    names that limitation instead of surfacing the bare rsp error.
- `kl-help` now requires a namespaced argument.  `kl-help kl-walk` (and
  `kl-help kernlens-walk`) work; a bare `kl-help walk` is rejected with a
  hint naming the `kl-` spelling.  KernLens registers `kl-*` and
  `kernlens-*` only, precisely so its commands never collide with GDB's
  own, and accepting a bare name in the help text undid that -- `kl-help
  print` would have answered "no command matches" while GDB's own `help
  print` works, and `kl-help slab` reads like a question about a GDB
  command.  The rejected query is answered with the form that does work:
  ```
  kernlens-help: no command matches 'slab' -- names are namespaced, so
  try 'kl-slab'; run 'kl-help' for the full list
  ```
  - This drops the never-working `kl-help -slab` spelling, which argparse
    read as an option and rejected.  The previous test only passed because
    it matched the `usage:` line argparse printed on its way out.
- Invalid arguments now print one guided message on every failure path:
  a missing required argument, an unknown option, a bad `--range`, a
  mutually exclusive pair, and a `type=` converter that raises.  The
  README had documented this since the command layer landed, but only the
  converter path was implemented; the rest fell through to argparse's own
  bare usage line and, worse, `ArgumentParser.error` ends in
  `sys.exit`, which would have closed the GDB shell.  The parser's
  `error` is now replaced with a variant that raises and is caught inside
  `invoke`, so the failure never leaves the command:
  ```
  kl-walk: error: the following arguments are required: va
  usage : kernlens-walk [-h] [-p ROOT] va [{4,5}]
  try   : kl-help kl-walk  (detailed help and examples)
  ```
  - The message and the pointer use the `kl-` alias, not the canonical
    `kernlens-` name, matching how the commands are documented.
- The CI actions were bumped off the deprecated Node 20 runtime (GitHub
  removed Node 20 from the runners on 2026-09-23, so every run warned
  that `checkout@v4`, `setup-python@v5` and `setup-uv@v6` were being
  forced onto Node 24): `actions/checkout@v7`,
  `actions/setup-python@v7` and `astral-sh/setup-uv@v10.3.2`, all of
  which declare `runs.using: node24`.
  - `setup-uv` is pinned to an exact version on purpose: the project
    stopped publishing rolling major aliases after `v7` (`@v10` does not
    exist, and `@v7` would miss three majors of fixes).
  - A `.github/dependabot.yml` now tracks the `github-actions` and `uv`
    ecosystems weekly, so the next runtime migration arrives as a
    reviewable PR instead of as a warning on every run.
- CI is now `concurrency`-guarded (`ci-<workflow>-<ref>`,
  `cancel-in-progress`), so a burst of pushes to a branch cancels the
  superseded run instead of queueing several full matrices.  It can also
  be started by hand (`workflow_dispatch`), and a `push` that only
  touches prose (`CHANGELOG.md`, `CREDITS.md`, `LICENSE`, `docs/**`,
  `images/**`, `examples/gdbinit.example`) no longer runs the suite.
  - The two READMEs are deliberately **not** in `paths-ignore`: both are
    asserted by `tests/integration/test_gdbinit.py` (their command tables
    must match the frozen contract), so a README edit has to run the
    suite.
  - The filter is on `push` only.  Applying it to `pull_request` as well
    would leave a required check permanently "pending" on a doc-only PR,
    because no run would ever be created to satisfy it.
- Architecture refactor with no user-visible behaviour change (every
  command, alias, and public name is byte-for-byte the same):
  - `gdb/kernel.py` (previously a ~1.6k-line class) is now a thin
    `KernelInspector` composition over `gdb/inspectors/`, with one
    mixin per kernel subsystem (`metadata`, `modules`, `structpage`,
    `kallsyms`, `dmesg`, `bpf`, `buddy`, `slabcache`, `dmabuf`) sharing
    a common `InspectorBase` and its read primitives.
  - The 40 command classes moved out of `gdbinit.py` (3.3k → ~160 lines)
    into a `kernlens.commands` package, then reworked into pwndbg's
    function style: each command is a plain `kernlens_<verb>` function
    decorated with `@Command(parser, category, aliases=[...])`.
    `commands/framework.py` owns the decorator, the `CommandDefinition`
    record, the `OnlyWhen*` guards, and `register_all()` (idempotent),
    so `gdbinit.py` is only a bootstrap.  `-h`/`--help` print the
    per-command `argparse` help (examples, notes, and aliases folded
    into the epilog) and a failing guard or `gdb.GdbError` prints a
    `message.error(...)` line instead of aborting the session.
  - `output/message.py` and `output/tree.py` add pwndbg's `message`
    helpers (`error`/`warn`/`hint`/`notice`/`success`/`info`/`on`/`off`)
    and the indenting-tree context manager used by the command output.
  - The facade's public surface is now declared once, in a single
    `_BINDINGS` table in `gdb/facade.py`; `gdb/api.py` derives
    `FACADE_FUNCTIONS` and `INSTANCE_NAMES` from it instead of keeping
    parallel hand-maintained lists.
  - Semantic colour roles moved to `output/colors.py`, so the command
    formatting helpers no longer repeat raw `Palette` members.
  - `tests/contract_spec.py` freezes the external contract (commands,
    facade bound names, installed free functions, component instances);
    both integration suites assert the live surfaces match it.
- The ported pwndbg commands now use pwndbg's exact option names and
  metavars, so `kl-*` lines can be copied from pwndbg workflows verbatim:
  - `kl-slab` absorbs the old `kernlens-slabs` command (`list [filter]`,
    `info <name>...`, `contains <addr>...`) with pwndbg's `-v/--verbose`,
    `-c/--cpu`, `-n/--node`, `-p/--partial`, and `-a/--active`, and shows
    both lists for `info` like pwndbg does.  A bare address still prints
    a single slab, and the kernlens-only granular inspector is now
    reachable as `kl-slab details <addr> [-c <cpu>]`.
  - `kl-kbpf` takes pwndbg's `-v/--verbose`, `-b/--break <n>`, and
    `-p/--progs` / `-m/--maps` short options.
  - `kl-buddydump` takes pwndbg's `-z/--zone`, `-o/--order`,
    `-m/--mtype`, `-p/--pcp-only`, `-c/--cpu`, `-n/--node`,
    `-f/--find`, and `--MIGRATE_TYPES`.
  - `kl-kbase` takes `-r/--rebase` and `-v/--verbose`; the kernlens-only
    `--set` / `--phys` / `--idt` remain available but are hidden.
  - `kl-msr` takes pwndbg's `msr` positional plus `-w/--write`,
    `-l/--list`, and `-r/--range A-B` (a single-ended range is rejected
    with pwndbg's message), and evaluates the explicit MSR before the
    range exactly as pwndbg does.
  - `kl-kmod` gained `-l/--load <path>` (loads a module's symbols at its
    runtime base), and `kl-klookup` gained `-a/--apply` (KernLens reads
    kallsyms live, so it explains that the symbols are already current).
  - `kl-pagewalk <vaddr>`, `kl-p2v <paddr>`, and `kl-v2p <vaddr>` use
    pwndbg's metavars.
- The integration fixtures and their command arguments now come from the
  real test kernel (Linux 6.1.134 as built for the pwn4kernel VM) rather
  than invented stand-ins.  A fixture that no longer matches the kernel
  the code targets now fails here instead of surfacing as a surprise on a
  live session:
  - boot-invariant facts are used verbatim and were re-verified across
    successive boots: link-time symbol offsets from `System.map`
    (`_text`, `divide_error`, `kfree`, `commit_creds`, `__x64_sys_read`/
    `write`/`open`, `sys_call_table`, `modules`, `jiffies`), the
    zero-based per-CPU offsets (`current_task`, `__per_cpu_start/_end`),
    `sizeof(struct page)` (64), the banner/release, the `CONFIG_*`
    values, and the `syscall` count (451).
  - KASLR-relocated addresses are a **sample boot**: they are derived as
    `link + slide` (with `_text` as a link-time base), exactly as the
    kernel does.  The direct-map/vmemmap bases (`page_offset_base`,
    `vmemmap_base`) and `__per_cpu_offset[0]` are kernel *variables*
    filled in from the physical memory map -- also boot-chosen, so they
    are sample-boot values too, not `link + slide`.
- The examples use the same real-environment values, and
  `examples/slab_snapshot.py` grew `--page-offset-base` / `--vmemmap-base`
  so a report can be pointed at any kernel (the library defaults describe
  a generic nokaslr kernel):
  - `slab_snapshot.py` now renders a real direct-map page
    (`page_offset_base + 0x120000`) with the real 4 KiB PTE the live page
    tables hold for it and the real `kmalloc-1k` cache shape, so its
    `pgd/pud/pmd/pte` and `leaf phys` match a genuine page-table walk.
  - `trace.py` reports on a real mapped direct-map address instead of an
    invented one, so its split/walk lines reflect the test kernel.
  - `gdb_tracer.py` documents that its `kfree`/`$rdi` default is the
    validated hook point.
- `examples/tracing/cve_2025_38616_tracer.py` is validated end to end against the
  **real** PoC: with the tracer armed, running `/home/ctf/exploit` in the
  guest produces the complete KTLS use-after-free chain (write/`splice`
  merging into one skb A, the `tcp_ack` release that leaves
  `H->dataref == 1`, the deferred free, the `tls_strp_msg_hold` clone
  that hands the freed page to `n`, and the `skb_free_head` of `n` -- the
  double free).  The host-side `BUG: Bad page map` / `Bad page state`
  markers corroborate it.
- The GDB commands now expose the memory-inspection surface that was
  previously unreachable, while staying true to "commands inspect a
  debuggee": `kl-slab --detail [--cpu <id>]` prints the granular SLUB
  inspector output (head->page, cache, freeptr offset/random, decoded
  next pointer, per-CPU slabs/freelists, and partial lists), `kl-kbase
  --idt [count]` dumps decoded IDT gates, `kl-read --mode ascii`
  hexdumps raw bytes, and `kl-read-field <address> <type> <path>` reads
  a struct field.  `kl-kvar` accepts a leading `&` only (symbols, not
  raw addresses).
- Pure-arithmetic, codec, and formatting helpers are intentionally
  **not** command options: they stay available to sourced scripts
  (`trace.py`) through `kernlens` / `kdbg` and are not surfaced as
  `kl-bits --op`, `kl-int --mode pack/unpack/fmt`, `kl-pt --entry`, or
  `kl-addr --virt/--kaslr`.  The underlying `BitOps`, `IntCodec`,
  `IntFmt`, `KAddr`, and `KPageTable` methods are unchanged.
- GDB command output is now colored consistently.  Previously only a
  few fragments were styled (`kl-slab`, `kl-bt`, `kl-help`, `kl-status`,
  and the symbol/location fields of `kl-sym` / `kl-read`), while the
  labels and numeric values of the other commands printed as plain
  terminal text.  Every command now colors its field labels (cyan),
  addresses and hex values (dim), decimal counts (bright cyan),
  booleans (green / red), and symbols / notes through the shared
  `kdbg` styler, so the display matches the `kl-slab` / `kl-help`
  style.  `kl-color off` still produces byte-identical plain text.
- Command argument placeholders no longer use terse abbreviations.
  `<expr>` is now `<address>`, `<va>` is `<virtual-address>`, `<pte>` is
  `<page-table-entry>`, `<bit>` is `<bit-index>`, `<bits>` is `<width>`,
  and `<runtime-_text>` is `<runtime-text-address>`, consistently across
  the commands, `kl-help`, READMEs, and examples.
- `docs/architecture.md`: public API map, dependency boundaries, and
  corrected GDB loading/import notes; `docs/naming.md` is now the
  maintained naming reference.
- `kernlens.gdb.walker.PageTableWalker` (facade:
  `kdbg.walk`), plus the frozen `PageWalk` / `WalkLevel`
  results.  Walks start at `CR3` (falling back to `init_top_pgt` /
  `swapper_pg_dir`), select 4-level or 5-level geometry from
  `CR4.LA57`, decode every level, and reconstruct 4 KiB, 2 MiB, and
  1 GiB leaves.  Unreadable or non-present entries end the walk with a
  `note` instead of raising.
- `kernlens-walk <virtual-address> [4|5]` / `kl-walk` GDB command that
  prints the full walk and the final physical address.
- `kernlens.gdb.kbase.Kbase` and `kernlens-kbase [--set] [--phys]` /
  `kl-kbase`: recover the runtime kernel text base from decoded x86-64
  IDT gates.  The finder uses the link-time IDT-stub symbol, QEMU's
  `monitor info mem` mapping, or 2 MiB text alignment, and can apply
  the detected KASLR slide with `--set`.
- `kernlens-base` / `kl-base`: automatic base selection.  It shows and
  applies the runtime base when a kernel is running, falls back to the
  default link-time base and zero slide otherwise, and can be run again
  safely after a reboot/re-attach.  `kl-kaslr` and `kl-kaslr-offset`
  remain the manual overrides.
- `examples/tracing/cve_2025_38616_tracer.py`: now loads without adding `src/`
  to `sys.path` or importing `kernlens`; it reuses the API and commands
  installed by `gdbinit.py` and calls `kdbg` methods directly without
  per-file aliases.  `trace-start` runs the registered
  `kl-base` command, while `trace-start manual` keeps a manual
  `kl-kaslr` / `kl-kaslr-offset` selection.  Event formatting now uses
  the keyword-only color arguments of `Styler.kv` / `kv_int`, and a
  manual zero slide is rejected before installing breakpoints.  The
  high-frequency `[defer?]` path still prints every A_clone decision line
  but no longer prints a backtrace; backtraces remain on the key
  wake/release/kfree nodes.  `kaslr-text` / `kaslr-offset` are kept as
  compatibility wrappers for the registered `kl-kaslr*` commands.
- `tests/integration/test_gdbinit.py`: executes the real `gdbinit.py`
  against a recording fake `gdb` and a stub facade, covering command
  and alias registration, argument validation, KASLR/color handling,
  and output formatting.
- `pythonpath = ["src"]` in the pytest configuration so the suites run
  from a bare checkout, without an editable install.
- `kernlens.gdb.api` and `KERNLENS_API`: `gdbinit.py` now installs the
  public Python API (`KAddr`, `KPageTable`, `IntFmt`, `kdbg`, and
  selected facade free functions) into GDB's `__main__` namespace, so a
  later `source trace.py` can use them without imports.  Stateless core
  helpers are exposed as free functions as well (`byte_swap64`,
  `popcount`, `pack_u16`, `virt_to_phys`, `split_4`, ...), with
  class-qualified access (`BitOps.byte_swap64`), identifier-safe aliases
  (`BitOps_byte_swap64`), and `KERNLENS_QUALIFIED` dotted keys to avoid
  collisions.  Stateful components (`logger`, `styler`, `reader`,
  `slub`, ...) are installed as the default `kdbg` instances;
  `KERNLENS_INSTANCES` maps them and `KERNLENS_CLASSES` exposes
  constructors that allocate independent state.  See
  `examples/trace.py`, `FACADE_FUNCTIONS`, and `core_functions()`.
- Reorganized the package into three layers: `core/` (pure Python),
  `output/` (palette, levels, logger, styler), and `gdb/` (one module
  per adapter component plus a facade).  Imports now use
  `kernlens.core.*`, `kernlens.output`, and `kernlens.gdb.facade`.
- Renamed the public Python API to one readable, medium-length style;
  GDB commands and aliases are unchanged.  Highlights: `bswap*` →
  `byte_swap*`, `clz`/`ctz`/`ffs`/`fls`/`rotl`/`rotr` →
  `leading_zeros`/`trailing_zeros`/`first_set`/`last_set`/
  `rotate_left`/`rotate_right`, `read_kernel_u64` → `read_kvar`,
  `walk_page_table` → `walk`, `level_5x` → `five_level`.  The naming
  rules are documented in `docs/naming.md`.
- Documentation and the 0.1.0 changelog entries now use the KernLens
  name consistently.
- `kernlens-pte <page-table-entry> [virtual-address]` now labels bit 7
  as `PS/PAT` and, when a virtual address is supplied, prints the 4 KiB,
  2 MiB, and 1 GiB leaf translations instead of assuming a 4 KiB leaf
  (which mis-translated huge entries).
- `IntCodec`'s `byteorder` parameters are annotated as
  `ByteOrder | ByteOrderCodec`, matching the documented behaviour and
  the rest of the API.
- Development is now managed with uv: the dev dependencies use a PEP 735
  dependency group, `uv.lock` is committed, and the documented commands
  and CI use `uv sync` / `uv run`.
- Moved the package from a flat `src/` directory to `src/kernlens/` so the
  distribution name, import name, and src layout agree.
- `kernlens.gdb` exports component names lazily, so importing the package
  outside GDB no longer fails.
- `Styler.box` gained a `joints` keyword; `Styler.block` gained a
  `vertical` keyword.
- `Styler.pad` now rejects unknown alignment tokens.
- **The facade's 140 bindings are declared `Final`, not restated.**  A
  plain `self.info = self.logger.info` is invisible to
  `--verifytypes` as a declaration, so the flat surface counted as
  ambiguous even though pyright could read the signature.  `Final`
  marks it as declared *and* keeps the inferred signature -- parameter
  names and defaults included -- so nothing is copied by hand and nothing
  can drift from the component.  A `Callable[[str], None]` annotation was
  measured and rejected for that reason: it loses keyword names, so
  `kdbg.info(message="...")` stops type-checking.
- **`Command` and the three guards preserve the decorated signature.**
  `Command.__call__` was `Callable[..., Any]` on both sides, so every
  command body was untyped the moment it was decorated.  It is now
  generic over `ParamSpec`/`TypeVar`.  The guards were plain closures
  with inferred types; they are now a `_Guard` `Protocol` with a generic
  `__call__`, which is the only spelling that both declares a type for
  `--verifytypes` and keeps `def kmod(module_name: str | None = None)` a
  real signature.
- **`BlockLocation` is constructed with explicit keywords.**  The buddy
  walk built a `base_fields` dict and splatted it into three
  `BlockLocation(**base_fields, ...)` calls; mypy cannot check a
  constructor through `**dict`, so a missing or misspelled field was
  invisible to both checkers.  The five shared fields are written out at
  each call site.
- **All cache slots live in `InspectorBase.__slots__`.**  Each mixin used
  to be free to add its own, but two sibling bases with non-empty
  `__slots__` make the concrete class uninstantiable ("multiple bases
  have instance lay-out conflict").  The block is now in the one base all
  mixins share, which also lets each mixin be checked alone.  The
  `_page_is_enum` cache had no slot at all; see Fixed.

### Removed

- Removed the legacy root modules (`BitOps.py`, `IntCodec.py`,
  `IntFmt.py`, `KAddr.py`, `KPageTable.py`, `Logger.py`, `_Internal.py`)
  and `gdb/toolkit.py`.  Use `kernlens.core.*`, `kernlens.output`, and
  `kernlens.gdb.facade` instead.
- Removed the one-off `docs/project-review.md` report; the maintained
  references are `docs/architecture.md`, `docs/naming.md`, README, and
  this changelog.

### Fixed

- **`kernlens doctor` could report a successful load when the startup
  file had failed.**  The probe ran `source "..."`, but GDB's `source`
  does not strip quotes: it looked for a file whose name began with a
  quote, printed a warning, and continued to the next `-ex`.  The import
  then succeeded only because the checkout launcher exports
  `PYTHONPATH`, which the probe inherited.  The source line is now
  unquoted (GDB takes the rest of the line as the path, so spaces work),
  and `run_command` drops `PYTHONPATH`/`PYTHONHOME` so the check stands
  on the startup file alone.  The shell installer had the same quoting
  bug and is fixed with it.
- **`typing.get_type_hints(Styler)` raised `TypeError`.**  The class
  exposes formatting methods called `tuple`, `dict`, `list`, `set` and
  `range`, and nine annotations in the class body used those bare names.
  Annotations are evaluated in the class namespace, so
  `__slots__: tuple[str, ...]` resolved to the *method* and the
  subscript failed -- while pyright and mypy both accepted it, because
  they resolve the builtin.  The annotations now say
  `builtins.tuple[...]`, so the class works for `dataclasses`,
  `typing.get_type_hints`, and documentation tools that evaluate them.
- **The per-session page-encoding probe was never cached.**  `_page_is_enum`
  was assigned inside `try/except AttributeError`, but no class declared
  the name in `__slots__`, so the assignment always failed and the cache
  never took effect -- every call re-walked DWARF and BTF.  The slot now
  exists on `InspectorBase`, the assignment is unconditional, and
  `KernelInspector.__init__` / `reset` put it in the "not probed" state.
- **The two guards over `docs/architecture.md` were blind in three
  separate ways, and each one was found only by deleting a file.**
  `test_every_name_in_the_tree_exists` checks that every filename the
  tree block lists really exists; `test_doc_paths_name_real_files` does
  the same for rooted paths in the prose.  Both reported success while
  checking almost nothing.
  1. The pattern was ``[\w.]+\.(?:py|md|...)``.  A hyphen is not in
     ``\w``, so a hyphenated name matched nothing at all, and
     ``py.typed`` was skipped for its second dot.  The comment above it
     claimed the opposite -- "anchored at a word boundary start so a
     hyphenated long name is matched whole rather than from its last
     segment" -- which described an intent the code never implemented.
  2. Removing the hyphen problem by whitelisting extensions still could
     not match ``py.typed`` or ``gdbinit.example``, whose tails are not
     extensions.  And leaving the slash out of the class meant the
     rooted-path guard matched nothing, because every path it looks for
     starts with ``src/`` or ``docs/``.
  3. With the pattern fixed, the bare-name search went through
     ``Path.rglob`` over the whole checkout -- including ``.venv``, which
     ships ``py.typed`` for six of its own packages.  Deleting the real
     ``src/kernlens/py.typed`` therefore failed no test, because six
     other files by that name still resolved.
  Measured at each stage, deleting one file at a time: before, removing
  ``docs/naming.md`` failed two tests while removing two other documents
  the tree listed as current failed none.  After, deleting ``py.typed``,
  ``docs/naming.md`` and ``docs/api.md`` each fails, and restoring them
  passes.
  Both guards now share ``doc_filenames()`` (one pattern, with the
  hyphen, the slash and a free-form tail) and ``path_exists()``, which
  skips ``.venv``/``build``/``__pycache__``.  The pattern errs wide on
  purpose: a false positive fails a test that runs on every commit, while
  a false negative passes forever.  The one token that legitimately names
  nothing in this repository, ``~/.gdbinit``, is listed by name.
  Still deliberately unchecked: a *bare* name shared by more than one
  real file.  Deleting the root ``README.md`` fails no test because
  ``examples/README.md`` and four others are real, and the tree block
  does not say which directory it meant.  The guard cannot resolve that
  without a directory column in a hand-drawn tree; it is a limit, not a
  bug, and it is why ``test_every_example_appears_in_the_tree`` exists as
  the narrow counterpart.
- **`kl-help <command>` collapsed the examples into one line.**
  ``argparse`` re-wraps ``epilog`` as running prose by default, so the four
  invocations written for `kl-buddy` came out as two lines that break in the
  middle of a command name (`kl-` at end of line, `buddy info` at the start
  of the next), and the blank line separating `Notes:` from `Examples:`
  disappeared entirely.  Every command carrying examples or notes was
  affected, which is 30 of the 40.
  ``Command`` now installs a ``_CommandHelpFormatter`` that returns
  ``description`` and ``epilog`` verbatim while still wrapping option help,
  so the shape the author wrote is the shape the user reads.  The notes
  blocks lost their implicit wrapping at the same time; they carry explicit
  line breaks now.
- ``kl-buddy``'s notes said ``` `inf`o` ``` where it meant ``kl-buddy info``:
  a backtick pair opened inside another, so the rendered text was the literal
  string with a stray backtick in it.
- **Three tests were order-dependent and passed only by accident.**
  ``message.notice`` colourises the ``Examples:`` / ``Notes:`` / ``Alias:``
  labels, so the raw epilog is a string with an SGR sequence wrapped around
  ``Alias:``.  The assertions compared that against plain text, which worked
  when an earlier test had switched colour off for the whole process and
  failed whenever the class ran alone -- ``pytest -k FrameworkHelperTests``
  was red on a tree that ``pytest`` called green.  A module-level ``plain()``
  strips SGR sequences, and the four epilog assertions use it.
- ``HelpRenderingTests`` (5) render the parser and read the resulting lines,
  which is what the existing ``assertIn`` checks could not do: every string
  was present in the epilog while the rendered help was unusable.  Removing
  the formatter fails 4 of them.  The tutorial was re-captured on the test VM,
  so `docs/tutorial/kl-help.md` shows the real layout rather than the one
  the prose described.
- **`SECURITY.md` claimed the tool was read-only; one command writes.**
  ``kl-msr --write`` runs ``gdb.execute("set $reg = ...")``, which changes
  the target.  The claim was load-bearing -- it was the sentence defining
  what counts as unsafe behaviour against the target -- so a reader
  deciding whether to trust the tool with a live kernel was reading
  something false.
  The policy now names the exception and says it is opt-in, never taken
  as a side effect of a read.  Both READMEs say the same where they
  describe command behaviour.  ``WriteAccessClaimTests`` (3) keep the
  code and the prose from disagreeing again: the tool must still have a
  write path, the policy must name it, and neither README may drop it.
- `docs/architecture.md` listed `api/trace.py`, which the rename in the
  previous commit had removed, and its tree block had lost its column
  alignment.  The tree also omitted `docs/tutorial/` and the three
  READMEs under `examples/`.  Rewritten against the real tree and
  re-aligned.
- `docs/architecture.md` and both root READMEs told a reader to
  `source trace.py`, a file that no longer exists.  The snippets now name
  a file the reader creates (`my_script.py`) and point at
  `examples/api/installed_api_tour.py` for a working version -- which is
  what the snippet was always illustrating: any file sourced after
  `gdbinit.py` inherits the installed names.
- The coverage prose claimed `tests/unit/test_examples.py` had 63 tests
  in two places; it had grown to 85.  Those counts now live in the test
  file itself, where they cannot outlive it.
- `tools/run_examples_gdb.py` reported a false mismatch across boots.
  Its shape digest hashed section headings verbatim, so
  `kernel identity (slide +0x16200000)` differed on the next boot --
  because the slide had changed, which is the one thing guaranteed to
  change.  Addresses and counts are now placeholders, so the record
  survives a reboot while a renamed section still fails.  Both
  properties are pinned by `ExampleCaptureShapeTests`.
- `examples/api/freelist_walk.py` had four defects that only a live
  target exposed.  All four produced *confident, plausible* output rather
  than an error, which is why none of them showed up in a green build:
  - **The hardening report inverted itself.**  `kconfig_get()` returns
    `"y"`, `"n"`, `"m"` or `None` -- a string, never a bool -- and the
    example tested it for truthiness, so every option set to `n` printed
    as `y`.  On the test kernel that meant claiming
    `INIT_ON_FREE_DEFAULT_ON` was *on*, i.e. freed objects zeroed, while
    the chain below it was visibly intact.  The options are now printed
    by value.
  - **`kconfig_get()` returning `None` is not the same as `"n"`.**  The
    config parser keeps only `NAME=value` lines, so `# X is not set` is
    dropped: an option disabled in the config and an option absent from
    the image are indistinguishable.  Both read as off, and a `*` now
    marks the ones the tool cannot tell apart -- worth saying, because a
    reader debugging a surprising chain is exactly who needs to know.
  - **`nr_cpus()` returning -1 wiped out the whole run.**  It is the
    documented sentinel for "unreadable", and `range(-1)` is empty, so a
    single failed symbol read skipped every chain *and* then indexed
    `cpus[0]`.  It now falls back to one CPU and says so.
  - **A decoded link was only checked for being *some* slab object.**
    `slab_object()` also returns the owning cache, and that half was
    thrown away.  A stale link that lands in a different cache's slab
    passes the first check and is still wrong, so the walk now compares
    the cache and stops.
- `examples/api/freelist_walk.py` was also missing the stop condition
  its own docstring promised: a chain longer than the slab has objects,
  which is how a corrupted freelist that still points at readable slab
  memory shows up.  It stopped on "not a slab object" and on cycles, and
  neither catches that case.
- `tests/unit/test_examples.py` gains `FreelistWalkRegressions` (4 tests,
  each shown to fail when its fix is reverted).  They are AST assertions
  rather than output assertions because the file needs a live GDB and the
  test environment's stubbed `gdb` has no memory to read.
- Loading KernLens no longer silently hands a command to another plugin.
  GDB does not protect command names: re-defining one replaces the
  previous definition without an error (even a built-in), so whichever
  plugin loads last wins.  `register_all()` previously swallowed the
  "already exists" error and recorded the name as registered anyway,
  which meant `kl-help` could list a command that actually ran someone
  else's implementation.  Registration now asks GDB for the exact list of
  pre-existing user commands (`help user-defined`) and reports any name
  it does not own:
  ```
  kernlens: alias 'kl-bits' is already defined by another plugin; the
  built-in definition is shadowed. Load KernLens last, or rename the
  conflicting definition.
  ```
  - A name that is genuinely taken is left alone and is **not** added to
    `command_names`, so `kl-help` never advertises a definition KernLens
    does not control.  `framework.conflicts()` returns the shadowed names.
  - Re-sourcing `gdbinit.py` stays silent: the owner of each name is
    recorded in a session map on the `gdb` module itself (a reload builds
    a fresh `framework` module, so the map cannot live there), and only a
    name owned by something else is reported.
  - `gdb.execute("help <name>")` was rejected as the probe: GDB's `help`
    matches abbreviations *and* prefixes, so `kernlens-pt` also resolves
    `kernlens-pte` and a bare `pt` resolves the built-in `ptype`.  The
    first cut reported seven of KernLens' own commands as squatters.
  - Consequence worth noting: sharing a session with pwndbg stays
    warning-free, because pwndbg registers bare names (`pagewalk`,
    `kbase`, `slab`, …) while KernLens registers only `kernlens-*` and
    `kl-*`; the two namespaces do not intersect.
- The layout-probe CI step failed on every matrix job.  It installed
  `bpftool` and read `/sys/kernel/btf/vmlinux` with it, but the Ubuntu
  `bpftool` package installs a *wrapper* that dispatches to a per-kernel
  tools package (`linux-tools-<release>`) which does not exist on a
  GitHub runner, so the probe aborted with
  `bpftool failed on /sys/kernel/btf/vmlinux`.  The tool now reads the
  blob with the project's own BTF parser, so the step needs neither
  `bpftool` nor `libbpf`; the CI condition is just "is there BTF here".
- `kernlens.gdb.btf` could not resolve a field that BTF inlines
  anonymously, so a BTF-only probe disagreed with the DWARF/bpftool view
  for `struct page.lru`/`compound_head`/`_mapcount`, `struct slab`'s
  `freelist`/`counters` and `bpf_prog.insns` -- 6 fields across the
  registry.  `BTF.offset` now descends into unnamed struct/union members
  (named members still win, and a self-referential anonymous member is
  guarded), which also makes the runtime BTF tier resolve those fields.
- Real-kernel fixes found by exercising every command's options against a
  live QEMU/KGDB session (Linux 6.1.134, KASLR on, DWARF5 debug info).
  The session is confirmed booted over SSH (`ctf@127.0.0.1:2222`) before
  any GDB is attached, so the debuggee is a genuinely running kernel:
  - `kl-percpu` resolved per-CPU symbols to a bogus address on a real
    kernel.  Per-CPU symbols are **zero-based**: `__per_cpu_start` is the
    first thing in the per-CPU section, so its address is a genuine `0`
    and each symbol's bare value (``0x1fb80`` for `current_task`) *is* its
    offset inside the section.  The command read those symbols through
    `kvar_addr()`, which adds the KASLR slide -- correct for an ordinary
    global, but here it turned the offset into an address far outside the
    section.  The command now reads the bare value for the symbol and for
    the section bounds, so `kl-percpu current_task` reports the real
    `__per_cpu_offset[cpu] + 0x1fb80`.
  - `cur_cpu()` (and therefore `kl-cpu`'s `current=`, the `[defer?]`
    lines, and `kl-percpu`'s default CPU) never resolved on a real
    kernel: it bailed out on the genuinely-zero `__per_cpu_start` and did
    not mask GDB's negative-valued `$gs_base`.  Both are fixed, and the
    new `CpuInfo.percpu_start()` makes the zero-based section base
    explicit.  Found while validating the CVE tracer against the live
    `exploit` binary, where every `cur_cpu=?` was in fact CPU 0.
  - `kl-status` always printed `KASLR slide: +0x0`.  The reader follows
    KASLR on its own for every read, but the command reported the
    `kaslr_offset` attribute, which stays zero until a command sets it.
    A new facade method (`kdbg.kaslr_slide()`) asks the reader for the
    slide actually in effect, so a status check right after boot agrees
    with the reads that follow.
  - A malformed `kl-slab` argument (`kl-slab bogus`) raised an uncaught
    `argparse.ArgumentTypeError` out of the command body; GDB turns an
    uncaught Python exception inside `invoke` into a fatal error that
    aborts the whole sourced script.  The framework now reports argument
    errors the way argparse would and returns.
  - `kl-slab info` now honours `-a/--active` (per-CPU active cache and
    freelist) and `-p/--partial` (the node's `nr_partial` and head slab)
    as separate views, followed by them being forced on by default, so
    `-p` no longer prints the CPU caches and `-a` no longer prints the
    node lists.  `-n/--node` filters the node view.
  - `kl-buddydump -f/--find` accepted only decimal (pwndbg's `type=int`)
    even though the value is an address; it now parses `0x...` and
    `&symbol` and matches a free page by physical address, virtual
    address, or `struct page` pointer.
  - The CVE tracer's `tcp_eat_recv_skb` breakpoint degraded to a bare
    symbol name.  `bp_spec()` asks GDB for `&symbol` to add the slide,
    but `tcp_eat_recv_skb` is a `static` function that the test kernel's
    DWARF exposes only as inlined locations -- there is no
    `&`-expressible symbol for it (`gdb.lookup_global_symbol` and
    `lookup_static_symbol` both return `None`), so `bp_spec()` correctly
    falls back to the bare name and GDB resolves it through DWARF at the
    link-time address.  The tracer now reports that case explicitly
    instead of printing a breakpoint that looks relocated but is not.
- Real-kernel fixes found by validating against a live QEMU/KGDB session
  (Linux 6.1.134, KASLR on, DWARF5 debug info):
  - The inspectors now resolve struct field offsets from the loaded
    `vmlinux` debug info instead of hardcoding them
    (`InspectorBase._offset_of` / `_sizeof`, cached and reset with the
    rest of the derived state).  The previous fixed offsets did not
    match a real build, so `kl-slabs`, `kl-slab --detail`, `kl-kdmesg`,
    `kl-buddydump`, and `kl-kbpf` returned nothing.
  - Offsets now come from a three-tier chain: DWARF first, then the
    image's embedded **BTF** (`CONFIG_DEBUG_INFO_BTF`), then the
    fallback registry.  `kernlens.gdb.btf` parses BTF directly -- no
    `bpftool` and no `libbpf` -- reading the `.BTF` section of the
    loaded image through GDB, or an ELF/raw blob via
    `reader.config.btf_path`.  It never borrows the host's BTF while
    debugging another kernel, which would silently describe the wrong
    build.  Only the final tier warns.
  - The fallback table moved to a single registry
    (`kernlens.gdb.layouts`), which records where each struct is
    defined and gates its entries on the kernel version and `CONFIG_*`
    predicates.  Its values are verified against Linux 7.0
    (`VERIFIED_KERNEL`); on the 6.1.134 validation target they are
    reached only through DWARF, so nothing changes there.
  - `kl-kbpf --maps` read `map_type`/`key_size`/`value_size`/
    `max_entries` at the pre-4.15 offsets (`0x10`–`0x1C`); with
    `CONFIG_SECURITY` the LSM `security` pointer shifts them to
    `0x18`–`0x24`, so maps were mis-decoded.  `kl-kdmabuf` read
    `struct dma_buf`'s `priv`/`list_node`/`exp_name` from stale offsets
    too; both are now resolved from the debug info.
  - Every command warns once, through `message.warn`, when any struct
    layout fell back to the built-in table, because those values are
    only verified for one build and may be silently wrong for another.
    Loading a matching `vmlinux` resolves every offset from DWARF and
    suppresses the warning.
- Source headers said GPL-2.0-or-later while `LICENSE`, `pyproject.toml`,
  and the user-facing files say GPL-3.0-or-later; all headers now agree.
- The `tests/conftest.py` docstring referenced a pytest `pythonpath`
  setting that did not exist.
- Corrected invalid test fixtures: the 1 GiB leaf sample is now 1 GiB
  aligned, the SLUB `counters` sample describes 3 of 8 objects in use,
  the five-level walk fixture has actual `pgd/p4d/pud/pmd` levels, and
  the invalid freeptr offset no longer uses a potentially valid 1 MiB
  value.
- GDB stack walking no longer dereferences ``None`` at the oldest
  frame; `kl-bt`/`kl-chain` now stop cleanly when ``Frame.older()``
  returns ``None``.
- GDB expression conversion failures (for example ``int($cr3)`` with
  no inferior loaded) now return ``None`` instead of raising, so
  `kl-walk` reports a page-table-root note rather than crashing.
- `KAddr.virt_to_phys` and `SlubInspector.head_to_page` now reject
  addresses outside the direct map instead of wrapping them into bogus
  physical/page addresses.
- `SlubInspector.freeptr_offset` validates pointer alignment and, when
  readable, the cache object size instead of rejecting every offset at
  or above 1 MiB.
- `IntFmt.size`/`Styler.size` carry rounded values into the next unit
  (for example `1 MiB - 1` is `1M`, not `1024K`).
- `kl-percpu` checks ``__per_cpu_end`` and validates the CPU index;
  `kl-cpu` rejects negative and out-of-range CPU numbers.
- Logger tests patched `kernlens.output.logger.time` by string, which fails on
  Python 3.10 because the package re-exports the `Logger` class and
  shadows the submodule attribute.  Tests now patch the imported module
  object directly.
- `BitOps.coerce` raised `NameError` because `IntType` was only
  referenced in a string annotation.
- `IntFmt.bytes_cstring` added a spurious ellipsis when the NUL
  terminator appeared after the default 64-byte display limit.
- `IntFmt.bytes_dump` included bytes beyond the requested `limit`.
- `Styler.box` produced rows one character narrower than its borders
  and omitted interior column separators.
- `Styler.block` added two columns of unintended right padding.
- `KAddr.page_align_up` returned the next page even for an
  already-aligned address.
- `SlubInspector.freeptr_offset` treated the valid offset `0` as
  missing, breaking ordinary SLUB freelist decoding.
- `KernelDebugger` could not be instantiated because its `indent`
  property collided with the bound `Styler.indent` method.  The config
  prefix is now exposed as `indent_str`.
- `KPageTable.split_4` and `BitOps.extract_bits` documentation examples
  showed incorrect values.
- `IntFmt.bytes_*_array` now accepts either `ByteOrder` or a
  `ByteOrderCodec` (e.g. `byteorder=LE`), matching the documented API.

## Version history note

Earlier revisions of this file carried `0.1.0` and `0.2.0` headings.
Neither was ever tagged or published, and neither was ever the version in
`pyproject.toml`, which has read `0.2.0` since the file was created.  The
`0.1.0` heading was dated 2026-10-25 -- a day whose only commit was the
licence bootstrap -- while listing modules that first appeared on the
26th.  They were development milestones written after the fact, not
release records.

Their entries are folded into the release above, in their original
wording.  `0.3.0` is the first tagged release, and every entry in it
describes code that exists at the tag.
