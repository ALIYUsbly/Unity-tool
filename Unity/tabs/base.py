"""Base class for a tab. Subclass it, fill in `sections`, and override only the
hooks you need."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from Unity.core.tools import resolve_profile_path
from Unity.ui.widgets import Form, action_grid, button, card


class Tab:
  title = "TAB"            # text on the tab
  platform = None          # matches "platform" in device profiles (or None)
  config_title = None      # title of the options card; None = no options card
  sections = []            # list of Section(...) = the buttons

  def __init__(self):
    self.v = {}            # option key -> W (get/set), filled by options()
    self.ui = None
    self.run = None

  # ---- building the page ---------------------------------------------
  def build(self, ui, run, save_as_profile=None, can_run=None):
    self.ui, self.run = ui, run
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setAlignment(Qt.AlignTop)
    sa.setWidget(inner)
    if self.config_title:
      form = Form(card(lay, self.config_title), self.v, ui)
      self.options(form)
      # Only a tab whose options are worth remembering per-device (it has
      # at least one field listed in profile_fields()) gets this button.
      if save_as_profile and self.profile_fields():
        r = form._next()
        form.grid.addWidget(
            button("SAVE CURRENT SETTINGS AS A NEW PROFILE...",
                   lambda: save_as_profile(self), accent=True),
            r, 0, 1, 4)
    for sec in self.sections:
      action_grid(
          lay, sec, lambda s, a: self.run(self, s, a),
          can_run=(lambda action, section=sec: can_run(self, section, action))
          if can_run else None,
      )
    return sa

  def options(self, form):
    """Add option rows: form.file / entry / radio / combo / check / note."""

  def values(self):
    """Current option values as a dict (strings are stripped)."""
    out = {}
    for k, w in self.v.items():
      val = w.get()
      out[k] = val.strip() if isinstance(val, str) else val
    return out

  # ---- hooks (all optional) -------------------------------------------
  def check_options(self, ui):
    """Validate the options BEFORE the button asks anything. False = stop."""
    return True

  def check_cmds(self, ui, cmds):
    """Validate the built commands. False = stop."""
    return True

  def pre_args(self, script, args, opts):
    """Arguments placed BEFORE the command (e.g. adb -s <serial>)."""
    return []

  def extra_flags(self, script, args, opts):
    """Flags appended AFTER the command (e.g. --loader=...)."""
    return []

  def risk_note(self, cmds):
    """Extra paragraph for the write/erase warning (end with a blank line)."""
    return ""

  def before_run(self, ui, script, opts):
    """Called once right before the commands start."""

  def apply_profile(self, ui, p):
    """Fill options from a device profile; return a list of applied items."""
    return []

  def profile_fields(self):
    """{var_key: ProfileField(profile_key, kind)} for the options worth
    saving into a new device profile via SAVE AS PROFILE. A key missing
    here (e.g. a session toggle) is never saved. Mirrors apply_profile()
    in reverse - a "file" field uses the same path convention apply_path()
    loads back; see Unity.core.profile_capture.capture_tab_values()."""
    return {}

  # ---- helpers for tab authors ---------------------------------------
  def file_missing(self, ui, key, name):
    """True (and shows a dialog) when option `key` names a file that is not
    there. An empty option is fine."""
    p = self.v[key].get().strip()
    if p and not os.path.isfile(p):
      ui.dialog(name, f"{name} file not found:\n{p}")
      return True
    return False

  def apply_path(self, ui, p, key, var, lab, applied):
    """Set option `var` from profile field `key` when the file exists."""
    if p.get(key):
      path = resolve_profile_path(p[key])
      if path:
        self.v[var].set(path)
        applied.append(f"{lab} {os.path.basename(path)}")
      else:
        ui.log(f"PROFILE WARNING: {lab} not found: {p[key]}")
