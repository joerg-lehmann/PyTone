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

import item

class request:
    def __str__(self):
        return self.__class__.__name__

    __repr__ = __str__

#
# database requests
#

class dbrequest:
    def __init__(self, songdbid):
        self.songdbid = songdbid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, self.songdbid)

    def __cmp__(self, other):
        cmp(hash(self), hash(other))

    def __hash__(self):
        # for the cashing system every dbrequest has to be hashable
        # by default we rely on self.__str__ for computing the hash value
        return hash(str(self))

class dbrequestsingle(dbrequest):
    """ db request yielding a single result (not a list) and requiring a
    specific songdb to work on
    """
    pass

class dbrequestsongs(dbrequest):
    """ db request yielding a list of songs, which have to be merged when querying multiple databases

    Note that the resulting list must not be changed by the caller,
    with the exception that the order of the items may be changed at
    will (for instance by sorting)

    """

    # standard song wrapper function, wrapping a dbitem.song instance in a item.song instance
    def _songwrapper(song, songdbid):
        return item.song(songdbid, song)
    
    def __init__(self, songdbid, random=False, sort=False, wrapperfunc=_songwrapper):
        self.songdbid = songdbid
        self.sort = sort
        self.random = random
        self.wrapperfunc = wrapperfunc


class dbrequestlist(dbrequest):
    """ db request yielding a result list (not containing songs),
    which have to be merged when querying multiple databases

    If wrapperfunc is not None, is has to be a function which will be
    called for every item of the result list. wrapperfunc has to
    accepts two arguments: The first one is the item, and the second
    one is the id of the database/one of the databases where it has
    been found. The return value of wrapperfunc will then be used
    instead of the original item in the result list.

    Note that the resulting list must not be changed by the caller!
    """
    def __init__(self, songdbid, wrapperfunc=None, sort=False):
        self.songdbid = songdbid
        self.wrapperfunc = wrapperfunc
        self.sort = sort

    def __str__(self):
        return "%s(%s, %s)->%s" % (self.__class__.__name__, self.wrapperfunc, self.sort, self.songdbid)


#
# database requests which yield a single result
#

class getdatabaseinfo(dbrequestsingle):
    # XXX make this a db request. Like this it's bogus.
    """ return tuple (type, location) of database """
    pass
        

class queryregistersong(dbrequestsingle):
    def __init__(self, songdbid, path):
        self.songdbid = songdbid
        self.path = path
        
    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.path, self.songdbid)


class getsong(dbrequestsingle):
    def __init__(self, songdbid, id):
        self.songdbid = songdbid
        self.id = id
        
    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.id, self.songdbid)


class getalbum(dbrequestsingle):
    def __init__(self, songdbid, album):
        self.songdbid = songdbid
        self.album = album
        
    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.album, self.songdbid)


class getartist(dbrequestsingle):
    def __init__(self, songdbid, artist):
        self.songdbid = songdbid
        self.artist = artist
        
    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.artist, self.songdbid)


class getplaylist(dbrequestsingle):
    def __init__(self, songdbid, path):
        self.songdbid = songdbid
        self.path = path
        
    def __str__(self):
        return "%s(%s)->%s" % (self.__class__.__name__, self.path, self.songdbid)


class getsongsinplaylist(dbrequestsingle):
    """ return all songs stored in playlist path """
    def __init__(self, songdbid, path, random=False):
        self.songdbid = songdbid
        self.path = path 
        self.random = random

    def __str__(self):
        return "%s(%s,random=%s)->%s" % (self.__class__.__name__,
                                         self.path, self.random, self.songdbid)


#
# database requests which yield a list of songs
#

class getsongs(dbrequestsongs):
    
    def __init__(self, songdbid, artist=None, album=None, indexname=None, indexid=None,
                 random=False, sort=False):
        dbrequestsongs.__init__(self, songdbid, random, sort)
        self.songdbid = songdbid
        self.artist = artist
        self.album = album
        self.indexname = indexname
        self.indexid = indexid
        
    def __str__(self):
        return ( "%s(%s, %s, (%s->%s), random=%s, sort=%s)->%s" %
                 (self.__class__.__name__,
                  self.artist, self.album,
                  self.indexname, self.indexid,
                  self.random,
                  self.sort,
                  self.songdbid))


