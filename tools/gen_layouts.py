#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
"""Generate and verify the fallback struct layouts in ``kernlens.gdb.layouts``.

The inspectors resolve every struct field offset from the loaded debug
info; the table in :mod:`kernlens.gdb.layouts` is only the fallback for a
build with no debug info at all.  That table must therefore be *exact*
for the kernels it claims, and this tool keeps it honest:

* it probes a real kernel -- ``--vmlinux`` through GDB's DWARF, or
  ``--btf`` through the project's own BTF parser (no ``bpftool``
  dependency, so it also works on a runner whose ``bpftool`` is the
  Ubuntu wrapper script that refuses to run) -- for every struct/field
  the registry declares, and
* with ``--check`` it compares the probe against the registry and exits
  non-zero on any disagreement, so CI can catch a table that drifted
  from the kernel it was verified against.

Without ``--check`` it prints a ready-to-paste ``StructVariant`` block for
a newly verified kernel.  The pure helpers (:func:`build_spec`,
:func:`compare`, :func:`render`) are unit-tested; only the two
``probe_*`` wrappers touch an external process / file.

Usage::

    tools/gen_layouts.py --vmlinux /path/to/vmlinux          # report
    tools/gen_layouts.py --vmlinux /path/to/vmlinux --check  # CI guard
    tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux       # host kernel
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from kernlens.gdb import btf, layouts  # noqa: E402

#: Line printed before the JSON payload so surrounding GDB noise is ignored.
_MARKER = "@@KERNLENS_JSON@@"

#: GDB batch payload.  ``%``-formatting keeps the many braces out of
#: :meth:`str.format`; the two tokens are substituted by :func:`probe_gdb`.
_GDB_PROBE = """\
import gdb
import json

SPEC = json.loads(__SPEC__)

report = {}
for type_name, paths in SPEC.items():
    entry = {"fields": {}}
    try:
        entry["sizeof"] = int(gdb.parse_and_eval("sizeof(%s)" % type_name))
    except Exception:
        pass
    for path in paths:
        try:
            expr = "(unsigned long)&((%s *)0)->%s" % (type_name, path)
            entry["fields"][path] = int(gdb.parse_and_eval(expr))
        except Exception:
            continue
    report[type_name] = entry

