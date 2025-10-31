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

    printable = """\
abcdefghijklmnopqrstuvwxyz\
ABCDEFGHIJKLMNOPQRSTUVWXYZ\
0123456789-_./!\
@#$%^&*|?,;:'"`+=<>()[]{}"""
    glyph2char = (
        ("backslash", "\\"),
        ("tilde", "~")
    )

    def __init__(self, regsel, enable, data):
        self.regsel = regsel
        self.enable = enable
        self.data = data
        self._buffered = False
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
        self.glyphs = {"solid": chr(255)}
        self.default_custom_glyphs()
        self.CHARS = self.printable + self.glyphs["backslash"] + self.glyphs["tilde"] + " "
        self.FCHARS = self.printable[:67] + self.glyphs["backslash"] + " " # allowable filename characters

    def clear(self):
        """Clear the LCD, initialize layers"""
        self._send(0x01)
        self.setcursorpos(0, 0)
        time.sleep(40 * CONFIG["lcd_exec_time"])
        self._layers = [[[""] * COLS for _ in range(ROWS)] for _ in range(5)]
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
# self._layers:
# 0 - scrolled text
# 1 - static text
# 2 - blinking text
# 3 - scroll buffer
# 4 - LCD contents
        for name, char in self.glyph2char:
            text = text.replace(char, self.glyphs[name])
        if len(text) > COLS:
            self._layers[3][row] = list(text)
            self._layers[2][row] = [""] * COLS
            self._layers[1][row] = [""] * COLS
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
                if force or self._layers[2][row][col + i] == "":
                    self._blinktimer[row][col + i] = time.time() + timeout
                    self._layers[2][row][col + i] = char
        else:
            if align == "left":
                self._layers[1][row][:len(text)] = list(text)
                self._layers[2][row][:len(text)] = [""] * len(text)
            elif align == "right":
                self._layers[1][row][COLS - len(text):] = list(text)
                self._layers[2][row][COLS - len(text):] = [""] * len(text)
            else:
                n = min(len(text), COLS - col)
                self._layers[1][row][col:col + n] = list(text[:n])
                self._layers[2][row][col:col + n] = [""] * n
        if not self._buffered:
            self.update()

    def update(self):
        """Updates the LCD"""
        t = time.time()
        for row in range(ROWS):
            if any(self._layers[3][row]):
                scrollmax = len(self._layers[3][row]) - COLS
                if t > self._scrolltimer:
                    self._scrollpos[row] += 1
                    if self._scrollpos[row] > scrollmax + CONFIG["scroll_pause"]:
                        self._scrollpos[row] = -CONFIG["scroll_pause"]
                i = min(max(0, self._scrollpos[row]), scrollmax)
                self._layers[0][row] = self._layers[3][row][i:i + COLS]
            if any(self._layers[2][row]):
                for col, btime in enumerate(self._blinktimer[row]):
                    if btime and t > btime:
                        self._layers[2][row][col] = ""
            chars = [""] * COLS
            for i in range(3):
                for col in range(COLS):
                    if self._layers[i][row][col] != "":
                        chars[col] = self._layers[i][row][col]
            self._putchars(chars, row, 0)
        if t > self._scrolltimer:
            self._scrolltimer += CONFIG["scroll_time"]

    def define_glyph(self, name, loc, text):
        """Instate a custom LCD glyph from ascii art
        
        Args:
          name: descriptive name for the glyph
          loc: the memory location for the glyph (0-7)
          text: a string representing the 40 pixels of the glyph
            (8 rows times 5 columns) with hash marks (#) and dots (.)
            Spaces and newlines are ignored, so this can be a
            multiline string
            
        Returns:
          a character that can be used to write the glyph on the LCD
        """
        if loc < 0 or loc > 7:
            raise ValueError("Custom character location outside range (0-7)")
        bits = text.replace(" ", "").replace("\n", "").replace(".", "0").replace("#", "1")
        glyphbytes = [int(bits[i:i + 5], 2) for i in range(0, 40, 5)]
        self._send(0x40 | loc << 3)
        for b in glyphbytes:
            self._send(b, gpiod.line.Value.ACTIVE)
        self.glyphs[name] = chr(loc)

    def default_custom_glyphs(self):
        """Re-initialize standard custom glyphs"""
        self.define_glyph("backslash", 0,
            """.....
               #....
               .#...
               ..#..
               ...#.
               ....#
               .....
               ....."""
        )
        self.define_glyph("tilde", 1,
            """.....
               .....
               .....
               .##.#
               #..#.
               .....
               .....
               ....."""
        )
        self.define_glyph("check", 2,
            """.....
               ....#
               ...##
               #.##.
               ###..
               .#...
               .....
               ....."""
        )
        self.define_glyph("cross", 3, 
            """.....
               ##.##
               .###.
               ..#..
               .###.
               ##.##
               .....
               ....."""
        )
        self.define_glyph("folder", 4, 
            """.....
               .....
               ##...
               #.###
               #...#
               #...#
               #####
               ....."""
        )
        self.define_glyph("wifi_on", 5, 
            """.###.
               #...#
               ..#..
               .#.#.
               .....
               ..#..
               .....
               ....."""
        )
        self.define_glyph("wifi_off", 6,
            """.#.#.
               ..#..
               .#.#.
               .....
               ..#..
               .....
               ..#..
               ....."""
        )
        self.define_glyph("note", 7,
            """..#..
               ..##.
               ..#.#
               ..#.#
               ..#..
               ###..
               ###..
               ....."""
        )

    def setcursorpos(self, row, col):
        if row < ROWS and col < COLS:
            offset = (0x00, 0x40, COLS, 0x40 + COLS)
            self._send(0x80 | offset[row] + col)

    def setcursormode(self, mode):
        if mode == "hide":
            #self._send(0x0c | 0x00)
            self._send(0x0c)
        elif mode == "blink":
            self._send(0x0d)
        elif mode == "line":    
            self._send(0x0e)

    def _progresswheel_spin(self):
        c = self._layers[4][ROWS - 1][COLS - 1]
        i = 0
        while self._spinning:
            s = (self.glyphs["backslash"] + "|/-")[i]
            self._putchars(s, ROWS - 1, COLS - 1)
            time.sleep(CONFIG["frame_time"])
            i = (i + 1) % 4
        self._putchars(c, ROWS - 1, COLS - 1)

    def _putchars(self, chars, row, col):
        lastcol = -2
        for c in chars:
            if c and self._layers[4][row][col] != c:
                if lastcol != col - 1:
                    self.setcursorpos(row, col)
                self._send(ord(c), gpiod.line.Value.ACTIVE)
                self._layers[4][row][col] = c
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

