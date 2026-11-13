"""Extraordinary Digital Clock.

A desktop clock application built with Python and Tkinter. It goes well
beyond a basic ``datetime`` + ``Label`` tutorial project into a small
multi-feature desktop app with real UI/UX and software design decisions
behind it.

Features:

- Custom window chrome: borderless, draggable window with its own
  minimize and close controls instead of relying on the OS title bar.
- Time of day reactive background: the palette shifts between day and
  night tones depending on the current hour, recalculated every 30 seconds.
- Digital plus analog display: a live analog clock face drawn on a Canvas
  using trigonometry for the hour, minute, and second hands, alongside
  the standard digital readout and full date.
- World clock panel: five configurable timezones shown as fixed UTC
  offsets, updating live alongside the local clock.
- Theme switcher: three built-in themes swappable instantly via a click,
  no restart required.
- Stopwatch: start, stop, lap, and reset, with a scrolling lap history.
- Alarms: set multiple labeled alarms; a popup and audible beep fire
  when one is triggered.
- Persistent settings: last-used theme, window position, and active mode
  are saved to ``settings.json`` and restored on the next launch.

Only the Python standard library is used. World clock times use fixed UTC
offsets rather than a timezone database, so no ``tzdata`` install is
needed. The trade-off: offsets are hardcoded to each city's current
standard, so they will be off by an hour during daylight saving time
transitions until manually updated in ``WORLD_CLOCK_OFFSETS``.

Run it with::

    python Digital_Clock.py

The pure helper functions at the top of this file (time formatting,
world clock offsets, stopwatch formatting, alarm parsing, hand geometry,
and settings load/save) are deliberately independent of Tkinter so they
can be unit tested without a display. See ``tests/test_clock.py``.
"""

import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:  # pragma: no cover - Tkinter missing on minimal installs
    tk = None
    messagebox = None

try:
    import winsound
except ImportError:  # winsound only exists on Windows
    winsound = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: City name to fixed offset from UTC, in hours. Offsets may be fractional:
#: India, for example, is UTC+05:30. Edit these values to add a city or to
#: correct an offset after a daylight saving time change.
WORLD_CLOCK_OFFSETS = {
    "Dhaka": 6,
    "Seoul": 9,
    "Riyadh": 3,
    "Berlin": 1,
    "Dublin": 0,
    "Kolkata": 5.5,
}

#: Built-in themes. Each theme maps a role name to a hex colour.
THEMES = {
    "Cyberpunk": {
        "bg": "#0d0221",
        "bg_day": "#1b0a3d",
        "bg_night": "#0d0221",
        "fg": "#00f0ff",
        "accent": "#ff2a6d",
        "muted": "#8a7fb8",
        "button": "#2a1a4a",
        "button_fg": "#00f0ff",
    },
    "Minimal Light": {
        "bg": "#f5f5f0",
        "bg_day": "#ffffff",
        "bg_night": "#e8e8e2",
        "fg": "#1a1a1a",
        "accent": "#2563eb",
        "muted": "#6b7280",
        "button": "#e5e7eb",
        "button_fg": "#1a1a1a",
    },
    "Old Money": {
        "bg": "#1c1a16",
        "bg_day": "#2a251c",
        "bg_night": "#1c1a16",
        "fg": "#d4af37",
        "accent": "#8c6a1f",
        "muted": "#a89f8d",
        "button": "#3a3226",
        "button_fg": "#d4af37",
    },
}

THEME_ORDER = ["Cyberpunk", "Minimal Light", "Old Money"]

#: Hour at which day tones start, and hour at which night tones start.
DAY_START_HOUR = 6
NIGHT_START_HOUR = 18

DEFAULT_SETTINGS = {
    "theme": "Cyberpunk",
    "geometry": "520x660+100+100",
    "mode": "Clock",
}

SETTINGS_FILENAME = "settings.json"

#: A saved window geometry must look like ``WIDTHxHEIGHT+X+Y``. Anything
#: else is treated as corrupt and replaced with the default, instead of
#: crashing the app inside ``root.geometry()`` on the next launch.
GEOMETRY_PATTERN = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")


