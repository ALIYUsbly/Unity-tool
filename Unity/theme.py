"""Colours and the Qt stylesheet (QSS). Change the look here only."""

BG, PANEL, PANEL2, INPUT, HOVER = (
    "#12141a", "#2a3042", "#222632", "#0f1117", "#2d3342")
ACCENT, ACCENT_HOVER, TEXT, MUTED = "#4f8cff", "#6aa0ff", "#dfe3ea", "#8b93a3"
OK, BUSY, WARN = "#3ddc97", "#ff6b6b", "#f5b84a"
# (normal, hover) button colours per risk level
RISK = {"safe": ("#2a3040", "#353d52"), "write": ("#8a5f12", "#a06f17"),
        "danger": ("#8f2a37", "#a83444")}

QSS = f"""
* {{ font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QFrame#panel {{ background: {PANEL}; border-radius: 12px; }}
QFrame#card {{ background: {PANEL2}; border-radius: 10px; }}
QFrame#bar {{ background: {PANEL}; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#note {{ background: #2c2614; color: {WARN}; border-radius: 8px;
  padding: 8px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent;
  border: none; }}
QPushButton {{ background: {PANEL2}; border: none; border-radius: 8px;
  padding: 8px 12px; }}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:disabled {{ color: #5a6070; }}
QPushButton[risk="safe"] {{ background: {RISK['safe'][0]}; }}
QPushButton[risk="safe"]:hover {{ background: {RISK['safe'][1]}; }}
QPushButton[risk="write"] {{ background: {RISK['write'][0]}; }}
QPushButton[risk="write"]:hover {{ background: {RISK['write'][1]}; }}
QPushButton[risk="danger"] {{ background: {RISK['danger'][0]}; }}
QPushButton[risk="danger"]:hover {{ background: {RISK['danger'][1]}; }}
QPushButton[accent="true"] {{ background: {ACCENT}; color: white; }}
QPushButton[accent="true"]:hover {{ background: {ACCENT_HOVER}; }}
QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{ background: {INPUT};
  border: none; border-radius: 8px; padding: 6px; }}
QComboBox QAbstractItemView {{ background: {INPUT};
  selection-background-color: {ACCENT}; }}
QListWidget::item {{ padding: 4px; }}
QListWidget::item:selected {{ background: {ACCENT}; color: white;
  border-radius: 4px; }}
QTabWidget::pane {{ border: none; background: {PANEL}; border-radius: 12px; }}
QTabBar::tab {{ background: {PANEL2}; padding: 8px 16px; margin-right: 4px;
  border-radius: 8px; font-weight: bold; }}
QTabBar::tab:selected {{ background: {ACCENT}; color: white; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {HOVER}; border-radius: 5px;
  min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
"""
