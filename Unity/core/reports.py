"""Plain-text reports of what a read-only tool printed (no GUI code).

Reports land in <BACKUP_DIR>/reports/<time>_<action>.txt. They can contain
IMEI / MEID / serial numbers, so that folder is git-ignored with the rest of
backups/.
"""
import os
import re
import time

from Unity.config import BACKUP_DIR

REPORTS_SUBDIR = "reports"


def slug(text):
  return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "report"


def report_path(label, root=None, now=None):
  root = root or os.path.join(BACKUP_DIR, REPORTS_SUBDIR)
  stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
  return os.path.join(root, f"{stamp}_{slug(label)}.txt")


def write_report(path, label, shown_cmds, lines, ok, now=None):
  """Write the report and return its path (raises OSError on failure)."""
  os.makedirs(os.path.dirname(path), exist_ok=True)
  when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
  head = [f"TSM report: {label}", f"Time: {when}",
          f"Status: {'complete' if ok else 'INCOMPLETE (failed or aborted)'}",
          "", "Commands:"]
  head += [f"  {c}" for c in shown_cmds]
  with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(head) + "\n\nOutput:\n" + "\n".join(lines) + "\n")
  return path
