# 架构

**KernLens**（`kernlens`）是一个依赖很少的小型工具集，用于从 Python 与 GDB
调试 Linux 内核。它刻意分成两层：一个可以在任何地方做单元测试的纯 Python
内核，以及一个把依赖 `gdb` 的模块挡在内核导入路径之外的 GDB 适配层。在 GDB
之外导入 `kernlens` 或 `kernlens.gdb` 是安全的；真正解析一个会导入 `gdb` 的
组件才需要调试器会话。

## 目标

- **纯 Python 内核。** 编码、位运算、地址分类、页表算术、格式化与日志，都不
  需要 GDB、Linux 或目标内核。
- **状态显式。** 纯函数是静态的，模块级状态不可变。可变状态只存在于显式的
  `Logger`、`Styler`、`DebugConfig`、适配层组件，以及 `kdbg` 实例里。
- **可预测的 64 位语义。** 指针与页表辅助函数把输入掩到 64 位，所以负的
  Python 整数表现得就像对应的无符号内核值。
- **在边界上校验。** 公开的辅助函数拒绝不可能的位宽、对齐、类型码与偏移，
  而不是默默算出无意义的结果。
- **纯文本输出。** 格式化函数返回 `str`；颜色是可选的装饰，从不是结构上的
  必要条件。
- **没有调试器也能测。** GDB 适配层是针对一个假的 `gdb` 模块做集成测试的。

## 命名

GDB 命令是简短而稳定的那层接口：`kernlens-<verb>` 加一个 `kl-<verb>` 别名。
Python API 用一套可读、中等长度的风格 —— `snake_case` 函数、`PascalCase`
类，不用晦涩的 C 库缩写，也不用过长的项目专用名。完整规则与缩写表在
[`naming.md`](naming.md)。

## 仓库布局

