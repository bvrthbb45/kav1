from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QLabel
from datetime import datetime
from app.views.common.warning_dialog import show_warning


class LogsDialog(QDialog):
    def __init__(self, logs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.setMinimumSize(500, 400)

        if not isinstance(logs, list):
            message = logs.get("message", "No logs available")
            show_warning(
                "No Logs Found",
                "Could not retrieve logs for this visitor.\n\n"
                "Possible reasons:\n"
                "✓ Visitor has no recorded logs\n"
                "✓ Visitor was created before build bf46edd — visitor creation date may be missing\n\n"
                "Technical details:\n"
                f"• {message}",
            )
        else:
            layout = QVBoxLayout()
            self.logs_list = QListWidget()

            for log in logs:
                ts = datetime.fromisoformat(log["timestamp"])
                formatted = ts.strftime("%H:%M:%S %d/%m/%Y")
                entry = f"{formatted} - {log['visitor_dbid']} - {log['visitor_name']} - {log['action']}"
                self.logs_list.addItem(entry)

            layout.addWidget(QLabel("Recent Logs:"))
            layout.addWidget(self.logs_list)
            self.setLayout(layout)