def settings_path():
    """Return the path of the settings file, next to this script."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, SETTINGS_FILENAME)


# ---------------------------------------------------------------------------
# Pure helpers (no Tkinter, unit tested in tests/test_clock.py)
# ---------------------------------------------------------------------------

def format_time(moment):
    """Format a datetime as a 24 hour clock string, ``HH:MM:SS``."""
    return moment.strftime("%H:%M:%S")


def format_date(moment):
    """Format a datetime as a full date, for example ``Monday, 09 November 2026``."""
    return moment.strftime("%A, %d %B %Y")


def format_stopwatch(elapsed_seconds):
    """Format an elapsed time as ``MM:SS.cc`` or ``HH:MM:SS.cc``.

    ``cc`` is hundredths of a second. Hours are shown only once the
    elapsed time reaches one hour.
    """
    if elapsed_seconds < 0:
        raise ValueError("elapsed time cannot be negative")
    total_centiseconds = int(round(elapsed_seconds * 100))
    hours, remainder = divmod(total_centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    if hours:
        return "%02d:%02d:%02d.%02d" % (hours, minutes, seconds, centiseconds)
    return "%02d:%02d.%02d" % (minutes, seconds, centiseconds)


def format_countdown(remaining_seconds):
    """Format a countdown as ``MM:SS`` or ``HH:MM:SS`` once it reaches an hour.

    A negative value is clamped to zero: a countdown never shows a
    negative time.
    """
    if remaining_seconds < 0:
        remaining_seconds = 0
    total_seconds = int(remaining_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    return "%02d:%02d" % (minutes, seconds)


#: Pomodoro phase lengths, in seconds: 25 minutes of focus, 5 of break.
POMODORO_FOCUS_SECONDS = 25 * 60
POMODORO_BREAK_SECONDS = 5 * 60


def pomodoro_next_phase(phase):
    """Return the phase that follows ``phase``: Focus then Break, then Focus."""
    if phase == "Focus":
        return "Break"
    return "Focus"


def pomodoro_phase_seconds(phase):
    """Return the length of a Pomodoro ``phase`` in seconds."""
    if phase == "Break":
        return POMODORO_BREAK_SECONDS
    return POMODORO_FOCUS_SECONDS


def lap_split_seconds(lap_times, index):
    """Return the split for lap ``index``: the time since the previous lap.

    The first lap has no previous lap, so its split is the lap time itself.
    Raises ``IndexError`` for an index outside the list.
    """
    if index < 0 or index >= len(lap_times):
        raise IndexError("lap index out of range")
    if index == 0:
        return lap_times[0]
    return lap_times[index] - lap_times[index - 1]


def world_clock_time(now, offset_hours):
    """Return ``now`` shifted by a fixed UTC offset, in hours.

    The offset may be fractional, for half hour zones such as Kolkata.
    """
    return now + timedelta(hours=offset_hours)


def parse_alarm_time(text):
    """Parse and normalise an alarm time entered as ``HH:MM`` (24 hour).

    Returns the normalised ``HH:MM`` string. Raises ``ValueError`` with
    a plain message for anything that is not a valid 24 hour time.
    """
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError("use HH:MM, 24 hour format")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        raise ValueError("use HH:MM, 24 hour format") from None
    if not 0 <= hour <= 23:
        raise ValueError("hour must be 00 to 23")
    if not 0 <= minute <= 59:
        raise ValueError("minute must be 00 to 59")
    return "%02d:%02d" % (hour, minute)


def alarm_due(alarm, now):
    """Return True when an enabled alarm should fire at ``now``.

    ``alarm`` is a dict with ``time`` (``HH:MM``), ``label``, and
    ``enabled`` keys. An alarm fires during the whole minute it names;
    the app records which minute it already fired in so it rings once.
    """
    if not alarm.get("enabled", True):
        return False
    return now.strftime("%H:%M") == alarm.get("time")


def hand_angles(moment):
    """Return the (hour, minute, second) hand angles in degrees.

    Angles are measured clockwise from 12 o'clock, so 3 o'clock is
    90 degrees and 6 o'clock is 180 degrees.
    """
    second = moment.second * 6
    minute = (moment.minute + moment.second / 60.0) * 6
    hour = ((moment.hour % 12) + moment.minute / 60.0) * 30
    return hour, minute, second


def hand_endpoint(center_x, center_y, length, angle_degrees):
    """Return the (x, y) endpoint of a clock hand at a given angle.

    The angle is measured clockwise from 12 o'clock, matching
    :func:`hand_angles`. Canvas y grows downwards, hence the minus sign.
    """
    radians = math.radians(angle_degrees)
    x = center_x + length * math.sin(radians)
    y = center_y - length * math.cos(radians)
    return x, y


def palette_for_hour(hour):
    """Return ``"day"`` for daytime hours and ``"night"`` otherwise.

    Day runs from 06:00 up to, but not including, 18:00.
    """
    if DAY_START_HOUR <= hour < NIGHT_START_HOUR:
        return "day"
    return "night"


def next_theme(current):
    """Return the next theme name after ``current``, cycling the list."""
    if current not in THEME_ORDER:
        return THEME_ORDER[0]
    index = THEME_ORDER.index(current)
    return THEME_ORDER[(index + 1) % len(THEME_ORDER)]


def load_settings(path):
    """Load settings from ``path``, falling back to defaults.

    A missing file, a corrupt file, or unknown keys all fall back to
    :data:`DEFAULT_SETTINGS` for the affected values, never raising.
    """
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings
    for key in DEFAULT_SETTINGS:
        if key in stored:
            settings[key] = stored[key]
    if settings["theme"] not in THEMES:
        settings["theme"] = DEFAULT_SETTINGS["theme"]
    if settings["mode"] not in ("Clock", "Stopwatch", "Alarms"):
        settings["mode"] = DEFAULT_SETTINGS["mode"]
    if (not isinstance(settings["geometry"], str)
            or not GEOMETRY_PATTERN.match(settings["geometry"])):
        settings["geometry"] = DEFAULT_SETTINGS["geometry"]
    return settings


def save_settings(path, settings):
    """Save ``settings`` as JSON to ``path``. Returns True on success."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, sort_keys=True)
    except OSError:
        return False
    return True


