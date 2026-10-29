# Python API 参考

本文件收录 `kernlens` 导出的名字。这部分内容原在 README 中；首页改为
先讲命令能做什么之后，它移到了这里，正文未改（原本是准确的）。

命令行参考见 [`tutorial/`](../tutorial/README.md) —— 每个命令一页，附真实运行输出。

以下名字均可从包根导入：

```python
from kernlens import BITS, LE, BE, IntFmt, KAddr, KPageTable, Logger, Styler
```

`core/` 与 `output/` 不需要 gdb。文末的 `gdb/` 一节是适配层，把同一个
logger 与 styler 接到活内存上。

## 常量

`from kernlens import ...`

| 名称               | 值                 | 含义                   |
| ------------------ | ------------------ | ---------------------- |
| `PAGE_SHIFT`       | 12                 | 页帧位移               |
| `PAGE_SIZE`        | 4096               | 页大小                 |
| `PAGE_MASK`        | 0xFFF              | 页内偏移掩码           |
| `PTR_BITS`         | 64                 | 指针宽度               |
| `PTR_HEX_DIGITS`   | 16                 | 完整指针的十六进制位数 |
| `KERNEL_BASE`      | 0xFFFFFFFF81000000 | 链接时 `_text`         |
| `KERNEL_OFFSET`    | 0                  | 默认 KASLR slide       |
| `PAGE_OFFSET_BASE` | 0xFFFF888000000000 | direct map 起始        |
| `VMEMAP_BASE`      | 0xFFFFEA0000000000 | `struct page` 数组起始 |
| `USER_TOP`         | 0x00007FFFFFFFFFFF | 用户半区顶             |
| `KERNEL_BOTTOM`    | 0xFFFF800000000000 | 内核半区底             |
| `VMALLOC_START`    | 0xFFFFC90000000000 | vmalloc 起始           |
| `VMALLOC_END`      | 0xFFFFE8FFFFFFFFFF | vmalloc 结束           |
| `MODULE_START`     | 0xFFFFFFFFC0000000 | 模块区起始             |
| `MODULE_END`       | 0xFFFFFFFFFEFFFFFF | 模块区结束             |
| `MAX_ERRNO`        | 4095               | `ERR_PTR` 端点         |

## BitOps / BITS

全静态命名空间；`BITS = BitOps()` 是短别名。所有方法对任意 Python
int 都可工作，先把输入 mask 到目标宽度。

| 分组        | 方法                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| 字节交换    | `byte_swap(v, bits)`, `byte_swap16`, `byte_swap32`, `byte_swap64`                                      |
| 宽度重解释  | `sign_extend(v, bits)`, `truncate(v, bits)`, `to_u8/16/32/64`, `to_i8/16/32/64`, `coerce(v, int_type)` |
| 宽度元数据  | `mask(bits)`, `sign_bit(bits)`, `unsigned_range(bits)`, `signed_range(bits)`                           |
| 人口 / 扫描 | `popcount`, `leading_zeros(v, bits=64)`, `trailing_zeros`, `first_set`, `last_set`                     |
| 2 的幂      | `is_power_of_2`, `next_power_of_2`, `log2_floor`, `log2_ceil`                                          |
| 旋转        | `rotate_left(v, shift, bits=64)`, `rotate_right(v, shift, bits=64)`                                    |
| 对齐        | `align_up`, `align_down`, `is_aligned`                                                                 |
| 单 bit      | `bit_test`, `bit_set`, `bit_clear`, `bit_toggle`                                                       |
| 位段        | `extract_bits(v, shift, width)`, `insert_bits(v, field, shift, width)`, `clear_bits`                   |
| cpumask     | `cpumask_test`, `cpumask_count`, `cpumask_first`, `cpumask_next`                                       |

```python
BitOps.byte_swap32(0xdeadbeef)          # 0xefbeadde
BitOps.sign_extend(0x8000, 16)          # -32768
BitOps.popcount(0xff)                   # 8
BitOps.align_up(0x1234, 0x1000)         # 0x2000
BitOps.extract_bits(0x12345678, 8, 8)   # 0x56
BitOps.cpumask_next(0b1010, 1)          # 3
```

## IntCodec / ByteOrderCodec / LE / BE

`IntCodec` 全静态；所有多字节方法的末位关键字参数是
`byteorder: ByteOrder = ByteOrder.LE`。`ByteOrderCodec` 绑定一个
字节序到静态方法，调用点写 `LE.pack_u16(...)` 即可。所有
`byteorder` 参数都同时接受 `ByteOrder` 与 `ByteOrderCodec`，因此
`IntCodec.pack_u16(0x1234, BE)`、`IntFmt.bytes_u16_array(data,
byteorder=LE)` 都有效。

