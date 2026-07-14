from pathlib import Path
import argparse
import json
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
EDIT_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "video-diary-edit" / "scripts"
sys.path.insert(0, str(EDIT_SCRIPT_DIR))

from workflow_state import load_job, save_job, value_fingerprint


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def run_cover(args, aspect, base_frame, output_path, qc_path):
  command = [
    sys.executable,
    SCRIPT_DIR / "render-cover.py",
    "--date",
    args.date,
    "--route",
    args.route,
    "--style-version",
    args.style_version,
    "--day-label",
    args.day_label,
    "--base-frame",
    base_frame,
    "--output",
    output_path,
    "--aspect",
    aspect,
    "--qc-output",
    qc_path,
  ]
  if args.title:
    command.extend(["--title", args.title])
  if args.book_title:
    command.extend(["--book-title", args.book_title])
  if args.subtitle:
    command.extend(["--subtitle", args.subtitle])
  if args.note:
    command.extend(["--note", args.note])
  subprocess.run([str(value) for value in command], check=True)


def main():
  parser = argparse.ArgumentParser(description="Render matching 3:4 and 4:3 covers with one locked style version.")
  parser.add_argument("--date", required=True)
  parser.add_argument("--route", default="video-diary")
  parser.add_argument("--style-version", default="v1.3.1")
  parser.add_argument("--day-label", default="")
  parser.add_argument("--base-frame-3x4", required=True)
  parser.add_argument("--base-frame-4x3")
  parser.add_argument("--output-prefix", required=True)
  parser.add_argument("--title")
  parser.add_argument("--book-title")
  parser.add_argument("--subtitle", default="")
  parser.add_argument("--note", default="")
  args = parser.parse_args()

  root = Path.cwd()
  base_3x4 = resolve_path(root, args.base_frame_3x4)
  base_4x3 = resolve_path(root, args.base_frame_4x3) if args.base_frame_4x3 else base_3x4
  prefix = resolve_path(root, args.output_prefix)
  output_3x4 = prefix.parent / f"{prefix.name}_3x4.jpg"
  output_4x3 = prefix.parent / f"{prefix.name}_4x3.jpg"
  qc_dir = root / "04_videos" / args.date / "cover-qc"
  qc_3x4 = qc_dir / f"{prefix.name}_3x4_qc.json"
  qc_4x3 = qc_dir / f"{prefix.name}_4x3_qc.json"

  run_cover(args, "3:4", base_3x4, output_3x4, qc_3x4)
  run_cover(args, "4:3", base_4x3, output_4x3, qc_4x3)

  content = {
    "title": args.title or args.book_title or "",
    "subtitle": args.subtitle,
    "note": args.note,
    "dayLabel": args.day_label,
  }
  manifest = {
    "date": args.date,
    "route": args.route,
    "styleVersion": args.style_version,
    "contentHash": value_fingerprint(content),
    "content": content,
    "covers": {
      "3x4": str(output_3x4),
      "4x3": str(output_4x3),
    },
    "qc": {
      "3x4": str(qc_3x4),
      "4x3": str(qc_4x3),
    },
  }
  manifest_path = qc_dir / f"{prefix.name}_pair_manifest.json"
  manifest_path.parent.mkdir(parents=True, exist_ok=True)
  manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  job = load_job(root, args.date)
  job.setdefault("content", {}).update({key: value for key, value in content.items() if value})
  job.setdefault("style", {}).update({"coverRoute": args.route, "coverVersion": args.style_version})
  job.setdefault("artifacts", {}).update({
    "cover3x4": str(output_3x4),
    "cover4x3": str(output_4x3),
    "coverPairManifest": str(manifest_path),
  })
  job.setdefault("quality", {})["cover"] = {"status": "pass", "manifest": str(manifest_path)}
  save_job(root, args.date, job)

  if job.get("artifacts", {}).get("correctedSrt"):
    subprocess.run(
      [sys.executable, EDIT_SCRIPT_DIR / "build-review-pack.py", "--date", args.date],
      check=True,
    )

  print(f"cover_3x4={output_3x4}")
  print(f"cover_4x3={output_4x3}")
  print(f"manifest={manifest_path}")
  print("qc=pass")


if __name__ == "__main__":
  main()