print("__MARKER__")
print(json.dumps(report))
"""

# ---------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------

def build_spec() -> dict[str, list[str]]:
    """Return ``{type_name: [field paths]}`` for every registry entry."""
    spec: dict[str, list[str]] = {}
    for entry in layouts.entries():
        paths = sorted({path for v in entry.variants for path in v.fields})
        spec[entry.type_name] = paths
    return spec


def compare(
    report: dict[str, Any],
    version: layouts.Version | None = None,
    config: dict[str, str] | None = None,
) -> list[str]:
    """Return a human-readable diff between *report* and the registry.

    Each string is ``"<location>: registry <a> != actual <b>"``; an empty
    list means the registry still matches the probed kernel for every
    struct it declares.  A struct the registry declares but the probe did
    not return is itself a difference, so an incomplete probe can never
    pass silently.
    """
    diffs: list[str] = []
    for layout in layouts.entries():
        type_name = layout.type_name
        entry = report.get(type_name)
        if entry is None:
            diffs.append(f"{type_name}: not found in the probed kernel")
            continue
        for path in sorted(
            {path for v in layout.variants for path in v.fields}
        ):
            if path not in entry.get("fields", {}):
                diffs.append(f"{type_name}.{path}: not found in the probe")
                continue
            expected = layouts.offset(type_name, path, version, config)
            actual = entry["fields"][path]
            if expected is not None and expected != actual:
                diffs.append(
                    f"{type_name}.{path}: registry {expected:#x} "
                    f"!= actual {actual:#x}"
                )
        size = entry.get("sizeof")
        expected_size = layouts.sizeof(type_name, version, config)
        if (
            expected_size is not None
            and size is not None
            and expected_size != size
        ):
            diffs.append(
                f"sizeof({type_name}): registry {expected_size:#x} "
                f"!= actual {size:#x}"
            )
    return diffs


def render(report: dict[str, Any]) -> str:
    """Render *report* as a ``StructVariant`` body ready to paste."""
    lines: list[str] = []
    for type_name in sorted(report):
        entry = report[type_name]
        lines.append(f"# {type_name}")
        if entry.get("sizeof") is not None:
            lines.append(f"#     sizeof = {entry['sizeof']:#x}")
        for path, value in sorted(entry.get("fields", {}).items()):
            lines.append(f"    {path!r}: {value:#x},")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Probes (shell out)
# ---------------------------------------------------------------------

def probe_gdb(vmlinux: str) -> dict[str, Any]:
    """Probe *vmlinux* through GDB's DWARF; raise on failure."""
    spec = json.dumps(build_spec())
    script = _GDB_PROBE.replace("__SPEC__", repr(spec)).replace(
        "__MARKER__", _MARKER,
    )
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8",
    )
    try:
        handle.write(script)
        handle.close()
        result = subprocess.run(
            [
                "gdb", "-batch", "-nx", "-q",
                "-ex", f"file {vmlinux}",
                "-ex", f"source {handle.name}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        os.unlink(handle.name)
    return _extract(result.stdout, result.stderr, vmlinux)


def probe_btf(btf_path: str) -> dict[str, Any]:
    """Probe a BTF blob using the project's own parser.

    The parser is self-contained, so this needs neither ``bpftool`` nor
    ``libbpf``.  That matters on CI: the Ubuntu ``bpftool`` package
    installs a *wrapper* that dispatches to a per-kernel tools package
    and fails on a cloud runner, where no matching package exists.
    """
    data = Path(btf_path).read_bytes()
    blob = btf.extract_btf(data) or data
    database = btf.parse(blob)
    if database is None:
        raise RuntimeError(f"no usable BTF in {btf_path}")
    spec = build_spec()
    report: dict[str, Any] = {}
    for type_name, paths in spec.items():
        if not database.has(type_name):
            continue
        entry: dict[str, Any] = {"fields": {}}
        size = database.sizeof(type_name)
        if size is not None:
            entry["sizeof"] = size
        for path in paths:
            value = database.offset(type_name, path)
            if value is not None:
                entry["fields"][path] = value
        report[type_name] = entry
    return report


def _extract(stdout: str, stderr: str, source: str) -> dict[str, Any]:
    """Pull the JSON payload out of GDB's mixed output."""
    index = stdout.find(_MARKER)
    if index < 0:
        raise RuntimeError(
            f"gdb produced no layout report for {source}:\n"
            f"{stderr.strip() or stdout.strip()}"
        )
    payload = stdout[index + len(_MARKER):].strip().splitlines()
    if not payload:
        raise RuntimeError(f"empty layout report for {source}")
    return json.loads(payload[0])


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe a real kernel for the struct layouts the fallback "
            "registry declares, and optionally verify the registry."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--vmlinux", metavar="PATH",
        help="a vmlinux with DWARF debug info (read through GDB)",
    )
    source.add_argument(
        "--btf", metavar="PATH",
        help=(
            "a BTF blob such as /sys/kernel/btf/vmlinux or a vmlinux "
            "with an embedded .BTF section (parsed directly)"
        ),
    )
    parser.add_argument(
        "--check", action="store_true",
        help="compare against the registry and exit non-zero on a mismatch",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the raw probe report as JSON",
    )
    parser.add_argument(
        "--config", metavar="FILE",
        help="a .config file used to select CONFIG-gated registry variants",
    )
    parser.add_argument(
        "--version", metavar="X.Y.Z",
        help="kernel version used to select version-gated registry variants",
    )
    return parser.parse_args(argv)


def _load_config(path: str | None) -> dict[str, str] | None:
    if path is None:
        return None
    config: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("CONFIG_") and "=" in line:
            name, _, value = line.partition("=")
            config[name] = value
    return config


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.vmlinux:
            report = probe_gdb(args.vmlinux)
        else:
            report = probe_btf(args.btf)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    version = (
        layouts.parse_version(f"Linux version {args.version}")
        if args.version else None
    )
    config = _load_config(args.config)

    if args.check:
        diffs = compare(report, version, config)
        if diffs:
            print("fallback registry does not match the probed kernel:")
            for diff in diffs:
                print(f"  {diff}")
            return 1
        print("fallback registry matches the probed kernel")
        return 0

    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())