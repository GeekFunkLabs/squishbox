from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

from squishbox import SquishBox, CONFIG, __version__
from squishbox.config import save_state

ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]


def run_script(path):
    spec = spec_from_file_location(path.stem, path)
    mod = module_from_spec(spec)
    CONFIG["startup_script"] = path.stem
    save_state(CONFIG)

    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()

    del CONFIG["startup_script"]
    save_state(CONFIG)


def main():
    scripts = []
    builtin_dir = Path(__file__).parent
    for path in builtin_dir.glob("*.py"):
        if path.stem in {"__init__", Path(__file__).stem}:
            continue
        scripts.append(path)
    for d in CONFIG.get("script_paths", []):
        d = Path(d).expanduser()
        if not d.exists():
            continue
        for path in d.glob("*.py"):
            scripts.append(path)
    scripts.sort(key=lambda path: path.stem)
    names = [path.stem for path in scripts]
    if CONFIG.get("startup_script") in names:
        run_script(scripts[
            names.index(CONFIG["startup_script"])
        ])

    sb = SquishBox()
    def clear_binds():
        sb.knob1.clear_binds()
        sb.button1.clear_binds()
    def add_binds():
        sb.knob1.bind('left', sb.action_dec)
        sb.knob1.bind('right', sb.action_inc)
        sb.button1.bind('tap', sb.action_do)
        sb.button1.bind('hold', sb.action_back)
    clear_binds()
    add_binds()

    last = 0
    while True:
        sb.lcd.clear()
        sb.lcd.write(f"SquishBox {__version__}", row=0)
        match sb.menu_choose([*names,
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
                sb.lcd.write("starting ".rjust(COLS), row=ROWS - 1)
                clear_binds()
                run_script(scripts[names.index(name)])
                clear_binds()
                add_binds()


if __name__ == "__main__":
    main()

