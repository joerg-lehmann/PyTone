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

import copy, gc, math, random, service, time
import config
import events, hub, requests
import metadata
import item
import log

# helper function for the random selection of songs


#
# a collection of statistical information
#

class songdbmanagerstats:
    def __init__(self, songdbsstats, requestcachesize, requestcachemaxsize,
                 requestcacherequests, requestcachehits, requestcachemisses):
        self.songdbsstats = songdbsstats
        self.requestcachesize = requestcachesize
        self.requestcachemaxsize = requestcachemaxsize
        self.requestcacherequests = requestcacherequests
        self.requestcachehits = requestcachehits
        self.requestcachemisses = requestcachemisses

#
# the song database manager class
#

class songdbmanager(service.service):
    """ song database manager

    The song database manager receives database events and requests, passes them on to
    the various databases, collects the results and delivers them back to the caller.
    - Results of database requests are cached.
    - dbitem.song instances are wrapped in item.song instances which also contain the
      id of the database where the song is stored.
    - Random song selections are handled.

    """

    def __init__(self):
        service.service.__init__(self, "songdb manager")

        # hub for the various song databases
        self.songdbhub = hub.hub()

        # list of registered songdbs
        self.songdbids = []

        # result cache containing a mapping hash(request) -> (request, result, lastaccess)
        self.requestcache = {}
        # maximal number of objects referred by request cache
        self.requestcachemaxsize = config.database.requestcachesize
        # cache use statististics
        self.requestcachehits = 0
        self.requestcachemisses = 0
        # current number of objects referred to by items in result cache
        self.requestcachesize = 0 

        # we are a database service provider...
        self.channel.supply(requests.dbrequestsingle, self.dbrequestsingle)
        self.channel.supply(requests.dbrequestsongs, self.dbrequestsongs)
        self.channel.supply(requests.dbrequestlist, self.dbrequestlist)
        self.channel.supply(requests.getdatabasestats, self.getdatabasestats)
        self.channel.supply(requests.getnumberofsongs, self.getnumberofsongs)
        self.channel.supply(requests.getnumberofalbums, self.getnumberofalbums)
        self.channel.supply(requests.getnumberofartists, self.getnumberofartists)
        self.channel.supply(requests.getnumberoftags, self.getnumberoftags)
        self.channel.supply(requests.getnumberofratings, self.getnumberofratings)

        # and need to be informed about database changes
        self.channel.subscribe(events.dbevent, self.dbevent)

        # finally, we supply some information about the databases and the cache
        self.channel.supply(requests.getsongdbmanagerstats, self.getsongdbmanagerstats)

    def resetafterexception(self):
        # when an exception occurs, we clear the cache
        self.requestcache = {}

    def addsongdb(self, id, config):
        """ add songdb with id defined by config
        return id (or None if player is turned off)
        """
        type = config.type
        if type=="off":
            return None

        if type=="local":
            import songdbs.sqlite
            songdb = songdbs.sqlite.songdb(id, config, self.songdbhub)
        elif type=="remote":
            import songdbs.remote
            songdb = songdbs.remote.songdb(id, config.networklocation, self.songdbhub)

        for postprocessor_name in config.postprocessors:
            try:
                metadata.get_metadata_postprocessor(postprocessor_name)
            except:
                raise RuntimeError("Unkown metadata postprocesor '%s' for database '%r'" % (postprocessor_name, id))

        self.songdbids.append(id)
        songdb.setName("song database thread (id=%s)" % id)
        songdb.start()
        if config.autoregisterer:
            hub.notify(events.autoregistersongs(id))
            hub.notify(events.autoregisterplaylists(id))

        return id

    # method decorators for result caching and random song selection

    def cacheresult(requesthandler):
        """ method decorator which caches results of the request """
        def newrequesthandler(self, request):
            log.debug("dbrequest cache: query for request: %r" % request)
            requesthash = hash(request)
            log.debug("dbrequest cache: sucessfully hashed request: %d" % requesthash)
            try:
                # try to get the result from the cache
                result = self.requestcache[requesthash][0]
                # update atime
                self.requestcache[requesthash][2] = time.time()
                self.requestcachehits += 1
                log.debug("dbrequest cache: hit for request: %r" % request)
            except KeyError:
                # make a copy of request for later storage in cache
                requestcopy = copy.copy(request)
                result = requesthandler(self, request)
                resultnoobjects = len(gc.get_referents(result)) + 1
                self.requestcache[requesthash] = [result, requestcopy, time.time(), resultnoobjects]
                self.requestcachemisses += 1
                self.requestcachesize += resultnoobjects
                # remove least recently used items from cache
                if self.requestcachesize > self.requestcachemaxsize:
                    log.debug("dbrequest cache: purging old items")
                    cachebytime = [(item[2], key) for key, item in self.requestcache.items()]
                    cachebytime.sort()
                    for atime, key in cachebytime[-10:]:
                        self.requestcachesize -= self.requestcache[key][3]
                        del self.requestcache[key]
                log.debug("db request cache miss for request: %r (%d requests and %d objects cached)" %
                          (request, len(self.requestcache), self.requestcachesize))
            return result
        return newrequesthandler

    def _genrandomchoice(self, songs):
        """ returns random selection of songs up to the maximal length
        configured. Note that this method changes as a side-effect the
        parameter songs"""

        # consider trivial case separately
        if not songs:
            return []

        # choose item, avoiding duplicates. Stop after a predefined
        # total length (in seconds). Take rating of songs/albums/artists
        # into account
        length = 0
        result = []

        # generate an initial random sample of large enough size samplesize 
        # to choose from
        samplesize = min(100, len(songs))
        sample = random.sample(songs, samplesize)
        currenttime = time.time()

        # relative percentage of songs accepted with a given rating
        ratingdistribution = [5, 10, 20, 30, 35]

        # normalize distribution
        normfactor = float(sum(ratingdistribution))
        ratingdistribution = [x/normfactor for x in ratingdistribution]

        # scale for rating reduction: for playing times longer
        # ago than lastplayedscale seconds, the rating is not
        # influenced.
        lastplayedscale = 60.0 * 60 * 24

        while length < config.general.randominsertlength:
            for song in sample:
                # we have to query the song from our databases 
                # since otherwise this is done automatically leading to
                # a deadlock
                if song.song_metadata is None:
                    song.song_metadata = self.songdbhub.request(requests.getsong_metadata(song.songdbid, song.id))
                    # if the song has been deleted in the meantime, we proceed to the next one
                    if song.song_metadata is None:
                        continue
                if song.rating:
                    rating = song.rating
                else:
                    # punish skipped songs if they have not been rated
                    rating = min(5, max(1, 3 + max(0, 0.5*(song.playcount - song.skipcount))))
                if song.date_lastplayed:
                    # Simple heuristic algorithm to consider song ratings
                    # for random selection. Certainly not optimal!
                    last = max(0, (currenttime-song.date_lastplayed)/60)
                    rating -= 2 * math.exp(-last/lastplayedscale)
                    if rating < 1:
                        rating = 1
                if rating == 5:
                    threshold = ratingdistribution[4]
                else:
                    # get threshold by linear interpolation
                    intpart = int(rating)
                    rest = rating-intpart
                    threshold = (ratingdistribution[intpart-1] +
                                 (ratingdistribution[intpart] - ratingdistribution[intpart-1])*rest)
                if random.random() <= threshold or len(sample) == 1:
                    result.append(song)
                    length += song.length
                    if length >= config.general.randominsertlength or len(result) >= samplesize:
                        return result
            # recreate sample without already chosen songs, if we ran out of songs
            sample = [song for song in sample if song not in result]
        return result


    def selectrandom(requesthandler):
        """ method decorator which returns a random selection of the request result if requested

        Note that the result has to be a list of songs.
        """
        def newrequesthandler(self, request):
            songs = requesthandler(self, request)
            if request.random:
                 return self._genrandomchoice(songs)
            else:
                 return songs
        return newrequesthandler

    def sortresult(requesthandler):
        """ method decorator which sorts the result list if requested """
        def newrequesthandler(self, request):
            result = requesthandler(self, request)
            # XXX turned off
            if request.sort and 0:
                result.sort(request.sort)
            return result
        return newrequesthandler

    # cache update

    def updatecache(self, event):
        """ update/clear requestcache when database event sent """
        if isinstance(event, (events.checkpointdb, events.autoregistersongs)):
            return
        if isinstance(event, events.update_song):
            oldsong_metadata = self.songdbhub.request(requests.getsong_metadata(event.songdbid, event.song.id))
            newsong_metadata = event.song.song_metadata
            # The following is an optimization for an update_song event which occurs rather often
            # Not very pretty, but for the moment enough
            if ( oldsong_metadata.album == newsong_metadata.album and
                 oldsong_metadata.artist == newsong_metadata.artist and
                 oldsong_metadata.tags == newsong_metadata.tags and
                 oldsong_metadata.rating == newsong_metadata.rating ):
                # only the playing information was changed, so we just
                # delete the relevant cache results

                for key, item in self.requestcache.items():
                    if isinstance(item[1], (requests.getsongs)):
                        del self.requestcache[key]
                return
        # otherwise we delete the queries for the correponding database (and all compound queries)
        log.debug("dbrequest cache: emptying cache for database %r" % event.songdbid)
        for key, item in self.requestcache.items():
            songdbid = item[1].songdbid
            if songdbid is None or songdbid == event.songdbid:
                del self.requestcache[key]

    # event handlers

    def quit(self, event):
        service.service.quit(self, event)
        self.songdbhub.notify(events.quit())

    def dbevent(self, event):
        if event.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database event" % event.songdbid)
            return

        # first update result cache (to allow the updatecache method
        # to query the old state of the database)
        self.updatecache(event)
        # and then send the event to the database
        self.songdbhub.notify(event)

    # request handlers

    def dbrequestsingle(self, request):
        if request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
            return

        return self.songdbhub.request(request)

    def dbrequestsongs(self, request):
        # make a copy of the original request, because we will subsequently modify it
        nrequest = copy.copy(request)
        # also reset the sort function as otherwise
        # sending over the network (which requires pickling the
        # request) fails
        # XXX we disable this at the moment
        if request.songdbid is None:
            nrequest.sort = False
            resulthash = {}
            for songdbid in self.songdbids:
                nrequest.songdbid = songdbid
                # Query the songs in the database songdbid via dbrequestsongs to cache
                # the result.
                # Note that in the case of getlastplayedsongs requests, we cheat
                # a little bit, since then the result of the database request is a tuple
                # (playingtime, dbsong).
                for dbsong in self.dbrequestsongs(nrequest):
                    resulthash[dbsong] = songdbid
            return resulthash.values()
        elif request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
            return
        else:
            return self.songdbhub.request(nrequest)
    dbrequestsongs = selectrandom(cacheresult(sortresult(dbrequestsongs)))

    def dbrequestlist(self, request):
        # make a copy of the original request, because we will subsequently modify it
        nrequest = copy.copy(request)

        if request.songdbid is None:
            resulthash = {}
            for songdbid in self.songdbids:
                nrequest.songdbid = songdbid
                for result in self.dbrequestlist(nrequest):
                    resulthash[result] = songdbid
            # sort results
            return resulthash.keys()
        elif request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
        else:
            # use nrequest here instead of request in order to not
            # send sort to database (this fails when
            # using a network channel, since we cannot pickle these
            # objects)
            return self.songdbhub.request(nrequest)
    dbrequestlist = cacheresult(dbrequestlist)

    def getdatabasestats(self, request):
        if request.songdbid is None:
            return "Virtual", ""
        elif request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
        else:
            return self.songdbhub.request(request)

    # requests which return number of items of a certain kind

    def getnumberofsongs(self, request):
        if request.songdbid is not None and request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
        # XXX use filters in sqlite instead
        if request.songdbid is not None and request.filters is None:
            return self.songdbhub.request(request)
        else:
            return len(self.dbrequestsongs(requests.getsongs(songdbid=request.songdbid,
                                                             filters=request.filters)))
    getnumberofsongs = cacheresult(getnumberofsongs)

    def _requestnumbers(self, request, listrequest):
        """ helper method for a request which queries for the number of items.

        If a database is specified, the corresponding database request is
        executed directly. Otherwise, the length of the result of listrequest
        is returned. """
        if request.songdbid is not None and request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%r' for database request" % request.songdbid)
        elif request.songdbid is None or request.filters:
            return len(self.dbrequestlist(listrequest(songdbid=request.songdbid, filters=request.filters)))
        else:
            return self.songdbhub.request(request)

    def getnumberofalbums(self, request):
        return self._requestnumbers(request, requests.getalbums)
    getnumberofalbums = cacheresult(getnumberofalbums)

    def getnumberoftags(self, request):
        return self._requestnumbers(request, requests.gettags)
    getnumberoftags = cacheresult(getnumberoftags)

    def getnumberofartists(self, request):
        return self._requestnumbers(request, requests.getartists)
    getnumberofartists = cacheresult(getnumberofartists)

    def getnumberofratings(self, request):
        return self._requestnumbers(request, requests.getratings)
    getnumberofratings = cacheresult(getnumberofratings)

    def getsongdbmanagerstats(self, request):
        songdbsstats = []
        for songdbid in self.songdbids:
            songdbsstats.append(self.songdbhub.request(requests.getdatabasestats(songdbid)))
        return songdbmanagerstats(songdbsstats,
                                  self.requestcachesize, self.requestcachemaxsize,
                                  len(self.requestcache),
                                  self.requestcachehits, self.requestcachemisses)
