from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

from squishbox import SquishBox, CONFIG, __version__


ROWS = CONFIG["lcd_rows"]
COLS = CONFIG["lcd_cols"]


def discover_scripts():
    scripts = []
    builtin_dir = Path(__file__).parent
    for path in builtin_dir.glob("*.py"):
        if path.stem in {"__init__", Path(__file__).stem}:
            continue
        scripts.append(path)
    for d in CONFIG.get("script_dirs", []):
        d = Path(d).expanduser()
        if not d.exists():
            continue
        for path in d.glob("*.py"):
            scripts.append(path)
    return scripts


def load_script(path: Path):
    spec = spec_from_file_location(path.stem, path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    sb = SquishBox()    
    sb.knob1.bind('left', sb.action_dec)
    sb.knob1.bind('right', sb.action_inc)
    sb.button1.bind('tap', sb.action_do)
    sb.button1.bind('hold', sb.action_back)

    scripts = discover_scripts()
    scripts.sort(key=lambda path: path.stem)
    names = [path.stem for path in scripts]

    while True:
        sb.lcd.clear()
        sb.lcd.write(f"SquishBox {__version__}", row=0)
        match sb.menu_choose([*names,
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
            case name:
                sb.lcd.write(name.ljust(COLS), row=ROWS - 2)
                sb.lcd.write("starting ".rjust(COLS), row=ROWS - 1)
                
                mod = load_script(scripts[names.index(name)])
                if hasattr(mod, "main"):
                    mod.main()


if __name__ == "__main__":
    main()

