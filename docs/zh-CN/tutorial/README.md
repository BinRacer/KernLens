# KernLens 教程

逐个命令走一遍 KernLens，输出取自真实内核，而不是编造的例子。

每页结构一致：命令回答什么、确切的调用、它在捕获内核上产生的输出、如何读这段输出，以及它在什么情况下会拒绝。页面按 `kl-help` 打印的分类分组。

## 捕获内核 {#the-capture-kernel}

本教程的全部输出来自项目测试虚拟机的一次启动：

| 事实 | 值 |
| --- | --- |
| 内核 | `6.1.134` (x86_64, DWARF debug info) |
| CPU 数 | 4 |
| SLUB 缓存数 | 170 |
| KASLR 偏移 | `0x2cc00000` |
| `_text`（链接时） | `0xffffffff81000000` |
| `_text`（运行时） | `0xffffffffadc00000` |
| `page_offset_base` | `0xffff975280000000` |
| `vmemmap_base` | `0xffffee5d00000000` |
| 一个空闲页（物理） | `0x400000` |
| 它的直接映射别名 | `0xffff975280400000` |
| 它的 `struct page` | `0xffffee5d00010000` |

`page_offset_base` 与 `vmemmap_base` 是启动代码填进去的内核**变量**，所以每次启动都会变，偏移也随之变化。这里其余的（结构体偏移、zone 列表、缓存名、符号名）对本次构建是稳定的。凡是与启动相关的，KernLens 都在运行时重新推导而不是假定，这就是命令显示这些数字而不是某个常量的原因。

### 复现这份捕获

```gdb
(gdb) source /path/to/KernLens/gdbinit.py
(gdb) file /path/to/vmlinux
(gdb) target remote :1234
(gdb) kl-color off
(gdb) python exec(open("tools/tutorial_capture.py").read())
```

`kl-color off` 不是装饰：它让捕获文本里没有 ANSI 转义序列，这些页面才能干净地 diff。捕获脚本写出 `tools/tutorial_capture.json`；`tools/gen_tutorial.py` 再从它渲染页面，页面与捕获不一致时 `--check` 会失败。

## 怎么读这些页面

- **调用** —— 确切的命令行。用的是 `kl-` 别名；每一个都展开为 `kernlens-` 名。
- **输出** —— 原样，包括对齐。表头行下缩进两格是 KernLens 表示“该记录的一行”的约定。
- **读法** —— 每一行是什么意思，以及从这些值能得出什么结论。
- **说明** —— 这些值从哪来（DWARF、BTF、注册表兜底，还是裸内存），以及命令在什么情况下拒绝。

## 页面

### Help

在命令集里找到方向。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-help`](../../en/tutorial/kl-help.md) | Lists every KernLens command, or explains one in detail. |

### Overview

在陌生的会话上第一个该跑的命令。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-status`](../../en/tutorial/kl-status.md) | Shows the KernLens version, color mode, KASLR slide, and layout. |

### Kernel base & kaslr

内核被加载到哪里，以及 KernLens 如何应对随机化的基址。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-base`](../../en/tutorial/kl-base.md) | Selects the runtime kernel text base and KASLR slide. |
| [`kl-kaslr`](../../en/tutorial/kl-kaslr.md) | Sets the KASLR slide from a runtime _text address. |
| [`kl-kaslr-offset`](../../en/tutorial/kl-kaslr-offset.md) | Sets the KASLR slide directly. |
| [`kl-kbase`](../../en/tutorial/kl-kbase.md) | Finds the kernel virtual base address. |

### Kernel metadata

配置与构建信息：命令行、版本、选项、模块、系统调用表，以及日志。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-kchecksec`](../../en/tutorial/kl-kchecksec.md) | Checks for kernel hardening configuration options. |
| [`kl-kcmdline`](../../en/tutorial/kl-kcmdline.md) | Return the kernel command line (/proc/cmdline). |
| [`kl-kconfig`](../../en/tutorial/kl-kconfig.md) | Outputs the kernel config (/proc/config.gz). |
| [`kl-kdmesg`](../../en/tutorial/kl-kdmesg.md) | Displays the kernel ring buffer (dmesg) contents. |
| [`kl-klookup`](../../en/tutorial/kl-klookup.md) | Lookup kernel symbols |
| [`kl-kmod`](../../en/tutorial/kl-kmod.md) | Displays the loaded Linux kernel modules. |
| [`kl-ksyscalls`](../../en/tutorial/kl-ksyscalls.md) | Displays the Linux syscall table, including names and addresses of syscalls. |
| [`kl-kversion`](../../en/tutorial/kl-kversion.md) | Outputs the kernel version (/proc/version). |

