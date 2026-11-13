# Extraordinary Digital Clock

A desktop clock application built with Python and Tkinter. It goes well beyond a
basic `datetime` + `Label` tutorial project into a small multi-feature desktop
app with real UI/UX and software design decisions behind it.

![Digital Clock Screenshot](screenshot.png)

## Features

- **Custom window chrome** — borderless, draggable window with its own
  minimize/close controls instead of relying on the OS title bar.
- **Time of day reactive background** — the gradient shifts color palette
  depending on the current hour (day tones vs. night tones), recalculated
  every 30 seconds.
- **Digital + analog display** — a live analog clock face is drawn on a
  `Canvas` using trigonometry for the hour/minute/second hands, alongside the
  standard digital readout and full date.
- **World clock panel**: six configurable timezones (Dhaka, Seoul, Riyadh,
  Berlin, Dublin, Kolkata by default) shown as fixed UTC offsets, updating
  live alongside the local clock. Offsets may be fractional, so half hour
  zones such as Kolkata (UTC+05:30) work too.
- **Theme switcher** — three built-in themes (Cyberpunk, Minimal Light, Old
  Money) swappable instantly via a click, no restart required.
- **Stopwatch**: start/stop/lap/reset, with a scrolling lap history. Each
  lap shows its split time since the previous lap.
- **Alarms**: set multiple labeled alarms; a popup and audible beep fire
  when one is triggered. Double-click an alarm to enable or disable it.
- **Pomodoro mode**: 25 minute focus sessions with 5 minute breaks, with a
  count of completed focus sessions.
- **Persistent settings**: last-used theme, window position, and active
  mode are saved to `settings.json` and restored on the next launch. Settings
  are written as soon as the theme or mode changes, not only when the app
  closes. A corrupt settings file, or a saved window position the app cannot
  use, falls back to the defaults instead of crashing.

## Why this project (design notes)

This was deliberately built with a class based architecture
(`DigitalClockApp`) rather than flat procedural script logic, to demonstrate:

- Encapsulation of state (theme, alarms, stopwatch) inside a single object
  rather than scattered globals.
- Correct use of Tkinter's event-driven model — `.after()` for scheduled
  updates instead of blocking loops, which is the single most common mistake
  beginners make with GUI programming in Python.
- Basic 2D geometry/trigonometry applied to a real rendering problem (the
  analog clock hands).
- File I/O and state persistence via JSON, mirroring how real desktop apps
  remember user preferences.

## Requirements

- Python 3.8 or later
- Tkinter (bundled with most Python installations; on Ubuntu/Debian, install
  via `sudo apt install python3-tk` if it's missing)
- `winsound` is used for the alarm beep on Windows automatically; on macOS/
  Linux the app falls back to a terminal bell instead of crashing.

No third party packages are required — everything here uses the Python
standard library. World clock times use fixed UTC offsets rather than a
timezone database, so no `tzdata` install is needed. The trade-off: offsets
are hardcoded to each city's current standard, so they will be off by an
hour during daylight saving time transitions until manually updated in
`WORLD_CLOCK_OFFSETS` at the top of the file.

## Running it

```bash
python Digital_Clock.py
```

The window remembers its last position and theme between runs via
`settings.json`, which is created automatically next to the script on first
launch. This file is user specific runtime state, not source code — it's
listed in `.gitignore` so it won't be committed to the repository.

## Tests

The pure logic lives in functions that do not touch Tkinter, so it is
covered by unit tests that need no display: time formatting, world clock
offsets, stopwatch formatting and lap splits, alarm parsing and toggling,
analog hand geometry, Pomodoro countdown and phases, themes, and settings
load/save.

```bash
python -m unittest discover -s tests -v
```

## Controls

- **Drag** the title bar (or anywhere on the background) to move the window.
- Click **Clock / Stopwatch / Alarms / Pomodoro** tabs to switch modes.
- **Double-click** an alarm in the list to enable or disable it.
- Click the **🎨 theme name** in the top-right of the tab bar to cycle themes.
- Press **Esc** or click **✕** to close the app.

## Possible future additions

- Automatic daylight saving time adjustment for world clock offsets
- Weather integration via a free API alongside the time
- Offline text-to-speech time announcements
- Custom user-added timezones via the UI (currently edited via the
  `WORLD_CLOCK_OFFSETS` dictionary in the source file)

## License

MIT. Feel free to fork and build on this.
