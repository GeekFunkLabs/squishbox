#!/usr/bin/env python3
"""Front-end menu for SquishBox scripts"""

from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

from squishbox import SquishBox, CONFIG, __version__
from squishbox.config import save_state, CONFIG_PATH

ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]


def run_script(path):
    spec = spec_from_file_location(path.stem, path)
    mod = module_from_spec(spec)
    CONFIG["startup_script"] = path.stem
    save_state(CONFIG_PATH, CONFIG)
    sb.knob1.clear_binds()
    sb.button1.clear_binds()
    
    try:
        spec.loader.exec_module(mod)
        if hasattr(mod, "main"):
            mod.main()
    except Exception as e:
        sb.display_error(e)
    finally:
        CONFIG.pop("startup_script", None)
        save_state(CONFIG_PATH, CONFIG)
        sb.knob1.clear_binds()
        sb.button1.clear_binds()
        sb.knob1.bind('left', sb.action_dec)
        sb.knob1.bind('right', sb.action_inc)
        sb.button1.bind('tap', sb.action_do)
        sb.button1.bind('hold', sb.action_back)


sb = SquishBox()
sb.knob1.bind('left', sb.action_dec)
sb.knob1.bind('right', sb.action_inc)
sb.button1.bind('tap', sb.action_do)
sb.button1.bind('hold', sb.action_back)

paths = []
builtin_dir = Path(__file__).parent
for path in builtin_dir.glob("*.py"):
    if path.stem in {"__init__", Path(__file__).stem}:
        continue
    paths.append(path)
for d in CONFIG.get("script_paths", []):
    d = Path(d).expanduser()
    if not d.exists():
        continue
    for path in d.glob("*.py"):
        paths.append(path)
paths.sort(key=lambda path: path.stem)
scripts = {path.stem: path for path in paths}
if CONFIG.get("startup_script") in scripts:
    run_script(scripts[CONFIG["startup_script"]])

last = 0
while True:
    sb.lcd.clear()
    sb.lcd.write(f"SquishBox {__version__}", row=0)
    match sb.menu_choose([
        *scripts,
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
        case last, name:
            sb.lcd.write(name.ljust(COLS), row=ROWS - 2)
            sb.lcd.write("starting..".rjust(COLS), row=ROWS - 1)
            run_script(scripts[name])

