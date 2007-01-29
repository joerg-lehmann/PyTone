# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003, 2004 Jörg Lehmann <joerg@luga.de>
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

import os.path
import random
import time
import pickle

import config
import events, hub, requests
import item
import log
import service
import encoding

_counter = 0

class playlistitem:
    """ wrapped song with the two additional attributes played and id

    - id:     unique id for playlist item (note that the same song
              can be present more than once in the playlist)
    - played: has playlist item already been played
    - playstarttime: time at which song has been played or None if played is False
    """

    def __init__(self, song, played=False, playstarttime=None):
        global _counter
        self.song = song
        self.played = played
        self.playstarttime = playstarttime
        # has the playing of the song registered in the database
        self.playingregistered = False
        self.id = _counter
        _counter += 1

    def __repr__(self):
        return "playlistitem: id=%s" % `self.id`

    def getid(self):
        return self.id

    def getinfo(self):
        return self.song.getinfo()

    def getinfolong(self):
        return self.song.getinfolong()

    def markplayed(self):
        self.played = True
        self.playstarttime = time.time()

    def markunplayed(self):
        self.played = False

    def hasbeenplayed(self):
        return self.played


def initplaylist(id, playerid, songdbid):
    """initialize playlist service corresponding to player with playerid
    """
    playlist(id, playerid, songdbid).start()


