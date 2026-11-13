"""Visual identity: colours, font and the application style sheet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ACCENT = "#68E78E"
DANGER = "#FF1F22"
INK = "#000B1A"


@dataclass(frozen=True)
class Palette:
    name: str
    window: str
    sidebar: str
    card: str
    card_hover: str
    field: str
    border: str
    text: str
    muted: str
    accent_text: str       # accent used as text/icon colour
    accent_soft: str       # translucent accent background
    selection: str
    warning: str


DARK = Palette("dark", "#0A0B0C", "#0A0B0C", "#151718", "#1D2022", "#101213", "#2A2E31",
               "#F4F6F8", "#8A93A2", ACCENT, "rgba(104,231,142,0.13)", "#1C3A29", "#F5C451")
LIGHT = Palette("light", "#ECEEF1", "#FFFFFF", "#FFFFFF", "#F6F8F9", "#F7F8FA", "#D9DEE5",
                INK, "#5A6472", "#12813C", "rgba(104,231,142,0.28)", "#C9F5D6", "#9A6700")

_current = DARK


def current() -> Palette:
    return _current


def load_font() -> str:
    """Register the bundled Urbanist font; fall back to the system font."""
    file = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Urbanist.ttf"
    font_id = QFontDatabase.addApplicationFont(str(file)) if file.exists() else -1
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    return families[0] if families else QApplication.font().family()


def apply(app: QApplication, name: str, family: str) -> Palette:
    global _current
    _current = LIGHT if name == "light" else DARK
    font = QFont(family, 10)
    font.setWeight(QFont.Weight.Medium)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(_stylesheet(_current, family))
    return _current


def _stylesheet(p: Palette, family: str) -> str:
    return f"""
