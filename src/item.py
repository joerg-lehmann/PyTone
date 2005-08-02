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


import os.path, string, time
import dbitem, metadata
import events, hub, requests
import helper

# We import the _genrandomchoice function used in the songdb module.
# Maybe we should instead put it in a separate module
from services.songdb import _genrandomchoice


class item:
    """ base class for various items presentend in the database and
    playlist windows (as opposed to those stored in the database
    itself (cf. module dbitem)"""

    def __init__(self, songdbid):
        """ each item has to be bound to a specific database
        identified by songdbid """
        self.songdbid = songdbid

    def getid(self):
        """ return unique id of item in context """
        raise NotImplementedError("has to be implemented by sub classes")

    def getname(self):
        """ short name used for item in lists """
        raise NotImplementedError("has to be implemented by sub classes")

    def getinfo(self):
        """ 4x4 array containing rows and columns used for display of item
        in iteminfowin"""
        return [["", "", "", ""]]

    def getinfolong(self):
        """ nx4 array containing rows and columns used for display of item
        in iteminfowin2"""
        return self.getinfo()

class diritem(item):

    """ item containing other items """

    def getname(self):
        return "%s/" % self.name

    def getid(self):
        return self.name

    def cmpitem(x, y):
        """ compare the two items x, y of diritem

        Note that can be implemented as a staticmethod, when no reference to the
        concrete instance is necessary. This may be useful, when cmpitem is passed to
        database requests, because then the caching of the result only works, when always
        the same cmpitem function is passed to the request. """
        # by default we just compare the names of the artists (case insensitively)
        return cmp(x.name.lower(), y.name.lower())
    cmpitem = staticmethod(cmpitem)

    def getcontents(self):
        """ return items contained in self """
        pass

    def getcontentsrecursive(self):
        """ return items contained in self including subdirs (in arbitrary order)"""
        result = []
        for aitem in self.getcontents():
            if isinstance(aitem, diritem):
                result.extend(aitem.getcontentsrecursive())
            else:
                result.append(aitem)

        return result

    def getcontentsrecursivesorted(self):
        """ return items contained in self including subdirs (sorted)"""
        result = []
        for aitem in self.getcontents():
            if isinstance(aitem, diritem):
                result.extend(aitem.getcontentsrecursivesorted())
            else:
                result.append(aitem)

        return result

    def getcontentsrecursiverandom(self):
        """ return random list of items contained in self including subdirs """
        # this should be implemented by subclasses
        return []

    def getheader(self, item):
        """ return header (used for title bar in filelistwin) of item in self.

        Note that item can be None!
        """
        pass

    def isartist(self):
        """ does self represent an artist? """
        return False

    def isalbum(self):
        """ does self represent an album? """
        return False


