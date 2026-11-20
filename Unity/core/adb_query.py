"""Synchronous adb package queries for the ADB tab's package-manager dialogs
(scan / uninstall / restore).

core/runner.py streams long-running flashing jobs asynchronously and reports
back through log lines - fine for a flash that takes minutes, wrong for this:
the UI needs the package list *right now* to build the checklist the user
picks from. These calls are short (`pm list packages`), so they just block
briefly and return a plain (names, error) pair instead of going through the
job queue.
"""
import subprocess

from Unity.core.tools import resolve_tool


def _adb(args, serial=None, timeout=15):
  exe, _cwd = resolve_tool("adb")
  exe = exe or "adb"
  argv = [exe] + (["-s", serial] if serial else []) + args
  try:
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                       check=False)
  except Exception as e:  # adb missing, device unplugged mid-call, etc.
    return "", str(e)
  return r.stdout, (r.stderr.strip() if r.returncode != 0 else "")


def _pkg_names(text):
  return sorted(line.split(":", 1)[1].strip() for line in text.splitlines()
               if line.startswith("package:"))


def list_packages(serial=None):
  """All packages currently installed for this user. Returns (names, err)."""
  out, err = _adb(["shell", "pm", "list", "packages"], serial)
  return (_pkg_names(out), "") if not err else ([], err)


def list_restorable(serial=None):
  """Packages uninstalled-for-this-user that CAN be restored: known to the
  system (`pm list packages -u` includes them) but missing from the normal
  installed list. Returns (names, err)."""
  installed, err = list_packages(serial)
  if err:
    return [], err
  out, err = _adb(["shell", "pm", "list", "packages", "-u"], serial)
  if err:
    return [], err
  return sorted(set(_pkg_names(out)) - set(installed)), ""
