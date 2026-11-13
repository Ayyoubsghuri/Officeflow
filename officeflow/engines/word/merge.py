"""Append several Word documents into one.

Paragraphs and tables are copied with their formatting. Pictures and links
are carried over by re-registering them in the merged file; other embedded
objects (charts, OLE objects) cannot be moved between packages safely, so
they are left out and reported.
"""

from __future__ import annotations

import copy
from io import BytesIO
from pathlib import Path
from typing import Sequence

from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

from officeflow.core.operation import OperationError
from officeflow.engines.word.document import open_docx

_REL_ATTRS = (qn("r:id"), qn("r:embed"), qn("r:link"))
_OBJECT_TAGS = {qn("w:drawing"), qn("w:object"), qn("w:pict")}


def _rebind(element, source_part, target_part) -> int:
    """Point relationship ids inside ``element`` at relationships of the
    target document. Returns how many objects had to be dropped."""
    dropped = 0
    for node in list(element.iter()):
        for attr in _REL_ATTRS:
            rid = node.get(attr)
            if rid is None:
                continue
            rel = source_part.rels.get(rid)
            if rel is None:
                continue
            if rel.is_external:
                node.set(attr, target_part.relate_to(rel.target_ref, rel.reltype, is_external=True))
            elif rel.reltype == RT.IMAGE:
                new_rid, _image = target_part.get_or_add_image(BytesIO(rel.target_part.blob))
                node.set(attr, new_rid)
            else:
                holder = node
                while holder is not None and holder.tag not in _OBJECT_TAGS:
                    holder = holder.getparent()
                victim = holder if holder is not None else node
                if victim.getparent() is not None:
                    victim.getparent().remove(victim)
                    dropped += 1
                break
    return dropped


def merge_documents(sources: Sequence[Path], destination: Path, page_breaks: bool = True,
                    progress=None) -> tuple[int, list[str]]:
    """Returns (number of documents merged, warnings/errors)."""
    notes: list[str] = []
    base = None
    merged = 0
    for index, source in enumerate(sources):
        if progress:
            progress(index, len(sources), source.name)
        try:
            document = open_docx(source)
        except OperationError as exc:
            notes.append(str(exc))
            continue
        if base is None:
            base = document
            merged = 1
            continue
        body = base.element.body
        if page_breaks:
            base.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        final_sectpr = body.find(qn("w:sectPr"))
        dropped = 0
        for block in document.element.body.iterchildren():
            if block.tag == qn("w:sectPr"):
                continue
            clone = copy.deepcopy(block)
            dropped += _rebind(clone, document.part, base.part)
            if final_sectpr is not None:
                final_sectpr.addprevious(clone)
            else:
                body.append(clone)
        if dropped:
            notes.append(f"{source.name}: {dropped} embedded object(s) such as charts could not be copied.")
        merged += 1
    if base is None:
        raise OperationError("None of the documents could be read. " + " ".join(notes))
    base.save(str(destination))
    return merged, notes
