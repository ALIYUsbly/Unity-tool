"""MEDIATEK (MTK) tab - tool: mtk.py"""
import os

from Unity.config import MTK_NV
from Unity.core.backups import backup_start_dir, new_snapshot_dir
from Unity.core import bootloader_message as BLM
from Unity.core import builders as B
from Unity.core.actions import Action, Section, batch, fixed
from Unity.core.profile_capture import ProfileField
from Unity.core.scatter import SCATTER_PARTTYPE, parse_scatter
from Unity.tabs.base import Tab

# mtk.py commands that accept --parttype (user / boot1 / rpmb / lu0 ...)
MTK_PARTTYPE_CMDS = {"r", "rl", "rf", "w", "wf", "wl", "e"}

BCB_MESSAGE_PATCHED_NAME = "bcb_wipe_data.bin"
# Most devices use "misc"; many OPPO/Vivo MTK boards use "para" instead -
# check the scatter file for whichever is present if unsure.
DEFAULT_BCB_PARTITION = "misc"


# ----------------------------------------------------------- builders ----
def backup_nv(ui):
  d = ui.pick_dir("Folder to store the NVRAM / IMEI backup",
                  backup_start_dir())
  if not d:
    return None
  # `r` accepts comma-separated partition and file lists (per `mtk.py r -h`)
  files = ",".join(os.path.join(d, f"{p}.bin") for p in MTK_NV)
  return [["r", ",".join(MTK_NV), files]]


def snapshot(ui):
  """Pre-operation snapshot in one click: back up the NVRAM / IMEI partitions
  into a new time-stamped folder, then read the partition table. Whatever
  the tool prints while connecting (chip, secure-boot flags, MEID ...) is
  saved in a report next to the backups."""
  d = new_snapshot_dir()
  if not d:
    ui.dialog("Snapshot", "Could not create the snapshot folder under the "
              "backup folder (check permissions / TSM_BACKUP_DIR).")
    return None
  ui.log(f"SNAPSHOT folder: {d}")
  files = ",".join(os.path.join(d, f"{p}.bin") for p in MTK_NV)
  return [["r", ",".join(MTK_NV), files], ["printgpt"]]


def restore_nv(ui):
  return B.write_partitions_from_folder(
      ui, "Folder containing the NVRAM / IMEI backup", MTK_NV)


def backup_bcb(ui):
  part = ui.ask_text(
      "BCB partition name",
      "Partition holding the bootloader message (usually 'misc'; "
      "OPPO/Vivo MTK devices often use 'para' - check the scatter "
      "file if unsure):", DEFAULT_BCB_PARTITION)
  if not part:
    return None
  out = ui.pick_save(f"Save '{part}' partition backup as",
                      f"{part}_backup.bin")
  return [["r", part, out]] if out else None


def safe_format(ui):
  """Recovery-triggered factory reset: patch a BCB partition backup
  (misc on most devices, para on many OPPO/Vivo MTK boards) with the
  bootloader's wipe-data message, write it back. Needs a backup made
  with BACKUP BCB PARTITION first - the write only replaces the first
  BLM.MESSAGE_SIZE bytes of that file, so anything a device keeps
  after that is carried through unchanged instead of being guessed at
  or zeroed.

  Does NOT auto-reboot: on some loader/firmware combinations the DA
  `reset` command hangs after the write (Main - Handling da commands
  ... never returns) even though the write itself already completed
  and was confirmed beforehand - the write is the part that matters,
  reset is just a convenience that isn't reliable enough to chain
  automatically. Power-cycle the device by hand once the write
  finishes; it'll boot into recovery and run the wipe on its own."""
  backup = ui.pick_file(
      "BCB partition backup (made with BACKUP BCB PARTITION)",
      "Backup (*.bin);;All Files (*)")
  if not backup:
    return None
  part = ui.ask_text(
      "BCB partition name",
      "Partition name this backup came from (must match for the "
      "write step):", DEFAULT_BCB_PARTITION)
  if not part:
    return None
  out_path = os.path.join(os.path.dirname(backup), BCB_MESSAGE_PATCHED_NAME)
  try:
    size = BLM.patch_misc_backup(backup, out_path)
  except ValueError as e:
    ui.dialog("Safe Format", str(e))
    return None
  ui.log(f"wrote {out_path} ({size} bytes) - only the first "
         f"{BLM.MESSAGE_SIZE} bytes changed from the backup")
  ui.log("Once the write below confirms done, power-cycle the device "
         "by hand (unplug / hold power) - it should boot into recovery "
         "and run the wipe. The 'reset' DA command is not sent "
         "automatically; it has hung on some loaders after a "
         "successful write.")
  return [["w", part, out_path]]


