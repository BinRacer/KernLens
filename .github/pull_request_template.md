## What this changes

## Why

If this fixes a wrong answer, say what was printed and what is true.

## Checks

- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest -q` passes
- [ ] If a command's output or behaviour changed, the tutorial and the
      capture were regenerated (`tools/gen_tutorial.py`, not hand-edited)
- [ ] If a struct layout was involved, it resolves from DWARF or BTF
      first, and any fallback offset was verified against a real kernel
- [ ] `uv run python tools/check_examples.py --check` passes

## Anything reviewers should look at twice

Places where you made a judgement call, or where you are not certain.