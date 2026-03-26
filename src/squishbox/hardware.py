#!/usr/bin/env python3
"""SquishBox Raspberry Pi hardware interface.

Provides low-level access to GPIO-backed hardware components used by
SquishBox, including buttons, rotary encoders, LCD display, and outputs.

Also implements event-driven input handling and a buffered LCD rendering
system with support for scrolling, blinking, and custom glyphs.

Requires:
    - gpiod
"""
from contextlib import contextmanager
from datetime import timedelta
from threading import Thread
import time

import gpiod

from .config import CONFIG


ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]


class _Control:
    """Base class for input controls with event binding.

    Provides a simple event → callback mapping. Subclasses trigger
    events (e.g. "tap", "left") which invoke the bound functions.
    """

    def __getitem__(self, val):
        """Return the bound callback for an event (or no-op if unbound)."""
        return self._actions.get(val, lambda: None)

    def bind(self, event, func):
        """Bind a callback function to an event.

        Args:
            event: Event name (string).
            func: Callable to invoke, or None to remove binding.
        """
        if func == None:
            self._actions.pop(event, None)
        else:
            self._actions[event] = func

    def clear_binds(self):
        """Remove all event bindings."""
        self._actions = {}


class Button(_Control):
    """GPIO button with tap/hold detection.

    Monitors a GPIO input line and emits events based on press duration.

    Events:
        "down": button pressed
        "up": button released
        "tap": short press
        "hold": long press (duration >= CONFIG["hold_time"])
    """
    UP, DOWN, HELD = 0, 1, 2

    def __init__(self, pin, pull_up=CONFIG["pull_up"]):
        """Initialize button input and start event watcher thread.

        Args:
            pin: GPIO pin number.
            pull_up: Whether to enable pull-up (else pull-down).
        """
        if pull_up:
            bias = gpiod.line.Bias.PULL_UP
        else:
            bias = gpiod.line.Bias.PULL_DOWN
        line = gpiod.request_lines(
            CONFIG["gpio_chip"],
            consumer="squishbox",
            config={
                pin: gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    edge_detection=gpiod.line.Edge.BOTH,
                    bias=bias,
                    debounce_period=timedelta(
                        seconds=CONFIG["button_debounce"]
                    )
                )
            }
        )
        self._state = self.UP
        self._actions = {}
        self._watching = True
        t = Thread(
            target=lambda: self._watch(line, pin, pull_up),
            daemon=True
        )
        t.start()

    def _watch(self, line, pin, pull_up):
        if pull_up:
            connect = gpiod.EdgeEvent.Type.FALLING_EDGE
            disconnect = gpiod.EdgeEvent.Type.RISING_EDGE
        else:
            connect = gpiod.EdgeEvent.Type.RISING_EDGE
            disconnect = gpiod.EdgeEvent.Type.FALLING_EDGE
        while self._watching:
            for event in line.read_edge_events():
                if event.event_type is connect:
                    self._state = self.DOWN
                    self["down"]()
                    if not line.wait_edge_events(CONFIG["hold_time"]):
                        self._state = self.HELD
                        self["hold"]()
                elif event.event_type is disconnect:
                    self["up"]()
                    if self._state == self.DOWN:
                        self["tap"]()
                    self._state = self.UP


class Encoder(_Control):
    """Quadrature rotary encoder.

    Detects rotation direction using two GPIO inputs.

    Events:
        "left": counterclockwise rotation
        "right": clockwise rotation
    """
    
    def __init__(self, pin1, pin2, pull_up=CONFIG["pull_up"]):
        """Initialize encoder inputs and start watcher thread.

        Args:
            pin1: First GPIO pin.
            pin2: Second GPIO pin.
            pull_up: Whether to enable pull-up resistors.
        """
        if pull_up:
            bias = gpiod.line.Bias.PULL_UP
        else:
            bias = gpiod.line.Bias.PULL_DOWN
        lines = gpiod.request_lines(
            CONFIG["gpio_chip"],
            consumer="squishbox",
            config={
                (pin1, pin2): gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    edge_detection=gpiod.line.Edge.BOTH,
                    bias=bias,
                    debounce_period=timedelta(
                        seconds=CONFIG["encoder_debounce"]
                    )
                )
            }
        )
        self._edges = (0, 0)
        self._actions = {}
        self._watching = True
        t = Thread(
            target=lambda: self._watch(lines, pin1, pin2, pull_up),
            daemon=True
        )
        t.start()

    def _watch(self, lines, pin1, pin2, pull_up):
        s = int(pull_up)
        while self._watching:
            for event in lines.read_edge_events():
                if event.event_type is event.Type.RISING_EDGE:
                    self._edges = (self._edges[-1], event.line_offset)
                elif event.event_type is event.Type.FALLING_EDGE:
                    self._edges = (self._edges[-1], -event.line_offset)
                if self._edges == (s * pin1, s * pin2):
                    self["left"]()
                elif self._edges == (s * pin2, s * pin1):
                    self["right"]()


