Programming
===========

This page is a practical primer for customizing/writing SquishBox apps.


Instead of dealing directly with GPIO timing, LCD protocols,
encoder debouncing, or event queues, applications interact with
a single high-level object

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

``SquishBox()`` always returns the same shared hardware interface instance.

.. code-block:: python

   a = squishbox.SquishBox()
   b = squishbox.SquishBox()

   print(a is b)   # True

This allows helper modules or plugins to access the hardware safely without
creating duplicate GPIO handlers.

Application Model
-----------------

Most SquishBox programs follow a simple pattern:

1. Access the shared ``SquishBox()`` instance
2. Start the synth/audio process
3. Draw something on the LCD
4. Wait for user input
5. Respond to that input
6. Repeat until exit

Example:

.. code-block:: python

    import squishbox

    sb = squishbox.SquishBox()
    sb.lcd.clear()
    sb.lcd.write("My Cool Synth", row=0)

    i = 0
    synth = start_synth()
    synth.select_patch(i)

    while True:
        i, action = sb.menu_choose(synth.patchnames, i=i)

        if action == None:
            break
        else:
            synth.select_patch(i)

Configuration Files
^^^^^^^^^^^^^^^^^^^

The main SquishBox configuration file ``squishboxconf.yaml`` is intended
to allow the user to change global behavior without modifying code.

The ``controls`` section defines named inputs such as buttons and encoders.
Each item describes the hardware type, GPIO settings, and event bindings.

* ``actions`` Links events to SquishBox UI actions:

  * ``inc``/``dec`` change a value/option
  * ``select`` do/confirm
  * ``back`` cancel/return
  
* ``messages`` Emits MIDI messages in response to events.
  Message format is ``<type>:<channel>:<number>:<value>``.
  Only control change messages (``ctrl``) are implemented.


.. code-block:: yaml

    controls:
      knob1:
        type: encoder
        pins: [22, 27]
        actions: {left: dec, right: inc}
      knob1_button:
        type: button
        pin: 17
        actions: {tap: select, hold: back}    
      foot_left:
        type: button
        pin: 9
        messages: {on: ctrl:16:22:127, off: ctrl:16:22:0}

The main config file is loaded on import and stored in the ``CONFIG`` variable.
The ``load_config()`` and ``save_state()`` functions can be used
to manage config files for SquishBox apps.

.. code-block:: python

    from squishbox.config import load_config, save_state

    myconfig = load_config("myappconf.yaml")
    
    ...
    
    myconfig["last_bank_path"] = current_bank
    save_state("myappconf.yaml", myconfig)

Tokens ending with ``_path`` in config files are converted to ``pathlib.Path``
objects upon loading, and are serialized as POSIX strings when saving.

Controlling the LCD
-------------------

The built-in LCD object is available as:

.. code-block:: python

   sb.lcd

Clear the display:

.. code-block:: python

   sb.lcd.clear()

Write text:

.. code-block:: python

   sb.lcd.write("Patch Loaded", row=0)
   sb.lcd.write("Grand Piano", row=1, align="right")

Long text automatically scrolls when needed. Alignment is left by default.

The ``timeout=`` option overlays text for a specified number of seconds:

.. code-block:: python

   sb.lcd.write("Saved", row=1, timeout=2)

This is useful for status messages.

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

User Interaction
----------------

The user interaction helpers use a blocking model - they don't return
until a value is ready (unless ``timeout=`` is used). This makes it easier
to understand program flow. They all have built-in idle loops that update
scrolling elements of the LCD and provide CPU time for other processes
such as synths/audio applications.

Several menu helper functions are provided to make it easy to create apps.

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
* filenames (with ``charset=sb.lcd.fnchars()``)
* labels

Returns the entered text. Use ``menu_confirm()`` afterward to let the user
confirm/cancel the input if desired.

File Browser
^^^^^^^^^^^^

.. code-block:: python

   path = sb.menu_choosefile("/home/pi/patches", ext=[".yaml"])

This provides a simple two-line browser for selecting files. Returns 
a ``Path()`` object for the chosen file, or the last-browsed directory if
canceled. 

System Settings Menu
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    if sb.menu_systemsettings() == "shell":
        sys.exit()

This provides a unified system settings menu for LCD, WiFi, and MIDI
settings. It also allows the user to shutdown/reboot the Pi, or exit
the current program.

Direct Action Handling
^^^^^^^^^^^^^^^^^^^^^^

For more complex user interfaces (e.g. vertically-scrollable menus, screens
with active status indicators and/or custom actions), the ``get_action()``
function can be used to create interaction loops.

Incoming actions are stored in a queue, and ``get_action()``
retrieves them FIFO-style, blocking while the queue is empty
(or until ``timeout`` is exceeded).

.. code-block:: python

    # display scrollable multi-line output

    out = text.splitlines() # some multi-line text
    irow, crow = 0, 0

    while True:
        for i in range(irow, min(irow + ROWS, len(out))):
            sb.lcd.write(
                (out[i] if i < len(out) else "").ljust(COLS),
                row=i - irow
            )
        match sb.get_action():
            case "inc":
                crow += 1
                if crow == ROWS or crow == len(out):
                    crow -= 1
                    irow = min(irow + 1, len(out) - ROWS) % len(out)
            case "dec":
                crow -= 1
                if crow < 0:
                    crow = 0
                    irow = max(irow - 1, 0)
            case "select" | "back":
                break

The ``add_action()`` function can be used as a callback to send events
to be picked up by ``get_action()``. MIDI events are a common case.

.. code-block:: python

    def monitor_midi():
        while True:
            event = midi_input()
            sb.add_action(event)

    ...

    while True:
        sb.lcd.write(patchnames[i], row=0)
        action = sb.get_action()
        if action == "inc":
            i = (i + 1) % len(patchnames)
            select_patch(i)
        elif action == "dec":
            i = (i - 1) % len(patchnames)
            select_patch(i)
        elif isinstance(action, MidiEvent):
            sb.lcd.write(str(action), row=1, timeout=2)

Controlling Outputs
^^^^^^^^^^^^^^^^^^^

Outputs are defined in the configuration file:

.. code-block:: yaml

    outputs:
      led_blinker: {type: binary, pin: 23}
      led_fader: {type: pwm, pin: 4, level: 60}

Configured outputs are available through ``sb.outputs``.

Example:

.. code-block:: python

   sb.outputs["led_blinker"].on()
   sb.outputs["led_blinker"].off()

PWM outputs expose a ``level`` property representing duty cycle percentage.

.. code-block:: python

   sb.outputs["led_fader"].level = 75

Miscellaneous Tools
-------------------

Running Shell Commands
^^^^^^^^^^^^^^^^^^^^^^

The ``shell_cmd()`` method executes a string as a shell command and
returns the output as an ASCII-encoded string.

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

Unhandled exceptions are automatically displayed on the LCD before the
application exits. To handle errors gracefully (i.e. without exiting):

.. code-block:: python

   try:
       load_patch(name)
   except Exception as e:
       sb.display_error(e, "Load failed")

API Reference
-------------

The classes and functions below form the programming interface
for the squishbox package.

.. toctree::
   :maxdepth: 2

   api/squishbox
   api/hardware
   api/config

