"""Builders shared by several tabs (the edl.py and mtk.py command names match).

Use them in a tab like:  Action("READ PARTITION...", B.read_partition)
"""
import os

from Unity.core.backups import backup_start_dir


def read_partition(ui):
  part = ui.ask_name("Read partition", "Partition name (e.g. boot, fsg):")
  if not part:
    return None
  out = ui.pick_save("Save partition as", f"{part}.bin")
  return [["r", part, out]] if out else None


def write_partition(ui):
  part = ui.ask_name("Write partition", "Partition name (e.g. boot):")
  if not part:
    return None
  src = ui.pick_file(f"Image to write to '{part}'")
  return [["w", part, src]] if src else None


def erase_partition(ui):
  part = ui.ask_name("Erase partition", "Partition name to erase:")
  return [["e", part]] if part else None


def read_all(ui):
  d = ui.pick_dir("Folder to save all partitions into", backup_start_dir())
  return [["rl", d]] if d else None


def read_all_skip(ui):
  d = ui.pick_dir("Folder to save backup into (userdata is skipped)",
              backup_start_dir())
  return [["rl", d, "--skip=userdata"]] if d else None


def write_folder(ui):
  d = ui.pick_dir("Folder containing partition images (named by partition)")
  return [["wl", d]] if d else None


def read_partitions_to_folder(ui, folder_title, partitions):
  """Backup several named partitions into one folder (one `r` per partition)."""
  d = ui.pick_dir(folder_title, backup_start_dir())
  if not d:
    return None
  return [["r", p, os.path.join(d, f"{p}.bin")] for p in partitions]


def write_partitions_from_folder(ui, folder_title, partitions):
  """Restore several named partitions from one folder (one `w` per partition).
  The reverse of read_partitions_to_folder: looks for <folder>/<name>.bin for
  each partition and skips (with a log line) any that are missing, instead of
  failing the whole restore."""
  d = ui.pick_dir(folder_title)
  if not d:
    return None
  cmds, missing = [], []
  for p in partitions:
    f = os.path.join(d, f"{p}.bin")
    if os.path.isfile(f):
      cmds.append(["w", p, f])
    else:
      missing.append(p)
  if missing:
    ui.log(f"SKIPPED (file not found in folder): {', '.join(missing)}")
  if not cmds:
    ui.dialog("Restore", "None of the expected backup files were found in "
              "that folder.")
    return None
  return cmds
