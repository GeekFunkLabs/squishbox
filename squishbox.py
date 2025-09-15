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

__version__ = '0.9.0'

from datetime import timedelta
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread
import time
import traceback

import gpiod
import yaml

# hardware-related settings
LCD_RS = 7; LCD_EN = 16; LCD_DATA = 26, 6, 5, 8  # LCD pins
COLS, ROWS = 16, 2                               # LCD display size
CONT_PIN = 12; CONTRAST = 100                    # contrast PWM pin and initial value
BACK_PIN = 13; BACKLIGHT = 100                   # backlight PWM pin and initial value
ROT_L = 22; ROT_R = 27; ROT_BTN = 17             # rotary encoder R/L pins + button
PULL_UP = True                                   # bias for inputs
ACTIVE_HIGH = True                               # active level for outputs
GPIO_CHIP = '/dev/gpiochip4'                     # path to gpio character device
SCRIPTS_DIR = ''                                 # location for squishbox scripts
# UI settings
HOLD_TIME = 1.0                                  # button hold time
SCROLL_TIME = 0.2; SCROLL_PAUSE = 3              # scrolling text options
MENU_TIME = 3.0                                  # menu timeout delay
FRAME_TIME = 0.1                                 # time for a single animation frame
POLL_TIME = 0.01                                 # default button polling interval
BTN_BOUNCE = 0.02                                # button debounce time
ENC_BOUNCE = 0.002                               # encoder debounce time
EXEC_TIME = 50e-6                                # increase if LCD displays garbage


class _SquishBoxControl:

    def __getitem__(self, val):
        return self._actions.get(val, lambda: None)

    def bind(self, event, func):
        if func == None and event in self._actions:
            del self._actions[event]
        else:
            self._actions[event] = func

    def clear_binds(self):
        self._actions = {}


