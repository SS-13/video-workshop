"""Small JSON Schema subset validator for public control-plane contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json


TYPE_MAP = {
  "object": dict,
  "array": list,
  "string": str,
  "integer": int,
  "number": (int, float),
  "boolean": bool,
  "null": type(None),
}


def matches_type(value: Any, type_name: str) -> bool:
  if type_name not in TYPE_MAP:
    return False
  if type_name in {"integer", "number"} and isinstance(value, bool):
    return False
  return isinstance(value, TYPE_MAP[type_name])


def load_json(path: Path) -> Dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def validate_value(value: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
  errors: List[str] = []
  expected_type = schema.get("type")
  if expected_type:
    allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
    matches = any(matches_type(value, type_name) for type_name in allowed_types)
    if not matches:
      errors.append(f"{path}: expected {allowed_types}, got {type(value).__name__}")
      return errors

  if "enum" in schema and value not in schema["enum"]:
    errors.append(f"{path}: value {value!r} is not in enum")

  if isinstance(value, dict):
    for key in schema.get("required", []):
      if key not in value:
        errors.append(f"{path}: missing required property {key}")
    properties = schema.get("properties", {})
    for key, child in value.items():
      if key in properties:
        errors.extend(validate_value(child, properties[key], f"{path}.{key}"))

  if isinstance(value, list) and "items" in schema:
    for index, item in enumerate(value):
      errors.extend(validate_value(item, schema["items"], f"{path}[{index}]"))

  if isinstance(value, (int, float)) and not isinstance(value, bool):
    if "minimum" in schema and value < schema["minimum"]:
      errors.append(f"{path}: {value} is below minimum {schema['minimum']}")

  return errors


def validate_contract_examples(root: Path) -> Dict[str, Any]:
  contract_root = root / "00_system" / "contracts"
  pairs = [
    ("run", contract_root / "schemas" / "run.schema.json", contract_root / "examples" / "run.json"),
    ("artifact", contract_root / "schemas" / "artifact.schema.json", contract_root / "examples" / "artifact.json"),
    (
      "publish-package",
      contract_root / "schemas" / "publish-package.schema.json",
      contract_root / "examples" / "publish-package.json",
    ),
  ]
  results = []
  all_errors: List[Dict[str, Any]] = []
  for name, schema_path, example_path in pairs:
    if not schema_path.exists() or not example_path.exists():
      missing = []
      if not schema_path.exists():
        missing.append(str(schema_path.relative_to(root)))
      if not example_path.exists():
        missing.append(str(example_path.relative_to(root)))
      errors = [f"missing file: {path}" for path in missing]
    else:
      errors = validate_value(load_json(example_path), load_json(schema_path))
    results.append({"contract": name, "valid": not errors, "errors": errors})
    for error in errors:
      all_errors.append({"contract": name, "error": error})
  return {
    "valid": not all_errors,
    "contracts": results,
    "errors": all_errors,
  }
