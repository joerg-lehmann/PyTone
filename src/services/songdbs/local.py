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

import os
import errno
import sys
import time
import bsddb.dbshelve
import bsddb.db

import events, hub, requests
import errors
import log
import metadata
import dbitem
import service


class mydbshelve(bsddb.dbshelve.DBShelf):
    def __init__(self, filename, flags=bsddb.db.DB_CREATE, mode=0660, filetype=bsddb.db.DB_HASH, dbenv=None, dbname=None):
        bsddb.dbshelve.DBShelf.__init__(self, dbenv)
        self.open(filename, dbname, filetype, flags, mode)
        self.set_get_returns_none(0)

    def has_key(self, key, txn=None):
        try:
            value = self.get(key, txn=txn)
        except KeyError:
            return False
        return True

class dbenv:

    def __init__(self, dbenvdir, cachesize):
        self.dbenvdir = dbenvdir
        self.cachesize = cachesize

        try:
            os.mkdir(self.dbenvdir, 02775)
        except OSError, e:
            if e.errno != errno.EEXIST: raise

        # setup db environment
        self.dbenv = bsddb.db.DBEnv()

        # calculate cache parameters for bsddb for cachesize in kB
        # the factor 1000 is taken from zodb.storage.base
        gbytes, bytes = divmod(self.cachesize*1024, 1024 * 1024 * 1000)
        self.dbenv.set_cachesize(gbytes, bytes)

        # set maximal size of log file to 0.5MB and enable its automatic removal if supported
        self.dbenv.set_lg_max(1024*1024)
        try:
            self.dbenv.set_flags(bsddb.db.DB_LOG_AUTOREMOVE, 1)
        except AttributeError:
            pass

        self.dbenv.open(self.dbenvdir,
                        bsddb.db.DB_CREATE |
                        bsddb.db.DB_INIT_MPOOL |
                        bsddb.db.DB_INIT_LOG |
                        bsddb.db.DB_INIT_TXN |
                        bsddb.db.DB_RECOVER |
                        bsddb.db.DB_PRIVATE
                        )

        self.tables = []

    def openshelve(self, filename, flags, dbname=None):
        # automatically commit database open
        flags |= bsddb.db.DB_AUTO_COMMIT
        shelve = mydbshelve(filename, flags=flags, dbenv=self.dbenv, dbname=dbname)
        self.tables.append(shelve)
        return shelve

    def close(self):
        for table in self.tables:
            table.close()
        # Checkpoint the database twice, as recommended by Sleepycat
        self.checkpoint()
        self.checkpoint()

        self.dbenv.close()
        self.dbenv = None

    def txn_begin(self):
        return self.dbenv.txn_begin()

    def txn_commit(self):
        self.dbenv.txn.commit()

    def txn_abort(self):
        self.dbenv.txn.abort()

    def checkpoint(self):
        """flush memory pool, write checkpoint record to log and flush flog"""
        # this sometimes results in an intermittent error (no idea why)
        log.debug("checkpointing database")
        try:
            self.dbenv.txn_checkpoint(0, 0, bsddb.db.DB_FORCE)
        except bsddb._db.DBInvalidArgError:
            # we just try again:
            try:
                self.dbenv.txn_checkpoint(0, 0, bsddb.db.DB_FORCE)
            except bsddb._db.DBInvalidArgError:
                # if it still doesn't work, we don't feel responsible
                # anymore and just log the error
                log.warning("checkpointing the database failed with DBInvalidArgError\n")
                return

        # delete log files (even when DB_LOG_AUTOREMOVE is not supported)
        for logfile in self.dbenv.log_archive(bsddb.db.DB_ARCH_ABS):
            os.unlink(logfile)

#
# statistical information about songdb
#

class songdbstats:
    def __init__(self, id, type, basedir, location, dbenvdir, cachesize,
                 numberofsongs, numberofalbums, numberofartists, numberofgenres, numberofdecades):
        self.id = id
        self.type = type
        self.basedir = basedir
        self.location = location
        self.dbenvdir = dbenvdir
        self.cachesize = cachesize
        self.numberofsongs = numberofsongs
        self.numberofalbums = numberofalbums
        self.numberofartists = numberofartists
        self.numberofgenres = numberofgenres
        self.numberofdecades = numberofdecades

#
# songdb class
#

# interval in seconds after which logs are flushed
checkpointinterval = 60

