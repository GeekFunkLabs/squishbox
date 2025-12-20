import os
from pathlib import Path
from threading import Thread
import time

"""
sudo apt install python3-gi python3-gi-cairo gir1.2-gst-1.0
sudo apt install python3-gi gir1.2-gst-1.0 \
                 gstreamer1.0-plugins-base \
                 gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad \
                 gstreamer1.0-plugins-ugly \
                 gstreamer1.0-libav
sudo apt install gstreamer1.0-alsa
sudo apt install gstreamer1.0-tools
sudo apt install python3-gi python3-gst-1.0 gstreamer1.0-alsa
"""

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

import yaml

import squishbox
from squishbox.config import load_config, save_state


Gst.init(None)

COLS = squishbox.CONFIG["lcd_cols"]
ROWS = squishbox.CONFIG["lcd_rows"]
MENU_TIME = squishbox.CONFIG["menu_timeout"]
FRAME_TIME = squishbox.CONFIG["frame_time"]

class GStreamerPlayer:

    def __init__(self):
        self._volume = 1.0
        self._seek_waiting = None
        self._playing = False
        self._async_done = False
        self.statuscallback = lambda x: None
        self.eoscallback = lambda x: None
        lev = Gst.ElementFactory.make("level", "level")
        lev.set_property("interval", 100 * Gst.MSECOND)
        lev.set_property("post-messages", True)
        self._pb = Gst.ElementFactory.make("playbin")
        self._pb.set_property("audio-filter", lev)
        self._pb.set_property("volume", 0.0)
        bus = self._pb.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        Thread(target=GLib.MainLoop().run, daemon=True).start()

    @property
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, play):
        self._playing = play
        if play:
            self._pb.set_state(Gst.State.PLAYING)
        else:
            self._pb.set_state(Gst.State.PAUSED)

    @property
    def volume(self):
        return self._volume
    
    @volume.setter
    def volume(self, vol):
        self._pb.set_property("volume", vol)
        self._volume = vol

    def duck(self, vol):
        self._pb.set_property("volume", self._volume * vol)    

    def play(self, uri, start_seconds=0, level=1.0):        
        if self._pb.get_property("uri") != uri:
            self._pb.set_state(Gst.State.READY)
            self._pb.set_property("uri", uri)
            self.playing = True
            self._pb.set_property("volume", self._volume * level)
            self._async_done = False
        if start_seconds > 0:
            self._seek_waiting = start_seconds

    def seek(self, seconds):
        if self._async_done == False:
            self._seek_waiting = seconds
        else:
            self._pb.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                int(seconds * Gst.SECOND)
            )
            self._async_done = False

    def _on_bus_message(self, bus, msg):
        if msg.type == Gst.MessageType.ELEMENT:
            s = msg.get_structure()
            if s.get_name() == "level":
                pos_ok, pos = self._pb.query_position(Gst.Format.TIME)
                dur_ok, dur = self._pb.query_duration(Gst.Format.TIME)
                self.statuscallback((
                    s.get_value("peak"),
                    s.get_value("rms"),
                    pos // Gst.SECOND if pos_ok else 0,
                    dur // Gst.SECOND if dur_ok else 0,
                ))
        elif msg.type == Gst.MessageType.EOS:
            self.eoscallback("end-of-stream")
        elif msg.type == Gst.MessageType.ASYNC_DONE:
            self._async_done = True
            if self._seek_waiting != None:
                self.seek(self._seek_waiting)
                self._seek_waiting = None


def play_track(n):
    track.i = n
    track.path = tracks_path / tracks[track.i]["file"]
    track.name = tracks[track.i].get("name", track.path.name)
    start = tracks[track.i].get("start", 0)
    if ":" in str(start):
        m, s = start.split(":")
        start = int(m) * 60 + int(s)
    player.play(
        track.path.as_uri(),
        start_seconds=start,
        level=tracks[track.i].get("level", 1.0)
    )


def advance_track(msg):
    play_track((track.i + 1) % len(tracks))
    eoscallback(msg)


def levels_to_vu(dBpeak, dBrms):
    # modify to tweak VDU responsiveness
    levels = 5
    dB = dBpeak * 0.7 + dBrms * 0.3
    return min(levels - 1, int(levels * max(0, ((dB + 40) / 34)) ** 3))


def show_tracklist(startrow, end=0):
    irow = min(startrow, len(tracks) - ROWS + end) % len(tracks)
    crow = 0
    while True:
        for i in range(irow, min(irow + ROWS, len(tracks) + end)):
            if i >= len(tracks):
                sb.lcd.write(" " * COLS, row=i - irow)
                break
            if i == track.i:
                m = " " + sb.lcd["play"] + " :"
            else:
                m = f" {i - track.i:+}:"
            name = tracks[i].get("name", Path(tracks[i]["file"]).name)
            sb.lcd.write((m + name).ljust(COLS), row=i - irow)
            sb.lcd.write(m, row=i - irow)
        sb.lcd.write(">", row=crow, col=0, timeout=FRAME_TIME)
        match sb.get_action():
            case "inc":
                crow += 1
                if crow == ROWS or crow == len(tracks):
                    crow -= 1
                    irow = min(irow + 1, len(tracks) - ROWS + end) % len(tracks)
            case "dec":
                crow -= 1
                if crow < 0:
                    crow = 0
                    irow = max(irow - 1, 0)
            case "do":
                i = irow + crow
                if irow + crow == len(tracks):
                    name = ""
                else:
                    name = tracks[i].get(
                        "name", Path(tracks[i]["file"]).name
                    )
                return irow + crow, name
            case "back":
                return None, ""
            case "end-of-stream":
                return show_tracklist(irow, end)


