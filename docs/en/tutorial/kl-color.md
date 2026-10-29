# `kl-color`

Colour control

**Canonical:** `kernlens-color`  
**Category:** output  
**Synopsis:** `kl-color [-h] [{on,off,toggle}]`

Turns ANSI colour on, off, or toggles it, and reports the resulting state either way.  Colour is one switch affecting the logger and the styler together, so a command cannot end up half coloured.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | `on` \| `off` \| `toggle` | explicit state; no argument prints the current state |

## Querying the current state

### Invocation

```gdb
kl-color
```

### Output

```text
KernLens color: on
```

### Reading it

With no argument the command only reports.  The state comes from the facade, which owns both the logger's and the styler's flag.

## Toggling

### Invocation

```gdb
kl-color toggle
```

### Output

```text
KernLens color: off
```

### Reading it

`toggle` flips whatever the current state is, which is what makes it safe to bind to a key: it never has to know the starting state.

## Turning it on explicitly

### Invocation

```gdb
kl-color on
```

### Output

```text
KernLens color: on
```

### Reading it

`on`/`off` are idempotent, so scripts can assert the state they need without checking first.

## Notes

Disabling colour first is worth doing before capturing output for a bug report or for these pages: the escape sequences are invisible in a terminal but very visible in a diff.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
