"""USB-based device detection (no GUI code, so it is easy to test).

Maps the VID:PID pair a phone exposes in a flashing/diagnostic USB mode to a
platform ("qualcomm" / "mtk" / "spd" / None) and a human-readable mode label,
so the app can suggest the right tab instead of making the user identify the
chipset by hand.

This is a hint, not a guarantee: several brands/chipsets reuse the same
generic VID:PID (e.g. MediaTek's BROM ID is shared across hundreds of
models), so detection narrows down "which tab" and "which mode", never
"which exact model" - the profile picker is still how you pick that.

Works with pyusb if it's installed (cross-platform); otherwise falls back to
parsing `lsusb` output, which is only available on Linux. If neither path
finds anything, scan() just returns an empty list rather than raising, so a
missing dependency never breaks the rest of the app.
"""
import re
import subprocess

# (vid, pid) in lowercase hex, no separators -> (platform_or_None, label)
USB_SIGNATURES = {
    ("05c6", "9008"): ("qualcomm", "EDL / Emergency Download Mode"),
    ("05c6", "900e"): ("qualcomm", "DIAG"),
    ("05c6", "9006"): ("qualcomm", "EDL (alternate PID)"),
    ("0e8d", "0003"): ("mtk", "BROM"),
    ("0e8d", "2000"): ("mtk", "Preloader"),
    ("1782", "4d00"): ("spd", "Spreadtrum Boot ROM / diag"),
    ("04e8", "685d"): (None, "Samsung Download Mode (Odin)"),
    ("04e8", "6860"): (None, "Samsung Download Mode (Odin)"),
    ("18d1", "d001"): (None, "Android fastboot"),
    ("18d1", "4ee7"): (None, "Android fastboot / ADB composite"),
}

_ID_RE = re.compile(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})")


def _via_pyusb():
  import usb.core  # noqa: deferred import - optional dependency
  ids = set()
  for dev in usb.core.find(find_all=True):
    try:
      ids.add((f"{dev.idVendor:04x}", f"{dev.idProduct:04x}"))
    except Exception:
      continue
  return ids


def _via_lsusb():
  out = subprocess.run(["lsusb"], capture_output=True, text=True,
                       timeout=5, check=False).stdout
  ids = set()
  for line in out.splitlines():
    m = _ID_RE.search(line)
    if m:
      ids.add((m.group(1).lower(), m.group(2).lower()))
  return ids


def list_usb_ids():
  """Every (vid, pid) lowercase-hex pair currently on the USB bus.

  Returns an empty set (never raises) if no enumeration method works.
  """
  try:
    return _via_pyusb()
  except Exception:
    pass
  try:
    return _via_lsusb()
  except Exception:
    return set()


def scan():
  """Recognised devices currently connected.

  Returns a list of (platform_or_None, label, vid, pid) tuples - one per
  matched VID:PID. Empty list means nothing recognised was found.
  """
  found = []
  for vid, pid in list_usb_ids():
    sig = USB_SIGNATURES.get((vid, pid))
    if sig:
      platform, label = sig
      found.append((platform, label, vid, pid))
  return found
