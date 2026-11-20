"""Dialogs and file pickers. One `Prompts` object is created by the main
window and handed to every builder as `ui`."""
import os

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout)
from Unity.core.scatter import SCATTER_SKIP
from Unity.theme import TEXT
from Unity.ui.widgets import button, label


class Prompts:

  def __init__(self, parent, log):
    self.parent = parent
    self.log = log          # log(text) writes a line to the log panel

  # ---- messages -------------------------------------------------------
  def dialog(self, title, text, ok="OK", cancel=None, danger=False):
    """Modal dialog. Returns True only if the OK button was pressed."""
    dlg = QDialog(self.parent)
    dlg.setWindowTitle(title)
    long_text = text.count("\n") > 5 or len(text) > 220
    dlg.resize(*((580, 440) if long_text else (460, 230)))
    lay = QVBoxLayout(dlg)
    t = QLabel(title)
    t.setStyleSheet(f"font-weight:bold;color:{'#ff8a8a' if danger else TEXT}")
    lay.addWidget(t)
    box = QPlainTextEdit(text)
    box.setReadOnly(True)
    lay.addWidget(box, 1)
    row = QHBoxLayout()
    row.addStretch(1)
    if cancel:
      row.addWidget(button(cancel, dlg.reject, width=110))
    row.addWidget(button(ok, dlg.accept, risk="danger" if danger else None,
                         accent=not danger, width=110))
    lay.addLayout(row)
    return dlg.exec() == QDialog.Accepted

  # ---- text input -----------------------------------------------------
  def ask_name(self, title, prompt):
    v, ok = QInputDialog.getText(self.parent, title, prompt)
    return v.strip() if ok and v.strip() else None

  def ask_text(self, title, prompt, default=""):
    v, ok = QInputDialog.getText(self.parent, title, prompt,
                                 QLineEdit.Normal, default)
    return v.strip() if ok and v.strip() else None
  def ask_int(self,title,prompt):
    v,ok = QInputDialog.getInt(self.parent,title,prompt)
    return v if ok else None

  # ---- single choice from a list --------------------------------------
  def ask_choice(self, title, prompt, options):
    """options: list of (label, value) pairs. Returns the chosen value, or
    None if cancelled. The combo box is editable so typing filters it."""
    dlg = QDialog(self.parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(prompt))
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    for label, _value in options:
      combo.addItem(label)
    lay.addWidget(combo)
    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    if dlg.exec() != QDialog.Accepted:
      return None
    idx = combo.currentIndex()
    if idx < 0 or idx >= len(options):
      return None
    return options[idx][1]
  # ---- file pickers ---------------------------------------------------
  def pick_file(self, title, flt="All files (*)"):
    return QFileDialog.getOpenFileName(self.parent, title, "", flt)[0] or None

  def pick_dir(self, title, start=""):
    return QFileDialog.getExistingDirectory(self.parent, title, start) or None

  def pick_save(self, title, default):
    return QFileDialog.getSaveFileName(self.parent, title, default)[0] or None

  # ---- MTK scatter checklist -----------------------------------------
  def scatter_dialog(self, parts, base):
    """Checklist of scatter partitions. Returns the ticked ones or None."""
    dlg = QDialog(self.parent)
    dlg.setWindowTitle("Flash from scatter file")
    dlg.resize(560, 560)
    lay = QVBoxLayout(dlg)
    lay.addWidget(label(
        "Tick the partitions to flash. Unticked by default: bootloader, "
        "IMEI/calibration and user-data partitions. Missing files are "
        "disabled.", "muted", wrap=True))
    lw = QListWidget()
    items = []
    for p in parts:
      found = os.path.isfile(os.path.join(base, p["file"]))
      it = QListWidgetItem(f"{p['name']}   ({p['file']})"
                           + ("" if found else "   [file missing]"))
      if found:
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        on = p["dl"] and p["name"].lower() not in SCATTER_SKIP
        it.setCheckState(Qt.Checked if on else Qt.Unchecked)
      else:
        it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
      lw.addItem(it)
      items.append((it, p, found))
    lay.addWidget(lw, 1)

    def setall(state):
      for it, _p, found in items:
        if found:
          it.setCheckState(state)

    row = QHBoxLayout()
    row.addWidget(button("All", lambda: setall(Qt.Checked)))
    row.addWidget(button("None", lambda: setall(Qt.Unchecked)))
    row.addStretch(1)
    row.addWidget(button("Cancel", dlg.reject, width=110))
    row.addWidget(button("Continue", dlg.accept, accent=True, width=110))
    lay.addLayout(row)
    if dlg.exec() != QDialog.Accepted:
      return None
    return [p for it, p, found in items
            if found and it.checkState() == Qt.Checked]

  # ---- searchable package checklist (ADB package manager) -------------
  def package_dialog(self, title, packages, note=""):
    """Searchable checklist of package names. Returns the ticked ones, or
    None if cancelled. Ticks survive typing in the filter box - filtering
    only changes what's shown, not what's selected."""
    dlg = QDialog(self.parent)
    dlg.setWindowTitle(title)
    dlg.resize(560, 580)
    lay = QVBoxLayout(dlg)
    if note:
      lay.addWidget(label(note, "muted", wrap=True))
    search = QLineEdit()
    search.setPlaceholderText(f"Filter ({len(packages)} packages)")
    lay.addWidget(search)
    lw = QListWidget()
    lay.addWidget(lw, 1)
    count = label("0 selected", "muted")
    lay.addWidget(count)
    selected = set()

    def on_changed(item):
      name = item.data(Qt.UserRole)
      if item.checkState() == Qt.Checked:
        selected.add(name)
      else:
        selected.discard(name)
      count.setText(f"{len(selected)} selected")

    lw.itemChanged.connect(on_changed)

    def populate(filter_text=""):
      lw.blockSignals(True)
      lw.clear()
      ft = filter_text.lower()
      for name in packages:
        if ft and ft not in name.lower():
          continue
        it = QListWidgetItem(name)
        it.setData(Qt.UserRole, name)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if name in selected else Qt.Unchecked)
        lw.addItem(it)
      lw.blockSignals(False)

    search.textChanged.connect(populate)
    populate()

    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(button("Cancel", dlg.reject, width=110))
    row.addWidget(button("Continue", dlg.accept, accent=True, width=110))
    lay.addLayout(row)
    if dlg.exec() != QDialog.Accepted:
      return None
    return sorted(selected)
