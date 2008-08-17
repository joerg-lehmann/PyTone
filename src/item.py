# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2005, 2006, 2007 Jörg Lehmann <joerg@luga.de>
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
import config, metadata
import events, hub, requests
import encoding
import helper

#
# filters
#

class filter:
    def __init__(self, name, indexname, indexid):
        self.name = name
        self.indexname = indexname
        self.indexid = indexid

    def __repr__(self):
        # for dbrequest cache
        return "%r=%r" % (self.indexname, self.indexid)

    def SQL_JOIN_string(self):
        return ""

    def SQL_WHERE_string(self):
        return ""

    def SQL_args(self):
        return []


class hiddenfilter(filter):
    " a filter which does not show up in the UI "
    def __init__(self, indexname, indexid):
        filter.__init__(self, None, indexname, indexid)


class urlfilter(hiddenfilter):
    def __init__(self, url):
        self.url = url
        hiddenfilter.__init__(self, "url", url)

    def SQL_WHERE_string(self):
        return "songs.url = ?"

    def SQL_args(self):
        return [self.url]


class compilationfilter(hiddenfilter):
    def __init__(self, iscompilation):
        self.iscompilation = iscompilation
        hiddenfilter.__init__(self, "compilation", iscompilation)

    def SQL_WHERE_string(self):
        return "%s songs.compilation" % (not self.iscompilation and "NOT" or "")
        # return "(songs.compilation = %s)" % (self.iscompilation and "1" or "0")


class artistfilter(hiddenfilter):
    def __init__(self, artist_id):
        self.artist_id = artist_id
        hiddenfilter.__init__(self, "artist_id", artist_id)

    def SQL_WHERE_string(self):
        return "artists.id = ? OR songs.album_artist_id = ?"

    def SQL_args(self):
        return [self.artist_id, self.artist_id]


class noartistfilter(hiddenfilter):
    def __init__(self):
        hiddenfilter.__init__(self, "artist_id", None)

    def SQL_WHERE_string(self):
        return "songs.artist_id IS NULL"


class albumfilter(hiddenfilter):
    def __init__(self, album_id):
        self.album_id = album_id
        hiddenfilter.__init__(self, "album_id", album_id)

    def SQL_WHERE_string(self):
        return "albums.id = ?"

    def SQL_args(self):
        return [self.album_id]


class playlistfilter(hiddenfilter):
    def __init__(self, playlist_id):
        self.playlist_id = playlist_id
        hiddenfilter.__init__(self, "playlist_id", playlist_id)

    def SQL_JOIN_string(self):
        return "JOIN playlistcontents ON playlistcontents.song_id = songs.id"

    def SQL_WHERE_string(self):
        return "playlistcontents.playlist_id = ?"

    def SQL_args(self):
        return [self.playlist_id]


class playedsongsfilter(filter):
    def __init__(self):
        filter.__init__(self, _("Played songs"), "playedsongs", "true")

    def SQL_WHERE_string(self):
        return "songs.playcount > 0"


class searchfilter(filter):
    def __init__(self, searchstring):
        self.searchstring = searchstring
        filter.__init__(self, "Search: %s" % searchstring, None, searchstring)

    def SQL_WHERE_string(self):
        #return "(songs.title LIKE ?)"
        return "(songs.title LIKE ?) OR (albums.name LIKE ?) OR (artists.name LIKE ?)"

    def SQL_args(self):
        return ["%%%s%%" % self.searchstring] * 3


class tagfilter(filter):

    """ filters only items of given tag,
    
    if tag_id is not None, use this id to query the database, otherwise use tag_name """

    def __init__(self, tag_name, tag_id=None, inverted=False):
        self.tag_name = tag_name
        self.tag_id = tag_id
        self.inverted = inverted
        name = "%s%s=%s" % (_("Tag"), inverted and "!" or "", tag_name)
        filter.__init__(self, name, indexname="tag", indexid=tag_name)

    def __repr__(self):
        return "tag%r=%r" % (self.inverted and "!" or "", self.tag_name)

    def SQL_WHERE_string(self):
        if self.tag_id:
            return ( "songs.id %sIN (SELECT taggings.song_id FROM taggings WHERE taggings.tag_id = %d)" % 
                     (self.inverted and "NOT " or "", self.tag_id) )
        else:
            return ( "songs.id %sIN (SELECT taggings.song_id FROM taggings, tags WHERE taggings.tag_id = tags.id and tags.name=?)" % 
                     (self.inverted and "NOT " or "") )

    def SQL_args(self):
        if not self.tag_id:
            return [self.tag_name]
        else:
            return []


