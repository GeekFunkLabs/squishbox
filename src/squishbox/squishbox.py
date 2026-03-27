import re
import subprocess
import sys
from threading import Thread
import time
import traceback

from . import hardware
from .config import CONFIG, CONFIG_PATH, save_state
from .midi import midi_connect, midi_ports
from .keys import keys_dispatch, keys_stop

ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]
MENU_TIME = CONFIG["menu_timeout"]


class SquishBox:
    """Singleton interface to SquishBox hardware and UI.

    Provides access to the LCD, controls (buttons/encoders), outputs,
    and a set of menu-driven interaction helpers. All hardware is
    initialized on first instantiation using values from CONFIG.

    This class is a singleton; repeated instantiation returns the same object.
    """
    _instance = None

    def __new__(cls):
        """Create or return the singleton SquishBox instance.

        On first creation:
          - Initializes LCD display
          - Configures input controls and binds events to actions
          - Configures output pins (binary/PWM)
          - Detects WiFi state
          - Installs a global exception hook to display errors on the LCD

        Subsequent calls return the existing instance.
        """
        if cls._instance is None:
            obj = super(SquishBox, cls).__new__(cls)
            obj._actions = []
            # set up LCD
            obj.lcd = hardware.LCD_HD44780(
                CONFIG["lcd_regsel"],
                CONFIG["lcd_enable"],
                CONFIG["lcd_data"]
            )
            # add controls
            obj.controls = {}
            for name, spec in CONFIG["controls"].items():
                if spec["type"] == "button":
                    obj.controls[name] = hardware.Button(
                        spec["pin"],
                        pull_up=spec.get("pull_up", CONFIG["pull_up"])
                    )
                elif spec["type"] == "encoder":
                    obj.controls[name] = hardware.Encoder(
                        spec["pins"][0],
                        spec["pins"][1],
                        pull_up=spec.get("pull_up", CONFIG["pull_up"])
                    )
                else:
                    continue
                for event, action in spec["events"].items():
                    obj.controls[name].bind(
                        event, lambda a=action: obj.add_action(a)
                    )
            # add outputs
            obj.outputs = {}                
            for name, spec in CONFIG["outputs"].items():
                if spec["type"] == "binary":
                    obj.outputs[name] = hardware.Output(
                        spec["pin"],
                        on=spec.get("on", False)
                    )
                elif spec["type"] == "pwm":
                    obj.outputs[name] = hardware.PWMOutput(
                        spec["pin"],
                        freq=spec.get("freq", 2000),
                        level=spec.get("level", 0)
                    )
                else:
                    continue
            obj._wifienabled = obj.shell_cmd("nmcli radio wifi") == "enabled"
            sys.excepthook = lambda _, e, __: obj.display_error(e)
            cls._instance = obj
        return cls._instance

    def menu_choose(self, opts, row=ROWS-1, align="right", i=0, wrap=True,
                    timeout=MENU_TIME, func=None):
        """Display a scrolling selection menu on the LCD.

        The user navigates options via bound input actions ("inc", "dec",
        "select", "back"). The provided callback is invoked whenever the
        selection index changes.

        Args:
            opts (list): Sequence of selectable items (displayed via str()).
            row (int): LCD row to render the menu.
            align (str): "left" or "right" text alignment.
            i (int): Initial index.
            wrap (bool): If True, selection wraps around at ends.
            timeout (float): Seconds to wait for input (0 = wait indefinitely).
            func (callable): Callback invoked as func(index) on selection change.

        Returns:
            (index, item) on selection
            (index, None) if canceled ("back")
            (-1, None) if timed out
            (-1, other) if an unhandled action is received
        """
        i = i % len(opts)
        while True:
            if align == "left":
                self.lcd.write(str(opts[i]).ljust(COLS), row)
            else:
                self.lcd.write(str(opts[i]).rjust(COLS), row)
            if func:
                func(i)
            match self.get_action(timeout=timeout):
                case "inc" if wrap:
                    i = (i + 1) % len(opts)
                case "dec" if wrap:
                    i = (i - 1) % len(opts)
                case "inc":
                    i = min(i + 1, len(opts) - 1)
                case "dec":
                    i = max(i - 1, 0)
                case "select":
                    self.lcd.write(" " * COLS, row)
                    return i, opts[i]
                case "back":
                    self.lcd.write(" " * COLS, row)
                    return i, None
                case other:
                    self.lcd.write(" " * COLS, row)
                    return -1, other

    def menu_confirm(self, text="", row=ROWS-1, timeout=MENU_TIME):
        """Display a yes/no confirmation prompt.

        The user toggles between confirm (check) and cancel (cross)
        using "inc"/"dec", and confirms with "select".

        Args:
            text (str): Prompt text.
            row (int): LCD row to render the prompt.
            timeout (float): Seconds to wait (0 = wait indefinitely).

        Returns:
            True if confirmed
            False if explicitly rejected
            None if canceled ("back") or timed out
            other if an unhandled action is received
        """
        self.lcd.write((text + " ").ljust(COLS), row)
        c = True
        while True:
            self.lcd.write(
                self.lcd["check"] if c else self.lcd["cross"],
                row, COLS - 1
            )
            match self.get_action(timeout=timeout):
                case "inc" | "dec":
                    c = not c
                case "select":
                    self.lcd.write(" "  * COLS, row)
                    return c
                case "back" | None:
                    self.lcd.write(" "  * COLS, row)
                    return None
                case other:
                    self.lcd.write(" "  * COLS, row)
                    return other

    def menu_entertext(self, text="", row=ROWS-1, i=-1,
                   timeout=0, charset=""):
        """Interactive text entry using buttons/encoder or keyboard input.

        Supports two cursor modes:
          - "blink": move cursor position
          - "line": modify character at cursor

        Input sources:
          - Encoder/buttons ("inc", "dec", "select", "back")
          - Key events via keys_dispatch()

        Args:
            text (str): Initial text buffer.
            row (int): LCD row to render input.
            i (int): Initial cursor index (negative values index from end).
            timeout (float): Seconds to wait for input (0 = wait indefinitely).
            charset (str): Allowed characters; defaults to LCD printable set.

        Returns:
            Final edited string on completion. If an unhandled action
            is received, passes it back to the caller for handling.
        """
        if charset == "":
            charset = self.lcd.printable()
        i = i % len(text) if text else 0
        text = list(text.ljust(COLS))
        mode = "blink"
        self.lcd.setcursormode(mode)
        keys_dispatch(self.add_action)
        while True:
            w = text[max(0, i + 1 - COLS):max(COLS, i + 1)]
            self.lcd.write("".join(w), row)
            self.lcd.setcursorpos(row, min(i, COLS - 1))
            match self.get_action(timeout=timeout):
                case "inc" if mode == "line":
                    c = charset.find(text[i])
                    text[i] = charset[(c + 1) % len(charset)]
                case "dec" if mode == "line":
                    c = charset.find(text[i])
                    text[i] = charset[(c - 1) % len(charset)]
                case "inc" | ("key", "right"):
                    i += 1
                    if i == len(text):
                        text.append(" ")
                case "dec" | ("key", "left"):
                    i = max(i - 1, 0)
                case ("key", "erase"):
                    if i > 0:
                        text[i - 1:] = text[i:]
                        i -= 1
                case "select" | ("key", "insert"):
                    mode = "blink" if mode == "line" else "line"
                    self.lcd.setcursormode(mode)
                case "back" | ("key", "done"):
                    self.lcd.setcursormode("hide")
                    text = "".join(text)
                    for name, char in self.lcd.glyph2char:
                        text.replace(self.lcd[name], char) 
                    keys_stop()
                    return text
                case ("key", k):
                    if mode == "line":
                        text.insert(i, k)
                    else:
                        text[i] = k
                    i += 1
                    if i == len(text):
                        text.append(" ")
                case other:
                    self.lcd.setcursormode("hide")
                    keys_stop()
                    return other

    def menu_choosefile(self, topdir, start=None, ext=[],
                        row=ROWS - 2, timeout=0):
        """Browse directories and select a file.

        Displays a simple two-line file browser. Directories are shown
        with a trailing '/', and navigation includes a parent ("../")
        entry where applicable.

        Args:
            topdir (Path): Root directory (user cannot navigate above this).
            start (Path): Optional starting file or directory (relative to topdir).
            ext (list): List of allowed file extensions (empty = show all).
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).

        Returns:
            Path: selected file, or last directory if canceled
        """
        curdir = topdir
        if start:
            start = topdir / start
            if start.is_dir():
                curdir = max(start, topdir)
            else:
                curdir = max(start.parent, topdir)
        while True:
            self.lcd.write(
                f"{curdir.relative_to(topdir.parent)}/:".ljust(COLS),
                row
            )
            paths = sorted([p for p in curdir.iterdir()
                            if p.is_dir() or p.suffix in ext or not ext])
            names = [f'{p.name}/'
                     if p.is_dir() else p.name for p in paths]
            if curdir != topdir:
                paths.append(curdir.parent)
                names.append("../")
            i = paths.index(start) if start in paths else 0
            start = None
            i, res = self.menu_choose(names, row + 1, i=i, timeout=timeout)
            if res == None:
                return curdir
            if paths[i].is_dir():
                startfile = curdir
                curdir = paths[i]
            else:
                return paths[i]

    @property
    def contrast_level(self):
        """Current LCD contrast level (0–100).

        Returns default value if no contrast output is configured.
        """
        if "contrast" in self.outputs:
            return self.outputs["contrast"].level
        else:
            return 100

    @contrast_level.setter
    def contrast_level(self, level):
        if "contrast" in self.outputs:
            self.outputs["contrast"].level = level

    @property
    def backlight_level(self):
        """Current LCD backlight brightness (0–100).

        Falls back to CONFIG default if no backlight output is configured.
        """
        if "backlight" in self.outputs:
            return self.outputs["backlight"].level
        else:
            return CONFIG["backlight_level"]

    @backlight_level.setter
    def backlight_level(self, level):
        if "backlight" in self.outputs:
            self.outputs["backlight"].level = level

    def menu_lcdsettings(self, row=ROWS - 2, timeout=MENU_TIME):
        """Adjust LCD contrast and backlight using slider UI.

        Presents two sequential sliders. Changes are applied live and
        written back to the config file on exit.

        Args:
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).
        """
        d = 100 / COLS
        slider = [self.lcd["solid"] * i for i in range(COLS + 1)]
        while True:
            self.lcd.write("Contrast".ljust(COLS), row)
            ival = round(self.contrast_level / d)
            i, res = self.menu_choose(
                slider, row + 1, align="left",
                i=ival, wrap=False, timeout=timeout,
                func=lambda i: setattr(self, "contrast_level", i * d)
            )
            if res == None:
                break
            self.lcd.write("Brightness".ljust(COLS), row)
            ival = round(self.backlight_level / d)
            i, res = self.menu_choose(
                slider, row + 1, align="left",
                i=ival, wrap=False, timeout=timeout,
                func=lambda i: setattr(self, "backlight_level", i * d)
            )
            if res == None:
                break
        self.lcd.write(" "  * COLS, row)
        CONFIG["outputs"]["contrast"]["level"] = self.contrast_level
        CONFIG["outputs"]["backlight"]["level"] = self.backlight_level
        save_state(CONFIG_PATH, CONFIG)

    def menu_midisettings(self, row=ROWS - 2, timeout=0):
        """Manage MIDI input/output connections.

        Lists available MIDI ports and allows toggling connections.
        Active connections are persisted to the config file and
        restored automatically on startup.

        Args:
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).
        """
        srcnames = list(midi_ports(input=True))
        destnames = list(midi_ports(output=True))
        if not (srcnames and destnames):
            self.lcd.write("no MIDI ports".rjust(COLS), row + 1)
            self.get_action(timeout=MENU_TIME)
            self.lcd.write(" " * COLS, row + 1)
            return
        last_src = 0
        last_dest = 0
        conns = CONFIG.get("midi_connections", [])
        while True:
            self.lcd.write("Source Ports:".ljust(COLS), row)
            last_src, src = self.menu_choose(
                srcnames + ["any"], row + 1, i=last_src, timeout=timeout
            )
            if src == None:
                self.lcd.write(" " * COLS, row)
                if conns:
                    CONFIG["midi_connections"] = sorted(conns)
                else:
                    CONFIG.pop("midi_connections", None)
                save_state(CONFIG_PATH, CONFIG)
                break
            while True:
                midi_connect()
                self.lcd.write("Dest. Ports:".ljust(COLS), row)
                last_dest, dest = self.menu_choose(
                    [f">{p}" if f"{src}>{p}" in conns else f" {p}"
                     for p in destnames + ["any"]],
                    row + 1, i=last_dest, timeout=timeout
                )
                if dest == None:
                    break
                conn = f"{src}>{dest[1:]}"
                if conn in conns:
                    conns.remove(conn)
                else:
                    conns.append(conn)
            if CONFIG.get("midi_connections") == []:
                del CONFIG["midi_connections"]

    @property
    def wifienabled(self):
        """Get/set WiFi radio state"""
        return self._wifienabled

    @wifienabled.setter
    def wifienabled(self, enable):
        if enable:
            self.shell_cmd("sudo nmcli radio wifi on")
        else:
            self.shell_cmd("sudo nmcli radio wifi off")
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == "enabled"

    def menu_wifisettings(self, row=ROWS - 2, timeout=0):
        """Manage WiFi connectivity using nmcli.

        Features:
          - Enable/disable WiFi radio
          - Scan for networks
          - Connect/disconnect from access points
          - Prompt for passwords when required

        Displays connection status and IP address when available.

        Args:
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).
        """
        self._wifienabled = self.shell_cmd("nmcli radio wifi") == "enabled"
        aps = self.shell_cmd("nmcli -g IN-USE,SSID dev wifi").splitlines()
        while True:
            if ip := self.shell_cmd("hostname -I").strip():
                self.lcd.write(f"Connected as {ip}".ljust(COLS), row, align="right")
            else:
                self.lcd.write("Not connected".ljust(COLS), row)
            if self.wifienabled:
                ssid = [x[0].replace("*", self.lcd["check"]) + x[2:]
                        for x in aps if x[2:]]
                match self.menu_choose(
                    ssid + ["Scan", "Disable WiFi"],
                    row + 1, timeout=timeout,
                    i=max("".join(s[0] for s in ssid).find(self.lcd["check"]), 0)
                )[1]:
                    case None:
                        self.lcd.write(" " * COLS, row)
                        break
                    case "Scan":
                        with self.lcd.activity("scanning ".rjust(COLS)):
                            aps = self.shell_cmd(
                                "sudo nmcli -g IN-USE,SSID dev wifi"
                            ).splitlines()
                    case "Disable WiFi":
                        self.wifienabled = False
                        self.lcd.write(" " * COLS, row)
                        break
                    case ssid if ssid[0] == self.lcd["check"]:
                        self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                        with self.lcd.activity("disconnecting ".rjust(COLS)):
                            self.shell_cmd(f"sudo nmcli con down {ssid[1:]}")
                    case ssid:
                        self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                        self.lcd.write("connecting ".rjust(COLS), row + 1)
                        try:
                            with self.lcd.activity("connecting ".rjust(COLS)):
                                self.shell_cmd(f"sudo nmcli con up {ssid[1:]}")
                        except subprocess.CalledProcessError:
                            self.lcd.write("Password:".ljust(COLS), row)
                            psk = self.menu_entertext(row=row + 1).strip()
                            if not self.menu_confirm(psk, row + 1):
                                continue
                            self.lcd.write(ssid[1:COLS + 1].ljust(COLS), row)
                            try:
                                with self.lcd.activity("connecting ".rjust(COLS)):
                                    self.shell_cmd(
                                        "sudo nmcli dev wifi connect".split() +
                                        [ssid[1:], "password", psk],
                                        shell=False
                                    )
                            except subprocess.CalledProcessError:
                                self.lcd.write("connection fail".rjust(COLS), row + 1)
                                self.get_action(timeout=MENU_TIME)
            else:
                res = self.menu_choose(["Enable WiFi"], row + 1, timeout=timeout)
                if res[1] != None:
                    self.wifienabled = True
                else:
                    self.lcd.write(" " * COLS, row)
                    break

    def menu_exit(self, row=ROWS - 2, timeout=MENU_TIME):
        """System exit menu.

        Allows the user to:
          - Shutdown the system
          - Reboot
          - Exit to shell

        Args:
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).

        Returns:
            "shell" if shell option is selected
            None otherwise (system may exit before returning)
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
        """Top-level system settings menu.

        Provides access to LCD, MIDI, WiFi, and exit options.

        Args:
            row (int): Starting LCD row (uses two rows).
            timeout (float): Seconds to wait (0 = wait indefinitely).

        Returns:
            str | None: "shell" if user selects exit-to-shell, otherwise None
        """
        self.lcd.write("System Menu".ljust(COLS), row)
        match self.menu_choose([
            "LCD Settings..",
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

    def display_error(self, err, msg="", row=ROWS - 2):
        """Display an exception on the LCD and print traceback.

        Formats the exception into a single-line message for the LCD,
        with file/line context shown on the second row. Full traceback
        is printed to stdout for debugging.

        KeyboardInterrupt exits immediately.

        Args:
            err (Exception): Exception instance
            msg (str): Optional prefix message
            row (int): Starting LCD row (uses two rows)
        """
        if isinstance(err, KeyboardInterrupt):
            sys.exit()

        tb = traceback.extract_tb(err.__traceback__)
        frame = tb[-1]

        location = f"{frame.filename.split('/')[-1]}:{frame.lineno}"
        code = frame.line.strip() if frame.line else ""

        text = (f"{msg}: " if msg else "") + f"{type(err).__name__}: {err}"
        text = re.sub(r"[\n^]", " ", text)
        text = re.sub(r" {2,}", " ", text)

        debug = f"{location} {code}"

        self.lcd.write(text, row)
        self.lcd.write(debug, row + 1)
        if msg:
            print(msg)
        traceback.print_exception(type(err), err, err.__traceback__)
        self.get_action()

    def add_action(self, name):
        """Queue an input action.

        Actions are typically generated by hardware event bindings.
        """
        self._actions.append(name)

    def clear_actions(self):
        """Remove all pending input actions."""
        self._actions = []
        
    def get_action(self, idle=CONFIG["poll_time"], timeout=0):
        """Wait for and return the next input action.

        Continuously updates the LCD while polling for actions.

        Args:
            idle (float): Delay in seconds between polling iterations.
            timeout (float): Seconds to wait (0 = wait indefinitely).

        Returns:
            object: Next action from the queue, None if timed out
        """
        t0 = time.time()
        self._scrolltimer = t0
        self.lcd.buffered = True
        while not self._actions:
            self.lcd.update()
            time.sleep(idle)
            if timeout and time.time() - t0 > timeout:
                self.buffered = False
                return None
        self.lcd.buffered = False
        return self._actions.pop(0)

    @staticmethod
    def shell_cmd(cmd, **kwargs):
        """Run a shell command and return its stdout.

        Wrapper around subprocess.run with sensible defaults:
          - check=True (raises on failure)
          - captures stdout
          - ASCII decoding
          - strips trailing newline

        Args:
            cmd (str | list): Command string (or list if shell=False)
            **kwargs (dict): Passed through to subprocess.run

        Returns:
            str: Command stdout as a stripped string

        Raises:
            subprocess.CalledProcessError on failure (unless overridden)
        """
        kwargs = {
            "check": True,
            "shell": True,
            "stdout": subprocess.PIPE,
            "encoding": "ascii",
        } | kwargs            
        return subprocess.run(cmd, **kwargs).stdout.rstrip("\n")