class Output:
    """Digital (on/off) GPIO output."""

    def __init__(self, pin, on=False):
        """Initialize output pin.

        Args:
            pin: GPIO pin number.
            on: Initial state (True = active).
        """
        self._pin = pin
        if on:
            val = gpiod.line.Value.ACTIVE
        else:
            val = gpiod.line.Value.INACTIVE
        self._line = gpiod.request_lines(
            CONFIG["gpio_chip"],
            consumer="squishbox",
            config={
                pin: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                    output_value=val
                )
            }
        )

    def on(self):
        """Set output to active (HIGH)."""
        self._line.set_value(self._pin, gpiod.line.Value.ACTIVE)
        
    def off(self):
        """Set output to inactive (LOW)."""
        self._line.set_value(self._pin, gpiod.line.Value.INACTIVE)


class PWMOutput:
    """Software PWM output using a background thread.

    Generates a PWM signal by toggling a GPIO line at a fixed frequency.
    Duty cycle is controlled via the `level` attribute (0–100).
    """

    def __init__(self, pin, freq=2000, level=0):
        """Initialize PWM output and start PWM thread.

        Args:
            pin: GPIO pin number.
            freq: PWM frequency in Hz.
            level: Duty cycle percentage (0–100).
        """
        self.freq = freq
        self.level = level
        self._line = gpiod.request_lines(
            CONFIG["gpio_chip"],
            consumer="squishbox",
            config={
                pin: gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                )
            }
        )
        self._active = True
        t = Thread(target=lambda: self._pwm(pin), daemon=True)
        t.start()

    def _pwm(self, pin):
        while self._active:
            period = 1 / self.freq
            t_on = period * self.level / 100
            if self.level > 0:
                self._line.set_value(pin, gpiod.line.Value.ACTIVE)
                time.sleep(t_on)
            if self.level < 100:
                self._line.set_value(pin, gpiod.line.Value.INACTIVE)
                time.sleep(period - t_on)