class getlastplayedsongs(dbrequestsongs):

    # in the case of getlastplayedsongs, the database returns tuples (playingtime, dbsong)
    # instead of dbsongs. We thus have to use a different wrapper function here.
    def _songwrapper(playingtimesongtuple, songdbid):
        song, playingtime = playingtimesongtuple
        return item.song(songdbid, song, playingtime)

    def __init__(self, songdbid, random=False, sort=False, wrapperfunc=_songwrapper):
        dbrequestsongs.__init__(self, songdbid, random, sort, wrapperfunc)


class gettopplayedsongs(dbrequestsongs):
    pass


class getlastaddedsongs(dbrequestsongs):
    pass


class getsongsinplaylists(dbrequestsongs):
    """ return all songs stored in all playlists """
    pass


class getartists(dbrequestlist):
    def __init__(self, songdbid, indexname=None, indexid=None, wrapperfunc=None, sort=False):
        self.songdbid = songdbid
        self.indexname = indexname
        self.indexid = indexid
        self.wrapperfunc = wrapperfunc
        self.sort = sort
        
    def __str__(self):
        return "%s(%s, %s), %s, %s )->%s" % (self.__class__.__name__,
                                             self.indexname, self.indexid, self.wrapperfunc, self.sort, self.songdbid)
    

class getalbums(dbrequestlist):
    def __init__(self, songdbid, artist=None, indexname=None, indexid=None, wrapperfunc=None, sort=False):
        self.songdbid = songdbid
        self.artist = artist
        self.indexname = indexname
        self.indexid = indexid
        self.wrapperfunc = wrapperfunc
        self.sort = sort
        
    def __str__(self):
        return "%s(%s, %s, %s, %s %s)->%s" % (self.__class__.__name__,
                                              self.artist, self.indexname, self.indexid, self.wrapperfunc, self.sort,
                                              self.songdbid)


class getgenres(dbrequestlist):
    pass


class getyears(dbrequestlist):
    pass


class getdecades(dbrequestlist):
    pass


class getratings(dbrequestlist):
    pass


class getplaylists(dbrequestlist):
    pass

#
# database request yielding the numbe of items of a certain kind
#

class getnumberofsongs(dbrequest):
    def __init__(self, songdbid, artist=None, album=None, indexname=None, indexid=None):
        self.songdbid = songdbid
        self.artist = artist
        self.album = album
        self.indexname = indexname
        self.indexid = indexid
        
    def __str__(self):
        return ( "%s(%s, %s, (%s->%s))->%s" %
                 (self.__class__.__name__,
                  self.artist, self.album,
                  self.indexname, self.indexid,
                  self.songdbid))

class getnumberofalbums(dbrequest):
    pass

class getnumberofdecades(dbrequest):
    pass

class getnumberofgenres(dbrequest):
    pass

class getnumberofratings(dbrequest):
    pass

#
# other requests for playlist and player service
#

class requestnextsong(request):
    """ request a song from playlistid. Go back in playlist if previous is set """
    def __init__(self, playlistid, previous=0):
        self.playlistid = playlistid
        self.previous = previous

    def __str__(self):
        return "%s->%s,%s" % (self.__class__.__name__, `self.playlistid`, `self.previous`)


class getplaybackinfo(request):
    """ request info about song currently playing on player playerid """
    def __init__(self, playerid):
        self.playerid = playerid

    def __str__(self):
        return "%s->%s" % (self.__class__.__name__, `self.playerid`)


class requestinput:
    def __init__(self, title, prompt, handler):
        self.title = title
        self.prompt = prompt
        self.handler = handler

    def __str__(self):
        return "%s(%s,%s,%s)" % (self.__class__.__name__,
                              self.title, self.prompt, `self.handler`)


class playlistgetcontents(request):
    pass
