#!/usr/bin/env python3
"""FluidPatcher script for the SquishBox"""

from pathlib import Path
import re
import sys
import time

from fluidpatcher import *
import squishbox
from squishbox.hardware import Output, PWMOutput

COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
FRAME_TIME = squishbox.CONFIG["frame_time"]

def edit_sounds():
    chan = 0
    while True:
        # get current presets per channel
        sb.lcd.write("Sounds:".ljust(COLS), row=0)
        sounds = {}
        channel_info = []
        for c in range(1, fp.fluidsetting("synth.midi-channels") + 1):
            if p := fp.bank[pname][c]:
                sounds[c] = p
                presetname = fp.soundfonts[p.file][p.bank, p.prog]
                channel_info.append(f"{c}: {p.file}:{p.bank:03}:{p.prog:03} {presetname}")
            else:
                channel_info.append(f"{c}:")
        # channel selection
        if chan == 0:
            chan = list(sounds)[0] if sounds else 1
        chan = sb.menu_choose(channel_info, row=1, timeout=0, align="left", i=chan - 1)[0] + 1
        if chan == 0:
            break
        while True:
            if p := sounds.get(chan):
                # select preset in the current soundfont
                sb.lcd.write(f"{chan}: {p.file}".ljust(COLS), row=0)
                sf = fp.soundfonts[p.file]
                presets = []
                preset_info = []
                for bank, prog in sf:
                    presets.append(SFPreset(p.file, bank, prog))
                    preset_info.append(f"{bank:03}:{prog:03} {sf[bank, prog]}")
                if (p.bank, p.prog) not in sf:
                    sb.lcd.write(f"{p.bank}:{p.prog}".ljust(COLS), row=1)
                    sb.get_action()
                    change_preset(chan, presets[i := 0])
                else:
                    i = list(sf).index((p.bank, p.prog))
                if sb.menu_choose(
                    preset_info, row=1, i=i, timeout=0, align="left",
                    func=lambda i: change_preset(chan, presets[i])
                )[1] == "":
                    break
            # change soundfont
            sb.lcd.write("Set Sound File:".ljust(COLS), row=0)
            if p := sounds.get(chan):
                newsf = sb.menu_choose(
                    list(fp.soundfonts) + ["Load Sound File", "No Sound"],
                    i=list(fp.soundfonts).index(p.file),
                    row=1, timeout=0)[1]
            else:
                newsf = sb.menu_choose(
                    list(fp.soundfonts) + ["Load Sound File"],
                    row=1, timeout=0)[1]
            if newsf == "":
                break
            if newsf == "No Sound":
                del fp.bank.patch[pname][chan]
                fp.apply_patch(pname)
                break
            if newsf == "Load Sound File":
                sb.lcd.write("Load Sound File:".ljust(COLS), row=0)
                newsf = sb.menu_choosefile(topdir=CONFIG["sounds_path"], ext=".sf2")
                if newsf == "":
                    break
            sounds[chan] = SFPreset(newsf, 0, 0)
            change_preset(chan, sounds[chan])

def change_preset(chan, preset):
    fp.bank.patch[pname][chan] = preset
    fp.apply_patch(pname)


