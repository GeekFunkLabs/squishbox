import os
from pathlib import Path

import yaml

DEFAULTS = {
    "lcd_rows": 2,
    "lcd_cols": 16,
    "menu_time": 3,
    "hold_time": 1.0,
    "scroll_time": 0.2,
    "scroll_pause": 3,
    "menu_timeout": 3.0,
    "frame_time": 0.1,
    "poll_time": 0.01,
    "button_debounce": 0.02,
    "encoder_debounce": 0.002,
    "lcd_exec_time": 50e-6,
    "lcd_regsel": 7,
    "lcd_enable": 16,
    "lcd_data": (26, 6, 5, 8),
    "lcd_cols": 16,
    "lcd_rows": 2,
    "lcd_contrast": 12,
    "lcd_backlight": 13,
    "contrast_level": 100,
    "backlight_level": 100,
    "rotary_left": 22,
    "rotary_right": 27,
    "rotary_button": 17,
    "pull_up": True,
    "active_high": True,
    "gpio_chip": "/dev/gpiochip4",
}

CONFIG_PATH = Path(os.getenv(
    "SQUISHBOX_CONFIG",
    "~/.config/squishbox/squishboxconf.yaml"
)).expanduser()

def load_config():
    if CONFIG_PATH.exists():
        user_cfg = yaml.safe_load(path.read_text())
    else:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(yaml.safe_dump(DEFAULTS))
        user_cfg = {}
    CONFIG = DEFAULTS | user_cfg
    return CONFIG

def save_state(config):
    CONFIG_PATH.write_text(yaml.safe_dump(config, sort_keys=False))

CONFIG = load_config()

