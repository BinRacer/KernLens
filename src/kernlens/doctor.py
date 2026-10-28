#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
"""Host-side installation check: ``kernlens doctor``.

The first question a new user asks is "why did nothing happen?", and the
answer is almost always one of four things: GDB's embedded Python cannot
import the package, ``~/.gdbinit`` does not source the startup file, no
``vmlinux`` with debug info is loaded, or no target is attached.  Each of
those has a different fix, and guessing which one applies is what turns a
first run into an issue thread.

This module answers them from the host shell.  It imports nothing from
:mod:`kernlens.gdb`, so it runs under the system Python rather than
GDB's, and it probes GDB by running it in batch mode.  The report is
deliberately plain text: it is meant to be pasted into a bug report.

``python -m kernlens.doctor`` is the entry point; ``bin/kernlens`` in a
checkout and the installer both call it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .install import startup_path

#: Status words, ordered by severity so the exit code is easy to derive.
OK = "ok"
WARN = "warn"
FAIL = "fail"

#: Runs *command* and returns ``(exit status, combined output)``.
Runner = Callable[[Sequence[str]], "tuple[int, str]"]

#: Outcome of one probe.
@dataclass(frozen=True)
class Check:
    """One labelled result in the report."""

    name: str
    status: str
    detail: str


def run_command(
    command: Sequence[str],
    *,
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run *command*, returning its exit status and combined output.

    Never raises: a missing binary or a hung GDB is reported as a status
    and a message, because a doctor that crashes is worse than no doctor.

    ``PYTHONPATH`` and ``PYTHONHOME`` are dropped unless *env* is given.
    The checkout launcher exports ``PYTHONPATH`` so its own import works,
    but a probe that inherits it can prove only that the launcher works:
    ``import kernlens`` would succeed even when the startup file failed
    to load.  The check has to stand on the startup file alone.
    """
    if env is None:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def _gdb_version(text: str) -> str:
    """Pull the first line of ``gdb --version`` out of *text*."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "unknown"


def _probe_value(text: str, marker: str) -> str | None:
    """Return the value after ``marker=`` on its own line, if present."""
    for line in text.splitlines():
        if line.startswith(marker + "="):
            return line.split("=", 1)[1].strip()
    return None


def check_python(
    *,
    python: Sequence[int] = tuple(sys.version_info[:3]),
) -> Check:
    """The host interpreter has to be at least Python 3.10."""
    text = ".".join(str(part) for part in python)
    if tuple(python) >= (3, 10):
        return Check("python", OK, f"{text} (>= 3.10)")
    return Check(
        "python", FAIL,
        f"{text} is older than 3.10; KernLens will not import",
    )


def check_package(
    *, package_file: str = __file__,
) -> Check:
    """Report the version and the location that ``import kernlens`` found."""
    path = Path(package_file).resolve()
    return Check("package", OK, f"kernlens {__version__} at {path.parent}")


def check_gdb(*, which: Callable[[str], str | None] = shutil.which,
              runner: Runner = run_command) -> Check:
    """Find GDB and read its version."""
    path = which("gdb")
    if path is None:
        return Check(
            "gdb", FAIL,
            "no gdb on PATH; install it (e.g. apt install gdb)",
        )
    status, output = runner([path, "--version"])
    version = _gdb_version(output) if status == 0 else "version unreadable"
    return Check("gdb", OK if status == 0 else WARN, f"{version} ({path})")


def check_gdb_python(gdb: str, *, runner: Runner = run_command) -> Check:
    """Ask GDB which Python it embeds.

    This is the version that runs KernLens, and it is often older than
    the interpreter the user installed the package with.
    """
    marker = "KLPY"
    status, output = runner([
        gdb, "--batch", "-nx",
        "-ex", f"python print('{marker}=' + '.'.join("
               "str(part) for part in sys.version_info[:3]))",
    ])
    value = _probe_value(output, marker)
    if status != 0 or value is None:
        return Check(
            "gdb-python", WARN,
            "GDB could not run Python; it may be built without Python "
            "support",
        )
    if tuple(int(part) for part in value.split(".")) < (3, 10):
        return Check(
            "gdb-python", FAIL,
            f"{value} is older than 3.10; KernLens needs 3.10+ inside GDB",
        )
    return Check("gdb-python", OK, value)


def find_source_line(rc: Path) -> Path | None:
    """Return the startup file *rc* sources, or ``None``.

    Only a ``source`` line naming ``gdbinit.py`` counts.  Relative paths
    are resolved against the directory holding *rc*, which is how GDB
    reads them.
    """
    try:
        text = rc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found: Path | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or not line.startswith("source"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        target = parts[1].strip().strip("\"'")
        if not target.endswith("gdbinit.py"):
            continue
        candidate = Path(target).expanduser()
        if not candidate.is_absolute():
            candidate = rc.parent / candidate
        found = candidate
    return found


def default_startup() -> Path:
    """The startup file shipped with this copy of KernLens."""
    return startup_path()


def check_gdbinit(rc: Path, *, startup: Path | None = None) -> Check:
    """Does *rc* source an existing KernLens startup file?"""
    sourced = find_source_line(rc)
    if sourced is None:
        target = startup if startup is not None else default_startup()
        return Check(
            "gdbinit", WARN,
            f"{rc} does not source KernLens; add: "
            f"source {target}",
        )
    if not sourced.is_file():
        return Check(
            "gdbinit", FAIL,
            f"{rc} sources {sourced}, which does not exist",
        )
    return Check("gdbinit", OK, f"{rc} sources {sourced}")


def check_gdb_load(
    gdb: str,
    startup: Path,
    *,
    runner: Runner = run_command,
) -> Check:
    """Source the startup file in a real GDB and import ``kernlens``.

    This is the only check that proves the whole load path: GDB's Python
    version, the package search path, and the startup file all at once.
    """
    if not startup.is_file():
        return Check("gdb-load", FAIL, f"startup file not found: {startup}")
    marker = "KLVER"
    status, output = runner([
        gdb, "--batch", "-nx",
        # Unquoted on purpose: GDB's ``source`` treats the rest of the
        # line as the filename and does not strip quotes.
        "-ex", f"source {startup}",
        "-ex", f"python import kernlens; print('{marker}=' + kernlens.__version__)",
    ])
    value = _probe_value(output, marker)
    if status == 0 and value is not None:
        return Check("gdb-load", OK, f"kernlens {value} loaded inside GDB")
    detail = output.splitlines()[-1] if output else "no output"
    return Check(
        "gdb-load", FAIL,
        f"GDB could not load {startup}: {detail}",
    )


def check_vmlinux(path: Path | None) -> Check:
    """Check the optional ``--vmlinux`` argument looks like an ELF file."""
    if path is None:
        return Check(
            "vmlinux", WARN,
            "not given; pass --vmlinux /path/to/vmlinux to check it",
        )
    if not path.is_file():
        return Check("vmlinux", FAIL, f"{path} does not exist")
    try:
        magic = path.read_bytes()[:4]
    except OSError as exc:
        return Check("vmlinux", FAIL, f"{path} is unreadable: {exc}")
    if magic != b"\x7fELF":
        return Check("vmlinux", FAIL, f"{path} is not an ELF file")
    return Check(
        "vmlinux", OK,
        f"{path} ({path.stat().st_size / (1024 * 1024):.1f} MiB); "
        "DWARF is confirmed when GDB loads it",
    )


def check_btf(path: Path) -> Check:
    """BTF is the fallback when the image has no DWARF."""
    if path.is_file():
        return Check("btf", OK, f"{path} (fallback layouts available)")
    return Check(
        "btf", WARN,
        f"{path} is absent; load a vmlinux with DWARF for exact layouts",
    )


def check_target(*, connected: bool | None = None) -> Check:
    """A target cannot be probed from the host; state what is needed."""
    if connected is True:
        return Check("target", OK, "attached")
    return Check(
        "target", WARN,
        "not checked; attach with: target remote :1234, then kl-base",
    )


def collect(
    options: argparse.Namespace,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Runner = run_command,
    python: Sequence[int] = tuple(sys.version_info[:3]),
    package_file: str = __file__,
) -> list[Check]:
    """Run every probe and return the report rows in display order."""
    checks = [
        check_python(python=python),
        check_package(package_file=package_file),
    ]
    gdb = check_gdb(which=which, runner=runner)
    checks.append(gdb)
    gdb_path = which("gdb")
    if gdb_path is not None:
        python_check = check_gdb_python(gdb_path, runner=runner)
        checks.append(python_check)
        if python_check.status != FAIL:
            rc = Path(options.gdbinit).expanduser()
            startup = find_source_line(rc)
            if startup is None:
                startup = (
                    Path(options.startup).expanduser()
                    if options.startup
                    else default_startup()
                )
            checks.append(check_gdb_load(gdb_path, startup, runner=runner))
    checks.append(check_gdbinit(
        Path(options.gdbinit).expanduser(),
        startup=Path(options.startup).expanduser() if options.startup else None,
    ))
    checks.append(check_vmlinux(
        Path(options.vmlinux).expanduser() if options.vmlinux else None,
    ))
    checks.append(check_btf(Path(options.btf).expanduser()))
    checks.append(check_target())
    return checks


def render(checks: Sequence[Check]) -> str:
    """Format the report as plain text, one probe per line."""
    width = max(len(check.name) for check in checks)
    lines = ["KernLens doctor", ""]
    for check in checks:
        lines.append(
            f"  {check.status:<4}  {check.name:<{width}}  {check.detail}"
        )
    failures = [check for check in checks if check.status == FAIL]
    warnings = [check for check in checks if check.status == WARN]
    lines.append("")
    if failures:
        lines.append(
            f"{len(failures)} check(s) failed; fix those before running "
            "KernLens."
        )
    elif warnings:
        lines.append(
            f"{len(warnings)} warning(s); the report above says what each "
            "one needs."
        )
    else:
        lines.append("All checks passed.")
    lines.append(
        "Next: gdb -q -ex 'file vmlinux' -ex 'target remote :1234' "
        "-ex kl-base"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(
        prog="kernlens doctor",
        description=(
            "Check that this machine can load KernLens inside GDB. "
            "Run it when a command is missing or refuses to start."
        ),
    )
    parser.add_argument(
        "--gdbinit", default=str(Path.home() / ".gdbinit"),
        help="GDB startup file to inspect (default: ~/.gdbinit)",
    )
    parser.add_argument(
        "--startup", default=None,
        help="KernLens startup file to load when --gdbinit names none",
    )
    parser.add_argument(
        "--vmlinux", default=None,
        help="kernel image to check for debug info",
    )
    parser.add_argument(
        "--btf", default="/sys/kernel/btf/vmlinux",
        help="BTF blob to check (default: /sys/kernel/btf/vmlinux)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checks and print the report; 1 when a check failed."""
    options = build_parser().parse_args(argv)
    checks = collect(options)
    print(render(checks))
    return 1 if any(check.status == FAIL for check in checks) else 0


if __name__ == "__main__":  # pragma: no cover - exercised as a script
    raise SystemExit(main())
