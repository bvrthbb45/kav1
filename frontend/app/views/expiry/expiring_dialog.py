from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core import fields
from app.core.api_client import ApiClient

TAG = "expiring_dialog"
COLUMNS = ["Visitor ID", "Name", "Project", "Expiry of", "Date", "Days left", "Inside"]
RED = QColor("#b00020")
ORANGE = QColor("#b36b00")


class ExpiringDialog(QDialog):
    """Visitors whose classification / security approval is expired or about
    to expire, soonest first."""

    def __init__(self, days=fields.DEFAULT_WARN_DAYS, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Expiring approvals")
        self.setMinimumSize(760, 420)
        self.api_client = ApiClient.get_instance()

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Expiring within (days):"))
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setValue(days)
        top.addWidget(self.days)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load)
        top.addWidget(refresh)
        top.addStretch()
        layout.addLayout(top)

        self.summary = QLabel("")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

        self.api_client.tagged_response.connect(self.on_response)
        self.finished.connect(
            lambda _=None: self.api_client.tagged_response.disconnect(self.on_response)
        )
        self.days.valueChanged.connect(lambda _=None: self.load())
        self.load()

    def load(self):
        self.api_client.get_expiring(self.days.value(), tag=TAG)

    def on_response(self, tag, rows):
        if tag != TAG or not isinstance(rows, list):
            return
        self.table.setRowCount(len(rows))
        expired = 0
        for r, row in enumerate(rows):
            info = row["expiry"]
            is_expired = info["status"] == "expired"
            expired += is_expired
            left = info["days_left"]
            values = [
                row["visitorid"],
                row["name"],
                row.get("project") or "",
                info["field"],
                info["date"],
                "EXPIRED (%d days ago)" % -left if is_expired else str(left),
                "yes" if row["inside"] else "no",
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setForeground(QBrush(RED if is_expired else ORANGE))
                if c == 5:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
        self.summary.setText(
            "%d expired, %d expiring within %d days"
            % (expired, len(rows) - expired, self.days.value())
        )
