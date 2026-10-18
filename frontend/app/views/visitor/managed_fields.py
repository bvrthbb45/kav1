"""Form section for the properties the application understands:
project, information-security approval and the two validity dates."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from app.core import fields

NOT_SET = ""  # first combo item: nothing chosen yet


def _parse_date(text):
    parsed = fields.parse_date(text)
    return QDate(parsed.year, parsed.month, parsed.day) if parsed else None


class OptionalDate(QWidget):
    """A checkbox plus a calendar date; unchecked means 'no date'."""

    def __init__(self, check_text):
        super().__init__()
        self.check = QCheckBox(check_text)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setEnabled(False)
        self.check.toggled.connect(self.date.setEnabled)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.check)
        row.addWidget(self.date)
        row.addStretch()

    def set_enabled_by_rule(self, allowed):
        self.check.setEnabled(allowed)
        if not allowed:
            self.check.setChecked(False)

    def value(self):
        return (
            self.date.date().toString("yyyy-MM-dd") if self.check.isChecked() else None
        )

    def set_value(self, text):
        d = _parse_date(text) if text not in (None, "") else None
        if d is None:
            self.check.setChecked(False)
            return False
        self.date.setDate(d)
        self.check.setChecked(True)
        return True


class ManagedFields(QWidget):
    """Project, infosec status (+ expiry) and classification expiry."""

    def __init__(self, require_infosec=False, parent=None):
        super().__init__(parent)
        self.require_infosec = require_infosec
        self._project_key = fields.PROJECT_KEY
        self._infosec_expiry_key = fields.INFOSEC_EXPIRY_KEY
        self._classification_key = fields.CLASSIFICATION_EXPIRY_KEY
        self._infosec_was_set = False
        self._legacy_expiry = {}  # unparseable old text, kept so it is not lost

        self.project = QLineEdit()
        self.project.setPlaceholderText("e.g. נבו")

        self.infosec = QComboBox()
        self.infosec.addItem("— choose —", NOT_SET)
        for option in fields.INFOSEC_OPTIONS:
            self.infosec.addItem(option, option)
        self.infosec_expiry = OptionalDate("Approval valid until")
        self.classification_expiry = OptionalDate("Has classification expiry")

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(QLabel("Project:"), self.project)
        form.addRow(QLabel("Information security:"), self.infosec)
        form.addRow(QLabel("Security approval expiry:"), self.infosec_expiry)
        form.addRow(QLabel("Classification expiry:"), self.classification_expiry)

        self.infosec.currentIndexChanged.connect(self._on_infosec_changed)
        self._on_infosec_changed()

    @staticmethod
    def managed_keys(properties):
        """Keys of `properties` this widget edits (so generic editors skip them)."""
        keys = {
            fields.INFOSEC_KEY,
            fields.INFOSEC_EXPIRY_KEY,
            fields.CLASSIFICATION_EXPIRY_KEY,
        }
        for aliases in (
            fields.INFOSEC_EXPIRY_ALIASES,
            fields.CLASSIFICATION_EXPIRY_ALIASES,
        ):
            found = fields.find_key(properties, aliases)
            if found is not None:
                keys.add(found)
        project_key = fields.find_key(properties, fields.PROJECT_ALIASES)
        if project_key is not None:
            keys.add(project_key)
        return keys

    def _on_infosec_changed(self):
        approved = self.infosec.currentData() in (
            fields.INFOSEC_APPROVED,
            fields.INFOSEC_EXCEPTION,
        )
        self.infosec_expiry.set_enabled_by_rule(approved)
        if approved and self._infosec_expiry_key not in self._legacy_expiry:
            self.infosec_expiry.check.setChecked(True)  # every approval needs one

    def set_values(self, properties):
        properties = properties or {}
        key = fields.find_key(properties, fields.PROJECT_ALIASES)
        self._project_key = key if key is not None else fields.PROJECT_KEY
        self.project.setText(str(properties.get(self._project_key, "") or ""))

        status = properties.get(fields.INFOSEC_KEY, NOT_SET)
        self._infosec_was_set = status not in (None, NOT_SET)
        index = self.infosec.findData(status)
        self.infosec.setCurrentIndex(index if index >= 0 else 0)

        key = fields.find_key(properties, fields.INFOSEC_EXPIRY_ALIASES)
        self._infosec_expiry_key = key if key is not None else fields.INFOSEC_EXPIRY_KEY
        key = fields.find_key(properties, fields.CLASSIFICATION_EXPIRY_ALIASES)
        self._classification_key = (
            key if key is not None else fields.CLASSIFICATION_EXPIRY_KEY
        )
        # Dates nobody can read (old free text) are kept as typed, not dropped.
        self._legacy_expiry = {}
        for key in (self._infosec_expiry_key, self._classification_key):
            raw = properties.get(key)
            if raw not in (None, "") and _parse_date(raw) is None:
                self._legacy_expiry[key] = raw
        self.infosec_expiry.set_value(properties.get(self._infosec_expiry_key))
        self._on_infosec_changed()
        if not self.infosec_expiry.check.isChecked():
            self.infosec_expiry.set_value(properties.get(self._infosec_expiry_key))
        self.classification_expiry.set_value(properties.get(self._classification_key))

    def validate(self):
        """Error text for the operator, or None when the section is valid."""
        status = self.infosec.currentData()
        if status == NOT_SET and (self.require_infosec or self._infosec_was_set):
            return "Please choose the information-security status."
        if status in (fields.INFOSEC_APPROVED, fields.INFOSEC_EXCEPTION):
            if (
                self.infosec_expiry.value() is None
                and self._infosec_expiry_key not in self._legacy_expiry
            ):
                return "An approved status needs an approval expiry date."
        return None

    def get_properties(self):
        """The managed keys to merge into the visitor's properties."""
        props = {}
        project = self.project.text().strip()
        if project:
            props[self._project_key] = project
        status = self.infosec.currentData()
        if status != NOT_SET:
            props[fields.INFOSEC_KEY] = status
            expiry = self.infosec_expiry.value()
            if expiry and status != fields.INFOSEC_DENIED:
                props[self._infosec_expiry_key] = expiry
        classification = self.classification_expiry.value()
        if classification:
            props[self._classification_key] = classification
        for key, raw in self._legacy_expiry.items():
            props.setdefault(key, raw)  # the server will ask the operator to fix it
        return props
