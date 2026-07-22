#!/usr/bin/env python3
"""Read-only export/normalization of the repository's GitHub-side enforcement
configuration (rulesets + branch protection).

This is operator tooling, not CI: it shells out to the authenticated `gh` CLI
and is meant to be run manually (or by a trusted, non-PR-triggered scheduled
job later) to refresh the committed snapshot at
docs/governance/github_ruleset_snapshot.json. It never applies or changes any
GitHub setting -- it only reads and normalizes.

Usage:
    python scripts/qnty_ruleset_snapshot.py --repo CipherCuttle/Qnty > snapshot.json
    python scripts/qnty_ruleset_snapshot.py --repo CipherCuttle/Qnty --write docs/governance/github_ruleset_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone


def _gh_api_json(args: list[str]) -> object:
    result = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Branch protection 404s ("Branch not protected") when none is
        # configured; that is a normal, expected state, not a tool failure.
        if "404" in result.stderr or '"status":"404"' in result.stdout:
            return None
        raise RuntimeError(f"gh api {' '.join(args)} failed: {result.stderr.strip()}")
    text = result.stdout.strip()
    if not text:
        return None
    return json.loads(text)


def normalize(repo: str, *, now: datetime | None = None) -> dict:
    rulesets = _gh_api_json(["--paginate", f"repos/{repo}/rulesets"])
    branch_protection = _gh_api_json([f"repos/{repo}/branches/main/protection"])
    repo_settings = _gh_api_json([f"repos/{repo}"])

    merge_methods = {}
    bypass_actors_present = False
    if isinstance(repo_settings, dict):
        merge_methods = {
            "allow_squash_merge": repo_settings.get("allow_squash_merge"),
            "allow_merge_commit": repo_settings.get("allow_merge_commit"),
            "allow_rebase_merge": repo_settings.get("allow_rebase_merge"),
            "delete_branch_on_merge": repo_settings.get("delete_branch_on_merge"),
        }
    if isinstance(rulesets, list):
        for rs in rulesets:
            if isinstance(rs, dict) and rs.get("bypass_actors"):
                bypass_actors_present = True

    captured_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "captured_at_utc": captured_at,
        "repo": repo,
        "commands": [
            f"gh api --paginate repos/{repo}/rulesets",
            f"gh api repos/{repo}/branches/main/protection",
        ],
        "rulesets": rulesets if rulesets is not None else [],
        "rulesets_configured": bool(rulesets),
        "main_branch_protection": branch_protection,
        "main_branch_protected": branch_protection is not None,
        "merge_methods": merge_methods,
        "bypass_actors_present": bypass_actors_present,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. CipherCuttle/Qnty")
    parser.add_argument("--write", type=str, default=None, help="path to write the snapshot JSON to (default: stdout)")
    args = parser.parse_args(argv)

    snapshot = normalize(args.repo)
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if args.write:
        with open(args.write, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {args.write}", file=sys.stderr)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
