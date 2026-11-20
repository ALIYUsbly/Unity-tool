"""QUALCOMM (EDL) tab - tool: edl.py"""
import glob
import os
import re

from Unity.config import QCOM_EFS
from Unity.core import bootloader_message as BLM
from Unity.core import builders as B
from Unity.core.actions import Action, Section, fixed
from Unity.core.profile_capture import ProfileField
from Unity.tabs.base import Tab

# Which shared options each edl.py command accepts (from `edl.py -h`).
# docopt rejects options a command does not list, so only add valid ones.
EDL_SECTORSIZE_CMDS = {"printgpt", "r", "rl", "rf", "rs", "w", "wl", "wf",
                       "ws", "e", "es", "ep"}
EDL_MEMORY_CMDS = {"printgpt", "gpt", "r", "rl", "rf", "rs", "w", "wl", "wf",
                   "ws", "e", "es", "ep", "footer", "getstorageinfo", "qfil"}
EDL_SKIPWRITE_CMDS = {"w", "ws", "e", "es", "ep"}

MISC_MESSAGE_PATCHED_NAME = "misc_wipe_data.bin"


# ----------------------------------------------------------- builders ----
def backup_efs(ui):
  return B.read_partitions_to_folder(ui, "Folder to store the EFS backup",
                                     QCOM_EFS)


def restore_efs(ui):
  return B.write_partitions_from_folder(
      ui, "Folder containing the EFS backup (modemst1.bin etc.)", QCOM_EFS)


def backup_misc(ui):
  out = ui.pick_save("Save MISC partition backup as", "misc_backup.bin")
  return [["r", "misc", out]] if out else None


def safe_format(ui):
  """Recovery-triggered factory reset: patch a MISC backup with the
  bootloader's wipe-data message, write it back, reboot. Needs a backup
  made with BACKUP MISC PARTITION first - the write only replaces the
  first 1088 bytes of that file, so anything a device keeps after that
  (e.g. A/B slot-control data) is carried through unchanged instead of
  being guessed at or zeroed."""
  backup = ui.pick_file(
      "MISC partition backup (made with BACKUP MISC PARTITION)",
      "Backup (*.bin);;All Files (*)")
  if not backup:
    return None
  out_path = os.path.join(os.path.dirname(backup), MISC_MESSAGE_PATCHED_NAME)
  try:
    size = BLM.patch_misc_backup(backup, out_path)
  except ValueError as e:
    ui.dialog("Safe Format", str(e))
    return None
  ui.log(f"wrote {out_path} ({size} bytes) - only the first "
         f"{BLM.MESSAGE_SIZE} bytes changed from the backup")
  return [["w", "misc", out_path], ["reset"]]


def flash_modem(ui):
  f = ui.pick_file("Baseband/modem firmware image (e.g. NON-HLOS.bin)")
  return [["w", "modem", f]] if f else None


def read_all_xml(ui):
  d = ui.pick_dir("Folder for backup + rawprogram XML (userdata skipped)")
  return [["rl", d, "--skip=userdata", "--genxml"]] if d else None


def qfil_flash(ui):
  xml = "XML (*.xml);;All files (*)"
  raw = ui.pick_file("Select rawprogram XML (e.g. rawprogram0.xml)", xml)
  if not raw:
    return None
  img_dir = os.path.dirname(raw)
  # Multi-LUN (UFS) firmware ships rawprogram0..N.xml / patch0..N.xml. Flashing
  # only the picked file would leave other LUNs old, so pass a pattern.
  raw_arg = raw
  m = re.match(r"^(.*?)\d+(\.xml)$", os.path.basename(raw))
  if m:
    sib = re.compile(rf"^{re.escape(m.group(1))}\d+{re.escape(m.group(2))}$")
    raws = sorted(f for f in os.listdir(img_dir) if sib.match(f))
    if len(raws) > 1:
      broad = sorted(os.path.basename(p) for p in glob.glob(
          os.path.join(img_dir, f"{m.group(1)}*{m.group(2)}")))
      mid = "*" if broad == raws else "[0-9]*"
      raw_arg = os.path.join(img_dir, f"{m.group(1)}{mid}{m.group(2)}")
      ui.log(f"FOUND {len(raws)} rawprogram files: {', '.join(raws)}")
  patches = sorted(glob.glob(os.path.join(img_dir, "patch*.xml")))
  if len(patches) > 1:
    patch_arg = os.path.join(img_dir, "patch*.xml")
    ui.log(f"FOUND {len(patches)} patch files")
  elif patches:
    patch_arg = patches[0]
  else:
    patch_arg = ui.pick_file("Select patch XML (e.g. patch0.xml)", xml)
    if not patch_arg:
      return None
  return [["qfil", raw_arg, patch_arg, img_dir]]