* {{ font-family: "{family}", "Segoe UI", "Tahoma", sans-serif; font-size: 14px; color: {p.text}; outline: 0; }}
QMainWindow {{ background: {p.window}; }}
QStackedWidget, QWidget#page, QWidget#rail {{ background: transparent; }}
QPushButton[kind="round"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 22px; padding: 0; }}
QPushButton[kind="round"]:hover {{ border-color: {p.muted}; background: {p.card_hover}; }}
QPushButton[kind="logo"] {{ background: #FFFFFF; border: none; border-radius: 22px; padding: 0; }}
QLabel[role="pill"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 20px;
    padding: 10px 18px; font-weight: 600; }}
QLabel[role="statuspill"] {{ border-radius: 20px; padding: 10px 22px; color: #FFFFFF; font-weight: 600;
    border: 1px solid rgba(255,255,255,0.25);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E7A44, stop:0.5 #3DAE66, stop:1 #1E7A44); }}
QLabel[role="alert"] {{ background: {DANGER}; color: #FFFFFF; border-radius: 9px; font-size: 10px; font-weight: 700; }}
QLineEdit[pill="true"] {{ border-radius: 21px; padding: 0 18px; background: {p.card}; min-height: 42px; max-height: 42px; }}
QFrame[floatbar="true"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 16px; }}
QPushButton[kind="tool"] {{ background: transparent; border: none; border-radius: 12px; padding: 0; min-height: 0; }}
QPushButton[kind="tool"]:hover {{ background: {p.card_hover}; }}
QPushButton[kind="tool"]:checked {{ background: {p.selection}; }}
QPushButton[kind="create"] {{ background: transparent; color: #F2557D; border: 1px solid {p.border};
    border-radius: 14px; padding: 8px 18px; }}
QPushButton[kind="create"]:hover {{ border-color: #F2557D; background: rgba(242,85,125,0.08); }}
QLabel[role="crumb"] {{ color: {p.muted}; font-size: 16px; font-weight: 600; }}
QLabel[role="draft"] {{ background: #F7A8F0; color: #6A0A5F; border-radius: 6px; padding: 3px 9px;
    font-size: 12px; font-weight: 700; }}
QLabel[role="saved"] {{ background: {p.accent_soft}; color: {p.accent_text}; border-radius: 6px; padding: 3px 9px;
    font-size: 12px; font-weight: 700; }}
QLineEdit[title="true"] {{ background: transparent; border: 1px solid transparent; border-radius: 10px;
    font-size: 20px; font-weight: 700; padding: 4px 8px; }}
QLineEdit[title="true"]:hover {{ border-color: {p.border}; }}
QLineEdit[title="true"]:focus {{ border-color: #F2557D; background: {p.field}; }}
QFrame[folder="true"] {{ background: transparent; border: none; }}
QFrame[folder="true"] QLabel {{ color: #FFFFFF; }}
QFrame[folder="true"] QLabel[role="muted"] {{ color: rgba(255,255,255,0.80); }}
QFrame[folder="true"] QProgressBar {{ background: rgba(255,255,255,0.30); max-height: 3px; min-height: 3px; }}
QFrame[folder="true"] QProgressBar::chunk {{ background: #FFFFFF; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QToolTip {{ background: {p.card}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}

QLabel {{ background: transparent; }}
QLabel[role="logo"] {{ font-size: 21px; font-weight: 700; }}
QLabel[role="h1"] {{ font-size: 28px; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 18px; font-weight: 600; }}
QLabel[role="muted"], QLabel[role="help"] {{ color: {p.muted}; }}
QLabel[role="help"] {{ font-size: 12px; }}
QLabel[role="caption"] {{ color: {p.muted}; font-size: 12px; font-weight: 600; }}
QLabel[role="stat"] {{ font-size: 34px; font-weight: 300; }}
QLabel[role="field"] {{ font-weight: 600; }}
QLabel[role="badge"] {{ background: {p.accent_soft}; color: {p.accent_text}; border-radius: 10px;
    padding: 3px 10px; font-size: 12px; font-weight: 600; }}

QFrame[card="true"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 20px; }}
QFrame[card="tool"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 20px; }}
QFrame[card="tool"]:hover {{ background: {p.card_hover}; border-color: {p.accent_text}; }}
QFrame[card="hero"] {{ border-radius: 24px; border: 1px solid rgba(255,255,255,0.18);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #17663A, stop:0.55 #2F9A58, stop:1 #5FCB82); }}
QFrame[card="hero"] QLabel {{ color: #FFFFFF; }}
QFrame[card="hero"] QLabel[role="muted"] {{ color: rgba(255,255,255,0.78); }}
QFrame[banner="success"] {{ background: {p.accent_soft}; border: 1px solid {p.accent_text}; border-radius: 14px; }}
QFrame[banner="warning"] {{ background: rgba(245,196,81,0.14); border: 1px solid {p.warning}; border-radius: 14px; }}
QFrame[banner="failed"], QFrame[banner="cancelled"] {{ background: rgba(255,31,34,0.12);
    border: 1px solid {DANGER}; border-radius: 14px; }}
QFrame[banner="info"] {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 14px; }}

QPushButton {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 17px;
    padding: 8px 18px; min-height: 20px; font-weight: 600; }}
QPushButton:hover {{ background: {p.card_hover}; border-color: {p.muted}; }}
QPushButton:pressed {{ background: {p.field}; }}
QPushButton:disabled {{ color: {p.muted}; background: transparent; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: {INK}; border: 1px solid {ACCENT}; }}
QPushButton[kind="primary"]:hover {{ background: #86F0A6; }}
QPushButton[kind="primary"]:disabled {{ background: {p.accent_soft}; color: {p.muted}; border-color: transparent; }}
QPushButton[kind="hero"] {{ background: #FFFFFF; color: {INK}; border: none; }}
QPushButton[kind="hero"]:hover {{ background: #E9FBEF; }}
QPushButton[kind="danger"] {{ color: {DANGER}; }}
QPushButton[kind="danger"]:hover {{ border-color: {DANGER}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; padding: 6px 10px; }}
QPushButton[kind="ghost"]:hover {{ background: {p.card_hover}; }}
QPushButton[kind="nav"] {{ background: transparent; border: none; border-radius: 14px;
    padding: 10px 14px; text-align: left; font-weight: 500; color: {p.muted}; }}
QPushButton[kind="nav"]:hover {{ background: {p.card_hover}; color: {p.text}; }}
QPushButton[kind="nav"]:checked {{ background: {p.accent_soft}; color: {p.accent_text}; font-weight: 600; }}

QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{ background: {p.field}; border: 1px solid {p.border};
    border-radius: 12px; padding: 8px 12px; selection-background-color: {p.selection}; selection-color: {p.text}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p.accent_text}; }}
QLineEdit:read-only {{ color: {p.muted}; }}
QPlainTextEdit[mono="true"] {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 13px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {p.card}; border: 1px solid {p.border}; padding: 4px;
    selection-background-color: {p.selection}; selection-color: {p.text}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid {p.muted}; background: {p.field}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{_check_icon()}"); }}

QListWidget, QTableWidget {{ background: {p.field}; border: 1px solid {p.border}; border-radius: 14px;
    padding: 4px; alternate-background-color: transparent; gridline-color: transparent; }}
QListWidget::item {{ padding: 7px 8px; border-radius: 8px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {p.selection}; color: {p.text}; }}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {p.border}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {p.muted}; border: none;
    border-bottom: 1px solid {p.border}; padding: 8px; font-size: 12px; font-weight: 600; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QProgressBar {{ background: {p.border}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; height: 0; width: 0; }}
QSplitter::handle {{ background: transparent; }}
QMessageBox, QFileDialog, QInputDialog {{ background: {p.window}; }}
"""


def _check_icon() -> str:
    """Write the check-mark image used by check boxes once and return its path."""
    from officeflow.services import paths

    file = paths.app_home() / "check.svg"
    if not file.exists():
        file.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M4.5 9.5l3 3 6-7" '
            f'fill="none" stroke="{INK}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            encoding="utf-8")
    return file.as_posix()
