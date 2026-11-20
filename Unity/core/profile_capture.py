"""Turns a tool run's captured output into a ready-to-save device profile.

No GUI code here, so it's easy to test. The GUI side (a button in each tab's
config panel, wired up in MainWindow.save_as_profile) builds on top of
extract_device_facts(), capture_tab_values() and build_profile() below.
"""
import collections
import os
import re

# A tab declares, in its profile_fields() hook, which of its option keys
# (self.v / tab.values() keys) are worth saving into a device profile, and
# under what JSON key:
#   "file"  - the value is a path; copy it into the profile's loaders
#             folder and store the copy's path (same handling apply_path()
#             uses to load a file field back).
#   "value" - stored as-is (empty string becomes None, matching the "null
#             = auto" convention already used by the hand-written profiles).
# A key with no entry here (e.g. a session toggle like "skipwrite") is never
# saved, matching how that tab's own apply_profile() never restores it.
ProfileField = collections.namedtuple("ProfileField", "profile_key kind")

QCOM_PATTERNS = {
    "hwid": r"HWID:\s*(0x[0-9a-fA-F]+)",
    "pk_hash": r"PK_HASH:\s*(0x[0-9a-fA-F]+)",
    "cpu": r'CPU detected:\s*"([^"]+)"',
    "serial": r"Serial:\s*(0x[0-9a-fA-F]+)",
    "target_name": r"TargetName=(\S+)",
    "memory_detected": r"MemoryName=(\S+)",
    "sector_size_detected": r"block_size:(\d+)",
}

# MTK/SPD output formats haven't been checked against real tool output yet -
# add patterns here the same way once we have a sample log for each.
MTK_PATTERNS = {}
SPD_PATTERNS = {}

PATTERNS_BY_PLATFORM = {
    "qualcomm": QCOM_PATTERNS,
    "mtk": MTK_PATTERNS,
    "spd": SPD_PATTERNS,
}


def extract_device_facts(platform, text):
  """{fact_name: value} for every pattern that matched in `text`.

  Only the first match of each pattern is kept (a printgpt dump can repeat
  some lines, e.g. once per LUN, and the first occurrence is representative).
  Returns {} if the platform is unknown or nothing matched - never raises.
  """
  facts = {}
  for name, pattern in PATTERNS_BY_PLATFORM.get(platform, {}).items():
    m = re.search(pattern, text)
    if m:
      facts[name] = m.group(1)
  return facts


def facts_note(facts):
  """Human-readable line for the profile's `notes` field, or ''."""
  if not facts:
    return ""
  parts = [f"{k}={v}" for k, v in facts.items()]
  return "Captured from device: " + ", ".join(parts) + "."


def slug(text):
  return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "device"


def unique_path(path):
  """`path`, or `path` with -2, -3, ... inserted before the extension if it
  already exists."""
  if not os.path.exists(path):
    return path
  root, ext = os.path.splitext(path)
  for i in range(2, 1000):
    cand = f"{root}-{i}{ext}"
    if not os.path.exists(cand):
      return cand
  raise OSError(f"too many existing files named like {path}")


def copy_loader_files(values, loaders_dir, model_slug, copy=None):
  """For every value in `values` that is an existing file on disk, copy it
  into loaders_dir and return a new dict with that value replaced by the
  copy's path. Non-file values are passed through unchanged.

  `copy` defaults to shutil.copy2; tests pass a fake to avoid touching disk.
  """
  import shutil
  copy = copy or shutil.copy2
  out = dict(values)
  for key, val in values.items():
    if isinstance(val, str) and val and os.path.isfile(val):
      os.makedirs(loaders_dir, exist_ok=True)
      name = os.path.basename(val)
      dest = unique_path(os.path.join(loaders_dir, f"{model_slug}_{name}"))
      copy(val, dest)
      out[key] = dest
  return out


def capture_tab_values(values, fields, loaders_dir, model_slug,
                       devices_dir=None, copy=None):
  """`values` (from tab.values()) + `fields` (from tab.profile_fields())
  -> {profile_key: value-ready-to-json-dump}, applying each field's "file"
  or "value" handling. Keys in `values` with no entry in `fields` are
  dropped (that's how a session-only option like "skipwrite" is excluded).

  A copied loader's path is stored relative to `devices_dir` when given
  (matching every hand-written profile's convention, e.g.
  "loaders/qualcomm/A3S.elf" - this is what keeps working if the whole
  project folder is ever moved), or absolute when `devices_dir` is None.
  """
  by_file = {k: v for k, v in values.items()
            if k in fields and fields[k].kind == "file"}
  copied = copy_loader_files(by_file, loaders_dir, model_slug, copy=copy)
  if devices_dir:
    copied = {k: (os.path.relpath(v, devices_dir) if v else v)
              for k, v in copied.items()}
  out = {}
  for key, field in fields.items():
    val = values.get(key, "")
    if field.kind == "file":
      val = copied.get(key, val)
      out[field.profile_key] = val or None
    else:
      out[field.profile_key] = val if val not in ("", None) else None
  return out


def unique_id(base_id, existing_ids):
  """`base_id`, or `base_id` with -2, -3, ... appended, until it is not in
  `existing_ids` (the uniqueness load_profiles() actually enforces - a
  profile's `id` must be unique, regardless of its file name)."""
  if base_id not in existing_ids:
    return base_id
  for i in range(2, 1000):
    cand = f"{base_id}-{i}"
    if cand not in existing_ids:
      return cand
  raise ValueError(f"too many existing profiles with id like {base_id}")


def build_profile(platform, brand, model, codename, values, facts,
                  extra_notes=""):
  """The JSON-ready dict for a new device profile (paths in `values` must
  already be the COPIED loader paths, as returned by copy_loader_files)."""
  profile = {
      "id": slug(f"{brand}_{model}_{codename}" if codename
                else f"{brand}_{model}"),
      "brand": brand,
      "model": model,
      "codename": codename or "",
      "platform": platform,
  }
  profile.update(values)
  for name, value in facts.items():        # kept as explicit fields too, not
    profile[name] = value                  # just prose, so later code could
                                            # match on them automatically
  note = " ".join(x for x in (facts_note(facts), extra_notes) if x)
  profile["notes"] = note
  return profile
