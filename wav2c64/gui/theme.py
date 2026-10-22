"""Day and night themes. Night is based on the C64 start screen blue."""

from PySide6.QtGui import QColor, QPalette

PIXEL_FONT = "Press Start 2P"

DAY = {
    "name": "day",
    "bg": "#f1efe9",
    "panel": "#ffffff",
    "input": "#ffffff",
    "text": "#1d1938",
    "muted": "#5d5880",
    "accent": "#352879",
    "accent2": "#6c5eb5",
    "accent_text": "#ffffff",
    "border": "#cbc6e3",
    "wave": "#352879",
    "wave_bg": "#ffffff",
    "grid": "#e6e3f2",
    "sel": "#6c5eb5",
    "sel_alpha": 40,
    "dim_alpha": 120,
    "overlay": "#c46c71",
    "playhead": "#d0472f",
    "ok": "#3f9a3a",
    "warn": "#c49a1f",
    "bad": "#c43c3c",
}

NIGHT = {
    "name": "night",
    "bg": "#352879",          # C64 blue
    "panel": "#2c216a",
    "input": "#241b57",
    "text": "#dcd8ff",
    "muted": "#a59ee6",
    "accent": "#6c5eb5",      # C64 light blue
    "accent2": "#8f86e8",
    "accent_text": "#ffffff",
    "border": "#6c5eb5",
    "wave": "#a49bf0",
    "wave_bg": "#241b57",
    "grid": "#2f2470",
    "sel": "#a49bf0",
    "sel_alpha": 38,
    "dim_alpha": 140,
    "overlay": "#a9ff9f",     # C64 light green
    "playhead": "#edf171",    # C64 yellow
    "ok": "#a9ff9f",
    "warn": "#edf171",
    "bad": "#ff8a8a",
}


def palette_for(t):
    p = QPalette()
    c = QColor
    p.setColor(QPalette.Window, c(t["bg"]))
    p.setColor(QPalette.WindowText, c(t["text"]))
    p.setColor(QPalette.Base, c(t["input"]))
    p.setColor(QPalette.AlternateBase, c(t["panel"]))
    p.setColor(QPalette.Text, c(t["text"]))
    p.setColor(QPalette.Button, c(t["panel"]))
    p.setColor(QPalette.ButtonText, c(t["text"]))
    p.setColor(QPalette.Highlight, c(t["accent"]))
    p.setColor(QPalette.HighlightedText, c(t["accent_text"]))
    p.setColor(QPalette.ToolTipBase, c(t["panel"]))
    p.setColor(QPalette.ToolTipText, c(t["text"]))
    p.setColor(QPalette.PlaceholderText, c(t["muted"]))
    p.setColor(QPalette.Link, c(t["accent2"]))
    p.setColor(QPalette.Disabled, QPalette.Text, c(t["muted"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, c(t["muted"]))
    p.setColor(QPalette.Disabled, QPalette.WindowText, c(t["muted"]))
    return p


def stylesheet_for(t):
    f = PIXEL_FONT
    return """
QWidget {{ color: {text}; }}
QMainWindow, QDialog {{ background: {bg}; }}
QGroupBox {{
    background: {panel}; border: 2px solid {border}; border-radius: 0px;
    margin-top: 18px; padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 8px; padding: 2px 6px;
    font-family: "{f}"; font-size: 8pt; color: {accent_text};
    background: {accent};
}}
QLabel#h1 {{ font-family: "{f}"; font-size: 10pt; color: {text}; }}
QLabel#muted {{ color: {muted}; }}
QLabel#pixel {{ font-family: "{f}"; font-size: 7pt; color: {muted}; }}
QPushButton {{
    background: {panel}; border: 2px solid {border}; padding: 6px 12px;
    border-radius: 0px; font-family: "{f}"; font-size: 7pt;
}}
QPushButton:hover {{ border-color: {accent2}; }}
QPushButton:pressed {{ background: {accent}; color: {accent_text}; }}
QPushButton:checked {{ background: {accent}; color: {accent_text}; }}
QPushButton:disabled {{ color: {muted}; border-color: {grid}; }}
QPushButton#primary {{
    background: {accent}; color: {accent_text}; border: 2px solid {accent2};
    font-size: 9pt; padding: 10px 18px;
}}
QPushButton#primary:disabled {{ background: {panel}; color: {muted}; border-color: {grid}; }}
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{
    background: {input}; border: 2px solid {border}; padding: 3px 4px; border-radius: 0px;
    selection-background-color: {accent}; selection-color: {accent_text};
}}
QComboBox QAbstractItemView {{ background: {input}; selection-background-color: {accent}; }}
QTabWidget::pane {{ border: 2px solid {border}; background: {panel}; }}
QTabBar::tab {{
    background: {bg}; border: 2px solid {border}; padding: 6px 10px; margin-right: 2px;
    font-family: "{f}"; font-size: 7pt;
}}
QTabBar::tab:selected {{ background: {accent}; color: {accent_text}; }}
QProgressBar {{
    border: 2px solid {border}; background: {input}; text-align: center; height: 22px;
    border-radius: 0px; font-family: "{f}"; font-size: 7pt;
}}
QProgressBar::chunk {{ background: {ok}; }}
QProgressBar[level="warn"]::chunk {{ background: {warn}; }}
QProgressBar[level="bad"]::chunk {{ background: {bad}; }}
QTextBrowser, QPlainTextEdit, QTableWidget {{
    background: {input}; border: 2px solid {border};
}}
QHeaderView::section {{ background: {accent}; color: {accent_text}; border: 0; padding: 4px; }}
QScrollBar:horizontal {{ background: {panel}; height: 14px; border: 1px solid {border}; }}
QScrollBar::handle:horizontal {{ background: {accent2}; min-width: 24px; }}
QScrollBar:vertical {{ background: {panel}; width: 14px; border: 1px solid {border}; }}
QScrollBar::handle:vertical {{ background: {accent2}; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSlider::groove:horizontal {{ height: 6px; background: {grid}; border: 1px solid {border}; }}
QSlider::handle:horizontal {{ background: {accent}; width: 12px; margin: -6px 0; border: 1px solid {accent2}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 2px solid {border}; background: {input}; }}
QCheckBox::indicator:checked {{ background: {accent2}; }}
QToolTip {{ background: {panel}; color: {text}; border: 2px solid {border}; padding: 4px; }}
QSplitter::handle {{ background: {bg}; }}
""".format(f=f, **t)
