#!/usr/bin/env python3
"""A SquishBox wrapper for amsynth"""

import os
from pathlib import Path

import alsa_midi
import yaml

import squishbox
from squishbox.midi import midi_ports


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]

PARS = {}
# name                   cc    type   default  pmin        pmax     step   base  offset    unit 
for name, cc, typ, new, *s, unit in [r.split for r in """\
amp_attack                1     pow       0       0         2.5       0       3  0.0005       s
amp_decay                 1     pow       0       0         2.5       0       3  0.0005       s
amp_sustain               1     lin       1       0           1       0       1       0       -
amp_release               1     pow       0       0         2.5       0       3  0.0005       s
osc1_waveform             1     lin       2       0           4       1       1       0       -
filter_attack             1     pow       0       0         2.5       0       3  0.0005       s
filter_decay              1     pow       0       0         2.5       0       3  0.0005       s
filter_sustain            1     lin       1       0           1       0       1       0       -
filter_release            1     pow       0       0         2.5       0       3  0.0005       s
filter_resonance          1     lin       0       0        0.97       0       1       0       -
filter_env_amount         1     lin       0     -16          16       0       1       0       -
filter_cutoff             1     exp     1.5    -0.5         1.5       0      16       0       -
osc2_detune               1     exp       0      -1           1       0    1.25       0       -
osc2_waveform             1     lin       2       0           4       1       1       0       -
master_vol                1     pow    0.67       0           1       0       2       0       -
lfo_freq                  1     pow       0       0         7.5       0       2       0      Hz
lfo_waveform              1     lin       0       0           6       1       1       0       -
osc2_range                1     exp       0      -3           4       1       2       0       -
osc_mix                   1     lin       0      -1           1       0       1       0       -
freq_mod_amount           1     pow       0       0  1.25992105       0       3      -1       -
filter_mod_amount         1     lin      -1      -1           1       0       1       0       -
amp_mod_amount            1     lin      -1      -1           1       0       1       0       -
osc_mix_mode              1     lin       0       0           1       0       1       0       -
osc1_pulsewidth           1     lin       1       0           1       0       1       0       -
osc2_pulsewidth           1     lin       1       0           1       0       1       0       -
reverb_roomsize           1     lin       0       0           1       0       1       0       -
reverb_damp               1     lin       0       0           1       0       1       0       -
reverb_wet                1     lin       0       0           1       0       1       0       -
reverb_width              1     lin       1       0           1       0       1       0       -
distortion_crunch         1     lin       0       0         0.9       0       1       0       -
osc2_sync                 1     lin       0       0           1       1       1       0       -
portamento_time           1     lin       0       0           1       0       1       0       -
keyboard_mode             1     lin       0       0           2       1       1       0       -
osc2_pitch                1     lin       0     -12          12       1       1       0       -
filter_type               1     lin       0       0           4       1       1       0       -
filter_slope              1     lin       1       0           1       1       1       0       -
freq_mod_osc              1     lin       0       0           2       1       1       0       -
filter_kbd_track          1     lin       1       0           1       0       1       0       -
filter_vel_sens           1     lin       1       0           1       0       1       0       -
amp_vel_sens              1     lin       1       0           1       0       1       0       -
portamento_mode           1     lin       0       0           1       1       1       0       -
""".splitlines()]:
    PARS[name] = {"cc": int(cc), "new": float(new), "unit": unit, "vals": []}
    pmin, pmax, step, base, offset = map(float, s)
    for i in range(128):
        switch typ:
            case "lin":
                val = offset + base * i
            case "exp":
                val = offset + base ** i
            case "pow":
                val = offset + i ** base
        val = min(max(val, pmin), pmax)
        if step:
            val = pmin + round((val - pmin) / step) * step
        PARS[name]["vals"].append(val)


def read_bankfile(path):
    presets = {}
    for p in path.read_text().split("<preset> <name> "):
        presetname, *rows = p.splitlines()
        presets[presetname] = {
            name: min(
                range(128),
                key=lambda i: abs(PARS[name]["vals"][i] - val)
            )
            for name, val in [(s[1], float(s[2]))
                for s in [r.split() for r in rows]
            ]
        }
    return presets


def write_bankfile(path, presets):
    text = ["amSynth"]
    for presetname, preset in presets.items():
        text.append(f"<preset> <name> {presetname}")
        for name, val in preset.items():
            text.append(
                f"<parameter> {name} {PARS[name]['vals'][val]}"
            )
    path.write_text("\n".join(text))


