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
