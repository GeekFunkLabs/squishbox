#!/usr/bin/env python3
"""A SquishBox wrapper for amsynth"""

from math import log
import os
from pathlib import Path
from subprocess import Popen, PIPE
import sys
from threading import Thread

import alsa_midi

import squishbox
from squishbox.config import load_config, save_state
from squishbox.midi import midi_ports, midi_connect


COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]

AMSPORT = "amsynth:0(MIDI IN)"
PARS = {}
# name              cc    type   default  pmin   pmax   base  offset
for name, cc, typ, default, *s in [r.split() for r in """\
amp_attack          12     pow       0       0    2.5      3  0.0005
amp_decay           13     pow       0       0    2.5      3  0.0005
amp_sustain         14     lin       1       0      1      1       0
amp_release         15     pow       0       0    2.5      3  0.0005
osc1_waveform       16     stp       2       0      4      1       0
filter_attack       17     pow       0       0    2.5      3  0.0005
filter_decay        18     pow       0       0    2.5      3  0.0005
filter_sustain      19     lin       1       0      1      1       0
filter_release      20     pow       0       0    2.5      3  0.0005
filter_resonance    21     lin       0       0   0.97      1       0
filter_env_amount   22     lin       0     -16     16      1       0
filter_cutoff       23     exp     1.5    -0.5    1.5     16       0
osc2_detune         24     exp       0      -1      1   1.25       0
osc2_waveform       25     stp       2       0      4      1       0
master_vol          26     pow    0.67       0      1      2       0
lfo_freq            27     pow       0       0    7.5      2       0
lfo_waveform        28     stp       0       0      6      1       0
osc2_range          29     stp       0      -3      4      2       0
osc_mix             30     lin       0      -1      1      1       0
freq_mod_amount     44     pow       0       0   1.26      3      -1
filter_mod_amount   45     lin      -1      -1      1      1       0
amp_mod_amount      46     lin      -1      -1      1      1       0
osc_mix_mode        47     lin       0       0      1      1       0
osc1_pulsewidth     48     lin       1       0      1      1       0
osc2_pulsewidth     49     lin       1       0      1      1       0
reverb_roomsize     50     lin       0       0      1      1       0
reverb_damp         51     lin       0       0      1      1       0
reverb_wet          52     lin       0       0      1      1       0
reverb_width        53     lin       1       0      1      1       0
distortion_crunch   54     lin       0       0    0.9      1       0
osc2_sync           55     stp       0       0      1      1       0
portamento_time     56     lin       0       0      1      1       0
keyboard_mode       57     stp       0       0      2      1       0
osc2_pitch          58     stp       0     -12     12      1       0
filter_type         59     stp       0       0      4      1       0
filter_slope        60     stp       1       0      1      1       0
freq_mod_osc        61     stp       0       0      2      1       0
filter_kbd_track    62     lin       1       0      1      1       0
filter_vel_sens     63     lin       1       0      1      1       0
amp_vel_sens        84     lin       1       0      1      1       0
portamento_mode     85     stp       0       0      1      1       0
""".splitlines()]:
    PARS[name] = {
        "cc": int(cc), "default": float(default), "vals": [], "display": []
    }
    pmin, pmax, base, offset = map(float, s)
    for i in range(128):
        val = pmin + (pmax - pmin) * i / 127
        if typ == "stp":
            val = round(val)
            PARS[name]["display"].append(val)
        elif typ == "lin":
            PARS[name]["display"].append(base * val + offset)
        elif typ == "exp":
            PARS[name]["display"].append(base ** val + offset)
        elif typ == "pow":
            PARS[name]["display"].append(val ** base + offset)
        PARS[name]["vals"].append(val)        
# make displayed values pretty
for name in """\
osc_mix_mode
osc1_pulsewidth
osc2_pulsewidth
amp_sustain
filter_resonance
filter_cutoff
filter_sustain
freq_mod_amount
filter_mod_amount
amp_mod_amount
reverb_roomsize
reverb_damp
reverb_wet
reverb_width
distortion_crunch
filter_kbd_track
filter_vel_sens
amp_vel_sens""".split():
    PARS[name]["display"] = [
        f"{i / 1.27:.0f}%" for i in range(128)
    ]
