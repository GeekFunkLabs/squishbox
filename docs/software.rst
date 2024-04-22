Software
========

The FluidPatcher software for the SquishBox turns it into a customizable MIDI sound module. The software is installed on Raspberry Pi OS by running a script from the command line. This downloads the code that runs the synth and a few other software dependencies, and sets up the interface to run on startup. These changes aren’t drastic – you don’t have to sacrifice your Raspberry Pi computer or buy a new one to use exclusively with the SquishBox! You can install the software on a working OS without wiping anything, and you can easily pop the Pi out of the enclosure and use it for something else as you need. You can view the source code for FluidPatcher at https://github.com/GeekFunkLabs/fluidpatcher and learn how it works if that interests you.

Setup
------------

If you’re using a brand new Raspberry Pi or just want to start fresh you can get OS images and instructions on installing at https://raspberrypi.org/software, and information on how to set up your Pi at https://raspberrypi.org/documentation.

Log in, make sure your Pi is connected to the internet, and enter the following command::

   curl -sL geekfunklabs.com/squishbox | bash

This will download and run an install script that will query you for options, then do all the configuration and software installation automatically. The first time running the script you will see the message ::

   This script must reboot your computer to activate your sound card.
   Once this is complete, run this script again to continue setup.
   Reboot? ([y]/n)

Respond `y` to reboot, then enter the above command again. The script will now query you for install options. You can just press enter for each option to choose the defaults (enclosed in square brackets) to install everything, but here is an explanation of each of the options. ::

   What are you setting up?
   1. SquishBox
   2. Naked Raspberry Pi Synth

This software can be installed on a bare Raspberry Pi without the SquishBox add-ons, but you should choose option 1 here. The script may need to reboot your Pi in order to set up the sound card, after which you should run the script again to continue. ::

   What version of SquishBox hardware are you using?
   v6 - Green PCB with SMT components
   v4 - Purple PCB, has 2 resistors and LED
   v3 - Purple PCB, has 1 resistor
   v2 - Hackaday/perfboard build

Different versions of the PCB have slightly different wiring. The PCB used in these instructions is v6. ::

   Enter Install location [/home/user]

The code installs in your home directory by default, but can be installed in any location where you have write privileges. ::

   Which audio output would you like to use?
   0. No change
   1. Default
   2. Headphones
   3. sndrpihifiberry
   4. vc4hdmi
   Choose [3]
   
Choose sndrpihifiberry from the list. ::

   Install/update synthesizer software? ([y]/n)

This installs the base code that runs the SquishBox. You can also use this script to reconfigure some of the later optional extras, so if you want to do that without changing your code, reply no here. ::

   Set up web-based file manager? ([y]/n)
   Please create a user name and password.
   username:
   password:

When the SquishBox is connected to a network, its web interface provides a convenient way of editing your patches, banks, and config files, as well as uploading soundfonts. Choose a good password to protect your SquishBox settings from other users on the same network. To log in to the file manager, connect a computer/tablet/phone to the same network as the SquishBox and point a web browser to the IP address of the SquishBox (see “WIFI Settings” below). ::

   Download and install ~400MB of additional soundfonts? (y/[n])

Responding `y` downloads a collection of extra soundfonts in addition to the general MIDI soundfont that is downloaded by default. ::

   Update/upgrade your operating system? ([y]/n)

Any time you install new software on the Raspberry Pi, it’s a good idea to make sure your other software is all up to date, so you should probably say yes here. ::

   Option selection complete. Proceed with installation? ([y]/n)

The terminal will start producing a bunch of output as it installs and configures the necessary software. ::

   This may take some time ... go make some coffee.

If something does go wrong, this output can often be helpful in identifying the problem when seeking support, which can be found at geekfunklabs.com/support. Once finished, the software will ask if you would like to reboot. If you haven’t installed the Pi in the SquishBox yet, you can reply no and then enter sudo poweroff to safely shut down.

