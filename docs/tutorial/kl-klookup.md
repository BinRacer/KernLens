# `kernlens-klookup`

Symbol search

**Alias:** `kl-klookup`, `kl-kallsyms`, `kl-ks`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-klookup [-h] [-a] [symbol]`

Searches the kernel's own kallsyms tables and prints every match with its address and type.  This is the command to use when GDB's symbol table is at link-time addresses and `info symbol` misses.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | Address or symbol name to lookup |
| `-a`, `--apply` | — | applies all the symbols that satisfy the filter |

## A function

### Invocation

```gdb
kernlens-klookup commit_creds
```

### Output

```text
0xffffffffadddd800 T commit_creds
0xffffffffaf9e942c r __ksymtab_commit_creds
2 symbol(s) found
```

### Reading it

Two rows appear for a function: the function itself (`T` for a global text symbol) and its `__ksymtab_` entry (`r`, read-only data), which is the export record used by modules.  The trailing count is the number of matches, not a limit.

## A variable

### Invocation

```gdb
kernlens-klookup page_offset_base
```

### Output

```text
0xffffffffaf9893a8 D page_offset_base
0xffffffffaf9f0620 r __ksymtab_page_offset_base
2 symbol(s) found
```

### Reading it

`D` marks an initialised data symbol.  The address shown is where the variable lives, not its value -- use `kl-kvar` for the value, which is a distinction `page_offset_base` makes very visible, since the address is in `.data` and the value is a direct-map base.

## Notes

`-a/--apply` is accepted for pwndbg compatibility and explains that it is a no-op: pwndbg rebuilds an ELF symbol table from kallsyms and loads it, while KernLens reads the tables live, so there is nothing to apply.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
