"""Right-hand panel: status, Stop/Clear buttons and the colored log."""
import re
import time

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                               QVBoxLayout)

from Unity.config import MAX_LOG_LINES, PROGRESS_RE
from Unity.theme import BUSY, OK, WARN
from Unity.ui.widgets import button


class LogPanel(QFrame):
  stop_clicked = Signal()

  def __init__(self):
    super().__init__()
    self.setObjectName("panel")
    self._has_text = False
    self._last_progress = False
    lay = QVBoxLayout(self)
    head = QHBoxLayout()
    self.dot = QLabel("●")
    self.dot.setStyleSheet(f"color:{OK}")
    self.status = QLabel("READY")
    self.status.setStyleSheet("font-weight:bold")
    head.addWidget(self.dot)
    head.addWidget(self.status)
    head.addStretch(1)
    head.addWidget(button("Clear", self.clear))
    self.btn_stop = button("Stop", self.stop_clicked.emit, risk="danger")
    self.btn_stop.setEnabled(False)
    head.addWidget(self.btn_stop)
    lay.addLayout(head)
    self.box = QPlainTextEdit()
    self.box.setReadOnly(True)
    self.box.setMaximumBlockCount(MAX_LOG_LINES)
    self.box.setStyleSheet(
        "font-family:'JetBrains Mono','DejaVu Sans Mono',Consolas,monospace;"
        "font-size:12px;")
    lay.addWidget(self.box, 1)

  @staticmethod
  def _fmt(msg):
    low = msg.lower()
    color = None
    if msg.startswith("SUCCESS"):
      color = OK
    elif re.match(r"^\[\d+/\d+\]", msg):
      color = "#7aa7ff"
    elif "warning" in low:
      color = WARN
    elif any(w in low for w in ("error", "critical", "abort", "failed")):
      color = "#ff7b7b"
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color or "#9fe3c9"))
    return fmt

  def write(self, msg):
    """Add a log line. Consecutive progress lines (45%) replace each other."""
    is_progress = bool(PROGRESS_RE.search(msg))
    cur = self.box.textCursor()
    cur.movePosition(QTextCursor.End)
    if is_progress and self._last_progress:
      cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
      cur.removeSelectedText()
    elif self._has_text:
      cur.insertBlock()
    cur.insertText(f"[{time.strftime('%H:%M:%S')}] {msg}", self._fmt(msg))
    self._has_text = True
    self._last_progress = is_progress
    self.box.moveCursor(QTextCursor.End)

  def set_busy(self, busy):
    self.dot.setStyleSheet(f"color:{BUSY if busy else OK}")
    self.status.setText("RUNNING..." if busy else "READY")
    self.btn_stop.setEnabled(busy)

  def clear(self):
    self.box.clear()
    self._has_text = False
    self._last_progress = False
