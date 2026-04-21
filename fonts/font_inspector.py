#!/usr/bin/env python3
"""
Inspect fonts used on a web page.

Usage:
    python font_inspector.py https://example.com
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait


SCRIPT = r"""
const hiddenTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "META", "LINK", "TITLE", "HEAD"]);

function firstFamily(fontFamily) {
  if (!fontFamily) return "unknown";
  const first = fontFamily.split(",")[0].trim();
  return first.replace(/^['"]|['"]$/g, "") || "unknown";
}

function isVisible(style) {
  return style.display !== "none" &&
         style.visibility !== "hidden" &&
         style.opacity !== "0";
}

function normalizeWeightValue(weightRaw) {
  if (!weightRaw) return "400";
  const lowered = String(weightRaw).toLowerCase().trim();
  if (lowered === "normal") return "400";
  if (lowered === "bold") return "700";
  return String(weightRaw).trim();
}

function weightName(weightValue) {
  const numeric = Number.parseInt(weightValue, 10);
  if (Number.isNaN(numeric)) return "Unknown";
  if (numeric <= 150) return "Thin";
  if (numeric <= 250) return "ExtraLight";
  if (numeric <= 350) return "Light";
  if (numeric <= 450) return "Normal";
  if (numeric <= 550) return "Medium";
  if (numeric <= 650) return "SemiBold";
  if (numeric <= 750) return "Bold";
  if (numeric <= 850) return "ExtraBold";
  return "Black";
}

function normalizeSpace(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function ownTextContent(el) {
  let combined = "";
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) combined += ` ${node.textContent || ""}`;
  }
  return normalizeSpace(combined);
}

function cssPath(el) {
  if (!(el instanceof Element)) return "";
  const path = [];
  let current = el;
  while (current && current.nodeType === Node.ELEMENT_NODE && path.length < 8) {
    let selector = current.nodeName.toLowerCase();
    if (current.id) {
      selector += `#${current.id}`;
      path.unshift(selector);
      break;
    }

    let sibling = current;
    let nth = 1;
    while ((sibling = sibling.previousElementSibling)) {
      if (sibling.nodeName.toLowerCase() === selector) nth += 1;
    }
    selector += `:nth-of-type(${nth})`;
    path.unshift(selector);
    current = current.parentElement;
  }
  return path.join(" > ");
}

function blockLink(el, textValue) {
  const base = window.location.href.split("#")[0];
  const withId = el.closest("[id]");
  if (withId && withId.id) {
    return `${base}#${encodeURIComponent(withId.id)}`;
  }

  if (textValue.length >= 10) {
    const fragment = encodeURIComponent(textValue.slice(0, 140));
    return `${base}#:~:text=${fragment}`;
  }

  return base;
}

const usage = new Map();
const records = [];
const elements = document.querySelectorAll("*");

for (const el of elements) {
  if (hiddenTags.has(el.tagName)) continue;

  const style = window.getComputedStyle(el);
  if (!isVisible(style)) continue;

  const text = ownTextContent(el);
  if (!text) continue;

  const primaryFamily = firstFamily(style.fontFamily);
  const stack = style.fontFamily || "unknown";
  const weight = normalizeWeightValue(style.fontWeight || "400");
  const weightLabel = weightName(weight);
  const fontStyle = style.fontStyle || "normal";
  const key = `${primaryFamily}|||${weight}|||${fontStyle}`;

  if (!usage.has(key)) {
    usage.set(key, {
      font_family: primaryFamily,
      font_stack: stack,
      font_weight: weight,
      font_weight_name: weightLabel,
      font_style: fontStyle,
      elements_count: 0
    });
  }
  usage.get(key).elements_count += 1;

  const preview = text.slice(0, 140);
  records.push({
    font_family: primaryFamily,
    font_stack: stack,
    font_weight: weight,
    font_weight_name: weightLabel,
    font_style: fontStyle,
    elements_count: 1,
    block_link: blockLink(el, preview),
    block_selector: cssPath(el),
    block_text_preview: preview
  });
}

const loaded = [];
if (document.fonts && document.fonts.size > 0) {
  for (const entry of document.fonts) {
    loaded.push({
      family: entry.family || "unknown",
      weight: entry.weight || "unknown",
      style: entry.style || "unknown",
      status: entry.status || "unknown"
    });
  }
}

return {
  url: window.location.href,
  total_elements_scanned: elements.length,
  combinations_in_use: Array.from(usage.values()).sort(
    (a, b) => b.elements_count - a.elements_count
  ),
  element_records: records,
  loaded_fonts: loaded
};
"""


def build_driver(browser: str, timeout: int):
  if browser == "chrome":
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    chrome_bin = os.environ.get("CHROME_BIN") or shutil.which("chromium") or shutil.which("google-chrome")
    if chrome_bin:
      options.binary_location = chrome_bin
    driver = webdriver.Chrome(options=options)
  elif browser == "edge":
    options = EdgeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = webdriver.Edge(options=options)
  elif browser == "firefox":
    options = FirefoxOptions()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options)
  else:
    raise ValueError(f"Unsupported browser: {browser}")

  driver.set_page_load_timeout(timeout)
  return driver


def detect_fonts(url: str, timeout: int, browser: str | None) -> dict[str, Any]:
  last_error: Exception | None = None
  candidates = [browser] if browser else ["chrome", "edge", "firefox"]

  for candidate in candidates:
    try:
      driver = build_driver(candidate, timeout)
      break
    except Exception as exc:  # noqa: BLE001
      last_error = exc
      driver = None
  else:
    if last_error is not None:
      raise RuntimeError(
        "Could not start a browser driver. Install Chrome/Edge/Firefox and WebDriver."
      ) from last_error
    raise RuntimeError("Could not start a browser driver.")

  try:
    driver.get(url)
    WebDriverWait(driver, timeout).until(
      lambda drv: drv.execute_script("return document.readyState") == "complete"
    )
    result = driver.execute_script(SCRIPT)
    result["browser"] = candidate
    result["summary"] = summarize(result.get("combinations_in_use", []))
    return result
  finally:
    driver.quit()


def summarize(combinations: list[dict[str, Any]]) -> dict[str, list[str]]:
  by_family: dict[str, set[str]] = defaultdict(set)
  for item in combinations:
    key = item.get("font_family", "unknown")
    weight = str(item.get("font_weight", "unknown"))
    font_style = str(item.get("font_style", "normal"))
    by_family[key].add(f"{weight}/{font_style}")

  return {
    family: sorted(values, key=lambda v: (v.split("/")[0], v.split("/")[1]))
    for family, values in sorted(by_family.items(), key=lambda x: x[0].lower())
  }


def print_human_readable(data: dict[str, Any]) -> None:
  print(f"URL: {data['url']}")
  print(f"Browser: {data['browser']}")
  print(f"Scanned elements: {data['total_elements_scanned']}")
  print("")
  print("Fonts in use (grouped):")
  if not data["summary"]:
    print("  (no visible text nodes found)")
  for family, variants in data["summary"].items():
    print(f"  - {family}: {', '.join(variants)}")

  if data.get("combinations_in_use"):
    print("")
    print("Detailed combinations:")
    for item in data["combinations_in_use"]:
      print(
        f"  - {item['font_family']} | weight={item['font_weight']} ({item['font_weight_name']}) | "
        f"style={item['font_style']} | elements={item['elements_count']}"
      )


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Detect fonts and font weights used on a web page by URL."
  )
  parser.add_argument("url", help="Target page URL (for example, https://example.com)")
  parser.add_argument(
    "--browser",
    choices=["chrome", "edge", "firefox"],
    default=None,
    help="Force a specific browser driver (default: auto-detect).",
  )
  parser.add_argument(
    "--timeout",
    type=int,
    default=20,
    help="Page load and wait timeout in seconds (default: 20).",
  )
  parser.add_argument(
    "--json",
    action="store_true",
    help="Print full JSON output instead of human-readable text.",
  )
  return parser.parse_args()


def main() -> int:
  args = parse_args()
  try:
    data = detect_fonts(args.url, args.timeout, args.browser)
  except WebDriverException as exc:
    print(f"WebDriver error: {exc}", file=sys.stderr)
    return 2
  except Exception as exc:  # noqa: BLE001
    print(f"Error: {exc}", file=sys.stderr)
    return 1

  if args.json:
    print(json.dumps(data, ensure_ascii=False, indent=2))
  else:
    print_human_readable(data)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
