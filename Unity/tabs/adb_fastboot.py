"""ADB / FASTBOOT tab - tools: adb, fastboot (found on PATH)"""
import os
import shlex

from Unity.core import adb_query
from Unity.core.actions import Action, Section, batch, fixed
from Unity.tabs.base import Tab


def _query(ui, fn):
  """Run an adb_query function; if adb reports more than one device is
  connected, ask for a serial once and retry with it. Returns (names, err)."""
  names, err = fn()
  if err and "more than one device" in err.lower():
    serial = ui.ask_text("Multiple devices",
                         "More than one device/emulator found - serial to "
                         "use:")
    if not serial:
      return [], err
    names, err = fn(serial)
  return names, err


# ------------------------------------------------------ ADB builders -----
def adb_info(ui):
  props = ["ro.product.model", "ro.product.brand", "ro.build.version.release",
           "ro.build.version.security_patch", "ro.board.platform",
           "ro.build.display.id"]
  return [["shell", "getprop", p] for p in props]


def adb_install(ui):
  f = ui.pick_file("Select APK", "APK (*.apk);;All files (*)")
  return [["install", "-r", f]] if f else None

def frpbypass(ui):
  cmd=["content insert --uri content://settings/secure --bind name:s:user_setup_complete --bind value:s:1",
      "settings put global setup_wizard_has_run 1",
      "settings put secure user_setup_complete 1",
      "settings put global device_provisioned 1"
      ]
  return [["shell",p] for p in cmd ]

def adb_push(ui):
  f = ui.pick_file("File to push")
  if not f:
    return None
  dest = ui.ask_text("Push", "Destination path on the device:",
                     "/sdcard/Download/")
  return [["push", f, dest]] if dest else None


def adb_pull(ui):
  src = ui.ask_text("Pull", "File or folder path on the device:")
  if not src:
    return None
  d = ui.pick_dir("Save to folder")
  return [["pull", src, d]] if d else None


def adb_shell(ui):
  c = ui.ask_text("ADB shell", "Command to run on the device:")
  if not c:
    return None
  try:
    return [["shell"] + shlex.split(c)]
  except ValueError as e:
    ui.dialog("Shell command", f"Cannot parse command: {e}")
    return None


def adb_sideload(ui):
  f = ui.pick_file("Update zip to sideload", "ZIP (*.zip);;All files (*)")
  return [["sideload", f]] if f else None


# -------------------------------------------- package manager (debloat) -----
def pm_scan_uninstall(ui):
  names, err = _query(ui, adb_query.list_packages)
  if err:
    ui.dialog("Scan packages", f"adb error:\n{err}")
    return None
  if not names:
    ui.dialog("Scan packages", "No packages found - is a device connected "
             "with USB debugging on?")
    return None
  picked = ui.package_dialog(
      "Installed packages - pick what to uninstall", names,
      note="Removed with `pm uninstall --user 0`: gone for this user, but "
           "NOT wiped from the system image. Use RESTORE PACKAGE to bring "
           "any of these back later.")
  if not picked:
    return None
  return [["shell", "pm", "uninstall", "--user", "0", p] for p in picked]


def pm_restore(ui):
  names, err = _query(ui, adb_query.list_restorable)
  if err:
    ui.dialog("Restore packages", f"adb error:\n{err}")
    return None
  if not names:
    ui.dialog("Restore packages", "Nothing to restore - no packages are "
             "currently removed for this user.")
    return None
  picked = ui.package_dialog(
      "Packages removed for this user - pick what to restore", names)
  if not picked:
    return None
  return [["shell", "cmd", "package", "install-existing", p] for p in picked]


# ------------------------------------------------ fastboot builders -----
def fb_flash(ui):
  part = ui.ask_name("Fastboot flash", "Partition name (e.g. boot, recovery):")
  if not part:
    return None
  f = ui.pick_file(f"Image to flash to '{part}'")
  return [["flash", part, f]] if f else None


