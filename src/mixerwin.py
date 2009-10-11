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
# and the ossaudiodev module, as well as the internal mixer

class ossmixer:
    def __init__(self, device, channel):
        self.mixer = oss.open_mixer(device)
        self.channel = channel
        log.info(_("initialized oss mixer: device %s, channel %s") %
                 (device, channel))

    def get(self):
        return self.mixer.read_channel(self.channel)

    def adjust(self, level_adjust):
        oldlevel = self.get()
        self.mixer.write_channel(self.channel, (max(0, min(oldlevel[0]+level_adjust, 100)),
                                                max(0, min(oldlevel[1]+level_adjust, 100)) ) )

class ossaudiodevmixer:
    def __init__(self, device, channel):
        self.mixer = oss.openmixer(device)
        self.channel = channel
        log.info(_("initialized oss mixer: device %s, channel %s") %
                 (device, channel))

    def get(self):
        return self.mixer.get(self.channel)


    def adjust(self, level_adjust):
        oldlevel = self.get()
        self.mixer.set(self.channel, (max(0, min(oldlevel[0]+level_adjust, 100)),
                                      max(0, min(oldlevel[1]+level_adjust, 100)) ) )

class internalmixer:
    def __init__(self, playerid):
        self.playerid = playerid
        self.volume = 1
        log.info(_("initialized internal mixer: player %s") % playerid)

    def get(self):
        return [self.volume*100, self.volume*100]

    def adjust(self, level_adjust):
        hub.notify(events.player_change_volume_relative(self.playerid, level_adjust))



# determine oss module to be used, if any present

try:
    import ossaudiodev as oss
    externalmixer = ossaudiodevmixer 
except:
    try:
        import oss
        externalmixer = ossmixer
    except:
        externalmixer = None
    

class mixerwin(window.window):

    def __init__(self, screen, maxh, maxw, channel):
        self.channel = channel
        if config.mixer.type == "external":
            if externalmixer is not None:
                mixer_device = config.mixer.device
                channelre = re.compile("SOUND_MIXER_[a-zA-Z0-9]")
                if channelre.match(config.mixer.channel):
                    mixer_channel = eval("oss.%s" % config.mixer.channel)
                else:
                    raise errors.configurationerror("Wrong mixer channel specification: %s" % config.mixer.channel)
                self.mixer = externalmixer(mixer_device, mixer_channel)
            else:
                 self.mixer = internalmixer("main")
                 log.warning("Could not initialize external mixer, using internal one")
        elif config.mixer.type == "internal":
            self.mixer = internalmixer("main")
        else:
            self.mixer = None
        self.stepsize = config.mixer.stepsize

        if self.mixer:
            self.level = self.mixer.get()
        else:
            self.level = None
        self.keybindings = config.keybindings.general

        # for identification purposes, we only generate this once
        self.hidewindowevent = events.hidewindow(self)

        self.hide()

        if self.mixer:
            self.channel.subscribe(events.keypressed, self.keypressed)
            self.channel.subscribe(events.mouseevent, self.mouseevent)
            self.channel.subscribe(events.hidewindow, self.hidewindow)
            self.channel.subscribe(events.focuschanged, self.focuschanged)
        if isinstance(self.mixer, internalmixer):
            self.channel.subscribe(events.player_volume_changed, self.player_volume_changed)


    def changevolume(self, change):
        if self.mixer:
            self.mixer.adjust(change)

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

    def player_volume_changed(self, event):
        if isinstance(self.mixer, internalmixer) and event.playerid==self.mixer.playerid:
            self.mixer.volume = event.volume
            if self.hasfocus():
                self.update()

    def update(self):
        self.level = self.mixer.get()
        self.top()
        window.window.update(self)
        self.addstr(self.iy, self.ix, encoding.encode(_("Volume:")), self.colors.description)
        self.addstr(" %3d " % round(self.level[0]), self.colors.content)
 
        percent = int(round(self.barlen*self.level[0]/100))
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
