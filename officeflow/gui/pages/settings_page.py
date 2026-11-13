"""Application settings."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import officeflow
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, card, label, open_folder, page_header, scrollable
from officeflow.services import paths


class SettingsPage(QWidget):
    themeChanged = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        content = QWidget()
        content.setObjectName("page")
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(18)
        root.addWidget(page_header("Settings"))

        look = self._section(root, "Appearance")
        look.addWidget(label("Theme", "field"))
        self._theme = QComboBox()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        self._theme.setCurrentIndex(max(self._theme.findData(ctx.settings.theme), 0))
        self._theme.currentIndexChanged.connect(self._theme_selected)
        self._theme.setMaximumWidth(260)
        look.addWidget(self._theme)

        files = self._section(root, "Files")
        files.addWidget(label("Default output folder", "field"))
        row = QHBoxLayout()
        self._output = QLineEdit(str(ctx.settings.resolved_output_dir()))
        self._output.editingFinished.connect(self._save)
        browse = button("Browse", icon_name="folder")
        browse.clicked.connect(self._browse)
        row.addWidget(self._output, 1)
        row.addWidget(browse)
        files.addLayout(row)
        files.addWidget(label("New tool pages start with this folder. Each tool lets you change it.", "help"))
        self._recursive = QCheckBox("Include files in sub-folders by default")
        self._recursive.setChecked(ctx.settings.include_subfolders)
        self._recursive.toggled.connect(self._save)
        files.addWidget(self._recursive)

        extend = self._section(root, "Plugins")
        extend.addWidget(label("Extra tools can be added by placing plugin files in the plugin folder. "
                               "They are loaded the next time OfficeFlow starts. Only install plugins "
                               "from people you trust.", "muted", wrap=True))
        row = QHBoxLayout()
        plugins = button("Open plugin folder", icon_name="folder")
        plugins.clicked.connect(lambda: open_folder(paths.plugins_dir()))
        row.addWidget(plugins)
        row.addStretch()
        extend.addLayout(row)

        about = self._section(root, "About")
        about.addWidget(label(f"OfficeFlow {officeflow.__version__} — offline office automation", "field"))
        about.addWidget(label(f"Data folder: {paths.app_home()}", "muted", wrap=True))
        root.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))

    @staticmethod
    def _section(root: QVBoxLayout, title: str) -> QVBoxLayout:
        box = card()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(label(title, "h2"))
        root.addWidget(box)
        return layout

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Default output folder", self._output.text())
        if folder:
            self._output.setText(folder)
            self._save()

    def _save(self) -> None:
        self._ctx.settings.output_dir = self._output.text().strip()
        self._ctx.settings.include_subfolders = self._recursive.isChecked()
        self._ctx.settings.save()

    def _theme_selected(self) -> None:
        self._ctx.settings.theme = self._theme.currentData()
        self._ctx.settings.save()
        self.themeChanged.emit(self._ctx.settings.theme)
