"""Generic page that drives any registered operation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from officeflow.core.operation import Operation
from officeflow.core.runner import preview_operation, run_operation
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, card, label, scrollable
from officeflow.gui.widgets.file_list import InputList
from officeflow.gui.widgets.param_form import ParamForm
from officeflow.gui.widgets.run_panel import RunPanel


class ToolPage(QWidget):
    back = Signal()

    def __init__(self, ctx: AppContext, op: Operation) -> None:
        super().__init__()
        self._ctx, self._op = ctx, op
        content = QWidget()
        content.setObjectName("page")
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(18)

        head = QHBoxLayout()
        back = button("Back", icon_name="back")
        back.clicked.connect(self.back)
        head.addWidget(back)
        head.addStretch()
        root.addLayout(head)
        root.addWidget(label(op.name, "h1"))
        root.addWidget(label(op.description, "muted", wrap=True))

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)

        inputs_card = card()
        inputs_layout = QVBoxLayout(inputs_card)
        inputs_layout.setContentsMargins(22, 20, 22, 20)
        self.inputs = InputList(ctx, f"1 · {op.input_label}", op.input_extensions)
        inputs_layout.addWidget(self.inputs)
        left.addWidget(inputs_card)

        run_card = card()
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(22, 20, 22, 20)
        run_layout.addWidget(label("3 · Preview and run", "h2"))
        self.panel = RunPanel(ctx)
        self.panel.previewRequested.connect(self.preview)
        self.panel.runRequested.connect(self.run)
        run_layout.addWidget(self.panel)
        left.addWidget(run_card, 1)
        columns.addLayout(left, 3)

        settings_card = card()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(22, 20, 22, 20)
        settings_layout.setSpacing(14)
        settings_layout.addWidget(label("2 · Settings", "h2"))
        self.form = ParamForm(op.params)
        settings_layout.addWidget(self.form, 1)
        columns.addWidget(settings_card, 2)
        root.addLayout(columns, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))

    def _ready(self) -> bool:
        if not self.inputs.paths():
            self.panel.show_message("failed", "Add at least one file or folder first (step 1).")
            return False
        return True

    def preview(self) -> None:
        if not self._ready():
            return
        op, inputs, params = self._op, self.inputs.paths(), self.form.values()
        recursive = self.panel.recursive.isChecked()
        self.panel.start(lambda c: preview_operation(op, inputs, params, c, recursive),
                         self.panel.show_preview, "Preparing the preview…")

    def run(self) -> None:
        if not self._ready():
            return
        op, inputs, params = self._op, self.inputs.paths(), self.form.values()
        if params.get("move") and not self.panel.confirm(
                "Move files?", "The original files will be removed from their current folders "
                "after they have been copied to the output folder.\n\nContinue?"):
            return
        recursive, db = self.panel.recursive.isChecked(), self._ctx.db
        self.panel.start(lambda c: run_operation(op, inputs, params, c, recursive, db),
                         lambda outcome: self.panel.show_result(outcome.status, outcome.result))
