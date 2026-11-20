"""Left panel: searchable list of device profiles."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLineEdit, QListWidget, QVBoxLayout

from Unity.core.profile_api import filter_profiles
from Unity.ui.widgets import button, label


class Sidebar(QFrame):
  chosen = Signal(object)   # the selected profile dict
  detect_clicked = Signal()

  def __init__(self, profiles):
    super().__init__()
    self.setObjectName("panel")
    self.setFixedWidth(280)
    self.profiles = profiles
    self.visible = []
    self.brand = None
    lay = QVBoxLayout(self)
    lay.addWidget(button("DETECT DEVICE", self.detect_clicked.emit,
                         accent=True))
    lay.addWidget(label("MODELS", "muted"))
    self.search = QLineEdit()
    self.search.setPlaceholderText("Search model / codename")
    self.search.textChanged.connect(self.refresh)
    lay.addWidget(self.search)
    self.lb = QListWidget()
    self.lb.currentRowChanged.connect(self._on_row)
    lay.addWidget(self.lb, 1)
    self.count = label("", "muted")
    lay.addWidget(self.count)
    self.refresh()

  def set_brand(self, name):
    self.brand = name or None
    self.refresh()

  def refresh(self, *_):
    self.visible = filter_profiles(self.profiles, self.search.text(),
                                   self.brand)
    self.lb.blockSignals(True)
    self.lb.clear()
    for p in self.visible:
      code = f" ({p['codename']})" if p.get("codename") else ""
      self.lb.addItem(f"{p['brand']} {p['model']}{code}")
    self.lb.blockSignals(False)
    self.count.setText(f"{len(self.visible)} of {len(self.profiles)} models")

  def _on_row(self, row):
    if 0 <= row < len(self.visible):
      self.chosen.emit(self.visible[row])
