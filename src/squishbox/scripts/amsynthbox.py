#!/usr/bin/env python3
"""A SquishBox wrapper for amsynth"""

import os
from pathlib import Path
from subprocess import Popen, PIPE
import sys
from threading import Thread

import alsa_midi
import yaml

import squishbox
from squishbox.midi import midi_ports, midi_connect


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]

AMSPORT = "amsynth:0(MIDI IN)"
PARS = {}
# name                   cc    type   default  pmin        pmax     step   base  offset    unit 
for name, cc, typ, default, *s, unit in [r.split() for r in """\
amp_attack               12     pow       0       0         2.5       0       3  0.0005       s
amp_decay                13     pow       0       0         2.5       0       3  0.0005       s
amp_sustain              14     lin       1       0           1       0       1       0       -
amp_release              15     pow       0       0         2.5       0       3  0.0005       s
osc1_waveform            16     lin       2       0           4       1       1       0       -
filter_attack            17     pow       0       0         2.5       0       3  0.0005       s
filter_decay             18     pow       0       0         2.5       0       3  0.0005       s
filter_sustain           19     lin       1       0           1       0       1       0       -
filter_release           20     pow       0       0         2.5       0       3  0.0005       s
filter_resonance         21     lin       0       0        0.97       0       1       0       -
filter_env_amount        22     lin       0     -16          16       0       1       0       -
filter_cutoff            23     exp     1.5    -0.5         1.5       0      16       0       -
osc2_detune              24     exp       0      -1           1       0    1.25       0       -
osc2_waveform            25     lin       2       0           4       1       1       0       -
master_vol               26     pow    0.67       0           1       0       2       0       -
lfo_freq                 27     pow       0       0         7.5       0       2       0      Hz
lfo_waveform             28     lin       0       0           6       1       1       0       -
osc2_range               29     exp       0      -3           4       1       2       0       -
osc_mix                  30     lin       0      -1           1       0       1       0       -
freq_mod_amount          44     pow       0       0  1.25992105       0       3      -1       -
filter_mod_amount        45     lin      -1      -1           1       0       1       0       -
amp_mod_amount           46     lin      -1      -1           1       0       1       0       -
osc_mix_mode             47     lin       0       0           1       0       1       0       -
osc1_pulsewidth          48     lin       1       0           1       0       1       0       -
osc2_pulsewidth          49     lin       1       0           1       0       1       0       -
reverb_roomsize          50     lin       0       0           1       0       1       0       -
reverb_damp              51     lin       0       0           1       0       1       0       -
reverb_wet               52     lin       0       0           1       0       1       0       -
reverb_width             53     lin       1       0           1       0       1       0       -
distortion_crunch        54     lin       0       0         0.9       0       1       0       -
osc2_sync                55     lin       0       0           1       1       1       0       -
portamento_time          56     lin       0       0           1       0       1       0       -
keyboard_mode            57     lin       0       0           2       1       1       0       -
osc2_pitch               58     lin       0     -12          12       1       1       0       -
filter_type              59     lin       0       0           4       1       1       0       -
filter_slope             60     lin       1       0           1       1       1       0       -
freq_mod_osc             61     lin       0       0           2       1       1       0       -
filter_kbd_track         62     lin       1       0           1       0       1       0       -
filter_vel_sens          63     lin       1       0           1       0       1       0       -
amp_vel_sens             84     lin       1       0           1       0       1       0       -
portamento_mode          85     lin       0       0           1       1       1       0       -
""".splitlines()]:
    PARS[name] = {"cc": int(cc), "default": float(default), "unit": unit, "vals": []}
    pmin, pmax, step, base, offset = map(float, s)
    for x in [i/127 for i in range(128)]:
        match typ:
            case "lin":
                val = offset + base * x
            case "exp":
                val = offset + base ** x
            case "pow":
                val = offset + x ** base
        val = min(max(val, pmin), pmax)
        if step:
            val = pmin + round((val - pmin) / step) * step
        PARS[name]["vals"].append(val)

