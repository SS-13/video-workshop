from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


TOOLS_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = TOOLS_ROOT.parent / ".codex" / "skills" / "video-diary-cover" / "scripts" / "render-cover.py"
SPEC = importlib.util.spec_from_file_location("render_cover", SCRIPT_PATH)
RENDER_COVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER_COVER)


class CoverGlyphQcTest(unittest.TestCase):
  def font_path(self):
    for value in RENDER_COVER.DISPLAY_FONTS:
      if Path(value).is_file():
        return value
    self.skipTest("No configured cover font is installed")

  def test_font_supports_ascii_and_rejects_unmapped_codepoint(self):
    from PIL import ImageFont

    font = ImageFont.truetype(self.font_path(), 64)

    self.assertEqual(RENDER_COVER.missing_glyphs(font, "ABC"), [])
    self.assertEqual(RENDER_COVER.missing_glyphs(font, "𠀀"), ["𠀀"])

  def test_render_command_fails_cover_qc_for_missing_title_glyph(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      base = root / "base.jpg"
      output = root / "cover.jpg"
      qc_path = root / "qc.json"
      Image.new("RGB", (1080, 1440), (30, 30, 30)).save(base)

      result = subprocess.run(
        [
          sys.executable,
          str(SCRIPT_PATH),
          "--date", "2030-01-01",
          "--base-frame", str(base),
          "--output", str(output),
          "--title", "𠀀",
          "--qc-output", str(qc_path),
        ],
        text=True,
        capture_output=True,
        check=False,
      )

      self.assertNotEqual(result.returncode, 0)
      self.assertIn("missing_glyph", result.stderr + result.stdout)
      self.assertEqual(json.loads(qc_path.read_text(encoding="utf-8"))["passed"], False)

  def test_v131_fits_long_mixed_title(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      base = root / "base.jpg"
      output = root / "cover.jpg"
      qc_path = root / "qc.json"
      Image.new("RGB", (1080, 1440), (30, 30, 30)).save(base)

      result = subprocess.run(
        [
          sys.executable,
          str(SCRIPT_PATH),
          "--date", "2030-01-01",
          "--style-version", "v1.3.1",
          "--base-frame", str(base),
          "--output", str(output),
          "--title", "在WAIC，看见未来，也看见好问题",
          "--qc-output", str(qc_path),
        ],
        cwd=TOOLS_ROOT.parent,
        text=True,
        capture_output=True,
        check=False,
      )

      self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
      self.assertTrue(json.loads(qc_path.read_text(encoding="utf-8"))["passed"])


if __name__ == "__main__":
  unittest.main()