```python
from kernlens import IntCodec, ByteOrder, IntType, LE, BE

IntCodec.pack_u16(0x1234)                          # b'\x34\x12'
IntCodec.pack_u16(0x1234, ByteOrder.BE)            # b'\x12\x34'
IntCodec.unpack_u16(b'\x12\x34', 0, ByteOrder.BE)  # 0x1234
IntCodec.pack_array([1, 2, 3], IntType.U32)        # 12 字节 LE
IntCodec.unpack_array(b'\x01\x00\x02\x00', IntType.U16, 2)  # [1, 2]
IntCodec.is_in_range(-1, IntType.I16)              # True

LE.pack_u16(0x1234)          # b'\x34\x12'
BE.pack_u16(0x1234)          # b'\x12\x34'
BE.unpack_u16(b'\x12\x34')   # 0x1234
```

`ByteOrder.LE.prefix` → `"<"`；`ByteOrder.BE.prefix` → `">"`。
`IntType.<T>` 暴露 `.code .width .bits .signed .mask .min_value .max_value`。

## IntFmt

全静态；返回纯 `str`；不碰颜色、不碰 logger。

| 分组   | 方法                                                                                                                                                                                                                     |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 整数   | `addr`, `hex`, `hex8/16/32/64`, `off(base, delta)`, `field_off(delta)`, `size`, `pfn`, `page_off`, `mask`, `bits(v, bits=8)`, `flags(v, names)`, `percent(num, den)`, `signed`, `signed_hex`, `timestamp`, `duration_ns` |
| 字节串 | `bytes_hex(data, limit=64)`, `bytes_ascii`, `bytes_cstring`, `bytes_dump(data, limit=64, base=0)`, `bytes_u16_array(data, count=None, byteorder=LE)`, `bytes_u32_array`, `bytes_u64_array`                               |

```python
IntFmt.addr(-1)                        # '0xffffffffffffffff'
IntFmt.size(1536)                      # '1.5K'
IntFmt.off(0xffff888000001000, 0x40)   # '0xffff888000001000+0x40'
IntFmt.flags(0x5, {0: "A", 2: "C"})    # '0x5(A|C)'
IntFmt.bytes_hex(b'\xde\xad')          # 'de ad'
IntFmt.bytes_u16_array(b'\x01\x00\x02\x00')  # '0x0001 0x0002'
```

## KAddr

全静态；输入先 mask 到 64 位，负 Python int 等同无符号内核值。

| 分组    | 方法                                                                                                                                                                 |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 分类    | `is_user`, `is_kernel`, `is_canonical(addr, bits=48)`, `is_direct_map(addr, base, size)`, `is_vmemmap`, `is_vmalloc`, `is_module`, `is_text(addr, base=KERNEL_BASE)` |
| 转换    | `virt_to_phys`, `phys_to_virt`, `phys_to_pfn`, `pfn_to_phys`, `phys_to_page(phys, vmemmap, page_size=64)`, `virt_to_page(addr, ...)`, `page_align`, `page_align_up`  |
| KASLR   | `kaslr_runtime(link, offset)`, `kaslr_link(runtime, offset)`                                                                                                         |
| ERR_PTR | `is_err(ptr)`, `ptr_err(ptr)`, `err_ptr(err)`                                                                                                                        |
| tag     | `ptr_tag(addr, mask)`, `strip_tag(addr, mask)`                                                                                                                       |

```python
KAddr.is_kernel(0xffff888000000000)        # True
KAddr.virt_to_phys(0xffff888000001000)     # 0x1000
KAddr.phys_to_page(0x1000)                 # 0xffffea0000000040
KAddr.ptr_err(0xfffffffffffffff2)          # 14
KAddr.err_ptr(-14)                         # 0xfffffffffffffff2
```

## KPageTable

全静态；只算地址、解 PTE 位、不读内存。4 级与 5 级页表都支持；
5 级专属入口用 `five_level=True`。

| 分组      | 方法                                                                                                                                                 |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 索引      | `pgd_index(va, five_level=False)`, `p4d_index`, `pud_index`, `pmd_index`, `pte_index`, `page_offset`                                                 |
| 拆分      | `split_4(va)` → `(pgd, pud, pmd, pte, off)`, `split_5(va)` → `(pgd, p4d, pud, pmd, pte, off)`, `split(va, five_level=False)`, `split_2m`, `split_1g` |
| 大页      | `huge_2m_base`, `huge_1g_base`, `is_2m_aligned`, `is_1g_aligned`                                                                                     |
| 规范化    | `canonicalize(va, five_level=False)`                                                                                                                 |
| 表项地址  | `entry_addr(table_base, index)`, `pgd/p4d/pud/pmd/pte_entry_addr`, `next_table(entry)`                                                               |
| PTE 解码  | `pte_present/writable/user/accessed/dirty/global/nx`, `pte_is_huge`, `pte_phys`, `pte_pfn`, `pte_flags`, `make_pte(phys, flags=0)`                   |
| leaf → PA | `pte_to_phys`, `pmd_to_phys`, `pud_to_phys`                                                                                                          |

