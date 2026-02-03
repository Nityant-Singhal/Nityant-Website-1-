"""IIT Cal - Offline JEE Study Dashboard.

This application is designed to be fully local and offline. It stores
all data in the local folder, writes append-only CSV entries, and keeps
logs in a human-readable format.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PIL import Image

import strings

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older Pythons
    from backports.zoneinfo import ZoneInfo  # type: ignore

IST = ZoneInfo("Asia/Kolkata")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BACKUP_DIR = DATA_DIR / "backup"
IMAGES_DIR = ROOT / "images" / "IIT imgs"
SOUNDS_DIR = ROOT / "sounds"
LOGS_DIR = ROOT / "logs"

PROGRESS_FILE = DATA_DIR / "jee_progress.csv"
MONTHLY_FILE = DATA_DIR / "monthly_productivity.csv"
REFLECTION_FILE = DATA_DIR / "daily_reflection.txt"
SESSION_STATE_FILE = DATA_DIR / "session_state.txt"
CONFIG_FILE = ROOT / "config.json"
LINKS_FILE = ROOT / "links.txt"
QUOTES_FILE = ROOT / "quotes.txt"


@dataclass
class AppConfig:
    """Configuration data loaded from config.json.

    Attributes:
        image_interval_seconds: Seconds between background rotations.
        countdown_target: ISO timestamp for countdown target.
        default_theme: Default theme name.
        auto_backup_on_save: Toggle for backups on save.
        max_image_dimension: Maximum dimension for background images.
        image_quality: JPEG quality for optimized images.
        end_of_day_trigger_minutes_before_sleep: Trigger reflection popup.
        save_at_midnight_ist: Whether to auto-save at midnight IST.
        default_sleep_time: Default sleep time used for end-of-day timer.
        image_folder_size_limit_mb: Threshold for images folder size.
        resume_policy_on_crash: How to handle crash resume.
    """

    image_interval_seconds: int = 100
    countdown_target: str = "2027-01-21T00:00:00+05:30"
    default_theme: str = "dark"
    auto_backup_on_save: bool = True
    max_image_dimension: int = 1920
    image_quality: int = 85
    end_of_day_trigger_minutes_before_sleep: int = 30
    save_at_midnight_ist: bool = True
    default_sleep_time: str = "11:00 PM"
    image_folder_size_limit_mb: int = 2048
    resume_policy_on_crash: str = "ask"


class OverrideLogger:
    """Utility to record any automatic overrides for stability."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.override_events: List[str] = []

    def log_override(self, message: str) -> None:
        """Log an override message with timestamp."""
        timestamp = datetime.now(IST).isoformat()
        entry = f"{timestamp} - {message}"
        self.override_events.append(entry)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(entry + "\n")

    def summary(self) -> str:
        """Provide a summary of overrides for display."""
        if not self.override_events:
            return "No overrides today."
        return "\n".join(self.override_events)