print("\n".join((str(v) for v in PARS["amp_sustain"]["vals"])))
sys.exit()

def read_bankfile(path):
    presets = {}
    for line in path.read_text().splitlines():
        if line.startswith("<preset> <name>"):
            presetname = line.split(maxsplit=2)[-1]
            presets[presetname] = {
                name: PARS[name]["default"] for name in PARS
            }
        if not presets:
            continue
        if line.startswith("<parameter>"):
            name, val = line.split()[1:3]
            presets[presetname][name] = min(
                range(128),
                key=lambda i: abs(PARS[name]["vals"][i] - float(val))
            )
    return presets


def write_bankfile(path, presets):
    lines = ["amSynth"]
    for presetname, preset in presets.items():
        lines.append(f"<preset> <name> {presetname}")
        for name, val in preset.items():
            lines.append(
                f"<parameter> {name} {PARS[name]['vals'][val]}"
            )
    lines.append(["EOF"])
    path.write_text("\n".join(lines))


def start_wrapper():
    """Create a client for observing/routing MIDI messages
    and insert it between amSynth and anything connected to it
    """
    conns = squishbox.CONFIG.setdefault("midi_connections", [])
    for i, (src, dest) in enumerate((c.split(">") for c in conns)):
        if dest == AMSPORT:
            conns[i] = f"{src}>_amsynth_wrapper:0(in)"
    conns.append(f"_amsynth_wrapper:1(out)>{AMSPORT}")
    client = alsa_midi.SequencerClient("_amsynth_wrapper")
    inport = client.create_port(
        "in",
        caps=alsa_midi.WRITE_PORT,
        type=alsa_midi.PortType.MIDI_GENERIC,
    )
    outport = client.create_port(
        "out",
        caps=alsa_midi.READ_PORT,
        type=alsa_midi.PortType.MIDI_GENERIC,
    )
#    midi_connect()
    return client, inport, outport


def remove_wrapper(client):
    client.close()
    conns = squishbox.CONFIG["midi_connections"]
    for i, (src, dest) in enumerate((c.split(">") for c in conns)):
        if dest == "_amsynth_wrapper:0(in)":
            conns[i] = f"{src}>{AMSPORT}"
    conns.remove(f"_amsynth_wrapper:1(out)>{AMSPORT}")
    if squishbox.CONFIG.get("midi_connections") == []:
        del squishbox.CONFIG["midi_connections"]
    midi_connect()


def process_events():
    while True:
        try:
            evt = wrapper.event_input(timeout=0.1)
        except TypeError: # occurs if client is closed
            break
        if evt == None:
            continue
        if midi_learn_callback != None:
            if (
                isinstance(evt, alsa_midi.ControlChangeEvent) and
                CONFIG["midi_channel"] in (evt.channel + 1, 0)
            ):
                midi_learn_callback(evt.param)
        elif (
            isinstance(evt, alsa_midi.ControlChangeEvent) and
            CONFIG["midi_channel"] in (evt.channel + 1, 0)
        ):
            if evt.param in CONFIG.get("controllers", {}):
                name = CONFIG["controllers"][evt.param]
                send_param(name, evt.value)
                if display_callback != None:
                    display_callback((name, PARS[name]["vals"][evt.value]))
        else:
            wrapper.event_output(evt, dest=amsynth_port)
            wrapper.drain_output()


def send_param(name, i):
    curvals[name] = i
    evt = alsa_midi.ControlChangeEvent(
        channel=(CONFIG["midi_channel"] or 1) - 1,
        param=PARS[name]["cc"],
        value=i,
    )
    print(evt, name, PARS[name]["vals"][i])
    wrapper.event_output(evt, dest=amsynth_port)
    wrapper.drain_output()


