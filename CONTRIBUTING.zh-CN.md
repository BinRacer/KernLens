# 参与开发

KernLens 的开发说明。只想*使用*它的话，[README](README.zh-CN.md) 里有
一条命令的安装方式和命令表，这里的内容一条都用不上。

## 分发方式

KernLens 从同一棵树以两种方式分发。`install.sh` 克隆 checkout，往
`~/.gdbinit` 写一个带标记的块，并留下 `kernlens` 包装脚本；
`pip install .` 构建的 wheel 里带有同一个启动文件。目前还没有 PyPI
发布，在发布存在之前，文档不得提供 PyPI 安装命令。

启动文件是约束设计的那一部分。GDB 是 **source** 它而不是 import 它，
所以它必须在 GDB 的 `__main__` 命名空间里运行，并能让 `kernlens` 从
自己的位置被 import：checkout 里是 `src/`，wheel 里是 `site-packages`。
`src/kernlens/gdbinit.py` 同时处理两种情况；根目录的 `gdbinit.py` 是
兼容旧 `~/.gdbinit` 行的 shim。

控制台脚本只运行在宿主侧，而控制台脚本本身有两个名字：`kernlens` 与
短别名 `kl`，与每条 GDB 命令的长短拼写一一对应。`kernlens path` 打印
启动文件，`kernlens install` 编辑 `~/.gdbinit`，`kernlens doctor` 检查
加载路径，`kernlens version` 打印版本。它们都不 import `kernlens.gdb`，
因为宿主解释器里没有 `gdb` 模块。

动手改这两条路径之前，先知道一处不对称：`install.sh` 只写 `kernlens`
包装脚本，所以从 checkout 安装时 `PATH` 上没有 `kl`。`kl` 这个名字只来自
wheel 的 `[project.scripts]` 条目，也就是说这个别名只对 `pip install`
的用户存在。这不属于可以随手"顺手修掉"的笔误：shell 安装器写的是一个
静态文件、读不到 `pyproject.toml`，在那里补第二个名字意味着把 entry
point 的目标在 shell 里再抄一遍——而这正是 `tests/unit/test_install.py`
已经为标记行防住的那类漂移。

发布是 release 步骤，不是代码步骤。顺序、检查项与一次性的 trusted
publishing 配置见 [`docs/en/releasing.md`](docs/en/releasing.md)。
`tools/check_wheel.py` 是"构建出的 wheel 真的含有启动文件和控制台脚本"的
闸门；在 CI 用它检查真实构建之前，测试全绿并不能说明包是好的。

## 测试与开发

测试同时兼容 `unittest` 与 pytest。开发命令统一通过 uv 执行：

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
uv run pyright
uv run mypy
uv run python tools/gen_commands.py --check
uv run python tools/gen_demo.py --check
uv run python tools/gen_docs_site.py --check
uv run python tools/gen_tutorial.py --capture tools/tutorial_capture.json \
    --meta tools/tutorial_meta.json --out docs/en/tutorial --check
uv run python tools/gen_tutorial_index.py \
    --capture tools/tutorial_capture.json --meta tools/tutorial_meta.json \
    --out docs/zh-CN/tutorial --locale zh-CN --check
uv run python tools/check_examples.py --check
uv run python tools/gen_examples_readme.py --check
uv run python tools/check_example_capture.py
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux \
    --coverage --version "$(uname -r | cut -d- -f1)"
