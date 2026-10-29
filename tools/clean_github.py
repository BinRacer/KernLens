#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Delete the GitHub records a rewritten history left behind.

A force-push replaces commits but leaves their workflow runs and pull
request behind, so the Actions tab keeps showing red or stale entries for
SHAs nobody can fetch.  This removes them.

Two things it cannot do, and says so rather than failing halfway:

* **A merged pull request cannot be deleted.**  GitHub has no endpoint for
  it.  The options are to close the branch's record by editing the PR
  body, to leave it, or to delete the repository -- so the PR is reported,
  not removed.
* **Deleting a workflow run needs `Actions: write`.**  A fine-grained token
  with only `Contents: write` gets a 403, which is reported as a hint.

Run it dry first; `--apply` is what deletes::

    uv run python tools/clean_github.py --repo owner/name
    uv run python tools/clean_github.py --repo owner/name --apply

It only considers runs and PRs whose `head_sha` is no longer reachable
from any branch, which is why it needs a local clone: reachability is a
question only the object database can answer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

#: The runs GitHub keeps regardless of what the API says.
KEEP_CONCLUSIONS = ("in_progress", "queued", "requested", "waiting", "pending")


def _git(*args: str) -> str:
    """Run git and return stdout, raising SystemExit on failure."""
    result = subprocess.run(
        ("git", *args), capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return result.stdout


def _remote_token() -> str:
    """Return a GitHub token, preferring the one `gh` already stores."""
    result = subprocess.run(
        ("gh", "auth", "token"), capture_output=True, text=True, check=False,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise SystemExit(
            "no GitHub token; run `gh auth login` or set GH_TOKEN"
        )
    return token


def _api(
    method: str, path: str, token: str,
) -> tuple[int, Any]:
    """Call the REST API and return ``(status, decoded body or None)``."""
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            decoded = json.loads(body) if body else None
        except json.JSONDecodeError:
            decoded = body
        return exc.code, decoded


def _reachable_hashes() -> set[str]:
    """Every commit reachable from any local or remote-tracking ref."""
    output = _git("rev-list", "--all")
    return set(output.split())


def _orphaned_runs(
    repo: str, token: str, reachable: set[str],
) -> list[dict[str, Any]]:
    """Workflow runs whose commit is no longer reachable from any ref."""
    orphans: list[dict[str, Any]] = []
    page = 1
    while True:
        status, body = _api(
            "GET",
            f"/repos/{repo}/actions/runs?per_page=100&page={page}",
            token,
        )
        if status != 200 or not isinstance(body, dict):
            raise SystemExit(
                f"cannot list workflow runs (HTTP {status}): {body}"
            )
        runs = body.get("workflow_runs", [])
        if not runs:
            break
        for run in runs:
            if run.get("head_sha") in reachable:
                continue
            if run.get("conclusion") in KEEP_CONCLUSIONS:
                continue
            orphans.append(run)
        if len(runs) < 100:
            break
        page += 1
    return orphans


def _orphaned_pulls(
    repo: str, token: str, reachable: set[str],
) -> list[dict[str, Any]]:
    """Pull requests whose head commit is no longer reachable."""
    status, body = _api(
        "GET", f"/repos/{repo}/pulls?state=all&per_page=100", token,
    )
    if status != 200 or not isinstance(body, list):
        raise SystemExit(f"cannot list pull requests (HTTP {status}): {body}")
    return [pr for pr in body if pr.get("head", {}).get("sha") not in reachable]


def _describe_run(run: dict[str, Any]) -> str:
    """One line naming a workflow run."""
    return (
        f"{run.get('id')}  {run.get('name')}  "
        f"{run.get('head_branch')}  {run.get('head_sha', '')[:7]}  "
        f"{run.get('conclusion')}  {run.get('created_at')}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete the GitHub records a rewritten history left behind.",
    )
    parser.add_argument(
        "--repo", required=True, metavar="OWNER/NAME",
        help="repository to clean, e.g. BinRacer/KernLens",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually delete; without it, only report",
    )
    args = parser.parse_args(argv)

    token = _remote_token()
    reachable = _reachable_hashes()
    runs = _orphaned_runs(args.repo, token, reachable)
    pulls = _orphaned_pulls(args.repo, token, reachable)

    print(f"unreachable workflow runs: {len(runs)}")
    for run in runs:
        print(f"  {_describe_run(run)}")
    print(f"unreachable pull requests: {len(pulls)}")
    for pr in pulls:
        print(
            f"  #{pr.get('number')}  {pr.get('state')}  "
            f"{pr.get('title', '')[:60]}"
        )

    merged = [pr for pr in pulls if pr.get("merged_at")]
    if merged:
        print(
            "\nNote: a merged pull request cannot be deleted -- GitHub has "
            "no endpoint for it. The run records above are what can go."
        )

    if not args.apply:
        print("\nnothing deleted; re-run with --apply")
        return 0

    deleted = 0
    denied = 0
    for run in runs:
        status, body = _api(
            "DELETE", f"/repos/{args.repo}/actions/runs/{run.get('id')}", token,
        )
        if status in (204, 200):
            deleted += 1
        elif status == 403:
            denied += 1
        else:
            print(f"  failed {run.get('id')}: HTTP {status} {body}")

    print(f"\ndeleted {deleted} run(s)")
    if denied:
        print(
            f"{denied} run(s) refused with 403: the token needs "
            "`Actions: write` (a fine-grained PAT with only `Contents: "
            "write` cannot delete runs)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())