class song(item):
    def __init__(self, songdbid,  song, playingtime=None):
        """ song together with its database.

        If playingtime is not None, it specifies the time at which this specific song instance
        has been played (currently only used for songs appearing the in lastplayedsongs list).
        """
        assert isinstance(song, dbitem.song), "song has to be a dbitem.song instance, not a %s instance" % repr(song.__class__)
        self.songdbid = songdbid
        self.song = song
        self.playingtime = playingtime

    def __repr__(self):
        return "song(%s) in %s database" % (self.id, self.songdbid)

    __str__ = __repr__

    def __getattr__(self, attr):
        # Python tries to call __setstate__ upon unpickling -- prevent this
        if attr=="__setstate__":
            raise AttributeError
        return getattr(self.song, attr)

    def _updatesong(self):
        """ notify database of song changes """
        hub.notify(events.updatesong(self.songdbid, self.song))

    def getid(self):
        return self.song.id

    def getname(self):
        return self.song.title

    def getinfo(self):
        l = [["", "", "", ""]]*4
        l[0] = [_("Title:"), self.song.title]
        if self.song.tracknr:
            l[0] += [_("Nr:"), str(self.song.tracknr)]
        else:
            l[0] += ["", ""]
        l[1] = [_("Album:"),  self.song.album]
        if self.song.year:
            l[1] += [_("Year:"), str(self.song.year)]
        else:
            l[1] += ["", ""]
        l[2] = [_("Artist:"), self.song.artist,
              _("Time:"), helper.formattime(self.song.length)]
        l[3] = [_("Genre:"), self.song.genre]

        if self.getplayingtime() is not None:
            seconds = int((time.time()-self.getplayingtime())/60)
            days, rest = divmod(seconds, 24*60)
            hours, minutes = divmod(rest, 60)
            if days>=10:
                played = "%dd" % days
            elif days>0:
                played = "%dd %dh" % (days, hours)
            elif hours>0:
                played = "%dh %dm" % (hours, minutes)
            else:
                played = "%dm" % minutes
            if self.song.rating:
                played = played + " (%s)" % ("*"*self.song.rating)
            l[3] += [_("Played:"),
                   _("#%d, %s ago") % (self.song.nrplayed, played)]

        else:
            if self.song.rating:
                l[3] += [_("Rating:"), "*"*self.song.rating]
            else:
                l[3] += ["", ""]
        return l

    def getinfolong(self):
        l = []
        l.append([_("Title:"), self.song.title, "", ""])
        l.append([_("Album:"),  self.song.album, "", ""])
        l.append([_("Artist:"), self.song.artist, "", ""])
        if self.song.year:
            l.append([_("Year:"), str(self.song.year), "", ""])
        else:
            l.append([_("Year:"), "", "", ""])

        if self.song.tracknr:
            l.append([_("Track No:"), str(self.song.tracknr), "", ""])
        else:
            l.append([_("Track No:"), "", "", ""])

        l.append([_("Genre:"), self.song.genre, "", ""])
        l.append([_("Time:"), "%d:%02d" % divmod(self.song.length, 60), "", ""])
        l.append([_("Path:"), self.song.path, "", ""])

        if self.song.rating:
            l.append([_("Rating:"), "*"*self.song.rating, "", ""])
        else:
            l.append([_("Rating:"), "-", "", ""])

        l.append([_("Times played:"), str(self.song.nrplayed), "", ""])

        for played in self.song.lastplayed[-1:-6:-1]:
            last = int((time.time()-played)/60)
            days, rest = divmod(last, 24*60)
            hours, minutes = divmod(rest, 60)
            if days>0:
                lastplayed = "%dd %dh %dm" % (days, hours, minutes)
            elif hours>0:
                lastplayed = "%dh %dm" % (hours, minutes)
            else:
                lastplayed = "%dm" % minutes

            l.append([_("Played:"), "%s (%s)" % (time.ctime(played), _("%s ago") % lastplayed), "", ""])

        return l

    def format(self, formatstring, adddict={}, safe=False):
        """format song info using formatstring. Further song information
        in adddict is added. If safe is True, all values are cleaned
        of characters which are neither letters, digits, a blank or a colon.
        """

        d = {}
        d.update(self.song.__dict__)
        d.update(adddict)
        d["minutes"], d["seconds"] = divmod(d["length"], 60)
        d["length"] = "%d:%02d" % (d["minutes"], d["seconds"])

        if safe:
            allowedchars = string.letters + string.digits + " :"
            for key, value in d.items():
                try:
                    l = []
                    for c in value:
                        if c in allowedchars:
                            l.append(c)
                    d[key] = "".join(l)
                except TypeError:
                    pass

        return formatstring % d

    def play(self):
        self.song.play()
        self._updatesong()

    def unplay(self):
        """ forget last time song has been played (e.g., because playback was not complete) """
        self.song.unplay()
        self._updatesong()

    def rate(self, rating):
        if rating:
            self.song.rating = rating
        else:
            self.song.rating = None
        self.song.ratingsource = 0
        self._updatesong()

    def rescan(self):
        """rescan id3 information for song, keeping playing statistic, rating, etc."""
        hub.notify(events.rescansong(self.songdbid, self.song))

    def getplayingtime(self):
        """ return time at which this particular song instance has been played or the
        last playing time, if no such time has been specified at instance creation time """
        if self.playingtime is None and self.song.lastplayed:
            return self.song.lastplayed[-1]
        else:
            return self.playingtime