def flash_modem(ui):
  part = ui.ask_text(
      "Modem/baseband partition",
      "Partition name (newer chips: md1img, older: modem):", "md1img")
  if not part:
    return None
  f = ui.pick_file(f"Modem/baseband firmware image for '{part}'")
  return [["w", part, f]] if f else None


def read_full(ui):
  out = ui.pick_save("Save full flash dump as", "full_flash.bin")
  return [["rf", out]] if out else None


def write_full(ui):
  f = ui.pick_file("Full flash image (wf)")
  return [["wf", f]] if f else None


def scatter_flash(ui):
  sc = ui.pick_file("Select scatter file",
                    "Scatter (*scatter*.txt *.txt);;All files (*)")
  if not sc:
    return None
  try:
    parts = parse_scatter(sc)
  except OSError as e:
    ui.dialog("Scatter", f"Cannot read scatter file:\n{e}")
    return None
  if not parts:
    ui.dialog("Scatter", "No partitions found. Only the '- partition_index:' "
              "scatter format is supported.")
    return None
  base = os.path.dirname(sc)
  chosen = ui.scatter_dialog(parts, base)
  if not chosen:
    return None

  # Group partitions by --parttype (mtk.py takes one --parttype per
  # invocation, so each group becomes a single comma-joined `w` call).
  # Writing one partition at a time means one full BROM/DA handshake
  # PER PARTITION - on a flaky USB/controller that reconnect can fail
  # mid-batch (the "Waiting for PreLoader VCOM" loop). Batching into
  # one `w name1,name2 file1,file2` call per parttype group means the
  # whole group shares a single handshake instead.
  #
  # Sparse images are NOT converted here - core.safety.find_sparse_images /
  # start_sparse_conversion already does that centrally for every mtk.py
  # write command (async, on a background thread, with progress), right
  # in run_action before these cmds are turned into jobs. Converting here
  # too would just duplicate that work on the UI thread and freeze it.
  groups = {}  # parttype (or None) -> [(name, path), ...]
  for p in chosen:
    path = os.path.join(base, p["file"])
    pt = SCATTER_PARTTYPE.get(p["region"])
    groups.setdefault(pt, []).append((p["name"], path))

  cmds = []
  for pt, items in groups.items():
    names = ",".join(n for n, _ in items)
    paths = ",".join(f for _, f in items)
    c = ["w", names, paths]
    if pt:
      c.append(f"--parttype={pt}")
    cmds.append(c)
  return cmds


