#
# KernLens demo: a kernel under QEMU, GDB attached through the gdbstub.
#
# The first stage builds a small x86_64 kernel and a one-binary
# initramfs; the second carries only GDB, QEMU, the kernel, and the
# KernLens source.  The kernel is built here rather than downloaded
# because a prebuilt vmlinux with debug info is hundreds of megabytes and
# would have to be hosted somewhere; building it keeps the image
# reproducible from a tag.
#
# `BASE_IMAGE` is an argument so a restricted network can point at a
# mirror without editing the file:
#
#   docker build --build-arg BASE_IMAGE=registry.example/ubuntu:24.04 ...

ARG BASE_IMAGE=ubuntu:24.04

FROM ${BASE_IMAGE} AS kernel

ARG KERNEL_VERSION=6.1.134
ARG KERNEL_URL=https://cdn.kernel.org/pub/linux/kernel/v6.x

ENV DEBIAN_FRONTEND=noninteractive
# `python3` is not for anything this repository runs: the kernel's
# `tools/bpf/resolve_btfids` generates `libbpf/bpf_helper_defs.h` with it,
# and the base image does not carry it.  Without it the build dies at
# `GEN .../bpf_helper_defs.h` with `/usr/bin/env: 'python3': No such file
# or directory`, which is what the first tagged run of the image hit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc \
        bison \
        build-essential \
        ca-certificates \
        cpio \
        curl \
        dwarves \
        flex \
        gzip \
        libelf-dev \
        libssl-dev \
        python3 \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL "${KERNEL_URL}/linux-${KERNEL_VERSION}.tar.xz" \
        -o linux.tar.xz \
    && tar -xJf linux.tar.xz \
    && mv "linux-${KERNEL_VERSION}" linux

COPY demo/kernel/config.fragment demo/kernel/init.c /build/

WORKDIR /build/linux
RUN make defconfig \
    && scripts/kconfig/merge_config.sh -O . .config /build/config.fragment \
    && make olddefconfig \
    && make -j"$(nproc)" bzImage

# One static binary is the whole userspace.  A shell would need a second
# binary and a libc in the initramfs; this needs neither.
WORKDIR /build/initramfs
RUN gcc -static -Os -o init /build/init.c \
    && mkdir -p proc sys dev \
    && find . -print0 | cpio --null -o -H newc | gzip -9 \
        > /build/initramfs.cpio.gz

# `.BTF` and the symbol table are what KernLens reads; the DWARF sections
# are most of the image and are only needed while the kernel is built.
RUN cp /build/linux/vmlinux /build/vmlinux \
    && objcopy --strip-debug /build/vmlinux

FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.source="https://github.com/BinRacer/KernLens" \
      org.opencontainers.image.description="KernLens demo: a Linux kernel under QEMU and GDB" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        gdb \
        qemu-system-x86 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=kernel /build/linux/arch/x86/boot/bzImage /opt/demo/bzImage
COPY --from=kernel /build/vmlinux /opt/demo/vmlinux
COPY --from=kernel /build/initramfs.cpio.gz /opt/demo/initramfs.cpio.gz

# The checkout layout is the install path the README documents, and the
# startup file adds `src/` to `sys.path` from its own location.  No pip
# and no wheel are involved; GDB's interpreter is 3.12 here, so the only
# runtime dependency (`typing-extensions` below 3.12) is not needed.
COPY gdbinit.py /opt/kernlens/gdbinit.py
COPY src /opt/kernlens/src

COPY demo/demo.gdb demo/demo-commands.gdb demo/entrypoint.sh /opt/demo/
RUN chmod +x /opt/demo/entrypoint.sh

WORKDIR /opt/kernlens
ENTRYPOINT ["/opt/demo/entrypoint.sh"]