def edit_layers():
    """Edit or add keyboard layers

    A layer is a note-to-note router rule. This menu lets the user
    view and edit/add layers. The layer channel, key range,
    key shift, and target channel can be set.
    Only patch-level layers are accessible.
    Note that a MidiRule can route to/from multiple channels,
    so editing such a rule will break it (but one could add more
    rules to get the same behavior).
    """
    nchan = fp.fluidsetting("synth.midi-channels")
    channel_info = []
    for c in range(1, nchan):
        if p := fp.bank[pname][c]:
            presetname = fp.soundfonts[p.file][p.bank, p.prog]
            channel_info.append(f"{c}: {p.file}:{p.bank}:{p.prog} {presetname}")
        else:
            channel_info.append(f"{c}:")
    last=0
    while True:
        # layer selection
        sb.lcd.write("Layers:".ljust(COLS), row=0)
        layers = [(i, rule)
                  for i, rule in enumerate(fp.bank.patch[pname].get("rules", []))
                  if rule.type == rule.totype == "note"]
        if layers:
            ri, rules = zip(*layers)
            last, rule = sb.menu_choose(rules + ("Add Layer", "Delete Layer"),
                                        row=1, i=last, timeout=0)
        else:
            last, rule = sb.menu_choose(["Add Layer"], row=1, i=last, timeout=0)
        if rule == "":
            break
        elif rule == "Add Layer":
            rule = MidiRule(type="note", chan=1, num="0-127")
        elif rule == "Delete Layer":
            sb.lcd.write("Delete Layer:".ljust(COLS), row=0)
            if (i := sb.menu_choose(rules, row=1, i=0, timeout=0)[0]) != -1:
                del fp.bank.patch[pname]["rules"][ri[i]]
            continue
        # layer creation/editing
        num_min = -1
        fp.set_callback(action_notedown)
        sb.lcd.write(f"range: {rule.num.min}-{rule.num.max}".rjust(COLS), row=1)
        i, evt = sb.menu_choose([f"channel: [{c}]" for c in range(1, nchan + 1)],
                                row=0, i=rule.chan.min - 1, timeout=0)
        fp.set_callback(None)
        if isinstance(evt, FluidMidiEvent):
            chan, num_min = evt.chan, evt.num
        elif evt == "":
            continue
        else:
            chan = i + 1
        if num_min == -1:
            fp.set_callback(action_notedown)
            sb.lcd.write(f"channel: {chan}".rjust(COLS), row=0)
            num_min, evt = sb.menu_choose([f"range: [{n}]-{rule.num.max}" for n in range(128)],
                                          row=1, i=rule.num.min, wrap=False, timeout=0)
            fp.set_callback(None)
            if isinstance(evt, FluidMidiEvent):
                num_min = evt.num
            elif evt == "":
                continue
        fp.set_callback(action_notedown)
        sb.lcd.write(f"channel: {chan}".rjust(COLS), row=0)
        num_max, evt = sb.menu_choose([f"range: {num_min}-[{n}]" for n in range(128)],
                                      row=1, i=rule.num.max, wrap=False, timeout=0)
        fp.set_callback(None)
        if isinstance(evt, FluidMidiEvent):
            num_max = evt.num
        elif evt == "":
            continue
        sb.lcd.write(f"key shift:".rjust(COLS), row=0)
        add = sb.menu_choose([format(k, "+") for k in range(-36, 37)],
                             row=1, i=int(rule.num.add) + 36, wrap=False, timeout=0
                            )[0]
        if add == -1:
            continue
        sb.lcd.write("target:".rjust(COLS), row=0)
        tochan = sb.menu_choose(channel_info, row=1, align="left", timeout=0,
                                i=rule.chan.tomin - 1)[0] + 1
        if tochan == 0:
            continue
        newrule = rule.copy(chan=f"{chan}={tochan}",
                            num=f"{num_min}-{num_max}*1{add - 36:+}")
        if last == len(layers):
            fp.bank.patch[pname].setdefault("rules", []).append(newrule)
        else:
            fp.bank.patch[pname]["rules"][ri[last]] = newrule
        fp.apply_patch(pname)

def action_notedown(evt):
    if (isinstance(evt, FluidMidiEvent) and evt.type == "note" and evt.val > 0):
        sb.add_action(evt)


FLUIDFX_OPTS = {}
for fs, vi, vf, dv, name, fmt in (
    ("synth.reverb.room-size", 0, 1, 0.01, "Reverb Size", "4.2f"),
    ("synth.reverb.damp", 0, 1, 0.01, "Reverb Damp", "4.2f"),
    ("synth.reverb.width", 0, 1, 0.01, "Reverb Width", "4.2f"),
    ("synth.reverb.level", 0, 1, 0.01, "Reverb Level", "4.2f"),
    ("synth.chorus.level", 0, 10, 1, "Chorus Level", "4.1f"),
    ("synth.chorus.speed", 0, 5, 0.1, "Chorus Speed", "3.1f"),
    ("synth.chorus.depth", 0, 256, 1, "Chorus Depth", "3d"),
    ("synth.chorus.nr", 0, 99, 1, "Chorus Voices", "2d"),
    ("synth.gain", 0, 5, 0.1, "Gain", "4.2f"),
):
    vals = [format(vi + dv * i, fmt) for i in range(int((vf - vi) / dv) + 1)]
    FLUIDFX_OPTS[name] = vals, fs

