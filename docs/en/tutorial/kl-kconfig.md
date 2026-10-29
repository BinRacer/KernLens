# `kernlens-kconfig`

Kernel configuration

**Alias:** `kl-kconfig`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-kconfig [-h] [-l FILE_PATH] [config_name]`

Reads the kernel's embedded configuration.  Struct layouts depend on `CONFIG_*` options, so this is the other half of the information the layout registry needs besides the version.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | (optional) | a config name to search for (e.g. RANDOMIZE_BASE) |
| `-l`, `--load` | — | merge CONFIG_* lines from a kernel config file |

## One option

### Invocation

```gdb
kernlens-kconfig RANDOMIZE_BASE
```

### Output

```text
CONFIG_RANDOMIZE_BASE = y
```

### Reading it

The name may be given with or without the `CONFIG_` prefix.  The value is printed in the same form the kernel uses: `y`, `m`, a number, or a quoted string, and `not set` for an option that is off -- which is different from `= n`.

## Notes

The full dump is thousands of lines, so pipe it: `kl-kconfig | grep DMABUF`.  When `/proc/config.gz` support is absent the command says so rather than inventing defaults, because a guessed `CONFIG_*` silently picks the wrong struct layout.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
