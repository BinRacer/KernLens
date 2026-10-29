# 命名约定

KernLens 有两个命名面：

- **GDB 命令行**，命令必须短、好敲（`kernlens-walk`、`kl-walk`）；
- **Python API**，名字会在脚本、测试失败和 traceback 里被读到，所以必须可读，但
  不能变长。

下面的规则同时约束这两个面，由代码评审而非 linter 保证。

## GDB 命令

- 规范命令是 `kernlens-<动词>`；后缀一到两个词：`kernlens-slab`、
  `kernlens-kaslr-offset`。
- 每个规范命令都有一个 `kl-<动词>` 别名。别名是预期的交互形式；规范名用于脚本和
  文档。
- **不**因 Python API 变化而改命令名。命令层是稳定的用户界面，Python 层是实现。
- 命令住在 `kernlens.commands`（每个领域一个模块），是 pwndbg 风格的**普通函数**：
  一个名为 `kernlens_<动词>` 的函数，用 `@Command(parser, category, ...)` 装饰。
  框架从函数名推出 `kernlens-<动词>` 命令名（下划线变连字符）；装饰器记录一个
  `CommandDefinition`，由 `register_all()` 实例化 `gdb.Command` 包装器，所以没有
  手写的类。
- 每个命令绑定一个 `argparse.ArgumentParser`；`-h`/`--help` 渲染该 parser（示例、
  说明和别名列表折进 epilog）。领域函数给选项加的注解名与 argparse 的 `dest` 同名。
- 从 pwndbg 移植的命令保留 pwndbg 的选项拼写——长名和短名都保留
  （`-p/--progs`、`-p/--pcp-only`、`-b/--break`、`-r/--range`）——也保留 pwndbg 的
  metavar（`<vaddr>`、`<paddr>`），这样从 pwndbg 工作流里抄来的命令行继续可用。
  KernLens 独有的选项按同样风格添加；pwndbg 没有的选项（`kl-base --rebase`、
  `kl-slab --detail`）保持可用，但通过 `framework.hide()` 注册，让 `--help` 只显示
  pwndbg 那部分界面。

## 模块与包

- 包名是短的小写名词：`core`、`output`、`gdb`、`commands`、`inspectors`。
- 模块名是 `snake_case`，且只表示一件事：`bitops.py`、`codec.py`、`paging.py`、
  `palette.py`、`walker.py`。
- 一个包可以把许多小模块归到带私有前缀的共享基座上（`inspectors/_base.py`）；下划线
  标记它是内部管道，不是领域模块。
- 包的 `__init__.py` 重导出其公开面；它可以包含惰性导入的接线，但不含领域逻辑。
- 每个模块拥有唯一实现；包根目录下没有历史遗留的重导出模块。

## 示例文件

示例不是库模块：读者在还不知道它做什么的时候先遇到它，而文件名是目录列表、traceback
和 `git diff` 里唯一可得的描述。所以它们多带一条信息——这个文件是**哪一类**东西。

**`<主题>_<类别>.py`**，小写 `snake_case`，主题不用纯数字，类别不由动词顶替。

| 类别 | 这个文件 | 它的产物 |
| --- | --- | --- |
| `_tour` | 安装一个命令，按段打印 | 对某一主题的通览 |
| `_walk` | 安装一个命令，沿结构逐环跟进 | 它走过的链 |
| `_tracer` | 安装从不中断调试目标的断点 | 一份日志 |
| `_bp` | 安装一个以停下或做判定为目的的断点 | 一次陷阱 |
| `_snapshot` | 只用常量算出一份报告，不需要目标 | 一张表 |
| `_sample` | 能跑起来的最小东西 | 可复制的起点 |

| 文件 | 主题 | 类别 |
| --- | --- | --- |
| `api/address_tour.py` | 一个地址的多种页表视图 | `_tour` |
| `api/installed_api_tour.py` | `gdbinit.py` 装好的那些名字 | `_tour` |
| `api/kernel_facts_tour.py` | 目标的自述信息 | `_tour` |
| `api/freelist_walk.py` | SLUB 空闲链表编码 | `_walk` |
| `api/slab_snapshot.py` | 由常量得出的 slab 报告 | `_snapshot` |
| `api/hello_sample.py` | 最小可用脚本 | `_sample` |
| `tracing/gdb_tracer.py` | `kfree` 的参数 | `_tracer` |
| `tracing/cve_2025_38616_tracer.py` | 某个 CVE 的 UAF 链 | `_tracer` |
| `breakpoints/conditional_bp.py` | 某个对象的释放 | `_bp` |
| `breakpoints/per_cpu_bp.py` | 每 CPU 寻址 | `_bp` |

