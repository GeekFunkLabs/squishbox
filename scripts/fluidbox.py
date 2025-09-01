#!/usr/bin/env python3
"""FluidPatcher script for the SquishBox"""

from pathlib import Path
import re
import sys
import time

from fluidpatcher import FluidPatcher, SFPreset, MidiRule
from fluidpatcher.pfluidsynth import FluidMidiEvent
import squishbox

# this script is designed for a 16x2 LCD
COLS, ROWS = 16, 2

FLUIDFX_OPTS = {}
for fs, vi, vf, dv, name, fmt in (
    ('synth.reverb.room-size', 0, 1, 0.1, 'Reverb Size', '4.1f'),
    ('synth.reverb.damp', 0, 1, 0.1, 'Reverb Damp', '4.1f'),
    ('synth.reverb.width', 0, 100, 0.5, 'Reverb Width', '5.1f'),
    ('synth.reverb.level', 0, 1, 0.01, 'Reverb Level', '5.2f'),
    ('synth.chorus.nr', 0, 99, 1, 'Chorus Voices', '2d'),
    ('synth.chorus.level', 0, 10, 0.1, 'Chorus Level', '4.1f'),
    ('synth.chorus.speed', 0, 21, 0.1, 'Chorus Speed', '4.1f'),
    ('synth.chorus.depth', 0.3, 5.0, 0.1, 'Chorus Depth', '3.1f'),
    ('synth.gain', 0.0, 5.0, 0.1, 'Gain', '4.2f'),
):
    vals = [format(vi + dv * i, fmt) for i in range(int((vf - vi) / dv) + 1)]
    FLUIDFX_OPTS[name] = vals, fs

VOICE_TYPES = dict(note='NT', cc='CC', kpress='KP', prog='PC', pbend='PB', cpress='CP')

def effects_menu():
    while True:
        sb.lcd_write("Effects:".ljust(COLS), row=0)
        fp.apply_patch(pname)
        name = sb.menu_choose(list(FLUIDFX_OPTS), row=1)[1]
        if name == "":
            break
        vals, fs = FLUIDFX_OPTS[name]
        sb.lcd_write(name.ljust(COLS), row=0)
        i = min(range(len(vals)), key=lambda i: abs(float(vals[i]) - fp.fluidsetting(fs)))
        if sb.menu_choose(vals, row=1, i=i, wrap=False,
                         func=lambda i: fp.fluidsetting_set(fs, vals[i])
                        )[0] != -1:
            fp.bank.patch[pname].set_default('fluidsettings', {})[fs] = fp.fluidsetting(fs)


