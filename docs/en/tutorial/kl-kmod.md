# `kl-kmod`

Loaded modules

**Canonical:** `kernlens-kmod`  
**Category:** kernel metadata  
**Synopsis:** `kl-kmod [-h] [-l PATH] [module_name]`

Walks the `modules` list and prints each loaded module with its address range and size.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | A module name to search for |
| `-l`, `--load` | — | the path of the module to load |

## Listing modules

### Invocation

```gdb
kl-kmod
```

### Output

```text
no kernel modules are loaded
```

### Reading it

One row per module: name, base, size, and state.  The base is in the module region, not the direct map, so it is usable as a breakpoint address directly.

## Filtering

### Invocation

```gdb
kl-kmod nonexistent
```

### Output

```text
no kernel modules are loaded
```

### Reading it

A name that matches nothing is reported as such rather than printing an empty table -- an empty result and a typo look the same otherwise.

## Notes

A kernel with no modules loaded at all prints `no kernel modules are loaded`, which is a normal state for a minimal VM, not an error.  `-l/--load` runs `add-symbol-file` for a module .ko so its own symbols resolve.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
