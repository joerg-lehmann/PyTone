# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2007 Jörg Lehmann <joerg@luga.de>
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
import events, requests, hub
import item
import slist
import log

class filelist(slist.slist):

    def __init__(self, win, songdbids):
        slist.slist.__init__(self, win, config.filelistwindow.scrollmode == "page")

        self.basedir = item.basedir(songdbids, rootdir=True)
        # self.basedir = item.basedir(songdbids)
        self.dir = [self.basedir]
        self.shistory = []
        self.readdir()

        self.win.channel.subscribe(events.songschanged, self.songschanged)
        self.win.channel.subscribe(events.artistschanged, self.artistschanged)
        self.win.channel.subscribe(events.albumschanged, self.albumschanged)
        self.win.channel.subscribe(events.tagschanged, self.tagschanged)
        self.win.channel.subscribe(events.songchanged, self.songchanged)
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
        if config.filelistwindow.skipsinglealbums and isinstance(self.dir[-1], item.artist) and len(self) <= 2:
            self.dir = self.getselectedsubdir()
            self.readdir()

    def dirup(self):
        if len(self.shistory)>0:
            dir, selected, top = self.shistory.pop()
            self.dir = dir
            self.readdir()
            self.selected = selected
            self.top = top
            # the window size could have changed in the meantime, so we have to update top
            self._updatetop()
            self._notifyselectionchanged()

    def focus_on(self, searchstring):
        # remove any previous focus
        if isinstance(self.dir[-1], item.focus_on):
            self.dirup()
        self.shistory.append((self.dir, self.selected, self.top))
        songdbid = self.dir[-1].songdbid
        # if filters apply, use them
        try:
            filters = self.dir[-1].filters
        except AttributeError:
            filters = None
        self.dir = self.dir + [item.focus_on(songdbid, searchstring, filters)]
        self.readdir()

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
        if self.isdirselected():
            if not isinstance(self.getselected(), (item.artist, item.album)):
                self.win.sendmessage(_("Not rating virtual directories!"))
                return False
            songs = self.getselected().getcontentsrecursive()
            if rating:
                self.win.sendmessage(_("Rating %d song(s) with %d star(s)...") % (len(songs), rating))
            else:
                self.win.sendmessage(_("Removing rating of %d song(s)...") % len(songs))
        elif self.issongselected():
            songs = [self.getselected()]
        for song in songs:
            song.rate(rating)
        return True

    def addtagselection(self, tag):
        if self.isdirselected():
            if not isinstance(self.getselected(), (item.artist, item.album)):
                self.win.sendmessage(_("Not tagging virtual directories!"))
                return False
            songs = self.getselected().getcontentsrecursive()
            self.win.sendmessage(_("Tagging %d song(s) with tag '%s'...") % (len(songs), tag))
        elif self.issongselected():
            songs = [self.getselected()]
        for song in songs:
            song.addtag(tag)
        return True

    def removetagselection(self, tag):
        if self.isdirselected():
            if not isinstance(self.getselected(), (item.artist, item.album)):
                self.win.sendmessage(_("Not untagging virtual directories!"))
                return False
            songs = self.getselected().getcontentsrecursive()
            self.win.sendmessage(_("Removing tag '%s' from %d song(s)...") % (tag, len(songs)))
        elif self.issongselected():
            songs = [self.getselected()]
        for song in songs:
            song.removetag(tag)
        return True

    def toggledeleteselection(self):
        if self.isdirselected():
            if not isinstance(self.getselected(), (item.artist, item.album)):
                self.win.sendmessage(_("Not (un)deleting virtual directories!"))
                return False
            songs = self.getselected().getcontentsrecursive()
            self.win.sendmessage(_("(Un)deleting %d song(s)...") % len(songs))
        elif self.issongselected():
            songs = [self.getselected()]
        for song in songs:
            song.toggledelete()
        self.updatedir()
        return True

    def rescanselection(self, force):
        if ( isinstance(self.getselected(), item.basedir) or
             ( isinstance(self.getselected(), item.filesystemdir) and self.getselected().isbasedir()) ):
            # instead of rescanning of a whole filesystem we start the autoregisterer
            self.win.sendmessage(_("Scanning for songs in database '%s'...") % self.getselected().songdbid)
            hub.notify(events.autoregistersongs(self.getselected().songdbid))
        else:
            if self.isdirselected():
                # distribute songs over songdbs
                # Note that we have to ensure that only dbitem.song (and not item.song) instances
                # are sent to the db
                songs = self.getselected().getcontentsrecursive()
            else:
                songs = [self.getselected()]
            self.win.sendmessage(_("Rescanning %d song(s)...") % len(songs))
            dsongs = {}
            for song in songs:
                dsongs.setdefault(song.songdbid, []).append(song)
            for songdbid, songs in dsongs.items():
                if songs:
                    hub.notify(events.autoregisterer_rescansongs(songdbid, songs, force))

    # event handler

    def songschanged(self, event):
        if isinstance( self.dir[-1], (item.songs, item.album)):
            self.updatedir()
            self.win.update()

    def artistschanged(self, event):
        if isinstance( self.dir[-1], item.basedir):
            self.updatedir()
            self.win.update()

    def albumschanged(self, event):
        if isinstance(self.dir[-1], (item.albums, item.artist, item.compilations)):
            self.updatedir()
            self.win.update()

    def tagschanged(self, event):
        if isinstance(self.dir[-1], item.tags):
            self.updatedir()
            self.win.update()

    def songchanged(self, event):
        if isinstance( self.dir[-1], (item.songs, item.album, item.topplayedsongs, item.lastplayedsongs)):
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
        # either we are able to locate the artist or we should look under compilations
        if ( (event.song.artist_id and (self.selectbyid(event.song.artist_id) or self.selectbyid("compilations"))) or
             self.selectbyid("noartist") ):
            self.dirdown()
            # We might have skipped the album when there is only a single one of
            # the given artist.
            if not isinstance(self.dir[-1], item.album) and self.selectbyid(event.song.album_id):
                self.dirdown()
            self.selectbyid(event.song.id)
        self.win.update()
