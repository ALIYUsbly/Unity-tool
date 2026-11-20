"""MediaTek META tab - diagnostic reads and offline backup inspection.

The first rollout deliberately exposes no META write action. Captured A3
parameter-2 traffic is write-like, but its complete semantics have not been
independently established against a real para backup yet.
"""
from Unity.config import META_SNAPSHOT_PROPS,PROFILES_DIR
from Unity.core.actions import Action, Section, fixed
from Unity.tabs.base import Tab
from Unity.core.profiles import _find_profile_by_model,_load_profile_offsets,load_profiles
import json, os
import sys
# ----------------------------------------------------------- builders ----
#since these is MTK only script let point the mtk rofiles only
PROFILES_DIR =PROFILES_DIR+"/mtk"




def meta_frp_clear_dry(ui):
    """Dry-run: print the offsets, don't write."""
    profiles, errors = load_profiles(PROFILES_DIR)
    if not profiles:
        ui.log("No device profiles found under " + PROFILES_DIR)
        return None

    options = [
        (f"{p['model']}  ({p['brand']})", p["id"])
        for p in profiles
    ]
    profile_id = ui.ask_choice(
        "FRP clear dry-run", "Select device model:", options)
    if not profile_id:
        return None

    frp_lba, para_lba,board = _load_profile_offsets(PROFILES_DIR,profile_id) if profile_id else (None, None)
    args = ["frp-clear"]
    if frp_lba is not None and para_lba is not None:
        args += [f"--frp-seek={frp_lba}", f"--para-seek={para_lba}",f"--board={board}"]
    return [args]

def meta_frp_clear_run(ui):
    profiles, errors = load_profiles(PROFILES_DIR)
    if not profiles:
        ui.log("No device profiles found under " + PROFILES_DIR)
        return None

    options = [
        (f"{p['model']}  ({p['brand']})", p["id"])
        for p in profiles
    ]
    profile_id = ui.ask_choice(
        "FRP clear", "Select device model:", options)
    if not profile_id:
        return None

    frp_lba, para_lba,board = _load_profile_offsets(PROFILES_DIR,profile_id) if profile_id else (None, None)
    if frp_lba is None or para_lba is None:
        frp_lba = ui.ask_int(
            "FRP LBA",
            "Enter frp start LBA (from AndroidUtility log, WIPE (frp)[...LBA:0x...] → decimal):")
        para_lba = ui.ask_int(
            "PARA LBA",
            "Enter para start LBA (from AndroidUtility log, WIPE (para)[...LBA:0x...] → decimal):")
        if frp_lba is None or para_lba is None:
            return None
        
    return [[
        "frp-clear",
        f"--frp-seek={frp_lba}",
        f"--para-seek={para_lba}",
        f"--board={board}",
        "--yes",
    ]]



def meta_getprop(ui):
  name = ui.ask_text(
      "Get property", "Property name:", "ro.product.model")
  if not name:
    return None
  return [["getprop", name]]


def meta_snapshot(ui):
  """DEVICE INFO plus the build properties listed in config.META_SNAPSHOT_PROPS,
  all saved to one report."""
  return [["info"]] + [["getprop", p] for p in META_SNAPSHOT_PROPS]


def meta_read_file(ui):
  path = ui.ask_text(
      "Read device file",
      "Device path (e.g. /dev/block/by-name/frp):")
  if not path:
    return None
  out = ui.pick_save("Save as", "readfile.bin")
  return [["read-file", path, out]] if out else None


def meta_read_para(ui):
  """Read the para alias used by the supplied factory-reset capture."""
  path = ui.ask_text(
      "Read para partition (META)",
      "Device path (capture path; no leading slash):",
      "dev/block/by-name/para")
  if not path:
    return None
  out = ui.pick_save("Save para backup as", "para_meta_backup.bin")
  return [["read-file", path, out]] if out else None


def meta_read_para_platform(ui):
  path = "dev/block/platform/bootdevice/by-name/para"
  out = ui.pick_save("Save para backup as", "para_platform_meta_backup.bin")
  return [["read-file", path, out]] if out else None


def meta_read_misc(ui):
  path = ui.ask_text(
      "Read misc partition (META)",
      "Device path (capture path; no leading slash):",
      "dev/block/by-name/misc")
  if not path:
    return None
  out = ui.pick_save("Save misc backup as", "misc_meta_backup.bin")
  return [["read-file", path, out]] if out else None


def meta_inspect_backup(ui):
  path = ui.pick_file("Select a saved META partition backup",
                      "Binary backup (*.bin);;All Files (*)")
  return [["inspect-backup", path]] if path else None


# --------------------------------------------------------------- tab -----
class MediatekMetaTab(Tab):
  title = "MEDIATEK META (READ-ONLY)"
  platform = "mtk"
  config_title = "META MODE"

  sections = [
      Section("READ / DIAGNOSTICS (META MODE)", "meta.py", [
          Action("SNAPSHOT (INFO + BUILD)", meta_snapshot, report=True),
          Action("DEVICE INFO", fixed("info"), report=True),
          Action("GET PROPERTY...", meta_getprop),
          Action("READ FILE...", meta_read_file),
          Action("READ PARA (CAPTURE PATH)...", meta_read_para, report=True),
          Action("READ PARA (PLATFORM PATH)...", meta_read_para_platform,
                 report=True),
          Action("READ MISC (COMPARISON)...", meta_read_misc, report=True),
          Action("INSPECT SAVED PARTITION BACKUP...", meta_inspect_backup,
                 report=True),
          Action("PROTOCOL CAPABILITIES", fixed("capabilities"), report=True),
          Action("LIST / WATCH PORTS", fixed("list-ports")),
          Action("REBOOT DEVICE", fixed("reboot")),
      ]),
      Section("FRP / SECURITY (DESTRUCTIVE)", "meta.py", [
          Action("FRP CLEAR (DRY-RUN)...", meta_frp_clear_dry),
          Action("FRP CLEAR (EXECUTE)...", meta_frp_clear_run,"danger"),
          Action("SAFE-FORMAT(RECOVERY WIPE)",fixed("factory-reset-mode01"),"danger"),
          Action("FORMAT-USERDATA",fixed("factory-reset-dd"),"danger"),
         
      ]),
  ]


  def options(self, form):
    form.check("verbose", "Verbose (-v)")
    form.entry("timeout", "Wait timeout (seconds)")
    form.note("For device reads: power the phone OFF, press an action, "
              "then connect it. The tool waits for Preloader and enters "
              "META mode. Read para first and inspect the saved backup. "
              "META writes are intentionally not enabled in this test build.")

  def pre_args(self, script, args, opts):
    if not args or args[0] in ("list-ports", "capabilities", "inspect-backup"):
      pre = []
    else:
      pre = ["--wait"]
      if opts.get("timeout"):
        pre.append(f"--wait-timeout={opts['timeout']}")
    if opts.get("verbose"):
      pre.append("-v")
    return pre