class SquishBoxButton(_SquishBoxControl):

    UP, DOWN, HELD = 0, 1, 2

    def __init__(self, pin, pull_up=PULL_UP):
        if pull_up:
            bias = gpiod.line.Bias.PULL_UP
        else:
            bias = gpiod.line.Bias.PULL_DOWN
        line = gpiod.request_lines(
            GPIO_CHIP,
            consumer="squishbox",
            config={
                pin: gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    edge_detection=gpiod.line.Edge.BOTH,
                    bias=bias,
                    debounce_period=timedelta(seconds=BTN_BOUNCE),
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
                    self['down']()
                    if not line.wait_edge_events(HOLD_TIME):
                        self._state = self.HELD
                        self['hold']()
                elif event.event_type is disconnect:
                    self['up']()
                    if self._state == self.DOWN:
                        self['tap']()
                    self._state = self.UP


class SquishBoxRotEnc(_SquishBoxControl):
    
    def __init__(self, pin1, pin2, pull_up=PULL_UP):
        if pull_up:
            bias = gpiod.line.Bias.PULL_UP
        else:
            bias = gpiod.line.Bias.PULL_DOWN
        lines = gpiod.request_lines(
            GPIO_CHIP,
            consumer="squishbox",
            config={
                (pin1, pin2): gpiod.LineSettings(
                    direction=gpiod.line.Direction.INPUT,
                    edge_detection=gpiod.line.Edge.BOTH,
                    bias=bias,
                    debounce_period=timedelta(seconds=ENC_BOUNCE),
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
                    self['left']()
                elif self._edges == (s * pin2, s * pin1):
                    self['right']()


class SquishBoxOutput:

    def __init__(self, pin, on=0):
        self._pin = pin
        if on:
            val = gpiod.line.Value.ACTIVE
        else:
            val = gpiod.line.Value.INACTIVE
        self._line = gpiod.request_lines(
            GPIO_CHIP,
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


class SquishBoxPWM:

    def __init__(self, pin, freq=2000, level=0):
        self.freq = freq
        self.level = level
        self._line = gpiod.request_lines(
            GPIO_CHIP,
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


class SquishBox:
    """Object representation of the SquishBox hardware"""
    _instance = None

    def __new__(cls):
        print(cls._instance)
        if cls._instance is None:
            cls._instance = super(SquishBox, cls).__new__(cls)
            print(cls._instance)
            self = cls._instance
            """Initializes LCD, encoder, and related GPIO"""
            self._actions = []
            self._buffered = False
            self._wifienabled = self.shell_cmd("nmcli radio wifi") == 'enabled'
            # set up LCD GPIO
            self._lines = gpiod.request_lines(
                GPIO_CHIP,
                consumer="squishbox",
                config={
                    (LCD_RS, LCD_EN, *LCD_DATA):
                        gpiod.LineSettings(direction=gpiod.line.Direction.OUTPUT)
                }
            )
            # initialize LCD
            for val in (0x33, 0x32, 0x28, 0x0c, 0x06):
                self._lcd_send(val)
            self.lcd_clear()
            self.define_custom_glyphs()
            sys.excepthook = lambda _, e, tb: self.display_error(e, tb=tb)
            # add encoder/pushbutton controls
            self.knob1 = SquishBoxRotEnc(ROT_L, ROT_R)
            self.button1 = SquishBoxButton(ROT_BTN)
            self.backlight = SquishBoxPWM(BACK_PIN, level=BACKLIGHT)
            self.contrast = SquishBoxPWM(CONT_PIN, level=CONTRAST)
        return cls._instance

    def lcd_clear(self):
        """Clear the LCD, initialize layers"""
        self._lcd_send(0x01)
        self._lcd_setcursorpos(0, 0)
        time.sleep(40 * EXEC_TIME)
        self._layers = [[[""] * COLS for _ in range(ROWS)] for _ in range(5)]
        self._blinktimer = [[0] * COLS for _ in range(ROWS)]
        self._scrollpos = [0] * ROWS
        self._scrolltimer = time.time()

    def lcd_write(self, text, row, col=0, align='', timeout=0, force=True):
        """Writes text to the LCD
        
        Writes text to the LCD starting at row, col.
        Text wider than the LCD will be scrolled.
        Specifying a timeout writes temporary text.

        Args:
          text: string to write
          row: the row at which to start writing
          col: the column at which to start writing
          align: place text against 'left' or 'right' edge of LCD
          timeout: seconds to keep text
          force: write over other timed text
        """
# self._layers:
# 0 - scrolled text
# 1 - static text
# 2 - blinking text
# 3 - scroll buffer
# 4 - LCD contents
        if len(text) > COLS:
            self._layers[3][row] = list(text)
            self._layers[2][row] = [""] * COLS
            self._layers[1][row] = [""] * COLS
            if align == 'right':
                self._scrollpos[row] = len(text) - COLS
            else:
                self._scrollpos[row] = -SCROLL_PAUSE
        elif timeout:
            if align == 'left':
                text = text[:COLS]
                col = 0
            if align == 'right':
                text = text[-COLS:]
                col = COLS - len(text)
            else:
                text = text[:COLS - col]
            for i, char in enumerate(text):
                if force or self._layers[2][row][col + i] == "":
                    self._blinktimer[row][col + i] = time.time() + timeout
                    self._layers[2][row][col + i] = char
        else:
            if align == 'left':
                self._layers[1][row][:len(text)] = list(text)
                self._layers[2][row][:len(text)] = [""] * len(text)
            elif align == 'right':
                self._layers[1][row][COLS - len(text):] = list(text)
                self._layers[2][row][COLS - len(text):] = [""] * len(text)
            else:
                n = min(len(text), COLS - col)
                self._layers[1][row][col:col + n] = list(text[:n])
                self._layers[2][row][col:col + n] = [""] * n
        if not self._buffered:
            self.update_lcd()

    def update_lcd(self):
        """Updates the LCD
        
        User shouldn't need to call this - it is already called
        by get_action, which is called in all the menu_* functions.
        May be helpful if designing custom menus or displays
        """       
        t = time.time()
        for row in range(ROWS):
            if any(self._layers[3][row]):
                scrollmax = len(self._layers[3][row]) - COLS
                if t > self._scrolltimer:
                    self._scrollpos[row] += 1
                    if self._scrollpos[row] > scrollmax + SCROLL_PAUSE:
                        self._scrollpos[row] = -SCROLL_PAUSE
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
            self._lcd_putchars(chars, row, 0)
        if t > self._scrolltimer:
            self._scrolltimer += SCROLL_TIME

    def menu_choose(self, opts, row=ROWS-1, align='right', i=0, wrap=True,
                    timeout=MENU_TIME, func=lambda i: None):
        """Basic LCD menu presenting a list of options
        
        Args:
          opts: list of items to display as the choices
          row: the row on which to show the choices
          align: place text against 'left' or 'right' edge of LCD
          i: index of the choice to display first
          wrap: cyclic vs. bounded option selection
          timeout: seconds to wait, if 0 wait forever
          func: function to call on choice inc/dec

        Returns: (index, item) tuple for the chosen option,
          or (-1, '') if canceled or timed out
        """
        i = i % len(opts)
        while True:
            if align == 'left':
                self.lcd_write(str(opts[i]).ljust(COLS), row)
            else:
                self.lcd_write(str(opts[i]).rjust(COLS), row)
            match self.get_action(timeout=timeout):
                case 'inc' if wrap:
                    i = (i + 1) % len(opts)
                    func(i)
                case 'dec' if wrap:
                    i = (i - 1) % len(opts)
                    func(i)
                case 'inc':
                    i = min(i + 1, len(opts) - 1)
                    func(i)
                case 'dec':
                    i = max(i - 1, 0)
                    func(i)
                case 'do':
                    self.lcd_write(" " * COLS, row)
                    return i, opts[i]
                case 'back':
                    self.lcd_write(" " * COLS, row)
                    return -1, ''
                case action:
                    self.lcd_write(" " * COLS, row)
                    return -1, action

    def menu_confirm(self, text='', row=ROWS-1, timeout=MENU_TIME):
        """Offers a yes/no choice

        Args:
          text: string to write
          row: the row to display the choice
          timeout: seconds to wait, if 0 wait forever

        Returns: True if check is selected, else False
        """
        self.lcd_write((text + " ").ljust(COLS), row)
        c = 1
        while True:
            self.lcd_write([self.XMARK, self.CHECK][c], row, COLS - 1)
            match self.get_action(timeout=timeout):
                case 'inc' | 'dec':
                    c ^= 1
                case 'do' if c:
                    self.lcd_write(" "  * COLS, row)
                    return True
                case _:
                    self.lcd_write(" "  * COLS, row)
                    return False

    def menu_entertext(self, text=' ', row=ROWS-1, i=-1,
                   timeout=0, charset=""):
        """Text entry interface

        Allows a user to enter text character-by-character. User can toggle
        between cursor modes - blinking square changes the cursor position,
        underline changes the current character.

        Args:
          text: the initial text to be edited
          row: the row in which to show the input
          i: initial cursor position, from end if negative
          timeout: seconds to wait, if 0 wait forever
          charset: the set of allowed characters

        Returns: the edited string
        """
        if charset == "":
            charset = self.FNGLYPHS
        i %= len(text)
        text = list(text.ljust(COLS))
        c = charset.find(text[i])
        mode = 'blink'
        self._lcd_setcursormode(mode)
        while True:
            if mode == 'blink':
                w = text[max(0, i + 1 - COLS):max(COLS, i + 1)]
                self.lcd_write(w, row)
            else:
                self.lcd_write(charset[c], row, min(i, COLS - 1))
            self._lcd_setcursorpos(row, min(i, COLS - 1))
            match self.get_action(timeout=timeout), mode:
                case 'inc', 'blink':
                    i = min(i + 1, len(text)) 
                    if i == len(text):
                        text.append(' ')
                    c = charset.find(text[i])
                case 'dec' , 'blink':
                    i = max(i - 1, 0)
                    c = charset.find(text[i])
                case 'inc', 'line':
                    c = (c + 1) % len(charset)
                    text[i] = charset[c]
                case 'dec', 'line':
                    c = (c - 1) % len(charset)
                    text[i] = charset[c]
                case 'do', _:
                    mode = 'blink' if mode == 'line' else 'line'
                    self._lcd_setcursormode(mode)
                case _:
                    self._lcd_setcursormode('hide')
                    text = ''.join(text).strip()
                    for glyph, char in self.GLYPH2CHAR:
                        text = text.replace(glyph, char)
                    return text

    def menu_choosefile(self, topdir, startfile='', ext=None,
                        row=ROWS - 2, timeout=0):
        """Browse and select a file on the system

        Args:
          topdir: Path of the highest-level directory the user may see
          startfile: Path of the file to show as the initial choice
          ext: the file extensions to show, if None shows all files
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever

        Returns: Path of the chosen file or empty string if canceled
        """
        curdir = topdir if startfile == '' else (
                startfile.parent if startfile.parent > topdir else topdir)
        while True:
            self.lcd_write(f"{curdir.relative_to(topdir.parent)}/:".ljust(COLS), row)
            files = sorted([p for p in curdir.glob('*')
                            if p.is_dir() or p.suffix in ext or ext == None])
            names = [f"{self.FOLDER}{p.name}/"
                     if p.is_dir() else p.name for p in files]
            if curdir != topdir:
                files.append(curdir.parent)
                names.append("../")
            i = files.index(startfile) if startfile in files else 0
            i = self.menu_choose(names, row + 1, i=i, timeout=timeout)[0]
            if i == -1:
                self.lcd_write(" "  * COLS, row)
                return ""
            file = files[i]
            if file.is_dir():
                startfile = curdir
                curdir = file
            else:
                self.lcd_write(" "  * COLS, row)
                return file

    def menu_lcdsettings(self, row=ROWS - 2, timeout=MENU_TIME):
        """Menu for setting backlight and contrast levels
        
        Shows adjustable sliders for contrast and backlight.
        Values are saved to the config file when the user exits.

        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever
        """
        d = 10
        slider = [chr(255) * int(i * COLS / 100) for i in range(0, 101, d)]
        while True:
            self.lcd_write("Contrast".ljust(COLS), row)
            ival = int(self.contrast.level / d)
            if self.menu_choose(slider, row + 1, align='left', i=ival, wrap=False, timeout=timeout,
                    func=lambda i: setattr(self.contrast, 'level', i * d)
                    )[0] == -1:
                break
            self.lcd_write("Brightness".ljust(COLS), row)
            ival = int(self.backlight.level / d)
            if self.menu_choose(slider, row + 1, align='left', i=ival, wrap=False, timeout=timeout,
                    func=lambda i: setattr(self.backlight, 'level', i * d)
                    )[0] == -1:
                break
        self.lcd_write(" "  * COLS, row)
        if squishbox_cfgpath != None:
            squishbox_cfg.setdefault('globals', {}).update(
                CONTRAST=self.contrast.level,
                BACKLIGHT=self.backlight.level,
            )
            squishbox_cfgpath.write_text(yaml.safe_dump(squishbox_cfg))
            

    @property
    def wifienabled(self):
        return self._wifienabled

    @wifienabled.setter
    def wifienabled(self, enable):
        if enable:
            self.shell_cmd("sudo nmcli radio wifi on")
        else:
            self.shell_cmd("sudo nmcli radio wifi off")
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == 'enabled'

    def menu_wifisettings(self, row=ROWS - 2, timeout=0):
        """Wifi settings menu
        
        A series of menus that provides a unified interface for
        adjusting wifi settings. Can be used to turn
        wifi on/off, scan for networks, connect/disconnect, and
        enter passwords. Uses NetworkManager's 'nmcli' command
        to control system-wide network settings.

        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever
        """
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == 'enabled'
        nw = self.shell_cmd("nmcli -g IN-USE,SSID dev wifi").splitlines()
        while True:
            if ip := self.shell_cmd("hostname -I").strip():
                self.lcd_write(f"Connected as {ip}".ljust(COLS), row, align='right')
            else:
                self.lcd_write("Not connected".ljust(COLS), row)
            if self.wifienabled:
                ssid = [x[0].replace('*', self.CHECK) + x[2:] for x in nw if x[2:]]
                opts = ssid + ["Scan", "Disable WiFi"]
                i = max(''.join(s[0] for s in ssid).find(self.CHECK), 0)
                match self.menu_choose(opts, row + 1, i=i, timeout=timeout)[1]:
                    case '':
                        self.lcd_write(" " * COLS, row)
                        return
                    case "Scan":
                        self.lcd_write("scanning ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        nw = self.shell_cmd("sudo nmcli -g IN-USE,SSID dev wifi").splitlines()
                        self.progresswheel_stop()
                    case "Disable WiFi":
                        self.wifienabled = False
                        self.lcd_write(" " * COLS, row)
                        return
                    case ssid if ssid[0] == self.CHECK:
                        self.lcd_write(ssid[1:COLS + 1].ljust(COLS), row)
                        self.lcd_write("disconnecting ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        self.shell_cmd(f"sudo nmcli con down {ssid[1:]}")
                        self.progresswheel_stop()
                    case ssid:
                        self.lcd_write(ssid[1:COLS + 1].ljust(COLS), row)
                        self.lcd_write("connecting ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        try:
                            self.shell_cmd(f"sudo nmcli con up {ssid[1:]}")
                        except subprocess.CalledProcessError:
                            self.progresswheel_stop()
                            self.lcd_write("Password:".ljust(COLS), row)
                            psk = self.menu_entertext(row=row + 1, charset=self.GLYPHS)
                            if not self.menu_confirm(psk, row + 1):
                                continue
                            self.lcd_write(ssid[1:COLS + 1].ljust(COLS), row)
                            self.lcd_write("connecting ".rjust(COLS), row + 1)
                            self.progresswheel_start()
                            try:
                                cmd = ["sudo", "nmcli", "dev", "wifi", "connect"]
                                self.shell_cmd([*cmd, ssid[1:], 'password', psk], shell=False)
                            except subprocess.CalledProcessError:
                                self.progresswheel_stop()
                                self.lcd_write("connection fail".rjust(COLS), row + 1)
                                self.get_action(timeout=MENU_TIME)
                            else:
                                self.progresswheel_stop()
                        else:
                            self.progresswheel_stop()
            else:
                if self.menu_choose(["Enable WiFi"], row + 1, timeout=timeout)[0] == 0:
                    self.wifienabled = True
                else:
                    self.lcd_write(" " * COLS, row)
                    return

    def menu_exit(self, row=ROWS - 2, timeout=MENU_TIME):
        """Options to reboot, shutdown, or exit the current script
        
        Returns: "shell" if that option is chosen, otherwise None
        """
        self.lcd_write("Exit options:".ljust(COLS), row)
        match self.menu_choose(["Shutdown", "Reboot", "Shell"],
                               row + 1, timeout=timeout)[1]:
            case "Shutdown":
                self.lcd_write("Shutting down..".ljust(COLS), row)
                self.lcd_write("Wait 15s, unplug".rjust(COLS), row + 1)
                self.shell_cmd("sudo poweroff")
                sys.exit()
            case "Reboot":
                self.lcd_write("Rebooting".ljust(COLS), row)
                self.lcd_write("please wait..".rjust(COLS), row + 1)
                self.shell_cmd("sudo reboot")
                sys.exit()
            case "Shell":
                return "shell"

    def menu_systemsettings(self, row=ROWS - 2, timeout=MENU_TIME):
        """A unified system settings menu
        
        Returns: "shell" if that option is chosen, otherwise None
        """
        self.lcd_write("System Menu".ljust(COLS), row)
        match self.menu_choose(["LCD Settings",
                                "WiFi Settings",
                                "Exit"
                               ], row + 1, timeout)[1]:
            case "LCD Settings":
                self.menu_lcdsettings(row)
            case "WiFi Settings":
                self.menu_wifisettings(row)
            case "Exit":
                if self.menu_exit(row) == "shell":
                    return "shell"

    def progresswheel_start(self):
        """Shows an animation while another process runs
        
        Displays a spinning character in the lower right corner of the
        LCD that runs in a thread after this function returns, to give
        the user some feedback while a long-running process completes.
        """
        self._spinning = True
        self._spin = Thread(target=self._progresswheel_spin)
        self._spin.start()
    
    def progresswheel_stop(self):
        """Removes the spinning character"""
        self._spinning = False
        self._spin.join()

    def display_error(self, err, msg="", tb=None, row=ROWS - 1):
        """Displays Exception text on the LCD
        
        Reformats the text of an Exception so it can be displayed on one
        line and scrolls it across the bottom row of the LCD, and also prints
        information to stdout for debugging.

        Args:
          err: the Exception
          msg: an optional error message
        """
        if type(err) == KeyboardInterrupt:
            sys.exit()
        # remove newlines + carets and compress spaces
        err_oneline = f"{msg}: " if msg else ""        
        err_oneline += f"{type(err).__name__}: "
        err_oneline += re.sub(' {2,}', ' ', re.sub('\n|\^', ' ', str(err)))
        for glyph, char in self.GLYPH2CHAR:
            err_oneline.replace(char, glyph)
        self.lcd_write(err_oneline, row)
        if msg:
            print(msg)
        if tb:
            traceback.print_exception(type(err), err, tb)
        else:
            print(err)
        self.get_action()
        self.lcd_write(" " * COLS, row)

    def action_inc(self):
        """Bind target - increment a value/choice
        """
        self._actions.append('inc')

    def action_dec(self):
        """Bind target - decrement a value/choice
        """
        self._actions.append('dec')

    def action_do(self):
        """Bind target - open/choose/enter/confirm things
        """
        self._actions.append('do')

    def action_back(self):
        """Bind target - cancel/escape/go back
        """
        self._actions.append('back')
    
    def add_action(self, name):
        """Add an action to the stack"""
        self._actions.append(name)

    def clear_actions(self):
        """Clear all actions from the stack
        """
        self._actions = []
        
    def get_action(self, idle=POLL_TIME, timeout=0):
        """Block and update the display until an action occurs
        
        Args:
          idle: delay between polling controls so other threads can work
          timeout: return after this many seconds. If 0 wait forever
        Returns: The action name, or None if timed out
        """
        t0 = time.time()
        self._scrolltimer = t0
        self._buffered = True
        while not self._actions:
            self.update_lcd()
            time.sleep(idle)
            if timeout and time.time() - t0 > timeout:
                self._buffered = False
                return None
        self._buffered = False
        return self._actions.pop(0)

    def draw_glyph(self, loc, text):
        """Instate a custom LCD glyph from ascii art
        
        Args:
          loc: the memory location for the glyph (0-7)
          text: a string representing the 40 pixels of the glyph
            (8 rows times 5 columns) with hash marks (#) and dots (.)
            Spaces and newlines are ignored, so this can be a
            multiline string
            
        Returns:
          a character that can be used to write the glyph on the LCD
        """
        bits = text.replace(' ', '').replace('\n', '').replace('.', '0').replace('#', '1')
        glyphbytes = [int(bits[i:i + 5], 2) for i in range(0, 40, 5)]
        self._lcd_send(0x40 | loc << 3)
        for b in glyphbytes:
            self._lcd_send(b, gpiod.line.Value.ACTIVE)
        return chr(loc)

    def define_custom_glyphs(self):
        """Re-initialize standard SquishBox custom glyphs
        """
        self.BACKSLASH = self.draw_glyph(0, """.....
                                               #....
                                               .#...
                                               ..#..
                                               ...#.
                                               ....#
                                               .....
                                               .....""")

        self.TILDE = self.draw_glyph(1, """.....
                                           .....
                                           .....
                                           .##.#
                                           #..#.
                                           .....
                                           .....
                                           .....""")

        self.CHECK = self.draw_glyph(2, """.....
                                           ....#
                                           ...##
                                           #.##.
                                           ###..
                                           .#...
                                           .....
                                           .....""")

        self.XMARK = self.draw_glyph(3, """.....
                                           ##.##
                                           .###.
                                           ..#..
                                           .###.
                                           ##.##
                                           .....
                                           .....""")

        self.FOLDER = self.draw_glyph(4, """.....
                                            .....
                                            ##...
                                            #.###
                                            #...#
                                            #...#
                                            #####
                                            .....""")

        self.WIFION = self.draw_glyph(5, """.###.
                                            #...#
                                            ..#..
                                            .#.#.
                                            .....
                                            ..#..
                                            .....
                                            .....""")

        self.WIFIOFF = self.draw_glyph(6, """.#.#.
                                             ..#..
                                             .#.#.
                                             .....
                                             ..#..
                                             .....
                                             ..#..
                                             .....""")

        self.NOTEICON = self.draw_glyph(7, """..#..
                                              ..##.
                                              ..#.#
                                              ..#.#
                                              ..#..
                                              ###..
                                              ###..
                                              .....""")

        printable = """abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./!@#$%^&*|?,;:'"`+=<>()[]{}"""
        self.GLYPHS = printable + self.BACKSLASH + self.TILDE + ' '
        self.FNGLYPHS = printable[:67] + self.BACKSLASH + ' ' # allowable filename characters
        self.GLYPH2CHAR = ((self.BACKSLASH, '\\'), (self.TILDE, '~'))

    @staticmethod
    def shell_cmd(cmd, shell=True, **kwargs):
        """Executes a shell command and returns the output
        
        Uses subprocess.run to execute a shell command and returns the output
        as ascii with trailing newlines removed. Blocks until shell command
        has returned.
        
        Args:
          cmd: text of the command line to execute
          kwargs: additional keyword arguments passed to subprocess.run

        Returns: the stripped ascii STDOUT of the command
        """
        return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, shell=shell,
                              encoding='ascii', **kwargs).stdout.rstrip('\n')

    def _progresswheel_spin(self):
        c = self._layers[4][ROWS - 1][COLS - 1]
        i = 0
        while self._spinning:
            s = (self.BACKSLASH + '|/-')[i]
            self._lcd_putchars(s, ROWS - 1, COLS - 1)
            time.sleep(FRAME_TIME)
            i = (i + 1) % 4
        self._lcd_putchars(c, ROWS - 1, COLS - 1)

    def _lcd_putchars(self, chars, row, col):
        lastcol = -2
        for c in chars:
            if c and self._layers[4][row][col] != c:
                if lastcol != col - 1:
                    self._lcd_setcursorpos(row, col)
                self._lcd_send(ord(c), gpiod.line.Value.ACTIVE)
                self._layers[4][row][col] = c
                lastcol = col
            col += 1

    def _lcd_setcursorpos(self, row, col):
        if row < ROWS and col < COLS:
            offset = (0x00, 0x40, COLS, 0x40 + COLS)
            self._lcd_send(0x80 | offset[row] + col)

    def _lcd_setcursormode(self, mode):
        if mode == 'hide':
            #self._lcd_send(0x0c | 0x00)
            self._lcd_send(0x0c)
        elif mode == 'blink':
            self._lcd_send(0x0d)
        elif mode == 'line':    
            self._lcd_send(0x0e)

    def _lcd_send(self, val, reg=gpiod.line.Value.INACTIVE):
        if LCD_RS == 0:
            return
        self._lines.set_value(LCD_RS, reg)
        self._lines.set_value(LCD_EN, gpiod.line.Value.INACTIVE)
        for nib in (val >> 4, val):
            line_vals = {}
            for i in range(4):
                if nib >> i & 1:
                    line_vals[LCD_DATA[i]] = gpiod.line.Value.ACTIVE
                else:
                    line_vals[LCD_DATA[i]] = gpiod.line.Value.INACTIVE
            self._lines.set_values(line_vals)
            self._lines.set_value(LCD_EN, gpiod.line.Value.ACTIVE)
            time.sleep(EXEC_TIME)
            self._lines.set_value(LCD_EN, gpiod.line.Value.INACTIVE)


# set appropriate Umask for web file manager
os.umask(0o002) # default file mode -rw-rw-r-- dir mode drwxrwxr-x

# search for config file
squishbox_cfg = {}
for d in (Path('.'),
          Path('./config'),
          Path.home() / '.config'):
    squishbox_cfgpath = d / 'squishboxconf.yaml'
    if squishbox_cfgpath.exists():
        squishbox_cfg = yaml.safe_load(squishbox_cfgpath.read_text())
        break

# apply config file settings
if 'globals' in squishbox_cfg:
    for var, val in squishbox_cfg['globals'].items():
        globals()[var] = val

squishbox_hardware = SquishBox()
def get_hardware():
    return squishbox_hardware

if __name__ == "__main__":
    """Display the SquishBox shell"""
    from importlib import import_module
    
    if SCRIPTS_DIR not in sys.path:
        sys.path.append(SCRIPTS_DIR)
    scripts = []
    for p in Path(SCRIPTS_DIR).iterdir():
        if p.suffix == '.py' and p.name != 'squishbox.py':
            scripts.append(p)

    sb = get_hardware()

    sb.knob1.bind('left', sb.action_dec)
    sb.knob1.bind('right', sb.action_inc)
    sb.button1.bind('tap', sb.action_do)
    sb.button1.bind('hold', sb.action_back)

    while True:
        sb.lcd_clear()
        sb.lcd_write(f"SquishBox {__version__}", row=0)
        match sb.menu_choose([*scripts,
                              "LCD Settings",
                              "WiFi Settings",
                              "Exit"
                             ], row=ROWS - 1, timeout=0)[1]:
            case "LCD Settings":
                sb.menu_lcdsettings()
            case "WiFi Settings":
                sb.menu_wifisettings()
            case "Exit" | "":
                if sb.menu_exit() == "shell":
                    break
            case script:
                sb.lcd_write(str(script).ljust(COLS), row=ROWS - 2)
                sb.lcd_write("starting ".rjust(COLS), row=ROWS - 1)
                
                import_module(script.stem)
                del sys.modules[script.stem]

