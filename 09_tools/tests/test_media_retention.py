from pathlib import Path
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.media_retention import (  # noqa: E402
  MediaRetentionError,
  build_retention_plan,
  configure_retention,
  disk_space_status,
  run_retention,
)


class MediaRetentionTest(unittest.TestCase):
  def make_workspace(self, root, enabled=True, days=3, minimum_free_bytes=0):
    (root / "00_state/locks").mkdir(parents=True)
    (root / "00_state/workspace.json").write_text(
      json.dumps({
        "schemaVersion": 1,
        "mediaRetention": {
          "enabled": enabled,
          "retentionDays": days,
          "minimumFreeBytes": minimum_free_bytes,
        },
      }) + "\n",
      encoding="utf-8",
    )
    (root / "00_state/production-stats.csv").write_text(
      "content_id,date,column\n",
      encoding="utf-8",
    )
    for value in ("03_recordings", "04_videos", "05_exports", "06_logs"):
      (root / value).mkdir(parents=True, exist_ok=True)

  def add_completed_content(
    self,
    root,
    date_value="2026-07-14",
    content_id="2026-07-14_Day42",
    ready=True,
    stats=True,
  ):
    key = (date_value, "video-diary", "001")
    export_root = root / "05_exports" / key[0] / key[1] / key[2]
    export_root.mkdir(parents=True, exist_ok=True)
    (export_root / "publish-package.json").write_text(
      json.dumps({
        "contentId": content_id,
        "publishReady": ready,
        "production": {"statsRecorded": stats},
      }) + "\n",
      encoding="utf-8",
    )
    if stats:
      with (root / "00_state/production-stats.csv").open(
        "a", encoding="utf-8", newline=""
      ) as file:
        writer = csv.writer(file)
        writer.writerow([content_id, date_value, "video-diary"])
    return key

  def add_video(self, root, stage, key, name="sample.mp4", size=32):
    path = root / stage / key[0] / key[1] / key[2] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"v" * size)
    return path

  def test_plan_only_includes_logged_publish_ready_old_video_files(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root)
      eligible = self.add_completed_content(root)
      recent = self.add_completed_content(
        root,
        date_value="2026-07-15",
        content_id="2026-07-15_Day43",
      )
      unready = self.add_completed_content(
        root,
        date_value="2026-07-13",
        content_id="2026-07-13_Day41",
        ready=False,
        stats=False,
      )
      for stage in ("03_recordings", "04_videos", "05_exports"):
        self.add_video(root, stage, eligible, name=f"{stage}.mp4")
      self.add_video(root, "03_recordings", recent)
      self.add_video(root, "03_recordings", unready)
      subtitle = root / "04_videos" / eligible[0] / eligible[1] / eligible[2] / "final.srt"
      subtitle.write_text("subtitle", encoding="utf-8")

      plan = build_retention_plan(root, "2026-07-17")

      self.assertEqual(plan["cutoffDate"], "2026-07-14")
      self.assertEqual(plan["candidateCount"], 3)
      self.assertTrue(all(item["date"] == "2026-07-14" for item in plan["candidateFiles"]))
      self.assertTrue(subtitle.is_file())
      reasons = {item["reason"] for item in plan["protectedContents"]}
      self.assertIn("retention-window", reasons)
      self.assertIn("publish-not-ready", reasons)

  def test_apply_deletes_explicit_video_files_and_preserves_text_assets(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root)
      key = self.add_completed_content(root)
      videos = [
        self.add_video(root, "03_recordings", key, "source.MP4", 10),
        self.add_video(root, "04_videos", key, "working.mov", 20),
        self.add_video(root, "05_exports", key, "final.mp4", 30),
      ]
      subtitle = root / "04_videos" / key[0] / key[1] / key[2] / "final.srt"
      subtitle.write_text("subtitle", encoding="utf-8")
      cover = root / "05_exports" / key[0] / key[1] / key[2] / "cover.jpg"
      cover.write_bytes(b"cover")

      result = run_retention(root, "2026-07-17", apply=True)

      self.assertEqual(result["status"], "completed")
      self.assertEqual(len(result["deletedFiles"]), 3)
      self.assertEqual(result["deletedBytes"], 60)
      self.assertTrue(all(not path.exists() for path in videos))
      self.assertTrue(subtitle.is_file())
      self.assertTrue(cover.is_file())
      self.assertTrue((root / result["manifest"]).is_file())
      ledger = (root / "00_state/media-retention-ledger.csv").read_text(encoding="utf-8")
      self.assertEqual(len(ledger.strip().splitlines()), 4)

      repeated = run_retention(root, "2026-07-17", apply=True)
      self.assertEqual(repeated["candidateCount"], 0)
      self.assertEqual(repeated["deletedFiles"], [])

  def test_production_lock_skips_without_deleting(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root)
      key = self.add_completed_content(root)
      video = self.add_video(root, "05_exports", key)
      (root / "00_state/locks/production-active.lock.json").write_text("{}\n", encoding="utf-8")

      result = run_retention(root, "2026-07-17", apply=True)

      self.assertEqual(result["status"], "skipped")
      self.assertEqual(result["reason"], "production-lock")
      self.assertTrue(video.is_file())

  def test_disabled_policy_requires_explicit_opt_in(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root, enabled=False)

      with self.assertRaises(MediaRetentionError):
        run_retention(root, "2026-07-17", apply=True)

      result = run_retention(root, "2026-07-17", apply=True, if_enabled=True)
      self.assertEqual(result["status"], "skipped")
      self.assertEqual(result["reason"], "disabled")

  def test_configure_preserves_workspace_and_validates_days(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root, enabled=False)
      workspace_path = root / "00_state/workspace.json"
      workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
      workspace["integrations"] = {"githubIssues": {"enabled": True}}
      workspace_path.write_text(json.dumps(workspace) + "\n", encoding="utf-8")

      config = configure_retention(root, enabled=True, retention_days=3)

      self.assertTrue(config["enabled"])
      self.assertEqual(config["retentionDays"], 3)
      updated = json.loads(workspace_path.read_text(encoding="utf-8"))
      self.assertTrue(updated["integrations"]["githubIssues"]["enabled"])
      with self.assertRaises(MediaRetentionError):
        configure_retention(root, retention_days=0)

  def test_disk_space_status_uses_workspace_threshold(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      self.make_workspace(root, minimum_free_bytes=2048)
      with patch(
        "video_production_core.media_retention.shutil.disk_usage",
        return_value=type("Usage", (), {"free": 1024})(),
      ):
        status = disk_space_status(root)

      self.assertFalse(status["ready"])
      self.assertEqual(status["freeBytes"], 1024)

  def test_render_entrypoint_stops_before_engine_when_disk_is_low(self):
    script_path = (
      TOOLS_DIR.parent
      / ".codex/skills/video-diary-edit/scripts/render-day.py"
    )
    spec = importlib.util.spec_from_file_location("render_day_entrypoint", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with patch.object(module, "disk_space_status", return_value={
      "ready": False,
      "freeBytes": 100,
      "minimumFreeBytes": 200,
      "retentionEnabled": True,
    }), patch.object(module.subprocess, "run") as run:
      with self.assertRaises(SystemExit) as error:
        module.main()

    self.assertEqual(error.exception.code, 2)
    run.assert_not_called()


if __name__ == "__main__":
  unittest.main()
