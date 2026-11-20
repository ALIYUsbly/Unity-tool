"""Runs a queue of external commands with QProcess and reports the output.

The runner knows nothing about tabs: it just gets a list of jobs
(shown_text, program, argv, working_dir) and runs them one after another,
stopping at the first failure.
"""
import re
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

class TaskRunner(QObject):
  message = Signal(str)       # one log line
  busy_changed = Signal(bool)
  finished = Signal(bool)       # True only when every queued command exits 0

  def __init__(self, parent=None):
    super().__init__(parent)
    self.busy = False
    self.abort = False
    self.proc = None
    self._jobs = []
    self._i = 0
    self._buf = ""

  def start(self, jobs):
    self.busy = True
    self.abort = False
    self._jobs = list(jobs)
    self._i = 0
    self.busy_changed.emit(True)
    self._next()

  def stop(self):
    self.abort = True
    p = self.proc
    if p and p.state() != QProcess.NotRunning:
      p.terminate()
      QTimer.singleShot(3000, lambda: self._kill(p))
    self.message.emit("!!! ABORT REQUESTED !!!")

  @staticmethod
  def _kill(p):
    try:
      if p.state() != QProcess.NotRunning:
        p.kill()
    except RuntimeError:  # process object already deleted
      pass

  def _next(self):
    if self.abort or self._i >= len(self._jobs):
      return self._finish(ok=not self.abort)
    shown, program, argv, cwd, env = self._jobs[self._i]
    self._i += 1
    self.message.emit(f"[{self._i}/{len(self._jobs)}] {shown}::")
    p = QProcess(self)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.setWorkingDirectory(cwd)
    if env is not None:
      qenv = QProcessEnvironment()
      for k, v in env.items():
        qenv.insert(k, v)
      p.setProcessEnvironment(qenv)
    p.readyReadStandardOutput.connect(self._on_output)
    p.finished.connect(self._on_finished)
    p.errorOccurred.connect(self._on_error)
    self.proc = p
    self._buf = ""
    p.start(program, argv)

  def _on_output(self, final=False):
    if not self.proc:
      return
    self._buf += bytes(self.proc.readAllStandardOutput()).decode(
        "utf-8", "replace")
    parts = re.split(r"[\r\n]", self._buf)
    self._buf = "" if final is True else parts.pop()
    for line in parts:
      if line.strip():
        self.message.emit(line.strip())

  def _on_error(self, err):
    if err == QProcess.FailedToStart:
      self.message.emit(
          f"CRITICAL: failed to start process ({self.proc.errorString()})")
      self._finish(ok=False)

  def _on_finished(self, code, _status):
    self._on_output(final=True)
    if self.abort:
      return self._finish(ok=False)
    if code != 0:
      self.message.emit(f"ERROR: exit code {code} - stopping.")
      return self._finish(ok=False)
    self.proc.deleteLater()
    self.proc = None
    self._next()

  def _finish(self, ok):
    if not self.busy:
      return
    if ok:
      self.message.emit("SUCCESS: Task completed.")
    elif self.abort:
      self.message.emit("Task aborted.")
    if self.proc is not None:
      self.proc.deleteLater()
    self.proc = None
    self.busy = False
    self.finished.emit(bool(ok))
    self.busy_changed.emit(False)