class artist(diritem):

    """ artist bound to specific songdb """

    def __init__(self, songdbid, name):
        self.songdbid = songdbid
        self.name = name

    def __repr__(self):
        return "artist(%s) in %s" % (self.name, self.songdbid)

    def _albumwrapper(self, aalbum, songdbid):
        return album(self.songdbid, aalbum.id, self.name, aalbum.name)

    def getcontents(self):
        albums = hub.request(requests.getalbums(self.songdbid, self.name, wrapperfunc=self._albumwrapper, sort=self.cmpitem))
        return albums + [songs(self.songdbid, self.name)]

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, artist=self.name))

    def getcontentsrecursivesorted(self):
        albums = hub.request(requests.getalbums(self.songdbid, self.name, wrapperfunc=self._albumwrapper, sort=self.cmpitem))
        result = []
        for aalbum in albums:
            result.extend(aalbum.getcontentsrecursivesorted())
        return result

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, artist=self.name, random=True))

    def getheader(self, item):
        return self.name

    def getinfo(self):
        l = [[_("Artist:"), self.name, "", ""]]
        return l

    def isartist(self):
        return True

    def rate(self, rating):
        for song in self.getcontentsrecursive():
            if song.ratingsource is None or song.ratingsource == 2:
                if rating:
                    song.song.rating = rating
                else:
                    song.song.rating = None
                song.song.ratingsource = 2
                song._updatesong()

class album(diritem):

    """ album bound to specific songdb """

    def __init__(self, songdbid, id, artist, name):
        self.songdbid = songdbid
        self.id = id
        self.artist = artist
        self.name = name

    def __repr__(self):
        return "album(%s) in %s" % (self.id, self.songdbid)

    def cmpitem(x, y):
        return ( x.tracknr!="" and y.tracknr!="" and
                 cmp(int(x.tracknr), int(y.tracknr)) or
                 cmp(x.name, y.name) or
                 cmp(x.path, y.path) )
    cmpitem = staticmethod(cmpitem)

    def getid(self):
        return self.id

    def getcontents(self):
        songs = hub.request(requests.getsongs(self.songdbid, artist=self.artist, album=self.name, sort=self.cmpitem))
        return songs

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, artist=self.artist, album=self.name))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid,
                                             artist=self.artist,
                                             album=self.name,
                                             random=True))

    def getheader(self, item):
        if self.artist:
            return self.artist + " - " + self.name
        else:
            return self.name

    def getinfo(self):
        l = [[_("Artist:"), self.artist is None and _("various") or self.artist, "", ""],
             [_("Album:"), self.name, "", ""]]
        return l

    def isalbum(self):
        return True

    def rate(self, rating):
        for song in self.getcontentsrecursive():
            if song.ratingsource is None or song.ratingsource >= 1:
                if rating:
                    song.song.rating = rating
                else:
                    song.song.rating = None
                song.song.ratingsource = 1
                song._updatesong()


