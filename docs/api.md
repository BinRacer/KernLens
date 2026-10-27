# Python API reference

Reference for the names `kernlens` exports.  This was part of the README
until the front page was rewritten to lead with what the commands do;
the text is unchanged, because it was accurate.

For the command line instead, see [`tutorial/`](tutorial/) -- one
generated page per command, with real output from a running kernel.

Every name below is importable from the package root:

```python
from kernlens import BITS, LE, BE, IntFmt, KAddr, KPageTable, Logger, Styler
```

`core/` and `output/` run without gdb.  The `gdb/` section at the end is
the adapter that wires the same logger and styler to live memory.

## Constants

`from kernlens import ...`

| Name | Value | Meaning |
|------|-------|---------|
| `PAGE_SHIFT` | 12 | page-frame shift |
| `PAGE_SIZE` | 4096 | page size in bytes |
| `PAGE_MASK` | 0xFFF | page-offset mask |
| `PTR_BITS` | 64 | pointer width |
| `PTR_HEX_DIGITS` | 16 | hex digits in a full pointer |
| `KERNEL_BASE` | 0xFFFFFFFF81000000 | link-time `_text` |
| `KERNEL_OFFSET` | 0 | default KASLR slide |
| `PAGE_OFFSET_BASE` | 0xFFFF888000000000 | direct-map start |
| `VMEMAP_BASE` | 0xFFFFEA0000000000 | `struct page` array start |
| `USER_TOP` | 0x00007FFFFFFFFFFF | top of user half |
| `KERNEL_BOTTOM` | 0xFFFF800000000000 | bottom of kernel half |
| `VMALLOC_START` | 0xFFFFC90000000000 | vmalloc start |
| `VMALLOC_END` | 0xFFFFE8FFFFFFFFFF | vmalloc end |
| `MODULE_START` | 0xFFFFFFFFC0000000 | module region start |
| `MODULE_END` | 0xFFFFFFFFFEFFFFFF | module region end |
| `MAX_ERRNO` | 4095 | `ERR_PTR` range endpoint |

## BitOps / BITS

All-static namespace; `BITS = BitOps()` is a short alias.  Every
method tolerates arbitrary Python ints and masks its input to width.

| Family | Methods |
|--------|---------|
| byte swap | `byte_swap(v, bits)`, `byte_swap16`, `byte_swap32`, `byte_swap64` |
| width reinterpret | `sign_extend(v, bits)`, `truncate(v, bits)`, `to_u8/16/32/64`, `to_i8/16/32/64`, `coerce(v, int_type)` |
| width metadata | `mask(bits)`, `sign_bit(bits)`, `unsigned_range(bits)`, `signed_range(bits)` |
| population / scan | `popcount`, `leading_zeros(v, bits=64)`, `trailing_zeros`, `first_set`, `last_set` |
| power-of-two | `is_power_of_2`, `next_power_of_2`, `log2_floor`, `log2_ceil` |
| rotate | `rotate_left(v, shift, bits=64)`, `rotate_right(v, shift, bits=64)` |
| align | `align_up`, `align_down`, `is_aligned` |
| single bit | `bit_test`, `bit_set`, `bit_clear`, `bit_toggle` |
| bit field | `extract_bits(v, shift, width)`, `insert_bits(v, field, shift, width)`, `clear_bits` |
| cpumask | `cpumask_test`, `cpumask_count`, `cpumask_first`, `cpumask_next` |

```python
BitOps.byte_swap32(0xdeadbeef)          # 0xefbeadde
BitOps.sign_extend(0x8000, 16)          # -32768
BitOps.popcount(0xff)                   # 8
BitOps.align_up(0x1234, 0x1000)         # 0x2000
BitOps.extract_bits(0x12345678, 8, 8)   # 0x56
BitOps.cpumask_next(0b1010, 1)          # 3
```

## IntCodec / ByteOrderCodec / LE / BE

