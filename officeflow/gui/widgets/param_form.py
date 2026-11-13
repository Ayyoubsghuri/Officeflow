"""Builds a settings form from an operation's declared parameters."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget,
)

from officeflow.core.operation import Param, ParamType
from officeflow.gui.widgets.common import label


class ParamForm(QWidget):
    changed = Signal()  # any value edited by the user

    def __init__(self, params: Sequence[Param]) -> None:
        super().__init__()
        self._editors: dict[str, tuple[Param, QWidget]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if not params:
            layout.addWidget(label("This tool has no settings.", "muted"))
        for param in params:
            editor = self._editor(param)
            self._editors[param.key] = (param, editor)
            self._watch(editor)
            if param.type is ParamType.BOOL:
                layout.addWidget(self._check_row(editor, param.label))  # type: ignore[arg-type]
            else:
                layout.addWidget(label(param.label + (" *" if param.required else ""), "field", wrap=True))
                layout.addWidget(editor)
            if param.help:
                layout.addWidget(label(param.help, "help", wrap=True))
            layout.addSpacing(8)
        layout.addStretch()

    @staticmethod
    def _check_row(box: QCheckBox, text: str) -> QWidget:
        """Check box with a label that wraps (QCheckBox text cannot wrap)."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        caption = label(text, wrap=True)
        caption.setCursor(Qt.CursorShape.PointingHandCursor)
        caption.mousePressEvent = lambda _event: box.toggle()  # clicking the text toggles the box
        layout.addWidget(box, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(caption, 1)
        box.setAccessibleName(text)
        return row

    def _watch(self, editor: QWidget) -> None:
        signal = {QCheckBox: "toggled", QSpinBox: "valueChanged", QComboBox: "currentIndexChanged",
                  QPlainTextEdit: "textChanged", QLineEdit: "textChanged"}[type(editor)]
        getattr(editor, signal).connect(lambda *_: self.changed.emit())

    @staticmethod
    def _editor(param: Param) -> QWidget:
        if param.type is ParamType.BOOL:
            box = QCheckBox()
            box.setChecked(bool(param.default))
            return box
        if param.type is ParamType.INT:
            spin = QSpinBox()
            spin.setRange(param.minimum, param.maximum)
            spin.setValue(int(param.default or 0))
            return spin
        if param.type is ParamType.CHOICE:
            combo = QComboBox()
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            for value, text in param.choices:
                combo.addItem(text, value)
            combo.setCurrentIndex(max(combo.findData(param.default), 0))
            return combo
        if param.type is ParamType.MULTILINE:
            edit = QPlainTextEdit(str(param.default or ""))
            edit.setProperty("mono", "true")
            edit.setFixedHeight(96)
            edit.setPlaceholderText(param.placeholder)
            return edit
        line = QLineEdit(str(param.default or ""))
        line.setPlaceholderText(param.placeholder)
        return line

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, (_, editor) in self._editors.items():
            if isinstance(editor, QCheckBox):
                result[key] = editor.isChecked()
            elif isinstance(editor, QSpinBox):
                result[key] = editor.value()
            elif isinstance(editor, QComboBox):
                result[key] = editor.currentData()
            elif isinstance(editor, QPlainTextEdit):
                result[key] = editor.toPlainText()
            else:
                result[key] = editor.text()  # type: ignore[union-attr]
        return result

    def set_values(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            if key not in self._editors:
                continue
            _, editor = self._editors[key]
            if isinstance(editor, QCheckBox):
                editor.setChecked(bool(value))
            elif isinstance(editor, QSpinBox):
                editor.setValue(int(value))
            elif isinstance(editor, QComboBox):
                editor.setCurrentIndex(max(editor.findData(value), 0))
            elif isinstance(editor, QPlainTextEdit):
                editor.setPlainText(str(value))
            else:
                editor.setText(str(value))  # type: ignore[union-attr]