class playlist(service.service):
    """manage playlist for a single player, which can be accessed 
    by multipled users"""

    def __init__(self, id, playerid, songdbid):
        service.service.__init__(self, "playlist")
        self.id = id
        # each playlist service is identified by the corresponding player
        self.playerid = playerid
        self.songdbid = songdbid
        self.items = []
        self.ttime = 0
        self.ptime = 0
        self.playingitem = None
        self.logfilename = config.general.logfile
        self.autoplaymode = config.general.autoplaymode

        self.channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
        self.channel.subscribe(events.playerstop, self.playerstop)
        self.channel.subscribe(events.playlistaddsongs, self.playlistaddsongs)
        self.channel.subscribe(events.playlistaddsongtop, self.playlistaddsongtop)
        self.channel.subscribe(events.playlistdeletesong, self.playlistdeletesong)
        self.channel.subscribe(events.playlistmovesongup, self.playlistmovesongup)
        self.channel.subscribe(events.playlistmovesongdown, self.playlistmovesongdown)
        self.channel.subscribe(events.playlistclear, self.playlistclear)
        self.channel.subscribe(events.playlistdeleteplayedsongs,
                               self.playlistdeleteplayedsongs)
        self.channel.subscribe(events.playlistreplay, self.playlistreplay)
        self.channel.subscribe(events.playlistsave, self.playlistsave)
        self.channel.subscribe(events.playlistshuffle, self.playlistshuffle)
        self.channel.subscribe(events.playlisttoggleautoplaymode, self.playlisttoggleautoplaymode)
        self.channel.subscribe(events.playlistplaysong, self.playlistplaysong)
        self.channel.subscribe(events.songchanged, self.songchanged)

        self.channel.supply(requests.playlist_requestnextsong, self.playlist_requestnextsong)
        self.channel.supply(requests.playlistgetcontents, self.playlistgetcontents)

        # try to load dump from prior crash, if existent
        if config.general.dumpfile:
            try:
                if os.path.isfile(config.general.dumpfile):
                    self.load()
                    os.unlink(config.general.dumpfile)
            except:
                pass

    def append(self, item):
        self.ttime += item.song.length
        if item.hasbeenplayed():
            self.ptime += item.song.length
        self.items.append(item)

    def insert(self, index, item):
        self.ttime += item.song.length
        if item.hasbeenplayed():
            self.ptime += item.song.length
        self.items.insert(index, item)

    def __delitem__(self, index):
        item = self.items[index]
        self.ttime -= item.song.length
        if item.hasbeenplayed():
            self.ptime -= item.song.length
        self.items.__delitem__(index)
        self._updateplaystarttimes()

    # all methods starting with an underscore may modify the playlist but leave
    # it up to the caller to announce this change via an playlistchanged event

    def _searchnextitem(self):
        """return playlistitem which has to be played next or None"""
        for i in range(len(self.items)):
            if not self.items[i].hasbeenplayed():
                return self.items[i]
        return None

    def _logplay(self, item):
        if self.logfilename:
            logfile = open(self.logfilename, "a")
            logfile.write("%s: %s\n" % (time.asctime(), encoding.encode_path(item.song.url)))
            logfile.close()

    def _updateplaystarttimes(self):
        # TODO: take crossfading time into account
        if self.playingitem:
            playstarttime = self.playingitem.playstarttime + self.playingitem.song.length
        else:
            playstarttime = time.time()
        for item in self.items:
            if not item.hasbeenplayed():
                item.playstarttime = playstarttime
                playstarttime += item.song.length

    def _playitem(self, item):
        """ check for a song abortion, register song as being played
        and update playlist information accordingly"""

        if not item.hasbeenplayed():
            self.ptime += item.song.length
        self.playingitem = item
        item.markplayed()
        self._updateplaystarttimes()
        self._logplay(item)

    def _playnext(self):
        """ mark next item from playlist as played and as currently playing and return
        corresponding song"""
        nextitem = self._searchnextitem()
        if nextitem:
            self._playitem(nextitem)
            return nextitem
        else:
            return None

    def _playprevious(self):
        """ mark next item from playlist as played & currently playing and return
        corresponding song"""

        # start either from the currently playing song, or if no song
        # is currently played, the first unplayed song in the playlist...
        #
        if self.playingitem:
            currentitem = self.playingitem
        else:
            currentitem = self._searchnextitem()

        if currentitem:
            # ... and go back one song
            i = self.items.index(currentitem)
            if i == 0:
                return
            self._markunplayed(currentitem)
            item = self.items[i-1]
            self._playitem(item)
            return item

    def _clear(self):
        self.items = []
        self.ptime = 0
        self.ttime = 0
        self.playingitem = None

    def _deleteplayedsongs(self):
        for i in range(len(self.items)-1,-1,-1):
            if self.items[i].hasbeenplayed() and self.items[i] != self.playingitem:
                del self[i]

    def _checksong(self, song):
        # it is ok if the song is contained in a local song database, so we first
        # check whether this is the case.
        # XXX make this behaviour configurable?
	stats = hub.request(requests.getdatabasestats(song.songdbid))
        if isinstance(song, item.song):
            if stats.type == "local":
                return song

	return song

        # XXX do we really need this
        # currently it does not work anymore
        if os.path.isfile(song.path):
            # first we try to access the song via its filesystem path
            return hub.request(requests.queryregistersong(self.songdbid, song.path))

        if song.artist != dbitem.UNKNOWN and song.album != dbitem.UNKNOWN:
            # otherwise we use the artist and album tags and try to obtain the song via
            # the database
            songs = hub.request(requests.getsongs(self.songdbid,
                                                  artist=song.artist, album=song.album))
            for asong in songs:
                if asong.title == song.title:
                    return asong

        # song not found
        # XXX start transmitting song
        return

    def _addsongs(self, songs):
        """add songs to end of playlist"""
        for song in songs:
            if song:
                song = self._checksong(song)
                if song:
                    self.append(playlistitem(song))
        self._updateplaystarttimes()

    def _markunplayed(self, item):
        """ mark song unplayed and adjust playlist information accordingly """
        if item.hasbeenplayed():
            self.ptime -= item.song.length
            item.markunplayed()
            self._updateplaystarttimes()

    def _markallunplayed(self):
        """ mark all songs in playlist as not having been played """
        for item in self.items:
            self._markunplayed(item)

    # convenience method for issuing a playlistchanged event

    def notifyplaylistchanged(self):
        hub.notify(events.playlistchanged(self.items, self.ptime, self.ttime, self.autoplaymode, self.playingitem))

    # statusbar input handler

    def saveplaylisthandler(self, name, key):
        name = name.strip()
        if key == ord("\n") and name != "" and self.items:
            songs = [item.song for item in self.items if item.song.songdbid == self.songdbid ]
            hub.notify(events.add_playlist(self.songdbid, name, songs))

    def _locatesong(self, id):
        """ locate position of item in playlist by id """
        for item, i in zip(self.items, range(len(self.items))):
            if item.id == id:
                return i
        else:
            return None

    def dump(self):
        """ write playlist to dump file """
        if self.playingitem:
            self.playingitem.markunplayed()
        # self._deleteplayedsongs()
        self.notifyplaylistchanged()
        dumpfile = open(config.general.dumpfile, "w")
        pickle.dump(self.items, dumpfile)

    def load(self):
        """ load playlist from file """
        dumpfile = open(config.general.dumpfile, "r")
        self._clear()
        for item in pickle.load(dumpfile):
            # We have to be careful here and not use the playlist item
            # stored in the dump file directly, since its id and the
            # global _counter variable are not in accordance. Besides that
            # the playstarttime information stored in the pickle is incorrect.
            # We thus have to create a new playlistitem.
            newplaylistitem = playlistitem(item.song, item.played, item.playstarttime)
            self.append(newplaylistitem)
        self._updateplaystarttimes()

    # event handlers

    def playbackinfochanged(self, event):
       # We are only interested in the case of the player having been stopped due to
       # no more song being left in the playlist.
       if event.playbackinfo.isstopped():
           self.playingitem = None
           self.notifyplaylistchanged()

    def playerstop(self, event):
        # Mark the currently playing song as unplayed again when the
        # player has been stopped manually. Note that the handling of
        # this event is potentially racy with the playbackinfochanged
        # event, but the ordering of the events in our event channel
        # should prevent any problems.
        if event.playerid == self.playerid:
            if self.playingitem:
                self._markunplayed(self.playingitem)
                self.playingitem = None
                self.notifyplaylistchanged()

    def playlistaddsongs(self, event):
        self._addsongs(event.songs)
        self.notifyplaylistchanged()

    def playlistaddsongtop(self, event):
        if event.song:
            song = self._checksong(event.song)
            if song:
                newitem = playlistitem(song)
                for i in range(len(self.items)):
                    if not self.items[i].hasbeenplayed():
                        self.insert(i, newitem)
                        break
                else:
                    self.append(newitem)
                self._playitem(newitem)
                self._updateplaystarttimes()
                hub.notify(events.playerplaysong(self.playerid, newitem))
                self.notifyplaylistchanged()

    def playlistdeletesong(self, event):
        i = self._locatesong(event.id)
        if i is not None:
            del self[i]
            self.notifyplaylistchanged()

    def playlistmovesongup(self, event):
        i = self._locatesong(event.id)
        if i is not None and i > 0:
            self.items[i-1], self.items[i] = self.items[i], self.items[i-1]
            self._updateplaystarttimes()
            self.notifyplaylistchanged()

    def playlistmovesongdown(self, event):
        i = self._locatesong(event.id)
        if i is not None and i<len(self.items)-1:
            self.items[i], self.items[i+1] = self.items[i+1], self.items[i]
            self._updateplaystarttimes()
            self.notifyplaylistchanged()

    def playlistclear(self, event):
        self._clear()
        self.notifyplaylistchanged()

    def playlistdeleteplayedsongs(self, event):
        self._deleteplayedsongs()
        self.notifyplaylistchanged()

    def playlistreplay(self, event):
        self._markallunplayed()
        self.notifyplaylistchanged()

    def playlistsave(self, event):
        hub.notify(events.requestinput(_("Save playlist"),
                                       _("Name:"),
                                       self.saveplaylisthandler))

    def playlistshuffle(self, event):
        random.shuffle(self.items)
        self._updateplaystarttimes()
        self.notifyplaylistchanged()

    def playlisttoggleautoplaymode(self, event):
        if self.autoplaymode == "off":
            self.autoplaymode = "repeat"
        elif self.autoplaymode == "repeat":
            self.autoplaymode = "random"
        else:
            self.autoplaymode = "off"
        self.notifyplaylistchanged()

    def playlistplaysong(self, event):
        i = self._locatesong(event.id)
        self._playitem(self.items[i])
        self.notifyplaylistchanged()
        hub.notify(events.playerplaysong(self.playerid, self.items[i]))

    def songchanged(self, event):
        # check whether one of our playlist items is affected by the change
        # in the songdb
        for item in self.items:
            if item.song == event.song and item.song.id==event.songdbid:
                item.song = event.song
                self._updateplaystarttimes()
                self.notifyplaylistchanged()

    def quit(self, event):
        service.service.quit(self, event)
        self.dump()

    #
    # request handler
    #

    def playlist_requestnextsong(self, request):
        if request.playlistid != self.id:
            raise hub.DenyRequest
        if not request.previous:
            nextitem = self._playnext()
            if not nextitem:
                if self.autoplaymode == "random":
                    # add some randomly selected song to the end of the playlist
                    randomsongs = hub.request(requests.getsongs(None, random=True))
                    if randomsongs:
                        self._addsongs(randomsongs[0:1])
                        nextitem = self._playnext()
                elif self.autoplaymode == "repeat":
                    self._markallunplayed()
                    nextitem = self._playnext()
        else:
            nextitem = self._playprevious()
        self.notifyplaylistchanged()
        return nextitem

    def playlistgetcontents(self, request):
        return self.items, self.ptime, self.ttime, self.autoplaymode, self.playingitem
