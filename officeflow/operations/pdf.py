"""PDF toolbox: thin operation wrappers around ``officeflow.engines.pdf``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from officeflow.core.operation import (
    Operation, OperationContext, OperationError, OperationResult, Param, ParamType, Preview,
)
from officeflow.core.registry import register
from officeflow.engines.excel import io as excel_io
from officeflow.engines.excel.transform import build_pattern
from officeflow.engines.pdf import content, organizer, pages
from officeflow.engines.pdf.reader import PDF_EXTENSIONS
from officeflow.services.files import safe_filename
from officeflow.services.textnorm import split_lines, to_western_digits

PATTERNS = Param(
    "patterns", "Extraction patterns (one regular expression per line)", ParamType.MULTILINE,
    r"\b\d{4}/\d{2}/\d{3}\b", required=True,
    help="Each line is a regular expression searched in the PDF text. If a pattern contains "
         "parentheses, only the part inside the first pair is used as the value.",
)
IGNORE_CASE = Param("ignore_case", "Ignore upper/lower case", ParamType.BOOL, True)
WESTERN = Param("western_digits", "Treat Arabic digits (٠-٩) as 0-9", ParamType.BOOL, True,
                help="A reference written ٢٠٢٤/٠١/٠٠٥ is grouped with 2024/01/005.")
MAX_PAGES = Param("max_pages", "Pages to read per PDF (0 = all pages)", ParamType.INT, 0,
                  help="Reading only the first pages is much faster on large collections.", maximum=10_000)
MOVE = Param("move", "Move files instead of copying (originals are removed)", ParamType.BOOL, False)


class _Planned(Operation):
    """Shared preview/run for the tools built on the organizer engine."""

    category = "pdf"
    input_extensions = PDF_EXTENSIONS
    output_extensions = PDF_EXTENSIONS
    report_name = "Report.xlsx"

    def options(self, params) -> organizer.OrganizerOptions:
        raise NotImplementedError

    def preview(self, inputs, params, ctx):
        plan = organizer.build_plan(inputs, self.options(params), ctx.progress)
        return Preview("Nothing has been changed yet. " + organizer.plan_summary(plan),
                       organizer.PLAN_HEADERS, organizer.plan_rows(plan))

    def run(self, inputs, params, ctx):
        options = self.options(params)
        plan = organizer.build_plan(
            inputs, options, lambda d, t, m: ctx.progress(d, t * 2, f"Reading {m}"))
        created, errors = organizer.apply_plan(
            plan, ctx.output_dir, options.move,
            lambda d, t, m: ctx.progress(t + d, t * 2, f"Copying {m}"))
        rows = organizer.plan_rows(plan)
        report = ctx.out_path(self.report_name)
        excel_io.write_table(pd.DataFrame(rows, columns=organizer.PLAN_HEADERS), report, "Report")
        warnings = [f"{i.source.name}: {i.note}" for i in plan if i.status in ("unmatched", "duplicate")]
        errors += [i.note for i in plan if i.status == "error"]
        return OperationResult(
            f"{organizer.plan_summary(plan)} · {len(created)} file(s) written.",
            created, [report], organizer.PLAN_HEADERS, rows, warnings, errors)


@register
class SmartOrganizer(_Planned):
    id = "pdf.organize"
    name = "PDF Smart Organizer"
    description = ("Read PDFs from several folders, extract a reference with regular expressions and "
                   "sort the files into one folder per reference. Detects duplicates and unmatched files.")
    input_label = "PDF files or source folders (add as many folders as you need)"
    report_name = "Organizer report.xlsx"
    params = (
        PATTERNS, IGNORE_CASE, WESTERN, MAX_PAGES,
        Param("multi_match", "When a PDF contains several different values", ParamType.CHOICE, "all",
              choices=(("all", "Copy it into every matching folder"),
                       ("first", "Use the first value only"),
                       ("separate", f"Put it in “{organizer.MULTIPLE_FOLDER}” for manual review"))),
        Param("unmatched", "When no pattern matches or the PDF is unreadable", ParamType.CHOICE, "folder",
              choices=(("folder", f"Put it in “{organizer.NO_MATCH_FOLDER}” / “{organizer.UNREADABLE_FOLDER}”"),
                       ("skip", "Leave it out"))),
        Param("duplicates", "Identical files", ParamType.CHOICE, "skip",
              choices=(("skip", "Keep one copy, skip the others"),
                       ("folder", f"Keep one copy, put the others in “{organizer.DUPLICATES_FOLDER}”"),
                       ("keep", "Keep all copies"))),
        Param("rename_template", "Rename files (optional)", placeholder="{value} - {name}",
              help="Leave empty to keep the original names. Tokens: {value} extracted value, "
                   "{name} original name, {n} counter, {folder} source folder."),
        MOVE,
    )

    def options(self, params):
        return organizer.OrganizerOptions(
            patterns=split_lines(params["patterns"]),
            **{k: v for k, v in params.items() if k != "patterns"})


@register
class BatchRename(_Planned):
    id = "pdf.rename"
    name = "Batch rename PDFs"
    description = "Rename PDFs using information found inside them (reference, invoice number, name…)."
    report_name = "Rename report.xlsx"
    params = (
        PATTERNS, IGNORE_CASE, WESTERN, MAX_PAGES,
        Param("rename_template", "New file name", default="{value}", required=True,
              help="Tokens: {value} extracted value, {name} original name, {n} counter, {folder} source folder."),
        Param("unmatched", "When no pattern matches", ParamType.CHOICE, "folder",
              choices=(("folder", f"Copy unchanged into “{organizer.NO_MATCH_FOLDER}”"), ("skip", "Leave it out"))),
        MOVE,
    )

    def options(self, params):
        return organizer.OrganizerOptions(
            patterns=split_lines(params["patterns"]), group_into_folders=False, duplicates="keep",
            **{k: v for k, v in params.items() if k != "patterns"})


@register
class ExtractText(Operation):
    id = "pdf.text"
    name = "Extract PDF text"
    category = "pdf"
    description = "Save the text of each PDF as a UTF-8 text file (Arabic and French supported)."
    input_extensions = PDF_EXTENSIONS
    output_extensions = (".txt",)
    params = (Param("page_markers", "Insert a “Page N” line before each page", ParamType.BOOL, True),)

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Pages", "Characters"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                out = ctx.out_path(path.stem + ".txt")
                count, characters = content.export_text(path, out, params["page_markers"])
                result.outputs.append(out)
                result.rows.append([path.name, str(count), str(characters)])
                if not characters:
                    result.warnings.append(f"{path.name}: no text found (probably a scanned document).")
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, "Error", str(exc)])
        result.summary = f"Text extracted from {len(result.outputs)} of {len(inputs)} PDF(s)."
        return result


@register
class TablesToExcel(Operation):
    id = "pdf.tables"
    name = "Extract tables to Excel"
    category = "pdf"
    description = "Detect tables in text-based PDFs and save them as Excel sheets (one workbook per PDF)."
    input_extensions = PDF_EXTENSIONS
    output_extensions = (".xlsx",)

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Tables"])
        total = 0
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                tables = content.extract_tables(path)
                if not tables:
                    result.warnings.append(f"{path.name}: no table detected.")
                    result.rows.append([path.name, "0"])
                    continue
                out = ctx.out_path(path.stem + " - tables.xlsx")
                excel_io.write_workbook(
                    out, {f"Page {page} - T{n}": frame for n, (page, frame) in enumerate(tables, 1)})
                result.outputs.append(out)
                result.rows.append([path.name, str(len(tables))])
                total += len(tables)
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        result.summary = f"{total} table(s) extracted from {len(result.outputs)} PDF(s)."
        return result


@register
class MergePdfs(Operation):
    id = "pdf.merge"
    name = "Merge PDFs"
    category = "pdf"
    description = "Join several PDFs into one, in the order listed, with a bookmark for each file."
    input_extensions = PDF_EXTENSIONS
    output_extensions = PDF_EXTENSIONS
    min_inputs = 2
    params = (Param("output_name", "Output file name", default="Merged", required=True),)

    def run(self, inputs, params, ctx):
        out = ctx.out_path(safe_filename(params["output_name"]) + ".pdf")
        count, errors = pages.merge_pdfs(inputs, out, ctx.progress)
        return OperationResult(
            f"{len(inputs) - len(errors)} PDF(s) merged into {out.name} ({count} pages).", [out], errors=errors)


@register
class SplitPdf(Operation):
    id = "pdf.split"
    name = "Split PDFs"
    category = "pdf"
    description = "Cut each PDF into smaller files of a fixed number of pages."
    input_extensions = PDF_EXTENSIONS
    output_extensions = PDF_EXTENSIONS
    params = (Param("pages_per_file", "Pages per file", ParamType.INT, 1, minimum=1, maximum=10_000),)

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Parts"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                folder = Path(safe_filename(path.stem))
                parts = pages.split_pdf(path, params["pages_per_file"], lambda n: ctx.out_path(folder / n))
                result.outputs += parts
                result.rows.append([path.name, str(len(parts))])
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        result.summary = f"{len(result.outputs)} file(s) created from {len(inputs)} PDF(s)."
        return result


@register
class ExtractPages(Operation):
    id = "pdf.pages"
    name = "Extract specific pages"
    category = "pdf"
    description = "Keep only the pages you choose from each PDF."
    input_extensions = PDF_EXTENSIONS
    output_extensions = PDF_EXTENSIONS
    params = (Param("pages", "Pages", required=True, placeholder="1-3, 5, 10-",
                    help="Page numbers and ranges. “10-” means from page 10 to the end."),)

    def run(self, inputs, params, ctx):
        pages.parse_page_ranges(params["pages"], 1)  # reject a bad specification before starting
        result = OperationResult("", headers=["File", "Pages kept"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            out = ctx.out_path(f"{path.stem} - pages.pdf")
            try:
                kept = pages.extract_pages(path, params["pages"], out)
                result.outputs.append(out)
                result.rows.append([path.name, str(kept)])
            except OperationError as exc:
                ctx.release(out)
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        result.summary = f"Pages extracted from {len(result.outputs)} of {len(inputs)} PDF(s)."
        return result


@register
class SearchPdfs(Operation):
    id = "pdf.search"
    name = "Search text in PDFs"
    category = "pdf"
    description = "Find a word, phrase or pattern across many PDFs and list every occurrence in Excel."
    input_extensions = PDF_EXTENSIONS
    output_extensions = (".xlsx",)
    params = (
        Param("find", "Search for", required=True),
        Param("regex", "Use a regular expression", ParamType.BOOL, False),
        Param("case_sensitive", "Match case", ParamType.BOOL, False),
        WESTERN,
    )

    def run(self, inputs, params, ctx):
        find = to_western_digits(params["find"]) if params["western_digits"] else params["find"]
        pattern = build_pattern(find, params["regex"], params["case_sensitive"])
        result = OperationResult("", headers=["File", "Page", "Match", "Context"])
        files_with_hits = 0
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                hits = content.search_pdf(path, pattern, params["western_digits"])
                files_with_hits += bool(hits)
                result.rows += [[path.name, str(h.page), h.match, h.context] for h in hits]
            except OperationError as exc:
                result.errors.append(str(exc))
        report = ctx.out_path("Search results.xlsx")
        excel_io.write_table(pd.DataFrame(result.rows, columns=result.headers), report, "Results")
        result.outputs, result.reports = [report], [report]
        result.summary = (f"{len(result.rows)} occurrence(s) in {files_with_hits} of "
                          f"{len(inputs)} PDF(s). Saved to {report.name}.")
        return result


@register
class ComparePdfs(Operation):
    id = "pdf.compare"
    name = "Compare two PDFs"
    category = "pdf"
    description = "Compare the text of two PDFs and produce a side-by-side report of the differences."
    input_extensions = PDF_EXTENSIONS
    output_extensions = (".html",)
    input_label = "Exactly two PDFs (first = reference)"
    min_inputs = max_inputs = 2

    def run(self, inputs, params, ctx):
        ctx.progress(0, 1, "Comparing")
        out = ctx.out_path(f"Comparison - {safe_filename(inputs[0].stem)} vs {safe_filename(inputs[1].stem)}.html")
        stats = content.compare_pdfs(inputs[0], inputs[1], out)
        if stats["changed_lines"]:
            summary = (f"{stats['changed_lines']} differing line(s), similarity "
                       f"{stats['similarity']}%. Open {out.name} to see them.")
        else:
            summary = "The text of the two PDFs is identical."
        return OperationResult(summary, [out], [out])