If you want to use the Pi for something else, you can enter sudo systemctl disable squishbox at the command line to stop the synth from running on startup. If needed later, you can enter sudo systemctl enable squishbox to get it back again.

Usage
-----

When you plug in the SquishBox, the Pi will boot and start the synthesizer software. The FluidPatcher version is displayed while the last-used bank loads. The current patch name, number, and total patches available are displayed on the LCD. Rotating the encoder cycles through patches. The encoder can also be tapped to advance to the next patch. The stompbutton sends MIDI messages that can be routed in banks or patches to act as a pedal, effects control, or perform other actions. The messages sent are control change 30 with a value of 127 and 0 on press and release, and control change 31 toggling between 0 and 127 with each press.
Holding down the rotary encoder for one second opens the menu. In menus the stompbutton does not send MIDI messages. Instead, rotating the encoder scrolls through options, or tapping the encoder advances to the next option and tapping the stompbutton goes back. This makes it easier to use the SquishBox with feet if it’s placed on the floor. Holding the encoder for one second selects options, and holding the stompbutton for one second cancels or exits. Most menus will time out after a few seconds with no input.
Some menus have specific interaction modes:

* When asked to confirm a choice, it will be shown with a check mark or X next to it. Selecting the check mark confirms, X cancels. 
* Some menus allow changing a numerical setting. Rotating the encoder adjusts the value, and holding the encoder confirms it.
* Some menus allow entering text character-by-character. The cursor appears as an underline for changing position and a blinking square for changing the current character. Holding the encoder switches between cursor modes. Holding the stompbutton exits editing, after which you will be asked to confirm or cancel your entry.

Below is a list of the menu options, with short descriptions of what they do.
* Load Bank – Load a bank file from the list of available banks. The current bank is displayed first. 
* Save Bank – Save the current bank. Changing the name saves as a new bank. 
* Save Patch – Saves the current state of the synthesizer (instrument settings, control change values) to the current patch. Modify the name to create a new patch. 
* Delete Patch – Erases the current patch from the bank, after asking for confirmation. 
* Open Soundfont – Opens a single soundfont and switches to playing sounds from the soundfont's presets instead of the patches in the current bank. Holding the encoder creates a new patch in the current bank that uses the selected preset on MIDI channel 1, after prompting you for a new for the new patch.
* Effects.. – Opens a menu that allows you to modify the settings of the chorus and reverb effects units, and the gain (maximum output volume) of the SquishBox. Changes affect all patches in the bank – save the bank to make them permanent. 
* System Menu.. – Opens a menu with more system-related tasks: 

	* Power Down – To protect the memory card of the SquishBox, this option should be used before unplugging. Allow 30 seconds for complete shutdown. 
	* MIDI Devices – This menu can be used to view the list of available MIDI devices, and to interconnect MIDI inputs and outputs. By default, the SquishBox automatically connects to all available MIDI devices, but this menu allows more control. It also includes a MIDI Monitor option that displays incoming MIDI messages on the screen. Pressing any button exits the MIDI monitor. 
	* WIFI Settings – Displays the current IP Address of the SquishBox, and provides a menu to scan for and connect to available WIFI networks. You can also enable/disable the wifi adapter here. It is useful to turn off the wifi adapter when you are out of range of any known networks, to keep the Pi from wasting CPU doing scans.
	* USB File Copy – Allows you to copy your banks, soundfonts, and config files back and forth between the SquishBox and a USB storage device. Files are copied to/from a SquishBox/ folder on the USB. The Sync with USB option will update the files to the newest available version on either device.  

The SquishBox software and soundfonts collection include several banks with useful patches, and a large selection of soundfonts. However, a powerful feature of the SquishBox is the ability to configure it the way you need and create and your own patches. For information on how to edit the config and bank files for your squishbox refer to the README at:

github.com/GeekFunkLabs/fluidpatcher/blob/master/patcher/file_formats.md

There you can also find a link to a series of lesson videos on editing and creating patches, uploading new sounds, and configuring your SquishBox.

API Reference
-------------

stuff and things