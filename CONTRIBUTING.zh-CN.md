# 参与开发

KernLens 的开发说明。只想*使用*它的话，[README](README.zh-CN.md) 里有
三步快速开始和命令表，这里的内容一条都用不上。

## 分发方式

KernLens 以源码 checkout 的形式分发，不作为包发布。没有 PyPI 版本，
只要入口还是一个需要 source 的文件而不是一个可以 import 的模块，就不会有。

原因不是省事。每个快速开始路径的终点都是 `source /path/to/gdbinit.py`，
而 `gdbinit.py` 不在 wheel 里：wheel 由 `src/` 构建，启动文件与它平级。
现在发布只会得到一个装得干干净净、然后照着文档怎么都跑不起来的包 ——
那比不发布更糟。

要发布，得先把启动文件变成 package data 并加一个打印其路径的入口点，
那是一次带自己测试的真实改动，不是改个元数据。在那之前，升级路径是
`git pull`，`uv sync` 只用于开发。

## 测试与开发

测试同时兼容 `unittest` 与 pytest。开发命令统一通过 uv 执行：

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
uv run pyright
uv run mypy
```

`pyright` 与 `mypy` 都是闸门：包内是空的 `py.typed`，而两个检查器
经常互相发现对方接受的注解问题。它们读取的都是 `types-gdb` 开发依赖
提供的 `gdb` stub，因此运行时不需调试器。

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
规范见 [`docs/naming.md`](docs/naming.md)。想按命令逐个上手、并看到
真实内核的输出，从 [`docs/tutorial/`](docs/tutorial/README.md) 开始
——每个命令一页。版本历史见 [`CHANGELOG.md`](CHANGELOG.md)。

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
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux \
    --coverage --version "$(uname -r | cut -d- -f1)"         # CI 用法
```

`--check` 在发现任何偏差时以非零码退出，可用于 CI 中守护表的更新。
`--coverage` 是 CI 实际断言的较弱主张：它只要求探测**对应该版本**
注册表所声明存在的每个结构体都被解析到，不比对偏移。这个区别很关键，
因为结构体可能合法地消失——`struct kmem_cache_cpu` 在 7.0 被 sheaves
取代——所以无视版本的覆盖检查会把健康的探测误报为失败。不传
`--version` 时会退化为要求全部条目，这是内核版本无法识别时应有的严格读法。

`tools/abi_ranges.py` 负责决定**哪些内核版本需要单独一行**。
这些结构体跨版本发生过变化，所以「用某一个内核验证过的一行」
对另一个内核是**静默错误**的：注册表里的 `struct slab.slab_cache`
取自 7.0 内核，在所有版本上都报 `0x8`，而 5.17–6.1 实际是 `0x18`。
该工具读取本地 `linux-stable` 仓库，把每个版本的
结构体体按一组 `CONFIG_*` 求值成**扁平成员序**，
然后报告成员序不变的区间：

```console
uv run python tools/abi_ranges.py struct slab
uv run python tools/abi_ranges.py --with-layouts --since v5.15 struct kmem_cache
uv run python tools/abi_ranges.py --config-file /boot/config-$(uname -r)
```

它需要一份 `linux-stable` 检出（`--repo` 或 `$KERNLENS_LINUX_STABLE`），
且只做**侦察**而非**定值**：成员序只说明哪些版本发生了变化，
不说明新偏移是多少——具体数值仍要用 `gen_layouts.py` 从真实内核取得。
