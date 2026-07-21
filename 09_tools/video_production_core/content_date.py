"""Resolve the default content date without changing explicit user dates."""

from __future__ import annotations

from datetime import datetime, timedelta


DEFAULT_CONTENT_DAY_BOUNDARY_HOUR = 9


def default_content_date(
  now: datetime | None = None,
  boundary_hour: int = DEFAULT_CONTENT_DAY_BOUNDARY_HOUR,
) -> str:
  """Return the local content date used when the user omits a date."""
  if boundary_hour < 0 or boundary_hour > 23:
    raise ValueError("Content day boundary hour must be between 0 and 23.")

  local_now = now or datetime.now().astimezone()
  if local_now.tzinfo is None:
    local_now = local_now.astimezone()
  if local_now.hour < boundary_hour:
    local_now -= timedelta(days=1)
  return local_now.date().isoformat()
