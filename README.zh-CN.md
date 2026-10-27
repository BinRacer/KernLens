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
    <a href="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml"><img src="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml/badge.svg" alt="CI 状态"></a>
    <a href="https://github.com/BinRacer/KernLens"><img src="https://img.shields.io/badge/GitHub-KernLens-181717.svg" alt="GitHub: KernLens"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="许可证：GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-informational" alt="Python 3.10-3.13">
    <img src="https://img.shields.io/badge/GDB-introspection-informational" alt="GDB introspection">
  </p>
</div>

## 概览

KernLens 给 GDB 增加 **40 个命令**，用来读一个正在运行的 Linux 内核。
每个命令都通过同一个 reader 读真实内存，用可以手算核对的算术解码，并把
结果连同"它来自哪个表项"一起打印出来 —— 所以错误的结果看起来就是错的，
而不是看起来像真的。

`core/` 与 `output/` 是纯 Python，完全不依赖 GDB；只有 `gdb/` 需要
调试目标。

## 它长什么样

一个 2 MiB 映射，逐级走查。走查停下的位置和硬件一致：

```text
VA: 0xffff8cb880400000
Paging: 4-level  root=0x6ad2000
pgd      : idx=0x119 entry=0x6ad28c8 value=0x4a01067 -> 0x4a01000
pud      : idx=0xe2 entry=0x4a01710 value=0x4a02067 -> 0x4a02000
pmd      : idx=0x2 entry=0x4a02010 value=0x80000000004000e3 (huge leaf)
Leaf: 2 MiB huge pa=0x400000 offset=0x0
Flags: P RW A D PAT PS NX
```

每行给出索引、**表项自身的地址**、原始值和下一级的去处。`pmd` 上的
`PS` 位就是没有 `pte` 那一行的原因。同一个地址强制按 5 级页表走查：

```text
pgd      : idx=0x1ff entry=0x6ad2ff8 value=0x3015067 -> 0x3015000
p4d      : idx=0x119 entry=0x30158c8 value=0x0
Note: p4d entry is not present
```

SLUB 分配器，其中 `Size` 与 `Obj Size` 的差值就是每个对象的额外开销：

```text
Name                         # Objects  Size  Obj Size  order
ext4_groupinfo_4k            22         184   184       0
AF_VSOCK                     25         1280  1232      3
MPTCPv6                      15         2112  2064      3
```

以及空闲链表的编码 —— 这是 use-after-free 追踪器必须算对的部分。
槽位里存的**不是指针**：

```text
cpu 0 first object : 0xffff911c466b5000
  slot address   : 0xffff911c466b5200   (object + offset 512)
  stored word    : 0xfa9c7eb28ed8d5fb
  decoded next   : 0xffff911c466b5800
  the arithmetic : 0xffff911c466b5800 ^ 0x53184e8d4227204 ^ swab(0xffff911c466b5200) = 0xfa9c7eb28ed8d5fb
  check          : 0xfa9c7eb28ed8d5fb
```

## 快速开始

```console
git clone https://github.com/BinRacer/KernLens
echo "source $(pwd)/KernLens/gdbinit.py" >> ~/.gdbinit
```

```gdb
(gdb) file vmlinux
(gdb) target remote :1234
(gdb) kl-base            # 恢复 KASLR 偏移并应用
(gdb) kl-help            # 按分类列出全部命令
```

**先跑 `kl-base`**：在 KASLR 内核上，vmlinux 里的每个符号都还停在链接期
地址，偏移没应用之前解析出来的东西一律不可信。加载 `gdbinit.py` 不会
装任何断点，在 `file vmlinux` 之前 source 也安全。

源码 checkout 就是唯一的安装方式。KernLens 未发布到 PyPI，从那里安装
也得不到能用的副本：快速开始里 source 的那个启动文件并不在 wheel 里。
`gdbinit.py` 会把自己的 `src/` 加进 `sys.path`，所以没有东西需要安装，
也没有版本需要对齐；升级就是 `git pull`。开发环境搭建见
[`CONTRIBUTING.zh-CN.md`](CONTRIBUTING.zh-CN.md)。

## 40 个命令

分组与 `kl-help` 完全一致。`kl-` 形式是你在提示符下敲的；规范的
`kernlens-` 形式是脚本和生成式教程用的。两者始终都能用。

### 内核元信息 (8)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-kchecksec` | `kl-kchecksec` | 内核加固项审计 |
| `kernlens-kcmdline` | `kl-kcmdline` | 启动命令行 |
| `kernlens-kconfig` | `kl-kconfig` | 内核配置项 |
| `kernlens-kdmesg` | `kl-kdmesg` | 内核日志 |
| `kernlens-klookup` | `kl-klookup` | 符号搜索 |
| `kernlens-kmod` | `kl-kmod` | 已加载模块 |
| `kernlens-ksyscalls` | `kl-ksyscalls` | 系统调用表 |
| `kernlens-kversion` | `kl-kversion` | 内核版本 |

### 地址与页表 (9)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-addr` | `kl-addr` | 地址分类 |
| `kernlens-p2v` | `kl-p2v` | 物理地址转虚拟 |
| `kernlens-page` | `kl-page` | 地址所属页 |
| `kernlens-pageinfo` | `kl-pageinfo` | 解析 struct page |
| `kernlens-pagewalk` | `kl-pagewalk` | 页表走查（pwndbg 格式） |
| `kernlens-pt` | `kl-pt` | 页表索引 |
| `kernlens-pte` | `kl-pte` | 解码页表项 |
| `kernlens-v2p` | `kl-v2p` | 虚拟地址转物理 |
| `kernlens-walk` | `kl-walk` | 逐级走查页表 |

