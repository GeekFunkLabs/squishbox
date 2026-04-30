# SquishBox

- [Official Documentation](https://geekfunklabs.github.io/squishbox)
- [Source Repository](https://github.com/GeekFunkLabs/squishbox)

The SquishBox is a compact add-on board and enclosure for Raspberry Pi
(primarily Pi 3B+ and Pi 4) that combines:

- high-quality stereo DAC with 1/4" outputs
- MIDI in/out via TRS minijacks
- 16x2 character LCD
- pushbutton rotary encoder
- breakout GPIO for extra controls, LEDs, and peripherals

This creates a portable embedded platform for audio projects such as synths,
sound modules, pedalboard utilities, sequencers, and music players.

The software package includes ready-to-run applications plus a simple Python API
for building your own.

## Building/Obtaining

This repository includes schematics, PCB fabrication files, BOMs, and enclosure
models for users who want to build their own hardware.

Kits and pre-built units are also available from the Geek Funk Labs
[store](https://geekfunklabs.com/store).

## Installing

The SquishBox software targets Raspberry Pi OS 13 (Trixie) on Pi 3B+/4.
Other platforms may work but are not officially tested.

To install on a fresh or existing system, log in as a regular user and run:

```bash
curl -sL geekfunklabs.com/squishbox | bash
```

Answer the prompts, wait for install to complete,
and reboot the Pi to activate the LCD/button interface.

## Using the SquishBox

On first boot, the SquishBox starts a launcher that lets the user choose
an app to run or modify system settings.
Selections can be made by turning the rotary encoder.
Tapping the rotary encoder confirms a choice.
Pressing and holding the encoder will cancel or return to the previous
screen in most situations.
To safely shut down the SquishBox before disconnecting power,
use the "Shutdown" option in the "Exit" menu.

## Writing SquishBox Apps

The squishbox python package provides access to the LCD,
controls (buttons/encoders), outputs,
and a set of menu-driven interaction helpers.
Here is a simple example app:

```python
import squishbox

sb = squishbox.SquishBox()

sb.lcd.clear()
sb.lcd.write("Audio Test", row=0)

while True:
    i, option = sb.menu_choose(["Noise", "Sine", "Exit"], row=1)

    if option == "Noise":
        sb.shell_cmd("speaker-test -l2 -c2")

    elif option == "Sine":
        sb.shell_cmd("speaker-test -l2 -c2 -tsine")

    elif option == "Exit":
        break
```

## Support and Feature Requests

The SquishBox is under active development, and feature requests are
welcome. 

Please post requests/questions to Discussions on GitHub,
and open issues or pull requests for bugs.