`IntCodec` is all-static; every multi-byte method takes
`byteorder: ByteOrder = ByteOrder.LE` as its trailing keyword.
`ByteOrderCodec` binds one byte order to the statics so the call site
reads `LE.pack_u16(...)`.

```python
from kernlens import IntCodec, ByteOrder, IntType, LE, BE

IntCodec.pack_u16(0x1234)                          # b'\x34\x12'
IntCodec.pack_u16(0x1234, ByteOrder.BE)            # b'\x12\x34'
IntCodec.unpack_u16(b'\x12\x34', 0, ByteOrder.BE)  # 0x1234
IntCodec.pack_array([1, 2, 3], IntType.U32)        # 12 bytes LE
IntCodec.unpack_array(b'\x01\x00\x02\x00', IntType.U16, 2)  # [1, 2]
IntCodec.is_in_range(-1, IntType.I16)              # True

LE.pack_u16(0x1234)          # b'\x34\x12'
BE.pack_u16(0x1234)          # b'\x12\x34'
BE.unpack_u16(b'\x12\x34')   # 0x1234
```

`ByteOrder.LE.prefix` → `"<"`; `ByteOrder.BE.prefix` → `">"`.
`IntType.<T>` exposes `.code .width .bits .signed .mask .min_value .max_value`.
Every `byteorder` parameter accepts either a `ByteOrder` member or a
bound `ByteOrderCodec`, so `IntCodec.pack_u16(0x1234, BE)` and
`IntFmt.bytes_u16_array(data, byteorder=LE)` are valid.

## IntFmt

All-static; returns plain `str`; never touches color or the logger.

| Family | Methods |
|--------|---------|
| integers | `addr`, `hex`, `hex8/16/32/64`, `off(base, delta)`, `field_off(delta)`, `size`, `pfn`, `page_off`, `mask`, `bits(v, bits=8)`, `flags(v, names)`, `percent(num, den)`, `signed`, `signed_hex`, `timestamp`, `duration_ns` |
| byte strings | `bytes_hex(data, limit=64)`, `bytes_ascii`, `bytes_cstring`, `bytes_dump(data, limit=64, base=0)`, `bytes_u16_array(data, count=None, byteorder=LE)`, `bytes_u32_array`, `bytes_u64_array` |

```python
IntFmt.addr(-1)                        # '0xffffffffffffffff'
IntFmt.size(1536)                      # '1.5K'
IntFmt.off(0xffff888000001000, 0x40)   # '0xffff888000001000+0x40'
IntFmt.flags(0x5, {0: "A", 2: "C"})    # '0x5(A|C)'
IntFmt.bytes_hex(b'\xde\xad')          # 'de ad'
IntFmt.bytes_u16_array(b'\x01\x00\x02\x00')  # '0x0001 0x0002'
```

## KAddr

All-static; masks its input to 64 bits first, so negative Python ints
behave like the unsigned kernel values.

| Family | Methods |
|--------|---------|
| classify | `is_user`, `is_kernel`, `is_canonical(addr, bits=48)`, `is_direct_map(addr, base, size)`, `is_vmemmap`, `is_vmalloc`, `is_module`, `is_text(addr, base=KERNEL_BASE)` |
| translate | `virt_to_phys`, `phys_to_virt`, `phys_to_pfn`, `pfn_to_phys`, `phys_to_page(phys, vmemmap, page_size=64)`, `virt_to_page(addr, ...)`, `page_align`, `page_align_up` |
| KASLR | `kaslr_runtime(link, offset)`, `kaslr_link(runtime, offset)` |
| ERR_PTR | `is_err(ptr)`, `ptr_err(ptr)`, `err_ptr(err)` |
| tags | `ptr_tag(addr, mask)`, `strip_tag(addr, mask)` |

```python
KAddr.is_kernel(0xffff888000000000)        # True
KAddr.virt_to_phys(0xffff888000001000)     # 0x1000
KAddr.phys_to_page(0x1000)                 # 0xffffea0000000040
KAddr.ptr_err(0xfffffffffffffff2)          # 14
KAddr.err_ptr(-14)                         # 0xfffffffffffffff2
```

