"""Frozen external contract for the KernLens public surfaces.

The constants live in ``contract_spec`` (importable from both the unit
and integration suites); this module only asserts their internal
consistency, so it runs without GDB.
"""

from __future__ import annotations

import unittest

from contract_spec import (
    CANONICAL_COMMANDS,
    COMPONENT_INSTANCE_NAMES,
    FACADE_BOUND_NAMES,
    PUBLIC_API_EXTRA,
)


class ContractTest(unittest.TestCase):
    """The classic KernLens surface stays present and unchanged."""

    def test_canonical_command_names_are_unique(self) -> None:
        self.assertEqual(
            len(CANONICAL_COMMANDS), len(set(CANONICAL_COMMANDS)),
        )
        for name in CANONICAL_COMMANDS:
            self.assertTrue(name.startswith("kernlens-"), name)

    def test_facade_bound_names_are_unique(self) -> None:
        self.assertEqual(
            len(FACADE_BOUND_NAMES), len(set(FACADE_BOUND_NAMES)),
        )

    def test_public_api_names_are_unique(self) -> None:
        self.assertEqual(
            len(PUBLIC_API_EXTRA), len(set(PUBLIC_API_EXTRA)),
        )

    def test_component_instance_names_are_unique(self) -> None:
        self.assertEqual(
            len(COMPONENT_INSTANCE_NAMES),
            len(set(COMPONENT_INSTANCE_NAMES)),
        )


if __name__ == "__main__":
    unittest.main()