class podcastfilter(tagfilter):
    def __init__(self, inverted=False):
        tagfilter.__init__(self, "G:Podcast", inverted=inverted)
        # hide filter
        self.name = None


class deletedfilter(tagfilter):
    def __init__(self, inverted=False):
        tagfilter.__init__(self, "S:Deleted", inverted=inverted)
        # hide filter
        self.name = None


class ratingfilter(filter):

    """ filters only items of given rating """

    def __init__(self, rating):
        if rating is not None:
            name = "%s=%s" % (_("Rating"), "*" * rating)
        else:
            name = "%s=%s" % (_("Rating"), _("Not rated"))
        self.rating = rating
        filter.__init__(self, name, indexname="rating", indexid=rating)

    def SQL_WHERE_string(self):
        if self.rating:
            return "songs.rating = ?"
        else:
            return "songs.rating IS NULL"

    def SQL_args(self):
        if self.rating:
            return [self.rating]
        else:
            return []


class filters(tuple):

    def getname(self):
        s = ", ".join([filter.name for filter in self if filter.name])
        if s:
            return " <%s>" % s
        else:
            return ""

    def added(self, filter):
        return filters(self + (filter,))

    def removed(self, filterclass):
        return filters(tuple([f for f in self if not isinstance(f, filterclass)]))

    def contains(self, filterclass):
        for f in self:
            if isinstance(f, filterclass):
                return True
        return False

    def SQL_JOIN_string(self):
        return "\n".join([filter.SQL_JOIN_string() for filter in self])

    def SQL_WHERE_string(self):
        wheres = [filter.SQL_WHERE_string() for filter in self]
        wheres = ["(%s)" % s for s in wheres if s]
        filterstring = " AND ".join(wheres)
        if filterstring:
            filterstring = "WHERE (%s)" % filterstring
            return filterstring

    def SQL_args(self):
        result = []
        for filter in self:
            result.extend(filter.SQL_args())
        return result

# helper function for usage in getinfo methods, which merges information about
# filters in third and forth columns of lines
def _mergefilters(lines, filters):
    # filter out filters which are to be shown
    filters = [filter for filter in filters if filter.name]
    if filters:
        for nr, filter in enumerate(filters[:4]):
            if len(lines) > nr:
                lines[nr][2:3] = [_("Filter:"), filter.name]
            else:
                lines.append(["", "", _("Filter:"), filter.name])
    return lines


class item(object):
    """ base class for various items presentend in the database and
    playlist windows."""

    def __init__(self, songdbid, id):
        """ each item has to be bound to a specific database
        identified by songdbid """
        self.songdbid = songdbid
        self.id = id

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
        return "[%s]/" % self.name

    def getid(self):
        return self.name

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
        if item and item.artist and item.album:
            s = "%s - %s" % (item.artist, item.album)
        else:
            s = self.name
        return s + self.filters.getname()

    def getinfo(self):
        return _mergefilters([[self.name, "", "", ""]], self.filters)


#
# specialized classes
#

def _formatnumbertotal(number, total):
    """ return string for number and total number """
    if number and total:
        return "%d/%d" % (number, total)
    elif number:
        return "%d" % number
    else:
        return "-"


