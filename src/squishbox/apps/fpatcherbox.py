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

VOICE_TYPES = {
    "note": "NT", "ctrl": "CC", "kpress": "KP",
    "prog": "PC", "pbend": "PB", "cpress": "CP"
}

FLUIDFX_VALS = {
    name: (
        fsname,
        [format(x + z * i, fmt) for i in range(int((y - x) / z) + 1)]
    )  for fsname, x, y, z, name, fmt in (
        ("synth.reverb.room-size", 0, 1, 0.01, "Reverb Size", "4.2f"),
        ("synth.reverb.damp", 0, 1, 0.01, "Reverb Damp", "4.2f"),
        ("synth.reverb.width", 0, 1, 0.01, "Reverb Width", "4.2f"),
        ("synth.reverb.level", 0, 1, 0.01, "Reverb Level", "4.2f"),
        ("synth.chorus.level", 0, 10, 1, "Chorus Level", "4.1f"),
        ("synth.chorus.speed", 0, 5, 0.1, "Chorus Speed", "3.1f"),
        ("synth.chorus.depth", 0, 256, 1, "Chorus Depth", "3d"),
        ("synth.chorus.nr", 0, 99, 1, "Chorus Voices", "2d"),
        ("synth.gain", 0, 5, 0.1, "Gain", "4.2f"),
    )
}


def filter_keydown(evt):
    if (isinstance(evt, FluidMidiEvent) and evt.type == "note" and evt.val > 0):
        sb.add_action(evt)


