
# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2006, 2007 Jörg Lehmann <joerg@luga.de>
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

import os
import errno
import math
import sys
import random
import time

try:
    import sqlite3 as sqlite
except ImportError:
    from pysqlite2 import dbapi2 as sqlite

import events, hub, requests
import errors
import log
import metadata
import item
import service
import encoding
import config as configmodule


create_tables = """
CREATE TABLE artists (
  id             INTEGER CONSTRAINT pk_artist_id PRIMARY KEY AUTOINCREMENT,
  name           TEXT UNIQUE
);

CREATE TABLE albums (
  id             INTEGER CONSTRAINT pk_album_id PRIMARY KEY AUTOINCREMENT,
  artist_id      INTEGER CONSTRAINT fk_albums_artist_id REFERENCES artists(id),
  name           TEXT,
  UNIQUE (artist_id, name)
);

CREATE TABLE tags (
  id             INTEGER CONSTRAINT pk_tag_id PRIMARY KEY AUTOINCREMENT,
  name           TEXT UNIQUE
);

CREATE TABLE taggings (
  song_id        INTEGER CONSTRAINT fk_song_id REFERENCES songs(id),
  tag_id         INTEGER CONSTRAINT fk_tag_id  REFERENCES tags(id)
);

CREATE TABLE playstats (
  song_id        INTEGER CONSTRAINT fk_song_id REFERENCES songs(id),
  date_played    TIMESTAMP
);

CREATE TABLE playlists (
  id             INTEGER CONSTRAINT pk_playlist_id PRIMARY KEY AUTOINCREMENT,
  name           TEXT UNIQUE
);

CREATE TABLE playlistcontents (
  playlist_id    INTEGER CONSTRAINT fk_playlist_id  REFERENCES playlists(id),
  song_id        INTEGER CONSTRAINT fk_song_id      REFERENCES songs(id),
  position       INTEGER
);

CREATE TABLE songs (
  id                    INTEGER CONSTRAINT pk_song_id PRIMARY KEY AUTOINCREMENT,
  url                   TEXT UNIQUE,
  type                  TEXT,
  title                 TEXT,
  album_id              INTEGER CONSTRAINT fk_song_album_id  REFERENCES albums(id),
  artist_id             INTEGER CONSTRAINT fk_song_artist_id REFERENCES artists(id),
  album_artist_id       INTEGER CONSTRAINT fk_song_artist_id REFERENCES artists(id),
  year                  INTEGER,
  comments              BLOB,
  lyrics                BLOB,
  bpm                   INTEGER,
  length                INTEGER,
  tracknumber           INTEGER,
  trackcount            INTEGER,
  disknumber            INTEGER,
  diskcount             INTEGER,
  compilation           BOOL,
  bitrate               INTEGER,
  is_vbr                BOOL,
  samplerate            INTEGER,
  replaygain_track_gain FLOAT,
  replaygain_track_peak FLOAT,
  replaygain_album_gain FLOAT,
  replaygain_album_peak FLOAT,
  size                  INTEGER,
  date_added            TIMESTAMP,
  date_updated          TIMESTAMP,
  date_lastplayed       TIMESTAMP,
  playcount             INTEGER,
  skipcount             INTEGER,
  rating                INTEGER
);

CREATE INDEX album_id ON albums(name);
CREATE INDEX artist_id ON artists(name);
CREATE INDEX tag_id ON tags(name);
CREATE INDEX playlist_id ON playlists(name);

CREATE INDEX url_song ON songs(url);
CREATE INDEX album_id_song ON songs(album_id);
CREATE INDEX artist_id_song ON songs(artist_id);
CREATE INDEX year_song ON songs(year);
CREATE INDEX compilation_song ON songs(compilation);

CREATE INDEX taggings_song_id ON taggings(song_id);
CREATE INDEX taggings_tag_id ON taggings(tag_id);

CREATE INDEX playlistcontents_song_id ON playlistcontents(song_id);
CREATE INDEX playlistcontents_playlist_id ON playlistcontents(playlist_id);
"""

songcolumns_plain = ["url", "type", "title",  "year", "bpm",
                     "length", "tracknumber", "trackcount", "disknumber", "diskcount",
                     "compilation", "bitrate", "is_vbr", "samplerate", 
                     "replaygain_track_gain", "replaygain_track_peak",
                     "replaygain_album_gain", "replaygain_album_peak", 
                     "size", "compilation", "date_added", "date_updated", "date_lastplayed",
                     "playcount", "skipcount", "rating"]

songcolumns_indices = ["album_id", "artist_id", "album_artist_id"]
songcolumns_w_indices = songcolumns_plain + songcolumns_indices
songcolumns_lists = ["comments", "lyrics"]
songcolumns_all = songcolumns_w_indices + songcolumns_lists

# secure unpickler which does not accept any instances

import cPickle, cStringIO

def loads(s):
    unpickler = cPickle.Unpickler(cStringIO.StringIO(s))
    unpickler.find_global = None
    return unpickler.load()

def dumps(obj):
    return buffer(cPickle.dumps(obj))

