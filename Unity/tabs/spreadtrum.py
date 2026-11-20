"""SPREADTRUM / UNISOC (SPD) tab - tool: spd.py

spd.py takes the serial port FIRST: `spd.py /dev/ttyUSB0 readpart ...`
"""
import glob
import os

from Unity.config import SPD_NV
from Unity.core.actions import Action, Section, batch, fixed
from Unity.core.profile_capture import ProfileField
from Unity.tabs.base import Tab

SPD_NO_PORT_CMDS = {"listparts", "extractpac"}   # never talk to the device
SPD_WRITE_CMDS = {"write", "writepart"}          # --verify applies to these
SPD_DESTRUCTIVE_CMDS = {"write", "writepart", "erase", "erasepart"}  # --force


class DeviceCmd(list):
  """A command that must talk to the device even though its name is normally
  offline (e.g. `spd.py <port> listparts` reads the phone's real table)."""


def uses_device(args):
  return args[0] not in SPD_NO_PORT_CMDS or isinstance(args, DeviceCmd)


# ----------------------------------------------------------- builders ----
def read_partition(ui):
  part = ui.ask_name("SPD Read Partition",
                     "Partition name (e.g. boot, recovery):")
  if not part:
    return None
  out = ui.pick_save("Save Partition As", f"{part}.bin")
  return [["readpart", part, out]] if out else None


def write_partition(ui):
  part = ui.ask_name("SPD Write Partition", "Partition name (e.g. boot):")
  if not part:
    return None
  src = ui.pick_file(f"Select image file for '{part}'")
  return [["writepart", part, src]] if src else None


def erase_partition(ui):
  part = ui.ask_name("SPD Erase Partition", "Partition name to erase:")
  return [["erasepart", part]] if part else None


def extract_pac(ui):
  pac = ui.pick_file("Select firmware .pac",
                     "PAC firmware (*.pac);;All files (*)")
  return [["extractpac", pac]] if pac else None


def list_parts_from_device(ui):
  """Connects to the phone (needs port + FDLs) and lists its real table."""
  return [DeviceCmd(["listparts"])]


def _read_many(ui, title, prompt, default=""):
  names = ui.ask_text(title, prompt, default)
  if not names:
    return None
  d = ui.pick_dir("Folder to save the backup into")
  if not d:
    return None
  parts = [n.strip() for n in names.split(",") if n.strip()]
  return [["readpart", n, os.path.join(d, f"{n}.bin")] for n in parts]


def backup_partitions(ui):
  return _read_many(
      ui, "Backup partitions",
      "Partition names, comma separated (e.g. boot,recovery,modem):")


def backup_nv(ui):
  return _read_many(
      ui, "Backup NV / IMEI partitions",
      "Partitions to back up (comma separated). Names differ per model: "
      "check LIST PARTITIONS first.", ",".join(SPD_NV))


def write_folder(ui):
  d = ui.pick_dir("Folder with images named <partition>.bin or .img")
  if not d:
    return None
  files = sorted(f for f in os.listdir(d)
                 if f.lower().endswith((".bin", ".img"))
                 and not f.lower().startswith("fdl"))
  if not files:
    ui.dialog("Write folder", "No .bin or .img files found in that folder.")
    return None
  return [["writepart", os.path.splitext(f)[0], os.path.join(d, f)]
          for f in files]