class song(item):

    __slots__ = ["songdbid", "id", "album_id", "artist_id", "song", "playingtime"]

    def __init__(self, songdbid, id, album_id, artist_id, album_artist_id, date_played=None):
        """ create song with given id together with its database."""
        self.songdbid = songdbid
        self.id = id
        self.album_id = album_id
        self.artist_id = artist_id
        self.album_artist_id = album_artist_id
        self.date_played = date_played
        self.song_metadata = None

    def __repr__(self):
        return "song(%r) in %r database" % (self.id, self.songdbid)

    # the following two methods have to be defined because we use song as a
    # member of a set in the autoregisterer
    def __hash__(self):
        return hash("%r-%d" % (self.songdbid, self.id))

    def __eq__(self, other):
        return isinstance(other, song) and self.songdbid == other.songdbid and self.id == other.id

    def __getstate__(self):
        return (self.songdbid, self.id, self.album_id, self.artist_id, self.album_artist_id, self.date_played)

    def __setstate__(self, tuple):
        self.songdbid, self.id, self.album_id, self.artist_id, self.album_artist_id, self.date_played = tuple
        self.song_metadata = None

    def __getattr__(self, attr):
        # we refuse to fetch the song metadata if an "internal" method name is queried.
        # Thus, we do not interfere with pickling of song instances, etc.
        if attr.startswith("__"):
            raise AttributeError
        if not self.song_metadata:
            self.song_metadata = hub.request(requests.getsong_metadata(self.songdbid, self.id))
        # return metadata if we have been able to fetch it, otherwise return None
        if self.song_metadata:
            return getattr(self.song_metadata, attr)
        else:
            return None

    def _updatesong_metadata(self):
        """ notify database of song changes """
        hub.notify(events.update_song(self.songdbid, self))

    def getid(self):
        return self.id

    def getname(self):
        if self.title:
            return self.title
        else:
            return "DELETED"

    def getinfo(self):
        l = [["", "", "", ""]]*4
        # if we are unable to fetch the title, the song has been deleted in the meantime
        if self.title is None:
            return l
        l[0] = [_("Title:"), self.title]
        if self.tracknumber:
            l[0] += [_("Nr:"), _formatnumbertotal(self.tracknumber, self.trackcount)]
        else:
            l[0] += ["", ""]
        if self.album:
             l[1] = [_("Album:"),  self.album]
        else:
             l[1] = [_("URL:"), self.url]

        if self.year:
            l[1] += [_("Year:"), str(self.year)]
        else:
            l[1] += ["", ""]

        if self.artist:
            l[2] = [_("Artist:"), self.artist]
        else:
            l[2] = ["", ""]
        if self.length:
            l[2] += [_("Time:"), helper.formattime(self.length)]
        else:
            l[2] += ["", ""]
        if self.tags:
            l[3] = [_("Tags:"), u" | ".join(self.tags)]

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
            if self.rating:
                played = played + " (%s)" % ("*"*self.rating)
            l[3] += [_("Played:"),
                   _("#%d, %s ago") % (self.playcount, played)]
        else:
            if self.rating:
                l[3] += [_("Rating:"), "*" * self.rating]
            else:
                l[3] += ["", ""]
        return l

    def getinfolong(self):
        l = []
        # if we are unable to fetch the title, the song has been deleted in the meantime
        if self.title is None:
            return l
        l.append([_("Title:"), self.title, "", ""])
        l.append([_("Album:"), self.album or "-", "", ""])
        l.append([_("Artist:"), self.artist or "-", "", ""])

        if self.year:
            year = str(self.year)
        else:
            year = "-"
        l.append([_("Time:"), "%d:%02d" % divmod(self.length, 60), _("Year:"), year])
        l.append([_("Track No:"), _formatnumbertotal(self.tracknumber, self.trackcount), 
                  _("Disk No:"), _formatnumbertotal(self.disknumber, self.diskcount)])
        l.append([_("Tags:"), u" | ".join(self.tags), _("Rating:"), self.rating and ("*" * self.rating) or "-"])

        if self.size:
            if self.size > 1024*1024:
                sizestring = "%.1f MB" % (self.size / 1024.0 / 1024)
            elif self.size > 1024:
                sizestring = "%.1f kB" % (self.size / 1024.0)
            else:
                sizestring = "%d B" % self.size
        else:
            sizestring = ""
        typestring = self.type.upper()
        if self.bitrate is not None:
            typestring = "%s %dkbps" % (typestring, self.bitrate/1000)
            if self.is_vbr:
                typestring = typestring + "VBR"
            if self.samplerate:
                typestring = "%s (%.1f kHz)" % (typestring, self.samplerate/1000.)

        l.append([_("File type:"), typestring, _("Size:"), sizestring])
        replaygain = ""
        if self.replaygain_track_gain is not None and self.replaygain_track_peak is not None:
            replaygain = replaygain + "%s: %+f dB (peak: %f) " % (_("track"),
                                                                  self.replaygain_track_gain,
                                                                  self.replaygain_track_peak)
        if self.replaygain_album_gain is not None and self.replaygain_album_peak is not None:
            replaygain = replaygain + "%s: %+f dB (peak: %f)" % (_("album"),
                                                                 self.replaygain_album_gain,
                                                                 self.replaygain_album_peak)
        l.append([_("Replaygain:"), replaygain or "-", _("Beats per minute:"), self.bpm and str(self.bpm) or "-"])
        l.append([_("Times played:"), str(self.playcount),_("Times skipped:"), str(self.skipcount)])
        l.append([_("Comment:"), self.comments and self.comments[0][2] or "-", 
                  _("Lyrics:"), self.lyrics and _("%d lines") % len(self.lyrics[0][2].split("\n")) or "-"])
        l.append([_("URL:"), self.url, "", ""])

        for played in self.dates_played[-1:-6:-1]:
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

        if self.title is None:
            return "DELETED"
        d = {}
        d.update(self.song_metadata.__dict__)
        d.update(adddict)
        d["minutes"], d["seconds"] = divmod(d["length"], 60)
        d["length"] = "%d:%02d" % (d["minutes"], d["seconds"])

        if safe:
            allowedchars = encoding.decode(string.letters + string.digits + " :")
            for key, value in d.items():
                try:
                    l = []
                    for c in value:
                        if c in allowedchars:
                            l.append(c)
                    d[key] = "".join(l)
                except TypeError:
                    pass

        return unicode(formatstring) % d

    def rate(self, rating):
        # just to fetch song metadata
        oldrating = self.rating
        # if this was sucessful we can rate the song
        if self.song_metadata:
            if rating:
                self.song_metadata.rating = rating
            else:
                self.song_metadata.rating = None
            self._updatesong_metadata()

    def addtag(self, tag):
        tags = self.tags
        if tags is not None and tag not in tags:
            tags.append(tag)
            self.tags = tags
            self._updatesong_metadata()

    def removetag(self, tag):
        tags = self.tags
        if tags is not None and tag in tags:
            tags.remove(tag)
            self.tags = tags
            self._updatesong_metadata()

    def toggledelete(self):
        if self.tags is None:
            return
        if "S:Deleted" in self.tags:
            self.tags.remove("S:Deleted")
        else:
            self.tags.append("S:Deleted")
        self._updatesong_metadata()

    def getplayingtime(self):
        """ return time at which this particular song instance has been played or the
        last playing time, if no such time has been specified at instance creation time """
        return self.date_played or self.date_lastplayed


