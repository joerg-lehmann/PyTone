# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004 J�rg Lehmann <joerg@luga.de>
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

import copy, math, random, service, time
import config
import events, hub, requests
import dbitem, item, log

# helper function for the random selection of songs

def _genrandomchoice(songs):
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
            rating = song.rating or 3
            if song.lastplayed:
                # Simple heuristic algorithm to consider song ratings
                # for random selection. Certainly not optimal!
                last = max(0, (currenttime-song.lastplayed[-1])/60)
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
        self.resultcache = {}
        # maximal number of items stored in cache
        self.resultcachesize = 500
        # cache use statististics
        self.resultcachehits = 0
        self.resultcachemisses = 0
        
        # we are a database service provider...
        self.channel.supply(requests.dbrequestsingle, self.dbrequestsingle)
        self.channel.supply(requests.dbrequestsongs, self.dbrequestsongs)
        self.channel.supply(requests.dbrequestlist, self.dbrequestlist)
        self.channel.supply(requests.getnumberofsongs, self.getnumberofsongs)
        self.channel.supply(requests.getnumberofalbums, self.getnumberofalbums)
        self.channel.supply(requests.getnumberofdecades, self.getnumberofdecades)
        self.channel.supply(requests.getnumberofgenres, self.getnumberofgenres)
        self.channel.supply(requests.getnumberofratings, self.getnumberofratings)
        
        # and need to be informed about database changes
        self.channel.subscribe(events.dbevent, self.dbevent)

    def resetafterexception(self):
        # when an exception occurs, we clear the cache
        self.resultcache = {}

    def addsongdb(self, id, config):
        """ add songdb with id defined by config
        return id (or None if player is turned off)
        """
        type = config.type
        if type=="off":
            return None

        if type=="local":
            import songdbs.local
            songdb = songdbs.local.songdb(id, config, self.songdbhub)
        elif type=="remote":
            import songdbs.remote
            songdb = songdbs.remote.songdb(id, config.networklocation, self.songdbhub)

        self.songdbids.append(id)
        songdb.setName("song database thread (id=%s)" % id)
        songdb.start()
        if config.autoregisterer:
            hub.notify(events.autoregistersongs(id))

        return id

    # method decorators for result caching and random song selection

    def cacheresult(requesthandler):
        """ method decorator which caches results of the request """
        def newrequesthandler(self, request):
            #if self.resultcachemisses>0:
            #    log.debug("%3d%% cache hits" % (100.*self.resultcachehits/(self.resultcachehits+self.resultcachemisses)))
            requesthash = hash(request)
            log.debug("dbrequest cache query for request: %s, %d" % (request, requesthash))
            try:
                # try to get the result from the cache
                result = self.resultcache[requesthash][0]
                # update atime
                self.resultcache[requesthash][2] = time.time()
                self.resultcachehits += 1
                log.debug("dbrequest cache hit for request: %s" % request)
            except KeyError:
                # make a copy of request for later storage in cache
                requestcopy = copy.copy(request)
                result = requesthandler(self, request)
                self.resultcache[requesthash] = [result, requestcopy, time.time()]
                self.resultcachemisses += 1
                # remove least recently used items from cache
                if len(self.resultcache) > self.resultcachesize:
                    log.info("db rqeuest cache: purging old items")
                    cachebytime = [(item[2], key) for key, item in self.resultcache.items()]
                    cachebytime.sort()
                    for atime, key in cachebytime[-10:]:
                        del self.resultcache[key]
                log.debug("db request cache miss for request: %s (%d requests cached)" % (request, len(self.resultcache)))
            return result
        return newrequesthandler

    def selectrandom(requesthandler):
        """ method decorator which returns a random selection of the request result if requested

        Note that the result has to be a list of songs.
        """
        def newrequesthandler(self, request):
            songs = requesthandler(self, request)
            if request.random:
                return _genrandomchoice(songs)
            else:
                return songs
        return newrequesthandler

    def sortresult(requesthandler):
        """ method decorator which sorts the result list if requested """
        def newrequesthandler(self, request):
            result = requesthandler(self, request)
            if request.sort:
                result.sort(request.sort)
            return result
        return newrequesthandler

    # cache update

    def updatecache(self, event):
        """ update/clear resultcache when database event sent """
        if isinstance(event, (events.checkpointdb, events.autoregistersongs)):
            return
        if isinstance(event, events.updatesong):
            oldsong = self.songdbhub.request(requests.getsong(event.songdbid, event.song.id))
            newsong = event.song
            # The following is an optimization for an updatesong event which occurs rather often
            # Not very pretty, but for the moment enough
            if ( oldsong.album == newsong.album and
                 oldsong.artist == newsong.artist and
                 oldsong.genre == newsong.genre and
                 oldsong.year == newsong.year and
                 oldsong.rating == newsong.rating ):
                # only the playing information was changed, so we just
                # delete the relevant cache results

                for key, item in self.resultcache.items():
                    if isinstance(item[1], (requests.gettopplayedsongs, requests.getlastplayedsongs)):
                        del self.resultcache[key]
                return
        # otherwise we delete the queries for the correponding database (and all compound queries)
        for key, item in self.resultcache.items():
            songdbid = item[1].songdbid
            if songdbid is None or songdbid == event.songdbid:
                del self.resultcache[key]

    # event handlers

    def quit(self, event):
        service.service.quit(self, event)
        self.songdbhub.notify(events.quit())

    def dbevent(self, event):
        if event.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%s' for database event" % event.songdbid)
            return

        # first update result cache (to allow the updatechace method
        # to query the old state of the database)
        self.updatecache(event)
        # and then send the event to the database
        self.songdbhub.notify(event)

    # request handlers

    def dbrequestsingle(self, request):
        if request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%s' for database request" % request.songdbid)
            return

        result = self.songdbhub.request(request)
        # wrap all dbitm.song instances in result in a item.song instance
        if isinstance(result, dbitem.song):
            return item.song(request.songdbid, result)
        else:
            try:
                newresult = []
                for aitem in result:
                    if isinstance(aitem, dbitem.song):
                        newresult.append(item.song(request.songdbid, aitem))
                    else:
                        newresult.append(aitem)
                return newresult
            except:
                return result

    def dbrequestsongs(self, request):
        # make a copy of the original request, because we will subsequently modify it
        nrequest = copy.copy(request)
        # we do not care about the random choice flag, this is done by the method decorator
        nrequest.random = False
        # also reset the sort and wrapper function as otherwise
        # sending over the network (which requires pickling the
        # request) fails
        nrequest.sort = False
        nrequest.wrapperfunc = False
        if request.songdbid is None:
            resulthash = {}
            for songdbid in self.songdbids:
                nrequest.songdbid = songdbid
                # Query the songs in the database songdbid via dbrequestsongs to cache
                # the result.
                # Note that in the case of getlastplayedsongs requests, we cheat
                # a little bit, since then the result of the database request is a tuple
                # (playingtime, dbsong). Correspondingly, wrapperfunc has to deal
                # with such tuples instead of with the dbsongs themselves.
                for dbsong in self.dbrequestsongs(nrequest):
                    resulthash[dbsong] = songdbid
            if request.wrapperfunc:
                return [request.wrapperfunc(dbsong, songdbid) for dbsong, songdbid in resulthash.items()]
            else:
                return resulthash.values()
        elif request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%s' for database request" % request.songdbid)
            return
        else:
            dbsongs = self.songdbhub.request(nrequest)
            if request.wrapperfunc:
                return [request.wrapperfunc(dbsong, request.songdbid) for dbsong in dbsongs]
            else:
                return dbsongs
    dbrequestsongs = selectrandom(cacheresult(sortresult(dbrequestsongs)))

    def dbrequestlist(self, request):
        # make a copy of the original request, because we will subsequently modify it
        nrequest = copy.copy(request)
        # we do not want to wrap and sort the intermediate results
        nrequest.wrapperfunc = None
        nrequest.sort = False

        if request.songdbid is None:
            resulthash = {}
            for songdbid in self.songdbids:
                nrequest.songdbid = songdbid
                for result in self.dbrequestlist(nrequest):
                    resulthash[result] = songdbid
            if request.wrapperfunc is not None:
                return [request.wrapperfunc(item, songdbid) for item, songdbid in resulthash.items()]
            else:
                return resulthash.keys()
        elif request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%s' for database request" % request.songdbid)
        else:
            # use nrequest here instead of request in order to not
            # send wrapperfunc and sort to database (this fails when
            # using a network channel, since we cannot pickle these
            # objects)
            result = self.songdbhub.request(nrequest)
            if request.wrapperfunc is not None:
                return [request.wrapperfunc(item, request.songdbid) for item in result]
            else:
                return result
    dbrequestlist = cacheresult(sortresult(dbrequestlist))

    # requests which return number of items of a certain kind

    def _requestnumbers(self, request, listrequest, requestkwargs={}):
        """ helper method for a request which queries for the number of items.
        
        If a database is specified, the corresponding database request is
        executed directly. Otherwise, the length of the result of listrequest
        is returned. """
        if request.songdbid is not None and request.songdbid not in self.songdbids:
            log.error("songdbmanager: invalid songdbid '%s' for database request" % request.songdbid)
        elif request.songdbid is None or requestkwargs:
            if issubclass(listrequest, requests.dbrequestlist):
                return len(self.dbrequestlist(listrequest(songdbid=None, **requestkwargs)))
            else:
                return len(self.dbrequestsongs(listrequest(songdbid=None, **requestkwargs)))
        else:
            return self.songdbhub.request(request)

    def getnumberofsongs(self, request):
        if request.artist is request.album is request.indexname is request.indexid is None:
            requestkwargs = {}
        else:
            requestkwargs = { "artist": request.artist,
                              "album": request.album,
                              "indexname": request.indexname,
                              "indexid": request.indexid }
        return self._requestnumbers(request, requests.getsongs, requestkwargs)
    getnumberofsongs = cacheresult(getnumberofsongs)

    def getnumberofalbums(self, request):
        return self._requestnumbers(request, requests.getalbums)
    getnumberofalbums = cacheresult(getnumberofalbums)

    def getnumberofdecades(self, request):
        return self._requestnumbers(request, requests.getdecades)
    getnumberofdecades = cacheresult(getnumberofdecades)

    def getnumberofgenres(self, request):
        return self._requestnumbers(request, requests.getgenres)
    getnumberofgenres = cacheresult(getnumberofgenres)

    def getnumberofratings(self, request):
        return self._requestnumbers(request, requests.getratings)
    getnumberofratings = cacheresult(getnumberofratings)
        