def effects_menu():
    last = 0
    while True:
        sb.lcd.write("Effects:".ljust(COLS), row=0)
        fp.apply_patch(pname)
        i, name = sb.menu_choose(list(FLUIDFX_OPTS), row=1, i=last, timeout=0)
        if name == "":
            break
        last = i
        vals, fs = FLUIDFX_OPTS[name]
        sb.lcd.write(name.ljust(COLS), row=0)
        curval = fp.fluidsetting(fs)
        i = min(range(len(vals)), key=lambda i: abs(float(vals[i]) - curval))
        if sb.menu_choose(vals, row=1, i=i, wrap=False, timeout=0,
                          func=lambda i: fp.fluidsetting_set(fs, vals[i])
                         )[0] == -1:
            fp.fluidsetting_set(fs, curval)
        else:
            fp.bank.patch[pname].setdefault("fluidsettings", {})[fs] = fp.fluidsetting(fs)


def load_bank(bank):
    sb.lcd.write(bank.name.ljust(COLS), row=0)
    sb.lcd.write("loading bank ".ljust(COLS), row=1)
    sb.progresswheel_start()
    try:
        fp.load_bank(bank)
    except Exception as e:
        sb.progresswheel_stop()
        sb.display_error(e, "bank load error")
        return False
    sb.progresswheel_stop()
    return True


def refresh_display():
    fp.apply_patch(pname)
    sb.lcd.write(pname.ljust(COLS), row=0)
    sb.lcd.write(f"patch {pno + 1}/{len(fp.bank)}".rjust(COLS), row=1)
    if sb.wifienabled:
        sb.lcd.write(sb.lcd.glyphs["wifi_on"], row=1, col=0)
    else:
        sb.lcd.write(sb.lcd.glyphs["wifi_off"], row=1, col=0)


VOICE_TYPES = dict(note="NT", cc="CC", kpress="KP", prog="PC", pbend="PB", cpress="CP")

# main

sb = squishbox.SquishBox()
sb.knob1.bind("left", sb.action_dec)
sb.knob1.bind("right", sb.action_inc)
sb.button1.bind("tap", sb.action_do)
sb.button1.bind("hold", sb.action_back)
sb.lcd.clear()

fp = FluidPatcher()

load_bank(CONFIG["current_bank"])

