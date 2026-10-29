# demo/

A kernel, QEMU, and GDB, packaged so KernLens can be tried without a
debug target of your own.

```console
docker build -f demo/Dockerfile -t kernlens-demo .
docker run --rm -it kernlens-demo
```

Run both from the repository root; the build context is the checkout and
the Dockerfile is `demo/Dockerfile`.

| File | Purpose |
| --- | --- |
| `Dockerfile` | builds the kernel and initramfs, then the runtime image |
| `entrypoint.sh` | boots QEMU, waits for userspace, attaches GDB |
| `demo.gdb` | loads the image and sources `gdbinit.py` |
| `demo-commands.gdb` | the scripted tour; no address is baked in |
| `kernel/config.fragment` | the options the commands read, on top of `defconfig` |
| `kernel/init.c` | the whole userspace: mounts, seeds a few objects, prints the boot marker |

`docker run --rm -it kernlens-demo <command>` runs one GDB command
instead of the tour, for example:

```console
docker run --rm -it kernlens-demo kl-slab info dentry
```

The page [docs/demo-container.md](../docs/demo-container.md) explains
what is inside, why the kernel is compiled rather than downloaded, and
the limits of the microvm.