class artist(diritem):

    """ artist bound to specific songdb """

    def __init__(self, songdbid, id, name, filters):
        self.songdbid = songdbid
        self.id = id
        self.name = name

        self.filters = filters.removed(compilationfilter).added(artistfilter(id))

    def __repr__(self):
        return "artist(%r) in %r (filtered: %r)" % (self.name, self.songdbid, self.filters)

    def getname(self):
        return "%s/" % self.name

    def getcontents(self):
        albums = hub.request(requests.getalbums(self.songdbid, filters=self.filters))
        return albums + [songs(self.songdbid, self.name, self.filters)]

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters))

    def getcontentsrecursivesorted(self):
        albums = hub.request(requests.getalbums(self.songdbid, filters=self.filters))
        result = []
        for aalbum in albums:
            result.extend(aalbum.getcontentsrecursivesorted())
        return result

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters, random=True))

    def getheader(self, item):
        return self.name + self.filters.getname()

    def getinfo(self):
        if self.name == metadata.VARIOUS:
            # this should not happen, actually
            artistname = _("Various")
        else:
            artistname = self.name
        return _mergefilters([[_("Artist:"), artistname, "", ""]], self.filters)


class album(diritem):

    """ album bound to specific songdb """

    def __init__(self, songdbid, id, artist, name, filters):
        self.songdbid = songdbid
        self.id = id
        self.artist = artist
        self.name = name
        self.filters = filters.added(albumfilter(id))

    def __repr__(self):
        return "album(%r) in %r" % (self.id, self.songdbid)

    class _orderclass:
        def cmpitem(self, x, y):
            return ( x.disknumber and y.disknumber and cmp(x.disknumber, y.disknumber) or
                     x.tracknumber and y.tracknumber and cmp(x.tracknumber, y.tracknumber) or
                     cmp(x.title, y.title) )
        def SQL_string(self):
            return "ORDER BY songs.disknumber, songs.tracknumber, songs.title"
    order = _orderclass()

    def getid(self):
        return self.id

    def getname(self):
        return "%s/" % self.name

    def getcontents(self):
        songs = hub.request(requests.getsongs(self.songdbid, sort=self.order, filters=self.filters))
        return songs

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters))

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters, random=True))

    def getinfo(self):
        if self.artist == metadata.VARIOUS:
            artistname = _("Various")
        else:
            artistname = self.artist
        albumname =  self.name 
        l = [[_("Artist:"), artistname, "", ""],
             [_("Album:"), albumname, "", ""]]
        return _mergefilters(l, self.filters)