class songdb(service.service):
    def __init__(self, id, config, songdbhub):
        service.service.__init__(self, "%s songdb" % id, hub=songdbhub)
        self.id = id
        self.songdbbase = config.basename
        self.dbfile = "db"
        self.basedir = config.musicbasedir
        self.playingstatslength = config.playingstatslength
        self.tracknrandtitlere = config.tracknrandtitlere
        self.tagcapitalize = config.tags_capitalize
        self.tagstripleadingarticle = config.tags_stripleadingarticle
        self.tagremoveaccents = config.tags_removeaccents
        self.dbenvdir = config.dbenvdir
        self.cachesize = config.cachesize

        if not os.path.isdir(self.basedir):
            raise errors.configurationerror("musicbasedir '%s' of database %s is not a directory." % (self.basedir, self.id))

        if not os.access(self.basedir, os.X_OK | os.R_OK):
            raise errors.configurationerror("you are not allowed to access and read config.general.musicbasedir.")

        self.dbenv = dbenv(self.dbenvdir, self.cachesize)

        # We keep the year index still around although we do not use it anymore.
        # otherwise we run into troubles when upgrading from the old mulit-file layout
        self.indices = ["genre", "decade", "rating"]

        # currently active transaction - initially, none
        self.txn = None

        try:
            self._initdb()
        except:
            raise errors.databaseerror("cannot initialise/open song database files.")

        # we need to be informed about database changes
        self.channel.subscribe(events.updatesong, self.updatesong)
        self.channel.subscribe(events.rescansong, self.rescansong)
        self.channel.subscribe(events.delsong, self.delsong)
        self.channel.subscribe(events.updateplaylist, self.updateplaylist)
        self.channel.subscribe(events.delplaylist, self.delplaylist)
        self.channel.subscribe(events.updatealbum, self.updatealbum)
        self.channel.subscribe(events.updateartist, self.updateartist)
        self.channel.subscribe(events.registersongs, self.registersongs)
        self.channel.subscribe(events.registerplaylists, self.registerplaylists)
        self.channel.subscribe(events.clearstats, self.clearstats)

        # regularly flush the database log
        self.channel.subscribe(events.checkpointdb, self.checkpointdb)
        # send this event to normal hub, since otherwise the timer service does not get it
        hub.notify(events.sendeventin(events.checkpointdb(self.id), checkpointinterval, repeat=checkpointinterval))

        # we are a database service provider...
        self.channel.supply(requests.getdatabasestats, self.getdatabasestats)
        self.channel.supply(requests.queryregistersong, self.queryregistersong)
        self.channel.supply(requests.getartists, self.getartists)
        self.channel.supply(requests.getalbums, self.getalbums)
        self.channel.supply(requests.getalbum, self.getalbum)
        self.channel.supply(requests.getartist, self.getartist)
        self.channel.supply(requests.getsong, self.getsong)
        self.channel.supply(requests.getsongs, self.getsongs)
        self.channel.supply(requests.getnumberofsongs, self.getnumberofsongs)
        self.channel.supply(requests.getnumberofalbums, self.getnumberofalbums)
        self.channel.supply(requests.getnumberofartists, self.getnumberofartists)
        self.channel.supply(requests.getnumberofgenres, self.getnumberofgenres)
        self.channel.supply(requests.getnumberofdecades, self.getnumberofdecades)
        self.channel.supply(requests.getnumberofratings, self.getnumberofratings)
        self.channel.supply(requests.getgenres, self.getgenres)
        self.channel.supply(requests.getdecades, self.getdecades)
        self.channel.supply(requests.getratings, self.getratings)
        self.channel.supply(requests.getlastplayedsongs, self.getlastplayedsongs)
        self.channel.supply(requests.gettopplayedsongs, self.gettopplayedsongs)
        self.channel.supply(requests.getlastaddedsongs, self.getlastaddedsongs)
        self.channel.supply(requests.getplaylist, self.getplaylist)
        self.channel.supply(requests.getplaylists, self.getplaylists)
        self.channel.supply(requests.getsongsinplaylist, self.getsongsinplaylist)
        self.channel.supply(requests.getsongsinplaylists, self.getsongsinplaylists)

        self.autoregisterer = songautoregisterer(self.basedir, self.id, self.isbusy,
                                                 self.tracknrandtitlere,
                                                 self.tagcapitalize, self.tagstripleadingarticle, self.tagremoveaccents)
        self.autoregisterer.start()

    def _initdb(self):
        """ initialise database using modern bsddb interface of Python 2.3 and above """

        openflags = bsddb.db.DB_CREATE

        self.songs = self.dbenv.openshelve(self.dbfile, flags=openflags, dbname="songs")
        self.artists = self.dbenv.openshelve(self.dbfile, flags=openflags, dbname="artists")
        self.albums = self.dbenv.openshelve(self.dbfile, flags=openflags, dbname="albums")
        self.playlists = self.dbenv.openshelve(self.dbfile, flags=openflags, dbname="playlists")
        for index in self.indices:
            setattr(self, index+"s", self.dbenv.openshelve(self.dbfile, flags=openflags, dbname=index+"s"))
        self.stats = self.dbenv.openshelve(self.dbfile, flags=openflags, dbname="stats")

        # check whether we have to convert from an old multi-file database layout
        if self.songdbbase:
            songdbprefix = self.songdbbase
            if os.path.exists(songdbprefix + "_CONVERTED"):
                log.warning(_('using new database, please set "basename=" in [database.%s] section of your config file') % self.id)
            else:
                self._convertfromoldfilelayout()

        log.info(_("database %s: basedir %s, %d songs, %d artists, %d albums, %d genres, %d playlists") %
                 (self.id, self.basedir, len(self.songs),  len(self.artists),  len(self.albums),
                  len(self.genres), len(self.playlists)))

        # check whether we have to deal with a newly created database
        if not self.stats:
            try:
                self._txn_begin()
                # insert lists into statistics db
                if not "topplayed" in self.stats.keys():
                    self.stats.put("topplayed", [], txn=self.txn)
                if not "lastplayed" in self.stats.keys():
                    self.stats.put("lastplayed", [], txn=self.txn)
                if not "lastadded" in self.stats.keys():
                    self.stats.put("lastadded", [], txn=self.txn)

                # set version number for new, empty database
                self.stats.put("db_version", 5, txn=self.txn)

                # set database version for older databases
                if not self.stats.has_key("db_version", txn=self.txn):
                    self.stats.put("db_version", 1, txn=self.txn)

                # delete old version of lastplayed list
                if self.stats.get("lastplayed", txn=self.txn) and not type(self.stats.get("lastplayed", txn=self.txn)[0]) == type(()):
                    self.stats.put("lastplayed", [], txn=self.txn)
            except:
                self._txn_abort()
                raise
            else:
                self._txn_commit()

        # upgrade database
        if not self.stats.has_key("db_version") or self.stats["db_version"] < 2:
            self._updatefromversion1to2()

        if self.stats["db_version"] < 3:
            self._updatefromversion2to3()

        if self.stats["db_version"] < 4:
            self._updatefromversion3to4()

        if self.stats["db_version"] < 5:
            self._updatefromversion4to5()

        if self.stats["db_version"] > 5:
            raise RuntimeError("database version %d not supported" % self.stats["db_version"])
 
    def _updatefromversion1to2(self):
        """ update from database version 1 to version 2 """

        log.info(_("updating song database %s from version 1 to version 2") % self.id)

        print _("Updating song database %s from version 1 to version 2:") % self.id,
        try:
            self._txn_begin()
            print "%d artists..." % len(self.artists),
            for artistid, artist in self.artists.items(txn=self.txn):
                newalbums = []
                for album in artist.albums:
                    newalbum  = self.albums[album].name
                    newalbums.append(newalbum)
                artist.albums = newalbums
                self.artists.put(artistid, artist, txn=self.txn)

            print "%d genres..." % len(self.genres),
            for genreid, genre in self.genres.items(txn=self.txn):
                newalbums = []
                for album in genre.albums:
                    newalbum = self.albums[album].name
                    newalbums.append(newalbum)
                genre.albums = newalbums
                self.genres.put(genreid, genre, self.txn)

            print "%d years..." % len(self.years),
            for yearid, year in self.years.items(txn=self.txn):
                newalbums = []
                for album in year.albums:
                    newalbum  = self.albums[album].name
                    newalbums.append(newalbum)
                year.albums = newalbums
                self.years.put(yearid, year, txn=self.txn)

            print "%d albums..." % len(self.albums),
            for albumid, album in self.albums.items(txn=self.txn):
                if album.name in self.albums:
                    newalbum = self.albums[album.name]
                    newalbum.artists.append(album.artist)
                    newalbum.songs.extend(album.songs)
                    newalbum.genres.extend(album.genres)
                    newalbum.years.extend(album.years)
                else:
                    newalbum = album
                    newalbum.id = album.name
                    newalbum.artists = [album.artist]
                    del newalbum.artist

                self.albums.put(newalbum.id, newalbum, txn=self.txn)
                self.albums.delete(albumid, txn=self.txn)
            print
            self.stats.put("db_version", 2, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            self._checkpoint()
            print "Done"

    def _updatefromversion2to3(self):
        """ update from database version 2 to version 3 """

        log.info(_("updating song database %s from version 2 to version 3") % self.id)
        print _("Updating song database %s from version 2 to version 3:") % self.id,
        if self.basedir.endswith("/"):
           lb = len(self.basedir)
        else:
           lb = len(self.basedir)+1
        try:
            self._txn_begin()
            print "%d songs..." % len(self.songs),
            for songid, song in self.songs.items(txn=self.txn):
                if songid.startswith(self.basedir):
                    song.id = song.id[lb:]
                    self.songs.delete(songid, txn=self.txn)
                    self.songs.put(song.id, song, txn=self.txn)
                else:
                    raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)

            print "%d artists..." % len(self.artists),
            for artistid, artist in self.artists.items(txn=self.txn):
                newsongs = []
                for songid in artist.songs:
                    if songid.startswith(self.basedir):
                        newsongs.append(songid[lb:])
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
                artist.songs = newsongs
                self.artists.put(artistid, artist, txn=self.txn)

            print "%d albums..." % len(self.albums),
            for albumid, album in self.albums.items(txn=self.txn):
                newsongs = []
                for songid in album.songs:
                    if songid.startswith(self.basedir):
                        newsongs.append(songid[lb:])
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
                album.songs = newsongs
                self.albums.put(albumid, album, txn=self.txn)

            print "%d genres..." % len(self.genres),
            for genreid, genre in self.genres.items(txn=self.txn):
                newsongs = []
                for songid in genre.songs:
                    if songid.startswith(self.basedir):
                        newsongs.append(songid[lb:])
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
                genre.songs = newsongs
                self.genres.put(genreid, genre, self.txn)

            print "%d years..." % len(self.years),
            for yearid, year in self.years.items(txn=self.txn):
                newsongs = []
                for songid in year.songs:
                    if songid.startswith(self.basedir):
                        newsongs.append(songid[lb:])
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
                year.songs = newsongs
                self.years.put(yearid, year, txn=self.txn)

            print "lastadded...",
            newlastadded = []
            for songid in self.stats.get("lastadded", txn=self.txn):
                if songid.startswith(self.basedir):
                    newlastadded.append(songid[lb:])
                else:
                    raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
            self.stats.put("lastadded", newlastadded, txn=self.txn)

            print "lastplayed...",
            newlastplayed = []
            try:
                for songid, playingtime in self.stats.get("lastplayed", txn=self.txn):
                    if songid.startswith(self.basedir):
                        newlastplayed.append((songid[lb:], playingtime))
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
            except ValueError:
                # we're dealing with a very old song database from which we cannot use
                # the lastplayed information
                pass
            self.stats.put("lastplayed", newlastplayed, txn=self.txn)

            print "topplayed...",
            newsongs = []
            for songid in self.stats.get("topplayed", txn=self.txn):
                if songid.startswith(self.basedir):
                    newsongs.append(songid[lb:])
                else:
                    raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
            self.stats.put("topplayed", newsongs, txn=self.txn)

            print "%d playlists..." % len(self.playlists)
            for path, playlist in self.playlists.items(txn=self.txn):
                newsongs = []
                for songid in playlist.songs:
                    if songid.startswith(self.basedir):
                        newsongs.append(songid[lb:])
                    else:
                        raise RuntimeError("insconsistency in database: wrong basedir of song '%s'" % songid)
                playlist.songs = newsongs
                self.playlists.put(path, playlist, txn=self.txn)

            print
            self.stats.put("db_version", 3, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            self._checkpoint()
            print "Done"

    def _updatefromversion3to4(self):
        """ update from database version 3 to version 4 """

        log.info(_("updating song database %s from version 3 to version 4") % self.id)
        print _("Updating song database %s from version 3 to version 4:") % self.id

        try:
            self._txn_begin()
            print "%d songs..." % len(self.songs),

            for songid, song in self.songs.items(txn=self.txn):
                if song.rating is not None:
                    song.ratingsource = 0
                else:
                    song.ratingsource = None
                if song.lastplayed:
                    song.lastplayed = [song.lastplayed]
                else:
                    song.lastplayed = []
                self.songs.put(songid, song, txn=self.txn)
                self._indexsong_index(song, "rating")
            print
            self.stats.put("db_version", 4, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            self._checkpoint()
            print "Done"

    def _updatefromversion4to5(self):
        """ update from database version 4 to version 5 """

        log.info(_("updating song database %s from version 4 to version 5") % self.id)
        print _("Updating song database %s from version 4 to version 5:") % self.id

        try:
            self._txn_begin()
            print "%d songs..." % len(self.songs)

            nr = 0
            for songid, song in self.songs.items(txn=self.txn):
                if song.year is not None:
                    song.decade = 10*(song.year//10)
                else:
                    song.decade = None
                self.songs.put(songid, song, txn=self.txn)
                self._indexsong_index(song, "decade")
                nr += 1
                if nr % 100 == 0:
                    print "finished %d/%d songs\r" % (nr, len(self.songs)),
                    sys.stdout.flush()
            print

            # emptying years index (but not removing it, how can we do that?)
            years = self.dbenv.openshelve(self.dbfile, flags=bsddb.db.DB_CREATE, dbname="years")
            print "%d years..." % len(years.keys())
            for year in years.keys():
                years.delete(year, txn=self.txn)
            years.close()

            self.stats.put("db_version", 5, txn=self.txn)
        except:
            self._txn_abort()
            print "Conversion failed - changes have not been comitted"
            raise
        else:
            self._txn_commit()
            self._checkpoint()
            print "Done"

    def _convertfromoldfilelayout(self):
        """ convert databases from old multifile layout """

        log.info(_("converting song database %s from old multifile layout") % self.id)
        print _("converting song database %s from old multifile layout:") % self.id

        assert(len(self.songs) == len(self.artists) == len(self.albums) == len(self.playlists) == 0), "new db has to be empty"

        songdbprefix = self.songdbbase

        try:
            self._txn_begin()
            songs = bsddb.dbshelve.open(songdbprefix + "_songs.db")
            print "%d songs..." % len(songs),
            for songid, song in songs.items():
                self.songs.put(songid, song, txn=self.txn)

            artists = bsddb.dbshelve.open(songdbprefix + "_artists.db")
            print "%d artists..." % len(artists),
            for artistid, artist in artists.items():
                self.artists.put(artistid, artist, txn=self.txn)

            albums = bsddb.dbshelve.open(songdbprefix + "_albums.db")
            print "%d albums..." % len(albums),
            for albumid, album in albums.items():
                self.albums.put(albumid, album, txn=self.txn)

            playlists = bsddb.dbshelve.open(songdbprefix + "_playlists.db")
            print "%d playlists..." % len(albums),
            for playlistid, playlist in playlists.items():
                self.playlists.put(playlistid, playlist, txn=self.txn)

            print "%d indices..." % len(self.indices),
            # We have to hard-wire the index names to the ones used in database version 4
            # except for the year index which does no longer exist in version 5 and thus does
            # not need to be upgraded.
            for indexname in ["genre", "rating"]:
                newindex = getattr(self, indexname+"s")
                oldindex = bsddb.dbshelve.open(songdbprefix + "_"+indexname+"s.db")
                for id, item in oldindex.items():
                    newindex.put(id, item, txn=self.txn)

            print "stats...",
            stats = bsddb.dbshelve.open(songdbprefix + "_stats.db")
            for id, item in stats.items():
                self.stats.put(id, item, txn=self.txn)

            print "marking old db as converted...",
            marker = open(songdbprefix+"_CONVERTED", "w")
            marker.close()
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
            self._checkpoint()
            print "Done"

    def run(self):
        service.service.run(self)
        self.close()

    def close(self):
        self.dbenv.close()

    # transaction machinery

    def _txn_begin(self):
        if self.txn:
            raise RuntimeError("more than one transaction in parallel is not supported")
        self.txn = self.dbenv.txn_begin()

    def _txn_commit(self):
        self.txn.commit()
        self.txn = None

    def _txn_abort(self):
        self.txn.abort()
        self.txn = None

    def _checkpoint(self):
        """flush memory pool, write checkpoint record to log and flush flog"""
        self.dbenv.checkpoint()

    # resetting db stats

    def _clearstats(self):
        try:
            self._txn_begin()
            # insert lists into statistics db 
            self.stats.put("topplayed", [], txn=self.txn)
            self.stats.put("lastplayed", [], txn=self.txn)
            self.stats.put("lastadded", [], txn=self.txn)
            for songid, song in self.songs.items(txn=self.txn):
                song.nrplayed = 0
                song.lastplayed = []
                self.songs.put(songid, song, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    # methods for insertion/update of corresponding index tables

    def _indexsong_album(self, song):
        """ insert/update album information for song """
        # marker: do we have to write new album information
        changed = False

        # insert album in songdb, or fetch existent one from songdb
        try:
            album = self.albums.get(song.album, txn=self.txn)
        except KeyError:
            log.debug("new album: %s" % song.album)
            album = dbitem.album(song.album)
            changed = True
            # hub.notify(events.albumaddedordeleted(self.id, album))

        if song.id not in album.songs:
            changed = True
            album.songs.append(song.id)

        if song.artist not in album.artists:
            changed = True
            album.artists.append(song.artist)

        if changed:
            self.albums.put(song.album, album, txn=self.txn)

    def _unindexsong_album(self, song):
        """ delete album information for song, but do not delete album """
        album = self.albums.get(song.album, txn=self.txn)

        album.songs.remove(song.id)
        
        # list of remaining songs
        osongs = [self.songs.get(songid, txn=self.txn) for songid in album.songs]

        # check whether another song has the same artist
        for osong in osongs:
            if osong.artist == song.artist:
                break
        else:
            album.artists.remove(song.artist)

        if album.songs:
            self.albums.put(song.album, album, txn=self.txn)
        else:
            self.albums.delete(song.album, txn=self.txn)
            hub.notify(events.albumaddedordeleted(self.id, album))

    def _indexsong_artist(self, song):
        """ insert/update artist information for song """
        changed = False

        # insert artist in songdb, or fetch existent one from songdb
        try:
            artist = self.artists.get(song.artist, txn=self.txn)
        except KeyError:
            log.debug("new artist: %s" % song.artist)
            artist = dbitem.artist(song.artist)
            changed = True
            hub.notify(events.artistaddedordeleted(self.id, artist))

        if song.album not in artist.albums:
            changed = True
            artist.albums.append(song.album)

        if song.id not in artist.songs:
            changed = True
            artist.songs.append(song.id)

        if changed:
            self.artists.put(song.artist, artist, txn=self.txn)


    def _unindexsong_artist(self, song):
        """ delete artist information for song, but do not delete artist """
        artist = self.artists.get(song.artist, txn=self.txn)

        artist.songs.remove(song.id)

        # list of remaining songs
        osongs = [self.songs.get(songid, txn=self.txn) for songid in artist.songs]

        # check whether album has already been deleted from album index
        try:
            album = self.albums.get(song.album, txn=self.txn)
            # album is still present 
            if song.artist not in album.artists:
                artist.albums.remove(song.album)
        except KeyError:
            # album has already been deleted
            artist.albums.remove(song.album)

        if artist.songs:
            self.artists.put(song.artist, artist, txn=self.txn)
        else:
            self.artists.delete(song.artist, txn=self.txn)
            hub.notify(events.artistaddedordeleted(self.id, artist))

    # other indices: genre, decade, rating, ...

    def _indexsong_index(self, song, indexname):
        """ insert/update index for song """

        index = getattr(self, indexname+"s")
        # indexid always has to be a string, but we also need the original value
        # if we have to construct a new index entry below
        oindexid = getattr(song, indexname)
        indexid = str(oindexid)

        changed = False

        # insert new index entry in songdb, or fetch existent one from songdb
        try:
            indexentry = index.get(indexid, txn=self.txn)
        except KeyError:
            log.debug("new entry in index %s: %s" % (indexname, indexid))
            indexentry = getattr(dbitem, indexname)(oindexid)
            changed = True
            # XXX no event

        if song.id not in indexentry.songs:
            changed = True
            indexentry.songs.append(song.id)

        if song.artist not in indexentry.artists:
            changed = True
            indexentry.artists.append(song.artist)

        if song.album not in indexentry.albums:
            changed = True
            indexentry.albums.append(song.album)

        if changed:
            index.put(indexid, indexentry, txn=self.txn)

    def _unindexsong_index(self, song, indexname):
        """ delete song from a given index (for instance genre, decade)"""

        index = getattr(self, indexname+"s")
        # indexid always has to be a string 
        indexid = str(getattr(song, indexname))
        indexentry = index.get(indexid, txn=self.txn)

        # remove song itself from the index
        indexentry.songs.remove(song.id)

        # check if either the artist is no longer present, or if it
        # doesn't contain the indexid any longer. In both cases remove
        # it from theindex
        if not self.artists.has_key(song.artist, txn=self.txn):
            indexentry.artists.remove(song.artist)
        else:
            # Note that for querying all songs of a given artist we
            # may not use the usual read methods of the songdb class
            # because we are in a transaction
            songids = self.artists.get(song.artist, txn=self.txn).songs
            songs = [self.songs.get(songid, txn=self.txn)  for songid in songids]
            for asong in songs:
                if getattr(asong, indexname) == getattr(song, indexname):
                    break
            else:
                indexentry.artists.remove(song.artist)

        # same for albums
        if not self.albums.has_key(song.album, txn=self.txn):
            indexentry.albums.remove(song.album)
        else:
            songids = self.albums.get(song.album, txn=self.txn).songs
            songs = [self.songs.get(songid, txn=self.txn)  for songid in songids]
            for asong in songs:
                if getattr(asong, indexname) == getattr(song, indexname):
                    break
            else:
                indexentry.albums.remove(song.album)


        # delete index entry or write it with new values
        if not indexentry.artists:
            assert not indexentry.albums, "inconsistency in database: index entry has no artist but albums" + str(indexentry.albums)
            index.delete(indexid, txn=self.txn)
        else:
            index.put(indexid, indexentry, txn=self.txn)

    # index for statistical information

    def _indexsong_stats(self, song):
        """ insert/update playing (and creation) statistics for song """
        # some assumptions made:
        # - if lastplayed info is changed for a song, this song has been
        #   played and, thus, gets added to the top of the lastplayed list
        lastadded = self.stats.get("lastadded", txn=self.txn)
        lastplayed = self.stats.get("lastplayed", txn=self.txn)
        topplayed = self.stats.get("topplayed", txn=self.txn)

        if not lastadded or self.songs.get(lastadded[0], txn=self.txn).added<song.added:
            lastadded.insert(0, song.id)
            self.stats.put("lastadded", lastadded[:self.playingstatslength], txn=self.txn)

        if song.lastplayed:
            if not lastplayed or lastplayed[0][1] < song.lastplayed[-1]:
                lastplayed.insert(0, (song.id, song.lastplayed[-1]))
                self.stats.put("lastplayed", lastplayed[:self.playingstatslength], txn=self.txn)
            elif lastplayed[0][0] == song.id and lastplayed[0][1] > song.lastplayed[-1]:
                # delete song because it has been unplayed
                del lastplayed[0]
                self.stats.put("lastplayed", lastplayed[:self.playingstatslength], txn=self.txn)
        elif lastplayed and lastplayed[0][0] == song.id:
            # delete song because it has been unplayed
            del lastplayed[0]
            self.stats.put("lastplayed", lastplayed[:self.playingstatslength], txn=self.txn)

        try:
            topplayed.remove(song.id)
        except ValueError:
            pass

        if song.nrplayed:
            for i in range(len(topplayed)):
                asong = self.songs.get(topplayed[i], txn=self.txn)
                if (asong.nrplayed < song.nrplayed or
                    (asong.nrplayed == song.nrplayed and asong.lastplayed[-1] < song.lastplayed[-1])):
                    topplayed.insert(i, song.id)
                    break
            else:
                topplayed.append(song.id)

        self.stats.put("topplayed", topplayed[:self.playingstatslength], txn=self.txn)

    def _unindexsong_stats(self, song):
        """ delete  playing (and creation) statistics for song """
        # some assumptions made:
        # - if lastplayed info is changed for a song, this song has been
        #   played and, thus, gets added to the top of the lastplayed list
        lastadded = self.stats.get("lastadded", txn=self.txn)
        lastplayed = self.stats.get("lastplayed", txn=self.txn)
        topplayed = self.stats.get("topplayed", txn=self.txn)

        if song.id in lastadded:
            lastadded.remove(song.id)
            self.stats.put("lastadded", lastadded, txn=self.txn)

        newlastplayed = []
        for asongid, alastplayed in lastplayed:
            if song.id != asongid:
                newlastplayed.append((asongid, alastplayed))
        if len(lastplayed) != len(newlastplayed):
            self.stats.put("lastplayed", newlastplayed, txn=self.txn)

        if song.id in topplayed:
            topplayed.remove(song.id)
            self.stats.put("topplayed", topplayed, txn=self.txn)

    def _indexsong(self, song):
        self._indexsong_album(song)
        self._indexsong_artist(song)
        for index in self.indices:
            self._indexsong_index(song, index)
        self._indexsong_stats(song)

    def _reindexsong(self, oldsong, newsong):
        reindex = False
        # check whether we have to update the indices
        if oldsong.album != newsong.album or oldsong.artist != newsong.artist:
            reindex = True
        else:
            for index in self.indices:
                if getattr(oldsong, index) != getattr(newsong, index):
                    reindex = True
                    break
        if reindex:
            # The update process of the album and artist information
            # is split into three parts to prevent an intermediate
            # deletion of artist and/or album (together with its rating
            # information)
            self._unindexsong_album(oldsong)
            self._unindexsong_artist(oldsong)
            for index in self.indices:
                self._unindexsong_index(oldsong, index)

            self._indexsong_album(newsong)
            self._indexsong_artist(newsong)
            for index in self.indices:
                self._indexsong_index(newsong, index)
        # update playing statistics if necessary
        if (oldsong.lastplayed != newsong.lastplayed or
            oldsong.nrplayed != newsong.nrplayed):
            self._indexsong_stats(newsong)

    def _unindexsong(self, song):
        self._unindexsong_album(song)
        self._unindexsong_artist(song)
        for index in self.indices:
            self._unindexsong_index(song, index)
        self._unindexsong_stats(song)

    # methods for registering, deleting and updating of song database

    def _queryregistersong(self, path):
        """get song info from database or insert new one"""

        path = os.path.normpath(path)

        # check if we are allowed to store this song in this database
        if not path.startswith(self.basedir):
            return None

        # we assume that the relative (with respect to the basedir)
        # path of the song is the song id.  This allows to quickly
        # verify (without reading the song itself) whether we have
        # already registered the song Otherwise, we would have to
        # create a song instance, which is quite costly.
        if self.basedir.endswith("/"):
           songid = path[len(self.basedir):]
        else:
           songid = path[len(self.basedir)+1:]
        try:
            song = self.songs[songid]
        except KeyError:
            song = dbitem.song(songid, self.basedir, self.tracknrandtitlere, self.tagcapitalize, self.tagstripleadingarticle, self.tagremoveaccents)

            self._txn_begin()
            try:
                self.songs.put(song.id, song, txn=self.txn)
                # insert into indices
                self._indexsong(song)
            except:
                self._txn_abort()
                raise
            else:
                self._txn_commit()
                log.debug("new song %s" % path)

        return song

    def _delsong(self, song):
        """delete song from database"""
        if not self.songs.has_key(song.id):
            raise KeyError

        log.debug("delete song: %s" % str(song))
        self._txn_begin()
        try:
            self._unindexsong(song)
            self.songs.delete(song.id, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    def _updatesong(self, song):
        """updates entry of given song"""

        if not isinstance(song, dbitem.song):
            log.error("updatesong: song has to be a dbitem.song instance, not a %s instance" % repr(song.__class__))
            return

        self._txn_begin()
        try:
            oldsong = self.songs.get(song.id, txn=self.txn)
            self.songs.put(song.id, song, txn=self.txn)
            self._reindexsong(oldsong, song)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()
        hub.notify(events.songchanged(self.id, song))

    def _registersong(self, song):
        """register song into database or rescan existent one"""

        # check if we are allowed to store this song in this database
        if not song.path.startswith(self.basedir):
            return

        if song.id in self.songs:
            # if the song is already in the database, we just update
            # its id3 information (in case that it changed) and
            # write the new song in the database
            newsong = self.songs[song.id]
            newsong.update(song)
            self._updatesong(newsong)
        else:
            self._txn_begin()
            try:
                self.songs.put(song.id, song, txn=self.txn)
                # insert into indices
                self._indexsong(song)
            except:
                self._txn_abort()
                raise
            else:
                self._txn_commit()

    def _rescansong(self, song):
        """reread id3 information of song (or delete it if it does not longer exist)"""
        try:
            song.scanfile(self.basedir,
                          self.tracknrandtitlere,
                          self.tagcapitalize, self.tagstripleadingarticle, self.tagremoveaccents)
            self._updatesong(song)
        except IOError:
            self._delsong(song)

    def _registerplaylist(self, playlist):
        # also try to register songs in playlist and delete song, if
        # this fails
        paths = []
        for path in playlist.songs:
            try:
                if self._queryregistersong(path) is not None:
                    paths.append(path)
            except (IOError, OSError):
                pass
        playlist.songs = paths

        # a resulting, non-empty playlist can be written in the database
        if playlist.songs:
            self._txn_begin()
            try:
                self.playlists.put(playlist.path, playlist, txn=self.txn)
                hub.notify(events.dbplaylistchanged(self.id, playlist))
            except:
                self._txn_abort()
                raise
            else:
                self._txn_commit()

    def _delplaylist(self, playlist):
        """delete playlist from database"""
        if not self.playlists.has_key(playlist.id):
            raise KeyError

        log.debug("delete playlist: %s" % str(playlist))
        self._txn_begin()
        try:
            self.playlists.delete(playlist.id, txn=self.txn)
            hub.notify(events.dbplaylistchanged(self.id, playlist))
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    _updateplaylist = _registerplaylist

    def _updatealbum(self, album):
        """updates entry of given album of artist"""
        # XXX: changes of other indices not handled correctly
        self._txn_begin()
        try:
            self.albums.put(album.id, album, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    def _updateartist(self, artist):
        """updates entry of given artist"""
        # XXX: changes of other indices not handled correctly

        self._txn_begin()
        try:
            # update artist cache if existent
            self.artists.put(artist.name, artist, txn=self.txn)
        except:
            self._txn_abort()
            raise
        else:
            self._txn_commit()

    # read-only methods for accesing the database

    ##########################################################################################
    # !!! It is not save to call any of the following methods when a transaction is active !!!
    ##########################################################################################

    def _getsong(self, id):
        """return song entry with given id"""
        song = self.songs.get(id)
        return song

    def _getalbum(self, album):
        """return given album"""
        return self.albums[album]

    def _getartist(self, artist):
        """return given artist"""
        return self.artists.get(artist)

    def _filtersongs(self, songs, filters):
        """return items matching filters"""
        for filter in filters:
            indexname = filter.indexname
            indexid = filter.indexid
            songs = [song for song in songs if getattr(song, indexname) == indexid]
        return songs

    def _getsongs(self, artist=None, album=None, filters=None):
        """ returns song of given artist, album and with song.indexname==indexid

        All values either have to be strings or None, in which case they are ignored.
        """

        if artist is None and album is None and not filters:
            # return all songs in songdb
            # songs = map(self.songs.get, self.songs.keys())
            return self.songs.values()

        if not filters:
            if album is None:
                # return all songs of a given artist
                keys = self._getartist(artist).songs
                songs = map(self.songs.get, keys)
                return songs
            elif artist is None:
                keys = self._getalbum(album).songs
                return map(self.songs.get, keys)
            else:
                # return all songs on a given album of a given artist
                # We first determine all songs of the artist and filter afterwards
                # for the songs on the given album. Doing it the other way round,
                # turns out to be really bad for the special case of an unknown
                # album which contains songs of many artists.
                keys = self._getartist(artist).songs
                songs = map(self.songs.get, keys)
                return [song for song in songs if song.album==album]
        else:
            # filters specified
            if artist is None and album is None:
                index = getattr(self, filters[0].indexname+"s")
                songs = map(self.songs.get, index[str(filters[0].indexid)].songs)
                return self._filtersongs(songs, filters[1:])
            else:
                songs = self._getsongs(artist=artist, album=album)
                return self._filtersongs(songs, filters)

    def _filteralbumartists(self, itemname, filters, itemids=None):
        itemgetter = getattr(self, itemname).get
        # consider case without filters separately
        if not filters:
           if itemids is None:
               itemids = getattr(self, itemname).keys()
           return map(itemgetter, itemids)

        if itemids is None:
            index = getattr(self, filters[0].indexname+"s")
            itemids = getattr(index[str(filters[0].indexid)], itemname)
            filters = filters[1:]
        # we use a hash to construction of the intersection of the results of the various filters
        items = {}
        for itemid in itemids:
            items[itemid] = itemgetter(itemid)

        for filter in filters:
            newitems = {}
            index = getattr(self, filter.indexname+"s")
            for itemid in getattr(index[str(filter.indexid)], itemname):
                if itemid in items:
                    newitems[itemid] = items[itemid]
            items = newitems
        return items.values()

    def _getartists(self, filters=None):
        """return all stored artists"""
        return self._filteralbumartists("artists", filters)

    def _getalbums(self, artist=None, filters=None):
        """return albums of a given artist and genre

        artist has to be a string. If it is none, all stored
        albums are returned
        """
        if artist is None:
            return self._filteralbumartists("albums", filters)
        else:
            return self._filteralbumartists("albums", filters, self.artists[artist].albums)

    def _filterindex(self, index, filters):
        """ return all keys in index filtered by filters """
        items = getattr(self, index).values()
        if filters:
            for filter in filters:
                newitems = []
                indexname = filter.indexname
                indexid = filter.indexid
                for item in items:
                    for song in map(self.songs.get, item.songs):
                        if getattr(song, indexname) == indexid:
                            newitems.append(item)
                            break
                items = newitems
        return items

    def _getgenres(self, filters):
        """return all stored genres"""
        return self._filterindex("genres", filters)

    def _getdecades(self, filters):
        """return all stored decades"""
        return self._filterindex("decades", filters)

    def _getratings(self, filters):
        """return all stored ratings"""
        return self._filterindex("ratings", filters)

    def _getlastplayedsongs(self, filters):
        """return the last played songs"""
        if not filters:
            return [(self.songs[songid], playingtime) for songid, playingtime in self.stats["lastplayed"]]
        else:
            songs = [self.songs[songid] for songid, playingtime in self.stats["lastplayed"]]
            filteredsongids = [song.id for song in self._filtersongs(songs, filters)]
            return [(self.songs[songid], playingtime) for songid, playingtime in self.stats["lastplayed"]
                    if songid in filteredsongids]

    def _gettopplayedsongs(self, filters):
        """return the top played songs"""
        keys = self.stats["topplayed"]
        return self._filtersongs(map(self.songs.get, keys), filters)

    def _getlastaddedsongs(self, filters):
        """return the last played songs"""
        keys = self.stats["lastadded"]
        return self._filtersongs(map(self.songs.get, keys), filters)

    def _getplaylist(self, path):
        """returns playlist entry with given path"""
        return self.playlists.get(path)

    def _getplaylists(self):
        return self.playlists.values()

    def _getsongsinplaylist(self, path):
        playlist = self._getplaylist(path)
        result = []
        for path in playlist.songs:
            try:
                song = self._queryregistersong(path)
                if song:
                    result.append(song)
            except IOError:
                pass
        return result

    def _getsongsinplaylists(self):
        playlists = self._getplaylists()
        songs = []
        for playlist in playlists:
            songs.extend(self._getsongsinplaylist(playlist.path))
        return songs

    def isbusy(self):
        """ check whether db is currently busy """
        return self.txn is not None or self.channel.queue.qsize()>0

    # event handlers

    def checkpointdb(self, event):
        """flush memory pool, write checkpoint record to log and flush flog"""
        if event.songdbid == self.id:
            self._checkpoint()

    def updatesong(self, event):
        if event.songdbid == self.id:
            try:
                self._updatesong(event.song)
            except KeyError:
                pass

    def rescansong(self, event):
        if event.songdbid == self.id:
            try:
                self._rescansong(event.song)
            except KeyError:
                pass

    def delsong(self, event):
        if event.songdbid == self.id:
            try:
                self._delsong(event.song)
            except KeyError:
                pass

    def updatealbum(self, event):
        if event.songdbid == self.id:
            try:
                self._updatealbum(event.album)
            except KeyError:
                pass

    def updateartist(self, event):
        if event.songdbid == self.id:
            try:
                self._updateartist(event.artist)
            except KeyError:
                pass

    def registersongs(self, event):
        if event.songdbid == self.id:
            for song in event.songs:
                try: self._registersong(song)
                except (IOError, OSError): pass

    def registerplaylists(self, event):
        if event.songdbid == self.id:
            for playlist in event.playlists:
                try: self._registerplaylist(playlist)
                except (IOError, OSError): pass

    def delplaylist(self, event):
        if event.songdbid == self.id:
            try:
                self._delplaylist(event.playlist)
            except KeyError:
                pass

    def updateplaylist(self, event):
        if event.songdbid == self.id:
            try:
                self._updateplaylist(event.playlist)
            except KeyError:
                pass

    def clearstats(self, event):
        if event.songdbid == self.id:
            self._clearstats()

    # request handlers

    def getdatabasestats(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        numberofdecades = self.getnumberofdecades(requests.getnumberofdecades(self.id))
        return songdbstats(self.id, "local", self.basedir, None, self.dbenvdir, self.cachesize,
                           len(self.songs), len(self.albums), len(self.artists),
                           len(self.genres), numberofdecades)

    def getnumberofsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return len(self.songs)

    def getnumberofdecades(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return len(self.decades.keys())

    def getnumberofgenres(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        # XXX why does len(self.genres) not work???
        # return len(self.genres)
        return len(self.genres.keys())

    def getnumberofratings(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        # XXX why does len(self.genres) not work???
        # return len(self.genres)
        return len(self.ratings.keys())

    def getnumberofalbums(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        # see above
        return len(self.albums.keys())

    def getnumberofartists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        # see above
        return len(self.artists.keys())

    def queryregistersong(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._queryregistersong(request.path)

    def getsong(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getsong(request.id)
        except KeyError:
            return None

    def getsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getsongs(request.artist, request.album, request.filters)
        except (KeyError, AttributeError, TypeError):
            return []

    def getartists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getartists(request.filters)
        except KeyError:
            return []

    def getartist(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getartist(request.artist)
        except KeyError:
            return None

    def getalbums(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getalbums(request.artist, request.filters)
        except KeyError:
            return []

    def getalbum(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        try:
            return self._getalbum(request.album)
        except KeyError:
            return None

    def getgenres(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getgenres(request.filters)

    def getdecades(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getdecades(request.filters)

    def getratings(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getratings(request.filters)

    def getlastplayedsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getlastplayedsongs(request.filters)

    def gettopplayedsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._gettopplayedsongs(request.filters)

    def getlastaddedsongs(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getlastaddedsongs(request.filters)

    def getplaylist(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getplaylist(request.path)

    def getplaylists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getplaylists()

    def getsongsinplaylist(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getsongsinplaylist(request.path)

    def getsongsinplaylists(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        return self._getsongsinplaylists()

#
# thread for automatic registering and rescanning of songs in database
#

class songautoregisterer(service.service):

    def __init__(self, basedir, songdbid, dbbusymethod,
                 tracknrandtitlere, tagcapitalize, tagstripleadingarticle, tagremoveaccents):
        service.service.__init__(self, "songautoregisterer", daemonize=True)
        self.basedir = basedir
        self.songdbid = songdbid
        self.dbbusymethod = dbbusymethod
        self.tracknrandtitlere = tracknrandtitlere
        self.tagcapitalize = tagcapitalize
        self.tagstripleadingarticle = tagstripleadingarticle
        self.tagremoveaccents = tagremoveaccents
        self.done = False
        # support file extensions
        self.supportedextensions = metadata.getextensions()

        # checkpoint count used to determine the number of requests in between 
        # checkpoint calls
        self.checkpointcount = 0

        self.channel.subscribe(events.autoregistersongs, self.autoregistersongs)
        self.channel.subscribe(events.rescansongs, self.rescansongs)

    def _notify(self, event):
        """ wait until db is not busy, send event and checkpoint db regularly """
        while self.dbbusymethod():
            time.sleep(0.1)
        hub.notify(event, -100)
        self.checkpointcount += 1
        if self.checkpointcount == 100:
            hub.notify(events.checkpointdb(self.songdbid), -100)
            self.checkpointcount = 0

    def registerdirtree(self, dir):
        """ scan for songs and playlists in dir and its subdirectories, returning all items which have been scanned """
        log.debug("registerer: entering %s"% dir)
        self.channel.process()
        if self.done: return []
        songpaths = []
        playlistpaths = []
        registereditems = []
        # number of songs sent to the database at one time
        dividesongsby = 5

        # scan for paths of songs and playlists and recursively call registering of subdirectories
        for name in os.listdir(dir):
            path = os.path.join(dir, name)
            extension = os.path.splitext(path)[1].lower()
            if os.access(path, os.R_OK):
                if os.path.isdir(path):
                    try:
                        registereditems.extend(self.registerdirtree(path))
                    except (IOError, OSError), e:
                        log.warning("songautoregisterer: could not enter dir %s: %s" % (path, e))
                elif extension in self.supportedextensions:
                    songpaths.append(path)
                elif extension == ".m3u":
                    playlistpaths.append(path)

        # now register songs...
        songs = []
        for path in songpaths:
            if self.basedir.endswith("/"):
               songid = path[len(self.basedir):]
            else:
               songid = path[len(self.basedir)+1:]
            songs.append(dbitem.song(songid, self.basedir,
                                     self.tracknrandtitlere,
                                     self.tagcapitalize, self.tagstripleadingarticle, self.tagremoveaccents))
        if songs:
            for i in xrange(0, len(songs), dividesongsby):
                self._notify(events.registersongs(self.songdbid, songs[i:i+dividesongsby]))
            registereditems.extend(songs)

        # ... and playlists
        playlists = [dbitem.playlist(path) for path in playlistpaths]
        if playlists:
            self._notify(events.registerplaylists(self.songdbid, playlists))

        # checkpoint regularly to prevent overly large transaction logs and wait until the
        # database is not busy any more
        if songs or playlists:
            self._notify(events.checkpointdb(self.songdbid))

        registereditems.extend(playlists)
        log.debug("registerer: leaving %s"% dir)
        return registereditems

    def run(self):
        # wait a little bit to not disturb the startup too much
        time.sleep(2)
        service.service.run(self)

    def rescansong(self, song):
        # to take load of the database thread, we also enable the songautoregisterer
        # to rescan songs
        try:
            song.scanfile(self.basedir,
                          self.tracknrandtitlere,
                          self.tagcapitalize, self.tagstripleadingarticle, self.tagremoveaccents)
            self._notify(events.updatesong(self.songdbid, song))
        except IOError:
            self._notify(events.delsong(self.songdbid, song))

    def rescanplaylist(self, playlist):
        try:
            newplaylist = dbitem.playlist(playlist.path)
            self._notify(events.updateplaylist(self.songdbid, newplaylist))
        except IOError:
            self._notify(events.delplaylist(self.songdbid, playlist))

    #
    # event handler
    #

    def autoregistersongs(self, event):
        if self.songdbid == event.songdbid:
            log.info(_("database %s: scanning for songs in %s") % (self.songdbid, self.basedir))

            # get all songs and playlists currently stored in the database
            oldsongs = hub.request(requests.getsongs(self.songdbid))
            oldplaylists = hub.request(requests.getplaylists(self.songdbid))

            # scan for all songs and playlists in the filesystem
            log.debug("database %s: searching for new songs" % self.songdbid)
            registereditems = self.registerdirtree(self.basedir)

            # update information for songs which have not yet been scanned (in particular
            # remove songs which are no longer present in the database)
            log.debug("database %s: removing stale songs" % self.songdbid)
            registereditemshash = {}
            for item in registereditems:
                registereditemshash[item] = None
            for song in oldsongs:
                if song not in registereditemshash:
                    self.rescansong(song)
            for playlist in oldplaylists:
                if playlist not in registereditemshash:
                    self.rescanplaylist(playlist)

            log.info(_("database %s: finished scanning for songs in %s") % (self.songdbid, self.basedir))

    def rescansongs(self, event):
        if self.songdbid == event.songdbid:
            log.info(_("database %s: rescanning %d songs") % (self.songdbid, len(event.songs)))
            for song in event.songs:
                self.rescansong(song)
            log.info(_("database %s: finished rescanning %d songs") % (self.songdbid, len(event.songs)))

