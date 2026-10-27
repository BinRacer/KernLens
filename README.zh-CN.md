<div align="center">
  <a href="https://github.com/BinRacer/KernLens">
    <img src="images/banner.svg" alt="KernLens" style="width:100%; max-width:100%; margin-top:0; margin-bottom:-0.5rem">
  </a>

  <p>
    <a href="./README.md">English</a> | <a href="./README.zh-CN.md">简体中文</a>
  </p>

  <p>
    面向 GDB 的 Linux 内核检查工具 — 从原始内存、页表到 SLUB 内部结构与符号解析。
  </p>

  <p>
    <a href="https://github.com/BinRacer/KernLens"><img src="https://img.shields.io/badge/GitHub-KernLens-181717.svg" alt="GitHub: KernLens"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="许可证：GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-informational" alt="Python 3.10-3.13">
    <img src="https://img.shields.io/badge/GDB-introspection-informational" alt="GDB introspection">
  </p>
</div>

## 概览

KernLens 是一套纯 Python 内核调试工具集，覆盖字节序编解码、位运算、
x86_64 地址分类、页表计算、整数格式化、结构化日志。
`src/kernlens/core/` 与 `src/kernlens/output/` 不依赖 gdb；
`src/kernlens/gdb/` 下的组件负责把同一套 logger / styler 接到活内存
读取、符号解析和 SLUB 检查上。

## 目录

```
kernlens/                          # 仓库根
├── src/kernlens/
│   ├── __init__.py               # 包顶层 re-export
│   ├── core/                     # 纯 Python：constants、bitops、codec、fmt、addr、paging
│   ├── output/                   # palette、levels、logger、styler
│   ├── gdb/                      # 每个适配组件一个模块
│   │   ├── config.py ... facade.py
│   │   ├── api.py                # 供 source 脚本使用的公共 API
│   │   └── __init__.py           # 组件懒加载导出
│   └── py.typed                  # PEP 561 标记
├── tests/
│   ├── unit/                     # 纯 Python 测试
│   └── integration/              # 基于 fake 的适配层 + gdbinit 测试
├── examples/                     # slab_snapshot, gdb_tracer, trace, cve_2025_38616_trace
├── gdbinit.py                    # 可选的 ~/.gdbinit 入口
├── docs/
│   ├── architecture.md           # 结构、API 地图与设计说明
│   └── naming.md                 # 命令与 Python 命名规范
├── images/banner.svg
├── pyproject.toml
├── uv.lock
├── MANIFEST.in
└── CHANGELOG.md
```

依赖方向：`core.constants` / `core.validation` → `core` 其余模块；
`core.bitops` / `core.fmt` → `core.codec`；`output` 不依赖 `core`；
`gdb` 各组件 → `core.paging` 和/或 `output`，`gdb.facade` → 全部组件。
无环。

## 安装

