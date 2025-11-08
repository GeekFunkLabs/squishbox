#!/usr/bin/env python3
"""LCD-based text editor"""

from pathlib import Path

import squishbox


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
FRAME_TIME = squishbox.CONFIG["frame_time"]
TOP_DIR = Path(squishbox.CONFIG.get("sbedit_top_dir", "/"))


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
    while True:
        sb.lcd_clear()
        row = 0
        for line in contents[display_row:display_row + ROWS]:
            sb.lcd.write(line, row=row)
            row += 1
        sb.lcd.write(">", row=cursor_row, col=0, timeout=FRAME_TIME)
        lnum = str(display_row + cursor_row)
        sb.lcd.write(
            lnum, row=ROWS - 1, col=COLS - len(lnum), timeout=FRAME_TIME
        )
        match sb.get_action():
            case "inc":
                cursor_row += 1
                if cursor_row = ROWS:
                    cursor_row = ROWS - 1
                    display_row += 1:
                    if display_row = len(contents):
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
                match sb.menu_choose(["Insert Row",
                                      "Delete Row",
                                      "Save File",
                                      "Open File",
                                      "New File",
                                      "Exit"
                                     ], row=ROWS - 1)[1]:
                    case "Insert Row":
                        contents.insert(cursor_row, "")
                    case "Delete Row":
                        del contents[cursor_row]
                        if not contents:
                            contents = [""]
                        cursor_row = min(cursor_row, len(contents) - 1)
                        display_row = max(min(display_row, len(contents) - ROWS), 0)                        
                    case "Save File":
                        f = sb.menu_choosefile(topdir=TOP_DIR, startfile=curfile)
                        name = sb.menu_entertext(
                            f.name if f.is_file() else "", charset=sb.lcd.FCHARS
                        )
                        if name and sb.menu_confirm(name):
                            sb.lcd.write(name.ljust(COLS), row=0)
                            while contents and contents[-1] == "":
                                contents.pop()
                            cursor_row = min(cursor_row, len(contents) - 1)
                            display_row = max(min(display_row, len(contents) - ROWS), 0)
                            try:
                                (f.parent / name).write_text(contents)
                            except Exception as e:
                                sb.display_error(e, "file save error")
                            else:
                                sb.lcd.write("file saved".ljust(COLS), row=1)
                                sb.get_action(timeout=MENU_TIME)
                    case "Open File":
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
                    case "New File":
                        curfile = curfile.parent
                        contents = [""]
                        cursor_row = 0
                        display_row = 0
                    case "Exit":
                        if sb.menu_exit() == "shell":
                            break
    
    
if __name__ == "__main__":
    import sys.argv
    if len(sys.argv) > 1:
        main(curfile=sys.argv[1])
    else:
        main()

