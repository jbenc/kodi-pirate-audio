# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2020 Jiri Benc <jbenc@upir.cz>

import xbmc
import piratedisplay
import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageFont, PIL.ImageEnhance
import os, time

class PirateMonitor(xbmc.Monitor):
    def __init__(self):
        super(PirateMonitor, self).__init__()
        self.disp = piratedisplay.PirateDisplay(event=self.button_event)
        self.font_title = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
                                                 30)
        self.font_sub = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf',
                                               30)


    def new_img(self, path=None, brightness=None, quadrant=None):
        res = PIL.Image.new('RGB', (piratedisplay.WIDTH, piratedisplay.HEIGHT),
                            color=(0, 0, 0))
        if path:
            try:
                img = PIL.Image.open(path)
                width = piratedisplay.WIDTH
                height = piratedisplay.HEIGHT
                if quadrant:
                    width *= 2
                    height *= 2
                img.thumbnail((width, height))
                if not quadrant:
                    # centered
                    x = (width - img.width) // 2
                    y = (height - img.height) // 2
                else:
                    x = quadrant[0] * -piratedisplay.WIDTH
                    y = quadrant[1] * -piratedisplay.HEIGHT
                res.paste(img, box=(x, y))
                del img
            except IOError:
                pass
            if brightness:
                enh = PIL.ImageEnhance.Brightness(res)
                res = enh.enhance(brightness)
                del enh
        return res


    def onNotification(self, sender, method, data):
        super(PirateMonitor, self).onNotification(sender, method, data)
        if method == 'Player.OnPlay':
            icon = xbmc.getInfoLabel('Player.Art(thumb)')
            duration = xbmc.getInfoLabel('Player.Duration')
            elapsed = xbmc.getInfoLabel('Player.Time')
            title = xbmc.getInfoLabel('Player.Title')
            artist = xbmc.getInfoLabel('MusicPlayer.Artist')
            album = xbmc.getInfoLabel('MusicPlayer.Album')
            try:
                # Python 2
                title = title.decode('utf-8', 'ignore')
                artist = artist.decode('utf-8', 'ignore')
                album = album.decode('utf-8', 'ignore')
            except AttributeError:
                # Python 3
                pass

            img = self.new_img(icon, 0.2)
            draw = PIL.ImageDraw.Draw(img)
            draw.text((0, 0), title, font=self.font_title, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            draw.text((0, 30), artist, font=self.font_sub, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            self.disp.show(img.tobytes())
            self.disp.wake()
            del draw
            del img
        elif method == 'Player.OnStop':
            self.disp.sleep()


    def button_event(self, button, state):
        if os.path.exists('/tmp/piratekodiview'):
            if state == 0:
                return
            if state == 2:
                self.disp.sleep()
                return
            self.disp.show(self.new_img().tobytes())
            self.disp.wake()
            filename = '/tmp/screenshot.png'
            try:
                os.unlink(filename)
            except OSError:
                pass
            xbmc.executebuiltin('TakeScreenshot({},sync)'.format(filename))
            while not os.path.exists(filename):
                time.sleep(0.1)
            img = self.new_img(filename, quadrant={ 'A':(0,0), 'B':(0,1), 'X':(1,0), 'Y':(1,1) }[button])
            self.disp.show(img.tobytes())
            del img


monitor = PirateMonitor()
monitor.waitForAbort()
