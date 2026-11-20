"""Classifies a partition dump into reusable/ (generic firmware - safe to
keep in a firmware archive and flash to another unit of the SAME model and
build) and identity/ (unique to this physical phone - never copy to another
device, re-flash only onto the same unit it came from). No GUI code here,
so it's easy to test.

Two callers:
  * MainWindow, automatically, right after a BACKUP (SKIP USERDATA) run
    succeeds (see Action.auto_sort in core/actions.py and
    MainWindow._run_auto_sort) - uses move=True since source and
    destination are in the same backup folder on the same filesystem, so
    the "move" is really just a rename: instant, no UI freeze, no doubled
    disk usage, even for a multi-gigabyte full backup.
  * By hand, for a dump made some other way:
        from Unity.core.sort_dump import sort_dump
        sort_dump("/path/to/backup/folder")
"""
import datetime
import shutil
from pathlib import Path

# Generic firmware: identical across every unit of this exact model/build.
# Safe to keep in a reusable firmware archive.
REUSABLE = {
    "boot", "system", "vendor", "recovery", "erecovery", "cust", "logo",
    "lk", "lk2", "loader_ext1", "loader_ext2", "md1img", "md1dsp",
    "spmfw", "mcupmfw", "tee1", "tee2", "odmdtbo", "gz1", "gz2",
    "cache", "log", "expdb", "reserve0", "reserve1", "rrecord",
    "bootfail_info", "misc",
}

# Unique to the physical device: IMEI/MAC calibration, serials, lock state,
# this unit's own flash layout. Never copy to another device.
IDENTITY = {
    "nvram", "nvdata", "nvcfg", "nff", "proinfo", "protect1", "protect2",
    "oeminfo", "hwparam", "frp", "seccfg", "gpt", "gpt_backup",
    "para", "sec1", "flashinfo", "boot_para", "bfr", "metadata",
}

REASONS = {
    "nvram": "RF/IMEI calibration", "nvdata": "RF/IMEI calibration",
    "nvcfg": "RF/IMEI calibration", "nff": "RF/IMEI calibration",
    "proinfo": "IMEI1/IMEI2, Wi-Fi/BT MAC",
    "protect1": "IMEI1/IMEI2, Wi-Fi/BT MAC",
    "protect2": "IMEI1/IMEI2, Wi-Fi/BT MAC",
    "oeminfo": "per-unit serial/board identity",
    "hwparam": "per-unit serial/board identity",
    "frp": "factory-reset/account-lock state",
    "seccfg": "security/unlock state tied to this device",
    "gpt": "this unit's own flash layout",
    "gpt_backup": "this unit's own flash layout",
    "para": "uncertain - treated as device-specific",
    "sec1": "uncertain - treated as device-specific",
    "flashinfo": "uncertain - treated as device-specific",
    "boot_para": "uncertain - treated as device-specific",
    "bfr": "uncertain - treated as device-specific",
    "metadata": "uncertain - treated as device-specific",
}


def classify(stem):
  if stem in REUSABLE:
    return "reusable", ""
  if stem in IDENTITY:
    return "identity", REASONS.get(stem, "device-specific")
  return "unclassified", ""


def sort_dump(folder, move=True, tag=""):
  """Sort every .bin/.img/.json file directly inside `folder` into
  reusable/ and identity/ subfolders, and write a MANIFEST.txt explaining
  the split. Returns {"reusable": n, "identity": n, "unclassified": [names]}.

  move=True (the default) renames files instead of copying them - fine and
  fast here since source and destination both live inside `folder`, on the
  same filesystem. Pass move=False to keep the originals in place too (the
  standalone CLI script defaults to this for a manual, one-off archive
  pass where you may want both).
  """
  folder = Path(folder)
  files = sorted(p for p in folder.iterdir()
                if p.is_file() and p.suffix in (".bin", ".img", ".json"))
  if not files:
    return {"reusable": 0, "identity": 0, "unclassified": []}

  reusable_dir = folder / "reusable"
  identity_dir = folder / "identity"
  reusable_dir.mkdir(exist_ok=True)
  identity_dir.mkdir(exist_ok=True)

  manifest = {"reusable": [], "identity": [], "unclassified": []}
  op = shutil.move if move else shutil.copy2

  for p in files:
    kind, reason = classify(p.stem.lower())
    if kind == "reusable":
      op(str(p), str(reusable_dir / p.name))
      manifest["reusable"].append(p.name)
    elif kind == "identity":
      op(str(p), str(identity_dir / p.name))
      manifest["identity"].append((p.name, reason))
    else:
      manifest["unclassified"].append(p.name)

  lines = [
      f"Dump sorted {datetime.datetime.now().isoformat(timespec='seconds')}",
      f"Source: {folder}", f"Tag: {tag or '(none given)'}",
      f"Mode: {'moved' if move else 'copied'}", "",
      f"REUSABLE ({len(manifest['reusable'])}) - generic firmware, safe to "
      f"flash to another unit of the SAME model + build:",
  ]
  lines += [f"  {n}" for n in manifest["reusable"]]
  lines += ["", f"IDENTITY ({len(manifest['identity'])}) - unique to THIS "
           f"physical phone, never copy to another device:"]
  lines += [f"  {n:<20} {why}" for n, why in manifest["identity"]]
  if manifest["unclassified"]:
    lines += ["", f"UNCLASSIFIED ({len(manifest['unclassified'])}) - left "
             f"in place, not sorted, check these by hand:"]
    lines += [f"  {n}" for n in manifest["unclassified"]]

  (folder / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
  return {
      "reusable": len(manifest["reusable"]),
      "identity": len(manifest["identity"]),
      "unclassified": manifest["unclassified"],
  }
