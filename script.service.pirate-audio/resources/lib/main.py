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


def center_text(draw, y, text, font, fill=(255, 255, 255)):
    if y is None:
        # center to the whole screen
        y = (piratedisplay.height - sum(font.getmetrics())) // 2
    width = draw.textsize(text, font=font)[0]
    draw.text(((piratedisplay.width - width) // 2, y), text, font=font, fill=fill)


def boxed_text(draw, x, y, halign, text, font, fill=(0xff, 0xff, 0xff), padding=(10, 2)):
    """halign specified horizontal alignment and is 'left', 'right' or
    'center'. Vertical alignment is always center. x and y can be None, in
    which case they refer to the center of the screen."""
    bgfill = (0, 0, 0, 196)
    height = sum(font.getmetrics()) + 2 * padding[1]
    width = draw.textsize(text, font=font)[0] + 2 * padding[0]
    if x is None:
        x = piratedisplay.width // 2
    if y is None:
        y = piratedisplay.height // 2
    y -= height // 2
    if halign == 'right':
        x -= width
    elif halign == 'center':
        x -= width // 2
    draw.rectangle((x, y, x + width - 1, y + height - 1), fill=bgfill)
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
        self.font_symxl = PIL.ImageFont.truetype('/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf',
                                                 100)
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

        self.actions = (
            { 'help': (u'\u23ef', u'\U0001f50a', u'\u23ed', u'\U0001f509'),
              'init': self.notification_play,
              'notification': self.notification_play,
              'button': self.button_event_play },
            { 'help': (u'\u2b09', u'\u2b08', u'\u2b0b', u'\u2b0a'),
              'init': self.screenshot,
              'button': self.button_event_screen },
        )
        self.cur_action = 0
        self.action_switcher = 0

        self.playing = False
        self.paused = False

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


    def new_overlay_info(self, preserve_timer=False):
        if not preserve_timer:
            self.remove_overlay_info()
        img = PIL.Image.new('RGBA', (piratedisplay.width, piratedisplay.height),
                            color=(0, 0, 0, 0))
        self.img_info = img
        return PIL.ImageDraw.Draw(img)


    def new_overlay_popup(self, timeout):
        if self.img_popup_timer is not None:
            self.disp.del_user_timer(self.img_popup_timer)
        img = PIL.Image.new('RGBA', (piratedisplay.width, piratedisplay.height),
                            color=(0, 0, 0, 0))
        self.img_popup = img
        self.img_popup_timer = self.disp.add_user_timer(timeout, self.delete_popup)
        return PIL.ImageDraw.Draw(img)


    def remove_overlay_info(self):
        if self.img_info_timer is not None:
            self.disp.del_user_timer(self.img_info_timer)
            self.img_info_timer = None
        self.img_info = None


    def set_help(self, topleft, topright, bottomleft, bottomright):
        fill = (0xff, 0xee, 0x00)
        draw = self.new_overlay_popup(timeout=8)
        boxed_text(draw, 0, 71, 'left', topleft, self.font_sym, fill)
        boxed_text(draw, 0, piratedisplay.height - 52, 'left', bottomleft, self.font_sym, fill)
        boxed_text(draw, piratedisplay.width - 1, 71, 'right', topright, self.font_sym, fill)
        boxed_text(draw, piratedisplay.width - 1, piratedisplay.height - 52, 'right', bottomright, self.font_sym, fill)


    def delete_popup(self, timer_id=None):
        self.img_popup = None
        self.redraw()


    def hide(self):
        self.remove_overlay_info()
        self.img_bg = None
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

        draw = self.new_overlay_info(preserve_timer=True)
        draw.text((0, 0), artist, font=self.font_sub, fill=(255, 255, 255))
        multiline_text(draw, (0, self.font_title_height), title,
                       font=self.font_title, fill=(255, 255, 255), max_rows=2)
        draw.rectangle((0, piratedisplay.height - self.font_sub_height,
                        progress - 1, piratedisplay.height - 1),
                       fill=(0, 0, 0xb0))
        center_text(draw, piratedisplay.height - self.font_sub_height,
                    '{} / {}'.format(elapsed, duration), font=self.font_sub, fill=(0xb0, 0xb0, 0xb0))

        if self.paused:
            boxed_text(draw, None, None, 'center', u'\u23f8', self.font_symxl)

        if not initial:
            self.redraw()


    def notification_play(self, method=None):
        # method will be None in the case of a fake event after mode switch
        if method is not None and method != 'Player.OnPlay' and method != 'Player.OnStop':
            return
        if self.playing:
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

            self.remove_overlay_info()
            self.new_background(cache, 0.2)
            self.set_playing_info(initial=True)
            self.set_help(u'\u23ef', u'\U0001f50a', u'\u23ed', u'\U0001f509')
            self.redraw()
            self.img_info_timer = self.disp.add_recurrent_user_timer(1, self.set_playing_info)
        else:
            self.hide()


    def screenshot(self, button='A', clear=True):
        if clear:
            self.new_background()
        draw = self.new_overlay_info()
        boxed_text(draw, None, None, 'center', u'\u23f3', self.font_symxl)
        self.redraw()

        filename = '/tmp/screenshot.png'
        try:
            os.unlink(filename)
        except OSError:
            pass
        xbmc.executebuiltin('TakeScreenshot({},sync)'.format(filename))
        while not os.path.exists(filename):
            time.sleep(0.1)
        self.remove_overlay_info()
        self.new_background(filename, quadrant={ 'A':(0,0), 'B':(0,1), 'X':(1,0), 'Y':(1,1) }[button])
        self.redraw()


    def next_action(self):
        self.cur_action += 1
        if self.cur_action >= len(self.actions):
            self.cur_action = 0
        action = self.actions[self.cur_action]
        self.set_help(*action['help'])
        if 'init' in action:
            action['init']()


    def onNotification(self, sender, method, data):
        super(PirateAddon, self).onNotification(sender, method, data)
        if method == 'Player.OnPlay':
            self.playing = True
            self.paused = False
        elif method == 'Player.OnStop':
            self.playing = False
            self.paused = False
        elif method == 'Player.OnPause':
            self.paused = True
        elif method == 'Player.OnResume':
            self.paused = False
        action = self.actions[self.cur_action]
        if 'notification' in action:
            action['notification'](method)


    def button_event(self, button, state):
        # long pressing (> 1 sec) B button always switches actions
        if button == 'B':
            if state == 2:
                if self.action_switcher == 3:
                    self.next_action()
                self.action_switcher += 1
                return
            if state == 0:
                self.action_switcher = 0
        self.actions[self.cur_action]['button'](button, state)


    def button_event_play(self, button, state):
        if button in ('X', 'Y'):
            if state == 0:
                return
            volume = self.json_call('Application.GetProperties', properties=['volume'])['volume']
            if button == 'X':
                volume = min(100, volume + 5)
            else:
                volume = max(0, volume - 5)
            xbmc.executebuiltin('SetVolume({})'.format(volume))
            draw = self.new_overlay_popup(timeout=5)
            draw.rectangle((piratedisplay.width - 10, 0,
                            piratedisplay.width - 1, piratedisplay.height - 1),
                           outline=(255, 255, 255), width=1)
            y = (piratedisplay.height - 2) * (100 - volume) // 100
            draw.rectangle((piratedisplay.width - 9, y + 1,
                            piratedisplay.width - 2, piratedisplay.height - 2),
                           fill=(0, 255, 0))
            self.redraw()
            return
        if state != 1:
            return
        if button == 'A':
            xbmc.executebuiltin('PlayerControl(Play)')
        elif button == 'B':
            xbmc.executebuiltin('PlayerControl(Next)')


    def button_event_screen(self, button, state):
        if state != 1:
            return
        self.screenshot(button, clear=False)


addon = PirateAddon()
addon.waitForAbort()
