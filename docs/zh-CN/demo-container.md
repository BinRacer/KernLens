# 演示容器

一个镜像里有内核、QEMU、GDB 和 KernLens，所以第一次会话不需要调试目标、不需要
内核源码树，也不需要 `/dev/kvm`：

```console
docker build -f demo/Dockerfile -t kernlens-demo .
docker run --rm -it kernlens-demo
```

在仓库根目录执行：构建上下文就是这份 checkout，Dockerfile 是
[`demo/Dockerfile`](https://github.com/BinRacer/KernLens/blob/main/demo/Dockerfile)。

默认运行会启动客户机、等用户态就绪、附上 GDB，然后跑一段简短的导览：

| 命令 | 它展示什么 |
| --- | --- |
| `kl-status` | KASLR 偏移、`_text`、直接映射与 vmemmap 基址、CPU 拓扑 |
| `kl-base` | 运行时的 text 基址，以及是由哪份证据推出来的 |
| `kl-kconfig RANDOMIZE_BASE` | 运行中内核的配置，从 IKCONFIG 读出 |
| `kl-slab info kmalloc-1k` | 一个缓存的几何形状与每 CPU 空闲链表 |
| `kl-sym` | 通过符号表解析出的 `init_task` |
| `kl-walk --style pwndbg` | `init_task` 背后的各级页表 |

传入一个命令就只跑那一个，不跑导览：

```console
docker run --rm -it kernlens-demo kl-slab info dentry
docker run --rm -it kernlens-demo kl-help
```

## 里面有什么

| 部件 | 来源 |
| --- | --- |
| 内核 | 6.1.134，由 `linux-6.1.134.tar.xz` 加 `x86_64_defconfig` 与 [`demo/kernel/config.fragment`](https://github.com/BinRacer/KernLens/blob/main/demo/kernel/config.fragment) 构建 |
| 用户态 | 一个静态二进制 [`demo/kernel/init.c`](https://github.com/BinRacer/KernLens/blob/main/demo/kernel/init.c)，作为 initramfs 挂载 |
| 机器 | QEMU `-M microvm -cpu qemu64 -m 512M -smp 4`，TCG |
| 调试器 | GDB 通过 [`demo/demo.gdb`](https://github.com/BinRacer/KernLens/blob/main/demo/demo.gdb) 附到 gdbstub |

内核在第一个构建阶段编译，离开该阶段的只有三个文件：`bzImage`、剥掉调试信息的
`vmlinux`、initramfs。第二个阶段只带 GDB、QEMU、这个内核和 KernLens 源码——
没有别的。

## 为什么是构建内核，而不是下载

带 DWARF 的 `vmlinux` 约 700 MB。把它塞进镜像等于让用户下载一个只读一次的文件，
还会把演示钉死在那次构建恰好使用的配置上。自己构建让镜像可以从某个 tag 复现，也让
配置片段留在仓库里。

构建保留 `.BTF` 与符号表，丢弃 DWARF 段：

```dockerfile
RUN cp /build/linux/vmlinux /build/vmlinux \
    && objcopy --strip-debug /build/vmlinux
```

这正是发行版剥离后 `vmlinux` 的样子，也是这个演示同时是对 KernLens 自身的检验的
原因：没有 DWARF，GDB 就没有 `struct` 类型，于是布局来自镜像里的 BTF、地址来自
符号表。一个命令在这里能用，就能用在只带 BTF 而没有 DWARF 的调试包里。

## 会话是怎么起来的

[`demo/entrypoint.sh`](https://github.com/BinRacer/KernLens/blob/main/demo/entrypoint.sh)
做四件事：

1. 用 `-s` 启动 QEMU，在 1234 端口打开 gdbstub。内核照常启动，GDB 附到一台已经在
   跑的机器上。
2. 把控制台输出重定向到文件，等待 `kernlens-demo: init running` 这一行——initramfs
   在挂好 `/proc`、`/sys`、`/dev` 之后才打印它。在这之前附上去，读到的是未初始化
   的内存。
3. 以 `gdb -q -batch -nx` 运行 `demo.gdb`（载入镜像、连接、source
   `gdbinit.py`），然后跑导览或调用方给的命令。
4. 退出时杀掉 QEMU，包括 Ctrl-C 的情况。

TCG 意味着不需要 `/dev/kvm`；在这台测量用机器上，客户机约两秒进入用户态。有 KVM
的机器**只能**在同时修改 QEMU 启动参数时传 `--device /dev/kvm`，镜像本身没有这样
做。

## 地址每次都会变

KASLR 是开着的。导览从不打印从捕获里抄来的地址：它用
`reader.kvar_addr("init_task")` 解析出 `init_task`，再把那个数传给 `kl-sym` 和
`kl-walk`。上一次运行的数字在下一次就是错的——这正是这个演示要教的东西。

## 换内核版本

`KERNEL_VERSION` 是构建参数，换一个 6.1.y 版本不需要改文件：

```console
docker build -f demo/Dockerfile \
  --build-arg KERNEL_VERSION=6.1.140 -t kernlens-demo .
```

`BASE_IMAGE` 是为连不上 Docker Hub 的网络准备的：

```console
docker build -f demo/Dockerfile \
  --build-arg BASE_IMAGE=registry.example/ubuntu:24.04 \
  -t kernlens-demo .
```

配置片段是契约：它保留 `CONFIG_DEBUG_INFO_BTF`、`CONFIG_IKCONFIG`、
`CONFIG_SLUB`、`CONFIG_RANDOMIZE_BASE`、`CONFIG_KALLSYMS_ALL`，以及导览需要读的
串口与 initramfs 选项。去掉其中一个，导览的某一部分会变成 `?` 或"未配置"的提示，
而不是一个错误的答案。

## 限制

- **仅 amd64。** 内核构建和镜像都是 x86_64；多架构清单需要为每种架构准备原生
  构建机。
- **没有模块、没有磁盘、没有网络。** `microvm` 加 initramfs 就是整个客户机。那些
  去找已加载模块或块设备的命令会如实报告它们找到的东西——什么也没有。
- **TCG 比 KVM 慢。** 导览很小；在 TCG 下遍历大内核里的每一个缓存不会是瞬时的。
- **还没有发布镜像。** 打版本 tag 时 `demo image` workflow 会构建同一个镜像并发到
  GitHub Container Registry。在第一个版本之前，用本页顶部的命令在本地构建。

---