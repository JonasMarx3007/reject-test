# reject-test

Isolated test repository for a pull-request policy that blocks changes attributed
to Claude or Anthropic.

The policy inspects:

- the pull-request author's GitHub login;
- each commit's linked GitHub author and committer;
- Git author and committer names and email addresses;
- `Co-authored-by` trailers in commit messages.

The workflow runs from the trusted default branch with minimal permissions. It
never checks out or executes code from the pull request. When attribution is
detected, the workflow requests changes with an explanation, closes the pull
request, and reports a failed status named `Claude attribution policy` on the
pull request's head commit.

This is a metadata policy, not an AI detector. It cannot identify undisclosed use
of Claude when the attribution has been removed.

## Making the policy binding

On its own the workflow only reports, reviews and closes. A pull request can
still be reopened and merged by a maintainer, and pushes straight to `main` are
never inspected. To make the policy binding, add a branch ruleset for `main`
that:

1. requires a pull request before merging;
2. requires the `Claude attribution policy` status check to pass;
3. blocks force pushes and does not allow bypassing these rules.

## Known limitations

- Only commit metadata and the pull-request author are inspected. The
  pull-request title and description, and commit-message lines such as
  `Generated with Claude Code` or `Claude-Session:`, are not checked.
- `Co-authored-by` trailers must start at the beginning of a line; an indented
  trailer is not detected.
- GitHub's pull-request commits API returns at most 250 commits, so commits
  beyond that in very large pull requests are not inspected.
- Login matching is broad: any login starting with `anthropic`, or with
  `claude-` / `claude[`, is rejected, which can catch unrelated human accounts.

## Repository layout

| Path | Purpose |
| --- | --- |
| `.github/workflows/reject-claude-attribution.yml` | Runs the policy on pull-request events |
| `scripts/check_pr_attribution.py` | Inspects attribution metadata and rejects the pull request |
| `tests/test_check_pr_attribution.py` | Unit tests for the matching rules and rejection message |

## Local test

```powershell
python -m unittest discover -s tests -v
```
