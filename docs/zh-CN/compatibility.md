# 兼容性

哪些环境是 KernLens **真正跑过**的、哪些是**预期可用**的、哪些**不做承诺**。这个
区分正是本页存在的理由：一份与"预期"行相矛盾的 bug 报告是有价值的，而一行悄悄变成
承诺的记录不是。

## 四个词

| 词 | 含义 | 依据 |
| --- | --- | --- |
| **实测**（measured） | 有人在那套环境上跑过，结果就在本仓库里 | 一份捕获、一段录下的命令，或一条 CI 日志 |
| **测试中实测**（measured in tests） | 代码路径被覆盖，但用的是合成输入，不是那套环境 | `tests/` 里的一个测试 |
| **预期**（expected） | 路径上没有发行版相关的东西，所述要求也满足，但没人跑过 | 要求本身 |
| **不支持**（unsupported） | 超出承诺范围；它可能能跑，但结果不构成承诺 | 设计决定，或一段拒绝 |

"不支持"不是"我们还没做到"。对只解码 x86_64 而言，这是一条划定的边界；对没有
Python 的 GDB 而言，这是物理事实。

## 两个解释器，不是一个

最常见的首次运行失败，是把"Python 3.10+"读成一项要求。它是两项，而且互不相关：

| | 宿主机 Python | GDB 内嵌的 Python |
| --- | --- | --- |
| 运行什么 | `kernlens` 控制台脚本、`install.sh`、`kernlens doctor` | 启动文件、每一个命令、每一次 `kernlens.*` 导入 |
| 下限 | 3.10（`requires-python`） | 3.10（包是被导入的，不是被重写的） |
| 从哪里看到 | `kernlens doctor` → `python` | `kernlens doctor` → `gdb-python` |

在下面那台测量用机器上，两者恰好接近——3.12.11 与 3.12.3——那是巧合，不是要求。
在它们之间传递的是磁盘上的文件，不是解释器：启动文件把自己所在包的父目录加进
`sys.path`，于是包和它的依赖都从宿主机当初安装它们的同一个 `site-packages` 里解析。

**不会**传递的是为宿主机解释器编译的扩展。KernLens 是纯 Python，今天没有这类依赖；
这是增加这类依赖之前要检查的地方，而不是现在要解决的问题。

## 矩阵

| 环境 | GDB | GDB 的 Python | 宿主机 Python | 内核 | 状态 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| Ubuntu 24.04.5 宿主，x86_64 QEMU 客户机 | 15.1（Ubuntu 15.1-1ubuntu1~24.04.1） | 3.12.3 | 3.12.11 | 6.1.134，4 级页表，KASLR 开，SLUB，4 CPU | 实测 | `tools/tutorial_capture.json`；`kernlens doctor` |
| Ubuntu 24.04.5，干净 venv 里的 wheel，仅加载 | 15.1 | 3.12.3 | 3.12 | 无（无调试目标） | 实测 | `source $(kernlens path)` 打印 `KernLens 0.3.0 loaded` |
| Ubuntu 24.04.5，无 `vmlinux` 且无目标 | 15.1 | 3.12.3 | 3.12.11 | 宿主 7.0.0-38-generic，BTF 可读 | 实测 | `kernlens doctor` 报告 `btf ok`；`kl-status` 打印 `?` 而不是猜测 |
| 4 级页表含 2 MiB 大页叶项 | 15.1 | 3.12.3 | 3.12.11 | 6.1.134 | 实测 | 捕获中的 `kl-walk` 与 `kl-pagewalk` |
| 5 级页表 | 无（假 `gdb`） | 不适用 | 3.10 – 3.13 | 合成页表 | 测试中实测 | `tests/integration/test_gdb_facade.py` 走完整的 4 级与 5 级页表；捕获只在 4 级内核上尝试 5 级，并报告 `p4d entry is not present` |
| 无 DWARF 也无 BTF 时的兜底布局 | 无（假 `gdb`） | 不适用 | 3.10 – 3.13 | 6.1.134 的布局数值 | 测试中实测 | `tests/integration/test_gdb_facade.py`；命令层在使用兜底时会警告 |
| 任意 Linux，任意带 Python 3.10+ 的 GDB | 任意 | 3.10 – 3.13 | 3.10 – 3.13 | 任意带 DWARF 或 BTF 的 x86_64 | 预期 | 要求均满足；未运行 |
| 以 `--without-python` 构建的 GDB | 任意 | 无 | 任意 | 任意 | 不支持 | 没有解释器可以 source Python 文件；`doctor` 会报告 |
| 内嵌 Python 低于 3.10 的 GDB | 任意 | < 3.10 | 任意 | 任意 | 不支持 | `requires-python` 是 3.10；包由那个解释器导入 |
| arm64、ppc64le、riscv64 | 任意 | 任意 | 任意 | 任意 | 不支持 | 页表与 `struct page` 解码是按 x86_64 写的 |
| `vmcore` / 崩溃转储 / `crash` 工具 | 任意 | 任意 | 任意 | 任意 | 不支持 | 命令通过活动的 `target remote` 读内存 |
| 既无 DWARF 也无 BTF、版本又在兜底表之外的内核 | 任意 | 任意 | 任意 | 任意 | 不支持 | 注册表里没有条目；命令打印 `not in the fallback registry` |

第 1、3、4 行是宿主或它调试的 QEMU 客户机；第 2 行是该宿主上的干净 venv；第 5、6
行从不加载调试器，所以 GDB 一列写"无"。第 3 行就是"没有 `vmlinux`、没有目标"的宿主
的样子：`btf ok` 表示兜底表可读，`kl-status` 对它解析不出来的东西打印 `?`——那是
文档化的拒绝，不是故障。

兜底表不能替代 DWARF。偏移依赖 `CONFIG_*` 选项，所以某个条目对同一版本的另一次构建
可能是错的；这就是使用它会打印警告的原因，也是它那一行的状态是"测试中实测"而不是在
某个内核上"实测"的原因。

这里不承诺最低 GDB 版本。跑过的最老版本是 15.1，也就是实测那一行。用到的 API
——`gdb.Command`、`parse_and_eval`、`execute`、`selected_inferior`、
`newest_frame`、`lookup_type`——存在的时间远早于此，这只是一个"更老的版本应该也能
用"的论据，不是一次测量。把论据变成承诺的，是某条在更老 GDB 上的实测记录。

## 新增一行需要什么

要把"预期"行变成"实测"行，一个 pull request 应当带上：

- `kernlens doctor` 报告（宿主侧），以代码块粘贴；
- `kl-status --doctor` 报告（会话内），如果该行声称覆盖某个内核；
- 内核版本及其页表级数，如果该行声称覆盖某个内核——对一份完整捕获来说，就是
  `tools/tutorial_capture.json` 记录的那个版本。

缺了这些就是散文，而本页存在的意义正是取代散文。
`tests/unit/test_compatibility.py` 检查那些无需调试目标就能检查的部分：状态用词、
与 `pyproject.toml` 及 CI 矩阵对照的 Python 版本范围，以及与捕获对照的测量内核。

## 支持窗口

这不是发行版支持承诺。修复落在 `main` 和最新的发布上；旧版本不做回溯修补。什么算
安全漏洞、以及版本表，见
[`SECURITY.md`](https://github.com/BinRacer/KernLens/blob/main/SECURITY.md)。

---