# start squishbox
sb = squishbox.SquishBox()
sb.knob1.bind("left", sb.action_dec)
sb.knob1.bind("right", sb.action_inc)
sb.button1.bind("tap", sb.action_do)
sb.button1.bind("hold", sb.action_back)
sb.lcd.clear()

# add some glyphs
sb.lcd["play"] = """
-X---
-XX--
-XXX-
-XXXX
-XXX-
-XX--
-X---
-----"""
sb.lcd["pause"] = """
XX-XX
XX-XX
XX-XX
XX-XX
XX-XX
XX-XX
XX-XX
-----"""
sb.lcd["rewind"] = """
--X--
-XXX-
XXXXX
-----
--X--
-XXX-
XXXXX
-----"""
sb.lcd["ffwd"] = """
XXXXX
-XXX-
--X--
-----
XXXXX
-XXX-
--X--
-----"""
for i in range(2, 7, 2):
    sb.lcd[f"L{i}"] = "-----" * (8 - i) + "XXXXX" * i

# set up config
default_cfg = """\
tracklists_path: ~/.config/trackbox
tracks_head: ~/Music
"""
CONFIG_PATH = Path(os.getenv(
    "TRACKBOX_CONFIG",
    "~/.config/trackbox/trackboxconf.yaml"
)).expanduser()
CONFIG = load_config(CONFIG_PATH, default_cfg)
TRACKLISTS_PATH = Path(CONFIG["tracklists_path"]).expanduser()
TRACKS_HEAD = Path(CONFIG["tracks_head"]).expanduser()

# load the tracklist
if "current_tracklist" not in CONFIG:
    f = sb.menu_choosefile(topdir=TRACKS_HEAD)
    if f.is_file():
        tracklist = {
            "tracks": [{"file": str(f.relative_to(TRACKS_HEAD))}]
        }
    else:
        sys.exit()
else:
    tracklist = yaml.safe_load(Path(
        TRACKLISTS_PATH,
        CONFIG["current_tracklist"]
    ).read_text())
tracks_path = TRACKS_HEAD / tracklist.get("tracks_path", "")
tracks = tracklist["tracks"]
track = type("TrackState", (), dict(
    i=tracklist.get("start", tracklist.get("position", 0)),
))

player = GStreamerPlayer()
player.volume = CONFIG.get("master_volume", 1.0)
player.eoscallback = advance_track
play_track(track.i)
sb.lcd.write(track.name.ljust(COLS), row=0)

