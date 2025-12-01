from pathlib import Path
import threading
import time

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

Gst.init(None)

class GStreamerPlayer:
    """A simple music player with fade and volume control using GStreamer."""

    def __init__(self, fade_time=2.0, initial_volume=0.8):
        self.fade_time = fade_time
        self.target_volume = initial_volume
        self.current_volume = 0.0
        self.lock = threading.Lock()

        # Two playbins for crossfading
        self.players = [Gst.ElementFactory.make("playbin", None) for _ in range(2)]
        for p in self.players:
            p.set_property("volume", 0.0)

        self.active = 0
        self.bus_watch_thread = threading.Thread(target=self._bus_watch, daemon=True)
        self.loop = GLib.MainLoop()
        threading.Thread(target=self.loop.run, daemon=True).start()
        self.playing = False
        self.bus_watch_thread.start()

    # ---------------------------------------------------------
    # Playback control
    # ---------------------------------------------------------
    def set_uri(self, uri):
        """Prepare next track for playback (no fade yet)."""
        next_idx = 1 - self.active
        player = self.players[next_idx]
        player.set_state(Gst.State.NULL)
        player.set_property("uri", uri)
        player.set_property("volume", 0.0)

    def play(self, uri=None):
        """Start or crossfade to a new URI."""
        if uri:
            self.set_uri(uri)
            self._crossfade_to_next()
        else:
            # resume current player
            p = self.players[self.active]
            p.set_state(Gst.State.PLAYING)
            self._fade(p, self.current_volume, self.target_volume)
        self.playing = True

    def pause(self):
        """Pause current player (no fade)."""
        self.players[self.active].set_state(Gst.State.PAUSED)
        self.playing = False

    def stop(self):
        """Stop playback and fade out."""
        p = self.players[self.active]
        self._fade(p, self.current_volume, 0.0)
        p.set_state(Gst.State.NULL)
        self.playing = False

    # ---------------------------------------------------------
    # Volume control
    # ---------------------------------------------------------
    def set_volume(self, vol):
        """Set target volume (0.0–1.0)."""
        with self.lock:
            self.target_volume = max(0.0, min(vol, 1.0))
            self.players[self.active].set_property("volume", self.target_volume)
            self.current_volume = self.target_volume

    def fade_to_volume(self, new_vol, duration=None):
        """Smoothly fade to new volume."""
        duration = duration or self.fade_time
        p = self.players[self.active]
        self._fade(p, self.current_volume, new_vol, duration)
        with self.lock:
            self.target_volume = new_vol
            self.current_volume = new_vol

    # ---------------------------------------------------------
    # Private internals
    # ---------------------------------------------------------
    def _fade(self, player, start, end, duration=None):
        """Simple software volume fade loop."""
        duration = duration or self.fade_time
        steps = int(duration * 20)  # 20 Hz fade resolution
        delta = (end - start) / steps if steps > 0 else 0
        for i in range(steps):
            with self.lock:
                self.current_volume = start + delta * i
                player.set_property("volume", self.current_volume)
            time.sleep(1/20.0)
        player.set_property("volume", end)
        with self.lock:
            self.current_volume = end

    def _crossfade_to_next(self):
        """Crossfade from active player to next one."""
        cur = self.players[self.active]
        nxt_idx = 1 - self.active
        nxt = self.players[nxt_idx]

        nxt.set_state(Gst.State.PLAYING)
        threads = [
            threading.Thread(target=self._fade, args=(cur, self.current_volume, 0.0, self.fade_time), daemon=True),
            threading.Thread(target=self._fade, args=(nxt, 0.0, self.target_volume, self.fade_time), daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        cur.set_state(Gst.State.NULL)
        self.active = nxt_idx

    def _bus_watch(self):
        """Monitor EOS or errors asynchronously."""
        while True:
            bus = self.players[self.active].get_bus()
            msg = bus.timed_pop_filtered(500 * Gst.MSECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if not msg:
                continue
            if msg.type == Gst.MessageType.EOS:
                self.on_end_of_stream()
            elif msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                print(f"[GStreamer Error] {err}: {dbg}")

    # ---------------------------------------------------------
    # Hook for external EOS handling
    # ---------------------------------------------------------
    def on_end_of_stream(self):
        """Override this or attach a callback externally."""
        print("Track ended.")

player = GStreamerPlayer()
player.play(Path("/home/billyp/Downloads/09 - Museum Of Idiots.mp3").as_uri())
input("Press enter to fade to next track")
player.play(Path("/home/billyp/Downloads/02 - Bap Bap Bap.mp3").as_uri())
input("Press enter to stop")

