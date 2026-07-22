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
  carried_backlog_ids,
  complete_candidate,
  record_candidate_triage,
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

  def write_policy(self, top_k=3, mode="rolling", lookback_days=7):
    policy = {
      "schemaVersion": 1,
      "topK": top_k,
      "lookbackDays": lookback_days,
      "repeatThreshold": 2,
      "priorityOrder": ["P0", "P1", "P2", "P3"],
      "candidateRules": {
        "explicitPromotionRequest": True,
        "repeatedObservation": True,
        "p0AlwaysEligible": False,
        "deterministicFinding": True,
        "reproducibleObservation": True,
        "productionBlocking": True,
        "materialRework": True,
        "highImpact": True,
      },
      "selection": {
        "mode": mode,
        "freezeDailyTopK": mode == "frozen",
        "carryForwardBacklog": True,
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
        "triage": observation.get("triage", {}),
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

  def test_completed_top_k_releases_slot_and_survives_same_day_rerun(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {"summary": "任务一", "priority": "P0", "promoteRequested": True},
      {"summary": "任务二", "priority": "P1", "promoteRequested": True},
      {"summary": "任务三", "priority": "P2", "promoteRequested": True},
    ])
    first = run_evolution(self.root, target)
    candidate_id = first["topK"][0]["id"]
    evidence = self.root / "evidence.txt"
    artifact = self.root / "artifact.json"
    evidence.write_text("passed\n", encoding="utf-8")
    artifact.write_text("{}\n", encoding="utf-8")

    completed = complete_candidate(
      self.root,
      target,
      candidate_id,
      "feature",
      [str(evidence)],
      [str(artifact)],
      actor="test",
      requires_canary=True,
      process_action="test",
      process_note="Added regression coverage.",
    )
    repeated = complete_candidate(
      self.root,
      target,
      candidate_id,
      "feature",
      [str(evidence)],
      [str(artifact)],
      actor="test",
      requires_canary=True,
    )
    record_observation(self.root, {
      "date": target,
      "summary": "午间新增需求",
      "category": "new-capability",
      "priority": "P0",
      "scope": "system-core",
      "actor": "test",
      "promoteRequested": True,
    })
    rerun = run_evolution(self.root, target)

    ledger = json.loads(
      (self.root / completed["completionRecord"]).read_text(encoding="utf-8")
    )
    self.assertEqual(len(ledger["completed"]), 1)
    self.assertTrue(repeated["reused"])
    self.assertNotIn(candidate_id, [item["id"] for item in rerun["topK"]])
    self.assertIn("午间新增需求", [item["summary"] for item in rerun["topK"]])
    self.assertEqual(rerun["selectionMode"], "rolling")
    self.assertEqual(rerun["summary"]["completedTopKCount"], 0)
    self.assertEqual(rerun["summary"]["completedCandidateCount"], 1)
    self.assertIn(candidate_id, completed["topKChanges"]["exited"])
    self.assertTrue(ledger["completed"][0]["releaseCandidate"])
    self.assertEqual(ledger["completed"][0]["releaseTarget"], "2.2.0")
    self.assertEqual(ledger["completed"][0]["versionDecision"], "automatic-bump")
    self.assertEqual(ledger["completed"][0]["versionPlanBase"], "2.1.0")
    self.assertEqual(ledger["completed"][0]["recommendedSemVer"], "minor")
    self.assertTrue(ledger["completed"][0]["requiresCanary"])
    self.assertEqual(ledger["completed"][0]["processAction"], "test")
    self.assertEqual(ledger["completed"][0]["processNote"], "Added regression coverage.")

  def test_completed_candidate_does_not_return_on_a_later_day(self):
    first_date = "2026-07-12"
    next_date = "2026-07-13"
    self.write_policy(top_k=1)
    self.append_observations(first_date, [{
      "summary": "已经完成的能力",
      "priority": "P0",
      "promoteRequested": True,
    }])
    first = run_evolution(self.root, first_date)
    evidence = self.root / "completion-evidence.txt"
    evidence.write_text("passed\n", encoding="utf-8")
    complete_candidate(
      self.root,
      first_date,
      first["topK"][0]["id"],
      "bugfix",
      [str(evidence)],
      actor="test",
    )
    self.append_observations(next_date, [
      {
        "summary": "已经完成的能力",
        "priority": "P0",
        "promoteRequested": True,
      },
      {
        "summary": "新的候选能力",
        "priority": "P1",
        "promoteRequested": True,
      },
    ])

    next_state = run_evolution(self.root, next_date)

    self.assertEqual(next_state["topK"][0]["summary"], "新的候选能力")
    self.assertNotIn(
      "已经完成的能力",
      [item["summary"] for item in next_state["backlog"]],
    )

  def test_report_lists_completed_candidates_separately_from_active_work(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {"summary": "已完成的能力", "priority": "P0", "promoteRequested": True},
      {"summary": "仍待处理的能力", "priority": "P1", "promoteRequested": True},
    ])
    first = run_evolution(self.root, target)
    evidence = self.root / "completion-report.txt"
    evidence.write_text("passed\n", encoding="utf-8")

    completed = complete_candidate(
      self.root,
      target,
      first["topK"][0]["id"],
      "bugfix",
      [str(evidence)],
      actor="test",
      process_action="test",
    )
    state = json.loads((self.root / completed["statePath"]).read_text(encoding="utf-8"))
    report = (self.root / completed["reportPath"]).read_text(encoding="utf-8")

    self.assertEqual(state["outputSchemaVersion"], 2)
    self.assertEqual(state["completed"][0]["candidateId"], first["topK"][0]["id"])
    self.assertIn("## 已完成候选", report)
    self.assertIn("已完成的能力", report)
    self.assertIn("仍待处理的能力", report)

  def test_unfinished_top_k_is_re_ranked_on_the_next_day(self):
    first_date = "2026-07-12"
    next_date = "2026-07-13"
    self.write_policy(top_k=1)
    self.append_observations(first_date, [{
      "summary": "昨日未完成事项",
      "priority": "P2",
      "promoteRequested": True,
    }])
    first = run_evolution(self.root, first_date)
    self.assertEqual(first["topK"][0]["summary"], "昨日未完成事项")
    self.append_observations(next_date, [{
      "summary": "今日更高优先级事项",
      "priority": "P0",
      "promoteRequested": True,
    }])

    next_state = run_evolution(self.root, next_date)

    self.assertEqual(next_state["topK"][0]["summary"], "今日更高优先级事项")
    carried = next(item for item in next_state["backlog"] if item["summary"] == "昨日未完成事项")
    self.assertEqual(carried["status"], "parked-topk")
    self.assertEqual(carried["ageDays"], 1)

  def test_carry_uses_only_the_nearest_successful_snapshot(self):
    older = self.root / "00_state" / "evolution" / "2026-07-11.json"
    latest = self.root / "00_state" / "evolution" / "2026-07-12.json"
    older.write_text(
      json.dumps({"topK": [{"id": "CAND-retired00001"}], "backlog": []}),
      encoding="utf-8",
    )
    latest.write_text(
      json.dumps({
        "topK": [{"id": "CAND-current00001"}],
        "backlog": [{"id": "CAND-current00002"}],
      }),
      encoding="utf-8",
    )

    carried = carried_backlog_ids(self.root, "2026-07-13", 7)

    self.assertEqual(carried, {"CAND-current00001", "CAND-current00002"})
    self.assertNotIn("CAND-retired00001", carried)

  def test_carry_set_participates_in_input_hash(self):
    first_date = "2026-07-12"
    next_date = "2026-07-13"
    self.append_observations(first_date, [{
      "summary": "跨日事项",
      "priority": "P1",
      "promoteRequested": True,
    }])
    run_evolution(self.root, first_date)
    first_next = run_evolution(self.root, next_date)
    previous_path = self.root / "00_state" / "evolution" / f"{first_date}.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    previous["backlog"].append({"id": "CAND-no-source0001"})
    previous_path.write_text(json.dumps(previous), encoding="utf-8")

    refreshed = run_evolution(self.root, next_date)

    self.assertFalse(refreshed["reused"])
    self.assertNotEqual(first_next["inputHash"], refreshed["inputHash"])

  def test_carried_backlog_priority_rises_one_level_per_day(self):
    first_date = "2026-07-12"
    next_date = "2026-07-13"
    self.write_policy(top_k=1)
    self.append_observations(first_date, [
      {"summary": "当日阻断项", "priority": "P0", "promoteRequested": True},
      {"summary": "延期任务", "priority": "P2", "promoteRequested": True},
    ])

    first = run_evolution(self.root, first_date)
    evidence = self.root / "blocking-item-complete.txt"
    evidence.write_text("passed\n", encoding="utf-8")
    complete_candidate(
      self.root,
      first_date,
      first["topK"][0]["id"],
      "bugfix",
      [str(evidence)],
      actor="test",
    )
    second = run_evolution(self.root, next_date)

    self.assertEqual(first["topK"][0]["summary"], "当日阻断项")
    self.assertEqual(second["topK"][0]["summary"], "延期任务")
    self.assertEqual(second["topK"][0]["originalPriority"], "P2")
    self.assertEqual(second["topK"][0]["priority"], "P1")
    self.assertEqual(second["topK"][0]["ageDays"], 1)
    self.assertEqual(second["topK"][0]["priorityRaisedBy"], 1)

  def test_active_candidate_is_carried_after_observation_leaves_lookback_window(self):
    first_date = "2026-07-10"
    carry_date = "2026-07-11"
    target_date = "2026-07-12"
    self.write_policy(top_k=1, lookback_days=2)
    self.append_observations(first_date, [{
      "summary": "窗口外仍未完成的活动事项",
      "priority": "P1",
      "promoteRequested": True,
    }])

    first = run_evolution(self.root, first_date)
    carried_snapshot = run_evolution(self.root, carry_date)
    self.assertEqual(carried_snapshot["topK"][0]["id"], first["topK"][0]["id"])
    self.append_observations(target_date, [{
      "summary": "今日更高优先级事项",
      "priority": "P0",
      "promoteRequested": True,
    }])

    result = run_evolution(self.root, target_date)

    self.assertEqual(result["topK"][0]["summary"], "今日更高优先级事项")
    carried = next(
      item for item in result["backlog"]
      if item["id"] == first["topK"][0]["id"]
    )
    self.assertEqual(carried["summary"], "窗口外仍未完成的活动事项")
    self.assertEqual(carried["firstSeenAt"], f"{first_date}T12:01:00+08:00")
    self.assertEqual(carried["ageDays"], 2)
    self.assertEqual(carried["status"], "parked-topk")

  def test_completed_candidate_is_excluded_from_carried_snapshot(self):
    first_date = "2026-07-10"
    carry_date = "2026-07-11"
    target_date = "2026-07-12"
    self.write_policy(top_k=1, lookback_days=2)
    self.append_observations(first_date, [{
      "summary": "完成后不应复活的事项",
      "priority": "P0",
      "promoteRequested": True,
    }])

    first = run_evolution(self.root, first_date)
    evidence = self.root / "carried-completion-evidence.txt"
    evidence.write_text("passed\n", encoding="utf-8")
    complete_candidate(
      self.root,
      first_date,
      first["topK"][0]["id"],
      "bugfix",
      [str(evidence)],
      actor="test",
    )
    run_evolution(self.root, carry_date)
    result = run_evolution(self.root, target_date)

    candidate_id = first["topK"][0]["id"]
    self.assertNotIn(candidate_id, [item["id"] for item in result["topK"]])
    self.assertNotIn(candidate_id, [item["id"] for item in result["backlog"]])

  def test_p0_ties_are_sorted_oldest_first(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {
        "summary": "较新的P0",
        "priority": "P0",
        "promoteRequested": True,
        "createdAt": f"{target}T12:03:00+08:00",
      },
      {
        "summary": "最早的P0",
        "priority": "P0",
        "promoteRequested": True,
        "createdAt": f"{target}T12:01:00+08:00",
      },
      {
        "summary": "中间的P0",
        "priority": "P0",
        "promoteRequested": True,
        "createdAt": f"{target}T12:02:00+08:00",
      },
    ])

    result = run_evolution(self.root, target)

    self.assertEqual(
      [item["summary"] for item in result["topK"]],
      ["最早的P0", "中间的P0", "较新的P0"],
    )

  def test_native_p0_precedes_older_candidate_aged_to_p0(self):
    target = "2026-07-13"
    self.write_policy(top_k=1)
    self.append_observations("2026-07-11", [{
      "summary": "由P2老化为P0",
      "priority": "P2",
      "promoteRequested": True,
      "createdAt": "2026-07-11T09:00:00+08:00",
    }])
    self.append_observations(target, [{
      "summary": "当天原生P0",
      "priority": "P0",
      "promoteRequested": True,
      "createdAt": "2026-07-13T09:00:00+08:00",
    }])

    result = run_evolution(self.root, target)

    self.assertEqual(result["topK"][0]["summary"], "当天原生P0")

  def test_blocking_critical_issue_precedes_older_equal_priority_work(self):
    target = "2026-07-13"
    self.write_policy(top_k=1)
    self.append_observations("2026-07-12", [{
      "summary": "更早但不阻断的事项",
      "priority": "P1",
      "promoteRequested": True,
      "createdAt": "2026-07-12T09:00:00+08:00",
    }])
    self.append_observations(target, [{
      "summary": "当前阻断产出的事项",
      "priority": "P1",
      "triage": {
        "impactLevel": "critical",
        "blocking": True,
        "reproducible": True,
      },
      "createdAt": "2026-07-13T09:00:00+08:00",
    }])

    result = run_evolution(self.root, target)

    self.assertEqual(result["topK"][0]["summary"], "当前阻断产出的事项")

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

  def test_p0_without_issue_evidence_stays_observation_only(self):
    target = "2026-07-13"
    self.append_observations(target, [{
      "summary": "只有优先级但没有运行证据",
      "category": "bug",
      "priority": "P0",
    }])

    result = run_evolution(self.root, target)

    self.assertEqual(result["topK"], [])
    self.assertEqual(result["backlog"][0]["status"], "needs-evidence")

  def test_reproducible_blocker_becomes_issue_ready(self):
    target = "2026-07-13"
    self.append_observations(target, [{
      "summary": "确认可复现的导出阻断",
      "category": "bug",
      "priority": "P1",
      "triage": {
        "workflowStep": "render",
        "reproduction": "从 review 断点恢复且 wordJson 为空",
        "userImpact": "无法导出成片",
        "impactLevel": "critical",
        "priorityReason": "阻断可用产物",
        "proposedFix": "空路径进入校验前直接失败",
        "validationPlan": "新增断点恢复回归测试",
        "processGate": "增加输入契约门禁",
        "reproducible": True,
        "blocking": True,
        "causesRework": True,
      },
    }])

    result = run_evolution(self.root, target)
    candidate = result["topK"][0]

    self.assertIn("reproducible-observation", candidate["eligibilityReasons"])
    self.assertIn("production-blocking", candidate["eligibilityReasons"])
    self.assertIn("material-rework", candidate["eligibilityReasons"])
    self.assertIn("high-impact", candidate["eligibilityReasons"])
    self.assertEqual(candidate["triage"]["workflowStep"], "render")
    self.assertEqual(candidate["triage"]["impactLevel"], "critical")

  def test_triage_update_does_not_increase_occurrence_count(self):
    target = "2026-07-13"
    self.append_observations(target, [{
      "summary": "待补充分诊的问题",
      "category": "bug",
      "priority": "P1",
      "promoteRequested": True,
    }])
    first = run_evolution(self.root, target)
    candidate_id = first["topK"][0]["id"]

    triage_observation = record_candidate_triage(
      self.root,
      target,
      candidate_id,
      {
        "workflowStep": "review-resume",
        "reproduction": "resume without word timing data",
        "userImpact": "render cannot continue",
        "impactLevel": "high",
        "reproducible": True,
        "blocking": True,
      },
      actor="test",
    )
    updated = run_evolution(self.root, target)
    candidate = updated["topK"][0]

    self.assertFalse(triage_observation["countsAsOccurrence"])
    self.assertEqual(candidate["id"], candidate_id)
    self.assertEqual(candidate["occurrenceCount"], 1)
    self.assertEqual(candidate["triage"]["workflowStep"], "review-resume")
    self.assertIn("reproducible-observation", candidate["eligibilityReasons"])

  def test_report_contains_local_production_issue_list(self):
    target = "2026-07-13"
    self.append_observations(target, [
      {
        "summary": "字幕渲染首次超时",
        "category": "performance",
        "affectedComponent": "subtitle-render",
      },
      {
        "summary": "封面字体加载失败",
        "category": "bug",
        "affectedComponent": "cover-font",
        "promoteRequested": True,
      },
      {
        "summary": "调整开场文案",
        "category": "content-rule",
        "promoteRequested": True,
      },
    ])

    result = run_evolution(self.root, target)
    report = (self.root / result["reportPath"]).read_text(encoding="utf-8")

    self.assertIn("## 生产问题清单", report)
    self.assertIn("字幕渲染首次超时", report)
    self.assertIn("待复现/判断", report)
    self.assertIn("封面字体加载失败", report)
    issue_section = report.split("## 生产问题清单", 1)[1].split("## P0 结论", 1)[0]
    self.assertNotIn("调整开场文案", issue_section)

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

  def test_new_observations_roll_into_current_top_k(self):
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

    self.assertNotEqual(
      [item["id"] for item in second["topK"]],
      [item["id"] for item in first["topK"]],
    )
    self.assertEqual(second["selectionMode"], "rolling")
    self.assertIn("午间新增高优先级需求", [item["summary"] for item in second["topK"]])
    self.assertEqual(len(second["topKChanges"]["entered"]), 1)
    self.assertEqual(len(second["topKChanges"]["exited"]), 1)

  def test_frozen_mode_remains_available_for_legacy_workspaces(self):
    target = "2026-07-13"
    self.write_policy(mode="frozen")
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

    self.assertEqual([item["id"] for item in second["topK"]], [item["id"] for item in first["topK"]])
    self.assertEqual(second["selectionMode"], "frozen")

  def test_explicit_reselect_can_replace_locked_daily_top_k(self):
    target = "2026-07-13"
    self.write_policy(mode="frozen")
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