class playlist(diritem):

    """ songs in a playlist in the corresponding database """

    def __init__(self, songdbid, id, name, nfilters):
        self.songdbid = songdbid
        self.id = id
        self.name = name
        if nfilters is not None:
            self.filters = nfilters.added(playlistfilter(id))
        else:
            self.filters = filters((playlistfilter(id),))

    def getname(self):
        return "%s/" % self.name

    class _orderclass:
        def SQL_string(self):
            return "ORDER BY playlistcontents.position"
    order = _orderclass()

    def getcontents(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters, sort=self.order))

    getcontentsrecursive = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters, random=True))

    def getheader(self, item):
        if item and item.artist and item.album:
            return item.artist + " - " + item.album
        else:
            return self.name

    def getinfo(self):
        return [["%s:" % _("Playlist"), self.name, "", ""]]


class totaldiritem(diritem):

    """ diritem which contains the total database(s) as its contents """

    def getcontentsrecursive(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters))

    getcontentsrecursivesorted = getcontentsrecursive

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, filters=self.filters, random=True))


class songs(totaldiritem):

    """ all songs in the corresponding database """

    def __init__(self, songdbid, artist=None, filters=None):
        self.songdbid = songdbid
        self.id = "songs"
        self.name = _("Songs")
        self.artist = artist
        self.filters = filters
        self.nrsongs = None

    def getname(self):
        if self.nrsongs is None:
            self.nrsongs = hub.request(requests.getnumberofsongs(self.songdbid, filters=self.filters))
        return "[%s (%d)]/" % (self.name, self.nrsongs)

    class _orderclass:
        def cmpitem(self, x, y):
            return ( cmp(x.title, y.title) or
                     cmp(x.album, y.album) or
                     cmp(x.path, y.path)
                     )
        def SQL_string(self):
            return "ORDER BY songs.title, albums.name, songs.url"
    order = _orderclass()

    def getcontents(self):
        songs = hub.request(requests.getsongs(self.songdbid, filters=self.filters, sort=self.order))
        self.nrsongs = len(songs)
        return songs

    def getinfo(self):
        if self.artist is not None:
            l = [[_("Artist:"), self.artist, "", ""],
                    [self.name, "", "", ""]]
        else:
            l = [[self.name, "", "", ""]]
        return _mergefilters(l, self.filters)


class noartist(songs):

    """ list of songs without artist information """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "noartist"
        self.name = _("No artist")
        self.filters = filters.added(noartistfilter())
        self.nrsongs = None

    def getinfo(self):
        return _mergefilters([[self.name, "", "", ""]], self.filters)


class randomsongs(totaldiritem):

    """ random list of songs out of  the corresponding database """

    def __init__(self, songdbid, maxnr, filters):
        self.songdbid = songdbid
        self.id = "randomsongs"
        self.name = _("Random song list")
        self.maxnr = maxnr
        self.filters = filters

    def getcontents(self):
        songs = []
        while len(songs)<self.maxnr:
            newsongs = hub.request(requests.getsongs(self.songdbid, filters=self.filters, random=True))
            if len(newsongs) > 0:
                songs.extend(newsongs)
            else:
                break
        return songs[:self.maxnr]


class lastplayedsongs(diritem):

    """ songs last played out of the corresponding databases """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "lastplayedsongs"
        self.filters = filters.added(playedsongsfilter())
        self.name = _("Last played songs")

    class _orderclass:
        def cmpitem(self, x, y):
            return cmp(y.getplayingtime(), x.getplayingtime())
        def SQL_string(self):
            return "ORDER BY playstats.date_played DESC LIMIT 100"
    order = _orderclass()

    def getcontents(self):
        return hub.request(requests.getlastplayedsongs(self.songdbid, sort=self.order, filters=self.filters))

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getlastplayedsongs(self.songdbid, filters=self.filters, random=True))

    def getinfo(self):
        return _mergefilters([[self.name, "", "", ""]], self.filters[:-1])


class topplayedsongs(diritem):

    """ songs most often played of the corresponding databases """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "topplayedsongs"
        self.filters = filters.added(playedsongsfilter())
        self.name = _("Top played songs")

    class _orderclass:
        def cmpitem(self, x, y):
            return cmp(y.playcount, x.playcount) or cmp(y.date_lastplayed, x.date_lastplayed)
        def SQL_string(self):
            return "ORDER BY songs.playcount DESC, songs.date_lastplayed DESC LIMIT 100"
    order = _orderclass()

    def getcontents(self):
        songs = hub.request(requests.getsongs(self.songdbid, sort=self.order, filters=self.filters))
        return songs

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, sort=self.order, filters=self.filters, random=True))

    def getinfo(self):
        return _mergefilters([[self.name, "", "", ""]], self.filters[:-1])


