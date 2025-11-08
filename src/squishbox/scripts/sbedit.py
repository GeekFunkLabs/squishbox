#!/usr/bin/env python3
"""LCD-based text editor"""

from pathlib import Path

import squishbox


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
FRAME_TIME = squishbox.CONFIG["frame_time"]
TOP_DIR = Path(squishbox.CONFIG.get("sbedit_top_dir", Path.home()))

def main(curfile = None):
    sb = squishbox.SquishBox()
    sb.knob1.bind('left', sb.action_dec)
    sb.knob1.bind('right', sb.action_inc)
    sb.button1.bind('tap', sb.action_do)
    sb.button1.bind('hold', sb.action_back)
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

    cursor_row = 0
    display_row = 0
    last = 0
    while True:
        sb.lcd.clear()
        row = 0
        for line in contents[display_row:display_row + ROWS]:
            sb.lcd.write(line.ljust(COLS), row=row)
            row += 1
        sb.lcd.write(
            f"{display_row + cursor_row}>",
            row=cursor_row, col=0, timeout=FRAME_TIME
        )
        match sb.get_action():
            case "inc":
                cursor_row += 1
                if cursor_row == ROWS:
                    cursor_row = ROWS - 1
                    display_row += 1
                    if display_row == len(contents):
                        contents.append("")
            case "dec":
                cursor_row -= 1
                if cursor_row < 0:
                    cursor_row = 0
                    display_row = max(display_row - 1, 0)
            case "do":
                i = display_row + cursor_row
                contents[i] = sb.menu_entertext(contents[i], row=cursor_row)
                sb.lcd.clear()
            case "back":
                i, choice = sb.menu_choose(["Insert Row",
                                            "Delete Row",
                                            "Save File",
                                            "Open File",
                                            "New File",
                                            "Exit"
                                           ], row=ROWS - 1, i=last)
                last = i if i != -1 else last
                if choice == "Insert Row":
                    contents.insert(display_row + cursor_row, "")
                if choice ==  "Delete Row":
                    del contents[display_row + cursor_row]
                    if not contents:
                        contents = [""]
                    cursor_row = min(cursor_row, len(contents) - 1)
                    display_row = max(min(display_row, len(contents) - ROWS), 0)                        
                if choice ==  "Save File":
                    f = sb.menu_choosefile(topdir=TOP_DIR, startfile=curfile)
                    name = sb.menu_entertext(
                        f.name if f.is_file() else "", charset=sb.lcd.FCHARS
                    ).strip()
                    if name and sb.menu_confirm(name):
                        sb.lcd.write(name.ljust(COLS), row=0)
                        while contents and contents[-1] == "":
                            contents.pop()
                        cursor_row = min(cursor_row, len(contents) - 1)
                        display_row = max(min(display_row, len(contents) - ROWS), 0)
                        try:
                            (f.parent / name).write_text("\n".join(contents))
                        except Exception as e:
                            sb.display_error(e, "file save error")
                        else:
                            sb.lcd.write("file saved".ljust(COLS), row=1)
                            sb.get_action(timeout=MENU_TIME)
                if choice ==  "Open File":
                    f = sb.menu_choosefile(topdir=TOP_DIR, startfile=curfile)
                    if f.is_file():
                        try:
                            contents = f.read_text().splitlines()
                        except Exception as e:
                            sb.display_error(e, "error opening file")
                        else:
                            curfile = f
                            cursor_row = 0
                            display_row = 0
                if choice ==  "New File":
                    curfile = curfile.parent
                    contents = [""]
                    cursor_row = 0
                    display_row = 0
                if choice ==  "Exit":
                    if sb.menu_exit() == "shell":
                        break

    
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main(curfile=Path(sys.argv[1]).resolve())
    else:
        main()