class playlist(diritem):

    """ songs in a playlist in the corresponding database """

    def __init__(self, songdbid, path, name, songs):
        self.songdbid = songdbid
        self.path = path
        self.name = name
        self.songs = songs

    def getid(self):
        return self.path

    def getcontents(self):
        return hub.request(requests.getsongsinplaylist(self.songdbid, self.path))

    def getcontentsrecursive(self):
        return hub.request(requests.getsongsinplaylist(self.songdbid, self.path))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongsinplaylist(self.songdbid, self.path, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return self.name

    def getinfo(self):
        return [["%s:" % _("Playlist"), self.name, "", ""]]

class filtereditem(diritem):

    """ super class for item, which filters only items of a given kind"""

    def __init__(self, songdbid, item, indexname, indexid):
        self.songdbid = songdbid
        self.item = item
        self.indexname = indexname
        self.indexid = indexid
        self.nritems = None

    def getid(self):
        return self.item.getid()

    def getname(self):
        if isinstance(self.item, albums) or isinstance(self.item, songs):
            self.nritems = len(self.getcontents())
            return "%s (%d) <%s>/" % (self.item.name, self.nritems, self.fname)
        else:
            return "%s <%s>/" % (self.item.name, self.fname)

    def cmpitem(self, x, y):
        try:
            return self.item.cmpitem(x.item, y.item)
        except AttributeError:
            return self.item.cmpitem(x, y)

    def getheader(self, item):
        if item is None:
            return ""
        if isinstance(self.item, albums):
            return "%s <%s>" % (self.item.getheader(item.item),
                                self.fname)
        else:
            return "%s <%s>" % (self.item.getheader(item),
                                self.fname)

    def _album_artist_wrapper(self, aalbum, songdbid):
        return  self.__class__(self.songdbid,
                               album(self.songdbid, aalbum.id, self.item.name, aalbum.name),
                               self.indexid)

    def _album_noartist_wrapper(self, aalbum, songdbid):
        return  self.__class__(self.songdbid,
                               album(self.songdbid, aalbum.id, None, aalbum.name),
                               self.indexid)

    def getcontents(self):
        if isinstance(self.item, artist):
            contents = hub.request(requests.getalbums(self.songdbid,
                                                      self.item.name,
                                                      indexname=self.indexname, indexid=self.indexid,
                                                      wrapperfunc=self._album_artist_wrapper, sort=self.cmpitem))
            contents = contents + [self.__class__(self.songdbid, songs(self.songdbid, artist=self.item.name), self.indexid)]
        elif isinstance(self.item, album):
            contents = hub.request(requests.getsongs(self.songdbid,
                                                     artist=self.item.artist,
                                                     album=self.item.name,
                                                     indexname=self.indexname, indexid=self.indexid,
                                                     sort=self.cmpitem))
        elif isinstance(self.item, songs):
            contents =  hub.request(requests.getsongs(self.songdbid,
                                                      artist=self.item.artist,
                                                      indexname=self.indexname, indexid=self.indexid,
                                                      sort=self.cmpitem))
        elif isinstance(self.item, albums):
            contents = hub.request(requests.getalbums(self.songdbid,
                                                      indexname=self.indexname, indexid=self.indexid,
                                                      wrapperfunc = self._album_noartist_wrapper,
                                                      sort=self.cmpitem))
        else:
            # should not happen
            contents = []

        return contents

    def getcontentsrecursive(self):
        if isinstance(self.item, artist):
            return hub.request(requests.getsongs(self.songdbid,
                                                 artist=self.item.name,
                                                 indexname=self.indexname, indexid=self.indexid))
        elif isinstance(self.item, album):
            return hub.request(requests.getsongs(self.songdbid,
                                                 artist=self.item.artist,
                                                 album=self.item.name,
                                                 indexname=self.indexname, indexid=self.indexid))
        elif isinstance(self.item, songs) or isinstance(self.item, albums):
            return hub.request(requests.getsongs(self.songdbid,
                                                 indexname=self.indexname, indexid=self.indexid))

        # should not happen
        return []

    def getcontentsrecursiverandom(self):
        if isinstance(self.item, artist):
            return hub.request(requests.getsongs(self.songdbid,
                                                        artist=self.item.name,
                                                        indexname=self.indexname, indexid=self.indexid,
                                                        random=True))
        elif isinstance(self.item, album):
            return hub.request(requests.getsongs(self.songdbid,
                                                        artist=self.item.artist,
                                                        album=self.item.name,
                                                        indexname=self.indexname, indexid=self.indexid,
                                                        random=True))
        elif isinstance(self.item, songs) or isinstance(self.item, albums):
            return hub.request(requests.getsongs(self.songdbid,
                                                 indexname=self.indexname, indexid=self.indexid,
                                                 random=True))

        # should not happen
        return []


    def getinfo(self):
        l = self.item.getinfo()
        l.append([_("Filter:"), self.fname, "", ""])
        return l
    
    def isartist(self):
        return isinstance(self.item, artist)

    def isalbum(self):
        return isinstance(self.item, album)


class filtereddecade(filtereditem):

    """ item, which filters only items of agiven decade"""

    def __init__(self, songdbid, item, indexid):
        filtereditem.__init__(self, songdbid, item, indexname="decade", indexid=indexid)
        self.decade = indexid
        self.fname = "%s=%s" % (_("Decade"),
                                self.decade and "%ds" % self.decade or _("Unknown"))


class filteredgenre(filtereditem):

    """ item, which filters only items of given genre"""

    def __init__(self, songdbid, item, indexid):
        filtereditem.__init__(self, songdbid, item, indexname="genre", indexid=indexid)
        self.genre = indexid
        self.fname = "%s=%s" % (_("Genre"), self.genre)


class filteredrating(filtereditem):

    """ item, which filters only items of given rating"""

    def __init__(self, songdbid, item, indexid):
        filtereditem.__init__(self, songdbid, item, indexname="rating", indexid=indexid)
        self.rating = indexid
        if self.rating is not None:
            self.fname = "%s=%s" % (_("Rating"), "*" * self.rating)
        else:
            self.fname = "%s=%s" % (_("Rating"), _("Not rated"))


class index(diritem):

    """ artists, albums + songs filtered by a given index e in the corresponding database """

    def __init__(self, songdbid, indexname, indexid, indexclass):
        self.songdbid = songdbid
        self.indexname = indexname
        self.indexid= indexid
        self.indexclass = indexclass

    def getid(self):
        return self.indexname

    def cmpitem(x, y):
        return cmp(x.item.name.lower(), y.item.name.lower())
    cmpitem = staticmethod(cmpitem)

    def _artistwrapper(self, aartist, asongdbid):
        return self.indexclass(self.songdbid, artist(self.songdbid, aartist.name), self.indexid)

    def getcontents(self):
        contents = hub.request(requests.getartists(self.songdbid, indexname=self.indexname, indexid=self.indexid,
                                                   wrapperfunc=self._artistwrapper, sort=self.cmpitem))
        contents = contents + [ self.indexclass(self.songdbid, albums(self.songdbid), self.indexid),
                                self.indexclass(self.songdbid, songs(self.songdbid), self.indexid) ]
        return contents

    def getcontentsrecursivesorted(self):
        # we cannot rely on the default implementation since we don't want
        # to have the albums and songs included trice
        artists = hub.request(requests.getartists(self.songdbid, indexname=self.indexname, indexid=self.indexid,
                                                  wrapperfunc=self._artistwrapper, sort=self.cmpitem))
        result = []
        for aartist in artists:
            result.extend(aartist.getcontentsrecursivesorted())
        return result

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid,
                                             indexname=self.indexname, indexid=self.indexid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid,
                                             indexname=self.indexname, indexid=self.indexid,
                                             random=True))