## KPageTable

All-static; computes addresses and decodes PTE bits, never reads
memory.  4-level and 5-level paging supported; 5-level entry points
take `five_level=True`.

| Family | Methods |
|--------|---------|
| index | `pgd_index(va, five_level=False)`, `p4d_index`, `pud_index`, `pmd_index`, `pte_index`, `page_offset` |
| split | `split_4(va)` → `(pgd, pud, pmd, pte, off)`, `split_5(va)` → `(pgd, p4d, pud, pmd, pte, off)`, `split(va, five_level=False)`, `split_2m`, `split_1g` |
| huge page | `huge_2m_base`, `huge_1g_base`, `is_2m_aligned`, `is_1g_aligned` |
| canonicalize | `canonicalize(va, five_level=False)` |
| entry address | `entry_addr(table_base, index)`, `pgd/p4d/pud/pmd/pte_entry_addr`, `next_table(entry)` |
| PTE decode | `pte_present/writable/user/accessed/dirty/global/nx`, `pte_is_huge`, `pte_phys`, `pte_pfn`, `pte_flags`, `make_pte(phys, flags=0)` |
| leaf → PA | `pte_to_phys`, `pmd_to_phys`, `pud_to_phys` |

Class constants: `PTE_PRESENT RW USER PWT PCD ACCESSED DIRTY PAT GLOBAL PS NX`, `PTE_ADDR_MASK`, and the geometry constants (`BITS_PER_LEVEL`, `ENTRY_SIZE`, `PTE_SHIFT`, `HUGE_2M_SHIFT`, `HUGE_1G_SHIFT`, `PGD_SHIFT_4/5`, `PHYS_BITS`).

```python
KPageTable.split_4(0xffff888000001234)
# (0x111, 0x000, 0x000, 0x001, 0x234)

KPageTable.split_5(0xffff800000001234)
# (0x1ff, 0x100, 0x000, 0x000, 0x001, 0x234)

pte = 0x8000000000123067
KPageTable.pte_present(pte)   # True
KPageTable.pte_phys(pte)      # 0x123000
KPageTable.pte_pfn(pte)       # 0x123
KPageTable.pte_flags(pte)     # ['P', 'RW', 'US', 'A', 'D', 'NX']

KPageTable.pte_to_phys(pte, 0xffff888000001abc)   # 0x123abc
```

`KPageTable` only does arithmetic.  To translate a live address,
`kernlens.gdb.walker.PageTableWalker` (bound as `kdbg.walk`)
walks the real tables from `CR3` and reports every level; the
`kernlens-walk` command prints it.  A walk stops cleanly with a `note`
on an unreadable, absent, or non-present entry.

## Logger / LogLevel / Palette

`Palette` is a `str` enum; every value is the SGR sequence.

```python
Palette.RED           # '\x1b[31m'
f"{Palette.RED}"      # '\x1b[31m'
Palette.BRIGHT_RED_BOLD
```

`LogLevel` carries a fixed-width 9-char tag and a `Palette`:

```python
LogLevel.INFO.tag     # '[INFO]   '
LogLevel.INFO.color   # Palette.CYAN
```

`Logger`:

```python
log = Logger()                                # color, tags, stdout
log = Logger(color_enabled=False, show_time=True)
log = Logger(min_level=LogLevel.WARN, stream=io.StringIO())

log.debug("raw=0xdeadbeef")
log.info("hooked __slab_free")
log.success("stage 3 reached")
log.warn("freelist head is stale")
log.error("head_to_page failed")
```

