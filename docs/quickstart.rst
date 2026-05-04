Quick Start
===========

Follow the steps below to get a SquishBox up and running quickly. Some or all
of the hardware steps can be skipped by purchasing a kit or fully assembled
unit from the Geek Funk Labs `store <https://geekfunklabs.com/store>`__.

1. `Fabricating PCB and Enclosure`_
2. `Putting it Together`_
3. `Installing the Software`_
4. `Basic Usage`_

Fabricating PCB and Enclosure
-----------------------------

The PCB fabrication files include only the surface-mount components for
automated assembly. Through-hole components are intended to be sourced
separately and soldered by hand.

Load the enclosure model files in ``hardware/enclosure/`` into your preferred
slicer software for 3D printing. All parts are designed to print flat-side
down without supports.

Three enclosure variants are provided:

* **basic** — Fits Raspberry Pi 3 Model B+ and Raspberry Pi 4 Model B.
  A Raspberry Pi 5 can fit, but not with the standard fan installed.
* **deluxe** — Fits Pi 3/4 and adds mounting points for two momentary
  footswitches and two LEDs, which can be connected to the P1 header on
  the SquishBox PCB.
* **mini** — Fits Raspberry Pi Model A+, with an enlarged cutout to
  accommodate wide USB cables or adapters.

Recommended print notes:

* PLA is sufficient, though other materials may be used for specific traits
* Infill is not critical due to the small internal volume
* Use at least 2–3 wall layers for good strength

Putting it Together
-------------------

Insert the through-hole components from the side of the PCB with the matching
silkscreen outlines, then solder them in place.

Install the LCD module last, as it blocks access to several other solder
points.

Mount the completed PCB into the enclosure by passing the rotary encoder shaft
and audio jacks through the corresponding openings, then secure them with the
included washers and nuts.

Install the Raspberry Pi by plugging its GPIO header into the 2x20 socket,
then fasten the lid in place.

Installing the Software
-----------------------

The SquishBox software is targeted for a Pi 3B+/4 running Raspberry Pi OS
(64-bit, based on Debian 13 "Trixie") or newer.
To install on a fresh or existing system, log in as a regular user and run:

.. code-block:: bash

    bash <(curl -sL geekfunklabs.com/squishbox)

Answer the prompts, wait for the installation to complete, then reboot the Pi
to activate the LCD and control interface.

Basic Usage
-----------

On first boot, the SquishBox launches a menu system for starting apps or
changing system settings.

Controls:

* Turn the rotary encoder to move through menu items
* Tap the encoder to confirm a selection
* Press and hold the encoder to cancel or return to the previous screen

To safely power down before disconnecting power, choose **Shutdown** from the
**Exit** menu.