class lastaddedsongs(diritem):

    """ songs last added to the corresponding database """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "lastaddedsongs"
        self.filters = filters
        self.name = _("Last added songs")

    class _orderclass:
        def cmpitem(self, x, y):
            return cmp(y.date_added, x.date_added)
        def SQL_string(self):
            return "ORDER BY songs.date_added DESC LIMIT 100"
    order = _orderclass()

    def getcontents(self):
        return hub.request(requests.getsongs(self.songdbid, sort=self.order, filters=self.filters))

    getcontentsrecursive = getcontentsrecursivesorted = getcontents

    def getcontentsrecursiverandom(self):
        return hub.request(requests.getsongs(self.songdbid, sort=self.order, filters=self.filters, random=True))


class albums(totaldiritem):

    """ all albums in the corresponding database """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "albums"
        self.filters = filters
        self.name = _("Albums")
        self.nralbums = None

    def getname(self):
        if self.nralbums is None:
            self.nralbums = hub.request(requests.getnumberofalbums(self.songdbid, filters=self.filters))
        return "[%s (%d)]/" % (self.name, self.nralbums)

    def getcontents(self):
        albums = hub.request(requests.getalbums(self.songdbid, filters=self.filters))
        self.nralbums = len(albums)
        return albums

    def getheader(self, item):
        if self.nralbums is None:
            self.nralbums = len(self.getcontents())
        return "%s (%d)" % (self.name, self.nralbums) + self.filters.getname()


class compilations(albums):
    def __init__(self, songdbid, filters):
        filters = filters.added(compilationfilter(True))
        albums.__init__(self, songdbid, filters)
        self.id = "compilations"
        self.name = _("Compilations")


class podcasts(albums):
    def __init__(self, songdbid, filters):
        filters = filters.removed(podcastfilter)
        filters = filters.added(podcastfilter())
        albums.__init__(self, songdbid, filters)
        self.id = "podcasts"
        self.name = _("Podcasts")


class deleted(albums):
    def __init__(self, songdbid, filters):
        filters = filters.removed(deletedfilter)
        filters = filters.added(deletedfilter())
        import log
        log.debug(str(filters))
        albums.__init__(self, songdbid, filters)
        self.id = "deleted"
        self.name = _("Deleted songs")


class tags(totaldiritem):

    """ all tags in the corresponding database """

    def __init__(self, songdbid, songdbids, filters):
        self.songdbid = songdbid
        self.id = "tags"
        self.songdbids = songdbids
        self.filters = filters
        self.name = _("Tags")
        self.nrtags = None
        self.exclude_tag_ids = []
        for filter in self.filters:
            if isinstance(filter, tagfilter):
                if not filter.inverted:
                    self.exclude_tag_ids.append(filter.tag_id)

    def getname(self):
        if self.nrtags is None:
            self.nrtags = len(self.getcontents())
        return "[%s (%d)]/" % (self.name, self.nrtags)

    def getcontents(self):
        tags = hub.request(requests.gettags(self.songdbid, filters=self.filters))
        tags = [tag for tag in tags if tag.id not in self.exclude_tag_ids]
        self.nrtags = len(tags)
        return tags

    def getheader(self, item):
        if self.nrtags is None:
            self.nrtags = len(self.getcontents())
        return "%s (%d)" % (self.name, self.nrtags) + self.filters.getname()


class ratings(totaldiritem):

    """ all ratings in the corresponding database """

    def __init__(self, songdbid, songdbids, filters):
        self.songdbid = songdbid
        self.id = "ratings"
        self.songdbids = songdbids
        self.filters = filters
        self.name = _("Ratings")
        self.nrratings = 6

    def getname(self):
        if self.nrratings is None:
            self.nrratings = len(self.getcontents())
        return "[%s (%d)]/" % (self.name, self.nrratings)

    def getcontents(self):
        ratings = [rating(self.songdbid, r, self.filters) for r in range(1, 6)]
        ratings.append(rating(self.songdbid, None, self.filters))
        self.nrratings = len(ratings)
        return ratings

    def getheader(self, item):
        if self.nrratings is None:
            nrratings = len(self.getcontents())
        return "%s (%d)" % (self.name, self.nrratings) + self.filters.getname()