def beep():
    """Sound the alarm beep: ``winsound`` on Windows, terminal bell elsewhere."""
    if winsound is not None:
        try:
            winsound.Beep(880, 500)
        except RuntimeError:
            print("\a", end="", flush=True)
    else:
        print("\a", end="", flush=True)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

if tk is not None:

    class DigitalClockApp:
        """The Tkinter application: window chrome, clock, themes."""

        def __init__(self, root, settings):
            self.root = root
            self.settings = settings
            self.theme_name = settings["theme"]
            self.mode = settings["mode"]
            self.alarms = []
            self._fired_alarms = set()
            self._sw_running = False
            self._sw_start = 0.0
            self._sw_elapsed = 0.0
            self._sw_lap_times = []
            self._drag_offset = (0, 0)
            self._palette = palette_for_hour(datetime.now().hour)

            self.root.overrideredirect(True)
            self.root.geometry(settings["geometry"])
            self.root.protocol("WM_DELETE_WINDOW", self.close)
            self.root.bind("<Escape>", lambda event: self.close())

            self._build_title_bar()
            self._build_tab_bar()
            self._build_clock_tab()
            self._build_stopwatch_tab()
            self._build_alarms_tab()
            self.show_mode(self.mode)

            self.apply_theme()
            self._tick()

        # -- window chrome -------------------------------------------------

        def _build_title_bar(self):
            self.title_bar = tk.Frame(self.root, height=36)
            self.title_bar.pack(fill="x")
            self.title_bar.pack_propagate(False)
            self.title_label = tk.Label(
                self.title_bar, text="Extraordinary Digital Clock",
                font=("Segoe UI", 11, "bold"))
            self.title_label.pack(side="left", padx=10)
            self.min_button = tk.Button(
                self.title_bar, text="\u2013", font=("Segoe UI", 12),
                bd=0, command=self.root.iconify)
            self.min_button.pack(side="right", padx=2)
            self.close_button = tk.Button(
                self.title_bar, text="\u2715", font=("Segoe UI", 11),
                bd=0, command=self.close)
            self.close_button.pack(side="right", padx=2)
            for widget in (self.title_bar, self.title_label):
                widget.bind("<Button-1>", self._drag_start)
                widget.bind("<B1-Motion>", self._drag_move)

        def _drag_start(self, event):
            self._drag_offset = (event.x_root, event.y_root)

        def _drag_move(self, event):
            dx = event.x_root - self._drag_offset[0]
            dy = event.y_root - self._drag_offset[1]
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry("+%d+%d" % (x, y))
            self._drag_offset = (event.x_root, event.y_root)

        # -- tabs ----------------------------------------------------------

        def _build_tab_bar(self):
            self.tab_bar = tk.Frame(self.root, height=40)
            self.tab_bar.pack(fill="x")
            self.tab_bar.pack_propagate(False)
            self.tab_buttons = {}
            for mode in ("Clock", "Stopwatch", "Alarms"):
                button = tk.Button(
                    self.tab_bar, text=mode, font=("Segoe UI", 11),
                    bd=0, command=lambda m=mode: self.show_mode(m))
                button.pack(side="left", padx=4, pady=4)
                self.tab_buttons[mode] = button
            self.theme_button = tk.Button(
                self.tab_bar, text="", font=("Segoe UI", 11),
                bd=0, command=self.cycle_theme)
            self.theme_button.pack(side="right", padx=8, pady=4)

        def show_mode(self, mode):
            """Switch the visible tab and remember it in settings."""
            self.mode = mode
            self.settings["mode"] = mode
            for name, frame in (("Clock", self.clock_frame),
                                ("Stopwatch", self.stopwatch_frame),
                                ("Alarms", self.alarms_frame)):
                if name == mode:
                    frame.pack(fill="both", expand=True)
                else:
                    frame.pack_forget()
            self.apply_theme()
            self._save_settings()

        def cycle_theme(self):
            self.theme_name = next_theme(self.theme_name)
            self.settings["theme"] = self.theme_name
            self.apply_theme()
            self._save_settings()

        def _save_settings(self):
            """Write the current theme, geometry, and mode to disk."""
            self.settings["geometry"] = self.root.geometry()
            self.settings["theme"] = self.theme_name
            self.settings["mode"] = self.mode
            save_settings(settings_path(), self.settings)

        # -- clock tab -----------------------------------------------------

        def _build_clock_tab(self):
            self.clock_frame = tk.Frame(self.root)
            self.time_label = tk.Label(
                self.clock_frame, font=("Segoe UI", 44, "bold"))
            self.time_label.pack(pady=(24, 0))
            self.date_label = tk.Label(
                self.clock_frame, font=("Segoe UI", 14))
            self.date_label.pack(pady=(0, 12))
            self.analog_canvas = tk.Canvas(
                self.clock_frame, width=240, height=240,
                highlightthickness=0)
            self.analog_canvas.pack(pady=8)
            self.world_frame = tk.Frame(self.clock_frame)
            self.world_frame.pack(pady=(4, 12))
            self.world_labels = {}
            for city in WORLD_CLOCK_OFFSETS:
                row = tk.Frame(self.world_frame)
                row.pack(fill="x", padx=20)
                name_label = tk.Label(row, text=city,
                                      font=("Segoe UI", 11), width=10,
                                      anchor="w")
                name_label.pack(side="left")
                time_label = tk.Label(row, font=("Segoe UI", 11, "bold"),
                                      anchor="e")
                time_label.pack(side="right")
                self.world_labels[city] = (name_label, time_label)

        # -- stopwatch tab -------------------------------------------------

        def _build_stopwatch_tab(self):
            self.stopwatch_frame = tk.Frame(self.root)
            self.sw_label = tk.Label(
                self.stopwatch_frame, font=("Segoe UI", 40, "bold"))
            self.sw_label.pack(pady=(32, 8))
            self.sw_button_row = tk.Frame(self.stopwatch_frame)
            self.sw_button_row.pack(pady=8)
            self.sw_start_button = tk.Button(
                self.sw_button_row, text="Start", font=("Segoe UI", 11),
                bd=0, command=self._sw_toggle, width=10)
            self.sw_start_button.pack(side="left", padx=4)
            self.sw_lap_button = tk.Button(
                self.sw_button_row, text="Lap", font=("Segoe UI", 11),
                bd=0, command=self._sw_lap, width=10)
            self.sw_lap_button.pack(side="left", padx=4)
            self.sw_reset_button = tk.Button(
                self.sw_button_row, text="Reset", font=("Segoe UI", 11),
                bd=0, command=self._sw_reset, width=10)
            self.sw_reset_button.pack(side="left", padx=4)
            self.sw_laps = tk.Listbox(
                self.stopwatch_frame, font=("Segoe UI", 11), height=8,
                bd=0, highlightthickness=0)
            self.sw_laps.pack(fill="both", expand=True, padx=20, pady=12)

        def _sw_current_elapsed(self):
            if self._sw_running:
                return self._sw_elapsed + (time.monotonic() - self._sw_start)
            return self._sw_elapsed

        def _sw_toggle(self):
            if self._sw_running:
                self._sw_elapsed = self._sw_current_elapsed()
                self._sw_running = False
                self.sw_start_button.configure(text="Start")
            else:
                self._sw_start = time.monotonic()
                self._sw_running = True
                self.sw_start_button.configure(text="Stop")

        def _sw_lap(self):
            if not self._sw_running:
                return
            lap_time = self._sw_current_elapsed()
            self._sw_lap_times.append(lap_time)
            split = lap_split_seconds(self._sw_lap_times,
                                      len(self._sw_lap_times) - 1)
            self.sw_laps.insert(
                "end", "Lap %d  %s  (+%s)" % (len(self._sw_lap_times),
                                              format_stopwatch(lap_time),
                                              format_stopwatch(split)))
            self.sw_laps.see("end")

        def _sw_reset(self):
            self._sw_running = False
            self._sw_elapsed = 0.0
            self._sw_lap_times = []
            self.sw_start_button.configure(text="Start")
            self.sw_laps.delete(0, "end")

        # -- alarms tab ----------------------------------------------------

        def _build_alarms_tab(self):
            self.alarms_frame = tk.Frame(self.root)
            form = tk.Frame(self.alarms_frame)
            form.pack(fill="x", padx=20, pady=(24, 8))
            self.alarm_time_entry = tk.Entry(form, font=("Segoe UI", 12),
                                             width=8)
            self.alarm_time_entry.pack(side="left", padx=(0, 8))
            self.alarm_time_entry.insert(0, "07:30")
            self.alarm_label_entry = tk.Entry(form, font=("Segoe UI", 12))
            self.alarm_label_entry.pack(side="left", fill="x", expand=True,
                                        padx=(0, 8))
            self.alarm_label_entry.insert(0, "Wake up")
            self.alarm_add_button = tk.Button(
                form, text="Add alarm", font=("Segoe UI", 11), bd=0,
                command=self._add_alarm, width=10)
            self.alarm_add_button.pack(side="left")
            self.alarm_hint = tk.Label(
                self.alarms_frame,
                text="Enter a time as HH:MM, 24 hour format, plus a label.",
                font=("Segoe UI", 10))
            self.alarm_hint.pack(pady=(0, 8))
            self.alarm_list = tk.Listbox(
                self.alarms_frame, font=("Segoe UI", 11), height=8,
                bd=0, highlightthickness=0)
            self.alarm_list.pack(fill="both", expand=True, padx=20, pady=4)
            self.alarm_delete_button = tk.Button(
                self.alarms_frame, text="Delete selected",
                font=("Segoe UI", 11), bd=0, command=self._delete_alarm)
            self.alarm_delete_button.pack(pady=12)

        def _add_alarm(self):
            try:
                alarm_time = parse_alarm_time(self.alarm_time_entry.get())
            except ValueError as exc:
                if messagebox is not None:
                    messagebox.showerror("Invalid time", str(exc))
                return
            label = self.alarm_label_entry.get().strip() or "Alarm"
            self.alarms.append({"time": alarm_time, "label": label,
                                "enabled": True})
            self._refresh_alarm_list()

        def _delete_alarm(self):
            selection = self.alarm_list.curselection()
            if not selection:
                return
            del self.alarms[selection[0]]
            self._refresh_alarm_list()

        def _refresh_alarm_list(self):
            self.alarm_list.delete(0, "end")
            for alarm in self.alarms:
                self.alarm_list.insert(
                    "end", "%s  %s" % (alarm["time"], alarm["label"]))

        def _check_alarms(self, now):
            today = now.date().isoformat()
            # Forget keys from earlier days so the set stays small.
            self._fired_alarms = {
                key for key in self._fired_alarms if key[0] == today}
            for index, alarm in enumerate(self.alarms):
                # The fired key is per alarm, not one slot shared by
                # all of them: with a single shared (date, time) key,
                # a second alarm set for the same minute never rang.
                # The index is part of the key too, so two alarms with
                # the same time and the same label still ring separately.
                key = (today, index, alarm["time"])
                if alarm_due(alarm, now) and key not in self._fired_alarms:
                    self._fired_alarms.add(key)
                    beep()
                    if messagebox is not None:
                        messagebox.showinfo(
                            "Alarm",
                            "%s: %s" % (alarm["time"], alarm["label"]))

        def _draw_analog(self, now):
            canvas = self.analog_canvas
            theme = THEMES[self.theme_name]
            canvas.delete("all")
            cx, cy = 120, 120
            canvas.create_oval(10, 10, 230, 230, outline=theme["fg"], width=2)
            for hour_mark in range(12):
                angle = hour_mark * 30
                outer = hand_endpoint(cx, cy, 108, angle)
                inner = hand_endpoint(cx, cy, 96, angle)
                canvas.create_line(outer[0], outer[1], inner[0], inner[1],
                                   fill=theme["fg"], width=2)
            hour_angle, minute_angle, second_angle = hand_angles(now)
            for angle, length, width, colour in (
                    (hour_angle, 55, 5, theme["fg"]),
                    (minute_angle, 85, 3, theme["fg"]),
                    (second_angle, 95, 1, theme["accent"])):
                end = hand_endpoint(cx, cy, length, angle)
                canvas.create_line(cx, cy, end[0], end[1],
                                   fill=colour, width=width)
            canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                               fill=theme["accent"], outline=theme["accent"])

        # -- theming -------------------------------------------------------

        def apply_theme(self):
            theme = THEMES[self.theme_name]
            bg_key = "bg_day" if self._palette == "day" else "bg_night"
            bg = theme[bg_key]
            self.root.configure(bg=bg)
            for widget in (self.title_bar, self.tab_bar, self.clock_frame):
                widget.configure(bg=bg)
            self.title_label.configure(bg=bg, fg=theme["fg"])
            for button in (self.min_button, self.close_button):
                button.configure(bg=bg, fg=theme["fg"],
                                 activebackground=theme["button"],
                                 activeforeground=theme["fg"])
            for mode, button in self.tab_buttons.items():
                button.configure(
                    bg=theme["button"] if mode == self.mode else bg,
                    fg=theme["button_fg"],
                    activebackground=theme["button"],
                    activeforeground=theme["button_fg"])
            self.theme_button.configure(
                text="\U0001f3a8 " + self.theme_name,
                bg=bg, fg=theme["accent"],
                activebackground=theme["button"],
                activeforeground=theme["accent"])
            self.time_label.configure(bg=bg, fg=theme["fg"])
            self.date_label.configure(bg=bg, fg=theme["muted"])
            self.analog_canvas.configure(bg=bg)
            self.stopwatch_frame.configure(bg=bg)
            self.sw_label.configure(bg=bg, fg=theme["fg"])
            self.sw_button_row.configure(bg=bg)
            for button in (self.sw_start_button, self.sw_lap_button,
                           self.sw_reset_button):
                button.configure(bg=theme["button"], fg=theme["button_fg"],
                                 activebackground=theme["button"],
                                 activeforeground=theme["button_fg"])
            self.sw_laps.configure(bg=bg, fg=theme["fg"],
                                   selectbackground=theme["button"])
            self.alarms_frame.configure(bg=bg)
            for widget in (self.alarm_hint,):
                widget.configure(bg=bg, fg=theme["muted"])
            for widget in (self.alarm_time_entry, self.alarm_label_entry):
                widget.configure(bg=theme["button"], fg=theme["button_fg"],
                                 insertbackground=theme["button_fg"])
            for button in (self.alarm_add_button, self.alarm_delete_button):
                button.configure(bg=theme["button"], fg=theme["button_fg"],
                                 activebackground=theme["button"],
                                 activeforeground=theme["button_fg"])
            self.alarm_list.configure(bg=bg, fg=theme["fg"],
                                      selectbackground=theme["button"])
            self.world_frame.configure(bg=bg)
            for name_label, time_label in self.world_labels.values():
                name_label.master.configure(bg=bg)
                name_label.configure(bg=bg, fg=theme["muted"])
                time_label.configure(bg=bg, fg=theme["fg"])

        # -- main loop -----------------------------------------------------

        def _tick(self):
            now = datetime.now()
            self.time_label.configure(text=format_time(now))
            self.date_label.configure(text=format_date(now))
            self._draw_analog(now)
            self.sw_label.configure(
                text=format_stopwatch(self._sw_current_elapsed()))
            for city, offset in WORLD_CLOCK_OFFSETS.items():
                city_time = world_clock_time(now, offset)
                label = self.world_labels[city][1]
                label.configure(text=format_time(city_time))
            self._check_alarms(now)
            palette = palette_for_hour(now.hour)
            if palette != self._palette:
                self._palette = palette
                self.apply_theme()
            self.root.after(200, self._tick)

        def close(self):
            self._save_settings()
            self.root.destroy()


def main():
    """Entry point: refuse to run headless without Tkinter, else start the app."""
    if tk is None:
        print("Tkinter is not available. On Ubuntu/Debian, install it with:",
              file=sys.stderr)
        print("    sudo apt install python3-tk", file=sys.stderr)
        return 1
    settings = load_settings(settings_path())
    root = tk.Tk()
    root.title("Extraordinary Digital Clock")
    DigitalClockApp(root, settings)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