### 内存与符号 (11)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-bt` | `kl-bt` | 调用栈 |
| `kernlens-buddy` | `kl-buddy` | 在伙伴系统中定位地址 |
| `kernlens-buddydump` | `kl-buddydump` | 伙伴系统空闲链转储 |
| `kernlens-chain` | `kl-chain` | 精简调用链 |
| `kernlens-kbpf` | `kl-kbpf` | BPF 程序与映射 |
| `kernlens-kdmabuf` | `kl-kdmabuf` | dma-buf 对象 |
| `kernlens-kvar` | `kl-kvar` | 读取内核变量 |
| `kernlens-read` | `kl-read` | 内存转储 |
| `kernlens-read-field` | `kl-read-field` | 读取结构体字段 |
| `kernlens-slab` | `kl-slab` | SLUB 缓存检查 |
| `kernlens-sym` | `kl-sym` | 地址转符号 |

### 内核基址与 KASLR (4)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-base` | `kl-base` | 当前基址与偏移 |
| `kernlens-kaslr` | `kl-kaslr` | 由运行时地址求偏移 |
| `kernlens-kaslr-offset` | `kl-kaslr-offset` | 直接设置偏移 |
| `kernlens-kbase` | `kl-kbase` | 查找内核基址 |

### CPU 拓扑 (3)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-cpu` | `kl-cpu` | CPU 拓扑 |
| `kernlens-msr` | `kl-msr` | MSR 寄存器 |
| `kernlens-percpu` | `kl-percpu` | per-CPU 符号地址 |

### 位与整数原语 (2)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-bits` | `kl-bits` | 按位查看 |
| `kernlens-int` | `kl-int` | 按整数查看 |

### 总览 (1)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-status` | `kl-status` | 会话状态 |

### 输出 (1)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-color` | `kl-color` | 颜色开关 |

### 帮助 (1)

| 命令 | 别名 | 输出内容 |
| --- | --- | --- |
| `kernlens-help` | `kl-help` | 命令参考 |

每个命令在 [`docs/tutorial/`](docs/tutorial/) 都有一页：真实捕获的输出、
全部选项，以及如何读这个结果。

命令表看不出来的有两件事。一是 `kl-help <命令>` 给出用法和现成例子，
且 `--help` 在所有命令上都可用，错误信息是引导式的而不是一行 usage。
二是这些命令从不 `stop()` 调试目标 —— 它们只读内存然后返回，所以可以
放进断点处理函数里组合使用。

## 当库用

命令只是一层薄壳，底下是 Python API。在 source 过的脚本里直接调用：

```python
# 在 gdbinit.py 之后 source 的任意文件 —— 名字已经装好了
print(split_4(0xffff888000001234))       # KPageTable，不读内存
print(read_kvar("jiffies"))              # 经 facade 读活内存
print(LE.unpack_u32(b"\x34\x12\x00\x00"))  # LE 本身就是 ByteOrderCodec
```

或者正常导入：

```python
from kernlens import KAddr, KPageTable

# (0x111, 0x0, 0x0, 0x1, 0x234) —— 每级一个索引，最外层在前
KPageTable.split_4(0xffff888000001234)
KAddr.is_direct_map(0xffff888000001234)  # True
```

算术那一半不需要调试器，这正是它能在宿主机上被测试的原因。完整参考见
[`docs/api.zh-CN.md`](docs/api.zh-CN.md)。

## 它凭什么不会说假话

本仓库对自己做出的每一句断言都由机器校验，否则就只是"写下来那天正确"
的散文：

- `docs/tutorial/` 是**生成**的，来自在真实内核上的捕获；
  `gen_tutorial.py --check` 在页面与捕获不一致时失败。
- 示例覆盖度在 `tools/example_manifest.py` 中声明，由
  `tools/check_examples.py --check` 强制执行：声明了但代码里没有会失败，
  只在散文里提到却从未执行的命令同样会失败。
- 不需要调试器的示例在 CI 里真跑；其余的在 GDB 下重放并记录，每次推送
  都把记录和源码比对。
- `docs/architecture.md` 里的目录树、`examples/README.md` 里的数字，都
  与实际树和实际测量比对，而不是手写。

本页出现的 `kl-*` 命令数由测试对命令注册表校验，所以它不会悄悄变成假的。

## 文档地图

| 文档 | 内容 |
| --- | --- |
| [`docs/tutorial/`](docs/tutorial/) | 每个命令一页，真实输出 |
| [`docs/api.zh-CN.md`](docs/api.zh-CN.md) | Python API 参考 |
| [`docs/architecture.md`](docs/architecture.md) | 包结构、API 映射、设计说明 |
| [`examples/`](examples/README.md) | 可运行脚本，按意图分组 |
| [`docs/naming.md`](docs/naming.md) | 命令与文件名约定 |
| [`CONTRIBUTING.zh-CN.md`](CONTRIBUTING.zh-CN.md) | 环境搭建、测试、布局生成器 |
| [`SECURITY.md`](SECURITY.md) | 什么算漏洞，以及如何私下报告 |
| [`CHANGELOG.md`](CHANGELOG.md) | 全部变更，最新的在前 |

## 环境要求与许可

Python 3.10+，以及一个用 Python 3.10+ 构建的 GDB。仅支持 x86_64 内核
—— 页表与 `struct page` 的解码是针对该架构写的。Python 3.12 以下唯一
的运行时依赖是 `typing-extensions`。

不发布任何包。安装方式就是 `git clone`，见[快速开始](#快速开始)。
PyPI 上的 `kernlens` 不是这个项目。

GPL-3.0-or-later。见 [`LICENSE`](LICENSE)；第三方归属见
[`CREDITS.md`](CREDITS.md)。
