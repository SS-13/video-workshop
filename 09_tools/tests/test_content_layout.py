from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest


TOOLS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_ROOT))
MODULE_PATH = TOOLS_ROOT / "migrate-date-first-layout.py"
SPEC = importlib.util.spec_from_file_location("migrate_date_first_layout", MODULE_PATH)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)

from video_production_core.content_layout import ContentRef, next_sequence  # noqa: E402
from video_production_core.run_store import default_run_id  # noqa: E402


class ContentLayoutTest(unittest.TestCase):
  def test_paths_are_date_first_for_every_content_type(self):
    root = Path("/workspace")
    ref = ContentRef("2026-07-14", "reading-note", "2")

    self.assertEqual(
      ref.text_path(root, "01_inbox"),
      root / "01_inbox/2026-07-14/reading-note/002.md",
    )
    self.assertEqual(
      ref.media_dir(root, "04_videos"),
      root / "04_videos/2026-07-14/reading-note/002",
    )

  def test_next_sequence_scans_text_and_media(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      (root / "01_inbox/2026-07-14/reading-note").mkdir(parents=True)
      (root / "01_inbox/2026-07-14/reading-note/001.md").write_text("one\n")
      (root / "04_videos/2026-07-14/reading-note/003").mkdir(parents=True)

      self.assertEqual(next_sequence(root, "2026-07-14", "reading-note"), "004")

  def test_run_ids_include_sequence_for_repeatable_content_types(self):
    root = Path("/workspace")
    self.assertNotEqual(
      default_run_id(root, "2026-07-14", "reading-note", "001"),
      default_run_id(root, "2026-07-14", "reading-note", "002"),
    )

  def test_migration_is_conflict_safe_and_preserves_recording(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      (root / "01_inbox").mkdir()
      (root / "01_inbox/2026-07-13.md").write_text("03_recordings/2026-07-13/source.mp4\n")
      (root / "03_recordings/2026-07-13").mkdir(parents=True)
      source = root / "03_recordings/2026-07-13/source.mp4"
      source.write_bytes(b"recording")
      (root / "04_videos/2026-07-13").mkdir(parents=True)
      (root / "04_videos/2026-07-13/job.json").write_text(json.dumps({
        "recording": str(source),
      }))

      operations = MIGRATION.build_operations(root)
      self.assertFalse([MIGRATION.operation_conflict(item) for item in operations if MIGRATION.operation_conflict(item)])
      for operation in operations:
        MIGRATION.apply_operation(operation)
      MIGRATION.rewrite_active_references(root, True)

      linked = root / "03_recordings/2026-07-13/video-diary/001/source.mp4"
      moved_inbox = root / "01_inbox/2026-07-13/video-diary/001.md"
      moved_job = root / "04_videos/2026-07-13/video-diary/001/job.json"
      self.assertTrue(source.is_file())
      self.assertEqual(linked.read_bytes(), source.read_bytes())
      self.assertIn("03_recordings/2026-07-13/video-diary/001/", moved_inbox.read_text())
      self.assertIn("03_recordings/2026-07-13/video-diary/001/", moved_job.read_text())


if __name__ == "__main__":
  unittest.main()
