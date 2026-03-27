import importlib.resources as res
import os
from pathlib import Path

import yaml


CONFIG_PATH = Path(os.getenv(
    "SQUISHBOX_CONFIG",
    "~/SquishBox/config/squishboxconf.yaml"
)).expanduser()


def load_config(name, default_cfg={}):
    """Load configuration data
    
    Loads config from YAML files, including drop-in configs if found.
    Creates a default config if target doesn't exist. Returns config as
    a dict after performing Path conversion on items with keys ending
    in ``_path``.
    
    Args:
        name (str | Path): config file relative to CONFIG_PATH or absolute
        default_cfg (dict): overrides for initial config values

    Returns:
        dict: config data
    """
    path = CONFIG_PATH.parent / name
    sys_default = Path("/usr/share/squishbox/defaults") / path.name
    pkg_default = res.files("squishbox.data.defaults") / path.name
    if sys_default.exists():
        cfg = yaml.safe_load(system_default.read_text())
    elif pkg_default.exists():
        cfg = yaml.safe_load(pkg_default.read_text())
    cfg |= default_cfg

    if path.exists():
        cfg |= yaml.safe_load(path.read_text())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(default_cfg, sort_keys=False))

    conf_d = path.parent / (path.stem + ".d")
    if conf_d.exists():
        for f in sorted(conf_d.glob("*.yaml")):
            cfg |= yaml.safe_load(f.read_text())

    for key, val in list(cfg.items()):
        if key.endswith("_path") and val is not None:
            cfg[key] = Path(val).expanduser()

    return cfg
    
    
def save_state(name, cfg):
    """Write config data back to a file
    
    Args:
        name (str | Path): config file relative to CONFIG_PATH or absolute
        cfg (dict): the current config state
    """
    path = CONFIG_PATH.parent / name
    cfg_posix = {k: v.as_posix() if isinstance(v, Path) else v
                 for k, v in cfg.items()}
    path.write_text(yaml.safe_dump(cfg_posix, sort_keys=False))


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)

CONFIG = load_config(CONFIG_PATH.name)

