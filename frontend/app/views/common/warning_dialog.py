from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


def show_warning(message: str, detail: str, icon=QMessageBox.Warning, parent=None):
    msg = QMessageBox(parent)
    msg.setIcon(icon)
    msg.setWindowTitle(message)
    msg.setText(detail)
    msg.setStandardButtons(QMessageBox.Ok)

    msg.setWindowFlags(
        Qt.WindowStaysOnTopHint
        | Qt.Dialog
        | Qt.CustomizeWindowHint
        | Qt.WindowTitleHint
    )
    msg.setWindowModality(Qt.ApplicationModal)

    msg.setModal(True)
    msg.activateWindow()
    msg.raise_()

    msg.setWindowFlag(Qt.WindowCloseButtonHint, False)

    return msg.exec()


def show_critical_disconnection_warning(message: str, detail: str, parent=None):
    """Show a highly prominent disconnection warning that cannot be ignored"""
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle(f"🔴 {message}")
    msg.setText(f"❌ {detail}")
    msg.setStandardButtons(QMessageBox.Ok)
    
    # Make it extremely prominent and un-hideable
    msg.setWindowFlags(
        Qt.WindowStaysOnTopHint |
        Qt.Dialog |
        Qt.CustomizeWindowHint |
        Qt.WindowTitleHint |
        Qt.WindowSystemMenuHint
    )
    msg.setWindowModality(Qt.ApplicationModal)
    msg.setModal(True)
    
    # Remove close button completely
    msg.setWindowFlag(Qt.WindowCloseButtonHint, False)
    
    # Make font bold and larger
    font = QFont()
    font.setPointSize(12)
    font.setWeight(QFont.Bold)
    msg.setFont(font)
    
    # Force it to be visible and on top
    msg.activateWindow()
    msg.raise_()
    msg.setFocus()
    
    return msg.exec()
