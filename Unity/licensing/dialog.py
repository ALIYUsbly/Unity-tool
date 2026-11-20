"""First-run and replacement-device licence activation dialog."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QApplication,
)

from Unity.licensing.client import save_key, validate


class ActivationDialog(QDialog):
    def __init__(self, parent=None, initial_key=""):
        super().__init__(parent)

        self.setWindowTitle("Activate TSM")
        self.setMinimumWidth(440)

        self.tier = None
        self.key = ""

        layout = QVBoxLayout(self)

        title = QLabel("Activate TSM")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Enter your TSM licence key. Activation requires an internet "
            "connection on first use. One licence is bound to one computer."
        ))

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("TSM-XXXXX-XXXXX-XXXXX")
        self.key_input.setText(initial_key)
        self.key_input.setClearButtonEnabled(True)
        layout.addWidget(self.key_input)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        row = QHBoxLayout()
        row.addStretch(1)

        self.cancel_btn = QPushButton("Exit")
        self.activate_btn = QPushButton("Activate")
        self.activate_btn.setDefault(True)

        row.addWidget(self.cancel_btn)
        row.addWidget(self.activate_btn)
        layout.addLayout(row)

        self.cancel_btn.clicked.connect(self.reject)
        self.activate_btn.clicked.connect(self._activate)
        self.key_input.returnPressed.connect(self._activate)

    def _activate(self):
        key = self.key_input.text().strip()

        if not key:
            self.status.setText("Enter your licence key.")
            return

        self.activate_btn.setEnabled(False)
        self.status.setText("Contacting licence server…")

        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            ok, tier, reason = validate(key)
        finally:
            QApplication.restoreOverrideCursor()
            self.activate_btn.setEnabled(True)

        if ok:
            save_key(key)
            self.key = key
            self.tier = tier
            self.accept()
            return

        if reason == "device_mismatch":
            msg = (
                "This licence is already activated on another computer. "
                "Contact the TSM administrator to reset its device binding."
            )
        elif reason == "expired":
            msg = "This licence has expired. Contact the TSM administrator."
        elif reason == "revoked":
            msg = "This licence has been revoked."
        elif str(reason).startswith("server_unreachable"):
            msg = (
                "Cannot reach the licence server and no valid offline "
                "activation is available. Check your internet connection."
            )
        else:
            msg = f"Activation failed: {reason}"

        self.status.setText(msg)