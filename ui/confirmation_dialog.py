"""Native desktop confirmation dialog (QMessageBox, not an HTML popup)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QWidget

from core import config


def confirm_sensitive(kind: str, name: str, parent: QWidget | None = None) -> bool:
    """Ask the user whether to proceed. Returns True for Continue, False for Cancel.

    kind: 'prompt' or 'file'
    name: file name, or a snippet of the prompt
    """
    is_file = kind == "file"
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Sensitive content detected")
    box.setWindowModality(Qt.WindowModality.ApplicationModal)
    box.setText(
        f"Sensitive content ({config.SENSITIVE_MARKER}) was detected in "
        + ("a file." if is_file else "a text prompt.")
    )
    box.setInformativeText(
        ("File: " if is_file else "Prompt: ") + name + "\n\nDo you want to continue?"
    )
    continue_btn = box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
    cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn)  # safe default
    box.setEscapeButton(cancel_btn)
    box.raise_()
    box.activateWindow()
    box.exec()
    return box.clickedButton() is continue_btn
