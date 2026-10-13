import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    file = Path(__file__).resolve()
    package_root = file.parents[3]
    sys.path.append(str(package_root))
    __package__ = "frontend.app.views"

from PySide6.QtWidgets import (
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QLabel,
    QListWidget,
    QHBoxLayout,
    QStyle,
    QApplication,
    QDialog,
    QInputDialog,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import QTimer

from app.core.api_client import ApiClient
from app.core.ws_client import WebSocketClient
from app.core.settings import Settings

# from app.core.version import get_version

from app.views.visitor.visitor_details_dialog import VisitorDetailsDialog
from app.views.visitor.create_visitor_dialog import CreateVisitorDialog
from .connection_dialog import ConnectionDialog
from app.views.search.search_dialog import SearchDialog

# from search.search_result_dialog import SearchResultDialog
from app.views.common.warning_dialog import show_critical_disconnection_warning
from app.utils.log import Log


class MainWindow(QMainWindow):
    def __init__(self, appName="Kav 1"):
        super().__init__()
        self.logger = Log()

        self.ask_for_connection()

        self.setup_ui(appName)
        self.setup_clients()
        self.connect_signals()

        QTimer.singleShot(1000, self.force_sync)

    def setup_ui(self, appName):
        self.setWindowTitle(appName)
        self.setMinimumSize(800, 600)
        self.setGeometry(100, 100, 800, 600)

        # self.log = QTextEdit()
        # self.log.setReadOnly(True)

        self.ws_status_label = QLabel("Disconnected")
        self.ws_status_label.setObjectName("ws_status_label")
        # self.client_version = QLabel(f"Version Hash: {get_version()}")

        self.search_button = QPushButton("Search Visitors")
        self.search_button.setIcon(
            self.style().standardIcon(QStyle.SP_FileDialogContentsView)
        )
        self.create_button = QPushButton("Add Visitor")
        self.create_button.setIcon(self.style().standardIcon(QStyle.SP_CommandLink))
        self.sync_button = QPushButton("Force Sync")
        self.sync_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.logs_button = QPushButton("Show Logs")

        button_height = 40
        self.logs_button.setFixedHeight(button_height)
        self.sync_button.setFixedHeight(button_height)
        self.search_button.setFixedHeight(button_height)
        self.create_button.setFixedHeight(button_height)

        font = QFont()
        font.setPointSize(13)
        self.visitors_list = QListWidget(self)
        self.visitors_list.setFont(font)
        self.visitors_list.setAlternatingRowColors(True)
        self.visitors_list.setSelectionMode(QListWidget.SingleSelection)
        self.visitors_list.setMinimumHeight(300)

        self.visitors_list.clicked.connect(self.on_visitor_clicked)

        # self.log.setStyleSheet("background-color: #1c1c1c; color: #dcdcdc;")

        layout = QVBoxLayout()

        layout.addWidget(self.ws_status_label)
        # layout.addWidget(self.client_version)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.logs_button)
        button_layout.addWidget(self.sync_button)
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.create_button)

        layout.addLayout(button_layout)

        layout.addWidget(QLabel("Visitors Inside:"))
        layout.addWidget(self.visitors_list)
        # layout.addWidget(self.log)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def setup_clients(self):
        self.ws_client = WebSocketClient()
        self.api_client = ApiClient.get_instance()
        self.ws_client.connect(Settings.get_ws_url())

    def connect_signals(self):
        # Clear existing connections
        self.api_client.response_received.disconnect()
        self.ws_client.message_received.disconnect()

        # Set up new connections
        self.ws_client.message_received.connect(self.handle_ws_message)
        self.ws_client.connected.connect(self.handle_connect)
        self.ws_client.disconnected.connect(self.handle_disconnect)

        # Connect buttons
        self.logs_button.clicked.connect(self.open_logs_dialog)

        # Default API response handler
        self.api_client.response_received.connect(self.handle_api_response)
        self.api_client.error_occurred.connect(self.log_error)

        # Button connections
        self.search_button.clicked.connect(self.open_search_dialog)
        self.sync_button.clicked.connect(self.force_sync)
        self.create_button.clicked.connect(self.add_visitor_dialog)

    def handle_ws_message(self, message: str):
        self.logger.write_to_log(message)
        if "sync" in message.lower():
            self.api_client.response_received.disconnect()
            self.api_client.response_received.connect(self.handle_get_visitors)
            self.api_client.get_visitors_inside()

    def handle_api_response(self, response: dict):
        self.logger.write_to_log(f"API Response Type: {type(response)}")
        self.logger.write_to_log(f"API Response Content: {str(response)}")

        if response and isinstance(response, dict) and "visitor" in response:
            # This is a single visitor response
            self.api_client.response_received.disconnect()
            self.api_client.response_received.connect(self.handle_get_visitors)
            self.api_client.get_visitors_inside()
        elif response and isinstance(response, list):
            # This is a list of visitors, update the list directly
            self.update_visitors_list(response)

    def log_error(self, error: str):
        self.logger.write_to_log(f"Error: {error}")

    def force_sync(self):
        self.logger.write_to_log("Manual sync initiated...")
        try:
            # Temporarily connect the specific handler
            self.api_client.response_received.disconnect()
            self.api_client.response_received.connect(self.handle_get_visitors)
            self.api_client.get_visitors_inside()
        except Exception as e:
            self.log_error(f"Sync failed: {str(e)}")
            # Restore default handler
            self.api_client.response_received.disconnect()
            self.api_client.response_received.connect(self.handle_api_response)

    def open_search_dialog(self):
        dialog = SearchDialog()
        dialog.exec()

    def add_visitor_dialog(self):
        dialog = CreateVisitorDialog()
        dialog.exec()

    def handle_get_visitors(self, response):
        try:
            if response and isinstance(response, list):
                self.logger.write_to_log(f"Visitor list received: {response}")
                self.update_visitors_list(response)
            else:
                self.logger.write_to_log("handle_get_visitors: response was not a list")
        except Exception as e:
            self.logger.write_to_log(f"Exception in handle_get_visitors: {e}")

    def update_visitors_list(self, visitors):
        """Update the visitors list with those currently inside."""
        try:
            self.visitors_list.clear()
            if visitors and isinstance(visitors, list):  # More explicit check
                for visitor in visitors:
                    if (
                        isinstance(visitor, dict)
                        and "visitorid" in visitor
                        and "name" in visitor
                    ):
                        display_name = f"{visitor['visitorid']} - {visitor['name']}"
                        self.visitors_list.addItem(display_name)
        except Exception as e:
            self.log_error(f"Error updating visitors list: {str(e)}")

    def on_visitor_clicked(self):
        """Handle visitor item click."""
        selected_item = self.visitors_list.currentItem()
        if selected_item:
            visitor_id = selected_item.text().split(" - ")[0]
            self.show_visitor_details(visitor_id)

    def show_visitor_details(self, visitor_id):
        """Show visitor details in a new dialog."""
        self.api_client.response_received.disconnect()
        self.api_client.response_received.connect(self.handle_visitor_details)
        self.api_client.get_visitor_by_id(visitor_id)

    def handle_visitor_details(self, results):
        """Handle the visitor details response."""
        if results and "visitor" in results:
            visitor_details_dialog = VisitorDetailsDialog(results["visitor"], self)
            if visitor_details_dialog.exec() == QDialog.Accepted:
                # When dialog is accepted (after status change or deletion)
                self.api_client.get_visitors_inside()

    def ask_for_connection(self):
        """Show connection configuration dialog"""
        dialog = ConnectionDialog()
        if dialog.exec():
            address = dialog.get_address()
            if address:
                Settings.set_url(address)
                self.logger.write_to_log(f"Connection set to: {address}")
        else:
            self.logger.write_to_log("Connection configuration cancelled")

    def handle_connect(self):
        msg = f"Connected to {Settings.get_base_url()}"
        self.logger.write_to_log(msg)
        self.ws_status_label.setText(msg)
        # Remove disconnected styling
        self.ws_status_label.setProperty("disconnected", False)
        self.ws_status_label.style().unpolish(self.ws_status_label)
        self.ws_status_label.style().polish(self.ws_status_label)

    def handle_disconnect(self):
        message = "⚠️ CONNECTION LOST - Server Disconnected"
        self.logger.write_to_log(message)
        self.ws_status_label.setText(message)
        # Apply disconnected styling
        self.ws_status_label.setProperty("disconnected", True)
        self.ws_status_label.style().unpolish(self.ws_status_label)
        self.ws_status_label.style().polish(self.ws_status_label)

        # Show prominent, un-hideable warning dialog
        self.show_disconnection_dialog()

    def show_disconnection_dialog(self):
        """Show a critical disconnection warning dialog."""
        try:
            show_critical_disconnection_warning(
                "Connection Lost", "The server connection has been lost.", parent=self
            )
        except Exception as e:
            self.logger.write_to_log(f"Error showing disconnection dialog: {str(e)}")
        finally:
            self.close()
            QApplication.quit()

    def open_logs_dialog(self):
        try:
            self.api_client.response_received.disconnect()
        except TypeError:
            pass

        limit, ok = QInputDialog.getInt(
            self, "Logs Limit", "Enter the number of logs to retrieve:", 50, 1, 1000
        )

        if ok:
            self.api_client.response_received.connect(self.handle_logs_response)
            self.api_client.get_logs(limit=limit)

    def handle_logs_response(self, logs):
        from app.views.logs.logs_dialog import LogsDialog

        dialog = LogsDialog(logs, self)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