for name, *display in [r.split() for r in """\
osc1_waveform     sine square triangle noise noise+SH
osc2_waveform     sine square triangle noise noise+SH
lfo_waveform      sine square triangle noise noise+SH saw+ saw-
osc2_sync         off on
keyboard_mode     poly mono legato
filter_type       lowpass highpass bandpass notch bypass
filter_slope      12dB/oct 24dB/oct
freq_mod_osc      osc1+2 osc1 osc2
portamento_mode   always legato
""".splitlines()]:
    PARS[name]["display"] = [
        display[round((len(display) - 1) * i / 127)]
        for i in range(128)
    ]
for name in """\
amp_attack
amp_decay
amp_release
filter_attack
filter_decay
filter_release
portamento_time""".split():
    PARS[name]["display"] = [
        f"{v * 1000:.0f} ms" if v < 1.0 else f"{v:.1f} s"
        for v in PARS[name]["display"]
    ]
PARS["lfo_freq"]["display"] = [
    f"{v:.1f} Hz" for v in PARS["lfo_freq"]["display"]
]
PARS["osc2_detune"]["display"] = [
    f"{1200 * log(v, 2):.1f} cents"
    for v in PARS["osc2_detune"]["display"]
]
PARS["osc2_pitch"]["display"] = [
    f"{v:+} semitones" for v in PARS["osc2_pitch"]["display"]
]
PARS["osc2_range"]["display"] = [
    f"{v:+} octaves" for v in PARS["osc2_range"]["display"]
]
PARS["master_vol"]["display"] = [
    f"{20 * log(v, 10):+.1f} dB" if v else "-inf dB"
    for v in PARS["master_vol"]["display"]
]
PARS["filter_env_amount"]["display"] = [
    f"{v / 16 * 100:.0f}%"
    for v in PARS["filter_env_amount"]["display"]
]
PARS["osc_mix"]["display"] = [
    f"1:{(127 - i) / 1.27:3.0f}%  2:{i / 1.27:3.0f}%"
    for i in range(128)
]


def read_bankfile(path):
    presets = {}
    for line in path.read_text().splitlines():
        if line.startswith("<preset> <name>"):
            presetname = line.split(maxsplit=2)[-1]
            presets[presetname] = {
                name: min(
                    range(128),
                    key=lambda i: abs(
                        PARS[name]["vals"][i] - PARS[name]["default"]
                    )
                ) for name in PARS
            }
        elif line.startswith("<parameter>"):
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
    lines.append("EOF")
    path.write_text("\n".join(lines))


def setup_amsynth():
    """Shadow config to amsynth configs
    """
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
    amsctrl = Path("~/.config/amsynth/controllers").expanduser()
    controllers = ["null"] * 128
    for name in PARS:
        controllers[PARS[name]["cc"]] = name
    amsctrl.write_text("\n".join(controllers))


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
                    display_callback((name, evt.value))
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
    wrapper.event_output(evt, dest=amsynth_port)
    wrapper.drain_output()


def set_preset(presetname):
    for name, i in presets[presetname].items():
        curvals[name] = i
        send_param(name, i)


def refresh_display():
    sb.lcd.write(pname.ljust(COLS), row=0)
    sb.lcd.write(f"patch {pno + 1}/{len(presets)}".rjust(COLS), row=1)


# start squishbox
sb = squishbox.SquishBox()
sb.lcd.clear()

CONFIG = load_config("amsynthbox.yaml")
if not CONFIG["banks_path"].exists():
    CONFIG["banks_path"].mkdir(parents=True, exist_ok=True)
    Path(CONFIG["banks_path"] / "presets").symlink_to(
        "/usr/share/amsynth/banks"
    )
    Path("/usr/share/amsynth/banks/amsynth_factory.bank").copy(
        CONFIG["banks_path"] / "amsynth_factory.bank"
    )

