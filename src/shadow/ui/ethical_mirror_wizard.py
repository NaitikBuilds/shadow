"""Ethical Mirror onboarding wizard (C08).

Ten-prompt wizard with:
  - resume at the first unanswered prompt (each answer is persisted
    immediately with onboarding_prompt_id set)
  - Skip enabled after ≥3 answers (limited-profile per DR-P4-03)
  - Close (X) increments a dismiss counter; wizard re-offers on next
    launch until 3 dismissals or onboarded
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from shadow.agent.ethical_mirror import (
    ONBOARDING_PROMPTS,
    EthicalValueDuplicateError,
    EthicalValuesStore,
    EthicalValueValidationError,
    answered_prompt_count,
    next_unanswered_prompt_index,
)

# DR-P4-03 spec baseline: allow early exit after at least 3 values.
EARLY_EXIT_MIN = 3


class EthicalMirrorWizard(QDialog):
    """10-prompt wizard. Modal, cancellable, resumable."""

    def __init__(self, memory, parent=None) -> None:
        super().__init__(parent)
        self._store = EthicalValuesStore(memory)
        self._step_index: int | None = next_unanswered_prompt_index(self._store)
        self._completed = False

        self.setWindowTitle("SHADOW — Set up your Ethical Mirror")
        self.setModal(True)
        self.resize(560, 420)
        self._build_ui()

        if self._step_index is None:
            # All prompts already answered — nothing to do.
            self._completed = True
            self._store.mark_onboarded()
            self.accept()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._step_label = QLabel(self)
        self._step_label.setStyleSheet("color: #888;")
        root.addWidget(self._step_label)

        self._prompt_label = QLabel(self)
        self._prompt_label.setWordWrap(True)
        self._prompt_label.setStyleSheet(
            "font-size: 15px; font-weight: 600; padding: 8px 0;"
        )
        root.addWidget(self._prompt_label)

        self._hint_label = QLabel(
            "Answer in your own words. Values are stored locally and can be "
            "edited or deleted anytime. This is advisory only — SHADOW will "
            "never judge or block actions based on your values.",
            self,
        )
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._hint_label)

        self._input = QTextEdit(self)
        self._input.setPlaceholderText("Your value (1–300 characters)")
        self._input.setTabChangesFocus(True)
        root.addWidget(self._input, 1)

        self._char_count = QLabel("0 / 300", self)
        self._char_count.setAlignment(Qt.AlignRight)
        self._char_count.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._char_count)
        self._input.textChanged.connect(self._on_text_changed)

        buttons = QHBoxLayout()
        self._skip_btn = QPushButton("Skip (limited profile)", self)
        self._skip_btn.setEnabled(answered_prompt_count(self._store) >= EARLY_EXIT_MIN)
        self._skip_btn.clicked.connect(self._on_skip)
        buttons.addWidget(self._skip_btn)

        buttons.addStretch(1)

        self._cancel_btn = QPushButton("Not now", self)
        self._cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_btn)

        self._next_btn = QPushButton("Save & next", self)
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._on_next)
        buttons.addWidget(self._next_btn)

        root.addLayout(buttons)

        self._render_step()

    def _render_step(self) -> None:
        if self._step_index is None:
            return
        total = len(ONBOARDING_PROMPTS)
        answered = answered_prompt_count(self._store)
        self._step_label.setText(
            f"Step {self._step_index + 1} of {total}  ·  {answered} saved so far"
        )
        self._prompt_label.setText(ONBOARDING_PROMPTS[self._step_index])
        self._input.clear()
        self._input.setFocus()
        self._next_btn.setText(
            "Finish" if self._step_index == total - 1 else "Save & next"
        )

    def _on_text_changed(self) -> None:
        n = len(self._input.toPlainText().strip())
        self._char_count.setText(f"{n} / 300")

    # ---- public accessors (for tests) -----------------------------------
    def current_step(self) -> int | None:
        return self._step_index

    def skip_enabled(self) -> bool:
        return self._skip_btn.isEnabled()

    def is_completed(self) -> bool:
        return self._completed

    # ---- actions --------------------------------------------------------
    def _on_next(self) -> None:
        if self._step_index is None:
            self.accept()
            return
        text = self._input.toPlainText().strip()
        if not text:
            QMessageBox.information(
                self, "Ethical Mirror", "Please write something first."
            )
            return
        try:
            self._store.add(text, onboarding_prompt_id=self._step_index)
        except EthicalValueDuplicateError:
            QMessageBox.information(
                self,
                "Ethical Mirror",
                "You already have a value with the same text. Try different words.",
            )
            return
        except EthicalValueValidationError as exc:
            QMessageBox.warning(self, "Ethical Mirror", str(exc))
            return

        self._step_index = next_unanswered_prompt_index(self._store)
        self._skip_btn.setEnabled(answered_prompt_count(self._store) >= EARLY_EXIT_MIN)

        if self._step_index is None:
            # All prompts answered.
            self._store.mark_onboarded()
            self._completed = True
            self.accept()
            return
        self._render_step()

    def _on_skip(self) -> None:
        n = answered_prompt_count(self._store)
        if n < EARLY_EXIT_MIN:
            return
        confirm = QMessageBox.question(
            self,
            "Finish onboarding early?",
            f"You have {n} of {len(ONBOARDING_PROMPTS)} values saved.\n\n"
            "You can add more anytime in Settings → Ethical Mirror. "
            "Fewer than 10 values puts Ethical Mirror in limited profile mode.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._store.mark_onboarded()
        self._completed = True
        self.accept()

    def _on_cancel(self) -> None:
        # Preserves whatever answers were saved; bumps dismiss count so
        # the wizard stops nagging after DISMISS_OFFER_LIMIT dismissals.
        self._store.increment_dismissed()
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        # Same treatment as Cancel when closed via X.
        if not self._completed:
            self._store.increment_dismissed()
        super().closeEvent(event)
