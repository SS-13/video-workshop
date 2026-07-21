from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.github_issue_sync import (
  GitHubClient,
  GitHubIssueSyncError,
  build_issue_work_packet,
  check_pull_request_merge_gate,
  check_pull_request_issue_gate,
  closing_issue_numbers,
  reconcile_merged_pull_request,
  sync_topk_issues,
)


class FakeGitHubClient:
  def __init__(
    self,
    issues=None,
    pull_body="",
    base_branch="main",
    draft=False,
    checks=None,
    merged=False,
    head_branch="fix/topk-test",
    head_repository=None,
  ):
    self.repository = "example/video-workshop"
    self.issues = list(issues or [])
    self.pull_body = pull_body
    self.base_branch = base_branch
    self.draft = draft
    self.checks = checks or {"status": "success", "checks": [{"name": "test", "state": "SUCCESS"}]}
    self.merged = merged
    self.headBranch = head_branch
    self.headRepository = head_repository or self.repository
    self.merges = []
    self.closedIssues = []
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

  def close_issue(self, number):
    issue = self.get_issue(number)
    issue.update({"state": "closed", "state_reason": "completed"})
    self.closedIssues.append(number)
    return issue

  def get_issue(self, number):
    return next(item for item in self.issues if item["number"] == number)

  def get_pull_request(self, number):
    return {
      "number": number,
      "body": self.pull_body,
      "base": {"ref": self.base_branch},
      "head": {
        "ref": self.headBranch,
        "repo": {"full_name": self.headRepository},
      },
      "merged": self.merged,
      "draft": self.draft,
    }

  def default_branch(self):
    return "main"

  def get_pull_request_checks(self, number):
    return self.checks

  def merge_pull_request(self, number, auto=False):
    self.merges.append({"number": number, "auto": auto})
    return {"number": number, "auto": auto, "output": "merged"}


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

  def candidate(
    self,
    candidate_id,
    summary,
    category,
    priority="P2",
    scope="system-core",
    triage=None,
  ):
    return {
      "id": candidate_id,
      "summary": summary,
      "category": category,
      "priority": priority,
      "originalPriority": priority,
      "firstSeenAt": "2030-01-01T09:00:00+08:00",
      "scope": scope,
      "affectedComponent": "test-component",
      "occurrenceCount": 1,
      "eligibilityReasons": ["explicit-promotion-request"],
      "triage": triage or {},
    }

  def write_state(self, target_date, candidates, rolling=False, backlog=None):
    path = self.root / "00_state" / "evolution" / f"{target_date}.json"
    path.write_text(
      json.dumps({
        "date": target_date,
        "topKLocked": not rolling,
        "selectionMode": "rolling" if rolling else "frozen",
        "topK": candidates,
        "backlog": backlog or [],
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
          "processAction": "test",
          "status": "completed",
        }],
      }),
      encoding="utf-8",
    )

  def test_sync_creates_typed_issues_with_priority_labels(self):
    target = "2030-01-01"
    self.write_state(target, [
      self.candidate(
        "CAND-bug000000001",
        "Fix rendering regression",
        "bug",
        "P0",
        triage={
          "workflowStep": "render",
          "reproduction": "resume from review without word timing data",
          "userImpact": "final video cannot be exported",
          "priorityReason": "blocks a usable artifact",
          "proposedFix": "validate the timing path before resolution",
          "validationPlan": "run the resume regression test",
          "processGate": "add an input contract check",
        },
      ),
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
    self.assertIn("## Top-K Issue", client.issues[0]["body"])
    self.assertIn("**影响的流程步骤：** render", client.issues[0]["body"])
    self.assertIn("**复现条件 / 运行记录：** resume from review", client.issues[0]["body"])
    self.assertIn("**是否需要改流程或加门禁：** add an input contract check", client.issues[0]["body"])
    self.assertIn("**完成后的流程回写：** `pending`", client.issues[0]["body"])

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
    self.assertIn("status:backlog", labels)
    self.assertEqual(result["updated"][0]["workflowStatus"], "backlog")

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
    self.assertIn("- [x] 实现完成并形成可核对产物", client.issues[0]["body"])
    self.assertIn("**完成后的流程回写：** `test`", client.issues[0]["body"])

  def test_completed_rolling_candidate_is_projected_after_leaving_top_k(self):
    first_date = "2030-01-01"
    target = "2030-01-02"
    candidate_id = "CAND-rolledone001"
    self.write_state(first_date, [
      self.candidate(candidate_id, "Completed rolling feature", "new-capability", "P1"),
    ])
    self.write_completion(first_date, candidate_id)
    self.write_state(target, [], rolling=True)
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    labels = {item["name"] for item in client.issues[0]["labels"]}
    self.assertIn("status:verified", labels)
    self.assertEqual(result["created"][0]["workflowStatus"], "verified")
    self.assertEqual(client.issues[0]["title"], "Completed rolling feature")

  def test_issue_ready_backlog_is_projected_with_backlog_status(self):
    target = "2030-01-01"
    active = self.candidate("CAND-active000001", "Active repair", "bug", "P0")
    waiting = self.candidate("CAND-waiting0001", "Waiting repair", "bug", "P1")
    self.write_state(target, [active], backlog=[waiting])
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    self.assertEqual(len(result["created"]), 2)
    waiting_issue = next(item for item in client.issues if "Waiting repair" in item["title"])
    self.assertIn("status:backlog", {item["name"] for item in waiting_issue["labels"]})


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

  def test_private_path_in_public_triage_forces_redacted_projection(self):
    target = "2030-01-01"
    self.write_state(target, [
      self.candidate(
        "CAND-privatepath1",
        "Public summary",
        "bug",
        scope="system-core",
        triage={"reproduction": "/Users/example/private/run.json"},
      ),
    ])
    client = FakeGitHubClient()

    result = sync_topk_issues(self.root, target, client=client)

    self.assertEqual(result["privacyRedacted"][0]["reason"], "private-pattern")
    self.assertEqual(client.issues[0]["title"], "受限事项 CAND-privatepath1")
    self.assertNotIn("/Users/example", client.issues[0]["body"])

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

  def test_topk_pr_gate_requires_a_linked_issue_when_requested(self):
    client = FakeGitHubClient(pull_body="Refactor the control plane")

    result = check_pull_request_issue_gate(client, 12, require_topk=True)

    self.assertFalse(result["valid"])
    self.assertIn("managed TopK Issue", result["violations"][0])

  def test_merge_gate_requires_verified_issue_ready_pr_and_green_checks(self):
    issue = {
      "number": 7,
      "title": "Verified repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:verified"}],
      "state": "open",
      "html_url": "https://github.com/example/video-workshop/issues/7",
    }
    client = FakeGitHubClient([issue], pull_body="Closes #7", draft=False)

    result = check_pull_request_merge_gate(client, 12)

    self.assertTrue(result["valid"])
    self.assertEqual(result["checks"]["status"], "success")

  def test_merge_gate_blocks_draft_or_unfinished_checks(self):
    issue = {
      "number": 7,
      "title": "Verified repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:verified"}],
      "state": "open",
      "html_url": "https://github.com/example/video-workshop/issues/7",
    }
    client = FakeGitHubClient(
      [issue],
      pull_body="Closes #7",
      draft=True,
      checks={"status": "pending", "checks": [{"name": "test", "state": "PENDING"}]},
    )

    result = check_pull_request_merge_gate(client, 12)

    self.assertFalse(result["valid"])
    self.assertTrue(any("Ready for review" in item for item in result["violations"]))
    self.assertTrue(any("not green" in item for item in result["violations"]))

  def test_merge_gate_blocks_unchecked_canary_gate(self):
    issue = {
      "number": 7,
      "title": "Verified repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:verified"}],
      "state": "open",
      "html_url": "https://github.com/example/video-workshop/issues/7",
    }
    client = FakeGitHubClient(
      [issue],
      pull_body="Closes #7\n- [ ] One real PR HEAD video Canary is recorded",
      checks={"status": "success", "checks": [{"name": "test", "state": "SUCCESS"}]},
    )

    result = check_pull_request_merge_gate(client, 12)

    self.assertFalse(result["valid"])
    self.assertEqual(len(result["uncheckedCanaryGates"]), 1)
    self.assertTrue(any("unchecked Canary" in item for item in result["violations"]))

  def test_reconcile_closes_only_verified_managed_issues_after_merge(self):
    verified_issue = {
      "number": 7,
      "title": "Verified repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:verified"}],
      "state": "open",
    }
    pending_issue = {
      "number": 8,
      "title": "Pending repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:topk"}],
      "state": "open",
    }
    unrelated_issue = {
      "number": 9,
      "title": "Unrelated issue",
      "body": "",
      "labels": [{"name": "status:verified"}],
      "state": "open",
    }
    client = FakeGitHubClient(
      [verified_issue, pending_issue, unrelated_issue],
      pull_body="Closes #7\nCloses #8\nCloses #9",
      merged=True,
    )

    result = reconcile_merged_pull_request(client, 40, apply=True)

    self.assertTrue(result["valid"])
    self.assertEqual(result["eligibleIssues"], [7])
    self.assertEqual(result["closedIssues"], [7])
    self.assertEqual(result["alreadyClosedIssues"], [])
    self.assertEqual(client.closedIssues, [7])
    self.assertEqual(client.get_issue(7)["state"], "closed")
    self.assertEqual(client.get_issue(8)["state"], "open")
    self.assertEqual(client.get_issue(9)["state"], "open")
    self.assertEqual(
      {item["number"]: item["reason"] for item in result["skippedIssues"]},
      {8: "not-verified", 9: "unmanaged-issue"},
    )

    repeated = reconcile_merged_pull_request(client, 40, apply=True)
    self.assertEqual(repeated["closedIssues"], [])
    self.assertEqual(repeated["alreadyClosedIssues"], [7])
    self.assertEqual(client.closedIssues, [7])

  def test_reconcile_rejects_unmerged_or_non_topk_branch(self):
    issue = {
      "number": 7,
      "title": "Verified repair",
      "body": "",
      "labels": [{"name": "topk"}, {"name": "status:verified"}],
      "state": "open",
    }
    client = FakeGitHubClient(
      [issue],
      pull_body="Closes #7",
      merged=False,
      head_branch="feature/unrelated",
    )

    result = reconcile_merged_pull_request(client, 40, apply=True)

    self.assertFalse(result["valid"])
    self.assertEqual(result["closedIssues"], [])
    self.assertEqual(client.get_issue(7)["state"], "open")
    self.assertTrue(any("not merged" in item for item in result["violations"]))
    self.assertTrue(any("fix/topk-*" in item for item in result["violations"]))

  def test_work_packet_resolves_issue_and_completion_command(self):
    target = "2030-01-01"
    candidate_id = "CAND-start000001"
    candidate = self.candidate(candidate_id, "Fix a repeatable defect", "bug", "P0")
    self.write_state(target, [candidate])
    client = FakeGitHubClient()
    sync_topk_issues(self.root, target, client=client)

    packet = build_issue_work_packet(
      self.root,
      target,
      candidate_id,
      client=client,
    )

    self.assertEqual(packet["issueNumber"], 1)
    self.assertEqual(packet["branchName"], "fix/topk-cand-start000001")
    self.assertEqual(packet["recommendedChangeType"], "bugfix")
    self.assertIn("Closes #1", packet["prBody"])
    self.assertIn("evolve complete CAND-start000001", packet["completionCommand"])

  def test_get_retries_transient_503_with_backoff(self):
    client = GitHubClient("example/video-workshop")
    responses = [
      subprocess.CompletedProcess([], 1, "", "gh: HTTP 503"),
      subprocess.CompletedProcess([], 1, "", "gh: HTTP 503"),
      subprocess.CompletedProcess([], 0, '{"login":"example"}', ""),
    ]
    with patch("video_production_core.github_issue_sync.subprocess.run", side_effect=responses) as run:
      with patch("video_production_core.github_issue_sync.time.sleep") as sleep:
        result = client._run(["user"])

    self.assertEqual(result["login"], "example")
    self.assertEqual(run.call_count, 3)
    self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

  def test_post_does_not_retry_after_transient_failure(self):
    client = GitHubClient("example/video-workshop")
    response = subprocess.CompletedProcess([], 1, "", "gh: HTTP 503")
    with patch("video_production_core.github_issue_sync.subprocess.run", return_value=response) as run:
      with self.assertRaises(GitHubIssueSyncError):
        client._run(
          ["--method", "POST", "repos/example/video-workshop/issues"],
          {"title": "test"},
        )

    self.assertEqual(run.call_count, 1)

  def test_required_checks_classify_pending_state(self):
    client = GitHubClient("example/video-workshop")
    response = subprocess.CompletedProcess(
      [],
      1,
      '[{"name":"test","state":"PENDING","bucket":"pending"}]',
      "",
    )
    with patch("video_production_core.github_issue_sync.subprocess.run", return_value=response):
      result = client.get_pull_request_checks(12)

    self.assertEqual(result["status"], "pending")
    self.assertEqual(result["states"], ["PENDING"])

  def test_merge_command_can_queue_auto_merge(self):
    client = GitHubClient("example/video-workshop")
    response = subprocess.CompletedProcess([], 0, "queued", "")
    with patch("video_production_core.github_issue_sync.subprocess.run", return_value=response) as run:
      result = client.merge_pull_request(12, auto=True)

    self.assertTrue(result["auto"])
    self.assertIn("--auto", run.call_args.args[0])
    self.assertIn("--squash", run.call_args.args[0])


if __name__ == "__main__":
  unittest.main()