def start_wrapper():
    """Create a client for observing/routing MIDI messages
    and insert it between amSynth and anything connected to it
    """
    wclient = alsa_midi.SequencerClient("amSynthBox")
    inport = wclient.create_port("amSynthBox MIDI in")
    outport = wclient.create_port("amSynth wrapper")
    amsport = midi_ports()["amsynth:0(MIDI IN)"]
    for info in amsport.list_subscribers(
        alsa_midi.SubscriptionQueryType.READ
    ):
        amsport.disconnect_from(info.addr)
        inport.connect_from(info.addr)
    outport.connect_to(amsport)
    return wclient


def process_events():
    while listening:
        evt = wrapper.event_input()
        if midi_learn_callback != None:
            if (
                isinstance(evt, alsa_midi.ControlChangeEvent) and
                evt.chan == CONFIG["midi_channel"]
            ):
                midi_learn_callback(evt.param)
        elif (
            isinstance(evt, alsa_midi.ControlChangeEvent) and
            evt.chan == CONFIG["midi_channel"] and
            evt.param in CONFIG.get("controllers", {})
        ):
            name = CONFIG["controllers"][evt.param]
            send_param(name, evt.value)
            if display_callback != None:
                display_callback((name, PARS[name]["vals"][evt.value]))
        else:
            wrapper.event_output(evt, amsport)
            wrapper.drain_output()


def send_param(name, val):
    curvals[name] = val
    evt = alsa_midi.ControlChangeEvent(
        chan = CONFIG["midi_channel"],
        param = PARS[name]["cc"],
        value = val
    )
    wrapper.event_output(evt, amsport)
    wrapper.drain_output()


def set_preset(presetname):
    for name, val in presets[presetname].items():
        curvals[name] = val
        send_midi("cc", chan, PARS[name]["cc"], val)


def save_state(cfg):
    cfg_posix = {k: v.as_posix() if isinstance(v, Path) else v
                 for k, v in cfg.items()}
    CONFIG_PATH.write_text(yaml.safe_dump(cfg_posix, sort_keys=False))


def refresh_display():
    sb.lcd.write(pname.ljust(COLS), row=0)
    sb.lcd.write(f"patch {pno + 1}/{len(presets)}".rjust(COLS), row=1)


# start squishbox
sb = squishbox.SquishBox()
sb.knob1.bind("left", sb.action_dec)
sb.knob1.bind("right", sb.action_inc)
sb.button1.bind("tap", sb.action_do)
sb.button1.bind("hold", sb.action_back)
sb.lcd.clear()

DEFAULT_CONFIG = yaml.safe_load("""\
midi_channel: 15
sample_rate: 44100
polyphony: 16
pitch_bend_range: 2
banks_path: ~/.local/share/amsynth/banks
current_bank: default
""")

CONFIG_PATH = Path(os.getenv(
    "AMSYNTHBOX_CONFIG",
    "~/.config/amsynth/amsynthboxconf.yaml"
)).expanduser()
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

# read config, create if it doesn't exist
if CONFIG_PATH.exists():
    CONFIG = yaml.safe_load(CONFIG_PATH.read_text())
else:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(DEFAULT_CONFIG))
    CONFIG = {}
CONFIG = DEFAULT_CONFIG | CONFIG
CONFIG["banks_path"] = Path(CONFIG["banks_path"])
CONFIG["current_bank"] = Path(CONFIG["current_bank"])

