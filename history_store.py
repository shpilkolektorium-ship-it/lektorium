from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

HISTORY_PATH = Path(__file__).resolve().parent / ".search_history.json"
MAX_HISTORY_ITEMS = 50

_LOCK = Lock()


def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()


def _entry_defaults(entry: dict[str, Any]) -> dict[str, Any]:
  request_url = str(entry.get("request_url", "") or "")
  resolved_url = str(entry.get("resolved_url", "") or "")
  summary_rows = entry.get("summary_rows", [])
  full_rows = entry.get("full_rows", [])
  created_at = str(entry.get("created_at", "") or _now_iso())
  updated_at = str(entry.get("updated_at", "") or created_at)

  return {
    "id": str(entry.get("id", datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"))),
    "created_at": created_at,
    "updated_at": updated_at,
    "request_url": request_url,
    "resolved_url": resolved_url,
    "summary_rows": summary_rows if isinstance(summary_rows, list) else [],
    "full_rows": full_rows if isinstance(full_rows, list) else [],
    "pinned": bool(entry.get("pinned", False)),
    "starred": bool(entry.get("starred", False)),
    "is_empty": bool(entry.get("is_empty", not request_url and not resolved_url)),
  }


def _sort_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return sorted(entries, key=lambda item: str(item.get("updated_at", "")), reverse=True)


def _write_history_unlocked(entries: list[dict[str, Any]]) -> None:
  limited = _sort_entries(entries)[:MAX_HISTORY_ITEMS]
  HISTORY_PATH.write_text(
    json.dumps(limited, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )


def _read_history_unlocked() -> list[dict[str, Any]]:
  if not HISTORY_PATH.exists():
    return []
  try:
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
      normalized = [_entry_defaults(item) for item in data if isinstance(item, dict)]
      return _sort_entries(normalized)[:MAX_HISTORY_ITEMS]
    return []
  except Exception:  # noqa: BLE001
    return []


def load_history() -> list[dict[str, Any]]:
  with _LOCK:
    return _read_history_unlocked()


def add_history_entry(
  chat_id: str | None,
  request_url: str,
  resolved_url: str,
  summary_rows: list[dict[str, Any]],
  full_rows: list[dict[str, Any]],
) -> str:
  now_iso = _now_iso()

  with _LOCK:
    history = _read_history_unlocked()
    if chat_id:
      for item in history:
        if item.get("id") == chat_id:
          item["request_url"] = request_url
          item["resolved_url"] = resolved_url
          item["summary_rows"] = summary_rows
          item["full_rows"] = full_rows
          item["updated_at"] = now_iso
          item["is_empty"] = False
          _write_history_unlocked(history)
          return str(item["id"])

    entry_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    history.append(
      _entry_defaults(
        {
          "id": entry_id,
          "created_at": now_iso,
          "updated_at": now_iso,
          "request_url": request_url,
          "resolved_url": resolved_url,
          "summary_rows": summary_rows,
          "full_rows": full_rows,
          "is_empty": False,
        }
      )
    )
    _write_history_unlocked(history)
    return entry_id


def create_empty_chat() -> str:
  now_iso = _now_iso()
  chat_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
  entry = _entry_defaults(
    {
      "id": chat_id,
      "created_at": now_iso,
      "updated_at": now_iso,
      "request_url": "",
      "resolved_url": "",
      "summary_rows": [],
      "full_rows": [],
      "is_empty": True,
    }
  )
  with _LOCK:
    history = _read_history_unlocked()
    history.append(entry)
    _write_history_unlocked(history)
  return chat_id


def toggle_pinned(chat_id: str) -> bool:
  with _LOCK:
    history = _read_history_unlocked()
    for item in history:
      if item.get("id") == chat_id:
        item["pinned"] = not bool(item.get("pinned", False))
        item["updated_at"] = _now_iso()
        _write_history_unlocked(history)
        return True
  return False


def toggle_starred(chat_id: str) -> bool:
  with _LOCK:
    history = _read_history_unlocked()
    for item in history:
      if item.get("id") == chat_id:
        item["starred"] = not bool(item.get("starred", False))
        item["updated_at"] = _now_iso()
        _write_history_unlocked(history)
        return True
  return False


def delete_chat(chat_id: str) -> bool:
  with _LOCK:
    history = _read_history_unlocked()
    filtered = [item for item in history if item.get("id") != chat_id]
    if len(filtered) == len(history):
      return False
    _write_history_unlocked(filtered)
    return True
