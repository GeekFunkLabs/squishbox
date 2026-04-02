# SquishBox

The SquishBox is a compact add-on card and enclosure for Raspberry Pi (primarily targeting Pi 3B+ or 4) that provides a rotary encoder, a bright and easy-to-read 16x2 character LCD display, a high-quality sound card with 1/4" outputs, and MIDI in/out minijacks. Additional GPIO pins are broken out to allow adding more buttons, controls, LEDS, and other inputs/outputs. This makes it a highly portable embedded computer for audio applications, such as a synth/sound module or music player. The software package includes several pre-built applications for these purposes, as well as a simple python API for creating more. 

The official documentation for the SquishBox is hosted at https://geekfunklabs.github.io/squishbox.

## Building/Obtaining

The [source code repository](https://github.com/GeekFunkLabs/squishbox) for the SquishBox includes all the parts lists, schematics, and design files necessary to manufacture the PCB and 3D-print an enclosure. Users can also obtain kits or pre-built units from the Geek Funk Labs [Tindie store](https://www.tindie.com/stores/albedozero/).

## Installing

The software for the SquishBox is targeted at Pi 3B+/4 running Raspberry Pi OS version 13 (Trixie). Results on other platforms may vary. Install can be performed on a fresh or working system. The install script downloads all necessary software and performs setup. To run the install script on a fresh or working system, log in as a regular user and enter

```bash
curl -sL geekfunklabs.com/squishbox | bash
```

Answer the prompts, wait for install to complete, and reboot the Pi to activate the LCD/button interface.

## Using the SquishBox

On first boot, the SquishBox starts a launcher that lets the user choose an app to run or modify system settings. Selection can be made by turning the rotary encoder. Tapping the rotary encoder confirms a selection. Pressing and holding the encoder will cancel or return to the previous screen in most situations. To safely shut down the SquishBox before disconnecting power, use the "Shutdown" option in the "Exit" menu.

## Writing SquishBox Apps

The squishbox python package provides access to the LCD, controls (buttons/encoders), outputs, and a set of menu-driven interaction helpers. Here is a simple example app:

```python
import squishbox

sb = squishbox.SquishBox()
sb.lcd.clear()
sb.lcd.write("Simple SquishBox App", row=0)
i, option = sb.menu_choose(["Option 1", "Option 2", "Option 3"], row=1)
```

More information on writing apps and making them visible in the launcher can be found in the [official documentation](https://geekfunklabs.github.io/squishbox).

