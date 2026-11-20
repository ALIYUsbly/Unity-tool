"""APPLE / iOS tab - tools: ideviceinfo, idevicediagnostics, idevicebackup2,
idevicerestore, idevicecrashreport (from the open-source libimobiledevice
project: https://libimobiledevice.org).

These talk to the device through usbmuxd using Apple's own published
protocol (the same one iTunes/Finder use) - nothing here bypasses Apple's
signing or security model. idevicerestore in particular still needs Apple's
signature server to bless the IPSW being restored, so it only works for iOS
versions Apple is currently signing, same as iTunes/Finder restore.

Setup (not done by this file):
  Linux:   apt install usbmuxd libimobiledevice-utils
           (usbmuxd must be running; it usually starts automatically)
  Windows: install "Apple Mobile Device Support" (ships with iTunes, or the
           standalone installer) so usbmuxd-equivalent pairing works, then
           put libimobiledevice's Windows builds on PATH or in a vendor
           folder referenced by LOCAL_TOOL_DIRS.
  The device must have "Trust This Computer" accepted at least once for any
  action except the DFU/Recovery-mode firmware restore, which works even on
  a disabled/unresponsive device.
"""
from Unity.core.actions import Action, Section, fixed
from Unity.tabs.base import Tab


# ----------------------------------------------------------- builders ----
def backup_device(ui):
  d = ui.pick_dir("Folder to save the full encrypted backup into")
  return [["backup", "--full", d]] if d else None


def restore_backup(ui):
  d = ui.pick_dir("Folder containing the backup to restore")
  return [["restore", d]] if d else None


def pull_crash_logs(ui):
  d = ui.pick_dir("Folder to save crash logs into")
  return [[d]] if d else None


def restore_update(ui):
  """Reinstall/repair iOS from an IPSW, keeping the user's data (like
  iTunes/Finder "Update")."""
  f = ui.pick_file("IPSW firmware file",
                   "IPSW firmware (*.ipsw);;All Files (*)")
  return [[f]] if f else None


def restore_erase(ui):
  """Full restore from an IPSW, erasing the device (like iTunes/Finder
  "Restore iPhone...", or the only option for a disabled/unresponsive
  device)."""
  f = ui.pick_file("IPSW firmware file",
                   "IPSW firmware (*.ipsw);;All Files (*)")
  return [["-e", f]] if f else None


# --------------------------------------------------------------- tab -----
class IosTab(Tab):
  title = "APPLE / iOS"
  platform = "ios"
  config_title = "APPLE / iOS"

  sections = [
      Section("DEVICE INFO", "ideviceinfo", [
          Action("FULL INFO", fixed()),
          Action("SIMPLE INFO (model / iOS / serial)", fixed("-s")),
      ]),
      Section("DIAGNOSTICS", "idevicediagnostics", [
          Action("RUN DIAGNOSTICS", fixed("diagnostics")),
          Action("BATTERY INFO", fixed("ioregistry", "-k", "BatteryData")),
          Action("RESTART DEVICE", fixed("restart")),
      ]),
      Section("BACKUP / RESTORE (Apple protocol)", "idevicebackup2", [
          Action("FULL BACKUP...", backup_device),
          Action("RESTORE FROM BACKUP...", restore_backup, "write"),
      ]),
      Section("CRASH LOGS", "idevicecrashreport", [
          Action("PULL CRASH LOGS...", pull_crash_logs),
      ]),
      Section("FIRMWARE RESTORE (DFU / Recovery mode)", "idevicerestore", [
          Action("UPDATE FROM IPSW... (keeps data)", restore_update, "write"),
          Action("RESTORE FROM IPSW... (erases device)", restore_erase,
                 "danger"),
      ]),
  ]

  def options(self, form):
    form.note(
        "Most actions need 'Trust This Computer' accepted on the device "
        "at least once. Firmware restore works even on a disabled or "
        "unresponsive device (DFU/Recovery mode) and still needs Apple's "
        "signature server to accept the IPSW, same as iTunes/Finder.")
