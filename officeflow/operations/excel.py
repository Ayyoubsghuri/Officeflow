"""Excel toolbox: thin operation wrappers around ``officeflow.engines.excel``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from officeflow.core.operation import (
    Operation, OperationContext, OperationError, OperationResult, Param, ParamType, Preview,
)
from officeflow.core.registry import register
from officeflow.engines.excel import io, replace, transform
from officeflow.services.files import safe_filename
from officeflow.services.textnorm import split_list

SHEET = Param("sheet", "Sheet", help="Sheet name or number. Leave empty for the first sheet.",
              placeholder="First sheet")
MATCHING = Param(
    "matching", "Column matching", ParamType.CHOICE, "fuzzy",
    help="How columns from different files are recognised as the same column.",
    choices=(("fuzzy", "Smart — also accept small spelling differences"),
             ("similar", "Ignore case, spaces, accents and punctuation"),
             ("exact", "Names must be identical")),
)


def _match_rows(matches: Sequence[transform.ColumnMatch]) -> list[list[str]]:
    labels = {"exact": "Same name", "similar": "Similar name", "fuzzy": "Close spelling",
              "new": "New column"}
    return [[m.source, m.original, m.canonical, labels[m.kind]] for m in matches]


class _PerFile(Operation):
    """Helper base: apply ``transform_one`` to each file independently; a file
    that fails is reported and the batch continues."""

    category = "excel"
    input_extensions = io.TABLE_EXTENSIONS
    suffix = ""

    def process(self, frame: pd.DataFrame, params: dict[str, Any], path: Path,
                ctx: OperationContext) -> tuple[list[Path], str]:
        raise NotImplementedError

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Result"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                frame = io.read_table(path, params.get("sheet", ""))
                outputs, note = self.process(frame, params, path, ctx)
                result.outputs += outputs
                result.rows.append([path.name, note])
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        ctx.progress(len(inputs), len(inputs), "Done")
        ok = len(inputs) - len(result.errors)
        result.summary = f"{ok} of {len(inputs)} file(s) processed, {len(result.outputs)} file(s) created."
        return result


@register
class MergeFiles(Operation):
    id = "excel.merge_files"
    name = "Merge Excel files"
    category = "excel"
    description = ("Combine many Excel/CSV files into one table. Columns are matched even when "
                   "their names differ slightly.")
    input_extensions = io.TABLE_EXTENSIONS
    params = (
        Param("sheets", "Sheets to read", ParamType.CHOICE, "first",
              choices=(("first", "First sheet of each file"), ("all", "All sheets of each file"))),
        MATCHING,
        Param("add_source", "Add a “Source” column with the original file name", ParamType.BOOL, True),
        Param("output_name", "Output file name", default="Merged", required=True),
    )

    def _load(self, inputs, params, ctx) -> tuple[list[tuple[str, pd.DataFrame]], list[str]]:
        frames, errors = [], []
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs) + 1, f"Reading {path.name}")
            try:
                if params["sheets"] == "all":
                    for sheet, frame in io.read_all_sheets(path).items():
                        if not frame.empty:
                            frames.append((f"{path.name} / {sheet}", frame))
                else:
                    frames.append((path.name, io.read_table(path)))
            except OperationError as exc:
                errors.append(str(exc))
        if not frames:
            raise OperationError("None of the files could be read. " + " ".join(errors))
        return frames, errors

    def preview(self, inputs, params, ctx):
        frames, errors = self._load(inputs, params, ctx)
        merged, matches = transform.merge_frames(frames, params["matching"])
        return Preview(
            f"{len(frames)} table(s) → 1 file with {len(merged)} rows and "
            f"{len(merged.columns)} columns. Check how the columns were matched:",
            ["Source", "Column", "Goes into", "Why"], _match_rows(matches), errors)

    def run(self, inputs, params, ctx):
        frames, errors = self._load(inputs, params, ctx)
        merged, matches = transform.merge_frames(
            frames, params["matching"], "Source" if params["add_source"] else "")
        ctx.progress(len(inputs), len(inputs) + 1, "Writing merged file")
        out = ctx.out_path(safe_filename(params["output_name"]) + ".xlsx")
        io.write_table(merged, out, "Merged")
        return OperationResult(
            f"Merged {len(frames)} table(s) into {out.name}: {len(merged)} rows, "
            f"{len(merged.columns)} columns.",
            [out], headers=["Source", "Column", "Goes into", "Why"],
            rows=[r for r in _match_rows(matches) if r[3] != "Same name"] or _match_rows(matches),
            errors=errors)


@register
class MergeSheets(_PerFile):
    id = "excel.merge_sheets"
    name = "Merge worksheets"
    description = "Combine all the sheets of each workbook into a single sheet."
    input_extensions = io.EXCEL_EXTENSIONS
    params = (MATCHING,
              Param("add_source", "Add a “Sheet” column with the original sheet name", ParamType.BOOL, True))

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Result"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                frames = [(n, f) for n, f in io.read_all_sheets(path).items() if not f.empty]
                if not frames:
                    raise OperationError(f"{path.name}: all sheets are empty.")
                merged, _ = transform.merge_frames(
                    frames, params["matching"], "Sheet" if params["add_source"] else "")
                out = ctx.out_path(f"{path.stem} - merged.xlsx")
                io.write_table(merged, out, "Merged")
                result.outputs.append(out)
                result.rows.append([path.name, f"{len(frames)} sheets → {len(merged)} rows"])
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        result.summary = f"{len(result.outputs)} of {len(inputs)} workbook(s) merged."
        return result


@register
class RemoveDuplicates(_PerFile):
    id = "excel.remove_duplicates"
    name = "Remove duplicates"
    description = "Delete repeated rows, comparing all columns or only the ones you choose."
    params = (
        SHEET,
        Param("columns", "Columns to compare", help="Comma-separated. Leave empty to compare whole rows.",
              placeholder="e.g. Reference, Email"),
        Param("keep", "Keep", ParamType.CHOICE, "first",
              choices=(("first", "The first occurrence"), ("last", "The last occurrence"),
                       ("none", "None — remove every repeated row"))),
        Param("loose", "Ignore case, extra spaces and Arabic/Western digit differences", ParamType.BOOL, True),
        Param("save_removed", "Save removed rows in a second sheet", ParamType.BOOL, True),
    )

    def process(self, frame, params, path, ctx):
        subset = transform.resolve_columns(frame, split_list(params["columns"]))
        kept, removed = transform.remove_duplicates(frame, subset, params["keep"], params["loose"])
        sheets = {"Data": kept}
        if params["save_removed"] and len(removed):
            sheets["Removed duplicates"] = removed
        out = ctx.out_path(f"{path.stem} - no duplicates.xlsx")
        io.write_workbook(out, sheets)
        return [out], f"{len(removed)} duplicate row(s) removed, {len(kept)} kept"


@register
class CleanData(_PerFile):
    id = "excel.clean"
    name = "Clean and normalize data"
    description = "Trim spaces, remove invisible characters and empty rows, unify digits and letter case."
    params = (
        SHEET,
        Param("trim", "Trim spaces at the start and end of cells", ParamType.BOOL, True),
        Param("collapse_spaces", "Replace repeated spaces with one", ParamType.BOOL, True),
        Param("remove_invisible", "Remove invisible characters (direction marks, non-breaking spaces)",
              ParamType.BOOL, True),
        Param("western_digits", "Convert Arabic digits (٠-٩) to 0-9", ParamType.BOOL, False),
        Param("drop_empty_rows", "Remove empty rows", ParamType.BOOL, True),
        Param("drop_empty_columns", "Remove empty columns", ParamType.BOOL, False),
        Param("text_case", "Letter case", ParamType.CHOICE, "keep",
              choices=(("keep", "Keep as is"), ("upper", "UPPERCASE"), ("lower", "lowercase"),
                       ("title", "Title Case"))),
    )

    def process(self, frame, params, path, ctx):
        options = transform.CleanOptions(**{k: v for k, v in params.items() if k != "sheet"})
        cleaned, stats = transform.clean_frame(frame, options)
        out = ctx.out_path(f"{path.stem} - clean.xlsx")
        io.write_table(cleaned, out)
        return [out], (f"{stats['cells_changed']} cell(s) cleaned, {stats['rows_removed']} empty "
                       f"row(s) and {stats['columns_removed']} empty column(s) removed")


@register
class SplitByColumn(_PerFile):
    id = "excel.split"
    name = "Split by column value"
    description = "Create one file (or one sheet) for each distinct value of a column."
    params = (
        SHEET,
        Param("column", "Column to split on", required=True, placeholder="e.g. Department"),
        Param("target", "Create", ParamType.CHOICE, "files",
              choices=(("files", "One file per value"), ("sheets", "One workbook with a sheet per value"))),
    )

    def preview(self, inputs, params, ctx):
        rows, warnings = [], []
        for path in inputs:
            try:
                frame = io.read_table(path, params["sheet"])
                column = transform.resolve_columns(frame, [params["column"]])[0]
                rows += [[path.name, value, str(len(part))]
                         for value, part in transform.split_frame(frame, column).items()]
            except OperationError as exc:
                warnings.append(str(exc))
        return Preview(f"{len(rows)} part(s) will be created.", ["File", "Value", "Rows"], rows, warnings)

    def process(self, frame, params, path, ctx):
        column = transform.resolve_columns(frame, [params["column"]])[0]
        parts = transform.split_frame(frame, column)
        if params["target"] == "sheets":
            out = ctx.out_path(f"{path.stem} - split.xlsx")
            io.write_workbook(out, parts)
            return [out], f"{len(parts)} sheet(s) in {out.name}"
        outputs = []
        for value, part in parts.items():
            ctx.check_cancelled()
            out = ctx.out_path(Path(safe_filename(path.stem)) / f"{safe_filename(value)}.xlsx")
            io.write_table(part, out)
            outputs.append(out)
        return outputs, f"{len(parts)} file(s) created"


@register
class CompareFiles(Operation):
    id = "excel.compare"
    name = "Compare two Excel files"
    category = "excel"
    description = "Find rows that exist in only one file and cells whose values changed."
    input_extensions = io.TABLE_EXTENSIONS
    input_label = "Exactly two files (first = reference)"
    min_inputs = max_inputs = 2
    params = (
        SHEET,
        Param("keys", "Key column(s)", placeholder="e.g. Reference",
              help="Columns that identify a row. Leave empty to compare row by row in order."),
    )

    def run(self, inputs, params, ctx):
        first, second = (io.read_table(p, params["sheet"]) for p in inputs)
        ctx.progress(1, 3, "Comparing")
        sheets = transform.compare_frames(first, second, split_list(params["keys"]))
        counts = {name: len(frame) for name, frame in sheets.items()}
        summary = pd.DataFrame(
            [["First file", inputs[0].name, len(first)], ["Second file", inputs[1].name, len(second)]]
            + [[name, "", count] for name, count in counts.items()],
            columns=["Item", "File", "Rows"])
        out = ctx.out_path(f"Comparison - {safe_filename(inputs[0].stem)} vs {safe_filename(inputs[1].stem)}.xlsx")
        io.write_workbook(out, {"Summary": summary, **sheets})
        identical = not any(counts.values())
        return OperationResult(
            "The two files are identical." if identical else
            f"{counts['Only in first']} row(s) only in the first file, {counts['Only in second']} only "
            f"in the second, {counts['Changed cells']} changed cell(s). Details in {out.name}.",
            reports=[out], outputs=[out], headers=["Item", "File", "Rows"],
            rows=summary.astype(str).values.tolist())


@register
class SearchReplace(Operation):
    id = "excel.replace"
    name = "Search and replace"
    category = "excel"
    description = ("Replace text in every sheet of many files at once. Formatting is preserved; "
                   "formulas and numbers are not touched.")
    input_extensions = io.TABLE_EXTENSIONS
    params = (
        Param("find", "Find", required=True),
        Param("replace", "Replace with"),
        Param("regex", "Use a regular expression", ParamType.BOOL, False),
        Param("case_sensitive", "Match case", ParamType.BOOL, False),
        Param("whole_cell", "Match the entire cell content only", ParamType.BOOL, False),
    )

    def _each(self, inputs, params, ctx, write: bool) -> OperationResult:
        pattern = transform.build_pattern(params["find"], params["regex"], params["case_sensitive"])
        result = OperationResult("", headers=["File", "Replacements"])
        total = 0
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                out = ctx.out_path(path.name) if write else None
                count = replace.replace_in_file(path, out, pattern, params["replace"],
                                                params["regex"], params["whole_cell"])
                total += count
                result.rows.append([path.name, str(count)])
                if out:
                    result.outputs.append(out)
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        verb = "made" if write else "would be made"
        result.summary = f"{total} replacement(s) {verb} in {len(inputs)} file(s)."
        return result

    def preview(self, inputs, params, ctx):
        r = self._each(inputs, params, ctx, write=False)
        return Preview(r.summary, r.headers, r.rows, r.errors)

    def run(self, inputs, params, ctx):
        return self._each(inputs, params, ctx, write=True)


@register
class ExtractRows(Operation):
    id = "excel.extract"
    name = "Extract specific information"
    category = "excel"
    description = "Collect the rows that match a condition from many files into one file."
    input_extensions = io.TABLE_EXTENSIONS
    params = (
        SHEET,
        Param("column", "Column to test", required=True),
        Param("mode", "Condition", ParamType.CHOICE, "contains",
              choices=(("contains", "Contains"), ("equals", "Is exactly"), ("regex", "Matches regular expression"),
                       ("not_empty", "Is not empty"), ("empty", "Is empty"))),
        Param("value", "Value"),
        Param("case_sensitive", "Match case", ParamType.BOOL, False),
        Param("keep_columns", "Columns to keep", help="Comma-separated. Leave empty to keep all columns."),
        Param("output_name", "Output file name", default="Extracted", required=True),
    )

    def _collect(self, inputs, params, ctx) -> tuple[pd.DataFrame, list[list[str]], list[str]]:
        if params["mode"] in ("contains", "equals", "regex") and not params["value"]:
            raise OperationError("“Value” is required for this condition.")
        frames, rows, errors = [], [], []
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                frame = io.read_table(path, params["sheet"])
                column = transform.resolve_columns(frame, [params["column"]])[0]
                found = transform.filter_rows(frame, column, params["mode"], params["value"],
                                              params["case_sensitive"])
                keep = transform.resolve_columns(frame, split_list(params["keep_columns"]))
                if keep:
                    found = found[keep]
                frames.append((path.name, found))
                rows.append([path.name, f"{len(found)} of {len(frame)} rows"])
            except OperationError as exc:
                errors.append(str(exc))
                rows.append([path.name, f"Error: {exc}"])
        if not frames:
            raise OperationError("No file could be processed. " + " ".join(errors))
        merged, _ = transform.merge_frames(frames, "similar", "Source" if len(inputs) > 1 else "")
        return merged, rows, errors

    def preview(self, inputs, params, ctx):
        merged, rows, errors = self._collect(inputs, params, ctx)
        return Preview(f"{len(merged)} matching row(s) will be extracted.", ["File", "Matches"], rows, errors)

    def run(self, inputs, params, ctx):
        merged, rows, errors = self._collect(inputs, params, ctx)
        out = ctx.out_path(safe_filename(params["output_name"]) + ".xlsx")
        io.write_table(merged, out, "Extracted")
        return OperationResult(f"{len(merged)} matching row(s) saved to {out.name}.", [out],
                               headers=["File", "Matches"], rows=rows, errors=errors)


@register
class FormattedReport(_PerFile):
    id = "excel.report"
    name = "Generate formatted report"
    description = ("Turn raw data into a presentable workbook: styled header, filters, fitted "
                   "columns, totals and an optional summary by group.")
    params = (
        SHEET,
        Param("totals", "Add a totals row for numeric columns", ParamType.BOOL, True),
        Param("group_by", "Summarise by column", placeholder="e.g. Department",
              help="Optional. Adds a “Summary” sheet with the row count and totals for each value."),
    )

    def process(self, frame, params, path, ctx):
        numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])
                   and not pd.api.types.is_bool_dtype(frame[c])]
        sheets: dict[str, pd.DataFrame] = {}
        data, totals_on = frame, set()
        if params["totals"] and numeric and len(frame):
            total = {c: frame[c].sum() for c in numeric}
            first_text = next((c for c in frame.columns if c not in numeric), None)
            if first_text is not None:
                total[first_text] = "Total"
            data = pd.concat([frame.astype(object), pd.DataFrame([total])], ignore_index=True)
            totals_on.add("Report")
        sheets["Report"] = data
        note = f"{len(frame)} rows"
        if params["group_by"]:
            column = transform.resolve_columns(frame, [params["group_by"]])[0]
            grouped = frame.groupby(column, dropna=False, sort=True)
            summary = grouped.size().rename("Rows").to_frame()
            others = [c for c in numeric if c != column]
            if others:
                summary = summary.join(grouped[others].sum())
            sheets["Summary"] = summary.reset_index()
            note += f", summary of {len(summary)} group(s)"
        out = ctx.out_path(f"{path.stem} - report.xlsx")
        io.write_workbook(out, sheets, frozenset(totals_on))
        return [out], note


@register
class ConvertFormat(Operation):
    id = "excel.convert"
    name = "Convert CSV ↔ Excel"
    category = "excel"
    description = "Convert CSV files to Excel workbooks, or each Excel sheet to a CSV file."
    input_extensions = io.TABLE_EXTENSIONS
    params = (
        Param("delimiter", "CSV separator (when creating CSV)", ParamType.CHOICE, ",",
              choices=((",", "Comma  ,"), (";", "Semicolon  ;  (French Excel)"), ("\t", "Tab"))),
    )

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=["File", "Result"])
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                if path.suffix.lower() in io.CSV_EXTENSIONS:
                    out = ctx.out_path(path.stem + ".xlsx")
                    io.write_table(io.read_table(path), out)
                    created = [out]
                else:
                    sheets = io.read_all_sheets(path)
                    created = []
                    for sheet, frame in sheets.items():
                        suffix = "" if len(sheets) == 1 else f" - {safe_filename(sheet)}"
                        out = ctx.out_path(f"{path.stem}{suffix}.csv")
                        created.append(io.write_csv(frame, out, params["delimiter"]))
                result.outputs += created
                result.rows.append([path.name, " , ".join(p.name for p in created)])
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        result.summary = f"{len(inputs) - len(result.errors)} of {len(inputs)} file(s) converted."
        return result