类常量：`PTE_PRESENT RW USER PWT PCD ACCESSED DIRTY PAT GLOBAL PS NX`、`PTE_ADDR_MASK`，以及几何常量（`BITS_PER_LEVEL`、`ENTRY_SIZE`、`PTE_SHIFT`、`HUGE_2M_SHIFT`、`HUGE_1G_SHIFT`、`PGD_SHIFT_4/5`、`PHYS_BITS`）。

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

`KPageTable` 只做算术；要翻译活地址，使用
`kernlens.gdb.walker.PageTableWalker`（facade 上为
`kdbg.walk`）：它从 `CR3` 出发实际遍历页表并返回每一级，
`kernlens-walk` 命令负责打印。遇到不可读、缺失或 not-present 的表项时，
遍历会带 `note` 正常结束，不抛异常。

## Logger / LogLevel / Palette

`Palette` 是 `str` 枚举，每个值就是 SGR 序列。

```python
Palette.RED           # '\x1b[31m'
f"{Palette.RED}"      # '\x1b[31m'
Palette.BRIGHT_RED_BOLD
```

`LogLevel` 携带 9 字符定宽 tag 与 `Palette`：

```python
LogLevel.INFO.tag     # '[INFO]   '
LogLevel.INFO.color   # Palette.CYAN
```

`Logger`：

```python
log = Logger()                                # 彩色、带 tag、stdout
log = Logger(color_enabled=False, show_time=True)
log = Logger(min_level=LogLevel.WARN, stream=io.StringIO())

log.debug("raw=0xdeadbeef")
log.info("hooked __slab_free")
log.success("stage 3 reached")
log.warn("freelist head is stale")
log.error("head_to_page failed")
```

| 方法                                                             | 用途                               |
| ---------------------------------------------------------------- | ---------------------------------- |
| `set_color_enabled(bool)` / `enable_color()` / `disable_color()` | 颜色开关                           |
| `set_min_level(level)` / `is_enabled(level)`                     | 级别过滤                           |
| `set_show_tag(bool)` / `set_show_time(bool)`                     | 前缀开关                           |
| `set_stream(stream)`                                             | 重定向；`None` 回 stdout           |
| `once(key, msg, level=INFO) -> bool`                             | 每 key 只输出一次                  |
| `reset_once()`                                                   | 清空 once                          |
| `throttle(key, interval, msg, level=INFO) -> bool`               | 每 interval 秒最多一次             |
| `reset_throttle()`                                               | 清空 throttle                      |
| `counter(key, delta=1) -> int`                                   | 累加                               |
| `counters()` / `reset_counters()`                                | 快照 / 清零                        |
| `summary(*, level=INFO, sort_by="key")`                          | 打印全部计数                       |
| `check(cond, ok_msg, *, fail_msg=None, fail_level=WARN) -> bool` | 条件输出                           |
| `assert_(cond, msg) -> bool`                                     | 失败时输出 `ASSERT: msg`，不抛异常 |
| `fmt_line(level, msg) -> str`                                    | 只返回格式化后的行                 |
| `banner(title, *, char="=", width=80, color=CYAN)`               | INFO 横幅                          |
| `rule(*, char="-", width=80, color=DIM)`                         | INFO 分隔线                        |
| `reset()`                                                        | 清空 once / counters / throttle    |

## Styler

实例方法；构造时可选 `color_enabled` / `key_color` / `value_color`。
所有颜色参数接受 `Palette` 成员或原始 SGR 字符串。

```python
sty = Styler()
sty = Styler(color_enabled=False)
sty = Styler(key_color=Palette.BRIGHT_YELLOW, value_color=Palette.GREEN)
sty.disable_color(); sty.enable_color()
sty.set_key_color(Palette.BRIGHT_CYAN); sty.set_value_color(Palette.DIM)
sty.set_kv_colors(Palette.CYAN, Palette.GREEN)
```

