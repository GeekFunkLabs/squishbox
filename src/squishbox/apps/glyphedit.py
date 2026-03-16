#!/usr/bin/env python3
"""Edit and save glyphs"""

from pathlib import Path
import yaml

from squishbox import SquishBox, CONFIG
from squishbox.config import save_state, CONFIG_PATH


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
        sb.lcd[name] = text[:p] + b + text[p + 1:]
        sb.lcd.write(sb.lcd[name], row=1, col=COLS - 1)
        match sb.get_action(timeout=FRAME_TIME):
            case "inc":
                p = (p + 1) % 40
                b = "X"
            case "dec":
                p = (p - 1) % 40
                b = "X"
            case "select":
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


def show_glyph(i):
    if i < len(glyphs):
        sb.lcd.write(sb.lcd[list(glyphs)[i]], row=1)


def main():
    sb.lcd.clear()

    last = 0
    while True:
        sb.lcd.clear()
        sb.lcd.write("Glyph Editor", row=0)
        i, choice = sb.menu_choose(
            [*["  " + s for s in glyphs],
             "Add Glyph",
             "Save Changes",
             "LCD Settings..",
             "Exit"
            ], row=1, i=last, timeout=0,
            func=show_glyph
        )
        last = i if choice != None else last
        if choice == "Add Glyph":
            sb.lcd.write("Add Glyph:".ljust(COLS), row=0)
            name = sb.menu_entertext().strip()
            sb.lcd.write(" " * COLS, row=1)
            if name != "" and name not in glyphs:
                last = len(glyphs)
                glyphs[name] = edit_glyph(name, "-" * 40)
        elif choice == "Save Changes":
            CONFIG.update(glyphs_5x8=glyphs)
            save_state(CONFIG_PATH, CONFIG)
            sb.lcd.write("changes saved".rjust(COLS), row=1)
            sb.get_action(timeout=MENU_TIME)
        elif choice == "LCD Settings..":
            sb.menu_lcdsettings()
        elif choice == "Exit" or choice == None:
            if sb.menu_exit() == "shell":
                break
        else:
            name = choice[2:]
            sb.lcd.write(f"{sb.lcd[name]} {name}".ljust(COLS), row=0)
            match sb.menu_choose(["Edit", "Delete"], row=1)[1]:
                case "Edit":
                    glyphs[name] = edit_glyph(name, glyphs[name])
                case "Delete":
                    del glyphs[name]
                    last = 0


if __name__ == "__main__":
    main()