```

`pyright` 与 `mypy` 都是闸门：包内是空的 `py.typed`，而两个检查器
经常互相发现对方接受的注解问题。它们读取的都是 `types-gdb` 开发依赖
提供的 `gdb` stub，因此运行时不需调试器。

仍可在 uv 环境中使用 stdlib runner，但它需要和 `tests/conftest.py` 为
pytest 注入的那批路径一致——pytest 的 `pythonpath` 设置只在 pytest 内
生效，所以辅助模块 `contract_spec`、`example_manifest`、`abi_ranges`
以及 mkdocs hook 单独跑时都不可导入：

```console
PYTHONPATH=tests:tools:hooks uv run python -m unittest discover -s tests/unit
PYTHONPATH=tests:tools:hooks uv run python -m unittest discover -s tests/integration
```

不加这个前缀时，十个单元测试模块（`contract_spec`、`example_manifest`、
`abi_ranges` 等）和四个集成测试都会导入失败，裸 `discover` 会报出与
代码无关的错误。

集成测试会注入 fake `gdb` 模块，不需要调试器或内核；
`tests/integration/test_gdbinit.py` 还用 fake `gdb` 与 stub facade
直接执行真实的 `gdbinit.py`，因此命令注册、参数解析和输出格式
也无需 GDB 即可覆盖。`uv sync` 以可编辑方式安装项目，因此 `uv run`
通过 wheel 的 `.pth` 文件就能找到 `src/kernlens`，不依赖 `PYTHONPATH`；
`pyproject.toml` 另外设置了 `pythonpath = ["src"]`，裸 `pytest`
也能直接在 checkout 中运行。

公共 API 地图、模块职责、SLUB 检查模型与 gdb 加载方式见
[`docs/en/architecture.md`](docs/en/architecture.md)；命令与 Python 命名
规范见 [`docs/en/naming.md`](docs/en/naming.md)。想按命令逐个上手、并看到
真实内核的输出，从 [`docs/en/tutorial/`](docs/en/tutorial/README.md) 开始
——每个命令一页。版本历史见 [`CHANGELOG.md`](CHANGELOG.md)。

### 文档站

文档站就是 checkout 里的同一批 Markdown，由 mkdocs 构建并部署到
GitHub Pages。主题单独放在一个依赖组里，`uv sync` 不会下载它：

```console
uv sync --group docs
uv run --group docs mkdocs serve      # http://127.0.0.1:8000/KernLens/
uv run --group docs mkdocs build --strict
```

`--strict` 就是 CI 用的闸门：内部链接坏掉、或有页面没进 nav，构建直接
失败。`docs/en/index.md` 与 `docs/zh-CN/index.md` 由两份 README 生成，
`docs/llms.txt` 由 `mkdocs.yml` 的 nav 生成——改源文件，然后运行
`uv run python tools/gen_docs_site.py`。新增页面必须同时有 nav 条目和
`PAGE_NOTES` 里的一行说明，否则 `--check` 会失败。

### 历史：笔者保持线性，对他人从宽

笔者直接向 `main` 提交，所以 `main` 天然是一条线。这是对一个人习惯的
描述，不是压在贡献者身上的规则。

外部贡献可以用 **squash**、**rebase** 或 **merge** 落地。没有冲突时，
三者产生的文件完全相同，测试覆盖也完全相同：`pull_request` 针对
`refs/pull/<n>/merge` 运行，也就是分支与 `main` 合并后的结果；随后
`push: main` 会针对真正落地的那个提交再跑一次。所以 merge 提交并不是
一个没被测过的提交，这只是日志形状的选择，与安全无关。

**Merge 是明确允许的**，因为另外两种方式把成本转嫁给了贡献者而不是
维护者。rebase 会让贡献者去解决并非由他造成的冲突，并对一个他可能无法
改写的 fork 分支强推；这种情况下，merge 的成本落在维护者身上，rebase
的成本落在一个陌生人身上。接受一个 merge 提交是两者中更便宜的那个，
而日志正是适合付出这点代价的地方。

```console
# 贡献者
git pull --rebase origin main       # 可选，让 PR 跟住 main
git push --force-with-lease         # 仅在你 rebase 过之后

# 维护者，处理一个贡献
gh pr merge <n> --merge --delete-branch
```

分支里有一串对叙事没有贡献的 fixup 提交时，squash 仍是默认——它是唯一
对贡献者零要求、也完全不会失败的选项。每个提交都能独立成立、且分支
已经跟上 `main` 时，用 rebase 保留它们。

merge 提交唯一的代价是：`git bisect` 可能落到一个有两个父提交的节点上，
而那里构建失败的原因可能两边都不归。真遇到时，`git bisect
--first-parent` 会跳过 merge 提交，按当初评审的那条线去做二分。

不可让步的不是图的形状，而是**每个提交的形状**：一个提交只做一件事、
提交信息说清为什么、不要在一个 merge 提交里夹带未经评审的内容。本小节
关于落地方式的全部内容都是偏好；这一条才是要求。

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
（`layouts.VERIFIED_KERNEL` 写明两个：6.1.134 测试虚机经 DWARF、
7.0.0-38 宿主机经 BTF），并按版本与 `CONFIG_*` 选择变体。由于一个值
只对它被测量时的那套配置成立，一旦用到兜底层，命令层会按结构体类型
各打印一次性告警。该告警**不带命令名前缀**——它由共享的命令层发出，
而不是由恰好触发它的那条命令：

```console
struct bpf_map, struct dma_buf: no debug info; using built-in fallback
layouts that may not match this kernel. Load a matching vmlinux for
exact struct offsets.
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
对另一个内核是**静默错误**的。这不是假设：`struct slab.slab_cache`
曾经只有一行、取自 7.0 内核，于是在所有版本上都报 `0x8`，而 5.17–6.1
实际是 `0x18`——修法正是现在那条按版本分段的记录，而不是改一个常数。
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
