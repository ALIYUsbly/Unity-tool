"""Small reusable widgets and the Form helper used by tab option panels."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout)


class W:
  """Tiny get/set adapter so every option widget looks the same:
  tab.v["name"].get() / .set(value)."""

  def __init__(self, get, setter):
    self.get, self.set = get, setter


def label(text, name=None, wrap=False):
  lbl = QLabel(text)
  if name:
    lbl.setObjectName(name)
  lbl.setWordWrap(wrap)
  return lbl


def button(text, cb, risk=None, accent=False, width=None):
  b = QPushButton(text)
  b.setCursor(Qt.PointingHandCursor)
  if risk:
    b.setProperty("risk", risk)
  if accent:
    b.setProperty("accent", "true")
  if width:
    b.setFixedWidth(width)
  b.clicked.connect(lambda _=False: cb())
  return b


def card(layout, title):
  """A titled rounded panel added to `layout`; returns its grid layout."""
  f = QFrame()
  f.setObjectName("card")
  outer = QVBoxLayout(f)
  outer.addWidget(label(title, "muted"))
  grid = QGridLayout()
  grid.setColumnStretch(1, 1)
  outer.addLayout(grid)
  layout.addWidget(f)
  return grid


def action_grid(layout, section, on_click, can_run=None):
  """Card with a 2-column grid of buttons, one per Action of the Section.
  on_click(section, action) is called when a button is pressed."""
  grid = card(layout, section.title)
  for c in (0, 1):
    grid.setColumnStretch(c, 1)
  for i, action in enumerate(section.actions):
    b = button(action.label, lambda a=action: on_click(section, a),
               risk=action.risk)
    if can_run is not None:
      b.setEnabled(bool(can_run(action)))
    grid.addWidget(b, i // 2, i % 2)


class Form:
  """Adds labelled option rows to a card. Every row registers a W in `store`
  under its key, so the tab can read it later with tab.v[key].get()."""

  def __init__(self, grid, store, ui):
    self.grid, self.v, self.ui = grid, store, ui
    self.row = 0

  def _next(self):
    r = self.row
    self.row += 1
    return r

  def file(self, key, text, title, flt="All Files (*)"):
    r = self._next()
    self.grid.addWidget(label(text, "muted"), r, 0)
    le = QLineEdit()
    self.grid.addWidget(le, r, 1)

    def browse():
      f = self.ui.pick_file(title, flt)
      if f:
        le.setText(f)
        self.ui.log(f"{text.upper()} SET: {os.path.basename(f)}")

    self.grid.addWidget(button("Browse", browse, accent=True), r, 2)
    self.grid.addWidget(button("Clear", le.clear), r, 3)
    self.v[key] = W(le.text, le.setText)

  def entry(self, key, text, hint=""):
    r = self._next()
    self.grid.addWidget(label(text, "muted"), r, 0)
    le = QLineEdit()
    self.grid.addWidget(le, r, 1)
    if hint:
      self.grid.addWidget(label(hint, "muted"), r, 2, 1, 2)
    self.v[key] = W(le.text, le.setText)
    return le

  def radio(self, key, text, options):
    """options = [("Auto", ""), ("4096 (UFS)", "4096"), ...]; first = default."""
    r = self._next()
    self.grid.addWidget(label(text, "muted"), r, 0)
    box = QHBoxLayout()
    grp = QButtonGroup(self.grid.parent())
    rbs = {}
    for t, val in options:
      rb = QRadioButton(t)
      grp.addButton(rb)
      box.addWidget(rb)
      rbs[val] = rb
    box.addStretch(1)
    rbs[options[0][1]].setChecked(True)
    self.grid.addLayout(box, r, 1, 1, 3)
    default = options[0][1]
    self.v[key] = W(
        lambda: next((k for k, b in rbs.items() if b.isChecked()), ""),
        lambda val: rbs.get(val, rbs[default]).setChecked(True))

  def combo(self, key, text, values, hint="", button_=None):
    """Editable drop-down. button_ = ("Detect", callback) adds a button."""
    r = self._next()
    self.grid.addWidget(label(text, "muted"), r, 0)
    cb = QComboBox()
    cb.setEditable(True)
    cb.addItems(values)
    cb.setCurrentText("")
    cb.setMinimumWidth(150)
    self.grid.addWidget(cb, r, 1)
    if button_:
      self.grid.addWidget(button(button_[0], button_[1], accent=True), r, 2)
    elif hint:
      self.grid.addWidget(label(hint, "muted"), r, 2, 1, 2)
    self.v[key] = W(cb.currentText, cb.setCurrentText)
    return cb

  def check(self, key, text, color=None):
    r = self._next()
    cb = QCheckBox(text)
    if color:
      cb.setStyleSheet(f"color:{color}")
    self.grid.addWidget(cb, r, 0, 1, 4)
    self.v[key] = W(cb.isChecked, cb.setChecked)

  def note(self, text):
    r = self._next()
    self.grid.addWidget(label(text, "muted", wrap=True), r, 0, 1, 4)
