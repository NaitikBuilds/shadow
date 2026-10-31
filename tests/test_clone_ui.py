"""Tests for C11: clone UI + simulation labeling."""

from __future__ import annotations

import pytest

from shadow.agent.shadow_cloning import CloneManager
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


class FakeBackend:
    def __init__(self, reply: str = "simulated reply") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def generate(self, prompt, **kw):
        self.calls.append({"prompt": prompt, **kw})
        return self.reply


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def manager(memory):
    return CloneManager(memory, config={"clone_max_concurrent": 2})


@pytest.fixture
def session(manager):
    return manager.create(
        "test",
        {"time_range": {"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}},
    )


# --- generate_reply ---
def test_generate_reply_adds_message_and_artifact(session):
    backend = FakeBackend("simulated output")
    art = session.generate_reply(backend, "what if I quit?")
    assert art["label"] == "simulation"
    assert art["text"] == "simulated output"
    msgs = session.list_messages()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_generate_reply_rejects_empty(session):
    with pytest.raises(ValueError):
        session.generate_reply(FakeBackend(), "  ")


def test_generate_reply_handles_backend_error(session):
    class Boom:
        def generate(self, p, **kw):
            raise RuntimeError("boom")

    art = session.generate_reply(Boom(), "x")
    assert "generation failed" in art["text"]


# --- feed ---
def test_feed_interleaves_in_order(session):
    backend = FakeBackend("out1")
    session.generate_reply(backend, "q1")
    session.generate_reply(backend, "q2")
    feed = session.feed()
    assert len(feed) == 4
    kinds = [i["kind"] for i in feed]
    assert kinds.count("message") == 2
    assert kinds.count("artifact") == 2


def test_feed_empty(session):
    assert session.feed() == []


# --- Qt dialogs ---
def test_create_dialog_constructs(manager, qtbot):
    from shadow.ui.clone_create_dialog import CloneCreateDialog

    dlg = CloneCreateDialog(manager)
    qtbot.addWidget(dlg)
    assert dlg._name is not None


def test_create_dialog_rejects_invalid_date(manager, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from shadow.ui.clone_create_dialog import CloneCreateDialog

    dlg = CloneCreateDialog(manager)
    qtbot.addWidget(dlg)
    dlg._name.setText("x")
    dlg._start.setText("not-a-date")
    warns: list = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warns.append(a))
    dlg._on_create()
    assert warns
    assert dlg.created_session() is None


def test_create_dialog_creates_session(manager, qtbot):
    from shadow.ui.clone_create_dialog import CloneCreateDialog

    dlg = CloneCreateDialog(manager)
    qtbot.addWidget(dlg)
    dlg._name.setText("ui-test")
    dlg._start.setText("2026-01-01 00:00:00")
    dlg._end.setText("2026-12-31 23:59:59")
    dlg._on_create()
    assert dlg.created_session() is not None
    assert dlg.created_session().name == "ui-test"


def test_chat_dialog_banner_visible(session, qtbot):
    from shadow.ui.clone_chat_dialog import CloneChatDialog

    dlg = CloneChatDialog(session, FakeBackend())
    qtbot.addWidget(dlg)
    assert "SIMULATION" in dlg._banner.text()


def test_chat_dialog_copy_includes_label(session, qtbot):
    from PySide6.QtWidgets import QApplication

    from shadow.ui.clone_chat_dialog import CloneChatDialog

    backend = FakeBackend("result text")
    dlg = CloneChatDialog(session, backend)
    qtbot.addWidget(dlg)
    art = session.generate_reply(backend, "q")
    dlg._render()
    dlg._selected_artifact = art
    dlg._on_copy()
    clip = QApplication.clipboard().text()
    assert "SIMULATION" in clip
    assert "result text" in clip


def test_list_dialog_empty_state(manager, qtbot):
    from shadow.ui.clone_list_dialog import CloneListDialog

    dlg = CloneListDialog(manager, FakeBackend())
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 1
    assert not dlg._open_btn.isEnabled()


def test_list_dialog_shows_active_clone(manager, qtbot):
    from shadow.ui.clone_list_dialog import CloneListDialog

    manager.create("seed", {"time_range": {"start": "2026-01-01 00:00:00"}})
    dlg = CloneListDialog(manager, FakeBackend())
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 1
    assert dlg._open_btn.isEnabled()
