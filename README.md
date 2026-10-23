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

## Local test

```powershell
python -m unittest discover -s tests -v
```

<!-- policy test r3-l5 -->
