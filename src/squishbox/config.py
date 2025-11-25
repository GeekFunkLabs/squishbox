import os
from pathlib import Path

import yaml


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def load_config():
    if CONFIG_PATH.exists():
        user_cfg = yaml.safe_load(CONFIG_PATH.read_text())
    else:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(yaml.safe_dump(DEFAULTS))
        user_cfg = {}
    CONFIG = DEFAULTS | user_cfg
    return CONFIG


def save_state(cfg):
    CONFIG_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False))


CONFIG_PATH = Path(os.getenv(
    "SQUISHBOX_CONFIG",
    "~/.config/squishbox/squishboxconf.yaml"
)).expanduser()

yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)

DEFAULTS = yaml.safe_load("""\
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
lcd_contrast: 12
lcd_backlight: 13
contrast_level: 100
backlight_level: 100
rotary_left: 22
rotary_right: 27
rotary_button: 17
pull_up: true
active_high: true
gpio_chip: /dev/gpiochip4
glyphs_5x8:
  backslash: |
    -----
    X----
    -X---
    --X--
    ---X-
    ----X
    -----
    -----
  tilde: |
    -----
    -----
    -----
    -XX-X
    X--X-
    -----
    -----
    -----
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
  folder: |
    -----
    -----
    XX---
    X-XXX
    X---X
    X---X
    XXXXX
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
""")

CONFIG = load_config()

