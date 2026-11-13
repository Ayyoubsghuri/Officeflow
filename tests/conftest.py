from __future__ import annotations

from pathlib import Path

import pandas as pd
import pymupdf
import pytest

from officeflow.core import registry
from officeflow.core.operation import OperationContext
from officeflow.core.runner import run_operation

registry.load_builtin()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICEFLOW_HOME", str(tmp_path / "_home"))


def make_pdf(path: Path, pages: list[str], html: bool = False) -> Path:
    """Create a PDF with one text block per page. ``html=True`` uses the
    shaping engine, which is required for Arabic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page()
            if html:
                page.insert_htmlbox(pymupdf.Rect(50, 50, 550, 700), text)
            else:
                page.insert_text((72, 100), text, fontsize=12)
        document.save(path)
    return path


def make_xlsx(path: Path, rows: list[dict], sheet: str = "Sheet1") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False, sheet_name=sheet)
    return path


@pytest.fixture
def run(tmp_path):
    """Run an operation by id into ``tmp_path/out`` and return the outcome."""

    def _run(op_id: str, inputs, params=None, out: str = "out"):
        ctx = OperationContext(tmp_path / out)
        return run_operation(registry.get(op_id), inputs, params or {}, ctx)

    return _run
