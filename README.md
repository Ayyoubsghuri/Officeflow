# OfficeFlow

Offline-first desktop automation for Excel, PDF and Word documents.
Select files or folders, configure a tool, preview what will happen, run it in the background,
and chain tools into reusable workflows. Original files are never modified unless you explicitly
choose "move".

## Quick start

Build the interface once (needs Node.js 20+), then start the app:

```bash
pip install -r requirements.txt
```

```bash
cd frontend
npm install
npm run build
```

```bash
cd ..
python -m officeflow
```

`npm run build` exports the Next.js interface and copies it into `officeflow/web/`, where the Python
process serves it. On Windows and macOS OfficeFlow opens in its own frameless window (pywebview, using
the WebView2 runtime that ships with Windows 10/11). Elsewhere, or with `python -m officeflow --browser`,
it opens in the default browser.

### Development

Run the engine and the interface separately to get hot reload:

```bash
python -m officeflow --serve --port 8765 --token dev
```

```bash
cd frontend
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8765 NEXT_PUBLIC_API_TOKEN=dev npm run dev
```

Then open http://localhost:3000.

### Tests

```bash
python -m pytest
```

```bash
cd frontend
npm run build
npm run e2e
```

`pytest` covers the engines, the tools, workflows, the HTTP API and the AI assistant with a fake model (82 tests; no real AI calls). `npm run e2e` starts the real
server with sample files and drives the built interface in Chromium through Playwright (organizer
preview and run, workflow building rules, saving, the AI assistant with a stand-in model, every page,
no browser errors).

## Status by phase

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, interface, history, logs, settings, themes | **Done** |
| 2 | Excel automation (10 tools) | **Done** |
| 3 | PDF automation incl. Smart Organizer (9 tools) | **Done**, except OCR (see below) |
| 4 | Word automation (7 tools) | **Done** |
| 5 | Cross-document automation | Partly: workflows already chain Excel → Word → PDF; dedicated cross tools (PDF data → Excel, PDF vs Excel checks) not started |
| 6 | Workflow Builder | **Done** |
| 7 | Installer (PyInstaller), optimisation | Not started |

