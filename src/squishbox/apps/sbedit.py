#!/usr/bin/env python3
"""LCD-based text editor"""

from pathlib import Path

import squishbox


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
FRAME_TIME = squishbox.CONFIG["frame_time"]
TOP_DIR = Path(squishbox.CONFIG.get("top_directory", Path.home()))

def main(curfile = None):
    sb = squishbox.SquishBox()
    sb.lcd.clear()

    if curfile:
        try:
            contents = curfile.read_text().splitlines()
        except Exception as e:
            sb.display_error(e, "error opening file")
            curfile = None
            contents = [""]
    else:
        contents = [""]

    crow = 0
    irow = 0
    last = 0
    while True:
        sb.lcd.clear()
        for i in range(irow, min(irow + ROWS, len(contents))):
            if i >= len(contents):
                sb.lcd.write(" " * COLS, row=i - irow)
            else:
                sb.lcd.write(contents[i].ljust(COLS), row=i - irow)
        sb.lcd.write(
            f"{irow + crow + 1}>",
            row=crow, col=0, timeout=FRAME_TIME
        )
        match sb.get_action():
            case "inc":
                crow += 1
                if crow == ROWS or crow == len(contents):
                    crow = ROWS - 1
                    irow += 1
                    if irow == len(contents):
                        contents.append("")
            case "dec":
                crow -= 1
                if crow < 0:
                    crow = 0
                    irow = max(irow - 1, 0)
            case "select":
                i = irow + crow
                contents[i] = sb.menu_entertext(contents[i], row=crow).rstrip()
            case "back":
                i, choice = sb.menu_choose([
                    "Open File",
                    "Save File",
                    "Insert Row",
                    "Delete Row",
                    "Clear Rows",
                    "Exit"
                ], row=ROWS - 1, i=last)
                last = i if choice != None else last
                if choice == "Insert Row":
                    contents.insert(irow + crow, "")
                if choice ==  "Delete Row":
                    del contents[irow + crow]
                    if not contents:
                        contents = [""]
                    crow = min(crow, len(contents) - 1)
                    irow = max(min(irow, len(contents) - ROWS), 0)                        
                if choice ==  "Save File":
                    f = sb.menu_choosefile(topdir=TOP_DIR, start=curfile)
                    name = sb.menu_entertext(
                        f.name if f.is_file() else "", charset=sb.lcd.fnchars()
                    ).strip()
                    if name and sb.menu_confirm(name):
                        sb.lcd.write(name.ljust(COLS), row=0)
                        while contents and contents[-1] == "":
                            contents.pop()
                        crow = min(crow, len(contents) - 1)
                        irow = max(min(irow, len(contents) - ROWS), 0)
                        try:
                            (f.parent / name).write_text("\n".join(contents))
                        except Exception as e:
                            sb.display_error(e, "file save error")
                        else:
                            sb.lcd.write("file saved".ljust(COLS), row=1)
                            sb.get_action(timeout=MENU_TIME)
                if choice ==  "Open File":
                    f = sb.menu_choosefile(topdir=TOP_DIR, start=curfile)
                    if f.is_file():
                        try:
                            contents = f.read_text().splitlines()
                        except Exception as e:
                            sb.display_error(e, "error opening file")
                        else:
                            curfile = f
                            crow = 0
                            irow = 0
                if choice ==  "Clear Rows":
                    curfile = curfile.parent
                    contents = [""]
                    crow = 0
                    irow = 0
                if choice ==  "Exit":
                    if sb.menu_exit() == "shell":
                        break

    
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main(curfile=Path(sys.argv[1]).resolve())
    else:
        main()