pos, dur = 0, 0
while True:
    sb.lcd.write(
        sb.lcd["play"] if player.playing else sb.lcd["pause"],
        row=1, col=0
    )
    player.statuscallback = sb.add_action
    eoscallback = sb.add_action
    match sb.get_action():
        case "do":
            player.playing = False if player.playing else True
        case "inc" | "dec" as d if pos >=0 and dur >= 0:
            player.statuscallback = lambda x: None
            seeks = []
            for s in range(pos):
                t = f"{s // 60:02}:{s % 60:02}/{dur // 60:02}:{dur % 60:02}"
                seeks.append(sb.lcd["rewind"] + t.rjust(COLS - 1))
            t = f"{pos // 60:02}:{pos % 60:02}/{dur // 60:02}:{dur % 60:02}"
            seeks.append(t.rjust(COLS))
            for s in range(pos + 1, dur + 1):
                t = f"{s // 60:02}:{s % 60:02}/{dur // 60:02}:{dur % 60:02}"
                seeks.append(sb.lcd["ffwd"] + t.rjust(COLS - 1))
            s, res = sb.menu_choose(
                seeks, row=1, wrap=False,
                i=min(pos + 1, dur) if d == "inc" else max(pos - 1, 0)
            )
            if res != None and s >= 0:
                player.seek(s)
                player.playing = True
            elif res == "end-of-stream":
                sb.lcd.write(track.name.ljust(COLS), row=0)
        case "end-of-stream":
            sb.lcd.write(track.name.ljust(COLS), row=0)
        case (peak, rms, pos, dur):
            vdu = [" ", sb.lcd["L2"], sb.lcd["L4"], sb.lcd["L6"], sb.lcd["solid"]]
            for c, (dBpeak, dBrms) in enumerate(zip(peak, rms)):
                sb.lcd.write(
                    vdu[levels_to_vu(dBpeak, dBrms)],
                    row=1, col=1 + c,
                )
            sb.lcd.write(
                (f"{pos // 60:02}:{pos % 60:02}/" +
                 f"{dur // 60:02}:{dur % 60:02}").rjust(COLS - 3),
                row=1, col=3
            )
        case "back":
            player.statuscallback = lambda x: None
            while True:
                i, choice = sb.menu_choose([
                    "Volume",
                    "Tracklist",
                    "Load Tracklist",
                    "Save Tracklist",
                    "System Menu..",
                ], row=ROWS - 1)
                if choice != "end-of-stream":
                    break
                sb.lcd.write(track.name.ljust(COLS), row=0)
            eoscallback = lambda x: None
            # handle menu choice
            if choice == "System Menu..":
                if sb.menu_systemsettings() == "shell":
                    break
            elif choice == "Load Tracklist":
                f = sb.menu_choosefile(
                    topdir=TRACKLISTS_PATH,
                    start=CONFIG.get("current_tracklist")
                )
                if f.is_file():
                    try:
                        tracklist = yaml.safe_load(f.read_text())
                    except Exception as e:
                        sb.display_error(e, "error opening file")
                    else:
                        CONFIG["current_tracklist"] = f.relative_to(TRACKLISTS_PATH).as_posix()
                        save_state(CONFIG_PATH, CONFIG)
                        tracks_path = TRACKS_HEAD / tracklist.get("tracks_path", "")
                        tracks = tracklist["tracks"]
                        track.i = tracklist.get("start", tracklist.get("position", 0))
                        play_track(track.i)
            elif choice == "Save Tracklist":
                f = sb.menu_choosefile(
                    topdir=TRACKLISTS_PATH,
                    start=CONFIG.get("current_tracklist"),
                    ext=".yaml",
                )
                name = sb.menu_entertext(
                    f.name if f.is_file() else "", charset=sb.lcd.fnchars()
                ).strip()
                if name and sb.menu_confirm(name):
                    sb.lcd.write(name.ljust(COLS), row=0)
                    path = ((f.parent if f.is_file() else f) / name).with_suffix(".yaml")
                    try:
                        path.write_text(yaml.safe_dump(tracklist, sort_keys=False))
                    except Exception as e:
                        sb.display_error(e, "bank save error")
                    else:
                        CONFIG["current_tracklist"] = path.relative_to(TRACKLISTS_PATH).as_posix()
                        save_state(CONFIG_PATH, CONFIG)
            elif choice == "Volume":
                d = 1 / COLS
                slider = [sb.lcd["solid"] * i for i in range(COLS + 1)]
                while True:
                    sb.lcd.write("Master Volume".ljust(COLS), row=0)
                    ival = round(player.volume / d)
                    i, choice = sb.menu_choose(
                        slider, align="left", i=ival, wrap=False,
                        func=lambda i: setattr(player, "volume", i * d)
                    )
                    CONFIG["master_volume"] = player.volume
                    save_state(CONFIG_PATH, CONFIG)
                    if choice == None:
                        break
                    tracks[track.i].setdefault("level", 1.0)
                    sb.lcd.write("Track Level".ljust(COLS), row=0)
                    ival = round(tracks[track.i]["level"] / d)
                    i, choice = sb.menu_choose(
                        slider, align="left", i=ival, wrap=False,
                        func=lambda i: player.duck(i * d)
                    )
                    if i >= 0:
                        tracks[track.i]["level"] = i * d
                    if choice == None:
                        break
            elif choice == "Tracklist":
                t = track.i
                while True:
                    eoscallback = sb.add_action
                    t, name = show_tracklist(t)
                    eoscallback = lambda x: None
                    if t == None:
                        break
                    sb.lcd.clear()
                    sb.lcd.write(name.ljust(COLS), row=0)
                    if len(tracks) > 1:
                        opts = ["Play", "Move", "Delete", "Add"]
                    else:
                        opts = ["Play", "Move", "Add"]
                    i, choice = sb.menu_choose(opts, row=ROWS - 1)
                    if choice == "Play":
                        play_track(t)
                    elif choice == "Move":
                        eoscallback = sb.add_action
                        p, name = show_tracklist(t, end=1)
                        eoscallback = lambda x: None
                        if p == None:
                            break
                        mtrack = tracks.pop(t)
                        if p > t:
                            p -= 1
                        tracks.insert(p, mtrack)
                        if track.i == t:
                            track.i = p
                        elif t < track.i <= p:
                            track.i -= 1
                        elif t > track.i >= p:
                            track.i += 1
                        t = p
                    elif choice == "Delete":
                        tracks.pop(t)
                        if t == track.i:
                            play_track(track.i % len(tracks))
                    elif choice == "Add":
                        f = sb.menu_choosefile(topdir=TRACKS_HEAD, start=tracks_path)
                        if f.is_file():
                            t = len(tracks)
                            tracks.append({"file": str(f.relative_to(tracks_path))})
            # menu finished, display current track name
            sb.lcd.write(track.name.ljust(COLS), row=0)

