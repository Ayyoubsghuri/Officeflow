# OfficeFlow

Offline-first desktop automation for Excel, PDF and (later) Word documents.
Select files or folders, configure a tool, preview what will happen, run it in the background,
and chain tools into reusable workflows. Original files are never modified unless you explicitly
choose "move".

## Quick start

```bash
pip install -r requirements.txt
python -m officeflow
```

Run the tests (the GUI tests run headless):

```bash
python -m pytest
```

On a Linux server without a display, Qt needs `libegl1 libgl1 libxkbcommon0 libfontconfig1`.

## Status by phase

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, GUI foundation, history, logs, settings, themes | **Done** |
| 2 | Excel automation (10 tools) | **Done** |
| 3 | PDF automation incl. Smart Organizer (9 tools) | **Done**, except OCR (see below) |
| 4 | Word automation | Not started — toolbox shows "Not available yet" |
| 5 | Cross-document automation | Not started |
| 6 | Workflow Builder | **Done** (chains any registered tools; Word/cross tools will plug in) |
| 7 | Installer (PyInstaller), optimisation | Not started |

Not implemented yet, by design of the phased plan: OCR for scanned PDFs (PaddleOCR/Tesseract),
"make PDF searchable", Word tools, Excel↔Word/PDF cross tools, optional local AI (Ollama), the Windows installer.
Scanned PDFs are currently detected and reported ("no text found") rather than processed.

### Excel toolbox
Merge files (smart column matching: case/spaces/accents/Arabic letter variants, plus fuzzy spelling —
columns that differ only by a number such as `Prix 2023`/`Prix 2024` are never merged) · Merge worksheets ·
Remove duplicates (optionally ignoring case, spaces, Arabic vs Western digits; removed rows kept in a sheet) ·
Clean and normalise · Split by column value (files or sheets) · Compare two files (by key columns or row
order) · Search and replace (keeps formatting, never touches formulas) · Extract matching rows ·
Formatted report (styled header, filters, totals, group summary) · CSV ↔ Excel (detects UTF-8/UTF-16/
Windows-1256/1252 and the delimiter; keeps leading zeros).

### Workflow Builder
A node canvas: a **Files & folders** start node feeds the first step, and each step node passes its output
files to the next. Add steps from the floating **Add step** bar or the dashed node at the end of the chain;
drag nodes, pan by dragging the background, zoom with the wheel or the left tool bar, and undo/redo every
change (Ctrl+Z / Ctrl+Shift+Z). Selecting a node opens its settings in the panel on the right. A step that
cannot use the previous step's files (for example "Merge PDFs" after "Extract PDF text") is marked in red
before anything runs. After a run each node shows Done / Failed / Not run and the number of files it made.
Workflows are saved by name; the badge next to the name shows **Draft** until the current version is saved.

### PDF toolbox
**Smart Organizer** — several source folders, several regex patterns (capture group or `(?P<value>…)`
selects the value), one output folder per value regardless of the source folder, optional renaming
template (`{value}`, `{name}`, `{n}`, `{folder}`), duplicate detection by content hash, policies for
files with several values / no match / unreadable / password-protected files, a full preview before
anything is copied, and an Excel report. Plus: batch rename, extract text, tables → Excel, merge (with
bookmarks), split, extract pages (`1-3, 5, 10-`), search across PDFs → Excel, compare two PDFs → HTML diff.

### Arabic support
Text is NFKC-normalised (PDF presentation forms → normal letters), bidi marks removed, Arabic-Indic digit
runs that PDF extractors return reversed are restored, and `٢٠٢٤/٠١/٠٠٥` is matched/grouped with
`2024/01/005` when "Treat Arabic digits as 0-9" is on. File names keep Arabic characters; only characters
illegal on Windows are replaced (`2024/01/005` → folder `2024-01-005`). Excel sheets with Arabic headers
are written right-to-left.
Known limit: in some PDFs (it depends on the producing software) Arabic text next to Arabic-Indic digits
is extracted in visual order, so a pattern such as `رقم\s*(\d+)` may not match there; patterns on the
reference itself (`\d{4}/\d{2}/\d{3}`) work in both cases.

## Architecture

```
GUI (PySide6)  ──calls──▶  core.runner / core.workflow  ──▶  Operation.run()  ──▶  engines/*
     │                              │                               (pure processing, no Qt)
     └── QThread worker             └── services: database (SQLite), settings, logging, files
```

The GUI never contains processing logic: every tool is an `Operation` that can be run from the GUI,
a workflow, or a test with the same code path.

```
officeflow/
├── __main__.py            entry point (python -m officeflow)
├── app.py                 bootstrap: logging, registry, plugins, theme, main window
├── core/
│   ├── operation.py       Operation contract, Param, Preview, OperationResult, OperationContext
│   ├── registry.py        @register decorator, built-in discovery, plugin folder loading
│   ├── runner.py          validate → expand folders → run → catch errors → record history
│   └── workflow.py        Workflow/Step model, validation of step compatibility, chained execution
├── engines/               document processing, independent of the GUI
│   ├── excel/  io.py (read/write/format, CSV detection) · transform.py (merge, dedupe, clean,
│   │           split, filter, compare) · replace.py (in-place cell replace keeping formatting)
│   └── pdf/    reader.py (safe open, text) · organizer.py (plan/apply) · pages.py · content.py
├── operations/            the tools users see: thin wrappers declaring params over the engines
│   ├── excel.py
│   └── pdf.py
├── services/              files.py (unicode-safe names, no-overwrite paths) · textnorm.py (Arabic)
│                          database.py · settings.py · logsetup.py · paths.py
├── gui/                   theme.py · icons.py · worker.py · main_window.py · pages/ · widgets/
└── assets/fonts/          Urbanist (SIL OFL)
tests/                     engine, core and headless GUI tests
```

### Key interfaces

```python
class Operation(ABC):
    id: str; name: str; category: str            # "excel" | "pdf" | "word" | "cross"
    input_extensions: tuple[str, ...]            # which files the runner collects from folders
    output_extensions: tuple[str, ...]           # used to check workflow steps fit together
    params: tuple[Param, ...]                    # rendered automatically as a settings form
    def preview(self, inputs, params, ctx) -> Preview          # must not write files
    def run(self, inputs, params, ctx) -> OperationResult      # outputs feed the next workflow step
```

`OperationContext` gives an operation its output folder, `ctx.out_path(name)` (never overwrites:
`report.xlsx` → `report (2).xlsx`), `ctx.progress(done, total, message)` and cancellation.
User-facing problems are raised as `OperationError`; anything else is caught by the runner, logged,
and shown as a readable error.

### Adding a tool (plugin)
Drop a `.py` file in the plugin folder (Settings → Plugins → Open plugin folder); it loads at start-up
and appears in its toolbox, the dashboard and the workflow builder:

```python
from officeflow.core.operation import Operation, OperationResult, Param
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
`pandas`, `openpyxl`, `PyMuPDF` (PDF text, tables, pages), `PySide6-Essentials` (GUI). No network access is
used. Camelot/OpenCV were not needed: PyMuPDF's table finder covers ruled tables in text PDFs.
