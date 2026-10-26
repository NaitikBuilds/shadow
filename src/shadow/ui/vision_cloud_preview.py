"""Per-window preview and approval for cloud vision uploads."""

from enum import StrEnum

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class VisionCloudDecision(StrEnum):
    """Decision for a single interactive vision request."""

    SEND_TO_CLOUD = "send_to_cloud"
    USE_LOCAL = "use_local"
    CANCEL = "cancel"


class VisionCloudPreviewDialog(QDialog):
    """Preview a captured window before sending its image to the cloud."""

    def __init__(
        self,
        image_bytes: bytes,
        window_title: str,
        process_name: str,
        provider_name: str,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("SHADOW — Cloud Vision Preview")
        self.setModal(True)
        self.resize(620, 560)

        self.decision = VisionCloudDecision.CANCEL
        self.dont_ask_again = False

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Send this image to the cloud?</h2>")
        layout.addWidget(title)

        details = QLabel(
            f"<b>Window:</b> {window_title or 'Unknown window'}<br>"
            f"<b>Application:</b> {process_name or 'Unknown application'}<br>"
            f"<b>Provider:</b> {provider_name or 'Configured provider'}"
        )
        details.setWordWrap(True)
        layout.addWidget(details)

        warning = QLabel(
            "Approving sends the captured image to the selected cloud "
            "provider for analysis. The image is not intentionally saved "
            "by SHADOW. The provider may process it according to its "
            "own policies. You can use local vision instead."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b36b00;")
        layout.addWidget(warning)

        self.preview = QLabel()
        self.preview.setMinimumSize(320, 200)
        self.preview.setMaximumSize(580, 340)
        self.preview.setScaledContents(False)
        self.preview.setStyleSheet(
            "QLabel { background: #202020; border: 1px solid #555; }"
        )
        self.preview.setText("Preview unavailable")
        layout.addWidget(self.preview)

        # Decode directly from memory; never write the screenshot to disk.
        pixmap = QPixmap()
        if image_bytes and pixmap.loadFromData(image_bytes):
            self.preview.setPixmap(
                pixmap.scaled(
                    QSize(580, 340),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.remember_cb = QCheckBox(
            "Don't ask again for this application in this session"
        )
        self.remember_cb.setChecked(False)
        layout.addWidget(self.remember_cb)

        buttons = QHBoxLayout()

        send_btn = QPushButton("Send to cloud")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._send)
        buttons.addWidget(send_btn)

        local_btn = QPushButton("Use local instead")
        local_btn.clicked.connect(self._use_local)
        buttons.addWidget(local_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        layout.addLayout(buttons)

    def _send(self):
        self.decision = VisionCloudDecision.SEND_TO_CLOUD
        self.dont_ask_again = self.remember_cb.isChecked()
        self.accept()

    def _use_local(self):
        self.decision = VisionCloudDecision.USE_LOCAL
        self.accept()
