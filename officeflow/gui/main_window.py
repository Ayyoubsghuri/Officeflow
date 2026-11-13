"""Main window: top bar, navigation rail and the page stack."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCompleter, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from officeflow import APP_NAME
from officeflow.core import registry
from officeflow.gui import icons, theme
from officeflow.gui.context import AppContext
from officeflow.gui.pages.dashboard import DashboardPage
from officeflow.gui.pages.history import HistoryPage
from officeflow.gui.pages.logs import LogsPage
from officeflow.gui.pages.settings_page import SettingsPage
from officeflow.gui.pages.toolbox import ToolboxPage
from officeflow.gui.pages.workflow_page import WorkflowPage
from officeflow.gui.widgets.common import label
from officeflow.gui.widgets.run_panel import RunPanel

NAV = (
    ("dashboard", "Dashboard", "home"), ("excel", "Excel Toolbox", "excel"), ("pdf", "PDF Toolbox", "pdf"),
    ("word", "Word Toolbox", "word"), ("workflow", "Workflow Builder", "workflow"),
    ("history", "History", "history"), ("logs", "Logs", "logs"), ("settings", "Settings", "settings"),
)


class Canvas(QWidget):
    """Window background with the subtle dot grid of the visual identity."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        palette = theme.current()
        painter.fillRect(self.rect(), QColor(palette.window))
        dot = QColor(palette.text)
        dot.setAlpha(22 if palette.name == "dark" else 30)
        painter.setPen(dot)
        for x in range(14, self.width(), 26):
            for y in range(14, self.height(), 26):
                painter.drawPoint(x, y)
        painter.end()


def round_button(icon_name: str, tooltip: str, color: str | None = None) -> QPushButton:
    widget = QPushButton()
    widget.setProperty("kind", "round")
    widget.setFixedSize(44, 44)
    widget.setIcon(icons.icon(icon_name, color, 20))
    widget.setIconSize(QSize(20, 20))
    widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


