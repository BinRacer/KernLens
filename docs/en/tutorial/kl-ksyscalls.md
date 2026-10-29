# `kl-ksyscalls`

Syscall table

**Canonical:** `kernlens-ksyscalls`  
**Category:** kernel metadata  
**Synopsis:** `kl-ksyscalls [-h] [syscall_name]`

Decodes `sys_call_table` and resolves each entry to a symbol.  Useful for finding where a syscall is really implemented, and for spotting hooks: an entry that points outside `__x64_sys_*` is worth a second look.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | a syscall name to search for |

## The whole table

### Invocation

```gdb
kl-ksyscalls
```

### Output

```text
Syscall table address with 451 entries found at 0xffffffff9ba00300.

                Address Symbol
   0 0xffffffff9a6ee280 __x64_sys_read
   1 0xffffffff9a6ee3e0 __x64_sys_write
   2 0xffffffff9a6e9d30 __x64_sys_open
   3 0xffffffff9a6e7030 __x64_sys_close
   4 0xffffffff9a6f52a0 __x64_sys_newstat
   5 0xffffffff9a6f4fa0 __x64_sys_newfstat
   6 0xffffffff9a6f54f0 __x64_sys_newlstat
   7 0xffffffff9a70d660 __x64_sys_poll
   8 0xffffffff9a6eaa20 __x64_sys_lseek
   9 0xffffffff9a252960 __x64_sys_mmap
  10 0xffffffff9a650510 __x64_sys_mprotect
  11 0xffffffff9a64aa90 __x64_sys_munmap
  12 0xffffffff9a64ba90 __x64_sys_brk
  13 0xffffffff9a3c1ca0 __x64_sys_rt_sigaction
  14 0xffffffff9a3baeb0 __x64_sys_rt_sigprocmask
  15 0xffffffff9a24a580 __x64_sys_rt_sigreturn
  16 0xffffffff9a709c10 __x64_sys_ioctl
... (434 more line(s), 454 total)
```

*The capture has 454 lines; the first 20 are shown.  Run the command to see the rest.*

### Reading it

The header gives the table's address and length; the length is discovered by walking until the entries stop resolving to `__x64_sys_*` symbols, not taken from a constant, because `NR_syscalls` is a build-time macro.  Each row is the syscall number, the resolved address, and the symbol.

## Filtering by name

### Invocation

```gdb
kl-ksyscalls read
```

### Output

```text
Syscall table address with 451 entries found at 0xffffffff9ba00300.

                Address Symbol
   0 0xffffffff9a6ee280 __x64_sys_read
  17 0xffffffff9a6ed5d0 __x64_sys_pread64
  19 0xffffffff9a6eb320 __x64_sys_readv
  89 0xffffffff9a6f4820 __x64_sys_readlink
 187 0xffffffff9a5f2e30 __x64_sys_readahead
 267 0xffffffff9a6f47c0 __x64_sys_readlinkat
 295 0xffffffff9a6eb720 __x64_sys_preadv
 310 0xffffffff9a6629b0 __x64_sys_process_vm_readv
 327 0xffffffff9a6eb540 __x64_sys_preadv2
```

### Reading it

A substring filter.  The match is against the symbol name, so `read` finds `read`, `pread64`, `readv`, `readlink`, `readlinkat`, and `process_vm_readv` -- the families are what you usually want.

## Filtering by number

### Invocation

```gdb
kl-ksyscalls 0
```

### Output

```text
cannot read sys_call_table; load a matching vmlinux (with debug info) first
```

### Reading it

A name that is not in the table is reported as an unreadable table, which is the honest answer when the matching `vmlinux` is not loaded.

## Notes

On this kernel the table has 451 entries.  The count follows `CONFIG_*` options (new syscalls, compat entries), which is why it is discovered rather than hardcoded.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
