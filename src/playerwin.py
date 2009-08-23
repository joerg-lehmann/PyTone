# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003 Jörg Lehmann <joerg@luga.de>
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

import os
import config
import log
import window
import events, hub
import statusbar
import encoding

from helper import formattime

class playerwin(window.window):
    def __init__(self, screen, layout, channel, playerid):
        self.song = None
        self.time = 0
        self.paused = 0
        self.stopped = 1
        self.playerid = playerid
        self.keybindings = config.keybindings.general
        self.songformat = config.playerwindow.songformat
        self.playerinfofile = config.general.playerinfofile
        self.songchangecommand = config.general.songchangecommand.strip()
        if self.songchangecommand:
            self.songchangecommand = "( %s )&" % self.songchangecommand
        h, w, y, x, border = layout
        window.window.__init__(self, screen, h, w, y, x,
                               config.colors.playerwindow,
                               _("Playback Info"), border)
	try:
            self.playerinfofd = open(self.playerinfofile, "w")
        except IOError, e:
            log.error(_("error '%s' occured during write to playerinfofile") % e)
            self.playerinfofd = None
        # we don't want to have the focus
        self.panel.bottom()

        channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
        channel.subscribe(events.keypressed, self.keypressed)
        self.update()

    def resize(self, layout):
        h, w, y, x, self.border = layout
        window.window.resize(self, h, w, y, x)

    def updatestatusbar(self):
        if self.song and not self.paused and self.keybindings["playerpause"]:
            sbar = statusbar.generatedescription("general", "playerpause")
        else:
            sbar = statusbar.generatedescription("general", "playerstart")
        hub.notify(events.statusbar_update(1, sbar))
        
    def update(self):
        window.window.update(self)
        self.updatestatusbar()
        self.addstr(1, self.ix, " "*self.iw)
        if self.song:
            self.move(1, self.ix)
            s1 = _("Time:")
            s2 = " %s/%s " % (formattime(self.time), formattime(self.song.length))
            self.addstr(s1, self.colors.description)
            self.addstr(s2, self.colors.content)

            if not self.paused:
                barlen = self.iw-len(s1)-len(s2)
                try:
                    percentplayed = int(barlen*self.time/self.song.length)
                except ZeroDivisionError:
                    percentplayed = 0
                self.addstr("#"*(percentplayed), self.colors.progressbarhigh)
                self.addstr("#"*(barlen-percentplayed), self.colors.progressbar)
            else:
                self.addstr(_("paused"), self.colors.description)

    # event handler

    def playbackinfochanged(self, event):
        if event.playbackinfo.playerid == self.playerid:
            if self.song != event.playbackinfo.song and event.playbackinfo.song and self.songchangecommand:
                os.system(event.playbackinfo.song.format(self.songchangecommand, safe=True))
            self.song = event.playbackinfo.song
            self.paused = event.playbackinfo.ispaused()
            self.stopped = event.playbackinfo.isstopped()
            if self.song:
                self.settitle(u"%s%s" % (event.playbackinfo.iscrossfading() and "-> " or "", self.song.format(self.songformat)))
            else:
                self.settitle(_("Playback Info"))
            self.time = event.playbackinfo.time
            self.update()

            # update player info file, if configured
            if self.playerinfofd:
                try:
                    self.playerinfofd.seek(0)
                    if self.song:
                        info = "%s - %s (%s/%s)\n"  % ( self.song.artist,
                                                        self.song.title,
                                                        formattime(self.time),
                                                        formattime(self.song.length))
                    else:
                        info = _("Not playing") + "\n"
                    info = encoding.encode(info)
                    self.playerinfofd.write(info)
                    self.playerinfofd.truncate(len(info))
                except IOError, e:
                    log.error(_("error '%s' occured during write to playerinfofile") % e)
                    self.playerinfofd = None

    def keypressed(self, event):
        key = event.key
        if key in self.keybindings["playerstart"] and self.paused:
            hub.notify(events.playerstart(self.playerid))
        elif key in self.keybindings["playerpause"] and not self.paused and not self.stopped:
            hub.notify(events.playerpause(self.playerid))
        elif key in self.keybindings["playerstart"]:
            hub.notify(events.playerstart(self.playerid))
        elif key in self.keybindings["playernextsong"]:
            hub.notify(events.playernext(self.playerid))
        elif key in self.keybindings["playerprevioussong"]:
            hub.notify(events.playerprevious(self.playerid))
        elif key in self.keybindings["playerrewind"]:
            hub.notify(events.playerseekrelative(self.playerid, -2))
        elif key in self.keybindings["playerforward"]:
            hub.notify(events.playerseekrelative(self.playerid, 2))
        elif key in self.keybindings["playerstop"]:
            hub.notify(events.playerstop(self.playerid))
        elif key in self.keybindings["playerplayfaster"]:
            hub.notify(events.playerplayfaster(self.playerid))
        elif key in self.keybindings["playerplayslower"]:
            hub.notify(events.playerplayslower(self.playerid))
        elif key in self.keybindings["playerspeedreset"]:
            hub.notify(events.playerspeedreset(self.playerid))
        elif key in self.keybindings["playerratecurrentsong1"]:
            if self.song:
                self.song.rate(1)
        elif key in self.keybindings["playerratecurrentsong2"]:
            if self.song:
                self.song.rate(2)
        elif key in self.keybindings["playerratecurrentsong3"]:
            if self.song:
                self.song.rate(3)
        elif key in self.keybindings["playerratecurrentsong4"]:
            if self.song:
                self.song.rate(4)
        elif key in self.keybindings["playerratecurrentsong5"]:
            if self.song:
                self.song.rate(5)
        else:
            return
        raise hub.TerminateEventProcessing

