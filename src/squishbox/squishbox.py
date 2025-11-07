import re
import subprocess
import sys
from threading import Thread
import time
import traceback

from . import hardware
from .config import CONFIG, save_state
from .midi import midi_connect, midi_ports

ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]
MENU_TIME = CONFIG["menu_timeout"]


class SquishBox:
    """Object interface to the SquishBox UI"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            obj = super(SquishBox, cls).__new__(cls)
            """Initializes LCD, encoder, and related GPIO"""
            obj._actions = []
            # set up LCD
            obj.lcd = hardware.LCD_HD44780(
                CONFIG["lcd_regsel"],
                CONFIG["lcd_enable"],
                CONFIG["lcd_data"]
            )
            obj.backlight = hardware.PWMOutput(
                CONFIG["lcd_backlight"], level=CONFIG["backlight_level"]
            )
            obj.contrast = hardware.PWMOutput(
                CONFIG["lcd_contrast"], level=CONFIG["contrast_level"]
            )
            # add encoder/pushbutton controls
            obj.knob1 = hardware.Encoder(
                CONFIG["rotary_left"],
                CONFIG["rotary_right"]
            )
            obj.button1 = hardware.Button(
                CONFIG["rotary_button"]
            )
            obj._wifienabled = obj.shell_cmd("nmcli radio wifi") == "enabled"
            sys.excepthook = lambda _, e, tb: obj.display_error(e, tb=tb)
            cls._instance = obj
        return cls._instance

    def menu_choose(self, opts, row=ROWS-1, align="right", i=0, wrap=True,
                    timeout=MENU_TIME, func=lambda i: None):
        """Basic LCD menu presenting a list of options
        
        Args:
          opts: list of items to display as the choices
          row: the row on which to show the choices
          align: place text against "left" or "right" edge of LCD
          i: index of the choice to display first
          wrap: cyclic vs. bounded option selection
          timeout: seconds to wait, if 0 wait forever
          func: function to call on choice inc/dec

        Returns: (index, item) tuple for the chosen option,
          or (-1, "") if canceled or timed out
        """
        i = i % len(opts)
        while True:
            if align == "left":
                self.lcd.write(str(opts[i]).ljust(COLS), row)
            else:
                self.lcd.write(str(opts[i]).rjust(COLS), row)
            match self.get_action(timeout=timeout):
                case "inc" if wrap:
                    i = (i + 1) % len(opts)
                    func(i)
                case "dec" if wrap:
                    i = (i - 1) % len(opts)
                    func(i)
                case "inc":
                    i = min(i + 1, len(opts) - 1)
                    func(i)
                case "dec":
                    i = max(i - 1, 0)
                    func(i)
                case "do":
                    self.lcd.write(" " * COLS, row)
                    return i, opts[i]
                case "back":
                    self.lcd.write(" " * COLS, row)
                    return -1, ""
                case action:
                    self.lcd.write(" " * COLS, row)
                    return -1, action

    def menu_confirm(self, text="", row=ROWS-1, timeout=MENU_TIME):
        """Offers a yes/no choice

        Args:
          text: string to write
          row: the row to display the choice
          timeout: seconds to wait, if 0 wait forever

        Returns: True if check is selected, else False
        """
        self.lcd.write((text + " ").ljust(COLS), row)
        c = 1
        while True:
            if c:
                self.lcd.write(self.lcd.glyphs["check"], row, COLS - 1)
            else:
                self.lcd.write(self.lcd.glyphs["cross"], row, COLS - 1)
            match self.get_action(timeout=timeout):
                case "inc" | "dec":
                    c ^= 1
                case "do" if c:
                    self.lcd.write(" "  * COLS, row)
                    return True
                case _:
                    self.lcd.write(" "  * COLS, row)
                    return False

    def menu_entertext(self, text=" ", row=ROWS-1, i=-1,
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
            charset = self.lcd.FCHARS
        i %= len(text)
        text = list(text.ljust(COLS))
        c = charset.find(text[i])
        mode = "blink"
        self.lcd.setcursormode(mode)
        while True:
            if mode == "blink":
                w = text[max(0, i + 1 - COLS):max(COLS, i + 1)]
                self.lcd.write("".join(w), row)
            else:
                self.lcd.write(charset[c], row, min(i, COLS - 1))
            self.lcd.setcursorpos(row, min(i, COLS - 1))
            match self.get_action(timeout=timeout), mode:
                case "inc", "blink":
                    i = min(i + 1, len(text)) 
                    if i == len(text):
                        text.append(" ")
                    c = charset.find(text[i])
                case "dec" , "blink":
                    i = max(i - 1, 0)
                    c = charset.find(text[i])
                case "inc", "line":
                    c = (c + 1) % len(charset)
                    text[i] = charset[c]
                case "dec", "line":
                    c = (c - 1) % len(charset)
                    text[i] = charset[c]
                case "do", _:
                    mode = "blink" if mode == "line" else "line"
                    self.lcd.setcursormode(mode)
                case _:
                    self.lcd.setcursormode("hide")
                    text = "".join(text).strip()
                    for name, char in self.lcd.glyph2char:
                        text.replace(self.lcd.glyphs[name], char) 
                    return text

    def menu_choosefile(self, topdir, startfile="", ext=[],
                        row=ROWS - 2, timeout=0):
        """Browse and select a file on the system

        Args:
          topdir: Path of the highest-level directory the user may see
          startfile: Path of the file to show as the initial choice
          ext: list of file extensions to show, if empty shows all files
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever

        Returns: Path of the chosen file or empty string if canceled
        """
        curdir = topdir if startfile == "" else (
                startfile.parent if startfile.parent > topdir else topdir)
        while True:
            self.lcd.write(
                f"{curdir.relative_to(topdir.parent)}/:".ljust(COLS),
                row
            )
            paths = sorted([p for p in curdir.iterdir()
                            if p.is_dir() or p.suffix in ext or not ext])
            names = [f'{self.lcd.glyphs["folder"]}{p.name}/'
                     if p.is_dir() else p.name for p in paths]
            if curdir != topdir:
                paths.append(curdir.parent)
                names.append("../")
            i = paths.index(startfile) if startfile in paths else 0
            i = self.menu_choose(names, row + 1, i=i, timeout=timeout)[0]
            if i == -1:
                self.lcd.write(" "  * COLS, row)
                return ""
            path = paths[i]
            if path.is_dir():
                startfile = curdir
                curdir = path
            else:
                self.lcd.write(" "  * COLS, row)
                return path

    def menu_lcdsettings(self, row=ROWS - 2, timeout=MENU_TIME):
        """Menu for setting backlight and contrast levels
        
        Shows adjustable sliders for contrast and backlight.
        Values are saved to the config file when the user exits.

        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever
        """
        d = 10
        slider = [self.lcd.glyphs["solid"] * int(i * COLS / 100)
                  for i in range(0, 101, d)]
        while True:
            self.lcd.write("Contrast".ljust(COLS), row)
            ival = int(self.contrast.level / d)
            if self.menu_choose(
                slider, row + 1, align="left",
                i=ival, wrap=False, timeout=timeout,
                func=lambda i: setattr(self.contrast, "level", i * d)
            )[0] == -1:
                break
            self.lcd.write("Brightness".ljust(COLS), row)
            ival = int(self.backlight.level / d)
            if self.menu_choose(
                slider, row + 1, align="left",
                i=ival, wrap=False, timeout=timeout,
                func=lambda i: setattr(self.backlight, "level", i * d)
            )[0] == -1:
                break
        self.lcd.write(" "  * COLS, row)
        CONFIG["contrast_level"] = self.contrast.level
        CONFIG["backlight_level"] = self.backlight.level
        save_state(CONFIG)

    def menu_midisettings(self, row=ROWS - 2, timeout=0):
        """List and connect/disconnect MIDI ports

        Connections are added to the config file and will
        be reconnected automatically
        
         Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever
        """
        inames = list(midi_ports(input=True))
        onames = list(midi_ports(output=True))
        if not (inames and onames):
            self.lcd.write("no MIDI ports".rjust(COLS), row + 1)
            self.get_action(timeout=MENU_TIME)
            self.lcd.write(" " * COLS, row + 1)
            return
        ilast = 0
        olast = 0
        conns = CONFIG.get("midi_connections", [])
        while True:
            self.lcd.write("Source Ports:".ljust(COLS), row)
            ilast, iname = self.menu_choose(
                inames, row + 1, i=ilast, timeout=timeout
            )
            if ilast == -1:
                self.lcd.write(" " * COLS, row)
                if conns:
                    CONFIG["midi_connections"] = sorted(conns)
                else:
                    CONFIG.pop("midi_connections", None)
                save_state(CONFIG)
                return
            while True:
                midi_connect()
                self.lcd.write("Dest. Ports:".ljust(COLS), row)
                olast, oname = self.menu_choose(
                    [f">{p}" if f"{iname}>{p}" in conns else f" {p}"
                     for p in onames],
                    row + 1, i=olast, timeout=timeout
                )
                if olast == -1:
                    break
                conn = f"{iname}>{oname[1:]}"
                if conn in conns:
                    conns.remove(conn)           
                else:
                    conns.append(conn)

    @property
    def wifienabled(self):
        return self._wifienabled

    @wifienabled.setter
    def wifienabled(self, enable):
        if enable:
            self.shell_cmd("sudo nmcli radio wifi on")
        else:
            self.shell_cmd("sudo nmcli radio wifi off")
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == "enabled"

    def menu_wifisettings(self, row=ROWS - 2, timeout=0):
        """Wifi settings menu
        
        Turn wifi on/off, scan for networks, connect/disconnect, and
        enter passwords.

        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever
        """
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == "enabled"
        nw = self.shell_cmd("nmcli -g IN-USE,SSID dev wifi").splitlines()
        while True:
            if ip := self.shell_cmd("hostname -I").strip():
                self.lcd.write(f"Connected as {ip}".ljust(COLS), row, align="right")
            else:
                self.lcd.write("Not connected".ljust(COLS), row)
            if self.wifienabled:
                ssid = [x[0].replace("*", self.lcd.glyphs["check"]) + x[2:]
                        for x in nw if x[2:]]
                opts = ssid + ["Scan", "Disable WiFi"]
                i = max("".join(s[0] for s in ssid).find(self.lcd.glyphs["check"]), 0)
                match self.menu_choose(opts, row + 1, i=i, timeout=timeout)[1]:
                    case "":
                        self.lcd.write(" " * COLS, row)
                        return
                    case "Scan":
                        self.lcd.write("scanning ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        nw = self.shell_cmd("sudo nmcli -g IN-USE,SSID dev wifi").splitlines()
                        self.progresswheel_stop()
                    case "Disable WiFi":
                        self.wifienabled = False
                        self.lcd.write(" " * COLS, row)
                        return
                    case ssid if ssid[0] == self.lcd.glyphs["check"]:
                        self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                        self.lcd.write("disconnecting ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        self.shell_cmd(f"sudo nmcli con down {ssid[1:]}")
                        self.progresswheel_stop()
                    case ssid:
                        self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                        self.lcd.write("connecting ".rjust(COLS), row + 1)
                        self.progresswheel_start()
                        try:
                            self.shell_cmd(f"sudo nmcli con up {ssid[1:]}")
                        except subprocess.CalledProcessError:
                            self.progresswheel_stop()
                            self.lcd.write("Password:".ljust(COLS), row)
                            psk = self.menu_entertext(row=row + 1, charset=self.lcd.CHARS)
                            if not self.menu_confirm(psk, row + 1):
                                continue
                            self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                            self.lcd.write("connecting ".rjust(COLS), row + 1)
                            self.progresswheel_start()
                            try:
                                cmd = ["sudo", "nmcli", "dev", "wifi", "connect"]
                                self.shell_cmd([*cmd, ssid[1:], "password", psk], shell=False)
                            except subprocess.CalledProcessError:
                                self.progresswheel_stop()
                                self.lcd.write("connection fail".rjust(COLS), row + 1)
                                self.get_action(timeout=MENU_TIME)
                            else:
                                self.progresswheel_stop()
                        else:
                            self.progresswheel_stop()
            else:
                if self.menu_choose(["Enable WiFi"], row + 1, timeout=timeout)[0] == 0:
                    self.wifienabled = True
                else:
                    self.lcd.write(" " * COLS, row)
                    return

    def menu_exit(self, row=ROWS - 2, timeout=MENU_TIME):
        """Reboot, shutdown, or exit the current script
        
        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever

        Returns: "shell" if that option is chosen, otherwise None
        """
        self.lcd.write("Exit options:".ljust(COLS), row)
        match self.menu_choose(["Shutdown", "Reboot", "Shell"],
                               row + 1, timeout=timeout)[1]:
            case "Shutdown":
                self.lcd.write("Shutting down..".ljust(COLS), row)
                self.lcd.write("wait 15s, unplug".rjust(COLS), row + 1)
                self.shell_cmd("sudo poweroff")
                sys.exit()
            case "Reboot":
                self.lcd.write("Rebooting".ljust(COLS), row)
                self.lcd.write("please wait..".rjust(COLS), row + 1)
                self.shell_cmd("sudo reboot")
                sys.exit()
            case "Shell":
                return "shell"
        self.lcd.write(" " * COLS, row)

    def menu_systemsettings(self, row=ROWS - 2, timeout=MENU_TIME):
        """A unified system settings menu
        
        Args:
          row: menu uses this row and the one below it
          timeout: seconds to wait, if 0 wait forever

        Returns: "shell" if that option is chosen, otherwise None
        """
        self.lcd.write("System Menu".ljust(COLS), row)
        match self.menu_choose(["LCD Settings..",
                                "MIDI Settings..",
                                "WiFi Settings..",
                                "Exit"
                               ], row + 1, timeout)[1]:
            case "LCD Settings..":
                self.menu_lcdsettings(row)
            case "MIDI Settings..":
                self.menu_midisettings(row)
            case "WiFi Settings..":
                self.menu_wifisettings(row)
            case "Exit":
                if self.menu_exit(row) == "shell":
                    return "shell"
        self.lcd.write(" " * COLS, row)

    def progresswheel_start(self):
        """Shows an animation while another process runs
        
        Displays a spinning character in the lower right corner of the
        LCD that runs in a thread after this function returns, to give
        the user some feedback while a long-running process completes.
        """
        self.lcd._spinning = True
        self._spin = Thread(target=self.lcd._progresswheel_spin)
        self._spin.start()
    
    def progresswheel_stop(self):
        """Removes the spinning character"""
        self.lcd._spinning = False
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
        err_oneline += re.sub(" {2,}", " ", re.sub("\n|\^", " ", str(err)))
        for name, char in self.lcd.glyph2char:
            err_oneline.replace(char, self.lcd.glyphs[name])
        self.lcd.write(err_oneline, row)
        if msg:
            print(msg)
        if tb:
            traceback.print_exception(type(err), err, tb)
        else:
            print(err)
        self.get_action()
        self.lcd.write(" " * COLS, row)

    def action_inc(self):
        """Bind target - increment a value/choice
        """
        self._actions.append("inc")

    def action_dec(self):
        """Bind target - decrement a value/choice
        """
        self._actions.append("dec")

    def action_do(self):
        """Bind target - open/choose/enter/confirm things
        """
        self._actions.append("do")

    def action_back(self):
        """Bind target - cancel/escape/go back
        """
        self._actions.append("back")
    
    def add_action(self, name):
        """Add an action to the stack"""
        self._actions.append(name)

    def clear_actions(self):
        """Clear all actions from the stack
        """
        self._actions = []
        
    def get_action(self, idle=CONFIG["poll_time"], timeout=0):
        """Block and update the display until an action occurs
        
        Args:
          idle: delay between polling controls so other threads can work
          timeout: return after this many seconds. If 0 wait forever
        Returns: The action name, or None if timed out
        """
        t0 = time.time()
        self._scrolltimer = t0
        self.lcd._buffered = True
        while not self._actions:
            self.lcd.update()
            time.sleep(idle)
            if timeout and time.time() - t0 > timeout:
                self._buffered = False
                return None
        self.lcd._buffered = False
        return self._actions.pop(0)

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
                              encoding="ascii", **kwargs).stdout.rstrip("\n")

