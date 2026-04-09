# SquishBox Hardware

This directory contains the design and fabrication files for the SquishBox PCB and enclosure. These files are sufficient to fabricate the PCB, source components, and 3D-print a complete enclosure.

Editable design files are also provided to support modification and customization. If anything is missing or unclear, please open a GitHub issue or contact [albedozero@geekfunklabs.com](mailto:albedozero@geekfunklabs.com).

## Directory Structure

```shell
hardware/
  pcb/
    fabrication/    # Gerbers, drill files, pick-and-place, BOM
    kicad/          # KiCad source design files
  enclosure/
    print/          # STL and 3MF files for slicing
    freecad/        # FreeCAD source design files
    step/           # STEP files for other CAD software
```

## PCB Details

The fabrication files include only surface-mount components for automated assembly. Through-hole components are intended to be sourced separately and soldered by hand.

Insert through-hole components from the side matching the silkscreen outlines.

Install the LCD module last, as it blocks access to several solder points.

### P1 Header

Unused pins from the Raspberry Pi GPIO header are broken out to P1 for attaching additional buttons/outputs. Pins 4 and 7 are connected to ground through 1k resistors, to allow connecting LEDs without additional components.

| P1 pin | function        |
|--------|-----------------|
|  1     | 5V              |
|  2     | 3.3V            |
|  3     | GPIO4           |
|  4     | 1k → GND        |
|  5     | GPIO2 (I2C SDA) |
|  6     | GPIO3 (I2C SCL) |
|  7     | 1k → GND        |
|  8     | GPIO23          |
|  9     | GPIO24          |
|  10    | GPIO10          |
|  11    | GPIO25          |
|  12    | GPIO9           |
|  13    | GPIO11          |
|  14    | GND             |

## Case Details

All parts are designed to be printed flat-side down without supports.

* Infill amount is not critical due to the small interior volume
* Use at least 2–3 wall layers for adequate strength

Three enclosure variants are provided:

* **basic** — Fits Raspberry Pi 3 Model B+ / Raspberry Pi 4 Model B. A Raspberry Pi 5 can fit, but not with the standard fan installed.
* **deluxe** — Fits Pi 3/4 and includes mounting points for two momentary footswitches and two LEDs, which can be connected to the P1 header on the SquishBox PCB.
* **mini** — Fits Raspberry Pi Model A+, with an enlarged cutout to accommodate wide USB cables or adapters.