项目使用 [uv](https://docs.astral.sh/uv/) 管理。在 checkout 中执行：

```console
uv sync
uv run python -c "import kernlens; print(kernlens.__version__)"
```

`uv sync` 会创建 `.venv`、以可编辑模式安装项目，并按照
`uv.lock` 安装 `dev` 依赖组。请提交 `uv.lock`，确保本地与 CI
使用完全一致的依赖版本。

只安装运行时依赖（可编辑模式）：

```console
uv pip install -e .
```

或者把 `src/kernlens/` 目录拷进项目根后直接导入：

```python
from kernlens import BITS, LE, BE, IntFmt, KAddr, KPageTable, Logger, Styler
```

需要 Python 3.10+。Python < 3.12 时唯一运行时依赖是
`typing-extensions`（提供 `typing.override`）。

包内附带 `src/kernlens/py.typed`，因此类型检查器会把它视为符合
PEP 561 的类型化分发包。该标记有意保持为空（不是 `partial`）：
所有公开模块都有类型标注，并且该文件会同时进入 wheel 与源码包。

gdb 侧把包所在目录加入 `sys.path` 后正常导入 facade：

```python
import sys
sys.path.insert(0, "/path/to/repo/src")

from kernlens.gdb.facade import kdbg
```

`import kernlens.gdb` 本身在 gdb 外是安全的，组件名按需懒加载。
GDB 需要内置 Python 3.10 或更新版本。

## GDB 启动文件

在 `~/.gdbinit` 中加入一行，即可让每个 GDB 会话直接使用 KernLens：

```gdb
source /path/to/KernLens/gdbinit.py
```

在 checkout 中可以直接写入用户启动文件：

```console
echo "source $(pwd)/gdbinit.py" >> ~/.gdbinit
```

`gdbinit.py` 会自动把 checkout 的 `src/` 加入 `sys.path`，因此即使
没有把包安装进 GDB 的 Python 环境也能使用。它注册命令并安装公共
Python API，但不会在加载时安装任何断点，可以在 `file vmlinux` 之前
加载。

### 供 trace 脚本使用的 Python API

`gdbinit.py` 被 GDB source 时运行在 `__main__` 命名空间，因此它会
把项目公共类/常量（`KAddr`、`KPageTable`、`IntFmt`、`BitOps` 等）、
`KernelDebugger` 类和共享的 `kdbg` 对象、`read_kvar`、`kvar_addr`、
`walk`、`sym`、`head_to_page`、`print_slab`、`find_kbase` 等 facade
自由函数，以及
`byte_swap64`、`popcount`、`pack_u16`、`virt_to_phys`、`split_4` 等
无状态核心工具函数安装到该命名空间。之后 `source trace.py` 可以直接
调用这些名字，不需要再写 `from kernlens import ...`：

```gdb
# ~/.gdbinit
source /path/to/KernLens/gdbinit.py
```

```python
# trace.py
print(byte_swap64(0x1122334455667788))
print(popcount(0xFF))
print(split_4(0xFFFF888000001234))
print(pack_u16(0x1234))
print(virt_to_phys(0xFFFF888000001234))
print(read_kvar("jiffies"))
```

```gdb
(gdb) source /path/to/trace.py
```

为避免重名，推荐优先使用类名限定形式：

```python
BitOps.byte_swap64(value)
KAddr.virt_to_phys(addr)
KPageTable.split_4(addr)
IntCodec.pack_u16(value)
IntFmt.size(1024)
```

同时提供标识符安全的 `BitOps_byte_swap64(...)` 别名，以及带点号的
`KERNLENS_QUALIFIED["BitOps.byte_swap64"]` 映射；`byte_swap64(...)`
这类裸别名仍保留，便于短脚本快速使用。

有状态组件直接提供与 `kdbg` 共用的默认实例：

```python
logger.info("trace hit")
styler.addr(address)
reader.u64("$rdi")
symbols.sym(pc)
slub.print_slab(head)
```

`KERNLENS_INSTANCES` 映射这些名字（`config`、`logger`、`styler`、
`reader`、`symbols`、`kaslr`、`cpu`、`walker`、`slub`、`kdbg`）到
对应对象。需要独立状态时，可通过 `KERNLENS_CLASSES` 实例化：

```python
local_logger = KERNLENS_CLASSES["Logger"]()
local_styler = KERNLENS_CLASSES["Styler"]()
local_config = KERNLENS_CLASSES["DebugConfig"]()
```

每次构造都会得到独立对象；修改 `local_logger`、`local_styler` 或
`local_config` 不会影响全局的 `logger`、`styler`、`config`。

`KERNLENS_API` 是已安装名字的完整映射，便于发现和检查；
`FACADE_FUNCTIONS` 列出 facade 自由函数，其余无状态别名来自
`BitOps`、`IntCodec`、`KAddr`、`KPageTable` 和 `IntFmt`。`kdbg`
仍是首选的面向对象入口。可运行的示例见
[`examples/trace.py`](examples/trace.py)。

### 获取帮助

所有命令都支持在 GDB 内自解释：

```gdb
(gdb) kl-help            # 按类别列出所有命令
(gdb) kl-help walk       # 查看单个命令的用法、参数与示例
(gdb) kl-walk --help     # 等效写法；-h、help、? 同样可用
```

参数错误不再只打印一行 `usage`，而是给出引导信息：

```gdb
(gdb) kl-walk
kl-walk: invalid arguments
usage : kl-walk <virtual-address> [4|5]
try   : kl-help walk   (detailed help and examples)
```

`help kl-walk`（GDB 原生帮助）会显示同样的摘要、用法、参数与示例。
完整命令表如下。

| 命令                               | 短别名            | 作用                                          |
| ---------------------------------- | ----------------- | --------------------------------------------- |
| `kernlens-help [command]`          | `kl-help`         | 列出命令，或查看某个命令的详细帮助            |
| `kernlens-status`                  | `kl-status`       | 版本、颜色、KASLR、`_text`、布局基址、拓扑    |
| `kernlens-slab <list\|info\|contains\|details> [arg] [--verbose] [--cpu <id>] [--node <id>] [--partial] [--active]` | `kl-slab` | SLUB cache：`list` / `info` / `contains`（pwndbg 形式）、`details` 细粒度 inspector；直接跟地址则打印该 slab |
| `kernlens-page <address> [--verbose]` | `kl-page`      | 地址分类；直接映射地址还会翻译物理地址和 page |
| `kernlens-pte <page-table-entry> [virtual-address]` | `kl-pte` | 解码 PTE 标志；按 4K/2M/1G 三种 leaf 给出翻译 |
| `kernlens-sym <address>`           | `kl-sym`          | 将地址解析为符号和源码位置                    |
| `kernlens-bt [depth] [--chain]`    | `kl-bt`           | 格式化内核调用栈；`--chain` 输出紧凑调用链    |
| `kernlens-chain [depth]`           | `kl-chain`        | 紧凑的 `caller <- callee` 调用链              |
| `kernlens-read <address> [count] [--mode ascii]`  | `kl-read`         | 按 64 位字 dump 内存；`--mode ascii` 输出字节             |
| `kernlens-kvar <symbol>`           | `kl-kvar`         | 读取 KASLR 感知的内核全局变量                 |
| `kernlens-read-field <address> <type> <path>` | `kl-read-field` | 读取结构体字段（整数）              |
| `kernlens-addr <address> [tag-mask]` | `kl-addr`       | 完整 KAddr 分析，包括 ERR_PTR/tag             |
| `kernlens-pt <virtual-address>`    | `kl-pt`           | 4/5 级页表索引和大页基址                      |
| `kernlens-walk <virtual-address> [4\|5] [--pgd <table>]` | `kl-walk`   | 按 CR3 实际走页表并解码每一级                 |
| `kernlens-pagewalk <vaddr> [--pgd <table>]` | `kl-pagewalk` | pwndbg 风格页表遍历（最深一级在前） |
| `kernlens-bits <value> [bit-index]` | `kl-bits`        | BitOps popcount/扫描和位操作                  |
| `kernlens-int <value> [width]`     | `kl-int`          | 有符号/无符号和 LE/BE 整数视图                |
| `kernlens-cpu [cpu]`               | `kl-cpu`          | CPU 拓扑、在线掩码、当前 CPU、per-CPU 偏移    |
| `kernlens-percpu <symbol> [cpu]`   | `kl-percpu`       | 解析 per-CPU 符号的运行时地址                 |
| `kernlens-msr [name] [--write <v>] [--list] [--range A-B]` | `kl-msr` | 读写 x86_64 模型特定寄存器（MSR，经 GDB 的 `$` 伪寄存器） |
| `kernlens-base`                    | `kl-base`         | 自动选择运行时内核基址和 KASLR slide          |
| `kernlens-kbase [--rebase] [--verbose]`  | `kl-kbase`        | 从 IDT 恢复文本基址                          |
| `kernlens-p2v <paddr>`  | `kl-p2v`          | 物理地址→虚拟地址 + `struct page` 信息        |
| `kernlens-v2p <vaddr>`   | `kl-v2p`          | 虚拟地址→物理地址（走页表）+ page 信息        |
| `kernlens-pageinfo <struct-page>`  | `kl-pageinfo`     | `struct page`→虚拟/物理地址 + 类型/引用计数   |
| `kernlens-kcmdline`                | `kl-kcmdline`     | 打印内核启动命令行                            |
| `kernlens-kversion`                | `kl-kversion`     | 打印内核版本 banner 与 release                |
| `kernlens-kconfig [name] [--load <file>]` | `kl-kconfig` | 打印内核 `CONFIG_*` 配置项                |
| `kernlens-kchecksec`               | `kl-kchecksec`    | 审计内核加固 `CONFIG_*` 选项                  |
| `kernlens-kmod [name] [--load <path>]`             | `kl-kmod`         | 列出已加载的内核模块                          |
| `kernlens-ksyscalls [name]`        | `kl-ksyscalls`    | 列出系统调用表                                |
| `kernlens-kdmesg [--ctime]`        | `kl-kdmesg`       | 打印内核环形缓冲区（dmesg）                  |
| `kernlens-klookup [symbol] [--apply]` | `kl-klookup`      | 从 kallsyms 符号表查找内核符号                |
| `kernlens-kbpf [--verbose] [--break n] [--progs] [--maps] [--values]` | `kl-kbpf` | 列出 BPF 程序与映射 |
| `kernlens-buddydump [--zone z] [--order n] [--mtype m] [--pcp-only] [--cpu c] [--node n] [--find a]` | `kl-buddydump` | buddy 分配器空闲链表 |
| `kernlens-kdmabuf`                 | `kl-kdmabuf`      | 列出 dma-buf 及其 scatterlist 链             |
| `kernlens-kaslr <runtime-text-address>` | `kl-kaslr`   | 用运行时 `_text` 设置 KASLR slide             |
| `kernlens-kaslr-offset <offset>`   | `kl-kaslr-offset` | 直接设置 KASLR slide                          |
| `kernlens-color [on\|off\|toggle]` | `kl-color`        | 开关 ANSI 颜色                                |

```gdb
(gdb) kl-sym $pc
(gdb) kl-bt 12
(gdb) kl-chain 8
(gdb) kl-read 0xffff8880032a1c40 8
(gdb) kl-kvar jiffies
(gdb) kl-addr 0xffff888000001000
(gdb) kl-pt 0xffff888000001234
(gdb) kl-walk 0xffff888000001234
(gdb) kl-bits 0xff 3
(gdb) kl-int 0x1234 16
(gdb) kl-cpu
(gdb) kl-percpu current_task 0
(gdb) kl-base
(gdb) kl-kbase
```

`kl-status` 与 `kl-kbase` 都会从实时 IDT 推导 KASLR slide，因此在
`kl-base` 之前也能与读取层实际使用的 slide 保持一致。

`kl-msr` 通过 GDB 的 `$` 伪寄存器（`$efer`、`$lstar`、`$fs_base`
等）读写 MSR，覆盖常用寄存器且无需注入代码。远程目标只会暴露它
实现了的寄存器，因此当内核不提供 `$lstar` 时会明确报告
`the remote target does not expose this MSR`，而不是编造数值。pwndbg
是通过在目标上执行 `rdmsr`/`wrmsr` shellcode 拿到其余寄存器的；
KernLens 有意不在目标中执行代码，所以支持的范围是 `--list`、目标
确实暴露的寄存器，以及对这些寄存器的 `--write`。

这些命令是纯 Python API 的 GDB 薄封装：
`KAddr` → `addr`/`page`，`KPageTable`/`PageTableWalker` →
`pt`/`pte`/`walk`，`BitOps` → `bits`，`IntCodec`/`IntFmt` → `int`，
`MemoryReader`/`SymbolResolver`/`CpuInfo` → `kvar`/`read`/`sym`/
`bt`/`chain`/`cpu`/`percpu`，`SlubInspector` → `slab`，
`Kaslr` → `kaslr`/`status`，`Kbase` → `kbase`，`Styler` → `color`。

### 内核文本基址恢复

`kl-base` 是自动配置命令：没有运行中的内核时显示默认链接期基址并把
KASLR slide 清零；有运行中的内核时从 IDT 恢复当前运行基址，立即把
检测到的 slide 写入 `kdbg.kaslr_offset`，并在重启或重新 attach 后再次
运行以刷新：

```gdb
(gdb) kl-base
kernel base : 0xffffffff99e00000  (runtime)
KASLR offset: +0x18e00000
link _text  : 0xffffffff81000000
method      : symbol
status      : kernel running
```

`kl-kbase` 是同一检测器的底层诊断形式：默认只显示、不修改状态，
加 `--set` 才应用 slide，加 `--verbose`（pwndbg 的同名选项）还可
打印物理地址。`kl-kaslr` 和 `kl-kaslr-offset` 仍用于无法读取 IDT
时的手工覆盖。

检测器与 pwndbg 的 `kbase` 思路相同：x86-64 的 0 号 IDT 门指向
内核 `.text` 中的 `asm_exc_divide_error`。KernLens 从 QEMU 的
`monitor info registers`（或 `$idt` / `idt_table`）读取 IDT，解码
16 字节门描述符，然后依次尝试：

1. 用处理器地址与链接期 `asm_exc_divide_error` 的差值修正链接期
   `_text`（有 vmlinux 时最准确）；
2. 用 `monitor info mem` 找到包含该处理器的映射起始地址；
3. 按 2 MiB 内核文本对齐向下取整。

`kl-kbase --set` 会把检测到的 slide 写入 `kdbg.kaslr_offset`；
`kl-kbase --verbose` 会打印文本基址的物理地址（旧写法 `--phys` 仍然
可用，但已隐藏）。整个过程不依赖 pwndbg。

**KASLR 自适应。** 无需先执行 `kl-base`：内存读取层会在首次 KASLR
感知读取时自动探测 slide；若在当前 slide 下读取失败（例如重启或重新
连接后），会自动重新探测并重试。若调试器已携带重定位（`add-symbol-file
vmlinux <runtime>`），也会回退到按链接时地址读取。每次 slide 变化时，
读取层会清空 inspector 中由地址派生的缓存，因此移植的命令（kallsyms、
modules、syscalls、dmesg、BPF、buddy、SLUB、dma-buf 等）都能跨越
KASLR 变化继续工作。`kl-base` 与 `kl-kbase --set` 仍可用于显式
固定 slide。

原有 `kernlens-*` 命令保持不变，`kl-*` 只是别名。
示例配置见 [`examples/gdbinit.example`](examples/gdbinit.example)。
重复加载 `gdbinit.py` 是安全的；示例 `examples/gdb_tracer.py` 把自己的
命令注册在 `kernlens-tracer-` 前缀下，不会与自带的
`kernlens-slab` / `kernlens-color` 冲突。

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

### 布局签名

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

不在包级导入。gdb 内用正常 import（见[安装](#安装)）
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

## 示例

- [`examples/slab_snapshot.py`](examples/slab_snapshot.py)：不依赖
  gdb，渲染一份 slab 报告；默认使用真实测试内核的取值（一个直接映射
  页及其页表里真实的 PTE，以及真实的 `kmalloc-1k` 形态），可用
  `--head` / `--page-offset-base` / `--vmemmap-base` 指向其它内核。
- [`examples/gdb_tracer.py`](examples/gdb_tracer.py)：在 gdb 内安装
  `kfree` 断点，并提供 `kernlens-tracer-slab` / `kernlens-tracer-color`
  命令（带前缀，避免遮蔽同用途的 KernLens 命令）。
- [`examples/trace.py`](examples/trace.py)：在 `gdbinit.py` 之后
  `source`，直接使用已安装的公共 API，不写 `from kernlens import ...`。
- [`examples/cve_2025_38616_trace.py`](examples/cve_2025_38616_trace.py)：
  CVE-2025-38616 KTLS UAF tracer，直接复用 `gdbinit.py` 已注册的
  API 和命令；`trace-start` 会调用已注册的 `kl-base` 自动选择基址，
  并在安装断点前应用 KASLR。手工配置需先设置非零的
  `kl-kaslr` / `kl-kaslr-offset`，再执行 `trace-start manual`；
  旧的 `kaslr-text` / `kaslr-offset` 名称保留为这些已注册命令的包装。
- [`examples/gdbinit.example`](examples/gdbinit.example)：加载项目根
  `gdbinit.py` 的 `~/.gdbinit` 示例。

## 组合示例

```python
from kernlens import IntFmt, KAddr, KPageTable, Logger, Palette, Styler

log = Logger()
sty = Styler()

head = 0xffff8880032a1c40
phys = KAddr.virt_to_phys(head)
page = KAddr.virt_to_page(head)

log.info(sty.table(
    ["field", "value"],
    [
        ["head",  IntFmt.addr(head)],
        ["phys",  IntFmt.hex64(phys)],
        ["page",  IntFmt.addr(page)],
        ["pfn",   IntFmt.pfn(phys)],
        ["split", str(KPageTable.split_4(head))],
    ],
    aligns=["l", "r"],
))
```

## 测试与开发

测试同时兼容 `unittest` 与 pytest。开发命令统一通过 uv 执行：

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
```

仍可在 uv 环境中使用 stdlib runner：

```console
uv run python -m unittest discover -s tests/unit
uv run python -m unittest discover -s tests/integration
```

集成测试会注入 fake `gdb` 模块，不需要调试器或内核；
`tests/integration/test_gdbinit.py` 还用 fake `gdb` 与 stub facade
直接执行真实的 `gdbinit.py`，因此命令注册、参数解析和输出格式
也无需 GDB 即可覆盖。`uv sync` 已安装项目，因此 `uv run` 会导入
安装后的分发包，不再依赖 `PYTHONPATH`；`pyproject.toml` 另外设置了
`pythonpath = ["src"]`，裸 `pytest` 也能直接在 checkout 中运行。

公共 API 地图、模块职责、SLUB 检查模型与 gdb 加载方式见
[`docs/architecture.md`](docs/architecture.md)；命令与 Python 命名
规范见 [`docs/naming.md`](docs/naming.md)；版本历史见
[`CHANGELOG.md`](CHANGELOG.md)。

### 结构体布局：DWARF → BTF → 验证过的兜底表

所有结构体字段偏移都在首次使用时按三级链解析，因此检查器始终跟随
它所面对的那个内核镜像——偏移会随内核版本和 `CONFIG_*` 变化（例如
`CONFIG_SECURITY` 会在 `struct bpf_map::map_type` 之前插入
`void *security`）：

1. **DWARF**——已加载 `vmlinux` 的调试信息
   （`gdb.parse_and_eval`），对所面对构建精确；
2. **BTF**——镜像内嵌的类型库（`CONFIG_DEBUG_INFO_BTF`），由
   `kernlens.gdb.btf` **自行解析**（不用 `bpftool`、不用
   `libbpf`），用于缺少 DWARF 的构建；
3. **兜底注册表** `kernlens/gdb/layouts.py`——仅当前两者都不可用时。

每个注册表条目都记录结构体的定义位置、验证时使用的内核
（`layouts.VERIFIED_KERNEL`，当前为 Linux 7.0），并按版本与
`CONFIG_*` 选择变体。由于这些值只对一个构建成立，一旦用到兜底层，
命令会打印一次性告警：

```console
kl-kbpf: struct bpf_map, struct dma_buf: no debug info; using built-in
fallback layouts that may not match this kernel. Load a matching vmlinux
for exact struct offsets.
```

对于没有可用 `.BTF` 节的远程目标，也可显式指定 BTF：把
`kdbg.reader.config.btf_path` 指向原始 blob 或带 `.BTF` 节的
`vmlinux`。

`tools/gen_layouts.py` 用于保证注册表不漂移：它探测真实内核
（通过 GDB 的 DWARF 读 `vmlinux`，或通过项目自带的解析器读 BTF，
不需要 `bpftool` / `libbpf`），并可据此校验注册表：

```console
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux --check
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux --check
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux   # 报告
```

`--check` 在发现任何偏差时以非零码退出，可用于 CI 中守护表的更新。

## 许可证

GPL-3.0-or-later，见 [`LICENSE`](LICENSE)。

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
  [`docs/naming.md`](docs/naming.md)：可读、不过长，一个概念只用一种拼写。
