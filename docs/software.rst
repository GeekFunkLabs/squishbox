Software
========

The SquishBox Python package makes it easy to build menu-driven hardware
applications for Raspberry Pi audio projects.

Instead of dealing directly with GPIO timing, LCD protocols, encoder
debouncing, and event handling, your program interacts with a single
high-level object:

.. code-block:: python

   import squishbox
   sb = squishbox.SquishBox()

From there you can:

* Write text to the LCD
* Read knob and button actions
* Present menus and prompts
* Edit text from the front panel
* Control LEDs and outputs
* Launch shell commands
* Build complete standalone hardware applications

This page is a practical primer for customizing/writing SquishBox apps.

Application Model
-----------------

Most SquishBox programs follow a simple pattern:

1. Create the shared ``SquishBox()`` instance
2. Draw something on the LCD
3. Wait for user input
4. Respond to that input
5. Repeat until exit

Example:

.. code-block:: python

   import squishbox

   sb = squishbox.SquishBox()

   sb.lcd.clear()
   sb.lcd.write("Hello SquishBox", row=0)

   while True:
       action = sb.get_action()

       if action == "inc":
           sb.lcd.write("Turned Right ", row=1)

       elif action == "dec":
           sb.lcd.write("Turned Left  ", row=1)

       elif action == "select":
           sb.lcd.write("Tapped       ", row=1)

       elif action == "back":
           break

The default control mappings usually are:

* ``inc`` — clockwise turn
* ``dec`` — counterclockwise turn
* ``select`` — encoder tap
* ``back`` — encoder hold

These mappings come from the hardware configuration and may be customized.

The Shared Singleton
^^^^^^^^^^^^^^^^^^^^

``SquishBox()`` is a singleton. Creating it multiple times returns the same
shared hardware interface.

.. code-block:: python

   a = squishbox.SquishBox()
   b = squishbox.SquishBox()

   print(a is b)   # True

This allows helper modules or plugins to access the hardware safely without
creating duplicate GPIO handlers.

Configuration File
^^^^^^^^^^^^^^^^^^

The SquishBox configuration file is loaded on import, and defines
settings such as:

* LCD configuration
* UI timings
* Inputs/Outputs and bindings
* Custom LCD characters

The default path for the configuration file is: ::

    $HOME/SquishBox/config/squishboxconf.yaml
    
Drop-in config files can be used for things such as
hardware overlays (e.g. ``squishboxconf.d/v2.yaml``).

Using the LCD
-------------

The built-in LCD object is available as:

.. code-block:: python

   sb.lcd

Clear the display:

.. code-block:: python

   sb.lcd.clear()

Set contrast/backlight levels:

.. code-block:: python

   sb.contrast_level = 70
   sb.backlight_level = 40

Write text:

.. code-block:: python

   sb.lcd.write("Patch Loaded", row=0)
   sb.lcd.write("Grand Piano", row=1, align="right")

Long text automatically scrolls when needed. Alignment is left by default.

Custom Characters
^^^^^^^^^^^^^^^^^

Characters beyond the standard "ASCII Printable" set can be defined as
custom characters in the configuration file:

.. code-block:: yaml

    glyphs_5x8:
      wifi_on: |
        -XXX-
        X---X
        --X--
        -X-X-
        -----
        --X--
        -----
        -----

A maximum of 8 unique custom characters can be displayed at once, but
an arbitrary number can be defined in the LCD object. They are displayed
using element access:

.. code-block:: python

   sb.lcd.write("WiFi status: " + sb.lcd["wifi_on"], row=0)

Temporary Messages
^^^^^^^^^^^^^^^^^^

Use ``timeout=`` to overlay a message briefly:

.. code-block:: python

   sb.lcd.write("Saved", row=1, timeout=2)

This is useful for confirmations and status notices.

Menus
-----

The fastest way to build a usable front-panel interface is with the built-in
menu helpers.

Choice Menu
^^^^^^^^^^^

.. code-block:: python

   i, option = sb.menu_choose(
       ["Piano", "Organ", "Synth"],
       row=1
   )

   if option:
       sb.lcd.write(option, row=0)

Returns:

* selected index
* selected item
* item is returned as ``None`` if canceled

Confirmation Prompt
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   if sb.menu_confirm("Delete file?"):
       delete_file()

Text Entry
^^^^^^^^^^

.. code-block:: python

   name = sb.menu_entertext("New Patch")

Useful for:

* patch names
* WiFi passwords
* filenames
* labels

File Browser
^^^^^^^^^^^^

.. code-block:: python

   path = sb.menu_choosefile("/home/pi/patches", ext=[".yaml"])

This provides a simple two-line browser for selecting files.

System Settings Menu
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    if sb.menu_systemsettings() == "shell":
        sys.exit()

This provides a unified system settings menu for LCD, WiFi, and MIDI
settings. It also allows the user to shutdown/reboot the Pi, or exit
the current program.

Input/Output Access
-------------------

Controls and outputs are defined and bound to actions in the
configuration file.

.. code-block:: yaml

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
      led_fader: {type: pwm, pin: 4, level: 60}
      led_blinker: {type: binary, pin: 23}

Reading Input Directly
^^^^^^^^^^^^^^^^^^^^^^

For games, meters, transport controls, or custom interfaces, use raw actions:

.. code-block:: python

   while True:
       action = sb.get_action(timeout=0.1)

       if action == "inc":
           value += 1
       elif action == "dec":
           value -= 1
       elif action == "back":
           break

``timeout`` allows your loop to continue running while waiting for input.

Outputs and LEDs
^^^^^^^^^^^^^^^^

Configured outputs are available through:

.. code-block:: python

   sb.outputs

Example:

.. code-block:: python

   sb.outputs["led1"].on()
   sb.outputs["led1"].off()

PWM duty cycles are controlled using a ``level`` property.

Miscellaneous Toos
------------------

Running Shell Commands
^^^^^^^^^^^^^^^^^^^^^^

For integrating Linux utilities:

.. code-block:: python

   result = sb.shell_cmd("hostname -I")
   sb.lcd.write(result, row=1)

Useful for:

* audio tools
* system commands
* WiFi utilities
* file conversion
* launching synth engines

Long Running Tasks
^^^^^^^^^^^^^^^^^^

Use the activity spinner while work is in progress:

.. code-block:: python

   with sb.lcd.activity("Loading..."):
       load_large_patch()

This gives visual feedback on the LCD while your task runs.

Error Handling
^^^^^^^^^^^^^^

Unhandled exceptions are automatically shown on the LCD with useful debug
information.

Still, for user-facing programs, catch expected errors:

.. code-block:: python

   try:
       load_patch(name)
   except Exception as e:
       sb.display_error(e, "Load failed")

