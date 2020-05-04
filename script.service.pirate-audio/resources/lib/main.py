# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2020 Jiri Benc <jbenc@upir.cz>

import xbmc
import piratedisplay
import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageFont, PIL.ImageEnhance
import json, os, time


class RpcError(Exception):
    pass


class PirateAddon(xbmc.Monitor):
    def __init__(self):
        super(PirateAddon, self).__init__()
        self.font_title = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
                                                 30)
        self.font_sub = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf',
                                               30)
        self.blank = PIL.Image.new('RGB', (piratedisplay.WIDTH, piratedisplay.HEIGHT),
                                   color=(0, 0, 0))
        self.img_bg = None
        self.img_info = None
        self.img_popup = None
        self.img_popup_timer = None
        self.disp = piratedisplay.PirateDisplay(button_repeat_hz=5, event=self.button_event)


    def json_call(self, method, **kwargs):
        res = xbmc.executeJSONRPC(json.dumps({ 'jsonrpc': '2.0',
                                               'method': method,
                                               'params': kwargs,
                                               'id': 1 }))
        res = json.loads(res)
        if 'error' in res:
            raise RpcError(res['error']['message'])
        return res['result']


    def new_background(self, path=None, brightness=None, quadrant=None):
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
        self.img_bg = res
        self.redraw()


    def new_overlay(self, timeout=None):
        img = PIL.Image.new('RGBA', (piratedisplay.WIDTH, piratedisplay.HEIGHT),
                            color=(0, 0, 0, 0))
        if timeout:
            self.img_popup = img
            if self.img_popup_timer is not None:
                self.disp.del_user_timer(self.img_popup_timer)
            self.img_popup_timer = self.disp.add_user_timer(timeout, self.delete_popup)
        else:
            self.img_info = img
        return PIL.ImageDraw.Draw(img)


    def delete_popup(self, timer_id=None):
        self.img_popup = None
        self.redraw()


    def hide(self):
        self.img_bg = None
        self.img_info = None
        self.redraw()


    def redraw(self):
        if not self.img_bg and not self.img_info and not self.img_popup:
            self.disp.sleep()
            return
        src = self.img_bg or self.blank
        if self.img_info or self.img_popup:
            src = src.copy()
        if self.img_info:
            src.paste(self.img_info, mask=self.img_info)
        if self.img_popup:
            src.paste(self.img_popup, mask=self.img_popup)
        self.disp.show(src.tobytes())
        self.disp.wake()


    def onNotification(self, sender, method, data):
        super(PirateAddon, self).onNotification(sender, method, data)
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

            draw = self.new_overlay()
            draw.text((0, 0), title, font=self.font_title, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            draw.text((0, 30), artist, font=self.font_sub, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            self.new_background(icon, 0.2)
        elif method == 'Player.OnStop':
            self.hide()


    def button_event(self, button, state):
        if os.path.exists('/tmp/piratekodiview'):
            if state == 0:
                return
            if state == 2:
                self.disp.sleep()
                return
            self.disp.show(self.blank.tobytes())
            self.disp.wake()
            filename = '/tmp/screenshot.png'
            try:
                os.unlink(filename)
            except OSError:
                pass
            xbmc.executebuiltin('TakeScreenshot({},sync)'.format(filename))
            while not os.path.exists(filename):
                time.sleep(0.1)
            self.img_info = None
            self.new_background(filename, quadrant={ 'A':(0,0), 'B':(0,1), 'X':(1,0), 'Y':(1,1) }[button])
            return
        if button in ('X', 'Y'):
            if state == 0:
                return
            volume = self.json_call('Application.GetProperties', properties=['volume'])['volume']
            if button == 'X':
                volume = min(100, volume + 5)
            else:
                volume = max(0, volume - 5)
            xbmc.executebuiltin('SetVolume({})'.format(volume))
            draw = self.new_overlay(timeout=5)
            draw.rectangle((piratedisplay.WIDTH - 10, 0,
                            piratedisplay.WIDTH - 1, piratedisplay.HEIGHT - 1),
                           outline=(255, 255, 255), width=1)
            y = (piratedisplay.HEIGHT - 2) * (100 - volume) // 100
            draw.rectangle((piratedisplay.WIDTH - 9, y + 1,
                            piratedisplay.WIDTH - 2, piratedisplay.HEIGHT - 2),
                           fill=(0, 255, 0))
            self.redraw()


addon = PirateAddon()
addon.waitForAbort()