# --------------------------------------------------------------- tab -----
class QualcommTab(Tab):
  title = "QUALCOMM (EDL)"
  platform = "qualcomm"
  config_title = "QUALCOMM CONFIGURATION"

  # ADD BUTTONS HERE: one Action(...) per button
  sections = [
      Section("READ / BACKUP", "edl.py", [
          Action("READ DEVICE INFO (GPT)", fixed("printgpt")),
          Action("GET STORAGE INFO", fixed("getstorageinfo")),
          Action("READ PARTITION...", B.read_partition),
          Action("BACKUP EFS (MODEM/FSG)", backup_efs),
          Action("BACKUP ALL PARTITIONS...", B.read_all),
          Action("BACKUP (SKIP USERDATA)...", B.read_all_skip),
          Action("BACKUP + XML (NO USERDATA)...", read_all_xml),
          Action("BACKUP MISC PARTITION...", backup_misc),
          Action("REBOOT TO NORMAL", fixed("reset")),
      ]),
      Section("FLASH / WRITE", "edl.py", [
          Action("WRITE PARTITION...", B.write_partition, "write"),
          Action("FLASH FOLDER (wl)...", B.write_folder, "write"),
          Action("FLASH FIRMWARE (XML)...", qfil_flash, "write"),
          Action("FLASH MODEM/BASEBAND ONLY...", flash_modem, "write"),
          Action("RESTORE EFS (MODEM/FSG)...", restore_efs, "write"),
      ]),
      Section("ERASE / RESET", "edl.py", [
          Action("ERASE PARTITION...", B.erase_partition, "danger"),
          Action("RESET FRP", fixed("e", "frp"), "danger"),
          Action("WIPE USERDATA", fixed("e", "userdata"), "danger"),
          Action("SAFE FORMAT (RECOVERY WIPE)...", safe_format, "danger"),
      ]),
  ]

  def options(self, form):
    form.file("loader", "Loader (.elf/.mbn)", "Select Firehose Loader",
              "ELF / MBN Loaders (*.elf *.mbn);;All Files (*)")
    form.radio("sector", "Sector size",
               [("Auto", ""), ("4096 (UFS)", "4096"), ("512 (eMMC)", "512")])
    form.radio("memory", "Memory type",
               [("Auto", ""), ("UFS", "UFS"), ("eMMC", "eMMC"),
                ("NAND", "NAND")])
    form.check("skipwrite",
               "Simulate only, no writes (--skipwrite; single write/erase)")

  def check_options(self, ui):
    return not self.file_missing(ui, "loader", "Loader")

  def before_run(self, ui, script, opts):
    if opts["skipwrite"]:
      ui.log("SIMULATION: --skipwrite added to write/erase commands")

  def extra_flags(self, script, args, opts):
    flags = []
    if not args:
      return flags
    cmd = args[0]
    if opts["loader"]:
      flags.append(f"--loader={opts['loader']}")
    if opts["sector"] and cmd in EDL_SECTORSIZE_CMDS:
      flags.append(f"--sectorsize={opts['sector']}")
    if opts["memory"] and cmd in EDL_MEMORY_CMDS:
      flags.append(f"--memory={opts['memory']}")
    if opts["skipwrite"] and cmd in EDL_SKIPWRITE_CMDS:
      flags.append("--skipwrite")
    return flags

  def risk_note(self, cmds):
    if any(len(c) >= 2 and c[0] == "w" and c[1] == "misc" for c in cmds):
      return (
          "SAFE FORMAT writes a recovery wipe-data command into the MISC "
          "partition, using the backup you made with BACKUP MISC "
          "PARTITION - only the first 1088 bytes of that backup are "
          "changed, so anything a device stores after that (e.g. A/B "
          "slot-control data) is carried through unchanged. The device "
          "will reboot into recovery, run a normal data wipe (the same "
          "thing 'Wipe data/factory reset' does from the recovery menu), "
          "then reboot to system on its own.\n\n")
    return ""

  def apply_profile(self, ui, p):
    applied = []
    # sector size / memory fall back to Auto when the profile has none
    self.v["sector"].set(str(p["sector_size"]) if p.get("sector_size") else "")
    self.v["memory"].set(p.get("memory") or "")
    self.apply_path(ui, p, "loader", "loader", "loader", applied)
    return applied

  def profile_fields(self):
    # "skipwrite" is a session toggle (simulate-only), never saved - same
    # as apply_profile() above never restoring it.
    return {
        "loader": ProfileField("loader", "file"),
        "sector": ProfileField("sector_size", "value"),
        "memory": ProfileField("memory", "value"),
    }
