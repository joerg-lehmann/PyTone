# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2005 Jörg Lehmann <joerg@luga.de>
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

import os.path, locale, re, string, sys, time
import log, metadata

fallbacklocalecharset = 'iso-8859-1'

# Try to determine "correct" character set for the reencoding of the
# unicode strings contained in Ogg Vorbis files
try:
    # works only in python > 2.3
    localecharset = locale.getpreferredencoding()
except:
    try:
        localecharset = locale.getdefaultlocale()[1]
    except:
        try:
            localecharset = sys.getdefaultencoding()
        except:
            localecharset = fallbacklocalecharset
if localecharset in [None, 'ANSI_X3.4-1968']:
    localecharset = fallbacklocalecharset


tracknrandtitlere = re.compile("^\[?(\d+)\]? ?[- ] ?(.*)\.(mp3|ogg)$")
UNKNOWN = "Unknown"


class dbitem:

    """ base class for various items stored in database:

    songs, albums, artists, genres, years, playlists"""

    def __cmp__(self, other):
        try:
            return cmp(self.id, other.id)
        except:
            return 1

    def __repr__(self):
        return "%s(%s)" % (self.__class__, self.id)

    def __hash__(self):
        return hash(self.id)


class song(dbitem):

    def __init__(self, relpath, basedir, tracknrandtitlere, capitalize, stripleadingarticle, removeaccents):
        # use relative path of song as its id
        self.id = os.path.normpath(relpath)
        self.name = os.path.basename(self.id)

        # we set the path later in readid3info
        self.path = None

        # determine type of file from its extension
        self.type = metadata.gettype(os.path.splitext(relpath)[1])
        if self.type is None:
            raise RuntimeError("Fileformat of song '%s' not supported" % (self.id))

        # song metadata
        self.title = ""
        self.album = ""
        self.artist = ""
        self.year = ""
        self.genre = ""
        self.tracknr = ""
        self.length = 0

        # statistical information
        self.nrplayed = 0
        self.lastplayed = []
        self.added = time.time()
        self.rating = None
        # where does rating come from: 0=song itself, 1=album, 2=artist
        # This information is used when you rate an album or an artist to not
        # overwrite the rating already given to a specific song or all songs
        # on a given album of that artist, respectively.
        self.ratingsource = None

        self.scanfile(basedir, tracknrandtitlere, capitalize, stripleadingarticle, removeaccents)

    def __getattr__(self, name):
        if name=="albumid":
            return self.album
        elif name=="artistid":
            return artist
        elif name=="genreid":
            return genre
        else:
            raise AttributeError

    def scanfile(self, basedir, tracknrandtitlere, capitalize, stripleadingarticle, removeaccents):
        """ update path info for song and scan id3 information """
        self.path = os.path.normpath(os.path.join(basedir, self.id))
        if not os.access(self.path, os.R_OK):
            raise IOError("cannot read song")

        # guesses for title and tracknr using the filename
        match = re.match(tracknrandtitlere, self.name)
        if match:
            fntracknr = str(int(match.group(1)))
            fntitle = match.group(2)
        else:
            fntracknr = ""
            fntitle = self.name
            if fntitle.lower().endswith(".mp3") or fntitle.lower().endswith(".ogg"):
                fntitle = fntitle[:-4]

        first, second = os.path.split(os.path.dirname(self.id))
        if first and second and not os.path.split(first)[0]:
            fnartist = first
            fnalbum = second
        else:
            fnartist = fnalbum = ""

        fntitle = fntitle.replace("_", " ")
        fnalbum = fnalbum.replace("_", " ")
        fnartist = fnartist.replace("_", " ")

        try:
            metadatadecoder = metadata.getmetadatadecoder(self.type)
        except:
            raise RuntimeError("Support for %s songs not enabled" % (self.type))

        try:
            log.debug("reading metadata for %s" % self.path)
            md = metadatadecoder(self.path)
            self.title = md.title
            self.album = md.album
            self.artist = md.artist
            self.year = md.year
            self.genre = md.genre
            self.tracknr = md.tracknr
            self.length = md.length
            log.debug("metadata for %s read successfully" % self.path)
        except:
            log.warning("could not read metadata for %s" % self.path)
            log.debug_traceback()

        # sanity check for tracknr
        try:
            self.tracknr= str(int(self.tracknr))
        except:
            # treat track number like "3/12"
            try:
                self.tracknr= str(int(self.tracknr[:self.tracknr.index('/')]))
            except:
                self.tracknr= ""

        # do some further treatment of the song info

        # use title from filename, if it is a longer version of
        # the id3 tag title
        if not self.title or fntitle.startswith(self.title):
            self.title = fntitle

        # also try to use tracknr from filename, if not present as id3 tag
        if not self.tracknr or self.tracknr == "0":
            self.tracknr = fntracknr

        # we don't want empty album names
        if not self.album:
            if fnalbum:
                self.album = fnalbum
            else:
                self.album = UNKNOWN

        # nor empty artist names
        if not self.artist:
            if fnartist:
                self.artist = fnartist
            else:
                self.artist = UNKNOWN

        # nor empty genres
        if not self.genre:
            self.genre = UNKNOWN

        if not self.year or self.year == "0":
            self.year = None
        else:
            try:
                self.year = int(self.year)
            except:
                self.year = None

        if capitalize:
            # normalize artist, album and title
            self.artist = string.capwords(self.artist)
            self.album = string.capwords(self.album)
            self.title = string.capwords(self.title)

        if stripleadingarticle:
            # strip leading "The " in artist names, often used inconsistently
            if self.artist.startswith("The ") and len(self.artist)>4:
                self.artist = self.artist[4:]

        if removeaccents:
            translationtable = string.maketrans('ÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛáàäâéèëêíìïîóòöôúùüû',
                                                'AAAAEEEEIIIIOOOOUUUUaaaaeeeeiiiioooouuuu')
            self.artist = string.translate(self.artist, translationtable)
            self.album = string.translate(self.album, translationtable)
            self.title = string.translate(self.title, translationtable)

    def play(self):
        self.nrplayed += 1
        self.lastplayed.append(time.time())
        # only store last 10 playing times
        self.lastplayed = self.lastplayed[-10:]

    def unplay(self):
        if self.nrplayed or 1:
            self.nrplayed -= 1
            self.lastplayed.pop()

    def update(self, newsong):
        """ update song metadata using the information in newsong"""
        self.title = newsong.title
        self.album = newsong.album
        self.artist = newsong.artist
        self.year = newsong.year
        self.genre = newsong.genre
        self.tracknr = newsong.tracknr
        self.length = newsong.length


