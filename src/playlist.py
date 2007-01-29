# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004 Jörg Lehmann <joerg@luga.de>
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
import events, hub, requests
import slist

#
# playlist class, which acts as glue layer between the playlist service
# and the playlist window
#

class playlist(slist.slist):
    def __init__(self, win, playerid):
        slist.slist.__init__(self, win, config.playlistwindow.scrollmode=="page")
        self.playerid = playerid
        self.songdbid = "main"
        items, self.ptime, self.ttime, self.autoplaymode, self.playingitem = \
               hub.request(requests.playlistgetcontents())
        self.set(items)
        self._recenter()

        self.win.channel.subscribe(events.playlistchanged, self.playlistchanged)

    def _recenter(self):
        """ recenter playlist around currently playing (or alternatively last) song """
        for i in range(len(self)):
            if self[i] is self.playingitem or i==len(self)-1:
                oldselected = self.selected
                self.selected = i
                if self.selected != oldselected:
                    self._notifyselectionchanged()
                h2 = self.win.ih/2
                if len(self)-i <= h2:
                    self.top = max(0, len(self)-self.win.ih)
                elif i >= h2:
                    self.top = i-h2
                else:
                    self.top = 0
                self._updatetop()
                break

    def getselectedsong(self):
        """ return song corresponding to currently selected item or None """
        playlistitem = self.getselected()
        if playlistitem:
            return playlistitem.song
        else:
            return None

    # The following three slist.slist methods are delegated to the
    # playlist service. Any resulting changes to the playlist will be
    # performed only later when a playlistchanged event comes back

    def deleteselected(self):
        "delete currently selected item"
        if self.selected is not None:
            hub.notify(events.playlistdeletesong(self.getselected().id))

    def moveitemup(self):
        "move selected item up, if not first"
        if self.selected is not None and self.selected>0:
            hub.notify(events.playlistmovesongup(self.getselected().id))

    def moveitemdown(self):
        "move selected item down, if not last"
        if self.selected is not None and self.selected<len(self)-1:
            hub.notify(events.playlistmovesongdown(self.getselected().id))

    def rateselection(self, rating):
        if self.selected is not None:
            self.getselectedsong().rate(rating)

    def rescanselection(self, force):
        if self.selected is not None:
            song = self.getselectedsong()
            hub.notify(events.autoregisterer_rescansongs(song.songdbid, [song], force))

    def playselected(self):
        item = self.getselected()
        if item:
            hub.notify(events.playlistplaysong(item.id))

    def filelistjumptoselected(self):
        song = self.getselectedsong()
        if song is not None:
            hub.notify(events.filelistjumptosong(song))

    # event handler

    def playlistchanged(self, event):
        self.set(event.items, keepselection=True)
        self.ptime = event.ptime
        self.ttime = event.ttime
        self.autoplaymode = event.autoplaymode
        self.playingitem = event.playingitem

        # recenter window if the playlist window doesn't have the focus.
        if not self.win.hasfocus():
            self._recenter()

        self.win.update()
