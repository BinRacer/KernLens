# `kl-kcmdline`

Boot command line

**Canonical:** `kernlens-kcmdline`  
**Category:** kernel metadata  
**Synopsis:** `kl-kcmdline [-h]`

The kernel's own record of how it was started.  Worth reading before interpreting almost anything else: `nokaslr`, `pti`, `no5lvl` and the zone layout all come from here.

## Reading the command line

### Invocation

```gdb
kl-kcmdline
```

### Output

```text
root=/dev/sda console=ttyS0 rw loglevel=3 oops=panic panic=1 net.ifnames=0 biosdevname=0 no5lvl kaslr pti=on
```

### Reading it

The line is read from `saved_command_line`, so it is what the kernel saved at boot rather than what is in this shell's history.  `kaslr` present means the slide is non-zero; `no5lvl` means the 5-level tables are compiled in but disabled.

## Notes

`kl-kcmdline` reads a kernel variable, so it works on a stripped image.  `--load` does not exist here: the value is live, and a loaded file would describe a different boot.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
