"""SquishBox Raspberry Pi interface

This module provides classes and functions for creating python applications
for the `SquishBox <https://www.geekfunklabs.com/products/squishbox>`_ ,
a Raspberry Pi add-on that provides an LCD, pushbutton rotary encoder,
sound card, and MIDI input/output.

Requires:
- gpiod
- yaml
"""

from importlib.metadata import version, PackageNotFoundError

from .squishbox import SquishBox
from .config import CONFIG

__all__ = ["SquishBox", "CONFIG"]

try:
    __version__ = version("squishbox")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

