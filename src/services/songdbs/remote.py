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

import copy

import events, hub, requests
import log
import network
import service

#
# songdb class
#

class songdb(service.service):
    def __init__(self, id, networklocation, songdbhub):
        service.service.__init__(self, "remote songdb", hub=songdbhub)
        self.id = id
        self.networklocation = networklocation
        self.remotesongdbid = "main"
        
        self.networkchannel = network.clientchannel(self.networklocation)
        #self.networkchannel.transmit(events.updatesong)
        #self.networkchannel.transmit(events.updatealbum)
        #self.networkchannel.transmit(events.updateartist)
        #self.networkchannel.transmit(events.playlistaddsong)
        self.networkchannel.start()

        # we need to be informed about database changes
        #self.channel.subscribe(events.updatesong, self.updatesong)
        #self.channel.subscribe(events.updatealbum, self.updatealbum)
        #self.channel.subscribe(events.updateartist, self.updateartist)
        #self.channel.subscribe(events.registersongs, self.registersongs)
        #self.channel.subscribe(events.registerplaylists, self.registerplaylists)
        
        # we are a database service provider...
        self.channel.supply(requests.dbrequest, self.dbrequest)
        log.info(_("database %s: type remote, location: %s") % (self.id,
                                                                self.networklocation))

    # request handler

    def dbrequest(self, request):
        if self.id != request.songdbid:
            raise hub.DenyRequest
        log.debug("dispatching %s" % `request`)
        # we have to copy the request, because another thread may also access it
        request = copy.copy(request)
        request.songdbid = self.remotesongdbid
        result = self.networkchannel.request(request)
        log.debug("result %s" % `result`)
        # we change the databasestats accordingly
        if isinstance(request, requests.getdatabasestats):
            result.type = "remote"
            result.location = str(self.networklocation)
        return result
