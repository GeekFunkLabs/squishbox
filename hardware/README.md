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

## Case Details

All parts are designed to be printed flat-side down without supports.

* Infill amount is not critical due to the small interior volume
* Use at least 2–3 wall layers for adequate strength

Three enclosure variants are provided:

* **basic** — Fits Raspberry Pi 3 Model B+ / Raspberry Pi 4 Model B. A Raspberry Pi 5 can fit, but not with the standard fan installed.
* **deluxe** — Fits Pi 3/4 and includes mounting points for two momentary footswitches and two LEDs, which can be connected to the P1 header on the SquishBox PCB.
* **mini** — Fits Raspberry Pi Model A+, with an enlarged cutout to accommodate wide USB cables or adapters.

