"""TSM application startup with licence activation."""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

from PySide6.QtWidgets import QApplication

from Unity.licensing.client import require_license
from Unity.licensing.dialog import ActivationDialog
from Unity.theme import QSS
from Unity.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)

    # Verify activation before opening the main TSM window.
    ok, tier, reason = require_license()

    if not ok:
        dialog = ActivationDialog(initial_key="")

        if dialog.exec() != ActivationDialog.Accepted:
            return 0

        tier = dialog.tier

    win = MainWindow()
    win.license_tier = tier
    
    win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())