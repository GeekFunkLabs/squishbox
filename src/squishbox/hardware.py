#!/usr/bin/env python3
"""SquishBox Raspberry Pi interface

This module provides classes and functions for creating python applications
for the `SquishBox <https://www.geekfunklabs.com/products/squishbox>`_ ,
a Raspberry Pi add-on that provides an LCD, pushbutton rotary encoder,
PCM5102-based sound card, and MIDI minijacks. Running this module as a
script starts a shell application that lets the user run other applications
and change system-wide settings.

Module-level constants:
  squishbox_cfgpath - yaml configuration file Path
  squishbox_cfg - dict of config values
  squishbox_hardware - singleton instance of SquishBox() class

Requires:
- gpiod
- yaml
"""

from datetime import timedelta
from threading import Thread
import time

import gpiod

from .config import CONFIG


ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]


class _Control:

    def __getitem__(self, val):
        return self._actions.get(val, lambda: None)

    def bind(self, event, func):
        if func == None and event in self._actions:
            del self._actions[event]
        else:
            self._actions[event] = func

    def clear_binds(self):
        self._actions = {}


class Button(_Control):

    UP, DOWN, HELD = 0, 1, 2

    def __init__(self, pin, pull_up=CONFIG["pull_up"]):
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

    def _watch(self, line, pin, pull_up=CONFIG["pull_up"]):
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
    
    def __init__(self, pin1, pin2, pull_up=CONFIG["pull_up"]):
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

    def __init__(self, pin, on=0):
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
        self._line.set_value(self._pin, gpiod.line.Value.ACTIVE)
        
    def off(self):
        self._line.set_value(self._pin, gpiod.line.Value.INACTIVE)


class PWMOutput:

    def __init__(self, pin, freq=2000, level=0):
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
        return self._printable + self["backslash"] + self["tilde"] + " "

    def fnchars(self):
        return self._printable[:67] + self["backslash"] + " "

    def __setitem__(self, name, text):
        self._glyphs[name] = text
        self._chars.pop(name, None)

    def __getitem__(self, name):
        if name not in self._chars:
            if len(self._used) < 8:
                loc = len(self._used)
            else:
                loc = self._chars.pop(self._used[-8])
            self._load_glyph(loc, self._glyphs[name])
            self._chars[name] = loc
        if self._chars[name] < 8 and name not in self._used:
            self._used = self._used[-7:] + [name]
        return chr(self._chars[name])

    def clear(self):
        """Clear the LCD, initialize layers"""
        self._send(0x01)
        self.setcursorpos(0, 0)
        time.sleep(40 * CONFIG["lcd_exec_time"])
        self._layers = {x: [[""] * COLS for _ in range(ROWS)]
                        for x in ("displayed", "scrollbuffer", "scrolling", "static", "blinking")}
        self._blinktimer = [[0] * COLS for _ in range(ROWS)]
        self._scrollpos = [0] * ROWS
        self._scrolltimer = time.time()

    def write(self, text, row, col=0, align="", timeout=0, force=True):
        """Writes text to the LCD
        
        Writes text to the LCD starting at row, col.
        Text wider than the LCD will be scrolled.
        Specifying a timeout writes temporary text.

        Args:
          text: string to write
          row: the row at which to start writing
          col: the column at which to start writing
          align: place text against "left" or "right" edge of LCD
          timeout: seconds to keep text
          force: write over other timed text
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
        """Updates the LCD"""
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
        """set the cursor row and column"""
        if row < ROWS and col < COLS:
            offset = (0x00, 0x40, COLS, 0x40 + COLS)
            self._send(0x80 | offset[row] + col)

    def setcursormode(self, mode):
        """set cursor to blink, line, or hide"""
        if mode == "hide":
            #self._send(0x0c | 0x00)
            self._send(0x0c)
        elif mode == "blink":
            self._send(0x0d)
        elif mode == "line":    
            self._send(0x0e)

    def activity_start(self):
        """Shows an animation while another process runs
        
        Displays a spinning character in the lower right corner of the
        LCD that runs in a thread after this function returns, to give
        the user some feedback while a long-running process completes.
        """
        self._spinning = True
        self._spin = Thread(target=self._activitywheel_spin)
        self._spin.start()
    
    def activity_stop(self):
        """Removes the spinning character"""
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

