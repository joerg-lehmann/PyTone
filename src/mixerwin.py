# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002 Jörg Lehmann <joerg@luga.de>
#
# This file is part of PyTone (http://www.luga.de/pytone/)
#
# PyTone is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2
# as published by the Free Software Foundation.
#
# PyTone is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PyTone; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import errors
import re
import config
import encoding
import events, hub
import log
import statusbar
import window

# two simple abstraction classes for the different mixer types from the oss
# and the ossaudiodev module, respectively.

class ossmixer:
    def __init__(self, device, channel):
        self.mixer = oss.open_mixer(device)
        self.channel = channel
        log.info(_("initialized oss mixer: device %s, channel %s") %
                 (device, channel))

    def get(self):
        return self.mixer.read_channel(self.channel)
        
    def set(self, level):
        self.mixer.write_channel(self.channel, level)


class ossaudiodevmixer:
    def __init__(self, device, channel):
        self.mixer = oss.openmixer(device)
        self.channel = channel
        log.info(_("initialized oss mixer: device %s, channel %s") %
                 (device, channel))


    def get(self):
        return self.mixer.get(self.channel)
        
    def set(self, level):
        self.mixer.set(self.channel, level)


# determine oss module to be used, if any present

try:
    import ossaudiodev as oss
    mixer = ossaudiodevmixer 
except:
    try:
        import oss
        mixer = ossmixer
    except:
        mixer = None
    

class mixerwin(window.window):

    def __init__(self, screen, maxh, maxw, channel):
        self.channel = channel
        self.mixer_device = config.mixer.device
        self.stepsize = config.mixer.stepsize

        channelre = re.compile("SOUND_MIXER_[a-zA-Z0-9]")
        if channelre.match(config.mixer.channel):
            self.mixer_channel = eval("oss.%s" % config.mixer.channel)
        else:
            raise errors.configurationerror("Wrong mixer channel specification: %s" % config.mixer.channel)
        self.mixer = mixer(self.mixer_device, self.mixer_channel)
        self.level = self.mixer.get()
        self.keybindings = config.keybindings.general

        # for identification purposes, we only generate this once
        self.hidewindowevent = events.hidewindow(self)
        
        self.hide()

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.mouseevent, self.mouseevent)
        self.channel.subscribe(events.hidewindow, self.hidewindow)
        self.channel.subscribe(events.focuschanged, self.focuschanged)

    def changevolume(self, change):
        oldlevel = self.mixer.get()
        self.level= ( max(0, min(oldlevel[0]+change, 100)),
                      max(0, min(oldlevel[1]+change, 100)) )
        self.mixer.set(self.level)
        
    # event handler

    def keypressed(self, event):
        key = event.key
        if key in self.keybindings["volumeup"]:
            self.changevolume(self.stepsize)
        elif key in self.keybindings["volumedown"]:
            self.changevolume(-self.stepsize)
        else:
            if self.hasfocus():
                self.hide()
                raise hub.TerminateEventProcessing
            return

        self.update()
        if config.mixerwindow.autoclosetime:
            hub.notify(events.sendeventin(self.hidewindowevent,
                                              config.mixerwindow.autoclosetime,
                                              replace=1))
        
        raise hub.TerminateEventProcessing

    def mouseevent(self, event):
        if self.hasfocus():
            self.hide()
            raise hub.TerminateEventProcessing

    def focuschanged(self, event):
        # we either have focus, or we disappear...
        if not self.hasfocus():
            self.hide()
        else:
            sbar = statusbar.generatedescription("general", "volumedown")
            sbar += statusbar.separator
            sbar += statusbar.generatedescription("general", "volumeup")
            sbar += statusbar.terminate

            hub.notify(events.statusbar_update(0, sbar))

    def update(self):
        self.top()
        window.window.update(self)
        self.addstr(self.iy, self.ix, encoding.encode(_("Volume:")), self.colors.description)
        self.addstr(" %3d " % self.level[0], self.colors.content)
 
        percent = self.barlen*self.level[0]/100
        self.addstr("#"*percent, self.colors.barhigh)
        self.addstr("#"*(self.barlen-percent), self.colors.bar)


class popupmixerwin(mixerwin):

    """ mixer which appears as a popup at the center of the screen """
    
    def __init__(self, screen, maxh, maxw, channel):
        # calculate size and position
        self.barlen = 20
        h = 3
        w = len(_("Volume:")) + 7 + self.barlen
        y = (maxh-h)/2
        x = (maxw-w)/2

        window.window.__init__(self,
                               screen, h, w, y, x,
                               config.colors.mixerwindow,
                               _("Mixer"))
                
        mixerwin.__init__(self, screen, maxh, maxw, channel)

    def resize(self, maxh, maxw):
        h = 3
        w = len(_("Volume:")) + 7 + self.barlen
        y = (maxh-h)/2
        x = (maxw-w)/2
        window.window.resize(self, h, w, y, x)
        
        
class statusbarmixerwin(mixerwin):

    """ mixer which appears in the statusbar """
    
    def __init__(self, screen, maxh, maxw, channel):
        # calculate size and position
        self.barlen = max(0, maxw - len(_("Volume:")) - 5)

        window.window.__init__(self,
                               screen, 1, maxw, maxh-1, 0, config.colors.mixerwindow)
                
        mixerwin.__init__(self, screen, maxh, maxw, channel)

    def resize(self, maxh, maxw):
        window.window.resize(self, 1, maxw, maxh-1, 0)