```
.
├── .github/workflows/
│   ├── ci.yml            # 测试、类型检查、生成器、wheel 校验
│   ├── docs.yml          # 严格构建站点并部署到 Pages
│   └── release.yml       # 版本 tag -> PyPI -> GitHub Release
├── src/kernlens/
│   ├── __init__.py       # 公开再导出与 __version__
│   ├── cli.py            # `kernlens` 控制台脚本：path/install/doctor
│   ├── doctor.py         # 宿主侧的加载路径检查
│   ├── gdbinit.py        # GDB 启动文件，作为包数据分发
│   ├── install.py        # 启动路径 + ~/.gdbinit 标记块
│   ├── core/
│   │   ├── constants.py  # 布局常量
│   │   ├── validation.py # 边界校验
│   │   ├── bitops.py     # BitOps / BITS
│   │   ├── codec.py      # IntCodec / ByteOrderCodec / LE / BE
│   │   ├── fmt.py        # IntFmt
│   │   ├── addr.py       # KAddr
│   │   └── paging.py     # KPageTable
│   ├── output/
│   │   ├── palette.py    # Palette（原始 ANSI）
│   │   ├── colors.py     # 语义化颜色角色
│   │   ├── levels.py     # LogLevel
│   │   ├── logger.py     # Logger
│   │   └── styler.py     # Styler
│   ├── commands/
│   │   ├── __init__.py   # 包导出与注册表访问器
│   │   ├── framework.py  # @Command 框架：argparse + 守卫 + 注册表
│   │   ├── formatting.py # 共用的输出/解析辅助
│   │   ├── help.py       # GROUP_ORDER + kl-help 概览/详情渲染
│   │   ├── overview.py   # kl-status
│   │   ├── kernel_base.py# kl-base（show/text/offset/idt/rebase）
│   │   ├── memory.py     # kl-slab（list/info/contains/details）/ kl-sym / kl-bt / ...
│   │   ├── metadata.py   # kl-kcmdline / kl-kversion / kl-kconfig / ...
│   │   ├── misc.py       # kl-cpu / kl-percpu / kl-msr / kl-color
│   │   ├── paging.py     # kl-addr / kl-pt / kl-walk / kl-p2v / ...
│   │   └── primitives.py # kl-bits / kl-int
│   ├── gdb/
│   │   ├── __init__.py   # 惰性组件导出
│   │   ├── _types.py     # Pyright 协议
│   │   ├── config.py     # DebugConfig
│   │   ├── styler.py     # KernelStyler
│   │   ├── reader.py     # MemoryReader
│   │   ├── symbols.py    # SymbolResolver
│   │   ├── kaslr.py      # Kaslr
│   │   ├── kbase.py      # Kbase / 基于 IDT 的 text 基址恢复
│   │   ├── cpu.py        # CpuInfo
│   │   ├── walker.py     # PageTableWalker / PageWalk / WalkLevel
│   │   ├── btf.py        # 自带 BTF 类型解析器（不依赖 libbpf）
│   │   ├── layouts.py    # 已验证的兜底 struct 布局
│   │   ├── kernel.py     # KernelInspector（inspectors/ 的薄组合层）
│   │   ├── inspectors/   # 每个内核子系统一个模块
│   │   │   ├── _base.py      # InspectorBase + 共用读取原语
│   │   │   ├── metadata.py   # version / cmdline / CONFIG_*
│   │   │   ├── modules.py    # 模块列表 + sys_call_table
│   │   │   ├── structpage.py # x86_64 struct page
│   │   │   ├── kallsyms.py   # 内嵌符号表
│   │   │   ├── dmesg.py      # printk_ringbuffer
│   │   │   ├── bpf.py        # prog_idr / map_idr
│   │   │   ├── buddy.py      # buddy 空闲链表 / zone 元数据
│   │   │   ├── slabcache.py  # SLUB 缓存列表 / 对象查找
│   │   │   └── dmabuf.py     # dma-buf 与 scatterlist
│   │   ├── slub.py       # SlubInspector
│   │   ├── api.py        # 供 source 的脚本使用的公开 API 引导
│   │   └── facade.py     # KernelDebugger / kdbg + _BINDINGS 表
│   └── py.typed          # PEP 561 标记
├── tests/
│   ├── contract_spec.py  # 冻结的外部契约常量
│   ├── unit/             # 纯 Python 测试
│   └── integration/      # 适配层、gdbinit 与可在宿主运行的示例
├── docs/
│   ├── en/               # 默认语言；构建到站点根
│   │   ├── architecture.md   # 布局、API 映射与设计说明
│   │   ├── compatibility.md  # 实测 / 预期 / 不支持
│   │   ├── releasing.md      # 打 tag 前必须一致的东西
│   │   ├── index.md          # 由 README.md 生成（首页）
│   │   ├── api.md            # Python API 参考
│   │   ├── commands.md       # 生成的命令/别名表
│   │   ├── naming.md         # 命令、示例与 Python 命名规则
│   │   └── tutorial/         # 每个命令一页，生成（30 页）
│   ├── zh-CN/            # 中文页面，路径相同，独立目录
│   │   ├── index.md      # 由 README.zh-CN.md 生成
│   │   ├── api.md        # 同一份 API 参考的中文版
│   │   └── tutorial/     # 索引已翻译；页面本身没有
│   ├── assets/           # 生成的 demo.svg + demo.cast、extra.css，加上
│   │                     #   手写的 social-card.svg 及其渲染的 PNG，
│   │                     #   以及 images/banner.svg 的副本（见下）
│   └── llms.txt          # 生成的站点纯文本索引
├── overrides/            # mkdocs 主题覆盖：语言切换器
├── hooks/
│   └── language.py       # 逐页 <html lang>，以及首页标题
├── demo/
│   ├── Dockerfile        # 先构建内核，再构建运行时镜像
│   ├── entrypoint.sh     # 启动 QEMU、等待用户态、附着 GDB
│   ├── demo.gdb          # 加载镜像、连接、source gdbinit.py
│   ├── demo-commands.gdb # 不含地址的那趟演示
│   ├── kernel/
│   │   ├── config.fragment  # 在 defconfig 上加的命令会读的选项
│   │   └── init.c           # 全部用户态：挂载与启动标记
│   └── README.md         # 怎么构建、怎么跑
├── bin/kernlens          # 检出式启动器；`bin/kl` 是同一个工具
├── install.sh            # 一条命令的检出式安装
├── gdbinit.py            # 检出 shim -> src/kernlens/gdbinit.py
├── examples/
│   ├── api/                          # 脚本化使用 API
│   │   ├── README.md                 # 每个示例是干什么的
│   │   ├── hello_sample.py           # `_sample`  能跑起来的最小例子
│   │   ├── installed_api_tour.py     # `_tour`    gdbinit.py 装进命名空间的名字
│   │   ├── kernel_facts_tour.py      # `_tour`    `kfacts`  -- 目标内核
│   │   ├── address_tour.py           # `_tour`    `atour`   -- 九种视角
│   │   ├── slab_tour.py              # `_tour`    `stour`   -- 从缓存往下
│   │   ├── symbols_tour.py           # `_tour`    `ytour`   -- 解析与读取
│   │   ├── intcodec_tour.py          # `_tour`    `icodec`  -- 每种位宽
│   │   ├── intfmt_tour.py            # `_tour`    `ifmt`    -- 按类型格式化
│   │   ├── bitops_tour.py            # `_tour`    `btour`   -- 位域
│   │   ├── bits_tour.py              # `_tour`    `bittour` -- kl-bits
│   │   ├── int_tour.py               # `_tour`    `inttour` -- kl-int
│   │   ├── freelist_walk.py          # `_walk`    `flwalk`  -- SLUB 链
│   │   ├── slab_snapshot.py          # `_snapshot` 报告，不需要目标
│   │   └── gdbinit.example           # ~/.gdbinit 示例（不是脚本）
│   ├── tracing/                      # 记录日志后继续的断点
│   │   ├── README.md
│   │   ├── gdb_tracer.py             # `_tracer`  通用，靠环境变量配置
│   │   ├── cve_2025_38616_tracer.py  # `_tracer`  某 CVE 的 UAF 链
│   │   └── kaslr_retarget_tour.py    # `_tour`    `retarget` -- 修正基址
│   └── breakpoints/                  # 目的就是停下来的断点
│       ├── README.md
│       ├── conditional_bp.py         # `_bp`      `kbp-object`
│       ├── watchfield_bp.py          # `_bp`      `kwatch-field`
│       └── per_cpu_bp.py             # `_bp`      `pbreak`
├── images/banner.svg
├── mkdocs.yml            # 文档站点，由 CI 构建并部署
├── .dockerignore         # 演示镜像的构建上下文
├── CITATION.cff          # 如何引用本项目；版本与日期
├── pyproject.toml
├── tools/                            # 生成器与示例契约
│   ├── example_manifest.py           # 每个示例必须覆盖什么
│   ├── check_examples.py             # 静态检查；CI 里跑 --check
│   ├── run_examples_gdb.py           # 重放只能在 GDB 里跑的示例
│   ├── check_example_capture.py      # 把那份记录与仓库树对账
│   ├── gen_examples_readme.py        # 渲染 README 的覆盖表
│   ├── gen_tutorial.py               # 由捕获渲染 docs/en/tutorial/
│   ├── gen_tutorial_index.py         # 渲染每种语言的教程索引
│   ├── gen_commands.py               # 按语言渲染命令表
│   ├── gen_demo.py                   # 渲染 docs/assets/demo.*
│   ├── gen_docs_site.py              # 渲染两个首页 + llms.txt
│   ├── check_wheel.py                # wheel 里确实有启动文件
│   ├── release.py                    # 版本闸门与发布说明
│   ├── gen_layouts.py                # 用 BTF 校验 struct 布局
│   └── abi_ranges.py                 # 跨版本的结构漂移调查
├── uv.lock
├── CONTRIBUTING.md       # 环境、测试、布局生成器
├── CONTRIBUTING.zh-CN.md
├── CREDITS.md            # 第三方署名
└── CHANGELOG.md
```