| Method | Purpose |
|--------|---------|
| `set_color_enabled(bool)` / `enable_color()` / `disable_color()` | color toggle |
| `set_min_level(level)` / `is_enabled(level)` | level filter |
| `set_show_tag(bool)` / `set_show_time(bool)` | prefix control |
| `set_stream(stream)` | redirect; `None` restores stdout |
| `once(key, msg, level=INFO) -> bool` | emit once per key |
| `reset_once()` | forget all once keys |
| `throttle(key, interval, msg, level=INFO) -> bool` | emit at most every `interval` seconds |
| `reset_throttle()` | forget all throttle timestamps |
| `counter(key, delta=1) -> int` | accumulate |
| `counters()` / `reset_counters()` | snapshot / clear |
| `summary(*, level=INFO, sort_by="key")` | print all counters |
| `check(cond, ok_msg, *, fail_msg=None, fail_level=WARN) -> bool` | conditional emit |
| `assert_(cond, msg) -> bool` | record `ASSERT: msg` on failure, never raises |
| `fmt_line(level, msg) -> str` | build line without printing |
| `banner(title, *, char="=", width=80, color=CYAN)` | INFO-level banner |
| `rule(*, char="-", width=80, color=DIM)` | INFO-level rule |
| `reset()` | clear once / counters / throttle |

## Styler

Instance methods; construct with optional `color_enabled`,
`key_color`, `value_color`.  Every color argument accepts a
`Palette` member or a raw SGR string.

```python
sty = Styler()
sty = Styler(color_enabled=False)
sty = Styler(key_color=Palette.BRIGHT_YELLOW, value_color=Palette.GREEN)
sty.disable_color(); sty.enable_color()
sty.set_key_color(Palette.BRIGHT_CYAN); sty.set_value_color(Palette.DIM)
sty.set_kv_colors(Palette.CYAN, Palette.GREEN)
```

| Family | Methods |
|--------|---------|
| primitives | `style(text, color)`, `addr(value)` |
| numeric (colored) | `hex(v, *, digits=None, color=DIM)`, `hex8/16/32/64`, `dec(v, color="")`, `size`, `pfn`, `percent`, `bits(v, *, width=8, color=DIM)` |
| align / truncate | `ljust/rjust/center(text, width, *, fill=" ", color="")`, `pad(text, width, *, align="left", fill=" ", color="")`, `truncate(text, width, *, ellipsis="...", color="")` |
| k=v | `kv`, `kv_int`, `kv_hex`, `kv_bool(label, value, *, true_color=None, false_color=None)` |
| containers | `seq`, `list`, `tuple`, `set`, `dict`, `pairs`, `range`, `named(name, items, *, style="[]", ...)`, `kv_seq(label, items, *, style="[]", ...)` |
| layout | `table`, `box`, `chain`, `cols`, `block` |
| transforms | `highlight(text, pattern, *, color=BRIGHT_YELLOW_BOLD)`, `indent(text, *, level=1, width=2)` |
| groups | `fields(pairs, *, sep="  ", ...)`, `kv_group(pairs, *, assign=" = ", ...)` |
| symbols | `tick()`, `cross()`, `bullet()`, `arrow()` |
| progress | `bar(value, max_value, *, width=20, ...)` |

### Layout signatures

```python
sty.table(headers, rows, *, header_color=CYAN, item_color=None,
          bracket_color=DIM, col_sep="  ", rule="-", fill=" ",
          aligns=None, max_col_width=None)

sty.box(headers, rows, *, header_color=CYAN, item_color=None,
        border_color=DIM, chars="┌┐└┘─│", joints="┬┴┼├┤",
        fill=" ", aligns=None, max_col_width=None)

sty.cols(items, n, *, item_color=None, col_sep="  ", pad=2,
         fill=" ", aligns=None, max_col_width=None)

sty.block(title, lines, *, width=0, border_color=DIM,
          title_color=CYAN, chars="┌┐└┘─", vertical="│")
```

`aligns` accepts one token (`"l"` / `"r"` / `"c"` / `"left"` /
`"right"` / `"center"`) for all columns, or a list for per-column
alignment.  `fill` must be a single character.  `max_col_width`
truncates each cell with `"..."` before sizing the column.