| 分组         | 方法                                                                                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 原语         | `style(text, color)`, `addr(value)`                                                                                                                                     |
| 数值（带色） | `hex(v, *, digits=None, color=DIM)`, `hex8/16/32/64`, `dec(v, color="")`, `size`, `pfn`, `percent`, `bits(v, *, width=8, color=DIM)`                                    |
| 对齐 / 截断  | `ljust/rjust/center(text, width, *, fill=" ", color="")`, `pad(text, width, *, align="left", fill=" ", color="")`, `truncate(text, width, *, ellipsis="...", color="")` |
| k=v          | `kv`, `kv_int`, `kv_hex`, `kv_bool(label, value, *, true_color=None, false_color=None)`                                                                                 |
| 容器         | `seq`, `list`, `tuple`, `set`, `dict`, `pairs`, `range`, `named(name, items, *, style="[]", ...)`, `kv_seq(label, items, *, style="[]", ...)`                           |
| 布局         | `table`, `box`, `chain`, `cols`, `block`                                                                                                                                |
| 文本变换     | `highlight(text, pattern, *, color=BRIGHT_YELLOW_BOLD)`, `indent(text, *, level=1, width=2)`                                                                            |
| 组           | `fields(pairs, *, sep="  ", ...)`, `kv_group(pairs, *, assign=" = ", ...)`                                                                                              |
| 符号         | `tick()`, `cross()`, `bullet()`, `arrow()`                                                                                                                              |
| 进度         | `bar(value, max_value, *, width=20, ...)`                                                                                                                               |

## 布局签名

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

`aligns` 接受单一 token（`"l"` / `"r"` / `"c"` / `"left"` /
`"right"` / `"center"`）应用于所有列，也接受列表逐列指定。
`fill` 必须是单字符。`max_col_width` 在计算列宽前用 `"..."`
截断每个单元。

```python
sty.kv("pid", "1234", value_color=Palette.GREEN)   # pid=1234
sty.kv_hex("page", 0xffffea0000a1c000)             # page=0x…（dim）
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

## gdb/（gdb 侧）

不在包级导入。gdb 内用正常 import（见[安装](index.md#安装)）
加载；模块导出 `DebugConfig`、`KernelStyler`、`MemoryReader`、
`SymbolResolver`、`Kaslr`、`Kbase`、`IdtEntry`、`IdtInfo`、
`KbaseResult`、`CpuInfo`、`PageTableWalker`、`PageWalk`、
`WalkLevel`、`SlubInspector`、`KernelDebugger`
与单例 `kdbg`。下表每个方法同时也是组件访问器
（`kdbg.logger.*`、`kdbg.styler.*`、`kdbg.reader.*` …）。

| 分组          | facade 方法                                                                                                                                                                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 日志          | `debug info success warn error once throttle counter summary check assert_ banner rule`                                                                                                                                                                       |
| styler        | `style addr hex hex8 hex16 hex32 hex64 dec size pfn percent bits ljust rjust center pad truncate kv kv_int kv_hex kv_bool seq list tuple set dict pairs range named kv_seq table box cols block highlight indent fields kv_group tick cross bullet arrow bar` |
| kernel styler | `fn loc depth_marker branch fl_tag kv_cpu kv_online kv_err kv_trans`                                                                                                                                                                                          |
| reader        | `u64 read_kvar kvar_addr arg read_field`                                                                                                                                                                                                                      |
| symbols       | `sym line backtrace chain color_chain`                                                                                                                                                                                                                        |
| kaslr         | `bp_spec link_text find_kbase`                                                                                                                                                                                                                                |
| cpu           | `nr_cpus nr_nodes cpu_online cur_cpu percpu_off`                                                                                                                                                                                                              |
| 页表          | `walk`                                                                                                                                                                                                                                                        |
| slub          | `page_bytes head_to_page compound_head cache_name cpu_slab_ptr cpu_active_slab cpu_freelist freeptr_offset freeptr_random decode_freeptr freelist_dist partial_info in_partial print_slab`                                                                    |

```python
kdbg.kaslr_offset = 0x1e000000
text = kdbg.link_text()
if text is not None:
    kdbg.info("_text runtime = " + kdbg.addr(
        text + kdbg.kaslr_offset
    ))
kdbg.print_slab(head)
kdbg.disable_color()           # 同时关闭 logger 与 styler
```

`KernelDebugger.indent` 绑定到 `Styler.indent` 文本格式化方法；配置
里的缩进前缀通过独立的 `indent_str` 属性访问，避免同名冲突。

## 约定

- 表格式布局方法（`table` / `box` / `cols`）共用 `fill` / `aligns` /
  `max_col_width`；`box` / `block` 还接受自定义边框
  （`joints` / `vertical`）。
- `Styler` 在 `color_enabled=False` 时返回纯文本，结构不变。
- `IntCodec` 与 `IntFmt.bytes_*_array` 的 `byteorder` 参数同时接受
  `ByteOrder` 与 `ByteOrderCodec`。
- `KAddr` / `KPageTable` 把输入 mask 到 64 位；负 Python int 等同无符号值。
- `Logger.once` / `throttle` / `counter` 状态保存在实例里；`reset()` 一次清空三者。
- GDB 命令保持简短（`kernlens-walk` / `kl-walk`）；Python 命名遵循
  [`naming.md`](../naming.md)：可读、不过长，一个概念只用一种拼写。
