"""Diagnostics panel — read-only system state for troubleshooting."""

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DiagnosticsPanel(QWidget):
    """Read-only view of SHADOW's current state."""

    def __init__(self, backend, memory, config, observer=None):
        super().__init__()
        self.backend = backend
        self.memory = memory
        self.config = config
        self.observer = observer

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Diagnostics</h2>"))

        subtitle = QLabel(
            "Read-only snapshot. Useful for bug reports and troubleshooting."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(subtitle)

        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)

        copy_btn = QPushButton("Copy to clipboard")
        copy_btn.clicked.connect(self.copy_report)
        buttons.addWidget(copy_btn)

        buttons.addStretch()
        layout.addLayout(buttons)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(self.text)

        self.refresh()

    # ---------- report ----------

    def refresh(self):
        report = self._build_report()
        self.text.setPlainText(report)

    def copy_report(self):
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self.text.toPlainText())
        except Exception:
            pass

    def _build_report(self) -> str:
        sections = [
            self._backend_section(),
            self._models_section(),
            self._observer_section(),
            self._database_section(),
            self._retention_section(),
            self._errors_section(),
            self._network_section(),
        ]
        return "\n\n".join(s for s in sections if s)

    # ---------- sections ----------

    def _backend_section(self) -> str:
        lines = ["=== Backend ==="]
        try:
            info = self.backend.info if self.backend else {}
            for k, v in info.items():
                lines.append(f"  {k:12}: {v}")
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _models_section(self) -> str:
        lines = ["=== Models ==="]
        try:
            from shadow.models import ModelManager

            cache_dir = (self.config.get("models") or {}).get("cache_dir", "models")
            mgr = ModelManager(cache_dir=cache_dir)
            status = mgr.status()
            for mid, info in status.items():
                state = "missing"
                if info["present"]:
                    state = "ok" if info["verified"] else "unverified"
                lines.append(
                    f"  {mid:20} {state:12} "
                    f"{info['size_bytes'] // (1024 * 1024):>5} MB"
                )
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _observer_section(self) -> str:
        lines = ["=== Observer ==="]
        try:
            if self.observer is not None:
                running = self.observer.isRunning()
                lines.append(f"  running     : {running}")
                sources = [s.name for s in getattr(self.observer, "sources", [])]
                lines.append(f"  sources     : {', '.join(sources) or '(none)'}")
                mode = getattr(self.observer, "_current_mode", "?")
                lines.append(f"  mode        : {mode}")
                tick_count = getattr(self.observer, "_tick_count", "?")
                lines.append(f"  ticks       : {tick_count}")
            else:
                lines.append("  observer    : not attached")
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _database_section(self) -> str:
        lines = ["=== Database ==="]
        try:
            cur = self.memory.conn.cursor()
            counts = [
                ("observations", "SELECT COUNT(*) FROM observations"),
                ("vec_observations", "SELECT COUNT(*) FROM vec_observations"),
                ("entities", "SELECT COUNT(*) FROM entities"),
                ("edges", "SELECT COUNT(*) FROM edges"),
                ("activity_log", "SELECT COUNT(*) FROM activity_log"),
                ("consent_audit", "SELECT COUNT(*) FROM consent_audit"),
            ]
            for label, sql in counts:
                try:
                    cur.execute(sql)
                    lines.append(f"  {label:18}: {cur.fetchone()[0]}")
                except Exception:
                    lines.append(f"  {label:18}: (unavailable)")

            # File size
            db_path = Path(self.memory.db_path)
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                lines.append(f"  {'file size':18}: {size_mb:.2f} MB")

            # WAL mode
            cur.execute("PRAGMA journal_mode")
            lines.append(f"  {'journal mode':18}: {cur.fetchone()[0]}")

            # Schema version
            cur.execute("SELECT value FROM schema_meta WHERE key = 'current_version'")
            row = cur.fetchone()
            lines.append(f"  {'schema version':18}: {row[0] if row else 'unknown'}")
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _retention_section(self) -> str:
        lines = ["=== Retention ==="]
        try:
            last = self.memory.get_meta("last_prune_at")
            lines.append(f"  last prune     : {last or 'never'}")

            cur = self.memory.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'prune'")
            lines.append(f"  prune runs     : {cur.fetchone()[0]}")
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _errors_section(self) -> str:
        lines = ["=== Recent Errors (last 5) ==="]
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT timestamp, details FROM activity_log "
                "WHERE action = 'error' ORDER BY id DESC LIMIT 5"
            )
            rows = cur.fetchall()
            if not rows:
                lines.append("  (none)")
            else:
                for ts, details in rows:
                    lines.append(f"  [{ts}] {(details or '')[:100]}")
        except Exception as exc:
            lines.append(f"  error: {exc}")
        return "\n".join(lines)

    def _network_section(self) -> str:
        return (
            "=== Network ===\n"
            "  main process   : isolated (no outbound calls)\n"
            "  enforced by    : scripts/check_network_isolation.py in CI"
        )
