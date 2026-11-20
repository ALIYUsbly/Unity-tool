"""The two building blocks of every tab: Action (a button) and Section
(a titled group of buttons that all run the same tool).

A *builder* is a function `build(ui) -> list of commands | None`.
  - ui is the helper with dialogs/pickers (ask_name, pick_file, pick_dir ...)
  - each command is a list of arguments for the tool, e.g. ["r", "boot", "out.bin"]
  - return None to cancel (user closed a dialog)
"""
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Action:
  label: str
  build: Callable          # build(ui) -> [[args...], ...] or None
  risk: str = "safe"       # "safe" | "write" | "danger"
  report: bool = False     # True = save the tool output to backups/reports/


@dataclass
class Section:
  title: str
  script: str              # "edl.py", "mtk.py", "adb", "heimdall" ...
  actions: List[Action]


def fixed(*args):
  """Builder for a button that always runs one command: fixed("printgpt")."""
  return lambda ui: [list(args)]


def batch(*commands):
  """Builder for a button that runs several fixed commands one after another:
  batch(["e", "userdata"], ["e", "cache"])."""
  return lambda ui: [list(c) for c in commands]
