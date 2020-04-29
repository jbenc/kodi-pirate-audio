# SPDX-License-Identifier: GPL-2.0-or-later

import RPi.GPIO as GPIO
import spidev
import threading
import time

WIDTH = 240
HEIGHT = 240

# BCM pins used by Pirate Audio boards
BCM_LCD_DCX = 9         # command (low) / data (high) serial interface wire (D/CX)
BCM_LCD_BACKLIGHT = 13  # backlight
BCM_BUTTON_A = 5
BCM_BUTTON_B = 6
BCM_BUTTON_X = 16
BCM_BUTTON_Y = 20
BCM_BUTTON_Y2 = 24      # newer revisions (after 23 January 2020)

# ST7789 commands
SWRESET = 0x01
SLPIN = 0x10
SLPOUT = 0x11
INVON = 0x21
DISPOFF = 0x28
DISPON = 0x29
CASET = 0x2a
RASET = 0x2b
RAMWR = 0x2c
MADCTL = 0x36
COLMOD = 0x3a

# Button map
button_map = {
    BCM_BUTTON_A: 'A',
    BCM_BUTTON_B: 'B',
    BCM_BUTTON_X: 'X',
    BCM_BUTTON_Y: 'Y',
    BCM_BUTTON_Y2: 'Y',
}


class PirateDisplay:
    def __init__(self, button_repeat_hz=3, event=None):
        self.spi = spidev.SpiDev()
        # open /dev/spidev0.1
        self.spi.open(0, 1)
        # minimal Serial clock cycle for Write (TSCYCW) is 16 ns, which
        # gives us a maximum of 62.5 MHz; set the transfer speed a bit lower
        # than that
        self.spi.max_speed_hz = 60000000

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BCM_LCD_DCX, GPIO.OUT)
        GPIO.setup(BCM_LCD_BACKLIGHT, GPIO.OUT)
        # the buttons connect to ground when pressed; need to configure
        # with pull up resistors
        GPIO.setup(tuple(button_map.keys()), GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.reset()

        self._repeat_delay = 1.0 / button_repeat_hz
        self._user_event = event
        # The RPi.GPIO software debouncing (bouncetime parameter) is not
        # working well. It also doesn't handle key releases that are needed
        # to detect continuous hold of a button. We're implementing own
        # debouncing instead, using the RPi.GPIO interrupt only as a trigger
        # for a custom thread handling the debouncing. As such, we trigger
        # the interrupt on both edges.
        self._button_state = { k: 0 for k in button_map }
        self._button_reads = { k: 0 for k in button_map }
        self._button_interrupt = threading.Event()
        self._button_debouncer_thread = threading.Thread(target=self._button_debouncer)
        self._button_debouncer_thread.daemon = True
        self._button_debouncer_thread.start()
        for pin in button_map:
            GPIO.add_event_detect(pin, GPIO.BOTH, lambda pin: self._button_interrupt.set())


    def _command(self, cmd, data=None):
        GPIO.output(BCM_LCD_DCX, 0)
        # need 10 ns delay for C/DX setup time (TDCS) but that's of no
        # concern as Python on Pi is not that fast
        self.spi.writebytes((cmd,))
        if data:
            GPIO.output(BCM_LCD_DCX, 1)
            # another 10 ns delay here
            self.spi.writebytes2(data)


    def _button_set(self, pin, pressed):
        prev_pressed = self._button_state[pin] > 0
        if not pressed and not prev_pressed:
            return
        if pressed:
            now = time.time()
            if prev_pressed and self._button_state[pin] + self._repeat_delay > now:
                return
            self._button_state[pin] = now
        else:
            self._button_state[pin] = 0
            prev_pressed = False
        if self._user_event:
            self._user_event(button_map[pin], int(pressed) + int(prev_pressed))


    def _button_debouncer(self):
        while True:
            # calculate the expected timeout to report the next hold key
            # event; None if no keys are pressed
            timeout = None
            for t in self._button_state.values():
                if t > 0 and (not timeout or t + self._repeat_delay < timeout):
                    timeout = t + self._repeat_delay
            if timeout:
                timeout = max(timeout - time.time(), 0)
            self._button_interrupt.wait(timeout)
            for pin in button_map:
                self._button_reads[pin] = 0
            while True:
                done = 0
                for pin in self._button_reads:
                    self._button_reads[pin] = self._button_reads[pin] << 1 & 0xff \
                                            | 0x10 | GPIO.input(pin)
                    if self._button_reads[pin] == 0xf0:
                        # 4+ consecutive reads of zeroes
                        self._button_set(pin, True)
                        done += 1
                    elif self._button_reads[pin] == 0xff:
                        # 4+ consecutive reads of ones
                        self._button_set(pin, False)
                        done += 1
                if done == len(self._button_reads):
                    break
                # sleep for 5 ms, ignoring any interrupts that come meanwhile
                time.sleep(.005)
                self._button_interrupt.clear()


    def set_user_event(self, event):
        self._user_event = event


    def reset(self):
        self.backlight(False)
        self._command(SWRESET)
        # when the display is in sleep mode, it needs up to 120 ms to reset
        time.sleep(0.120)

        # set normal display orientation and RGB order
        self._command(MADCTL, b'\x00')
        # set 6 bits per color
        self._command(COLMOD, b'\x66')
        # set inverse mode
        self._command(INVON)

        # set view range: columns 0 to WIDTH-1, rows 0 to HEIGHT-1
        # parameters to CASET are: start column (high), start column (low),
        # end column (high), end column (low)
        self._command(CASET, (0, 0, (WIDTH - 1) >> 8, (WIDTH - 1) & 0xff))
        # parameters to RASET are: start row (high), start row (low),
        # end row (high), end row (low)
        self._command(RASET, (0, 0, (HEIGHT - 1) >> 8, (HEIGHT - 1) & 0xff))

        self.sleeping = True


    def sleep(self):
        if self.sleeping:
            return
        self.backlight(False)
        self._command(DISPOFF)
        self._command(SLPIN)
        # need 5 ms for supply voltage and clock to stabilize
        time.sleep(0.005)
        self.sleeping = True


    def wake(self):
        if not self.sleeping:
            return
        self._command(SLPOUT)
        # need 120 ms to wake up
        time.sleep(0.120)
        self._command(DISPON)
        self.backlight(True)
        self.sleeping = False


    def backlight(self, on=True):
        GPIO.output(BCM_LCD_BACKLIGHT, on)


    def show(self, data):
        self._command(RAMWR, data)
