# `kl-sym`

Symbol lookup

**Canonical:** `kernlens-sym`  
**Category:** memory & symbols  
**Synopsis:** `kl-sym [-h] [-f] [-a] [query]`

Answers "which symbol is this?" from both tables a session has: an address resolves through the loaded debug info, and `--find` searches the kernel's own kallsyms table by name or address.  The second half was `kl-klookup`.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | address to resolve, or a name (or address) to search for |
| `-f`, `--find` | — | search the kernel's kallsyms table instead of resolving |
| `-a`, `--apply` | — | accepted for pwndbg parity; kernlens reads kallsyms live |

## A text address

### Invocation

```gdb
kl-sym 0xffffffff9a200100
```

### Output

```text
0xffffffff9a200100  secondary_startup_64 at arch/x86/kernel/head_64.S:282
```

### Reading it

The symbol, its section, and `file:line` -- the line comes from DWARF, so it is exact for this build.  The address printed first is the one that was queried, unchanged.  GDB's symbol table is link-time, so KernLens subtracts the slide before asking it; that is why this resolves on a KASLR kernel where a plain `info symbol` misses.

## A data address

### Invocation

```gdb
kl-sym 0xffff9762c0400000
```

### Output

```text
0xffff9762c0400000  ?? at ??
```

### Reading it

`?? at ??` means nothing covers the address.  For a direct-map address that is the correct answer -- the direct map is not a symbol, it is a mapping -- and it is worth seeing so you do not mistake it for a broken symbol table.

## Searching kallsyms for a function

### Invocation

```gdb
kl-sym --find commit_creds
```

### Output

```text
0xffffffff9a3dd800 T commit_creds
0xffffffff9bfe942c r __ksymtab_commit_creds
2 symbol(s) found
```

### Reading it

Two rows appear for a function: the function itself (`T` for a global text symbol) and its `__ksymtab_` entry (`r`, read-only data), which is the export record used by modules.  The trailing count is the number of matches, not a limit.  The first column is a *runtime* address, so it is usable even when GDB's own symbols are link-time.

## Searching kallsyms for a variable

### Invocation

```gdb
kl-sym --find page_offset_base
```

### Output

```text
0xffffffff9bf893a8 D page_offset_base
0xffffffff9bff0620 r __ksymtab_page_offset_base
2 symbol(s) found
```

### Reading it

`D` marks an initialised data symbol.  The address shown is where the variable lives, not its value -- use `kl-kvar` for the value, which is a distinction `page_offset_base` makes very visible, since the address is in `.data` and the value is a direct-map base.

## Notes

`--find` is the command to use when GDB's symbol table is at link-time addresses and `info symbol` misses; without it the argument must be an address, and a name is refused with a pointer to `--find`.  `-a/--apply` is accepted for pwndbg compatibility and explains that it is a no-op: pwndbg rebuilds an ELF symbol table from kallsyms and loads it, while KernLens reads the tables live, so there is nothing to apply.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