class DataManager:
    """Handle CSV data operations with safety checks."""

    def __init__(self, override_logger: OverrideLogger) -> None:
        self.override_logger = override_logger
        self.write_lock = QtCore.QMutex()

    def append_progress_row(self, row: List[str], auto_saved: bool) -> bool:
        """Append a single row to the main progress CSV.

        Args:
            row: Ordered list of column values.
            auto_saved: Whether this row is auto-saved.

        Returns:
            True if write succeeded, False if file is locked.
        """
        self.write_lock.lock()
        try:
            timestamp = datetime.now(IST).isoformat()
            row.append(timestamp)
            row.append("True" if auto_saved else "False")
            with PROGRESS_FILE.open("a", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(row)
            return True
        except PermissionError:
            self._backup_progress_file()
            return False
        finally:
            self.write_lock.unlock()

    def update_monthly_productivity(self, date_key: str, study_hours: float) -> None:
        """Update monthly_productivity.csv with atomic write.

        Args:
            date_key: Date in YYYY-MM-DD.
            study_hours: Study hours in decimal.
        """
        rows = []
        if MONTHLY_FILE.exists():
            with MONTHLY_FILE.open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file)
                rows = list(reader)
        header = rows[0] if rows else [
            "Date",
            "StudyHoursDecimal",
            "DayOfMonth",
            "Month",
            "Year",
        ]
        data_rows = [row for row in rows[1:] if row and row[0] != date_key]
        date_obj = datetime.strptime(date_key, "%Y-%m-%d")
        new_row = [
            date_key,
            f"{study_hours:.2f}",
            str(date_obj.day),
            str(date_obj.month),
            str(date_obj.year),
        ]
        data_rows.append(new_row)
        temp_path = MONTHLY_FILE.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(header)
            writer.writerows(sorted(data_rows, key=lambda r: r[0]))
        temp_path.replace(MONTHLY_FILE)

    def load_monthly_productivity(self) -> Dict[str, float]:
        """Load monthly productivity values keyed by date."""
        data: Dict[str, float] = {}
        if not MONTHLY_FILE.exists():
            return data
        with MONTHLY_FILE.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    data[row["Date"]] = float(row["StudyHoursDecimal"])
                except (ValueError, KeyError):
                    continue
        return data

    def load_progress_for_date(self, date_key: str) -> Optional[Dict[str, str]]:
        """Load the latest progress row for a given date."""
        if not PROGRESS_FILE.exists():
            return None
        with PROGRESS_FILE.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("Date") == date_key:
                    return row
        return None

    def append_reflection(self, text: str) -> None:
        """Append a reflection entry to the daily_reflection file."""
        with REFLECTION_FILE.open("a", encoding="utf-8") as file:
            file.write(text + "\n")

    def _backup_progress_file(self) -> None:
        """Create a timestamped backup if a write fails."""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
        backup_file = BACKUP_DIR / f"jee_progress_backup-{timestamp}.csv"
        if PROGRESS_FILE.exists():
            shutil.copy2(PROGRESS_FILE, backup_file)
        self.override_logger.log_override(
            "Backup created due to write failure (file likely locked)."
        )


class EndOfDayDialog(QDialog):
    """Dialog for collecting end-of-day reflections."""

    def __init__(self, total_session_hours: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.END_OF_DAY_TITLE)
        self.setModal(True)
        self.skip_reason: Optional[str] = None
        self.result_text: Optional[str] = None

        self.productive_hours = QLineEdit(f"{total_session_hours:.2f}")
        self.time_wasted = QLineEdit("0")
        self.day_sleep_combo = QComboBox()
        self.day_sleep_combo.addItems(["No", "Yes"])
        self.day_sleep_duration = QLineEdit("0")
        self.biggest_mistake = QTextEdit()
        self.one_thing_right = QTextEdit()
        self.new_learnt = QTextEdit()

        form = QFormLayout()
        form.addRow("Productive hours", self.productive_hours)
        form.addRow("Time wasted (hours)", self.time_wasted)
        form.addRow("Day sleep taken?", self.day_sleep_combo)
        form.addRow("Day sleep duration (hours)", self.day_sleep_duration)
        form.addRow("Biggest mistake today", self.biggest_mistake)
        form.addRow("One thing done right", self.one_thing_right)
        form.addRow("Anything new learnt", self.new_learnt)

        self.save_button = QPushButton(strings.END_OF_DAY_SAVE)
        self.skip_button = QPushButton(strings.END_OF_DAY_SKIP)

        self.save_button.clicked.connect(self.save)
        self.skip_button.clicked.connect(self.skip)

        button_row = QHBoxLayout()
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.skip_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def save(self) -> None:
        """Save reflection data to a string for the caller."""
        self.result_text = (
            f"Productive hours: {self.productive_hours.text()} | "
            f"Time wasted: {self.time_wasted.text()} | "
            f"Day sleep: {self.day_sleep_combo.currentText()} "
            f"({self.day_sleep_duration.text()} hours) | "
            f"Mistake: {self.biggest_mistake.toPlainText()} | "
            f"Right: {self.one_thing_right.toPlainText()} | "
            f"Learnt: {self.new_learnt.toPlainText()}"
        )
        self.accept()

    def skip(self) -> None:
        """Prompt for a skip reason."""
        reason, ok = QtWidgets.QInputDialog.getText(
            self,
            strings.END_OF_DAY_REASON,
            "Enter skip reason:",
        )
        if ok and reason.strip():
            self.skip_reason = reason.strip()
            self.accept()
        elif ok:
            QMessageBox.warning(self, "Skip", "Skip reason is required.")


