#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║           AEGIS  —  task_manager.py                      ║
║   Saves every task result to its own dedicated file.     ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import re
from datetime import datetime
from pathlib import Path


TASKS_DIR = Path.home() / ".aegis" / "tasks"


class TaskManager:
    """
    Manages task output files.  Each task is saved to a separate
    timestamped file inside  ~/.aegis/tasks/.
    """

    def __init__(self, tasks_dir: Path = TASKS_DIR):
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    # ── Sanitise filename ──────────────────────────────────
    @staticmethod
    def _safe_name(name: str) -> str:
        name = re.sub(r"[^\w\-. ]", "_", name).strip().replace(" ", "_")
        return name[:80] if name else "task"

    # ── Save a task file ───────────────────────────────────
    def save(self, filename: str, content: str) -> str:
        """
        Write content to a new file in the tasks directory.
        Filename is auto-prefixed with a timestamp so files never collide.
        Returns the full path of the saved file.
        """
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self._safe_name(Path(filename).stem)
        ext  = Path(filename).suffix or ".txt"
        fname= f"{ts}_{base}{ext}"
        path = self.tasks_dir / fname

        path.write_text(content, encoding="utf-8")
        return str(path)

    # ── List saved tasks ───────────────────────────────────
    def list_tasks(self) -> list[str]:
        """Return sorted list of saved task filenames (newest first)."""
        files = sorted(self.tasks_dir.glob("*"), reverse=True)
        return [f.name for f in files if f.is_file()]

    # ── Read a task file ───────────────────────────────────
    def read(self, filename: str) -> str:
        path = self.tasks_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"[not found: {filename}]"
