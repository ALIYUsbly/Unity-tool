"""Backup checks (no GUI code, so it is easy to test).

Two jobs:
  * after a read finishes, confirm the output file really exists and is not
    empty / left as '<name>.partial' by an interrupted read;
  * before a write or erase, tell the user what the backup folder looks like.
"""
import os
import time

from Unity.config import BACKUP_DIR, READ_CMDS_WITH_FILE

PARTIAL_SUFFIX = ".partial"


def backup_start_dir(path=None):
  """Backup folder (created if needed) used as the starting point of pickers."""
  path = path or BACKUP_DIR
  try:
    os.makedirs(path, exist_ok=True)
  except OSError:
    return ""
  return path


def new_snapshot_dir(root=None, now=None):
  """Create and return <root>/snapshot-<timestamp>, or None if it can't be made."""
  root = root or BACKUP_DIR
  stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
  path = os.path.join(root, f"snapshot-{stamp}")
  try:
    os.makedirs(path, exist_ok=True)
  except OSError:
    return None
  return path


def read_outputs(script, cmds):
  """Files that the read commands in `cmds` are going to produce."""
  out = []
  for c in cmds:
    if len(c) >= 3 and c[0] in READ_CMDS_WITH_FILE:
      out += c[2].split(",") if script == "mtk.py" else [c[2]]
  return out


def check_outputs(paths):
  """Return a list of 'path: problem' strings; empty list = all good."""
  problems = []
  for p in paths:
    if os.path.isfile(p):
      if os.path.getsize(p) == 0:
        problems.append(f"{p}: file is empty")
    elif os.path.isfile(p + PARTIAL_SUFFIX):
      problems.append(f"{p}: only an incomplete '{os.path.basename(p)}"
                      f"{PARTIAL_SUFFIX}' exists")
    else:
      problems.append(f"{p}: file was not created")
  return problems


def scan_backup_dir(root):
  """(good_files, problems) for every file under `root`.

  A file is a problem when it is empty or still named '*.partial'."""
  good, problems = [], []
  for dirpath, dirs, files in os.walk(root):
    if dirpath == root and "reports" in dirs:
      dirs.remove("reports")      # text reports are not partition backups
    for name in sorted(files):
      path = os.path.join(dirpath, name)
      rel = os.path.relpath(path, root)
      try:
        size = os.path.getsize(path)
      except OSError:
        problems.append(f"{rel}: unreadable")
        continue
      if name.endswith(PARTIAL_SUFFIX) or size == 0:
        why = "incomplete" if name.endswith(PARTIAL_SUFFIX) else "empty"
        problems.append(f"{rel}: {why}")
      else:
        good.append(rel)
  return good, problems


def backup_status_text(root=None, max_problems=5):
  """Short paragraph for the write/erase warning (ends with a blank line)."""
  root = root or BACKUP_DIR
  if not os.path.isdir(root):
    return (f"Backup folder check: {root} does not exist yet, so no backup "
            "has been made there (backups saved elsewhere are not "
            "checked).\n\n")
  good, problems = scan_backup_dir(root)
  text = f"Backup folder check ({root}): {len(good)} usable file(s)"
  if not good:
    text += " - NOTHING backed up there yet"
  if problems:
    shown = "\n    ".join(problems[:max_problems])
    more = (f"\n    ... (+{len(problems) - max_problems} more)"
            if len(problems) > max_problems else "")
    text += f"\n  INCOMPLETE / EMPTY files:\n    {shown}{more}"
  return text + "\n(Backups saved in other folders are not checked.)\n\n"
