import os
from pathlib import Path

import yaml


def load_config(path, default_cfg=""):
    if path.exists():
        user_cfg = yaml.safe_load(path.read_text())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default_cfg)
        user_cfg = {}
    cfg = yaml.safe_load(default_cfg) | user_cfg
    for key, val in list(cfg.items()):
        if key.endswith("_path") and val is not None:
            cfg[key] = Path(val)
    return cfg


def save_state(path, cfg):
    cfg_posix = {k: v.as_posix() if isinstance(v, Path) else v
                 for k, v in cfg.items()}
    path.write_text(yaml.safe_dump(cfg_posix, sort_keys=False))


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)

CONFIG_PATH = Path(os.getenv(
    "SQUISHBOX_CONFIG",
    "~/SquishBox/config/squishboxconf.yaml"
)).expanduser()

DEFAULT_CFG = """\
lcd_rows: 2
lcd_cols: 16
menu_time: 3
hold_time: 1.0
scroll_time: 0.2
scroll_pause: 3
menu_timeout: 3.0
frame_time: 0.1
poll_time: 0.01
button_debounce: 0.02
encoder_debounce: 0.002
lcd_regsel: 7
lcd_enable: 16
lcd_data: [26, 6, 5, 8]
lcd_exec_time: 5.0e-05
controls:
  knob1:
    type: encoder
    pins: [22, 27]
    events: {left: dec, right: inc}
  knob1_button:
    type: button
    pin: 17
    events: {tap: select, hold: back}
outputs:
  contrast: {type: pwm, pin: 12, level: 100}
  backlight: {type: pwm, pin: 13, level: 100}
pull_up: true
active_high: true
gpio_chip: /dev/gpiochip4
glyphs_5x8:
  check: |
    -----
    ----X
    ---XX
    X-XX-
    XXX--
    -X---
    -----
    -----
  cross: |
    -----
    XX-XX
    -XXX-
    --X--
    -XXX-
    XX-XX
    -----
    -----
  wifi_on: |
    -XXX-
    X---X
    --X--
    -X-X-
    -----
    --X--
    -----
    -----
  wifi_off: |
    -X-X-
    --X--
    -X-X-
    -----
    --X--
    -----
    --X--
    -----
  note: |
    --X--
    --XX-
    --X-X
    --X-X
    --X--
    XXX--
    XXX--
    -----
"""

CONFIG = load_config(CONFIG_PATH, DEFAULT_CFG)

