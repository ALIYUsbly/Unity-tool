"""Device profile loading and filtering (no GUI code, so it is easy to test)."""

import json
import os
import sys
REQUIRED_KEYS = ("id", "brand", "model", "platform")

def _load_profile_offsets(PROFILES_DIR,profile_id_or_model):
    """Look up frp_lba/para_lba from the device profile JSON.
    Returns (frp_lba, para_lba) or (None, None) if not in profile."""
    # Try id first, then model
    for candidate in (profile_id_or_model,):
        path = os.path.join(PROFILES_DIR, f"{candidate}.json")
        if os.path.exists(path):
            with open(path) as f:
                p = json.load(f)
            return p.get("frp_lba"), p.get("para_lba"),p.get("board")
    return None, None
def _find_profile_by_model(PROFILES_DIR,model):
    """Find the profile id whose 'model' field matches (case-insensitive)."""
    if not os.path.isdir(PROFILES_DIR):
        return None
    for fname in os.listdir(PROFILES_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(PROFILES_DIR, fname)
        try:
            with open(path) as f:
                p = json.load(f)
            if p.get("model", "").lower() == model.lower():
                return p.get("id")
        except Exception:
            continue
    return None

def load_profiles(root):
  """Load every *.json under `root`.

  Returns (profiles, errors). A broken file never stops the others loading;
  it just adds a message to `errors`.
  """
  profiles, errors = [], []
  seen_ids = set()
  for dirpath, _dirs, files in os.walk(root):
    for name in sorted(files):
      if not name.endswith(".json"):
        continue
      path = os.path.join(dirpath, name)
      rel = os.path.relpath(path, root)
      try:
        with open(path, encoding="utf-8") as f:
          data = json.load(f)
      except (OSError, ValueError) as e:
        errors.append(f"{rel}: {e}")
        continue
      if not isinstance(data, dict):
        errors.append(f"{rel}: top level must be an object")
        continue
      missing = [k for k in REQUIRED_KEYS if not data.get(k)]
      if missing:
        errors.append(f"{rel}: missing {', '.join(missing)}")
        continue
      if data["id"] in seen_ids:
        errors.append(f"{rel}: duplicate id '{data['id']}'")
        continue
      seen_ids.add(data["id"])
      data["platform"] = str(data["platform"]).lower()
      data.setdefault("codename", "")
      data.setdefault("notes", "")
      data["_path"] = path
      profiles.append(data)
  profiles.sort(key=lambda p: (p["brand"].lower(), p["model"].lower()))
  return profiles, errors


def filter_profiles(profiles, query="", brand_key=None):
  """Filter by search text and an optional brand/platform key.

  Every word in `query` must appear somewhere in brand, model, codename,
  platform or id. `brand_key` matches either the brand ("Xiaomi") or the
  platform ("qualcomm", "mtk"), case-insensitively.
  """
  words = (query or "").lower().split()
  key = brand_key.lower() if brand_key else None
  result = []
  for p in profiles:
    if key and key not in (p.get("brand", "").lower(), p.get("platform", "")):
      continue
    haystack = " ".join(
        str(p.get(k, "")) for k in ("brand", "model", "codename", "platform",
                                    "id")).lower()
    if all(w in haystack for w in words):
      result.append(p)
  return result
