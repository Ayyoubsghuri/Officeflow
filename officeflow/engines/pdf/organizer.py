"""PDF Smart Organizer: group, rename and de-duplicate PDFs by content.

The work is split in two so the GUI can show a safe preview:

* ``build_plan`` reads the PDFs and decides where each one goes — it never
  writes anything;
* ``apply_plan`` copies (or moves) the files according to the plan.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from officeflow.core.operation import OperationError
from officeflow.engines.pdf.reader import PdfError, iter_page_texts
from officeflow.services.files import file_hash, safe_filename, unique_path
from officeflow.services.textnorm import normalize_text, to_western_digits

NO_MATCH_FOLDER = "_No match"
MULTIPLE_FOLDER = "_Multiple matches"
DUPLICATES_FOLDER = "_Duplicates"
UNREADABLE_FOLDER = "_Unreadable"
_TOKENS = {"value", "name", "n", "folder"}

Progress = Callable[[int, int, str], None]


@dataclass
class OrganizerOptions:
    patterns: Sequence[str]
    ignore_case: bool = True
    western_digits: bool = True
    max_pages: int = 0                 # 0 = whole document
    group_into_folders: bool = True
    multi_match: str = "all"           # all | first | separate
    unmatched: str = "folder"          # folder | skip
    duplicates: str = "skip"           # skip | folder | keep
    rename_template: str = ""          # "" keeps the original name
    move: bool = False


@dataclass
class PlanItem:
    source: Path
    status: str                        # matched | multiple | unmatched | duplicate | error
    values: list[str] = field(default_factory=list)
    destinations: list[Path] = field(default_factory=list)  # relative to the output folder
    note: str = ""


def compile_patterns(options: OrganizerOptions) -> list[re.Pattern[str]]:
    if not options.patterns:
        raise OperationError("Add at least one extraction pattern.")
    flags = re.MULTILINE | (re.IGNORECASE if options.ignore_case else 0)
    compiled = []
    for text in options.patterns:
        try:
            compiled.append(re.compile(to_western_digits(text) if options.western_digits else text, flags))
        except re.error as exc:
            raise OperationError(f"Invalid pattern “{text}”: {exc}") from None
    return compiled


def check_template(template: str) -> None:
    unknown = set(re.findall(r"\{(\w*)[^}]*\}", template)) - _TOKENS
    if unknown or template.count("{") != template.count("}"):
        raise OperationError(
            "Invalid file name template. Use {value}, {name}, {n} and {folder}, "
            "for example: {value} - {name}"
        )


def find_values(text: str, patterns: Sequence[re.Pattern[str]], western_digits: bool = True) -> list[str]:
    """Distinct values found in ``text``, in order of appearance. A pattern
    with a group named ``value`` (or a first group) yields that group,
    otherwise the whole match."""
    text = normalize_text(text, western_digits)
    found: dict[str, None] = {}
    for pattern in patterns:
        for match in pattern.finditer(text):
            if "value" in pattern.groupindex:
                value = match.group("value")
            elif pattern.groups:
                value = match.group(1)
            else:
                value = match.group(0)
            value = re.sub(r"\s+", " ", value or "").strip()
            if value:
                found.setdefault(value)
    return list(found)


def extract_values(path: Path, patterns: Sequence[re.Pattern[str]], options: OrganizerOptions) -> list[str]:
    found: dict[str, None] = {}
    for text in iter_page_texts(path, options.max_pages):
        for value in find_values(text, patterns, options.western_digits):
            found.setdefault(value)
    return list(found)


def _file_name(template: str, source: Path, value: str, counter: int) -> str:
    if not template:
        return source.name
    name = template.format_map({"value": value, "name": source.stem, "n": f"{counter:03d}",
                                "folder": source.parent.name})
    return safe_filename(name) + source.suffix.lower()


def build_plan(
    files: Sequence[Path], options: OrganizerOptions, progress: Progress | None = None
) -> list[PlanItem]:
    patterns = compile_patterns(options)
    check_template(options.rename_template)
    plan: list[PlanItem] = []
    hashes: dict[str, Path] = {}
    spellings: dict[str, str] = {}  # with ignore_case, "ab12" joins the folder of "AB12"
    taken: set[Path] = set()

    def place(folder: str, name: str) -> Path:
        # Reserve a unique relative destination so two "invoice.pdf" from
        # different folders never collide.
        return unique_path(Path(folder) / name if folder else Path(name), taken)

    for index, source in enumerate(files):
        if progress:
            progress(index, len(files), source.name)
        item = PlanItem(source, "matched")
        plan.append(item)
        try:
            digest = file_hash(source)
            original = hashes.setdefault(digest, source)
            if original is not source:
                item.note = f"Identical to {original.name} ({original.parent})"
                if options.duplicates != "keep":
                    item.status = "duplicate"
                    if options.duplicates == "folder":
                        item.destinations = [place(DUPLICATES_FOLDER, source.name)]
                    continue
            item.values = extract_values(source, patterns, options)
            if options.ignore_case:
                item.values = list(dict.fromkeys(
                    spellings.setdefault(v.casefold(), v) for v in item.values))
        except (PdfError, OSError) as exc:
            item.status, item.note = "error", str(exc)
            if options.unmatched == "folder":
                item.destinations = [place(UNREADABLE_FOLDER, source.name)]
            continue
        counter = index + 1
        if not item.values:
            item.status = "unmatched"
            item.note = item.note or "No pattern matched (scanned PDFs contain no text)"
            if options.unmatched == "folder":
                item.destinations = [place(NO_MATCH_FOLDER, source.name)]
            continue
        chosen = item.values
        if len(item.values) > 1:
            item.status = "multiple"
            if options.multi_match == "first" or not options.group_into_folders:
                chosen = item.values[:1]
            elif options.multi_match == "separate":
                item.destinations = [place(MULTIPLE_FOLDER, source.name)]
                continue
        for value in chosen:
            folder = safe_filename(value) if options.group_into_folders else ""
            item.destinations.append(place(folder, _file_name(options.rename_template, source, value, counter)))
    if progress:
        progress(len(files), len(files), "Plan ready")
    return plan


def apply_plan(
    plan: Sequence[PlanItem], output_dir: Path, move: bool = False, progress: Progress | None = None
) -> tuple[list[Path], list[str]]:
    """Copy every planned file. Returns (created files, errors). Existing
    files in the output folder are never overwritten. With ``move`` the
    source is deleted only after all of its copies were written."""
    created: list[Path] = []
    errors: list[str] = []
    taken: set[Path] = set()
    for index, item in enumerate(plan):
        if progress:
            progress(index, len(plan), item.source.name)
        try:
            for relative in item.destinations:
                target = unique_path(output_dir / relative, taken)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.source, target)
                created.append(target)
            if move and item.destinations:
                item.source.unlink()
        except OSError as exc:
            errors.append(f"{item.source.name}: {exc.strerror or exc}")
    if progress:
        progress(len(plan), len(plan), "Done")
    return created, errors


STATUS_LABELS = {
    "matched": "Matched", "multiple": "Several values", "unmatched": "No match",
    "duplicate": "Duplicate", "error": "Unreadable",
}


def plan_rows(plan: Sequence[PlanItem]) -> list[list[str]]:
    return [
        [item.source.name, item.source.parent.name, STATUS_LABELS[item.status], ", ".join(item.values),
         " ; ".join(str(d) for d in item.destinations) or "(skipped)", item.note]
        for item in plan
    ]


PLAN_HEADERS = ["File", "Source folder", "Status", "Extracted value(s)", "Destination", "Note"]


def plan_summary(plan: Sequence[PlanItem]) -> str:
    count = {s: sum(i.status == s for i in plan) for s in STATUS_LABELS}
    folders = {d.parts[0] for i in plan for d in i.destinations if len(d.parts) > 1 and not d.parts[0].startswith("_")}
    parts = [f"{len(plan)} PDF(s)", f"{len(folders)} folder(s)" if folders else "",
             f"{count['matched'] + count['multiple']} matched",
             f"{count['multiple']} with several values" if count["multiple"] else "",
             f"{count['unmatched']} without match" if count["unmatched"] else "",
             f"{count['duplicate']} duplicate(s)" if count["duplicate"] else "",
             f"{count['error']} unreadable" if count["error"] else ""]
    return " · ".join(p for p in parts if p)