class DayDetailDialog(QDialog):
    """Dialog to show details for a selected date."""

    def __init__(self, data: Dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Day Details")
        form = QFormLayout()
        for key, value in data.items():
            form.addRow(key, QLabel(value))
        self.setLayout(form)


class IITCalApp(QtWidgets.QMainWindow):
    """Main application window and UI logic."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(strings.APP_TITLE)
        self.resize(1200, 800)

        self.override_logger = OverrideLogger(LOGS_DIR / "overrides_log.txt")
        self.data_manager = DataManager(self.override_logger)
        self.config = self.load_config()

        self.session_running = False
        self.session_start_time: Optional[datetime] = None
        self.session_total = timedelta()
        self.session_count = 0
        self.last_reflection_date: Optional[str] = None

        self.background_images = self.load_images()
        self.current_image_index = 0

        self.build_ui()
        self.apply_theme()
        self.start_timers()
        self.load_quote()
        self.restore_window_state()
        self.check_for_resume_session()
        self.check_overrides_summary()

    def load_config(self) -> AppConfig:
        """Load configuration from JSON, or use defaults."""
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return AppConfig(**data)
        return AppConfig()

    def restore_window_state(self) -> None:
        """Restore last window geometry from config if available."""
        config_path = CONFIG_FILE
        if not config_path.exists():
            return
        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        geometry = data.get("window_geometry")
        if geometry:
            self.restoreGeometry(QtCore.QByteArray.fromHex(geometry.encode()))

    def save_window_state(self) -> None:
        """Persist window geometry in config.json."""
        data = self.config.__dict__.copy()
        data["window_geometry"] = self.saveGeometry().toHex().data().decode()
        with CONFIG_FILE.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    def build_ui(self) -> None:
        """Build the main UI layout."""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.background_label = QLabel()
        self.background_label.setScaledContents(True)
        self.background_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.clock_label = QLabel()
        self.clock_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))

        self.countdown_label = QLabel()
        self.countdown_label.setFont(QFont("Arial", 14))

        self.quote_label = QLabel()
        self.quote_label.setWordWrap(True)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.clock_label)
        top_bar.addStretch()
        top_bar.addWidget(self.countdown_label)

        self.status_label = QLabel(strings.STATUS_READY)

        self.start_button = QPushButton(strings.BTN_START_SESSION)
        self.stop_button = QPushButton(strings.BTN_STOP_SESSION)
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.start_session)
        self.stop_button.clicked.connect(self.stop_session)

        session_row = QHBoxLayout()
        session_row.addWidget(self.start_button)
        session_row.addWidget(self.stop_button)

        self.session_total_label = QLabel("00:00:00")
        self.session_count_label = QLabel("0")

        form_group = QGroupBox("Daily Entry")
        form_layout = QFormLayout()

        self.subject_input = QLineEdit()
        self.day_type_input = QLineEdit()
        self.lecture_hours_input = QLineEdit("0")
        self.questions_input = QLineEdit("0")
        self.wake_time_input = QLineEdit()
        self.sleep_time_input = QLineEdit(self.config.default_sleep_time)
        self.notes_input = QTextEdit()

        form_layout.addRow(strings.LABEL_SUBJECT, self.subject_input)
        form_layout.addRow(strings.LABEL_DAY_TYPE, self.day_type_input)
        form_layout.addRow(strings.LABEL_LECTURE_HOURS, self.lecture_hours_input)
        form_layout.addRow(strings.LABEL_QUESTIONS_SOLVED, self.questions_input)
        form_layout.addRow(strings.LABEL_WAKE_TIME, self.wake_time_input)
        form_layout.addRow(strings.LABEL_SLEEP_TIME, self.sleep_time_input)
        form_layout.addRow(strings.LABEL_NOTES, self.notes_input)

        form_group.setLayout(form_layout)

        self.save_button = QPushButton(strings.BTN_SAVE_DAILY)
        self.save_button.clicked.connect(self.save_daily_entry)

        daily_layout = QVBoxLayout()
        daily_layout.addLayout(session_row)
        daily_layout.addWidget(QLabel(strings.LABEL_SESSION_TOTAL + ":"))
        daily_layout.addWidget(self.session_total_label)
        daily_layout.addWidget(QLabel(strings.LABEL_SESSION_COUNT + ":"))
        daily_layout.addWidget(self.session_count_label)
        daily_layout.addWidget(form_group)
        daily_layout.addWidget(self.save_button)

        dashboard_widget = QWidget()
        dashboard_widget.setLayout(daily_layout)

        self.month_calendar = QCalendarWidget()
        self.month_calendar.clicked.connect(self.open_day_detail)
        self.update_calendar_colors()

        month_layout = QVBoxLayout()
        month_layout.addWidget(self.month_calendar)
        month_widget = QWidget()
        month_widget.setLayout(month_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(dashboard_widget, strings.TAB_DASHBOARD)
        self.tabs.addTab(month_widget, strings.TAB_MONTH)

        self.links_layout = QVBoxLayout()
        self.load_links()

        self.reload_links_button = QPushButton(strings.BTN_RELOAD_LINKS)
        self.reload_links_button.clicked.connect(self.load_links)
        self.reload_quotes_button = QPushButton(strings.BTN_RELOAD_QUOTES)
        self.reload_quotes_button.clicked.connect(self.load_quote)
        self.backup_button = QPushButton(strings.BTN_BACKUP_NOW)
        self.backup_button.clicked.connect(self.backup_now)
        self.export_month_button = QPushButton(strings.BTN_EXPORT_MONTH)
        self.export_month_button.clicked.connect(self.export_month)

        side_layout = QVBoxLayout()
        side_layout.addWidget(QLabel("Links"))
        side_layout.addLayout(self.links_layout)
        side_layout.addStretch()
        side_layout.addWidget(self.reload_links_button)
        side_layout.addWidget(self.reload_quotes_button)
        side_layout.addWidget(self.backup_button)
        side_layout.addWidget(self.export_month_button)

        side_widget = QWidget()
        side_widget.setLayout(side_layout)

        main_layout = QGridLayout()
        main_layout.addLayout(top_bar, 0, 0, 1, 2)
        main_layout.addWidget(self.quote_label, 1, 0, 1, 2)
        main_layout.addWidget(self.tabs, 2, 0)
        main_layout.addWidget(side_widget, 2, 1)
        main_layout.addWidget(self.status_label, 3, 0, 1, 2)

        self.central_widget.setLayout(main_layout)

        self.background_label.lower()
        self.background_label.setParent(self.central_widget)
        self.background_label.resize(self.central_widget.size())
        self.central_widget.installEventFilter(self)

        self.apply_background_image()

    def apply_theme(self) -> None:
        """Apply dark or light theme based on config."""
        if self.config.default_theme == "light":
            self.setStyleSheet("background-color: #f2f2f2; color: #111;")
        else:
            self.setStyleSheet("background-color: #111; color: #f2f2f2;")

    def eventFilter(self, source: QObject, event: QtCore.QEvent) -> bool:  # type: ignore[name-defined]
        """Handle resize events to scale background image."""
        if event.type() == QtCore.QEvent.Type.Resize:
            self.background_label.resize(self.central_widget.size())
            self.apply_background_image()
        return super().eventFilter(source, event)

    def start_timers(self) -> None:
        """Start timers for clock, countdown, and background rotation."""
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.background_timer = QTimer(self)
        self.background_timer.timeout.connect(self.rotate_background)
        self.background_timer.start(self.config.image_interval_seconds * 1000)

        self.end_of_day_timer = QTimer(self)
        self.end_of_day_timer.timeout.connect(self.check_end_of_day)
        self.end_of_day_timer.start(60 * 1000)

    def update_clock(self) -> None:
        """Update live IST clock and countdown."""
        now = datetime.now(IST)
        self.clock_label.setText(f"{strings.CLOCK_LABEL}: {now.strftime('%H:%M:%S')}")
        target = datetime.fromisoformat(self.config.countdown_target)
        delta = target - now
        if delta.total_seconds() < 0:
            delta = timedelta(0)
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.countdown_label.setText(
            f"Countdown: {days}D {hours}H {minutes}M {seconds}S"
        )

    def load_images(self) -> List[Path]:
        """Load image paths from the images folder."""
        if not IMAGES_DIR.exists():
            return []
        images = [
            path
            for path in IMAGES_DIR.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
        random.shuffle(images)
        return images

    def apply_background_image(self) -> None:
        """Apply the current background image, scaled to window size."""
        if not self.background_images:
            self.background_label.setText(strings.NO_IMAGES_HINT)
            self.background_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            return
        image_path = self.background_images[self.current_image_index]
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            self.background_label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.background_label.setPixmap(scaled)

    def rotate_background(self) -> None:
        """Rotate to the next background image."""
        if not self.background_images:
            return
        self.current_image_index = (self.current_image_index + 1) % len(self.background_images)
        self.apply_background_image()

    def start_session(self) -> None:
        """Start a study session and write session_state.txt."""
        if self.session_running:
            return
        self.session_start_time = datetime.now(IST)
        self.session_running = True
        self.session_count += 1
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText(strings.STATUS_SESSION_RUNNING)
        session_data = {
            "start": self.session_start_time.isoformat(),
            "session_id": self.session_count,
            "subject": self.subject_input.text() or "General",
        }
        with SESSION_STATE_FILE.open("w", encoding="utf-8") as file:
            json.dump(session_data, file)
        self.play_sound("session_start.mp3")

    def stop_session(self) -> None:
        """Stop the current session and update totals."""
        if not self.session_running or not self.session_start_time:
            return
        end_time = datetime.now(IST)
        duration = end_time - self.session_start_time
        self.session_total += duration
        self.session_running = False
        self.session_start_time = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText(strings.STATUS_SESSION_STOPPED)
        self.session_total_label.setText(self.format_timedelta(self.session_total))
        self.session_count_label.setText(str(self.session_count))
        if SESSION_STATE_FILE.exists():
            SESSION_STATE_FILE.write_text("", encoding="utf-8")
        self.play_sound("session_stop.mp3")

    def check_for_resume_session(self) -> None:
        """Check if a previous session was running and prompt to resume."""
        if not SESSION_STATE_FILE.exists():
            return
        content = SESSION_STATE_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            self.override_logger.log_override("Corrupt session_state.txt; discarded.")
            SESSION_STATE_FILE.write_text("", encoding="utf-8")
            return
        start_time = data.get("start")
        if not start_time:
            return
        message = strings.MSG_RESUME_SESSION.format(time=start_time)
        reply = QMessageBox.question(self, "Resume", message)
        if reply == QMessageBox.StandardButton.Yes:
            self.session_start_time = datetime.fromisoformat(start_time)
            self.session_running = True
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText(strings.STATUS_SESSION_RUNNING)
        else:
            SESSION_STATE_FILE.write_text("", encoding="utf-8")

    def format_timedelta(self, duration: timedelta) -> str:
        """Format a timedelta into HH:MM:SS."""
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def save_daily_entry(self) -> None:
        """Save the daily entry to CSV."""
        date_key = datetime.now(IST).strftime("%Y-%m-%d")
        row = [
            date_key,
            self.day_type_input.text() or "",
            self.subject_input.text() or "",
            self.lecture_hours_input.text() or "0",
            self.questions_input.text() or "0",
            self.format_timedelta(self.session_total),
            self.wake_time_input.text() or "",
            self.sleep_time_input.text() or self.config.default_sleep_time,
            str(self.session_count),
            self.notes_input.toPlainText() or "",
        ]
        success = self.data_manager.append_progress_row(row, auto_saved=False)
        if not success:
            QMessageBox.warning(self, "File Locked", strings.STATUS_FILE_LOCKED)
        self.data_manager.update_monthly_productivity(
            date_key, self.session_total.total_seconds() / 3600
        )
        self.update_calendar_colors()

    def check_end_of_day(self) -> None:
        """Check whether to trigger end-of-day reflection popup."""
        now = datetime.now(IST)
        date_key = now.strftime("%Y-%m-%d")
        if self.last_reflection_date == date_key:
            return
        sleep_time_str = self.sleep_time_input.text() or self.config.default_sleep_time
        try:
            sleep_time = datetime.strptime(sleep_time_str, "%I:%M %p")
        except ValueError:
            return
        trigger_time = now.replace(
            hour=sleep_time.hour,
            minute=sleep_time.minute,
            second=0,
            microsecond=0,
        ) - timedelta(minutes=self.config.end_of_day_trigger_minutes_before_sleep)
        if now >= trigger_time:
            self.trigger_end_of_day()
            self.last_reflection_date = date_key

    def trigger_end_of_day(self) -> None:
        """Show end-of-day reflection dialog and save results."""
        total_hours = self.session_total.total_seconds() / 3600
        dialog = EndOfDayDialog(total_hours, self)
        self.play_sound("day_end.mp3")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            now = datetime.now(IST).isoformat()
            date_key = datetime.now(IST).strftime("%Y-%m-%d")
            if dialog.skip_reason:
                entry = f"{date_key} | skipped | {dialog.skip_reason}"
                self.data_manager.append_reflection(entry)
                return
            reflection_text = dialog.result_text or ""
            entry = f"{date_key} | {now} | {reflection_text}"
            self.data_manager.append_reflection(entry)
            self.notes_input.append(reflection_text)
            self.save_daily_entry()

    def open_day_detail(self, date: QDate) -> None:
        """Open details for a selected date."""
        date_key = date.toString("yyyy-MM-dd")
        data = self.data_manager.load_progress_for_date(date_key)
        if not data:
            QMessageBox.information(self, "No Data", "No data for this date.")
            return
        dialog = DayDetailDialog(data, self)
        dialog.exec()

    def update_calendar_colors(self) -> None:
        """Update calendar heatmap colors based on monthly data."""
        productivity = self.data_manager.load_monthly_productivity()
        fmt = QtGui.QTextCharFormat()
        for date_str, hours in productivity.items():
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            intensity = min(hours / 10.0, 1.0)
            color = QColor.fromHsv(120, int(255 * intensity), 200)
            fmt.setBackground(color)
            self.month_calendar.setDateTextFormat(
                QDate(date_obj.year, date_obj.month, date_obj.day), fmt
            )

    def load_links(self) -> None:
        """Load links from links.txt and render buttons."""
        while self.links_layout.count():
            item = self.links_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()
        if not LINKS_FILE.exists():
            return
        with LINKS_FILE.open("r", encoding="utf-8") as file:
            lines = [line.strip() for line in file if line.strip()]
        for line in lines:
            if "|" not in line:
                continue
            label, url = line.split("|", 1)
            button = QPushButton(label)
            button.clicked.connect(lambda _, link=url: QtGui.QDesktopServices.openUrl(QtCore.QUrl(link)))
            self.links_layout.addWidget(button)

    def load_quote(self) -> None:
        """Load a random quote from quotes.txt."""
        if not QUOTES_FILE.exists():
            self.quote_label.setText("")
            return
        with QUOTES_FILE.open("r", encoding="utf-8") as file:
            quotes = [line.strip() for line in file if line.strip()]
        if quotes:
            self.quote_label.setText(random.choice(quotes))

    def backup_now(self) -> None:
        """Create a backup of the main progress file."""
        timestamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
        backup_file = BACKUP_DIR / f"jee_progress_backup-{timestamp}.csv"
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if PROGRESS_FILE.exists():
            shutil.copy2(PROGRESS_FILE, backup_file)
            QMessageBox.information(self, "Backup", "Backup created.")

    def export_month(self) -> None:
        """Export monthly productivity file to a chosen location."""
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Month", "monthly_productivity.csv", "CSV Files (*.csv)"
        )
        if target:
            shutil.copy2(MONTHLY_FILE, Path(target))
            QMessageBox.information(self, "Export", "Monthly file exported.")

    def play_sound(self, filename: str) -> None:
        """Play a sound if the file exists."""
        sound_path = SOUNDS_DIR / filename
        if not sound_path.exists():
            return
        effect = QSoundEffect(self)
        effect.setSource(QtCore.QUrl.fromLocalFile(str(sound_path)))
        effect.play()

    def check_overrides_summary(self) -> None:
        """Display overrides summary once per session."""
        summary = self.override_logger.summary()
        QMessageBox.information(self, strings.OVERRIDES_SUMMARY_TITLE, summary)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Prompt if closing while a session is running."""
        if self.session_running:
            reply = QMessageBox.question(
                self,
                "Confirm",
                "A session is running. Close anyway?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.save_window_state()
        event.accept()


def ensure_folders() -> None:
    """Ensure required folders exist."""
    for path in [DATA_DIR, BACKUP_DIR, IMAGES_DIR, SOUNDS_DIR, LOGS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    """Configure logging to logs/error_log.txt."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOGS_DIR / "error_log.txt"),
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def main() -> None:
    """Application entry point."""
    ensure_folders()
    configure_logging()
    app = QtWidgets.QApplication(sys.argv)
    window = IITCalApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
