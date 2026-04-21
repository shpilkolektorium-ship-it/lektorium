from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import Flask, render_template, request

from font_inspector import detect_fonts
from history_store import add_history_entry, load_history

app = Flask(__name__)


def normalize_url(raw_url: str) -> str:
  value = raw_url.strip()
  if not value:
    return value

  parsed = urlparse(value)
  if not parsed.scheme:
    return f"https://{value}"
  return value


@app.route("/", methods=["GET", "POST"])
def index():
  page_url = ""
  summary_rows: list[dict[str, str | int]] = []
  full_rows: list[dict[str, str | int]] = []
  history_entries = load_history()
  error = ""

  if request.method == "POST":
    page_url = request.form.get("url", "")
    normalized_url = normalize_url(page_url)

    if not normalized_url:
      error = "Введите ссылку на страницу."
    else:
      try:
        data = detect_fonts(normalized_url, timeout=25, browser=None)
        summary_rows = data.get("combinations_in_use", [])
        full_rows = data.get("element_records", [])
        add_history_entry(
          request_url=normalized_url,
          resolved_url=data.get("url", normalized_url),
          summary_rows=summary_rows,
          full_rows=full_rows,
        )
        history_entries = load_history()
      except Exception as exc:  # noqa: BLE001
        error = f"Не удалось проанализировать страницу: {exc}"

  return render_template(
    "index.html",
    page_url=page_url,
    summary_rows=summary_rows,
    full_rows=full_rows,
    history_entries=history_entries,
    error=error,
  )


if __name__ == "__main__":
  host = os.environ.get("HOST", "0.0.0.0")
  port = int(os.environ.get("PORT", "8000"))
  debug = os.environ.get("FLASK_DEBUG", "0") == "1"
  app.run(host=host, port=port, debug=debug)
