from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from flask import Flask, render_template, request

from font_inspector import detect_fonts
from history_store import (
  add_history_entry,
  delete_chat,
  load_history,
  toggle_pinned,
  toggle_starred,
)

app = Flask(__name__)


def normalize_url(raw_url: str) -> str:
  value = raw_url.strip()
  if not value:
    return value

  parsed = urlparse(value)
  if not parsed.scheme:
    return f"https://{value}"
  return value


def group_full_rows(full_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
  grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
  for row in full_rows:
    key = (
      str(row.get("font_family", "unknown")),
      str(row.get("font_weight_name", "Unknown")),
      str(row.get("font_weight", "unknown")),
      str(row.get("font_style", "normal")),
    )
    grouped[key].append(row)

  result: list[dict[str, Any]] = []
  for index, (key, rows) in enumerate(grouped.items(), start=1):
    font_family, font_weight_name, font_weight, font_style = key
    result.append(
      {
        "group_id": f"group-{index}",
        "font_family": font_family,
        "font_weight_name": font_weight_name,
        "font_weight": font_weight,
        "font_style": font_style,
        "rows": rows,
        "rows_count": len(rows),
      }
    )

  result.sort(key=lambda item: item["rows_count"], reverse=True)
  return result


def parse_iso_datetime(value: str) -> datetime:
  raw = (value or "").strip()
  if not raw:
    return datetime.now(timezone.utc)
  normalized = raw.replace("Z", "+00:00")
  try:
    parsed = datetime.fromisoformat(normalized)
  except ValueError:
    return datetime.now(timezone.utc)
  if parsed.tzinfo is None:
    return parsed.replace(tzinfo=timezone.utc)
  return parsed.astimezone(timezone.utc)


def history_sections(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  visible_entries = [item for item in entries if not bool(item.get("is_empty", False))]
  now = datetime.now(timezone.utc)
  today = now.date()
  yesterday = today - timedelta(days=1)
  week_border = today - timedelta(days=7)

  pinned = [item for item in visible_entries if item.get("pinned")]
  regular = [item for item in visible_entries if not item.get("pinned")]

  buckets: dict[str, list[dict[str, Any]]] = {
    "Сегодня": [],
    "Вчера": [],
    "На прошлой неделе": [],
    "В прошлом месяце": [],
  }

  for item in regular:
    updated = parse_iso_datetime(str(item.get("updated_at", ""))).date()
    if updated == today:
      buckets["Сегодня"].append(item)
    elif updated == yesterday:
      buckets["Вчера"].append(item)
    elif updated >= week_border:
      buckets["На прошлой неделе"].append(item)
    else:
      buckets["В прошлом месяце"].append(item)

  grouped = [{"title": title, "items": items} for title, items in buckets.items() if items]
  return pinned, grouped


def get_chat_by_id(entries: list[dict[str, Any]], chat_id: str) -> dict[str, Any] | None:
  for entry in entries:
    if entry.get("id") == chat_id:
      return entry
  return None


@app.route("/", methods=["GET", "POST"])
def index():
  page_url = ""
  active_chat_id = request.args.get("chat_id", "").strip()
  summary_rows: list[dict[str, str | int]] = []
  full_rows: list[dict[str, str | int]] = []
  grouped_full_rows: list[dict[str, Any]] = []
  history_entries = load_history()
  pinned_chats, dated_groups = history_sections(history_entries)
  error = ""

  if request.method == "POST":
    history_action = request.form.get("history_action", "").strip()
    chat_id = request.form.get("chat_id", "").strip()

    if history_action:
      if history_action == "new":
        active_chat_id = ""
        page_url = ""
        summary_rows = []
        full_rows = []
        grouped_full_rows = []
      elif history_action == "pin" and chat_id:
        toggle_pinned(chat_id)
        active_chat_id = active_chat_id or chat_id
      elif history_action == "star" and chat_id:
        toggle_starred(chat_id)
        active_chat_id = active_chat_id or chat_id
      elif history_action == "delete" and chat_id:
        delete_chat(chat_id)
        if active_chat_id == chat_id:
          active_chat_id = ""
      elif history_action == "select" and chat_id:
        active_chat_id = chat_id

      history_entries = load_history()
      pinned_chats, dated_groups = history_sections(history_entries)
    else:
      page_url = request.form.get("url", "")
      active_chat_id = request.form.get("active_chat_id", "").strip()
      normalized_url = normalize_url(page_url)

      if not normalized_url:
        error = "Введите ссылку на страницу."
      else:
        try:
          data = detect_fonts(normalized_url, timeout=25, browser=None)
          summary_rows = data.get("combinations_in_use", [])
          full_rows = data.get("element_records", [])
          grouped_full_rows = group_full_rows(full_rows)
          active_chat_id = add_history_entry(
            chat_id=active_chat_id if active_chat_id else None,
            request_url=normalized_url,
            resolved_url=data.get("url", normalized_url),
            summary_rows=summary_rows,
            full_rows=full_rows,
          )
          history_entries = load_history()
          pinned_chats, dated_groups = history_sections(history_entries)
        except Exception as exc:  # noqa: BLE001
          error = f"Не удалось проанализировать страницу: {exc}"

  for item in history_entries:
    rows = item.get("full_rows", [])
    item["grouped_full_rows"] = group_full_rows(rows if isinstance(rows, list) else [])
    item["title"] = item.get("request_url") or "Новый чат"

  if active_chat_id:
    active_item = get_chat_by_id(history_entries, active_chat_id)
    if active_item is not None:
      page_url = str(active_item.get("request_url", "") or "")
      summary_rows = active_item.get("summary_rows", [])
      full_rows = active_item.get("full_rows", [])
      grouped_full_rows = active_item.get("grouped_full_rows", [])
    else:
      active_chat_id = ""
  elif summary_rows or full_rows:
    pass
  elif history_entries:
    active_chat_id = str(history_entries[0].get("id", ""))
    active_item = get_chat_by_id(history_entries, active_chat_id)
    if active_item is not None:
      page_url = str(active_item.get("request_url", "") or "")
      summary_rows = active_item.get("summary_rows", [])
      full_rows = active_item.get("full_rows", [])
      grouped_full_rows = active_item.get("grouped_full_rows", [])

  return render_template(
    "index.html",
    page_url=page_url,
    active_chat_id=active_chat_id,
    summary_rows=summary_rows,
    full_rows=full_rows,
    grouped_full_rows=grouped_full_rows,
    history_entries=history_entries,
    pinned_chats=pinned_chats,
    dated_groups=dated_groups,
    error=error,
  )


if __name__ == "__main__":
  host = os.environ.get("HOST", "0.0.0.0")
  port = int(os.environ.get("PORT", "8000"))
  debug = os.environ.get("FLASK_DEBUG", "0") == "1"
  app.run(host=host, port=port, debug=debug)
