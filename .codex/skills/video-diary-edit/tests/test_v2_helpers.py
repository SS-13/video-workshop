from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import file_fingerprint, stage_cache_key


def load_module(name, path):
  spec = importlib.util.spec_from_file_location(name, path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


timing_module = load_module("subtitle_timing", SCRIPT_DIR / "check-subtitle-timing.py")
transcribe_module = load_module("transcribe", SCRIPT_DIR / "transcribe-recording-to-srt.py")
render_v2_module = load_module("render_v2", SCRIPT_DIR / "render-day-v2.py")
publish_module = load_module("publish_package", SCRIPT_DIR / "build-publish-package.py")
correct_module = load_module("correct_transcript", SCRIPT_DIR / "correct-transcript.py")
review_module = load_module("build_review_pack", SCRIPT_DIR / "build-review-pack.py")


class WorkflowStateTest(unittest.TestCase):
  def test_file_fingerprint_and_cache_key_change_with_content(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "sample.txt"
      path.write_text("first", encoding="utf-8")
      first = file_fingerprint(path)
      first_key = stage_cache_key([path], {"model": "base"})
      path.write_text("second", encoding="utf-8")
      second = file_fingerprint(path)
      second_key = stage_cache_key([path], {"model": "base"})
      self.assertNotEqual(first["sha256Sample"], second["sha256Sample"])
      self.assertNotEqual(first_key, second_key)

  def test_optional_artifact_path_rejects_empty_or_directory_values(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      artifact = root / "artifact.srt"
      artifact.write_text("test", encoding="utf-8")

      self.assertIsNone(render_v2_module.optional_artifact_path(root, ""))
      self.assertIsNone(render_v2_module.optional_artifact_path(root, "."))
      self.assertEqual(render_v2_module.optional_artifact_path(root, artifact), artifact)

  def test_review_assets_keep_video_and_subtitle_under_one_root_without_copying(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      workspace = root / "04_videos" / "2026-07-21" / "video-diary" / "001"
      video = workspace / "preprocessed" / "source_trimmed.mp4"
      subtitle = workspace / "subtitles" / "2026-07-21_transcribed_corrected.srt"
      video.parent.mkdir(parents=True)
      subtitle.parent.mkdir(parents=True)
      video.write_bytes(b"video")
      subtitle.write_text("subtitle", encoding="utf-8")

      assets = review_module.build_review_assets(root, workspace, video, subtitle)

      self.assertEqual(assets["video"].resolve(), video.resolve())
      self.assertEqual(assets["subtitle"].resolve(), subtitle.resolve())
      self.assertTrue(assets["video"].is_symlink())
      self.assertTrue(assets["subtitle"].is_symlink())
      self.assertEqual(assets["directory"].name, "review")
      self.assertEqual((assets["directory"] / "README.md").is_file(), True)
      manifest = json.loads((assets["directory"] / "review-manifest.json").read_text(encoding="utf-8"))
      self.assertEqual(manifest["video"], "video.mp4")
      self.assertEqual(manifest["subtitle"], "subtitles.srt")

  def test_review_assets_do_not_overwrite_real_files(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      workspace = root / "workspace"
      video = workspace / "source.mp4"
      subtitle = workspace / "source.srt"
      workspace.mkdir(parents=True)
      video.write_bytes(b"video")
      subtitle.write_text("subtitle", encoding="utf-8")
      review_dir = workspace / "review"
      review_dir.mkdir()
      (review_dir / "video.mp4").write_bytes(b"user file")

      with self.assertRaises(RuntimeError):
        review_module.build_review_assets(root, workspace, video, subtitle)


class SubtitleAlignmentTest(unittest.TestCase):
  def test_exact_word_boundaries_pass(self):
    blocks = [{"start": 1.0, "end": 2.0, "text": "测试"}]
    words = [{"start": 1.0, "end": 2.0, "text": "测试"}]
    errors, report = timing_module.check_word_alignment(blocks, words, 0.45, 0.25, 0)
    self.assertEqual(errors, [])
    self.assertEqual(report["p95StartDelta"], 0.0)

  def test_sustained_offset_fails(self):
    blocks = [{"start": 1.4, "end": 2.4, "text": "测试"}]
    words = [{"start": 1.0, "end": 2.0, "text": "测试"}]
    errors, _ = timing_module.check_word_alignment(blocks, words, 0.45, 0.25, 0)
    self.assertTrue(any(error.startswith("global_audio_offset") for error in errors))


class TranscriptCorrectionTest(unittest.TestCase):
  def test_missing_optional_dictionaries_leave_transcript_unchanged(self):
    with tempfile.TemporaryDirectory() as directory:
      missing = Path(directory) / "missing.tsv"

      replacements, used_paths = correct_module.read_dictionary_chain([missing])
      corrected, stats = correct_module.apply_replacements("原始字幕", replacements)

      self.assertEqual(replacements, [])
      self.assertEqual(used_paths, [])
      self.assertEqual(corrected, "原始字幕")
      self.assertEqual(stats, [])


class WhisperCppConversionTest(unittest.TestCase):
  def test_full_json_is_converted_to_canonical_words(self):
    fixture = {
      "result": {"language": "zh"},
      "model": {"type": "base"},
      "transcription": [{
        "offsets": {"from": 0, "to": 1000},
        "text": "测试",
        "tokens": [
          {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}, "p": 1.0},
          {"text": "测", "offsets": {"from": 100, "to": 500}, "p": 0.9},
          {"text": "试", "offsets": {"from": 500, "to": 900}, "p": 0.8},
        ],
      }],
    }
    with tempfile.TemporaryDirectory() as directory:
      input_path = Path(directory) / "raw.json"
      output_path = Path(directory) / "canonical.json"
      input_path.write_text(json.dumps(fixture), encoding="utf-8")
      transcribe_module.canonicalize_whisper_cpp(input_path, output_path)
      converted = json.loads(output_path.read_text(encoding="utf-8"))
      self.assertEqual(converted["engine"], "whisper.cpp")
      self.assertEqual(len(converted["segments"][0]["words"]), 2)
      self.assertEqual(converted["segments"][0]["words"][0]["start"], 0.1)


class PublishPackageTest(unittest.TestCase):
  def test_infer_content_date_prefers_content_identity(self):
    package = {
      "contentId": "2026-07-15_Day43",
      "runId": "fallback",
    }

    value = publish_module.infer_content_date(package, Path("05_exports/2026-07-14/final.mp4"))

    self.assertEqual(value, "2026-07-15")

  def test_markdown_lists_each_chapter_once(self):
    package = {
      "title": "测试",
      "description": "描述",
      "chapters": [
        {"time": "00:00", "title": "开始"},
        {"time": "00:30", "title": "继续"},
      ],
      "artifacts": {
        "video": "final.mp4",
        "cover3x4": "3x4.jpg",
        "cover4x3": "4x3.jpg",
        "srt": "final.srt",
      },
      "production": {
        "videoDurationSeconds": 60,
        "fileSizeBytes": 1024,
        "productionTotalMinutes": 5,
        "subtitleQc": "pass",
        "compliance": "pass",
        "statsRecorded": True,
        "systemVersion": "3.0.0",
      },
      "publishReady": True,
    }

    markdown = publish_module.markdown_content(package)

    self.assertEqual(markdown.count("00:00｜开始"), 1)
    self.assertEqual(markdown.count("00:30｜继续"), 1)


if __name__ == "__main__":
  unittest.main()