def fb_flash_folder(ui):
  d = ui.pick_dir("Folder with <partition>.img files")
  if not d:
    return None
  imgs = sorted(f for f in os.listdir(d) if f.lower().endswith(".img"))
  if not imgs:
    ui.dialog("Flash folder", "No .img files found in that folder.")
    return None
  return [["flash", os.path.splitext(f)[0], os.path.join(d, f)] for f in imgs]


def fb_erase(ui):
  part = ui.ask_name("Fastboot erase", "Partition name to erase:")
  return [["erase", part]] if part else None


def fb_boot(ui):
  f = ui.pick_file("Image to boot (not flashed)")
  return [["boot", f]] if f else None


def fb_slot(ui):
  s = ui.ask_name("Active slot", "Slot (a or b):")
  return [["set_active", s]] if s in ("a", "b") else None


# --------------------------------------------------------------- tab -----
class AdbFastbootTab(Tab):
  title = "ADB / FASTBOOT"
  platform = None
  config_title = "ADB / FASTBOOT CONFIGURATION"

  sections = [
      Section("ADB (phone booted, USB debugging on)", "adb", [
          Action("LIST DEVICES", fixed("devices", "-l")),
          Action("DEVICE INFO", adb_info),
          Action("INSTALL APK...", adb_install),
          Action("PUSH FILE TO DEVICE...", adb_push),
          Action("PULL FILE FROM DEVICE...", adb_pull),
          Action("RUN SHELL COMMAND...", adb_shell),
          Action("SIDELOAD ZIP (RECOVERY)...", adb_sideload, "write"),
          Action("FRPBYPASS",frpbypass)
      ]),
      Section("PACKAGE MANAGER (debloat)", "adb", [
          Action("SCAN INSTALLED PACKAGES...", pm_scan_uninstall, "write"),
          Action("RESTORE PACKAGE...", pm_restore),
      ]),
      Section("ADB REBOOT", "adb", [
          Action("REBOOT SYSTEM", fixed("reboot")),
          Action("REBOOT TO BOOTLOADER", fixed("reboot", "bootloader")),
          Action("REBOOT TO RECOVERY", fixed("reboot", "recovery")),
          Action("REBOOT TO DOWNLOAD (SAMSUNG)", fixed("reboot", "download")),
          Action("REBOOT TO EDL (QUALCOMM)", fixed("reboot", "edl")),
      ]),
      Section("FASTBOOT (bootloader mode)", "fastboot", [
          Action("LIST DEVICES", fixed("devices")),
          Action("GETVAR ALL", fixed("getvar", "all")),
          Action("BOOT IMAGE (NO FLASH)...", fb_boot),
          Action("REBOOT", fixed("reboot")),
          Action("REBOOT TO BOOTLOADER", fixed("reboot", "bootloader")),
          Action("REBOOT TO RECOVERY", fixed("reboot", "recovery")),
          Action("SET ACTIVE SLOT...", fb_slot, "write"),
      ]),
      Section("FASTBOOT FLASH / ERASE", "fastboot", [
          Action("FLASH PARTITION...", fb_flash, "write"),
          Action("FLASH FOLDER (<partition>.img)...", fb_flash_folder, "write"),
          Action("UNLOCK BOOTLOADER", fixed("flashing", "unlock"), "danger"),
          Action("LOCK BOOTLOADER", fixed("flashing", "lock"), "danger"),
          Action("ERASE PARTITION...", fb_erase, "danger"),
          Action("ERASE FRP", fixed("erase", "frp"), "danger"),
          Action("WIPE USERDATA + CACHE",
                 batch(["erase", "userdata"], ["erase", "cache"]), "danger"),
      ]),
  ]

  def options(self, form):
    form.entry("serial", "Device serial",
               hint="blank = the only connected device")

  def pre_args(self, script, args, opts):
    # `-s <serial>` goes before the command; `devices` does not take it
    if opts["serial"] and args and args[0] != "devices":
      return ["-s", opts["serial"]]
    return []