# --------------------------------------------------------------- tab -----
class SpreadtrumTab(Tab):
  title = "SPREADTRUM (SPD)"
  platform = "spd"
  config_title = "SPREADTRUM CONFIGURATION"

  sections = [
      Section("READ / BACKUP", "spd.py", [
          Action("READ DEVICE INFO", fixed("info")),
          Action("TEST CONNECTION (HANDSHAKE)", fixed("handshake")),
          Action("LIST PARTS (BUILT-IN TABLE)", fixed("listparts")),
          Action("LIST PARTS (FROM DEVICE)", list_parts_from_device),
          Action("READ PARTITION...", read_partition),
          Action("BACKUP PARTITIONS...", backup_partitions),
          Action("BACKUP NV / IMEI DATA...", backup_nv),
          Action("EXTRACT FDL FROM .PAC...", extract_pac),
      ]),
      Section("FLASH / WRITE", "spd.py", [
          Action("WRITE PARTITION...", write_partition, "write"),
          Action("WRITE FOLDER (name.bin/.img)...", write_folder, "write"),
      ]),
      Section("ERASE / RESET", "spd.py", [
          Action("ERASE PARTITION...", erase_partition, "danger"),
          Action("FRP BYPASS",
                 batch(["erasepart", "persistent"], ["erasepart", "frp"]),
                 "danger"),
          Action("FACTORY RESET",
                 batch(["erasepart", "userdata"], ["erasepart", "cache"]),
                 "danger"),
      ]),
  ]

  def options(self, form):
    self.port_box = form.combo("port", "Serial port", [""],
                               button_=("Detect", self.detect_ports))
    form.file("fdl1", "FDL1", "Select FDL1", "FDL / BIN (*.bin);;All Files (*)")
    form.file("fdl2", "FDL2", "Select FDL2", "FDL / BIN (*.bin);;All Files (*)")
    form.combo("baud", "Baud rate", ["", "115200", "460800", "921600"],
               hint="blank = tool default")
    form.check("verify", "Verify writes (--verify)")
    form.check("force", "Force critical operations (--force)", "#ff8a8a")
    form.check("debug", "Debug output (--debug)")
    form.note("FDL files must match the phone's chipset. EXTRACT FDL FROM .PAC "
              "pulls them out of stock firmware. The BUILT-IN table is "
              "generic: use FROM DEVICE to see the phone's real partitions.")

  def detect_ports(self):
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    self.port_box.clear()
    self.port_box.addItems(ports)
    if ports:
      self.port_box.setCurrentText(ports[0])
      self.ui.log(f"SERIAL PORTS: {', '.join(ports)}")
    else:
      self.ui.log("SERIAL PORTS: none found (check the cable, download "
                  "mode, ModemManager and the dialout group)")

  def check_cmds(self, ui, cmds):
    if not any(uses_device(c) for c in cmds):
      return True
    baud = self.v["baud"].get().strip()
    if baud and not baud.isdigit():
      ui.dialog("Baud rate", "Baud rate must be a number (or leave it blank).")
      return False
    if not self.v["port"].get().strip():
      ui.dialog("Serial port",
                "Select the Spreadtrum serial port first (click Detect).")
      return False
    return not (self.file_missing(ui, "fdl1", "FDL1")
                or self.file_missing(ui, "fdl2", "FDL2"))

  def risk_note(self, cmds):
    if any(c and c[0] in SPD_DESTRUCTIVE_CMDS for c in cmds):
      return ("SPD: if the phone's partition table can't be read, the tool "
              "falls back to a GENERIC layout. Check LIST PARTS (FROM "
              "DEVICE) first.\n\n")
    return ""

  def pre_args(self, script, args, opts):
    if not args:
      return []
    if not uses_device(args):
      # spd.py reads the first word as the port, so these commands need an
      # EMPTY port ("") or `listparts` itself would be taken as the port
      return [""]
    return [opts["port"]] if opts["port"] else []

  def extra_flags(self, script, args, opts):
    flags = []
    if not args or not uses_device(args):
      return flags
    cmd = args[0]
    if opts["fdl1"]:
      flags += ["--fdl1", opts["fdl1"]]
    if opts["fdl2"]:
      flags += ["--fdl2", opts["fdl2"]]
    if opts["baud"]:
      flags += ["--baud", opts["baud"]]
    if opts["debug"]:
      flags.append("--debug")
    if opts["verify"] and cmd in SPD_WRITE_CMDS:
      flags.append("--verify")
    if opts["force"] and cmd in SPD_DESTRUCTIVE_CMDS:
      flags.append("--force")
    return flags

  def apply_profile(self, ui, p):
    applied = []
    self.apply_path(ui, p, "fdl1", "fdl1", "FDL1", applied)
    self.apply_path(ui, p, "fdl2", "fdl2", "FDL2", applied)
    return applied

  def profile_fields(self):
    # port/baud/verify/force/debug are session choices, never saved - same
    # as apply_profile() above never restoring them.
    return {
        "fdl1": ProfileField("fdl1", "file"),
        "fdl2": ProfileField("fdl2", "file"),
    }