def set_preset(presetname):
    print("sending", presetname)
    for name, i in presets[presetname].items():
        curvals[name] = i
        send_param(name, i)


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
midi_channel: 1
sample_rate: 44100
polyphony: 16
pitch_bend_range: 2
audio_driver: alsa
alsa_audio_device: hw:sndrpihifiberry
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
CONFIG["banks_path"] = Path(CONFIG["banks_path"]).expanduser()
CONFIG["current_bank"] = Path(CONFIG["current_bank"]).expanduser()

# write amsynth config
amscfg = Path("~/.config/amsynth/config").expanduser()
amscfg.write_text(
    "\n".join(
        [f"{k} {v}" for k, v in CONFIG.items() if k in (
                "midi_channel",
                "sample_rate",
                "polyphony",
                "pitch_bend_range",
                "audio_driver",
                "alsa_audio_device",
            )
        ]
    )
)

# write controller config
amsctrl = Path("~/.config/amsynth/controllers").expanduser()
controllers = ["null"] * 128
for name in PARS:
    controllers[PARS[name]["cc"]] = name
amsctrl.write_text("\n".join(controllers))

# link default banks to user banks location
CONFIG["banks_path"].mkdir(parents=True, exist_ok=True)
for path in (
    Path("~/.local/share/amsynth/banks").expanduser(),
    Path("/usr/share/amsynth/banks"),
):
    for bank in [f for f in path.iterdir() if f.is_file()]:
        if not (CONFIG["banks_path"] / bank.name).exists():
            (CONFIG["banks_path"] / bank.name).symlink_to(bank)

# start amsynth
try:
    amsynthx = Popen(
        ["stdbuf", "-oL", "amsynth", "-x"],
        stdout=PIPE, stderr=PIPE,
        text=True, bufsize=1
    )
except FileNotFoundError as e:
    sb.display_error(e, "install with 'apt install amsynth'")
    sys.exit()
for line in amsynthx.stdout:
    if "headless mode" in line:
        break
amsynth_port = midi_ports()[AMSPORT]
wrapper, wrapper_in, wrapper_out = start_wrapper()
midithread = Thread(target=process_events, daemon=True)
display_callback = sb.add_action
midi_learn_callback = None
midithread.start()

presets = read_bankfile(
    CONFIG["banks_path"] / CONFIG["current_bank"]
)
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
                            (f"{PARS[name]['vals'][curvals[name]]:g}" +
                             (f" {unit}" if unit != "-" else ""))
                            for name, unit in [
                                (name, PARS[name]["unit"]) for name in PARS
                            ]
                        ],
                        row=1, i=lastpar,
                        func = lambda i: sb.lcd.write(
                            list(PARS)[i].ljust(COLS), row=0
                        )
                    )
                    if par == None:
                        break
                    lastpar = i
                    name = list(PARS)[i]
                    sb.lcd.write(name.ljust(COLS), row=0)
                    res = sb.menu_choose(
                        PARS[name]["vals"], row=1,
                        i=curvals[name],
                        func=lambda i: send_param(name, i)
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
                i, par = sb.menu_choose(
                    ccs, row=1, i=lastpar,
                    func=lambda i: sb.lcd.write(
                        list(PARS)[i].ljust(COLS), row=0
                    )
                )
                if par != None:
                    lastpar=i
                    midi_learn_callback = sb.add_action
                    i, cc = sb.menu_choose(range(128), row=1, i=ctrls.get(par, 0))
                    CONFIG.setdefault("controllers", {})
                    if isinstance(cc, int):
                        CONFIG["controllers"][cc] = par
                    elif i > -1:
                        CONFIG["controllers"].pop(cc, None)
                        if CONFIG["controllers"] == {}:
                            del CONFIG["controllers"]
                    midi_learn_callback = None
            elif choice == "System Menu..":
                remove_wrapper(wrapper)
                midithread.join()
                if sb.menu_systemsettings() == "shell":
                    break
                wrapper, wrapper_in, wrapper_out = start_wrapper()
                midithread = Thread(target=process_events, daemon=True)
                midithread.start()
            display_callback = sb.add_action
            refresh_display()

