"""Workflow Builder: a node canvas where tools are chained into a workflow.

The page owns the workflow (ordered steps); the canvas only displays it. Every
change goes through ``_change`` so it can be undone, and the canvas is rebuilt
from the steps afterwards.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLineEdit, QMenu, QMessageBox, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from officeflow.core import registry
from officeflow.core.operation import OperationError, ParamType
from officeflow.core.workflow import Step, Workflow, as_result, run_workflow
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, card, label
from officeflow.gui.widgets.file_list import InputList
from officeflow.gui.widgets.flow_canvas import START_ID, FlowScene, FlowView, NodeData
from officeflow.gui.widgets.param_form import ParamForm
from officeflow.gui.widgets.run_panel import RunPanel

UNDO_LIMIT = 60


class WorkflowPage(QWidget):
    navigate = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.steps: list[Step] = []
        self._uids: list[str] = []
        self._counter = itertools.count(1)
        self.selected = START_ID
        self.form: ParamForm | None = None
        self._form_uid = ""
        self._form_dirty = False
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self._saved_state: dict[str, Any] | None = None
        self._status: dict[str, tuple[str, str]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 14, 28, 22)
        root.setSpacing(14)
        root.addLayout(self._top_bar())

        body = QHBoxLayout()
        body.setSpacing(18)
        self.scene = FlowScene()
        self.scene.nodeSelected.connect(self._on_node_selected)
        self.scene.addRequested.connect(lambda: self._show_add_menu(QCursor.pos()))
        self.view = FlowView(self.scene)
        self.view.create_button.clicked.connect(
            lambda: self._show_add_menu(self.view.create_button.mapToGlobal(QPoint(0, -8)), above=True))
        self.view.undo_button.clicked.connect(self.undo)
        self.view.redo_button.clicked.connect(self.redo)
        canvas = QFrame()
        canvas.setProperty("card", "true")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(1, 1, 1, 1)
        canvas_layout.addWidget(self.view)
        body.addWidget(canvas, 1)
        body.addWidget(self._inspector())
        root.addLayout(body, 1)

        for keys, slot in ((QKeySequence.StandardKey.Undo, self.undo), (QKeySequence.StandardKey.Redo, self.redo),
                           ("Ctrl+Shift+Z", self.redo), (QKeySequence.StandardKey.Delete, self._delete_selected),
                           (QKeySequence.StandardKey.Save, self.save)):
            QShortcut(QKeySequence(keys), self, slot, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self._reload_saved()
        self._rebuild()
        self._show_inspector()
        self._update_badges()

    # -- layout ------------------------------------------------------------
    def _top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        crumb = button("Dashboard", "ghost", "folder")
        crumb.setProperty("role", "crumb")
        crumb.clicked.connect(lambda: self.navigate.emit("dashboard"))
        bar.addWidget(crumb)
        bar.addWidget(label("/", "crumb"))
        self.name_edit = QLineEdit()
        self.name_edit.setProperty("title", "true")
        self.name_edit.setPlaceholderText("Untitled workflow")
        self.name_edit.setMinimumWidth(260)
        self.name_edit.textEdited.connect(lambda _t: self._update_badges())
        bar.addWidget(self.name_edit)
        self.badge = label("Draft", "draft")
        self.badge.setFixedHeight(24)
        bar.addWidget(self.badge)
        bar.addStretch()
        self.saved_combo = QComboBox()
        self.saved_combo.setMinimumWidth(210)
        self.saved_combo.activated.connect(lambda _i: self.load_named(self.saved_combo.currentData()))
        bar.addWidget(self.saved_combo)
        for text, kind, icon_name, slot in (("New", "", "plus", self.new), ("Delete", "danger", "trash", self.delete),
                                            ("Save", "", "save", self.save), ("Run", "primary", "play", self.run)):
            widget = button(text, kind, icon_name)
            widget.clicked.connect(slot)
            bar.addWidget(widget)
        return bar

    def _inspector(self) -> QWidget:
        frame = card()
        frame.setFixedWidth(380)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        scroll.setWidget(self.stack)
        outer.addWidget(scroll)

        start = QWidget()
        layout = QVBoxLayout(start)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(label("Start", "caption"))
        layout.addWidget(label("Files & folders", "h2"))
        layout.addWidget(label("These files go into the first step. Each following step receives the "
                               "files produced by the step before it.", "muted", wrap=True))
        self.inputs = InputList(self._ctx, "Input", ())
        self.inputs.setMinimumHeight(220)
        self.inputs.changed.connect(self._rebuild)
        layout.addWidget(self.inputs)
        self.panel = RunPanel(self._ctx, "Run workflow", with_preview=False)
        self.panel.show_counts = False
        self.panel.runRequested.connect(self.run)
        layout.addWidget(self.panel, 1)
        self.stack.addWidget(start)

        step = QWidget()
        self._step_layout = QVBoxLayout(step)
        self._step_layout.setContentsMargins(20, 20, 20, 20)
        self._step_layout.setSpacing(10)
        self._step_chip = label("", "caption")
        self._step_title = label("", "h2", wrap=True)
        self._step_about = label("", "muted", wrap=True)
        self._step_warning = label("", wrap=True)
        self._step_warning.setStyleSheet("color: #FF1F22;")
        self._step_result = label("", "muted", wrap=True)
        for widget in (self._step_chip, self._step_title, self._step_about, self._step_warning):
            self._step_layout.addWidget(widget)
        row = QHBoxLayout()
        self._earlier = button("", icon_name="back", tooltip="Move this step earlier")
        self._later = button("", icon_name="forward", tooltip="Move this step later")
        remove = button("Remove", "danger", "trash")
        self._earlier.clicked.connect(lambda: self.move_step(self.selected, -1))
        self._later.clicked.connect(lambda: self.move_step(self.selected, 1))
        remove.clicked.connect(self._delete_selected)
        for widget in (self._earlier, self._later):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(remove)
        self._step_layout.addLayout(row)
        self._step_layout.addWidget(self._step_result)
        self._step_layout.addSpacing(6)
        self._step_layout.addWidget(label("Settings", "caption"))
        self._form_slot = self._step_layout.count()
        self._step_layout.addStretch()
        self.stack.addWidget(step)
        return frame

    # -- state helpers -----------------------------------------------------
    def _state(self) -> dict[str, Any]:
        return {"name": self.name_edit.text(), "steps": [(s.op_id, dict(s.params)) for s in self.steps],
                "uids": list(self._uids), "selected": self.selected}

    def _restore(self, state: dict[str, Any]) -> None:
        self._close_form()
        self.name_edit.setText(state["name"])
        self.steps = [Step(op, dict(params)) for op, params in state["steps"]]
        self._uids = list(state["uids"])
        self.selected = state["selected"] if state["selected"] in self._uids else START_ID
        self._rebuild()
        self._show_inspector()
        self._update_badges()

    def _change(self) -> None:
        """Record the current state before a modification (for undo)."""
        self._commit_form()
        self._undo.append(self._state())
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self._status.clear()

    def workflow(self) -> Workflow:
        self._commit_form()
        return Workflow(self.name_edit.text().strip(), [Step(s.op_id, dict(s.params)) for s in self.steps])

    def _index(self, uid: str) -> int:
        return self._uids.index(uid) if uid in self._uids else -1

    # -- editing -----------------------------------------------------------
    def add_step(self, op_id: str) -> None:
        self._change()
        self.steps.append(Step(op_id))
        uid = f"s{next(self._counter)}"
        self._uids.append(uid)
        self.selected = uid
        self._rebuild()
        self._show_inspector()
        self._update_badges()

    def remove_step(self, uid: str) -> None:
        index = self._index(uid)
        if index < 0:
            return
        self._change()
        del self.steps[index], self._uids[index]
        self.selected = self._uids[min(index, len(self._uids) - 1)] if self._uids else START_ID
        self._close_form()
        self._rebuild()
        self._show_inspector()
        self._update_badges()

    def move_step(self, uid: str, delta: int) -> None:
        index = self._index(uid)
        target = index + delta
        if index < 0 or not 0 <= target < len(self.steps):
            return
        self._change()
        for items in (self.steps, self._uids):
            items[index], items[target] = items[target], items[index]
        self.scene.positions.clear()
        self._rebuild()
        self._show_inspector()
        self._update_badges()

    def _delete_selected(self) -> None:
        if self.selected != START_ID:
            self.remove_step(self.selected)

    def undo(self) -> None:
        if self._undo:
            self._commit_form()
            self._redo.append(self._state())
            self._restore(self._undo.pop())

    def redo(self) -> None:
        if self._redo:
            self._commit_form()
            self._undo.append(self._state())
            self._restore(self._redo.pop())

    def select(self, key: str) -> None:
        self.scene.select(key)
        self._on_node_selected(key)

    def _on_node_selected(self, key: str) -> None:
        key = key or self.selected
        if key == self.selected and (key == START_ID or self._form_uid == key):
            return
        self._commit_form()
        self.selected = key if key == START_ID or key in self._uids else START_ID
        self._show_inspector()

    def _show_add_menu(self, position: QPoint, above: bool = False) -> None:
        menu = QMenu(self)
        for category, title in registry.CATEGORIES.items():
            operations = registry.by_category(category)
            if not operations:
                continue
            sub = menu.addMenu(title)
            for op in operations:
                action = sub.addAction(op.name)
                action.setToolTip(op.description)
                action.triggered.connect(lambda _=False, op_id=op.id: self.add_step(op_id))
        if above:
            position -= QPoint(0, menu.sizeHint().height())
        menu.exec(position)

    # -- inspector -----------------------------------------------------------
    def _close_form(self) -> None:
        if self.form is not None:
            self.form.setParent(None)
            self.form.deleteLater()
        self.form, self._form_uid, self._form_dirty = None, "", False

    def _commit_form(self) -> None:
        index = self._index(self._form_uid)
        if self.form is not None and index >= 0:
            self.steps[index].params = self.form.values()

    def _on_form_changed(self) -> None:
        index = self._index(self._form_uid)
        if index < 0 or self.form is None:
            return
        if not self._form_dirty:  # one undo entry per editing session of a step
            self._undo.append(self._state())
            del self._undo[:-UNDO_LIMIT]
            self._redo.clear()
            self._form_dirty = True
        self.steps[index].params = self.form.values()
        self._status.clear()
        self._refresh_nodes()
        self._update_badges()

    def _show_inspector(self) -> None:
        index = self._index(self.selected)
        if index < 0:
            self._close_form()
            self.stack.setCurrentIndex(0)
            return
        op = registry.get(self.steps[index].op_id)
        if self._form_uid != self.selected:
            self._close_form()
            self.form = ParamForm(op.params)
            self.form.set_values(self.steps[index].params)
            self.form.changed.connect(self._on_form_changed)
            self._form_uid = self.selected
            self._step_layout.insertWidget(self._form_slot, self.form)
        self._step_chip.setText(f"STEP {index + 1} · {registry.CATEGORIES[op.category].upper()}")
        self._step_title.setText(op.name)
        self._step_about.setText(op.description)
        warning = self._warnings().get(self.selected, "")
        self._step_warning.setText(warning)
        self._step_warning.setVisible(bool(warning))
        status = self._status.get(self.selected)
        self._step_result.setText(f"Last run: {status[1]}" if status and status[1] else "")
        self._step_result.setVisible(bool(status and status[1]))
        self._earlier.setEnabled(index > 0)
        self._later.setEnabled(index < len(self.steps) - 1)
        self.stack.setCurrentIndex(1)

    # -- canvas -------------------------------------------------------------
    def _warnings(self) -> dict[str, str]:
        result = {}
        for index in range(1, len(self.steps)):
            before, after = registry.get(self.steps[index - 1].op_id), registry.get(self.steps[index].op_id)
            if not set(before.output_extensions) & set(after.input_extensions):
                result[self._uids[index]] = (f"Needs {', '.join(after.input_extensions)} but the previous "
                                             f"step produces {', '.join(before.output_extensions)}")
        return result

    @staticmethod
    def _summary(op, params: dict[str, Any]) -> str:
        for param in op.params:
            value = params.get(param.key, param.default)
            if param.type in (ParamType.TEXT, ParamType.MULTILINE) and str(value).strip():
                first = str(value).strip().splitlines()[0]
                return f"{param.label.split('(')[0].strip()}: {first}"
        return re.split(r"(?<=[.:;])\s", op.description)[0].rstrip(".")

    def _nodes(self) -> list[NodeData]:
        inputs = self.inputs.paths()
        first = registry.get(self.steps[0].op_id) if self.steps else None
        if inputs:
            subtitle = f"{len(inputs)} item(s): " + ", ".join(p.name for p in inputs[:3])
        elif first:
            subtitle = f"Add {', '.join(first.input_extensions)} files or folders"
        else:
            subtitle = "Choose the files to process"
        nodes = [NodeData(START_ID, "start", "folder", "Start", "Files & folders", subtitle, chip_lime=True)]
        warnings = self._warnings()
        for index, (uid, step) in enumerate(zip(self._uids, self.steps)):
            op = registry.get(step.op_id)
            status, text = self._status.get(uid, ("", ""))
            nodes.append(NodeData(uid, op.category, op.category,
                                  f"Step {index + 1}" if status else
                                  f"Step {index + 1} · {registry.CATEGORIES[op.category]}", op.name,
                                  self._summary(op, step.params), status,
                                  text if status in ("success", "warning") else "", warnings.get(uid, "")))
        return nodes

    def _rebuild(self) -> None:
        self.scene.build(self._nodes(), set(self._warnings()), self.selected)
        self.view.undo_button.setEnabled(bool(self._undo))
        self.view.redo_button.setEnabled(bool(self._redo))

    def _refresh_nodes(self) -> None:
        """Update node texts in place (keeps the item being dragged or edited)."""
        for data in self._nodes():
            item = self.scene.nodes.get(data.key)
            if item is not None:
                item.data_ = data
                item.update()
        self.view.undo_button.setEnabled(bool(self._undo))
        self.view.redo_button.setEnabled(bool(self._redo))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.view.fit()

    # -- persistence -----------------------------------------------------------
    def _definition(self) -> dict[str, Any]:
        return self.workflow().to_dict()

    def _update_badges(self) -> None:
        saved = self._saved_state is not None and self._saved_state == self._definition()
        self.badge.setText("Saved" if saved else "Draft")
        self.badge.setProperty("role", "saved" if saved else "draft")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def _reload_saved(self, select: str = "") -> None:
        self.saved_combo.clear()
        self.saved_combo.addItem("Open a saved workflow…", "")
        for name in self._ctx.db.list_workflows():
            self.saved_combo.addItem(name, name)
        self.saved_combo.setCurrentIndex(max(self.saved_combo.findData(select), 0))

    def save(self) -> None:
        workflow = self.workflow()
        try:
            if not workflow.name:
                raise OperationError("Give the workflow a name (top left) before saving it.")
            workflow.validate()
        except OperationError as exc:
            self.select(START_ID)
            self.panel.show_message("failed", str(exc))
            return
        self._ctx.db.save_workflow(workflow.name, workflow.to_dict())
        self._saved_state = workflow.to_dict()
        self._reload_saved(workflow.name)
        self._update_badges()
        self.panel.show_message("success", f"Workflow “{workflow.name}” saved.")

    def load(self, workflow: Workflow, saved: bool = False) -> None:
        self._close_form()
        self.name_edit.setText(workflow.name)
        self.steps = [Step(s.op_id, dict(s.params)) for s in workflow.steps]
        self._uids = [f"s{next(self._counter)}" for _ in self.steps]
        self.selected = START_ID
        self._undo.clear()
        self._redo.clear()
        self._status.clear()
        self._saved_state = workflow.to_dict() if saved else None
        self.scene.positions.clear()
        self._rebuild()
        self._show_inspector()
        self._update_badges()
        self.view.fit()

    def load_named(self, name: str) -> None:
        data = self._ctx.db.load_workflow(name) if name else None
        if data:
            self.load(Workflow.from_dict(data), saved=True)

    def new(self) -> None:
        self.load(Workflow(""))
        self.saved_combo.setCurrentIndex(0)

    def delete(self) -> None:
        name = self.saved_combo.currentData()
        if not name:
            self.panel.show_message("failed", "Choose a saved workflow to delete.")
            return
        if QMessageBox.question(self, "Delete workflow?", f"Delete the saved workflow “{name}”?") \
                == QMessageBox.StandardButton.Yes:
            self._ctx.db.delete_workflow(name)
            self.new()
            self._reload_saved()

    # -- run -------------------------------------------------------------------
    def run(self) -> None:
        workflow = self.workflow()
        workflow.name = workflow.name or "Unsaved workflow"
        self.select(START_ID)
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
        uids = list(self._uids)
        self._status = {uid: ("pending", "") for uid in uids}
        self._refresh_nodes()

        def progress(_done: int, _total: int, message: str) -> None:
            match = re.match(r"Step (\d+)/", message)
            if match:
                current = int(match.group(1)) - 1
                for index, uid in enumerate(uids):
                    if index < current and self._status.get(uid, ("",))[0] == "running":
                        self._status[uid] = ("success", "")
                if 0 <= current < len(uids) and self._status.get(uids[current], ("",))[0] == "pending":
                    self._status[uids[current]] = ("running", "")
                    self._refresh_nodes()

        def finished(outcome) -> None:
            for index, uid in enumerate(uids):
                if index < len(outcome.steps):
                    step = outcome.steps[index][1]
                    count = len(step.result.outputs)
                    self._status[uid] = (step.status, f"{count} file{'s' if count != 1 else ''}"
                                         if step.status in ("success", "warning") else step.result.summary)
                else:
                    self._status[uid] = ("pending", "")
            if uids == self._uids:
                self._refresh_nodes()
            self.panel.show_result(outcome.status, as_result(outcome))

        recursive, db = self.panel.recursive.isChecked(), self._ctx.db
        self.panel.start(lambda c: run_workflow(workflow, inputs, c, recursive, db), finished,
                         "Running the workflow…", progress)
