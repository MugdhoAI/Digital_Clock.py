"""Unit tests for the pure helpers in Digital_Clock.py.

These tests need no display: they only exercise the functions that do
not touch Tkinter. Run them from the repository root with::

    python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Digital_Clock as clock


class TestFormatting(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(clock.format_time(datetime(2026, 11, 9, 8, 5, 3)),
                         "08:05:03")
        self.assertEqual(clock.format_time(datetime(2026, 11, 9, 0, 0, 0)),
                         "00:00:00")
        self.assertEqual(clock.format_time(datetime(2026, 11, 9, 23, 59, 59)),
                         "23:59:59")

    def test_format_date(self):
        self.assertEqual(clock.format_date(datetime(2026, 11, 9)),
                         "Monday, 09 November 2026")

    def test_format_stopwatch_seconds(self):
        self.assertEqual(clock.format_stopwatch(0), "00:00.00")
        self.assertEqual(clock.format_stopwatch(5.5), "00:05.50")
        self.assertEqual(clock.format_stopwatch(65.25), "01:05.25")
        self.assertEqual(clock.format_stopwatch(599.99), "09:59.99")

    def test_format_stopwatch_hours(self):
        self.assertEqual(clock.format_stopwatch(3600), "01:00:00.00")
        self.assertEqual(clock.format_stopwatch(3661.5), "01:01:01.50")

    def test_format_stopwatch_negative(self):
        with self.assertRaises(ValueError):
            clock.format_stopwatch(-1)


class TestWorldClock(unittest.TestCase):
    def test_positive_offset(self):
        now = datetime(2026, 11, 9, 12, 0, 0)
        self.assertEqual(clock.world_clock_time(now, 6),
                         datetime(2026, 11, 9, 18, 0, 0))

    def test_negative_offset_crosses_midnight(self):
        now = datetime(2026, 11, 9, 2, 0, 0)
        self.assertEqual(clock.world_clock_time(now, -5),
                         datetime(2026, 11, 8, 21, 0, 0))

    def test_configured_cities(self):
        self.assertEqual(clock.WORLD_CLOCK_OFFSETS["Dhaka"], 6)
        self.assertEqual(clock.WORLD_CLOCK_OFFSETS["Seoul"], 9)
        self.assertEqual(clock.WORLD_CLOCK_OFFSETS["Riyadh"], 3)
        self.assertEqual(clock.WORLD_CLOCK_OFFSETS["Berlin"], 1)
        self.assertEqual(clock.WORLD_CLOCK_OFFSETS["Dublin"], 0)


class TestAlarms(unittest.TestCase):
    def test_parse_alarm_time(self):
        self.assertEqual(clock.parse_alarm_time("7:30"), "07:30")
        self.assertEqual(clock.parse_alarm_time(" 23:59 "), "23:59")
        self.assertEqual(clock.parse_alarm_time("00:00"), "00:00")

    def test_parse_alarm_time_rejects_bad_input(self):
        for bad in ("", "7", "7:30:00", "24:00", "12:60", "ab:cd", "7-30"):
            with self.assertRaises(ValueError, msg=bad):
                clock.parse_alarm_time(bad)

    def test_alarm_due(self):
        alarm = {"time": "07:30", "label": "Wake up", "enabled": True}
        self.assertTrue(clock.alarm_due(alarm, datetime(2026, 11, 9, 7, 30, 0)))
        self.assertTrue(clock.alarm_due(alarm, datetime(2026, 11, 9, 7, 30, 45)))
        self.assertFalse(clock.alarm_due(alarm, datetime(2026, 11, 9, 7, 31, 0)))
        self.assertFalse(clock.alarm_due(alarm, datetime(2026, 11, 9, 8, 30, 0)))

    def test_alarm_due_disabled(self):
        alarm = {"time": "07:30", "label": "Wake up", "enabled": False}
        self.assertFalse(clock.alarm_due(alarm, datetime(2026, 11, 9, 7, 30, 0)))


@unittest.skipIf(clock.tk is None, "Tkinter is not available")
class TestAlarmFiring(unittest.TestCase):
    """Exercise DigitalClockApp._check_alarms without a display.

    The app object is created without __init__ (so no window is built),
    and the module level beep/messagebox are replaced with recorders.
    """

    def setUp(self):
        self.beeps = []
        self.popups = []
        self._real_beep = clock.beep
        self._real_messagebox = clock.messagebox
        clock.beep = lambda: self.beeps.append(1)

        popups = self.popups

        class FakeMessagebox:
            @staticmethod
            def showinfo(title, message):
                popups.append(message)

        clock.messagebox = FakeMessagebox

    def tearDown(self):
        clock.beep = self._real_beep
        clock.messagebox = self._real_messagebox

    def make_app(self, alarms):
        app = clock.DigitalClockApp.__new__(clock.DigitalClockApp)
        app.alarms = alarms
        app._last_fired = None     # fired-state attribute before the fix
        app._fired_alarms = set()  # fired-state attribute after the fix
        return app

    def test_two_alarms_in_the_same_minute_both_fire(self):
        # Regression test: the fired key used to be one (date, time)
        # slot shared by every alarm, so the second alarm set for
        # 07:30 was silently swallowed.
        app = self.make_app([
            {"time": "07:30", "label": "Wake up", "enabled": True},
            {"time": "07:30", "label": "Take medicine", "enabled": True},
        ])
        app._check_alarms(datetime(2026, 11, 9, 7, 30, 0))
        self.assertEqual(len(self.beeps), 2)
        self.assertEqual(len(self.popups), 2)
        self.assertTrue(any("Wake up" in p for p in self.popups))
        self.assertTrue(any("Take medicine" in p for p in self.popups))

    def test_alarm_rings_once_per_minute(self):
        app = self.make_app([
            {"time": "07:30", "label": "Wake up", "enabled": True},
        ])
        app._check_alarms(datetime(2026, 11, 9, 7, 30, 0))
        app._check_alarms(datetime(2026, 11, 9, 7, 30, 45))
        self.assertEqual(len(self.beeps), 1)

    def test_alarm_fires_again_the_next_day(self):
        app = self.make_app([
            {"time": "07:30", "label": "Wake up", "enabled": True},
        ])
        app._check_alarms(datetime(2026, 11, 9, 7, 30, 0))
        app._check_alarms(datetime(2026, 11, 10, 7, 30, 0))
        self.assertEqual(len(self.beeps), 2)


class TestAnalogGeometry(unittest.TestCase):
    def test_hand_angles(self):
        self.assertEqual(clock.hand_angles(datetime(2026, 11, 9, 3, 0, 0)),
                         (90.0, 0.0, 0))
        self.assertEqual(clock.hand_angles(datetime(2026, 11, 9, 12, 0, 0)),
                         (0.0, 0.0, 0))
        self.assertEqual(clock.hand_angles(datetime(2026, 11, 9, 6, 30, 0)),
                         (195.0, 180.0, 0))

    def test_hand_endpoint_cardinal_points(self):
        cases = (
            (0, (120.0, 20.0)),
            (90, (220.0, 120.0)),
            (180, (120.0, 220.0)),
            (270, (20.0, 120.0)),
        )
        for angle, expected in cases:
            got = clock.hand_endpoint(120, 120, 100, angle)
            self.assertAlmostEqual(got[0], expected[0], places=9)
            self.assertAlmostEqual(got[1], expected[1], places=9)


class TestThemes(unittest.TestCase):
    def test_palette_for_hour(self):
        self.assertEqual(clock.palette_for_hour(6), "day")
        self.assertEqual(clock.palette_for_hour(12), "day")
        self.assertEqual(clock.palette_for_hour(17), "day")
        self.assertEqual(clock.palette_for_hour(18), "night")
        self.assertEqual(clock.palette_for_hour(0), "night")
        self.assertEqual(clock.palette_for_hour(23), "night")

    def test_next_theme_cycles(self):
        self.assertEqual(clock.next_theme("Cyberpunk"), "Minimal Light")
        self.assertEqual(clock.next_theme("Minimal Light"), "Old Money")
        self.assertEqual(clock.next_theme("Old Money"), "Cyberpunk")
        self.assertEqual(clock.next_theme("Unknown"), "Cyberpunk")

    def test_all_themes_have_all_keys(self):
        keys = {"bg", "bg_day", "bg_night", "fg", "accent", "muted",
                "button", "button_fg"}
        for name, theme in clock.THEMES.items():
            self.assertEqual(set(theme), keys, name)


class TestSettings(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        settings = clock.load_settings("/nonexistent/settings.json")
        self.assertEqual(settings, clock.DEFAULT_SETTINGS)

    def test_corrupt_file_returns_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as handle:
            handle.write("{not json")
            path = handle.name
        try:
            self.assertEqual(clock.load_settings(path),
                             clock.DEFAULT_SETTINGS)
        finally:
            os.unlink(path)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            stored = {"theme": "Old Money", "geometry": "400x500+10+20",
                      "mode": "Stopwatch"}
            self.assertTrue(clock.save_settings(path, stored))
            self.assertEqual(clock.load_settings(path), stored)

    def test_unknown_theme_and_mode_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"theme": "Nope", "mode": "Nope",
                           "geometry": "400x500+10+20"}, handle)
            settings = clock.load_settings(path)
            self.assertEqual(settings["theme"], "Cyberpunk")
            self.assertEqual(settings["mode"], "Clock")
            self.assertEqual(settings["geometry"], "400x500+10+20")

    def test_beep_does_not_raise(self):
        clock.beep()


if __name__ == "__main__":
    unittest.main()