#
# statistical information about songdb
#

class songdbstats:
    def __init__(self, id, type, basedir, location, dbfile, cachesize,
                 numberofsongs, numberofalbums, numberofartists, numberoftags):
        self.id = id
        self.type = type
        self.basedir = basedir
        self.location = location
        self.dbfile = dbfile
        self.cachesize = cachesize
        self.numberofsongs = numberofsongs
        self.numberofalbums = numberofalbums
        self.numberofartists = numberofartists
        self.numberoftags = numberoftags

#
# songdb class
#

class songdb(service.service):

    currentdbversion = 1

    def __init__(self, id, config, songdbhub):
        service.service.__init__(self, "%r songdb" % id, hub=songdbhub)
        self.id = id
        self.basedir = config.musicbasedir
        self.dbfile = config.dbfile
        self.cachesize = config.cachesize
        self.playingstatslength = config.playingstatslength

        if not os.path.isdir(self.basedir):
            raise errors.configurationerror("musicbasedir '%r' of database %r is not a directory." % 
                                            (self.basedir, self.id))

        if not os.access(self.basedir, os.X_OK | os.R_OK):
            raise errors.configurationerror("you are not allowed to access and read config.general.musicbasedir.")

        # currently active cursor - initially, none
        self.cur = None

        # we need to be informed about database changes
        self.channel.subscribe(events.add_song, self.add_song)
        self.channel.subscribe(events.update_song, self.update_song)
        self.channel.subscribe(events.delete_song, self.delete_song)
        self.channel.subscribe(events.song_played, self.song_played)
        self.channel.subscribe(events.song_skipped, self.song_skipped)

        self.channel.subscribe(events.add_playlist, self.add_playlist)
        self.channel.subscribe(events.update_playlist, self.update_playlist)
        self.channel.subscribe(events.delete_playlist, self.delete_playlist)

        self.channel.subscribe(events.clearstats, self.clearstats)

        # we are a database service provider...
        self.channel.supply(requests.getdatabasestats, self.getdatabasestats)
        self.channel.supply(requests.getsong_metadata, self.getsong_metadata)
        self.channel.supply(requests.getartists, self.getartists)
        self.channel.supply(requests.getalbums, self.getalbums)
        self.channel.supply(requests.gettag_id, self.gettag_id)
        self.channel.supply(requests.getsongs, self.getsongs)
        self.channel.supply(requests.getnumberofsongs, self.getnumberofsongs)
        self.channel.supply(requests.getnumberofalbums, self.getnumberofalbums)
        self.channel.supply(requests.getnumberofartists, self.getnumberofartists)
        self.channel.supply(requests.getnumberoftags, self.getnumberoftags)
        self.channel.supply(requests.getnumberofratings, self.getnumberofratings)
        self.channel.supply(requests.gettags, self.gettags)
        self.channel.supply(requests.getratings, self.getratings)
        self.channel.supply(requests.getlastplayedsongs, self.getlastplayedsongs)
        self.channel.supply(requests.getplaylists, self.getplaylists)

        self.autoregisterer = songautoregisterer(self.basedir, self.id, self.isbusy,
                                                 config.tracknrandtitlere, config.postprocessors)
        self.autoregisterer.start()

    def run(self):
        # self.con = sqlite.connect(":memory:")
        log.debug("dbfile: '%r'" % self.dbfile)
        self.con = sqlite.connect(self.dbfile)
        self.con.row_factory = sqlite.Row

        dbversion = self.con.execute("PRAGMA user_version").fetchone()[0]
        log.debug("Found on-disk db version: %d" % dbversion)
        if dbversion == 0:
            # fresh database
            self._txn_begin()
            self.con.executescript(create_tables)
            self._txn_commit()
            self.con.execute("PRAGMA user_version=%d" % self.currentdbversion)
        log.debug("Starting db sevice")
        service.service.run(self)
        self.close()

    def close(self):
        self.con.close()

    # transaction machinery

    def _txn_begin(self):
        if self.cur:
            raise RuntimeError("more than one transaction in parallel is not supported")
        # self.con.execute("BEGIN TRANSACTION")
        self.cur = self.con.cursor()

    def _txn_commit(self):
        # self.con.execute("COMMIT TRANSACTION")
        self.cur.close()
        self.con.commit()
        self.cur = None

    def _txn_abort(self):
        # self.con.execute("ROLLBACK")
        self.con.rollback()
        self.cur.close()
        self.cur = None

    # resetting db stats

    def _clearstats(self):
        self._txn_begin()
        try:
            self.cur.execute("DELETE FROM playstats")
            self.cur.execute("UPDATE songs SET playcount = 0, skipcount = 0, date_lastplayed = NULL ")

        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    #
    # methods for adding, updating and deleting songs
    #

    # helper methods

    def _queryindex(self, table, indexnames, values):
        " query indexnames in table and return id "
        newindexentry = False
        wheres = " AND ".join(["%s = ?" % indexname for indexname in indexnames])
        self.cur.execute("SELECT id FROM %s WHERE %s" % (table, wheres), values)
        r = self.cur.fetchone()
        return r["id"]

    def _queryregisterindex(self, table, indexnames, values):
        " register in table and return if tuple (id, newentry) "
        newindexentry = False
        wheres = " AND ".join(["%s = ?" % indexname for indexname in indexnames])
        self.cur.execute("SELECT id FROM %s WHERE %s" % (table, wheres), values)
        r = self.cur.fetchone()
        if r is None:
            self.cur.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(indexnames),
                                                                  ", ".join(["?"]*len(indexnames))), 
                             values)
            self.cur.execute("SELECT id FROM %s WHERE %s" % (table, wheres), values)
            r = self.cur.fetchone()
            newindexentry = True
        return r["id"], newindexentry

    def _checkremoveindex(self, indextable, reftable, indexnames, value):
        "remove entry from indextable if no longer referenced in reftable and return whether this has happened"
        if value is None:
            return False
        wheres = " OR ".join(["%s = ?" % indexname for indexname in indexnames])
        num = self.cur.execute("SELECT count(*) FROM %s WHERE (%s)" % (reftable, wheres),
                               [value]*len(indexnames)).fetchone()[0]
        if num == 0:
            self.cur.execute("DELETE FROM %s WHERE id = ?" % indextable, [value])
            return True
        else:
            return False

    _song_insert = "INSERT INTO songs (%s) VALUES (%s)" % (",".join(songcolumns_all),
                                                           ",".join(["?"] * len(songcolumns_all)))

    def _add_song(self, song):
        """add song metadata to database"""
        log.debug("adding song: %r" % song)

        if not isinstance(song, metadata.song_metadata):
            log.error("add_song: song has to be a meta.song instance, not a %r instance" % 
                      song.__class__)
            return

        self._txn_begin()
        try:
            # query and register artist, album_artist and album
            if song.artist:
                song.artist_id, newartist = self._queryregisterindex("artists", ["name"], [song.artist])
            else:
                song.artist_id, newartist = None, False
            if song.album_artist:
                song.album_artist_id, newartist2 = self._queryregisterindex("artists", ["name"], 
                                                                            [song.album_artist])
                newartist = newartist or newartist2
                if song.album:
                    song.album_id, newalbum = self._queryregisterindex("albums", ["artist_id", "name"], 
                                                                       [song.album_artist_id, song.album])
                else:
                    song.album_id, newalbum = None, False
            else:
                song.album_artist_id = None
                song.album_id = None
                newalbum = False

            # pickle the comments and lyrics lists
            comments = dumps(song.comments)
            lyrics = dumps(song.lyrics)

            # register song
            self.cur.execute(self._song_insert,
                             [getattr(song, columnname) for columnname in songcolumns_w_indices] + [comments, lyrics])

            self.cur.execute("SELECT id FROM songs WHERE url = ?", (song.url,))
            r = self.cur.fetchone()
            song_id = r["id"]

            # register song tags
            newtag = False
            for tag in song.tags:
                tag_id, newtag2 = self._queryregisterindex("tags", ["name"], [tag])
                newtag = newtag or newtag2
                self.cur.execute("INSERT INTO taggings (song_id, tag_id) VALUES (?, ?)", 
                                 (song_id, tag_id))
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            if newartist:
                hub.notify(events.artistschanged(self.id))
            if newalbum:
                hub.notify(events.albumschanged(self.id))
            if newtag:
                hub.notify(events.tagschanged(self.id))
            # we don't issue a songschanged event because the resulting queries put a too high load 
            # on the database
            # hub.notify(events.songschanged(self.id))

            #for r in cur.execute("SELECT id, name FROM artists"):
            #    log.info("AR: %r %r" % (r["id"], r["name"]))
            #for r in cur.execute("SELECT id, artist_id, name FROM albums"):
            #    log.info("AL: %r %r %r" % (r["id"], r["artist_id"], r["name"]))
            #for r in cur.execute("SELECT id, title FROM songs"):
            #    log.info("S: %r %r" % (r["id"], r["title"]))

    def _delete_song(self, song):
        """delete song from database"""
        log.debug("delete song: %r" % song)
        if not isinstance(song, item.song):
            log.error("_delete_song: song has to be a item.song instance, not a %r instance" % song.__class__)

        self._txn_begin()
        try:
            # remove song
            self.cur.execute("DELETE FROM songs WHERE id = ?", [song.id])

            # remove corresponding album and artists
            deletedalbum = self._checkremoveindex("albums", "songs", ["album_id"], song.album_id)
            deletedartist = self._checkremoveindex("artists", "songs", ["album_artist_id", "artist_id"], 
                                                   song.artist_id)
            deletedartist |= self._checkremoveindex("artists", "songs", ["album_artist_id", "artist_id"], 
                                                    song.album_artist_id)


            # query tags in order to be able to delete them (as opposed to album_id, etc.,
            # they are not stored in item.song)
            tag_ids = []
            for r in self.cur.execute("""SELECT DISTINCT tags.id AS tag_id FROM tags
                                         JOIN taggings ON (taggings.tag_id =tags.id)
                                         WHERE taggings.song_id = ?""", [song.id]):
                tag_ids.append(r["tag_id"])

            # remove taggings
            deletedtag = False
            self.cur.execute("DELETE FROM taggings WHERE song_id = ?", [song.id])
            for tag_id in tag_ids:
                deletedtag |= self._checkremoveindex("tags", "taggings", ["tag_id"], tag_id)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            if deletedartist:
                hub.notify(events.artistschanged(self.id))
            if deletedalbum:
                hub.notify(events.albumschanged(self.id))
            if deletedtag:
                hub.notify(events.tagschanged(self.id))
        # XXX send event?

    _song_update = ( "INSERT OR REPLACE INTO songs (id, %s) VALUES (?, %s)" % 
                     (",".join(songcolumns_all), ",".join(["?"] * len(songcolumns_all))) )

    def _update_song(self, song):
        """updates entry of song"""
        log.debug("updating song %r" % song)
        if not isinstance(song, item.song):
            log.error("_update_song: song has to be a item.song instance, not a %r instance" %
                      newsong.__class__)
            return
        if not song.song_metadata:
            log.error("_update_song: song doesn't contain song metadata")
            return
        oldsong = self._getsong_metadata(song.id)

        self._txn_begin()
        try:

            # query artist, album_artist and album of oldsong (in comparison to the _add_song method, we do not have
            # to add entries to the indices
            if oldsong.artist:
                oldsong.artist_id = self._queryindex("artists", ["name"], [oldsong.artist])
            else:
                oldsong.artist_id = None
            if oldsong.album_artist:
                oldsong.album_artist_id = self._queryindex("artists", ["name"], [oldsong.album_artist])
                if oldsong.album:
                    oldsong.album_id = self._queryindex("albums", ["artist_id", "name"], [oldsong.album_artist_id, oldsong.album])
                else:
                    oldsong.album_id = None
            else:
                oldsong.album_artist_id = None
                oldsong.album_id = None

            # flags for changes of corresponding tables
            changedartists = False
            changedalbums = False
            changedtags = False
            # register new artists, album_artists and albums if necessary
            if oldsong.artist != song.artist:
                if song.artist:
                    song.artist_id, newartist = self._queryregisterindex("artists", ["name"], [song.artist])
                    changedartists |= newartist
                else:
                    song.artist_id = None
            if oldsong.album_artist != song.album_artist:
                if song.album_artist:
                    song.album_artist_id, newartist = self._queryregisterindex("artists", ["name"], [song.album_artist])
                    changedartists |= newartist
                    if song.album:
                        song.album_id, newalbum = self._queryregisterindex("albums", ["artist_id", "name"], 
                                                                           [song.album_artist_id, song.album])
                        changedalbums |= newalbum
                    else:
                        song.album_id = None
                else:
                    song.album_artist_id = None
                    song.album_id = None
            elif oldsong.album != song.album and song.album:
                # only the album name changed
                song.album_id, newalbum = self._queryregisterindex("albums", ["artist_id", "name"], 
                                                                   [song.album_artist_id, song.album])
                changedalbums |= newalbum

            # encode the comments and lyrics lists
            comments = dumps(song.comments)
            lyrics = dumps(song.lyrics)

            # update songs table
            self.cur.execute(self._song_update, 
                            [song.id]+[getattr(song, columnname) for columnname in songcolumns_w_indices] + [comments, lyrics])

            # delete old artists, album_artists and albums if necessary
            # we have to do this after the songs table has been updated, otherwise we
            # cannot detect whether we have to remove an album/artist or not
            if oldsong.album != song.album:
                changedalbums |= self._checkremoveindex("albums", "songs", ["album_id"], song.album_id)
            if oldsong.artist != song.artist:
                changedartists |= self._checkremoveindex("artists", "songs", ["album_artist_id", "artist_id"],
                                                         oldsong.artist_id)
            if oldsong.album_artist != song.album_artist:
                changedartists |= self._checkremoveindex("artists", "songs", ["album_artist_id", "artist_id"],
                                                         oldsong.album_artist_id)

            # update tag information if necessary
            if oldsong.tags != song.tags:
                # check for new tags
                for tag in song.tags:
                    if tag not in oldsong.tags:
                        tag_id, newtag = self._queryregisterindex("tags", ["name"], [tag])
                        changedtags |= newtag
                        self.cur.execute("INSERT INTO taggings (song_id, tag_id) VALUES (?, ?)", 
                                         (song.id, tag_id))
                # check for removed tags
                for tag in oldsong.tags:
                    if tag not in song.tags:
                        tag_id = self._queryregisterindex("tags", ["name"], [tag])[0]
                        self.cur.execute("DELETE FROM taggings WHERE (tag_id = ? AND song_id = ?)", [tag_id, song.id])
                        changedtags |= self._checkremoveindex("tags", "taggings", ["tag_id"], tag_id)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            if changedartists:
                hub.notify(events.artistschanged(self.id))
            if changedalbums:
                hub.notify(events.albumschanged(self.id))
            if changedtags:
                hub.notify(events.tagschanged(self.id))
        hub.notify(events.songchanged(self.id, song))

    def _song_played(self, song, date_played):
        """register playing of song"""
        log.debug("playing song: %r" % song)
        if not isinstance(song, item.song):
            log.error("_update_song: song has to be an item.song instance, not a %r instance" % song.__class__)
            return
        self._txn_begin()
        try:
            self.cur.execute("INSERT INTO playstats (song_id, date_played) VALUES (?, ?)", [song.id, date_played])
            self.cur.execute("UPDATE songs SET playcount = playcount+1, date_lastplayed = ? WHERE id = ?", [date_played, song.id])
            song.playcount += 1
            song.date_lastplayed = date_played
            song.dates_played.append(date_played)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
        hub.notify(events.songchanged(self.id, song))

    def _song_skipped(self, song):
        """register skipping of song"""
        log.debug("skipping song: %r" % song)
        if not isinstance(song, item.song):
            log.error("_update_song: song has to be an item.song instance, not a %r instance" % song.__class__)
            return
        self._txn_begin()
        try:
            self.cur.execute("UPDATE songs SET skipcount = skipcount+1 WHERE id = ?", [song.id])
            song.skipcount += 1
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
        hub.notify(events.songchanged(self.id, song))

    def _add_playlist(self, name, songs):
        log.debug("adding playlist %r" % name)
        if not songs:
            log.error("_add_playlist: cannot add empty playlist")

        self._txn_begin()
        try:
            self.cur.execute("INSERT OR REPLACE INTO playlists (name) VALUES (?)", [name])
            self.cur.execute("SELECT id FROM playlists WHERE name = ?", [name])
            r = self.cur.fetchone()
            playlist_id = r["id"]
            for position, song in enumerate(songs):
                self.cur.execute("INSERT INTO playlistcontents (playlist_id, song_id, position) VALUES (?, ?, ?)",
                                 [playlist_id, song.id, position + 1])
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    def _delete_playlist(self, playlist):
        """delete playlist from database"""
        if not self.playlists.has_key(playlist.id):
            raise KeyError

        log.debug("delete playlist: %r" % playlist)
        self._txn_begin()
        try:
            self.playlists.delete(playlist.id, txn=self.cur)
            hub.notify(events.dbplaylistchanged(self.id, playlist))
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    _update_playlist = _add_playlist

    # read-only methods for accesing the database

    ##########################################################################################
    # !!! It is not save to call any of the following methods when a transaction is active !!!
    ##########################################################################################

    _song_select = """SELECT %s, artists.name AS artist, albums.name AS album 
                      FROM songs 
                      LEFT JOIN albums ON albums.id == album_id
                      LEFT JOIN artists ON artists.id == songs.artist_id
                      WHERE songs.id = ?
                      """ % ", ".join([c for c in songcolumns_all if c!="artist_id"])

    _song_tags_select = """SELECT tags.name AS name FROM tags
                           JOIN taggings ON taggings.tag_id = tags.id
                           WHERE taggings.song_id = ?"""

    _song_playstats_select = "SELECT date_played FROM playstats WHERE song_id = ?"

    def _getsong_metadata(self, song_id):
        """return song entry with given song_id"""
        log.debug("Querying song metadata for id=%r" % song_id)
        try:
            r = self.con.execute(self._song_select, [song_id]).fetchone()
            if r:
                # fetch album artist
                if r["album_artist_id"] is not None:
                    select = """SELECT name FROM artists WHERE id = ?"""
                    album_artist = self.con.execute(select, (r["album_artist_id"],)).fetchone()["name"]
                else:
                    album_artist = None

                # fetch tags
                tags = []
                for tr in self.con.execute(self._song_tags_select, [song_id]):
                    tags.append(tr["name"])

                # fetch playstats
                dates_played = []
                for tr in self.con.execute(self._song_playstats_select, [song_id]):
                    dates_played.append(tr["date_played"])

                # generate and populate metadata
                md = metadata.song_metadata()
                for field in songcolumns_plain:
                    md[field] = r[field]
                md.album = r["album"]
                md.artist = r["artist"]
                md.album_artist = album_artist
                md.tags = tags
                md.comments = loads(r["comments"])
                md.lyrics = loads(r["lyrics"])
                md.dates_played = dates_played
                return md
            else:
                log.debug("Song '%d' not found in database" % song_id)
                return None
        except:
            log.debug_traceback()
            return None

    def _gettag_id(self, tag_name):
        return self.con.execute("SELECT id FROM tags WHERE name = ?", [tag_name]).fetchone()[0]

    def _getsongs(self, sort=None, filters=None):
        """ returns songs filtered according to filters"""
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        orderstring = sort and sort.SQL_string() or ""
        args = filters and filters.SQL_args() or []
        select = """SELECT DISTINCT songs.id              AS song_id, 
                                    songs.album_id        AS album_id, 
                                    songs.artist_id       AS artist_id,
                                    songs.album_artist_id AS album_artist_id
                    FROM songs
                    LEFT JOIN artists   ON (songs.artist_id = artists.id)
                    LEFT JOIN albums    ON (songs.album_id = albums.id) 
                    %s
                    %s
                    %s
                    """ % (joinstring, wherestring, orderstring)
        # log.debug(select)
        return  [item.song(self.id, row["song_id"], row["album_id"], row["artist_id"], row["album_artist_id"])
                 for row in self.con.execute(select, args)]

    def _getartists(self, filters=None):
        """return artists filtered according to filters"""
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        args = filters and filters.SQL_args() or []
        select = """SELECT DISTINCT artists.id AS artist_id, artists.name AS artist_name
                    FROM artists 
                    JOIN songs         ON (songs.artist_id = artists.id)
                    LEFT JOIN albums   ON (album_id = albums.id)
                    %s
                    %s
                    ORDER BY artists.name COLLATE NOCASE""" % (joinstring, wherestring)
        # log.debug(select)
        return [item.artist(self.id, row["artist_id"], row["artist_name"], filters)
                for row in self.con.execute(select, args)]

    def _getalbums(self, filters=None):
        """return albums filtered according to filters"""
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        args = filters and filters.SQL_args() or []
        # Hackish, but effective to allow collections show up in artists view
        if filters.contains(item.artistfilter):
            artist_id_column = "artist_id"
        else:
            artist_id_column = "album_artist_id"
        select ="""SELECT DISTINCT albums.id AS album_id, artists.name AS artist_name, albums.name AS album_name
                   FROM albums 
                   JOIN artists  ON (songs.%s = artists.id)
                   JOIN songs    ON (songs.album_id = albums.id)
                   %s
                   %s
                   ORDER BY albums.name COLLATE NOCASE""" % (artist_id_column, joinstring, wherestring)

        # log.debug(select)
        return [item.album(self.id, row["album_id"], row["artist_name"], row["album_name"], filters)
                for row in self.con.execute(select, args)]

    def _gettags(self, filters=None):
        """return tags filtered according to filters"""
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        args = filters and filters.SQL_args() or []
        select ="""SELECT DISTINCT tags.id AS tag_id, tags.name AS tag_name
                   FROM tags
                   JOIN taggings ON (taggings.tag_id = tags.id)
                   JOIN songs ON (songs.id = taggings.song_id)
                   %s
                   %s
                   ORDER BY tags.name COLLATE NOCASE""" % (joinstring, wherestring)
        # log.debug(select)
        return [item.tag(self.id, row["tag_id"], row["tag_name"], filters)
                for row in self.con.execute(select, args)]

    def _getratings(self, filters):
        """return all stored ratings"""
        return []

    def _getlastplayedsongs(self, sort=None, filters=None):
        """return the last played songs"""
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        orderstring = sort and sort.SQL_string() or ""
        args = filters and filters.SQL_args() or []
        select = """SELECT DISTINCT songs.id              AS song_id,
                                    songs.album_id        AS album_id,
                                    songs.artist_id       AS artist_id,
                                    songs.album_artist_id AS album_artist_id,
                                    playstats.date_played AS date_played
                    FROM songs
                    LEFT JOIN artists   ON (songs.artist_id = artists.id)
                    LEFT JOIN albums    ON (songs.album_id = albums.id) 
                    JOIN      playstats ON (songs.id = playstats.song_id)
                    %s
                    %s
                    %s
                    """ % (joinstring, wherestring, orderstring)
        # log.debug(select)
        return  [item.song(self.id, row["song_id"], row["album_id"], row["artist_id"], 
                           row["album_artist_id"], row["date_played"])
                 for row in self.con.execute(select, args)]

    def _getplaylists(self, filters=None):
        joinstring = filters and filters.SQL_JOIN_string() or ""
        wherestring = filters and filters.SQL_WHERE_string() or ""
        args = filters and filters.SQL_args() or []
        select ="""SELECT DISTINCT playlists.id AS playlist_id, playlists.name AS playlist_name
                   FROM playlists
                   JOIN playlistcontents ON (playlistcontents.playlist_id = playlists.id)
                   JOIN songs ON (songs.id = playlistcontents.song_id)
                   %s
                   %s
                   ORDER BY playlists.name COLLATE NOCASE""" % (joinstring, wherestring)
        # JOIN taggings ON (taggings.tag_id = tags.id)
        # log.debug(select)
        return [item.playlist(self.id, row["playlist_id"], row["playlist_name"], filters)
                for row in self.con.execute(select, args)]

    def isbusy(self):
        """ check whether db is currently busy """
        return self.cur is not None or self.channel.queue.qsize()>0

    # event handlers

    def add_song(self, event):
        if event.songdbid == self.id:
            try:
                self._add_song(event.song)
            except KeyError:
                log.debug_traceback()
                pass

    def update_song(self, event):
        if event.songdbid == self.id:
            try:
                self._update_song(event.song)
            except:
                log.debug_traceback()
                pass

    def delete_song(self, event):
        if event.songdbid == self.id:
            try:
                self._delete_song(event.song)
            except:
                log.debug_traceback()
                pass

    def song_played(self, event):
        if event.songdbid == self.id:
            try:
                self._song_played(event.song, event.date_played)
            except KeyError:
                pass

    def song_skipped(self, event):
        if event.songdbid == self.id:
            try:
                self._song_skipped(event.song)
            except KeyError:
                pass

    def add_playlist(self, event):
        if event.songdbid == self.id:
            try: 
                self._add_playlist(event.name, event.songs)
            except:
                pass

    def delete_playlist(self, event):
        if event.songdbid == self.id:
            try:
                self._delete_playlist(event.name)
            except KeyError:
                pass

    def update_playlist(self, event):
        if event.songdbid == self.id:
            try:
                self._update_playlist(event.name, event.songs)
            except KeyError:
                pass

    def clearstats(self, event):
        if event.songdbid == self.id:
            self._clearstats()

    # request handlers

    def getdatabasestats(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return songdbstats(self.id, "local", self.basedir, None, self.dbfile, self.cachesize, 
                           self.getnumberofsongs(request), 
                           self.getnumberofalbums(request),
                           self.getnumberofartists(request),
                           self.getnumberoftags(request))

    def getnumberofsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self.con.execute("SELECT count(*) FROM songs").fetchone()[0]

    def getnumberoftags(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self.con.execute("SELECT count(*) FROM tags").fetchone()[0]

    def getnumberofratings(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return 0

    def getnumberofalbums(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self.con.execute("SELECT count(*) FROM albums").fetchone()[0]

    def getnumberofartists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self.con.execute("SELECT count(*) FROM artists").fetchone()[0]

    def getsong_metadata(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getsong_metadata(song_id=request.song_id)
        except KeyError:
            return None

    def getsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getsongs(request.sort, request.filters)
        except (KeyError, AttributeError, TypeError):
            log.debug_traceback()
            return []

    def getartists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getartists(request.filters)
        except KeyError:
            log.debug_traceback()
            return []

    def getalbums(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getalbums(request.filters)
        except KeyError:
            log.debug_traceback()
            return []

    def gettag_id(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._gettag_id(request.tag_name)
        except:
            log.debug_traceback()
            return None

    def gettags(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._gettags(request.filters)

    def getplaylists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getplaylists(request.filters)

    def getratings(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getratings(request.filters)

    def getlastplayedsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getlastplayedsongs(request.sort, request.filters)


#
# thread for automatic registering and rescanning of songs in database
#

class songautoregisterer(service.service):

    def __init__(self, basedir, songdbid, dbbusymethod,
                 tracknrandtitlere, postprocessors):
        service.service.__init__(self, "songautoregisterer", daemonize=True)
        self.basedir = basedir
        self.songdbid = songdbid
        self.dbbusymethod = dbbusymethod
        self.tracknrandtitlere = tracknrandtitlere
        self.postprocessors = postprocessors
        self.done = False
        # support file extensions
        self.supportedextensions = metadata.getextensions()

        self.channel.subscribe(events.autoregistersongs, self.autoregistersongs)
        self.channel.subscribe(events.autoregisterer_rescansongs, self.autoregisterer_rescansongs)
        self.channel.supply(requests.autoregisterer_queryregistersong, self.autoregisterer_queryregistersong)

    def _notify(self, event):
        """ wait until db is not busy and send event """
        while self.dbbusymethod():
            time.sleep(0.1)
        hub.notify(event, -100)

    def _request(self, request):
        """ wait until db is not busy and send event """
        while self.dbbusymethod():
            time.sleep(0.1)
        return hub.request(request, -100)

    def _registerorupdatesong(self, path, force):
        """ register or update song in database and return it

        If force is set, the mtime of the song file is ignored.
        """
        if not path.startswith(self.basedir):
            log.error("Path of song not in basedir of database")
            return None

        # generate url corresponding to song
        if self.basedir.endswith("/"):
           relpath = path[len(self.basedir):]
        else:
           relpath = path[len(self.basedir)+1:]

        song_url = u"file://" + encoding.decode_path(relpath)
        urlfilter = item.filters((item.urlfilter(song_url),))
        songs = self._request(requests.getsongs(self.songdbid, filters=urlfilter))

        if songs:
            # there is exactly one resulting song
            song = songs[0]
            song.song_metadata = self._request(requests.getsong_metadata(self.songdbid, song.id))
            try:
                if force or song.song_metadata.date_updated < os.stat(path).st_mtime:
                    # the song has changed since the last update
                    newsong_metadata = metadata.metadata_from_file(relpath, self.basedir, self.tracknrandtitlere, self.postprocessors)
                    song.song_metadata.update(newsong_metadata)
                    self._notify(events.update_song(self.songdbid, song))
                    log.debug("registerer: song '%r' rescanned" % song_url)
                else:
                    log.debug("registerer: not scanning unchanged song '%r'" % song_url)
            except (IOError, OSError, RuntimeError):
                log.debug("registerer: song '%r' can no longer be read. deleting it from db" % song_url)
                self._notify(events.delete_song(self.songdbid, song))
        else:
            # song was not stored in database
            newsong_metadata = metadata.metadata_from_file(relpath, self.basedir, self.tracknrandtitlere, self.postprocessors)
            self._notify(events.add_song(self.songdbid, newsong_metadata))
            # fetch new song from database
            song = self._request(requests.getsongs(self.songdbid, filters=urlfilter))[0]
        return song

    def registerdirtree(self, dir, oldsongs, force):
        """ scan for songs in dir and its subdirectories, removing those scanned from the set oldsongs. 

        If force is set, the m_time of a song is ignored and the song is always scanned.
        """
        log.debug("registerer: entering %r"% dir)
        self.channel.process()
        if self.done: return
        songpaths = []

        # scan for paths of songs and recursively call registering of subdirectories
        for name in os.listdir(dir):
            path = os.path.join(dir, name)
            extension = os.path.splitext(path)[1].lower()
            if os.access(path, os.R_OK):
                if os.path.isdir(path):
                    try:
                        self.registerdirtree(path, oldsongs, force)
                    except (IOError, OSError), e:
                        log.warning("songautoregisterer: could not enter dir %r: %r" % (path, e))
                elif extension in self.supportedextensions:
                    songpaths.append(path)

        # now register songs...
        songs = []
        for path in songpaths:
            try:
                song = self._registerorupdatesong(path, force)
                # remove song from list of songs to be checked (if present)
                oldsongs.discard(song)
            except (IOError, OSError):
                # if the registering or update failed we do nothing and the song
                # will be deleted from the database later on
                pass
            except:
                # but in case of non-IO exceptions report them in debugging mode
                log.debug_traceback()
        log.debug("registerer: leaving %r"% dir)

    def rescansong(self, song, force):
        if song.songdbid != self.songdbid:
            log.debug("Trying to rescan song in wrong database")
            return
        if song.song_metadata is None:
            song.song_metadata = self._request(requests.getsong_metadata(self.songdbid, song.id))
            if song.song_metadata is None:
                log.debug("Song not found in database")
                return
        if not song.url.startswith("file://"):
            log.debug("Can only rescan local files")
            return
        relpath = encoding.encode_path(song.url[7:])
        path = os.path.join(self.basedir, relpath)
        try:
            if force or song_metadata.date_updated < os.stat(path).st_mtime:
                newsong_metadata = metadata.metadata_from_file(relpath, self.basedir, self.tracknrandtitlere, self.postprocessors)
                song.song_metadata.update(newsong_metadata)
                self._notify(events.update_song(self.songdbid, song))
        except (IOError, OSError):
            log.debug_traceback()
            # if anything goes wrong, we delete the song from the database
            self._notify(events.delete_song(self.songdbid, song))

    def rescanplaylist(self, playlist):
        if playlist.songdbid != self.songdbid:
            log.debug("Trying to rescan playlist in wrong database")
            return
        name = playlist.name
        if name[-4:] != ".m3u":
            name = name + ".m3u"
        try:
            path = os.path.join(configmodule.general.playlistdir, name)
            file = open(path, "r")
            songs = []
            for line in file.xreadlines():
                if not line.startswith("#"):
                    song = self._registerorupdatesong(line.strip(), force=False)
                    if song:
                        songs.append(song)
            file.close()
            self._notify(events.update_playlist(self.songdbid, playlist.name, songs))
        except (IOError, OSError):
            self._notify(events.delete_playlist(self.songdbid, playlist.name))

    #
    # event handler
    #

    def autoregistersongs(self, event):
        if self.songdbid == event.songdbid:
            oldsongs = set(hub.request(requests.getsongs(self.songdbid)))
            log.info(_("database %r: scanning for songs in %r (currently %d songs registered)") % (self.songdbid, self.basedir, len(oldsongs)))

            # scan for all songs in the filesystem
            log.debug("database %r: searching for new songs" % self.songdbid)
            self.registerdirtree(self.basedir, oldsongs, event.force)

            # remove songs which have not yet been scanned and thus are not accesible anymore
            log.info(_("database %r: removing %d stale songs") % (self.songdbid, len(oldsongs)))
            for song in oldsongs:
                self._notify(events.delete_song(self.songdbid, song))

            playlists = hub.request(requests.getplaylists(self.songdbid))
            log.info(_("database %r: rescanning %d playlists") % (self.songdbid, len(playlists)))
            for playlist in playlists:
                self.rescanplaylist(playlist)

            nrsongs = hub.request(requests.getnumberofsongs(self.songdbid))
            log.info(_("database %r: rescan finished (%d songs registered)") % (self.songdbid, nrsongs))

    def autoregisterer_rescansongs(self, event):
        if self.songdbid == event.songdbid:
            log.info(_("database %r: rescanning %d songs%s") % (self.songdbid, len(event.songs), event.force and _(" (full)") or ""))
            for song in event.songs:
                self.rescansong(song, event.force)
            log.info(_("database %r: finished rescanning %d songs") % (self.songdbid, len(event.songs)))

    def autoregisterer_queryregistersong(self, request):
        if self.songdbid != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._registerorupdatesong(request.path, force=False)
        except:
            return None
