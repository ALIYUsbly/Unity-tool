"""Top bar with the brand filter buttons."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout

from Unity.config import BRANDS
from Unity.ui.widgets import button


class BrandBar(QFrame):
  changed = Signal(str)   # selected brand, "" when the filter is cleared

  def __init__(self):
    super().__init__()
    self.setObjectName("bar")
    self.current = ""
    self.buttons = {}
    lay = QHBoxLayout(self)
    lay.setContentsMargins(12, 8, 12, 8)
    for name in BRANDS:
      b = button(name, lambda n=name: self.toggle(n))
      lay.addWidget(b, 1)
      self.buttons[name] = b

  def toggle(self, name):
    """Click a brand to filter the list; click it again to clear."""
    self.current = "" if self.current == name else name
    for n, b in self.buttons.items():
      b.setProperty("accent", "true" if n == self.current else "false")
      b.style().unpolish(b)
      b.style().polish(b)
    self.changed.emit(self.current)
