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

## When the policy runs

The workflow is triggered by `pull_request_target` events (`opened`, `reopened`,
`synchronize`, `ready_for_review`). Pushes straight to `main` are not inspected,
so every change should arrive through a pull request.

## Test scenarios

| Scenario | Expected result |
| --- | --- |
| Commits with only human author, committer and trailers | `Claude attribution policy` succeeds and the pull request stays open |
| A `Co-authored-by` trailer with an `@anthropic.com` address | Changes requested, pull request closed, status fails |
| A Git author or committer using an `@anthropic.com` address | Changes requested, pull request closed, status fails |
| A pull request or commit linked to a `claude` / `anthropic` GitHub login | Changes requested, pull request closed, status fails |

## Local test

```powershell
python -m unittest discover -s tests -v
```