## 公开 API 映射

包根是一个便利层，不是兼容层：它再导出纯 Python 内核与输出层的名字。GDB 适配
层是选择性使用的，并且只走规范子模块导入。不存在历史上的模块别名。

| 导入 | 主要公开名字 | 需要 GDB |
|--------|-------------------|-----------|
| `from kernlens import ...` | `BitOps`、`IntCodec`、`IntFmt`、`KAddr`、`KPageTable`、`Logger`、`Palette`、`Styler`、常量 | 否 |
| `from kernlens.core import ...` | 同样的内核名字，位于各自的规范层 | 否 |
| `from kernlens.output import ...` | `Logger`、`LogLevel`、`Palette`、`Styler`、`colors` | 否 |
| `from kernlens.commands import ...` | `Command`、`CommandCategory`、`registry`、`register_all`、`GROUP_ORDER` | 是 |
| `from kernlens.gdb import ...` | 惰性组件导出，如 `DebugConfig`、`MemoryReader`、`KernelDebugger` | 解析到 gdb 支撑的名字时 |
| `from kernlens.gdb.api import ...` | `install_public_api`、`core_functions`、`FACADE_FUNCTIONS`、`kdbg` | 是 |
| `from kernlens.gdb.facade import kdbg` | `KernelDebugger` 组合，以及 `kdbg` 单例 | 是 |

```python
from kernlens import BitOps, IntCodec, IntFmt, KAddr, KPageTable

# 在 GDB 的 Python 会话里：
from kernlens.gdb.facade import kdbg
```

内核层与输出层从不导入 `gdb`；`output` 也不导入 `core`。这由
`tests/unit/test_structure.py` 强制执行。

## 依赖图

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
   └── commands.help ── commands.framework（注册表由外部传入）