# --------------------------------------------------------------- tab -----
class MediatekTab(Tab):
  title = "MEDIATEK (MTK)"
  platform = "mtk"
  config_title = "MEDIATEK CONFIGURATION"

  sections = [
      Section("READ / BACKUP", "mtk.py", [
          Action("PRE-OP SNAPSHOT (NV BACKUP + INFO)", snapshot,
                 report=True),
          Action("READ PARTITION TABLE", fixed("printgpt"), report=True),
          Action("READ PARTITION...", B.read_partition),
          Action("BACKUP ALL PARTITIONS...", B.read_all),
          Action("BACKUP (SKIP USERDATA)...", B.read_all_skip),
          Action("READ FULL FLASH (rf)...", read_full),
          Action("BACKUP NVRAM / IMEI DATA...", backup_nv),
          Action("BACKUP BCB PARTITION...", backup_bcb),
          Action("REBOOT DEVICE", fixed("reset")),
      ]),
      Section("FLASH / WRITE", "mtk.py", [
          Action("WRITE PARTITION...", B.write_partition, "write"),
          Action("FLASH FULL IMAGE (wf)...", write_full, "write"),
          Action("FLASH FOLDER (wl)...", B.write_folder, "write"),
          Action("FLASH FROM SCATTER FILE...", scatter_flash, "write"),
          Action("FLASH MODEM/BASEBAND ONLY...", flash_modem, "write"),
          Action("RESTORE NVRAM / IMEI DATA...", restore_nv, "write"),
      ]),
      Section("ERASE / RESET", "mtk.py", [
          Action("ERASE PARTITION...", B.erase_partition, "danger"),
          Action("FRP BYPASS", fixed("e", "frp"), "danger"),
          # `e` documents a single partition, so erase them one at a time
          Action("FACTORY RESET", batch(["e", "userdata"], ["e", "cache"]),
                 "danger"),
          Action("BOOTLOADER UNLOCK", fixed("da", "seccfg", "unlock"),
                 "danger"),
          Action("SAFE FORMAT (RECOVERY WIPE)...", safe_format, "danger"),
      ]),
  ]

  def options(self, form):
    form.file("loader", "DA loader", "Select DA loader")
    form.file("preloader", "Preloader", "Select preloader",
              "Preloader (*.bin);;All Files (*)")
    form.combo("parttype", "Partition type",
               ["", "user", "boot1", "rpmb", "lu0"],
               hint="blank = tool default; applies to read/write/erase")

  def check_options(self, ui):
    return not (self.file_missing(ui, "loader", "DA loader")
                or self.file_missing(ui, "preloader", "Preloader"))

  def check_cmds(self, ui, cmds):
    """mtk.py reads/writes take comma-separated name and file lists, so a
    comma inside a file path silently splits it in two. Refuse instead."""
    bad = [c for c in cmds if len(c) >= 3 and c[0] in ("r", "w")
           and len(c[1].split(",")) != len(c[2].split(","))]
    if bad:
      ui.dialog("Comma in file path",
                "mtk.py treats a comma as a list separator, so a file or "
                "folder name containing ',' would be split into two paths "
                "and the wrong file could be read or written.\n\n"
                "Rename the file/folder (or move it) so its full path has "
                "no commas, then try again.")
      return False
    return True

  def extra_flags(self, script, args, opts):
    flags = []
    if not args:
      return flags
    if opts["loader"]:
      flags.append(f"--loader={opts['loader']}")
    if opts["preloader"]:
      flags.append(f"--preloader={opts['preloader']}")
    # scatter writes already carry their own --parttype
    if (opts["parttype"] and args[0] in MTK_PARTTYPE_CMDS
        and not any(a.startswith("--parttype") for a in args)):
      flags.append(f"--parttype={opts['parttype']}")
    return flags

  def risk_note(self, cmds):
    if any(len(c) >= 3 and c[0] == "w" and BCB_MESSAGE_PATCHED_NAME in c[2]
           for c in cmds):
      return (
          "SAFE FORMAT writes a recovery wipe-data command into the BCB "
          "partition (misc/para/equivalent), using the backup you made "
          "with BACKUP BCB PARTITION - only the first "
          f"{BLM.MESSAGE_SIZE} bytes of that backup are changed, so "
          "anything a device stores after that (e.g. vendor calibration "
          "data, A/B slot-control data) is carried through unchanged. "
          "This does NOT auto-reboot the device - once the write "
          "completes, power-cycle it by hand; it will boot into "
          "recovery and run a normal data wipe (the same thing 'Wipe "
          "data/factory reset' does from the recovery menu) on its "
          "own.\n\n")
    return ""

  def apply_profile(self, ui, p):
    applied = []
    self.v["parttype"].set(p.get("parttype") or "")
    self.apply_path(ui, p, "loader", "loader", "DA loader", applied)
    self.apply_path(ui, p, "preloader", "preloader", "preloader", applied)
    return applied

  def profile_fields(self):
    return {
        "loader": ProfileField("loader", "file"),
        "preloader": ProfileField("preloader", "file"),
        "parttype": ProfileField("parttype", "value"),
    }