# start amsynth
setup_amsynth()
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
    CONFIG["banks_path"] / CONFIG["currentbank_path"]
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
                amsynthx.terminate()
                break
        case name, val:
            sb.lcd.write(
                name[:COLS].ljust(COLS),
                row=0, timeout=MENU_TIME
            )
            sb.lcd.write(
                PARS[name]["display"][val].rjust(COLS),
                row=1, timeout=MENU_TIME
            )
        case "select":
            display_callback = None
            i, choice = sb.menu_choose([
                "Parameters",
                "MIDI Learn..",
                "Save Preset",
                "Delete Preset",
                "Load Bank",
                "Save Bank",
                "System Menu..",
            ], row=1, i=last)
            last = i if choice != None else last
            if choice == "Parameters":
                while True:
                    i, par = sb.menu_choose(
                        [PARS[name]["display"][curvals[name]] for name in PARS],
                        row=1, i=lastpar, timeout=0,
                        func = lambda i: sb.lcd.write(
                            list(PARS)[i].ljust(COLS), row=0
                        )
                    )
                    if par == None:
                        break
                    lastpar = i
                    name = list(PARS)[i]
                    sb.lcd.write(f"{name[-15:]}:".ljust(COLS), row=0)
                    opts = list(dict.fromkeys(PARS[name]["display"]))
                    res = sb.menu_choose(
                        opts, row=1, wrap=False, timeout=0,
                        i=opts.index(PARS[name]["display"][curvals[name]]),
                        func=lambda i: send_param(
                            name, PARS[name]["display"].index(opts[i])
                        )
                    )
                    if res[1] == None:
                        break
            elif choice == "MIDI Learn..":
                ctrls = {v: k for k, v in CONFIG.get("controllers", {}).items()}
                ccs = [str(ctrls.get(par, "not mapped")) for par in PARS]
                i, par = sb.menu_choose(
                    list(PARS), row=0, i=lastpar, align="left",
                    func=lambda i: sb.lcd.write(
                        ccs[i].rjust(COLS), row=1
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
                        save_state(CONFIG_PATH, CONFIG)
                    midi_learn_callback = None
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
            elif choice == "Load Bank":
                f = sb.menu_choosefile(
                    topdir=CONFIG["banks_path"],
                    start=CONFIG["currentbank_path"],
                )
                if f.is_file():
                    try:
                        presets = read_bankfile(f)
                    except Exception as e:
                        sb.display_error(e, "bank load error")
                    else:
                        CONFIG["currentbank_path"] = f
                        save_state(CONFIG_PATH, CONFIG)
                        pno = 0
                        set_preset(pname := list(presets)[pno])
            elif choice == "Save Bank":
                f = sb.menu_choosefile(
                    topdir=CONFIG["banks_path"],
                    start=CONFIG["currentbank_path"]
                )
                name = sb.menu_entertext(
                    f.name if f.is_file() else "", charset=sb.lcd.fnchars()
                ).strip()
                if name and sb.menu_confirm(name):
                    sb.lcd.write(name.ljust(COLS), row=0)
                    try:
                        write_bankfile(f.parent / name, presets)
                    except Exception as e:
                        sb.display_error(e, "bank save error")
                    else:
                        CONFIG["currentbank_path"] = f.parent / name
                        save_state(CONFIG_PATH, CONFIG)
                        sb.lcd.write("bank saved".ljust(COLS), row=1)
                        sb.get_action(timeout=MENU_TIME)
            elif choice == "System Menu..":
                remove_wrapper(wrapper)
                midithread.join()
                if sb.menu_systemsettings() == "shell":
                    amsynthx.terminate()
                    break
                wrapper, wrapper_in, wrapper_out = start_wrapper()
                midithread = Thread(target=process_events, daemon=True)
                midithread.start()
            display_callback = sb.add_action
            refresh_display()

