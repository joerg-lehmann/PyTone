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

import config
import events, hub
import item
import slist

class filelist(slist.slist):

    def __init__(self, win, songdbids):
        slist.slist.__init__(self, win, config.filelistwindow.scrollmode == "page")

        self.basedir = item.basedir(songdbids)
        self.dir = [self.basedir]
        self.shistory = []
        self.readdir()

        self.win.channel.subscribe(events.artistaddedordeleted, self.artistaddedordeleted)
        self.win.channel.subscribe(events.albumaddedordeleted, self.albumaddedordeleted)
        self.win.channel.subscribe(events.dbplaylistchanged, self.dbplaylistchanged)
        self.win.channel.subscribe(events.filelistjumptosong, self.filelistjumptosong)

    def isdirselected(self):
        return isinstance(self.getselected(), item.diritem)

    def issongselected(self):
        return isinstance(self.getselected(), item.song)

    def getselectedsubdir(self):
        return self.dir + [self.getselected()]

    def readdir(self):
        self.set(self.dir[-1].getcontents())

    def updatedir(self):
        """ reread directory trying to keep the current selection """
        self.set(self.dir[-1].getcontents(), keepselection=True)

    def dirdown(self):
        self.shistory.append((self.dir, self.selected, self.top))
        self.dir = self.getselectedsubdir()
        self.readdir()
        # In the case of the selected item having been an artist check
        # whether only one album is present. If yes directly jump to
        # this album.
        if config.filelistwindow.skipsinglealbums and self.dir[-1].isartist() and len(self) <= 2:
            self.dir = self.getselectedsubdir()
            self.readdir()

    def dirup(self):
        if len(self.shistory)>0:
            dir, selected, top = self.shistory.pop()
            self.dir = dir
            self.readdir()
            self.selected = selected
            self.top = top
            self._notifyselectionchanged()

    def selectionpath(self):
        return self.dir[-1].getheader(self.getselected())

    def insertrecursiveselection(self):
        if self.isdirselected():
            songs = self.getselected().getcontentsrecursivesorted()
            hub.notify(events.playlistaddsongs(songs))
        elif self.issongselected():
            hub.notify(events.playlistaddsongs([self.getselected()]))

    def randominsertrecursiveselection(self):
        if self.isdirselected():
            songs = self.getselected().getcontentsrecursiverandom()
            hub.notify(events.playlistaddsongs(songs))
        elif self.issongselected():
            hub.notify(events.playlistaddsongs([self.getselected()]))

    def rateselection(self, rating):
        if (isinstance(self.getselected(), item.song) or
            isinstance(self.getselected(), item.album) or
            isinstance(self.getselected(), item.artist)):
            self.getselected().rate(rating)

    def rescanselection(self):
        if self.isdirselected():
            # instead of rescanning of a whole filesystem we start the autoregisterer
            if ( isinstance(self.getselected(), item.basedir) or
                 ( isinstance(self.getselected(), item.filesystemdir) and self.getselected().isbasedir()) ):
                hub.notify(events.autoregistersongs(self.getselected().songdbid))
            else:
                # distribute songs over songdbs
                # Note that we have to ensure that only dbitem.song (and not item.song) instances
                # are sent to the db
                dsongs = {}
                for song in self.getselected().getcontentsrecursive():
                    dsongs.setdefault(song.songdbid, []).append(song.song)
                for songdbid, songs in dsongs.items():
                    if songs:
                        hub.notify(events.rescansongs(songdbid, songs))
        else:
            self.getselected().rescan()

    # event handler

    def artistaddedordeleted(self, event):
        #if isinstance(self.dir[-1], item.basedir):
        self.updatedir()
        self.win.update()

    def albumaddedordeleted(self, event):
        #if (isinstance(self.dir[-1], item.artist) and
        #    self.dir[-1].songdbid==event.songdbid and
        #    self.dir[-1].name in event.album.artists):
        self.updatedir()
        self.win.update()

    def dbplaylistchanged(self, event):
        #if (isinstance(self.dir[-1], item.artist) and
        #    self.dir[-1].songdbid==event.songdbid and
        #    self.dir[-1].name in event.album.artists):
        self.updatedir()
        self.win.update()

    def filelistjumptosong(self, event):
        """ directly jump to given song """
        # In order to get the correct shistory, we more or less simulate
        # a walk through the directory hierarchy, starting from the basedir.
        self.shistory = []
        self.dir = [self.basedir]
        self.readdir()
        if self.selectbyname(event.song.artist):
            self.dirdown()
            # We might have skipped the album when there is only a single one of
            # the given artist.
            if not self.dir[-1].isalbum():
                if self.selectbyname(event.song.album):
                    self.dirdown()
                self.selectbyname(event.song.name)
        self.win.update()
