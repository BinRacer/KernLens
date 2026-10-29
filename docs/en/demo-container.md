# Demo container

A kernel, QEMU, GDB, and KernLens in one image, so the first session does
not need a debug target, a kernel source tree, or `/dev/kvm`:

```console
docker build -f demo/Dockerfile -t kernlens-demo .
docker run --rm -it kernlens-demo
```

Run those from the repository root: the build context is the checkout
and the Dockerfile is [`demo/Dockerfile`](https://github.com/BinRacer/KernLens/blob/main/demo/Dockerfile).

The default run boots the guest, waits for userspace, attaches GDB, and
runs a short tour:

| Command | What it shows |
| --- | --- |
| `kl-status` | the KASLR slide, `_text`, direct-map and vmemmap bases, topology |
| `kl-base` | the runtime text base, and which evidence produced it |
| `kl-kconfig RANDOMIZE_BASE` | the running kernel's config, read from IKCONFIG |
| `kl-slab info kmalloc-1k` | a cache's geometry and the per-CPU freelists |
| `kl-sym` | `init_task` resolved through the symbol table |
| `kl-walk --style pwndbg` | the page-table levels behind `init_task` |

Pass a command to run only that one instead of the tour:

```console
docker run --rm -it kernlens-demo kl-slab info dentry
docker run --rm -it kernlens-demo kl-help
```

## What is inside

| Piece | Source |
| --- | --- |
| kernel | 6.1.134, built from `linux-6.1.134.tar.xz` with `x86_64_defconfig` plus [`demo/kernel/config.fragment`](https://github.com/BinRacer/KernLens/blob/main/demo/kernel/config.fragment) |
| userspace | one static binary, [`demo/kernel/init.c`](https://github.com/BinRacer/KernLens/blob/main/demo/kernel/init.c), mounted as the initramfs |
| machine | QEMU `-M microvm -cpu qemu64 -m 512M -smp 4`, TCG |
| debugger | GDB attached to the gdbstub with [`demo/demo.gdb`](https://github.com/BinRacer/KernLens/blob/main/demo/demo.gdb) |

The kernel is compiled in the first build stage and only three files
leave it: `bzImage`, the stripped `vmlinux`, and the initramfs.  The
second stage carries GDB, QEMU, the kernel, and the KernLens source --
nothing else.

## Why the kernel is built, not downloaded

A `vmlinux` with DWARF is about 700 MB.  Shipping one would make the
image a download of a file that is read once, and it would pin the demo
to whatever config that build happened to use.  Building it keeps the
image reproducible from a tag and keeps the config fragment in the
repository.

The build keeps `.BTF` and the symbol table and drops the DWARF sections:

```dockerfile
RUN cp /build/linux/vmlinux /build/vmlinux \
    && objcopy --strip-debug /build/vmlinux
```

That is the shape of a distribution's stripped `vmlinux`, and it is why
the demo is also a check on KernLens itself: with no DWARF, GDB has no
`struct` types, so layouts come from the image's BTF and addresses from
the symbol table.  If a command works here, it works on a debug package
that ships BTF instead of DWARF.

## How the session starts

[`demo/entrypoint.sh`](https://github.com/BinRacer/KernLens/blob/main/demo/entrypoint.sh)
does four things:

1. Starts QEMU with `-s`, which opens the gdbstub on port 1234.  The
   kernel boots normally; GDB attaches to a running machine.
2. Sends the console to a file and waits for the line
   `kernlens-demo: init running`, which the initramfs prints after
   mounting `/proc`, `/sys`, and `/dev`.  Attaching before that reads
   uninitialised memory.
3. Runs `gdb -q -batch -nx` with `demo.gdb` (load the image, connect,
   source `gdbinit.py`) and then either the tour or the caller's command.
4. Kills QEMU on exit, including Ctrl-C.

TCG means no `/dev/kvm` is required; the guest reaches userspace in about
two seconds on the machines this was measured on.  A machine with KVM can
pass `--device /dev/kvm` only if the QEMU invocation is changed to use
it, which the image does not do.

## Addresses change every run

KASLR is enabled.  The tour never prints an address copied from a
capture: it resolves `init_task` with `reader.kvar_addr("init_task")` and
passes that number to `kl-sym` and `kl-walk`.  A number from one run
is wrong in the next, which is exactly what the demo is meant to teach.

## Changing the kernel

`KERNEL_VERSION` is a build argument, so another 6.1.y release does not
need an edit:

```console
docker build -f demo/Dockerfile \
  --build-arg KERNEL_VERSION=6.1.140 -t kernlens-demo .
```

`BASE_IMAGE` exists for a network that cannot reach Docker Hub:

```console
docker build -f demo/Dockerfile \
  --build-arg BASE_IMAGE=registry.example/ubuntu:24.04 \
  -t kernlens-demo .
```

The config fragment is the contract: it keeps `CONFIG_DEBUG_INFO_BTF`,
`CONFIG_IKCONFIG`, `CONFIG_SLUB`, `CONFIG_RANDOMIZE_BASE`,
`CONFIG_KALLSYMS_ALL`, and the serial/initramfs options the tour reads.
Removing one turns part of the tour into a `?` or a "not configured"
message rather than a wrong answer.

## Limits

- **amd64 only.**  The kernel build and the image are x86_64; a
  multi-architecture manifest would need a native builder per
  architecture.
- **No modules, no disk, no network.**  `microvm` with an initramfs is
  the whole guest.  Commands that look for loaded modules or block
  devices report what they find, which is nothing.
- **TCG is slower than KVM.**  The tour is small; walking every cache in
  a large kernel under TCG is not instant.
- **The image is built locally, not published.**  Compiling a kernel is
  minutes of work, and a registry tag would pin this project to
  maintaining rebuilds for an artifact that is one command away.  The
  `demo/Dockerfile` in the checkout is the deliverable: build it with the
  command at the top of this page.  No workflow builds or publishes an
  image.
