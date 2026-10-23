import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_pr_attribution.py"
SPEC = importlib.util.spec_from_file_location("check_pr_attribution", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def commit(
    *,
    sha="0123456789abcdef",
    message="Normal change",
    author_login="alice",
    committer_login="alice",
    author_name="Alice",
    author_email="alice@example.com",
):
    return {
        "sha": sha,
        "author": {"login": author_login} if author_login else None,
        "committer": {"login": committer_login} if committer_login else None,
        "commit": {
            "author": {"name": author_name, "email": author_email},
            "committer": {"name": author_name, "email": author_email},
            "message": message,
        },
    }


class AttributionPolicyTests(unittest.TestCase):
    def test_clean_pull_request_passes(self):
        self.assertEqual(MODULE.inspect("alice", [commit()]), [])

    def test_claude_pull_request_author_is_rejected(self):
        findings = MODULE.inspect("claude", [commit()])
        self.assertTrue(any("@claude" in finding.reason for finding in findings))

    def test_claude_github_commit_author_is_rejected(self):
        findings = MODULE.inspect("alice", [commit(author_login="claude[bot]")])
        self.assertTrue(any("@claude[bot]" in finding.reason for finding in findings))

    def test_anthropic_email_is_rejected(self):
        findings = MODULE.inspect(
            "alice",
            [commit(author_name="Claude", author_email="noreply@anthropic.com")],
        )
        self.assertTrue(any("anthropic.com" in finding.reason for finding in findings))

    def test_claude_coauthor_trailer_is_rejected(self):
        message = "Add feature\n\nCo-authored-by: Claude <noreply@anthropic.com>"
        findings = MODULE.inspect("alice", [commit(message=message)])
        self.assertTrue(any("co-author Claude" in finding.reason for finding in findings))

    def test_plain_claude_reference_is_not_rejected(self):
        findings = MODULE.inspect("alice", [commit(message="Document Claude policy")])
        self.assertEqual(findings, [])

    def test_unrelated_person_named_claude_is_not_rejected(self):
        findings = MODULE.inspect(
            "alice",
            [commit(author_name="Claude Bernard", author_email="claude@example.com")],
        )
        self.assertEqual(findings, [])

    def test_rejection_body_explains_the_finding(self):
        body = MODULE.rejection_body(
            [MODULE.Finding("commit abc123", "co-author Claude <noreply@anthropic.com>")]
        )
        self.assertIn("Pull request rejected", body)
        self.assertIn("commit abc123", body)
        self.assertIn("noreply@anthropic.com", body)

    def test_rejection_requests_changes_then_closes_pull_request(self):
        finding = MODULE.Finding("commit abc123", "co-author Claude <noreply@anthropic.com>")
        with patch.object(MODULE, "_github_request") as request:
            MODULE._reject_pull_request(
                "https://api.github.test",
                "owner/repository",
                7,
                "token",
                [finding],
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].kwargs["method"], "POST")
        self.assertEqual(request.call_args_list[0].kwargs["payload"]["event"], "REQUEST_CHANGES")
        self.assertEqual(
            request.call_args_list[1],
            call(
                "https://api.github.test/repos/owner/repository/pulls/7",
                "token",
                method="PATCH",
                payload={"state": "closed"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
