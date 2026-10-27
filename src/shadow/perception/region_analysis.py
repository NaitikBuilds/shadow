"""Background worker for analyzing a user-selected screen region."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class RegionAnalysisWorker(QThread):
    """Analyze a cropped region without blocking the Qt UI thread."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        vision_service,
        image_bytes: bytes,
        question: str,
        *,
        authorized: bool = False,
        window_metadata: dict | None = None,
        local_only: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._vision_service = vision_service
        self._image_bytes = image_bytes
        self._question = question.strip()
        self._authorized = authorized
        self._window_metadata = dict(window_metadata or {})
        self._local_only = local_only

    def run(self) -> None:
        """Run one image-analysis request and report its result."""
        try:
            if not self._image_bytes:
                raise ValueError("The selected region contains no image data.")

            if not self._question:
                raise ValueError("Please enter a question about the selected region.")

            if self.isInterruptionRequested():
                return

            service = self._vision_service
            if service is None:
                raise RuntimeError("No vision service is configured.")

            # VisionRouter supports cloud/local routing. VisionService accepts
            # extra keyword arguments and forwards them to its backend.
            if hasattr(service, "local_service"):
                answer = service.analyze(
                    self._image_bytes,
                    task="query",
                    prompt=self._question,
                    authorized=self._authorized,
                    window_metadata=self._window_metadata,
                    local_only=self._local_only,
                )
            else:
                # Preserve compatibility with the existing local VisionService.
                answer = service.analyze(
                    self._image_bytes,
                    task="query",
                    prompt=self._question,
                )

            if self.isInterruptionRequested():
                return

            answer = answer.strip() if answer else ""
            if not answer:
                raise RuntimeError(
                    "The vision service returned no answer. "
                    "Check model availability and provider configuration."
                )

            self.succeeded.emit(answer)

        except Exception as exc:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