def edit_sounds():
    while True:
        # get current presets per channel
        sb.lcd_write("Sounds:".ljust(COLS), row=0)
        sounds = {}
        channels = []
        for chan in range(1, fp.fluidsetting('synth.midi-channels') + 1):
            if p := fp.bank[pname][chan]:
                sounds[chan] = p
                channels.append(f"{chan}: {p} {fp.soundfonts[p.file][p.bank, p.prog]}")
            else:
                channels.append(f"{chan}:")
        chan = sb.menu_choose(channels, row=1, timeout=0, align='left',
                              i=list(sounds)[0] - 1 if sounds else 0
                             )[0] + 1
        if chan == 0:
            break
        while True:
            i = 0
            if chan in sounds:
                # select preset in the current soundfont
                sb.lcd_write(f"{chan}: {sounds[chan].file}".ljust(COLS), row=0)
                sf = fp.soundfonts[sounds[chan].file]
                presets = [SFPreset(sounds[chan].file, *p) for p in sf]
                try:
                    i = list(sf).index((sounds[chan].bank, sounds[chan].prog))
                except ValueError:
                    sb.lcd_write(f"{sounds[chan].bank}:{sounds[chan].prog}".ljust(COLS), row=1)
                    sb.get_action()
                    change_preset(chan, presets[i := 0])
                if sb.menu_choose([f"{p[0]:03d}:{p[1]:03d} {sf[p]}" for p in sf],
                                  row=1, i=i, timeout=0, align='left',
                                  func=lambda i: change_preset(chan, presets[i])
                                 )[1] == "":
                    break
                i = list(fp.soundfonts).index(sounds[chan].file)
            # change/load a soundfont
            sb.lcd_write("Set Soundfont:".ljust(COLS), row=0)
            match sb.menu_choose(list(fp.soundfonts) + ["Load Soundfont", "No Soundfont"],
                                 row=1, timeout=0, i=i
                                )[1]:
                case "No Soundfont":
                    del fp.bank.patch[pname][chan]
                    fp.apply_patch(pname)
                    break
                case "Load Soundfont":
                    newsf = sb.menu_choosefile(topdir=fp.cfg.sfpath,
                                               startfile=fp.cfg.sfpath / sf,
                                               ext='.sf2')
                    if newsf == "":
                        continue
                case "":
                    continue
                case newsf:
                    pass
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
    nchan = fp.fluidsetting('synth.midi-channels')
    presets = []
    for chan in range(1, nchan + 1):
        if p := fp.bank[pname][chan]:
            presets.append(f"{chan}: {p} {fp.soundfonts[p.file][p.bank, p.prog]}")
        else:
            presets.append(f"{chan}:")
    i=0
    while True:
        sb.lcd_write("Layers:".ljust(COLS), row=0)
        layers = [rule for rule in fp.bank.patch[pname].get('rules', [])
                  if rule.type == rule.totype == 'note']
        i, rule = sb.menu_choose(layers + ["Add Layer"], row=1, i=i, timeout=0)
        if rule == "":
            break
        elif rule == "Add Layer":
            rule = MidiRule(type='note', chan=1, num='0-127')
        sb.lcd_write(f"channel: {rule.chan.min}".ljust(COLS), row=0)
        sb.lcd_write(f"range: {rule.num.min}-{rule.num.max}".ljust(COLS), row=1)
        while True:
            evt = get_midievent()
            if evt == 'back':
                continue
            elif evt == 'do':
                chan, num_min = rule.chan.min, rule.num.min
                break
            elif evt.type == 'note' and evt.val > 0:
                chan, num_min = evt.chan, evt.num
                break
        sb.lcd_write(f"channel: {chan}".ljust(COLS), row=0)
        sb.lcd_write(f"range: {num_min}-{rule.num.max}".ljust(COLS), row=1)
        while True:
            evt = get_midievent()
            if evt == 'back':
                continue
            elif evt == 'do':
                num_max = rule.num.max
                break
            elif evt.type == 'note' and evt.val > 0:
                num_max = evt.num
                break
        sb.lcd_write(f"range: {num_min}-{num_max}".ljust(COLS), row=0)
        add = sb.menu_choose([f"key shift: {k:+3d}" for k in range(-36, 37)],
                             row=1, i=int(rule.num.add) + 36, timeout=0, wrap=False
                            )[0]
        if add == -1:
            continue
        sb.lcd_write("target:".ljust(COLS), row=0)
        tochan = sb.menu_choose(presets, row=1, align='left', timeout=0,
                                i=rule.chan.tomin - 1)[0] + 1
        if tochan == 0:
            continue
        newrule = rule.copy(chan=f"{chan}={tochan}",
                            num=f"{num_min}-{num_max}*1+{add - 36}")
        if rule == "Add Layer":
            fp.bank.patch[pname].setdefault('rules', []).append(newrule)
        else:
            fp.bank.patch[pname]['rules'][i] = newrule
        fp.apply_patch(pname)


def midi_connect():
    """Make MIDI connections as enumerated in config"""
    devs = {client: port for port, client in re.findall(" (\d+): '([^\n]*)'", sb.shell_cmd("aconnect -io"))}
    for link in fp.cfg.get('midiconnections', []):
        mfrom, mto = list(link.items())[0]
        for client in devs:
            if re.search(mfrom.split(':')[0], client):
                mfrom = re.sub(mfrom.split(':')[0], devs[client], mfrom, count=1)
            if re.search(mto.split(':')[0], client):
                mto = re.sub(mto.split(':')[0], devs[client], mto, count=1)
        try: sb.shell_cmd(f"aconnect {mfrom} {mto}")
        except subprocess.CalledProcessError: pass 


def load_bank(bank):
    sb.lcd_write(bank.name.ljust(COLS), ROWS - 2)
    sb.lcd_write("loading bank ".ljust(COLS), ROWS - 1)
    sb.progresswheel_start()
    try:
        fp.load_bank(bank)
    except Exception as e:
        sb.progresswheel_stop()
        sb.display_error(e, "bank load error: ")
        return False
    sb.progresswheel_stop()
    return True


def midievent_listen(event):
    global lastevent
    if isinstance(event, FluidMidiEvent) and event.type in VOICE_TYPES:
        lastevent = event
        if showstatus:
            if showevent:
                typ = VOICE_TYPES[event.type]
                if hasattr(event, 'num'):
                    sb.lcd_blink(f"{event.chan:03}:{typ}{event.num}={event.val}".ljust(COLS),
                                 row=1, delay=squishbox.MENU_TIMEOUT, override=True)
                else:
                    sb.lcd_blink(f"{event.chan:03}:{typ}={event.val}".ljust(COLS),
                                 row=1, delay=squishbox.MENU_TIMEOUT, override=True)
            else:
                sb.lcd_blink(sb.NOTEICON, row=1, col=1)