豁免：`api/gdbinit.example` 是一段 dotfile 片段，不是脚本。

类别不是装饰——它是读者最需要的第一件事，也是文件名最容易漏掉的东西。
`trace.py` 既没说主题也没说类别；它现在是 `installed_api_tour.py`，这次改名就是这条
规则的全部论据。`gdb_tracer.py` 保留它的主题（`gdb`），只因为它是其他 tracer 参照的
*通用* tracer；讲某个具体子系统的文件要写出那个子系统。

`tools/check_examples.py --check` 会强制这个模式，所以一个名字没归类的示例会让构建
失败，而不是事后才被发现。

## 导入路径

- `from kernlens import ...` 是纯 Python 核心层与输出层便利的公开面。
- `from kernlens.core.<module> import ...` 与 `from kernlens.output import ...` 是
  规范的层内导入。
- GDB 代码用 `from kernlens.gdb.facade import kdbg`；只需要一个适配器组件时直接导入
  组件模块，如 `kernlens.gdb.walker`；内核子系统的 mixin 住在
  `kernlens.gdb.inspectors` 下。
- GDB 命令住在 `kernlens.commands`；`gdbinit.py` 只负责把它们引导起来。
- 不要添加兼容别名或重导出模块；新代码使用这些规范路径。

## Python API

### 类

- `PascalCase`，名词在前：`PageTableWalker`、`KernelDebugger`、`MemoryReader`、
  `SlubInspector`。
- 内核缩写按词写：`CpuInfo`、`Kaslr`、`SlubInspector`。
- `KAddr` 与 `KPageTable` 是既有的例外；不要新增 `K` 前缀的类。

### 函数与方法

- `snake_case`，动作动词在前：`read_*`、`write_*`、`print_*`、`walk`、`kvar_addr`、
  `decode_*`。
- 谓词以 `is_` / `has_` 开头：`is_present`、`is_direct_map`。
- 格式化函数以 `fmt_` 开头，或是格式化命名空间里的短名词：`fmt_line`、
  `IntFmt.addr`、`Styler.hex64`。
- 转换函数用 `<源>_to_<目标>`：`virt_to_phys`、`phys_to_pfn`。
- 读取函数用 `read_*`；返回内核地址的读取函数用 `kvar_addr`，而不是再加一个
  `read_*` 动词。
- 简单查询避免 `get_` 前缀：`counters()`，不是 `get_counters()`。
- 一个概念一种拼写：同一层里不要混用 `format_` 与 `fmt_`、`typ` 与 `int_type`、
  `offset` 与 `off`。

### 变量与参数

- `snake_case`；在需要时用名词加单位：`kaslr_offset`、`page_size`、`byte_count`。
- 单字母只允许用作循环下标（`i`、`j`）或约定的数学名（`x`、`y`）。
- 布尔量读起来像断言：`color_enabled`、`five_level`、`in_partial`。
- 私有模块状态与辅助函数以 `_` 开头；常量是 `UPPER_SNAKE`。

### 缩写

以下是本仓库风格的一部分，可以直接使用而无需展开：

```
addr  off   len   nr    cur   prev  cfg   ctx   buf   tmp   ptr
val   ret   err   pfn   pte   pgd   pud   pmd   p4d   va    pa
phys  virt  kaslr percpu slub kvar  freeptr fmt  bt    kv    id
u8 u16 u32 u64 i8 i16 i32 i64 le be
```

其余一律写全。特别地，不要把 C 库缩写如 `clz`、`ctz`、`ffs`、`fls`、`rotl`、
`rotr`、`bswap` 加进公开 API；可读的形式是 `leading_zeros`、`trailing_zeros`、
`first_set`、`last_set`、`rotate_left`、`rotate_right`、`byte_swap`。

### 长度

- 目标两个词，容忍三个。
- 超过约 20 字符的公开名需要有理由；优先更短的名词（`cpu_slab_ptr`，而不是
  `cpu_slab_template_pointer`）。
- 私有辅助函数在多余的字能防住 bug 时可以更长，但同一张缩写表仍然适用。

---