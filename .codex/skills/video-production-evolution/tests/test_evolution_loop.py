from pathlib import Path
from datetime import date, timedelta
import json
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from evolution_loop import (  # noqa: E402
  EvolutionDeferred,
  ObservationParseError,
  record_observation,
  run_evolution,
)


class EvolutionLoopTest(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name)
    (self.root / "00_system").mkdir(parents=True)
    (self.root / "00_state" / "observations").mkdir(parents=True)
    (self.root / "00_state" / "evolution").mkdir(parents=True)
    (self.root / "00_state" / "locks").mkdir(parents=True)
    (self.root / "17_reports" / "evolution").mkdir(parents=True)
    (self.root / "package.json").write_text(
      json.dumps({"version": "2.1.0"}),
      encoding="utf-8",
    )
    self.write_policy()

  def tearDown(self):
    self.temp.cleanup()

  def write_policy(self, top_k=3):
    policy = {
      "schemaVersion": 1,
      "topK": top_k,
      "lookbackDays": 7,
      "repeatThreshold": 2,
      "priorityOrder": ["P0", "P1", "P2", "P3"],
      "candidateRules": {
        "explicitPromotionRequest": True,
        "repeatedObservation": True,
        "p0AlwaysEligible": True,
        "deterministicFinding": True,
      },
    }
    (self.root / "00_system" / "evolution-policy.json").write_text(
      json.dumps(policy),
      encoding="utf-8",
    )

  def append_observations(self, observation_date, observations):
    path = self.root / "00_state" / "observations" / f"{observation_date}.ndjson"
    lines = []
    for index, observation in enumerate(observations, start=1):
      payload = {
        "id": f"OBS-{observation_date.replace('-', '')}-{index:03d}",
        "date": observation_date,
        "summary": observation["summary"],
        "category": observation.get("category", "uncategorized"),
        "priority": observation.get("priority", "P2"),
        "scope": observation.get("scope", "system-core"),
        "affectedComponent": observation.get("affectedComponent", "general"),
        "source": observation.get("source", "user-correction"),
        "actor": observation.get("actor", "test"),
        "promoteRequested": observation.get("promoteRequested", False),
        "deterministicFinding": observation.get("deterministicFinding", False),
        "createdAt": observation.get("createdAt", f"{observation_date}T12:{index:02d}:00+08:00"),
      }
      lines.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

  def test_default_top_k_selects_three_and_keeps_every_other_update(self):
    target = "2026-07-13"
    observations = [
      {"summary": "更新一", "priority": "P0", "promoteRequested": True},
      {"summary": "更新二", "priority": "P1", "promoteRequested": True},
      {"summary": "更新三", "priority": "P2", "promoteRequested": True},
      {"summary": "更新四", "priority": "P3", "promoteRequested": True},
      {"summary": "更新五", "priority": "P2", "promoteRequested": False},
    ]
    self.append_observations(target, observations)

    result = run_evolution(self.root, target)

    self.assertEqual(result["topKLimit"], 3)
    self.assertEqual(len(result["topK"]), 3)
    self.assertEqual(result["topK"][0]["contentIds"], [])
    self.assertEqual(result["summary"]["todayObservationCount"], 5)
    self.assertEqual(result["summary"]["deduplicatedUpdateCount"], 5)
    self.assertEqual(len(result["backlog"]), 2)
    statuses = {item["summary"]: item["status"] for item in result["backlog"]}
    self.assertEqual(statuses["更新四"], "parked-topk")
    self.assertEqual(statuses["更新五"], "needs-evidence")

  def test_top_k_can_be_overridden_without_changing_policy(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {"summary": f"更新{index}", "promoteRequested": True}
      for index in range(5)
    ])

    result = run_evolution(self.root, target, top_k_override=2)

    self.assertEqual(result["topKLimit"], 2)
    self.assertEqual(len(result["topK"]), 2)
    policy = json.loads((self.root / "00_system" / "evolution-policy.json").read_text(encoding="utf-8"))
    self.assertEqual(policy["topK"], 3)

  def test_repeated_observation_becomes_candidate(self):
    target_date = date.fromisoformat("2026-07-13")
    previous = (target_date - timedelta(days=1)).isoformat()
    target = target_date.isoformat()
    shared = {
      "summary": "字幕整体偏快",
      "category": "subtitle-rule",
      "affectedComponent": "subtitle-timing",
    }
    self.append_observations(previous, [shared])
    self.append_observations(target, [shared])

    result = run_evolution(self.root, target)

    self.assertEqual(len(result["topK"]), 1)
    self.assertEqual(result["topK"][0]["occurrenceCount"], 2)
    self.assertIn("repeated-observation", result["topK"][0]["eligibilityReasons"])

  def test_single_temporary_update_stays_in_needs_evidence(self):
    target = "2026-07-13"
    self.append_observations(target, [{
      "summary": "今天临时加一张图",
      "category": "temporary-exception",
      "scope": "single-run",
    }])

    result = run_evolution(self.root, target)

    self.assertEqual(result["topK"], [])
    self.assertEqual(result["backlog"][0]["status"], "needs-evidence")

  def test_same_inputs_reuse_previous_state_and_report(self):
    target = "2026-07-13"
    self.append_observations(target, [{
      "summary": "固化发布包",
      "promoteRequested": True,
    }])

    first = run_evolution(self.root, target)
    state_path = self.root / first["statePath"]
    report_path = self.root / first["reportPath"]
    first_state = state_path.read_text(encoding="utf-8")
    first_report = report_path.read_text(encoding="utf-8")
    second = run_evolution(self.root, target)

    self.assertFalse(first["reused"])
    self.assertTrue(second["reused"])
    self.assertEqual(state_path.read_text(encoding="utf-8"), first_state)
    self.assertEqual(report_path.read_text(encoding="utf-8"), first_report)

  def test_invalid_ndjson_writes_error_report_without_state(self):
    target = "2026-07-13"
    path = self.root / "00_state" / "observations" / f"{target}.ndjson"
    original = "{not-json}\n"
    path.write_text(original, encoding="utf-8")

    with self.assertRaises(ObservationParseError):
      run_evolution(self.root, target)

    self.assertEqual(path.read_text(encoding="utf-8"), original)
    self.assertFalse((self.root / "00_state" / "evolution" / f"{target}.json").exists())
    self.assertTrue((self.root / "17_reports" / "evolution" / f"{target}-daily-evolution-error.md").exists())

  def test_production_lock_defers_loop(self):
    target = "2026-07-13"
    lock = self.root / "00_state" / "locks" / "production-active.lock.json"
    lock.write_text("{}\n", encoding="utf-8")

    with self.assertRaises(EvolutionDeferred):
      run_evolution(self.root, target)

  def test_record_observation_appends_every_update(self):
    target = "2026-07-13"
    for index in range(6):
      record_observation(self.root, {
        "date": target,
        "summary": f"更新 {index}",
        "category": "new-capability",
        "priority": "P2",
        "actor": "test",
      })

    path = self.root / "00_state" / "observations" / f"{target}.ndjson"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    self.assertEqual(len(lines), 6)

  def test_new_observations_do_not_replace_locked_daily_top_k(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {"summary": "早间任务一", "priority": "P1", "promoteRequested": True},
      {"summary": "早间任务二", "priority": "P2", "promoteRequested": True},
      {"summary": "早间任务三", "priority": "P3", "promoteRequested": True},
    ])
    first = run_evolution(self.root, target)

    record_observation(self.root, {
      "date": target,
      "summary": "午间新增高优先级需求",
      "category": "bug",
      "priority": "P0",
      "scope": "system-core",
      "actor": "test",
      "promoteRequested": True,
    })
    second = run_evolution(self.root, target)

    self.assertEqual(
      [item["id"] for item in second["topK"]],
      [item["id"] for item in first["topK"]],
    )
    self.assertEqual(second["selectionMode"], "frozen")
    self.assertIn(
      "午间新增高优先级需求",
      [item["summary"] for item in second["backlog"]],
    )

  def test_explicit_reselect_can_replace_locked_daily_top_k(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {"summary": "早间任务一", "priority": "P1", "promoteRequested": True},
      {"summary": "早间任务二", "priority": "P2", "promoteRequested": True},
      {"summary": "早间任务三", "priority": "P3", "promoteRequested": True},
    ])
    run_evolution(self.root, target)
    record_observation(self.root, {
      "date": target,
      "summary": "阻断生产的紧急问题",
      "category": "bug",
      "priority": "P0",
      "scope": "system-core",
      "actor": "test",
      "promoteRequested": True,
    })

    result = run_evolution(self.root, target, reselect=True)

    self.assertEqual(result["selectionMode"], "explicit-reselect")
    self.assertIn(
      "阻断生产的紧急问题",
      [item["summary"] for item in result["topK"]],
    )


if __name__ == "__main__":
  unittest.main()
