## -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2007 Jörg Lehmann <joerg@luga.de>
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

class event:
    def __str__(self):
        return self.__class__.__name__


class dbevent(event):

    """ base class for all database service events """

    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.songdbid)


class quit(event):
    """ request end of thread """
    pass


class keypressed(event):
    def __init__(self, key):
        self.key = key

    def __str__(self):
        return "%s(%d)" % (self.__class__.__name__, self.key)


class mouseevent(event):
    def __init__(self,  y, x, state):
        self.y, self.x, self.state = y, x, state

    def __str__(self):
        return "%s(%d, %d, %d)" % (self.__class__.__name__,
                                   self.y, self.x, self.state)


class selectionchanged(event):
    def __init__(self, item):
        self.item = item

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, repr(self.item))


class focuschanged(event):
    pass


class activateplaylist(event):
    pass


class activatefilelist(event):
    pass


class sendeventat(event):

    """ send event at alarmtime and every repeat seconds after (if
    nonzero) or replace the given event"""

    def __init__(self, event, alarmtime,  replace=0):
        self.event = event
        self.alarmtime = alarmtime
        self.repeat = repeat
        self.replace = replace

    def __str__(self):
        return "%s(%s, %s, %s)" % (self.__class__.__name__, self.event, self.alarmtime, self.repeat, self.replace)


class sendeventin(event):

    """ send event in alartimediff seconds and every repeat seconds
    after (if nonzero), or replace the given event"""

    def __init__(self, event, alarmtimediff, repeat=0, replace=0):
        self.event = event
        self.alarmtimediff = alarmtimediff
        self.repeat = repeat
        self.replace = replace

    def __str__(self):
        return "%s(%s, %s, %s, %s)" % (self.__class__.__name__, self.event, self.alarmtimediff, self.repeat, self.replace)


class checkpointdb(dbevent):
    """flush memory pool, write checkpoint record to log and flush flog of songdbid"""


class add_song(dbevent):
    """ add song to database """

    def __init__(self, songdbid, song):
        self.songdbid = songdbid
        self.song = song

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.song, self.songdbid)


class update_song(dbevent):
    """ update song in database """

    def __init__(self, songdbid, song):
        self.songdbid = songdbid
        self.song = song

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.song, self.songdbid)


class song_played(dbevent):
    """ register playing of song in database """

    def __init__(self, songdbid, song, date_played):
        self.songdbid = songdbid
        self.song = song
        self.date_played = date_played

    def __str__(self):
        return "%s(%s, %s)->%s" % (self.__class__.__name__, self.song, self.date_played, self.songdbid)


class song_skipped(dbevent):
    """ register skipping of song in database """

    def __init__(self, songdbid, song):
        self.songdbid = songdbid
        self.song = song

    def __str__(self):
        return "%s(%s, %s)->%s" % (self.__class__.__name__, self.song, self.songdbid)


class delete_song(dbevent):
    """ delete song from database """
    def __init__(self, songdbid, song):
        self.songdbid = songdbid
        self.song = song

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.song, self.songdbid)


class add_playlist(dbevent):
    """ add playlist to database """
    def __init__(self, songdbid, name, songs):
        self.songdbid = songdbid
        self.name = name
        self.songs = songs

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.name, self.songs, self.songdbid)


class update_playlist(dbevent):
    """ update playlist in database """

    def __init__(self, songdbid, name, songs):
        self.songdbid = songdbid
        self.name = name
        self.songs = songs

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.name, self.songs, self.songdbid)


class delete_playlist(dbevent):
    """ delete playlist from database """

    def __init__(self, songdbid, name):
        self.songdbid = songdbid
        self.name = name

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.name, self.songdbid)




class autoregistersongs(dbevent):
    """ start autoregisterer for database 

    If force is set, the m_time of songs is ignored and they are always rescanned.
    """
    def __init__(self, songdbid, force=False):
        self.songdbid = songdbid
        self.force = force

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.force, self.songdbid)


class autoregisterer_rescansongs(dbevent):
    """ rescan songs in given database 

    If force is set, the m_time of songs is ignored and they are always rescanned
    """
    def __init__(self, songdbid, songs, force=False):
        self.songdbid = songdbid
        self.songs = songs
        self.force = force

    def __str__(self):
        return "%s(%s, %s)->%s" % (self.__class__.__name__, self.songs, self.force, self.songdbid)


class clearstats(dbevent):
    """ clear playing and added information of all songs (be carefull!) """

    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)


class songchanged(event):
    """ song information changed """
    def __init__(self, songdbid, song):
        self.songdbid = songdbid
        self.song = song

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.song, self.songdbid)


class songschanged(event):
    "list of songs in database changed"
    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)

class artistschanged(event):
    "list of artists in database changed"
    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)


class albumschanged(event):
    "list of albums in database changed"
    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)


class tagschanged(event):
    "list of tags in database changed"
    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)


