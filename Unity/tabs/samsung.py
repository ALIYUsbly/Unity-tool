"""SAMSUNG (ODIN) tab - tools: heimdall (vendor/Heimdall build), tar, lz4"""
import os

from Unity.core.actions import Action, Section, fixed
from Unity.tabs.base import Tab


# ----------------------------------------------------------- builders ----
def download_pit(ui):
  out = ui.pick_save("Save PIT as", "device.pit")
  return [["download-pit", "--output", out]] if out else None


def flash_partition(ui):
  part = ui.ask_name("Heimdall flash",
                     "Partition name exactly as in PIT (e.g. BOOT):")
  if not part:
    return None
  f = ui.pick_file(f"Image to flash to '{part}'")
  return [["flash", f"--{part}", f]] if f else None


def flash_recovery(ui):
  f = ui.pick_file("Recovery image", "Images (*.img *.bin);;All files (*)")
  return [["flash", "--RECOVERY", f]] if f else None


def extract_tar(ui):
  t = ui.pick_file("Odin .tar / .tar.md5 file",
                   "Odin tar (*.tar *.md5);;All files (*)")
  if not t:
    return None
  d = ui.pick_dir("Extract into folder")
  return [["-xvf", t, "-C", d]] if d else None


def decompress_lz4(ui):
  d = ui.pick_dir("Folder containing .lz4 files")
  if not d:
    return None
  files = sorted(f for f in os.listdir(d) if f.lower().endswith(".lz4"))
  if not files:
    ui.dialog("LZ4", "No .lz4 files found in that folder.")
    return None
  return [["-d", "-f", os.path.join(d, f), os.path.join(d, f[:-4])]
          for f in files]


# Odin/COMBINATION firmware filename -> Heimdall partition flag. Covers the
# images that typically ship inside a COMBINATION_* package; anything else
# is left for FLASH PARTITION... instead of guessed.
COMBINATION_PART_MAP = {
    "boot.img": "BOOT",
    "recovery.img": "RECOVERY",
    "cache.img": "CACHE",
    "hidden.img": "HIDDEN",
    "modem.bin": "MODEM",
    "non-hlos.bin": "MODEM",
    "sboot.bin": "BOOTLOADER",
}


def flash_combination_folder(ui):
  d = ui.pick_dir("Folder with extracted + decompressed COMBINATION images "
                  "(EXTRACT ODIN .TAR, then DECOMPRESS .LZ4 first)")
  if not d:
    return None
  files = sorted(f for f in os.listdir(d)
                 if os.path.isfile(os.path.join(d, f))
                 and not f.lower().endswith((".lz4", ".tar", ".md5")))
  if not files:
    ui.dialog("Flash combination firmware",
             "No flashable images found in that folder - extract the .tar "
             "and decompress the .lz4 files first.")
    return None

  cmds, unknown = [], []
  for f in files:
    part = COMBINATION_PART_MAP.get(f.lower())
    if part:
      cmds.append(["flash", f"--{part}", os.path.join(d, f)])
    else:
      unknown.append(f)

  if unknown:
    ui.log("FLASH COMBINATION: unrecognised file name(s), skipped - flash "
          "these individually with FLASH PARTITION if needed: "
          + ", ".join(unknown))
  if not cmds:
    ui.dialog("Flash combination firmware",
             "None of the files in that folder matched a known COMBINATION "
             "partition name. Flash them individually with FLASH "
             "PARTITION... instead (PRINT PIT shows the exact names your "
             "device expects).")
    return None
  return cmds


# --------------------------------------------------------------- tab -----
class SamsungTab(Tab):
  title = "SAMSUNG (ODIN)"
  platform = None
  config_title = "SAMSUNG (HEIMDALL) CONFIGURATION"

  sections = [
      Section("READ / INFO", "heimdall", [
          Action("DETECT DEVICE", fixed("detect")),
          Action("PRINT PIT (PARTITION NAMES)", fixed("print-pit")),
          Action("DOWNLOAD PIT TO FILE...", download_pit),
          Action("CLOSE PC SCREEN", fixed("close-pc-screen")),
      ]),
      Section("FLASH / WRITE", "heimdall", [
          Action("FLASH PARTITION...", flash_partition, "write"),
          Action("FLASH RECOVERY...", flash_recovery, "write"),
          Action("FLASH COMBINATION FIRMWARE FOLDER...",
                 flash_combination_folder, "write"),
      ]),
      Section("ODIN FIRMWARE TOOLS", "tar", [
          Action("EXTRACT ODIN .TAR / .TAR.MD5...", extract_tar),
      ]),
      Section("ODIN FIRMWARE TOOLS (LZ4)", "lz4", [
          Action("DECOMPRESS ALL .LZ4 IN FOLDER...", decompress_lz4),
      ]),
  ]

  def options(self, form):
    form.check("noreboot",
               "Do not reboot afterwards (--no-reboot; flash / PIT)")
    form.note(
        "Put the phone in Download Mode first (Vol Down + Power/Bixby, or "
        "ADB tab > REBOOT TO DOWNLOAD). Heimdall needs the exact partition "
        "names from PRINT PIT. It works on older Samsung models; newer "
        "(Android 8+) often need real Odin / Thor. Odin .tar files: EXTRACT "
        "the tar, DECOMPRESS the .lz4 files, then flash the images.\n\n"
        "COMBINATION firmware is Samsung's factory test package (file name "
        "starts with COMBINATION_). It boots into the factory test/"
        "diagnosis binary instead of normal Android - useful for hardware "
        "diagnostics (touch, sensors, camera via the Diagnosis app) and for "
        "getting a device that won't boot normally into a state where EFS/"
        "IMEI can be read or repaired. It does not go through the regular "
        "setup wizard, since it isn't running normal Android - that's a "
        "property of the firmware itself, not something this tool changes.")

  def extra_flags(self, script, args, opts):
    if (script == "heimdall" and opts["noreboot"] and args
        and args[0] in ("flash", "print-pit", "download-pit")):
      return ["--no-reboot"]
    return []
