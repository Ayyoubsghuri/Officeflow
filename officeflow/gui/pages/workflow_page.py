"""Workflow Builder: chain tools into a reusable automation."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QListWidget, QMessageBox, QVBoxLayout, QWidget,
)

from officeflow.core import registry
from officeflow.core.operation import OperationError
from officeflow.core.workflow import Step, Workflow, as_result, run_workflow
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, card, label, page_header, scrollable
from officeflow.gui.widgets.file_list import InputList
from officeflow.gui.widgets.param_form import ParamForm
from officeflow.gui.widgets.run_panel import RunPanel


class WorkflowPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._steps: list[Step] = []
        self._form: ParamForm | None = None
        self._editing = -1
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 28, 36, 28)
        root.setSpacing(18)
        root.addWidget(page_header("Workflow Builder", "Combine tools into a chain. Each step receives the files "
                                   "produced by the step before it. Save the workflow to run it again later."))

        bar = card()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(22, 16, 22, 16)
        bar_layout.setSpacing(10)
        self._saved = QComboBox()
        self._saved.setMinimumWidth(220)
        self._saved.activated.connect(self._load_selected)
        self._name = QLineEdit()
        self._name.setPlaceholderText("Workflow name, e.g. Monthly invoices")
        save = button("Save", icon_name="save")
        new = button("New", icon_name="plus")
        delete = button("Delete", "danger", "trash")
        save.clicked.connect(self._save)
        new.clicked.connect(self._new)
        delete.clicked.connect(self._delete)
        bar_layout.addWidget(label("Saved", "field"))
        bar_layout.addWidget(self._saved)
        bar_layout.addWidget(label("Name", "field"))
        bar_layout.addWidget(self._name, 1)
        for widget in (save, new, delete):
            bar_layout.addWidget(widget)
        root.addWidget(bar)

        middle = QHBoxLayout()
        middle.setSpacing(18)
        steps_card = card()
        steps_layout = QVBoxLayout(steps_card)
        steps_layout.setContentsMargins(22, 20, 22, 20)
        steps_layout.setSpacing(10)
        steps_layout.addWidget(label("1 · Steps", "h2"))
        self._list = QListWidget()
        self._list.setMinimumHeight(190)
        self._list.currentRowChanged.connect(self._select)
        steps_layout.addWidget(self._list, 1)
        add_row = QHBoxLayout()
        self._tools = QComboBox()
        for op in registry.all_operations():
            self._tools.addItem(f"{registry.CATEGORIES[op.category]} · {op.name}", op.id)
        add = button("Add step", "primary", "plus")
        add.clicked.connect(self._add)
        add_row.addWidget(self._tools, 1)
        add_row.addWidget(add)
        steps_layout.addLayout(add_row)
        move_row = QHBoxLayout()
        for text, icon_name, slot in (("Up", "up", lambda: self._move(-1)), ("Down", "down", lambda: self._move(1)),
                                      ("Remove", "trash", self._remove)):
            control = button(text, "ghost", icon_name)
            control.clicked.connect(slot)
            move_row.addWidget(control)
        move_row.addStretch()
        steps_layout.addLayout(move_row)
        middle.addWidget(steps_card, 2)

        settings_card = card()
        self._settings_layout = QVBoxLayout(settings_card)
        self._settings_layout.setContentsMargins(22, 20, 22, 20)
        self._settings_layout.setSpacing(12)
        self._settings_title = label("2 · Step settings", "h2")
        self._settings_layout.addWidget(self._settings_title)
        self._hint = label("Add a step, then select it to change its settings.", "muted", wrap=True)
        self._settings_layout.addWidget(self._hint)
        self._settings_layout.addStretch()
        middle.addWidget(settings_card, 3)
        root.addLayout(middle)

        run_card = card()
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(22, 20, 22, 20)
        run_layout.setSpacing(14)
        self.inputs = InputList(ctx, "3 · Files or folders for the first step", ())
        run_layout.addWidget(self.inputs)
        self.panel = RunPanel(ctx, "Run workflow", with_preview=False)
        self.panel.show_counts = False
        self.panel.runRequested.connect(self.run)
        run_layout.addWidget(self.panel)
        root.addWidget(run_card)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
        self._reload_saved()

    # -- steps -----------------------------------------------------------
    def _commit(self) -> None:
        """Store the values of the form being edited back into its step."""
        if self._form is not None and 0 <= self._editing < len(self._steps):
            self._steps[self._editing].params = self._form.values()

    def _refresh_list(self, select: int = -1) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for number, step in enumerate(self._steps, 1):
            try:
                name = registry.get(step.op_id).name
            except KeyError:
                name = f"Unknown tool ({step.op_id})"
            self._list.addItem(f"{number}.  {name}")
        self._list.blockSignals(False)
        self._editing = -1
        self._list.setCurrentRow(select if self._steps else -1)
        if not self._steps:
            self._select(-1)
        first = registry.get(self._steps[0].op_id) if self._steps and self._known(self._steps[0]) else None
        self.inputs.set_filter("3 · " + (first.input_label if first else "Files or folders for the first step"),
                               first.input_extensions if first else ())

    @staticmethod
    def _known(step: Step) -> bool:
        try:
            registry.get(step.op_id)
            return True
        except KeyError:
            return False

    def _select(self, row: int) -> None:
        self._commit()
        if self._form is not None:
            self._form.setParent(None)
            self._form.deleteLater()
            self._form = None
        self._editing = row
        valid = 0 <= row < len(self._steps) and self._known(self._steps[row])
        self._hint.setVisible(not valid)
        if not valid:
            self._settings_title.setText("2 · Step settings")
            return
        step = self._steps[row]
        op = registry.get(step.op_id)
        self._settings_title.setText(f"2 · Step {row + 1} — {op.name}")
        self._form = ParamForm(op.params)
        self._form.set_values(step.params)
        self._settings_layout.insertWidget(2, self._form)

    def _add(self) -> None:
        self._commit()
        self._steps.append(Step(self._tools.currentData()))
        self._refresh_list(len(self._steps) - 1)

    def _remove(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._steps):
            self._form_discard()
            del self._steps[row]
            self._refresh_list(min(row, len(self._steps) - 1))

    def _move(self, delta: int) -> None:
        row = self._list.currentRow()
        target = row + delta
        if 0 <= row < len(self._steps) and 0 <= target < len(self._steps):
            self._commit()
            self._steps[row], self._steps[target] = self._steps[target], self._steps[row]
            self._form_discard()
            self._refresh_list(target)

    def _form_discard(self) -> None:
        self._editing = -1

    # -- persistence -----------------------------------------------------
    def workflow(self) -> Workflow:
        self._commit()
        return Workflow(self._name.text().strip(), [Step(s.op_id, dict(s.params)) for s in self._steps])

    def _reload_saved(self, select: str = "") -> None:
        self._saved.clear()
        self._saved.addItem("Choose a saved workflow…", "")
        for name in self._ctx.db.list_workflows():
            self._saved.addItem(name, name)
        self._saved.setCurrentIndex(max(self._saved.findData(select), 0))

    def _save(self) -> None:
        workflow = self.workflow()
        try:
            if not workflow.name:
                raise OperationError("Give the workflow a name before saving it.")
            workflow.validate()
        except OperationError as exc:
            self.panel.show_message("failed", str(exc))
            return
        self._ctx.db.save_workflow(workflow.name, workflow.to_dict())
        self._reload_saved(workflow.name)
        self.panel.show_message("success", f"Workflow “{workflow.name}” saved.")

    def _load_selected(self) -> None:
        name = self._saved.currentData()
        data = self._ctx.db.load_workflow(name) if name else None
        if data:
            self.load(Workflow.from_dict(data))

    def load(self, workflow: Workflow) -> None:
        self._form_discard()
        self._name.setText(workflow.name)
        self._steps = [Step(s.op_id, dict(s.params)) for s in workflow.steps]
        self._refresh_list(0)

    def _new(self) -> None:
        self.load(Workflow(""))
        self._saved.setCurrentIndex(0)

    def _delete(self) -> None:
        name = self._saved.currentData()
        if name and QMessageBox.question(self, "Delete workflow?", f"Delete the saved workflow “{name}”?") \
                == QMessageBox.StandardButton.Yes:
            self._ctx.db.delete_workflow(name)
            self._new()
            self._reload_saved()

    # -- run -------------------------------------------------------------
    def run(self) -> None:
        workflow = self.workflow()
        workflow.name = workflow.name or "Unsaved workflow"
        try:
            workflow.validate()
        except OperationError as exc:
            self.panel.show_message("failed", str(exc))
            return
        inputs = self.inputs.paths()
        if not inputs:
            self.panel.show_message("failed", "Add at least one file or folder for the first step.")
            return
        if any(s.params.get("move") for s in workflow.steps) and not self.panel.confirm(
                "Move files?", "A step is set to move files: originals will be removed from their "
                "folders.\n\nContinue?"):
            return
        recursive, db = self.panel.recursive.isChecked(), self._ctx.db
        self.panel.start(lambda c: run_workflow(workflow, inputs, c, recursive, db),
                         lambda outcome: self.panel.show_result(outcome.status, as_result(outcome)))