class playlists(diritem):

    """ all playlists in the corresponding database """

    def __init__(self, songdbid, filters):
        self.songdbid = songdbid
        self.id = "playlists"
        self.name = _("Playlists")
        self.filters = filters
        self.nrplaylists = None

    def getname(self):
        if self.nrplaylists is None:
            self.nrplaylists = len(self.getcontents())
        return "[%s (%d)]/" % (_("Playlists"), self.nrplaylists)

    def getcontents(self):
        playlists = hub.request(requests.getplaylists(self.songdbid, filters=self.filters))
        self.nrplaylists = len(playlists)
        return playlists

    def getheader(self, item):
        if self.nrplaylists is None:
            self.nrplaylists = len(self.getcontents())
        return "%s (%d)" % (_("Playlists"), self.nrplaylists)


class filesystemdir(diritem):

    """ diritem corresponding to directory in filesystem """

    def __init__(self, songdbid, basedir, dir):
        self.songdbid = songdbid
        self.id = "filesystemdir"
        self.basedir = basedir
        self.dir = dir

        if self.dir==self.basedir:
            self.name =  _("Filesystem")
        else:
            self.name = encoding.decode_path(self.dir[len(self.basedir):].split("/")[-1])

    def getname(self):
        if self.isbasedir():
            return "[%s]/" % _("Filesystem")
        else:
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
                        song = hub.request(requests.autoregisterer_queryregistersong(self.songdbid, path))
                        if song:
                            items.append(song)
                except (IOError, OSError): pass
        except OSError:
            return None
        items.sort(cmp=lambda x, y: cmp(x.getname(), y.getname()))
        return items

    def getcontentsrecursiverandom(self):
        return []
        # songs = self.getcontentsrecursive()
        # return _genrandomchoice(songs)

    def getheader(self, item):
        if self.isbasedir():
            return _("Filesystem")
        else:
            return self.name

    def getinfo(self):
        return [["%s:" % _("Filesystem"), encoding.decode_path(self.dir), "", ""]]

    def isbasedir(self):
        """ return whether the filesystemdir is the basedir of a song database """
        return self.dir == self.basedir

_dbstats = None

class basedir(totaldiritem):

    """ base dir of database view"""

    def __init__(self, songdbids, afilters=None, rootdir=False):
        # XXX: as a really dirty hack, we cache the result of getdatabasestats for
        # all databases because we cannot call this request safely later on
        # (we might be handling another request which calls the basedir constructor)
        global _dbstats
        if _dbstats is None:
            _dbstats = {}
            for songdbid in songdbids:
                _dbstats[songdbid] = hub.request(requests.getdatabasestats(songdbid))
        self.name =  _("Song Database")
        self.songdbids = songdbids
        if len(songdbids) == 1:
            self.songdbid = songdbids[0]
            self.type = _dbstats[self.songdbid].type
            self.basedir = _dbstats[self.songdbid].basedir
        else:
            self.songdbid = None
            self.type = "virtual"
            self.basedir = None
        self.id = "basedir"
        if afilters is None:
            # add default filters
            self.filters = filters((podcastfilter(inverted=True),
                                    deletedfilter(inverted=True)))
        else:
            self.filters = afilters
        self.rootdir = rootdir
        self.maxnr = 100
        self.nrartists = None
        self.nrsongs = None
        self._initvirtdirs()

    def _initvirtdirs(self):
        self.virtdirs = []
        self.virtdirs.append(noartist(self.songdbid, filters=self.filters))
        self.virtdirs.append(compilations(self.songdbid, filters=self.filters))
        if self.type == "local" and self.rootdir:
            self.virtdirs.append(filesystemdir(self.songdbid, self.basedir, self.basedir))
        self.virtdirs.append(songs(self.songdbid, filters=self.filters))
        self.virtdirs.append(albums(self.songdbid, filters=self.filters))
        self.virtdirs.append(podcasts(self.songdbid, filters=self.filters))
        self.virtdirs.append(deleted(self.songdbid, filters=self.filters))

        if not self.filters.contains(searchfilter):
             self.virtdirs.append(tags(self.songdbid, self.songdbids, filters=self.filters))
        if not self.filters.contains(ratingfilter):
            self.virtdirs.append(ratings(self.songdbid, self.songdbids, filters=self.filters))
        if not self.filters.contains(playedsongsfilter):
            self.virtdirs.append(topplayedsongs(self.songdbid, filters=self.filters))
            self.virtdirs.append(lastplayedsongs(self.songdbid, filters=self.filters))
            self.virtdirs.append(playedsongs(self.songdbid, nfilters=self.filters))
        self.virtdirs.append(lastaddedsongs(self.songdbid, filters=self.filters))
        self.virtdirs.append(randomsongs(self.songdbid, self.maxnr, filters=self.filters))
        if not self.filters.contains(searchfilter):
            self.virtdirs.append(playlists(self.songdbid, filters=self.filters))
        if len(self.songdbids) > 1:
            self.virtdirs.extend([basedir([songdbid], self.filters) for songdbid in self.songdbids])

    def getname(self):
        if self.nrsongs is None:
            self.nrsongs = hub.request(requests.getnumberofsongs(self.songdbid, filters=self.filters))
        if self.basedir:
            return  _("[Database: %s (%d)]") % (self.basedir, self.nrsongs)
        else:
            return _("%d databases (%d)") % (len(self.songdbids), self.nrsongs)

    def getcontents(self):
        # do not show artists which only appear in compilations
        filters = self.filters.added(compilationfilter(False))
        aartists = hub.request(requests.getartists(self.songdbid, filters=filters))
        self.nrartists = len(aartists)
        # reset cached value
        self.nrsongs = None
        if config.filelistwindow.virtualdirectoriesattop:
            return self.virtdirs + aartists
        else:
            return aartists + self.virtdirs

    def getcontentsrecursivesorted(self):
        # we cannot rely on the default implementation since we don't want
        # to have the albums and songs included trice
        artists = hub.request(requests.getartists(self.songdbid, filters=self.filters))
        result = []
        for aartist in artists:
            result.extend(aartist.getcontentsrecursivesorted())
        return result

    def getheader(self, item):
        if self.nrartists is not None:
            nrartistsstring = _("%d artists") % self.nrartists
        else:
            nrartistsstring = _("? artists") 
        if self.basedir:
            maxlen = 15
            dirname = self.basedir
            if len(dirname)>maxlen:
                dirname = "..."+dirname[-maxlen+3:]
            else:
                dirname = self.basedir
            s = _("Database (%s, %s)") % (dirname, nrartistsstring)
        else:
            s = _("%d databases (%s)") % (len(self.songdbids), nrartistsstring)
        return s + self.filters.getname()

    def getinfo(self):
         if self.basedir:
             description = _("[Database: %s (%%d)]") % (self.basedir)
         else:
             description = _("%d databases (%%d)") % (len(self.songdbids))
         return _mergefilters([[self.name, description, "", ""]], self.filters)