class genre(index):

    """ artists, albums + songs from a specific genre in the corresponding database """

    def __init__(self, songdbid, name):
        index.__init__(self, songdbid, indexname="genre", indexid=name, indexclass=filteredgenre)
        self.name = name

    def getheader(self, item):
        return self.name

    def getinfo(self):
        return [["%s:" % _("Genre"), self.name, "", ""]]


class decade(index):

    """ artists, albums + songs from a specific decade in the corresponding database """

    def __init__(self, songdbid, decade):
        # decade = None, ..., 1960, 1970, ...
        assert decade is None or decade%10 == 0, \
               "decade has to be an integer multiple of 10 or None"

        index.__init__(self, songdbid, indexname="decade", indexid=decade, indexclass=filtereddecade)
        self.decade = decade
        self.name = decade and "%ds" % decade or _("Unknown")

    def getheader(self, item):
        return self.name

    def getinfo(self):
        return [["%s:" % _("Decade"), self.name, "", ""]]

class rating(index):

    """ artists, albums + songs with a specific rating in the corresponding database """

    def __init__(self, songdbid, rating):
        index.__init__(self, songdbid, indexname="rating", indexid=rating, indexclass=filteredrating)
        self.rating = rating

    def getname(self):
        if self.rating is not None:
            return "%s/" % ("*" * self.rating)
        else:
            return ("%s/" % _("Not rated"))

    def getheader(self, item):
        if self.rating is not None:
            return "*" * self.rating
        else:
            return _("Not rated")

    def getinfo(self):
        if self.rating is not None:
            return [["%s:" % _("Rating"), "*" * self.rating, "", ""]]
        else:
            return [["%s:" % _("Rating"), _("Not rated"), "", ""]]


class randomsonglist(diritem):

    """ random list of songs out of  the corresponding database """

    def __init__(self, songdbid, maxnr):
        self.songdbid = songdbid
        self.name = "[%s]" % _("Random song list")
        self.maxnr = maxnr

    def getcontents(self):
        songs = []
        while len(songs)<self.maxnr:
            newsongs = hub.request(requests.getsongs(self.songdbid, random=True))
            if len(newsongs) > 0:
                songs.extend(newsongs)
            else:
                break
        return songs[:self.maxnr]

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return _("Random song list")

    def getinfo(self):
        return [[_("Random song list"), "", "", ""]]