showevent = False
last = 0
pno = 0
fp.apply_patch(pname := fp.bank.patches[pno])
refresh_display()
fp.set_callback(sb.add_action)
while True:
    evt = sb.get_action()
    if evt == "inc":
        pno = (pno + 1) % len(fp.bank)
        fp.apply_patch(pname := fp.bank.patches[pno])
        refresh_display()
    elif evt == "dec":
        pno = (pno - 1) % len(fp.bank)
        fp.apply_patch(pname := fp.bank.patches[pno])
        refresh_display()
    elif evt == "back":
        if showevent:
            showevent = False
            sb.lcd.write("show events OFF".rjust(COLS), row=1,
                         timeout=MENU_TIME)
        else:
            showevent = True
            sb.lcd.write("show events ON".rjust(COLS), row=1,
                         timeout=MENU_TIME)
    elif isinstance(evt, FluidMidiEvent) and evt.type in VOICE_TYPES:
        sb.lcd.write(sb.lcd.glyphs["note"], row=1, col=1,
                     timeout=FRAME_TIME, force=False)
        if showevent:
            typ = VOICE_TYPES[evt.type]
            if hasattr(evt, "num"):
                sb.lcd.write(f"{evt.chan:03}:{typ}{evt.num}={evt.val}".ljust(COLS),
                             row=1, col=2, timeout=MENU_TIME)
            else:
                sb.lcd.write(f"{evt.chan:03}:{typ}={evt.val}".ljust(COLS),
                             row=1, col=2, timeout=MENU_TIME)
    elif hasattr(evt, "rule"):
        if hasattr(evt.rule, "lcdwrite"):
            if hasattr(evt.rule, "format"):
                strval = format(evt.val, evt.rule.format)
                sb.lcd.write(f"{evt.rule.lcdwrite} {strval}".rjust(COLS), row=1,
                             timeout=MENU_TIME)
            else:
                sb.lcd.write(evt.rule.lcdwrite.rjust(COLS), row=1,
                             timeout=MENU_TIME)
        if hasattr(evt.rule, "setpin"):
            if evt.rule.setpin in outpins:
                if isinstance(outpins[evt.rule.setpin], Output):
                    if evt.val:
                        outpins[evt.rule.setpin].on()
                    else:
                        outpins[evt.rule.setpin].off()
                elif isinstance(outpins[evt.rule.setpin], PWMOutput):
                    outpins[evt.rule.setpin].level = min(100, max(0, evt.val))
        if hasattr(evt.rule, "patch"):
            if evt.rule.patch in fp.bank:
                pno = fp.bank.index(evt.rule.patch)
            elif isinstance(evt.rule.patch, int):
                pno = evt.rule.patch - 1
            elif evt.rule.patch[-1] in "+-":
                num, sign = evt.rule.patch[:-1], evt.rule.patch[-1]
                pno = (pno + int(sign + num)) % len(fp.bank) 
            fp.apply_patch(pname := fp.bank.patches[pno])
            refresh_display()
    if evt != "do":
        continue
    fp.set_callback(None)
    i, choice = sb.menu_choose(["Load Bank",
                                "Save Bank",
                                "Save Patch",
                                "Delete Patch",
                                "Sounds..",
                                "Layers..",
                                "Effects..",
                                "System Menu.."
                               ], row=1, i=last)
    last = i if i != -1 else last
    if choice == "Load Bank":
        lastbank = CONFIG["current_bank"]
        f = sb.menu_choosefile(
            topdir=CONFIG["banks_path"],
            startfile=CONFIG["banks_path"] / CONFIG["current_bank"],
            ext=".yaml"
        )
        if f and load_bank(f):
            CONFIG["current_bank"] = f
            save_state(CONFIG)
            if CONFIG["current_bank"] == lastbank and pname in fp.bank:
                pno = fp.bank.index(pname)
            else:
                pno = 0
            fp.apply_patch(pname := fp.bank.patches[pno])
    elif choice == "Save Bank":
        f = sb.menu_choosefile(topdir=CONFIG["bank_path"],
                               startfile=fp.bankfile,
                               ext=".yaml")
        if f != "":
            sb.lcd.write("Save as:".ljust(COLS), row=0)
            name = sb.menu_entertext(f.name)
            if sb.menu_confirm(name):
                sb.lcd.write(name.ljust(COLS), row=0)
                try:
                    fp.save_bank((f.parent / name).with_suffix(".yaml"))
                except Exception as e:
                    sb.display_error(e, "bank save error")
                else:
                    CONFIG["current_bank"] = f.parent / name
                    save_state(CONFIG)
                    sb.lcd.write("bank saved".ljust(COLS), row=1)
                    sb.get_action(timeout=MENU_TIME)
    elif choice == "Save Patch":
        sb.lcd.write("Save patch as:".ljust(COLS), row=0)
        newname = sb.menu_entertext(pname)
        if sb.menu_confirm(newname):
            if newname != pname:
                fp.bank[newname] = fp.bank[pname].copy()
                pno = fp.bank.index(newname)
                pname = newname
            fp.update_patch(pname)
    elif choice == "Delete Patch":
        sb.lcd.write("Delete patch:".ljust(COLS), row=0)
        if sb.menu_confirm(pname):
            del fp.bank[pname]
            pno = min(pno, len(fp.bank) - 1)
            fp.apply_patch(pname := fp.bank.patches[pno])
    elif choice == "Sounds..":
        edit_sounds()
    elif choice == "Layers..":
        edit_layers()
    elif choice == "Effects..":
        effects_menu()
    elif choice == "System Menu..":
        if sb.menu_systemsettings() == "shell":
            break
    fp.set_callback(sb.add_action)
    refresh_display()