class MainWindow(QMainWindow):
    themeChanged = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self._expanded = True
        self._build("dashboard")

    # -- construction ----------------------------------------------------
    def _build(self, start: str) -> None:
        ctx = self.ctx
        canvas = Canvas()
        outer = QVBoxLayout(canvas)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._rail())
        self._stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(ctx),
            "excel": ToolboxPage(ctx, "excel"),
            "pdf": ToolboxPage(ctx, "pdf"),
            "word": ToolboxPage(ctx, "word"),
            "workflow": WorkflowPage(ctx),
            "history": HistoryPage(ctx),
            "logs": LogsPage(),
            "settings": SettingsPage(ctx),
        }
        for page in self._pages.values():
            self._stack.addWidget(page)
        self._pages["dashboard"].navigate.connect(self.navigate)
        self._pages["workflow"].navigate.connect(self.navigate)
        self._pages["dashboard"].openTool.connect(self.open_tool)
        self._pages["settings"].themeChanged.connect(self._theme_requested)
        body.addWidget(self._stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(canvas)
        self.navigate(start)

    def _top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(76)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(22, 14, 26, 10)
        layout.setSpacing(10)
        logo = round_button("workflow", APP_NAME, theme.INK)
        logo.setProperty("kind", "logo")
        logo.clicked.connect(lambda: self.navigate("dashboard"))
        menu = round_button("logs", "Show or hide the menu labels")
        menu.clicked.connect(self._toggle_rail)
        layout.addWidget(logo)
        layout.addWidget(menu)
        self._search = QLineEdit()
        self._search.setProperty("pill", "true")
        self._search.setPlaceholderText("Search tools…")
        self._search.setFixedSize(230, 44)
        names = {op.name: op.id for op in registry.all_operations()}
        completer = QCompleter(sorted(names), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(lambda name: (self.open_tool(names[name]), self._search.clear()))
        self._search.setCompleter(completer)
        layout.addWidget(self._search)
        layout.addStretch()

        today = QLabel(date.today().strftime("%B %d").replace(" 0", " "))
        today.setProperty("role", "pill")
        layout.addWidget(today)
        self._status = QLabel()
        self._status.setProperty("role", "statuspill")
        self._status.setMinimumWidth(360)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)
        layout.addStretch()

        settings = round_button("settings", "Settings")
        settings.clicked.connect(lambda: self.navigate("settings"))
        bell = round_button("history", "Tasks that need attention — open the history")
        bell.clicked.connect(lambda: self.navigate("history"))
        self._badge = QLabel(bell)
        self._badge.setProperty("role", "alert")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(18, 18)
        self._badge.move(QPoint(27, 0))
        self._mode = round_button("eye", "Switch between the dark and light theme")
        self._mode.clicked.connect(
            lambda: self._theme_requested("light" if theme.current().name == "dark" else "dark"))
        for widget in (settings, bell, self._mode):
            layout.addWidget(widget)
        return bar

    def _rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("rail")
        self._rail_widget = rail
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(18, 10, 10, 18)
        layout.setSpacing(6)
        self._nav = QButtonGroup(self)
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, text, icon_name in NAV:
            if key == "history":
                layout.addStretch()
            item = QPushButton(text)
            item.setProperty("kind", "nav")
            item.setCheckable(True)
            item.setIcon(icons.icon(icon_name, theme.current().muted, 20))
            item.setIconSize(QSize(20, 20))
            item.setToolTip(text)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self._nav.addButton(item)
            self._nav_buttons[key] = item
            layout.addWidget(item)
        self._apply_rail()
        return rail

    def _apply_rail(self) -> None:
        for (key, text, _), item in zip(NAV, self._nav_buttons.values()):
            item.setText(f"  {text}" if self._expanded else "")
        self._rail_widget.setFixedWidth(216 if self._expanded else 76)

    def _toggle_rail(self) -> None:
        self._expanded = not self._expanded
        self._apply_rail()

    # -- navigation ------------------------------------------------------
    def navigate(self, key: str) -> None:
        page = self._pages[key]
        if isinstance(page, ToolboxPage):
            page.show_grid()
        if hasattr(page, "refresh"):
            page.refresh()
        self._stack.setCurrentWidget(page)
        self._nav_buttons[key].setChecked(True)
        self._current = key
        self.refresh_status()

    def open_tool(self, op_id: str) -> None:
        category = registry.get(op_id).category
        self.navigate(category)
        self._pages[category].open_tool(op_id)

    def refresh_status(self) -> None:
        runs = self.ctx.db.list_runs(50)
        problems = sum(r.status == "failed" for r in runs)
        self._badge.setText(str(min(problems, 99)))
        self._badge.setVisible(problems > 0)
        if runs:
            last = runs[0]
            text = f"Last task · {last.name} · {last.status}"
        else:
            text = f"Ready · {len(registry.all_operations())} tools · works offline"
        self._status.setText(self._status.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 420))

    def current_page(self) -> str:
        return self._current

    # -- theme and shutdown ----------------------------------------------
    def busy(self) -> bool:
        return any(panel.is_busy() for panel in self.findChildren(RunPanel))

    def _theme_requested(self, name: str) -> None:
        if self.busy():
            QMessageBox.information(self, APP_NAME, "Please wait for the running task to finish "
                                    "before changing the theme.")
            return
        self.ctx.settings.theme = name
        self.ctx.settings.save()
        self.themeChanged.emit(name)       # the application re-applies the style sheet
        self._build(self._current)         # icons are tinted per theme, so rebuild the pages

    def closeEvent(self, event) -> None:  # noqa: N802
        panels = [p for p in self.findChildren(RunPanel) if p.is_busy()]
        if panels:
            answer = QMessageBox.question(self, APP_NAME, "A task is still running. Cancel it and quit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for panel in panels:
                panel.cancel()
                panel.wait()
        event.accept()
