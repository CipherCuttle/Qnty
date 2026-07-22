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


def _is_expected_unprotected_main(args: list[str], result: subprocess.CompletedProcess[str]) -> bool:
    """Return true only for GitHub's normal unprotected-main response."""
    if len(args) != 1 or not args[0].startswith("repos/") or not args[0].endswith("/branches/main/protection"):
        return False
    for text in (result.stderr, result.stdout):
        try:
            payload = json.loads(text.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("status") == "404" and payload.get("message") == "Branch not protected":
            return True
    return False


def _gh_api_json(args: list[str], *, allow_unprotected_main: bool = False) -> object:
    result = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Only this exact endpoint and response represent normal absence.
        if allow_unprotected_main and _is_expected_unprotected_main(args, result):
            return None
        raise RuntimeError(f"gh api {' '.join(args)} failed: {result.stderr.strip()}")
    text = result.stdout.strip()
    if not text:
        return None
    return json.loads(text)


def normalize(repo: str, *, now: datetime | None = None) -> dict:
    rulesets = _gh_api_json(["--paginate", f"repos/{repo}/rulesets"])
    branch_protection = _gh_api_json([f"repos/{repo}/branches/main/protection"], allow_unprotected_main=True)
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
    detailed_rulesets = []
    if not isinstance(rulesets, list):
        raise RuntimeError("rulesets endpoint returned a non-list response")
    for summary in rulesets:
        if not isinstance(summary, dict) or not isinstance(summary.get("id"), int):
            raise RuntimeError(f"ruleset summary missing integer id: {summary!r}")
        detail = _gh_api_json([f"repos/{repo}/rulesets/{summary['id']}"])
        if not isinstance(detail, dict):
            raise RuntimeError(f"ruleset detail was not an object for id={summary['id']}")
        detailed_rulesets.append(detail)
        if detail.get("bypass_actors"):
            bypass_actors_present = True

    captured_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "capture": {"captured_at_utc": captured_at},
        "policy": {
            "repo": repo,
            "commands": [
                f"gh api --paginate repos/{repo}/rulesets",
                f"gh api repos/{repo}/branches/main/protection",
            ],
            "rulesets": detailed_rulesets,
            "rulesets_configured": bool(detailed_rulesets),
            "main_branch_protection": branch_protection,
            "main_branch_protected": branch_protection is not None,
            "merge_methods": merge_methods,
            "bypass_actors_present": bypass_actors_present,
        },
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
