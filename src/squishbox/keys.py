"""Simple keystroke capturing"""
from contextlib import contextmanager
import threading
import time

from evdev import InputDevice, list_devices, ecodes


keycodes = (
"KEY_A", "KEY_B", "KEY_C", "KEY_D", "KEY_E", "KEY_F", "KEY_G", "KEY_H",
"KEY_I", "KEY_J", "KEY_K", "KEY_L", "KEY_M", "KEY_N", "KEY_O", "KEY_P",
"KEY_Q", "KEY_R", "KEY_S", "KEY_T", "KEY_U", "KEY_V", "KEY_W", "KEY_X",
"KEY_Y", "KEY_Z", "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5",
"KEY_6", "KEY_7", "KEY_8", "KEY_9", "KEY_0", "KEY_GRAVE", "KEY_MINUS", "KEY_EQUAL",
"KEY_LEFTBRACE", "KEY_RIGHTBRACE", "KEY_BACKSLASH", "KEY_SEMICOLON",
"KEY_APOSTROPHE", "KEY_COMMA", "KEY_DOT", "KEY_SLASH", "KEY_SPACE")

keymap_us = (
r"""abcdefghijklmnopqrstuvwxyz1234567890`-=[]\;',./ """,
r"""ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()~_+{}|:"<>? """
)

KEYMAPS = {
"us": {keycodes[i]: (keymap_us[0][i], keymap_us[1][i]) for i in range(len(keycodes))}
}

SCAN_TIME = 2.0
POLL_TIME = 0.01

state = type("State", (), dict(running=False, thread=None))


@contextmanager
def keys_dispatch(on_key, loc="us"):
    state.running = True
    state.thread = threading.Thread(
        target=_listen,
        args=(on_key, KEYMAPS[loc]),
        daemon=True,
    )
    state.thread.start()
    try:
        yield
    finally:
        state.running = False
        state.thread.join()


def _listen(on_key, keymap):
    devs = {}
    last_scan = 0
    shift, caps = False, False
    while state.running:
        t = time.time()
        if t - last_scan > SCAN_TIME:
            devs = refresh_devices(devs)
            last_scan = t
        for dev in list(devs.values()):
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY:
                        k = ecodes.KEY[event.code]
                        if k == "KEY_LEFTSHIFT" or k == "KEY_RIGHTSHIFT":
                            shift = event.value > 0
                        elif event.value > 0:
                            if k == "KEY_CAPSLOCK":
                                caps = not caps
                            elif k == "KEY_LEFT":
                                on_key(("key", "left"))
                            elif k == "KEY_RIGHT":
                                on_key(("key", "right"))
                            elif k == "KEY_BACKSPACE":
                                on_key(("key", "erase"))
                            elif k == "KEY_INSERT":
                                on_key(("key", "insert"))
                            elif k == "KEY_ENTER" or k == "KEY_ESC":
                                on_key(("key", "done"))
                            elif k in keymap:
                                on_key(("key", keymap[k][shift ^ caps]))
            except BlockingIOError:
                pass
            except OSError:
                devs = refresh_devices(devs)
        time.sleep(POLL_TIME)


def refresh_devices(current):
    paths = set(list_devices())
    for p in set(current) - paths:
        try:
            current[p].close()
        except Exception:
            pass
        del current[p]
    for p in paths - set(current):
        try:
            dev = InputDevice(p)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                current[p] = dev
        except Exception:
            pass
    return current

