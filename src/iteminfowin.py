# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2005 Jörg Lehmann <joerg@luga.de>
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

import config
import item
import services.playlist
import events, hub
import window
import messagewin

# marker class
class _selection:
    pass
selection = _selection()

class iteminfowin(window.window):
    def __init__(self, screen, layout, channel, playerids, player):
        # player for pre-listening
        self.player = player      
        # list of players for which information can be displayed
        self.playerids = [playerid for playerid in playerids if playerid is not None]

        # hash for items (for each view mode)
        self.items = {}
        self.items[selection] = None
        for playerid in self.playerids:
            self.items[playerid] = None

        # currently active view mode
        self.activeview = selection
        self.keybindings = config.keybindings.general

        h, w, y, x, border = layout
        window.window.__init__(self, screen, h, w, y, x,
                               config.colors.iteminfowindow,
                               _("MP3 Info"), border)

        channel.subscribe(events.selectionchanged, self.selectionchanged)
        channel.subscribe(events.songchanged, self.songchanged)
        channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
        channel.subscribe(events.keypressed, self.keypressed)

    def resize(self, layout):
        h, w, y, x, self.border = layout
        window.window.resize(self, h, w, y, x)

    def update(self):
        # update window title
        aitem = self.items[self.activeview]
        title = _("No song")
        if isinstance(aitem, (item.song, services.playlist.playlistitem)):
            if isinstance(aitem, item.song):
                atype = aitem.type
            else:
                atype = aitem.song.type
            if atype == "mp3":
                title = _("MP3 Info")
            elif atype == "ogg":
                title = _("Ogg Info")
            else:
                title = _("Song Info")
        elif isinstance(aitem, item.diritem):
            title = _("Directory Info")
        if self.activeview != selection:
            title = title + " " + _("[Player: %s]") % self.activeview
        self.settitle(title)

        window.window.update(self)

        # get lines to display
        empty= [["", "", "", ""]]
        if aitem:
            info = aitem.getinfo()
        else:
            info = []
        l = info + empty*(4-len(info))

        colsep = self.iw > 45

        # calculate width of columns
        wc1 = max( len(l[0][0]), len(l[1][0]), len(l[2][0]), len(l[3][0])) + colsep
        wc3 = max( len(l[0][2]), len(l[1][2]), len(l[2][2])) + colsep
        wc4 = 5
        wc4 = max( len(l[0][3]), len(l[1][3]), len(l[2][3]))
        wc2 = self.iw-wc1-wc3-wc4-1

        for lno in range(4):
            self.move(1+lno, self.ix)
            self.addstr(l[lno][0].ljust(wc1)[:wc1], self.colors.description)
            self.addstr(l[lno][1].ljust(wc2)[:wc2], self.colors.content)
            self.addch(" ")
            if lno != 3 or isinstance(aitem, item.diritem):
                self.addstr(l[lno][2].ljust(wc3)[:wc3], self.colors.description)
                self.addstr(l[lno][3].ljust(wc4)[:wc4], self.colors.content)
            else:
                # special handling of last line for songs
                wc3 = max(len(l[3][-2]), 5) + colsep
                wc4 = max(len(l[3][-1]), 5)
                
                self.move(1+lno, self.iw-wc3-wc4-1-self.ix)
                self.addch(" ")
                self.addstr(l[3][-2].ljust(wc3)[:wc3], self.colors.description)
                self.addstr(l[3][-1].ljust(wc4)[:wc4], self.colors.content)

    # event handler

    def selectionchanged(self, event):
        if self.player and self.items[selection] != event.item:
            if isinstance(event.item, item.song):
                hub.notify(events.playerplaysong(self.player, event.item))
            elif isinstance(event.item, services.playlist.playlistitem):
                hub.notify(events.playerplaysong(self.player, event.item.song))
        self.items[selection] = event.item
        self.update()

    def songchanged(self, event):
        # needed only for songs, since these can be rated or updated
        # when they are played note that this may update too often (if
        # multiple songdbs are used), but who cares.
        changed = False
        for view, aitem in self.items.items():
            if isinstance(aitem, item.song) and event.songdbid == aitem.songdbid and event.song == aitem:
                aitem.song = event.song
                changed = True
            elif ( isinstance(aitem, services.playlist.playlistitem) and
                   event.songdbid == aitem.song.songdbid and event.song == aitem.song):
                aitem.song.song = event.song
                changed = True
        if changed:
            self.update()

    def playbackinfochanged(self, event):
        playerid = event.playbackinfo.playerid
        if  playerid in self.playerids:
            if event.playbackinfo.song != self.items[playerid]:
                self.items[playerid] = event.playbackinfo.song
                if self.activeview == playerid:
                    self.update()

    def keypressed(self, event):
        key = event.key
        if key in self.keybindings["toggleiteminfowindow"]:
            if self.activeview == selection:
                self.activeview = self.playerids[0]
            else:
                i = self.playerids.index(self.activeview)
                if i < len(self.playerids)-1:
                    self.activeview = self.playerids[i+1]
                else:
                    self.activeview = selection
        else:
            return
        self.update()
        raise hub.TerminateEventProcessing


class iteminfowinlong(messagewin.messagewin):

    def __init__(self, screen, maxh, maxw, channel):
        messagewin.messagewin.__init__(self, screen, maxh, maxw, channel,
                                       config.colors.iteminfolongwindow,
                                       _("Item info"), [],
                                       config.iteminfolongwindow.autoclosetime)

        self.item = None

        channel.subscribe(events.selectionchanged, self.selectionchanged)

    def _outputlen(self, width):
        return 15

    def showitems(self):
        # get lines to display
        empty= [["", "", "", ""]]
        if self.item:
            info = self.item.getinfolong()
        else:
            info = []
        l = info + empty*(4-len(info))

        colsep = self.iw > 45

        # calculate width of columns
        wc1 = 0
        wc3 = 0
        for line in info:
            wc1 = max(wc1, len(line[0]))
            wc3 = max(wc3, len(line[2]))
        wc1 += colsep
        wc3 += colsep
        wc4 = 0
        wc2 = self.iw-wc1-wc3-wc4-1
        self.clear()
        for lno in range(len(info)):
            line = l[lno]
            self.move(self.iy+lno, self.ix)
            self.addstr(line[0].ljust(wc1)[:wc1], self.colors.description)
            self.addstr(line[1].ljust(wc2)[:wc2], self.colors.content)
            self.addch(" ")
            if lno!=self.ih:
                self.addstr(line[2].ljust(wc3)[:wc3], self.colors.description)
                self.addstr(line[3].ljust(wc4)[:wc4], self.colors.content)
            else:
                # special handling of last line
                wc3 = max(len(line[-2]), 5) + colsep
                wc4 = max(len(line[-1]), 5)
                
                self.move(1+lno, self.iw-wc3-wc4-1-self.ix)
                self.addch(" ")
                self.addstr(line[-2].ljust(wc3)[:wc3], self.colors.description)
                self.addstr(line[-1].ljust(wc4)[:wc4], self.colors.content)

    def selectionchanged(self, event):
        self.item = event.item
