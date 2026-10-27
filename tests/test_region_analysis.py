"""Tests for SHADOW's region-analysis worker and text-only memory storage."""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QCoreApplication

from shadow.memory.images import ImageObservationStore
from shadow.perception.region_analysis import RegionAnalysisWorker


@pytest.fixture(scope="module")
def qcore_app():
    """Create a Qt application for QThread tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class FakeVisionService:
    """Fake vision service for deterministic worker tests."""

    def __init__(self, answer: str = "A sample answer"):
        self.answer = answer
        self.calls = []

    def analyze(self, image_bytes, task="caption", prompt="", **kwargs):
        self.calls.append(
            {
                "image_bytes": image_bytes,
                "task": task,
                "prompt": prompt,
                "kwargs": kwargs,
            }
        )
        return self.answer


class FakeVisionRouter:
    """Fake router exposing the interface used by the region worker."""

    def __init__(self, answer: str = "A sample answer"):
        self.answer = answer
        self.calls = []

    @property
    def local_service(self):
        """Match the router-detection convention used by ScreenVisionSource."""
        return object()

    def analyze(
        self,
        image_bytes,
        task="caption",
        prompt="",
        authorized=False,
        window_metadata=None,
        local_only=False,
    ):
        self.calls.append(
            {
                "image_bytes": image_bytes,
                "task": task,
                "prompt": prompt,
                "authorized": authorized,
                "window_metadata": window_metadata,
                "local_only": local_only,
            }
        )
        return self.answer


def run_worker(worker, qtbot):
    """Run a worker and wait for its completion."""
    results = {"success": [], "failure": []}
    worker.succeeded.connect(results["success"].append)
    worker.failed.connect(results["failure"].append)

    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()

    return results


def test_worker_sends_image_and_question_to_legacy_service(qcore_app, qtbot):
    service = FakeVisionService("This is a chart.")
    image_bytes = b"fake-image-bytes"

    worker = RegionAnalysisWorker(
        service,
        image_bytes,
        "Explain this chart",
    )
    results = run_worker(worker, qtbot)

    assert results["success"] == ["This is a chart."]
    assert results["failure"] == []
    assert len(service.calls) == 1
    assert service.calls[0]["image_bytes"] == image_bytes
    assert service.calls[0]["task"] == "query"
    assert service.calls[0]["prompt"] == "Explain this chart"


def test_worker_forwards_router_privacy_and_routing_options(qcore_app, qtbot):
    router = FakeVisionRouter()

    worker = RegionAnalysisWorker(
        router,
        b"fake-image-bytes",
        "Read the text",
        authorized=True,
        window_metadata={"title": "Notepad", "is_sensitive": False},
        local_only=True,
    )
    results = run_worker(worker, qtbot)

    assert results["success"] == ["A sample answer"]
    assert results["failure"] == []
    assert len(router.calls) == 1

    call = router.calls[0]
    assert call["task"] == "query"
    assert call["prompt"] == "Read the text"
    assert call["authorized"] is True
    assert call["local_only"] is True
    assert call["window_metadata"]["is_sensitive"] is False


def test_worker_rejects_empty_image(qcore_app, qtbot):
    service = FakeVisionService()

    worker = RegionAnalysisWorker(service, b"", "What is this?")
    results = run_worker(worker, qtbot)

    assert results["success"] == []
    assert len(results["failure"]) == 1
    assert "no image data" in results["failure"][0].lower()
    assert service.calls == []


def test_worker_rejects_empty_question(qcore_app, qtbot):
    service = FakeVisionService()

    worker = RegionAnalysisWorker(service, b"fake-image-bytes", "  ")
    results = run_worker(worker, qtbot)

    assert results["success"] == []
    assert len(results["failure"]) == 1
    assert "question" in results["failure"][0].lower()
    assert service.calls == []


def test_worker_reports_empty_model_answer(qcore_app, qtbot):
    service = FakeVisionService(answer="")

    worker = RegionAnalysisWorker(service, b"fake-image-bytes", "Describe this")
    results = run_worker(worker, qtbot)

    assert results["success"] == []
    assert len(results["failure"]) == 1
    assert "no answer" in results["failure"][0].lower()


def test_worker_reports_missing_vision_service(qcore_app, qtbot):
    worker = RegionAnalysisWorker(
        None,
        b"fake-image-bytes",
        "What is this?",
    )
    results = run_worker(worker, qtbot)

    assert results["success"] == []
    assert len(results["failure"]) == 1
    assert "no vision service" in results["failure"][0].lower()


class FakeMemory:
    """Minimal fake implementing the observation API used by the store."""

    def __init__(self):
        self.calls = []

    def add_observation(self, source, content, metadata=""):
        self.calls.append(
            {
                "source": source,
                "content": content,
                "metadata": metadata,
            }
        )
        return 123


def test_record_region_capture_saves_question_and_answer_only():
    memory = FakeMemory()
    store = ImageObservationStore(memory)

    observation_id = store.record_region_capture(
        question="Explain this diagram",
        answer="It shows a client-server architecture.",
        window_title="Diagram",
        process="notepad.exe",
    )

    assert observation_id == 123
    assert len(memory.calls) == 1

    row = memory.calls[0]
    assert row["source"] == "region_capture"
    assert "Explain this diagram" in row["content"]
    assert "client-server architecture" in row["content"]

    metadata = json.loads(row["metadata"])
    assert metadata["question"] == "Explain this diagram"
    assert metadata["answer"] == "It shows a client-server architecture."
    assert metadata["window_title"] == "Diagram"
    assert metadata["process"] == "notepad.exe"

    # No screenshot data should be persisted.
    assert "image_bytes" not in metadata
    assert "image_path" not in metadata
    assert "base64" not in metadata


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("", "An answer"),
        ("A question", ""),
        ("  ", "An answer"),
        ("A question", "  "),
    ],
)
def test_record_region_capture_rejects_empty_text(question, answer):
    memory = FakeMemory()
    store = ImageObservationStore(memory)

    result = store.record_region_capture(question, answer)

    assert result is None
    assert memory.calls == []


def test_record_region_capture_handles_memory_failure():
    class BrokenMemory:
        def add_observation(self, source, content, metadata=""):
            raise RuntimeError("database unavailable")

    store = ImageObservationStore(BrokenMemory())

    assert (
        store.record_region_capture(
            "What is this?",
            "A diagram",
        )
        is None
    )
