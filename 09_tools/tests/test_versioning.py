from pathlib import Path
import json
import sys
import tempfile
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.versioning import (  # noqa: E402
  apply_version_plan,
  build_version_plan,
  bump_version,
  proposed_major_version,
)


class VersioningTest(unittest.TestCase):
  def make_root(self):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    (root / "00_system").mkdir(parents=True)
    (root / "00_state" / "evolution" / "completed").mkdir(parents=True)
    (root / "00_system" / "system.json").write_text(
      json.dumps({"activeRelease": "3.0.0"}),
      encoding="utf-8",
    )
    (root / "package.json").write_text(
      json.dumps({"version": "3.0.0"}),
      encoding="utf-8",
    )
    (root / "00_system" / "release-policy.json").write_text(
      json.dumps({
        "versioning": {
          "automatic": True,
          "baseVersion": "3.0.0",
          "baseVersionAt": "2026-07-14T05:55:55+08:00",
          "historicalCandidateIds": ["CAND-history"],
          "majorRequiresUserConfirmation": True,
        }
      }),
      encoding="utf-8",
    )
    return temp, root

  def write_completed(self, root, entries):
    (root / "00_state" / "evolution" / "completed" / "2026-07-15.json").write_text(
      json.dumps({"schemaVersion": 1, "date": "2026-07-15", "completed": entries}),
      encoding="utf-8",
    )

  def test_bump_rules_and_major_proposal(self):
    self.assertEqual(bump_version("3.0.0", "bugfix"), "3.0.1")
    self.assertEqual(bump_version("3.0.1", "feature"), "3.1.0")
    self.assertEqual(bump_version("3.1.0", "bugfix"), "3.1.1")
    self.assertEqual(proposed_major_version("3.5.6"), "4.0.0")

  def test_plan_keeps_historical_release_and_replays_minor_patch(self):
    temp, root = self.make_root()
    self.addCleanup(temp.cleanup)
    self.write_completed(root, [
      {
        "candidateId": "CAND-history",
        "summary": "3.0 baseline",
        "changeType": "major-evolution",
        "completedAt": "2026-07-15T10:00:00+08:00",
      },
      {
        "candidateId": "CAND-feature",
        "summary": "small feature",
        "changeType": "feature",
        "completedAt": "2026-07-15T11:00:00+08:00",
      },
      {
        "candidateId": "CAND-bug-one",
        "summary": "first bug",
        "changeType": "bugfix",
        "completedAt": "2026-07-15T12:00:00+08:00",
      },
      {
        "candidateId": "CAND-major-new",
        "summary": "new contract",
        "changeType": "major-evolution",
        "completedAt": "2026-07-15T13:00:00+08:00",
      },
    ])

    plan = build_version_plan(root)

    targets = {item["candidateId"]: item for item in plan["records"]}
    self.assertEqual(targets["CAND-history"]["releaseTarget"], "3.0.0")
    self.assertEqual(targets["CAND-history"]["versionDecision"], "historical-user-confirmed")
    self.assertEqual(targets["CAND-feature"]["releaseTarget"], "3.1.0")
    self.assertEqual(targets["CAND-bug-one"]["releaseTarget"], "3.1.1")
    self.assertIsNone(targets["CAND-major-new"]["releaseTarget"])
    self.assertEqual(targets["CAND-major-new"]["versionDecision"], "user-confirmation-required")
    self.assertEqual(plan["pendingMajor"][0]["proposedTarget"], "4.0.0")
    self.assertEqual(plan["lastPlannedVersion"], "3.1.1")

  def test_backfill_is_idempotent(self):
    temp, root = self.make_root()
    self.addCleanup(temp.cleanup)
    self.write_completed(root, [{
      "candidateId": "CAND-bug",
      "summary": "bug",
      "changeType": "bugfix",
      "completedAt": "2026-07-15T10:00:00+08:00",
    }])

    first = apply_version_plan(root)
    second = apply_version_plan(root)

    self.assertEqual(first["changedRecords"], 1)
    self.assertEqual(second["changedRecords"], 0)
    record = json.loads(
      (root / "00_state" / "evolution" / "completed" / "2026-07-15.json").read_text(
        encoding="utf-8"
      )
    )["completed"][0]
    self.assertEqual(record["releaseTarget"], "3.0.1")
    self.assertEqual(record["versionPlanBase"], "3.0.0")


if __name__ == "__main__":
  unittest.main()
