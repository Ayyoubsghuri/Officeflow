"""Word toolbox: thin operation wrappers around ``officeflow.engines.word``."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from officeflow.core.operation import (
    Operation, OperationError, OperationResult, Param, ParamType, Preview,
)
from officeflow.core.registry import register
from officeflow.engines.excel import io as excel_io
from officeflow.engines.excel.transform import build_pattern
from officeflow.engines.word import content, convert, generate, merge
from officeflow.engines.word.document import WORD_EXTENSIONS, iter_paragraphs, open_docx, replace_in_document
from officeflow.services.files import safe_filename

SHEET = Param("sheet", "Sheet", help="Sheet name or number. Leave empty for the first sheet.",
              placeholder="First sheet")


class _EachDocument(Operation):
    category = "word"
    input_extensions = WORD_EXTENSIONS
    output_extensions = WORD_EXTENSIONS
    headers = ["Document", "Result"]

    def process(self, path: Path, params, ctx) -> tuple[list[Path], str, list[str]]:
        raise NotImplementedError

    def run(self, inputs, params, ctx):
        result = OperationResult("", headers=self.headers)
        for index, path in enumerate(inputs):
            ctx.progress(index, len(inputs), path.name)
            try:
                outputs, note, warnings = self.process(path, params, ctx)
                result.outputs += outputs
                result.warnings += warnings
                result.rows.append([path.name, note])
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
        ctx.progress(len(inputs), len(inputs), "Done")
        result.summary = (f"{len(inputs) - len(result.errors)} of {len(inputs)} document(s) processed, "
                          f"{len(result.outputs)} file(s) created.")
        return result


@register
class GenerateDocuments(Operation):
    id = "word.generate"
    name = "Generate documents from Excel"
    category = "word"
    description = ("Create one Word document per Excel row from a template. Write placeholders such as "
                   "{{Name}} or {{Montant}} in the template; they are replaced by the row's values.")
    input_extensions = excel_io.TABLE_EXTENSIONS
    output_extensions = WORD_EXTENSIONS
    input_label = "Excel or CSV file(s) with one row per document"
    params = (
        Param("template", "Word template (.docx)", ParamType.FILE, required=True, extensions=(".docx",),
              help="Placeholders: {{Column name}} for a value, {{n}} for the row number."),
        SHEET,
        Param("file_name", "File name of each document", default="{{n}}", required=True,
              help="Uses the same placeholders, e.g. “Contrat {{Nom}}” or “{{n}} - {{Référence}}”."),
        Param("skip_empty", "Skip rows that are completely empty", ParamType.BOOL, True),
    )

    def _rows(self, path: Path, params) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
        frame = excel_io.read_table(path, params["sheet"])
        if params["skip_empty"]:
            frame = frame.dropna(how="all")
        fields = generate.template_fields(Path(params["template"]))
        if not fields:
            raise OperationError("The template contains no {{placeholder}}. Write the column names between "
                                 "double braces, e.g. {{Name}}.")
        mapping, missing = generate.column_map(fields, [str(c) for c in frame.columns])
        return frame, mapping, missing

    def preview(self, inputs, params, ctx):
        rows, warnings, total = [], [], 0
        for path in inputs:
            frame, mapping, missing = self._rows(path, params)
            total += len(frame)
            rows += [[f"{{{{{field}}}}}", column, path.name] for field, column in mapping.items()]
            warnings += [f"{{{{{m}}}}} matches no column in {path.name} and will stay as written." for m in missing]
        return Preview(f"{total} document(s) will be created. Placeholders found in the template:",
                       ["Placeholder", "Column", "Data file"], rows, warnings)

    def run(self, inputs, params, ctx):
        template = Path(params["template"])
        result = OperationResult("", headers=["Data file", "Documents"])
        number = 0
        for path in inputs:
            try:
                frame, mapping, missing = self._rows(path, params)
            except OperationError as exc:
                result.errors.append(str(exc))
                result.rows.append([path.name, f"Error: {exc}"])
                continue
            result.warnings += [f"{{{{{m}}}}} matches no column in {path.name}." for m in missing]
            columns = [str(c) for c in frame.columns]
            records = frame.to_dict("records")
            for record in records:
                number += 1
                ctx.progress(number - 1, number + len(records), f"Document {number}")
                name = safe_filename(generate.file_name(params["file_name"], record, mapping, columns, number))
                out = ctx.out_path(name + ".docx")
                generate.fill(template, record, mapping, number, out)
                result.outputs.append(out)
            result.rows.append([path.name, str(len(records))])
        result.summary = f"{len(result.outputs)} document(s) generated from {template.name}."
        return result


@register
class ReplaceText(_EachDocument):
    id = "word.replace"
    name = "Replace text in documents"
    description = ("Find and replace text in many Word files at once — body, tables, headers and footers. "
                   "Formatting is kept.")
    headers = ["Document", "Replacements"]
    params = (
        Param("find", "Find", required=True),
        Param("replace", "Replace with"),
        Param("regex", "Use a regular expression", ParamType.BOOL, False),
        Param("case_sensitive", "Match case", ParamType.BOOL, False),
    )

    def _pattern(self, params):
        return build_pattern(params["find"], params["regex"], params["case_sensitive"])

    def process(self, path, params, ctx):
        pattern = self._pattern(params)
        document = open_docx(path)
        if params["regex"]:
            count = replace_in_document(document, pattern, lambda m: m.expand(params["replace"]))
        else:
            count = replace_in_document(document, pattern, lambda _m: params["replace"])
        out = ctx.out_path(path.name)
        document.save(str(out))
        return [out], str(count), []

    def preview(self, inputs, params, ctx):
        pattern = self._pattern(params)
        rows, errors, total = [], [], 0
        for path in inputs:
            try:
                count = sum(len(pattern.findall(p.text)) for p in iter_paragraphs(open_docx(path)))
                total += count
                rows.append([path.name, str(count)])
            except OperationError as exc:
                errors.append(str(exc))
        return Preview(f"{total} replacement(s) would be made in {len(inputs)} document(s).",
                       ["Document", "Matches"], rows, errors)


@register
class MergeDocuments(Operation):
    id = "word.merge"
    name = "Merge Word documents"
    category = "word"
    description = "Join several Word documents into one, in the order listed, keeping text, tables and pictures."
    input_extensions = output_extensions = WORD_EXTENSIONS
    min_inputs = 2
    params = (
        Param("page_breaks", "Start each document on a new page", ParamType.BOOL, True),
        Param("output_name", "Output file name", default="Merged", required=True),
    )

    def run(self, inputs, params, ctx):
        out = ctx.out_path(safe_filename(params["output_name"]) + ".docx")
        count, notes = merge.merge_documents(inputs, out, params["page_breaks"], ctx.progress)
        errors = [n for n in notes if "cannot" in n]
        warnings = [n for n in notes if n not in errors]
        return OperationResult(f"{count} document(s) merged into {out.name}.", [out], errors=errors,
                               warnings=warnings)


@register
class WordTables(_EachDocument):
    id = "word.tables"
    name = "Extract tables to Excel"
    description = "Copy every table of each Word document into an Excel workbook (one sheet per table)."
    output_extensions = (".xlsx",)
    headers = ["Document", "Tables"]

    def process(self, path, params, ctx):
        tables = content.extract_tables(path)
        if not tables:
            return [], "0", [f"{path.name}: no table found."]
        out = ctx.out_path(f"{path.stem} - tables.xlsx")
        excel_io.write_workbook(out, {f"Table {i}": t for i, t in enumerate(tables, 1)})
        return [out], str(len(tables)), []


@register
class WordText(_EachDocument):
    id = "word.text"
    name = "Extract text"
    description = "Save the text of each Word document as a UTF-8 text file."
    output_extensions = (".txt",)
    headers = ["Document", "Characters"]

    def process(self, path, params, ctx):
        out = ctx.out_path(path.stem + ".txt")
        return [out], str(content.export_text(path, out)), []


@register
class FormatDocuments(_EachDocument):
    id = "word.format"
    name = "Format documents"
    description = ("Give documents a consistent look: font, size, line spacing and margins; remove empty "
                   "paragraphs; set right-to-left direction on Arabic paragraphs.")
    params = (
        Param("font", "Font", default="Calibri", required=True),
        Param("arabic_font", "Font for Arabic text", default="Arial", required=True),
        Param("size", "Font size (pt)", ParamType.INT, 11, minimum=6, maximum=72),
        Param("line_spacing", "Line spacing", ParamType.CHOICE, "1.15",
              choices=(("1.0", "Single"), ("1.15", "1.15"), ("1.5", "1.5"), ("2.0", "Double"))),
        Param("margin_cm", "Page margins", ParamType.CHOICE, "2.0",
              choices=(("1.27", "Narrow (1.27 cm)"), ("2.0", "Normal (2 cm)"), ("2.54", "Wide (2.54 cm)"))),
        Param("justify", "Justify long paragraphs", ParamType.BOOL, False),
        Param("remove_empty", "Remove empty paragraphs", ParamType.BOOL, True),
        Param("rtl_arabic", "Right-to-left for Arabic paragraphs", ParamType.BOOL, True),
    )

    def process(self, path, params, ctx):
        options = content.FormatOptions(
            font=params["font"], arabic_font=params["arabic_font"], size=params["size"],
            line_spacing=float(params["line_spacing"]), margin_cm=float(params["margin_cm"]),
            justify=params["justify"], remove_empty=params["remove_empty"], rtl_arabic=params["rtl_arabic"])
        out = ctx.out_path(path.name)
        stats = content.format_document(path, out, options)
        return [out], (f"{stats['paragraphs']} paragraph(s) formatted, {stats['removed']} empty removed, "
                       f"{stats['rtl']} set right-to-left"), []


@register
class WordToPdf(_EachDocument):
    id = "word.pdf"
    name = "Convert Word to PDF"
    description = "Convert Word documents to PDF using LibreOffice or Microsoft Word installed on this computer."
    output_extensions = (".pdf",)

    def run(self, inputs, params, ctx):
        if convert.converter_name() is None:
            raise OperationError("Converting to PDF needs LibreOffice (free, libreoffice.org) or Microsoft Word "
                                 "installed on this computer.")
        return super().run(inputs, params, ctx)

    def process(self, path, params, ctx):
        open_docx(path)  # reject damaged files: LibreOffice would "convert" them as plain text
        out = ctx.out_path(path.stem + ".pdf")
        try:
            convert.to_pdf(path, out)
        except OperationError:
            ctx.release(out)
            raise
        return [out], "Converted", []
