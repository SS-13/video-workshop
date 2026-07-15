from pathlib import Path
import json
import sys
import tempfile
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.github_issue_sync import (
  check_pull_request_issue_gate,
  closing_issue_numbers,
  sync_topk_issues,
)


class FakeGitHubClient:
  def __init__(self, issues=None, pull_body="", base_branch="main"):
    self.repository = "example/video-workshop"
    self.issues = list(issues or [])
    self.pull_body = pull_body
    self.base_branch = base_branch
    self.labelsEnsured = 0

  def ensure_labels(self):
    self.labelsEnsured += 1

  def list_managed_issues(self):
    return self.issues

  def create_issue(self, title, body, labels):
    issue = {
      "number": len(self.issues) + 1,
      "title": title,
      "body": body,
      "labels": [{"name": value} for value in labels],
      "state": "open",
      "html_url": f"https://github.com/example/video-workshop/issues/{len(self.issues) + 1}",
    }
    self.issues.append(issue)
    return issue

  def update_issue(self, number, title, body, labels):
    issue = self.get_issue(number)
    issue.update({
      "title": title,
      "body": body,
      "labels": [{"name": value} for value in labels],
    })
    return issue

  def get_issue(self, number):
    return next(item for item in self.issues if item["number"] == number)

  def get_pull_request(self, number):
    return {
      "number": number,
      "body": self.pull_body,
      "base": {"ref": self.base_branch},
    }

  def default_branch(self):
    return "main"


class GitHubIssueSyncTest(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    (self.root / "00_system").mkdir(parents=True)
    (self.root / "00_state" / "evolution" / "completed").mkdir(parents=True)
    (self.root / "00_state").mkdir(exist_ok=True)
    (self.root / "00_system" / "evolution-policy.json").write_text(
      json.dumps({
        "priorityOrder": ["P0", "P1", "P2", "P3"],
        "selection": {
          "priorityAging": {
            "enabled": True,
            "daysPerLevel": 1,
            "maximumPriority": "P0",
          },
        },
        "githubIssues": {
          "publicScopes": ["system-core"],
        },
      }),
      encoding="utf-8",
    )

  def tearDown(self):
    self.temp.cleanup()

  def candidate(self, candidate_id, summary, category, priority="P2", scope="system-core"):
    return {
      "id": candidate_id,
      "summary": summary,
      "category": category,
      "priority": priority,
      "originalPriority": priority,
      "firstSeenAt": "2030-01-01T09:00:00+08:00",
      "scope": scope,
      "affectedComponent": "test-component",
    }

  def write_state(self, target_date, candidates):
    path = self.root / "00_state" / "evolution" / f"{target_date}.json"
    path.write_text(
      json.dumps({
        "date": target_date,
        "topKLocked": True,
        "topK": candidates,
      }),
      encoding="utf-8",
    )

  def write_completion(self, target_date, candidate_id, change_type="feature"):
    path = self.root / "00_state" / "evolution" / "completed" / f"{target_date}.json"
    path.write_text(
      json.dumps({
        "date": target_date,
        "completed": [{
          "candidateId": candidate_id,
          "changeType": change_type,
          "status": "completed",
        }],
      }),
      encoding="utf-8",
    )

  def test_sync_creates_typed_issues_with_priority_labels(self):
    target = "2030-01-01"
    self.write_state(target, [
      self.candidate("CAND-bug000000001", "Fix rendering regression", "bug", "P0"),
      self.candidate("CAND-feat00000001", "Add export option", "new-capability", "P1"),
      self.candidate("CAND-other0000001", "Clarify workflow policy", "content-rule", "P2"),
    ])
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    self.assertEqual(len(result["created"]), 3)
    self.assertEqual(client.labelsEnsured, 1)
    labels = [
      {item["name"] for item in issue["labels"]}
      for issue in client.issues
    ]
    self.assertIn("type:bug", labels[0])
    self.assertIn("priority:P0", labels[0])
    self.assertIn("type:feature", labels[1])
    self.assertIn("type:other", labels[2])
    self.assertTrue(all("status:topk" in value for value in labels))
    self.assertEqual(client.issues[0]["title"], "Fix rendering regression")

  def test_open_issue_priority_ages_without_returning_to_daily_topk(self):
    first_date = "2030-01-01"
    self.write_state(first_date, [
      self.candidate("CAND-aging000001", "Old maintenance task", "content-rule", "P3"),
    ])
    client = FakeGitHubClient()
    sync_topk_issues(self.root, first_date, client=client)
    self.assertIn("priority:P3", {item["name"] for item in client.issues[0]["labels"]})

    later_date = "2030-01-04"
    self.write_state(later_date, [])
    result = sync_topk_issues(self.root, later_date, client=client)

    labels = {item["name"] for item in client.issues[0]["labels"]}
    self.assertIn("priority:P0", labels)
    self.assertNotIn("priority:P3", labels)
    self.assertEqual(result["updated"][0]["ageDays"], 3)
    self.assertEqual(result["updated"][0]["priority"], "P0")

  def test_completed_candidate_becomes_verified_but_stays_open(self):
    target = "2030-01-01"
    candidate_id = "CAND-done00000001"
    self.write_state(target, [
      self.candidate(candidate_id, "Verified feature", "new-capability", "P1"),
    ])
    self.write_completion(target, candidate_id)
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    labels = {item["name"] for item in client.issues[0]["labels"]}
    self.assertIn("status:verified", labels)
    self.assertEqual(client.issues[0]["state"], "open")
    self.assertTrue(result["created"][0]["verified"])

  def test_non_public_scope_is_listed_as_a_redacted_issue(self):
    target = "2030-01-01"
    self.write_state(target, [
      self.candidate(
        "CAND-private00001",
        "Private workspace preference",
        "content-rule",
        scope="workspace-user",
      ),
    ])
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    self.assertEqual(len(result["created"]), 1)
    self.assertEqual(result["privacySkipped"], [])
    self.assertEqual(
      result["privacyRedacted"][0]["reason"],
      "scope-not-public:workspace-user",
    )
    self.assertEqual(client.issues[0]["title"], "受限事项 CAND-private00001")
    self.assertNotIn("Private workspace preference", client.issues[0]["body"])

  def test_dry_run_does_not_mutate_remote_client(self):
    target = "2030-01-01"
    self.write_state(target, [
      self.candidate("CAND-dryrun000001", "Dry run", "new-capability"),
    ])
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, dry_run=True, client=client)

    self.assertEqual(len(result["created"]), 1)
    self.assertEqual(client.issues, [])
    self.assertEqual(client.labelsEnsured, 0)

  def test_pr_gate_requires_verified_topk_issue(self):
    issue = {
      "number": 7,
      "title": "[TopK] Test",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:topk"}],
      "state": "open",
      "html_url": "https://github.com/example/video-workshop/issues/7",
    }
    client = FakeGitHubClient([issue], pull_body="Closes #7")

    blocked = check_pull_request_issue_gate(client, 12)
    issue["labels"] = [{"name": "topk"}, {"name": "status:verified"}]
    allowed = check_pull_request_issue_gate(client, 12)

    self.assertFalse(blocked["valid"])
    self.assertTrue(allowed["valid"])
    self.assertEqual(closing_issue_numbers("Fixes #7 and resolves #8"), [7, 8])


if __name__ == "__main__":
  unittest.main()