class lastplayedsongs(diritem):

    """ songs last played out of the corresponding databases """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = "[%s]" % _("Last played songs")

    def cmpitem(x, y):
        return cmp(y.getplayingtime(), x.getplayingtime())
    cmpitem = staticmethod(cmpitem)

    def getcontents(self):
        songs = hub.request(requests.getlastplayedsongs(self.songdbid, sort=self.cmpitem))
        return songs

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getlastplayedsongs(self.songdbid, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return _("Last played songs")

    def getinfo(self):
        return [[_("Last played songs"), "", "", ""]]


class topplayedsongs(diritem):

    """ songs most often played of the corresponding databases """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = "[%s]" % _("Top played songs")

    def cmpitem(x, y):
        return cmp(y.nrplayed, x.nrplayed) or cmp(y.lastplayed, x.lastplayed)
    cmpitem = staticmethod(cmpitem)

    def getcontents(self):
        songs = hub.request(requests.gettopplayedsongs(self.songdbid, sort=self.cmpitem))
        return songs

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.gettopplayedsongs(self.songdbid, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return _("Top played songs")

    def getinfo(self):
        return [[_("Top played songs"), "", "", ""]]



class lastaddedsongs(diritem):

    """ songs last added to the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = "[%s]" % _("Last added songs")

    def cmpitem(x, y):
        return cmp(y.added, x.added)
    cmpitem = staticmethod(cmpitem)

    def getcontents(self):
        return hub.request(requests.getlastaddedsongs(self.songdbid, sort=self.cmpitem))

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getlastaddedsongs(self.songdbid, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return _("Last added songs")

    def getinfo(self):
        return [[_("Last added songs"), "", "", ""]]


class albums(diritem):

    """ all albums in the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = _("Albums")
        self.nralbums = None

    def getname(self):
        if self.nralbums is None:
            self.nralbums = hub.request(requests.getnumberofalbums(self.songdbid))
        return "[%s (%d)]/" % (self.name, self.nralbums)

    def getcontents(self):
        def albumwrapper(aalbum, songdbid):
            return album(self.songdbid, aalbum.id, None, aalbum.name)
        albums = hub.request(requests.getalbums(self.songdbid, wrapperfunc=albumwrapper, sort=self.cmpitem))
        return albums

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        #if item:
        #    return item.artist
        #else:
        #    return self.getname()[1:-2]
        return self.getname()[1:-2]

    def getinfo(self):
        return [[_("Albums"), "", "", ""]]


class genres(diritem):

    """ all genres in the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = _("Genres")
        self.nrgenres = None

    def getname(self):
        if self.nrgenres is None:
            self.nrgenres = hub.request(requests.getnumberofgenres(self.songdbid))
        return "[%s (%d)]/" % (_("Genres"), self.nrgenres)

    def _genrewrapper(self, agenre, songdbid):
        return genre(songdbid, agenre.name)

    def getcontents(self):
        genres = hub.request(requests.getgenres(self.songdbid, wrapperfunc=self._genrewrapper, sort=self.cmpitem))
        return genres

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        nrgenres = hub.request(requests.getnumberofgenres(self.songdbid))
        return "%s (%d)" % (_("Genres"), nrgenres)

    def getinfo(self):
        return [[_("Genres"), "", "", ""]]


class decades(diritem):

    """ all decades in the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = _("Decades")
        self.nrdecades = None

    def getname(self):
        if self.nrdecades is None:
            self.nrdecades = hub.request(requests.getnumberofdecades(self.songdbid))
        return "[%s (%d)]/" % (_("Decades"), self.nrdecades)

    def _decadewrapper(self, adecade, songdbid):
        return decade(songdbid, adecade)

    def getcontents(self):
        decades = hub.request(requests.getdecades(self.songdbid, self._decadewrapper, sort=self.cmpitem))
        return decades

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        nrdecades = hub.request(requests.getnumberofdecades(self.songdbid))
        return "%s (%d)" % (_("Decades"), nrdecades)

    def getinfo(self):
        return [[_("Decades"), "", "", ""]]

class ratings(diritem):

    """ all ratings in the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = _("Ratings")
        self.nrratings = None

    def getname(self):
        if self.nrratings is None:
            self.nrratings = hub.request(requests.getnumberofratings(self.songdbid))
        return "[%s (%d)]/" % (_("Ratings"), self.nrratings)

    def cmpitem(x, y):
        if x.rating is None:
            return 1
        elif y.rating is None:
            return -1
        else:
            return cmp(y.rating, x.rating)
    cmpitem = staticmethod(cmpitem)

    def _ratingwrapper(self, arating, songdbid):
        return rating(songdbid, arating.rating)

    def getcontents(self):
        ratings = hub.request(requests.getratings(self.songdbid, wrapperfunc=self._ratingwrapper, sort=self.cmpitem))
        return ratings

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        nrratings = hub.request(requests.getnumberofratings(self.songdbid))
        return "%s (%d)" % (_("Ratings"), nrratings)

    def getinfo(self):
        return [[_("Ratings"), "", "", ""]]


class songs(diritem):

    """ all songs in the corresponding database """

    def __init__(self, songdbid, artist=None):
        self.songdbid = songdbid
        self.name = _("Songs")
        self.artist = artist
        self.nrsongs = None

    def getname(self):
        if self.artist is None:
            if self.nrsongs is None:
                self.nrsongs = hub.request(requests.getnumberofsongs(self.songdbid))
            return "[%s (%d)]/" % (self.name, self.nrsongs)
        else:
            if self.nrsongs is None:
                self.nrsongs = len(self.getcontents())
            return "[%s (%d)]/" % (_("Songs"), self.nrsongs)

    def cmpitem(x, y):
        return ( cmp(x.title, y.title) or
                 cmp(x.album, y.album) or
                 cmp(x.path, y.path)
                 )
    cmpitem = staticmethod(cmpitem)

    def getcontents(self):
        songs = hub.request(requests.getsongs(self.songdbid, artist=self.artist, sort=self.cmpitem))
        return songs

    getcontentsrecursivesorted = getcontents

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, artist=self.artist))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, artist=self.artist, random=True))

    def getheader(self, item):
        if item:
            return item.artist + " - " + item.album
        else:
            return self.getname()[1:-2]

    def getinfo(self):
        if self.artist is not None:
            return [[_("Artist:"), self.artist, "", ""],
                    [_("Songs"), "", "", ""]]
        else:
            return [[_("Songs"), "", "", ""]]


class playlists(diritem):

    """ all playlists in the corresponding database """

    def __init__(self, songdbid):
        self.songdbid = songdbid
        self.name = _("Playlists")
        self.nrplaylists = None

    def getname(self):
        if self.nrplaylists is None:
            self.nrplaylists = len(self.getcontents())
        return "[%s (%d)]/" % (_("Playlists"), self.nrplaylists)

    def getcontents(self):
        def playlistwrapper(aplaylist, songdbid):
            # Note that a playlist is always bound to a particular songdb (much like a song).
            # Thus, we have to use its songdbid here.
            return playlist(songdbid, aplaylist.path, aplaylist.name, aplaylist.songs)
        playlists = hub.request(requests.getplaylists(self.songdbid, wrapperfunc=playlistwrapper, sort=self.cmpitem))
        return playlists

    def getcontentsrecursive(self):
        return hub.request(requests.getsongsinplaylists(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongsinplaylists(self.songdbid, random=True))

    def getheader(self, item):
        return "%s (%d)" % (_("Playlists"), len(self.getcontents()))

    def getinfo(self):
        return [[_("Playlists"), "", "", ""]]


class filesystemdir(diritem):

    """ diritem corresponding to directory in filesystem """

    def __init__(self, songdbid, basedir, dir):
        self.songdbid = songdbid
        self.basedir = basedir
        self.dir = dir

        if self.dir==self.basedir:
            self.name = "[%s]" % _("Filesystem")
        else:
            self.name = self.dir[len(self.basedir):].split("/")[-1]

    def getname(self):
        return "%s/" % self.name

    def getcontents(self):
        items = []
        try:
            for name in os.listdir(self.dir):
                try:
                    path = os.path.join(self.dir, name)
                    extension = os.path.splitext(path)[1]
                    if os.path.isdir(path) and os.access(path, os.R_OK|os.X_OK):
                        newitem = filesystemdir(self.songdbid, self.basedir, path)
                        items.append(newitem)
                    elif extension in metadata.getextensions() and os.access(path, os.R_OK):
                        newsong = hub.request(requests.queryregistersong(self.songdbid, path))
                        items.append(newsong)
                except (IOError, OSError) : pass
        except OSError:
            return None
        items.sort(self.cmpitem)
        return items

    def getcontentsrecursiverandom(self):
        songs = self.getcontentsrecursive()
        return _genrandomchoice(songs)

    def getheader(self, item):
        if self.dir==self.basedir:
            return _("Filesystem")
        else:
            return self.name

    def getinfo(self):
        return [["%s:" % _("Filesystem"), self.dir, "", ""]]

    def isbasedir(self):
        """ return whether the filesystemdir is the basedir of a song database """
        return self.dir == self.basedir


class basedir(diritem):

    """ base dir of database view"""

    def __init__(self, songdbids, maxnr, virtualdirectoriesattop):
        self.name = _("Song Database")
        self.songdbids = songdbids
        if len(songdbids) == 1:
            self.songdbid = songdbids[0]
            self.type, self.basedir = hub.request(requests.getdatabaseinfo(self.songdbid))
        else:
            self.songdbid = None
            self.type = "virtual"
            self.basedir = None
        self.maxnr = maxnr
        self.virtualdirectoriesattop = virtualdirectoriesattop
        self.nrsongs = None

        if self.type=="local":
            self.filesystemdir = filesystemdir(self.songdbid, self.basedir, self.basedir)
        else:
            self.filesystemdir = None
        self.songs = songs(self.songdbid)
        self.albums = albums(self.songdbid)
        self.decades = decades(self.songdbid)
        self.genres = genres(self.songdbid)
        self.ratings = ratings(self.songdbid)
        self.topplayedsongs = topplayedsongs(self.songdbid)
        self.lastplayedsongs = lastplayedsongs(self.songdbid)
        self.lastaddedsongs = lastaddedsongs(self.songdbid)
        self.randomsonglist = randomsonglist(self.songdbid, self.maxnr)
        self.playlists = playlists(self.songdbid)
        if len(self.songdbids) > 1:
            self.subbasedirs = [basedir([songdbid], self.maxnr, self.virtualdirectoriesattop)
                                for songdbid in self.songdbids]
        else:
            self.subbasedirs = []

        self.virtdirs = [self.songs,
                         self.albums,
                         self.decades,
                         self.genres,
                         self.ratings,
                         self.topplayedsongs,
                         self.lastplayedsongs,
                         self.lastaddedsongs,
                         self.randomsonglist,
                         self.playlists]
        if self.filesystemdir is not None:
            self.virtdirs[:0] = [self.filesystemdir]
        self.virtdirs.extend(self.subbasedirs)

    def getname(self):
        return "[%s]/" % self.getheader(None)

    def _artistwrapper(self, aartist, songdbid):
        return artist(self.songdbid, aartist.name)

    def getcontents(self):
        aartists = hub.request(requests.getartists(self.songdbid, wrapperfunc=self._artistwrapper, sort=self.cmpitem))
        if self.virtualdirectoriesattop:
            return self.virtdirs + aartists
        else:
            return aartists + self.virtdirs

    def getcontentsrecursivesorted(self):
        # we cannot rely on the default implementation since we don't want
        # to have the albums and songs included trice
        artists = hub.request(requests.getartists(self.songdbid, wrapperfunc=self.artistwrapper, sort=self.cmpitem))
        result = []
        for aartist in artists:
            result.extend(aartist.getcontentsrecursivesorted())
        return result

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, random=True))

    def getheader(self, item):
        if self.nrsongs is None:
            self.nrsongs = hub.request(requests.getnumberofsongs(self.songdbid))
        if self.basedir:
            return _("Database (%s, %d songs)") % (self.basedir, self.nrsongs)
        else:
            return _("%d databases (%d songs)") % (len(self.songdbids), self.nrsongs)

    def getinfo(self):
        return [["%s:" % _("Database"), self.basedir, "", ""]]
