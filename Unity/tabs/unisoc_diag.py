"""UNISOC DIAG tab - tool: unisoc_diag.py

Auto-detects the device by USB VID:PID 1782:4d00. No port argument needed.

The tool performs the full BROM → Diag re-enumeration internally, which
takes 5-15 seconds. It uses pyusb to talk to raw bulk endpoints, because
the phone does NOT expose a /dev/ttyUSB* or /dev/ttyACM* node.

Firmware capability varies by device class:
  * Consumer phones (Infinix, Tecno, itel, Tiger T-series):
      full Diag firmware — shell, ADB enable, factory reset all work
  * POS / payment terminals (sc9832e-class):
      restricted firmware — shell and device-ID commands return error
      only info/cal/psn reads work

The tab exposes buttons for the full feature set; the tool logs a clear
error if the device's firmware refuses a command.
"""
from Unity.core.actions import Action, Section, fixed
from Unity.tabs.base import Tab


# ---------------------------------------------------------------------------
# Action builders (run on the UI thread, return list[list[str]] or None)
# ---------------------------------------------------------------------------

def shell_command(ui):
    """Prompt for an arbitrary shell command. Auto-adds --danger for
    commands that modify device state."""
    cmd = ui.ask_text(
        "Unisoc shell",
        "Shell command to run (e.g. getprop ro.product.model):",
        "getprop ro.product.model")
    if not cmd:
        return None
    args = ["shell"]
    # Auto-confirm destructive commands so the user doesn't have to
    # remember --danger.
    if any(tok in cmd.lower() for tok in (
            "rm ", "wipe", "setprop", "settings put",
            "am broadcast", "svc ", "pm ", ">", "dd ")):
        args.append("--danger")
    args.append(cmd)
    return [args]


# ---------------------------------------------------------------------------
# Tab definition
# ---------------------------------------------------------------------------

class UnisocDiagTab(Tab):
    title = "UNISOC DIAG"
    platform = "unisoc"
    config_title = "UNISOC DIAG CONFIGURATION"

    sections = [
        Section("DEVICE INFO", "unisoc_diag.py", [
            Action("READ PLATFORM INFO", fixed("info")),
            Action("READ FULL INFO",     fixed("fullinfo")),
            Action("READ IMEI + MACS",   fixed("cal")),
            Action("READ PSN",           fixed("psn")),
        ]),
        Section("SHELL / SERVICING", "unisoc_diag.py", [
            Action("RUN SHELL COMMAND...", shell_command, "write"),
            Action("ENABLE ADB",
                   fixed("shell", "--danger",
                         "settings put global adb_enabled 1"), "write"),
            Action("ENABLE ADB OVER TCP",
                   fixed("shell", "--danger",
                         "setprop service.adb.tcp.port 5555"), "write"),
        ]),
        Section("FACTORY / DANGER", "unisoc_diag.py", [
            Action("FACTORY RESET",
                   fixed("shell", "--danger",
                         "AT+ETSRESET"),
                   "danger"),
        ]),
    ]

    # -- UI ---------------------------------------------------------------

    def options(self, form):
        """Configuration panel shown above the sections.

        No port selector — the tool auto-detects the device by VID:PID.
        The `form` API in the base Tab class takes care of layout; we
        only need to provide the note text.
        """
        form.note(
            "Device is auto-detected by USB VID:PID 1782:4d00. "
            "No port selection needed.\n\n"
            "Put the phone into BROM mode (power off, hold Vol Down, "
            "plug USB) and click any button. The tool performs the "
            "handshake and re-enumeration automatically (5-15 sec).\n\n"
            "NOTE: POS-class firmware (sc9832e) blocks shell and device-ID "
            "commands. Consumer phones (Infinix, Tecno, itel with Tiger "
            "T-series) support all commands."
        )

    # -- command flow hooks ----------------------------------------------

    def check_cmds(self, ui, cmds):
        """Called before running a batch of commands.

        We always return True — no port is required, and the tool
        handles device detection itself. If you later want to add a
        preflight (e.g. warn the user if the device is POS-class), this
        is where it goes.
        """
        return True

    def pre_args(self, script, args, opts):
        """Arguments that must come BEFORE the subcommand.

        `unisoc_diag.py --wait <subcommand>` — the --wait flag makes the
        tool listen for the device up to 60 seconds. If the device is
        already present, --wait returns immediately, so this is harmless
        for the already-connected case.
        """
        return ["--wait"]

    def extra_flags(self, script, args, opts):
        """No per-command flags to add — VID:PID is hardcoded in the tool."""
        return []

    def apply_profile(self, ui, p):
        """No profile-based settings for Unisoc devices."""
        return []