def get_midievent(idle=squishbox.POLL_TIME, timeout=0):
    global lastevent
    oldevent = lastevent
    t0 = time.time()
    while lastevent == oldevent:
        if timeout and time.time() - t0 > timeout:
            return None
        if action := sb.get_action(timeout=idle):
            return action
    return lastevent


def toggle_showevent():
    global showevent
    if showevent:
        showevent = False
        sb.lcd_blink("show events OFF".ljust(COLS), row=1,
                     delay=squishbox.MENU_TIMEOUT, override=True)
    else:
        showevent = True
        sb.lcd_blink("show events ON".ljust(COLS), row=1,
                     delay=squishbox.MENU_TIMEOUT, override=True)


def change_patch(i):
    sb.lcd_write(f"patch {i + 1}/{len(fp.bank)}".rjust(COLS), ROWS - 1)
    if sb.wifienabled:
        sb.lcd_write(sb.WIFION, row=1, col=0)
    else:
        sb.lcd_write(sb.WIFIOFF, row=1, col=0)
    fp.apply_patch(fp.bank.patches[i])


# main
sb = squishbox.squishbox_hardware
sb.knob1.bind('left', sb.action_dec)
sb.knob1.bind('right', sb.action_inc)
sb.button1.bind('tap', sb.action_do)
sb.lcd_clear()

cfgfile = [*sys.argv, ''][1] or 'fluidpatcherconf.yaml'
for path in (Path(cfgfile).parent,
             Path('./config'),
             Path.home() / '.config'):
    if (path / cfgfile).exists():
        try:
            fp = FluidPatcher(Path(path, cfgfile))
        except Exception as e:
            sb.display_error(e, f"Error loading {cfgfile}) ")
        break
else:
    sb.lcd_write(f"{cfgfile} not found".ljust(COLS), row=0)

showstatus = False
showevent = False
lastevent = None
fp.set_callback(midievent_listen)

load_bank(fp.cfg.bankfile)

pno = 0
last = 0
while True:
    change_patch(pno)
    sb.button1.bind('hold', toggle_showevent)
    showstatus=True
    pno, pname = sb.menu_choose(fp.bank.patches, row=0, align='left',
                                    i=pno, timeout=0, func=change_patch)
    showstatus=False
    sb.button1.bind('hold', sb.action_back)
    sb.lcd_write(pname, row=0)
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
        lastbank = fp.cfg.bankfile
        f = sb.menu_choosefile(topdir=fp.cfg.bankpath,
                               startfile=fp.cfg.bankpath / fp.cfg.bankfile,
                               ext='.yaml')
        if f and load_bank(f):
            fp.cfg.bankfile = f
            if fp.cfg.bankfile == lastbank and pname in fp.bank.patches:
                pno = fp.bank.index(pname)
            else:
                pno = 0
    elif choice == "Save Bank":
        f = sb.menu_choosefile(topdir=fp.cfg.bankpath,
                               startfile=fp.cfg.bankpath / fp.cfg.bankfile,
                               ext='.yaml')
        if f == "":
            continue
        sb.lcd_write("Save as:".ljust(COLS), row=0)
        name = sb.menu_entertext(f.name)
        if not sb.menu_confirm(name):
            continue
        sb.lcd_write(name.ljust(COLS), row=0)
        try:
            fp.save_bank((f.parent / name).with_suffix('.yaml'))
        except Exception as e:
            sb.display_error(e, "bank save error: ")
        else:
            fp.cfg.bankfile = f.parent / name
            sb.lcd_write("bank saved".ljust(COLS), row=1)
            sb.get_action(timeout=2)
    elif choice == "Save Patch":
        sb.lcd_write("Save patch as:".ljust(COLS), row=0)
        newname = sb.menu_entertext(pname)
        if sb.menu_confirm(newname):
            if newname != pname:
                fp.bank[newname] = fp.bank[pname].copy()
            fp.update_patch(newname)
    elif choice == "Delete Patch":
        sb.lcd_write("Delete patch:".ljust(COLS), row=0)
        if sb.menu_confirm(pname):
            del fp.bank[pname]
            pno = min(pno, len(fp.bank))
    elif choice == "Sounds..":
        edit_sounds()
    elif choice == "Layers..":
        edit_layers()
    elif choice == "Effects..":
        effects_menu()
    elif choice == "System Menu..":
        if sb.menu_systemsettings() == "shell":
            break

