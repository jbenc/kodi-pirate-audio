# Kodi addon for Pimoroni Pirate Audio boards

Support for the on-board display and buttons on Pimoroni Pirate Audio.

[Pimoroni Pirate Audio](https://learn.pimoroni.com/tutorial/sandyj/getting-started-with-pirate-audio)
is a family of small factor expansion boards for Raspberry Pi, especially
suitable for Raspberry Pi Zero. While it supports MPD (Music Player Daemon)
out of the box, I wanted a solution based on [Kodi](https://kodi.tv/) to offer
a better experience to the family. We're already using
[Kore](https://kodi.wiki/view/Kore) to access our home theater system and
want to control all home players by a single app.

## Requisites

```
apt-get install python-rpi.gpio python-spidev python-pil
```

## Debugging

To see what is Kodi displaying, create `/tmp/piratekodiview` file to switch
on a debug mode. Pressing one of the buttons then shows a corresponding part
of Kodi screen (button A shows the top left part, etc). Note what you see is
a screenshot, not a live view. To refresh the screen, press the button
again. A long press of any of the buttons will switch off the screen.

If you don't have a keyboard connected, use the remote control in web view
or in Kore.

Note that when Kodi is in a screen saver mode, the screenshot may show
garbage. Press any button on the remote to dismiss the screen saver.

## Development

The heart of the addon is a **piratedisplay** Python module. It is a from
scratch implemention of ST7789 display driver in Python. While there is an
existing ST7789 PIP project, it is unsatisfactory: it initializes the
display in a rather weird way (limits the number of colors that can be
displayed, instructs the hardware to rotate the image by 90° and compensates
for that by rotating by -90° in sofware, sets a custom hard coded gamma,
etc). The **piratedisplay** module is much more performant. With the same
image displayed in a loop:

.               | ST7789 PIP | piratedisplay
----------------|------------|--------------
FPS             | 3.7        | > 19
CPU consumption | ~ 50%      | ~ 15%
initialization  | 2.5 sec    | 1.5 sec

In addition, the **piratedisplay** module handles the buttons including
optional software repeat.

The module is usable on its own in other projects.
