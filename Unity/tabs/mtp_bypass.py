"""MTP tab - tool: mtp_trigger.py"""
from Unity.core.actions import Action, Section, fixed
from Unity.tabs.base import Tab


def launch_url(ui):
  """Ask for a URL; returns None (cancel) if the dialog is closed or empty."""
  url = ui.ask_text("Target URL", "Enter website to open:", "https://google.com")
  return [["launch", url]] if url else None


class MtpTab(Tab):
  title = "MTP / BYPASS"
  platform = "mtp"
  config_title = "UNIVERSAL MTP TRIGGER CONFIGURATION"

  sections = [
      Section("BYPASS / LAUNCH INTENTS", "mtp_trigger.py", [
          Action("OPEN YOUTUBE", fixed("launch", "youtube")),
          Action("OPEN GOOGLE MAPS", fixed("launch", "maps")),
          Action("OPEN CUSTOM FILE MANAGER", fixed("launch", "com.Unityscreener.org")),
          Action("LAUNCH CUSTOM URL...", launch_url),
      ]),
      Section("DIAGNOSTICS & SYSTEM", "mtp_trigger.py", [
          Action("READ PHONE INFO (MTP)", fixed("info")),
          Action("REBOOT DEVICE", fixed("reset")),
      ]),
  ]

  def options(self, form):
    # Matches the app's exact top card option rendering format
    form.combo("timeout", "USB Timeout (ms)", ["2000", "5000", "10000"])
    
    # FIXED: Removed 'default' and 'hint' keyword arguments which caused the TypeError
    form.check("force_claim", "Force Claim Interface")


  def check_options(self, ui):
    # No mandatory file configurations required for general MTP operations
    return True

  def extra_flags(self, script, args, opts):
    flags = []
    if not args:
      return flags
    
    # Pass structural settings straight down to mtp_trigger.py execution arguments
    if opts["timeout"]:
      flags.append(f"--timeout={opts['timeout']}")
    if opts["force_claim"]:
      flags.append("--force")
      
    return flags

  def apply_profile(self, ui, p):
    applied = []
    self.v["timeout"].set(p.get("timeout") or "2000")
    self.v["force_claim"].set(p.get("force_claim") if "force_claim" in p else True)
    return applied
