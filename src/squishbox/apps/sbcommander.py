#!/usr/bin/env python3
"""LCD-based orthodox file manager"""

from pathlib import Path
import shutil

import squishbox


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
TOP_DIR = Path(squishbox.CONFIG.get("top_directory", Path.home()))


def select_files(path):
    irow, crow = 0, 0
    paths = sorted([p for p in path.iterdir() if p.is_file()])
    sel = [False for p in paths]
    sb.lcd.setcursormode("line")
    while True:
        for i in range(irow, min(irow + ROWS, len(paths))):
            if i >= len(paths):
                sb.lcd.write(" " * COLS, row=i - irow)
                continue
            if sel[i]:
                sb.lcd.write((sb.lcd["check"] + paths[i].name).ljust(COLS), row=i - irow)
            else:
                sb.lcd.write((" " + paths[i].name).ljust(COLS), row=i - irow)
        sb.lcd.setcursorpos(crow, 0)
        match sb.get_action():
            case "inc":
                crow += 1
                if crow == ROWS or crow == len(paths):
                    crow -= 1
                    irow = min(irow + 1, len(paths) - ROWS) % len(paths)
            case "dec":
                crow -= 1
                if crow < 0:
                    crow = 0
                    irow = max(irow - 1, 0)
            case "select":
                i = irow + crow
                sel[i] = not sel[i]
            case "back":
                break
    sb.lcd.setcursormode("hide")
    return [paths[i] for i in range(len(sel)) if sel[i]]


def copy_unique(src, dest_dir):
    if (dest_dir / src.name).exists():
        i = 1
        while (dest_dir / f"{src.stem}_{i}{src.suffix}").exists():
            i += 1
        shutil.copy2(src, dest_dir / f"{src.stem}_{i}{src.suffix}")
    else:
        shutil.copy2(src, dest_dir)


sb = squishbox.SquishBox()

lastdir, src, dest = None, None, None
while True:
    sb.lcd.clear()
    opts = [
        "Run Command",
        "Eject Drives",
        "System Menu..",
    ]
    if src == None:
        opts[0:0] = ["Choose File(s).."]
    else:
        opts[0:0] = ["Copy", "Move", "Delete",]
        if isinstance(src, list):
            sb.lcd.write(
                " ".join([p.name for p in src]).ljust(COLS),
                row=0,
            )
        elif src.is_dir():
            sb.lcd.write(f"{src.name}/".ljust(COLS), row=0)
            opts[2:2] = ["Make Directory", "Rename"]
        else:
            sb.lcd.write(src.name.ljust(COLS), row=0)
            opts[2:2] = ["Rename"]
    i, choice = sb.menu_choose(opts, row=ROWS - 1, timeout=0)
    if choice == None:
        src = None
        continue
    elif choice == "Choose File(s)..":
        src = sb.menu_choosefile(topdir=TOP_DIR, start=lastdir)
        if src.is_file():
            lastdir = src.parent
        else:
            lastdir = src
            sb.lcd.write((str(src) + "/").ljust(COLS), row=0)
            i, choice = sb.menu_choose([
                "Select Multiple",
                "Select All",
                "Select Tree",
            ], row=ROWS - 1, timeout=0)
            if choice == None:
                continue
            elif choice == "Select Multiple":
                src = select_files(src)
            elif choice == "Select All":
                src = [p for p in src.iterdir() if p.is_file()]
            elif choice == "Select Tree":
                pass
        continue
    elif choice == "System Menu..":
        if sb.menu_systemsettings() == "shell":
            break
    elif choice == "Eject Drives":
        sb.lcd.write("Eject Drives".ljust(COLS), row=ROWS - 2)
        sb.lcd.write("please wait ".rjust(COLS), row=ROWS - 1)
        sb.lcd.activity_start()
        for name, info in [b.split(maxsplit=1) for b in (
            sb.shell_cmd("lsblk -lpo NAME,TYPE,TRAN").splitlines()
        )]:
            if "usb" in info and "/media" in info:
                sb.shell_cmd(f"udisksctl unmount -b {name}")
                sb.shell_cmd(f"udisksctl power-off -b {name}")
        sb.lcd.activity_stop()
        sb.lcd.write("safe to remove".rjust(COLS), row=ROWS - 1)
        sb.get_action(timeout=MENU_TIME)
    elif choice == "Run Command":
        sb.lcd.write("Run Command:".ljust(COLS), row=ROWS - 2)
        cmd = sb.menu_entertext().strip()
        if isinstance(src, list):
            args = " ".join([p.name for p in src])
            cmd = sb.menu_entertext(f"{cmd} {args}", i=-1).strip()
            cwd = src[0].parent
        elif src != None:
            cmd = sb.menu_entertext(f"{cmd} {src.name}", i=-1).strip()
            cwd = src.parent
        else:
            cwd = None
        try:
            out = sb.shell_cmd(cmd, cwd=cwd, timeout=10)
        except Exception as e:
            sb.display_error(e)
        else:
            out = ["$ " + cmd] + out.splitlines() + ["..."]
            irow, crow = 0, 0
            while True:
                for i in range(irow, min(irow + ROWS, len(out))):
                    sb.lcd.write(
                        (out[i] if i < len(out) else "").ljust(COLS),
                        row=i - irow
                    )
                match sb.get_action():
                    case "inc":
                        crow += 1
                        if crow == ROWS or crow == len(out):
                            crow -= 1
                            irow = min(irow + 1, len(out) - ROWS) % len(out)
                    case "dec":
                        crow -= 1
                        if crow < 0:
                            crow = 0
                            irow = max(irow - 1, 0)
                    case "select" | "back":
                        break
    elif choice == "Make Directory":
        sb.lcd.write("Make Directory:".ljust(COLS), row=ROWS - 2)
        name = sb.menu_entertext(charset=sb.lcd.fnchars()).strip()
        if sb.menu_confirm(name):
            try:
                (src / name).mkdir()
            except Exception as e:
                sb.display_error(e)
    elif choice == "Rename":
        sb.lcd.write("Rename:".ljust(COLS), row=ROWS - 2)
        name = sb.menu_entertext(src.name, charset=sb.lcd.fnchars()).strip()
        if sb.menu_confirm(name):
            try:
                src.rename(name)
            except Exception as e:
                sb.display_error(e)
    elif choice == "Delete":
        if sb.menu_confirm("Delete?"):
            try:
                if isinstance(src, list):
                    for p in src:
                        p.unlink()
                elif src.is_file():
                    src.unlink()
                else:
                    shutil.rmtree(src)
            except Exception as e:
                sb.display_error(e)
    else:
        dest = sb.menu_choosefile(topdir=TOP_DIR, start=dest)
        dest = dest.parent if dest.is_file() else dest
        if choice == "Copy":
            try:
                if isinstance(src, list):
                    for p in src:
                        copy_unique(p, dest)
                elif src.is_file():
                    copy_unique(src, dest)
                else:
                    shutil.copytree(src, dest, dirs_exist_ok=True)
            except Exception as e:
                sb.display_error(e)
        elif choice == "Move":
            try:
                if isinstance(src, list):
                    for p in src:
                        shutil.copy2(p, dest)
                else:
                    shutil.move(src, dest)
            except Exception as e:
                sb.display_error(e)
    src = None
        

