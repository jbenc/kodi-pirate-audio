# SPDX-License-Identifier: GPL-2.0-or-later

import xbmc
import piratedisplay
import PIL, PIL.Image, PIL.ImageDraw, PIL.ImageFont, PIL.ImageEnhance

class PirateMonitor(xbmc.Monitor):
    def __init__(self):
        super(PirateMonitor, self).__init__()
        self.disp = piratedisplay.PirateDisplay()
        self.font_title = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
                                                 30)
        self.font_sub = PIL.ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf',
                                               30)

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

            img = PIL.Image.new('RGB', (piratedisplay.WIDTH, piratedisplay.HEIGHT),
                                color=(0, 0, 0))
            if icon:
                try:
                    img_icon = PIL.Image.open(icon)
                    img_icon.thumbnail((piratedisplay.WIDTH, piratedisplay.HEIGHT))
                    img.paste(img_icon, box=((piratedisplay.WIDTH - img_icon.width) // 2,
                                             (piratedisplay.HEIGHT - img_icon.height) // 2))
                    del img_icon
                    enh = PIL.ImageEnhance.Brightness(img)
                    img = enh.enhance(0.2)
                    del enh
                except IOError:
                    pass
            draw = PIL.ImageDraw.Draw(img)
            draw.text((0, 0), title, font=self.font_title, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            draw.text((0, 30), artist, font=self.font_sub, fill=(255, 255, 255), stroke_fill=(0, 0, 0))
            self.disp.show(img.tobytes())
            self.disp.wake()
            del draw
            del img
        elif method == 'Player.OnStop':
            self.disp.sleep()

monitor = PirateMonitor()
monitor.waitForAbort()