class LCD_HD44780:
    """HD44780-compatible character LCD driver.

    Provides buffered text rendering with support for:
      - Static text
      - Scrolling text (for long lines)
      - Timed/blinking overlays
      - Custom glyphs (up to 8 hardware slots)

    Rendering is layered and only updates changed characters to
    minimize GPIO traffic.
    """
    _printable = """\
abcdefghijklmnopqrstuvwxyz\
ABCDEFGHIJKLMNOPQRSTUVWXYZ\
0123456789-_./!\
@#$%^&*|?,;:'"`+=<>()[]{}"""
    _glyphs = {
        "backslash": """\
-----
X----
-X---
--X--
---X-
----X
-----
-----""",
        "tilde": """\
-----
-----
-----
-XX-X
X--X-
-----
-----
-----"""}
    glyph2char = (
        ("backslash", "\\"),
        ("tilde", "~")
    )

    def __init__(self, regsel, enable, data):
        self.regsel = regsel
        self.enable = enable
        self.data = data
        self.buffered = False
        self._spinning = False
        # set up LCD GPIO
        self._lines = gpiod.request_lines(
            CONFIG["gpio_chip"],
            consumer="squishbox",
            config={
                (regsel, enable, *data): gpiod.LineSettings(
                    direction=gpiod.line.Direction.OUTPUT,
                )
            }
        )
        # initialize LCD
        for val in (0x33, 0x32, 0x28, 0x0c, 0x06):
            self._send(val)
        self.clear()
        # set up glyphs
        for name, text in CONFIG["glyphs_5x8"].items():
            self._glyphs[name] = text
        self._chars = {"solid": 255}
        self._used = []

    def printable(self):
        """Return full set of printable characters supported by the LCD."""
        return self._printable + self["backslash"] + self["tilde"] + " "

    def fnchars(self):
       """Return reduced character set suitable for filenames."""
        return self._printable[:67] + self["backslash"] + " "

    def __setitem__(self, name, text):
        """Define or update a custom glyph.

        Args:
            name: Glyph name.
            text: 5x8 bitmap string using 'X' (on) and '-' (off).
        """
        self._glyphs[name] = text
        self._chars.pop(name, None)

    def __getitem__(self, name):
        """Return character for a named glyph.

        Loads the glyph into LCD memory if not already present.
        Uses LRU replacement when all 8 custom slots are occupied.

        Returns:
            Single-character string usable in display text.
        """
        if name not in self._chars:
            free = set(range(8)) - set(self._chars.values())
            if free:
                loc = list(free)[0]
            else:
                loc = self._chars.pop(self._used.pop(0), 0)
            self._load_glyph(loc, self._glyphs[name])
            self._chars[name] = loc
        if self._chars[name] < 8:
            if name in self._used:
                self._used.remove(name)
            self._used.append(name)
            if len(self._used) > 8:
                self._used.pop(0)
        return chr(self._chars[name])

    def clear(self):
        """Clear the display and reset all rendering layers.

        Also resets scrolling state, blinking timers, and cursor position.
        """
        self._send(0x01)
        self.setcursorpos(0, 0)
        time.sleep(40 * CONFIG["lcd_exec_time"])
        self._layers = {x: [[""] * COLS for _ in range(ROWS)]
                        for x in ("displayed", "scrollbuffer", "scrolling", "static", "blinking")}
        self._blinktimer = [[0] * COLS for _ in range(ROWS)]
        self._scrollpos = [0] * ROWS
        self._scrolltimer = time.time()

    def write(self, text, row, col=0, align="", timeout=0, force=True):
        """Write text to the LCD using layered rendering.

        Behavior depends on text length and parameters:
          - Long text is placed in scroll buffer
          - timeout > 0 creates temporary (blinking) overlay
          - Otherwise writes to static layer

        Args:
            text: String to display.
            row: Target row.
            col: Starting column.
            align: "left", "right", or default (no alignment).
            timeout: Duration for temporary text (seconds).
            force: Overwrite existing timed text if True.
        """
        for name, char in self.glyph2char:
            text = text.replace(char, self[name])
        if len(text) > COLS:
            self._layers["scrollbuffer"][row] = list(text)
            self._layers["blinking"][row] = [""] * COLS
            self._layers["static"][row] = [""] * COLS
            if align == "right":
                self._scrollpos[row] = len(text) - COLS
            else:
                self._scrollpos[row] = -CONFIG["scroll_pause"]
        elif timeout:
            if align == "left":
                text = text[:COLS]
                col = 0
            if align == "right":
                text = text[-COLS:]
                col = COLS - len(text)
            else:
                text = text[:COLS - col]
            for i, char in enumerate(text):
                if force or self._layers["blinking"][row][col + i] == "":
                    self._blinktimer[row][col + i] = time.time() + timeout
                    self._layers["blinking"][row][col + i] = char
        else:
            if align == "left":
                self._layers["static"][row][:len(text)] = list(text)
                self._layers["blinking"][row][:len(text)] = [""] * len(text)
            elif align == "right":
                self._layers["static"][row][COLS - len(text):] = list(text)
                self._layers["blinking"][row][COLS - len(text):] = [""] * len(text)
            else:
                n = min(len(text), COLS - col)
                self._layers["static"][row][col:col + n] = list(text[:n])
                self._layers["blinking"][row][col:col + n] = [""] * n
        if not self.buffered:
            self.update()

    def update(self):
        """Render buffered content to the LCD.

        Handles:
          - Scrolling updates
          - Expiring timed/blinking text
          - Layer compositing

        Does nothing if activity spinner is active.
        """
        if self._spinning:
            return
        t = time.time()
        for row in range(ROWS):
            if any(self._layers["scrollbuffer"][row]):
                scrollmax = len(self._layers["scrollbuffer"][row]) - COLS
                if t > self._scrolltimer:
                    self._scrollpos[row] += 1
                    if self._scrollpos[row] > scrollmax + CONFIG["scroll_pause"]:
                        self._scrollpos[row] = -CONFIG["scroll_pause"]
                i = min(max(0, self._scrollpos[row]), scrollmax)
                self._layers["scrolling"][row] = self._layers["scrollbuffer"][row][i:i + COLS]
            if any(self._layers["blinking"][row]):
                for col, btime in enumerate(self._blinktimer[row]):
                    if btime and t > btime:
                        self._layers["blinking"][row][col] = ""
            chars = [" "] * COLS
            for x in ("scrolling", "static", "blinking"):
                for col in range(COLS):
                    if self._layers[x][row][col] != "":
                        chars[col] = self._layers[x][row][col]
            self._putchars(chars, row, 0)
        if t > self._scrolltimer:
            self._scrolltimer += CONFIG["scroll_time"]

    def setcursorpos(self, row, col):
        """Set cursor position.

        Args:
            row: Row index.
            col: Column index.
        """
        if row < ROWS and col < COLS:
            offset = (0x00, 0x40, COLS, 0x40 + COLS)
            self._send(0x80 | offset[row] + col)

    def setcursormode(self, mode):
        """Set cursor display mode.

        Args:
            mode: One of:
                "hide"  – no cursor
                "blink" – blinking block cursor
                "line"  – underline cursor
        """
        if mode == "hide":
            self._send(0x0c)
        elif mode == "blink":
            self._send(0x0d)
        elif mode == "line":    
            self._send(0x0e)

    @contextmanager
    def activity(self, msg=None):
        """Shows an animation while another process runs
        
        Runs in a ``with`` statement. Displays a spinning character
        in the lower right corner of the LCD to give feedback while a
        long-running process completes.

        Args:
          msg: text to display
        """
        if msg:
            self.write(msg, row=ROWS - 1)
        if not self._spinning:
            self._spinning = True
            self._spin = Thread(target=self._activitywheel_spin)
            self._spin.start()
        try:
            yield
        finally:
            self._spinning = False
            self._spin.join()
    
    def _activitywheel_spin(self):
        c = self._layers["displayed"][ROWS - 1][COLS - 1]
        i = 0
        while self._spinning:
            s = (self["backslash"] + "|/-")[i]
            self._putchars(s, ROWS - 1, COLS - 1)
            time.sleep(CONFIG["frame_time"])
            i = (i + 1) % 4
        self._putchars(c, ROWS - 1, COLS - 1)

    def _load_glyph(self, loc, text):
        bits = text.replace("\n", "").replace("-", "0").replace("X", "1")
        glyphbytes = [int(bits[i:i + 5], 2) for i in range(0, 40, 5)]
        self._send(0x40 | loc << 3)
        for b in glyphbytes:
            self._send(b, gpiod.line.Value.ACTIVE)

    def _putchars(self, chars, row, col):
        lastcol = -2
        for c in chars:
            if c and self._layers["displayed"][row][col] != c:
                if lastcol != col - 1:
                    self.setcursorpos(row, col)
                self._send(ord(c), gpiod.line.Value.ACTIVE)
                self._layers["displayed"][row][col] = c
                lastcol = col
            col += 1

    def _send(self, val, reg=gpiod.line.Value.INACTIVE):
        if self.regsel == 0:
            return
        self._lines.set_value(self.regsel, reg)
        self._lines.set_value(self.enable, gpiod.line.Value.INACTIVE)
        for nib in (val >> 4, val):
            line_vals = {}
            for i in range(4):
                if nib >> i & 1:
                    line_vals[self.data[i]] = gpiod.line.Value.ACTIVE
                else:
                    line_vals[self.data[i]] = gpiod.line.Value.INACTIVE
            self._lines.set_values(line_vals)
            self._lines.set_value(self.enable, gpiod.line.Value.ACTIVE)
            time.sleep(CONFIG["lcd_exec_time"])
            self._lines.set_value(self.enable, gpiod.line.Value.INACTIVE)