class FPBox:

    def __init__(self):
        self.pno = 0
        self.last = 0
        self.showevent = False
        self.load_bank(CONFIG["fpatcherbox_path"])
        with sb.lcd.activity("loading ".rjust(COLS)):
            self.apply_patch()

    def load_bank(self, bank):
        sb.lcd.write(bank.name.ljust(COLS), row=0)
        try:
            fp.load_bank(bank)
        except Exception as e:
            sb.display_error(e, "bank load error")
            return False
        return True

    def apply_patch(self, pno=None):
        if pno != None:
            self.pno = pno
        self.pname = fp.bank.patches[self.pno]
        fp.apply_patch(self.pname)

    def run(self):
        while True:
            self.refresh_main()
            self.main_loop()
            if self.menu_loop() == "shell":
                break

    def refresh_main(self):
        sb.lcd.write(self.pname.ljust(COLS), row=0)
        sb.lcd.write(
            f"patch {self.pno + 1}/{len(fp.bank)}".rjust(COLS),
            row=1
        )
        if sb.wifienabled:
            sb.lcd.write(sb.lcd["wifi_on"], row=1, col=0)
        else:
            sb.lcd.write(sb.lcd["wifi_off"], row=1, col=0)

    def main_loop(self):
        with fp.midi_capture(sb.add_action):
            while True:
                evt = sb.get_action()
                if evt == "inc":
                    self.on_increment(1)
                elif evt == "dec":
                    self.on_increment(-1)
                elif evt == "back":
                    self.on_toggle_showevent()
                elif isinstance(evt, FluidMidiEvent):
                    self.on_midi_event(evt)
                elif hasattr(evt, "rule"):
                    self.on_rule_event(evt)
                elif evt == "do":
                    return

    def on_increment(self, inc):
        self.apply_patch((self.pno + inc) % len(fp.bank))
        self.refresh_main()

    def on_toggle_showevent(self):
        if self.showevent:
            self.showevent = False
            sb.lcd.write(
                "show events OFF".rjust(COLS), row=1, timeout=MENU_TIME
            )
        else:
            self.showevent = True
            sb.lcd.write(
                "show events ON".rjust(COLS), row=1, timeout=MENU_TIME
            )

    def on_midi_event(self, evt):
        if evt.type not in VOICE_TYPES:
            return
        sb.lcd.write(
            sb.lcd["note"], row=1, col=1,
            timeout=FRAME_TIME, force=False
        )
        if self.showevent:
            typ = VOICE_TYPES[evt.type]
            if hasattr(evt, "num"):
                sb.lcd.write(
                    f"{evt.chan}:{typ}{evt.num}={evt.val}".ljust(COLS),
                    row=1, col=2, timeout=MENU_TIME
                )
            else:
                sb.lcd.write(
                    f"{evt.chan}:{typ}={evt.val}".ljust(COLS),
                    row=1, col=2, timeout=MENU_TIME
                )

    def on_rule_event(self, evt):
        if hasattr(evt.rule, "lcdwrite"):
            if hasattr(evt.rule, "format"):
                strval = format(evt.val, evt.rule.format)
                sb.lcd.write(
                    f"{evt.rule.lcdwrite} {strval}".rjust(COLS),
                    row=1, timeout=MENU_TIME
                )
            else:
                sb.lcd.write(
                    evt.rule.lcdwrite.rjust(COLS),
                    row=1, timeout=MENU_TIME
                )
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
                self.pno = fp.bank.patches.index(evt.rule.patch)
            elif isinstance(evt.rule.patch, int):
                self.pno = evt.rule.patch - 1
            elif evt.rule.patch[-1] in "+-":
                num, sign = evt.rule.patch[:-1], evt.rule.patch[-1]
                self.pno = (self.pno + int(sign + num)) % len(fp.bank)
            self.apply_patch()
            self.refresh_main()

    def menu_loop(self):
        i, choice = sb.menu_choose(
            ["Load Bank", "Save Bank", "Save Patch", "Delete Patch",
             "Sounds..", "Layers..", "Effects..", "System Menu.."],
            row=1, i=self.last
        )
        self.last = i if choice != None else self.last
        if choice == "Load Bank":
            self.choose_bank()
        elif choice == "Save Bank":
            self.save_bank()
        elif choice == "Save Patch":
            self.save_patch()
        elif choice == "Delete Patch":
            self.delete_patch()
        elif choice == "Sounds..":
            self.edit_sounds()
        elif choice == "Layers..":
            self.edit_layers()
        elif choice == "Effects..":
            self.edit_effects()
        elif choice == "System Menu..":
            return sb.menu_systemsettings()

    def choose_bank(self):
        f = sb.menu_choosefile(
            topdir=CONFIG["banks_path"],
            start=CONFIG["fpatcherbox_path"],
            ext=".yaml"
        )
        if f.is_file() and self.load_bank(f):
            if (
                f == CONFIG["fpatcherbox_path"] and
                self.pname in fp.bank
            ):
                self.pno = fp.bank.patches.index(self.pname)
            else:
                self.pno = 0
            CONFIG["fpatcherbox_path"] = f
            save_config()
            with sb.lcd.activity("loading ".rjust(COLS)):
                self.apply_patch()

    def save_bank(self):
        f = sb.menu_choosefile(
            topdir=CONFIG["banks_path"],
            start=CONFIG["fpatcherbox_path"],
            ext=".yaml"
        )
        name = sb.menu_entertext(
            f.name if f.is_file() else "", charset=sb.lcd.fnchars()
        ).strip()
        if name and sb.menu_confirm(name):
            sb.lcd.write(name.ljust(COLS), row=0)
            try:
                fp.save_bank((f.parent / name).with_suffix(".yaml"))
            except Exception as e:
                sb.display_error(e, "bank save error")
            else:
                CONFIG["fpatcherbox_path"] = f.parent / name
                save_config()
                sb.lcd.write("bank saved".ljust(COLS), row=1)
                sb.get_action(timeout=MENU_TIME)

    def save_patch(self):
        sb.lcd.write("Save patch as:".ljust(COLS), row=0)
        newname = sb.menu_entertext(self.pname).strip()
        if sb.menu_confirm(newname):
            if newname != self.pname:
                fp.bank[newname] = fp.bank[self.pname].copy()
                self.pno = fp.bank.patches.index(newname)
                self.pname = newname
            fp.update_patch(self.pname)

    def delete_patch(self):
        sb.lcd.write("Delete patch:".ljust(COLS), row=0)
        if sb.menu_confirm(self.pname):
            del fp.bank[self.pname]
            self.apply_patch(min(self.pno, len(fp.bank) - 1))

    def edit_sounds(self):
        chan = None
        while True:
            chan = self.select_channel(chan)
            if chan is None:
                return
            sf = self.select_soundfont(chan)
            if sf is None:
                continue
            if self.select_preset(sf, chan) is None:
                continue

    def edit_layers(self):
        """Edit or add keyboard layers

        A layer is a note-to-note router rule. This menu lets the user
        view and edit/add layers. The layer channel, key range,
        key shift, and target channel can be set.
        Only patch-level layers are accessible.
        Note that a MidiRule can route to/from multiple channels,
        so editing such a rule will break it (but one could add more
        rules to get the same behavior).
        """
        rule = None
        while True:
            rule, rule_index = self.select_layer(rule)
            if rule_index is None:
                return
            if rule is None:
                continue
            rule = self.configure_layer(rule)
            if rule is None:
                continue
            rules = fp.bank.patch[self.pname].setdefault("rules", [])
            if rule_index < 0:
                rules.append(rule)
            else:
                rules[rule_index] = rule
            self.apply_patch()

    def edit_effects(self):
        last = 0
        while True:
            sb.lcd.write("Effects:".ljust(COLS), row=0)
            self.apply_patch()
            i, name = sb.menu_choose(list(FLUIDFX_VALS), row=1, i=last, timeout=0)
            if name is None:
                break
            last = i
            fsname, vals = FLUIDFX_VALS[name]
            sb.lcd.write(name.ljust(COLS), row=0)
            curval = fp.fluidsetting(fsname)
            i = min(range(len(vals)), key=lambda i: abs(float(vals[i]) - curval))
            i, choice = sb.menu_choose(
                vals, row=1, i=i, wrap=False, timeout=0,
                func=lambda i: fp.fluidsetting_set(fsname, vals[i])
            )
            if choice is None:
                fp.fluidsetting_set(fsname, curval)
            else:
                fluidsettings = fp.bank.patch[self.pname].setdefault("fluidsettings", {})
                fluidsettings[fsname] = fp.fluidsetting(fsname)

    def select_channel(self, chan=None, msg="Sounds:"):
        channel_info = []
        for c in range(fp.fluidsetting("synth.midi-channels")):
            if p := fp.bank.patch[self.pname].get(c + 1):
                name = fp.soundfonts[p.file][p.bank, p.prog]
                channel_info.append(
                    f"{c + 1}: {p.file}:{p.bank:03}:{p.prog:03} {name}"
                )
                if chan is None:
                    chan = c + 1
            else:
                channel_info.append(f"{c + 1}:")
        if chan is None:
            chan = 1
        sb.lcd.write(msg.ljust(COLS), row=0)
        i, choice = sb.menu_choose(
            channel_info, row=1, i=chan - 1, timeout=0, align="left",
            func=lambda i: sb.lcd.write(f"{i + 1}:", row=1, col=0)
        )
        if choice is None:
            return None
        else:
            return i + 1

    def select_soundfont(self, chan):
        sb.lcd.write("Set Sound File:".ljust(COLS), row=0)
        if p := fp.bank.patch[self.pname].get(chan):
            i, newsf = sb.menu_choose(
                list(fp.soundfonts) + ["Load Sound File", "No Sound"],
                i=list(fp.soundfonts).index(p.file),
                row=1, timeout=0
            )
        else:
            i, newsf = sb.menu_choose(
                list(fp.soundfonts) + ["Load Sound File"],
                row=1, timeout=0
            )
        if newsf is None:
            return None
        if newsf == "No Sound":
            del fp.bank.patch[self.pname][chan]
            self.apply_patch()
            return None
        if newsf == "Load Sound File":
            sb.lcd.write("Load Sound File:".ljust(COLS), row=0)
            newsf = sb.menu_choosefile(
                topdir=CONFIG["sounds_path"], ext=".sf2"
            )
            if not newsf.is_file():
                return None
        with sb.lcd.activity("loading ".rjust(COLS)):
            sf = fp.open_soundfont(newsf)
        return sf

    def select_preset(self, sf, chan):
        presets = []
        preset_info = []
        for bank, prog in sf:
            presets.append(SFPreset(sf.file, bank, prog))
            preset_info.append(f"{bank:03}:{prog:03} {sf[bank, prog]}")
        p = fp.bank.patch[self.pname].get(chan)
        if p and p.file == sf.file and (p.bank, p.prog) in sf:
            i = list(sf).index((p.bank, p.prog))
        else:
            i = 0
        sb.lcd.write("Choose Preset:".ljust(COLS), row=0)
        def change_preset(i):
            fp.bank.patch[self.pname][chan] = presets[i]
            self.apply_patch()
        i, choice = sb.menu_choose(
            preset_info, row=1, i=i, timeout=0, align="left",
            func=change_preset
        )
        return False if choice is None else True

    def select_layer(self, rule=None):
        rules = fp.bank.patch[self.pname].get("rules", [])
        layers = [r for r in rules if r.type == r.totype == "note"]
        sb.lcd.write("Layers:".ljust(COLS), row=0)
        if layers:
            i, rule = sb.menu_choose(
                layers + ["Add Layer", "Delete Layer"],
                i=layers.index(rule) if rule in layers else 0,
                row=1, timeout=0
            )
        else:
            i, rule = sb.menu_choose(
                ["Add Layer"], row=1, timeout=0
            )
        if rule is None:
            return rule, None
        elif rule == "Add Layer":
            return MidiRule(type="note"), -1
        elif rule == "Delete Layer":
            sb.lcd.write("Delete Layer:".ljust(COLS), row=0)
            i, rule = sb.menu_choose(layers, row=1, i=0, timeout=0)
            if rule is not None:
                del fp.bank.patch[self.pname]["rules"][rules.index(rule)]
                self.apply_patch()
            return None, 0
        return rule, rules.index(rule)

    def configure_layer(self, rule):
        if hasattr(rule, "chan"):
            chan, tochan = rule.chan.min, rule.chan.tomin
        else:
            chan, tochan = 1, 1
        if hasattr(rule, "num"):
            num_min, num_max = rule.num.min, rule.num.max
            add = rule.num.add
        else:
            num_min, num_max, add = 0, 127, 0
        sb.lcd.write(f"range: {num_min}-{num_max}".rjust(COLS), row=1)
        nchan = fp.fluidsetting("synth.midi-channels")
        with fp.midi_capture(filter_keydown):
            i, evt = sb.menu_choose(
                [f"channel: [{c + 1}]" for c in range(nchan)],
                row=0, i=chan - 1, timeout=0
            )
        if evt is None:
            return None
        elif isinstance(evt, FluidMidiEvent):
            chan, num_min = evt.chan, evt.num
        else:
            chan = i + 1
            sb.lcd.write(f"channel: {chan}".rjust(COLS), row=0)
            with fp.midi_capture(filter_keydown):
                num_min, evt = sb.menu_choose(
                    [f"range: [{n}]-{num_max}" for n in range(128)],
                    row=1, i=num_min, wrap=False, timeout=0
                )
            if evt is None:
                return None
            elif isinstance(evt, FluidMidiEvent):
                num_min = evt.num
        sb.lcd.write(f"channel: {chan}".rjust(COLS), row=0)
        with fp.midi_capture(filter_keydown):
            num_max, evt = sb.menu_choose(
                [f"range: {num_min}-[{n}]" for n in range(128)],
                row=1, i=num_max, wrap=False, timeout=0
            )
        if evt is None:
            return None
        elif isinstance(evt, FluidMidiEvent):
            num_max = evt.num
        sb.lcd.write(f"key shift:".rjust(COLS), row=0)
        i, add = sb.menu_choose(
            [format(k, "+") for k in range(-36, 37)],
            row=1, i=int(add) + 36, wrap=False, timeout=0
        )
        if add is None:
            return None
        tochan = self.select_channel(tochan, "target:")
        if tochan is None:
            return None
        return rule.copy(
            chan=f"{chan}={tochan}",
            num=f"{num_min}-{num_max}*1{add}"
        )


sb = squishbox.SquishBox()
sb.knob1.bind("left", sb.action_dec)
sb.knob1.bind("right", sb.action_inc)
sb.button1.bind("tap", sb.action_do)
sb.button1.bind("hold", sb.action_back)
sb.lcd.clear()

fp = FluidPatcher(fluidlog=-1)

CONFIG.setdefault(
    "fpatcherbox_path",
    CONFIG["banks_path"] / "testbank.yaml"
)

def main():
    FPBox().run()

if __name__ == "__main__":
    main()

