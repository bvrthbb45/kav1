import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    file = Path(__file__).resolve()
    package_root = file.parents[3]
    sys.path.append(str(package_root))
    __package__ = "frontend.app.views"

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QApplication,
    QCheckBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from app.core.api_client import ApiClient
from app.views.common.warning_dialog import show_warning


class EditVisitorDialog(QDialog):
    def __init__(self, visitor_data, parent=None):
        super().__init__(parent)
        self.visitor_data = visitor_data
        self.api_client = ApiClient.get_instance()
        self.api_client.error_occurred.connect(self.on_error)

        self.setWindowTitle("Edit Visitor")
        self.setMinimumSize(500, 600)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        basic_frame = QFrame()
        basic_frame.setFrameShape(QFrame.StyledPanel)
        basic_layout = QVBoxLayout(basic_frame)
        basic_layout.setContentsMargins(12, 12, 12, 12)

        name_layout = QHBoxLayout()
        name_label = QLabel("Name:")
        self.name_input = QLineEdit()
        self.name_input.setText(self.visitor_data["name"])
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        basic_layout.addLayout(name_layout)

        id_layout = QHBoxLayout()
        id_label = QLabel("Visitor ID:")
        self.id_input = QLineEdit()
        self.id_input.setText(self.visitor_data["visitorid"])
        id_layout.addWidget(id_label)
        id_layout.addWidget(self.id_input)
        basic_layout.addLayout(id_layout)

        layout.addWidget(basic_frame)

        properties_frame = QFrame()
        properties_frame.setFrameShape(QFrame.StyledPanel)
        properties_layout = QVBoxLayout(properties_frame)
        properties_layout.setContentsMargins(12, 12, 12, 12)

        properties_title = QLabel("Properties")
        properties_title.setAlignment(Qt.AlignCenter)
        font = properties_title.font()
        font.setBold(True)
        font.setPointSize(12)
        properties_title.setFont(font)
        properties_layout.addWidget(properties_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.properties_layout = QVBoxLayout(scroll_content)
        self.properties_layout.setContentsMargins(8, 8, 8, 8)
        self.properties_layout.setSpacing(8)

        self.property_inputs = {}
        for key, value in self.visitor_data.get("properties", {}).items():
            self.add_property_field(key, value)

        scroll.setWidget(scroll_content)
        properties_layout.addWidget(scroll)

        add_property_btn = QPushButton("Add Property")
        add_property_btn.clicked.connect(lambda: self.add_property_field())
        properties_layout.addWidget(add_property_btn)

        layout.addWidget(properties_frame)

        button_layout = QHBoxLayout()

        save_btn = QPushButton("Save Changes")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.save_changes)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def add_property_field(self, key="", value=""):
        field_layout = QHBoxLayout()

        key_input = QLineEdit()
        key_input.setPlaceholderText("Property Name")
        key_input.setText(key)

        value_input = QLineEdit()
        value_input.setPlaceholderText("Value")
        value_input.setText(str(value))

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(30)
        remove_btn.clicked.connect(lambda: self.remove_property_field(field_layout))

        field_layout.addWidget(key_input)
        field_layout.addWidget(value_input)
        field_layout.addWidget(remove_btn)

        container = QWidget()
        container.setLayout(field_layout)
        self.properties_layout.addWidget(container)

        field_layout.setProperty("container", container)

    def remove_property_field(self, field_layout):
        container = field_layout.property("container")
        if container:
            container.deleteLater()

    def save_changes(self):
        name = self.name_input.text().strip()
        visitorid = self.id_input.text().strip()

        if not name or not visitorid:
            show_warning(
                "Missing Information", "Both name and visitor ID are required fields."
            )
            return

        properties = {}
        for i in range(self.properties_layout.count()):
            container = self.properties_layout.itemAt(i).widget()
            if container:
                field_layout = container.layout()
                key_input = field_layout.itemAt(0).widget()
                value_input = field_layout.itemAt(1).widget()

                key = key_input.text().strip()
                value = value_input.text().strip()

                if key:
                    properties[key] = value

        update_data = {}
        if name != self.visitor_data["name"]:
            update_data["name"] = name
        if visitorid != self.visitor_data["visitorid"]:
            update_data["visitorid"] = visitorid
        if properties != self.visitor_data.get("properties", {}):
            update_data["properties"] = properties

        if update_data:
            confirm_dialog = QDialog(self)
            confirm_dialog.setWindowTitle("Confirm Changes")

            layout = QVBoxLayout(confirm_dialog)

            message = QLabel("Are you sure you want to save these changes?")
            layout.addWidget(message)

            checkbox = QCheckBox("I confirm these changes are correct")
            layout.addWidget(checkbox)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            ok_button = buttons.button(QDialogButtonBox.Ok)
            ok_button.setEnabled(False)

            checkbox.stateChanged.connect(
                lambda state: ok_button.setEnabled(state == 2)  # Qt.Checked is 2
            )

            buttons.accepted.connect(confirm_dialog.accept)
            buttons.rejected.connect(confirm_dialog.reject)
            layout.addWidget(buttons)

            if confirm_dialog.exec() == QDialog.Accepted:
                self.api_client.response_received.disconnect()
                self.api_client.response_received.connect(self.on_update_success)
                self.api_client.update_visitor(
                    self.visitor_data["visitorid"], update_data
                )
        else:
            self.reject()

    def on_update_success(self, response):
        if response and "visitor" in response:
            self.api_client.response_received.disconnect(self.on_update_success)
            self.accept()
            if self.parent():
                self.parent().accept()

    def on_error(self, error_message):
        self.api_client.response_received.disconnect(self.on_update_success)
        show_warning("Error", error_message)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    test_visitor = {
        "name": "John Doe",
        "visitorid": "V12345",
        "inside": True,
        "properties": {"Company": "Acme Inc", "Badge": "B123", "Purpose": "Meeting"},
    }

    dialog = EditVisitorDialog(test_visitor)
    dialog.show()
    sys.exit(app.exec())
