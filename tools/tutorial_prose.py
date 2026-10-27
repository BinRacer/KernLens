#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Hand-written prose for the generated tutorial pages.

Every entry in :data:`PAGES` is keyed by the canonical command name.  The
renderer in ``tools/gen_tutorial.py`` merges this text with captured
output, so the prose here never repeats an output block: it says what
the command is for and how to read the answer, and the capture supplies
the values.

Rules for editing this file:

* an ``invocation`` must appear verbatim in the capture, or
  ``gen_tutorial.py --check`` fails -- there is no way to document an
  example that was never really run;
* ``reading`` explains the shape of the output, not the specific
  numbers, because the numbers change between boots;
* where a value is genuinely boot-dependent (the KASLR slide, the
  direct-map base), say so instead of presenting it as a constant.
"""

from __future__ import annotations

PAGES: dict[str, dict] = {}


# --------------------------------------------------------------------
# help and overview
# --------------------------------------------------------------------

PAGES["kernlens-help"] = {
    "title": "Command reference",
    "intro": (
        "`kl-help` is the only command that needs no debuggee: it reads "
        "the command registry that `@Command` decorated functions "
        "populate.  A bare invocation lists every command grouped by "
        "category; giving a name prints that command's full help."
    ),
    "sections": [
        {
            "heading": "Listing every command",
            "invocation": "kernlens-help",
            "reading": (
                "Commands are grouped by the category the decorator "
                "declared.  The usage column is the command's own "
                "`argparse` usage string, so it always matches what the "
                "parser accepts.  Only `kernlens-` names are listed: the "
                "`kl-` aliases are one-to-one and would double the "
                "output."
            ),
        },
        {
            "heading": "Explaining one command",
            "invocation": "kernlens-help kl-walk",
            "reading": (
                "The argument must be namespaced.  `kl-help walk` is "
                "rejected with a hint to try `kl-walk`, because the bare "
                "names exist in pwndbg and GDB but never in KernLens' "
                "registry -- accepting them would make the help depend on "
                "what else happens to be loaded."
            ),
        },
        {
            "heading": "A command with subcommands",
            "invocation": "kernlens-help kernlens-slab",
            "reading": (
                "Subcommands appear in the positional argument's help "
                "text rather than as argparse subparsers, because "
                "KernLens dispatches them itself to keep pwndbg's "
                "`slab list` / `slab info` spellings working."
            ),
        },
    ],
    "notes": (
        "The `Examples:` and `Notes:` lines at the bottom of each page "
        "come from the decorator, not from the parser, so they can carry "
        "the longer explanation that would clutter `--help`."
    ),
}

PAGES["kernlens-status"] = {
    "title": "Session status",
    "intro": (
        "One-screen check that KernLens is attached to a kernel it can "
        "read, and what it currently believes about that kernel.  Run it "
        "first when a command behaves unexpectedly."
    ),
    "sections": [
        {
            "heading": "The status block",
            "invocation": "kernlens-status",
            "reading": (
                "`KASLR slide` is the value the **reader** is using, "
                "derived from the live IDT if nothing has set it yet -- "
                "it is not a cached attribute that stays zero.  "
                "`_text` shows the link-time and runtime addresses "
                "side by side, which is the quickest way to spot a slide "
                "that is wrong by a constant.  `page_offset` and "
                "`vmemmap` are the two bases every address translation "
                "depends on; both are kernel variables chosen at boot."
            ),
        },
    ],
    "notes": (
        "Everything here is read through the facade, so it works on a "
        "stripped kernel with no debug info: the slide is recovered from "
        "the IDT, and the version from the banner."
    ),
}

PAGES["kernlens-color"] = {
    "title": "Colour control",
    "intro": (
        "Turns ANSI colour on, off, or toggles it, and reports the "
        "resulting state either way.  Colour is one switch affecting the "
        "logger and the styler together, so a command cannot end up half "
        "coloured."
    ),
    "sections": [
        {
            "heading": "Querying the current state",
            "invocation": "kernlens-color",
            "reading": (
                "With no argument the command only reports.  The state "
                "comes from the facade, which owns both the logger's and "
                "the styler's flag."
            ),
        },
        {
            "heading": "Toggling",
            "invocation": "kernlens-color toggle",
            "reading": (
                "`toggle` flips whatever the current state is, which is "
                "what makes it safe to bind to a key: it never has to know "
                "the starting state."
            ),
        },
        {
            "heading": "Turning it on explicitly",
            "invocation": "kernlens-color on",
            "reading": (
                "`on`/`off` are idempotent, so scripts can assert the "
                "state they need without checking first."
            ),
        },
    ],
    "notes": (
        "Disabling colour first is worth doing before capturing output "
        "for a bug report or for these pages: the escape sequences are "
        "invisible in a terminal but very visible in a diff."
    ),
}

# --------------------------------------------------------------------
# kernel base and KASLR
# --------------------------------------------------------------------

PAGES["kernlens-base"] = {
    "title": "Active base and slide",
    "intro": (
        "Prints the base KernLens is *using right now* and how it decided "
        "on it.  Unlike `kl-kbase`, which searches, this only reports: it "
        "never changes the slide."
    ),
    "sections": [
        {
            "heading": "The active base",
            "invocation": "kernlens-base",
            "reading": (
                "`kernel base` is the runtime `_text`; `KASLR offset` is "
                "the difference from the link-time address.  `method` "
                "names the source -- `symbol` means the `_text` symbol "
                "resolved, which is the strongest evidence available.  "
                "`status` reports whether there is a live inferior at all, "
                "since the slide can also be known from a core file."
            ),
        },
    ],
    "notes": (
        "12+ call sites add the slide to a link-time address themselves, "
        "which is why `link_text()` keeps returning the link-time value "
        "and this command is what reports the runtime one."
    ),
}

PAGES["kernlens-kbase"] = {
    "title": "Find the kernel base",
    "intro": (
        "Recovers the kernel's runtime base from the live machine, "
        "independently of any symbol table.  This is what makes KernLens "
        "usable on a KASLR kernel whose `vmlinux` is loaded at its "
        "link-time addresses."
    ),
    "sections": [
        {
            "heading": "The search",
            "invocation": "kernlens-kbase",
            "reading": (
                "`method: symbol` is the strongest case: the `_text` "
                "symbol was resolvable.  When it is not, the fallback "
                "reads the IDT and takes the first handler's address, "
                "subtracting the handler's known link-time offset -- that "
                "is what `handler=` and `symbol=` report.  `idt:` shows "
                "the table's own base, limit, and where it was read from "
                "(`monitor` means the QEMU monitor, `memory` means the "
                "`idt_table` symbol)."
            ),
        },
        {
            "heading": "Showing the physical address",
            "invocation": "kernlens-kbase -v",
            "reading": (
                "`-v` adds the physical address the text is loaded at, "
                "which is what a bootloader or QEMU command line refers "
                "to.  It is derived from the runtime virtual address with "
                "the same direct-map base the rest of KernLens uses."
            ),
        },
        {
            "heading": "Dumping the IDT",
            "invocation": "kernlens-kbase -i 4",
            "reading": (
                "`-i N` prints the first N gate descriptors: offset, "
                "segment selector, gate type, IST index, DPL, and whether "
                "the address is in the kernel or user range.  The first "
                "entries are the CPU exceptions in architectural order, "
                "which makes a wrong IST or DPL immediately visible."
            ),
        },
        {
            "heading": "Rebasing the symbol file",
            "invocation": "kernlens-kbase -r",
            "reading": (
                "`-r` runs `add-symbol-file` for the loaded object at the "
                "recovered base, so GDB's own symbol lookups (and "
                "`info symbol`, and pwndbg's disassembly) start working at "
                "runtime addresses.  Without it GDB's symbol table remains "
                "link-time."
            ),
        },
        {
            "heading": "Applying an explicit value",
            "invocation": "kernlens-kbase --offset {slide}",
            "reading": (
                "`--offset` sets the slide directly and prints nothing "
                "else, which is the form to use in a script that already "
                "knows the slide."
            ),
        },
        {
            "heading": "Computing a slide from a known address",
            "invocation": "kernlens-kbase --text 0xffffffff81000000",
            "reading": (
                "`--text` takes a runtime `_text` and derives the slide "
                "from it.  Passing the link-time address yields `+0x0`, "
                "which is a useful sanity check that the inputs are what "
                "you think they are."
            ),
        },
    ],
    "notes": (
        "`-s/--set` and `-p/--phys` are KernLens-only additions hidden "
        "from `-h`, so the visible surface stays pwndbg's.  The slide is "
        "verified against the IDT rather than trusted, because a wrong "
        "slide produces plausible-looking garbage everywhere else."
    ),
}

PAGES["kernlens-kaslr"] = {
    "title": "Slide from a runtime address",
    "intro": (
        "Sets the KASLR slide from a runtime `_text` you already have -- "
        "from a leak, from `%pK` output, or from the monitor."
    ),
    "sections": [
        {
            "heading": "Deriving and applying",
            "invocation": "kernlens-kaslr {text}",
            "reading": (
                "The difference from the link-time `_text` is the slide.  "
                "Both values are printed so a typo (an address that is not "
                "actually `_text`) shows up as an absurd slide instead of "
                "silently shifting every later read."
            ),
        },
    ],
    "notes": (
        "Prefer `kl-kbase` when the machine is live: it derives the same "
        "value *and* cross-checks it against the IDT.  This command is "
        "for when you already have the address from elsewhere."
    ),
}

PAGES["kernlens-kaslr-offset"] = {
    "title": "Set the slide directly",
    "intro": (
        "Applies a slide you were given, with no derivation and no "
        "verification.  `0` means a non-KASLR kernel."
    ),
    "sections": [
        {
            "heading": "Applying a numeric slide",
            "invocation": "kernlens-kaslr-offset {slide}",
            "reading": (
                "One line, echoing the value that was set.  The slide is "
                "a plain attribute on the facade, so this returns "
                "immediately; nothing is read from the target."
            ),
        },
    ],
    "notes": (
        "Because nothing is verified, a wrong value here makes every "
        "later read wrong in a plausible way.  `kl-status` is the quick "
        "check afterwards: its `_text` row shows link and runtime "
        "side by side."
    ),
}


# --------------------------------------------------------------------
# kernel metadata
# --------------------------------------------------------------------

PAGES["kernlens-kcmdline"] = {
    "title": "Boot command line",
    "intro": (
        "The kernel's own record of how it was started.  Worth reading "
        "before interpreting almost anything else: `nokaslr`, `pti`, "
        "`no5lvl` and the zone layout all come from here."
    ),
    "sections": [
        {
            "heading": "Reading the command line",
            "invocation": "kernlens-kcmdline",
            "reading": (
                "The line is read from `saved_command_line`, so it is what "
                "the kernel saved at boot rather than what is in this "
                "shell's history.  `kaslr` present means the slide is "
                "non-zero; `no5lvl` means the 5-level tables are compiled "
                "in but disabled."
            ),
        },
    ],
    "notes": (
        "`kl-kcmdline` reads a kernel variable, so it works on a stripped "
        "image.  `--load` does not exist here: the value is live, and a "
        "loaded file would describe a different boot."
    ),
}

PAGES["kernlens-kversion"] = {
    "title": "Kernel version",
    "intro": (
        "Prints the full version banner and the release string KernLens "
        "parses out of it.  The release is what the layout registry's "
        "version bands are keyed on, so it is worth checking when an "
        "offset looks wrong."
    ),
    "sections": [
        {
            "heading": "Banner and parsed release",
            "invocation": "kernlens-kversion",
            "reading": (
                "The first line is `linux_banner` verbatim, including the "
                "compiler and build timestamp.  The `release:` line is the "
                "normalised `MAJOR.MINOR.PATCH` that the registry uses for "
                "variant selection; a distribution suffix (`-generic`, "
                "`-amd64`) is stripped, because the ABI follows the "
                "upstream version, not the packaging."
            ),
        },
    ],
    "notes": (
        "`CONFIG_LOCALVERSION` and the build user appear in the banner but "
        "not in the parsed release -- they identify the build, not the "
        "ABI."
    ),
}

PAGES["kernlens-kconfig"] = {
    "title": "Kernel configuration",
    "intro": (
        "Reads the kernel's embedded configuration.  Struct layouts depend "
        "on `CONFIG_*` options, so this is the other half of the "
        "information the layout registry needs besides the version."
    ),
    "sections": [
        {
            "heading": "One option",
            "invocation": "kernlens-kconfig RANDOMIZE_BASE",
            "reading": (
                "The name may be given with or without the `CONFIG_` "
                "prefix.  The value is printed in the same form the kernel "
                "uses: `y`, `m`, a number, or a quoted string, and "
                "`not set` for an option that is off -- which is "
                "different from `= n`."
            ),
        },
    ],
    "notes": (
        "The full dump is thousands of lines, so pipe it: "
        "`kl-kconfig | grep DMABUF`.  When `/proc/config.gz` support is "
        "absent the command says so rather than inventing defaults, "
        "because a guessed `CONFIG_*` silently picks the wrong struct "
        "layout."
    ),
}

PAGES["kernlens-kchecksec"] = {
    "title": "Hardening audit",
    "intro": (
        "Audits the `CONFIG_*` options that decide how hard the kernel is "
        "to exploit.  This is the kernel-space counterpart of pwndbg's "
        "`checksec`."
    ),
    "sections": [
        {
            "heading": "The audit",
            "invocation": "kernlens-kchecksec",
            "output_lines": 20,
            "reading": (
                "Three states appear: `= y` (enabled), `= m` (module), and "
                "`not set` (compiled out).  The list is ordered from the "
                "stack to the allocator, so a quick scan tells you whether "
                "the machine is a realistic target or a debugging build.  "
                "Note that `SLAB_FREELIST_RANDOM` and "
                "`SLAB_FREELIST_HARDENED` are separate: the first "
                "shuffles object order, the second encodes the free "
                "pointer."
            ),
        },
    ],
    "notes": (
        "The options audited are fixed in the command, not configurable: "
        "they are the ones that change what an exploit has to do, and a "
        "user-supplied list would make two reports incomparable."
    ),
}

PAGES["kernlens-kmod"] = {
    "title": "Loaded modules",
    "intro": (
        "Walks the `modules` list and prints each loaded module with its "
        "address range and size."
    ),
    "sections": [
        {
            "heading": "Listing modules",
            "invocation": "kernlens-kmod",
            "reading": (
                "One row per module: name, base, size, and state.  The base "
                "is in the module region, not the direct map, so it is "
                "usable as a breakpoint address directly."
            ),
        },
        {
            "heading": "Filtering",
            "invocation": "kernlens-kmod nonexistent",
            "reading": (
                "A name that matches nothing is reported as such rather "
                "than printing an empty table -- an empty result and a "
                "typo look the same otherwise."
            ),
        },
    ],
    "notes": (
        "A kernel with no modules loaded at all prints "
        "`no kernel modules are loaded`, which is a normal state for a "
        "minimal VM, not an error.  `-l/--load` runs `add-symbol-file` "
        "for a module .ko so its own symbols resolve."
    ),
}

PAGES["kernlens-ksyscalls"] = {
    "title": "Syscall table",
    "intro": (
        "Decodes `sys_call_table` and resolves each entry to a symbol.  "
        "Useful for finding where a syscall is really implemented, and "
        "for spotting hooks: an entry that points outside "
        "`__x64_sys_*` is worth a second look."
    ),
    "sections": [
        {
            "heading": "The whole table",
            "invocation": "kernlens-ksyscalls",
            "output_lines": 20,
            "reading": (
                "The header gives the table's address and length; the "
                "length is discovered by walking until the entries stop "
                "resolving to `__x64_sys_*` symbols, not taken from a "
                "constant, because `NR_syscalls` is a build-time macro.  "
                "Each row is the syscall number, the resolved address, and "
                "the symbol."
            ),
        },
        {
            "heading": "Filtering by name",
            "invocation": "kernlens-ksyscalls read",
            "reading": (
                "A substring filter.  The match is against the symbol name, "
                "so `read` finds `read`, `pread64`, `readv`, `readlink`, "
                "`readlinkat`, and `process_vm_readv` -- the families are "
                "what you usually want."
            ),
        },
        {
            "heading": "Filtering by number",
            "invocation": "kernlens-ksyscalls 0",
            "reading": (
                "A name that is not in the table is reported as an "
                "unreadable table, which is the honest answer when the "
                "matching `vmlinux` is not loaded."
            ),
        },
    ],
    "notes": (
        "On this kernel the table has 451 entries.  The count follows "
        "`CONFIG_*` options (new syscalls, compat entries), which is why "
        "it is discovered rather than hardcoded."
    ),
}

PAGES["kernlens-kdmesg"] = {
    "title": "Kernel log",
    "intro": (
        "Prints the ring buffer (`dmesg`) by walking the "
        "`prb`/`printk_info` records directly, which works even when "
        "`dmesg` is restricted for unprivileged users."
    ),
    "sections": [
        {
            "heading": "The ring buffer",
            "invocation": "kernlens-kdmesg",
            "output_lines": 24,
            "reading": (
                "Each line is `[seconds.microseconds] message`, matching "
                "the usual `dmesg` format.  The records are read from the "
                "ring buffer's descriptor array, so the order is the "
                "kernel's own, not a re-sort.  The buffer starts with the "
                "version banner and the command line, which is a "
                "convenient cross-check against `kl-kversion` and "
                "`kl-kcmdline`."
            ),
        },
        {
            "heading": "Wall-clock timestamps",
            "invocation": "kernlens-kdmesg --ctime",
            "reading": (
                "`--ctime` converts the monotonic timestamps to wall-clock "
                "form using the boot time the kernel recorded.  It is "
                "useful for correlating with an exploit run that has its "
                "own timestamps."
            ),
        },
    ],
    "notes": (
        "`printk_info.text_len` is a `u16` and the sequence number lives "
        "in `printk_info`, not in the text blob: reading either from the "
        "wrong place produces plausible but wrong lines.  NUL bytes are "
        "stripped because GDB aborts the write on them."
    ),
}

PAGES["kernlens-klookup"] = {
    "title": "Symbol search",
    "intro": (
        "Searches the kernel's own kallsyms tables and prints every match "
        "with its address and type.  This is the command to use when "
        "GDB's symbol table is at link-time addresses and `info symbol` "
        "misses."
    ),
    "sections": [
        {
            "heading": "A function",
            "invocation": "kernlens-klookup commit_creds",
            "reading": (
                "Two rows appear for a function: the function itself "
                "(`T` for a global text symbol) and its `__ksymtab_` entry "
                "(`r`, read-only data), which is the export record used by "
                "modules.  The trailing count is the number of matches, "
                "not a limit."
            ),
        },
        {
            "heading": "A variable",
            "invocation": "kernlens-klookup page_offset_base",
            "reading": (
                "`D` marks an initialised data symbol.  The address shown "
                "is where the variable lives, not its value -- use "
                "`kl-kvar` for the value, which is a distinction "
                "`page_offset_base` makes very visible, since the address "
                "is in `.data` and the value is a direct-map base."
            ),
        },
    ],
    "notes": (
        "`-a/--apply` is accepted for pwndbg compatibility and explains "
        "that it is a no-op: pwndbg rebuilds an ELF symbol table from "
        "kallsyms and loads it, while KernLens reads the tables live, so "
        "there is nothing to apply."
    ),
}

# --------------------------------------------------------------------
# CPU topology
# --------------------------------------------------------------------

PAGES["kernlens-cpu"] = {
    "title": "CPU topology",
    "intro": (
        "Reports how many CPUs the kernel has, which are online, and the "
        "per-CPU offset each one's data is based at."
    ),
    "sections": [
        {
            "heading": "The topology summary",
            "invocation": "kernlens-cpu",
            "reading": (
                "`nr_cpus` is the configured count and `nr_nodes` the NUMA "
                "node count.  `Online` is compacted into ranges "
                "(`0-3`) rather than four separate numbers, which keeps a "
                "128-CPU machine readable.  `current` is the CPU GDB is "
                "stopped on."
            ),
        },
        {
            "heading": "One CPU in detail",
            "invocation": "kernlens-cpu 0",
            "reading": (
                "The per-CPU offset is the base that a per-CPU symbol's "
                "section offset is added to.  It differs between CPUs, "
                "which is why a per-CPU symbol cannot be read with a bare "
                "`&symbol`."
            ),
        },
    ],
    "notes": (
        "`cur_cpu()` masks GDB's `$gs_base` to 64 bits: the remote target "
        "reports it as a negative value, and the unmasked value silently "
        "fails the per-CPU range check."
    ),
}

PAGES["kernlens-percpu"] = {
    "title": "Per-CPU symbol address",
    "intro": (
        "Resolves a per-CPU symbol to the address the given CPU actually "
        "uses.  This is the fix for the classic mistake of taking "
        "`&current_task` and getting a section offset that is not any "
        "CPU's copy."
    ),
    "sections": [
        {
            "heading": "The current CPU",
            "invocation": "kernlens-percpu current_task",
            "reading": (
                "The bare value of a per-CPU symbol *is* its offset within "
                "the per-CPU section, zero-based, so the runtime address is "
                "`__per_cpu_offset[cpu] + offset`.  Both parts are printed, "
                "which is what makes a mismatch obvious."
            ),
        },
        {
            "heading": "Another CPU",
            "invocation": "kernlens-percpu current_task 1",
            "reading": (
                "Different CPU, different base, same offset.  Comparing two "
                "CPUs' output is the quickest way to confirm the offsets "
                "are being applied rather than ignored."
            ),
        },
    ],
    "notes": (
        "The per-CPU base is read from `__per_cpu_offset[]` rather than "
        "derived, because the linker only guarantees the section is "
        "zero-based; where it lands at run time is the kernel's choice."
    ),
}

PAGES["kernlens-msr"] = {
    "title": "Model-specific registers",
    "intro": (
        "Reads or writes x86_64 MSRs through GDB's register interface.  "
        "On a QEMU gdbstub only a few are exposed, and the command says "
        "which ones rather than guessing."
    ),
    "sections": [
        {
            "heading": "Known registers",
            "invocation": "kernlens-msr -l",
            "reading": (
                "The built-in table of names to numbers.  Using the name "
                "instead of the number makes a script self-documenting, and "
                "the table is short enough to read."
            ),
        },
        {
            "heading": "Reading a register",
            "invocation": "kernlens-msr 0xc0000082",
            "reading": (
                "This is `MSR_LSTAR`, the syscall entry point.  On this "
                "target the read fails, and the message says exactly why: "
                "the gdbstub exposes only `$efer`, `$fs_base` and "
                "`$gs_base` as pseudo-registers, and a wider value comes "
                "back as `void`.  Reporting the limitation is preferable to "
                "printing a zero that looks like a real value."
            ),
        },
    ],
    "notes": (
        "`--range A-B` prints a run of registers.  Writing (`-w`) goes "
        "through the same pseudo-register interface, so it is limited the "
        "same way.  Reading an arbitrary MSR would need shellcode "
        "injection, which this project deliberately does not do: it "
        "kernel-panicked the test VM in every prototype."
    ),
}

# --------------------------------------------------------------------
# addresses and page tables
# --------------------------------------------------------------------

PAGES["kernlens-addr"] = {
    "title": "Address analysis",
    "intro": (
        "Classifies a 64-bit value as an address: canonical or not, which "
        "region it falls in, whether it is an error pointer, how it "
        "aligns, and -- when it is in the direct map -- what physical page "
        "it refers to."
    ),
    "sections": [
        {
            "heading": "A direct-map address",
            "invocation": "kernlens-addr {direct}",
            "reading": (
                "`Region` is a set of independent tests, not a single "
                "classification: `kernel`, `user`, `direct`, `vmemmap`, "
                "`vmalloc`, `module` and `text` are each answered "
                "separately, because a vmemmap address is also a kernel "
                "address.  `Physical` appears only when the address is in "
                "the direct map, since only there is the mapping a constant "
                "offset."
            ),
        },
        {
            "heading": "A text address",
            "invocation": "kernlens-addr {text_addr}",
            "reading": (
                "Now `text=True` and `direct=False`, and there is no "
                "`Physical` row: text is mapped by the kernel image's own "
                "page tables at its runtime virtual address, not through "
                "the direct map."
            ),
        },
        {
            "heading": "A non-canonical value",
            "invocation": "kernlens-addr 0x5",
            "reading": (
                "`user=True` and every kernel region false.  `Canonical` "
                "reports both 48-bit and 57-bit forms, which differ only "
                "for values in the upper half between the two sign "
                "boundaries -- a useful check when a pointer arrives "
                "truncated."
            ),
        },
        {
            "heading": "Ignoring a tag",
            "invocation": "kernlens-addr {direct} 0xfff",
            "reading": (
                "The optional second argument masks the low bits before the "
                "analysis, which is how an address-tagged or page-offset-"
                "carrying value is normalised to its page."
            ),
        },
    ],
    "notes": (
        "The region boundaries are constants (`KERNEL_BASE`, "
        "`VMALLOC_START`, ...) for the layout's fixed parts, while "
        "`page_offset_base` and `vmemmap_base` are read from the kernel.  "
        "A wrong slide changes the former, never the latter."
    ),
}

PAGES["kernlens-pt"] = {
    "title": "Page-table indices",
    "intro": (
        "Shows the index extracted at each level for a virtual address, in "
        "both 4-level and 5-level form, plus the huge-page bases it falls "
        "inside.  This is pure arithmetic -- nothing is read from the "
        "target."
    ),
    "sections": [
        {
            "heading": "A direct-map address",
            "invocation": "kernlens-pt {direct}",
            "reading": (
                "The 4-level row shows five entries (pgd/pud/pmd/pte/off) "
                "and the 5-level row six (with p4d), which is the whole "
                "difference between the modes: 5-level adds one level and "
                "shrinks the offset.  `huge` gives the base of the 2 MiB "
                "and 1 GiB regions containing the address, and `aligned` "
                "says whether the address sits exactly on one -- the pair "
                "answers 'could this be mapped by a huge page?'.  "
                "`page_offset` is the byte offset within a 4 KiB page."
            ),
        },
        {
            "heading": "A text address",
            "invocation": "kernlens-pt {text_addr}",
            "reading": (
                "The upper-half indices are near their maximum "
                "(`pgd=511`, `pud=510`) because the kernel image sits at "
                "the very top of the address space.  This is also where the "
                "two modes disagree most visibly: 5-level paging widens "
                "`pgd` but the kernel still occupies the top."
            ),
        },
    ],
    "notes": (
        "Indices are computed from the address widths, so they do not "
        "depend on the live tables at all.  `kl-walk` is the command that "
        "then reads each level."
    ),
}

PAGES["kernlens-walk"] = {
    "title": "Walk the page tables",
    "intro": (
        "Follows the live tables from CR3 down to the leaf, decoding each "
        "entry.  This is the authoritative answer for `what is this "
        "address mapped to`, as opposed to what the index arithmetic "
        "suggests."
    ),
    "sections": [
        {
            "heading": "A 2 MiB huge-page mapping",
            "invocation": "kernlens-walk {direct}",
            "reading": (
                "Each level row is `name: idx= entry= value=`, so the "
                "entry's address and content are both visible.  The walk "
                "stops at the first level whose entry has the `PS` bit set "
                "-- here `pmd`, marked `(huge leaf)` -- because a huge "
                "mapping has no lower levels.  `Leaf: 2 MiB` then gives the "
                "physical base and the offset inside the huge page.  "
                "`root=` is CR3 with its low control bits masked off."
            ),
        },
        {
            "heading": "Forcing 5-level paging",
            "invocation": "kernlens-walk {direct} 5",
            "reading": (
                "The optional second argument forces the mode.  Here the "
                "walk reports an absent `p4d` entry, which is the correct "
                "answer: the CPU is running with 4-level paging (`no5lvl` "
                "is on the command line), so the tables have no P4D level "
                "and the address is not mapped in that mode."
            ),
        },
    ],
    "notes": (
        "`$cr3` is physical, so table pages are read at "
        "`page_offset_base + phys`.  `-p/--pgd` walks a table other than "
        "the live CR3: a saved one, or a foreign process's."
    ),
}

PAGES["kernlens-pagewalk"] = {
    "title": "Pagewalk (pwndbg format)",
    "intro": (
        "The same walk as `kl-walk`, printed in pwndbg's `pagewalk` "
        "layout: leaf first, root last."
    ),
    "sections": [
        {
            "heading": "The pwndbg layout",
            "invocation": "kernlens-pagewalk {direct}",
            "reading": (
                "The order is reversed relative to `kl-walk` -- the leaf is "
                "printed first -- because that is what pwndbg's command "
                "does and scripts may parse it.  Each row shows the level, "
                "the entry's address, the index in brackets, the raw value, "
                "the decoded flags, and the next table.  The final line is "
                "the translated address, or the physical address when the "
                "walk reached a leaf."
            ),
        },
    ],
    "notes": (
        "Kept alongside `kl-walk` deliberately: `kl-walk` is the KernLens "
        "view (root-down, with the failure reason inline), and this is the "
        "pwndbg-compatible one.  Neither is redundant for a user who has "
        "pwndbg muscle memory."
    ),
}

PAGES["kernlens-pte"] = {
    "title": "Decode a page-table entry",
    "intro": (
        "Takes one page-table entry's raw value and decodes the flag bits "
        "and the physical address it encodes.  No memory is read: the "
        "value is the argument."
    ),
    "sections": [
        {
            "heading": "Flags and physical address",
            "invocation": "kernlens-pte 0x8000000000120063",
            "reading": (
                "`present=True` comes from bit 0.  The flag list names each "
                "set bit: `P` present, `RW` writable, `US` user, `A` "
                "accessed, `D` dirty, `PS` page-size (huge), `NX` "
                "no-execute.  `bit7=PS/PAT` is called out separately "
                "because bit 7 means page-size at the PMD level and "
                "PAT elsewhere; only the level resolves it, so the command "
                "reports the ambiguity rather than picking one."
            ),
        },
        {
            "heading": "With an address for context",
            "invocation": "kernlens-pte 0x8000000000120063 {direct}",
            "reading": (
                "Giving the address lets the command label the three leaf "
                "interpretations of the same bits: what the value would "
                "mean as a 4 KiB, 2 MiB or 1 GiB leaf.  This is how a "
                "rounding mistake becomes obvious -- the same entry reads "
                "differently at each level."
            ),
        },
    ],
    "notes": (
        "Removing the low 12 bits gives the physical page frame; the `NX` "
        "bit is the top bit of the 64-bit value, which is why the entry "
        "starts with `0x8`."
    ),
}

PAGES["kernlens-page"] = {
    "title": "Page for an address",
    "intro": (
        "Classifies an address and, for a direct-map address, prints the "
        "physical address, pfn and the `struct page` that describes it in "
        "one place."
    ),
    "sections": [
        {
            "heading": "The default view",
            "invocation": "kernlens-page {direct}",
            "reading": (
                "`Class` is the region set from `kl-addr`.  `Physical` and "
                "`page` follow from the direct map and the vmemmap, both of "
                "which are printed as `bases:` so the arithmetic can be "
                "checked by hand: `page = vmemmap + pfn * sizeof(struct "
                "page)`."
            ),
        },
        {
            "heading": "Verbose",
            "invocation": "kernlens-page {direct} -v",
            "reading": (
                "`-v` adds the full `kl-addr` block -- canonicality, the "
                "`ERR_PTR` check, and the alignment pair -- before the same "
                "translation.  It is the 'explain this address completely' "
                "form."
            ),
        },
    ],
    "notes": (
        "`sizeof(struct page)` is read from the debug info (64 bytes "
        "here), never assumed: it changes with `CONFIG_*` options, and "
        "using `PAGE_SIZE` instead is a classic error that produces "
        "`struct page` pointers 64x too far apart."
    ),
}

PAGES["kernlens-pageinfo"] = {
    "title": "Describe a struct page",
    "intro": (
        "The reverse direction: given a `struct page` pointer, prints the "
        "virtual address it backs, the physical address, the pfn, and what "
        "the page currently is."
    ),
    "sections": [
        {
            "heading": "From struct page to address",
            "invocation": "kernlens-pageinfo {vmemmap_page}",
            "reading": (
                "`type: buddy` is the most useful field: it says the page "
                "is on a buddy free list, which is what you expect for a "
                "free page.  `refcount: 0` agrees.  On a 6.1 kernel the "
                "type comes from the `PG_buddy` flag, since the `page_type` "
                "ordinals used by 6.12+ do not exist yet -- the probe "
                "decides which encoding applies by asking whether "
                "`enum pageflags` still defines `PG_slab`."
            ),
        },
    ],
    "notes": (
        "A page that is allocated but not on any list reports a type of "
        "`unknown` or `initialized`; that is not a failure, it is the "
        "absence of a type tag.  Use `kl-slab details` for a page that is "
        "a slab."
    ),
}

PAGES["kernlens-p2v"] = {
    "title": "Physical to virtual",
    "intro": (
        "Translates a physical address to its direct-map virtual address "
        "and prints the `struct page` and type, the same three facts as "
        "`kl-pageinfo`."
    ),
    "sections": [
        {
            "heading": "A free page",
            "invocation": "kernlens-p2v 0x400000",
            "reading": (
                "`Virtual` is `page_offset_base + phys` exactly, because "
                "that is what the direct map is.  The `struct page` and "
                "`type: buddy` rows come from the vmemmap, and agree with "
                "`kl-v2p` and `kl-pageinfo` for the same page -- running "
                "all three is a good way to confirm the two bases are "
                "right."
            ),
        },
    ],
    "notes": (
        "No page tables are walked: the direct map is a constant offset, "
        "so this works even for a physical address with no valid virtual "
        "mapping of its own."
    ),
}

PAGES["kernlens-v2p"] = {
    "title": "Virtual to physical",
    "intro": (
        "Translates a virtual address to physical by consulting the live "
        "page tables, falling back to the direct-map arithmetic when the "
        "address is in the direct map."
    ),
    "sections": [
        {
            "heading": "A direct-map address",
            "invocation": "kernlens-v2p {direct}",
            "reading": (
                "The result matches `kl-p2v 0x400000` in reverse, which is "
                "the check that matters.  Because a direct-map address's "
                "translation is exactly `virt - page_offset_base`, agreement "
                "here means the base is correct; disagreement means the "
                "slide or the base is wrong, not that the tables are."
            ),
        },
    ],
    "notes": (
        "For an address outside the direct map this must walk the tables, "
        "so it fails where `kl-p2v` cannot: an unmapped page has no "
        "physical address even though the arithmetic would produce one."
    ),
}

# --------------------------------------------------------------------
# memory and symbols
# --------------------------------------------------------------------

PAGES["kernlens-sym"] = {
    "title": "Address to symbol",
    "intro": (
        "Resolves an address to the symbol that covers it and its source "
        "location, using the loaded debug info.  Equivalent to GDB's "
        "`info symbol` but KASLR-aware."
    ),
    "sections": [
        {
            "heading": "A text address",
            "invocation": "kernlens-sym {text_sym}",
            "reading": (
                "The symbol, its section, and `file:line` -- the line comes "
                "from DWARF, so it is exact for this build.  The address "
                "printed first is the one that was queried, unchanged."
            ),
        },
        {
            "heading": "A data address",
            "invocation": "kernlens-sym {direct}",
            "reading": (
                "`?? at ??` means nothing covers the address.  For a "
                "direct-map address that is the correct answer -- the direct "
                "map is not a symbol, it is a mapping -- and it is worth "
                "seeing so you do not mistake it for a broken symbol table."
            ),
        },
    ],
    "notes": (
        "GDB's symbol table is link-time.  KernLens subtracts the slide "
        "before asking GDB, which is why this resolves on a KASLR kernel "
        "where a plain `info symbol` would miss."
    ),
}

PAGES["kernlens-bt"] = {
    "title": "Backtrace",
    "intro": (
        "A kernel-aware backtrace: each frame's return address resolved to "
        "a symbol and source line, with the noise of the interrupted "
        "context handled."
    ),
    "sections": [
        {
            "heading": "The whole stack",
            "invocation": "kernlens-bt",
            "reading": (
                "Frames are printed `#N address symbol at file:line`.  "
                "Frames 1 and 2 being the same symbol "
                "(`default_idle`) is normal in an idle stack: the compiler "
                "emitted inlined copies, and both map back to the same "
                "out-of-line body.  The stack ends in the idle loop, which "
                "tells you the CPU is not running anything interesting."
            ),
        },
        {
            "heading": "Limiting the depth",
            "invocation": "kernlens-bt 4",
            "reading": (
                "A depth limit keeps the output readable on a deep stack.  "
                "The inner frames are the same, so the limit is applied "
                "from the innermost frame outward, not by truncating the "
                "printed text."
            ),
        },
    ],
    "notes": (
        "`--chain` switches to the one-line form, which is what "
        "`kl-chain` prints.  A frame showing `??` is one where the return "
        "address did not resolve -- often a stack-corruption artefact, and "
        "worth noting rather than hiding."
    ),
}

PAGES["kernlens-chain"] = {
    "title": "Compact call chain",
    "intro": (
        "The same stack as `kl-bt` collapsed to one line of "
        "`caller <- callee`, for pasting into a report."
    ),
    "sections": [
        {
            "heading": "The chain",
            "invocation": "kernlens-chain",
            "reading": (
                "Innermost first, joined by `<-`.  Only symbol names "
                "appear -- no addresses, no source lines -- which is what "
                "makes it fit on one line.  Repeated inlined symbols are "
                "kept rather than deduplicated, because collapsing them "
                "would misrepresent the depth."
            ),
        },
        {
            "heading": "A longer chain",
            "invocation": "kernlens-chain 12",
            "reading": (
                "The optional argument is a depth.  `init_thread_union` "
                "appearing between frames is a known artefact of the "
                "kernel's stack layout, not a bad unwind."
            ),
        },
    ],
    "notes": (
        "For anything where the addresses matter, use `kl-bt`: this form "
        "deliberately drops them."
    ),
}

PAGES["kernlens-read"] = {
    "title": "Dump memory",
    "intro": (
        "Reads memory as 64-bit words with a symbol annotation per word, "
        "or as a hex+ASCII dump.  The counterpart of pwndbg's `x` for "
        "kernel memory."
    ),
    "sections": [
        {
            "heading": "Words",
            "invocation": "kernlens-read {direct}",
            "reading": (
                "Each row is `address: value symbol`.  The values here are "
                "the contents of a free page, so they are leftover data -- "
                "an uninitialised page keeps whatever was there before, "
                "which is precisely why `CONFIG_INIT_ON_ALLOC_DEFAULT_ON` "
                "exists.  The `??` annotations mean no symbol covers the "
                "value, which is correct for a data word."
            ),
        },
        {
            "heading": "Hex and ASCII",
            "invocation": "kernlens-read {direct} 16 -m ascii",
            "reading": (
                "`-m ascii` switches to the `hexdump -C` style: eight "
                "bytes of hex, then the printable rendering, with "
                "non-printable bytes as `.`.  The byte count is the second "
                "positional, so `16` means two rows of eight."
            ),
        },
    ],
    "notes": (
        "An unreadable address is reported per row instead of aborting, so "
        "a partially valid range still yields data.  The word size follows "
        "the 64-bit model: KernLens is x86_64-only."
    ),
}

PAGES["kernlens-kvar"] = {
    "title": "Read a kernel variable",
    "intro": (
        "Reads a named kernel global, applying the KASLR slide and "
        "re-deriving it if the read fails.  This is the command for "
        "`page_offset_base` and friends, where `&symbol` under KASLR reads "
        "nothing useful."
    ),
    "sections": [
        {
            "heading": "A base variable",
            "invocation": "kernlens-kvar page_offset_base",
            "reading": (
                "Three rows: the symbol name, the runtime address it lives "
                "at, and its value.  The distinction is the whole point -- "
                "the address is in `.data` near `_text`, while the value is "
                "a direct-map base far away.  Both are KASLR-shifted, and "
                "KernLens re-derives the slide once if the first read "
                "returns nothing."
            ),
        },
        {
            "heading": "A numeric variable",
            "invocation": "kernlens-kvar nr_online_nodes",
            "reading": (
                "For an `int` the value is read at its natural width, not "
                "as eight bytes: reading a 4-byte variable as 8 bytes picks "
                "up the neighbouring field and produces a large, "
                "plausible-looking wrong number."
            ),
        },
    ],
    "notes": (
        "Anonymous symbols (`static` functions, some kallsyms entries) have "
        "no `&`-expressible symbol, so a read through the symbol name fails "
        "even though the address exists.  That is a DWARF limitation, and "
        "the command reports it rather than returning zero."
    ),
}

PAGES["kernlens-read-field"] = {
    "title": "Read a struct field",
    "intro": (
        "Reads one field out of a struct at a given address, following a "
        "dotted path into nested members.  This is the command to use when "
        "you can compute an address but not read the struct in one go."
    ),
    "sections": [
        {
            "heading": "A nested path",
            "invocation": (
                "kernlens-read-field {vmemmap_page} 'struct page' "
                "_refcount.counter"
            ),
            "reading": (
                "The `field:` row echoes the exact expression that was "
                "evaluated, so the path can be checked against the debug "
                "info.  `_refcount` is a nested `{ counter }` struct on this "
                "kernel, which is why the path has two components: asking "
                "for `_refcount` alone would try to print a struct as an "
                "integer."
            ),
        },
    ],
    "notes": (
        "The type name is quoted so the shell (and GDB's own argument "
        "lexer) keeps `struct page` together.  A field that cannot be read "
        "prints `<unreadable>` rather than `0`, because a zero refcount and "
        "an unreadable one mean very different things."
    ),
}

# --------------------------------------------------------------------
# memory and symbols (allocator)
# --------------------------------------------------------------------

PAGES["kernlens-slab"] = {
    "title": "SLUB cache inspection",
    "intro": (
        "Inspects the SLUB allocator at three levels: the caches the kernel "
        "has, one cache's shape and per-CPU state, and one object's slab.  "
        "The subcommand form (`list`/`info`/`contains`/`details`) is "
        "pwndbg's; a bare address still works for compatibility."
    ),
    "sections": [
        {
            "heading": "Every cache",
            "invocation": "kernlens-slab list",
            "output_lines": 20,
            "reading": (
                "One row per cache: name, object count, pages per slab "
                "(`Size`), object size, and the order the slab is allocated "
                "at.  `Size` and `Obj Size` differ when the cache rounds up "
                "for alignment or adds metadata -- that gap is the per-object "
                "overhead an amplification attack cares about."
            ),
        },
        {
            "heading": "Filtering caches",
            "invocation": "kernlens-slab list kmalloc",
            "output_lines": 20,
            "reading": (
                "A filter is a substring match, so `kmalloc` catches all "
                "three families: `dma-kmalloc-*` (DMA-capable), "
                "`kmalloc-rcl-*` (reclaimable), and plain `kmalloc-*`.  The "
                "trailing `of N cache(s) shown` line is what tells you the "
                "list was filtered rather than short."
            ),
        },
        {
            "heading": "One cache in full",
            "invocation": "kernlens-slab info dentry",
            "reading": (
                "`Offset` is the freelist pointer's offset inside the "
                "object; `Size (including metadata)` is the stride the "
                "allocator actually uses.  `Slab size` is the page-order "
                "size of one slab (`PAGE_SIZE << oo_order`).  The usercopy "
                "window is the range the hardened usercopy checks allow: "
                "`dentry` has a real window (56/32), while a plain kmalloc "
                "cache stores the whole object and reports "
                "`usersize == object_size`.  The per-CPU rows are the live "
                "`kmem_cache_cpu` state, and the node row is the partial "
                "list's length against `min_partial`."
            ),
        },
        {
            "heading": "Cache internals",
            "invocation": "kernlens-slab info dentry -i -r --reclaim --ctor",
            "reading": (
                "Four opt-in rows, none of which changes the default output: "
                "`inuse` is the object stride including metadata, `random` is "
                "the freelist randomisation key (`CONFIG_SLAB_FREELIST_RANDOM`), "
                "`reclaim` says whether `SLAB_RECLAIM_ACCOUNT` is set, and "
                "`ctor` names the constructor (or `none`).  These are "
                "KernLens-only additions: the shared `info` block must stay "
                "byte-identical to pwndbg's."
            ),
        },
        {
            "heading": "Partial slabs only",
            "invocation": "kernlens-slab info dentry -p",
            "reading": (
                "Restricts the per-CPU rows and shows the node's partial "
                "list head instead.  `nr_partial=0x17/ min_partial=0x5` is "
                "the current length against the watermark the kernel keeps "
                "before it starts freeing empty slabs; `min_partial` lives in "
                "`struct kmem_cache` (not the node), which is why it is "
                "reported as the same value for every node.  It is "
                "`max(MIN_PARTIAL, ilog2(object_size)/2)`."
            ),
        },
        {
            "heading": "Active slabs only",
            "invocation": "kernlens-slab info dentry -a",
            "reading": (
                "Just the per-CPU active slab and freelist.  `active` is a "
                "`struct page` pointer; `freelist` is the next free object in "
                "that slab.  Both can legitimately be empty on an idle CPU."
            ),
        },
        {
            "heading": "Which cache owns an object",
            "invocation": "kernlens-slab contains {slab_object}",
            "reading": (
                "Given an object address, reports the cache it belongs to and "
                "the cache's object and slab sizes.  This is the fastest way "
                "to identify an unexplained heap pointer.  pwndbg's form is "
                "one line; `-v` adds the slab head, the object index within "
                "the slab, the slab's state, its counters, and the "
                "neighbouring objects."
            ),
        },
        {
            "heading": "One slab in detail",
            "invocation": "kernlens-slab details {slab_object}",
            "reading": (
                "`Slab @` is the `struct page` for the slab (the argument is "
                "an object inside it).  `freeptr: offset=96` is where the "
                "freelist pointer is stored inside each object, together with "
                "the randomisation key.  `objects: 21 inuse=21 frozen=1` "
                "decodes the packed counters word "
                "(`inuse:16 | objects:15 | frozen:1`); `state: frozen` is "
                "derived from `frozen`, not from list membership, because a "
                "frozen (per-CPU) slab is on no list at all.  "
                "`in_partial=False` agrees: this slab is CPU-owned, not on "
                "the node's partial list."
            ),
        },
    ],
    "notes": (
        "`kl-slab` merges what used to be two commands (`kernlens-slab` and "
        "`kernlens-slabs`), so `kl-slabs` still resolves as an alias.  The "
        "legacy `-d/--detail` flag and the bare-address form remain for "
        "scripts written against the older interface.  `kl-slab <addr>` is "
        "`contains`, not `details` -- the object first, the slab on request."
    ),
}

PAGES["kernlens-buddy"] = {
    "title": "Locate an address in the buddy allocator",
    "intro": (
        "Answers 'what is this page' for the page allocator: which zone it "
        "belongs to, whether it is free, and if so which free block it is "
        "part of and where inside that block."
    ),
    "sections": [
        {
            "heading": "Free blocks, per order",
            "invocation": "kernlens-buddy list",
            "reading": (
                "One row per non-empty order per zone.  `nr_free` is the "
                "kernel's per-ORDER counter, so it counts *blocks* of "
                "`1 << order` pages, not pages; `pages(1<<order)` multiplies "
                "it out.  There is deliberately no migratetype column: "
                "`free_area.nr_free` is a single counter covering all "
                "migratetypes, and reading it at a migratetype stride reads "
                "the next `free_area`'s list pointers instead."
            ),
        },
        {
            "heading": "One zone",
            "invocation": "kernlens-buddy list -z DMA",
            "reading": (
                "Same table, filtered.  The DMA zone on this machine has no "
                "order-8 block, which the list shows by omission rather than "
                "by a zero row."
            ),
        },
        {
            "heading": "By pfn",
            "invocation": "kernlens-buddy info pfn:1024",
            "reading": (
                "`Zone` gives the containing span and the node; `Status: "
                "free` means the head page is on a buddy free list.  "
                "`Order: 10` says the containing block is 1024 pages, and "
                "`Position: 0 / 1024 pages (block head)` says this pfn is "
                "the block's own head.  `Own block head` answers the "
                "different question 'is this page itself the head of a "
                "block?', which is what you need before touching "
                "`page->private`."
            ),
        },
        {
            "heading": "By virtual address",
            "invocation": "kernlens-buddy info {direct}",
            "reading": (
                "A direct-map address is translated exactly once and gives "
                "the same answer as `pfn:1024`.  `virt:`, `phys:`, `page:` "
                "and `pfn:` prefixes force one reading; a bare value is "
                "tried as vmemmap, then direct map, then physical, and the "
                "first plausible one wins.  The vmemmap range sits above "
                "`page_offset_base`, so the narrower interpretation must be "
                "tried first or a `struct page` pointer would be mistaken "
                "for a direct-map address."
            ),
        },
        {
            "heading": "Verbose",
            "invocation": "kernlens-buddy info pfn:1024 -v",
            "reading": (
                "Adds the block's span, its buddy, and the zone's page "
                "counts.  `Buddy: pfn=0x0 ... (or merged into a larger "
                "block)` is the honest answer for an order-10 block: its "
                "buddy is outside the zone, so nothing is there to merge "
                "with.  `spanned` counts what the zone covers and `present` "
                "what is actually backed by RAM; the gap is reserved holes."
            ),
        },
        {
            "heading": "One free list",
            "invocation": "kernlens-buddy freelist -z DMA -o 10 -m Movable",
            "reading": (
                "A per-migratetype view, which is what `list` cannot give: "
                "this walks the actual `free_list[mtype]`.  It needs all "
                "three of zone, order and migratetype, because a partial "
                "specification would silently pick one."
            ),
        },
        {
            "heading": "Free list contents",
            "invocation": "kernlens-buddy freelist -z DMA -o 10 -m Movable -v",
            "reading": (
                "Each block's pfn, physical address and direct-map alias.  "
                "`nr_free=3` matches the three blocks listed, which is the "
                "cross-check that per-order counts and per-type lists agree: "
                "the order-10 blocks are all Movable, and the other "
                "migratetypes hold none."
            ),
        },
        {
            "heading": "An empty list",
            "invocation": "kernlens-buddy freelist -z DMA -o 10 -m Unmovable -v",
            "reading": (
                "Empty is reported as empty, and the header still shows the "
                "per-order total so the relationship between the two "
                "commands stays visible: `nr_free=3` counts all migratetypes, "
                "while this particular list holds zero."
            ),
        },
    ],
    "notes": (
        "PCP (per-CPU page) lists are not covered yet: a page can be free in "
        "a PCP list without appearing here.  `--limit` caps the rows printed "
        "for very large zones."
    ),
}

PAGES["kernlens-buddydump"] = {
    "title": "Buddy free-list dump",
    "intro": (
        "pwndbg's `buddydump` view: every page on the free lists, in list "
        "order, with its `struct page` and physical address."
    ),
    "sections": [
        {
            "heading": "Every zone",
            "invocation": "kernlens-buddydump",
            "output_lines": 18,
            "reading": (
                "Each row is `[index] virtual [page: ptr, phys: addr]`.  The "
                "index is the position in the list, so consecutive blocks of "
                "the same order appear consecutively -- the physical "
                "addresses jump around after the first few because the lists "
                "interleave low-order blocks from across the zone."
            ),
        },
        {
            "heading": "One zone",
            "invocation": "kernlens-buddydump -z DMA",
            "reading": (
                "The DMA zone here is small and its blocks are the largest "
                "ones, so the first rows are the same order-10 and order-9 "
                "blocks `kl-buddy list` counts."
            ),
        },
        {
            "heading": "Searching for an address",
            "invocation": "kernlens-buddydump -f {direct}",
            "reading": (
                "`-f/--find` matches against the virtual address, the "
                "physical address, or the `struct page`, so any of the three "
                "forms identifies the block.  It accepts hex, which matters "
                "because the value is an address."
            ),
        },
        {
            "heading": "The migratetype count",
            "invocation": "kernlens-buddydump --MIGRATE_TYPES 5",
            "reading": (
                "`--MIGRATE_TYPES` overrides the discovered count.  It exists "
                "for images whose `migratetype_names` symbol is missing; "
                "getting it wrong misplaces every list after the first, so "
                "the command normally reads the array instead of guessing."
            ),
        },
    ],
    "notes": (
        "Overlaps `kl-buddy` on purpose: this is the pwndbg layout, "
        "`kl-buddy` is the KernLens one with the per-order totals.  Use "
        "`kl-buddy list` for counts and this for the individual blocks."
    ),
}

PAGES["kernlens-kbpf"] = {
    "title": "BPF programs and maps",
    "intro": (
        "Walks the BPF object lists and prints each program and map.  "
        "Root-only in a normal kernel, but readable through a debugger "
        "regardless of credentials."
    ),
    "sections": [
        {
            "heading": "The default view",
            "invocation": "kernlens-kbpf",
            "reading": (
                "Two summary lines when nothing is loaded.  The counts come "
                "from the `prog_idr`/`map_idr` IDR structures, so they are "
                "the kernel's own totals."
            ),
        },
        {
            "heading": "Programs only",
            "invocation": "kernlens-kbpf -p",
            "reading": (
                "`-p` restricts the output to programs, which is what you "
                "want when looking for a hook: each row carries the program "
                "type, its `bpf_func` entry point, and the map it uses."
            ),
        },
        {
            "heading": "Maps only",
            "invocation": "kernlens-kbpf -m",
            "reading": (
                "`-m` restricts to maps.  `--values` additionally dumps each "
                "map's contents, which is how a BPF-based keylogger or "
                "rootkit is spotted."
            ),
        },
    ],
    "notes": (
        "An empty list is a normal state for a minimal kernel, not a "
        "failure.  `-b N` prints the Nth program and sets a breakpoint at "
        "its `bpf_func`, which is the practical way to catch a program "
        "running."
    ),
}

PAGES["kernlens-kdmabuf"] = {
    "title": "dma-buf objects",
    "intro": (
        "Walks the dma-buf export list and prints each buffer with its "
        "attachment chain.  dma-bufs are a common cross-device "
        "use-after-free surface, so enumerating them is usually the first "
        "step."
    ),
    "sections": [
        {
            "heading": "The list",
            "invocation": "kernlens-kdmabuf",
            "reading": (
                "One row per exported buffer: size, the exporter's name, and "
                "the attachment count.  When there are none, the message "
                "names the two things it needs -- the list symbol and at "
                "least one exported buffer -- so an empty result is not "
                "confused with a broken symbol lookup."
            ),
        },
    ],
    "notes": (
        "The entry point is `db_list` (or `debugfs_list` on older kernels); "
        "which one exists is probed, not assumed."
    ),
}

# --------------------------------------------------------------------
# bit and integer primitives
# --------------------------------------------------------------------

PAGES["kernlens-bits"] = {
    "title": "Bit-level view",
    "intro": (
        "Shows a 64-bit value in binary and reports the bit statistics that "
        "come up in exploit work: population count, leading and trailing "
        "zeros, highest and lowest set bit, and whether the value is a power "
        "of two."
    ),
    "sections": [
        {
            "heading": "With a bit to test",
            "invocation": "kernlens-bits 0xff 3",
            "reading": (
                "The `value:` row pairs the hex form with a 64-bit binary "
                "rendering, so the bit positions can be counted directly.  "
                "`scan:` gives `popcount`, the leading and trailing zero "
                "counts (1-based `first_set`/`last_set`), and `power:` "
                "reports the floor and ceiling log2 -- equal values mean the "
                "number IS a power of two.  The final row tests, sets, "
                "clears and toggles the given bit, showing each result, so "
                "one invocation answers all four questions."
            ),
        },
        {
            "heading": "An address",
            "invocation": "kernlens-bits {text_addr}",
            "reading": (
                "`trailing_zeros=20` is the page offset of this address "
                "(2 MiB aligned), which is the kind of fact that jumps out "
                "of the binary rendering and is tedious to compute by hand.  "
                "`log2_ceil=64` on a value with the top bit set is correct, "
                "not a bug: the next power of two above it does not fit in "
                "64 bits."
            ),
        },
    ],
    "notes": (
        "The value is masked to 64 bits, so a negative input is read as its "
        "two's-complement form -- which is what you want when analysing a "
        "raw register."
    ),
}

PAGES["kernlens-int"] = {
    "title": "Integer view",
    "intro": (
        "Shows one value as signed and unsigned at 8/16/32/64 bits, reports "
        "which widths it fits in, and dumps its little- and big-endian byte "
        "layouts."
    ),
    "sections": [
        {
            "heading": "Default width",
            "invocation": "kernlens-int 0xff",
            "reading": (
                "`view:` gives the unsigned and signed readings plus "
                "`in_u`/`in_i`, which say whether the value fits the width "
                "as unsigned and as signed.  `range:` prints the full U64 and "
                "I64 bounds.  `LE bytes` and `BE bytes` are the same value in "
                "memory order and network order, which is the quickest way to "
                "spot a byte-order bug: on x86 the little-endian form is what "
                "a memory dump shows."
            ),
        },
        {
            "heading": "A specific width",
            "invocation": "kernlens-int 0x1234 16",
            "reading": (
                "The second argument restricts the analysis to that width, so "
                "the signed/unsigned split and the `range:` line describe "
                "16-bit integers rather than 64-bit ones."
            ),
        },
        {
            "heading": "A negative value",
            "invocation": "kernlens-int -1 32",
            "reading": (
                "A negative value is interpreted as two's complement and "
                "masked to the width, so `-1` at 32 bits is `0xffffffff`, "
                "unsigned `4294967295`, signed `-1`.  This is the case where "
                "the four views differ most, and the reason the command "
                "reports all of them instead of picking one."
            ),
        },
    ],
    "notes": (
        "Only 8, 16, 32 and 64 are accepted as widths; anything else is "
        "rejected with the list, because an arbitrary width would make the "
        "byte dumps ambiguous."
    ),
}
