# `kernlens-kversion`

Kernel version

**Alias:** `kl-kversion`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-kversion [-h]`

Prints the full version banner and the release string KernLens parses out of it.  The release is what the layout registry's version bands are keyed on, so it is worth checking when an offset looks wrong.

## Banner and parsed release

### Invocation

```gdb
kernlens-kversion
```

### Output

```text
Linux version 6.1.134 (bogon@bogon) (gcc (Ubuntu 14.2.0-4ubuntu2~24.04.1) 14.2.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC Sat Oct 17 22:41:31 CST 2026\n
release: 6.1.134
```

### Reading it

The first line is `linux_banner` verbatim, including the compiler and build timestamp.  The `release:` line is the normalised `MAJOR.MINOR.PATCH` that the registry uses for variant selection; a distribution suffix (`-generic`, `-amd64`) is stripped, because the ABI follows the upstream version, not the packaging.

## Notes

`CONFIG_LOCALVERSION` and the build user appear in the banner but not in the parsed release -- they identify the build, not the ABI.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
