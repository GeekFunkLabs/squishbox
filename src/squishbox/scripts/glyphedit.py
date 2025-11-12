#!/usr/bin/env python3
"""Edit and save glyphs"""

from pathlib import Path
import yaml

from squishbox import SquishBox, CONFIG
from squishbox.config import save_state


COLS = CONFIG["lcd_cols"]
ROWS = CONFIG["lcd_rows"]
MENU_TIME = CONFIG["menu_timeout"]
FRAME_TIME = CONFIG["frame_time"]

glyphs = CONFIG["glyphs_5x8"].copy()
sb = SquishBox()


def edit_glyph(name, text):
    text = text.replace(" ", "").replace("\n", "")
    sb.lcd.write(f"{name}:".ljust(COLS), row=0)
    p = 0
    b = "X"
    while True:    
        sb.lcd.define_glyph(
            0, text[:p] + b + text[p + 1:]
        )
        sb.lcd.write(chr(0), row=1, col=COLS - 1)
        match sb.get_action(timeout=FRAME_TIME):
            case "inc":
                p = (p + 1) % 40
                b = "X"
            case "dec":
                p = (p - 1) % 40
                b = "X"
            case "do":
                text = (
                    text[:p] +
                    ("X" if text[p] == "-" else "-") +
                    text[p + 1:]
                )
            case "back":
                break
            case None:
                b = "-" if b == "X" else "X"
    return "\n".join([text[i:i + 5] for i in range(0, 40, 5)])


def main():
    sb.knob1.bind('left', sb.action_dec)
    sb.knob1.bind('right', sb.action_inc)
    sb.button1.bind('tap', sb.action_do)
    sb.button1.bind('hold', sb.action_back)
    sb.lcd.clear()

    last = 0
    while True:
        sb.lcd.clear()
        sb.lcd.write("Glyph Editor", row=0)
        i, name = sb.menu_choose(
            [*[f"{chr(0)} {s}" for s in glyphs],
             "Add Glyph",
             "Save Changes",
             "LCD Settings..",
             "Exit"
            ], row=1, i=last, timeout=0,
            func=lambda i: sb.lcd.define_glyph(
                0, list(glyphs.values())[i]
            ) if i < len(glyphs) else None
        )
        last = i if name != None else last
        if name == "Add Glyph":
            sb.lcd.write("Add Glyph:".ljust(COLS), row=0)
            name = sb.menu_entertext().strip()
            sb.lcd.write(" " * COLS, row=1)
            if name != "" and name not in glyphs:
                last = len(glyphs)
                glyphs[name] = edit_glyph(name, "-" * 40)
        elif name == "Save Changes":
            save_state(CONFIG.update(glyphs=glyphs))
            sb.lcd.write("changes saved".rjust(COLS), row=1)
            sb.get_action(timeout=MENU_TIME)
        elif name == "LCD Settings..":
            sb.menu_lcdsettings()
        elif name == "Exit" or name == None:
            if sb.menu_exit() == "shell":
                sb.lcd.default_custom_glyphs()
                break
        else:
            name = name[2:]
            sb.lcd.write(f"{chr(0)} {name}".ljust(COLS), row=0)
            match sb.menu_choose(["Edit", "Delete"], row=1)[1]:
                case "Edit":
                    glyphs[name] = edit_glyph(name, glyphs[name])
                case "Delete":
                    del glyphs[name]
                    last = 0


if __name__ == "__main__":
    main()

