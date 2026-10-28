"""The ``kernlens`` console script.

Four host-side commands, none of which imports ``kernlens.gdb``:

``path``
    print the startup file to source from ``~/.gdbinit``;
``install``
    write (or remove) the marked block that sources it;
``doctor``
    check that this machine can load KernLens inside GDB;
``version``
    print the installed version.

With no argument the script runs ``doctor``, which is what a user who has
just installed something needs most.  Flags with no subcommand are passed
to ``doctor`` as well, so the pre-subcommand spelling keeps working.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, doctor, install

_HELP = """\
usage: kernlens <command> [options]

Host-side tools for the KernLens GDB extension.

commands:
  path       print the startup file to source from ~/.gdbinit
  install    add the startup file to ~/.gdbinit (--uninstall removes it)
  doctor     check that GDB can load KernLens (the default)
  version    print the installed version

Run `kernlens doctor` when a KernLens command is missing or refuses to
start; paste its report into an issue.
"""


def build_install_parser() -> argparse.ArgumentParser:
    """The ``kernlens install`` options."""
    parser = argparse.ArgumentParser(
        prog="kernlens install",
        description=(
            "Write the marked block that sources KernLens from "
            "~/.gdbinit.  Running it again replaces the block instead of "
            "appending a second one."
        ),
    )
    parser.add_argument(
        "--gdbinit", default=str(Path.home() / ".gdbinit"),
        help="GDB startup file to edit (default: ~/.gdbinit)",
    )
    parser.add_argument(
        "--startup", default=None,
        help="startup file to source (default: the one in this package)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print what would change without writing",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="remove the block instead of writing it",
    )
    return parser


def _install_command(argv: Sequence[str]) -> int:
    options = build_install_parser().parse_args(argv)
    gdbinit = Path(options.gdbinit).expanduser()
    startup = (
        Path(options.startup).expanduser() if options.startup else None
    )
    try:
        if options.uninstall:
            messages = install.uninstall(gdbinit, dry_run=options.dry_run)
        else:
            messages = install.install(
                gdbinit, startup=startup, dry_run=options.dry_run,
            )
    except (OSError, ValueError) as exc:
        print(f"kernlens install: {exc}", file=sys.stderr)
        return 1
    for message in messages:
        print(message)
    if not options.uninstall and not options.dry_run:
        print(f"Next: gdb -q -ex 'source {gdbinit}'")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a subcommand; no argument means ``doctor``."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return doctor.main([])
    command, rest = arguments[0], arguments[1:]
    if command in ("-h", "--help", "help"):
        print(_HELP, end="")
        return 0
    if command == "path":
        print(install.startup_path())
        return 0
    if command == "version":
        print(f"kernlens {__version__}")
        return 0
    if command == "doctor":
        return doctor.main(rest)
    if command == "install":
        return _install_command(rest)
    # Before the subcommands existed, every argument belonged to doctor.
    return doctor.main(arguments)


if __name__ == "__main__":  # pragma: no cover - exercised as a script
    raise SystemExit(main())