class index(basedir):

    def __init__(self, songdbids, name, description, filters):
        basedir.__init__(self, songdbids, filters)
        self.name = name
        self.description = description
        self.type = "index"

    def getname(self):
        # XXX make this configurable (note that showing the numbers by default is rather costly)
        if 1:
            return "%s/" % self.description
        else:
            if self.nrsongs is None:
                self.nrsongs = hub.request(requests.getnumberofsongs(self.songdbid, filters=self.filters))
            return "%s (%d)/" % (self.description, self.nrsongs)

    def getinfo(self):
        return _mergefilters([[self.name, self.description, "", ""]], self.filters[:-1])


class tag(index):
    def __init__(self, songdbid, id, name, nfilters):
        if nfilters is not None:
            nfilters = nfilters.added(tagfilter(name, tag_id=id))
        else:
            nfilters = filters((tagfilter(name, tag_id=id),))
        index.__init__(self, [songdbid], _("Tag:"), name, nfilters)
        self.id = id


class rating(index):
    def __init__(self, songdbid, r, nfilters):
        if nfilters is not None:
            nfilters = nfilters.added(ratingfilter(r))
        else:
            nfilters = filters((ratingfilter(r),))
        if r is None:
            description = _("Not rated")
        else:
            description = "*" * r
        index.__init__(self, [songdbid], _("Rating:"), description, nfilters)
        self.id = r


class playedsongs(index):

    """ songs played at least once """

    def __init__(self, songdbid, nfilters):
        if nfilters is not None:
            nfilters = nfilters.added(playedsongsfilter())
        else:
            nfilters = filters((playedsongsfilter(),))
        index.__init__(self, [songdbid], _("Played songs:"), "[%s]" % _("Played songs"), nfilters)
        self.name = _("Played songs")
        self.id = "playedsongs"

    def getinfo(self):
        return _mergefilters([[self.name, "", "", ""]], self.filters[:-1])


class focus_on(index):

    """ songs filtered by search string """

    def __init__(self, songdbid, searchstring, nfilters):
        if nfilters is not None:
            nfilters = nfilters.added(searchfilter(searchstring))
        else:
            nfilters = filters((searchfilter(searchstring),))
        index.__init__(self, [songdbid], _("Search:"), searchstring, nfilters)
        self.id = "search: %s" % searchstring

