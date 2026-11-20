"""Checks run before anything is written to a phone."""
import os

from PySide6.QtCore import QObject, QThread, Signal

from Unity.core.backups import backup_status_text
from Unity.config import (MTK_NV_HINT, QCOM_EFS, SPARSE_MAGIC, SPD_NV_HINT,
                    WRITE_CMDS_WITH_FILE)


def is_sparse_image(path):
  try:
    with open(path, "rb") as f:
      return f.read(4) == SPARSE_MAGIC
  except OSError:
    return False


def find_sparse_images(script, cmds):
  """Files about to be written raw that are Android sparse images."""
  found = []
  for c in cmds:
    if len(c) >= 3 and c[0] in WRITE_CMDS_WITH_FILE:
      files = c[2].split(",") if script == "mtk.py" else [c[2]]
      found += [p for p in files if os.path.isfile(p) and is_sparse_image(p)]
  return found


class _SparseConverterWorker(QObject):
  """Converts every sparse image referenced by `cmds` to a raw copy.
  Runs on a background QThread so a multi-GB system.img/userdata.img
  doesn't freeze the GUI - unsparse() is pure Python, not a subprocess,
  so QProcess (used for mtk.py itself) doesn't apply here; QThread does."""
  progress = Signal(str)
  finished = Signal(object)   # converted cmds, or None on failure

  def __init__(self, script, cmds):
    super().__init__()
    self.script = script
    self.cmds = cmds

  def run(self):
    if self.script != "mtk.py":
      self.finished.emit(self.cmds)
      return
    from Unity.core import sparse as SP
    out = []
    for c in self.cmds:
      if len(c) >= 3 and c[0] in WRITE_CMDS_WITH_FILE:
        new = []
        for p in c[2].split(","):
          if os.path.isfile(p) and is_sparse_image(p):
            name = os.path.basename(p)
            self.progress.emit(f"{name}: sparse image, converting to raw...")
            last = {"pct": -5}

            def cb(done, total, name=name, last=last):
              pct = (done * 100 // total) if total else 0
              if pct >= last["pct"] + 5 or pct in (0, 100):
                self.progress.emit(f"{name}: converting to raw... {pct}%")
                last["pct"] = pct

            try:
              p = SP.raw_for(p, progress=cb)
            except (OSError, ValueError) as e:
              self.progress.emit(f"ERROR converting {name}: {e}")
              self.finished.emit(None)
              return
            self.progress.emit(f"  writing the raw copy instead: {p}")
          new.append(p)
        c = [c[0], c[1], ",".join(new)] + list(c[3:])
      out.append(c)
    self.finished.emit(out)


def make_sparse_converter(script, cmds):
  """Build (but do not start) a background QThread + worker for sparse
  conversion. Returns (thread, worker).

  IMPORTANT - caller contract: connect worker.progress and
  worker.finished to BOUND METHODS OF A REAL QOBJECT (e.g. the
  MainWindow), never to a plain function/lambda/closure. Qt's
  AutoConnection can only tell that a cross-thread signal needs to be
  queued back onto the receiver's own thread when the receiver is a
  QObject it can inspect - for a bare callable it has no thread
  affinity to go on, so it runs the slot directly INSIDE the emitting
  (background) thread instead. Since progress/finished end up touching
  GUI widgets and calling thread.quit()/wait(), that means GUI calls
  from a non-GUI thread (undefined behaviour, frequently crashes the
  whole process) and wait() potentially deadlocking against itself.
  Routing through MainWindow's own bound slots gets a correct, safe
  QueuedConnection back to the main thread for free."""
  thread = QThread()
  worker = _SparseConverterWorker(script, cmds)
  worker.moveToThread(thread)
  thread.started.connect(worker.run)
  return thread, worker


def confirm_sparse(ui, sparse):
  return ui.dialog(
      "Sparse image detected",
      "These files are Android sparse images:\n\n  "
      + "\n  ".join(os.path.basename(p) for p in sparse)
      + "\n\nWriting a sparse image raw usually leaves a partition that "
        "will not boot unless the tool converts it first (for example "
        "with simg2img). Write anyway?",
      ok="Write anyway", cancel="Cancel", danger=True)


def confirm_risk(ui, label, risk, cmds, note=""):
  """Backup warning shown for every write / erase. `note` is an extra
  paragraph from the tab (it must end with a blank line)."""
  preview = "\n".join("  " + " ".join(c) for c in cmds[:12])
  if len(cmds) > 12:
    preview += f"\n  ... (+{len(cmds) - 12} more)"
  head = ("This will ERASE data on the device." if risk == "danger"
          else "This will WRITE to the device storage.")
  msg = (f"{label}\n\n{head}\n\n"
         "Have you backed up the important partitions first?\n"
         f"  Qualcomm: {', '.join(QCOM_EFS)}\n  MTK: {MTK_NV_HINT}\n"
         f"  SPD: {SPD_NV_HINT}\n"
         "Losing these can mean a lost IMEI / no network.\n\n"
         f"{backup_status_text()}"
         f"{note}Commands:\n{preview}\n\nContinue?")
  return ui.dialog("Backup warning", msg, ok="Continue", cancel="Cancel",
                   danger=(risk == "danger"))
