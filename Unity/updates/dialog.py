"""TSM update checker dialog."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QApplication,
)

from Unity.version import VERSION, UPDATE_CHANNEL, UPDATE_PLATFORM
from Unity.updates.client import (
    fetch_manifest,
    is_newer,
    download_verified,
)


class UpdateDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("TSM Updates")
        self.setMinimumWidth(520)

        self.manifest = None

        layout = QVBoxLayout(self)

        self.info = QLabel("Checking for updates...")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        row = QHBoxLayout()

        close_btn = QPushButton("Close")
        self.download_btn = QPushButton("Download update")
        self.download_btn.setEnabled(False)

        row.addStretch()
        row.addWidget(close_btn)
        row.addWidget(self.download_btn)

        layout.addLayout(row)

        close_btn.clicked.connect(self.reject)
        self.download_btn.clicked.connect(self._download)

        self._check()

    def _check(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            data = fetch_manifest(
                UPDATE_PLATFORM,
                UPDATE_CHANNEL,
            )

            remote_version = data.get("version")

            if not remote_version:
                raise ValueError("No release is available.")

            self.manifest = data

            if not is_newer(remote_version, VERSION):
                self.info.setText(
                    f"TSM {VERSION} is up to date."
                )
                return

            notes = data.get(
                "release_notes",
                "No release notes available."
            )

            self.info.setText(
                f"New version: {remote_version}\n"
                f"Current version: {VERSION}\n\n"
                f"Release notes:\n{notes}"
            )

            self.download_btn.setEnabled(True)

        except Exception as exc:
            self.info.setText(
                f"Update check failed:\n{exc}"
            )

        finally:
            QApplication.restoreOverrideCursor()

    def _download(self):
        data = self.manifest or {}

        filename = f"Unity-{data.get('version', 'update')}.bin"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save TSM update",
            str(Path.home() / "Downloads" / filename),
            "TSM executable (*.bin)",
        )

        if not path:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            digest = download_verified(
                data.get("download_url"),
                data.get("sha256"),
                path,
            )

            os.chmod(path, 0o755)

            self.info.setText(
                f"Update downloaded successfully.\n\n"
                f"Location: {path}\n\n"
                f"SHA-256: {digest}\n\n"
                "Close TSM and replace your existing executable "
                "after backing it up."
            )

            QMessageBox.information(
                self,
                "Update verified",
                "Download completed and checksum verified."
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Update failed",
                str(exc),
            )

        finally:
            QApplication.restoreOverrideCursor()