```

没有循环导入。`core.codec` 不依赖任何东西；`core.bitops` 与 `core.fmt` 导入
它；`output` 独立于 `core`；`gdb` 的组件只导入 `core.*`、`output` 以及同级
模块，而 `gdb.facade` 把它们组合起来。`commands.framework` 拥有 `@Command`
装饰器、`CommandDefinition` 记录、`OnlyWhen*` 守卫以及注册表；各领域模块导入
它（以及 `commands.formatting`），但从不导入 `commands.help` —— `help.py`
通过 `framework.registry()` 读注册表，而不是导入命令模块。

## 各模块职责

### `core.constants` / `core.validation`

- 页与指针常量：`PAGE_SHIFT`、`PAGE_SIZE`、`PAGE_MASK`、`PTR_BITS`、
  `PTR_HEX_DIGITS`、`PTR_MASK`。
- x86-64 地址空间边界：`KERNEL_BASE`、`KERNEL_BOTTOM`、`PAGE_OFFSET_BASE`、
  `VMEMAP_BASE`、`VMALLOC_START/END`、`MODULE_START/END`、`USER_TOP`、
  `MAX_ERRNO`。
- 校验辅助：`check_bits`、`check_pow2`、`check_nonneg`。

这两个模块是纯数据与校验；公开常量由 `kernlens/__init__.py` 再导出。

### `core.bitops`

一个无状态的整数位运算命名空间。运算前先把输入掩到要求的位宽；带显式位宽的
方法会先校验它。按族分组：

- 字节交换（`byte_swap`、`byte_swap16/32/64`）；
- 位宽重解释（`sign_extend`、`truncate`、`to_u*`、`to_i*`、`coerce`）；
- 位宽元数据（`mask`、`sign_bit`、各种范围）；
- 计数与扫描（`popcount`、`leading_zeros`、`trailing_zeros`、`first_set`、
  `last_set`）；
- 2 的幂与对数；
- 旋转；
- 对齐；
- 单个位与位域；
- `cpumask` 字操作。

`BITS` 是习惯用的短别名。

### `core.codec`

基于 `struct` 的、考虑字节序的整数 <-> 字节转换。静态方法带一个末尾的
`byteorder` 关键字。`ByteOrder` 是 `"<"` / `">"` 的枚举；`IntType` 描述八种
整数类型（4 种位宽 × 2 种符号性），并暴露 `code`、`width`、`bits`、`signed`、
`mask`、`min_value` 与 `max_value`。

`ByteOrderCodec` 把某一种字节序绑到静态方法上（`LE.pack_u16(...)`）。
`byteorder` 参数既接受 `ByteOrder` 成员，也接受绑好的编解码器，所以
`IntFmt.bytes_u16_array(data, byteorder=LE)` 与
`IntCodec.pack_u16(value, BE)` 都能用。

范围与缓冲区大小的校验交给 `struct`；负的数组长度会被显式拒绝。

### `core.fmt`

在 `IntCodec` 之上的整数与字节串格式化。它返回纯字符串，不依赖颜色或日志。
覆盖地址、带位宽的十六进制、偏移、人类可读的大小、`ERR_PTR` 风格的标志、
百分比、时间戳、时长、字节的 hex/ASCII/C 字符串视图、hexdump，以及带类型的
数组格式化。

### `core.addr`

x86-64 地址分类与直接映射转换：

- 用户/内核与规范地址检查（48 位与 57 位）；
- 直接映射、vmemmap、vmalloc、module 与 text 范围；
- 虚拟 <-> 物理，以及 pfn <-> page 转换；
- 页对齐；
- KASLR 链接时/运行时转换；
- `ERR_PTR` 编解码；
- 指针标签提取。

所有输入都掩到 64 位。布局常量假定一个比较新的 x86-64 Linux，直接映射
64 TiB、物理地址 52 位；内核配置不同时，调用方可以显式传入基址/大小。

### `core.paging`

纯页表几何与 PTE 解码。它从不读内存。支持 4 级与 5 级页表、索引提取、
把虚拟地址拆成各级索引加偏移、规范化、表项地址计算、PTE 标志位解码、
大页对齐/基址辅助，以及 4 KiB、2 MiB、1 GiB 叶子的物理地址重建。

### `gdb.walker.PageTableWalker`

`KPageTable` 是纯算术，所以它无法翻译一个活动地址。`PageTableWalker` 在不把
内存访问搬进内核层的前提下补上了这个缺口：它通过 `MemoryReader` 读 8 字节
表项，从 `$cr3` 开始（取不到时退回 `init_top_pgt` / `swapper_pg_dir`），并
按 `CR4.LA57` 选择 4 级或 5 级几何。

`walk(va, *, five_level=None, root=None)` 接受显式根与分页模式，以便重放捕获
下来的页表，并返回一个冻结的 `PageWalk`，其中每个解码层级对应一个
`WalkLevel`，另有最终物理地址、叶子大小（4 KiB / 2 MiB / 1 GiB），以及在遍历
提前结束时给出 `note`。读不出来、表项不存在、present 位为 0 这三种情况都不
抛异常，因为遍历器要能在断点回调里使用。`kernlens-walk` 命令是它的 GDB
前端（逐层细节），`kernlens-pagewalk` 则模仿 pwndbg 的最深一层优先的呈现方式，
并支持 `--pgd` 覆盖根。

### `output.Logger` / `output.Styler`

`Logger` 是一个带严重级别的小型写入器，支持级别过滤、前缀控制、流注入，
以及 `once` / `throttle` / `counter` 状态、校验、横幅与分隔线。`Styler` 负责
所有呈现相关工作：颜色、对齐、键值对、容器、表格、方框、分栏、块、高亮与
进度条。

`Styler` 从不要求颜色。当 `color_enabled=False` 时，每个方法返回的纯文本与
彩色路径用 SGR 序列包住的那份完全相同。布局方法共用 `fill`、`aligns` 与
`max_col_width`；画框默认用 Unicode，但接受自定义字符与接点。

`output.colors` 把**语义**映射到原始 ANSI 序列（字段标签永远是 `LABEL`，
三态标志是 `TRUE` / `FALSE` / `MISSING`，等等）。命令层的格式化辅助读这些
角色，所以换一套配色只改一个文件，而不是每个命令模块。

### `gdb/` 组件

GDB 适配层按职责拆分。只有确实接触被调试进程的模块导入 `gdb`；`config.py`
与 `styler.py` 保持与调试器无关：

| 模块 | 职责 |
|--------|----------------|
| `config.py` | KASLR 偏移、表头宽度、缩进、freelist 扫描上限 |
| `styler.py` | 基于 `Styler` 的内核专用符号/位置/SLUB 格式化 |
| `reader.py` | 安全的表达式/内存读取，带自愈的 KASLR 翻译 |
| `symbols.py` | pc -> 符号、`file:line`、栈回溯、调用链 |
| `kaslr.py` | 断点规格与链接时 `_text` |
| `kbase.py` | IDT 门描述符解码与运行时内核 text 基址恢复 |
| `cpu.py` | CPU 数、online 掩码、当前 CPU、per-CPU 偏移 |
| `walker.py` | 基于 `CR3` 的遍历、4/5 级选择、大页叶子 |
| `btf.py` | 自带 BTF 解析器（镜像里的 `.BTF`，或 `btf_path`）；不需要 `libbpf`/`bpftool` |
| `layouts.py` | 已验证的兜底 struct 布局，仅在既没有 DWARF **也**没有 BTF 时使用 |
| `inspectors/` | 每个内核子系统一个 mixin（见下文）；各自拥有自己的常量、数据类与方法 |
| `kernel.py` | `KernelInspector`，把 `inspectors/` 的 mixin 组合到一个对象后面的薄壳 |
| `slub.py` | `struct page`/`struct slab` 解码、freelist、partial 链表、slab 块打印 |
| `facade.py` | `KernelDebugger` 组合、`_BINDINGS` 表，以及 `kdbg` 单例 |

`KernelDebugger` 为每个组件各持一个实例，并把常用的方法直接再发布到门面上。
这次再发布由一张 `_BINDINGS` 表驱动（140 行 `(public_name, component, member,
free_function)`）；`api.FACADE_FUNCTIONS` 与 `api.INSTANCE_NAMES` 由它派生，
所以公开面只声明一次。每一行都绑定为
`self.<name>: Final = self.<component>.<member>`，这样既保留了组件方法真实的
签名（包括参数名与默认值），又给 `pyright --verifytypes` 一个声明类型而不是
一个推断；如果新增绑定却没写 `Final` 注解，`tests/unit/test_structure.py`
会失败。组件访问器（`kdbg.logger`、`kdbg.styler`、`kdbg.reader`、
`kdbg.symbols`、`kdbg.kaslr`、`kdbg.kbase`、`kdbg.cpu`、`kdbg.walker`、
`kdbg.kernel`、`kdbg.slub`）仍然可用。

`KernelDebugger.indent` 绑定的是 `Styler.indent` 这个文本格式化函数；配置里的
前缀另外以 `indent_str` 暴露，避免门面上重名。

### `gdb/inspectors/`

`KernelInspector` 曾经是一个 1.6k 行的类。现在它按内核子系统拆开了：每个
`InspectorBase` 子类都是一个 mixin，拥有自己领域的常量、数据类与方法，再由
`KernelInspector` 组合到同一个 API 后面。

| 模块 | 子系统 |
|--------|-----------|
| `_base.py` | `InspectorBase`（读取器 + 字节/字读取、`_cstring`、`_walk_list`、`vmemmap_base` / `page_offset_base`）与 `_ByteReader`；还有三层 struct 偏移解析器 |
| `metadata.py` | `linux_banner`、`saved_command_line`、`IKCFG` 里的 `CONFIG_*` 镜像 |
| `modules.py` | `struct module` 链表与 `sys_call_table` |
| `structpage.py` | x86_64 `struct page` 的 type/refcount 打包 |
| `kallsyms.py` | 内嵌的 `kallsyms` 表（token 展开 + 地址） |
| `dmesg.py` | `printk_ringbuffer`（`printk_rb_static`）与 `tk_core` |
| `bpf.py` | BPF 的 `prog_idr` / `map_idr`（xarray 遍历） |
| `buddy.py` | `node_data[].node_zones[].free_area[]` 与 zone/node 元数据 |
| `slabcache.py` | 全局 `slab_caches` 链表与对象 -> 缓存查找 |
| `dmabuf.py` | dma-buf 链表（`debugfs_list` / `db_list`）与 scatterlist |

每个 mixin 都声明 `__slots__ = ()`；缓存槽只存在于 `InspectorBase` 上，那是
它们共同的唯一基类（两个各自带非空 slots 的兄弟基类会引发 "instance lay-out
conflict"）。`tests/unit/test_structure.py` 强制检查包的形状，以及 inspectors
永不导入 `kernel`、`facade` 或 `api`。

#### struct 偏移解析

任何东西都不得硬编码结构体字段偏移，因为布局取决于内核版本与 `CONFIG_*`
（例如 `CONFIG_SECURITY` 会在 `struct bpf_map::map_type` 之前插入
`void *security`，把它从 `0x10` 移到 `0x18`）。inspectors 调用
`InspectorBase._layout_offset(type, path)` / `_layout_sizeof(type)`，它们通过
三层链条解析并缓存结果：

1. **DWARF** —— 对已加载的 `vmlinux` 做 `gdb.parse_and_eval`；
2. **BTF** —— `gdb/btf.py` 解析镜像里的 `.BTF` 段（或
   `reader.config.btf_path`）；BTF 是真实的类型信息，所以这里命中**不算**
   兜底，也不告警；
3. **注册表** —— `gdb/layouts.py`，其中 `StructVariant` 条目由
   `version_min`/`version_max` 与 `CONFIG_*` 谓词把关。

解析器把注册表里的值当作 `_offset_of` / `_sizeof` 的 `default` 参数传入；基类
在第一次用到默认值时把该键记进 `_fallbacks`，当这个集合非空时，
`CommandDefinition.invoke` 会针对每个 struct 类型打印一条 `message.warn`
（通过 `framework.warn_fallback_layouts`）。`reset()` 会清空偏移缓存、兜底
记录以及缓存的 BTF 句柄。

只查**已加载**镜像的 BTF —— 从不查宿主机的 —— 所以跨内核会话不会悄悄借用
错误的布局。`tools/gen_layouts.py` 会对着真实内核重新生成并校验注册表，
`tools/abi_ranges.py` 读本地的 `linux-stable` 克隆，报告哪些发布区间需要自己
一行（成员列表是变化的上界 —— 它说的是该往哪里探，而不是值是多少）。

### `commands/`

GDB 命令遵循 pwndbg 的约定。一个命令就是一个名为 `kernlens_<verb>` 的普通
函数，用 `@Command(parser, category=..., aliases=[...], examples=...,
notes=...)` 装饰，并（可选地）再加一个守卫：

```python
_parser = argparse.ArgumentParser(description="Displays the loaded modules.")
_parser.add_argument("module_name", nargs="?", default=None)

