# `kernlens-msr`

Model-specific registers

**Alias:** `kl-msr`  
**Category:** CPU topology  
**Synopsis:** `kernlens-msr [-h] [-w [write_value]] [-l] [-r [MSR_RANGE]] [msr]`

Reads or writes x86_64 MSRs through GDB's register interface.  On a QEMU gdbstub only a few are exposed, and the command says which ones rather than guessing.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | MSR value or name |
| `-w`, `--write` | write_value | value to write in MSR |
| `-l`, `--list` | — | list common MSRs for the current arch |
| `-r`, `--range` | (optional) | dash separated range of MSRs to read |

## Known registers

### Invocation

```gdb
kernlens-msr -l
```

### Output

```text
MSR_EFER           = 0xc0000080
MSR_STAR           = 0xc0000081
MSR_LSTAR          = 0xc0000082
MSR_CSTAR          = 0xc0000083
MSR_SYSCALL_MASK   = 0xc0000084
MSR_FS_BASE        = 0xc0000100
MSR_GS_BASE        = 0xc0000101
MSR_KERNEL_GS_BASE = 0xc0000102
MSR_TSC_AUX        = 0xc0000103
```

### Reading it

The built-in table of names to numbers.  Using the name instead of the number makes a script self-documenting, and the table is short enough to read.

## Reading a register

### Invocation

```gdb
kernlens-msr 0xc0000082
```

### Output

```text
cannot read $lstar; the remote target does not expose this MSR
```

### Reading it

This is `MSR_LSTAR`, the syscall entry point.  On this target the read fails, and the message says exactly why: the gdbstub exposes only `$efer`, `$fs_base` and `$gs_base` as pseudo-registers, and a wider value comes back as `void`.  Reporting the limitation is preferable to printing a zero that looks like a real value.

## Notes

`--range A-B` prints a run of registers.  Writing (`-w`) goes through the same pseudo-register interface, so it is limited the same way.  Reading an arbitrary MSR would need shellcode injection, which this project deliberately does not do: it kernel-panicked the test VM in every prototype.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