# write amsynth config
amscfg = Path("~/.config/amsynth/config").expanduser()
amscfg.write_text("/n".join([f"{k} {v}"
    for k, v in CONFIG.items() if k in (
        "midi_channel",
        "sample_rate",
        "polyphony",
        "pitch_bend_range",
    )]
)

# write controller config
amsctrl = Path("~/.config/amsynth/controllers").expanduser()
controllers = ["null"] * 128
for name in PARS:
    controllers[PARS[name]["cc"]] = name
amsctrl.write_text("/n".join(controllers))

# link default banks to user banks location
CONFIG["banks_path"].mkdir(parents=True, exist_ok=True)
for bank in (
    Path("~/.local/share/amsynth/banks").expanduser().iterdir() +
    Path("/usr/share/amsynth/banks").iterdir()
):
    if not (CONFIG_PATH["banks_path"] / bank.name).exists():
        (CONFIG_PATH["banks_path"] / bank.name).symlink_to(bank)

# start amsynth
try:
    sb.shell_cmd("amsynth -x")
except Exception as e:
    sb.display_error(e, "install with 'apt install amsynth'"
amsport = midi_ports()["amsynth:0(MIDI IN)"]
wrapper = start_wrapper()
midithread = Thread(target=process_events, daemon=True)
listening = True
midi_learn_callback = None
display_callback = sb.add_action
midithread.start()

presets = read_bankfile(CONFIG["current_bank"])
curvals = {name: 0 for name in PARS}
pno = 0
set_preset(pname := list(presets)[pno])

last = 0
lastpar = 0
refresh_display()
while True:
    match sb.get_action():
        case "inc":
            pno = (pno + 1) % len(presets)
            set_preset(pname := list(presets)[pno])
            refresh_display()
        case "dec":
            pno = (pno - 1) % len(presets)
            set_preset(pname := list(presets)[pno])
            refresh_display()
        case "back":
            if sb.menu_exit() == "shell":
                break
        case name, val:
            sb.lcd.write(
                name.ljust(COLS),
                row=0, timeout=MENU_TIMEOUT
            )
            sb.lcd.write(
                (f"{val:g} {PARS[name]['unit']}"
                    if PARS[name]["unit"] != "-"
                    else f"{val:g}"
                ).rjust(COLS),
                row=1, timeout=MENU_TIMEOUT
            )
        case "do":
            display_callback = None
            i, choice = sb.menu_choose(
                [
                    "Parameters",
                    "Load Bank",
                    "Save Bank",
                    "Save Preset",
                    "Delete Preset",
                    "MIDI Learn..",
                    "System Menu..",
                ], row=1, i=last
            )
            if choice == "Parameters":
                while True:
                    i, par = sb.menu_choose(
                        [
                            (
                                f"{PARS[name]['vals'][curvals[name]]:g}" +
                                f" {unit}" if unit != "-" else ""
                            )
                            for name, unit in [(name, PARS[name]["unit"]) for name in PARS]
                        ],
                        row=1, i=lastpar,
                        func = lambda i: sb.lcd_write(
                            list(PARS)[i].ljust(COLS), row=0
                        )
                    )
                    if par == None:
                        break
                    lastpar = i
                    sb.lcd.write(par.ljust(COLS), row=0)
                    res = sb.menu_choose(
                        PARS[par]["vals"],
                        row=1, i=PARS[par]["vals"].index(curvals[par]),
                        func=lambda i: send_param(par, i)
                    )
                    if res[1] == None:
                        break
            elif choice == "Load Bank":
                f = sb.menu_choosefile(
                    topdir=CONFIG["banks_path"],
                    startfile=CONFIG["current_bank"],
                )
                if f.is_file():
                    try:
                        presets = read_bankfile(f)
                    except Exception as e:
                        sb.display_error(e, "bank load error")
                    else:
                        pno = 0
                        set_preset(pname := list(presets)[pno])
            elif choice == "Save Bank":
                f = sb.menu_choosefile(
                    topdir=CONFIG["bank_path"],
                    startfile=CONFIG["current_bank"]
                )
                name = sb.menu_entertext(
                    f.name if f.is_file() else "", charset=sb.lcd.FCHARS
                ).strip()
                if name and sb.menu_confirm(name):
                    sb.lcd.write(name.ljust(COLS), row=0)
                    try:
                        write_bankfile(f.parent / name, presets)
                    except Exception as e:
                        sb.display_error(e, "bank save error")
                    else:
                        CONFIG["current_bank"] = f.parent / name
                        save_state(CONFIG)
                        sb.lcd.write("bank saved".ljust(COLS), row=1)
                        sb.get_action(timeout=MENU_TIME)
            elif choice == "Save Preset":
                sb.lcd.write("Save preset as:".ljust(COLS), row=0)
                newname = sb.menu_entertext(pname).strip()
                if sb.menu_confirm(newname):
                    pname = newname
                    presets[pname] = curvals.copy()
                    pno = list(presets).index(pname)
            elif choice == "Delete Preset":
                sb.lcd.write("Delete preset:".ljust(COLS), row=0)
                if sb.menu_confirm(pname):
                    del presets[pname]
                    pno = min(pno, len(presets) - 1)
                    set_preset(pname := list(presets)[pno])
            elif choice == "MIDI Learn..":
                ctrls = {v: k for k, v in CONFIG.get("controllers", {}).items()}
                ccs = [ctrls.get(par, "not mapped") for par in PARS]
                i, par = sb.choose_menu(
                    ccs, row=1, i=lastpar,
                    func=lambda i: sb.write(
                        list(PARS)[i].ljust(COLS), row=0
                    )
                )
                if par != None:
                    lastpar=i
                    midi_learn_callback = sb.add_action
                    i, cc = sb.choose_menu(range(128), row=1, i=ctrls.get(par, 0))
                    CONFIG.setdefault("controllers", {})
                    if isinstance(cc, int):
                        CONFIG["controllers"][cc] = par
                    elif i > -1:
                        CONFIG["controllers"].pop(cc, None)
                        if CONFIG["controllers"] == {}:
                            del CONFIG["controllers"]
                    midi_learn_callback = None
            elif choice == "System Menu..":
                listening = False
                midithread.join()
                wrapper.close()
                if sb.menu_systemsettings() == "shell":
                    break
                wrapper = start_wrapper()
            display_callback = sb.add_action
            refresh_display()