@Command(_parser, category=CommandCategory.KERNEL_METADATA, aliases=["kl-kmod"])
@OnlyWithKernelSymbols
def kernlens_kmod(module_name: str | None = None) -> None:
    ...
```

框架（`commands/framework.py`）复刻了 pwndbg 的语义：

- 装饰器记录一条 `CommandDefinition`（函数、parser、分类、别名、示例、
  说明），并从函数名推出命令名，所以注册表无需手工维护清单就能填满；
- `-h`/`--help` 打印 parser，其 epilog 携带示例、说明与别名列表；
- 失败的守卫打印 `message.error(...)` 并返回而不抛异常；函数体里抛出的任何
  `gdb.GdbError` 都被当作 `message.error` 报告并吞掉 —— 一个命令永不会让
  会话中断；
- `register_all()` 为每条定义实例化一个 `gdb.Command` 子类（每个 `kl-` 别名
  再加一个），并且是幂等的，所以 source 两次 `gdbinit.py` 也安全。

输出使用 pwndbg 的 `print` 惯例，配合共用的 `output.message`
（`error`/`warn`/`hint`/`notice`/`success`/`info`/`on`/`off`）与
`output.tree.IndentContextManager` 辅助。`commands/help.py` 由分类渲染分组的
`kl-help` 概览，由 parser 渲染单个命令的详情；它通过框架读注册表，所以从不
导入领域模块。

`src/kernlens/gdbinit.py` 只是一个引导：它的 `bootstrap(namespace)` 导入包、
调用 `register_all()`，并安装公开的 Python API。仓库根目录的 `gdbinit.py` 是
一个 shim，把 GDB source 时拿到的命名空间交给它。

## 在 GDB 内加载

普通的包导入：

```python
import sys
sys.path.insert(0, "/path/to/repo/src")
from kernlens.gdb.facade import kdbg
```

导入 `kernlens.gdb` 本身在 GDB 之外是安全的；它的公开名字是按需从各自的模块
惰性解析的。解析一个会导入 `gdb` 的组件（`reader`、`symbols`、`kaslr`、
`kbase`、`cpu`、`walker`、`slub`、`facade`）需要调试器会话；`config` 与
`styler` 不需要。

`gdbinit.py` 是一个薄引导：它导入 `kernlens.commands`（由此注册
`kernlens-*` 命令与它们的 `kl-*` 别名），然后调用 `register_all()`。完整的
命令表、别名与调用示例在
[项目 README](https://github.com/BinRacer/KernLens/blob/main/README.zh-CN.md)
与生成的[命令参考](commands.md)里；`kl-help` 按分类分组列出它们，
`kl-help kl-<command>`（或 `kl-help kernlens-<command>`）显示单个命令的详情。

启动文件是包数据，所以 `source $(kernlens path)` 在 wheel 里与在检出里一样
可用：它先把 `kernlens/` 目录的父目录（`src/` 或 `site-packages`）加进
`sys.path` 再导入，因为 GDB 内嵌的 Python 通常两个都看不到。仓库根目录的
`gdbinit.py` 是检出 shim：它加上 `src/`，并用自身的全局变量调用打包的
`bootstrap()`。

它还会用自己的全局变量调用 `kernlens.gdb.api.install_public_api()`。GDB 把
Python 文件 source 进 `__main__`，所以之后 `source anything.py` 可以不写导入
就用 `KAddr`、`KPageTable`、`IntFmt`、`kdbg`、`read_kvar`、`walk`、`sym`、
`head_to_page`、`print_slab`、`find_kbase`，以及 `FACADE_FUNCTIONS` 里的其他
名字。无状态的内核方法也作为自由函数导出（`byte_swap64`、`popcount`、
`pack_u16`、`virt_to_phys`、`split_4` 等），来自 `BitOps`、`IntCodec`、
`KAddr`、`KPageTable` 与 `IntFmt`；`core_functions()` 返回那份映射。
偏好不冲突名字时，可以用带类限定的访问（`BitOps.byte_swap64`）、合法标识符
别名（`BitOps_byte_swap64`），以及 `KERNLENS_QUALIFIED` 里的点号键。有状态的
组件（`logger`、`styler`、`config`、`reader`、`symbols`、`kaslr`、`kbase`、
`cpu`、`walker`、`slub`）以 `kdbg` 拥有的默认实例安装；`KERNLENS_INSTANCES`
把二者对应起来，`KERNLENS_CLASSES` 则支持构造独立实例。构造函数会分配全新
状态（例如新的 `Logger` 有自己的计数器与最低级别）；修改本地实例永不改变全局
默认值。`KERNLENS_API` 记录安装好的映射。这是仅限 GDB 的引导；普通宿主代码
应当显式从 `kernlens` 或 `kernlens.gdb` 导入。

## SLUB 检查模型

`SlubInspector` 针对当代 SLUB 布局：

1. **对象 -> page。** 对直接映射里的对象地址，减去 `page_offset_base`，再按
   `PAGE_SHIFT` 右移得到 pfn，然后把 `pfn * sizeof(struct page)` 加到
   `vmemmap_base`。
2. **尾页 -> 头页。** `compound_head` 最低位为 1 的 `struct page` 是尾页；
   清掉低位即可恢复头页。
3. **缓存。** `struct slab.slab_cache` 指向 `kmem_cache`；缓存名按 C 字符串
   读取。
4. **计数器。** `struct slab.counters` 打包了 `inuse:16`、`objects:15` 与
   `frozen:1`。
5. **freelist。** `kmem_cache.offset` 是 freeptr 槽。值为 `0` 是合法的：对
   普通缓存，SLUB 把指针存在对象开头。开启
   `CONFIG_SLAB_FREELIST_HARDENED` 时，存下来的字是
   `ptr ^ random ^ swab(ptr_addr)`；`decode_freeptr` 做逆运算。
   `freelist_dist` 带扫描上限与环检测地走完这条链。
6. **partial 链表。** `kmem_cache.node[node].partial` 是一个 `list_head`；
   减去 `slab_list` 偏移即可还原 slab。`in_partial` 带边界与环保护地扫描。

Per-CPU slab 通过 `kmem_cache.cpu_slab` 加 `__per_cpu_offset[cpu]` 读取。
`print_slab` 打印头页、各 CPU 的 freelist、node 的 partial 链表，以及头页
slab 的 freelist 链。

代码假定内核有 `struct slab`（5.17+）以及通常的 `page_offset_base` /
`vmemmap_base` 符号。SLUB 布局不同的内核需要一个小适配层，而不是改动通用
内核层。

## 错误处理与限制

- 公开的纯 Python 辅助函数对非法位宽、对齐、计数、偏移与范围抛
  `ValueError`。
- `IntCodec` 让 `struct.error` 在溢出与缓冲区过短时向上传播。
- 面向 GDB 的读取器在读失败时返回 `None`；由调用方决定那是否致命。
- 页表遍历按分页级数（4 或 5）限制，遇到读不出或缺失的表项时返回 `note`
  而不是抛异常。
- freelist 遍历由 `DebugConfig.freelist_scan_limit` 限制（默认 4096），并
  检测环。partial 链表扫描上限 10000 个链接，在链表头或重复链接处停止。
- KASLR 是自愈的。`MemoryReader` 对需要 KASLR 的读取应用
  `DebugConfig.kaslr_offset`，当偏移未设置（或按它读取失败）时，向门面的
  基于 IDT 的检测器询问当前偏移并重试。链接时读取放在最后尝试，所以一个
  已经带着重定位的调试器（`add-symbol-file vmlinux <runtime>`）仍然可用。
  每当偏移变化，读取器就触发 `on_change` 钩子，丢弃 `KernelInspector` 中由
  地址推导出的缓存 —— 这正是每个移植过来的命令都能跟随 KASLR 变化、无需
  手工执行 `kl-base` 的原因。`kl-base` 仍是用户侧显式固定偏移的方式：
  它的 `offset` 与 `text` 子命令就是手工覆盖。

## 测试策略

- **单元测试**覆盖每个纯 Python 模块，包括校验错误与边界值。
- **集成测试**在导入 `kernlens.gdb.facade` 之前装上假的 `gdb` 模块。这个假
  模块实现 `parse_and_eval`、`execute`、`find_pc_line`、`newest_frame` 与
  `error`，并提供确定性的内存/符号模型。
  `tests/integration/test_gdb_facade.py` 在没有活动内核的情况下覆盖
  `MemoryReader`、`SymbolResolver`、`Kaslr`、`CpuInfo`、`SlubInspector`、
  `PageTableWalker` 与门面，包括在合成页表上完整走完 4 级与 5 级。
- `tests/integration/test_gdbinit.py` 用记录式的假 `gdb` 与桩门面执行真实的
  检出 shim（`gdbinit.py`），覆盖命令注册、别名、参数校验与输出格式。
  `tests/unit/test_cli.py` 覆盖宿主侧控制台脚本，`tools/check_wheel.py` 检查
  构建出的 wheel。
- `tests/contract_spec.py` 冻结可观察的外部契约（规范命令集、门面绑定的名字、
  安装的自由函数，以及组件实例）。`tests/unit/test_contract.py` 检查这些常量
  自洽，两个集成测试套件都断言活动注册表、别名、门面与公开 API 与冻结集合
  一致 —— 这样内部包布局可以重构，而不会悄悄改变公开面。
- **示例**刻意保持很小，可以作为冒烟测试运行（在检出里执行
  `uv run python examples/api/slab_snapshot.py`）。

开发用 uv 管理。`uv sync` 依据提交的 `uv.lock` 安装项目与 `dev` 依赖组；在
那个环境里用任一种运行器跑测试：

```bash
uv sync
uv run pytest --cov=kernlens
uv run python -m unittest discover -s tests/unit
uv run python -m unittest discover -s tests/integration
```

## 运行要求

- Python 3.10+。
- x86-64 的 Linux 内核目标。
- 带 Python 3.10+ 的 GDB（适配层只用标准的 GDB Python API；不需要任何调试器
  专用扩展）。
- 终端支持 UTF-8（默认的画框字符与进度字符）；纯 ASCII 终端可以用自定义的
  `chars` / `joints`。
- `typing_extensions` 只在 Python < 3.12 时需要（为了 `typing.override`）。