class dbplaylistchanged(event):
    def __init__(self, songdbid, playlist):
        self.songdbid = songdbid
        self.playlist = playlist

    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.playlist, self.songdbid)


class playerevent(event):
    """ event for the player control """

    def __init__(self, playerid):
        self.playerid = playerid

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.playerid)


class playerstart(playerevent):
    """ start player """
    pass


class playerpause(playerevent):
    """ pause player """
    pass


class playertogglepause(playerevent):
    """ pause player, if playing, or start playing, if paused """
    pass


class playernext(playerevent):
    """ play next song on player """
    pass


class playerprevious(playerevent):
    """ play previous song on player"""
    pass


class playerseekrelative(playerevent):
    """ seek relative in song by the given number of seconds """
    
    def __init__(self, playerid, seconds):
        self.playerid = playerid
        self.seconds = seconds

    def __str__(self):
        return "%s(%f->%s)" % (self.__class__.__name__, self.seconds, self.playerid)


class playerplayfaster(playerevent):
    """ increase play speed of song on player"""

    def __init__(self,playerid):
        self.playerid = playerid
        self.speed_adj = 441

class playerplayslower(playerevent):
    """ decrease play speed of song on player"""

    def __init__(self,playerid):
        self.playerid = playerid
        self.speed_adj = 441

class playerspeedreset(playerevent):
    """ Reset play speed of song on player back to its original rate"""

    def __init__(self,playerid):
        self.playerid = playerid

class playerstop(playerevent):
    """ stop player """
    pass


class playerplaysong(playerevent):
    """ play song or playlistitem on player """

    def __init__(self, playerid, playlistitemorsong):
        self.playerid = playerid
        self.playlistitemorsong = playlistitemorsong

    def __str__(self):
        return "%s(%s->%s)" % (self.__class__.__name__, self.playlistitemorsong, self.playerid)


class playerratecurrentsong(playerevent):
    """ rate song currently being played """
    def __init__(self, playerid, rating):
        playerevent.__init__(self, playerid)
        self.rating = rating

    def __str__(self):
        return "%s(%s,%d)" % (self.__class__.__name__, self.playerid, self.rating)


class playbackinfochanged(event):
    def __init__(self, playbackinfo):
        self.playbackinfo = playbackinfo

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.playbackinfo)


class statusbar_update(event):
    """ update status bar

    pos = 0: info for currently selected window
    pos = 1: player info
    pos = 2: global info
    """

    def __init__(self, pos, content):
        self.pos = pos
        self.content = content

    def __str__(self):
        return "%s(%s, %s)" % (self.__class__.__name__, self.pos, self.content)


class statusbar_showmessage(event):
    """ show a message (which automatically disappears after some time in the statusbar"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return "%r(%r)" % (self.__class__.__name__, self.content)



class requestinput(event):
    def __init__(self, title, prompt, handler):
        self.title = title
        self.prompt = prompt
        self.handler = handler

    def __str__(self):
        return "%s(%s,%s,%s)" % (self.__class__.__name__,
                              self.title, self.prompt, self.handler)


class playlistevent(event):
    pass


class playlistaddsongs(playlistevent):
    """ add songs to playlist """
    def __init__(self, songs):
        self.songs = songs

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.songs)


class playlistaddsongtop(playlistevent):
    """ add song to top of playlist """
    def __init__(self, song):
        self.song = song

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.song)


class playlistdeletesong(playlistevent):
    def __init__(self, id):
        self.id = id

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.id)


class playlistmovesongup(playlistevent):
    def __init__(self, id):
        self.id = id

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.id)


class playlistmovesongdown(playlistevent):
    def __init__(self, id):
        self.id = id

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.id)


class playlistsave(playlistevent):
    pass


class playlistclear(playlistevent):
    pass


class playlistdeleteplayedsongs(playlistevent):
    pass


class playlistreplay(playlistevent):
    """mark all songs of playlist unplayed again"""
    pass


class playlistshuffle(playlistevent):
    pass


class playlisttoggleautoplaymode(playlistevent):
    pass


class playlistplaysong(playlistevent):
    """ immediately play song in playlist """
    def __init__(self, id):
        self.id = id

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.id)


class playlistchanged(event):
    def __init__(self, items, ptime, ttime, autoplaymode, playingitem):
        self.items = items
        self.ptime = ptime
        self.ttime = ttime
        self.autoplaymode = autoplaymode
        self.playingitem = playingitem

    def __str__(self):
        return "%s(%s,%s/%s,%s,%s)" % (self.__class__.__name__,
                                       self.items, self.ptime, self.ttime, self.autoplaymode,
                                       self.playingitem)

class filelistjumptosong(event):
    """ jump to specific song in filelist window """
    def __init__(self, song):
        self.song = song

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.song)

class hidewindow(event):
    def __init__(self, window):
        self.window = window

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.window)
