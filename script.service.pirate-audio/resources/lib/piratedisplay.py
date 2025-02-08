# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2020 Jiri Benc <jbenc@upir.cz>

import RPi.GPIO as GPIO
import spidev
import threading
import time

width = 240
height = 240

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
button_map_90 = {
    BCM_BUTTON_A: 'B',
    BCM_BUTTON_B: 'Y',
    BCM_BUTTON_X: 'A',
    BCM_BUTTON_Y: 'X',
    BCM_BUTTON_Y2: 'X',
}


class PirateDisplay:
    def __init__(self, button_repeat_hz=3, event=None, rotate=0):
        # we currently support only rotate=0 and rotate=90
        self.rotate = rotate
        self.button_map = button_map_90 if rotate == 90 else button_map
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
        GPIO.setup(tuple(self.button_map.keys()), GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.reset()

        self._repeat_delay = 1.0 / button_repeat_hz
        self._user_event = event
        self._user_timers = []
        self._next_user_timer = None
        self._last_user_timer_id = 0
        self._user_timer_lock = threading.Lock()
        # The RPi.GPIO software debouncing (bouncetime parameter) is not
        # working well. It also doesn't handle key releases that are needed
        # to detect continuous hold of a button. We're implementing own
        # debouncing instead, using the RPi.GPIO interrupt only as a trigger
        # for a custom thread handling the debouncing. As such, we trigger
        # the interrupt on both edges.
        self._button_state = { k: 0 for k in self.button_map }
        self._button_reads = { k: 0 for k in self.button_map }
        self._button_interrupt = threading.Event()
        self._button_debouncer_thread = threading.Thread(target=self._button_debouncer)
        self._button_debouncer_thread.daemon = True
        self._button_debouncer_thread.start()
        for pin in self.button_map:
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
            self._user_event(self.button_map[pin], int(pressed) + int(prev_pressed))


    def _button_debouncer(self):
        while True:
            # calculate the expected timeout to report the next hold key
            # event; None if no keys are pressed
            timeout = None
            for t in self._button_state.values():
                if t > 0 and (not timeout or t + self._repeat_delay < timeout):
                    timeout = t + self._repeat_delay
            # mix in user timers
            t = self._next_user_timer
            if t:
                if not timeout or t < timeout:
                    timeout = t
            if timeout:
                timeout = max(timeout - time.time(), 0)
            self._button_interrupt.wait(timeout)

            # fire user timers if needed
            if self._user_timers:
                self._user_timer_lock.acquire()
                cur_time = time.time()
                fire_timers = []
                new_timers = []
                new_next = None
                for t in self._user_timers:
                    include = True
                    if cur_time >= t[0]:
                        fire_timers.append(t)
                        if t[1]:
                            t[0] += t[1]
                        else:
                            include = False
                    if include:
                        new_timers.append(t)
                        if new_next is None or t[0] < new_next:
                            new_next = t[0]
                self._next_user_timer = new_next
                self._user_timers = new_timers
                self._user_timer_lock.release()
                for t in fire_timers:
                    t[3](t[2], *t[4], **t[5])

            for pin in self.button_map:
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


    def _add_user_timer(self, recurrent, secs, event, args, kwargs):
        t = time.time() + secs
        self._user_timer_lock.acquire()
        self._last_user_timer_id += 1
        timer_id = self._last_user_timer_id
        self._user_timers.append([t, secs if recurrent else 0, timer_id, event, args, kwargs])
        if self._next_user_timer is None or self._next_user_timer > t:
            self._next_user_timer = t
        self._user_timer_lock.release()
        self._button_interrupt.set()
        return timer_id


    def add_user_timer(self, secs, event, *args, **kwargs):
        return self._add_user_timer(False, secs, event, args, kwargs)


    def add_recurrent_user_timer(self, secs, event, *args, **kwargs):
        return self._add_user_timer(True, secs, event, args, kwargs)


    def del_user_timer(self, timer_id):
        self._user_timer_lock.acquire()
        new_timers = []
        new_next = None
        for t in self._user_timers:
            if t[2] != timer_id:
                new_timers.append(t)
                if new_next is None or t[0] < new_next:
                    new_next = t[0]
        self._next_user_timer = new_next
        self._user_timers = new_timers
        self._user_timer_lock.release()


    def reset_user_timer(self, timer_id, secs, event, *args, **kwargs):
        if timer_id is not None:
            updated = False
            wake = False
            new_t = time.time() + secs
            self._user_timer_lock.acquire()
            for t in self._user_timers:
                if t[2] == timer_id:
                    t[0] = new_t
                    t[3] = event
                    t[4] = args
                    t[5] = kwargs
                    updated = True
                    break
            if updated and self._next_user_timer > new_t:
                self._next_user_timer = new_t
                wake = True
            self._user_timer_lock.release()
            if wake:
                self._button_interrupt.set()
            if updated:
                return timer_id
        return self._add_user_timer(False, secs, event, args, kwargs)


    def clear_user_timers(self):
        self._user_timers = []
        self._next_user_timer = None


    def reset(self):
        self.backlight(False)
        self._command(SWRESET)
        # when the display is in sleep mode, it needs up to 120 ms to reset
        time.sleep(0.120)

        # set normal display orientation and RGB order
        self._command(MADCTL, b'\x60' if self.rotate == 90 else b'\x00')
        # set 6 bits per color
        self._command(COLMOD, b'\x66')
        # set inverse mode
        self._command(INVON)

        # set view range: columns 0 to width-1, rows 0 to height-1
        # parameters to CASET are: start column (high), start column (low),
        # end column (high), end column (low)
        self._command(CASET, (0, 0, (width - 1) >> 8, (width - 1) & 0xff))
        # parameters to RASET are: start row (high), start row (low),
        # end row (high), end row (low)
        self._command(RASET, (0, 0, (height - 1) >> 8, (height - 1) & 0xff))

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
        # restore inverse mode; for some reason, sometimes it's not
        # preserved on wakeup
        self._command(INVON)
        self.backlight(True)
        self.sleeping = False


    def backlight(self, on=True):
        GPIO.output(BCM_LCD_BACKLIGHT, on)


    def show(self, data):
        self._command(RAMWR, data)
