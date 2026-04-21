# Font Inspector

Tool that detects which fonts and font variants are used on a web page by URL.

## What it does

- opens a page in a real browser (headless mode);
- reads computed styles from visible text elements;
- reports font family + weight + style combinations;
- prints grouped output (family -> list of used variants).

## Setup

```bash
python -m pip install -r requirements.txt
```

You need at least one installed browser: Chrome, Edge, or Firefox.

## Usage

### Web service (UI)

Run:

```bash
python app.py
```

Open in browser:

```text
http://127.0.0.1:8000
```

On the page:
- paste URL into the input field;
- click the "Запустить" button;
- get a table with `font`, `weight/style`, and mention count.

### CLI

```bash
python font_inspector.py https://example.com
```

JSON output:

```bash
python font_inspector.py https://example.com --json
```

Force browser:

```bash
python font_inspector.py https://example.com --browser edge
```

## Notes

- The tool analyzes rendered styles, so it is closer to "what users actually see".
- Dynamic content loaded after initial page load may require re-run with a larger timeout.

## Docker

Build image:

```bash
docker build -t font-inspector .
```

Run container:

```bash
docker run --rm -p 8000:8000 font-inspector
```

Open in browser:

```text
http://127.0.0.1:8000
```
