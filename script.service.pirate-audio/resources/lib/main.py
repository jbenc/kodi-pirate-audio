# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2020 Jiri Benc <jbenc@upir.cz>

import xbmc
import piratedisplay
import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageFont, PIL.ImageEnhance
import json, os, time


def multiline_text(draw, xy, text, font, fill, spacing=0, max_rows=None):
    row = 0
    x, y = xy
    height = sum(font.getmetrics()) + spacing
    words = text.split()
    words.reverse()
    while words and (max_rows is None or row < max_rows):
        line = []
        while words:
            line.append(words.pop())
            width = draw.textsize(' '.join(line), font=font)[0]
            if width > piratedisplay.width and len(line) > 1:
                words.append(line.pop())
                break
        draw.text((x, y), ' '.join(line), font=font, fill=fill)
        y += height
        row += 1


def center_text(draw, y, text, font, fill):
    width = draw.textsize(text, font=font)[0]
    draw.text(((piratedisplay.width - width) // 2, y), text, font=font, fill=fill)


def boxed_text(draw, x, y, right_align, text, font, fill=(0xff, 0xee, 0x00), padding=(10, 2)):
    bgfill = (0, 0, 0, 196)
    height = sum(font.getmetrics()) + 2 * padding[1]
    width = draw.textsize(text, font=font)[0] + 2 * padding[0]
    y -= height // 2
    if right_align:
        x -= width
    x2 = x + width
    y2 = y + height
    draw.rectangle((x, y, x2 - 1, y2 - 1), fill=bgfill)
    draw.text((x + padding[0], y + padding[1]), text, font=font, fill=fill)


class RpcError(Exception):
    pass


class PirateAddon(xbmc.Monitor):
    def __init__(self):
        super(PirateAddon, self).__init__()
        self.font_title = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
                                                 30)
        self.font_sub = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf',
                                               30)
        self.font_sym = PIL.ImageFont.truetype('/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf',
                                               32)
        self.font_title_height = sum(self.font_title.getmetrics())
        self.font_sub_height = sum(self.font_sub.getmetrics())

        self.blank = PIL.Image.new('RGB', (piratedisplay.width, piratedisplay.height),
                                   color=(0, 0, 0))
        self.img_bg = None
        self.img_bg_cache = None
        self.img_info = None
        self.img_popup = None
        self.img_info_timer = None
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
        if path and not quadrant and self.img_bg_cache and self.img_bg_cache[:2] == (path, brightness):
            # the image is unchanged, use the cached version
            self.img_bg = self.img_bg_cache[2]
            return

        res = PIL.Image.new('RGB', (piratedisplay.width, piratedisplay.height),
                            color=(0, 0, 0))
        if path:
            try:
                img = PIL.Image.open(path)
                width = piratedisplay.width
                height = piratedisplay.height
                if quadrant:
                    width *= 2
                    height *= 2
                img.thumbnail((width, height))
                if not quadrant:
                    # centered
                    x = (width - img.width) // 2
                    y = (height - img.height) // 2
                else:
                    x = quadrant[0] * -piratedisplay.width
                    y = quadrant[1] * -piratedisplay.height
                res.paste(img, box=(x, y))
                del img
            except IOError:
                pass
            if brightness:
                enh = PIL.ImageEnhance.Brightness(res)
                res = enh.enhance(brightness)
        self.img_bg = res
        self.img_bg_cache = (path, brightness, res)


    def new_overlay(self, timeout=None):
        img = PIL.Image.new('RGBA', (piratedisplay.width, piratedisplay.height),
                            color=(0, 0, 0, 0))
        if timeout:
            self.img_popup = img
            if self.img_popup_timer is not None:
                self.disp.del_user_timer(self.img_popup_timer)
            self.img_popup_timer = self.disp.add_user_timer(timeout, self.delete_popup)
        else:
            self.img_info = img
        return PIL.ImageDraw.Draw(img)


    def set_help(self, topleft, topright, bottomleft, bottomright):
        draw = self.new_overlay(timeout=10)
        boxed_text(draw, 0, 71, False, topleft, self.font_sym)
        boxed_text(draw, 0, piratedisplay.height - 52, False, bottomleft, self.font_sym)
        boxed_text(draw, piratedisplay.width - 1, 71, True, topright, self.font_sym)
        boxed_text(draw, piratedisplay.width - 1, piratedisplay.height - 52, True, bottomright, self.font_sym)


    def delete_popup(self, timer_id=None):
        self.img_popup = None
        self.redraw()


    def hide(self):
        if self.img_info_timer is not None:
            self.disp.del_user_timer(self.img_info_timer)
            self.img_info_timer = None
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


    def set_playing_info(self, timer_id=None, initial=False):

        def to_secs(s):
            res = 0
            try:
                for t in s.split(':'):
                    res = res * 60 + int(t)
            except ValueError:
                return 0
            return res

        duration = xbmc.getInfoLabel('Player.Duration')
        if initial:
            # when changing songs, Kodi returns old data for duration,
            # workaround that
            elapsed = ':'.join(['00'] * len(duration.split(':')))
        else:
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

        # there's 'Player.Progress' infolabel but it always returns an empty
        # string, calculate the progress manually. While doing so, normalize
        # to pixels instead of per cent:
        progress = 0
        duration_secs = to_secs(duration)
        if duration_secs:
            progress = to_secs(elapsed) * piratedisplay.width // duration_secs

        draw = self.new_overlay()
        draw.text((0, 0), artist, font=self.font_sub, fill=(255, 255, 255))
        multiline_text(draw, (0, self.font_title_height), title,
                       font=self.font_title, fill=(255, 255, 255), max_rows=2)
        draw.rectangle((0, piratedisplay.height - self.font_sub_height,
                        progress - 1, piratedisplay.height - 1),
                       fill=(0, 0, 0xb0))
        center_text(draw, piratedisplay.height - self.font_sub_height,
                    '{} / {}'.format(elapsed, duration), font=self.font_sub, fill=(0xb0, 0xb0, 0xb0))

        if not initial:
            self.redraw()


    def onNotification(self, sender, method, data):
        super(PirateAddon, self).onNotification(sender, method, data)
        if method == 'Player.OnPlay':
            cache = None
            icon = xbmc.getInfoLabel('Player.Art(thumb)')
            if icon:
                cache = self.json_call('Textures.GetTextures',
                                       properties=['cachedurl'],
                                       filter={'field': 'url', 'operator': 'is',
                                               'value': icon})['textures']
                if cache:
                    cache = xbmc.translatePath('special://thumbnails/' + cache[0]['cachedurl'])
                elif icon.startswith('/'):
                    # if the icon is not cached, we can use it directly if
                    # it's on a local filesystem
                    cache = icon
                else:
                    # for all other cases, we go with no icon (assign None
                    # instead of the [])
                    cache = None

            self.new_background(cache, 0.2)
            self.set_playing_info(initial=True)
            self.set_help(u'\u23ef', u'\U0001f50a', u'\u23ed', u'\U0001f509')
            self.redraw()
            if self.img_info_timer is not None:
                self.disp.del_user_timer(self.img_info_timer)
            self.img_info_timer = self.disp.add_recurrent_user_timer(1, self.set_playing_info)
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
            self.redraw()
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
            draw.rectangle((piratedisplay.width - 10, 0,
                            piratedisplay.width - 1, piratedisplay.height - 1),
                           outline=(255, 255, 255), width=1)
            y = (piratedisplay.height - 2) * (100 - volume) // 100
            draw.rectangle((piratedisplay.width - 9, y + 1,
                            piratedisplay.width - 2, piratedisplay.height - 2),
                           fill=(0, 255, 0))
            self.redraw()


addon = PirateAddon()
addon.waitForAbort()
