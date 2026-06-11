#!/usr/bin/env python3
"""Front-end menu for SquishBox apps"""

from pathlib import Path
import subprocess
import sys

from squishbox import SquishBox, CONFIG, __version__
from squishbox.config import save_state, CONFIG_PATH

ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]

paths = []
builtin_dir = Path(__file__).parent
for path in builtin_dir.glob("*.py"):
    if path.stem in {"__init__", Path(__file__).stem}:
        continue
    paths.append(path)
for d in CONFIG.get("app_dirs", []):
    d = Path(d).expanduser()
    if d.exists():
        for path in d.glob("*.py"):
            paths.append(path)
paths.sort(key=lambda path: path.stem)
apps = {path.stem: path for path in paths}
if CONFIG.get("startup_app") in apps:
    subprocess.run([sys.executable, apps[CONFIG["startup_app"]]])

sb = SquishBox()

last = 0
while True:
    sb.lcd.clear()
    sb.lcd.write(f"SquishBox {__version__}", row=0)
    if sb.wifienabled:
        sb.lcd.write(sb.lcd["wifi_on"], row=1, col=0)
    else:
        sb.lcd.write(sb.lcd["wifi_off"], row=1, col=0)
    match sb.menu_choose([
        *apps,
        "LCD Settings..",
        "MIDI Settings..",
        "WiFi Settings..",
        "Exit"
    ], row=ROWS - 1, i=last, timeout=0):
        case last, "LCD Settings..":
            sb.menu_lcdsettings()
        case last, "MIDI Settings..":
            sb.menu_midisettings()
        case last, "WiFi Settings..":
            sb.menu_wifisettings()
        case last, "Exit" | None:
            if sb.menu_exit() == "shell":
                break
        case last, name if name in apps:
            sb.lcd.write(name.ljust(COLS), row=ROWS - 2)
            sb.lcd.write("starting..".rjust(COLS), row=ROWS - 1)

            CONFIG["startup_app"] = name
            save_state(CONFIG_PATH, CONFIG)
            sb.close()
            subprocess.run([sys.executable, apps[name]])
            sb = SquishBox()
            CONFIG.pop("startup_app", None)
            save_state(CONFIG_PATH, CONFIG)