### Cpu topology

有多少 CPU，它们的 per-CPU 数据在哪里。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-cpu`](../../en/tutorial/kl-cpu.md) | Displays CPU topology, the online mask, and per-CPU offsets. |
| [`kl-msr`](../../en/tutorial/kl-msr.md) | Reads or writes x86_64 model-specific registers (via GDB). |
| [`kl-percpu`](../../en/tutorial/kl-percpu.md) | Resolves a per-CPU symbol to its runtime address for a CPU. |

### Addresses & page tables

从一个原始 64 位值到它指向的物理页，两个方向都有。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-addr`](../../en/tutorial/kl-addr.md) | Prints a full KAddr analysis of an address. |
| [`kl-p2v`](../../en/tutorial/kl-p2v.md) | Translates a physical address to virtual + struct page. |
| [`kl-page`](../../en/tutorial/kl-page.md) | Classifies an address and translates direct-map addresses. |
| [`kl-pageinfo`](../../en/tutorial/kl-pageinfo.md) | Translates a struct page to virtual and physical addresses. |
| [`kl-pagewalk`](../../en/tutorial/kl-pagewalk.md) | Walks the page tables in pwndbg's pagewalk format. |
| [`kl-pt`](../../en/tutorial/kl-pt.md) | Shows 4-level/5-level page-table indices for an address. |
| [`kl-pte`](../../en/tutorial/kl-pte.md) | Decodes page-table entry flags and leaf translations. |
| [`kl-v2p`](../../en/tutorial/kl-v2p.md) | Translates a virtual address (live page tables) to physical. |
| [`kl-walk`](../../en/tutorial/kl-walk.md) | Walks the live page tables and decodes every level. |

### Memory & symbols

读内核自己的内存：符号、栈、SLUB、buddy 分配器、BPF 与 dma-buf。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-bt`](../../en/tutorial/kl-bt.md) | Prints a formatted kernel backtrace. |
| [`kl-buddy`](../../en/tutorial/kl-buddy.md) | Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block. |
| [`kl-buddydump`](../../en/tutorial/kl-buddydump.md) | Displays metadata and freelists of the buddy allocator. |
| [`kl-chain`](../../en/tutorial/kl-chain.md) | Prints a compact caller <- callee call chain. |
| [`kl-kbpf`](../../en/tutorial/kl-kbpf.md) | Prints information about the linux kernel bpf progs and maps. |
| [`kl-kdmabuf`](../../en/tutorial/kl-kdmabuf.md) | Prints DMA buf info. |
| [`kl-kvar`](../../en/tutorial/kl-kvar.md) | Reads a KASLR-aware kernel global variable. |
| [`kl-read`](../../en/tutorial/kl-read.md) | Dumps kernel memory as 64-bit words with symbol annotations. |
| [`kl-read-field`](../../en/tutorial/kl-read-field.md) | Reads a struct field (including nested paths) as an integer. |
| [`kl-slab`](../../en/tutorial/kl-slab.md) | Prints information about the linux kernel's slab allocator SLUB. |
| [`kl-sym`](../../en/tutorial/kl-sym.md) | Resolves an address to a symbol and source location. |

### Bit & integer primitives

对手上已有的值做纯算术。这是仅有的几个完全不碰内核状态的命令。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-bits`](../../en/tutorial/kl-bits.md) | Inspects a 64-bit value; optionally test/set/clear a bit. |
| [`kl-int`](../../en/tutorial/kl-int.md) | Shows signed/unsigned and LE/BE integer views. |

### Output

输出呈现控制。

| 命令 | 它回答什么 |
| --- | --- |
| [`kl-color`](../../en/tutorial/kl-color.md) | Enable, disable, or toggle ANSI color output. |

## 每页通用的约定

KernLens 的输出区分三种状态，读这些页面时这个区分很重要：

- 一个**值**（`Size: 0xc0`）—— 从活动内核读出；
- `?` —— 该数据在本次构建或当前状态下不可得，命令如实说明，而不是打印一个看似合理的 0；
- `<unreadable>` —— 内存完全读不出来（坏地址、页未加载）。

每层嵌套缩进两格对齐，标签后面跟 `: `（一个空格），这样值能排成一列。

---

由 `tools/gen_tutorial_index.py` 从与页面相同的捕获生成。不要手改：重新运行生成器。
