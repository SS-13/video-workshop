from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import tempfile


JOB_SCHEMA_VERSION = 2
FINGERPRINT_SAMPLE_BYTES = 1024 * 1024


def now_iso():
  return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def file_fingerprint(path):
  path = Path(path)
  stat = path.stat()
  digest = hashlib.sha256()
  digest.update(str(stat.st_size).encode("utf-8"))
  digest.update(str(stat.st_mtime_ns).encode("utf-8"))

  with path.open("rb") as file:
    digest.update(file.read(FINGERPRINT_SAMPLE_BYTES))
    if stat.st_size > FINGERPRINT_SAMPLE_BYTES:
      file.seek(max(0, stat.st_size - FINGERPRINT_SAMPLE_BYTES))
      digest.update(file.read(FINGERPRINT_SAMPLE_BYTES))

  return {
    "path": str(path.resolve()),
    "size": stat.st_size,
    "mtimeNs": stat.st_mtime_ns,
    "sha256Sample": digest.hexdigest(),
  }


def value_fingerprint(value):
  payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stage_cache_key(inputs, params=None):
  normalized_inputs = []
  for value in inputs:
    path = Path(value)
    normalized_inputs.append(file_fingerprint(path) if path.exists() else {"path": str(path), "missing": True})
  return value_fingerprint({"inputs": normalized_inputs, "params": params or {}})


def job_path(root, date):
  return Path(root) / "04_videos" / date / "job.json"


def new_job(date, column):
  timestamp = now_iso()
  return {
    "schemaVersion": JOB_SCHEMA_VERSION,
    "date": date,
    "column": column,
    "engine": "v2",
    "status": "created",
    "createdAt": timestamp,
    "updatedAt": timestamp,
    "source": {},
    "content": {},
    "style": {},
    "requests": {
      "coverCardSeconds": 0.0,
      "insertPlan": [],
    },
    "artifacts": {},
    "quality": {},
    "stages": {},
  }


def load_job(root, date, column="video-diary"):
  path = job_path(root, date)
  if not path.exists():
    return new_job(date, column)

  data = json.loads(path.read_text(encoding="utf-8"))
  data.setdefault("schemaVersion", JOB_SCHEMA_VERSION)
  data.setdefault("column", column)
  data.setdefault("engine", "v2")
  data.setdefault("status", "created")
  data.setdefault("source", {})
  data.setdefault("content", {})
  data.setdefault("style", {})
  data.setdefault("requests", {"coverCardSeconds": 0.0, "insertPlan": []})
  data.setdefault("artifacts", {})
  data.setdefault("quality", {})
  data.setdefault("stages", {})
  return data


def save_job(root, date, job):
  path = job_path(root, date)
  path.parent.mkdir(parents=True, exist_ok=True)
  job["schemaVersion"] = JOB_SCHEMA_VERSION
  job["updatedAt"] = now_iso()

  descriptor, temp_name = tempfile.mkstemp(prefix="job-", suffix=".json", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      json.dump(job, file, ensure_ascii=False, indent=2)
      file.write("\n")
    os.replace(temp_name, path)
  finally:
    if os.path.exists(temp_name):
      os.unlink(temp_name)
  return path


def stage_is_current(job, name, cache_key, outputs):
  stage = job.get("stages", {}).get(name, {})
  if stage.get("status") != "completed" or stage.get("cacheKey") != cache_key:
    return False
  return all(Path(output).exists() for output in outputs)


def record_stage(job, name, cache_key, outputs, elapsed_seconds, extra=None):
  job.setdefault("stages", {})[name] = {
    "status": "completed",
    "cacheKey": cache_key,
    "outputs": [str(Path(output)) for output in outputs],
    "elapsedSeconds": round(float(elapsed_seconds), 3),
    "completedAt": now_iso(),
    **(extra or {}),
  }