Not implemented yet: OCR for scanned PDFs and "make PDF searchable", the dedicated cross-document tools,
optional local AI (Ollama), and the Windows installer. Scanned PDFs are detected and reported ("no text
found") rather than processed.

### If a page stays blank or shows an error
Close every OfficeFlow window and start it again (an engine left running from before an update causes a
version warning). To see the exact error, start with `python -m officeflow --debug`, right-click the page and
choose **Inspect → Console**.

### Not verified on Windows yet
This repository was developed and tested on Linux. The engines, API and interface are covered by the
tests above, but the parts that only exist inside the native window could not be run here:
the frameless window itself, its minimise/maximise/close buttons and edge resizing, native file dialogs,
dragging files from Explorer onto the drop zones, and Word → PDF through Microsoft Word (LibreOffice
conversion is tested). They are written against pywebview's documented API; check them on Windows before
relying on them.

## Interface

- **Dashboard:** the 3D stack of glass folders (one per tool) from the design reference. Hover to pick a
  tool, click to open it; ← / → or the round handle also move the selection. Below it, the deck shows
  recent activity, saved workflows and the selected tool as a green folder (formats, last run, success rate).
- **Custom title bar:** the window has no Windows header. The app's top bar is the title bar: drag it to
  move the window, double-click to maximise, use its own minimise/maximise/close buttons, and resize from
  the window edges.
- **Toolboxes and tool pages:** every tool shows what it reads and writes, takes files or folders
  (buttons, native dialogs, or drag-and-drop from Explorer), previews without touching anything, runs in
  the background with live progress and cancellation, and lists the result.
- **Workflow Builder** — see below. **History**, **Logs**, **Settings** (theme, output folder, plugins,
  PDF converter status).

### Workflow Builder
A node canvas in the style of the second design reference. A **Files & folders** start node feeds the
first step, and each step passes its output files to the next.

- Every node shows its formats: **IN** what it reads, **OUT** what it writes. The start node shows the
  file types actually found in your inputs.
- **The flow only offers what can follow.** The *Add step* menu lists only tools that can read the files
  arriving at that point. The "+" on a connector inserts a step that can read the previous step's files
  *and* produce what the next step needs. Moving or removing a step is disabled, with the reason shown,
  when it would leave a step unable to read its input.
- Drag nodes, pan the canvas, zoom with the wheel or the left tool bar, tidy the layout, undo/redo every
  change (Ctrl+Z / Ctrl+Shift+Z), Delete removes the selected step, Ctrl+S saves.
- After a run each node shows Done / Remarks / Failed / Not run and how many files it produced.
- Saved workflows open from the dashboard or the builder; the badge shows **Draft** until saved.

## AI assistant (optional)

Choose a provider in **Settings → AI assistant** and paste its API key:

- **Anthropic (Claude)** — default model Claude Opus 5.5; Sonnet 5.5 and Haiku 5.5 can be chosen.
- **OpenAI** — pick any text model available to your account (**Load my models** fetches the list of model
  names; default `gpt-5`). Requests are sent with `store=false`.

Each provider keeps its own key; switching provider does not delete the other key. The assistant does two
things only:

- **Create a workflow** from a description. The answer is checked against the real tool list (tool ids,
  settings, and that every step can read the previous step's files); problems are sent back for a fix
  automatically. The result opens in the Workflow Builder as an unsaved draft — it is never run by itself.
  If a needed tool does not exist, the assistant names it and offers to create it.
- **Create a tool (plugin)** from a description. The code is checked statically before you see it: only
  an allow-list of offline libraries (no networking, no launching programs, no `eval`/`exec`, no dynamic
  imports), a valid tool definition, no replacing built-in tools. You read the code, tick “I have read this
  code”, and only then is it installed into the plugin folder and loaded. Plugins can be viewed and removed in
  Settings → Plugins.

**What stays on your computer:** your files and their contents, file names and folder paths, results,
history and logs. **What is sent:** your request text — shown to you exactly before you click *Send*, with
file paths and e-mail addresses replaced by placeholders (on by default) — and OfficeFlow's tool list
(names, settings, file formats). Every request is recorded locally in the assistant's *Activity* list
(`ai_activity.jsonl` in the data folder). The API key is stored in the data folder, encrypted with Windows
DPAPI on Windows, and is never sent back to the interface. Requests are billed to your API key. With
Claude, the server-side refusal fallback is enabled for Opus 5.5 / Sonnet 5.5 so a declined request is
retried on a fallback model automatically. Whatever the provider, its own data-retention policy applies
to the request text it receives.

The static plugin check is a review aid, not a sandbox: a plugin runs with your user's permissions, so
install only code you have read.

## Tools

### Excel toolbox
Merge files (smart column matching: case/spaces/accents/Arabic letter variants, plus fuzzy spelling —
columns that differ only by a number such as `Prix 2023`/`Prix 2024` are never merged) · Merge worksheets ·
Remove duplicates (optionally ignoring case, spaces, Arabic vs Western digits; removed rows kept in a sheet) ·
Clean and normalise · Split by column value (files or sheets) · Compare two files (by key columns or row
order) · Search and replace (keeps formatting, never touches formulas) · Extract matching rows ·
Formatted report (styled header, filters, totals, group summary) · CSV ↔ Excel (detects UTF-8/UTF-16/
Windows-1256/1252 and the delimiter; keeps leading zeros).

### PDF toolbox
**Smart Organizer** — several source folders, several regex patterns (capture group or `(?P<value>…)`
selects the value), one output folder per value regardless of the source folder, optional renaming
template (`{value}`, `{name}`, `{n}`, `{folder}`), duplicate detection by content hash, policies for
files with several values / no match / unreadable / password-protected files, a full preview before
anything is copied, and an Excel report. Plus: batch rename, extract text, tables → Excel, merge (with
bookmarks), split, extract pages (`1-3, 5, 10-`), search across PDFs → Excel, compare two PDFs → HTML diff.

### Word toolbox
- **Generate documents from Excel** — one `.docx` per row from a template with `{{Column}}` placeholders
  (body, tables, headers, footers; `{{n}}` = row number). Placeholders split by Word over several
  formatting runs still work and keep their formatting. File names can use placeholders too.
- **Replace text** across many documents (plain or regex), keeping formatting.
- **Merge documents** in order, keeping text, tables and pictures. Charts and embedded objects cannot be
  moved between files safely; they are left out and reported.
- **Format documents** — font (separate font for Arabic), size, line spacing, margins, justify, remove
  empty paragraphs, right-to-left on Arabic paragraphs.
- **Extract tables to Excel**, **Extract text**.
- **Convert Word to PDF** through LibreOffice (free) or, on Windows, Microsoft Word.

Old `.doc` files are not supported (save them as `.docx`).

### Arabic support
Text is NFKC-normalised (PDF presentation forms → normal letters), bidi marks removed, Arabic-Indic digit
runs that PDF extractors return reversed are restored, and `٢٠٢٤/٠١/٠٠٥` is matched/grouped with
`2024/01/005` when "Treat Arabic digits as 0-9" is on. File names keep Arabic characters; only characters
illegal on Windows are replaced (`2024/01/005` → folder `2024-01-005`). Excel sheets with Arabic headers
are written right-to-left; Word formatting marks Arabic paragraphs right-to-left.
Known limit: in some PDFs (it depends on the producing software) Arabic text next to Arabic-Indic digits
is extracted in visual order, so a pattern such as `رقم\s*(\d+)` may not match there; patterns on the
reference itself (`\d{4}/\d{2}/\d{3}`) work in both cases.

## Architecture

```
Next.js interface (frontend/)  ──HTTP + event stream──▶  FastAPI server (officeflow/server)
      shown in a frameless pywebview window                     │
      (officeflow/desktop.py)                                    ▼
                                        core.runner / core.workflow ──▶ Operation.run() ──▶ engines/*
                                                    │                              (pure processing)
                                                    └── services: SQLite history, settings, logging, files
```

The interface never contains processing logic: every tool is an `Operation` that runs identically from
the interface, a workflow, or a test. The server only listens on `127.0.0.1`, and every API call must
carry the per-launch token, so other web pages open on the computer cannot use it.

```
officeflow/
├── __main__.py            entry point (python -m officeflow)
├── desktop.py             starts the server, opens the frameless window, window/dialog/drop bridge
├── ai/                    assistant.py (Claude and OpenAI providers, answer checks) · privacy.py (redaction, tool
│                          catalog) · plugin_check.py (static safety check for AI-written plugins)
├── server/
│   ├── app.py             FastAPI routes: tools, jobs, workflows, history, logs, settings, files
│   └── jobs.py            background jobs with progress, cancellation and event streams
├── core/
│   ├── operation.py       Operation contract, Param, Preview, OperationResult, OperationContext
│   ├── registry.py        @register decorator, built-in discovery, plugin folder loading
│   ├── runner.py          validate → expand folders → run → catch errors → record history
│   └── workflow.py        Workflow/Step model, validation of step compatibility, chained execution
├── engines/               document processing, independent of any interface
│   ├── excel/  io.py · transform.py · replace.py
│   ├── pdf/    reader.py · organizer.py · pages.py · content.py
│   └── word/   document.py (walk + run-aware replace) · generate.py · merge.py · content.py · convert.py
├── operations/            the tools users see: excel.py · pdf.py · word.py
├── services/              files.py · textnorm.py (Arabic) · database.py · settings.py · logsetup.py · paths.py
└── web/                   built interface (generated by `npm run build`, not committed)
frontend/
├── app/                   pages: dashboard, toolbox, tool, workflow, history, logs, settings
├── components/            Shell (title bar, rail, window controls), FolderFan, Deck, FlowCanvas,
│                          AddStepMenu, InputList, FileBrowser, ParamForm, RunPanel, ToolCard, Icon
├── lib/                   api.ts (client + event streams), desktop.ts (window bridge), formats.ts
│                          (which tool can follow which), app-context.tsx, useJob.ts, pick.ts
└── e2e/smoke.mjs          browser test against the real server
tests/                     engines, tools, workflows, API
```

### Key interfaces

```python
class Operation(ABC):
    id: str; name: str; category: str            # "excel" | "pdf" | "word" | "cross"
    input_extensions: tuple[str, ...]            # which files the runner collects from folders
    output_extensions: tuple[str, ...]           # what the next workflow step receives
    params: tuple[Param, ...]                    # rendered automatically as a settings form
    def preview(self, inputs, params, ctx) -> Preview          # must not write files
    def run(self, inputs, params, ctx) -> OperationResult      # outputs feed the next workflow step
```

`OperationContext` gives an operation its output folder, `ctx.out_path(name)` (never overwrites:
`report.xlsx` → `report (2).xlsx`), `ctx.progress(done, total, message)` and cancellation.
User-facing problems are raised as `OperationError`; anything else is caught by the runner, logged,
and shown as a readable error.

Main API routes (all under `/api`, token required): `GET meta` (tools and their parameters),
`POST jobs` (`preview` / `run` / `workflow`), `GET jobs/{id}/events` (progress stream),
`POST jobs/{id}/cancel`, `GET|PUT|DELETE workflows`, `GET history`, `POST history/export`, `GET logs`,
`GET|PUT settings`, `GET fs/list` (in-app file browser), `POST fs/scan`, `POST open`.

### Adding a tool (plugin)
Drop a `.py` file in the plugin folder (Settings → Plugins → Open plugin folder); it loads at start-up
and appears in its toolbox, the dashboard and the workflow builder, with its settings form generated
from its parameters:

```python
from officeflow.core.operation import Operation, OperationResult
from officeflow.core.registry import register

@register
class CountPages(Operation):
    id, name, category = "pdf.count", "Count pages", "pdf"
    description = "List the number of pages of each PDF."
    input_extensions = output_extensions = (".pdf",)

    def run(self, inputs, params, ctx):
        from officeflow.engines.pdf.reader import page_count
        rows = [[p.name, str(page_count(p))] for p in inputs]
        return OperationResult(f"{len(rows)} PDF(s) counted.", headers=["File", "Pages"], rows=rows)
```

### Data locations
Settings, the SQLite database (history + saved workflows), logs and plugins live in
`%APPDATA%\OfficeFlow` on Windows (`~/.local/share/officeflow` on Linux). `OFFICEFLOW_HOME` overrides it.

## Dependencies
Python: `pandas`, `openpyxl`, `PyMuPDF` (PDF text, tables, pages), `python-docx`, `fastapi` + `uvicorn`
(local API), `pywebview` (native window on Windows/macOS), `anthropic` / `openai` (optional AI assistant). Interface: Next.js, React, Framer Motion; the
Urbanist font (SIL OFL) is bundled, so nothing is loaded from the internet. Word → PDF uses LibreOffice
or Microsoft Word if installed. Camelot/OpenCV were not needed: PyMuPDF's table finder covers ruled
tables in text PDFs.
