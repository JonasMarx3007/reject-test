#!/usr/bin/env python3
"""Block pull requests carrying Claude or Anthropic attribution metadata."""

from __future__ import annotations

import json
import os
import re
import sys
from html import escape
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STATUS_CONTEXT = "Claude attribution policy"
CLAUDE_LOGIN = re.compile(r"^(?:claude|claude(?:-|\[).+|anthropic(?:-|\[)?.*)$", re.I)
ANTHROPIC_EMAIL = re.compile(r"@(?:[a-z0-9-]+\.)*anthropic\.com$", re.I)
CLAUDE_IDENTITY = re.compile(r"^(?:claude(?:\s+(?:code|ai|opus|sonnet|haiku))?|anthropic)$", re.I)
COAUTHOR = re.compile(
    r"^co-authored-by:\s*(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$",
    re.I | re.M,
)


@dataclass(frozen=True)
class Finding:
    location: str
    reason: str


def _is_denied_login(login: str | None) -> bool:
    return bool(login and CLAUDE_LOGIN.fullmatch(login.strip()))


def _is_denied_identity(name: str | None, email: str | None) -> bool:
    clean_name = " ".join((name or "").split())
    clean_email = (email or "").strip()
    return bool(ANTHROPIC_EMAIL.search(clean_email)) or bool(
        clean_name and CLAUDE_IDENTITY.fullmatch(clean_name) and "anthropic" in clean_email.casefold()
    )


def inspect(pr_author: str | None, commits: Iterable[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []

    if _is_denied_login(pr_author):
        findings.append(Finding("pull request", f"GitHub author @{pr_author}"))

    for index, item in enumerate(commits, start=1):
        sha = str(item.get("sha", "unknown"))[:12]
        location = f"commit {sha} (#{index})"

        for role in ("author", "committer"):
            account = item.get(role) or {}
            login = account.get("login")
            if _is_denied_login(login):
                findings.append(Finding(location, f"GitHub {role} @{login}"))

        commit = item.get("commit") or {}
        for role in ("author", "committer"):
            identity = commit.get(role) or {}
            name = identity.get("name")
            email = identity.get("email")
            if _is_denied_identity(name, email):
                findings.append(Finding(location, f"Git {role} {name} <{email}>"))

        message = str(commit.get("message", ""))
        for match in COAUTHOR.finditer(message):
            name, email = match.group("name"), match.group("email")
            if _is_denied_identity(name, email):
                findings.append(Finding(location, f"co-author {name} <{email}>"))

    return _deduplicate(findings)


def _deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    return list(dict.fromkeys(findings))


def _github_request(url: str, token: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reject-test-attribution-policy",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def _load_all_commits(api_url: str, repository: str, number: int, token: str) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{api_url}/repos/{repository}/pulls/{number}/commits?per_page=100&page={page}"
        batch = _github_request(url, token)
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an unexpected commits response")
        commits.extend(batch)
        if len(batch) < 100:
            return commits
        page += 1


def _set_status(api_url: str, repository: str, sha: str, token: str, state: str, description: str) -> None:
    url = f"{api_url}/repos/{repository}/statuses/{sha}"
    _github_request(
        url,
        token,
        method="POST",
        payload={"state": state, "context": STATUS_CONTEXT, "description": description[:140]},
    )


def rejection_body(findings: list[Finding]) -> str:
    shown = findings[:20]
    details = [
        f"- **{escape(finding.location)}:** `{escape(finding.reason)}`"
        for finding in shown
    ]
    if len(findings) > len(shown):
        details.append(f"- …and {len(findings) - len(shown)} additional finding(s).")
    return "\n".join(
        [
            "## Pull request rejected",
            "",
            "This pull request was automatically closed because prohibited "
            "Claude/Anthropic attribution was found:",
            "",
            *details,
            "",
            "Remove the prohibited attribution from every commit, rewrite the "
            "branch history, and open a new pull request.",
        ]
    )


def _reject_pull_request(
    api_url: str,
    repository: str,
    number: int,
    token: str,
    findings: list[Finding],
) -> None:
    base_url = f"{api_url}/repos/{repository}/pulls/{number}"
    body = rejection_body(findings)

    try:
        _github_request(
            f"{base_url}/reviews",
            token,
            method="POST",
            payload={"body": body, "event": "REQUEST_CHANGES"},
        )
    except urllib.error.HTTPError as exc:
        print(f"Could not submit a changes-requested review: HTTP {exc.code}", file=sys.stderr)

    _github_request(base_url, token, method="PATCH", payload={"state": "closed"})


def main() -> int:
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pull_request = event["pull_request"]
    repository = os.environ["GITHUB_REPOSITORY"]
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    token = os.environ["GITHUB_TOKEN"]
    number = int(pull_request["number"])
    head_sha = pull_request["head"]["sha"]
    pr_author = (pull_request.get("user") or {}).get("login")

    try:
        commits = _load_all_commits(api_url, repository, number, token)
        findings = inspect(pr_author, commits)
        if findings:
            print("Rejected: prohibited Claude/Anthropic attribution was found:", file=sys.stderr)
            for finding in findings:
                print(f"- {finding.location}: {finding.reason}", file=sys.stderr)
            _set_status(api_url, repository, head_sha, token, "failure", "Rejected: Claude/Anthropic attribution detected")
            _reject_pull_request(api_url, repository, number, token, findings)
            return 1

        _set_status(api_url, repository, head_sha, token, "success", "No Claude/Anthropic attribution detected")
        print("Accepted: no prohibited attribution metadata was found.")
        return 0
    except Exception as exc:
        print(f"Policy check failed safely: {exc}", file=sys.stderr)
        try:
            _set_status(api_url, repository, head_sha, token, "error", "Policy check error; merge must remain blocked")
        except Exception as status_exc:
            print(f"Could not report error status: {status_exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