class artist(dbitem):
    def __init__(self, name):
        self.id = name
        self.name = name
        self.albums = []
        self.songs = []


class album(dbitem):
    def __init__(self, name):
        self.id = name
        self.name = name
        self.artists = []
        self.songs = []


class playlist(dbitem):
    def __init__(self, path):
        self.path = self.id = os.path.normpath(path)
        self.name = os.path.basename(path)
        if self.name.endswith(".m3u"):
            self.name = self.name[:-4]
        self.songs = []

        file = open(self.path, "r")

        for line in file.xreadlines():
            # XXX: interpret extended m3u format (especially for streams)
            # see: http://forums.winamp.com/showthread.php?s=dbec47f3a05d10a3a77959f17926d39c&threadid=65772
            if not line.startswith("#") and not chr(0) in line:
                path = line.strip()
                if not path.startswith("/"):
                    path = os.path.join(self.path, path)
                if os.path.isfile(path):
                    self.songs.append(path)
        file.close()


class dbindex(dbitem):

    """ base class for indices (besides albums and artists) in database """

    def __init__(self, id):
        self.id = id
        self.artists = []
        self.albums = []
        self.songs = []


class genre(dbindex):
    def __init__(self, name):
        dbindex.__init__(self, name)
        self.name = name


class year(dbindex):
    def __init__(self, year):
        dbindex.__init__(self, str(year))
        self.year = year


class rating(dbindex):
    def __init__(self, rating):
        dbindex.__init__(self, str(rating))
        self.rating = rating
