from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

HISTORY_PATH = Path(__file__).resolve().parent / ".search_history.json"
MAX_HISTORY_ITEMS = 50

_LOCK = Lock()


def _read_history_unlocked() -> list[dict[str, Any]]:
  if not HISTORY_PATH.exists():
    return []
  try:
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
      return data[:MAX_HISTORY_ITEMS]
    return []
  except Exception:  # noqa: BLE001
    return []


def load_history() -> list[dict[str, Any]]:
  with _LOCK:
    return _read_history_unlocked()


def add_history_entry(
  request_url: str,
  resolved_url: str,
  summary_rows: list[dict[str, Any]],
  full_rows: list[dict[str, Any]],
) -> None:
  entry = {
    "id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "request_url": request_url,
    "resolved_url": resolved_url,
    "summary_rows": summary_rows,
    "full_rows": full_rows,
  }

  with _LOCK:
    history = _read_history_unlocked()
    history.insert(0, entry)
    limited = history[:MAX_HISTORY_ITEMS]
    HISTORY_PATH.write_text(
      json.dumps(limited, ensure_ascii=False, indent=2),
      encoding="utf-8",
    )
