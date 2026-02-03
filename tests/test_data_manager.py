"""Unit tests for data operations.

These tests focus on CSV append logic and monthly productivity updates.
"""

import csv
from datetime import datetime
from pathlib import Path

import app


def test_append_progress_row(tmp_path: Path) -> None:
    """Appending a row should add a line with timestamp and autosave flag."""
    app.PROGRESS_FILE = tmp_path / "jee_progress.csv"
    app.PROGRESS_FILE.write_text(
        "Date,Day Type,Subject,Lecture Hours,Questions Solved,Total Session Time (HH:MM:SS),"
        "Wake Time (hh:mm AM/PM),Sleep Time (hh:mm AM/PM),Session Count,Notes/Mistakes,"
        "Manual Save Timestamp (ISO),AutoSavedFlag\n",
        encoding="utf-8",
    )
    manager = app.DataManager(app.OverrideLogger(tmp_path / "overrides_log.txt"))
    row = [
        "2026-01-24",
        "Practice",
        "Physics",
        "2.0",
        "50",
        "04:30:00",
        "06:45 AM",
        "11:15 PM",
        "3",
        "Notes",
    ]
    assert manager.append_progress_row(row, auto_saved=True) is True
    with app.PROGRESS_FILE.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    assert len(rows) == 2
    assert rows[1][0] == "2026-01-24"
    assert rows[1][-1] == "True"


def test_update_monthly_productivity(tmp_path: Path) -> None:
    """Monthly productivity updates should replace existing date rows."""
    app.MONTHLY_FILE = tmp_path / "monthly_productivity.csv"
    manager = app.DataManager(app.OverrideLogger(tmp_path / "overrides_log.txt"))
    manager.update_monthly_productivity("2026-01-24", 4.5)
    manager.update_monthly_productivity("2026-01-24", 5.5)
    with app.MONTHLY_FILE.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    assert len(rows) == 2
    assert rows[1][0] == "2026-01-24"
    assert rows[1][1] == "5.50"
