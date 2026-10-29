"""Check that a built wheel can be loaded by GDB.

The wheel used to be unusable: ``gdbinit.py`` lived beside ``src/`` and
was not package data, so ``pip install`` produced a package with no
startup file.  That is a property of the build, not of the source tree,
so importing ``kernlens`` in a checkout cannot verify it.  CI builds the
wheel and runs this.

Usage::

    python tools/check_wheel.py dist/*.whl
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

#: Files a wheel must contain for ``source $(kernlens path)`` to work.
REQUIRED: tuple[str, ...] = (
    "kernlens/__init__.py",
    "kernlens/cli.py",
    "kernlens/gdbinit.py",
    "kernlens/py.typed",
)

#: The console-script lines that make ``kernlens path`` and ``kl path``
#: exist.  Two names for one function: the GDB command line spells every
#: command ``kernlens-<verb>`` and its ``kl-<verb>`` alias, and the host
#: CLI is the same tool seen from the other interpreter.  Shipping only the
#: long name meant a reader who had just typed ``kl-status`` had to
#: remember a different spelling one prompt later.
ENTRY_POINTS = (
    "kernlens = kernlens.cli:main",
    "kl = kernlens.cli:main",
)


def check(wheel: Path) -> list[str]:
    """Return every reason *wheel* would not be loadable, in order."""
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for required in REQUIRED:
            if required not in names:
                problems.append(f"missing {required}")
        entry_points = sorted(
            name for name in names
            if name.endswith(".dist-info/entry_points.txt")
        )
        if not entry_points:
            problems.append("missing .dist-info/entry_points.txt")
        else:
            text = archive.read(entry_points[0]).decode("utf-8")
            text = text.replace("\r\n", "\n")
            for entry_point in ENTRY_POINTS:
                if entry_point not in text:
                    problems.append(
                        f"entry_points.txt does not contain {entry_point!r}"
                    )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Check every wheel named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path)
    args = parser.parse_args(argv)

    failed = False
    for wheel in args.wheels:
        problems = check(wheel)
        if problems:
            failed = True
            for problem in problems:
                print(f"{wheel}: {problem}", file=sys.stderr)
        else:
            print(
                f"{wheel}: ships the startup file and the console script"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