```python
sty.kv("pid", "1234", value_color=Palette.GREEN)   # pid=1234
sty.kv_hex("page", 0xffffea0000a1c000)             # page=0x… (dim)
sty.kv_bool("ready", True)                         # ready=true

sty.list([1, 2, 3])                                # [1, 2, 3]
sty.dict({"pid": 1, "cpu": 0})                     # {pid: 1, cpu: 0}
sty.named("cpus", [0, 1, 2])                       # cpus[0, 1, 2]
sty.kv_seq("slab", {"page": "0xea00"}, style="{}") # slab={page: 0xea00}

print(sty.table(
    ["name", "inuse", "frozen"],
    [["kmalloc-1k", 3, 0], ["kmalloc-64", 7, 1]],
    aligns=["l", "r", "c"],
    max_col_width=20,
))
print(sty.cols(range(6), 3))
print(sty.block("slab", ["page=0xea00", "inuse=3"]))
print(sty.bar(4, 8, width=8))           # [████░░░░] 4/8
```

## gdb/ (gdb side)

Not imported at package level.  Load inside gdb with a normal import
(see [Install](#install)).  The package exposes
`DebugConfig`, `KernelStyler`, `MemoryReader`, `SymbolResolver`,
`Kaslr`, `Kbase`, `IdtEntry`, `IdtInfo`, `KbaseResult`, `CpuInfo`,
`PageTableWalker`, `PageWalk`, `WalkLevel`, `SlubInspector`,
`KernelDebugger`, and the singleton `kdbg`.  Every method listed on
`kdbg` below is also available as a component accessor (`kdbg.logger.*`,
`kdbg.styler.*`, `kdbg.reader.*`, ...).

| Group | Facade methods |
|-------|----------------|
| logging | `debug info success warn error once throttle counter summary check assert_ banner rule` |
| styler | `style addr hex hex8 hex16 hex32 hex64 dec size pfn percent bits ljust rjust center pad truncate kv kv_int kv_hex kv_bool seq list tuple set dict pairs range named kv_seq table box cols block highlight indent fields kv_group tick cross bullet arrow bar` |
| kernel styler | `fn loc depth_marker branch fl_tag kv_cpu kv_online kv_err kv_trans` |
| reader | `u64 read_kvar kvar_addr arg read_field` |
| symbols | `sym line backtrace chain color_chain` |
| kaslr | `bp_spec link_text find_kbase` |
| cpu | `nr_cpus nr_nodes cpu_online cur_cpu percpu_off` |
| page tables | `walk` |
| slub | `page_bytes head_to_page compound_head cache_name cpu_slab_ptr cpu_active_slab cpu_freelist freeptr_offset freeptr_random decode_freeptr freelist_dist partial_info in_partial print_slab` |

```python
kdbg.kaslr_offset = 0x1e000000
text = kdbg.link_text()
if text is not None:
    kdbg.info("_text runtime = " + kdbg.addr(
        text + kdbg.kaslr_offset
    ))
kdbg.print_slab(head)
kdbg.disable_color()           # both logger and styler
```

`KernelDebugger.indent` is bound to the `Styler.indent` text formatter;
the configuration prefix is available separately as `indent_str`.

## Conventions

- Table-like layout methods (`table`, `box`, `cols`) share `fill` /
  `aligns` / `max_col_width`; `box` and `block` also accept custom
  border characters (`joints`, `vertical`).
- `Styler` output is plain text when `color_enabled=False`; the
  structure is unchanged.
- `IntCodec` and the `IntFmt.bytes_*_array` helpers accept either a
  `ByteOrder` or a `ByteOrderCodec` for their `byteorder` argument.
- `KAddr` / `KPageTable` mask their input to 64 bits; negative Python
  ints behave like unsigned values.
- `Logger.once` / `throttle` / `counter` state lives on the instance;
  `reset()` clears all three at once.
- GDB commands stay short (`kernlens-walk`, `kl-walk`); Python names
  follow [`naming.md`](naming.md) — readable, but no longer
  than necessary, with one spelling per concept.
